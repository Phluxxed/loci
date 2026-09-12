"""Report the matched TypeScript comparison with explicit exploration routing.

The original v3 corpus, controls and numerical gates remain the inputs. Both
conditions expose the same B-capability tool schema; the intervention is the
versioned prompt policy used by B. Numeric scoring stays in the immutable
frozen evaluator, while this module reports the separately observed routing
evidence and keeps it out of that evaluator's thresholds.
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from benchmarks.typescript_context_baseline import save
from benchmarks.typescript_context_corpus import load_controls, load_corpus
from benchmarks.typescript_context_routing_v2 import CALL_TARGET_CASES, VERSION
from benchmarks.typescript_context_routing_v2_run import COMPARISON_ROOT, sha, validate_freeze
from benchmarks.typescript_context_routing_v2_replay import (
    expected_routing_identity,
    validate_policy_contract,
)
from benchmarks.typescript_context_routing_v2_observed import (
    PROTOCOL as OBSERVED_PROTOCOL,
    RAW_PROTOCOL,
)
from benchmarks.typescript_context_explore_v2_report import (
    _load_runs as _load_explore_runs,
)
from benchmarks.typescript_context_compare_report import evaluate as _evaluate_frozen


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CORPUS_ROOT = ROOT / "benchmarks" / "corpora" / "typescript-context-v3"
ARMS = ("A", "B")
REPETITIONS = 3
CASE_COUNT = 17
EXPECTED_RUNS = CASE_COUNT * REPETITIONS * len(ARMS)
ARM_LABELS = {"A": "exploration available", "B": "explicit exploration routing"}
CANDIDATE_REQUIRED = 9
MEASUREMENT_PROTOCOL = OBSERVED_PROTOCOL


def _validate_current_artifact(
    result: Mapping[str, Any],
    provenance: Mapping[str, Any],
    folder: Path,
    run: Mapping[str, Any],
) -> None:
    """Reject artifacts from the earlier routing comparison or a mixed batch."""

    if OBSERVED_PROTOCOL != VERSION:
        raise ValueError("routing observer is not owned by the current protocol")
    if result.get("protocol") != VERSION:
        raise ValueError("report requires the current typescript-context-routing-v2 result protocol")
    if result.get("schema_version") != 3:
        raise ValueError("routing result schema is not the current schema")
    if result.get("provenance") != dict(provenance):
        raise ValueError("result provenance differs from provenance.json")
    identity = result.get("identity")
    if not isinstance(identity, Mapping):
        raise ValueError("routing result identity is missing")
    expected_identity = {
        "task_id": run.get("task_id"),
        "repetition": run.get("repetition"),
        "arm": run.get("arm"),
    }
    if any(identity.get(key) != value for key, value in expected_identity.items()):
        raise ValueError("routing result identity differs from the planned attempt")
    if result.get("attempt_id") != folder.name or result.get("arm") != run.get("arm"):
        raise ValueError("routing result attempt identity differs from the planned attempt")
    if provenance.get("attempt_id") != folder.name:
        raise ValueError("routing provenance attempt identity differs from the planned attempt")
    routing_identity = provenance.get("routing")
    if (
        not isinstance(routing_identity, Mapping)
        or routing_identity.get("version") != VERSION
        or routing_identity.get("condition") != run.get("arm")
        or routing_identity.get("capability_arm") != "B"
    ):
        raise ValueError("routing provenance uses an incompatible protocol identity")
    raw_path = folder / "adapter-trace.json"
    if not raw_path.is_file():
        raise ValueError("routing attempt is missing the retained adapter trace")
    try:
        raw = json.loads(raw_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("retained adapter trace is not valid JSON") from exc
    if raw.get("protocol") not in {None, RAW_PROTOCOL}:
        raise ValueError("retained adapter trace uses an incompatible protocol")


def _validate_source_denominator(runs: Sequence[Mapping[str, Any]]) -> None:
    """Require the complete frozen batch and its nine maintained attempts/arm."""

    if len(runs) != EXPECTED_RUNS:
        raise ValueError("routing report requires every one of the exact 102 planned attempts")
    maintained = [run for run in runs if run.get("group") == "maintained_task"]
    if len(maintained) != CANDIDATE_REQUIRED * len(ARMS):
        raise ValueError("routing report requires the complete nine-attempt maintained denominator per arm")
    if any(
        sum(run.get("arm") == arm for run in maintained) != CANDIDATE_REQUIRED
        for arm in ARMS
    ):
        raise ValueError("routing report requires nine maintained attempts for each arm")


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


def _validate_route_observation(value: Any, case_id: str) -> dict[str, Any]:
    """Validate one observed routing record without interpreting its outcome."""

    if not isinstance(value, Mapping):
        raise ValueError("routing observation must be an object")
    required = {
        "schema_version", "observations_complete", "first_repository_call",
        "initial_route_expected", "initial_type_route", "requested_anchor_received",
        "maintained_exposure", "explore_calls", "fallback_calls", "helper_call_count",
        "failures",
    }
    if not required.issubset(value):
        raise ValueError("routing observation is missing required fields")
    if value["schema_version"] != 1 or type(value["observations_complete"]) is not bool:
        raise ValueError("routing observation schema is invalid")
    expected_route = "call_target" if case_id in CALL_TARGET_CASES else "type_dependencies"
    if value["initial_route_expected"] != expected_route:
        raise ValueError("routing observation has the wrong initial route declaration")
    for key in ("initial_type_route", "requested_anchor_received", "maintained_exposure"):
        if value[key] is not None and type(value[key]) is not bool:
            raise ValueError("routing observation boolean field is invalid")
    if value["first_repository_call"] is not None and not isinstance(value["first_repository_call"], Mapping):
        raise ValueError("routing first repository call is invalid")
    for key in ("explore_calls", "fallback_calls", "failures"):
        if not isinstance(value[key], list):
            raise ValueError("routing observation list field is invalid")
    if type(value["helper_call_count"]) is not int or value["helper_call_count"] < 0:
        raise ValueError("routing helper call count is invalid")
    item_fields = {
        "item_id", "intent", "status", "successful_delivery", "anchor_ids", "omissions",
        "requested_anchor_received", "anchor_complete",
    }
    for item in value["explore_calls"]:
        if not isinstance(item, Mapping) or not item_fields.issubset(item):
            raise ValueError("routing explore call is incomplete")
        if not isinstance(item["item_id"], str) or not isinstance(item["status"], str):
            raise ValueError("routing explore call identity is invalid")
        if type(item["successful_delivery"]) is not bool:
            raise ValueError("routing explore delivery status is invalid")
        if not isinstance(item["anchor_ids"], list) or not isinstance(item["omissions"], list):
            raise ValueError("routing explore evidence lists are invalid")
        for key in ("requested_anchor_received", "anchor_complete"):
            if item[key] is not None and type(item[key]) is not bool:
                raise ValueError("routing explore evidence flag is invalid")
    return dict(value)


def _load_runs(
    output: Path,
    corpus: dict[str, Any],
    controls: dict[str, Any],
    freeze: Mapping[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Load frozen numeric rows and add independently retained routing data."""

    runs = _load_explore_runs(output, corpus, controls)
    for run in runs:
        folder = output / str(run["directory"])
        result = json.loads((folder / "result.json").read_text(encoding="utf-8"))
        provenance = run.get("provenance")
        if not isinstance(provenance, Mapping):
            raise ValueError("routing attempt provenance is missing")
        _validate_current_artifact(result, provenance, folder, run)
        route = result.get("routing")
        route_error: str | None = None
        if route is not None:
            try:
                route = _validate_route_observation(route, str(run["task_id"]))
            except ValueError as exc:
                route_error = str(exc)
                route = None
        else:
            route_error = "routing observation is missing"
        identity_error: str | None = None
        if freeze is not None and isinstance(provenance, Mapping):
            try:
                expected = expected_routing_identity(
                    corpus, controls, str(run["task_id"]), str(run["arm"]), dict(freeze),
                )
                if provenance.get("routing") != expected:
                    identity_error = "provenance routing identity differs from the frozen policy"
            except (KeyError, TypeError, ValueError) as exc:
                identity_error = str(exc)
            expected_engine = {
                key: freeze["engine"][key]
                for key in ("commit", "source_tree", "extractor_version")
            }
            source = provenance.get("source")
            case = next(case for case in corpus["cases"] if case["id"] == run["task_id"])
            if (
                not isinstance(source, Mapping)
                or source.get("engine") != expected_engine
                or source.get("freeze_json_sha256") != freeze.get("freeze_json_sha256")
                or provenance.get("snapshot_files") != corpus["snapshots"][case["snapshot"]]["files"]
                or provenance.get("corpus_sha256") != sha((Path(corpus["_root"]) / "corpus.json").read_bytes())
                or provenance.get("controls_sha256") != sha((Path(corpus["_root"]) / "comparison-controls.json").read_bytes())
            ):
                raise ValueError("routing provenance source identity differs from the frozen inputs")
        run["routing"] = route
        run["routing_error"] = route_error
        run["routing_identity_error"] = identity_error
        run["routing_observed"] = (
            route is not None
            and route_error is None
            and identity_error is None
            and route.get("observations_complete") is True
        )
        run["routing_expected"] = (
            "call_target" if str(run["task_id"]) in CALL_TARGET_CASES else "type_dependencies"
        )
        # Keep these fields in every per-attempt row so report consumers do
        # not have to reconstruct the retained workflow evidence.
        run["routing_calls"] = route.get("explore_calls", []) if route is not None else []
        run["routing_fallback_calls"] = route.get("fallback_calls", []) if route is not None else []
        run["routing_failures"] = route.get("failures", []) if route is not None else (
            [route_error] if route_error else []
        )
    _validate_source_denominator(runs)
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
        "The intervention is explicit routing guidance. The model chooses its tools; "
        "using loci_explore on every candidate attempt is not an acceptance gate."
    )
    return result


