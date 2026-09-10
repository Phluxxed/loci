"""Aggregate the saved A-only TypeScript context baseline artifacts.

This report is intentionally an accounting layer.  It reads the immutable
corpus for case order and grouping, but it never treats an absent measurement as
zero and never converts authored negative checks into an exhaustive graph
claim.  The complete raw result for every parsed run is retained in
``summary.json`` so the aggregate can be audited or recomputed later.
"""

from __future__ import annotations

import argparse
import json
import math
import statistics
from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from benchmarks.typescript_context_corpus import DEFAULT_ROOT, load_corpus


PLANNED_REPETITIONS = 3
EXPECTED_ARMS = {"A"}
MAINTAINED_CORPUS_GROUP = "maintained_task"
_CAUSAL_INVALID_FAILURES = frozenset({
    "invalid_trace",
    "unaccounted_tool_output",
    "delivery_trace_mismatch",
})


def _finite_number(value: Any) -> int | float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    if not math.isfinite(value):
        return None
    return value


def _nonnegative_number(value: Any) -> int | float | None:
    number = _finite_number(value)
    return number if number is not None and number >= 0 else None


def _json_value(value: Any) -> Any:
    """Return a JSON-safe copy while rejecting non-finite numeric values."""

    return json.loads(json.dumps(value, ensure_ascii=False, allow_nan=False))


def _read_json(path: Path) -> tuple[Any | None, str | None]:
    try:
        return json.loads(path.read_text(encoding="utf-8")), None
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
        return None, f"{type(exc).__name__}: {exc}"


def _relative_path(path: Path, root: Path) -> str:
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


def _metric(values: Sequence[Any]) -> dict[str, Any]:
    """Summarise measured numeric values without hiding nulls."""

    raw = [_finite_number(value) for value in values]
    measured = [value for value in raw if value is not None]
    unavailable = len(raw) - len(measured)
    return {
        "values": raw,
        "median": statistics.median(measured) if measured and unavailable == 0 else None,
        "observed_subset_median": statistics.median(measured) if measured else None,
        "measured_count": len(measured),
        "unavailable_count": unavailable,
        "status": "complete" if raw and unavailable == 0 else "partial" if measured else "unavailable",
    }


def _sum_metric(values: Sequence[Any]) -> dict[str, Any]:
    """Return a measured subtotal and expose an unavailable total when needed."""

    raw = [_nonnegative_number(value) for value in values]
    measured = [value for value in raw if value is not None]
    unavailable = len(raw) - len(measured)
    subtotal = sum(measured)
    return {
        "values": raw,
        "total": subtotal if unavailable == 0 else None,
        "measured_subtotal": subtotal,
        "measured_count": len(measured),
        "unavailable_count": unavailable,
        "status": "complete" if raw and unavailable == 0 else "partial" if measured else "unavailable",
    }


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _display(value: Any) -> str:
    return "unavailable" if value is None else str(value)


def _list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    return []


def _identity_key(identity: Mapping[str, Any]) -> tuple[str, int] | None:
    task_id = identity.get("task_id")
    repetition = identity.get("repetition")
    if (
        not isinstance(task_id, str)
        or isinstance(repetition, bool)
        or not isinstance(repetition, int)
    ):
        return None
    return task_id, repetition


def _spans_accounting(
    artifact: Mapping[str, Any], measurement: Mapping[str, Any]
) -> dict[str, Any]:
    """Derive unique and duplicate source bytes from verified event spans.

    The trace stores every delivery span, including repeats.  Unioning those
    intervals by file gives the within-run unique byte count; the remainder of
    the measured source total is duplicate delivery.  If the artifact has a
    source total but no verifiable spans, duplicate bytes stay unavailable.
    """

    spans: list[tuple[str, int, int]] = []
    malformed = False
    for event in _list(artifact.get("events")):
        if not isinstance(event, Mapping):
            malformed = True
            continue
        for span in _list(event.get("spans")):
            if not isinstance(span, Mapping):
                malformed = True
                continue
            file = span.get("file")
            start = span.get("start_byte")
            end = span.get("end_byte")
            if (
                not isinstance(file, str)
                or isinstance(start, bool)
                or not isinstance(start, int)
                or isinstance(end, bool)
                or not isinstance(end, int)
                or start < 0
                or end <= start
            ):
                malformed = True
                continue
            spans.append((file, start, end))

    span_total = sum(end - start for _, start, end in spans)
    source_total = _nonnegative_number(measurement.get("source_bytes"))
    accounting_failures: list[str] = []
    if source_total is not None and spans and source_total != span_total:
        accounting_failures.append("measurement_source_bytes_mismatch")

    if source_total is None:
        if not spans and not malformed:
            # A trace with no source deliveries has an unambiguous zero total.
            source_total = 0
        elif spans:
            source_total = span_total

    by_file: dict[str, list[tuple[int, int]]] = defaultdict(list)
    for file, start, end in spans:
        by_file[file].append((start, end))
    unique_total = 0
    for intervals in by_file.values():
        cursor_start = cursor_end = None
        for start, end in sorted(intervals):
            if cursor_start is None:
                cursor_start, cursor_end = start, end
            elif start <= cursor_end:
                cursor_end = max(cursor_end, end)
            else:
                unique_total += cursor_end - cursor_start
                cursor_start, cursor_end = start, end
        if cursor_start is not None:
            unique_total += cursor_end - cursor_start

    if source_total is None or malformed or (not spans and source_total):
        duplicate_total = None
        unique_value = unique_total if spans else None
    else:
        duplicate_total = max(source_total - unique_total, 0)
        unique_value = unique_total
    return {
        "source_bytes": source_total,
        "span_bytes": span_total,
        "unique_source_bytes": unique_value,
        "duplicate_source_bytes": duplicate_total,
        "span_status": "complete" if not malformed else "partial",
        "accounting_failures": accounting_failures,
    }


