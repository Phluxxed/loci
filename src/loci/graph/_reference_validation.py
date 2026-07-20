from __future__ import annotations

import json
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Mapping, Sequence, cast

from loci.parser.reference_models import ImportBinding, RawLocalExport, RawSymbolReference

from .contracts import (
    GraphContractError,
    GraphEdge,
    GraphEvidence,
    JSONValue,
    _indexed_edge_endpoints,
)
from .imports import ImportRecord
from .references import ReferenceSupport, SymbolReferenceRecord


@dataclass(frozen=True, slots=True)
class _ValidationIndex:
    nodes_by_file: Mapping[str, tuple[Mapping[str, Any], ...]]
    imports_by_binding: Mapping[
        tuple[str, ImportBinding],
        tuple[ImportRecord, ...],
    ]
    import_support: frozenset[tuple[bool, str, int, str, str]]
    export_support: frozenset[tuple[str, int, str, str]]


def materialize_reference_edges(
    records: Sequence[SymbolReferenceRecord],
) -> list[GraphEdge]:
    """Build one deterministic edge per resolved source/target relationship."""
    edges: dict[tuple[str, str, str, str], GraphEdge] = {}
    ranks: dict[tuple[str, str, str, str], tuple[int, int, str, str]] = {}
    for record in records:
        if not isinstance(record, SymbolReferenceRecord):
            raise _error("Reference edge input is not a SymbolReferenceRecord")
        if record.status != "resolved":
            continue
        if record.binding is None or record.target_id is None:
            raise _error("Resolved reference requires a binding and target")
        edge = GraphEdge(
            from_id=record.source_id,
            to_id=record.target_id,
            type=("references_type" if record.binding.type_only else "references"),
            directed=True,
            namespace="loci",
            resolution="import-resolved",
            evidence=GraphEvidence(
                file=record.raw.source_file,
                line=record.raw.line,
                content_hash=record.raw.source_hash,
            ),
        )
        key = (edge.namespace, edge.type, edge.from_id, edge.to_id)
        rank = (
            record.raw.line,
            record.raw.column,
            record.raw.text,
            json.dumps(
                record.binding.to_dict(),
                sort_keys=True,
                separators=(",", ":"),
            ),
        )
        if key not in ranks or rank < ranks[key]:
            edges[key] = edge
            ranks[key] = rank
    return [edges[key] for key in sorted(edges)]


def index_reference_edge_records(
    records: Sequence[SymbolReferenceRecord],
) -> Mapping[
    tuple[str, str, bool, str, int, str],
    tuple[SymbolReferenceRecord, ...],
]:
    """Index resolved records once for bounded edge-contract validation."""
    indexed: dict[
        tuple[str, str, bool, str, int, str],
        list[SymbolReferenceRecord],
    ] = {}
    for record in records:
        if not isinstance(record, SymbolReferenceRecord):
            raise _error("Reference edge record is not a SymbolReferenceRecord")
        if record.status != "resolved" or record.binding is None:
            continue
        indexed.setdefault(
            (
                record.source_id,
                cast(str, record.target_id),
                record.binding.type_only,
                record.raw.source_file,
                record.raw.line,
                record.raw.source_hash,
            ),
            [],
        ).append(record)
    return MappingProxyType({
        key: tuple(values) for key, values in indexed.items()
    })


