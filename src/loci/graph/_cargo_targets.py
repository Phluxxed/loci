from __future__ import annotations

import os
import stat
from collections.abc import Mapping
from pathlib import Path

import loci.graph.rust_crates as cargo


_AUTO_TARGETS: tuple[tuple[str, cargo.RustTargetKind, str], ...] = (
    ("bin", "bin", "src/bin"),
    ("example", "example", "examples"),
    ("test", "test", "tests"),
    ("bench", "bench", "benches"),
)


def parse_targets(
    repo_root: Path,
    shell: cargo._PackageShell,
    package: Mapping[str, object],
    package_edition: str,
) -> tuple[list[cargo.RustTarget], list[cargo.RustCrateProblem]]:
    manifest = shell.manifest
    targets: dict[tuple[cargo.RustTargetKind, str], cargo.RustTarget] = {}
    manual = any(
        name in manifest.raw for name in ("lib", "bin", "example", "test", "bench")
    )
    auto_default = not (package_edition == "2015" and manual)

    lib_raw = manifest.raw.get("lib")
    if lib_raw is not None:
        _record_target(
            targets,
            _explicit_target(
                repo_root,
                manifest,
                "lib",
                cargo._mapping(lib_raw, "invalid_lib_target"),
                default_name=shell.name,
                default_paths=("src/lib.rs",),
                package_edition=package_edition,
            ),
        )
    elif _auto_enabled(package, "autolib", auto_default):
        _record_target(
            targets,
            _auto_target(
                repo_root,
                manifest,
                "lib",
                shell.name,
                "src/lib.rs",
                package_edition,
            ),
        )

    for table_name, kind, _ in _AUTO_TARGETS:
        raw_entries = manifest.raw.get(table_name, [])
        if not isinstance(raw_entries, list):
            raise cargo._CargoError(f"invalid_{table_name}_targets")
        for raw_entry in raw_entries:
            entry = cargo._mapping(raw_entry, f"invalid_{table_name}_target")
            name = cargo._package_name(entry.get("name"))
            _record_target(
                targets,
                _explicit_target(
                    repo_root,
                    manifest,
                    kind,
                    entry,
                    default_name=name,
                    default_paths=_target_default_paths(kind, name, shell.name),
                    package_edition=package_edition,
                ),
            )

    if _auto_enabled(package, "autobins", auto_default):
        _record_auto_target(
            targets,
            _auto_target(
                repo_root,
                manifest,
                "bin",
                shell.name,
                "src/main.rs",
                package_edition,
            ),
        )
    for table_name, kind, directory in _AUTO_TARGETS:
        flag = {
            "bin": "autobins",
            "example": "autoexamples",
            "test": "autotests",
            "bench": "autobenches",
        }[table_name]
        if not _auto_enabled(package, flag, auto_default):
            continue
        for name, relative in _discover_named_targets(
            repo_root, manifest, directory
        ):
            _record_auto_target(
                targets,
                _auto_target(
                    repo_root,
                    manifest,
                    kind,
                    name,
                    relative,
                    package_edition,
                ),
            )

    build = package.get("build")
    if build is not False:
        build_path = (
            "build.rs"
            if build in (None, True)
            else cargo._nonempty_string(build, "invalid_build_target")
        )
        _record_target(
            targets,
            _auto_target(
                repo_root,
                manifest,
                "build_script",
                "build-script-build",
                build_path,
                package_edition,
            ),
        )

    return list(targets.values()), []


def _explicit_target(
    repo_root: Path,
    manifest: cargo._Manifest,
    kind: cargo.RustTargetKind,
    raw: Mapping[str, object],
    *,
    default_name: str,
    default_paths: tuple[str, ...],
    package_edition: str,
) -> cargo.RustTarget:
    name = cargo._package_name(raw.get("name", default_name))
    edition = cargo._edition(raw.get("edition", package_edition))
    required = (
        ()
        if kind == "lib"
        else tuple(
            sorted(
                set(
                    cargo._string_tuple(
                        raw.get("required-features", ()),
                        "invalid_required_features",
                    )
                )
            )
        )
    )
    paths = (
        (cargo._nonempty_string(raw["path"], "invalid_target_path"),)
        if "path" in raw
        else default_paths
    )
    selected_roots = [
        root_file
        for candidate in paths
        if (root_file := _target_file(repo_root, manifest.root, candidate))
        is not None
    ]
    if len(selected_roots) > 1:
        raise cargo._CargoError("ambiguous_target_root")
    root_file = selected_roots[0] if selected_roots else None
    return cargo.RustTarget(
        kind,
        name,
        cargo._crate_name(name),
        root_file or "",
        edition,
        required,
    )


