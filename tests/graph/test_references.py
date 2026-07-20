from __future__ import annotations

import hashlib
from dataclasses import replace
from pathlib import Path

import pytest

from loci.graph import _javascript_references
from loci.graph import _python_references
from loci.graph import _rust_references
from loci.graph.contracts import GraphContractError
from loci.graph.go_modules import (
    GoModule,
    GoModuleContext,
    GoReplacement,
    GoRequirement,
    GoWorkspace,
    build_go_package_index,
)
from loci.graph.imports import resolve_imports
from loci.graph.javascript_modules import (
    build_javascript_resolution_index,
    load_javascript_module_context,
)
from loci.graph.references import (
    build_reference_resolver_index,
    resolve_symbol_references,
)
from loci.graph.rust_crates import (
    CargoContext,
    CargoPackage,
    CargoWorkspace,
    RustDependency,
    RustTarget,
    build_rust_crate_index,
)
from loci.parser.extractor import parse_file
from loci.parser.imports import ImportExtractionBatch, extract_import_batch
from loci.parser.symbols import Symbol, make_file_symbol, make_symbol_id


def _resolve_python_tree(
    tmp_path: Path,
    files: dict[str, str],
) -> tuple[list, list[Symbol], list[ImportExtractionBatch]]:
    symbols: list[Symbol] = []
    batches: list[ImportExtractionBatch] = []
    file_nodes: dict[str, Symbol] = {}
    for relative_path, source in files.items():
        path = tmp_path / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(source, encoding="utf-8")
        source_hash = hashlib.sha256(source.encode()).hexdigest()
        file_node = make_file_symbol(
            relative_path,
            language="python",
            content_hash=source_hash,
        )
        file_nodes[relative_path] = file_node
        symbols.append(file_node)
        symbols.extend(
            replace(
                symbol,
                id=make_symbol_id(relative_path, symbol.qualified_name, symbol.kind),
                file_path=relative_path,
            )
            for symbol in parse_file(path)
        )
        batches.append(
            extract_import_batch(
                path,
                source_file=relative_path,
                language="python",
                source_hash=source_hash,
            )
        )

    imports = resolve_imports(
        [raw for batch in batches for raw in batch.imports],
        file_nodes=file_nodes,
    )
    exports = [export for batch in batches for export in batch.exports]
    observations = [reference for batch in batches for reference in batch.references]
    index = build_reference_resolver_index(symbols, imports, exports)
    return (
        resolve_symbol_references(observations, imports=imports, index=index),
        symbols,
        batches,
    )


def _javascript_language(relative_path: str) -> str:
    return (
        "typescript"
        if Path(relative_path).suffix in {".ts", ".tsx", ".mts", ".cts"}
        else "javascript"
    )


def _resolve_javascript_tree(
    tmp_path: Path,
    files: dict[str, str],
    *,
    controls: dict[str, str] | None = None,
) -> tuple[list, list[Symbol], list[ImportExtractionBatch]]:
    symbols: list[Symbol] = []
    batches: list[ImportExtractionBatch] = []
    file_nodes: dict[str, Symbol] = {}
    for relative_path, source in files.items():
        path = tmp_path / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(source, encoding="utf-8")
        source_hash = hashlib.sha256(source.encode()).hexdigest()
        language = _javascript_language(relative_path)
        file_node = make_file_symbol(
            relative_path,
            language=language,
            content_hash=source_hash,
        )
        file_nodes[relative_path] = file_node
        symbols.append(file_node)
        symbols.extend(
            replace(
                symbol,
                id=make_symbol_id(relative_path, symbol.qualified_name, symbol.kind),
                file_path=relative_path,
            )
            for symbol in parse_file(path)
        )
        batches.append(
            extract_import_batch(
                path,
                source_file=relative_path,
                language=language,
                source_hash=source_hash,
            )
        )

    control_paths: list[Path] = []
    for relative_path, source in (controls or {}).items():
        path = tmp_path / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(source, encoding="utf-8")
        control_paths.append(path)
    loaded = load_javascript_module_context(tmp_path, control_paths)
    assert loaded.problems == ()
    javascript_index = build_javascript_resolution_index(
        loaded.context,
        file_nodes=file_nodes,
    )
    assert javascript_index.problems == ()
    imports = resolve_imports(
        [raw for batch in batches for raw in batch.imports],
        file_nodes=file_nodes,
        javascript_modules=javascript_index.index,
    )
    exports = [export for batch in batches for export in batch.exports]
    observations = [reference for batch in batches for reference in batch.references]
    index = build_reference_resolver_index(symbols, imports, exports)
    return (
        resolve_symbol_references(observations, imports=imports, index=index),
        symbols,
        batches,
    )


def _resolve_go_tree(
    tmp_path: Path,
    files: dict[str, str],
    *,
    modules: tuple[GoModule, ...],
    workspaces: tuple[GoWorkspace, ...] = (),
) -> tuple[list, list[Symbol], list[ImportExtractionBatch]]:
    symbols: list[Symbol] = []
    batches: list[ImportExtractionBatch] = []
    file_nodes: dict[str, Symbol] = {}
    for relative_path, source in files.items():
        path = tmp_path / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(source, encoding="utf-8")
        source_hash = hashlib.sha256(source.encode()).hexdigest()
        file_node = make_file_symbol(
            relative_path,
            language="go",
            content_hash=source_hash,
        )
        batch = extract_import_batch(
            path,
            source_file=relative_path,
            language="go",
            source_hash=source_hash,
        )
        if batch.go_package is not None:
            file_node.metadata["loci"]["go_package"] = {
                "name": batch.go_package.name,
                "line": batch.go_package.line,
            }
        file_nodes[relative_path] = file_node
        symbols.append(file_node)
        symbols.extend(
            replace(
                symbol,
                id=make_symbol_id(relative_path, symbol.qualified_name, symbol.kind),
                file_path=relative_path,
            )
            for symbol in parse_file(path)
        )
        batches.append(batch)

    package_build = build_go_package_index(
        GoModuleContext(modules=modules, workspaces=workspaces),
        file_nodes=file_nodes,
    )
    assert package_build.problems == ()
    symbols.extend(package_build.index.package_nodes)
    imports = resolve_imports(
        [raw for batch in batches for raw in batch.imports],
        file_nodes=file_nodes,
        go_packages=package_build.index,
    )
    exports = [export for batch in batches for export in batch.exports]
    observations = [reference for batch in batches for reference in batch.references]
    index = build_reference_resolver_index(
        symbols,
        imports,
        exports,
        go_packages=package_build.index,
    )
    return (
        resolve_symbol_references(observations, imports=imports, index=index),
        symbols,
        batches,
    )


