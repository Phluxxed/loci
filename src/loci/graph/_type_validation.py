"""Evidence checks for the authored type relation family."""
from __future__ import annotations

from typing import Any, Mapping, Sequence

from loci.parser.reference_models import RawLocalExport
from loci.parser.symbols import Symbol

from .contracts import GraphContractError, GraphEdge
from .imports import ImportRecord
from .type_models import TypeRelationRecord
from .type_relations import materialize_type_edges, resolve_type_relations, type_site_key


def validate_type_records(
    records: Sequence[TypeRelationRecord],
    *,
    imports: Sequence[ImportRecord],
    exports: Sequence[RawLocalExport],
    indexed_nodes: Mapping[str, Mapping[str, Any]],
    file_hashes: Mapping[str, str],
    input_hashes: Mapping[str, str],
) -> None:
    """Re-establish outcomes against current owner, binding and target evidence."""
    symbols = [Symbol.from_dict(dict(value)) for value in indexed_nodes.values()]
    file_nodes = {symbol.file_path: symbol for symbol in symbols if symbol.kind == "file"}
    seen = set()
    for record in records:
        if not isinstance(record, TypeRelationRecord):
            raise _error("Invalid type relation record")
        raw = record.raw
        key = type_site_key(raw)
        if key in seen:
            raise _error("Duplicate type observation site", file=raw.source_file)
        seen.add(key)
        file = file_nodes.get(raw.source_file)
        if (file is None or file.language != raw.language
                or file.content_hash != raw.source_hash
                or file_hashes.get(raw.source_file) != raw.source_hash):
            raise _error("Type source endpoint is missing or stale", file=raw.source_file)
        if not (raw.owner.start_byte <= raw.start_byte < raw.end_byte <= raw.owner.end_byte):
            raise _error("Type occurrence lies outside its declaration owner", file=raw.source_file)
        for item in record.support:
            if file_hashes.get(item.file) != item.content_hash:
                raise _error("Type support source is stale", file=item.file)
            if item.endpoint_id is not None and item.endpoint_id not in indexed_nodes:
                raise _error("Type support endpoint is missing", target=item.endpoint_id)
        for control in record.resolution_controls:
            if input_hashes.get(control.file) != control.content_hash:
                raise _error("Type resolution control is stale", file=control.file)
        for binding in raw.local_bindings:
            expected_namespace = {
                "class": "both", "enum": "both", "interface": "type", "type": "type",
                "type_parameter": "type", "function": "value", "constant": "value",
                "parameter": "value", "namespace": "both", "unindexed": binding.namespace,
            }[binding.kind]
            if binding.namespace != expected_namespace:
                raise _error("Type binding namespace does not match its declaration kind")
    expected = resolve_type_relations(
        [record.raw for record in records], symbols=symbols, imports=imports,
        exports=exports, file_hashes=file_hashes, input_hashes=input_hashes,
    )
    actual = sorted(records, key=lambda record: type_site_key(record.raw))
    if [record.to_dict() for record in actual] != [record.to_dict() for record in expected]:
        raise _error("Type resolution does not match current indexed binding evidence")


def index_type_edge_records(records: Sequence[TypeRelationRecord]) -> dict[tuple, GraphEdge]:
    return {(edge.type, edge.from_id, edge.to_id): edge
            for edge in materialize_type_edges(records)}


def validate_type_projection(
    edges: Sequence[GraphEdge], records: Sequence[TypeRelationRecord],
) -> None:
    """Persisted type edges must be the complete deterministic record projection."""
    actual = [edge for edge in edges if edge.namespace == "loci"
              and edge.type in {"uses_type", "extends", "implements", "embeds"}]
    key = lambda edge: (edge.type, edge.from_id, edge.to_id)
    if sorted(actual, key=key) != sorted(materialize_type_edges(records), key=key):
        raise _error("Persisted type edges do not match the complete record projection")


def validate_type_edge(
    edge: GraphEdge,
    *,
    indexed_nodes: Mapping[str, Mapping[str, Any]],
    file_hashes: Mapping[str, str] | None,
    type_index: Mapping[tuple, GraphEdge],
    edge_index: int,
) -> None:
    expected = type_index.get((edge.type, edge.from_id, edge.to_id))
    if expected is None or edge != expected:
        raise GraphContractError("INVALID_GRAPH_EDGE", "Type edge lacks matching proven observation",
                                 {"edge_index": edge_index})
    if edge.from_id not in indexed_nodes or edge.to_id not in indexed_nodes:
        raise GraphContractError("INVALID_GRAPH_EDGE", "Type edge endpoint is not indexed",
                                 {"edge_index": edge_index})
    if file_hashes is not None and (
        edge.evidence is None or file_hashes.get(edge.evidence.file) != edge.evidence.content_hash
    ):
        raise GraphContractError("INVALID_GRAPH_EDGE", "Type edge evidence is stale",
                                 {"edge_index": edge_index})


def _error(message: str, **details) -> GraphContractError:
    return GraphContractError("INVALID_TYPE_RELATION", message, details)
