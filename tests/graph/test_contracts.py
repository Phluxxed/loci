from __future__ import annotations

import pytest

from loci.graph.contracts import (
    GRAPH_SCHEMA_VERSION,
    GraphContractError,
    GraphContribution,
    GraphEdge,
    GraphEvidence,
    GraphNodeRef,
    validate_graph_edges,
)
from loci.graph.imports import ImportRecord
from loci.parser.imports import RawImport, RustImportContext


PARENT_ID = "guide.md::Guide#section"
CHILD_ID = "guide.md::Guide > Install#section"
CHILD_HASH = "a" * 64
SOURCE_ID = "src/source.py::__file__#file"
TARGET_ID = "src/target.py::__file__#file"
SOURCE_HASH = "c" * 64
GO_SOURCE_ID = "cmd/server/main.go::__file__#file"
GO_TARGET_ID = "internal/store::example.com/project/internal/store#package"
GO_IMPORT_PATH = "example.com/project/internal/store"
RUST_SOURCE_ID = "app/src/main.rs::__file__#file"
RUST_ROOT_ID = "core/src/lib.rs::__file__#file"
RUST_TARGET_CRATE = "core/Cargo.toml::lib:core"
RUST_TARGET_ID = f"{RUST_TARGET_CRATE}#crate"
RUST_TARGET_HASH = "d" * 64


def _edge(**overrides) -> GraphEdge:
    values = {
        "from_id": PARENT_ID,
        "to_id": CHILD_ID,
        "type": "contains",
        "directed": True,
        "namespace": "loci",
        "resolution": "exact",
        "evidence": GraphEvidence(
            file="guide.md",
            line=5,
            content_hash=CHILD_HASH,
        ),
    }
    values.update(overrides)
    return GraphEdge(**values)


def _indexed_nodes() -> dict[str, dict]:
    return {
        PARENT_ID: {
            "id": PARENT_ID,
            "kind": "section",
            "language": "markdown",
            "file_path": "guide.md",
            "line": 1,
            "content_hash": "b" * 64,
        },
        CHILD_ID: {
            "id": CHILD_ID,
            "kind": "section",
            "language": "markdown",
            "file_path": "guide.md",
            "line": 5,
            "content_hash": CHILD_HASH,
        },
    }


def _import_edge(**overrides) -> GraphEdge:
    values = {
        "from_id": SOURCE_ID,
        "to_id": TARGET_ID,
        "type": "imports",
        "directed": True,
        "namespace": "loci",
        "resolution": "import-resolved",
        "evidence": GraphEvidence(
            file="src/source.py",
            line=3,
            content_hash=SOURCE_HASH,
        ),
    }
    values.update(overrides)
    return GraphEdge(**values)


def _raw_import(**overrides) -> RawImport:
    values = {
        "source_file": "src/source.py",
        "language": "python",
        "line": 3,
        "text": "from target import value",
        "specifier": "target",
        "imported_name": "value",
        "type_only": False,
        "is_reexport": False,
        "source_hash": SOURCE_HASH,
    }
    values.update(overrides)
    return RawImport(**values)


def _import_record(*, raw: RawImport | None = None, **overrides) -> ImportRecord:
    values = {
        "raw": raw or _raw_import(),
        "source_id": SOURCE_ID,
        "target_file": "src/target.py",
        "target_package": None,
        "target_crate": None,
        "target_kind": "file",
        "target_id": TARGET_ID,
        "status": "resolved",
        "unresolved_reason": None,
    }
    values.update(overrides)
    return ImportRecord(**values)


def _import_nodes() -> dict[str, dict]:
    return {
        SOURCE_ID: {
            "id": SOURCE_ID,
            "name": "source.py",
            "kind": "file",
            "language": "python",
            "file_path": "src/source.py",
            "line": 1,
            "content_hash": SOURCE_HASH,
        },
        TARGET_ID: {
            "id": TARGET_ID,
            "name": "target.py",
            "kind": "file",
            "language": "python",
            "file_path": "src/target.py",
            "line": 1,
            "content_hash": "d" * 64,
        },
    }


