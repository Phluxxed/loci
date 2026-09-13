"""Independent relationship and proof scoring for multilingual-context-v1.

The frozen corpus names authored language meanings rather than graph edge enum
values.  This scorer joins each meaning to the persisted semantic record that
establishes it, then requires an actual delivered edge and source proof.  It
does not change or rescore the historical TypeScript comparisons.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
import hashlib
import re
from pathlib import Path
from typing import Any

from benchmarks import typescript_context_relationships as prior


@dataclass(frozen=True)
class RelationSpec:
    family: str
    edge_type: str
    contexts: frozenset[str] = frozenset()
    literal: bool = False


_SPECS: dict[tuple[str, str], RelationSpec] = {
    ("python", "parameter_annotation"): RelationSpec("type", "uses_type", frozenset({"annotation"})),
    ("python", "field_annotation"): RelationSpec("type", "uses_type", frozenset({"property", "type_argument"})),
    ("python", "alias_target"): RelationSpec("type", "uses_type", frozenset({"alias"})),
    ("python", "type_argument"): RelationSpec("type", "uses_type", frozenset({"type_argument"})),
    ("python", "direct_class_base"): RelationSpec("type", "extends", frozenset({"heritage"})),
    ("python", "literal_forward_annotation"): RelationSpec(
        "type", "uses_type", frozenset({"annotation", "return"}), literal=True
    ),
    ("python", "calls"): RelationSpec("call", "calls"),
    ("javascript", "calls"): RelationSpec("call", "calls"),
    ("javascript", "direct_class_extends"): RelationSpec("type", "extends", frozenset({"heritage"})),
    ("go", "parameter_type"): RelationSpec("type", "uses_type", frozenset({"annotation"})),
    ("go", "return_type"): RelationSpec("type", "uses_type", frozenset({"return"})),
    ("go", "type_argument"): RelationSpec("type", "uses_type", frozenset({"type_argument"})),
    ("go", "alias_target"): RelationSpec("type", "uses_type", frozenset({"alias"})),
    ("go", "generic_constraint"): RelationSpec("type", "uses_type", frozenset({"constraint"})),
    ("go", "struct_embedding"): RelationSpec("type", "embeds", frozenset({"struct_embedding"})),
    ("go", "interface_embedding"): RelationSpec("type", "embeds", frozenset({"interface_embedding"})),
    ("go", "calls"): RelationSpec("call", "calls"),
    ("rust", "generic_bound"): RelationSpec("type", "uses_type", frozenset({"constraint"})),
    ("rust", "parameter_type"): RelationSpec("type", "uses_type", frozenset({"annotation"})),
    ("rust", "return_type"): RelationSpec("type", "uses_type", frozenset({"return"})),
    ("rust", "field_type"): RelationSpec("type", "uses_type", frozenset({"property"})),
    ("rust", "supertrait"): RelationSpec("type", "supertrait", frozenset({"supertrait"})),
    ("rust", "impl_trait"): RelationSpec("type", "impl_trait", frozenset({"impl_trait"})),
    ("rust", "impl_self_type"): RelationSpec("type", "impl_self_type", frozenset({"impl_self_type"})),
    ("rust", "calls"): RelationSpec("call", "calls"),
    ("typescript", "parameter_type"): RelationSpec("type", "uses_type", frozenset({"annotation"})),
}


def validate_relation_mappings(corpus: Mapping[str, Any]) -> None:
    """Fail preparation if any positive corpus meaning lacks an explicit map."""
    missing = sorted({
        (case.get("language"), relation.get("kind"))
        for case in prior._as_sequence(corpus.get("cases", []))
        if isinstance(case, Mapping)
        for relation in prior._as_sequence(case.get("relationships", []))
        if isinstance(relation, Mapping)
        and (case.get("language"), relation.get("kind")) not in _SPECS
    })
    if missing:
        raise ValueError("unsupported multilingual relationship mappings: " + repr(missing))


def _source_bytes(repo: str | Path, name: Any) -> bytes:
    if not isinstance(name, str):
        raise ValueError("proof source has no file")
    root = Path(repo).resolve()
    path = (root / name).resolve()
    if path != root and root not in path.parents:
        raise ValueError("proof source escapes snapshot")
    return path.read_bytes()


def _exact_impl_endpoints(
    case: Mapping[str, Any], endpoints: dict[str, dict[str, Any]], symbols: Sequence[Mapping[str, Any]]
) -> None:
    """Resolve only frozen Rust impl endpoints whose authored span is exact."""
    impl_sources = {
        relation.get("from")
        for relation in prior._as_sequence(case.get("relationships", []))
        if isinstance(relation, Mapping) and relation.get("kind") in {"impl_trait", "impl_self_type"}
    }
    context_by_id = {
        item.get("id"): item
        for item in prior._as_sequence(case.get("context", []))
        if isinstance(item, Mapping) and isinstance(item.get("id"), str)
    }
    for context_id in impl_sources:
        context = context_by_id.get(context_id)
        endpoint = endpoints.get(context_id)
        if not context or not endpoint or endpoint.get("status") != "source_only":
            continue
        start, end = context.get("start_byte"), context.get("end_byte")
        matches = [
            symbol for symbol in symbols
            if symbol.get("kind") == "impl"
            and symbol.get("file_path") == context.get("file")
            and symbol.get("byte_offset") == start
            and type(symbol.get("byte_length")) is int
            and symbol.get("byte_offset") + symbol.get("byte_length") == end
        ]
        endpoint.update(
            status="indexed" if len(matches) == 1 else "ambiguous" if matches else "missing",
            symbol_ids=sorted(symbol["id"] for symbol in matches),
            symbols=matches,
        )


def _endpoint_table(case: Mapping[str, Any], symbols: Sequence[Mapping[str, Any]]) -> dict[str, dict[str, Any]]:
    endpoints = prior._endpoint_table(case, symbols)
    _exact_impl_endpoints(case, endpoints, symbols)
    return endpoints


def _literal_name(value: Any) -> bool:
    return bool(isinstance(value, str) and re.fullmatch(r"(['\"])[A-Za-z_$][\w$]*(?:\.[A-Za-z_$][\w$]*)*\1", value))


def _semantic_records(index: Mapping[str, Any], spec: RelationSpec, source_id: str, target_id: str) -> list[dict[str, Any]]:
    graph = index.get("graph", {})
    key = "calls" if spec.family == "call" else "type_relations"
    records = []
    for record in prior._as_sequence(graph.get(key, [])) if isinstance(graph, Mapping) else []:
        if not isinstance(record, Mapping) or record.get("status") != "resolved":
            continue
        raw = record.get("raw", {})
        if not isinstance(raw, Mapping):
            continue
        observed_source = record.get("caller_id") if spec.family == "call" else record.get("source_id")
        observed_type = "calls" if spec.family == "call" else raw.get("relation")
        if observed_source != source_id or record.get("target_id") != target_id or observed_type != spec.edge_type:
            continue
        if spec.contexts and raw.get("context") not in spec.contexts:
            continue
        if spec.literal and not _literal_name(raw.get("text")):
            continue
        records.append(dict(record))
    return records


def _record_edge(index: Mapping[str, Any], spec: RelationSpec, record: Mapping[str, Any]) -> dict[str, Any] | None:
    raw = record.get("raw", {})
    source = record.get("caller_id") if spec.family == "call" else record.get("source_id")
    for edge in prior._index_edges(index):
        if (
            prior._proven_edge(edge)
            and edge.get("type") == spec.edge_type
            and edge.get("from") == source
            and edge.get("to") == record.get("target_id")
            and isinstance(raw, Mapping)
            and edge.get("evidence", {}).get("line") == raw.get("line")
        ):
            return edge
    return None


def _line_interval(data: bytes, line: Any) -> tuple[int, int] | None:
    if type(line) is not int or line < 1:
        return None
    lines = data.splitlines(keepends=True)
    if line > len(lines):
        return None
    start = sum(map(len, lines[: line - 1]))
    content = lines[line - 1].rstrip(b"\r\n")
    return start, start + len(content)


def _support_interval(
    support: Mapping[str, Any], index: Mapping[str, Any], repo: str | Path
) -> tuple[str, int, int] | None:
    file = support.get("file")
    data = _source_bytes(repo, file)
    digest = hashlib.sha256(data).hexdigest()
    kind = support.get("kind")
    if kind in {"caller_definition", "local_definition"}:
        symbol = next(
            (item for item in prior._index_symbols(index) if item.get("id") == support.get("endpoint_id")),
            None,
        )
        if not symbol or symbol.get("file_path") != file:
            return None
        start, length = symbol.get("byte_offset"), symbol.get("byte_length")
        if type(start) is not int or type(length) is not int or length <= 0:
            return None
        if hashlib.sha256(data[start : start + length]).hexdigest() != support.get("content_hash"):
            return None
        return file, start, start + length
    if digest != support.get("content_hash"):
        return None
    interval = _line_interval(data, support.get("line"))
    return (file, *interval) if interval is not None else None


def _joined_call_reference(index: Mapping[str, Any], record: Mapping[str, Any]) -> Mapping[str, Any] | None:
    if record.get("resolution") != "import-resolved":
        return None
    raw = record.get("raw", {})
    matches = [
        item for item in prior._as_sequence(index.get("graph", {}).get("symbol_references", []))
        if isinstance(item, Mapping)
        and item.get("status") == "resolved"
        and all(item.get("raw", {}).get(left) == raw.get(right) for left, right in (
            ("source_file", "source_file"), ("source_hash", "source_hash"),
            ("start_byte", "callee_start_byte"), ("end_byte", "callee_end_byte"),
        ))
    ]
    return matches[0] if len(matches) == 1 else None


def _proof_intervals(index: Mapping[str, Any], spec: RelationSpec, record: Mapping[str, Any]) -> list[tuple[str, int, int]]:
    repo = index.get("repo_path")
    support = list(prior._as_sequence(record.get("support", [])))
    controls = list(prior._as_sequence(record.get("resolution_controls", [])))
    if spec.family == "call":
        reference = _joined_call_reference(index, record)
        if reference is not None:
            support.extend(prior._as_sequence(reference.get("support", [])))
            for name in prior._as_sequence(reference.get("resolution_control_files", [])):
                controls.append({"file": name, "content_hash": index.get("graph", {}).get("input_hashes", {}).get(name)})
        if record.get("raw", {}).get("language") == "go":
            target_file = record.get("target_file")
            if isinstance(target_file, str):
                data = _source_bytes(repo, target_file)
                controls.append({"file": target_file, "content_hash": hashlib.sha256(data).hexdigest(), "line": 1})
            for name, digest in index.get("graph", {}).get("input_hashes", {}).items():
                if Path(name).name in {"go.mod", "go.work"}:
                    controls.append({"file": name, "content_hash": digest})
    intervals: list[tuple[str, int, int]] = []
    for item in support:
        if isinstance(item, Mapping):
            interval = _support_interval(item, index, repo)
            if interval is None:
                raise ValueError("persisted relationship support is invalid")
            intervals.append(interval)
    for control in controls:
        if not isinstance(control, Mapping):
            raise ValueError("persisted resolution control is invalid")
        file = control.get("file")
        data = _source_bytes(repo, file)
        if hashlib.sha256(data).hexdigest() != control.get("content_hash"):
            raise ValueError("resolution control hash differs from snapshot")
        if type(control.get("line")) is int:
            interval = _line_interval(data, control["line"])
            if interval is None:
                raise ValueError("resolution control line is invalid")
            intervals.append((file, *interval))
        else:
            intervals.append((file, 0, len(data)))
    return list(dict.fromkeys(intervals))


def _claim_records(index: Mapping[str, Any], edge: Mapping[str, Any]) -> list[tuple[RelationSpec, dict[str, Any]]]:
    """Find the persisted semantic records that can establish one graph edge."""
    graph = index.get("graph", {})
    if not isinstance(graph, Mapping):
        return []
    wanted = (edge.get("type"), edge.get("from"), edge.get("to"), edge.get("evidence", {}).get("line"))
    found: list[tuple[RelationSpec, dict[str, Any]]] = []
    for name, family in (("type_relations", "type"), ("calls", "call"), ("symbol_references", "reference")):
        for value in prior._as_sequence(graph.get(name, [])):
            if not isinstance(value, Mapping) or value.get("status") != "resolved":
                continue
            raw = value.get("raw", {})
            if not isinstance(raw, Mapping):
                continue
            if family == "call":
                observed = ("calls", value.get("caller_id"), value.get("target_id"), raw.get("line"))
            elif family == "reference":
                binding = value.get("binding", {})
                edge_type = "references_type" if isinstance(binding, Mapping) and binding.get("type_only") else "references"
                observed = (edge_type, value.get("source_id"), value.get("target_id"), raw.get("line"))
            else:
                observed = (raw.get("relation"), value.get("source_id"), value.get("target_id"), raw.get("line"))
            if observed == wanted:
                found.append((RelationSpec(family, str(wanted[0])), dict(value)))
    return found


def _claim_proof_intervals(
    index: Mapping[str, Any], spec: RelationSpec, record: Mapping[str, Any]
) -> list[tuple[str, int, int]]:
    """Rebuild the product's stored support/control basis for one claim."""
    if spec.family != "reference":
        intervals = _proof_intervals(index, spec, record)
    else:
        intervals = []
        repo = index.get("repo_path")
        for support in prior._as_sequence(record.get("support", [])):
            if not isinstance(support, Mapping):
                raise ValueError("relationship support is invalid")
            interval = _support_interval(support, index, repo)
            if interval is None:
                raise ValueError("relationship support differs from snapshot")
            intervals.append(interval)
        controls = [
            {"file": name, "content_hash": index.get("graph", {}).get("input_hashes", {}).get(name)}
            for name in prior._as_sequence(record.get("resolution_control_files", []))
        ]
        if record.get("raw", {}).get("language") == "go":
            target_file = record.get("target_file")
            if isinstance(target_file, str):
                data = _source_bytes(repo, target_file)
                controls.append({"file": target_file, "content_hash": hashlib.sha256(data).hexdigest(), "line": 1})
            for name, digest in index.get("graph", {}).get("input_hashes", {}).items():
                if Path(name).name in {"go.mod", "go.work"}:
                    controls.append({"file": name, "content_hash": digest})
        for control in controls:
            data = _source_bytes(repo, control.get("file"))
            if hashlib.sha256(data).hexdigest() != control.get("content_hash"):
                raise ValueError("resolution control hash differs from snapshot")
            interval = _line_interval(data, control.get("line")) if type(control.get("line")) is int else (0, len(data))
            if interval is None:
                raise ValueError("resolution control line is invalid")
            intervals.append((control["file"], *interval))

    # Rust records additionally rely on each exact external `mod` declaration
    # along the involved files' path back to its crate root.
    raw = record.get("raw", {})
    if isinstance(raw, Mapping) and raw.get("language") == "rust":
        repo = index.get("repo_path")
        pending = [value for value in (raw.get("source_file"), record.get("target_file")) if isinstance(value, str)]
        pending.extend(
            support.get("file") for support in prior._as_sequence(record.get("support", []))
            if isinstance(support, Mapping) and isinstance(support.get("file"), str)
        )
        seen: set[str] = set()
        imports = prior._as_sequence(index.get("graph", {}).get("imports", []))
        while pending:
            target_file = pending.pop(0)
            if target_file in seen:
                continue
            seen.add(target_file)
            parents = [
                item for item in imports
                if isinstance(item, Mapping) and item.get("status") == "resolved"
                and item.get("target_file") == target_file
                and isinstance(item.get("raw"), Mapping)
                and isinstance(item["raw"].get("rust"), Mapping)
                and item["raw"]["rust"].get("kind") == "module"
            ]
            for parent in parents:
                parent_raw = parent["raw"]
                data = _source_bytes(repo, parent_raw.get("source_file"))
                if hashlib.sha256(data).hexdigest() != parent_raw.get("source_hash"):
                    raise ValueError("Rust module declaration differs from snapshot")
                interval = _line_interval(data, parent_raw.get("line"))
                if interval is None:
                    raise ValueError("Rust module declaration line is invalid")
                intervals.append((parent_raw["source_file"], *interval))
                pending.append(parent_raw["source_file"])
    return list(dict.fromkeys(intervals))


