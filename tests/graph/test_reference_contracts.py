from __future__ import annotations

from dataclasses import replace

import pytest

from loci.graph.contracts import (
    GraphContractError,
    GraphEdge,
    GraphEvidence,
    validate_graph_edges,
)
from loci.graph.imports import ImportRecord
from loci.graph.references import (
    MAX_REFERENCE_SUPPORT_RECORDS,
    ReferenceSupport,
    SymbolReferenceRecord,
    materialize_reference_edges,
    validate_symbol_reference_records,
)
from loci.parser.imports import RawImport
from loci.parser.reference_models import (
    ImportBinding,
    RawLocalExport,
    RawSymbolReference,
)


SOURCE_HASH = "a" * 64
TARGET_HASH = "b" * 64
SOURCE_ID = "src/use.py::run#function"
IMPORT_SOURCE_ID = "src/use.py::__file__#file"
IMPORT_TARGET_ID = "src/model.py::__file__#file"
TARGET_ID = "src/model.py::Thing#class"


def _binding(**overrides) -> ImportBinding:
    values = {
        "local_name": "Alias",
        "imported_name": "Thing",
        "exported_name": None,
        "kind": "symbol",
        "type_only": False,
        "module_level": True,
        "declaration_start_byte": 0,
        "scope_start_byte": 0,
        "scope_end_byte": 200,
        "import_line": 1,
        "import_text": "from .model import Thing as Alias",
        "import_specifier": ".model",
    }
    values.update(overrides)
    return ImportBinding(**values)


def _raw_reference(**overrides) -> RawSymbolReference:
    values = {
        "source_file": "src/use.py",
        "language": "python",
        "line": 5,
        "column": 12,
        "start_byte": 80,
        "end_byte": 85,
        "text": "Alias",
        "path": ("Alias",),
        "candidate_bindings": (_binding(),),
        "binding_state": "definite",
        "source_hash": SOURCE_HASH,
    }
    values.update(overrides)
    return RawSymbolReference(**values)


def _support(**overrides) -> ReferenceSupport:
    values = {
        "kind": "definition",
        "file": "src/model.py",
        "line": 3,
        "content_hash": TARGET_HASH,
        "endpoint_id": TARGET_ID,
    }
    values.update(overrides)
    return ReferenceSupport(**values)


def _import_support(**overrides) -> ReferenceSupport:
    values = {
        "kind": "import_binding",
        "file": "src/use.py",
        "line": 1,
        "content_hash": SOURCE_HASH,
        "endpoint_id": IMPORT_TARGET_ID,
    }
    values.update(overrides)
    return ReferenceSupport(**values)


def _resolved_record(**overrides) -> SymbolReferenceRecord:
    raw = overrides.pop("raw", _raw_reference())
    values = {
        "raw": raw,
        "binding": raw.candidate_bindings[0],
        "source_id": SOURCE_ID,
        "source_kind": "function",
        "import_source_id": IMPORT_SOURCE_ID,
        "import_target_id": IMPORT_TARGET_ID,
        "target_file": "src/model.py",
        "target_id": TARGET_ID,
        "target_kind": "class",
        "status": "resolved",
        "unresolved_reason": None,
        "import_unresolved_reason": None,
        "resolution_basis": "direct_binding",
        "support": (_import_support(), _support()),
        "resolution_control_files": (),
        "resolution_configuration": None,
    }
    values.update(overrides)
    return SymbolReferenceRecord(**values)


def _unresolved_record(**overrides) -> SymbolReferenceRecord:
    raw = overrides.pop("raw", _raw_reference())
    values = {
        "raw": raw,
        "binding": raw.candidate_bindings[0],
        "source_id": SOURCE_ID,
        "source_kind": "function",
        "import_source_id": IMPORT_SOURCE_ID,
        "import_target_id": IMPORT_TARGET_ID,
        "target_file": None,
        "target_id": None,
        "target_kind": None,
        "status": "unresolved",
        "unresolved_reason": "target_not_indexed",
        "import_unresolved_reason": None,
        "resolution_basis": None,
        "support": (),
        "resolution_control_files": (),
        "resolution_configuration": None,
    }
    values.update(overrides)
    return SymbolReferenceRecord(**values)


