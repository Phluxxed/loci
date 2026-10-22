"""Deterministic control/variant comparisons; native workflows stay in complete_work."""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import hashlib
import gzip
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import resource
import shutil
import signal
import subprocess
import sys
import time
import traceback
import uuid

ROOT = Path(__file__).resolve().parents[1]


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False, allow_nan=False) + "\n")


def read_index(path: Path) -> dict:
    return json.loads(gzip.decompress(path.read_bytes()))


def validate_packets(packets: list[dict]) -> None:
    # The observer uses its pinned schema, never the candidate's validators.
    from loci.mcp_output_models import LociReadOutput, LociRetrieveOutput
    for envelope in packets:
        payload = envelope["structuredContent"]
        model = LociReadOutput if "source" in payload else LociRetrieveOutput
        model.model_validate(payload)


def git(repo: Path, *args: str) -> str:
    return subprocess.check_output(["git", "-C", str(repo), *args], text=True).strip()


def working_state(repo: Path) -> dict:
    """Protect dirty tracked and untracked inputs, including their exact bytes."""
    status = git(repo, "status", "--porcelain=v1", "-uall")
    names = subprocess.check_output(
        ["git", "-C", str(repo), "ls-files", "-z", "--modified", "--others", "--exclude-standard"]
    ).decode().split("\0")
    return {"head": git(repo, "rev-parse", "HEAD"), "status": status,
            "files": {name: digest(repo / name) if (repo / name).is_file() else None
                      for name in sorted(set(names)) if name},
            "index_diff": git(repo, "diff", "--cached", "--binary")}


def usage() -> dict:
    r = resource.getrusage(resource.RUSAGE_SELF)
    children = resource.getrusage(resource.RUSAGE_CHILDREN)
    return {"user_cpu_s": r.ru_utime, "system_cpu_s": r.ru_stime,
            "children_user_cpu_s": children.ru_utime, "children_system_cpu_s": children.ru_stime,
            "peak_rss_bytes": int(r.ru_maxrss * (1 if sys.platform == "darwin" else 1024)),
            "minor_faults": r.ru_minflt, "major_faults": r.ru_majflt,
            "block_inputs": r.ru_inblock, "block_outputs": r.ru_oublock}


@contextmanager
def measure(rows: list, phase: str, **identity):
    before, started = usage(), time.perf_counter_ns()
    row = {"phase": phase, **identity, "status": "failed"}
    try:
        yield row
        row["status"] = "completed"
    finally:
        after = usage()
        row.update(elapsed_ns=time.perf_counter_ns() - started,
                   resources={k: after[k] - before[k] for k in before if k != "peak_rss_bytes"},
                   process_peak_rss_bytes=after["peak_rss_bytes"])
        rows.append(row)


def tree_bytes(root: Path) -> int:
    return sum(p.stat().st_size for p in root.rglob("*") if p.is_file())


