import json
from pathlib import Path

from benchmarks.typescript_context_compare_report import evaluate


def examples():
    root = Path(__file__).parents[1] / "benchmarks/corpora/typescript-context-v3"
    corpus = json.loads((root / "corpus.json").read_text())
    controls = json.loads((root / "comparison-controls.json").read_text())
    runs = []
    for case in corpus["cases"]:
        for repetition in range(3):
            for arm in ("A", "B"):
                runs.append({"task_id": case["id"], "group": case["group"], "arm": arm,
                             "repetition": repetition, "answer_correct": True, "task_correct": True,
                             "measurement_complete": True, "outcome": "completed", "failures": [],
                             "read_count": 10 if arm == "A" else 8, "context_recall": 1.0,
                             "serialized_tool_output_bytes": 10000 if arm == "A" else 9000,
                             "input_tokens": 10000 if arm == "A" else 9000, "end_to_end_seconds": 20,
                             "relationships": {"required_semantic_dependencies_total": 1,
                                               "available_dependency_links_total": 1,
                                               "delivered_dependency_links_total": 1,
                                               "forbidden_proven_relationships": 0}})
    return runs, controls


def test_exact_twenty_percent_reduction_and_all_gates_keep():
    runs, controls = examples()
    result = evaluate(runs, controls, endpoints_available=True)
    assert result["sum_of_eligible_median_calls"] == {"A": 30, "B": 24}
    assert len(result["eligible_maintained_tasks"]) == 3
    assert result["verdict"] == "keep"
    assert not result["failed_gates"] and not result["unknown_gates"]


def test_more_provider_input_rejects_even_when_calls_improve():
    runs, controls = examples()
    for run in runs:
        if run["arm"] == "B":
            run["input_tokens"] = 10001
    result = evaluate(runs, controls, endpoints_available=True)
    assert result["verdict"] == "reject"
    assert result["failed_gates"] == ["input_tokens"]


def test_missing_measurements_remain_inconclusive_and_do_not_become_zero():
    runs, controls = examples()
    selected = next(run for run in runs if run["arm"] == "B" and run["group"] == "maintained_task")
    selected["input_tokens"] = None
    selected["measurement_complete"] = selected["task_correct"] = False
    result = evaluate(runs, controls, endpoints_available=True)
    assert result["verdict"] == "inconclusive"
    gate = next(item for item in result["gates"] if item["name"] == "input_tokens")
    assert gate["actual"]["sums_of_task_medians"]["B"] is None
    assert gate["passed"] is None


def test_latency_and_source_recall_include_unsuccessful_attempts():
    runs, controls = examples()
    selected = [run for run in runs if run["arm"] == "B" and run["group"] == "maintained_task"]
    selected[0]["task_correct"] = False
    selected[0]["end_to_end_seconds"] = 100
    selected[0]["context_recall"] = selected[1]["context_recall"] = 0.5
    result = evaluate(runs, controls, endpoints_available=True)
    assert result["maintained_p95_seconds"] == {"A": 20, "B": 100}
    assert "maintained_p95_latency" in result["failed_gates"]
    assert "per_task_source_recall" in result["failed_gates"]
    assert len(result["eligible_maintained_tasks"]) == 2


def test_false_relationship_and_missing_endpoint_gates_are_not_offset_by_savings():
    runs, controls = examples()
    selected = next(run for run in runs if run["arm"] == "B")
    selected["relationships"]["forbidden_proven_relationships"] = 1
    result = evaluate(runs, controls, endpoints_available=False)
    assert result["verdict"] == "reject"
    assert {"authored_false_relationships", "repaired_endpoints"} <= set(result["failed_gates"])
