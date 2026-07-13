from __future__ import annotations

import pytest

from loci.graph.contracts import GraphContractError, GraphEdge
from loci.graph.traversal import (
    MAX_GRAPH_FILTER_VALUES,
    filter_graph_edges,
    find_graph_paths,
    graph_adjacency,
    graph_hub_threshold,
    graph_relation_terms,
    semantic_bridge_terms,
)


def _edge(
    source: str,
    target: str,
    *,
    namespace: str = "wiki",
    edge_type: str = "links",
    resolution: str = "declared",
    directed: bool = True,
    line: int = 1,
) -> GraphEdge:
    return GraphEdge.from_dict({
        "from": source,
        "to": target,
        "type": edge_type,
        "directed": directed,
        "namespace": namespace,
        "resolution": resolution,
        "evidence": {
            "file": f"{source}.md",
            "line": line,
            "content_hash": "a" * 64,
        },
    })


def test_filter_defaults_exclude_heuristic_edges():
    edges = [
        _edge("a", "b", resolution="exact"),
        _edge("b", "c", resolution="declared"),
        _edge("c", "d", resolution="import-resolved"),
        _edge("d", "e", resolution="heuristic"),
    ]

    filtered = filter_graph_edges(
        edges,
        namespaces=None,
        edge_types=None,
        resolutions=None,
    )

    assert [edge.resolution for edge in filtered] == ["exact", "declared"]


def test_filter_applies_all_allow_lists_and_deduplicates_values():
    keep = _edge("a", "b", namespace="wiki", edge_type="supports")
    edges = [
        keep,
        _edge("b", "c", namespace="code", edge_type="supports"),
        _edge("c", "d", namespace="wiki", edge_type="mentions"),
    ]

    filtered = filter_graph_edges(
        edges,
        namespaces=["wiki", "wiki"],
        edge_types=["supports"],
        resolutions=["declared"],
    )

    assert filtered == (keep,)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("namespaces", []),
        ("edge_types", [""]),
        ("resolutions", ["declared"] * (MAX_GRAPH_FILTER_VALUES + 1)),
    ],
)
def test_filter_rejects_invalid_allow_lists(field: str, value: list[str]):
    arguments = {
        "namespaces": None,
        "edge_types": None,
        "resolutions": None,
    }
    arguments[field] = value

    with pytest.raises(GraphContractError) as raised:
        filter_graph_edges([], **arguments)

    assert raised.value.code == "INVALID_INPUT"


def test_filter_rejects_unknown_resolution():
    with pytest.raises(GraphContractError) as raised:
        filter_graph_edges(
            [],
            namespaces=None,
            edge_types=None,
            resolutions=["trusted"],
        )

    assert raised.value.code == "GRAPH_RESOLUTION_UNSUPPORTED"


def test_adjacency_preserves_forward_and_reverse_orientation():
    edge = _edge("a", "b")

    outgoing = graph_adjacency([edge], direction="outgoing")
    incoming = graph_adjacency([edge], direction="incoming")
    either = graph_adjacency([edge], direction="either")

    assert [(step.to_id, step.traversed) for step in outgoing["a"]] == [
        ("b", "forward")
    ]
    assert [(step.to_id, step.traversed) for step in incoming["b"]] == [
        ("a", "reverse")
    ]
    assert [(step.to_id, step.traversed) for step in either["a"]] == [
        ("b", "forward")
    ]
    assert [(step.to_id, step.traversed) for step in either["b"]] == [
        ("a", "reverse")
    ]
    assert incoming["b"][0].edge.from_id == "a"
    assert incoming["b"][0].edge.to_id == "b"


def test_undirected_edge_is_available_both_ways():
    adjacency = graph_adjacency(
        [_edge("a", "b", directed=False)],
        direction="outgoing",
    )

    assert adjacency["a"][0].traversed == "forward"
    assert adjacency["b"][0].traversed == "reverse"


def test_path_search_is_deterministic_and_avoids_cycles():
    edges = [
        _edge("a", "b"),
        _edge("b", "a"),
        _edge("b", "d"),
        _edge("a", "c"),
        _edge("c", "d"),
    ]

    result = find_graph_paths(
        edges,
        ["a"],
        ["d"],
        direction="outgoing",
        max_hops=3,
        max_nodes=16,
        max_paths=8,
    )

    assert [path.node_ids for path in result.paths] == [
        ("a", "b", "d"),
        ("a", "c", "d"),
    ]
    assert all(len(path.node_ids) == len(set(path.node_ids)) for path in result.paths)


def test_path_search_orders_equal_hops_by_node_priority():
    result = find_graph_paths(
        [_edge("a", "b"), _edge("b", "d"), _edge("a", "c"), _edge("c", "d")],
        ["a"],
        ["d"],
        direction="outgoing",
        max_hops=2,
        max_nodes=16,
        max_paths=8,
        node_priorities={"c": 5.0, "b": 1.0},
    )

    assert [path.node_ids for path in result.paths] == [
        ("a", "c", "d"),
        ("a", "b", "d"),
    ]


def test_path_search_can_reach_one_target_through_another_target():
    result = find_graph_paths(
        [_edge("a", "b"), _edge("b", "c")],
        ["a"],
        ["b", "c"],
        direction="outgoing",
        max_hops=2,
        max_nodes=3,
        max_paths=8,
    )

    assert [path.node_ids for path in result.paths] == [
        ("a", "b"),
        ("a", "b", "c"),
    ]


