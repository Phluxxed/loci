from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

import loci.graph.go_modules as go_modules
from loci.graph.contracts import GraphContractError
from loci.graph.go_modules import (
    GoExclusion,
    GoModule,
    GoModuleContext,
    GoPackageBinding,
    GoReplacement,
    GoRequirement,
    GoWorkspace,
    build_go_package_index,
    load_go_module_context,
)
from loci.parser.symbols import Symbol, make_file_symbol


def _go_file(
    path: str,
    package: str | None,
    *,
    content_hash: str | None = None,
    line: int = 1,
) -> Symbol:
    node = make_file_symbol(
        path,
        language="go",
        content_hash=content_hash or hashlib.sha256(path.encode()).hexdigest(),
    )
    if package is not None:
        node.metadata["loci"]["go_package"] = {"name": package, "line": line}
    return node


def _module(
    *,
    root: str = ".",
    module_path: str = "example.com/project",
    requirements: tuple[GoRequirement, ...] = (),
    exclusions: tuple[GoExclusion, ...] = (),
    replacements: tuple[GoReplacement, ...] = (),
) -> GoModule:
    source = "go.mod" if root == "." else f"{root}/go.mod"
    return GoModule(
        source=source,
        root=root,
        module_path=module_path,
        requirements=requirements,
        exclusions=exclusions,
        replacements=replacements,
    )


def test_loader_parses_go_mod_directives_and_blocks(tmp_path: Path):
    go_mod = tmp_path / "go.mod"
    go_mod.write_text(
        """
module (
    "example.com/proj\\ect"
)

require (
    example.com/z v1.2.0 // indirect
    `example.com/a` `v1.0.0`
)
exclude example.com/z v1.1.0
exclude (
    example.com/a v0.9.0
)
replace (
    example.com/a => ./local/a
    example.com/local v1.2.3 => ./local/versioned
    example.com/z v1.2.0 => "example.com/fork/z" "v1.2.1"
)
toolchain go1.23.0
""".lstrip(),
        encoding="utf-8",
    )

    loaded = load_go_module_context(tmp_path, [go_mod])

    assert loaded.problems == ()
    assert loaded.input_hashes == {
        "go.mod": hashlib.sha256(go_mod.read_bytes()).hexdigest(),
    }
    assert len(loaded.context.modules) == 1
    module = loaded.context.modules[0]
    assert module.source == "go.mod"
    assert module.root == "."
    assert module.module_path == "example.com/project"
    assert module.requirements == (
        GoRequirement("example.com/a", "v1.0.0"),
        GoRequirement("example.com/z", "v1.2.0"),
    )
    assert module.exclusions == (
        GoExclusion("example.com/a", "v0.9.0"),
        GoExclusion("example.com/z", "v1.1.0"),
    )
    assert module.replacements == (
        GoReplacement(
            module_path="example.com/a",
            version=None,
            local_root="local/a",
            remote_path=None,
            remote_version=None,
        ),
        GoReplacement(
            module_path="example.com/local",
            version="v1.2.3",
            local_root="local/versioned",
            remote_path=None,
            remote_version=None,
        ),
        GoReplacement(
            module_path="example.com/z",
            version="v1.2.0",
            local_root=None,
            remote_path="example.com/fork/z",
            remote_version="v1.2.1",
        ),
    )


