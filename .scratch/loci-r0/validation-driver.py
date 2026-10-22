"""R0 disposable experiment: repeated graph validation vs content-keyed reuse.

No product edits. Same freshness, source read, proof, and error paths. The cache
keys every validation input, keeps one private state, and copies it on reuse.
"""
from __future__ import annotations

from collections import Counter
import copy
import cProfile
import hashlib
import io
import json
import os
from pathlib import Path
import platform
import pstats
import sys
import time

from benchmarks.typescript_context_corpus import load_corpus, materialize_snapshot
from loci import service
from loci.storage.index_store import IndexStore


ROOT = Path(__file__).resolve().parent
OUT = ROOT.parents[1] / ".scratch/loci-r0/validation"
OUT.mkdir(parents=True, exist_ok=True)
DATA = ROOT / ".r0-data"
DATA.mkdir(exist_ok=True)
CORPUS = load_corpus(ROOT / "benchmarks/corpora/typescript-context-v3")
ORIGINAL_VALIDATE = IndexStore.validate_graph_state
ORIGINAL_LOAD = IndexStore.load
ORIGINAL_SCAN = service._scan_repository_files
COUNTS = Counter()
MODE = "control"
CACHED_KEY = None
CACHED_STATE = None


def validate(self, index):
    global CACHED_KEY, CACHED_STATE
    COUNTS["validation_requests"] += 1
    if MODE == "reuse":
        raw = json.dumps({k: index.get(k) for k in ("symbols", "file_hashes", "graph")},
                         sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()
        COUNTS["cache_key_bytes"] += len(raw)
        key = hashlib.sha256(raw).digest()
        if key == CACHED_KEY:
            COUNTS["cache_hits"] += 1
            # A caller cannot mutate the private validated state.
            return copy.deepcopy(CACHED_STATE)
        COUNTS["cache_misses"] += 1
        state = ORIGINAL_VALIDATE(self, index)
        COUNTS["full_validations"] += 1
        CACHED_KEY, CACHED_STATE = key, copy.deepcopy(state)
        return state
    COUNTS["full_validations"] += 1
    return ORIGINAL_VALIDATE(self, index)


def load(self, repo):
    COUNTS["index_loads"] += 1
    return ORIGINAL_LOAD(self, repo)


def scan(*args, **kwargs):
    COUNTS["repository_scans"] += 1
    return ORIGINAL_SCAN(*args, **kwargs)


def measure(operation):
    COUNTS.clear()
    wall, cpu = time.perf_counter(), time.process_time()
    value = operation()
    return value, {"wall_ms": (time.perf_counter() - wall) * 1000,
                   "cpu_ms": (time.process_time() - cpu) * 1000,
                   "counts": dict(COUNTS)}


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                     separators=(",", ":")).encode()).hexdigest()


