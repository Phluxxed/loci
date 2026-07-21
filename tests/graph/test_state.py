from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

import pytest

from loci.graph.contracts import (
    GRAPH_SCHEMA_VERSION,
    GRAPH_STATE_SCHEMA_VERSION,
    GraphContractError,
    GraphContribution,
    GraphEdge,
    GraphEvidence,
    GraphNodeRef,
)
from loci.graph.calls import CallRecord
from loci.graph.imports import ImportRecord
from loci.graph.profiles import GraphProfile, LoadedGraphProfile
from loci.graph.references import ReferenceSupport, SymbolReferenceRecord
from loci.graph.state import (
    GraphDiagnostic,
    GraphIndexState,
    LoadedGraphContribution,
)
from loci.parser.imports import RawImport, RustImportContext
from loci.parser._binding_context import ExecutableOwner
from loci.parser.call_models import RawCallSite
from loci.parser.reference_models import (
    ImportBinding,
    RawLocalExport,
    RawSymbolReference,
)


FIXTURES = Path(__file__).parents[1] / "fixtures" / "graph_profiles"


def _raw_import() -> RawImport:
    return RawImport(
        source_file="src/example.py",
        language="python",
        line=3,
        text="from package import target",
        specifier="package",
        imported_name="target",
        type_only=False,
        is_reexport=False,
        source_hash="d" * 64,
        bindings=(),
    )


def _resolved_import() -> ImportRecord:
    return ImportRecord(
        raw=_raw_import(),
        source_id="src/example.py::__file__#file",
        target_file="src/package/target.py",
        target_package=None,
        target_crate=None,
        target_kind="file",
        target_id="src/package/target.py::__file__#file",
        status="resolved",
        unresolved_reason=None,
    )


def _resolved_go_import() -> ImportRecord:
    raw = RawImport(
        source_file="cmd/server/main.go",
        language="go",
        line=4,
        text='import "example.com/project/internal/store"',
        specifier="example.com/project/internal/store",
        imported_name=None,
        type_only=False,
        is_reexport=False,
        source_hash="e" * 64,
        bindings=(),
    )
    return ImportRecord(
        raw=raw,
        source_id="cmd/server/main.go::__file__#file",
        target_file=None,
        target_package="example.com/project/internal/store",
        target_crate=None,
        target_kind="package",
        target_id=(
            "internal/store::example.com/project/internal/store#package"
        ),
        status="resolved",
        unresolved_reason=None,
    )


def _rust_raw_import() -> RawImport:
    return RawImport(
        source_file="src/lib.rs",
        language="rust",
        line=2,
        text="use crate::api::Client;",
        specifier="crate::api::Client",
        imported_name="Client",
        type_only=False,
        is_reexport=False,
        source_hash="f" * 64,
        bindings=(),
        rust=RustImportContext(
            kind="use",
            lexical_module_path=(),
            visibility="private",
            module_level=True,
            configuration="unconditional",
        ),
    )


def _inline_rust_module_observation() -> RawImport:
    return RawImport(
        source_file="src/lib.rs",
        language="rust",
        line=1,
        text="pub mod inline { pub struct Thing; }",
        specifier="inline",
        imported_name=None,
        type_only=False,
        is_reexport=True,
        source_hash="f" * 64,
        bindings=(),
        rust=RustImportContext(
            kind="module",
            lexical_module_path=(),
            visibility="pub",
            module_level=True,
            configuration="unconditional",
            inline=True,
        ),
    )


def _resolved_rust_file_import() -> ImportRecord:
    return ImportRecord(
        raw=_rust_raw_import(),
        source_id="src/lib.rs::__file__#file",
        target_file="src/api.rs",
        target_package=None,
        target_crate=None,
        target_kind="file",
        target_id="src/api.rs::__file__#file",
        status="resolved",
        unresolved_reason=None,
        resolution_basis="rust_module_path",
        resolution_control_files=("Cargo.toml",),
        resolution_configuration="unconditional",
    )


