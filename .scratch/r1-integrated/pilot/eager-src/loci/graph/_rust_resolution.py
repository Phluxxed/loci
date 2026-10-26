from __future__ import annotations

import re
from collections import Counter, defaultdict, deque
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import PurePosixPath
from types import MappingProxyType

from loci.parser.imports import ImportUnresolvedReason, RawImport, RustImportContext
from loci.parser.symbols import FILE_NODE_QUALIFIED_NAME, Symbol, make_symbol_id

from . import rust_crates as rust
from ._rust_aliases import (
    AliasLimitError,
    _route_is_visible,
    build_alias_routes,
    merge_dependency_bindings,
)
from ._rust_semantics import merge_observed_configuration, widest_configuration


_RUST_KEYWORDS = frozenset({
    "Self",
    "abstract",
    "as",
    "async",
    "await",
    "become",
    "box",
    "break",
    "const",
    "continue",
    "crate",
    "do",
    "dyn",
    "else",
    "enum",
    "extern",
    "false",
    "final",
    "fn",
    "for",
    "gen",
    "if",
    "impl",
    "in",
    "let",
    "loop",
    "macro",
    "match",
    "mod",
    "move",
    "mut",
    "override",
    "priv",
    "pub",
    "ref",
    "return",
    "self",
    "static",
    "struct",
    "super",
    "trait",
    "true",
    "try",
    "type",
    "typeof",
    "union",
    "unsafe",
    "unsized",
    "use",
    "virtual",
    "where",
    "while",
    "yield",
})


@dataclass(frozen=True, slots=True)
class _OwnedModuleFile:
    binding: rust.RustModuleBinding
    ancestry: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class _ImporterContext:
    crate_id: str
    declaring: rust.RustModuleBinding
    configuration: rust.RustResolutionConfiguration


@dataclass(frozen=True, slots=True)
class _RouteWalk:
    binding: rust.RustModuleBinding
    matched_segments: int
    configuration: rust.RustResolutionConfiguration
    unresolved_reason: ImportUnresolvedReason | None = None


@dataclass(frozen=True, slots=True)
class RustImportResolverIndex:
    base_modules_by_source: Mapping[
        tuple[str, str], tuple[rust.RustModuleBinding, ...]
    ]


def build_rust_crate_index(
    context: rust.CargoContext,
    *,
    file_nodes: Mapping[str, Symbol],
    observations: Sequence[RawImport],
) -> rust.RustCrateBuild:
    rust_observations = tuple(
        item
        for item in observations
        if item.language == "rust" and item.rust is not None
    )
    if len(rust_observations) > rust.MAX_RUST_OBSERVATIONS:
        return _rejected_build(
            "observation_limit_exceeded",
            rust.MAX_RUST_OBSERVATIONS,
        )
    module_declarations = tuple(
        item for item in rust_observations if item.rust.kind == "module"
    )
    if len(module_declarations) > rust.MAX_RUST_MODULE_DECLARATIONS:
        return _rejected_build(
            "module_declaration_limit_exceeded",
            rust.MAX_RUST_MODULE_DECLARATIONS,
        )

    candidates = [
        (package, target, rust.make_rust_crate_id(
            package.source,
            target.kind,
            target.crate_name,
        ))
        for package in sorted(context.packages, key=lambda item: item.source)
        for target in sorted(
            package.targets,
            key=lambda item: (item.kind, item.crate_name, item.target_name),
        )
    ]
    id_counts = Counter(crate_id for _, _, crate_id in candidates)
    invalid_packages = {
        package.source
        for package, _, crate_id in candidates
        if id_counts[crate_id] > 1
    }

    problems: list[rust.RustCrateProblem] = []
    for source in sorted(invalid_packages):
        problems.append(_problem(
            "GRAPH_RUST_CRATE_INVALID",
            source,
            "duplicate_crate_identity",
        ))

    crates: dict[str, rust.RustCrate] = {}
    crate_nodes: dict[str, Symbol] = {}
    package_by_crate_id: dict[str, rust.CargoPackage] = {}
    for package, target, crate_id in candidates:
        if package.source in invalid_packages:
            continue
        root_node = file_nodes.get(target.root_file)
        if not _is_rust_file_node(root_node):
            problems.append(_problem(
                "GRAPH_RUST_CRATE_INVALID",
                package.source,
                "crate_root_not_indexed",
            ))
            continue
        crate = rust.RustCrate(
            id=crate_id,
            manifest=package.source,
            package_name=package.name,
            target=target,
        )
        crates[crate_id] = crate
        package_by_crate_id[crate_id] = package
        crate_nodes[crate_id] = _make_crate_node(crate, package, root_node)

    observations_by_source: dict[str, tuple[RawImport, ...]] = {}
    grouped_observations: dict[str, list[RawImport]] = defaultdict(list)
    for item in module_declarations:
        grouped_observations[item.source_file].append(item)
    for source, items in grouped_observations.items():
        observations_by_source[source] = tuple(sorted(
            items,
            key=lambda item: (
                item.line,
                item.rust.lexical_module_path if item.rust else (),
                item.specifier,
                item.text,
            ),
        ))

    modules: dict[
        tuple[str, tuple[str, ...]], list[rust.RustModuleBinding]
    ] = defaultdict(list)
    module_failures: dict[
        tuple[str, str, int, tuple[str, ...], str],
        ImportUnresolvedReason,
    ] = {}
    for crate in sorted(crates.values(), key=lambda item: item.id):
        crate_modules, crate_problems, crate_failures = _build_crate_modules(
            crate,
            file_nodes=file_nodes,
            observations_by_source=observations_by_source,
        )
        problems.extend(crate_problems)
        for key, bindings in crate_modules.items():
            modules[key].extend(bindings)
        for key, reason in crate_failures.items():
            existing = module_failures.get(key)
            module_failures[key] = (
                "ambiguous"
                if existing is not None and existing != reason
                else reason
            )

    frozen_modules = {
        key: tuple(sorted(set(bindings), key=_module_binding_key))
        for key, bindings in sorted(modules.items())
    }
    crate_ids_by_source: dict[str, set[str]] = defaultdict(set)
    for bindings in frozen_modules.values():
        for binding in bindings:
            crate_ids_by_source[binding.source_file].add(binding.crate_id)

    dependencies = _build_dependency_bindings(
        context,
        crates=crates,
        package_by_crate_id=package_by_crate_id,
    )
    if dependencies is None:
        return _rejected_build(
            "resolution_candidate_limit_exceeded",
            rust.MAX_RUST_RESOLUTION_CANDIDATES,
        )
    try:
        alias_result = build_alias_routes(
            crates=crates,
            package_by_crate_id=package_by_crate_id,
            observations=rust_observations,
            modules=frozen_modules,
            dependencies=dependencies,
        )
    except AliasLimitError as exc:
        return _rejected_build(
            exc.reason,
            exc.limit,
        )
    frozen_modules, dependencies = alias_result

    index = rust.RustCrateIndex(
        crate_nodes=tuple(sorted(crate_nodes.values(), key=lambda item: item.id)),
        crates_by_id=MappingProxyType(dict(sorted(crates.items()))),
        crate_ids_by_source_file=MappingProxyType({
            source: tuple(sorted(crate_ids))
            for source, crate_ids in sorted(crate_ids_by_source.items())
        }),
        modules_by_crate_path=MappingProxyType(frozen_modules),
        dependencies_by_crate_alias=MappingProxyType(dependencies),
        module_failures_by_observation=MappingProxyType(dict(sorted(
            module_failures.items()
        ))),
    )
    return rust.RustCrateBuild(
        index=index,
        problems=tuple(sorted(problems, key=_problem_key)),
    )


