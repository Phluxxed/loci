from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import pytest

from benchmarks.typescript_context_adapter import wire
from benchmarks.typescript_context_corpus import _isolated_store, load_corpus, materialize_snapshot
from benchmarks.typescript_context_explore_observed import (
    ExploreObservedTrace,
    measure,
    reconcile_observed,
    replay_trace,
)
from benchmarks.typescript_context_explore_tools import ExploreAdapter, normalize_arguments
from loci import service


CORPUS_ROOT = Path(__file__).parents[1] / "benchmarks" / "corpora" / "typescript-context-v3"


def _lifecycle(call: dict) -> list[dict]:
    started = {key: copy.deepcopy(call[key]) for key in ("id", "type", "server", "tool", "arguments")}
    return [
        {"type": "item.started", "item": started},
        {"type": "item.completed", "item": copy.deepcopy(call)},
    ]


def _explore_call(item_id: str, arguments: dict, payload: dict) -> dict:
    return {
        "id": item_id,
        "type": "mcp_tool_call",
        "server": "evaluation",
        "tool": "loci_explore",
        "arguments": copy.deepcopy(arguments),
        "status": "completed",
        "error": None,
        "result": {"content": [], "structured_content": copy.deepcopy(payload)},
    }


def _helper_call(item_id: str) -> dict:
    return {
        "id": item_id,
        "type": "mcp_tool_call",
        "server": "codex",
        "tool": "list_mcp_resources",
        "arguments": {"server": "codex"},
        "status": "completed",
        "error": None,
        "result": {
            "structured_content": None,
            "content": [{"type": "text", "text": '{"resources":[],"server":"codex"}'}],
        },
    }


def _events(calls: list[dict], answer: dict | None = None, usage: dict | None = None) -> list[dict]:
    result: list[dict[str, Any]] = [{"type": "thread.started", "thread_id": "explore-observed-thread"}]
    for call in calls:
        result.extend(_lifecycle(call))
    result.append(
        {
            "type": "item.completed",
            "item": {"id": "answer", "type": "agent_message", "text": json.dumps(answer or {})},
        }
    )
    if usage is not None:
        result.append({"type": "turn.completed", "usage": copy.deepcopy(usage)})
    return result


@pytest.fixture
def trace():
    return ExploreObservedTrace(load_corpus(CORPUS_ROOT), "imported_interface", "explore-observed", "B")


def test_explore_trace_records_and_replays_exact_operation(trace) -> None:
    raw = trace.files["consumer.ts"]
    first = raw[69:152].decode("utf-8")
    second = raw[0:69].decode("utf-8")
    payload = {
        "intent": "type_dependencies",
        "sources": [
            {
                "id": 1,
                "file": "consumer.ts",
                "start_byte": 69,
                "end_byte": 152,
                "content": first,
            },
            {
                "id": 2,
                "file": "consumer.ts",
                "start_byte": 0,
                "end_byte": 69,
                "content": second,
            },
        ],
        "_evaluation": {"attempt_id": "explore-observed/attempt/1"},
    }
    arguments = normalize_arguments("loci_explore", {"intent": "type_dependencies", "query": "processOrder"})
    response = wire(payload)
    event_id = trace.record(
        operation="explore",
        response_json=response,
        spans=[
            {"file": "consumer.ts", "start_byte": 69, "text": first},
            {"file": "consumer.ts", "start_byte": 0, "text": second},
        ],
        elapsed_ms=1.25,
        arguments=arguments,
    )
    assert trace.events[-1]["id"] == event_id
    assert trace.events[-1]["operation"] == "explore"
    assert trace.events[-1]["source_bytes"] == len(first.encode()) + len(second.encode())
    raw_trace = {
        "schema_version": 3,
        "protocol": "typescript-context-explore-v1",
        "identity": trace.identity,
        "events": trace.events,
        "failures": [],
        "attempts": 1,
        "deliveries": [
            {
                "attempt_id": "explore-observed/attempt/1",
                "operation": "explore",
                "arguments": arguments,
                "response_json": response,
                "serialized_bytes": len(response.encode("utf-8")),
                "source_bytes": trace.events[-1]["source_bytes"],
                "elapsed_ms": 2.0,
                "trace_event_id": event_id,
                "status": "recorded",
                "spans": copy.deepcopy(trace.events[-1]["spans"]),
            }
        ],
    }
    replayed = replay_trace(trace.corpus, raw_trace)
    assert replayed.events == trace.events


