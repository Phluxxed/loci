from __future__ import annotations

import hashlib
import json
import math
import os
import posixpath
import re
import stat
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from types import MappingProxyType
from typing import Literal, TypeAlias

import yaml
from yaml.tokens import AliasToken, AnchorToken, TagToken

from loci.parser.imports import ImportUnresolvedReason, RawImport
from loci.parser.symbols import Symbol

from .contracts import GraphContractError, JSONValue
from .profiles import read_contained_file


MAX_JAVASCRIPT_CONTROL_BYTES = 1_048_576
MAX_JAVASCRIPT_CONTROL_FILES = 10_000
MAX_JAVASCRIPT_JSON_DEPTH = 64
MAX_JAVASCRIPT_WORKSPACE_PATTERNS = 1_000
MAX_JAVASCRIPT_WORKSPACE_PACKAGES = 10_000
MAX_TYPESCRIPT_CONFIG_EXTENDS_DEPTH = 32
MAX_TYPESCRIPT_PATH_PATTERNS = 1_000
MAX_TYPESCRIPT_PATH_TARGETS = 10_000
MAX_JAVASCRIPT_PACKAGE_MAP_DEPTH = 32
MAX_JAVASCRIPT_RESOLUTION_CANDIDATES = 256

JavaScriptResolutionBasis: TypeAlias = Literal[
    "relative_path",
    "compiler_paths",
    "compiler_base_url",
    "compiler_root_dirs",
    "package_imports",
    "package_self_reference",
    "workspace_exports",
    "workspace_legacy_entry",
]
JavaScriptModuleProblemCode: TypeAlias = Literal[
    "GRAPH_JAVASCRIPT_PACKAGE_INVALID",
    "GRAPH_JAVASCRIPT_WORKSPACE_INVALID",
    "GRAPH_TYPESCRIPT_CONFIG_INVALID",
    "GRAPH_JAVASCRIPT_INDEX_LIMIT_EXCEEDED",
]

_CONFIG_NAMES = frozenset({"tsconfig.json", "jsconfig.json"})
_DEPENDENCY_FIELDS = (
    "dependencies",
    "devDependencies",
    "peerDependencies",
    "optionalDependencies",
)
_MODULE_RESOLUTIONS = frozenset(
    {"node16", "nodenext", "bundler", "node10", "classic"}
)
_URL_RE = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*:")
_ENCODED_SEPARATOR_RE = re.compile(r"%2f|%5c", re.IGNORECASE)
_JAVASCRIPT_EXTENSIONS = (
    ".ts",
    ".tsx",
    ".mts",
    ".cts",
    ".js",
    ".jsx",
    ".mjs",
    ".cjs",
)
_TYPESCRIPT_EXTENSIONS = (".ts", ".tsx", ".mts", ".cts")


@dataclass(frozen=True, slots=True)
class JavaScriptPackageManifest:
    source: str
    root: str
    name: str | None
    package_type: Literal["module", "commonjs"] | None
    workspaces: tuple[str, ...]
    dependencies: Mapping[str, str]
    dev_dependencies: Mapping[str, str]
    peer_dependencies: Mapping[str, str]
    optional_dependencies: Mapping[str, str]
    main: str | None
    types: str | None
    typings: str | None
    has_exports: bool
    exports: JSONValue
    has_imports: bool
    imports: JSONValue


@dataclass(frozen=True, slots=True)
class TypeScriptPathMapping:
    pattern: str
    targets: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class TypeScriptProjectConfig:
    source: str
    root: str
    controls: tuple[str, ...]
    module: str | None
    module_resolution: Literal[
        "node16", "nodenext", "bundler", "node10", "classic"
    ] | None
    allow_js: bool
    paths: tuple[TypeScriptPathMapping, ...]
    base_url: str | None
    root_dirs: tuple[str, ...]
    module_suffixes: tuple[str, ...] | None
    custom_conditions: tuple[str, ...]
    resolve_package_json_exports: bool | None
    resolve_package_json_imports: bool | None
    root_dir: str | None
    out_dir: str | None
    declaration_dir: str | None
    files: tuple[str, ...] | None
    include: tuple[str, ...] | None
    exclude: tuple[str, ...] | None
    unsupported_resolution_options: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class JavaScriptWorkspace:
    source: str
    root: str
    package_roots: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class JavaScriptModuleProblem:
    code: JavaScriptModuleProblemCode
    message: str
    source: str
    details: dict[str, JSONValue]


