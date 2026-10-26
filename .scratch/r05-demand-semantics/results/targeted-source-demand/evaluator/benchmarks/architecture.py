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
        if payload.get("policy") == "graph-free-file-v1":
            from benchmarks.architecture_cases import validate_graph_free_packet
            validate_graph_free_packet(payload)
            continue
        if payload.get("policy") == "demand-semantic-v1":
            from benchmarks.architecture_cases import validate_demand_packet
            validate_demand_packet(payload)
            continue
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


def acquire(service, repo: Path, request: dict, inventory: dict, rows: list,
            *, graph_free: bool, enrichment: bool, demand: bool = False,
            trial: str = "first") -> tuple[list, dict]:
    from benchmarks.architecture_cases import ACQUISITION_LIMITS as limits, next_acquisition_query
    packets, queries, asked = [], [], []
    continuations = source_bytes = output_bytes = 0
    reason = "query_limit"
    while len(queries) < limits["retrieval_calls"]:
        if source_bytes >= limits["source_bytes"] or output_bytes >= limits["output_bytes"]:
            reason = "byte_admission_limit"
            break
        semantic = demand and len(queries) == 1
        query = request["query"] if not asked or semantic else next_acquisition_query(inventory, packets, asked)
        if query is None:
            reason = "discovery_exhausted"
            break
        start = len(packets)
        phase = "semantic_context" if semantic else "retrieval" if not asked else "followup"
        if trial == "repeat":
            phase = "repeat_" + phase
        with measure(rows, phase, case_id=request["case_id"], query=query) as row:
            packet = (service.semantic_context(repo, query) if semantic else
                      service.retrieve(repo, query, ensure_fresh=True, graph_enrichment=enrichment))
            row["usage"] = packet.get("usage")
            if semantic:
                row["work"] = service.semantic_observer()["work"]
        def append(payload):
            nonlocal source_bytes, output_bytes
            envelope = {"content": [], "structuredContent": payload, "isError": False}
            packets.append(envelope)
            source_bytes += payload["usage"]["evidence_bytes"]
            output_bytes += len(json.dumps(envelope, ensure_ascii=False, separators=(",", ":")).encode())
        append(packet)
        for item in packet["items"]:
            reference = item["source_ref"] if not item["complete"] else None
            seen = set()
            while reference:
                if (continuations >= limits["continuation_calls"] or source_bytes >= limits["source_bytes"]
                        or output_bytes >= limits["output_bytes"]):
                    break
                if reference in seen:
                    raise ValueError("non-progressing acquisition continuation")
                seen.add(reference)
                with measure(rows, "repeat_continuation" if trial == "repeat" else "continuation",
                             case_id=request["case_id"]) as row:
                    page = service.read(repo, reference, ensure_fresh=True)
                    row["usage"] = page.get("usage")
                append(page)
                continuations += 1
                reference = page.get("next_source_ref") if not page["complete"] else None
                if not page["complete"] and not reference:
                    raise ValueError("incomplete acquisition source without continuation")
        query_row = {"query": query, "packet_start": start, "packet_end": len(packets)}
        if semantic:
            query_row["operation"] = "semantic_context"
        queries.append(query_row)
        asked.append(query)
    return packets, {"queries": queries, "termination": reason,
        "continuation_calls": continuations, "source_bytes": source_bytes, "output_bytes": output_bytes,
        "soft_byte_limit_overshoot": {"source_bytes": max(0, source_bytes - limits["source_bytes"]),
                                      "output_bytes": max(0, output_bytes - limits["output_bytes"])}}