def _rust_package(
    *,
    source: str,
    root: str,
    name: str,
    root_file: str,
    dependencies: tuple[RustDependency, ...] = (),
) -> CargoPackage:
    return CargoPackage(
        source=source,
        root=root,
        name=name,
        workspace_source=None,
        edition="2021",
        features={},
        dependencies=dependencies,
        targets=(
            RustTarget(
                "lib",
                name,
                name.replace("-", "_"),
                root_file,
                "2021",
                (),
            ),
        ),
    )


def _resolve_rust_tree(
    tmp_path: Path,
    files: dict[str, str],
    *,
    packages: tuple[CargoPackage, ...],
    workspaces: tuple[CargoWorkspace, ...] = (),
) -> tuple[list, list[Symbol], list[ImportExtractionBatch]]:
    symbols: list[Symbol] = []
    batches: list[ImportExtractionBatch] = []
    file_nodes: dict[str, Symbol] = {}
    for relative_path, source in files.items():
        path = tmp_path / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(source, encoding="utf-8")
        source_hash = hashlib.sha256(source.encode()).hexdigest()
        file_node = make_file_symbol(
            relative_path,
            language="rust",
            content_hash=source_hash,
        )
        file_nodes[relative_path] = file_node
        symbols.append(file_node)
        symbols.extend(
            replace(
                symbol,
                id=make_symbol_id(relative_path, symbol.qualified_name, symbol.kind),
                file_path=relative_path,
            )
            for symbol in parse_file(path)
        )
        batches.append(
            extract_import_batch(
                path,
                source_file=relative_path,
                language="rust",
                source_hash=source_hash,
            )
        )

    rust_build = build_rust_crate_index(
        CargoContext(packages=packages, workspaces=workspaces),
        file_nodes=file_nodes,
        observations=tuple(
            raw for batch in batches for raw in batch.imports
        ),
    )
    assert rust_build.problems == ()
    symbols.extend(rust_build.index.crate_nodes)
    imports = resolve_imports(
        [raw for batch in batches for raw in batch.imports],
        file_nodes=file_nodes,
        rust_crates=rust_build.index,
    )
    exports = [export for batch in batches for export in batch.exports]
    observations = [reference for batch in batches for reference in batch.references]
    index = build_reference_resolver_index(
        symbols,
        imports,
        exports,
        rust_crates=rust_build.index,
    )
    return (
        resolve_symbol_references(observations, imports=imports, index=index),
        symbols,
        batches,
    )


def test_resolves_rust_named_alias_and_module_qualified_items_with_provenance(
    tmp_path: Path,
):
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
    records, _, _ = _resolve_rust_tree(
        tmp_path,
        {
            "app/src/lib.rs": """
mod local;
use crate::local::inside;
use core_alias::api::run as execute;
use core_alias::api;

pub fn call() {
    inside();
    execute();
    let _: api::Thing;
}
""".lstrip(),
            "app/src/local.rs": "pub(crate) fn inside() {}\n",
            "core/src/lib.rs": "pub mod api;\n",
            "core/src/api.rs": """
pub fn run() {}
pub struct Thing;
""".lstrip(),
            "unrelated/api.rs": "pub fn run() {}\npub struct Thing;\n",
        },
        packages=(app, core),
    )

    by_path = {record.raw.path: record for record in records}
    assert by_path[("inside",)].status == "resolved", (
        by_path[("inside",)].unresolved_reason,
        by_path[("inside",)].import_unresolved_reason,
    )
    assert by_path[("inside",)].target_file == "app/src/local.rs"
    assert by_path[("execute",)].status == "resolved", (
        by_path[("execute",)].unresolved_reason,
        by_path[("execute",)].import_unresolved_reason,
    )
    assert by_path[("execute",)].target_file == "core/src/api.rs"
    assert by_path[("execute",)].resolution_configuration == "declared_possible"
    assert by_path[("execute",)].resolution_control_files == (
        "app/Cargo.toml",
        "core/Cargo.toml",
    )
    assert by_path[("api", "Thing")].status == "resolved"
    assert by_path[("api", "Thing")].target_kind == "struct"


def test_resolves_rust_2015_extern_crate_to_same_package_library(tmp_path: Path):
    package = CargoPackage(
        source="Cargo.toml",
        root=".",
        name="demo",
        workspace_source=None,
        edition="2015",
        features={},
        dependencies=(),
        targets=(
            RustTarget("lib", "demo", "demo", "src/lib.rs", "2015", ()),
            RustTarget("bin", "runner", "runner", "src/main.rs", "2015", ()),
        ),
    )
    records, _, _ = _resolve_rust_tree(
        tmp_path,
        {
            "src/lib.rs": "pub struct Thing;\n",
            "src/main.rs": """
extern crate demo as library;
fn main() { let _: library::Thing; }
""".lstrip(),
        },
        packages=(package,),
    )

    assert len(records) == 1
    assert records[0].status == "resolved"
    assert records[0].target_file == "src/lib.rs"
    assert records[0].target_kind == "struct"
    assert records[0].resolution_basis == "qualified_member"
    assert records[0].resolution_control_files == ("Cargo.toml",)


def test_resolves_rust_inherited_workspace_dependency_item(tmp_path: Path):
    dependency = RustDependency(
        alias="core_alias",
        package_name="core",
        kind="normal",
        path="crates/core",
        optional=False,
        default_features=True,
        features=(),
        target_condition=None,
        inherited=True,
        source="Cargo.toml",
    )
    app = CargoPackage(
        source="crates/app/Cargo.toml",
        root="crates/app",
        name="app",
        workspace_source="Cargo.toml",
        edition="2021",
        features={},
        dependencies=(dependency,),
        targets=(RustTarget(
            "lib",
            "app",
            "app",
            "crates/app/src/lib.rs",
            "2021",
            (),
        ),),
    )
    core = CargoPackage(
        source="crates/core/Cargo.toml",
        root="crates/core",
        name="core",
        workspace_source="Cargo.toml",
        edition="2021",
        features={},
        dependencies=(),
        targets=(RustTarget(
            "lib",
            "core",
            "core",
            "crates/core/src/lib.rs",
            "2021",
            (),
        ),),
    )
    workspace = CargoWorkspace(
        source="Cargo.toml",
        root=".",
        member_sources=("crates/app/Cargo.toml", "crates/core/Cargo.toml"),
    )
    records, _, _ = _resolve_rust_tree(
        tmp_path,
        {
            "crates/app/src/lib.rs": (
                "use core_alias::Thing;\npub fn call() { let _: Thing; }\n"
            ),
            "crates/core/src/lib.rs": "pub struct Thing;\n",
        },
        packages=(app, core),
        workspaces=(workspace,),
    )

    assert len(records) == 1
    assert records[0].status == "resolved"
    assert records[0].target_file == "crates/core/src/lib.rs"
    assert records[0].resolution_control_files == (
        "Cargo.toml",
        "crates/app/Cargo.toml",
        "crates/core/Cargo.toml",
    )