def worker(config_path: Path) -> int:
    """One fresh process per condition/repetition, importing ONLY its candidate src."""
    started = time.perf_counter_ns()
    config = json.loads(config_path.read_text())
    implementation = Path(config["implementation"])
    sys.path.insert(0, str(implementation / "src"))
    rows: list[dict] = []
    report: dict = {"status": "incomplete", "phases": rows, "cases": [], "indexes": {}}
    output = Path(config["artifacts"])
    try:
        with measure(rows, "runtime_setup"):
            from loci import service
            from loci.storage.store_identity import bind_mcp_store
            from loci.storage.store_resolver import activate_mcp_store
            import loci.service
            loaded = Path(loci.service.__file__).resolve()
            if not loaded.is_relative_to(implementation / "src"):
                raise ValueError(f"candidate import escaped implementation: {loaded}")
            binding = bind_mcp_store()
            activate_mcp_store(binding)
            resolution = service.get_store_resolution().to_dict()
            if (Path(resolution["base_dir"]).resolve() != Path(config["store"]).resolve()
                    or resolution.get("namespace") != config["namespace"]):
                raise ValueError("runtime store binding differs from experiment")
            report["binding"] = resolution
            report["service_source"] = str(loaded)
            report["pid"] = os.getpid()
            report["python"] = sys.version
            report["dependencies"] = sorted((d.metadata["Name"], d.version)
                                                for d in importlib.metadata.distributions())
        for snapshot, path in config["snapshots"].items():
            repo = Path(path)
            with measure(rows, "indexing", snapshot=snapshot) as measurement:
                measurement["work"] = service.index_repo(repo, incremental=False)
            store = service.get_store()
            # Nongit source exports must retain their identity despite living
            # below a worktree. Never use the implementation checkout as input.
            canonical = store._canonical_repo(str(repo))
            if Path(canonical).resolve() != repo.resolve():
                raise ValueError("fixture canonicalized outside its isolated source root")
            index = store.load(repo)
            if index is None:
                raise ValueError("indexing did not produce an index")
            index_file = output / "indexes" / f"{snapshot}.json.gz"
            index_file.parent.mkdir(parents=True, exist_ok=True)
            index_file.write_bytes(gzip.compress(json.dumps(index, ensure_ascii=False,
                                        separators=(",", ":"), allow_nan=False).encode(), mtime=0))
            report["indexes"][snapshot] = str(index_file.relative_to(output))
        for request in config["requests"]:
            repo = Path(config["snapshots"][request["snapshot"]])
            case_id = request["case_id"]
            with measure(rows, "retrieval", case_id=case_id) as measurement:
                packet = service.retrieve(repo, request.get("query", ""),
                                          seed_ids=request.get("seed_ids"), ensure_fresh=True,
                                          graph_enrichment=config["enrichment"] == "on")
                measurement["usage"] = packet.get("usage")
            packets = [{"content": [], "structuredContent": packet, "isError": False}]
            # Fixed continuation rule: hydrate every incomplete selected item,
            # following hash-bound references. No gold-guided additional reads.
            for item in packet["items"]:
                reference = item["source_ref"] if not item["complete"] else None
                seen: set[str] = set()
                while reference:
                    if reference in seen:
                        raise ValueError("non-progressing source continuation")
                    seen.add(reference)
                    with measure(rows, "continuation", case_id=case_id) as measurement:
                        page = service.read(repo, reference, ensure_fresh=True)
                        measurement["usage"] = page.get("usage")
                    packets.append({"content": [], "structuredContent": page, "isError": False})
                    reference = page.get("next_source_ref") if not page["complete"] else None
                    if not page["complete"] and not reference:
                        raise ValueError("incomplete source without continuation")
            case_file = output / "packets" / f"{case_id}.json"
            write(case_file, packets)
            report["cases"].append({"case_id": case_id, "snapshot": request["snapshot"],
                                    "packets": str(case_file.relative_to(output))})
            # Preserve partial progress if a later operation fails/interruption occurs.
            write(output / "worker.json", report)
        report["store_bytes"] = tree_bytes(Path(config["store"]))
        report["cache_bytes"] = tree_bytes(Path(os.environ["XDG_CACHE_HOME"]))
        report["catalog"] = service.list_repos()
        report["status"] = "completed"
    except Exception as exc:
        report.update(status="failed", error=f"{type(exc).__name__}: {exc}", traceback=traceback.format_exc())
    finally:
        report["process_elapsed_ns"] = time.perf_counter_ns() - started
        report["process_resources"] = usage()
        write(output / "worker.json", report)
    return 0 if report["status"] == "completed" else 1


def run_process(command: list[str], cwd: Path, env: dict, log: Path) -> dict:
    """Own a process group; never signal or clean another run's processes."""
    started = time.perf_counter_ns()
    before = resource.getrusage(resource.RUSAGE_CHILDREN)
    with log.open("wb") as stream:
        process = subprocess.Popen(command, cwd=cwd, env=env, stdout=stream,
                                   stderr=subprocess.STDOUT, start_new_session=True)
        try:
            code = process.wait()
        except BaseException:
            os.killpg(process.pid, signal.SIGTERM)
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait()
            raise
        finally:
            # A successful worker may still have spawned background children.
            # Its session/process group belongs exclusively to this invocation.
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
    after = resource.getrusage(resource.RUSAGE_CHILDREN)
    return {"exit_code": code, "elapsed_ns": time.perf_counter_ns() - started,
            "user_cpu_s": after.ru_utime - before.ru_utime,
            "system_cpu_s": after.ru_stime - before.ru_stime}


def artifact_manifest(output: Path) -> dict:
    return {str(p.relative_to(output)): digest(p) for p in sorted(output.rglob("*"))
            if p.is_file() and p.name != "manifest.json" and ".owned" not in p.relative_to(output).parts}


