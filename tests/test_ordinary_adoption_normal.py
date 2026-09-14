from __future__ import annotations

import json
from pathlib import Path

import pytest

from benchmarks.ordinary_adoption_normal import normal_evidence_registry, observe_normal_rollout


THREAD = "normal-thread"
TURN = "normal-turn"
HASH = "a" * 64


def _metadata() -> dict[str, str]:
    return {
        "run_id": "normal-run",
        "case_id": "normal-case",
        "condition": "ordinary_delegate",
        "purpose": "ordinary",
        "thread_id": THREAD,
        "turn_id": TURN,
        "target_repo": "/repo",
    }


def _mcp(item_id: str, tool: str, structured: dict, *, is_error: bool = False) -> dict:
    return {
        "type": "event_msg",
        "payload": {
            "type": "item_completed",
            "thread_id": THREAD,
            "turn_id": TURN,
            "started_at_ms": 1,
            "completed_at_ms": 2,
            "item": {
                "type": "McpToolCall",
                "id": item_id,
                "server": "loci",
                "tool": tool,
                "arguments": {"repo": "/repo", **({"query": "entry"} if tool == "loci_retrieve" else {"source_ref": "ref"})},
                "status": "completed",
                "duration": {"secs": 0, "nanos": 1},
                "result": {"content": [], "structuredContent": structured, "isError": is_error},
            },
        },
    }


def _finalize_output_bytes(structured: dict) -> dict:
    usage = structured.setdefault("usage", {})
    usage["output_bytes"] = 0
    for _ in range(16):
        result = {"content": [], "structuredContent": structured, "isError": False}
        size = len(json.dumps(result, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))
        if usage["output_bytes"] == size:
            return structured
        usage["output_bytes"] = size
    raise AssertionError("fixture output byte accounting did not converge")


def _fixture_evidence_bytes(sources: list[dict]) -> int:
    intervals: dict[tuple[str, str], list[tuple[int, int]]] = {}
    try:
        for source in sources:
            intervals.setdefault((source["file"], source["content_hash"]), []).append(
                (source["start_byte"], source["end_byte"])
            )
    except (KeyError, TypeError):
        return 0
    total = 0
    for ranges in intervals.values():
        start = end = -1
        for current_start, current_end in sorted(ranges):
            if start < 0:
                start, end = current_start, current_end
            elif current_start <= end:
                end = max(end, current_end)
            else:
                total += end - start
                start, end = current_start, current_end
        if start >= 0:
            total += end - start
    return total


def _outer(call_id: str, *outputs: dict) -> list[dict]:
    return [
        {
            "type": "response_item",
            "payload": {"type": "custom_tool_call", "id": f"request-{call_id}", "call_id": call_id, "name": "exec", "input": "call"},
        },
        {
            "type": "response_item",
            "payload": {
                "type": "custom_tool_call_output",
                "id": f"output-{call_id}",
                "call_id": call_id,
                "output": [{"type": "input_text", "text": json.dumps(output, separators=(",", ":"))} for output in outputs],
            },
        },
    ]


def _records(body: list[dict]) -> list[dict]:
    records = [
        {"type": "session_meta", "payload": {"id": THREAD, "agent_path": "/root/test"}},
        {"type": "event_msg", "payload": {"type": "task_started", "turn_id": TURN}},
        {"type": "turn_context", "payload": {"turn_id": TURN, "root_turn_id": "root", "cwd": "/repo"}},
        *body,
        {
            "type": "event_msg",
            "payload": {"type": "item_completed", "item": {"type": "AgentMessage", "id": "answer", "phase": "final", "content": []}},
        },
        {"type": "event_msg", "payload": {"type": "task_complete", "turn_id": TURN}},
    ]
    for ordinal, record in enumerate(records):
        record["ordinal"] = ordinal
    return records


def _write(tmp_path: Path, body: list[dict]) -> Path:
    path = tmp_path / "normal-rollout.jsonl"
    path.write_text("".join(json.dumps(record) + "\n" for record in _records(body)), encoding="utf-8")
    return path


def _source(
    source_id: int,
    content: str,
    *,
    start: int = 10,
    end: int = 12,
    start_byte: int = 0,
) -> dict:
    return {
        "id": source_id,
        "file": "src/entry.ts",
        "start_byte": start_byte,
        "end_byte": start_byte + len(content.encode("utf-8")),
        "start_line": start,
        "end_line": end,
        "content_hash": HASH,
        "content": content,
        "source_ref": f"ref-{source_id}",
    }