def _resolved_rust_crate_import() -> ImportRecord:
    return ImportRecord(
        raw=_rust_raw_import(),
        source_id="src/lib.rs::__file__#file",
        target_file=None,
        target_package=None,
        target_crate="Cargo.toml::lib:demo",
        target_kind="crate",
        target_id="Cargo.toml::lib:demo#crate",
        status="resolved",
        unresolved_reason=None,
        resolution_basis="cargo_path_dependency",
        resolution_control_files=("Cargo.toml", "demo/Cargo.toml"),
        resolution_configuration="declared_possible",
    )


def _reference_binding() -> ImportBinding:
    return ImportBinding(
        local_name="Target",
        imported_name="Target",
        exported_name=None,
        kind="symbol",
        type_only=False,
        module_level=True,
        declaration_start_byte=0,
        scope_start_byte=0,
        scope_end_byte=200,
        import_line=3,
        import_text="from package import Target",
        import_specifier="package",
    )


def _local_export() -> RawLocalExport:
    return RawLocalExport(
        source_file="src/package/target.py",
        language="python",
        line=2,
        text="class Target:",
        local_name="Target",
        exported_name="Target",
        type_only=False,
        definition_start_byte=10,
        definition_end_byte=40,
        source_hash="e" * 64,
    )


def _symbol_reference() -> SymbolReferenceRecord:
    binding = _reference_binding()
    raw = RawSymbolReference(
        source_file="src/example.py",
        language="python",
        line=5,
        column=12,
        start_byte=80,
        end_byte=86,
        text="Target",
        path=("Target",),
        candidate_bindings=(binding,),
        binding_state="definite",
        source_hash="d" * 64,
    )
    return SymbolReferenceRecord(
        raw=raw,
        binding=binding,
        source_id="src/example.py::run#function",
        source_kind="function",
        import_source_id="src/example.py::__file__#file",
        import_target_id="src/package/target.py::__file__#file",
        target_file="src/package/target.py",
        target_id="src/package/target.py::Target#class",
        target_kind="class",
        status="resolved",
        unresolved_reason=None,
        import_unresolved_reason=None,
        resolution_basis="direct_binding",
        support=(
            ReferenceSupport(
                kind="import_binding",
                file="src/example.py",
                line=3,
                content_hash="d" * 64,
                endpoint_id="src/package/target.py::__file__#file",
            ),
            ReferenceSupport(
                kind="definition",
                file="src/package/target.py",
                line=2,
                content_hash="e" * 64,
                endpoint_id="src/package/target.py::Target#class",
            ),
        ),
        resolution_control_files=(),
        resolution_configuration=None,
    )


def _call_record() -> CallRecord:
    return CallRecord(
        raw=RawCallSite(
            source_file="src/example.py",
            language="python",
            line=5,
            column=12,
            start_byte=80,
            end_byte=88,
            callee_start_byte=80,
            callee_end_byte=86,
            callee_text="Target",
            callee_path=("Target",),
            callee_form="identifier",
            local_candidates=(),
            local_binding_state="absent",
            owner=ExecutableOwner(
                kind="callable",
                definition_start_byte=50,
                definition_end_byte=120,
                body_start_byte=70,
                body_end_byte=120,
            ),
            source_hash="d" * 64,
        ),
        caller_id="src/example.py::run#function",
        caller_kind="function",
        target_file=None,
        target_id=None,
        target_kind=None,
        status="unresolved",
        resolution=None,
        unresolved_reason="callee_not_proven",
        reference_unresolved_reason=None,
        resolution_basis=None,
        support=(),
        resolution_control_files=(),
        resolution_configuration=None,
    )


