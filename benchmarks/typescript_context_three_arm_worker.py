"""Run exactly one frozen ABC attempt in a pinned engine subprocess.

The parent runner owns the ABC freeze, schedule, transport proofs, and retry
policy.  This module owns one attempt: it validates the selected source tree,
loads the frozen corpus controls, and delegates the lifecycle to
``typescript_context_compare._run_attempt``.  Keeping that lifecycle shared is
what preserves failure retention, request auditing, event capture, budgets,
measurement, and snapshot checks across the staged and ABC runners.
"""

from __future__ import annotations

import argparse
import copy
import json
import os
from pathlib import Path
import subprocess
from typing import Any

from benchmarks import typescript_context_compare as compare


COMMON_ROOT = Path(__file__).resolve().parents[1]
TOOLS_MODULE = "benchmarks.typescript_context_three_arm_tools"

_ARM_NAMES = frozenset({"A", "B", "C"})

_REQUIRED_SPEC_KEYS = frozenset({
    "corpus_root", "output", "catalog", "engine_src", "engine", "plan",
    "expected_schema_hash", "freeze",
})


def _is_hex(value: Any, length: int) -> bool:
    return (isinstance(value, str) and len(value) == length
            and all(character in "0123456789abcdefABCDEF" for character in value))


def _absolute_path(spec: dict[str, Any], key: str, *, directory: bool = False,
                   file: bool = False) -> Path:
    value = spec.get(key)
    if not isinstance(value, str) or not Path(value).is_absolute():
        raise ValueError(f"worker spec {key} must be an absolute path")
    path = Path(value).resolve()
    if directory and not path.is_dir():
        raise ValueError(f"worker spec {key} is not a directory: {path}")
    if file and not path.is_file():
        raise ValueError(f"worker spec {key} is not a file: {path}")
    return path


def _package_root(engine_src: Path) -> Path:
    """Resolve either a ``.../src`` path or its checkout root."""

    source = engine_src.resolve()
    if (source / "loci").is_dir():
        return source
    if (source / "src" / "loci").is_dir():
        return source / "src"
    raise ValueError(f"pinned engine source has no loci package: {source}")


def _validate_engine_source(engine_src: Path, engine: dict[str, Any], arm: str) -> Path:
    """Validate the declared pin and every source blob before indexing."""

    if not isinstance(engine, dict):
        raise ValueError("worker engine metadata must be an object")
    if arm not in _ARM_NAMES:
        raise ValueError(f"unsupported worker arm: {arm}")
    if engine.get("arm") != arm:
        raise ValueError("worker engine arm differs from the attempt arm")
    for field in ("commit", "source_tree"):
        if not _is_hex(engine.get(field), 40):
            raise ValueError(f"worker engine {field} must be a 40-character git id")
    if type(engine.get("extractor_version")) is not int:
        raise ValueError("worker engine extractor_version must be an integer")

    source = _package_root(engine_src)
    # The parent owns source archive materialization and exposes the canonical
    # file inventory/checker.  Reuse it here so a worker cannot silently drift
    # from the exact archive that was frozen for the attempt.
    try:
        from benchmarks.typescript_context_three_arm import source_identity, verify_engine

        identity = source_identity(arm)
        if any(identity.get(field) != engine.get(field)
               for field in ("arm", "commit", "source_tree", "extractor_version")):
            raise ValueError(f"worker engine metadata does not match frozen {arm} source")
        verify_engine(identity, source)
    except (OSError, subprocess.CalledProcessError) as exc:
        raise ValueError(f"worker engine source is unavailable: {source}") from exc
    return source


