from __future__ import annotations

import pytest

from loci.graph.contracts import GraphEdge, GraphEvidence
from loci.graph.imports import ImportRecord, materialize_import_edges, resolve_import
from loci.parser.imports import RawImport
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


def test_resolves_absolute_module_before_same_named_package():
    file_nodes = _file_nodes(
        "consumer.py",
        "pkg/mod.py",
        "pkg/mod/__init__.py",
    )

    record = resolve_import(_raw("pkg.mod"), file_nodes=file_nodes)

    assert record.status == "resolved"
    assert record.target_file == "pkg/mod.py"
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
    assert record.target_file == f"src/{expected}"
    assert record.target_id == file_nodes[f"src/{expected}"].id


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


def test_javascript_relative_import_ignores_unsupported_extensions():
    file_nodes = _javascript_file_nodes(
        "src/consumer.ts",
        "src/module.jsx",
    )

    record = resolve_import(
        _javascript_raw("./module"),
        file_nodes=file_nodes,
    )

    assert record.status == "unresolved"
    assert record.unresolved_reason == "not_indexed"


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
