"""Observed routing exposure for the versioned TypeScript comparison.

The retained adapter trace remains on the ``typescript-context-explore-v1``
protocol.  This module keeps the corrected v2 accounting and adds a small,
evaluator-owned observation of the first repository route.  It never puts the
case answer or source context into a provider request.
"""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from typing import Any

from benchmarks.typescript_context_corpus import load_controls
from benchmarks.typescript_context_delivery import payload_texts
from benchmarks.typescript_context_observed import (
    HELPERS,
    _source_free_helper,
    _terminal_calls,
)
from benchmarks.typescript_context_explore_tools import TOOL_NAMES_B
from benchmarks.typescript_context_routing_v2_tools import normalize_arguments
from benchmarks.typescript_context_explore_v2_observed import (
    ExploreObservedTrace,
    ExploreReadTrace,
)
from benchmarks.typescript_context_explore_observed import replay_trace
from benchmarks.typescript_context_routing import CALL_TARGET_CASES


VERSION = "typescript-context-routing-v2"
PROTOCOL = VERSION
RAW_PROTOCOL = "typescript-context-explore-v1"


def _trace_operation(tool: str) -> str:
    """Return the operation name emitted by the frozen adapter trace."""

    if tool.startswith("graph_"):
        return "graph"
    if tool == "loci_explore":
        return "explore"
    return tool


def _ledger_operation(tool: str) -> str:
    """Return the public operation name retained in an adapter delivery."""

    return "explore" if tool == "loci_explore" else tool


def _known_native_error(
    tool: Any,
    status: Any,
    payload_kind: Any,
    texts: Any,
) -> bool:
    """Recognize only non-empty host validation errors outside the ledger."""

    if status != "failed" or payload_kind not in {"text_blocks", "host_error"}:
        return False
    if not isinstance(texts, list) or not texts:
        return False
    executing_prefix = f"Error executing tool {tool}:"
    calling_prefix = "Error calling tool"
    for text in texts:
        if not isinstance(text, str) or not text.strip():
            return False
        if text.startswith(executing_prefix):
            if not text[len(executing_prefix) :].strip():
                return False
        elif text.startswith(calling_prefix):
            if not text[len(calling_prefix) :].strip(" :\t\r\n"):
                return False
        else:
            return False
    return True


def reconcile_observed(raw_trace: dict[str, Any], events: list[dict[str, Any]]) -> dict[str, Any]:
    """Bind host calls to exact v1 deliveries with the corrected v2 accounting.

    The routing condition exposes the same B tool surface on both A and B
    identities.  The raw trace still records the original A/B identity, so the
    reconciler deliberately uses ``TOOL_NAMES_B`` for either valid arm.
    """

    calls, failures = _terminal_calls(events)
    deliveries = raw_trace.get("deliveries", [])
    session = raw_trace["identity"]["session_id"]
    expected_ids = [f"{session}/attempt/{number}" for number in range(1, len(deliveries) + 1)]
    if (
        [entry.get("attempt_id") for entry in deliveries] != expected_ids
        or raw_trace.get("attempts") != len(deliveries)
    ):
        failures.append({"category": "invalid_attempt_sequence"})
    ledger = {entry.get("attempt_id"): entry for entry in deliveries}
    trace_events = {entry["id"]: entry for entry in raw_trace["events"]}
    arm = raw_trace.get("identity", {}).get("arm")
    if arm not in {"A", "B"}:
        tool_names = frozenset()
        failures.append({"category": "invalid_arm", "arm": arm})
    else:
        # Both routing arms receive the same thirteen original tools plus the
        # explore tool.  Keeping this branch here, instead of changing the
        # frozen v2 module, preserves old replay semantics and A/B identity.
        tool_names = TOOL_NAMES_B

    matched: set[Any] = set()
    matched_events: set[Any] = set()
    rows: list[dict[str, Any]] = []
    validated_results: list[Any] = []
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
            trace_operation = _trace_operation(tool)
            ledger_operation = _ledger_operation(tool)
            evaluation = result.get("_evaluation") if isinstance(result, dict) else None
            attempt_id = evaluation.get("attempt_id") if isinstance(evaluation, dict) else None
            row["attempt_id"] = attempt_id
            entry = ledger.get(attempt_id)
            if entry is None:
                if _known_native_error(tool, call.get("status"), payload_kind, texts):
                    row["source_bytes"] = 0
                    continue
                failures.append({"category": "unmatched_delivery", "item": item_id})
                continue
            if attempt_id in matched:
                failures.append({"category": "duplicate_delivery", "item": item_id})
                continue
            matched.add(attempt_id)
            try:
                if call.get("status") != "completed":
                    raise ValueError("recorded delivery has failed host status")
                parameters = normalize_arguments(tool, call["arguments"])
                if entry["operation"] != ledger_operation or entry["arguments"] != parameters:
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
                        trace_event["operation"] != trace_operation
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


