from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, Sequence
from types import MappingProxyType
from typing import Any, cast

from loci.graph.calls import CallRecord
from loci.graph.contracts import (
    GraphContractError,
    GraphEdge,
    GraphEvidence,
)
from loci.graph.references import SymbolReferenceRecord
from loci.parser.call_models import RawCallSite


_CALLER_KINDS = frozenset({"file", "function", "method"})
_CALLABLE_KINDS = frozenset({"function", "method"})


def materialize_call_edges(records: Sequence[CallRecord]) -> list[GraphEdge]:
    """Build one deterministic edge per resolved caller/target relationship."""
    edges: dict[tuple[str, str, str, str, str], GraphEdge] = {}
    ranks: dict[tuple[str, str, str, str, str], tuple[str, int, int, int]] = {}
    for record in records:
        if not isinstance(record, CallRecord):
            raise _error("Call edge input is not a CallRecord")
        if record.status != "resolved":
            continue
        if (
            record.caller_id is None
            or record.target_id is None
            or record.resolution is None
        ):
            raise _error("Resolved call requires caller, target, and resolution")
        edge = GraphEdge(
            from_id=record.caller_id,
            to_id=record.target_id,
            type="calls",
            directed=True,
            namespace="loci",
            resolution=record.resolution,
            evidence=GraphEvidence(
                file=record.raw.source_file,
                line=record.raw.line,
                content_hash=record.raw.source_hash,
            ),
        )
        key = (
            edge.namespace,
            edge.type,
            edge.from_id,
            edge.to_id,
            edge.resolution,
        )
        rank = (
            record.raw.source_file,
            record.raw.line,
            record.raw.column,
            record.raw.start_byte,
        )
        if key not in ranks or rank < ranks[key]:
            edges[key] = edge
            ranks[key] = rank
    return [edges[key] for key in sorted(edges)]


def validate_call_records(
    records: Sequence[CallRecord],
    *,
    symbol_references: Sequence[SymbolReferenceRecord],
    indexed_nodes: Mapping[str, Mapping[str, Any]],
    file_hashes: Mapping[str, str],
) -> None:
    """Cross-check call records against current indexed evidence."""
    references = _index_references(symbol_references, file_hashes=file_hashes)
    file_nodes, callables = _index_nodes(indexed_nodes)
    for record_index, record in enumerate(records):
        if not isinstance(record, CallRecord):
            raise _record_error(record_index, "Call record has an invalid type")
        if file_hashes.get(record.raw.source_file) != record.raw.source_hash:
            raise _record_error(record_index, "Call source evidence is stale")
        source_nodes = file_nodes.get(record.raw.source_file, ())
        if len(source_nodes) != 1 or (
            source_nodes[0].get("language") != record.raw.language
            or source_nodes[0].get("content_hash") != record.raw.source_hash
        ):
            raise _record_error(record_index, "Call source endpoint is missing or stale")
        caller, stop = _validate_outcome(
            record,
            file_node=source_nodes[0],
            callables=callables,
            references=references,
            record_index=record_index,
        )
        if stop:
            continue
        assert caller is not None
        target = _validate_target(
            record,
            indexed_nodes=indexed_nodes,
            record_index=record_index,
        )
        _validate_support(
            record,
            caller=caller,
            target=target,
            file_hashes=file_hashes,
            record_index=record_index,
        )
        if record.resolution == "import-resolved":
            _validate_reference(
                record,
                references=references,
                file_hashes=file_hashes,
                target=target,
                record_index=record_index,
            )


def index_call_edge_records(
    records: Sequence[CallRecord],
) -> Mapping[tuple[str, str, str], tuple[CallRecord, ...]]:
    """Index resolved records once for bounded edge-contract validation."""
    indexed: dict[tuple[str, str, str], list[CallRecord]] = {}
    for record in records:
        if not isinstance(record, CallRecord):
            raise _error("Call edge record is not a CallRecord")
        if record.status != "resolved":
            continue
        assert record.caller_id is not None
        assert record.target_id is not None
        assert record.resolution is not None
        indexed.setdefault(
            (record.caller_id, record.target_id, record.resolution),
            [],
        ).append(record)
    return MappingProxyType({key: tuple(values) for key, values in indexed.items()})