@dataclass(frozen=True, slots=True)
class JavaScriptModuleContext:
    manifests: tuple[JavaScriptPackageManifest, ...]
    workspaces: tuple[JavaScriptWorkspace, ...]
    configs: tuple[TypeScriptProjectConfig, ...]


@dataclass(frozen=True, slots=True)
class JavaScriptModuleLoad:
    context: JavaScriptModuleContext
    input_hashes: dict[str, str]
    problems: tuple[JavaScriptModuleProblem, ...]


@dataclass(frozen=True, slots=True)
class JavaScriptResolutionIndex:
    context: JavaScriptModuleContext
    indexed_files: frozenset[str]
    manifests_by_root: Mapping[str, JavaScriptPackageManifest]
    active_packages_by_name: Mapping[
        str, tuple[JavaScriptPackageManifest, ...]
    ]
    package_owner_by_file: Mapping[str, JavaScriptPackageManifest]
    config_by_file: Mapping[str, TypeScriptProjectConfig]


@dataclass(frozen=True, slots=True)
class JavaScriptResolutionBuild:
    index: JavaScriptResolutionIndex
    problems: tuple[JavaScriptModuleProblem, ...]


@dataclass(frozen=True, slots=True)
class JavaScriptImportResolution:
    target_file: str | None
    basis: JavaScriptResolutionBasis | None
    control_files: tuple[str, ...]
    unresolved_reason: ImportUnresolvedReason | None

    def __post_init__(self) -> None:
        if (self.target_file is None) == (self.unresolved_reason is None):
            raise ValueError("resolution requires exactly one target or reason")
        if self.target_file is not None and self.basis is None:
            raise ValueError("resolved JavaScript import requires a basis")
        if self.target_file is None and self.basis is not None:
            raise ValueError("unresolved JavaScript import must not have a basis")
        if self.control_files != tuple(sorted(set(self.control_files))):
            raise ValueError("resolution controls must be unique and sorted")


class _CandidateLimitError(RuntimeError):
    pass


@dataclass(slots=True)
class _CandidateBudget:
    count: int = 0

    def admit(self) -> None:
        self.count += 1
        if self.count > MAX_JAVASCRIPT_RESOLUTION_CANDIDATES:
            raise _CandidateLimitError


@dataclass(frozen=True, slots=True)
class _ConfigBuild:
    config: TypeScriptProjectConfig
    module_resolution_explicit: bool


class _JavaScriptControlError(ValueError):
    def __init__(
        self,
        reason: str,
        *,
        line: int | None = None,
        limit: int | None = None,
        limit_error: bool = False,
    ) -> None:
        super().__init__(reason)
        self.reason = reason
        self.line = line
        self.limit = limit
        self.limit_error = limit_error


class _DuplicateKeyError(ValueError):
    pass


class _ControlLoader:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.input_hashes: dict[str, str] = {}
        self.raw_configs: dict[str, Mapping[str, object]] = {}
        self.config_builds: dict[str, _ConfigBuild] = {}

    def read(self, path: Path, *, kind: str) -> tuple[bytes, str]:
        source = _candidate_source(self.root, path)
        if source not in self.input_hashes and len(self.input_hashes) >= MAX_JAVASCRIPT_CONTROL_FILES:
            raise _JavaScriptControlError(
                "control_file_limit_exceeded",
                limit=MAX_JAVASCRIPT_CONTROL_FILES,
                limit_error=True,
            )
        try:
            data, source = _read_control_candidate(self.root, path)
        except _JavaScriptControlError as exc:
            self.input_hashes[source] = _sentinel_hash(kind, exc.reason)
            raise
        self.input_hashes[source] = hashlib.sha256(data).hexdigest()
        return data, source

    def load_config(self, path: Path, stack: tuple[str, ...] = ()) -> _ConfigBuild:
        source = _candidate_source(self.root, path)
        if source in self.config_builds:
            return self.config_builds[source]
        if source in stack:
            raise _JavaScriptControlError("config_cycle")
        if len(stack) >= MAX_TYPESCRIPT_CONFIG_EXTENDS_DEPTH:
            raise _JavaScriptControlError(
                "extends_depth_exceeded",
                limit=MAX_TYPESCRIPT_CONFIG_EXTENDS_DEPTH,
                limit_error=True,
            )

        data, source = self.read(path, kind="config")
        raw = _parse_json_control(data, jsonc=True)
        self.raw_configs[source] = raw
        base: _ConfigBuild | None = None
        extends = raw.get("extends")
        if extends is not None:
            if not isinstance(extends, str) or not extends:
                raise _JavaScriptControlError("invalid_extends")
            base_path = _resolve_extends_path(self.root, source, extends)
            base = self.load_config(base_path, (*stack, source))

        built = _build_config(source, raw, base)
        self.config_builds[source] = built
        return built


