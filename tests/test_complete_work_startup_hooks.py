"""Regression for the observed native bootstrap ordering; never launch a host."""
from copy import deepcopy
import json
from pathlib import Path

import pytest

from benchmarks.complete_work import availability, r0, r1
from benchmarks.complete_work.evaluate import write_json
from tests.test_complete_work_availability import _trace, _write
from tests.test_complete_work_common_context import _rewrite_probe
from tests.test_complete_work_r1 import _freeze, _write_amendment
from tests.test_complete_work_r1_availability import _startup_rows, host_gate


def _hook(text="Common Code Mode instructions.", turn="turn"):
    # Actual failed trace row16: hooks.additional_context with harness hook=true.
    return {"type": "response_item", "payload": {
        "type": "message", "role": "developer", "id": "hook-envelope",
        "content": [{"type": "input_text", "text": text}],
        "internal_chat_message_metadata_passthrough": {
            "turn_id": turn, "create_time": 1793096371.949571,
            "content_item_kinds": ["hooks.additional_context"],
            "content_item_metadata": [{"provenance": {"type": "harness", "hook": True}}]}}}


def _rows(tmp_path):
    workspace, observer = tmp_path / "w", tmp_path / "o"
    _, rows, _, _, tools = _trace(tmp_path, (workspace, []), "native")
    return _startup_rows(rows, workspace, observer, "Task.", tools), workspace, observer


def _insert_hook(rows):
    index = next(i for i, row in enumerate(rows) if row.get("type") == "response_item"
                 and row["payload"].get("type") == "custom_tool_call")
    rows.insert(index, _hook())


def _audit(tmp_path, rows, workspace, observer):
    trace = tmp_path / "native.jsonl"
    _write(trace, rows)
    return availability.audit_common_context(trace, workspace, observer, "Task.", [])


def test_observed_post_prompt_pre_model_hook_is_compared_and_times_are_transport(tmp_path):
    rows, workspace, observer = _rows(tmp_path)
    _insert_hook(rows)
    for i, row in enumerate(rows):
        payload = row["payload"]
        if payload.get("type") == "message":
            payload.setdefault("internal_chat_message_metadata_passthrough", {})["create_time"] = 1793096371.0 + i
    first = _audit(tmp_path, rows, workspace, observer)
    changed = deepcopy(rows)
    for row in changed:
        meta = row["payload"].get("internal_chat_message_metadata_passthrough", {})
        if "create_time" in meta:
            meta["create_time"] += 10.125
    assert _audit(tmp_path, changed, workspace, observer)["common"] == first["common"]
    changed_hook = next(r["payload"] for r in changed if r["payload"].get("id") == "hook-envelope")
    changed_hook["content"][0]["text"] += " A changed instruction."
    assert _audit(tmp_path, changed, workspace, observer)["common_sha256"] != first["common_sha256"]


@pytest.mark.parametrize("mutation", ["untyped", "wrong_turn", "not_hook", "unaligned", "extra_user",
                                     "after_reasoning_event", "after_reasoning_start", "after_agent_event", "after_raw_reasoning",
                                     "after_assistant", "after_call", "nested_time"])
def test_hook_exception_keeps_provenance_and_execution_boundaries(tmp_path, mutation):
    rows, workspace, observer = _rows(tmp_path)
    _insert_hook(rows)
    index = next(i for i, r in enumerate(rows) if r["payload"].get("id") == "hook-envelope")
    payload = rows[index]["payload"]
    meta = payload["internal_chat_message_metadata_passthrough"]
    if mutation == "untyped":
        payload.pop("internal_chat_message_metadata_passthrough")
    elif mutation == "wrong_turn":
        meta["turn_id"] = "another-turn"
    elif mutation == "not_hook":
        meta["content_item_metadata"][0]["provenance"]["hook"] = False
    elif mutation == "unaligned":
        meta["content_item_kinds"].append("hooks.additional_context")
    elif mutation == "extra_user":
        payload["role"] = "user"
    elif mutation == "nested_time":
        meta["content_item_metadata"][0]["annotation"] = {"create_time": "semantic-metadata"}
        baseline = _audit(tmp_path, rows, workspace, observer)
        meta["content_item_metadata"][0]["annotation"]["create_time"] = "changed"
        assert _audit(tmp_path, rows, workspace, observer)["common"] != baseline["common"]
        return
    elif mutation in {"after_reasoning_event", "after_reasoning_start", "after_agent_event"}:
        rows.insert(index, {"type": "event_msg", "payload": {
                    "type": "item_started" if mutation == "after_reasoning_start" else "item_completed",
                    "item": {"type": "AgentMessage" if mutation == "after_agent_event" else "Reasoning"}}})
    elif mutation == "after_raw_reasoning":
        rows.insert(index, {"type": "response_item", "payload": {"type": "reasoning"}})
    elif mutation == "after_assistant":
        rows.insert(index, {"type": "response_item", "payload": {"type": "message", "role": "assistant"}})
    else:
        hook = rows.pop(index)
        rows.insert(index + 1, hook)
    with pytest.raises(ValueError, match="instruction update"):
        _audit(tmp_path, rows, workspace, observer)


@pytest.mark.parametrize("host_gate", [{"common_context": True}], indirect=True)
def test_hook_and_transport_handling_survive_four_probe_gate(host_gate):
    _, frozen, gate_path, gate, _ = host_gate
    for i, condition in enumerate(r1.CONDITIONS):
        def mutation(rows):
            _insert_hook(rows)
            for row in rows:
                if row["payload"].get("type") == "message":
                    row["payload"].setdefault("internal_chat_message_metadata_passthrough", {})["create_time"] = 1793096371.0 + i
        _rewrite_probe(gate, condition, mutation)
    write_json(gate_path, gate)
    assert len(r1.require_availability(frozen, gate_path)["threads"]) == 4


def test_only_pinned_availability_reader_can_be_explicitly_amended(tmp_path):
    path = _freeze(tmp_path, common_context=True)
    frozen = json.loads(path.read_text())
    reader = str(availability.__file__)
    frozen["host"]["orchestration_files"][reader] = "1" * 64
    frozen.pop("freeze_sha256")
    frozen["freeze_sha256"] = r1.identity(frozen)
    write_json(path, frozen)
    original = path.read_bytes()
    amendment = tmp_path / "amendment.json"
    _write_amendment(amendment, {
        "schema_version": 1, "kind": "r1-instrumentation-amendment",
        "freeze_sha256": frozen["freeze_sha256"],
        "changes": {reader: {"before_sha256": "1" * 64, "after_sha256": r0.digest(Path(reader))}}})
    assert r1.read_freeze(path, amendment=amendment) == frozen
    assert path.read_bytes() == original


def test_preflight_keeps_closed_thread_identity_when_later_qualification_fails(tmp_path, monkeypatch):
    path = _freeze(tmp_path, common_context=True)
    gate = tmp_path / "deterministic.json"
    write_json(gate, {"status": "passed"})
    calls = []
    def closed(config, gate, frozen, *, measured, amendment=None):
        assert not measured
        calls.append(config)
        result = {"status": "closed", "thread_id": "offline-closed-thread", "exit_code": 0, "measured": False}
        write_json(config.parent / "execution.json", result)
        return result
    monkeypatch.setattr(r1, "_execute_native", closed)
    result = r1.preflight(path, gate, tmp_path / "preflight")
    assert result["status"] == "failed" and len(calls) == 1
    assert result["probes"][0]["thread_id"] == "offline-closed-thread"
    assert "unique native availability rollout unavailable" in result["probes"][0]["error"]
