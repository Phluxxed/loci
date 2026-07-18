from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

import loci.graph.javascript_modules as javascript_modules
from loci.graph.javascript_modules import (
    JavaScriptModuleContext,
    build_javascript_resolution_index,
    load_javascript_module_context,
    resolve_javascript_import,
)
from loci.parser.imports import RawImport
from loci.parser.symbols import Symbol, make_file_symbol


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


def _javascript_file(path: str) -> Symbol:
    suffix = Path(path).suffix
    language = "typescript" if suffix in {".ts", ".tsx", ".mts", ".cts"} else "javascript"
    return make_file_symbol(
        path,
        language=language,
        content_hash=hashlib.sha256(path.encode()).hexdigest(),
    )


def _raw(
    source_file: str,
    specifier: str,
    *,
    type_only: bool = False,
) -> RawImport:
    return RawImport(
        source_file=source_file,
        language=(
            "typescript"
            if Path(source_file).suffix in {".ts", ".tsx", ".mts", ".cts"}
            else "javascript"
        ),
        line=1,
        text=f'import value from "{specifier}";',
        specifier=specifier,
        imported_name=None,
        type_only=type_only,
        is_reexport=False,
        source_hash="a" * 64,
    )


def _resolution_index(
    tmp_path: Path,
    files: list[str],
    controls: list[Path] | None = None,
    *,
    allow_problems: bool = False,
):
    loaded = load_javascript_module_context(tmp_path, controls or [])
    assert loaded.problems == ()
    file_nodes = {path: _javascript_file(path) for path in files}
    built = build_javascript_resolution_index(loaded.context, file_nodes=file_nodes)
    if not allow_problems:
        assert built.problems == ()
    return built.index


@pytest.mark.parametrize(
    ("specifier", "target"),
    [
        ("./runtime.js", "src/runtime.ts"),
        ("./module.mjs", "src/module.mts"),
        ("./legacy.cjs", "src/legacy.cts"),
        ("./component.jsx", "src/component.tsx"),
    ],
)
def test_resolver_applies_explicit_output_extension_substitution(
    tmp_path: Path,
    specifier: str,
    target: str,
):
    source = "src/consumer.ts"
    index = _resolution_index(tmp_path, [source, target])

    resolved = resolve_javascript_import(_raw(source, specifier), index)

    assert resolved.target_file == target
    assert resolved.basis == "relative_path"
    assert resolved.control_files == ()
    assert resolved.unresolved_reason is None


def test_resolver_preserves_legacy_extensionless_order_and_type_declarations(
    tmp_path: Path,
):
    source = "src/consumer.ts"
    index = _resolution_index(
        tmp_path,
        [source, "src/value.ts", "src/value.d.ts", "src/value.js", "src/value.jsx"],
    )

    runtime = resolve_javascript_import(_raw(source, "./value"), index)
    type_index = _resolution_index(
        tmp_path,
        [source, "src/value.d.ts", "src/value.js"],
    )
    type_only = resolve_javascript_import(
        _raw(source, "./value.js", type_only=True),
        type_index,
    )

    assert runtime.target_file == "src/value.ts"
    assert type_only.target_file == "src/value.d.ts"


def test_resolver_enforces_node_esm_extensions_but_substitutes_explicit_js(
    tmp_path: Path,
):
    package = tmp_path / "package.json"
    package.write_text('{"name":"app","type":"module"}', encoding="utf-8")
    config = tmp_path / "tsconfig.json"
    config.write_text('{"compilerOptions":{"module":"nodenext"}}', encoding="utf-8")
    source = "src/consumer.ts"
    index = _resolution_index(
        tmp_path,
        [source, "src/value.ts"],
        [package, config],
    )

    extensionless = resolve_javascript_import(_raw(source, "./value"), index)
    explicit = resolve_javascript_import(_raw(source, "./value.js"), index)

    assert extensionless.target_file is None
    assert extensionless.unresolved_reason == "not_indexed"
    assert explicit.target_file == "src/value.ts"
    assert explicit.control_files == ("package.json", "tsconfig.json")


def test_resolver_uses_module_suffixes_then_root_dirs(tmp_path: Path):
    config = tmp_path / "tsconfig.json"
    config.write_text(
        """
{
  "compilerOptions": {
    "moduleResolution": "bundler",
    "rootDirs": ["src", "generated"],
    "moduleSuffixes": [".native", ""]
  }
}
""".lstrip(),
        encoding="utf-8",
    )
    source = "src/views/page.ts"
    index = _resolution_index(
        tmp_path,
        [source, "generated/shared/item.native.ts"],
        [config],
    )

    resolved = resolve_javascript_import(_raw(source, "../shared/item"), index)

    assert resolved.target_file == "generated/shared/item.native.ts"
    assert resolved.basis == "compiler_root_dirs"
    assert resolved.control_files == ("tsconfig.json",)


