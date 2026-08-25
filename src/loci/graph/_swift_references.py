from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Mapping, Sequence, cast

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
from .swift_modules import SwiftModuleIndex


_SwiftExportKey = tuple[str, str]
_ImportLookup = Mapping[
    tuple[str, ImportBinding],
    tuple[ImportRecord, ...],
]


@dataclass(frozen=True, slots=True)
class _SwiftExportTarget:
    symbol: Symbol
    support: tuple[ReferenceSupport, ...]


@dataclass(frozen=True, slots=True)
class SwiftReferenceIndex:
    """Importable Swift declarations keyed by their owning module endpoint."""

    surfaces: Mapping[_SwiftExportKey, tuple[_SwiftExportTarget, ...]]
    ambiguous: frozenset[_SwiftExportKey]
    module_directories: tuple[tuple[str, str], ...]


@dataclass(frozen=True, slots=True)
class SwiftReferenceOutcome:
    target: Symbol | None
    reason: ReferenceUnresolvedReason | None
    import_unresolved_reason: ImportUnresolvedReason | None
    basis: ReferenceResolutionBasis | None
    support: tuple[ReferenceSupport, ...]
    resolution_control_files: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class SwiftBindingSelection:
    """One deferred Swift binding, or the verdict that none can apply."""

    binding: ImportBinding | None
    import_record: ImportRecord | None
    out_of_scope: bool


def build_swift_reference_index(
    symbols: Sequence[Symbol],
    exports: Sequence[RawLocalExport],
    *,
    file_nodes: Mapping[str, Symbol],
    swift_modules: SwiftModuleIndex | None,
) -> SwiftReferenceIndex:
    """Compile exported Swift declarations under their declared module nodes."""
    definitions: dict[tuple[str, int, int], list[Symbol]] = {}
    for symbol in symbols:
        if symbol.language != "swift" or symbol.kind in {"file", "module"}:
            continue
        key = (
            symbol.file_path,
            symbol.byte_offset,
            symbol.byte_offset + symbol.byte_length,
        )
        candidates = definitions.setdefault(key, [])
        if len(candidates) <= MAX_REFERENCE_RESOLUTION_CANDIDATES:
            candidates.append(symbol)

    directories: tuple[tuple[str, str], ...] = ()
    if swift_modules is not None:
        directories = tuple(
            sorted(
                swift_modules.directories_by_module.items(),
                key=lambda item: (-len(item[1]), item[0]),
            )
        )

    surfaces: dict[_SwiftExportKey, dict[str, _SwiftExportTarget]] = {}
    ambiguous: set[_SwiftExportKey] = set()
    for export in exports:
        if not isinstance(export, RawLocalExport):
            raise _error("Swift reference export is not a RawLocalExport")
        if export.language != "swift":
            continue
        file_node = file_nodes.get(export.source_file)
        if (
            file_node is None
            or file_node.language != "swift"
            or file_node.content_hash != export.source_hash
        ):
            raise _error(
                "Swift export source evidence is stale",
                file=export.source_file,
            )
        module_id = _owning_module(export.source_file, directories)
        if module_id is None:
            continue
        key = (module_id, export.exported_name)
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
        if (
            len(candidates) != 1
            or export.local_name is None
            or candidates[0].name != export.local_name
        ):
            ambiguous.add(key)
            continue
        target = candidates[0]
        targets = surfaces.setdefault(key, {})
        if (
            target.id not in targets
            and len(targets) >= MAX_REFERENCE_RESOLUTION_CANDIDATES
        ):
            ambiguous.add(key)
            continue
        targets[target.id] = _SwiftExportTarget(
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
        )
        if len(targets) > 1:
            ambiguous.add(key)

    return SwiftReferenceIndex(
        surfaces=MappingProxyType({
            key: tuple(sorted(targets.values(), key=lambda item: item.symbol.id))
            for key, targets in sorted(surfaces.items())
        }),
        ambiguous=frozenset(ambiguous),
        module_directories=directories,
    )


