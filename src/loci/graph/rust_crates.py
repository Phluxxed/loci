from __future__ import annotations

import hashlib
import math
import os
import stat
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from types import MappingProxyType
from typing import Literal, TypeAlias

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - exercised on Python 3.10
    import tomli as tomllib

from .contracts import GraphContractError, JSONValue
from .profiles import read_contained_file


MAX_CARGO_CONTROL_BYTES = 1_048_576
MAX_CARGO_CONTROL_FILES = 10_000
MAX_CARGO_TOTAL_BYTES = 67_108_864
MAX_CARGO_TOML_DEPTH = 64
MAX_CARGO_WORKSPACE_PATTERNS = 1_000
MAX_CARGO_PACKAGES = 10_000
MAX_CARGO_TARGETS = 50_000
MAX_CARGO_DEPENDENCIES = 100_000
MAX_RUST_MODULE_DECLARATIONS = 250_000
MAX_RUST_OBSERVATIONS = 1_000_000
MAX_RUST_MODULE_DEPTH = 128
MAX_RUST_RESOLUTION_CANDIDATES = 256
MAX_RUST_ALIAS_PASSES = 128

RustTargetKind: TypeAlias = Literal[
    "lib", "bin", "example", "test", "bench", "build_script"
]
RustDependencyKind: TypeAlias = Literal["normal", "dev", "build"]
RustResolutionBasis: TypeAlias = Literal[
    "rust_module_declaration",
    "rust_module_path",
    "cargo_path_dependency",
    "cargo_workspace_dependency",
    "cargo_package_library",
]
RustResolutionConfiguration: TypeAlias = Literal[
    "unconditional",
    "declared_possible",
]
RustCrateProblemCode: TypeAlias = Literal[
    "GRAPH_CARGO_MANIFEST_INVALID",
    "GRAPH_CARGO_WORKSPACE_INVALID",
    "GRAPH_RUST_CRATE_INVALID",
    "GRAPH_RUST_MODULE_INVALID",
    "GRAPH_RUST_INDEX_LIMIT_EXCEEDED",
]

_EDITIONS = frozenset({"2015", "2018", "2021", "2024"})
_DEPENDENCY_TABLES: tuple[tuple[str, RustDependencyKind], ...] = (
    ("dependencies", "normal"),
    ("dev-dependencies", "dev"),
    ("build-dependencies", "build"),
)
@dataclass(frozen=True, slots=True)
class RustDependency:
    alias: str
    package_name: str
    kind: RustDependencyKind
    path: str | None
    optional: bool
    default_features: bool
    features: tuple[str, ...]
    target_condition: str | None
    inherited: bool
    source: str


@dataclass(frozen=True, slots=True)
class RustTarget:
    kind: RustTargetKind
    target_name: str
    crate_name: str
    root_file: str
    edition: str
    required_features: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class CargoPackage:
    source: str
    root: str
    name: str
    workspace_source: str | None
    edition: str
    features: Mapping[str, tuple[str, ...]]
    dependencies: tuple[RustDependency, ...]
    targets: tuple[RustTarget, ...]


@dataclass(frozen=True, slots=True)
class CargoWorkspace:
    source: str
    root: str
    member_sources: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class RustCrateProblem:
    code: RustCrateProblemCode
    message: str
    source: str
    details: dict[str, JSONValue]


@dataclass(frozen=True, slots=True)
class CargoContext:
    packages: tuple[CargoPackage, ...]
    workspaces: tuple[CargoWorkspace, ...]


@dataclass(frozen=True, slots=True)
class CargoLoad:
    context: CargoContext
    input_hashes: dict[str, str]
    problems: tuple[RustCrateProblem, ...]


@dataclass(frozen=True, slots=True)
class _Manifest:
    source: str
    root: str
    raw: Mapping[str, object]


@dataclass(frozen=True, slots=True)
class _PackageShell:
    manifest: _Manifest
    name: str
    workspace_root: str | None


