from __future__ import annotations

import json
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


def test_rust_remains_unsupported_language():
    raw = RawImport(
        source_file="src/lib.rs",
        language="rust",
        line=1,
        text="use crate::thing;",
        specifier="crate::thing",
        imported_name=None,
        type_only=False,
        is_reexport=False,
        source_hash=SOURCE_HASH,
    )
    file_nodes = {
        "src/lib.rs": make_file_symbol(
            "src/lib.rs",
            language="rust",
            content_hash=SOURCE_HASH,
        )
    }

    record = resolve_import(raw, file_nodes=file_nodes)

    assert record.unresolved_reason == "unsupported_language"
