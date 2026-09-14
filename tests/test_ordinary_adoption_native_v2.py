from __future__ import annotations

import json
from pathlib import Path

import pytest

from benchmarks.ordinary_adoption_native_v2 import NATIVE_ADAPTER_VERSION, observe_rollout
from benchmarks.ordinary_adoption_observed import ObservationError, observe_rollout as observe_v1


THREAD = "native-v2-thread"
TURN = "native-v2-turn"


def _metadata() -> dict[str, str]:
    return {"run_id": "native-v2", "purpose": "primary_check", "thread_id": THREAD, "turn_id": TURN, "target_repo": "/repo"}


def _mcp(result: dict, *, item_id: str = "mcp-1") -> dict:
    return {
        "type": "event_msg",
        "payload": {
            "type": "item_completed", "thread_id": THREAD, "turn_id": TURN,
            "started_at_ms": 1, "completed_at_ms": 2,
            "item": {
                "type": "McpToolCall", "id": item_id, "server": "anvil", "tool": "anvil_manifest_inquire",
                "arguments": {"repo": "/repo"}, "status": "completed", "duration": {"secs": 0, "nanos": 1}, "result": result,
            },
        },
    }


def _outer(result: dict) -> list[dict]:
    return [
        {"type": "response_item", "payload": {"type": "custom_tool_call", "id": "outer-request", "call_id": "outer", "name": "exec", "input": "call"}},
        {"type": "response_item", "payload": {"type": "custom_tool_call_output", "id": "outer-output", "call_id": "outer", "output": json.dumps({"result": result}, separators=(",", ":"))}},
    ]


def _write(tmp_path: Path, body: list[dict]) -> Path:
    records = [
        {"type": "session_meta", "payload": {"id": THREAD, "agent_path": "/root/test", "cwd": "/repo"}},
        {"type": "event_msg", "payload": {"type": "task_started", "turn_id": TURN}},
        {"type": "turn_context", "payload": {"turn_id": TURN, "root_turn_id": "root", "model": "gpt-6-astra", "effort": "ultra"}},
        *body,
        {"type": "event_msg", "payload": {"type": "item_completed", "item": {"type": "AgentMessage", "id": "final", "phase": "final", "content": []}}},
        {"type": "event_msg", "payload": {"type": "task_complete", "turn_id": TURN}},
    ]
    for ordinal, record in enumerate(records):
        record["ordinal"] = ordinal
    path = tmp_path / "rollout.jsonl"
    path.write_text("".join(json.dumps(record) + "\n" for record in records), encoding="utf-8")
    return path


def test_accepts_real_optional_is_error_shape_without_changing_raw_bytes_or_exact_delivery(tmp_path: Path) -> None:
    result = {
        "content": [{"type": "text", "text": "Manifest inquiry returned found."}],
        "structuredContent": {"result": {"outcome": "found"}},
    }
    observed = observe_rollout(_write(tmp_path, [_mcp(result), *_outer(result)]), _metadata())
    call = observed["mcp_calls"][0]

    assert NATIVE_ADAPTER_VERSION == "ordinary-adoption-native-v2"
    assert "isError" not in call["result"]
    assert call["relationship_delivery"]["application_error"] is False
    assert call["canonical_result_json_bytes"] == len(json.dumps(result, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8"))
    assert call["model_delivery"]["status"] == "full_exact"


def test_preserves_old_valid_captures_exactly(tmp_path: Path) -> None:
    result = {"content": [], "structuredContent": {"status": "ok"}, "isError": False}
    rollout = _write(tmp_path, [_mcp(result), *_outer(result)])
    assert observe_rollout(rollout, _metadata()) == observe_v1(rollout, _metadata())


@pytest.mark.parametrize("flag", [None, 0, "false", []])
def test_rejects_malformed_present_is_error(tmp_path: Path, flag: object) -> None:
    result = {"content": [], "structuredContent": {"status": "ok"}, "isError": flag}
    with pytest.raises(ObservationError, match="invalid native MCP result envelope"):
        observe_rollout(_write(tmp_path, [_mcp(result)]), _metadata())


def test_preserves_duplicate_and_missing_integrity_rejection(tmp_path: Path) -> None:
    result = {"content": [], "structuredContent": {"status": "ok"}}
    with pytest.raises(ObservationError, match="duplicate terminal id"):
        observe_rollout(_write(tmp_path, [_mcp(result), _mcp(result)]), _metadata())

    broken = _write(tmp_path, [_mcp(result, item_id="mcp-2")])
    records = broken.read_text(encoding="utf-8").splitlines()
    records[3] = records[3].replace('"result": {', '"unexpected": {')
    broken.write_text("\n".join(records) + "\n", encoding="utf-8")
    with pytest.raises(ObservationError, match="missing: result"):
        observe_rollout(broken, _metadata())