def _index_nodes(
    indexed_nodes: Mapping[str, Mapping[str, Any]],
) -> tuple[
    Mapping[str, tuple[Mapping[str, Any], ...]],
    Mapping[tuple[str, int, int, str], tuple[Mapping[str, Any], ...]],
]:
    file_nodes: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    callables: dict[
        tuple[str, int, int, str],
        list[Mapping[str, Any]],
    ] = defaultdict(list)
    for node_id, node in indexed_nodes.items():
        if node.get("id") != node_id:
            raise _error("Call validation node identity is inconsistent")
        file_path = node.get("file_path")
        kind = node.get("kind")
        if not isinstance(file_path, str):
            continue
        if kind == "file":
            file_nodes[file_path].append(node)
            continue
        if kind not in _CALLABLE_KINDS:
            continue
        start = node.get("byte_offset")
        length = node.get("byte_length")
        if (
            not isinstance(start, int)
            or isinstance(start, bool)
            or not isinstance(length, int)
            or isinstance(length, bool)
            or length < 0
        ):
            raise _error("Call validation callable span is invalid", endpoint_id=node_id)
        callables[(file_path, start, start + length, kind)].append(node)
    return (
        MappingProxyType({key: tuple(values) for key, values in file_nodes.items()}),
        MappingProxyType({key: tuple(values) for key, values in callables.items()}),
    )


def _validate_outcome(
    record: CallRecord,
    *,
    file_node: Mapping[str, Any],
    callables: Mapping[
        tuple[str, int, int, str],
        Sequence[Mapping[str, Any]],
    ],
    references: Mapping[
        tuple[str, str, int, int],
        Sequence[SymbolReferenceRecord],
    ],
    record_index: int,
) -> tuple[Mapping[str, Any] | None, bool]:
    raw = record.raw
    if raw.callee_form == "dynamic" or raw.local_binding_state == "unsupported":
        _require_unresolved(record, "unsupported_callee", record_index=record_index)
        return None, True

    caller_candidates: list[Mapping[str, Any]]
    if raw.owner.kind == "file":
        caller_candidates = [file_node]
    elif raw.owner.kind == "unindexed":
        caller_candidates = []
    else:
        assert raw.owner.definition_start_byte is not None
        assert raw.owner.definition_end_byte is not None
        caller_candidates = [
            node
            for kind in _CALLABLE_KINDS
            for node in callables.get(
                (
                    raw.source_file,
                    raw.owner.definition_start_byte,
                    raw.owner.definition_end_byte,
                    kind,
                ),
                (),
            )
            if node.get("language") == raw.language
        ]
    if not caller_candidates:
        _require_unresolved(record, "caller_not_indexed", record_index=record_index)
        return None, True
    if len(caller_candidates) != 1:
        _require_unresolved(record, "caller_ambiguous", record_index=record_index)
        return None, True
    caller = caller_candidates[0]
    if (
        record.caller_id != caller.get("id")
        or record.caller_kind != caller.get("kind")
    ):
        raise _record_error(record_index, "Call caller outcome is stale")

    binding_reason = {
        "shadowed": "local_binding_shadowed",
        "ambiguous": "local_binding_ambiguous",
    }.get(raw.local_binding_state)
    if binding_reason is not None:
        _require_unresolved(record, binding_reason, record_index=record_index)
        return caller, True

    exact_references = references.get(
        (
            raw.source_file,
            raw.source_hash,
            raw.callee_start_byte,
            raw.callee_end_byte,
        ),
        (),
    )
    reference = exact_references[0] if len(exact_references) == 1 else None
    local_target, local_reason = _current_local_target(raw, callables=callables)
    imported_reference = (
        reference
        if reference is not None
        and reference.status == "resolved"
        and reference.binding is not None
        and not reference.binding.type_only
        and reference.target_kind in _CALLABLE_KINDS
        else None
    )
    if local_target is not None and imported_reference is not None:
        _require_unresolved(record, "conflicting_resolution", record_index=record_index)
        return caller, True
    if local_target is not None:
        _require_resolved(
            record,
            resolution="exact",
            target=local_target,
            record_index=record_index,
        )
        return caller, False
    if imported_reference is not None:
        _require_resolved(
            record,
            resolution="import-resolved",
            target=imported_reference,
            record_index=record_index,
        )
        return caller, False
    if reference is not None and reference.status == "unresolved":
        _require_unresolved(
            record,
            "reference_unresolved",
            reference_reason=reference.unresolved_reason,
            record_index=record_index,
        )
        return caller, True
    if (
        reference is not None
        and reference.status == "resolved"
        and reference.binding is not None
        and not reference.binding.type_only
        and reference.target_kind not in _CALLABLE_KINDS
    ):
        _require_unresolved(record, "target_not_callable", record_index=record_index)
        return caller, True
    if local_reason is not None:
        _require_unresolved(record, local_reason, record_index=record_index)
        return caller, True
    _require_unresolved(record, "callee_not_proven", record_index=record_index)
    return caller, True


