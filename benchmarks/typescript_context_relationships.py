"""Relationship scoring for the frozen TypeScript context corpus.

The corpus describes relationships in terms of authored symbol identities.  The
graph index and graph tools use node ids and edge metadata, so this module keeps
the two namespaces separate and only joins them through an indexed symbol's
exact id.  In particular, a same-name symbol in another file is never a
candidate endpoint.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from typing import Any


_ALLOWED_RESOLUTIONS = frozenset({"exact", "declared", "import-resolved"})
_STRUCTURAL_EDGE_TYPES = frozenset({"contains", "imports", "imports_type"})
_SEMANTIC_EDGE_TYPES = frozenset({"calls", "references", "references_type"})


def _is_mapping(value: Any) -> bool:
    return isinstance(value, Mapping)


def _as_sequence(value: Any) -> list[Any]:
    """Return list-like JSON values without treating strings as collections."""

    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return list(value)
    return []


def _integer(value: Any) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value


def _edge_key(edge: Mapping[str, Any]) -> str:
    """Build a deterministic identity for one JSON graph edge."""

    try:
        return json.dumps(edge, sort_keys=True, separators=(",", ":"))
    except (TypeError, ValueError):
        # Graph packets are JSON by contract.  This fallback only makes the
        # scorer well behaved for a caller's hand-built Mapping subclass.
        return repr(sorted((str(key), repr(value)) for key, value in edge.items()))


def _edge_shape(value: Any) -> bool:
    """Recognise the GraphEdge shape, rather than arbitrary ``edge`` fields."""

    if not _is_mapping(value):
        return False
    required = {"from", "to", "type", "directed", "namespace", "resolution", "evidence"}
    return required.issubset(value) and _is_mapping(value.get("evidence"))


def _index_symbols(index: Mapping[str, Any]) -> list[dict[str, Any]]:
    raw_symbols = index.get("symbols", [])
    symbols: list[dict[str, Any]] = []
    for symbol in _as_sequence(raw_symbols):
        if _is_mapping(symbol):
            symbols.append(dict(symbol))
    return symbols


def _index_edges(index: Mapping[str, Any]) -> list[dict[str, Any]]:
    graph = index.get("graph", {})
    raw_edges: Any = graph.get("edges", []) if _is_mapping(graph) else []
    edges: list[dict[str, Any]] = []
    for edge in _as_sequence(raw_edges):
        if _edge_shape(edge):
            edges.append(dict(edge))
    return edges


def _proven_edge(edge: Mapping[str, Any]) -> bool:
    """Apply the graph resolution contract used for semantic evidence."""

    return (
        edge.get("namespace") == "loci"
        and edge.get("directed") is True
        and edge.get("resolution") in _ALLOWED_RESOLUTIONS
        and edge.get("type") not in _STRUCTURAL_EDGE_TYPES
    )


def _contained_symbol(context: Mapping[str, Any], symbol: Mapping[str, Any]) -> bool:
    expected = context.get("symbol")
    if not _is_mapping(expected):
        return False
    if (
        symbol.get("file_path") != context.get("file")
        or symbol.get("name") != expected.get("name")
        or symbol.get("kind") != expected.get("kind")
    ):
        return False

    context_start = _integer(context.get("start_byte"))
    context_end = _integer(context.get("end_byte"))
    symbol_start = _integer(symbol.get("byte_offset"))
    symbol_length = _integer(symbol.get("byte_length"))
    if None in (context_start, context_end, symbol_start, symbol_length):
        return False
    if context_end < context_start or symbol_length < 0:
        return False
    symbol_end = symbol_start + symbol_length
    return context_start <= symbol_start and symbol_end <= context_end


def _endpoint_table(
    case: Mapping[str, Any], symbols: Sequence[Mapping[str, Any]]
) -> dict[str, dict[str, Any]]:
    endpoints: dict[str, dict[str, Any]] = {}
    for context in _as_sequence(case.get("context", [])):
        if not _is_mapping(context):
            continue
        context_id = context.get("id")
        if not isinstance(context_id, str):
            continue
        expected = context.get("symbol")
        if expected is None:
            endpoints[context_id] = {
                "id": context_id,
                "file": context.get("file"),
                "status": "source_only",
                "symbol_ids": [],
                "symbols": [],
            }
            continue

        matches: dict[str, Mapping[str, Any]] = {}
        if _is_mapping(expected):
            for symbol in symbols:
                if not _contained_symbol(context, symbol):
                    continue
                symbol_id = symbol.get("id")
                if isinstance(symbol_id, str):
                    matches.setdefault(symbol_id, symbol)
        matched_symbols = [matches[symbol_id] for symbol_id in sorted(matches)]
        if not matched_symbols:
            status = "missing"
        elif len(matched_symbols) > 1:
            status = "ambiguous"
        else:
            status = "indexed"
        endpoints[context_id] = {
            "id": context_id,
            "file": context.get("file"),
            "status": status,
            "symbol_ids": sorted(matches),
            "symbols": matched_symbols,
        }
    return endpoints


def _line_interval(endpoint: Mapping[str, Any]) -> tuple[int, int] | None:
    symbols = endpoint.get("symbols", [])
    if endpoint.get("status") != "indexed" or len(symbols) != 1:
        return None
    symbol = symbols[0]
    start = _integer(symbol.get("line"))
    end = _integer(symbol.get("end_line"))
    if start is None:
        return None
    if end is None:
        end = start
    if end < start:
        return None
    return start, end


def _kind_mode(kind: Any, edges: Sequence[Mapping[str, Any]]) -> tuple[str, frozenset[str]]:
    """Choose precise kind evidence or the explicitly generic type fallback."""

    if kind == "calls":
        return "exact_kind", frozenset({"calls"})
    if isinstance(kind, str) and any(
        _proven_edge(edge) and edge.get("type") == kind for edge in edges
    ):
        return "exact_kind", frozenset({kind})
    return "generic_references_type", frozenset({"references_type"})


def _matching_edges(
    edges: Sequence[Mapping[str, Any]],
    source_id: str,
    target_id: str,
    edge_types: frozenset[str],
) -> list[dict[str, Any]]:
    return [
        dict(edge)
        for edge in edges
        if _proven_edge(edge)
        and edge.get("from") == source_id
        and edge.get("to") == target_id
        and edge.get("type") in edge_types
    ]


def _unwrap_result(value: Any) -> Any:
    """Unwrap the two MCP spelling variants without walking arbitrary fields."""

    if not _is_mapping(value):
        return value
    for key in ("structured_content", "structuredContent"):
        nested = value.get(key)
        if _is_mapping(nested):
            return nested
    return value


def _delivered_edges(delivered_results: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Extract only edges in the service's neighbor/path response structures."""

    delivered: list[dict[str, Any]] = []
    seen: set[str] = set()

    def add(edge: Any) -> None:
        if not _edge_shape(edge):
            return
        normalized = dict(edge)
        key = _edge_key(normalized)
        if key in seen:
            return
        seen.add(key)
        delivered.append(normalized)

    for result in _as_sequence(delivered_results):
        payload = _unwrap_result(result)
        if not _is_mapping(payload):
            continue

        # graph_neighbors and graph_traverse_neighbors.
        for operation_result in _as_sequence(payload.get("results", [])):
            if not _is_mapping(operation_result):
                continue
            for neighbor in _as_sequence(operation_result.get("neighbors", [])):
                if _is_mapping(neighbor):
                    add(neighbor.get("edge"))

        # graph_paths and graph_retrieve.  Rejected paths still contain the
        # actual edge objects returned by the service, so their steps count as
        # delivered graph evidence even when the path was not accepted.
        for path_key in ("paths", "rejected_paths"):
            for path in _as_sequence(payload.get(path_key, [])):
                if not _is_mapping(path):
                    continue
                for step in _as_sequence(path.get("steps", [])):
                    if _is_mapping(step):
                        add(step.get("edge"))

    return delivered


