from __future__ import annotations

import posixpath
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from types import MappingProxyType

from loci.parser.imports import ImportUnresolvedReason, RawImport
from loci.parser.symbols import Symbol

from .contracts import JSONValue
from .javascript_modules import (
    MAX_JAVASCRIPT_RESOLUTION_CANDIDATES,
    JavaScriptImportResolution,
    JavaScriptModuleContext,
    JavaScriptModuleProblem,
    JavaScriptPackageManifest,
    JavaScriptResolutionBasis,
    JavaScriptResolutionBuild,
    JavaScriptResolutionIndex,
    TypeScriptPathMapping,
    TypeScriptProjectConfig,
    _ENCODED_SEPARATOR_RE,
    _JAVASCRIPT_EXTENSIONS,
    _TYPESCRIPT_EXTENSIONS,
    _URL_RE,
)


class _CandidateLimitError(RuntimeError):
    pass


@dataclass(slots=True)
class _CandidateBudget:
    count: int = 0

    def admit(self) -> None:
        self.count += 1
        if self.count > MAX_JAVASCRIPT_RESOLUTION_CANDIDATES:
            raise _CandidateLimitError


def build_javascript_resolution_index(
    context: JavaScriptModuleContext,
    *,
    file_nodes: Mapping[str, Symbol],
) -> JavaScriptResolutionBuild:
    """Build frozen lookups so individual import resolution performs no I/O."""
    indexed_files = frozenset(
        path
        for path, node in file_nodes.items()
        if (
            path == node.file_path
            and node.kind == "file"
            and node.language in {"javascript", "typescript"}
            and path.endswith(_JAVASCRIPT_EXTENSIONS)
        )
    )
    manifests_by_root = {manifest.root: manifest for manifest in context.manifests}
    active_roots = {
        root
        for workspace in context.workspaces
        for root in workspace.package_roots
    }
    active_by_name: dict[str, list[JavaScriptPackageManifest]] = {}
    for root in sorted(active_roots):
        manifest = manifests_by_root.get(root)
        if manifest is not None and manifest.name is not None:
            active_by_name.setdefault(manifest.name, []).append(manifest)

    problems: list[JavaScriptModuleProblem] = []
    for name, manifests in active_by_name.items():
        if len(manifests) > 1:
            problems.append(
                JavaScriptModuleProblem(
                    "GRAPH_JAVASCRIPT_PACKAGE_INVALID",
                    "Active JavaScript workspace package name is ambiguous",
                    "@javascript-packages",
                    {"reason": "duplicate_active_package_name"},
                )
            )

    owner_by_file: dict[str, JavaScriptPackageManifest] = {}
    config_by_file: dict[str, TypeScriptProjectConfig] = {}
    for path in sorted(indexed_files):
        owners = [
            manifest
            for manifest in context.manifests
            if _path_is_within(path, manifest.root)
        ]
        if owners:
            deepest = max(_path_depth(manifest.root) for manifest in owners)
            winners = [
                manifest for manifest in owners if _path_depth(manifest.root) == deepest
            ]
            if len(winners) == 1:
                owner_by_file[path] = winners[0]

        selection, ambiguous = _select_config(path, context.configs)
        if selection is not None:
            config_by_file[path] = selection
        elif ambiguous:
            problems.append(
                JavaScriptModuleProblem(
                    "GRAPH_TYPESCRIPT_CONFIG_INVALID",
                    "TypeScript project ownership is ambiguous",
                    "@typescript-projects",
                    {"reason": "ambiguous_project_ownership"},
                )
            )

    frozen_active = {
        name: tuple(sorted(manifests, key=lambda item: item.source))
        for name, manifests in sorted(active_by_name.items())
    }
    index = JavaScriptResolutionIndex(
        context=context,
        indexed_files=indexed_files,
        manifests_by_root=MappingProxyType(dict(sorted(manifests_by_root.items()))),
        active_packages_by_name=MappingProxyType(frozen_active),
        package_owner_by_file=MappingProxyType(owner_by_file),
        config_by_file=MappingProxyType(config_by_file),
    )
    return JavaScriptResolutionBuild(
        index=index,
        problems=tuple(
            sorted(problems, key=lambda item: (item.source, item.code, item.message))
        ),
    )