def _retrieve(sources: list[dict] | None = None, relationships: list[dict] | None = None) -> dict:
    selected_sources = sources if sources is not None else [_source(1, "export function entry() {}\n")]
    payload = {
        "schema_version": 1,
        "policy": "normal-graph-v1",
        "status": "ok",
        "nodes": [{"id": "entry"}, {"id": "callee"}],
        "sources": selected_sources,
        "relationships": relationships if relationships is not None else [_relationship()],
        "ownership": [{"owner_id": "file:entry", "member_id": "entry", "basis": "indexed_file"}],
        "usage": {
            "edges_traversed": 3,
            "relationships_delivered": 1,
            "evidence_bytes": _fixture_evidence_bytes(selected_sources),
        },
    }
    return _finalize_output_bytes(payload)


def _read(source: dict | None = None) -> dict:
    selected_source = source if source is not None else _source(2, "export function entry() {}\n")
    payload = {
        "schema_version": 1,
        "status": "ok",
        "source": selected_source,
        "complete": True,
        "next_source_ref": None,
        "usage": {"evidence_bytes": selected_source["end_byte"] - selected_source["start_byte"]},
    }
    return _finalize_output_bytes(payload)


def _relationship(*, line: int = 11, source_ids: list[int] | None = None) -> dict:
    return {
        "id": 1,
        "edge": {
            "from": "entry",
            "to": "callee",
            "type": "calls",
            "directed": True,
            "namespace": "loci",
            "resolution": "exact",
            "evidence": {"file": "src/entry.ts", "line": line, "content_hash": HASH},
        },
        "traversed": "forward",
        "source_ids": source_ids if source_ids is not None else [1],
        "proof": "complete",
    }


def test_normal_adapter_counts_normal_public_calls_and_validates_real_shaped_proof(tmp_path: Path) -> None:
    retrieve = _retrieve()
    read = _read()
    body = [
        _mcp("retrieve-1", "loci_retrieve", retrieve),
        _mcp("read-1", "loci_read", read),
        *_outer("outer-1", retrieve, read),
    ]

    observed = observe_normal_rollout(_write(tmp_path, body), _metadata())
    retrieve_call, read_call = observed["normal_calls"]

    assert observed["normal_cost"] == {
        "public_invocations": 2,
        "normal_context_retrieval_invocations": 1,
        "exact_source_hydration_invocations": 1,
        "source_content_bytes": 54,
        "source_content_bytes_status": "complete",
        "semantic_relationship_count": 1,
        "semantic_relationship_count_status": "complete",
        "proof_validated_relationship_count": 1,
        "proof_validated_relationship_count_status": "complete",
        "actual_traversed_edge_count": 3,
        "actual_traversed_edge_count_status": "complete",
        "reported_delivered_relationship_count": 1,
        "reported_delivered_relationship_count_status": "complete",
        "ownership_association_count": 1,
        "ownership_association_count_status": "complete",
        "reported_evidence_bytes": 54,
        "actual_evidence_bytes": 54,
        "evidence_bytes_status": "complete",
        "reported_output_bytes": retrieve["usage"]["output_bytes"] + read["usage"]["output_bytes"],
        "actual_output_bytes": retrieve["usage"]["output_bytes"] + read["usage"]["output_bytes"],
        "output_bytes_status": "complete",
        "byte_accounting_status": "complete",
    }
    assert retrieve_call["relationships"] == {
        "status": "complete",
        "semantic_relationship_count": 1,
        "proof_validated_relationship_count": 1,
        "actual_traversed_edge_count": 3,
        "actual_traversed_edge_count_status": "complete",
        "delivered_relationship_count": 1,
        "delivered_relationship_count_status": "complete",
    }
    assert retrieve_call["ownership"] == {"status": "complete", "ownership_association_count": 1}
    assert retrieve_call["byte_accounting"]["status"] == "complete"
    assert retrieve_call["actual_host_proof_status"] == "validated"
    assert read_call["source"] == {"status": "complete", "source_record_count": 1, "source_content_bytes": 27}
    assert read_call["byte_accounting"]["status"] == "complete"
    registry = normal_evidence_registry(observed)
    assert registry["retrieve-1"]["semantic_relationship_count"] == 1
    assert len(registry["retrieve-1"]["model_output_refs"]) == 1


