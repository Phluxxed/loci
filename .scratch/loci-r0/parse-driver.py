"""Disposable R0 experiment: reuse immutable tree-sitter trees per index operation.

Run from this worktree with the primary checkout's .venv and PYTHONPATH=src:.
This file never patches serving source on disk. Each arm gets an isolated store.
"""
from __future__ import annotations

import argparse
from collections import Counter
from contextlib import contextmanager
import gc
import hashlib
import json
import os
from pathlib import Path
import tempfile
import time
import tracemalloc
from typing import Any

from benchmarks.multilingual_context_inputs import load_inputs
from benchmarks.typescript_context_corpus import load_corpus, materialize_snapshot


def _digest(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    ).hexdigest()


def _normalized_packet(value: Any) -> Any:
    """Opaque source-ref IDs are store-local; retain all semantic packet fields."""
    if isinstance(value, dict):
        return {
            k: _normalized_packet(v)
            for k, v in value.items()
            if k not in {"source_ref", "next_source_ref"}
        }
    if isinstance(value, list):
        return [_normalized_packet(v) for v in value]
    return value


def _first_differences(left: Any, right: Any, prefix: str = "", limit: int = 12) -> list[str]:
    if left == right:
        return []
    if limit <= 0:
        return []
    if type(left) is not type(right):
        return [prefix + " (type)"]
    if isinstance(left, dict):
        keys = sorted(set(left) | set(right))
        result: list[str] = []
        for key in keys:
            path = f"{prefix}.{key}" if prefix else key
            if key not in left or key not in right:
                result.append(path + " (missing)")
            else:
                result.extend(_first_differences(left[key], right[key], path, limit - len(result)))
            if len(result) >= limit:
                break
        return result
    if isinstance(left, list):
        if len(left) != len(right):
            return [prefix + f" (length {len(left)} != {len(right)})"]
        result = []
        for i, (a, b) in enumerate(zip(left, right)):
            result.extend(_first_differences(a, b, f"{prefix}[{i}]", limit - len(result)))
            if len(result) >= limit:
                break
        return result
    return [prefix or "<root>"]


class ParseCounter:
    def __init__(self, reuse: bool) -> None:
        self.reuse = reuse
        self.requests = 0
        self.parses = 0
        self.hits = 0
        self.parse_wall_ns = 0
        self.by_grammar: Counter[str] = Counter()
        self.hits_by_grammar: Counter[str] = Counter()
        self.cache: dict[tuple[object, bytes], Any] = {}
        self.cache_source_bytes = 0
        self.grammar_by_language: dict[object, str] = {}

    def grammar(self, language: object) -> str:
        return self.grammar_by_language.get(language, repr(language))

    def wrap(self, parser: Any, grammar: str | None = None) -> Any:
        if getattr(parser, "_r0_parse_facade", False):
            if grammar is not None:
                self.grammar_by_language[parser.language] = grammar
            return parser
        language = parser.language
        if language is None:
            raise RuntimeError("parser has no language")
        if grammar is not None:
            self.grammar_by_language[language] = grammar
        counter = self

        class Facade:
            _r0_parse_facade = True

            def parse(self, source: bytes, *args: Any, **kwargs: Any) -> Any:
                # Current Loci consumers make only one-argument full parses.
                # Refuse changed parser semantics rather than caching unsafely.
                if not isinstance(source, bytes) or args or kwargs:
                    raise RuntimeError("unexpected parse signature in R0 experiment")
                label = counter.grammar(language)
                counter.requests += 1
                counter.by_grammar[label] += 1
                key = (language, source)
                if counter.reuse and key in counter.cache:
                    counter.hits += 1
                    counter.hits_by_grammar[label] += 1
                    return counter.cache[key]
                start = time.perf_counter_ns()
                tree = parser.parse(source)
                counter.parse_wall_ns += time.perf_counter_ns() - start
                counter.parses += 1
                if counter.reuse:
                    counter.cache[key] = tree
                    counter.cache_source_bytes += len(source)
                return tree

            def __getattr__(self, name: str) -> Any:
                return getattr(parser, name)

        return Facade()

    def summary(self) -> dict[str, Any]:
        return {
            "requests": self.requests,
            "actual_parses": self.parses,
            "hits": self.hits,
            "parse_wall_seconds": self.parse_wall_ns / 1e9,
            "by_grammar": dict(sorted(self.by_grammar.items())),
            "hits_by_grammar": dict(sorted(self.hits_by_grammar.items())),
            "cache_entries_at_end": len(self.cache),
            "cache_source_bytes_at_end": self.cache_source_bytes,
        }


