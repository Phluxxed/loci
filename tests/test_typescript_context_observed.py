"""Protocol v3 measures observed retrieval calls and exact delivered source."""
from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from benchmarks.typescript_context_adapter import wire
from benchmarks.typescript_context_corpus import DEFAULT_ROOT, load_corpus
from benchmarks.typescript_context_observed import (
    ObservedTrace,
    measure,
    reconcile_observed,
    replay_trace,
)
from benchmarks.typescript_context_tools_v3 import normalize_arguments


V3_ROOT = DEFAULT_ROOT.with_name("typescript-context-v3")
UNKNOWN_SERVER_59B = "resources/read failed: unknown MCP server 'mcp__evaluation'"


@pytest.fixture
def corpus():
    return load_corpus(V3_ROOT)


@pytest.fixture
def trace(corpus):
    return ObservedTrace(corpus, "imported_interface", "observed-test")


def _gold(trace, gold_id):
    return next(item for item in trace.case["context"] if item["id"] == gold_id)


def _raw(trace, deliveries=None, failures=None):
    deliveries = deliveries or []
    return {
        "schema_version": 3,
        "identity": copy.deepcopy(trace.identity),
        "events": copy.deepcopy(trace.events),
        "failures": copy.deepcopy(failures or []),
        "attempts": len(deliveries),
        "deliveries": copy.deepcopy(deliveries),
    }


def _record_sources(trace, *, gold_ids, attempt_no, operation="file", arguments=None):
    if arguments is None:
        arguments = {"file_path": _gold(trace, gold_ids[0])["file"]}
    normalized = normalize_arguments(operation, arguments)
    attempt_id = f"{trace.identity['session_id']}/attempt/{attempt_no}"
    spans = []
    sources = []
    for gold_id in gold_ids:
        gold = _gold(trace, gold_id)
        source = trace.files[gold["file"]][gold["start_byte"] : gold["end_byte"]].decode()
        sources.append(source)
        spans.append({"file": gold["file"], "start_byte": gold["start_byte"], "text": source})
    result = {"sources": sources, "_evaluation": {"attempt_id": attempt_id}}
    response_json = wire(result)
    event_id = trace.record(
        operation=operation,
        response_json=response_json,
        spans=spans,
        elapsed_ms=1.5,
        arguments=normalized,
        reason="missing_context",
        detail="A legacy adapter label is accepted but never observed.",
    )
    event = trace.events[-1]
    assert event["id"] == event_id
    delivery = {
        "attempt_id": attempt_id,
        "operation": operation,
        "arguments": normalized,
        "response_json": response_json,
        "serialized_bytes": len(response_json.encode("utf-8")),
        "source_bytes": sum(span["end_byte"] - span["start_byte"] for span in event["spans"]),
        "elapsed_ms": 2.0,
        "trace_event_id": event_id,
        "status": "recorded",
        "spans": copy.deepcopy(event["spans"]),
    }
    return event, delivery


def _call(
    item_id,
    *,
    tool,
    arguments,
    server="evaluation",
    result=None,
    status="completed",
    error=None,
):
    return {
        "id": item_id,
        "type": "mcp_tool_call",
        "server": server,
        "tool": tool,
        "arguments": copy.deepcopy(arguments),
        "status": status,
        "error": copy.deepcopy(error),
        "result": copy.deepcopy(result),
    }


def _lifecycle(call, *, terminal_type="item.completed"):
    started = {
        key: copy.deepcopy(call[key])
        for key in ("id", "type", "server", "tool", "arguments")
    }
    return [
        {"type": "item.started", "item": started},
        {"type": terminal_type, "item": copy.deepcopy(call)},
    ]


def _structured_call(item_id, *, tool, arguments, structured, server="evaluation"):
    return _call(
        item_id,
        tool=tool,
        arguments=arguments,
        server=server,
        result={"content": [], "structured_content": structured},
    )


def _empty_resources_call(item_id, *, tool="list_mcp_resources", server="codex"):
    key = "resources" if tool == "list_mcp_resources" else "resourceTemplates"
    text = json.dumps({key: [], "server": server}, separators=(",", ":"))
    return _call(
        item_id,
        tool=tool,
        arguments={"server": server},
        server=server,
        result={"structured_content": None, "content": [{"type": "text", "text": text}]},
    )


def _host_error_call(item_id, *, tool, arguments, message, server="evaluation"):
    return _call(
        item_id,
        tool=tool,
        arguments=arguments,
        server=server,
        status="failed",
        result=None,
        error={"message": message},
    )