def test_normal_errors_are_known_source_free_and_do_not_become_unknown_zero(tmp_path: Path) -> None:
    error = {"error": {"code": "INVALID_SOURCE_REF", "message": "bad", "details": {}}}
    observed = observe_normal_rollout(
        _write(tmp_path, [_mcp("retrieve-error", "loci_retrieve", error, is_error=True)]), _metadata()
    )
    call = observed["normal_calls"][0]
    assert call["source"] == {"status": "known_source_free_error", "source_record_count": 0, "source_content_bytes": 0}
    assert call["relationships"]["semantic_relationship_count"] == 0
    assert call["relationships"]["actual_traversed_edge_count"] is None
    assert call["relationships"]["actual_traversed_edge_count_status"] == "unknown_after_error"
    assert call["relationships"]["delivered_relationship_count"] == 0
    assert observed["normal_cost"]["source_content_bytes"] == 0
    assert call["byte_accounting"]["actual_evidence_bytes"] == 0
    assert call["byte_accounting"]["reported_evidence_bytes"] is None
    assert call["byte_accounting"]["status"] == "unknown"
    assert observed["normal_cost"]["byte_accounting_status"] == "unknown"


@pytest.mark.parametrize(
    "broken",
    [
        _retrieve(relationships=[_relationship(line=99)]),
        _retrieve(relationships=[_relationship(source_ids=[99])]),
        _retrieve(sources=[{"id": 1, "content": "missing contract fields"}]),
    ],
)
def test_missing_or_corrupt_normal_source_proof_is_unknown_not_zero(tmp_path: Path, broken: dict) -> None:
    observed = observe_normal_rollout(
        _write(tmp_path, [_mcp("retrieve-corrupt", "loci_retrieve", broken), *_outer("outer-1", broken)]),
        _metadata(),
    )
    call = observed["normal_calls"][0]
    assert call["relationships"]["semantic_relationship_count"] is None
    assert call["relationships"]["proof_validated_relationship_count"] is None
    assert call["actual_host_proof_status"] == "unknown"


@pytest.mark.parametrize("corruption", ["source_extent", "unhashable_source_id", "containment", "missing_endpoint"])
def test_contract_corruption_cannot_qualify_as_a_semantic_normal_edge(
    tmp_path: Path, corruption: str
) -> None:
    broken = _retrieve()
    if corruption == "source_extent":
        broken["sources"][0]["end_byte"] += 1
    elif corruption == "unhashable_source_id":
        broken["relationships"][0]["source_ids"] = [{}]
    elif corruption == "containment":
        broken["relationships"][0]["edge"]["type"] = "contains"
    else:
        broken["nodes"] = [{"id": "entry"}]

    observed = observe_normal_rollout(
        _write(tmp_path, [_mcp("retrieve-corrupt-edge", "loci_retrieve", broken), *_outer("outer-1", broken)]),
        _metadata(),
    )
    call = observed["normal_calls"][0]
    assert call["relationships"]["semantic_relationship_count"] is None
    assert call["actual_host_proof_status"] == "unknown"


def test_empty_source_requires_zero_extent_and_missing_traversal_usage_cannot_validate_host_proof(
    tmp_path: Path,
) -> None:
    empty_source = _source(2, "")
    read = _read(empty_source)
    empty_observed = observe_normal_rollout(_write(tmp_path, [_mcp("empty-read", "loci_read", read)]), _metadata())
    assert empty_observed["normal_calls"][0]["source"]["status"] == "complete"

    missing_usage = _retrieve()
    missing_usage["usage"] = {"relationships_delivered": 1}
    observed = observe_normal_rollout(
        _write(tmp_path, [_mcp("uncounted", "loci_retrieve", missing_usage), *_outer("outer-1", missing_usage)]),
        _metadata(),
    )
    call = observed["normal_calls"][0]
    assert call["relationships"]["actual_traversed_edge_count"] is None
    assert call["relationships"]["actual_traversed_edge_count_status"] == "unknown_schema"
    assert call["actual_host_proof_status"] == "unknown"


def test_overlapping_source_spans_use_unique_extent_union_for_evidence_accounting(
    tmp_path: Path,
) -> None:
    sources = [
        _source(1, "0123456789", start=10, end=11),
        _source(2, "456789ab", start=10, end=11, start_byte=4),
    ]
    retrieve = _retrieve(sources=sources)
    assert sum(source["end_byte"] - source["start_byte"] for source in sources) == 18
    assert retrieve["usage"]["evidence_bytes"] == 12

    observed = observe_normal_rollout(
        _write(tmp_path, [_mcp("overlap", "loci_retrieve", retrieve), *_outer("outer", retrieve)]),
        _metadata(),
    )
    call = observed["normal_calls"][0]
    assert call["source"]["source_content_bytes"] == 12
    assert call["byte_accounting"] == {
        "reported_evidence_bytes": 12,
        "actual_evidence_bytes": 12,
        "evidence_bytes_status": "complete",
        "reported_output_bytes": retrieve["usage"]["output_bytes"],
        "actual_output_bytes": retrieve["usage"]["output_bytes"],
        "output_bytes_status": "complete",
        "status": "complete",
    }
    assert call["actual_host_proof_status"] == "validated"