def _raw_import(**overrides) -> RawImport:
    values = {
        "source_file": "src/use.py",
        "language": "python",
        "line": 1,
        "text": "from .model import Thing as Alias",
        "specifier": ".model",
        "imported_name": "Thing",
        "type_only": False,
        "is_reexport": False,
        "source_hash": SOURCE_HASH,
        "bindings": (_binding(),),
        "rust": None,
    }
    values.update(overrides)
    return RawImport(**values)


def _import_record(**overrides) -> ImportRecord:
    values = {
        "raw": _raw_import(),
        "source_id": IMPORT_SOURCE_ID,
        "target_file": "src/model.py",
        "target_package": None,
        "target_crate": None,
        "target_kind": "file",
        "target_id": IMPORT_TARGET_ID,
        "status": "resolved",
        "unresolved_reason": None,
    }
    values.update(overrides)
    return ImportRecord(**values)


def _definition_export(**overrides) -> RawLocalExport:
    values = {
        "source_file": "src/model.py",
        "language": "python",
        "line": 3,
        "text": "class Thing:",
        "local_name": "Thing",
        "exported_name": "Thing",
        "type_only": False,
        "definition_start_byte": 10,
        "definition_end_byte": 40,
        "source_hash": TARGET_HASH,
    }
    values.update(overrides)
    return RawLocalExport(**values)


def _indexed_nodes() -> dict[str, dict]:
    return {
        IMPORT_SOURCE_ID: {
            "id": IMPORT_SOURCE_ID,
            "kind": "file",
            "language": "python",
            "file_path": "src/use.py",
            "byte_offset": 0,
            "byte_length": 0,
            "content_hash": SOURCE_HASH,
            "line": 1,
            "metadata": {"loci": {"file_node": True}},
        },
        SOURCE_ID: {
            "id": SOURCE_ID,
            "kind": "function",
            "language": "python",
            "file_path": "src/use.py",
            "byte_offset": 50,
            "byte_length": 100,
            "content_hash": SOURCE_HASH,
            "line": 4,
            "metadata": {},
        },
        IMPORT_TARGET_ID: {
            "id": IMPORT_TARGET_ID,
            "kind": "file",
            "language": "python",
            "file_path": "src/model.py",
            "byte_offset": 0,
            "byte_length": 0,
            "content_hash": TARGET_HASH,
            "line": 1,
            "metadata": {"loci": {"file_node": True}},
        },
        TARGET_ID: {
            "id": TARGET_ID,
            "kind": "class",
            "language": "python",
            "file_path": "src/model.py",
            "byte_offset": 10,
            "byte_length": 30,
            "content_hash": TARGET_HASH,
            "line": 3,
            "metadata": {},
        },
    }


def _validate_records(*records: SymbolReferenceRecord) -> None:
    validate_symbol_reference_records(
        records,
        imports=[_import_record()],
        exports=[_definition_export()],
        indexed_nodes=_indexed_nodes(),
        file_hashes={"src/use.py": SOURCE_HASH, "src/model.py": TARGET_HASH},
    )


def test_unsupported_reference_does_not_claim_unresolved_import_outcome():
    raw = _raw_reference(binding_state="unsupported", text="Alias[str]")
    record = _unresolved_record(
        raw=raw,
        import_target_id=None,
        unresolved_reason="unsupported_reference",
    )
    unresolved_import = _import_record(
        target_file=None,
        target_kind=None,
        target_id=None,
        status="unresolved",
        unresolved_reason="not_indexed",
    )

    validate_symbol_reference_records(
        [record],
        imports=[unresolved_import],
        exports=[_definition_export()],
        indexed_nodes=_indexed_nodes(),
        file_hashes={"src/use.py": SOURCE_HASH, "src/model.py": TARGET_HASH},
    )


@pytest.mark.parametrize("record", [_support(), _resolved_record(), _unresolved_record()])
def test_reference_graph_records_round_trip_strictly(record):
    serialized = record.to_dict()

    assert type(record).from_dict(serialized) == record

    missing = dict(serialized)
    missing.pop(next(iter(missing)))
    with pytest.raises(GraphContractError, match="fields"):
        type(record).from_dict(missing)

    unknown = dict(serialized)
    unknown["unknown"] = True
    with pytest.raises(GraphContractError, match="fields"):
        type(record).from_dict(unknown)


@pytest.mark.parametrize(
    "overrides",
    [
        {"kind": "guess"},
        {"file": "/tmp/model.py"},
        {"file": "src/../model.py"},
        {"line": 0},
        {"content_hash": "not-a-hash"},
        {"endpoint_id": ""},
    ],
)
def test_reference_support_rejects_malformed_fields(overrides):
    with pytest.raises(GraphContractError):
        _support(**overrides)