def _route_counts(
    runs: Sequence[Mapping[str, Any]],
    predicate: Any,
    *,
    required: int,
) -> dict[str, Any]:
    """Count pass/fail/unknown observed route outcomes without imputing data."""

    counts: dict[str, Any] = {
        "required": required,
        "known": 0,
        "pass": 0,
        "fail": 0,
        "unknown": 0,
        "pass_attempts": [],
        "fail_attempts": [],
        "unknown_attempts": [],
    }
    for run in runs:
        attempt = str(run.get("directory"))
        route = run.get("routing")
        if run.get("routing_observed") is not True or not isinstance(route, Mapping):
            counts["unknown"] += 1
            counts["unknown_attempts"].append(attempt)
            continue
        try:
            outcome = predicate(route)
        except (KeyError, TypeError, ValueError):
            outcome = None
        if outcome is True:
            counts["known"] += 1
            counts["pass"] += 1
            counts["pass_attempts"].append(attempt)
        elif outcome is False:
            counts["known"] += 1
            counts["fail"] += 1
            counts["fail_attempts"].append(attempt)
        else:
            counts["unknown"] += 1
            counts["unknown_attempts"].append(attempt)
    return counts


def _routing_exposure(runs: Sequence[Mapping[str, Any]], replay_complete: bool) -> dict[str, Any]:
    """Summarize maintained-task exposure for both arms and the candidate gate."""

    maintained = [run for run in runs if run.get("group") == "maintained_task"]
    by_arm = {
        arm: _route_counts(
            [run for run in maintained if run.get("arm") == arm],
            lambda route: route.get("maintained_exposure")
            if type(route.get("maintained_exposure")) is bool else None,
            required=CANDIDATE_REQUIRED,
        )
        for arm in ARMS
    }
    candidate = by_arm["B"]
    established = bool(
        replay_complete
        and candidate["unknown"] == 0
        and candidate["pass"] == CANDIDATE_REQUIRED
    )
    if not replay_complete or candidate["unknown"]:
        status = "unknown"
    else:
        status = "established" if established else "not_established"
    return {
        # Keep direct arm keys for report consumers while retaining the
        # explicit ``maintained`` grouping in the published summary.
        "A": by_arm["A"],
        "B": by_arm["B"],
        "maintained": by_arm,
        "candidate_required": CANDIDATE_REQUIRED,
        "candidate_passes": candidate["pass"],
        "candidate_exposure_established": established,
        "status": status,
        "exposure_status": status,
        "all_routing_observed": all(run.get("routing_observed") is True for run in runs),
        "replay_complete": replay_complete,
        "description": (
            "A is descriptive. B qualifies for the candidate exposure only when all nine "
            "maintained attempts have observed maintained exposure and independent replay is complete."
        ),
    }


