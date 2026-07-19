from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

import loci.graph.rust_crates as rust_crates
from loci.graph.contracts import GraphContractError
from loci.graph.rust_crates import (
    CargoPackage,
    CargoContext,
    RustDependency,
    RustTarget,
    build_rust_crate_index,
    load_cargo_context,
    make_rust_crate_id,
)
from loci.parser.imports import RawImport, RustImportContext
from loci.parser.symbols import Symbol, make_file_symbol


_DEFAULT_IMPORTED_NAME = object()


def _write(path: Path, content: str = "") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def _file_nodes(*paths: str) -> dict[str, Symbol]:
    return {
        path: make_file_symbol(
            path,
            language="rust",
            content_hash=hashlib.sha256(path.encode()).hexdigest(),
        )
        for path in paths
    }


def _rust_observation(
    source_file: str,
    specifier: str,
    *,
    kind: str = "module",
    imported_name: str | None | object = _DEFAULT_IMPORTED_NAME,
    lexical_module_path: tuple[str, ...] = (),
    lexical_module_visibilities: tuple[str, ...] = (),
    lexical_module_configurations: tuple[str, ...] = (),
    visibility: str = "private",
    configuration: str = "unconditional",
    path_override: str | None = None,
    inline: bool = False,
    module_level: bool = True,
    is_reexport: bool = False,
) -> RawImport:
    return RawImport(
        source_file=source_file,
        language="rust",
        line=1,
        text=f"{kind} {specifier}",
        specifier=specifier,
        imported_name=(
            specifier.rsplit("::", 1)[-1]
            if imported_name is _DEFAULT_IMPORTED_NAME
            else imported_name  # type: ignore[arg-type]
        ),
        type_only=False,
        is_reexport=is_reexport,
        source_hash="0" * 64,
        rust=RustImportContext(
            kind=kind,  # type: ignore[arg-type]
            lexical_module_path=lexical_module_path,
            visibility=visibility,
            module_level=module_level,
            configuration=configuration,  # type: ignore[arg-type]
            path_override=path_override,
            lexical_module_visibilities=lexical_module_visibilities,
            lexical_module_configurations=lexical_module_configurations,  # type: ignore[arg-type]
            inline=inline,
        ),
    )


def test_loader_parses_package_dependencies_features_and_targets(tmp_path: Path):
    manifest = _write(
        tmp_path / "Cargo.toml",
        """
[package]
name = "demo-kit"
edition = "2021"

[features]
default = []
fast = ["dep:serde"]

[dependencies]
serde = { version = "1", optional = true, default-features = false, features = ["derive"] }
local_alias = { package = "local-package", path = "vendor/local" }

[dev-dependencies]
tempfile = "3"

[build-dependencies]
cc = "1"

[target.'cfg(unix)'.dependencies]
libc = "0.2"

[[bin]]
name = "admin-tool"
path = "tools/admin.rs"
edition = "2024"
required-features = ["fast"]
""".lstrip(),
    )
    for source in (
        "src/lib.rs",
        "src/main.rs",
        "src/bin/worker.rs",
        "examples/demo.rs",
        "tests/integration.rs",
        "benches/speed.rs",
        "build.rs",
        "tools/admin.rs",
    ):
        _write(tmp_path / source)
    (tmp_path / "vendor" / "local").mkdir(parents=True)

    loaded = load_cargo_context(tmp_path, [manifest])

    assert loaded.problems == ()
    assert loaded.input_hashes == {
        "Cargo.toml": hashlib.sha256(manifest.read_bytes()).hexdigest()
    }
    package = loaded.context.packages[0]
    assert (package.source, package.root, package.name) == (
        "Cargo.toml",
        ".",
        "demo-kit",
    )
    assert package.workspace_source is None
    assert package.edition == "2021"
    assert dict(package.features) == {
        "default": (),
        "fast": ("dep:serde",),
    }
    assert package.dependencies == (
        RustDependency(
            alias="cc",
            package_name="cc",
            kind="build",
            path=None,
            optional=False,
            default_features=True,
            features=(),
            target_condition=None,
            inherited=False,
            source="Cargo.toml",
        ),
        RustDependency(
            alias="libc",
            package_name="libc",
            kind="normal",
            path=None,
            optional=False,
            default_features=True,
            features=(),
            target_condition="cfg(unix)",
            inherited=False,
            source="Cargo.toml",
        ),
        RustDependency(
            alias="local_alias",
            package_name="local-package",
            kind="normal",
            path="vendor/local",
            optional=False,
            default_features=True,
            features=(),
            target_condition=None,
            inherited=False,
            source="Cargo.toml",
        ),
        RustDependency(
            alias="serde",
            package_name="serde",
            kind="normal",
            path=None,
            optional=True,
            default_features=False,
            features=("derive",),
            target_condition=None,
            inherited=False,
            source="Cargo.toml",
        ),
        RustDependency(
            alias="tempfile",
            package_name="tempfile",
            kind="dev",
            path=None,
            optional=False,
            default_features=True,
            features=(),
            target_condition=None,
            inherited=False,
            source="Cargo.toml",
        ),
    )
    assert package.targets == (
        RustTarget("bench", "speed", "speed", "benches/speed.rs", "2021", ()),
        RustTarget("bin", "admin-tool", "admin_tool", "tools/admin.rs", "2024", ("fast",)),
        RustTarget("bin", "demo-kit", "demo_kit", "src/main.rs", "2021", ()),
        RustTarget("bin", "worker", "worker", "src/bin/worker.rs", "2021", ()),
        RustTarget("build_script", "build-script-build", "build_script_build", "build.rs", "2021", ()),
        RustTarget("example", "demo", "demo", "examples/demo.rs", "2021", ()),
        RustTarget("lib", "demo-kit", "demo_kit", "src/lib.rs", "2021", ()),
        RustTarget("test", "integration", "integration", "tests/integration.rs", "2021", ()),
    )