def test_resolver_applies_paths_before_base_url(tmp_path: Path):
    config = tmp_path / "tsconfig.json"
    config.write_text(
        """
{
  "compilerOptions": {
    "moduleResolution": "bundler",
    "baseUrl": ".",
    "paths": {"@app/*": ["mapped/*", "fallback/*"]}
  }
}
""".lstrip(),
        encoding="utf-8",
    )
    source = "src/consumer.ts"
    index = _resolution_index(
        tmp_path,
        [source, "mapped/value.ts", "@app/value.ts"],
        [config],
    )

    resolved = resolve_javascript_import(_raw(source, "@app/value"), index)

    assert resolved.target_file == "mapped/value.ts"
    assert resolved.basis == "compiler_paths"
    assert resolved.control_files == ("tsconfig.json",)


def test_builder_selects_deepest_owning_config_and_jsconfig_preference(
    tmp_path: Path,
):
    root_config = tmp_path / "tsconfig.json"
    root_config.write_text(
        '{"compilerOptions":{"allowJs":true,"baseUrl":"root"}}',
        encoding="utf-8",
    )
    nested = tmp_path / "apps" / "web"
    nested.mkdir(parents=True)
    nested_ts = nested / "tsconfig.json"
    nested_ts.write_text(
        '{"compilerOptions":{"allowJs":true,"baseUrl":"ts"}}',
        encoding="utf-8",
    )
    nested_js = nested / "jsconfig.json"
    nested_js.write_text(
        '{"compilerOptions":{"baseUrl":"js"}}',
        encoding="utf-8",
    )
    source = "apps/web/src/page.js"
    index = _resolution_index(
        tmp_path,
        [source, "apps/web/js/value.js", "apps/web/ts/value.js", "root/value.js"],
        [root_config, nested_ts, nested_js],
    )

    resolved = resolve_javascript_import(_raw(source, "value"), index)

    assert resolved.target_file == "apps/web/js/value.js"
    assert resolved.basis == "compiler_base_url"
    assert resolved.control_files == ("apps/web/jsconfig.json",)


def _write_workspace_controls(tmp_path: Path, *, target_exports: object) -> list[Path]:
    root = tmp_path / "package.json"
    root.write_text(
        '{"name":"root","workspaces":["apps/*","packages/*"]}',
        encoding="utf-8",
    )
    app_dir = tmp_path / "apps" / "web"
    app_dir.mkdir(parents=True)
    app = app_dir / "package.json"
    app.write_text(
        '{"name":"@repo/web","dependencies":{"@repo/core":"workspace:*"}}',
        encoding="utf-8",
    )
    core_dir = tmp_path / "packages" / "core"
    core_dir.mkdir(parents=True)
    core = core_dir / "package.json"
    core.write_text(
        json.dumps({"name": "@repo/core", "exports": target_exports}),
        encoding="utf-8",
    )
    return [root, app, core]


def test_resolver_uses_declared_workspace_exports_with_control_provenance(
    tmp_path: Path,
):
    controls = _write_workspace_controls(
        tmp_path,
        target_exports={"./format": "./src/format.ts"},
    )
    source = "apps/web/src/page.ts"
    target = "packages/core/src/format.ts"
    index = _resolution_index(tmp_path, [source, target], controls)

    resolved = resolve_javascript_import(_raw(source, "@repo/core/format"), index)

    assert resolved.target_file == target
    assert resolved.basis == "workspace_exports"
    assert resolved.control_files == (
        "apps/web/package.json",
        "package.json",
        "packages/core/package.json",
    )


def test_resolver_does_not_guess_missing_workspace_build_output(tmp_path: Path):
    controls = _write_workspace_controls(
        tmp_path,
        target_exports={".": "./dist/index.js"},
    )
    source = "apps/web/src/page.ts"
    index = _resolution_index(
        tmp_path,
        [source, "packages/core/src/index.ts"],
        controls,
        allow_problems=True,
    )

    resolved = resolve_javascript_import(_raw(source, "@repo/core"), index)

    assert resolved.target_file is None
    assert resolved.unresolved_reason == "not_indexed"
    assert resolved.control_files == (
        "apps/web/package.json",
        "package.json",
        "packages/core/package.json",
    )


