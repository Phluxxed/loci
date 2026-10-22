"""R0 snapshots and native-session readback. Never starts a model or sandbox.

Run agents through the existing native host, with its permissions unchanged.
The historical complete-work controller remains the graph-on/off runner.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from urllib.parse import unquote, urlsplit

from .accounting import summarize_native
from .evaluate import restore_snapshot, source_snapshot, verify_snapshot, write_json


PROTECTION_FIELDS = (
    "approval_policy", "approvals_reviewer", "sandbox_policy", "permission_profile",
    "active_permission_profile", "file_system_sandbox_policy",
)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def disjoint(*paths: Path) -> bool:
    return all(not a.is_relative_to(b) and not b.is_relative_to(a)
               for i, a in enumerate(paths) for b in paths[i + 1:])


def prepare(source: Path, destination: Path, *, run_id: str, arm: str,
            native_config: Path, conditions: dict) -> dict:
    """Copy a prepared source export; keep all results outside the task snapshot."""
    if arm not in {"native", "loci"} or not run_id:
        raise ValueError("explicit run identity and native/loci assignment required")
    source = source.resolve(strict=True)
    destination = destination.resolve()
    native_config = native_config.resolve(strict=True)
    if not disjoint(source, destination):
        raise ValueError("source and destination must be disjoint")
    destination.mkdir(parents=True, exist_ok=False)
    observer = destination / "observer"
    observer.mkdir()
    snapshot = source_snapshot(source, observer / "source-history")
    restore_snapshot(snapshot, observer / "source-history", destination / "workspace")
    write_json(observer / "source-before.json", snapshot)
    manifest = {
        "schema_version": 1, "kind": "r0-native-session-input", "run_id": run_id,
        "arm": arm, "workspace": str(destination / "workspace"),
        "observer": str(observer), "source_identity": snapshot["sha256"],
        "native_config": str(native_config), "native_config_sha256": digest(native_config),
        "conditions": conditions, "permission_overrides": {}, "measured": False,
    }
    write_json(observer / "run.json", manifest)
    return manifest


def qualify(config: Path, trace: Path, *, thread_id: str) -> dict:
    """Archive one closed native trace and replayable source; retain unknowns."""
    manifest = json.loads(config.read_text())
    if manifest.get("kind") != "r0-native-session-input" or manifest.get("permission_overrides") != {}:
        raise ValueError("R0 requires the unchanged native permission configuration")
    observer = Path(manifest["observer"]).resolve(strict=True)
    workspace = Path(manifest["workspace"]).resolve(strict=True)
    if not disjoint(workspace, observer):
        raise ValueError("task source and observer results overlap")
    output = observer / "qualification"
    output.mkdir(exist_ok=False)
    raw = trace.read_bytes()
    archived = output / "native-rollout.jsonl"
    archived.write_bytes(raw)
    try:
        accounting = summarize_native(archived, thread_id)
    except (ValueError, KeyError, TypeError) as exc:
        accounting = {"usage_status": "unknown", "usage": None, "stages": [],
                      "turn_contexts": [], "native_errors": [f"invalid native evidence: {exc}"]}
    before = json.loads((observer / "source-before.json").read_text())
    verify_snapshot(before, manifest["source_identity"])
    after = source_snapshot(workspace, observer / "source-history")
    write_json(output / "source-after.json", after)
    errors = list(accounting.get("native_errors", []))
    if digest(Path(manifest["native_config"])) != manifest["native_config_sha256"]:
        errors.append("native configuration changed during qualification")
    contexts = accounting.get("turn_contexts", [])
    expected = manifest["conditions"].get("native_protection")
    if not contexts:
        errors.append("native turn settings unavailable")
    for context in contexts:
        observed = {field: context.get(field) for field in PROTECTION_FIELDS}
        if expected is None or observed != expected:
            errors.append("native protection settings differ from the existing host")
        for field in ("model", "effort"):
            if context.get(field) != manifest["conditions"].get(field):
                errors.append(f"native {field} differs from assignment")
    if manifest["arm"] == "native" and any(
            item.get("server") == "loci"
            for stage in accounting.get("stages", []) for item in stage.get("items", [])):
        errors.append("native-only assignment invoked Loci")
    for stage in accounting.get("stages", []):
        for item in stage.get("items", []):
            if item.get("type") == "commandExecution":
                cwd = item.get("cwd")
                if isinstance(cwd, str) and cwd.startswith("file://"):
                    uri = urlsplit(cwd)
                    cwd = unquote(uri.path) if uri.netloc in {"", "localhost"} else None
                if not isinstance(cwd, str) or not Path(cwd).is_absolute() or Path(cwd).resolve() != workspace:
                    errors.append("command working directory differs from assigned snapshot")
            if item.get("type") == "collabAgentToolCall":
                errors.append("trial delegated work outside its captured thread")
    result = {
        "schema_version": 1, "kind": "r0-native-session-qualification",
        "run_id": manifest["run_id"], "arm": manifest["arm"], "thread_id": thread_id,
        "status": "qualified_observations" if not errors and accounting.get("usage_status") == "known" else "unqualified",
        "measured": False, "config_sha256": digest(config),
        "native_trace_sha256": hashlib.sha256(raw).hexdigest(),
        "source_before": manifest["source_identity"], "source_after": after["sha256"],
        "conditions": manifest["conditions"], "native_config_sha256": manifest["native_config_sha256"],
        "workspace": str(workspace), "observer": str(observer),
        "accounting": accounting, "errors": errors,
        "limitations": [
            "Experimental separation uses independent source copies and fresh native sessions; no additional access-control layer.",
            "Native-only navigation is an audited instruction policy, not a hidden-tool capability boundary.",
            "Observed response usage does not prove complete billing or invisible upstream retry accounting.",
            "This readback neither launches nor authorizes a measured pilot; independent grading and a prospective freeze remain necessary.",
        ],
    }
    write_json(output / "result.json", result)
    return result


def check_pair(left: dict, right: dict) -> dict:
    """Reject unequal inputs/settings or shared sessions/storage before analysis."""
    errors = []
    if {left.get("arm"), right.get("arm")} != {"native", "loci"}:
        errors.append("pair must have one native and one Loci assignment")
    for field in ("conditions", "native_config_sha256", "source_before"):
        if left.get(field) is None or left.get(field) != right.get(field):
            errors.append(f"unequal pair {field}")
    if (not all(r.get("thread_id") for r in (left, right))
            or left["thread_id"] == right["thread_id"]):
        errors.append("pair reused a native session")
    if not all(r.get("run_id") for r in (left, right)) or left["run_id"] == right["run_id"]:
        errors.append("pair reused a run identity")
    paths = [Path(r[field]).resolve() for r in (left, right) for field in ("workspace", "observer")]
    if not disjoint(*paths):
        errors.append("pair source or result storage overlaps")
    if any(r.get("status") != "qualified_observations" for r in (left, right)):
        errors.append("pair contains unqualified evidence")
    return {"status": "matched" if not errors else "invalid", "errors": errors, "measured": False}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="operation", required=True)
    create = commands.add_parser("prepare")
    for flag in ("source", "destination", "native-config", "conditions"):
        create.add_argument("--" + flag, type=Path, required=True)
    create.add_argument("--run-id", required=True)
    create.add_argument("--arm", choices=("native", "loci"), required=True)
    read = commands.add_parser("qualify")
    read.add_argument("--config", type=Path, required=True)
    read.add_argument("--trace", type=Path, required=True)
    read.add_argument("--thread-id", required=True)
    args = parser.parse_args()
    if args.operation == "prepare":
        result = prepare(args.source, args.destination, run_id=args.run_id, arm=args.arm,
                         native_config=args.native_config, conditions=json.loads(args.conditions.read_text()))
    else:
        result = qualify(args.config, args.trace, thread_id=args.thread_id)
    print(json.dumps({key: result[key] for key in ("run_id", "arm", "status", "workspace", "observer") if key in result}))


if __name__ == "__main__":
    main()