def _state() -> GraphIndexState:
    profile = GraphProfile.from_dict(
        json.loads((FIXTURES / "generic.json").read_text())
    )
    node = GraphNodeRef(
        id="guide.md::Guide#section",
        namespace="example",
        kind="section",
        attributes={"status": "current"},
    )
    edge = GraphEdge(
        from_id="guide.md::Guide#section",
        to_id="other.md::Other#section",
        type="related_to",
        directed=True,
        namespace="example",
        resolution="declared",
        evidence=GraphEvidence(
            file="guide.md",
            line=2,
            content_hash="a" * 64,
        ),
    )
    contribution = GraphContribution(
        schema_version=GRAPH_SCHEMA_VERSION,
        namespace="example",
        nodes=(node,),
        edges=(edge,),
    )
    return GraphIndexState(
        schema_version=GRAPH_STATE_SCHEMA_VERSION,
        profiles=(LoadedGraphProfile(
            source=".loci/graph/profiles/generic.json",
            content_hash="b" * 64,
            profile=profile,
        ),),
        nodes=(node,),
        edges=(edge,),
        imports=(_resolved_import(),),
        rust_module_observations=(_inline_rust_module_observation(),),
        exports=(_local_export(),),
        symbol_references=(_symbol_reference(),),
        calls=(_call_record(),),
        contributions=(LoadedGraphContribution(
            source=".loci/graph/contributions/example.json",
            content_hash="c" * 64,
            contribution=contribution,
        ),),
        input_hashes={
            ".loci/graph/contributions/example.json": "c" * 64,
            ".loci/graph/profiles/generic.json": "b" * 64,
        },
        diagnostics=(GraphDiagnostic(
            severity="warning",
            code="GRAPH_EVIDENCE_STALE",
            message="Evidence changed",
            source=".loci/graph/contributions/example.json",
            details={"edge_index": 0},
        ),),
    )


def test_graph_state_round_trip_is_stable():
    state = _state()

    serialized = state.to_dict()
    restored = GraphIndexState.from_dict(serialized)

    assert restored == state
    assert list(serialized["input_hashes"]) == sorted(serialized["input_hashes"])
    assert json.dumps(
        restored.to_dict(),
        separators=(",", ":"),
    ) == json.dumps(serialized, separators=(",", ":"))


def test_import_record_round_trip_is_exact_and_stable():
    record = _resolved_import()

    serialized = record.to_dict()

    assert serialized == {
        "raw": {
            "source_file": "src/example.py",
            "language": "python",
            "line": 3,
            "text": "from package import target",
            "specifier": "package",
            "imported_name": "target",
            "type_only": False,
            "is_reexport": False,
            "source_hash": "d" * 64,
            "rust": None,
        },
        "source_id": "src/example.py::__file__#file",
        "target_file": "src/package/target.py",
        "target_package": None,
        "target_crate": None,
        "target_kind": "file",
        "target_id": "src/package/target.py::__file__#file",
        "status": "resolved",
        "unresolved_reason": None,
        "resolution_basis": None,
        "resolution_control_files": [],
        "resolution_configuration": None,
    }
    assert list(serialized) == [
        "raw",
        "source_id",
        "target_file",
        "target_package",
        "target_crate",
        "target_kind",
        "target_id",
        "status",
        "unresolved_reason",
        "resolution_basis",
        "resolution_control_files",
        "resolution_configuration",
    ]
    assert list(serialized["raw"]) == [
        "source_file",
        "language",
        "line",
        "text",
        "specifier",
        "imported_name",
        "type_only",
        "is_reexport",
        "source_hash",
        "rust",
    ]
    assert ImportRecord.from_dict(serialized) == record


def test_rust_import_record_round_trip_preserves_strict_context_and_provenance():
    record = _resolved_rust_file_import()

    serialized = record.to_dict()

    assert serialized["raw"]["rust"] == {
        "kind": "use",
        "lexical_module_path": [],
        "visibility": "private",
        "module_level": True,
        "configuration": "unconditional",
        "path_override": None,
        "lexical_module_visibilities": [],
        "lexical_module_configurations": [],
        "inline": False,
    }
    assert serialized["target_file"] == "src/api.rs"
    assert serialized["target_crate"] is None
    assert serialized["resolution_basis"] == "rust_module_path"
    assert serialized["resolution_configuration"] == "unconditional"
    assert ImportRecord.from_dict(serialized) == record


