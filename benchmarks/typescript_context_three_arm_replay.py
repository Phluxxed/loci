"""Verify and independently replay a frozen TypeScript context ABC batch.

The three-arm runner retains two different kinds of evidence for every
attempt: the adapter's exact v3 observation trace and the host/provider event
stream.  This module checks both streams against the retained result and
recomputes the observed measurement from them.  It deliberately does not
decide whether an answer is good enough for a comparison gate; an incorrect
answer, timeout, budget exhaustion, or other recorded task failure remains a
valid run outcome when its evidence is internally consistent.

Relationship measurements require an index.  When ``--engine-root`` is
provided, each arm is replayed in a separate subprocess with the selected
engine source first on ``PYTHONPATH``.  This keeps the pinned A/B runtimes
separate from the current C implementation.  The raw trace/accounting replay
does not require an engine and is always performed.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
from pathlib import Path
import subprocess
import sys
import tempfile
from typing import Any, Iterable, Mapping

from benchmarks.typescript_context_corpus import (
    _isolated_store,
    load_controls,
    load_corpus,
    materialize_snapshot,
)
from benchmarks.typescript_context_observed import (
    measure as observed_measure,
    reconcile_observed,
    replay_trace,
)


ROOT = Path(__file__).resolve().parents[1]
COMPARISON = "typescript-context-three-arm-v1"
DEFAULT_CORPUS_ROOT = ROOT / "benchmarks" / "corpora" / "typescript-context-v3"
DEFAULT_COMPARISON_ROOT = ROOT / "benchmarks" / "comparisons" / COMPARISON
ARMS = ("A", "B", "C")
ARM_ORDERS = (("A", "B", "C"), ("B", "C", "A"), ("C", "A", "B"))
CASE_COUNT = 17
REPETITIONS = 3
EXPECTED_RUNS = CASE_COUNT * REPETITIONS * len(ARMS)


def _failure(
    failures: list[dict[str, Any]],
    scope: str,
    category: str,
    message: str,
    **extra: Any,
) -> None:
    item: dict[str, Any] = {
        "scope": scope,
        "category": category,
        "message": str(message)[:1000],
    }
    item.update(extra)
    failures.append(item)


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _safe_json(
    path: Path,
    failures: list[dict[str, Any]],
    scope: str,
) -> Any | None:
    try:
        return _read_json(path)
    except Exception as exc:  # malformed retained evidence is a run failure
        _failure(failures, scope, "invalid_json", f"{path.name}: {type(exc).__name__}: {exc}")
        return None


def _finite_number(value: Any) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(float(value))
    )


def planned_attempts(corpus: Mapping[str, Any], controls: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Construct the exact frozen 17 x 3 x 3 ABC plan.

    This is intentionally repeated here instead of trusting a saved summary
    or report.  The identity set is part of the verifier's input contract.
    """

    cases = corpus.get("cases")
    case_ids = controls.get("case_ids")
    schedule = controls.get("schedule")
    arms = controls.get("arms")
    if corpus.get("version") != "typescript-context-v3":
        raise ValueError("typescript-context-v3 corpus required")
    if (
        not isinstance(cases, list)
        or len(cases) != CASE_COUNT
        or not isinstance(case_ids, list)
        or case_ids != [case.get("id") for case in cases]
        or len(set(case_ids)) != CASE_COUNT
        or not isinstance(arms, dict)
        or set(arms) != set(ARMS)
        or not isinstance(schedule, dict)
    ):
        raise ValueError("frozen ABC case or arm identity changed")
    if (
        schedule.get("repetitions") != REPETITIONS
        or schedule.get("case_order") != "corpus_order"
        or schedule.get("arm_orders") != [list(order) for order in ARM_ORDERS]
        or schedule.get("concurrency") != 1
        or schedule.get("planned_runs") != EXPECTED_RUNS
    ):
        raise ValueError("frozen ABC schedule changed")
    result = [
        {
            "attempt_id": f"{case['id']}-r{repetition}-{arm}",
            "case_id": case["id"],
            "snapshot": case["snapshot"],
            "repetition": repetition,
            "arm": arm,
        }
        for case in cases
        for repetition, order in enumerate(ARM_ORDERS, start=1)
        for arm in order
    ]
    if len({item["attempt_id"] for item in result}) != EXPECTED_RUNS:
        raise ValueError("frozen ABC plan contains duplicate attempt identities")
    return result


