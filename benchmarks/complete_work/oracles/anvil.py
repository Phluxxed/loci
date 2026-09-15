"""Independent behavioral oracle for the Anvil creation-evidence episode.

The evaluator deliberately keeps its TypeScript fixture outside a measured
checkout.  It exercises the candidate's exported Manifest seams and an
ephemeral loopback server; an agent's added tests are neither loaded nor used
as an oracle.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Mapping, Sequence

SCHEMA_VERSION = 1
EPISODE_ID = "anvil-creation-evidence"
SOURCE_COMMIT = "53bf29e60cece2335aa39fe301935a07e8e8d4e4"
SOURCE_FILE_COUNT = 638
DEFAULT_SOURCE_ROOT = Path("/tmp/anvil-source-tasks-20260914/t21")
ROOT = Path(__file__).resolve().parents[3]
SOURCE_MANIFEST = ROOT / "benchmarks/comparisons/ordinary-adoption-v1/cases.json"
FIXTURE = Path(__file__).with_name("anvil_creation_evidence_fixture.mjs")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _check(identifier: str, passed: bool, detail: str) -> dict[str, Any]:
    return {"id": identifier, "passed": passed, "detail": detail}


def _safe_error(error: BaseException | str) -> str:
    """Keep reports useful without returning target paths or subprocess dumps."""
    text = str(error).replace("\n", " ").strip()
    return text[:500] or type(error).__name__


def source_manifest() -> Mapping[str, Any]:
    data = json.loads(SOURCE_MANIFEST.read_text(encoding="utf-8"))
    if data.get("source_commit") != SOURCE_COMMIT:
        raise ValueError("the pinned source manifest names a different commit")
    files = data.get("source_files")
    if not isinstance(files, dict) or len(files) != SOURCE_FILE_COUNT:
        raise ValueError("the pinned source manifest does not contain the expected 638-file map")
    return data


def validate_pinned_source(source_root: Path = DEFAULT_SOURCE_ROOT) -> dict[str, Any]:
    """Validate the supplied Anvil export against the evaluator-only file map."""
    root = source_root.resolve()
    manifest = source_manifest()
    expected = manifest["source_files"]
    actual: dict[str, str] = {}
    if not root.is_dir():
        return _check("pinned_source_identity", False, "pinned Anvil source export is unavailable")
    for path in root.rglob("*"):
        if path.is_file():
            actual[path.relative_to(root).as_posix()] = _sha256(path)
    missing = sorted(set(expected) - set(actual))
    unexpected = sorted(set(actual) - set(expected))
    changed = sorted(name for name, digest in expected.items() if actual.get(name) != digest)
    ok = not missing and not unexpected and not changed
    detail = (
        "pinned 638-file Anvil export matches the evaluator file map"
        if ok
        else f"pinned source identity mismatch (missing={len(missing)}, unexpected={len(unexpected)}, changed={len(changed)})"
    )
    return _check("pinned_source_identity", ok, detail)


def prepare_target(destination: Path, *, source_root: Path = DEFAULT_SOURCE_ROOT) -> dict[str, Any]:
    """Make an isolated target copy only after confirming the retained export.

    Dependency preparation remains explicit: run ``npm ci`` in the returned
    destination with the pinned package-lock before a measured episode.
    """
    identity = validate_pinned_source(source_root)
    if not identity["passed"]:
        raise ValueError(identity["detail"])
    if destination.exists():
        raise FileExistsError("target destination already exists")
    shutil.copytree(source_root, destination)
    copied = validate_pinned_source(destination)
    if not copied["passed"]:
        shutil.rmtree(destination)
        raise RuntimeError("copied target did not retain pinned source identity")
    return {
        "schema_version": SCHEMA_VERSION,
        "episode_id": EPISODE_ID,
        "target": str(destination),
        "source_commit": SOURCE_COMMIT,
        "source_file_count": SOURCE_FILE_COUNT,
        "package_lock_sha256": _sha256(destination / "package-lock.json"),
    }


def _runtime_provenance(repo: Path, node_binary: str) -> dict[str, Any]:
    package_lock = repo / "package-lock.json"
    return {
        "target_commit": SOURCE_COMMIT,
        "target_file_count": SOURCE_FILE_COUNT,
        "node_binary": node_binary,
        "node_version": _node_version(node_binary),
        "package_lock_sha256": _sha256(package_lock) if package_lock.is_file() else None,
        "fixture_sha256": _sha256(FIXTURE),
    }


def _node_version(node_binary: str) -> str | None:
    try:
        result = subprocess.run(
            [node_binary, "--version"], text=True, capture_output=True, timeout=15, check=False
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return result.stdout.strip() if result.returncode == 0 else None


def _supported_node(version: str | None) -> bool:
    if version is None:
        return False
    try:
        major, minor, patch = (int(part) for part in version.removeprefix("v").split(".", 2))
    except ValueError:
        return False
    return (major, minor, patch) >= (22, 18, 0)


def evaluate(
    repo: Path,
    *,
    work_dir: Path,
    node_binary: str = "node",
    timeout_seconds: int = 90,
) -> dict[str, Any]:
    """Evaluate one candidate checkout without mutating it.

    Return shape::

      {"schema_version": 1, "episode_id": "anvil-creation-evidence",
       "status": "passed|failed|unavailable", "checks": [{"id", "passed", "detail"}],
       "errors": [str], "runtime": {...}, "provenance": {...}}

    ``work_dir`` is evaluator-owned scratch space.  The candidate must already
    have dependencies installed from its unchanged package lock.  Runtime
    overrides are intentionally limited to the Node executable and timeout.
    """
    repo = repo.resolve()
    work_dir = work_dir.resolve()
    runtime = _runtime_provenance(repo, node_binary)
    report: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "episode_id": EPISODE_ID,
        "status": "unavailable",
        "checks": [],
        "errors": [],
        "runtime": runtime,
        "provenance": {
            "source_commit": SOURCE_COMMIT,
            "source_manifest": str(SOURCE_MANIFEST.relative_to(ROOT)),
            "fixture": FIXTURE.name,
            "candidate_is_not_compared_to_baseline": True,
        },
    }
    required = [repo / "package.json", repo / "package-lock.json", repo / "src/manifest/view-server.ts", FIXTURE]
    if not repo.is_dir() or any(not path.is_file() for path in required):
        report["errors"].append("candidate checkout or required runtime files are unavailable")
        return report
    if runtime["node_version"] is None:
        report["errors"].append("Node runtime is unavailable")
        return report
    if not _supported_node(runtime["node_version"]):
        report["errors"].append("Node runtime is older than the pinned Node 22.18 minimum")
        return report
    expected_lock = source_manifest()["source_files"]["package-lock.json"]
    if runtime["package_lock_sha256"] != expected_lock:
        report["errors"].append("candidate package lock does not match the pinned source environment")
        return report
    if not (repo / "node_modules").is_dir():
        report["errors"].append("candidate dependencies are unavailable; prepare with npm ci from the pinned lock")
        return report

    work_dir.mkdir(parents=True, exist_ok=True)
    output = work_dir / "anvil-creation-evidence-result.json"
    command = [node_binary, "--experimental-strip-types", str(FIXTURE), "--repo", str(repo), "--output", str(output)]
    try:
        result = subprocess.run(command, text=True, capture_output=True, timeout=timeout_seconds, check=False)
    except subprocess.TimeoutExpired:
        report["errors"].append("independent fixture exceeded its time limit")
        return report
    except OSError as error:
        report["errors"].append(f"independent fixture could not start: {_safe_error(error)}")
        return report
    if result.returncode != 0 or not output.is_file():
        report["errors"].append("independent fixture did not complete")
        return report
    try:
        fixture_result = json.loads(output.read_text(encoding="utf-8"))
        checks = fixture_result["checks"]
        if not isinstance(checks, list) or not all(isinstance(item, dict) for item in checks):
            raise ValueError("fixture check result has an invalid shape")
        report["checks"] = checks
        report["errors"] = [str(item) for item in fixture_result.get("errors", [])]
        report["status"] = "passed" if all(item.get("passed") is True for item in checks) else "failed"
    except (OSError, ValueError, TypeError, json.JSONDecodeError) as error:
        report["errors"].append(f"independent fixture output is invalid: {_safe_error(error)}")
    return report


def _main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, help="candidate Anvil checkout")
    parser.add_argument("--work-dir", type=Path, help="evaluator-owned scratch directory")
    parser.add_argument("--output", type=Path, required=True, help="JSON report path")
    parser.add_argument("--node-binary", default="node")
    parser.add_argument("--timeout-seconds", type=int, default=90)
    parser.add_argument("--prepare-target", type=Path, help="copy a verified pinned source export here")
    parser.add_argument("--source-root", type=Path, default=DEFAULT_SOURCE_ROOT)
    args = parser.parse_args(argv)
    if args.prepare_target is not None:
        payload = prepare_target(args.prepare_target, source_root=args.source_root)
    else:
        if args.repo is None or args.work_dir is None:
            parser.error("--repo and --work-dir are required unless --prepare-target is used")
        payload = evaluate(args.repo, work_dir=args.work_dir, node_binary=args.node_binary, timeout_seconds=args.timeout_seconds)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return 0 if payload.get("status", "passed") == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(_main())