@dataclass(frozen=True, slots=True)
class _WorkspaceDraft:
    manifest: _Manifest
    members: tuple[str, ...]
    exclude: tuple[str, ...]
    package: Mapping[str, object]
    dependencies: Mapping[str, object]


class _CargoError(ValueError):
    def __init__(
        self,
        reason: str,
        *,
        limit: int | None = None,
        limit_error: bool = False,
    ) -> None:
        super().__init__(reason)
        self.reason = reason
        self.limit = limit
        self.limit_error = limit_error


def load_cargo_context(
    repo_path: Path,
    candidates: Sequence[Path],
    *,
    max_control_bytes: int = MAX_CARGO_CONTROL_BYTES,
    max_control_files: int = MAX_CARGO_CONTROL_FILES,
    max_total_bytes: int = MAX_CARGO_TOTAL_BYTES,
) -> CargoLoad:
    """Load bounded repository-local Cargo metadata without executing Cargo."""
    root = repo_path.resolve(strict=True)
    controls = sorted(
        {
            _candidate_source(root, path): path
            for path in candidates
            if path.name == "Cargo.toml"
        }.items()
    )
    if len(controls) > max_control_files:
        problem = _problem(
            "index",
            "@cargo-controls",
            _CargoError(
                "control_file_limit_exceeded",
                limit=max_control_files,
                limit_error=True,
            ),
        )
        return CargoLoad(_empty_context(), {}, (problem,))

    input_hashes: dict[str, str] = {}
    problems: list[RustCrateProblem] = []
    invalid_control_sources: set[str] = set()
    loaded_controls: list[tuple[str, bytes]] = []
    total_bytes = 0
    for source, path in controls:
        try:
            data, source = _read_control_candidate(
                root,
                path,
                max_control_bytes=max_control_bytes,
            )
        except _CargoError as exc:
            input_hashes[source] = _sentinel_hash("manifest", exc.reason)
            problems.append(_problem("manifest", source, exc))
            if not source.startswith("@outside/"):
                invalid_control_sources.add(source)
            continue
        input_hashes[source] = hashlib.sha256(data).hexdigest()
        total_bytes += len(data)
        if total_bytes <= max_total_bytes:
            loaded_controls.append((source, data))

    if total_bytes > max_total_bytes:
        problems.append(
            _problem(
                "index",
                "@cargo-controls",
                _CargoError(
                    "total_control_bytes_exceeded",
                    limit=max_total_bytes,
                    limit_error=True,
                ),
            )
        )
        return _load_result(_empty_context(), input_hashes, problems)

    manifests: list[_Manifest] = []
    for source, data in loaded_controls:
        try:
            raw = _parse_toml(data)
            package = raw.get("package")
            workspace = raw.get("workspace")
            if package is None and workspace is None:
                raise _CargoError("missing_package_or_workspace")
            if package is not None and not isinstance(package, dict):
                raise _CargoError("invalid_package")
            if workspace is not None and not isinstance(workspace, dict):
                raise _CargoError("invalid_workspace")
            manifests.append(_Manifest(source, _control_root(source), raw))
        except _CargoError as exc:
            invalid_control_sources.add(source)
            problems.append(_problem("manifest", source, exc))

    context, build_problems = _build_context(
        root,
        manifests,
        invalid_control_sources=invalid_control_sources,
    )
    problems.extend(build_problems)
    if any(problem.code == "GRAPH_RUST_INDEX_LIMIT_EXCEEDED" for problem in problems):
        context = _empty_context()
    return _load_result(context, input_hashes, problems)