def _terminal_host_calls(
    events: Any,
) -> tuple[list[tuple[str, dict[str, Any], dict[str, Any] | None]], list[dict[str, Any]]]:
    """Return terminal tool calls in host order and lifecycle diagnostics."""

    if not isinstance(events, list):
        return [], [{"category": "invalid_host_events"}]

    started: dict[str, tuple[int, dict[str, Any]]] = {}
    terminal: dict[str, tuple[int, dict[str, Any]]] = {}
    order: list[str] = []
    failures: list[dict[str, Any]] = []
    for position, event in enumerate(events):
        if not isinstance(event, dict):
            failures.append({"category": "invalid_host_event", "position": position})
            continue
        item = event.get("item")
        if not isinstance(item, dict) or item.get("type") != "mcp_tool_call":
            continue
        item_id = item.get("id")
        if not isinstance(item_id, str) or not item_id:
            failures.append({"category": "invalid_tool_identity", "position": position})
            continue
        event_type = event.get("type")
        if event_type == "item.started":
            if item_id in started:
                failures.append({"category": "duplicate_tool_event", "item": item_id, "event_type": event_type})
            else:
                started[item_id] = (position, item)
        elif event_type in {"item.completed", "item.failed"}:
            if item_id in terminal:
                failures.append({"category": "duplicate_tool_event", "item": item_id, "event_type": event_type})
            else:
                terminal[item_id] = (position, item)
                order.append(item_id)
            if item_id not in started:
                failures.append({"category": "orphan_terminal_tool_event", "item": item_id})
        else:
            failures.append({"category": "invalid_tool_event", "item": item_id, "event_type": event_type})

    for item_id, (position, item) in terminal.items():
        start = started.get(item_id)
        if start is None:
            continue
        if start[0] >= position:
            failures.append({"category": "terminal_before_start", "item": item_id})
        if any(start[1].get(key) != item.get(key) for key in ("server", "tool", "arguments")):
            failures.append({"category": "changed_tool_request", "item": item_id})
        if not isinstance(item.get("server"), str) or not item.get("server"):
            failures.append({"category": "invalid_tool_request", "item": item_id, "field": "server"})
        if not isinstance(item.get("tool"), str) or not item.get("tool"):
            failures.append({"category": "invalid_tool_request", "item": item_id, "field": "tool"})
        if not isinstance(item.get("arguments"), dict):
            failures.append({"category": "invalid_tool_request", "item": item_id, "field": "arguments"})
        if _event_type_for(events, position) == "item.failed":
            valid_status = item.get("status") == "failed"
        else:
            valid_status = item.get("status") in {"completed", "failed"}
        if not valid_status:
            failures.append({"category": "invalid_tool_status", "item": item_id})

    for item_id in started:
        if item_id not in terminal:
            failures.append({"category": "incomplete_tool_lifecycle", "item": item_id})

    calls = [(item_id, terminal[item_id][1], started.get(item_id, (0, None))[1]) for item_id in order]
    return calls, failures


def _event_type_for(events: list[Any], position: int) -> Any:
    event = events[position]
    return event.get("type") if isinstance(event, dict) else None


