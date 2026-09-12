"""Pure resolution and projection of authored type relationships.

This family owns declaration contracts, independently of executable references.
The imported branch reuses contained language export resolvers; it never
inserts synthetic observations into the existing reference family.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Mapping, Sequence

from loci.parser._binding_context import ExecutableOwner
from loci.parser.reference_models import ImportBinding, RawLocalExport, RawSymbolReference
from loci.parser.symbols import Symbol
from loci.parser.type_models import RawTypeObservation, valid_type_import_path

from ._javascript_references import (
    JavaScriptReferenceIndex,
    build_javascript_reference_index,
    resolve_javascript_reference,
)
from ._python_references import (
    PythonReferenceIndex, _is_imported_submodule, build_python_reference_index,
    resolve_python_reference,
)
from .contracts import GraphContractError, GraphEdge, GraphEvidence
from .imports import ImportRecord
from .type_models import TypeControl, TypeRelationRecord, TypeSupport

TYPE_EDGE_KINDS = frozenset({"uses_type", "extends", "implements"})
TYPE_TARGET_KINDS = frozenset({"class", "interface", "type", "enum"})
VALUE_TARGET_KINDS = frozenset({"class", "enum", "function", "constant"})
MAX_TYPE_CANDIDATES = 16


@dataclass(frozen=True)
class _ResolutionIndex:
    declarations: Mapping[tuple[str, int, int], tuple[Symbol, ...]]
    imports: Mapping[tuple[str, ImportBinding], tuple[ImportRecord, ...]]
    javascript: JavaScriptReferenceIndex
    python: PythonReferenceIndex
    file_hashes: Mapping[str, str]
    input_hashes: Mapping[str, str]
    all_imports: Sequence[ImportRecord]
    exports: Sequence[RawLocalExport]


def resolve_type_relations(
    observations: Sequence[RawTypeObservation],
    *,
    symbols: Sequence[Symbol],
    imports: Sequence[ImportRecord],
    exports: Sequence[RawLocalExport],
    file_hashes: Mapping[str, str],
    input_hashes: Mapping[str, str],
) -> list[TypeRelationRecord]:
    """Resolve only the exact lexical/import universe carried by each site."""
    declarations: dict[tuple[str, int, int], list[Symbol]] = defaultdict(list)
    imported: dict[tuple[str, ImportBinding], list[ImportRecord]] = defaultdict(list)
    for symbol in symbols:
        if symbol.kind != "file":
            declarations[(symbol.file_path, symbol.byte_offset,
                          symbol.byte_offset + symbol.byte_length)].append(symbol)
    for record in imports:
        if record.raw.language not in {"typescript", "python", "javascript"}:
            continue
        for binding in record.raw.bindings:
            if binding.local_name is not None:
                imported[(record.raw.source_file, binding)].append(record)
    index = _ResolutionIndex(
        declarations={key: tuple(value) for key, value in declarations.items()},
        imports={key: tuple(value) for key, value in imported.items()},
        javascript=build_javascript_reference_index(
            symbols, imports, exports,
            file_nodes={symbol.file_path: symbol for symbol in symbols
                        if symbol.kind == "file"},
        ),
        python=build_python_reference_index(
            symbols, imports, exports,
            file_nodes={symbol.file_path: symbol for symbol in symbols if symbol.kind == "file"},
        ),
        file_hashes=file_hashes,
        input_hashes=input_hashes,
        all_imports=imports,
        exports=exports,
    )
    return [_resolve(raw, index) for raw in sorted(observations, key=type_site_key)]


def type_site_key(raw: RawTypeObservation) -> tuple:
    return (raw.source_file, raw.start_byte, raw.end_byte, raw.relation,
            raw.context, raw.lookup_space, raw.owner.start_byte, raw.owner.end_byte)


def _resolve(raw: RawTypeObservation, index: _ResolutionIndex) -> TypeRelationRecord:
    if not isinstance(raw, RawTypeObservation):
        raise _error("Type observation has an invalid record type")
    if index.file_hashes.get(raw.source_file) != raw.source_hash:
        raise _error("Type observation source hash is stale", file=raw.source_file)
    owners = tuple(symbol for symbol in index.declarations.get(
        (raw.source_file, raw.owner.start_byte, raw.owner.end_byte), ()
    ) if symbol.kind == raw.owner.kind)
    owner = owners[0] if len(owners) == 1 else None
    support = [TypeSupport("type_site", raw.source_file, raw.line, raw.source_hash,
                           owner.id if owner else None)]
    if owner is not None:
        support.append(TypeSupport("owner", raw.source_file, owner.line,
                                   raw.source_hash, owner.id))
    universe = "lexical_scope" if raw.local_bindings else "unavailable"
    scope_file = raw.source_file if raw.local_bindings else None
    all_candidates = _local_candidates(raw, index)
    candidates = all_candidates[:MAX_TYPE_CANDIDATES]
    extra_truncated = max(0, len(all_candidates) - MAX_TYPE_CANDIDATES)
    complete = raw.candidates_complete and not extra_truncated if raw.local_bindings else False
    truncated = raw.candidates_truncated + extra_truncated

    def finish(
        reason: str | None,
        *,
        target: Symbol | None = None,
        basis: str | None = None,
        extra_support: Sequence[TypeSupport] = (),
        controls: Sequence[TypeControl] = (),
        candidate_ids: tuple[str, ...] = candidates,
        candidate_universe: str = universe,
        candidate_scope_file: str | None = scope_file,
        candidates_complete: bool = complete,
        candidates_truncated: int = truncated,
    ) -> TypeRelationRecord:
        return TypeRelationRecord(
            raw=raw,
            source_id=owner.id if owner else None,
            source_kind=owner.kind if owner else None,
            target_id=target.id if target else None,
            target_file=target.file_path if target else None,
            target_kind=target.kind if target else None,
            status="resolved" if reason is None else "unresolved",
            unresolved_reason=reason,
            resolution_basis=basis,
            support=tuple(dict.fromkeys((*support, *extra_support))),
            resolution_controls=tuple(controls),
            candidate_universe=candidate_universe,
            candidate_scope_file=candidate_scope_file,
            candidate_ids=candidate_ids,
            candidates_complete=candidates_complete,
            candidates_truncated=candidates_truncated,
        )

    if owner is None:
        return finish("ambiguous_owner" if len(owners) > 1 else "unsupported_owner")
    if raw.owner.kind == "unindexed":
        return finish("unsupported_owner")
    if raw.binding_state == "unsupported" or raw.unsupported_reason is not None:
        return finish("unsupported_syntax")
    if raw.candidates_truncated or not raw.candidates_complete:
        return finish("binding_limit")
    if raw.binding_state == "shadowed":
        return finish("type_parameter")
    if raw.binding_state == "ambiguous":
        return finish("binding_ambiguous")
    if raw.binding_state == "unbound":
        return finish("binding_not_found")
    if raw.binding_state == "local":
        if len(raw.local_bindings) != 1 or len(raw.path) != 1:
            return finish("unsupported_reference")
        binding = raw.local_bindings[0]
        targets = tuple(symbol for symbol in index.declarations.get(
            (raw.source_file, binding.declaration_start_byte,
             binding.declaration_end_byte), ()
        ) if symbol.name == binding.name and symbol.kind == binding.kind)
        if len(targets) != 1:
            return finish("ambiguous_target" if len(targets) > 1 else "binding_unindexed")
        target = targets[0]
        definition = _definition(target, index)
        args = dict(extra_support=(definition,), candidate_ids=(target.id,),
                    candidate_universe="lexical_scope", candidate_scope_file=raw.source_file,
                    candidates_complete=True, candidates_truncated=0)
        if not _target_compatible(raw, target):
            return finish("unsupported_target", **args)
        if raw.relation != "uses_type" and owner.id == target.id:
            return finish("self_heritage", **args)
        return finish(None, target=target, basis="lexical_binding", **args)
    if raw.binding_state != "imported" or len(raw.import_bindings) != 1:
        return finish("unsupported_reference")
    binding = raw.import_bindings[0]
    if raw.language in {"typescript", "javascript"} and not ((binding.kind == "symbol" and len(raw.path) == 1)
            or (binding.kind == "namespace" and len(raw.path) == 2)):
        return finish("unsupported_reference")
    matches = index.imports.get((raw.source_file, binding), ())
    if len(matches) != 1:
        return finish("binding_ambiguous" if matches else "import_unresolved")
    imported = matches[0]
    controls = _controls(imported.resolution_control_files, index)
    if imported.status != "resolved" or imported.target_file is None:
        return finish("import_unresolved", controls=controls)
    import_support = TypeSupport("import_binding", raw.source_file, binding.import_line,
                                 raw.source_hash, imported.target_id)
    # This temporary value only crosses the existing export-resolver seam.
    # Its executable owner is deliberately irrelevant and is never persisted.
    reference = RawSymbolReference(
        source_file=raw.source_file, language=raw.language,
        line=raw.line, column=raw.column, start_byte=raw.start_byte, end_byte=raw.end_byte,
        text=raw.text, path=raw.path, candidate_bindings=(binding,),
        binding_state="definite", source_hash=raw.source_hash,
        owner=ExecutableOwner("file", None, None, None, None),
    )
    if raw.language == "python":
        if not _exact_python_type_path(reference, binding, imported):
            return finish("unsupported_reference", extra_support=(import_support,), controls=controls)
        outcome = resolve_python_reference(reference, binding=binding,
                                           import_record=imported, index=index.python)
        surfaces = index.python.surfaces
    else:
        outcome = resolve_javascript_reference(reference, binding=binding,
                                               import_record=imported, index=index.javascript)
        surfaces = index.javascript.surfaces
    controls = _controls(tuple(sorted(set((*imported.resolution_control_files,
                                          *outcome.resolution_control_files)))), index)
    extra = (import_support, *(TypeSupport(item.kind, item.file, item.line,
                                          item.content_hash, item.endpoint_id)
                               for item in outcome.support))
    if outcome.target is None:
        # Export surfaces can omit alternatives after their own limits or lose
        # candidates to unresolved routes. Never label that list exhaustive.
        name = binding.imported_name if binding.kind == "symbol" and len(raw.path) == 1 else raw.path[-1]
        visible = tuple(sorted({item.symbol.id for item in surfaces.get(
            (imported.target_file, name), ())}))
        return finish(outcome.reason or "target_not_indexed", extra_support=extra,
                      controls=controls, candidate_ids=visible[:MAX_TYPE_CANDIDATES],
                      candidate_universe="import_surface",
                      candidate_scope_file=imported.target_file, candidates_complete=False,
                      candidates_truncated=max(0, len(visible) - MAX_TYPE_CANDIDATES))
    target = outcome.target
    args = dict(extra_support=extra, controls=controls, candidate_ids=(target.id,),
                candidate_universe="import_surface", candidate_scope_file=imported.target_file,
                candidates_complete=True, candidates_truncated=0)
    if not _target_compatible(raw, target):
        return finish("unsupported_target", **args)
    if raw.language == "typescript" and raw.relation == "extends" and owner.kind == "class" and (
        binding.type_only or _type_only_value_route(outcome.support, index)
    ):
        return finish("type_only_value", **args)
    if raw.relation != "uses_type" and owner.id == target.id:
        return finish("self_heritage", **args)
    return finish(None, target=target, basis=outcome.basis, **args)


def _exact_python_type_path(
    raw: RawSymbolReference, binding: ImportBinding, imported: ImportRecord,
) -> bool:
    """The value resolver permits attribute suffixes; a type needs the exact name."""
    if not valid_type_import_path("python", raw.path, binding):
        return False
    if binding.kind == "symbol":
        return len(raw.path) == (2 if _is_imported_submodule(raw, binding, imported) else 1)
    return True


def _local_candidates(raw: RawTypeObservation, index: _ResolutionIndex) -> tuple[str, ...]:
    ids = {symbol.id for binding in raw.local_bindings
           for symbol in index.declarations.get(
               (raw.source_file, binding.declaration_start_byte, binding.declaration_end_byte), ())
           if symbol.name == binding.name and symbol.kind == binding.kind}
    return tuple(sorted(ids))


def _target_compatible(raw: RawTypeObservation, target: Symbol) -> bool:
    if raw.relation == "extends" and raw.owner.kind == "class":
        return target.kind == "class"
    if raw.relation in {"extends", "implements"}:
        return target.kind in {"interface", "class", "type"}
    return target.kind in (TYPE_TARGET_KINDS if raw.lookup_space == "type"
                           else VALUE_TARGET_KINDS)


def _definition(symbol: Symbol, index: _ResolutionIndex) -> TypeSupport:
    content_hash = index.file_hashes.get(symbol.file_path)
    if content_hash is None:
        raise _error("Type definition has no current source hash", target=symbol.id)
    return TypeSupport("definition", symbol.file_path, symbol.line, content_hash, symbol.id)


def _controls(files: Sequence[str], index: _ResolutionIndex) -> tuple[TypeControl, ...]:
    result = []
    for file in sorted(set(files)):
        content_hash = index.input_hashes.get(file)
        if content_hash is None:
            raise _error("Type resolution control has no current hash", file=file)
        result.append(TypeControl(file, content_hash))
    return tuple(result)


def _type_only_value_route(support: Sequence, index: _ResolutionIndex) -> bool:
    """Conservatively require runtime-capable authored steps for class extends.

    The existing export index keeps line/endpoint provenance, not per-binding
    value namespaces. A mixed or unidentifiable step cannot prove this route.
    """
    for item in support:
        if item.kind == "reexport":
            records = [record for record in index.all_imports
                       if record.raw.source_file == item.file and record.raw.line == item.line
                       and record.raw.is_reexport and record.target_id == item.endpoint_id]
            if not records or any(record.raw.type_only or any(
                binding.type_only for binding in record.raw.bindings
            ) for record in records):
                return True
        elif item.kind == "local_export":
            records = [export for export in index.exports
                       if export.source_file == item.file and export.line == item.line]
            if not records or any(export.type_only for export in records):
                return True
    return False


def materialize_type_edges(records: Sequence[TypeRelationRecord]) -> list[GraphEdge]:
    projected: dict[tuple[str, str, str], GraphEdge] = {}
    for record in sorted(records, key=lambda item: type_site_key(item.raw)):
        if record.status != "resolved":
            continue
        assert record.source_id is not None and record.target_id is not None
        key = (record.raw.relation, record.source_id, record.target_id)
        projected.setdefault(key, GraphEdge(
            from_id=record.source_id, to_id=record.target_id, type=record.raw.relation,
            directed=True, namespace="loci", resolution=record.resolution,
            evidence=GraphEvidence(file=record.raw.source_file, line=record.raw.line,
                                   content_hash=record.raw.source_hash),
        ))
    return list(projected.values())


def _error(message: str, **details) -> GraphContractError:
    return GraphContractError("INVALID_TYPE_RELATION", message, details)