@pytest.mark.parametrize(
    "overrides",
    [
        {"binding": None},
        {"target_file": None},
        {"target_id": None},
        {"target_kind": None},
        {"unresolved_reason": "target_not_indexed"},
        {"resolution_basis": None},
        {"support": ()},
        {"import_unresolved_reason": "external"},
        {"resolution_configuration": "unconditional"},
    ],
)
def test_resolved_reference_record_rejects_impossible_states(overrides):
    with pytest.raises(GraphContractError):
        _resolved_record(**overrides)


@pytest.mark.parametrize(
    "overrides",
    [
        {"unresolved_reason": None},
        {"target_file": "src/model.py"},
        {"target_id": TARGET_ID},
        {"target_kind": "class"},
        {"resolution_basis": "direct_binding"},
        {"import_unresolved_reason": "external"},
        {"resolution_control_files": ["pyproject.toml"]},
    ],
)
def test_unresolved_reference_record_rejects_impossible_states(overrides):
    with pytest.raises(GraphContractError):
        _unresolved_record(**overrides)


def test_reference_record_requires_binding_snapshot_from_raw_observation():
    with pytest.raises(GraphContractError, match="candidate"):
        _resolved_record(binding=replace(_binding(), imported_name="Other"))


def test_reference_record_accepts_explicit_ambiguous_source_outcome():
    record = _unresolved_record(
        source_id=IMPORT_SOURCE_ID,
        source_kind="file",
        unresolved_reason="ambiguous_source",
    )

    assert record.unresolved_reason == "ambiguous_source"


def test_unresolved_reference_may_omit_binding_when_no_candidate_is_selected():
    first = _binding()
    second = replace(
        first,
        imported_name="OtherThing",
        import_text="from .other import OtherThing as Alias",
        import_specifier=".other",
    )
    raw = _raw_reference(
        candidate_bindings=(first, second),
        binding_state="unsupported",
    )

    record = _unresolved_record(
        raw=raw,
        binding=None,
        unresolved_reason="unsupported_reference",
    )

    assert record.binding is None


def test_reference_record_enforces_support_bound_atomically():
    with pytest.raises(GraphContractError, match="support"):
        _resolved_record(
            support=(_support(),) * (MAX_REFERENCE_SUPPORT_RECORDS + 1),
        )


def test_reference_records_validate_against_current_import_export_and_nodes():
    record = _resolved_record()

    _validate_records(record, _unresolved_record())
    edge = materialize_reference_edges([record])[0]
    validate_graph_edges(
        [edge],
        indexed_nodes=_indexed_nodes(),
        file_hashes={"src/use.py": SOURCE_HASH, "src/model.py": TARGET_HASH},
        imports=[_import_record()],
        symbol_references=[record],
    )


def test_reference_edge_materialization_deduplicates_by_earliest_evidence():
    later_binding = _binding(import_line=2, import_text="from .model import Thing as Alias")
    later_raw = _raw_reference(
        line=6,
        column=4,
        start_byte=100,
        end_byte=105,
        candidate_bindings=(later_binding,),
    )
    later = _resolved_record(
        raw=later_raw,
        binding=later_binding,
        support=(
            _import_support(line=2),
            _support(),
        ),
    )
    first = _resolved_record()

    edges = materialize_reference_edges([
        later,
        _unresolved_record(),
        first,
    ])

    assert edges == [GraphEdge(
        from_id=SOURCE_ID,
        to_id=TARGET_ID,
        type="references",
        directed=True,
        namespace="loci",
        resolution="import-resolved",
        evidence=GraphEvidence(
            file="src/use.py",
            line=5,
            content_hash=SOURCE_HASH,
        ),
    )]


def test_reference_edge_materialization_preserves_explicit_type_only_binding():
    binding = _binding(type_only=True)
    raw = _raw_reference(candidate_bindings=(binding,))
    record = _resolved_record(raw=raw, binding=binding)

    assert materialize_reference_edges([record])[0].type == "references_type"


