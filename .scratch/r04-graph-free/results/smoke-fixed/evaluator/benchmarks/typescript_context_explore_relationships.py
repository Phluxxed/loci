"""Observed relationship/proof coverage for the separately frozen explore trial.

The old scorer remains immutable. Generic dependency credit accepts authored
uses_type without claiming that it proves a precise parameter/property subtype.
"""
from __future__ import annotations

from collections.abc import Mapping
import hashlib
from pathlib import Path

from benchmarks import typescript_context_relationships as prior


_GENERIC_TYPE_KINDS = frozenset({"parameter_type", "property_type", "alias_of", "type_query", "return_type", "intersection_member"})


def _kind_mode(kind):
    if not isinstance(kind, str):
        return "unsupported_kind", frozenset()
    if kind in _GENERIC_TYPE_KINDS:
        return "generic_type_dependency", frozenset({"references_type", "uses_type"})
    # A missing inheritance/call edge must never become generic type credit.
    return "exact_kind", frozenset({kind})


def _forbidden_records(case, endpoints, symbols, edges):
    by_id = {s["id"]: s for s in symbols}
    found = {}
    for ordinal, forbidden in enumerate(case.get("forbidden_relationships", [])):
        mode, kinds = _kind_mode(forbidden.get("kind"))
        for edge in edges:
            if not prior._proven_edge(edge) or edge.get("type") not in kinds:
                continue
            if not prior._forbidden_target_matches(edge, forbidden, by_id):
                continue
            origin = prior._forbidden_origin_mode(edge, forbidden, endpoints, by_id)
            if origin is not None:
                found[ordinal, prior._edge_key(edge)] = {"forbidden_index": ordinal,
                    "relationship": dict(forbidden), "origin_mode": origin,
                    "match_mode": mode, "edge": dict(edge)}
    return list(found.values())


def _key(edge):
    return edge.get("type"), edge.get("from"), edge.get("to"), edge.get("evidence", {}).get("line")


def _proof_sets(index, edge):
    """Join persisted records independently of the product's source selector."""
    graph = index.get("graph", {})
    expected = _key(edge)
    references = [r for r in graph.get("symbol_references", []) if r.get("status") == "resolved"]
    for record in graph.get("type_relations", []):
        raw = record.get("raw", {})
        if record.get("status") == "resolved" and (
            raw.get("relation"), record.get("source_id"), record.get("target_id"), raw.get("line")
        ) == expected:
            yield record.get("support", [])
    for record in references:
        raw = record.get("raw", {})
        kind = "references_type" if record.get("binding", {}).get("type_only") else "references"
        if (kind, record.get("source_id"), record.get("target_id"), raw.get("line")) == expected:
            yield record.get("support", [])
    for record in graph.get("calls", []):
        raw = record.get("raw", {})
        if record.get("status") != "resolved" or (
            "calls", record.get("caller_id"), record.get("target_id"), raw.get("line")
        ) != expected:
            continue
        support = list(record.get("support", []))
        if record.get("resolution") == "import-resolved":
            joined = [r for r in references if all(r.get("raw", {}).get(a) == raw.get(b) for a, b in (
                ("source_file", "source_file"), ("source_hash", "source_hash"),
                ("start_byte", "callee_start_byte"), ("end_byte", "callee_end_byte"),
            ))]
            if len(joined) != 1:
                continue
            support.extend(joined[0].get("support", []))
        yield support


def _source_bytes(repo, name):
    if not isinstance(name, str) or Path(name).is_absolute() or ".." in Path(name).parts:
        raise ValueError("source path is not repository relative")
    root = Path(repo).resolve()
    path = root / name
    if not path.resolve().is_relative_to(root) or path.is_symlink():
        raise ValueError("source path escapes the snapshot")
    return path.read_bytes()


def _valid_source(source, repo):
    data = _source_bytes(repo, source.get("file"))
    start, end = source.get("start_byte"), source.get("end_byte")
    if (type(start) is not int or type(end) is not int or not 0 <= start < end <= len(data)
            or not isinstance(source.get("content"), str)
            or data[start:end] != source["content"].encode("utf-8")
            or hashlib.sha256(data).hexdigest() != source.get("content_hash")):
        raise ValueError("source bytes/hash do not match the frozen snapshot")
    return source


def _covered_support(support, sources, index, repo):
    name = support.get("file")
    data = _source_bytes(repo, name)
    if support.get("kind") in {"caller_definition", "local_definition"}:
        symbol = next((s for s in prior._index_symbols(index) if s.get("id") == support.get("endpoint_id")), None)
        if not symbol or symbol.get("file_path") != name or symbol.get("content_hash") != support.get("content_hash"):
            return False
        start = symbol["byte_offset"]
        end = start + symbol["byte_length"]
        if hashlib.sha256(data[start:end]).hexdigest() != support.get("content_hash"):
            return False
    else:
        if hashlib.sha256(data).hexdigest() != support.get("content_hash"):
            return False
        line = support.get("line")
        lines = data.splitlines(keepends=True)
        if type(line) is not int or not 1 <= line <= len(lines):
            return False
        start = sum(map(len, lines[:line - 1]))
        end = start + len(lines[line - 1])
    position = start
    for source in sorted((s for s in sources if s.get("file") == name), key=lambda s: s["start_byte"]):
        if source["start_byte"] <= position:
            position = max(position, source["end_byte"])
    return position >= end