def load_javascript_module_context(
    repo_path: Path,
    control_candidates: Sequence[Path],
) -> JavaScriptModuleLoad:
    """Load bounded repository-local JavaScript controls without executing tools."""
    root = repo_path.resolve(strict=True)
    candidates = sorted(
        {_candidate_source(root, path): path for path in control_candidates}.items()
    )
    if len(candidates) > MAX_JAVASCRIPT_CONTROL_FILES:
        problem = _problem(
            "index",
            "@javascript-controls",
            _JavaScriptControlError(
                "control_file_limit_exceeded",
                limit=MAX_JAVASCRIPT_CONTROL_FILES,
                limit_error=True,
            ),
        )
        return JavaScriptModuleLoad(_empty_context(), {}, (problem,))

    loader = _ControlLoader(root)
    manifests: list[JavaScriptPackageManifest] = []
    workspace_controls: list[tuple[str, str, tuple[str, ...], bool]] = []
    configs: list[TypeScriptProjectConfig] = []
    problems: list[JavaScriptModuleProblem] = []

    for source, path in candidates:
        kind = _control_kind(path)
        if kind is None:
            continue
        try:
            if kind == "package":
                data, source = loader.read(path, kind=kind)
                manifest = _parse_package_manifest(source, data)
                manifests.append(manifest)
                if manifest.workspaces:
                    workspace_controls.append(
                        (source, manifest.root, manifest.workspaces, False)
                    )
            elif kind == "workspace":
                data, source = loader.read(path, kind=kind)
                patterns = _parse_pnpm_workspace(data)
                workspace_controls.append(
                    (source, _control_root(source), patterns, True)
                )
            else:
                configs.append(loader.load_config(path).config)
        except _JavaScriptControlError as exc:
            problems.append(_problem(kind, source, exc))

    if any(problem.code == "GRAPH_JAVASCRIPT_INDEX_LIMIT_EXCEEDED" for problem in problems):
        context = _empty_context()
    else:
        try:
            workspaces = _build_workspaces(workspace_controls, manifests)
            context = JavaScriptModuleContext(
                manifests=tuple(sorted(manifests, key=lambda item: item.source)),
                workspaces=workspaces,
                configs=tuple(sorted(configs, key=lambda item: item.source)),
            )
        except _JavaScriptControlError as exc:
            context = _empty_context()
            problems.append(_problem("workspace", "@javascript-workspaces", exc))

    return JavaScriptModuleLoad(
        context=context,
        input_hashes=dict(sorted(loader.input_hashes.items())),
        problems=tuple(
            sorted(problems, key=lambda item: (item.source, item.code, item.message))
        ),
    )


def _parse_package_manifest(source: str, data: bytes) -> JavaScriptPackageManifest:
    raw = _parse_json_control(data, jsonc=False)
    root = _control_root(source)
    name = _optional_nonempty_string(raw, "name", "invalid_name")
    package_type = raw.get("type")
    if package_type not in (None, "module", "commonjs"):
        raise _JavaScriptControlError("invalid_package_type")
    workspaces = _string_tuple(raw.get("workspaces", ()), "invalid_workspaces")
    if len(workspaces) > MAX_JAVASCRIPT_WORKSPACE_PATTERNS:
        raise _JavaScriptControlError(
            "workspace_pattern_limit_exceeded",
            limit=MAX_JAVASCRIPT_WORKSPACE_PATTERNS,
            limit_error=True,
        )
    for pattern in workspaces:
        _validate_workspace_pattern(pattern, allow_exclusion=False)

    dependency_maps = {
        field: _string_mapping(raw.get(field, {}), f"invalid_{_snake(field)}")
        for field in _DEPENDENCY_FIELDS
    }
    main = _optional_nonempty_string(raw, "main", "invalid_main")
    types = _optional_nonempty_string(raw, "types", "invalid_types")
    typings = _optional_nonempty_string(raw, "typings", "invalid_typings")
    return JavaScriptPackageManifest(
        source=source,
        root=root,
        name=name,
        package_type=package_type,
        workspaces=workspaces,
        dependencies=MappingProxyType(dependency_maps["dependencies"]),
        dev_dependencies=MappingProxyType(dependency_maps["devDependencies"]),
        peer_dependencies=MappingProxyType(dependency_maps["peerDependencies"]),
        optional_dependencies=MappingProxyType(
            dependency_maps["optionalDependencies"]
        ),
        main=main,
        types=types,
        typings=typings,
        has_exports="exports" in raw,
        exports=raw.get("exports"),
        has_imports="imports" in raw,
        imports=raw.get("imports"),
    )


