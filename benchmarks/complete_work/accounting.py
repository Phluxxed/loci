"""Versioned accounting for an entire native App Server episode.

Cumulative usage is differenced once across the fresh thread, never added once
per stage. A missing or inconsistent observation remains explicitly unknown.
"""
from __future__ import annotations

from collections import Counter
from datetime import datetime
import json
import math
from pathlib import Path

FIELDS = ("inputTokens", "cachedInputTokens", "outputTokens",
          "reasoningOutputTokens", "totalTokens", "cacheWriteInputTokens")


def usage_value(value: dict) -> dict:
    out = {}
    for key in FIELDS:
        item = value.get(key, 0 if key == "cacheWriteInputTokens" else None)
        if not isinstance(item, int) or isinstance(item, bool) or item < 0:
            raise ValueError(f"invalid usage {key}")
        out[key] = item
    if out["cachedInputTokens"] > out["inputTokens"]:
        raise ValueError("cached input exceeds input")
    return out


def summarize(journal_path: Path, stages: list[dict], thread_id: str) -> dict:
    records = [json.loads(line) for line in journal_path.read_text().splitlines()]
    return _summarize_records(records, stages, thread_id)


def _summarize_records(records: list[dict], stages: list[dict], thread_id: str) -> dict:
    by_turn = {s["turn_id"]: s for s in stages if s.get("turn_id")}
    totals = {key: 0 for key in FIELDS}
    stage_usage = {key: {f: 0 for f in FIELDS} for key in by_turn}
    observed: Counter = Counter()
    items: dict[tuple[str, str], dict] = {}
    raw_calls: dict[tuple[str, str], dict] = {}
    raw_outputs: dict[tuple[str, str], dict] = {}
    responses: dict[tuple[str, str], dict] = {}
    boundaries: dict[str, list[dict]] = {key: [] for key in by_turn}
    usage_errors: list[str] = []
    capture_errors: list[str] = []
    for row in records:
        if row.get("direction") != "received":
            continue
        event = row.get("message", {})
        method, params = event.get("method"), event.get("params", {})
        if not isinstance(params, dict):
            continue
        if params.get("threadId") not in (None, thread_id):
            capture_errors.append("foreign thread event")
            continue
        turn = params.get("turnId") or params.get("turn", {}).get("id")
        if turn in by_turn:
            boundaries[turn].append({k: row.get(k) for k in ("ordinal", "monotonic", "utc")})
        if method == "rawResponse/completed" and turn in by_turn:
            ident = params.get("responseId")
            if not isinstance(ident, str) or not ident:
                capture_errors.append("upstream completion has no response identity")
            else:
                key = (turn, ident)
                if key in responses and responses[key] != params:
                    capture_errors.append("conflicting duplicate upstream response")
                responses[key] = params
        if method == "thread/tokenUsage/updated":
            if turn not in by_turn:
                usage_errors.append("usage for unknown turn")
                continue
            try:
                current = usage_value(params["tokenUsage"]["total"])
                if any(current[f] < totals[f] for f in FIELDS):
                    raise ValueError("nonmonotonic cumulative usage")
                delta = {f: current[f] - totals[f] for f in FIELDS}
                for f in FIELDS:
                    stage_usage[turn][f] += delta[f]
                if any(delta.values()):
                    observed[turn] += 1
                totals = current
            except (KeyError, ValueError, TypeError) as exc:
                usage_errors.append(str(exc))
        if method in ("item/started", "item/completed") and turn in by_turn:
            item = params.get("item", {})
            if isinstance(item, dict) and isinstance(item.get("id"), str):
                key = (turn, item["id"])
                # Retain the latest complete shape; starts are only fallback.
                boundary = {"utc": row.get("utc"), "emitted_at_ms": event.get("emittedAtMs"),
                            "ordinal": row.get("ordinal"), "monotonic": row.get("monotonic")}
                if method == "item/completed" or key not in items:
                    previous = items.get(key, {})
                    items[key] = {**item, "capture_boundary": method,
                                  "capture_started": (boundary if method == "item/started"
                                                      else previous.get("capture_started")),
                                  "capture_completed": boundary if method == "item/completed" else None}
        if method == "rawResponseItem/completed" and turn in by_turn:
            item = params.get("item", {})
            if isinstance(item, dict) and item.get("type") in ("function_call", "custom_tool_call"):
                ident = item.get("call_id", item.get("id"))
                if isinstance(ident, str):
                    raw_calls[(turn, ident)] = item
            if isinstance(item, dict) and item.get("type") in ("function_call_output", "custom_tool_call_output"):
                ident = item.get("call_id")
                if isinstance(ident, str):
                    raw_outputs[(turn, ident)] = item
    stage_rows = []
    for stage in stages:
        turn = stage.get("turn_id")
        selected = [v for (t, _), v in items.items() if t == turn]
        calls = [{**v, **({"output_item": raw_outputs[(t, ident)]}
                         if (t, ident) in raw_outputs else {})}
                 for (t, ident), v in raw_calls.items() if t == turn]
        counts = Counter(x.get("type", "unknown") for x in selected)
        interrupted = stage["outcome"] in {"timed_out", "runtime_failed", "capture_failed", "interrupted", "failed"}
        known = bool(turn and observed[turn] and not usage_errors and not capture_errors and not interrupted)
        u = stage_usage.get(turn)
        upstream = [v for (t, _), v in responses.items() if t == turn]
        stage_rows.append({
            "stage_id": stage["stage_id"], "turn_id": turn,
            "outcome": stage["outcome"], "elapsed_ms": stage.get("elapsed_ms"),
            "usage_status": "known" if known else "unknown",
            "usage": ({**u, "uncachedInputTokens": u["inputTokens"] - u["cachedInputTokens"]}
                      if known and u else None),
            "usage_updates": observed[turn],
            "observed_usage_delta": u,
            "usage_limitation": ("Interrupted capture may omit the final upstream request; observed usage is a lower bound."
                                 if interrupted else None),
            "mcp_calls": counts["mcpToolCall"],
            "shell_calls": counts["commandExecution"],
            "file_change_calls": counts["fileChange"],
            "context_compactions": counts["contextCompaction"],
            "subagent_calls": counts["collabAgentToolCall"],
            "failed_shell_calls": sum(x.get("exitCode") not in (None, 0)
                                      or x.get("status") in ("failed", "errored")
                                      for x in selected if x.get("type") == "commandExecution"),
            "outer_tool_calls": len(calls) if calls else None,
            "outer_tool_calls_status": "observed" if calls else "unavailable",
            "model_requests": None,
            "observed_completed_model_requests": len(upstream) if upstream else None,
            "model_requests_status": "completion_lower_bound" if upstream else "unavailable",
            "upstream_responses": upstream,
            "first_event": boundaries[turn][0] if turn in boundaries and boundaries[turn] else None,
            "last_event": boundaries[turn][-1] if turn in boundaries and boundaries[turn] else None,
            "operation_counts_status": "observed_items_only",
            "items": selected, "raw_tool_calls": calls,
        })
    reached = [x for x in stage_rows if x["outcome"] != "not_reached"]
    known = bool(reached) and all(x["usage_status"] == "known" for x in reached)
    return {
        "schema_version": 1, "accounting": "app-server-episode-v1",
        "thread_id": thread_id, "stages": stage_rows,
        "usage_status": "known" if known else "unknown",
        "usage": ({**totals, "uncachedInputTokens": totals["inputTokens"] - totals["cachedInputTokens"]}
                  if known else None),
        "observed_cumulative_usage": totals, "usage_errors": usage_errors,
        "capture_errors": capture_errors,
        "operation_totals": {key: sum(x[key] for x in stage_rows)
                             for key in ("mcp_calls", "shell_calls", "file_change_calls",
                                         "context_compactions", "subagent_calls", "failed_shell_calls")},
        "phase_groups": {
            label: {
                "stage_ids": [x["stage_id"] for x in stage_rows if x["stage_id"] in ids],
                "usage": ({f: sum(x["usage"][f] for x in stage_rows if x["stage_id"] in ids)
                           for f in (*FIELDS, "uncachedInputTokens")}
                          if all(x["usage_status"] == "known" for x in stage_rows
                                 if x["stage_id"] in ids) else None),
                "mcp_calls": sum(x["mcp_calls"] for x in stage_rows if x["stage_id"] in ids),
                "shell_calls": sum(x["shell_calls"] for x in stage_rows if x["stage_id"] in ids),
                "elapsed_ms": (sum(x["elapsed_ms"] for x in stage_rows if x["stage_id"] in ids)
                               if all(x["elapsed_ms"] is not None for x in stage_rows if x["stage_id"] in ids)
                               else None),
            } for label, ids in (("orientation", {"orient"}),
                                 ("downstream", {"implement", "continue"}))
        },
        "limitations": ["Usage updates are not proven model-request counts; unique raw response completions are a lower bound that may omit failed upstream requests/retries.",
                        "Raw outer-call availability is explicit; nested operation counts are distinct.",
                        "Behavioral quality and rework attribution require the independent oracle/review.",
                        "MCP source/delivery receipts are joined separately; item presence is not model reliance."],
    }


