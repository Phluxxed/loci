from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from types import MappingProxyType
from typing import cast

from loci.parser.imports import ImportUnresolvedReason
from loci.parser.reference_models import (
    MAX_REFERENCE_RESOLUTION_CANDIDATES,
    ImportBinding,
    RawLocalExport,
    RawSymbolReference,
)
from loci.parser.symbols import Symbol

from . import rust_crates as rust
from ._rust_aliases import _route_is_visible
from ._rust_resolution import build_rust_import_resolver_index
from ._rust_semantics import widest_configuration
from .contracts import GraphContractError, JSONValue
from .imports import ImportRecord
from .references import (
    MAX_REFERENCE_REEXPORT_PASSES,
    MAX_REFERENCE_SUPPORT_RECORDS,
    ReferenceResolutionBasis,
    ReferenceSupport,
    ReferenceUnresolvedReason,
)


_RustItemKey = tuple[str, tuple[str, ...], str]
_TYPE_LIKE_KINDS = frozenset({"struct", "enum", "trait", "type"})
_RUST_ITEM_FIELDS = {
    "lexical_module_path",
    "visibility",
    "visibility_scope",
    "configuration",
}
_RUST_CONFIGURATIONS = frozenset({"unconditional", "declared_possible"})
_RUST_VISIBILITIES = frozenset({
    "private",
    "pub",
    "pub(crate)",
    "pub(self)",
    "pub(super)",
})


@dataclass(frozen=True, slots=True)
class _RustItemMetadata:
    lexical_module_path: tuple[str, ...]
    visibility: str
    visibility_scope: tuple[str, ...] | None
    configuration: rust.RustResolutionConfiguration


@dataclass(frozen=True, slots=True)
class _RustItemTarget:
    symbol: Symbol
    crate_id: str
    module_path: tuple[str, ...]
    visibility: str
    visibility_scope: tuple[str, ...] | None
    configuration: rust.RustResolutionConfiguration
    support: tuple[ReferenceSupport, ...]
    control_files: tuple[str, ...] = ()
    via_reexport: bool = False


@dataclass(frozen=True, slots=True)
class _Importer:
    crate_id: str
    module_path: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class _RustReexportRule:
    source: _RustItemKey
    importer: _Importer
    record: ImportRecord
    binding: ImportBinding
    visibility: str
    visibility_scope: tuple[str, ...] | None


@dataclass(frozen=True, slots=True)
class RustReferenceIndex:
    crates: rust.RustCrateIndex
    base_modules_by_source: Mapping[
        tuple[str, str], tuple[rust.RustModuleBinding, ...]
    ]
    canonical_modules_by_source: Mapping[
        str, tuple[rust.RustModuleBinding, ...]
    ]
    surfaces: Mapping[_RustItemKey, tuple[_RustItemTarget, ...]]
    ambiguous: frozenset[_RustItemKey]


@dataclass(frozen=True, slots=True)
class RustReferenceOutcome:
    target: Symbol | None
    reason: ReferenceUnresolvedReason | None
    import_unresolved_reason: ImportUnresolvedReason | None
    basis: ReferenceResolutionBasis | None
    support: tuple[ReferenceSupport, ...]
    resolution_control_files: tuple[str, ...]
    resolution_configuration: rust.RustResolutionConfiguration | None