def _validate_span(span: Mapping[str, Any], repo: str | Path) -> dict[str, Any]:
    file, start, end = span.get("file"), span.get("start_byte"), span.get("end_byte")
    data = _source_bytes(repo, file)
    if type(start) is not int or type(end) is not int or not 0 <= start < end <= len(data):
        raise ValueError("delivered source has invalid interval")
    content = span.get("content", span.get("text"))
    if not isinstance(content, str) or data[start:end] != content.encode("utf-8"):
        raise ValueError("delivered source bytes differ from snapshot")
    content_hash = span.get("content_hash")
    if content_hash is not None and content_hash != hashlib.sha256(data).hexdigest():
        raise ValueError("delivered source hash differs from snapshot")
    return {"file": file, "start_byte": start, "end_byte": end}


def _covers(spans: Sequence[Mapping[str, Any]], intervals: Sequence[tuple[str, int, int]]) -> bool:
    for file, start, end in intervals:
        cursor = start
        for span in sorted((item for item in spans if item.get("file") == file), key=lambda item: item["start_byte"]):
            if span["start_byte"] > cursor:
                break
            cursor = max(cursor, span["end_byte"])
            if cursor >= end:
                break
        if cursor < end:
            return False
    return True


def _unwrap(value: Any) -> Any:
    return prior._unwrap_result(value)


