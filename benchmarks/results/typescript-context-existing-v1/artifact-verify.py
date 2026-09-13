#!/usr/bin/env python3
"""Independently verify the frozen TypeScript context A/B comparison artifact.

The verifier only reads the recorded batch, frozen corpus, and frozen source
fingerprints.  It replays observation traces and rebuilds temporary snapshot
indexes under /tmp; it never starts Codex, an MCP server, or a provider call.
A wrong answer or a hard-budget outcome remains a measured result.  Integrity
requires that its calls, costs, usage, provenance, and saved measurement are
complete and reproducible.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Callable


OLD_V3_COMMIT = "e8f26370a7978734e646c0073f22b585be9131a8"
EXPECTED_COMPARISON = "typescript-context-existing-v1"
EXPECTED_MODEL = "gpt-5.6-luna"
EXPECTED_REASONING = "high"
EXPECTED_ATTEMPTS = 102
EXPECTED_CASES = 17
EXPECTED_REPETITIONS = 3
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
EXPECTED_B_MODE = "expanded_get"
ATTEMPT_DIR_RE = re.compile(r"^.+-r[0-9]+-[A-Za-z]$")
OID_RE = re.compile(r"^[0-9a-f]{40}$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


def sha(value: bytes | str) -> str:
    if isinstance(value, str):
        value = value.encode("utf-8")
    return hashlib.sha256(value).hexdigest()


def wire_value(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), allow_nan=False)


def _repo_root(corpus_root: Path) -> Path:
    resolved = corpus_root.resolve()
    try:
        # <checkout>/benchmarks/corpora/typescript-context-v3
        if resolved.parts[-3:] != ("benchmarks", "corpora", "typescript-context-v3"):
            raise ValueError
    except (IndexError, ValueError) as exc:
        raise ValueError(f"corpus root must be <checkout>/benchmarks/corpora/typescript-context-v3: {resolved}") from exc
    return resolved.parents[2]


def _git_bytes(repo: Path, *args: str) -> bytes | None:
    try:
        return subprocess.run(
            ["git", *args], cwd=repo, check=True, capture_output=True
        ).stdout
    except (OSError, subprocess.CalledProcessError):
        return None


def _git_text(repo: Path, *args: str) -> str | None:
    data = _git_bytes(repo, *args)
    if data is None:
        return None
    try:
        return data.decode("utf-8").strip()
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


def _copy(value: Any) -> Any:
    return json.loads(json.dumps(value, ensure_ascii=False, allow_nan=False))


def _imports(repo: Path) -> dict[str, Any]:
    if str(repo) not in sys.path:
        sys.path.insert(0, str(repo))
    from benchmarks.typescript_context_adapter import wire
    from benchmarks.typescript_context_corpus import (
        _isolated_store,
        load_controls,
        load_corpus,
        materialize_snapshot,
    )
    from benchmarks.typescript_context_delivery import payload_texts
    from benchmarks.typescript_context_observed import (
        reconcile_observed,
        replay_trace,
    )
    from benchmarks.typescript_context_tools_v3 import TOOL_NAMES
    from benchmarks.typescript_context_transport_probe import _model_payload
    from benchmarks.typescript_context_expansion_tools import measure as expansion_measure
    from benchmarks.typescript_context_compare import (
        AB_ARM_ORDERS,
        ARM_MODULES,
        EXPECTED_RUNS,
        MODEL,
        REASONING_EFFORT,
        planned_attempts,
    )
    from loci import service

    expected_pairs = {("mcp__evaluation", name) for name in TOOL_NAMES} | {
        ("functions", "list_mcp_resources"),
        ("functions", "list_mcp_resource_templates"),
        ("functions", "read_mcp_resource"),
    }
    return {
        "wire": wire,
        "load_controls": load_controls,
        "load_corpus": load_corpus,
        "materialize_snapshot": materialize_snapshot,
        "isolated_store": _isolated_store,
        "payload_texts": payload_texts,
        "reconcile_observed": reconcile_observed,
        "replay_trace": replay_trace,
        "model_payload": _model_payload,
        "expansion_measure": expansion_measure,
        "ARM_MODULES": ARM_MODULES,
        "AB_ARM_ORDERS": AB_ARM_ORDERS,
        "EXPECTED_RUNS": EXPECTED_RUNS,
        "MODEL": MODEL,
        "REASONING_EFFORT": REASONING_EFFORT,
        "planned_attempts": planned_attempts,
        "service": service,
        "expected_pairs": expected_pairs,
        "tool_names": set(TOOL_NAMES),
    }


def _relative_under(root: Path, value: Any, checks: list[dict[str, Any]], scope: str) -> Path | None:
    if not isinstance(value, str) or not value:
        _failure(checks, scope, "missing_relative_path", "saved path is not a nonempty string")
        return None
    value_path = Path(value)
    if value_path.is_absolute():
        _failure(checks, scope, "absolute_path", "saved path must be relative", path=value)
        return None
    resolved = (root / value_path).resolve()
    try:
        resolved.relative_to(root.resolve())
    except ValueError:
        _failure(checks, scope, "path_escape", "saved path escapes its root", path=value)
        return None
    return resolved


def _path_for_frozen(repo: Path, corpus_root: Path, category: str, relative: str) -> tuple[Path, str]:
    if category == "corpus_files":
        path = corpus_root / relative
        git_path = corpus_root.resolve().relative_to(repo.resolve()).as_posix() + "/" + relative
    else:
        path = repo / relative
        git_path = relative
    return path, git_path


def _validate_hash_map(
    repo: Path,
    corpus_root: Path,
    mapping: Any,
    category: str,
    commit: str,
    checks: list[dict[str, Any]],
) -> dict[str, str]:
    if not isinstance(mapping, dict) or not mapping:
        _failure(checks, "freeze", f"missing_{category}", f"freeze.{category} is not a nonempty object")
        return {}
    normalized: dict[str, str] = {}
    for relative, expected in mapping.items():
        scope = f"freeze/{category}/{relative}"
        if not isinstance(relative, str) or not relative or Path(relative).is_absolute():
            _failure(checks, scope, "invalid_frozen_path", "frozen path is not relative")
            continue
        if not isinstance(expected, str) or not SHA256_RE.fullmatch(expected):
            _failure(checks, scope, "invalid_frozen_hash", "frozen hash is not sha256")
            continue
        try:
            current, git_path = _path_for_frozen(repo, corpus_root, category, relative)
        except ValueError as exc:
            _failure(checks, scope, "frozen_path_outside_repo", str(exc))
            continue
        normalized[relative] = expected
        if not current.is_file():
            _failure(checks, scope, "missing_current_file", f"missing current frozen file: {current}")
        elif sha(current.read_bytes()) != expected:
            _failure(checks, scope, "current_hash_mismatch", "current frozen file differs from pinned hash")
        committed = _git_bytes(repo, "show", f"{commit}:{git_path}")
        if committed is None:
            _failure(checks, scope, "missing_pinned_file", f"file is absent at {commit}: {git_path}")
        elif sha(committed) != expected:
            _failure(checks, scope, "pinned_hash_mismatch", "pinned frozen file differs from freeze hash")
    return normalized


def _git_diff_sha(repo: Path, baseline_commit: str) -> str | None:
    data = _git_bytes(repo, "diff", "--binary", f"{baseline_commit}..HEAD", "--", "src")
    return sha(data) if data is not None else None


def _verify_old_v3_files(repo: Path, corpus_root: Path, checks: list[dict[str, Any]]) -> None:
    """Check that the original v3 freeze and every file it pins are unchanged."""
    old_freeze_path = corpus_root / "freeze.json"
    old_freeze = _safe_json(old_freeze_path, checks, "old-v3-freeze")
    if not isinstance(old_freeze, dict):
        return
    old_freeze_git_path = corpus_root.resolve().relative_to(repo.resolve()).as_posix() + "/freeze.json"
    old_pinned = _git_bytes(repo, "show", f"{OLD_V3_COMMIT}:{old_freeze_git_path}")
    if old_pinned is None:
        _failure(checks, "old-v3-freeze", "missing_old_freeze_at_commit", f"{old_freeze_git_path} absent at {OLD_V3_COMMIT}")
    elif sha(old_pinned) != sha(old_freeze_path.read_bytes()):
        _failure(checks, "old-v3-freeze", "old_freeze_changed", "typescript-context-v3/freeze.json changed since the original v3 commit")
    old_files = old_freeze.get("corpus_files")
    if not isinstance(old_files, dict):
        _failure(checks, "old-v3-freeze", "missing_old_corpus_map", "original v3 freeze has no corpus_files map")
        return
    for relative, expected in old_files.items():
        scope = f"old-v3-freeze/{relative}"
        if not isinstance(relative, str) or not isinstance(expected, str):
            _failure(checks, scope, "invalid_old_file_entry", "original v3 file entry is malformed")
            continue
        current = corpus_root / relative
        git_path = old_freeze_git_path.removesuffix("/freeze.json") + "/" + relative
        if not current.is_file():
            _failure(checks, scope, "missing_old_current_file", f"original v3 file is absent: {relative}")
            continue
        if sha(current.read_bytes()) != expected:
            _failure(checks, scope, "old_file_changed", "original v3 frozen file differs from its original hash")
        pinned = _git_bytes(repo, "show", f"{OLD_V3_COMMIT}:{git_path}")
        if pinned is None:
            _failure(checks, scope, "missing_old_file_at_commit", f"original v3 file absent at {OLD_V3_COMMIT}")
        elif sha(pinned) != expected:
            _failure(checks, scope, "old_pinned_hash_mismatch", "original v3 pinned bytes differ from its hash")


def _verify_freeze(
    repo: Path,
    corpus_root: Path,
    corpus: dict[str, Any],
    controls: dict[str, Any],
    manifest: dict[str, Any],
    environment: dict[str, Any],
    checks: list[dict[str, Any]],
) -> dict[str, Any]:
    freeze_path = repo / "benchmarks" / "comparisons" / EXPECTED_COMPARISON / "freeze.json"
    manifest_freeze = manifest.get("freeze")
    if isinstance(manifest_freeze, dict) and isinstance(manifest_freeze.get("path"), str):
        candidate = Path(manifest_freeze["path"])
        if not candidate.is_absolute():
            candidate = repo / candidate
        if candidate.resolve() != freeze_path.resolve():
            _failure(checks, "freeze", "freeze_path_mismatch", "manifest points to a different comparison freeze")
    freeze = _safe_json(freeze_path, checks, "freeze")
    if not isinstance(freeze, dict):
        freeze = {}
    if freeze.get("version") != EXPECTED_COMPARISON:
        _failure(checks, "freeze", "freeze_version_mismatch", "comparison freeze version is unexpected")

    freeze_commit = freeze.get("freeze_commit")
    candidate_tree = freeze.get("candidate_source_tree")
    baseline_commit = freeze.get("baseline_commit") or controls.get("baseline_engine", {}).get("commit")
    # freeze.json is authored before its carrier commit exists; the runner
    # records the immutable carrier in manifest.freeze/environment instead.
    carrier_commit = (manifest_freeze.get("carrier_commit") if isinstance(manifest_freeze, dict) else None)
    if not isinstance(carrier_commit, str):
        carrier_commit = environment.get("carrier_commit") or _git_text(repo, "rev-parse", "HEAD")
    if not isinstance(freeze_commit, str) or not OID_RE.fullmatch(freeze_commit):
        _failure(checks, "freeze", "invalid_freeze_commit", "freeze_commit must be a full commit id")
        freeze_commit = ""
    if not isinstance(candidate_tree, str) or not OID_RE.fullmatch(candidate_tree):
        _failure(checks, "freeze", "invalid_candidate_tree", "candidate_source_tree must be a full tree id")
        candidate_tree = ""
    if not isinstance(baseline_commit, str) or not OID_RE.fullmatch(baseline_commit):
        _failure(checks, "freeze", "invalid_baseline_commit", "baseline_commit must be a full commit id")
        baseline_commit = ""
    if not isinstance(carrier_commit, str) or not OID_RE.fullmatch(carrier_commit):
        _failure(checks, "freeze", "invalid_carrier_commit", "carrier_commit must be a full commit id")
        carrier_commit = ""

    current_commit = _git_text(repo, "rev-parse", "HEAD")
    current_tree = _git_text(repo, "rev-parse", "HEAD:src")
    frozen_tree = _git_text(repo, "rev-parse", f"{freeze_commit}:src") if freeze_commit else None
    if current_commit is None:
        _failure(checks, "freeze", "missing_current_commit", "cannot resolve current carrier commit")
        current_commit = ""
    if current_tree != candidate_tree:
        _failure(checks, "freeze", "current_source_tree_mismatch", "HEAD:src differs from candidate_source_tree")
    if frozen_tree != candidate_tree:
        _failure(checks, "freeze", "pinned_source_tree_mismatch", "freeze_commit:src differs from candidate_source_tree")
    for ancestor, label, descendant in ((freeze_commit, "carrier_not_descendant", "HEAD"), (freeze_commit, "carrier_not_after_freeze", carrier_commit), (carrier_commit, "carrier_not_ancestor", "HEAD")):
        if ancestor and descendant:
            try:
                subprocess.run(["git", "merge-base", "--is-ancestor", ancestor, descendant], cwd=repo, check=True, capture_output=True)
            except (OSError, subprocess.CalledProcessError):
                _failure(checks, "freeze", label, f"{descendant} is not a descendant of {ancestor}")
    carrier_tree = _git_text(repo, "rev-parse", f"{carrier_commit}:src") if carrier_commit else None
    if carrier_tree != candidate_tree:
        _failure(checks, "freeze", "carrier_source_tree_mismatch", "published carrier src tree differs from candidate_source_tree")

    harness = _validate_hash_map(repo, corpus_root, freeze.get("harness_files"), "harness_files", freeze_commit, checks) if freeze_commit else {}
    corpus_files = _validate_hash_map(repo, corpus_root, freeze.get("corpus_files"), "corpus_files", freeze_commit, checks) if freeze_commit else {}
    comparison_files = _validate_hash_map(repo, corpus_root, freeze.get("comparison_files"), "comparison_files", freeze_commit, checks) if freeze_commit and "comparison_files" in freeze else {}

    required_harness: set[str] = set()
    try:
        from benchmarks.typescript_context_baseline_v3 import HARNESS_FILES
        required_harness.update(str(Path(path).resolve().relative_to(repo.resolve())) for path in HARNESS_FILES)
    except Exception as exc:
        _failure(checks, "freeze", "harness_closure_failed", f"cannot load baseline v3 harness closure: {exc}")
    required_harness.update({
        "benchmarks/typescript_context_expansion_tools.py",
        "benchmarks/typescript_context_expansion_transport.py",
        "benchmarks/typescript_context_compare_report.py",
        "benchmarks/typescript_context_compare.py",
    })
    missing = sorted(required_harness - set(harness))
    if missing:
        _failure(checks, "freeze", "missing_required_harness", ", ".join(missing))

    baseline_tree = _git_text(repo, "rev-parse", f"{baseline_commit}:src") if baseline_commit else None
    if baseline_tree != controls.get("baseline_source_tree"):
        _failure(checks, "freeze", "baseline_tree_mismatch", "baseline commit does not resolve to controls baseline_source_tree")
    candidate_diff = _git_diff_sha(repo, baseline_commit) if baseline_commit else None
    if freeze.get("candidate_diff_sha256") != candidate_diff:
        _failure(checks, "freeze", "candidate_diff_mismatch", "current candidate source diff differs from freeze")

    # Frozen paths must remain clean as well as byte-identical.  This catches
    # staged or intent-to-add changes whose content hash happens to be current.
    frozen_paths = list(harness) + list(comparison_files) + ["src"]
    status = _git_text(repo, "status", "--porcelain", "--", *frozen_paths) if frozen_paths else ""
    if status:
        _failure(checks, "freeze", "frozen_paths_dirty", "frozen harness/source/comparison paths have uncommitted changes", status=status)

    corpus_sha = sha((corpus_root / "corpus.json").read_bytes()) if (corpus_root / "corpus.json").is_file() else None
    controls_sha = sha((corpus_root / "comparison-controls.json").read_bytes()) if (corpus_root / "comparison-controls.json").is_file() else None
    if controls.get("corpus_sha256") != corpus_sha:
        _failure(checks, "freeze", "controls_corpus_hash_mismatch", "controls corpus hash differs from current corpus")
    if corpus.get("version") != "typescript-context-v3" or controls.get("corpus_version") != corpus.get("version"):
        _failure(checks, "freeze", "corpus_version_mismatch", "v3 corpus/controls version contract is not preserved")

    _verify_old_v3_files(repo, corpus_root, checks)

    freeze_sha = sha(freeze_path.read_bytes()) if freeze_path.is_file() else None
    if manifest_freeze is not None and isinstance(manifest_freeze, dict):
        for key in (
            "freeze_commit", "carrier_commit", "candidate_source_tree", "baseline_commit", "baseline_source_tree",
            "candidate_diff_sha256", "current_source_tree", "freeze_json_sha256", "harness_files",
            "comparison_files", "corpus_files",
        ):
            expected = {
                "freeze_commit": freeze_commit,
                "carrier_commit": carrier_commit,
                "candidate_source_tree": candidate_tree,
                "baseline_commit": baseline_commit,
                "baseline_source_tree": controls.get("baseline_source_tree"),
                "candidate_diff_sha256": candidate_diff,
                "current_source_tree": current_tree,
                "freeze_json_sha256": freeze_sha,
                "harness_files": harness,
                "comparison_files": comparison_files or None,
                "corpus_files": freeze.get("corpus_files"),
            }[key]
            if manifest_freeze.get(key) != expected:
                _failure(checks, "freeze", "manifest_freeze_mismatch", f"manifest.freeze.{key} differs from current pinned freeze")

    # The comparison environment intentionally records the machine/package
    # contract plus candidate fingerprints; corpus/control/baseline hashes are
    # manifest fields.  Do not require legacy v3 environment keys that the A/B
    # runner does not emit.
    env_expected = {
        "freeze_commit": freeze_commit,
        "carrier_commit": carrier_commit,
        "candidate_source_tree": candidate_tree,
        "current_source_tree": current_tree,
        "freeze_json_sha256": freeze_sha,
        "harness_files": harness,
        "comparison_files": comparison_files or None,
    }
    for key, expected in env_expected.items():
        if environment.get(key) != expected:
            _failure(checks, "environment", "environment_fingerprint_mismatch", f"environment.{key} differs from freeze")
    for key, expected in (controls.get("environment") or {}).items():
        if environment.get(key) != expected:
            _failure(checks, "environment", "control_environment_mismatch", f"environment.{key} differs from controls")
    expected_cli = controls.get("agent", {}).get("cli_version")
    expected_cli = f"codex-cli {expected_cli}" if isinstance(expected_cli, str) else None
    if environment.get("cli_version") != expected_cli:
        _failure(checks, "environment", "cli_version_mismatch", "environment CLI differs from controls")

    return {
        "version": freeze.get("version"),
        "path": str(freeze_path),
        "freeze_commit": freeze_commit,
        # carrier_commit is the published freeze carrier; current_commit is
        # separately retained so later descendants with the same source tree
        # remain verifiable.
        "carrier_commit": carrier_commit,
        "declared_carrier_commit": carrier_commit,
        "candidate_source_tree": candidate_tree,
        "baseline_commit": baseline_commit,
        "baseline_source_tree": controls.get("baseline_source_tree"),
        "current_commit": current_commit,
        "current_source_tree": current_tree,
        "freeze_json_sha256": freeze_sha,
        "candidate_diff_sha256": candidate_diff,
        "harness_files": harness,
        "corpus_files": freeze.get("corpus_files") if isinstance(freeze.get("corpus_files"), dict) else {},
        "comparison_files": comparison_files or None,
        "created_at": freeze.get("created_at"),
    }


def _actual_tool_set(request: dict[str, Any], wire: Callable[[Any], str]) -> tuple[list[list[str]], str]:
    additional = [
        item for item in request.get("input", [])
        if isinstance(item, dict) and item.get("type") == "additional_tools"
    ]
    namespaces: list[Any] = []
    for item in additional:
        tools = item.get("tools")
        if not isinstance(tools, list):
            raise ValueError("additional_tools item has no tools list")
        namespaces.extend(tools)
    pairs: list[list[str]] = []
    for namespace in namespaces:
        if not isinstance(namespace, dict) or namespace.get("type") != "namespace":
            raise ValueError("additional tool is not a namespace")
        name = namespace.get("name")
        if not isinstance(name, str):
            raise ValueError("namespace has no name")
        tools = namespace.get("tools")
        if not isinstance(tools, list):
            raise ValueError("namespace has no tool list")
        for tool in tools:
            if not isinstance(tool, dict) or not isinstance(tool.get("name"), str):
                raise ValueError("namespace tool has no name")
            pairs.append([name, tool["name"]])
    canonical = sha(wire({"tools": [item["tools"] for item in additional]}))
    return pairs, canonical


def _parse_jsonl(path: Path, checks: list[dict[str, Any]], scope: str) -> list[dict[str, Any]]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        _failure(checks, scope, "missing_events", str(exc))
        return []
    events: list[dict[str, Any]] = []
    for line_number, line in enumerate(lines, 1):
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError as exc:
            _failure(checks, scope, "invalid_event_json", f"line {line_number}: {exc}")
            continue
        if not isinstance(value, dict):
            _failure(checks, scope, "invalid_event", f"line {line_number} is not an object")
            continue
        events.append(value)
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
    item: dict[str, Any],
    case: dict[str, Any],
    controls: dict[str, Any],
    manifest: dict[str, Any],
    expected_schema: str | None,
    expected_tools: list[list[str]] | None,
    expected_pairs: set[tuple[str, str]],
    wire: Callable[[Any], str],
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
    if audit.get("request_sha256") != sha(wire(request)):
        _failure(checks, scope, "request_hash_mismatch", "request hash differs from effective request")
    agent = controls.get("agent", {})
    if request.get("model") != agent.get("model") or request.get("model") != EXPECTED_MODEL:
        _failure(checks, scope, "model_mismatch", "request model differs from the frozen model")
    if request.get("reasoning", {}).get("effort") != agent.get("reasoning_effort"):
        _failure(checks, scope, "reasoning_mismatch", "request reasoning differs from controls")
    request_input = request.get("input")
    expected_prompt = agent.get("common_prompt", "") + case.get("prompt", "")
    if (
        not isinstance(request_input, list)
        or not request_input
        or not isinstance(request_input[-1], dict)
        or request_input[-1].get("content") != [{"type": "input_text", "text": expected_prompt}]
    ):
        _failure(checks, scope, "prompt_mismatch", "effective prompt differs from common prompt plus case prompt")
    try:
        actual_tools, canonical = _actual_tool_set(request, wire)
        additional = [x for x in request_input or [] if isinstance(x, dict) and x.get("type") == "additional_tools"]
        schema_hash = sha(wire({"tools": additional}))
    except Exception as exc:
        _failure(checks, scope, "invalid_tool_schema", f"{type(exc).__name__}: {exc}")
        return
    if audit.get("tool_schemas_sha256") != schema_hash:
        _failure(checks, scope, "tool_schema_hash_mismatch", "request tool schema hash differs")
    if audit.get("canonical_tool_schemas_sha256") != canonical:
        _failure(checks, scope, "canonical_tool_schema_hash_mismatch", "request canonical schema hash differs")
    if expected_schema is not None and canonical != expected_schema:
        _failure(checks, scope, "tool_schema_drift", "request canonical schema differs from transport proof")
    if manifest.get("canonical_tool_schemas_sha256") != canonical:
        _failure(checks, scope, "manifest_schema_drift", "request canonical schema differs from manifest")
    if expected_tools is not None and actual_tools != expected_tools:
        _failure(checks, scope, "tool_set_mismatch", "request tool set differs from transport proof")
    audit_tools = audit.get("tools")
    if audit_tools != actual_tools:
        _failure(checks, scope, "audit_tool_set_mismatch", "request-audit tools differ from effective request")
    actual_pairs = {tuple(pair) for pair in actual_tools if isinstance(pair, list) and len(pair) == 2}
    if len(actual_tools) != len(expected_pairs) or actual_pairs != expected_pairs:
        _failure(checks, scope, "fixed_tool_set_mismatch", "request does not expose exactly the frozen sixteen-tool set")
    # Per-request canonical schema must not silently carry causal controls.
    for namespace in request_input or []:
        if not isinstance(namespace, dict):
            continue
        if namespace.get("type") != "additional_tools":
            continue
        serialized = wire(namespace)
        if any(key in serialized for key in ('"reason"', '"detail"', '"because"')):
            _failure(checks, scope, "causal_parameter_exposed", "tool schema exposes a causal parameter")


def _canonical_config(config: dict[str, Any]) -> dict[str, Any]:
    """Normalize only per-attempt temporary paths for cross-run comparison."""
    value = _copy(config)
    args = value.get("mcp_servers.evaluation.args")
    if isinstance(args, list) and len(args) >= 3:
        args[-1] = "<run.json>"
    env = value.get("mcp_servers.evaluation.env")
    if isinstance(env, dict) and "LOCI_BASE_DIR" in env:
        env["LOCI_BASE_DIR"] = "<temporary-store>"
    return value


def _verify_provenance(
    run_dir: Path,
    item: dict[str, Any],
    case: dict[str, Any],
    corpus: dict[str, Any],
    controls: dict[str, Any],
    manifest: dict[str, Any],
    freeze: dict[str, Any],
    output: Path,
    wire: Callable[[Any], str],
    checks: list[dict[str, Any]],
) -> dict[str, Any] | None:
    scope = run_dir.name + "/provenance"
    provenance = _safe_json(run_dir / "provenance.json", checks, scope)
    result = _safe_json(run_dir / "result.json", checks, scope + "/result")
    if not isinstance(provenance, dict):
        return None
    if isinstance(result, dict) and result.get("provenance") != provenance:
        _failure(checks, scope, "result_provenance_mismatch", "result.provenance differs from provenance.json")
    expected_files = corpus.get("snapshots", {}).get(item["snapshot"], {}).get("files")
    if provenance.get("snapshot_files") != expected_files:
        _failure(checks, scope, "snapshot_fingerprint_mismatch", "provenance snapshot files differ from corpus")
    expected = {
        "attempt_id": item["attempt_id"],
        "case_id": item["case_id"],
        "snapshot": item["snapshot"],
        "repetition": item["repetition"],
        "arm": item["arm"],
        "adapter_module": "benchmarks.typescript_context_expansion_tools",
        "model": EXPECTED_MODEL,
        "reasoning_effort": EXPECTED_REASONING,
        "corpus_sha256": manifest.get("corpus_sha256"),
        "controls_sha256": manifest.get("controls_sha256"),
        "catalog_sha256": manifest.get("catalog_sha256"),
        "runner_sha256": manifest.get("runner_sha256"),
        "canonical_tool_schemas_sha256": manifest.get("canonical_tool_schemas_sha256"),
    }
    for key, value in expected.items():
        if provenance.get(key) != value:
            _failure(checks, scope, "provenance_identity_mismatch", f"provenance.{key} differs from frozen identity")
    prompt = controls.get("agent", {}).get("common_prompt", "") + case.get("prompt", "")
    if provenance.get("prompt_sha256") != sha(prompt):
        _failure(checks, scope, "prompt_hash_mismatch", "provenance prompt hash differs from frozen prompt")
    extractor = corpus.get("baseline_engine", {}).get("extractor_version")
    if provenance.get("extractor_version") != extractor:
        _failure(checks, scope, "extractor_mismatch", "provenance extractor version differs from corpus")
    if not isinstance(provenance.get("index_seconds"), (int, float)) or isinstance(provenance.get("index_seconds"), bool) or provenance["index_seconds"] < 0:
        _failure(checks, scope, "invalid_index_seconds", "provenance index_seconds is not a finite nonnegative number")
    source = provenance.get("source")
    if not isinstance(source, dict):
        _failure(checks, scope, "missing_source_provenance", "provenance.source is not an object")
    else:
        expected_source = {
            "baseline_commit": freeze.get("baseline_commit"),
            "baseline_source_tree": freeze.get("baseline_source_tree"),
            "candidate_source_tree": freeze.get("candidate_source_tree"),
            "candidate_diff_sha256": freeze.get("candidate_diff_sha256"),
            "freeze_commit": freeze.get("freeze_commit"),
            "carrier_commit": freeze.get("carrier_commit"),
            "current_source_tree": freeze.get("current_source_tree"),
            "freeze_json_sha256": freeze.get("freeze_json_sha256"),
            "comparison_files": freeze.get("comparison_files"),
            "source_scope": "retrieval-only candidate; A uses the existing exact v3 path",
        }
        for key, expected in expected_source.items():
            if source.get(key) != expected:
                _failure(checks, scope, "source_provenance_mismatch", f"source.{key} differs from frozen carrier provenance")
        current_attempt_commit = source.get("current_commit")
        if not isinstance(current_attempt_commit, str) or not OID_RE.fullmatch(current_attempt_commit):
            _failure(checks, scope, "source_commit_malformed", "source.current_commit is not a full commit id")
        elif current_attempt_commit != source.get("carrier_commit"):
            _failure(checks, scope, "source_commit_mismatch", "attempt current_commit differs from its frozen carrier_commit")
        if source.get("current_source_tree") != freeze.get("candidate_source_tree"):
            _failure(checks, scope, "source_tree_mismatch", "attempt source tree differs from candidate source tree")
        if source.get("source_scope") != "retrieval-only candidate; A uses the existing exact v3 path":
            _failure(checks, scope, "source_scope_mismatch", "attempt source scope is not the frozen retrieval-only scope")
    config = provenance.get("config")
    if not isinstance(config, dict):
        _failure(checks, scope, "missing_config", "provenance config is not an object")
    else:
        if provenance.get("config_sha256") != sha(wire(config)):
            _failure(checks, scope, "config_hash_mismatch", "provenance config hash differs from config")
        if config.get("model_catalog_json") != str((output / "model-catalog.json").resolve()):
            _failure(checks, scope, "catalog_path_mismatch", "attempt config does not point to retained model catalog")
        args = config.get("mcp_servers.evaluation.args")
        if not isinstance(args, list) or len(args) < 3 or args[:2] != ["-m", "benchmarks.typescript_context_expansion_tools"] or not isinstance(args[-1], str):
            _failure(checks, scope, "adapter_module_mismatch", "attempt config does not select expansion tools for both arms")
        if config.get("mcp_servers.evaluation.command") != str((Path(sys.executable).parent / "python").resolve()) and not str(config.get("mcp_servers.evaluation.command", "")).endswith("/.venv/bin/python"):
            _failure(checks, scope, "python_runtime_mismatch", "attempt config does not use the repository venv python")
        evaluation_env = config.get("mcp_servers.evaluation.env")
        if (not isinstance(evaluation_env, dict) or not isinstance(evaluation_env.get("LOCI_BASE_DIR"), str)
                or not evaluation_env.get("LOCI_BASE_DIR") or evaluation_env.get("LOCI_STORE_NAMESPACE") != "typescript-context-preflight"):
            _failure(checks, scope, "evaluation_environment_mismatch", "attempt config has no isolated preflight store environment")
        if config.get("mcp_servers.evaluation.required") is not True or config.get("mcp_servers.evaluation.default_tools_approval_mode") != "auto":
            _failure(checks, scope, "evaluation_server_config_mismatch", "attempt config changes required/approval semantics")
        serialized = wire(config)
        if any(key in serialized for key in ('"reason"', '"detail"', '"because"')):
            _failure(checks, scope, "causal_config_exposed", "attempt config exposes causal controls")
    provenance["_canonical_config_sha256"] = sha(wire(_canonical_config(config))) if isinstance(config, dict) else None
    return provenance


def _verify_usage(measurement: dict[str, Any], baseline: dict[str, Any], checks: list[dict[str, Any]], scope: str) -> bool:
    usage = measurement.get("provider_usage")
    required = {"input_tokens", "cached_input_tokens", "cache_write_input_tokens", "output_tokens", "reasoning_output_tokens"}
    usage_ok = isinstance(usage, dict) and required.issubset(usage)
    if usage_ok:
        for key in required:
            value = usage.get(key)
            if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                usage_ok = False
                break
        if usage_ok and usage["cached_input_tokens"] > usage["input_tokens"]:
            usage_ok = False
    if not usage_ok:
        _failure(checks, scope, "incomplete_usage", "measurement lacks complete nonnegative provider usage")
    if not isinstance(measurement.get("usage_semantics"), str) or not measurement.get("usage_semantics"):
        _failure(checks, scope, "missing_usage_semantics", "measurement lacks usage semantics")
        usage_ok = False
    if measurement.get("token_status") != "measured":
        _failure(checks, scope, "usage_not_measured", "measurement token_status is not measured")
        usage_ok = False
    accounting = baseline.get("output_accounting")
    accounting_ok = isinstance(accounting, dict) and accounting.get("complete") is True
    if not accounting_ok:
        _failure(checks, scope, "incomplete_accounting", "output accounting is incomplete")
    if measurement.get("measurement_complete") is not True:
        _failure(checks, scope, "measurement_incomplete", "saved measurement is incomplete")
        usage_ok = False
    return bool(usage_ok and accounting_ok and measurement.get("measurement_complete") is True)


def _verify_snapshot(
    corpus: dict[str, Any],
    snapshot: str,
    materialize_snapshot: Callable[[dict[str, Any], str, Path], None],
    destination: Path,
    checks: list[dict[str, Any]],
) -> bool:
    scope = f"snapshot/{snapshot}"
    expected = corpus.get("snapshots", {}).get(snapshot, {}).get("files")
    if not isinstance(expected, dict):
        _failure(checks, scope, "missing_snapshot_files", "snapshot has no files map")
        return False
    try:
        materialize_snapshot(corpus, snapshot, destination)
    except Exception as exc:
        _failure(checks, scope, "snapshot_materialization_failed", f"{type(exc).__name__}: {exc}")
        return False
    actual: dict[str, str] = {}
    for path in destination.rglob("*"):
        if path.is_file():
            actual[str(path.relative_to(destination))] = sha(path.read_bytes())
    if actual != expected:
        _failure(checks, scope, "snapshot_materialization_mismatch", "materialized snapshot files differ from corpus")
        return False
    return True


class _SnapshotIndexes:
    """Materialize and index each frozen snapshot once under a temporary root."""

    def __init__(self, corpus: dict[str, Any], materialize_snapshot: Callable[..., None], isolated_store: Any, service: Any, checks: list[dict[str, Any]]):
        self.corpus = corpus
        self.materialize_snapshot = materialize_snapshot
        self.isolated_store = isolated_store
        self.service = service
        self.checks = checks
        self.temp = tempfile.TemporaryDirectory(prefix="loci-existing-verify-")
        self.root = Path(self.temp.name)
        self.indexes: dict[str, Any] = {}
        self.valid: dict[str, bool] = {}

    def close(self) -> None:
        self.temp.cleanup()

    def get(self, snapshot: str) -> Any | None:
        if snapshot in self.indexes:
            return self.indexes[snapshot]
        if snapshot in self.valid and not self.valid[snapshot]:
            return None
        destination = self.root / "snapshots" / snapshot
        if not _verify_snapshot(self.corpus, snapshot, self.materialize_snapshot, destination, self.checks):
            self.valid[snapshot] = False
            return None
        store = self.root / "stores" / snapshot
        try:
            with self.isolated_store(store):
                self.service.index_repo(destination, incremental=False)
                index = self.service.get_store().load(destination.resolve())
        except Exception as exc:
            self.valid[snapshot] = False
            _failure(self.checks, f"snapshot/{snapshot}", "snapshot_index_failed", f"{type(exc).__name__}: {exc}")
            return None
        if not isinstance(index, dict):
            self.valid[snapshot] = False
            _failure(self.checks, f"snapshot/{snapshot}", "snapshot_index_missing", "fresh index was not persisted")
            return None
        self.indexes[snapshot] = index
        self.valid[snapshot] = True
        return index


def _verify_run(
    run_dir: Path,
    item: dict[str, Any],
    case: dict[str, Any],
    corpus: dict[str, Any],
    controls: dict[str, Any],
    manifest: dict[str, Any],
    freeze: dict[str, Any],
    output: Path,
    imports: dict[str, Any],
    indexes: _SnapshotIndexes,
    checks: list[dict[str, Any]],
    global_ids: dict[str, set[str]],
) -> dict[str, Any] | None:
    scope = run_dir.name
    result = _safe_json(run_dir / "result.json", checks, scope)
    if not isinstance(result, dict):
        return None
    identity = result.get("identity")
    measurement = result.get("measurement")
    baseline = result.get("baseline")
    if not all(isinstance(value, dict) for value in (identity, measurement, baseline)):
        _failure(checks, scope, "invalid_artifact", "result must contain identity, measurement, and baseline objects")
        return None
    if result.get("schema_version") != 3 or measurement.get("schema_version") != 3:
        _failure(checks, scope, "artifact_schema_mismatch", "result and measurement must use schema 3")
    expected_identity = {
        "task_id": item["case_id"],
        "arm": item["arm"],
        "repetition": item["repetition"],
        "snapshot": item["snapshot"],
    }
    if result.get("attempt_id") != item["attempt_id"] or result.get("arm") != item["arm"]:
        _failure(checks, scope, "attempt_identity_mismatch", "top-level attempt identity differs from plan")
    if measurement.get("intent_collection") != "not_collected":
        _failure(checks, scope, "intent_collection_exposed", "observed v3 measurement exposes model intent/causal collection")
    for key, expected in expected_identity.items():
        if identity.get(key) != expected or measurement.get(key) != expected:
            _failure(checks, scope, "run_identity_mismatch", f"{key} differs from immutable plan")
    if identity != {key: measurement.get(key) for key in identity}:
        _failure(checks, scope, "identity_copy_mismatch", "measurement identity differs from trace identity")
    if identity.get("session_id") != measurement.get("session_id"):
        _failure(checks, scope, "session_mismatch", "measurement and trace session IDs differ")
    session = identity.get("session_id")
    if not isinstance(session, str) or not session.startswith(item["attempt_id"] + "-"):
        _failure(checks, scope, "session_id_format", "session ID is not bound to the planned attempt")
    elif session in global_ids["sessions"]:
        _failure(checks, scope, "duplicate_session_id", f"session ID is reused: {session}")
    else:
        global_ids["sessions"].add(session)
    for key, expected in (
        ("corpus_sha256", manifest.get("corpus_sha256")),
        ("controls_sha256", manifest.get("controls_sha256")),
        ("controls_version", controls.get("version")),
    ):
        if identity.get(key) != expected:
            _failure(checks, scope, "trace_fingerprint_mismatch", f"identity.{key} differs from current frozen value")

    trace_path = run_dir / "adapter-trace.json"
    raw_trace = _safe_json(trace_path, checks, scope + "/trace")
    if not isinstance(raw_trace, dict):
        return {
            "attempt_id": item["attempt_id"], "task_id": item["case_id"], "arm": item["arm"],
            "repetition": item["repetition"], "session_id": session, "provider_thread_id": baseline.get("provider_thread_id"),
            "outcome": measurement.get("outcome"), "answer_correct": measurement.get("answer_correct"),
            "task_correct": measurement.get("task_correct"), "read_count": measurement.get("read_count"),
            "replayed": False, "reconciled": False, "complete": False, "usage_complete": False,
        }
    if raw_trace.get("schema_version") != 3 or raw_trace.get("identity") != identity:
        _failure(checks, scope + "/trace", "trace_identity_mismatch", "adapter trace schema or identity differs from result")
    if raw_trace.get("events") != result.get("events"):
        _failure(checks, scope + "/trace", "trace_event_mismatch", "result events differ from adapter trace")
    copy_trace = _safe_json(run_dir / "adapter-trace-copy.json", checks, scope + "/trace-copy")
    if copy_trace != raw_trace:
        _failure(checks, scope + "/trace-copy", "trace_copy_mismatch", "adapter-trace-copy.json differs from adapter-trace.json")
    initial = _safe_json(run_dir / "initial-trace.json", checks, scope + "/initial-trace")
    if isinstance(initial, dict):
        if initial.get("schema_version") != 3 or initial.get("identity") != identity or initial.get("events") or initial.get("deliveries") or initial.get("attempts") != 0 or initial.get("failures"):
            _failure(checks, scope + "/initial-trace", "initial_trace_not_empty", "initial trace is not a schema-3 empty trace with the planned identity")

    try:
        replayed_trace = imports["replay_trace"](corpus, raw_trace)
        replay_ok = replayed_trace.events == raw_trace.get("events") and replayed_trace.identity == identity
    except Exception as exc:
        replay_ok = False
        _failure(checks, scope + "/trace", "trace_replay_failed", f"{type(exc).__name__}: {exc}")
    if not replay_ok:
        _failure(checks, scope + "/trace", "trace_replay_mismatch", "replayed source trace differs from raw trace")

    trace_event_ids = []
    for event in raw_trace.get("events", []):
        event_id = event.get("id") if isinstance(event, dict) else None
        if not isinstance(event_id, str) or not event_id:
            _failure(checks, scope + "/trace", "missing_trace_event_id", "source trace event has no id")
        else:
            trace_event_ids.append(event_id)
            if event_id in global_ids["trace_events"]:
                _failure(checks, scope + "/trace", "duplicate_trace_event_id", f"trace event id is reused: {event_id}")
            global_ids["trace_events"].add(event_id)
    deliveries = raw_trace.get("deliveries")
    if not isinstance(deliveries, list) or raw_trace.get("attempts") != len(deliveries):
        _failure(checks, scope + "/trace", "invalid_attempt_count", "trace attempts does not equal delivery count")
    if isinstance(deliveries, list):
        expected_delivery_ids = [f"{session}/attempt/{n}" for n in range(1, len(deliveries) + 1)] if isinstance(session, str) else []
        actual_delivery_ids = [entry.get("attempt_id") for entry in deliveries if isinstance(entry, dict)]
        if actual_delivery_ids != expected_delivery_ids:
            _failure(checks, scope + "/trace", "invalid_delivery_sequence", "trace delivery IDs are not the exact session sequence")

    provider_events = _parse_jsonl(run_dir / "events.jsonl", checks, scope + "/provider-events")
    saved_provider_events = _safe_json(run_dir / "events.json", checks, scope + "/provider-events-copy")
    if saved_provider_events != provider_events:
        _failure(checks, scope + "/provider-events", "provider_events_copy_mismatch", "events.json differs from JSONL")
    _verify_lifecycle(provider_events, checks, scope + "/provider-events")
    for event in provider_events:
        item_value = event.get("item")
        if isinstance(item_value, dict) and item_value.get("type") == "mcp_tool_call":
            args = item_value.get("arguments")
            if isinstance(args, dict) and any(key in args for key in ("reason", "detail", "because")):
                _failure(checks, scope + "/provider-events", "causal_argument_observed", "provider tool call contains a causal argument")
    thread_ids = [event.get("thread_id") for event in provider_events if event.get("type") == "thread.started"]
    provider_thread = baseline.get("provider_thread_id")
    if len(thread_ids) != 1 or not isinstance(thread_ids[0], str) or not thread_ids[0]:
        _failure(checks, scope + "/provider-events", "provider_thread_missing", "provider event stream must contain one thread.started id")
    elif thread_ids[0] != provider_thread:
        _failure(checks, scope + "/provider-events", "provider_thread_mismatch", "provider thread differs from baseline")
    if isinstance(provider_thread, str) and provider_thread:
        if provider_thread in global_ids["providers"]:
            _failure(checks, scope, "duplicate_provider_thread_id", f"provider thread id is reused: {provider_thread}")
        global_ids["providers"].add(provider_thread)

    try:
        accounting = imports["reconcile_observed"](raw_trace, provider_events)
        compare_accounting = _copy(accounting)
        compare_accounting.pop("validated_results", None)
        reconciled = True
        if baseline.get("output_accounting") != compare_accounting:
            _failure(checks, scope + "/accounting", "output_accounting_mismatch", "saved accounting differs from exact event/trace reconciliation")
        for row in accounting.get("calls", []):
            attempt_value = row.get("attempt_id") if isinstance(row, dict) else None
            if isinstance(attempt_value, str) and attempt_value:
                if attempt_value in global_ids["delivery_attempts"]:
                    _failure(checks, scope + "/accounting", "duplicate_delivery_attempt_id", f"delivery attempt id is reused: {attempt_value}")
                global_ids["delivery_attempts"].add(attempt_value)
    except Exception as exc:
        accounting = {}
        reconciled = False
        _failure(checks, scope + "/accounting", "reconciliation_failed", f"{type(exc).__name__}: {exc}")

    # Check the temporary materialization independently, and use the fresh
    # index so expansion_tools.measure reproduces the complete relationship
    # object rather than dropping B's canonical type-context edges.
    index = indexes.get(item["snapshot"])
    elapsed = baseline.get("actual_process_seconds")
    exit_code = baseline.get("exit_code")
    measurement_replayed = False
    baseline_replayed = False
    if not isinstance(elapsed, (int, float)) or isinstance(elapsed, bool) or not math.isfinite(float(elapsed)) or elapsed < 0 or not isinstance(exit_code, int) or isinstance(exit_code, bool):
        _failure(checks, scope, "invalid_termination", "saved elapsed or exit code is invalid")
    elif replay_ok and reconciled and index is not None:
        try:
            recomputed = imports["expansion_measure"](
                corpus, case, {"trace_path": str(trace_path)}, provider_events,
                elapsed, exit_code, measurement.get("outcome") == "timeout", index,
            )
            measurement_replayed = recomputed.get("measurement") == measurement
            if not measurement_replayed:
                _failure(checks, scope, "measurement_replay_mismatch", "saved measurement differs from exact recomputation")
            recomputed_baseline = recomputed.get("baseline", {})
            recomputed_baseline = _copy(recomputed_baseline)
            recomputed_baseline["arm"] = item["arm"]
            recomputed_baseline["attempt_id"] = item["attempt_id"]
            baseline_replayed = recomputed_baseline == baseline
            if not baseline_replayed:
                _failure(checks, scope, "baseline_replay_mismatch", "saved full baseline differs from exact expansion measurement")
        except Exception as exc:
            _failure(checks, scope, "measurement_replay_failed", f"{type(exc).__name__}: {exc}")
    elif index is None:
        _failure(checks, scope, "missing_snapshot_index", "cannot rerun measurement without a fresh snapshot index")

    expected_schema = manifest.get("canonical_tool_schemas_sha256")
    expected_tools = global_ids.get("transport_tools")
    _verify_request(
        run_dir, item, case, controls, manifest, expected_schema,
        expected_tools, imports["expected_pairs"], imports["wire"], checks,
    )
    provenance = _verify_provenance(run_dir, item, case, corpus, controls, manifest, freeze, output, imports["wire"], checks)
    if isinstance(provenance, dict) and isinstance(provenance.get("_canonical_config_sha256"), str):
        global_ids["config_hashes"].add(provenance["_canonical_config_sha256"])
    accounting_complete = isinstance(baseline.get("output_accounting"), dict) and baseline["output_accounting"].get("complete") is True
    if baseline.get("tool_delivery_verified") != accounting_complete:
        _failure(checks, scope + "/accounting", "delivery_flag_mismatch", "tool_delivery_verified disagrees with accounting")
    usage_complete = _verify_usage(measurement, baseline, checks, scope + "/usage")

    # A false answer, tool failure, timeout, malformed answer, or budget
    # exhaustion is a valid recorded outcome.  It is intentionally omitted
    # from integrity failures; only missing evidence/measurement is fatal.
    return {
        "attempt_id": item["attempt_id"],
        "task_id": identity.get("task_id"),
        "arm": identity.get("arm"),
        "repetition": identity.get("repetition"),
        "session_id": identity.get("session_id"),
        "provider_thread_id": provider_thread,
        "outcome": measurement.get("outcome"),
        "answer_correct": measurement.get("answer_correct"),
        "task_correct": measurement.get("task_correct"),
        "read_count": measurement.get("read_count"),
        "replayed": bool(replay_ok and measurement_replayed and baseline_replayed),
        "reconciled": bool(reconciled),
        "complete": bool(accounting_complete),
        "usage_complete": bool(usage_complete),
    }


def _verify_transport_mode(
    mode: dict[str, Any],
    evidence: Path,
    corpus: dict[str, Any],
    expected_schema: str,
    expected_tools: list[list[str]],
    expected_pairs: set[tuple[str, str]],
    replay_trace: Callable[..., Any],
    reconcile_observed: Callable[..., Any],
    payload_texts: Callable[..., Any],
    model_payload: Callable[..., Any],
    wire: Callable[[Any], str],
    checks: list[dict[str, Any]],
    scope: str,
    *,
    b_mode: bool = False,
) -> None:
    required_files = ("events.json", "trace.json", "effective-request.json", "accounting.json", "next-request.json", "stdout.jsonl", "stderr.txt", "initial-trace.json", "run.json")
    for name in required_files:
        if not (evidence / name).is_file():
            _failure(checks, scope, "missing_evidence_file", f"missing {name}")
    trace = _safe_json(evidence / "trace.json", checks, scope + "/trace")
    events = _safe_json(evidence / "events.json", checks, scope + "/events")
    saved_accounting = _safe_json(evidence / "accounting.json", checks, scope + "/accounting")
    request = _safe_json(evidence / "effective-request.json", checks, scope + "/request")
    next_request = _safe_json(evidence / "next-request.json", checks, scope + "/next-request")
    stdout_events = _parse_jsonl(evidence / "stdout.jsonl", checks, scope + "/stdout")
    if isinstance(events, list) and stdout_events != events:
        _failure(checks, scope, "stdout_events_mismatch", "stdout JSONL differs from events.json")
    if not isinstance(trace, dict) or not isinstance(events, list) or not isinstance(saved_accounting, dict):
        return
    if trace.get("schema_version") != 3 or trace.get("identity", {}).get("task_id") != "imported_interface":
        _failure(checks, scope, "trace_identity_mismatch", "transport trace is not the imported_interface v3 trace")
    if trace.get("identity", {}).get("arm") != ("B" if b_mode else "A"):
        _failure(checks, scope, "trace_arm_mismatch", "transport trace arm differs from proof")
    try:
        replayed = replay_trace(corpus, trace)
        if replayed.events != trace.get("events"):
            _failure(checks, scope, "trace_replay_mismatch", "transport trace does not replay exactly")
    except Exception as exc:
        _failure(checks, scope, "trace_replay_failed", f"{type(exc).__name__}: {exc}")
    try:
        actual_accounting = reconcile_observed(trace, events)
        if saved_accounting != actual_accounting:
            _failure(checks, scope, "accounting_mismatch", "saved accounting differs from raw transport events")
        metadata_accounting = mode.get("observed_accounting")
        if metadata_accounting != actual_accounting:
            _failure(checks, scope, "metadata_accounting_mismatch", "proof accounting differs from raw transport events")
    except Exception as exc:
        _failure(checks, scope, "reconciliation_failed", f"{type(exc).__name__}: {exc}")
    terminal = [
        event.get("item") for event in events
        if isinstance(event, dict)
        and event.get("type") in {"item.completed", "item.failed"}
        and isinstance(event.get("item"), dict)
        and event["item"].get("type") == "mcp_tool_call"
    ]
    if len(terminal) != 1:
        _failure(checks, scope, "terminal_call_count", "transport evidence must contain exactly one terminal MCP call")
    else:
        call = terminal[0]
        if mode.get("call_item") != call:
            _failure(checks, scope, "call_item_mismatch", "proof call_item differs from terminal provider call")
        if b_mode:
            structured = ((call.get("result") or {}).get("structured_content") if isinstance(call.get("result"), dict) else None)
            context = structured.get("type_context") if isinstance(structured, dict) else None
            if not isinstance(context, dict) or context.get("status") != "complete" or not context.get("references"):
                _failure(checks, scope, "missing_type_context", "B transport call does not retain complete type_context references")
            elif any(not isinstance(ref, dict) or not isinstance(ref.get("edge"), dict) for ref in context["references"]):
                _failure(checks, scope, "invalid_type_context_edges", "B type_context references lack canonical edge objects")
        if isinstance(next_request, dict):
            outputs = [x for x in next_request.get("input", []) if isinstance(x, dict) and x.get("type") == "function_call_output"]
            if len(outputs) != 1:
                _failure(checks, scope, "next_request_output_count", "next request does not contain exactly one function_call_output")
            else:
                try:
                    kind, texts = payload_texts(call)
                    decoded = model_payload(outputs[0].get("output"), kind)
                    if decoded != texts:
                        _failure(checks, scope, "payload_replay_mismatch", "next-request payload differs from terminal tool call")
                    if mode.get("payload_kind") != kind or mode.get("payload_texts") != texts:
                        _failure(checks, scope, "saved_payload_mismatch", "proof payload differs from terminal tool call")
                    proof_outputs = mode.get("model_tool_outputs")
                    if proof_outputs != outputs:
                        _failure(checks, scope, "logged_output_mismatch", "logged model tool output differs from next request")
                except Exception as exc:
                    _failure(checks, scope, "payload_validation_failed", f"{type(exc).__name__}: {exc}")
        else:
            _failure(checks, scope, "invalid_next_request", "next request is not an object")
    if not isinstance(request, dict):
        _failure(checks, scope, "invalid_effective_request", "effective request is not an object")
    else:
        try:
            actual_tools, actual_schema = _actual_tool_set(request, wire)
            if actual_schema != expected_schema or actual_schema != mode.get("canonical_tool_schemas_sha256"):
                _failure(checks, scope, "actual_schema_mismatch", "effective request schema differs from proof schema")
            actual_pairs = {tuple(pair) for pair in actual_tools if isinstance(pair, list) and len(pair) == 2}
            if actual_tools != expected_tools or len(actual_tools) != len(expected_pairs) or actual_pairs != expected_pairs:
                _failure(checks, scope, "actual_tool_set_mismatch", "effective request does not expose exactly the frozen tool set")
            if mode.get("tool_set") != actual_tools:
                _failure(checks, scope, "saved_tool_set_mismatch", "proof tool set differs from effective request")
        except Exception as exc:
            _failure(checks, scope, "request_validation_failed", f"{type(exc).__name__}: {exc}")
    if mode.get("trace_schema_version") != 3 or mode.get("canonical_tool_schemas_sha256") != expected_schema:
        _failure(checks, scope, "proof_schema_mismatch", "mode proof schema metadata differs")
    if mode.get("output_verified") is not True or mode.get("request_count") != 2:
        _failure(checks, scope, "proof_unverified", "mode does not record a verified two-request exchange")
    if mode.get("observed_accounting", {}).get("complete") is not True:
        _failure(checks, scope, "proof_accounting_incomplete", "mode accounting is incomplete")


def _verify_transport(
    output: Path,
    corpus_root: Path,
    corpus: dict[str, Any],
    manifest: dict[str, Any],
    environment: dict[str, Any],
    imports: dict[str, Any],
    checks: list[dict[str, Any]],
) -> tuple[str | None, list[list[str]] | None]:
    proof_path = output / str(manifest.get("transport_proof_file", "transport-verification.json"))
    proof = _safe_json(proof_path, checks, "transport")
    if not isinstance(proof, dict):
        return None, None
    expected_schema = proof.get("canonical_tool_schemas_sha256")
    catalog = output / "model-catalog.json"
    expected_corpus = sha((corpus_root / "corpus.json").read_bytes()) if (corpus_root / "corpus.json").is_file() else None
    expected_controls = sha((corpus_root / "comparison-controls.json").read_bytes()) if (corpus_root / "comparison-controls.json").is_file() else None
    for key, expected in (
        ("schema_version", 3), ("probe", "typescript-context-v3-typed-transport"),
        ("model", EXPECTED_MODEL), ("reasoning_effort", EXPECTED_REASONING), ("tool_count", 16),
        ("corpus_sha256", expected_corpus), ("controls_sha256", expected_controls),
        ("catalog_sha256", sha(catalog.read_bytes()) if catalog.is_file() else None),
        ("script_sha256", sha((imports["repo"] / "benchmarks/typescript_context_transport_v3.py").read_bytes()) if (imports["repo"] / "benchmarks/typescript_context_transport_v3.py").is_file() else None),
        ("controls_version", None),
    ):
        if key == "controls_version":
            continue
        if proof.get(key) != expected:
            _failure(checks, "transport", "proof_field_mismatch", f"transport.{key} differs from frozen value")
    if proof.get("controls_version") != controls_version_from(corpus):
        _failure(checks, "transport", "controls_version_mismatch", "transport proof controls version differs")
    if proof.get("canonical_tool_schemas_sha256") != manifest.get("canonical_tool_schemas_sha256"):
        _failure(checks, "transport", "schema_hash_mismatch", "transport schema differs from manifest")
        expected_schema = manifest.get("canonical_tool_schemas_sha256")
    if proof_path.is_file() and manifest.get("transport_proof_sha256") != sha(proof_path.read_bytes()):
        _failure(checks, "transport", "proof_hash_mismatch", "saved transport proof differs from manifest hash")
    if not proof_path.is_file() or environment.get("transport_proof_sha256") != sha(proof_path.read_bytes()):
        _failure(checks, "environment", "proof_hash_mismatch", "environment transport proof hash differs")
    modes = proof.get("modes")
    if not isinstance(modes, list) or len(modes) != len(EXPECTED_TRANSPORT_MODES):
        _failure(checks, "transport", "mode_count", "transport proof must contain exactly ten modes")
        modes = []
    ids = {mode.get("mode") for mode in modes if isinstance(mode, dict)}
    if ids != EXPECTED_TRANSPORT_MODES:
        _failure(checks, "transport", "mode_set", "transport proof mode set differs from frozen ten modes")
    evidence_root = _relative_under(output, proof.get("evidence_root"), checks, "transport/evidence_root")
    expected_tools: list[list[str]] | None = None
    schema = expected_schema if isinstance(expected_schema, str) else None
    # Derive the fixed tool list from the first saved effective request before
    # validating individual modes; the first mode must not be compared to an
    # empty placeholder.
    if evidence_root and evidence_root.is_dir():
        for candidate_mode in modes:
            if isinstance(candidate_mode, dict):
                candidate_evidence = _relative_under(output, candidate_mode.get("evidence_dir"), checks, "transport/tool-list-evidence")
                if candidate_evidence and (candidate_evidence / "effective-request.json").is_file():
                    candidate_request = _safe_json(candidate_evidence / "effective-request.json", checks, "transport/tool-list-request")
                    if isinstance(candidate_request, dict):
                        try:
                            expected_tools, _ = _actual_tool_set(candidate_request, imports["wire"])
                        except Exception:
                            pass
                    break
    if schema and evidence_root and evidence_root.is_dir():
        for mode in modes:
            if not isinstance(mode, dict):
                _failure(checks, "transport", "invalid_mode", "transport mode is not an object")
                continue
            mode_scope = f"transport/{mode.get('mode', '<unknown>')}"
            evidence = _relative_under(output, mode.get("evidence_dir"), checks, mode_scope + "/evidence")
            if evidence is None or not evidence.is_dir():
                _failure(checks, mode_scope, "missing_evidence", "mode evidence directory is absent")
                continue
            _verify_transport_mode(
                mode, evidence, corpus, schema, expected_tools or [], imports["expected_pairs"],
                imports["replay_trace"], imports["reconcile_observed"], imports["payload_texts"],
                imports["model_payload"], imports["wire"], checks, mode_scope,
            )
            actual_request = _safe_json(evidence / "effective-request.json", checks, mode_scope + "/request-again")
            if isinstance(actual_request, dict):
                try:
                    actual, _ = _actual_tool_set(actual_request, imports["wire"])
                    if expected_tools is None:
                        expected_tools = actual
                    elif actual != expected_tools:
                        _failure(checks, mode_scope, "tool_drift", "transport modes expose different tools")
                except Exception:
                    pass
    # Set the fixed tool list from the first effective request if not already
    # discovered, so measured request checks can bind to transport evidence.
    if expected_tools is None and modes:
        first = modes[0] if isinstance(modes[0], dict) else {}
        evidence = _relative_under(output, first.get("evidence_dir"), checks, "transport/first-evidence")
        if evidence and (evidence / "effective-request.json").is_file():
            try:
                expected_tools, _ = _actual_tool_set(_read_json(evidence / "effective-request.json"), imports["wire"])
            except Exception:
                expected_tools = None
    return schema, expected_tools


def controls_version_from(corpus: dict[str, Any]) -> str | None:
    # The corpus loader attaches controls only when called; the controls file
    # is read separately by verify(), so this helper is intentionally tolerant.
    return "typescript-context-controls-v3"


def _verify_b_transport(
    output: Path,
    corpus_root: Path,
    corpus: dict[str, Any],
    manifest: dict[str, Any],
    environment: dict[str, Any],
    imports: dict[str, Any],
    expected_schema: str | None,
    expected_tools: list[list[str]] | None,
    checks: list[dict[str, Any]],
) -> None:
    proof_path = output / str(manifest.get("expansion_transport_proof_file", "expansion-transport-verification.json"))
    proof = _safe_json(proof_path, checks, "expansion-transport")
    if not isinstance(proof, dict):
        return
    for key, expected in (
        ("schema_version", 1), ("probe", "typescript-context-expanded-get-transport"),
        ("case_id", "imported_interface"), ("arm", "B"), ("model", EXPECTED_MODEL),
        ("reasoning_effort", EXPECTED_REASONING), ("canonical_tool_schemas_sha256", expected_schema),
    ):
        if proof.get(key) != expected:
            _failure(checks, "expansion-transport", "proof_field_mismatch", f"expansion transport {key} differs")
    if proof_path.is_file() and manifest.get("expansion_transport_proof_sha256") != sha(proof_path.read_bytes()):
        _failure(checks, "expansion-transport", "proof_hash_mismatch", "B transport proof differs from manifest hash")
    if proof_path.is_file() and environment.get("expansion_transport_proof_sha256") != sha(proof_path.read_bytes()):
        _failure(checks, "environment", "b_proof_hash_mismatch", "environment B proof hash differs")
    observation = proof.get("observation")
    if not isinstance(observation, dict):
        _failure(checks, "expansion-transport", "missing_observation", "B proof has no observation")
        return
    if observation.get("mode") != EXPECTED_B_MODE:
        _failure(checks, "expansion-transport", "mode_mismatch", "B proof mode is not expanded_get")
    for key, expected in (("request_count", 2), ("output_verified", True), ("adapter_attempts", 1), ("adapter_deliveries", 1), ("trace_schema_version", 3)):
        if observation.get(key) != expected:
            _failure(checks, "expansion-transport", "observation_incomplete", f"B observation {key} differs")
    root = _relative_under(output, proof.get("evidence_root"), checks, "expansion-transport/evidence_root")
    evidence = _relative_under(output, observation.get("evidence_dir"), checks, "expansion-transport/observation-evidence")
    if root is None or evidence is None or not evidence.is_dir():
        return
    if not str(evidence).startswith(str(root)):
        _failure(checks, "expansion-transport", "evidence_root_mismatch", "B observation evidence escapes proof evidence_root")
    _verify_transport_mode(
        observation, evidence, corpus, expected_schema or "", expected_tools or [], imports["expected_pairs"],
        imports["replay_trace"], imports["reconcile_observed"], imports["payload_texts"],
        imports["model_payload"], imports["wire"], checks, "expansion-transport/expanded_get", b_mode=True,
    )
    artifacts = proof.get("artifacts")
    if not isinstance(artifacts, list) or not artifacts:
        _failure(checks, "expansion-transport", "missing_artifacts", "B proof has no artifact hashes")
    else:
        listed: set[str] = set()
        for entry in artifacts:
            scope = "expansion-transport/artifact"
            if not isinstance(entry, dict) or not isinstance(entry.get("path"), str):
                _failure(checks, scope, "invalid_artifact_entry", "B artifact entry is malformed")
                continue
            path = _relative_under(output, entry["path"], checks, scope)
            if path is None:
                continue
            listed.add(entry["path"])
            if not path.is_file():
                _failure(checks, scope, "missing_artifact", f"missing B proof artifact: {entry['path']}")
                continue
            data = path.read_bytes()
            if entry.get("bytes") != len(data):
                _failure(checks, scope, "artifact_size_mismatch", f"B artifact size differs: {entry['path']}")
            if entry.get("sha256") != sha(data):
                _failure(checks, scope, "artifact_hash_mismatch", f"B artifact hash differs: {entry['path']}")
        for required in ("trace.json", "events.json", "effective-request.json", "next-request.json", "accounting.json"):
            if not any(path.endswith("/" + required) or path == required for path in listed):
                _failure(checks, "expansion-transport", "artifact_manifest_missing", f"B artifact manifest omits {required}")


def _verify_manifest_fingerprints(
    output: Path, corpus_root: Path, repo: Path, manifest: dict[str, Any],
    freeze: dict[str, Any], checks: list[dict[str, Any]],
) -> None:
    """Bind manifest hashes to current bytes and to the published freeze."""
    corpus_path = corpus_root / "corpus.json"
    controls_path = corpus_root / "comparison-controls.json"
    expected = {
        "corpus_sha256": sha(corpus_path.read_bytes()) if corpus_path.is_file() else None,
        "controls_sha256": sha(controls_path.read_bytes()) if controls_path.is_file() else None,
        "runner_sha256": sha((repo / "benchmarks/typescript_context_compare.py").read_bytes()) if (repo / "benchmarks/typescript_context_compare.py").is_file() else None,
        "transport_script_sha256": sha((repo / "benchmarks/typescript_context_transport_v3.py").read_bytes()) if (repo / "benchmarks/typescript_context_transport_v3.py").is_file() else None,
        "expansion_transport_script_sha256": sha((repo / "benchmarks/typescript_context_expansion_transport.py").read_bytes()) if (repo / "benchmarks/typescript_context_expansion_transport.py").is_file() else None,
    }
    for key, value in expected.items():
        if manifest.get(key) != value:
            _failure(checks, "manifest", "manifest_hash_mismatch", f"manifest.{key} differs from current bytes")
    harness = freeze.get("harness_files") if isinstance(freeze.get("harness_files"), dict) else {}
    for key, relative in (("runner_sha256", "benchmarks/typescript_context_compare.py"), ("transport_script_sha256", "benchmarks/typescript_context_transport_v3.py"), ("expansion_transport_script_sha256", "benchmarks/typescript_context_expansion_transport.py")):
        if relative in harness and manifest.get(key) != harness[relative]:
            _failure(checks, "manifest", "manifest_freeze_hash_mismatch", f"manifest.{key} differs from frozen harness map")
    historical = _safe_json(corpus_root / "transport-verification.json", checks, "historical-transport")
    if isinstance(historical, dict) and manifest.get("canonical_tool_schemas_sha256") != historical.get("canonical_tool_schemas_sha256"):
        _failure(checks, "manifest", "canonical_schema_history_mismatch", "manifest canonical schema differs from the frozen v3 transport proof")
    for key, file_name in (("transport_proof_file", "transport-verification.json"), ("expansion_transport_proof_file", "expansion-transport-verification.json")):
        if manifest.get(key) != file_name:
            _failure(checks, "manifest", "proof_file_mismatch", f"manifest.{key} is not the fixed proof filename")
    if manifest.get("freeze", {}).get("candidate_source_tree") != freeze.get("candidate_source_tree"):
        _failure(checks, "manifest", "manifest_source_tree_mismatch", "manifest candidate source tree differs from freeze")


def _verify_catalog(output: Path, manifest: dict[str, Any], transport: dict[str, Any] | None, checks: list[dict[str, Any]]) -> dict[str, Any] | None:
    path = output / "model-catalog.json"
    catalog = _safe_json(path, checks, "catalog")
    if not isinstance(catalog, dict):
        return None
    data_hash = sha(path.read_bytes()) if path.is_file() else None
    if manifest.get("catalog_file") != "model-catalog.json" or manifest.get("catalog_sha256") != data_hash:
        _failure(checks, "catalog", "catalog_hash_mismatch", "manifest catalog identity differs from retained bytes")
    if isinstance(transport, dict) and transport.get("catalog_sha256") != data_hash:
        _failure(checks, "catalog", "transport_catalog_mismatch", "transport proof catalog differs from retained bytes")
    models = catalog.get("models")
    if not isinstance(models, list) or len(models) != 1 or not isinstance(models[0], dict) or models[0].get("slug") != EXPECTED_MODEL:
        _failure(checks, "catalog", "fresh_catalog_identity", "retained catalog is not the single fresh Luna catalog")
    elif not any(isinstance(level, dict) and level.get("effort") == EXPECTED_REASONING for level in models[0].get("supported_reasoning_levels", [])):
        _failure(checks, "catalog", "catalog_reasoning_level", "fresh catalog does not advertise high reasoning")
    return catalog


def _verify_plan(
    output: Path,
    corpus: dict[str, Any],
    controls: dict[str, Any],
    imports: dict[str, Any],
    checks: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    # Derive the schedule independently of the runner implementation.  The
    # imported runner plan is checked as a second witness, never trusted as
    # the only source of the 102 immutable identities.
    case_ids = controls.get("case_ids")
    cases = corpus.get("cases")
    snapshots = {case.get("id"): case.get("snapshot") for case in cases if isinstance(case, dict)} if isinstance(cases, list) else {}
    expected: list[dict[str, Any]] = []
    if isinstance(case_ids, list) and len(case_ids) == EXPECTED_CASES:
        for case_id in case_ids:
            for repetition, order in enumerate((("A", "B"), ("B", "A"), ("A", "B")), start=1):
                for arm in order:
                    expected.append({
                        "attempt_id": f"{case_id}-r{repetition}-{arm}",
                        "case_id": case_id,
                        "snapshot": snapshots.get(case_id),
                        "repetition": repetition,
                        "arm": arm,
                    })
    try:
        runner_plan = imports["planned_attempts"](corpus, controls)
        if runner_plan != expected:
            _failure(checks, "plan", "runner_plan_mismatch", "runner planned_attempts differs from independently derived schedule")
    except Exception as exc:
        _failure(checks, "plan", "planned_attempts_failed", f"{type(exc).__name__}: {exc}")
    if len(expected) != EXPECTED_ATTEMPTS:
        _failure(checks, "plan", "planned_count", f"expected exactly {EXPECTED_ATTEMPTS} planned attempts")
    plan = _safe_json(output / "plan.json", checks, "plan")
    if not isinstance(plan, dict) or plan.get("schema_version") != 3 or plan.get("attempts") != expected:
        _failure(checks, "plan", "plan_mismatch", "plan.json is not the exact immutable planned order")
    ids = [entry.get("attempt_id") for entry in expected if isinstance(entry, dict)]
    if len(ids) != len(set(ids)) or len(ids) != EXPECTED_ATTEMPTS:
        _failure(checks, "plan", "planned_id_uniqueness", "planned attempt IDs are not unique")
    return expected


def _verify_summary(output: Path, expected_rows: list[dict[str, Any]], checks: list[dict[str, Any]]) -> None:
    summary = _safe_json(output / "summary.json", checks, "summary")
    if not isinstance(summary, dict):
        return
    expected_schedule = {
        "repetitions": 3, "case_order": "corpus_order",
        "arm_orders": [["A", "B"], ["B", "A"], ["A", "B"]], "concurrency": 1,
    }
    for key, expected in (("schema_version", 3), ("comparison", EXPECTED_COMPARISON), ("planned_runs", EXPECTED_ATTEMPTS), ("recorded_runs", EXPECTED_ATTEMPTS), ("complete_batch", True), ("schedule", expected_schedule)):
        if summary.get(key) != expected:
            _failure(checks, "summary", "summary_plan_mismatch", f"summary.{key} differs from exact schedule")
    if summary.get("results") != expected_rows:
        _failure(checks, "summary", "summary_results_mismatch", "summary.results differs from flattened saved artifacts in plan order")


def _summary_row(result: dict[str, Any]) -> dict[str, Any]:
    measurement = result.get("measurement") or {}
    baseline = result.get("baseline") or {}
    row = {**measurement, **baseline}
    row["attempt_id"] = result.get("attempt_id")
    row["arm"] = result.get("arm") or result.get("identity", {}).get("arm")
    row["directory"] = result.get("attempt_id")
    return row


def _verify_provenance_errata(output: Path, freeze: dict[str, Any], checks: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Validate the result-side note without treating descriptive metadata as evidence."""
    path = output / "provenance-errata.json"
    document = _safe_json(path, checks, "provenance-errata")
    if not isinstance(document, dict):
        return None
    if document.get("schema_version") != 1 or document.get("method_changed") is not False or document.get("frozen_files_changed") is not False:
        _failure(checks, "provenance-errata", "errata_contract_mismatch", "result-side errata does not declare metadata-only corrections")
    if document.get("freeze_json_sha256") != freeze.get("freeze_json_sha256"):
        _failure(checks, "provenance-errata", "errata_freeze_hash_mismatch", "errata points at a different comparison freeze")
    first_files = document.get("first_attempt_files")
    if not isinstance(first_files, dict) or not first_files:
        _failure(checks, "provenance-errata", "missing_first_attempt_evidence", "errata has no first-attempt file evidence")
    else:
        for relative, metadata in first_files.items():
            scope = f"provenance-errata/{relative}"
            if not isinstance(metadata, dict) or not isinstance(metadata.get("sha256"), str):
                _failure(checks, scope, "invalid_first_attempt_entry", "first-attempt evidence entry is malformed")
                continue
            path_value = _relative_under(output, relative, checks, scope)
            if path_value is None or not path_value.is_file():
                _failure(checks, scope, "missing_first_attempt_file", "first-attempt evidence file is absent")
            elif sha(path_value.read_bytes()) != metadata.get("sha256"):
                _failure(checks, scope, "first_attempt_hash_mismatch", "first-attempt evidence hash differs")
    return document