def build_rust_reference_index(
    symbols: Sequence[Symbol],
    exports: Sequence[RawLocalExport],
    imports: Sequence[ImportRecord],
    *,
    file_nodes: Mapping[str, Symbol],
    rust_crates: rust.RustCrateIndex | None,
) -> RustReferenceIndex:
    """Compile exact Rust item surfaces under Stage 9 crate/module routes."""
    crate_index = rust_crates or _empty_crate_index()
    resolver_index = build_rust_import_resolver_index(crate_index)
    definitions: dict[tuple[str, int, int], list[Symbol]] = defaultdict(list)
    for symbol in symbols:
        if symbol.language != "rust" or symbol.kind in {"file", "crate"}:
            continue
        candidates = definitions[
            (
                symbol.file_path,
                symbol.byte_offset,
                symbol.byte_offset + symbol.byte_length,
            )
        ]
        if len(candidates) <= MAX_REFERENCE_RESOLUTION_CANDIDATES:
            candidates.append(symbol)

    surfaces: dict[_RustItemKey, dict[str, _RustItemTarget]] = {}
    ambiguous: set[_RustItemKey] = set()
    for export in exports:
        if not isinstance(export, RawLocalExport):
            raise _error("Rust reference export is not a RawLocalExport")
        if export.language != "rust":
            continue
        file_node = file_nodes.get(export.source_file)
        if (
            file_node is None
            or file_node.language != "rust"
            or file_node.content_hash != export.source_hash
        ):
            raise _error(
                "Rust export source evidence is stale",
                file=export.source_file,
            )
        if export.definition_start_byte is None:
            continue
        candidates = definitions.get(
            (
                export.source_file,
                export.definition_start_byte,
                cast(int, export.definition_end_byte),
            ),
            (),
        )
        if len(candidates) != 1 or export.local_name != candidates[0].name:
            continue
        symbol = candidates[0]
        metadata = _rust_item_metadata(symbol)
        if metadata is None:
            continue
        for crate_id, base in _definition_bases(
            symbol.file_path,
            crate_index,
            resolver_index.base_modules_by_source,
        ):
            module_path = (*base.module_path, *metadata.lexical_module_path)
            visibility_scope = _visibility_scope(metadata.visibility, module_path)
            if visibility_scope is _INVALID_SCOPE:
                continue
            key = (crate_id, module_path, export.exported_name)
            target = _RustItemTarget(
                symbol=symbol,
                crate_id=crate_id,
                module_path=module_path,
                visibility=metadata.visibility,
                visibility_scope=cast(
                    tuple[str, ...] | None,
                    visibility_scope,
                ),
                configuration=widest_configuration(
                    base.configuration,
                    metadata.configuration,
                ),
                support=(
                    ReferenceSupport(
                        kind="definition",
                        file=export.source_file,
                        line=symbol.line,
                        content_hash=export.source_hash,
                        endpoint_id=symbol.id,
                    ),
                ),
            )
            _add_target(surfaces, key, target, ambiguous=ambiguous)

    skeleton = RustReferenceIndex(
        crates=crate_index,
        base_modules_by_source=resolver_index.base_modules_by_source,
        canonical_modules_by_source=_canonical_modules_by_source(crate_index),
        surfaces=MappingProxyType({}),
        ambiguous=frozenset(),
    )
    rules_by_source: dict[_RustItemKey, list[_RustReexportRule]] = defaultdict(list)
    for rule in _reexport_rules(imports, skeleton):
        source_rules = rules_by_source[rule.source]
        if len(source_rules) >= MAX_REFERENCE_RESOLUTION_CANDIDATES:
            ambiguous.add(rule.source)
            continue
        source_rules.append(rule)
    rules = tuple(
        rule
        for source in sorted(rules_by_source)
        for rule in rules_by_source[source]
    )
    for _ in range(MAX_REFERENCE_REEXPORT_PASSES):
        snapshot = _with_surfaces(skeleton, surfaces, ambiguous)
        changed = False
        for rule in rules:
            targets, _ = _lookup_item(
                _endpoint_modules(rule.record, snapshot, terminal=True),
                cast(str, rule.binding.imported_name),
                importer=rule.importer,
                index=snapshot,
            )
            for target in targets:
                support = (
                    ReferenceSupport(
                        kind="reexport",
                        file=rule.record.raw.source_file,
                        line=rule.record.raw.line,
                        content_hash=rule.record.raw.source_hash,
                        endpoint_id=cast(str, rule.record.target_id),
                    ),
                    *target.support,
                )
                if len(support) >= MAX_REFERENCE_SUPPORT_RECORDS:
                    ambiguous.add(rule.source)
                    continue
                changed |= _add_target(
                    surfaces,
                    rule.source,
                    _RustItemTarget(
                        symbol=target.symbol,
                        crate_id=rule.source[0],
                        module_path=rule.source[1],
                        visibility=rule.visibility,
                        visibility_scope=rule.visibility_scope,
                        configuration=widest_configuration(
                            cast(
                                rust.RustResolutionConfiguration,
                                rule.record.resolution_configuration,
                            ),
                            target.configuration,
                        ),
                        support=support,
                        control_files=tuple(sorted(set((
                            *rule.record.resolution_control_files,
                            *target.control_files,
                        )))),
                        via_reexport=True,
                    ),
                    ambiguous=ambiguous,
                )
        if not changed:
            break
    else:
        ambiguous.update(rule.source for rule in rules)

    return _with_surfaces(skeleton, surfaces, ambiguous)


