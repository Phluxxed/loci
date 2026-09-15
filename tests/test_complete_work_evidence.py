from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from mcp.types import CallToolResult

from benchmarks.complete_work.control import ControlConfig, ReceiptStore
from benchmarks.complete_work.evidence import summarize_delivery


def _config(tmp_path: Path, target: Path) -> ControlConfig:
    raw = {
        "schema_version": 1, "target_root": str(target), "arm": "on",
        "store_dir": str(tmp_path / "store"), "receipt_dir": str(tmp_path / "receipts"),
        "store_namespace": "evidence-test",
    }
    path = tmp_path / "control.json"
    path.write_text(json.dumps(raw), encoding="utf-8")
    return ControlConfig.load(path)


def _payload(path: Path, *, graph: bool = False) -> dict:
    raw = path.read_bytes()
    source = {
        "file": path.name, "content_hash": hashlib.sha256(raw).hexdigest(),
        "start_byte": 0, "end_byte": len(raw), "start_line": 1, "end_line": 1,
        "content": raw.decode("utf-8"),
    }
    payload = {"sources": [source], "items": [], "relationships": []}
    if graph:
        payload["relationships"] = [{"proof": "complete", "edge": {"evidence": {
            "file": path.name, "content_hash": source["content_hash"], "line": 1,
        }}}]
    return payload


def _packet(receipt_dir: Path, descriptor: dict) -> dict:
    return json.loads((receipt_dir / descriptor["path"]).read_text(encoding="utf-8"))


def _native_result(receipt_dir: Path, receipt: dict) -> dict:
    """Match the installed McpToolCallResult schema, which has no isError."""
    result = _packet(receipt_dir, receipt["packet"])
    result.pop("isError")
    result["_meta"] = None
    return result


def _native_item(receipt_dir: Path, receipt: dict, *, capture_started=None, capture_completed=None) -> dict:
    return {
        "type": "mcpToolCall", "id": f"item-{receipt['sequence']}", "server": "loci",
        "tool": receipt["operation"], "arguments": receipt["arguments"],
        "status": "completed", "error": None, "result": _native_result(receipt_dir, receipt),
        "capture_started": capture_started, "capture_completed": capture_completed,
    }


def _accounting(receipts: list[dict], receipt_dir: Path) -> dict:
    stages = []
    for stage_id, receipt in zip(("orient", "implement", "continue"), receipts, strict=True):
        stages.append({"stage_id": stage_id, "items": [_native_item(receipt_dir, receipt)]})
    return {"stages": stages}


def _utc(ns: int) -> str:
    return datetime.fromtimestamp(ns / 1_000_000_000, timezone.utc).isoformat()


def _rewrite_receipt_windows(receipt_dir: Path, windows: list[tuple[int, int]]) -> list[dict]:
    paths = sorted((receipt_dir / "receipts").glob("*.json"))
    for path, (started, recorded) in zip(paths, windows, strict=True):
        value = json.loads(path.read_text(encoding="utf-8"))
        value["started_unix_ns"] = started
        value["recorded_unix_ns"] = recorded
        path.write_text(json.dumps(value), encoding="utf-8")
    return [json.loads(path.read_text(encoding="utf-8")) for path in paths]


def test_join_retains_three_stages_versions_exact_packets_duplicates_and_graph_delivery(tmp_path: Path) -> None:
    target = tmp_path / "target"
    target.mkdir()
    source = target / "source.py"
    source.write_text("alpha\n", encoding="utf-8")
    store = ReceiptStore(_config(tmp_path, target))
    first = store.record("loci_retrieve", {"repo": str(target), "query": "alpha"},
                         CallToolResult(content=[], structured_content=_payload(source, graph=True), is_error=False), started_unix_ns=1)
    assert not first.is_error
    second = store.record("loci_read", {"repo": str(target), "source_ref": "same"},
                          CallToolResult(content=[], structured_content=_payload(source), is_error=False), started_unix_ns=2)
    assert not second.is_error
    source.write_text("beta changed\n", encoding="utf-8")
    third = store.record("loci_retrieve", {"repo": str(target), "query": "beta"},
                         CallToolResult(content=[], structured_content=_payload(source), is_error=False), started_unix_ns=3)
    assert not third.is_error
    receipt_dir = tmp_path / "receipts"
    receipts = [json.loads(path.read_text(encoding="utf-8")) for path in sorted((receipt_dir / "receipts").glob("*.json"))]

    result = summarize_delivery(receipt_dir, _accounting(receipts, receipt_dir))

    assert result["status"] == "known", result
    assert [stage["stage_id"] for stage in result["stages"]] == ["continue", "implement", "orient"]
    assert result["episode"]["matched_calls"] == 3
    assert result["episode"]["packet_bytes"] == sum(row["packet"]["bytes"] for row in receipts)
    assert result["episode"]["relationships_delivered"] == 1
    assert result["episode"]["proofs_delivered"] == 1
    assert result["episode"]["repeated_unchanged_source_bytes"] == len(b"alpha\n")
    assert result["episode"]["unique_unchanged_source_bytes"] == len(b"alpha\n") + len(b"beta changed\n")
    assert len(result["source_versions"]) == 2
    assert "provider-token" in result["limitations"][0]


