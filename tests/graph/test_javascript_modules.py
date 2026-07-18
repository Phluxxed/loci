from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

import loci.graph.javascript_modules as javascript_modules
from loci.graph.javascript_modules import (
    JavaScriptModuleContext,
    load_javascript_module_context,
)


def test_loader_parses_strict_packages_jsonc_configs_and_pnpm_workspace(
    tmp_path: Path,
):
    package = tmp_path / "package.json"
    package.write_text(
        """
{
  "name": "@repo/root",
  "type": "module",
  "workspaces": ["apps/*", "packages/*"],
  "dependencies": {"@repo/core": "workspace:*"},
  "devDependencies": {"vitest": "^3"},
  "peerDependencies": {"react": "^19"},
  "optionalDependencies": {"fsevents": "^2"},
  "main": "./dist/index.js",
  "types": "./dist/index.d.ts",
  "exports": {".": "./dist/index.js"},
  "imports": {"#src/*": "./src/*.ts"}
}
""".lstrip(),
        encoding="utf-8",
    )
    tsconfig = tmp_path / "tsconfig.json"
    tsconfig.write_text(
        """
{
  // JSONC comments and trailing commas are supported.
  "compilerOptions": {
    "module": "NodeNext",
    "allowJs": true,
    "baseUrl": ".",
    "paths": {"@/*": ["src/*",],},
    "rootDirs": ["src", "generated"],
    "moduleSuffixes": [".native", ""],
    "customConditions": ["development"],
    "resolvePackageJsonExports": true,
    "resolvePackageJsonImports": true,
    "rootDir": "src",
    "outDir": "dist",
    "declarationDir": "types",
  },
  "include": ["src/**/*.ts",],
}
""".lstrip(),
        encoding="utf-8",
    )
    workspace = tmp_path / "pnpm-workspace.yaml"
    workspace.write_text(
        "packages:\n  - 'apps/*'\n  - packages/*\n  - '!packages/legacy'\n",
        encoding="utf-8",
    )
    app_dir = tmp_path / "apps" / "web"
    app_dir.mkdir(parents=True)
    app_package = app_dir / "package.json"
    app_package.write_text('{"name":"@repo/web"}', encoding="utf-8")
    core_dir = tmp_path / "packages" / "core"
    core_dir.mkdir(parents=True)
    core_package = core_dir / "package.json"
    core_package.write_text('{"name":"@repo/core"}', encoding="utf-8")

    loaded = load_javascript_module_context(
        tmp_path,
        [workspace, tsconfig, package, app_package, core_package],
    )

    assert loaded.problems == ()
    assert loaded.input_hashes == {
        "apps/web/package.json": hashlib.sha256(app_package.read_bytes()).hexdigest(),
        "package.json": hashlib.sha256(package.read_bytes()).hexdigest(),
        "packages/core/package.json": hashlib.sha256(
            core_package.read_bytes()
        ).hexdigest(),
        "pnpm-workspace.yaml": hashlib.sha256(workspace.read_bytes()).hexdigest(),
        "tsconfig.json": hashlib.sha256(tsconfig.read_bytes()).hexdigest(),
    }
    manifest = next(
        item for item in loaded.context.manifests if item.source == "package.json"
    )
    assert manifest.source == "package.json"
    assert manifest.root == "."
    assert manifest.name == "@repo/root"
    assert manifest.package_type == "module"
    assert manifest.workspaces == ("apps/*", "packages/*")
    assert dict(manifest.dependencies) == {"@repo/core": "workspace:*"}
    assert manifest.has_exports is True
    assert manifest.exports == {".": "./dist/index.js"}
    assert manifest.has_imports is True
    assert manifest.imports == {"#src/*": "./src/*.ts"}

    config = loaded.context.configs[0]
    assert config.source == "tsconfig.json"
    assert config.controls == ("tsconfig.json",)
    assert config.module == "nodenext"
    assert config.module_resolution == "nodenext"
    assert config.allow_js is True
    assert config.base_url == "."
    assert config.paths[0].pattern == "@/*"
    assert config.paths[0].targets == ("src/*",)
    assert config.root_dirs == ("src", "generated")
    assert config.module_suffixes == (".native", "")
    assert config.custom_conditions == ("development",)
    assert config.root_dir == "src"
    assert config.out_dir == "dist"
    assert config.declaration_dir == "types"
    assert config.include == ("src/**/*.ts",)

    pnpm_workspace = next(
        item
        for item in loaded.context.workspaces
        if item.source == "pnpm-workspace.yaml"
    )
    assert pnpm_workspace.root == "."
    assert pnpm_workspace.package_roots == (".", "apps/web", "packages/core")