def _parse_pnpm_workspace(data: bytes) -> tuple[str, ...]:
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise _JavaScriptControlError("invalid_utf8") from exc
    try:
        for token in yaml.scan(text):
            if isinstance(token, (AliasToken, AnchorToken, TagToken)):
                raise _JavaScriptControlError("yaml_alias_or_anchor")
        raw = yaml.safe_load(text)
    except _JavaScriptControlError:
        raise
    except yaml.YAMLError as exc:
        line = getattr(getattr(exc, "problem_mark", None), "line", None)
        raise _JavaScriptControlError(
            "invalid_yaml",
            line=None if line is None else line + 1,
        ) from exc
    if not isinstance(raw, dict) or set(raw) != {"packages"}:
        raise _JavaScriptControlError("invalid_workspace_shape")
    if "<<" in raw:
        raise _JavaScriptControlError("yaml_alias_or_anchor")
    patterns = _string_tuple(raw["packages"], "invalid_packages")
    if len(patterns) > MAX_JAVASCRIPT_WORKSPACE_PATTERNS:
        raise _JavaScriptControlError(
            "workspace_pattern_limit_exceeded",
            limit=MAX_JAVASCRIPT_WORKSPACE_PATTERNS,
            limit_error=True,
        )
    for pattern in patterns:
        _validate_workspace_pattern(pattern, allow_exclusion=True)
    return patterns


def _build_workspaces(
    controls: Sequence[tuple[str, str, tuple[str, ...], bool]],
    manifests: Sequence[JavaScriptPackageManifest],
) -> tuple[JavaScriptWorkspace, ...]:
    roots = tuple(manifest.root for manifest in manifests)
    workspaces: list[JavaScriptWorkspace] = []
    for source, workspace_root, patterns, include_root in controls:
        selected: set[str] = {workspace_root} if include_root else set()
        positive = [pattern for pattern in patterns if not pattern.startswith("!")]
        negative = [pattern[1:] for pattern in patterns if pattern.startswith("!")]
        for pattern in positive:
            selected.update(
                root
                for root in roots
                if _workspace_pattern_matches(workspace_root, pattern, root)
            )
        for pattern in negative:
            selected.difference_update(
                root
                for root in tuple(selected)
                if _workspace_pattern_matches(workspace_root, pattern, root)
            )
        if len(selected) > MAX_JAVASCRIPT_WORKSPACE_PACKAGES:
            raise _JavaScriptControlError(
                "workspace_package_limit_exceeded",
                limit=MAX_JAVASCRIPT_WORKSPACE_PACKAGES,
                limit_error=True,
            )
        workspaces.append(
            JavaScriptWorkspace(
                source=source,
                root=workspace_root,
                package_roots=tuple(sorted(selected)),
            )
        )
    return tuple(sorted(workspaces, key=lambda item: item.source))