def test_resolves_rust_named_public_reexport_but_not_private_canonical_route(
    tmp_path: Path,
):
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
    records, _, _ = _resolve_rust_tree(
        tmp_path,
        {
            "app/src/lib.rs": """
use core_alias::exposed;
use core_alias::hidden::run as forbidden;

pub fn call() {
    exposed();
    forbidden();
}
""".lstrip(),
            "core/src/lib.rs": """
mod hidden;
mod facade;
pub use facade::exposed;
""".lstrip(),
            "core/src/hidden.rs": "pub fn run() {}\n",
            "core/src/facade.rs": "pub use crate::hidden::run as exposed;\n",
        },
        packages=(app, core),
    )

    by_path = {record.raw.path: record for record in records}
    assert by_path[("exposed",)].status == "resolved"
    assert by_path[("exposed",)].target_file == "core/src/hidden.rs"
    assert by_path[("exposed",)].resolution_basis == "reexport_chain"
    assert [support.kind for support in by_path[("exposed",)].support] == [
        "import_binding",
        "reexport",
        "reexport",
        "definition",
    ]
    assert by_path[("forbidden",)].status == "unresolved"
    assert by_path[("forbidden",)].import_unresolved_reason == "inaccessible"


def test_rust_reexport_pass_limit_fails_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(_rust_references, "MAX_REFERENCE_REEXPORT_PASSES", 1)
    package = _rust_package(
        source="Cargo.toml",
        root=".",
        name="demo",
        root_file="src/lib.rs",
    )
    records, _, _ = _resolve_rust_tree(
        tmp_path,
        {
            "src/lib.rs": """
mod hidden;
mod facade;
mod consumer;
pub use facade::exposed;
""".lstrip(),
            "src/hidden.rs": "pub fn run() {}\n",
            "src/facade.rs": "pub use crate::hidden::run as exposed;\n",
            "src/consumer.rs": (
                "use crate::exposed;\npub fn call() { exposed(); }\n"
            ),
        },
        packages=(package,),
    )

    assert len(records) == 1
    assert records[0].status == "unresolved"
    assert records[0].unresolved_reason == "ambiguous_target"


def test_enforces_rust_terminal_item_visibility_scopes(tmp_path: Path):
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
    records, _, _ = _resolve_rust_tree(
        tmp_path,
        {
            "app/src/lib.rs": """
use core_alias::crate_only as crate_bad;
use core_alias::public as public_external;

pub fn call() {
    crate_bad();
    public_external();
}
""".lstrip(),
            "core/src/lib.rs": """
pub mod outer;
pub(crate) fn crate_only() {}
pub fn public() {}
fn private() {}

use crate::crate_only as crate_ok;
use crate::private as private_ok;
use crate::outer::child::parent_visible as parent_bad;
use crate::outer::child::outer_visible as outer_bad;
pub fn root_call() { crate_ok(); private_ok(); parent_bad(); outer_bad(); }
""".lstrip(),
            "core/src/outer.rs": """
pub mod child;
use self::child::parent_visible as parent_ok;
use self::child::outer_visible as outer_ok;
use self::child::self_only as self_bad;
use self::child::private_child as private_bad;
pub fn outer_call() { parent_ok(); outer_ok(); self_bad(); private_bad(); }
""".lstrip(),
            "core/src/outer/child.rs": """
pub(super) fn parent_visible() {}
pub(self) fn self_only() {}
pub(in crate::outer) fn outer_visible() {}
fn private_child() {}

use self::self_only as self_ok;
use self::private_child as private_ok;
pub fn child_call() { self_ok(); private_ok(); }
""".lstrip(),
        },
        packages=(app, core),
    )

    by_path = {record.raw.path: record for record in records}
    for path in (
        ("public_external",),
        ("crate_ok",),
        ("private_ok",),
        ("parent_ok",),
        ("outer_ok",),
        ("self_ok",),
    ):
        assert by_path[path].status == "resolved", (path, by_path[path])
    assert by_path[("crate_bad",)].unresolved_reason == "target_inaccessible"
    assert by_path[("parent_bad",)].unresolved_reason == "target_inaccessible"
    assert by_path[("outer_bad",)].unresolved_reason == "target_inaccessible"
    assert by_path[("self_bad",)].unresolved_reason == "target_inaccessible"
    assert by_path[("private_bad",)].unresolved_reason == "target_inaccessible"


def test_rust_declared_configuration_converges_and_divergence_fails_closed(
    tmp_path: Path,
):
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
    records, _, _ = _resolve_rust_tree(
        tmp_path,
        {
            "app/src/lib.rs": """
use core_alias::convergent;
use core_alias::divergent;
pub fn call() { convergent(); divergent(); }
""".lstrip(),
            "core/src/lib.rs": """
mod a;
mod b;
#[cfg(feature = "one")]
pub use a::value as convergent;
#[cfg(feature = "two")]
pub use a::value as convergent;
#[cfg(feature = "one")]
pub use a::value as divergent;
#[cfg(feature = "two")]
pub use b::value as divergent;
""".lstrip(),
            "core/src/a.rs": "pub fn value() {}\n",
            "core/src/b.rs": "pub fn value() {}\n",
        },
        packages=(app, core),
    )

    by_path = {record.raw.path: record for record in records}
    assert by_path[("convergent",)].status == "resolved"
    assert by_path[("convergent",)].resolution_configuration == "declared_possible"
    assert by_path[("divergent",)].status == "unresolved"
    assert by_path[("divergent",)].unresolved_reason == "configuration_divergent"


