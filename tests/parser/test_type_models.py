from __future__ import annotations

from dataclasses import FrozenInstanceError
from hashlib import sha256

import pytest

from loci.parser.reference_models import ImportBinding
from loci.parser.type_models import (
    MAX_TYPE_BINDINGS_PER_OBSERVATION,
    MAX_TYPE_PATH_SEGMENTS,
    LocalTypeBinding,
    RawTypeObservation,
    TypeDeclarationOwner,
)


SOURCE_HASH = sha256(b"typescript source").hexdigest()


def _owner(kind: str = "interface") -> TypeDeclarationOwner:
    return TypeDeclarationOwner(kind=kind, start_byte=0, end_byte=100)


def _local(
    name: str = "Thing",
    *,
    kind: str = "interface",
    namespace: str = "type",
    declaration_start_byte: int = 0,
    declaration_end_byte: int = 5,
) -> LocalTypeBinding:
    return LocalTypeBinding(
        name=name,
        kind=kind,
        namespace=namespace,
        declaration_start_byte=declaration_start_byte,
        declaration_end_byte=declaration_end_byte,
        scope_start_byte=0,
        scope_end_byte=100,
    )


def _import(name: str = "Thing") -> ImportBinding:
    return ImportBinding(
        local_name=name,
        imported_name=name,
        exported_name=None,
        kind="symbol",
        type_only=False,
        module_level=True,
        declaration_start_byte=0,
        scope_start_byte=0,
        scope_end_byte=100,
        import_line=1,
        import_text=f'import {{ {name} }} from "./types"',
        import_specifier="./types",
    )


def _observation(**changes: object) -> RawTypeObservation:
    values: dict[str, object] = {
        "source_file": "src/a.ts",
        "language": "typescript",
        "line": 2,
        "column": 3,
        "start_byte": 10,
        "end_byte": 15,
        "text": "Thing",
        "path": ("Thing",),
        "relation": "uses_type",
        "context": "property",
        "lookup_space": "type",
        "owner": _owner(),
        "local_bindings": (_local(),),
        "import_bindings": (),
        "binding_state": "local",
        "candidates_complete": True,
        "candidates_truncated": 0,
        "unsupported_reason": None,
        "source_hash": SOURCE_HASH,
    }
    values.update(changes)
    return RawTypeObservation(**values)  # type: ignore[arg-type]


def test_local_and_imported_observations_round_trip_with_byte_evidence() -> None:
    local = _observation()
    imported = _observation(
        owner=_owner("function"),
        local_bindings=(),
        import_bindings=(_import(),),
        binding_state="imported",
    )

    assert RawTypeObservation.from_dict(local.to_dict()) == local
    assert RawTypeObservation.from_dict(imported.to_dict()) == imported
    assert local.to_dict()["local_bindings"][0]["namespace"] == "type"
    with pytest.raises(FrozenInstanceError):
        local.text = "Other"  # type: ignore[misc]


def test_class_binding_occupies_both_namespaces() -> None:
    observation = _observation(
        owner=_owner("class"),
        local_bindings=(_local(kind="class", namespace="both"),),
        lookup_space="type",
    )
    assert observation.local_bindings[0].namespace == "both"


def test_unsupported_and_truncated_candidate_observations_are_explicit() -> None:
    unsupported = _observation(
        owner=TypeDeclarationOwner("unindexed", 10, 15),
        path=(),
        local_bindings=(_local(),),
        binding_state="unsupported",
        candidates_complete=False,
        candidates_truncated=0,
        unsupported_reason="unsupported_conditional_type",
    )
    first = _local()
    second = _local(declaration_start_byte=6, declaration_end_byte=11)
    truncated = _observation(
        local_bindings=(first, second),
        binding_state="ambiguous",
        candidates_complete=False,
        candidates_truncated=1,
    )

    assert unsupported.path == ()
    assert RawTypeObservation.from_dict(unsupported.to_dict()) == unsupported
    assert truncated.candidates_truncated == 1
    assert len(truncated.local_bindings) == 2


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("source_hash", "not-a-sha"),
        ("start_byte", -1),
        ("end_byte", 10),
        ("candidates_complete", 1),
        ("unsupported_reason", "why"),
    ],
)
def test_observation_rejects_malformed_state_and_spans(field: str, value: object) -> None:
    changes: dict[str, object] = {field: value}
    if field == "end_byte":
        changes["start_byte"] = 10
    if field == "unsupported_reason":
        changes["binding_state"] = "local"
    with pytest.raises(ValueError):
        _observation(**changes)


def test_nested_records_and_exact_fields_are_strict() -> None:
    owner = _owner().to_dict()
    owner["extra"] = True
    with pytest.raises(ValueError):
        TypeDeclarationOwner.from_dict(owner)

    values = _observation().to_dict()
    values["owner"]["start_byte"] = 20
    values["owner"]["end_byte"] = 19
    with pytest.raises(ValueError):
        RawTypeObservation.from_dict(values)


def test_observation_enforces_binding_and_path_limits() -> None:
    too_many = tuple(_local(name=f"Thing{i}") for i in range(MAX_TYPE_BINDINGS_PER_OBSERVATION + 1))
    with pytest.raises(ValueError):
        _observation(
            local_bindings=too_many,
            binding_state="ambiguous",
            candidates_complete=False,
            candidates_truncated=1,
        )

    too_deep = tuple(f"T{i}" for i in range(MAX_TYPE_PATH_SEGMENTS + 1))
    with pytest.raises(ValueError):
        _observation(path=too_deep)
