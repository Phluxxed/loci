from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest

from loci.graph.contracts import GraphContractError, GraphEdge, GraphEvidence
from loci.graph.go_modules import (
    GoModule,
    GoModuleContext,
    GoPackageBinding,
    GoPackageIndex,
    GoReplacement,
    GoRequirement,
    GoWorkspace,
    build_go_package_index,
    make_go_package_id,
)
from loci.graph.imports import (
    ImportRecord,
    materialize_import_edges,
    resolve_import,
    resolve_imports,
)
from loci.graph.javascript_modules import (
    build_javascript_resolution_index,
    load_javascript_module_context,
)
from loci.graph.rust_crates import (
    CargoContext,
    CargoPackage,
    RustDependency,
    RustTarget,
    build_rust_crate_index,
    make_rust_crate_id,
    resolve_rust_import,
)
from loci.parser.imports import RawImport, RustImportContext
from loci.parser.symbols import Symbol, make_file_symbol


SOURCE_HASH = "a" * 64
JAVASCRIPT_CANDIDATES = (
    "module.ts",
    "module.tsx",
    "module.js",
    "module/index.ts",
    "module/index.tsx",
    "module/index.js",
)


def _raw(
    specifier: str,
    *,
    source_file: str = "consumer.py",
    imported_name: str | None = None,
    line: int = 1,
    text: str | None = None,
) -> RawImport:
    return RawImport(
        source_file=source_file,
        language="python",
        line=line,
        text=text or (
            f"from {specifier} import {imported_name}"
            if imported_name is not None
            else f"import {specifier}"
        ),
        specifier=specifier,
        imported_name=imported_name,
        type_only=False,
        is_reexport=False,
        source_hash=SOURCE_HASH,
    )


def _file_nodes(*paths: str) -> dict[str, Symbol]:
    return {
        path: make_file_symbol(
            path,
            language="python",
            content_hash=SOURCE_HASH,
        )
        for path in paths
    }


def _javascript_raw(
    specifier: str,
    *,
    source_file: str = "src/consumer.ts",
    language: str = "typescript",
    type_only: bool = False,
    is_reexport: bool = False,
) -> RawImport:
    return RawImport(
        source_file=source_file,
        language=language,
        line=1,
        text=f'import {{value}} from "{specifier}";',
        specifier=specifier,
        imported_name=None,
        type_only=type_only,
        is_reexport=is_reexport,
        source_hash=SOURCE_HASH,
    )


def _javascript_file_nodes(*paths: str) -> dict[str, Symbol]:
    return {
        path: make_file_symbol(
            path,
            language=(
                "javascript"
                if path.endswith((".js", ".jsx"))
                else "typescript"
            ),
            content_hash=SOURCE_HASH,
        )
        for path in paths
    }


def _go_raw(
    specifier: str,
    *,
    source_file: str = "cmd/server/main.go",
    line: int = 4,
) -> RawImport:
    return RawImport(
        source_file=source_file,
        language="go",
        line=line,
        text=f'import "{specifier}"',
        specifier=specifier,
        imported_name=None,
        type_only=False,
        is_reexport=False,
        source_hash=SOURCE_HASH,
    )


def _go_file(path: str, package: str) -> Symbol:
    node = make_file_symbol(path, language="go", content_hash=SOURCE_HASH)
    node.metadata["loci"]["go_package"] = {"name": package, "line": 1}
    return node


def _go_file_nodes(*files: tuple[str, str]) -> dict[str, Symbol]:
    return {path: _go_file(path, package) for path, package in files}


def _rust_module_raw(*, inline: bool) -> RawImport:
    return RawImport(
        source_file="src/lib.rs",
        language="rust",
        line=1,
        text="mod model {" if inline else "mod model;",
        specifier="model",
        imported_name=None,
        type_only=False,
        is_reexport=False,
        source_hash=SOURCE_HASH,
        rust=RustImportContext(
            kind="module",
            lexical_module_path=(),
            visibility="private",
            module_level=True,
            configuration="unconditional",
            inline=inline,
        ),
    )


def _rust_raw(
    specifier: str,
    *,
    source_file: str = "app/src/lib.rs",
    kind: str = "use",
    imported_name: str | None = None,
    lexical_module_path: tuple[str, ...] = (),
    visibility: str = "private",
    configuration: str = "unconditional",
    inline: bool = False,
    module_level: bool = True,
    is_reexport: bool = False,
) -> RawImport:
    return RawImport(
        source_file=source_file,
        language="rust",
        line=3,
        text=f"{kind} {specifier}",
        specifier=specifier,
        imported_name=imported_name,
        type_only=False,
        is_reexport=is_reexport,
        source_hash=SOURCE_HASH,
        rust=RustImportContext(
            kind=kind,  # type: ignore[arg-type]
            lexical_module_path=lexical_module_path,
            visibility=visibility,
            module_level=module_level,
            configuration=configuration,  # type: ignore[arg-type]
            lexical_module_visibilities=("private",) * len(lexical_module_path),
            lexical_module_configurations=("unconditional",)
            * len(lexical_module_path),
            inline=inline,
        ),
    )


def _rust_file_nodes(*paths: str) -> dict[str, Symbol]:
    return {
        path: make_file_symbol(
            path,
            language="rust",
            content_hash=SOURCE_HASH,
        )
        for path in paths
    }


def _rust_package(
    *,
    source: str,
    root: str,
    name: str,
    root_file: str,
    edition: str = "2021",
    dependencies: tuple[RustDependency, ...] = (),
) -> CargoPackage:
    return CargoPackage(
        source=source,
        root=root,
        name=name,
        workspace_source=None,
        edition=edition,
        features={},
        dependencies=dependencies,
        targets=(
            RustTarget(
                "lib",
                name,
                name.replace("-", "_"),
                root_file,
                edition,
                (),
            ),
        ),
    )


def _rust_index(
    packages: tuple[CargoPackage, ...],
    *,
    file_nodes: dict[str, Symbol],
    observations: tuple[RawImport, ...] = (),
):
    build = build_rust_crate_index(
        CargoContext(packages=packages, workspaces=()),
        file_nodes=file_nodes,
        observations=observations,
    )
    assert build.problems == ()
    return build.index