def resolve_rust_reference(
    raw: RawSymbolReference,
    *,
    binding: ImportBinding,
    import_record: ImportRecord,
    index: RustReferenceIndex,
) -> RustReferenceOutcome:
    """Resolve one Rust item only through its proven Stage 9 import endpoint."""
    if import_record.resolution_configuration is None:
        return _unresolved("unsupported_reference")
    importers = _importers(import_record, index)
    if not importers:
        return _unresolved("unsupported_reference")

    targets: list[_RustItemTarget] = []
    failures: list[ReferenceUnresolvedReason] = []
    for importer in importers:
        candidates, reason = _resolve_for_importer(
            raw,
            binding=binding,
            import_record=import_record,
            importer=importer,
            index=index,
        )
        targets.extend(candidates)
        if reason is not None:
            failures.append(reason)
    merged, reason = _merge_targets(targets, failures)
    if merged is None:
        return _unresolved(reason or "target_not_indexed")
    configuration = widest_configuration(
        import_record.resolution_configuration,
        merged.configuration,
    )
    basis: ReferenceResolutionBasis = (
        "reexport_chain"
        if merged.via_reexport
        else "qualified_member"
        if len(raw.path) > 1 and merged.symbol.name == raw.path[-1]
        else "direct_binding"
    )
    return RustReferenceOutcome(
        target=merged.symbol,
        reason=None,
        import_unresolved_reason=None,
        basis=basis,
        support=merged.support,
        resolution_control_files=tuple(sorted(set(
            (*import_record.resolution_control_files, *merged.control_files)
        ))),
        resolution_configuration=configuration,
    )


def _resolve_for_importer(
    raw: RawSymbolReference,
    *,
    binding: ImportBinding,
    import_record: ImportRecord,
    importer: _Importer,
    index: RustReferenceIndex,
) -> tuple[list[_RustItemTarget], ReferenceUnresolvedReason | None]:
    endpoints = _endpoint_modules(import_record, index, terminal=True)
    targets: list[_RustItemTarget] = []
    failures: list[ReferenceUnresolvedReason] = []

    if binding.imported_name is not None:
        direct, reason = _lookup_item(
            endpoints,
            binding.imported_name,
            importer=importer,
            index=index,
        )
        if len(raw.path) == 1:
            return direct, reason
        targets.extend(
            target for target in direct if target.symbol.kind in _TYPE_LIKE_KINDS
        )
        if reason is not None and reason != "target_not_indexed":
            failures.append(reason)

    if len(raw.path) >= 2:
        modules = _endpoint_modules(import_record, index, terminal=False)
        modules = _walk_modules(
            modules,
            raw.path[1:-1],
            importer=importer,
            index=index,
        )
        qualified, reason = _lookup_item(
            modules,
            raw.path[-1],
            importer=importer,
            index=index,
        )
        targets.extend(qualified)
        if reason is not None:
            failures.append(reason)

    if targets:
        return targets, None
    if "target_inaccessible" in failures:
        return [], "target_inaccessible"
    if "ambiguous_target" in failures:
        return [], "ambiguous_target"
    return [], failures[0] if failures else "target_not_indexed"