def _expected_trace_identity(
    corpus: Mapping[str, Any],
    controls: Mapping[str, Any],
    plan: Mapping[str, Any],
    session_id: str,
) -> dict[str, Any]:
    root = Path(str(corpus["_root"]))
    return {
        "task_id": plan["case_id"],
        "session_id": session_id,
        "arm": plan["arm"],
        "repetition": plan["repetition"],
        "snapshot": plan["snapshot"],
        "corpus_sha256": (root / "corpus.sha256").read_text(encoding="utf-8").strip(),
        "controls_sha256": (root / "comparison-controls.sha256").read_text(encoding="utf-8").strip(),
        "controls_version": controls["version"],
    }


def _load_jsonl(
    path: Path,
    failures: list[dict[str, Any]],
    scope: str,
) -> list[dict[str, Any]]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except Exception as exc:
        _failure(failures, scope, "missing_raw_events", f"{path.name}: {type(exc).__name__}: {exc}")
        return []
    events: list[dict[str, Any]] = []
    for line_number, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except Exception as exc:
            _failure(
                failures,
                scope,
                "invalid_event_json",
                f"line {line_number}: {type(exc).__name__}: {exc}",
            )
            continue
        if not isinstance(value, dict):
            _failure(failures, scope, "invalid_event_record", f"line {line_number} is not an object")
            continue
        events.append(value)
    return events


def _sequence_contains(expected: Iterable[Any], actual: Any) -> bool:
    """Return whether every expected failure object is retained in a list."""

    if not isinstance(actual, list):
        return False
    remaining = list(actual)
    for item in expected:
        try:
            remaining.remove(item)
        except ValueError:
            return False
    return True


def _provider_usage(events: list[dict[str, Any]]) -> Any:
    turns = [event for event in events if event.get("type") == "turn.completed"]
    return turns[-1].get("usage") if turns else None


def _check_provenance(
    directory: Path,
    result: Mapping[str, Any],
    plan: Mapping[str, Any],
    corpus: Mapping[str, Any],
    controls: Mapping[str, Any],
    failures: list[dict[str, Any]],
) -> bool:
    """Check optional retained provenance when the runner wrote it.

    The trace itself is the required source identity.  Provenance is checked
    when present so an older partial failure artifact can still be replayed,
    while the measured ABC runner receives the stronger snapshot fingerprint
    check.
    """

    path = directory / "provenance.json"
    if not path.is_file():
        return False
    provenance = _safe_json(path, failures, directory.name + "/provenance")
    if not isinstance(provenance, dict):
        return True
    if "provenance" in result and result.get("provenance") != provenance:
        _failure(failures, directory.name, "provenance_mismatch", "result.provenance differs from provenance.json")
    expected = {
        "attempt_id": plan["attempt_id"],
        "case_id": plan["case_id"],
        "snapshot": plan["snapshot"],
        "repetition": plan["repetition"],
        "arm": plan["arm"],
    }
    for key, value in expected.items():
        if key in provenance and provenance.get(key) != value:
            _failure(failures, directory.name, "provenance_identity_mismatch", f"provenance.{key} differs from plan")
    root = Path(str(corpus["_root"]))
    for key, value in (
        ("corpus_sha256", (root / "corpus.sha256").read_text(encoding="utf-8").strip()),
        ("controls_sha256", (root / "comparison-controls.sha256").read_text(encoding="utf-8").strip()),
    ):
        if key in provenance and provenance.get(key) != value:
            _failure(failures, directory.name, "provenance_fingerprint_mismatch", f"provenance.{key} differs from frozen input")
    snapshot_files = provenance.get("snapshot_files")
    expected_files = corpus.get("snapshots", {}).get(plan["snapshot"], {}).get("files")
    if snapshot_files is not None and snapshot_files != expected_files:
        _failure(failures, directory.name, "snapshot_fingerprint_mismatch", "provenance snapshot files differ from corpus")
    return True


def _compare_measurement(
    retained: Mapping[str, Any],
    recomputed: Mapping[str, Any],
    runner_failures: list[Any],
    failures: list[dict[str, Any]],
    scope: str,
) -> bool:
    expected = copy.deepcopy(dict(recomputed))
    if runner_failures:
        # The frozen runner intentionally makes a setup/request/measurement
        # failure ineligible even if the lower-level observation was complete.
        expected["measurement_complete"] = False
        expected["task_correct"] = False
    if dict(retained) != expected:
        _failure(failures, scope, "measurement_replay_mismatch", "saved measurement differs from v3 replay")
        return False
    return True


