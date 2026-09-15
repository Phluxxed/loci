"""Acceptance for the fixed complete-work graph control and source receipts."""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

from mcp import Client, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.types import CallToolResult
import pytest

from benchmarks.complete_work.control import (
    ControlConfig,
    DIRECT_POLICY,
    ReceiptStore,
    load_receipts,
    receipt_source_bytes,
)
from loci.mcp_output_models import LociReadOutput, LociRetrieveOutput


ROOT = Path(__file__).parents[1]


def _write_config(
    path: Path,
    *,
    target: Path,
    arm: str,
    store: Path,
    receipts: Path,
) -> None:
    path.write_text(json.dumps({
        "schema_version": 1,
        "target_root": str(target.resolve()),
        "arm": arm,
        "store_dir": str(store.resolve()),
        "receipt_dir": str(receipts.resolve()),
        "store_namespace": "complete-work-control-v1",
    }), encoding="utf-8")


def _server(config: Path) -> StdioServerParameters:
    env = os.environ.copy()
    python_path = [str(ROOT), str(ROOT / "src")]
    if env.get("PYTHONPATH"):
        python_path.append(env["PYTHONPATH"])
    env["PYTHONPATH"] = os.pathsep.join(python_path)
    return StdioServerParameters(
        command=sys.executable,
        args=["-m", "benchmarks.complete_work.control", str(config)],
        env=env,
        cwd=ROOT,
    )


def _prepare(config: Path) -> dict:
    params = _server(config)
    completed = subprocess.run(
        [params.command, "-m", "benchmarks.complete_work.control", "--prepare", str(config)],
        env=params.env,
        cwd=params.cwd,
        capture_output=True,
        text=True,
        timeout=30,
        check=True,
    )
    return json.loads(completed.stdout)


def _fixture_repo(path: Path) -> bytes:
    path.mkdir()
    (path / "callee.py").write_text(
        "def callee() -> int:\n    return 7\n", encoding="utf-8",
    )
    body = (
        "from callee import callee\n\n"
        "def caller() -> int:\n"
        "    # " + "direct source receipt paging " * 430 + "\n"
        "    return callee()\n"
    ).encode()
    (path / "caller.py").write_bytes(body)
    return body


def _anchor_source(payload: dict) -> tuple[dict, dict]:
    item = next(value for value in payload["items"] if value["role"] == "anchor")
    source = next(value for value in payload["sources"] if value["id"] in item["source_ids"])
    return item, source