def save(name, value):
    (OUT / name).write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def experiment():
    global MODE, CACHED_KEY, CACHED_STATE
    IndexStore.validate_graph_state, IndexStore.load = validate, load
    service._scan_repository_files = scan
    results = {"source_commit": "f41b3eaa4c7871c68972de5f760572a6bcbe1760",
               "source_file": service.__file__, "python": sys.version,
               "platform": platform.platform(), "fixtures": [],
               "interpretation": "Full fresh service route; no model execution or task correctness score."}
    for snapshot in ("imported_interface", "anvil"):
        repo = DATA / snapshot
        materialize_snapshot(CORPUS, snapshot, repo)
        os.environ["LOCI_BASE_DIR"] = str(DATA / ("store-" + snapshot))
        os.environ["LOCI_STORE_NAMESPACE"] = "r0-validation"
        MODE = "control"
        index_result, cold = measure(lambda: service.index_repo(repo, incremental=False))
        _, nochange = measure(lambda: service.index_repo(repo, incremental=True))
        store = service.get_store()
        index = store.load(repo)
        case = next(c for c in CORPUS["cases"] if c["snapshot"] == snapshot)
        anchor = next(c for c in case["context"] if c["id"] == case["anchor"])
        symbol = next(s for s in index["symbols"]
                      if s["name"] == anchor["symbol"]["name"]
                      and s["kind"] == anchor["symbol"]["kind"]
                      and s["file_path"] == anchor["file"])
        request = lambda: service.retrieve(repo, seed_ids=[symbol["id"]], ensure_fresh=True)
        packet = request()
        reference = next(i["source_ref"] for i in packet["items"] if i["role"] == "anchor")
        operations = {"retrieve": request,
                      "read": lambda: service.read(repo, reference, ensure_fresh=True)}
        fixture = {"snapshot": snapshot, "files": len(index["file_hashes"]),
                   "symbols": len(index["symbols"]),
                   "edges": len(index["graph"]["edges"]),
                   "semantic_records": {k: len(index["graph"].get(k, [])) for k in
                                        ("imports", "symbol_references", "calls", "type_relations")},
                   "index_json_bytes": store._index_path(repo).stat().st_size,
                   "mirrored_bytes": sum(p.stat().st_size for p in store._sources_dir(repo).rglob("*") if p.is_file()),
                   "cold_index": cold, "nochange_index": nochange, "operations": {}}
        for op_name, operation in operations.items():
            samples = {"control": [], "reuse": []}
            packets = {}
            # Control always established before intervention; alternating order
            # thereafter reduces order drift. Three is the corpus's existing
            # timing repetition count, not an agent budget.
            for arm in ("control", "reuse"):
                MODE = arm
                CACHED_KEY = CACHED_STATE = None
                initial, first = measure(operation)
                packets[arm] = initial
                fixture.setdefault("first_calls", {})[op_name + "/" + arm] = first
            for repeat in range(3):
                for arm in (("control", "reuse") if repeat % 2 == 0 else ("reuse", "control")):
                    MODE = arm
                    value, timing = measure(operation)
                    assert value == packets[arm], "repeated packet changed"
                    samples[arm].append(timing)
            assert packets["control"] == packets["reuse"], "candidate packet changed"
            save(snapshot + "-" + op_name + "-packet.json", packets["control"])
            fixture["operations"][op_name] = {"samples": samples, "identical": True,
                                            "packet_sha256": digest(packets["control"]),
                                            "output_bytes": packets["control"]["usage"]["output_bytes"]}
        MODE = "control"
        profile = cProfile.Profile()
        profile.runcall(operations["read"])
        profile.dump_stats(str(OUT / (snapshot + "-read.prof")))
        stream = io.StringIO()
        pstats.Stats(profile, stream=stream).sort_stats("cumulative").print_stats(35)
        (OUT / (snapshot + "-read-profile.txt")).write_text(stream.getvalue())
        checks = []
        MODE = "reuse"
        valid = store.validate_graph_state(index)
        valid.input_hashes["caller_mutation"] = "not cached"
        assert "caller_mutation" not in store.validate_graph_state(index).input_hashes
        checks.append({"check": "cached-state-private", "pass": True})
        for name, corrupt in (("duplicate-endpoint", copy.deepcopy(index)),
                              ("bad-graph-schema", copy.deepcopy(index))):
            if name == "duplicate-endpoint":
                corrupt["symbols"].append(copy.deepcopy(corrupt["symbols"][0]))
            else:
                corrupt["graph"]["schema_version"] = -1
            errors = []
            for arm in ("control", "reuse"):
                MODE = arm
                try:
                    store.validate_graph_state(corrupt)
                except Exception as exc:
                    errors.append({"type": type(exc).__name__, "code": getattr(exc, "code", None)})
            assert len(errors) == 2 and errors[0] == errors[1]
            checks.append({"check": name, "pass": True, "errors": errors})
        MODE = "reuse"
        # Change the actual selected file without refreshing: old refs must fail.
        source_path = repo / symbol["file_path"]
        before = source_path.read_bytes()
        source_path.write_bytes(before + b"\n// r0 drift\n")
        try:
            service.read(repo, reference)
        except service.LociError as exc:
            assert exc.code == "SOURCE_STALE"
            checks.append({"check": "source-drift", "pass": True, "code": exc.code})
        else:
            raise AssertionError("stale reference accepted")
        finally:
            source_path.write_bytes(before)
        fixture["negative_controls"] = checks
        results["fixtures"].append(fixture)
        save("results.json", results)
        print(snapshot, "complete", flush=True)
    return results


if __name__ == "__main__":
    experiment()