@contextmanager
def instrument_parsers(reuse: bool):
    import tree_sitter
    import tree_sitter_language_pack

    original_parser = tree_sitter.Parser
    original_get_parser = tree_sitter_language_pack.get_parser
    counter = ParseCounter(reuse)

    def parser_factory(*args: Any, **kwargs: Any) -> Any:
        return counter.wrap(original_parser(*args, **kwargs))

    def get_parser_factory(grammar: str) -> Any:
        return counter.wrap(original_get_parser(grammar), grammar)

    tree_sitter.Parser = parser_factory
    tree_sitter_language_pack.get_parser = get_parser_factory
    try:
        yield counter
    finally:
        tree_sitter.Parser = original_parser
        tree_sitter_language_pack.get_parser = original_get_parser
        counter.cache.clear()


@contextmanager
def isolated_store(base_dir: Path):
    before = os.environ.get("LOCI_BASE_DIR")
    os.environ["LOCI_BASE_DIR"] = str(base_dir)
    try:
        yield
    finally:
        if before is None:
            os.environ.pop("LOCI_BASE_DIR", None)
        else:
            os.environ["LOCI_BASE_DIR"] = before


def run_arm(
    repo: Path,
    store_dir: Path,
    *,
    reuse: bool,
    query: str | None,
) -> tuple[dict[str, Any], dict[str, Any], Any | None]:
    from loci.service import index_repo, retrieve
    from loci.storage.index_store import IndexStore

    gc.collect()
    tracemalloc.start()
    tracemalloc.reset_peak()
    before_heap = tracemalloc.get_traced_memory()[0]
    with isolated_store(store_dir):
        start_wall = time.perf_counter()
        start_cpu = time.process_time()
        with instrument_parsers(reuse) as counter:
            result = index_repo(repo, incremental=False)
            parse = counter.summary()
        wall = time.perf_counter() - start_wall
        cpu = time.process_time() - start_cpu
        _, peak_heap = tracemalloc.get_traced_memory()
        index = IndexStore(base_dir=store_dir).load(repo.resolve())
        assert index is not None
        packet = retrieve(repo, query, ensure_fresh=False) if query is not None else None
    tracemalloc.stop()
    metrics = {
        "arm": "reuse" if reuse else "control",
        "index_wall_seconds": wall,
        "index_cpu_seconds": cpu,
        "python_heap_peak_delta_bytes": max(0, peak_heap - before_heap),
        "parse": parse,
        "index_sha256": _digest(index),
        "packet_normalized_sha256": _digest(_normalized_packet(packet)) if packet else None,
        "symbols": len(index["symbols"]),
        "edges": len(index["graph"]["edges"]),
        "index_output": {k: v for k, v in result.items() if k not in {"path", "graph_diagnostics", "coverage"}},
    }
    return metrics, index, packet


