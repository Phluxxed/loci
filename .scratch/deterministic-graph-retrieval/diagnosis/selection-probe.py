#!/usr/bin/env python3
"""Diagnose normal retrieval selection against the frozen Anvil source.

This indexes only into a diagnosis-owned store, reads the persisted graph, and
replays the deterministic normal policy with instrumentation. It does not
modify the target source or the repository's product/test files.
"""
from __future__ import annotations

import argparse
import copy
import json
import os
from collections import Counter
from pathlib import Path
from typing import Any


CAPTURE = "src/tool-results/service.ts::CaptureCommandResultOptions#type"
BINDING = "src/work-context/binding.ts::WorkContextBinding#type"
TARGET_EDGE = (CAPTURE, "uses_type", BINDING)


def envelope_bytes(value: dict[str, Any]) -> int:
    envelope = {"content": [], "structuredContent": value, "isError": False}
    return len(json.dumps(envelope, ensure_ascii=False, separators=(",", ":")).encode())


def omission_counts(items: list[dict[str, Any]]) -> dict[str, int]:
    return {str(item["reason"]): int(item["count"]) for item in items}


def relation_key(edge: Any) -> tuple[str, str, str]:
    return (edge.from_id, edge.type, edge.to_id)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--store", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    repo = args.repo.resolve()
    store_root = args.store.resolve()
    output = args.output.resolve()
    os.environ["LOCI_BASE_DIR"] = str(store_root)

    # Imports must follow LOCI_BASE_DIR assignment: service resolves its store
    # dynamically, but this also makes the isolation intent mechanically clear.
    from loci import retrieval as retrieval_module
    from loci import service
    from loci._exploration_output import _evidence_bytes
    from loci.retrieval_io import finalize_response

    if repo != Path("/tmp/anvil-source-tasks-20260914/t23").resolve():
        raise SystemExit(f"unexpected frozen source: {repo}")
    if "selection-" not in str(store_root):
        raise SystemExit(f"diagnosis store must be selection-scoped: {store_root}")

    index_summary = service.index_repo(repo, incremental=False)
    store = service.get_store()
    index = store.load(repo)
    if index is None:
        raise RuntimeError("isolated index was not persisted")
    nodes = {node["id"]: node for node in index["symbols"]}
    state = store.validate_graph_state(index)

    matching_edges = [edge for edge in state.edges if relation_key(edge) == TARGET_EDGE]
    matching_records = [
        record for record in state.type_relations
        if (record.source_id, record.raw.relation, record.target_id) == TARGET_EDGE
    ]
    related_observations = [
        record for record in state.type_relations
        if record.raw.source_file == "src/tool-results/service.ts"
        and record.raw.text == "WorkContextBinding"
    ]
    relevant_imports = [
        record for record in state.imports
        if record.raw.source_file in {
            "src/tool-results/service.ts", "src/work-context/index.ts"
        }
        and (
            "WorkContextBinding" in record.raw.text
            or record.raw.specifier in {
                "../work-context/index.ts", "./binding.ts"
            }
        )
    ]

    original_packer = retrieval_module.RetrievalPacker
    original_lifts = retrieval_module._ownership_lifts
    original_output_limit = retrieval_module.LIMITS["max_output_bytes"]

    def replay(label: str, query: str, seeds: list[str] | None = None,
               suppress_lifts: str = "none",
               output_limit: int | None = None) -> dict[str, Any]:
        trace: list[dict[str, Any]] = []

        class TracingPacker(original_packer):
            def add(self, addition):  # type: ignore[no-untyped-def]
                before_response = self._render(self.state)
                before_evidence = _evidence_bytes(self.state.spans)
                finalize_response(before_response, before_evidence)
                before_omissions = Counter(self.omissions)
                candidate = copy.deepcopy(self.state)
                candidate_response = None
                candidate_evidence = None
                candidate_error = None
                try:
                    self._apply(candidate, addition)
                    candidate_response = self._render(candidate)
                    candidate_evidence = _evidence_bytes(candidate.spans)
                    finalize_response(candidate_response, candidate_evidence)
                except Exception as exc:  # preserve diagnosis if a candidate is invalid
                    candidate_error = f"{type(exc).__name__}: {exc}"
                accepted = super().add(addition)
                after_response = self._render(self.state)
                finalize_response(after_response, _evidence_bytes(self.state.spans))
                added_sources = []
                if candidate_response is not None:
                    before_keys = {
                        (item["file"], item["start_byte"], item["end_byte"], item["content_hash"])
                        for item in before_response["sources"]
                    }
                    for item in candidate_response["sources"]:
                        key = (item["file"], item["start_byte"], item["end_byte"], item["content_hash"])
                        if key not in before_keys:
                            added_sources.append({
                                "file": item["file"],
                                "start_byte": item["start_byte"],
                                "end_byte": item["end_byte"],
                                "content_bytes": len(item["content"].encode()),
                                "source_ref_bytes": len(item["source_ref"].encode()),
                                "serialized_source_bytes": len(json.dumps(
                                    item, ensure_ascii=False, separators=(",", ":")
                                ).encode()),
                            })
                edge = addition.relation.edge if addition.relation is not None else None
                trace.append({
                    "kind": "relationship" if edge is not None else "context",
                    "edge": edge.to_dict() if edge is not None else None,
                    "target_edge": relation_key(edge) == TARGET_EDGE if edge is not None else False,
                    "nodes_added": [str(item["id"]) for item in addition.nodes],
                    "items_added": [str(item.node["id"]) for item in addition.items],
                    "ownership_added": list(addition.ownership),
                    "before_output_bytes": before_response["usage"]["output_bytes"],
                    "before_evidence_bytes": before_evidence,
                    "candidate_output_bytes": (
                        candidate_response["usage"]["output_bytes"]
                        if candidate_response is not None else None
                    ),
                    "candidate_envelope_bytes_crosscheck": (
                        envelope_bytes(candidate_response) if candidate_response is not None else None
                    ),
                    "candidate_evidence_bytes": candidate_evidence,
                    "candidate_error": candidate_error,
                    "accepted": accepted,
                    "after_output_bytes": after_response["usage"]["output_bytes"],
                    "rejection_omissions": dict(self.omissions - before_omissions),
                    "added_sources": added_sources,
                })

                return accepted

        def lifts(source, node, terms):  # type: ignore[no-untyped-def]
            if suppress_lifts == "all":
                return ()
            if suppress_lifts == "file_members" and node.get("kind") in retrieval_module._NATIVE_KINDS:
                return ()
            return original_lifts(source, node, terms)

        retrieval_module.RetrievalPacker = TracingPacker
        retrieval_module._ownership_lifts = lifts
        retrieval_module.LIMITS["max_output_bytes"] = output_limit or original_output_limit
        try:
            result = retrieval_module.retrieve_context(
                repo, store, nodes, state, query, seed_ids=seeds, coverage="complete"
            )
        finally:
            retrieval_module.RetrievalPacker = original_packer
            retrieval_module._ownership_lifts = original_lifts
            retrieval_module.LIMITS["max_output_bytes"] = original_output_limit
        target_attempts = [item for item in trace if item["target_edge"]]
        first_target_index = next(
            (index for index, item in enumerate(trace) if item["target_edge"]),
            None,
        )
        before_target = trace[:first_target_index] if first_target_index is not None else trace
        target_delivered = any(
            (item["edge"]["from"], item["edge"]["type"], item["edge"]["to"]) == TARGET_EDGE
            for item in result["relationships"]
        )
        return {
            "label": label,
            "request": {"query": query, "seed_ids": seeds},
            "intervention": {
                "suppress_ownership_lifts": suppress_lifts,
                "max_output_bytes": output_limit or original_output_limit,
            },
            "result": {
                "status": result["status"],
                "nodes": [item["id"] for item in result["nodes"]],
                "items": [item["node_id"] for item in result["items"]],
                "ownership": result["ownership"],
                "relationships": [item["edge"] for item in result["relationships"]],
                "omissions": result["omissions"],
                "usage": result["usage"],
                "target_delivered": target_delivered,
                "envelope_bytes_crosscheck": envelope_bytes(result),
            },
            "target_attempts": target_attempts,
            "selection_before_first_target_attempt": {
                "addition_attempts": len(before_target),
                "context_attempts": sum(item["kind"] == "context" for item in before_target),
                "relationship_attempts": sum(
                    item["kind"] == "relationship" for item in before_target
                ),
                "accepted_relationships": [
                    item["edge"] for item in before_target
                    if item["kind"] == "relationship" and item["accepted"]
                ],
                "accepted_context": [
                    {
                        "items_added": item["items_added"],
                        "ownership_added": item["ownership_added"],
                        "output_delta_bytes": (
                            item["candidate_output_bytes"] - item["before_output_bytes"]
                            if item["candidate_output_bytes"] is not None else None
                        ),
                    }
                    for item in before_target
                    if item["kind"] == "context" and item["accepted"]
                ],
            },
        }

    requests = [
        ("capture-query", "CaptureCommandResultOptions", None),
        ("binding-query", "WorkContextBinding", None),
        ("explicit-pair", "binding contract", [CAPTURE, BINDING]),
    ]
    baseline = [replay(label, query, seeds) for label, query, seeds in requests]
    without_file_members = [
        replay(f"{label}-without-file-members", query, seeds,
               suppress_lifts="file_members")
        for label, query, seeds in requests
    ]
    without_ownership_expansion = [
        replay(f"{label}-without-ownership-expansion", query, seeds,
               suppress_lifts="all")
        for label, query, seeds in requests
    ]
    expanded_output = [
        replay(f"{label}-32768", query, seeds, output_limit=32768)
        for label, query, seeds in requests
    ]

    edge = matching_edges[0] if len(matching_edges) == 1 else None
    proof = None
    if edge is not None:
        retrieval_source = retrieval_module.RetrievalSource(repo, store, nodes, state)
        spans = retrieval_source.proof(edge)
        proof = [
            {
                "file": span.file,
                "start_byte": span.start_byte,
                "end_byte": span.end_byte,
                "start_line": span.start_line,
                "end_line": span.end_line,
                "content_hash": span.content_hash,
                "content_bytes": len(span.content.encode()),
                "content": span.content,
            }
            for span in spans or ()
        ]

    eligible = retrieval_module._eligible_edges(state.edges, nodes)
    adjacency = retrieval_module.graph_adjacency(eligible, direction="either")
    degrees = Counter()
    for item in eligible:
        degrees[item.from_id] += 1
        if item.to_id != item.from_id:
            degrees[item.to_id] += 1
    request_neighbor_order = []
    for label, query, seeds in requests:
        selected = seeds or ([CAPTURE] if label == "capture-query" else [BINDING])
        for anchor_id in selected:
            ranked = retrieval_module._ranked_neighbors(
                list(adjacency.get(anchor_id, ())), nodes,
                set(retrieval_module.graph_text_terms(query)), degrees,
            )
            request_neighbor_order.append({
                "label": label,
                "anchor": anchor_id,
                "eligible_neighbors": len(adjacency.get(anchor_id, ())),
                "target_positions_zero_based": [
                    position for position, step in enumerate(ranked)
                    if relation_key(step.edge) == TARGET_EDGE
                ],
                "first_12": [
                    {
                        "position_zero_based": position,
                        "from": step.edge.from_id,
                        "type": step.edge.type,
                        "to": step.edge.to_id,
                        "traversed": step.traversed,
                    }
                    for position, step in enumerate(ranked[:12])
                ],
            })

    evidence = {
        "schema_version": 1,
        "frozen_source": {
            "path": str(repo),
            "expected_commit": "53bf29e60cece2335aa39fe301935a07e8e8d4e4",
            "file_count_observed": sum(1 for item in repo.rglob("*") if item.is_file()),
        },
        "isolated_store": str(store_root),
        "index_summary": index_summary,
        "target_identity": {
            "from": CAPTURE,
            "type": "uses_type",
            "to": BINDING,
        },
        "stored": {
            "matching_edge_count": len(matching_edges),
            "edges": [item.to_dict() for item in matching_edges],
            "matching_type_record_count": len(matching_records),
            "type_records": [item.to_dict() for item in matching_records],
            "source_text_observation_count": len(related_observations),
            "source_text_observations": [item.to_dict() for item in related_observations],
            "relevant_import_records": [item.to_dict() for item in relevant_imports],
            "proof": proof,
        },
        "direct_anchor_neighbor_order": request_neighbor_order,
        "replays": {
            "baseline": baseline,
            "without_file_member_lifts": without_file_members,
            "without_ownership_expansion": without_ownership_expansion,
            "expanded_output": expanded_output,
        },
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({
        "output": str(output),
        "matching_edges": len(matching_edges),
        "matching_type_records": len(matching_records),
        "baseline_target_delivery": [item["result"]["target_delivered"] for item in baseline],
        "without_file_members_target_delivery": [
            item["result"]["target_delivered"] for item in without_file_members
        ],
        "without_ownership_expansion_target_delivery": [
            item["result"]["target_delivered"] for item in without_ownership_expansion
        ],
        "expanded_output_target_delivery": [
            item["result"]["target_delivered"] for item in expanded_output
        ],
    }, indent=2))


if __name__ == "__main__":
    main()
