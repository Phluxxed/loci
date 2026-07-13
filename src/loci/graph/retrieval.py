from __future__ import annotations

from collections import defaultdict
from math import ceil
from pathlib import Path
from typing import Any, Sequence

from .anchors import GraphAnchorSelection, select_graph_anchors
from .contracts import (
    GRAPH_SCHEMA_VERSION,
    GraphContractError,
    GraphEdge,
    GraphNodeRef,
)
from .state import GraphIndexState
from .traversal import (
    MAX_GRAPH_ESTIMATED_TOKENS,
    MAX_GRAPH_EVIDENCE_BYTES,
    GraphDirection,
    GraphPath,
    GraphTraversalResult,
    filter_graph_edges,
    find_graph_paths,
    graph_adjacency,
    graph_hub_threshold,
    graph_relation_terms,
    graph_text_terms,
    semantic_bridge_terms,
)
from ..storage.index_store import IndexStore


def retrieve_graph_neighbors(
    repo_path: Path,
    indexed_nodes: dict[str, dict[str, Any]],
    graph_state: GraphIndexState,
    seed_ids: list[str],
    *,
    namespaces: list[str] | None,
    edge_types: list[str] | None,
    resolutions: list[str] | None,
    direction: GraphDirection,
    max_neighbors: int,
) -> dict[str, Any]:
    unique_seed_ids = _graph_endpoint_ids(seed_ids, "seed_ids")
    _graph_budget_int(max_neighbors, "max_neighbors", 1, 256)
    _require_graph_endpoints(repo_path, indexed_nodes, unique_seed_ids)
    edges = filter_graph_edges(
        graph_state.edges,
        namespaces=namespaces,
        edge_types=edge_types,
        resolutions=resolutions,
    )
    _validate_graph_traversal_edges(edges, indexed_nodes)
    adjacency = graph_adjacency(edges, direction=direction)

    results = []
    for seed_id in unique_seed_ids:
        steps = adjacency.get(seed_id, ())
        selected = steps[:max_neighbors]
        results.append({
            "seed": _graph_node_ref(indexed_nodes[seed_id]),
            "neighbors": [
                {
                    "node": _graph_node_ref(indexed_nodes[step.to_id]),
                    "traversed": step.traversed,
                    "edge": step.edge.to_dict(),
                }
                for step in selected
            ],
            "returned": len(selected),
            "omitted": max(0, len(steps) - len(selected)),
        })
    return {
        "schema_version": GRAPH_SCHEMA_VERSION,
        "repo": str(repo_path),
        "filters": _graph_filter_envelope(
            namespaces,
            edge_types,
            resolutions,
            direction,
        ),
        "results": results,
        "counts": {
            "filtered_edges": len(edges),
            "returned_neighbors": sum(item["returned"] for item in results),
            "omitted_neighbors": sum(item["omitted"] for item in results),
        },
        "budget": {"max_neighbors_per_seed": max_neighbors},
        "diagnostics": [
            diagnostic.to_dict() for diagnostic in graph_state.diagnostics
        ],
    }


