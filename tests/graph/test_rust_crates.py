from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

import loci.graph.rust_crates as rust_crates
from loci.graph.contracts import GraphContractError
from loci.graph.rust_crates import (
    CargoContext,
    RustDependency,
    RustTarget,
    load_cargo_context,
)


def _write(path: Path, content: str = "") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


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