def summarize(phases: list[dict]) -> dict:
    result = {}
    for row in phases:
        group = result.setdefault(row["phase"], {"operations": 0, "elapsed_ns": 0,
                                                "user_cpu_s": 0, "system_cpu_s": 0,
                                                "children_user_cpu_s": 0, "children_system_cpu_s": 0})
        group["operations"] += 1
        group["elapsed_ns"] += row["elapsed_ns"]
        for key in ("user_cpu_s", "system_cpu_s", "children_user_cpu_s", "children_system_cpu_s"):
            group[key] += row["resources"][key]
    return result



def comparisons(output: Path, runs: list[dict]) -> list[dict]:
    """Report paired dimensions independently; no quality/cost composite."""
    pairs = []
    for control in (r for r in runs if r["arm"] == "control"):
        variant = next((r for r in runs if r["arm"] == "variant"
                        and r["repetition"] == control["repetition"] and r["suite"] == control["suite"]), None)
        if variant is None or any(r["status"] != "completed" for r in (control, variant)):
            pairs.append({"control": control["id"], "status": "unavailable"})
            continue
        left = json.loads((output / control["capability"]).read_text())
        right = json.loads((output / variant["capability"]).read_text())
        dimensions = []
        for a, b in zip(left, right, strict=True):
            if a["case_id"] != b["case_id"]:
                raise ValueError("paired capability inventories differ")
            def values(item):
                return {"anchor_selected": int(item["anchor_selection"]["selected"]),
                        "gold_spans_covered": item["source_coverage"]["covered"],
                        "gold_spans_required": item["source_coverage"]["required"],
                        "relationships_available": item["relationships"]["available_dependency_links_total"],
                        "relationships_delivered": item["relationships"]["delivered_dependency_links_total"],
                        "relationships_required": item["relationships"]["required_semantic_dependencies_total"],
                        "forbidden_relationships": item["negative_cases"]["forbidden_proven_relationships"]}
            a_values, b_values = values(a), values(b)
            delta = {k: b_values[k] - a_values[k] for k in a_values}
            regressed = any(delta[k] < 0 for k in ("anchor_selected", "gold_spans_covered", "relationships_available", "relationships_delivered")) or delta["forbidden_relationships"] > 0
            dimensions.append({"case_id": a["case_id"], "control": a_values, "variant": b_values,
                               "delta_variant_minus_control": delta, "capability_regression": regressed,
                               "efficiency": {"control": a["efficiency"], "variant": b["efficiency"]}})
        performance = {}
        for phase in sorted(set(control["phase_totals"]) | set(variant["phase_totals"])):
            a = control["phase_totals"].get(phase)
            b = variant["phase_totals"].get(phase)
            performance[phase] = {"control": a, "variant": b,
                                  "elapsed_delta_ns": b["elapsed_ns"] - a["elapsed_ns"] if a and b else None}
        pairs.append({"status": "compared", "control": control["id"], "variant": variant["id"],
                      "capability": dimensions, "performance": performance,
                      "regressed_cases": [d["case_id"] for d in dimensions if d["capability_regression"]]})
    return pairs


def preserve_evaluator(output: Path) -> dict:
    """Retain the actual observer code, even during uncommitted development."""
    files = {Path(__file__).resolve()}
    files.update(Path(module.__file__).resolve() for name, module in sys.modules.items()
                 if name.startswith(("benchmarks.", "loci.")) and getattr(module, "__file__", None)
                 and Path(module.__file__).suffix == ".py")
    identities = {}
    for source in sorted(files):
        if source.is_relative_to(ROOT):
            relative = source.relative_to(ROOT)
        elif "/src/loci/" in str(source):
            relative = Path("src/loci") / str(source).split("/src/loci/", 1)[1]
        else:
            raise ValueError(f"evaluator import outside its pinned source: {source}")
        target = output / "evaluator" / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        identities[str(relative)] = digest(source)
    return identities