def _go_import_edge(**overrides) -> GraphEdge:
    values = {
        "from_id": GO_SOURCE_ID,
        "to_id": GO_TARGET_ID,
        "type": "imports",
        "directed": True,
        "namespace": "loci",
        "resolution": "import-resolved",
        "evidence": GraphEvidence(
            file="cmd/server/main.go",
            line=4,
            content_hash=SOURCE_HASH,
        ),
    }
    values.update(overrides)
    return GraphEdge(**values)


def _go_import_record(**overrides) -> ImportRecord:
    raw_values = {
        "source_file": "cmd/server/main.go",
        "language": "go",
        "line": 4,
        "text": f'import "{GO_IMPORT_PATH}"',
        "specifier": GO_IMPORT_PATH,
        "imported_name": None,
        "type_only": False,
        "is_reexport": False,
        "source_hash": SOURCE_HASH,
    }
    values = {
        "raw": RawImport(**raw_values),
        "source_id": GO_SOURCE_ID,
        "target_file": None,
        "target_package": GO_IMPORT_PATH,
        "target_crate": None,
        "target_kind": "package",
        "target_id": GO_TARGET_ID,
        "status": "resolved",
        "unresolved_reason": None,
    }
    values.update(overrides)
    return ImportRecord(**values)


def _go_import_nodes(**target_overrides) -> dict[str, dict]:
    target = {
        "id": GO_TARGET_ID,
        "name": "store",
        "qualified_name": GO_IMPORT_PATH,
        "kind": "package",
        "language": "go",
        "file_path": "internal/store/store.go",
        "line": 1,
        "content_hash": "d" * 64,
        "metadata": {
            "loci": {
                "go_package_node": True,
                "directory": "internal/store",
                "import_path": GO_IMPORT_PATH,
                "package_name": "store",
            }
        },
    }
    target.update(target_overrides)
    return {
        GO_SOURCE_ID: {
            "id": GO_SOURCE_ID,
            "name": "main.go",
            "qualified_name": "main.go",
            "kind": "file",
            "language": "go",
            "file_path": "cmd/server/main.go",
            "line": 1,
            "content_hash": SOURCE_HASH,
            "metadata": {},
        },
        GO_TARGET_ID: target,
    }


def _rust_import_edge(**overrides) -> GraphEdge:
    values = {
        "from_id": RUST_SOURCE_ID,
        "to_id": RUST_TARGET_ID,
        "type": "imports",
        "directed": True,
        "namespace": "loci",
        "resolution": "import-resolved",
        "evidence": GraphEvidence(
            file="app/src/main.rs",
            line=4,
            content_hash=SOURCE_HASH,
        ),
    }
    values.update(overrides)
    return GraphEdge(**values)


def _rust_import_record(**overrides) -> ImportRecord:
    values = {
        "raw": RawImport(
            source_file="app/src/main.rs",
            language="rust",
            line=4,
            text="use core::Thing;",
            specifier="core::Thing",
            imported_name="Thing",
            type_only=False,
            is_reexport=False,
            source_hash=SOURCE_HASH,
            rust=RustImportContext(
                kind="use",
                lexical_module_path=(),
                visibility="private",
                module_level=True,
                configuration="unconditional",
            ),
        ),
        "source_id": RUST_SOURCE_ID,
        "target_file": None,
        "target_package": None,
        "target_crate": RUST_TARGET_CRATE,
        "target_kind": "crate",
        "target_id": RUST_TARGET_ID,
        "status": "resolved",
        "unresolved_reason": None,
        "resolution_basis": "cargo_path_dependency",
        "resolution_control_files": ("app/Cargo.toml", "core/Cargo.toml"),
        "resolution_configuration": "unconditional",
    }
    values.update(overrides)
    return ImportRecord(**values)


