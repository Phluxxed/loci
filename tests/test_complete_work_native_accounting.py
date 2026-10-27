from __future__ import annotations

import json
from copy import deepcopy
import hashlib
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


def _summarize(tmp_path: Path, rows: list[dict], *, allow_instruction_updates=False) -> dict:
    path = tmp_path / "rollout.jsonl"
    path.write_text("".join(json.dumps(row) + "\n" for row in rows))
    return summarize_native(path, THREAD, allow_instruction_updates=allow_instruction_updates)


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


def _bootstrap(turn: str = TURNS[0]) -> dict:
    return _response("message", turn, role="user", content=[
        {"type": "input_text", "text": "host guidance"},
        {"type": "input_text", "text": "host environment"},
    ], internal_chat_message_metadata_passthrough={
        "turn_id": turn,
        "content_item_kinds": ["agents_md.instructions", "environments.environment_context"],
        "content_item_metadata": [{"provenance": {"type": "agents_md"}},
                                  {"provenance": {"type": "harness", "hook": False}}],
    })


def test_typed_host_bootstrap_preserves_usage_and_task_freshness(tmp_path):
    rows = _episode()
    rows.insert(2, _bootstrap())
    result = _summarize(tmp_path, rows)
    assert result["usage_status"] == "known"
    assert result["usage"]["totalTokens"] == 25
    assert result["native_provenance"]["bootstrap_message_rows"] == [2]


def test_retained_top_level_trace_is_read_without_rewriting_evidence():
    path = (Path(__file__).resolve().parents[1] / ".scratch/r1-integrated/pilot"
            / "archived-runs/receipt-location-native/observer/qualification/native-rollout.jsonl")
    before = hashlib.sha256(path.read_bytes()).hexdigest()
    result = summarize_native(path, "01a176ca-a192-7cb1-8351-a0ca42d0d477")
    assert result["usage_status"] == "known" and result["native_errors"] == []
    assert result["usage"] == {
        "inputTokens": 118160, "cachedInputTokens": 95232, "outputTokens": 934,
        "reasoningOutputTokens": 124, "totalTokens": 119094,
        "cacheWriteInputTokens": 0, "uncachedInputTokens": 22928,
    }
    assert result["native_provenance"]["bootstrap_message_rows"] == [7]
    assert hashlib.sha256(path.read_bytes()).hexdigest() == before


@pytest.mark.parametrize("mutation", [
    lambda p: p["internal_chat_message_metadata_passthrough"].pop("turn_id"),
    lambda p: p["internal_chat_message_metadata_passthrough"]["content_item_kinds"].append("user.text"),
    lambda p: p["internal_chat_message_metadata_passthrough"].pop("content_item_metadata"),
    lambda p: p["internal_chat_message_metadata_passthrough"]["content_item_metadata"][0].update(provenance={"type": "user"}),
    lambda p: p["internal_chat_message_metadata_passthrough"]["content_item_metadata"][1]["provenance"].update(hook=True),
    lambda p: p["content"].pop(),
    lambda p: p["content"][0].update(type="output_text"),
    lambda p: p["content"][0].update(text=""),
])
def test_partial_or_mixed_bootstrap_metadata_is_rejected(tmp_path, mutation):
    rows = _episode()
    bootstrap = _bootstrap()
    mutation(bootstrap["payload"])
    rows.insert(2, bootstrap)
    with pytest.raises(ValueError, match="bootstrap provenance"):
        _summarize(tmp_path, rows)


@pytest.mark.parametrize("placement", ["duplicate", "after_task", "later_turn"])
def test_bootstrap_is_only_one_envelope_before_the_first_task(tmp_path, placement):
    rows = _episode()
    if placement == "duplicate":
        rows[2:2] = [_bootstrap(), _bootstrap()]
    elif placement == "after_task":
        rows.insert(3, _bootstrap())
    else:
        pos = next(i for i, row in enumerate(rows) if row["type"] == "event_msg"
                   and row["payload"].get("type") == "task_started"
                   and row["payload"]["turn_id"] == TURNS[1])
        rows.insert(pos + 1, _bootstrap(TURNS[1]))
    with pytest.raises(ValueError, match="bootstrap is duplicated or misplaced"):
        _summarize(tmp_path, rows)


@pytest.mark.parametrize("kind", ["assistant", "tool", "extra_user", "textual_bootstrap"])
def test_bootstrap_does_not_hide_inherited_or_additional_task_history(tmp_path, kind):
    rows = _episode()
    rows.insert(2, _bootstrap())
    if kind == "assistant":
        extra = _response("message", TURNS[0], role="assistant", content=[])
    elif kind == "tool":
        extra = deepcopy(next(row for row in rows if row["type"] == "response_item"
                              and row["payload"].get("type") == "function_call"))
    else:
        extra = _response("message", TURNS[0], role="user", content=[{
            "type": "input_text", "text": "# AGENTS.md instructions\n<environment_context>"
            if kind == "textual_bootstrap" else "another task",
        }])
    rows.insert(3, extra)
    with pytest.raises(ValueError, match="inherited first-turn history|single fresh first-turn user"):
        _summarize(tmp_path, rows)