def _expected_anchor(case: Any) -> tuple[dict[str, Any] | None, str | None, list[dict[str, Any]]]:
    failures: list[dict[str, Any]] = []
    if not isinstance(case, dict):
        return None, None, [{"category": "invalid_case"}]
    context = case.get("context")
    if not isinstance(context, list):
        return None, None, [{"category": "invalid_anchor_context"}]
    matches = [entry for entry in context if isinstance(entry, dict) and entry.get("id") == case.get("anchor")]
    if len(matches) != 1:
        failures.append({"category": "invalid_anchor_context"})
        return None, None, failures
    anchor = matches[0]
    symbol = anchor.get("symbol")
    file = anchor.get("file")
    if (
        not isinstance(symbol, dict)
        or not isinstance(symbol.get("name"), str)
        or not isinstance(symbol.get("kind"), str)
        or not isinstance(file, str)
    ):
        failures.append({"category": "invalid_anchor_context"})
        return None, None, failures
    native_id = f"{file}::{symbol['name']}#{symbol['kind']}"
    return anchor, native_id, failures


def _native_payload(call: dict[str, Any]) -> tuple[dict[str, Any] | None, bool]:
    result = call.get("result")
    if not isinstance(result, dict):
        return None, False
    payload = result.get("structured_content")
    if not isinstance(payload, dict):
        return None, False
    body = {key: value for key, value in payload.items() if key != "_evaluation"}
    try:
        # Validate against the product contract, while excluding the evaluator
        # attempt metadata that the adapter appends to every response.
        from loci.mcp_output_models import LociExploreSuccess

        LociExploreSuccess.model_validate(body)
    except Exception:
        return body, False
    return body, True


def _source_for_anchor(
    payload: dict[str, Any] | None,
    anchor: dict[str, Any] | None,
    native_id: str | None,
    files: dict[str, bytes],
) -> tuple[bool, bool, list[Any]]:
    """Return requested/complete flags after validating one native response."""

    if payload is None or anchor is None or native_id is None:
        return False, False, []
    items = payload.get("items")
    sources = payload.get("sources")
    if not isinstance(items, list) or not isinstance(sources, list):
        return False, False, []
    anchor_items = [
        item
        for item in items
        if isinstance(item, dict)
        and item.get("id") == native_id
        and item.get("role") == "anchor"
        and item.get("name") == anchor.get("symbol", {}).get("name")
        and item.get("kind") == anchor.get("symbol", {}).get("kind")
        and item.get("file") == anchor.get("file")
    ]
    if len(anchor_items) != 1:
        return False, False, []
    item = anchor_items[0]
    source_id = item.get("source_id")
    if type(source_id) is not int:
        return False, False, []
    matching = [source for source in sources if isinstance(source, dict) and source.get("id") == source_id]
    all_ids = [source.get("id") for source in sources if isinstance(source, dict)]
    if len(matching) != 1 or len(all_ids) != len(set(all_ids)):
        return False, False, []
    source = matching[0]
    file = anchor.get("file")
    if not isinstance(file, str) or file not in files:
        return False, False, []
    content = source.get("content")
    start = source.get("start_byte")
    end = source.get("end_byte")
    if not isinstance(content, str) or not content or type(start) is not int or type(end) is not int:
        return False, False, []
    try:
        encoded = content.encode("utf-8")
    except UnicodeEncodeError:
        return False, False, []
    expected_start = anchor.get("start_byte")
    expected_end = anchor.get("end_byte")
    if (
        type(expected_start) is not int
        or type(expected_end) is not int
        or source.get("file") != file
        or start != expected_start
        or end <= start
        or end > expected_end
        or end - start != len(encoded)
        or files[file][start:end] != encoded
        or source.get("content_hash") != hashlib.sha256(files[file]).hexdigest()
    ):
        return False, False, []
    complete = end == expected_end and item.get("complete") is True
    return True, complete, [item.get("id")]