def resolve_rust_import(
    raw: RawImport,
    *,
    index: rust.RustCrateIndex,
    resolver_index: RustImportResolverIndex | None = None,
) -> rust.RustImportResolution:
    context = raw.rust
    if raw.language != "rust" or context is None:
        return _unresolved_rust("invalid_specifier")
    parts = _rust_specifier_parts(raw)
    if parts is None:
        return _unresolved_rust("invalid_specifier")
    if context.configuration == "unsupported":
        return _unresolved_rust("unsupported_configuration")
    if context.kind == "module" and context.inline:
        return _unresolved_rust("invalid_specifier")

    importer_contexts = _importer_contexts(
        raw,
        index=index,
        resolver_index=(
            resolver_index
            or build_rust_import_resolver_index(index)
        ),
    )
    if not importer_contexts:
        return _unresolved_rust("unsupported_configuration")
    if len(importer_contexts) > rust.MAX_RUST_RESOLUTION_CANDIDATES:
        return _unresolved_rust("ambiguous")

    candidates = tuple(
        _resolve_in_importer_context(
            raw,
            parts=parts,
            importer=item,
            index=index,
        )
        for item in importer_contexts
    )
    return _merge_rust_resolutions(candidates)


def build_rust_import_resolver_index(
    index: rust.RustCrateIndex,
) -> RustImportResolverIndex:
    base_modules: dict[
        tuple[str, str], list[rust.RustModuleBinding]
    ] = defaultdict(list)
    for (owner_crate_id, route_path), bindings in index.modules_by_crate_path.items():
        for binding in bindings:
            if (
                binding.crate_id != owner_crate_id
                or binding.module_path != route_path
            ):
                continue
            parent_bindings = index.modules_by_crate_path.get(
                (owner_crate_id, route_path[:-1]),
                (),
            )
            if route_path and any(
                parent.source_file == binding.source_file
                for parent in parent_bindings
            ):
                continue
            base_modules[(owner_crate_id, binding.source_file)].append(binding)
    return RustImportResolverIndex(MappingProxyType({
        key: tuple(sorted(set(bindings), key=_module_binding_key))
        for key, bindings in sorted(base_modules.items())
    }))


