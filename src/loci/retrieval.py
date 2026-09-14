"""Fixed deterministic graph-backed context retrieval."""
from __future__ import annotations

from collections import Counter, defaultdict, deque
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Mapping, Sequence

from ._retrieval_output import (
    Addition,
    ItemInput,
    LIMITS,
    RelationInput,
    RetrievalPacker,
)
from ._retrieval_source import (
    RetrievalSource,
    _source_node,
    edge_identity,
    preview_span,
    snapshot_id,
)
from .graph.anchors import GraphAnchor, select_graph_anchors
from .graph.contracts import GraphContractError, GraphEdge
from .graph.state import GraphIndexState
from .graph.traversal import GraphTraversalStep, graph_adjacency, graph_text_terms
from .storage.index_store import IndexStore


_FAMILY_TYPES = (
    ("calls", frozenset({"calls"})),
    ("types", frozenset({
        "uses_type", "extends", "implements", "embeds", "supertrait",
        "impl_trait", "impl_self_type", "references_type",
    })),
    ("values", frozenset({"references"})),
    ("imports", frozenset({"imports", "imports_type"})),
)
_TYPE_TO_FAMILY = {
    edge_type: index
    for index, (_, edge_types) in enumerate(_FAMILY_TYPES)
    for edge_type in edge_types
}
_ALLOWED_RESOLUTIONS = frozenset({"exact", "declared", "import-resolved"})
_NATIVE_KINDS = frozenset({"file", "package", "crate", "module"})


@dataclass(frozen=True)
class _SelectedAnchor:
    node_id: str
    score: float
    matched_terms: tuple[str, ...]
    match_scope: tuple[str, ...]


@dataclass(frozen=True)
class _Visit:
    node_id: str
    anchor_index: int
    depth: int
    lineage: tuple[str, ...]
    why: str