def _validate_spec(spec: dict[str, Any]) -> tuple[dict[str, Any], Path, dict[str, Any], Path, Path, Path]:
    if not isinstance(spec, dict):
        raise ValueError("worker spec must be an object")
    missing = sorted(_REQUIRED_SPEC_KEYS - set(spec))
    if missing:
        raise ValueError("worker spec is missing: " + ", ".join(missing))
    corpus_root = _absolute_path(spec, "corpus_root", directory=True)
    output = _absolute_path(spec, "output", directory=True)
    catalog = _absolute_path(spec, "catalog", file=True)
    engine_src = _absolute_path(spec, "engine_src", directory=True)
    freeze = spec["freeze"]
    if not isinstance(freeze, dict):
        raise ValueError("worker spec freeze must be an object")
    expected_schema_hash = spec["expected_schema_hash"]
    if not _is_hex(expected_schema_hash, 64):
        raise ValueError("worker expected_schema_hash must be a SHA-256 hex digest")

    plan = spec["plan"]
    if not isinstance(plan, dict):
        raise ValueError("worker plan must be an object")
    for field in ("attempt_id", "case_id", "snapshot", "arm"):
        if not isinstance(plan.get(field), str) or not plan[field]:
            raise ValueError(f"worker plan {field} must be a non-empty string")
    if plan["arm"] not in _ARM_NAMES:
        raise ValueError("worker plan arm must be A, B, or C")
    if type(plan.get("repetition")) is not int or plan["repetition"] not in {1, 2, 3}:
        raise ValueError("worker plan repetition must be 1, 2, or 3")
    expected_attempt = f"{plan['case_id']}-r{plan['repetition']}-{plan['arm']}"
    if plan["attempt_id"] != expected_attempt:
        raise ValueError("worker plan attempt_id does not match its case, repetition, and arm")

    engine = spec["engine"]
    if not isinstance(engine, dict):
        raise ValueError("worker engine must be an object")
    if engine.get("arm") != plan["arm"]:
        raise ValueError("worker engine and plan arms differ")
    return spec, engine_src, engine, corpus_root, output, catalog


def _runtime_for_engine(engine_src: Path, engine: dict[str, Any]) -> tuple[Any, Any, dict[str, Any]]:
    """Assert that this fresh worker already imported the selected engine."""

    import loci
    from loci import service
    from loci.storage.index_store import EXTRACTOR_VERSION

    source = _package_root(engine_src)
    loci_file = Path(getattr(loci, "__file__", "")).resolve()
    service_file = Path(getattr(service, "__file__", "")).resolve()
    if not loci_file.is_relative_to(source) or not service_file.is_relative_to(source):
        raise ValueError("worker imported loci/service outside the pinned engine source")
    if EXTRACTOR_VERSION != engine["extractor_version"]:
        raise ValueError("worker runtime extractor version differs from the pinned engine")
    runtime = {
        "loci_file": str(loci_file),
        "service_file": str(service_file),
        "loci_version": getattr(loci, "__version__", None),
        "extractor_version": EXTRACTOR_VERSION,
    }
    return loci, service, runtime


def _source_provenance(engine: dict[str, Any], freeze: dict[str, Any]) -> dict[str, Any]:
    """Return compact selected-engine and overall-freeze provenance."""

    selected = {key: engine.get(key) for key in
                ("arm", "commit", "source_tree", "extractor_version")}
    return {
        "engine": selected,
        "freeze_commit": freeze.get("freeze_commit"),
        "freeze_json_sha256": freeze.get("freeze_json_sha256"),
        "carrier_commit": freeze.get("carrier_commit", freeze.get("current_commit")),
        "source_scope": "assigned pinned engine; fixed v3 auto-get comparison",
    }


def _source_provenance_callback(engine: dict[str, Any], freeze: dict[str, Any]):
    source = _source_provenance(engine, freeze)

    def wrapped(_controls: dict[str, Any], _declared_freeze: dict[str, Any]) -> dict[str, Any]:
        return copy.deepcopy(source)

    return wrapped


def _settings_for_engine(base_settings, engine_src: Path):
    source = _package_root(engine_src)
    pythonpath = os.pathsep.join((str(source), str(COMMON_ROOT.resolve())))

    def settings(run_file: Path, catalog: Path, store: Path) -> dict[str, Any]:
        config = dict(base_settings(run_file, catalog, store))
        environment = dict(config.get("mcp_servers.evaluation.env", {}))
        environment["PYTHONPATH"] = pythonpath
        environment["PYTHONDONTWRITEBYTECODE"] = "1"
        config["mcp_servers.evaluation.env"] = environment
        return config

    return settings