def _rust_specifier_parts(raw: RawImport) -> tuple[str, ...] | None:
    context = raw.rust
    assert context is not None
    specifier = raw.specifier
    if (
        not specifier
        or any(character.isspace() or ord(character) < 32 for character in specifier)
    ):
        return None
    absolute = specifier.startswith("::")
    body = specifier[2:] if absolute else specifier
    if not body or body.startswith(":") or body.endswith(":"):
        return None
    parts = tuple(body.split("::"))
    if (
        any(not part for part in parts)
        or len(parts) > rust.MAX_RUST_MODULE_DEPTH
    ):
        return None
    if context.kind == "module":
        return parts if len(parts) == 1 and _valid_rust_identifier(parts[0]) else None
    if context.kind == "extern_crate":
        return (
            parts
            if len(parts) == 1
            and (parts[0] == "self" or _valid_rust_identifier(parts[0]))
            else None
        )
    special = {"crate", "self", "super"}
    if absolute and any(part in special for part in parts):
        return None
    if not absolute:
        if parts[0] in {"crate", "self"}:
            if any(part in special for part in parts[1:]):
                return None
        elif parts[0] == "super":
            offset = 0
            while offset < len(parts) and parts[offset] == "super":
                offset += 1
            if any(part in special for part in parts[offset:]):
                return None
        elif any(part in special for part in parts):
            return None
    for index, part in enumerate(parts):
        if part == "*":
            if index != len(parts) - 1:
                return None
            continue
        if part in {"crate", "self", "super"}:
            continue
        if not _valid_rust_identifier(part):
            return None
    return parts


def _valid_rust_identifier(value: str) -> bool:
    raw = value.startswith("r#")
    identifier = value[2:] if raw else value
    if not identifier or not identifier.isidentifier():
        return False
    if identifier in {"crate", "self", "super", "Self"}:
        return False
    if not raw and identifier in _RUST_KEYWORDS:
        return False
    return True


def _importer_contexts(
    raw: RawImport,
    *,
    index: rust.RustCrateIndex,
    resolver_index: RustImportResolverIndex,
) -> tuple[_ImporterContext, ...]:
    context = raw.rust
    assert context is not None
    candidates: list[_ImporterContext] = []
    owner_ids = frozenset(index.crate_ids_by_source_file.get(raw.source_file, ()))
    if not owner_ids:
        return ()
    for owner_crate_id in sorted(owner_ids):
        for binding in resolver_index.base_modules_by_source.get(
            (owner_crate_id, raw.source_file),
            (),
        ):
            route_path = binding.module_path
            declaring_path = (*route_path, *context.lexical_module_path)
            declaring = _canonical_source_binding(
                index,
                owner_crate_id=owner_crate_id,
                module_path=declaring_path,
                source_file=raw.source_file,
            )
            if declaring is None:
                continue
            configuration = merge_observed_configuration(
                declaring.configuration,
                context.configuration,
            )
            if configuration is None:
                continue
            candidates.append(_ImporterContext(
                crate_id=owner_crate_id,
                declaring=declaring,
                configuration=configuration,
            ))
            if len(candidates) > rust.MAX_RUST_RESOLUTION_CANDIDATES:
                return tuple(candidates)
    return tuple(sorted(
        set(candidates),
        key=lambda item: (
            item.crate_id,
            item.declaring.module_path,
            item.declaring.source_file,
            item.configuration,
        ),
    ))


def _canonical_source_binding(
    index: rust.RustCrateIndex,
    *,
    owner_crate_id: str,
    module_path: tuple[str, ...],
    source_file: str,
) -> rust.RustModuleBinding | None:
    candidates = tuple(
        binding
        for binding in index.modules_by_crate_path.get(
            (owner_crate_id, module_path),
            (),
        )
        if binding.crate_id == owner_crate_id
        and binding.module_path == module_path
        and binding.source_file == source_file
    )
    if len(candidates) != 1:
        return None
    return candidates[0]