def _go_module(
    root: str,
    module_path: str,
    *,
    requirements: tuple[GoRequirement, ...] = (),
    replacements: tuple[GoReplacement, ...] = (),
) -> GoModule:
    return GoModule(
        source="go.mod" if root == "." else f"{root}/go.mod",
        root=root,
        module_path=module_path,
        requirements=requirements,
        exclusions=(),
        replacements=replacements,
    )


def _go_package_index(
    file_nodes: dict[str, Symbol],
    *modules: GoModule,
    workspaces: tuple[GoWorkspace, ...] = (),
) -> GoPackageIndex:
    build = build_go_package_index(
        GoModuleContext(modules=modules, workspaces=workspaces),
        file_nodes=file_nodes,
    )
    assert build.problems == ()
    return build.index


def _package_symbol(directory: str, import_path: str) -> Symbol:
    return Symbol(
        id=make_go_package_id(directory, import_path),
        name="pkg",
        qualified_name=import_path,
        kind="package",
        language="go",
        file_path=f"{directory}/pkg.go",
        byte_offset=0,
        byte_length=0,
        content_hash=SOURCE_HASH,
        metadata={
            "loci": {
                "go_package_node": True,
                "directory": directory,
                "import_path": import_path,
                "package_name": "pkg",
            }
        },
        line=1,
        end_line=1,
    )


class _CountingBindings(tuple[GoPackageBinding, ...]):
    iterations = 0

    def __iter__(self):
        self.iterations += 1
        return super().__iter__()


class _CountingRustModules(dict):
    item_iterations = 0

    def items(self):
        self.item_iterations += 1
        return super().items()


def test_resolves_absolute_module_before_same_named_package():
    file_nodes = _file_nodes(
        "consumer.py",
        "pkg/mod.py",
        "pkg/mod/__init__.py",
    )

    record = resolve_import(_raw("pkg.mod"), file_nodes=file_nodes)

    assert record.status == "resolved"
    assert record.target_kind == "file"
    assert record.target_file == "pkg/mod.py"
    assert record.target_package is None
    assert record.target_id == file_nodes["pkg/mod.py"].id


def test_deep_import_does_not_fall_back_to_an_intermediate_package():
    file_nodes = _file_nodes("consumer.py", "pkg/__init__.py")

    record = resolve_import(_raw("pkg.missing"), file_nodes=file_nodes)

    assert record.status == "unresolved"
    assert record.unresolved_reason == "not_indexed"


def test_resolves_from_import_to_submodule_before_package_fallback():
    with_submodule = _file_nodes(
        "consumer.py",
        "pkg/__init__.py",
        "pkg/value.py",
    )
    without_submodule = _file_nodes("consumer.py", "pkg/__init__.py")

    submodule = resolve_import(
        _raw("pkg", imported_name="value"),
        file_nodes=with_submodule,
    )
    package = resolve_import(
        _raw("pkg", imported_name="value"),
        file_nodes=without_submodule,
    )

    assert submodule.target_file == "pkg/value.py"
    assert package.target_file == "pkg/__init__.py"


def test_resolves_star_import_to_package_itself():
    file_nodes = _file_nodes("consumer.py", "pkg/__init__.py")
    raw = _raw("pkg", text="from pkg import *")

    record = resolve_import(raw, file_nodes=file_nodes)

    assert record.target_file == "pkg/__init__.py"


def test_resolves_relative_dots_from_importing_package_directory():
    file_nodes = _file_nodes(
        "src/pkg/sub/consumer.py",
        "src/pkg/core.py",
    )

    record = resolve_import(
        _raw(
            "..core",
            source_file="src/pkg/sub/consumer.py",
            imported_name="Thing",
        ),
        file_nodes=file_nodes,
    )

    assert record.target_file == "src/pkg/core.py"


def test_resolves_repository_root_and_inferred_src_package_roots():
    file_nodes = _file_nodes(
        "consumer.py",
        "rootpkg.py",
        "src/loci/__init__.py",
    )

    root_record = resolve_import(_raw("rootpkg"), file_nodes=file_nodes)
    src_record = resolve_import(_raw("loci"), file_nodes=file_nodes)

    assert root_record.target_file == "rootpkg.py"
    assert src_record.target_file == "src/loci/__init__.py"


def test_reports_duplicate_valid_package_roots_as_ambiguous():
    file_nodes = _file_nodes(
        "consumer.py",
        "vendor_a/pkg/__init__.py",
        "vendor_b/pkg/__init__.py",
    )

    record = resolve_import(_raw("pkg"), file_nodes=file_nodes)

    assert record == ImportRecord(
        raw=_raw("pkg"),
        source_id=file_nodes["consumer.py"].id,
        target_file=None,
        target_package=None,
        target_crate=None,
        target_kind=None,
        target_id=None,
        status="unresolved",
        unresolved_reason="ambiguous",
    )


def test_missing_module_is_not_resolved_by_name_fallback():
    file_nodes = _file_nodes("consumer.py", "unrelated/same_name.py")

    record = resolve_import(_raw("same_name"), file_nodes=file_nodes)

    assert record.status == "unresolved"
    assert record.unresolved_reason == "not_indexed"
    assert record.target_file is None


def test_materializes_one_directed_edge_with_earliest_evidence():
    file_nodes = _file_nodes("consumer.py", "target.py")
    later = resolve_import(_raw("target", line=8), file_nodes=file_nodes)
    earlier = resolve_import(_raw("target", line=2), file_nodes=file_nodes)

    edges = materialize_import_edges(
        [later, earlier],
        file_nodes=file_nodes,
    )

    assert edges == [GraphEdge(
        from_id=file_nodes["consumer.py"].id,
        to_id=file_nodes["target.py"].id,
        type="imports",
        directed=True,
        namespace="loci",
        resolution="import-resolved",
        evidence=GraphEvidence(
            file="consumer.py",
            line=2,
            content_hash=SOURCE_HASH,
        ),
    )]