def _build_config(
    source: str,
    raw: Mapping[str, object],
    base: _ConfigBuild | None,
) -> _ConfigBuild:
    root = _control_root(source)
    base_config = base.config if base is not None else None
    compiler = raw.get("compilerOptions", {})
    if not isinstance(compiler, dict):
        raise _JavaScriptControlError("invalid_compiler_options")

    module = base_config.module if base_config else None
    if "module" in compiler:
        module = _lower_string(compiler["module"], "invalid_module")

    resolution_explicit = base.module_resolution_explicit if base else False
    module_resolution = base_config.module_resolution if base_config else None
    unsupported = set(base_config.unsupported_resolution_options if base_config else ())
    if "moduleResolution" in compiler:
        resolution_explicit = True
        candidate = _lower_string(
            compiler["moduleResolution"], "invalid_module_resolution"
        )
        candidate = "node10" if candidate == "node" else candidate
        if candidate not in _MODULE_RESOLUTIONS:
            module_resolution = None
            unsupported.add("moduleResolution")
        else:
            module_resolution = candidate  # type: ignore[assignment]
    elif not resolution_explicit:
        module_resolution = _implied_module_resolution(module)

    allow_js = base_config.allow_js if base_config else source.endswith("jsconfig.json")
    if "allowJs" in compiler:
        allow_js = _boolean(compiler["allowJs"], "invalid_allow_js")

    base_url = base_config.base_url if base_config else None
    if "baseUrl" in compiler:
        base_url = _config_path(root, compiler["baseUrl"], "invalid_base_url")

    paths = base_config.paths if base_config else ()
    if "paths" in compiler:
        paths = _parse_paths(compiler["paths"], base_url or root)

    root_dirs = base_config.root_dirs if base_config else ()
    if "rootDirs" in compiler:
        root_dirs = _config_paths(root, compiler["rootDirs"], "invalid_root_dirs")

    module_suffixes = base_config.module_suffixes if base_config else None
    if "moduleSuffixes" in compiler:
        module_suffixes = _string_tuple(
            compiler["moduleSuffixes"], "invalid_module_suffixes", allow_empty=True
        )

    custom_conditions = base_config.custom_conditions if base_config else ()
    if "customConditions" in compiler:
        custom_conditions = _string_tuple(
            compiler["customConditions"], "invalid_custom_conditions"
        )

    exports_flag = base_config.resolve_package_json_exports if base_config else None
    if "resolvePackageJsonExports" in compiler:
        exports_flag = _boolean(
            compiler["resolvePackageJsonExports"],
            "invalid_resolve_package_json_exports",
        )
    imports_flag = base_config.resolve_package_json_imports if base_config else None
    if "resolvePackageJsonImports" in compiler:
        imports_flag = _boolean(
            compiler["resolvePackageJsonImports"],
            "invalid_resolve_package_json_imports",
        )

    root_dir = _inherited_config_path(base_config, "root_dir")
    out_dir = _inherited_config_path(base_config, "out_dir")
    declaration_dir = _inherited_config_path(base_config, "declaration_dir")
    if "rootDir" in compiler:
        root_dir = _config_path(root, compiler["rootDir"], "invalid_root_dir")
    if "outDir" in compiler:
        out_dir = _config_path(root, compiler["outDir"], "invalid_out_dir")
    if "declarationDir" in compiler:
        declaration_dir = _config_path(
            root, compiler["declarationDir"], "invalid_declaration_dir"
        )

    for option in ("plugins",):
        if compiler.get(option):
            unsupported.add(option)

    files = base_config.files if base_config else None
    include = base_config.include if base_config else None
    exclude = base_config.exclude if base_config else None
    if "files" in raw:
        files = _config_paths(root, raw["files"], "invalid_files")
    if "include" in raw:
        include = _config_paths(root, raw["include"], "invalid_include")
    if "exclude" in raw:
        exclude = _config_paths(root, raw["exclude"], "invalid_exclude")
    _validate_references(raw.get("references"))

    controls = (*base_config.controls, source) if base_config else (source,)
    config = TypeScriptProjectConfig(
        source=source,
        root=root,
        controls=tuple(dict.fromkeys(controls)),
        module=module,
        module_resolution=module_resolution,
        allow_js=allow_js,
        paths=paths,
        base_url=base_url,
        root_dirs=root_dirs,
        module_suffixes=module_suffixes,
        custom_conditions=custom_conditions,
        resolve_package_json_exports=exports_flag,
        resolve_package_json_imports=imports_flag,
        root_dir=root_dir,
        out_dir=out_dir,
        declaration_dir=declaration_dir,
        files=files,
        include=include,
        exclude=exclude,
        unsupported_resolution_options=tuple(sorted(unsupported)),
    )
    return _ConfigBuild(config, resolution_explicit)


def _parse_paths(value: object, origin: str) -> tuple[TypeScriptPathMapping, ...]:
    if not isinstance(value, dict):
        raise _JavaScriptControlError("invalid_paths")
    if len(value) > MAX_TYPESCRIPT_PATH_PATTERNS:
        raise _JavaScriptControlError(
            "path_pattern_limit_exceeded",
            limit=MAX_TYPESCRIPT_PATH_PATTERNS,
            limit_error=True,
        )
    mappings: list[TypeScriptPathMapping] = []
    target_count = 0
    for pattern, raw_targets in value.items():
        if not isinstance(pattern, str) or not pattern or pattern.count("*") > 1:
            raise _JavaScriptControlError("invalid_path_pattern")
        targets = _string_tuple(raw_targets, "invalid_path_targets")
        target_count += len(targets)
        if target_count > MAX_TYPESCRIPT_PATH_TARGETS:
            raise _JavaScriptControlError(
                "path_target_limit_exceeded",
                limit=MAX_TYPESCRIPT_PATH_TARGETS,
                limit_error=True,
            )
        mappings.append(
            TypeScriptPathMapping(
                pattern,
                tuple(
                    _normalize_repo_path(origin, target, "invalid_path_target")
                    for target in targets
                ),
            )
        )
    return tuple(mappings)