def delivered_edges(index, results):
    """Return proved delivered edges and explicit delivery-integrity violations."""
    available = {prior._edge_key(e) for e in prior._index_edges(index) if prior._proven_edge(e)}
    edges = []
    violations = []
    repo = index.get("repo_path")

    def add(edge, *, capsule=None, relation=None):
        problem = None
        if not prior._edge_shape(edge) or prior._edge_key(edge) not in available:
            problem = "delivered_edge_not_proven_in_index"
        elif capsule is not None:
            try:
                if not isinstance(relation, Mapping):
                    raise ValueError("missing exploration relationship record")
                by_id = {s["id"]: s for s in capsule.get("sources", [])}
                source_ids = relation.get("source_ids", [])
                if not source_ids or any(sid not in by_id for sid in source_ids):
                    raise ValueError("missing relationship source IDs")
                sources = [_valid_source(by_id[sid], repo) for sid in source_ids]
                proofs = list(_proof_sets(index, edge))
                if not any(proof and all(_covered_support(s, sources, index, repo) for s in proof) for proof in proofs):
                    raise ValueError("complete indexed relationship proof is not delivered")
                if relation.get("traversed") not in {"forward", "reverse"}:
                    raise ValueError("invalid traversal direction")
            except (KeyError, TypeError, ValueError, OSError) as exc:
                problem = "invalid_relationship_proof: " + str(exc)
        if problem:
            violations.append({"edge": edge, "reason": problem})
        else:
            edges.append(dict(edge))

    for edge in prior._delivered_edges(results):
        add(edge)
    for result in results:
        payload = prior._unwrap_result(result)
        if not isinstance(payload, Mapping):
            continue
        for symbol in prior._as_sequence(payload.get("symbols", [])):
            if not isinstance(symbol, Mapping):
                continue
            context = symbol.get("type_context", {})
            for reference in prior._as_sequence(context.get("references", [])) if isinstance(context, Mapping) else []:
                add(reference.get("edge") if isinstance(reference, Mapping) else reference)
        # Current expanded-get payload keeps type_context at the result root.
        context = payload.get("type_context", {})
        for reference in prior._as_sequence(context.get("references", [])) if isinstance(context, Mapping) else []:
            add(reference.get("edge") if isinstance(reference, Mapping) else reference)
        if payload.get("intent") in {"locate", "type_dependencies", "impact"}:
            for relation in prior._as_sequence(payload.get("relationships", [])):
                if isinstance(relation, Mapping):
                    add(relation.get("edge"), capsule=payload, relation=relation)
                else:
                    violations.append({"edge": None, "reason": "invalid_exploration_relationship"})
    return list({prior._edge_key(e): e for e in edges}.values()), violations


def score_relationships(case, index, results):
    """Score unchanged endpoint gold with native-kind and generic-link separation."""
    symbols = prior._index_symbols(index)
    available = prior._index_edges(index)
    delivered, violations = delivered_edges(index, results)
    endpoints = prior._endpoint_table(case, symbols)
    records, issues = [], []
    for ordinal, relationship in enumerate(case.get("relationships", [])):
        if not isinstance(relationship, Mapping):
            continue
        kind = relationship.get("kind")
        mode, kinds = _kind_mode(kind)
        start_key, end_key = relationship.get("from"), relationship.get("to")
        source = endpoints.get(start_key if isinstance(start_key, str) else "", {"status": "missing", "symbol_ids": []})
        target = endpoints.get(end_key if isinstance(end_key, str) else "", {"status": "missing", "symbol_ids": []})
        found, sent = [], []
        for role, endpoint in (("from", source), ("to", target)):
            if endpoint["status"] in {"missing", "ambiguous", "source_only"}:
                issues.append({"relationship": ordinal, "endpoint": role, "context_id": relationship.get(role), "status": endpoint["status"]})
        if source["status"] == target["status"] == "indexed":
            start, end = source["symbol_ids"][0], target["symbol_ids"][0]
            found = prior._matching_edges(available, start, end, kinds)
            sent = prior._matching_edges(delivered, start, end, kinds)
        records.append({"index": ordinal, **relationship, "from_status": source["status"], "to_status": target["status"],
                        "match_mode": mode, "available": bool(found), "delivered": bool(sent),
                        "available_edges": found, "delivered_edges": sent})
    found = [r for r in records if r["available"]]
    sent = [r for r in records if r["delivered"]]
    forbidden = _forbidden_records(case, endpoints, symbols, available)
    return {
        "schema_version": 2, "case_id": case.get("id"),
        "required_semantic_dependencies_total": len(records), "required_semantic_dependencies": records,
        "available_dependency_links_total": len(found), "available_dependency_links": found,
        "delivered_dependency_links_total": len(sent), "delivered_dependency_links": sent,
        "dependency_link_recall": {"label": "Exact endpoint dependency links; generic uses_type/references_type do not prove precise subtypes.",
            "required": len(records), "available": len(found), "delivered": len(sent),
            "available_ratio": len(found) / len(records) if records else None,
            "delivered_ratio": len(sent) / len(records) if records else None},
        "precise_kind_links_available_total": sum(r["match_mode"] == "exact_kind" for r in found),
        "precise_kind_links_delivered_total": sum(r["match_mode"] == "exact_kind" for r in sent),
        "missing_endpoints": sorted({i["context_id"] for i in issues if i["status"] == "missing"}),
        "multiple_endpoints": sorted({i["context_id"] for i in issues if i["status"] == "ambiguous"}),
        "source_only_endpoints": sorted({i["context_id"] for i in issues if i["status"] == "source_only"}),
        "endpoint_issues": issues,
        "forbidden_proven_relationships": len(forbidden) + len(violations),
        "forbidden_proven_relationship_edges": forbidden,
        "delivery_integrity_violations": violations,
        "forbidden_scope": "Authored frozen negatives plus delivered edge/index consistency and complete exploration source proof; not exhaustive semantic truth.",
    }
