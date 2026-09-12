"""Focused accounting checks for the isolated multilingual trace."""
from __future__ import annotations

import copy
import json
from pathlib import Path

from benchmarks.multilingual_context_inputs import load_inputs
from benchmarks.multilingual_context_observed import (
    PROTOCOL,
    MultilingualObservedTrace,
    measure,
    replay_trace,
)
from benchmarks.multilingual_context_tools import normalize_arguments
from benchmarks.typescript_context_adapter import wire


def _raw(trace: MultilingualObservedTrace, deliveries: list[dict] | None = None) -> dict:
    deliveries = deliveries or []
    return {
        "schema_version": 3,
        "protocol": PROTOCOL,
        "identity": copy.deepcopy(trace.identity),
        "events": copy.deepcopy(trace.events),
        "failures": [],
        "attempts": len(deliveries),
        "deliveries": copy.deepcopy(deliveries),
    }


def _events(case: dict, calls: list[dict], turns: int = 1) -> list[dict]:
    events: list[dict] = [{"type": "thread.started", "thread_id": "thread"}]
    for call in calls:
        started = {key: copy.deepcopy(call[key]) for key in ("id", "type", "server", "tool", "arguments")}
        events.extend(({"type": "item.started", "item": started}, {"type": "item.completed", "item": call}))
    events.append({"type": "item.completed", "item": {
        "id": "answer", "type": "agent_message", "text": json.dumps(case["answer"]),
    }})
    events.extend({"type": "turn.completed", "usage": {
        "input_tokens": 100, "cached_input_tokens": 10, "output_tokens": 20,
    }} for _ in range(turns))
    return events


def test_explore_operation_replays_without_disguising_it_as_graph() -> None:
    corpus, _ = load_inputs()
    case = corpus["cases"][0]
    trace = MultilingualObservedTrace(corpus, case["id"], "explicit-explore", "B", 1)
    trace.record(
        operation="explore",
        response_json=wire({"intent": "locate", "sources": []}),
        spans=[],
        elapsed_ms=1.0,
        arguments=normalize_arguments("loci_explore", {"intent": "locate"}),
    )
    replayed = replay_trace(corpus, _raw(trace))
    assert replayed.events == trace.events
    assert replayed.events[0]["operation"] == "explore"


def test_operation_and_task_time_are_hard_failures_and_raw_usage_is_unambiguous(tmp_path: Path) -> None:
    corpus, _ = load_inputs()
    case = corpus["cases"][0]
    trace = MultilingualObservedTrace(corpus, case["id"], "budget", "B", 1)
    arguments = normalize_arguments("loci_explore", {"intent": "locate", "max_evidence_bytes": 0})
    attempt_id = "budget/attempt/1"
    payload = {
        "schema_version": 1,
        "intent": "locate",
        "selection": {},
        "scope": {},
        "limits": {"max_nodes": 64, "max_neighbors": 32},
        "usage": {"nodes_examined": 0, "evidence_bytes": 0, "output_bytes": 0},
        "items": [], "sources": [], "relationships": [], "omissions": [],
        "_evaluation": {"attempt_id": attempt_id},
    }
    response = wire(payload)
    event_id = trace.record(
        operation="explore", response_json=response, spans=[], elapsed_ms=10_001,
        arguments=arguments,
    )
    delivery = {
        "attempt_id": attempt_id, "operation": "explore", "arguments": arguments,
        "response_json": response, "serialized_bytes": len(response.encode()), "source_bytes": 0,
        "elapsed_ms": 10_001, "trace_event_id": event_id, "status": "recorded", "spans": [],
    }
    path = tmp_path / "trace.json"
    path.write_text(json.dumps(_raw(trace, [delivery])))
    call = {
        "id": "explore", "type": "mcp_tool_call", "server": "evaluation", "tool": "loci_explore",
        "arguments": arguments, "status": "completed", "error": None,
        "result": {"content": [], "structured_content": payload},
    }
    result = measure(corpus, case, {"trace_path": str(path)}, _events(case, [call]), 181.0, 0, True)
    failures = result["baseline"]["failures"]
    assert {item.get("limit") for item in failures if item["category"] == "budget_exhausted"} >= {
        "operation_time", "task_time",
    }
    assert result["measurement"]["outcome"] == "timeout"
    assert result["measurement"]["full_pass"] is False

    ambiguous = measure(corpus, case, {"trace_path": str(path)}, _events(case, [call], turns=2), 1.0, 0, False)
    assert ambiguous["measurement"]["measurement_complete"] is False
    assert any(item["category"] == "provider_usage_ambiguous" for item in ambiguous["baseline"]["failures"])