def validate_reference_edge(
    edge: GraphEdge,
    *,
    edge_index: int,
    indexed_nodes: Mapping[str, Mapping[str, Any]],
    file_hashes: Mapping[str, str] | None,
    reference_index: Mapping[
        tuple[str, str, bool, str, int, str],
        Sequence[SymbolReferenceRecord],
    ],
) -> None:
    if edge.resolution != "import-resolved":
        raise GraphContractError(
            "GRAPH_RESOLUTION_UNSUPPORTED",
            "Resolution tier is not permitted for this graph edge type",
            {"edge_index": edge_index, "resolution": edge.resolution},
        )
    if edge.directed is not True:
        raise GraphContractError(
            "INVALID_GRAPH_EDGE",
            "Reference edges must be directed",
            {"edge_index": edge_index, "field": "directed"},
        )
    source, target = _indexed_edge_endpoints(
        edge,
        edge_index=edge_index,
        indexed_nodes=indexed_nodes,
    )
    source_file = source.get("file_path")
    if not isinstance(source_file, str) or _is_synthetic_node(target):
        raise GraphContractError(
            "INVALID_GRAPH_EDGE",
            "Reference edge endpoints must be an indexed source and code-symbol target",
            {"edge_index": edge_index, "field": "endpoints"},
        )
    if edge.evidence.file != source_file:
        _raise_edge_evidence_error(
            edge_index,
            "file",
            expected=source_file,
            actual=edge.evidence.file,
        )
    current_hash = file_hashes.get(source_file) if file_hashes is not None else None
    if edge.evidence.content_hash != current_hash:
        _raise_edge_evidence_error(
            edge_index,
            "content_hash",
            expected=current_hash,
            actual=edge.evidence.content_hash,
        )
    type_only = edge.type == "references_type"
    matches = [
        record
        for record in reference_index.get(
            (
                edge.from_id,
                edge.to_id,
                type_only,
                source_file,
                edge.evidence.line,
                edge.evidence.content_hash,
            ),
            (),
        )
        if (
            record.source_kind == source.get("kind")
            and record.target_kind == target.get("kind")
            and record.target_file == target.get("file_path")
        )
    ]
    if not matches:
        raise GraphContractError(
            "GRAPH_EVIDENCE_INVALID",
            "Reference edge is not backed by a matching resolved reference record",
            {"edge_index": edge_index, "field": "reference_record"},
        )
    if not all(record.support for record in matches):
        raise GraphContractError(
            "GRAPH_EVIDENCE_INVALID",
            "Reference edge record has no support",
            {"edge_index": edge_index, "field": "support"},
        )


def validate_symbol_reference_records(
    records: Sequence[SymbolReferenceRecord],
    *,
    imports: Sequence[ImportRecord],
    exports: Sequence[RawLocalExport],
    indexed_nodes: Mapping[str, Mapping[str, Any]],
    file_hashes: Mapping[str, str],
) -> None:
    """Cross-check reference records against current indexed evidence."""
    validation_index = _build_validation_index(
        imports=imports,
        exports=exports,
        indexed_nodes=indexed_nodes,
        file_hashes=file_hashes,
    )
    for record_index, record in enumerate(records):
        if not isinstance(record, SymbolReferenceRecord):
            raise _error(
                "Reference record has an invalid type",
                record_index=record_index,
            )
        if file_hashes.get(record.raw.source_file) != record.raw.source_hash:
            raise _record_error(record_index, "Reference source evidence is stale")
        _validate_source_owner(
            record,
            indexed_nodes=indexed_nodes,
            validation_index=validation_index,
            record_index=record_index,
        )
        matched_import = _validate_import(
            record,
            validation_index=validation_index,
            record_index=record_index,
        )
        if record.status == "resolved":
            _validate_target(
                record,
                indexed_nodes=indexed_nodes,
                record_index=record_index,
            )
        _validate_support(
            record,
            validation_index=validation_index,
            file_hashes=file_hashes,
            matched_import=matched_import,
            record_index=record_index,
        )


def _build_validation_index(
    *,
    imports: Sequence[ImportRecord],
    exports: Sequence[RawLocalExport],
    indexed_nodes: Mapping[str, Mapping[str, Any]],
    file_hashes: Mapping[str, str],
) -> _ValidationIndex:
    nodes_by_file: dict[str, list[Mapping[str, Any]]] = {}
    endpoints_by_span: dict[tuple[str, int, int], list[str]] = {}
    for node_id, node in indexed_nodes.items():
        file = node.get("file_path")
        if not isinstance(file, str):
            continue
        nodes_by_file.setdefault(file, []).append(node)
        start = node.get("byte_offset")
        length = node.get("byte_length")
        if (
            not _is_synthetic_node(node)
            and isinstance(start, int)
            and not isinstance(start, bool)
            and isinstance(length, int)
            and not isinstance(length, bool)
        ):
            endpoints_by_span.setdefault(
                (file, start, start + length),
                [],
            ).append(node_id)

    imports_by_binding: dict[
        tuple[str, ImportBinding],
        list[ImportRecord],
    ] = {}
    import_support: set[tuple[bool, str, int, str, str]] = set()
    for record in imports:
        if not isinstance(record, ImportRecord):
            raise _error("Reference validation import is not an ImportRecord")
        for binding in record.raw.bindings:
            imports_by_binding.setdefault(
                (record.raw.source_file, binding),
                [],
            ).append(record)
        if record.status == "resolved" and record.target_id is not None:
            if record.target_id not in indexed_nodes:
                raise _error(
                    "Reference import target endpoint is not indexed",
                    target_id=record.target_id,
                )
            import_support.add((
                record.raw.is_reexport,
                record.raw.source_file,
                record.raw.line,
                record.raw.source_hash,
                record.target_id,
            ))

    export_support: set[tuple[str, int, str, str]] = set()
    for export in exports:
        if not isinstance(export, RawLocalExport):
            raise _error("Reference validation export is not a RawLocalExport")
        if file_hashes.get(export.source_file) != export.source_hash:
            raise _error(
                "Reference export source evidence is stale",
                file=export.source_file,
            )
        if export.definition_start_byte is None:
            continue
        for endpoint_id in endpoints_by_span.get(
            (
                export.source_file,
                export.definition_start_byte,
                cast(int, export.definition_end_byte),
            ),
            (),
        ):
            export_support.add((
                export.source_file,
                export.line,
                export.source_hash,
                endpoint_id,
            ))
    return _ValidationIndex(
        nodes_by_file=MappingProxyType({
            file: tuple(nodes) for file, nodes in nodes_by_file.items()
        }),
        imports_by_binding=MappingProxyType({
            key: tuple(records) for key, records in imports_by_binding.items()
        }),
        import_support=frozenset(import_support),
        export_support=frozenset(export_support),
    )