def _build_context(
    repo_root: Path,
    manifests: Sequence[_Manifest],
    *,
    invalid_control_sources: set[str],
) -> tuple[CargoContext, list[RustCrateProblem]]:
    from ._cargo_workspace import (
        add_path_dependency_members as _add_path_dependency_members,
        invalid_workspace_members as _invalid_workspace_members,
        matching_workspace_members as _matching_workspace_members,
        package_shell as _package_shell,
        select_workspace_members as _select_workspace_members,
        workspace_draft as _workspace_draft,
    )

    problems: list[RustCrateProblem] = []
    shells: dict[str, _PackageShell] = {}
    invalid_sources: set[str] = set(invalid_control_sources)
    for manifest in manifests:
        if "package" not in manifest.raw:
            continue
        try:
            shells[manifest.source] = _package_shell(repo_root, manifest)
        except _CargoError as exc:
            invalid_sources.add(manifest.source)
            problems.append(_problem("manifest", manifest.source, exc))

    drafts: dict[str, _WorkspaceDraft] = {}
    for manifest in manifests:
        if "workspace" not in manifest.raw:
            continue
        try:
            drafts[manifest.source] = _workspace_draft(manifest)
        except _CargoError as exc:
            invalid_sources.add(manifest.source)
            invalid_sources.update(
                source
                for source, shell in shells.items()
                if _path_is_within(shell.manifest.root, manifest.root)
            )
            problems.append(_problem("workspace", manifest.source, exc))

    workspace_members: dict[str, set[str]] = {}
    workspace_by_root = {draft.manifest.root: source for source, draft in drafts.items()}
    for source, draft in drafts.items():
        if source in invalid_sources:
            continue
        try:
            if _invalid_workspace_members(draft, invalid_control_sources):
                raise _CargoError("workspace_member_invalid")
            selected = _select_workspace_members(draft, shells)
            if source in shells:
                selected.add(source)
            workspace_members[source] = selected
        except _CargoError as exc:
            invalid_sources.add(source)
            invalid_sources.update(_matching_workspace_members(draft, shells))
            problems.append(_problem("workspace", source, exc))

    for source, shell in tuple(shells.items()):
        if shell.workspace_root is None or source in invalid_sources:
            continue
        workspace_source = workspace_by_root.get(shell.workspace_root)
        if workspace_source is None or workspace_source in invalid_sources:
            invalid_sources.add(source)
            problems.append(
                _problem("manifest", source, _CargoError("workspace_not_found"))
            )
            continue
        workspace_members.setdefault(workspace_source, set()).add(source)

    _add_path_dependency_members(
        repo_root,
        shells,
        drafts,
        workspace_members,
        invalid_sources,
        problems,
        invalid_control_sources=invalid_control_sources,
    )

    claims: dict[str, list[str]] = {}
    for workspace_source, members in workspace_members.items():
        for member in members:
            if member not in invalid_sources:
                claims.setdefault(member, []).append(workspace_source)
    for member, owners in claims.items():
        if len(owners) > 1:
            invalid_sources.add(member)
            problems.append(
                _problem("manifest", member, _CargoError("ambiguous_workspace"))
            )

    package_workspace = {
        member: owners[0]
        for member, owners in claims.items()
        if len(owners) == 1 and member not in invalid_sources
    }
    packages: list[CargoPackage] = []
    for source, shell in sorted(shells.items()):
        if source in invalid_sources:
            continue
        workspace_source = package_workspace.get(source)
        workspace = drafts.get(workspace_source) if workspace_source else None
        try:
            package, target_problems = _parse_package(
                repo_root,
                shell,
                workspace_source=workspace_source,
                workspace=workspace,
            )
            packages.append(package)
            problems.extend(target_problems)
        except _CargoError as exc:
            invalid_sources.add(source)
            problems.append(_problem("manifest", source, exc))

    workspaces: list[CargoWorkspace] = []
    invalid_workspaces: set[str] = set()
    for source, members in workspace_members.items():
        if source in invalid_sources:
            invalid_workspaces.add(source)
            continue
        if any(member in invalid_sources for member in members):
            invalid_workspaces.add(source)
            problems.append(
                _problem("workspace", source, _CargoError("workspace_member_invalid"))
            )
            continue
        member_sources = tuple(sorted(members))
        if not member_sources:
            invalid_workspaces.add(source)
            problems.append(
                _problem("workspace", source, _CargoError("workspace_has_no_members"))
            )
            continue
        workspaces.append(
            CargoWorkspace(
                source=source,
                root=drafts[source].manifest.root,
                member_sources=member_sources,
            )
        )
    if invalid_workspaces:
        packages = [
            package
            for package in packages
            if package.workspace_source not in invalid_workspaces
        ]

    if len(packages) > MAX_CARGO_PACKAGES:
        return _empty_context(), [
            _problem(
                "index",
                "@cargo-packages",
                _CargoError(
                    "package_limit_exceeded",
                    limit=MAX_CARGO_PACKAGES,
                    limit_error=True,
                ),
            )
        ]
    target_count = sum(len(package.targets) for package in packages)
    if target_count > MAX_CARGO_TARGETS:
        return _empty_context(), [
            _problem(
                "index",
                "@cargo-targets",
                _CargoError(
                    "target_limit_exceeded",
                    limit=MAX_CARGO_TARGETS,
                    limit_error=True,
                ),
            )
        ]
    dependency_count = sum(len(package.dependencies) for package in packages)
    if dependency_count > MAX_CARGO_DEPENDENCIES:
        return _empty_context(), [
            _problem(
                "index",
                "@cargo-dependencies",
                _CargoError(
                    "dependency_limit_exceeded",
                    limit=MAX_CARGO_DEPENDENCIES,
                    limit_error=True,
                ),
            )
        ]
    return (
        CargoContext(
            packages=tuple(sorted(packages, key=lambda item: item.source)),
            workspaces=tuple(sorted(workspaces, key=lambda item: item.source)),
        ),
        problems,
    )