def test_materializes_one_go_package_edge_with_earliest_evidence():
    file_nodes = _go_file_nodes(
        ("cmd/server/main.go", "main"),
        ("internal/store/store.go", "store"),
        ("unrelated/store/store.go", "store"),
    )
    go_packages = _go_package_index(
        file_nodes,
        _go_module(".", "example.com/project"),
    )
    later = resolve_import(
        _go_raw("example.com/project/internal/store", line=8),
        file_nodes=file_nodes,
        go_packages=go_packages,
    )
    earlier = resolve_import(
        _go_raw("example.com/project/internal/store", line=2),
        file_nodes=file_nodes,
        go_packages=go_packages,
    )

    edges = materialize_import_edges(
        [later, earlier],
        file_nodes=file_nodes,
        go_packages=go_packages,
    )

    assert edges == [GraphEdge(
        from_id=file_nodes["cmd/server/main.go"].id,
        to_id=make_go_package_id(
            "internal/store",
            "example.com/project/internal/store",
        ),
        type="imports",
        directed=True,
        namespace="loci",
        resolution="import-resolved",
        evidence=GraphEvidence(
            file="cmd/server/main.go",
            line=2,
            content_hash=SOURCE_HASH,
        ),
    )]


def test_go_package_edge_rejects_invalid_package_metadata():
    file_nodes = _go_file_nodes(
        ("cmd/server/main.go", "main"),
        ("internal/store/store.go", "store"),
    )
    go_packages = _go_package_index(
        file_nodes,
        _go_module(".", "example.com/project"),
    )
    record = resolve_import(
        _go_raw("example.com/project/internal/store"),
        file_nodes=file_nodes,
        go_packages=go_packages,
    )
    go_packages.package_nodes[0].metadata["loci"]["package_name"] = "main"

    with pytest.raises(GraphContractError) as exc_info:
        materialize_import_edges(
            [record],
            file_nodes=file_nodes,
            go_packages=go_packages,
        )

    assert exc_info.value.code == "INVALID_GRAPH_SCHEMA"
    assert exc_info.value.details["field"] == "target_id"


@pytest.mark.parametrize(
    "winner_index",
    range(len(JAVASCRIPT_CANDIDATES)),
)
def test_javascript_relative_import_uses_fixed_candidate_order(
    winner_index: int,
):
    available = JAVASCRIPT_CANDIDATES[winner_index:]
    expected = JAVASCRIPT_CANDIDATES[winner_index]
    file_nodes = _javascript_file_nodes(
        "src/consumer.ts",
        *(f"src/{path}" for path in available),
    )

    record = resolve_import(
        _javascript_raw("./module"),
        file_nodes=file_nodes,
    )

    assert record.status == "resolved"
    assert record.target_kind == "file"
    assert record.target_file == f"src/{expected}"
    assert record.target_id == file_nodes[f"src/{expected}"].id
    assert record.resolution_basis == "relative_path"
    assert record.resolution_control_files == ()


def test_javascript_relative_import_resolves_parent_directory():
    file_nodes = _javascript_file_nodes(
        "src/ui/consumer.tsx",
        "src/shared.ts",
    )

    record = resolve_import(
        _javascript_raw(
            "../shared",
            source_file="src/ui/consumer.tsx",
        ),
        file_nodes=file_nodes,
    )

    assert record.target_file == "src/shared.ts"


@pytest.mark.parametrize(
    ("specifier", "language"),
    [("react", "javascript"), ("@scope/package", "typescript")],
)
def test_javascript_bare_package_is_external(
    specifier: str,
    language: str,
):
    source_file = "src/consumer.js" if language == "javascript" else "src/consumer.ts"
    file_nodes = _javascript_file_nodes(source_file)

    record = resolve_import(
        _javascript_raw(
            specifier,
            source_file=source_file,
            language=language,
        ),
        file_nodes=file_nodes,
    )

    assert record.status == "unresolved"
    assert record.unresolved_reason == "external"


def test_javascript_relative_import_cannot_escape_repository_root():
    file_nodes = _javascript_file_nodes("src/consumer.ts")

    record = resolve_import(
        _javascript_raw("../../outside"),
        file_nodes=file_nodes,
    )

    assert record.status == "unresolved"
    assert record.unresolved_reason == "invalid_specifier"


def test_javascript_relative_import_includes_jsx_in_extensionless_candidates():
    file_nodes = _javascript_file_nodes(
        "src/consumer.ts",
        "src/module.jsx",
    )

    record = resolve_import(
        _javascript_raw("./module"),
        file_nodes=file_nodes,
    )

    assert record.status == "resolved"
    assert record.target_file == "src/module.jsx"


def test_javascript_control_resolution_threads_record_provenance(tmp_path: Path):
    root = tmp_path / "package.json"
    root.write_text(
        json.dumps({"name": "root", "workspaces": ["apps/*", "packages/*"]}),
        encoding="utf-8",
    )
    app_dir = tmp_path / "apps" / "web"
    app_dir.mkdir(parents=True)
    app = app_dir / "package.json"
    app.write_text(
        json.dumps({
            "name": "@repo/web",
            "dependencies": {"@repo/core": "workspace:*"},
        }),
        encoding="utf-8",
    )
    core_dir = tmp_path / "packages" / "core"
    core_dir.mkdir(parents=True)
    core = core_dir / "package.json"
    core.write_text(
        json.dumps({
            "name": "@repo/core",
            "exports": {"./format": "./src/format.ts"},
        }),
        encoding="utf-8",
    )
    file_nodes = _javascript_file_nodes(
        "apps/web/src/page.ts",
        "packages/core/src/format.ts",
    )
    loaded = load_javascript_module_context(tmp_path, [root, app, core])
    javascript_index = build_javascript_resolution_index(
        loaded.context,
        file_nodes=file_nodes,
    ).index

    record = resolve_import(
        _javascript_raw(
            "@repo/core/format",
            source_file="apps/web/src/page.ts",
        ),
        file_nodes=file_nodes,
        javascript_modules=javascript_index,
    )

    assert record.status == "resolved"
    assert record.target_file == "packages/core/src/format.ts"
    assert record.resolution_basis == "workspace_exports"
    assert record.resolution_control_files == (
        "apps/web/package.json",
        "package.json",
        "packages/core/package.json",
    )


def test_javascript_reexport_preserves_record_flag():
    file_nodes = _javascript_file_nodes(
        "src/index.ts",
        "src/runtime.ts",
    )

    record = resolve_import(
        _javascript_raw(
            "./runtime",
            source_file="src/index.ts",
            is_reexport=True,
        ),
        file_nodes=file_nodes,
    )

    assert record.status == "resolved"
    assert record.target_file == "src/runtime.ts"
    assert record.raw.is_reexport is True


def test_go_without_package_index_remains_unsupported_language():
    file_nodes = _go_file_nodes(("cmd/server/main.go", "main"))

    record = resolve_import(
        _go_raw("example.com/project/store"),
        file_nodes=file_nodes,
    )

    assert record.status == "unresolved"
    assert record.unresolved_reason == "unsupported_language"


