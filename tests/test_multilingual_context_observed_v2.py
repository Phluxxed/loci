"""Corrected multilingual v2 accounting and real transport acceptance."""
from __future__ import annotations

import asyncio
import copy
import json
import os
import sys
from pathlib import Path
from typing import Any

import pytest
from mcp import Client, StdioServerParameters
from mcp.client.stdio import stdio_client

from benchmarks import multilingual_context_observed_v2 as observed_v2
from benchmarks.multilingual_context_inputs import load_inputs
from benchmarks.multilingual_context_observed_v2 import (
    PROTOCOL,
    MultilingualObservedTrace,
    measure,
    reconcile_observed,
    replay_trace,
)
from benchmarks.multilingual_context_tools_v2 import normalize_arguments
from benchmarks.typescript_context_adapter import wire
from benchmarks.typescript_context_corpus import _isolated_store, materialize_snapshot
from loci import service


ROOT = Path(__file__).parents[1]
SYMBOL_ID = "app.js::run#function"
GRAPH_ARGUMENTS: dict[str, dict[str, Any]] = {
    "graph_anchors": {"question": "run dependencies", "seed_ids": [SYMBOL_ID]},
    "graph_neighbors": {"seed_ids": [SYMBOL_ID]},
    "graph_traverse_neighbors": {"seed_ids": [SYMBOL_ID]},
    "graph_paths": {"source_ids": [SYMBOL_ID], "target_ids": ["helper.js::make#function"]},
    "graph_retrieve": {"question": "run dependencies", "seed_ids": [SYMBOL_ID]},
    "graph_imports": {"file": "app.js"},
    "graph_references": {"file": "app.js"},
    "graph_calls": {"file": "app.js"},
}


def _raw(trace: MultilingualObservedTrace, deliveries: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "schema_version": 3,
        "protocol": PROTOCOL,
        "identity": copy.deepcopy(trace.identity),
        "events": copy.deepcopy(trace.events),
        "failures": [],
        "attempts": len(deliveries),
        "deliveries": copy.deepcopy(deliveries),
    }


def _events(calls: list[dict[str, Any]]) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for call in calls:
        started = {
            key: copy.deepcopy(call[key])
            for key in ("id", "type", "server", "tool", "arguments")
        }
        events.extend(
            (
                {"type": "item.started", "item": started},
                {"type": "item.completed", "item": copy.deepcopy(call)},
            )
        )
    return events