@pytest.mark.parametrize(
    "record",
    [
        _resolved_record(source_id=IMPORT_SOURCE_ID, source_kind="file"),
        _resolved_record(import_target_id="src/other.py::__file__#file"),
        _resolved_record(target_kind="function"),
        _resolved_record(
            support=(
                _import_support(),
                _support(content_hash="c" * 64),
            ),
        ),
    ],
)
def test_reference_record_cross_validation_rejects_stale_or_mismatched_evidence(
    record: SymbolReferenceRecord,
):
    with pytest.raises(GraphContractError):
        _validate_records(record)


def test_reference_record_cross_validation_rejects_stale_source_hash():
    with pytest.raises(GraphContractError, match="stale"):
        validate_symbol_reference_records(
            [_resolved_record()],
            imports=[_import_record()],
            exports=[_definition_export()],
            indexed_nodes=_indexed_nodes(),
            file_hashes={"src/use.py": "c" * 64, "src/model.py": TARGET_HASH},
        )


@pytest.mark.parametrize(
    "support",
    [
        (_support(),),
        (
            _import_support(),
            _support(endpoint_id="src/model.py::Other#class"),
        ),
        (
            _import_support(),
            ReferenceSupport(
                kind="reexport",
                file="src/model.py",
                line=2,
                content_hash=TARGET_HASH,
                endpoint_id=IMPORT_TARGET_ID,
            ),
            _support(),
        ),
    ],
)
def test_reference_record_rejects_incomplete_or_unbacked_support(
    support: tuple[ReferenceSupport, ...],
):
    with pytest.raises(GraphContractError):
        _validate_records(_resolved_record(support=support))


def test_reference_record_accepts_current_named_reexport_support_chain():
    barrel_hash = "d" * 64
    barrel_id = "src/barrel.py::__file__#file"
    nodes = _indexed_nodes()
    nodes[barrel_id] = {
        "id": barrel_id,
        "kind": "file",
        "language": "python",
        "file_path": "src/barrel.py",
        "byte_offset": 0,
        "byte_length": 0,
        "content_hash": barrel_hash,
        "line": 1,
        "metadata": {"loci": {"file_node": True}},
    }
    direct_import = _import_record(
        target_file="src/barrel.py",
        target_id=barrel_id,
    )
    reexport_binding = _binding(
        local_name="Thing",
        exported_name="Thing",
        import_line=1,
        import_text="from .model import Thing",
        import_specifier=".model",
    )
    reexport_import = _import_record(
        raw=_raw_import(
            source_file="src/barrel.py",
            line=1,
            text="from .model import Thing",
            is_reexport=True,
            source_hash=barrel_hash,
            bindings=(reexport_binding,),
        ),
        source_id=barrel_id,
    )
    record = _resolved_record(
        import_target_id=barrel_id,
        resolution_basis="reexport_chain",
        support=(
            _import_support(endpoint_id=barrel_id),
            ReferenceSupport(
                kind="reexport",
                file="src/barrel.py",
                line=1,
                content_hash=barrel_hash,
                endpoint_id=IMPORT_TARGET_ID,
            ),
            _support(),
        ),
    )

    validate_symbol_reference_records(
        [record],
        imports=[direct_import, reexport_import],
        exports=[_definition_export()],
        indexed_nodes=nodes,
        file_hashes={
            "src/use.py": SOURCE_HASH,
            "src/barrel.py": barrel_hash,
            "src/model.py": TARGET_HASH,
        },
    )


def test_reference_record_requires_exact_downstream_reexport_failure_support():
    barrel_hash = "d" * 64
    barrel_id = "src/barrel.py::__file__#file"
    nodes = _indexed_nodes()
    nodes[barrel_id] = {
        "id": barrel_id,
        "kind": "file",
        "language": "python",
        "file_path": "src/barrel.py",
        "byte_offset": 0,
        "byte_length": 0,
        "content_hash": barrel_hash,
        "line": 1,
        "metadata": {"loci": {"file_node": True}},
    }
    direct_import = _import_record(
        target_file="src/barrel.py",
        target_id=barrel_id,
    )
    reexport_binding = _binding(
        local_name="Thing",
        exported_name="Thing",
        import_line=1,
        import_text="from external import Thing",
        import_specifier="external",
    )
    failed_reexport = _import_record(
        raw=_raw_import(
            source_file="src/barrel.py",
            line=1,
            text="from external import Thing",
            specifier="external",
            is_reexport=True,
            source_hash=barrel_hash,
            bindings=(reexport_binding,),
        ),
        source_id=barrel_id,
        target_file=None,
        target_kind=None,
        target_id=None,
        status="unresolved",
        unresolved_reason="external",
    )
    import_support = _import_support(endpoint_id=barrel_id)
    failure_support = ReferenceSupport(
        kind="reexport",
        file="src/barrel.py",
        line=1,
        content_hash=barrel_hash,
        endpoint_id=barrel_id,
    )
    record = _unresolved_record(
        import_target_id=barrel_id,
        unresolved_reason="import_unresolved",
        import_unresolved_reason="external",
        support=(import_support, failure_support),
    )
    evidence = {
        "imports": [direct_import, failed_reexport],
        "exports": [],
        "indexed_nodes": nodes,
        "file_hashes": {
            "src/use.py": SOURCE_HASH,
            "src/barrel.py": barrel_hash,
            "src/model.py": TARGET_HASH,
        },
    }

    validate_symbol_reference_records([record], **evidence)
    with pytest.raises(GraphContractError, match="direct or downstream failure"):
        validate_symbol_reference_records(
            [replace(record, support=(import_support,))],
            **evidence,
        )


