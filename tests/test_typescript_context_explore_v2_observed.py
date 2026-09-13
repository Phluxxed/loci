from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import pytest

from benchmarks.typescript_context_adapter import wire
from benchmarks.typescript_context_corpus import _isolated_store, load_corpus, materialize_snapshot
from benchmarks.typescript_context_explore_observed import replay_trace as replay_v1
from benchmarks.typescript_context_explore_tools import ExploreAdapter, normalize_arguments
from benchmarks.typescript_context_explore_v2_observed import (
    PROTOCOL,
    RAW_PROTOCOL,
    ExploreObservedTrace,
    measure,
    reconcile_observed,
    replay_trace,
)
from loci import service


CORPUS_ROOT = Path(__file__).parents[1] / "benchmarks" / "corpora" / "typescript-context-v3"
SYMBOL_ID = "consumer.ts::processOrder#function"
GRAPH_ARGUMENTS: dict[str, dict[str, Any]] = {
    "graph_anchors": {"question": "processOrder"},
    "graph_neighbors": {"seed_ids": [SYMBOL_ID]},
    "graph_traverse_neighbors": {"seed_ids": [SYMBOL_ID]},
    "graph_paths": {"source_ids": [SYMBOL_ID], "target_ids": [SYMBOL_ID]},
    "graph_retrieve": {"question": "processOrder"},
    "graph_imports": {"file": "consumer.ts"},
    "graph_references": {"file": "consumer.ts"},
    "graph_calls": {"file": "consumer.ts"},
}


def _lifecycle(call: dict[str, Any]) -> list[dict[str, Any]]:
    started = {
        key: copy.deepcopy(call[key])
        for key in ("id", "type", "server", "tool", "arguments")
    }
    return [
        {"type": "item.started", "item": started},
        {"type": "item.completed", "item": copy.deepcopy(call)},
    ]


def _events(calls: list[dict[str, Any]]) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = [{"type": "thread.started", "thread_id": "v2-observed-thread"}]
    for call in calls:
        events.extend(_lifecycle(call))
    events.append(
        {
            "type": "item.completed",
            "item": {"id": "answer", "type": "agent_message", "text": "{}"},
        }
    )
    return events


def _structured_call(item_id: str, tool: str, arguments: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": item_id,
        "type": "mcp_tool_call",
        "server": "evaluation",
        "tool": tool,
        "arguments": copy.deepcopy(arguments),
        "status": "completed",
        "error": None,
        "result": {"content": [], "structured_content": copy.deepcopy(payload)},
    }


def _helper_call(item_id: str) -> dict[str, Any]:
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


def _graph_fixture(tool: str) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    corpus = load_corpus(CORPUS_ROOT)
    trace = ExploreObservedTrace(corpus, "imported_interface", "v2-graph", "B", 1)
    arguments = normalize_arguments(tool, GRAPH_ARGUMENTS[tool])
    attempt_id = "v2-graph/attempt/1"
    payload = {"operation": tool, "_evaluation": {"attempt_id": attempt_id}}
    response = wire(payload)
    event_id = trace.record(
        operation="graph",
        response_json=response,
        spans=[],
        elapsed_ms=1.0,
        arguments=arguments,
    )
    delivery = {
        "attempt_id": attempt_id,
        "operation": tool,
        "arguments": copy.deepcopy(arguments),
        "response_json": response,
        "serialized_bytes": len(response.encode("utf-8")),
        "source_bytes": 0,
        "elapsed_ms": 2.0,
        "trace_event_id": event_id,
        "status": "recorded",
        "spans": [],
    }
    raw = {
        "schema_version": 3,
        "protocol": RAW_PROTOCOL,
        "identity": trace.identity,
        "events": copy.deepcopy(trace.events),
        "failures": [],
        "attempts": 1,
        "deliveries": [delivery],
    }
    return raw, payload, arguments


