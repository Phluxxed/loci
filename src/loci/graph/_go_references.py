from __future__ import annotations

import unicodedata
from dataclasses import dataclass
from pathlib import PurePosixPath
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
from .go_modules import GoPackageIndex
from .imports import ImportRecord
from .references import (
    ReferenceResolutionBasis,
    ReferenceSupport,
    ReferenceUnresolvedReason,
)


_GoExportKey = tuple[str, str]
_ImportLookup = Mapping[
    tuple[str, ImportBinding],
    tuple[ImportRecord, ...],
]


@dataclass(frozen=True, slots=True)
class _GoExportTarget:
    symbol: Symbol
    support: tuple[ReferenceSupport, ...]


@dataclass(frozen=True, slots=True)
class GoReferenceIndex:
    package_names: Mapping[str, str]
    surfaces: Mapping[_GoExportKey, tuple[_GoExportTarget, ...]]
    ambiguous: frozenset[_GoExportKey]


@dataclass(frozen=True, slots=True)
class GoReferenceOutcome:
    target: Symbol | None
    reason: ReferenceUnresolvedReason | None
    import_unresolved_reason: ImportUnresolvedReason | None
    basis: ReferenceResolutionBasis | None
    support: tuple[ReferenceSupport, ...]
    resolution_control_files: tuple[str, ...]


def build_go_reference_index(
    symbols: Sequence[Symbol],
    exports: Sequence[RawLocalExport],
    *,
    file_nodes: Mapping[str, Symbol],
    go_packages: GoPackageIndex | None,
) -> GoReferenceIndex:
    """Compile exported Go definitions under exact Stage 7 package endpoints."""
    definitions: dict[tuple[str, int, int], list[Symbol]] = {}
    for symbol in symbols:
        if symbol.language != "go" or symbol.kind in {"file", "package"}:
            continue
        key = (
            symbol.file_path,
            symbol.byte_offset,
            symbol.byte_offset + symbol.byte_length,
        )
        candidates = definitions.setdefault(key, [])
        if len(candidates) <= MAX_REFERENCE_RESOLUTION_CANDIDATES:
            candidates.append(symbol)

    package_names: dict[str, str] = {}
    packages_by_directory: dict[str, list[Symbol]] = {}
    for package in go_packages.package_nodes if go_packages is not None else ():
        directory, package_name = _package_metadata(package)
        package_names[package.id] = package_name
        packages_by_directory.setdefault(directory, []).append(package)

    surfaces: dict[_GoExportKey, dict[str, _GoExportTarget]] = {}
    ambiguous: set[_GoExportKey] = set()
    for export in exports:
        if not isinstance(export, RawLocalExport):
            raise _error("Go reference export is not a RawLocalExport")
        if export.language != "go":
            continue
        file_node = file_nodes.get(export.source_file)
        if (
            file_node is None
            or file_node.language != "go"
            or file_node.content_hash != export.source_hash
        ):
            raise _error(
                "Go export source evidence is stale",
                file=export.source_file,
            )
        packages = packages_by_directory.get(_parent_directory(export.source_file), ())
        if not packages:
            continue
        keys = tuple((package.id, export.exported_name) for package in packages)
        if export.definition_start_byte is None:
            ambiguous.update(keys)
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
            ambiguous.update(keys)
            continue
        target = candidates[0]
        for key in keys:
            targets = surfaces.setdefault(key, {})
            if (
                target.id not in targets
                and len(targets) >= MAX_REFERENCE_RESOLUTION_CANDIDATES
            ):
                ambiguous.add(key)
                continue
            targets[target.id] = _GoExportTarget(
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

    return GoReferenceIndex(
        package_names=MappingProxyType(dict(sorted(package_names.items()))),
        surfaces=MappingProxyType({
            key: tuple(sorted(targets.values(), key=lambda item: item.symbol.id))
            for key, targets in sorted(surfaces.items())
        }),
        ambiguous=frozenset(ambiguous),
    )


def select_go_reference_binding(
    raw: RawSymbolReference,
    *,
    imports_by_binding: _ImportLookup,
    index: GoReferenceIndex,
) -> tuple[ImportBinding | None, ImportRecord | None]:
    """Select one deferred import by exact declared package name metadata."""
    if raw.language != "go" or raw.binding_state != "deferred":
        return None, None
    exact: list[tuple[ImportBinding, ImportRecord]] = []
    unresolved: list[tuple[ImportBinding, ImportRecord]] = []
    for binding in raw.candidate_bindings:
        records = imports_by_binding.get((raw.source_file, binding), ())
        if len(records) > 1:
            return None, None
        if not records:
            continue
        record = records[0]
        if record.status == "unresolved":
            unresolved.append((binding, record))
            continue
        if (
            record.target_kind == "package"
            and record.target_id is not None
            and index.package_names.get(record.target_id) == raw.path[0]
        ):
            exact.append((binding, record))
    if len(exact) == 1:
        return exact[0]
    if exact:
        return None, None
    if len(unresolved) == 1:
        return unresolved[0]
    return None, None


def resolve_go_reference(
    raw: RawSymbolReference,
    *,
    binding: ImportBinding,
    import_record: ImportRecord,
    index: GoReferenceIndex,
) -> GoReferenceOutcome:
    """Resolve one qualified Go identifier inside its proven package endpoint."""
    if (
        binding.kind != "namespace"
        or len(raw.path) != 2
        or import_record.target_kind != "package"
        or import_record.target_id is None
    ):
        return _unresolved("unsupported_reference")
    target_name = raw.path[1]
    if not _exported_name(target_name):
        return _unresolved("target_inaccessible")
    key = (import_record.target_id, target_name)
    if key in index.ambiguous:
        return _unresolved("ambiguous_target")
    targets = index.surfaces.get(key, ())
    if len(targets) > 1:
        return _unresolved("ambiguous_target")
    if not targets:
        return _unresolved("target_not_indexed")
    target = targets[0]
    return GoReferenceOutcome(
        target=target.symbol,
        reason=None,
        import_unresolved_reason=None,
        basis="qualified_member",
        support=target.support,
        resolution_control_files=(),
    )


def _package_metadata(package: Symbol) -> tuple[str, str]:
    loci = package.metadata.get("loci")
    if (
        package.language != "go"
        or package.kind != "package"
        or not isinstance(loci, Mapping)
        or loci.get("go_package_node") is not True
    ):
        raise _error("Go reference package endpoint is invalid", symbol_id=package.id)
    directory = loci.get("directory")
    package_name = loci.get("package_name")
    if not isinstance(directory, str) or not isinstance(package_name, str):
        raise _error("Go reference package metadata is invalid", symbol_id=package.id)
    return directory, package_name


def _parent_directory(file: str) -> str:
    return PurePosixPath(file).parent.as_posix()


def _exported_name(name: str) -> bool:
    # Go uses Unicode category Lu, not an ASCII-only uppercase check.
    # Source: https://go.dev/ref/spec#Exported_identifiers
    return bool(name) and unicodedata.category(name[0]) == "Lu"


def _unresolved(reason: ReferenceUnresolvedReason) -> GoReferenceOutcome:
    return GoReferenceOutcome(
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