def test_rust_crate_import_round_trip_preserves_crate_identity():
    record = _resolved_rust_crate_import()

    serialized = record.to_dict()

    assert serialized["target_file"] is None
    assert serialized["target_package"] is None
    assert serialized["target_crate"] == "Cargo.toml::lib:demo"
    assert serialized["target_kind"] == "crate"
    assert serialized["target_id"] == "Cargo.toml::lib:demo#crate"
    assert serialized["resolution_configuration"] == "declared_possible"
    assert ImportRecord.from_dict(serialized) == record


def test_package_import_record_round_trip_preserves_package_identity():
    record = _resolved_go_import()

    serialized = record.to_dict()

    assert serialized["target_file"] is None
    assert serialized["target_package"] == "example.com/project/internal/store"
    assert serialized["target_kind"] == "package"
    assert ImportRecord.from_dict(serialized) == record


def test_javascript_import_record_round_trip_preserves_resolution_provenance():
    raw = RawImport(
        source_file="apps/web/src/page.ts",
        language="typescript",
        line=1,
        text='import {format} from "@repo/core/format";',
        specifier="@repo/core/format",
        imported_name=None,
        type_only=False,
        is_reexport=False,
        source_hash="f" * 64,
        bindings=(),
    )
    record = ImportRecord(
        raw=raw,
        source_id="apps/web/src/page.ts::__file__#file",
        target_file="packages/core/src/format.ts",
        target_package=None,
        target_crate=None,
        target_kind="file",
        target_id="packages/core/src/format.ts::__file__#file",
        status="resolved",
        unresolved_reason=None,
        resolution_basis="workspace_exports",
        resolution_control_files=(
            "apps/web/package.json",
            "package.json",
            "packages/core/package.json",
        ),
    )

    serialized = record.to_dict()

    assert serialized["resolution_basis"] == "workspace_exports"
    assert serialized["resolution_control_files"] == [
        "apps/web/package.json",
        "package.json",
        "packages/core/package.json",
    ]
    assert ImportRecord.from_dict(serialized) == record


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("resolution_basis", "guessed"),
        ("resolution_control_files", ["../outside.json"]),
        ("resolution_control_files", ["z.json", "a.json"]),
        ("resolution_control_files", ["package.json", "package.json"]),
    ],
)
def test_import_record_rejects_invalid_resolution_provenance(
    field: str,
    value: object,
):
    payload = _resolved_import().to_dict()
    payload[field] = value

    with pytest.raises(GraphContractError):
        ImportRecord.from_dict(payload)


@pytest.mark.parametrize(
    "field",
    [
        "status",
        "source_id",
        "target_package",
        "target_crate",
        "target_kind",
        "resolution_basis",
        "resolution_control_files",
        "resolution_configuration",
    ],
)
def test_import_record_rejects_missing_fields(field: str):
    payload = _resolved_import().to_dict()
    del payload[field]

    with pytest.raises(GraphContractError) as exc_info:
        ImportRecord.from_dict(payload)

    assert exc_info.value.code == "INVALID_GRAPH_SCHEMA"
    assert exc_info.value.details["missing"] == [field]


def test_import_record_rejects_unknown_raw_fields():
    payload = _resolved_import().to_dict()
    payload["raw"]["unexpected"] = True

    with pytest.raises(GraphContractError) as exc_info:
        ImportRecord.from_dict(payload)

    assert exc_info.value.code == "INVALID_GRAPH_SCHEMA"
    assert exc_info.value.details["unknown"] == ["unexpected"]


def test_graph_state_rejects_missing_raw_import_bindings():
    payload = cast(dict[str, Any], _state().to_dict())
    del payload["imports"][0]["raw"]["bindings"]

    with pytest.raises(GraphContractError) as exc_info:
        GraphIndexState.from_dict(payload)

    assert exc_info.value.code == "INVALID_GRAPH_SCHEMA"
    assert exc_info.value.details["missing"] == ["bindings"]


