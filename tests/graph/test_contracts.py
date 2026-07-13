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


PARENT_ID = "guide.md::Guide#section"
CHILD_ID = "guide.md::Guide > Install#section"
CHILD_HASH = "a" * 64


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