def resolve_javascript_import(
    raw: RawImport,
    index: JavaScriptResolutionIndex,
) -> JavaScriptImportResolution:
    """Resolve one static JS/TS observation from repository evidence only."""
    controls: set[str] = set()
    config, config_ambiguous = _select_config(raw.source_file, index.context.configs)
    owner = index.package_owner_by_file.get(raw.source_file)
    if config_ambiguous:
        return _unresolved("ambiguous", _config_controls_for_file(raw.source_file, index))
    if config is not None:
        controls.update(config.controls)
        if config.unsupported_resolution_options:
            return _unresolved("unsupported_configuration", controls)

    specifier = raw.specifier
    invalid = _invalid_specifier(specifier)
    if invalid:
        return _unresolved("invalid_specifier", controls)
    if _URL_RE.match(specifier) or specifier.startswith("node:"):
        return _unresolved("external", controls)

    request_mode = _request_mode(raw, config, owner)
    if owner is not None and _request_mode_uses_package_type(raw, config):
        controls.add(owner.source)
    budget = _CandidateBudget()
    try:
        if specifier.startswith(("./", "../")):
            return _resolve_relative(
                raw,
                index,
                config,
                request_mode,
                controls,
                budget,
            )

        attempted_contained_route = False
        if config is not None:
            path_mapping = _matching_path_mapping(specifier, config.paths)
            if path_mapping is not None:
                attempted_contained_route = True
                capture = _pattern_capture(path_mapping.pattern, specifier)
                for target_pattern in path_mapping.targets:
                    target_base = target_pattern.replace("*", capture or "")
                    target = _resolve_path_base(
                        target_base,
                        raw,
                        index,
                        config,
                        request_mode,
                        budget,
                        allow_directory=True,
                    )
                    if target is not None:
                        return _resolved(target, "compiler_paths", controls)

            if config.base_url is not None:
                attempted_contained_route = True
                base = _normalize_join(config.base_url, specifier)
                if base is not None:
                    target = _resolve_path_base(
                        base,
                        raw,
                        index,
                        config,
                        request_mode,
                        budget,
                        allow_directory=True,
                    )
                    if target is not None:
                        return _resolved(target, "compiler_base_url", controls)

        if specifier.startswith("#"):
            if owner is None:
                return _unresolved("inaccessible", controls)
            controls.add(owner.source)
            if not _package_map_enabled(config, imports_map=True):
                return _unresolved("inaccessible", controls)
            return _resolve_package_map(
                raw,
                index,
                owner,
                owner.imports,
                owner.has_imports,
                specifier,
                basis="package_imports",
                config=config,
                request_mode=request_mode,
                controls=controls,
                budget=budget,
                imports_map=True,
                allow_output_remap=True,
            )

        package_name, subpath = _package_specifier_parts(specifier)
        if package_name is None:
            return _unresolved("external", controls)

        if owner is not None and owner.name == package_name:
            controls.add(owner.source)
            if not _package_map_enabled(config, imports_map=False):
                return _unresolved("inaccessible", controls)
            return _resolve_package_map(
                raw,
                index,
                owner,
                owner.exports,
                owner.has_exports,
                "." if not subpath else f"./{subpath}",
                basis="package_self_reference",
                config=config,
                request_mode=request_mode,
                controls=controls,
                budget=budget,
                imports_map=False,
                allow_output_remap=True,
            )

        active = index.active_packages_by_name.get(package_name, ())
        if not active:
            return _unresolved(
                "not_indexed" if attempted_contained_route else "external",
                controls,
            )
        if owner is None or not _declares_dependency(owner, package_name):
            return _unresolved("external", controls)
        controls.add(owner.source)
        controls.update(_workspace_control_sources(index.context, active))
        if len(active) != 1:
            return _unresolved("ambiguous", controls)
        target_package = active[0]
        controls.add(target_package.source)
        if target_package.has_exports and _package_map_enabled(
            config,
            imports_map=False,
        ):
            return _resolve_package_map(
                raw,
                index,
                target_package,
                target_package.exports,
                True,
                "." if not subpath else f"./{subpath}",
                basis="workspace_exports",
                config=config,
                request_mode=request_mode,
                controls=controls,
                budget=budget,
                imports_map=False,
                allow_output_remap=False,
            )
        return _resolve_legacy_package(
            raw,
            index,
            target_package,
            subpath,
            config,
            request_mode,
            controls,
            budget,
        )
    except _CandidateLimitError:
        return _unresolved("unsupported_configuration", controls)