def fixture_corpora() -> list[tuple[str, dict[str, Any]]]:
    multilingual, _ = load_inputs()
    typescript = load_corpus(Path("benchmarks/corpora/typescript-context-v3"))
    return [("multi", multilingual), ("ts", typescript)]


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--limit", type=int, default=0, help="0 runs all frozen snapshots")
    p.add_argument("--repeat", type=int, default=1)
    p.add_argument("--edge-only", action="store_true")
    p.add_argument("--packet-snapshots", default="python_contracts,javascript_dependencies,go_contracts,rust_contracts,tsx_props,markdown_navigation,imported_interface,anvil")
    args = p.parse_args()
    output = args.output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    packets = set(args.packet_snapshots.split(","))
    rows: list[dict[str, Any]] = []
    diffs: list[dict[str, Any]] = []

    with tempfile.TemporaryDirectory(prefix="loci-r0-parse-") as temp:
        root = Path(temp)
        for group, corpus in ([] if args.edge_only else fixture_corpora()):
            snapshots = list(corpus["snapshots"])
            if args.limit:
                snapshots = snapshots[:args.limit]
            for snapshot in snapshots:
                repo = root / "repos" / group / snapshot
                materialize_snapshot(corpus, snapshot, repo)
                case = next((c for c in corpus["cases"] if c["snapshot"] == snapshot), None)
                query = case["prompt"] if snapshot in packets and case else None
                for repetition in range(args.repeat):
                    # The first pair is always control then candidate. A second
                    # pair reverses order to expose cache/order sensitivity.
                    order = (False, True) if repetition % 2 == 0 else (True, False)
                    pair: dict[str, tuple[dict[str, Any], dict[str, Any], Any | None]] = {}
                    for reuse in order:
                        arm = "reuse" if reuse else "control"
                        store = root / "stores" / group / snapshot / str(repetition) / arm
                        metrics, index, packet = run_arm(repo, store, reuse=reuse, query=query)
                        metrics.update(group=group, snapshot=snapshot, repetition=repetition)
                        rows.append(metrics)
                        pair[arm] = (metrics, index, packet)
                        print(f"{group}/{snapshot} rep={repetition} {arm}: "
                              f"{metrics['index_wall_seconds']:.3f}s "
                              f"parse={metrics['parse']['actual_parses']}/{metrics['parse']['requests']}",
                              flush=True)
                    a, b = pair["control"], pair["reuse"]
                    index_diffs = _first_differences(a[1], b[1])
                    packet_diffs = _first_differences(
                        _normalized_packet(a[2]), _normalized_packet(b[2])
                    ) if query else []
                    diffs.append({
                        "group": group, "snapshot": snapshot, "repetition": repetition,
                        "index_equal": not index_diffs, "index_diff_paths": index_diffs,
                        "packet_equal": not packet_diffs if query else None,
                        "packet_diff_paths": packet_diffs,
                    })
                    if index_diffs or packet_diffs:
                        print(f"DIFF {group}/{snapshot}: {index_diffs} {packet_diffs}", flush=True)
        # Deliberate malformed and invalid-UTF8 files exercise the same index
        # path, including error diagnostics and graph validation.
        repo = root / "repos" / "edge_cases"
        repo.mkdir(parents=True)
        (repo / "broken.ts").write_bytes(b"type Broken = {\n")
        (repo / "invalid.py").write_bytes(b"def bad():\n    return \xff\n")
        (repo / "valid.py").write_bytes(b"def keep() -> int:\n    return 1\n")
        (repo / "Package.swift").write_text(
            'let package = Package(name: "Feature", targets: [.target(name: "Feature")])\n'
        )
        swift_source = repo / "Sources" / "Feature" / "Thing.swift"
        swift_source.parent.mkdir(parents=True)
        swift_source.write_text("import Foundation\nstruct Thing { func run() {} }\n")
        pair = {}
        for reuse in (False, True):
            arm = "reuse" if reuse else "control"
            metrics, index, packet = run_arm(
                repo, root / "stores" / "edge_cases" / arm,
                reuse=reuse, query="keep",
            )
            metrics.update(group="edge_cases", snapshot="malformed_utf8", repetition=0)
            rows.append(metrics)
            pair[arm] = (metrics, index, packet)
        a, b = pair["control"], pair["reuse"]
        index_diffs = _first_differences(a[1], b[1])
        packet_diffs = _first_differences(_normalized_packet(a[2]), _normalized_packet(b[2]))
        diffs.append({
            "group": "edge_cases", "snapshot": "malformed_utf8", "repetition": 0,
            "index_equal": not index_diffs, "index_diff_paths": index_diffs,
            "packet_equal": not packet_diffs, "packet_diff_paths": packet_diffs,
            "diagnostic_codes": [d["code"] for d in a[1]["graph"]["diagnostics"]],
        })
    report = {
        "schema_version": 1,
        "experiment": "tree_reuse_exact_grammar_and_bytes_per_index_operation",
        "source_commit": "f41b3eaa4c7871c68972de5f760572a6bcbe1760",
        "rows": rows,
        "diffs": diffs,
        "scope": {
            "operation": "one index_repo call",
            "cache_key": "tree-sitter Language equality and exact source bytes",
            "cache_cleared_after_operation": True,
            "python_heap_peak_delta_excludes_c_allocations": True,
            "ast_walks_unchanged": True,
        },
    }
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(f"wrote {output}; pairs={len(diffs)}; failures="
          f"{sum(not d['index_equal'] or d['packet_equal'] is False for d in diffs)}")


if __name__ == "__main__":
    main()