def test_loader_resolves_local_extends_and_preserves_option_origins(tmp_path: Path):
    configs = tmp_path / "configs"
    configs.mkdir()
    base = configs / "base.json"
    base.write_text(
        """
{
  "compilerOptions": {
    "baseUrl": ".",
    "paths": {"@base/*": ["base-src/*"]},
    "rootDirs": ["base-src", "generated"]
  },
  "include": ["base-src/**/*.ts"]
}
""".lstrip(),
        encoding="utf-8",
    )
    child = tmp_path / "tsconfig.json"
    child.write_text(
        """
{
  "extends": "./configs/base",
  "compilerOptions": {
    "paths": {"@child/*": ["child-src/*"]},
    "outDir": "dist"
  },
  "include": ["src/**/*.ts"]
}
""".lstrip(),
        encoding="utf-8",
    )

    loaded = load_javascript_module_context(tmp_path, [child])

    assert loaded.problems == ()
    assert loaded.input_hashes == {
        "configs/base.json": hashlib.sha256(base.read_bytes()).hexdigest(),
        "tsconfig.json": hashlib.sha256(child.read_bytes()).hexdigest(),
    }
    config = loaded.context.configs[0]
    assert config.controls == ("configs/base.json", "tsconfig.json")
    assert config.base_url == "configs"
    assert config.paths[0].pattern == "@child/*"
    assert config.paths[0].targets == ("configs/child-src/*",)
    assert config.root_dirs == ("configs/base-src", "configs/generated")
    assert config.out_dir == "dist"
    assert config.include == ("src/**/*.ts",)


@pytest.mark.parametrize(
    ("filename", "content", "reason"),
    [
        ("package.json", '{"name":"a","name":"b"}', "duplicate_key"),
        ("package.json", '{"value": NaN}', "non_finite_number"),
        ("package.json", '{"dependencies": []}', "invalid_dependencies"),
        ("package.json", '{"workspaces": {"packages": ["a"]}}', "invalid_workspaces"),
        ("tsconfig.json", '{"compilerOptions":{"paths":[]}}', "invalid_paths"),
        ("tsconfig.json", '{"compilerOptions":{"allowJs":"yes"}}', "invalid_allow_js"),
        ("pnpm-workspace.yaml", "packages: &all\n  - apps/*\n", "yaml_alias_or_anchor"),
        ("pnpm-workspace.yaml", "packages: apps/*\n", "invalid_packages"),
        ("pnpm-workspace.yaml", "packages: []\nother: true\n", "invalid_workspace_shape"),
    ],
)
def test_loader_rejects_invalid_whole_controls(
    tmp_path: Path,
    filename: str,
    content: str,
    reason: str,
):
    control = tmp_path / filename
    control.write_text(content, encoding="utf-8")

    loaded = load_javascript_module_context(tmp_path, [control])

    assert loaded.context == JavaScriptModuleContext((), (), ())
    assert len(loaded.problems) == 1
    assert loaded.problems[0].source == filename
    assert loaded.problems[0].details["reason"] == reason
    assert loaded.input_hashes[filename] == hashlib.sha256(
        control.read_bytes()
    ).hexdigest()


def test_loader_rejects_invalid_utf8_and_excessive_json_depth(tmp_path: Path):
    invalid_utf8 = tmp_path / "package.json"
    invalid_utf8.write_bytes(b'{"name":"a"}\xff')
    deep = tmp_path / "tsconfig.json"
    deep.write_text("[" * 65 + "]" * 65, encoding="utf-8")

    loaded = load_javascript_module_context(tmp_path, [deep, invalid_utf8])

    assert loaded.context == JavaScriptModuleContext((), (), ())
    assert [(problem.source, problem.details["reason"]) for problem in loaded.problems] == [
        ("package.json", "invalid_utf8"),
        ("tsconfig.json", "json_depth_exceeded"),
    ]