def _resolve_relative(
    raw: RawImport,
    index: JavaScriptResolutionIndex,
    config: TypeScriptProjectConfig | None,
    request_mode: str | None,
    controls: set[str],
    budget: _CandidateBudget,
) -> JavaScriptImportResolution:
    base = _relative_base(raw.source_file, raw.specifier)
    if base is None:
        return _unresolved("invalid_specifier", controls)
    if (
        config is not None
        and config.module_resolution in {"node16", "nodenext"}
        and request_mode == "import"
        and not _has_supported_extension(raw.specifier)
    ):
        return _unresolved("not_indexed", controls)
    target = _resolve_path_base(
        base,
        raw,
        index,
        config,
        request_mode,
        budget,
        allow_directory=True,
    )
    if target is not None:
        return _resolved(target, "relative_path", controls)

    if config is not None and config.root_dirs:
        for alternate in _root_dir_alternates(raw.source_file, base, config.root_dirs):
            target = _resolve_path_base(
                alternate,
                raw,
                index,
                config,
                request_mode,
                budget,
                allow_directory=True,
            )
            if target is not None:
                return _resolved(target, "compiler_root_dirs", controls)
    return _unresolved("not_indexed", controls)


def _resolve_path_base(
    base: str,
    raw: RawImport,
    index: JavaScriptResolutionIndex,
    config: TypeScriptProjectConfig | None,
    request_mode: str | None,
    budget: _CandidateBudget,
    *,
    allow_directory: bool,
) -> str | None:
    extensionless = _extensionless_allowed(config, request_mode)
    for candidate in _path_candidates(
        base,
        type_only=raw.type_only,
        module_suffixes=(config.module_suffixes if config else None),
        extensionless=extensionless,
        allow_directory=allow_directory,
    ):
        budget.admit()
        if candidate in index.indexed_files:
            return candidate
    return None


def _path_candidates(
    base: str,
    *,
    type_only: bool,
    module_suffixes: tuple[str, ...] | None,
    extensionless: bool,
    allow_directory: bool,
) -> tuple[str, ...]:
    suffixes = module_suffixes if module_suffixes is not None else ("",)
    stem: str
    extensions: tuple[str, ...]
    if base.endswith((".d.ts", ".d.mts", ".d.cts")):
        return (base,)
    written = next((extension for extension in _JAVASCRIPT_EXTENSIONS if base.endswith(extension)), None)
    if written in _TYPESCRIPT_EXTENSIONS:
        stem = base[: -len(written)]
        extensions = (written,)
    elif written in {".js", ".jsx"}:
        stem = base[: -len(written)]
        extensions = (
            (".ts", ".tsx", ".d.ts", ".js", ".jsx")
            if type_only
            else (".ts", ".tsx", ".js", ".jsx")
        )
    elif written == ".mjs":
        stem = base[:-4]
        extensions = (".mts", ".d.mts", ".mjs") if type_only else (".mts", ".mjs")
    elif written == ".cjs":
        stem = base[:-4]
        extensions = (".cts", ".d.cts", ".cjs") if type_only else (".cts", ".cjs")
    else:
        if not extensionless:
            return ()
        stem = base
        extensions = (
            (".ts", ".tsx", ".d.ts", ".js", ".jsx")
            if type_only
            else (".ts", ".tsx", ".js", ".jsx")
        )

    candidates: list[str] = []
    for suffix in suffixes:
        candidates.extend(f"{stem}{suffix}{extension}" for extension in extensions)
    if written is None and extensionless and allow_directory:
        index_base = f"{base}/index"
        for suffix in suffixes:
            candidates.extend(
                f"{index_base}{suffix}{extension}" for extension in extensions
            )
    return tuple(dict.fromkeys(candidates))