def _call(item_id: str, tool: str, arguments: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
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


def _graph_fixture(tool: str) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    corpus, _ = load_inputs()
    case = next(case for case in corpus["cases"] if case["id"] == "javascript_value_dependencies")
    session = f"unit-{tool}"
    trace = MultilingualObservedTrace(corpus, case["id"], session, "B", 1)
    arguments = normalize_arguments(tool, GRAPH_ARGUMENTS[tool])
    attempt_id = f"{session}/attempt/1"
    event_id = f"{session}:1"
    payload = {
        "operation": tool,
        "_evaluation": {"attempt_id": attempt_id, "event_id": event_id, "calls_remaining": 7},
    }
    response = wire(payload)
    recorded_id = trace.record(
        operation="graph",
        response_json=response,
        spans=[],
        elapsed_ms=1.0,
        arguments=arguments,
    )
    assert recorded_id == event_id
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
    return _raw(trace, [delivery]), payload, arguments


@pytest.mark.parametrize("tool", tuple(GRAPH_ARGUMENTS))
def test_every_graph_tool_uses_public_ledger_and_internal_trace_operation(tool: str) -> None:
    raw, payload, arguments = _graph_fixture(tool)

    accounting = reconcile_observed(raw, _events([_call("graph-call", tool, arguments, payload)]))

    assert accounting["complete"] is True
    assert accounting["failures"] == []
    assert raw["deliveries"][0]["operation"] == tool
    assert raw["events"][0]["operation"] == "graph"
    assert accounting["calls"][0]["trace_event_id"] == raw["events"][0]["id"]
    assert accounting["validated_results"] == [payload]


@pytest.mark.parametrize(
    "tamper",
    (
        "protocol",
        "schema",
        "ledger_operation",
        "trace_operation",
        "arguments",
        "output",
        "serialized_bytes",
        "span",
        "missing_attempt_id",
        "duplicate_attempt_id",
        "missing_trace_id",
        "evaluation_event_id",
        "evaluation_metadata",
        "duplicate_trace_id",
    ),
)
def test_integrity_tampering_cannot_receive_complete_accounting(tamper: str) -> None:
    raw, payload, arguments = _graph_fixture("graph_calls")
    raw = copy.deepcopy(raw)
    payload = copy.deepcopy(payload)
    if tamper == "protocol":
        raw["protocol"] = "multilingual-context-workflow-v1"
    elif tamper == "schema":
        raw["schema_version"] = 2
    elif tamper == "ledger_operation":
        raw["deliveries"][0]["operation"] = "graph"
    elif tamper == "trace_operation":
        raw["events"][0]["operation"] = "graph_calls"
    elif tamper == "arguments":
        raw["deliveries"][0]["arguments"]["file"] = "helper.js"
    elif tamper == "output":
        raw["deliveries"][0]["response_json"] = "{}"
    elif tamper == "serialized_bytes":
        raw["deliveries"][0]["serialized_bytes"] += 1
    elif tamper == "span":
        raw["deliveries"][0]["spans"] = [
            {"file": "app.js", "start_byte": 0, "end_byte": 1, "sha256": "bad", "text": "x"}
        ]
        raw["deliveries"][0]["source_bytes"] = 1
    elif tamper == "missing_attempt_id":
        raw["deliveries"][0]["attempt_id"] = None
    elif tamper == "duplicate_attempt_id":
        raw["deliveries"].append(copy.deepcopy(raw["deliveries"][0]))
        raw["attempts"] = 2
    elif tamper == "missing_trace_id":
        raw["deliveries"][0]["trace_event_id"] = "missing:1"
    elif tamper == "evaluation_event_id":
        payload["_evaluation"]["event_id"] = "other:1"
    elif tamper == "evaluation_metadata":
        payload["_evaluation"] = []
    elif tamper == "duplicate_trace_id":
        raw["events"].append(copy.deepcopy(raw["events"][0]))

    accounting = reconcile_observed(
        raw,
        _events([_call("graph-call", "graph_calls", arguments, payload)]),
    )

    assert accounting["complete"] is False
    assert accounting["complete_payload_bytes"] is None
    assert accounting["source_bytes"] is None
    assert accounting["failures"]


def test_truthful_rejection_is_costed_but_never_validated_as_source_proof() -> None:
    corpus, _ = load_inputs()
    case = next(case for case in corpus["cases"] if case["id"] == "javascript_value_dependencies")
    session = "truthful-rejection"
    trace = MultilingualObservedTrace(corpus, case["id"], session, "B", 1)
    arguments = normalize_arguments("graph_calls", {"file": "app.js"})
    attempt_id = f"{session}/attempt/1"
    payload = {
        "error": {"code": "BUDGET_EXHAUSTED", "message": "withheld"},
        "_evaluation": {"attempt_id": attempt_id, "calls_remaining": 0},
    }
    response = wire(payload)
    delivery = {
        "attempt_id": attempt_id,
        "operation": "graph_calls",
        "arguments": arguments,
        "response_json": response,
        "serialized_bytes": len(response.encode("utf-8")),
        "source_bytes": 0,
        "elapsed_ms": 1.0,
        "trace_event_id": None,
        "status": "rejected",
        "spans": [],
    }
    raw = _raw(trace, [delivery])

    accounting = reconcile_observed(
        raw,
        _events([_call("rejected", "graph_calls", arguments, payload)]),
    )

    assert accounting["complete"] is True
    assert accounting["source_bytes"] == 0
    assert accounting["recorded_payload_bytes"] == len(response.encode("utf-8"))
    assert accounting["validated_results"] == []

    donated = copy.deepcopy(payload)
    donated.pop("error")
    donated_response = wire(donated)
    raw["deliveries"][0]["response_json"] = donated_response
    raw["deliveries"][0]["serialized_bytes"] = len(donated_response.encode("utf-8"))
    invalid = reconcile_observed(
        raw,
        _events([_call("donated", "graph_calls", arguments, donated)]),
    )
    assert invalid["complete"] is False
    assert invalid["validated_results"] == []


def test_measure_exposes_v2_protocol_and_explicit_answer_contract(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    corpus, _ = load_inputs()
    case = next(case for case in corpus["cases"] if case["id"] == "javascript_value_dependencies")
    trace = MultilingualObservedTrace(corpus, case["id"], "measure-v2", "B", 1)
    trace_path = tmp_path / "trace.json"
    trace_path.write_text(json.dumps(_raw(trace, [])), encoding="utf-8")
    events = [
        {"type": "thread.started", "thread_id": "measure-thread"},
        {
            "type": "item.completed",
            "item": {"id": "answer", "type": "agent_message", "text": json.dumps(case["answer"])},
        },
        {
            "type": "turn.completed",
            "usage": {"input_tokens": 100, "cached_input_tokens": 20, "output_tokens": 10},
        },
    ]

    result = measure(
        corpus,
        case,
        {"trace_path": str(trace_path)},
        events,
        elapsed=1.0,
        exit_code=0,
        timed_out=False,
    )

    assert result["protocol"] == PROTOCOL
    assert result["measurement"]["measurement_complete"] is True
    assert result["measurement"]["task_correct"] is True
    assert result["measurement"]["full_pass"] is False

    monkeypatch.setattr(observed_v2, "check_answer", lambda *_args: False)
    gated = measure(
        corpus,
        case,
        {"trace_path": str(trace_path)},
        events,
        elapsed=1.0,
        exit_code=0,
        timed_out=False,
    )
    assert gated["measurement"]["task_correct"] is False
    assert gated["measurement"]["context_recall"] == result["measurement"]["context_recall"]
    assert gated["measurement"]["full_pass"] is False


def test_real_v2_stdio_graph_surface_reconciles_exact_transport_evidence(tmp_path: Path) -> None:
    """Exercise every graph route through the actual adapter subprocess."""

    corpus, _ = load_inputs()
    case = next(case for case in corpus["cases"] if case["id"] == "javascript_value_dependencies")
    repo = tmp_path / "snapshot"
    materialize_snapshot(corpus, case["snapshot"], repo)
    trace_path = tmp_path / "adapter-trace.json"
    run_path = tmp_path / "run.json"
    run = {
        "repo": str(repo),
        "corpus_root": corpus["_root"],
        "case_id": case["id"],
        "session_id": "real-v2-graph",
        "arm": "B",
        "repetition": 1,
        "trace_path": str(trace_path),
    }
    run_path.write_text(json.dumps(run), encoding="utf-8")
    cache = tmp_path / "cache"

    async def exercise() -> list[dict[str, Any]]:
        env = os.environ.copy()
        env["PYTHONPATH"] = os.pathsep.join((str(ROOT), str(ROOT / "src")))
        params = StdioServerParameters(
            command=sys.executable,
            args=["-m", "benchmarks.multilingual_context_tools_v2", str(run_path)],
            env=env,
            cwd=ROOT,
        )
        calls: list[dict[str, Any]] = []
        async with Client(stdio_client(params)) as session:
            advertised = {tool.name for tool in (await session.list_tools()).tools}
            assert set(GRAPH_ARGUMENTS) <= advertised
            for ordinal, (tool, arguments) in enumerate(GRAPH_ARGUMENTS.items(), 1):
                response = await session.call_tool(tool, arguments)
                assert not response.is_error
                assert isinstance(response.structured_content, dict)
                calls.append(_call(f"transport-{ordinal}", tool, arguments, response.structured_content))
        return calls

    with _isolated_store(cache):
        service.index_repo(repo, incremental=False)
        calls = asyncio.run(exercise())

    raw = json.loads(trace_path.read_text(encoding="utf-8"))
    accounting = reconcile_observed(raw, _events(calls))

    assert raw["protocol"] == PROTOCOL
    assert accounting["complete"] is True
    assert accounting["failures"] == []
    assert [entry["operation"] for entry in raw["deliveries"]] == list(GRAPH_ARGUMENTS)
    assert {event["operation"] for event in raw["events"]} == {"graph"}
    assert [row["arguments"] for row in accounting["calls"]] == list(GRAPH_ARGUMENTS.values())
    assert [row["serialized_bytes"] for row in accounting["calls"]] == [
        entry["serialized_bytes"] for entry in raw["deliveries"]
    ]
    assert [row["source_bytes"] for row in accounting["calls"]] == [
        entry["source_bytes"] for entry in raw["deliveries"]
    ]
    assert [row["trace_event_id"] for row in accounting["calls"]] == [
        event["id"] for event in raw["events"]
    ]
    assert [entry["spans"] for entry in raw["deliveries"]] == [
        event["spans"] for event in raw["events"]
    ]
    path_delivery = next(entry for entry in raw["deliveries"] if entry["operation"] == "graph_paths")
    path_payload = json.loads(path_delivery["response_json"])
    assert path_delivery["source_bytes"] > 0
    assert any(
        step["edge"]["type"] == "calls" and step["evidence_span"]["content"]
        for path in path_payload["paths"]
        for step in path["steps"]
    )
    wrong_operation = copy.deepcopy(raw)
    wrong_operation["deliveries"][0]["operation"] = "graph"
    wrong_bytes = copy.deepcopy(raw)
    wrong_bytes["deliveries"][1]["serialized_bytes"] += 1
    wrong_span = copy.deepcopy(raw)
    wrong_span_delivery = next(
        entry for entry in wrong_span["deliveries"] if entry["operation"] == "graph_paths"
    )
    wrong_span_delivery["spans"][0]["text"] += "x"
    duplicate_trace = copy.deepcopy(raw)
    duplicate_trace["events"].append(copy.deepcopy(duplicate_trace["events"][0]))
    for tampered in (wrong_operation, wrong_bytes, wrong_span, duplicate_trace):
        rejected = reconcile_observed(tampered, _events(calls))
        assert rejected["complete"] is False
        assert rejected["source_bytes"] is None
    assert replay_trace(corpus, raw).events == raw["events"]