def _auto_target(
    repo_root: Path,
    manifest: cargo._Manifest,
    kind: cargo.RustTargetKind,
    name: str,
    relative: str,
    edition: str,
) -> cargo.RustTarget:
    root_file = _target_file(repo_root, manifest.root, relative)
    return cargo.RustTarget(
        kind,
        name,
        cargo._crate_name(name),
        root_file or "",
        edition,
        (),
    )


def _target_default_paths(
    kind: cargo.RustTargetKind,
    name: str,
    package_name: str,
) -> tuple[str, ...]:
    if kind == "bin" and name == package_name:
        return ("src/main.rs", f"src/bin/{name}.rs", f"src/bin/{name}/main.rs")
    directory = {
        "bin": "src/bin",
        "example": "examples",
        "test": "tests",
        "bench": "benches",
    }[kind]
    return (f"{directory}/{name}.rs", f"{directory}/{name}/main.rs")


def _discover_named_targets(
    repo_root: Path,
    manifest: cargo._Manifest,
    directory: str,
) -> list[tuple[str, str]]:
    path = repo_root / cargo._join_repo_path(manifest.root, directory)
    try:
        scanner = os.scandir(path)
    except OSError:
        return []
    entries: list[os.DirEntry[str]] = []
    with scanner:
        for entry in scanner:
            entries.append(entry)
            if len(entries) > cargo.MAX_CARGO_TARGETS:
                raise cargo._CargoError(
                    "target_limit_exceeded",
                    limit=cargo.MAX_CARGO_TARGETS,
                    limit_error=True,
                )
    discovered: list[tuple[str, str]] = []
    for entry in entries:
        if entry.is_symlink():
            continue
        if entry.is_file(follow_symlinks=False) and entry.name.endswith(".rs"):
            discovered.append((entry.name[:-3], f"{directory}/{entry.name}"))
        elif entry.is_dir(follow_symlinks=False):
            main = Path(entry.path) / "main.rs"
            try:
                main_stat = os.lstat(main)
            except OSError:
                continue
            if stat.S_ISREG(main_stat.st_mode):
                discovered.append((entry.name, f"{directory}/{entry.name}/main.rs"))
    return sorted(discovered)


def _record_auto_target(
    targets: dict[tuple[cargo.RustTargetKind, str], cargo.RustTarget],
    target: cargo.RustTarget,
) -> None:
    if (target.kind, target.crate_name) not in targets:
        _record_target(targets, target)


def _record_target(
    targets: dict[tuple[cargo.RustTargetKind, str], cargo.RustTarget],
    target: cargo.RustTarget,
) -> None:
    if not target.root_file:
        return
    identity = (target.kind, target.crate_name)
    if identity in targets:
        raise cargo._CargoError("duplicate_target")
    if len(targets) >= cargo.MAX_CARGO_TARGETS:
        raise cargo._CargoError(
            "target_limit_exceeded",
            limit=cargo.MAX_CARGO_TARGETS,
            limit_error=True,
        )
    targets[identity] = target


def _target_file(repo_root: Path, package_root: str, value: str) -> str | None:
    relative = cargo._normalize_repo_path(
        repo_root,
        package_root,
        value,
        "target_outside_repository",
    )
    path = repo_root / relative
    try:
        file_stat = os.lstat(path)
    except OSError:
        return None
    if stat.S_ISLNK(file_stat.st_mode) or not stat.S_ISREG(file_stat.st_mode):
        return None
    try:
        resolved = path.resolve(strict=True)
        resolved.relative_to(repo_root)
    except (OSError, ValueError):
        return None
    if resolved != path:
        return None
    return relative


def _auto_enabled(
    package: Mapping[str, object],
    field: str,
    default: bool,
) -> bool:
    return cargo._boolean(package.get(field, default), f"invalid_{field}")
