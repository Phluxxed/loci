from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from benchmarks import multilingual_context_compare as runner


def _corpus() -> dict:
    return {
        "version": "multilingual-context-v1",
        "cases": [{"id": f"case_{number}", "snapshot": f"snapshot_{number}", "prompt": f" task {number}"}
                  for number in range(19)],
    }


def _controls() -> dict:
    return {"agent": {"common_prompt": "common\n", "workflow_guide": "guide\n"}}


def _request(prompt: str, *, arm: str) -> dict:
    tools = [
        {"type": "namespace", "name": "mcp__evaluation", "tools": [{"name": "get"}]},
        {"type": "namespace", "name": "functions", "tools": [
            {"name": "list_mcp_resources"}, {"name": "list_mcp_resource_templates"}, {"name": "read_mcp_resource"},
        ]},
    ]
    if arm == "B":
        tools[0]["tools"].append({"name": "loci_explore"})
    return {
        "model": runner.MODEL, "reasoning": {"effort": runner.REASONING_EFFORT},
        "input": [{"type": "additional_tools", "tools": tools},
                  {"type": "message", "content": [{"type": "input_text", "text": prompt}]}],
    }


def test_schedule_is_fixed_serial_ab_ba_for_19_cases() -> None:
    plan = runner.schedule(_corpus())
    assert len(plan) == 114
    assert plan[:6] == [
        {"attempt_id": "case_0-r1-A", "case_id": "case_0", "snapshot": "snapshot_0", "repetition": 1, "arm": "A"},
        {"attempt_id": "case_0-r1-B", "case_id": "case_0", "snapshot": "snapshot_0", "repetition": 1, "arm": "B"},
        {"attempt_id": "case_0-r2-B", "case_id": "case_0", "snapshot": "snapshot_0", "repetition": 2, "arm": "B"},
        {"attempt_id": "case_0-r2-A", "case_id": "case_0", "snapshot": "snapshot_0", "repetition": 2, "arm": "A"},
        {"attempt_id": "case_0-r3-A", "case_id": "case_0", "snapshot": "snapshot_0", "repetition": 3, "arm": "A"},
        {"attempt_id": "case_0-r3-B", "case_id": "case_0", "snapshot": "snapshot_0", "repetition": 3, "arm": "B"},
    ]
    assert len({item["attempt_id"] for item in plan}) == 114


def test_b_prompt_adds_only_frozen_guide() -> None:
    corpus, controls = _corpus(), _controls()
    assert runner.build_prompt(corpus, controls, "case_0", "A") == "common\n task 0"
    assert runner.build_prompt(corpus, controls, "case_0", "B") == "common\nguide\n task 0"


def test_request_audit_requires_arm_specific_workflow_surface() -> None:
    prompt = "common\n task"
    a = runner.audit_request(_request(prompt, arm="A"), prompt, "A")
    b = runner.audit_request(_request(prompt, arm="B"), prompt, "B")
    assert a["service_tier"] == "default"
    assert ("mcp__evaluation", "loci_explore") not in a["tools"]
    assert ("mcp__evaluation", "loci_explore") in b["tools"]
    with pytest.raises(ValueError, match="A unexpectedly"):
        runner.audit_request(_request(prompt, arm="B"), prompt, "A")


def test_settings_pins_default_tier_without_overriding_reserved_builtin_provider(tmp_path: Path) -> None:
    value = runner.settings(tmp_path / "run.json", tmp_path / "catalog.json", tmp_path / "store")
    assert value["service_tier"] == "default"
    assert "model_providers.openai.request_max_retries" not in value
    assert "model_providers.openai.stream_max_retries" not in value
    assert value["mcp_servers.evaluation.args"] == ["-m", runner.TOOLS_MODULE, str(tmp_path / "run.json")]


def test_validate_freeze_rejects_uncommitted_or_mismatched_controls(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = tmp_path / "inputs"
    root.mkdir()
    corpus = _corpus() | {"_root": str(root)}
    controls = _controls()
    corpus_bytes = b'{"frozen":true}'
    controls_bytes = b'{"controls":true}'
    (root / "corpus.json").write_bytes(corpus_bytes)
    (root / "comparison-controls.json").write_bytes(controls_bytes)
    freeze = tmp_path / "freeze.json"
    freeze.write_text(json.dumps({
        "version": runner.COMPARISON, "plan": runner.schedule(corpus), "model": runner.MODEL,
        "reasoning_effort": runner.REASONING_EFFORT, "service_tier": "default",
        "request_max_retries": runner.REQUEST_MAX_RETRIES, "stream_max_retries": runner.STREAM_MAX_RETRIES,
        "corpus_sha256": hashlib.sha256(corpus_bytes).hexdigest(),
        "controls_sha256": hashlib.sha256(controls_bytes).hexdigest(),
        "workflow_guide_sha256": hashlib.sha256(b"guide\n").hexdigest(),
    }))
    monkeypatch.setattr(runner, "ROOT", tmp_path)
    with pytest.raises(ValueError, match="freeze identity"):
        runner._validate_freeze(corpus, controls, freeze)