def _delivered_claims(index: Mapping[str, Any], results: Sequence[Mapping[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    repo = index.get("repo_path")
    claims: list[dict[str, Any]] = []
    violations: list[dict[str, Any]] = []
    available = {prior._edge_key(edge) for edge in prior._index_edges(index) if prior._proven_edge(edge)}

    def add(edge: Any, *, sources: Sequence[Mapping[str, Any]] | None = None, explore: bool = False) -> None:
        if not prior._edge_shape(edge) or prior._edge_key(edge) not in available:
            violations.append({"edge": edge, "reason": "delivered_edge_not_proven_in_index"})
            return
        claims.append({"edge": dict(edge), "sources": list(sources) if sources is not None else None, "explore": explore})

    for result in results:
        payload = _unwrap(result)
        if not isinstance(payload, Mapping):
            continue
        if payload.get("intent") in {"locate", "type_dependencies", "dependencies", "impact"}:
            by_id: dict[Any, dict[str, Any]] = {}
            try:
                for source in prior._as_sequence(payload.get("sources", [])):
                    if not isinstance(source, Mapping) or source.get("id") in by_id:
                        raise ValueError("invalid or duplicate exploration source")
                    by_id[source.get("id")] = _validate_span(source, repo)
                for relation in prior._as_sequence(payload.get("relationships", [])):
                    if not isinstance(relation, Mapping) or relation.get("traversed") not in {"forward", "reverse"}:
                        raise ValueError("invalid exploration relationship")
                    source_ids = relation.get("source_ids")
                    if not isinstance(source_ids, list) or not source_ids or any(item not in by_id for item in source_ids):
                        raise ValueError("missing exploration relationship source IDs")
                    add(relation.get("edge"), sources=[by_id[item] for item in source_ids], explore=True)
            except (KeyError, OSError, TypeError, ValueError) as exc:
                violations.append({"edge": None, "reason": "invalid_relationship_proof: " + str(exc)})
            continue
        for edge in prior._delivered_edges([payload]):
            add(edge)
        for symbol in prior._as_sequence(payload.get("symbols", [])):
            context = symbol.get("type_context", {}) if isinstance(symbol, Mapping) else {}
            for reference in prior._as_sequence(context.get("references", [])) if isinstance(context, Mapping) else []:
                add(reference.get("edge") if isinstance(reference, Mapping) else reference)
        context = payload.get("type_context", {})
        for reference in prior._as_sequence(context.get("references", [])) if isinstance(context, Mapping) else []:
            add(reference.get("edge") if isinstance(reference, Mapping) else reference)
    unique = {}
    for claim in claims:
        key = (prior._edge_key(claim["edge"]), claim["explore"], repr(claim["sources"]))
        unique[key] = claim
    return list(unique.values()), violations


def _mentions(use: Any, text: Any) -> bool:
    if not isinstance(use, str) or not isinstance(text, str) or not text:
        return False
    return bool(re.search(r"(?<![\w$])" + re.escape(text.strip("'\"")) + r"(?![\w$])", use))


def _forbidden_records(
    case: Mapping[str, Any], endpoints: Mapping[str, Mapping[str, Any]], index: Mapping[str, Any]
) -> list[dict[str, Any]]:
    symbols = prior._index_symbols(index)
    by_id = {symbol.get("id"): symbol for symbol in symbols}
    records: list[tuple[dict[str, Any], dict[str, Any]]] = []
    for item in prior._as_sequence(index.get("graph", {}).get("type_relations", [])):
        if isinstance(item, Mapping) and item.get("status") == "resolved":
            raw = item.get("raw", {})
            spec = RelationSpec("type", raw.get("relation"), frozenset())
            edge = _record_edge(index, spec, item)
            if edge is not None:
                records.append((dict(item), edge))
    for item in prior._as_sequence(index.get("graph", {}).get("calls", [])):
        if isinstance(item, Mapping) and item.get("status") == "resolved":
            edge = _record_edge(index, RelationSpec("call", "calls"), item)
            if edge is not None:
                records.append((dict(item), edge))
    found = {}
    for ordinal, forbidden in enumerate(prior._as_sequence(case.get("forbidden_relationships", []))):
        if not isinstance(forbidden, Mapping):
            continue
        origin = endpoints.get(forbidden.get("from"), {})
        origin_ids = set(origin.get("symbol_ids", [])) if origin.get("status") == "indexed" else set()
        requested_kind = forbidden.get("kind")
        if requested_kind == "class_inheritance":
            requested_kind = "extends"
        target_files = set(prior._as_sequence(forbidden.get("target_files")))
        if isinstance(forbidden.get("target_file"), str):
            target_files.add(forbidden["target_file"])
        # Some frozen negatives identify a use site textually instead of with
        # a context id.  When that text names one or more actual source
        # declarations, bind to those sources so (for example) `generic
        # Thing` cannot condemn the separately proven `probe(Thing)` edge.
        use = forbidden.get("use")
        all_semantic = [
            item
            for key in ("type_relations", "calls", "symbol_references")
            for item in prior._as_sequence(index.get("graph", {}).get(key, []))
            if isinstance(item, Mapping)
        ]
        textual_origins = {
            item.get("caller_id", item.get("source_id"))
            for item in all_semantic
            if isinstance(by_id.get(item.get("caller_id", item.get("source_id"))), Mapping)
            and _mentions(use, by_id[item.get("caller_id", item.get("source_id"))].get("name"))
        }
        for record, edge in records:
            raw = record.get("raw", {})
            source_id = record.get("caller_id", record.get("source_id"))
            target = by_id.get(record.get("target_id"), {})
            if origin_ids and source_id not in origin_ids:
                continue
            if not origin_ids and forbidden.get("from") is not None:
                continue
            if not origin_ids and textual_origins and source_id not in textual_origins:
                continue
            if not origin_ids and not _mentions(forbidden.get("use"), raw.get("callee_text", raw.get("text"))):
                continue
            if requested_kind is not None and edge.get("type") != requested_kind:
                continue
            if target_files and target.get("file_path") not in target_files:
                continue
            if forbidden.get("target_name") is not None and target.get("name") != forbidden.get("target_name"):
                continue
            expected_configuration = forbidden.get("configuration")
            if expected_configuration is not None and record.get("resolution_configuration") != expected_configuration:
                continue
            found[ordinal, prior._edge_key(edge)] = {
                "forbidden_index": ordinal,
                "relationship": dict(forbidden),
                "edge": edge,
                "record_context": raw.get("context"),
            }
    return list(found.values())


def score_relationships(
    case: dict[str, Any],
    index: dict[str, Any],
    delivered_results: list[dict[str, Any]],
    delivered_spans: Sequence[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """Score exact authored meanings, actual relation claims and delivered proof."""
    language = case.get("language")
    symbols = prior._index_symbols(index)
    endpoints = _endpoint_table(case, symbols)
    claims, violations = _delivered_claims(index, delivered_results)
    global_spans: list[dict[str, Any]] = []
    for span in delivered_spans or []:
        global_spans.append(_validate_span(span, index.get("repo_path")))

    # Trust is a property of every delivered relationship, including an
    # extraneous claim that does not happen to be named by this case's gold.
    # Validate it before the gold projection so neither arm can hide an
    # unsupported or incompletely sourced edge outside a required relation.
    for claim in claims:
        matching = _claim_records(index, claim["edge"])
        spans = claim["sources"] if claim["explore"] else global_spans
        if not matching:
            violations.append({"edge": claim["edge"], "reason": "delivered_edge_has_no_persisted_semantic_record"})
            continue
        if not any(_covers(spans, _claim_proof_intervals(index, spec, record)) for spec, record in matching):
            violations.append({
                "edge": claim["edge"],
                "reason": "invalid_relationship_proof: complete persisted proof is not delivered",
            })

    records_out = []
    issues = []
    for ordinal, relationship in enumerate(prior._as_sequence(case.get("relationships", []))):
        if not isinstance(relationship, Mapping):
            continue
        spec = _SPECS.get((language, relationship.get("kind")))
        if spec is None:
            raise ValueError(f"unsupported multilingual relationship mapping: {(language, relationship.get('kind'))!r}")
        source = endpoints.get(relationship.get("from"), {"status": "missing", "symbol_ids": []})
        target = endpoints.get(relationship.get("to"), {"status": "missing", "symbol_ids": []})
        for role, endpoint in (("from", source), ("to", target)):
            if endpoint.get("status") != "indexed":
                issues.append({"relationship": ordinal, "endpoint": role,
                               "context_id": relationship.get(role), "status": endpoint.get("status", "missing")})
        semantic = []
        if source.get("status") == target.get("status") == "indexed":
            semantic = _semantic_records(index, spec, source["symbol_ids"][0], target["symbol_ids"][0])
        available = []
        delivered = []
        for record in semantic:
            edge = _record_edge(index, spec, record)
            if edge is None:
                continue
            available.append(edge)
            proof = _proof_intervals(index, spec, record)
            for claim in claims:
                if prior._edge_key(claim["edge"]) != prior._edge_key(edge):
                    continue
                spans = claim["sources"] if claim["explore"] else global_spans
                if _covers(spans, proof):
                    delivered.append(edge)
                    break
        record_out = {
            "index": ordinal, **dict(relationship),
            "from_status": source.get("status", "missing"),
            "to_status": target.get("status", "missing"),
            "match_mode": "semantic_record",
            "graph_type": spec.edge_type,
            "record_contexts": sorted(spec.contexts),
            "available": bool(available),
            "delivered": bool(delivered),
            "available_edges": list({prior._edge_key(edge): edge for edge in available}.values()),
            "delivered_edges": list({prior._edge_key(edge): edge for edge in delivered}.values()),
        }
        records_out.append(record_out)

    forbidden = _forbidden_records(case, endpoints, index)
    delivered_keys = {prior._edge_key(claim["edge"]) for claim in claims}
    forbidden_delivered = [item for item in forbidden if prior._edge_key(item["edge"]) in delivered_keys]
    available_records = [record for record in records_out if record["available"]]
    delivered_records = [record for record in records_out if record["delivered"]]
    violations = list({repr(item): item for item in violations}.values())
    return {
        "schema_version": 3,
        "case_id": case.get("id"),
        "language": language,
        "required_semantic_dependencies_total": len(records_out),
        "required_semantic_dependencies": records_out,
        "available_dependency_links_total": len(available_records),
        "available_dependency_links": available_records,
        "delivered_dependency_links_total": len(delivered_records),
        "delivered_dependency_links": delivered_records,
        "dependency_link_recall": {
            "label": "Exact frozen meaning joined to persisted semantic record and delivered source proof.",
            "required": len(records_out),
            "available": len(available_records),
            "delivered": len(delivered_records),
            "available_ratio": len(available_records) / len(records_out) if records_out else None,
            "delivered_ratio": len(delivered_records) / len(records_out) if records_out else None,
        },
        "missing_endpoints": sorted({item["context_id"] for item in issues if item["status"] == "missing"}),
        "multiple_endpoints": sorted({item["context_id"] for item in issues if item["status"] == "ambiguous"}),
        "source_only_endpoints": sorted({item["context_id"] for item in issues if item["status"] == "source_only"}),
        "endpoint_issues": issues,
        "forbidden_available_relationships": len(forbidden),
        "forbidden_delivered_relationships": len(forbidden_delivered),
        "forbidden_proven_relationships": len(forbidden) + len(violations),
        "forbidden_proven_relationship_edges": forbidden,
        "forbidden_delivered_relationship_edges": forbidden_delivered,
        "delivery_integrity_violations": violations,
        "forbidden_scope": "Frozen multilingual negatives plus delivered edge/index and complete exploration-proof consistency.",
    }