def _current_local_target(
    raw: RawCallSite,
    *,
    callables: Mapping[
        tuple[str, int, int, str],
        Sequence[Mapping[str, Any]],
    ],
) -> tuple[Mapping[str, Any] | None, str | None]:
    if raw.local_binding_state != "definite":
        return None, None
    binding = raw.local_candidates[0]
    candidates = [
        node
        for node in callables.get(
            (
                raw.source_file,
                binding.definition_start_byte,
                binding.definition_end_byte,
                binding.callable_kind,
            ),
            (),
        )
        if node.get("name") == binding.name and node.get("language") == raw.language
    ]
    if not candidates:
        return None, "local_target_not_indexed"
    if len(candidates) != 1:
        return None, "local_binding_ambiguous"
    return candidates[0], None


def _require_resolved(
    record: CallRecord,
    *,
    resolution: str,
    target: Mapping[str, Any] | SymbolReferenceRecord,
    record_index: int,
) -> None:
    target_id = (
        target.target_id
        if isinstance(target, SymbolReferenceRecord)
        else target.get("id")
    )
    target_file = (
        target.target_file
        if isinstance(target, SymbolReferenceRecord)
        else target.get("file_path")
    )
    target_kind = (
        target.target_kind
        if isinstance(target, SymbolReferenceRecord)
        else target.get("kind")
    )
    expected_basis = (
        "local_callable" if resolution == "exact" else "imported_reference"
    )
    if (
        record.status != "resolved"
        or record.resolution != resolution
        or record.resolution_basis != expected_basis
        or record.target_id != target_id
        or record.target_file != target_file
        or record.target_kind != target_kind
    ):
        raise _record_error(
            record_index,
            "Resolved call outcome does not match current local/reference evidence",
        )


def _require_unresolved(
    record: CallRecord,
    reason: str,
    *,
    reference_reason: str | None = None,
    record_index: int,
) -> None:
    if (
        record.status != "unresolved"
        or record.unresolved_reason != reason
        or record.reference_unresolved_reason != reference_reason
    ):
        raise _record_error(
            record_index,
            "Unresolved call outcome does not match current local/reference evidence",
        )