@pytest.mark.parametrize(
    "field",
    [
        "kind",
        "lexical_module_path",
        "visibility",
        "module_level",
        "configuration",
        "path_override",
        "lexical_module_visibilities",
        "lexical_module_configurations",
        "inline",
    ],
)
def test_rust_import_context_rejects_missing_fields(field: str):
    payload = _resolved_rust_file_import().to_dict()
    del payload["raw"]["rust"][field]

    with pytest.raises(GraphContractError) as exc_info:
        ImportRecord.from_dict(payload)

    assert exc_info.value.code == "INVALID_GRAPH_SCHEMA"
    assert exc_info.value.details["missing"] == [field]


def test_rust_import_context_rejects_unknown_fields():
    payload = _resolved_rust_file_import().to_dict()
    payload["raw"]["rust"]["guessed_scope"] = "crate"

    with pytest.raises(GraphContractError) as exc_info:
        ImportRecord.from_dict(payload)

    assert exc_info.value.details["unknown"] == ["guessed_scope"]


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("lexical_module_path", ["outer", "bad::child"]),
        ("lexical_module_path", ["outer", ".."]),
        ("lexical_module_visibilities", ["pub"]),
        ("lexical_module_configurations", ["conditional"]),
        ("visibility", "pub(in /outside)"),
        ("inline", True),
        ("path_override", "custom.rs"),
    ],
)
def test_rust_import_context_rejects_invalid_scope_shapes(
    field: str,
    value: object,
):
    payload = _resolved_rust_file_import().to_dict()
    payload["raw"]["rust"][field] = value

    with pytest.raises(GraphContractError):
        ImportRecord.from_dict(payload)


def test_raw_import_rejects_missing_or_cross_language_rust_context():
    missing = _resolved_rust_file_import().to_dict()
    missing["raw"]["rust"] = None
    cross_language = _resolved_import().to_dict()
    cross_language["raw"]["rust"] = _resolved_rust_file_import().to_dict()[
        "raw"
    ]["rust"]

    with pytest.raises(GraphContractError, match="requires Rust context"):
        ImportRecord.from_dict(missing)
    with pytest.raises(GraphContractError, match="Only Rust imports"):
        ImportRecord.from_dict(cross_language)


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"target_file": None}, "Resolved file import requires a target file and ID"),
        ({"target_id": None}, "Resolved file import requires a target file and ID"),
        ({"target_package": "example.com/pkg"}, "Resolved file import cannot have a target package"),
        ({"target_kind": None}, "Resolved import requires a target kind"),
        ({"target_kind": "package"}, "Resolved package import cannot have a target file"),
        ({"unresolved_reason": "external"}, "Resolved import cannot have an unresolved reason"),
        ({"status": "unresolved"}, "Unresolved import cannot have a target"),
        (
            {
                "status": "unresolved",
                "target_file": None,
                "target_kind": None,
                "target_id": None,
            },
            "Unresolved import requires an unresolved reason",
        ),
    ],
)
def test_import_record_rejects_impossible_status_combinations(
    changes: dict[str, object],
    message: str,
):
    payload = _resolved_import().to_dict()
    payload.update(changes)

    with pytest.raises(GraphContractError, match=message):
        ImportRecord.from_dict(payload)


@pytest.mark.parametrize(
    ("record", "message"),
    [
        (_resolved_import, "Go imports must target packages"),
        (_resolved_go_import, "Only Go imports may target packages"),
    ],
)
def test_import_record_rejects_language_target_mismatches(record, message: str):
    payload = record().to_dict()
    if payload["target_kind"] == "file":
        payload["raw"]["language"] = "go"
    else:
        payload["raw"]["language"] = "python"

    with pytest.raises(GraphContractError, match=message):
        ImportRecord.from_dict(payload)


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("target_crate", None, "requires a target crate and ID"),
        ("target_file", "src/api.rs", "cannot have a file or package target"),
        ("target_id", "other#crate", "target identity is inconsistent"),
        ("resolution_basis", "workspace_exports", "Invalid Rust resolution basis"),
        ("resolution_configuration", None, "requires resolution configuration"),
        ("resolution_configuration", "conditional", "Invalid Rust resolution"),
    ],
)
def test_rust_crate_import_rejects_invalid_target_and_provenance(
    field: str,
    value: object,
    message: str,
):
    payload = _resolved_rust_crate_import().to_dict()
    payload[field] = value

    with pytest.raises(GraphContractError, match=message):
        ImportRecord.from_dict(payload)


