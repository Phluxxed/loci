from __future__ import annotations

from dataclasses import replace

import pytest

from loci.graph.contracts import GraphContractError
from loci.graph.references import (
    MAX_REFERENCE_SUPPORT_RECORDS,
    ReferenceSupport,
    SymbolReferenceRecord,
)
from loci.parser.reference_models import ImportBinding, RawSymbolReference


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
        "support": (_support(),),
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