def run_worker(spec: dict[str, Any]) -> dict[str, Any]:
    """Run one ABC attempt and return the saved v3 artifact."""

    spec, engine_src, engine, corpus_root, output, catalog = _validate_spec(spec)
    plan = spec["plan"]
    package_root = _validate_engine_source(engine_src, engine, plan["arm"])

    # Corpus loading is intentionally per-attempt only.  The parent owns the
    # 153-attempt schedule and overall freeze; this worker accepts one plan.
    from benchmarks.typescript_context_corpus import (
        _isolated_store,
        load_controls,
        load_corpus,
        materialize_snapshot,
    )

    corpus = load_corpus(corpus_root)
    controls = load_controls(corpus)
    matching_cases = [case for case in corpus["cases"] if case["id"] == plan["case_id"]]
    if len(matching_cases) != 1:
        raise ValueError(f"worker plan case is not in the frozen corpus: {plan['case_id']}")
    case = matching_cases[0]
    if case["snapshot"] != plan["snapshot"]:
        raise ValueError("worker plan snapshot differs from the corpus case")

    _loci, service, runtime = _runtime_for_engine(package_root, engine)
    from benchmarks.typescript_context_baseline_v3 import (
        child_environment,
        execute,
        inspect_request,
        launch_args,
        save,
        settings as baseline_settings,
    )
    from benchmarks.typescript_context_three_arm_tools import measure

    selected_settings = _settings_for_engine(baseline_settings, package_root)
    old_arm_modules = compare.ARM_MODULES
    old_source_provenance = compare._source_provenance
    compare.ARM_MODULES = {arm: TOOLS_MODULE for arm in ("A", "B", "C")}
    compare._source_provenance = _source_provenance_callback(engine, spec["freeze"])
    try:
        artifact = compare._run_attempt(
            corpus=corpus,
            controls=controls,
            plan=plan,
            output=output,
            catalog=catalog,
            expected_schema_hash=spec["expected_schema_hash"],
            freeze=spec["freeze"],
            inspect_request=inspect_request,
            settings=selected_settings,
            launch_args=launch_args,
            child_environment=child_environment,
            execute=execute,
            save=save,
            materialize_snapshot=materialize_snapshot,
            isolated_store=_isolated_store,
            service=service,
            measure=measure,
        )
    finally:
        # These globals are the only scoped compare changes.  Restoring the
        # original object and function matters when tests call run_worker
        # repeatedly in one interpreter rather than via fresh subprocesses.
        compare.ARM_MODULES = old_arm_modules
        compare._source_provenance = old_source_provenance

    if not isinstance(artifact, dict):
        raise ValueError("worker attempt did not return an artifact object")
    if artifact.get("attempt_id") != plan["attempt_id"] or artifact.get("arm") != plan["arm"]:
        raise ValueError("worker result identity differs from its plan")

    provenance = artifact.setdefault("provenance", {})
    provenance["engine_runtime"] = runtime
    provenance["source"] = _source_provenance(engine, spec["freeze"])

    destination = output / plan["attempt_id"]
    destination.mkdir(parents=True, exist_ok=True)
    save(destination / "provenance.json", provenance)
    save(destination / "result.json", artifact)
    return artifact


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--spec", type=Path, required=True)
    args = parser.parse_args()
    try:
        spec = json.loads(args.spec.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"invalid worker spec: {args.spec}") from exc
    artifact = run_worker(spec)
    print(json.dumps({
        "output": str(Path(spec["output"]).resolve()),
        "attempt_id": artifact["attempt_id"],
        "arm": artifact["arm"],
        "measurement_complete": artifact.get("measurement", {}).get("measurement_complete"),
    }, ensure_ascii=False, separators=(",", ":")), flush=True)


__all__ = [
    "TOOLS_MODULE",
    "run_worker",
]


if __name__ == "__main__":
    main()
