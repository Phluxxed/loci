"""R1 combined qualification using the unchanged R0 acquisition and proof scorers.

This deterministic policy asks semantics in slot two using the next path query,
then at most four delivered-identity proof requests. Native agents may choose
whether to ask semantics; this fixture policy does not measure agent benefit.
"""
from __future__ import annotations

import argparse
import gzip
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import time

from benchmarks.architecture import (
    ROOT, acquire, acquisition_scores, artifact_manifest, digest, measure,
    preserve_evaluator, run_process, summarize, tree_bytes, usage, write,
)
from benchmarks.architecture_cases import load_suite, prepare_snapshots, requests


def _archive_index(path: Path, index: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(gzip.compress(json.dumps(index, sort_keys=True).encode(), mtime=0))


def worker(config_path: Path) -> int:
    """Fresh process and store per arm/repetition, warm repeat immediately per case."""
    started = time.perf_counter_ns()
    config = json.loads(config_path.read_text())
    output = config_path.parent
    phases = []
    with measure(phases, "runtime_setup"):
        from loci.integrated import IntegratedSource
        service = IntegratedSource(output / ".owned" / "store")
    report = {"cases": [], "indexes": {}, "phases": phases}
    inventories = {}
    for snapshot, path in config["snapshots"].items():
        root = Path(path)
        with measure(phases, "inventory", snapshot=snapshot) as row:
            row["work"] = service.index_repo(root)
            index = service.inventory(root)
            inventories[snapshot] = {"schema_version": 1, "files": {
                name: {"sha256": value, "size": (root / name).stat().st_size}
                for name, value in sorted(index["file_hashes"].items())}}
        relative = f"indexes/{snapshot}.json.gz"
        _archive_index(output / relative, index)
        report["indexes"][snapshot] = relative
        write(output / "inventories" / f"{snapshot}.json", inventories[snapshot])
    report["semantic_modules_before_questions"] = sorted(name for name in sys.modules
        if name in {"loci.parser", "loci.graph", "loci.storage"}
        or name.startswith(("loci.parser.", "loci.graph.", "loci.storage.")))
    for request in config["requests"]:
        root = Path(config["snapshots"][request["snapshot"]])
        case = {"case_id": request["case_id"], "snapshot": request["snapshot"]}
        for repeat in (False, True):
            prefix = "repeat_" if repeat else ""
            with measure(phases, prefix + "end_to_end", case_id=request["case_id"]):
                packets, trace = acquire(service, root, request, inventories[request["snapshot"]], phases,
                    graph_free=True, enrichment=True, demand=config["semantic"],
                    path_navigation=True, focused=config["semantic"], trial="repeat" if repeat else "first")
            relative = f"packets/{request['case_id']}{'.repeat' if repeat else ''}.json"
            write(output / relative, packets)
            case[prefix + "packets"] = relative
            case[prefix + "acquisition"] = trace
            if config["semantic"] and any(q.get("operation") == "semantic_context" for q in trace["queries"]):
                observer = service.semantic_observer()
                relative = f"case-indexes/{request['case_id']}{'.repeat' if repeat else ''}.json.gz"
                _archive_index(output / relative, observer["index"])
                case[prefix + "index"] = relative
                case[prefix + "semantic_work"] = observer["work"]
        report["cases"].append(case)
    report.update(status="completed", process_elapsed_ns=time.perf_counter_ns() - started,
                  process_resources=usage(), phase_totals=summarize(phases),
                  store_bytes=tree_bytes(output / ".owned" / "store"))
    write(output / "worker.json", report)
    return 0


def _selected(corpus: dict, selected: list[str]) -> dict:
    if selected:
        corpus["cases"] = [case for case in corpus["cases"] if case["id"] in selected]
        snapshots = {case["snapshot"] for case in corpus["cases"]}
        corpus["snapshots"] = {name: value for name, value in corpus["snapshots"].items() if name in snapshots}
    return corpus


def run(output: Path, corpora: list[Path], *, cases: list[str], repetitions: int = 1) -> dict:
    output = output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    result = {"status": "incomplete", "selected_cases": cases, "inputs": [], "runs": [],
              "qualification": "fixed-policy fixture acquisition and proof; agent task correctness unmeasured"}
    found = set()
    for number, source in enumerate(corpora):
        load_suite(source)
        target = output / "inputs" / str(number)
        target.mkdir(parents=True)
        for path in source.iterdir():
            if path.is_file() and path.suffix in {".json", ".sha256", ".gz", ".md"}:
                shutil.copyfile(path, target / path.name)
        corpus = _selected(load_suite(target), cases)
        found.update(case["id"] for case in corpus["cases"])
        if not corpus["cases"]:
            continue
        result["inputs"].append(str(target.relative_to(output)))
        snapshots = prepare_snapshots(corpus, output / ".owned" / f"fixtures-{number}")
        for repetition in range(repetitions):
            order = (False, True) if repetition % 2 == 0 else (True, False)
            for semantic in order:
                arm = "integrated" if semantic else "source-only"
                artifacts = output / f"{arm}-{repetition + 1}-suite-{number}"
                artifacts.mkdir()
                config = {"architecture": "integrated", "semantic": semantic,
                          "snapshots": snapshots, "requests": requests(corpus)}
                write(artifacts / "config.json", config)
                env = dict(os.environ, PYTHONPATH=str(ROOT / "src") + os.pathsep + str(ROOT))
                execution = run_process([sys.executable, "-m", "benchmarks.architecture_integrated",
                    "--worker", str(artifacts / "config.json")], ROOT, env, artifacts / "process.log")
                if execution["exit_code"]:
                    raise RuntimeError(f"qualification worker failed: {artifacts / 'process.log'}")
                report = json.loads((artifacts / "worker.json").read_text())
                for repeat in (False, True):
                    scores = acquisition_scores(corpus, snapshots, artifacts, report, demand=semantic,
                        focused=semantic, path_navigation=True, repeat=repeat)
                    write(artifacts / ("repeat-capability.json" if repeat else "capability.json"), scores)
                result["runs"].append({"arm": arm, "suite": str(target.relative_to(output)),
                    "artifacts": str(artifacts.relative_to(output)), "execution": execution,
                    "phase_totals": report["phase_totals"], "store_bytes": report["store_bytes"]})
    if set(cases) - found:
        raise ValueError(f"unknown cases: {sorted(set(cases) - found)}")
    result["evaluator_sources"] = preserve_evaluator(output)
    # Runtime code is part of the replayable record even though scoring cannot
    # establish behavior beyond the exact archived packets.
    for name in ("integrated.py", "integrated_mcp.py", "focused_proof.py", "demand_semantics.py",
                 "graph_free.py", "path_navigation.py"):
        relative = Path("src/loci") / name
        destination = output / "implementation" / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / relative, destination)
    result["status"] = "completed"
    write(output / "result.json", result)
    write(output / "manifest.json", artifact_manifest(output))
    return result


