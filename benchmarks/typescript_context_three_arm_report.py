"""Report the frozen v3 matched A/B/C TypeScript context comparison.

The v3 corpus and controls are deliberately treated as immutable inputs here.
Pair scoring is delegated to the frozen A/B evaluator so that adding arm C does
not create a second decision rule.  A pair is represented as ``candidate /
comparator`` (for example ``C/B``), while its nested frozen result keeps the
same shape and values as the existing evaluator with the real arm names put
back in place.
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any, Mapping

from benchmarks.typescript_context_baseline import save
from benchmarks.typescript_context_compare_report import (
    evaluate as _evaluate_frozen_pair,
    summarize,
)
from benchmarks.typescript_context_corpus import load_controls, load_corpus
from benchmarks.typescript_context_report_v3 import source_occurrences


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CORPUS_ROOT = ROOT / "benchmarks" / "corpora" / "typescript-context-v3"
DEFAULT_COMPARISON_ROOT = ROOT / "benchmarks" / "comparisons" / "typescript-context-three-arm-v1"
ARMS = ("A", "B", "C")
REPETITIONS = 3
CASE_COUNT = 17
EXPECTED_RUNS = CASE_COUNT * REPETITIONS * len(ARMS)


def _comparison_pairs(controls: Mapping[str, Any]) -> list[tuple[str, str]]:
    """Return controls-declared ``candidate, comparator`` arm pairs."""

    raw = controls.get("acceptance", {}).get("comparison_pairs")
    if not isinstance(raw, list) or not raw:
        raise ValueError("controls must declare comparison_pairs")
    arms = set(controls.get("arms", {}))
    pairs: list[tuple[str, str]] = []
    for pair in raw:
        if (not isinstance(pair, (list, tuple)) or len(pair) != 2
                or any(not isinstance(arm, str) for arm in pair)):
            raise ValueError("comparison_pairs must contain two arm names")
        candidate, comparator = pair
        if candidate == comparator or candidate not in arms or comparator not in arms:
            raise ValueError("comparison_pairs contain an unknown or repeated arm")
        pairs.append((candidate, comparator))
    return pairs


def _restore_arm_names(value: Any, *, alias_to_actual: Mapping[str, str]) -> Any:
    """Restore real arm names in a frozen pair result without changing values."""

    if isinstance(value, dict):
        return {
            alias_to_actual.get(key, key): _restore_arm_names(item, alias_to_actual=alias_to_actual)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_restore_arm_names(item, alias_to_actual=alias_to_actual) for item in value]
    if isinstance(value, str):
        # The frozen evaluator has one human-readable requirement string with
        # arm names.  Preserve all other strings exactly.
        return value.replace(
            "B median >= A median for each maintained task",
            f"{alias_to_actual.get('B', 'B')} median >= "
            f"{alias_to_actual.get('A', 'A')} median for each maintained task",
        )
    return value


def evaluate_pair(
    runs: list[dict],
    controls: dict,
    *,
    candidate: str,
    comparator: str,
    endpoints_available: bool | None = None,
) -> dict:
    """Apply the frozen pair evaluator to any two actual arm names.

    The frozen evaluator calls its comparator ``A`` and candidate ``B``.  The
    temporary labels are removed from the returned result, so ``arms``,
    per-task values and gate evidence name the actual pair arms.
    """

    if candidate == comparator:
        raise ValueError("a comparison pair needs two different arms")
    pair_runs: list[dict] = []
    for run in runs:
        arm = run.get("arm")
        if arm not in {candidate, comparator}:
            continue
        copied = dict(run)
        copied["arm"] = "B" if arm == candidate else "A"
        pair_runs.append(copied)
    frozen = _evaluate_frozen_pair(
        pair_runs,
        controls,
        endpoints_available=endpoints_available,
    )
    return _restore_arm_names(frozen, alias_to_actual={"A": comparator, "B": candidate})


def _endpoint_availability(payload: Any, case_ids: list[str]) -> bool | None:
    """Read the endpoint gate from one arm's preflight payload."""

    if payload is None:
        return None
    if isinstance(payload, bool):
        return payload
    if not isinstance(payload, dict):
        return None
    explicit = payload.get("endpoints_available")
    if isinstance(explicit, bool):
        return explicit
    cases = payload.get("cases")
    if not isinstance(cases, list):
        return None
    by_id = {case.get("id"): case for case in cases if isinstance(case, dict)}
    if set(by_id) != set(case_ids):
        return False
    for case_id in case_ids:
        endpoints = by_id[case_id].get("endpoints")
        if not isinstance(endpoints, list):
            return None
        for endpoint in endpoints:
            if not isinstance(endpoint, dict) or "status" not in endpoint:
                return None
            if endpoint["status"] not in {"indexed", "source_only"}:
                return False
    return True