def _resolve_in_importer_context(
    raw: RawImport,
    *,
    parts: tuple[str, ...],
    importer: _ImporterContext,
    index: rust.RustCrateIndex,
) -> rust.RustImportResolution:
    context = raw.rust
    assert context is not None
    crate = index.crates_by_id[importer.crate_id]
    controls = (crate.manifest,)

    if context.kind == "module":
        failure = index.module_failures_by_observation.get(
            _module_failure_key(
                importer.crate_id,
                raw,
                importer.declaring.module_path,
            )
        )
        if failure is not None:
            return _unresolved_rust(failure)
        walk = _walk_module_route(
            importer.declaring,
            parts,
            importer=importer,
            index=index,
        )
        if walk.unresolved_reason is not None:
            return _unresolved_rust(walk.unresolved_reason)
        if walk.matched_segments != 1:
            return _unresolved_rust("not_indexed")
        return _resolved_from_walk(
            walk,
            basis="rust_module_declaration",
            control_files=controls,
            index=index,
        )

    if context.kind == "extern_crate":
        if parts == ("self",):
            return _resolved_crate(
                importer.crate_id,
                basis="rust_module_path",
                control_files=controls,
                configuration=importer.configuration,
                index=index,
            )
        alias = raw.imported_name or parts[0]
        return _resolve_dependency_route(
            alias,
            (),
            importer=importer,
            index=index,
        )

    absolute = raw.specifier.startswith("::")
    if parts[0] == "crate":
        root = _crate_root_binding(importer.crate_id, index=index)
        return _resolve_local_route(
            root,
            parts[1:],
            importer=importer,
            index=index,
        )
    if parts[0] == "self":
        return _resolve_local_route(
            importer.declaring,
            parts[1:],
            importer=importer,
            index=index,
        )
    if parts[0] == "super":
        parent_path = list(importer.declaring.module_path)
        offset = 0
        while offset < len(parts) and parts[offset] == "super":
            if not parent_path:
                return _unresolved_rust("invalid_specifier")
            parent_path.pop()
            offset += 1
        parent = _one_route_binding(
            importer.crate_id,
            tuple(parent_path),
            importer=importer,
            index=index,
        )
        if parent is None:
            return _unresolved_rust("unsupported_configuration")
        if isinstance(parent, str):
            return _unresolved_rust(parent)
        return _resolve_local_route(
            parent,
            parts[offset:],
            importer=importer,
            index=index,
        )

    if absolute and crate.target.edition == "2015":
        return _resolve_local_route(
            _crate_root_binding(importer.crate_id, index=index),
            parts,
            importer=importer,
            index=index,
        )

    if not absolute:
        local_start = (
            _crate_root_binding(importer.crate_id, index=index)
            if crate.target.edition == "2015"
            else importer.declaring
        )
        local_walk = _walk_module_route(
            local_start,
            parts,
            importer=importer,
            index=index,
        )
        if local_walk.unresolved_reason is not None:
            return _unresolved_rust(local_walk.unresolved_reason)
        if local_walk.matched_segments:
            return _resolved_from_walk(
                local_walk,
                basis="rust_module_path",
                control_files=controls,
                index=index,
            )

    return _resolve_dependency_route(
        parts[0],
        parts[1:],
        importer=importer,
        index=index,
    )


def _resolve_local_route(
    start: rust.RustModuleBinding,
    parts: tuple[str, ...],
    *,
    importer: _ImporterContext,
    index: rust.RustCrateIndex,
) -> rust.RustImportResolution:
    walk = _walk_module_route(
        start,
        parts,
        importer=importer,
        index=index,
    )
    if walk.unresolved_reason is not None:
        return _unresolved_rust(walk.unresolved_reason)
    return _resolved_from_walk(
        walk,
        basis="rust_module_path",
        control_files=(index.crates_by_id[importer.crate_id].manifest,),
        index=index,
    )


def _resolve_dependency_route(
    alias: str,
    parts: tuple[str, ...],
    *,
    importer: _ImporterContext,
    index: rust.RustCrateIndex,
) -> rust.RustImportResolution:
    bindings = index.dependencies_by_crate_alias.get((importer.crate_id, alias), ())
    if not bindings:
        return _unresolved_rust("external")
    if len(bindings) > rust.MAX_RUST_RESOLUTION_CANDIDATES:
        return _unresolved_rust("ambiguous")
    target_ids = {binding.target_crate_id for binding in bindings}
    if len(target_ids) != 1:
        return _unresolved_rust("ambiguous")
    binding = merge_dependency_bindings(bindings)
    root = _crate_root_binding(binding.target_crate_id, index=index)
    walk = _walk_module_route(
        root,
        parts,
        importer=importer,
        index=index,
    )
    if walk.unresolved_reason is not None:
        return _unresolved_rust(walk.unresolved_reason)
    configuration = widest_configuration(
        importer.configuration,
        binding.configuration,
    )
    walk = _RouteWalk(
        binding=walk.binding,
        matched_segments=walk.matched_segments,
        configuration=widest_configuration(configuration, walk.configuration),
    )
    return _resolved_from_walk(
        walk,
        basis=binding.basis,
        control_files=binding.control_files,
        index=index,
    )


def _walk_module_route(
    start: rust.RustModuleBinding,
    parts: tuple[str, ...],
    *,
    importer: _ImporterContext,
    index: rust.RustCrateIndex,
) -> _RouteWalk:
    current = start
    configuration = widest_configuration(
        importer.configuration,
        start.configuration,
    )
    matched = 0
    for part in parts:
        if part == "*":
            break
        route_path = (*current.module_path, part)
        next_binding = _one_route_binding(
            current.crate_id,
            route_path,
            importer=importer,
            index=index,
        )
        if next_binding is None:
            break
        if isinstance(next_binding, str):
            return _RouteWalk(
                binding=current,
                matched_segments=matched,
                configuration=configuration,
                unresolved_reason=next_binding,
            )
        current = next_binding
        configuration = widest_configuration(
            configuration,
            current.configuration,
        )
        matched += 1
    return _RouteWalk(
        binding=current,
        matched_segments=matched,
        configuration=configuration,
    )