def worker(config_path: Path) -> int:
    """One fresh process per condition/repetition, importing ONLY its candidate src."""
    started = time.perf_counter_ns()
    config = json.loads(config_path.read_text())
    implementation = Path(config["implementation"])
    sys.path.insert(0, str(implementation / "src"))
    rows: list[dict] = []
    report: dict = {"status": "incomplete", "phases": rows, "cases": [], "indexes": {}}
    output = Path(config["artifacts"])
    demand = config.get("architecture") == "demand"
    graph_free = config.get("architecture") in {"graph-free", "demand"}
    acquisition = config.get("operation") == "acquisition"
    try:
        with measure(rows, "runtime_setup"):
            if graph_free:
                if demand:
                    from loci.demand_semantics import DemandSource
                    import loci.demand_semantics
                    service = DemandSource(Path(config["store"]) / config["namespace"])
                    loaded = Path(loci.demand_semantics.__file__).resolve()
                else:
                    from loci.graph_free import GraphFreeSource
                    import loci.graph_free
                    service = GraphFreeSource(Path(config["store"]) / config["namespace"])
                    loaded = Path(loci.graph_free.__file__).resolve()
                resolution = {"base_dir": config["store"], "namespace": config["namespace"],
                              "store_id": config["namespace"]}
            else:
                from loci import service
                from loci.storage.store_identity import bind_mcp_store
                from loci.storage.store_resolver import activate_mcp_store
                activate_mcp_store(bind_mcp_store())
                loaded = Path(service.__file__).resolve()
                resolution = service.get_store_resolution().to_dict()
            if not loaded.is_relative_to(implementation / "src"):
                raise ValueError(f"candidate import escaped implementation: {loaded}")
            if (Path(resolution["base_dir"]).resolve() != Path(config["store"]).resolve()
                    or resolution.get("namespace") != config["namespace"]):
                raise ValueError("runtime store binding differs from experiment")
            report["binding"] = resolution
            report["service_source"] = str(loaded)
            report["pid"] = os.getpid()
            report["python"] = sys.version
            report["dependencies"] = sorted((d.metadata["Name"], d.version)
                                                for d in importlib.metadata.distributions())
        inventories = {}
        for snapshot, path in config["snapshots"].items():
            repo = Path(path)
            with measure(rows, "indexing", snapshot=snapshot) as measurement:
                measurement["work"] = service.index_repo(repo) if graph_free else service.index_repo(repo, incremental=False)
            store = None if graph_free else service.get_store()
            # Nongit source exports must retain their identity despite living
            # below a worktree. Never use the implementation checkout as input.
            canonical = str(repo.resolve()) if graph_free else store._canonical_repo(str(repo))
            if Path(canonical).resolve() != repo.resolve():
                raise ValueError("fixture canonicalized outside its isolated source root")
            index = service.inventory(repo) if graph_free else store.load(repo)
            if index is None:
                raise ValueError("indexing did not produce an index")
            index_file = output / "indexes" / f"{snapshot}.json.gz"
            index_file.parent.mkdir(parents=True, exist_ok=True)
            index_file.write_bytes(gzip.compress(json.dumps(index, ensure_ascii=False,
                                        separators=(",", ":"), allow_nan=False).encode(), mtime=0))
            report["indexes"][snapshot] = str(index_file.relative_to(output))
            if acquisition:
                with measure(rows, "discovery", snapshot=snapshot):
                    hashes = dict(index.get("file_hashes", {}))
                    if not graph_free:
                        hashes.update(index.get("graph", {}).get("input_hashes", {}))
                    inventories[snapshot] = {"schema_version": 1, "files": {
                        name: {"sha256": value, "size": (repo / name).stat().st_size}
                        for name, value in sorted(hashes.items()) if (repo / name).is_file()}}
                    write(output / "inventories" / f"{snapshot}.json", inventories[snapshot])
        report["semantic_modules_before_questions"] = sorted(n for n in sys.modules if
            n in {"loci.graph", "loci.parser"} or n.startswith(("loci.graph.", "loci.parser.")))
        report["resources_before_questions"] = usage()
        for request in ([] if config.get("operation") == "exact-source" else config["requests"]):
            repo = Path(config["snapshots"][request["snapshot"]])
            case_id = request["case_id"]
            if acquisition:
                packets, trace = acquire(service, repo, request, inventories[request["snapshot"]], rows,
                                         graph_free=graph_free, enrichment=config["enrichment"] == "on", demand=demand)
                case_file = output / "packets" / f"{case_id}.json"
                write(case_file, packets)
                case = {"case_id": case_id, "snapshot": request["snapshot"],
                        "packets": str(case_file.relative_to(output)), "acquisition": trace}
                if demand and any(q.get("operation") == "semantic_context" for q in trace["queries"]):
                    observer = service.semantic_observer()
                    sparse_file = output / "case-indexes" / f"{case_id}.json.gz"
                    sparse_file.parent.mkdir(parents=True, exist_ok=True)
                    sparse_file.write_bytes(gzip.compress(json.dumps(observer["index"], ensure_ascii=False,
                        separators=(",", ":"), allow_nan=False).encode(), mtime=0))
                    case["index"] = str(sparse_file.relative_to(output))
                    case["semantic_work"] = observer["work"]
                if config.get("repeat_queries"):
                    repeated, repeat_trace = acquire(service, repo, request, inventories[request["snapshot"]], rows,
                        graph_free=graph_free, enrichment=config["enrichment"] == "on", demand=demand, trial="repeat")
                    repeat_file = output / "packets" / f"{case_id}.repeat.json"
                    write(repeat_file, repeated)
                    case.update(repeat_packets=str(repeat_file.relative_to(output)), repeat_acquisition=repeat_trace)
                    if demand and any(q.get("operation") == "semantic_context" for q in repeat_trace["queries"]):
                        observer = service.semantic_observer()
                        repeated_index = output / "case-indexes" / f"{case_id}.repeat.json.gz"
                        repeated_index.write_bytes(gzip.compress(json.dumps(observer["index"], ensure_ascii=False,
                            separators=(",", ":"), allow_nan=False).encode(), mtime=0))
                        case.update(repeat_index=str(repeated_index.relative_to(output)), repeat_semantic_work=observer["work"])
                report["cases"].append(case)
                write(output / "worker.json", report)
                continue
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
        report["catalog"] = None if graph_free else service.list_repos()
        report["loaded_semantic_modules"] = sorted(n for n in sys.modules if n in {"loci.graph", "loci.parser", "loci.storage"}
            or n.startswith(("loci.graph.", "loci.parser.", "loci.storage."))) if graph_free else None
        report["status"] = "completed"
    except Exception as exc:
        report.update(status="failed", error=f"{type(exc).__name__}: {exc}", traceback=traceback.format_exc())
    finally:
        report["process_elapsed_ns"] = time.perf_counter_ns() - started
        report["process_resources"] = usage()
        write(output / "worker.json", report)
    return 0 if report["status"] == "completed" else 1


