"""Apply the frozen v3 gates to the complete matched existing-edge A/B batch."""

from __future__ import annotations

import argparse
import json
import math
from collections import Counter
from pathlib import Path

from benchmarks.typescript_context_baseline import save
from benchmarks.typescript_context_corpus import load_controls, load_corpus
from benchmarks.typescript_context_report_v3 import metric, source_occurrences


_METRICS = (
    "read_count", "validated_read_count", "context_recall", "serialized_tool_output_bytes",
    "source_bytes", "unique_source_bytes", "duplicate_source_bytes", "recorded_payload_bytes",
    "input_tokens", "cached_input_tokens", "output_tokens", "end_to_end_seconds", "index_seconds",
)
_RELATIONSHIPS = (
    "required_semantic_dependencies_total", "available_dependency_links_total",
    "delivered_dependency_links_total", "forbidden_proven_relationships",
)


def summarize(runs: list[dict]) -> dict:
    return {
        "runs": len(runs),
        "answers_correct": sum(bool(run.get("answer_correct")) for run in runs),
        "fully_successful": sum(bool(run.get("task_correct")) for run in runs),
        "measurement_complete": sum(bool(run.get("measurement_complete")) for run in runs),
        "outcomes": dict(Counter(run.get("outcome", "unknown") for run in runs)),
        "failure_events": dict(Counter(failure["category"] for run in runs for failure in run["failures"])),
        **{name: metric([run.get(name) for run in runs]) for name in _METRICS},
        "relationships": {name: metric([run.get("relationships", {}).get(name) for run in runs])["sum"]
                          for name in _RELATIONSHIPS},
    }