def test_reconcile_explore_and_resource_helper_counts_proof_bytes(trace) -> None:
    source = trace.files["consumer.ts"][69:152].decode("utf-8")
    payload = {
        "intent": "locate",
        "sources": [{"id": 1, "file": "consumer.ts", "start_byte": 69, "end_byte": 152, "content": source}],
        "_evaluation": {"attempt_id": "explore-observed/attempt/1"},
    }
    arguments = normalize_arguments("loci_explore", {"intent": "locate", "query": "processOrder"})
    response = wire(payload)
    event_id = trace.record(
        operation="explore",
        response_json=response,
        spans=[{"file": "consumer.ts", "start_byte": 69, "text": source}],
        elapsed_ms=1,
        arguments=arguments,
    )
    raw_trace = {
        "schema_version": 3,
        "protocol": "typescript-context-explore-v1",
        "identity": trace.identity,
        "events": trace.events,
        "failures": [],
        "attempts": 1,
        "deliveries": [
            {
                "attempt_id": "explore-observed/attempt/1",
                "operation": "explore",
                "arguments": arguments,
                "response_json": response,
                "serialized_bytes": len(response.encode("utf-8")),
                "source_bytes": trace.events[-1]["source_bytes"],
                "elapsed_ms": 2,
                "trace_event_id": event_id,
                "status": "recorded",
                "spans": copy.deepcopy(trace.events[-1]["spans"]),
            }
        ],
    }
    calls = [_explore_call("explore-call", arguments, payload), _helper_call("resource-call")]
    accounting = reconcile_observed(raw_trace, _events(calls))
    assert accounting["complete"] is True
    assert accounting["tool_call_count"] == 2
    assert accounting["source_bytes"] == len(source.encode("utf-8"))
    assert accounting["failures"] == []
    assert accounting["calls"][1]["source_bytes"] == 0
    assert accounting["validated_results"] == [payload]


def test_measure_uses_explore_scorer_and_observed_counts(tmp_path: Path) -> None:
    corpus = load_corpus(CORPUS_ROOT)
    repo = tmp_path / "snapshot"
    materialize_snapshot(corpus, "imported_interface", repo)
    run = {
        "repo": str(repo),
        "corpus_root": str(CORPUS_ROOT),
        "case_id": "imported_interface",
        "session_id": "explore-measure",
        "arm": "B",
        "repetition": 1,
        "trace_path": str(tmp_path / "trace.json"),
    }
    with _isolated_store(tmp_path / "cache"):
        service.index_repo(repo, incremental=False)
        index = service.get_store().load(repo.resolve())
        adapter = ExploreAdapter(run)
        result = adapter.read_operation("loci_explore", {"intent": "type_dependencies", "query": "processOrder"})
        payload = result.structured_content
        arguments = adapter.deliveries[0]["arguments"]
        call = _explore_call("measure-call", arguments, payload)
        events = _events(
            [call],
            answer=corpus["cases"][0]["answer"],
            usage={"input_tokens": 100, "cached_input_tokens": 20, "output_tokens": 10},
        )
        artifact = measure(corpus, next(c for c in corpus["cases"] if c["id"] == "imported_interface"), run, events, 1.0, 0, False, index)
    assert artifact["protocol"] == "typescript-context-explore-v1"
    assert artifact["measurement"]["measurement_complete"] is True
    assert artifact["measurement"]["read_count"] == 1
    assert artifact["baseline"]["relationships"]["schema_version"] == 2
    assert artifact["baseline"]["relationships"]["delivery_integrity_violations"] == []
