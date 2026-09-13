#!/usr/bin/env python3
"""Verify a frozen A-only TypeScript context protocol-v2 artifact batch.

This is an artifact verifier, not a runner.  It never launches Codex or
rebuilds an index.  The benchmark's corpus, trace replay, and v2 delivery
reconciliation code remain the source of truth for those checks; this script
binds them to every retained attempt and records incomplete or failed attempts
without treating a failed model outcome as a missing artifact.
"""

from __future__ import annotations

import argparse
import collections
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Mapping


RUN_NAME = re.compile(r"^(?P<case>.+)-r(?P<repetition>[1-9][0-9]*)$")
EXPECTED_HARNESS = (
    "benchmarks/typescript_context_adapter.py",
    "benchmarks/typescript_context_baseline.py",
    "benchmarks/typescript_context_corpus.py",
    "benchmarks/typescript_context_delivery.py",
    "benchmarks/typescript_context_relationships.py",
    "benchmarks/typescript_context_trace.py",
    "benchmarks/typescript_context_transport_probe.py",
)


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _repo_root(corpus_root: Path) -> Path:
    """Resolve the checkout from the normal benchmarks/corpora layout."""

    # .../<checkout>/benchmarks/corpora/typescript-context-v2
    parents = corpus_root.resolve().parents
    if len(parents) < 3:
        raise ValueError(f"corpus root is too shallow: {corpus_root}")
    return parents[2]


def _imports(corpus_root: Path):
    root = _repo_root(corpus_root)
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    from benchmarks.typescript_context_adapter import wire
    from benchmarks.typescript_context_corpus import check_answer, load_controls, load_corpus
    from benchmarks.typescript_context_delivery import reconcile_deliveries
    from benchmarks.typescript_context_trace import replay

    return root, wire, check_answer, load_controls, load_corpus, reconcile_deliveries, replay


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _failure(checks: list[dict[str, Any]], scope: str, category: str, message: str, **extra: Any) -> None:
    item = {"scope": scope, "category": category, "message": message}
    item.update(extra)
    checks.append(item)


def _safe_json(path: Path, checks: list[dict[str, Any]], scope: str) -> Any | None:
    try:
        return _read_json(path)
    except Exception as exc:  # malformed saved artifacts are evidence of a failed check
        _failure(checks, scope, "invalid_json", f"{path.name}: {type(exc).__name__}: {exc}")
        return None