def _rust_import_nodes(
    *,
    target_overrides: dict | None = None,
    metadata_overrides: dict | None = None,
) -> dict[str, dict]:
    target = {
        "id": RUST_TARGET_ID,
        "name": "core",
        "qualified_name": RUST_TARGET_CRATE,
        "kind": "crate",
        "language": "rust",
        "file_path": "core/src/lib.rs",
        "byte_offset": 0,
        "byte_length": 0,
        "signature": RUST_TARGET_CRATE,
        "line": 1,
        "end_line": 1,
        "content_hash": RUST_TARGET_HASH,
        "metadata": {
            "loci": {
                "rust_crate_node": True,
                "manifest": "core/Cargo.toml",
                "package_name": "core-kit",
                "package_root": "core",
                "target_kind": "lib",
                "target_name": "core-kit",
                "crate_name": "core",
                "crate_root": "core/src/lib.rs",
                "edition": "2021",
                "required_features": [],
            }
        },
    }
    target.update(target_overrides or {})
    target["metadata"]["loci"].update(metadata_overrides or {})
    return {
        RUST_SOURCE_ID: {
            "id": RUST_SOURCE_ID,
            "name": "main.rs",
            "qualified_name": "main.rs",
            "kind": "file",
            "language": "rust",
            "file_path": "app/src/main.rs",
            "line": 1,
            "content_hash": SOURCE_HASH,
            "metadata": {},
        },
        RUST_ROOT_ID: {
            "id": RUST_ROOT_ID,
            "name": "lib.rs",
            "qualified_name": "lib.rs",
            "kind": "file",
            "language": "rust",
            "file_path": "core/src/lib.rs",
            "line": 1,
            "content_hash": RUST_TARGET_HASH,
            "metadata": {},
        },
        RUST_TARGET_ID: target,
    }


def test_graph_contract_round_trip_is_stable():
    contribution = GraphContribution(
        schema_version=GRAPH_SCHEMA_VERSION,
        namespace="loci",
        nodes=(
            GraphNodeRef(
                id=PARENT_ID,
                namespace="loci",
                kind="section",
                attributes={"language": "markdown", "line": 1},
            ),
        ),
        edges=(_edge(),),
    )

    serialized = contribution.to_dict()
    restored = GraphContribution.from_dict(serialized)

    assert restored == contribution
    assert serialized["edges"][0]["from"] == PARENT_ID
    assert serialized["edges"][0]["to"] == CHILD_ID
    assert "from_id" not in serialized["edges"][0]


def test_graph_contract_rejects_unknown_schema_version():
    with pytest.raises(GraphContractError) as exc_info:
        GraphContribution.from_dict({
            "schema_version": GRAPH_SCHEMA_VERSION + 1,
            "namespace": "loci",
            "nodes": [],
            "edges": [],
        })

    assert exc_info.value.code == "INVALID_GRAPH_SCHEMA"
    assert exc_info.value.details["schema_version"] == GRAPH_SCHEMA_VERSION + 1


def test_graph_node_rejects_non_finite_attribute():
    with pytest.raises(GraphContractError) as exc_info:
        GraphNodeRef.from_dict({
            "id": PARENT_ID,
            "namespace": "loci",
            "kind": "section",
            "attributes": {"score": float("nan")},
        })

    assert exc_info.value.code == "INVALID_GRAPH_SCHEMA"


def test_graph_contribution_rejects_record_limit():
    node = {
        "id": PARENT_ID,
        "namespace": "loci",
        "kind": "section",
        "attributes": {},
    }
    with pytest.raises(GraphContractError) as exc_info:
        GraphContribution.from_dict({
            "schema_version": GRAPH_SCHEMA_VERSION,
            "namespace": "loci",
            "nodes": [node] * 10_001,
            "edges": [],
        })

    assert exc_info.value.code == "INVALID_GRAPH_SCHEMA"


def test_graph_edge_rejects_unknown_resolution():
    payload = _edge().to_dict()
    payload["resolution"] = "probable"

    with pytest.raises(GraphContractError) as exc_info:
        GraphEdge.from_dict(payload)

    assert exc_info.value.code == "GRAPH_RESOLUTION_UNSUPPORTED"
    assert exc_info.value.details["resolution"] == "probable"


def test_graph_edge_rejects_unknown_type():
    with pytest.raises(GraphContractError) as exc_info:
        validate_graph_edges(
            [_edge(type="calls")],
            indexed_nodes=_indexed_nodes(),
        )

    assert exc_info.value.code == "GRAPH_EDGE_TYPE_UNSUPPORTED"
    assert exc_info.value.details["type"] == "calls"