def _relationship_record(
    relationship_index: int,
    relationship: Mapping[str, Any],
    endpoints: Mapping[str, Mapping[str, Any]],
    available_edges: Sequence[Mapping[str, Any]],
    delivered_edges: Sequence[Mapping[str, Any]],
) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    source_context = relationship.get("from")
    target_context = relationship.get("to")
    source_endpoint = endpoints.get(source_context, {
        "id": source_context,
        "status": "missing",
        "symbol_ids": [],
        "symbols": [],
    })
    target_endpoint = endpoints.get(target_context, {
        "id": target_context,
        "status": "missing",
        "symbol_ids": [],
        "symbols": [],
    })
    source_status = source_endpoint.get("status", "missing")
    target_status = target_endpoint.get("status", "missing")
    mode, edge_types = _kind_mode(relationship.get("kind"), available_edges)
    available: list[dict[str, Any]] = []
    delivered: list[dict[str, Any]] = []
    issues: list[dict[str, Any]] = []

    for role, context_id, status in (
        ("from", source_context, source_status),
        ("to", target_context, target_status),
    ):
        if status in {"missing", "ambiguous", "source_only"}:
            issues.append({"relationship": relationship_index, "endpoint": role,
                           "context_id": context_id, "status": status})

    if source_status == "indexed" and target_status == "indexed":
        source_id = source_endpoint["symbol_ids"][0]
        target_id = target_endpoint["symbol_ids"][0]
        available = _matching_edges(available_edges, source_id, target_id, edge_types)
        delivered = _matching_edges(delivered_edges, source_id, target_id, edge_types)

    record = {
        "index": relationship_index,
        "from": source_context,
        "kind": relationship.get("kind"),
        "to": target_context,
        "from_status": source_status,
        "to_status": target_status,
        "match_mode": mode,
        "available": bool(available),
        "delivered": bool(delivered),
        "available_edges": available,
        "delivered_edges": delivered,
    }
    return record, available, delivered, issues