def test_resolver_requires_workspace_dependency_and_unique_package_name(tmp_path: Path):
    controls = _write_workspace_controls(tmp_path, target_exports="./src/index.ts")
    app = controls[1]
    app.write_text('{"name":"@repo/web"}', encoding="utf-8")
    duplicate_dir = tmp_path / "packages" / "duplicate"
    duplicate_dir.mkdir()
    duplicate = duplicate_dir / "package.json"
    duplicate.write_text('{"name":"@repo/core"}', encoding="utf-8")
    controls.append(duplicate)
    source = "apps/web/src/page.ts"
    index = _resolution_index(
        tmp_path,
        [source, "packages/core/src/index.ts"],
        controls,
        allow_problems=True,
    )

    undeclared = resolve_javascript_import(_raw(source, "@repo/core"), index)

    assert undeclared.target_file is None
    assert undeclared.unresolved_reason == "external"

    app.write_text(
        '{"name":"@repo/web","dependencies":{"@repo/core":"*"}}',
        encoding="utf-8",
    )
    ambiguous_index = _resolution_index(
        tmp_path,
        [source, "packages/core/src/index.ts"],
        controls,
        allow_problems=True,
    )
    ambiguous = resolve_javascript_import(
        _raw(source, "@repo/core"), ambiguous_index
    )
    assert ambiguous.unresolved_reason == "ambiguous"


def test_resolver_supports_private_imports_and_self_output_remapping(tmp_path: Path):
    package = tmp_path / "package.json"
    package.write_text(
        """
{
  "name": "@repo/core",
  "type": "module",
  "exports": {".": "./dist/index.js"},
  "imports": {"#internal": "./dist/internal.js"}
}
""".lstrip(),
        encoding="utf-8",
    )
    config = tmp_path / "tsconfig.json"
    config.write_text(
        '{"compilerOptions":{"module":"nodenext","rootDir":"src","outDir":"dist"}}',
        encoding="utf-8",
    )
    source = "src/consumer.ts"
    index = _resolution_index(
        tmp_path,
        [source, "src/index.ts", "src/internal.ts"],
        [package, config],
    )

    private = resolve_javascript_import(_raw(source, "#internal"), index)
    self_reference = resolve_javascript_import(_raw(source, "@repo/core"), index)

    assert private.target_file == "src/internal.ts"
    assert private.basis == "package_imports"
    assert self_reference.target_file == "src/index.ts"
    assert self_reference.basis == "package_self_reference"


def test_resolver_honours_package_conditions_and_reports_unknown_mode_ambiguity(
    tmp_path: Path,
):
    controls = _write_workspace_controls(
        tmp_path,
        target_exports={
            ".": {
                "types": "./src/index.d.ts",
                "import": "./src/index.ts",
                "require": "./src/index.cts",
                "default": "./src/fallback.ts",
            }
        },
    )
    source = "apps/web/src/page.ts"
    files = [
        source,
        "packages/core/src/index.d.ts",
        "packages/core/src/index.ts",
        "packages/core/src/index.cts",
        "packages/core/src/fallback.ts",
    ]
    index = _resolution_index(tmp_path, files, controls)

    type_only = resolve_javascript_import(
        _raw(source, "@repo/core", type_only=True), index
    )
    runtime = resolve_javascript_import(_raw(source, "@repo/core"), index)

    assert type_only.target_file == "packages/core/src/index.d.ts"
    assert runtime.target_file is None
    assert runtime.unresolved_reason == "ambiguous"


@pytest.mark.parametrize(
    ("specifier", "reason"),
    [
        ("../../escape", "invalid_specifier"),
        (".\\value", "invalid_specifier"),
        ("./bad%2Fvalue", "invalid_specifier"),
        ("https://example.com/mod.js", "external"),
        ("node:fs", "external"),
        ("fs", "external"),
    ],
)
def test_resolver_keeps_invalid_and_external_specifiers_as_non_edges(
    tmp_path: Path,
    specifier: str,
    reason: str,
):
    source = "src/consumer.ts"
    index = _resolution_index(tmp_path, [source])

    resolved = resolve_javascript_import(_raw(source, specifier), index)

    assert resolved.target_file is None
    assert resolved.unresolved_reason == reason


def test_resolver_fails_closed_for_unsupported_package_map_arrays(tmp_path: Path):
    controls = _write_workspace_controls(
        tmp_path,
        target_exports={".": ["./src/index.ts", "./src/fallback.ts"]},
    )
    source = "apps/web/src/page.ts"
    index = _resolution_index(
        tmp_path,
        [source, "packages/core/src/index.ts", "packages/core/src/fallback.ts"],
        controls,
    )

    resolved = resolve_javascript_import(_raw(source, "@repo/core"), index)

    assert resolved.target_file is None
    assert resolved.unresolved_reason == "unsupported_configuration"