def _parse_package(
    repo_root: Path,
    shell: _PackageShell,
    *,
    workspace_source: str | None,
    workspace: _WorkspaceDraft | None,
) -> tuple[CargoPackage, list[RustCrateProblem]]:
    from ._cargo_targets import parse_targets

    package_raw = _mapping(shell.manifest.raw.get("package"), "invalid_package")
    edition = _package_edition(package_raw.get("edition"), workspace)
    features = _parse_features(shell.manifest.raw.get("features", {}))
    dependencies = _parse_dependencies(
        repo_root,
        shell.manifest,
        workspace,
    )
    targets, target_problems = parse_targets(
        repo_root,
        shell,
        package_raw,
        edition,
    )
    return (
        CargoPackage(
            source=shell.manifest.source,
            root=shell.manifest.root,
            name=shell.name,
            workspace_source=workspace_source,
            edition=edition,
            features=MappingProxyType(dict(sorted(features.items()))),
            dependencies=tuple(
                sorted(
                    dependencies,
                    key=lambda item: (
                        item.alias,
                        item.kind,
                        item.target_condition or "",
                        item.source,
                    ),
                )
            ),
            targets=tuple(
                sorted(
                    targets,
                    key=lambda item: (item.kind, item.target_name, item.root_file),
                )
            ),
        ),
        target_problems,
    )


def _package_edition(value: object, workspace: _WorkspaceDraft | None) -> str:
    if value is None:
        return "2015"
    if isinstance(value, str):
        return _edition(value)
    inherited = _mapping(value, "invalid_edition")
    if inherited != {"workspace": True} or workspace is None:
        raise _CargoError("invalid_edition")
    return _edition(
        _nonempty_string(workspace.package.get("edition"), "missing_workspace_edition")
    )


def _parse_features(value: object) -> dict[str, tuple[str, ...]]:
    features: dict[str, tuple[str, ...]] = {}
    for name, entries in _mapping(value, "invalid_features").items():
        if not isinstance(name, str) or not name:
            raise _CargoError("invalid_feature_name")
        features[name] = _string_tuple(entries, "invalid_feature_values")
    return features