def _lookup_item(
    modules: Sequence[rust.RustModuleBinding],
    name: str,
    *,
    importer: _Importer,
    index: RustReferenceIndex,
) -> tuple[list[_RustItemTarget], ReferenceUnresolvedReason | None]:
    found = False
    visible: list[_RustItemTarget] = []
    for module in modules:
        key = (module.crate_id, module.module_path, name)
        if key in index.ambiguous:
            return [], "ambiguous_target"
        candidates = index.surfaces.get(key, ())
        found = found or bool(candidates)
        visible.extend(
            target
            for target in candidates
            if _item_visible(target, importer=importer)
        )
    if visible:
        return visible, None
    return [], "target_inaccessible" if found else "target_not_indexed"


def _endpoint_modules(
    record: ImportRecord,
    index: RustReferenceIndex,
    *,
    terminal: bool,
) -> tuple[rust.RustModuleBinding, ...]:
    if record.target_kind == "crate" and record.target_id is not None:
        bindings = index.crates.modules_by_crate_path.get((record.target_id, ()), ())
    elif record.target_kind == "file" and record.target_file is not None:
        bindings = index.canonical_modules_by_source.get(record.target_file, ())
    else:
        return ()
    canonical = tuple(sorted(set(bindings), key=_module_key))
    return _rank_endpoint_modules(canonical, record.raw.specifier, terminal=terminal)


def _rank_endpoint_modules(
    modules: tuple[rust.RustModuleBinding, ...],
    specifier: str,
    *,
    terminal: bool,
) -> tuple[rust.RustModuleBinding, ...]:
    hints = _route_hints(specifier, terminal=terminal)
    if not modules or not hints:
        return modules
    scored = [
        (
            max(
                (
                    len(hint)
                    for hint in hints
                    if not hint or module.module_path[-len(hint):] == hint
                ),
                default=-1,
            ),
            module,
        )
        for module in modules
    ]
    best = max(score for score, _ in scored)
    if best < 0:
        return modules
    return tuple(module for score, module in scored if score == best)


def _route_hints(specifier: str, *, terminal: bool) -> tuple[tuple[str, ...], ...]:
    parts = tuple(part for part in specifier.removeprefix("::").split("::") if part)
    if terminal and parts:
        parts = parts[:-1]
    while parts and parts[0] in {"crate", "self", "super"}:
        parts = parts[1:]
    hints = {parts}
    if parts:
        hints.add(parts[1:])
    return tuple(sorted(hints, key=lambda value: (-len(value), value)))


def _walk_modules(
    starts: Sequence[rust.RustModuleBinding],
    parts: Sequence[str],
    *,
    importer: _Importer,
    index: RustReferenceIndex,
) -> tuple[rust.RustModuleBinding, ...]:
    current = tuple(starts)
    for part in parts:
        following: list[rust.RustModuleBinding] = []
        for module in current:
            route = (*module.module_path, part)
            if not _route_is_visible(
                index.crates.modules_by_crate_path,
                owner_crate_id=module.crate_id,
                route_path=route,
                importer_crate_id=importer.crate_id,
                importer_path=importer.module_path,
            ):
                continue
            following.extend(
                index.crates.modules_by_crate_path.get((module.crate_id, route), ())
            )
        current = tuple(sorted(set(following), key=_module_key))
        if not current:
            break
    return current


def _importers(
    record: ImportRecord,
    index: RustReferenceIndex,
) -> tuple[_Importer, ...]:
    context = record.raw.rust
    if context is None:
        return ()
    importers: set[_Importer] = set()
    for crate_id in index.crates.crate_ids_by_source_file.get(
        record.raw.source_file,
        (),
    ):
        for base in index.base_modules_by_source.get(
            (crate_id, record.raw.source_file),
            (),
        ):
            module_path = (*base.module_path, *context.lexical_module_path)
            if _canonical_module(
                index.crates,
                crate_id=crate_id,
                module_path=module_path,
                source_file=record.raw.source_file,
            ):
                importers.add(_Importer(crate_id, module_path))
    return tuple(sorted(importers, key=lambda item: (item.crate_id, item.module_path)))