def _compare_baseline(
    retained: Mapping[str, Any],
    recomputed: Mapping[str, Any],
    runner_failures: list[Any],
    plan: Mapping[str, Any],
    failures: list[dict[str, Any]],
    scope: str,
    *,
    include_relationships: bool = False,
) -> bool:
    """Compare every raw-derived baseline field, retaining runner failures."""

    expected = copy.deepcopy(dict(recomputed))
    expected_failures = expected.pop("failures", [])
    retained_failures = retained.get("failures")
    if not isinstance(retained_failures, list):
        _failure(failures, scope, "missing_failure_evidence", "baseline.failures is not a list")
    else:
        expected_full = list(expected_failures)
        expected_full.extend(item for item in runner_failures if item not in expected_full)
        if retained_failures != expected_full:
            _failure(failures, scope, "failure_evidence_mismatch", "retained failures differ from raw replay failures")
    expected["arm"] = plan["arm"]
    expected["attempt_id"] = plan["attempt_id"]
    if runner_failures:
        expected["tool_delivery_verified"] = False
    expected.pop("relationships", None)
    actual = {key: value for key, value in retained.items() if key not in {"failures", "relationships"}}
    if actual != expected:
        _failure(failures, scope, "baseline_replay_mismatch", "saved baseline differs from raw v3 replay")
        return False
    if include_relationships and retained.get("relationships") != recomputed.get("relationships"):
        _failure(failures, scope, "relationship_replay_mismatch", "saved relationships differ from pinned-engine replay")
        return False
    return True


