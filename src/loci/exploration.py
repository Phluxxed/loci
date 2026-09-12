"""Intent-specific selection over proven graph records and cached source."""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
import hashlib
import heapq
import math
from pathlib import Path
import re
from typing import Any, Mapping

from ._exploration_output import Bundle, Relation, Span, pack_exploration
from .graph.anchors import select_graph_anchors
from .graph.contracts import GraphContractError, GraphEdge
from .graph.state import GraphIndexState
from .graph.traversal import filter_graph_edges, graph_adjacency, graph_hub_threshold
from .graph.type_relations import TYPE_EDGE_KINDS, type_site_key
from .storage.index_store import IndexStore
from .type_context import _CachedSource


INTENTS = ("locate", "type_dependencies", "dependencies", "impact")
TYPE_WEIGHTS = {"uses_type": .9, "extends": .95, "implements": .9}
IMPACT_WEIGHTS = {**TYPE_WEIGHTS, "calls": .9, "references": .7, "references_type": .75}
DEPENDENCY_WEIGHTS = {**TYPE_WEIGHTS, "calls": .9, "references": .7}
_STRUCTURAL_CONTEXTS = frozenset({"alias", "type_query", "type_argument", "constraint"})
_STOP_WORDS = frozenset("""
    a an and are as at be by can code context define definition dependency depend
    do does exact explicitly explore find for from function have how if in input
    interface is it its locate method of on only or output related relationship
    return returns show source that the their these this to type typed types use
    uses using want what when where which with you your explain field fields
""".split())
_MEMBER = re.compile(r"(?:['\"]([^'\"\n]{1,128})['\"]|([A-Za-z_$][\w$]*))\??\s*:\s*[^:;{}]*$")


def _invalid(message: str, **details: Any) -> GraphContractError:
    return GraphContractError("INVALID_INPUT", message, details)


def _terms(text: str) -> set[str]:
    text = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1 \2", text)
    text = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", text)
    values = set()
    for word in re.findall(r"[^\W_]+", text.casefold()):
        if len(word) > 4 and word.endswith("ies"):
            word = word[:-3] + "y"
        elif len(word) > 3 and word.endswith("s") and not word.endswith(("ss", "us", "is")):
            word = word[:-1]
        if len(word) >= 2 and word not in _STOP_WORDS:
            values.add(word)
    return values


def _limits(query, intent, seed_ids, max_hops, max_output_bytes, max_evidence_bytes, resolutions):
    if not isinstance(intent, str) or intent not in INTENTS:
        raise _invalid("Unsupported retrieval intent", supported_intents=list(INTENTS), fallback_intent="locate")
    if not isinstance(query, str) or len(query.encode("utf-8")) > 4096:
        raise _invalid("Query must be a string of at most 4096 UTF-8 bytes", field="query")
    if seed_ids is None:
        seed_ids = []
    if not isinstance(seed_ids, list) or len(seed_ids) > 5 or any(
        not isinstance(value, str) or not value for value in seed_ids
    ) or len(set(seed_ids)) != len(seed_ids):
        raise _invalid("Provide at most five unique, nonempty symbol IDs", field="seed_ids")
    if not query.strip() and not seed_ids:
        raise _invalid("Provide a query or explicit source symbol IDs", field="query")
    if max_hops is None:
        max_hops = {"locate": 0, "type_dependencies": 3, "dependencies": 3, "impact": 1}[intent]
    for field, value, low, high in (
        ("max_hops", max_hops, 0, 4),
        ("max_output_bytes", max_output_bytes, 2048, 262144),
        ("max_evidence_bytes", max_evidence_bytes, 0, 65536),
    ):
        if type(value) is not int or not low <= value <= high:
            raise _invalid(f"{field} must be an integer between {low} and {high}", field=field)
    if resolutions is None:
        resolutions = ["exact", "import-resolved"]
    if not isinstance(resolutions, list) or any(
        not isinstance(value, str) or value not in {"exact", "import-resolved"} for value in resolutions
    ):
        raise _invalid("Only exact and import-resolved relationships are supported", field="resolutions")
    return seed_ids, resolutions, {
        "max_hops": 0 if intent == "locate" else max_hops,
        "max_nodes": 64, "max_items": 12, "max_neighbors": 32,
        "max_output_bytes": max_output_bytes, "max_evidence_bytes": max_evidence_bytes,
    }