def evaluate(runs: list[dict], controls: dict, *, endpoints_available: bool | None) -> dict:
    thresholds = controls["acceptance"]
    arms = {arm: summarize([run for run in runs if run["arm"] == arm]) for arm in ("A", "B")}
    case_ids = controls["case_ids"]
    per_task = {arm: {case: summarize([run for run in runs if run["arm"] == arm and run["task_id"] == case])
                      for case in case_ids} for arm in arms}
    maintained = list(dict.fromkeys(run["task_id"] for run in runs if run["group"] == "maintained_task"))
    eligible = [case for case in maintained
                if all(per_task[arm][case]["fully_successful"] == 3 for arm in arms)]
    sums = {arm: sum(per_task[arm][case]["read_count"]["median"] for case in eligible) for arm in arms}
    fewer = [case for case in eligible if per_task["A"][case]["read_count"]["median"]
             - per_task["B"][case]["read_count"]["median"] >= 1]
    p95 = {}
    for arm in arms:
        times = [run.get("end_to_end_seconds") for run in runs
                 if run["arm"] == arm and run["group"] == "maintained_task"]
        p95[arm] = (sorted(times)[math.ceil(.95 * len(times)) - 1]
                    if len(times) == 9 and all(value is not None for value in times) else None)
    gates = []

    def gate(name, passed, actual, required):
        gates.append({"name": name, "passed": passed, "actual": actual, "required": required})

    gate("complete_measurements", all(arms[arm]["measurement_complete"] == 51 for arm in arms),
         {arm: arms[arm]["measurement_complete"] for arm in arms}, {"A": 51, "B": 51})
    fixture_passes = sum(bool(run.get("task_correct")) for run in runs
                         if run["arm"] == "B" and run["group"] != "maintained_task")
    gate("fixture_full_passes", fixture_passes == thresholds["fixture_correct_answers_required"],
         fixture_passes, thresholds["fixture_correct_answers_required"])
    forbidden = arms["B"]["relationships"]["forbidden_proven_relationships"]
    gate("authored_false_relationships", forbidden == 0 if forbidden is not None else None, forbidden, 0)
    gate("repaired_endpoints", endpoints_available, endpoints_available, True)
    maintained_passes = sum(bool(run.get("task_correct")) for run in runs
                            if run["arm"] == "B" and run["group"] == "maintained_task")
    gate("maintained_full_passes", maintained_passes >= thresholds["maintained_correct_answers_min"],
         maintained_passes, thresholds["maintained_correct_answers_min"])
    regressions = [case for case in case_ids
                   if per_task["B"][case]["fully_successful"] < per_task["A"][case]["fully_successful"]]
    gate("per_task_success", not regressions, regressions, [])
    gate("eligible_paired_tasks", len(eligible) >= thresholds["minimum_fully_successful_paired_tasks"],
         len(eligible), thresholds["minimum_fully_successful_paired_tasks"])
    gate("positive_comparator", sums["A"] > 0, sums["A"], "> 0")
    reduction = 1 - sums["B"] / sums["A"] if sums["A"] > 0 else None
    gate("observed_call_reduction", sums["B"] <= sums["A"] * (1 - thresholds["tool_calls_relative_reduction_min"])
         if sums["A"] > 0 else None, reduction, thresholds["tool_calls_relative_reduction_min"])
    gate("tasks_with_fewer_calls", len(fewer) >= thresholds["minimum_tasks_with_one_fewer_median_tool_call"],
         fewer, thresholds["minimum_tasks_with_one_fewer_median_tool_call"])
    recalls = {arm: {case: per_task[arm][case]["context_recall"]["median"] for case in maintained} for arm in arms}
    known_recall = all(value is not None for values in recalls.values() for value in values.values())
    gate("per_task_source_recall", all(recalls["B"][case] >= recalls["A"][case] for case in maintained)
         if known_recall else None, recalls, "B median >= A median for each maintained task")
    for name, threshold in (("serialized_tool_output_bytes", "median_sum_output_bytes_ratio_max"),
                            ("input_tokens", "median_sum_gross_input_tokens_ratio_max")):
        medians = {arm: [per_task[arm][case][name]["median"] for case in maintained] for arm in arms}
        totals = {arm: sum(values) if all(value is not None for value in values) else None
                  for arm, values in medians.items()}
        ratio = (totals["B"] / totals["A"] if totals["B"] is not None
                 and totals["A"] is not None and totals["A"] > 0 else None)
        gate(name, ratio <= thresholds[threshold] if ratio is not None else None,
             {"sums_of_task_medians": totals, "ratio": ratio}, thresholds[threshold])
    latency_ratio = p95["B"] / p95["A"] if p95["B"] is not None and p95["A"] is not None and p95["A"] > 0 else None
    gate("maintained_p95_latency", latency_ratio <= thresholds["maintained_p95_latency_ratio_max"]
         if latency_ratio is not None else None, {"seconds": p95, "ratio": latency_ratio},
         thresholds["maintained_p95_latency_ratio_max"])
    unknown = [item["name"] for item in gates if item["passed"] is None]
    failed = [item["name"] for item in gates if item["passed"] is False]
    verdict = "inconclusive" if unknown or "complete_measurements" in failed else "keep" if not failed else "reject"
    return {"arms": arms, "per_task": per_task, "eligible_maintained_tasks": eligible,
            "sum_of_eligible_median_calls": sums, "observed_call_reduction": reduction,
            "maintained_p95_seconds": p95, "gates": gates, "failed_gates": failed,
            "unknown_gates": unknown, "verdict": verdict}