def retrieve_graph_paths(
    repo_path: Path,
    store: IndexStore,
    indexed_nodes: dict[str, dict[str, Any]],
    graph_state: GraphIndexState,
    source_ids: list[str],
    target_ids: list[str],
    *,
    namespaces: list[str] | None,
    edge_types: list[str] | None,
    resolutions: list[str] | None,
    direction: GraphDirection,
    max_hops: int,
    max_nodes: int,
    max_paths: int,
    path_offset: int,
    max_evidence_bytes: int,
    max_estimated_tokens: int,
) -> dict[str, Any]:
    sources = _graph_endpoint_ids(source_ids, "source_ids")
    targets = _graph_endpoint_ids(target_ids, "target_ids")
    _validate_graph_evidence_budgets(max_evidence_bytes, max_estimated_tokens)
    _require_graph_endpoints(repo_path, indexed_nodes, (*sources, *targets))
    edges = filter_graph_edges(
        graph_state.edges,
        namespaces=namespaces,
        edge_types=edge_types,
        resolutions=resolutions,
    )
    _validate_graph_traversal_edges(edges, indexed_nodes)
    traversal = find_graph_paths(
        edges,
        sources,
        targets,
        direction=direction,
        max_hops=max_hops,
        max_nodes=max_nodes,
        max_paths=max_paths,
        path_offset=path_offset,
    )

    evidence_limit = min(max_evidence_bytes, max_estimated_tokens * 4)
    evidence_bytes = 0
    paths: list[dict[str, Any]] = []
    rejected_paths: list[dict[str, Any]] = []
    diagnostics = [diagnostic.to_dict() for diagnostic in graph_state.diagnostics]
    for path in traversal.paths:
        hydrated, error = _hydrate_graph_path(
            repo_path,
            store,
            indexed_nodes,
            path,
        )
        if error is not None:
            rejected_paths.append(_rejected_graph_path(path, error["code"]))
            diagnostics.append(error)
            continue
        assert hydrated is not None
        path_bytes = int(hydrated.pop("evidence_bytes"))
        if evidence_bytes + path_bytes > evidence_limit:
            rejected_paths.append(
                _rejected_graph_path(path, "EVIDENCE_BUDGET_EXCEEDED")
            )
            continue
        evidence_bytes += path_bytes
        paths.append(hydrated)

    return {
        "schema_version": GRAPH_SCHEMA_VERSION,
        "repo": str(repo_path),
        "support_kind": "edge_sequence",
        "sources": [_graph_node_ref(indexed_nodes[node_id]) for node_id in sources],
        "targets": [_graph_node_ref(indexed_nodes[node_id]) for node_id in targets],
        "filters": _graph_filter_envelope(
            namespaces,
            edge_types,
            resolutions,
            direction,
        ),
        "paths": paths,
        "rejected_paths": rejected_paths,
        "counts": {
            "filtered_edges": traversal.filtered_edge_count,
            "examined_nodes": traversal.examined_nodes,
            "examined_paths": traversal.examined_paths,
            "returned_paths": len(paths),
            "rejected_paths": len(rejected_paths),
            "omitted_rejected_paths": 0,
            "omitted_nodes": traversal.omitted_nodes,
            "omitted_paths": traversal.omitted_paths,
        },
        "budget": _graph_budget_envelope(
            traversal,
            max_hops=max_hops,
            max_nodes=max_nodes,
            max_paths=max_paths,
            path_offset=path_offset,
            evidence_bytes=evidence_bytes,
            max_evidence_bytes=max_evidence_bytes,
            max_estimated_tokens=max_estimated_tokens,
        ),
        "diagnostics": diagnostics,
    }