NATIVE_USAGE_FIELDS = {
    "input_tokens": "inputTokens",
    "cached_input_tokens": "cachedInputTokens",
    "output_tokens": "outputTokens",
    "reasoning_output_tokens": "reasoningOutputTokens",
    "total_tokens": "totalTokens",
    "cache_write_input_tokens": "cacheWriteInputTokens",
}
NATIVE_ITEM_TYPES = {
    "McpToolCall": "mcpToolCall",
    "CommandExecution": "commandExecution",
    "FileChange": "fileChange",
    "ContextCompaction": "contextCompaction",
    "SubAgentActivity": "collabAgentToolCall",
}
NATIVE_CONTEXT_FIELDS = (
    "turn_id", "cwd", "model", "effort", "approval_policy", "approvals_reviewer",
    "sandbox_policy", "permission_profile", "active_permission_profile",
    "file_system_sandbox_policy",
)


def _native_usage(value: object) -> dict:
    if not isinstance(value, dict) or any(key not in value for key in NATIVE_USAGE_FIELDS):
        raise ValueError("native usage is missing required fields")
    usage = usage_value({name: value[key] for key, name in NATIVE_USAGE_FIELDS.items()})
    if (usage["totalTokens"] != usage["inputTokens"] + usage["outputTokens"]
            or usage["reasoningOutputTokens"] > usage["outputTokens"]):
        raise ValueError("native usage totals are inconsistent")
    return usage