def test_hop_limit_records_that_deeper_frontier_was_omitted():
    result = find_graph_paths(
        [_edge("a", "b"), _edge("b", "c")],
        ["a"],
        ["c"],
        direction="outgoing",
        max_hops=1,
        max_nodes=8,
        max_paths=8,
    )

    assert result.paths == ()
    assert result.hop_limit_reached is True
    assert result.omitted_paths >= 1


def test_node_limit_stops_frontier_and_records_omission():
    result = find_graph_paths(
        [_edge("a", "b"), _edge("a", "c"), _edge("a", "d")],
        ["a"],
        ["d"],
        direction="outgoing",
        max_hops=1,
        max_nodes=2,
        max_paths=8,
    )

    assert result.node_limit_reached is True
    assert result.examined_nodes == 2
    assert result.omitted_nodes == 2
    assert [path.node_ids for path in result.paths] == [("a", "d")]


def test_path_window_has_deterministic_continuation():
    edges = [
        _edge("a", "b", edge_type="first"),
        _edge("a", "b", edge_type="second", line=2),
        _edge("a", "b", edge_type="third", line=3),
    ]

    first = find_graph_paths(
        edges,
        ["a"],
        ["b"],
        direction="outgoing",
        max_hops=1,
        max_nodes=8,
        max_paths=2,
    )
    second = find_graph_paths(
        edges,
        ["a"],
        ["b"],
        direction="outgoing",
        max_hops=1,
        max_nodes=8,
        max_paths=2,
        path_offset=2,
    )

    assert [path.steps[0].edge.type for path in first.paths] == ["first", "second"]
    assert first.next_path_offset == 2
    assert [path.steps[0].edge.type for path in second.paths] == ["third"]
    assert second.next_path_offset is None


def test_path_window_preserves_deterministic_source_order_across_pages():
    edges = [_edge(source, "target") for source in ("z", "y", "a")]

    first = find_graph_paths(
        edges,
        ["z", "y", "a"],
        ["target"],
        direction="outgoing",
        max_hops=1,
        max_nodes=8,
        max_paths=1,
    )
    second = find_graph_paths(
        edges,
        ["z", "y", "a"],
        ["target"],
        direction="outgoing",
        max_hops=1,
        max_nodes=8,
        max_paths=1,
        path_offset=1,
    )

    assert first.paths[0].node_ids == ("z", "target")
    assert second.paths[0].node_ids == ("y", "target")


def test_path_search_rejects_endpoint_sets_larger_than_node_budget():
    with pytest.raises(GraphContractError) as raised:
        find_graph_paths(
            [],
            ["a"],
            ["b", "c"],
            direction="outgoing",
            max_hops=1,
            max_nodes=2,
            max_paths=1,
        )

    assert raised.value.code == "INVALID_INPUT"


@pytest.mark.parametrize(
    "kwargs",
    [
        {"source_ids": [], "target_ids": ["b"]},
        {"source_ids": ["a"], "target_ids": []},
        {"source_ids": [""], "target_ids": ["b"]},
        {"source_ids": ["a"], "target_ids": ["b"], "direction": "sideways"},
        {"source_ids": ["a"], "target_ids": ["b"], "max_hops": 0},
        {"source_ids": ["a"], "target_ids": ["b"], "max_nodes": 1},
        {"source_ids": ["a"], "target_ids": ["b"], "max_paths": 0},
        {"source_ids": ["a"], "target_ids": ["b"], "path_offset": -1},
    ],
)
def test_path_search_rejects_invalid_requests(kwargs: dict):
    arguments = {
        "source_ids": ["a"],
        "target_ids": ["b"],
        "direction": "outgoing",
        "max_hops": 1,
        "max_nodes": 8,
        "max_paths": 1,
    }
    arguments.update(kwargs)

    with pytest.raises(GraphContractError) as raised:
        find_graph_paths([], **arguments)

    assert raised.value.code == "INVALID_INPUT"


def test_hub_threshold_is_derived_from_filtered_edge_count():
    assert graph_hub_threshold(0) == 4
    assert graph_hub_threshold(24) == 5
    assert graph_hub_threshold(2_000) == 45


def test_semantic_bridge_terms_remove_endpoint_words_and_stem_inflections():
    terms = semantic_bridge_terms(
        "How can an idea incubated in AI Graph Ideas become durable Brain maintenance?",
        "AI Graph Ideas",
        "Brain Steward Handoff Path",
    )

    assert "incubat" in terms
    assert "durable" in terms
    assert "maintenance" in terms
    assert "graph" not in terms
    assert "brain" not in terms


def test_endpoint_only_overlap_does_not_create_semantic_bridge_terms():
    assert semantic_bridge_terms(
        "Does Code Graph RAG connect Recall Efficient Wiki Traversal?",
        "Code Graph RAG",
        "Recall Efficient Wiki Traversal",
    ) == ("connect",)


def test_semantic_terms_normalize_abstract_noun_to_entity_form():
    assert semantic_bridge_terms(
        "What supports faithfulness before connectivity?",
        "Sparse Rule",
        "TACTIC KG Faithful Construction",
    ) == ("support", "before", "connectivity")


def test_relation_terms_keep_predicates_not_generic_evidence_words():
    assert graph_relation_terms(
        "What evidence shows that Code Graph RAG improved traversal?"
    ) == ("improv",)
    assert graph_relation_terms(
        "How can an incubated idea become durable maintenance?"
    ) == ("incubat", "become")
