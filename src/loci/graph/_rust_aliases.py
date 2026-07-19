from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from loci.parser.imports import RawImport

from . import rust_crates as rust
from ._rust_semantics import merge_observed_configuration, widest_configuration


@dataclass(frozen=True, slots=True)
class _AliasInput:
    source_crate_id: str
    declaring_path: tuple[str, ...]
    source_configuration: rust.RustResolutionConfiguration
    raw: RawImport


class AliasLimitError(RuntimeError):
    def __init__(self, reason: str, limit: int) -> None:
        super().__init__(reason)
        self.reason = reason
        self.limit = limit


def build_alias_routes(
    *,
    crates: Mapping[str, rust.RustCrate],
    package_by_crate_id: Mapping[str, rust.CargoPackage],
    observations: Sequence[RawImport],
    modules: Mapping[
        tuple[str, tuple[str, ...]], tuple[rust.RustModuleBinding, ...]
    ],
    dependencies: Mapping[
        tuple[str, str], tuple[rust.RustDependencyBinding, ...]
    ],
) -> tuple[
    dict[tuple[str, tuple[str, ...]], tuple[rust.RustModuleBinding, ...]],
    dict[tuple[str, str], tuple[rust.RustDependencyBinding, ...]],
]:
    routes = dict(modules)
    dependency_routes = dict(dependencies)
    alias_inputs = _alias_inputs(
        crates=crates,
        observations=observations,
        modules=modules,
    )

    module_groups: dict[
        tuple[str, tuple[str, ...]], list[_AliasInput]
    ] = defaultdict(list)
    extern_groups: dict[tuple[str, str], list[_AliasInput]] = defaultdict(list)
    for item in alias_inputs:
        context = item.raw.rust
        assert context is not None
        alias = item.raw.imported_name
        if alias is None or alias == "_":
            continue
        if context.kind == "extern_crate":
            extern_groups[(item.source_crate_id, alias)].append(item)
        elif context.kind == "use" and not item.raw.specifier.endswith("::*"):
            module_groups[
                (item.source_crate_id, (*item.declaring_path, alias))
            ].append(item)

    for key, items in sorted(extern_groups.items()):
        if len(items) > rust.MAX_RUST_RESOLUTION_CANDIDATES:
            raise AliasLimitError(
                "resolution_candidate_limit_exceeded",
                rust.MAX_RUST_RESOLUTION_CANDIDATES,
            )
        candidates: list[rust.RustDependencyBinding] = []
        for item in items:
            context = item.raw.rust
            assert context is not None
            source_crate = crates[item.source_crate_id]
            package = package_by_crate_id[item.source_crate_id]
            if item.raw.specifier == "self":
                candidates.append(rust.RustDependencyBinding(
                    source_crate_id=item.source_crate_id,
                    alias=key[1],
                    target_crate_id=item.source_crate_id,
                    basis="rust_module_path",
                    configuration=item.source_configuration,
                    control_files=(package.source,),
                ))
                continue
            for binding in dependency_routes.get(
                (source_crate.id, item.raw.specifier),
                (),
            ):
                candidates.append(rust.RustDependencyBinding(
                    source_crate_id=item.source_crate_id,
                    alias=key[1],
                    target_crate_id=binding.target_crate_id,
                    basis=binding.basis,
                    configuration=widest_configuration(
                        item.source_configuration,
                        binding.configuration,
                    ),
                    control_files=binding.control_files,
                ))
        if len(candidates) > rust.MAX_RUST_RESOLUTION_CANDIDATES:
            raise AliasLimitError(
                "resolution_candidate_limit_exceeded",
                rust.MAX_RUST_RESOLUTION_CANDIDATES,
            )
        if candidates:
            grouped: dict[str, list[rust.RustDependencyBinding]] = defaultdict(list)
            for candidate in candidates:
                grouped[candidate.target_crate_id].append(candidate)
            dependency_routes[key] = tuple(
                merge_dependency_bindings(target_bindings)
                for _, target_bindings in sorted(grouped.items())
            )

    extern_aliases = frozenset(extern_groups)

    pending = dict(sorted(module_groups.items()))
    if any(
        len(items) > rust.MAX_RUST_RESOLUTION_CANDIDATES
        for items in pending.values()
    ):
        raise AliasLimitError(
            "resolution_candidate_limit_exceeded",
            rust.MAX_RUST_RESOLUTION_CANDIDATES,
        )
    original_route_keys = frozenset(routes)
    for pass_number in range(rust.MAX_RUST_ALIAS_PASSES):
        added = False
        completed: list[tuple[str, tuple[str, ...]]] = []
        for key, items in pending.items():
            if key in routes:
                completed.append(key)
                continue
            targets: list[rust.RustModuleBinding] = []
            all_resolved = True
            for item in items:
                target = _resolve_alias_target(
                    item,
                    crates=crates,
                    modules=routes,
                    dependencies=dependency_routes,
                    extern_aliases=extern_aliases,
                )
                if target is None:
                    all_resolved = False
                    break
                targets.append(target)
            if not all_resolved:
                continue
            completed.append(key)
            endpoints = {
                (target.crate_id, target.module_path, target.source_file)
                for target in targets
            }
            if len(endpoints) != 1:
                continue
            target = targets[0]
            contexts = [item.raw.rust for item in items]
            assert all(context is not None for context in contexts)
            visibility = (
                contexts[0].visibility
                if all(
                    context.visibility == contexts[0].visibility
                    for context in contexts
                    if context is not None
                )
                else "private"
            )
            configuration: rust.RustResolutionConfiguration = target.configuration
            for item in items:
                configuration = widest_configuration(
                    configuration,
                    item.source_configuration,
                )
            routes[key] = (
                rust.RustModuleBinding(
                    crate_id=target.crate_id,
                    module_path=target.module_path,
                    source_file=target.source_file,
                    visibility=visibility,
                    configuration=configuration,
                ),
            )
            added = True
        for key in completed:
            pending.pop(key, None)
        if not added:
            break
        if pass_number + 1 == rust.MAX_RUST_ALIAS_PASSES and pending:
            for key in tuple(routes):
                if key not in original_route_keys:
                    routes.pop(key)
            raise AliasLimitError(
                "alias_pass_limit_exceeded",
                rust.MAX_RUST_ALIAS_PASSES,
            )

    for key in tuple(dependency_routes):
        crate = crates[key[0]]
        if crate.target.edition == "2015" and key not in extern_groups:
            dependency_routes.pop(key)

    return dict(sorted(routes.items())), dict(sorted(dependency_routes.items()))


