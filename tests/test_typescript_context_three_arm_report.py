from __future__ import annotations

import json
from pathlib import Path

import pytest

from benchmarks.typescript_context_compare_report import evaluate as evaluate_frozen_pair
from benchmarks.typescript_context_three_arm_report import (
    EXPECTED_RUNS,
    evaluate_three_arm,
    generate_report,
)


ROOT = Path(__file__).parents[1]
CORPUS_ROOT = ROOT / "benchmarks" / "corpora" / "typescript-context-v3"


def _controls_and_cases() -> tuple[dict, list[dict]]:
    corpus = json.loads((CORPUS_ROOT / "corpus.json").read_text(encoding="utf-8"))
    controls = json.loads((CORPUS_ROOT / "comparison-controls.json").read_text(encoding="utf-8"))
    return controls, corpus["cases"]


def _runs() -> tuple[list[dict], dict]:
    controls, cases = _controls_and_cases()
    calls = {"A": 10, "B": 8, "C": 7}
    runs = []
    for case in cases:
        for repetition in range(1, 4):
            for arm in ("A", "B", "C"):
                count = calls[arm]
                runs.append({
                    "task_id": case["id"],
                    "group": case["group"],
                    "arm": arm,
                    "repetition": repetition,
                    "answer_correct": True,
                    "task_correct": True,
                    "measurement_complete": True,
                    "outcome": "completed",
                    "failures": [],
                    "read_count": count,
                    "validated_read_count": count,
                    "context_recall": 1.0,
                    "serialized_tool_output_bytes": count * 1000,
                    "source_bytes": 1000,
                    "unique_source_bytes": 900,
                    "duplicate_source_bytes": 100,
                    "recorded_payload_bytes": 10000,
                    "input_tokens": count * 1000,
                    "cached_input_tokens": 100,
                    "output_tokens": 100,
                    "end_to_end_seconds": 20,
                    "index_seconds": 1,
                    "relationships": {
                        "required_semantic_dependencies_total": 1,
                        "available_dependency_links_total": 1,
                        "delivered_dependency_links_total": 1,
                        "forbidden_proven_relationships": 0,
                    },
                })
    return runs, controls


def test_three_arm_relabels_actual_arms_and_keeps_pair_semantics() -> None:
    runs, controls = _runs()
    result = evaluate_three_arm(runs, controls, endpoints_available=True)

    c_over_b = result["comparisons"]["C/B"]
    assert set(c_over_b["arms"]) == {"B", "C"}
    assert c_over_b["sum_of_eligible_median_calls"] == {"B": 24, "C": 21}
    assert c_over_b["verdict"] == "reject"  # 12.5% is below the frozen 20% rule.
    assert result["comparisons"]["C/A"]["verdict"] == "keep"
    assert result["candidate_verdict"] == "keep"
    assert result["all_pairs_verdict"] == "reject"
    assert result["new_semantics"]["benefit_proven"] is False


def test_b_over_a_pair_is_identical_to_the_frozen_pair_evaluator() -> None:
    runs, controls = _runs()
    result = evaluate_three_arm(runs, controls, endpoints_available=True)
    expected = evaluate_frozen_pair(
        [run for run in runs if run["arm"] in {"A", "B"}],
        controls,
        endpoints_available=True,
    )

    assert result["comparisons"]["B/A"] == expected


def test_missing_provider_usage_is_inconclusive() -> None:
    runs, controls = _runs()
    selected = next(run for run in runs if run["arm"] == "C" and run["group"] == "maintained_task")
    selected["input_tokens"] = None

    result = evaluate_three_arm(runs, controls, endpoints_available=True)

    assert result["comparisons"]["C/B"]["verdict"] == "inconclusive"
    assert "input_tokens" in result["comparisons"]["C/B"]["unknown_gates"]
    assert result["candidate_verdict"] == "inconclusive"
    assert result["all_pairs_verdict"] == "inconclusive"


