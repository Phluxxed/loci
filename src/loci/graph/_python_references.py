from __future__ import annotations

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
from .imports import ImportRecord
from .references import (
    MAX_REFERENCE_REEXPORT_PASSES,
    MAX_REFERENCE_SUPPORT_RECORDS,
    ReferenceResolutionBasis,
    ReferenceSupport,
    ReferenceUnresolvedReason,
)


_ExportKey = tuple[str, str]


@dataclass(frozen=True, slots=True)
class _PythonExportTarget:
    symbol: Symbol
    support: tuple[ReferenceSupport, ...]
    control_files: tuple[str, ...]
    via_reexport: bool


@dataclass(frozen=True, slots=True)
class _PythonReexportRule:
    source: _ExportKey
    target: _ExportKey
    support: ReferenceSupport
    control_files: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class PythonReferenceIndex:
    surfaces: Mapping[_ExportKey, tuple[_PythonExportTarget, ...]]
    ambiguous: frozenset[_ExportKey]
    cyclic: frozenset[_ExportKey]
    import_failures: Mapping[_ExportKey, frozenset[ImportUnresolvedReason]]


@dataclass(frozen=True, slots=True)
class PythonReferenceOutcome:
    target: Symbol | None
    reason: ReferenceUnresolvedReason | None
    import_unresolved_reason: ImportUnresolvedReason | None
    basis: ReferenceResolutionBasis | None
    support: tuple[ReferenceSupport, ...]
    resolution_control_files: tuple[str, ...]