def test_rust_unsupported_namespaces_macros_and_associated_items_fail_closed(
    tmp_path: Path,
):
    package = _rust_package(
        source="Cargo.toml",
        root=".",
        name="demo",
        root_file="src/lib.rs",
    )
    records, _, batches = _resolve_rust_tree(
        tmp_path,
        {
            "src/lib.rs": """
pub mod model;
use crate::model::Thing;
use crate::model::Shared;
use crate::model::Generated;
use crate::model::*;
pub fn call() { Thing::method(); Shared; Generated!(); Anything; }
""".lstrip(),
            "src/model.rs": """
pub struct Thing;
impl Thing { pub fn method() {} }
pub trait Shared {}
pub const Shared: usize = 1;
""".lstrip(),
        },
        packages=(package,),
    )

    by_path = {record.raw.path: record for record in records}
    assert by_path[("Thing", "method")].status == "resolved"
    assert by_path[("Thing", "method")].target_kind == "struct"
    assert by_path[("Shared",)].unresolved_reason == "ambiguous_target"
    assert by_path[("Generated",)].unresolved_reason == "unsupported_reference"
    assert all(
        reference.path != ("Anything",)
        for batch in batches
        for reference in batch.references
    )


def test_rust_reference_index_rejects_inconsistent_item_metadata(tmp_path: Path):
    source = "pub fn visible() {}\n"
    path = tmp_path / "lib.rs"
    path.write_text(source, encoding="utf-8")
    source_hash = hashlib.sha256(source.encode()).hexdigest()
    file_node = make_file_symbol(
        "lib.rs",
        language="rust",
        content_hash=source_hash,
    )
    symbol = replace(
        parse_file(path)[0],
        id=make_symbol_id("lib.rs", "visible", "function"),
        file_path="lib.rs",
        metadata={
            "loci": {
                "rust_item": {
                    "lexical_module_path": [],
                    "visibility": "pub",
                    "visibility_scope": [],
                    "configuration": "unconditional",
                }
            }
        },
    )
    batch = extract_import_batch(
        path,
        source_file="lib.rs",
        language="rust",
        source_hash=source_hash,
    )

    with pytest.raises(GraphContractError, match="scope is inconsistent"):
        build_reference_resolver_index(
            [file_node, symbol],
            [],
            batch.exports,
        )


def test_resolves_go_declared_package_name_and_explicit_alias(tmp_path: Path):
    module = GoModule(
        source="go.mod",
        root=".",
        module_path="example.com/project",
        requirements=(),
        exclusions=(),
        replacements=(),
    )
    records, _, _ = _resolve_go_tree(
        tmp_path,
        {
            "internal/storage/store.go": (
                "package store\n"
                "const Limit = 10\n"
                "type Record struct{}\n"
                "func Open() {}\n"
            ),
            "cmd/default/main.go": (
                "package main\n"
                'import "example.com/project/internal/storage"\n'
                "func run() { store.Open(); store.Record{}; _ = store.Limit }\n"
            ),
            "cmd/alias/main.go": (
                "package main\n"
                'import depot "example.com/project/internal/storage"\n'
                "func run() { depot.Open() }\n"
            ),
        },
        modules=(module,),
    )

    selected = [
        record
        for record in records
        if record.raw.source_file in {"cmd/default/main.go", "cmd/alias/main.go"}
    ]
    assert [(record.raw.text, record.target_id) for record in selected] == [
        ("store.Open", "internal/storage/store.go::Open#function"),
        ("store.Record", "internal/storage/store.go::Record#type"),
        ("store.Limit", "internal/storage/store.go::Limit#constant"),
        ("depot.Open", "internal/storage/store.go::Open#function"),
    ]
    assert {record.status for record in selected} == {"resolved"}
    assert {record.resolution_basis for record in selected} == {"qualified_member"}
    assert [record.binding.local_name for record in selected if record.binding] == [
        None,
        None,
        None,
        "depot",
    ]
    assert {
        tuple(support.kind for support in record.support) for record in selected
    } == {("import_binding", "definition")}


def test_resolves_go_workspace_package_only_through_active_stage_7_endpoint(
    tmp_path: Path,
):
    app = GoModule(
        source="app/go.mod",
        root="app",
        module_path="example.com/app",
        requirements=(),
        exclusions=(),
        replacements=(),
    )
    library = GoModule(
        source="lib/go.mod",
        root="lib",
        module_path="example.com/lib",
        requirements=(),
        exclusions=(),
        replacements=(),
    )
    workspace = GoWorkspace(
        source="go.work",
        root=".",
        go_version="1.26",
        use_roots=("app", "lib"),
        replacements=(),
    )
    records, _, _ = _resolve_go_tree(
        tmp_path,
        {
            "app/main.go": (
                "package main\n"
                'import "example.com/lib/logging"\n'
                "func run() { logging.Write() }\n"
            ),
            "lib/logging/logging.go": "package logging\nfunc Write() {}\n",
            "unrelated/logging.go": "package logging\nfunc Write() {}\n",
        },
        modules=(app, library),
        workspaces=(workspace,),
    )

    record = next(
        item for item in records if item.raw.source_file == "app/main.go"
    )
    assert record.status == "resolved"
    assert record.import_target_id == "lib/logging::example.com/lib/logging#package"
    assert record.target_id == "lib/logging/logging.go::Write#function"


def test_resolves_go_contained_replacement_under_required_import_identity(
    tmp_path: Path,
):
    application = GoModule(
        source="app/go.mod",
        root="app",
        module_path="example.com/app",
        requirements=(GoRequirement("example.com/dep", "v1.2.0"),),
        exclusions=(),
        replacements=(
            GoReplacement(
                module_path="example.com/dep",
                version=None,
                local_root="third_party/dep",
                remote_path=None,
                remote_version=None,
            ),
        ),
    )
    dependency = GoModule(
        source="third_party/dep/go.mod",
        root="third_party/dep",
        module_path="local.invalid/dep",
        requirements=(),
        exclusions=(),
        replacements=(),
    )
    records, _, _ = _resolve_go_tree(
        tmp_path,
        {
            "app/main.go": (
                "package main\n"
                'import "example.com/dep/client"\n'
                "func run() { client.New() }\n"
            ),
            "third_party/dep/client/client.go": "package client\nfunc New() {}\n",
        },
        modules=(application, dependency),
    )

    record = next(
        item for item in records if item.raw.source_file == "app/main.go"
    )
    assert record.status == "resolved"
    assert record.import_target_id == (
        "third_party/dep/client::example.com/dep/client#package"
    )
    assert record.target_id == "third_party/dep/client/client.go::New#function"


