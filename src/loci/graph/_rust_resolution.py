from __future__ import annotations

import re
from collections import Counter, defaultdict, deque
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import PurePosixPath
from types import MappingProxyType

from loci.parser.imports import RawImport, RustImportContext
from loci.parser.symbols import Symbol

from . import rust_crates as rust
from ._rust_aliases import (
    AliasLimitError,
    build_alias_routes,
    merge_dependency_bindings,
)
from ._rust_semantics import merge_observed_configuration


@dataclass(frozen=True, slots=True)
class _OwnedModuleFile:
    binding: rust.RustModuleBinding
    ancestry: tuple[str, ...]


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
    for crate in sorted(crates.values(), key=lambda item: item.id):
        crate_modules, crate_problems = _build_crate_modules(
            crate,
            file_nodes=file_nodes,
            observations_by_source=observations_by_source,
        )
        problems.extend(crate_problems)
        for key, bindings in crate_modules.items():
            modules[key].extend(bindings)

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
    )
    return rust.RustCrateBuild(
        index=index,
        problems=tuple(sorted(problems, key=_problem_key)),
    )


def _build_crate_modules(
    crate: rust.RustCrate,
    *,
    file_nodes: Mapping[str, Symbol],
    observations_by_source: Mapping[str, tuple[RawImport, ...]],
) -> tuple[
    dict[tuple[str, tuple[str, ...]], list[rust.RustModuleBinding]],
    list[rust.RustCrateProblem],
]:
    modules: dict[
        tuple[str, tuple[str, ...]], list[rust.RustModuleBinding]
    ] = defaultdict(list)
    problems: list[rust.RustCrateProblem] = []
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
                continue
            if candidate in owned.ancestry:
                problems.append(_problem(
                    "GRAPH_RUST_MODULE_INVALID",
                    raw.source_file,
                    "cyclic_module_source",
                ))
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

    return dict(modules), problems


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