def _one_route_binding(
    owner_crate_id: str,
    route_path: tuple[str, ...],
    *,
    importer: _ImporterContext,
    index: rust.RustCrateIndex,
) -> rust.RustModuleBinding | ImportUnresolvedReason | None:
    bindings = index.modules_by_crate_path.get((owner_crate_id, route_path), ())
    if not bindings:
        return None
    if len(bindings) > rust.MAX_RUST_RESOLUTION_CANDIDATES:
        return "ambiguous"
    visible = tuple(
        binding
        for binding in bindings
        if _route_is_visible(
            index.modules_by_crate_path,
            owner_crate_id=owner_crate_id,
            route_path=route_path,
            importer_crate_id=importer.crate_id,
            importer_path=importer.declaring.module_path,
        )
    )
    if not visible:
        return "inaccessible"
    endpoints = {
        (binding.crate_id, binding.module_path, binding.source_file)
        for binding in visible
    }
    if len(endpoints) != 1:
        return "ambiguous"
    target = visible[0]
    configuration = target.configuration
    for binding in visible[1:]:
        configuration = widest_configuration(
            configuration,
            binding.configuration,
        )
    return rust.RustModuleBinding(
        crate_id=target.crate_id,
        module_path=target.module_path,
        source_file=target.source_file,
        visibility=target.visibility,
        configuration=configuration,
    )


def _crate_root_binding(
    crate_id: str,
    *,
    index: rust.RustCrateIndex,
) -> rust.RustModuleBinding:
    bindings = index.modules_by_crate_path[(crate_id, ())]
    return bindings[0]


def _resolved_from_walk(
    walk: _RouteWalk,
    *,
    basis: rust.RustResolutionBasis,
    control_files: tuple[str, ...],
    index: rust.RustCrateIndex,
) -> rust.RustImportResolution:
    if walk.binding.module_path:
        return rust.RustImportResolution(
            target_file=walk.binding.source_file,
            target_crate=None,
            target_id=make_symbol_id(
                walk.binding.source_file,
                FILE_NODE_QUALIFIED_NAME,
                "file",
            ),
            basis=basis,
            control_files=tuple(sorted(set(control_files))),
            configuration=walk.configuration,
            unresolved_reason=None,
        )
    return _resolved_crate(
        walk.binding.crate_id,
        basis=basis,
        control_files=control_files,
        configuration=walk.configuration,
        index=index,
    )


def _resolved_crate(
    crate_id: str,
    *,
    basis: rust.RustResolutionBasis,
    control_files: tuple[str, ...],
    configuration: rust.RustResolutionConfiguration,
    index: rust.RustCrateIndex,
) -> rust.RustImportResolution:
    crate = index.crates_by_id[crate_id]
    return rust.RustImportResolution(
        target_file=None,
        target_crate=crate.id.removesuffix("#crate"),
        target_id=crate_id,
        basis=basis,
        control_files=tuple(sorted(set(control_files))),
        configuration=configuration,
        unresolved_reason=None,
    )


def _unresolved_rust(
    reason: ImportUnresolvedReason,
) -> rust.RustImportResolution:
    return rust.RustImportResolution(
        target_file=None,
        target_crate=None,
        target_id=None,
        basis=None,
        control_files=(),
        configuration=None,
        unresolved_reason=reason,
    )


def _merge_rust_resolutions(
    resolutions: tuple[rust.RustImportResolution, ...],
) -> rust.RustImportResolution:
    unresolved = tuple(
        item.unresolved_reason
        for item in resolutions
        if item.unresolved_reason is not None
    )
    if unresolved:
        if len(unresolved) == len(resolutions) and len(set(unresolved)) == 1:
            return _unresolved_rust(unresolved[0])
        return _unresolved_rust("ambiguous")
    endpoints = {
        (item.target_file, item.target_crate, item.target_id)
        for item in resolutions
    }
    if len(endpoints) != 1:
        return _unresolved_rust("ambiguous")
    first = resolutions[0]
    bases = tuple(item.basis for item in resolutions)
    configurations = tuple(item.configuration for item in resolutions)
    assert all(basis is not None for basis in bases)
    assert all(configuration is not None for configuration in configurations)
    basis_priority = {
        "cargo_package_library": 0,
        "cargo_path_dependency": 1,
        "cargo_workspace_dependency": 2,
        "rust_module_path": 3,
        "rust_module_declaration": 4,
    }
    basis = min(bases, key=basis_priority.__getitem__)  # type: ignore[arg-type]
    configuration = configurations[0]
    assert configuration is not None
    for candidate in configurations[1:]:
        assert candidate is not None
        configuration = widest_configuration(configuration, candidate)
    return rust.RustImportResolution(
        target_file=first.target_file,
        target_crate=first.target_crate,
        target_id=first.target_id,
        basis=basis,
        control_files=tuple(sorted({
            control
            for item in resolutions
            for control in item.control_files
        })),
        configuration=configuration,
        unresolved_reason=None,
    )


