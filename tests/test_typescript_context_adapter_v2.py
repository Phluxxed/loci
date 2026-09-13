from __future__ import annotations

import json
from pathlib import Path

import pytest

from benchmarks.typescript_context_adapter import Adapter, wire
from benchmarks.typescript_context_corpus import (
    _isolated_store,
    load_corpus,
    materialize_snapshot,
)
from loci.service import index_repo


CORPUS_ROOT = Path(__file__).parents[1] / "benchmarks" / "corpora" / "typescript-context-v2"


@pytest.fixture
def imported_v2_adapter(tmp_path: Path):
    corpus = load_corpus(CORPUS_ROOT)
    repo = tmp_path / "snapshot"
    materialize_snapshot(corpus, "imported_interface", repo)
    cache = tmp_path / "cache"
    trace_path = tmp_path / "trace.json"
    run = {
        "repo": str(repo),
        "corpus_root": str(CORPUS_ROOT),
        "case_id": "imported_interface",
        "session_id": "adapter-v2-imported-interface",
        "arm": "A",
        "repetition": 1,
        "trace_path": str(trace_path),
    }
    with _isolated_store(cache):
        index_repo(repo, incremental=False)
        yield Adapter(run), run, trace_path


def _assert_delivery_shape(entry: dict) -> None:
    assert set(entry) == {
        "attempt_id", "operation", "arguments", "reason", "detail", "because",
        "response_json", "serialized_bytes", "source_bytes", "elapsed_ms",
        "trace_event_id", "status", "spans",
    }
    assert entry["serialized_bytes"] == len(entry["response_json"].encode("utf-8"))
    assert json.loads(entry["response_json"])
    assert entry["elapsed_ms"] >= 0


def test_v2_records_exact_successful_delivery_and_persisted_ledger(imported_v2_adapter):
    adapter, _run, trace_path = imported_v2_adapter

    result = adapter.read(
        "search",
        {"query": "processOrder"},
        "task_context",
        "Locate the processOrder entry point.",
    )
    payload = result.structured_content
    assert isinstance(payload, dict)
    assert payload["_evaluation"] == {
        "attempt_id": "adapter-v2-imported-interface/attempt/1",
        "calls_remaining": 23,
        "event_id": "adapter-v2-imported-interface:1",
    }

    entry = adapter.deliveries[0]
    _assert_delivery_shape(entry)
    assert entry["attempt_id"] == payload["_evaluation"]["attempt_id"]
    assert entry["operation"] == "search"
    assert entry["arguments"] == {"query": "processOrder"}
    assert entry["reason"] == "task_context"
    assert entry["detail"] == "Locate the processOrder entry point."
    assert entry["because"] is None
    assert entry["response_json"] == wire(payload)
    assert entry["trace_event_id"] == payload["_evaluation"]["event_id"]
    assert entry["status"] == "recorded"
    assert entry["spans"] == adapter.trace.events[0]["spans"]
    assert len(entry["spans"]) == 1
    assert entry["spans"][0]["text"] == payload["symbols"][0]["signature"]
    assert entry["source_bytes"] == len(payload["symbols"][0]["signature"].encode())

    saved = json.loads(trace_path.read_text(encoding="utf-8"))
    assert saved["deliveries"] == adapter.deliveries
    assert saved["events"] == adapter.trace.events
    assert saved["failures"] == []