def test_loader_parses_go_work_use_and_replace_blocks(tmp_path: Path):
    go_work = tmp_path / "go.work"
    go_work.write_text(
        """
go 1.23.0
use (
    ./app // primary
    `./lib`
)
replace (
    example.com/old => ./local/old
    example.com/remote v1.0.0 => example.com/fork v1.1.0
)
godebug default=go1.21
""".lstrip(),
        encoding="utf-8",
    )

    loaded = load_go_module_context(tmp_path, [go_work])

    assert loaded.problems == ()
    assert loaded.context.modules == ()
    assert len(loaded.context.workspaces) == 1
    workspace = loaded.context.workspaces[0]
    assert workspace.source == "go.work"
    assert workspace.root == "."
    assert workspace.go_version == "1.23.0"
    assert workspace.use_roots == ("app", "lib")
    assert workspace.replacements == (
        GoReplacement(
            module_path="example.com/old",
            version=None,
            local_root="local/old",
            remote_path=None,
            remote_version=None,
        ),
        GoReplacement(
            module_path="example.com/remote",
            version="v1.0.0",
            local_root=None,
            remote_path="example.com/fork",
            remote_version="v1.1.0",
        ),
    )


@pytest.mark.parametrize(
    ("content", "reason"),
    [
        ("require example.com/a v1.0.0\n", "module_directive_count"),
        ("module example.com/a\nmodule example.com/b\n", "module_directive_count"),
        ("module example.com/a\nrequire example.com/b\n", "invalid_require"),
        ("module example.com/a\nrequire (\nexample.com/b v1.0.0\n", "unterminated_block"),
        ("module \"example.com/a\n", "unterminated_string"),
        ("module example.com/a /* bad */\n", "block_comments_not_allowed"),
        ("module example.com/a\n)\n", "unexpected_block_close"),
    ],
)
def test_loader_rejects_malformed_go_mod_as_one_problem(
    tmp_path: Path,
    content: str,
    reason: str,
):
    go_mod = tmp_path / "go.mod"
    go_mod.write_text(content, encoding="utf-8")

    loaded = load_go_module_context(tmp_path, [go_mod])

    assert loaded.context.modules == ()
    assert len(loaded.problems) == 1
    assert loaded.problems[0].code == "GRAPH_GO_MODULE_INVALID"
    assert loaded.problems[0].source == "go.mod"
    assert loaded.problems[0].details["reason"] == reason
    assert loaded.input_hashes["go.mod"] == hashlib.sha256(
        go_mod.read_bytes()
    ).hexdigest()


@pytest.mark.parametrize(
    ("content", "reason"),
    [
        ("use ./app\n", "go_directive_count"),
        ("go 1.22\ngo 1.23\nuse ./app\n", "go_directive_count"),
        ("go latest\nuse ./app\n", "invalid_go_version"),
        ("go 1.23\nuse ./app extra\n", "invalid_use"),
        ("go 1.23\nmodule example.com/a\n", "module_directive_in_go_work"),
    ],
)
def test_loader_rejects_malformed_go_work_as_one_problem(
    tmp_path: Path,
    content: str,
    reason: str,
):
    go_work = tmp_path / "go.work"
    go_work.write_text(content, encoding="utf-8")

    loaded = load_go_module_context(tmp_path, [go_work])

    assert loaded.context.workspaces == ()
    assert len(loaded.problems) == 1
    assert loaded.problems[0].code == "GRAPH_GO_WORKSPACE_INVALID"
    assert loaded.problems[0].source == "go.work"
    assert loaded.problems[0].details["reason"] == reason