def test_go_unexported_method_duplicate_missing_and_external_cases_fail_closed(
    tmp_path: Path,
):
    module = GoModule(
        source="go.mod",
        root=".",
        module_path="example.com/project",
        requirements=(),
        exclusions=(),
        replacements=(),
    )
    records, _, _ = _resolve_go_tree(
        tmp_path,
        {
            "store/first.go": (
                "package store\n"
                "const hidden = 1\n"
                "type Record struct{}\n"
                "func Open() {}\n"
                "func Duplicate() {}\n"
                "func (Record) Method() {}\n"
            ),
            "store/second.go": "package store\nfunc Duplicate() {}\n",
            "audit/log.go": "package audit\nfunc Log() {}\n",
            "wrong/wrong.go": "package wrong\nfunc Missing() {}\n",
            "cmd/use/main.go": (
                "package main\n"
                "import (\n"
                '    "example.com/project/audit"\n'
                '    "example.com/project/store"\n'
                ")\n"
                "func run() { store.hidden; store.Record.Method; "
                "store.Missing(); store.Duplicate() }\n"
            ),
            "cmd/shadow/main.go": (
                "package main\n"
                'import depot "example.com/project/store"\n'
                "func run(depot int) { depot.Open() }\n"
            ),
            "cmd/external/main.go": (
                "package main\n"
                'import "external.invalid/pkg"\n'
                "func run() { pkg.Open() }\n"
            ),
            "one/pkg.go": "package shared\nfunc Open() {}\n",
            "two/pkg.go": "package shared\nfunc Open() {}\n",
            "cmd/ambiguous/main.go": (
                "package main\n"
                "import (\n"
                '    "example.com/project/one"\n'
                '    "example.com/project/two"\n'
                ")\n"
                "func run() { shared.Open() }\n"
            ),
        },
        modules=(module,),
    )

    outcomes = {
        record.raw.text: (
            record.status,
            record.unresolved_reason,
            record.import_unresolved_reason,
            record.target_id,
        )
        for record in records
        if record.raw.source_file.startswith("cmd/")
    }
    assert outcomes == {
        "store.hidden": ("unresolved", "target_inaccessible", None, None),
        "store.Record.Method": (
            "unresolved",
            "unsupported_reference",
            None,
            None,
        ),
        "store.Missing": ("unresolved", "target_not_indexed", None, None),
        "store.Duplicate": ("unresolved", "ambiguous_target", None, None),
        "depot.Open": ("unresolved", "binding_shadowed", None, None),
        "pkg.Open": ("unresolved", "import_unresolved", "external", None),
        "shared.Open": ("unresolved", "ambiguous_binding", None, None),
    }
    store_reference = next(
        record.raw for record in records if record.raw.text == "store.Missing"
    )
    assert len(store_reference.candidate_bindings) == 2


def test_go_dot_and_blank_imports_never_create_symbol_reference_candidates(
    tmp_path: Path,
):
    module = GoModule(
        source="go.mod",
        root=".",
        module_path="example.com/project",
        requirements=(),
        exclusions=(),
        replacements=(),
    )
    records, _, batches = _resolve_go_tree(
        tmp_path,
        {
            "store/store.go": "package store\nfunc Open() {}\n",
            "cmd/dot/main.go": (
                "package main\n"
                'import . "example.com/project/store"\n'
                "func run() { Open() }\n"
            ),
            "cmd/blank/main.go": (
                "package main\n"
                'import _ "example.com/project/store"\n'
                "func run() {}\n"
            ),
        },
        modules=(module,),
    )

    assert not [
        record for record in records if record.raw.source_file.startswith("cmd/")
    ]
    assert not [
        reference
        for batch in batches
        if batch.go_package is not None and batch.go_package.name == "main"
        for reference in batch.references
    ]


def test_resolves_javascript_named_namespace_default_and_type_only_bindings(
    tmp_path: Path,
):
    records, _, _ = _resolve_javascript_tree(
        tmp_path,
        {
            "src/model.ts": (
                "export class Thing {}\n"
                "export interface Shape {}\n"
                "export default function Factory() {}\n"
            ),
            "src/wrong.ts": "export class Thing {}\n",
            "src/use.ts": (
                'import Factory, {Thing as Alias, type Shape} from "./model.js";\n'
                'import type {Shape as StatementShape} from "./model.js";\n'
                'import * as model from "./model.js";\n'
                "function run(value: Shape, other: StatementShape) { "
                "Alias; model.Thing; Factory; }\n"
            ),
        },
    )

    selected = [record for record in records if record.raw.source_file == "src/use.ts"]

    assert [record.raw.text for record in selected] == [
        "Shape",
        "StatementShape",
        "Alias",
        "model.Thing",
        "Factory",
    ]
    assert [record.target_id for record in selected] == [
        "src/model.ts::Shape#interface",
        "src/model.ts::Shape#interface",
        "src/model.ts::Thing#class",
        "src/model.ts::Thing#class",
        "src/model.ts::Factory#function",
    ]
    assert [record.resolution_basis for record in selected] == [
        "direct_binding",
        "direct_binding",
        "direct_binding",
        "qualified_member",
        "direct_binding",
    ]
    assert [record.binding.type_only for record in selected if record.binding] == [
        True,
        True,
        False,
        False,
        False,
    ]
    assert {record.status for record in selected} == {"resolved"}


def test_resolves_javascript_local_export_alias_and_named_reexport(
    tmp_path: Path,
):
    records, _, _ = _resolve_javascript_tree(
        tmp_path,
        {
            "src/model.ts": (
                "export class Thing {}\n"
                "export default function Factory() {}\n"
            ),
            "src/local.ts": "class Local {}\nexport {Local as Renamed};\n",
            "src/named.ts": (
                'export {Thing as PublicThing, default as PublicFactory} '
                'from "./model.js";\n'
            ),
            "src/use.ts": (
                'import {Renamed} from "./local.js";\n'
                'import {PublicThing, PublicFactory} from "./named.js";\n'
                "function run() { Renamed; PublicThing; PublicFactory; }\n"
            ),
        },
    )

    selected = [record for record in records if record.raw.source_file == "src/use.ts"]

    assert [record.target_id for record in selected] == [
        "src/local.ts::Local#class",
        "src/model.ts::Thing#class",
        "src/model.ts::Factory#function",
    ]
    assert [record.resolution_basis for record in selected] == [
        "direct_binding",
        "reexport_chain",
        "reexport_chain",
    ]
    assert [[support.kind for support in record.support] for record in selected] == [
        ["import_binding", "local_export", "definition"],
        ["import_binding", "reexport", "definition"],
        ["import_binding", "reexport", "definition"],
    ]