def _resolve_package_map(
    raw: RawImport,
    index: JavaScriptResolutionIndex,
    package: JavaScriptPackageManifest,
    mapping: JSONValue,
    has_mapping: bool,
    request: str,
    *,
    basis: JavaScriptResolutionBasis,
    config: TypeScriptProjectConfig | None,
    request_mode: str | None,
    controls: set[str],
    budget: _CandidateBudget,
    imports_map: bool,
    allow_output_remap: bool,
) -> JavaScriptImportResolution:
    if not has_mapping:
        return _unresolved("inaccessible", controls)
    modes = (request_mode,) if request_mode is not None else ("import", "require")
    outcomes = [
        _resolve_package_map_mode(
            raw,
            index,
            package,
            mapping,
            request,
            basis,
            config,
            mode,
            controls,
            budget,
            imports_map,
            allow_output_remap,
        )
        for mode in modes
    ]
    first = outcomes[0]
    if all(outcome == first for outcome in outcomes[1:]):
        return first
    return _unresolved("ambiguous", controls)


def _resolve_package_map_mode(
    raw: RawImport,
    index: JavaScriptResolutionIndex,
    package: JavaScriptPackageManifest,
    mapping: JSONValue,
    request: str,
    basis: JavaScriptResolutionBasis,
    config: TypeScriptProjectConfig | None,
    request_mode: str,
    controls: set[str],
    budget: _CandidateBudget,
    imports_map: bool,
    allow_output_remap: bool,
) -> JavaScriptImportResolution:
    selected, capture, reason = _select_package_map_entry(mapping, request, imports_map)
    if reason is not None:
        return _unresolved(reason, controls)
    conditions = _active_conditions(raw, config, request_mode)
    target, reason = _select_condition_target(selected, conditions)
    if reason is not None:
        return _unresolved(reason, controls)
    assert isinstance(target, str)
    if imports_map and not target.startswith("./"):
        return _unresolved("external", controls)
    target_base = _package_target_path(package.root, target, capture)
    if target_base is None:
        return _unresolved("inaccessible", controls)
    resolved = _resolve_path_base(
        target_base,
        raw,
        index,
        config,
        request_mode,
        budget,
        allow_directory=True,
    )
    if resolved is None and allow_output_remap and config is not None:
        resolved = _remap_local_output(target_base, config, raw, index, budget)
    if resolved is None:
        return _unresolved("not_indexed", controls)
    return _resolved(resolved, basis, controls)


def _select_package_map_entry(
    mapping: JSONValue,
    request: str,
    imports_map: bool,
) -> tuple[JSONValue, str | None, ImportUnresolvedReason | None]:
    if imports_map and not isinstance(mapping, dict):
        return None, None, "unsupported_configuration"
    if isinstance(mapping, list):
        return None, None, "unsupported_configuration"
    if isinstance(mapping, str) or mapping is None:
        if request not in {".", "#"} and not (imports_map and request.startswith("#")):
            return None, None, "inaccessible"
        return mapping, None, None
    if not isinstance(mapping, dict):
        return None, None, "unsupported_configuration"
    keys = tuple(mapping)
    is_subpath_map = all(
        key.startswith("#" if imports_map else ".") for key in keys
    )
    is_condition_map = all(
        not key.startswith((".", "#")) for key in keys
    )
    if not is_subpath_map and not is_condition_map:
        return None, None, "unsupported_configuration"
    if is_condition_map:
        if request != "." or imports_map:
            return None, None, "inaccessible"
        return mapping, None, None
    if request in mapping:
        return mapping[request], None, None
    matches: list[tuple[int, str, str, JSONValue]] = []
    for key, value in mapping.items():
        if key.count("*") != 1:
            continue
        prefix, suffix = key.split("*", 1)
        if request.startswith(prefix) and request.endswith(suffix):
            capture = request[len(prefix): len(request) - len(suffix) if suffix else None]
            matches.append((len(prefix), key, capture, value))
    if not matches:
        return None, None, "inaccessible"
    _, _, capture, selected = max(matches, key=lambda item: (item[0], item[1]))
    return selected, capture, None


