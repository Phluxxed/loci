"""Cross-module acceptance for the complete-work episode capture pipeline."""
from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
import subprocess
import sys
import time

from mcp import Client, StdioServerParameters
from mcp.client.stdio import stdio_client
import pytest

from benchmarks.complete_work.accounting import summarize
from benchmarks.complete_work.control import load_receipts, receipt_source_bytes
from benchmarks.complete_work.controller import run_stages, source_snapshot, write_json
from benchmarks.complete_work.evaluate import restore_snapshot, snapshot_diff
from benchmarks.complete_work.evidence import summarize_delivery
from benchmarks.complete_work.runtime import Journal


ROOT = Path(__file__).parents[1]
THREAD_ID = "thread-integration"
STAGES = [
    {"stage_id": "orient", "prompt": "inspect", "cap_seconds": 120},
    {"stage_id": "implement", "prompt": "edit", "cap_seconds": 360},
    {"stage_id": "continue", "prompt": "verify", "cap_seconds": 240},
]
CALLER_VERSIONS = (
    b"from callee import callee\n\ndef caller() -> int:\n    return callee()\n",
    b"from callee import callee\n\ndef caller() -> int:\n    return callee() + 1\n",
    b"from callee import callee\n\ndef caller() -> int:\n    return callee() + 2\n",
)
USAGE_TOTALS = (
    (100, 20, 10, 2, 110),
    (160, 30, 20, 4, 180),
    (210, 35, 30, 6, 240),
)


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


def _prepare(config: Path) -> None:
    server = _server(config)
    subprocess.run(
        [server.command, "-m", "benchmarks.complete_work.control", "--prepare", str(config)],
        cwd=server.cwd,
        env=server.env,
        capture_output=True,
        text=True,
        timeout=30,
        check=True,
    )


async def _retrieve(config: Path, arguments: dict) -> dict:
    async with Client(stdio_client(_server(config))) as session:
        result = await session.call_tool("loci_retrieve", arguments)
        assert result.is_error is False, result.structured_content
        return result.model_dump(mode="json", by_alias=True, exclude_none=True)


def _received(journal: Journal, method: str, params: dict) -> None:
    journal.write("received", {
        "method": method,
        "params": params,
        "emittedAtMs": time.time_ns() / 1_000_000,
    })


class ScriptedNativeClient:
    """Drive fixed turns while preserving the native events the runtime emits."""

    def __init__(self, repo: Path, config: Path, journal: Journal) -> None:
        self.repo = repo
        self.config = config
        self.journal = journal
        self.turn_index = 0
        self.active_turn: str | None = None
        self.closed = False

    def call(self, method: str, params: dict, *, timeout: float = 30) -> dict:
        if method == "turn/start":
            self.turn_index += 1
            self.active_turn = f"turn-{self.turn_index}"
            return {"turn": {"id": self.active_turn}}
        if method == "turn/interrupt":
            return {"interrupted": True}
        raise AssertionError(f"unexpected scripted call: {method}")

    def next_event(self, timeout: float) -> dict:
        assert timeout > 0
        assert self.active_turn is not None
        stage_index = self.turn_index - 1
        (self.repo / "caller.py").write_bytes(CALLER_VERSIONS[stage_index])
        arguments = {"repo": str(self.repo), "query": "caller", "seed_ids": None}
        item_id = f"mcp-{self.turn_index}"
        common = {
            "threadId": THREAD_ID,
            "turnId": self.active_turn,
        }
        _received(self.journal, "item/started", {**common, "item": {
            "id": item_id,
            "type": "mcpToolCall",
            "server": "loci",
            "tool": "loci_retrieve",
            "arguments": arguments,
            "status": "inProgress",
        }})
        packet = asyncio.run(_retrieve(self.config, arguments))
        assert packet.pop("isError") is False
        # The Python MCP client adds its own server-info metadata; the native
        # App Server McpToolCallResult captured by this harness does not.
        packet.pop("_meta", None)
        _received(self.journal, "item/completed", {**common, "item": {
            "id": item_id,
            "type": "mcpToolCall",
            "server": "loci",
            "tool": "loci_retrieve",
            "arguments": arguments,
            "status": "completed",
            "error": None,
            # Installed ThreadStartResponse.McpToolCallResult omits isError.
            "result": packet,
        }})
        input_tokens, cached_tokens, output_tokens, reasoning_tokens, total_tokens = USAGE_TOTALS[stage_index]
        _received(self.journal, "thread/tokenUsage/updated", {**common, "tokenUsage": {"total": {
            "inputTokens": input_tokens,
            "cachedInputTokens": cached_tokens,
            "outputTokens": output_tokens,
            "reasoningOutputTokens": reasoning_tokens,
            "totalTokens": total_tokens,
            "cacheWriteInputTokens": 0,
        }}})
        _received(self.journal, "rawResponse/completed", {
            **common,
            "responseId": f"response-{self.turn_index}",
        })
        completed = {
            "method": "turn/completed",
            "params": {"threadId": THREAD_ID, "turn": {
                "id": self.active_turn,
                "status": "completed",
                "error": None,
            }},
        }
        self.journal.write("received", completed)
        return completed

    def close(self) -> None:
        self.closed = True