def _preflight_availability(
    preflight: Mapping[str, Any] | None,
    *,
    arms: tuple[str, ...],
    case_ids: list[str],
) -> dict[str, bool | None]:
    """Return endpoint availability for each arm in either supported shape."""

    if preflight is None:
        return {arm: None for arm in arms}
    arm_payloads = preflight.get("arms") if isinstance(preflight, dict) else None
    if isinstance(arm_payloads, dict):
        return {
            arm: _endpoint_availability(arm_payloads.get(arm), case_ids)
            for arm in arms
        }
    available = _endpoint_availability(preflight, case_ids)
    return {arm: available for arm in arms}


def _raw_failures(runs: list[dict]) -> list[dict[str, Any]]:
    failures: list[dict[str, Any]] = []
    for run in runs:
        for failure in run.get("failures", []):
            failures.append({
                "attempt": run.get("directory"),
                "task_id": run.get("task_id"),
                "repetition": run.get("repetition"),
                "arm": run.get("arm"),
                "failure": failure,
            })
    return failures


def _maintained_p95(runs: list[dict], arm: str) -> float | int | None:
    """Use the frozen nearest-rank p95 over all nine maintained attempts."""

    values = [
        run.get("end_to_end_seconds")
        for run in runs
        if run.get("arm") == arm and run.get("group") == "maintained_task"
    ]
    if len(values) != 9 or any(value is None for value in values):
        return None
    return sorted(values)[math.ceil(0.95 * len(values)) - 1]


def _paired_denominators(pair: Mapping[str, Any], *, candidate: str, comparator: str) -> dict[str, Any]:
    eligible = list(pair["eligible_maintained_tasks"])
    sums = pair["sum_of_eligible_median_calls"]
    return {
        "candidate": candidate,
        "comparator": comparator,
        "eligible_maintained_tasks": eligible,
        "eligible_task_count": len(eligible),
        "sum_of_eligible_median_calls": {
            comparator: sums[comparator],
            candidate: sums[candidate],
        },
        "positive_comparator": sums[comparator] > 0,
    }