def _select_condition_target(
    value: JSONValue,
    conditions: frozenset[str],
) -> tuple[str | None, ImportUnresolvedReason | None]:
    if value is None:
        return None, "inaccessible"
    if isinstance(value, str):
        return value, None
    if isinstance(value, list):
        return None, "unsupported_configuration"
    if not isinstance(value, dict):
        return None, "unsupported_configuration"
    for condition, target in value.items():
        if condition.startswith("types@"):
            return None, "unsupported_configuration"
        if condition in conditions:
            return _select_condition_target(target, conditions)
    return None, "inaccessible"


def _resolve_legacy_package(
    raw: RawImport,
    index: JavaScriptResolutionIndex,
    package: JavaScriptPackageManifest,
    subpath: str,
    config: TypeScriptProjectConfig | None,
    request_mode: str | None,
    controls: set[str],
    budget: _CandidateBudget,
) -> JavaScriptImportResolution:
    bases: list[str] = []
    if subpath:
        joined = _normalize_join(package.root, subpath)
        if joined is None:
            return _unresolved("inaccessible", controls)
        bases.append(joined)
    else:
        entries = (
            (package.types, package.typings, package.main)
            if raw.type_only
            else (package.main,)
        )
        for entry in entries:
            if entry:
                joined = _package_target_path(package.root, entry, None)
                if joined is None:
                    return _unresolved("inaccessible", controls)
                bases.append(joined)
        bases.append(f"{package.root}/index" if package.root != "." else "index")
    for base in bases:
        target = _resolve_path_base(
            base,
            raw,
            index,
            config,
            request_mode,
            budget,
            allow_directory=True,
        )
        if target is not None:
            return _resolved(target, "workspace_legacy_entry", controls)
    return _unresolved("not_indexed", controls)


def _remap_local_output(
    target: str,
    config: TypeScriptProjectConfig,
    raw: RawImport,
    index: JavaScriptResolutionIndex,
    budget: _CandidateBudget,
) -> str | None:
    if config.root_dir is None:
        return None
    output_roots = tuple(
        root for root in (config.out_dir, config.declaration_dir) if root is not None
    )
    for output_root in output_roots:
        if not _path_is_within(target, output_root):
            continue
        relative = _relative_to_root(target, output_root)
        if relative is None:
            continue
        source_base = _normalize_join(config.root_dir, relative)
        if source_base is None:
            continue
        for candidate in _output_source_candidates(source_base):
            budget.admit()
            if candidate in index.indexed_files:
                return candidate
    return None


def _output_source_candidates(path: str) -> tuple[str, ...]:
    if path.endswith(".d.mts"):
        return (f"{path[:-6]}.mts",)
    if path.endswith(".d.cts"):
        return (f"{path[:-6]}.cts",)
    if path.endswith(".d.ts"):
        return (f"{path[:-5]}.ts", f"{path[:-5]}.tsx")
    if path.endswith(".mjs"):
        return (f"{path[:-4]}.mts",)
    if path.endswith(".cjs"):
        return (f"{path[:-4]}.cts",)
    if path.endswith(".js"):
        return (f"{path[:-3]}.ts", f"{path[:-3]}.tsx")
    return ()


def _select_config(
    path: str,
    configs: Sequence[TypeScriptProjectConfig],
) -> tuple[TypeScriptProjectConfig | None, bool]:
    typescript = path.endswith(_TYPESCRIPT_EXTENSIONS)
    applicable = [config for config in configs if _config_applies(path, config, typescript)]
    if not applicable:
        return None, False
    deepest = max(_path_depth(config.root) for config in applicable)
    winners = [config for config in applicable if _path_depth(config.root) == deepest]
    if not typescript:
        jsconfigs = [config for config in winners if config.source.endswith("jsconfig.json")]
        if jsconfigs:
            winners = jsconfigs
    if len(winners) != 1:
        return None, True
    return winners[0], False