def generate_report(output: Path, corpus_root: Path, comparison_root: Path) -> dict:
    corpus = load_corpus(corpus_root)
    controls = load_controls(corpus)
    expected = {f"{case['id']}-r{rep}-{arm}" for case in corpus["cases"] for rep in range(1, 4) for arm in ("A", "B")}
    if {path.parent.name for path in output.glob("*/result.json")} != expected:
        raise ValueError("report requires every one of the exact 102 planned attempts")
    runs = []
    for case in corpus["cases"]:
        for rep in range(1, 4):
            for arm in ("A", "B"):
                folder = output / f"{case['id']}-r{rep}-{arm}"
                result = json.loads((folder / "result.json").read_text())
                provenance = json.loads((folder / "provenance.json").read_text())
                identity = result["identity"]
                if (identity["task_id"], identity["repetition"], identity["arm"]) != (case["id"], rep, arm):
                    raise ValueError("result identity differs from planned attempt")
                measurement, baseline = result["measurement"], result["baseline"]
                source = source_occurrences(result["events"])
                if not measurement.get("measurement_complete"):
                    source["unique_source_bytes"] = source["duplicate_source_bytes"] = None
                runs.append({**measurement, **source, "arm": arm, "task_id": case["id"],
                             "group": case["group"], "directory": folder.name,
                             "end_to_end_seconds": baseline.get("end_to_end_seconds"),
                             "index_seconds": provenance.get("index_seconds"),
                             "failures": baseline.get("failures", []), "relationships": baseline.get("relationships", {}),
                             "recorded_payload_bytes": baseline.get("output_accounting", {}).get("recorded_payload_bytes"),
                             **{key: (measurement.get("provider_usage") or {}).get(key)
                                for key in ("input_tokens", "cached_input_tokens", "output_tokens")}})
    preflight_path = comparison_root / "preflight.json"
    endpoints_available = None
    if preflight_path.exists():
        preflight = json.loads(preflight_path.read_text())
        endpoints_available = ({case["id"] for case in preflight["cases"]} == {case["id"] for case in corpus["cases"]}
                               and all(endpoint["status"] in {"indexed", "source_only"}
                                       for case in preflight["cases"] for endpoint in case["endpoints"]))
    summary = {"schema_version": 3, "comparison": "typescript-context-existing-v1", "method": "all_observed_tool_calls",
               "planned_runs": 102, "recorded_runs": len(runs), "complete_batch": True,
               **evaluate(runs, controls, endpoints_available=endpoints_available), "runs": runs}
    save(output / "report-summary.json", summary)
    lines = ["# Existing-edge type-context comparison", "", f"Frozen-gate verdict: **{summary['verdict']}**.", "",
             "Fresh A/B runs use the same v3 tasks, tool schemas, prompt, model and controls. B enables bounded existing type context on get. Historical A-only results are not paired here.", "",
             "| Arm | Full passes | Complete measurements | Calls | Output bytes | Gross input tokens |",
             "|---|---:|---:|---:|---:|---:|"]
    for arm, totals in summary["arms"].items():
        lines.append(f"| {arm} | {totals['fully_successful']}/51 | {totals['measurement_complete']}/51 | {totals['read_count']['sum']} | {totals['serialized_tool_output_bytes']['sum']} | {totals['input_tokens']['sum']} |")
    lines.extend(["", "## Maintained tasks", "", "| Task | Arm | Full passes | Calls, median | Source recall, median | Output bytes, median | Gross input, median |",
                  "|---|---|---:|---:|---:|---:|---:|"])
    for case in corpus["cases"]:
        if case["group"] == "maintained_task":
            for arm in ("A", "B"):
                task = summary["per_task"][arm][case["id"]]
                lines.append(f"| {case['id']} | {arm} | {task['fully_successful']}/3 | {task['read_count']['median']} | {task['context_recall']['median']} | {task['serialized_tool_output_bytes']['median']} | {task['input_tokens']['median']} |")
    lines.extend(["", "## Frozen acceptance gates", "", "| Gate | Passed | Actual | Required |", "|---|---|---|---|"])
    for item in summary["gates"]:
        lines.append(f"| {item['name']} | {item['passed']} | {json.dumps(item['actual'])} | {json.dumps(item['required'])} |")
    lines.extend(["", "All errors and failed attempts retain costs. Gross input includes cached input as a subset. Latency uses nearest-rank p95 across all nine maintained attempts per arm. Relationship negatives cover the authored forbidden cases; canonical edge values are preserved when recognizing the added response container.", "",
                  "These three source-comprehension tasks from one maintained repository do not establish broad coding or code-edit gains.", "",
                  "## All attempts", "", "| Attempt | Answer | Full pass | Accounting | Calls | Output bytes | Source recall | Outcome |",
                  "|---|---|---|---|---:|---:|---:|---|"])
    for run in runs:
        lines.append(f"| {run['directory']} | {run['answer_correct']} | {run['task_correct']} | {run.get('measurement_complete')} | {run.get('read_count')} | {run.get('serialized_tool_output_bytes')} | {run.get('context_recall')} | {run['outcome']} |")
    (output / "report.md").write_text("\n".join(lines) + "\n")
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--corpus-root", type=Path, required=True)
    parser.add_argument("--comparison-root", type=Path, required=True)
    args = parser.parse_args()
    result = generate_report(args.output, args.corpus_root, args.comparison_root)
    print(json.dumps({key: result[key] for key in ("recorded_runs", "verdict", "failed_gates", "unknown_gates")}))


if __name__ == "__main__":
    main()
