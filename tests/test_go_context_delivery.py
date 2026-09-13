"""Bounded end-to-end acceptance for the W4.4 Go context slice."""
from __future__ import annotations

from pathlib import Path

import pytest

from benchmarks.typescript_context_corpus import load_corpus
from loci import service
from tests.test_python_context_delivery import (
    CORPUS_ROOT,
    _assert_item_definitions_match_get,
    _assert_packet,
    _assert_required_context,
    _case,
    _edges,
    _indexed_snapshot,
    _items,
    _relation_sources,
)


EVIDENCE_BUDGET = 8192
OUTPUT_BUDGET = 16384


@pytest.fixture
def corpus():
    return load_corpus(CORPUS_ROOT)


def _explore(repo: Path, *, intent: str, seed_id: str, **kwargs) -> dict:
    result = service.explore(
        repo,
        intent=intent,
        seed_ids=[seed_id],
        max_evidence_bytes=EVIDENCE_BUDGET,
        max_output_bytes=OUTPUT_BUDGET,
        **kwargs,
    )
    assert result["usage"]["evidence_bytes"] <= EVIDENCE_BUDGET
    assert result["usage"]["output_bytes"] <= OUTPUT_BUDGET
    return result


def _assert_delivery(repo: Path, result: dict, case: dict, required: set[str]) -> None:
    _assert_packet(repo, result)
    _assert_item_definitions_match_get(repo, result)
    _assert_required_context(
        repo,
        result,
        case,
        required,
        exact_symbol_ids={
            context["id"]
            for context in case["context"]
            if context.get("symbol") and context["id"] in required
        },
    )


def _type_pairs(repo: Path, file: str) -> set[tuple[str | None, str | None, str]]:
    return {
        (record["source_id"], record["target_id"], record["raw"]["relation"])
        for record in service.graph_references(
            repo, file=file, family="type", status="resolved"
        )["items"]
    }


def test_go_alias_generic_contract_delivers_authored_alias_and_constraint_context(tmp_path, corpus):
    case = _case(corpus, "go_alias_generic_contract")
    with _indexed_snapshot(tmp_path, corpus, case["snapshot"]) as repo:
        result = _explore(
            repo,
            intent="type_dependencies",
            seed_id="app/main.go::Build#function",
        )

        assert set(_items(result)) == {
            "app/main.go::Build#function",
            "model/model.go::AliasID#type",
            "model/model.go::Page#type",
            "model/model.go::UserID#type",
            "model/model.go::Number#type",
        }
        assert _edges(result) == {
            ("app/main.go::Build#function", "uses_type", "model/model.go::AliasID#type"),
            ("app/main.go::Build#function", "uses_type", "model/model.go::Page#type"),
            ("app/main.go::Build#function", "uses_type", "model/model.go::UserID#type"),
            ("model/model.go::Page#type", "uses_type", "model/model.go::Number#type"),
        }
        assert any(omission["reason"] == "alternative_path" for omission in result["omissions"])
        _assert_delivery(
            repo, result, case,
            {"entry", "alias", "id", "page", "constraint", "import", "module", "package"},
        )

        pairs = _type_pairs(repo, "model/model.go") | _type_pairs(repo, "app/main.go")
        assert {
            ("app/main.go::Build#function", "model/model.go::AliasID#type", "uses_type"),
            ("app/main.go::Build#function", "model/model.go::Page#type", "uses_type"),
            ("app/main.go::Build#function", "model/model.go::UserID#type", "uses_type"),
            ("model/model.go::AliasID#type", "model/model.go::UserID#type", "uses_type"),
            ("model/model.go::Page#type", "model/model.go::Number#type", "uses_type"),
        } <= pairs
        records = service.graph_references(repo, family="type", status="all")["items"]
        assert not {
            "wrong/model.go::UserID#type",
            "model/model.go::int64#type",
            "model/model.go::int#type",
            "model/model.go::any#type",
            "model/model.go::T#type",
        }.intersection({record["target_id"] for record in records if record["target_id"]})
        assert any(
            record["raw"]["text"] == "T"
            and record["unresolved_reason"] == "type_parameter"
            for record in records
        )


def test_go_explicit_embedding_delivers_struct_and_interface_context(tmp_path, corpus):
    case = _case(corpus, "go_explicit_embedding")
    with _indexed_snapshot(tmp_path, corpus, case["snapshot"]) as repo:
        result = _explore(
            repo,
            intent="dependencies",
            seed_id="app/main.go::Start#function",
        )

        assert set(_items(result)) == {
            "app/main.go::Start#function",
            "model/model.go::Entity#type",
            "model/model.go::Audit#type",
            "model/model.go::Combined#type",
            "model/model.go::Runner#type",
        }
        assert _edges(result) == {
            ("app/main.go::Start#function", "uses_type", "model/model.go::Entity#type"),
            ("app/main.go::Start#function", "uses_type", "model/model.go::Combined#type"),
            ("model/model.go::Entity#type", "embeds", "model/model.go::Audit#type"),
            ("model/model.go::Combined#type", "embeds", "model/model.go::Runner#type"),
        }
        _assert_delivery(
            repo, result, case,
            {"entry", "entity", "audit", "combined", "runner", "import", "module", "package"},
        )

        records = service.graph_references(
            repo, file="model/model.go", family="type", status="resolved"
        )["items"]
        assert {
            (record["source_id"], record["target_id"], record["raw"]["relation"], record["raw"]["context"])
            for record in records
        } >= {
            ("model/model.go::Entity#type", "model/model.go::Audit#type", "embeds", "struct_embedding"),
            ("model/model.go::Combined#type", "model/model.go::Runner#type", "embeds", "interface_embedding"),
        }
        calls = service.graph_calls(repo, file="app/main.go", status="all")["items"]
        stamp = [call for call in calls if call["raw"]["callee_text"] == "e.Stamp"]
        assert stamp and all(call["target_id"] is None for call in stamp)