def test_resolves_javascript_star_barrels_but_never_forwards_default(
    tmp_path: Path,
):
    records, _, _ = _resolve_javascript_tree(
        tmp_path,
        {
            "src/model.ts": (
                "export class Thing {}\n"
                "export default function Factory() {}\n"
            ),
            "src/first.ts": 'export * from "./model.js";\n',
            "src/second.ts": 'export * from "./first.js";\n',
            "src/use.ts": (
                'import Factory, {Thing} from "./second.js";\n'
                "function run() { Thing; Factory; }\n"
            ),
        },
    )

    selected = [record for record in records if record.raw.source_file == "src/use.ts"]

    assert [(record.raw.text, record.target_id) for record in selected] == [
        ("Thing", "src/model.ts::Thing#class"),
        ("Factory", None),
    ]
    assert selected[0].resolution_basis == "reexport_chain"
    assert [support.kind for support in selected[0].support] == [
        "import_binding",
        "reexport",
        "reexport",
        "definition",
    ]
    assert selected[1].unresolved_reason == "target_not_indexed"


def test_javascript_star_conflicts_and_wrong_file_names_never_select_a_target(
    tmp_path: Path,
):
    records, _, _ = _resolve_javascript_tree(
        tmp_path,
        {
            "src/left.ts": "export class Thing {}\n",
            "src/right.ts": "export class Thing {}\n",
            "src/wrong.ts": "export class Missing {}\n",
            "src/barrel.ts": (
                'export * from "./left.js";\n'
                'export * from "./right.js";\n'
            ),
            "src/use.ts": (
                'import {Thing, Missing} from "./barrel.js";\n'
                "function run() { Thing; Missing; }\n"
            ),
        },
    )

    selected = [record for record in records if record.raw.source_file == "src/use.ts"]

    assert [(record.raw.text, record.unresolved_reason) for record in selected] == [
        ("Thing", "ambiguous_target"),
        ("Missing", "target_not_indexed"),
    ]
    assert all(record.target_id is None for record in selected)


def test_javascript_explicit_reexport_overrides_same_name_star_candidate(
    tmp_path: Path,
):
    records, _, _ = _resolve_javascript_tree(
        tmp_path,
        {
            "src/selected.ts": "export class Thing {}\n",
            "src/ignored.ts": "export class Thing {}\n",
            "src/barrel.ts": (
                'export {Thing} from "./selected.js";\n'
                'export * from "./ignored.js";\n'
            ),
            "src/use.ts": (
                'import {Thing} from "./barrel.js";\n'
                "function run() { Thing; }\n"
            ),
        },
    )

    record = next(record for record in records if record.raw.source_file == "src/use.ts")

    assert record.target_id == "src/selected.ts::Thing#class"
    assert record.resolution_basis == "reexport_chain"


def test_javascript_star_cycles_resolve_only_a_single_convergent_target(
    tmp_path: Path,
):
    records, _, _ = _resolve_javascript_tree(
        tmp_path,
        {
            "src/a.ts": 'export * from "./b.js";\n',
            "src/b.ts": (
                'export * from "./a.js";\n'
                "export class Seed {}\n"
            ),
            "src/use.ts": (
                'import {Seed, Missing} from "./a.js";\n'
                "function run() { Seed; Missing; }\n"
            ),
        },
    )

    selected = [record for record in records if record.raw.source_file == "src/use.ts"]

    assert selected[0].target_id == "src/b.ts::Seed#class"
    assert selected[0].resolution_basis == "reexport_chain"
    assert selected[1].target_id is None
    assert selected[1].unresolved_reason == "ambiguous_target"


def test_javascript_workspace_barrel_preserves_stage_8_control_provenance(
    tmp_path: Path,
):
    records, _, _ = _resolve_javascript_tree(
        tmp_path,
        {
            "apps/web/src/use.ts": (
                'import {Thing} from "@repo/core";\n'
                "export function run() { return Thing; }\n"
            ),
            "packages/core/src/index.ts": 'export * from "./model.js";\n',
            "packages/core/src/model.ts": "export class Thing {}\n",
        },
        controls={
            "package.json": '{"name":"root","workspaces":["apps/*","packages/*"]}',
            "apps/web/package.json": (
                '{"name":"@repo/web","dependencies":{"@repo/core":"workspace:*"}}'
            ),
            "packages/core/package.json": (
                '{"name":"@repo/core","exports":"./src/index.ts"}'
            ),
        },
    )

    record = next(
        record for record in records if record.raw.source_file == "apps/web/src/use.ts"
    )

    assert record.target_id == "packages/core/src/model.ts::Thing#class"
    assert record.resolution_basis == "reexport_chain"
    assert record.resolution_control_files == (
        "apps/web/package.json",
        "package.json",
        "packages/core/package.json",
    )


def test_javascript_anonymous_default_computed_and_commonjs_cases_fail_closed(
    tmp_path: Path,
):
    records, _, batches = _resolve_javascript_tree(
        tmp_path,
        {
            "src/model.ts": "export default function () {}\nexport class Thing {}\n",
            "src/use.ts": (
                'import Factory from "./model.js";\n'
                'import * as model from "./model.js";\n'
                "Factory; model[name];\n"
                'const legacy = require("./model.js"); legacy.Thing;\n'
            ),
        },
    )

    selected = [record for record in records if record.raw.source_file == "src/use.ts"]

    assert [(record.raw.text, record.unresolved_reason) for record in selected] == [
        ("Factory", "target_not_indexed"),
        ("model[name]", "unsupported_reference"),
    ]
    use_batch = next(
        batch
        for batch in batches
        if any(raw.source_file == "src/use.ts" for raw in batch.imports)
    )
    assert len(use_batch.imports) == 2
    assert all(reference.path[0] != "legacy" for reference in use_batch.references)