def _git(root: Path, *args: str) -> str | None:
    try:
        return subprocess.run(
            ["git", *args], cwd=root, check=True, capture_output=True, text=True
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def _git_bytes(root: Path, *args: str) -> bytes | None:
    try:
        return subprocess.run(
            ["git", *args], cwd=root, check=True, capture_output=True
        ).stdout
    except (OSError, subprocess.CalledProcessError):
        return None


def _terminal_tool_calls(events: list[dict[str, Any]], checks: list[dict[str, Any]], scope: str) -> list[dict[str, Any]]:
    """Return every terminal mcp_tool_call and flag orphaned starts.

    Current Codex JSON uses item.completed with status=failed for host/schema
    failures.  item.failed is accepted as a terminal event too so an artifact
    cannot silently omit a failed call from v2 cost accounting.
    """

    started: dict[str, int] = {}
    terminal: dict[str, int] = {}
    calls: list[dict[str, Any]] = []
    for index, event in enumerate(events, 1):
        if not isinstance(event, dict):
            _failure(checks, scope, "invalid_event", f"event {index} is not an object")
            continue
        item = event.get("item")
        if not isinstance(item, dict) or item.get("type") != "mcp_tool_call":
            continue
        item_id = item.get("id")
        if not isinstance(item_id, str) or not item_id:
            _failure(checks, scope, "invalid_tool_event", f"mcp tool event {index} has no item id")
            continue
        if event.get("type") == "item.started":
            if item_id in started:
                _failure(checks, scope, "duplicate_tool_start", f"duplicate start for {item_id}")
            started[item_id] = index
        elif event.get("type") in {"item.completed", "item.failed"}:
            if item_id in terminal:
                _failure(checks, scope, "duplicate_tool_terminal", f"duplicate terminal event for {item_id}")
            terminal[item_id] = index
            calls.append(item)
    missing = sorted(set(started) - set(terminal))
    orphaned = sorted(set(terminal) - set(started))
    if missing:
        _failure(checks, scope, "unreconciled_tool_start", "tool calls have no terminal event", item_ids=missing)
    if orphaned:
        _failure(checks, scope, "orphaned_tool_terminal", "terminal tool calls have no start event", item_ids=orphaned)
    return calls


def _verify_environment(
    output: Path,
    corpus_root: Path,
    corpus: dict[str, Any],
    controls: dict[str, Any],
    repo: Path,
    checks: list[dict[str, Any]],
) -> dict[str, Any]:
    scope = "environment"
    path = output / "environment.json"
    environment = _safe_json(path, checks, scope)
    if not isinstance(environment, dict):
        return {}

    expected_environment = controls.get("environment", {})
    if not isinstance(expected_environment, dict):
        _failure(checks, scope, "invalid_controls", "controls.environment is not an object")
    else:
        observed = {key: environment.get(key) for key in expected_environment}
        if observed != expected_environment:
            _failure(checks, scope, "environment_hash_mismatch", "saved environment differs from frozen controls")

    corpus_hash = sha((corpus_root / "corpus.json").read_bytes())
    controls_hash = sha((corpus_root / "comparison-controls.json").read_bytes())
    if environment.get("corpus_sha256") != corpus_hash:
        _failure(checks, scope, "corpus_hash_mismatch", "environment corpus hash differs from corpus.json")
    if environment.get("controls_sha256") != controls_hash:
        _failure(checks, scope, "controls_hash_mismatch", "environment controls hash differs from comparison-controls.json")
    if environment.get("baseline_source_tree") != controls.get("baseline_source_tree"):
        _failure(checks, scope, "source_tree_mismatch", "saved baseline source tree differs from controls")
    if environment.get("baseline_commit") != controls.get("baseline_engine", {}).get("commit"):
        _failure(checks, scope, "baseline_commit_mismatch", "saved baseline commit differs from controls")

    saved_harness = environment.get("harness_files")
    current_harness: dict[str, str] = {}
    for relative in EXPECTED_HARNESS:
        path = repo / relative
        if not path.is_file():
            _failure(checks, scope, "missing_harness_file", f"missing {relative}")
            continue
        current_harness[relative] = sha(path.read_bytes())
    if saved_harness != current_harness:
        _failure(checks, scope, "harness_hash_mismatch", "current harness files differ from saved environment")

    measured_commit = environment.get("harness_commit")
    resolved_commit = (
        _git(repo, "rev-parse", "--verify", f"{measured_commit}^{{commit}}")
        if isinstance(measured_commit, str) and measured_commit
        else None
    )
    if resolved_commit is None:
        _failure(checks, scope, "measured_commit_missing", "saved harness commit is not present in the checkout")
    else:
        for relative in EXPECTED_HARNESS:
            committed = _git_bytes(repo, "show", f"{measured_commit}:{relative}")
            expected_hash = saved_harness.get(relative) if isinstance(saved_harness, dict) else None
            if committed is None:
                _failure(checks, scope, "measured_harness_missing", f"{relative} is absent from the saved harness commit")
            elif expected_hash != sha(committed):
                _failure(checks, scope, "measured_harness_hash_mismatch", f"{relative} differs at the saved harness commit")
        measured_source = _git(repo, "rev-parse", f"{measured_commit}:src")
        if measured_source != controls.get("baseline_source_tree"):
            _failure(checks, scope, "measured_source_tree_mismatch", "saved harness commit src tree differs from frozen baseline source")
    current_source = _git(repo, "rev-parse", "HEAD:src")
    if current_source is not None and current_source != controls.get("baseline_source_tree"):
        _failure(checks, scope, "source_tree_mismatch", "current src tree differs from frozen baseline source")
    return environment


def _transport_expectation(
    output: Path,
    corpus_root: Path,
    controls: dict[str, Any],
    repo: Path,
    checks: list[dict[str, Any]],
) -> tuple[str | None, list[list[str]] | None]:
    scope = "transport"
    path = output / "transport-verification.json"
    transport = _safe_json(path, checks, scope)
    if not isinstance(transport, dict):
        return None, None
    expected_corpus_hash = sha((corpus_root / "corpus.json").read_bytes())
    if transport.get("corpus_sha256") != expected_corpus_hash:
        _failure(checks, scope, "corpus_hash_mismatch", "transport verification uses another corpus")
    probe = repo / "benchmarks/typescript_context_transport_probe.py"
    if probe.is_file() and transport.get("script_sha256") != sha(probe.read_bytes()):
        _failure(checks, scope, "probe_hash_mismatch", "transport probe hash differs from current harness")
    catalog = output / "model-catalog.json"
    if catalog.is_file() and transport.get("catalog_sha256") != sha(catalog.read_bytes()):
        _failure(checks, scope, "catalog_hash_mismatch", "transport verification uses another model catalog")
    modes = transport.get("modes")
    if not isinstance(modes, list) or not modes:
        _failure(checks, scope, "missing_transport_modes", "transport verification has no mode observations")
        return transport.get("canonical_tool_schemas_sha256"), None
    schema_hashes = {mode.get("tool_schemas_sha256") for mode in modes if isinstance(mode, dict)}
    if len(schema_hashes) != 1 or None in schema_hashes:
        _failure(checks, scope, "transport_schema_drift", "transport modes do not share one tool schema hash")
    canonical = transport.get("canonical_tool_schemas_sha256")
    if schema_hashes and canonical not in schema_hashes:
        _failure(checks, scope, "transport_schema_hash_mismatch", "transport canonical schema hash is not observed in modes")
    tool_sets = [mode.get("tool_set") for mode in modes if isinstance(mode, dict)]
    if tool_sets and any(tool_set != tool_sets[0] for tool_set in tool_sets[1:]):
        _failure(checks, scope, "transport_tool_set_drift", "transport modes expose different effective tool sets")
    return canonical, tool_sets[0] if tool_sets and isinstance(tool_sets[0], list) else None


def _verify_request(
    run_dir: Path,
    case: dict[str, Any],
    controls: dict[str, Any],
    transport_schema: str | None,
    transport_tools: list[list[str]] | None,
    wire: Any,
    checks: list[dict[str, Any]],
) -> str | None:
    scope = run_dir.name + "/request"
    audit = _safe_json(run_dir / "request-audit.json", checks, scope)
    if not isinstance(audit, dict):
        return None
    request = audit.get("request")
    if not isinstance(request, dict):
        _failure(checks, scope, "invalid_request", "request-audit.request is not an object")
        return None
    try:
        computed_request_hash = sha(wire(request).encode("utf-8"))
    except Exception as exc:
        _failure(checks, scope, "invalid_request", f"cannot serialize effective request: {exc}")
        computed_request_hash = None
    if computed_request_hash is not None and audit.get("request_sha256") != computed_request_hash:
        _failure(checks, scope, "request_hash_mismatch", "saved request hash does not match effective request")
    if request.get("model") != controls.get("agent", {}).get("model"):
        _failure(checks, scope, "model_mismatch", "effective request model differs from controls")
    reasoning = request.get("reasoning")
    if not isinstance(reasoning, dict) or reasoning.get("effort") != controls.get("agent", {}).get("reasoning_effort"):
        _failure(checks, scope, "reasoning_mismatch", "effective request reasoning differs from controls")
    expected_prompt = controls.get("agent", {}).get("common_prompt", "") + case.get("prompt", "")
    request_input = request.get("input")
    if not isinstance(request_input, list) or not request_input:
        _failure(checks, scope, "prompt_mismatch", "effective request has no input")
    elif request_input[-1].get("content") != [{"type": "input_text", "text": expected_prompt}]:
        _failure(checks, scope, "prompt_mismatch", "effective task prompt differs from frozen common prompt plus case")

    additional = [item for item in request_input or [] if isinstance(item, dict) and item.get("type") == "additional_tools"]
    try:
        tool_schema_hash = sha(wire({"tools": additional}).encode("utf-8"))
        canonical_hash = sha(wire({"tools": [item["tools"] for item in additional]}).encode("utf-8"))
    except (KeyError, TypeError, ValueError) as exc:
        _failure(checks, scope, "invalid_tool_schema", f"effective additional tool schemas are malformed: {exc}")
        return None
    if audit.get("tool_schemas_sha256") != tool_schema_hash:
        _failure(checks, scope, "tool_schema_hash_mismatch", "saved tool schema hash differs from effective request")
    if audit.get("canonical_tool_schemas_sha256") != canonical_hash:
        _failure(checks, scope, "canonical_tool_schema_hash_mismatch", "saved canonical tool schema hash differs from effective request")
    if transport_schema is not None and canonical_hash != transport_schema:
        _failure(checks, scope, "tool_schema_drift", "effective tool schemas differ from frozen transport verification")
    tools = audit.get("tools")
    if transport_tools is not None and tools != transport_tools:
        _failure(checks, scope, "tool_set_mismatch", "effective tool set differs from frozen transport verification")
    return canonical_hash


def _verify_provenance(
    run_dir: Path,
    case: dict[str, Any],
    corpus: dict[str, Any],
    controls: dict[str, Any],
    measurement: dict[str, Any],
    trace_path: Path,
    wire: Any,
    checks: list[dict[str, Any]],
) -> None:
    scope = run_dir.name + "/provenance"
    provenance = _safe_json(run_dir / "provenance.json", checks, scope)
    if not isinstance(provenance, dict):
        return
    expected_files = corpus["snapshots"][case["snapshot"]]["files"]
    if provenance.get("snapshot_files") != expected_files:
        _failure(checks, scope, "snapshot_fingerprint_mismatch", "saved snapshot file hashes differ from frozen corpus")
    run = provenance.get("run")
    identity_keys = ("case_id", "session_id", "arm", "repetition")
    if not isinstance(run, dict):
        _failure(checks, scope, "invalid_run_provenance", "provenance.run is not an object")
    else:
        for key in identity_keys:
            expected = case["id"] if key == "case_id" else measurement.get(key)
            if run.get(key) != expected:
                _failure(checks, scope, "run_identity_mismatch", f"provenance.run.{key} differs from measurement")
        if run.get("trace_path") and Path(run["trace_path"]).resolve() != trace_path.resolve():
            # A copied artifact can legitimately retain the original absolute
            # path, so this is informational rather than a hard check.
            pass
    config = provenance.get("config")
    if not isinstance(config, dict):
        _failure(checks, scope, "invalid_provenance_config", "provenance.config is not an object")
    else:
        if provenance.get("config_sha256") != sha(wire(config).encode("utf-8")):
            _failure(checks, scope, "config_hash_mismatch", "saved configuration hash does not match configuration")
    prompt = provenance.get("prompt_sha256")
    expected_prompt = controls.get("agent", {}).get("common_prompt", "") + case.get("prompt", "")
    if not isinstance(prompt, str):
        _failure(checks, scope, "missing_prompt_hash", "provenance has no prompt hash")
    elif prompt != sha(expected_prompt.encode("utf-8")):
        _failure(checks, scope, "prompt_hash_mismatch", "provenance prompt hash differs from frozen effective prompt")
    if provenance.get("extractor_version") is not None and provenance.get("extractor_version") != corpus["baseline_engine"]["extractor_version"]:
        _failure(checks, scope, "extractor_mismatch", "provenance extractor differs from frozen baseline")


def _failure_categories(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [entry.get("category", "unclassified") for entry in value if isinstance(entry, dict)]


def _verify_run(
    run_dir: Path,
    case: dict[str, Any],
    repetition: int,
    corpus: dict[str, Any],
    controls: dict[str, Any],
    wire: Any,
    check_answer: Any,
    reconcile_deliveries: Any,
    replay: Any,
    transport_schema: str | None,
    transport_tools: list[list[str]] | None,
    checks: list[dict[str, Any]],
) -> dict[str, Any] | None:
    scope = run_dir.name
    result_path = run_dir / "result.json"
    artifact = _safe_json(result_path, checks, scope)
    if not isinstance(artifact, dict):
        return None
    measurement = artifact.get("measurement")
    baseline = artifact.get("baseline")
    identity = artifact.get("identity")
    if not isinstance(measurement, dict) or not isinstance(baseline, dict) or not isinstance(identity, dict):
        _failure(checks, scope, "invalid_artifact", "result must contain object identity, measurement, and baseline")
        return None

    expected_identity = {
        "task_id": case["id"],
        "arm": "A",
        "repetition": repetition,
        "snapshot": case["snapshot"],
    }
    for key, expected in expected_identity.items():
        if identity.get(key) != expected or measurement.get(key) != expected:
            _failure(checks, scope, "run_identity_mismatch", f"{key} does not match planned A-only identity")
    if identity != {key: measurement.get(key) for key in identity}:
        _failure(checks, scope, "identity_copy_mismatch", "artifact identity differs from measurement identity")

    trace_path = run_dir / "adapter-trace.json"
    raw_trace = _safe_json(trace_path, checks, scope + "/trace")
    if not isinstance(raw_trace, dict):
        raw_trace = {}
    if raw_trace.get("identity") != identity:
        _failure(checks, scope + "/trace", "trace_identity_mismatch", "adapter trace identity differs from result identity")
    if raw_trace.get("events") != artifact.get("events"):
        _failure(checks, scope + "/trace", "trace_event_mismatch", "adapter trace events differ from result events")
    deliveries = raw_trace.get("deliveries")
    if not isinstance(deliveries, list):
        _failure(checks, scope + "/trace", "missing_delivery_ledger", "v2 trace has no deliveries list")
        deliveries = []
    expected_attempts = [f"{identity.get('session_id')}/attempt/{index}" for index in range(1, len(deliveries) + 1)]
    actual_attempts = [entry.get("attempt_id") for entry in deliveries if isinstance(entry, dict)]
    if actual_attempts != expected_attempts or raw_trace.get("attempts") != len(deliveries):
        _failure(checks, scope + "/trace", "delivery_attempt_sequence_mismatch", "v2 delivery ledger attempts are not contiguous")

    try:
        replayed = replay(corpus, artifact)
        if replayed != measurement:
            _failure(checks, scope, "trace_replay_mismatch", "saved measurement differs from exact core trace replay")
    except Exception as exc:
        _failure(checks, scope, "trace_replay_failed", f"{type(exc).__name__}: {exc}")

    events_path = run_dir / "events.jsonl"
    events: list[dict[str, Any]] = []
    try:
        lines = events_path.read_text(encoding="utf-8").splitlines()
        for line_no, line in enumerate(lines, 1):
            if not line.strip():
                continue
            try:
                event = json.loads(line)
            except Exception as exc:
                _failure(checks, scope + "/events", "invalid_event_json", f"line {line_no}: {exc}")
                continue
            if isinstance(event, dict):
                events.append(event)
            else:
                _failure(checks, scope + "/events", "invalid_event", f"line {line_no} is not an object")
    except OSError as exc:
        _failure(checks, scope + "/events", "missing_events", str(exc))

    calls = _terminal_tool_calls(events, checks, scope + "/events")
    accounting: dict[str, Any] | None = None
    if raw_trace:
        try:
            accounting = reconcile_deliveries(raw_trace, calls, raw_trace.get("events", []))
            accounting.pop("validated_results", None)
        except Exception as exc:
            _failure(checks, scope + "/delivery", "delivery_reconciliation_failed", f"{type(exc).__name__}: {exc}")
    saved_accounting = baseline.get("output_accounting")
    if not isinstance(saved_accounting, dict):
        _failure(checks, scope + "/delivery", "missing_output_accounting", "baseline has no v2 output_accounting")
    elif accounting is not None and saved_accounting != accounting:
        _failure(checks, scope + "/delivery", "output_accounting_mismatch", "saved output accounting differs from raw event/ledger reconciliation")
    if accounting is not None:
        if baseline.get("tool_delivery_verified") != accounting.get("complete"):
            _failure(checks, scope + "/delivery", "delivery_flag_mismatch", "tool_delivery_verified disagrees with reconciled delivery")
        expected_adapter_ms = sum(entry.get("elapsed_ms", 0) for entry in deliveries if isinstance(entry, dict))
        if baseline.get("adapter_elapsed_ms") is not None and baseline.get("adapter_elapsed_ms") != expected_adapter_ms:
            _failure(checks, scope + "/delivery", "delivery_timing_mismatch", "adapter elapsed total differs from persisted ledger")

    raw_failures = raw_trace.get("failures") if isinstance(raw_trace.get("failures"), list) else []
    baseline_failures = baseline.get("failures") if isinstance(baseline.get("failures"), list) else []
    if baseline_failures[: len(raw_failures)] != raw_failures:
        _failure(checks, scope, "failure_ledger_mismatch", "baseline failures do not retain adapter failures as a prefix")
    invalid_causal = [failure for failure in raw_failures if isinstance(failure, dict) and failure.get("category") == "invalid_trace"]
    if invalid_causal:
        # An invalid causal attribution is a failed causal claim even when every
        # output byte is known and delivery reconciliation is complete.
        if baseline.get("lineage_valid") is not False:
            _failure(checks, scope, "invalid_causal_attribution_not_flagged", "invalid_trace was retained without lineage_valid=false")
        if measurement.get("task_correct") is True:
            _failure(checks, scope, "invalid_causal_attribution_accepted", "invalid_trace run is marked task-correct")

    answer = measurement.get("answer")
    try:
        answer_match = bool(check_answer(corpus, case["id"], answer))
    except Exception:
        answer_match = False
        _failure(checks, scope, "invalid_answer", "measurement answer is not a valid JSON answer")
    accounting_complete = bool(isinstance(saved_accounting, dict) and saved_accounting.get("complete") is True)
    complete_bytes = saved_accounting.get("complete_payload_bytes") if isinstance(saved_accounting, dict) else None
    if accounting_complete and (isinstance(complete_bytes, bool) or not isinstance(complete_bytes, int) or complete_bytes < 0):
        _failure(checks, scope + "/delivery", "missing_complete_output_cost", "complete accounting has no nonnegative complete_payload_bytes")
    if not accounting_complete and complete_bytes is not None:
        _failure(checks, scope + "/delivery", "false_complete_output_cost", "incomplete accounting reports a complete payload byte total")

    _verify_request(run_dir, case, controls, transport_schema, transport_tools, wire, checks)
    _verify_provenance(run_dir, case, corpus, controls, measurement, trace_path, wire, checks)

    failure_categories = collections.Counter(_failure_categories(baseline.get("failures")))
    return {
        "path": run_dir.name,
        "task_id": identity.get("task_id"),
        "arm": identity.get("arm"),
        "repetition": identity.get("repetition"),
        "session_id": identity.get("session_id"),
        "provider_thread_id": baseline.get("provider_thread_id"),
        "outcome": measurement.get("outcome"),
        "task_correct": measurement.get("task_correct"),
        "answer_match": answer_match,
        "lineage_status": measurement.get("lineage_status"),
        "lineage_valid": baseline.get("lineage_valid"),
        "invalid_causal_attribution": bool(invalid_causal),
        "invalid_causal_failures": invalid_causal,
        "failure_categories": dict(sorted(failure_categories.items())),
        "delivery_complete": accounting_complete,
        "complete_output_bytes": complete_bytes if accounting_complete else None,
        "tool_call_count": saved_accounting.get("tool_call_count") if isinstance(saved_accounting, dict) else None,
        "read_count": measurement.get("read_count"),
        "avoidable_reads": measurement.get("avoidable_reads"),
        "context_recall": measurement.get("context_recall"),
    }


def _verify_summary(output: Path, expected: dict[tuple[str, int], dict[str, Any]], checks: list[dict[str, Any]]) -> None:
    scope = "summary"
    summary = _safe_json(output / "summary.json", checks, scope)
    if not isinstance(summary, dict):
        return

    # baseline_report.py postprocesses the runner summary in place.  Its
    # durable shape keeps each parsed artifact under runs[*].raw_result and
    # exposes the 51-run identity contract under batch.  Verify that richer
    # shape first; retain support for the runner's original results list below
    # so this verifier also works before report postprocessing.
    if isinstance(summary.get("runs"), list):
        batch = summary.get("batch")
        if not isinstance(batch, dict):
            _failure(checks, scope, "invalid_report_summary", "report summary has no batch object")
        else:
            expected_batch = {
                "planned_runs": len(expected),
                "recorded_result_files": len(expected),
                "recorded_runs": len(expected),
                "unique_identity_count": len(expected),
                "expected_identity_count": len(expected),
                "complete_batch": True,
                "missing_identities": [],
                "unexpected_identities": [],
                "duplicate_identities": [],
                "arm_mismatch_paths": [],
                "invalid_identity_paths": [],
                "invalid_result_count": 0,
                "partial_attempt_directories": [],
            }
            for key, value in expected_batch.items():
                if batch.get(key) != value:
                    _failure(checks, scope, "report_batch_mismatch", f"summary.batch.{key} does not match the 51-attempt plan")
        corpus_summary = summary.get("corpus")
        if corpus_summary != {
            "version": "typescript-context-v2",
            "case_count": 17,
            "fixture_case_count": 14,
            "maintained_case_count": 3,
        }:
            _failure(checks, scope, "report_corpus_mismatch", "report summary corpus counts differ from frozen v2 corpus")
        if summary.get("arm") != "A":
            _failure(checks, scope, "report_arm_mismatch", "report summary is not the A-only arm")

        rows = summary["runs"]
        if len(rows) != len(expected):
            _failure(checks, scope, "summary_result_count_mismatch", "report summary runs do not contain exactly 51 rows")
            return
        seen: set[tuple[str, int]] = set()
        known_complete = []
        for row in rows:
            if not isinstance(row, dict):
                _failure(checks, scope, "invalid_summary_row", "report summary run row is not an object")
                continue
            identity = row.get("identity")
            if not isinstance(identity, dict):
                _failure(checks, scope, "invalid_summary_identity", "report summary run has no identity object")
                continue
            key = (identity.get("task_id"), identity.get("repetition"))
            if key in seen:
                _failure(checks, scope, "duplicate_summary_identity", f"duplicate report summary identity {key}")
            seen.add(key)
            if key not in expected:
                _failure(checks, scope, "unexpected_summary_identity", f"unexpected report summary identity {key}")
                continue
            if identity.get("arm") != "A" or row.get("identity_key") != [key[0], key[1]]:
                _failure(checks, scope, "summary_identity_mismatch", f"report summary identity metadata differs for {key}")
            raw = row.get("raw_result")
            path_value = row.get("path")
            expected_path = f"{key[0]}-r{key[1]}/result.json"
            if path_value != expected_path:
                _failure(checks, scope, "summary_path_mismatch", f"report summary path differs for {key}")
                continue
            saved_path = output / expected_path
            saved = _safe_json(saved_path, checks, scope + "/" + expected_path)
            if raw != saved:
                _failure(checks, scope, "raw_result_mismatch", f"runs[*].raw_result differs from {expected_path}")
            if isinstance(saved, dict):
                if row.get("identity") != saved.get("identity") or row.get("measurement") != saved.get("measurement") or row.get("baseline") != saved.get("baseline"):
                    _failure(checks, scope, "summary_projection_mismatch", f"report summary projection differs for {expected_path}")
                provenance = _safe_json(saved_path.parent / "provenance.json", checks, scope + "/" + expected_path + "/provenance")
                if row.get("provenance") != provenance:
                    _failure(checks, scope, "summary_provenance_mismatch", f"report summary provenance differs for {expected_path}")
                if isinstance(saved.get("baseline"), dict):
                    accounting = saved["baseline"].get("output_accounting")
                    known_complete.append(isinstance(accounting, dict) and accounting.get("complete") is True)
        if seen != set(expected):
            _failure(checks, scope, "summary_identity_set_mismatch", "report summary identities are not exactly the planned 51")
        report_accounting_complete = bool(known_complete) and all(known_complete)
        if summary.get("accounting_complete") != report_accounting_complete:
            _failure(checks, scope, "report_accounting_flag_mismatch", "report summary accounting_complete disagrees with raw artifacts")
        if isinstance(batch, dict) and batch.get("accounting_complete") != report_accounting_complete:
            _failure(checks, scope, "report_batch_accounting_flag_mismatch", "summary.batch.accounting_complete disagrees with raw artifacts")
        return

    if summary.get("planned_runs") != len(expected):
        _failure(checks, scope, "planned_run_count_mismatch", "summary planned_runs is not the A-only target")
    if summary.get("recorded_runs") != len(expected):
        _failure(checks, scope, "recorded_run_count_mismatch", "summary recorded_runs is not the A-only target")
    if summary.get("complete_batch") is not True:
        _failure(checks, scope, "incomplete_batch", "summary does not mark the 51-attempt A-only batch complete")
    rows = summary.get("results")
    if not isinstance(rows, list) or len(rows) != len(expected):
        _failure(checks, scope, "summary_result_count_mismatch", "summary results do not contain exactly one row per planned attempt")
        return
    seen: set[tuple[str, int]] = set()
    for row in rows:
        if not isinstance(row, dict):
            _failure(checks, scope, "invalid_summary_row", "summary result row is not an object")
            continue
        key = (row.get("task_id"), row.get("repetition"))
        if key in seen:
            _failure(checks, scope, "duplicate_summary_identity", f"duplicate summary identity {key}")
        seen.add(key)
        if key not in expected:
            _failure(checks, scope, "unexpected_summary_identity", f"unexpected summary identity {key}")
        elif row != expected[key]:
            _failure(checks, scope, "summary_artifact_mismatch", f"summary row differs from saved result for {key}")


def verify(output: Path, corpus_root: Path) -> dict[str, Any]:
    output = output.resolve()
    corpus_root = corpus_root.resolve()
    checks: list[dict[str, Any]] = []
    repo, wire, check_answer, load_controls, load_corpus, reconcile_deliveries, replay = _imports(corpus_root)
    corpus = load_corpus(corpus_root)
    controls = load_controls(corpus)
    if corpus.get("version") != "typescript-context-v2":
        _failure(checks, "protocol", "wrong_corpus_version", "the verifier requires typescript-context-v2")
    if set(controls.get("arms", {})) != {"A", "B", "C"}:
        _failure(checks, "protocol", "unexpected_controls_arms", "v2 controls must declare A, B, and C")
    repetitions = controls.get("schedule", {}).get("repetitions")
    case_ids = controls.get("case_ids")
    if repetitions != 3 or not isinstance(case_ids, list) or len(case_ids) != 17:
        _failure(checks, "protocol", "unexpected_plan", "v2 A-only verifier expects 17 cases and 3 repetitions")
    expected_count = len(case_ids) * repetitions if isinstance(repetitions, int) and isinstance(case_ids, list) else 51
    if expected_count != 51:
        _failure(checks, "protocol", "unexpected_plan", f"derived A-only count is {expected_count}, expected 51")

    _verify_environment(output, corpus_root, corpus, controls, repo, checks)
    transport_schema, transport_tools = _transport_expectation(output, corpus_root, controls, repo, checks)

    cases = {case["id"]: case for case in corpus.get("cases", []) if isinstance(case, dict) and isinstance(case.get("id"), str)}
    expected_dirs = {f"{case_id}-r{repetition}" for case_id in case_ids for repetition in range(1, repetitions + 1)}
    actual_dirs = {path.name for path in output.iterdir() if path.is_dir() and RUN_NAME.match(path.name)} if output.is_dir() else set()
    for extra in sorted(actual_dirs - expected_dirs):
        _failure(checks, "batch", "unexpected_attempt_directory", f"unexpected attempt directory {extra}")
    for missing in sorted(expected_dirs - actual_dirs):
        _failure(checks, "batch", "missing_attempt_directory", f"missing planned attempt directory {missing}")

    run_reports: list[dict[str, Any]] = []
    identity_keys: set[tuple[str, str, int]] = set()
    sessions: set[str] = set()
    provider_sessions: set[str] = set()
    expected_summary: dict[tuple[str, int], dict[str, Any]] = {}
    for case_id in case_ids:
        case = cases.get(case_id)
        if case is None:
            _failure(checks, "batch", "missing_case", f"case {case_id} is absent from corpus")
            continue
        for repetition in range(1, repetitions + 1):
            run_dir = output / f"{case_id}-r{repetition}"
            if not run_dir.is_dir():
                continue
            report = _verify_run(
                run_dir, case, repetition, corpus, controls, wire, check_answer,
                reconcile_deliveries, replay, transport_schema, transport_tools, checks,
            )
            if report is None:
                continue
            run_reports.append(report)
            key = (report.get("task_id"), report.get("arm"), report.get("repetition"))
            if key in identity_keys:
                _failure(checks, run_dir.name, "duplicate_identity", f"duplicate run identity {key}")
            identity_keys.add(key)
            session_id = report.get("session_id")
            if not isinstance(session_id, str) or not session_id:
                _failure(checks, run_dir.name, "missing_session_id", "run has no nonempty session_id")
            elif session_id in sessions:
                _failure(checks, run_dir.name, "duplicate_session_id", f"duplicate session_id {session_id}")
            else:
                sessions.add(session_id)
            provider_id = report.get("provider_thread_id")
            if isinstance(provider_id, str) and provider_id:
                if provider_id in provider_sessions:
                    _failure(checks, run_dir.name, "duplicate_provider_session", f"duplicate provider thread id {provider_id}")
                provider_sessions.add(provider_id)
            result = _safe_json(run_dir / "result.json", checks, run_dir.name)
            if isinstance(result, dict) and isinstance(result.get("measurement"), dict) and isinstance(result.get("baseline"), dict):
                expected_summary[(case_id, repetition)] = {
                    **result["measurement"],
                    **result["baseline"],
                }

    planned_identity_keys = {(case_id, "A", repetition) for case_id in case_ids for repetition in range(1, repetitions + 1)}
    if identity_keys != planned_identity_keys:
        _failure(checks, "batch", "identity_set_mismatch", "saved identities are not exactly the planned 17x3 A-only set")
    if len(sessions) != len(identity_keys):
        _failure(checks, "batch", "session_set_mismatch", "session IDs are not unique for all retained attempts")
    _verify_summary(output, expected_summary, checks)

    invalid_count = sum(report["invalid_causal_attribution"] for report in run_reports)
    known_complete_bytes = sum(
        report["complete_output_bytes"]
        for report in run_reports
        if isinstance(report.get("complete_output_bytes"), int)
    )
    complete_output_runs = sum(report["delivery_complete"] for report in run_reports)
    groups: dict[str, dict[str, Any]] = {}
    for report in run_reports:
        case = cases.get(report["task_id"], {})
        group = "maintained3" if case.get("group") == "maintained_task" else "fixture14"
        entry = groups.setdefault(group, {"runs": 0, "task_correct": 0, "answer_matches": 0, "outcomes": collections.Counter(), "invalid_causal_attribution": 0})
        entry["runs"] += 1
        entry["task_correct"] += bool(report.get("task_correct"))
        entry["answer_matches"] += bool(report.get("answer_match"))
        entry["outcomes"][report.get("outcome")] += 1
        entry["invalid_causal_attribution"] += bool(report.get("invalid_causal_attribution"))
    for entry in groups.values():
        entry["outcomes"] = dict(sorted(entry["outcomes"].items()))

    verification_failures = [item for item in checks if item.get("category") not in {"measurement_failure"}]
    result = {
        "schema_version": 2,
        "verified": not verification_failures and len(run_reports) == expected_count,
        "verification_status": "passed" if not verification_failures and len(run_reports) == expected_count else "incomplete_or_failed",
        "corpus_version": corpus.get("version"),
        "planned_runs": expected_count,
        "verified_runs": len(run_reports),
        "unique_identities": len(identity_keys),
        "unique_session_ids": len(sessions),
        "unique_provider_sessions": len(provider_sessions),
        "exact_trace_replays": sum(1 for item in checks if item.get("category") == "trace_replay_failed" or item.get("category") == "trace_replay_mismatch") == 0 and len(run_reports),
        "complete_delivery_accounting_runs": complete_output_runs,
        "known_complete_output_bytes": known_complete_bytes,
        "known_complete_output_bytes_status": "complete" if complete_output_runs == len(run_reports) else "partial" if complete_output_runs else "unavailable",
        "invalid_causal_attribution_runs": invalid_count,
        "groups": groups,
        "runs": sorted(run_reports, key=lambda item: (item.get("task_id", ""), item.get("repetition", 0))),
        "checks_failed": len(verification_failures),
        "failures": checks,
        "meaning": "Artifact integrity, frozen controls, exact trace replay, request schemas, snapshot fingerprints, and v2 delivery accounting are checked independently of model success. Invalid causal attribution is retained separately from known complete output costs.",
    }
    output.mkdir(parents=True, exist_ok=True)
    (output / "verification.json").write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True, help="saved baseline result directory")
    parser.add_argument("--corpus-root", type=Path, required=True, help="frozen typescript-context-v2 corpus directory")
    args = parser.parse_args()
    try:
        result = verify(args.output, args.corpus_root)
    except Exception as exc:
        # Keep the command's failure explicit.  A malformed corpus/control file
        # cannot be safely downgraded to a partial artifact result.
        print(json.dumps({"verified": False, "verification_status": "blocked", "error": f"{type(exc).__name__}: {exc}"}, indent=2))
        return 2
    print(json.dumps({
        "verified": result["verified"],
        "verification_status": result["verification_status"],
        "planned_runs": result["planned_runs"],
        "verified_runs": result["verified_runs"],
        "checks_failed": result["checks_failed"],
        "invalid_causal_attribution_runs": result["invalid_causal_attribution_runs"],
        "complete_delivery_accounting_runs": result["complete_delivery_accounting_runs"],
    }, indent=2))
    return 0 if result["verified"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