def _config_applies(
    path: str,
    config: TypeScriptProjectConfig,
    typescript: bool,
) -> bool:
    if not _path_is_within(path, config.root):
        return False
    if typescript and config.source.endswith("jsconfig.json"):
        return False
    if not typescript and config.source.endswith("tsconfig.json") and not config.allow_js:
        return False
    if config.files is not None and path not in config.files:
        return False
    if config.include is not None and not any(
        _glob_matches(pattern, path) for pattern in config.include
    ):
        return False
    if config.exclude is not None and any(
        _glob_matches(pattern, path) for pattern in config.exclude
    ):
        return False
    if config.files is None and config.include is None and config.out_dir is not None:
        if _path_is_within(path, config.out_dir):
            return False
    return True


def _glob_matches(pattern: str, value: str) -> bool:
    index = 0
    expression = ""
    while index < len(pattern):
        if pattern[index:index + 3] == "**/":
            expression += "(?:.*/)?"
            index += 3
        elif pattern[index:index + 2] == "**":
            expression += ".*"
            index += 2
        elif pattern[index] == "*":
            expression += "[^/]*"
            index += 1
        elif pattern[index] == "?":
            expression += "[^/]"
            index += 1
        else:
            expression += re.escape(pattern[index])
            index += 1
    return re.fullmatch(expression, value) is not None


def _matching_path_mapping(
    specifier: str,
    mappings: Sequence[TypeScriptPathMapping],
) -> TypeScriptPathMapping | None:
    matches = [
        mapping
        for mapping in mappings
        if _pattern_capture(mapping.pattern, specifier) is not None
    ]
    if not matches:
        return None
    return max(
        matches,
        key=lambda item: (len(item.pattern.split("*", 1)[0]), -mappings.index(item)),
    )


def _pattern_capture(pattern: str, value: str) -> str | None:
    if "*" not in pattern:
        return "" if pattern == value else None
    prefix, suffix = pattern.split("*", 1)
    if not value.startswith(prefix) or not value.endswith(suffix):
        return None
    return value[len(prefix): len(value) - len(suffix) if suffix else None]


def _request_mode(
    raw: RawImport,
    config: TypeScriptProjectConfig | None,
    owner: JavaScriptPackageManifest | None,
) -> str | None:
    suffix = Path(raw.source_file).suffix
    if suffix in {".mts", ".mjs"}:
        return "import"
    if suffix in {".cts", ".cjs"}:
        return "require"
    if config is None:
        return None
    if config.module_resolution == "bundler":
        return "import"
    if config.module_resolution in {"node10", "classic"}:
        return "require"
    if config.module_resolution in {"node16", "nodenext"}:
        if owner is not None and owner.package_type == "module":
            return "import"
        if owner is not None and owner.package_type == "commonjs":
            return "require"
        if config.module in {"es2015", "es2020", "es2022", "esnext", "preserve"}:
            return "import"
        if config.module == "commonjs":
            return "require"
    return None


def _request_mode_uses_package_type(
    raw: RawImport,
    config: TypeScriptProjectConfig | None,
) -> bool:
    return (
        Path(raw.source_file).suffix in {".ts", ".tsx", ".js", ".jsx"}
        and config is not None
        and config.module_resolution in {"node16", "nodenext"}
    )


def _active_conditions(
    raw: RawImport,
    config: TypeScriptProjectConfig | None,
    request_mode: str,
) -> frozenset[str]:
    values = set(config.custom_conditions if config else ())
    values.add(request_mode)
    values.add("default")
    if raw.type_only:
        values.add("types")
    if config is not None and config.module_resolution in {"node16", "nodenext"}:
        values.add("node")
    return frozenset(values)


def _package_map_enabled(
    config: TypeScriptProjectConfig | None,
    *,
    imports_map: bool,
) -> bool:
    if config is None:
        return True
    configured = (
        config.resolve_package_json_imports
        if imports_map
        else config.resolve_package_json_exports
    )
    if configured is not None:
        return configured
    return config.module_resolution not in {"node10", "classic"}


def _extensionless_allowed(
    config: TypeScriptProjectConfig | None,
    request_mode: str | None,
) -> bool:
    if config is None:
        return True
    if config.module_resolution in {None, "bundler", "node10", "classic"}:
        return True
    return request_mode == "require"