def _verify_attempt(
    directory: Path,
    plan: Mapping[str, Any] | None,
    corpus: Mapping[str, Any],
    controls: Mapping[str, Any],
    global_ids: dict[str, set[Any]],
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    scope = directory.name
    failures: list[dict[str, Any]] = []
    report: dict[str, Any] = {
        "attempt_id": scope,
        "replayed": False,
        "reconciled": False,
        "measurement_replayed": False,
        "accounting_complete": False,
        "usage_available": False,
        "measurement_status": "unknown",
        "valid": False,
        "failures": failures,
    }
    result = _safe_json(directory / "result.json", failures, scope)
    if plan is None:
        _failure(failures, scope, "unexpected_attempt", "attempt directory is not in the frozen 153-attempt plan")
    if not isinstance(result, dict):
        return report, None
    identity = result.get("identity")
    measurement = result.get("measurement")
    baseline = result.get("baseline")
    if not all(isinstance(value, dict) for value in (identity, measurement, baseline)):
        _failure(failures, scope, "invalid_artifact", "result must contain identity, measurement, and baseline objects")
        return report, None
    if result.get("schema_version") != 3 or measurement.get("schema_version") != 3:
        _failure(failures, scope, "artifact_schema_mismatch", "result and measurement must use schema 3")
    if plan is None:
        return report, None
    report.update({
        "task_id": plan["case_id"],
        "arm": plan["arm"],
        "repetition": plan["repetition"],
        "outcome": measurement.get("outcome"),
        "answer_correct": measurement.get("answer_correct"),
        "task_correct": measurement.get("task_correct"),
        "read_count": measurement.get("read_count"),
        "serialized_tool_output_bytes": measurement.get("serialized_tool_output_bytes"),
        "source_bytes": measurement.get("source_bytes"),
        "context_recall": measurement.get("context_recall"),
        "provider_usage": measurement.get("provider_usage"),
        "actual_process_seconds": baseline.get("actual_process_seconds"),
        "index_seconds": None,
        "retained_failures": list(baseline.get("failures", [])) if isinstance(baseline.get("failures"), list) else [],
    })
    expected_top = {"attempt_id": plan["attempt_id"], "arm": plan["arm"]}
    for key, value in expected_top.items():
        if result.get(key) != value:
            _failure(failures, scope, "attempt_identity_mismatch", f"result.{key} differs from plan")
    session_id = identity.get("session_id")
    if not isinstance(session_id, str) or not session_id:
        _failure(failures, scope, "missing_session_id", "identity.session_id is missing")
        session_id = ""
    elif not session_id.startswith(plan["attempt_id"] + "-"):
        _failure(failures, scope, "session_id_format", "session ID is not bound to the planned attempt")
    elif session_id in global_ids["sessions"]:
        _failure(failures, scope, "duplicate_session_id", "session ID is reused")
    else:
        global_ids["sessions"].add(session_id)
    expected_identity = _expected_trace_identity(corpus, controls, plan, session_id)
    if identity != expected_identity:
        _failure(failures, scope, "run_identity_mismatch", "result identity differs from frozen plan or corpus fingerprints")
    if measurement.get("intent_collection") != "not_collected":
        _failure(failures, scope, "intent_collection_exposed", "observed v3 measurement exposes model intent")
    measurement_identity = {key: measurement.get(key) for key in expected_identity}
    if measurement_identity != expected_identity:
        _failure(failures, scope, "measurement_identity_mismatch", "measurement identity differs from trace identity")
    identity_keys = (identity.get("task_id"), identity.get("repetition"), identity.get("arm"))
    if identity_keys in global_ids["identities"]:
        _failure(failures, scope, "duplicate_result_identity", "planned task/repetition/arm identity is reused")
    if all(isinstance(value, (str, int)) and not isinstance(value, bool) for value in identity_keys):
        global_ids["identities"].add(identity_keys)

    events_value = result.get("events")
    if not isinstance(events_value, list):
        _failure(failures, scope, "missing_saved_events", "result.events is not a list")
    trace_path = directory / "adapter-trace.json"
    raw_trace = _safe_json(trace_path, failures, scope + "/trace")
    if not isinstance(raw_trace, dict):
        return report, None
    if raw_trace.get("schema_version") != 3 or raw_trace.get("identity") != identity:
        _failure(failures, scope, "trace_identity_mismatch", "adapter trace schema or identity differs from result")
    if isinstance(events_value, list) and events_value != raw_trace.get("events"):
        _failure(failures, scope, "trace_event_mismatch", "result events differ from adapter trace")
    trace_copy = directory / "adapter-trace-copy.json"
    if trace_copy.is_file() and _safe_json(trace_copy, failures, scope + "/trace-copy") != raw_trace:
        _failure(failures, scope, "trace_copy_mismatch", "adapter-trace-copy.json differs from adapter-trace.json")
    try:
        replayed = replay_trace(corpus, raw_trace)
        if replayed.identity != identity or replayed.events != raw_trace.get("events"):
            raise ValueError("replayed source trace differs from raw trace")
        report["replayed"] = True
    except Exception as exc:
        _failure(failures, scope, "trace_replay_failed", f"{type(exc).__name__}: {exc}")

    trace_events = raw_trace.get("events")
    if isinstance(trace_events, list):
        for event in trace_events:
            event_id = event.get("id") if isinstance(event, dict) else None
            if not isinstance(event_id, str) or not event_id:
                _failure(failures, scope, "missing_trace_event_id", "source trace event has no id")
            elif event_id in global_ids["trace_events"]:
                _failure(failures, scope, "duplicate_trace_event_id", "trace event id is reused")
            elif isinstance(event_id, str):
                global_ids["trace_events"].add(event_id)
    deliveries = raw_trace.get("deliveries")
    if not isinstance(deliveries, list) or raw_trace.get("attempts") != len(deliveries):
        _failure(failures, scope, "invalid_attempt_count", "trace attempts does not equal delivery count")
    elif isinstance(session_id, str):
        expected_delivery_ids = [f"{session_id}/attempt/{number}" for number in range(1, len(deliveries) + 1)]
        actual_delivery_ids = [item.get("attempt_id") if isinstance(item, dict) else None for item in deliveries]
        if actual_delivery_ids != expected_delivery_ids:
            _failure(failures, scope, "invalid_delivery_sequence", "trace delivery IDs are not the exact session sequence")
        for attempt_id in actual_delivery_ids:
            if isinstance(attempt_id, str) and attempt_id in global_ids["delivery_attempts"]:
                _failure(failures, scope, "duplicate_delivery_attempt_id", "delivery attempt ID is reused")
            if isinstance(attempt_id, str):
                global_ids["delivery_attempts"].add(attempt_id)

    events = _load_jsonl(directory / "events.jsonl", failures, scope + "/provider-events")
    events_copy_path = directory / "events.json"
    if events_copy_path.is_file():
        events_copy = _safe_json(events_copy_path, failures, scope + "/provider-events-copy")
        if events_copy != events:
            _failure(failures, scope, "provider_events_copy_mismatch", "events.json differs from events.jsonl")
    if any(not isinstance(event, dict) for event in events):
        _failure(failures, scope, "invalid_provider_event", "provider event stream contains a non-object")
    thread_ids = [event.get("thread_id") for event in events if event.get("type") == "thread.started"]
    provider_thread = baseline.get("provider_thread_id")
    if len(set(thread_ids)) > 1 or len(thread_ids) > 1:
        _failure(failures, scope, "provider_thread_ambiguous", "provider event stream has multiple thread IDs")
    if thread_ids and thread_ids[0] != provider_thread:
        _failure(failures, scope, "provider_thread_mismatch", "provider thread differs from baseline")
    if provider_thread is not None and (not isinstance(provider_thread, str) or not provider_thread):
        _failure(failures, scope, "invalid_provider_thread", "baseline provider thread ID is invalid")
    if isinstance(provider_thread, str) and provider_thread:
        if provider_thread in global_ids["providers"]:
            _failure(failures, scope, "duplicate_provider_thread_id", "provider thread ID is reused")
        global_ids["providers"].add(provider_thread)
    report["usage_available"] = _provider_usage(events) is not None

    accounting: dict[str, Any] = {}
    accounting_ok = False
    try:
        accounting = reconcile_observed(raw_trace, events)
        compare_accounting = copy.deepcopy(accounting)
        compare_accounting.pop("validated_results", None)
        if baseline.get("output_accounting") != compare_accounting:
            _failure(failures, scope + "/accounting", "output_accounting_mismatch", "saved accounting differs from raw event reconciliation")
        else:
            accounting_ok = True
        report["reconciled"] = True
        report["accounting_complete"] = bool(accounting.get("complete") is True)
    except Exception as exc:
        _failure(failures, scope + "/accounting", "reconciliation_failed", f"{type(exc).__name__}: {exc}")

    runner_failures = result.get("runner_failures", [])
    if not isinstance(runner_failures, list):
        _failure(failures, scope, "invalid_runner_failures", "result.runner_failures is not a list")
        runner_failures = []
    elapsed = baseline.get("actual_process_seconds")
    exit_code = baseline.get("exit_code")
    measurement_ok = False
    recomputed_baseline: dict[str, Any] | None = None
    if not _finite_number(elapsed) or elapsed < 0:
        _failure(failures, scope, "invalid_termination", "baseline.actual_process_seconds is invalid")
    elif not isinstance(exit_code, int) or isinstance(exit_code, bool):
        _failure(failures, scope, "invalid_termination", "baseline.exit_code is invalid")
    elif report["replayed"] and report["reconciled"] and accounting_ok:
        try:
            case = next(case for case in corpus["cases"] if case["id"] == plan["case_id"])
            timed_out = measurement.get("outcome") == "timeout"
            recomputed = observed_measure(
                corpus,
                case,
                {"trace_path": str(trace_path)},
                events,
                float(elapsed),
                exit_code,
                timed_out,
                None,
            )
            measurement_ok = _compare_measurement(
                measurement,
                recomputed["measurement"],
                runner_failures,
                failures,
                scope,
            )
            report["measurement_replayed"] = measurement_ok
            report["measurement_status"] = "complete" if measurement.get("measurement_complete") else "inconclusive"
            recomputed_baseline = recomputed["baseline"]
            _compare_baseline(
                baseline,
                recomputed_baseline,
                runner_failures,
                plan,
                failures,
                scope,
            )
            if baseline.get("tool_delivery_verified") != bool(accounting.get("complete") is True and not runner_failures):
                _failure(failures, scope, "delivery_flag_mismatch", "tool_delivery_verified disagrees with retained failure/accounting state")
            if baseline.get("adapter_elapsed_ms") != recomputed_baseline.get("adapter_elapsed_ms"):
                _failure(failures, scope, "adapter_cost_mismatch", "adapter elapsed cost differs from raw trace")
        except Exception as exc:
            _failure(failures, scope, "measurement_replay_failed", f"{type(exc).__name__}: {exc}")
    else:
        _failure(failures, scope, "measurement_replay_unavailable", "trace/accounting evidence was not replayable")

    raw_usage = _provider_usage(events)
    if measurement.get("provider_usage") != raw_usage:
        _failure(failures, scope, "provider_usage_mismatch", "measurement provider usage differs from raw turn.completed event")
    token_status = measurement.get("token_status")
    expected_token_status = "measured" if raw_usage is not None else "unavailable"
    if token_status != expected_token_status:
        _failure(failures, scope, "provider_usage_status_mismatch", "token status differs from raw provider usage availability")

    _check_provenance(directory, result, plan, corpus, controls, failures)
    provenance = _safe_json(directory / "provenance.json", [], scope + "/provenance-summary") if (directory / "provenance.json").is_file() else None
    if isinstance(provenance, dict):
        report["index_seconds"] = provenance.get("index_seconds")
    report["file_hashes"] = {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in (directory / "result.json", directory / "adapter-trace.json", directory / "events.jsonl")
        if path.is_file()
    }
    report["valid"] = not failures
    report["failures"] = failures
    report["raw_failures"] = list(baseline.get("failures", [])) if isinstance(baseline.get("failures"), list) else []
    context = {
        "directory": directory,
        "plan": dict(plan),
        "result": result,
        "events": events,
        "trace_path": trace_path,
        "recomputed_baseline": recomputed_baseline,
        "measurement_ok": measurement_ok,
    }
    return report, context


def _engine_source(engine_root: Path, arm: str) -> Path:
    candidates = (engine_root / arm / "src", engine_root / arm, engine_root / f"{arm}-src")
    for candidate in candidates:
        if (candidate / "loci").is_dir():
            return candidate.resolve()
    raise ValueError(f"pinned engine source for arm {arm} is unavailable under {engine_root}")


def _worker_main(engine_src: Path) -> int:
    """Replay one arm's relationship measurements in its pinned runtime."""

    try:
        spec = json.load(sys.stdin)
        if not isinstance(spec, dict) or not isinstance(spec.get("items"), list):
            raise ValueError("engine replay spec must contain an items list")
        import loci  # resolved through the selected engine environment
        from loci import service
        loci_path = Path(str(getattr(loci, "__file__", ""))).resolve()
        if not loci_path.is_relative_to(engine_src.resolve()):
            raise ValueError("engine replay imported loci outside the selected pinned source")
        from benchmarks.typescript_context_three_arm_tools import measure

        corpus = load_corpus(Path(spec["corpus_root"]))
        indexes: dict[str, Any] = {}
        with tempfile.TemporaryDirectory(prefix="loci-three-arm-replay-") as temporary:
            temporary_root = Path(temporary)
            with _isolated_store(temporary_root / "store"):
                for snapshot in sorted({item["snapshot"] for item in spec["items"]}):
                    repo = temporary_root / snapshot
                    materialize_snapshot(corpus, snapshot, repo)
                    service.index_repo(repo, incremental=False)
                    index = service.get_store().load(repo.resolve())
                    if index is None:
                        raise ValueError(f"pinned engine did not persist index for {snapshot}")
                    indexes[snapshot] = index
                outputs = []
                for item in spec["items"]:
                    case = next(case for case in corpus["cases"] if case["id"] == item["case_id"])
                    events = _load_jsonl(Path(item["events_path"]), [], "worker/events")
                    run = {"trace_path": item["trace_path"]}
                    artifact = measure(
                        corpus,
                        case,
                        run,
                        events,
                        item["elapsed"],
                        item["exit_code"],
                        item["timed_out"],
                        indexes[item["snapshot"]],
                    )
                    baseline = dict(artifact["baseline"])
                    baseline["arm"] = item["arm"]
                    baseline["attempt_id"] = item["attempt_id"]
                    outputs.append({
                        "attempt_id": item["attempt_id"],
                        "measurement": artifact["measurement"],
                        "baseline": baseline,
                    })
        json.dump({"loci_file": str(loci_path), "runs": outputs}, sys.stdout, allow_nan=False)
        return 0
    except Exception as exc:
        json.dump({"error": f"{type(exc).__name__}: {exc}"}, sys.stdout)
        return 2


def _run_pinned_engine_replay(
    contexts: Mapping[str, Mapping[str, Any]],
    corpus_root: Path,
    engine_root: Path,
    comparison_root: Path | None,
    output_root: Path,
    failures: list[dict[str, Any]],
) -> dict[str, Any]:
    """Replay relationship measurements once per arm in isolated subprocesses."""

    result: dict[str, Any] = {
        "status": "skipped",
        "attempts": 0,
        "arms": {},
        "meaning": "Raw trace/accounting replay is independent; pinned engine replay verifies relationship fields when available.",
    }
    grouped: dict[str, list[Mapping[str, Any]]] = {arm: [] for arm in ARMS}
    for context in contexts.values():
        plan = context["plan"]
        # A lower-level failure has no trustworthy relationship output to
        # replay.  Its raw failure remains preserved and independently checked.
        if context.get("measurement_ok") and isinstance(context.get("result", {}).get("baseline"), dict):
            if "relationships" in context["result"]["baseline"]:
                grouped[plan["arm"]].append(context)
    try:
        from benchmarks.typescript_context_three_arm import engine_environment
    except Exception as exc:
        _failure(failures, "engine-replay", "engine_environment_unavailable", str(exc))
        result["status"] = "failed"
        return result
    any_group = False
    engine_pins: dict[str, dict[str, Any]] = {}
    pin_documents = []
    if comparison_root is not None:
        pin_documents.append(comparison_root / "freeze.json")
    pin_documents.append(output_root / "manifest.json")
    for path in pin_documents:
        if not path.is_file():
            continue
        try:
            document = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            _failure(failures, "engine-replay", "invalid_engine_pin_document", f"{path}: {exc}")
            continue
        engines = document.get("engines") if isinstance(document, dict) else None
        if engines is None and isinstance(document, dict):
            engines = document.get("identity", {}).get("freeze", {}).get("engines")
        if isinstance(engines, dict):
            engine_pins.update({arm: value for arm, value in engines.items() if isinstance(value, dict)})
    for arm, arm_contexts in grouped.items():
        if not arm_contexts:
            result["arms"][arm] = {"status": "skipped", "attempts": 0}
            continue
        any_group = True
        try:
            engine_src = _engine_source(engine_root, arm)
            if arm in engine_pins:
                from benchmarks.typescript_context_three_arm import verify_engine

                verify_engine(engine_pins[arm], engine_src)
            spec = {
                "corpus_root": str(corpus_root.resolve()),
                "items": [
                    {
                        "attempt_id": context["plan"]["attempt_id"],
                        "case_id": context["plan"]["case_id"],
                        "snapshot": context["plan"]["snapshot"],
                        "arm": context["plan"]["arm"],
                        "trace_path": str(context["trace_path"].resolve()),
                        "events_path": str((context["directory"] / "events.jsonl").resolve()),
                        "elapsed": context["result"]["baseline"]["actual_process_seconds"],
                        "exit_code": context["result"]["baseline"]["exit_code"],
                        "timed_out": context["result"]["measurement"].get("outcome") == "timeout",
                    }
                    for context in arm_contexts
                ],
            }
            environment = engine_environment(engine_src)
            completed = subprocess.run(
                [sys.executable, "-m", "benchmarks.typescript_context_three_arm_replay", "--worker", "--engine-src", str(engine_src)],
                cwd=ROOT,
                env=environment,
                input=json.dumps(spec, allow_nan=False),
                text=True,
                capture_output=True,
                timeout=600,
                check=False,
            )
            if completed.returncode != 0:
                raise RuntimeError(completed.stdout[-2000:] or completed.stderr[-2000:])
            payload = json.loads(completed.stdout)
            by_attempt = {item["attempt_id"]: item for item in payload.get("runs", [])}
            if len(by_attempt) != len(arm_contexts):
                raise ValueError("pinned engine replay returned the wrong attempt count")
            arm_failures = 0
            for context in arm_contexts:
                attempt_id = context["plan"]["attempt_id"]
                replayed = by_attempt.get(attempt_id)
                if replayed is None:
                    _failure(failures, attempt_id, "engine_replay_missing", "pinned engine omitted an attempt")
                    arm_failures += 1
                    continue
                retained = context["result"]
                if replayed.get("measurement") != retained.get("measurement"):
                    _failure(failures, attempt_id, "engine_measurement_mismatch", "pinned engine measurement differs from retained result")
                    arm_failures += 1
                recomputed_baseline = replayed.get("baseline", {})
                retained_baseline = retained.get("baseline", {})
                for key in ("relationships",):
                    if recomputed_baseline.get(key) != retained_baseline.get(key):
                        _failure(failures, attempt_id, "relationship_replay_mismatch", f"baseline.{key} differs from pinned engine replay")
                        arm_failures += 1
            result["arms"][arm] = {
                "status": "passed" if arm_failures == 0 else "failed",
                "attempts": len(arm_contexts),
                "failures": arm_failures,
                "engine_src": str(engine_src),
                "loci_file": payload.get("loci_file"),
            }
            result["attempts"] += len(arm_contexts)
        except Exception as exc:
            _failure(failures, f"engine-replay/{arm}", "engine_replay_failed", f"{type(exc).__name__}: {exc}")
            result["arms"][arm] = {"status": "failed", "attempts": len(arm_contexts)}
    if any_group:
        result["status"] = "passed" if not any(item.get("scope", "").startswith("engine-replay") or item.get("category", "").startswith("engine_") or item.get("category") in {"engine_measurement_mismatch", "relationship_replay_mismatch"} for item in failures) else "failed"
    return result


def verify(
    output: Path,
    corpus_root: Path = DEFAULT_CORPUS_ROOT,
    comparison_root: Path | None = None,
    engine_root: Path | None = None,
) -> dict[str, Any]:
    """Verify a retained ABC output directory and write its sidecar report."""

    output = Path(output).resolve()
    corpus_root = Path(corpus_root).resolve()
    comparison_root = Path(comparison_root).resolve() if comparison_root is not None else None
    failures: list[dict[str, Any]] = []
    corpus = load_corpus(corpus_root)
    controls = load_controls(corpus)
    plan = planned_attempts(corpus, controls)
    plan_by_id = {item["attempt_id"]: item for item in plan}
    output.mkdir(parents=True, exist_ok=True)
    result_dirs = {
        path.name: path
        for path in output.iterdir()
        if path.is_dir() and (path / "result.json").is_file()
    }
    expected_names = set(plan_by_id)
    if set(result_dirs) != expected_names:
        _failure(
            failures,
            "plan",
            "planned_identity_set_mismatch",
            f"expected exactly {EXPECTED_RUNS} result identities, found {len(result_dirs)} result directories",
            missing=sorted(expected_names - set(result_dirs)),
            unexpected=sorted(set(result_dirs) - expected_names),
        )
    global_ids: dict[str, set[Any]] = {
        "sessions": set(),
        "providers": set(),
        "trace_events": set(),
        "delivery_attempts": set(),
        "identities": set(),
    }
    reports: list[dict[str, Any]] = []
    contexts: dict[str, dict[str, Any]] = {}
    for name in sorted(result_dirs):
        report, context = _verify_attempt(
            result_dirs[name],
            plan_by_id.get(name),
            corpus,
            controls,
            global_ids,
        )
        reports.append(report)
        if context is not None:
            contexts[name] = context
        failures.extend(report.get("failures", []))
    expected_identity_keys = {
        (item["case_id"], item["repetition"], item["arm"]) for item in plan
    }
    if global_ids["identities"] != expected_identity_keys:
        _failure(
            failures,
            "plan",
            "unique_identity_count",
            "recorded identities do not equal the exact frozen 153 identity set",
            unique_identity_count=len(global_ids["identities"]),
        )
    engine_replay = {"status": "skipped", "attempts": 0, "arms": {arm: {"status": "skipped", "attempts": 0} for arm in ARMS}}
    if engine_root is not None:
        engine_replay = _run_pinned_engine_replay(
            contexts,
            corpus_root,
            Path(engine_root).resolve(),
            comparison_root,
            output,
            failures,
        )
    raw_failures = [
        {"attempt_id": report.get("attempt_id"), "failure": failure}
        for report in reports
        for failure in report.get("raw_failures", [])
    ]
    complete_accounting = sum(bool(report.get("accounting_complete")) for report in reports)
    complete_usage = sum(bool(report.get("usage_available")) for report in reports)
    inconclusive_measurements = sum(report.get("measurement_status") == "inconclusive" for report in reports)
    replayed_count = sum(bool(report.get("replayed")) for report in reports)
    reconciled_count = sum(bool(report.get("reconciled")) for report in reports)
    measurement_replayed_count = sum(bool(report.get("measurement_replayed")) for report in reports)
    # Missing usage and incomplete accounting are descriptive measurements.  A
    # tampered retained value still fails through the raw replay comparisons.
    passed = (
        not failures
        and len(result_dirs) == EXPECTED_RUNS
        and len(global_ids["identities"]) == EXPECTED_RUNS
        and all(report.get("valid") for report in reports)
    )
    verification = {
        "schema_version": 1,
        "comparison": COMPARISON,
        "verification_status": "passed" if passed else "failed",
        "passed": passed,
        "planned_count": EXPECTED_RUNS,
        "recorded_count": len(result_dirs),
        "unique_identity_count": len(global_ids["identities"]),
        "replayed_count": replayed_count,
        "reconciled_count": reconciled_count,
        "measurement_replayed_count": measurement_replayed_count,
        "complete_accounting_count": complete_accounting,
        "complete_usage_count": complete_usage,
        "inconclusive_measurement_count": inconclusive_measurements,
        "measurement_replay_skipped": engine_root is None,
        "engine_replay": engine_replay,
        "runs": reports,
        "raw_failures": raw_failures,
        "failures": failures,
        "meaning": (
            "Independent v3 trace, host-event, accounting, provider-usage, and retained-measurement verification. "
            "Incorrect answers, timeouts, budget exhaustion, and other accurately recorded partial outcomes remain valid run facts; "
            "missing or mismatched evidence fails integrity."
        ),
    }
    verification_path = output / "artifact-verification.json"
    verification_path.write_text(json.dumps(verification, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")
    return verification


verify_batch = verify
verify_artifacts = verify


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, help="retained ABC result directory")
    parser.add_argument("--corpus-root", type=Path, default=DEFAULT_CORPUS_ROOT)
    parser.add_argument("--comparison-root", type=Path, default=DEFAULT_COMPARISON_ROOT)
    parser.add_argument("--engine-root", type=Path, help="materialized pinned A/B/C engine root for relationship replay")
    parser.add_argument("--worker", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--engine-src", type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    if args.worker:
        if args.engine_src is None:
            parser.error("--worker requires --engine-src")
        return _worker_main(args.engine_src.resolve())
    if args.output is None:
        parser.error("--output is required")
    try:
        report = verify(args.output, args.corpus_root, args.comparison_root, args.engine_root)
    except Exception as exc:
        output = args.output.resolve()
        output.mkdir(parents=True, exist_ok=True)
        report = {
            "schema_version": 1,
            "comparison": COMPARISON,
            "verification_status": "blocked",
            "passed": False,
            "planned_count": EXPECTED_RUNS,
            "recorded_count": 0,
            "unique_identity_count": 0,
            "failures": [{"scope": "load", "category": "verification_blocked", "message": f"{type(exc).__name__}: {exc}"}],
            "meaning": "The frozen corpus or retained output could not be loaded for independent replay.",
        }
        (output / "artifact-verification.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "output": str(args.output.resolve() / "artifact-verification.json"),
        "passed": report["passed"],
        "verification_status": report["verification_status"],
        "recorded_count": report.get("recorded_count", 0),
        "failure_count": len(report.get("failures", [])),
    }))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