def test_loader_rejects_symlink_outside_and_oversized_without_reading(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    outside_dir = tmp_path.parent / f"{tmp_path.name}-outside"
    outside_dir.mkdir()
    outside = outside_dir / "package.json"
    outside.write_text('{"name":"outside"}', encoding="utf-8")
    linked = tmp_path / "package.json"
    linked.symlink_to(outside)
    oversized = tmp_path / "tsconfig.json"
    oversized.write_bytes(b"x" * (javascript_modules.MAX_JAVASCRIPT_CONTROL_BYTES + 1))

    def fail_if_read(*args: object, **kwargs: object) -> tuple[bytes, str]:
        raise AssertionError("rejected control was read")

    monkeypatch.setattr(javascript_modules, "read_contained_file", fail_if_read)

    loaded = load_javascript_module_context(
        tmp_path,
        [outside, linked, oversized],
    )

    assert loaded.context == JavaScriptModuleContext((), (), ())
    assert [(problem.source, problem.details["reason"]) for problem in loaded.problems] == [
        ("@outside/package.json", "outside_repository"),
        ("package.json", "symlink"),
        ("tsconfig.json", "control_file_too_large"),
    ]
    assert all(len(value) == 64 for value in loaded.input_hashes.values())


def test_loader_rejects_config_cycles_package_extends_and_escape(tmp_path: Path):
    first = tmp_path / "tsconfig.json"
    second = tmp_path / "base.json"
    first.write_text('{"extends":"./base.json"}', encoding="utf-8")
    second.write_text('{"extends":"./tsconfig.json"}', encoding="utf-8")

    cycled = load_javascript_module_context(tmp_path, [first])

    assert cycled.context.configs == ()
    assert cycled.problems[0].details["reason"] == "config_cycle"
    assert set(cycled.input_hashes) == {"base.json", "tsconfig.json"}

    first.write_text('{"extends":"@repo/tsconfig"}', encoding="utf-8")
    package_extends = load_javascript_module_context(tmp_path, [first])
    assert package_extends.context.configs == ()
    assert package_extends.problems[0].details["reason"] == "package_extends"

    first.write_text('{"extends":"../outside.json"}', encoding="utf-8")
    escaped = load_javascript_module_context(tmp_path, [first])
    assert escaped.context.configs == ()
    assert escaped.problems[0].details["reason"] == "extends_outside_repository"


def test_loader_rejects_whole_context_when_a_count_limit_is_crossed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    first = tmp_path / "package.json"
    second_dir = tmp_path / "app"
    second_dir.mkdir()
    second = second_dir / "package.json"
    first.write_text('{"name":"root"}', encoding="utf-8")
    second.write_text('{"name":"app"}', encoding="utf-8")
    monkeypatch.setattr(javascript_modules, "MAX_JAVASCRIPT_CONTROL_FILES", 1)

    loaded = load_javascript_module_context(tmp_path, [second, first])

    assert loaded.context == JavaScriptModuleContext((), (), ())
    assert len(loaded.problems) == 1
    assert loaded.problems[0].code == "GRAPH_JAVASCRIPT_INDEX_LIMIT_EXCEEDED"
    assert loaded.problems[0].details == {
        "reason": "control_file_limit_exceeded",
        "limit": 1,
    }


def test_loader_problem_details_are_bounded_and_do_not_echo_control_values(
    tmp_path: Path,
):
    secret = "do-not-leak-this-control-value"
    package = tmp_path / "package.json"
    package.write_text(
        '{"dependencies":{"%s": 12}}' % secret,
        encoding="utf-8",
    )

    loaded = load_javascript_module_context(tmp_path, [package])

    problem = loaded.problems[0]
    assert problem.details == {"reason": "invalid_dependencies"}
    assert secret not in problem.message
    assert secret not in repr(problem.details)
    assert str(tmp_path) not in repr(problem)
