from __future__ import annotations

from pathlib import Path

from benchmarks import multilingual_context_report as report


def _controls() -> dict:
    return {
        "case_ids": ["case_a", "case_b"],
        "acceptance": {
            "tool_calls_relative_reduction_min": .2,
            "minimum_tasks_with_one_fewer_median_tool_call": 1,
            "median_sum_output_bytes_ratio_max": 1.0,
            "median_sum_gross_input_tokens_ratio_max": 1.0,
            "p95_latency_ratio_max": 1.25,
            "p95_method": "nearest_rank",
        },
    }


def _run(case: str, arm: str, rep: int, *, calls: int, answer: bool = True) -> dict:
    return {
        "directory": f"{case}-r{rep}-{arm}", "task_id": case, "arm": arm, "repetition": rep,
        "group": "language_fixture", "language": "python_synthetic", "recorded": True,
        "evidence_complete": True, "provider_usage_complete": True, "answer_correct": answer,
        "full_pass": answer, "context_recall": 1, "read_count": calls,
        "serialized_tool_output_bytes": 10, "source_bytes": 8, "input_tokens": 20,
        "cached_input_tokens": 3, "output_tokens": 4, "end_to_end_seconds": 1,
        "relationships": {"required_semantic_dependencies_total": 1,
                          "delivered_dependency_links_total": 1,
                          "forbidden_proven_relationships": 0}, "failures": [],
    }


def _replay(runs: list[dict]) -> dict:
    return {"comparison": report.COMPARISON, "complete": True, "verified_runs": len(runs), "failures": [],
            "attempts": [{"attempt_id": run["directory"], "verified": True} for run in runs]}


def test_evaluate_requires_replay_and_applies_case_median_efficiency_gates() -> None:
    runs = []
    for case in _controls()["case_ids"]:
        for rep in range(1, 4):
            runs.extend((_run(case, "A", rep, calls=5), _run(case, "B", rep, calls=3)))
    value = report.evaluate(runs, _controls(), _replay(runs))
    gates = {item["name"]: item for item in value["gates"]}
    assert gates["every_B_full_pass"]["passed"] is True
    assert gates["median_call_reduction"]["passed"] is True
    assert gates["nearest_rank_p95_latency"]["passed"] is True


def test_evaluate_marks_missing_raw_or_replay_inconclusive() -> None:
    run = _run("case_a", "A", 1, calls=5)
    run["evidence_complete"] = False
    value = report.evaluate([run], _controls(), None)
    gates = {item["name"]: item for item in value["gates"]}
    assert gates["complete_raw_usage_and_replay"]["passed"] is None
    assert gates["every_B_full_pass"]["passed"] is None
    assert value["verdict"] == "inconclusive"


def test_attempt_status_distinguishes_model_answer_limitation() -> None:
    assert report._attempt_status({"evidence_complete": True, "model_answer_with_correct_source": True}) == (
        "model_limitation_wrong_answer_correct_source"
    )


def test_incomplete_source_coverage_is_quality_failure_not_trust_defect() -> None:
    assert report._has_trust_defect({"forbidden_proven_relationships": 0}, []) is False
    assert report._has_trust_defect({"forbidden_proven_relationships": 1}, []) is True
    assert report._attempt_status({"trust_defect": True, "evidence_complete": False}) == "withheld_trust_defect"


def test_language_efficiency_gate_cannot_be_hidden_by_global_reduction() -> None:
    controls = _controls()
    runs = []
    for case, a_calls, b_calls, language in (("case_a", 10, 5, "javascript"), ("case_b", 5, 5, "go")):
        for rep in range(1, 4):
            a, b = _run(case, "A", rep, calls=a_calls), _run(case, "B", rep, calls=b_calls)
            a["language"] = b["language"] = language
            runs.extend((a, b))
    global_result = report.evaluate(runs, controls, _replay(runs))
    by_language = report._language_dispositions(runs, controls, _replay(runs))
    assert global_result["verdict"] == "workflow_supported"
    assert by_language["go"]["efficiency_disposition"] == "unproven"


def test_generate_report_emits_all_planned_missing_slots(tmp_path: Path, monkeypatch) -> None:
    cases = [{"id": f"case_{number}", "snapshot": str(number), "prompt": "", "group": "language_fixture"}
             for number in range(19)]
    corpus = {"version": "multilingual-context-v1", "cases": cases}
    controls = _controls() | {"case_ids": [case["id"] for case in cases]}
    monkeypatch.setattr(report, "load_inputs", lambda: (corpus, controls))
    result = report.generate_report(tmp_path)
    assert result["recorded_runs"] == 0
    assert len(result["runs"]) == 114
    assert "All 114 planned attempts" in (tmp_path / "report.md").read_text()
