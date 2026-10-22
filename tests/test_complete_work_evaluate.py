"""Negative controls for evaluator-owned source readback, without a model."""
import copy
import json
from pathlib import Path

import pytest

from benchmarks.complete_work.controller import source_snapshot
from benchmarks.complete_work.evaluate import evaluate_episode, restore_snapshot, verify_snapshot
from benchmarks.complete_work.runtime import RuntimeFailure


def test_snapshot_rejects_changed_manifest_valid_blob_substitution_and_corrupt_blob(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    source = repo / "source.py"
    history = tmp_path / "history"
    source.write_text("old = 1\n")
    before = source_snapshot(repo, history)
    source.write_text("new = 2\n")
    after = source_snapshot(repo, history)
    restore_snapshot(before, history, tmp_path / "valid")
    assert (tmp_path / "valid/source.py").read_text() == "old = 1\n"

    changed = copy.deepcopy(before)
    changed["files"] = after["files"]
    with pytest.raises(RuntimeFailure, match="file map differs"):
        restore_snapshot(changed, history, tmp_path / "changed")
    assert not (tmp_path / "changed").exists()
    with pytest.raises(RuntimeFailure, match="captured stage identity"):
        verify_snapshot(after, before["sha256"])

    (history / "blobs" / before["files"]["source.py"]).write_bytes(b"corrupt")
    with pytest.raises(RuntimeFailure, match="source bytes differ"):
        restore_snapshot(before, history, tmp_path / "corrupt")


@pytest.mark.parametrize("corruption", ["manifest", "stage_identity"])
def test_episode_rejects_changed_source_before_running_oracle(tmp_path: Path, monkeypatch, corruption: str) -> None:
    from benchmarks.complete_work.oracles import anvil

    def forbidden(*args, **kwargs):
        pytest.fail("oracle must not grade a source version that failed readback validation")

    monkeypatch.setattr(anvil, "evaluate", forbidden)
    repo = tmp_path / "repo"
    repo.mkdir()
    source = repo / "source.py"
    source.write_text("before\n")
    output = tmp_path / "output"
    before = source_snapshot(repo, output / "source-history")
    source.write_text("after\n")
    after = source_snapshot(repo, output / "source-history")
    stage = {"stage_id": "implement", "outcome": "completed",
             "source_snapshot_sha256": before["sha256"]}
    if corruption == "manifest":
        after["sha256"] = before["sha256"]
    for name, value in {
        "result.json": {"run_id": "run", "measured": True, "episode_id": "anvil-creation-evidence", "stages": [stage]},
        "source-before.json": before, "source-after-implement.json": after,
    }.items():
        (output / name).write_text(json.dumps(value))
    config = tmp_path / "config.json"
    config.write_text(json.dumps({"run_id": "run", "output_dir": str(output), "repo": str(repo)}))
    with pytest.raises(RuntimeFailure, match="differs"):
        evaluate_episode(config)
    assert not (output / "evaluation/report.json").exists()