def build_python_reference_index(
    symbols: Sequence[Symbol],
    imports: Sequence[ImportRecord],
    exports: Sequence[RawLocalExport],
    *,
    file_nodes: Mapping[str, Symbol],
) -> PythonReferenceIndex:
    """Compile Python definitions and named re-exports to a bounded fixed point."""
    definitions: dict[tuple[str, int, int], list[Symbol]] = {}
    for symbol in symbols:
        if (
            symbol.language == "python"
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

    reexport_imports = _index_reexport_imports(imports)
    surfaces: dict[_ExportKey, dict[str, _PythonExportTarget]] = {}
    ambiguous: set[_ExportKey] = set()
    failures: dict[_ExportKey, set[ImportUnresolvedReason]] = {}
    rules: list[_PythonReexportRule] = []
    for export in exports:
        if not isinstance(export, RawLocalExport):
            raise _error("Python reference export is not a RawLocalExport")
        if export.language != "python":
            continue
        file_node = file_nodes.get(export.source_file)
        if (
            file_node is None
            or file_node.language != "python"
            or file_node.content_hash != export.source_hash
        ):
            raise _error(
                "Python export source evidence is stale",
                file=export.source_file,
            )
        key = (export.source_file, export.exported_name)
        if export.definition_start_byte is not None:
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
            _add_export_target(
                surfaces,
                key,
                _PythonExportTarget(
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
                ),
                ambiguous=ambiguous,
            )
            continue

        matches = reexport_imports.get(_reexport_evidence_key(export), ())
        if len(matches) != 1:
            if len(matches) > 1:
                ambiguous.add(key)
            continue
        record, binding = matches[0]
        if record.status == "unresolved":
            if record.unresolved_reason is not None:
                failures.setdefault(key, set()).add(record.unresolved_reason)
            continue
        if (
            record.target_file is None
            or record.target_id is None
            or binding.imported_name is None
        ):
            ambiguous.add(key)
            continue
        rules.append(
            _PythonReexportRule(
                source=key,
                target=(record.target_file, binding.imported_name),
                support=ReferenceSupport(
                    kind="reexport",
                    file=export.source_file,
                    line=export.line,
                    content_hash=export.source_hash,
                    endpoint_id=record.target_id,
                ),
                control_files=record.resolution_control_files,
            )
        )

    rules = sorted(
        set(rules),
        key=lambda rule: (
            rule.source,
            rule.target,
            rule.support.line,
            rule.support.endpoint_id,
        )
    )
    rules_by_source: dict[_ExportKey, list[_PythonReexportRule]] = {}
    for rule in rules:
        source_rules = rules_by_source.setdefault(rule.source, [])
        if len(source_rules) >= MAX_REFERENCE_RESOLUTION_CANDIDATES:
            ambiguous.add(rule.source)
            continue
        source_rules.append(rule)
    rules = [
        rule
        for source in sorted(rules_by_source)
        for rule in rules_by_source[source]
    ]
    for _ in range(MAX_REFERENCE_REEXPORT_PASSES):
        snapshot = {key: dict(value) for key, value in surfaces.items()}
        changed = False
        for rule in rules:
            for target in snapshot.get(rule.target, {}).values():
                support = (rule.support, *target.support)
                # The common resolver prepends the importing reference's support.
                if len(support) >= MAX_REFERENCE_SUPPORT_RECORDS:
                    ambiguous.add(rule.source)
                    continue
                changed |= _add_export_target(
                    surfaces,
                    rule.source,
                    _PythonExportTarget(
                        symbol=target.symbol,
                        support=support,
                        control_files=tuple(sorted(set(
                            (*rule.control_files, *target.control_files)
                        ))),
                        via_reexport=True,
                    ),
                    ambiguous=ambiguous,
                )
        if not changed:
            break
    else:
        ambiguous.update(rule.source for rule in rules)

    for key, targets in surfaces.items():
        if len(targets) > 1:
            ambiguous.add(key)
    graph: dict[_ExportKey, set[_ExportKey]] = {}
    for rule in rules:
        graph.setdefault(rule.source, set()).add(rule.target)
    cyclic = _cycle_reachable_keys(graph)
    return PythonReferenceIndex(
        surfaces=MappingProxyType({
            key: tuple(sorted(value.values(), key=lambda target: target.symbol.id))
            for key, value in surfaces.items()
        }),
        ambiguous=frozenset(ambiguous),
        cyclic=frozenset(cyclic),
        import_failures=MappingProxyType({
            key: frozenset(value) for key, value in failures.items()
        }),
    )


def resolve_python_reference(
    raw: RawSymbolReference,
    *,
    binding: ImportBinding,
    import_record: ImportRecord,
    index: PythonReferenceIndex,
) -> PythonReferenceOutcome:
    """Resolve one Python reference without searching outside its import endpoint."""
    target_name, basis = _python_target_name(raw, binding, import_record)
    if target_name is None or basis is None or import_record.target_file is None:
        return _unresolved("unsupported_reference")
    key = (import_record.target_file, target_name)
    if key in index.ambiguous:
        return _unresolved("ambiguous_target")
    targets = index.surfaces.get(key, ())
    if len(targets) > 1:
        return _unresolved("ambiguous_target")
    if not targets:
        failures = index.import_failures.get(key, frozenset())
        if len(failures) == 1:
            return _unresolved(
                "import_unresolved",
                import_reason=next(iter(failures)),
            )
        if len(failures) > 1 or key in index.cyclic:
            return _unresolved("ambiguous_target")
        return _unresolved("target_not_indexed")
    target = targets[0]
    return PythonReferenceOutcome(
        target=target.symbol,
        reason=None,
        import_unresolved_reason=None,
        basis="reexport_chain" if target.via_reexport else basis,
        support=target.support,
        resolution_control_files=target.control_files,
    )


def _python_target_name(
    raw: RawSymbolReference,
    binding: ImportBinding,
    import_record: ImportRecord,
) -> tuple[str | None, ReferenceResolutionBasis | None]:
    if binding.kind == "symbol" and binding.imported_name is not None:
        if _is_imported_submodule(raw, binding, import_record):
            if len(raw.path) < 2 or raw.path[0] != binding.local_name:
                return None, None
            return raw.path[1], "qualified_member"
        return binding.imported_name, "direct_binding"
    if binding.kind != "module" or binding.local_name is None:
        return None, None
    module_path = tuple(
        part for part in binding.import_specifier.split(".") if part
    )
    if not module_path:
        return None, None
    if binding.local_name != module_path[0]:
        if len(raw.path) < 2 or raw.path[0] != binding.local_name:
            return None, None
        return raw.path[1], "qualified_member"
    if (
        len(raw.path) <= len(module_path)
        or raw.path[:len(module_path)] != module_path
    ):
        return None, None
    return raw.path[len(module_path)], "qualified_member"


def _index_reexport_imports(
    imports: Sequence[ImportRecord],
) -> Mapping[
    tuple[str, str, int, str, str],
    tuple[tuple[ImportRecord, ImportBinding], ...],
]:
    indexed: dict[
        tuple[str, str, int, str, str],
        list[tuple[ImportRecord, ImportBinding]],
    ] = {}
    for record in imports:
        if record.raw.language != "python":
            continue
        for binding in record.raw.bindings:
            if (
                binding.module_level
                and binding.kind == "symbol"
                and binding.local_name is not None
            ):
                key = (
                    record.raw.source_file,
                    record.raw.source_hash,
                    binding.import_line,
                    binding.import_text,
                    binding.local_name,
                )
                matches = indexed.setdefault(key, [])
                if len(matches) <= MAX_REFERENCE_RESOLUTION_CANDIDATES:
                    matches.append((record, binding))
    return MappingProxyType({key: tuple(value) for key, value in indexed.items()})


def _reexport_evidence_key(
    export: RawLocalExport,
) -> tuple[str, str, int, str, str]:
    if export.local_name is None:
        raise _error("Python named re-export has no local name")
    return (
        export.source_file,
        export.source_hash,
        export.line,
        export.text,
        export.local_name,
    )


def _is_imported_submodule(
    raw: RawSymbolReference,
    binding: ImportBinding,
    import_record: ImportRecord,
) -> bool:
    if import_record.target_file is None or binding.imported_name is None:
        return False
    specifier = binding.import_specifier
    imported_name = binding.imported_name
    if specifier.startswith("."):
        dot_count = len(specifier) - len(specifier.lstrip("."))
        remainder = tuple(part for part in specifier[dot_count:].split(".") if part)
        base = PurePosixPath(raw.source_file).parent
        for _ in range(dot_count - 1):
            if base == PurePosixPath("."):
                return False
            base = base.parent
        module = base.joinpath(*remainder, imported_name)
        candidates = {f"{module.as_posix()}.py", (module / "__init__.py").as_posix()}
        return import_record.target_file in candidates

    module = PurePosixPath(*specifier.split("."), imported_name)
    candidates = (f"{module.as_posix()}.py", (module / "__init__.py").as_posix())
    return any(
        import_record.target_file == candidate
        or import_record.target_file.endswith(f"/{candidate}")
        for candidate in candidates
    )


def _add_export_target(
    surfaces: dict[_ExportKey, dict[str, _PythonExportTarget]],
    key: _ExportKey,
    target: _PythonExportTarget,
    *,
    ambiguous: set[_ExportKey],
) -> bool:
    targets = surfaces.setdefault(key, {})
    current = targets.get(target.symbol.id)
    if current is None and len(targets) >= MAX_REFERENCE_RESOLUTION_CANDIDATES:
        ambiguous.add(key)
        return False
    if current is None or _target_route_key(target) < _target_route_key(current):
        targets[target.symbol.id] = target
        return True
    return False


def _target_route_key(target: _PythonExportTarget) -> tuple[object, ...]:
    return (
        len(target.support),
        tuple(
            (
                support.kind,
                support.file,
                support.line,
                support.endpoint_id,
            )
            for support in target.support
        ),
        target.control_files,
    )


def _cycle_reachable_keys(
    graph: Mapping[_ExportKey, set[_ExportKey]],
) -> set[_ExportKey]:
    nodes = set(graph)
    nodes.update(target for targets in graph.values() for target in targets)
    reverse: dict[_ExportKey, set[_ExportKey]] = {}
    for source, targets in graph.items():
        for target in targets:
            reverse.setdefault(target, set()).add(source)

    visited: set[_ExportKey] = set()
    finish_order: list[_ExportKey] = []
    for root in sorted(nodes):
        if root in visited:
            continue
        stack: list[tuple[_ExportKey, bool]] = [(root, False)]
        while stack:
            node, expanded = stack.pop()
            if expanded:
                finish_order.append(node)
                continue
            if node in visited:
                continue
            visited.add(node)
            stack.append((node, True))
            stack.extend(
                (target, False)
                for target in reversed(sorted(graph.get(node, ())))
                if target not in visited
            )

    assigned: set[_ExportKey] = set()
    cycle_members: set[_ExportKey] = set()
    for root in reversed(finish_order):
        if root in assigned:
            continue
        component: set[_ExportKey] = set()
        component_stack = [root]
        while component_stack:
            node = component_stack.pop()
            if node in assigned:
                continue
            assigned.add(node)
            component.add(node)
            component_stack.extend(
                source
                for source in reverse.get(node, ())
                if source not in assigned
            )
        if len(component) > 1 or any(
            node in graph.get(node, ()) for node in component
        ):
            cycle_members.update(component)

    reachable = set(cycle_members)
    frontier = list(cycle_members)
    while frontier:
        target = frontier.pop()
        for source in reverse.get(target, ()):
            if source not in reachable:
                reachable.add(source)
                frontier.append(source)
    return reachable


def _unresolved(
    reason: ReferenceUnresolvedReason,
    *,
    import_reason: ImportUnresolvedReason | None = None,
) -> PythonReferenceOutcome:
    return PythonReferenceOutcome(
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
