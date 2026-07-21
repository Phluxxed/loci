from __future__ import annotations

from dataclasses import replace

import pytest

from loci.graph.calls import (
    CallRecord,
    CallSupport,
    materialize_call_edges,
    validate_call_records,
)
from loci.graph.contracts import (
    GraphContractError,
    GraphEdge,
    GraphEvidence,
    validate_graph_edges,
)
from loci.graph.references import ReferenceSupport, SymbolReferenceRecord
from loci.parser._binding_context import ExecutableOwner
from loci.parser.call_models import LocalCallableBinding, RawCallSite
from loci.parser.reference_models import ImportBinding, RawSymbolReference


SOURCE_FILE = "src/use.py"
TARGET_FILE = "src/target.py"
SOURCE_HASH = "a" * 64
TARGET_FILE_HASH = "b" * 64
CALLER_HASH = "c" * 64
TARGET_HASH = "d" * 64
FILE_ID = f"{SOURCE_FILE}::__file__#file"
CALLER_ID = f"{SOURCE_FILE}::caller#function"
LOCAL_TARGET_ID = f"{SOURCE_FILE}::target#function"
IMPORTED_TARGET_ID = f"{TARGET_FILE}::target#function"


def _binding(**overrides) -> LocalCallableBinding:
    values = {
        "name": "target",
        "callable_kind": "function",
        "definition_start_byte": 0,
        "definition_end_byte": 20,
        "definition_line": 1,
        "scope_start_byte": 0,
        "scope_end_byte": 200,
    }
    values.update(overrides)
    return LocalCallableBinding(**values)


def _owner() -> ExecutableOwner:
    return ExecutableOwner(
        kind="callable",
        definition_start_byte=30,
        definition_end_byte=100,
        body_start_byte=45,
        body_end_byte=100,
    )


def _raw_call(**overrides) -> RawCallSite:
    values = {
        "source_file": SOURCE_FILE,
        "language": "python",
        "line": 4,
        "column": 12,
        "start_byte": 60,
        "end_byte": 68,
        "callee_start_byte": 60,
        "callee_end_byte": 66,
        "callee_text": "target",
        "callee_path": ("target",),
        "callee_form": "identifier",
        "local_candidates": (_binding(),),
        "local_binding_state": "definite",
        "owner": _owner(),
        "source_hash": SOURCE_HASH,
    }
    values.update(overrides)
    return RawCallSite(**values)


def _call_support(**overrides) -> CallSupport:
    values = {
        "kind": "call_site",
        "file": SOURCE_FILE,
        "line": 4,
        "content_hash": SOURCE_HASH,
        "endpoint_id": CALLER_ID,
    }
    values.update(overrides)
    return CallSupport(**values)


def _resolved_local(**overrides) -> CallRecord:
    values = {
        "raw": _raw_call(),
        "caller_id": CALLER_ID,
        "caller_kind": "function",
        "target_file": SOURCE_FILE,
        "target_id": LOCAL_TARGET_ID,
        "target_kind": "function",
        "status": "resolved",
        "resolution": "exact",
        "unresolved_reason": None,
        "reference_unresolved_reason": None,
        "resolution_basis": "local_callable",
        "support": (
            _call_support(),
            _call_support(
                kind="caller_definition",
                line=3,
                content_hash=CALLER_HASH,
            ),
            _call_support(
                kind="local_definition",
                line=1,
                content_hash=TARGET_HASH,
                endpoint_id=LOCAL_TARGET_ID,
            ),
        ),
        "resolution_control_files": (),
        "resolution_configuration": None,
    }
    values.update(overrides)
    return CallRecord(**values)


def _unresolved(**overrides) -> CallRecord:
    values = {
        "raw": _raw_call(local_candidates=(), local_binding_state="absent"),
        "caller_id": CALLER_ID,
        "caller_kind": "function",
        "target_file": None,
        "target_id": None,
        "target_kind": None,
        "status": "unresolved",
        "resolution": None,
        "unresolved_reason": "callee_not_proven",
        "reference_unresolved_reason": None,
        "resolution_basis": None,
        "support": (),
        "resolution_control_files": (),
        "resolution_configuration": None,
    }
    values.update(overrides)
    return CallRecord(**values)