def retrieve_context(
    repo: Path,
    store: IndexStore,
    nodes: dict[str, dict],
    state: GraphIndexState,
    query: str = "",
    *,
    seed_ids: list[str] | None = None,
    coverage: str = "unknown",
) -> dict:
    """Return normal-graph-v1 context without caller-selected graph controls."""
    seeds = _validate_request(query, seed_ids)
    source = RetrievalSource(repo, store, nodes, state)
    anchors, selection, matching, lookup, selection_omissions = _select_anchors(
        nodes, source, query, seeds,
    )
    anchor_values = [
        {
            "node_id": anchor.node_id,
            "score": anchor.score,
            "matched_terms": list(anchor.matched_terms),
            "match_scope": list(anchor.match_scope),
        }
        for anchor in anchors
    ]
    packer = RetrievalPacker(
        repo,
        snapshot=snapshot_id(state, source.file_hashes),
        selection=selection,
        scope={
            "source": "indexed_supported_source",
            "coverage": coverage if coverage in {"complete", "partial", "unknown"} else "unknown",
            "matching": matching,
            "relationships": "known_static_relationships",
            "exhaustive": False,
        },
        anchors=anchor_values,
    )
    packer.usage["lookup_bytes"] = lookup["bytes"]
    packer.usage["lookup_files"] = lookup["files"]
    for reason, count in selection_omissions.items():
        packer.omit(reason, count)
    if not anchors:
        packer.omit("no_anchor")
        return packer.finish()

    query_terms = set(graph_text_terms(query))
    eligible_edges = _eligible_edges(state.edges, nodes)
    adjacency = graph_adjacency(eligible_edges, direction="either")
    degrees = Counter()
    for edge in eligible_edges:
        degrees[edge.from_id] += 1
        if edge.to_id != edge.from_id:
            degrees[edge.to_id] += 1

    visited: set[str] = set()
    expanded: set[str] = set()
    frontier: list[_Visit] = []
    for index, anchor in enumerate(anchors):
        if anchor.node_id in visited:
            packer.omit("alternative_path")
            continue
        node = nodes[anchor.node_id]
        if len(visited) >= LIMITS["max_nodes"]:
            packer.omit("node_limit")
            break
        visited.add(anchor.node_id)
        addition, missing_source = _anchor_addition(source, node, index, anchor)
        if missing_source:
            packer.omit("source_unavailable")
        packer.add(addition)
        frontier.append(_Visit(anchor.node_id, index, 0, (), "Selected anchor"))

    for depth in range(LIMITS["max_hops"] + 1):
        layer = deque(visit for visit in frontier if visit.depth == depth)
        frontier = [visit for visit in frontier if visit.depth != depth]
        expanded_layer: list[_Visit] = []
        while layer:
            visit = layer.popleft()
            if visit.node_id in expanded:
                continue
            expanded.add(visit.node_id)
            expanded_layer.append(visit)
            node = nodes[visit.node_id]
            _count_unresolved(packer, state, visit.node_id)
            for lifted in _ownership_lifts(source, node, query_terms):
                target = lifted.node
                target_id = str(target["id"])
                ownership = (
                    (target_id, str(node["id"]), lifted.basis)
                    if target.get("kind") == "file" and node.get("kind") not in _NATIVE_KINDS
                    else (str(node["id"]), target_id, lifted.basis)
                )
                if target_id in visited:
                    if ownership not in {
                        (item["owner_id"], item["member_id"], item["basis"])
                        for item in packer.state.ownership
                    }:
                        packer.add(Addition(nodes=(node, target), ownership=(ownership,)))
                    continue
                if len(visited) >= LIMITS["max_nodes"]:
                    packer.omit("node_limit")
                    continue
                addition, missing_source = _lift_addition(
                    source, node, target, lifted.basis, depth,
                )
                if missing_source:
                    packer.omit("source_unavailable")
                if packer.add(addition):
                    visited.add(target_id)
                    layer.append(_Visit(target_id, visit.anchor_index, depth,
                                        (*visit.lineage, visit.node_id),
                                        "Validated ownership context"))

        ordered = sorted(expanded_layer, key=lambda value: (value.anchor_index, value.node_id))
        per_anchor: dict[int, list[tuple[_Visit, list[GraphTraversalStep]]]] = defaultdict(list)
        for visit in ordered:
            neighbors = list(adjacency.get(visit.node_id, ()))
            packer.usage["eligible_edges_considered"] += len(neighbors)
            ranked = _ranked_neighbors(neighbors, nodes, query_terms, degrees)
            if len(ranked) > LIMITS["max_neighbors"]:
                packer.omit("neighbor_limit", len(ranked) - LIMITS["max_neighbors"])
                ranked = ranked[:LIMITS["max_neighbors"]]
            if depth == LIMITS["max_hops"]:
                packer.omit("hop_limit", len(ranked))
                continue
            per_anchor[visit.anchor_index].append((visit, ranked))

        next_visits: list[_Visit] = []
        scheduler: dict[int, list[deque[tuple[_Visit, GraphTraversalStep]]]] = {}
        for anchor_index in sorted(per_anchor):
            queues = [deque() for _ in range(8)]
            for visit, steps in per_anchor[anchor_index]:
                for step in steps:
                    queues[_queue_index(step)].append((visit, step))
            scheduler[anchor_index] = queues
        while any(queue for queues in scheduler.values() for queue in queues):
            for anchor_index in sorted(scheduler):
                queues = scheduler[anchor_index]
                for queue in queues:
                    if not queue:
                        continue
                    visit, step = queue.popleft()
                    target_id = step.to_id
                    if target_id in (*visit.lineage, visit.node_id):
                        packer.omit("cycle")
                        continue
                    already_visited = target_id in visited
                    if not already_visited and len(visited) >= LIMITS["max_nodes"]:
                        packer.omit("node_limit")
                        continue
                    packer.usage["edges_traversed"] += 1
                    target = nodes[target_id]
                    proof = source.proof(step.edge)
                    if proof is None:
                        packer.omit("proof_unavailable")
                        if not already_visited:
                            visited.add(target_id)
                        continue
                    addition, missing_source = _relation_addition(
                        source, nodes[visit.node_id], target, step, proof, depth + 1,
                        include_item=not already_visited,
                    )
                    if missing_source:
                        packer.omit("source_unavailable")
                    if not already_visited:
                        visited.add(target_id)
                    if packer.add(addition):
                        if already_visited:
                            packer.omit("alternative_path")
                        else:
                            next_visits.append(_Visit(
                                target_id, anchor_index, depth + 1,
                                (*visit.lineage, visit.node_id),
                                f"{_FAMILY_TYPES[_TYPE_TO_FAMILY[step.edge.type]][0]} relationship",
                            ))
        frontier.extend(next_visits)

    packer.usage["nodes_examined"] = len(visited)
    return packer.finish()


@dataclass(frozen=True)
class _Lift:
    node: Mapping[str, Any]
    basis: str