def _native_bootstrap_user(payload: dict, turn_id: str) -> bool:
    """Recognize the recorded host envelope, never a task's textual prefix."""
    metadata = payload.get("internal_chat_message_metadata_passthrough")
    if not isinstance(metadata, dict) or "content_item_kinds" not in metadata:
        return False
    kinds = metadata["content_item_kinds"]
    if not isinstance(kinds, list):
        raise ValueError("native user message classification is malformed")
    expected = ["agents_md.instructions", "environments.environment_context"]
    if not any(kind in expected for kind in kinds):
        return False
    content = payload.get("content")
    provenance = metadata.get("content_item_metadata")
    if (kinds != expected or metadata.get("turn_id") != turn_id
            or not isinstance(content, list) or len(content) != 2
            or not isinstance(provenance, list) or len(provenance) != 2
            or any(not isinstance(part, dict) or part.get("type") != "input_text"
                   or not isinstance(part.get("text"), str) or not part["text"]
                   for part in content)
            or provenance != [{"provenance": {"type": "agents_md"}},
                              {"provenance": {"type": "harness", "hook": False}}]):
        raise ValueError("native bootstrap provenance is malformed or unsupported")
    return True


def summarize_native(rollout_path: Path, thread_id: str) -> dict:
    """Reduce one fresh native rollout, retaining only safe metadata in the report.

    The original JSONL remains the source for full provenance and tool outputs.
    A completed turn needs its final response's usage record before task_complete.
    Interrupted turns retain observed lower bounds but cannot yield known usage.
    """
    rows = [json.loads(line) for line in rollout_path.read_text().splitlines()]
    if not rows or not isinstance(rows[0], dict) or rows[0].get("type") != "session_meta":
        raise ValueError("native rollout has no leading session_meta")
    meta = rows[0].get("payload")
    if (not isinstance(meta, dict) or meta.get("id") != thread_id
            or not isinstance(meta.get("session_id"), str) or not meta["session_id"]
            or not isinstance(meta.get("cwd"), str)
            or not isinstance(meta.get("cli_version"), str)):
        raise ValueError("native rollout session identity is invalid")
    if meta.get("forked_from_id") is not None:
        raise ValueError("native rollout contains forked history")
    # A spawned worker can be fresh (fork_turns=none). The source label alone
    # cannot prove inheritance; the first turn's actual history is checked below.
    source = meta.get("source")
    if isinstance(source, dict) and set(source) != {"subagent"}:
        raise ValueError("native rollout has a forked or unknown source")
    if (not isinstance(source, (str, dict))
            or meta.get("thread_source") != ("subagent" if isinstance(source, dict) else "user")):
        raise ValueError("native rollout source is invalid")

    started: dict[str, tuple[int, dict]] = {}
    contexts: dict[str, dict] = {}
    completed: dict[str, tuple[int, dict]] = {}
    failed: dict[str, tuple[int, dict, str]] = {}
    late_items: dict[str, list[str]] = {}
    finals: dict[str, int] = {}
    usage_positions: dict[str, list[int]] = {}
    first_turn_users = 0
    bootstrap_rows: list[int] = []
    active: str | None = None
    response_records: dict[str, tuple[str, dict, dict, dict]] = {}
    call_records: dict[tuple[str, str, str], dict] = {}
    item_records: dict[tuple[str, str, str], dict] = {}
    turn_sums: dict[str, dict[str, int]] = {}
    thread_sum = {field: 0 for field in FIELDS}
    native_errors: list[str] = []
    events: list[dict] = []

    def emit(method: str, params: dict, row: dict, index: int, *, emitted_at_ms: object = None) -> None:
        events.append({
            "direction": "received", "ordinal": row.get("ordinal", index),
            "utc": row.get("timestamp"), "monotonic": None,
            "message": {"method": method, "params": params, "emittedAtMs": emitted_at_ms},
        })

    def require_turn(value: object) -> str:
        if not isinstance(value, str) or value not in started:
            raise ValueError("native event belongs to an unknown turn")
        return value

    for index, row in enumerate(rows):
        if not isinstance(row, dict) or not isinstance(row.get("payload"), dict):
            raise ValueError("native rollout row is malformed")
        kind, payload = row.get("type"), row["payload"]
        if not started and index and kind in ("response_item", "token_usage_record", "turn_context"):
            raise ValueError("native rollout contains pre-turn history")
        if kind == "event_msg" and payload.get("type") != "task_started":
            if "turn_id" in payload and payload["turn_id"] not in started:
                raise ValueError("native event belongs to an unknown turn")
            if "thread_id" in payload and payload["thread_id"] != thread_id:
                raise ValueError("native event belongs to a foreign thread")
        if kind == "session_meta" and index:
            raise ValueError("native rollout has multiple session_meta rows")
        if kind == "event_msg" and payload.get("type") == "task_started":
            turn = payload.get("turn_id")
            if not isinstance(turn, str) or not turn or turn in started:
                raise ValueError("native task_started turn identity is invalid")
            if active is not None:
                native_errors.append(f"new turn began before {active} reached a terminal event")
            if not isinstance(payload.get("started_at"), (int, float)):
                raise ValueError("native task_started has no start time")
            started[turn] = (index, payload)
            turn_sums[turn] = {field: 0 for field in FIELDS}
            usage_positions[turn] = []
            active = turn
            continue
        if kind == "turn_context":
            turn = require_turn(payload.get("turn_id"))
            if turn != active or any(field not in payload for field in NATIVE_CONTEXT_FIELDS):
                raise ValueError("native turn context is missing or misplaced")
            context = {field: payload[field] for field in NATIVE_CONTEXT_FIELDS}
            if any(context[field] is None for field in ("cwd", "model", "effort", "approval_policy")):
                raise ValueError("native turn context is missing required settings")
            if turn in contexts and contexts[turn] != context:
                raise ValueError("conflicting native turn contexts")
            contexts[turn] = context
            continue
        if kind == "event_msg" and payload.get("type") in ("item_started", "item_completed"):
            turn = require_turn(payload.get("turn_id"))
            if payload.get("thread_id") != thread_id or (turn != active and turn not in failed):
                raise ValueError("native item thread or turn does not match")
            item = payload.get("item")
            if not isinstance(item, dict) or not isinstance(item.get("id"), str) or not isinstance(item.get("type"), str):
                raise ValueError("native item identity is invalid")
            identity = (turn, item["id"], payload["type"])
            if identity in item_records:
                if item_records[identity] != item:
                    raise ValueError("conflicting duplicate native item")
                continue
            item_records[identity] = item
            if turn in failed:
                late_items.setdefault(turn, []).append(row.get("timestamp"))
            adapted = dict(item)
            adapted["type"] = NATIVE_ITEM_TYPES.get(item["type"], item["type"])
            adapted["native_type"] = item["type"]
            if item["type"] == "CommandExecution" and "exit_code" in item:
                adapted["exitCode"] = item["exit_code"]
            emit("item/started" if payload["type"] == "item_started" else "item/completed",
                 {"threadId": thread_id, "turnId": turn, "item": adapted}, row, index,
                 emitted_at_ms=payload.get("started_at_ms") if payload["type"] == "item_started"
                 else payload.get("completed_at_ms"))
            continue
        if kind == "token_usage_record":
            turn = require_turn(payload.get("turn_id"))
            if (payload.get("thread_id") != thread_id or payload.get("session_id") != meta["session_id"]
                    or turn != active or not isinstance(payload.get("response_id"), str)
                    or not payload["response_id"]):
                raise ValueError("native usage identity is invalid")
            usage = _native_usage(payload.get("usage"))
            turn_total = _native_usage(payload.get("turn_token_usage"))
            thread_total = _native_usage(payload.get("thread_token_usage"))
            response_id = payload["response_id"]
            record = (turn, usage, turn_total, thread_total)
            if response_id in response_records:
                if response_records[response_id] != record:
                    raise ValueError("conflicting duplicate native response usage")
                continue
            response_records[response_id] = record
            for field in FIELDS:
                turn_sums[turn][field] += usage[field]
                thread_sum[field] += usage[field]
            if turn_sums[turn] != turn_total or thread_sum != thread_total:
                raise ValueError("native response, turn and thread usage do not reconcile")
            usage_positions[turn].append(index)
            emit("thread/tokenUsage/updated",
                 {"threadId": thread_id, "turnId": turn, "tokenUsage": {"total": thread_total}},
                 row, index)
            emit("rawResponse/completed", {"threadId": thread_id, "turnId": turn,
                                            "responseId": response_id}, row, index)
            continue
        if kind == "response_item":
            if active is None:
                native_errors.append("native response item appeared outside an active turn")
                continue
            metadata = payload.get("internal_chat_message_metadata_passthrough")
            attributed = metadata.get("turn_id") if isinstance(metadata, dict) else None
            if attributed is not None and attributed != active:
                raise ValueError("native response item has foreign turn attribution")
            if payload.get("type") == "message":
                if payload.get("role") == "user":
                    if _native_bootstrap_user(payload, active):
                        if active != next(iter(started)) or first_turn_users or bootstrap_rows:
                            raise ValueError("native bootstrap is duplicated or misplaced")
                        bootstrap_rows.append(index)
                    elif active == next(iter(started)):
                        first_turn_users += 1
                if (active == next(iter(started), None) and first_turn_users == 0
                        and payload.get("role") == "assistant"):
                    raise ValueError("native rollout contains inherited first-turn history")
                if payload.get("role") == "assistant" and payload.get("phase") == "final_answer":
                    turn = require_turn(active)
                    if turn in finals:
                        raise ValueError("duplicate native final response")
                    finals[turn] = index
            elif payload.get("type") in ("function_call", "custom_tool_call",
                                          "function_call_output", "custom_tool_call_output"):
                turn = require_turn(active)
                if turn == next(iter(started)) and first_turn_users == 0:
                    raise ValueError("native rollout contains inherited first-turn history")
                call_id = payload.get("call_id")
                if not isinstance(call_id, str) or not call_id:
                    raise ValueError("native outer tool item has no call identity")
                identity = (turn, call_id, payload["type"])
                if identity in call_records:
                    if call_records[identity] != payload:
                        raise ValueError("conflicting duplicate native outer tool item")
                    continue
                call_records[identity] = payload
                emit("rawResponseItem/completed", {"threadId": thread_id, "turnId": turn,
                                                   "item": payload}, row, index)
            continue
        if kind == "event_msg" and payload.get("type") in ("task_complete", "turn_aborted"):
            turn = require_turn(payload.get("turn_id"))
            if turn != active or turn in completed or turn in failed:
                raise ValueError("duplicate or misplaced native terminal event")
            if not isinstance(payload.get("duration_ms"), (int, float)) or payload["duration_ms"] < 0:
                raise ValueError("native terminal event has no valid duration")
            if payload["type"] == "task_complete":
                completed[turn] = (index, payload)
            else:
                if not isinstance(payload.get("reason"), str):
                    raise ValueError("native turn_aborted has no reason")
                failed[turn] = (index, payload, row.get("timestamp"))
            active = None

    if not started or first_turn_users != 1:
        raise ValueError("native rollout has no single fresh first-turn user message")
    if any(turn not in contexts for turn in started):
        raise ValueError("native rollout is missing a turn context")
    for turn, ident, kind in call_records:
        counterpart = (kind.removesuffix("_output") if kind.endswith("_output")
                       else kind + "_output")
        if (turn, ident, counterpart) not in call_records:
            native_errors.append(f"native outer tool {kind} has no paired item in turn {turn}")

    stages = []
    for number, (turn, (_index, _start)) in enumerate(started.items(), 1):
        outcome = "interrupted"
        elapsed = None
        if turn in failed:
            _terminal_index, terminal, _terminal_time = failed[turn]
            outcome = ({"timeout": "timed_out", "timed_out": "timed_out",
                        "interrupted": "interrupted"}.get(terminal["reason"], "failed"))
            elapsed = terminal.get("duration_ms")
        elif turn in completed:
            terminal_index, terminal = completed[turn]
            outcome = "completed"
            elapsed = terminal["duration_ms"]
            if turn not in finals or not any(finals[turn] < pos < terminal_index
                                             for pos in usage_positions[turn]):
                native_errors.append(f"final response usage is missing for turn {turn}")
                outcome = "capture_failed"
        else:
            native_errors.append(f"terminal event is missing for turn {turn}")
        stages.append({"stage_id": f"turn-{number}", "turn_id": turn,
                       "outcome": outcome, "elapsed_ms": elapsed})

    result = _summarize_records(events, stages, thread_id)
    result["accounting"] = "native-rollout-v1"
    result["phase_groups"] = {}  # Native turns have no historical orient/implement labels.
    result["native_provenance"] = {
        "rollout_path": str(rollout_path), "session_id": meta["session_id"], "cwd": meta["cwd"],
        "cli_version": meta["cli_version"], "source": "subagent" if isinstance(source, dict) else source,
        "thread_source": meta["thread_source"],
        "bootstrap_message_rows": bootstrap_rows,
    }
    result["turn_contexts"] = [contexts[turn] for turn in started]
    result["native_errors"] = native_errors
    for stage in result["stages"]:
        turn = stage["turn_id"]
        stage["late_items_after_abort"] = len(late_items.get(turn, []))
        stage["post_abort_cleanup_ms"] = None
        if turn in failed and late_items.get(turn):
            terminal_time = failed[turn][2]
            if isinstance(terminal_time, str) and all(isinstance(x, str) for x in late_items[turn]):
                try:
                    end = datetime.fromisoformat(max(late_items[turn]).replace("Z", "+00:00"))
                    start = datetime.fromisoformat(terminal_time.replace("Z", "+00:00"))
                    stage["post_abort_cleanup_ms"] = max(0, round((end - start).total_seconds() * 1000, 3))
                except ValueError:
                    native_errors.append(f"late item timestamps are invalid for turn {turn}")
    if native_errors:
        result["usage_status"] = "unknown"
        result["usage"] = None
        for stage in result["stages"]:
            stage["usage_status"] = "unknown"
            stage["usage"] = None
    return result


