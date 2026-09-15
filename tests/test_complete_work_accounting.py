from __future__ import annotations

import json
import math
from pathlib import Path

from benchmarks.complete_work.accounting import arm_cost, summarize


THREAD = "episode-thread"


def _stages(*outcomes: str) -> list[dict]:
    names = ("orient", "implement", "continue")
    return [
        {
            "stage_id": name,
            "turn_id": f"turn-{index + 1}" if outcome != "not_reached" else None,
            "outcome": outcome,
            "elapsed_ms": None if outcome == "not_reached" else (index + 1) * 100,
        }
        for index, (name, outcome) in enumerate(zip(names, outcomes, strict=True))
    ]


def _usage(
    turn: str,
    input_tokens: int,
    cached_tokens: int,
    output_tokens: int,
    *,
    thread: str = THREAD,
) -> dict:
    return {
        "direction": "received",
        "message": {
            "method": "thread/tokenUsage/updated",
            "params": {
                "threadId": thread,
                "turnId": turn,
                "tokenUsage": {"total": {
                    "inputTokens": input_tokens,
                    "cachedInputTokens": cached_tokens,
                    "outputTokens": output_tokens,
                    "reasoningOutputTokens": 0,
                    "totalTokens": input_tokens + output_tokens,
                }},
            },
        },
    }


def _event(method: str, turn: str, item: dict) -> dict:
    return {
        "direction": "received",
        "message": {"method": method, "params": {"threadId": THREAD, "turnId": turn, "item": item}},
    }


def _summarize(tmp_path: Path, records: list[dict], stages: list[dict] | None = None) -> dict:
    tmp_path.mkdir(parents=True, exist_ok=True)
    journal = tmp_path / "journal.jsonl"
    journal.write_text("\n".join(json.dumps(record) for record in records) + "\n", encoding="utf-8")
    return summarize(journal, stages or _stages("completed", "completed", "completed"), THREAD)


def test_three_turn_cumulative_usage_is_differenced_once_and_duplicate_update_is_free(tmp_path: Path) -> None:
    records = [
        _usage("turn-1", 100, 20, 10),
        _usage("turn-1", 100, 20, 10),  # Notification replay, not another request.
        _usage("turn-2", 160, 50, 25),
        _usage("turn-3", 240, 80, 40),
    ]

    result = _summarize(tmp_path, records)

    assert result["usage_status"] == "known"
    assert result["usage"] == {
        "inputTokens": 240,
        "cachedInputTokens": 80,
        "outputTokens": 40,
        "reasoningOutputTokens": 0,
        "totalTokens": 280,
        "cacheWriteInputTokens": 0,
        "uncachedInputTokens": 160,
    }
    assert [stage["usage"]["inputTokens"] for stage in result["stages"]] == [100, 60, 80]
    assert [stage["usage_updates"] for stage in result["stages"]] == [1, 1, 1]


def test_missing_nonmonotonic_and_foreign_thread_usage_never_become_zero(tmp_path: Path) -> None:
    missing = _summarize(tmp_path / "missing", [_usage("turn-1", 100, 20, 10)])
    assert missing["usage_status"] == "unknown"
    assert missing["usage"] is None
    assert missing["stages"][1]["usage"] is None

    nonmonotonic = _summarize(
        tmp_path / "nonmonotonic",
        [_usage("turn-1", 100, 20, 10), _usage("turn-2", 90, 20, 12)],
    )
    assert nonmonotonic["usage_status"] == "unknown"
    assert nonmonotonic["usage"] is None
    assert nonmonotonic["usage_errors"] == ["nonmonotonic cumulative usage"]

    foreign = _summarize(
        tmp_path / "foreign",
        [_usage("turn-1", 100, 20, 10, thread="other-thread")],
    )
    assert foreign["usage_status"] == "unknown"
    assert foreign["usage"] is None
    assert foreign["capture_errors"] == ["foreign thread event"]


def test_not_reached_stage_has_no_synthetic_zero_usage(tmp_path: Path) -> None:
    stages = _stages("completed", "completed", "not_reached")
    result = _summarize(
        tmp_path,
        [_usage("turn-1", 100, 20, 10), _usage("turn-2", 150, 40, 20)],
        stages,
    )

    assert result["usage_status"] == "known"
    not_reached = result["stages"][2]
    assert not_reached["outcome"] == "not_reached"
    assert not_reached["usage_status"] == "unknown"
    assert not_reached["usage"] is None
    assert not_reached["usage_updates"] == 0
    assert result["usage"]["inputTokens"] == 150