def test_unresolved_rust_import_rejects_control_or_configuration_provenance():
    payload = _resolved_rust_crate_import().to_dict()
    payload.update({
        "target_crate": None,
        "target_kind": None,
        "target_id": None,
        "status": "unresolved",
        "unresolved_reason": "external",
        "resolution_basis": None,
    })
    controls = dict(payload)
    configuration = dict(payload)
    controls["resolution_configuration"] = None
    configuration["resolution_control_files"] = []

    with pytest.raises(GraphContractError, match="cannot have control files"):
        ImportRecord.from_dict(controls)
    with pytest.raises(GraphContractError, match="cannot have resolution configuration"):
        ImportRecord.from_dict(configuration)


def test_empty_graph_state_has_complete_envelope():
    state = GraphIndexState.empty()

    assert state.to_dict() == {
        "schema_version": GRAPH_STATE_SCHEMA_VERSION,
        "profiles": [],
        "nodes": [],
        "edges": [],
        "imports": [],
        "rust_module_observations": [],
        "exports": [],
        "symbol_references": [],
        "calls": [],
        "contributions": [],
        "input_hashes": {},
        "diagnostics": [],
    }


def test_graph_state_uses_schema_version_eight():
    assert GRAPH_STATE_SCHEMA_VERSION == 8


def test_graph_state_rejects_schema_version_two_as_stale():
    payload = _state().to_dict()
    payload["schema_version"] = 2

    with pytest.raises(GraphContractError) as exc_info:
        GraphIndexState.from_dict(payload)

    assert exc_info.value.code == "INVALID_GRAPH_SCHEMA"
    assert exc_info.value.details == {
        "field": "schema_version",
        "schema_version": 2,
    }


def test_graph_state_rejects_schema_version_three_as_stale():
    payload = _state().to_dict()
    payload["schema_version"] = 3

    with pytest.raises(GraphContractError) as exc_info:
        GraphIndexState.from_dict(payload)

    assert exc_info.value.details == {
        "field": "schema_version",
        "schema_version": 3,
    }


def test_graph_state_rejects_schema_version_four_as_stale():
    payload = _state().to_dict()
    payload["schema_version"] = 4

    with pytest.raises(GraphContractError) as exc_info:
        GraphIndexState.from_dict(payload)

    assert exc_info.value.details == {
        "field": "schema_version",
        "schema_version": 4,
    }


def test_graph_state_rejects_schema_version_five_as_stale():
    payload = _state().to_dict()
    payload["schema_version"] = 5

    with pytest.raises(GraphContractError) as exc_info:
        GraphIndexState.from_dict(payload)

    assert exc_info.value.details == {
        "field": "schema_version",
        "schema_version": 5,
    }


def test_graph_state_rejects_schema_version_six_as_stale():
    payload = _state().to_dict()
    payload["schema_version"] = 6

    with pytest.raises(GraphContractError) as exc_info:
        GraphIndexState.from_dict(payload)

    assert exc_info.value.details == {
        "field": "schema_version",
        "schema_version": 6,
    }


def test_graph_state_rejects_schema_version_seven_as_stale():
    payload = _state().to_dict()
    payload["schema_version"] = 7

    with pytest.raises(GraphContractError) as exc_info:
        GraphIndexState.from_dict(payload)

    assert exc_info.value.details == {
        "field": "schema_version",
        "schema_version": 7,
    }


@pytest.mark.parametrize("field", ["exports", "symbol_references", "calls"])
def test_graph_state_rejects_missing_reference_envelope_fields(field: str):
    payload = _state().to_dict()
    del payload[field]

    with pytest.raises(GraphContractError) as exc_info:
        GraphIndexState.from_dict(payload)

    assert exc_info.value.code == "INVALID_GRAPH_SCHEMA"
    assert exc_info.value.details["missing"] == [field]