def _parse_json_control(data: bytes, *, jsonc: bool) -> Mapping[str, object]:
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise _JavaScriptControlError("invalid_utf8") from exc
    if jsonc:
        text = _strip_jsonc(text)
    try:
        value = json.loads(
            text,
            object_pairs_hook=_unique_object,
            parse_constant=_reject_json_constant,
        )
    except _DuplicateKeyError as exc:
        raise _JavaScriptControlError("duplicate_key") from exc
    except _JavaScriptControlError:
        raise
    except (json.JSONDecodeError, ValueError) as exc:
        raise _JavaScriptControlError("invalid_json") from exc
    _validate_json_value(value, 1)
    if not isinstance(value, dict):
        raise _JavaScriptControlError("invalid_control_shape")
    return value


def _strip_jsonc(text: str) -> str:
    without_comments: list[str] = []
    index = 0
    in_string = False
    escaped = False
    while index < len(text):
        char = text[index]
        if in_string:
            without_comments.append(char)
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            index += 1
            continue
        if char == '"':
            in_string = True
            without_comments.append(char)
            index += 1
            continue
        if char == "/" and index + 1 < len(text) and text[index + 1] == "/":
            index += 2
            while index < len(text) and text[index] not in "\r\n":
                without_comments.append(" ")
                index += 1
            continue
        if char == "/" and index + 1 < len(text) and text[index + 1] == "*":
            index += 2
            closed = False
            while index < len(text):
                if text[index:index + 2] == "*/":
                    index += 2
                    closed = True
                    break
                without_comments.append("\n" if text[index] == "\n" else " ")
                index += 1
            if not closed:
                raise _JavaScriptControlError("unterminated_comment")
            continue
        without_comments.append(char)
        index += 1

    chars = without_comments
    result: list[str] = []
    in_string = False
    escaped = False
    for index, char in enumerate(chars):
        if in_string:
            result.append(char)
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
            result.append(char)
            continue
        if char == ",":
            lookahead = index + 1
            while lookahead < len(chars) and chars[lookahead].isspace():
                lookahead += 1
            if lookahead < len(chars) and chars[lookahead] in "]}":
                result.append(" ")
                continue
        result.append(char)
    return "".join(result)


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise _DuplicateKeyError(key)
        result[key] = value
    return result


def _reject_json_constant(value: str) -> object:
    raise _JavaScriptControlError("non_finite_number")


def _validate_json_value(value: object, depth: int) -> None:
    if depth > MAX_JAVASCRIPT_JSON_DEPTH:
        raise _JavaScriptControlError(
            "json_depth_exceeded",
            limit=MAX_JAVASCRIPT_JSON_DEPTH,
        )
    if isinstance(value, float) and not math.isfinite(value):
        raise _JavaScriptControlError("non_finite_number")
    if isinstance(value, dict):
        for child in value.values():
            _validate_json_value(child, depth + 1)
    elif isinstance(value, list):
        for child in value:
            _validate_json_value(child, depth + 1)


def _read_control_candidate(root: Path, path: Path) -> tuple[bytes, str]:
    candidate = path if path.is_absolute() else root / path
    source = _candidate_source(root, candidate)
    try:
        lexical = Path(os.path.abspath(candidate))
        lexical.relative_to(root)
    except ValueError as exc:
        raise _JavaScriptControlError("outside_repository") from exc
    try:
        candidate_stat = os.lstat(lexical)
    except OSError as exc:
        raise _JavaScriptControlError("unreadable") from exc
    if stat.S_ISLNK(candidate_stat.st_mode):
        raise _JavaScriptControlError("symlink")
    if not stat.S_ISREG(candidate_stat.st_mode):
        raise _JavaScriptControlError("not_regular")
    if candidate_stat.st_size > MAX_JAVASCRIPT_CONTROL_BYTES:
        raise _JavaScriptControlError(
            "control_file_too_large",
            limit=MAX_JAVASCRIPT_CONTROL_BYTES,
            limit_error=True,
        )
    try:
        lexical.resolve(strict=True).relative_to(root)
    except (OSError, ValueError) as exc:
        raise _JavaScriptControlError("outside_repository") from exc
    try:
        return read_contained_file(
            root,
            lexical,
            record="JavaScript control file",
            max_bytes=MAX_JAVASCRIPT_CONTROL_BYTES,
        )
    except GraphContractError as exc:
        if exc.details.get("limit") == MAX_JAVASCRIPT_CONTROL_BYTES:
            raise _JavaScriptControlError(
                "control_file_too_large",
                limit=MAX_JAVASCRIPT_CONTROL_BYTES,
                limit_error=True,
            ) from exc
        raise _JavaScriptControlError("unsafe_or_unreadable") from exc