def _alias_inputs(
    *,
    crates: Mapping[str, rust.RustCrate],
    observations: Sequence[RawImport],
    modules: Mapping[
        tuple[str, tuple[str, ...]], tuple[rust.RustModuleBinding, ...]
    ],
) -> tuple[_AliasInput, ...]:
    base_modules_by_source: dict[
        tuple[str, str], list[rust.RustModuleBinding]
    ] = defaultdict(list)
    crate_ids_by_source: dict[str, set[str]] = defaultdict(set)
    for (owner_crate_id, route_path), bindings in modules.items():
        for binding in bindings:
            if binding.crate_id != owner_crate_id or binding.module_path != route_path:
                continue
            parent_bindings = modules.get((owner_crate_id, route_path[:-1]), ())
            if route_path and any(
                parent.source_file == binding.source_file
                for parent in parent_bindings
            ):
                continue
            base_modules_by_source[(owner_crate_id, binding.source_file)].append(binding)
            crate_ids_by_source[binding.source_file].add(owner_crate_id)

    inputs: list[_AliasInput] = []
    for raw in sorted(
        observations,
        key=lambda item: (item.source_file, item.line, item.specifier, item.text),
    ):
        context = raw.rust
        if (
            context is None
            or context.kind == "module"
            or not context.module_level
            or context.configuration == "unsupported"
        ):
            continue
        for crate_id in sorted(crate_ids_by_source.get(raw.source_file, ())):
            for base in base_modules_by_source.get((crate_id, raw.source_file), ()):
                declaring_path = (*base.module_path, *context.lexical_module_path)
                declaring_bindings = modules.get((crate_id, declaring_path), ())
                declaring = next(
                    (
                        binding
                        for binding in declaring_bindings
                        if binding.crate_id == crate_id
                        and binding.module_path == declaring_path
                        and binding.source_file == raw.source_file
                    ),
                    None,
                )
                if declaring is None:
                    continue
                configuration = merge_observed_configuration(
                    declaring.configuration,
                    context.configuration,
                )
                if configuration is None:
                    continue
                inputs.append(_AliasInput(
                    source_crate_id=crate_id,
                    declaring_path=declaring_path,
                    source_configuration=configuration,
                    raw=raw,
                ))
    return tuple(inputs)