def _parse_dependencies(
    repo_root: Path,
    manifest: _Manifest,
    workspace: _WorkspaceDraft | None,
) -> list[RustDependency]:
    dependencies: list[RustDependency] = []
    for table_name, kind in _DEPENDENCY_TABLES:
        dependencies.extend(
            _dependency_table(
                repo_root,
                manifest,
                manifest.raw.get(table_name, {}),
                kind=kind,
                target_condition=None,
                workspace=workspace,
            )
        )
        _check_dependency_limit(dependencies)
    target = _mapping(manifest.raw.get("target", {}), "invalid_target_dependencies")
    for condition, raw_target in target.items():
        if not isinstance(condition, str) or not condition:
            raise _CargoError("invalid_target_condition")
        target_table = _mapping(raw_target, "invalid_target_dependencies")
        for table_name, kind in _DEPENDENCY_TABLES:
            dependencies.extend(
                _dependency_table(
                    repo_root,
                    manifest,
                    target_table.get(table_name, {}),
                    kind=kind,
                    target_condition=condition,
                    workspace=workspace,
                )
            )
            _check_dependency_limit(dependencies)
    return dependencies


def _check_dependency_limit(dependencies: Sequence[RustDependency]) -> None:
    if len(dependencies) > MAX_CARGO_DEPENDENCIES:
        raise _CargoError(
            "dependency_limit_exceeded",
            limit=MAX_CARGO_DEPENDENCIES,
            limit_error=True,
        )


def _dependency_table(
    repo_root: Path,
    manifest: _Manifest,
    value: object,
    *,
    kind: RustDependencyKind,
    target_condition: str | None,
    workspace: _WorkspaceDraft | None,
) -> list[RustDependency]:
    result: list[RustDependency] = []
    for alias, declaration in _mapping(value, "invalid_dependencies").items():
        alias = _package_name(alias)
        if isinstance(declaration, str):
            if not declaration:
                raise _CargoError("invalid_dependency")
            result.append(
                RustDependency(
                    alias,
                    alias,
                    kind,
                    None,
                    False,
                    True,
                    (),
                    target_condition,
                    False,
                    manifest.source,
                )
            )
            continue
        raw = _mapping(declaration, "invalid_dependency")
        if raw.get("workspace") is True:
            result.append(
                _inherited_dependency(
                    repo_root,
                    manifest,
                    workspace,
                    alias,
                    raw,
                    kind,
                    target_condition,
                )
            )
            continue
        if "workspace" in raw:
            raise _CargoError("invalid_dependency_workspace")
        _validate_dependency_source(raw)
        package_name = _package_name(raw.get("package", alias))
        path = None
        if "path" in raw:
            path = _normalize_repo_path(
                repo_root,
                manifest.root,
                _nonempty_string(raw["path"], "invalid_dependency_path"),
                "path_outside_repository",
            )
        result.append(
            RustDependency(
                alias=alias,
                package_name=package_name,
                kind=kind,
                path=path,
                optional=_boolean(raw.get("optional", False), "invalid_dependency_optional"),
                default_features=_boolean(
                    raw.get("default-features", True),
                    "invalid_dependency_default_features",
                ),
                features=tuple(
                    sorted(set(_string_tuple(raw.get("features", ()), "invalid_dependency_features")))
                ),
                target_condition=target_condition,
                inherited=False,
                source=manifest.source,
            )
        )
    return result