def run(args) -> int:
    from benchmarks.architecture_cases import load_suite, prepare_snapshots, verify_snapshots, requests, score

    repo = Path(args.repo).resolve()
    common = Path(git(repo, "rev-parse", "--path-format=absolute", "--git-common-dir"))
    primary = common.parent
    output = Path(args.output).resolve()
    if output.exists():
        raise ValueError("output must be a new directory; previous experiments are immutable")
    if output.is_relative_to(primary) and not output.is_relative_to(primary / ".worktrees"):
        raise ValueError("outputs must not enter the primary working tree")
    before = working_state(primary)
    output.mkdir(parents=True)
    token = uuid.uuid4().hex
    owned = output / ".owned"
    owned.mkdir()
    worktrees: list[Path] = []
    report = {"schema_version": 1, "kind": "loci-architecture-comparison", "id": token,
              "status": "incomplete", "level": "A", "runs": [], "cleanup": [],
              "harness_revision": git(ROOT, "rev-parse", "HEAD"),
              "harness_dirty": bool(git(ROOT, "status", "--porcelain", "--untracked-files=no")),
              "host": {"platform": platform.platform(), "python": sys.version, "executable": sys.executable},
              "mechanism": "graph enrichment; both conditions retain full graph indexing and storage",
              "graph_free": False,
              "limits": ["source delivery is not agent task correctness", "single runs are descriptive, not significance tests",
                         "OS filesystem/provider caches are not claimed cold", "phase RSS is the process lifetime high-water mark",
                         "deterministic continuation hydrates selected incomplete items only"],
              "primary_before": before}
    created: set[Path] = set()
    try:
        worktree_parent = primary / ".worktrees"
        if subprocess.run(["git", "-C", str(primary), "check-ignore", "-q", ".worktrees/probe"]).returncode:
            raise ValueError("ignore /.worktrees/ before running (the harness never edits the primary checkout)")
        corpora = []
        requested_cases = set(getattr(args, "case", None) or [])
        found_cases = set()
        for i, source in enumerate(args.corpus):
            source = Path(source).resolve()
            load_suite(source)  # independent corpus/archive/span validation before copying
            target = output / "inputs" / str(i)
            target.mkdir(parents=True)
            for item in source.iterdir():
                if item.is_file() and item.suffix in {".json", ".sha256", ".gz", ".md"}:
                    shutil.copyfile(item, target / item.name)
            corpus = load_suite(target)
            if requested_cases:
                corpus["cases"] = [case for case in corpus["cases"] if case["id"] in requested_cases]
                found_cases.update(case["id"] for case in corpus["cases"])
                corpus["snapshots"] = {key: value for key, value in corpus["snapshots"].items()
                                       if key in {case["snapshot"] for case in corpus["cases"]}}
            if corpus["cases"]:
                corpus["_input_id"] = i
                corpora.append(corpus)
        if requested_cases - found_cases:
            raise ValueError(f"unknown selected cases: {sorted(requested_cases - found_cases)}")
        report["selected_cases"] = sorted(requested_cases) if requested_cases else None
        refs = {"control": git(repo, "rev-parse", "--verify", args.control_ref + "^{commit}"),
                "variant": git(repo, "rev-parse", "--verify", args.variant_ref + "^{commit}")}
        report["implementations"] = refs
        report["inputs"] = [str(Path(c["_root"]).relative_to(output)) for c in corpora]
        for repetition in range(args.repetitions):
            order = ["control", "variant"] if repetition % 2 == 0 else ["variant", "control"]
            for arm in order:
                run_id = f"{arm}-{repetition + 1}"
                run_root = owned / run_id
                run_root.mkdir()
                implementation = worktree_parent / f"r0-{token[:12]}-{run_id}"
                with measure(report.setdefault("setup", []), "checkout", run_id=run_id):
                    subprocess.run(["git", "-C", str(repo), "worktree", "add", "--quiet", "--detach",
                                    str(implementation), refs[arm]], check=True)
                worktrees.append(implementation)
                created.add(implementation)
                for corpus_id, corpus in enumerate(corpora):
                    label = f"{run_id}-suite-{corpus_id}"
                    artifacts = output / "artifacts" / label
                    artifacts.mkdir(parents=True)
                    with measure(report["setup"], "fixture_setup", run_id=label):
                        snapshots = prepare_snapshots(corpus, run_root / str(corpus_id) / "fixtures")
                        verify_snapshots(corpus, snapshots)
                    runtime = run_root / str(corpus_id)
                    store = runtime / "store"
                    namespace = f"r0-{token[:16]}-{label}"
                    config = {"implementation": str(implementation), "revision": refs[arm],
                              "enrichment": getattr(args, arm + "_enrichment"), "store": str(store),
                              "namespace": namespace, "snapshots": snapshots,
                              "artifacts": str(artifacts), "requests": requests(corpus)}
                    config_path = artifacts / "config.json"
                    write(config_path, config)
                    env = dict(os.environ)
                    for key in ("PYTHONPATH", "PYTHONHOME", "LOCI_BASE_DIR", "LOCI_STORE_NAMESPACE"):
                        env.pop(key, None)
                    env.update(LOCI_BASE_DIR=str(store), LOCI_STORE_NAMESPACE=namespace,
                               PYTHONDONTWRITEBYTECODE="1", PYTHONNOUSERSITE="1",
                               XDG_CACHE_HOME=str(runtime / "cache"), TMPDIR=str(runtime / "tmp"))
                    (runtime / "tmp").mkdir()
                    execution = run_process([sys.executable, "-B", str(Path(__file__).resolve()),
                                             "_worker", str(config_path)], implementation, env, artifacts / "process.log")
                    entry = {"id": label, "arm": arm, "repetition": repetition + 1, "suite": corpus["version"],
                             "enrichment": config["enrichment"], "execution": execution, "status": "incomplete"}
                    report["runs"].append(entry)
                    verify_snapshots(corpus, snapshots)  # candidate may not mutate its input
                    receipt = artifacts / "worker.json"
                    if not receipt.exists():
                        entry.update(status="failed", error="worker did not retain a terminal receipt")
                        continue
                    result = json.loads(receipt.read_text())
                    entry.update(status=result["status"], phase_totals=summarize(result["phases"]),
                                 process_resources=result.get("process_resources"), store_bytes=result.get("store_bytes"),
                                 cache_bytes=result.get("cache_bytes"))
                    if execution["exit_code"] != 0 or result["status"] != "completed":
                        entry.update(status="failed", error=result.get("error", "nonzero worker exit"))
                        continue
                    if [r["case_id"] for r in result["cases"]] != [r["case_id"] for r in config["requests"]]:
                        raise ValueError("incomplete or reordered request inventory")
                    binding = result["binding"]
                    if (Path(binding["base_dir"]) != store or binding["namespace"] != namespace
                            or result["service_source"] != str(implementation / "src/loci/service.py")):
                        raise ValueError("worker implementation/store identity mismatch")
                    entry["binding"] = binding
                    scores = []
                    for case in result["cases"]:
                        index = read_index(artifacts / result["indexes"][case["snapshot"]])
                        packets = json.loads((artifacts / case["packets"]).read_text())
                        validate_packets(packets)
                        scores.append(score(corpus, case["case_id"], Path(snapshots[case["snapshot"]]), index, packets))
                    write(artifacts / "capability.json", scores)
                    entry["capability"] = str((artifacts / "capability.json").relative_to(output))
                    invalid_cases = [item["case_id"] for item in scores if not item["integrity_ok"]]
                    if invalid_cases:
                        entry.update(status="invalid", invalid_cases=invalid_cases,
                                     error="independent source/output/proof integrity check failed")
        bindings = [r["binding"] for r in report["runs"] if "binding" in r]
        for key in ("base_dir", "namespace", "store_id"):
            if len({b[key] for b in bindings}) != len(bindings):
                raise ValueError(f"conditions share {key}")
        report["comparisons"] = comparisons(output, report["runs"])
        report["status"] = ("invalid" if any(r["status"] == "invalid" for r in report["runs"]) else
                            "completed" if all(r["status"] == "completed" for r in report["runs"]) else "failed")
    except (KeyboardInterrupt, SystemExit):
        report.update(status="incomplete", error="interrupted; later work was not reached")
    except Exception as exc:
        report.update(status="invalid" if isinstance(exc, ValueError) else "failed",
                      error=f"{type(exc).__name__}: {exc}", traceback=traceback.format_exc())
    finally:
        # Only paths actually created by this invocation are eligible. No prune,
        # global cache cleanup, serving-store access, or ambient-process scans.
        for path in worktrees:
            if path not in created or path.parent != primary / ".worktrees" or token[:12] not in path.name:
                raise RuntimeError("refusing cleanup of an unowned checkout")
            result = subprocess.run(["git", "-C", str(repo), "worktree", "remove", "--force", str(path)],
                                    capture_output=True, text=True)
            report["cleanup"].append({"path": str(path), "exit_code": result.returncode, "error": result.stderr})
        shutil.rmtree(owned)
        after = working_state(primary)
        report["primary_unchanged"] = after == before
        if after != before:
            report.update(status="invalid", error="primary working state changed during experiment", primary_after=after)
        if any(row["exit_code"] for row in report["cleanup"]):
            report.update(status="incomplete", error="owned worktree cleanup failed; see cleanup receipts")
        report["evaluator_sources"] = preserve_evaluator(output)
        write(output / "result.json", report)
        write(output / "manifest.json", artifact_manifest(output))
    print(json.dumps({"status": report["status"], "output": str(output), "runs": len(report["runs"]),
                      "primary_unchanged": report["primary_unchanged"], "error": report.get("error")}))
    return 0 if report["status"] == "completed" else 1


