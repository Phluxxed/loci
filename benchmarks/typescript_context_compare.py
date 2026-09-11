"""Run a fresh, serial A/B comparison under the frozen v3 observation protocol.

The runner owns scheduling and provenance only.  Retrieval measurements are
produced by the existing v3 ``measure`` function and are left for the report
and independent replay tools to aggregate.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import tempfile
import time
import uuid
from pathlib import Path, PurePosixPath
from typing import Any, Callable

from benchmarks.typescript_context_baseline import ROOT, command, sha
from benchmarks.typescript_context_adapter import wire


DEFAULT_CORPUS_ROOT = ROOT / "benchmarks" / "corpora" / "typescript-context-v3"
DEFAULT_FREEZE = ROOT / "benchmarks" / "comparisons" / "typescript-context-existing-v1" / "freeze.json"

# A/B is a staged block in the v3 controls.  Keep the explicit order here so
# an accidental later addition of C cannot silently change a matched run.
AB_ARM_ORDERS: tuple[tuple[str, str], ...] = (("A", "B"), ("B", "A"), ("A", "B"))
ARM_MODULES = {
    # One server implementation is launched for both arms.  Its run identity
    # selects the exact inherited A path or bounded B expansion dispatch.
    "A": "benchmarks.typescript_context_expansion_tools",
    "B": "benchmarks.typescript_context_expansion_tools",
}
EXPECTED_RUNS = 17 * 3 * 2
MODEL = "gpt-5.6-luna"
REASONING_EFFORT = "high"
TRANSPORT_MODE_IDS = frozenset({
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
})
TRANSPORT_PROOF_FILE = "transport-verification.json"
EXPANSION_TRANSPORT_PROOF_FILE = "expansion-transport-verification.json"


def _wire(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), allow_nan=False)


def _save(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
                    encoding="utf-8")


def _safe_relative(value: str) -> PurePosixPath:
    path = PurePosixPath(value)
    if not value or path.is_absolute() or ".." in path.parts or str(path) != value:
        raise ValueError(f"unsafe frozen relative path: {value!r}")
    return path


def attempt_id(case_id: str, repetition: int, arm: str) -> str:
    """Return the immutable result key for one scheduled attempt."""

    if not case_id or type(repetition) is not int or repetition not in {1, 2, 3}:
        raise ValueError("invalid comparison attempt identity")
    if arm not in {"A", "B"}:
        raise ValueError("A/B comparison requires arm A or B")
    return f"{case_id}-r{repetition}-{arm}"


def planned_attempts(corpus: dict[str, Any], controls: dict[str, Any]) -> list[dict[str, Any]]:
    """Expand the frozen A/B block into its serial, exact attempt order."""

    case_ids = controls.get("case_ids")
    if not isinstance(case_ids, list) or case_ids != [case["id"] for case in corpus.get("cases", [])]:
        raise ValueError("controls and corpus case order differ")
    if len(case_ids) != 17:
        raise ValueError("the matched v3 comparison requires exactly 17 cases")
    if set(controls.get("arms", {})) != {"A", "B", "C"}:
        raise ValueError("the v3 controls must retain their A/B/C arm declarations")
    staged = controls.get("staged_schedule", {})
    if staged.get("AB_arm_orders") != [list(order) for order in AB_ARM_ORDERS]:
        raise ValueError("v3 staged A/B arm order changed")
    if staged.get("AB_runs") != EXPECTED_RUNS:
        raise ValueError("v3 staged A/B run count changed")

    snapshots = {case["id"]: case["snapshot"] for case in corpus["cases"]}
    planned: list[dict[str, Any]] = []
    # Match the baseline runner's case-major traversal; repetition determines
    # which arm order is used, while every case/repetition remains adjacent.
    for case_id in case_ids:
        for repetition, order in enumerate(AB_ARM_ORDERS, start=1):
            for arm in order:
                planned.append({
                    "attempt_id": attempt_id(case_id, repetition, arm),
                    "case_id": case_id,
                    "snapshot": snapshots[case_id],
                    "repetition": repetition,
                    "arm": arm,
                })
    if len(planned) != EXPECTED_RUNS or len({item["attempt_id"] for item in planned}) != EXPECTED_RUNS:
        raise ValueError("invalid A/B comparison schedule")
    return planned


def _git_oid(value: Any, field: str) -> str:
    """Read one exact SHA-1 commit/tree object identifier from the freeze."""

    if (not isinstance(value, str) or len(value) != 40
            or any(character not in "0123456789abcdefABCDEF" for character in value)):
        raise ValueError(f"freeze field {field} must be a 40-character git object id")
    return value


def _git_blob(commit: str, path: str) -> bytes:
    try:
        result = subprocess.run(
            ["git", "show", f"{commit}:{path}"],
            cwd=ROOT,
            capture_output=True,
            check=True,
        )
    except subprocess.CalledProcessError as exc:
        raise ValueError(f"git object does not contain frozen file: {path}") from exc
    return result.stdout


def _frozen_file_map(mapping: Any, base: Path, label: str, *, git_commit: str | None = None) -> dict[str, str]:
    if not isinstance(mapping, dict) or not mapping:
        raise ValueError(f"freeze {label} must be a non-empty path/hash map")
    checked: dict[str, str] = {}
    base = base.resolve()
    for name, expected in mapping.items():
        if not isinstance(name, str) or not isinstance(expected, str) or len(expected) != 64:
            raise ValueError(f"invalid {label} fingerprint entry")
        relative = _safe_relative(name)
        path = (base / Path(*relative.parts)).resolve()
        # A comparison freeze may use repo-relative corpus paths.  Accept that
        # spelling while still requiring the resolved file to remain in scope.
        if not path.is_relative_to(base) or not path.is_file():
            repo_path = (ROOT / Path(*relative.parts)).resolve()
            if label == "corpus_files" and repo_path.is_file():
                path = repo_path
            else:
                raise ValueError(f"frozen {label} file is missing: {name}")
        if sha(path.read_bytes()) != expected:
            raise ValueError(f"frozen {label} hash mismatch: {name}")
        if git_commit is not None:
            try:
                repo_path = path.relative_to(ROOT).as_posix()
            except ValueError as exc:
                raise ValueError(f"frozen {label} file is outside the repository: {name}") from exc
            if sha(_git_blob(git_commit, repo_path)) != expected:
                raise ValueError(f"git {git_commit} {label} hash mismatch: {name}")
        checked[name] = expected
    return checked


def _git_diff_sha(baseline_commit: str) -> str:
    proc = subprocess.run(
        ["git", "diff", "--binary", f"{baseline_commit}..HEAD", "--", "src"],
        cwd=ROOT,
        capture_output=True,
        check=True,
    )
    return sha(proc.stdout)


def validate_freeze(corpus: dict[str, Any], controls: dict[str, Any], freeze_path: Path) -> dict[str, Any]:
    """Validate the comparison freeze, source tree and all listed harness files."""

    freeze_path = Path(freeze_path).resolve()
    if not freeze_path.is_file():
        raise ValueError(f"comparison freeze does not exist: {freeze_path}")
    freeze = json.loads(freeze_path.read_text(encoding="utf-8"))
    freeze_version = freeze.get("version")
    if not isinstance(freeze_version, str) or not freeze_version.startswith("typescript-context-existing-v1"):
        raise ValueError("unsupported comparison freeze version")
    if freeze.get("candidate_source_tree") is None or freeze.get("freeze_commit") is None:
        raise ValueError("comparison freeze must pin candidate_source_tree and freeze_commit")

    freeze_commit = _git_oid(freeze["freeze_commit"], "freeze_commit")
    candidate_tree = _git_oid(freeze["candidate_source_tree"], "candidate_source_tree")
    corpus_root = Path(corpus["_root"]).resolve()
    # The freeze commit is the published carrier of the code/corpus snapshot;
    # freeze.json itself is committed by a descendant so it cannot hash itself.
    try:
        subprocess.run(["git", "merge-base", "--is-ancestor", freeze_commit, "HEAD"],
                       cwd=ROOT, capture_output=True, check=True)
    except subprocess.CalledProcessError as exc:
        raise ValueError("freeze commit must be an ancestor of the current carrier commit") from exc
    current_commit = command(["git", "rev-parse", "HEAD"], cwd=ROOT)
    current_tree = command(["git", "rev-parse", "HEAD:src"], cwd=ROOT)
    freeze_tree = command(["git", "rev-parse", f"{freeze_commit}:src"], cwd=ROOT)
    if freeze_tree != candidate_tree or current_tree != candidate_tree:
        raise ValueError("candidate source tree differs from frozen/current source")

    _frozen_file_map(freeze.get("corpus_files"), corpus_root, "corpus_files", git_commit=freeze_commit)
    harness = _frozen_file_map(freeze.get("harness_files"), ROOT, "harness_files", git_commit=freeze_commit)
    comparison_files = None
    if "comparison_files" in freeze:
        comparison_files = _frozen_file_map(
            freeze.get("comparison_files"), ROOT, "comparison_files", git_commit=freeze_commit
        )
    compare_name = str(Path(__file__).resolve().relative_to(ROOT))
    if compare_name not in harness:
        raise ValueError("comparison freeze does not pin the comparison runner")
    from benchmarks.typescript_context_baseline_v3 import HARNESS_FILES as V3_HARNESS_FILES

    required_harness = {str(path.relative_to(ROOT)) for path in V3_HARNESS_FILES}
    required_harness.update({
        "benchmarks/typescript_context_expansion_tools.py",
        "benchmarks/typescript_context_expansion_transport.py",
        "benchmarks/typescript_context_compare_report.py",
        compare_name,
    })
    missing_harness = sorted(required_harness - set(harness))
    if missing_harness:
        raise ValueError("comparison freeze omits used harness files: " + ", ".join(missing_harness))

    baseline_commit = controls["baseline_engine"]["commit"]
    baseline_tree = command(["git", "rev-parse", f"{baseline_commit}:src"], cwd=ROOT)
    if baseline_tree != controls["baseline_source_tree"]:
        raise ValueError("v3 controls baseline source tree no longer resolves to its commit")

    paths = list(harness) + list(comparison_files or {}) + ["src"]
    if command(["git", "status", "--porcelain", "--", *paths], cwd=ROOT):
        raise ValueError("frozen harness or production source has uncommitted changes")
    if corpus.get("version") != "typescript-context-v3":
        raise ValueError("typescript-context-v3 corpus required")
    if controls.get("corpus_version") != corpus["version"]:
        raise ValueError("controls/corpus version mismatch")
    if controls.get("corpus_sha256") != sha((corpus_root / "corpus.json").read_bytes()):
        raise ValueError("controls corpus hash differs from corpus manifest")
    candidate_diff_sha256 = _git_diff_sha(baseline_commit)
    frozen_candidate_diff = freeze.get("candidate_diff_sha256")
    if frozen_candidate_diff is not None:
        if (not isinstance(frozen_candidate_diff, str) or len(frozen_candidate_diff) != 64
                or frozen_candidate_diff != candidate_diff_sha256):
            raise ValueError("candidate source diff differs from comparison freeze")
    return {
        "version": freeze_version,
        "path": str(freeze_path),
        "freeze_commit": freeze_commit,
        "carrier_commit": current_commit,
        "candidate_source_tree": candidate_tree,
        "baseline_commit": baseline_commit,
        "baseline_source_tree": controls["baseline_source_tree"],
        "current_commit": current_commit,
        "current_source_tree": current_tree,
        "freeze_json_sha256": sha(freeze_path.read_bytes()),
        "candidate_diff_sha256": candidate_diff_sha256,
        "harness_files": harness,
        "corpus_files": freeze["corpus_files"],
        "comparison_files": comparison_files,
    }


def _validate_transport_proof(proof: dict[str, Any], corpus: dict[str, Any],
                              catalog: Path) -> str:
    """Validate one actual v3 proof and return its canonical schema hash."""

    root = Path(corpus["_root"])
    if (not isinstance(proof, dict) or proof.get("schema_version") != 3
            or proof.get("probe") != "typescript-context-v3-typed-transport"
            or proof.get("model") != MODEL
            or proof.get("reasoning_effort") != REASONING_EFFORT
            or proof.get("tool_count") != 16):
        raise ValueError("offline v3 transport proof has incompatible settings")
    if (proof.get("corpus_sha256") != sha((root / "corpus.json").read_bytes())
            or proof.get("controls_sha256") != sha((root / "comparison-controls.json").read_bytes())
            or proof.get("catalog_sha256") != sha(Path(catalog).read_bytes())):
        raise ValueError("offline v3 transport proof does not match corpus, controls, or catalog")
    script = ROOT / "benchmarks" / "typescript_context_transport_v3.py"
    if proof.get("script_sha256") != sha(script.read_bytes()):
        raise ValueError("offline v3 transport proof uses a different transport script")
    value = proof.get("canonical_tool_schemas_sha256")
    if not isinstance(value, str) or len(value) != 64:
        raise ValueError("offline v3 transport proof has no canonical schema hash")
    modes = proof.get("modes")
    if not isinstance(modes, list) or len(modes) != len(TRANSPORT_MODE_IDS):
        raise ValueError("offline v3 transport proof must contain all ten modes")
    mode_ids = {mode.get("mode") for mode in modes if isinstance(mode, dict)}
    if mode_ids != TRANSPORT_MODE_IDS:
        raise ValueError("offline v3 transport proof does not contain the fixed ten modes")
    if any((not isinstance(mode, dict)
            or mode.get("canonical_tool_schemas_sha256") != value
            or mode.get("output_verified") is not True
            or mode.get("request_count") != 2)
           for mode in modes):
        raise ValueError("offline v3 transport proof contains an unverified mode")
    return value


def _validate_expansion_transport_proof(proof: dict[str, Any], expected_schema_hash: str) -> None:
    """Validate the single offline B-arm expanded-get proof."""

    if (not isinstance(proof, dict)
            or proof.get("schema_version") != 1
            or proof.get("probe") != "typescript-context-expanded-get-transport"
            or proof.get("arm") != "B"
            or proof.get("case_id") != "imported_interface"
            or proof.get("model") != MODEL
            or proof.get("reasoning_effort") != REASONING_EFFORT
            or proof.get("canonical_tool_schemas_sha256") != expected_schema_hash):
        raise ValueError("expanded B transport proof has incompatible settings")
    observation = proof.get("observation")
    accounting = observation.get("observed_accounting") if isinstance(observation, dict) else None
    if (not isinstance(observation, dict)
            or observation.get("output_verified") is not True
            or observation.get("request_count") != 2
            or observation.get("adapter_attempts") != 1
            or observation.get("adapter_deliveries") != 1
            or not isinstance(accounting, dict)
            or accounting.get("complete") is not True
            or accounting.get("tool_call_count") != 1):
        raise ValueError("expanded B transport proof is incomplete")


def _validate_catalog(catalog: Path) -> dict[str, Any]:
    """Check that the supplied local catalog selects the frozen Luna slug."""

    try:
        value = json.loads(Path(catalog).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"invalid model catalog: {catalog}") from exc
    models = value.get("models") if isinstance(value, dict) else None
    if not isinstance(models, list) or not any(
            isinstance(model, dict) and model.get("slug") == MODEL for model in models):
        raise ValueError(f"model catalog does not contain frozen model {MODEL}")
    return value


def _retain_catalog(catalog: Path, output: Path, *, resume: bool) -> Path:
    """Pin the caller's fresh catalog bytes inside the comparison output."""

    if catalog is None:
        raise ValueError("an explicit fresh --catalog path is required")
    catalog = Path(catalog).resolve()
    if not catalog.is_file():
        raise ValueError(f"model catalog does not exist: {catalog}")
    source_bytes = catalog.read_bytes()
    _validate_catalog(catalog)
    retained = output / "model-catalog.json"

    if resume:
        if not output.is_dir():
            raise ValueError("--resume requires an existing comparison output directory")
        if not retained.is_file():
            raise ValueError("--resume requires the retained model-catalog.json")
        if retained.read_bytes() != source_bytes:
            raise ValueError("cannot resume across changed model catalog bytes")
    else:
        if output.exists() and not output.is_dir():
            raise ValueError(f"comparison output is not a directory: {output}")
        if output.exists():
            # A caller may stage a freshly prepared catalog before invoking the
            # runner.  No other prior batch artifacts may be reused or replaced.
            allowed = {"model-catalog.json", "model-catalog-provenance.json"}
            unexpected = sorted(path.name for path in output.iterdir() if path.name not in allowed)
            if unexpected:
                raise ValueError(f"comparison output already contains batch artifacts: {unexpected}")
            output.mkdir(parents=True, exist_ok=True)
        else:
            output.mkdir(parents=True)
        if retained.exists() and retained.read_bytes() != source_bytes:
            raise ValueError("staged model-catalog.json differs from supplied catalog")
        if not retained.exists():
            retained.write_bytes(source_bytes)

    if sha(retained.read_bytes()) != sha(source_bytes):
        raise ValueError("retained model catalog bytes changed during setup")
    _validate_catalog(retained)
    return retained


