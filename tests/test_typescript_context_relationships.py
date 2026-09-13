from __future__ import annotations

from typing import Any

from benchmarks.typescript_context_corpus import load_corpus
from benchmarks.typescript_context_relationships import score_relationships


def _context(
    context_id: str,
    file: str,
    name: str | None,
    kind: str | None = "function",
    *,
    start: int = 0,
    end: int = 100,
) -> dict[str, Any]:
    symbol = None if name is None else {"name": name, "kind": kind}
    return {
        "id": context_id,
        "file": file,
        "start_byte": start,
        "end_byte": end,
        "symbol": symbol,
    }


def _symbol(
    symbol_id: str,
    file: str,
    name: str,
    kind: str = "function",
    *,
    offset: int = 10,
    length: int = 10,
    line: int = 5,
    end_line: int = 5,
) -> dict[str, Any]:
    return {
        "id": symbol_id,
        "file_path": file,
        "name": name,
        "kind": kind,
        "byte_offset": offset,
        "byte_length": length,
        "line": line,
        "end_line": end_line,
    }


def _edge(
    source: str,
    target: str,
    edge_type: str = "references_type",
    *,
    resolution: str = "import-resolved",
    evidence_file: str = "entry.ts",
    evidence_line: int = 5,
) -> dict[str, Any]:
    return {
        "from": source,
        "to": target,
        "type": edge_type,
        "directed": True,
        "namespace": "loci",
        "resolution": resolution,
        "evidence": {
            "file": evidence_file,
            "line": evidence_line,
            "content_hash": "evidence-hash",
        },
    }


def _node(symbol_id: str) -> dict[str, Any]:
    return {"id": symbol_id, "namespace": "loci", "kind": "symbol", "attributes": {}}


def _neighbor_packet(edge: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "results": [{
            "seed": _node(edge["from"]),
            "neighbors": [{"node": _node(edge["to"]), "edge": edge}],
        }],
        "diagnostics": [],
    }


def _path_packet(edge: dict[str, Any], *, retrieve: bool = False) -> dict[str, Any]:
    path = {
        "nodes": [_node(edge["from"]), _node(edge["to"])],
        "steps": [{
            "traversed": "forward",
            "edge": edge,
            "evidence_span": {
                "file": edge["evidence"]["file"],
                "start_line": edge["evidence"]["line"],
                "end_line": edge["evidence"]["line"],
                "content": "source evidence",
            },
        }],
    }
    packet = {
        "schema_version": 1,
        "paths": [path],
        "rejected_paths": [],
        "counts": {"accepted": 1, "rejected": 0},
        "budget": {},
    }
    if retrieve:
        packet.update({"support_kind": "edge_sequence", "sources": [_node(edge["from"])], "targets": [_node(edge["to"]) ]})
    return packet


def _index(symbols: list[dict[str, Any]], edges: list[dict[str, Any]]) -> dict[str, Any]:
    return {"symbols": symbols, "graph": {"edges": edges}}