def _validate_source_owner(
    record: SymbolReferenceRecord,
    *,
    indexed_nodes: Mapping[str, Mapping[str, Any]],
    validation_index: _ValidationIndex,
    record_index: int,
) -> None:
    raw = record.raw
    file_node = indexed_nodes.get(record.import_source_id)
    if (
        file_node is None
        or file_node.get("kind") != "file"
        or file_node.get("file_path") != raw.source_file
        or file_node.get("language") != raw.language
    ):
        raise _record_error(
            record_index,
            "Reference import source is not the current source file node",
            field="import_source_id",
        )
    candidates = [
        node
        for node in validation_index.nodes_by_file.get(raw.source_file, ())
        if not _is_synthetic_node(node) and _contains_reference(node, raw)
    ]
    ambiguous = False
    expected = file_node
    if candidates:
        smallest_length = min(cast(int, node["byte_length"]) for node in candidates)
        smallest = [
            node for node in candidates if node.get("byte_length") == smallest_length
        ]
        if len(smallest) == 1:
            expected = smallest[0]
        else:
            ambiguous = True
    if (
        expected.get("id") != record.source_id
        or expected.get("kind") != record.source_kind
        or expected.get("language") != raw.language
    ):
        raise _record_error(
            record_index,
            "Reference source owner does not match the current symbol index",
            field="source_id",
        )
    if ambiguous and not (
        record.status == "unresolved"
        and record.unresolved_reason == "ambiguous_source"
    ):
        raise _record_error(
            record_index,
            "Ambiguous reference source cannot be treated as resolved",
            field="source_id",
        )


def _validate_import(
    record: SymbolReferenceRecord,
    *,
    validation_index: _ValidationIndex,
    record_index: int,
) -> ImportRecord | None:
    if record.binding is None:
        if record.import_target_id is not None:
            raise _record_error(
                record_index,
                "Reference without a selected binding cannot claim an import target",
                field="import_target_id",
            )
        return None
    matches = [
        item
        for item in validation_index.imports_by_binding.get(
            (record.raw.source_file, record.binding),
            (),
        )
        if (
            item.source_id == record.import_source_id
            and item.raw.language == record.raw.language
            and item.raw.source_hash == record.raw.source_hash
        )
    ]
    if len(matches) != 1:
        raise _record_error(
            record_index,
            "Reference binding does not match one current import record",
            field="import_record",
        )
    matched = matches[0]
    if record.import_target_id != matched.target_id:
        raise _record_error(
            record_index,
            "Reference import target does not match its import record",
            field="import_target_id",
        )
    if record.import_unresolved_reason != matched.unresolved_reason:
        raise _record_error(
            record_index,
            "Reference import outcome does not match its import record",
            field="import_unresolved_reason",
        )
    if record.status == "resolved" and matched.status != "resolved":
        raise _record_error(
            record_index,
            "Resolved reference requires a resolved import record",
            field="import_record",
        )
    if record.unresolved_reason == "import_unresolved" and matched.status != "unresolved":
        raise _record_error(
            record_index,
            "Import-unresolved reference requires an unresolved import record",
            field="import_record",
        )
    return matched


