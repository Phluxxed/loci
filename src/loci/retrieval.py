"""Deterministic bounded target-source retrieval."""
from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Mapping

from ._retrieval_output import Addition, ItemInput, LIMITS, RetrievalPacker
from ._retrieval_source import RetrievalSource, _source_node, snapshot_id
from .graph.anchors import GraphAnchor, select_graph_anchors
from .graph.contracts import GraphContractError
from .storage.index_store import IndexStore


@dataclass(frozen=True)
class _SelectedAnchor:
    node_id: str
    score: float
    matched_terms: tuple[str, ...]
    match_scope: tuple[str, ...]
    literal_match: tuple[int, int] | None = None


@dataclass(frozen=True)
class _PreparedRetrieval:
    """Selected source and its bounded output packer."""

    source: RetrievalSource
    anchors: tuple[_SelectedAnchor, ...]
    packer: RetrievalPacker


def retrieve_context(
    repo: Path, store: IndexStore, nodes: dict[str, dict],
    file_hashes: Mapping[str, str], query: str = "", *,
    seed_ids: list[str] | None = None, coverage: str = "unknown",
) -> dict:
    """Locate source and pack selected definitions under fixed total budgets."""
    prepared = _prepare_context(repo, store, nodes, file_hashes, query,
                                seed_ids=seed_ids, coverage=coverage)
    visits = _pack_anchor_sources(prepared, nodes)
    prepared.packer.usage["nodes_examined"] = len(visits)
    return prepared.packer.finish()


def _pack_anchor_sources(
    prepared: _PreparedRetrieval,
    nodes: Mapping[str, Mapping[str, Any]],
) -> list[str]:
    """Reserve identities, then pack selected sources against their joint budget."""
    source, anchors, packer = prepared.source, prepared.anchors, prepared.packer
    if not anchors:
        packer.omit("no_anchor")
        return []
    lengths = []
    for anchor in anchors:
        try:
            lengths.append(len(source.definition(nodes[anchor.node_id]).content.encode("utf-8")))
        except (KeyError, UnicodeError, ValueError):
            lengths.append(0)
    budgets = _anchor_source_budgets(lengths)
    additions = []
    for anchor, budget in zip(anchors, budgets):
        addition, missing = _anchor_addition(source, nodes[anchor.node_id], anchor, budget)
        additions.append(addition)
        if missing:
            packer.omit("source_unavailable")
    identities = Addition(
        nodes=tuple(node for addition in additions for node in addition.nodes),
        ownership=tuple(value for addition in additions for value in addition.ownership),
    )
    if packer.add(identities):
        items = tuple(item for addition in additions for item in addition.items)
        if items and not packer.add(Addition(items=items)):
            # When even minimal excerpts cannot all fit, retain a useful subset
            # and the identities/omissions needed to re-anchor excluded source.
            for item in items:
                packer.add(Addition(items=(item,)))
    return [anchor.node_id for anchor in anchors]


def _anchor_source_budgets(lengths: list[int]) -> list[int]:
    """Share the fixed evidence budget while giving short anchors their full extent."""
    budgets = [0] * len(lengths)
    pending = {index for index, length in enumerate(lengths) if length}
    remaining = LIMITS["max_evidence_bytes"]
    while pending:
        share = remaining // len(pending)
        short = {index for index in pending if lengths[index] <= share}
        if not short:
            for index in sorted(pending):
                budgets[index] = share
            break
        for index in sorted(short):
            budgets[index] = lengths[index]
            remaining -= lengths[index]
        pending -= short
    return budgets


def _prepare_context(
    repo: Path,
    store: IndexStore,
    nodes: dict[str, dict],
    file_hashes: Mapping[str, str],
    query: str = "",
    *,
    seed_ids: list[str] | None = None,
    coverage: str = "unknown",
) -> _PreparedRetrieval:
    """Select anchors and initialize direct-source packing without traversal."""
    seeds = _validate_request(query, seed_ids)
    source = RetrievalSource(repo, store, nodes, file_hashes)
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
        store=store,
        snapshot=snapshot_id(source.file_hashes),
        selection=selection,
        scope={
            "source": "indexed_supported_source",
            "coverage": coverage if coverage in {"complete", "partial", "unknown"} else "unknown",
            "matching": matching,
            "relationships": "not_selected",
            "exhaustive": False,
        },
        anchors=anchor_values,
    )
    packer.usage["lookup_bytes"] = lookup["bytes"]
    packer.usage["lookup_files"] = lookup["files"]
    for reason, count in selection_omissions.items():
        packer.omit(reason, count)
    return _PreparedRetrieval(source, anchors, packer)


def _anchor_addition(
    source: RetrievalSource,
    node: Mapping[str, Any],
    anchor: _SelectedAnchor,
    preview_budget: int,
) -> tuple[Addition, bool]:
    nodes: list[Mapping[str, Any]] = [node]
    ownership = []
    items = []
    missing_source = True
    if _source_node(node) or node.get("kind") == "file":
        try:
            full = source.definition(node)
            missing_source = False
            items.append(ItemInput(node, "anchor", 0, "Explicit source identity" if not anchor.matched_terms
                                   else "Query matches " + ", ".join(anchor.matched_terms[:4]),
                                   full, full, True, anchor.literal_match, preview_budget))
        except (KeyError, UnicodeError, ValueError):
            missing_source = True
    owner = source.file_owner(node)
    if owner is not None:
        nodes.append(owner)
        ownership.append((str(owner["id"]), str(node["id"]), "indexed_file"))
    return Addition(tuple(nodes), tuple(items), tuple(ownership)), missing_source


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
    exact_symbols = [node for node in eligible if query.strip() in {
        node.get("name"), node.get("qualified_name"),
    }]
    selection = select_graph_anchors(exact_symbols or eligible, query, (),
                                     max_anchors=LIMITS["max_anchors"])
    if selection.anchors and exact_symbols:
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
    if not literal and selection.anchors:
        anchors = tuple(_from_graph_anchor(anchor) for anchor in selection.anchors)
        if selection.omitted_candidates:
            omissions["anchor_limit"] += selection.omitted_candidates
        if selection.qualified_candidates > 1:
            omissions["ambiguous_anchor"] += selection.qualified_candidates - 1
        return anchors, {
            "mode": "inferred",
            "candidate_count": selection.qualified_candidates,
            "omitted_candidates": selection.omitted_candidates,
        }, "symbol_metadata", stats, omissions
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
            selected.setdefault(node_id, _SelectedAnchor(
                node_id, 0.0, (), ("source_literal",),
                (offset, offset + len(needle)),
            ))
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