def test_loader_builds_workspace_members_and_inherits_edition_and_dependency(
    tmp_path: Path,
):
    root_manifest = _write(
        tmp_path / "Cargo.toml",
        """
[workspace]
members = ["crates/*"]
exclude = ["crates/old"]

[workspace.package]
edition = "2024"

[workspace.dependencies]
core_alias = { package = "core-lib", path = "crates/core", default-features = false, features = ["base"] }
""".lstrip(),
    )
    app_manifest = _write(
        tmp_path / "crates" / "app" / "Cargo.toml",
        """
[package]
name = "app"
edition.workspace = true

[dependencies]
core_alias = { workspace = true, optional = true, features = ["extra"] }
""".lstrip(),
    )
    core_manifest = _write(
        tmp_path / "crates" / "core" / "Cargo.toml",
        '[package]\nname = "core-lib"\nedition = "2021"\n',
    )
    old_manifest = _write(
        tmp_path / "crates" / "old" / "Cargo.toml",
        '[package]\nname = "old"\n',
    )
    external_manifest = _write(
        tmp_path / "tools" / "external" / "Cargo.toml",
        """
[package]
name = "external"
workspace = "../.."
""".lstrip(),
    )
    for root in ("crates/app", "crates/core", "crates/old", "tools/external"):
        _write(tmp_path / root / "src" / "lib.rs")

    loaded = load_cargo_context(
        tmp_path,
        [old_manifest, app_manifest, root_manifest, external_manifest, core_manifest],
    )

    assert loaded.problems == ()
    assert loaded.context.workspaces[0].member_sources == (
        "crates/app/Cargo.toml",
        "crates/core/Cargo.toml",
        "tools/external/Cargo.toml",
    )
    packages = {package.name: package for package in loaded.context.packages}
    assert packages["old"].workspace_source is None
    assert packages["app"].workspace_source == "Cargo.toml"
    assert packages["external"].workspace_source == "Cargo.toml"
    assert packages["app"].edition == "2024"
    assert packages["app"].dependencies == (
        RustDependency(
            alias="core_alias",
            package_name="core-lib",
            kind="normal",
            path="crates/core",
            optional=True,
            default_features=False,
            features=("base", "extra"),
            target_condition=None,
            inherited=True,
            source="Cargo.toml",
        ),
    )


def test_explicit_target_customizes_auto_discovered_target(tmp_path: Path):
    manifest = _write(
        tmp_path / "Cargo.toml",
        """
[package]
name = "app"
edition = "2021"

[[bin]]
name = "worker"
required-features = ["workers"]
""".lstrip(),
    )
    _write(tmp_path / "src" / "bin" / "worker.rs")

    loaded = load_cargo_context(tmp_path, [manifest])

    assert loaded.problems == ()
    assert loaded.context.packages[0].targets == (
        RustTarget(
            "bin",
            "worker",
            "worker",
            "src/bin/worker.rs",
            "2021",
            ("workers",),
        ),
    )


def test_workspace_rejects_missing_members_and_nested_duplicate_ownership(
    tmp_path: Path,
):
    missing = _write(
        tmp_path / "Cargo.toml",
        '[workspace]\nmembers = ["missing"]\n',
    )

    missing_load = load_cargo_context(tmp_path, [missing])

    assert missing_load.context == CargoContext((), ())
    assert missing_load.problems[0].code == "GRAPH_CARGO_WORKSPACE_INVALID"
    assert missing_load.problems[0].details == {"reason": "workspace_member_not_found"}

    missing.write_text('[workspace]\nmembers = ["crates/**"]\n', encoding="utf-8")
    nested = _write(
        tmp_path / "crates" / "nested" / "Cargo.toml",
        """
[package]
name = "nested"

[workspace]
members = ["member"]
""".lstrip(),
    )
    member = _write(
        tmp_path / "crates" / "nested" / "member" / "Cargo.toml",
        '[package]\nname = "member"\n',
    )
    _write(tmp_path / "crates" / "nested" / "src" / "lib.rs")
    _write(tmp_path / "crates" / "nested" / "member" / "src" / "lib.rs")

    nested_load = load_cargo_context(tmp_path, [missing, nested, member])

    assert "nested" not in {package.name for package in nested_load.context.packages}
    assert any(
        problem.source == "crates/nested/Cargo.toml"
        and problem.details["reason"] == "ambiguous_workspace"
        for problem in nested_load.problems
    )


def test_workspace_automatically_includes_contained_path_dependencies(tmp_path: Path):
    workspace = _write(
        tmp_path / "Cargo.toml",
        '[workspace]\nmembers = ["app"]\n',
    )
    app = _write(
        tmp_path / "app" / "Cargo.toml",
        '[package]\nname = "app"\n[dependencies]\nhelper = { path = "../helper" }\n',
    )
    helper = _write(
        tmp_path / "helper" / "Cargo.toml",
        '[package]\nname = "helper"\n',
    )
    _write(tmp_path / "app" / "src" / "lib.rs")
    _write(tmp_path / "helper" / "src" / "lib.rs")

    loaded = load_cargo_context(tmp_path, [helper, workspace, app])

    assert loaded.problems == ()
    assert loaded.context.workspaces[0].member_sources == (
        "app/Cargo.toml",
        "helper/Cargo.toml",
    )


def test_combined_root_manifest_and_invalid_member_fail_closed(tmp_path: Path):
    root = _write(
        tmp_path / "Cargo.toml",
        """
[package]
name = "root"
edition = "2021"

[workspace]
members = ["member"]
""".lstrip(),
    )
    member = _write(
        tmp_path / "member" / "Cargo.toml",
        '[package]\nname = "member"\n',
    )
    _write(tmp_path / "src" / "lib.rs")
    _write(tmp_path / "member" / "src" / "lib.rs")

    loaded = load_cargo_context(tmp_path, [member, root])

    assert loaded.problems == ()
    assert loaded.context.workspaces[0].member_sources == (
        "Cargo.toml",
        "member/Cargo.toml",
    )
    assert all(package.workspace_source == "Cargo.toml" for package in loaded.context.packages)

    member.write_text(
        '[package]\nname = "member"\n[dependencies]\nbad = []\n',
        encoding="utf-8",
    )
    invalid = load_cargo_context(tmp_path, [member, root])

    assert invalid.context == CargoContext((), ())
    assert any(
        problem.source == "Cargo.toml"
        and problem.details["reason"] == "workspace_member_invalid"
        for problem in invalid.problems
    )