def test_c_can_remain_a_final_candidate_when_b_is_rejected() -> None:
    runs, controls = _runs()
    for run in runs:
        if run["arm"] == "B":
            run["read_count"] = 10
            run["validated_read_count"] = 10
            run["serialized_tool_output_bytes"] = 10000
            run["input_tokens"] = 10001

    result = evaluate_three_arm(runs, controls, endpoints_available=True)

    assert result["comparisons"]["B/A"]["verdict"] == "reject"
    assert result["comparisons"]["C/A"]["verdict"] == "keep"
    assert result["comparisons"]["C/B"]["verdict"] == "keep"
    assert result["candidate_verdict"] == "keep"
    assert result["new_semantics"]["benefit_proven"] is True


def test_generate_report_rejects_an_incomplete_153_identity_set(tmp_path: Path) -> None:
    _, cases = _controls_and_cases()
    expected = [
        f"{case['id']}-r{repetition}-{arm}"
        for case in cases
        for repetition in range(1, 4)
        for arm in ("A", "B", "C")
    ]
    assert len(expected) == EXPECTED_RUNS
    for name in expected[:-1]:
        folder = tmp_path / name
        folder.mkdir()
        (folder / "result.json").write_text("{}", encoding="utf-8")

    with pytest.raises(ValueError, match="exact 153"):
        generate_report(tmp_path, CORPUS_ROOT, tmp_path / "comparison")


def test_preflight_is_checked_for_the_candidate_arm() -> None:
    runs, controls = _runs()
    cases = controls["case_ids"]

    def payload(status: str) -> dict:
        return {
            "cases": [
                {"id": case_id, "endpoints": [{"status": status}]}
                for case_id in cases
            ]
        }

    preflight = {
        "arms": {
            "A": payload("indexed"),
            "B": payload("indexed"),
            "C": payload("source_only"),
        }
    }
    result = evaluate_three_arm(runs, controls, preflight=preflight)

    assert result["endpoint_availability"] == {"A": True, "B": True, "C": True}
    assert result["comparisons"]["C/B"]["verdict"] == "reject"


def test_generate_report_preserves_metrics_failures_and_preflight(tmp_path: Path) -> None:
    runs, controls = _runs()
    output = tmp_path / "results"
    output.mkdir()
    for position, run in enumerate(runs):
        folder = output / f"{run['task_id']}-r{run['repetition']}-{run['arm']}"
        folder.mkdir()
        failure = [{"category": "bounded_error", "message": "retained"}] if position == 0 else []
        measurement = {
            key: value
            for key, value in run.items()
            if key not in {"group", "directory", "failures", "relationships", "end_to_end_seconds", "index_seconds"}
        }
        measurement["provider_usage"] = {
            "input_tokens": run["input_tokens"],
            "cached_input_tokens": run["cached_input_tokens"],
            "output_tokens": run["output_tokens"],
        }
        result = {
            "identity": {
                "task_id": run["task_id"],
                "repetition": run["repetition"],
                "arm": run["arm"],
            },
            "measurement": measurement,
            "baseline": {
                "end_to_end_seconds": run["end_to_end_seconds"],
                "failures": failure,
                "relationships": run["relationships"],
                "output_accounting": {"recorded_payload_bytes": run["recorded_payload_bytes"]},
            },
            "events": [{"spans": [{"file": "source.ts", "start_byte": 0, "end_byte": 10}]}],
        }
        (folder / "result.json").write_text(json.dumps(result), encoding="utf-8")
        (folder / "provenance.json").write_text(
            json.dumps({"index_seconds": run["index_seconds"]}), encoding="utf-8"
        )

    comparison = tmp_path / "comparison"
    comparison.mkdir()
    (comparison / "preflight.json").write_text(json.dumps({
        "arms": {
            arm: {
                "cases": [
                    {"id": case_id, "endpoints": [{"status": "indexed"}]}
                    for case_id in controls["case_ids"]
                ]
            }
            for arm in ("A", "B", "C")
        }
    }), encoding="utf-8")

    summary = generate_report(output, CORPUS_ROOT, comparison)

    assert summary["recorded_runs"] == EXPECTED_RUNS
    assert summary["candidate_verdict"] == "keep"
    assert summary["arms"]["C"]["read_count"]["sum"] == 357
    assert summary["runs"][0]["failures"] == [{"category": "bounded_error", "message": "retained"}]
    assert (output / "report-summary.json").is_file()
    assert "bounded_error" in (output / "report.md").read_text(encoding="utf-8")