def test_graph_edge_rejects_missing_endpoint():
    nodes = _indexed_nodes()
    del nodes[CHILD_ID]

    with pytest.raises(GraphContractError) as exc_info:
        validate_graph_edges([_edge()], indexed_nodes=nodes)

    assert exc_info.value.code == "GRAPH_ENDPOINT_NOT_FOUND"
    assert exc_info.value.details["missing_ids"] == [CHILD_ID]


@pytest.mark.parametrize(
    ("evidence", "field"),
    [
        (GraphEvidence(file="../guide.md", line=5, content_hash=CHILD_HASH), "file"),
        (GraphEvidence(file="guide.md", line=0, content_hash=CHILD_HASH), "line"),
        (GraphEvidence(file="guide.md", line=5, content_hash="not-a-hash"), "content_hash"),
    ],
)
def test_graph_edge_rejects_malformed_evidence(evidence: GraphEvidence, field: str):
    with pytest.raises(GraphContractError) as exc_info:
        validate_graph_edges(
            [_edge(evidence=evidence)],
            indexed_nodes=_indexed_nodes(),
        )

    assert exc_info.value.code == "GRAPH_EVIDENCE_INVALID"
    assert exc_info.value.details["field"] == field


def test_contains_evidence_must_identify_child_symbol():
    with pytest.raises(GraphContractError) as exc_info:
        validate_graph_edges(
            [_edge(evidence=GraphEvidence(
                file="guide.md",
                line=6,
                content_hash=CHILD_HASH,
            ))],
            indexed_nodes=_indexed_nodes(),
        )

    assert exc_info.value.code == "GRAPH_EVIDENCE_INVALID"
    assert exc_info.value.details["field"] == "line"


def test_contains_edge_must_be_directed_and_exact():
    with pytest.raises(GraphContractError) as direction_error:
        validate_graph_edges(
            [_edge(directed=False)],
            indexed_nodes=_indexed_nodes(),
        )
    assert direction_error.value.code == "INVALID_GRAPH_EDGE"

    with pytest.raises(GraphContractError) as resolution_error:
        validate_graph_edges(
            [_edge(resolution="declared")],
            indexed_nodes=_indexed_nodes(),
        )
    assert resolution_error.value.code == "GRAPH_RESOLUTION_UNSUPPORTED"


def test_import_edges_accept_runtime_and_type_only_records():
    nodes = _import_nodes()
    file_hashes = {"src/source.py": SOURCE_HASH}

    validate_graph_edges(
        [_import_edge()],
        indexed_nodes=nodes,
        file_hashes=file_hashes,
        imports=[_import_record()],
    )
    validate_graph_edges(
        [_import_edge(type="imports_type")],
        indexed_nodes=nodes,
        file_hashes=file_hashes,
        imports=[_import_record(raw=_raw_import(type_only=True))],
    )


def test_import_edge_accepts_go_package_target():
    validate_graph_edges(
        [_go_import_edge()],
        indexed_nodes=_go_import_nodes(),
        file_hashes={"cmd/server/main.go": SOURCE_HASH},
        imports=[_go_import_record()],
    )


def test_import_edge_accepts_rust_crate_target():
    validate_graph_edges(
        [_rust_import_edge()],
        indexed_nodes=_rust_import_nodes(),
        file_hashes={
            "app/src/main.rs": SOURCE_HASH,
            "core/src/lib.rs": RUST_TARGET_HASH,
        },
        imports=[_rust_import_record()],
    )


