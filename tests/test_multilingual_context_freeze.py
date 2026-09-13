"""Prevent changed preparation inputs from reaching the provider runner."""
import json

import pytest

from benchmarks import multilingual_context_freeze as freeze
from benchmarks.multilingual_context_compare import build_prompt, schedule
from benchmarks.typescript_context_baseline import sha


@pytest.fixture
def frozen(tmp_path, monkeypatch):
    corpus = {"version": "multilingual-context-v1", "_root": str(tmp_path),
              "cases": [{"id": f"case-{n}", "snapshot": f"snapshot-{n}", "prompt": "Read exact source."}
                        for n in range(19)]}
    controls = {"corpus_sha256": "corpus", "agent": {"common_prompt": "Common. ", "workflow_guide": "Guide. ",
                "model": "gpt-5.6-luna", "reasoning_effort": "high", "service_tier": "default",
                "request_max_retries": 0, "stream_max_retries": 0}}
    source = tmp_path / "proof.json"
    source.write_text('{"passed":true}\n')
    (tmp_path / "comparison-controls.json").write_text(json.dumps(controls))
    data = {"version": freeze.COMPARISON, "plan": schedule(corpus), "engine": {"exact": True},
            "harness_files": {}, "environment": {}, "freeze_commit": "preparation",
            "files": {"proof.json": sha(source.read_bytes())},
            "corpus_sha256": "corpus", "controls_sha256": sha((tmp_path / "comparison-controls.json").read_bytes()),
            "workflow_guide_sha256": sha(controls["agent"]["workflow_guide"].encode()),
            "prompt_sha256": {f"{c['id']}-{a}": sha(build_prompt(corpus, controls, c["id"], a).encode())
                              for c in corpus["cases"] for a in ("A", "B")},
            **{k: controls["agent"][k] for k in ("model", "reasoning_effort", "service_tier", "request_max_retries", "stream_max_retries")}}
    path = tmp_path / "freeze.json"
    path.write_text(json.dumps(data))
    saved = {"preparation:proof.json": source.read_bytes(), "HEAD:freeze.json": path.read_bytes()}
    monkeypatch.setattr(freeze, "ROOT", tmp_path)
    monkeypatch.setattr(freeze, "_input_identity", lambda: (corpus, controls))
    monkeypatch.setattr(freeze, "engine_identity", lambda: {"exact": True})
    monkeypatch.setattr(freeze, "harness_files", lambda: {})
    monkeypatch.setattr(freeze, "environment_identity", lambda: {})
    monkeypatch.setattr(freeze, "git", lambda *args: "")
    monkeypatch.setattr(freeze.subprocess, "check_output", lambda args, **kwargs: saved[args[2]])
    return path, source, data, saved


def test_exact_committed_declaration_passes(frozen):
    path, _, _, _ = frozen
    assert len(freeze.validate_freeze(path, require_published=False)["plan"]) == 114


def test_modified_proof_cannot_launch(frozen):
    path, source, _, _ = frozen
    source.write_text('{"passed":false}\n')
    with pytest.raises(ValueError, match="frozen input changed"):
        freeze.validate_freeze(path, require_published=False)


def test_retouched_proof_and_freeze_cannot_hide_commit_mismatch(frozen):
    path, source, data, _ = frozen
    source.write_text('{"passed":false}\n')
    data["files"]["proof.json"] = sha(source.read_bytes())
    path.write_text(json.dumps(data))
    with pytest.raises(ValueError, match="preparation commit"):
        freeze.validate_freeze(path, require_published=False)


def test_changed_task_prompt_cannot_launch(frozen):
    path, _, data, _ = frozen
    data["prompt_sha256"]["case-0-B"] = "changed"
    path.write_text(json.dumps(data))
    with pytest.raises(ValueError, match="frozen prompt changed"):
        freeze.validate_freeze(path, require_published=False)