def test_go_same_module_import_resolves_package_target():
    file_nodes = _go_file_nodes(
        ("cmd/server/main.go", "main"),
        ("internal/store/store.go", "store"),
    )
    go_packages = _go_package_index(
        file_nodes,
        _go_module(".", "example.com/project"),
    )

    record = resolve_import(
        _go_raw("example.com/project/internal/store"),
        file_nodes=file_nodes,
        go_packages=go_packages,
    )

    assert record.status == "resolved"
    assert record.target_kind == "package"
    assert record.target_file is None
    assert record.target_package == "example.com/project/internal/store"
    assert record.target_id == make_go_package_id(
        "internal/store",
        "example.com/project/internal/store",
    )
    assert record.target_id != make_go_package_id(
        "unrelated/store",
        "example.com/project/unrelated/store",
    )


def test_go_workspace_import_resolves_used_module_package():
    file_nodes = _go_file_nodes(
        ("app/main.go", "main"),
        ("lib/logging/logging.go", "logging"),
    )
    workspace = GoWorkspace(
        source="go.work",
        root=".",
        go_version="1.23",
        use_roots=("app", "lib"),
        replacements=(),
    )
    go_packages = _go_package_index(
        file_nodes,
        _go_module("app", "example.com/app"),
        _go_module("lib", "example.com/lib"),
        workspaces=(workspace,),
    )

    record = resolve_import(
        _go_raw("example.com/lib/logging", source_file="app/main.go"),
        file_nodes=file_nodes,
        go_packages=go_packages,
    )

    assert record.status == "resolved"
    assert record.target_package == "example.com/lib/logging"
    assert record.target_id == make_go_package_id(
        "lib/logging",
        "example.com/lib/logging",
    )


def test_go_local_replacement_resolves_under_required_import_path():
    requirement = GoRequirement("example.com/dep", "v1.2.0")
    replacement = GoReplacement(
        module_path="example.com/dep",
        version=None,
        local_root="third_party/dep",
        remote_path=None,
        remote_version=None,
    )
    file_nodes = _go_file_nodes(
        ("app/main.go", "main"),
        ("third_party/dep/client/client.go", "client"),
    )
    go_packages = _go_package_index(
        file_nodes,
        _go_module(
            "app",
            "example.com/app",
            requirements=(requirement,),
            replacements=(replacement,),
        ),
        _go_module("third_party/dep", "local.invalid/dep"),
    )

    record = resolve_import(
        _go_raw("example.com/dep/client", source_file="app/main.go"),
        file_nodes=file_nodes,
        go_packages=go_packages,
    )

    assert record.status == "resolved"
    assert record.target_package == "example.com/dep/client"
    assert record.target_id == make_go_package_id(
        "third_party/dep/client",
        "example.com/dep/client",
    )


@pytest.mark.parametrize(
    ("required_version", "expected_status", "expected_reason"),
    [
        ("v1.2.0", "resolved", None),
        ("v1.3.0", "unresolved", "external"),
    ],
)
def test_go_version_specific_local_replacement_requires_exact_version(
    required_version: str,
    expected_status: str,
    expected_reason: str | None,
):
    replacement = GoReplacement(
        module_path="example.com/dep",
        version="v1.2.0",
        local_root="third_party/dep",
        remote_path=None,
        remote_version=None,
    )
    file_nodes = _go_file_nodes(
        ("app/main.go", "main"),
        ("third_party/dep/client/client.go", "client"),
    )
    go_packages = _go_package_index(
        file_nodes,
        _go_module(
            "app",
            "example.com/app",
            requirements=(GoRequirement("example.com/dep", required_version),),
            replacements=(replacement,),
        ),
        _go_module("third_party/dep", "local.invalid/dep"),
    )

    record = resolve_import(
        _go_raw("example.com/dep/client", source_file="app/main.go"),
        file_nodes=file_nodes,
        go_packages=go_packages,
    )

    assert record.status == expected_status
    assert record.unresolved_reason == expected_reason
    if expected_status == "resolved":
        assert record.target_id == make_go_package_id(
            "third_party/dep/client",
            "example.com/dep/client",
        )
    else:
        assert record.target_id is None


@pytest.mark.parametrize(
    "specifier",
    [
        "",
        "/absolute/pkg",
        "./relative",
        "../relative",
        "example.com//pkg",
        "example.com/./pkg",
        "example.com/pkg/..",
        "example.com/pkg/",
        "example.com\\pkg",
        "example.com/pkg\nother",
    ],
)
def test_go_rejects_noncanonical_import_specifiers(specifier: str):
    file_nodes = _go_file_nodes(("main.go", "main"))
    go_packages = _go_package_index(
        file_nodes,
        _go_module(".", "example.com/project"),
    )

    record = resolve_import(
        _go_raw(specifier, source_file="main.go"),
        file_nodes=file_nodes,
        go_packages=go_packages,
    )

    assert record.status == "unresolved"
    assert record.unresolved_reason == "invalid_specifier"


@pytest.mark.parametrize("specifier", ["C", "fmt", "example.net/remote/pkg"])
def test_go_unmatched_import_is_external(specifier: str):
    file_nodes = _go_file_nodes(("main.go", "main"))
    go_packages = _go_package_index(
        file_nodes,
        _go_module(".", "example.com/project"),
    )

    record = resolve_import(
        _go_raw(specifier, source_file="main.go"),
        file_nodes=file_nodes,
        go_packages=go_packages,
    )

    assert record.unresolved_reason == "external"


def test_go_source_without_module_owner_is_external():
    file_nodes = _go_file_nodes(("outside/main.go", "main"))
    go_packages = _go_package_index(
        file_nodes,
        _go_module("app", "example.com/app"),
    )

    record = resolve_import(
        _go_raw("example.com/app/pkg", source_file="outside/main.go"),
        file_nodes=file_nodes,
        go_packages=go_packages,
    )

    assert record.unresolved_reason == "external"


def test_go_eligible_binding_without_package_node_is_not_indexed():
    file_nodes = _go_file_nodes(("main.go", "main"))
    go_packages = _go_package_index(
        file_nodes,
        _go_module(".", "example.com/project"),
    )

    record = resolve_import(
        _go_raw("example.com/project/missing", source_file="main.go"),
        file_nodes=file_nodes,
        go_packages=go_packages,
    )

    assert record.unresolved_reason == "not_indexed"


