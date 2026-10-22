"""Disposable R0 fixed-anchor normal retrieval corpus diagnostic."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import tempfile
import time
from pathlib import Path

from benchmarks.multilingual_context_inputs import load_inputs
from benchmarks.multilingual_context_relationships import score_relationships as score_multilingual
from benchmarks.typescript_context_corpus import load_corpus, materialize_snapshot
from benchmarks.typescript_context_explore_relationships import score_relationships as score_typescript
from benchmarks.typescript_context_relationships import _endpoint_table, _proven_edge
from benchmarks.typescript_context_trace import _covered
from loci import retrieval, service
from loci.mcp_output_models import LociRetrieveOutput


def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n")


def packet_hash(packet: dict) -> str:
    # Short source references are deterministic inside a store and are retained.
    return hashlib.sha256(json.dumps(packet, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def validate_packet(packet: dict, repo: Path, expected_files: dict[str, str]) -> list[dict]:
    LociRetrieveOutput.model_validate(packet)
    envelope = {"content": [], "structuredContent": packet, "isError": False}
    encoded = json.dumps(envelope, ensure_ascii=False, separators=(",", ":")).encode()
    assert len(encoded) == packet["usage"]["output_bytes"] <= packet["limits"]["max_output_bytes"]
    spans = []
    ids = set()
    for source in packet["sources"]:
        name = source["file"]
        assert name in expected_files, f"source outside frozen archive: {name}"
        raw = (repo / name).read_bytes()
        assert hashlib.sha256(raw).hexdigest() == expected_files[name] == source["content_hash"]
        start, end = source["start_byte"], source["end_byte"]
        assert type(start) is type(end) is int and 0 <= start < end <= len(raw)
        assert raw[start:end] == source["content"].encode()
        assert source["id"] not in ids
        ids.add(source["id"])
        spans.append({"file": name, "start_byte": start, "end_byte": end, "content": source["content"],
                      "content_hash": source["content_hash"]})
    for relation in packet["relationships"]:
        assert relation["proof"] == "complete" and relation["source_ids"]
        assert all(source_id in ids for source_id in relation["source_ids"])
    return spans


def request_for(case: dict, index: dict) -> tuple[dict | None, dict]:
    anchor = next(context for context in case["context"] if context["id"] == case["anchor"])
    endpoint = _endpoint_table(case, index["symbols"])[case["anchor"]]
    identity = {"gold_context_id": case["anchor"], "file": anchor["file"],
                "symbol": anchor.get("symbol"), "gold_interval": [anchor["start_byte"], anchor["end_byte"]],
                "status": endpoint["status"], "matching_ids": endpoint["symbol_ids"]}
    if endpoint["status"] == "indexed" and len(endpoint["symbol_ids"]) == 1:
        return {"seed_ids": [endpoint["symbol_ids"][0]]}, identity
    if endpoint["status"] == "source_only":
        return {"query": anchor["file"]}, identity
    if case.get("language") == "markdown" and endpoint["status"] == "missing":
        # The current f41b3ea index has no matching section declaration for
        # this frozen Markdown gold; use the exact file request in both arms.
        identity["request_fallback"] = "markdown_exact_file"
        return {"query": anchor["file"]}, identity
    return None, identity


def scored_case(corpus_name: str, case: dict, index: dict, packet: dict, spans: list[dict]) -> dict:
    # The existing scorers consume exploration-shaped proof. This in-memory
    # adapter exposes the unchanged normal packet's relationship/source records.
    # Historical semantic scorers deliberately reject structural imports as
    # non-semantic claims. Normal retrieval legitimately includes those; keep
    # them in the raw packet and validate them separately above.
    capsule = {"intent": "type_dependencies", "sources": packet["sources"],
               "relationships": [relation for relation in packet["relationships"]
                                 if _proven_edge(relation["edge"])]}
    if corpus_name == "typescript":
        relationships = score_typescript(case, index, [capsule])
    else:
        relationships = score_multilingual(case, index, [capsule], spans)
    gold = case["context"]
    hits = [context["id"] for context in gold if _covered(spans, context)]
    return {
        "gold_source_count": len(gold), "covered_gold_source_count": len(hits),
        "covered_gold_source_ids": hits, "all_gold_source_present": len(hits) == len(gold),
        "required_relationship_count": relationships["required_semantic_dependencies_total"],
        "available_relationship_count": relationships["available_dependency_links_total"],
        "delivered_relationship_count": relationships["delivered_dependency_links_total"],
        "precise_kind_links_delivered": relationships.get("precise_kind_links_delivered_total"),
        "forbidden_proven_relationships": relationships["forbidden_proven_relationships"],
        "delivery_integrity_violations": relationships["delivery_integrity_violations"],
        "endpoint_issues": relationships["endpoint_issues"],
        "packet_relationship_count": len(packet["relationships"]),
        "packet_source_count": len(packet["sources"]),
        "packet_item_count": len(packet["items"]),
        "packet_output_bytes": packet["usage"]["output_bytes"],
        "evidence_bytes": packet["usage"]["evidence_bytes"],
        "nodes_examined": packet["usage"]["nodes_examined"],
        "eligible_edges_considered": packet["usage"]["eligible_edges_considered"],
        "edges_traversed": packet["usage"]["edges_traversed"],
        "omissions": packet["omissions"],
        "status": packet["status"],
    }


def run(args: argparse.Namespace) -> None:
    worktree = Path(__file__).resolve().parent
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    archive_root = worktree / "benchmarks" / "corpora" / "typescript-context-v3"
    ts = load_corpus(archive_root)
    multi, _ = load_inputs()
    corpora = {"typescript": ts, "multilingual": multi}
    assert len(ts["cases"]) == 17 and len(multi["cases"]) == 19
    original_lifts = retrieval._ownership_lifts
    raw_path = output / "packets.jsonl"
    rows = []
    setups = []
    with tempfile.TemporaryDirectory(prefix="r0-corpus-", dir=worktree) as scratch:
        temp = Path(scratch)
        os.environ["LOCI_BASE_DIR"] = str(temp / "store")
        os.environ["LOCI_STORE_NAMESPACE"] = "r0-corpus-ablation"
        prepared = {}
        for corpus_name, corpus in corpora.items():
            expected = {key: value["files"] for key, value in corpus["snapshots"].items()}
            for snapshot in corpus["snapshots"]:
                repo = temp / "source" / corpus_name / snapshot
                materialize_snapshot(corpus, snapshot, repo)
                started = time.perf_counter_ns()
                indexed = service.index_repo(repo, incremental=False)
                setup_ms = (time.perf_counter_ns() - started) / 1_000_000
                started_load = time.perf_counter_ns()
                store = service.get_store()
                index = store.load(repo.resolve())
                assert index is not None
                nodes = {node["id"]: node for node in index["symbols"]}
                state = store.validate_graph_state(index)
                coverage = service.query_coverage_from_index(index, "indexed_symbols")["state"]
                load_ms = (time.perf_counter_ns() - started_load) / 1_000_000
                index["repo_path"] = str(repo.resolve())
                prepared[corpus_name, snapshot] = (repo, index, expected[snapshot],
                                                   store, nodes, state, coverage)
                setups.append({"corpus": corpus_name, "snapshot": snapshot, "index_ms": setup_ms,
                               "preload_ms": load_ms, "index_result": indexed,
                               "file_count": len(expected[snapshot])})
                print(f"indexed {corpus_name}/{snapshot} in {setup_ms:.1f} ms", flush=True)
        write_json(output / "setup.json", setups)

        def no_members(source, node, query_terms):
            if node.get("kind") in retrieval._NATIVE_KINDS:
                return ()
            return original_lifts(source, node, query_terms)

        with raw_path.open("w") as raw_file:
            for condition in ("baseline", "intervention"):
                if condition == "intervention" and args.experiment == "ownership":
                    retrieval._ownership_lifts = no_members
                for corpus_name, corpus in corpora.items():
                    for case in corpus["cases"]:
                        repo, index, files, store, nodes, state, coverage = prepared[corpus_name, case["snapshot"]]
                        request, identity = request_for(case, index)
                        row = {"corpus": corpus_name, "case_id": case["id"],
                               "snapshot": case["snapshot"], "condition": condition,
                               "anchor": identity, "request": request, "attempts": []}
                        if request is None:
                            row["error"] = "missing_or_ambiguous_frozen_anchor"
                        else:
                            first_packet = None
                            first_spans = None
                            for repetition in range(1, 4):
                                started_wall = time.perf_counter_ns()
                                started_cpu = time.process_time_ns()
                                try:
                                    packet = retrieval.retrieve_context(
                                        repo, store, nodes, state, request.get("query", ""),
                                        seed_ids=request.get("seed_ids"), coverage=coverage,
                                        graph_enrichment=(condition == "baseline" or args.experiment == "ownership"))
                                    wall_ms = (time.perf_counter_ns() - started_wall) / 1_000_000
                                    cpu_ms = (time.process_time_ns() - started_cpu) / 1_000_000
                                    spans = validate_packet(packet, repo, files)
                                    if first_packet is None:
                                        first_packet, first_spans = packet, spans
                                    attempt = {"repetition": repetition, "wall_ms": wall_ms,
                                               "cpu_ms": cpu_ms, "packet_sha256": packet_hash(packet),
                                               "error": None}
                                    raw = {"corpus": corpus_name, "case_id": case["id"],
                                           "condition": condition, **attempt, "packet": packet}
                                except Exception as exc:
                                    wall_ms = (time.perf_counter_ns() - started_wall) / 1_000_000
                                    cpu_ms = (time.process_time_ns() - started_cpu) / 1_000_000
                                    attempt = {"repetition": repetition, "wall_ms": wall_ms,
                                               "cpu_ms": cpu_ms, "error": f"{type(exc).__name__}: {exc}"}
                                    raw = {"corpus": corpus_name, "case_id": case["id"],
                                           "condition": condition, **attempt}
                                row["attempts"].append(attempt)
                                raw_file.write(json.dumps(raw, ensure_ascii=False) + "\n")
                                raw_file.flush()
                            if first_packet is not None:
                                try:
                                    row["score"] = scored_case(corpus_name, case, index, first_packet, first_spans)
                                except Exception as exc:
                                    row["score_error"] = f"{type(exc).__name__}: {exc}"
                            if len({item.get("packet_sha256") for item in row["attempts"] if not item["error"]}) > 1:
                                row["packet_variation"] = True
                        rows.append(row)
                        print(f"{condition} {corpus_name}/{case['id']} {row.get('error') or row.get('score_error') or 'ok'}", flush=True)
                if args.experiment == "ownership":
                    retrieval._ownership_lifts = original_lifts
    write_json(output / "results.json", {"experiment": args.experiment,
               "serving_revision": "f41b3eaa4c7871c68972de5f760572a6bcbe1760",
               "request_policy": "same evaluator-known exact gold anchor per pair",
               "measurement": "three direct retrieve_context repetitions on preloaded graph after separate indexing and validation",
               "corpora": {name: {"version": corpus["version"], "cases": len(corpus["cases"]),
                                    "corpus_sha256": hashlib.sha256((Path(corpus["_root"]) / "corpus.json").read_bytes()).hexdigest()}
                           for name, corpus in corpora.items()},
               "cases": rows})
    print(f"wrote {output}", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--experiment", choices=("control", "ownership"), required=True)
    parser.add_argument("--output", type=Path, required=True)
    run(parser.parse_args())
