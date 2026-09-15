"""Evaluate retained stage source outside episode time; never give feedback to a trial."""
from __future__ import annotations

import argparse
import difflib
import json
from pathlib import Path, PurePosixPath

from .controller import sha, write_json
from .runtime import RuntimeFailure


def restore_snapshot(snapshot: dict, history: Path, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=False)
    for name, digest in snapshot["files"].items():
        relative = PurePosixPath(name)
        if (not name or relative.is_absolute() or ".." in relative.parts
                or "\\" in name or relative.as_posix() != name):
            raise RuntimeFailure("unsafe snapshot path")
        if len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
            raise RuntimeFailure("invalid snapshot content address")
        data = (history / "blobs" / digest).read_bytes()
        if sha(data) != digest:
            raise RuntimeFailure("snapshot source bytes differ from their identity")
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)


def snapshot_diff(before: dict, after: dict, history: Path) -> tuple[list[dict], str]:
    changes = []
    patches = []
    for name in sorted(before["files"].keys() | after["files"].keys()):
        old, new = before["files"].get(name), after["files"].get(name)
        if old == new:
            continue
        changes.append({"file": name, "before": old, "after": new})
        try:
            left = (history / "blobs" / old).read_text().splitlines(keepends=True) if old else []
            right = (history / "blobs" / new).read_text().splitlines(keepends=True) if new else []
        except UnicodeError:
            patches.append(f"Binary source changed: {name}\n")
            continue
        patches.extend(difflib.unified_diff(left, right, fromfile="before/" + name,
                                            tofile="after/" + name))
    return changes, "".join(patches)


def evaluate_episode(config_path: Path) -> dict:
    config = json.loads(config_path.read_text())
    output = Path(config["output_dir"])
    receipt = json.loads((output / "result.json").read_text())
    if receipt["run_id"] != config["run_id"] or not receipt.get("measured"):
        raise RuntimeFailure("not a measured receipt for the configured episode")
    destination = output / "evaluation"
    destination.mkdir(exist_ok=False)
    history = output / "source-history"
    before = json.loads((output / "source-before.json").read_text())
    report = {"schema_version": 1, "run_id": config["run_id"],
              "episode_receipt_sha256": sha((output / "result.json").read_bytes()),
              "correct": None, "manual_review": "pending_arm_blinded_review",
              "stages": [], "errors": []}
    for stage in receipt["stages"]:
        identifier = stage["stage_id"]
        snapshot_path = output / f"source-after-{identifier}.json"
        if stage["outcome"] == "not_reached" or not snapshot_path.exists():
            report["stages"].append({"stage_id": identifier, "oracle_status": "unavailable",
                                     "reason": "no retained stage snapshot"})
            continue
        snapshot = json.loads(snapshot_path.read_text())
        stage_root = destination / identifier
        candidate = stage_root / "candidate"
        restore_snapshot(snapshot, history, candidate)
        # Prepared dependencies are immutable to the trial. The hidden evaluator
        # is outside every measured workspace and uses the retained source version.
        node_modules = Path(config["repo"]) / "node_modules"
        if node_modules.is_dir():
            (candidate / "node_modules").symlink_to(node_modules, target_is_directory=True)
        if receipt["episode_id"] == "anvil-creation-evidence":
            from .oracles.anvil import evaluate
            oracle = evaluate(candidate, work_dir=stage_root / "oracle")
        elif receipt["episode_id"] == "loci-direnv-exclusion":
            from .oracles.loci import evaluate
            oracle = evaluate(candidate, work_dir=stage_root / "oracle",
                              python_executable=config.get("oracle", {}).get("python_executable"))
        else:
            raise RuntimeFailure("unknown episode evaluator")
        write_json(stage_root / "oracle.json", oracle)
        changes, patch = snapshot_diff(before, snapshot, history)
        (stage_root / "changes.diff").write_text(patch)
        report["stages"].append({"stage_id": identifier,
                                 "snapshot_sha256": sha(snapshot_path.read_bytes()),
                                 "source_identity": snapshot["sha256"],
                                 "oracle_status": oracle["status"], "changes": changes,
                                 "oracle_receipt": str(stage_root / "oracle.json")})
    report["limitations"] = [
        "Behavioral checks are terminal-feature checks; orientation claims require stage-specific review.",
        "Correctness, invariant severity and rework require the predeclared arm-blinded review.",
        "A passing oracle is not final acceptance; these checks never trigger another agent turn.",
    ]
    write_json(destination / "report.json", report)
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    args = parser.parse_args()
    report = evaluate_episode(args.config)
    print(json.dumps({"run_id": report["run_id"], "manual_review": report["manual_review"],
                      "stages": [{k: x.get(k) for k in ("stage_id", "oracle_status")}
                                 for x in report["stages"]]}))


if __name__ == "__main__":
    main()