def verify(output: Path) -> dict:
    """Recompute every score with frozen fixtures, not a live candidate service."""
    output = output.resolve()
    if artifact_manifest(output) != json.loads((output / "manifest.json").read_text()):
        raise ValueError("retained artifact inventory/hash mismatch")
    result = json.loads((output / "result.json").read_text())
    if result["status"] != "completed":
        raise ValueError("qualification incomplete")
    for relative, expected in result["evaluator_sources"].items():
        if digest(ROOT / relative) != expected:
            raise ValueError(f"replay evaluator source differs: {relative}")
    count = 0
    with tempfile.TemporaryDirectory(prefix="loci-r1-replay-") as temporary:
        for entry in result["runs"]:
            corpus = _selected(load_suite(output / entry["suite"]), result["selected_cases"])
            snapshots = prepare_snapshots(corpus, Path(temporary) / entry["artifacts"])
            artifacts = output / entry["artifacts"]
            report = json.loads((artifacts / "worker.json").read_text())
            config = json.loads((artifacts / "config.json").read_text())
            if [case["case_id"] for case in report["cases"]] != [row["case_id"] for row in requests(corpus)]:
                raise ValueError("retained request inventory differs from authored cases")
            for repeat in (False, True):
                actual = acquisition_scores(corpus, snapshots, artifacts, report, demand=config["semantic"],
                    focused=config["semantic"], path_navigation=True, repeat=repeat)
                expected = json.loads((artifacts / ("repeat-capability.json" if repeat else "capability.json")).read_text())
                if actual != expected:
                    raise ValueError("independent combined acquisition replay differs")
                count += len(actual)
    return {"status": "verified", "case_executions": count}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--worker", type=Path)
    parser.add_argument("--verify", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--corpus", action="append", type=Path)
    parser.add_argument("--case", action="append", default=[])
    parser.add_argument("--repetitions", type=int, default=1)
    args = parser.parse_args()
    if args.worker:
        raise SystemExit(worker(args.worker))
    if args.verify:
        print(json.dumps(verify(args.verify)))
    elif args.output:
        if args.repetitions < 1:
            parser.error("repetitions must be positive")
        result = run(args.output, args.corpus or [ROOT / "benchmarks/corpora/typescript-context-v3",
            ROOT / "benchmarks/corpora/multilingual-context-v1"], cases=args.case, repetitions=args.repetitions)
        print(json.dumps({"status": result["status"], "runs": len(result["runs"])}))
    else:
        parser.error("choose --output or --verify")


if __name__ == "__main__":
    main()