def _provenance(result_path: Path) -> dict[str, Any]:
    value, _ = _read_json(result_path.parent / "provenance.json")
    return dict(value) if isinstance(value, Mapping) else {}


def _failure_categories(baseline: Mapping[str, Any]) -> list[str]:
    categories: list[str] = []
    for failure in _list(baseline.get("failures")):
        if isinstance(failure, Mapping) and isinstance(failure.get("category"), str):
            categories.append(failure["category"])
        else:
            categories.append("unclassified_failure")
    return categories


def _token_value(measurement: Mapping[str, Any], name: str) -> int | None:
    usage = measurement.get("provider_usage")
    if not isinstance(usage, Mapping):
        return None
    value = usage.get(name)
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return None
    return value


def _context_count(measurement: Mapping[str, Any]) -> int | None:
    delivered = measurement.get("required_context_delivered")
    if isinstance(delivered, list):
        return len(delivered)
    if isinstance(delivered, bool) or not isinstance(delivered, int) or delivered < 0:
        return None
    return delivered


def _relationship_value(measurement: Mapping[str, Any], name: str) -> Any:
    relationships = measurement.get("relationships")
    if not isinstance(relationships, Mapping):
        # The runner stores relationships under baseline; this fallback keeps
        # the field unavailable if a hand-authored artifact puts it elsewhere.
        return None
    return relationships.get(name)


def _load_run(result_path: Path, output: Path) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    artifact, error = _read_json(result_path)
    if error is not None or not isinstance(artifact, Mapping):
        return None, {
            "path": _relative_path(result_path, output),
            "category": "invalid_result",
            "error": error or "result.json must contain a JSON object",
        }

    identity = dict(_mapping(artifact.get("identity")))
    measurement = dict(_mapping(artifact.get("measurement")))
    baseline = dict(_mapping(artifact.get("baseline")))
    provenance = _provenance(result_path)
    accounting = _spans_accounting(artifact, measurement)
    index_seconds = _nonnegative_number(provenance.get("index_seconds"))
    if index_seconds is None:
        index_seconds = _nonnegative_number(baseline.get("index_seconds"))
    failures = _list(baseline.get("failures"))
    failure_categories = _failure_categories(baseline)
    if measurement.get("task_correct") is False and measurement.get("outcome") == "completed":
        failure_categories.append("incorrect_answer")
    delivery_verified = baseline.get("tool_delivery_verified") is True
    causal_inconclusive = (
        not delivery_verified
        or bool(_CAUSAL_INVALID_FAILURES.intersection(failure_categories))
    )
    raw_avoidable_reads = measurement.get("avoidable_reads")
    raw_proven_avoidable_reads = measurement.get("proven_avoidable_reads")
    run = {
        "path": _relative_path(result_path, output),
        "identity": identity,
        "identity_key": [identity.get("task_id"), identity.get("repetition")],
        "measurement": measurement,
        "baseline": baseline,
        "provenance": provenance,
        "derived": {
            **accounting,
            "index_seconds": index_seconds,
            "end_to_end_seconds": _nonnegative_number(baseline.get("end_to_end_seconds")),
            "actual_process_seconds": _nonnegative_number(baseline.get("actual_process_seconds")),
            "failure_categories": failure_categories,
            "delivery_verified": delivery_verified,
            "causal_avoidable_reads": None if causal_inconclusive else raw_avoidable_reads,
            "causal_proven_avoidable_reads": raw_proven_avoidable_reads,
            "causal_lineage_status": "inconclusive" if causal_inconclusive else measurement.get("lineage_status"),
            "causal_inconclusive_reason": (
                "tool delivery is not verified or trace delivery failed"
                if causal_inconclusive
                else None
            ),
            "token_values": {
                "gross_input_tokens": _token_value(measurement, "input_tokens"),
                "cached_input_tokens": _token_value(measurement, "cached_input_tokens"),
                "output_tokens": _token_value(measurement, "output_tokens"),
            },
            "relationship_values": {
                "available_dependency_links": _relationship_value(
                    baseline, "available_dependency_links_total"
                ),
                "delivered_dependency_links": _relationship_value(
                    baseline, "delivered_dependency_links_total"
                ),
                "forbidden_proven_relationships": _relationship_value(
                    baseline, "forbidden_proven_relationships"
                ),
            },
            "accounting_failures": accounting["accounting_failures"],
            "failure_count": len(failures),
            "required_context_delivered_count": _context_count(measurement),
        },
        # Keep the source artifact, including every raw event and measurement.
        "raw_result": _json_value(artifact),
    }
    return run, None