def test_nested_item_counts_and_outer_raw_calls_are_separate(tmp_path: Path) -> None:
    mcp = {"id": "mcp-1", "type": "mcpToolCall"}
    shell = {"id": "shell-1", "type": "commandExecution", "exitCode": 1}
    file_change = {"id": "file-1", "type": "fileChange"}
    raw_function = {"id": "raw-item-1", "call_id": "call-1", "type": "function_call"}
    raw_custom = {"id": "raw-item-2", "call_id": "call-2", "type": "custom_tool_call"}
    result = _summarize(
        tmp_path,
        [
            _usage("turn-1", 100, 20, 10),
            _usage("turn-2", 150, 40, 15),
            _usage("turn-3", 200, 60, 20),
            _event("item/started", "turn-1", mcp),
            _event("item/completed", "turn-1", mcp),
            _event("item/completed", "turn-1", shell),
            _event("item/completed", "turn-1", file_change),
            _event("rawResponseItem/completed", "turn-1", raw_function),
            _event("rawResponseItem/completed", "turn-1", raw_function),
            _event("rawResponseItem/completed", "turn-1", raw_custom),
        ],
    )

    stage = result["stages"][0]
    assert (stage["mcp_calls"], stage["shell_calls"], stage["file_change_calls"]) == (1, 1, 1)
    assert stage["failed_shell_calls"] == 1
    assert stage["outer_tool_calls"] == 2
    assert stage["outer_tool_calls_status"] == "observed"
    assert result["operation_totals"] == {
        "mcp_calls": 1, "shell_calls": 1, "file_change_calls": 1,
        "context_compactions": 0, "subagent_calls": 0, "failed_shell_calls": 1,
    }


def test_arm_cost_includes_failed_rows_and_retains_zero_success_and_missingness() -> None:
    rows = [
        {"run_id": "on-1", "usage_status": "known", "correct": True, "elapsed_ms": 100,
         "usage": {"uncachedInputTokens": 10, "cachedInputTokens": 2, "outputTokens": 3}},
        {"run_id": "on-2", "usage_status": "known", "correct": False, "elapsed_ms": 900,
         "usage": {"uncachedInputTokens": 90, "cachedInputTokens": 8, "outputTokens": 7}},
    ]
    result = arm_cost(rows, alpha=0.5, beta=2, expected_run_ids=["on-1", "on-2"])
    assert result == {
        "status": "known", "scheduled": 2, "correct": 1,
        "uncached_input": 100, "cached_input": 10, "output": 10,
        "elapsed_ms": 1000, "normalized_cost": 125.0,
        "elapsed_per_correct": 1000.0, "cost_per_correct": 125.0,
    }

    zero_success = arm_cost([{**rows[1], "correct": False}], alpha=1, beta=1, expected_run_ids=["on-2"])
    assert zero_success["status"] == "known"
    assert zero_success["correct"] == 0
    assert math.isinf(zero_success["elapsed_per_correct"])
    assert math.isinf(zero_success["cost_per_correct"])

    assert arm_cost([{**rows[0], "usage_status": "unknown"}], alpha=1, beta=1, expected_run_ids=["on-2"]) == {"status": "unproven"}
    assert arm_cost([{**rows[0], "correct": None}], alpha=1, beta=1, expected_run_ids=["on-2"]) == {"status": "unproven"}


def test_arm_cost_rejects_missing_duplicate_and_unexpected_scheduled_rows() -> None:
    row = {"run_id": "one", "usage_status": "known", "correct": True, "elapsed_ms": 100,
           "usage": {"uncachedInputTokens": 10, "cachedInputTokens": 2, "outputTokens": 3}}
    for rows, expected in [([row], ["one", "two"]), ([row, row], ["one"]), ([row], ["other"])]:
        assert arm_cost(rows, 0, 1, expected_run_ids=expected) == {"status": "unproven"}


def test_raw_response_completions_are_deduplicated_lower_bound_and_downstream_usage(tmp_path: Path) -> None:
    upstream = {"direction": "received", "message": {"method": "rawResponse/completed", "params": {
        "threadId": THREAD, "turnId": "turn-2", "responseId": "response-1",
    }}}
    result = _summarize(tmp_path, [
        _usage("turn-1", 100, 20, 10), _usage("turn-2", 150, 40, 15),
        _usage("turn-3", 200, 60, 20), upstream, upstream,
    ])
    stage = result["stages"][1]
    assert stage["observed_completed_model_requests"] == 1
    assert stage["model_requests"] is None
    assert stage["model_requests_status"] == "completion_lower_bound"
    assert result["phase_groups"]["downstream"]["usage"]["inputTokens"] == 100
    assert result["phase_groups"]["downstream"]["usage"]["cachedInputTokens"] == 40


def test_interruption_retains_partial_usage_without_claiming_a_complete_total(tmp_path: Path) -> None:
    result = _summarize(tmp_path, [_usage("turn-1", 100, 20, 10)],
                        _stages("timed_out", "not_reached", "not_reached"))
    assert result["usage_status"] == "unknown"
    assert result["usage"] is None
    assert result["observed_cumulative_usage"]["inputTokens"] == 100
    assert result["stages"][0]["observed_usage_delta"]["inputTokens"] == 100
    assert result["phase_groups"]["downstream"]["elapsed_ms"] is None
