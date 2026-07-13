from __future__ import annotations

import json
from pathlib import Path

import pytest

from loci.graph.contracts import (
    GRAPH_SCHEMA_VERSION,
    GraphContractError,
    GraphContribution,
    GraphEdge,
    GraphEvidence,
    GraphNodeRef,
)
from loci.graph.profiles import GraphProfile, LoadedGraphProfile
from loci.graph.state import (
    GraphDiagnostic,
    GraphIndexState,
    LoadedGraphContribution,
)


FIXTURES = Path(__file__).parents[1] / "fixtures" / "graph_profiles"


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
        schema_version=GRAPH_SCHEMA_VERSION,
        profiles=(LoadedGraphProfile(
            source=".loci/graph/profiles/generic.json",
            content_hash="b" * 64,
            profile=profile,
        ),),
        nodes=(node,),
        edges=(edge,),
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


def test_empty_graph_state_has_complete_envelope():
    state = GraphIndexState.empty()

    assert state.to_dict() == {
        "schema_version": GRAPH_SCHEMA_VERSION,
        "profiles": [],
        "nodes": [],
        "edges": [],
        "contributions": [],
        "input_hashes": {},
        "diagnostics": [],
    }


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