def evaluate_three_arm(
    runs: list[dict],
    controls: dict,
    *,
    endpoints_available: bool | Mapping[str, bool | None] | None = None,
    preflight: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Evaluate all controls-declared pairs and aggregate their verdicts.

    A missing endpoint preflight or required measurement remains unknown.  The
    frozen evaluator therefore reports ``inconclusive`` for the affected pair;
    the aggregate verdict is inconclusive if any pair is inconclusive, and
    reject if no pair is inconclusive but any pair rejects.
    """

    controls_arms = tuple(controls.get("arms", {}).keys())
    if set(controls_arms) != set(ARMS):
        raise ValueError("three-arm controls must declare A, B and C")
    case_ids = list(controls.get("case_ids", []))
    pairs = _comparison_pairs(controls)
    if preflight is not None:
        endpoint_by_arm = _preflight_availability(
            preflight, arms=ARMS, case_ids=case_ids,
        )
    elif isinstance(endpoints_available, Mapping):
        endpoint_by_arm = {arm: endpoints_available.get(arm) for arm in ARMS}
    else:
        endpoint_by_arm = {arm: endpoints_available for arm in ARMS}

    pair_results: dict[str, dict] = {}
    denominators: dict[str, dict[str, Any]] = {}
    for candidate, comparator in pairs:
        name = f"{candidate}/{comparator}"
        pair = evaluate_pair(
            runs,
            controls,
            candidate=candidate,
            comparator=comparator,
            endpoints_available=endpoint_by_arm.get(candidate),
        )
        pair_results[name] = pair
        denominators[name] = _paired_denominators(
            pair, candidate=candidate, comparator=comparator,
        )

    verdicts = [pair["verdict"] for pair in pair_results.values()]
    all_pairs_verdict = (
        "inconclusive" if "inconclusive" in verdicts
        else "reject" if "reject" in verdicts
        else "keep"
    )
    all_arm_runs = {arm: [run for run in runs if run.get("arm") == arm] for arm in ARMS}
    arm_summaries = {arm: summarize(arm_runs) for arm, arm_runs in all_arm_runs.items()}
    per_task = {
        arm: {
            case_id: summarize([
                run for run in all_arm_runs[arm] if run.get("task_id") == case_id
            ])
            for case_id in case_ids
        }
        for arm in ARMS
    }
    raw_failures = _raw_failures(runs)
    baseline_pair = pair_results.get("B/A")
    candidate_pair = pair_results.get("C/A")
    incremental_pair = pair_results.get("C/B")
    return {
        "arms": arm_summaries,
        "per_task": per_task,
        "maintained_latency_p95_seconds": {
            arm: _maintained_p95(runs, arm) for arm in ARMS
        },
        "comparisons": pair_results,
        "comparison_pairs": [list(pair) for pair in pairs],
        "paired_denominators": denominators,
        "endpoint_availability": endpoint_by_arm,
        "raw_failures": raw_failures,
        "failed_gates": {
            name: pair["failed_gates"] for name, pair in pair_results.items()
        },
        "unknown_gates": {
            name: pair["unknown_gates"] for name, pair in pair_results.items()
        },
        # ``all_pairs_verdict`` is descriptive: it is reject/inconclusive when
        # any comparator pair rejects/is unknown.  The candidate outcome below
        # follows the frozen final-candidate rule against A, even if B/A was
        # rejected; it must not be confused with incremental C semantics.
        "all_pairs_verdict": all_pairs_verdict,
        "candidate_verdict": candidate_pair["verdict"] if candidate_pair else None,
        "baseline_verdict": baseline_pair["verdict"] if baseline_pair else None,
        "incremental_new_semantics_verdict": (
            incremental_pair["verdict"] if incremental_pair else None
        ),
        # Compatibility convenience for callers that expect one primary
        # candidate verdict.  The explicit fields above carry the distinction.
        "verdict": candidate_pair["verdict"] if candidate_pair else all_pairs_verdict,
        "new_semantics": {
            "pair": "C/B" if "C/B" in pair_results else None,
            "verdict": incremental_pair["verdict"] if incremental_pair else None,
            "benefit_proven": incremental_pair is not None and incremental_pair["verdict"] == "keep",
            "candidate_against_a_verdict": candidate_pair["verdict"] if candidate_pair else None,
            "meaning": (
                "C's new semantics benefit is proven only by a passing C/B pair; "
                "a passing C/A pair alone does not establish incremental benefit over B."
            ),
        },
    }


def evaluate(
    runs: list[dict],
    controls: dict,
    *,
    endpoints_available: bool | Mapping[str, bool | None] | None = None,
    preflight: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Compatibility entry point for the three-arm evaluator."""

    return evaluate_three_arm(
        runs,
        controls,
        endpoints_available=endpoints_available,
        preflight=preflight,
    )


def _load_runs(output: Path, corpus: dict, controls: dict) -> list[dict]:
    """Load and validate every exact v3 case/repetition/arm identity."""

    case_ids = list(controls["case_ids"])
    if case_ids != [case["id"] for case in corpus["cases"]]:
        raise ValueError("controls and corpus case order differ")
    if len(case_ids) != CASE_COUNT or controls["schedule"]["repetitions"] != REPETITIONS:
        raise ValueError("three-arm report requires the frozen 17 x 3 schedule")
    expected_names = {
        f"{case_id}-r{repetition}-{arm}"
        for case_id in case_ids
        for repetition in range(1, REPETITIONS + 1)
        for arm in ARMS
    }
    actual_names = {path.parent.name for path in output.glob("*/result.json")}
    if actual_names != expected_names:
        raise ValueError("report requires every one of the exact 153 planned attempts")
    case_by_id = {case["id"]: case for case in corpus["cases"]}
    identities: set[tuple[str, int, str]] = set()
    runs: list[dict] = []
    for case_id in case_ids:
        for repetition in range(1, REPETITIONS + 1):
            for arm in ARMS:
                folder = output / f"{case_id}-r{repetition}-{arm}"
                result = json.loads((folder / "result.json").read_text(encoding="utf-8"))
                provenance = json.loads((folder / "provenance.json").read_text(encoding="utf-8"))
                identity = result.get("identity", {})
                observed = (
                    identity.get("task_id"),
                    identity.get("repetition"),
                    identity.get("arm"),
                )
                expected = (case_id, repetition, arm)
                if observed != expected:
                    raise ValueError("result identity differs from planned attempt")
                if observed in identities:
                    raise ValueError("duplicate result identity")
                identities.add(observed)
                measurement = result["measurement"]
                baseline = result["baseline"]
                source = source_occurrences(result["events"])
                if not measurement.get("measurement_complete"):
                    source["unique_source_bytes"] = source["duplicate_source_bytes"] = None
                runs.append({
                    **measurement,
                    **source,
                    "arm": arm,
                    "task_id": case_id,
                    "group": case_by_id[case_id]["group"],
                    "repetition": repetition,
                    "directory": folder.name,
                    "end_to_end_seconds": baseline.get("end_to_end_seconds"),
                    "index_seconds": provenance.get("index_seconds"),
                    "failures": baseline.get("failures", []),
                    "relationships": baseline.get("relationships", {}),
                    "recorded_payload_bytes": baseline.get("output_accounting", {}).get(
                        "recorded_payload_bytes"
                    ),
                    **{
                        key: (measurement.get("provider_usage") or {}).get(key)
                        for key in ("input_tokens", "cached_input_tokens", "output_tokens")
                    },
                })
    if len(identities) != EXPECTED_RUNS:
        raise ValueError("report requires 153 unique result identities")
    return runs


def _read_preflight(comparison_root: Path) -> Mapping[str, Any] | None:
    path = comparison_root / "preflight.json"
    if not path.exists():
        return None
    value = json.loads(path.read_text(encoding="utf-8"))
    return value if isinstance(value, dict) else None


def _all_attempt_lines(runs: list[dict]) -> list[str]:
    lines = [
        "## All planned attempts",
        "",
        "| Attempt | Arm | Answer | Full pass | Complete | Calls | Output bytes | Source bytes | Source recall | Gross input | Cached input | Output tokens | End-to-end s | Index s | Outcome | Raw failures |",
        "|---|---|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|---|",
    ]
    for run in runs:
        lines.append(
            "| {directory} | {arm} | {answer} | {full} | {complete} | {calls} | "
            "{output} | {source} | {recall} | {input} | {cached} | {output_tokens} | "
            "{latency} | {index} | {outcome} | {failures} |".format(
                directory=run.get("directory"),
                arm=run.get("arm"),
                answer=run.get("answer_correct"),
                full=run.get("task_correct"),
                complete=run.get("measurement_complete"),
                calls=run.get("read_count"),
                output=run.get("serialized_tool_output_bytes"),
                source=run.get("source_bytes"),
                recall=run.get("context_recall"),
                input=run.get("input_tokens"),
                cached=run.get("cached_input_tokens"),
                output_tokens=run.get("output_tokens"),
                latency=run.get("end_to_end_seconds"),
                index=run.get("index_seconds"),
                outcome=run.get("outcome", "unknown"),
                failures=json.dumps(run.get("failures", []), ensure_ascii=False),
            )
        )
    return lines


def _write_report(output: Path, summary: Mapping[str, Any]) -> None:
    lines = [
        "# Three-arm type-context comparison",
        "",
        f"Candidate C/A verdict: **{summary['candidate_verdict']}**. All-pairs diagnostic: **{summary['all_pairs_verdict']}**.",
        "",
        "The frozen v3 corpus, controls, 13 typed operations, source snapshots, "
        "ranking and budgets are shared by A, B and C. Pair gates use the frozen "
        "A/B evaluator with actual arm names restored.",
        "",
        "C's new semantics benefit is established only when C/B passes the frozen "
        "read rule and gates; C/A alone is insufficient.",
        "",
        "W2.4 `loci_explore` is not exposed by the frozen tool schema and is not measured.",
        "",
        "## Arm totals",
        "",
        "| Arm | Answers | Full passes | Complete measurements | Calls | Source bytes | Unique source bytes | Output bytes | Gross input | End-to-end p95 | Index time |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for arm, totals in summary["arms"].items():
        lines.append(
            f"| {arm} | {totals['answers_correct']}/{totals['runs']} | "
            f"{totals['fully_successful']}/{totals['runs']} | "
            f"{totals['measurement_complete']}/{totals['runs']} | "
            f"{totals['read_count']['sum']} | {totals['source_bytes']['sum']} | "
            f"{totals['unique_source_bytes']['sum']} | "
            f"{totals['serialized_tool_output_bytes']['sum']} | "
            f"{totals['input_tokens']['sum']} | "
            f"{summary['maintained_latency_p95_seconds'][arm]} | "
            f"{totals['index_seconds']['median']} |"
        )
    lines.extend([
        "",
        "## Maintained task measurements",
        "",
        "| Task | Arm | Answers | Full passes | Complete | Calls, median | Source bytes, median | Unique source, median | Recall, median | Output bytes, median | Gross input, median | Cached input, median | Output tokens, median | End-to-end, median | Index, median |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ])
    for case_id in summary["per_task"][ARMS[0]]:
        for arm in ARMS:
            task = summary["per_task"][arm][case_id]
            lines.append(
                f"| {case_id} | {arm} | {task['answers_correct']}/{task['runs']} | "
                f"{task['fully_successful']}/{task['runs']} | "
                f"{task['measurement_complete']}/{task['runs']} | "
                f"{task['read_count']['median']} | {task['source_bytes']['median']} | "
                f"{task['unique_source_bytes']['median']} | "
                f"{task['context_recall']['median']} | "
                f"{task['serialized_tool_output_bytes']['median']} | "
                f"{task['input_tokens']['median']} | "
                f"{task['cached_input_tokens']['median']} | "
                f"{task['output_tokens']['median']} | "
                f"{task['end_to_end_seconds']['median']} | "
                f"{task['index_seconds']['median']} |"
            )
    lines.extend([
        "",
        "## Pair verdicts",
        "",
        "| Pair | Verdict | Failed gates | Unknown gates | Eligible maintained tasks | Comparator median-call sum | Candidate median-call sum |",
        "|---|---|---|---|---:|---:|---:|",
    ])
    for name, pair in summary["comparisons"].items():
        denominator = summary["paired_denominators"][name]
        lines.append(
            f"| {name} | {pair['verdict']} | {json.dumps(pair['failed_gates'])} | "
            f"{json.dumps(pair['unknown_gates'])} | {denominator['eligible_task_count']} | "
            f"{denominator['sum_of_eligible_median_calls'][denominator['comparator']]} | "
            f"{denominator['sum_of_eligible_median_calls'][denominator['candidate']]} |"
        )
    lines.extend(["", "## Frozen gates", ""])
    for name, pair in summary["comparisons"].items():
        lines.extend([
            f"### {name}",
            "",
            "| Gate | Passed | Actual | Required |",
            "|---|---|---|---|",
        ])
        for item in pair["gates"]:
            lines.append(
                f"| {item['name']} | {item['passed']} | "
                f"{json.dumps(item['actual'], ensure_ascii=False)} | "
                f"{json.dumps(item['required'], ensure_ascii=False)} |"
            )
        lines.append("")
    lines.extend([
        "## Raw failures",
        "",
    ])
    if summary["raw_failures"]:
        lines.extend(
            f"- `{failure['attempt']}`: {json.dumps(failure['failure'], ensure_ascii=False)}"
            for failure in summary["raw_failures"]
        )
    else:
        lines.append("None recorded.")
    lines.extend(["", "These three source-comprehension tasks from one maintained repository do not establish broad coding or code-edit gains.", ""])
    lines.extend(_all_attempt_lines(summary["runs"]))
    (output / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def generate_report(
    output: Path,
    corpus_root: Path = DEFAULT_CORPUS_ROOT,
    comparison_root: Path = DEFAULT_COMPARISON_ROOT,
) -> dict[str, Any]:
    """Load the exact 153 attempts and write the three-arm report artifacts."""

    corpus = load_corpus(Path(corpus_root))
    if corpus["version"] != "typescript-context-v3":
        raise ValueError("v3 corpus required")
    controls = load_controls(corpus)
    runs = _load_runs(Path(output), corpus, controls)
    preflight = _read_preflight(Path(comparison_root))
    summary = {
        "schema_version": 3,
        "comparison": "typescript-context-three-arm-v1",
        "method": "all_observed_tool_calls",
        "planned_runs": EXPECTED_RUNS,
        "recorded_runs": len(runs),
        "complete_batch": len(runs) == EXPECTED_RUNS,
        "arms_declared": list(ARMS),
        "preflight": preflight,
        **evaluate_three_arm(runs, controls, preflight=preflight),
        "runs": runs,
    }
    save(Path(output) / "report-summary.json", summary)
    _write_report(Path(output), summary)
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--corpus-root", type=Path, default=DEFAULT_CORPUS_ROOT)
    parser.add_argument("--comparison-root", type=Path, default=DEFAULT_COMPARISON_ROOT)
    args = parser.parse_args()
    result = generate_report(args.output.resolve(), args.corpus_root.resolve(), args.comparison_root.resolve())
    print(json.dumps({
        key: result[key]
        for key in ("recorded_runs", "candidate_verdict", "all_pairs_verdict",
                    "failed_gates", "unknown_gates")
    }))


if __name__ == "__main__":
    main()
