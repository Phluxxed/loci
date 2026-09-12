"""Publish the complete W4.7 matched-workflow measurement without hiding gaps.

This reporter deliberately does not rescore a result.  It validates the
retained observation shape, exposes every planned slot (including missing
ones), and applies the thresholds already frozen in comparison-controls.json.
Independent replay is a separate required input owned by the replay module.
"""
from __future__ import annotations

import argparse
import json
import math
import statistics
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any

from benchmarks.multilingual_context_compare import ARMS, COMPARISON, EXPECTED_RUNS, schedule
from benchmarks.multilingual_context_inputs import load_inputs
from benchmarks.typescript_context_baseline import save
from benchmarks.typescript_context_report_v3 import source_occurrences


ROOT = Path(__file__).resolve().parents[1]
COMPARISON_ROOT = ROOT / "benchmarks" / "comparisons" / COMPARISON
METRICS = (
    "read_count", "serialized_tool_output_bytes", "source_bytes", "unique_source_bytes",
    "duplicate_source_bytes", "recorded_payload_bytes", "input_tokens", "cached_input_tokens",
    "output_tokens", "reasoning_output_tokens", "end_to_end_seconds", "actual_process_seconds", "adapter_elapsed_ms",
)
USAGE_KEYS = ("input_tokens", "cached_input_tokens", "output_tokens")
RAW_FILES = ("result.json", "provenance.json", "events.jsonl", "adapter-trace.json")


def _metric(values: Sequence[Any]) -> dict[str, Any]:
    known = [value for value in values if isinstance(value, (int, float)) and not isinstance(value, bool)]
    complete = len(known) == len(values) and bool(values)
    return {
        "complete": complete,
        "values": list(values),
        "sum": sum(known) if complete else None,
        "recorded_subtotal": sum(known),
        "median": statistics.median(known) if complete else None,
    }