def test_javascript_reexport_pass_limit_fails_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(_javascript_references, "MAX_REFERENCE_REEXPORT_PASSES", 1)

    records, _, _ = _resolve_javascript_tree(
        tmp_path,
        {
            "src/model.ts": "export class Thing {}\n",
            "src/first.ts": 'export * from "./model.js";\n',
            "src/second.ts": 'export * from "./first.js";\n',
            "src/use.ts": (
                'import {Thing} from "./second.js";\n'
                "function run() { Thing; }\n"
            ),
        },
    )

    record = next(record for record in records if record.raw.source_file == "src/use.ts")

    assert record.target_id is None
    assert record.unresolved_reason == "ambiguous_target"


def test_javascript_external_and_unsupported_config_failures_retain_provenance(
    tmp_path: Path,
):
    external_records, _, _ = _resolve_javascript_tree(
        tmp_path / "external",
        {
            "src/use.ts": (
                'import {External} from "react";\n'
                "function run() { External; }\n"
            ),
        },
    )
    configured_records, _, _ = _resolve_javascript_tree(
        tmp_path / "configured",
        {
            "src/model.ts": "export class Thing {}\n",
            "src/use.ts": (
                'import {Thing} from "./model.js";\n'
                "function run() { Thing; }\n"
            ),
        },
        controls={
            "tsconfig.json": (
                '{"compilerOptions":{"plugins":[{"name":"custom-loader"}]}}'
            ),
        },
    )

    external = external_records[0]
    configured = configured_records[0]
    assert (
        external.unresolved_reason,
        external.import_unresolved_reason,
        external.resolution_control_files,
    ) == ("import_unresolved", "external", ())
    assert (
        configured.unresolved_reason,
        configured.import_unresolved_reason,
        configured.resolution_control_files,
    ) == ("import_unresolved", "unsupported_configuration", ("tsconfig.json",))


def test_reference_index_rejects_stale_javascript_export_evidence(tmp_path: Path):
    _, symbols, batches = _resolve_javascript_tree(
        tmp_path,
        {
            "src/model.ts": "export class Thing {}\n",
            "src/use.ts": (
                'import {Thing} from "./model.js";\n'
                "function run() { Thing; }\n"
            ),
        },
    )
    file_nodes = {
        symbol.file_path: symbol for symbol in symbols if symbol.kind == "file"
    }
    imports = resolve_imports(
        [raw for batch in batches for raw in batch.imports],
        file_nodes=file_nodes,
    )
    exports = [export for batch in batches for export in batch.exports]
    stale = replace(exports[0], source_hash="f" * 64)

    with pytest.raises(GraphContractError, match="stale"):
        build_reference_resolver_index(symbols, imports, [stale, *exports[1:]])


def test_resolves_python_direct_alias_and_qualified_members_inside_exact_endpoint(
    tmp_path: Path,
):
    records, _, _ = _resolve_python_tree(
        tmp_path,
        {
            "pkg/__init__.py": "",
            "pkg/model.py": "class Thing:\n    pass\n",
            "wrong.py": "class Thing:\n    pass\n",
            "use.py": (
                "from pkg.model import Thing as Alias\n"
                "import pkg.model as model\n"
                "import pkg.model\n"
                "\n"
                "def run():\n"
                "    return Alias(), model.Thing(), pkg.model.Thing()\n"
            ),
        },
    )

    use_records = [record for record in records if record.raw.source_file == "use.py"]

    assert [record.raw.path for record in use_records] == [
        ("Alias",),
        ("model", "Thing"),
        ("pkg", "model", "Thing"),
    ]
    assert {record.status for record in use_records} == {"resolved"}
    assert {record.target_id for record in use_records} == {
        "pkg/model.py::Thing#class"
    }
    assert [record.resolution_basis for record in use_records] == [
        "direct_binding",
        "qualified_member",
        "qualified_member",
    ]
    assert {record.source_id for record in use_records} == {
        "use.py::run#function"
    }


def test_python_from_imported_submodule_resolves_member_inside_submodule(
    tmp_path: Path,
):
    records, _, _ = _resolve_python_tree(
        tmp_path,
        {
            "pkg/__init__.py": "",
            "pkg/model.py": "class Thing:\n    pass\n",
            "pkg/relative_use.py": (
                "from . import model as relative_model\n"
                "def build():\n"
                "    return relative_model.Thing()\n"
            ),
            "use.py": (
                "from pkg import model as absolute_model\n"
                "def build():\n"
                "    return absolute_model.Thing()\n"
            ),
        },
    )

    selected = [
        record
        for record in records
        if record.raw.source_file in {"pkg/relative_use.py", "use.py"}
    ]

    assert len(selected) == 2
    assert {record.status for record in selected} == {"resolved"}
    assert {record.target_id for record in selected} == {
        "pkg/model.py::Thing#class"
    }
    assert {record.resolution_basis for record in selected} == {
        "qualified_member"
    }


def test_source_owner_uses_smallest_symbol_and_module_code_uses_file_node(
    tmp_path: Path,
):
    records, _, _ = _resolve_python_tree(
        tmp_path,
        {
            "model.py": "class Thing:\n    pass\n",
            "use.py": (
                "from model import Thing\n"
                "Thing()\n"
                "\n"
                "class Factory:\n"
                "    def make(self):\n"
                "        return Thing()\n"
            ),
        },
    )

    assert [(record.source_id, record.source_kind) for record in records] == [
        ("use.py::__file__#file", "file"),
        ("use.py::Factory.make#method", "method"),
    ]


def test_equal_span_source_ambiguity_falls_back_to_file_without_guessing(
    tmp_path: Path,
):
    _, symbols, batches = _resolve_python_tree(
        tmp_path,
        {
            "model.py": "class Thing:\n    pass\n",
            "use.py": (
                "from model import Thing\n"
                "def run():\n"
                "    return Thing()\n"
            ),
        },
    )
    run = next(symbol for symbol in symbols if symbol.id == "use.py::run#function")
    duplicate = replace(
        run,
        id="use.py::run_alias#function",
        name="run_alias",
        qualified_name="run_alias",
    )
    file_nodes = {
        symbol.file_path: symbol for symbol in symbols if symbol.kind == "file"
    }
    imports = resolve_imports(
        [raw for batch in batches for raw in batch.imports],
        file_nodes=file_nodes,
    )
    exports = [export for batch in batches for export in batch.exports]
    observations = [reference for batch in batches for reference in batch.references]
    index = build_reference_resolver_index([*symbols, duplicate], imports, exports)

    record = resolve_symbol_references(observations, imports=imports, index=index)[0]

    assert record.status == "unresolved"
    assert record.unresolved_reason == "ambiguous_source"
    assert record.source_id == "use.py::__file__#file"
    assert record.source_kind == "file"
    assert record.target_id is None