def test_go_command_package_is_inaccessible():
    file_nodes = _go_file_nodes(
        ("main.go", "main"),
        ("cmd/tool/main.go", "main"),
    )
    go_packages = _go_package_index(
        file_nodes,
        _go_module(".", "example.com/project"),
    )

    record = resolve_import(
        _go_raw("example.com/project/cmd/tool", source_file="main.go"),
        file_nodes=file_nodes,
        go_packages=go_packages,
    )

    assert record.unresolved_reason == "inaccessible"


def test_go_internal_package_rejects_importer_outside_parent_tree():
    file_nodes = _go_file_nodes(
        ("app/main.go", "main"),
        ("lib/internal/store/store.go", "store"),
    )
    workspace = GoWorkspace(
        source="go.work",
        root=".",
        go_version="1.23",
        use_roots=("app", "lib"),
        replacements=(),
    )
    go_packages = _go_package_index(
        file_nodes,
        _go_module("app", "example.com/app"),
        _go_module("lib", "example.com/lib"),
        workspaces=(workspace,),
    )

    record = resolve_import(
        _go_raw("example.com/lib/internal/store", source_file="app/main.go"),
        file_nodes=file_nodes,
        go_packages=go_packages,
    )

    assert record.unresolved_reason == "inaccessible"


def test_go_more_specific_nested_module_does_not_fall_back_to_parent():
    file_nodes = _go_file_nodes(
        ("main.go", "main"),
        ("nested/pkg/pkg.go", "pkg"),
    )
    go_packages = _go_package_index(
        file_nodes,
        _go_module(".", "example.com/project"),
        _go_module("nested", "example.com/project/nested"),
    )

    record = resolve_import(
        _go_raw("example.com/project/nested/pkg", source_file="main.go"),
        file_nodes=file_nodes,
        go_packages=go_packages,
    )

    assert record.unresolved_reason == "external"


def test_go_longest_eligible_import_prefix_wins():
    source_module = _go_module("app", "example.com/app")
    broad_module = _go_module("broad", "broad.invalid/module")
    exact_module = _go_module("exact", "exact.invalid/module")
    broad = _package_symbol("broad/shared/pkg", "example.com/shared/pkg")
    exact = _package_symbol("exact/pkg", "example.com/shared/pkg")
    go_packages = GoPackageIndex(
        modules=(source_module, broad_module, exact_module),
        package_nodes=(broad, exact),
        bindings_by_source_module={
            "app": (
                GoPackageBinding("example.com", "broad", "broad.invalid/module", "go.work"),
                GoPackageBinding("example.com/shared", "exact", "exact.invalid/module", "go.work"),
            ),
        },
        packages_by_binding={
            ("broad", "example.com/shared/pkg"): broad,
            ("exact", "example.com/shared/pkg"): exact,
        },
        command_packages=frozenset(),
    )
    file_nodes = _go_file_nodes(("app/main.go", "main"))

    record = resolve_import(
        _go_raw("example.com/shared/pkg", source_file="app/main.go"),
        file_nodes=file_nodes,
        go_packages=go_packages,
    )

    assert record.target_id == exact.id


def test_go_distinct_targets_at_longest_prefix_are_ambiguous():
    source_module = _go_module("app", "example.com/app")
    first_module = _go_module("first", "first.invalid/module")
    second_module = _go_module("second", "second.invalid/module")
    first = _package_symbol("first/pkg", "example.com/shared/pkg")
    second = _package_symbol("second/pkg", "example.com/shared/pkg")
    go_packages = GoPackageIndex(
        modules=(source_module, first_module, second_module),
        package_nodes=(first, second),
        bindings_by_source_module={
            "app": (
                GoPackageBinding("example.com/shared", "first", "first.invalid/module", "go.work"),
                GoPackageBinding("example.com/shared", "second", "second.invalid/module", "go.work"),
            ),
        },
        packages_by_binding={
            ("first", "example.com/shared/pkg"): first,
            ("second", "example.com/shared/pkg"): second,
        },
        command_packages=frozenset(),
    )
    file_nodes = _go_file_nodes(("app/main.go", "main"))

    record = resolve_import(
        _go_raw("example.com/shared/pkg", source_file="app/main.go"),
        file_nodes=file_nodes,
        go_packages=go_packages,
    )

    assert record.status == "unresolved"
    assert record.unresolved_reason == "ambiguous"


def test_resolve_imports_threads_go_packages_without_changing_python():
    file_nodes = {
        **_file_nodes("consumer.py", "target.py"),
        **_go_file_nodes(
            ("main.go", "main"),
            ("store/store.go", "store"),
        ),
    }
    go_packages = _go_package_index(
        file_nodes,
        _go_module(".", "example.com/project"),
    )

    python_record, go_record = resolve_imports(
        (
            _raw("target"),
            _go_raw("example.com/project/store", source_file="main.go"),
        ),
        file_nodes=file_nodes,
        go_packages=go_packages,
    )

    assert python_record.target_kind == "file"
    assert python_record.target_file == "target.py"
    assert go_record.target_kind == "package"
    assert go_record.target_package == "example.com/project/store"


def test_resolve_imports_indexes_go_bindings_once_per_batch():
    source_module = _go_module("app", "example.com/app")
    bindings = _CountingBindings(
        GoPackageBinding(
            f"example.com/dep{index}",
            f"dep{index}",
            f"example.com/dep{index}",
            "go.work",
        )
        for index in range(100)
    )
    go_packages = GoPackageIndex(
        modules=(source_module,),
        package_nodes=(),
        bindings_by_source_module={"app": bindings},
        packages_by_binding={},
        command_packages=frozenset(),
    )
    file_nodes = _go_file_nodes(("app/main.go", "main"))
    raw_imports = tuple(
        _go_raw(f"outside.example/pkg{index}", source_file="app/main.go")
        for index in range(100)
    )

    records = resolve_imports(
        raw_imports,
        file_nodes=file_nodes,
        go_packages=go_packages,
    )

    assert all(record.unresolved_reason == "external" for record in records)
    assert bindings.iterations == 1


