from __future__ import annotations
import hashlib

from pathlib import Path

from loci.graph.swift_modules import (
    MAX_SWIFT_CONTROL_BYTES,
    build_swift_module_index,
    load_swift_module_context,
    make_swift_module_id,
)


def _package(root: Path, relative: str, body: str, *, sources: tuple[str, ...] = ()) -> Path:
    manifest = root / relative / "Package.swift"
    manifest.parent.mkdir(parents=True, exist_ok=True)
    manifest.write_text(body, encoding="utf-8")
    for source in sources:
        path = root / relative / source
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("public struct Placeholder {}\n", encoding="utf-8")
    return manifest


def _load(root: Path):
    load = load_swift_module_context(root, sorted(root.rglob("Package.swift")))
    return load, build_swift_module_index(load.context)


_SIMPLE = """// swift-tools-version:5.9
import PackageDescription

let package = Package(
    name: "Feature",
    targets: [
        .target(name: "Feature"),
        .testTarget(name: "FeatureTests", dependencies: ["Feature"])
    ]
)
"""


def test_literal_manifest_yields_one_module_per_target(tmp_path: Path):
    _package(
        tmp_path,
        "pkg",
        _SIMPLE,
        sources=("Sources/Feature/a.swift", "Tests/FeatureTests/b.swift"),
    )

    load, build = _load(tmp_path)

    assert not load.problems
    assert not build.problems
    assert [node.name for node in build.index.module_nodes] == [
        "Feature",
        "FeatureTests",
    ]
    module = build.index.modules_by_name["Feature"]
    assert module.id == make_swift_module_id("pkg", "Feature")
    assert module.kind == "module"
    assert module.language == "swift"
    assert module.file_path == "pkg/Package.swift"
    assert module.line == 7
    assert build.index.directories_by_module[module.id] == "pkg/Sources/Feature"
    assert load.input_hashes["pkg/Package.swift"]


def test_target_dependencies_are_read_from_both_declaration_forms(tmp_path: Path):
    _package(
        tmp_path,
        "pkg",
        """// swift-tools-version:5.9
import PackageDescription

let package = Package(
    name: "Feature",
    targets: [
        .target(name: "Core"),
        .target(
            name: "Feature",
            dependencies: ["Core", .target(name: "Extra"), .product(name: "Rx", package: "rx")]
        ),
        .target(name: "Extra")
    ]
)
""",
        sources=(
            "Sources/Core/a.swift",
            "Sources/Feature/b.swift",
            "Sources/Extra/c.swift",
        ),
    )

    load, _ = _load(tmp_path)

    targets = {target.name: target for target in load.context.packages[0].targets}
    assert targets["Feature"].dependencies == ("Core", "Extra")


def test_explicit_path_and_empty_path_are_both_honoured(tmp_path: Path):
    _package(
        tmp_path,
        "pkg",
        """// swift-tools-version:5.9
import PackageDescription

let package = Package(
    name: "Feature",
    targets: [
        .target(name: "Elsewhere", path: "custom/here"),
        .target(name: "AtRoot", path: "")
    ]
)
""",
        sources=("custom/here/a.swift",),
    )

    _, build = _load(tmp_path)

    directories = build.index.directories_by_module
    assert directories[make_swift_module_id("pkg", "Elsewhere")] == "pkg/custom/here"
    assert directories[make_swift_module_id("pkg", "AtRoot")] == "pkg"


def test_a_sole_target_falls_back_to_the_bare_sources_directory(tmp_path: Path):
    _package(
        tmp_path,
        "pkg",
        """// swift-tools-version:5.9
import PackageDescription

let package = Package(name: "Feature", targets: [.target(name: "Feature")])
""",
        sources=("Sources/Model/a.swift",),
    )

    _, build = _load(tmp_path)

    module = build.index.modules_by_name["Feature"]
    assert build.index.directories_by_module[module.id] == "pkg/Sources"


def test_two_targets_do_not_share_the_bare_sources_directory(tmp_path: Path):
    _package(
        tmp_path,
        "pkg",
        """// swift-tools-version:5.9
import PackageDescription

let package = Package(
    name: "Feature",
    targets: [.target(name: "One"), .target(name: "Two")]
)
""",
        sources=("Sources/loose.swift",),
    )

    load, build = _load(tmp_path)

    assert {problem.details["reason"] for problem in load.problems} == {
        "target_directory_missing"
    }
    assert build.index.directories_by_module == {}
    assert [node.name for node in build.index.module_nodes] == ["One", "Two"]
    assert all(
        node.metadata["loci"]["has_sources"] is False
        for node in build.index.module_nodes
    )