def _import_binding() -> ImportBinding:
    return ImportBinding(
        local_name="target",
        imported_name="target",
        exported_name=None,
        kind="symbol",
        type_only=False,
        module_level=True,
        declaration_start_byte=0,
        scope_start_byte=0,
        scope_end_byte=200,
        import_line=1,
        import_text="from .target import target",
        import_specifier=".target",
    )


def _reference(**overrides) -> SymbolReferenceRecord:
    binding = _import_binding()
    raw = RawSymbolReference(
        source_file=SOURCE_FILE,
        language="python",
        line=4,
        column=12,
        start_byte=60,
        end_byte=66,
        text="target",
        path=("target",),
        candidate_bindings=(binding,),
        binding_state="definite",
        source_hash=SOURCE_HASH,
    )
    values = {
        "raw": raw,
        "binding": binding,
        "source_id": CALLER_ID,
        "source_kind": "function",
        "import_source_id": FILE_ID,
        "import_target_id": f"{TARGET_FILE}::__file__#file",
        "target_file": TARGET_FILE,
        "target_id": IMPORTED_TARGET_ID,
        "target_kind": "function",
        "status": "resolved",
        "unresolved_reason": None,
        "import_unresolved_reason": None,
        "resolution_basis": "direct_binding",
        "support": (
            ReferenceSupport(
                kind="import_binding",
                file=SOURCE_FILE,
                line=1,
                content_hash=SOURCE_HASH,
                endpoint_id=f"{TARGET_FILE}::__file__#file",
            ),
            ReferenceSupport(
                kind="definition",
                file=TARGET_FILE,
                line=1,
                content_hash=TARGET_FILE_HASH,
                endpoint_id=IMPORTED_TARGET_ID,
            ),
        ),
        "resolution_control_files": (),
        "resolution_configuration": None,
    }
    values.update(overrides)
    return SymbolReferenceRecord(**values)


def _resolved_import(**overrides) -> CallRecord:
    raw = _raw_call(local_candidates=(), local_binding_state="absent")
    values = {
        "raw": raw,
        "caller_id": CALLER_ID,
        "caller_kind": "function",
        "target_file": TARGET_FILE,
        "target_id": IMPORTED_TARGET_ID,
        "target_kind": "function",
        "status": "resolved",
        "resolution": "import-resolved",
        "unresolved_reason": None,
        "reference_unresolved_reason": None,
        "resolution_basis": "imported_reference",
        "support": (
            _call_support(),
            _call_support(
                kind="caller_definition",
                line=3,
                content_hash=CALLER_HASH,
            ),
            _call_support(
                kind="symbol_reference",
                endpoint_id=IMPORTED_TARGET_ID,
            ),
        ),
        "resolution_control_files": (),
        "resolution_configuration": None,
    }
    values.update(overrides)
    return CallRecord(**values)


def _node(
    node_id: str,
    *,
    file: str,
    kind: str,
    line: int,
    content_hash: str,
    byte_offset: int,
    byte_length: int,
) -> dict:
    return {
        "id": node_id,
        "name": node_id.rsplit("::", 1)[-1].split("#", 1)[0],
        "qualified_name": node_id.rsplit("::", 1)[-1].split("#", 1)[0],
        "kind": kind,
        "language": "python",
        "file_path": file,
        "line": line,
        "byte_offset": byte_offset,
        "byte_length": byte_length,
        "content_hash": content_hash,
        "metadata": {"loci": {"file_node": True}} if kind == "file" else {},
    }