def test_loader_rejects_control_symlink_outside_path_and_oversized_file_without_reading(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    outside = tmp_path.parent / f"{tmp_path.name}-outside"
    outside.mkdir()
    outside_go_mod = outside / "go.mod"
    outside_go_mod.write_text("module example.com/outside\n", encoding="utf-8")

    linked_dir = tmp_path / "linked"
    linked_dir.mkdir()
    linked_go_mod = linked_dir / "go.mod"
    linked_go_mod.symlink_to(outside_go_mod)

    large_dir = tmp_path / "large"
    large_dir.mkdir()
    large_go_work = large_dir / "go.work"
    large_go_work.write_bytes(b"x" * (go_modules.MAX_GO_CONTROL_BYTES + 1))

    def fail_if_read(*args: object, **kwargs: object) -> tuple[bytes, str]:
        raise AssertionError("invalid control candidate was read")

    monkeypatch.setattr(go_modules, "read_contained_file", fail_if_read)

    loaded = load_go_module_context(
        tmp_path,
        [outside_go_mod, linked_go_mod, large_go_work],
    )

    assert loaded.context == go_modules.GoModuleContext((), ())
    assert [(problem.source, problem.details["reason"]) for problem in loaded.problems] == [
        ("@outside/go.mod", "outside_repository"),
        ("large/go.work", "control_file_too_large"),
        ("linked/go.mod", "symlink"),
    ]
    assert loaded.problems[1].code == "GRAPH_GO_INDEX_LIMIT_EXCEEDED"
    assert all(len(value) == 64 for value in loaded.input_hashes.values())


def test_loader_rejects_invalid_utf8_and_preserves_content_hash(tmp_path: Path):
    go_mod = tmp_path / "go.mod"
    go_mod.write_bytes(b"module example.com/a\n\xff")

    loaded = load_go_module_context(tmp_path, [go_mod])

    assert loaded.context.modules == ()
    assert loaded.problems[0].details == {"reason": "invalid_utf8"}
    assert loaded.input_hashes["go.mod"] == hashlib.sha256(
        go_mod.read_bytes()
    ).hexdigest()


def test_loader_rejects_directive_limit_without_partial_context(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    go_mod = tmp_path / "go.mod"
    go_mod.write_text(
        """
module example.com/a
require (
    example.com/b v1.0.0
    example.com/c v1.0.0
)
""".lstrip(),
        encoding="utf-8",
    )
    monkeypatch.setattr(go_modules, "MAX_GO_DIRECTIVES_PER_FILE", 2)

    loaded = load_go_module_context(tmp_path, [go_mod])

    assert loaded.context.modules == ()
    assert loaded.problems[0].code == "GRAPH_GO_INDEX_LIMIT_EXCEEDED"
    assert loaded.problems[0].details["reason"] == "directive_limit_exceeded"
    assert loaded.problems[0].details["limit"] == 2


def test_loader_treats_explicit_outside_roots_as_non_local(tmp_path: Path):
    go_mod = tmp_path / "go.mod"
    go_mod.write_text(
        """
module example.com/a
replace example.com/b => ../outside
""".lstrip(),
        encoding="utf-8",
    )
    go_work = tmp_path / "go.work"
    go_work.write_text(
        """
go 1.23
use ../outside
""".lstrip(),
        encoding="utf-8",
    )

    loaded = load_go_module_context(tmp_path, [go_work, go_mod])

    assert loaded.problems == ()
    assert loaded.context.modules[0].replacements == (
        GoReplacement("example.com/b", None, None, None, None),
    )
    assert loaded.context.workspaces[0].use_roots == ()


def test_loader_rejects_lexically_contained_symlink_escape(tmp_path: Path):
    outside = tmp_path.parent / f"{tmp_path.name}-replacement"
    outside.mkdir()
    (tmp_path / "linked").symlink_to(outside, target_is_directory=True)
    go_mod = tmp_path / "go.mod"
    go_mod.write_text(
        """
module example.com/a
replace example.com/b => ./linked
""".lstrip(),
        encoding="utf-8",
    )

    loaded = load_go_module_context(tmp_path, [go_mod])

    assert loaded.context.modules == ()
    assert loaded.problems[0].details["reason"] == "local_path_symlink_escape"
    assert str(outside) not in str(loaded.problems[0].details)


def test_loader_orders_nested_controls_and_hashes_deterministically(tmp_path: Path):
    a_dir = tmp_path / "a"
    b_dir = tmp_path / "b"
    a_dir.mkdir()
    b_dir.mkdir()
    a_mod = a_dir / "go.mod"
    b_mod = b_dir / "go.mod"
    a_mod.write_text("module example.com/a\n", encoding="utf-8")
    b_mod.write_text("module example.com/b\n", encoding="utf-8")

    loaded = load_go_module_context(tmp_path, [b_mod, a_mod])

    assert [module.source for module in loaded.context.modules] == [
        "a/go.mod",
        "b/go.mod",
    ]
    assert [module.root for module in loaded.context.modules] == ["a", "b"]
    assert list(loaded.input_hashes) == ["a/go.mod", "b/go.mod"]


def test_loader_rejects_quoted_directive_keyword(tmp_path: Path):
    go_mod = tmp_path / "go.mod"
    go_mod.write_text('"module" example.com/a\n', encoding="utf-8")

    loaded = load_go_module_context(tmp_path, [go_mod])

    assert loaded.context.modules == ()
    assert loaded.problems[0].details["reason"] == "invalid_directive_keyword"


def test_loader_rejects_block_form_go_directive(tmp_path: Path):
    go_work = tmp_path / "go.work"
    go_work.write_text(
        """
go (
    1.23
)
use ./app
""".lstrip(),
        encoding="utf-8",
    )

    loaded = load_go_module_context(tmp_path, [go_work])

    assert loaded.context.workspaces == ()
    assert loaded.problems[0].details["reason"] == "invalid_go_version"


def test_loader_classifies_growth_past_size_limit_as_limit_problem(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    go_mod = tmp_path / "go.mod"
    go_mod.write_text("module example.com/a\n", encoding="utf-8")

    def report_growth(*args: object, **kwargs: object) -> tuple[bytes, str]:
        raise GraphContractError(
            "INVALID_GRAPH_PROFILE",
            "Graph Go control file exceeds the size limit",
            {"source": "go.mod", "limit": go_modules.MAX_GO_CONTROL_BYTES},
        )

    monkeypatch.setattr(go_modules, "read_contained_file", report_growth)

    loaded = load_go_module_context(tmp_path, [go_mod])

    assert loaded.context.modules == ()
    assert loaded.problems[0].code == "GRAPH_GO_INDEX_LIMIT_EXCEEDED"
    assert loaded.problems[0].details == {
        "reason": "control_file_too_large",
        "limit": go_modules.MAX_GO_CONTROL_BYTES,
    }


def test_outside_candidate_cannot_shadow_contained_control(tmp_path: Path):
    inside_go_mod = tmp_path / "go.mod"
    inside_go_mod.write_text("module example.com/inside\n", encoding="utf-8")
    outside = tmp_path.parent / f"{tmp_path.name}-shadow"
    outside.mkdir()
    outside_go_mod = outside / "go.mod"
    outside_go_mod.write_text("module example.com/outside\n", encoding="utf-8")

    loaded = load_go_module_context(tmp_path, [inside_go_mod, outside_go_mod])

    assert [module.module_path for module in loaded.context.modules] == [
        "example.com/inside",
    ]
    assert [(problem.source, problem.details["reason"]) for problem in loaded.problems] == [
        ("@outside/go.mod", "outside_repository"),
    ]
    assert list(loaded.input_hashes) == ["@outside/go.mod", "go.mod"]


def test_builder_creates_stable_same_module_root_and_subpackage_nodes():
    module = _module()
    root_file = _go_file("root.go", "project", content_hash="1" * 64)
    store_z = _go_file("internal/store/z.go", "store", content_hash="2" * 64)
    store_a = _go_file(
        "internal/store/a.go",
        "store",
        content_hash="3" * 64,
        line=4,
    )
    file_nodes = {
        node.file_path: node
        for node in (root_file, store_z, store_a)
    }

    built = build_go_package_index(
        GoModuleContext(modules=(module,), workspaces=()),
        file_nodes=file_nodes,
    )

    assert built.problems == ()
    assert built.index.modules == (module,)
    assert built.index.bindings_by_source_module == {
        ".": (
            GoPackageBinding(
                import_prefix="example.com/project",
                module_root=".",
                declared_module_path="example.com/project",
                source="go.mod",
            ),
        ),
    }
    assert [node.id for node in built.index.package_nodes] == [
        ".::example.com/project#package",
        "internal/store::example.com/project/internal/store#package",
    ]
    store = built.index.packages_by_binding[
        (".", "example.com/project/internal/store")
    ]
    assert store.id == "internal/store::example.com/project/internal/store#package"
    assert store.name == "store"
    assert store.qualified_name == "example.com/project/internal/store"
    assert store.kind == "package"
    assert store.language == "go"
    assert store.file_path == "internal/store/a.go"
    assert store.byte_offset == 0
    assert store.byte_length == 0
    assert store.signature == "example.com/project/internal/store"
    assert store.content_hash == "3" * 64
    assert store.keywords == ["example", "com", "project", "internal", "store"]
    assert store.metadata == {
        "loci": {
            "go_package_node": True,
            "directory": "internal/store",
            "import_path": "example.com/project/internal/store",
            "package_name": "store",
            "module_root": ".",
            "declared_module_path": "example.com/project",
        }
    }
    assert (store.line, store.end_line) == (1, 1)

    rebuilt = build_go_package_index(
        GoModuleContext(modules=(module,), workspaces=()),
        file_nodes={
            root_file.file_path: root_file,
            store_z.file_path: store_z,
        },
    )
    moved = rebuilt.index.packages_by_binding[
        (".", "example.com/project/internal/store")
    ]
    assert moved.id == store.id
    assert moved.file_path == "internal/store/z.go"
    assert moved.content_hash == "2" * 64


def test_builder_uses_nearest_workspace_and_keeps_nested_module_ownership():
    app = _module(root="work/app", module_path="example.com/app")
    lib = _module(root="work/lib", module_path="example.com/lib")
    other = _module(root="other", module_path="example.com/other")
    context = GoModuleContext(
        modules=(other, lib, app),
        workspaces=(
            GoWorkspace(
                source="go.work",
                root=".",
                go_version="1.23",
                use_roots=("other", "work/app"),
                replacements=(),
            ),
            GoWorkspace(
                source="work/go.work",
                root="work",
                go_version="1.23",
                use_roots=("work/app", "work/lib"),
                replacements=(),
            ),
        ),
    )
    file_nodes = {
        node.file_path: node
        for node in (
            _go_file("work/app/app.go", "app"),
            _go_file("work/app/nested/parent.go", "nested"),
            _go_file("work/lib/lib.go", "lib"),
            _go_file("other/other.go", "other"),
        )
    }

    built = build_go_package_index(context, file_nodes=file_nodes)

    assert [
        (binding.import_prefix, binding.module_root, binding.source)
        for binding in built.index.bindings_by_source_module["work/app"]
    ] == [
        ("example.com/app", "work/app", "work/app/go.mod"),
        ("example.com/lib", "work/lib", "work/go.work"),
    ]
    assert [
        binding.import_prefix
        for binding in built.index.bindings_by_source_module["other"]
    ] == ["example.com/app", "example.com/other"]
    assert "work/lib::example.com/lib#package" in {
        node.id for node in built.index.package_nodes
    }
    assert "work/lib::example.com/app/lib#package" not in {
        node.id for node in built.index.package_nodes
    }


def test_builder_does_not_fall_back_past_nearest_workspace_that_omits_module():
    extra = _module(root="work/extra", module_path="example.com/extra")
    app = _module(root="work/app", module_path="example.com/app")
    context = GoModuleContext(
        modules=(extra, app),
        workspaces=(
            GoWorkspace(
                source="go.work",
                root=".",
                go_version="1.23",
                use_roots=("work/extra", "work/app"),
                replacements=(),
            ),
            GoWorkspace(
                source="work/go.work",
                root="work",
                go_version="1.23",
                use_roots=("work/app",),
                replacements=(),
            ),
        ),
    )

    built = build_go_package_index(
        context,
        file_nodes={"work/extra/extra.go": _go_file("work/extra/extra.go", "extra")},
    )

    assert built.index.bindings_by_source_module["work/extra"] == (
        GoPackageBinding(
            import_prefix="example.com/extra",
            module_root="work/extra",
            declared_module_path="example.com/extra",
            source="work/extra/go.mod",
        ),
    )


def test_builder_adds_required_local_replacement_as_distinct_package_identity():
    app = _module(
        root="app",
        module_path="example.com/app",
        requirements=(GoRequirement("example.com/dep", "v1.0.0"),),
        replacements=(
            GoReplacement("example.com/dep", None, "local/dep", None, None),
            GoReplacement("example.com/unused", None, "local/dep", None, None),
            GoReplacement("example.com/remote", None, None, "example.com/fork", "v1.0.0"),
        ),
    )
    dependency = _module(
        root="local/dep",
        module_path="example.com/local-dep",
    )
    package = _go_file("local/dep/pkg/dep.go", "dep")

    built = build_go_package_index(
        GoModuleContext(modules=(app, dependency), workspaces=()),
        file_nodes={package.file_path: package},
    )

    assert built.problems == ()
    assert built.index.bindings_by_source_module["app"] == (
        GoPackageBinding(
            import_prefix="example.com/app",
            module_root="app",
            declared_module_path="example.com/app",
            source="app/go.mod",
        ),
        GoPackageBinding(
            import_prefix="example.com/dep",
            module_root="local/dep",
            declared_module_path="example.com/local-dep",
            source="app/go.mod",
        ),
    )
    assert {
        node.id for node in built.index.package_nodes
    } == {
        "local/dep/pkg::example.com/dep/pkg#package",
        "local/dep/pkg::example.com/local-dep/pkg#package",
    }


def test_workspace_replacement_overrides_module_replacement():
    app = _module(
        root="app",
        module_path="example.com/app",
        requirements=(GoRequirement("example.com/dep", "v1.0.0"),),
        replacements=(
            GoReplacement("example.com/dep", None, "local/module-dep", None, None),
        ),
    )
    module_dep = _module(
        root="local/module-dep",
        module_path="example.com/module-dep",
    )
    workspace_dep = _module(
        root="local/workspace-dep",
        module_path="example.com/workspace-dep",
    )
    workspace = GoWorkspace(
        source="go.work",
        root=".",
        go_version="1.23",
        use_roots=("app",),
        replacements=(
            GoReplacement(
                "example.com/dep",
                None,
                "local/workspace-dep",
                None,
                None,
            ),
        ),
    )

    built = build_go_package_index(
        GoModuleContext(
            modules=(app, module_dep, workspace_dep),
            workspaces=(workspace,),
        ),
        file_nodes={},
    )

    dep_bindings = [
        binding
        for binding in built.index.bindings_by_source_module["app"]
        if binding.import_prefix == "example.com/dep"
    ]
    assert dep_bindings == [
        GoPackageBinding(
            import_prefix="example.com/dep",
            module_root="local/workspace-dep",
            declared_module_path="example.com/workspace-dep",
            source="go.work",
        )
    ]


def test_builder_records_commands_and_rejects_invalid_package_directories():
    module = _module()
    file_nodes = {
        node.file_path: node
        for node in (
            _go_file("cmd/tool/main.go", "main"),
            _go_file("conflict/a.go", "alpha"),
            _go_file("conflict/b.go", "beta"),
            _go_file("missing/missing.go", None),
            _go_file("vendor/hidden/hidden.go", "hidden"),
            _go_file("testonly/only_test.go", "testonly"),
        )
    }

    built = build_go_package_index(
        GoModuleContext(modules=(module,), workspaces=()),
        file_nodes=file_nodes,
    )

    assert built.index.package_nodes == ()
    assert built.index.command_packages == frozenset({
        (".", "example.com/project/cmd/tool"),
    })
    assert [(problem.source, problem.details["reason"]) for problem in built.problems] == [
        ("conflict", "conflicting_package_declarations"),
        ("missing", "missing_package_declaration"),
    ]


@pytest.mark.parametrize(
    ("limit_name", "expected_reason"),
    [
        ("MAX_GO_PACKAGE_BINDINGS", "binding_limit_exceeded"),
        ("MAX_GO_PACKAGE_NODES", "package_node_limit_exceeded"),
    ],
)
def test_builder_rejects_limits_without_partial_index(
    monkeypatch: pytest.MonkeyPatch,
    limit_name: str,
    expected_reason: str,
):
    monkeypatch.setattr(go_modules, limit_name, 0)
    module = _module()
    node = _go_file("store/store.go", "store")

    built = build_go_package_index(
        GoModuleContext(modules=(module,), workspaces=()),
        file_nodes={node.file_path: node},
    )

    assert built.index.modules == ()
    assert built.index.package_nodes == ()
    assert built.index.bindings_by_source_module == {}
    assert built.index.packages_by_binding == {}
    assert built.index.command_packages == frozenset()
    assert len(built.problems) == 1
    assert built.problems[0].code == "GRAPH_GO_INDEX_LIMIT_EXCEEDED"
    assert built.problems[0].details == {
        "reason": expected_reason,
        "limit": 0,
    }


def test_builder_never_lets_parent_binding_claim_nested_module_packages():
    root = _module(module_path="example.com/root")
    nested = _module(root="nested", module_path="example.com/nested")
    package = _go_file("nested/pkg/pkg.go", "pkg")

    built = build_go_package_index(
        GoModuleContext(modules=(root, nested), workspaces=()),
        file_nodes={package.file_path: package},
    )

    assert {node.id for node in built.index.package_nodes} == {
        "nested/pkg::example.com/nested/pkg#package",
    }
    assert (
        ".",
        "example.com/root/nested/pkg",
    ) not in built.index.packages_by_binding


def test_builder_only_admits_required_non_excluded_local_replacements():
    app = _module(
        root="app",
        module_path="example.com/app",
        requirements=(
            GoRequirement("example.com/excluded", "v1.0.0"),
            GoRequirement("example.com/outside", "v1.0.0"),
            GoRequirement("example.com/remote", "v1.0.0"),
        ),
        exclusions=(GoExclusion("example.com/excluded", "v1.0.0"),),
        replacements=(
            GoReplacement("example.com/excluded", None, "local/dep", None, None),
            GoReplacement("example.com/outside", None, None, None, None),
            GoReplacement(
                "example.com/remote",
                None,
                None,
                "example.com/fork",
                "v1.0.1",
            ),
        ),
    )
    dependency = _module(root="local/dep", module_path="example.com/local")

    built = build_go_package_index(
        GoModuleContext(modules=(app, dependency), workspaces=()),
        file_nodes={},
    )

    assert [
        binding.import_prefix
        for binding in built.index.bindings_by_source_module["app"]
    ] == ["example.com/app"]
    assert built.problems == ()


def test_builder_reports_missing_and_conflicting_local_replacement_modules():
    app = _module(
        root="app",
        module_path="example.com/app",
        requirements=(
            GoRequirement("example.com/conflict", "v1.0.0"),
            GoRequirement("example.com/missing", "v1.0.0"),
        ),
        replacements=(
            GoReplacement("example.com/conflict", None, "local/a", None, None),
            GoReplacement("example.com/conflict", None, "local/b", None, None),
            GoReplacement("example.com/missing", None, "local/missing", None, None),
        ),
    )
    local_a = _module(root="local/a", module_path="example.com/a")
    local_b = _module(root="local/b", module_path="example.com/b")

    built = build_go_package_index(
        GoModuleContext(modules=(app, local_a, local_b), workspaces=()),
        file_nodes={},
    )

    assert [
        binding.import_prefix
        for binding in built.index.bindings_by_source_module["app"]
    ] == ["example.com/app"]
    assert [problem.details["reason"] for problem in built.problems] == [
        "conflicting_local_replacements",
        "replacement_module_missing",
    ]
    assert all("/Users/" not in str(problem.details) for problem in built.problems)


def test_builder_rejects_disagreeing_workspace_replacement_versions():
    app = _module(
        root="app",
        module_path="example.com/app",
        requirements=(GoRequirement("example.com/dep", "v1.0.0"),),
    )
    worker = _module(
        root="worker",
        module_path="example.com/worker",
        requirements=(GoRequirement("example.com/dep", "v2.0.0"),),
    )
    dependency = _module(root="local/dep", module_path="example.com/local-dep")
    workspace = GoWorkspace(
        source="go.work",
        root=".",
        go_version="1.23",
        use_roots=("app", "worker"),
        replacements=(
            GoReplacement(
                "example.com/dep",
                "v1.0.0",
                "local/dep",
                None,
                None,
            ),
        ),
    )

    built = build_go_package_index(
        GoModuleContext(
            modules=(app, worker, dependency),
            workspaces=(workspace,),
        ),
        file_nodes={},
    )

    assert not any(
        binding.import_prefix == "example.com/dep"
        for binding in built.index.bindings_by_source_module["app"]
    )
    assert any(
        problem.details["reason"] == "workspace_requirement_version_conflict"
        for problem in built.problems
    )


@pytest.mark.parametrize(
    "invalid_path",
    [
        "/private/outside.go",
        "nested\\outside.go",
        "nested//outside.go",
        "nested/\x01.go",
    ],
)
def test_builder_reports_invalid_go_file_nodes_without_exposing_paths(
    invalid_path: str,
):
    node = _go_file(invalid_path, "safe")

    built = build_go_package_index(
        GoModuleContext(modules=(_module(),), workspaces=()),
        file_nodes={invalid_path: node},
    )

    assert built.index.package_nodes == ()
    assert len(built.problems) == 1
    assert built.problems[0].code == "GRAPH_GO_PACKAGE_INVALID"
    assert built.problems[0].source == "@invalid/go-file"
    assert built.problems[0].details == {"reason": "invalid_go_file_node"}
    assert invalid_path not in str(built.problems[0])


def test_builder_classifies_directories_once_and_materializes_unique_bindings_once(
    monkeypatch: pytest.MonkeyPatch,
):
    app = _module(root="app", module_path="example.com/app")
    lib = _module(root="lib", module_path="example.com/lib")
    workspace = GoWorkspace(
        source="go.work",
        root=".",
        go_version="1.23",
        use_roots=("app", "lib"),
        replacements=(),
    )
    file_nodes = {
        "app/app.go": _go_file("app/app.go", "app"),
        "lib/lib.go": _go_file("lib/lib.go", "lib"),
    }
    owner_calls = 0
    materialize_calls = 0
    original_owner = go_modules._owning_module_root
    original_materialize = go_modules._make_go_package_symbol

    def count_owner(*args: object, **kwargs: object) -> str | None:
        nonlocal owner_calls
        owner_calls += 1
        return original_owner(*args, **kwargs)

    def count_materialize(*args: object, **kwargs: object) -> Symbol:
        nonlocal materialize_calls
        materialize_calls += 1
        return original_materialize(*args, **kwargs)

    monkeypatch.setattr(go_modules, "_owning_module_root", count_owner)
    monkeypatch.setattr(go_modules, "_make_go_package_symbol", count_materialize)

    built = build_go_package_index(
        GoModuleContext(modules=(app, lib), workspaces=(workspace,)),
        file_nodes=file_nodes,
    )

    assert owner_calls == len(file_nodes)
    assert materialize_calls == len(built.index.package_nodes)