def test_bootstrap_does_not_turn_missing_final_usage_into_known(tmp_path):
    rows = [row for row in _episode()[:15]
            if not (row["type"] == "token_usage_record"
                    and row["payload"]["response_id"] == "response-2")]
    rows.insert(2, _bootstrap())
    result = _summarize(tmp_path, rows)
    assert result["usage_status"] == "unknown" and result["usage"] is None
    assert result["native_errors"] == ["final response usage is missing for turn turn-a"]


def _instruction_update(turn=TURNS[0]):
    return _response("message", turn, role="user", content=[
        {"type": "input_text", "text": "replacement host guidance"},
    ], internal_chat_message_metadata_passthrough={
        "turn_id": turn, "content_item_kinds": ["agents_md.instructions"],
        "content_item_metadata": [{"provenance": {"type": "agents_md"}}],
    })


def test_instruction_update_opt_in_preserves_accounting(tmp_path):
    rows = _episode()
    rows.insert(2, _bootstrap())
    without = _summarize(tmp_path, rows)
    assert _summarize(tmp_path, rows, allow_instruction_updates=True) == without
    rows.insert(5, _instruction_update())
    with pytest.raises(ValueError, match="bootstrap provenance"):
        _summarize(tmp_path, rows)
    result = _summarize(tmp_path, rows, allow_instruction_updates=True)
    assert result["usage"] == without["usage"]
    assert result["operation_totals"] == without["operation_totals"]
    assert [s["elapsed_ms"] for s in result["stages"]] == [2000, 1000]
    assert result["native_provenance"]["instruction_updates"] == [{
        "row": 5, "timestamp": "2026-10-22T00:00:00Z", "turn_id": TURNS[0],
        "content_sha256": hashlib.sha256(b"replacement host guidance").hexdigest(),
        "provenance": [{"provenance": {"type": "agents_md"}}],
    }]


@pytest.mark.parametrize("mutation", [
    lambda p: p["internal_chat_message_metadata_passthrough"].pop("turn_id"),
    lambda p: p["internal_chat_message_metadata_passthrough"].update(turn_id="foreign"),
    lambda p: p["internal_chat_message_metadata_passthrough"]["content_item_metadata"][0].update(provenance={"type": "user"}),
    lambda p: p["internal_chat_message_metadata_passthrough"]["content_item_kinds"].append("user.text"),
    lambda p: p["content"][0].update(text=""),
    lambda p: p.update(role="assistant"),
])
def test_instruction_update_rejects_spoofing(tmp_path, mutation):
    rows = _episode()
    rows.insert(2, _bootstrap())
    update = _instruction_update()
    mutation(update["payload"])
    rows.insert(5, update)
    with pytest.raises(ValueError):
        _summarize(tmp_path, rows, allow_instruction_updates=True)


def test_instruction_update_cannot_hide_extra_task_or_occur_outside_turn(tmp_path):
    rows = _episode()
    rows.insert(2, _bootstrap())
    rows.insert(5, _instruction_update())
    rows.insert(6, _response("message", TURNS[0], role="user", content=[]))
    with pytest.raises(ValueError, match="single fresh first-turn user"):
        _summarize(tmp_path, rows, allow_instruction_updates=True)
    rows = _episode()
    rows.insert(2, _bootstrap())
    rows.append(_instruction_update(TURNS[1]))
    with pytest.raises(ValueError, match="outside active turn"):
        _summarize(tmp_path, rows, allow_instruction_updates=True)


def test_saved_instruction_update_trace_requires_opt_in():
    path = (Path(__file__).resolve().parents[1] / ".scratch/r1-integrated"
            / "environment-drift-blocker/native-rollout.jsonl")
    thread = "01a17b96-9ebc-7980-a2ec-686848bbb21a"
    before = hashlib.sha256(path.read_bytes()).hexdigest()
    with pytest.raises(ValueError, match="bootstrap provenance"):
        summarize_native(path, thread)
    result = summarize_native(path, thread, allow_instruction_updates=True)
    assert result["usage_status"] == "known" and result["native_errors"] == []
    assert result["usage"]["totalTokens"] == 153656
    assert result["stages"][0]["elapsed_ms"] == 38482
    assert result["stages"][0]["shell_calls"] == 5
    assert result["native_provenance"]["instruction_updates"][0]["row"] == 58
    assert hashlib.sha256(path.read_bytes()).hexdigest() == before