def retrieve_graph_question(
    repo_path: Path,
    store: IndexStore,
    indexed_nodes: dict[str, dict[str, Any]],
    graph_state: GraphIndexState,
    question: str,
    seed_ids: list[str] | None,
    *,
    namespaces: list[str] | None,
    edge_types: list[str] | None,
    resolutions: list[str] | None,
    direction: GraphDirection,
    max_anchors: int,
    max_hops: int,
    max_nodes: int,
    max_paths: int,
    path_offset: int,
    max_evidence_bytes: int,
    max_estimated_tokens: int,
) -> dict[str, Any]:
    _validate_graph_evidence_budgets(max_evidence_bytes, max_estimated_tokens)
    _validate_graph_traversal_budgets(
        max_hops,
        max_nodes,
        max_paths,
        path_offset,
    )
    selection = select_graph_anchors(
        tuple(indexed_nodes.values()),
        question,
        seed_ids if seed_ids is not None else [],
        max_anchors=max_anchors,
    )
    edges = filter_graph_edges(
        graph_state.edges,
        namespaces=namespaces,
        edge_types=edge_types,
        resolutions=resolutions,
    )
    _validate_graph_traversal_edges(edges, indexed_nodes)
    graph_adjacency(edges, direction=direction)

    anchor_values = _graph_anchor_values(selection, indexed_nodes)
    routing = _graph_question_routing(question, explicit=selection.mode == "explicit")
    diagnostics = [diagnostic.to_dict() for diagnostic in graph_state.diagnostics]
    filters = _graph_filter_envelope(
        namespaces,
        edge_types,
        resolutions,
        direction,
    )
    if routing["kind"] == "suppressed" or len(selection.anchors) < 1:
        return _graph_retrieve_envelope(
            repo_path=repo_path,
            question=question,
            selection=selection,
            anchors=anchor_values,
            routing=routing,
            filters=filters,
            paths=[],
            rejected_paths=[],
            traversal=None,
            filtered_edge_count=len(edges),
            hub_threshold=graph_hub_threshold(len(edges)),
            max_hops=max_hops,
            max_nodes=max_nodes,
            max_paths=max_paths,
            path_offset=path_offset,
            evidence_bytes=0,
            max_evidence_bytes=max_evidence_bytes,
            max_estimated_tokens=max_estimated_tokens,
            diagnostics=diagnostics,
        )

    anchor_ids = tuple(anchor.node_id for anchor in selection.anchors)
    question_terms = set(semantic_bridge_terms(question, "", ""))
    node_relevance = {
        node_id: _graph_node_priority(symbol, question_terms)
        for node_id, symbol in indexed_nodes.items()
    }
    node_priorities = dict(node_relevance)
    for anchor in selection.anchors:
        node_priorities[anchor.node_id] = (
            node_priorities.get(anchor.node_id, 0.0)
            + min(10.0, float(anchor.score or 0.0) / 10.0)
        )
    graph_node_ids = {
        node_id
        for edge in edges
        for node_id in (edge.from_id, edge.to_id)
    }
    prioritized_nodes = sorted(
        graph_node_ids,
        key=lambda node_id: (-node_priorities.get(node_id, 0.0), node_id),
    )
    node_universe = set(anchor_ids)
    for node_id in prioritized_nodes:
        if len(node_universe) >= max_nodes:
            break
        node_universe.add(node_id)
    question_edges = tuple(
        edge
        for edge in edges
        if edge.from_id in node_universe and edge.to_id in node_universe
    )
    if selection.mode == "explicit":
        source_values = anchor_ids[:1]
        target_values = anchor_ids[1:]
        if not target_values:
            target_values = tuple(
                node_id
                for node_id, priority in sorted(
                    node_priorities.items(),
                    key=lambda item: (-item[1], item[0]),
                )
                if (
                    node_id in node_universe
                    and node_id not in source_values
                    and priority > 0
                )
            )
    else:
        source_values = anchor_ids
        relevant_nodes = tuple(
            node_id
            for node_id, priority in sorted(
                node_priorities.items(),
                key=lambda item: (-item[1], item[0]),
            )
            if node_id in node_universe and priority > 0
        )
        target_values = tuple(dict.fromkeys((*anchor_ids, *relevant_nodes)))
    if not target_values or not any(
        source != target for source in source_values for target in target_values
    ):
        return _graph_retrieve_envelope(
            repo_path=repo_path,
            question=question,
            selection=selection,
            anchors=anchor_values,
            routing={"kind": "relationship", "reason": "no_candidate_endpoint"},
            filters=filters,
            paths=[],
            rejected_paths=[],
            traversal=None,
            filtered_edge_count=len(edges),
            hub_threshold=graph_hub_threshold(len(edges)),
            max_hops=max_hops,
            max_nodes=max_nodes,
            max_paths=max_paths,
            path_offset=path_offset,
            evidence_bytes=0,
            max_evidence_bytes=max_evidence_bytes,
            max_estimated_tokens=max_estimated_tokens,
            diagnostics=diagnostics,
        )

    traversal = find_graph_paths(
        question_edges,
        source_values,
        target_values,
        direction=direction,
        max_hops=max_hops,
        max_nodes=max_nodes,
        max_paths=32,
        path_offset=0,
        node_priorities=node_priorities,
    )
    candidate_paths = list(traversal.paths)
    if selection.mode == "explicit":
        targeted_sources = anchor_ids[:1]
        targeted_ids = anchor_ids[1:]
    else:
        non_anchor_targets = [
            node_id
            for node_id in prioritized_nodes
            if node_id not in anchor_ids and node_id in node_universe
        ][:8]
        targeted_sources = anchor_ids[:5]
        targeted_ids = tuple(dict.fromkeys((*anchor_ids[:5], *non_anchor_targets)))
    for source_id in targeted_sources:
        for target_id in targeted_ids:
            if source_id == target_id:
                continue
            targeted = find_graph_paths(
                question_edges,
                [source_id],
                [target_id],
                direction=direction,
                max_hops=max_hops,
                max_nodes=max_nodes,
                max_paths=8,
                path_offset=0,
                node_priorities=node_priorities,
            )
            candidate_paths.extend(targeted.paths)

    threshold = graph_hub_threshold(len(edges))
    degrees = _graph_degrees(edges)
    scored: list[tuple[tuple, dict[str, Any], int]] = []
    rejected_paths: list[dict[str, Any]] = []
    seen_routes: set[tuple] = set()
    duplicate_paths = 0
    for path in candidate_paths:
        route_key = _question_path_key(path)
        if route_key in seen_routes:
            duplicate_paths += 1
            continue
        seen_routes.add(route_key)
        hydrated, error = _hydrate_graph_path(
            repo_path,
            store,
            indexed_nodes,
            path,
        )
        if error is not None:
            rejected_paths.append(_rejected_graph_path(path, error["code"]))
            diagnostics.append(error)
            continue
        assert hydrated is not None
        path_bytes = int(hydrated.pop("evidence_bytes"))
        evidence_text = " ".join(
            step["evidence_span"]["content"] for step in hydrated["steps"]
        )
        source_text = _graph_node_text(indexed_nodes[path.node_ids[0]])
        target_text = _graph_node_text(indexed_nodes[path.node_ids[-1]])
        required_terms = semantic_bridge_terms(
            question,
            source_text,
            target_text,
        )
        evidence_terms = set(graph_text_terms(evidence_text))
        required_term_set = set(required_terms)
        relation_terms = tuple(
            term
            for term in graph_relation_terms(question)
            if term in required_term_set
        )
        matched_terms = tuple(term for term in relation_terms if term in evidence_terms)
        intermediate = path.node_ids[1:-1]
        high_degree_nodes = tuple(
            node_id for node_id in intermediate if degrees.get(node_id, 0) > threshold
        )
        if len(path.steps) > 1 and not matched_terms:
            reason = "HUB_SHORTCUT" if high_degree_nodes else "SEMANTIC_BRIDGE_MISSING"
            rejected_paths.append(
                _rejected_graph_path(
                    path,
                    reason,
                    required_terms=required_terms,
                    high_degree_nodes=high_degree_nodes,
                )
            )
            continue

        score, components = _graph_path_score(
            path,
            selection,
            node_relevance,
            evidence_terms,
            question_terms,
            degrees,
            threshold,
        )
        hydrated.update({
            "support_kind": (
                "direct_authored_edge" if len(path.steps) == 1 else "semantic_bridge"
            ),
            "semantic_bridge": {
                "required": len(path.steps) > 1,
                "required_terms": list(required_terms),
                "matched_terms": list(matched_terms),
            },
            "retrieval_score": score,
            "score_components": components,
        })
        scored.append(((-score, _question_path_key(path)), hydrated, path_bytes))

    scored.sort(key=lambda item: item[0])
    window = scored[path_offset : path_offset + max_paths]
    evidence_limit = min(max_evidence_bytes, max_estimated_tokens * 4)
    evidence_bytes = 0
    paths: list[dict[str, Any]] = []
    for _key, hydrated, path_bytes in window:
        path_node_ids = [node["id"] for node in hydrated["nodes"]]
        if evidence_bytes + path_bytes > evidence_limit:
            rejected_paths.append({
                "nodes": path_node_ids,
                "reason": "EVIDENCE_BUDGET_EXCEEDED",
            })
            continue
        evidence_bytes += path_bytes
        paths.append(hydrated)
    if len(scored) > path_offset + max_paths:
        traversal = GraphTraversalResult(
            paths=traversal.paths,
            filtered_edge_count=traversal.filtered_edge_count,
            examined_nodes=traversal.examined_nodes,
            examined_paths=traversal.examined_paths,
            omitted_nodes=traversal.omitted_nodes,
            omitted_paths=(
                traversal.omitted_paths + len(scored) - path_offset - max_paths
            ),
            hop_limit_reached=traversal.hop_limit_reached,
            node_limit_reached=traversal.node_limit_reached,
            next_path_offset=path_offset + max_paths,
        )

    raw_rejected_count = len(rejected_paths)
    rejected_by_endpoints: dict[tuple[str, str], dict[str, Any]] = {}
    for rejected in rejected_paths:
        nodes = rejected.get("nodes", [])
        if not isinstance(nodes, list) or not nodes:
            endpoint_key = ("", "")
        else:
            endpoint_key = min(
                (str(nodes[0]), str(nodes[-1])),
                (str(nodes[-1]), str(nodes[0])),
            )
        current = rejected_by_endpoints.get(endpoint_key)
        if current is None or _rejected_path_rank(
            rejected,
            selection,
            node_relevance,
        ) < _rejected_path_rank(current, selection, node_relevance):
            rejected_by_endpoints[endpoint_key] = rejected
    rejected_paths = sorted(
        rejected_by_endpoints.values(),
        key=lambda path: _rejected_path_rank(path, selection, node_relevance),
    )
    omitted_rejected_paths = max(
        0,
        raw_rejected_count - min(len(rejected_paths), max_paths),
    )
    rejected_paths = rejected_paths[:max_paths]
    response = _graph_retrieve_envelope(
        repo_path=repo_path,
        question=question,
        selection=selection,
        anchors=anchor_values,
        routing=routing,
        filters=filters,
        paths=paths,
        rejected_paths=rejected_paths,
        traversal=traversal,
        filtered_edge_count=len(edges),
        hub_threshold=threshold,
        max_hops=max_hops,
        max_nodes=max_nodes,
        max_paths=max_paths,
        path_offset=path_offset,
        evidence_bytes=evidence_bytes,
        max_evidence_bytes=max_evidence_bytes,
        max_estimated_tokens=max_estimated_tokens,
        diagnostics=diagnostics,
        duplicate_paths=duplicate_paths,
    )
    response["counts"]["omitted_rejected_paths"] = omitted_rejected_paths
    return response


