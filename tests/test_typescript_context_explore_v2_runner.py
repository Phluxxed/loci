from __future__ import annotations

import json

import pytest

from benchmarks import typescript_context_compare as prior
from benchmarks import typescript_context_explore_v2 as runner
from benchmarks.typescript_context_corpus import load_corpus
from benchmarks.typescript_context_explore_v2_observed import measure as v2_measure


@pytest.mark.parametrize("fail", [False, True])
def test_v2_run_attempt_injects_measure_and_restores_scoped_overrides(
    monkeypatch, tmp_path, fail
):
    """The v2 wrapper uses the corrected measure and restores shared state."""
    monkeypatch.setattr(runner, "verify_engine", lambda _: None)
    modules, source_provenance = prior.ARM_MODULES, prior._source_provenance
    freeze = {
        "engine": {"commit": "engine", "source_tree": "tree", "extractor_version": 25},
        "freeze_commit": "harness",
        "freeze_json_sha256": "freeze",
        "canonical_tool_schemas_sha256": {"A": "schema-a", "B": "schema-b"},
    }

    def lifecycle(**kwargs):
        assert prior.ARM_MODULES == {"A": runner.TOOLS_MODULE, "B": runner.TOOLS_MODULE}
        assert kwargs["measure"] is v2_measure
        assert kwargs["expected_schema_hash"] == "schema-b"
        assert prior._source_provenance({}, {})["engine"] == freeze["engine"]
        if fail:
            raise ValueError("retained failure")
        return {"worked": True}

    monkeypatch.setattr(prior, "_run_attempt", lifecycle)
    if fail:
        with pytest.raises(ValueError, match="retained failure"):
            runner.run_attempt({}, {}, {"arm": "B"}, tmp_path, tmp_path / "catalog", freeze)
    else:
        assert runner.run_attempt(
            {}, {}, {"arm": "B"}, tmp_path, tmp_path / "catalog", freeze
        ) == {"worked": True}
    assert prior.ARM_MODULES is modules and prior._source_provenance is source_provenance


@pytest.mark.parametrize("replay_fails", [False, True])
def test_v2_batch_replays_before_report_and_fails_closed_on_replay_error(
    monkeypatch, tmp_path, replay_fails
):
    from benchmarks import typescript_context_explore_v2_replay as replay
    from benchmarks import typescript_context_explore_v2_report as report

    corpus = load_corpus(runner.CORPUS_ROOT)
    freeze = {
        "plan": runner.schedule(corpus),
        "canonical_tool_schemas_sha256": {"A": "a", "B": "b"},
    }
    protocol = tmp_path / "protocol"
    protocol.mkdir()
    for name in ("model-catalog.json", "model-catalog-provenance.json"):
        (protocol / name).write_text("{}")
    monkeypatch.setattr(runner, "COMPARISON_ROOT", protocol)
    monkeypatch.setattr(runner, "validate_freeze", lambda _: freeze)
    monkeypatch.setattr(runner, "environment", lambda _: {})
    monkeypatch.setattr(runner, "command", lambda _: "codex-cli 0.154.0")
    order = []

    def attempt(*args):
        order.append("attempt")
        return {
            "measurement": {
                "task_correct": True,
                "read_count": 1,
                "outcome": "completed",
                "measurement_complete": True,
            }
        }

    def verify(output):
        assert order == ["attempt"] * 102
        order.append("replay")
        # A failed fresh replay must override even a stale successful status.
        runner.save(
            output / "replay-verification.json",
            {"complete": True, "comparison": runner.COMPARISON},
        )
        if replay_fails:
            raise ValueError("independent replay failed")
        return {"complete": True}

    def generate(output, *_):
        assert order[-1] == "replay"
        assert not (output / "completion.json").exists()
        order.append("report")
        complete = json.loads((output / "replay-verification.json").read_text())["complete"]
        return {
            "replay_complete": complete,
            "verdict": "keep",
            "qualification_verdict": "keep" if complete else "inconclusive",
        }

    monkeypatch.setattr(runner, "run_attempt", attempt)
    monkeypatch.setattr(replay, "verify", verify)
    monkeypatch.setattr(report, "generate_report", generate)
    output = tmp_path / "results"
    runner.run_batch(protocol / "freeze.json", output)
    completion = json.loads((output / "completion.json").read_text())
    assert completion["replay_complete"] is not replay_fails
    assert completion["verdict"] == ("inconclusive" if replay_fails else "keep")
    assert order[-2:] == ["replay", "report"]