def _failure_list(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return [{"category": "invalid_failure_accounting", "value": value}]
    return [item if isinstance(item, dict) else {"category": "invalid_failure_item", "value": item}
            for item in value]


def _language(case_id: str, group: str) -> str:
    if group == "maintained_module_task":
        return "python_maintained_single_module"
    if case_id.startswith("python_"):
        return "python_synthetic"
    if case_id.startswith("javascript_"):
        return "javascript"
    if case_id.startswith("go_"):
        return "go"
    if case_id.startswith("rust_"):
        return "rust"
    if case_id.startswith("tsx_"):
        return "tsx_control"
    if case_id.startswith("markdown_"):
        return "markdown_navigation_control"
    return "unknown"


def _relationship_complete(relationships: Mapping[str, Any]) -> bool | None:
    required = relationships.get("required_semantic_dependencies_total")
    delivered = relationships.get("delivered_dependency_links_total")
    forbidden = relationships.get("forbidden_proven_relationships")
    if not all(isinstance(value, int) and not isinstance(value, bool)
               for value in (required, delivered, forbidden)):
        return None
    return delivered == required and forbidden == 0


def _has_trust_defect(relationships: Mapping[str, Any], failures: Sequence[Mapping[str, Any]]) -> bool:
    """Separate fabricated/unsafe evidence from ordinary incomplete coverage.

    A model declining to retrieve a required edge makes the quality gate fail;
    it does not establish that the retrieval implementation fabricated one.
    """
    forbidden = relationships.get("forbidden_proven_relationships")
    integrity = relationships.get("delivery_integrity_violations")
    integrity_count = len(integrity) if isinstance(integrity, list) else integrity
    if (isinstance(forbidden, int) and not isinstance(forbidden, bool) and forbidden > 0
            or isinstance(integrity_count, int) and not isinstance(integrity_count, bool) and integrity_count > 0):
        return True
    trust_categories = {
        "delivery_trace_mismatch", "unmatched_delivery", "unmatched_recorded_delivery",
        "duplicate_delivery", "source_snapshot", "source_mutation", "unaccounted_tool_output",
        "unreported_budget_violation", "forbidden_proven_relationship",
    }
    return any(failure.get("category") in trust_categories for failure in failures)


def _attempt_status(run: Mapping[str, Any]) -> str:
    if run.get("trust_defect"):
        return "withheld_trust_defect"
    if not run.get("evidence_complete"):
        return "inconclusive_missing_evidence"
    if run.get("model_answer_with_correct_source"):
        return "model_limitation_wrong_answer_correct_source"
    if run.get("full_pass"):
        return "full_pass"
    return "measured_failure"


def _missing_run(plan: Mapping[str, Any], case: Mapping[str, Any], why: str) -> dict[str, Any]:
    return {
        "directory": plan["attempt_id"], "task_id": plan["case_id"], "repetition": plan["repetition"],
        "arm": plan["arm"], "group": case["group"], "language": _language(case["id"], case["group"]),
        "recorded": False, "evidence_complete": False, "full_pass": False,
        "failures": [{"category": why}], "relationships": {}, "raw_evidence_missing": list(RAW_FILES),
        "provider_usage_complete": False,
    }


def _read_attempt(output: Path, plan: Mapping[str, Any], case: Mapping[str, Any]) -> dict[str, Any]:
    folder = output / plan["attempt_id"]
    if not folder.is_dir():
        return _missing_run(plan, case, "missing_attempt")
    absent = [name for name in RAW_FILES if not (folder / name).is_file()]
    try:
        result = json.loads((folder / "result.json").read_text(encoding="utf-8")) if "result.json" not in absent else {}
        provenance = json.loads((folder / "provenance.json").read_text(encoding="utf-8")) if "provenance.json" not in absent else {}
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        row = _missing_run(plan, case, "invalid_retained_artifact")
        row["failure_detail"] = str(exc)
        return row
    identity = result.get("identity") if isinstance(result, Mapping) else None
    expected = (plan["case_id"], plan["repetition"], plan["arm"])
    observed = ((identity or {}).get("task_id"), (identity or {}).get("repetition"), (identity or {}).get("arm"))
    identity_ok = observed == expected and result.get("attempt_id") == plan["attempt_id"] and result.get("arm") == plan["arm"]
    measurement = result.get("measurement") if isinstance(result.get("measurement"), Mapping) else {}
    baseline = result.get("baseline") if isinstance(result.get("baseline"), Mapping) else {}
    accounting = baseline.get("output_accounting") if isinstance(baseline.get("output_accounting"), Mapping) else {}
    usage = measurement.get("provider_usage") if isinstance(measurement.get("provider_usage"), Mapping) else None
    usage_ok = isinstance(usage, Mapping) and all(isinstance(usage.get(key), int) and usage[key] >= 0 for key in USAGE_KEYS)
    events = result.get("events") if isinstance(result.get("events"), list) else []
    try:
        source = source_occurrences(events)
    except (KeyError, TypeError, ValueError):
        source = {"recorded_source_bytes": None, "unique_source_bytes": None, "duplicate_source_bytes": None}
        absent.append("result.events")
    relationships = baseline.get("relationships") if isinstance(baseline.get("relationships"), Mapping) else {}
    failures = _failure_list(baseline.get("failures", []))
    if not identity_ok:
        failures.append({"category": "attempt_identity_mismatch", "expected": expected, "observed": observed})
    if not isinstance(accounting.get("complete"), bool) or not accounting.get("complete"):
        failures.append({"category": "incomplete_observed_accounting"})
    evidence_complete = not absent and identity_ok and usage_ok and accounting.get("complete") is True and measurement.get("measurement_complete") is True
    row = {
        **dict(measurement), **source,
        "directory": plan["attempt_id"], "task_id": plan["case_id"], "repetition": plan["repetition"],
        "arm": plan["arm"], "group": case["group"], "language": _language(case["id"], case["group"]),
        "recorded": True, "evidence_complete": evidence_complete,
        "raw_evidence_missing": sorted(set(absent)), "provider_usage_complete": usage_ok,
        "relationships": dict(relationships), "failures": failures,
        "recorded_payload_bytes": accounting.get("recorded_payload_bytes"),
        "end_to_end_seconds": baseline.get("end_to_end_seconds"),
        "actual_process_seconds": baseline.get("actual_process_seconds"),
        "adapter_elapsed_ms": baseline.get("adapter_elapsed_ms"),
        "provenance": provenance,
        **{key: usage.get(key) if usage_ok else None for key in USAGE_KEYS},
        "reasoning_output_tokens": usage.get("reasoning_output_tokens")
        if usage_ok and isinstance(usage.get("reasoning_output_tokens"), int) and usage["reasoning_output_tokens"] >= 0 else None,
    }
    row["relationship_complete"] = _relationship_complete(row["relationships"])
    row["full_pass"] = bool(measurement.get("full_pass")) and evidence_complete
    row["trust_defect"] = _has_trust_defect(row["relationships"], failures)
    row["model_answer_with_correct_source"] = bool(
        evidence_complete and not measurement.get("answer_correct")
        and measurement.get("context_recall") == 1 and row["relationship_complete"] is True
    )
    row["disposition"] = _attempt_status(row)
    return row


def load_runs(output: Path, corpus: Mapping[str, Any], controls: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Load every slot in the frozen plan, retaining absent slots as evidence gaps."""
    plan = schedule(dict(corpus))
    if controls.get("case_ids") != [case["id"] for case in corpus["cases"]]:
        raise ValueError("controls and frozen corpus case order differ")
    cases = {case["id"]: case for case in corpus["cases"]}
    runs = [_read_attempt(Path(output), slot, cases[slot["case_id"]]) for slot in plan]
    if len(runs) != EXPECTED_RUNS or len({run["directory"] for run in runs}) != EXPECTED_RUNS:
        raise ValueError("report did not construct the fixed 114-attempt plan")
    return runs


def summarize(runs: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    failures = [failure for run in runs for failure in run.get("failures", []) if isinstance(failure, Mapping)]
    relation_names = (
        "required_semantic_dependencies_total", "available_dependency_links_total",
        "delivered_dependency_links_total", "forbidden_proven_relationships",
    )
    return {
        "runs": len(runs), "recorded": sum(bool(run.get("recorded")) for run in runs),
        "evidence_complete": sum(bool(run.get("evidence_complete")) for run in runs),
        "answers_correct": sum(bool(run.get("answer_correct")) for run in runs),
        "full_passes": sum(bool(run.get("full_pass")) for run in runs),
        "outcomes": dict(Counter(str(run.get("outcome", "missing")) for run in runs)),
        "dispositions": dict(Counter(str(run.get("disposition", _attempt_status(run))) for run in runs)),
        "failure_events": dict(Counter(str(item.get("category", "invalid_failure")) for item in failures)),
        "relationships": {name: _metric([run.get("relationships", {}).get(name) for run in runs]) for name in relation_names},
        **{name: _metric([run.get(name) for run in runs]) for name in METRICS},
    }


def _nearest_rank_p95(values: Iterable[Any]) -> float | int | None:
    values = list(values)
    numeric = [value for value in values if isinstance(value, (int, float)) and not isinstance(value, bool)]
    if not values or len(numeric) != len(values):
        return None
    numeric.sort()
    return numeric[math.ceil(.95 * len(numeric)) - 1]


def _gate(name: str, passed: bool | None, actual: Any, required: Any) -> dict[str, Any]:
    return {"name": name, "passed": passed, "actual": actual, "required": required}


def _case_medians(runs: Sequence[Mapping[str, Any]], case_ids: Sequence[str], metric: str) -> dict[str, dict[str, float | int | None]]:
    return {
        arm: {case: _metric([run.get(metric) for run in runs if run["arm"] == arm and run["task_id"] == case])["median"]
              for case in case_ids}
        for arm in ARMS
    }


def _replay_status(replay: Mapping[str, Any] | None, expected_attempt_ids: set[str]) -> bool | None:
    """Return scoped replay completeness without letting another language hide a gap."""
    if not isinstance(replay, Mapping) or replay.get("comparison") != COMPARISON:
        return None
    failures = replay.get("failures")
    if not isinstance(failures, list):
        return None
    failed_ids = {item.get("attempt_id") for item in failures if isinstance(item, Mapping)}
    if expected_attempt_ids & failed_ids:
        return False
    attempts = replay.get("attempts")
    if not isinstance(attempts, list):
        return None
    verified = {item.get("attempt_id") for item in attempts
                if isinstance(item, Mapping) and item.get("verified") is True}
    return True if expected_attempt_ids <= verified else None


def evaluate(
    runs: Sequence[Mapping[str, Any]],
    controls: Mapping[str, Any],
    replay: Mapping[str, Any] | None,
    *,
    case_ids: Sequence[str] | None = None,
) -> dict[str, Any]:
    """Apply every frozen gate to the requested language/control case scope."""
    case_ids = list(controls["case_ids"] if case_ids is None else case_ids)
    selected = [run for run in runs if run["task_id"] in case_ids]
    by_arm = {arm: [run for run in selected if run["arm"] == arm] for arm in ARMS}
    arms = {arm: summarize(by_arm[arm]) for arm in ARMS}
    per_case = {arm: {case: summarize([run for run in by_arm[arm] if run["task_id"] == case])
                      for case in case_ids} for arm in ARMS}
    expected_attempt_ids = {f"{case}-r{repetition}-{arm}" for case in case_ids for repetition in range(1, 4) for arm in ARMS}
    all_evidence = len(selected) == len(expected_attempt_ids) and all(run.get("evidence_complete") for run in selected)
    replay_complete = _replay_status(replay, expected_attempt_ids)
    replay_ready = replay_complete is True
    gates: list[dict[str, Any]] = []
    gates.append(_gate("complete_raw_usage_and_replay", True if all_evidence and replay_ready else False if replay_complete is False else None,
                       {"raw_usage": all_evidence, "replay": replay_complete}, True))
    b_full = [run.get("full_pass") for run in by_arm["B"]]
    gates.append(_gate("every_B_full_pass", all(b_full) if all_evidence and replay_ready else None,
                       sum(bool(value) for value in b_full), len(b_full)))
    correct_regressions: list[str] = []
    source_regressions: list[str] = []
    source_medians = _case_medians(runs, case_ids, "context_recall")
    if all_evidence and replay_ready:
        for case in case_ids:
            if per_case["B"][case]["answers_correct"] < per_case["A"][case]["answers_correct"]:
                correct_regressions.append(case)
            a_source, b_source = source_medians["A"][case], source_medians["B"][case]
            if a_source is None or b_source is None:
                source_regressions.append(case + ":unknown")
            elif b_source < a_source:
                source_regressions.append(case)
    gates.append(_gate("no_per_case_correctness_regression", not correct_regressions if all_evidence and replay_ready else None,
                       correct_regressions, []))
    gates.append(_gate("no_per_case_required_source_regression", not source_regressions if all_evidence and replay_ready else None,
                       source_regressions, []))
    trust = [run["directory"] for run in selected if run.get("trust_defect")]
    gates.append(_gate("trust_defects_withheld", not trust if all_evidence and replay_ready else None, trust, []))
    call_medians = _case_medians(runs, case_ids, "read_count")
    output_medians = _case_medians(runs, case_ids, "serialized_tool_output_bytes")
    input_medians = _case_medians(runs, case_ids, "input_tokens")
    median_sums: dict[str, dict[str, float | int | None]] = {}
    for name, values in (("calls", call_medians), ("output_bytes", output_medians), ("gross_input_tokens", input_medians)):
        median_sums[name] = {arm: sum(values[arm].values()) if all(value is not None for value in values[arm].values()) else None
                             for arm in ARMS}
    call_a, call_b = median_sums["calls"]["A"], median_sums["calls"]["B"]
    reduction = 1 - call_b / call_a if isinstance(call_a, (int, float)) and call_a > 0 and call_b is not None else None
    saved = [case for case in case_ids if call_medians["A"][case] is not None and call_medians["B"][case] is not None
             and call_medians["A"][case] - call_medians["B"][case] >= 1]
    gates.append(_gate("median_call_reduction", reduction >= controls["acceptance"]["tool_calls_relative_reduction_min"]
                       if all_evidence and replay_ready and reduction is not None else None,
                       {"sum_case_medians": median_sums["calls"], "reduction": reduction},
                       controls["acceptance"]["tool_calls_relative_reduction_min"]))
    gates.append(_gate("at_least_one_case_saves_one_median_call", len(saved) >= controls["acceptance"]["minimum_tasks_with_one_fewer_median_tool_call"]
                       if all_evidence and replay_ready else None, saved, controls["acceptance"]["minimum_tasks_with_one_fewer_median_tool_call"]))
    for name, control_key in (("output_bytes", "median_sum_output_bytes_ratio_max"), ("gross_input_tokens", "median_sum_gross_input_tokens_ratio_max")):
        a, b = median_sums[name]["A"], median_sums[name]["B"]
        ratio = b / a if isinstance(a, (int, float)) and a > 0 and b is not None else None
        gates.append(_gate(name + "_no_greater", ratio <= controls["acceptance"][control_key]
                           if all_evidence and replay_ready and ratio is not None else None,
                           {"sum_case_medians": median_sums[name], "ratio": ratio}, controls["acceptance"][control_key]))
    p95 = {arm: _nearest_rank_p95([run.get("end_to_end_seconds") for run in by_arm[arm]]) for arm in ARMS}
    latency_ratio = p95["B"] / p95["A"] if isinstance(p95["A"], (int, float)) and p95["A"] > 0 and p95["B"] is not None else None
    gates.append(_gate("nearest_rank_p95_latency", latency_ratio <= controls["acceptance"]["p95_latency_ratio_max"]
                       if all_evidence and replay_ready and latency_ratio is not None else None,
                       {"seconds": p95, "ratio": latency_ratio, "method": controls["acceptance"]["p95_method"]},
                       controls["acceptance"]["p95_latency_ratio_max"]))
    unknown = [gate["name"] for gate in gates if gate["passed"] is None]
    failed = [gate["name"] for gate in gates if gate["passed"] is False]
    quality_gates = {"every_B_full_pass", "no_per_case_correctness_regression", "no_per_case_required_source_regression"}
    efficiency_gates = {"median_call_reduction", "at_least_one_case_saves_one_median_call", "output_bytes_no_greater", "gross_input_tokens_no_greater", "nearest_rank_p95_latency"}
    quality = "inconclusive" if any(gate["name"] in unknown for gate in gates if gate["name"] in quality_gates) else "pass" if not any(gate["name"] in failed for gate in gates if gate["name"] in quality_gates) else "failed"
    efficiency = "inconclusive" if any(gate["name"] in unknown for gate in gates if gate["name"] in efficiency_gates) else "pass" if not any(gate["name"] in failed for gate in gates if gate["name"] in efficiency_gates) else "unproven"
    verdict = "withheld" if trust else "inconclusive" if unknown else "workflow_supported" if quality == "pass" and efficiency == "pass" else "quality_only" if quality == "pass" else "measured_limitation"
    return {"case_ids": case_ids, "arms": arms, "per_case": per_case, "gates": gates, "failed_gates": failed, "unknown_gates": unknown,
            "all_evidence_complete": all_evidence, "replay_complete": replay_complete, "source_medians": source_medians,
            "median_call_medians": call_medians, "median_sums": median_sums, "p95_latency_seconds": p95,
            "p95_latency_ratio": latency_ratio, "quality_disposition": quality, "efficiency_disposition": efficiency,
            "verdict": verdict}


def _language_dispositions(
    runs: Sequence[Mapping[str, Any]], controls: Mapping[str, Any], replay: Mapping[str, Any] | None,
) -> dict[str, dict[str, Any]]:
    """Evaluate each language/control independently, plus Python's two required origins."""
    case_ids_by_slice: dict[str, list[str]] = {}
    for run in runs:
        case_ids_by_slice.setdefault(str(run["language"]), []).append(str(run["task_id"]))
    python_cases = sorted(set(case_ids_by_slice.get("python_synthetic", []) + case_ids_by_slice.get("python_maintained_single_module", [])))
    if python_cases:
        case_ids_by_slice["python_combined"] = python_cases
    values: dict[str, dict[str, Any]] = {}
    for language, ids in sorted(case_ids_by_slice.items()):
        ids = list(dict.fromkeys(ids))
        scoped = evaluate(runs, controls, replay, case_ids=ids)
        selected = [run for run in runs if run["task_id"] in ids]
        values[language] = {"case_ids": ids, **summarize(selected), **scoped,
                            "B_full_passes": f"{scoped['arms']['B']['full_passes']}/{scoped['arms']['B']['runs']}",
                            "disposition": scoped["verdict"]}
    return values


def _markdown(summary: Mapping[str, Any]) -> str:
    lines = ["# Multilingual compact-workflow comparison", "",
             f"Disposition: **{summary['verdict']}**. Quality: **{summary['quality_disposition']}**. "
             f"Efficiency: **{summary['efficiency_disposition']}**. Missing raw evidence, usage, or independent replay is inconclusive.", "",
             "## Per-language and control dispositions", "",
             "| Slice | Recorded | Complete evidence | B full passes | Disposition |",
             "|---|---:|---:|---:|---|"]
    for language, value in summary["language_dispositions"].items():
        lines.append(f"| {language} | {value['recorded']}/{value['runs']} | {value['evidence_complete']}/{value['runs']} | {value['B_full_passes']} | {value['disposition']} |")
    lines.extend(["", "## Independent slice gates", ""])
    for language, value in summary["language_dispositions"].items():
        lines.extend([f"### {language}", "",
                      f"Cases: `{', '.join(value['case_ids'])}`. Each arm's complete metric vectors are retained in `report-summary.json` under this slice's `arms` field.", "",
                      "| Arm | Complete metric vectors |", "|---|---|"])
        for arm in ARMS:
            metrics = {name: value["arms"][arm][name] for name in METRICS}
            lines.append(f"| {arm} | {json.dumps(metrics, ensure_ascii=False)} |")
        lines.extend(["", "| Gate | Passed | Actual | Required |", "|---|---|---|---|"])
        for gate in value["gates"]:
            lines.append(f"| {gate['name']} | {gate['passed']} | {json.dumps(gate['actual'], ensure_ascii=False)} | {json.dumps(gate['required'], ensure_ascii=False)} |")
        lines.append("")
    lines.extend(["", "Python synthetic fixtures and the maintained single-module task are reported separately. The single TSX row is a bounded control; Markdown is a navigation control.",
                  "", "## Gates", "", "| Gate | Passed | Actual | Required |", "|---|---|---|---|"])
    for gate in summary["gates"]:
        lines.append(f"| {gate['name']} | {gate['passed']} | {json.dumps(gate['actual'], ensure_ascii=False)} | {json.dumps(gate['required'], ensure_ascii=False)} |")
    lines.extend(["", "## All 114 planned attempts", "",
                  "| Attempt | Arm | Answer | Full pass | Complete | Calls | Full output bytes | Source bytes | Required source recall | Gross input | Cached input | Output | Reasoning output | Latency s | Budget failures | Other failures | Disposition |",
                  "|---|---|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|---|---|"])
    for run in summary["runs"]:
        failures = run.get("failures", [])
        budget = [item for item in failures if item.get("category") == "budget_exhausted"]
        other = [item for item in failures if item.get("category") != "budget_exhausted"]
        lines.append("| {directory} | {arm} | {answer_correct} | {full_pass} | {complete} | {read_count} | {serialized_tool_output_bytes} | {source_bytes} | {context_recall} | {input_tokens} | {cached_input_tokens} | {output_tokens} | {reasoning_output_tokens} | {end_to_end_seconds} | {budget} | {other} | {disposition} |".format(
            **{key: run.get(key) for key in ("directory", "arm", "answer_correct", "full_pass", "read_count", "serialized_tool_output_bytes", "source_bytes", "context_recall", "input_tokens", "cached_input_tokens", "output_tokens", "reasoning_output_tokens", "end_to_end_seconds", "disposition")},
            complete=run.get("evidence_complete"), budget=json.dumps(budget, ensure_ascii=False), other=json.dumps(other, ensure_ascii=False)))
    lines.extend(["", "Gross provider input includes cached input as a separately reported subset. Output tokens include reasoning when the host reports it. A wrong answer with fully correct source and relationship delivery is retained as a model limitation, not relabeled as a retrieval defect.", ""])
    return "\n".join(lines)


def generate_report(output: Path) -> dict[str, Any]:
    """Write ``report-summary.json`` and ``report.md`` from one immutable output tree."""
    output = Path(output).resolve()
    corpus, controls = load_inputs()
    runs = load_runs(output, corpus, controls)
    replay_path = output / "replay-verification.json"
    try:
        replay = json.loads(replay_path.read_text(encoding="utf-8")) if replay_path.is_file() else None
    except (OSError, UnicodeError, json.JSONDecodeError):
        replay = None
    summary = {"schema_version": 1, "comparison": COMPARISON, "planned_runs": EXPECTED_RUNS,
               "recorded_runs": sum(bool(run["recorded"]) for run in runs), "runs": runs,
               "replay": replay, **evaluate(runs, controls, replay)}
    summary["language_dispositions"] = _language_dispositions(runs, controls, replay)
    save(output / "report-summary.json", summary)
    (output / "report.md").write_text(_markdown(summary), encoding="utf-8")
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = generate_report(args.output)
    print(json.dumps({key: result[key] for key in ("recorded_runs", "verdict", "failed_gates", "unknown_gates")}))


if __name__ == "__main__":
    main()