def _answer_events(case, calls, *, usage=None, thread_id="observed-thread"):
    events = [{"type": "thread.started", "thread_id": thread_id}]
    for call in calls:
        events.extend(_lifecycle(call))
    events.append(
        {
            "type": "item.completed",
            "item": {"id": "answer", "type": "agent_message", "text": json.dumps(case["answer"])},
        }
    )
    if usage is not None:
        events.append({"type": "turn.completed", "usage": copy.deepcopy(usage)})
    return events


def _write_trace(tmp_path, raw):
    path = tmp_path / "observed-trace.json"
    path.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")
    return path


def test_observed_trace_has_exact_source_events_without_intent_or_causal_fields(trace):
    _record_sources(trace, gold_ids=["entry"], attempt_no=1)

    event = trace.events[0]
    assert {"reason", "detail", "because"}.isdisjoint(event)
    assert trace.report(trace.case["answer"])["schema_version"] == 3
    measurement = trace.report(
        trace.case["answer"],
        usage={"input_tokens": 100, "cached_input_tokens": 20, "output_tokens": 10},
        usage_semantics="gross input includes cached input; output includes reasoning",
    )
    assert measurement["measurement_method"] == "observed_tool_calls"
    assert measurement["intent_collection"] == "not_collected"
    assert measurement["answer_correct"] is True
    assert measurement["task_correct"] is True
    assert measurement["read_count"] == measurement["validated_read_count"] == 1
    assert not {
        "avoidable_reads",
        "proven_avoidable_reads",
        "classifications",
        "lineage_status",
    } & measurement.keys()

    with pytest.raises(ValueError, match="causal attribution"):
        trace.record(
            operation="file",
            response_json="{}",
            spans=[],
            elapsed_ms=1,
            because="observed-test:1",
        )


def test_observed_trace_retains_search_selection_validation_without_recording_intent(trace):
    search_result = {"search_id": "search-one", "symbols": []}
    trace.record(
        operation="search",
        response_json=wire(search_result),
        spans=[],
        elapsed_ms=1,
        arguments=normalize_arguments("search", {"query": "processOrder"}),
        reason="task_context",
        detail="Search labels remain adapter-only.",
    )
    assert trace.events[0]["search_id"] == "search-one"
    assert {"reason", "detail", "because"}.isdisjoint(trace.events[0])

    _record_sources(
        trace,
        gold_ids=["payload"],
        attempt_no=1,
        operation="get",
        arguments={
            "symbol_ids": ["types.ts::Contract#interface"],
            "selected_from_search_id": "search-one",
        },
    )
    assert trace.events[1]["arguments"]["selected_from_search_id"] == "search-one"

    before = len(trace.events)
    with pytest.raises(ValueError, match="selection"):
        trace.record(
            operation="get",
            response_json=wire({"source": "unused"}),
            spans=[],
            elapsed_ms=1,
            arguments=normalize_arguments(
                "get",
                {"symbol_ids": ["missing"], "selected_from_search_id": "unknown-search"},
            ),
        )
    assert len(trace.events) == before


def test_reconcile_counts_repeated_source_and_source_free_helper_calls(trace):
    _, first_delivery = _record_sources(trace, gold_ids=["entry"], attempt_no=1)
    _, second_delivery = _record_sources(trace, gold_ids=["entry"], attempt_no=2)
    raw = _raw(trace, [first_delivery, second_delivery])
    empty = _empty_resources_call("helper-empty")
    unknown = _host_error_call(
        "helper-unknown",
        tool="read_mcp_resource",
        arguments={"server": "mcp__evaluation", "uri": "? no"},
        message=UNKNOWN_SERVER_59B,
        server="mcp__evaluation",
    )
    events = _lifecycle(_structured_call(
        "read-1",
        tool="file",
        arguments={"file_path": "consumer.ts"},
        structured=json.loads(first_delivery["response_json"]),
    ))
    events += _lifecycle(_structured_call(
        "read-2",
        tool="file",
        arguments={"file_path": "consumer.ts"},
        structured=json.loads(second_delivery["response_json"]),
    ))
    events += _lifecycle(empty)
    events += _lifecycle(unknown)

    accounting = reconcile_observed(raw, events)
    assert accounting["complete"] is True
    assert accounting["tool_call_count"] == 4
    assert accounting["source_bytes"] == 2 * first_delivery["source_bytes"]
    assert accounting["recorded_payload_bytes"] == sum(
        row["serialized_bytes"] for row in accounting["calls"]
    )
    assert [row["source_bytes"] for row in accounting["calls"]] == [
        first_delivery["source_bytes"],
        second_delivery["source_bytes"],
        0,
        0,
    ]
    assert accounting["failures"] == []