def _reexport_rules(
    imports: Sequence[ImportRecord],
    index: RustReferenceIndex,
) -> tuple[_RustReexportRule, ...]:
    rules: list[_RustReexportRule] = []
    for record in imports:
        context = record.raw.rust
        if (
            record.status != "resolved"
            or record.raw.language != "rust"
            or not record.raw.is_reexport
            or context is None
            or context.kind != "use"
            or not context.module_level
            or record.resolution_configuration is None
            or record.target_id is None
        ):
            continue
        for importer in _importers(record, index):
            scope = _visibility_scope(context.visibility, importer.module_path)
            if scope is _INVALID_SCOPE:
                continue
            for binding in record.raw.bindings:
                if (
                    binding.kind != "symbol"
                    or not binding.module_level
                    or binding.imported_name is None
                    or binding.exported_name is None
                ):
                    continue
                rules.append(_RustReexportRule(
                    source=(
                        importer.crate_id,
                        importer.module_path,
                        binding.exported_name,
                    ),
                    importer=importer,
                    record=record,
                    binding=binding,
                    visibility=context.visibility,
                    visibility_scope=cast(tuple[str, ...] | None, scope),
                ))
    return tuple(sorted(rules, key=_reexport_rule_key))


_INVALID_SCOPE = object()


def _visibility_scope(
    visibility: str,
    declaring_path: tuple[str, ...],
) -> tuple[str, ...] | None | object:
    if visibility == "pub":
        return None
    if visibility == "pub(crate)":
        return ()
    if visibility in {"private", "pub(self)"}:
        return declaring_path
    if visibility == "pub(super)":
        return declaring_path[:-1] if declaring_path else _INVALID_SCOPE
    if not visibility.startswith("pub(in ") or not visibility.endswith(")"):
        return _INVALID_SCOPE
    raw_scope = visibility[len("pub(in "):-1]
    parts = tuple(part for part in raw_scope.split("::") if part)
    if not parts:
        return _INVALID_SCOPE
    if parts[0] == "crate":
        scope = parts[1:]
    elif parts[0] == "self":
        scope = (*declaring_path, *parts[1:])
    elif parts[0] == "super":
        scope_parts = list(declaring_path)
        offset = 0
        while offset < len(parts) and parts[offset] == "super":
            if not scope_parts:
                return _INVALID_SCOPE
            scope_parts.pop()
            offset += 1
        scope = (*scope_parts, *parts[offset:])
    else:
        return _INVALID_SCOPE
    if declaring_path[:len(scope)] != scope:
        return _INVALID_SCOPE
    return scope


def _definition_bases(
    source_file: str,
    index: rust.RustCrateIndex,
    base_modules: Mapping[
        tuple[str, str], tuple[rust.RustModuleBinding, ...]
    ],
) -> tuple[tuple[str, rust.RustModuleBinding], ...]:
    return tuple(
        (crate_id, base)
        for crate_id in index.crate_ids_by_source_file.get(source_file, ())
        for base in base_modules.get((crate_id, source_file), ())
    )


def _canonical_modules_by_source(
    index: rust.RustCrateIndex,
) -> Mapping[str, tuple[rust.RustModuleBinding, ...]]:
    by_source: dict[str, set[rust.RustModuleBinding]] = defaultdict(set)
    for (owner, route), bindings in index.modules_by_crate_path.items():
        for binding in bindings:
            if binding.crate_id == owner and binding.module_path == route:
                by_source[binding.source_file].add(binding)
    return MappingProxyType({
        source: tuple(sorted(bindings, key=_module_key))
        for source, bindings in sorted(by_source.items())
    })


def _canonical_module(
    index: rust.RustCrateIndex,
    *,
    crate_id: str,
    module_path: tuple[str, ...],
    source_file: str,
) -> bool:
    return any(
        binding.crate_id == crate_id
        and binding.module_path == module_path
        and binding.source_file == source_file
        for binding in index.modules_by_crate_path.get((crate_id, module_path), ())
    )


def _item_visible(target: _RustItemTarget, *, importer: _Importer) -> bool:
    if target.visibility_scope is None:
        return target.visibility == "pub"
    if target.crate_id != importer.crate_id:
        return False
    scope = target.visibility_scope
    return importer.module_path[:len(scope)] == scope


