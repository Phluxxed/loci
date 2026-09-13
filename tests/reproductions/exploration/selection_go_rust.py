#!/usr/bin/env python3
"""Reproduce selected W4.7 Go/Rust compact-selection omissions without providers."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from benchmarks.typescript_context_corpus import _isolated_store, load_corpus, materialize_snapshot
from loci import service


ROOT = Path(__file__).resolve().parents[3]
INPUTS = ROOT / "benchmarks/comparisons/multilingual-context-workflow-v1/inputs"
RESULTS = ROOT / "benchmarks/results/multilingual-context-workflow-v1"


CASES: dict[str, dict[str, Any]] = {
    "go_alias": {
        "attempt": "go_alias_generic_contract-r1-B",
        "snapshot": "go_contracts",
        "retained_requests": [{
            "intent": "type_dependencies",
            "seed_ids": ["app/main.go::Build#function"],
            "max_hops": 2,
            "max_output_bytes": 12000,
            "max_evidence_bytes": 8000,
        }],
        "followups": [{
            "intent": "type_dependencies",
            "seed_ids": ["model/model.go::AliasID#type"],
            "max_hops": 1,
            "max_output_bytes": 12000,
            "max_evidence_bytes": 8000,
        }],
        "available": [
            ["app/main.go::Build#function", "model/model.go::AliasID#type", "uses_type"],
            ["app/main.go::Build#function", "model/model.go::Page#type", "uses_type"],
            ["app/main.go::Build#function", "model/model.go::UserID#type", "uses_type"],
            ["model/model.go::AliasID#type", "model/model.go::UserID#type", "uses_type"],
            ["model/model.go::Page#type", "model/model.go::Number#type", "uses_type"],
        ],
        "classification": "expected_bounded_omission",
        "reason": "The global visited set retains one proof path per selected node: Build selects UserID directly, so AliasID -> UserID is disclosed as an alternative path.",
    },
    "go_api_impact": {
        "attempt": "go_known_api_impact-r1-B",
        "snapshot": "go_impact",
        "retained_requests": [
            {
                "intent": "dependencies",
                "max_hops": 2,
                "query": "Locate the authored api declarations named Handle and Request. Determine the exact api file, Request fields and field types, and proven direct callers of Handle, preserving unresolved relationships and package/import routes.",
            },
            {
                "intent": "impact",
                "max_hops": 2,
                "seed_ids": ["api/api.go::Handle#function"],
                "query": "Find known direct callers of api.Handle, including imported package routes.",
            },
        ],
        "followups": [
            {"intent": "type_dependencies", "seed_ids": ["cmd/server/main.go::Serve#function"], "max_hops": 1},
            {"intent": "type_dependencies", "seed_ids": ["cmd/worker/main.go::Work#function"], "max_hops": 1},
        ],
        "available": [
            ["cmd/server/main.go::Serve#function", "api/api.go::Handle#function", "calls"],
            ["cmd/worker/main.go::Work#function", "api/api.go::Handle#function", "calls"],
            ["api/api.go::Handle#function", "api/api.go::Request#type", "uses_type"],
            ["cmd/server/main.go::Serve#function", "api/api.go::Request#type", "uses_type"],
            ["cmd/worker/main.go::Work#function", "api/api.go::Request#type", "uses_type"],
        ],
        "classification": "task_agent_request_choice_with_expected_bounded_omission",
        "reason": "Impact walks incoming known dependents of Handle; it does not then walk each caller's outgoing Go type dependencies. Separate caller seeds are required because shared Request also retains one selected proof path.",
    },
    "rust_trait_impl": {
        "attempt": "rust_authored_trait_contract-r1-B",
        "snapshot": "rust_contracts",
        "retained_requests": [
            {
                "intent": "type_dependencies",
                "max_hops": 2,
                "query": "For build and Receipt, identify UserId alias underlying type, build generic bounds and return constructor, Render supertrait, Receipt fields, and traits explicitly implemented for Receipt.",
            },
            {
                "intent": "type_dependencies",
                "max_hops": 2,
                "seed_ids": ["src/lib.rs::Receipt#struct"],
            },
        ],
        "followups": [{
            "intent": "type_dependencies",
            "seed_ids": ["src/lib.rs::Envelope#struct"],
            "max_hops": 1,
        }],
        "available": [
            ["src/lib.rs::build#function", "src/lib.rs::Render#trait", "uses_type"],
            ["src/lib.rs::build#function", "src/lib.rs::UserId#type", "uses_type"],
            ["src/lib.rs::build#function", "src/lib.rs::Envelope#struct", "uses_type"],
            ["src/lib.rs::Envelope#struct", "src/lib.rs::Render#trait", "uses_type"],
            ["src/lib.rs::Envelope#struct", "src/lib.rs::UserId#type", "uses_type"],
            ["src/lib.rs::Render#trait", "src/lib.rs::Format#trait", "supertrait"],
            ["src/lib.rs::Receipt#struct", "src/lib.rs::UserId#type", "uses_type"],
            ["src/lib.rs::Receipt#impl", "src/lib.rs::Format#trait", "impl_trait"],
            ["src/lib.rs::Receipt#impl", "src/lib.rs::Receipt#struct", "impl_self_type"],
            ["src/lib.rs::Receipt#impl~1", "src/lib.rs::Render#trait", "impl_trait"],
            ["src/lib.rs::Receipt#impl~1", "src/lib.rs::Receipt#struct", "impl_self_type"],
        ],
        "classification": "expected_bounded_omission",
        "reason": "The inferred build packet and explicit Receipt packet select nine of eleven meanings; Envelope's deeper fields require Envelope as a focused seed.",
    },
    "rust_known_call": {
        "attempt": "rust_known_call_impact-r2-B",
        "snapshot": "rust_impact",
        "retained_requests": [{
            "intent": "dependencies",
            "max_hops": 3,
            "query": "Locate the authored declaration parse and Config, the module/import relationship between them, and definite static callers of parse. Report parse file, direct caller, Config field and type, and configuration value.",
        }],
        "followups": [
            {"intent": "impact", "seed_ids": ["src/api.rs::parse#function"], "max_hops": 1},
            {"intent": "type_dependencies", "seed_ids": ["src/api.rs::parse#function"], "max_hops": 1},
        ],
        "available": [
            ["src/lib.rs::caller#function", "src/api.rs::parse#function", "calls"],
            ["src/lib.rs::caller#function", "src/api.rs::Config#struct", "uses_type"],
            ["src/api.rs::parse#function", "src/api.rs::Config#struct", "uses_type"],
        ],
        "classification": "task_agent_request_choice",
        "reason": "Rust dependencies selects authored type edges and anchored caller, while definite calls require impact from parse and parse's parameter type requires a type-dependency request from parse.",
    },
    "rust_declared_possible_control": {
        "attempt": "rust_contained_optional_reexport-r1-B",
        "snapshot": "rust_workspace",
        "retained_requests": [{
            "intent": "type_dependencies",
            "max_hops": 2,
            "query": "use_it public_name field_name field_type dependency_package configuration active_feature_proven",
            "seed_ids": ["app/src/lib.rs::use_it#function"],
            "max_output_bytes": 12000,
            "max_evidence_bytes": 8192,
        }],
        "followups": [],
        "available": [
            ["app/src/lib.rs::use_it#function", "core/src/api.rs::Thing#struct", "uses_type"],
        ],
        "classification": "resolved_uncertainty_control",
        "reason": "The retained workspace packet preserves declared_possible on the optional path dependency and does not claim an active feature.",
    },
}


def canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def sha(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def relation_key(value: dict[str, Any]) -> tuple[str, str, str]:
    edge = value["edge"] if "edge" in value else value
    return edge["from"], edge["to"], edge["type"]


def frozen_packets(attempt: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    events = json.loads((RESULTS / attempt / "events.json").read_text())
    requests = [e["item"]["arguments"] for e in events if e["type"] == "item.started" and e["item"].get("tool") == "loci_explore"]
    packets = [e["item"]["result"]["structured_content"] for e in events if e["type"] == "item.completed" and e["item"].get("tool") == "loci_explore"]
    return requests, packets


def verify_sources(repo: Path, packet: dict[str, Any]) -> list[dict[str, Any]]:
    verified = []
    for source in packet["sources"]:
        raw = (repo / source["file"]).read_bytes()
        content = source["content"].encode()
        assert raw[source["start_byte"]:source["end_byte"]] == content
        assert sha(raw) == source["content_hash"]
        assert raw[:source["start_byte"]].count(b"\n") + 1 == source["start_line"]
        assert raw[:source["end_byte"]].count(b"\n") + (0 if content.endswith(b"\n") else 1) == source["end_line"]
        verified.append({
            "file": source["file"], "start_byte": source["start_byte"], "end_byte": source["end_byte"],
            "start_line": source["start_line"], "end_line": source["end_line"],
            "file_sha256": source["content_hash"], "span_sha256": sha(content),
        })
    return verified


def verify_paths(packet: dict[str, Any]) -> None:
    relationships = {r["id"]: r for r in packet["relationships"]}
    assert len(relationships) == len(packet["relationships"])
    anchors = {i["id"] for i in packet["items"] if i["role"] == "anchor"}
    assert len({i["id"] for i in packet["items"]}) == len(packet["items"])
    source_ids = {s["id"] for s in packet["sources"]}
    assert source_ids == set(range(1, len(packet["sources"]) + 1))
    for item in packet["items"]:
        assert item["source_id"] in source_ids
        assert item["depth"] == len(item["path"])
        if not item["path"]:
            assert item["id"] in anchors
            continue
        candidates = set(anchors)
        for relation_id in item["path"]:
            relation = relationships[relation_id]
            edge = relation["edge"]
            if relation["traversed"] == "forward":
                candidates = {edge["to"] for current in candidates if current == edge["from"]}
            else:
                candidates = {edge["from"] for current in candidates if current == edge["to"]}
            assert candidates
        assert item["id"] in candidates
    for relationship in packet["relationships"]:
        assert set(relationship["source_ids"]) <= source_ids


def verify_usage(packet: dict[str, Any]) -> None:
    intervals: dict[tuple[str, str], list[tuple[int, int]]] = {}
    for source in packet["sources"]:
        intervals.setdefault((source["file"], source["content_hash"]), []).append(
            (source["start_byte"], source["end_byte"])
        )
    evidence_bytes = 0
    for ranges in intervals.values():
        start = end = -1
        for current_start, current_end in sorted(ranges):
            if start < 0:
                start, end = current_start, current_end
            elif current_start <= end:
                end = max(end, current_end)
            else:
                evidence_bytes += end - start
                start, end = current_start, current_end
        if start >= 0:
            evidence_bytes += end - start
    envelope_bytes = len(json.dumps(
        {"content": [], "structuredContent": packet, "isError": False},
        ensure_ascii=False, separators=(",", ":"),
    ).encode())
    assert packet["usage"]["evidence_bytes"] == evidence_bytes
    assert packet["usage"]["output_bytes"] == envelope_bytes
    assert packet["usage"]["estimated_tokens"] == math.ceil(envelope_bytes / 4)
    assert evidence_bytes <= packet["limits"]["max_evidence_bytes"]
    assert envelope_bytes <= packet["limits"]["max_output_bytes"]


def compact_packet(packet: dict[str, Any]) -> dict[str, Any]:
    return {
        "intent": packet["intent"], "selection": packet["selection"], "status": packet["status"],
        "scope": packet["scope"], "limits": packet["limits"], "omissions": packet["omissions"],
        "items": [{k: item[k] for k in ("id", "role", "depth", "path")} for item in packet["items"]],
        "relationships": [{
            "from": r["edge"]["from"], "to": r["edge"]["to"], "type": r["edge"]["type"],
            "resolution": r["edge"]["resolution"], "traversed": r["traversed"],
            "configuration": r.get("resolution_configuration"), "evidence": r["edge"]["evidence"],
        } for r in packet["relationships"]],
        "sources": [{k: s[k] for k in ("file", "start_byte", "end_byte", "start_line", "end_line", "content_hash", "content")} for s in packet["sources"]],
    }


def run() -> dict[str, Any]:
    corpus = load_corpus(INPUTS)
    freeze = json.loads((ROOT / "benchmarks/comparisons/multilingual-context-workflow-v1/freeze.json").read_text())
    result: dict[str, Any] = {
        "schema_version": 1,
        "source_identity": {
            "worktree_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
            "frozen_engine": {k: freeze["engine"][k] for k in ("commit", "source_tree", "extractor_version", "graph_state_version")},
            "corpus_sha256": sha((INPUTS / "corpus.json").read_bytes()),
            "corpus_declared_sha256": (INPUTS / "corpus.sha256").read_text().strip(),
        },
        "contract": "One selected proof path per source item; scope.exhaustive is false.",
        "cases": {},
    }
    with tempfile.TemporaryDirectory(prefix="loci-w52-go-rust-") as temp_name:
        temp = Path(temp_name)
        for name, spec in CASES.items():
            repo = temp / name / "snapshot"
            store = temp / name / "store"
            materialize_snapshot(corpus, spec["snapshot"], repo)
            with _isolated_store(store):
                service.index_repo(repo, incremental=False)
                _, nodes, state = service._load_graph_context(repo, ensure_fresh=False)
                state_edges = {relation_key(e.to_dict()): e.to_dict() for e in state.edges}
                exact_state_edges = {canonical(edge.to_dict()) for edge in state.edges}
                available = [tuple(edge) for edge in spec["available"]]
                missing = [edge for edge in available if edge not in state_edges]
                assert not missing, (name, missing, sorted(state_edges))
                graph_projection = [state_edges[edge] for edge in available]
                graph_hash = sha(canonical(graph_projection))
                graph_state = {
                    "node_ids": sorted(nodes),
                    "edges": sorted((edge.to_dict() for edge in state.edges), key=canonical),
                }
                frozen_requests, frozen = frozen_packets(spec["attempt"])
                assert frozen_requests == spec["retained_requests"], (name, frozen_requests, spec["retained_requests"])
                retained = [service.explore(repo, **request) for request in spec["retained_requests"]]
                followups = [service.explore(repo, **request) for request in spec["followups"]]
                for packet in (*retained, *followups):
                    verify_paths(packet)
                    verify_sources(repo, packet)
                    verify_usage(packet)
                    for relationship in packet["relationships"]:
                        assert canonical(relationship["edge"]) in exact_state_edges
                retained_keys = {relation_key(r) for packet in retained for r in packet["relationships"]}
                followup_keys = {relation_key(r) for packet in followups for r in packet["relationships"]}
                omitted_keys = [edge for edge in available if edge not in retained_keys]
                assert set(omitted_keys) <= followup_keys, (name, omitted_keys, sorted(followup_keys))
                frozen_compact = [compact_packet(packet) for packet in frozen]
                retained_compact = [compact_packet(packet) for packet in retained]
                assert retained_compact == frozen_compact, name
                if name == "rust_declared_possible_control":
                    assert [[r.get("resolution_configuration") for r in p["relationships"]] for p in retained] == [["declared_possible"]]
                snapshot_files = {p: sha((repo / p).read_bytes()) for p in sorted(corpus["snapshots"][spec["snapshot"]]["files"])}
                result["cases"][name] = {
                    "attempt": spec["attempt"], "snapshot": spec["snapshot"],
                    "classification": spec["classification"], "reason": spec["reason"], "engine_change_needed": False,
                    "snapshot_files": snapshot_files,
                    "snapshot_files_sha256": sha(canonical(snapshot_files)),
                    "graph_state_sha256": sha(canonical(graph_state)),
                    "graph_counts": {"nodes": len(nodes), "edges": len(state.edges)},
                    "graph_projection_sha256": graph_hash,
                    "available_graph_edges": [list(edge) for edge in available],
                    "retained_requests": spec["retained_requests"],
                    "retained_request_sha256": sha(canonical(spec["retained_requests"])),
                    "frozen_packet_sha256": sha(canonical(frozen_compact)),
                    "replay_packet_sha256": sha(canonical(retained_compact)),
                    "replay_matches_frozen_packet": retained_compact == frozen_compact,
                    "retained_selected_edges": [[list(relation_key(r)) for r in p["relationships"]] for p in retained],
                    "retained_omissions": [p["omissions"] for p in retained],
                    "retained_effective_limits": [p["limits"] for p in retained],
                    "retained_configuration": [[r.get("resolution_configuration") for r in p["relationships"]] for p in retained],
                    "available_not_selected": [list(edge) for edge in omitted_keys],
                    "followup_requests": spec["followups"],
                    "followup_request_sha256": sha(canonical(spec["followups"])),
                    "followup_packet_sha256": sha(canonical([compact_packet(p) for p in followups])),
                    "followup_selected_edges": [[list(relation_key(r)) for r in p["relationships"]] for p in followups],
                    "followup_effective_limits": [p["limits"] for p in followups],
                    "followups_recover_all_available_not_selected": set(omitted_keys) <= followup_keys,
                    "proof_checks": {
                        "available_edges_in_state": True, "selected_edges_in_state": True,
                        "selected_paths_connected": True, "source_spans_match_snapshot": True,
                    },
                }
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    output_path = parser.parse_args().output
    value = run()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(json.dumps(value, indent=2, sort_keys=True).encode() + b"\n")
    print(json.dumps({"cases": len(value["cases"]), "all_replayed": all(
        case["replay_matches_frozen_packet"] for case in value["cases"].values()
    ), "output": str(output_path)}))