def _inherited_dependency(
    repo_root: Path,
    manifest: _Manifest,
    workspace: _WorkspaceDraft | None,
    alias: str,
    raw: Mapping[str, object],
    kind: RustDependencyKind,
    target_condition: str | None,
) -> RustDependency:
    if workspace is None:
        raise _CargoError("workspace_dependency_without_workspace")
    if set(raw) - {"workspace", "optional", "features"}:
        raise _CargoError("invalid_inherited_dependency")
    if alias not in workspace.dependencies:
        raise _CargoError("missing_workspace_dependency")
    base_value = workspace.dependencies[alias]
    if isinstance(base_value, str):
        if not base_value:
            raise _CargoError("invalid_workspace_dependency")
        base: Mapping[str, object] = {}
    else:
        base = _mapping(base_value, "invalid_workspace_dependency")
    _validate_dependency_source(base)
    if base.get("optional") is not None:
        raise _CargoError("workspace_dependency_optional")
    package_name = _package_name(base.get("package", alias))
    path = None
    if "path" in base:
        path = _normalize_repo_path(
            repo_root,
            workspace.manifest.root,
            _nonempty_string(base["path"], "invalid_dependency_path"),
            "path_outside_repository",
        )
    base_features = _string_tuple(base.get("features", ()), "invalid_dependency_features")
    member_features = _string_tuple(raw.get("features", ()), "invalid_dependency_features")
    return RustDependency(
        alias=alias,
        package_name=package_name,
        kind=kind,
        path=path,
        optional=_boolean(raw.get("optional", False), "invalid_dependency_optional"),
        default_features=_boolean(
            base.get("default-features", True),
            "invalid_dependency_default_features",
        ),
        features=tuple(sorted(set((*base_features, *member_features)))),
        target_condition=target_condition,
        inherited=True,
        source=workspace.manifest.source,
    )


def _validate_dependency_source(raw: Mapping[str, object]) -> None:
    for field in ("version", "git", "registry"):
        if field in raw:
            _nonempty_string(raw[field], f"invalid_dependency_{field}")
    sources = {field for field in ("path", "git", "registry") if field in raw}
    if ("path" in sources and len(sources) > 1) or {
        "git",
        "registry",
    } <= sources:
        raise _CargoError("conflicting_dependency_source")


def _parse_toml(data: bytes) -> Mapping[str, object]:
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise _CargoError("invalid_utf8") from exc
    try:
        raw = tomllib.loads(text)
    except (tomllib.TOMLDecodeError, ValueError, TypeError) as exc:
        raise _CargoError("invalid_toml") from exc
    _validate_toml_value(raw, 0)
    return raw


def _validate_toml_value(value: object, depth: int) -> None:
    if depth > MAX_CARGO_TOML_DEPTH:
        raise _CargoError(
            "toml_depth_exceeded",
            limit=MAX_CARGO_TOML_DEPTH,
            limit_error=True,
        )
    if isinstance(value, float) and not math.isfinite(value):
        raise _CargoError("non_finite_number")
    if isinstance(value, dict):
        for child in value.values():
            _validate_toml_value(child, depth + 1)
    elif isinstance(value, list):
        for child in value:
            _validate_toml_value(child, depth + 1)


def _read_control_candidate(
    root: Path,
    path: Path,
    *,
    max_control_bytes: int,
) -> tuple[bytes, str]:
    candidate = path if path.is_absolute() else root / path
    try:
        lexical = Path(os.path.abspath(candidate))
        lexical.relative_to(root)
    except ValueError as exc:
        raise _CargoError("outside_repository") from exc
    try:
        candidate_stat = os.lstat(lexical)
    except OSError as exc:
        raise _CargoError("unreadable") from exc
    if stat.S_ISLNK(candidate_stat.st_mode):
        raise _CargoError("symlink")
    if not stat.S_ISREG(candidate_stat.st_mode):
        raise _CargoError("not_regular")
    if candidate_stat.st_size > max_control_bytes:
        raise _CargoError(
            "control_file_too_large",
            limit=max_control_bytes,
            limit_error=True,
        )
    try:
        resolved = lexical.resolve(strict=True)
        resolved.relative_to(root)
    except (OSError, ValueError) as exc:
        raise _CargoError("outside_repository") from exc
    if resolved != lexical:
        raise _CargoError("symlink")
    try:
        return read_contained_file(
            root,
            lexical,
            record="Cargo manifest",
            max_bytes=max_control_bytes,
        )
    except GraphContractError as exc:
        if exc.details.get("limit") == max_control_bytes:
            raise _CargoError(
                "control_file_too_large",
                limit=max_control_bytes,
                limit_error=True,
            ) from exc
        raise _CargoError("unsafe_or_unreadable") from exc