def _historical_schema_hash(corpus: dict[str, Any]) -> str:
    """Read the frozen v3 proof hash used as the comparison schema baseline."""

    proof_path = Path(corpus["_root"]) / "transport-verification.json"
    try:
        proof = json.loads(proof_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError("frozen v3 transport proof is unavailable") from exc
    value = proof.get("canonical_tool_schemas_sha256") if isinstance(proof, dict) else None
    if not isinstance(value, str) or len(value) != 64:
        raise ValueError("frozen v3 transport proof has no canonical schema hash")
    return value


def _source_provenance(controls: dict[str, Any], freeze: dict[str, Any]) -> dict[str, Any]:
    baseline_commit = controls["baseline_engine"]["commit"]
    return {
        "baseline_commit": baseline_commit,
        "baseline_source_tree": controls["baseline_source_tree"],
        "candidate_source_tree": freeze["candidate_source_tree"],
        "candidate_diff_sha256": freeze["candidate_diff_sha256"],
        "freeze_commit": freeze["freeze_commit"],
        "carrier_commit": freeze.get("carrier_commit", freeze["current_commit"]),
        "current_commit": freeze["current_commit"],
        "current_source_tree": freeze["current_source_tree"],
        "freeze_json_sha256": freeze.get("freeze_json_sha256"),
        "comparison_files": freeze.get("comparison_files"),
        "source_scope": "retrieval-only candidate; A uses the existing exact v3 path",
    }


def _module_for_arm(arm: str) -> str:
    try:
        return ARM_MODULES[arm]
    except KeyError as exc:
        raise ValueError(f"unsupported comparison arm: {arm}") from exc


def _initial_trace(corpus: dict[str, Any], run: dict[str, Any]) -> dict[str, Any]:
    from benchmarks.typescript_context_observed import ObservedTrace

    trace = ObservedTrace(corpus, run["case_id"], run["session_id"], run["arm"], run["repetition"])
    return {
        "schema_version": 3,
        "identity": trace.identity,
        "events": [],
        "failures": [],
        "attempts": 0,
        "deliveries": [],
    }


def _parse_events(stdout: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    events: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    for line_number, line in enumerate(stdout.splitlines(), start=1):
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError as exc:
            failures.append({"category": "subprocess_output", "line": line_number,
                             "message": str(exc), "text": line[:500]})
            continue
        if isinstance(value, dict):
            events.append(value)
        else:
            failures.append({"category": "subprocess_output", "line": line_number,
                             "message": "Codex JSONL item must be an object"})
    return events, failures


def _failure(category: str, message: str, **extra: Any) -> dict[str, Any]:
    return {"category": category, "message": str(message)[:1000], **extra}


def _fallback_artifact(corpus: dict[str, Any], raw_trace: dict[str, Any], *, elapsed: float,
                       exit_code: int, failures: list[dict[str, Any]]) -> dict[str, Any]:
    """Produce a replayable failed artifact when setup/measurement itself fails."""

    from benchmarks.typescript_context_observed import ObservedTrace

    identity = raw_trace["identity"]
    trace = ObservedTrace(corpus, identity["task_id"], identity["session_id"], identity["arm"], identity["repetition"])
    measurement = trace.report({}, outcome="tool_failure")
    baseline = {
        "end_to_end_seconds": elapsed,
        "actual_process_seconds": elapsed,
        "exit_code": exit_code,
        "provider_thread_id": None,
        "failures": failures,
        "tool_delivery_verified": False,
        "measurement_complete": False,
    }
    return {
        "schema_version": 3,
        "identity": identity,
        "events": [],
        "measurement": measurement,
        "baseline": baseline,
    }


def _run_attempt(
    *,
    corpus: dict[str, Any],
    controls: dict[str, Any],
    plan: dict[str, Any],
    output: Path,
    catalog: Path,
    expected_schema_hash: str,
    freeze: dict[str, Any],
    inspect_request: Callable[[Path, dict[str, Any], str, Path], dict[str, Any]],
    settings: Callable[[Path, Path, Path], dict[str, Any]],
    launch_args: Callable[[Path, dict[str, Any], str], list[str]],
    child_environment: Callable[[Path, bool], dict[str, str]],
    execute: Callable[[list[str], dict[str, str], float], tuple[int, str, str, float, bool]],
    save: Callable[[Path, Any], None],
    materialize_snapshot: Callable[[dict[str, Any], str, Path], None],
    isolated_store,
    service,
    measure: Callable[..., dict[str, Any]],
) -> dict[str, Any]:
    """Run exactly one scheduled attempt and retain failures in its result."""

    destination = output / plan["attempt_id"]
    destination.mkdir(parents=True, exist_ok=False)
    failures: list[dict[str, Any]] = []
    started = time.monotonic()
    index = None
    events: list[dict[str, Any]] = []
    code = 1
    timed_out = False
    stdout = ""
    stderr = ""

    with tempfile.TemporaryDirectory(prefix="loci-v3-compare-") as temporary:
        temp = Path(temporary)
        repo, store = temp / "snapshot", temp / "store"
        run = {
            "repo": str(repo.resolve()),
            "corpus_root": corpus["_root"],
            "case_id": plan["case_id"],
            "session_id": f"{plan['attempt_id']}-{uuid.uuid4()}",
            "arm": plan["arm"],
            "repetition": plan["repetition"],
            "trace_path": str(destination / "adapter-trace.json"),
            "attempt_id": plan["attempt_id"],
        }
        run_file = temp / "run.json"
        save(run_file, run)
        initial = _initial_trace(corpus, run)
        save(Path(run["trace_path"]), initial)
        save(destination / "run.json", run)
        save(destination / "initial-trace.json", initial)

        try:
            materialize_snapshot(corpus, plan["snapshot"], repo)
            index_started = time.monotonic()
            with isolated_store(store):
                service.index_repo(repo, incremental=False)
                index = service.get_store().load(repo.resolve())
            index_seconds = time.monotonic() - index_started
            if index is None:
                raise ValueError("fresh index was not persisted")
        except Exception as exc:
            failures.append(_failure("setup", exc))
            index_seconds = None

        prompt = controls["agent"]["common_prompt"] + next(
            case["prompt"] for case in corpus["cases"] if case["id"] == plan["case_id"]
        )
        config: dict[str, Any] = {}
        audit: dict[str, Any] = {}
        if not failures:
            try:
                config = settings(run_file, catalog, store)
                module = _module_for_arm(plan["arm"])
                config["mcp_servers.evaluation.args"] = ["-m", module, str(run_file)]
                audit = inspect_request(repo, config, prompt, temp / "inspection-runtime")
                if audit.get("canonical_tool_schemas_sha256") != expected_schema_hash:
                    raise ValueError("effective canonical tool schemas differ from offline v3 proof")
                save(destination / "request-audit.json", audit)
            except Exception as exc:
                failures.append(_failure("request_audit", exc, arm=plan["arm"]))
                save(destination / "request-audit-error.json", {"error": str(exc), "arm": plan["arm"]})
        provenance = {
            "attempt_id": plan["attempt_id"],
            "case_id": plan["case_id"],
            "snapshot": plan["snapshot"],
            "repetition": plan["repetition"],
            "arm": plan["arm"],
            "adapter_module": _module_for_arm(plan["arm"]),
            "model": MODEL,
            "reasoning_effort": REASONING_EFFORT,
            "corpus_sha256": sha((Path(corpus["_root"]) / "corpus.json").read_bytes()),
            "controls_sha256": sha((Path(corpus["_root"]) / "comparison-controls.json").read_bytes()),
            "catalog_sha256": sha(catalog.read_bytes()),
            "runner_sha256": sha(Path(__file__).read_bytes()),
            "source": _source_provenance(controls, freeze),
            "config": config,
            "config_sha256": sha(wire(config).encode("utf-8")) if config else None,
            "prompt_sha256": sha(prompt.encode("utf-8")),
            "index_seconds": index_seconds,
            "snapshot_files": corpus["snapshots"][plan["snapshot"]]["files"],
        }
        try:
            from loci.storage.index_store import EXTRACTOR_VERSION
            provenance["extractor_version"] = EXTRACTOR_VERSION
        except ImportError:
            provenance["extractor_version"] = None
        if audit:
            provenance["canonical_tool_schemas_sha256"] = audit["canonical_tool_schemas_sha256"]
        save(destination / "provenance.json", provenance)

        if not failures:
            try:
                code, stdout, stderr, elapsed, timed_out = execute(
                    launch_args(repo, config, prompt),
                    child_environment(temp / "agent-runtime", True),
                    controls["limits"]["max_end_to_end_seconds_per_run"],
                )
                events, parse_failures = _parse_events(stdout)
                failures.extend(parse_failures)
            except Exception as exc:
                failures.append(_failure("subprocess", exc, arm=plan["arm"]))
                elapsed = time.monotonic() - started
        else:
            elapsed = time.monotonic() - started

        (destination / "events.jsonl").write_text(stdout, encoding="utf-8")
        (destination / "stderr.txt").write_text(stderr, encoding="utf-8")
        save(destination / "events.json", events)
        trace_path = Path(run["trace_path"])
        try:
            raw_trace = json.loads(trace_path.read_text(encoding="utf-8"))
            if raw_trace.get("schema_version") != 3:
                raise ValueError("adapter trace is not schema v3")
        except Exception as exc:
            failures.append(_failure("trace", exc))
            raw_trace = initial
            save(destination / "invalid-trace.json", {"error": str(exc)})
        save(destination / "adapter-trace-copy.json", raw_trace)

        if repo.is_dir():
            try:
                actual = {str(path.relative_to(repo)): sha(path.read_bytes())
                          for path in repo.rglob("*") if path.is_file()}
                expected = corpus["snapshots"][plan["snapshot"]]["files"]
                if actual != expected:
                    failures.append(_failure("source_snapshot", "snapshot changed during attempt"))
            except Exception as exc:
                failures.append(_failure("source_snapshot", exc))

        try:
            artifact = measure(corpus, next(case for case in corpus["cases"] if case["id"] == plan["case_id"]),
                               run, events, elapsed, code, timed_out, index)
        except Exception as exc:
            failures.append(_failure("measurement", exc))
            artifact = _fallback_artifact(corpus, raw_trace, elapsed=elapsed, exit_code=code, failures=failures)
        baseline = artifact.setdefault("baseline", {})
        saved_failures = baseline.setdefault("failures", [])
        for failure in failures:
            if failure not in saved_failures:
                saved_failures.append(failure)
        if failures:
            # A runner/setup failure makes the attempt ineligible even if a
            # partial measurement happened to look superficially complete.
            measurement = artifact.get("measurement")
            if isinstance(measurement, dict):
                measurement["measurement_complete"] = False
                measurement["task_correct"] = False
            baseline["tool_delivery_verified"] = False
        baseline["arm"] = plan["arm"]
        baseline["attempt_id"] = plan["attempt_id"]
        artifact["attempt_id"] = plan["attempt_id"]
        artifact["arm"] = plan["arm"]
        artifact["provenance"] = provenance
        if failures:
            artifact["runner_failures"] = failures
        save(destination / "result.json", artifact)
        return artifact


def _manifest(corpus: dict[str, Any], controls: dict[str, Any], catalog: Path,
              freeze: dict[str, Any], expected_schema_hash: str, plan: list[dict[str, Any]],
              *, transport_proof_sha256: str | None = None,
              expansion_transport_proof_sha256: str | None = None) -> dict[str, Any]:
    root = Path(corpus["_root"])
    if transport_proof_sha256 is None:
        # Kept as a small convenience for model-free callers of this helper.
        # Actual batches always pass the freshly generated output proof hash.
        transport_proof = root / "transport-verification.json"
        transport_proof_sha256 = sha(transport_proof.read_bytes())
    if expansion_transport_proof_sha256 is None:
        expansion_proof = root / EXPANSION_TRANSPORT_PROOF_FILE
        if expansion_proof.is_file():
            expansion_transport_proof_sha256 = sha(expansion_proof.read_bytes())
    return {
        "schema_version": 3,
        "comparison": "typescript-context-existing-v1",
        "measurement_status": "not_started",
        "planned_runs": len(plan),
        "schedule": {"repetitions": 3, "case_order": "corpus_order",
                      "arm_orders": [list(order) for order in AB_ARM_ORDERS],
                      "concurrency": 1},
        "corpus_root": str(root),
        "corpus_sha256": sha((root / "corpus.json").read_bytes()),
        "controls_sha256": sha((root / "comparison-controls.json").read_bytes()),
        "catalog_sha256": sha(catalog.read_bytes()),
        "catalog_file": "model-catalog.json",
        "runner_sha256": sha(Path(__file__).read_bytes()),
        "transport_proof_file": TRANSPORT_PROOF_FILE,
        "transport_proof_sha256": transport_proof_sha256,
        "transport_script_sha256": sha((ROOT / "benchmarks" / "typescript_context_transport_v3.py").read_bytes()),
        "expansion_transport_proof_file": EXPANSION_TRANSPORT_PROOF_FILE,
        "expansion_transport_proof_sha256": expansion_transport_proof_sha256,
        "expansion_transport_script_sha256": sha(
            (ROOT / "benchmarks" / "typescript_context_expansion_transport.py").read_bytes()
        ),
        "canonical_tool_schemas_sha256": expected_schema_hash,
        "freeze": freeze,
        "model": MODEL,
        "reasoning_effort": REASONING_EFFORT,
    }


def _summary_row(artifact: dict[str, Any]) -> dict[str, Any]:
    """Flatten one saved artifact in the same shape as the v3 baseline summary."""

    measurement = artifact.get("measurement") or {}
    baseline = artifact.get("baseline") or {}
    row = {**measurement, **baseline}
    row["attempt_id"] = artifact.get("attempt_id")
    row["arm"] = artifact.get("arm") or artifact.get("identity", {}).get("arm")
    row["directory"] = artifact.get("attempt_id")
    return row


def run_comparison(corpus: dict[str, Any], controls: dict[str, Any], catalog: Path,
                   output: Path, *, freeze_path: Path = DEFAULT_FREEZE,
                   resume: bool = False) -> dict[str, Any]:
    """Execute or resume the 102-attempt serial A/B comparison."""

    from benchmarks.typescript_context_baseline_v3 import (
        child_environment,
        execute,
        inspect_request,
        launch_args,
        save,
        settings,
    )
    # The expansion module delegates to frozen v3 observation accounting and
    # additionally normalizes B's proven type-context edges for the existing
    # relationship scorer.  Use it for both arms so A/B share one measurement
    # path and B edges are not silently discarded.
    from benchmarks.typescript_context_expansion_tools import measure
    from benchmarks.typescript_context_corpus import _isolated_store, materialize_snapshot
    from loci import service

    catalog = Path(catalog).resolve() if catalog is not None else None
    output = Path(output).resolve()
    plan = planned_attempts(corpus, controls)
    freeze = validate_freeze(corpus, controls, freeze_path)
    if resume:
        retained_catalog = _retain_catalog(catalog, output, resume=True)
        proof_path = output / "transport-verification.json"
        if not proof_path.is_file():
            raise ValueError("--resume requires the retained transport-verification.json")
        try:
            proof = json.loads(proof_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError("--resume requires a valid retained transport proof") from exc
        expected_schema_hash = _validate_transport_proof(proof, corpus, retained_catalog)
        if proof.get("controls_version") != controls.get("version"):
            raise ValueError("retained transport proof uses changed controls")
        if expected_schema_hash != _historical_schema_hash(corpus):
            raise ValueError("retained transport proof schema differs from frozen v3 proof")
        transport_proof_sha256 = sha(proof_path.read_bytes())
        expansion_proof_path = output / EXPANSION_TRANSPORT_PROOF_FILE
        if not expansion_proof_path.is_file():
            raise ValueError("--resume requires the retained expanded B transport proof")
        try:
            expansion_proof = json.loads(expansion_proof_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError("--resume requires a valid expanded B transport proof") from exc
        _validate_expansion_transport_proof(expansion_proof, expected_schema_hash)
        expansion_transport_proof_sha256 = sha(expansion_proof_path.read_bytes())
        manifest_path = output / "manifest.json"
        if not manifest_path.is_file():
            raise ValueError("--resume requires manifest.json")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        expected_manifest = _manifest(
            corpus, controls, retained_catalog, freeze, expected_schema_hash, plan,
            transport_proof_sha256=transport_proof_sha256,
            expansion_transport_proof_sha256=expansion_transport_proof_sha256,
        )
        for key in (
            "planned_runs", "schedule", "corpus_root", "corpus_sha256", "controls_sha256",
            "catalog_file", "catalog_sha256", "runner_sha256", "transport_proof_file",
            "transport_proof_sha256", "transport_script_sha256", "expansion_transport_proof_file",
            "expansion_transport_proof_sha256", "expansion_transport_script_sha256",
            "canonical_tool_schemas_sha256", "freeze", "model", "reasoning_effort",
        ):
            if manifest.get(key) != expected_manifest[key]:
                raise ValueError(f"cannot resume across changed {key}")
    else:
        retained_catalog = _retain_catalog(catalog, output, resume=False)
        proof_path = output / "transport-verification.json"
        if proof_path.exists():
            raise ValueError("comparison output already contains transport verification")
        # Always generate a new proof against the exact catalog bytes retained
        # for this batch.  A historical v3 proof is only the schema reference.
        from benchmarks.typescript_context_transport_v3 import verify_transport

        proof = verify_transport(corpus, retained_catalog, proof_path)
        expected_schema_hash = _validate_transport_proof(proof, corpus, retained_catalog)
        if proof.get("controls_version") != controls.get("version"):
            raise ValueError("fresh transport proof uses changed controls")
        if expected_schema_hash != _historical_schema_hash(corpus):
            raise ValueError("fresh transport proof schema differs from frozen v3 proof")
        transport_proof_sha256 = sha(proof_path.read_bytes())
        expansion_proof_path = output / EXPANSION_TRANSPORT_PROOF_FILE
        from benchmarks.typescript_context_expansion_transport import verify_transport as verify_expansion_transport

        expansion_proof = verify_expansion_transport(corpus, retained_catalog, expansion_proof_path)
        _validate_expansion_transport_proof(expansion_proof, expected_schema_hash)
        expansion_transport_proof_sha256 = sha(expansion_proof_path.read_bytes())
        manifest = _manifest(
            corpus, controls, retained_catalog, freeze, expected_schema_hash, plan,
            transport_proof_sha256=transport_proof_sha256,
            expansion_transport_proof_sha256=expansion_transport_proof_sha256,
        )
        save(output / "manifest.json", manifest)
        save(output / "plan.json", {"schema_version": 3, "attempts": plan})

    # Environment and CLI checks are metadata gates, shared with v3 baseline.
    from benchmarks.typescript_context_baseline import environment

    observed_environment = environment(controls)
    cli_version = command(["codex", "--version"], cwd=ROOT)
    if cli_version != "codex-cli 0.154.0":
        raise ValueError("Codex CLI changed from the frozen 0.154.0 contract")
    environment_identity = {
        "cli_version": cli_version,
        "freeze_commit": freeze["freeze_commit"],
        "carrier_commit": freeze["carrier_commit"],
        "candidate_source_tree": freeze["candidate_source_tree"],
        "current_source_tree": freeze["current_source_tree"],
        "freeze_json_sha256": freeze["freeze_json_sha256"],
        "comparison_files": freeze.get("comparison_files"),
        "catalog_file": "model-catalog.json",
        "catalog_sha256": sha(retained_catalog.read_bytes()),
        "transport_proof_file": TRANSPORT_PROOF_FILE,
        "transport_proof_sha256": transport_proof_sha256,
        "transport_script_sha256": sha((ROOT / "benchmarks" / "typescript_context_transport_v3.py").read_bytes()),
        "expansion_transport_proof_file": EXPANSION_TRANSPORT_PROOF_FILE,
        "expansion_transport_proof_sha256": expansion_transport_proof_sha256,
        "expansion_transport_script_sha256": sha(
            (ROOT / "benchmarks" / "typescript_context_expansion_transport.py").read_bytes()
        ),
        "canonical_tool_schemas_sha256": expected_schema_hash,
    }
    if not resume:
        save(output / "environment.json", {
            **observed_environment,
            **environment_identity,
            "harness_files": freeze["harness_files"],
        })
    else:
        environment_path = output / "environment.json"
        if not environment_path.is_file():
            raise ValueError("--resume requires environment.json")
        previous_environment = json.loads(environment_path.read_text(encoding="utf-8"))
        for key, value in {**observed_environment, **environment_identity,
                           "harness_files": freeze["harness_files"]}.items():
            if previous_environment.get(key) != value:
                raise ValueError(f"cannot resume across changed environment field: {key}")

    result_artifacts: list[dict[str, Any]] = []
    for item in plan:
        destination = output / item["attempt_id"]
        result_path = destination / "result.json"
        print(_wire({"starting": item["attempt_id"], "case_id": item["case_id"],
                     "repetition": item["repetition"], "arm": item["arm"],
                     "resumed": result_path.is_file()}), flush=True)
        if result_path.is_file():
            if not resume:
                raise ValueError(f"attempt already exists: {item['attempt_id']}")
            saved_result = json.loads(result_path.read_text(encoding="utf-8"))
            if saved_result.get("attempt_id") != item["attempt_id"] or saved_result.get("arm") != item["arm"]:
                raise ValueError(f"saved attempt identity mismatch: {item['attempt_id']}")
            result_artifacts.append(saved_result)
            measurement = saved_result.get("measurement") or {}
            baseline = saved_result.get("baseline") or {}
            print(_wire({
                "completed": item["attempt_id"],
                "correct": measurement.get("answer_correct"),
                "full_pass": measurement.get("task_correct"),
                "outcome": measurement.get("outcome"),
                "tool_calls": measurement.get("read_count"),
                "accounting_complete": measurement.get("measurement_complete"),
                "tool_delivery_verified": baseline.get("tool_delivery_verified"),
                "seconds": baseline.get("end_to_end_seconds"),
                "resumed": True,
            }), flush=True)
            continue
        if resume and destination.exists():
            raise ValueError(f"partial attempt cannot be resumed without overwriting: {item['attempt_id']}")
        result = _run_attempt(
            corpus=corpus,
            controls=controls,
            plan=item,
            output=output,
            catalog=retained_catalog,
            expected_schema_hash=expected_schema_hash,
            freeze=freeze,
            inspect_request=inspect_request,
            settings=settings,
            launch_args=launch_args,
            child_environment=child_environment,
            execute=execute,
            save=save,
            materialize_snapshot=materialize_snapshot,
            isolated_store=_isolated_store,
            service=service,
            measure=measure,
        )
        result_artifacts.append(result)
        measurement = result.get("measurement") or {}
        baseline = result.get("baseline") or {}
        print(_wire({
            "completed": item["attempt_id"],
            "correct": measurement.get("answer_correct"),
            "full_pass": measurement.get("task_correct"),
            "outcome": measurement.get("outcome"),
            "tool_calls": measurement.get("read_count"),
            "accounting_complete": measurement.get("measurement_complete"),
            "tool_delivery_verified": baseline.get("tool_delivery_verified"),
            "seconds": baseline.get("end_to_end_seconds"),
            "resumed": False,
        }), flush=True)

    summary = {
        "schema_version": 3,
        "comparison": "typescript-context-existing-v1",
        "planned_runs": len(plan),
        "recorded_runs": len(result_artifacts),
        "complete_batch": len(result_artifacts) == len(plan),
        "schedule": {"repetitions": 3, "case_order": "corpus_order",
                      "arm_orders": [list(order) for order in AB_ARM_ORDERS],
                      "concurrency": 1},
        "results": [_summary_row(artifact) for artifact in result_artifacts],
        "meaning": "Matched A/B evidence; report and independent replay own aggregation and gates.",
    }
    save(output / "summary.json", summary)
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus-root", type=Path, default=DEFAULT_CORPUS_ROOT)
    parser.add_argument("--catalog", type=Path, required=True,
                        help="fresh model catalog prepared for this batch")
    parser.add_argument("--freeze", type=Path, default=DEFAULT_FREEZE)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--resume", action="store_true",
                        help="continue only result directories that are entirely missing")
    args = parser.parse_args()

    from benchmarks.typescript_context_corpus import load_controls, load_corpus

    corpus = load_corpus(args.corpus_root)
    controls = load_controls(corpus)
    summary = run_comparison(corpus, controls, args.catalog, args.output,
                             freeze_path=args.freeze, resume=args.resume)
    print(json.dumps({"output": str(Path(args.output).resolve()),
                      "planned_runs": summary["planned_runs"],
                      "recorded_runs": summary["recorded_runs"],
                      "complete_batch": summary["complete_batch"]}))


# Keep the conventional name used by the v3 baseline verifier while exposing
# the more descriptive public function above.
verify_freeze = validate_freeze

__all__ = [
    "AB_ARM_ORDERS",
    "ARM_MODULES",
    "EXPECTED_RUNS",
    "TRANSPORT_MODE_IDS",
    "TRANSPORT_PROOF_FILE",
    "EXPANSION_TRANSPORT_PROOF_FILE",
    "attempt_id",
    "planned_attempts",
    "run_comparison",
    "validate_freeze",
    "verify_freeze",
]


if __name__ == "__main__":
    main()