def test_a_computed_target_list_is_unsupported_rather_than_guessed(tmp_path: Path):
    _package(
        tmp_path,
        "pkg",
        """// swift-tools-version:5.9
import PackageDescription

let isDevelop = false
let extra: [Target] = isDevelop ? [.target(name: "Extra")] : []

let package = Package(
    name: "Feature",
    targets: [.target(name: "Feature")] + extra
)
""",
        sources=("Sources/Feature/a.swift",),
    )

    load, build = _load(tmp_path)

    assert load.context.packages == ()
    assert [problem.details["reason"] for problem in load.problems] == [
        "unsupported_configuration"
    ]
    assert build.index.module_nodes == ()


def test_a_computed_target_name_drops_only_that_target(tmp_path: Path):
    _package(
        tmp_path,
        "pkg",
        """// swift-tools-version:5.9
import PackageDescription

let generated = "Generated"

let package = Package(
    name: "Feature",
    targets: [.target(name: generated), .target(name: "Feature")]
)
""",
        sources=("Sources/Feature/a.swift",),
    )

    load, build = _load(tmp_path)

    assert [problem.details["reason"] for problem in load.problems] == [
        "unsupported_configuration"
    ]
    assert [node.name for node in build.index.module_nodes] == ["Feature"]


def test_a_plugin_dependency_is_not_read_as_a_target(tmp_path: Path):
    _package(
        tmp_path,
        "pkg",
        """// swift-tools-version:5.9
import PackageDescription

let package = Package(
    name: "Feature",
    targets: [
        .target(
            name: "Feature",
            plugins: [.plugin(name: "OpenAPIGenerator", package: "swift-openapi-generator")]
        )
    ]
)
""",
        sources=("Sources/Feature/a.swift",),
    )

    _, build = _load(tmp_path)

    assert [node.name for node in build.index.module_nodes] == ["Feature"]


def test_a_target_name_two_packages_declare_is_dropped(tmp_path: Path):
    body = """// swift-tools-version:5.9
import PackageDescription

let package = Package(name: "%s", targets: [.target(name: "Shared")])
"""
    _package(tmp_path, "one", body % "One", sources=("Sources/Shared/a.swift",))
    _package(tmp_path, "two", body % "Two", sources=("Sources/Shared/b.swift",))

    _, build = _load(tmp_path)

    assert build.index.module_nodes == ()
    assert [problem.details["reason"] for problem in build.problems] == [
        "duplicate_target_name"
    ]
    assert build.problems[0].details["sources"] == [
        "one/Package.swift",
        "two/Package.swift",
    ]


def test_a_path_escaping_the_repository_is_refused(tmp_path: Path):
    repo = tmp_path / "repo"
    repo.mkdir()
    (tmp_path / "outside").mkdir()
    _package(
        repo,
        "pkg",
        """// swift-tools-version:5.9
import PackageDescription

let package = Package(
    name: "Feature",
    targets: [.target(name: "Feature", path: "../../outside")]
)
""",
    )

    load, build = _load(repo)

    assert [problem.details["reason"] for problem in load.problems] == [
        "path_outside_repository"
    ]
    assert build.index.directories_by_module == {}


def test_a_symlinked_manifest_is_refused(tmp_path: Path):
    _package(tmp_path, "real", _SIMPLE, sources=("Sources/Feature/a.swift",))
    link_dir = tmp_path / "link"
    link_dir.mkdir()
    (link_dir / "Package.swift").symlink_to(tmp_path / "real" / "Package.swift")

    load, _ = _load(tmp_path)

    refused = {
        problem.source: problem.details["reason"] for problem in load.problems
    }
    assert refused["link/Package.swift"] == "symlink"
    assert "real/Package.swift" not in refused or refused[
        "real/Package.swift"
    ] != "symlink"


def test_an_oversized_manifest_is_refused(tmp_path: Path):
    _package(
        tmp_path,
        "pkg",
        "// " + "x" * MAX_SWIFT_CONTROL_BYTES + "\n",
    )

    load, _ = _load(tmp_path)

    assert load.problems[0].details["reason"] == "control_file_too_large"
    assert load.problems[0].details["limit"] == MAX_SWIFT_CONTROL_BYTES


def test_a_manifest_without_a_package_call_is_unsupported(tmp_path: Path):
    _package(tmp_path, "pkg", "import PackageDescription\nlet x = 1\n")

    load, _ = _load(tmp_path)

    assert [problem.details["reason"] for problem in load.problems] == [
        "unsupported_configuration"
    ]


def _swift_repo(root: Path) -> None:
    _package(
        root,
        "Core",
        """// swift-tools-version:5.9
import PackageDescription

let package = Package(name: "Core", targets: [.target(name: "LottoCore")])
""",
        sources=("Sources/LottoCore/core.swift",),
    )
    app = root / "App"
    app.mkdir(parents=True, exist_ok=True)
    (app / "main.swift").write_text(
        "import Foundation\nimport LottoCore\nimport struct LottoCore.Ticket\n",
        encoding="utf-8",
    )


