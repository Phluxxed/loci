from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Mapping, Sequence, TypeAlias, cast

from loci.parser.imports import ImportUnresolvedReason
from loci.parser.reference_models import (
    MAX_REFERENCE_RESOLUTION_CANDIDATES,
    ImportBinding,
    RawLocalExport,
    RawSymbolReference,
)
from loci.parser.symbols import Symbol

from .contracts import GraphContractError, JSONValue
from .imports import ImportRecord
from .references import (
    ReferenceResolutionBasis,
    ReferenceSupport,
    ReferenceUnresolvedReason,
)


_ExportKey: TypeAlias = tuple[str, str]
_JAVASCRIPT_LANGUAGES = frozenset({"javascript", "typescript"})


@dataclass(frozen=True, slots=True)
class _JavaScriptExportTarget:
    symbol: Symbol
    support: tuple[ReferenceSupport, ...]
    control_files: tuple[str, ...]
    via_reexport: bool


@dataclass(frozen=True, slots=True)
class JavaScriptReferenceIndex:
    surfaces: Mapping[_ExportKey, tuple[_JavaScriptExportTarget, ...]]
    ambiguous: frozenset[_ExportKey]
    cyclic_files: frozenset[str]
    import_failures: Mapping[_ExportKey, frozenset[ImportUnresolvedReason]]
    star_import_failures: Mapping[str, frozenset[ImportUnresolvedReason]]


@dataclass(frozen=True, slots=True)
class JavaScriptReferenceOutcome:
    target: Symbol | None
    reason: ReferenceUnresolvedReason | None
    import_unresolved_reason: ImportUnresolvedReason | None
    basis: ReferenceResolutionBasis | None
    support: tuple[ReferenceSupport, ...]
    resolution_control_files: tuple[str, ...]


def build_javascript_reference_index(
    symbols: Sequence[Symbol],
    imports: Sequence[ImportRecord],
    exports: Sequence[RawLocalExport],
    *,
    file_nodes: Mapping[str, Symbol],
) -> JavaScriptReferenceIndex:
    """Compile exact JavaScript and TypeScript export surfaces without I/O."""
    del imports  # Re-export routes are added in the next incremental slice.
    definitions: dict[tuple[str, int, int], list[Symbol]] = {}
    for symbol in symbols:
        if (
            symbol.language in _JAVASCRIPT_LANGUAGES
            and symbol.kind != "file"
            and symbol.qualified_name == symbol.name
        ):
            key = (
                symbol.file_path,
                symbol.byte_offset,
                symbol.byte_offset + symbol.byte_length,
            )
            candidates = definitions.setdefault(key, [])
            if len(candidates) <= MAX_REFERENCE_RESOLUTION_CANDIDATES:
                candidates.append(symbol)

    surfaces: dict[_ExportKey, dict[str, _JavaScriptExportTarget]] = {}
    ambiguous: set[_ExportKey] = set()
    for export in exports:
        if not isinstance(export, RawLocalExport):
            raise _error("JavaScript reference export is not a RawLocalExport")
        if export.language not in _JAVASCRIPT_LANGUAGES:
            continue
        file_node = file_nodes.get(export.source_file)
        if (
            file_node is None
            or file_node.language != export.language
            or file_node.content_hash != export.source_hash
        ):
            raise _error(
                "JavaScript export source evidence is stale",
                file=export.source_file,
            )
        key = (export.source_file, export.exported_name)
        if export.definition_start_byte is None:
            ambiguous.add(key)
            continue
        candidates = definitions.get(
            (
                export.source_file,
                export.definition_start_byte,
                cast(int, export.definition_end_byte),
            ),
            (),
        )
        if len(candidates) != 1:
            ambiguous.add(key)
            continue
        target = candidates[0]
        targets = surfaces.setdefault(key, {})
        if target.id in targets or targets:
            ambiguous.add(key)
            continue
        targets[target.id] = _JavaScriptExportTarget(
            symbol=target,
            support=(
                ReferenceSupport(
                    kind="definition",
                    file=export.source_file,
                    line=export.line,
                    content_hash=export.source_hash,
                    endpoint_id=target.id,
                ),
            ),
            control_files=(),
            via_reexport=False,
        )

    return JavaScriptReferenceIndex(
        surfaces=MappingProxyType({
            key: tuple(value.values()) for key, value in surfaces.items()
        }),
        ambiguous=frozenset(ambiguous),
        cyclic_files=frozenset(),
        import_failures=MappingProxyType({}),
        star_import_failures=MappingProxyType({}),
    )


def resolve_javascript_reference(
    raw: RawSymbolReference,
    *,
    binding: ImportBinding,
    import_record: ImportRecord,
    index: JavaScriptReferenceIndex,
) -> JavaScriptReferenceOutcome:
    """Resolve one ESM reference only inside its proven module endpoint."""
    target_name, basis = _javascript_target_name(raw, binding)
    if target_name is None or basis is None or import_record.target_file is None:
        return _unresolved("unsupported_reference")
    key = (import_record.target_file, target_name)
    if key in index.ambiguous:
        return _unresolved("ambiguous_target")
    targets = index.surfaces.get(key, ())
    if len(targets) > 1:
        return _unresolved("ambiguous_target")
    if not targets:
        return _unresolved("target_not_indexed")
    target = targets[0]
    return JavaScriptReferenceOutcome(
        target=target.symbol,
        reason=None,
        import_unresolved_reason=None,
        basis="reexport_chain" if target.via_reexport else basis,
        support=target.support,
        resolution_control_files=tuple(sorted(set(
            (*import_record.resolution_control_files, *target.control_files)
        ))),
    )


def _javascript_target_name(
    raw: RawSymbolReference,
    binding: ImportBinding,
) -> tuple[str | None, ReferenceResolutionBasis | None]:
    if binding.kind == "symbol" and binding.imported_name is not None:
        return binding.imported_name, "direct_binding"
    if binding.kind == "namespace" and len(raw.path) >= 2:
        return raw.path[1], "qualified_member"
    return None, None


def _unresolved(
    reason: ReferenceUnresolvedReason,
    *,
    import_reason: ImportUnresolvedReason | None = None,
) -> JavaScriptReferenceOutcome:
    return JavaScriptReferenceOutcome(
        target=None,
        reason=reason,
        import_unresolved_reason=import_reason,
        basis=None,
        support=(),
        resolution_control_files=(),
    )


def _error(message: str, **details: object) -> GraphContractError:
    return GraphContractError(
        "GRAPH_CONTRACT_INVALID",
        message,
        cast(dict[str, JSONValue], details),
    )