def test_corrupt_declared_bytes_remain_mismatches_and_cannot_validate_host_proof(
    tmp_path: Path,
) -> None:
    retrieve = _retrieve()
    retrieve["usage"]["evidence_bytes"] = 0
    _finalize_output_bytes(retrieve)
    read = _read()
    read["usage"]["output_bytes"] += 1

    observed = observe_normal_rollout(
        _write(
            tmp_path,
            [
                _mcp("bad-evidence", "loci_retrieve", retrieve),
                _mcp("bad-output", "loci_read", read),
                *_outer("outer", retrieve, read),
            ],
        ),
        _metadata(),
    )
    retrieve_call, read_call = observed["normal_calls"]
    assert retrieve_call["byte_accounting"]["evidence_bytes_status"] == "mismatch"
    assert retrieve_call["byte_accounting"]["output_bytes_status"] == "complete"
    assert read_call["byte_accounting"]["evidence_bytes_status"] == "complete"
    assert read_call["byte_accounting"]["output_bytes_status"] == "mismatch"
    assert {retrieve_call["actual_host_proof_status"], read_call["actual_host_proof_status"]} == {"unknown"}
    assert observed["normal_cost"]["evidence_bytes_status"] == "mismatch"
    assert observed["normal_cost"]["output_bytes_status"] == "mismatch"
    assert observed["normal_cost"]["byte_accounting_status"] == "mismatch"
    assert all(
        not entry["model_output_refs"]
        for entry in normal_evidence_registry(observed).values()
    )


def test_inconsistent_traversal_and_reported_delivery_remain_mismatches_in_totals(
    tmp_path: Path,
) -> None:
    insufficient_traversal = _retrieve()
    insufficient_traversal["usage"] = {"edges_traversed": 0, "relationships_delivered": 1}
    traversal_observed = observe_normal_rollout(
        _write(
            tmp_path,
            [
                _mcp("traversal-mismatch", "loci_retrieve", insufficient_traversal),
                *_outer("outer-1", insufficient_traversal),
            ],
        ),
        _metadata(),
    )
    traversal_call = traversal_observed["normal_calls"][0]
    assert traversal_call["relationships"]["actual_traversed_edge_count"] == 0
    assert traversal_call["relationships"]["actual_traversed_edge_count_status"] == "mismatch"
    assert traversal_call["actual_host_proof_status"] == "unknown"
    assert traversal_observed["normal_cost"]["actual_traversed_edge_count"] == 0
    assert traversal_observed["normal_cost"]["actual_traversed_edge_count_status"] == "mismatch"

    delivered_mismatch = _retrieve()
    delivered_mismatch["usage"] = {"edges_traversed": 1, "relationships_delivered": 0}
    delivered_observed = observe_normal_rollout(
        _write(
            tmp_path,
            [
                _mcp("delivery-mismatch", "loci_retrieve", delivered_mismatch),
                *_outer("outer-1", delivered_mismatch),
            ],
        ),
        _metadata(),
    )
    assert delivered_observed["normal_cost"]["reported_delivered_relationship_count"] == 0
    assert delivered_observed["normal_cost"]["reported_delivered_relationship_count_status"] == "mismatch"
    assert delivered_observed["normal_calls"][0]["actual_host_proof_status"] == "unknown"


def test_unemitted_and_ambiguous_output_never_enters_answer_support_registry(tmp_path: Path) -> None:
    retrieve = _retrieve()
    unemitted = observe_normal_rollout(_write(tmp_path, [_mcp("unemitted", "loci_retrieve", retrieve)]), _metadata())
    assert unemitted["normal_calls"][0]["actual_host_proof_status"] == "not_model_delivered"
    assert normal_evidence_registry(unemitted)["unemitted"]["model_output_refs"] == []

    ambiguous = observe_normal_rollout(
        _write(
            tmp_path,
            [
                _mcp("same-1", "loci_retrieve", retrieve),
                _mcp("same-2", "loci_retrieve", retrieve),
                *_outer("outer-1", retrieve),
            ],
        ),
        _metadata(),
    )
    assert {call["actual_host_proof_status"] for call in ambiguous["normal_calls"]} == {"not_model_delivered"}
    assert all(not entry["model_output_refs"] for entry in normal_evidence_registry(ambiguous).values())