@pytest.mark.parametrize("arm", ("on", "off"))
def test_fixed_episode_assembles_control_accounting_delivery_and_stage_replay(
    tmp_path: Path,
    arm: str,
) -> None:
    repo = tmp_path / "target"
    repo.mkdir()
    (repo / "callee.py").write_text(
        "def callee() -> int:\n    return 7\n",
        encoding="utf-8",
    )
    (repo / "caller.py").write_bytes(CALLER_VERSIONS[0])
    receipts = tmp_path / "receipts"
    config = tmp_path / "control.json"
    config.write_text(json.dumps({
        "schema_version": 1,
        "target_root": str(repo),
        "arm": arm,
        "store_dir": str(tmp_path / "store"),
        "receipt_dir": str(receipts),
        "store_namespace": f"integration-{arm}",
    }), encoding="utf-8")
    _prepare(config)

    output = tmp_path / "output"
    output.mkdir()
    before = source_snapshot(repo, output / "source-history")
    write_json(output / "source-before.json", before)
    journal_path = output / "wire.jsonl"
    journal = Journal(journal_path)
    client = ScriptedNativeClient(repo, config, journal)
    try:
        rows = run_stages(client, journal, THREAD_ID, repo, STAGES, output)
    finally:
        journal.close()

    assert [row["stage_id"] for row in rows] == ["orient", "implement", "continue"]
    assert [row["outcome"] for row in rows] == ["completed", "completed", "completed"]
    assert client.closed is False

    accounting = summarize(journal_path, rows, THREAD_ID)
    assert accounting["usage_status"] == "known"
    assert accounting["usage"] == {
        "inputTokens": 210,
        "cachedInputTokens": 35,
        "outputTokens": 30,
        "reasoningOutputTokens": 6,
        "totalTokens": 240,
        "cacheWriteInputTokens": 0,
        "uncachedInputTokens": 175,
    }
    assert [stage["usage"]["inputTokens"] for stage in accounting["stages"]] == [100, 60, 50]
    assert [stage["mcp_calls"] for stage in accounting["stages"]] == [1, 1, 1]
    assert [stage["observed_completed_model_requests"] for stage in accounting["stages"]] == [1, 1, 1]
    assert accounting["phase_groups"]["downstream"]["usage"]["inputTokens"] == 110

    delivery = summarize_delivery(receipts, accounting)
    retained = load_receipts(receipts)
    assert delivery["status"] == "known", delivery["errors"]
    assert delivery["arm"] == arm
    assert delivery["episode"]["receipt_calls"] == 3
    assert delivery["episode"]["matched_calls"] == 3
    assert delivery["episode"]["packet_bytes"] == sum(row["packet"]["bytes"] for row in retained)
    assert delivery["episode"]["source_content_bytes"] == sum(
        stage["source_content_bytes"] for stage in delivery["stages"]
    )
    assert delivery["episode"]["source_content_bytes"] == (
        delivery["episode"]["unique_unchanged_source_bytes"]
        + delivery["episode"]["repeated_unchanged_source_bytes"]
    )
    assert all(stage["status"] == "known" and len(stage["calls"]) == 1
               for stage in delivery["stages"])
    if arm == "on":
        assert delivery["episode"]["relationships_delivered"] > 0
        assert delivery["episode"]["proofs_delivered"] > 0
    else:
        assert delivery["episode"]["relationships_delivered"] == 0
        assert delivery["episode"]["proofs_delivered"] == 0

    caller_versions = {
        version["sha256"]: receipt_source_bytes(receipts, version["sha256"])
        for version in delivery["source_versions"]
        if version["file"] == "caller.py"
    }
    assert set(caller_versions.values()) == set(CALLER_VERSIONS)

    implement = json.loads((output / "source-after-implement.json").read_text(encoding="utf-8"))
    continuation = json.loads((output / "source-after-continue.json").read_text(encoding="utf-8"))
    replay = tmp_path / "implement-replay"
    restore_snapshot(implement, output / "source-history", replay)
    assert (replay / "caller.py").read_bytes() == CALLER_VERSIONS[1]
    assert (repo / "caller.py").read_bytes() == CALLER_VERSIONS[2]

    changes, implementation_patch = snapshot_diff(before, implement, output / "source-history")
    assert [change["file"] for change in changes] == ["caller.py"]
    assert "return callee() + 1" in implementation_patch
    assert "return callee() + 2" not in implementation_patch
    continuation_changes, continuation_patch = snapshot_diff(
        implement,
        continuation,
        output / "source-history",
    )
    assert [change["file"] for change in continuation_changes] == ["caller.py"]
    assert "return callee() + 2" in continuation_patch