@pytest.mark.parametrize(
    ("target_overrides", "metadata_overrides"),
    [
        ({"kind": "file"}, {}),
        ({"language": "go"}, {}),
        ({"name": "wrong"}, {}),
        ({"qualified_name": "core/Cargo.toml::lib:wrong"}, {}),
        ({"file_path": "core/src/other.rs"}, {}),
        ({"byte_offset": 1}, {}),
        ({"byte_length": 1}, {}),
        ({"signature": "wrong"}, {}),
        ({"line": 2}, {}),
        ({"end_line": 2}, {}),
        ({"content_hash": "e" * 64}, {}),
        ({}, {"rust_crate_node": False}),
        ({}, {"manifest": "/core/Cargo.toml"}),
        ({}, {"package_name": ""}),
        ({}, {"package_root": "/core"}),
        ({}, {"package_root": "other"}),
        ({}, {"target_kind": "proc-macro"}),
        ({}, {"target_name": ""}),
        ({}, {"crate_name": "core-kit"}),
        ({}, {"crate_root": "core/src/other.rs"}),
        ({}, {"edition": "2027"}),
        ({}, {"required_features": ["b", "a"]}),
        ({}, {"required_features": ["feature", "feature"]}),
        ({}, {"required_features": [1]}),
    ],
)
def test_import_edge_rejects_invalid_rust_crate_target(
    target_overrides: dict,
    metadata_overrides: dict,
):
    with pytest.raises(GraphContractError) as exc_info:
        validate_graph_edges(
            [_rust_import_edge()],
            indexed_nodes=_rust_import_nodes(
                target_overrides=target_overrides,
                metadata_overrides=metadata_overrides,
            ),
            file_hashes={
                "app/src/main.rs": SOURCE_HASH,
                "core/src/lib.rs": RUST_TARGET_HASH,
            },
            imports=[_rust_import_record()],
        )

    assert exc_info.value.code == "INVALID_GRAPH_EDGE"
    assert exc_info.value.details["field"] == "target"


def test_import_edge_rejects_rust_crate_target_without_indexed_root_file():
    nodes = _rust_import_nodes()
    nodes.pop(RUST_ROOT_ID)

    with pytest.raises(GraphContractError) as exc_info:
        validate_graph_edges(
            [_rust_import_edge()],
            indexed_nodes=nodes,
            file_hashes={
                "app/src/main.rs": SOURCE_HASH,
                "core/src/lib.rs": RUST_TARGET_HASH,
            },
            imports=[_rust_import_record()],
        )

    assert exc_info.value.code == "INVALID_GRAPH_EDGE"
    assert exc_info.value.details["field"] == "target"


@pytest.mark.parametrize(
    ("edge", "record", "field"),
    [
        (
            _rust_import_edge(evidence=GraphEvidence(
                file="app/src/main.rs",
                line=5,
                content_hash=SOURCE_HASH,
            )),
            _rust_import_record(),
            "line",
        ),
        (
            _rust_import_edge(evidence=GraphEvidence(
                file="app/src/main.rs",
                line=4,
                content_hash="e" * 64,
            )),
            _rust_import_record(),
            "content_hash",
        ),
        (
            _rust_import_edge(),
            _rust_import_record(
                target_crate="other/Cargo.toml::lib:other",
                target_id="other/Cargo.toml::lib:other#crate",
            ),
            "import_record",
        ),
    ],
)
def test_rust_crate_import_edge_rejects_mismatched_provenance(
    edge: GraphEdge,
    record: ImportRecord,
    field: str,
):
    with pytest.raises(GraphContractError) as exc_info:
        validate_graph_edges(
            [edge],
            indexed_nodes=_rust_import_nodes(),
            file_hashes={
                "app/src/main.rs": SOURCE_HASH,
                "core/src/lib.rs": RUST_TARGET_HASH,
            },
            imports=[record],
        )

    assert exc_info.value.details["field"] == field


def test_rust_crate_import_edge_rejects_type_only_edge():
    with pytest.raises(GraphContractError) as exc_info:
        validate_graph_edges(
            [_rust_import_edge(type="imports_type")],
            indexed_nodes=_rust_import_nodes(),
            file_hashes={
                "app/src/main.rs": SOURCE_HASH,
                "core/src/lib.rs": RUST_TARGET_HASH,
            },
            imports=[_rust_import_record()],
        )

    assert exc_info.value.code == "INVALID_GRAPH_EDGE"
    assert exc_info.value.details["field"] == "type"