def test_a_swift_import_of_a_declared_target_resolves_to_its_module(tmp_path: Path):
    import hashlib

    from loci.graph.imports import materialize_import_edges, resolve_imports
    from loci.parser.imports import extract_import_batch
    from loci.parser.symbols import make_file_symbol

    _swift_repo(tmp_path)
    _, build = _load(tmp_path)

    source = tmp_path / "App" / "main.swift"
    body = source.read_bytes()
    source_hash = hashlib.sha256(body).hexdigest()
    file_nodes = {
        "App/main.swift": make_file_symbol(
            "App/main.swift",
            language="swift",
            content_hash=source_hash,
        )
    }
    batch = extract_import_batch(
        source,
        source_file="App/main.swift",
        language="swift",
        source_hash=source_hash,
    )

    records = resolve_imports(
        batch.imports,
        file_nodes=file_nodes,
        swift_modules=build.index,
    )
    outcomes = {
        record.raw.specifier: (record.status, record.target_kind, record.target_module)
        for record in records
    }
    assert outcomes == {
        "Foundation": ("unresolved", None, None),
        "LottoCore": ("resolved", "module", "LottoCore"),
        "LottoCore.Ticket": ("resolved", "module", "LottoCore"),
    }

    edges = materialize_import_edges(
        records,
        file_nodes=file_nodes,
        swift_modules=build.index,
    )
    assert [(edge.type, edge.to_id) for edge in edges] == [
        ("imports", make_swift_module_id("Core", "LottoCore"))
    ]
    assert edges[0].resolution == "import-resolved"
    assert edges[0].evidence.file == "App/main.swift"


def test_a_swift_import_stays_external_without_a_module_index(tmp_path: Path):
    import hashlib

    from loci.graph.imports import resolve_imports
    from loci.parser.imports import extract_import_batch
    from loci.parser.symbols import make_file_symbol

    _swift_repo(tmp_path)
    source = tmp_path / "App" / "main.swift"
    body = source.read_bytes()
    source_hash = hashlib.sha256(body).hexdigest()
    file_nodes = {
        "App/main.swift": make_file_symbol(
            "App/main.swift",
            language="swift",
            content_hash=source_hash,
        )
    }
    batch = extract_import_batch(
        source,
        source_file="App/main.swift",
        language="swift",
        source_hash=source_hash,
    )

    records = resolve_imports(batch.imports, file_nodes=file_nodes)

    assert {record.status for record in records} == {"unresolved"}
    assert {record.unresolved_reason for record in records} == {"external"}


def test_a_module_edge_is_rejected_when_its_endpoint_is_not_a_module_node(
    tmp_path: Path,
):
    import hashlib

    import pytest

    from loci.graph.contracts import GraphContractError, validate_graph_edges
    from loci.graph.imports import materialize_import_edges, resolve_imports
    from loci.parser.imports import extract_import_batch
    from loci.parser.symbols import make_file_symbol

    _swift_repo(tmp_path)
    _, build = _load(tmp_path)
    source = tmp_path / "App" / "main.swift"
    body = source.read_bytes()
    source_hash = hashlib.sha256(body).hexdigest()
    file_node = make_file_symbol(
        "App/main.swift",
        language="swift",
        content_hash=source_hash,
    )
    file_nodes = {"App/main.swift": file_node}
    batch = extract_import_batch(
        source,
        source_file="App/main.swift",
        language="swift",
        source_hash=source_hash,
    )
    records = resolve_imports(
        batch.imports,
        file_nodes=file_nodes,
        swift_modules=build.index,
    )
    edges = materialize_import_edges(
        records,
        file_nodes=file_nodes,
        swift_modules=build.index,
    )
    module = build.index.modules_by_name["LottoCore"]
    nodes = {
        file_node.id: file_node.to_dict(),
        module.id: module.to_dict(),
    }
    hashes = {"App/main.swift": source_hash, "Core/Package.swift": module.content_hash}

    validate_graph_edges(
        edges,
        indexed_nodes=nodes,
        file_hashes=hashes,
        imports=records,
    )

    stripped = dict(module.to_dict())
    stripped["metadata"] = {"loci": {"swift_module_node": False}}
    with pytest.raises(GraphContractError) as error:
        validate_graph_edges(
            edges,
            indexed_nodes={file_node.id: file_node.to_dict(), module.id: stripped},
            file_hashes=hashes,
            imports=records,
        )

    assert error.value.code == "INVALID_GRAPH_EDGE"


def test_a_manifest_input_hash_is_the_hash_of_its_content(tmp_path: Path):
    manifest = """// swift-tools-version:5.9
import PackageDescription

let package = Package(name: "Feature", targets: [.target(name: "Feature")])
"""
    _package(tmp_path, "pkg", manifest, sources=("Sources/Feature/a.swift",))

    load, _ = _load(tmp_path)

    assert load.input_hashes == {
        "pkg/Package.swift": hashlib.sha256(manifest.encode()).hexdigest()
    }