def _nodes() -> dict[str, dict]:
    return {
        FILE_ID: _node(
            FILE_ID,
            file=SOURCE_FILE,
            kind="file",
            line=1,
            content_hash=SOURCE_HASH,
            byte_offset=0,
            byte_length=0,
        ),
        CALLER_ID: _node(
            CALLER_ID,
            file=SOURCE_FILE,
            kind="function",
            line=3,
            content_hash=CALLER_HASH,
            byte_offset=30,
            byte_length=70,
        ),
        LOCAL_TARGET_ID: _node(
            LOCAL_TARGET_ID,
            file=SOURCE_FILE,
            kind="function",
            line=1,
            content_hash=TARGET_HASH,
            byte_offset=0,
            byte_length=20,
        ),
        IMPORTED_TARGET_ID: _node(
            IMPORTED_TARGET_ID,
            file=TARGET_FILE,
            kind="function",
            line=1,
            content_hash=TARGET_HASH,
            byte_offset=0,
            byte_length=20,
        ),
    }


def _validate(*records: CallRecord, references=()) -> None:
    validate_call_records(
        records,
        symbol_references=references,
        indexed_nodes=_nodes(),
        file_hashes={SOURCE_FILE: SOURCE_HASH, TARGET_FILE: TARGET_FILE_HASH},
    )


def test_call_records_validate_against_current_nodes_hashes_and_references():
    _validate(_resolved_local(), _unresolved())
    _validate(_resolved_import(), references=(_reference(),))


@pytest.mark.parametrize(
    "record",
    [
        _resolved_local(
            raw=_raw_call(source_hash="e" * 64),
            support=(
                _call_support(content_hash="e" * 64),
                _call_support(
                    kind="caller_definition", line=3, content_hash=CALLER_HASH
                ),
                _call_support(
                    kind="local_definition",
                    line=1,
                    content_hash=TARGET_HASH,
                    endpoint_id=LOCAL_TARGET_ID,
                ),
            ),
        ),
        _resolved_local(caller_kind="method"),
        _resolved_local(
            raw=_raw_call(local_candidates=(_binding(callable_kind="method"),)),
            target_kind="method",
        ),
        _resolved_local(
            support=(
                _call_support(),
                _call_support(
                    kind="caller_definition",
                    line=3,
                    content_hash="e" * 64,
                ),
                _call_support(
                    kind="local_definition",
                    line=1,
                    content_hash=TARGET_HASH,
                    endpoint_id=LOCAL_TARGET_ID,
                ),
            )
        ),
    ],
)
def test_call_record_validation_rejects_stale_or_mismatched_evidence(
    record: CallRecord,
):
    with pytest.raises(GraphContractError):
        _validate(record)


def test_import_resolved_call_requires_the_exact_current_reference():
    record = _resolved_import()

    with pytest.raises(GraphContractError, match="reference"):
        _validate(record)
    with pytest.raises(GraphContractError, match="reference"):
        _validate(
            record,
            references=(
                _reference(raw=replace(_reference().raw, start_byte=61)),
            ),
        )


@pytest.mark.parametrize(
    "record",
    [
        _unresolved(unresolved_reason="target_not_callable"),
        _unresolved(
            unresolved_reason="reference_unresolved",
            reference_unresolved_reason="target_not_indexed",
        ),
    ],
)
def test_unresolved_call_reason_must_match_current_evidence(record: CallRecord):
    with pytest.raises(GraphContractError, match="local/reference evidence"):
        _validate(record)


def test_call_edge_materialization_deduplicates_by_earliest_call_site():
    first = _resolved_local()
    later_raw = _raw_call(
        line=8,
        column=2,
        start_byte=70,
        end_byte=78,
        callee_start_byte=70,
        callee_end_byte=76,
    )
    later = _resolved_local(
        raw=later_raw,
        support=(
            _call_support(line=8),
            _call_support(
                kind="caller_definition", line=3, content_hash=CALLER_HASH
            ),
            _call_support(
                kind="local_definition",
                line=1,
                content_hash=TARGET_HASH,
                endpoint_id=LOCAL_TARGET_ID,
            ),
        ),
    )

    assert materialize_call_edges([later, _unresolved(), first]) == [GraphEdge(
        from_id=CALLER_ID,
        to_id=LOCAL_TARGET_ID,
        type="calls",
        directed=True,
        namespace="loci",
        resolution="exact",
        evidence=GraphEvidence(
            file=SOURCE_FILE,
            line=4,
            content_hash=SOURCE_HASH,
        ),
    )]