def test_workspace_glob_does_not_hide_an_invalid_member_manifest(tmp_path: Path):
    workspace = _write(
        tmp_path / "Cargo.toml",
        '[workspace]\nmembers = ["crates/*"]\n',
    )
    valid = _write(
        tmp_path / "crates" / "valid" / "Cargo.toml",
        '[package]\nname = "valid"\n',
    )
    invalid = _write(
        tmp_path / "crates" / "invalid" / "Cargo.toml",
        '[package]\nname = "first"\nname = "second"\n',
    )
    _write(tmp_path / "crates" / "valid" / "src" / "lib.rs")

    loaded = load_cargo_context(tmp_path, [valid, workspace, invalid])

    assert loaded.context == CargoContext((), ())
    assert any(
        problem.source == "Cargo.toml"
        and problem.details["reason"] == "workspace_member_invalid"
        for problem in loaded.problems
    )


def test_workspace_path_dependency_does_not_hide_an_invalid_member(tmp_path: Path):
    workspace = _write(
        tmp_path / "Cargo.toml",
        '[workspace]\nmembers = ["app"]\n',
    )
    app = _write(
        tmp_path / "app" / "Cargo.toml",
        '[package]\nname = "app"\n[dependencies]\nhelper = { path = "../helper" }\n',
    )
    invalid_helper = _write(
        tmp_path / "helper" / "Cargo.toml",
        '[package]\nname = "first"\nname = "second"\n',
    )
    _write(tmp_path / "app" / "src" / "lib.rs")

    loaded = load_cargo_context(tmp_path, [invalid_helper, workspace, app])

    assert loaded.context == CargoContext((), ())
    assert any(
        problem.source == "Cargo.toml"
        and problem.details["reason"] == "workspace_member_invalid"
        for problem in loaded.problems
    )


def test_dependency_sources_are_distinct_and_feature_mapping_is_frozen(tmp_path: Path):
    manifest = _write(
        tmp_path / "Cargo.toml",
        """
[package]
name = "app"

[features]
default = []

[dependencies]
registry = { version = "1", package = "same-name" }
git_alias = { git = "https://example.invalid/repo", package = "same-name" }
""".lstrip(),
    )

    loaded = load_cargo_context(tmp_path, [manifest])

    assert loaded.problems == ()
    assert [(item.alias, item.package_name, item.path) for item in loaded.context.packages[0].dependencies] == [
        ("git_alias", "same-name", None),
        ("registry", "same-name", None),
    ]
    with pytest.raises(TypeError):
        loaded.context.packages[0].features["new"] = ()  # type: ignore[index]


@pytest.mark.parametrize(
    ("content", "reason"),
    [
        ('[package]\nname = "a"\nname = "b"\n', "invalid_toml"),
        ('[package]\nname = []\n', "invalid_package_name"),
        ('[package]\nname = "a"\nedition = "2099"\n', "invalid_edition"),
        ('[workspace]\nmembers = ["../escape"]\n', "invalid_workspace_pattern"),
        ('[package]\nname = "a"\n[dependencies]\nb = { path = "../escape" }\n', "path_outside_repository"),
        ('[package]\nname = "a"\n[dependencies]\nb = { git = 1 }\n', "invalid_dependency_git"),
        (
            '[package]\nname = "a"\n[dependencies]\nb = { path = "local", git = "https://example.invalid/b" }\n',
            "conflicting_dependency_source",
        ),
    ],
)
def test_loader_rejects_invalid_whole_manifests(
    tmp_path: Path,
    content: str,
    reason: str,
):
    manifest = _write(tmp_path / "Cargo.toml", content)

    loaded = load_cargo_context(tmp_path, [manifest])

    assert loaded.context == CargoContext((), ())
    assert len(loaded.problems) == 1
    assert loaded.problems[0].source == "Cargo.toml"
    assert loaded.problems[0].details["reason"] == reason
    assert loaded.input_hashes["Cargo.toml"] == hashlib.sha256(
        manifest.read_bytes()
    ).hexdigest()