def _has_matching_anchor_trace_span(
    trace: ExploreObservedTrace | None,
    trace_event_id: Any,
    anchor: dict[str, Any] | None,
) -> bool:
    """Require this call's replayed source proof to begin at the requested anchor."""

    if trace is None or not isinstance(trace_event_id, str) or anchor is None:
        return False
    file = anchor.get("file")
    expected_start = anchor.get("start_byte")
    expected_end = anchor.get("end_byte")
    if (
        not isinstance(file, str)
        or type(expected_start) is not int
        or type(expected_end) is not int
        or expected_start < 0
        or expected_end <= expected_start
    ):
        return False
    event = next((event for event in trace.events if event.get("id") == trace_event_id), None)
    if not isinstance(event, dict) or not isinstance(event.get("spans"), list):
        return False
    for span in event["spans"]:
        if not isinstance(span, dict):
            continue
        start = span.get("start_byte")
        end = span.get("end_byte")
        text = span.get("text")
        if (
            span.get("file") == file
            and type(start) is int
            and type(end) is int
            and start == expected_start
            and start < end <= expected_end
            and isinstance(text, str)
            and bool(text)
        ):
            return True
    return False


def observe_routing(
    corpus: dict[str, Any],
    case: dict[str, Any],
    raw_trace: dict[str, Any],
    events: list[dict[str, Any]],
) -> dict[str, Any]:
    """Observe first-route exposure and exact native anchor delivery."""

    expected_route = "call_target" if case.get("id") in CALL_TARGET_CASES else "type_dependencies"
    terminal_calls, lifecycle_failures = _terminal_host_calls(events)
    failures: list[dict[str, Any]] = list(lifecycle_failures)
    routing_integrity_failures: list[dict[str, Any]] = []

    trace = None
    trace_ok = False
    try:
        trace = replay_trace(corpus, raw_trace)
        trace_ok = True
    except Exception as exc:
        failures.append({"category": "trace_replay_failed", "message": str(exc)})

    accounting: dict[str, Any] | None = None
    try:
        accounting = reconcile_observed(raw_trace, events)
        failures.extend(copy.deepcopy(accounting.get("failures", [])))
    except Exception as exc:
        failures.append({"category": "reconciliation_failed", "message": str(exc)})

    anchor, native_id, anchor_failures = _expected_anchor(case)
    failures.extend(anchor_failures)
    files = trace.files if trace is not None else {}

    rows_by_id = {
        row.get("item_id"): row
        for row in (accounting or {}).get("calls", [])
        if isinstance(row, dict)
    }
    deliveries = {
        entry.get("attempt_id"): entry
        for entry in (raw_trace.get("deliveries", []) if isinstance(raw_trace, dict) else [])
        if isinstance(entry, dict)
    }

    repository_calls = [
        (item_id, call)
        for item_id, call, _started in terminal_calls
        if call.get("tool") not in HELPERS
    ]
    first = repository_calls[0] if repository_calls else None
    first_repository_call = None
    if first is not None:
        item_id, call = first
        arguments = call.get("arguments")
        first_repository_call = {
            "item_id": item_id,
            "tool": call.get("tool"),
            "intent": arguments.get("intent") if isinstance(arguments, dict) else None,
            "status": call.get("status"),
        }

    explore_calls: list[dict[str, Any]] = []
    for position, (item_id, call) in enumerate(repository_calls):
        if call.get("tool") != "loci_explore":
            continue
        arguments = call.get("arguments")
        intent = arguments.get("intent") if isinstance(arguments, dict) else None
        payload, native_valid = _native_payload(call)
        native_status = (
            payload.get("status")
            if isinstance(payload, dict) and isinstance(payload.get("status"), str)
            else call.get("status")
        )
        row = rows_by_id.get(item_id)
        delivery = deliveries.get(row.get("attempt_id")) if isinstance(row, dict) else None
        successful_delivery = bool(
            call.get("status") == "completed"
            and native_valid
            and isinstance(row, dict)
            and row.get("serialized_bytes") is not None
            and row.get("source_bytes") is not None
            and isinstance(delivery, dict)
            and delivery.get("status") == "recorded"
            and delivery.get("trace_event_id") is not None
            and trace_ok
        )
        requested, complete, _ = _source_for_anchor(payload if native_valid else None, anchor, native_id, files)
        anchor_trace_proof = _has_matching_anchor_trace_span(
            trace,
            row.get("trace_event_id") if isinstance(row, dict) else None,
            anchor,
        )
        if requested and not anchor_trace_proof:
            failure = {
                "category": "missing_requested_anchor_source",
                "item": item_id,
            }
            failures.append(failure)
            routing_integrity_failures.append(failure)
        # A valid call for another anchor can still be delivered successfully.
        # Requested-anchor exposure additionally needs this call's source proof.
        successful_delivery = successful_delivery and (not requested or anchor_trace_proof)
        requested = bool(successful_delivery and requested)
        if not requested:
            complete = False
        ids = []
        omissions: list[Any] = []
        if isinstance(payload, dict):
            raw_items = payload.get("items")
            if isinstance(raw_items, list):
                ids = [
                    item.get("id")
                    for item in raw_items
                    if (
                        isinstance(item, dict)
                        and item.get("role") == "anchor"
                        and isinstance(item.get("id"), str)
                    )
                ]
            raw_omissions = payload.get("omissions")
            if isinstance(raw_omissions, list):
                omissions = copy.deepcopy(raw_omissions)
        explore_calls.append(
            {
                "item_id": item_id,
                "intent": intent,
                "status": native_status,
                "successful_delivery": successful_delivery,
                "anchor_ids": ids,
                "omissions": omissions,
                "requested_anchor_received": requested,
                "anchor_complete": complete,
            }
        )

    first_explore_position = next(
        (position for position, (item_id, call) in enumerate(repository_calls) if call.get("tool") == "loci_explore"),
        None,
    )
    fallback_calls: list[dict[str, Any]] = []
    if first_explore_position is not None:
        for item_id, call in repository_calls[first_explore_position + 1 :]:
            if call.get("tool") != "loci_explore":
                fallback_calls.append(
                    {"item_id": item_id, "tool": call.get("tool"), "status": call.get("status")}
                )

    helper_call_count = sum(1 for _item_id, call, _started in terminal_calls if call.get("tool") in HELPERS)
    observations_complete = bool(
        trace_ok
        and accounting is not None
        and accounting.get("complete")
        and not lifecycle_failures
        and not routing_integrity_failures
    )

    initial_type_route: bool | None
    requested_anchor_received: bool | None
    maintained_exposure: bool | None
    if not observations_complete:
        initial_type_route = None
        requested_anchor_received = None
        maintained_exposure = None
    else:
        initial_type_route = (
            first_repository_call is not None
            and first_repository_call.get("intent") == "type_dependencies"
        ) if first_repository_call is not None else None
        requested_anchor_received = (
            any(call["requested_anchor_received"] for call in explore_calls)
            if explore_calls
            else False
        )
        maintained_exposure = None
        if case.get("group") == "maintained_task":
            first_is_type_route = (
                first_repository_call is not None
                and first_repository_call.get("tool") == "loci_explore"
                and first_repository_call.get("intent") == "type_dependencies"
            )
            first_item_id = (
                first_repository_call.get("item_id") if first_repository_call is not None else None
            )
            first_explore = next(
                (call for call in explore_calls if call["item_id"] == first_item_id),
                None,
            )
            maintained_exposure = bool(
                first_is_type_route
                and first_explore is not None
                and first_explore["successful_delivery"]
                and first_explore["requested_anchor_received"]
            )

    return {
        "schema_version": 1,
        "observations_complete": observations_complete,
        "first_repository_call": first_repository_call,
        "initial_route_expected": expected_route,
        "initial_type_route": initial_type_route,
        "requested_anchor_received": requested_anchor_received,
        "maintained_exposure": maintained_exposure,
        "explore_calls": explore_calls,
        "fallback_calls": fallback_calls,
        "helper_call_count": helper_call_count,
        "failures": failures,
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
    """Measure a retained v1 trace using v2 accounting plus routing exposure."""

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
    artifact = {
        "schema_version": 3,
        "protocol": VERSION,
        "identity": trace.identity,
        "events": trace.events,
        "measurement": measurement,
        "baseline": baseline,
    }
    artifact["routing"] = observe_routing(corpus, case, raw, events)
    return artifact


__all__ = [
    "ExploreObservedTrace",
    "ExploreReadTrace",
    "PROTOCOL",
    "RAW_PROTOCOL",
    "VERSION",
    "measure",
    "observe_routing",
    "reconcile_observed",
    "replay_trace",
]