def _partial_attempt_directories(output: Path) -> list[dict[str, Any]]:
    attempt_files = ("adapter-trace.json", "provenance.json", "events.jsonl")
    partial: list[dict[str, Any]] = []
    if not output.exists():
        return partial
    for directory in sorted(path for path in output.rglob("*") if path.is_dir()):
        present = [name for name in attempt_files if (directory / name).is_file()]
        if present and not (directory / "result.json").is_file():
            partial.append({
                "path": _relative_path(directory, output),
                "present_files": present,
                "category": "partial_attempt",
            })
    return partial


def _case_group(case: Mapping[str, Any]) -> str:
    return "maintained3" if case.get("group") == MAINTAINED_CORPUS_GROUP else "fixture14"


def _measurement_values(
    runs: Sequence[Mapping[str, Any]], name: str
) -> list[Any]:
    return [
        _mapping(run.get("measurement")).get(name)
        for run in runs
    ]


def _authoritative_measurement_values(
    runs: Sequence[Mapping[str, Any]], name: str, *, require_delivery: bool = False
) -> list[Any]:
    values: list[Any] = []
    for run in runs:
        if require_delivery and _mapping(run.get("derived")).get("delivery_verified") is not True:
            values.append(None)
        else:
            values.append(_mapping(run.get("measurement")).get(name))
    return values


def _derived_values(
    runs: Sequence[Mapping[str, Any]], name: str
) -> list[Any]:
    return [_mapping(run.get("derived")).get(name) for run in runs]


def _token_values(runs: Sequence[Mapping[str, Any]], name: str) -> list[Any]:
    return [
        _mapping(run.get("derived")).get("token_values", {}).get(name)
        for run in runs
    ]


def _relationship_values(runs: Sequence[Mapping[str, Any]], name: str) -> list[Any]:
    return [
        _mapping(run.get("derived")).get("relationship_values", {}).get(name)
        for run in runs
    ]