def _source_symbol(node: Mapping[str, Any]) -> bool:
    return (type(node.get("byte_length")) is int and node["byte_length"] > 0
            and node.get("kind") not in {"file", "package", "crate"})


class _Source:
    def __init__(self, repo: Path, store: IndexStore, nodes: Mapping[str, dict]):
        self.cache = _CachedSource(repo, store)
        self.nodes = nodes
        self.hashes = {n["file_path"]: n["content_hash"] for n in nodes.values() if n.get("kind") == "file"}
        self.definitions: dict[str, Span] = {}

    def definition(self, node: dict) -> Span:
        if node["id"] not in self.definitions:
            exact = self.cache.symbol(node)
            file = node["file_path"]
            raw, _ = self.cache.file(file, self.hashes.get(file))
            start = exact["byte_offset"]
            content = exact["source"]
            line = raw[:start].count(b"\n") + 1
            self.definitions[node["id"]] = Span(
                file, start, start + len(content.encode("utf-8")), line,
                max(line, line + content.count("\n") - int(content.endswith("\n"))),
                hashlib.sha256(raw).hexdigest(), content,
            )
        return self.definitions[node["id"]]

    def support(self, support) -> Span:
        # Call definition support hashes the symbol; other families hash files.
        if support.kind in {"caller_definition", "local_definition"}:
            node = self.nodes[support.endpoint_id]
            if node["content_hash"] != support.content_hash or node["file_path"] != support.file:
                raise ValueError("Call definition support differs from its indexed endpoint")
            return self.definition(node)
        value = self.cache.support(support)
        return Span(value["file"], value["byte_offset"],
                    value["byte_offset"] + len(value["content"].encode("utf-8")),
                    value["start_line"], value["end_line"], value["content_hash"], value["content"])

    def member_terms(self, record) -> set[str]:
        raw = record.raw
        if raw.language == "python" and raw.context == "alias":
            # Python's explicit alias marker contains a colon but does not
            # introduce a property branch requiring a field-name query.
            return set()
        data, _ = self.cache.file(raw.source_file, raw.source_hash)
        prefix = data[max(raw.owner.start_byte, raw.start_byte - 4096):raw.start_byte].decode("utf-8", errors="ignore")
        match = _MEMBER.search(prefix)
        return _terms(next(group for group in match.groups() if group)) if match else set()


@dataclass(frozen=True)
class _EdgeRecord:
    record: Any
    context: str | None
    support: tuple


def _edge_key(edge: GraphEdge) -> tuple[str, str, str, int]:
    return edge.type, edge.from_id, edge.to_id, edge.evidence.line


def _records(state: GraphIndexState) -> dict[tuple, _EdgeRecord]:
    result = {}
    references = {
        (r.raw.source_file, r.raw.source_hash, r.raw.start_byte, r.raw.end_byte): r
        for r in state.symbol_references if r.status == "resolved"
    }
    for record in sorted(state.type_relations, key=lambda r: type_site_key(r.raw)):
        if record.status == "resolved":
            key = record.raw.relation, record.source_id, record.target_id, record.raw.line
            result.setdefault(key, _EdgeRecord(record, record.raw.context, record.support))
    for record in state.calls:
        if record.status == "resolved":
            key = "calls", record.caller_id, record.target_id, record.raw.line
            support = record.support
            if record.resolution == "import-resolved":
                # The validated call joins one exact callee span. For imported
                # members that reference proves the declaring type, not the member.
                reference = references.get((record.raw.source_file, record.raw.source_hash,
                                            record.raw.callee_start_byte, record.raw.callee_end_byte))
                if reference is None:
                    continue
                support = (*support, *reference.support)
            result.setdefault(key, _EdgeRecord(record, None, support))
    for record in state.symbol_references:
        if record.status == "resolved":
            kind = "references_type" if record.binding.type_only else "references"
            key = kind, record.source_id, record.target_id, record.raw.line
            result.setdefault(key, _EdgeRecord(record, None, record.support))
    return result


