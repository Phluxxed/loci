from __future__ import annotations

from dataclasses import replace

import pytest

from loci.parser.reference_models import (
    MAX_LOCAL_EXPORTS_PER_FILE,
    MAX_REFERENCE_PATH_SEGMENTS,
    MAX_REFERENCE_RESOLUTION_CANDIDATES,
    ImportBinding,
    RawLocalExport,
    RawSymbolReference,
    ReferenceExtractionBatch,
)


SOURCE_HASH = "a" * 64


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
        "scope_end_byte": 80,
        "import_line": 1,
        "import_text": "from model import Thing as Alias",
        "import_specifier": "model",
    }
    values.update(overrides)
    return ImportBinding(**values)


def _export(**overrides) -> RawLocalExport:
    values = {
        "source_file": "src/model.py",
        "language": "python",
        "line": 3,
        "text": "class Thing: ...",
        "local_name": "Thing",
        "exported_name": "Thing",
        "type_only": False,
        "definition_start_byte": 10,
        "definition_end_byte": 26,
        "source_hash": SOURCE_HASH,
    }
    values.update(overrides)
    return RawLocalExport(**values)


def _reference(**overrides) -> RawSymbolReference:
    values = {
        "source_file": "src/use.py",
        "language": "python",
        "line": 4,
        "column": 12,
        "start_byte": 45,
        "end_byte": 50,
        "text": "Alias",
        "path": ("Alias",),
        "candidate_bindings": (_binding(),),
        "binding_state": "definite",
        "source_hash": SOURCE_HASH,
    }
    values.update(overrides)
    return RawSymbolReference(**values)


@pytest.mark.parametrize(
    "record",
    [
        _binding(),
        _export(),
        _reference(),
        ReferenceExtractionBatch(exports=(_export(),), references=(_reference(),)),
    ],
)
def test_reference_parser_models_round_trip_strictly(record):
    serialized = record.to_dict()

    assert type(record).from_dict(serialized) == record

    missing = dict(serialized)
    missing.pop(next(iter(missing)))
    with pytest.raises(ValueError, match="fields"):
        type(record).from_dict(missing)

    unknown = dict(serialized)
    unknown["unknown"] = True
    with pytest.raises(ValueError, match="fields"):
        type(record).from_dict(unknown)


@pytest.mark.parametrize(
    "overrides",
    [
        {"local_name": ""},
        {"kind": "guess"},
        {"kind": []},
        {"type_only": 1},
        {"declaration_start_byte": -1},
        {"scope_start_byte": 2, "declaration_start_byte": 1},
        {"scope_end_byte": 0},
        {"import_line": 0},
        {"import_text": ""},
        {"import_specifier": ""},
        {
            "kind": "side_effect",
            "local_name": "Alias",
            "imported_name": None,
        },
        {"kind": "glob", "local_name": "Alias", "imported_name": None},
    ],
)
def test_import_binding_rejects_malformed_or_impossible_states(overrides):
    with pytest.raises(ValueError):
        _binding(**overrides)


@pytest.mark.parametrize(
    "overrides",
    [
        {"source_file": "/tmp/model.py"},
        {"source_file": "src/../model.py"},
        {"line": 0},
        {"type_only": "false"},
        {"definition_start_byte": 10, "definition_end_byte": None},
        {"definition_start_byte": 26, "definition_end_byte": 10},
        {"source_hash": "not-a-sha256"},
    ],
)
def test_raw_local_export_rejects_malformed_fields(overrides):
    with pytest.raises(ValueError):
        _export(**overrides)


@pytest.mark.parametrize(
    "overrides",
    [
        {"column": 0},
        {"start_byte": 50, "end_byte": 45},
        {"path": ()},
        {"path": ("Alias", "")},
        {"path": ("segment",) * (MAX_REFERENCE_PATH_SEGMENTS + 1)},
        {"candidate_bindings": ()},
        {"binding_state": "definite", "candidate_bindings": (_binding(), _binding())},
        {"binding_state": "ambiguous", "candidate_bindings": (_binding(),)},
        {"binding_state": "guess"},
        {"binding_state": []},
        {
            "candidate_bindings": (
                _binding(
                    kind="glob",
                    local_name=None,
                    imported_name=None,
                ),
            )
        },
        {
            "binding_state": "deferred",
            "candidate_bindings": (
                _binding(
                    kind="namespace",
                    local_name=None,
                    imported_name=None,
                ),
            ),
        },
        {
            "candidate_bindings": (
                replace(_binding(), scope_start_byte=51, declaration_start_byte=51),
            )
        },
        {"source_hash": "0" * 63},
    ],
)
def test_raw_symbol_reference_rejects_malformed_or_impossible_states(overrides):
    with pytest.raises(ValueError):
        _reference(**overrides)


def test_reference_parser_models_enforce_collection_bounds():
    binding = _binding()
    with pytest.raises(ValueError, match="candidate"):
        _reference(
            binding_state="ambiguous",
            candidate_bindings=(binding,) * (MAX_REFERENCE_RESOLUTION_CANDIDATES + 1),
        )

    export = _export()
    with pytest.raises(ValueError, match="exports"):
        ReferenceExtractionBatch(
            exports=(export,) * (MAX_LOCAL_EXPORTS_PER_FILE + 1),
            references=(),
        )


def test_reference_parser_models_require_immutable_tuple_collections():
    with pytest.raises(ValueError, match="path"):
        _reference(path=["Alias"])

    with pytest.raises(ValueError, match="candidate"):
        _reference(candidate_bindings=[_binding()])

    with pytest.raises(ValueError, match="exports"):
        ReferenceExtractionBatch(exports=[_export()], references=())


def test_go_default_package_reference_is_the_only_deferred_binding_state():
    binding = _binding(
        kind="namespace",
        local_name=None,
        imported_name=None,
    )

    reference = _reference(
        source_file="cmd/app/main.go",
        language="go",
        path=("store", "Thing"),
        text="store.Thing",
        candidate_bindings=(binding,),
        binding_state="deferred",
    )

    assert RawSymbolReference.from_dict(reference.to_dict()) == reference


def test_reference_parser_model_unknown_non_string_field_fails_closed():
    serialized = _binding().to_dict()
    serialized[1] = True

    with pytest.raises(ValueError, match="fields"):
        ImportBinding.from_dict(serialized)