def _rust_item_metadata(symbol: Symbol) -> _RustItemMetadata | None:
    loci = symbol.metadata.get("loci")
    if not isinstance(loci, Mapping) or "rust_item" not in loci:
        return None
    value = loci["rust_item"]
    if not isinstance(value, Mapping) or set(value) != _RUST_ITEM_FIELDS:
        raise _error("Rust item metadata has invalid fields", symbol_id=symbol.id)
    lexical = _string_path(value["lexical_module_path"], "lexical_module_path")
    visibility = value["visibility"]
    if not isinstance(visibility, str) or not (
        visibility in _RUST_VISIBILITIES
        or visibility.startswith("pub(in ") and visibility.endswith(")")
    ):
        raise _error("Rust item visibility is invalid", symbol_id=symbol.id)
    raw_scope = value["visibility_scope"]
    scope = None if raw_scope is None else _string_path(raw_scope, "visibility_scope")
    configuration = value["configuration"]
    if not isinstance(configuration, str) or configuration not in _RUST_CONFIGURATIONS:
        raise _error("Rust item configuration is invalid", symbol_id=symbol.id)
    if not _metadata_scope_valid(visibility, lexical, scope):
        raise _error("Rust item visibility scope is inconsistent", symbol_id=symbol.id)
    return _RustItemMetadata(
        lexical_module_path=lexical,
        visibility=visibility,
        visibility_scope=scope,
        configuration=cast(rust.RustResolutionConfiguration, configuration),
    )


def _metadata_scope_valid(
    visibility: str,
    lexical: tuple[str, ...],
    scope: tuple[str, ...] | None,
) -> bool:
    if visibility == "pub":
        return scope is None
    if scope is None:
        return False
    if visibility == "pub(crate)":
        return scope == ()
    if visibility in {"private", "pub(self)"}:
        return scope == lexical
    if visibility == "pub(super)":
        return scope == lexical[:-1]
    raw_scope = visibility[len("pub(in "):-1]
    parts = tuple(part for part in raw_scope.split("::") if part)
    if not parts:
        return False
    if parts[0] == "crate":
        expected = parts[1:]
    elif parts[0] == "self":
        expected = (*lexical, *parts[1:])
    elif parts[0] == "super":
        expected_parts = list(lexical)
        offset = 0
        while offset < len(parts) and parts[offset] == "super":
            if not expected_parts:
                return scope == ()
            expected_parts.pop()
            offset += 1
        expected = (*expected_parts, *parts[offset:])
    else:
        return False
    return scope == expected


def _string_path(value: object, field: str) -> tuple[str, ...]:
    if not isinstance(value, list) or any(
        not isinstance(item, str) or not item for item in value
    ):
        raise _error("Rust item path is invalid", field=field)
    if len(value) > rust.MAX_RUST_MODULE_DEPTH:
        raise _error("Rust item path exceeds the module-depth limit", field=field)
    return tuple(value)


def _add_target(
    surfaces: dict[_RustItemKey, dict[str, _RustItemTarget]],
    key: _RustItemKey,
    target: _RustItemTarget,
    *,
    ambiguous: set[_RustItemKey],
) -> bool:
    values = surfaces.setdefault(key, {})
    current = values.get(target.symbol.id)
    if current is None and len(values) >= MAX_REFERENCE_RESOLUTION_CANDIDATES:
        ambiguous.add(key)
        return False
    if current is None:
        values[target.symbol.id] = target
        return True
    merged = _merge_same_target(current, target)
    if merged == current:
        return False
    values[target.symbol.id] = merged
    return True


def _merge_same_target(
    left: _RustItemTarget,
    right: _RustItemTarget,
) -> _RustItemTarget:
    preferred = min((left, right), key=_target_key)
    return _RustItemTarget(
        symbol=preferred.symbol,
        crate_id=preferred.crate_id,
        module_path=preferred.module_path,
        visibility=preferred.visibility,
        visibility_scope=preferred.visibility_scope,
        configuration=widest_configuration(left.configuration, right.configuration),
        support=preferred.support,
        control_files=tuple(sorted(set((
            *left.control_files,
            *right.control_files,
        )))),
        via_reexport=preferred.via_reexport,
    )


