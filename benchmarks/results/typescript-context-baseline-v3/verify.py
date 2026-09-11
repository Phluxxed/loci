#!/usr/bin/env python3
"""Independently verify a frozen TypeScript context v3 A-only artifact batch.

This verifier reads saved artifacts and raw provider events only.  It never
starts Codex, an MCP server, an index build, or a provider request.  Model
success and hard-failure outcomes remain descriptive run facts; integrity is
decided from the frozen identity, source trace, call accounting, and replay.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any


RUN_NAME = re.compile(r"^(?P<case>.+)-r(?P<repetition>[1-9][0-9]*)$")
EXPECTED_TRANSPORT_MODES = {
    "typed_search",
    "typed_get",
    "grep_unknown_file_paths",
    "get_bool_context",
    "get_invalid_selection",
    "list_resources_evaluation",
    "list_resources_all_servers",
    "list_templates_evaluation",
    "read_missing_resource",
    "read_unknown_server",
}


def sha(value: bytes | str) -> str:
    if isinstance(value, str):
        value = value.encode("utf-8")
    return hashlib.sha256(value).hexdigest()


def _repo_root(corpus_root: Path) -> Path:
    # <checkout>/benchmarks/corpora/typescript-context-v3
    parents = corpus_root.resolve().parents
    if len(parents) < 3:
        raise ValueError(f"corpus root is too shallow: {corpus_root}")
    return parents[2]


def _git_bytes(repo: Path, *args: str) -> bytes | None:
    try:
        return subprocess.run(
            ["git", *args], cwd=repo, check=True, capture_output=True
        ).stdout
    except (OSError, subprocess.CalledProcessError):
        return None


def _git_text(repo: Path, *args: str) -> str | None:
    value = _git_bytes(repo, *args)
    if value is None:
        return None
    try:
        return value.decode("utf-8").strip()
    except UnicodeDecodeError:
        return None


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _failure(checks: list[dict[str, Any]], scope: str, category: str, message: str, **extra: Any) -> None:
    item: dict[str, Any] = {"scope": scope, "category": category, "message": message}
    item.update(extra)
    checks.append(item)


def _safe_json(path: Path, checks: list[dict[str, Any]], scope: str) -> Any | None:
    try:
        return _read_json(path)
    except Exception as exc:
        _failure(checks, scope, "invalid_json", f"{path.name}: {type(exc).__name__}: {exc}")
        return None


def _imports(corpus_root: Path):
    repo = _repo_root(corpus_root)
    if str(repo) not in sys.path:
        sys.path.insert(0, str(repo))
    from benchmarks.typescript_context_adapter import wire
    from benchmarks.typescript_context_corpus import check_answer, load_controls, load_corpus
    from benchmarks.typescript_context_delivery import payload_texts
    from benchmarks.typescript_context_observed import measure, reconcile_observed, replay_trace
    from benchmarks.typescript_context_tools_v3 import TOOL_NAMES
    from benchmarks.typescript_context_transport_probe import _model_payload

    expected_tools = {('mcp__evaluation', name) for name in TOOL_NAMES} | {
        ('functions', 'list_mcp_resources'),
        ('functions', 'list_mcp_resource_templates'),
        ('functions', 'read_mcp_resource'),
    }
    return (repo, wire, check_answer, load_controls, load_corpus, measure,
            reconcile_observed, replay_trace, payload_texts, _model_payload,
            expected_tools)


def _relative_under(root: Path, value: Any, checks: list[dict[str, Any]], scope: str) -> Path | None:
    if not isinstance(value, str) or not value:
        _failure(checks, scope, "missing_relative_path", "saved evidence path is not a nonempty string")
        return None
    path = Path(value)
    if path.is_absolute():
        _failure(checks, scope, "absolute_evidence_path", "saved evidence path must be relative to output", path=value)
        return None
    resolved = (root / path).resolve()
    try:
        resolved.relative_to(root.resolve())
    except ValueError:
        _failure(checks, scope, "evidence_path_escape", "saved evidence path escapes output root", path=value)
        return None
    return resolved


def _verify_freeze(
    output: Path,
    corpus_root: Path,
    repo: Path,
    corpus: dict[str, Any],
    controls: dict[str, Any],
    checks: list[dict[str, Any]],
) -> tuple[dict[str, Any], dict[str, Any]]:
    freeze = _safe_json(corpus_root / "freeze.json", checks, "freeze")
    environment = _safe_json(output / "environment.json", checks, "environment")
    if not isinstance(freeze, dict):
        freeze = {}
    if not isinstance(environment, dict):
        environment = {}

    harness = freeze.get("harness_files")
    corpus_files = freeze.get("corpus_files")
    if not isinstance(harness, dict) or not harness:
        _failure(checks, "freeze", "missing_harness_fingerprint", "freeze.harness_files is not a nonempty map")
        harness = {}
    if not isinstance(corpus_files, dict) or not corpus_files:
        _failure(checks, "freeze", "missing_corpus_fingerprint", "freeze.corpus_files is not a nonempty map")
        corpus_files = {}

    if environment.get("harness_files") != harness:
        _failure(checks, "environment", "harness_hash_mismatch", "environment harness hashes differ from freeze.json")
    corpus_hash = sha((corpus_root / "corpus.json").read_bytes())
    controls_hash = sha((corpus_root / "comparison-controls.json").read_bytes())
    if environment.get("corpus_sha256") != corpus_hash:
        _failure(checks, "environment", "corpus_hash_mismatch", "environment corpus hash differs from corpus.json")
    if environment.get("controls_sha256") != controls_hash:
        _failure(checks, "environment", "controls_hash_mismatch", "environment controls hash differs from controls")
    if environment.get("baseline_source_tree") != controls.get("baseline_source_tree"):
        _failure(checks, "environment", "source_tree_mismatch", "environment baseline source tree differs from controls")
    if environment.get("baseline_commit") != controls.get("baseline_engine", {}).get("commit"):
        _failure(checks, "environment", "baseline_commit_mismatch", "environment baseline commit differs from controls")
    expected_environment = controls.get("environment")
    if not isinstance(expected_environment, dict):
        _failure(checks, "environment", "missing_control_environment", "controls.environment is not an object")
    else:
        for key, expected in expected_environment.items():
            if environment.get(key) != expected:
                _failure(checks, "environment", "control_environment_mismatch",
                         f"saved environment field differs from controls.environment: {key}")
    expected_cli = controls.get("agent", {}).get("cli_version")
    if environment.get("cli_version") != ("codex-cli " + expected_cli if isinstance(expected_cli, str) else None):
        _failure(checks, "environment", "cli_version_mismatch", "saved CLI version differs from controls.agent.cli_version")

    # Check the mutable checkout as well as the exact bytes from the pinned
    # commit.  A later checkout change must not silently pass the freeze.
    for relative, expected_hash in harness.items():
        current = repo / relative
        if not current.is_file():
            _failure(checks, "environment", "missing_current_harness", f"current harness file is absent: {relative}")
        elif sha(current.read_bytes()) != expected_hash:
            _failure(checks, "environment", "current_harness_hash_mismatch", f"current harness differs from freeze.json: {relative}")

    harness_commit = environment.get("harness_commit")
    if not isinstance(harness_commit, str) or not harness_commit:
        _failure(checks, "environment", "missing_harness_commit", "environment has no pinned harness commit")
    elif _git_text(repo, "rev-parse", "--verify", f"{harness_commit}^{{commit}}") is None:
        _failure(checks, "environment", "missing_harness_commit", "pinned harness commit is unavailable")
    else:
        # Use the exact bytes from the pinned commit.  The checkout may have
        # moved since measurement, and text helpers must not strip binaries.
        for relative, expected_hash in harness.items():
            committed = _git_bytes(repo, "show", f"{harness_commit}:{relative}")
            if committed is None:
                _failure(checks, "environment", "missing_harness_at_commit", f"{relative} is absent at pinned commit")
            elif sha(committed) != expected_hash:
                _failure(checks, "environment", "harness_commit_hash_mismatch", f"{relative} differs at pinned commit")
        source_tree = _git_text(repo, "rev-parse", f"{harness_commit}:src")
        if source_tree != controls.get("baseline_source_tree"):
            _failure(checks, "environment", "pinned_source_tree_mismatch", "pinned harness commit src tree differs from controls")

        freeze_relative = corpus_root.resolve().relative_to(repo.resolve()).as_posix() + "/freeze.json"
        frozen_freeze = _git_bytes(repo, "show", f"{harness_commit}:{freeze_relative}")
        if frozen_freeze is None:
            _failure(checks, "freeze", "missing_pinned_freeze", "freeze.json is absent at pinned harness commit")
        elif sha(frozen_freeze) != sha((corpus_root / "freeze.json").read_bytes()):
            _failure(checks, "freeze", "pinned_freeze_hash_mismatch", "freeze.json differs from pinned harness commit")

    for relative, expected_hash in corpus_files.items():
        candidate = corpus_root / relative
        if not candidate.is_file():
            candidate = repo / relative
        if not candidate.is_file():
            _failure(checks, "freeze", "missing_frozen_file", f"frozen file is absent: {relative}")
        elif sha(candidate.read_bytes()) != expected_hash:
            _failure(checks, "freeze", "frozen_file_hash_mismatch", f"frozen file differs: {relative}")
        if isinstance(harness_commit, str) and harness_commit:
            try:
                frozen_path = corpus_root.resolve().relative_to(repo.resolve()).as_posix() + "/" + relative
            except ValueError:
                frozen_path = None
            if frozen_path is None:
                _failure(checks, "freeze", "corpus_path_outside_repo", f"corpus root is outside repository: {relative}")
            else:
                committed = _git_bytes(repo, "show", f"{harness_commit}:{frozen_path}")
                if committed is None:
                    _failure(checks, "freeze", "missing_frozen_file_at_commit", f"pinned corpus file is absent: {relative}")
                elif sha(committed) != expected_hash:
                    _failure(checks, "freeze", "pinned_frozen_file_hash_mismatch", f"pinned corpus file differs: {relative}")

    return freeze, environment


def _actual_tool_set(request: dict[str, Any]) -> tuple[list[list[str]], str]:
    additional = [item for item in request.get("input", [])
                  if isinstance(item, dict) and item.get("type") == "additional_tools"]
    namespaces: list[Any] = []
    for item in additional:
        tools = item.get("tools")
        if not isinstance(tools, list):
            raise ValueError("additional_tools item has no tool list")
        namespaces.extend(tools)
    pairs: list[list[str]] = []
    for namespace in namespaces:
        if not isinstance(namespace, dict) or namespace.get("type") != "namespace":
            raise ValueError("additional tool is not a namespace")
        name = namespace.get("name")
        for tool in namespace.get("tools", []):
            if not isinstance(tool, dict):
                raise ValueError("namespace tool is not an object")
            pairs.append([name, tool.get("name")])
    return pairs, sha(wire_value({"tools": [item["tools"] for item in additional]}).encode("utf-8"))


def wire_value(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), allow_nan=False)


def _verify_transport(
    output: Path,
    corpus_root: Path,
    corpus: dict[str, Any],
    transport: dict[str, Any],
    reconcile_observed: Any,
    replay_trace: Any,
    payload_texts: Any,
    model_payload: Any,
    expected_pairs: set[tuple[str, str]],
    checks: list[dict[str, Any]],
) -> tuple[str | None, list[list[str]] | None]:
    scope = "transport"
    if transport.get("schema_version") != 3:
        _failure(checks, scope, "transport_schema_mismatch", "transport verification is not schema 3")
    if transport.get("probe") != "typescript-context-v3-typed-transport":
        _failure(checks, scope, "transport_probe_mismatch", "unexpected transport verification probe")
    expected_corpus = sha((corpus_root / "corpus.json").read_bytes())
    expected_controls = sha((corpus_root / "comparison-controls.json").read_bytes())
    if transport.get("corpus_sha256") != expected_corpus:
        _failure(checks, scope, "corpus_hash_mismatch", "transport verification uses another corpus")
    if transport.get("controls_sha256") != expected_controls:
        _failure(checks, scope, "controls_hash_mismatch", "transport verification uses other controls")

    catalog = output / "model-catalog.json"
    if not catalog.is_file() or transport.get("catalog_sha256") != sha(catalog.read_bytes()):
        _failure(checks, scope, "catalog_hash_mismatch", "transport catalog hash does not match saved catalog")
    modes = transport.get("modes")
    if not isinstance(modes, list) or len(modes) != 10:
        _failure(checks, scope, "transport_mode_count", "transport verification must contain ten modes")
        modes = []
    ids = {mode.get("mode") for mode in modes if isinstance(mode, dict)}
    if ids != EXPECTED_TRANSPORT_MODES:
        _failure(checks, scope, "transport_mode_set", "transport modes differ from the ten frozen modes")
    evidence_root = _relative_under(output, transport.get("evidence_root"), checks, scope + "/evidence_root")
    if evidence_root is None or not evidence_root.is_dir():
        _failure(checks, scope, "missing_transport_evidence", "transport evidence root is absent")

    schema_hashes: set[str] = set()
    tool_sets: list[list[list[str]]] = []
    for mode in modes:
        if not isinstance(mode, dict):
            _failure(checks, scope, "invalid_transport_mode", "transport mode is not an object")
            continue
        mode_scope = f"{scope}/{mode.get('mode', '<unknown>')}"
        if mode.get("output_verified") is not True:
            _failure(checks, mode_scope, "transport_output_unverified", "transport mode is not output_verified")
        if mode.get("trace_schema_version") != 3:
            _failure(checks, mode_scope, "transport_trace_schema", "transport mode trace is not schema 3")
        accounting = mode.get("observed_accounting")
        if not isinstance(accounting, dict) or accounting.get("complete") is not True:
            _failure(checks, mode_scope, "transport_accounting_incomplete", "transport mode observed accounting is incomplete")
        if mode.get("expected_mode") not in {"recorded", "schema_error", "bounded_error", "helper"}:
            _failure(checks, mode_scope, "transport_expected_mode", "unknown transport mode expectation")
        schema = mode.get("canonical_tool_schemas_sha256")
        if not isinstance(schema, str):
            _failure(checks, mode_scope, "transport_schema_hash_missing", "transport mode has no canonical schema hash")
        else:
            schema_hashes.add(schema)
        tools = mode.get("tool_set")
        if isinstance(tools, list):
            tool_sets.append(tools)
        else:
            _failure(checks, mode_scope, "transport_tool_set_missing", "transport mode has no tool set")
        evidence = _relative_under(output, mode.get("evidence_dir"), checks, mode_scope + "/evidence")
        if evidence is None or not evidence.is_dir():
            _failure(checks, mode_scope, "missing_mode_evidence", "transport mode evidence directory is absent")
        else:
            for name in ("events.json", "trace.json", "effective-request.json", "accounting.json", "stdout.jsonl", "stderr.txt"):
                if not (evidence / name).is_file():
                    _failure(checks, mode_scope, "missing_mode_evidence_file", f"missing {name}")
            trace = _safe_json(evidence / "trace.json", checks, mode_scope + "/trace")
            events = _safe_json(evidence / "events.json", checks, mode_scope + "/events")
            saved_accounting = _safe_json(evidence / "accounting.json", checks, mode_scope + "/accounting")
            effective_request = _safe_json(evidence / "effective-request.json", checks, mode_scope + "/request")
            next_request = _safe_json(evidence / "next-request.json", checks, mode_scope + "/next-request")
            if not isinstance(trace, dict) or not isinstance(events, list):
                _failure(checks, mode_scope, "invalid_transport_evidence", "trace/events evidence has the wrong shape")
            else:
                try:
                    replayed = replay_trace(corpus, trace)
                    if replayed.events != trace.get("events"):
                        _failure(checks, mode_scope, "transport_trace_replay_mismatch", "transport trace does not replay exactly")
                except Exception as exc:
                    _failure(checks, mode_scope, "transport_trace_replay_failed", f"{type(exc).__name__}: {exc}")
                try:
                    recomputed_accounting = reconcile_observed(trace, events)
                    if saved_accounting != recomputed_accounting:
                        _failure(checks, mode_scope, "transport_accounting_mismatch", "saved accounting differs from raw transport events")
                    if accounting != recomputed_accounting:
                        _failure(checks, mode_scope, "transport_metadata_accounting_mismatch", "mode accounting differs from raw transport events")
                except Exception as exc:
                    _failure(checks, mode_scope, "transport_reconciliation_failed", f"{type(exc).__name__}: {exc}")

                terminal = [event.get("item") for event in events
                            if event.get("type") in {"item.completed", "item.failed"}
                            and isinstance(event.get("item"), dict)
                            and event["item"].get("type") == "mcp_tool_call"]
                if len(terminal) != 1:
                    _failure(checks, mode_scope, "transport_terminal_call_count", "transport evidence must contain exactly one terminal tool call")
                elif isinstance(next_request, dict):
                    try:
                        payload_kind, expected_payload = payload_texts(terminal[0])
                        outputs = [item for item in next_request.get("input", [])
                                   if isinstance(item, dict) and item.get("type") == "function_call_output"]
                        if len(outputs) != 1:
                            raise ValueError("next request does not contain exactly one function_call_output")
                        actual_payload = model_payload(outputs[0].get("output"), payload_kind)
                        if actual_payload != expected_payload:
                            _failure(checks, mode_scope, "transport_payload_mismatch", "next-request payload differs from host terminal call")
                        if mode.get("payload_kind") != payload_kind or mode.get("payload_texts") != expected_payload:
                            _failure(checks, mode_scope, "transport_saved_payload_mismatch", "saved mode payload differs from host terminal call")
                    except Exception as exc:
                        _failure(checks, mode_scope, "transport_payload_validation_failed", f"{type(exc).__name__}: {exc}")
                else:
                    _failure(checks, mode_scope, "invalid_next_request", "next request evidence is not an object")

            if isinstance(effective_request, dict):
                try:
                    actual_tools, actual_schema = _actual_tool_set(effective_request)
                    if actual_schema != mode.get("canonical_tool_schemas_sha256"):
                        _failure(checks, mode_scope, "transport_actual_schema_mismatch", "actual effective-request schema differs from mode metadata")
                    if actual_schema != transport.get("canonical_tool_schemas_sha256"):
                        _failure(checks, mode_scope, "transport_actual_schema_drift", "actual effective-request schema differs from batch metadata")
                    actual_pairs = {tuple(item) for item in actual_tools if len(item) == 2}
                    if actual_pairs != expected_pairs or len(actual_tools) != len(expected_pairs):
                        _failure(checks, mode_scope, "transport_actual_tool_set_mismatch", "actual effective request does not expose the frozen sixteen-tool set")
                    if isinstance(mode.get("tool_set"), list) and mode["tool_set"] != actual_tools:
                        _failure(checks, mode_scope, "transport_saved_tool_set_mismatch", "saved mode tool set differs from effective request")
                except Exception as exc:
                    _failure(checks, mode_scope, "transport_request_validation_failed", f"{type(exc).__name__}: {exc}")
            else:
                _failure(checks, mode_scope, "invalid_effective_request", "effective request evidence is not an object")
    if len(schema_hashes) != 1 or (schema_hashes and transport.get("canonical_tool_schemas_sha256") not in schema_hashes):
        _failure(checks, scope, "transport_schema_drift", "transport modes do not share the saved canonical schema hash")
    if tool_sets and any(value != tool_sets[0] for value in tool_sets[1:]):
        _failure(checks, scope, "transport_tool_drift", "transport modes expose different fixed tool sets")
    return transport.get("canonical_tool_schemas_sha256"), tool_sets[0] if tool_sets else None


def _parse_events(path: Path, checks: list[dict[str, Any]], scope: str) -> list[dict[str, Any]]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        _failure(checks, scope, "missing_events", str(exc))
        return []
    events: list[dict[str, Any]] = []
    for number, line in enumerate(lines, 1):
        if not line.strip():
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError as exc:
            _failure(checks, scope, "invalid_event_json", f"line {number}: {exc}")
            continue
        if not isinstance(item, dict):
            _failure(checks, scope, "invalid_event", f"line {number} is not an object")
            continue
        events.append(item)
    return events


def _verify_lifecycle(events: list[dict[str, Any]], checks: list[dict[str, Any]], scope: str) -> None:
    started: dict[str, int] = {}
    terminal: dict[str, int] = {}
    for number, event in enumerate(events, 1):
        item = event.get("item")
        if not isinstance(item, dict) or item.get("type") != "mcp_tool_call":
            continue
        item_id = item.get("id")
        if not isinstance(item_id, str) or not item_id:
            _failure(checks, scope, "invalid_tool_identity", f"tool event {number} has no id")
            continue
        if event.get("type") == "item.started":
            if item_id in started:
                _failure(checks, scope, "duplicate_tool_start", f"duplicate start for {item_id}")
            started[item_id] = number
        elif event.get("type") in {"item.completed", "item.failed"}:
            if item_id in terminal:
                _failure(checks, scope, "duplicate_tool_terminal", f"duplicate terminal for {item_id}")
            terminal[item_id] = number
    for item_id in sorted(set(started) - set(terminal)):
        _failure(checks, scope, "unfinished_tool_call", f"started call has no terminal event: {item_id}")
    for item_id in sorted(set(terminal) - set(started)):
        _failure(checks, scope, "orphaned_tool_terminal", f"terminal call has no start event: {item_id}")


def _verify_request(
    run_dir: Path,
    case: dict[str, Any],
    controls: dict[str, Any],
    transport_schema: str | None,
    transport_tools: list[list[str]] | None,
    expected_pairs: set[tuple[str, str]],
    wire: Any,
    checks: list[dict[str, Any]],
) -> None:
    scope = run_dir.name + "/request"
    audit = _safe_json(run_dir / "request-audit.json", checks, scope)
    if not isinstance(audit, dict):
        return
    request = audit.get("request")
    if not isinstance(request, dict):
        _failure(checks, scope, "invalid_request", "request-audit.request is not an object")
        return
    if audit.get("request_sha256") != sha(wire(request).encode("utf-8")):
        _failure(checks, scope, "request_hash_mismatch", "request hash does not match effective request")
    agent = controls.get("agent", {})
    if request.get("model") != agent.get("model"):
        _failure(checks, scope, "model_mismatch", "request model differs from controls")
    if request.get("reasoning", {}).get("effort") != agent.get("reasoning_effort"):
        _failure(checks, scope, "reasoning_mismatch", "request reasoning differs from controls")
    expected_prompt = agent.get("common_prompt", "") + case.get("prompt", "")
    request_input = request.get("input")
    if not isinstance(request_input, list) or not request_input or request_input[-1].get("content") != [{"type": "input_text", "text": expected_prompt}]:
        _failure(checks, scope, "prompt_mismatch", "effective prompt differs from frozen common prompt plus case")
    additional = [item for item in request_input or [] if isinstance(item, dict) and item.get("type") == "additional_tools"]
    try:
        schema_hash = sha(wire({"tools": additional}).encode("utf-8"))
        canonical_hash = sha(wire({"tools": [item["tools"] for item in additional]}).encode("utf-8"))
    except (KeyError, TypeError, ValueError) as exc:
        _failure(checks, scope, "invalid_tool_schema", str(exc))
        return
    if audit.get("tool_schemas_sha256") != schema_hash:
        _failure(checks, scope, "tool_schema_hash_mismatch", "saved tool schema hash differs from request")
    if audit.get("canonical_tool_schemas_sha256") != canonical_hash:
        _failure(checks, scope, "canonical_tool_schema_hash_mismatch", "saved canonical tool schema hash differs from request")
    if transport_schema is not None and canonical_hash != transport_schema:
        _failure(checks, scope, "tool_schema_drift", "request tool schemas differ from transport verification")
    tools = audit.get("tools")
    if transport_tools is not None and tools != transport_tools:
        _failure(checks, scope, "tool_set_mismatch", "request tool set differs from transport verification")
    pairs = {(item[0], item[1]) for item in tools or [] if isinstance(item, list) and len(item) == 2}
    if len(pairs) != 16 or pairs != expected_pairs or len(tools or []) != 16:
        _failure(checks, scope, "fixed_tool_set_mismatch", "request does not expose the fixed sixteen-tool surface")


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
        _failure(checks, scope, "snapshot_fingerprint_mismatch", "provenance snapshot files differ from corpus")
    run = provenance.get("run")
    if not isinstance(run, dict):
        _failure(checks, scope, "invalid_run_provenance", "provenance.run is not an object")
    else:
        for key, expected in (("case_id", case["id"]), ("session_id", measurement.get("session_id")),
                              ("arm", "A"), ("repetition", measurement.get("repetition"))):
            if run.get(key) != expected:
                _failure(checks, scope, "run_identity_mismatch", f"provenance.run.{key} differs from result identity")
    config = provenance.get("config")
    if not isinstance(config, dict) or provenance.get("config_sha256") != sha(wire(config).encode("utf-8")):
        _failure(checks, scope, "config_hash_mismatch", "provenance config hash does not match config")
    prompt = controls.get("agent", {}).get("common_prompt", "") + case.get("prompt", "")
    if provenance.get("prompt_sha256") != sha(prompt.encode("utf-8")):
        _failure(checks, scope, "prompt_hash_mismatch", "provenance prompt hash differs from frozen prompt")
    if provenance.get("extractor_version") is not None and provenance.get("extractor_version") != corpus["baseline_engine"]["extractor_version"]:
        _failure(checks, scope, "extractor_mismatch", "provenance extractor differs from corpus baseline")
    if config and "typescript_context_tools_v3" not in json.dumps(config, ensure_ascii=False):
        _failure(checks, scope, "v3_config_missing", "provenance config does not select the v3 typed tool server")


def _verify_run(
    run_dir: Path,
    case: dict[str, Any],
    repetition: int,
    corpus: dict[str, Any],
    controls: dict[str, Any],
    wire: Any,
    measure: Any,
    reconcile_observed: Any,
    replay_trace: Any,
    transport_schema: str | None,
    transport_tools: list[list[str]] | None,
    expected_pairs: set[tuple[str, str]],
    checks: list[dict[str, Any]],
) -> dict[str, Any] | None:
    scope = run_dir.name
    artifact = _safe_json(run_dir / "result.json", checks, scope)
    if not isinstance(artifact, dict):
        return None
    identity, measurement, baseline = artifact.get("identity"), artifact.get("measurement"), artifact.get("baseline")
    if not all(isinstance(value, dict) for value in (identity, measurement, baseline)):
        _failure(checks, scope, "invalid_artifact", "result must contain identity, measurement, and baseline objects")
        return None
    if artifact.get("schema_version") != 3 or measurement.get("schema_version") != 3:
        _failure(checks, scope, "artifact_schema_mismatch", "result and measurement must be schema 3")
    expected = {"task_id": case["id"], "arm": "A", "repetition": repetition, "snapshot": case["snapshot"]}
    for key, value in expected.items():
        if identity.get(key) != value or measurement.get(key) != value:
            _failure(checks, scope, "run_identity_mismatch", f"{key} differs from planned identity")
    for key, value in identity.items():
        if measurement.get(key) != value:
            _failure(checks, scope, "identity_copy_mismatch", f"measurement identity differs for {key}")
    if identity.get("corpus_sha256") != sha((Path(corpus["_root"]) / "corpus.json").read_bytes()):
        _failure(checks, scope, "identity_corpus_hash_mismatch", "trace identity corpus hash differs from corpus")
    if identity.get("controls_sha256") != sha((Path(corpus["_root"]) / "comparison-controls.json").read_bytes()):
        _failure(checks, scope, "identity_controls_hash_mismatch", "trace identity controls hash differs from controls")
    if identity.get("controls_version") != controls.get("version"):
        _failure(checks, scope, "identity_controls_version_mismatch", "trace identity controls version differs")

    trace_path = run_dir / "adapter-trace.json"
    raw_trace = _safe_json(trace_path, checks, scope + "/trace")
    if not isinstance(raw_trace, dict):
        return {"identity": identity, "replayed": False, "reconciled": False, "complete": False,
                "session_id": identity.get("session_id"), "provider_thread_id": baseline.get("provider_thread_id"),
                "task_correct": measurement.get("task_correct"), "outcome": measurement.get("outcome")}
    if raw_trace.get("schema_version") != 3 or raw_trace.get("identity") != identity:
        _failure(checks, scope + "/trace", "trace_identity_mismatch", "trace schema or identity differs from result")
    if raw_trace.get("events") != artifact.get("events"):
        _failure(checks, scope + "/trace", "trace_event_mismatch", "trace events differ from result events")
    try:
        replayed = replay_trace(corpus, raw_trace)
        replay_ok = replayed.events == raw_trace.get("events")
        if not replay_ok:
            _failure(checks, scope + "/trace", "trace_replay_mismatch", "replayed source events differ from raw trace")
    except Exception as exc:
        replay_ok = False
        _failure(checks, scope + "/trace", "trace_replay_failed", f"{type(exc).__name__}: {exc}")

    events = _parse_events(run_dir / "events.jsonl", checks, scope + "/events")
    _verify_lifecycle(events, checks, scope + "/events")
    try:
        accounting = reconcile_observed(raw_trace, events)
        compare_accounting = copy_dict(accounting)
        compare_accounting.pop("validated_results", None)
        saved_accounting = baseline.get("output_accounting")
        reconciled = True
        if saved_accounting != compare_accounting:
            _failure(checks, scope + "/accounting", "output_accounting_mismatch", "saved accounting differs from raw event reconciliation")
    except Exception as exc:
        reconciled = False
        accounting = {}
        _failure(checks, scope + "/accounting", "reconciliation_failed", f"{type(exc).__name__}: {exc}")

    duration = baseline.get("actual_process_seconds")
    exit_code = baseline.get("exit_code")
    if not isinstance(duration, (int, float)) or isinstance(duration, bool) or not isinstance(exit_code, int):
        _failure(checks, scope, "missing_run_termination", "saved duration or exit code is invalid")
        measurement_replayed = False
    else:
        timed_out = measurement.get("outcome") == "timeout"
        try:
            run = {"trace_path": str(trace_path)}
            recomputed = measure(corpus, case, run, events, duration, exit_code, timed_out, None)
            measurement_replayed = recomputed.get("measurement") == measurement
            if not measurement_replayed:
                _failure(checks, scope, "measurement_replay_mismatch", "saved measurement differs from raw-evidence recomputation")
            saved_baseline = {key: value for key, value in baseline.items() if key != "relationships"}
            replay_baseline = {key: value for key, value in recomputed.get("baseline", {}).items() if key != "relationships"}
            if saved_baseline != replay_baseline:
                _failure(checks, scope, "baseline_replay_mismatch", "saved non-relationship baseline fields differ from recomputation")
        except Exception as exc:
            measurement_replayed = False
            _failure(checks, scope, "measurement_replay_failed", f"{type(exc).__name__}: {exc}")

    _verify_request(run_dir, case, controls, transport_schema, transport_tools, expected_pairs, wire, checks)
    _verify_provenance(run_dir, case, corpus, controls, measurement, trace_path, wire, checks)
    accounting_complete = bool(isinstance(baseline.get("output_accounting"), dict)
                               and baseline["output_accounting"].get("complete") is True)
    if baseline.get("tool_delivery_verified") != accounting_complete:
        _failure(checks, scope + "/accounting", "delivery_flag_mismatch", "tool_delivery_verified disagrees with accounting")
    if measurement.get("measurement_complete") is not True:
        _failure(checks, scope, "measurement_incomplete", "saved measurement is not complete")

    return {
        "path": run_dir.name,
        "task_id": identity.get("task_id"),
        "arm": identity.get("arm"),
        "repetition": identity.get("repetition"),
        "session_id": identity.get("session_id"),
        "provider_thread_id": baseline.get("provider_thread_id"),
        "outcome": measurement.get("outcome"),
        "answer_correct": measurement.get("answer_correct"),
        "task_correct": measurement.get("task_correct"),
        "read_count": measurement.get("read_count"),
        "replayed": replay_ok and measurement_replayed,
        "reconciled": reconciled,
        "complete": accounting_complete,
    }


def copy_dict(value: Any) -> Any:
    """Small local deep copy that keeps the verifier dependency-free."""
    return json.loads(json.dumps(value, ensure_ascii=False))


def _verify_runner_summary(output: Path, expected_rows: list[dict[str, Any]], checks: list[dict[str, Any]]) -> None:
    summary = _safe_json(output / "summary.json", checks, "summary")
    if not isinstance(summary, dict):
        return
    if summary.get("arm") != "A" or summary.get("planned_runs") != 51 or summary.get("recorded_runs") != 51 or summary.get("complete_batch") is not True:
        _failure(checks, "summary", "summary_plan_mismatch", "runner summary does not describe the complete 51-run A-only plan")
    if summary.get("results") != expected_rows:
        _failure(checks, "summary", "summary_results_mismatch", "summary.results differs from flattened saved artifacts")


def _verify_report_summary(output: Path, checks: list[dict[str, Any]]) -> None:
    report = _safe_json(output / "report-summary.json", checks, "report-summary")
    if not isinstance(report, dict):
        return
    if report.get("schema_version") != 3 or report.get("arm") != "A" or report.get("planned_runs") != 51 or report.get("recorded_runs") != 51 or report.get("complete_batch") is not True:
        _failure(checks, "report-summary", "report_plan_mismatch", "report summary does not describe the complete 51-run A-only batch")
    if report.get("method") != "all_observed_tool_calls":
        _failure(checks, "report-summary", "report_method_mismatch", "report summary does not use observed-call measurement")
    overall = report.get("overall")
    if not isinstance(overall, dict) or overall.get("measurement_complete") != 51:
        _failure(checks, "report-summary", "report_complete_count", "report summary complete measurement count is not 51")
    if not isinstance(report.get("runs"), list) or len(report["runs"]) != 51:
        _failure(checks, "report-summary", "report_run_count", "report summary does not retain all 51 runs")


def verify(output: Path, corpus_root: Path) -> dict[str, Any]:
    output = output.resolve()
    corpus_root = corpus_root.resolve()
    checks: list[dict[str, Any]] = []
    (repo, wire, check_answer, load_controls, load_corpus, measure,
     reconcile_observed, replay_trace, payload_texts, model_payload,
     expected_pairs) = _imports(corpus_root)
    corpus = load_corpus(corpus_root)
    controls = load_controls(corpus)
    if corpus.get("version") != "typescript-context-v3":
        _failure(checks, "protocol", "wrong_corpus_version", "v3 corpus is required")
    if len(corpus.get("cases", [])) != 17 or controls.get("schedule", {}).get("repetitions") != 3:
        _failure(checks, "protocol", "unexpected_plan", "frozen protocol must contain 17 cases and three repetitions")
    case_ids = controls.get("case_ids")
    if not isinstance(case_ids, list) or case_ids != [case.get("id") for case in corpus.get("cases", [])]:
        _failure(checks, "protocol", "case_order_mismatch", "controls case order differs from corpus")
    expected_count = 51
    cases = {case["id"]: case for case in corpus.get("cases", []) if isinstance(case, dict) and isinstance(case.get("id"), str)}
    transport = _safe_json(output / "transport-verification.json", checks, "transport")
    if not isinstance(transport, dict):
        transport = {}
    transport_schema, transport_tools = _verify_transport(
        output, corpus_root, corpus, transport, reconcile_observed, replay_trace,
        payload_texts, model_payload, expected_pairs, checks)
    _verify_freeze(output, corpus_root, repo, corpus, controls, checks)

    expected_dirs = {f"{case_id}-r{repetition}" for case_id in case_ids or [] for repetition in range(1, 4)}
    actual_dirs = {path.name for path in output.iterdir() if path.is_dir() and RUN_NAME.match(path.name)} if output.is_dir() else set()
    for extra in sorted(actual_dirs - expected_dirs):
        _failure(checks, "batch", "unexpected_attempt_directory", f"unexpected attempt directory {extra}")
    for missing in sorted(expected_dirs - actual_dirs):
        _failure(checks, "batch", "missing_attempt_directory", f"missing attempt directory {missing}")

    reports: list[dict[str, Any]] = []
    expected_rows: list[dict[str, Any]] = []
    identity_keys: set[tuple[str, str, int]] = set()
    sessions: set[str] = set()
    providers: set[str] = set()
    replayed_count = reconciled_count = complete_count = 0
    for case_id in case_ids or []:
        case = cases.get(case_id)
        if case is None:
            _failure(checks, "batch", "missing_case", f"case is absent: {case_id}")
            continue
        for repetition in range(1, 4):
            run_dir = output / f"{case_id}-r{repetition}"
            if not run_dir.is_dir():
                continue
            report = _verify_run(run_dir, case, repetition, corpus, controls, wire, measure,
                                 reconcile_observed, replay_trace, transport_schema, transport_tools,
                                 expected_pairs, checks)
            if report is None:
                continue
            reports.append(report)
            key = (report.get("task_id"), report.get("arm"), report.get("repetition"))
            if key in identity_keys:
                _failure(checks, run_dir.name, "duplicate_identity", f"duplicate run identity {key}")
            identity_keys.add(key)
            session = report.get("session_id")
            provider = report.get("provider_thread_id")
            if not isinstance(session, str) or not session:
                _failure(checks, run_dir.name, "missing_session_id", "run has no session id")
            elif session in sessions:
                _failure(checks, run_dir.name, "duplicate_session_id", f"duplicate session id {session}")
            else:
                sessions.add(session)
            if not isinstance(provider, str) or not provider:
                _failure(checks, run_dir.name, "missing_provider_thread_id", "run has no provider thread id")
            elif provider in providers:
                _failure(checks, run_dir.name, "duplicate_provider_thread_id", f"duplicate provider thread id {provider}")
            else:
                providers.add(provider)
            replayed_count += bool(report["replayed"])
            reconciled_count += bool(report["reconciled"])
            complete_count += bool(report["complete"])
            result = _safe_json(run_dir / "result.json", checks, run_dir.name)
            if isinstance(result, dict) and isinstance(result.get("measurement"), dict) and isinstance(result.get("baseline"), dict):
                expected_rows.append({**result["measurement"], **result["baseline"]})

    expected_identity_keys = {(case_id, "A", repetition) for case_id in (case_ids or []) for repetition in range(1, 4)}
    if identity_keys != expected_identity_keys:
        _failure(checks, "batch", "identity_set_mismatch", "saved identities are not exactly the 51 planned A-only identities")
    _verify_runner_summary(output, expected_rows, checks)
    _verify_report_summary(output, checks)

    ordered_reports = sorted(reports, key=lambda item: (item.get("task_id", ""), item.get("repetition", 0)))
    identity_facts = {
        "corpus_sha256": sha((corpus_root / "corpus.json").read_bytes()),
        "controls_sha256": sha((corpus_root / "comparison-controls.json").read_bytes()),
        "run_identity_sha256": sha(wire(sorted((item.get("task_id"), item.get("arm"), item.get("repetition"), item.get("session_id")) for item in reports)).encode("utf-8")),
        "session_ids_sha256": sha(wire(sorted(sessions)).encode("utf-8")),
        "provider_thread_ids_sha256": sha(wire(sorted(providers)).encode("utf-8")),
    }
    integrity_failures = checks
    passed = (
        not integrity_failures
        and len(reports) == expected_count
        and len(identity_keys) == expected_count
        and len(sessions) == expected_count
        and len(providers) == expected_count
        and replayed_count == expected_count
        and reconciled_count == expected_count
        and complete_count == expected_count
    )
    result = {
        "schema_version": 1,
        "passed": passed,
        "verification_status": "passed" if passed else "failed",
        "corpus_version": corpus.get("version"),
        "planned_count": expected_count,
        "recorded_count": len(reports),
        "unique_identity_count": len(identity_keys),
        "unique_session_count": len(sessions),
        "unique_provider_thread_count": len(providers),
        "replayed_count": replayed_count,
        "reconciled_count": reconciled_count,
        "complete_accounting_count": complete_count,
        "identity_hash_facts": identity_facts,
        "transport_modes": len(transport.get("modes", [])) if isinstance(transport.get("modes"), list) else 0,
        "runs": ordered_reports,
        "failures": integrity_failures,
        "meaning": "Independent v3 artifact integrity verification. Failed answers and budget outcomes retain their measured costs and do not become integrity failures; source, accounting, identity, replay, and frozen-harness violations do.",
    }
    output.mkdir(parents=True, exist_ok=True)
    (output / "verification.json").write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--corpus-root", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = verify(args.output, args.corpus_root)
    except Exception as exc:
        args.output.mkdir(parents=True, exist_ok=True)
        blocked = {"schema_version": 1, "passed": False, "verification_status": "blocked",
                   "planned_count": 51, "recorded_count": 0, "failures": [
                       {"scope": "verifier", "category": "blocked", "message": f"{type(exc).__name__}: {exc}"}
                   ]}
        (args.output.resolve() / "verification.json").write_text(json.dumps(blocked, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(blocked, indent=2))
        return 2
    print(json.dumps({key: result[key] for key in (
        "passed", "verification_status", "planned_count", "recorded_count",
        "replayed_count", "reconciled_count", "complete_accounting_count",
    )}, indent=2))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