def test_graph_state_rejects_unknown_reference_envelope_field():
    payload = _state().to_dict()
    payload["reference_guesses"] = []

    with pytest.raises(GraphContractError) as exc_info:
        GraphIndexState.from_dict(payload)

    assert exc_info.value.code == "INVALID_GRAPH_SCHEMA"
    assert exc_info.value.details["unknown"] == ["reference_guesses"]


def test_graph_state_rejects_malformed_local_export():
    payload = cast(dict[str, Any], _state().to_dict())
    payload["exports"][0]["source_file"] = "../target.py"

    with pytest.raises(GraphContractError) as exc_info:
        GraphIndexState.from_dict(payload)

    assert exc_info.value.code == "INVALID_GRAPH_SCHEMA"
    assert exc_info.value.details["field"] == "exports"


def test_graph_state_rejects_malformed_symbol_reference():
    payload = cast(dict[str, Any], _state().to_dict())
    payload["symbol_references"][0]["raw"]["source_hash"] = "stale"

    with pytest.raises(GraphContractError) as exc_info:
        GraphIndexState.from_dict(payload)

    assert exc_info.value.code == "INVALID_GRAPH_SCHEMA"
    assert exc_info.value.details["field"] == "symbol_references"


def test_graph_state_rejects_malformed_call_record():
    payload = cast(dict[str, Any], _state().to_dict())
    payload["calls"][0]["raw"]["source_hash"] = "stale"

    with pytest.raises(GraphContractError) as exc_info:
        GraphIndexState.from_dict(payload)

    assert exc_info.value.code == "INVALID_GRAPH_SCHEMA"
    assert exc_info.value.details["field"] == "calls"


def test_graph_state_rejects_non_inline_rust_module_observation():
    payload = _state().to_dict()
    observation = payload["rust_module_observations"][0]
    observation["rust"]["inline"] = False

    with pytest.raises(GraphContractError) as exc_info:
        GraphIndexState.from_dict(payload)

    assert exc_info.value.code == "INVALID_GRAPH_SCHEMA"
    assert exc_info.value.details == {"field": "rust_module_observations"}


def test_graph_state_rejects_old_import_record_shape():
    payload = _state().to_dict()
    del payload["imports"][0]["target_package"]
    del payload["imports"][0]["target_kind"]

    with pytest.raises(GraphContractError) as exc_info:
        GraphIndexState.from_dict(payload)

    assert exc_info.value.code == "INVALID_GRAPH_SCHEMA"
    assert exc_info.value.details["missing"] == ["target_kind", "target_package"]


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("status", []),
        ("target_kind", []),
        ("unresolved_reason", []),
    ],
)
def test_import_record_rejects_non_string_enums(field: str, value: object):
    payload = _resolved_import().to_dict()
    payload[field] = value

    with pytest.raises(GraphContractError) as exc_info:
        ImportRecord.from_dict(payload)

    assert exc_info.value.code == "INVALID_GRAPH_SCHEMA"
    assert exc_info.value.details["field"] == field


def test_graph_state_rejects_invalid_input_hash():
    payload = _state().to_dict()
    payload["input_hashes"]["../outside.json"] = "not-a-hash"

    with pytest.raises(GraphContractError) as exc_info:
        GraphIndexState.from_dict(payload)

    assert exc_info.value.code == "INVALID_GRAPH_SCHEMA"
    assert exc_info.value.details["field"] == "input_hashes"


def test_graph_diagnostic_rejects_unknown_severity():
    payload = GraphDiagnostic(
        severity="error",
        code="BAD",
        message="Bad graph input",
        source=None,
        details={},
    ).to_dict()
    payload["severity"] = "fatal"

    with pytest.raises(GraphContractError) as exc_info:
        GraphDiagnostic.from_dict(payload)

    assert exc_info.value.code == "INVALID_GRAPH_SCHEMA"


def test_graph_state_rejects_unsafe_profile_source():
    payload = _state().to_dict()
    payload["profiles"][0]["source"] = "../generic.json"

    with pytest.raises(GraphContractError) as exc_info:
        GraphIndexState.from_dict(payload)

    assert exc_info.value.code == "INVALID_GRAPH_PROFILE"