def _normalize_repo_path(
    repo_root: Path,
    origin: str,
    value: str,
    escape_reason: str,
) -> str:
    if (
        not value
        or "\x00" in value
        or "\\" in value
        or value.startswith("/")
        or "//" in value
    ):
        raise _CargoError(escape_reason)
    origin_path = repo_root if origin == "." else repo_root / origin
    lexical = Path(os.path.abspath(origin_path / value))
    try:
        lexical_relative = lexical.relative_to(repo_root)
    except ValueError as exc:
        raise _CargoError(escape_reason) from exc
    resolved = lexical.resolve(strict=False)
    try:
        resolved_relative = resolved.relative_to(repo_root)
    except ValueError as exc:
        raise _CargoError(escape_reason) from exc
    if resolved != lexical:
        raise _CargoError("path_symlink")
    return (resolved_relative or lexical_relative).as_posix() or "."


def _mapping(value: object, reason: str) -> Mapping[str, object]:
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise _CargoError(reason)
    return value


def _string_tuple(value: object, reason: str) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple)):
        raise _CargoError(reason)
    result: list[str] = []
    for item in value:
        if not isinstance(item, str) or not item:
            raise _CargoError(reason)
        result.append(item)
    return tuple(result)


def _nonempty_string(value: object, reason: str) -> str:
    if not isinstance(value, str) or not value:
        raise _CargoError(reason)
    return value


def _boolean(value: object, reason: str) -> bool:
    if not isinstance(value, bool):
        raise _CargoError(reason)
    return value


def _package_name(value: object) -> str:
    if not isinstance(value, str) or not value or not all(
        character.isalnum() or character in "-_" for character in value
    ):
        raise _CargoError("invalid_package_name")
    return value


def _crate_name(value: str) -> str:
    return value.replace("-", "_")


def _edition(value: object) -> str:
    if not isinstance(value, str) or value not in _EDITIONS:
        raise _CargoError("invalid_edition")
    return value


def _join_repo_path(root: str, value: str) -> str:
    if root == ".":
        return value
    return f"{root}/{value}"


def _path_is_within(path: str, root: str) -> bool:
    try:
        PurePosixPath(path).relative_to(PurePosixPath(root))
    except ValueError:
        return False
    return True


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
    return hashlib.sha256(f"loci-cargo-{kind}:{reason}".encode()).hexdigest()


def _problem(kind: str, source: str, error: _CargoError) -> RustCrateProblem:
    code: RustCrateProblemCode
    if error.limit_error:
        code = "GRAPH_RUST_INDEX_LIMIT_EXCEEDED"
    elif kind == "workspace":
        code = "GRAPH_CARGO_WORKSPACE_INVALID"
    elif kind == "crate":
        code = "GRAPH_RUST_CRATE_INVALID"
    else:
        code = "GRAPH_CARGO_MANIFEST_INVALID"
    message = {
        "workspace": "Cargo workspace is invalid",
        "crate": "Rust crate target is invalid",
        "index": "Cargo/Rust index limit was exceeded",
    }.get(kind, "Cargo manifest is invalid")
    details: dict[str, JSONValue] = {"reason": error.reason}
    if error.limit is not None:
        details["limit"] = error.limit
    return RustCrateProblem(code, message, source, details)


def _empty_context() -> CargoContext:
    return CargoContext((), ())


def _load_result(
    context: CargoContext,
    input_hashes: Mapping[str, str],
    problems: Sequence[RustCrateProblem],
) -> CargoLoad:
    return CargoLoad(
        context=context,
        input_hashes=dict(sorted(input_hashes.items())),
        problems=tuple(
            sorted(problems, key=lambda item: (item.source, item.code, item.message))
        ),
    )