def _initial_type_route_compliance(runs: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Report the 13 non-endpoint cases that should begin on type routing."""

    selected = [run for run in runs if run.get("task_id") not in CALL_TARGET_CASES]
    by_arm = {
        arm: _route_counts(
            [run for run in selected if run.get("arm") == arm],
            lambda route: route.get("initial_type_route")
            if type(route.get("initial_type_route")) is bool else None,
            required=13 * REPETITIONS,
        )
        for arm in ARMS
    }
    for arm in ARMS:
        by_arm[arm]["required_cases"] = 13
        by_arm[arm]["case_ids"] = sorted({str(run.get("task_id")) for run in selected})
    return {
        "A": by_arm["A"],
        "B": by_arm["B"],
        "case_count": 13,
        "attempts_per_arm": 13 * REPETITIONS,
        "expected_route": "type_dependencies",
        "by_arm": by_arm,
    }


def _call_target_controls(runs: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Report actual first repository calls for the four endpoint controls."""

    selected = [run for run in runs if run.get("task_id") in CALL_TARGET_CASES]

    def actual_call(route: Mapping[str, Any]) -> bool | None:
        call = route.get("first_repository_call")
        if call is None:
            return None
        if not isinstance(call, Mapping):
            return False
        # The route observer records the first actual repository call. Presence
        # is the useful descriptive fact here; this section does not create a
        # numerical gate or infer an absent call from an answer.
        return bool(call.get("tool") or call.get("name") or call.get("operation"))

    by_arm = {
        arm: _route_counts(
            [run for run in selected if run.get("arm") == arm],
            actual_call,
            required=4 * REPETITIONS,
        )
        for arm in ARMS
    }
    for arm in ARMS:
        by_arm[arm]["required_cases"] = 4
        by_arm[arm]["case_ids"] = sorted({str(run.get("task_id")) for run in selected})
        by_arm[arm]["actual_use"] = by_arm[arm]["pass"]
    return {
        "A": by_arm["A"],
        "B": by_arm["B"],
        "case_count": 4,
        "attempts_per_arm": 4 * REPETITIONS,
        "expected_route": "call_target",
        "by_arm": by_arm,
    }


def _qualification_verdict(
    numeric_verdict: Any,
    *,
    complete_batch: bool,
    runs: Sequence[Mapping[str, Any]],
    replay_complete: bool,
    exposure: Mapping[str, Any],
) -> str:
    """Apply routing completeness around the unchanged numeric verdict."""

    if (not complete_batch or not replay_complete
            or any(run.get("measurement_complete") is not True for run in runs)
            or exposure.get("exposure_status") == "unknown"
            or exposure.get("all_routing_observed") is not True):
        return "inconclusive"
    if numeric_verdict == "reject" or exposure.get("exposure_status") == "not_established":
        return "reject"
    if numeric_verdict == "keep" and exposure.get("exposure_status") == "established":
        return "keep"
    return "inconclusive"


def _read_manifest(output: Path) -> Any:
    path = output / "manifest.json"
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _attempt_lines(runs: Sequence[Mapping[str, Any]]) -> list[str]:
    lines = [
        "## All planned attempts",
        "",
        "| Attempt | Arm | Answer | Full pass | Complete | Calls | Output bytes | Source bytes | Source recall | Gross input | Cached input | Output tokens | End-to-end s | Index s | Explore calls | Initial route | Maintained exposure | Routing calls | Fallback calls | Routing failures | Outcome | Raw failures |",
        "|---|---|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|---|---|---|---|---|",
    ]
    for run in runs:
        lines.append(
            "| {directory} | {arm} | {answer} | {full} | {complete} | {calls} | "
            "{output} | {source} | {recall} | {input} | {cached} | {output_tokens} | "
            "{latency} | {index} | {explore} | {initial} | {maintained} | {route_calls} | "
            "{fallback} | {routing_failures} | {outcome} | {failures} |".format(
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
                initial=(run.get("routing") or {}).get("initial_type_route")
                if isinstance(run.get("routing"), Mapping) else None,
                maintained=(run.get("routing") or {}).get("maintained_exposure")
                if isinstance(run.get("routing"), Mapping) else None,
                route_calls=json.dumps(run.get("routing_calls", []), ensure_ascii=False),
                fallback=json.dumps(run.get("routing_fallback_calls", []), ensure_ascii=False),
                routing_failures=json.dumps(run.get("routing_failures", []), ensure_ascii=False),
                outcome=run.get("outcome", "unknown"),
                failures=json.dumps(run.get("failures", []), ensure_ascii=False),
            )
        )
    return lines


def _write_report(output: Path, summary: Mapping[str, Any]) -> None:
    lines = [
        "# Explicit exploration routing comparison",
        "",
        f"Qualification verdict: **{summary['qualification_verdict']}**. "
        f"Frozen numerical gates: **{summary['numeric_verdict']}**. "
        f"Independent replay complete: **{summary['replay_complete']}**.",
        "",
        "The 17 original frozen cases, prompts, model, tool limits, source/index "
        "binding and numerical acceptance gates are shared by both conditions. "
        "A exposes the exploration capability; B adds the explicit routing policy. "
        "Tool choice remains the model's decision.",
        "",
        "## Routing exposure",
        "",
        f"Candidate exposure status: **{summary['routing_exposure']['exposure_status']}**; "
        f"B maintained passes: {summary['routing_exposure']['candidate_passes']}/"
        f"{summary['routing_exposure']['candidate_required']}; replay complete: "
        f"**{summary['routing_exposure']['replay_complete']}**.",
        "",
        "| Arm | Workflow | Required maintained attempts | Known | Pass | Fail | Unknown |",
        "|---|---|---:|---:|---:|---:|---:|",
    ]
    for arm in ARMS:
        exposure = summary["routing_exposure"]["maintained"][arm]
        lines.append(
            f"| {arm} | {ARM_LABELS[arm]} | {exposure['required']} | {exposure['known']} | "
            f"{exposure['pass']} | {exposure['fail']} | {exposure['unknown']} |"
        )
    lines.extend([
        "",
        "## Initial route observations",
        "",
        "| Arm | Expected route | Cases | Attempts | Known | Pass | Fail | Unknown |",
        "|---|---|---:|---:|---:|---:|---:|---:|",
    ])
    for arm in ARMS:
        compliance = summary["initial_type_route_compliance"]["by_arm"][arm]
        lines.append(
            f"| {arm} | type_dependencies | 13 | {compliance['required']} | {compliance['known']} | "
            f"{compliance['pass']} | {compliance['fail']} | {compliance['unknown']} |"
        )
    lines.extend([
        "",
        "## Call-target controls",
        "",
        "| Arm | Expected route | Cases | Attempts | Actual first calls | Missing/failed | Unknown |",
        "|---|---|---:|---:|---:|---:|---:|",
    ])
    for arm in ARMS:
        controls = summary["call_target_controls"]["by_arm"][arm]
        lines.append(
            f"| {arm} | call_target | 4 | {controls['required']} | {controls['pass']} | "
            f"{controls['fail']} | {controls['unknown']} |"
        )
    lines.extend([
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
    ])
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
    freeze = validate_freeze(COMPARISON_ROOT / "freeze.json")
    validate_policy_contract(corpus, controls, freeze)
    runs = _load_runs(output, corpus, controls, freeze)
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
    if replay and replay.get('comparison') != VERSION:
        raise ValueError("replay verification uses an incompatible routing protocol")
    if replay and replay.get('protocol') not in {None, VERSION}:
        raise ValueError("replay verification uses an incompatible routing protocol")
    replay_complete = (replay.get('comparison') == VERSION
                       and replay.get('protocol') == VERSION
                       and replay.get('complete') is True
                       and replay.get('expected_runs') == EXPECTED_RUNS
                       and replay.get('verified_runs') == EXPECTED_RUNS
                       and not replay.get('failures'))
    routing_exposure = _routing_exposure(runs, replay_complete)
    initial_type_route_compliance = _initial_type_route_compliance(runs)
    call_target_controls = _call_target_controls(runs)
    numeric_verdict = frozen["verdict"]
    qualification = _qualification_verdict(
        numeric_verdict,
        complete_batch=len(runs) == EXPECTED_RUNS,
        runs=runs,
        replay_complete=replay_complete,
        exposure=routing_exposure,
    )
    routing_failures = [
        {
            "attempt": run.get("directory"),
            "task_id": run.get("task_id"),
            "arm": run.get("arm"),
            "error": error,
        }
        for run in runs
        for error in (run.get("routing_error"), run.get("routing_identity_error"))
        if error
    ]
    summary = {
        "schema_version": 3,
        "protocol": VERSION,
        "comparison": VERSION,
        "method": "all_observed_tool_calls",
        "planned_runs": EXPECTED_RUNS,
        "recorded_runs": len(runs),
        "complete_batch": len(runs) == EXPECTED_RUNS,
        "arms_declared": list(ARMS),
        "arm_labels": dict(ARM_LABELS),
        "manifest": _read_manifest(output),
        "freeze": freeze,
        "preflight": preflight_payload,
        "endpoint_availability": endpoint_by_arm,
        "actual_loci_explore_usage": _usage(runs),
        "raw_failures": _raw_failures(runs),
        "routing_failures": routing_failures,
        "replay_complete": replay_complete,
        **frozen,
        "numeric_verdict": numeric_verdict,
        "routing_exposure": routing_exposure,
        "routing_exposure_status": routing_exposure["exposure_status"],
        "initial_type_route_compliance": initial_type_route_compliance,
        "call_target_controls": call_target_controls,
        "qualification_verdict": qualification,
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