def _validate_target(
    record: SymbolReferenceRecord,
    *,
    indexed_nodes: Mapping[str, Mapping[str, Any]],
    record_index: int,
) -> None:
    target = indexed_nodes.get(cast(str, record.target_id))
    if target is None or _is_synthetic_node(target):
        raise _record_error(
            record_index,
            "Reference target is not a current code symbol",
            field="target_id",
        )
    if (
        target.get("file_path") != record.target_file
        or target.get("kind") != record.target_kind
    ):
        raise _record_error(
            record_index,
            "Reference target identity does not match the current symbol index",
            field="target_id",
        )


def _validate_support(
    record: SymbolReferenceRecord,
    *,
    validation_index: _ValidationIndex,
    file_hashes: Mapping[str, str],
    matched_import: ImportRecord | None,
    record_index: int,
) -> None:
    import_support_count = 0
    final_definition_count = 0
    for support_index, support in enumerate(record.support):
        if file_hashes.get(support.file) != support.content_hash:
            raise _record_error(
                record_index,
                "Reference support evidence is stale",
                field="support",
                support_index=support_index,
            )
        if support.kind == "import_binding":
            import_support_count += 1
            if (
                matched_import is None
                or _import_support_key(support, reexport=False)
                not in validation_index.import_support
                or matched_import.target_id != support.endpoint_id
            ):
                raise _record_error(
                    record_index,
                    "Reference import support does not match its selected import",
                    field="support",
                    support_index=support_index,
                )
            continue
        if support.kind == "reexport":
            if (
                _import_support_key(support, reexport=True)
                not in validation_index.import_support
            ):
                raise _record_error(
                    record_index,
                    "Reference re-export support does not match a current import",
                    field="support",
                    support_index=support_index,
                )
            continue
        if _export_support_key(support) not in validation_index.export_support:
            raise _record_error(
                record_index,
                "Reference definition support does not match a current export",
                field="support",
                support_index=support_index,
            )
        if support.kind == "definition" and support.endpoint_id == record.target_id:
            final_definition_count += 1
    if record.status == "resolved" and (
        import_support_count != 1 or final_definition_count < 1
    ):
        raise _record_error(
            record_index,
            "Resolved reference requires one import and final definition support",
            field="support",
        )


def _import_support_key(
    support: ReferenceSupport,
    *,
    reexport: bool,
) -> tuple[bool, str, int, str, str]:
    return (
        reexport,
        support.file,
        support.line,
        support.content_hash,
        support.endpoint_id,
    )


def _export_support_key(
    support: ReferenceSupport,
) -> tuple[str, int, str, str]:
    return (
        support.file,
        support.line,
        support.content_hash,
        support.endpoint_id,
    )


def _contains_reference(
    node: Mapping[str, Any],
    raw: RawSymbolReference,
) -> bool:
    start = node.get("byte_offset")
    length = node.get("byte_length")
    return (
        isinstance(start, int)
        and not isinstance(start, bool)
        and isinstance(length, int)
        and not isinstance(length, bool)
        and length > 0
        and start <= raw.start_byte
        and raw.end_byte <= start + length
    )


def _is_synthetic_node(node: Mapping[str, Any]) -> bool:
    if node.get("kind") in {"file", "package", "crate"}:
        return True
    if node.get("language") == "markdown":
        return True
    metadata = node.get("metadata")
    loci = metadata.get("loci") if isinstance(metadata, Mapping) else None
    return isinstance(loci, Mapping) and any(
        loci.get(key) is True
        for key in ("file_node", "go_package", "rust_crate")
    )


def _raise_edge_evidence_error(
    edge_index: int,
    field: str,
    *,
    expected: JSONValue,
    actual: JSONValue,
) -> None:
    raise GraphContractError(
        "GRAPH_EVIDENCE_INVALID",
        "Reference edge evidence does not match the current reference record",
        {
            "edge_index": edge_index,
            "field": field,
            "expected": expected,
            "actual": actual,
        },
    )


def _record_error(
    record_index: int,
    message: str,
    **details: Any,
) -> GraphContractError:
    return _error(message, record_index=record_index, **details)


def _error(message: str, **details: Any) -> GraphContractError:
    return GraphContractError(
        "GRAPH_CONTRACT_INVALID",
        message,
        cast(dict[str, JSONValue], details),
    )
