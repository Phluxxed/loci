"""Focused checks for the post-measurement ABC artifact verifier."""

from __future__ import annotations

import json
from pathlib import Path
import shutil
import subprocess
import sys

from benchmarks.typescript_context_corpus import load_controls, load_corpus
from benchmarks.typescript_context_three_arm_replay import (
    CASE_COUNT,
    EXPECTED_RUNS,
    DEFAULT_CORPUS_ROOT,
    planned_attempts,
    verify,
)


def _copy_one_attempt(destination: Path) -> Path:
    source = next(Path("benchmarks/results/typescript-context-existing-v1").glob("*/result.json")).parent
    target = destination / source.name
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(source, target)
    return target


def test_planned_attempts_are_the_exact_frozen_153_identities() -> None:
    corpus = load_corpus(DEFAULT_CORPUS_ROOT)
    controls = load_controls(corpus)
    plan = planned_attempts(corpus, controls)

    assert len(corpus["cases"]) == CASE_COUNT
    assert len(plan) == EXPECTED_RUNS
    assert len({item["attempt_id"] for item in plan}) == EXPECTED_RUNS
    assert plan[0]["attempt_id"].endswith("-r1-A")
    assert plan[1]["attempt_id"].endswith("-r1-B")
    assert plan[2]["attempt_id"].endswith("-r1-C")


def test_incomplete_batch_is_rejected_without_rewriting_the_raw_record(tmp_path: Path) -> None:
    output = tmp_path / "results"
    attempt = _copy_one_attempt(output)
    raw_before = {
        name: (attempt / name).read_bytes()
        for name in ("adapter-trace.json", "events.jsonl", "result.json")
    }

    report = verify(output, DEFAULT_CORPUS_ROOT)

    assert report["passed"] is False
    assert report["recorded_count"] == 1
    assert any(item["category"] == "planned_identity_set_mismatch" for item in report["failures"])
    assert {
        name: (attempt / name).read_bytes()
        for name in raw_before
    } == raw_before


def test_tampered_identity_fails_while_trace_and_events_remain_unchanged(tmp_path: Path) -> None:
    output = tmp_path / "results"
    attempt = _copy_one_attempt(output)
    trace_before = (attempt / "adapter-trace.json").read_bytes()
    events_before = (attempt / "events.jsonl").read_bytes()
    result = json.loads((attempt / "result.json").read_text(encoding="utf-8"))
    result["identity"]["task_id"] = "tampered-task"
    (attempt / "result.json").write_text(json.dumps(result), encoding="utf-8")

    report = verify(output, DEFAULT_CORPUS_ROOT)

    assert report["passed"] is False
    assert any(item["category"] == "run_identity_mismatch" for item in report["failures"])
    assert (attempt / "adapter-trace.json").read_bytes() == trace_before
    assert (attempt / "events.jsonl").read_bytes() == events_before


def test_existing_raw_attempt_replays_without_an_engine_process(tmp_path: Path) -> None:
    output = tmp_path / "results"
    _copy_one_attempt(output)

    report = verify(output, DEFAULT_CORPUS_ROOT)

    assert report["replayed_count"] == 1
    assert report["reconciled_count"] == 1
    assert report["measurement_replayed_count"] == 1
    assert report["measurement_replay_skipped"] is True


def test_worker_cli_dispatches_without_parent_output(tmp_path: Path) -> None:
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "benchmarks.typescript_context_three_arm_replay",
            "--worker",
            "--engine-src",
            str(tmp_path),
        ],
        cwd=Path(__file__).resolve().parents[1],
        input="{}",
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 2
    assert json.loads(completed.stdout)["error"] == "ValueError: engine replay spec must contain an items list"
    assert "--output is required" not in completed.stderr