def test_resolve_imports_ignores_inline_rust_module_metadata():
    file_nodes = {
        "src/lib.rs": make_file_symbol(
            "src/lib.rs",
            language="rust",
            content_hash=SOURCE_HASH,
        )
    }

    records = resolve_imports(
        (_rust_module_raw(inline=True), _rust_module_raw(inline=False)),
        file_nodes=file_nodes,
    )

    assert len(records) == 1
    assert records[0].raw.rust is not None
    assert records[0].raw.rust.inline is False
    assert records[0].status == "unresolved"
    assert records[0].unresolved_reason == "unsupported_language"


def test_resolve_import_rejects_inline_rust_module_metadata():
    file_nodes = {
        "src/lib.rs": make_file_symbol(
            "src/lib.rs",
            language="rust",
            content_hash=SOURCE_HASH,
        )
    }

    with pytest.raises(
        GraphContractError,
        match="inline Rust module observations are metadata, not imports",
    ):
        resolve_import(_rust_module_raw(inline=True), file_nodes=file_nodes)


def test_rust_without_crate_index_remains_unsupported_language():
    raw = _rust_raw("crate::thing")
    file_nodes = _rust_file_nodes("app/src/lib.rs")

    record = resolve_import(raw, file_nodes=file_nodes)

    assert record.unresolved_reason == "unsupported_language"


def test_rust_external_module_declaration_resolves_exact_file():
    package = _rust_package(
        source="app/Cargo.toml",
        root="app",
        name="app",
        root_file="app/src/lib.rs",
    )
    raw = _rust_raw("api", kind="module")
    file_nodes = _rust_file_nodes("app/src/lib.rs", "app/src/api.rs")
    index = _rust_index(
        (package,),
        file_nodes=file_nodes,
        observations=(raw,),
    )

    resolution = resolve_rust_import(raw, index=index)
    record = resolve_import(raw, file_nodes=file_nodes, rust_crates=index)

    assert resolution.target_file == "app/src/api.rs"
    assert resolution.basis == "rust_module_declaration"
    assert record.target_kind == "file"
    assert record.target_file == "app/src/api.rs"
    assert record.target_id == file_nodes["app/src/api.rs"].id
    assert record.resolution_configuration == "unconditional"
    assert record.resolution_control_files == ("app/Cargo.toml",)


def test_rust_external_module_missing_from_frozen_index_is_not_indexed():
    package = _rust_package(
        source="app/Cargo.toml",
        root="app",
        name="app",
        root_file="app/src/lib.rs",
    )
    raw = _rust_raw("missing", kind="module")
    file_nodes = _rust_file_nodes("app/src/lib.rs")
    index = _rust_index((package,), file_nodes=file_nodes)

    record = resolve_import(raw, file_nodes=file_nodes, rust_crates=index)

    assert record.unresolved_reason == "not_indexed"


def test_rust_external_module_preserves_ambiguous_source_outcome():
    package = _rust_package(
        source="app/Cargo.toml",
        root="app",
        name="app",
        root_file="app/src/lib.rs",
    )
    raw = _rust_raw("duplicate", kind="module")
    file_nodes = _rust_file_nodes(
        "app/src/lib.rs",
        "app/src/duplicate.rs",
        "app/src/duplicate/mod.rs",
    )
    build = build_rust_crate_index(
        CargoContext(packages=(package,), workspaces=()),
        file_nodes=file_nodes,
        observations=(raw,),
    )

    record = resolve_import(
        raw,
        file_nodes=file_nodes,
        rust_crates=build.index,
    )

    assert build.problems[0].details["reason"] == "ambiguous_module_source"
    assert record.unresolved_reason == "ambiguous"


def test_rust_source_outside_crate_module_ownership_is_unsupported():
    package = _rust_package(
        source="app/Cargo.toml",
        root="app",
        name="app",
        root_file="app/src/lib.rs",
    )
    raw = _rust_raw("crate::Thing", source_file="loose.rs")
    file_nodes = _rust_file_nodes("app/src/lib.rs", "loose.rs")
    index = _rust_index((package,), file_nodes=file_nodes)

    record = resolve_import(raw, file_nodes=file_nodes, rust_crates=index)

    assert record.unresolved_reason == "unsupported_configuration"


def test_rust_current_crate_terminal_item_targets_crate_node():
    package = _rust_package(
        source="app/Cargo.toml",
        root="app",
        name="app",
        root_file="app/src/lib.rs",
    )
    raw = _rust_raw("crate::Thing")
    file_nodes = _rust_file_nodes("app/src/lib.rs")
    index = _rust_index((package,), file_nodes=file_nodes)

    record = resolve_import(raw, file_nodes=file_nodes, rust_crates=index)

    crate_id = make_rust_crate_id("app/Cargo.toml", "lib", "app")
    assert record.target_kind == "crate"
    assert record.target_file is None
    assert record.target_crate == crate_id.removesuffix("#crate")
    assert record.target_id == crate_id
    assert record.resolution_basis == "rust_module_path"
    assert record.resolution_configuration == "unconditional"


def test_rust_path_dependency_resolves_deepest_public_module_file():
    dependency = RustDependency(
        alias="core_alias",
        package_name="core",
        kind="normal",
        path="core",
        optional=True,
        default_features=True,
        features=(),
        target_condition=None,
        inherited=False,
        source="app/Cargo.toml",
    )
    app = _rust_package(
        source="app/Cargo.toml",
        root="app",
        name="app",
        root_file="app/src/lib.rs",
        dependencies=(dependency,),
    )
    core = _rust_package(
        source="core/Cargo.toml",
        root="core",
        name="core",
        root_file="core/src/lib.rs",
    )
    module = _rust_raw(
        "api",
        source_file="core/src/lib.rs",
        kind="module",
        visibility="pub",
    )
    raw = _rust_raw("core_alias::api::Thing")
    file_nodes = _rust_file_nodes(
        "app/src/lib.rs",
        "core/src/lib.rs",
        "core/src/api.rs",
    )
    index = _rust_index(
        (app, core),
        file_nodes=file_nodes,
        observations=(module,),
    )

    record = resolve_import(raw, file_nodes=file_nodes, rust_crates=index)

    assert record.target_kind == "file"
    assert record.target_file == "core/src/api.rs"
    assert record.resolution_basis == "cargo_path_dependency"
    assert record.resolution_control_files == (
        "app/Cargo.toml",
        "core/Cargo.toml",
    )
    assert record.resolution_configuration == "declared_possible"