def test_unmatched_ambiguous_and_missing_native_mcp_telemetry_are_unknown(tmp_path: Path) -> None:
    target = tmp_path / "target"
    target.mkdir()
    source = target / "source.py"
    source.write_text("alpha\n", encoding="utf-8")
    store = ReceiptStore(_config(tmp_path, target))
    store.record("loci_retrieve", {"repo": str(target), "query": "alpha"},
                 CallToolResult(content=[], structured_content=_payload(source), is_error=False), started_unix_ns=1)
    receipt_dir = tmp_path / "receipts"
    receipt = json.loads(next((receipt_dir / "receipts").glob("*.json")).read_text(encoding="utf-8"))
    item = {**_native_item(receipt_dir, receipt), "tool": "mcp__loci__loci_retrieve"}

    unmatched = summarize_delivery(receipt_dir, {"stages": [{"stage_id": "orient", "items": [{**item, "arguments": {"repo": "wrong"}}]}]})
    assert unmatched["status"] == "unknown"
    assert unmatched["errors"][0]["code"] == "NATIVE_MATCH_UNAVAILABLE"

    ambiguous = summarize_delivery(receipt_dir, {"stages": [{"stage_id": "orient", "items": [item, item]}]})
    assert ambiguous["status"] == "unknown"
    assert ambiguous["errors"][0]["code"] == "NATIVE_MATCH_AMBIGUOUS"

    missing = summarize_delivery(receipt_dir, {"stages": [{"stage_id": "orient", "items": []}]})
    assert missing["status"] == "unknown"
    assert missing["errors"][0]["code"] == "NATIVE_MCP_TELEMETRY_UNAVAILABLE"
    assert missing["stages"][0]["status"] == "unknown"


def test_retrieve_defaults_match_native_omissions_without_collapsing_seed_ids_empty_list(tmp_path: Path) -> None:
    target = tmp_path / "target"
    target.mkdir()
    source = target / "source.py"
    source.write_text("alpha\n", encoding="utf-8")
    store = ReceiptStore(_config(tmp_path, target))
    store.record("loci_retrieve", {"repo": str(target), "query": "", "seed_ids": None},
                 CallToolResult(content=[], structured_content=_payload(source), is_error=False), started_unix_ns=1)
    receipt_dir = tmp_path / "receipts"
    receipt = json.loads(next((receipt_dir / "receipts").glob("*.json")).read_text(encoding="utf-8"))
    native = _native_item(receipt_dir, receipt)
    native["arguments"] = {"repo": str(target), "query": ""}

    matched = summarize_delivery(receipt_dir, {"stages": [{"stage_id": "orient", "items": [native]}]})
    assert matched["status"] == "known", matched

    native["arguments"] = {"repo": str(target), "query": "", "seed_ids": []}
    changed = summarize_delivery(receipt_dir, {"stages": [{"stage_id": "orient", "items": [native]}]})
    assert changed["status"] == "unknown"
    assert {error["code"] for error in changed["errors"]} >= {"NATIVE_MATCH_UNAVAILABLE", "NATIVE_CALL_UNPAIRED"}


def test_identical_receipts_are_not_double_counted_and_unpaired_native_marks_its_stage_unknown(tmp_path: Path) -> None:
    target = tmp_path / "target"
    target.mkdir()
    source = target / "source.py"
    source.write_text("alpha\n", encoding="utf-8")
    store = ReceiptStore(_config(tmp_path, target))
    for started in (1, 2):
        store.record("loci_read", {"repo": str(target), "source_ref": "same"},
                     CallToolResult(content=[], structured_content=_payload(source), is_error=False), started_unix_ns=started)
    receipt_dir = tmp_path / "receipts"
    receipts = [json.loads(path.read_text(encoding="utf-8")) for path in sorted((receipt_dir / "receipts").glob("*.json"))]
    one_native = _native_item(receipt_dir, receipts[0])

    result = summarize_delivery(receipt_dir, {"stages": [{"stage_id": "implement", "items": [one_native]}]})

    assert result["status"] == "unknown"
    assert result["episode"]["matched_calls"] == 0
    assert result["episode"]["packet_bytes"] == 0
    assert {error["code"] for error in result["errors"]} >= {"NATIVE_MATCH_CONFLICT", "NATIVE_CALL_UNPAIRED"}
    assert result["stages"][0]["status"] == "unknown"