def _build_crate_modules(
    crate: rust.RustCrate,
    *,
    file_nodes: Mapping[str, Symbol],
    observations_by_source: Mapping[str, tuple[RawImport, ...]],
) -> tuple[
    dict[tuple[str, tuple[str, ...]], list[rust.RustModuleBinding]],
    list[rust.RustCrateProblem],
    dict[
        tuple[str, str, int, tuple[str, ...], str],
        ImportUnresolvedReason,
    ],
]:
    modules: dict[
        tuple[str, tuple[str, ...]], list[rust.RustModuleBinding]
    ] = defaultdict(list)
    problems: list[rust.RustCrateProblem] = []
    failures: dict[
        tuple[str, str, int, tuple[str, ...], str],
        ImportUnresolvedReason,
    ] = {}
    root_configuration: rust.RustResolutionConfiguration = (
        "declared_possible" if crate.target.required_features else "unconditional"
    )
    root = rust.RustModuleBinding(
        crate_id=crate.id,
        module_path=(),
        source_file=crate.target.root_file,
        visibility="pub",
        configuration=root_configuration,
    )
    modules[(crate.id, ())].append(root)
    queue = deque([_OwnedModuleFile(root, (root.source_file,))])
    visited: set[tuple[tuple[str, ...], str, rust.RustResolutionConfiguration]] = set()

    while queue:
        owned = queue.popleft()
        visit_key = (
            owned.binding.module_path,
            owned.binding.source_file,
            owned.binding.configuration,
        )
        if visit_key in visited:
            continue
        visited.add(visit_key)
        for raw in observations_by_source.get(owned.binding.source_file, ()):
            context = raw.rust
            assert context is not None
            lexical = _lexical_context(context)
            if lexical is None:
                problems.append(_problem(
                    "GRAPH_RUST_MODULE_INVALID",
                    raw.source_file,
                    "invalid_lexical_module_context",
                ))
                failures[_module_failure_key(
                    crate.id,
                    raw,
                    (*owned.binding.module_path, *context.lexical_module_path),
                )] = "unsupported_configuration"
                continue

            declaring_path = owned.binding.module_path
            declaring_configuration = owned.binding.configuration
            valid_lexical = True
            for name, visibility, configuration in lexical:
                declaring_path = (*declaring_path, name)
                declaring_configuration = merge_observed_configuration(
                    declaring_configuration,
                    configuration,
                )
                if declaring_configuration is None:
                    problems.append(_problem(
                        "GRAPH_RUST_MODULE_INVALID",
                        raw.source_file,
                        "unsupported_module_configuration",
                    ))
                    valid_lexical = False
                    break
                inline_binding = rust.RustModuleBinding(
                    crate_id=crate.id,
                    module_path=declaring_path,
                    source_file=owned.binding.source_file,
                    visibility=visibility,
                    configuration=declaring_configuration,
                )
                _record_module_binding(modules, inline_binding)
            if not valid_lexical:
                continue

            child_path = (*declaring_path, raw.specifier)
            if len(child_path) > rust.MAX_RUST_MODULE_DEPTH:
                problems.append(_problem(
                    "GRAPH_RUST_MODULE_INVALID",
                    raw.source_file,
                    "module_depth_exceeded",
                    limit=rust.MAX_RUST_MODULE_DEPTH,
                ))
                failures[_module_failure_key(
                    crate.id,
                    raw,
                    declaring_path,
                )] = "unsupported_configuration"
                continue
            child_configuration = merge_observed_configuration(
                declaring_configuration,
                context.configuration,
            )
            if child_configuration is None:
                problems.append(_problem(
                    "GRAPH_RUST_MODULE_INVALID",
                    raw.source_file,
                    "unsupported_module_configuration",
                ))
                failures[_module_failure_key(
                    crate.id,
                    raw,
                    declaring_path,
                )] = "unsupported_configuration"
                continue

            if context.inline:
                _record_module_binding(
                    modules,
                    rust.RustModuleBinding(
                        crate_id=crate.id,
                        module_path=child_path,
                        source_file=owned.binding.source_file,
                        visibility=context.visibility,
                        configuration=child_configuration,
                    ),
                )
                continue

            candidate, reason = _external_module_source(
                raw,
                context,
                file_nodes=file_nodes,
            )
            if candidate is None:
                problems.append(_problem(
                    "GRAPH_RUST_MODULE_INVALID",
                    raw.source_file,
                    reason,
                ))
                failures[_module_failure_key(
                    crate.id,
                    raw,
                    declaring_path,
                )] = _module_unresolved_reason(reason)
                continue
            if candidate in owned.ancestry:
                problems.append(_problem(
                    "GRAPH_RUST_MODULE_INVALID",
                    raw.source_file,
                    "cyclic_module_source",
                ))
                failures[_module_failure_key(
                    crate.id,
                    raw,
                    declaring_path,
                )] = "unsupported_configuration"
                continue
            binding = rust.RustModuleBinding(
                crate_id=crate.id,
                module_path=child_path,
                source_file=candidate,
                visibility=context.visibility,
                configuration=child_configuration,
            )
            if _record_module_binding(modules, binding):
                queue.append(_OwnedModuleFile(
                    binding,
                    (*owned.ancestry, candidate),
                ))

    return dict(modules), problems, failures


def _module_failure_key(
    crate_id: str,
    raw: RawImport,
    declaring_path: tuple[str, ...],
) -> tuple[str, str, int, tuple[str, ...], str]:
    return (
        crate_id,
        raw.source_file,
        raw.line,
        declaring_path,
        raw.specifier,
    )


def _module_unresolved_reason(reason: str) -> ImportUnresolvedReason:
    if reason == "ambiguous_module_source":
        return "ambiguous"
    if reason == "module_source_not_indexed":
        return "not_indexed"
    return "invalid_specifier"