def test_reconcile_counts_error_and_unfinished_started_calls_once_but_is_incomplete(trace):
    _, delivery = _record_sources(trace, gold_ids=["entry"], attempt_no=1)
    raw = _raw(trace, [delivery])
    source_call = _structured_call(
        "read-1",
        tool="file",
        arguments={"file_path": "consumer.ts"},
        structured=json.loads(delivery["response_json"]),
    )
    recoverable_error = _host_error_call(
        "input-error",
        tool="search",
        arguments={},
        message="Error executing tool search: search requires query",
    )
    unfinished = {
        "id": "unfinished",
        "type": "mcp_tool_call",
        "server": "evaluation",
        "tool": "get",
        "arguments": {"symbol_ids": ["types.ts::Contract#interface"]},
    }
    events = _lifecycle(source_call) + _lifecycle(recoverable_error) + [
        {"type": "item.started", "item": unfinished}
    ]

    accounting = reconcile_observed(raw, events)
    assert accounting["tool_call_count"] == 3
    assert [row["item_id"] for row in accounting["calls"]] == [
        "read-1",
        "input-error",
        "unfinished",
    ]
    assert accounting["complete"] is False
    assert any(f["category"] == "incomplete_tool_lifecycle" for f in accounting["failures"])
    assert any(row["item_id"] == "input-error" and row["source_bytes"] == 0
               for row in accounting["calls"])


@pytest.mark.parametrize("mutation", ["duplicate", "unexpected", "payload", "unmatched"])
def test_reconcile_rejects_duplicate_ids_unexpected_tools_payloads_and_unmatched_ledger(
    trace, mutation
):
    _, delivery = _record_sources(trace, gold_ids=["entry"], attempt_no=1)
    raw = _raw(trace, [delivery])
    valid = _structured_call(
        "read-1",
        tool="file",
        arguments={"file_path": "consumer.ts"},
        structured=json.loads(delivery["response_json"]),
    )
    events = _lifecycle(valid)

    if mutation == "duplicate":
        events.append({"type": "item.completed", "item": copy.deepcopy(valid)})
    elif mutation == "unexpected":
        events = _lifecycle(
            _structured_call(
                "ambient",
                tool="read",
                arguments={"operation": "file"},
                structured={"source": "unverified"},
                server="ambient",
            )
        )
        raw["events"] = []
        raw["deliveries"] = []
        raw["attempts"] = 0
    elif mutation == "payload":
        bad = _call(
            "bad-payload",
            tool="file",
            arguments={"file_path": "consumer.ts"},
            result={"structured_content": None, "content": [{"type": "image", "data": "x"}]},
        )
        events = _lifecycle(bad)
        raw["events"] = []
        raw["deliveries"] = []
        raw["attempts"] = 0
    else:
        events = []

    accounting = reconcile_observed(raw, events)
    assert accounting["complete"] is False
    assert accounting["complete_payload_bytes"] is None
    assert accounting["failures"]


@pytest.mark.parametrize("mutation", ["wrong_file", "response", "bytes", "identity"])
def test_replay_trace_rejects_wrong_file_and_tampered_source_artifacts(trace, mutation):
    _record_sources(trace, gold_ids=["entry"], attempt_no=1)
    raw = _raw(trace)
    if mutation == "wrong_file":
        raw["events"][0]["spans"][0]["file"] = "types.ts"
    elif mutation == "response":
        raw["events"][0]["response_json"] = "{}"
    elif mutation == "bytes":
        raw["events"][0]["serialized_bytes"] = 0
    else:
        raw["identity"]["corpus_sha256"] = "tampered"

    with pytest.raises(ValueError):
        replay_trace(trace.corpus, raw)


def test_measure_uses_all_observed_calls_as_primary_count_and_keeps_schema3_baseline(
    trace, tmp_path
):
    deliveries = []
    for attempt_no, gold_id in enumerate(("entry", "payload", "import"), start=1):
        _, delivery = _record_sources(trace, gold_ids=[gold_id], attempt_no=attempt_no)
        deliveries.append(delivery)
    raw = _raw(trace, deliveries)
    path = _write_trace(tmp_path, raw)
    calls = []
    for number, delivery in enumerate(deliveries, start=1):
        calls += _lifecycle(
            _structured_call(
                f"read-{number}",
                tool="file",
                arguments={"file_path": "consumer.ts" if number != 2 else "types.ts"},
                structured=json.loads(delivery["response_json"]),
            )
        )
    calls += _lifecycle(_empty_resources_call("helper-empty"))
    calls += _lifecycle(
        _host_error_call(
            "helper-unknown",
            tool="read_mcp_resource",
            arguments={"server": "mcp__evaluation", "uri": "? no"},
            message=UNKNOWN_SERVER_59B,
            server="mcp__evaluation",
        )
    )
    usage = {"input_tokens": 1000, "cached_input_tokens": 200, "output_tokens": 30}
    result = measure(
        trace.corpus,
        trace.case,
        {"trace_path": str(path)},
        [
            {"type": "thread.started", "thread_id": "observed-thread"},
            *calls,
            {"type": "item.completed", "item": {"id": "answer", "type": "agent_message",
                                                   "text": json.dumps(trace.case["answer"])}},
            {"type": "turn.completed", "usage": usage},
        ],
        3.0,
        0,
        False,
    )
    measurement = result["measurement"]
    assert result["schema_version"] == 3
    assert measurement["measurement_method"] == "observed_tool_calls"
    assert measurement["read_count"] == 5
    assert measurement["validated_read_count"] == 3
    assert measurement["answer_correct"] is True
    assert measurement["task_correct"] is True
    assert measurement["context_recall"] == 1
    assert measurement["measurement_complete"] is True
    assert not {"avoidable_reads", "proven_avoidable_reads", "classifications"} & measurement.keys()
    assert result["baseline"]["output_accounting"]["complete"] is True
    assert result["baseline"]["output_accounting"]["tool_call_count"] == 5
    assert result["baseline"]["tool_delivery_verified"] is True
    assert result["baseline"]["failures"] == []