def _ownership_lifts(
    source: RetrievalSource,
    node: Mapping[str, Any],
    query_terms: set[str],
) -> tuple[_Lift, ...]:
    if node.get("kind") not in _NATIVE_KINDS:
        owner = source.file_owner(node)
        return (_Lift(owner, "indexed_file"),) if owner is not None else ()
    basis = {
        "file": "indexed_file",
        "package": "go_package",
        "crate": "rust_crate",
        "module": "swift_module",
    }[str(node["kind"])]
    return tuple(
        _Lift(member, basis)
        for member in source.endpoint_members(
            node, query_terms, limit=LIMITS["max_owner_members"],
        )
    )


def _anchor_addition(
    source: RetrievalSource,
    node: Mapping[str, Any],
    index: int,
    anchor: _SelectedAnchor,
) -> tuple[Addition, bool]:
    nodes: list[Mapping[str, Any]] = [node]
    ownership = []
    items = []
    missing_source = False
    if _source_node(node) or node.get("kind") == "file":
        try:
            full = source.definition(node)
            preview, complete = preview_span(full, LIMITS["max_anchor_source_bytes"])
            items.append(ItemInput(node, "anchor", 0, "Explicit source identity" if not anchor.matched_terms
                                   else "Query matches " + ", ".join(anchor.matched_terms[:4]),
                                   full, preview, complete))
        except (KeyError, UnicodeError, ValueError):
            missing_source = True
    owner = source.file_owner(node)
    if owner is not None:
        nodes.append(owner)
        ownership.append((str(owner["id"]), str(node["id"]), "indexed_file"))
    return Addition(tuple(nodes), tuple(items), tuple(ownership)), missing_source


def _lift_addition(
    source: RetrievalSource,
    owner: Mapping[str, Any],
    member: Mapping[str, Any],
    basis: str,
    depth: int,
) -> tuple[Addition, bool]:
    if member.get("kind") == "file" and owner.get("kind") not in _NATIVE_KINDS:
        return Addition(
            nodes=(owner, member),
            ownership=((str(member["id"]), str(owner["id"]), "indexed_file"),),
        ), False
    missing_source = False
    try:
        full = source.definition(member)
        preview, complete = preview_span(full, LIMITS["max_related_source_bytes"])
        items = (ItemInput(member, "related", depth, "Validated ownership context",
                           full, preview, complete),)
    except (KeyError, UnicodeError, ValueError):
        items = ()
        missing_source = True
    return Addition(
        nodes=(owner, member),
        items=items,
        ownership=((str(owner["id"]), str(member["id"]), basis),),
    ), missing_source


def _relation_addition(
    source: RetrievalSource,
    current: Mapping[str, Any],
    target: Mapping[str, Any],
    step: GraphTraversalStep,
    proof: tuple,
    depth: int,
    *,
    include_item: bool,
) -> tuple[Addition, bool]:
    nodes: list[Mapping[str, Any]] = [current, target]
    items = []
    ownership = []
    missing_source = False
    if include_item and _source_node(target):
        try:
            full = source.definition(target)
            preview, complete = preview_span(full, LIMITS["max_related_source_bytes"])
            items.append(ItemInput(target, "related", depth,
                                   f"Selected by {step.edge.type}", full, preview, complete))
        except (KeyError, UnicodeError, ValueError):
            missing_source = True
        owner = source.file_owner(target)
        if owner is not None:
            nodes.append(owner)
            ownership.append((str(owner["id"]), str(target["id"]), "indexed_file"))
    configuration = source.resolution_configuration(step.edge)
    return Addition(
        nodes=tuple(nodes),
        items=tuple(items),
        ownership=tuple(ownership),
        relation=RelationInput(step.edge, step.traversed, proof, configuration),
    ), missing_source


def _eligible_edges(
    edges: Sequence[GraphEdge],
    nodes: Mapping[str, Mapping[str, Any]],
) -> tuple[GraphEdge, ...]:
    unique = {
        edge_identity(edge): edge
        for edge in edges
        if edge.namespace == "loci"
        and edge.type in _TYPE_TO_FAMILY
        and edge.resolution in _ALLOWED_RESOLUTIONS
        and edge.from_id in nodes and edge.to_id in nodes
    }
    return tuple(unique[key] for key in sorted(unique))