def _resolve_extends_path(root: Path, source: str, value: str) -> Path:
    if _URL_RE.match(value):
        raise _JavaScriptControlError("url_extends")
    if "\\" in value:
        raise _JavaScriptControlError("invalid_extends")
    if value.startswith("/"):
        raise _JavaScriptControlError("absolute_extends")
    if not value.startswith(("./", "../")):
        raise _JavaScriptControlError("package_extends")
    base = PurePosixPath(_control_root(source))
    normalized = posixpath.normpath(posixpath.join(base.as_posix(), value))
    if normalized == ".." or normalized.startswith("../"):
        raise _JavaScriptControlError("extends_outside_repository")
    candidate = root / normalized
    choices = [candidate]
    if candidate.suffix != ".json":
        choices.append(Path(f"{candidate}.json"))
    choices.append(candidate / "tsconfig.json")
    for choice in choices:
        try:
            os.lstat(choice)
        except OSError:
            continue
        return choice
    return choices[1] if len(choices) > 1 else choices[0]


def _control_kind(path: Path) -> str | None:
    if path.name == "package.json":
        return "package"
    if path.name == "pnpm-workspace.yaml":
        return "workspace"
    if path.name in _CONFIG_NAMES:
        return "config"
    return None


def _control_root(source: str) -> str:
    parent = PurePosixPath(source).parent.as_posix()
    return parent if parent else "."


def _candidate_source(root: Path, path: Path) -> str:
    candidate = path if path.is_absolute() else root / path
    try:
        return Path(os.path.abspath(candidate)).relative_to(root).as_posix()
    except ValueError:
        return f"@outside/{path.name}"


def _sentinel_hash(kind: str, reason: str) -> str:
    return hashlib.sha256(f"loci-javascript-{kind}:{reason}".encode()).hexdigest()


def _problem(
    kind: str,
    source: str,
    error: _JavaScriptControlError,
) -> JavaScriptModuleProblem:
    if error.limit_error:
        code: JavaScriptModuleProblemCode = "GRAPH_JAVASCRIPT_INDEX_LIMIT_EXCEEDED"
    elif kind == "workspace":
        code = "GRAPH_JAVASCRIPT_WORKSPACE_INVALID"
    elif kind == "config":
        code = "GRAPH_TYPESCRIPT_CONFIG_INVALID"
    else:
        code = "GRAPH_JAVASCRIPT_PACKAGE_INVALID"
    details: dict[str, JSONValue] = {"reason": error.reason}
    if error.line is not None:
        details["line"] = error.line
    if error.limit is not None:
        details["limit"] = error.limit
    messages = {
        "package": "JavaScript package control file is invalid",
        "workspace": "JavaScript workspace control file is invalid",
        "config": "TypeScript project control file is invalid",
        "index": "JavaScript control-file limit was exceeded",
    }
    return JavaScriptModuleProblem(
        code,
        messages.get(kind, "JavaScript module context is invalid"),
        source,
        details,
    )


def _empty_context() -> JavaScriptModuleContext:
    return JavaScriptModuleContext((), (), ())


def _string_tuple(
    value: object,
    reason: str,
    *,
    allow_empty: bool = False,
) -> tuple[str, ...]:
    if not isinstance(value, list) and not isinstance(value, tuple):
        raise _JavaScriptControlError(reason)
    result: list[str] = []
    for item in value:
        if not isinstance(item, str) or (not allow_empty and not item):
            raise _JavaScriptControlError(reason)
        result.append(item)
    return tuple(result)


def _string_mapping(value: object, reason: str) -> dict[str, str]:
    if not isinstance(value, dict):
        raise _JavaScriptControlError(reason)
    result: dict[str, str] = {}
    for key, item in value.items():
        if not isinstance(key, str) or not key or not isinstance(item, str) or not item:
            raise _JavaScriptControlError(reason)
        result[key] = item
    return dict(sorted(result.items()))