def _build_dependency_bindings(
    context: rust.CargoContext,
    *,
    crates: Mapping[str, rust.RustCrate],
    package_by_crate_id: Mapping[str, rust.CargoPackage],
) -> dict[tuple[str, str], tuple[rust.RustDependencyBinding, ...]] | None:
    packages_by_root: dict[str, list[rust.CargoPackage]] = defaultdict(list)
    for package in context.packages:
        packages_by_root[package.root].append(package)
    library_by_package: dict[str, rust.RustCrate] = {}
    for crate_id, crate in crates.items():
        if crate.target.kind == "lib":
            library_by_package[package_by_crate_id[crate_id].source] = crate

    candidates: dict[
        tuple[str, str], list[rust.RustDependencyBinding]
    ] = defaultdict(list)
    for crate_id, crate in sorted(crates.items()):
        package = package_by_crate_id[crate_id]
        allowed_kinds = _dependency_kinds_for_target(crate.target.kind)
        for dependency in package.dependencies:
            if dependency.kind not in allowed_kinds or dependency.path is None:
                continue
            target_packages = [
                target_package
                for target_package in packages_by_root.get(dependency.path, ())
                if target_package.name == dependency.package_name
                and target_package.source in library_by_package
            ]
            if len(target_packages) != 1:
                continue
            target_package = target_packages[0]
            target_crate = library_by_package[target_package.source]
            configuration: rust.RustResolutionConfiguration = (
                "declared_possible"
                if (
                    crate.target.required_features
                    or dependency.optional
                    or dependency.target_condition is not None
                )
                else "unconditional"
            )
            candidates[(crate_id, dependency.alias)].append(
                rust.RustDependencyBinding(
                    source_crate_id=crate_id,
                    alias=dependency.alias,
                    target_crate_id=target_crate.id,
                    basis=(
                        "cargo_workspace_dependency"
                        if dependency.inherited
                        else "cargo_path_dependency"
                    ),
                    configuration=configuration,
                    control_files=tuple(sorted({
                        package.source,
                        dependency.source,
                        target_package.source,
                    })),
                )
            )

        if crate.target.kind in {"bin", "example", "test", "bench"}:
            library = library_by_package.get(package.source)
            if library is not None:
                candidates[(crate_id, library.target.crate_name)].append(
                    rust.RustDependencyBinding(
                        source_crate_id=crate_id,
                        alias=library.target.crate_name,
                        target_crate_id=library.id,
                        basis="cargo_package_library",
                        configuration=(
                            "declared_possible"
                            if crate.target.required_features
                            else "unconditional"
                        ),
                        control_files=(package.source,),
                    )
                )

    merged: dict[
        tuple[str, str], tuple[rust.RustDependencyBinding, ...]
    ] = {}
    for key, bindings in sorted(candidates.items()):
        if len(bindings) > rust.MAX_RUST_RESOLUTION_CANDIDATES:
            return None
        by_target: dict[str, list[rust.RustDependencyBinding]] = defaultdict(list)
        for binding in bindings:
            by_target[binding.target_crate_id].append(binding)
        merged[key] = tuple(
            merge_dependency_bindings(target_bindings)
            for _, target_bindings in sorted(by_target.items())
        )
    return merged


def _dependency_kinds_for_target(
    target_kind: rust.RustTargetKind,
) -> frozenset[rust.RustDependencyKind]:
    if target_kind == "build_script":
        return frozenset({"build"})
    if target_kind in {"example", "test", "bench"}:
        return frozenset({"normal", "dev"})
    return frozenset({"normal"})


def _lexical_context(
    context: RustImportContext,
) -> tuple[tuple[str, str, str], ...] | None:
    count = len(context.lexical_module_path)
    if not (
        len(context.lexical_module_visibilities) == count
        and len(context.lexical_module_configurations) == count
    ):
        return None
    return tuple(zip(
        context.lexical_module_path,
        context.lexical_module_visibilities,
        context.lexical_module_configurations,
        strict=True,
    ))


def _external_module_source(
    raw: RawImport,
    context: RustImportContext,
    *,
    file_nodes: Mapping[str, Symbol],
) -> tuple[str | None, str]:
    if context.path_override is not None:
        base = _path_attribute_directory(
            raw.source_file,
            context.lexical_module_path,
        )
        candidate = _normalized_join(base, context.path_override)
        if candidate is None:
            return None, "module_path_outside_repository"
        if not _is_rust_file_node(file_nodes.get(candidate)):
            return None, "module_source_not_indexed"
        return candidate, ""

    base = _module_directory(raw.source_file, context.lexical_module_path)
    candidates = (
        _normalized_join(base, f"{raw.specifier}.rs"),
        _normalized_join(base, f"{raw.specifier}/mod.rs"),
    )
    indexed = tuple(
        candidate
        for candidate in candidates
        if candidate is not None and _is_rust_file_node(file_nodes.get(candidate))
    )
    if not indexed:
        return None, "module_source_not_indexed"
    if len(indexed) > 1:
        return None, "ambiguous_module_source"
    return indexed[0], ""


