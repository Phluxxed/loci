from __future__ import annotations

import json
from pathlib import Path

import pytest

from benchmarks.complete_work.accounting import summarize_native


THREAD = "fresh-thread"
SESSION = "parent-session"
TURNS = ("turn-a", "turn-b")
SETTINGS = {
    "cwd": "/fixture/repo",
    "model": "gpt-6-sol",
    "effort": "high",
    "approval_policy": "on-request",
    "approvals_reviewer": "auto_review",
    "sandbox_policy": {"type": "workspace-write"},
    "permission_profile": {"type": "managed"},
    "active_permission_profile": {"id": "fixture"},
    "file_system_sandbox_policy": {"kind": "restricted"},
}


def _usage(inputs: int, cache: int, outputs: int) -> dict:
    return {
        "input_tokens": inputs, "cached_input_tokens": cache,
        "cache_write_input_tokens": 0, "output_tokens": outputs,
        "reasoning_output_tokens": 0, "total_tokens": inputs + outputs,
    }


def _row(kind: str, payload: dict) -> dict:
    return {"timestamp": "2026-10-22T00:00:00Z", "type": kind, "payload": payload}


def _event(kind: str, turn: str, **fields) -> dict:
    return _row("event_msg", {"type": kind, "thread_id": THREAD, "turn_id": turn, **fields})


def _response(kind: str, turn: str, **fields) -> dict:
    return _row("response_item", {
        "type": kind, "internal_chat_message_metadata_passthrough": {"turn_id": turn},
        **fields,
    })


def _token(turn: str, response: str, own: dict, turn_total: dict, thread_total: dict) -> dict:
    return _row("token_usage_record", {
        "thread_id": THREAD, "session_id": SESSION, "turn_id": turn,
        "response_id": response, "usage": own,
        "turn_token_usage": turn_total, "thread_token_usage": thread_total,
    })


def _episode() -> list[dict]:
    first, second = TURNS
    rows = [_row("session_meta", {
        "id": THREAD, "session_id": SESSION, "cwd": SETTINGS["cwd"],
        "cli_version": "0.163.0", "source": "cli", "thread_source": "user",
    })]
    rows += [
        _event("task_started", first, started_at=100),
        _response("message", first, role="user", content=[]),
        _row("turn_context", {"turn_id": first, **SETTINGS}),
        _response("function_call", first, call_id="call-shell", name="exec_command",
                  arguments="{\"cmd\":\"false\"}"),
        _event("item_completed", first, item={
            "type": "CommandExecution", "id": "shell-1", "command": ["false"],
            "status": "completed", "exit_code": 7, "aggregated_output": "deliberate failure",
        }, completed_at_ms=100001),
        _response("function_call_output", first, call_id="call-shell",
                  output="exit 7: deliberate failure"),
        _response("custom_tool_call", first, call_id="call-mcp", name="exec",
                  input="retrieve source"),
        _event("item_started", first, item={
            "type": "McpToolCall", "id": "mcp-1", "server": "loci",
            "tool": "loci_read", "arguments": {"repo": "/fixture/repo"},
            "status": "inProgress",
        }, started_at_ms=100002),
        _event("item_completed", first, item={
            "type": "McpToolCall", "id": "mcp-1", "server": "loci",
            "tool": "loci_read", "arguments": {"repo": "/fixture/repo"},
            "status": "completed",
            "result": {"content": [], "structuredContent": {"source": {"content": "answer"}},
                       "isError": False},
        }, completed_at_ms=100003),
        _response("custom_tool_call_output", first, call_id="call-mcp",
                  output={"source": "answer"}),
        _token(first, "response-1", _usage(10, 2, 2),
               _usage(10, 2, 2), _usage(10, 2, 2)),
        _response("message", first, role="assistant", phase="final_answer", content=[]),
        _token(first, "response-2", _usage(4, 0, 1),
               _usage(14, 2, 3), _usage(14, 2, 3)),
        _event("task_complete", first, started_at=100, completed_at=102, duration_ms=2000),
        _event("task_started", second, started_at=200),
        _response("message", second, role="user", content=[]),
        _row("turn_context", {"turn_id": second, **SETTINGS}),
        _response("message", second, role="assistant", phase="final_answer", content=[]),
        _token(second, "response-3", _usage(6, 1, 2),
               _usage(6, 1, 2), _usage(20, 3, 5)),
        _event("task_complete", second, started_at=200, completed_at=201, duration_ms=1000),
    ]
    return rows


def _summarize(tmp_path: Path, rows: list[dict]) -> dict:
    path = tmp_path / "rollout.jsonl"
    path.write_text("".join(json.dumps(row) + "\n" for row in rows))
    return summarize_native(path, THREAD)


