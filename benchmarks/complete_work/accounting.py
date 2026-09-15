"""Versioned accounting for an entire native App Server episode.

Cumulative usage is differenced once across the fresh thread, never added once
per stage. A missing or inconsistent observation remains explicitly unknown.
"""
from __future__ import annotations

from collections import Counter
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
    by_turn = {s["turn_id"]: s for s in stages if s.get("turn_id")}
    totals = {key: 0 for key in FIELDS}
    stage_usage = {key: {f: 0 for f in FIELDS} for key in by_turn}
    observed: Counter = Counter()
    items: dict[tuple[str, str], dict] = {}
    raw_calls: dict[tuple[str, str], dict] = {}
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
    stage_rows = []
    for stage in stages:
        turn = stage.get("turn_id")
        selected = [v for (t, _), v in items.items() if t == turn]
        calls = [v for (t, _), v in raw_calls.items() if t == turn]
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