def _module_directory(
    source_file: str,
    lexical_module_path: tuple[str, ...],
) -> PurePosixPath:
    source = PurePosixPath(source_file)
    if source.name in {"lib.rs", "main.rs", "mod.rs"}:
        base = source.parent
    else:
        base = source.parent / source.stem
    for part in lexical_module_path:
        base /= part
    return base


def _path_attribute_directory(
    source_file: str,
    lexical_module_path: tuple[str, ...],
) -> PurePosixPath:
    source = PurePosixPath(source_file)
    base = source.parent
    if lexical_module_path and source.name not in {"lib.rs", "main.rs", "mod.rs"}:
        base /= source.stem
    for part in lexical_module_path:
        base /= part
    return base


def _normalized_join(base: PurePosixPath, value: str) -> str | None:
    if (
        not value
        or "\x00" in value
        or "\\" in value
        or any(part == "" for part in value.split("/"))
    ):
        return None
    raw = PurePosixPath(value)
    if raw.is_absolute():
        return None
    parts = list(base.parts)
    for part in raw.parts:
        if part == ".":
            continue
        if part == "..":
            if not parts:
                return None
            parts.pop()
            continue
        parts.append(part)
    return "/".join(parts) if parts else None


def _record_module_binding(
    modules: dict[tuple[str, tuple[str, ...]], list[rust.RustModuleBinding]],
    binding: rust.RustModuleBinding,
) -> bool:
    bindings = modules[(binding.crate_id, binding.module_path)]
    if binding in bindings:
        return False
    bindings.append(binding)
    return True


def _make_crate_node(
    crate: rust.RustCrate,
    package: rust.CargoPackage,
    root: Symbol,
) -> Symbol:
    qualified_name = crate.id.removesuffix("#crate")
    return Symbol(
        id=crate.id,
        name=crate.target.crate_name,
        qualified_name=qualified_name,
        kind="crate",
        language="rust",
        file_path=crate.target.root_file,
        byte_offset=0,
        byte_length=0,
        signature=qualified_name,
        content_hash=root.content_hash,
        keywords=_crate_keywords(crate, package),
        metadata={
            "loci": {
                "rust_crate_node": True,
                "manifest": crate.manifest,
                "package_name": crate.package_name,
                "package_root": package.root,
                "target_kind": crate.target.kind,
                "target_name": crate.target.target_name,
                "crate_name": crate.target.crate_name,
                "crate_root": crate.target.root_file,
                "edition": crate.target.edition,
                "required_features": list(crate.target.required_features),
            }
        },
        line=1,
        end_line=1,
    )


def _crate_keywords(crate: rust.RustCrate, package: rust.CargoPackage) -> list[str]:
    values = (
        crate.manifest,
        crate.package_name,
        package.root,
        crate.target.kind,
        crate.target.target_name,
        crate.target.crate_name,
        crate.target.root_file,
    )
    return sorted({
        match.group(0).lower()
        for value in values
        for match in re.finditer(r"[A-Za-z0-9]+", value)
    })


def _is_rust_file_node(node: Symbol | None) -> bool:
    if node is None or node.kind != "file" or node.language != "rust":
        return False
    loci = node.metadata.get("loci")
    return isinstance(loci, dict) and loci.get("file_node") is True


def _module_binding_key(
    binding: rust.RustModuleBinding,
) -> tuple[str, tuple[str, ...], str, str, str]:
    return (
        binding.crate_id,
        binding.module_path,
        binding.source_file,
        binding.visibility,
        binding.configuration,
    )


def _problem(
    code: rust.RustCrateProblemCode,
    source: str,
    reason: str,
    *,
    limit: int | None = None,
) -> rust.RustCrateProblem:
    details: dict[str, rust.JSONValue] = {"reason": reason}
    if limit is not None:
        details["limit"] = limit
    message = {
        "GRAPH_RUST_CRATE_INVALID": "Rust crate target is invalid",
        "GRAPH_RUST_MODULE_INVALID": "Rust module context is invalid",
        "GRAPH_RUST_INDEX_LIMIT_EXCEEDED": "Rust crate index limit exceeded",
    }[code]
    return rust.RustCrateProblem(code, message, source, details)


def _problem_key(
    problem: rust.RustCrateProblem,
) -> tuple[str, str, str, int]:
    reason = problem.details.get("reason")
    limit = problem.details.get("limit")
    return (
        problem.source,
        problem.code,
        reason if isinstance(reason, str) else "",
        limit if isinstance(limit, int) else -1,
    )


def _empty_index() -> rust.RustCrateIndex:
    return rust.RustCrateIndex(
        crate_nodes=(),
        crates_by_id=MappingProxyType({}),
        crate_ids_by_source_file=MappingProxyType({}),
        modules_by_crate_path=MappingProxyType({}),
        dependencies_by_crate_alias=MappingProxyType({}),
        module_failures_by_observation=MappingProxyType({}),
    )


def _rejected_build(reason: str, limit: int) -> rust.RustCrateBuild:
    return rust.RustCrateBuild(
        index=_empty_index(),
        problems=(
            _problem(
                "GRAPH_RUST_INDEX_LIMIT_EXCEEDED",
                "@rust-index",
                reason,
                limit=limit,
            ),
        ),
    )