def test_two_native_turns_reconcile_usage_and_keep_inner_outer_evidence(tmp_path: Path) -> None:
    rows = _episode()
    rows.insert(12, dict(rows[11]))  # An identical response usage replay is free.
    result = _summarize(tmp_path, rows)

    assert result["accounting"] == "native-rollout-v1"
    assert result["usage_status"] == "known"
    assert result["usage"] == {
        "inputTokens": 20, "cachedInputTokens": 3, "outputTokens": 5,
        "reasoningOutputTokens": 0, "totalTokens": 25,
        "cacheWriteInputTokens": 0, "uncachedInputTokens": 17,
    }
    assert result["native_errors"] == []
    assert result["phase_groups"] == {}
    assert [x["usage"]["inputTokens"] for x in result["stages"]] == [14, 6]
    assert [x["observed_completed_model_requests"] for x in result["stages"]] == [2, 1]
    assert result["turn_contexts"][0]["approval_policy"] == "on-request"
    assert "summary" not in result["turn_contexts"][0]
    first = result["stages"][0]
    assert (first["shell_calls"], first["failed_shell_calls"], first["mcp_calls"],
            first["outer_tool_calls"]) == (1, 1, 1, 2)
    assert first["outer_tool_calls_status"] == "observed"
    assert {call["output_item"]["call_id"] for call in first["raw_tool_calls"]} == {
        "call-shell", "call-mcp",
    }
    assert next(x for x in first["items"] if x["id"] == "mcp-1")["result"]["structuredContent"] == {
        "source": {"content": "answer"},
    }
    assert next(x for x in first["items"] if x["id"] == "shell-1")["exitCode"] == 7


def test_missing_final_usage_keeps_partial_tokens_unknown(tmp_path: Path) -> None:
    rows = [row for row in _episode()[:15]
            if not (row["type"] == "token_usage_record"
                    and row["payload"]["response_id"] == "response-2")]
    result = _summarize(tmp_path, rows)
    assert result["usage_status"] == "unknown"
    assert result["usage"] is None
    assert result["observed_cumulative_usage"]["inputTokens"] == 10
    assert result["stages"][0]["outcome"] == "capture_failed"
    assert result["native_errors"] == ["final response usage is missing for turn turn-a"]


@pytest.mark.parametrize("reason, outcome", [
    ("timeout", "timed_out"), ("interrupted", "interrupted"),
    ("runtime_failed", "failed"), (None, "interrupted"),
])
def test_terminal_failure_and_open_turn_keep_lower_bound_unknown(
    tmp_path: Path, reason: str | None, outcome: str,
) -> None:
    rows = _episode()[:12]
    if reason:
        rows.append(_event("turn_aborted", TURNS[0], reason=reason, started_at=100,
                           completed_at=102, duration_ms=2000))
    if reason == "interrupted":
        late = _event("item_completed", TURNS[0], item={
            "type": "CommandExecution", "id": "late-shell", "status": "completed",
            "command": ["cleanup"], "exit_code": 0,
        }, completed_at_ms=105000)
        late["timestamp"] = "2026-10-22T00:00:03Z"
        rows.append(late)
    result = _summarize(tmp_path, rows)
    assert result["usage_status"] == "unknown"
    assert result["observed_cumulative_usage"]["inputTokens"] == 10
    assert result["stages"][0]["outcome"] == outcome
    if reason == "interrupted":
        assert result["stages"][0]["late_items_after_abort"] == 1
        assert result["stages"][0]["post_abort_cleanup_ms"] == 3000


def test_unpaired_outer_call_is_unknown_even_with_complete_usage(tmp_path: Path) -> None:
    rows = [row for row in _episode()
            if not (row["type"] == "response_item"
                    and row["payload"].get("type") == "custom_tool_call_output")]
    result = _summarize(tmp_path, rows)
    assert result["usage_status"] == "unknown"
    assert any("has no paired item" in error for error in result["native_errors"])


@pytest.mark.parametrize("mutation, expected", [
    (lambda rows: rows[0]["payload"].update(id="other"), "session identity"),
    (lambda rows: rows[0]["payload"].update(forked_from_id="prior"), "forked history"),
    (lambda rows: rows.insert(1, _response("message", TURNS[0], role="assistant", content=[])),
     "pre-turn history"),
    (lambda rows: rows.insert(2, _response("message", TURNS[0], role="assistant", content=[])),
     "inherited first-turn history"),
    (lambda rows: rows.insert(3, _response("message", TURNS[0], role="user", content=[])),
     "single fresh first-turn user"),
    (lambda rows: rows[11]["payload"].update(turn_id="foreign"), "unknown turn"),
    (lambda rows: rows[11]["payload"]["turn_token_usage"].update(input_tokens=12, total_tokens=14),
     "do not reconcile"),
    (lambda rows: rows.insert(12, {**rows[11], "payload": {
        **rows[11]["payload"], "usage": _usage(11, 2, 2),
    }}), "conflicting duplicate"),
    (lambda rows: rows[3]["payload"].pop("sandbox_policy"), "context is missing"),
])
def test_corrupted_native_trace_never_becomes_known(
    tmp_path: Path, mutation, expected: str,
) -> None:
    rows = _episode()
    mutation(rows)
    with pytest.raises(ValueError, match=expected):
        _summarize(tmp_path, rows)