def test_rust_crate_import_edge_rejects_own_root_file_self_edge():
    own_source_id = "core/src/lib.rs::__file__#file"
    nodes = _rust_import_nodes()
    nodes.pop(RUST_SOURCE_ID)
    raw = RawImport(
        source_file="core/src/lib.rs",
        language="rust",
        line=4,
        text="use crate::Thing;",
        specifier="crate::Thing",
        imported_name="Thing",
        type_only=False,
        is_reexport=False,
        source_hash=RUST_TARGET_HASH,
        rust=RustImportContext(
            kind="use",
            lexical_module_path=(),
            visibility="private",
            module_level=True,
            configuration="unconditional",
        ),
    )

    with pytest.raises(GraphContractError) as exc_info:
        validate_graph_edges(
            [_rust_import_edge(
                from_id=own_source_id,
                evidence=GraphEvidence(
                    file="core/src/lib.rs",
                    line=4,
                    content_hash=RUST_TARGET_HASH,
                ),
            )],
            indexed_nodes=nodes,
            file_hashes={"core/src/lib.rs": RUST_TARGET_HASH},
            imports=[_rust_import_record(
                raw=raw,
                source_id=own_source_id,
                resolution_basis="rust_module_path",
                resolution_control_files=("core/Cargo.toml",),
            )],
        )

    assert exc_info.value.code == "INVALID_GRAPH_EDGE"
    assert exc_info.value.details["field"] == "endpoints"


@pytest.mark.parametrize(
    ("target_overrides", "metadata_overrides"),
    [
        ({"kind": "file"}, {}),
        ({"language": "python"}, {}),
        ({"name": "wrong"}, {}),
        ({"qualified_name": "example.com/project/wrong"}, {}),
        ({}, {"go_package_node": False}),
        ({}, {"import_path": "example.com/project/wrong"}),
        ({}, {"package_name": "main"}),
        ({}, {"package_name": "123invalid"}),
    ],
)
def test_import_edge_rejects_invalid_go_package_target(
    target_overrides: dict,
    metadata_overrides: dict,
):
    nodes = _go_import_nodes(**target_overrides)
    nodes[GO_TARGET_ID]["metadata"]["loci"].update(metadata_overrides)

    with pytest.raises(GraphContractError) as exc_info:
        validate_graph_edges(
            [_go_import_edge()],
            indexed_nodes=nodes,
            file_hashes={"cmd/server/main.go": SOURCE_HASH},
            imports=[_go_import_record()],
        )

    assert exc_info.value.code == "INVALID_GRAPH_EDGE"
    assert exc_info.value.details["field"] == "target"


@pytest.mark.parametrize(
    ("edge", "record", "field"),
    [
        (
            _go_import_edge(evidence=GraphEvidence(
                file="cmd/server/main.go",
                line=5,
                content_hash=SOURCE_HASH,
            )),
            _go_import_record(),
            "line",
        ),
        (
            _go_import_edge(evidence=GraphEvidence(
                file="cmd/server/main.go",
                line=4,
                content_hash="e" * 64,
            )),
            _go_import_record(),
            "content_hash",
        ),
        (
            _go_import_edge(),
            _go_import_record(target_id="other#package"),
            "import_record",
        ),
        (
            _go_import_edge(),
            _go_import_record(target_package="example.com/project/wrong"),
            "target",
        ),
    ],
)
def test_go_package_import_edge_rejects_mismatched_provenance(
    edge: GraphEdge,
    record: ImportRecord,
    field: str,
):
    with pytest.raises(GraphContractError) as exc_info:
        validate_graph_edges(
            [edge],
            indexed_nodes=_go_import_nodes(),
            file_hashes={"cmd/server/main.go": SOURCE_HASH},
            imports=[record],
        )

    assert exc_info.value.details["field"] == field


def test_go_package_import_edge_rejects_type_only_edge():
    with pytest.raises(GraphContractError) as exc_info:
        validate_graph_edges(
            [_go_import_edge(type="imports_type")],
            indexed_nodes=_go_import_nodes(),
            file_hashes={"cmd/server/main.go": SOURCE_HASH},
            imports=[_go_import_record()],
        )

    assert exc_info.value.code == "INVALID_GRAPH_EDGE"
    assert exc_info.value.details["field"] == "type"