def test_go_known_api_impact_delivers_incoming_callers_only(tmp_path, corpus):
    case = _case(corpus, "go_known_api_impact")
    with _indexed_snapshot(tmp_path, corpus, case["snapshot"]) as repo:
        impact = _explore(
            repo,
            intent="impact",
            seed_id="api/api.go::Handle#function",
        )
        assert set(_items(impact)) == {
            "api/api.go::Handle#function",
            "cmd/server/main.go::Serve#function",
            "cmd/worker/main.go::Work#function",
        }
        assert _edges(impact) == {
            ("cmd/server/main.go::Serve#function", "calls", "api/api.go::Handle#function"),
            ("cmd/worker/main.go::Work#function", "calls", "api/api.go::Handle#function"),
        }
        assert all(relation["traversed"] == "reverse" for relation in impact["relationships"])
        assert "api/api.go::Request#type" not in _items(impact)
        for relation in impact["relationships"]:
            assert {source["file"] for source in _relation_sources(impact, relation)} >= {
                "api/api.go",
            }
        _assert_delivery(
            repo, impact, case,
            {"entry", "serve", "work", "server_import", "worker_import", "module", "package"},
        )

        request = _explore(
            repo,
            intent="type_dependencies",
            seed_id="api/api.go::Handle#function",
        )
        assert set(_items(request)) == {
            "api/api.go::Handle#function",
            "api/api.go::Request#type",
        }
        assert _edges(request) == {
            ("api/api.go::Handle#function", "uses_type", "api/api.go::Request#type"),
        }
        _assert_delivery(repo, request, case, {"entry", "request", "package"})


def test_go_unproven_package_uses_never_guess_and_module_change_invalidates_proof(tmp_path, corpus):
    case = _case(corpus, "go_unproven_package_uses")
    with _indexed_snapshot(tmp_path, corpus, case["snapshot"]) as repo:
        keep = _explore(
            repo,
            intent="type_dependencies",
            seed_id="cmd/main.go::Keep#function",
        )
        assert set(_items(keep)) == {
            "cmd/main.go::Keep#function",
            "model/model.go::Request#type",
        }
        assert _edges(keep) == {
            ("cmd/main.go::Keep#function", "uses_type", "model/model.go::Request#type"),
        }
        _assert_delivery(
            repo, keep, case,
            {"entry", "request", "imports", "module", "package"},
        )

        type_records = service.graph_references(
            repo, file="cmd/main.go", family="type", status="all"
        )["items"]
        keep_ref = next(record for record in type_records if record["source_id"] == "cmd/main.go::Keep#function")
        assert keep_ref["target_id"] == "model/model.go::Request#type"
        symbol_records = service.graph_references(
            repo, file="cmd/main.go", family="symbol", status="all"
        )["items"]
        assert any(
            record["raw"]["text"] == "api.Request"
            and record["target_id"] == "model/model.go::Request#type"
            for record in symbol_records
        )

        calls = service.graph_calls(repo, file="cmd/main.go", status="all")["items"]
        disputed = {
            call["raw"]["callee_text"]: call
            for call in calls
            if call["raw"]["callee_text"] in {"api.Handle", "shared.Open", "fmt.Println", "api.Absent"}
        }
        assert set(disputed) == {"api.Handle", "shared.Open", "fmt.Println", "api.Absent"}
        assert all(call["status"] == "unresolved" for call in disputed.values())
        assert all(call["target_id"] is None and call["target_file"] is None for call in disputed.values())

        for seed_id in ("cmd/main.go::Probe#function", "cmd/main.go::Missing#function"):
            unresolved = _explore(repo, intent="dependencies", seed_id=seed_id)
            assert set(_items(unresolved)) == {seed_id}
            assert not unresolved["relationships"]
            _assert_packet(repo, unresolved)

        module = repo / "go.mod"
        module.write_text(
            module.read_text(encoding="utf-8").replace(
                "module example.com/acme", "module example.com/other"
            ),
            encoding="utf-8",
        )
        invalidated = _explore(
            repo,
            intent="type_dependencies",
            seed_id="cmd/main.go::Keep#function",
            ensure_fresh=True,
        )
        assert set(_items(invalidated)) == {"cmd/main.go::Keep#function"}
        assert not invalidated["relationships"]
        assert "model/model.go::Request#type" not in _items(invalidated)
        assert any(omission["reason"] == "unresolved_relation" for omission in invalidated["omissions"])
        _assert_packet(repo, invalidated)
