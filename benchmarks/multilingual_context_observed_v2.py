"""Observed accounting for the corrected multilingual workflow protocol.

The v2 adapter keeps public graph tool names in its delivery ledger while the
underlying read trace records their shared internal ``graph`` operation.  This
module reconciles those two truthful views without changing the frozen v1
implementation or artifacts.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from benchmarks.multilingual_context_answers_v2 import check_answer
from benchmarks.multilingual_context_inputs import load_controls
from benchmarks.multilingual_context_relationships import score_relationships
from benchmarks.typescript_context_delivery import payload_texts
from benchmarks.typescript_context_explore_observed import ExploreObservedTrace
from benchmarks.typescript_context_observed import HELPERS, _source_free_helper, _terminal_calls


PROTOCOL = "multilingual-context-workflow-v2"


class MultilingualObservedTrace(ExploreObservedTrace):
    """An isolated v2 trace whose internal operation set includes explore."""


def replay_trace(corpus: dict[str, Any], raw: dict[str, Any]) -> MultilingualObservedTrace:
    """Replay an exact v2 trace against the frozen corpus snapshot."""

    if raw.get("schema_version") != 3 or raw.get("protocol") != PROTOCOL:
        raise ValueError("multilingual v2 observation trace required")
    identity = raw["identity"]
    trace = MultilingualObservedTrace(
        corpus,
        identity["task_id"],
        identity["session_id"],
        identity["arm"],
        identity["repetition"],
    )
    if trace.identity != identity:
        raise ValueError("trace corpus/control identity mismatch")
    events = raw.get("events")
    if not isinstance(events, list):
        raise ValueError("trace events must be a list")
    for event in events:
        if not isinstance(event, dict):
            raise ValueError("trace event must be an object")
        trace.record(
            **{key: event[key] for key in ("operation", "response_json", "elapsed_ms", "arguments")},
            spans=[
                {key: span[key] for key in ("file", "start_byte", "text")}
                for span in event["spans"]
            ],
        )
        if trace.events[-1] != event:
            raise ValueError("recorded source event does not replay exactly")
    return trace


def _trace_operation(tool: str) -> str:
    if tool.startswith("graph_"):
        return "graph"
    if tool == "loci_explore":
        return "explore"
    return tool


def _ledger_operation(tool: str) -> str:
    return "explore" if tool == "loci_explore" else tool


def _valid_latency(value: Any) -> bool:
    return type(value) in (int, float) and 0 <= value < float("inf")


def _span_bytes(spans: Any) -> int:
    """Validate ledger span shape, byte ranges, hashes, and return exact bytes."""

    if not isinstance(spans, list):
        raise ValueError("delivery spans must be a list")
    total = 0
    for span in spans:
        if not isinstance(span, dict):
            raise ValueError("delivery source span must be an object")
        file = span.get("file")
        start, end = span.get("start_byte"), span.get("end_byte")
        text, digest = span.get("text"), span.get("sha256")
        if not isinstance(file, str) or not file:
            raise ValueError("delivery source span has invalid file")
        if type(start) is not int or type(end) is not int or start < 0 or end < start:
            raise ValueError("delivery source span has invalid byte range")
        if not isinstance(text, str) or not text:
            raise ValueError("delivery source span has empty text")
        encoded = text.encode("utf-8")
        if end != start + len(encoded):
            raise ValueError("delivery source span byte range differs from text")
        if not isinstance(digest, str) or hashlib.sha256(encoded).hexdigest() != digest:
            raise ValueError("delivery source span hash differs from text")
        total += len(encoded)
    return total


def _trace_table(raw_trace: dict[str, Any], failures: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    raw_events = raw_trace.get("events")
    if not isinstance(raw_events, list):
        failures.append({"category": "invalid_trace_events"})
        return {}
    identity = raw_trace.get("identity")
    identity = identity if isinstance(identity, dict) else {}
    session = identity.get("session_id")
    result: dict[str, dict[str, Any]] = {}
    for position, event in enumerate(raw_events):
        if not isinstance(event, dict):
            failures.append({"category": "invalid_trace_event", "position": position})
            continue
        event_id = event.get("id")
        if not isinstance(event_id, str) or not event_id:
            failures.append({"category": "invalid_trace_event_id", "position": position})
            continue
        if event_id in result:
            failures.append({"category": "duplicate_trace_event_id", "trace_event_id": event_id})
            continue
        if not isinstance(session, str) or event_id != f"{session}:{position + 1}":
            failures.append({"category": "invalid_trace_event_sequence", "trace_event_id": event_id})
        if any(event.get(key) != identity.get(key) for key in ("task_id", "session_id", "arm", "repetition")):
            failures.append({"category": "trace_event_identity_mismatch", "trace_event_id": event_id})
        result[event_id] = event
    return result


def _delivery_ledger(
    raw_trace: dict[str, Any], failures: list[dict[str, Any]]
) -> dict[str, dict[str, Any]]:
    deliveries = raw_trace.get("deliveries")
    if not isinstance(deliveries, list):
        failures.append({"category": "invalid_delivery_ledger"})
        return {}
    identity = raw_trace.get("identity")
    session = identity.get("session_id") if isinstance(identity, dict) else None
    if not isinstance(session, str) or not session:
        failures.append({"category": "invalid_trace_identity"})
        expected_ids: list[str] = []
    else:
        expected_ids = [f"{session}/attempt/{number}" for number in range(1, len(deliveries) + 1)]
    actual_ids = [entry.get("attempt_id") if isinstance(entry, dict) else None for entry in deliveries]
    if actual_ids != expected_ids or type(raw_trace.get("attempts")) is not int or raw_trace.get("attempts") != len(deliveries):
        failures.append({"category": "invalid_attempt_sequence"})
    ledger: dict[str, dict[str, Any]] = {}
    for position, entry in enumerate(deliveries):
        if not isinstance(entry, dict):
            failures.append({"category": "invalid_delivery", "position": position})
            continue
        attempt_id = entry.get("attempt_id")
        if not isinstance(attempt_id, str) or not attempt_id:
            failures.append({"category": "invalid_attempt_id", "position": position})
            continue
        if attempt_id in ledger:
            failures.append({"category": "duplicate_attempt_id", "attempt_id": attempt_id})
            continue
        ledger[attempt_id] = entry
    return ledger


def reconcile_observed(raw_trace: dict[str, Any], events: list[dict[str, Any]]) -> dict[str, Any]:
    """Bind host calls to exact deliveries and internal source-trace events.

    Valid source-free rejections retain their known output and zero source cost,
    but they never enter ``validated_results`` and therefore cannot count as
    relationship or source proof.
    """

    from benchmarks.multilingual_context_tools_v2 import (
        TOOL_NAMES_A,
        TOOL_NAMES_B,
        normalize_arguments,
    )

    calls, failures = _terminal_calls(events)
    if not isinstance(raw_trace, dict):
        failures.append({"category": "invalid_observation_trace"})
        raw_trace = {}
    if raw_trace.get("schema_version") != 3 or raw_trace.get("protocol") != PROTOCOL:
        failures.append({"category": "invalid_observation_protocol"})
    ledger = _delivery_ledger(raw_trace, failures)
    trace_events = _trace_table(raw_trace, failures)
    arm = raw_trace.get("identity", {}).get("arm") if isinstance(raw_trace.get("identity"), dict) else None
    if arm == "A":
        tool_names = TOOL_NAMES_A
    elif arm == "B":
        tool_names = TOOL_NAMES_B
    else:
        tool_names = frozenset()
        failures.append({"category": "invalid_arm", "arm": arm})

    matched: set[str] = set()
    matched_events: set[str] = set()
    rows: list[dict[str, Any]] = []
    validated_results: list[dict[str, Any]] = []
    for item_id, call, started in calls:
        item = call if call is not None else started if started is not None else {}
        row = {
            "item_id": item.get("id", item_id),
            "server": item.get("server"),
            "tool": item.get("tool"),
            "arguments": item.get("arguments"),
            "status": item.get("status"),
            "attempt_id": None,
            "trace_event_id": None,
            "delivery_status": None,
            "source_bytes": None,
            "serialized_bytes": None,
            "elapsed_ms": None,
            "payload_texts": None,
            "payload_format": None,
            "native_usage": None,
        }
        rows.append(row)
        if call is None:
            continue
        try:
            payload_kind, texts = payload_texts(call)
        except ValueError as exc:
            failures.append({"category": "unaccounted_tool_output", "item": item_id, "message": str(exc)})
            continue
        row.update(
            payload_format=payload_kind,
            payload_texts=texts,
            serialized_bytes=sum(len(text.encode("utf-8")) for text in texts),
        )
        tool, server = call.get("tool"), call.get("server")
        result = (call.get("result") or {}).get("structured_content")
        if server == "evaluation" and tool in tool_names:
            evaluation = result.get("_evaluation") if isinstance(result, dict) else None
            evaluation = evaluation if isinstance(evaluation, dict) else {}
            attempt_id = evaluation.get("attempt_id")
            row["attempt_id"] = attempt_id
            entry = ledger.get(attempt_id) if isinstance(attempt_id, str) else None
            if entry is None:
                if (
                    call.get("status") == "failed"
                    and payload_kind in {"text_blocks", "host_error"}
                    and all(
                        text.startswith(f"Error executing tool {tool}:")
                        or text.startswith("Error calling tool")
                        for text in texts
                    )
                ):
                    row["source_bytes"] = 0
                    continue
                failures.append({"category": "unmatched_delivery", "item": item_id})
                continue
            if attempt_id in matched:
                failures.append({"category": "duplicate_delivery", "item": item_id})
                continue
            matched.add(attempt_id)
            row["delivery_status"] = entry.get("status")
            try:
                parameters = normalize_arguments(tool, call["arguments"])
                if entry["operation"] != _ledger_operation(tool) or entry["arguments"] != parameters:
                    raise ValueError("actual request differs from recorded request")
                if payload_kind != "compact_json" or texts != [entry["response_json"]]:
                    raise ValueError("actual output differs from recorded output")
                if row["serialized_bytes"] != entry["serialized_bytes"]:
                    raise ValueError("serialized byte count differs")
                if not _valid_latency(entry["elapsed_ms"]):
                    raise ValueError("invalid delivery latency")
                row["elapsed_ms"] = entry["elapsed_ms"]
                source_bytes = _span_bytes(entry["spans"])
                if source_bytes != entry["source_bytes"]:
                    raise ValueError("delivery source byte count differs")
                trace_id = entry["trace_event_id"]
                row["trace_event_id"] = trace_id
                if trace_id is None:
                    if (
                        entry["status"] != "rejected"
                        or entry["spans"]
                        or source_bytes
                        or evaluation.get("event_id") is not None
                        or not isinstance(result.get("error"), dict)
                        or not isinstance(result["error"].get("code"), str)
                    ):
                        raise ValueError("source-free delivery is not a truthful rejection")
                else:
                    trace_event = trace_events.get(trace_id) if isinstance(trace_id, str) else None
                    if trace_event is None or trace_id in matched_events or entry["status"] != "recorded":
                        raise ValueError("delivery has no unique recorded source event")
                    if not _valid_latency(trace_event.get("elapsed_ms")):
                        raise ValueError("invalid source event latency")
                    if (
                        evaluation.get("event_id") != trace_id
                        or trace_event.get("operation") != _trace_operation(tool)
                        or trace_event.get("arguments") != parameters
                        or any(
                            trace_event.get(key) != entry.get(key)
                            for key in ("response_json", "serialized_bytes", "source_bytes", "spans")
                        )
                        or entry["elapsed_ms"] < trace_event["elapsed_ms"]
                    ):
                        raise ValueError("delivery differs from validated source event")
                    matched_events.add(trace_id)
                    validated_results.append(result)
                row["source_bytes"] = source_bytes
                if tool == "loci_explore" and isinstance(result, dict):
                    native = result.get("usage", {})
                    native_limits = result.get("limits", {})
                    row["native_usage"] = {
                        "nodes_examined": native.get("nodes_examined") if isinstance(native, dict) else None,
                        "evidence_bytes": native.get("evidence_bytes") if isinstance(native, dict) else None,
                        "output_bytes": native.get("output_bytes") if isinstance(native, dict) else None,
                        "selected_items": len(result.get("items", [])) if isinstance(result.get("items"), list) else None,
                        "max_nodes": native_limits.get("max_nodes") if isinstance(native_limits, dict) else None,
                        "max_neighbors": native_limits.get("max_neighbors") if isinstance(native_limits, dict) else None,
                    }
            except (KeyError, TypeError, UnicodeError, ValueError) as exc:
                failures.append({"category": "delivery_trace_mismatch", "item": item_id, "message": str(exc)})
        elif tool in HELPERS and _source_free_helper(call, payload_kind, texts):
            row["source_bytes"] = 0
        else:
            failures.append(
                {
                    "category": "unaccounted_tool_output",
                    "item": item_id,
                    "message": "tool or source-bearing payload outside verified surface",
                }
            )
    if matched != set(ledger) or matched_events != set(trace_events):
        failures.append({"category": "unmatched_recorded_delivery"})
    complete = not failures and all(
        row["serialized_bytes"] is not None and row["source_bytes"] is not None for row in rows
    )
    subtotal = sum(row["serialized_bytes"] or 0 for row in rows)
    return {
        "schema_version": 4,
        "complete": complete,
        "tool_call_count": len(calls),
        "recorded_payload_bytes": subtotal,
        "complete_payload_bytes": subtotal if complete else None,
        "source_bytes": sum(row["source_bytes"] or 0 for row in rows) if complete else None,
        "calls": rows,
        "failures": failures,
        "validated_results": validated_results,
    }


def measure(
    corpus: dict[str, Any],
    case: dict[str, Any],
    run: dict[str, Any],
    events: list[dict[str, Any]],
    elapsed: float,
    exit_code: int,
    timed_out: bool,
    index: Any = None,
) -> dict[str, Any]:
    """Recompute answer, source, relation, usage, latency, and hard budgets."""

    raw = json.loads(Path(run["trace_path"]).read_text(encoding="utf-8"))
    trace = replay_trace(corpus, raw)
    accounting = reconcile_observed(raw, events)
    delivered = accounting.pop("validated_results")
    messages = [
        event["item"]["text"]
        for event in events
        if event.get("type") == "item.completed" and event.get("item", {}).get("type") == "agent_message"
    ]
    outcome = "timeout" if timed_out else "tool_failure" if exit_code else "completed"
    try:
        answer = json.loads(messages[-1])
        if not isinstance(answer, dict):
            raise ValueError("answer must be an object")
    except (ValueError, IndexError):
        answer = {}
        if outcome == "completed":
            outcome = "malformed_answer"
    turns = [event for event in events if event.get("type") == "turn.completed"]
    usage = turns[0].get("usage") if len(turns) == 1 else None
    limits = load_controls(corpus)["limits"]
    failures = list(raw.get("failures", [])) + accounting["failures"]
    if len(turns) != 1:
        failures.append({"category": "provider_usage_ambiguous", "turn_completed_events": len(turns)})
    checks = [
        ("all_tool_calls", accounting["tool_call_count"], limits["max_top_level_tool_calls_per_run"]),
        ("all_tool_output", accounting["recorded_payload_bytes"], limits["max_serialized_output_bytes_per_run"]),
    ]
    if usage is not None:
        checks.extend(
            [
                ("input_tokens", usage["input_tokens"], limits["max_reported_input_tokens_per_run"]),
                ("output_tokens", usage["output_tokens"], limits["max_reported_output_tokens_per_run"]),
            ]
        )
    if accounting["source_bytes"] is not None:
        checks.append(("all_source", accounting["source_bytes"], limits["max_source_bytes_per_run"]))
    for name, actual, maximum in checks:
        if actual > maximum:
            failures.append(
                {"category": "budget_exhausted", "limit": name, "actual": actual, "maximum": maximum}
            )
    for row in accounting["calls"]:
        if (row["serialized_bytes"] or 0) > limits["max_serialized_output_bytes_per_operation"]:
            failures.append({"category": "budget_exhausted", "limit": "host_tool_output", "item": row["item_id"]})
        if (row["elapsed_ms"] or 0) > limits["max_retrieval_seconds_per_operation"] * 1000:
            failures.append({"category": "budget_exhausted", "limit": "operation_time", "item": row["item_id"]})
        if row["tool"] == "loci_explore":
            native = row.get("native_usage") or {}
            for name, actual, maximum in (
                ("explore_output", row["serialized_bytes"] or 0, limits["explore_output_bytes"]),
                ("explore_source", row["source_bytes"] or 0, limits["explore_evidence_bytes"]),
                ("explore_nodes", native.get("nodes_examined"), limits["max_nodes"]),
                ("explore_items", native.get("selected_items"), limits["max_selected_items"]),
                ("explore_configured_nodes", native.get("max_nodes"), limits["max_nodes"]),
                ("explore_configured_neighbors", native.get("max_neighbors"), limits["max_neighbors_per_node"]),
            ):
                if actual is not None and actual > maximum:
                    failures.append(
                        {"category": "budget_exhausted", "limit": name, "item": row["item_id"], "actual": actual, "maximum": maximum}
                    )
    if timed_out or elapsed > limits["max_end_to_end_seconds_per_run"]:
        failures.append(
            {"category": "budget_exhausted", "limit": "task_time", "actual": elapsed,
             "maximum": limits["max_end_to_end_seconds_per_run"]}
        )
    if outcome == "completed" and any(failure["category"] == "budget_exhausted" for failure in failures):
        outcome = "budget_exhausted"
    if outcome == "completed" and not accounting["complete"]:
        outcome = "tool_failure"
    semantics = (
        "One Codex turn.completed event; gross input includes cached input subset; output includes reasoning tokens."
        if usage is not None
        else None
    )
    measurement = trace.report(answer, usage=usage, usage_semantics=semantics, outcome=outcome)
    measurement.update(
        read_count=accounting["tool_call_count"],
        serialized_tool_output_bytes=accounting["complete_payload_bytes"],
        source_bytes=accounting["source_bytes"],
        estimated_source_tokens=(accounting["source_bytes"] + 3) // 4 if accounting["source_bytes"] is not None else None,
    )
    measurement["measurement_complete"] = accounting["complete"] and usage is not None
    measurement["task_correct"] = bool(
        measurement["task_correct"]
        and check_answer(corpus, case["id"], answer)
        and measurement["measurement_complete"]
    )
    baseline = {
        "end_to_end_seconds": min(elapsed, limits["max_end_to_end_seconds_per_run"]) if timed_out else elapsed,
        "actual_process_seconds": elapsed,
        "exit_code": exit_code,
        "provider_thread_id": next(
            (event["thread_id"] for event in events if event.get("type") == "thread.started"), None
        ),
        "failures": failures,
        "tool_delivery_verified": accounting["complete"],
        "output_accounting": accounting,
        "adapter_elapsed_ms": sum(entry["elapsed_ms"] for entry in raw.get("deliveries", [])),
        "recoverable_error_events": sum(
            failure["category"] in {"tool_error", "invalid_trace"} for failure in raw.get("failures", [])
        ) + sum(row["status"] == "failed" for row in accounting["calls"]),
    }
    relationships = None
    if index is not None:
        spans = [span for event in trace.events for span in event["spans"]]
        relationships = score_relationships(case, index, delivered, spans)
        baseline["relationships"] = relationships
    relationship_complete = bool(
        relationships is not None
        and relationships["delivered_dependency_links_total"] == relationships["required_semantic_dependencies_total"]
        and relationships["forbidden_proven_relationships"] == 0
        and not relationships["delivery_integrity_violations"]
    )
    measurement["full_pass"] = bool(
        measurement["task_correct"]
        and measurement["context_recall"] == 1
        and relationship_complete
        and not any(failure["category"] == "budget_exhausted" for failure in failures)
    )
    return {
        "schema_version": 4,
        "protocol": PROTOCOL,
        "identity": trace.identity,
        "events": trace.events,
        "measurement": measurement,
        "baseline": baseline,
    }


__all__ = ["PROTOCOL", "MultilingualObservedTrace", "measure", "reconcile_observed", "replay_trace"]