@pytest.mark.parametrize(
    ("edge", "code", "field"),
    [
        (_import_edge(directed=False), "INVALID_GRAPH_EDGE", "directed"),
        (
            _import_edge(resolution="exact"),
            "GRAPH_RESOLUTION_UNSUPPORTED",
            None,
        ),
        (
            _import_edge(evidence=GraphEvidence(
                file="src/target.py",
                line=3,
                content_hash=SOURCE_HASH,
            )),
            "GRAPH_EVIDENCE_INVALID",
            "file",
        ),
        (
            _import_edge(evidence=GraphEvidence(
                file="src/source.py",
                line=4,
                content_hash=SOURCE_HASH,
            )),
            "GRAPH_EVIDENCE_INVALID",
            "line",
        ),
        (
            _import_edge(evidence=GraphEvidence(
                file="src/source.py",
                line=3,
                content_hash="e" * 64,
            )),
            "GRAPH_EVIDENCE_INVALID",
            "content_hash",
        ),
    ],
)
def test_import_edge_rejects_corrupt_contract_fields(
    edge: GraphEdge,
    code: str,
    field: str | None,
):
    with pytest.raises(GraphContractError) as exc_info:
        validate_graph_edges(
            [edge],
            indexed_nodes=_import_nodes(),
            file_hashes={"src/source.py": SOURCE_HASH},
            imports=[_import_record()],
        )

    assert exc_info.value.code == code
    if field is not None:
        assert exc_info.value.details["field"] == field
    else:
        assert exc_info.value.details["resolution"] == "exact"


def test_import_edge_rejects_non_file_endpoint_even_with_same_name():
    symbol_id = "src/target.py::target#function"
    nodes = _import_nodes()
    nodes[symbol_id] = {
        "id": symbol_id,
        "name": "target.py",
        "kind": "function",
        "language": "python",
        "file_path": "src/target.py",
        "line": 1,
        "content_hash": "d" * 64,
    }

    with pytest.raises(GraphContractError) as exc_info:
        validate_graph_edges(
            [_import_edge(to_id=symbol_id)],
            indexed_nodes=nodes,
            file_hashes={"src/source.py": SOURCE_HASH},
            imports=[_import_record(target_id=symbol_id)],
        )

    assert exc_info.value.code == "INVALID_GRAPH_EDGE"
    assert exc_info.value.details["field"] == "endpoints"


def test_import_edge_rejects_same_named_file_that_is_not_the_record_target():
    wrong_target_id = "src/other/target.py::__file__#file"
    nodes = _import_nodes()
    nodes[wrong_target_id] = {
        "id": wrong_target_id,
        "name": "target.py",
        "kind": "file",
        "language": "python",
        "file_path": "src/other/target.py",
        "line": 1,
        "content_hash": "e" * 64,
    }

    with pytest.raises(GraphContractError) as exc_info:
        validate_graph_edges(
            [_import_edge(to_id=wrong_target_id)],
            indexed_nodes=nodes,
            file_hashes={"src/source.py": SOURCE_HASH},
            imports=[_import_record()],
        )

    assert exc_info.value.code == "GRAPH_EVIDENCE_INVALID"
    assert exc_info.value.details["field"] == "import_record"


def test_reserved_import_type_requires_loci_namespace():
    with pytest.raises(GraphContractError) as exc_info:
        validate_graph_edges(
            [_import_edge(namespace="llm-wiki")],
            indexed_nodes=_import_nodes(),
            file_hashes={"src/source.py": SOURCE_HASH},
            imports=[_import_record()],
        )

    assert exc_info.value.code == "GRAPH_EDGE_TYPE_UNSUPPORTED"
    assert exc_info.value.details["namespace"] == "llm-wiki"


def test_import_edge_requires_matching_resolved_record():
    with pytest.raises(GraphContractError) as exc_info:
        validate_graph_edges(
            [_import_edge()],
            indexed_nodes=_import_nodes(),
            file_hashes={"src/source.py": SOURCE_HASH},
            imports=[_import_record(target_id="src/other.py::__file__#file")],
        )

    assert exc_info.value.code == "GRAPH_EVIDENCE_INVALID"
    assert exc_info.value.details["field"] == "import_record"