def test_real_stdio_arms_match_selection_and_preserve_source_history(tmp_path: Path) -> None:
    repo = tmp_path / "target"
    original = _fixture_repo(repo)
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "hidden.py").write_text("secret = True\n", encoding="utf-8")
    configs: dict[str, Path] = {}
    receipt_dirs: dict[str, Path] = {}
    for arm in ("on", "off"):
        configs[arm] = tmp_path / f"{arm}.json"
        receipt_dirs[arm] = tmp_path / f"{arm}-receipts"
        _write_config(
            configs[arm],
            target=repo,
            arm=arm,
            store=tmp_path / f"{arm}-store",
            receipts=receipt_dirs[arm],
        )
        prepared = _prepare(configs[arm])
        assert prepared["symbols_indexed"] >= 2

    async def exercise() -> tuple[dict, dict]:
        descriptors: dict[str, list[dict]] = {}
        payloads: dict[str, dict] = {}
        for arm in ("on", "off"):
            async with Client(stdio_client(_server(configs[arm]))) as session:
                listed = await session.list_tools()
                assert {tool.name for tool in listed.tools} == {"loci_retrieve", "loci_read"}
                descriptors[arm] = [
                    tool.model_dump(mode="json", by_alias=True, exclude_none=True)
                    for tool in sorted(listed.tools, key=lambda value: value.name)
                ]
                result = await session.call_tool(
                    "loci_retrieve", {"repo": str(repo), "query": "caller"},
                )
                assert result.is_error is False, result.structured_content
                assert isinstance(result.structured_content, dict)
                payloads[arm] = result.structured_content

                item, _source = _anchor_source(payloads[arm])
                reference = item["source_ref"]
                pages: list[str] = []
                while reference is not None:
                    read = await session.call_tool(
                        "loci_read", {"repo": str(repo), "source_ref": reference},
                    )
                    assert read.is_error is False, read.structured_content
                    assert isinstance(read.structured_content, dict)
                    LociReadOutput.model_validate(read.structured_content)
                    pages.append(read.structured_content["source"]["content"])
                    reference = read.structured_content["next_source_ref"]
                expected = original[item["extent"]["start_byte"]:item["extent"]["end_byte"]]
                assert "".join(pages).encode() == expected
                assert len(pages) > 1

                rejected = await session.call_tool(
                    "loci_retrieve", {"repo": str(outside), "query": "hidden"},
                )
                assert rejected.is_error is True
                assert rejected.structured_content["error"]["code"] == "REPOSITORY_OUT_OF_SCOPE"
                rejected_read = await session.call_tool(
                    "loci_read", {"repo": str(outside), "source_ref": item["source_ref"]},
                )
                assert rejected_read.is_error is True
                assert (
                    rejected_read.structured_content["error"]["code"]
                    == "REPOSITORY_OUT_OF_SCOPE"
                )
        assert descriptors["on"] == descriptors["off"]
        return payloads["on"], payloads["off"]

    on, off = asyncio.run(exercise())
    LociRetrieveOutput.model_validate(on)
    on_item, on_source = _anchor_source(on)
    off_item, off_source = _anchor_source(off)
    assert on["anchors"] == off["anchors"]
    assert on_item["extent"] == off_item["extent"]
    assert on_source["content"] == off_source["content"]
    assert on["policy"] == "normal-graph-v1"
    assert on["relationships"]
    assert on["usage"]["edges_traversed"] > 0
    assert off["policy"] == DIRECT_POLICY
    assert off["scope"]["relationships"] == "omitted_by_benchmark_control"
    assert off["relationships"] == []
    assert off["ownership"] == []
    assert off["usage"]["eligible_edges_considered"] == 0
    assert off["usage"]["edges_traversed"] == 0
    visible_off = json.dumps(
        {"content": [], "structuredContent": off, "isError": False},
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode()
    assert off["usage"]["output_bytes"] == len(visible_off)

    first_receipts = load_receipts(receipt_dirs["off"])
    retrieve_receipt = first_receipts[0]
    source_version = next(
        value for value in retrieve_receipt["source_versions"]
        if value["file"] == "caller.py"
    )
    assert receipt_source_bytes(receipt_dirs["off"], source_version["sha256"]) == original
    packet_path = receipt_dirs["off"] / retrieve_receipt["packet"]["path"]
    packet = packet_path.read_bytes()
    assert hashlib.sha256(packet).hexdigest() == retrieve_receipt["packet"]["sha256"]
    assert any(
        value["operation_outcome"] == "error"
        and value["operation"] == "loci_retrieve"
        for value in first_receipts
    )

    old_reference = off_item["source_ref"]
    changed = original + b"\ndef changed_after_first_call() -> bool:\n    return True\n"
    (repo / "caller.py").write_bytes(changed)

    async def freshness() -> dict:
        async with Client(stdio_client(_server(configs["off"]))) as session:
            stale = await session.call_tool(
                "loci_read", {"repo": str(repo), "source_ref": old_reference},
            )
            assert stale.is_error is True
            assert stale.structured_content["error"]["code"] == "SOURCE_STALE"
            fresh = await session.call_tool(
                "loci_retrieve", {"repo": str(repo), "query": "caller"},
            )
            assert fresh.is_error is False
            return fresh.structured_content

    fresh = asyncio.run(freshness())
    fresh_item, _fresh_source = _anchor_source(fresh)
    assert fresh_item["extent"]["content_hash"] != off_item["extent"]["content_hash"]
    all_receipts = load_receipts(receipt_dirs["off"])
    assert [value["sequence"] for value in all_receipts] == list(range(1, len(all_receipts) + 1))
    assert any(
        value["operation_outcome"] == "error"
        and value["operation"] == "loci_read"
        for value in all_receipts
    )
    fresh_version = next(
        version
        for receipt in all_receipts
        for version in receipt["source_versions"]
        if version["file"] == "caller.py" and version["sha256"] != source_version["sha256"]
    )
    assert receipt_source_bytes(receipt_dirs["off"], fresh_version["sha256"]) == changed


def test_receipt_validation_turns_a_bad_extent_into_a_retained_failure(tmp_path: Path) -> None:
    repo = tmp_path / "target"
    repo.mkdir()
    raw = b"value = 1\n"
    (repo / "sample.py").write_bytes(raw)
    config_path = tmp_path / "config.json"
    receipts = tmp_path / "receipts"
    _write_config(
        config_path,
        target=repo,
        arm="off",
        store=tmp_path / "store",
        receipts=receipts,
    )
    store = ReceiptStore(ControlConfig.load(config_path))
    bad = CallToolResult(content=[], structured_content={
        "schema_version": 1,
        "status": "ok",
        "source": {
            "file": "sample.py",
            "content_hash": hashlib.sha256(raw).hexdigest(),
            "start_byte": 0,
            "end_byte": len(raw),
            "start_line": 1,
            "end_line": 1,
            "content": "wrong\n",
        },
    }, is_error=False)
    returned = store.record(
        "loci_read", {"repo": str(repo), "source_ref": "test"}, bad,
        started_unix_ns=1,
    )
    assert returned.is_error is True
    assert returned.structured_content["error"]["code"] == "SOURCE_RECEIPT_FAILED"
    receipt = load_receipts(receipts)[0]
    assert receipt["operation_outcome"] == "success"
    assert receipt["outcome"] == "error"
    assert receipt["validation"]["status"] == "failed"
    assert receipt["operation_packet"] != receipt["packet"]
    assert receipt_source_bytes(receipts, hashlib.sha256(raw).hexdigest()) == raw


def test_config_rejects_target_that_contains_control_and_oracles(tmp_path: Path) -> None:
    config = tmp_path / "unsafe.json"
    _write_config(
        config,
        target=ROOT,
        arm="on",
        store=tmp_path / "store",
        receipts=tmp_path / "receipts",
    )
    with pytest.raises(ValueError, match="control/oracle"):
        ControlConfig.load(config)