def _graph_endpoint_ids(values: list[str], field: str) -> tuple[str, ...]:
    if not isinstance(values, list) or not values:
        raise _invalid(
            "Graph endpoint lists must be non-empty lists of strings",
            field=field,
        )
    if any(not isinstance(value, str) or not value for value in values):
        raise _invalid("Graph endpoints must be non-empty strings", field=field)
    return tuple(dict.fromkeys(values))


def _require_graph_endpoints(
    repo_path: Path,
    indexed_nodes: dict[str, dict[str, Any]],
    node_ids: tuple[str, ...],
) -> None:
    missing_ids = list(dict.fromkeys(
        node_id for node_id in node_ids if node_id not in indexed_nodes
    ))
    if missing_ids:
        raise GraphContractError(
            "GRAPH_ENDPOINT_NOT_FOUND",
            "Graph endpoint is not indexed",
            {"repo": str(repo_path), "missing_ids": missing_ids},
        )


def _validate_graph_traversal_edges(
    edges: Sequence[GraphEdge],
    indexed_nodes: dict[str, dict[str, Any]],
) -> None:
    for edge_index, edge in enumerate(edges):
        missing = [
            node_id
            for node_id in (edge.from_id, edge.to_id)
            if node_id not in indexed_nodes
        ]
        if missing:
            raise GraphContractError(
                "GRAPH_ENDPOINT_NOT_FOUND",
                "Graph edge endpoint is not indexed",
                {"edge_index": edge_index, "missing_ids": missing},
            )