@pytest.mark.parametrize("tool", tuple(GRAPH_ARGUMENTS))
def test_graph_operation_map_keeps_public_ledger_and_internal_trace(tool: str) -> None:
    raw, payload, arguments = _graph_fixture(tool)
    accounting = reconcile_observed(raw, _events([_structured_call("graph-call", tool, arguments, payload)]))

    assert accounting["complete"] is True
    assert accounting["failures"] == []
    assert accounting["calls"][0]["tool"] == tool
    assert raw["deliveries"][0]["operation"] == tool
    assert raw["events"][0]["operation"] == "graph"


def test_graph_ledger_tampering_is_rejected_without_changing_raw_trace() -> None:
    raw, payload, arguments = _graph_fixture("graph_anchors")
    tampered = copy.deepcopy(raw)
    tampered["deliveries"][0]["operation"] = "graph"
    accounting = reconcile_observed(
        tampered,
        _events([_structured_call("graph-call", "graph_anchors", arguments, payload)]),
    )

    assert accounting["complete"] is False
    assert any(failure["category"] == "delivery_trace_mismatch" for failure in accounting["failures"])
    assert raw["deliveries"][0]["operation"] == "graph_anchors"


def test_v2_replay_delegates_to_v1_raw_trace_protocol() -> None:
    raw, _, _ = _graph_fixture("graph_neighbors")
    replayed = replay_trace(load_corpus(CORPUS_ROOT), raw)

    assert replay_trace is replay_v1
    assert replayed.events == raw["events"]
    assert raw["protocol"] == RAW_PROTOCOL


def test_real_adapter_mixed_get_explore_helper_reconciles_and_measures(tmp_path: Path) -> None:
    corpus = load_corpus(CORPUS_ROOT)
    case = next(case for case in corpus["cases"] if case["id"] == "imported_interface")
    repo = tmp_path / "snapshot"
    materialize_snapshot(corpus, "imported_interface", repo)
    trace_path = tmp_path / "trace.json"
    run = {
        "repo": str(repo),
        "corpus_root": str(CORPUS_ROOT),
        "case_id": case["id"],
        "session_id": "v2-real-adapter",
        "arm": "B",
        "repetition": 1,
        "trace_path": str(trace_path),
    }

    with _isolated_store(tmp_path / "store"):
        service.index_repo(repo, incremental=False)
        index = service.get_store().load(repo.resolve())
        adapter = ExploreAdapter(run)
        get_result = adapter.read_operation("get", {"symbol_ids": [SYMBOL_ID]})
        explore_result = adapter.read_operation(
            "loci_explore",
            {"intent": "locate", "query": "processOrder"},
        )
        deliveries = copy.deepcopy(adapter.deliveries)
        calls = [
            _structured_call(
                "get-call",
                "get",
                deliveries[0]["arguments"],
                get_result.structured_content,
            ),
            _structured_call(
                "explore-call",
                "loci_explore",
                deliveries[1]["arguments"],
                explore_result.structured_content,
            ),
            _helper_call("helper-call"),
        ]
        events = _events(calls)
        raw = json.loads(trace_path.read_text(encoding="utf-8"))
        accounting = reconcile_observed(raw, events)
        assert accounting["complete"] is True
        assert accounting["failures"] == []
        assert [row["tool"] for row in accounting["calls"]] == [
            "get",
            "loci_explore",
            "list_mcp_resources",
        ]
        assert accounting["calls"][2]["source_bytes"] == 0

        events[-1] = {
            "type": "turn.completed",
            "usage": {"input_tokens": 100, "cached_input_tokens": 20, "output_tokens": 10},
        }
        events.append(
            {
                "type": "item.completed",
                "item": {"id": "answer", "type": "agent_message", "text": json.dumps(case["answer"])},
            }
        )
        artifact = measure(corpus, case, run, events, 1.0, 0, False, index)

    assert artifact["protocol"] == PROTOCOL
    assert artifact["schema_version"] == 3
    assert artifact["measurement"]["measurement_complete"] is True
    assert artifact["measurement"]["read_count"] == 3
    assert artifact["baseline"]["relationships"]["schema_version"] == 2