def test_measure_allows_correct_answer_after_recoverable_bounded_input_error(trace, tmp_path):
    _, delivery = _record_sources(trace, gold_ids=["entry"], attempt_no=1)
    raw = _raw(trace, [delivery])
    path = _write_trace(tmp_path, raw)
    source_call = _structured_call(
        "read-1",
        tool="file",
        arguments={"file_path": "consumer.ts"},
        structured=json.loads(delivery["response_json"]),
    )
    input_error = _host_error_call(
        "input-error",
        tool="search",
        arguments={},
        message="Error executing tool search: search requires query",
    )
    usage = {"input_tokens": 100, "cached_input_tokens": 20, "output_tokens": 10}
    result = measure(
        trace.corpus,
        trace.case,
        {"trace_path": str(path)},
        _answer_events(trace.case, [source_call, input_error], usage=usage),
        1.0,
        0,
        False,
    )
    assert result["measurement"]["read_count"] == 2
    assert result["measurement"]["task_correct"] is True
    assert result["measurement"]["outcome"] == "completed"
    assert result["baseline"]["output_accounting"]["complete"] is True
    assert result["baseline"]["output_accounting"]["complete_payload_bytes"] is not None
    assert result["baseline"]["recoverable_error_events"] == 1


def test_measure_hard_budget_failure_cannot_pass_correct_answer(trace, tmp_path):
    raw = _raw(trace)
    path = _write_trace(tmp_path, raw)
    calls = [_empty_resources_call(f"helper-{number}") for number in range(25)]
    usage = {"input_tokens": 100, "cached_input_tokens": 20, "output_tokens": 10}
    result = measure(
        trace.corpus,
        trace.case,
        {"trace_path": str(path)},
        _answer_events(trace.case, calls, usage=usage),
        1.0,
        0,
        False,
    )
    assert result["measurement"]["read_count"] == 25
    assert result["measurement"]["outcome"] == "budget_exhausted"
    assert result["measurement"]["task_correct"] is False
    assert result["baseline"]["output_accounting"]["complete"] is True
    assert result["baseline"]["output_accounting"]["complete_payload_bytes"] == (
        25 * len('{"resources":[],"server":"codex"}'.encode("utf-8"))
    )


@pytest.mark.parametrize(
    ("elapsed", "exit_code", "timed_out", "usage", "expected_outcome"),
    [
        (181.0, 0, True, {"input_tokens": 100, "cached_input_tokens": 20, "output_tokens": 10}, "timeout"),
        (1.0, 1, False, {"input_tokens": 100, "cached_input_tokens": 20, "output_tokens": 10}, "tool_failure"),
        (1.0, 0, False, {"input_tokens": 200001, "cached_input_tokens": 20, "output_tokens": 10}, "budget_exhausted"),
    ],
)
def test_measure_time_process_and_token_failures_cannot_pass(
    trace, tmp_path, elapsed, exit_code, timed_out, usage, expected_outcome
):
    _, delivery = _record_sources(trace, gold_ids=["entry"], attempt_no=1)
    path = _write_trace(tmp_path, _raw(trace, [delivery]))
    source_call = _structured_call(
        "read-1",
        tool="file",
        arguments={"file_path": "consumer.ts"},
        structured=json.loads(delivery["response_json"]),
    )
    result = measure(
        trace.corpus,
        trace.case,
        {"trace_path": str(path)},
        _answer_events(trace.case, [source_call], usage=usage),
        elapsed,
        exit_code,
        timed_out,
    )
    assert result["measurement"]["answer_correct"] is True
    assert result["measurement"]["outcome"] == expected_outcome
    assert result["measurement"]["task_correct"] is False