def _ranked_neighbors(
    neighbors: Sequence[GraphTraversalStep],
    nodes: Mapping[str, Mapping[str, Any]],
    query_terms: set[str],
    degrees: Mapping[str, int],
) -> list[GraphTraversalStep]:
    def key(step: GraphTraversalStep) -> tuple[Any, ...]:
        node = nodes[step.to_id]
        text = " ".join(str(node.get(value, "")) for value in
                        ("name", "file_path", "signature"))
        overlap = len(query_terms & set(graph_text_terms(text)))
        edge = step.edge
        return (
            _queue_index(step), -overlap, degrees.get(step.to_id, 0), step.to_id,
            edge.type, edge.from_id, edge.to_id, edge.evidence.file,
            edge.evidence.line, edge.evidence.content_hash, step.traversed,
        )

    grouped: dict[int, list[GraphTraversalStep]] = defaultdict(list)
    for step in neighbors:
        grouped[_queue_index(step)].append(step)
    queues = [deque(sorted(grouped[index], key=key)) for index in range(8)]
    result = []
    while any(queues):
        for queue in queues:
            if queue:
                result.append(queue.popleft())
    return result


def _queue_index(step: GraphTraversalStep) -> int:
    return _TYPE_TO_FAMILY[step.edge.type] * 2 + (0 if step.traversed == "forward" else 1)


def _select_anchors(
    nodes: Mapping[str, dict[str, Any]],
    source: RetrievalSource,
    query: str,
    seeds: tuple[str, ...],
) -> tuple[
    tuple[_SelectedAnchor, ...], dict[str, Any], str, dict[str, int], Counter[str]
]:
    omissions: Counter[str] = Counter()
    if seeds:
        missing = [seed for seed in seeds if seed not in nodes]
        if missing:
            raise GraphContractError("GRAPH_ENDPOINT_NOT_FOUND", "Source seed is not indexed",
                                     {"missing_ids": missing})
        anchors = tuple(_SelectedAnchor(seed, 0.0, (), ()) for seed in seeds)
        return anchors, {"mode": "explicit", "candidate_count": len(anchors),
                         "omitted_candidates": 0}, "explicit_ids", {"bytes": 0, "files": 0}, omissions

    exact = _exact_file_anchor(nodes, query)
    if exact is not None:
        anchor = _SelectedAnchor(str(exact["id"]), 0.0, (), ("file_path",))
        return (anchor,), {"mode": "file", "candidate_count": 1,
                           "omitted_candidates": 0}, "exact_file", {"bytes": 0, "files": 0}, omissions

    eligible = [node for node in nodes.values() if _source_node(node)]
    selection = select_graph_anchors(eligible, query, (), max_anchors=LIMITS["max_anchors"])
    if selection.anchors:
        anchors = tuple(_from_graph_anchor(anchor) for anchor in selection.anchors)
        if selection.omitted_candidates:
            omissions["anchor_limit"] += selection.omitted_candidates
        if selection.qualified_candidates > 1:
            omissions["ambiguous_anchor"] += selection.qualified_candidates - 1
        return anchors, {
            "mode": "inferred",
            "candidate_count": selection.qualified_candidates,
            "omitted_candidates": selection.omitted_candidates,
        }, "symbol_metadata", {"bytes": 0, "files": 0}, omissions

    literal, stats, limited, unavailable = _literal_anchors(nodes, source, query)
    if limited:
        omissions["lookup_limit"] += 1
    if unavailable:
        omissions["source_unavailable"] += unavailable
    omitted = max(0, len(literal) - LIMITS["max_anchors"])
    anchors = tuple(literal[:LIMITS["max_anchors"]])
    if omitted:
        omissions["anchor_limit"] += omitted
    if len(literal) > 1:
        omissions["ambiguous_anchor"] += len(literal) - 1
    return anchors, {"mode": "literal", "candidate_count": len(literal),
                     "omitted_candidates": omitted}, "source_literal", stats, omissions


def _from_graph_anchor(anchor: GraphAnchor) -> _SelectedAnchor:
    return _SelectedAnchor(anchor.node_id, float(anchor.score or 0.0),
                           anchor.matched_terms, anchor.match_scope)


def _exact_file_anchor(
    nodes: Mapping[str, Mapping[str, Any]], query: str,
) -> Mapping[str, Any] | None:
    value = query.strip()
    if value.startswith("./"):
        value = value[2:]
    path = PurePosixPath(value)
    if not value or path.is_absolute() or ".." in path.parts or path.as_posix() != value:
        return None
    matches = [
        node for node in nodes.values()
        if node.get("file_path") == value
        and (node.get("kind") == "file" or _markdown_page_root(node))
    ]
    return matches[0] if len(matches) == 1 else None