def _forbidden_target_matches(
    edge: Mapping[str, Any],
    forbidden: Mapping[str, Any],
    symbol_by_id: Mapping[str, Mapping[str, Any]],
) -> bool:
    target = symbol_by_id.get(edge.get("to"))
    return bool(
        target
        and target.get("file_path") == forbidden.get("target_file")
        and target.get("name") == forbidden.get("target_name")
    )


def _forbidden_origin_mode(
    edge: Mapping[str, Any],
    forbidden: Mapping[str, Any],
    endpoints: Mapping[str, Mapping[str, Any]],
    symbol_by_id: Mapping[str, Mapping[str, Any]],
) -> str | None:
    origin_context_id = forbidden.get("from")
    origin_endpoint = endpoints.get(origin_context_id)
    if not origin_endpoint or origin_endpoint.get("status") != "indexed":
        return None
    origin_ids = origin_endpoint.get("symbol_ids", [])
    if edge.get("from") in origin_ids:
        return "symbol"

    origin_file = origin_endpoint.get("file")
    origin_interval = _line_interval(origin_endpoint)
    origin_node = symbol_by_id.get(edge.get("from"))
    if (
        not origin_file
        or origin_interval is None
        or not origin_node
        or origin_node.get("kind") != "file"
        or origin_node.get("file_path") != origin_file
    ):
        return None

    evidence = edge.get("evidence")
    evidence_file = evidence.get("file") if _is_mapping(evidence) else None
    evidence_line = _integer(evidence.get("line")) if _is_mapping(evidence) else None
    start_line, end_line = origin_interval
    if evidence_file == origin_file and evidence_line is not None and start_line <= evidence_line <= end_line:
        return "file"
    return None