def test_capture_intervals_disambiguate_identical_successful_native_results_without_iserror(tmp_path: Path) -> None:
    target = tmp_path / "target"
    target.mkdir()
    source = target / "source.py"
    source.write_text("alpha\n", encoding="utf-8")
    store = ReceiptStore(_config(tmp_path, target))
    for started in (1, 2):
        store.record("loci_read", {"repo": str(target), "source_ref": "same"},
                     CallToolResult(content=[], structured_content=_payload(source), is_error=False), started_unix_ns=started)
    receipt_dir = tmp_path / "receipts"
    receipts = _rewrite_receipt_windows(receipt_dir, [(1_000_000_000, 2_000_000_000), (3_000_000_000, 4_000_000_000)])
    items = [
        _native_item(receipt_dir, receipt,
                     capture_started={"utc": _utc(started - 1), "emitted_at_ms": index * 10},
                     capture_completed={"utc": _utc(recorded + 1), "emitted_at_ms": index * 10 + 1})
        for index, (receipt, (started, recorded)) in enumerate(zip(receipts, [(1_000_000_000, 2_000_000_000), (3_000_000_000, 4_000_000_000)], strict=True))
    ]
    assert all("isError" not in item["result"] for item in items)

    result = summarize_delivery(receipt_dir, {"stages": [{"stage_id": "continue", "items": items}]})

    assert result["status"] == "known", result
    assert result["episode"]["matched_calls"] == 2
    assert result["episode"]["repeated_unchanged_source_bytes"] == len(b"alpha\n")


def test_extra_or_failed_native_mcp_items_stay_unknown(tmp_path: Path) -> None:
    target = tmp_path / "target"
    target.mkdir()
    source = target / "source.py"
    source.write_text("alpha\n", encoding="utf-8")
    store = ReceiptStore(_config(tmp_path, target))
    store.record("loci_read", {"repo": str(target), "source_ref": "same"},
                 CallToolResult(content=[], structured_content=_payload(source), is_error=False), started_unix_ns=1)
    receipt_dir = tmp_path / "receipts"
    receipt = json.loads(next((receipt_dir / "receipts").glob("*.json")).read_text(encoding="utf-8"))
    matched = _native_item(receipt_dir, receipt)
    extra = {**_native_item(receipt_dir, receipt), "id": "extra", "arguments": {"repo": str(target), "source_ref": "other"}}
    failed = {**_native_item(receipt_dir, receipt), "id": "failed", "status": "failed", "error": {"message": "tool failed"}, "result": None}

    result = summarize_delivery(receipt_dir, {"stages": [{"stage_id": "implement", "items": [matched, extra, failed]}]})

    assert result["status"] == "unknown"
    assert result["episode"]["matched_calls"] == 1
    assert result["stages"][0]["status"] == "unknown"
    assert {error["code"] for error in result["errors"]} >= {"NATIVE_CALL_UNPAIRED", "NATIVE_MCP_ITEM_UNMATCHABLE"}


def test_corrupt_control_receipt_stops_the_join_before_any_attribution(tmp_path: Path) -> None:
    target = tmp_path / "target"
    target.mkdir()
    source = target / "source.py"
    source.write_text("alpha\n", encoding="utf-8")
    store = ReceiptStore(_config(tmp_path, target))
    store.record("loci_read", {"repo": str(target), "source_ref": "one"},
                 CallToolResult(content=[], structured_content=_payload(source), is_error=False), started_unix_ns=1)
    receipt_dir = tmp_path / "receipts"
    receipt = json.loads(next((receipt_dir / "receipts").glob("*.json")).read_text(encoding="utf-8"))
    (receipt_dir / receipt["operation_packet"]["path"]).write_bytes(b"corrupt")

    result = summarize_delivery(receipt_dir, {"stages": []})

    assert result["status"] == "unknown"
    assert result["errors"][0]["code"] == "RECEIPT_LOAD_FAILED"
    assert result["episode"] == {}