def _case_summary(
    case: Mapping[str, Any], runs: Sequence[Mapping[str, Any]], duplicate_keys: set[tuple[str, int]]
) -> dict[str, Any]:
    case_id = case["id"]
    expected_keys = {(case_id, repetition) for repetition in range(1, PLANNED_REPETITIONS + 1)}
    observed_keys = {
        key for run in runs
        if (key := _identity_key(_mapping(run.get("identity")))) is not None
    }
    correct_values = [
        _mapping(run.get("measurement")).get("task_correct")
        if isinstance(_mapping(run.get("measurement")).get("task_correct"), bool)
        else None
        for run in runs
    ]
    correct_count = sum(value is True for value in correct_values)
    case_eligible = (
        len(runs) == PLANNED_REPETITIONS
        and observed_keys == expected_keys
        and not any(key in duplicate_keys for key in expected_keys)
        and correct_values == [True, True, True]
    )
    if case_eligible:
        eligibility_reason = "three planned repetitions are exactly correct"
    elif len(runs) != PLANNED_REPETITIONS:
        eligibility_reason = "not all three repetitions were recorded"
    elif observed_keys != expected_keys:
        eligibility_reason = "planned case/repetition identity is missing or unexpected"
    elif any(key in duplicate_keys for key in expected_keys):
        eligibility_reason = "duplicate planned case/repetition identity"
    else:
        eligibility_reason = "case correctness is not 3/3"

    outcomes = [
        _mapping(run.get("measurement")).get("outcome")
        for run in runs
    ]
    failure_categories = Counter(
        category
        for run in runs
        for category in _mapping(run.get("derived")).get("failure_categories", [])
    )
    return {
        "id": case_id,
        "group": _case_group(case),
        "corpus_group": case.get("group"),
        "expected_repetitions": PLANNED_REPETITIONS,
        "recorded_repetitions": len(runs),
        "eligible": case_eligible,
        "eligibility_reason": eligibility_reason,
        "correctness": {
            "values": correct_values,
            "correct_count": correct_count,
            "incorrect_count": sum(value is False for value in correct_values),
            "unavailable_count": sum(value is None for value in correct_values),
        },
        "outcomes": {"values": outcomes, "counts": dict(sorted(Counter(_display(value) for value in outcomes).items()))},
        "failure_categories": dict(sorted(failure_categories.items())),
        "medians": {
            "avoidable_reads": _metric(_derived_values(runs, "causal_avoidable_reads")),
            "proven_avoidable_reads": _metric(
                _derived_values(runs, "causal_proven_avoidable_reads")
            ),
            "context_recall": _metric(_measurement_values(runs, "context_recall")),
            "required_context_delivered": _metric(
                _derived_values(runs, "required_context_delivered_count")
            ),
            "required_context_total": _metric(_measurement_values(runs, "required_context_total")),
            "read_count": _metric(_measurement_values(runs, "read_count")),
            "tool_elapsed_ms": _metric(_measurement_values(runs, "tool_elapsed_ms")),
            "serialized_tool_output_bytes": _metric(
                _authoritative_measurement_values(
                    runs, "serialized_tool_output_bytes", require_delivery=True
                )
            ),
            "source_bytes": _metric(_derived_values(runs, "source_bytes")),
            "unique_source_bytes": _metric(_derived_values(runs, "unique_source_bytes")),
            "duplicate_source_bytes": _metric(_derived_values(runs, "duplicate_source_bytes")),
            "index_seconds": _metric(_derived_values(runs, "index_seconds")),
            "end_to_end_seconds": _metric(_derived_values(runs, "end_to_end_seconds")),
            "actual_process_seconds": _metric(_derived_values(runs, "actual_process_seconds")),
            "gross_input_tokens": _metric(_token_values(runs, "gross_input_tokens")),
            "cached_input_tokens": _metric(_token_values(runs, "cached_input_tokens")),
            "output_tokens": _metric(_token_values(runs, "output_tokens")),
        },
        "relationships": {
            "available_dependency_links": _metric(
                _relationship_values(runs, "available_dependency_links")
            ),
            "delivered_dependency_links": _metric(
                _relationship_values(runs, "delivered_dependency_links")
            ),
            "forbidden_proven_relationships": _metric(
                _relationship_values(runs, "forbidden_proven_relationships")
            ),
            "scope": "authored frozen negatives only; not exhaustive unsupported-edge truth",
        },
    }


def _group_summary(
    group: str, cases: Sequence[Mapping[str, Any]], runs: Sequence[Mapping[str, Any]]
) -> dict[str, Any]:
    outcomes = Counter(
        _display(_mapping(run.get("measurement")).get("outcome")) for run in runs
    )
    failures = Counter(
        category
        for run in runs
        for category in _mapping(run.get("derived")).get("failure_categories", [])
    )
    def relationship(name: str) -> list[Any]:
        return [
            _mapping(run.get("derived")).get("relationship_values", {}).get(name)
            for run in runs
        ]

    return {
        "case_count": len(cases),
        "case_ids": [case["id"] for case in cases],
        "run_count": len(runs),
        "eligible_case_count": sum(bool(case.get("eligible")) for case in cases),
        "eligible_case_ids": [case["id"] for case in cases if case.get("eligible")],
        "outcomes": dict(sorted(outcomes.items())),
        "failure_categories": dict(sorted(failures.items())),
        "medians": {
            "context_recall": _metric(_measurement_values(runs, "context_recall")),
            "avoidable_reads": _metric(_derived_values(runs, "causal_avoidable_reads")),
            "serialized_tool_output_bytes": _metric(
                _authoritative_measurement_values(
                    runs, "serialized_tool_output_bytes", require_delivery=True
                )
            ),
            "source_bytes": _metric(_derived_values(runs, "source_bytes")),
            "duplicate_source_bytes": _metric(_derived_values(runs, "duplicate_source_bytes")),
            "available_dependency_links": _metric(relationship("available_dependency_links")),
            "delivered_dependency_links": _metric(relationship("delivered_dependency_links")),
            "forbidden_proven_relationships": _metric(
                relationship("forbidden_proven_relationships")
            ),
        },
    }


