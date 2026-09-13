"""Regression coverage for resolver controls through the comparison adapter."""
from __future__ import annotations

import asyncio
import hashlib
import json
from pathlib import Path

import pytest

from benchmarks.multilingual_context_observed import MultilingualObservedTrace
from benchmarks.multilingual_context_tools import MultilingualAdapter, create_server
from benchmarks.typescript_context_corpus import _isolated_store
from loci import service


CONTROLS_PATH = (
    Path(__file__).parents[1]
    / "benchmarks"
    / "comparisons"
    / "multilingual-context-workflow-v1"
    / "inputs"
    / "comparison-controls.json"
)


def _write_snapshot(repo: Path) -> dict[str, bytes]:
    sources = {
        "go.mod": b"module example.test/control\n\ngo 1.25\n// caf\xc3\xa9\n",
        "main.go": b"package main\n\nfunc main() {}\n",
        "crates/widget/Cargo.toml": (
            b"[package]\nname = \"widget\"\nversion = \"0.1.0\"\n"
            b"edition = \"2024\"\n# caf\xc3\xa9\n"
        ),
        "crates/widget/src/lib.rs": b"pub fn widget() {}\n",
    }
    for relative, content in sources.items():
        target = repo / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
    return sources


def _adapter(repo: Path, files: dict[str, bytes], arm: str) -> MultilingualAdapter:
    controls = json.loads(CONTROLS_PATH.read_text(encoding="utf-8"))
    index = service.get_store().load(repo)
    assert index is not None

    trace = MultilingualObservedTrace.__new__(MultilingualObservedTrace)
    trace.files = files
    trace.identity = {
        "task_id": "resolver-control-adapter",
        "session_id": f"resolver-control-adapter-{arm}",
        "arm": arm,
        "repetition": 1,
        "snapshot": "temporary-resolver-controls",
    }
    trace.events = []

    adapter = MultilingualAdapter.__new__(MultilingualAdapter)
    adapter.run = {"arm": arm}
    adapter.repo = repo.resolve()
    adapter.limits = dict(controls["limits"])
    adapter.trace = trace
    adapter.symbols = {symbol["id"]: symbol for symbol in index["symbols"]}
    adapter.lines = {
        name: content.decode("utf-8").splitlines(keepends=True)
        for name, content in files.items()
    }
    adapter.failures = []
    adapter.deliveries = []
    adapter.lock = asyncio.Lock()
    adapter.attempts = 0
    adapter.is_v2 = True
    return adapter


def _call_file(
    adapter: MultilingualAdapter,
    arm: str,
    file_path: str,
    *,
    start_line: int | None = None,
    end_line: int | None = None,
):
    server = create_server(adapter, arm)
    return asyncio.run(
        server.call_tool(
            "file",
            {"file_path": file_path, "start_line": start_line, "end_line": end_line},
        )
    )


@pytest.mark.parametrize("arm", ["A", "B"])
def test_both_arms_deliver_exact_go_and_cargo_controls_with_bounded_accounting(
    tmp_path: Path,
    arm: str,
) -> None:
    repo = tmp_path / "snapshot"
    files = _write_snapshot(repo)

    with _isolated_store(tmp_path / "cache"):
        service.index_repo(repo, incremental=False)
        service.reset_session_stats()
        adapter = _adapter(repo, files, arm)

        reads = [
            ("go.mod", 2, 4),
            ("crates/widget/Cargo.toml", 2, 5),
        ]
        expected_source_bytes = 0
        expected_file_bytes = 0
        for file_path, start_line, end_line in reads:
            response = _call_file(
                adapter,
                arm,
                file_path,
                start_line=start_line,
                end_line=end_line,
            )
            result = response.structured_content
            assert isinstance(result, dict)
            lines = files[file_path].decode("utf-8").splitlines(keepends=True)
            expected_content = "".join(lines[start_line - 1 : end_line])
            expected_start_byte = len("".join(lines[: start_line - 1]).encode("utf-8"))

            assert set(result) == {
                "file", "content", "total_lines", "start_line", "end_line", "_evaluation",
            }
            assert result["file"] == file_path
            assert result["content"] == expected_content
            assert result["total_lines"] == len(lines)
            assert result["start_line"] == start_line
            assert result["end_line"] == end_line

            source_bytes = len(expected_content.encode("utf-8"))
            event = adapter.trace.events[-1]
            delivery = adapter.deliveries[-1]
            expected_span = {
                "file": file_path,
                "start_byte": expected_start_byte,
                "end_byte": expected_start_byte + source_bytes,
                "sha256": hashlib.sha256(expected_content.encode("utf-8")).hexdigest(),
                "text": expected_content,
            }
            assert event["spans"] == [expected_span]
            assert event["source_bytes"] == source_bytes
            assert delivery["spans"] == [expected_span]
            assert delivery["source_bytes"] == source_bytes
            assert delivery["serialized_bytes"] == len(delivery["response_json"].encode("utf-8"))
            assert source_bytes <= adapter.limits["max_evidence_bytes"]
            assert delivery["serialized_bytes"] <= adapter.limits[
                "max_serialized_output_bytes_per_operation"
            ]

            expected_source_bytes += source_bytes
            expected_file_bytes += len(files[file_path])

        assert not adapter.failures
        assert sum(item["source_bytes"] for item in adapter.deliveries) == expected_source_bytes
        assert expected_source_bytes <= adapter.limits["max_source_bytes_per_run"]
        assert sum(item["serialized_bytes"] for item in adapter.deliveries) <= adapter.limits[
            "max_serialized_output_bytes_per_run"
        ]

        stats = service.session_stats(repo=str(repo.resolve()))
        assert stats["total_gets"] == 2
        assert stats["symbol_bytes_retrieved"] == expected_source_bytes
        assert stats["file_bytes_not_loaded"] == expected_file_bytes - expected_source_bytes


@pytest.mark.parametrize("arm", ["A", "B"])
def test_both_arms_report_stale_control_without_delivering_source(
    tmp_path: Path,
    arm: str,
) -> None:
    repo = tmp_path / "snapshot"
    files = _write_snapshot(repo)

    with _isolated_store(tmp_path / "cache"):
        service.index_repo(repo, incremental=False)
        service.reset_session_stats()
        adapter = _adapter(repo, files, arm)
        changed = b"module example.test/changed\n\ngo 1.25\n"
        (repo / "go.mod").write_bytes(changed)

        response = _call_file(adapter, arm, "go.mod")
        result = response.structured_content
        assert isinstance(result, dict)
        assert result["error"]["code"] == "LociError"
        assert result["error"]["message"] == (
            "Resolver control differs from indexed input; refresh the index"
        )
        assert files["go.mod"].decode("utf-8") not in json.dumps(result)
        assert changed.decode("utf-8") not in json.dumps(result)

        assert adapter.failures[-1]["category"] == "tool_error"
        assert adapter.trace.events[-1]["source_bytes"] == 0
        assert adapter.trace.events[-1]["spans"] == []
        assert adapter.deliveries[-1]["source_bytes"] == 0
        assert adapter.deliveries[-1]["spans"] == []
        assert service.session_stats(repo=str(repo.resolve()))["total_gets"] == 0
