from __future__ import annotations

import fnmatch
from collections.abc import Mapping
from pathlib import Path, PurePosixPath

import loci.graph.rust_crates as cargo


def package_shell(repo_root: Path, manifest: cargo._Manifest) -> cargo._PackageShell:
    package = cargo._mapping(manifest.raw.get("package"), "invalid_package")
    name = cargo._package_name(package.get("name"))
    workspace_value = package.get("workspace")
    workspace_root: str | None = None
    if workspace_value is not None:
        if "workspace" in manifest.raw:
            raise cargo._CargoError("package_and_workspace_pointer")
        workspace_root = cargo._normalize_repo_path(
            repo_root,
            manifest.root,
            cargo._nonempty_string(workspace_value, "invalid_workspace_pointer"),
            "workspace_outside_repository",
        )
    return cargo._PackageShell(manifest, name, workspace_root)


def workspace_draft(manifest: cargo._Manifest) -> cargo._WorkspaceDraft:
    workspace = cargo._mapping(manifest.raw.get("workspace"), "invalid_workspace")
    members = cargo._string_tuple(
        workspace.get("members", ()), "invalid_workspace_members"
    )
    exclude = cargo._string_tuple(
        workspace.get("exclude", ()), "invalid_workspace_exclude"
    )
    if len(members) + len(exclude) > cargo.MAX_CARGO_WORKSPACE_PATTERNS:
        raise cargo._CargoError(
            "workspace_pattern_limit_exceeded",
            limit=cargo.MAX_CARGO_WORKSPACE_PATTERNS,
            limit_error=True,
        )
    for pattern in (*members, *exclude):
        _validate_workspace_pattern(pattern)
    package = cargo._mapping(
        workspace.get("package", {}), "invalid_workspace_package"
    )
    dependencies = cargo._mapping(
        workspace.get("dependencies", {}),
        "invalid_workspace_dependencies",
    )
    return cargo._WorkspaceDraft(manifest, members, exclude, package, dependencies)


def select_workspace_members(
    workspace: cargo._WorkspaceDraft,
    shells: Mapping[str, cargo._PackageShell],
) -> set[str]:
    for pattern in workspace.members:
        if not any(
            _workspace_pattern_matches(
                workspace.manifest.root, pattern, shell.manifest.root
            )
            for shell in shells.values()
        ):
            raise cargo._CargoError("workspace_member_not_found")
    return matching_workspace_members(workspace, shells)


def matching_workspace_members(
    workspace: cargo._WorkspaceDraft,
    shells: Mapping[str, cargo._PackageShell],
) -> set[str]:
    selected = {
        source
        for source, shell in shells.items()
        if any(
            _workspace_pattern_matches(
                workspace.manifest.root, pattern, shell.manifest.root
            )
            for pattern in workspace.members
        )
    }
    for pattern in workspace.exclude:
        selected.difference_update(
            source
            for source in tuple(selected)
            if _workspace_pattern_matches(
                workspace.manifest.root,
                pattern,
                shells[source].manifest.root,
            )
        )
    return selected


def invalid_workspace_members(
    workspace: cargo._WorkspaceDraft,
    invalid_sources: set[str],
) -> set[str]:
    selected = {
        source
        for source in invalid_sources
        if any(
            _workspace_pattern_matches(
                workspace.manifest.root,
                pattern,
                cargo._control_root(source),
            )
            for pattern in workspace.members
        )
    }
    return {
        source
        for source in selected
        if not any(
            _workspace_pattern_matches(
                workspace.manifest.root,
                pattern,
                cargo._control_root(source),
            )
            for pattern in workspace.exclude
        )
    }


def add_path_dependency_members(
    repo_root: Path,
    shells: Mapping[str, cargo._PackageShell],
    drafts: Mapping[str, cargo._WorkspaceDraft],
    workspace_members: dict[str, set[str]],
    invalid_sources: set[str],
    problems: list[cargo.RustCrateProblem],
    *,
    invalid_control_sources: set[str],
) -> None:
    source_by_root = {shell.manifest.root: source for source, shell in shells.items()}
    source_by_root.update(
        (cargo._control_root(source), source) for source in invalid_control_sources
    )
    for workspace_source, members in workspace_members.items():
        draft = drafts[workspace_source]
        pending = list(sorted(members, reverse=True))
        processed: set[str] = set()
        while pending:
            member = pending.pop()
            if member in processed:
                continue
            processed.add(member)
            shell = shells.get(member)
            if shell is None or member in invalid_sources:
                continue
            try:
                roots = _declared_dependency_paths(repo_root, shell.manifest)
            except cargo._CargoError as exc:
                invalid_sources.add(member)
                problems.append(cargo._problem("manifest", member, exc))
                continue
            for dependency_root in roots:
                dependency_source = source_by_root.get(dependency_root)
                if dependency_source is None or dependency_source in members:
                    continue
                try:
                    relative = PurePosixPath(dependency_root).relative_to(
                        PurePosixPath(draft.manifest.root)
                    )
                except ValueError:
                    continue
                excluded = any(
                    _match_pattern_parts(
                        PurePosixPath(pattern).parts,
                        relative.parts,
                    )
                    for pattern in draft.exclude
                )
                if not excluded:
                    members.add(dependency_source)
                    pending.append(dependency_source)


def _declared_dependency_paths(
    repo_root: Path,
    manifest: cargo._Manifest,
) -> set[str]:
    paths: set[str] = set()
    tables: list[object] = [
        manifest.raw.get(name, {}) for name, _ in cargo._DEPENDENCY_TABLES
    ]
    target = manifest.raw.get("target", {})
    if target is not None:
        for target_table in cargo._mapping(
            target, "invalid_target_dependencies"
        ).values():
            target_mapping = cargo._mapping(
                target_table, "invalid_target_dependencies"
            )
            tables.extend(
                target_mapping.get(name, {}) for name, _ in cargo._DEPENDENCY_TABLES
            )
    for table in tables:
        for value in cargo._mapping(table, "invalid_dependencies").values():
            if isinstance(value, dict) and "path" in value:
                paths.add(
                    cargo._normalize_repo_path(
                        repo_root,
                        manifest.root,
                        cargo._nonempty_string(
                            value["path"], "invalid_dependency_path"
                        ),
                        "path_outside_repository",
                    )
                )
    return paths


def _validate_workspace_pattern(pattern: str) -> None:
    if (
        not pattern
        or "\x00" in pattern
        or "\\" in pattern
        or pattern.startswith("/")
        or "//" in pattern
        or any(part in {".", ".."} for part in PurePosixPath(pattern).parts)
        or any(character in pattern for character in "{}()")
    ):
        raise cargo._CargoError("invalid_workspace_pattern")


def _workspace_pattern_matches(workspace_root: str, pattern: str, root: str) -> bool:
    try:
        relative = PurePosixPath(root).relative_to(PurePosixPath(workspace_root))
    except ValueError:
        return False
    return _match_pattern_parts(PurePosixPath(pattern).parts, relative.parts)


def _match_pattern_parts(pattern: tuple[str, ...], value: tuple[str, ...]) -> bool:
    if not pattern:
        return not value
    if pattern[0] == "**":
        return _match_pattern_parts(pattern[1:], value) or (
            bool(value) and _match_pattern_parts(pattern, value[1:])
        )
    return (
        bool(value)
        and fnmatch.fnmatchcase(value[0], pattern[0])
        and _match_pattern_parts(pattern[1:], value[1:])
    )