def _resolve_alias_target(
    item: _AliasInput,
    *,
    crates: Mapping[str, rust.RustCrate],
    modules: Mapping[
        tuple[str, tuple[str, ...]], tuple[rust.RustModuleBinding, ...]
    ],
    dependencies: Mapping[
        tuple[str, str], tuple[rust.RustDependencyBinding, ...]
    ],
    extern_aliases: frozenset[tuple[str, str]],
) -> rust.RustModuleBinding | None:
    specifier = item.raw.specifier
    if not specifier or specifier.endswith("::*"):
        return None
    absolute = specifier.startswith("::")
    parts = tuple(part for part in specifier.split("::") if part)
    if not parts:
        return None
    crate = crates[item.source_crate_id]

    if parts[0] == "crate":
        return _one_module_route(
            modules,
            owner_crate_id=item.source_crate_id,
            route_path=parts[1:],
            importer_crate_id=item.source_crate_id,
            importer_path=item.declaring_path,
        )
    if parts[0] == "self":
        return _one_module_route(
            modules,
            owner_crate_id=item.source_crate_id,
            route_path=(*item.declaring_path, *parts[1:]),
            importer_crate_id=item.source_crate_id,
            importer_path=item.declaring_path,
        )
    if parts[0] == "super":
        parent = list(item.declaring_path)
        offset = 0
        while offset < len(parts) and parts[offset] == "super":
            if not parent:
                return None
            parent.pop()
            offset += 1
        return _one_module_route(
            modules,
            owner_crate_id=item.source_crate_id,
            route_path=(*parent, *parts[offset:]),
            importer_crate_id=item.source_crate_id,
            importer_path=item.declaring_path,
        )

    if absolute and crate.target.edition == "2015":
        return _one_module_route(
            modules,
            owner_crate_id=item.source_crate_id,
            route_path=parts,
            importer_crate_id=item.source_crate_id,
            importer_path=item.declaring_path,
        )
    if not absolute:
        local_paths = (
            (parts,)
            if crate.target.edition == "2015"
            else ((*item.declaring_path, *parts), parts)
        )
        for local_path in local_paths:
            target = _one_module_route(
                modules,
                owner_crate_id=item.source_crate_id,
                route_path=local_path,
                importer_crate_id=item.source_crate_id,
                importer_path=item.declaring_path,
            )
            if target is not None:
                return target

    dependency_key = (item.source_crate_id, parts[0])
    if crate.target.edition == "2015" and dependency_key not in extern_aliases:
        return None
    dependency_bindings = dependencies.get(dependency_key, ())
    target_crates = {binding.target_crate_id for binding in dependency_bindings}
    if len(target_crates) != 1:
        return None
    target_crate_id = next(iter(target_crates))
    return _one_module_route(
        modules,
        owner_crate_id=target_crate_id,
        route_path=parts[1:],
        importer_crate_id=item.source_crate_id,
        importer_path=item.declaring_path,
    )