def _merge_targets(
    targets: Sequence[_RustItemTarget],
    failures: Sequence[ReferenceUnresolvedReason],
) -> tuple[_RustItemTarget | None, ReferenceUnresolvedReason | None]:
    by_symbol: dict[str, list[_RustItemTarget]] = defaultdict(list)
    for target in targets:
        by_symbol[target.symbol.id].append(target)
    if not by_symbol:
        if "target_inaccessible" in failures:
            return None, "target_inaccessible"
        if "ambiguous_target" in failures:
            return None, "ambiguous_target"
        return None, failures[0] if failures else "target_not_indexed"
    if len(by_symbol) > 1:
        configurations = {
            target.configuration for values in by_symbol.values() for target in values
        }
        return (
            None,
            "configuration_divergent"
            if configurations == {"declared_possible"}
            else "ambiguous_target",
        )
    values = next(iter(by_symbol.values()))
    first = min(values, key=_target_key)
    configuration = first.configuration
    for value in values:
        configuration = widest_configuration(configuration, value.configuration)
    return (
        _RustItemTarget(
            symbol=first.symbol,
            crate_id=first.crate_id,
            module_path=first.module_path,
            visibility=first.visibility,
            visibility_scope=first.visibility_scope,
            configuration=configuration,
            support=first.support,
            control_files=tuple(sorted({
                control for value in values for control in value.control_files
            })),
            via_reexport=any(value.via_reexport for value in values),
        ),
        None,
    )


def _target_key(target: _RustItemTarget) -> tuple[object, ...]:
    return (
        len(target.support),
        tuple(
            (item.kind, item.file, item.line, item.endpoint_id)
            for item in target.support
        ),
        target.crate_id,
        target.module_path,
        target.symbol.id,
    )


def _reexport_rule_key(rule: _RustReexportRule) -> tuple[object, ...]:
    return (
        rule.source,
        rule.record.raw.source_file,
        rule.record.raw.line,
        rule.record.raw.specifier,
        rule.binding.imported_name,
        rule.binding.exported_name,
    )


def _module_key(binding: rust.RustModuleBinding) -> tuple[object, ...]:
    return (
        binding.crate_id,
        binding.module_path,
        binding.source_file,
        binding.visibility,
        binding.configuration,
    )


def _with_surfaces(
    skeleton: RustReferenceIndex,
    surfaces: Mapping[_RustItemKey, Mapping[str, _RustItemTarget]],
    ambiguous: set[_RustItemKey],
) -> RustReferenceIndex:
    return RustReferenceIndex(
        crates=skeleton.crates,
        base_modules_by_source=skeleton.base_modules_by_source,
        canonical_modules_by_source=skeleton.canonical_modules_by_source,
        surfaces=MappingProxyType({
            key: tuple(sorted(values.values(), key=_target_key))
            for key, values in sorted(surfaces.items())
        }),
        ambiguous=frozenset(ambiguous),
    )


def _empty_crate_index() -> rust.RustCrateIndex:
    empty = MappingProxyType({})
    return rust.RustCrateIndex(
        crate_nodes=(),
        crates_by_id=empty,
        crate_ids_by_source_file=empty,
        modules_by_crate_path=empty,
        dependencies_by_crate_alias=empty,
        module_failures_by_observation=empty,
    )


def _unresolved(reason: ReferenceUnresolvedReason) -> RustReferenceOutcome:
    return RustReferenceOutcome(
        target=None,
        reason=reason,
        import_unresolved_reason=None,
        basis=None,
        support=(),
        resolution_control_files=(),
        resolution_configuration=None,
    )


def _error(message: str, **details: object) -> GraphContractError:
    return GraphContractError(
        "GRAPH_REFERENCE_INDEX_INVALID",
        message,
        cast(dict[str, JSONValue], details),
    )