def _optional_nonempty_string(
    value: Mapping[str, object],
    field: str,
    reason: str,
) -> str | None:
    item = value.get(field)
    if item is None:
        return None
    if not isinstance(item, str) or not item:
        raise _JavaScriptControlError(reason)
    return item


def _lower_string(value: object, reason: str) -> str:
    if not isinstance(value, str) or not value:
        raise _JavaScriptControlError(reason)
    return value.lower()


def _boolean(value: object, reason: str) -> bool:
    if not isinstance(value, bool):
        raise _JavaScriptControlError(reason)
    return value


def _snake(value: str) -> str:
    return re.sub(r"(?<!^)(?=[A-Z])", "_", value).lower()


def _config_path(root: str, value: object, reason: str) -> str:
    if not isinstance(value, str) or not value:
        raise _JavaScriptControlError(reason)
    return _normalize_repo_path(root, value, reason)


def _config_paths(root: str, value: object, reason: str) -> tuple[str, ...]:
    return tuple(
        _normalize_repo_path(root, item, reason)
        for item in _string_tuple(value, reason)
    )


def _normalize_repo_path(origin: str, value: str, reason: str) -> str:
    if "\\" in value or value.startswith("/") or _URL_RE.match(value):
        raise _JavaScriptControlError(reason)
    normalized = posixpath.normpath(posixpath.join(origin, value))
    if normalized == ".." or normalized.startswith("../"):
        raise _JavaScriptControlError(reason)
    return normalized or "."


def _inherited_config_path(
    config: TypeScriptProjectConfig | None,
    field: str,
) -> str | None:
    return None if config is None else getattr(config, field)


def _implied_module_resolution(
    module: str | None,
) -> Literal["node16", "nodenext", "bundler", "node10", "classic"] | None:
    if module in {"node16", "node18", "node20"}:
        return "node16"
    if module == "nodenext":
        return "nodenext"
    if module == "preserve":
        return "bundler"
    return None


def _validate_references(value: object) -> None:
    if value is None:
        return
    if not isinstance(value, list):
        raise _JavaScriptControlError("invalid_references")
    for reference in value:
        if not isinstance(reference, dict) or set(reference) != {"path"}:
            raise _JavaScriptControlError("invalid_references")
        if not isinstance(reference["path"], str) or not reference["path"]:
            raise _JavaScriptControlError("invalid_references")


def _validate_workspace_pattern(pattern: str, *, allow_exclusion: bool) -> None:
    value = pattern
    if value.startswith("!"):
        if not allow_exclusion:
            raise _JavaScriptControlError("workspace_exclusion_not_supported")
        value = value[1:]
    if (
        not value
        or "\\" in value
        or value.startswith("/")
        or ".." in PurePosixPath(value).parts
        or any(character in value for character in "{}[]()")
    ):
        raise _JavaScriptControlError("invalid_workspace_pattern")
    for part in PurePosixPath(value).parts:
        if "*" in part and part not in {"*", "**"}:
            raise _JavaScriptControlError("unsupported_workspace_pattern")


def _workspace_pattern_matches(workspace_root: str, pattern: str, root: str) -> bool:
    try:
        relative = PurePosixPath(root).relative_to(PurePosixPath(workspace_root))
    except ValueError:
        return False
    pattern_parts = PurePosixPath(pattern).parts
    value_parts = relative.parts
    return _match_pattern_parts(pattern_parts, value_parts)


def _match_pattern_parts(pattern: tuple[str, ...], value: tuple[str, ...]) -> bool:
    if not pattern:
        return not value
    head = pattern[0]
    if head == "**":
        return _match_pattern_parts(pattern[1:], value) or bool(value) and _match_pattern_parts(pattern, value[1:])
    if not value or (head != "*" and head != value[0]):
        return False
    return _match_pattern_parts(pattern[1:], value[1:])


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
            if config is not None and config.resolve_package_json_imports is False:
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
            if config is not None and config.resolve_package_json_exports is False:
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
        if target_package.has_exports and not (
            config is not None and config.resolve_package_json_exports is False
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
    exact: list[str] = []
    stem: str
    extensions: tuple[str, ...]
    if base.endswith((".d.ts", ".d.mts", ".d.cts")):
        return (base,)
    written = next((extension for extension in _JAVASCRIPT_EXTENSIONS if base.endswith(extension)), None)
    if written in _TYPESCRIPT_EXTENSIONS:
        exact.append(base)
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

    candidates = list(exact)
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