def test_python_failures_are_retained_without_off_endpoint_name_matching(
    tmp_path: Path,
):
    records, _, _ = _resolve_python_tree(
        tmp_path,
        {
            "model.py": "class Thing:\n    pass\n",
            "wrong.py": "class Missing:\n    pass\n",
            "use.py": (
                "from model import Missing\n"
                "from nowhere import External\n"
                "from model import Thing\n"
                "\n"
                "def shadowed(Thing):\n"
                "    return Thing()\n"
                "\n"
                "def dynamic(name):\n"
                "    return Thing[name]\n"
                "\n"
                "def missing():\n"
                "    return Missing()\n"
                "\n"
                "def external():\n"
                "    return External()\n"
            ),
        },
    )

    outcomes = {
        record.raw.text: (
            record.status,
            record.unresolved_reason,
            record.import_unresolved_reason,
        )
        for record in records
        if record.raw.source_file == "use.py"
    }

    assert outcomes == {
        "Thing": ("unresolved", "binding_shadowed", None),
        "Thing[name]": ("unresolved", "unsupported_reference", None),
        "Missing": ("unresolved", "target_not_indexed", None),
        "External": ("unresolved", "import_unresolved", "not_indexed"),
    }


def test_python_named_reexport_chain_resolves_with_complete_support(
    tmp_path: Path,
):
    records, _, _ = _resolve_python_tree(
        tmp_path,
        {
            "pkg/__init__.py": "from .model import Thing\n",
            "pkg/model.py": "class Thing:\n    pass\n",
            "use.py": (
                "from pkg import Thing\n"
                "def run():\n"
                "    return Thing()\n"
            ),
        },
    )

    record = next(record for record in records if record.raw.source_file == "use.py")

    assert record.status == "resolved"
    assert record.target_id == "pkg/model.py::Thing#class"
    assert record.resolution_basis == "reexport_chain"
    assert [support.kind for support in record.support] == [
        "import_binding",
        "reexport",
        "definition",
    ]
    assert [support.file for support in record.support] == [
        "use.py",
        "pkg/__init__.py",
        "pkg/model.py",
    ]


def test_python_reexport_cycle_converges_only_when_it_has_one_exact_target(
    tmp_path: Path,
):
    records, _, _ = _resolve_python_tree(
        tmp_path,
        {
            "pkg/__init__.py": "",
            "pkg/a.py": "from .b import Thing\n",
            "pkg/b.py": "from .a import Thing\nclass Thing:\n    pass\n",
            "use.py": (
                "from pkg.a import Thing\n"
                "def run():\n"
                "    return Thing()\n"
            ),
        },
    )

    record = next(record for record in records if record.raw.source_file == "use.py")

    assert record.status == "resolved"
    assert record.target_id == "pkg/b.py::Thing#class"
    assert record.resolution_basis == "reexport_chain"


def test_python_unseeded_reexport_cycle_stays_ambiguous(tmp_path: Path):
    records, _, _ = _resolve_python_tree(
        tmp_path,
        {
            "pkg/__init__.py": "",
            "pkg/a.py": "from .b import Thing\n",
            "pkg/b.py": "from .a import Thing\n",
            "use.py": (
                "from pkg.a import Thing\n"
                "def run():\n"
                "    return Thing()\n"
            ),
        },
    )

    record = next(record for record in records if record.raw.source_file == "use.py")

    assert record.status == "unresolved"
    assert record.unresolved_reason == "ambiguous_target"
    assert record.target_id is None


def test_python_ambiguous_and_star_reexports_never_select_a_target(
    tmp_path: Path,
):
    records, _, _ = _resolve_python_tree(
        tmp_path,
        {
            "pkg/__init__.py": (
                "from .left import Thing\n"
                "from .right import Thing\n"
                "from .stars import *\n"
            ),
            "pkg/left.py": "class Thing:\n    pass\n",
            "pkg/right.py": "class Thing:\n    pass\n",
            "pkg/stars.py": "class StarThing:\n    pass\n",
            "use.py": (
                "from pkg import Thing, StarThing\n"
                "def run():\n"
                "    return Thing(), StarThing()\n"
            ),
        },
    )

    outcomes = {
        record.raw.path[0]: (record.unresolved_reason, record.target_id)
        for record in records
        if record.raw.source_file == "use.py"
    }

    assert outcomes == {
        "Thing": ("ambiguous_target", None),
        "StarThing": ("target_not_indexed", None),
    }


def test_python_reexport_pass_limit_fails_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(_python_references, "MAX_REFERENCE_REEXPORT_PASSES", 1)

    records, _, _ = _resolve_python_tree(
        tmp_path,
        {
            "pkg/__init__.py": "",
            "pkg/a.py": "from .b import Thing\n",
            "pkg/b.py": "from .c import Thing\n",
            "pkg/c.py": "class Thing:\n    pass\n",
            "use.py": (
                "from pkg.a import Thing\n"
                "def run():\n"
                "    return Thing()\n"
            ),
        },
    )

    record = next(record for record in records if record.raw.source_file == "use.py")

    assert record.status == "unresolved"
    assert record.unresolved_reason == "ambiguous_target"
    assert record.target_id is None


def test_reference_index_rejects_stale_python_export_evidence(tmp_path: Path):
    _, symbols, batches = _resolve_python_tree(
        tmp_path,
        {
            "model.py": "class Thing:\n    pass\n",
            "use.py": "from model import Thing\nThing()\n",
        },
    )
    file_nodes = {
        symbol.file_path: symbol for symbol in symbols if symbol.kind == "file"
    }
    imports = resolve_imports(
        [raw for batch in batches for raw in batch.imports],
        file_nodes=file_nodes,
    )
    exports = [export for batch in batches for export in batch.exports]
    stale = replace(exports[0], source_hash="f" * 64)

    with pytest.raises(GraphContractError, match="stale"):
        build_reference_resolver_index(symbols, imports, [stale, *exports[1:]])