def read_worker(config_path: Path) -> int:
    """Read an already indexed store in a fresh process, with no retrieval warmup."""
    from benchmarks.architecture_reads import locator, errors

    started = time.perf_counter_ns()
    config = json.loads(config_path.read_text())
    implementation = Path(config["implementation"])
    sys.path.insert(0, str(implementation / "src"))
    output = Path(config["artifacts"])
    rows: list[dict] = []
    report: dict = {"status": "incomplete", "phases": rows, "cases": []}
    try:
        with measure(rows, "read_runtime_setup"):
            from loci import service
            from loci.storage.store_identity import bind_mcp_store
            from loci.storage.store_resolver import activate_mcp_store
            import loci.service
            loaded = Path(loci.service.__file__).resolve()
            if not loaded.is_relative_to(implementation / "src"):
                raise ValueError(f"candidate import escaped implementation: {loaded}")
            activate_mcp_store(bind_mcp_store())
            binding = service.get_store_resolution().to_dict()
            if (Path(binding["base_dir"]).resolve() != Path(config["store"]).resolve()
                    or binding["namespace"] != config["namespace"]):
                raise ValueError("read worker store binding differs from experiment")
            report.update(binding=binding, service_source=str(loaded), pid=os.getpid())
        # Benchmark-only observation of the existing service seams. The direct
        # candidate can bypass graph context, yielding zero observed calls.
        report["observed_service_calls"] = {key: 0 for key in (
            "graph_context", "ensure_fresh_index", "index_is_stale", "index_repo_unlocked",
            "store_load", "store_load_source_index", "store_validate_graph_state")}
        for name, key in (("_load_graph_context", "graph_context"),
                          ("ensure_fresh_index", "ensure_fresh_index"),
                          ("_index_is_stale", "index_is_stale"),
                          ("_index_repo_unlocked", "index_repo_unlocked")):
            original = getattr(service, name, None)
            if original is None:
                continue
            def instrumented(*args, _original=original, _key=key, **kwargs):
                report["observed_service_calls"][_key] += 1
                with measure(rows, "diagnostic_" + _key):
                    return _original(*args, **kwargs)
            setattr(service, name, instrumented)
        from loci.storage.index_store import IndexStore
        for name, key in (("load", "store_load"),
                          ("load_source_index", "store_load_source_index"),
                          ("validate_graph_state", "store_validate_graph_state")):
            original = getattr(IndexStore, name, None)
            if original is None:
                continue
            def instrumented_store(self, *args, _original=original, _key=key, **kwargs):
                report["observed_service_calls"][_key] += 1
                with measure(rows, "diagnostic_" + _key):
                    return _original(self, *args, **kwargs)
            setattr(IndexStore, name, instrumented_store)

        def call(repo, reference, phase, case_id, *, fresh=False, expected_error=False):
            with measure(rows, phase, case_id=case_id) as measurement:
                try:
                    result = service.read(repo, reference, ensure_fresh=fresh)
                except service.LociError as exc:
                    if not expected_error:
                        raise
                    result = {"code": exc.code, "message": exc.message, "details": exc.details}
                    measurement["error_code"] = exc.code
                else:
                    if expected_error:
                        raise ValueError(f"negative read unexpectedly succeeded: {phase}")
                    measurement["usage"] = result.get("usage")
                return result

        for request in config["requests"]:
            repo = Path(config["snapshots"][request["snapshot"]])
            report.setdefault("index_file_bytes", {})[request["snapshot"]] = service.get_store()._index_path(repo).stat().st_size
            file = request["file"]
            raw = (repo / file).read_bytes()
            if hashlib.sha256(raw).hexdigest() != request["sha256"] or len(raw) != request["size"]:
                raise ValueError("read source changed since request preparation")
            reference = locator(repo, file, raw)
            case_id = request["case_id"]
            first = call(repo, reference, "first_read", case_id, fresh=True)
            repeat = call(repo, reference, "repeat_read", case_id, fresh=True)
            without_refresh = call(repo, reference, "read_without_refresh", case_id)
            pages = [first]
            seen = {reference}
            next_ref = first["next_source_ref"]
            while next_ref is not None:
                if next_ref in seen:
                    raise ValueError("non-progressing read continuation")
                seen.add(next_ref)
                page = call(repo, next_ref, "read_continuation", case_id, fresh=True)
                pages.append(page)
                next_ref = page["next_source_ref"]
            negatives = {}
            if request["negatives"]:
                negatives = {name: call(repo, ref, "read_expected_error", case_id,
                                       expected_error=True) for name, ref in errors(repo, file, raw)}
                # Change the source only within this worker, then restore exact bytes.
                # The outer runner verifies every frozen snapshot after the worker exits.
                path = repo / file
                try:
                    path.write_bytes(raw + b"\n")
                    negatives["stale"] = call(repo, reference, "read_expected_error", case_id,
                                               expected_error=True)
                    negatives["stale_refresh"] = call(repo, reference, "read_expected_error", case_id,
                                                       fresh=True, expected_error=True)
                finally:
                    path.write_bytes(raw)
                    with measure(rows, "freshness_restore", case_id=case_id) as measurement:
                        measurement["work"] = service.ensure_fresh_index(repo)
                outside = Path(config["store"]) / f"outside-{case_id}.txt"
                outside.parent.mkdir(parents=True, exist_ok=True)
                outside.write_bytes(raw)
                try:
                    path.unlink()
                    path.symlink_to(outside)
                    negatives["outside_symlink"] = call(repo, reference, "read_expected_error", case_id,
                                                        expected_error=True)
                finally:
                    path.unlink(missing_ok=True)
                    path.write_bytes(raw)
                    outside.unlink(missing_ok=True)
            case_file = output / "packets" / f"{case_id}.json"
            write(case_file, {"pages": pages, "repeat": repeat, "without_refresh": without_refresh,
                              "negatives": negatives})
            report["cases"].append({"case_id": case_id, "snapshot": request["snapshot"],
                                    "packets": str(case_file.relative_to(output))})
            write(output / "reader.json", report)
        report["store_bytes"] = tree_bytes(Path(config["store"]))
        report["cache_bytes"] = tree_bytes(Path(os.environ["XDG_CACHE_HOME"]))
        report["status"] = "completed"
    except Exception as exc:
        report.update(status="failed", error=f"{type(exc).__name__}: {exc}", traceback=traceback.format_exc())
    finally:
        report["process_elapsed_ns"] = time.perf_counter_ns() - started
        report["process_resources"] = usage()
        write(output / "reader.json", report)
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
            terminal = resource.getrusage(resource.RUSAGE_CHILDREN)
            write(log.with_suffix(".execution.json"), {
                "exit_code": process.returncode, "elapsed_ns": time.perf_counter_ns() - started,
                "user_cpu_s": terminal.ru_utime - before.ru_utime,
                "system_cpu_s": terminal.ru_stime - before.ru_stime,
            })
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
                values = {"anchor_selected": int(item["anchor_selection"]["selected"]),
                        "gold_spans_covered": item["source_coverage"]["covered"],
                        "gold_spans_required": item["source_coverage"]["required"],
                        "relationships_available": item["relationships"]["available_dependency_links_total"],
                        "relationships_delivered": item["relationships"]["delivered_dependency_links_total"],
                        "relationships_required": item["relationships"]["required_semantic_dependencies_total"],
                        "forbidden_relationships": item["negative_cases"]["forbidden_proven_relationships"]}
                if "acquisition" in item:
                    values.update(anchor_source_acquired=int(item["acquisition"]["anchor_source_acquired"]),
                        initial_gold_spans_covered=item["acquisition"]["initial_source_coverage"]["covered"],
                        session_relationships_delivered=item["session_relationships"]["delivered_dependency_links_total"])
                return values
            a_values, b_values = values(a), values(b)
            delta = {k: b_values[k] - a_values[k] for k in a_values}
            regressed = any(delta[k] < 0 for k in ("anchor_selected", "gold_spans_covered", "relationships_available", "relationships_delivered")) or delta["forbidden_relationships"] > 0
            dimensions.append({"case_id": a["case_id"], "control": a_values, "variant": b_values,
                               "delta_variant_minus_control": delta, "capability_regression": regressed,
                               "source_acquisition_regression": (delta["gold_spans_covered"] < 0 or
                                   delta.get("anchor_source_acquired", 0) < 0),
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


def read_comparisons(output: Path, runs: list[dict]) -> list[dict]:
    from benchmarks.architecture_reads import comparable

    pairs = []
    for control in (r for r in runs if r["arm"] == "control"):
        variant = next((r for r in runs if r["arm"] == "variant"
                        and r["repetition"] == control["repetition"] and r["suite"] == control["suite"]), None)
        if variant is None or any(r["status"] != "completed" for r in (control, variant)):
            pairs.append({"control": control["id"], "status": "unavailable"})
            continue
        left = json.loads((output / control["capability"]).read_text())
        right = json.loads((output / variant["capability"]).read_text())
        if left != right:
            pairs.append({"control": control["id"], "variant": variant["id"],
                          "status": "different_verified_source"})
            continue
        equivalent = True
        control_config = json.loads((output / control["capability"]).parent.joinpath("config.json").read_text())
        variant_config = json.loads((output / variant["capability"]).parent.joinpath("config.json").read_text())
        for a_case, b_case in zip(control["cases"], variant["cases"], strict=True):
            if a_case["case_id"] != b_case["case_id"]:
                raise ValueError("paired direct-read inventories differ")
            a = json.loads((output / a_case["packets"]).read_text())
            b = json.loads((output / b_case["packets"]).read_text())
            if comparable(a, Path(control_config["snapshots"][a_case["snapshot"]])) != comparable(
                    b, Path(variant_config["snapshots"][b_case["snapshot"]])):
                equivalent = False
        performance = {}
        for phase in sorted(set(control["phase_totals"]) | set(variant["phase_totals"])):
            a = control["phase_totals"].get(phase)
            b = variant["phase_totals"].get(phase)
            performance[phase] = {"control": a, "variant": b,
                                  "elapsed_delta_ns": b["elapsed_ns"] - a["elapsed_ns"] if a and b else None}
        pairs.append({"control": control["id"], "variant": variant["id"],
                      "status": "compared" if equivalent else "different_output",
                      "exact_output_equivalent": equivalent, "performance": performance})
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


def acquisition_scores(corpus: dict, snapshots: dict, artifacts: Path, worker_result: dict,
                       *, demand: bool, repeat: bool = False) -> list[dict]:
    """Same retained-source observer for execution and independent replay."""
    from benchmarks.architecture_cases import score_acquisition
    scores = []
    for case in worker_result["cases"]:
        packets = json.loads((artifacts / case["repeat_packets" if repeat else "packets"]).read_text())
        index_path = case.get("repeat_index" if repeat else "index", worker_result["indexes"][case["snapshot"]])
        index = read_index(artifacts / index_path)
        validate_packets(packets)
        inventory = json.loads((artifacts / "inventories" / f"{case['snapshot']}.json").read_text())
        trace = case["repeat_acquisition" if repeat else "acquisition"]
        repo = Path(snapshots[case["snapshot"]])
        scored = score_acquisition(corpus, case["case_id"], repo,
                                   index, packets, trace, inventory, demand=demand)
        if demand:
            from benchmarks.architecture_structural import validate_structural
            violations = validate_structural(index, packets, repo)
            count = sum(r["edge"]["type"] in {"imports", "imports_type"}
                for packet in packets for r in packet["structuredContent"].get("relationships", []))
            scored["structural_proof"] = {"claims": count,
                "verified": count if not violations else None, "violations": violations,
                "qualification": "structural proof is separate from authored semantic dependency credit"}
            if violations:
                scored["integrity_ok"] = scored["acquisition_integrity_ok"] = False
                scored["output_integrity"]["passed"] = False
                scored["output_integrity"]["failures"].extend(violations)
        scores.append(scored)
    return scores


def run(args) -> int:
    from benchmarks.architecture_cases import load_suite, prepare_snapshots, verify_snapshots, requests, score
    from benchmarks.architecture_reads import requests as read_requests, check_case
    from benchmarks.architecture_cases import score_acquisition

    operation = getattr(args, "operation", "retrieval")
    if operation == "exact-source" and not getattr(args, "mechanism", None):
        raise ValueError("exact-source requires --mechanism")

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
              "operation": operation,
              "mechanism": (args.mechanism if operation in {"exact-source", "acquisition"} else
                            "graph enrichment; both conditions retain full graph indexing and storage"),
              "graph_free": False,
              "limits": ["source delivery is not agent task correctness", "single runs are descriptive, not significance tests",
                         "OS filesystem/provider caches are not claimed cold", "phase RSS is the process lifetime high-water mark",
                         "deterministic continuation hydrates selected incomplete items only"],
              "primary_before": before}
    report["architectures"] = {arm: getattr(args, arm + "_architecture", "graph") for arm in ("control", "variant")}
    if operation != "acquisition" and any(a != "graph" for a in report["architectures"].values()):
        raise ValueError("graph-free candidate requires explicit acquisition observer")
    report["graph_free"] = report["architectures"] if operation == "acquisition" else False
    report["repeat_queries"] = bool(getattr(args, "repeat_queries", False))
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
        if not corpora:
            raise ValueError("experiment must contain at least one case")
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
                    assigned = (read_requests(snapshots, getattr(args, "read_file", None) or [],
                                              negatives=getattr(args, "read_negatives", False))
                                if operation == "exact-source" else requests(corpus))
                    config = {"implementation": str(implementation), "revision": refs[arm],
                              "operation": operation,
                              "repeat_queries": report["repeat_queries"],
                              "architecture": report["architectures"][arm],
                              "enrichment": "on" if operation == "exact-source" else getattr(args, arm + "_enrichment"), "store": str(store),
                              "namespace": namespace, "snapshots": snapshots,
                              "artifacts": str(artifacts), "requests": assigned}
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
                    if operation == "exact-source":
                        read_execution = run_process([sys.executable, "-B", str(Path(__file__).resolve()),
                                                      "_read_worker", str(config_path)], implementation, env,
                                                     artifacts / "read-process.log")
                        entry["read_execution"] = read_execution
                        verify_snapshots(corpus, snapshots)  # reject unrestored error probes or candidate writes
                        reader_path = artifacts / "reader.json"
                        if not reader_path.exists():
                            entry.update(status="failed", error="read worker did not retain a terminal receipt")
                            continue
                        reader = json.loads(reader_path.read_text())
                        entry["index_process_resources"] = entry["process_resources"]
                        entry["process_resources"] = reader.get("process_resources")
                        entry["phase_totals"].update(summarize(
                            [row for row in reader["phases"] if not row["phase"].startswith("diagnostic_")] ))
                        entry["diagnostic_phase_totals"] = summarize(
                            [row for row in reader["phases"] if row["phase"].startswith("diagnostic_")])
                        entry["observed_service_calls"] = reader.get("observed_service_calls")
                        entry["index_file_bytes"] = reader.get("index_file_bytes")
                        entry["store_bytes"] = reader.get("store_bytes")
                        entry["cache_bytes"] = reader.get("cache_bytes")
                        if read_execution["exit_code"] != 0 or reader["status"] != "completed":
                            entry.update(status="failed", error=reader.get("error", "nonzero read worker exit"))
                            continue
                        result = reader
                    if [r["case_id"] for r in result["cases"]] != [r["case_id"] for r in config["requests"]]:
                        raise ValueError("incomplete or reordered request inventory")
                    binding = result["binding"]
                    if (Path(binding["base_dir"]) != store or binding["namespace"] != namespace
                            or result["service_source"] != str(implementation / "src/loci" /
                                ({"graph-free": "graph_free.py", "demand": "demand_semantics.py"}.get(
                                    config["architecture"], "service.py")))):
                        raise ValueError("worker implementation/store identity mismatch")
                    entry["binding"] = binding
                    entry["cases"] = [{"case_id": case["case_id"], "snapshot": case["snapshot"],
                                       "packets": str((artifacts / case["packets"]).relative_to(output))}
                                      for case in result["cases"]] if operation == "exact-source" else []
                    scores = []
                    for case in ([] if operation == "acquisition" else result["cases"]):
                        packets = json.loads((artifacts / case["packets"]).read_text())
                        if operation == "exact-source":
                            request = next(r for r in config["requests"] if r["case_id"] == case["case_id"])
                            scores.append(check_case(Path(snapshots[case["snapshot"]]), request, packets))
                        else:
                            index = read_index(artifacts / result["indexes"][case["snapshot"]])
                            validate_packets(packets)
                            scores.append(score(corpus, case["case_id"], Path(snapshots[case["snapshot"]]), index, packets))
                    if operation == "acquisition":
                        with measure(report.setdefault("observer_phases", []), "proof_validation", run_id=label, trial="first"):
                            scores = acquisition_scores(corpus, snapshots, artifacts, result,
                                                        demand=config["architecture"] == "demand")
                    write(artifacts / "capability.json", scores)
                    entry["capability"] = str((artifacts / "capability.json").relative_to(output))
                    repeated_scores = []
                    if operation == "acquisition" and config["repeat_queries"]:
                        with measure(report["observer_phases"], "proof_validation", run_id=label, trial="repeat"):
                            repeated_scores = acquisition_scores(corpus, snapshots, artifacts, result,
                                demand=config["architecture"] == "demand", repeat=True)
                        write(artifacts / "repeat-capability.json", repeated_scores)
                        entry["repeat_capability"] = str((artifacts / "repeat-capability.json").relative_to(output))
                        entry["repeat_legacy_packet_invalid_cases"] = [s["case_id"] for s in repeated_scores if not s["integrity_ok"]]
                    entry["legacy_packet_invalid_cases"] = [item["case_id"] for item in scores if not item["integrity_ok"]]
                    invalid_cases = [item["case_id"] for item in scores + repeated_scores if not item.get("acquisition_integrity_ok", item["integrity_ok"])]
                    if invalid_cases:
                        entry.update(status="invalid", invalid_cases=invalid_cases,
                                     error="independent source/output/proof integrity check failed")
        if len(report["runs"]) != 2 * args.repetitions * len(corpora):
            raise ValueError("assigned comparison inventory is incomplete")
        bindings = [r["binding"] for r in report["runs"] if "binding" in r]
        for key in ("base_dir", "namespace", "store_id"):
            if len({b[key] for b in bindings}) != len(bindings):
                raise ValueError(f"conditions share {key}")
        report["comparisons"] = (read_comparisons(output, report["runs"]) if operation == "exact-source"
                                 else comparisons(output, report["runs"]))
        report["status"] = ("invalid" if any(r["status"] == "invalid" for r in report["runs"]) or
                            any(p["status"] in {"different_verified_source", "different_output"} for p in report["comparisons"]) else
                            "completed" if all(r["status"] == "completed" for r in report["runs"]) and
                            all(p["status"] == "compared" for p in report["comparisons"]) else "failed")
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
    from benchmarks.architecture_reads import check_case
    from benchmarks.architecture_cases import score_acquisition
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
            direct = result.get("operation") == "exact-source"
            worker_result = json.loads((artifacts / ("reader.json" if direct else "worker.json")).read_text())
            if [case["case_id"] for case in worker_result["cases"]] != [request["case_id"] for request in config["requests"]]:
                raise ValueError("retained read request inventory differs from worker receipt")
            actual = []
            for case in ([] if result.get("operation") == "acquisition" else worker_result["cases"]):
                packets = json.loads((artifacts / case["packets"]).read_text())
                if direct:
                    request = next(r for r in config["requests"] if r["case_id"] == case["case_id"])
                    actual.append(check_case(Path(snapshots[case["snapshot"]]), request, packets))
                else:
                    index = read_index(artifacts / worker_result["indexes"][case["snapshot"]])
                    validate_packets(packets)
                    actual.append(score(corpus, case["case_id"], Path(snapshots[case["snapshot"]]), index, packets))
                count += 1
            if result.get("operation") == "acquisition":
                actual = acquisition_scores(corpus, snapshots, artifacts, worker_result,
                                            demand=config["architecture"] == "demand")
                count += len(actual)
                if config.get("repeat_queries"):
                    repeated = acquisition_scores(corpus, snapshots, artifacts, worker_result,
                                                  demand=config["architecture"] == "demand", repeat=True)
                    if repeated != json.loads((artifacts / "repeat-capability.json").read_text()):
                        raise ValueError("independent repeated-query capability replay differs")
                    count += len(repeated)
            if actual != json.loads((artifacts / "capability.json").read_text()):
                raise ValueError("independent capability replay differs")
        if result.get("operation") == "acquisition" and comparisons(output, result["runs"]) != result["comparisons"]:
            raise ValueError("independent acquisition comparison replay differs")
        if result.get("operation") == "exact-source" and read_comparisons(output, result["runs"]) != result["comparisons"]:
            raise ValueError("independent exact-read comparison replay differs")
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
    execution.add_argument("--operation", choices=("retrieval", "exact-source", "acquisition"), default="retrieval")
    execution.add_argument("--control-architecture", choices=("graph", "graph-free", "demand"), default="graph")
    execution.add_argument("--variant-architecture", choices=("graph", "graph-free", "demand"), default="graph")
    execution.add_argument("--repeat-queries", action="store_true", help="repeat each acquisition sequence in the same worker and retain separate costs/proofs")
    execution.add_argument("--mechanism", help="actual mechanism under comparison, recorded in result metadata")
    execution.add_argument("--read-file", action="append", help="exact-source snapshot:relative/path; repeatable")
    execution.add_argument("--read-negatives", action="store_true", help="run destructive-in-copy error probes on selected small files")
    execution.add_argument("--corpus", action="append")
    execution.add_argument("--repetitions", type=int, default=1)
    execution.add_argument("--case", action="append", help="explicit case scope; repeat to select several")
    replay = commands.add_parser("verify")
    replay.add_argument("--output", required=True, type=Path)
    internal = commands.add_parser("_worker", help="internal isolated worker")
    internal.add_argument("config", type=Path)
    direct_worker = commands.add_parser("_read_worker", help="internal fresh read worker")
    direct_worker.add_argument("config", type=Path)
    args = parser.parse_args()
    if args.command == "_worker":
        if str(ROOT) not in sys.path:
            sys.path.insert(0, str(ROOT))
        return worker(args.config)
    if args.command == "_read_worker":
        if str(ROOT) not in sys.path:
            sys.path.insert(0, str(ROOT))
        return read_worker(args.config)
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