def test_loader_rejects_symlink_outside_and_oversized_without_reading(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    outside_dir = tmp_path.parent / f"{tmp_path.name}-outside"
    outside_dir.mkdir()
    outside = _write(outside_dir / "Cargo.toml", '[package]\nname = "outside"\n')
    linked = tmp_path / "Cargo.toml"
    linked.symlink_to(outside)
    oversized = tmp_path / "large" / "Cargo.toml"
    oversized.parent.mkdir()
    oversized.write_bytes(b"x" * (rust_crates.MAX_CARGO_CONTROL_BYTES + 1))

    def fail_if_read(*args: object, **kwargs: object) -> tuple[bytes, str]:
        raise AssertionError("rejected Cargo manifest was read")

    monkeypatch.setattr(rust_crates, "read_contained_file", fail_if_read)

    loaded = load_cargo_context(tmp_path, [outside, linked, oversized])

    assert loaded.context == CargoContext((), ())
    assert [(problem.source, problem.details["reason"]) for problem in loaded.problems] == [
        ("@outside/Cargo.toml", "outside_repository"),
        ("Cargo.toml", "symlink"),
        ("large/Cargo.toml", "control_file_too_large"),
    ]
    assert loaded.problems[-1].code == "GRAPH_RUST_INDEX_LIMIT_EXCEEDED"
    assert all(len(value) == 64 for value in loaded.input_hashes.values())


def test_loader_rejects_non_regular_control_and_symlinked_dependency_path(
    tmp_path: Path,
):
    directory_control = tmp_path / "directory" / "Cargo.toml"
    directory_control.mkdir(parents=True)
    outside = tmp_path.parent / f"{tmp_path.name}-dependency"
    outside.mkdir()
    linked = tmp_path / "linked"
    linked.symlink_to(outside, target_is_directory=True)
    manifest = _write(
        tmp_path / "Cargo.toml",
        '[package]\nname = "app"\n[dependencies]\nbad = { path = "linked" }\n',
    )

    loaded = load_cargo_context(tmp_path, [directory_control, manifest])

    assert loaded.context == CargoContext((), ())
    assert [(problem.source, problem.details["reason"]) for problem in loaded.problems] == [
        ("Cargo.toml", "path_outside_repository"),
        ("directory/Cargo.toml", "not_regular"),
    ]


def test_loader_rejects_invalid_utf8_depth_and_aggregate_bytes(tmp_path: Path):
    invalid = tmp_path / "Cargo.toml"
    invalid.write_bytes(b'[package]\nname = "a"\n\xff')
    deep = _write(
        tmp_path / "deep" / "Cargo.toml",
        "value = " + "{a=" * 65 + "1" + "}" * 65,
    )

    loaded = load_cargo_context(tmp_path, [deep, invalid])

    assert loaded.context == CargoContext((), ())
    assert [(problem.source, problem.details["reason"]) for problem in loaded.problems] == [
        ("Cargo.toml", "invalid_utf8"),
        ("deep/Cargo.toml", "toml_depth_exceeded"),
    ]

    valid = _write(
        tmp_path / "valid" / "Cargo.toml",
        '[package]\nname = "valid"\n',
    )
    aggregate = load_cargo_context(
        tmp_path,
        [valid],
        max_total_bytes=len(valid.read_bytes()) - 1,
    )
    assert aggregate.context == CargoContext((), ())
    assert aggregate.problems[0].details == {
        "reason": "total_control_bytes_exceeded",
        "limit": len(valid.read_bytes()) - 1,
    }
    assert aggregate.input_hashes["valid/Cargo.toml"] == hashlib.sha256(
        valid.read_bytes()
    ).hexdigest()


def test_loader_rejects_count_limits_without_partial_context(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    first = _write(tmp_path / "Cargo.toml", '[package]\nname = "a"\n')
    second = _write(tmp_path / "b" / "Cargo.toml", '[package]\nname = "b"\n')

    control_limit = load_cargo_context(
        tmp_path,
        [first, second],
        max_control_files=1,
    )
    assert control_limit.context == CargoContext((), ())
    assert control_limit.problems[0].details == {
        "reason": "control_file_limit_exceeded",
        "limit": 1,
    }

    monkeypatch.setattr(rust_crates, "MAX_CARGO_PACKAGES", 1)
    package_limit = load_cargo_context(tmp_path, [first, second])
    assert package_limit.context == CargoContext((), ())
    assert package_limit.problems[0].details == {
        "reason": "package_limit_exceeded",
        "limit": 1,
    }

    monkeypatch.setattr(rust_crates, "MAX_CARGO_PACKAGES", 10_000)
    monkeypatch.setattr(rust_crates, "MAX_CARGO_DEPENDENCIES", 1)
    first.write_text(
        '[package]\nname = "a"\n[dependencies]\nb = "1"\nc = "1"\n',
        encoding="utf-8",
    )
    dependency_limit = load_cargo_context(tmp_path, [first])
    assert dependency_limit.context == CargoContext((), ())
    assert dependency_limit.problems[0].details == {
        "reason": "dependency_limit_exceeded",
        "limit": 1,
    }

    monkeypatch.setattr(rust_crates, "MAX_CARGO_DEPENDENCIES", 100_000)
    monkeypatch.setattr(rust_crates, "MAX_CARGO_TARGETS", 1)
    first.write_text(
        """
[package]
name = "a"
edition = "2021"
autobins = false

[[bin]]
name = "one"
path = "one.rs"

[[bin]]
name = "two"
path = "two.rs"
""".lstrip(),
        encoding="utf-8",
    )
    _write(tmp_path / "one.rs")
    _write(tmp_path / "two.rs")
    target_limit = load_cargo_context(tmp_path, [first])
    assert target_limit.context == CargoContext((), ())
    assert target_limit.problems[0].details == {
        "reason": "target_limit_exceeded",
        "limit": 1,
    }

    monkeypatch.setattr(rust_crates, "MAX_CARGO_TARGETS", 50_000)
    monkeypatch.setattr(rust_crates, "MAX_CARGO_WORKSPACE_PATTERNS", 1)
    first.write_text(
        '[workspace]\nmembers = ["a", "b"]\n',
        encoding="utf-8",
    )
    workspace_limit = load_cargo_context(tmp_path, [first])
    assert workspace_limit.context == CargoContext((), ())
    assert workspace_limit.problems[0].details == {
        "reason": "workspace_pattern_limit_exceeded",
        "limit": 1,
    }


def test_loader_reports_growth_after_lstat_and_redacts_manifest_values(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    secret = "do-not-echo-this-value"
    manifest = _write(
        tmp_path / "Cargo.toml",
        f'[package]\nname = "a"\n[dependencies]\nb = {{ path = "../{secret}" }}\n',
    )

    invalid = load_cargo_context(tmp_path, [manifest])
    assert invalid.problems[0].details == {"reason": "path_outside_repository"}
    assert secret not in repr(invalid.problems)
    assert str(tmp_path) not in repr(invalid.problems)

    def report_growth(*args: object, **kwargs: object) -> tuple[bytes, str]:
        raise GraphContractError(
            "INVALID_GRAPH_EXTENSION",
            "Cargo manifest grew while reading",
            {"limit": rust_crates.MAX_CARGO_CONTROL_BYTES},
        )

    monkeypatch.setattr(rust_crates, "read_contained_file", report_growth)
    grown = load_cargo_context(tmp_path, [manifest])
    assert grown.context == CargoContext((), ())
    assert grown.problems[0].details == {
        "reason": "control_file_too_large",
        "limit": rust_crates.MAX_CARGO_CONTROL_BYTES,
    }
    assert len(grown.input_hashes["Cargo.toml"]) == 64


def test_crate_index_builds_stable_searchable_nodes_and_rejects_unindexed_roots():
    context = CargoContext(
        packages=(
            CargoPackage(
                source="Cargo.toml",
                root=".",
                name="demo-kit",
                workspace_source=None,
                edition="2021",
                features={},
                dependencies=(),
                targets=(
                    RustTarget("lib", "demo-kit", "demo_kit", "src/lib.rs", "2021", ()),
                    RustTarget("bin", "tool", "tool", "src/main.rs", "2024", ("cli",)),
                    RustTarget("example", "missing", "missing", "examples/missing.rs", "2021", ()),
                ),
            ),
        ),
        workspaces=(),
    )

    build = build_rust_crate_index(
        context,
        file_nodes=_file_nodes("src/lib.rs", "src/main.rs"),
        observations=(),
    )

    lib_id = make_rust_crate_id("Cargo.toml", "lib", "demo_kit")
    bin_id = make_rust_crate_id("Cargo.toml", "bin", "tool")
    assert [node.id for node in build.index.crate_nodes] == [bin_id, lib_id]
    assert build.index.crate_ids_by_source_file == {
        "src/lib.rs": (lib_id,),
        "src/main.rs": (bin_id,),
    }
    lib_node = build.index.crates_by_id[lib_id]
    assert lib_node.manifest == "Cargo.toml"
    assert lib_node.package_name == "demo-kit"
    assert build.index.crate_nodes[1].metadata == {
        "loci": {
            "rust_crate_node": True,
            "manifest": "Cargo.toml",
            "package_name": "demo-kit",
            "package_root": ".",
            "target_kind": "lib",
            "target_name": "demo-kit",
            "crate_name": "demo_kit",
            "crate_root": "src/lib.rs",
            "edition": "2021",
            "required_features": [],
        }
    }
    assert build.index.crate_nodes[1].content_hash == _file_nodes("src/lib.rs")[
        "src/lib.rs"
    ].content_hash
    assert [(problem.code, problem.details) for problem in build.problems] == [
        (
            "GRAPH_RUST_CRATE_INVALID",
            {"reason": "crate_root_not_indexed"},
        )
    ]


def test_crate_index_follows_only_declared_inline_external_and_path_modules():
    context = CargoContext(
        packages=(
            CargoPackage(
                source="Cargo.toml",
                root=".",
                name="demo",
                workspace_source=None,
                edition="2021",
                features={},
                dependencies=(),
                targets=(RustTarget("lib", "demo", "demo", "src/lib.rs", "2021", ()),),
            ),
        ),
        workspaces=(),
    )
    observations = (
        _rust_observation(
            "src/lib.rs",
            "api",
            inline=True,
            visibility="pub",
        ),
        _rust_observation("src/lib.rs", "internal"),
        _rust_observation(
            "src/lib.rs",
            "nested",
            lexical_module_path=("api",),
            lexical_module_visibilities=("pub",),
            lexical_module_configurations=("unconditional",),
            visibility="pub",
            configuration="conditional",
            path_override="custom.rs",
        ),
        _rust_observation("src/internal.rs", "child", visibility="pub(crate)"),
        _rust_observation(
            "src/internal.rs",
            "sibling",
            visibility="pub",
            path_override="sibling.rs",
        ),
    )

    build = build_rust_crate_index(
        context,
        file_nodes=_file_nodes(
            "src/lib.rs",
            "src/internal.rs",
            "src/internal/child.rs",
            "src/sibling.rs",
            "src/api/custom.rs",
            "src/undeclared.rs",
        ),
        observations=observations,
    )

    crate_id = make_rust_crate_id("Cargo.toml", "lib", "demo")
    modules = build.index.modules_by_crate_path
    assert {
        path: tuple(
            (item.source_file, item.visibility, item.configuration)
            for item in bindings
        )
        for (owner, path), bindings in modules.items()
        if owner == crate_id
    } == {
        (): (("src/lib.rs", "pub", "unconditional"),),
        ("api",): (("src/lib.rs", "pub", "unconditional"),),
        ("api", "nested"): (("src/api/custom.rs", "pub", "declared_possible"),),
        ("internal",): (("src/internal.rs", "private", "unconditional"),),
        ("internal", "child"): (("src/internal/child.rs", "pub(crate)", "unconditional"),),
        ("internal", "sibling"): (("src/sibling.rs", "pub", "unconditional"),),
    }
    assert "src/undeclared.rs" not in build.index.crate_ids_by_source_file
    assert build.index.crate_ids_by_source_file["src/lib.rs"] == (crate_id,)
    assert build.index.crate_ids_by_source_file["src/api/custom.rs"] == (crate_id,)
    assert build.problems == ()


def test_crate_index_rejects_ambiguous_unsafe_cyclic_and_too_deep_modules(
    monkeypatch: pytest.MonkeyPatch,
):
    context = CargoContext(
        packages=(
            CargoPackage(
                source="Cargo.toml",
                root=".",
                name="demo",
                workspace_source=None,
                edition="2021",
                features={},
                dependencies=(),
                targets=(RustTarget("lib", "demo", "demo", "src/lib.rs", "2021", ()),),
            ),
        ),
        workspaces=(),
    )
    observations = (
        _rust_observation("src/lib.rs", "duplicate"),
        _rust_observation("src/lib.rs", "missing"),
        _rust_observation("src/lib.rs", "escape", path_override="../../escape.rs"),
        _rust_observation("src/lib.rs", "empty", path_override="safe//file.rs"),
        _rust_observation("src/lib.rs", "cycle", path_override="lib.rs"),
        _rust_observation("src/lib.rs", "deep"),
        _rust_observation("src/deep.rs", "child"),
    )
    monkeypatch.setattr(rust_crates, "MAX_RUST_MODULE_DEPTH", 1)

    build = build_rust_crate_index(
        context,
        file_nodes=_file_nodes(
            "src/lib.rs",
            "src/duplicate.rs",
            "src/duplicate/mod.rs",
            "src/deep.rs",
            "src/deep/child.rs",
            "src/safe/file.rs",
        ),
        observations=observations,
    )

    assert set(build.index.modules_by_crate_path) == {
        (make_rust_crate_id("Cargo.toml", "lib", "demo"), ()),
        (make_rust_crate_id("Cargo.toml", "lib", "demo"), ("deep",)),
    }
    assert {problem.details["reason"] for problem in build.problems} == {
        "ambiguous_module_source",
        "cyclic_module_source",
        "module_depth_exceeded",
        "module_path_outside_repository",
        "module_source_not_indexed",
    }


def test_crate_index_builds_target_aware_dependency_and_library_bindings(
    tmp_path: Path,
):
    app_manifest = _write(
        tmp_path / "app" / "Cargo.toml",
        """
[package]
name = "app"
edition = "2021"

[dependencies]
core_alias = { package = "core", path = "../core" }
opt_alias = { package = "core", path = "../core", optional = true }
registry_only = "1"

[dev-dependencies]
dev_alias = { package = "dev-helper", path = "../dev" }

[build-dependencies]
builder = { package = "build-helper", path = "../builder" }

[target.'cfg(unix)'.dependencies]
core_alias = { package = "core", path = "../core" }
""".lstrip(),
    )
    core_manifest = _write(
        tmp_path / "core" / "Cargo.toml",
        '[package]\nname = "core"\nedition = "2021"\n',
    )
    dev_manifest = _write(
        tmp_path / "dev" / "Cargo.toml",
        '[package]\nname = "dev-helper"\nedition = "2021"\n',
    )
    builder_manifest = _write(
        tmp_path / "builder" / "Cargo.toml",
        '[package]\nname = "build-helper"\nedition = "2021"\n',
    )
    sources = (
        "app/src/lib.rs",
        "app/src/main.rs",
        "app/examples/demo.rs",
        "app/build.rs",
        "core/src/lib.rs",
        "dev/src/lib.rs",
        "builder/src/lib.rs",
    )
    for source in sources:
        _write(tmp_path / source)

    loaded = load_cargo_context(
        tmp_path,
        [builder_manifest, core_manifest, app_manifest, dev_manifest],
    )
    build = build_rust_crate_index(
        loaded.context,
        file_nodes=_file_nodes(*sources),
        observations=(),
    )

    app_lib = make_rust_crate_id("app/Cargo.toml", "lib", "app")
    app_bin = make_rust_crate_id("app/Cargo.toml", "bin", "app")
    app_example = make_rust_crate_id("app/Cargo.toml", "example", "demo")
    app_build = make_rust_crate_id(
        "app/Cargo.toml",
        "build_script",
        "build_script_build",
    )
    core_lib = make_rust_crate_id("core/Cargo.toml", "lib", "core")
    dev_lib = make_rust_crate_id("dev/Cargo.toml", "lib", "dev_helper")
    builder_lib = make_rust_crate_id(
        "builder/Cargo.toml",
        "lib",
        "build_helper",
    )
    bindings = build.index.dependencies_by_crate_alias

    assert bindings[(app_lib, "core_alias")][0].target_crate_id == core_lib
    assert bindings[(app_lib, "core_alias")][0].configuration == "declared_possible"
    assert bindings[(app_lib, "core_alias")][0].basis == "cargo_path_dependency"
    assert bindings[(app_lib, "core_alias")][0].control_files == (
        "app/Cargo.toml",
        "core/Cargo.toml",
    )
    assert bindings[(app_lib, "opt_alias")][0].configuration == "declared_possible"
    assert bindings[(app_bin, "app")][0].target_crate_id == app_lib
    assert bindings[(app_bin, "app")][0].basis == "cargo_package_library"
    assert bindings[(app_example, "dev_alias")][0].target_crate_id == dev_lib
    assert bindings[(app_example, "app")][0].target_crate_id == app_lib
    assert bindings[(app_build, "builder")][0].target_crate_id == builder_lib
    assert (app_lib, "dev_alias") not in bindings
    assert (app_bin, "dev_alias") not in bindings
    assert (app_build, "core_alias") not in bindings
    assert (app_build, "app") not in bindings
    assert all(
        key[1] != "registry_only"
        for key in bindings
    )
    assert build.problems == ()


def test_crate_index_converges_definite_module_aliases_and_reexports():
    context = CargoContext(
        packages=(
            CargoPackage(
                source="Cargo.toml",
                root=".",
                name="demo",
                workspace_source=None,
                edition="2021",
                features={},
                dependencies=(),
                targets=(RustTarget("lib", "demo", "demo", "src/lib.rs", "2021", ()),),
            ),
        ),
        workspaces=(),
    )
    observations = (
        _rust_observation("src/lib.rs", "a", visibility="pub"),
        _rust_observation("src/lib.rs", "b", visibility="pub"),
        _rust_observation(
            "src/lib.rs",
            "crate::a",
            kind="use",
            imported_name="facade",
            visibility="pub",
            is_reexport=True,
        ),
        _rust_observation(
            "src/lib.rs",
            "crate::facade",
            kind="use",
            imported_name="second",
            visibility="pub",
            is_reexport=True,
        ),
        _rust_observation(
            "src/lib.rs",
            "crate::a",
            kind="use",
            imported_name="conditional",
            configuration="conditional",
        ),
        _rust_observation(
            "src/lib.rs",
            "crate::a",
            kind="use",
            imported_name="clash",
        ),
        _rust_observation(
            "src/lib.rs",
            "crate::b",
            kind="use",
            imported_name="clash",
        ),
        _rust_observation(
            "src/lib.rs",
            "crate::a::*",
            kind="use",
            imported_name=None,
        ),
        _rust_observation(
            "src/lib.rs",
            "crate::a",
            kind="use",
            imported_name="block_only",
            module_level=False,
        ),
        _rust_observation(
            "src/lib.rs",
            "self",
            kind="extern_crate",
            imported_name="current",
        ),
    )

    build = build_rust_crate_index(
        context,
        file_nodes=_file_nodes("src/lib.rs", "src/a.rs", "src/b.rs"),
        observations=observations,
    )

    crate_id = make_rust_crate_id("Cargo.toml", "lib", "demo")
    modules = build.index.modules_by_crate_path
    assert modules[(crate_id, ("facade",))] == (
        rust_crates.RustModuleBinding(
            crate_id=crate_id,
            module_path=("a",),
            source_file="src/a.rs",
            visibility="pub",
            configuration="unconditional",
        ),
    )
    assert modules[(crate_id, ("second",))][0].module_path == ("a",)
    assert modules[(crate_id, ("conditional",))][0].configuration == "declared_possible"
    assert (crate_id, ("clash",)) not in modules
    assert (crate_id, ("block_only",)) not in modules
    assert (crate_id, ("*",)) not in modules
    assert build.index.dependencies_by_crate_alias[(crate_id, "current")] == (
        rust_crates.RustDependencyBinding(
            source_crate_id=crate_id,
            alias="current",
            target_crate_id=crate_id,
            basis="rust_module_path",
            configuration="unconditional",
            control_files=("Cargo.toml",),
        ),
    )
    assert build.problems == ()


def test_dependency_bindings_preserve_divergent_targets_as_ambiguous():
    app = CargoPackage(
        source="app/Cargo.toml",
        root="app",
        name="app",
        workspace_source=None,
        edition="2021",
        features={},
        dependencies=(
            RustDependency(
                alias="shared",
                package_name="first",
                kind="normal",
                path="first",
                optional=False,
                default_features=True,
                features=(),
                target_condition="cfg(unix)",
                inherited=False,
                source="app/Cargo.toml",
            ),
            RustDependency(
                alias="shared",
                package_name="second",
                kind="normal",
                path="second",
                optional=False,
                default_features=True,
                features=(),
                target_condition="cfg(windows)",
                inherited=False,
                source="app/Cargo.toml",
            ),
        ),
        targets=(RustTarget("lib", "app", "app", "app/src/lib.rs", "2021", ()),),
    )
    first = CargoPackage(
        source="first/Cargo.toml",
        root="first",
        name="first",
        workspace_source=None,
        edition="2021",
        features={},
        dependencies=(),
        targets=(RustTarget("lib", "first", "first", "first/src/lib.rs", "2021", ()),),
    )
    second = CargoPackage(
        source="second/Cargo.toml",
        root="second",
        name="second",
        workspace_source=None,
        edition="2021",
        features={},
        dependencies=(),
        targets=(RustTarget("lib", "second", "second", "second/src/lib.rs", "2021", ()),),
    )

    build = build_rust_crate_index(
        CargoContext((app, first, second), ()),
        file_nodes=_file_nodes(
            "app/src/lib.rs",
            "first/src/lib.rs",
            "second/src/lib.rs",
        ),
        observations=(),
    )

    app_id = make_rust_crate_id("app/Cargo.toml", "lib", "app")
    bindings = build.index.dependencies_by_crate_alias[(app_id, "shared")]
    assert [binding.target_crate_id for binding in bindings] == [
        make_rust_crate_id("first/Cargo.toml", "lib", "first"),
        make_rust_crate_id("second/Cargo.toml", "lib", "second"),
    ]
    assert all(binding.configuration == "declared_possible" for binding in bindings)


def test_alias_routes_enforce_scope_external_visibility_and_2015_extern_crate():
    app = CargoPackage(
        source="app/Cargo.toml",
        root="app",
        name="app",
        workspace_source=None,
        edition="2015",
        features={},
        dependencies=(
            RustDependency(
                alias="core_alias",
                package_name="core",
                kind="normal",
                path="core",
                optional=False,
                default_features=True,
                features=(),
                target_condition=None,
                inherited=False,
                source="app/Cargo.toml",
            ),
        ),
        targets=(RustTarget("lib", "app", "app", "app/src/lib.rs", "2015", ()),),
    )
    core = CargoPackage(
        source="core/Cargo.toml",
        root="core",
        name="core",
        workspace_source=None,
        edition="2021",
        features={},
        dependencies=(),
        targets=(RustTarget("lib", "core", "core", "core/src/lib.rs", "2021", ()),),
    )
    observations = (
        _rust_observation("app/src/lib.rs", "local", visibility="pub"),
        _rust_observation("app/src/lib.rs", "outer", inline=True, visibility="pub"),
        _rust_observation(
            "app/src/lib.rs",
            "child",
            lexical_module_path=("outer",),
            lexical_module_visibilities=("pub",),
            lexical_module_configurations=("unconditional",),
            visibility="pub",
        ),
        _rust_observation(
            "app/src/lib.rs",
            "self::child",
            kind="use",
            imported_name="self_child",
            lexical_module_path=("outer",),
            lexical_module_visibilities=("pub",),
            lexical_module_configurations=("unconditional",),
        ),
        _rust_observation(
            "app/src/lib.rs",
            "super::local",
            kind="use",
            imported_name="parent_local",
            lexical_module_path=("outer",),
            lexical_module_visibilities=("pub",),
            lexical_module_configurations=("unconditional",),
        ),
        _rust_observation(
            "app/src/lib.rs",
            "super::super::escape",
            kind="use",
            imported_name="escaped",
            lexical_module_path=("outer",),
            lexical_module_visibilities=("pub",),
            lexical_module_configurations=("unconditional",),
        ),
        _rust_observation(
            "app/src/lib.rs",
            "local",
            kind="use",
            imported_name="edition_root",
        ),
        _rust_observation(
            "app/src/lib.rs",
            "core_alias::public_api",
            kind="use",
            imported_name="missing_extern",
        ),
        _rust_observation(
            "app/src/lib.rs",
            "core_alias",
            kind="extern_crate",
            imported_name="external",
        ),
        _rust_observation(
            "app/src/lib.rs",
            "external::public_api",
            kind="use",
            imported_name="exposed",
            visibility="pub",
            is_reexport=True,
        ),
        _rust_observation(
            "app/src/lib.rs",
            "external::private_api",
            kind="use",
            imported_name="leak",
            visibility="pub",
            is_reexport=True,
        ),
        _rust_observation("core/src/lib.rs", "public_api", visibility="pub"),
        _rust_observation("core/src/lib.rs", "private_api"),
    )

    build = build_rust_crate_index(
        CargoContext((app, core), ()),
        file_nodes=_file_nodes(
            "app/src/lib.rs",
            "app/src/local.rs",
            "app/src/outer/child.rs",
            "core/src/lib.rs",
            "core/src/public_api.rs",
            "core/src/private_api.rs",
        ),
        observations=observations,
    )

    app_id = make_rust_crate_id("app/Cargo.toml", "lib", "app")
    core_id = make_rust_crate_id("core/Cargo.toml", "lib", "core")
    modules = build.index.modules_by_crate_path
    assert modules[(app_id, ("outer", "self_child"))][0].module_path == (
        "outer",
        "child",
    )
    assert modules[(app_id, ("outer", "parent_local"))][0].module_path == (
        "local",
    )
    assert modules[(app_id, ("edition_root",))][0].module_path == ("local",)
    assert modules[(app_id, ("exposed",))][0].crate_id == core_id
    assert modules[(app_id, ("exposed",))][0].module_path == ("public_api",)
    assert (app_id, ("escaped",)) not in modules
    assert (app_id, ("missing_extern",)) not in modules
    assert (app_id, ("leak",)) not in modules


def test_shared_source_file_can_belong_to_multiple_crate_targets():
    package = CargoPackage(
        source="Cargo.toml",
        root=".",
        name="shared",
        workspace_source=None,
        edition="2021",
        features={},
        dependencies=(),
        targets=(
            RustTarget("lib", "shared", "shared", "shared.rs", "2021", ()),
            RustTarget("bin", "shared-bin", "shared_bin", "shared.rs", "2021", ()),
        ),
    )
    observation = _rust_observation("shared.rs", "child", visibility="pub")

    build = build_rust_crate_index(
        CargoContext((package,), ()),
        file_nodes=_file_nodes("shared.rs", "shared/child.rs"),
        observations=(observation,),
    )

    lib_id = make_rust_crate_id("Cargo.toml", "lib", "shared")
    bin_id = make_rust_crate_id("Cargo.toml", "bin", "shared_bin")
    assert build.index.crate_ids_by_source_file["shared.rs"] == (bin_id, lib_id)
    assert build.index.crate_ids_by_source_file["shared/child.rs"] == (bin_id, lib_id)
    assert (lib_id, ("child",)) in build.index.modules_by_crate_path
    assert (bin_id, ("child",)) in build.index.modules_by_crate_path


def test_crate_index_limits_reject_the_whole_context(
    monkeypatch: pytest.MonkeyPatch,
):
    package = CargoPackage(
        source="Cargo.toml",
        root=".",
        name="demo",
        workspace_source=None,
        edition="2021",
        features={},
        dependencies=(),
        targets=(RustTarget("lib", "demo", "demo", "src/lib.rs", "2021", ()),),
    )
    observations = (
        _rust_observation("src/lib.rs", "one"),
        _rust_observation("src/lib.rs", "two"),
    )
    monkeypatch.setattr(rust_crates, "MAX_RUST_MODULE_DECLARATIONS", 1)

    build = build_rust_crate_index(
        CargoContext((package,), ()),
        file_nodes=_file_nodes("src/lib.rs", "src/one.rs", "src/two.rs"),
        observations=observations,
    )

    assert build.index.crate_nodes == ()
    assert build.index.modules_by_crate_path == {}
    assert build.problems[0].code == "GRAPH_RUST_INDEX_LIMIT_EXCEEDED"
    assert build.problems[0].details == {
        "reason": "module_declaration_limit_exceeded",
        "limit": 1,
    }


def test_duplicate_crate_identity_invalidates_the_owning_package():
    package = CargoPackage(
        source="Cargo.toml",
        root=".",
        name="demo",
        workspace_source=None,
        edition="2021",
        features={},
        dependencies=(),
        targets=(
            RustTarget("lib", "demo", "demo", "src/lib.rs", "2021", ()),
            RustTarget("bin", "tool-name", "tool_name", "src/one.rs", "2021", ()),
            RustTarget("bin", "tool_name", "tool_name", "src/two.rs", "2021", ()),
        ),
    )

    build = build_rust_crate_index(
        CargoContext((package,), ()),
        file_nodes=_file_nodes("src/lib.rs", "src/one.rs", "src/two.rs"),
        observations=(),
    )

    assert build.index.crate_nodes == ()
    assert build.problems[0].code == "GRAPH_RUST_CRATE_INVALID"
    assert build.problems[0].details == {"reason": "duplicate_crate_identity"}


def test_alias_pass_limit_rejects_partial_fixed_point(
    monkeypatch: pytest.MonkeyPatch,
):
    package = CargoPackage(
        source="Cargo.toml",
        root=".",
        name="demo",
        workspace_source=None,
        edition="2021",
        features={},
        dependencies=(),
        targets=(RustTarget("lib", "demo", "demo", "src/lib.rs", "2021", ()),),
    )
    observations = (
        _rust_observation("src/lib.rs", "base", visibility="pub"),
        _rust_observation(
            "src/lib.rs",
            "crate::base",
            kind="use",
            imported_name="z_first",
        ),
        _rust_observation(
            "src/lib.rs",
            "crate::z_first",
            kind="use",
            imported_name="a_second",
        ),
    )
    monkeypatch.setattr(rust_crates, "MAX_RUST_ALIAS_PASSES", 1)

    build = build_rust_crate_index(
        CargoContext((package,), ()),
        file_nodes=_file_nodes("src/lib.rs", "src/base.rs"),
        observations=observations,
    )

    assert build.index.crate_nodes == ()
    assert build.problems[0].code == "GRAPH_RUST_INDEX_LIMIT_EXCEEDED"
    assert build.problems[0].details == {
        "reason": "alias_pass_limit_exceeded",
        "limit": 1,
    }


def test_alias_candidate_limit_rejects_the_whole_context(
    monkeypatch: pytest.MonkeyPatch,
):
    package = CargoPackage(
        source="Cargo.toml",
        root=".",
        name="demo",
        workspace_source=None,
        edition="2021",
        features={},
        dependencies=(),
        targets=(RustTarget("lib", "demo", "demo", "src/lib.rs", "2021", ()),),
    )
    observations = (
        _rust_observation("src/lib.rs", "one", visibility="pub"),
        _rust_observation("src/lib.rs", "two", visibility="pub"),
        _rust_observation(
            "src/lib.rs",
            "crate::one",
            kind="use",
            imported_name="same",
        ),
        _rust_observation(
            "src/lib.rs",
            "crate::two",
            kind="use",
            imported_name="same",
        ),
    )
    monkeypatch.setattr(rust_crates, "MAX_RUST_RESOLUTION_CANDIDATES", 1)

    build = build_rust_crate_index(
        CargoContext((package,), ()),
        file_nodes=_file_nodes("src/lib.rs", "src/one.rs", "src/two.rs"),
        observations=observations,
    )

    assert build.index.crate_nodes == ()
    assert build.problems[0].details == {
        "reason": "resolution_candidate_limit_exceeded",
        "limit": 1,
    }