def _literal_anchors(
    nodes: Mapping[str, dict[str, Any]], source: RetrievalSource, query: str,
) -> tuple[list[_SelectedAnchor], dict[str, int], bool, int]:
    needle = query.encode("utf-8")
    if not needle:
        return [], {"bytes": 0, "files": 0}, False, 0
    representatives: dict[str, dict[str, Any]] = {}
    for node in nodes.values():
        file = node.get("file_path")
        if not isinstance(file, str):
            continue
        if node.get("kind") == "file":
            representatives[file] = node
        elif _markdown_page_root(node):
            representatives.setdefault(file, node)
    files = [(file, representatives[file]) for file in sorted(representatives)
             if file in source.file_hashes]
    selected: dict[str, _SelectedAnchor] = {}
    scanned_bytes = scanned_files = matches = 0
    limited = False
    unavailable = 0
    symbols_by_file: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for node in nodes.values():
        if _source_node(node):
            symbols_by_file[str(node["file_path"])].append(node)
    for file, file_node in files:
        if scanned_files >= LIMITS["max_lookup_files"]:
            limited = True
            break
        try:
            raw, _ = source.source.cache.file(file, source.file_hashes[file])
        except (UnicodeError, ValueError):
            unavailable += 1
            continue
        if scanned_bytes + len(raw) > LIMITS["max_lookup_bytes"]:
            limited = True
            break
        scanned_files += 1
        scanned_bytes += len(raw)
        offset = raw.find(needle)
        while offset >= 0:
            matches += 1
            containers = [
                node for node in symbols_by_file[file]
                if int(node["byte_offset"]) <= offset
                and offset + len(needle) <= int(node["byte_offset"]) + int(node["byte_length"])
            ]
            if containers:
                node = min(containers, key=lambda value: (int(value["byte_length"]), str(value["id"])))
            else:
                node = file_node
            node_id = str(node["id"])
            selected.setdefault(node_id, _SelectedAnchor(node_id, 0.0, (), ("source_literal",)))
            if matches >= LIMITS["max_literal_matches"]:
                limited = True
                break
            offset = raw.find(needle, offset + max(1, len(needle)))
        if limited:
            break
    values = list(selected.values())
    return values, {"bytes": scanned_bytes, "files": scanned_files}, limited, unavailable


def _markdown_page_root(node: Mapping[str, Any]) -> bool:
    metadata = node.get("metadata")
    markdown = metadata.get("markdown") if isinstance(metadata, Mapping) else None
    if not isinstance(markdown, Mapping):
        return False
    return markdown.get("page_root") is True or markdown.get("root_id") == node.get("id")


def _count_unresolved(packer: RetrievalPacker, state: GraphIndexState, node_id: str) -> None:
    for record in (*state.imports, *state.symbol_references, *state.calls, *state.type_relations):
        owner = getattr(record, "source_id", getattr(record, "caller_id", None))
        if owner != node_id or getattr(record, "status", None) == "resolved":
            continue
        reason = str(getattr(record, "unresolved_reason", ""))
        if "ambiguous" in reason:
            omission = "ambiguous_relation"
        elif "external" in reason:
            omission = "external_relation"
        elif "inaccessible" in reason or "private" in reason:
            omission = "inaccessible_relation"
        elif "unsupported" in reason:
            omission = "unsupported_semantics"
        else:
            omission = "unresolved_relation"
        packer.omit(omission)


def _validate_request(query: str, seed_ids: list[str] | None) -> tuple[str, ...]:
    if not isinstance(query, str):
        raise GraphContractError("INVALID_INPUT", "query must be a string", {"field": "query"})
    if len(query.encode("utf-8")) > 4096:
        raise GraphContractError("INVALID_INPUT", "query exceeds 4096 UTF-8 bytes", {"field": "query"})
    if seed_ids is None:
        seeds: tuple[str, ...] = ()
    elif not isinstance(seed_ids, list) or any(not isinstance(value, str) or not value for value in seed_ids):
        raise GraphContractError("INVALID_INPUT", "seed_ids must be a list of non-empty strings",
                                 {"field": "seed_ids"})
    else:
        seeds = tuple(seed_ids)
    if len(seeds) > LIMITS["max_explicit_anchors"] or len(set(seeds)) != len(seeds):
        raise GraphContractError("INVALID_INPUT", "seed_ids must contain at most five unique IDs",
                                 {"field": "seed_ids"})
    if not query.strip() and not seeds:
        raise GraphContractError("INVALID_INPUT", "query or seed_ids is required", {})
    return seeds