def select_swift_reference_binding(
    raw: RawSymbolReference,
    *,
    imports_by_binding: _ImportLookup,
    index: SwiftReferenceIndex,
) -> SwiftBindingSelection:
    """Pick the one imported module whose surface declares this bare name.

    Swift names an imported declaration without qualifying it, so the binding
    is only knowable once the module surfaces are indexed. A name no imported
    module declares is not a cross-module reference at all — it is a member, a
    local, or a system framework name — so it is reported out of scope rather
    than recorded as an unresolved cross-module reference.
    """
    if raw.language != "swift" or raw.binding_state != "deferred":
        return SwiftBindingSelection(None, None, False)
    name = raw.path[0]
    exact: list[tuple[ImportBinding, ImportRecord]] = []
    unresolved: list[tuple[ImportBinding, ImportRecord]] = []
    for binding in raw.candidate_bindings:
        records = imports_by_binding.get((raw.source_file, binding), ())
        if len(records) > 1:
            return SwiftBindingSelection(None, None, False)
        if not records:
            continue
        record = records[0]
        if record.status == "unresolved":
            unresolved.append((binding, record))
            continue
        if (
            record.target_kind == "module"
            and record.target_id is not None
            and (
                (record.target_id, name) in index.surfaces
                or (record.target_id, name) in index.ambiguous
            )
        ):
            exact.append((binding, record))
    if len(exact) == 1:
        # The module the reference sits in wins over any import of the same
        # name, so a name its own module also exports cannot be attributed.
        own = _owning_module(raw.source_file, index.module_directories)
        if own is not None and own != exact[0][1].target_id:
            if (own, name) in index.surfaces or (own, name) in index.ambiguous:
                return SwiftBindingSelection(None, None, False)
        return SwiftBindingSelection(exact[0][0], exact[0][1], False)
    if exact:
        return SwiftBindingSelection(None, None, False)
    return SwiftBindingSelection(None, None, True)


def resolve_swift_reference(
    raw: RawSymbolReference,
    *,
    binding: ImportBinding,
    import_record: ImportRecord,
    index: SwiftReferenceIndex,
) -> SwiftReferenceOutcome:
    """Resolve one bare Swift name inside its proven module endpoint."""
    if (
        binding.kind not in {"module", "symbol"}
        or not raw.path
        or import_record.target_kind != "module"
        or import_record.target_id is None
    ):
        return _unresolved("unsupported_reference")

    if binding.kind == "symbol":
        # Declaration imports bind their final component directly.  The
        # module import record still proves the owning module; the indexed
        # export surface proves the declaration itself.
        if (
            raw.binding_state == "deferred"
            or binding.local_name != raw.path[0]
            or binding.imported_name != raw.path[0]
            or binding not in import_record.raw.bindings
            or import_record.raw.imported_name != binding.imported_name
        ):
            return _unresolved("unsupported_reference")
        name = binding.imported_name
    elif raw.binding_state == "deferred":
        # A deferred name is bare, so the declaration is the path root.
        name = raw.path[0]
    elif len(raw.path) >= 2:
        # The binding matched the module's own name, so the reference is
        # module-qualified and the declaration is the segment after it.
        name = raw.path[1]
    else:
        return _unresolved("unsupported_reference")
    assert name is not None
    key = (import_record.target_id, name)
    if key in index.ambiguous:
        return _unresolved("ambiguous_target")
    targets = index.surfaces.get(key, ())
    if len(targets) > 1:
        return _unresolved("ambiguous_target")
    if not targets:
        return _unresolved("target_not_indexed")
    target = targets[0]
    return SwiftReferenceOutcome(
        target=target.symbol,
        reason=None,
        import_unresolved_reason=None,
        basis="direct_binding",
        support=target.support,
        resolution_control_files=(),
    )


def _owning_module(
    file: str,
    directories: Sequence[tuple[str, str]],
) -> str | None:
    """Return the deepest declared module directory containing ``file``."""
    for module_id, directory in directories:
        if not directory:
            return module_id
        if file.startswith(f"{directory}/"):
            return module_id
    return None


def _unresolved(reason: ReferenceUnresolvedReason) -> SwiftReferenceOutcome:
    return SwiftReferenceOutcome(
        target=None,
        reason=reason,
        import_unresolved_reason=None,
        basis=None,
        support=(),
        resolution_control_files=(),
    )


def _error(message: str, **details: object) -> GraphContractError:
    return GraphContractError(
        "GRAPH_REFERENCE_INDEX_INVALID",
        message,
        cast(dict[str, JSONValue], details),
    )
