"""Observed measurement for the separately frozen explore comparison.

This module keeps the v3 envelope and accounting rules while using a trace
validator whose operation set includes the product ``loci_explore`` tool.  The
old observed module is intentionally left unchanged.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import cast

from benchmarks.typescript_context_corpus import check_answer, load_controls
from benchmarks.typescript_context_delivery import payload_texts
from benchmarks.typescript_context_observed import (
    HELPERS,
    _source_free_helper,
    _terminal_calls,
)
from benchmarks.typescript_context_trace import REASONS, ReadTrace, _covered, _strings


PROTOCOL = "typescript-context-explore-v1"
OPERATIONS = frozenset({"search", "get", "graph", "file", "grep", "outline", "explore"})


class ExploreReadTrace(ReadTrace):
    """ReadTrace with an isolated operation set that honestly records explore."""

    def record(
        self,
        *,
        operation,
        reason,
        detail,
        response_json,
        spans,
        elapsed_ms,
        arguments=None,
        because=None,
    ) -> str:
        # Keep the frozen validator's checks local to this version.  Mutating
        # the old module's global OPERATIONS would make concurrent A/B runs
        # race and would change the meaning of old replay artifacts.
        if operation not in OPERATIONS or reason not in REASONS or not detail.strip():
            raise ValueError("operation, reason and explanation are required")
        if (
            isinstance(elapsed_ms, bool)
            or not isinstance(elapsed_ms, (int, float))
            or not 0 <= elapsed_ms < float("inf")
        ):
            raise ValueError("invalid latency")
        previous = {event["id"]: event for event in self.events}
        if because is not None and because not in previous:
            raise ValueError("causal parent must be an earlier event in this run")
        payload = json.loads(
            response_json,
            parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)),
        )
        delivered_strings = list(_strings(payload))
        verified = []
        for span in spans:
            file, start, source = span["file"], span["start_byte"], span["text"]
            raw = source.encode("utf-8")
            if (
                file not in self.files
                or type(start) is not int
                or start < 0
                or not raw
                or self.files[file][start : start + len(raw)] != raw
                or not any(source in value for value in delivered_strings)
            ):
                raise ValueError("source span is not exact delivered snapshot content")
            verified.append(
                {
                    "file": file,
                    "start_byte": start,
                    "end_byte": start + len(raw),
                    "sha256": hashlib.sha256(raw).hexdigest(),
                    "text": source,
                }
            )
        arguments = json.loads(json.dumps(arguments or {}, allow_nan=False))
        selection = arguments.get("selected_from_search_id")
        if selection is not None:
            searches = [
                event
                for event in self.events
                if event["operation"] == "search" and event["search_id"] == selection
            ]
            if operation != "get" or not searches or not arguments.get("symbol_ids"):
                raise ValueError("selection must reference an earlier search in this run")
            if reason in {"hydration", "setup", "unrelated"}:
                raise ValueError("non-selection reads must omit search selection lineage")
        search_id = payload.get("search_id") if operation == "search" and isinstance(payload, dict) else None
        if search_id is not None and (
            not isinstance(search_id, str)
            or not search_id
            or any(event["search_id"] == search_id for event in self.events)
        ):
            raise ValueError("invalid or repeated search id")
        event_id = f"{self.identity['session_id']}:{len(self.events) + 1}"
        event = {
            "id": event_id,
            **self.identity,
            "operation": operation,
            "reason": reason,
            "detail": detail,
            "because": because,
            "arguments": arguments,
            "search_id": search_id,
            "response_json": response_json,
            "serialized_bytes": len(response_json.encode("utf-8")),
            "source_bytes": sum(item["end_byte"] - item["start_byte"] for item in verified),
            "elapsed_ms": elapsed_ms,
            "spans": verified,
        }
        self.events.append(event)
        return event_id


class ExploreObservedTrace(ExploreReadTrace):
    """Observed v3 trace with no agent-authored intent or causal fields."""

    def record(
        self,
        *,
        operation,
        response_json,
        spans,
        elapsed_ms,
        arguments=None,
        reason=None,
        detail=None,
        because=None,
    ):
        if because is not None:
            raise ValueError("v3 does not collect causal attribution")
        event_id = ExploreReadTrace.record(
            self,
            operation=operation,
            reason="task_context",
            detail="Observed tool request.",
            response_json=response_json,
            spans=spans,
            elapsed_ms=elapsed_ms,
            arguments=arguments,
            because=None,
        )
        for field in ("reason", "detail", "because"):
            self.events[-1].pop(field)
        return event_id

    def report(self, answer, *, usage=None, usage_semantics=None, outcome="completed"):
        # The v3 report has no operation-specific logic, so reusing its method
        # preserves the exact measurement keys and old numeric interpretation.
        from benchmarks.typescript_context_observed import ObservedTrace

        return ObservedTrace.report(
            cast(ObservedTrace, self),
            answer,
            usage=usage,
            usage_semantics=usage_semantics,
            outcome=outcome,
        )


def replay_trace(corpus, raw):
    """Replay all exact events, including an ``explore`` operation."""
    if raw.get("schema_version") != 3:
        raise ValueError("v3 observation trace required")
    if raw.get("protocol") not in {None, PROTOCOL}:
        raise ValueError("unsupported explore observation protocol")
    identity = raw["identity"]
    trace = ExploreObservedTrace(
        corpus,
        identity["task_id"],
        identity["session_id"],
        identity["arm"],
        identity["repetition"],
    )
    if trace.identity != identity:
        raise ValueError("trace corpus/control identity mismatch")
    for event in raw["events"]:
        trace.record(
            **{
                key: event[key]
                for key in ("operation", "response_json", "elapsed_ms", "arguments")
            },
            spans=[
                {key: span[key] for key in ("file", "start_byte", "text")}
                for span in event["spans"]
            ],
        )
        if trace.events[-1] != event:
            raise ValueError("recorded source event does not replay exactly")
    return trace


def reconcile_observed(raw_trace, events):
    """Bind host calls to exact deliveries for either A's or B's tool set."""
    from benchmarks.typescript_context_explore_tools import (
        TOOL_NAMES_A,
        TOOL_NAMES_B,
        normalize_arguments,
    )

    calls, failures = _terminal_calls(events)
    deliveries = raw_trace.get("deliveries", [])
    session = raw_trace["identity"]["session_id"]
    expected_ids = [f"{session}/attempt/{number}" for number in range(1, len(deliveries) + 1)]
    if [entry.get("attempt_id") for entry in deliveries] != expected_ids or raw_trace.get("attempts") != len(deliveries):
        failures.append({"category": "invalid_attempt_sequence"})
    ledger = {entry.get("attempt_id"): entry for entry in deliveries}
    trace_events = {entry["id"]: entry for entry in raw_trace["events"]}
    arm = raw_trace.get("identity", {}).get("arm")
    if arm == "A":
        tool_names = TOOL_NAMES_A
    elif arm == "B":
        tool_names = TOOL_NAMES_B
    else:
        tool_names = frozenset()
        failures.append({"category": "invalid_arm", "arm": arm})
    matched, matched_events, rows, validated_results = set(), set(), [], []
    for item_id, call, started in calls:
        if call is not None:
            item = call
        elif started is not None:
            item = started
        else:
            failures.append({"category": "incomplete_tool_lifecycle", "item": item_id})
            item = {}
        row = {
            "item_id": item.get("id", item_id),
            "server": item.get("server"),
            "tool": item.get("tool"),
            "arguments": item.get("arguments"),
            "status": item.get("status"),
            "attempt_id": None,
            "trace_event_id": None,
            "source_bytes": None,
            "serialized_bytes": None,
            "payload_texts": None,
            "payload_format": None,
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
            expected_operation = (
                "graph"
                if tool.startswith("graph_")
                else "explore"
                if tool == "loci_explore"
                else tool
            )
            attempt_id = result.get("_evaluation", {}).get("attempt_id") if isinstance(result, dict) else None
            row["attempt_id"] = attempt_id
            entry = ledger.get(attempt_id)
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
            try:
                parameters = normalize_arguments(tool, call["arguments"])
                if entry["operation"] != expected_operation or entry["arguments"] != parameters:
                    raise ValueError("actual request differs from recorded request")
                if payload_kind != "compact_json" or texts != [entry["response_json"]]:
                    raise ValueError("actual output differs from recorded output")
                if row["serialized_bytes"] != entry["serialized_bytes"]:
                    raise ValueError("serialized byte count differs")
                if (
                    type(entry["elapsed_ms"]) not in (int, float)
                    or not 0 <= entry["elapsed_ms"] < float("inf")
                ):
                    raise ValueError("invalid delivery latency")
                source_bytes = sum(
                    span["end_byte"] - span["start_byte"] for span in entry["spans"]
                )
                if source_bytes != entry["source_bytes"]:
                    raise ValueError("delivery source byte count differs")
                trace_id = entry["trace_event_id"]
                row["trace_event_id"] = trace_id
                if trace_id is None:
                    if entry["status"] != "rejected" or entry["spans"] or source_bytes:
                        raise ValueError("rejected attempt delivered source")
                else:
                    trace_event = trace_events.get(trace_id)
                    if trace_event is None or trace_id in matched_events or entry["status"] != "recorded":
                        raise ValueError("delivery has no unique recorded source event")
                    if (
                        trace_event["operation"] != expected_operation
                        or trace_event["arguments"] != parameters
                        or any(
                            trace_event[key] != entry[key]
                            for key in ("response_json", "serialized_bytes", "source_bytes", "spans")
                        )
                        or entry["elapsed_ms"] < trace_event["elapsed_ms"]
                    ):
                        raise ValueError("delivery differs from validated source event")
                    matched_events.add(trace_id)
                    validated_results.append(result)
                row["source_bytes"] = source_bytes
            except (KeyError, TypeError, ValueError) as exc:
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
        "schema_version": 3,
        "complete": complete,
        "tool_call_count": len(calls),
        "recorded_payload_bytes": subtotal,
        "complete_payload_bytes": subtotal if complete else None,
        "source_bytes": sum(row["source_bytes"] or 0 for row in rows) if complete else None,
        "calls": rows,
        "failures": failures,
        "validated_results": validated_results,
    }


def measure(corpus, case, run, events, elapsed, exit_code, timed_out, index=None):
    """Measure observed calls and use the versioned proof-aware scorer."""
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
    usage = turns[-1].get("usage") if turns else None
    limits = load_controls(corpus)["limits"]
    failures = list(raw.get("failures", [])) + accounting["failures"]
    checks = [
        ("all_tool_calls", accounting["tool_call_count"], limits["max_top_level_tool_calls_per_run"]),
        ("all_tool_output", accounting["recorded_payload_bytes"], limits["max_serialized_output_bytes_per_run"]),
    ]
    if usage:
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
            failures.append({"category": "budget_exhausted", "limit": name})
    for row in accounting["calls"]:
        if (row["serialized_bytes"] or 0) > limits["max_serialized_output_bytes_per_operation"]:
            failures.append({"category": "budget_exhausted", "limit": "host_tool_output", "item": row["item_id"]})
    if outcome == "completed" and any(failure["category"] == "budget_exhausted" for failure in failures):
        outcome = "budget_exhausted"
    if outcome == "completed" and not accounting["complete"]:
        outcome = "tool_failure"
    semantics = (
        "Codex turn.completed gross input; cached input is a subset; output includes reasoning tokens."
        if usage
        else None
    )
    measurement = trace.report(answer, usage=usage, usage_semantics=semantics, outcome=outcome)
    measurement.update(
        read_count=accounting["tool_call_count"],
        serialized_tool_output_bytes=accounting["complete_payload_bytes"],
        source_bytes=accounting["source_bytes"],
    )
    measurement["estimated_source_tokens"] = (
        (accounting["source_bytes"] + 3) // 4 if accounting["source_bytes"] is not None else None
    )
    measurement["measurement_complete"] = accounting["complete"] and usage is not None
    measurement["task_correct"] = measurement["task_correct"] and measurement["measurement_complete"]
    baseline = {
        "end_to_end_seconds": min(elapsed, limits["max_end_to_end_seconds_per_run"]) if timed_out else elapsed,
        "actual_process_seconds": elapsed,
        "exit_code": exit_code,
        "provider_thread_id": next(
            (event["thread_id"] for event in events if event.get("type") == "thread.started"),
            None,
        ),
        "failures": failures,
        "tool_delivery_verified": accounting["complete"],
        "output_accounting": accounting,
        "adapter_elapsed_ms": sum(entry["elapsed_ms"] for entry in raw.get("deliveries", [])),
        "recoverable_error_events": sum(
            failure["category"] in {"tool_error", "invalid_trace"} for failure in raw.get("failures", [])
        ) + sum(row["status"] == "failed" for row in accounting["calls"]),
    }
    if index is not None:
        from benchmarks.typescript_context_explore_relationships import score_relationships

        baseline["relationships"] = score_relationships(case, index, delivered)
    return {
        "schema_version": 3,
        "protocol": PROTOCOL,
        "identity": trace.identity,
        "events": trace.events,
        "measurement": measurement,
        "baseline": baseline,
    }


__all__ = [
    "ExploreObservedTrace",
    "ExploreReadTrace",
    "OPERATIONS",
    "PROTOCOL",
    "measure",
    "reconcile_observed",
    "replay_trace",
]