def _relative_base(source_file: str, specifier: str) -> str | None:
    return _normalize_join(PurePosixPath(source_file).parent.as_posix(), specifier)


def _normalize_join(root: str, value: str) -> str | None:
    normalized = posixpath.normpath(posixpath.join(root, value))
    if normalized in {"", ".", ".."} or normalized.startswith("../"):
        return None
    return normalized


def _invalid_specifier(specifier: str) -> bool:
    return (
        not specifier
        or "\\" in specifier
        or specifier.startswith("/")
        or _ENCODED_SEPARATOR_RE.search(specifier) is not None
        or "\x00" in specifier
    )


def _has_supported_extension(specifier: str) -> bool:
    return specifier.endswith(_JAVASCRIPT_EXTENSIONS)


def _root_dir_alternates(
    source_file: str,
    base: str,
    roots: Sequence[str],
) -> tuple[str, ...]:
    source_root = next(
        (root for root in roots if _path_is_within(source_file, root)),
        None,
    )
    if source_root is None or not _path_is_within(base, source_root):
        return ()
    relative = _relative_to_root(base, source_root)
    if relative is None:
        return ()
    return tuple(
        alternate
        for root in roots
        if root != source_root
        for alternate in [_normalize_join(root, relative)]
        if alternate is not None
    )


def _package_target_path(
    package_root: str,
    target: str,
    capture: str | None,
) -> str | None:
    if not target.startswith("./") or _ENCODED_SEPARATOR_RE.search(target):
        return None
    value = target.replace("*", capture or "")
    parts = PurePosixPath(value).parts
    if ".." in parts or "node_modules" in parts or "\\" in value:
        return None
    return _normalize_join(package_root, value[2:])


def _package_specifier_parts(specifier: str) -> tuple[str | None, str]:
    parts = specifier.split("/")
    if specifier.startswith("@"):
        if len(parts) < 2 or not parts[0] or not parts[1]:
            return None, ""
        return "/".join(parts[:2]), "/".join(parts[2:])
    if not parts[0] or parts[0] in {".", ".."}:
        return None, ""
    return parts[0], "/".join(parts[1:])


def _declares_dependency(
    owner: JavaScriptPackageManifest,
    package_name: str,
) -> bool:
    return any(
        package_name in dependencies
        for dependencies in (
            owner.dependencies,
            owner.dev_dependencies,
            owner.peer_dependencies,
            owner.optional_dependencies,
        )
    )


def _workspace_control_sources(
    context: JavaScriptModuleContext,
    packages: Sequence[JavaScriptPackageManifest],
) -> set[str]:
    roots = {package.root for package in packages}
    return {
        workspace.source
        for workspace in context.workspaces
        if roots.intersection(workspace.package_roots)
    }


def _path_is_within(path: str, root: str) -> bool:
    if root == ".":
        return not path.startswith("../")
    return path == root or path.startswith(f"{root}/")


def _relative_to_root(path: str, root: str) -> str | None:
    if not _path_is_within(path, root):
        return None
    if root == ".":
        return path
    if path == root:
        return ""
    return path[len(root) + 1:]


def _path_depth(path: str) -> int:
    return 0 if path == "." else len(PurePosixPath(path).parts)


def _config_controls_for_file(
    path: str,
    index: JavaScriptResolutionIndex,
) -> set[str]:
    return {
        control
        for config in index.context.configs
        if _config_applies(path, config, path.endswith(_TYPESCRIPT_EXTENSIONS))
        for control in config.controls
    }


def _resolved(
    target: str,
    basis: JavaScriptResolutionBasis,
    controls: Sequence[str] | set[str],
) -> JavaScriptImportResolution:
    return JavaScriptImportResolution(
        target,
        basis,
        tuple(sorted(set(controls))),
        None,
    )


def _unresolved(
    reason: ImportUnresolvedReason,
    controls: Sequence[str] | set[str],
) -> JavaScriptImportResolution:
    return JavaScriptImportResolution(
        None,
        None,
        tuple(sorted(set(controls))),
        reason,
    )

