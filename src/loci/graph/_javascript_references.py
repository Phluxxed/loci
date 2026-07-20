from __future__ import annotations

import re
from dataclasses import dataclass
from types import MappingProxyType
from typing import Hashable, Mapping, Sequence, TypeAlias, TypeVar, cast

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


_ExportKey: TypeAlias = tuple[str, str]
_Node = TypeVar("_Node", bound=Hashable)
_JAVASCRIPT_LANGUAGES = frozenset({"javascript", "typescript"})
_LOCAL_EXPORT_RE = re.compile(r"^\s*export\s+(?:type\s+)?\{")


@dataclass(frozen=True, slots=True)
class _JavaScriptExportTarget:
    symbol: Symbol
    support: tuple[ReferenceSupport, ...]
    control_files: tuple[str, ...]
    via_reexport: bool


@dataclass(frozen=True, slots=True)
class _JavaScriptReexportRule:
    source: _ExportKey
    target: _ExportKey
    support: ReferenceSupport
    control_files: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class _JavaScriptStarRule:
    source_file: str
    target_file: str
    support: ReferenceSupport
    control_files: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class JavaScriptReferenceIndex:
    surfaces: Mapping[_ExportKey, tuple[_JavaScriptExportTarget, ...]]
    ambiguous: frozenset[_ExportKey]
    cyclic_keys: frozenset[_ExportKey]
    cyclic_files: frozenset[str]
    ambiguous_files: frozenset[str]
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
    explicit_counts: dict[_ExportKey, int] = {}
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
        explicit_counts[key] = explicit_counts.get(key, 0) + 1
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
        _add_export_target(
            surfaces,
            key,
            _JavaScriptExportTarget(
                symbol=target,
                support=_definition_support(export, target),
                control_files=(),
                via_reexport=False,
            ),
            ambiguous=ambiguous,
        )

    rules: list[_JavaScriptReexportRule] = []
    star_rules: list[_JavaScriptStarRule] = []
    failures: dict[_ExportKey, set[ImportUnresolvedReason]] = {}
    star_failures: dict[str, set[ImportUnresolvedReason]] = {}
    for record in imports:
        if record.raw.language not in _JAVASCRIPT_LANGUAGES or not record.raw.is_reexport:
            continue
        for binding in record.raw.bindings:
            if binding.kind == "glob":
                if record.status == "unresolved":
                    if record.unresolved_reason is not None:
                        star_failures.setdefault(record.raw.source_file, set()).add(
                            record.unresolved_reason
                        )
                elif record.target_file is None or record.target_id is None:
                    star_failures.setdefault(record.raw.source_file, set()).add(
                        "ambiguous"
                    )
                else:
                    star_rules.append(
                        _JavaScriptStarRule(
                            source_file=record.raw.source_file,
                            target_file=record.target_file,
                            support=ReferenceSupport(
                                kind="reexport",
                                file=record.raw.source_file,
                                line=record.raw.line,
                                content_hash=record.raw.source_hash,
                                endpoint_id=record.target_id,
                            ),
                            control_files=record.resolution_control_files,
                        )
                    )
                continue
            if binding.kind != "symbol" or binding.exported_name is None:
                if binding.exported_name is not None:
                    key = (record.raw.source_file, binding.exported_name)
                    explicit_counts[key] = explicit_counts.get(key, 0) + 1
                    ambiguous.add(key)
                continue
            key = (record.raw.source_file, binding.exported_name)
            explicit_counts[key] = explicit_counts.get(key, 0) + 1
            if record.status == "unresolved":
                if record.unresolved_reason is not None:
                    failures.setdefault(key, set()).add(record.unresolved_reason)
                continue
            if (
                binding.imported_name is None
                or record.target_file is None
                or record.target_id is None
            ):
                ambiguous.add(key)
                continue
            rules.append(
                _JavaScriptReexportRule(
                    source=key,
                    target=(record.target_file, binding.imported_name),
                    support=ReferenceSupport(
                        kind="reexport",
                        file=record.raw.source_file,
                        line=record.raw.line,
                        content_hash=record.raw.source_hash,
                        endpoint_id=record.target_id,
                    ),
                    control_files=record.resolution_control_files,
                )
            )

    ambiguous.update(key for key, count in explicit_counts.items() if count > 1)
    rules = sorted(set(rules), key=_reexport_rule_key)
    rules_by_source: dict[_ExportKey, list[_JavaScriptReexportRule]] = {}
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
    ambiguous_files: set[str] = set()
    star_rules = sorted(set(star_rules), key=_star_rule_key)
    star_rules_by_source: dict[str, list[_JavaScriptStarRule]] = {}
    for rule in star_rules:
        source_rules = star_rules_by_source.setdefault(rule.source_file, [])
        if len(source_rules) >= MAX_REFERENCE_RESOLUTION_CANDIDATES:
            ambiguous_files.add(rule.source_file)
            continue
        source_rules.append(rule)
    star_rules = [
        rule
        for source in sorted(star_rules_by_source)
        for rule in star_rules_by_source[source]
    ]
    explicit_keys = frozenset(explicit_counts)
    for _ in range(MAX_REFERENCE_REEXPORT_PASSES):
        snapshot = {key: dict(value) for key, value in surfaces.items()}
        snapshot_ambiguous = frozenset(ambiguous)
        snapshot_failures = {
            key: frozenset(value) for key, value in failures.items()
        }
        snapshot_star_failures = {
            file: frozenset(value) for file, value in star_failures.items()
        }
        names_by_file: dict[str, set[str]] = {}
        for file, name in set(snapshot) | set(snapshot_ambiguous) | set(snapshot_failures):
            names_by_file.setdefault(file, set()).add(name)
        changed = False
        for rule in rules:
            if rule.target in snapshot_ambiguous:
                if rule.source not in ambiguous:
                    ambiguous.add(rule.source)
                    changed = True
                continue
            target_failures = snapshot_failures.get(rule.target, frozenset())
            if target_failures:
                source_failures = failures.setdefault(rule.source, set())
                previous_count = len(source_failures)
                source_failures.update(target_failures)
                changed |= len(source_failures) != previous_count
            for target in snapshot.get(rule.target, {}).values():
                support = (rule.support, *target.support)
                if len(support) >= MAX_REFERENCE_SUPPORT_RECORDS:
                    ambiguous.add(rule.source)
                    continue
                changed |= _add_export_target(
                    surfaces,
                    rule.source,
                    _JavaScriptExportTarget(
                        symbol=target.symbol,
                        support=support,
                        control_files=tuple(sorted(set(
                            (*rule.control_files, *target.control_files)
                        ))),
                        via_reexport=True,
                    ),
                    ambiguous=ambiguous,
                )
        for rule in star_rules:
            source_star_failures = star_failures.setdefault(rule.source_file, set())
            previous_count = len(source_star_failures)
            source_star_failures.update(
                snapshot_star_failures.get(rule.target_file, frozenset())
            )
            changed |= len(source_star_failures) != previous_count
            for exported_name in sorted(names_by_file.get(rule.target_file, ())):
                if exported_name == "default":
                    continue
                source_key = (rule.source_file, exported_name)
                target_key = (rule.target_file, exported_name)
                if source_key in explicit_keys:
                    continue
                if target_key in snapshot_ambiguous:
                    if source_key not in ambiguous:
                        ambiguous.add(source_key)
                        changed = True
                    continue
                target_failures = snapshot_failures.get(target_key, frozenset())
                if target_failures:
                    source_failures = failures.setdefault(source_key, set())
                    failure_count = len(source_failures)
                    source_failures.update(target_failures)
                    changed |= len(source_failures) != failure_count
                for target in snapshot.get(target_key, {}).values():
                    support = (rule.support, *target.support)
                    if len(support) >= MAX_REFERENCE_SUPPORT_RECORDS:
                        if source_key not in ambiguous:
                            ambiguous.add(source_key)
                            changed = True
                        continue
                    changed |= _add_export_target(
                        surfaces,
                        source_key,
                        _JavaScriptExportTarget(
                            symbol=target.symbol,
                            support=support,
                            control_files=tuple(sorted(set(
                                (*rule.control_files, *target.control_files)
                            ))),
                            via_reexport=True,
                        ),
                        ambiguous=ambiguous,
                    )
        for key, targets in surfaces.items():
            if len(targets) > 1 and key not in ambiguous:
                ambiguous.add(key)
                changed = True
        if not changed:
            break
    else:
        ambiguous.update(rule.source for rule in rules)
        ambiguous_files.update(rule.source_file for rule in star_rules)

    for key, targets in surfaces.items():
        if len(targets) > 1:
            ambiguous.add(key)
    graph: dict[_ExportKey, set[_ExportKey]] = {}
    for rule in rules:
        graph.setdefault(rule.source, set()).add(rule.target)
    cyclic_keys = _cycle_reachable_nodes(graph)
    star_graph: dict[str, set[str]] = {}
    for rule in star_rules:
        star_graph.setdefault(rule.source_file, set()).add(rule.target_file)
    cyclic_files = _cycle_reachable_nodes(star_graph)
    return JavaScriptReferenceIndex(
        surfaces=MappingProxyType({
            key: tuple(value.values()) for key, value in surfaces.items()
        }),
        ambiguous=frozenset(ambiguous),
        cyclic_keys=frozenset(cyclic_keys),
        cyclic_files=frozenset(cyclic_files),
        ambiguous_files=frozenset(ambiguous_files),
        import_failures=MappingProxyType({
            key: frozenset(value) for key, value in failures.items()
        }),
        star_import_failures=MappingProxyType({
            file: frozenset(value) for file, value in star_failures.items()
        }),
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
    if key in index.ambiguous or import_record.target_file in index.ambiguous_files:
        return _unresolved("ambiguous_target")
    targets = index.surfaces.get(key, ())
    if len(targets) > 1:
        return _unresolved("ambiguous_target")
    if not targets:
        failures = index.import_failures.get(key, frozenset())
        star_failures = index.star_import_failures.get(
            import_record.target_file,
            frozenset(),
        )
        combined_failures = failures | star_failures
        if len(combined_failures) == 1:
            return _unresolved(
                "import_unresolved",
                import_reason=next(iter(combined_failures)),
            )
        if (
            len(combined_failures) > 1
            or key in index.cyclic_keys
            or import_record.target_file in index.cyclic_files
        ):
            return _unresolved("ambiguous_target")
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


def _definition_support(
    export: RawLocalExport,
    target: Symbol,
) -> tuple[ReferenceSupport, ...]:
    definition = ReferenceSupport(
        kind="definition",
        file=export.source_file,
        line=target.line,
        content_hash=export.source_hash,
        endpoint_id=target.id,
    )
    if not _LOCAL_EXPORT_RE.match(export.text):
        return (definition,)
    return (
        ReferenceSupport(
            kind="local_export",
            file=export.source_file,
            line=export.line,
            content_hash=export.source_hash,
            endpoint_id=target.id,
        ),
        definition,
    )


def _add_export_target(
    surfaces: dict[_ExportKey, dict[str, _JavaScriptExportTarget]],
    key: _ExportKey,
    target: _JavaScriptExportTarget,
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


def _target_route_key(target: _JavaScriptExportTarget) -> tuple[object, ...]:
    return (
        len(target.support),
        tuple(
            (support.kind, support.file, support.line, support.endpoint_id)
            for support in target.support
        ),
        target.control_files,
    )


def _reexport_rule_key(rule: _JavaScriptReexportRule) -> tuple[object, ...]:
    return (
        rule.source,
        rule.target,
        rule.support.line,
        rule.support.endpoint_id,
        rule.control_files,
    )


def _star_rule_key(rule: _JavaScriptStarRule) -> tuple[object, ...]:
    return (
        rule.source_file,
        rule.target_file,
        rule.support.line,
        rule.support.endpoint_id,
        rule.control_files,
    )


def _cycle_reachable_nodes(
    graph: Mapping[_Node, set[_Node]],
) -> set[_Node]:
    nodes = set(graph)
    nodes.update(target for targets in graph.values() for target in targets)
    reverse: dict[_Node, set[_Node]] = {}
    for source, targets in graph.items():
        for target in targets:
            reverse.setdefault(target, set()).add(source)

    visited: set[_Node] = set()
    finish_order: list[_Node] = []
    for root in sorted(nodes, key=repr):
        if root in visited:
            continue
        stack: list[tuple[_Node, bool]] = [(root, False)]
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
                for target in reversed(sorted(graph.get(node, ()), key=repr))
                if target not in visited
            )

    assigned: set[_Node] = set()
    cycle_members: set[_Node] = set()
    for root in reversed(finish_order):
        if root in assigned:
            continue
        component: set[_Node] = set()
        component_stack = [root]
        while component_stack:
            node = component_stack.pop()
            if node in assigned:
                continue
            assigned.add(node)
            component.add(node)
            component_stack.extend(
                source for source in reverse.get(node, ()) if source not in assigned
            )
        if len(component) > 1 or any(node in graph.get(node, ()) for node in component):
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