def test_valid_call_edge_requires_one_current_resolved_record():
    record = _resolved_local()
    edge = materialize_call_edges([record])[0]

    validate_graph_edges(
        [edge],
        indexed_nodes=_nodes(),
        file_hashes={SOURCE_FILE: SOURCE_HASH, TARGET_FILE: TARGET_FILE_HASH},
        calls=[record],
    )

    with pytest.raises(GraphContractError, match="call record"):
        validate_graph_edges(
            [edge],
            indexed_nodes=_nodes(),
            file_hashes={SOURCE_FILE: SOURCE_HASH, TARGET_FILE: TARGET_FILE_HASH},
        )


@pytest.mark.parametrize(
    "edge",
    [
        replace(materialize_call_edges([_resolved_local()])[0], namespace="wiki"),
        replace(materialize_call_edges([_resolved_local()])[0], directed=False),
        replace(materialize_call_edges([_resolved_local()])[0], resolution="declared"),
        replace(materialize_call_edges([_resolved_local()])[0], from_id=FILE_ID),
        replace(materialize_call_edges([_resolved_local()])[0], to_id=FILE_ID),
        replace(
            materialize_call_edges([_resolved_local()])[0],
            evidence=GraphEvidence(SOURCE_FILE, 9, SOURCE_HASH),
        ),
        replace(
            materialize_call_edges([_resolved_local()])[0],
            evidence=GraphEvidence(SOURCE_FILE, 4, "e" * 64),
        ),
    ],
)
def test_call_edges_reject_invalid_contract_fields(edge: GraphEdge):
    with pytest.raises(GraphContractError):
        validate_graph_edges(
            [edge],
            indexed_nodes=_nodes(),
            file_hashes={SOURCE_FILE: SOURCE_HASH, TARGET_FILE: TARGET_FILE_HASH},
            calls=[_resolved_local()],
        )


def test_recursive_call_is_the_only_deserializable_self_edge():
    recursive_raw = _raw_call(
        callee_text="caller",
        callee_path=("caller",),
        local_candidates=(
            _binding(
                name="caller",
                definition_start_byte=30,
                definition_end_byte=100,
                definition_line=3,
            ),
        ),
    )
    recursive = _resolved_local(
        raw=recursive_raw,
        target_id=CALLER_ID,
        target_file=SOURCE_FILE,
        support=(
            _call_support(),
            _call_support(
                kind="caller_definition", line=3, content_hash=CALLER_HASH
            ),
            _call_support(
                kind="local_definition",
                line=3,
                content_hash=CALLER_HASH,
                endpoint_id=CALLER_ID,
            ),
        ),
    )
    edge = materialize_call_edges([recursive])[0]

    assert GraphEdge.from_dict(edge.to_dict()) == edge
    _validate(recursive)
    validate_graph_edges(
        [edge],
        indexed_nodes=_nodes(),
        file_hashes={SOURCE_FILE: SOURCE_HASH},
        calls=[recursive],
    )

    for invalid in (
        replace(edge, type="links", namespace="wiki"),
        replace(edge, directed=False),
        replace(edge, resolution="declared"),
    ):
        with pytest.raises(GraphContractError):
            GraphEdge.from_dict(invalid.to_dict())
    with pytest.raises(GraphContractError):
        validate_graph_edges(
            [replace(edge, type="links", namespace="wiki")],
            indexed_nodes=_nodes(),
            file_hashes={SOURCE_FILE: SOURCE_HASH},
            calls=[recursive],
        )
    with pytest.raises(GraphContractError):
        validate_graph_edges(
            [edge],
            indexed_nodes=_nodes(),
            file_hashes={SOURCE_FILE: SOURCE_HASH},
        )