def verify(output: Path) -> int:
    from benchmarks.architecture_cases import load_suite, prepare_snapshots, score
    import tempfile

    output = output.resolve()
    expected = json.loads((output / "manifest.json").read_text())
    if artifact_manifest(output) != expected:
        raise ValueError("retained artifact inventory/hash mismatch")
    result = json.loads((output / "result.json").read_text())
    if result["status"] != "completed":
        raise ValueError(f"experiment is {result['status']}, not a successful comparison")
    for relative, identity in result["evaluator_sources"].items():
        if digest(ROOT / relative) != identity:
            raise ValueError(f"replay evaluator source differs: {relative}")
    count = 0
    with tempfile.TemporaryDirectory(prefix="loci-r0-replay-") as temporary:
        for entry in result["runs"]:
            artifacts = output / Path(entry["capability"]).parent
            config = json.loads((artifacts / "config.json").read_text())
            suite_id = int(entry["id"].rsplit("-", 1)[1])
            corpus = load_suite(output / result["inputs"][suite_id])
            if result.get("selected_cases"):
                corpus["cases"] = [case for case in corpus["cases"] if case["id"] in result["selected_cases"]]
                corpus["snapshots"] = {key: value for key, value in corpus["snapshots"].items()
                                       if key in {case["snapshot"] for case in corpus["cases"]}}
            snapshots = prepare_snapshots(corpus, Path(temporary) / entry["id"])
            worker_result = json.loads((artifacts / "worker.json").read_text())
            actual = []
            for case in worker_result["cases"]:
                index = read_index(artifacts / worker_result["indexes"][case["snapshot"]])
                packets = json.loads((artifacts / case["packets"]).read_text())
                validate_packets(packets)
                actual.append(score(corpus, case["case_id"], Path(snapshots[case["snapshot"]]), index, packets))
                count += 1
            if actual != json.loads((artifacts / "capability.json").read_text()):
                raise ValueError("independent capability replay differs")
    print(json.dumps({"status": "verified", "case_executions": count, "output": str(output)}))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    execution = commands.add_parser("run")
    execution.add_argument("--repo", default=str(ROOT))
    execution.add_argument("--output", required=True)
    execution.add_argument("--control-ref", default="HEAD")
    execution.add_argument("--variant-ref", default="HEAD")
    execution.add_argument("--control-enrichment", choices=("on", "off"), default="on")
    execution.add_argument("--variant-enrichment", choices=("on", "off"), default="off")
    execution.add_argument("--corpus", action="append")
    execution.add_argument("--repetitions", type=int, default=1)
    execution.add_argument("--case", action="append", help="explicit case scope; repeat to select several")
    replay = commands.add_parser("verify")
    replay.add_argument("--output", required=True, type=Path)
    internal = commands.add_parser("_worker", help="internal isolated worker")
    internal.add_argument("config", type=Path)
    args = parser.parse_args()
    if args.command == "_worker":
        return worker(args.config)
    # Script execution also works without installing benchmark modules.
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    sys.path.insert(0, str(ROOT / "src"))
    if args.command == "verify":
        return verify(args.output)
    if args.repetitions < 1:
        parser.error("repetitions must be positive")
    if args.corpus is None:
        args.corpus = [str(ROOT / "benchmarks/corpora" / name)
                       for name in ("typescript-context-v3", "multilingual-context-v1")]
    return run(args)


if __name__ == "__main__":
    raise SystemExit(main())