def arm_cost(rows: list[dict], alpha: float, beta: float, *,
             expected_run_ids: list[str]) -> dict:
    """All scheduled outcomes contribute; missing rows/usage are not zeros."""
    actual = [x.get("run_id") for x in rows]
    if (not expected_run_ids or len(expected_run_ids) != len(set(expected_run_ids))
            or len(actual) != len(set(actual)) or set(actual) != set(expected_run_ids)):
        return {"status": "unproven"}
    if not rows or any(x.get("usage_status") != "known" or x.get("correct") is None
                       or x.get("elapsed_ms") is None for x in rows):
        return {"status": "unproven"}
    success = sum(x["correct"] is True for x in rows)
    u = sum(x["usage"]["uncachedInputTokens"] for x in rows)
    k = sum(x["usage"]["cachedInputTokens"] for x in rows)
    o = sum(x["usage"]["outputTokens"] for x in rows)
    elapsed = sum(x["elapsed_ms"] for x in rows)
    cost = u + alpha * k + beta * o
    return {"status": "known", "scheduled": len(rows), "correct": success,
            "uncached_input": u, "cached_input": k, "output": o,
            "elapsed_ms": elapsed, "normalized_cost": cost,
            "elapsed_per_correct": elapsed / success if success else math.inf,
            "cost_per_correct": cost / success if success else math.inf}