def _costs(runs: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    token_values = {
        name: [
            _mapping(run.get("derived")).get("token_values", {}).get(name)
            for run in runs
        ]
        for name in ("gross_input_tokens", "cached_input_tokens", "output_tokens")
    }
    recorded_json = _sum_metric(
        _measurement_values(runs, "serialized_tool_output_bytes")
    )
    accountable_json = _sum_metric([
        value
        if _mapping(run.get("derived")).get("delivery_verified") is True
        else None
        for run, value in zip(runs, _measurement_values(runs, "serialized_tool_output_bytes"))
    ])
    accountable_json["recorded_subtotal"] = recorded_json["measured_subtotal"]
    accountable_json["recorded_measured_count"] = recorded_json["measured_count"]
    accountable_json["recorded_unavailable_count"] = recorded_json["unavailable_count"]
    return {
        "serialized_tool_output_bytes": accountable_json,
        "source_bytes": _sum_metric(_derived_values(runs, "source_bytes")),
        "unique_source_bytes": _sum_metric(_derived_values(runs, "unique_source_bytes")),
        "duplicate_source_bytes": _sum_metric(_derived_values(runs, "duplicate_source_bytes")),
        "provider_tokens": {name: _sum_metric(values) for name, values in token_values.items()},
        "estimated_source_tokens": _sum_metric(
            _measurement_values(runs, "estimated_source_tokens")
        ),
        "accounting_complete": bool(runs) and all(
            _mapping(run.get("derived")).get("delivery_verified") is True
            for run in runs
        ),
    }


def _latency_p95(runs: Sequence[Mapping[str, Any]], maintained_case_ids: set[str]) -> dict[str, Any]:
    expected_keys = {
        (case_id, repetition)
        for case_id in maintained_case_ids
        for repetition in range(1, PLANNED_REPETITIONS + 1)
    }
    candidate_runs = [
        run for run in runs
        if _identity_key(_mapping(run.get("identity"))) in expected_keys
        and _mapping(run.get("identity")).get("arm") == "A"
    ]
    by_key: dict[tuple[str, int], list[Mapping[str, Any]]] = defaultdict(list)
    for run in candidate_runs:
        key = _identity_key(_mapping(run.get("identity")))
        if key is not None:
            by_key[key].append(run)
    unique_runs = [records[0] for key, records in sorted(by_key.items()) if len(records) == 1]
    missing_keys = sorted(expected_keys - set(by_key))
    duplicate_keys = sorted(key for key, records in by_key.items() if len(records) > 1)
    values = [_mapping(run.get("derived")).get("end_to_end_seconds") for run in unique_runs]
    measured = [_finite_number(value) for value in values]
    missing = sum(value is None for value in measured)
    required = len(maintained_case_ids) * PLANNED_REPETITIONS
    result: dict[str, Any] = {
        "method": "nearest_rank",
        "quantile": 0.95,
        "values": measured,
        "sample_count": len(unique_runs),
        "candidate_run_count": len(candidate_runs),
        "required_sample_count": required,
        "missing_count": missing,
        "missing_identities": [list(key) for key in missing_keys],
        "duplicate_identities": [list(key) for key in duplicate_keys],
        "includes_failures": True,
        "failure_run_count": sum(
            _mapping(run.get("measurement")).get("outcome") != "completed"
            for run in unique_runs
        ),
        "status": "unavailable",
        "p95_seconds": None,
    }
    if required and not missing_keys and not duplicate_keys and len(unique_runs) == required and missing == 0:
        rank = max(1, math.ceil(result["quantile"] * required))
        result.update({
            "rank": rank,
            "status": "measured",
            "p95_seconds": sorted(value for value in measured if value is not None)[rank - 1],
        })
    elif missing_keys or duplicate_keys or len(unique_runs) != required:
        result["unavailable_reason"] = "maintained sample is not the planned nine runs"
    else:
        result["unavailable_reason"] = "one or more maintained latency values are unavailable"
    return result


def generate_report(output: Path) -> dict[str, Any]:
    """Aggregate all saved ``*/result.json`` artifacts below ``output``.

    The return value is the same object written to ``summary.json``.  Every
    parsed run remains in ``runs`` and every malformed result remains in
    ``invalid_results``; no run is silently dropped from cost totals.
    """

    output = Path(output).resolve()
    corpus = load_corpus(DEFAULT_ROOT)
    cases = list(corpus["cases"])
    case_by_id = {case["id"]: case for case in cases}
    expected_keys = [
        (case["id"], repetition)
        for case in cases
        for repetition in range(1, PLANNED_REPETITIONS + 1)
    ]
    expected_set = set(expected_keys)

    runs: list[dict[str, Any]] = []
    invalid_results: list[dict[str, Any]] = []
    partial_attempt_directories = _partial_attempt_directories(output)
    for result_path in sorted(output.rglob("result.json")) if output.exists() else []:
        run, invalid = _load_run(result_path, output)
        if run is not None:
            runs.append(run)
        elif invalid is not None:
            invalid_results.append(invalid)

    def sort_key(run: Mapping[str, Any]) -> tuple[int, int, str]:
        identity = _mapping(run.get("identity"))
        key = _identity_key(identity)
        try:
            position = expected_keys.index(key)
        except ValueError:
            position = len(expected_keys)
        repetition = key[1] if key is not None else 0
        return position, repetition, str(run.get("path"))

    runs.sort(key=sort_key)
    key_to_runs: dict[tuple[Any, Any], list[dict[str, Any]]] = defaultdict(list)
    invalid_identity_paths: list[str] = []
    for run in runs:
        identity = _mapping(run.get("identity"))
        key = _identity_key(identity)
        if key is None:
            invalid_identity_paths.append(run["path"])
            continue
        key_to_runs[key].append(run)
    duplicate_keys = {
        key for key, records in key_to_runs.items()
        if len(records) > 1 and key in expected_set
    }
    observed_keys = set(key_to_runs)
    missing_keys = sorted(expected_set - observed_keys, key=lambda key: expected_keys.index(key))
    unexpected_keys = sorted(observed_keys - expected_set, key=lambda key: (str(key[0]), str(key[1])))
    arm_mismatches = [
        run["path"] for run in runs
        if _mapping(run.get("identity")).get("arm") not in EXPECTED_ARMS
    ]
    complete_batch = (
        len(runs) == len(expected_keys)
        and len(observed_keys) == len(expected_keys)
        and not missing_keys
        and not unexpected_keys
        and not duplicate_keys
        and not invalid_results
        and not invalid_identity_paths
        and not arm_mismatches
        and not partial_attempt_directories
    )

    case_summaries: list[dict[str, Any]] = []
    case_runs: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for run in runs:
        task_id = _mapping(run.get("identity")).get("task_id")
        if isinstance(task_id, str) and task_id in case_by_id:
            case_runs[task_id].append(run)
    for case in cases:
        case_summaries.append(_case_summary(case, case_runs[case["id"]], duplicate_keys))

    grouped_cases: dict[str, list[dict[str, Any]]] = {"fixture14": [], "maintained3": []}
    for case_summary in case_summaries:
        grouped_cases[case_summary["group"]].append(case_summary)
    group_summaries = {
        group: _group_summary(
            group,
            group_cases,
            [run for case in group_cases for run in case_runs[case["id"]]],
        )
        for group, group_cases in grouped_cases.items()
    }
    maintained_ids = {
        case["id"] for case in cases if _case_group(case) == "maintained3"
    }

    all_failure_categories = Counter(
        category
        for run in runs
        for category in _mapping(run.get("derived")).get("failure_categories", [])
    )
    all_failure_categories.update(item["category"] for item in invalid_results)
    all_failure_categories.update("invalid_identity" for _ in invalid_identity_paths)
    all_failure_categories.update("partial_attempt" for _ in partial_attempt_directories)
    accounting_failures = Counter(
        failure
        for run in runs
        for failure in _mapping(run.get("derived")).get("accounting_failures", [])
    )
    eligible_case_ids = [case["id"] for case in case_summaries if case["eligible"]]
    environment, environment_error = _read_json(output / "environment.json")
    accounting_complete = (
        complete_batch
        and bool(runs)
        and all(
            _mapping(run.get("derived")).get("delivery_verified") is True
            for run in runs
        )
    )

    summary: dict[str, Any] = {
        "schema_version": 1,
        "arm": "A",
        "purpose": "Current retrieval baseline accounting; no candidate or improvement claim.",
        "input_root": str(output),
        "accounting_complete": accounting_complete,
        "corpus": {
            "version": corpus.get("version"),
            "case_count": len(cases),
            "fixture_case_count": len(grouped_cases["fixture14"]),
            "maintained_case_count": len(grouped_cases["maintained3"]),
        },
        "batch": {
            "planned_runs": len(expected_keys),
            "recorded_result_files": len(runs) + len(invalid_results),
            "recorded_runs": len(runs),
            "unique_identity_count": len(observed_keys),
            "complete_batch": complete_batch,
            "expected_identity_count": len(expected_keys),
            "missing_identities": [list(key) for key in missing_keys],
            "unexpected_identities": [list(key) for key in unexpected_keys],
            "duplicate_identities": [list(key) for key in sorted(duplicate_keys)],
            "arm_mismatch_paths": arm_mismatches,
            "invalid_identity_paths": invalid_identity_paths,
            "invalid_result_count": len(invalid_results),
            "partial_attempt_directories": partial_attempt_directories,
            "accounting_complete": accounting_complete,
            "all_costs_counted_for_parsed_runs": accounting_complete,
        },
        "eligibility": {
            "rule": "A case is eligible only when its three planned repetitions are all task_correct=true.",
            "eligible_case_ids": eligible_case_ids,
            "eligible_case_count": len(eligible_case_ids),
            "ineligible_case_ids": [case["id"] for case in case_summaries if not case["eligible"]],
        },
        "costs": {**_costs(runs), "accounting_complete": accounting_complete},
        "latency": {
            "index_seconds": _metric(_derived_values(runs, "index_seconds")),
            "end_to_end_seconds": _metric(_derived_values(runs, "end_to_end_seconds")),
            "actual_process_seconds": _metric(_derived_values(runs, "actual_process_seconds")),
            "maintained_p95_end_to_end_seconds": _latency_p95(runs, maintained_ids),
        },
        "context_and_causality": {
            "context_recall": _metric(_measurement_values(runs, "context_recall")),
            "required_context_delivered": _metric(
                _derived_values(runs, "required_context_delivered_count")
            ),
            "avoidable_reads": _metric(_derived_values(runs, "causal_avoidable_reads")),
            "proven_avoidable_reads": _metric(
                _derived_values(runs, "causal_proven_avoidable_reads")
            ),
            "null_or_inconclusive_runs": [
                run["path"]
                for run in runs
                if _mapping(run.get("derived")).get("causal_avoidable_reads") is None
                or _mapping(run.get("derived")).get("causal_lineage_status") == "inconclusive"
            ],
            "inconclusive_is_not_zero": True,
        },
        "relationships": {
            "available_dependency_links": _metric([
                _mapping(run.get("derived")).get("relationship_values", {}).get(
                    "available_dependency_links"
                )
                for run in runs
            ]),
            "delivered_dependency_links": _metric([
                _mapping(run.get("derived")).get("relationship_values", {}).get(
                    "delivered_dependency_links"
                )
                for run in runs
            ]),
            "forbidden_proven_relationships": _metric([
                _mapping(run.get("derived")).get("relationship_values", {}).get(
                    "forbidden_proven_relationships"
                )
                for run in runs
            ]),
            "forbidden_scope": (
                "proven_forbidden relationship count is limited to authored frozen "
                "negatives; it is not exhaustive unsupported-edge truth"
            ),
        },
        "failure_categories": dict(sorted(all_failure_categories.items())),
        "accounting_failures": dict(sorted(accounting_failures.items())),
        "invalid_results": invalid_results,
        "groups": group_summaries,
        "cases": case_summaries,
        "environment": environment if isinstance(environment, Mapping) else None,
        "environment_status": "available" if environment_error is None and environment is not None else "unavailable",
        "environment_error": environment_error,
        "runs": runs,
    }
    _write_report(output, summary)
    return summary


def _format_metric(metric: Mapping[str, Any], suffix: str = "") -> str:
    median = metric.get("median")
    if median is None:
        return "unavailable"
    status = metric.get("status")
    value = f"{median:g}" if isinstance(median, (int, float)) else str(median)
    return value + suffix + (" (partial)" if status == "partial" else "")


def _write_report(output: Path, summary: Mapping[str, Any]) -> None:
    output.mkdir(parents=True, exist_ok=True)
    (output / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    batch = _mapping(summary.get("batch"))
    eligibility = _mapping(summary.get("eligibility"))
    costs = _mapping(summary.get("costs"))
    latency = _mapping(summary.get("latency"))
    context = _mapping(summary.get("context_and_causality"))
    groups = _mapping(summary.get("groups"))
    lines = [
        "# TypeScript context A-only baseline report",
        "",
        "This report aggregates the saved current-retrieval baseline artifacts. It contains no candidate comparison or improvement claim.",
        "",
        "## Batch and eligibility",
        "",
        f"- Batch: **{'complete' if batch.get('complete_batch') else 'incomplete'}**; {batch.get('unique_identity_count', 0)}/{batch.get('expected_identity_count', 0)} unique planned case/repetition identities.",
        f"- Parsed result files: {batch.get('recorded_result_files', 0)}; recorded cost fields are retained. Complete accounting: {'yes' if summary.get('accounting_complete') else 'no'}.",
        f"- Eligible cases: {eligibility.get('eligible_case_count', 0)}/{summary.get('corpus', {}).get('case_count', 0)}; eligibility requires correctness 3/3.",
        "",
        "## Group medians",
        "",
        "| Group | Cases | Runs | Eligible | Context recall | Avoidable reads | JSON bytes | Source bytes | Delivered links |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for group in ("fixture14", "maintained3"):
        data = _mapping(groups.get(group))
        medians = _mapping(data.get("medians"))
        lines.append(
            f"| {group} | {data.get('case_count', 0)} | {data.get('run_count', 0)} | {data.get('eligible_case_count', 0)} | "
            f"{_format_metric(_mapping(medians.get('context_recall')))} | "
            f"{_format_metric(_mapping(medians.get('avoidable_reads')))} | "
            f"{_format_metric(_mapping(medians.get('serialized_tool_output_bytes')))} | "
            f"{_format_metric(_mapping(medians.get('source_bytes')))} | "
            f"{_format_metric(_mapping(medians.get('delivered_dependency_links')))} |"
        )

    p95 = _mapping(latency.get("maintained_p95_end_to_end_seconds"))
    lines.extend([
        "",
        "## Costs and latency",
        "",
        f"- Recorded JSON subtotal: {_display(_mapping(costs.get('serialized_tool_output_bytes')).get('recorded_subtotal'))} bytes; incomplete delivery accounting prevents a complete total.",
        f"- JSON tool-output bytes: {_display(_mapping(costs.get('serialized_tool_output_bytes')).get('total'))}; source bytes: {_display(_mapping(costs.get('source_bytes')).get('total'))}; duplicate source bytes: {_display(_mapping(costs.get('duplicate_source_bytes')).get('total'))}.",
        f"- Provider tokens: gross input {_display(_mapping(_mapping(costs.get('provider_tokens')).get('gross_input_tokens')).get('total'))}, cached input {_display(_mapping(_mapping(costs.get('provider_tokens')).get('cached_input_tokens')).get('total'))}, output {_display(_mapping(_mapping(costs.get('provider_tokens')).get('output_tokens')).get('total'))}; missing values remain unavailable.",
        f"- Index latency median: {_format_metric(_mapping(latency.get('index_seconds')), ' s')}; end-to-end median: {_format_metric(_mapping(latency.get('end_to_end_seconds')), ' s')}.",
        f"- Maintained end-to-end p95: {_display(p95.get('p95_seconds'))} s ({p95.get('method', 'nearest_rank')}, sample {p95.get('sample_count', 0)}/{p95.get('required_sample_count', 0)}, failures included).",
        "",
        "## Context, causality, and relationships",
        "",
        f"- Context recall median: {_format_metric(_mapping(context.get('context_recall')))}; avoidable-read median: {_format_metric(_mapping(context.get('avoidable_reads')))}.",
        f"- Runs with null or inconclusive avoidable-read accounting: {len(context.get('null_or_inconclusive_runs', []))}; these values are not treated as zero.",
        f"- Available dependency links median: {_format_metric(_mapping(_mapping(summary.get('relationships')).get('available_dependency_links')))}; delivered dependency links median: {_format_metric(_mapping(_mapping(summary.get('relationships')).get('delivered_dependency_links')))}.",
        f"- Proven forbidden relationships median: {_format_metric(_mapping(_mapping(summary.get('relationships')).get('forbidden_proven_relationships')))}. This counts authored frozen negative checks only and is not exhaustive unsupported-edge truth.",
        "",
        "## Per-case outcomes",
        "",
        "| Case | Group | Runs | Correct | Eligible | Outcomes | Context recall median | Avoidable reads median |",
        "| --- | --- | ---: | ---: | --- | --- | ---: | ---: |",
    ])
    for case in _list(summary.get("cases")):
        if not isinstance(case, Mapping):
            continue
        medians = _mapping(case.get("medians"))
        outcomes = ", ".join(
            f"{key}={value}" for key, value in _mapping(case.get("outcomes")).get("counts", {}).items()
        )
        correctness = _mapping(case.get("correctness"))
        lines.append(
            f"| {case.get('id')} | {case.get('group')} | {case.get('recorded_repetitions', 0)} | {correctness.get('correct_count', 0)}/3 | "
            f"{'yes' if case.get('eligible') else 'no'} | {outcomes or 'unavailable'} | "
            f"{_format_metric(_mapping(medians.get('context_recall')))} | {_format_metric(_mapping(medians.get('avoidable_reads')))} |"
        )
    lines.extend([
        "",
        "## Failure categories",
        "",
        f"`{json.dumps(summary.get('failure_categories', {}), sort_keys=True)}`",
        "",
        "Raw measurements, provider usage (when present), failure objects, causal classifications, relationship blocks, and source events are retained per run in `summary.json` under `runs`.",
    ])
    (output / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    summary = generate_report(args.output)
    print(json.dumps({
        "report": str((Path(args.output).resolve() / "report.md")),
        "summary": str((Path(args.output).resolve() / "summary.json")),
        "complete_batch": summary["batch"]["complete_batch"],
        "recorded_runs": summary["batch"]["recorded_runs"],
    }, sort_keys=True))


if __name__ == "__main__":
    main()