def test_rust_path_dependency_terminal_item_targets_dependency_crate():
    dependency = RustDependency(
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
    )
    app = _rust_package(
        source="app/Cargo.toml",
        root="app",
        name="app",
        root_file="app/src/lib.rs",
        dependencies=(dependency,),
    )
    core = _rust_package(
        source="core/Cargo.toml",
        root="core",
        name="core",
        root_file="core/src/lib.rs",
    )
    raw = _rust_raw("core_alias::Thing")
    file_nodes = _rust_file_nodes("app/src/lib.rs", "core/src/lib.rs")
    index = _rust_index((app, core), file_nodes=file_nodes)

    record = resolve_import(raw, file_nodes=file_nodes, rust_crates=index)

    core_id = make_rust_crate_id("core/Cargo.toml", "lib", "core")
    assert record.target_kind == "crate"
    assert record.target_crate == core_id.removesuffix("#crate")
    assert record.target_id == core_id
    assert record.resolution_basis == "cargo_path_dependency"


def test_rust_dependency_private_module_is_inaccessible():
    dependency = RustDependency(
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
    )
    app = _rust_package(
        source="app/Cargo.toml",
        root="app",
        name="app",
        root_file="app/src/lib.rs",
        dependencies=(dependency,),
    )
    core = _rust_package(
        source="core/Cargo.toml",
        root="core",
        name="core",
        root_file="core/src/lib.rs",
    )
    private_module = _rust_raw(
        "private_api",
        source_file="core/src/lib.rs",
        kind="module",
    )
    raw = _rust_raw("core_alias::private_api::Thing")
    file_nodes = _rust_file_nodes(
        "app/src/lib.rs",
        "core/src/lib.rs",
        "core/src/private_api.rs",
    )
    index = _rust_index(
        (app, core),
        file_nodes=file_nodes,
        observations=(private_module,),
    )

    record = resolve_import(raw, file_nodes=file_nodes, rust_crates=index)

    assert record.status == "unresolved"
    assert record.unresolved_reason == "inaccessible"


def test_rust_2015_dependency_requires_explicit_extern_crate_binding():
    dependency = RustDependency(
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
    )
    app = _rust_package(
        source="app/Cargo.toml",
        root="app",
        name="app",
        root_file="app/src/lib.rs",
        edition="2015",
        dependencies=(dependency,),
    )
    core = _rust_package(
        source="core/Cargo.toml",
        root="core",
        name="core",
        root_file="core/src/lib.rs",
    )
    extern = _rust_raw(
        "core_alias",
        kind="extern_crate",
        imported_name="external",
    )
    missing = _rust_raw("core_alias::Thing")
    explicit = _rust_raw("external::Thing")
    file_nodes = _rust_file_nodes("app/src/lib.rs", "core/src/lib.rs")
    index = _rust_index(
        (app, core),
        file_nodes=file_nodes,
        observations=(extern,),
    )

    missing_record = resolve_import(
        missing,
        file_nodes=file_nodes,
        rust_crates=index,
    )
    explicit_record = resolve_import(
        explicit,
        file_nodes=file_nodes,
        rust_crates=index,
    )

    assert missing_record.unresolved_reason == "external"
    assert explicit_record.status == "resolved"
    assert explicit_record.resolution_basis == "cargo_path_dependency"


def test_rust_module_alias_resolves_through_canonical_module_route():
    package = _rust_package(
        source="app/Cargo.toml",
        root="app",
        name="app",
        root_file="app/src/lib.rs",
    )
    module = _rust_raw("api", kind="module", visibility="pub")
    alias = _rust_raw("crate::api", imported_name="facade")
    raw = _rust_raw("facade::Thing")
    file_nodes = _rust_file_nodes("app/src/lib.rs", "app/src/api.rs")
    index = _rust_index(
        (package,),
        file_nodes=file_nodes,
        observations=(module, alias),
    )

    record = resolve_import(raw, file_nodes=file_nodes, rust_crates=index)

    assert record.target_file == "app/src/api.rs"
    assert record.resolution_basis == "rust_module_path"


def test_rust_2018_local_module_shadows_dependency_but_absolute_path_does_not():
    dependency = RustDependency(
        alias="api",
        package_name="core",
        kind="normal",
        path="core",
        optional=False,
        default_features=True,
        features=(),
        target_condition=None,
        inherited=False,
        source="app/Cargo.toml",
    )
    app = _rust_package(
        source="app/Cargo.toml",
        root="app",
        name="app",
        root_file="app/src/lib.rs",
        dependencies=(dependency,),
    )
    core = _rust_package(
        source="core/Cargo.toml",
        root="core",
        name="core",
        root_file="core/src/lib.rs",
    )
    local_module = _rust_raw("api", kind="module")
    bare = _rust_raw("api::Thing")
    absolute = _rust_raw("::api::Thing")
    file_nodes = _rust_file_nodes(
        "app/src/lib.rs",
        "app/src/api.rs",
        "core/src/lib.rs",
    )
    index = _rust_index(
        (app, core),
        file_nodes=file_nodes,
        observations=(local_module,),
    )

    bare_record = resolve_import(bare, file_nodes=file_nodes, rust_crates=index)
    absolute_record = resolve_import(
        absolute,
        file_nodes=file_nodes,
        rust_crates=index,
    )

    assert bare_record.target_file == "app/src/api.rs"
    assert bare_record.resolution_basis == "rust_module_path"
    assert absolute_record.target_kind == "crate"
    assert absolute_record.target_id == make_rust_crate_id(
        "core/Cargo.toml",
        "lib",
        "core",
    )
    assert absolute_record.resolution_basis == "cargo_path_dependency"


def test_rust_self_and_super_paths_use_exact_lexical_module_scope():
    package = _rust_package(
        source="app/Cargo.toml",
        root="app",
        name="app",
        root_file="app/src/lib.rs",
    )
    outer = _rust_raw("outer", kind="module", inline=True)
    child = _rust_raw(
        "child",
        kind="module",
        lexical_module_path=("outer",),
    )
    self_raw = _rust_raw(
        "self::child::Thing",
        lexical_module_path=("outer",),
    )
    super_raw = _rust_raw(
        "super::RootThing",
        lexical_module_path=("outer",),
    )
    file_nodes = _rust_file_nodes(
        "app/src/lib.rs",
        "app/src/outer/child.rs",
    )
    index = _rust_index(
        (package,),
        file_nodes=file_nodes,
        observations=(outer, child),
    )

    self_record = resolve_import(
        self_raw,
        file_nodes=file_nodes,
        rust_crates=index,
    )
    super_record = resolve_import(
        super_raw,
        file_nodes=file_nodes,
        rust_crates=index,
    )

    assert self_record.target_file == "app/src/outer/child.rs"
    assert super_record.target_kind == "crate"
    assert super_record.target_id == make_rust_crate_id(
        "app/Cargo.toml",
        "lib",
        "app",
    )


