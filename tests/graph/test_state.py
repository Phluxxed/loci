from __future__ import annotations

import json
from pathlib import Path

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
from loci.graph.imports import ImportRecord
from loci.graph.profiles import GraphProfile, LoadedGraphProfile
from loci.graph.state import (
    GraphDiagnostic,
    GraphIndexState,
    LoadedGraphContribution,
)
from loci.parser.imports import RawImport


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
    )


def _resolved_import() -> ImportRecord:
    return ImportRecord(
        raw=_raw_import(),
        source_id="src/example.py::__file__#file",
        target_file="src/package/target.py",
        target_package=None,
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
    )
    return ImportRecord(
        raw=raw,
        source_id="cmd/server/main.go::__file__#file",
        target_file=None,
        target_package="example.com/project/internal/store",
        target_kind="package",
        target_id=(
            "internal/store::example.com/project/internal/store#package"
        ),
        status="resolved",
        unresolved_reason=None,
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
        },
        "source_id": "src/example.py::__file__#file",
        "target_file": "src/package/target.py",
        "target_package": None,
        "target_kind": "file",
        "target_id": "src/package/target.py::__file__#file",
        "status": "resolved",
        "unresolved_reason": None,
        "resolution_basis": None,
        "resolution_control_files": [],
    }
    assert list(serialized) == [
        "raw",
        "source_id",
        "target_file",
        "target_package",
        "target_kind",
        "target_id",
        "status",
        "unresolved_reason",
        "resolution_basis",
        "resolution_control_files",
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
    ]
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
    )
    record = ImportRecord(
        raw=raw,
        source_id="apps/web/src/page.ts::__file__#file",
        target_file="packages/core/src/format.ts",
        target_package=None,
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
        "target_kind",
        "resolution_basis",
        "resolution_control_files",
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


def test_empty_graph_state_has_complete_envelope():
    state = GraphIndexState.empty()

    assert state.to_dict() == {
        "schema_version": GRAPH_STATE_SCHEMA_VERSION,
        "profiles": [],
        "nodes": [],
        "edges": [],
        "imports": [],
        "contributions": [],
        "input_hashes": {},
        "diagnostics": [],
    }


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


def test_graph_state_schema_four_rejects_old_import_record_shape():
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