def _graph_budget_int(
    value: int,
    field: str,
    minimum: int,
    maximum: int,
) -> None:
    if (
        not isinstance(value, int)
        or isinstance(value, bool)
        or not minimum <= value <= maximum
    ):
        raise _invalid(
            "Graph retrieval limit is out of range",
            field=field,
            value=value,
            minimum=minimum,
            maximum=maximum,
        )


def _validate_graph_evidence_budgets(
    max_evidence_bytes: int,
    max_estimated_tokens: int,
) -> None:
    _graph_budget_int(
        max_evidence_bytes,
        "max_evidence_bytes",
        1_024,
        MAX_GRAPH_EVIDENCE_BYTES,
    )
    _graph_budget_int(
        max_estimated_tokens,
        "max_estimated_tokens",
        256,
        MAX_GRAPH_ESTIMATED_TOKENS,
    )


def _validate_graph_traversal_budgets(
    max_hops: int,
    max_nodes: int,
    max_paths: int,
    path_offset: int,
) -> None:
    _graph_budget_int(max_hops, "max_hops", 1, 6)
    _graph_budget_int(max_nodes, "max_nodes", 2, 512)
    _graph_budget_int(max_paths, "max_paths", 1, 32)
    _graph_budget_int(path_offset, "path_offset", 0, 256)