def test_v2_rejects_fake_because_before_source_delivery(imported_v2_adapter):
    adapter, _run, trace_path = imported_v2_adapter
    search = adapter.read(
        "search",
        {"query": "processOrder"},
        "task_context",
        "Find the function before testing causal validation.",
    )
    symbol_id = search.structured_content["symbols"][0]["id"]

    result = adapter.read(
        "get",
        {"symbol_ids": [symbol_id], "context": 0},
        "missing_context",
        "Hydrate the function with a deliberately foreign cause.",
        because="foreign-session:99",
    )
    payload = result.structured_content
    assert payload["error"]["code"] == "INVALID_TRACE"
    assert "symbols" not in payload
    assert payload["_evaluation"] == {
        "attempt_id": "adapter-v2-imported-interface/attempt/2",
        "calls_remaining": 22,
    }
    assert len(adapter.trace.events) == 1
    assert [event["id"] for event in adapter.trace.events] == [
        "adapter-v2-imported-interface:1"
    ]

    entry = adapter.deliveries[-1]
    _assert_delivery_shape(entry)
    assert entry["attempt_id"].endswith("/attempt/2")
    assert entry["operation"] == "get"
    assert entry["because"] == "foreign-session:99"
    assert entry["status"] == "rejected"
    assert entry["trace_event_id"] is None
    assert entry["spans"] == []
    assert entry["source_bytes"] == 0
    assert entry["response_json"] == wire(payload)
    assert adapter.failures[-1]["category"] == "invalid_trace"
    assert adapter.failures[-1]["attempt_id"].endswith("/attempt/2")
    assert json.loads(trace_path.read_text(encoding="utf-8"))["deliveries"] == adapter.deliveries


def test_v2_rejects_selection_hydration_then_keeps_event_ids_contiguous(imported_v2_adapter):
    adapter, _run, _trace_path = imported_v2_adapter
    search = adapter.read(
        "search",
        {"query": "processOrder"},
        "task_context",
        "Find the function before testing selection metadata.",
    )
    search_payload = search.structured_content
    search_event = adapter.trace.events[-1]
    symbol_id = search_payload["symbols"][0]["id"]

    rejected = adapter.read(
        "get",
        {
            "symbol_ids": [symbol_id],
            "selected_from_search_id": search_payload["search_id"],
            "context": 0,
        },
        "hydration",
        "Deliberately combine selection lineage with hydration.",
        because=search_event["id"],
    )
    rejected_payload = rejected.structured_content
    assert rejected_payload["error"]["code"] == "INVALID_TRACE"
    assert "symbols" not in rejected_payload
    assert "event_id" not in rejected_payload["_evaluation"]
    assert adapter.deliveries[-1]["status"] == "rejected"
    assert adapter.deliveries[-1]["trace_event_id"] is None

    accepted = adapter.read(
        "get",
        {"symbol_ids": [symbol_id], "context": 0},
        "hydration",
        "Hydrate the function without search selection metadata.",
    )
    accepted_payload = accepted.structured_content
    assert accepted_payload["_evaluation"]["attempt_id"].endswith("/attempt/3")
    assert accepted_payload["_evaluation"]["event_id"] == "adapter-v2-imported-interface:2"
    assert [event["id"] for event in adapter.trace.events] == [
        "adapter-v2-imported-interface:1",
        "adapter-v2-imported-interface:2",
    ]
    assert adapter.trace.events[-1]["because"] is None
    assert adapter.deliveries[-1]["attempt_id"].endswith("/attempt/3")
    assert adapter.deliveries[-1]["trace_event_id"] == "adapter-v2-imported-interface:2"
    assert adapter.deliveries[-1]["status"] == "recorded"
    assert adapter.deliveries[-1]["spans"] == adapter.trace.events[-1]["spans"]
    assert adapter.deliveries[-1]["source_bytes"] > 0


