from __future__ import annotations

import pytest

from loci import service
from loci.type_context import TypeContextLimits, expand_type_context
from tests.reproductions.typescript_context_gaps import fixtures
from tests.test_type_relation_service import _setup, _state


def test_generic_reference_family_is_paginated_and_old_default_is_unchanged(tmp_path, monkeypatch):
    repo, store = _setup(tmp_path, monkeypatch, {
        "a.ts": "interface Payload { id: string }; function f<T>(x: Payload): T { throw 1; }\n",
    })
    assert service.graph_references(repo) == service.graph_references(repo, family="symbol")
    assert "family" not in service.graph_references(repo)
    first = service.graph_references(repo, family="type", limit=1)
    assert first["family"] == "type" and first["counts"] == {
        "total": 2, "resolved": 1, "unresolved": 1, "returned": 1,
    }
    assert first["pagination"]["next_offset"] == 1
    second = service.graph_references(repo, family="type", offset=1, limit=1)
    assert second["pagination"]["next_offset"] is None
    assert second["items"][0]["unresolved_reason"] == "type_parameter"
    assert second["items"][0]["target_id"] is None
    unresolved = service.graph_references(repo, family="type", status="unresolved", file="a.ts")
    assert unresolved["items"] == second["items"]
    health = service.graph_health(repo)
    assert health["status"] == "healthy"
    assert health["counts"]["graph_type_relations_resolved_by_basis"] == {"lexical_binding": 1}
    assert health["counts"]["graph_type_relations_unresolved_by_reason"] == {"type_parameter": 1}
    for bad in ("other", None, []):
        with pytest.raises(service.LociError, match="family"):
            service.graph_references(repo, family=bad)


def test_direction_evidence_and_budgets_work_through_existing_graph_queries(tmp_path, monkeypatch):
    repo, store = _setup(tmp_path, monkeypatch, fixtures()["local_alias_chain"]["files"])
    source, target = "consumer.ts::processOrder#function", "consumer.ts::Payload#interface"
    outgoing = service.graph_traverse_neighbors(repo, [source], edge_types=["uses_type"], direction="outgoing")
    neighbor, = outgoing["results"][0]["neighbors"]
    assert neighbor["node"]["id"] == "consumer.ts::Second#type"
    assert neighbor["traversed"] == "forward"
    incoming = service.graph_traverse_neighbors(repo, [target], edge_types=["uses_type"], direction="incoming")
    neighbor, = incoming["results"][0]["neighbors"]
    assert neighbor["node"]["id"] == "consumer.ts::First#type"
    assert neighbor["traversed"] == "reverse"
    assert neighbor["edge"]["to"] == target
    paths = service.graph_paths(repo, [source], [target], edge_types=["uses_type"], direction="outgoing")
    path, = paths["paths"]
    assert len(path["steps"]) == 3
    assert all(step["edge"]["resolution"] == "exact" for step in path["steps"])
    assert any("type First = Payload" in step["evidence_span"]["content"] for step in path["steps"])
    consumer = repo / "consumer.ts"
    consumer.write_text(consumer.read_text().replace(
        "export type First = Payload;", "export type First = Payload; // " + "context " * 200,
    ))
    bounded = service.graph_paths(repo, [source], [target], edge_types=["uses_type"],
                                  max_evidence_bytes=1024, ensure_fresh=True)
    assert not bounded["paths"]
    assert bounded["rejected_paths"][0]["reason"] == "EVIDENCE_BUDGET_EXCEEDED"


def test_alias_chain_has_a_typed_semantic_bridge_but_reverse_does_not(tmp_path, monkeypatch):
    repo, store = _setup(tmp_path, monkeypatch, fixtures()["local_alias_chain"]["files"])
    source, target = "consumer.ts::processOrder#function", "consumer.ts::Payload#interface"
    result = service.graph_retrieve(repo, "Which types does processOrder depend on?", [source, target],
                                    edge_types=["uses_type"], direction="outgoing")
    assert any(len(path["steps"]) == 3 for path in result["paths"])
    reverse = service.graph_retrieve(repo, "Which types does Payload depend on?", [target, source],
                                     edge_types=["uses_type"], direction="incoming")
    assert not any(len(path["steps"]) == 3 for path in reverse["paths"])


def test_heritage_paths_do_not_infer_authored_implements_for_a_descendant(tmp_path, monkeypatch):
    repo, store = _setup(tmp_path, monkeypatch, {
        "a.ts": "interface Contract {}\nclass Base implements Contract {}\nclass Child extends Base {}\n",
    })
    _, state = _state(repo, store)
    assert not any(edge.from_id == "a.ts::Child#class" and edge.type == "implements" for edge in state.edges)
    result = service.graph_retrieve(repo, "Which classes implement Contract?",
                                    ["a.ts::Child#class", "a.ts::Contract#interface"],
                                    edge_types=["extends", "implements"], direction="outgoing")
    assert not any(len(path["steps"]) > 1 for path in result["paths"])


def test_opt_in_hydrates_local_alias_chain_and_preserves_exact_roots_and_limits(tmp_path, monkeypatch):
    repo, store = _setup(tmp_path, monkeypatch, fixtures()["local_alias_chain"]["files"])
    source = "consumer.ts::processOrder#function"
    exact = service.get_symbols(repo, [source])
    result = service.get_symbols_result(repo, [source], include_type_context=True)
    assert result["symbols"] == exact
    context = result["type_context"]
    assert context["scope"] == "declared_type_relations"
    assert [item["id"] for item in context["symbols"]] == [
        "consumer.ts::Second#type", "consumer.ts::First#type", "consumer.ts::Payload#interface",
    ]
    assert len(context["references"]) == 3
    _, nodes, state = service._load_graph_context(repo, ensure_fresh=False)
    bounded = expand_type_context(repo, store, nodes, state, exact, limits=TypeContextLimits(max_hops=1))
    assert [item["id"] for item in bounded["symbols"]] == ["consumer.ts::Second#type"]
    assert bounded["omissions"] == {"hop_limit": 1}
    assert service.get_symbols_result(repo, [source]) == {"symbols": exact}
