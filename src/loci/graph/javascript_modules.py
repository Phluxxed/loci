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