def _graph_filter_envelope(
    namespaces: list[str] | None,
    edge_types: list[str] | None,
    resolutions: list[str] | None,
    direction: GraphDirection,
) -> dict[str, Any]:
    return {
        "namespaces": list(dict.fromkeys(namespaces)) if namespaces is not None else None,
        "edge_types": list(dict.fromkeys(edge_types)) if edge_types is not None else None,
        "resolutions": (
            list(dict.fromkeys(resolutions))
            if resolutions is not None
            else ["exact", "declared"]
        ),
        "direction": direction,
    }


def _hydrate_graph_path(
    repo_path: Path,
    store: IndexStore,
    indexed_nodes: dict[str, dict[str, Any]],
    path: GraphPath,
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    steps: list[dict[str, Any]] = []
    evidence_bytes = 0
    for step in path.steps:
        evidence = step.edge.evidence
        span = store.get_file_content(
            repo_path,
            evidence.file,
            start_line=evidence.line,
            end_line=evidence.line,
        )
        if span is None or not span.get("content"):
            return None, {
                "code": "EVIDENCE_UNAVAILABLE",
                "severity": "warning",
                "message": "Graph edge evidence could not be hydrated from cache",
                "details": {
                    "file": evidence.file,
                    "line": evidence.line,
                    "from": step.edge.from_id,
                    "to": step.edge.to_id,
                },
            }
        content = str(span["content"])
        evidence_bytes += len(content.encode("utf-8"))
        steps.append({
            "traversed": step.traversed,
            "edge": step.edge.to_dict(),
            "evidence_span": {
                "file": evidence.file,
                "start_line": evidence.line,
                "end_line": evidence.line,
                "content": content,
            },
        })
    return {
        "nodes": [
            _graph_node_ref(indexed_nodes[node_id]) for node_id in path.node_ids
        ],
        "steps": steps,
        "evidence_bytes": evidence_bytes,
    }, None


def _rejected_graph_path(
    path: GraphPath,
    reason: str,
    *,
    required_terms: tuple[str, ...] = (),
    high_degree_nodes: tuple[str, ...] = (),
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "nodes": list(path.node_ids),
        "reason": reason,
        "steps": [
            {
                "traversed": step.traversed,
                "edge": {
                    "from": step.edge.from_id,
                    "to": step.edge.to_id,
                    "type": step.edge.type,
                    "directed": step.edge.directed,
                    "namespace": step.edge.namespace,
                    "resolution": step.edge.resolution,
                    "evidence": {
                        "file": step.edge.evidence.file,
                        "line": step.edge.evidence.line,
                    },
                },
            }
            for step in path.steps
        ],
    }
    if required_terms:
        result["required_bridge_terms"] = list(required_terms)
    if high_degree_nodes:
        result["high_degree_nodes"] = list(high_degree_nodes)
    return result


def _rejected_path_rank(
    path: dict[str, Any],
    selection: GraphAnchorSelection,
    node_relevance: dict[str, float],
) -> tuple:
    nodes = path.get("nodes", [])
    if not isinstance(nodes, list) or not nodes:
        return (0, 0.0, 0, str(path.get("reason") or ""), ())
    anchor_rank = {
        anchor.node_id: len(selection.anchors) - index
        for index, anchor in enumerate(selection.anchors)
    }
    endpoint_ids = (str(nodes[0]), str(nodes[-1]))
    anchor_signal = sum(anchor_rank.get(node_id, 0) for node_id in endpoint_ids)
    relevance = sum(node_relevance.get(node_id, 0.0) for node_id in endpoint_ids)
    return (
        -anchor_signal,
        -relevance,
        len(nodes),
        str(path.get("reason") or ""),
        tuple(str(node_id) for node_id in nodes),
    )


def _graph_budget_envelope(
    traversal: GraphTraversalResult,
    *,
    max_hops: int,
    max_nodes: int,
    max_paths: int,
    path_offset: int,
    evidence_bytes: int,
    max_evidence_bytes: int,
    max_estimated_tokens: int,
) -> dict[str, Any]:
    return {
        "max_hops": max_hops,
        "max_nodes": max_nodes,
        "max_paths": max_paths,
        "path_offset": path_offset,
        "evidence_bytes": evidence_bytes,
        "estimated_tokens": ceil(evidence_bytes / 4),
        "max_evidence_bytes": max_evidence_bytes,
        "max_estimated_tokens": max_estimated_tokens,
        "hop_limit_reached": traversal.hop_limit_reached,
        "node_limit_reached": traversal.node_limit_reached,
        "next_path_offset": traversal.next_path_offset,
    }


def _graph_anchor_values(
    selection: GraphAnchorSelection,
    indexed_nodes: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    reason_kind = "explicit_seed" if selection.mode == "explicit" else "inferred"
    return [
        {
            "node": _graph_node_ref(indexed_nodes[anchor.node_id]),
            "matched_symbol_id": anchor.matched_symbol_id,
            "name": anchor.name,
            "score": anchor.score,
            "reason": {
                "kind": reason_kind,
                "matched_terms": list(anchor.matched_terms),
                "match_scope": list(anchor.match_scope),
            },
        }
        for anchor in selection.anchors
    ]


def _graph_question_routing(
    question: str,
    *,
    explicit: bool,
) -> dict[str, str]:
    terms = set(graph_text_terms(question))
    measurement_terms = set(graph_text_terms("exact measured result when"))
    relation_terms = set(graph_text_terms(
        "become bridge connect define evidence improved link propose related "
        "relation relationship shows support"
    ))
    if not explicit and terms & measurement_terms:
        return {
            "kind": "suppressed",
            "reason": "attribute_or_measurement_question",
        }
    if explicit or terms & relation_terms:
        return {"kind": "relationship", "reason": "relationship_intent"}
    return {"kind": "suppressed", "reason": "non_relationship_question"}


def _graph_node_priority(
    symbol: dict[str, Any],
    question_terms: set[str],
) -> float:
    metadata = symbol.get("metadata")
    frontmatter = metadata.get("frontmatter") if isinstance(metadata, dict) else None
    fields = [
        str(symbol.get("name") or ""),
        str(symbol.get("qualified_name") or ""),
        str(symbol.get("file_path") or ""),
        str(symbol.get("summary") or ""),
        " ".join(str(item) for item in symbol.get("keywords", []) if isinstance(item, str)),
    ]
    if isinstance(frontmatter, dict):
        fields.extend(
            str(frontmatter.get(key) or "")
            for key in ("title", "description", "source", "tags")
        )
    hits = question_terms & set(graph_text_terms(" ".join(fields)))
    return float(len(hits))


def _graph_node_text(symbol: dict[str, Any]) -> str:
    metadata = symbol.get("metadata")
    frontmatter = metadata.get("frontmatter") if isinstance(metadata, dict) else None
    title = frontmatter.get("title") if isinstance(frontmatter, dict) else ""
    return " ".join((
        str(symbol.get("name") or ""),
        str(symbol.get("file_path") or ""),
        str(title or ""),
    ))


def _graph_degrees(edges: Sequence[GraphEdge]) -> dict[str, int]:
    degrees: dict[str, int] = defaultdict(int)
    for edge in edges:
        degrees[edge.from_id] += 1
        degrees[edge.to_id] += 1
    return dict(degrees)


def _question_path_key(path: GraphPath) -> tuple:
    return min(path.node_ids, tuple(reversed(path.node_ids)))


def _graph_path_score(
    path: GraphPath,
    selection: GraphAnchorSelection,
    node_priorities: dict[str, float],
    evidence_terms: set[str],
    question_terms: set[str],
    degrees: dict[str, int],
    hub_threshold: int,
) -> tuple[float, dict[str, float]]:
    anchor_scores = {
        anchor.node_id: float(anchor.score or 0.0) for anchor in selection.anchors
    }
    anchor = min(
        3.0,
        (
            anchor_scores.get(path.node_ids[0], 0.0)
            + anchor_scores.get(path.node_ids[-1], 0.0)
        ) / 50.0,
    )
    endpoint = min(
        4.0,
        (
            node_priorities.get(path.node_ids[0], 0.0)
            + node_priorities.get(path.node_ids[-1], 0.0)
        ) / 4.0,
    )
    evidence = len(evidence_terms & question_terms) / max(1, len(question_terms))
    hop = 1.0 / len(path.steps)
    hub_penalty = sum(
        max(0, degrees.get(node_id, 0) - hub_threshold) / max(1, hub_threshold)
        for node_id in path.node_ids[1:-1]
    )
    direct = 0.5 if len(path.steps) == 1 else 0.0
    score = anchor + endpoint + evidence + hop + direct - (0.25 * hub_penalty)
    components = {
        "anchor": round(anchor, 6),
        "endpoint": round(endpoint, 6),
        "evidence": round(evidence, 6),
        "hop": round(hop, 6),
        "direct": round(direct, 6),
        "hub_penalty": round(hub_penalty, 6),
    }
    return round(score, 6), components


def _graph_retrieve_envelope(
    *,
    repo_path: Path,
    question: str,
    selection: GraphAnchorSelection,
    anchors: list[dict[str, Any]],
    routing: dict[str, str],
    filters: dict[str, Any],
    paths: list[dict[str, Any]],
    rejected_paths: list[dict[str, Any]],
    traversal: GraphTraversalResult | None,
    filtered_edge_count: int,
    hub_threshold: int,
    max_hops: int,
    max_nodes: int,
    max_paths: int,
    path_offset: int,
    evidence_bytes: int,
    max_evidence_bytes: int,
    max_estimated_tokens: int,
    diagnostics: list[dict[str, Any]],
    duplicate_paths: int = 0,
) -> dict[str, Any]:
    if traversal is None:
        traversal = GraphTraversalResult(
            paths=(),
            filtered_edge_count=filtered_edge_count,
            examined_nodes=0,
            examined_paths=0,
            omitted_nodes=0,
            omitted_paths=0,
            hop_limit_reached=False,
            node_limit_reached=False,
            next_path_offset=None,
        )
    return {
        "schema_version": GRAPH_SCHEMA_VERSION,
        "repo": str(repo_path),
        "question": question,
        "selection": selection.mode,
        "question_terms": list(selection.question_terms),
        "anchors": anchors,
        "routing": routing,
        "filters": filters,
        "hub_threshold": hub_threshold,
        "paths": paths,
        "rejected_paths": rejected_paths,
        "counts": {
            "filtered_edges": filtered_edge_count,
            "examined_nodes": traversal.examined_nodes,
            "examined_paths": traversal.examined_paths,
            "returned_paths": len(paths),
            "rejected_paths": len(rejected_paths),
            "duplicate_paths": duplicate_paths,
            "omitted_rejected_paths": 0,
            "omitted_nodes": traversal.omitted_nodes,
            "omitted_paths": traversal.omitted_paths,
        },
        "budget": _graph_budget_envelope(
            traversal,
            max_hops=max_hops,
            max_nodes=max_nodes,
            max_paths=max_paths,
            path_offset=path_offset,
            evidence_bytes=evidence_bytes,
            max_evidence_bytes=max_evidence_bytes,
            max_estimated_tokens=max_estimated_tokens,
        ),
        "diagnostics": diagnostics,
    }


def _graph_node_ref(symbol: dict[str, Any]) -> dict[str, Any]:
    return GraphNodeRef(
        id=symbol["id"],
        namespace="loci",
        kind=symbol["kind"],
        attributes={
            "language": symbol["language"],
            "file": symbol["file_path"],
            "line": symbol.get("line", 0),
            "end_line": symbol.get("end_line", 0),
        },
    ).to_dict()


def _invalid(message: str, **details: object) -> GraphContractError:
    return GraphContractError("INVALID_INPUT", message, dict(details))
