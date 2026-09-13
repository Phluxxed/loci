from __future__ import annotations

from hashlib import sha256

import pytest

from loci.graph.type_models import TypeControl, TypeRelationRecord, TypeSupport
from loci.parser.reference_models import ImportBinding
from loci.parser.type_models import LocalTypeBinding, RawTypeObservation, TypeDeclarationOwner


HASH = sha256(b"indexed file").hexdigest()


def _raw(*, imported: bool = False) -> RawTypeObservation:
    binding = ImportBinding(
        local_name="Thing",
        imported_name="Thing",
        exported_name=None,
        kind="symbol",
        type_only=False,
        module_level=True,
        declaration_start_byte=0,
        scope_start_byte=0,
        scope_end_byte=100,
        import_line=1,
        import_text='import { Thing } from "./types"',
        import_specifier="./types",
    )
    return RawTypeObservation(
        source_file="src/a.ts",
        language="typescript",
        source_hash=HASH,
        line=2,
        column=3,
        start_byte=10,
        end_byte=15,
        text="Thing",
        path=("Thing",),
        relation="uses_type",
        context="property",
        lookup_space="type",
        owner=TypeDeclarationOwner("interface", 0, 100),
        local_bindings=(
            LocalTypeBinding(
                name="Thing",
                kind="interface",
                namespace="type",
                declaration_start_byte=0,
                declaration_end_byte=5,
                scope_start_byte=0,
                scope_end_byte=100,
            ),
        ) if not imported else (),
        import_bindings=(binding,) if imported else (),
        binding_state="imported" if imported else "local",
        candidates_complete=True,
        candidates_truncated=0,
        unsupported_reason=None,
    )


def _support(*, imported: bool = False) -> tuple[TypeSupport, ...]:
    values = [
        TypeSupport("type_site", "src/a.ts", 2, HASH, "src/a.ts::Owner"),
        TypeSupport("owner", "src/a.ts", 1, HASH, "src/a.ts::Owner"),
        TypeSupport("definition", "src/types.ts", 4, HASH, "src/types.ts::Thing"),
    ]
    if imported:
        values.append(TypeSupport("import_binding", "src/a.ts", 1, HASH, "src/types.ts::Thing"))
    return tuple(values)


def _resolved(*, imported: bool = False) -> TypeRelationRecord:
    target = "src/types.ts::Thing"
    return TypeRelationRecord(
        raw=_raw(imported=imported),
        source_id="src/a.ts::Owner",
        source_kind="interface",
        target_id=target,
        target_file="src/types.ts",
        target_kind="interface",
        status="resolved",
        unresolved_reason=None,
        resolution_basis="direct_binding" if imported else "lexical_binding",
        support=_support(imported=imported),
        resolution_controls=(TypeControl("src/tsconfig.json", HASH),),
        candidate_universe="import_surface" if imported else "lexical_scope",
        candidate_scope_file="src/types.ts" if imported else "src/a.ts",
        candidate_ids=(target,),
        candidates_complete=True,
        candidates_truncated=0,
    )


def test_resolved_local_and_imported_records_round_trip_with_tiers() -> None:
    local = _resolved()
    imported = _resolved(imported=True)

    assert local.resolution == "exact"
    assert imported.resolution == "import-resolved"
    assert TypeRelationRecord.from_dict(local.to_dict()) == local
    assert TypeRelationRecord.from_dict(imported.to_dict()) == imported


def test_unresolved_candidates_and_truncation_remain_evidence() -> None:
    record = TypeRelationRecord(
        raw=_raw(imported=True),
        source_id="src/a.ts::Owner",
        source_kind="interface",
        target_id=None,
        target_file=None,
        target_kind=None,
        status="unresolved",
        unresolved_reason="ambiguous_target",
        resolution_basis=None,
        support=(
            TypeSupport("type_site", "src/a.ts", 2, HASH),
            TypeSupport("import_binding", "src/a.ts", 1, HASH),
        ),
        resolution_controls=(TypeControl("src/tsconfig.json", HASH),),
        candidate_universe="import_surface",
        candidate_scope_file="src/types.ts",
        candidate_ids=("src/types.ts::ThingA", "src/types.ts::ThingB"),
        candidates_complete=False,
        candidates_truncated=1,
    )

    assert record.resolution is None
    assert TypeRelationRecord.from_dict(record.to_dict()) == record
    assert record.candidate_ids == ("src/types.ts::ThingA", "src/types.ts::ThingB")


@pytest.mark.parametrize(
    "changes",
    [
        {"target_id": "other", "candidate_ids": ("target",)},
        {"resolution_basis": "bad"},
        {"unresolved_reason": "bad"},
        {"candidates_complete": 1},
        {"candidates_truncated": True},
        {"resolution_controls": ("not-a-control",)},
    ],
)
def test_relation_rejects_inconsistent_resolution_state(changes: dict[str, object]) -> None:
    values = {
        "raw": _raw(),
        "source_id": "src/a.ts::Owner",
        "source_kind": "interface",
        "target_id": "target",
        "target_file": "src/types.ts",
        "target_kind": "interface",
        "status": "resolved",
        "unresolved_reason": None,
        "resolution_basis": "lexical_binding",
        "support": _support(),
        "resolution_controls": (TypeControl("src/tsconfig.json", HASH),),
        "candidate_universe": "lexical_scope",
        "candidate_scope_file": "src/a.ts",
        "candidate_ids": ("target",),
        "candidates_complete": True,
        "candidates_truncated": 0,
    }
    values.update(changes)
    with pytest.raises(ValueError):
        TypeRelationRecord(**values)  # type: ignore[arg-type]


def test_graph_records_reject_unknown_fields_and_bad_hashes() -> None:
    support = TypeSupport("type_site", "src/a.ts", 2, HASH)
    encoded = support.to_dict()
    encoded["extra"] = 1
    with pytest.raises(ValueError):
        TypeSupport.from_dict(encoded)

    control = TypeControl("src/tsconfig.json", HASH).to_dict()
    control["content_hash"] = "0" * 63
    with pytest.raises(ValueError):
        TypeControl.from_dict(control)

    with pytest.raises(ValueError):
        TypeSupport("type_site", "/absolute.ts", 1, HASH)