def test_v2_signature_spans_root_context_and_duplicate_get_source(imported_v2_adapter):
    adapter, _run, _trace_path = imported_v2_adapter

    entry_result = adapter.read(
        "search",
        {"query": "processOrder"},
        "task_context",
        "Locate the requested function and read its exact signature.",
    )
    entry_payload = entry_result.structured_content
    entry_event = adapter.trace.events[-1]
    entry_symbol = entry_payload["symbols"][0]
    assert len(entry_event["spans"]) == 1
    assert entry_event["spans"][0]["text"] == entry_symbol["signature"]
    assert entry_event["source_bytes"] == len(entry_symbol["signature"].encode())

    payload_result = adapter.read(
        "search",
        {"query": "Payload"},
        "missing_context",
        "Find the imported interface named by the function signature.",
        because=entry_event["id"],
    )
    payload_payload = payload_result.structured_content
    payload_event = adapter.trace.events[-1]
    payload_symbol = next(symbol for symbol in payload_payload["symbols"]
                          if symbol["kind"] == "interface")
    assert payload_event["because"] == entry_event["id"]
    assert any(span["text"] == payload_symbol["signature"] for span in payload_event["spans"])

    hydrated_result = adapter.read(
        "get",
        {
            "symbol_ids": [payload_symbol["id"]],
            "selected_from_search_id": payload_payload["search_id"],
            "context": 0,
        },
        "missing_context",
        "Read the complete interface after the search result omitted its members.",
        because=payload_event["id"],
    )
    hydrated_payload = hydrated_result.structured_content
    hydrated_event = adapter.trace.events[-1]
    item = hydrated_payload["symbols"][0]
    assert hydrated_event["because"] == payload_event["id"]
    assert hydrated_event["arguments"]["selected_from_search_id"] == payload_payload["search_id"]
    assert hydrated_event["spans"][0]["text"] == item["source"]
    assert any(span["text"] == item["signature"] for span in hydrated_event["spans"])
    assert hydrated_event["source_bytes"] == (
        len(item["source"].encode()) + len(item["signature"].encode())
    )

    measurement = adapter.trace.report(adapter.trace.case["answer"])
    assert measurement["task_correct"] is True
    assert measurement["lineage_status"] == "complete"
    assert measurement["avoidable_reads"] == 2
    assert measurement["required_context_delivered"] == ["payload"]

    malformed = {
        "symbols": [{"id": entry_symbol["id"], "signature": "function processOrder<Wrong>("}],
    }
    assert adapter.spans("search", malformed) == []


def test_v2_retains_call_cap_rejection_and_charges_all_delivery_rows(imported_v2_adapter):
    adapter, _run, trace_path = imported_v2_adapter

    for attempt in range(1, 25):
        result = adapter.read(
            "file",
            {"file_path": "../consumer.ts", "start_line": 1, "end_line": 1},
            "verification",
            f"Check the snapshot boundary on attempt {attempt}.",
        )
        assert result.structured_content["error"]["code"] == "ValueError"
        assert result.structured_content["_evaluation"]["event_id"] == (
            f"adapter-v2-imported-interface:{attempt}"
        )

    assert len(adapter.failures) == 24
    assert all(failure["category"] == "tool_error" for failure in adapter.failures)

    exhausted = adapter.read(
        "file",
        {"file_path": "consumer.ts", "start_line": 1, "end_line": 1},
        "verification",
        "Exercise the retained top-level call budget failure.",
    )
    payload = exhausted.structured_content
    assert payload["error"]["code"] == "BUDGET_EXHAUSTED"
    assert "event_id" not in payload["_evaluation"]
    assert payload["_evaluation"]["attempt_id"].endswith("/attempt/25")
    assert len(adapter.trace.events) == 24
    assert len(adapter.deliveries) == 25
    assert [event["id"] for event in adapter.trace.events] == [
        f"adapter-v2-imported-interface:{n}" for n in range(1, 25)
    ]

    rejected = adapter.deliveries[-1]
    _assert_delivery_shape(rejected)
    assert rejected["attempt_id"].endswith("/attempt/25")
    assert rejected["status"] == "rejected"
    assert rejected["trace_event_id"] is None
    assert rejected["spans"] == []
    assert rejected["source_bytes"] == 0
    assert rejected["response_json"] == wire(payload)
    assert adapter.failures[-1] == {
        "attempt_id": "adapter-v2-imported-interface/attempt/25",
        "category": "budget_exhausted",
        "limit": "tool_calls",
    }
    assert sum(row["serialized_bytes"] for row in adapter.deliveries) == sum(
        event["serialized_bytes"] for event in adapter.trace.events
    ) + rejected["serialized_bytes"]
    assert sum(row["source_bytes"] for row in adapter.deliveries) == sum(
        event["source_bytes"] for event in adapter.trace.events
    )
    saved = json.loads(trace_path.read_text(encoding="utf-8"))
    assert saved["attempts"] == 25
    assert saved["deliveries"] == adapter.deliveries
    assert saved["failures"] == adapter.failures