def test_unresolved_reference_record_cannot_back_a_reference_edge():
    record = _unresolved_record()
    edge = GraphEdge(
        from_id=SOURCE_ID,
        to_id=TARGET_ID,
        type="references",
        directed=True,
        namespace="loci",
        resolution="import-resolved",
        evidence=GraphEvidence(
            file="src/use.py",
            line=5,
            content_hash=SOURCE_HASH,
        ),
    )

    assert materialize_reference_edges([record]) == []
    with pytest.raises(GraphContractError) as exc_info:
        validate_graph_edges(
            [edge],
            indexed_nodes=_indexed_nodes(),
            file_hashes={"src/use.py": SOURCE_HASH, "src/model.py": TARGET_HASH},
            imports=[_import_record()],
            symbol_references=[record],
        )

    assert exc_info.value.code == "GRAPH_EVIDENCE_INVALID"
    assert exc_info.value.details["field"] == "reference_record"


def test_reference_edge_requires_explicit_type_only_match():
    record = _resolved_record()
    edge = replace(materialize_reference_edges([record])[0], type="references_type")

    with pytest.raises(GraphContractError) as exc_info:
        validate_graph_edges(
            [edge],
            indexed_nodes=_indexed_nodes(),
            file_hashes={"src/use.py": SOURCE_HASH, "src/model.py": TARGET_HASH},
            symbol_references=[record],
        )

    assert exc_info.value.code == "GRAPH_EVIDENCE_INVALID"
    assert exc_info.value.details["field"] == "reference_record"


def test_reserved_reference_type_requires_loci_namespace():
    record = _resolved_record()
    edge = replace(materialize_reference_edges([record])[0], namespace="example")

    with pytest.raises(GraphContractError) as exc_info:
        validate_graph_edges(
            [edge],
            indexed_nodes=_indexed_nodes(),
            file_hashes={"src/use.py": SOURCE_HASH, "src/model.py": TARGET_HASH},
            symbol_references=[record],
        )

    assert exc_info.value.code == "GRAPH_EDGE_TYPE_UNSUPPORTED"
    assert exc_info.value.details["namespace"] == "example"


@pytest.mark.parametrize(
    "edge",
    [
        replace(materialize_reference_edges([_resolved_record()])[0], directed=False),
        replace(
            materialize_reference_edges([_resolved_record()])[0],
            resolution="declared",
        ),
        replace(
            materialize_reference_edges([_resolved_record()])[0],
            to_id=IMPORT_TARGET_ID,
        ),
        replace(
            materialize_reference_edges([_resolved_record()])[0],
            evidence=GraphEvidence(
                file="src/use.py",
                line=6,
                content_hash=SOURCE_HASH,
            ),
        ),
        replace(
            materialize_reference_edges([_resolved_record()])[0],
            evidence=GraphEvidence(
                file="src/use.py",
                line=5,
                content_hash="c" * 64,
            ),
        ),
    ],
)
def test_reference_edge_rejects_invalid_contract_fields(edge: GraphEdge):
    with pytest.raises(GraphContractError):
        validate_graph_edges(
            [edge],
            indexed_nodes=_indexed_nodes(),
            file_hashes={"src/use.py": SOURCE_HASH, "src/model.py": TARGET_HASH},
            symbol_references=[_resolved_record()],
        )
