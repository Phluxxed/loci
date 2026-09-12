"""Report the matched TypeScript comparison with the actual ``loci_explore`` workflow.

The original v3 corpus, controls and numerical gates remain the inputs. This
module loads the two-arm result directories produced by the qualification
runner: A is current exact retrieval and B also makes loci_explore available. Gate scoring stays
in ``typescript_context_compare_report.evaluate`` so this report has the same
acceptance rule as the original comparison.
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from benchmarks.typescript_context_baseline import save
from benchmarks.typescript_context_compare_report import evaluate as _evaluate_frozen
from benchmarks.typescript_context_corpus import load_controls, load_corpus
from benchmarks.typescript_context_report_v3 import source_occurrences


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CORPUS_ROOT = ROOT / "benchmarks" / "corpora" / "typescript-context-v3"
ARMS = ("A", "B")
REPETITIONS = 3
CASE_COUNT = 17
EXPECTED_RUNS = CASE_COUNT * REPETITIONS * len(ARMS)
ARM_LABELS = {"A": "current exact retrieval", "B": "exact retrieval plus loci_explore"}


def _as_list(value: Any) -> list[Any]:
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return list(value)
    return []


def _count_violation_items(value: Any) -> int | None:
    if isinstance(value, list):
        return len(value)
    if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
        return value
    return None


def _normalize_relationships(value: Any) -> dict[str, Any]:
    """Keep scorer fields and ensure proof violations reach the frozen gate."""

    if not isinstance(value, Mapping):
        return {}
    relationships = dict(value)
    violations = _count_violation_items(relationships.get("delivery_integrity_violations"))
    if violations is not None:
        existing = _count_violation_items(relationships.get("forbidden_proven_relationships"))
        # The explore scorer already includes this count. ``max`` keeps that
        # result unchanged while protecting hand-built or older artifacts.
        relationships["forbidden_proven_relationships"] = max(existing or 0, violations)
    return relationships


def _provider_events(folder: Path) -> list[dict[str, Any]] | None:
    """Read the retained provider event stream used for actual-tool disclosure."""

    path = folder / "events.jsonl"
    if not path.is_file():
        return None
    events: list[dict[str, Any]] = []
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                try:
                    value = json.loads(line)
                except json.JSONDecodeError:
                    return None
                if isinstance(value, dict):
                    events.append(value)
                else:
                    return None
    except (OSError, UnicodeError):
        return None
    return events


def _actual_explore_calls(provider_events: Sequence[Mapping[str, Any]] | None) -> int | None:
    """Count actual terminal host calls; source traces are not a substitute."""
    if provider_events is None:
        return None
    ids = set()
    for event in provider_events:
        if event.get('type') not in {'item.completed', 'item.failed'}:
            continue
        item = event.get('item')
        if not isinstance(item, Mapping) or item.get('type') != 'mcp_tool_call':
            continue
        if not isinstance(item.get('id'), str) or not item['id']:
            return None
        if item.get('server') == 'evaluation' and item.get('tool') == 'loci_explore':
            ids.add(item['id'])
    return len(ids)


def _load_runs(output: Path, corpus: dict[str, Any], controls: dict[str, Any]) -> list[dict[str, Any]]:
    """Load and validate all 17 x 3 x 2 planned result identities."""

    case_ids = list(controls["case_ids"])
    if case_ids != [case["id"] for case in corpus["cases"]]:
        raise ValueError("controls and corpus case order differ")
    if len(case_ids) != CASE_COUNT or controls["schedule"]["repetitions"] != REPETITIONS:
        raise ValueError("explore report requires the frozen 17 x 3 schedule")
    expected = {
        f"{case_id}-r{repetition}-{arm}"
        for case_id in case_ids
        for repetition in range(1, REPETITIONS + 1)
        for arm in ARMS
    }
    actual = {path.parent.name for path in output.glob("*/result.json")}
    if actual != expected:
        raise ValueError("report requires every one of the exact 102 planned attempts")

    case_by_id = {case["id"]: case for case in corpus["cases"]}
    identities: set[tuple[str, int, str]] = set()
    runs: list[dict[str, Any]] = []
    for case_id in case_ids:
        for repetition in range(1, REPETITIONS + 1):
            for arm in ARMS:
                folder = output / f"{case_id}-r{repetition}-{arm}"
                result = json.loads((folder / "result.json").read_text(encoding="utf-8"))
                provenance = json.loads((folder / "provenance.json").read_text(encoding="utf-8"))
                identity = result.get("identity", {})
                observed = (identity.get("task_id"), identity.get("repetition"), identity.get("arm"))
                if observed != (case_id, repetition, arm):
                    raise ValueError("result identity differs from planned attempt")
                if observed in identities:
                    raise ValueError("duplicate result identity")
                identities.add(observed)

                measurement = result["measurement"]
                baseline = result["baseline"]
                events = result["events"]
                source = source_occurrences(events)
                if not measurement.get("measurement_complete"):
                    source["unique_source_bytes"] = source["duplicate_source_bytes"] = None
                failures = baseline.get("failures", [])
                if not isinstance(failures, list):
                    failures = [{"category": "invalid_failure_accounting", "value": failures}]
                usage = measurement.get("provider_usage")
                accounting = baseline.get("output_accounting")
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
                    "failures": failures,
                    "relationships": _normalize_relationships(baseline.get("relationships", {})),
                    "recorded_payload_bytes": accounting.get("recorded_payload_bytes")
                    if isinstance(accounting, Mapping) else None,
                    "provenance": provenance,
                    "actual_loci_explore_calls": _actual_explore_calls(_provider_events(folder)),
                    **{
                        key: usage.get(key) if isinstance(usage, Mapping) else None
                        for key in ("input_tokens", "cached_input_tokens", "output_tokens")
                    },
                })
    if len(identities) != EXPECTED_RUNS:
        raise ValueError("report requires 102 unique result identities")
    return runs


def _endpoint_availability(payload: Any, case_ids: list[str]) -> bool | None:
    if payload is None:
        return None
    if isinstance(payload, bool):
        return payload
    if not isinstance(payload, Mapping):
        return None
    explicit = payload.get("endpoints_available")
    if isinstance(explicit, bool):
        return explicit
    cases = payload.get("cases")
    if not isinstance(cases, list):
        return None
    by_id = {case.get("id"): case for case in cases if isinstance(case, Mapping)}
    if set(by_id) != set(case_ids):
        return False
    for case_id in case_ids:
        endpoints = by_id[case_id].get("endpoints")
        if not isinstance(endpoints, list):
            return None
        for endpoint in endpoints:
            if not isinstance(endpoint, Mapping) or "status" not in endpoint:
                return None
            if endpoint["status"] not in {"indexed", "source_only"}:
                return False
    return True


def _preflight_availability(payload: Any, case_ids: list[str]) -> dict[str, bool | None]:
    """Read one shared current-source preflight or an equivalent arm map."""

    if isinstance(payload, Mapping) and isinstance(payload.get("arms"), Mapping):
        return {
            arm: _endpoint_availability(payload["arms"].get(arm), case_ids)
            for arm in ARMS
        }
    available = _endpoint_availability(payload, case_ids)
    return {arm: available for arm in ARMS}


def evaluate(
    runs: list[dict[str, Any]],
    controls: dict[str, Any],
    *,
    endpoints_available: bool | None = None,
    preflight: Any = None,
) -> dict[str, Any]:
    """Apply the unchanged frozen A/B gates to the observed runs."""

    if preflight is not None:
        if isinstance(preflight, (str, Path)):
            preflight = json.loads(Path(preflight).read_text(encoding="utf-8"))
        values = _preflight_availability(preflight, list(controls["case_ids"]))
        endpoints_available = (
            False if any(value is False for value in values.values())
            else None if any(value is None for value in values.values())
            else True
        )
    normalized = []
    for run in runs:
        copied = dict(run)
        copied["relationships"] = _normalize_relationships(run.get("relationships", {}))
        normalized.append(copied)
    return _evaluate_frozen(normalized, controls, endpoints_available=endpoints_available)


def _raw_failures(runs: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "attempt": run.get("directory"),
            "task_id": run.get("task_id"),
            "repetition": run.get("repetition"),
            "arm": run.get("arm"),
            "failure": failure,
        }
        for run in runs
        for failure in _as_list(run.get("failures"))
    ]


def _usage(runs: Sequence[Mapping[str, Any]]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for arm in ARMS:
        selected = [run for run in runs if run.get("arm") == arm]
        by_attempt = {
            str(run.get("directory")): run.get("actual_loci_explore_calls")
            for run in selected
        }
        known_counts = [value for value in by_attempt.values() if value is not None]
        result[arm] = {
            "label": ARM_LABELS[arm],
            "tool": "loci_explore",
            "attempts": len(selected),
            "attempts_with_actual_loci_explore": sum(value is not None and value > 0 for value in by_attempt.values()),
            "calls": sum(known_counts) if len(known_counts) == len(by_attempt) else None,
            "attempts_without_explore": [name for name, count in by_attempt.items() if count == 0],
            "usage_accounting_complete": all(value is not None for value in by_attempt.values()),
            "calls_by_attempt": by_attempt,
        }
    result["B"]["disclosure"] = (
        "The intervention is tool availability. The model chooses its tools; "
        "using loci_explore on every candidate attempt is not an acceptance gate."
    )
    return result


def _read_manifest(output: Path) -> Any:
    path = output / "manifest.json"
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _attempt_lines(runs: Sequence[Mapping[str, Any]]) -> list[str]:
    lines = [
        "## All planned attempts",
        "",
        "| Attempt | Arm | Answer | Full pass | Complete | Calls | Output bytes | Source bytes | Source recall | Gross input | Cached input | Output tokens | End-to-end s | Index s | Explore calls | Outcome | Raw failures |",
        "|---|---|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|---|",
    ]
    for run in runs:
        lines.append(
            "| {directory} | {arm} | {answer} | {full} | {complete} | {calls} | "
            "{output} | {source} | {recall} | {input} | {cached} | {output_tokens} | "
            "{latency} | {index} | {explore} | {outcome} | {failures} |".format(
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
                explore=run.get("actual_loci_explore_calls"),
                outcome=run.get("outcome", "unknown"),
                failures=json.dumps(run.get("failures", []), ensure_ascii=False),
            )
        )
    return lines


def _write_report(output: Path, summary: Mapping[str, Any]) -> None:
    lines = [
        "# Actual loci_explore workflow comparison",
        "",
        f"Qualification verdict: **{summary['qualification_verdict']}**. "
        f"Frozen numerical gates: **{summary['verdict']}**. "
        f"Independent replay complete: **{summary['replay_complete']}**.",
        "",
        "The 17 original frozen cases, prompts, model, tool limits, source/index "
        "binding and numerical acceptance gates are shared by both conditions. "
        "A is current exact retrieval; B also makes the actual "
        "`loci_explore` implementation available. Tool choice remains the model's decision.",
        "",
        "## Actual B workflow usage",
        "",
        f"B recorded {summary['actual_loci_explore_usage']['B']['calls']} actual `loci_explore` "
        f"calls across {summary['actual_loci_explore_usage']['B']['attempts_with_actual_loci_explore']}/"
        f"{summary['actual_loci_explore_usage']['B']['attempts']} B attempts; per-attempt "
        f"usage accounting complete: **{summary['actual_loci_explore_usage']['B']['usage_accounting_complete']}**.",
        "",
        "## Arm totals",
        "",
        "| Arm | Workflow | Answers | Full passes | Complete measurements | Calls | Output bytes | Gross input | Maintained p95 | Explore calls |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for arm, totals in summary["arms"].items():
        lines.append(
            f"| {arm} | {ARM_LABELS[arm]} | {totals['answers_correct']}/{totals['runs']} | "
            f"{totals['fully_successful']}/{totals['runs']} | {totals['measurement_complete']}/{totals['runs']} | "
            f"{totals['read_count']['sum']} | {totals['serialized_tool_output_bytes']['sum']} | "
            f"{totals['input_tokens']['sum']} | {summary['maintained_p95_seconds'][arm]} | "
            f"{summary['actual_loci_explore_usage'][arm]['calls']} |"
        )
    lines.extend([
        "",
        "## Maintained task measurements",
        "",
        "| Task | Arm | Workflow | Answers | Full passes | Complete | Calls, median | Source bytes, median | Recall, median | Output bytes, median | Gross input, median |",
        "|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ])
    for case_id in summary["per_task"]["A"]:
        if not any(run["task_id"] == case_id and run["group"] == "maintained_task" for run in summary["runs"]):
            continue
        for arm in ARMS:
            task = summary["per_task"][arm][case_id]
            lines.append(
                f"| {case_id} | {arm} | {ARM_LABELS[arm]} | {task['answers_correct']}/{task['runs']} | "
                f"{task['fully_successful']}/{task['runs']} | {task['measurement_complete']}/{task['runs']} | "
                f"{task['read_count']['median']} | {task['source_bytes']['median']} | "
                f"{task['context_recall']['median']} | {task['serialized_tool_output_bytes']['median']} | "
                f"{task['input_tokens']['median']} |"
            )
    lines.extend([
        "",
        "## Frozen acceptance gates",
        "",
        "| Gate | Passed | Actual | Required |",
        "|---|---|---|---|",
    ])
    for item in summary["gates"]:
        lines.append(
            f"| {item['name']} | {item['passed']} | {json.dumps(item['actual'], ensure_ascii=False)} | "
            f"{json.dumps(item['required'], ensure_ascii=False)} |"
        )
    lines.extend(["", "## Retained failures", ""])
    if summary["raw_failures"]:
        lines.extend(
            f"- `{failure['attempt']}` ({failure['arm']}): {json.dumps(failure['failure'], ensure_ascii=False)}"
            for failure in summary["raw_failures"]
        )
    else:
        lines.append("None recorded.")
    lines.extend([
        "",
        "Failed attempts retain their observed costs. Missing measurements remain unavailable "
        "and keep affected gates unknown. Gross provider input includes cached input as a subset.",
        "",
    ])
    lines.extend(_attempt_lines(summary["runs"]))
    (output / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def generate_report(
    output: Path,
    corpus_root: Path = DEFAULT_CORPUS_ROOT,
    preflight: Path | Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Load the exact two-arm batch and write the report artifacts."""

    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    corpus = load_corpus(Path(corpus_root))
    if corpus["version"] != "typescript-context-v3":
        raise ValueError("v3 corpus required")
    controls = load_controls(corpus)
    runs = _load_runs(output, corpus, controls)
    if preflight is None:
        preflight_payload = None
    elif isinstance(preflight, (str, Path)):
        preflight_payload = json.loads(Path(preflight).read_text(encoding="utf-8"))
    else:
        preflight_payload = dict(preflight)
    endpoint_by_arm = _preflight_availability(preflight_payload, list(controls["case_ids"]))
    frozen = evaluate(runs, controls, preflight=preflight_payload)
    replay_path = output / 'replay-verification.json'
    replay = json.loads(replay_path.read_text()) if replay_path.exists() else {}
    replay_complete = (replay.get('comparison') == 'typescript-context-explore-v2'
                       and replay.get('complete') is True
                       and replay.get('verified_runs') == EXPECTED_RUNS
                       and not replay.get('failures'))
    summary = {
        "schema_version": 3,
        "comparison": "typescript-context-explore-v2",
        "method": "all_observed_tool_calls",
        "planned_runs": EXPECTED_RUNS,
        "recorded_runs": len(runs),
        "complete_batch": len(runs) == EXPECTED_RUNS,
        "arms_declared": list(ARMS),
        "arm_labels": dict(ARM_LABELS),
        "manifest": _read_manifest(output),
        "preflight": preflight_payload,
        "endpoint_availability": endpoint_by_arm,
        "actual_loci_explore_usage": _usage(runs),
        "raw_failures": _raw_failures(runs),
        "replay_complete": replay_complete,
        "qualification_verdict": frozen['verdict'] if replay_complete else 'inconclusive',
        **frozen,
        "runs": runs,
    }
    save(output / "report-summary.json", summary)
    _write_report(output, summary)
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--corpus-root", type=Path, required=True)
    parser.add_argument("--preflight", type=Path, required=True)
    args = parser.parse_args()
    result = generate_report(args.output.resolve(), args.corpus_root.resolve(), args.preflight.resolve())
    print(json.dumps({
        key: result[key]
        for key in ("recorded_runs", "verdict", "failed_gates", "unknown_gates", "actual_loci_explore_usage")
    }))


if __name__ == "__main__":
    main()
