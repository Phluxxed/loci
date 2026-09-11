"""Run the frozen v3 ABC schedule with an independently pinned engine per arm."""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile
import time


ROOT = Path(__file__).resolve().parents[1]
COMPARISON = "typescript-context-three-arm-v1"
CORPUS_ROOT = ROOT / "benchmarks/corpora/typescript-context-v3"
COMPARISON_ROOT = ROOT / "benchmarks/comparisons" / COMPARISON
ARM_COMMITS = {
    "A": "9acd3e3589ddc034cade36e03c26c4508e9d4434",
    "B": "564c152099b13f469cb336f1046829f8e8d9d07b",
    "C": "0ad281fbe476ab9e2b9d0f1f9fa08a817618c77b",
}
ARM_ORDERS = [["A", "B", "C"], ["B", "C", "A"], ["C", "A", "B"]]
NEW_HARNESS = [f"benchmarks/typescript_context_three_arm{suffix}.py"
               for suffix in ("", "_worker", "_tools", "_preflight", "_report")]


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def save(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n")


def git(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()


def source_identity(arm: str) -> dict:
    commit = ARM_COMMITS[arm]
    archive = subprocess.check_output(["git", "archive", commit, "src"], cwd=ROOT)
    with tarfile.open(fileobj=io.BytesIO(archive)) as source:
        members = source.getmembers()
        if any(member.issym() or member.islnk() or not (
                member.name == "src" or member.name.startswith("src/")) for member in members):
            raise ValueError("unexpected source archive entry")
        files = {member.name: sha(source.extractfile(member).read())
                 for member in members if member.isfile()}
    return {"arm": arm, "commit": commit, "source_tree": git("rev-parse", commit + ":src"),
            "extractor_version": 24 if arm in {"A", "B"} else 25, "files": files}


def materialize_engine(identity: dict, engine_root: Path) -> Path:
    destination = engine_root / identity["arm"]
    if not destination.exists():
        archive = subprocess.check_output(["git", "archive", identity["commit"], "src"], cwd=ROOT)
        destination.mkdir(parents=True)
        with tarfile.open(fileobj=io.BytesIO(archive)) as source:
            source.extractall(destination, filter="data")
    verify_engine(identity, destination / "src")
    return destination / "src"


def verify_engine(identity: dict, engine_src: Path) -> None:
    actual = {str(path.relative_to(engine_src.parent)): sha(path.read_bytes())
              for path in engine_src.rglob("*") if path.is_file() and "__pycache__" not in path.parts}
    if actual != identity["files"]:
        raise ValueError(f"arm {identity['arm']} source differs from its pinned commit")


def engine_environment(engine_src: Path) -> dict:
    return {**os.environ, "PYTHONPATH": os.pathsep.join((str(engine_src.resolve()), str(ROOT))),
            "PYTHONDONTWRITEBYTECODE": "1"}


def schedule(corpus: dict, controls: dict) -> list[dict]:
    declared = controls["schedule"]
    if (declared["arm_orders"] != ARM_ORDERS or declared["repetitions"] != 3
            or declared["concurrency"] != 1 or declared["planned_runs"] != 153
            or declared["case_order"] != "corpus_order"
            or [case["id"] for case in corpus["cases"]] != controls["case_ids"]
            or len(corpus["cases"]) != 17):
        raise ValueError("frozen ABC schedule changed")
    return [{"attempt_id": f"{case['id']}-r{repetition}-{arm}", "case_id": case["id"],
             "snapshot": case["snapshot"], "repetition": repetition, "arm": arm}
            for case in corpus["cases"] for repetition, order in enumerate(ARM_ORDERS, 1)
            for arm in order]


def frozen_file_hashes() -> dict:
    old = json.loads((ROOT / "benchmarks/comparisons/typescript-context-existing-v1/freeze.json").read_text())
    for relative, expected in old["harness_files"].items():
        if sha((ROOT / relative).read_bytes()) != expected:
            raise ValueError("historical frozen harness changed: " + relative)
    return {relative: sha((ROOT / relative).read_bytes())
            for relative in sorted(set(old["harness_files"]) | set(NEW_HARNESS))}


def validate_freeze(path: Path) -> dict:
    value = json.loads(path.read_text())
    if value["version"] != COMPARISON or value["harness_files"] != frozen_file_hashes():
        raise ValueError("comparison harness differs from its freeze")
    for arm in ARM_COMMITS:
        if value["engines"][arm] != source_identity(arm):
            raise ValueError("comparison engine pin changed")
    for group, base in (("corpus_files", CORPUS_ROOT), ("comparison_files", ROOT)):
        for relative, digest in value[group].items():
            if sha((base / relative).read_bytes()) != digest:
                raise ValueError("frozen file changed: " + relative)
    paths = list(value["harness_files"]) + list(value["comparison_files"]) + [
        str(CORPUS_ROOT.relative_to(ROOT)), str(path.relative_to(ROOT))]
    if git("status", "--porcelain", "--", *paths):
        raise ValueError("frozen files must be committed before measurement")
    committed_freeze = subprocess.check_output(["git", "show", "HEAD:" + str(path.relative_to(ROOT))], cwd=ROOT)
    if committed_freeze != path.read_bytes():
        raise ValueError("freeze declaration differs from its committed carrier")
    subprocess.run(["git", "merge-base", "--is-ancestor", value["freeze_commit"], "HEAD"],
                   cwd=ROOT, check=True, capture_output=True)
    for relative, digest in value["harness_files"].items():
        blob = subprocess.check_output(["git", "show", value["freeze_commit"] + ":" + relative], cwd=ROOT)
        if sha(blob) != digest:
            raise ValueError("freeze commit differs from harness: " + relative)
    return {**value, "freeze_json_sha256": sha(path.read_bytes()), "carrier_commit": git("rev-parse", "HEAD")}


def checked_subprocess(module: str, args: list[str], engine_src: Path, *, timeout: int) -> None:
    subprocess.run([sys.executable, "-m", module, *args], cwd=ROOT,
                   env=engine_environment(engine_src), check=True, timeout=timeout)


def run_batch(freeze_path: Path, output: Path, catalog: Path, engine_root: Path, resume: bool) -> dict:
    from benchmarks.typescript_context_baseline import environment
    from benchmarks.typescript_context_compare import _retain_catalog
    from benchmarks.typescript_context_corpus import load_controls, load_corpus
    from benchmarks.typescript_context_expansion_transport import CANONICAL_TOOL_SCHEMAS_SHA256

    corpus = load_corpus(CORPUS_ROOT)
    controls = load_controls(corpus)
    plan = schedule(corpus, controls)
    freeze = validate_freeze(freeze_path)
    observed_environment = environment(controls)
    cli_version = subprocess.check_output(["codex", "--version"], text=True).strip()
    if cli_version != "codex-cli " + controls["agent"]["cli_version"]:
        raise ValueError("Codex environment changed; a new full matched block is required")
    engines = {arm: materialize_engine(identity, engine_root)
               for arm, identity in freeze["engines"].items()}
    retained = _retain_catalog(catalog.resolve(), output, resume=resume)
    catalog_provenance = catalog.with_name("model-catalog-provenance.json")
    retained_provenance = output / "model-catalog-provenance.json"
    if not catalog_provenance.is_file():
        raise ValueError("fresh model catalog provenance is required")
    if resume and (not retained_provenance.is_file()
                   or retained_provenance.read_bytes() != catalog_provenance.read_bytes()):
        raise ValueError("model catalog provenance changed")
    if not resume:
        retained_provenance.write_bytes(catalog_provenance.read_bytes())
    identity = {"schema_version": 3, "comparison": COMPARISON, "planned_runs": len(plan),
                "plan": plan, "freeze": freeze, "environment": observed_environment,
                "cli_version": cli_version, "catalog_sha256": sha(retained.read_bytes()),
                "catalog_provenance_sha256": sha(retained_provenance.read_bytes()),
                "canonical_tool_schemas_sha256": CANONICAL_TOOL_SCHEMAS_SHA256}
    manifest_path = output / "manifest.json"
    if resume:
        previous = json.loads(manifest_path.read_text())
        # A later publication may change HEAD, but never code, source, controls or evidence.
        old_identity = dict(previous["identity"])
        old_identity["freeze"] = {**old_identity["freeze"], "carrier_commit": freeze["carrier_commit"]}
        if old_identity != identity:
            raise ValueError("cannot resume across a changed matched environment or freeze")
        for relative, digest in previous["transport_files"].items():
            if sha((output / relative).read_bytes()) != digest:
                raise ValueError("retained transport evidence changed")
    else:
        for arm, engine_src in engines.items():
            checked_subprocess("benchmarks.typescript_context_three_arm_preflight",
                               ["--mode", "transport", "--arm", arm, "--engine-src", str(engine_src),
                                "--catalog", str(retained), "--output", str(output / f"transport-{arm}.json")],
                               engine_src, timeout=360)
        transport_files = {str(path.relative_to(output)): sha(path.read_bytes())
                           for path in output.glob("transport-*") if path.is_file()}
        for directory in output.glob("transport-*-evidence"):
            transport_files.update({str(path.relative_to(output)): sha(path.read_bytes())
                                    for path in directory.rglob("*") if path.is_file()})
        save(manifest_path, {"identity": identity, "transport_files": transport_files,
                            "started_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())})
    results = []
    for item in plan:
        destination = output / item["attempt_id"]
        result_path = destination / "result.json"
        if result_path.exists():
            if not resume:
                raise ValueError("attempt already exists: " + item["attempt_id"])
            result = json.loads(result_path.read_text())
            if result.get("attempt_id") != item["attempt_id"] or result.get("arm") != item["arm"]:
                raise ValueError("saved attempt identity differs from plan")
        else:
            if destination.exists():
                raise ValueError("partial attempt retained; it cannot be retried as a missing run")
            if frozen_file_hashes() != freeze["harness_files"]:
                raise ValueError("cannot mix a changed harness into a measured batch")
            arm = item["arm"]
            verify_engine(freeze["engines"][arm], engines[arm])
            print(json.dumps({"starting": item["attempt_id"], "position": len(results) + 1, "total": 153}), flush=True)
            with tempfile.TemporaryDirectory(prefix="loci-abc-worker-") as temporary:
                spec_path = Path(temporary) / "spec.json"
                save(spec_path, {"corpus_root": str(CORPUS_ROOT), "output": str(output),
                                "catalog": str(retained), "engine_src": str(engines[arm]),
                                "engine": freeze["engines"][arm], "plan": item,
                                "expected_schema_hash": CANONICAL_TOOL_SCHEMAS_SHA256, "freeze": freeze})
                checked_subprocess("benchmarks.typescript_context_three_arm_worker", ["--spec", str(spec_path)],
                                   engines[arm], timeout=300)
            result = json.loads(result_path.read_text())
        measured, baseline = result["measurement"], result["baseline"]
        row = {"attempt_id": item["attempt_id"], "arm": item["arm"], **measured,
               "end_to_end_seconds": baseline.get("end_to_end_seconds"),
               "failures": baseline.get("failures", [])}
        results.append(row)
        print(json.dumps({"completed": item["attempt_id"], "position": len(results),
                          "answer": measured.get("answer_correct"), "full_pass": measured.get("task_correct"),
                          "calls": measured.get("read_count"), "accounting": measured.get("measurement_complete"),
                          "seconds": baseline.get("end_to_end_seconds")}), flush=True)
        save(output / "progress.json", {"recorded_runs": len(results), "planned_runs": 153,
                                        "last_completed": item["attempt_id"]})
    summary = {"schema_version": 3, "comparison": COMPARISON, "planned_runs": 153,
               "recorded_runs": len(results), "complete_batch": len(results) == 153,
               "schedule": controls["schedule"], "results": results}
    save(output / "summary.json", summary)
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--freeze", type=Path, default=COMPARISON_ROOT / "freeze.json")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--catalog", type=Path, required=True)
    parser.add_argument("--engine-root", type=Path, required=True)
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()
    run_batch(args.freeze.resolve(), args.output.resolve(), args.catalog.resolve(),
              args.engine_root.resolve(), args.resume)


if __name__ == "__main__":
    main()