def _forbidden_records(
    case: Mapping[str, Any],
    endpoints: Mapping[str, Mapping[str, Any]],
    symbols: Sequence[Mapping[str, Any]],
    available_edges: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    symbol_by_id = {
        symbol.get("id"): symbol
        for symbol in symbols
        if isinstance(symbol.get("id"), str)
    }
    records: list[dict[str, Any]] = []
    seen: set[tuple[int, str]] = set()
    for forbidden_index, forbidden in enumerate(_as_sequence(case.get("forbidden_relationships", []))):
        if not _is_mapping(forbidden):
            continue
        mode, edge_types = _kind_mode(forbidden.get("kind"), available_edges)
        for edge in available_edges:
            if not _proven_edge(edge) or edge.get("type") not in edge_types:
                continue
            if not _forbidden_target_matches(edge, forbidden, symbol_by_id):
                continue
            origin_mode = _forbidden_origin_mode(edge, forbidden, endpoints, symbol_by_id)
            if origin_mode is None:
                continue
            edge_key = _edge_key(edge)
            dedup_key = (forbidden_index, edge_key)
            if dedup_key in seen:
                continue
            seen.add(dedup_key)
            records.append({
                "forbidden_index": forbidden_index,
                "relationship": dict(forbidden),
                "origin_mode": origin_mode,
                "match_mode": mode,
                "edge": dict(edge),
            })
    return records


def score_relationships(
    case: dict[str, Any],
    index: dict[str, Any],
    delivered_results: list[dict[str, Any]],
) -> dict[str, Any]:
    """Score authored semantic relationships against available and delivered edges.

    A relationship is credited only when both authored context endpoints resolve
    to one indexed symbol and a proven edge has those exact ids.  For non-call
    relationship kinds that the graph does not expose as a dedicated edge type,
    ``references_type`` provides a deliberately generic dependency-link signal.
    """

    symbols = _index_symbols(index)
    available_edges = _index_edges(index)
    delivered_edges = _delivered_edges(delivered_results)
    endpoints = _endpoint_table(case, symbols)

    required_records: list[dict[str, Any]] = []
    available_records: list[dict[str, Any]] = []
    delivered_records: list[dict[str, Any]] = []
    endpoint_issues: list[dict[str, Any]] = []
    for relationship_index, relationship in enumerate(_as_sequence(case.get("relationships", []))):
        if not _is_mapping(relationship):
            continue
        record, available, delivered, issues = _relationship_record(
            relationship_index,
            relationship,
            endpoints,
            available_edges,
            delivered_edges,
        )
        required_records.append(record)
        endpoint_issues.extend(issues)
        if available:
            available_records.append(record)
        if delivered:
            delivered_records.append(record)

    required_total = len(required_records)
    available_total = len(available_records)
    delivered_total = len(delivered_records)
    missing_endpoints = sorted({
        issue["context_id"] for issue in endpoint_issues if issue["status"] == "missing"
    })
    multiple_endpoints = sorted({
        issue["context_id"] for issue in endpoint_issues if issue["status"] == "ambiguous"
    })
    source_only_endpoints = sorted({
        issue["context_id"] for issue in endpoint_issues if issue["status"] == "source_only"
    })
    forbidden = _forbidden_records(case, endpoints, symbols, available_edges)
    exact_available = sum(
        1 for record in available_records if record["match_mode"] == "exact_kind"
    )
    exact_delivered = sum(
        1 for record in delivered_records if record["match_mode"] == "exact_kind"
    )

    recall_label = (
        "dependency-link recall; references_type fallback is generic and does not "
        "establish precise subtype/kind recall"
    )
    return {
        "schema_version": 1,
        "case_id": case.get("id"),
        "required_semantic_dependencies_total": required_total,
        "required_semantic_dependencies": required_records,
        "available_dependency_links_total": available_total,
        "available_dependency_links": available_records,
        "delivered_dependency_links_total": delivered_total,
        "delivered_dependency_links": delivered_records,
        "dependency_link_recall": {
            "label": recall_label,
            "required": required_total,
            "available": available_total,
            "delivered": delivered_total,
            "available_ratio": available_total / required_total if required_total else None,
            "delivered_ratio": delivered_total / required_total if required_total else None,
        },
        "precise_kind_links_available_total": exact_available,
        "precise_kind_links_delivered_total": exact_delivered,
        "missing_endpoints": missing_endpoints,
        "multiple_endpoints": multiple_endpoints,
        "source_only_endpoints": source_only_endpoints,
        "endpoint_issues": endpoint_issues,
        "forbidden_proven_relationships": len(forbidden),
        "forbidden_proven_relationship_edges": forbidden,
        "forbidden_scope": (
            "authored frozen forbidden_relationships only; this is not exhaustive "
            "truth about unsupported or unrecorded edges"
        ),
    }


__all__ = ["score_relationships"]