def _metadata_errata(repo: Path, freeze: dict[str, Any]) -> list[dict[str, Any]]:
    errata: list[dict[str, Any]] = []
    created = freeze.get("created_at")
    freeze_commit = freeze.get("freeze_commit")
    if isinstance(created, str) and isinstance(freeze_commit, str):
        commit_ts = _git_text(repo, "show", "-s", "--format=%cI", freeze_commit)
        if commit_ts and commit_ts[:19] != created[:19]:
            errata.append({"field": "freeze.created_at", "declared": created, "commit_time": commit_ts, "meaning": "literal metadata differs from carrier chronology; source hashes remain authoritative"})
    acceptance = freeze.get("premeasurement_acceptance")
    if isinstance(acceptance, dict) and acceptance.get("comparison_report_and_expansion_checks_passed") == 20:
        errata.append({"field": "freeze.premeasurement_acceptance.comparison_report_and_expansion_checks_passed", "declared": 20, "meaning": "published label is retained; independent verifier does not reinterpret its count"})
    return errata


def verify(output: Path, corpus_root: Path, report_path: Path | None = None) -> dict[str, Any]:
    output = output.resolve()
    corpus_root = corpus_root.resolve()
    checks: list[dict[str, Any]] = []
    if not output.is_dir():
        _failure(checks, "batch", "missing_output", f"comparison output directory is absent: {output}")
    repo = _repo_root(corpus_root)
    imports = _imports(repo)
    imports["repo"] = repo
    corpus = imports["load_corpus"](corpus_root)
    controls = imports["load_controls"](corpus)
    if corpus.get("version") != "typescript-context-v3":
        _failure(checks, "protocol", "wrong_corpus_version", "typescript-context-v3 corpus is required")
    if len(corpus.get("cases", [])) != EXPECTED_CASES:
        _failure(checks, "protocol", "case_count", "v3 comparison requires exactly 17 cases")
    if controls.get("case_ids") != [case.get("id") for case in corpus.get("cases", [])]:
        _failure(checks, "protocol", "case_order", "controls case order differs from corpus")
    manifest = _safe_json(output / "manifest.json", checks, "manifest")
    if not isinstance(manifest, dict):
        manifest = {}
    if manifest.get("schema_version") != 3 or manifest.get("comparison") != EXPECTED_COMPARISON or manifest.get("planned_runs") != EXPECTED_ATTEMPTS:
        _failure(checks, "manifest", "manifest_protocol_mismatch", "manifest does not describe the frozen 102-run comparison")
    environment = _safe_json(output / "environment.json", checks, "environment")
    if not isinstance(environment, dict):
        environment = {}
    freeze = _verify_freeze(repo, corpus_root, corpus, controls, manifest, environment, checks)
    _verify_manifest_fingerprints(output, corpus_root, repo, manifest, freeze, checks)
    provenance_errata = _verify_provenance_errata(output, freeze, checks)

    transport_catalog_proof = _safe_json(output / str(manifest.get("transport_proof_file", "transport-verification.json")), checks, "transport-for-catalog")
    catalog = _verify_catalog(output, manifest, transport_catalog_proof if isinstance(transport_catalog_proof, dict) else None, checks)
    transport_schema, transport_tools = _verify_transport(output, corpus_root, corpus, manifest, environment, imports, checks)
    _verify_b_transport(output, corpus_root, corpus, manifest, environment, imports, transport_schema, transport_tools, checks)
    plan = _verify_plan(output, corpus, controls, imports, checks)

    cases = {case.get("id"): case for case in corpus.get("cases", []) if isinstance(case, dict) and isinstance(case.get("id"), str)}
    expected_ids = {item.get("attempt_id") for item in plan}
    actual_attempt_dirs = {
        path.name for path in output.iterdir() if path.is_dir() and ATTEMPT_DIR_RE.fullmatch(path.name)
    } if output.is_dir() else set()
    for extra in sorted(actual_attempt_dirs - expected_ids):
        _failure(checks, "batch", "unexpected_attempt_directory", f"unexpected attempt directory {extra}")
    for missing in sorted(expected_ids - actual_attempt_dirs):
        _failure(checks, "batch", "missing_attempt_directory", f"missing planned attempt directory {missing}")

    indexes = _SnapshotIndexes(corpus, imports["materialize_snapshot"], imports["isolated_store"], imports["service"], checks)
    reports: list[dict[str, Any]] = []
    expected_rows: list[dict[str, Any]] = []
    global_ids: dict[str, set[str] | list[list[str]] | None] = {
        "sessions": set(), "providers": set(), "trace_events": set(), "delivery_attempts": set(), "config_hashes": set(), "transport_tools": transport_tools,
    }
    try:
        for item in plan:
            attempt_id = item.get("attempt_id")
            case = cases.get(item.get("case_id"))
            run_dir = output / str(attempt_id)
            if not isinstance(case, dict) or not run_dir.is_dir():
                continue
            report = _verify_run(
                run_dir, item, case, corpus, controls, manifest, freeze, output,
                imports, indexes, checks, global_ids,
            )
            if report is not None:
                reports.append(report)
            result = _safe_json(run_dir / "result.json", checks, run_dir.name + "/summary")
            if isinstance(result, dict) and isinstance(result.get("measurement"), dict) and isinstance(result.get("baseline"), dict):
                expected_rows.append(_summary_row(result))
    finally:
        indexes.close()
    _verify_summary(output, expected_rows, checks)

    # Keep the summary rows in exact plan order, and retain a concise per-run
    # account of accepted failed-answer/budget outcomes for audit consumers.
    expected_count = len(plan)
    complete_accounting = sum(1 for report in reports if report.get("complete"))
    complete_usage = sum(1 for report in reports if report.get("usage_complete"))
    if len(global_ids["config_hashes"]) != 1:
        _failure(checks, "batch", "config_drift", "canonical per-attempt evaluation configurations differ", fingerprints=sorted(global_ids["config_hashes"]))
    replayed = sum(1 for report in reports if report.get("replayed"))
    reconciled = sum(1 for report in reports if report.get("reconciled"))
    sessions = global_ids["sessions"]
    providers = global_ids["providers"]
    identity_facts = {
        "corpus_sha256": sha((corpus_root / "corpus.json").read_bytes()) if (corpus_root / "corpus.json").is_file() else None,
        "controls_sha256": sha((corpus_root / "comparison-controls.json").read_bytes()) if (corpus_root / "comparison-controls.json").is_file() else None,
        "run_identity_sha256": sha(wire_value(sorted((r.get("task_id"), r.get("arm"), r.get("repetition"), r.get("attempt_id")) for r in reports))),
        "session_ids_sha256": sha(wire_value(sorted(sessions))),
        "provider_thread_ids_sha256": sha(wire_value(sorted(providers))),
        "delivery_attempt_ids_sha256": sha(wire_value(sorted(global_ids["delivery_attempts"]))),
    }
    errata = _metadata_errata(repo, freeze)
    passed = (
        not checks
        and len(reports) == expected_count == EXPECTED_ATTEMPTS
        and len(sessions) == EXPECTED_ATTEMPTS
        and len(providers) == EXPECTED_ATTEMPTS
        and replayed == EXPECTED_ATTEMPTS
        and reconciled == EXPECTED_ATTEMPTS
        and complete_accounting == EXPECTED_ATTEMPTS
        and complete_usage == EXPECTED_ATTEMPTS
    )
    transport_count = 0
    transport_count_path = output / str(manifest.get("transport_proof_file", "transport-verification.json"))
    transport_count_value = _safe_json(transport_count_path, [], "transport-count")
    if isinstance(transport_count_value, dict) and isinstance(transport_count_value.get("modes"), list):
        transport_count = len(transport_count_value["modes"])
    result = {
        "schema_version": 1,
        "passed": passed,
        "verification_status": "passed" if passed else "failed",
        "output": str(output),
        "corpus_root": str(corpus_root),
        "comparison": EXPECTED_COMPARISON,
        "planned_count": expected_count,
        "recorded_count": len(reports),
        "unique_identity_count": len({(r.get("task_id"), r.get("arm"), r.get("repetition")) for r in reports}),
        "unique_session_count": len(sessions),
        "unique_provider_thread_count": len(providers),
        "unique_delivery_attempt_count": len(global_ids["delivery_attempts"]),
        "replayed_count": replayed,
        "reconciled_count": reconciled,
        "complete_accounting_count": complete_accounting,
        "complete_usage_count": complete_usage,
        "transport_modes": transport_count,
        "expansion_transport_modes": 1,
        "canonical_tool_schemas_sha256": manifest.get("canonical_tool_schemas_sha256"),
        "canonical_config_fingerprint_count": len(global_ids["config_hashes"]),
        "identity_hash_facts": identity_facts,
        "freeze_provenance": {key: freeze.get(key) for key in ("freeze_commit", "carrier_commit", "current_commit", "candidate_source_tree", "current_source_tree", "freeze_json_sha256", "candidate_diff_sha256")},
        "metadata_errata": errata,
        "provenance_errata": provenance_errata,
        "runs": reports,
        "failures": checks,
        "meaning": "Independent A/B artifact integrity verification. Failed answers and hard-budget outcomes remain valid measured outcomes; source, prompt, configuration, identity, transport, snapshot, accounting, usage, replay, measurement, and frozen-file violations fail integrity.",
    }
    target = report_path.resolve() if report_path is not None else Path("/tmp/loci-existing-comparison-verification.json")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True, help="comparison output directory")
    parser.add_argument("--corpus-root", type=Path, required=True, help="frozen v3 corpus directory")
    parser.add_argument("--report", type=Path, required=True, help="JSON verification report path")
    args = parser.parse_args()
    try:
        result = verify(args.output, args.corpus_root, args.report)
    except Exception as exc:
        blocked = {
            "schema_version": 1,
            "passed": False,
            "verification_status": "blocked",
            "output": str(args.output.resolve()),
            "corpus_root": str(args.corpus_root.resolve()),
            "planned_count": EXPECTED_ATTEMPTS,
            "recorded_count": 0,
            "failures": [{"scope": "verifier", "category": "blocked", "message": f"{type(exc).__name__}: {exc}"}],
        }
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(blocked, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(blocked, indent=2))
        return 2
    print(json.dumps({key: result.get(key) for key in (
        "passed", "verification_status", "planned_count", "recorded_count", "replayed_count",
        "reconciled_count", "complete_accounting_count", "complete_usage_count",
    )}, indent=2))
    return 0 if result.get("passed") else 1


if __name__ == "__main__":
    raise SystemExit(main())