def _one_module_route(
    modules: Mapping[
        tuple[str, tuple[str, ...]], tuple[rust.RustModuleBinding, ...]
    ],
    *,
    owner_crate_id: str,
    route_path: tuple[str, ...],
    importer_crate_id: str,
    importer_path: tuple[str, ...],
) -> rust.RustModuleBinding | None:
    bindings = modules.get((owner_crate_id, route_path), ())
    visible = tuple(
        binding
        for binding in bindings
        if _route_is_visible(
            modules,
            owner_crate_id=owner_crate_id,
            route_path=route_path,
            importer_crate_id=importer_crate_id,
            importer_path=importer_path,
        )
    )
    endpoints = {
        (binding.crate_id, binding.module_path, binding.source_file)
        for binding in visible
    }
    if len(endpoints) != 1:
        return None
    target = visible[0]
    configuration: rust.RustResolutionConfiguration = target.configuration
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


def _route_is_visible(
    modules: Mapping[
        tuple[str, tuple[str, ...]], tuple[rust.RustModuleBinding, ...]
    ],
    *,
    owner_crate_id: str,
    route_path: tuple[str, ...],
    importer_crate_id: str,
    importer_path: tuple[str, ...],
) -> bool:
    external = owner_crate_id != importer_crate_id
    for depth in range(1, len(route_path) + 1):
        prefix = route_path[:depth]
        bindings = modules.get((owner_crate_id, prefix), ())
        if not bindings:
            return False
        if external:
            if not any(binding.visibility == "pub" for binding in bindings):
                return False
        elif not any(
            _visibility_allows(
                binding.visibility,
                defining_parent=prefix[:-1],
                importer_path=importer_path,
            )
            for binding in bindings
        ):
            return False
    return True


def _visibility_allows(
    visibility: str,
    *,
    defining_parent: tuple[str, ...],
    importer_path: tuple[str, ...],
) -> bool:
    if visibility in {"pub", "pub(crate)"}:
        return True
    if visibility in {"private", "pub(self)"}:
        return importer_path[: len(defining_parent)] == defining_parent
    if visibility == "pub(super)":
        scope = defining_parent[:-1]
        return importer_path[: len(scope)] == scope
    if visibility.startswith("pub(in ") and visibility.endswith(")"):
        raw_scope = visibility[len("pub(in ") : -1]
        scope = _restricted_visibility_scope(raw_scope, defining_parent)
        return scope is not None and importer_path[: len(scope)] == scope
    return False


def _restricted_visibility_scope(
    value: str,
    defining_parent: tuple[str, ...],
) -> tuple[str, ...] | None:
    parts = tuple(part for part in value.split("::") if part)
    if not parts:
        return None
    if parts[0] == "crate":
        scope = parts[1:]
    elif parts[0] == "self":
        scope = (*defining_parent, *parts[1:])
    elif parts[0] == "super":
        scope_list = list(defining_parent)
        offset = 0
        while offset < len(parts) and parts[offset] == "super":
            if not scope_list:
                return None
            scope_list.pop()
            offset += 1
        scope = (*scope_list, *parts[offset:])
    else:
        return None
    if defining_parent[: len(scope)] != scope:
        return None
    return scope


def merge_dependency_bindings(
    bindings: Sequence[rust.RustDependencyBinding],
) -> rust.RustDependencyBinding:
    first = bindings[0]
    basis_priority = {
        "cargo_package_library": 0,
        "cargo_path_dependency": 1,
        "cargo_workspace_dependency": 2,
        "rust_module_path": 3,
        "rust_module_declaration": 4,
    }
    basis = min(
        (binding.basis for binding in bindings),
        key=basis_priority.__getitem__,
    )
    return rust.RustDependencyBinding(
        source_crate_id=first.source_crate_id,
        alias=first.alias,
        target_crate_id=first.target_crate_id,
        basis=basis,
        configuration=(
            "declared_possible"
            if any(
                binding.configuration == "declared_possible"
                for binding in bindings
            )
            else "unconditional"
        ),
        control_files=tuple(sorted({
            control
            for binding in bindings
            for control in binding.control_files
        })),
    )