def _priority(step, node, record, source, query_terms, intent, depth, degree, threshold):
    weights = DEPENDENCY_WEIGHTS if intent == "dependencies" else TYPE_WEIGHTS if intent == "type_dependencies" else IMPACT_WEIGHTS
    matches = query_terms & _terms(node["name"])
    if intent == "dependencies" and record.record.raw.language == "javascript":
        reason, relevance = "Authored JavaScript dependency", .85 + .03 * min(4, len(matches))
    elif intent in {"type_dependencies", "dependencies"}:
        member_terms = source.member_terms(record.record)
        matches |= query_terms & member_terms
        if depth == 0:
            reason, relevance = "Direct declared type", 1.0
        elif step.edge.type in {"extends", "implements"} or (
            record.context in _STRUCTURAL_CONTEXTS and not member_terms
        ):
            reason, relevance = "Authored type or heritage continuation", .95
        elif matches:
            reason, relevance = "Query matches " + ", ".join(sorted(matches)[:4]), .8
        else:
            return None
    else:
        reason, relevance = "Known static dependent", .85 + .03 * min(4, len(matches))
    hub_factor = 1.0 / (1.0 + math.log2(max(1.0, degree / threshold)))
    return weights[step.edge.type] * relevance * hub_factor * .85, reason


def explore_context(
    repo: Path, store: IndexStore, nodes: dict[str, dict], state: GraphIndexState,
    query: str = "", *, intent: str = "locate", seed_ids: list[str] | None = None,
    max_hops: int | None = None, max_output_bytes: int = 16384,
    max_evidence_bytes: int = 8192, resolutions: list[str] | None = None,
    coverage: str = "unknown",
) -> dict:
    """Select proved relationships; relevance controls delivery, never certainty."""
    seeds, resolutions, limits = _limits(query, intent, seed_ids, max_hops,
                                        max_output_bytes, max_evidence_bytes, resolutions)
    missing = [seed for seed in seeds if seed not in nodes]
    if missing:
        raise GraphContractError("GRAPH_ENDPOINT_NOT_FOUND", "Source seed is not indexed", {"missing_ids": missing})
    omissions: Counter[str] = Counter()
    eligible = [node for node in nodes.values() if _source_symbol(node)]
    supported_seeds = [seed for seed in seeds if _source_symbol(nodes[seed])]
    omissions["unsupported_anchor"] += len(seeds) - len(supported_seeds)
    if seeds and not supported_seeds:
        anchors = ()
        mode = "explicit"
    else:
        selection = select_graph_anchors(eligible, query, supported_seeds, max_anchors=5 if seeds else 3)
        anchors = selection.anchors
        mode = selection.mode
        omissions["anchor_limit"] += selection.omitted_candidates
    base = {
        "schema_version": 1, "intent": intent, "selection": mode,
        "scope": {"source": "indexed_supported_source", "coverage": coverage,
                  "relationships": {"locate": "none", "type_dependencies": "authored_types", "dependencies": "authored_dependencies", "impact": "known_static_dependents"}[intent],
                  "exhaustive": False},
        "limits": limits, "usage": {"nodes_examined": 0},
    }
    if not anchors:
        omissions["no_anchor"] += 1
        base["omissions"] = _omissions(omissions)
        return pack_exploration(base, [])
    source = _Source(repo, store, nodes)
    focus = query
    for anchor in anchors:
        focus = re.sub(r"(?<![\w$])" + re.escape(nodes[anchor.node_id]["name"]) + r"(?![\w$])", " ", focus, flags=re.I)
    query_terms = _terms(focus)
    weights = DEPENDENCY_WEIGHTS if intent == "dependencies" else TYPE_WEIGHTS if intent == "type_dependencies" else IMPACT_WEIGHTS
    edges = filter_graph_edges(state.edges, namespaces=["loci"], edge_types=list(weights), resolutions=resolutions) if resolutions else ()
    if intent == "dependencies":
        edges = tuple(edge for edge in edges if edge.type in TYPE_WEIGHTS
                      or nodes[edge.from_id].get("language") == "javascript")
    adjacency = graph_adjacency(edges, direction="incoming" if intent == "impact" else "outgoing")
    records = _records(state)
    degrees = Counter(endpoint for edge in edges for endpoint in (edge.from_id, edge.to_id))
    threshold = graph_hub_threshold(len(edges))
    unresolved = Counter(r.source_id for r in state.type_relations if r.status != "resolved")
    if intent == "dependencies":
        unresolved.update(r.source_id for r in state.symbol_references
                          if r.raw.language == "javascript" and r.status != "resolved")
        unresolved.update(r.caller_id for r in state.calls
                          if r.raw.language == "javascript" and r.status != "resolved")
    bundles = []
    visited = set()
    queue = []
    serial = 0
    for anchor in anchors:
        heapq.heappush(queue, (-1.0, serial, anchor.node_id, (), (), "Explicitly requested" if seeds else "Query matches " + ", ".join(anchor.matched_terms[:4])))
        serial += 1
    while queue and len(visited) < limits["max_nodes"]:
        negative, _, node_id, steps, lineage, why = heapq.heappop(queue)
        if node_id in visited:
            omissions["alternative_path"] += 1
            continue
        visited.add(node_id)
        node = nodes[node_id]
        if not _source_symbol(node):
            omissions["unsupported_anchor"] += 1
            continue
        try:
            span = source.definition(node)
            relation_values = []
            for step in steps:
                record = records.get(_edge_key(step.edge))
                if record is None:
                    raise ValueError("A projected relationship has no source record")
                supports = tuple(source.support(item) for item in record.support)
                relation_values.append(Relation(step.edge.to_dict(), step.traversed, supports))
            role = "anchor" if not steps else "dependency" if intent in {"type_dependencies", "dependencies"} else "dependent"
            bundles.append(Bundle({"id": node_id, "name": node["name"], "kind": node["kind"],
                                   "file": node["file_path"], "role": role, "depth": len(steps), "why": why},
                                  (span,), tuple(relation_values)))
        except (ValueError, UnicodeError, KeyError):
            omissions["source_unavailable"] += 1
            continue
        if intent == "locate":
            continue
        if intent in {"type_dependencies", "dependencies"}:
            supported = {"typescript", "python", "javascript"} if intent == "dependencies" else {"typescript", "python"}
            if node.get("language") not in supported:
                omissions["unsupported_language"] += 1
                continue
            omissions["unresolved_relation"] += unresolved[node_id]
        candidates = []
        neighbors = adjacency.get(node_id, ())
        omissions["neighbor_limit"] += max(0, len(neighbors) - limits["max_neighbors"])
        for step in neighbors[:limits["max_neighbors"]]:
            if step.to_id in (*lineage, node_id):
                omissions["cycle"] += 1
                continue
            record = records.get(_edge_key(step.edge))
            if record is None:
                omissions["source_unavailable"] += 1
                continue
            try:
                value = _priority(step, nodes[step.to_id], record, source, query_terms, intent,
                                  len(steps), degrees[step.to_id], threshold)
            except (ValueError, UnicodeError):
                omissions["source_unavailable"] += 1
                continue
            if value is None:
                omissions["not_selected"] += 1
                continue
            factor, reason = value
            candidates.append((-(-negative * factor), step.to_id, step, reason))
        candidates.sort(key=lambda c: (c[0], c[1], c[2].edge.type))
        if len(steps) >= limits["max_hops"]:
            omissions["hop_limit"] += len(candidates)
            continue
        for priority, target, step, reason in candidates:
            heapq.heappush(queue, (priority, serial, target, (*steps, step), (*lineage, node_id), reason))
            serial += 1
    if queue:
        omissions["node_limit"] += len({entry[2] for entry in queue} - visited)
    base["usage"]["nodes_examined"] = len(visited)
    base["omissions"] = _omissions(omissions)
    return pack_exploration(base, bundles)


def _omissions(values: Counter[str]) -> list[dict]:
    return [{"reason": reason, "count": count} for reason, count in sorted(values.items()) if count]