def validate_call_edge(
    edge: GraphEdge,
    *,
    edge_index: int,
    indexed_nodes: Mapping[str, Mapping[str, Any]],
    file_hashes: Mapping[str, str] | None,
    call_index: Mapping[tuple[str, str, str], Sequence[CallRecord]],
) -> None:
    if edge.resolution not in {"exact", "import-resolved"}:
        raise GraphContractError(
            "GRAPH_RESOLUTION_UNSUPPORTED",
            "Resolution tier is not permitted for this graph edge type",
            {"edge_index": edge_index, "resolution": edge.resolution},
        )
    if edge.directed is not True:
        raise GraphContractError(
            "INVALID_GRAPH_EDGE",
            "Call edges must be directed",
            {"edge_index": edge_index, "field": "directed"},
        )
    source = indexed_nodes.get(edge.from_id)
    target = indexed_nodes.get(edge.to_id)
    if source is None or target is None:
        raise GraphContractError(
            "GRAPH_ENDPOINT_MISSING",
            "Graph edge references an endpoint outside the indexed symbol set",
            {"edge_index": edge_index},
        )
    source_kind = source.get("kind")
    target_kind = target.get("kind")
    source_file = source.get("file_path")
    target_file = target.get("file_path")
    if (
        source_kind not in _CALLER_KINDS
        or target_kind not in _CALLABLE_KINDS
        or not isinstance(source_file, str)
        or not isinstance(target_file, str)
    ):
        raise GraphContractError(
            "INVALID_GRAPH_EDGE",
            "Call edge endpoints must be an indexed file/callable caller and callable target",
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
    matches = [
        record
        for record in call_index.get(
            (edge.from_id, edge.to_id, edge.resolution),
            (),
        )
        if (
            record.raw.source_file == source_file
            and record.raw.line == edge.evidence.line
            and record.raw.source_hash == edge.evidence.content_hash
            and record.caller_kind == source_kind
            and record.target_kind == target_kind
            and record.target_file == target_file
        )
    ]
    if not matches:
        raise GraphContractError(
            "GRAPH_EVIDENCE_INVALID",
            "Call edge is not backed by a matching current resolved call record",
            {"edge_index": edge_index, "field": "call_record"},
        )
    if not all(any(item.kind == "call_site" for item in record.support) for record in matches):
        raise GraphContractError(
            "GRAPH_EVIDENCE_INVALID",
            "Call edge record has no call-site support",
            {"edge_index": edge_index, "field": "support"},
        )


def _index_references(
    references: Sequence[SymbolReferenceRecord],
    *,
    file_hashes: Mapping[str, str],
) -> Mapping[tuple[str, str, int, int], tuple[SymbolReferenceRecord, ...]]:
    indexed: dict[
        tuple[str, str, int, int],
        list[SymbolReferenceRecord],
    ] = {}
    for reference in references:
        if not isinstance(reference, SymbolReferenceRecord):
            raise _error("Call validation reference is not a SymbolReferenceRecord")
        if file_hashes.get(reference.raw.source_file) != reference.raw.source_hash:
            raise _error(
                "Call validation reference evidence is stale",
                file=reference.raw.source_file,
            )
        indexed.setdefault(
            (
                reference.raw.source_file,
                reference.raw.source_hash,
                reference.raw.start_byte,
                reference.raw.end_byte,
            ),
            [],
        ).append(reference)
    return MappingProxyType({key: tuple(values) for key, values in indexed.items()})


def _validate_target(
    record: CallRecord,
    *,
    indexed_nodes: Mapping[str, Mapping[str, Any]],
    record_index: int,
) -> Mapping[str, Any]:
    assert record.target_id is not None
    target = indexed_nodes.get(record.target_id)
    if target is None:
        raise _record_error(record_index, "Call target endpoint is missing")
    if (
        target.get("kind") != record.target_kind
        or target.get("file_path") != record.target_file
        or not _same_language_family(target.get("language"), record.raw.language)
    ):
        raise _record_error(record_index, "Call target endpoint is stale")
    return target


def _validate_support(
    record: CallRecord,
    *,
    caller: Mapping[str, Any] | None,
    target: Mapping[str, Any],
    file_hashes: Mapping[str, str],
    record_index: int,
) -> None:
    assert record.caller_id is not None
    call_sites = [item for item in record.support if item.kind == "call_site"]
    if len(call_sites) != 1 or (
        call_sites[0].file != record.raw.source_file
        or call_sites[0].line != record.raw.line
        or call_sites[0].content_hash != file_hashes.get(record.raw.source_file)
        or call_sites[0].endpoint_id != record.caller_id
    ):
        raise _record_error(record_index, "Call-site support is missing or stale")
    caller_definitions = [
        item for item in record.support if item.kind == "caller_definition"
    ]
    if record.caller_kind == "file":
        if caller_definitions:
            raise _record_error(record_index, "File call has caller definition support")
    elif caller is None or len(caller_definitions) != 1 or not _supports_node(
        caller_definitions[0], caller
    ):
        raise _record_error(record_index, "Caller definition support is stale")
    if record.resolution == "exact":
        local_definitions = [
            item for item in record.support if item.kind == "local_definition"
        ]
        if len(local_definitions) != 1 or not _supports_node(
            local_definitions[0], target
        ):
            raise _record_error(record_index, "Local definition support is stale")


def _validate_reference(
    record: CallRecord,
    *,
    references: Mapping[
        tuple[str, str, int, int],
        Sequence[SymbolReferenceRecord],
    ],
    file_hashes: Mapping[str, str],
    target: Mapping[str, Any],
    record_index: int,
) -> None:
    assert record.caller_id is not None
    assert record.target_id is not None
    candidates = references.get(
        (
            record.raw.source_file,
            record.raw.source_hash,
            record.raw.callee_start_byte,
            record.raw.callee_end_byte,
        ),
        (),
    )
    matches = [
        reference
        for reference in candidates
        if (
            reference.status == "resolved"
            and reference.binding is not None
            and not reference.binding.type_only
            and reference.source_id == record.caller_id
            and reference.source_kind == record.caller_kind
            and reference.target_file == record.target_file
            and reference.target_id == record.target_id
            and reference.target_kind == record.target_kind
            and reference.resolution_control_files == record.resolution_control_files
            and reference.resolution_configuration == record.resolution_configuration
        )
    ]
    if len(candidates) != 1 or len(matches) != 1:
        raise _record_error(
            record_index,
            "Import-resolved call has no unique matching symbol reference",
        )
    definition_support = [
        item
        for item in matches[0].support
        if item.kind == "definition" and item.endpoint_id == record.target_id
    ]
    if (
        len(definition_support) != 1
        or definition_support[0].file != record.target_file
        or definition_support[0].line != target.get("line")
        or definition_support[0].content_hash
        != file_hashes.get(cast(str, record.target_file))
    ):
        raise _record_error(record_index, "Symbol reference target support is stale")


def _supports_node(support: Any, node: Mapping[str, Any]) -> bool:
    return (
        support.endpoint_id == node.get("id")
        and support.file == node.get("file_path")
        and support.line == node.get("line")
        and support.content_hash == node.get("content_hash")
    )


def _same_language_family(left: Any, right: str) -> bool:
    if not isinstance(left, str):
        return False
    return left == right or {left, right} <= {"javascript", "typescript"}


def _raise_edge_evidence_error(
    edge_index: int,
    field: str,
    *,
    expected: Any,
    actual: Any,
) -> None:
    raise GraphContractError(
        "GRAPH_EVIDENCE_INVALID",
        "Call edge evidence does not match current indexed content",
        {
            "edge_index": edge_index,
            "field": field,
            "expected": cast(Any, expected),
            "actual": cast(Any, actual),
        },
    )


def _record_error(record_index: int, message: str) -> GraphContractError:
    return GraphContractError(
        "INVALID_GRAPH_STATE",
        message,
        {"field": "calls", "record_index": record_index},
    )


def _error(message: str, **details: Any) -> GraphContractError:
    return GraphContractError(
        "INVALID_GRAPH_STATE",
        message,
        cast(dict[str, Any], details),
    )