def test_rust_shared_source_resolves_only_when_crate_contexts_converge():
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
            RustTarget("bin", "tool", "tool", "shared.rs", "2021", ()),
        ),
    )
    module = _rust_raw(
        "child",
        source_file="shared.rs",
        kind="module",
    )
    convergent = _rust_raw(
        "crate::child::Thing",
        source_file="shared.rs",
    )
    divergent = _rust_raw("crate::Thing", source_file="shared.rs")
    file_nodes = _rust_file_nodes("shared.rs", "shared/child.rs")
    index = _rust_index(
        (package,),
        file_nodes=file_nodes,
        observations=(module,),
    )

    convergent_record = resolve_import(
        convergent,
        file_nodes=file_nodes,
        rust_crates=index,
    )
    divergent_record = resolve_import(
        divergent,
        file_nodes=file_nodes,
        rust_crates=index,
    )

    assert convergent_record.target_file == "shared/child.rs"
    assert divergent_record.status == "unresolved"
    assert divergent_record.unresolved_reason == "ambiguous"


def test_rust_binary_uses_same_package_library_crate_binding():
    package = CargoPackage(
        source="Cargo.toml",
        root=".",
        name="app",
        workspace_source=None,
        edition="2021",
        features={},
        dependencies=(),
        targets=(
            RustTarget("lib", "app", "app", "src/lib.rs", "2021", ()),
            RustTarget("bin", "app", "app", "src/main.rs", "2021", ()),
        ),
    )
    raw = _rust_raw("app::Thing", source_file="src/main.rs")
    file_nodes = _rust_file_nodes("src/lib.rs", "src/main.rs")
    index = _rust_index((package,), file_nodes=file_nodes)

    record = resolve_import(raw, file_nodes=file_nodes, rust_crates=index)

    assert record.target_kind == "crate"
    assert record.target_id == make_rust_crate_id("Cargo.toml", "lib", "app")
    assert record.resolution_basis == "cargo_package_library"
    assert record.resolution_control_files == ("Cargo.toml",)


@pytest.mark.parametrize("specifier", ["std::fmt", "missing::Thing"])
def test_rust_uncontained_or_standard_crates_are_external(specifier: str):
    package = _rust_package(
        source="app/Cargo.toml",
        root="app",
        name="app",
        root_file="app/src/lib.rs",
    )
    raw = _rust_raw(specifier)
    file_nodes = _rust_file_nodes("app/src/lib.rs")
    index = _rust_index((package,), file_nodes=file_nodes)

    record = resolve_import(raw, file_nodes=file_nodes, rust_crates=index)

    assert record.unresolved_reason == "external"


@pytest.mark.parametrize(
    ("specifier", "configuration", "reason"),
    [
        ("crate::::Thing", "unconditional", "invalid_specifier"),
        ("::crate::Thing", "unconditional", "invalid_specifier"),
        ("crate::super::Thing", "unconditional", "invalid_specifier"),
        ("super::Thing", "unconditional", "invalid_specifier"),
        ("crate::Thing", "unsupported", "unsupported_configuration"),
    ],
)
def test_rust_fail_closed_outcomes(
    specifier: str,
    configuration: str,
    reason: str,
):
    package = _rust_package(
        source="app/Cargo.toml",
        root="app",
        name="app",
        root_file="app/src/lib.rs",
    )
    raw = _rust_raw(specifier, configuration=configuration)
    file_nodes = _rust_file_nodes("app/src/lib.rs")
    index = _rust_index((package,), file_nodes=file_nodes)

    record = resolve_import(raw, file_nodes=file_nodes, rust_crates=index)

    assert record.status == "unresolved"
    assert record.unresolved_reason == reason


def test_rust_import_path_depth_is_bounded(monkeypatch: pytest.MonkeyPatch):
    package = _rust_package(
        source="app/Cargo.toml",
        root="app",
        name="app",
        root_file="app/src/lib.rs",
    )
    raw = _rust_raw("crate::one::two")
    file_nodes = _rust_file_nodes("app/src/lib.rs")
    index = _rust_index((package,), file_nodes=file_nodes)
    monkeypatch.setattr("loci.graph.rust_crates.MAX_RUST_MODULE_DEPTH", 2)

    record = resolve_import(raw, file_nodes=file_nodes, rust_crates=index)

    assert record.unresolved_reason == "invalid_specifier"


def test_resolve_imports_threads_rust_index_without_changing_python():
    package = _rust_package(
        source="app/Cargo.toml",
        root="app",
        name="app",
        root_file="app/src/lib.rs",
    )
    file_nodes = {
        **_file_nodes("consumer.py", "target.py"),
        **_rust_file_nodes("app/src/lib.rs"),
    }
    index = _rust_index((package,), file_nodes=file_nodes)

    python_record, rust_record = resolve_imports(
        (_raw("target"), _rust_raw("crate::Thing")),
        file_nodes=file_nodes,
        rust_crates=index,
    )

    assert python_record.target_file == "target.py"
    assert python_record.resolution_basis is None
    assert rust_record.target_kind == "crate"
    assert rust_record.resolution_basis == "rust_module_path"


def test_resolve_imports_indexes_rust_source_ownership_once_per_batch():
    package = _rust_package(
        source="app/Cargo.toml",
        root="app",
        name="app",
        root_file="app/src/lib.rs",
    )
    file_nodes = _rust_file_nodes("app/src/lib.rs")
    index = _rust_index((package,), file_nodes=file_nodes)
    counting_modules = _CountingRustModules(index.modules_by_crate_path)
    counted_index = replace(
        index,
        modules_by_crate_path=counting_modules,
    )
    raw_imports = tuple(
        _rust_raw(f"crate::Thing{number}")
        for number in range(100)
    )

    records = resolve_imports(
        raw_imports,
        file_nodes=file_nodes,
        rust_crates=counted_index,
    )

    assert all(record.status == "resolved" for record in records)
    assert counting_modules.item_iterations == 1