def _type_case(*, kind: str = "parameter_type", forbidden: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    return {
        "id": "synthetic",
        "context": [
            _context("entry", "entry.ts", "entry"),
            _context("payload", "types.ts", "Payload", "interface"),
        ],
        "relationships": [{"from": "entry", "kind": kind, "to": "payload"}],
        "forbidden_relationships": forbidden or [],
    }


def test_available_and_delivered_dependency_links_are_separate_and_exact() -> None:
    case = _type_case()
    source = _symbol("entry-id", "entry.ts", "entry")
    target = _symbol("payload-id", "types.ts", "Payload", "interface")
    edge = _edge(source["id"], target["id"])

    unavailable = score_relationships(case, _index([source, target], [edge]), [])
    assert unavailable["required_semantic_dependencies_total"] == 1
    assert unavailable["available_dependency_links_total"] == 1
    assert unavailable["delivered_dependency_links_total"] == 0
    assert unavailable["required_semantic_dependencies"][0]["match_mode"] == "generic_references_type"
    assert "precise subtype/kind recall" in unavailable["dependency_link_recall"]["label"]

    delivered = score_relationships(
        case,
        _index([source, target], [edge]),
        [_neighbor_packet(edge)],
    )
    assert delivered["available_dependency_links_total"] == 1
    assert delivered["delivered_dependency_links_total"] == 1
    assert delivered["delivered_dependency_links"][0]["delivered_edges"] == [edge]


def test_neighbor_path_and_retrieve_packets_deliver_one_deduplicated_edge() -> None:
    case = _type_case()
    source = _symbol("entry-id", "entry.ts", "entry")
    target = _symbol("payload-id", "types.ts", "Payload", "interface")
    edge = _edge(source["id"], target["id"])
    results = [
        _neighbor_packet(edge),
        _path_packet(edge),
        {"structuredContent": _path_packet(edge, retrieve=True)},
    ]

    scored = score_relationships(case, _index([source, target], [edge]), results)
    assert scored["delivered_dependency_links_total"] == 1
    assert scored["delivered_dependency_links"][0]["delivered_edges"] == [edge]


def test_structural_edges_and_heuristic_resolution_do_not_satisfy_dependencies() -> None:
    case = _type_case()
    source = _symbol("entry-id", "entry.ts", "entry")
    target = _symbol("payload-id", "types.ts", "Payload", "interface")
    structural = [
        _edge(source["id"], target["id"], "contains"),
        _edge(source["id"], target["id"], "imports"),
        _edge(source["id"], target["id"], "imports_type"),
        _edge(source["id"], target["id"], "references_type", resolution="heuristic"),
    ]

    scored = score_relationships(case, _index([source, target], structural), [])
    assert scored["available_dependency_links_total"] == 0
    assert scored["delivered_dependency_links_total"] == 0


def test_exact_kind_edges_are_precise_when_the_graph_exposes_that_kind() -> None:
    case = _type_case(kind="parameter_type")
    source = _symbol("entry-id", "entry.ts", "entry")
    target = _symbol("payload-id", "types.ts", "Payload", "interface")
    edge = _edge(source["id"], target["id"], "parameter_type", resolution="declared")

    scored = score_relationships(case, _index([source, target], [edge]), [_path_packet(edge)])
    assert scored["available_dependency_links_total"] == 1
    assert scored["delivered_dependency_links_total"] == 1
    assert scored["precise_kind_links_available_total"] == 1
    assert scored["required_semantic_dependencies"][0]["match_mode"] == "exact_kind"


def test_wrong_file_target_is_not_an_exact_endpoint_and_is_retained_as_forbidden() -> None:
    case = _type_case(
        forbidden=[{
            "from": "entry",
            "kind": "parameter_type",
            "target_file": "wrong.ts",
            "target_name": "Payload",
        }]
    )
    source = _symbol("entry-id", "entry.ts", "entry")
    right_target = _symbol("right-id", "types.ts", "Payload", "interface")
    wrong_target = _symbol("wrong-id", "wrong.ts", "Payload", "interface")
    wrong_edge = _edge(source["id"], wrong_target["id"])

    scored = score_relationships(
        case,
        _index([source, right_target, wrong_target], [wrong_edge]),
        [_neighbor_packet(wrong_edge)],
    )
    assert scored["available_dependency_links_total"] == 0
    assert scored["delivered_dependency_links_total"] == 0
    assert scored["forbidden_proven_relationships"] == 1
    assert scored["forbidden_proven_relationship_edges"][0]["edge"] == wrong_edge
    assert scored["forbidden_proven_relationship_edges"][0]["origin_mode"] == "symbol"


def test_file_owned_reference_is_not_declaration_dependency_but_can_prove_forbidden() -> None:
    case = _type_case(
        forbidden=[{
            "from": "entry",
            "kind": "parameter_type",
            "target_file": "types.ts",
            "target_name": "Payload",
        }]
    )
    source = _symbol("entry-id", "entry.ts", "entry", line=5, end_line=5)
    target = _symbol("payload-id", "types.ts", "Payload", "interface")
    file_node = _symbol("entry-file", "entry.ts", "entry.ts", "file")
    file_edge = _edge(
        file_node["id"],
        target["id"],
        evidence_file="entry.ts",
        evidence_line=5,
    )

    scored = score_relationships(
        case,
        _index([source, target, file_node], [file_edge]),
        [],
    )
    assert scored["available_dependency_links_total"] == 0
    assert scored["forbidden_proven_relationships"] == 1
    assert scored["forbidden_proven_relationship_edges"][0]["origin_mode"] == "file"


def test_missing_ambiguous_and_source_only_endpoints_remain_visible() -> None:
    case = {
        "id": "endpoint-statuses",
        "context": [
            _context("missing", "missing.ts", "Missing"),
            _context("ambiguous", "entry.ts", "entry"),
            _context("source", "entry.ts", None),
            _context("target", "types.ts", "Payload", "interface"),
        ],
        "relationships": [
            {"from": "missing", "kind": "parameter_type", "to": "target"},
            {"from": "ambiguous", "kind": "parameter_type", "to": "target"},
            {"from": "source", "kind": "parameter_type", "to": "target"},
        ],
        "forbidden_relationships": [],
    }
    first = _symbol("entry-one", "entry.ts", "entry")
    second = _symbol("entry-two", "entry.ts", "entry")
    target = _symbol("payload-id", "types.ts", "Payload", "interface")

    scored = score_relationships(case, _index([first, second, target], []), [])
    assert scored["required_semantic_dependencies_total"] == 3
    assert scored["available_dependency_links_total"] == 0
    assert scored["missing_endpoints"] == ["missing"]
    assert scored["multiple_endpoints"] == ["ambiguous"]
    assert scored["source_only_endpoints"] == ["source"]


def test_frozen_default_identifier_case_uses_real_authored_context_and_call_edge() -> None:
    corpus = load_corpus()
    case = next(item for item in corpus["cases"] if item["id"] == "default_identifier")
    symbols = []
    for context in case["context"]:
        authored = context.get("symbol")
        if authored is None:
            continue
        symbol_id = f'{context["file"]}::{authored["name"]}#{authored["kind"]}'
        symbols.append({
            "id": symbol_id,
            "file_path": context["file"],
            "name": authored["name"],
            "kind": authored["kind"],
            "byte_offset": context["start_byte"],
            "byte_length": context["end_byte"] - context["start_byte"],
            "line": 1,
            "end_line": 1,
        })
    source_id = next(symbol["id"] for symbol in symbols if symbol["name"] == "useNumber")
    target_id = next(symbol["id"] for symbol in symbols if symbol["name"] == "num")
    edge = _edge(source_id, target_id, "calls", evidence_file="consumer.ts", evidence_line=1)

    scored = score_relationships(case, _index(symbols, [edge]), [_neighbor_packet(edge)])
    assert scored["required_semantic_dependencies_total"] == 1
    assert scored["available_dependency_links_total"] == 1
    assert scored["delivered_dependency_links_total"] == 1
    assert scored["required_semantic_dependencies"][0]["match_mode"] == "exact_kind"
