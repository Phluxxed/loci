from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from loci import service
from loci.type_context import TypeContextLimits, expand_type_context


@pytest.fixture
def indexed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("LOCI_BASE_DIR", str(tmp_path / "store"))

    def create(files: dict[str, str]) -> Path:
        repo = tmp_path / "repo"
        repo.mkdir()
        for name, text in files.items():
            path = repo / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text)
        service.index_repo(repo, incremental=False)
        return repo

    return create


def context(repo: Path, ids: list[str], **limits):
    roots = service.get_symbols(repo, ids)
    store, nodes, state = service._load_graph_context(repo, ensure_fresh=False)
    return expand_type_context(repo, store, nodes, state, roots, limits=TypeContextLimits(**limits))


def simple_repo(indexed):
    return indexed({
        "types.ts": "export interface Payload { value: string; }\n",
        "consumer.ts": 'import type { Payload } from "./types";\n'
        "export function first(x: Payload): string { return x.value; }\n"
        "export function second(x: Payload): string { return x.value; }\n",
    })


def test_second_declaration_uses_its_new_declared_type_record(indexed):
    repo = simple_repo(indexed)
    result = context(repo, ["consumer.ts::second#function"])
    assert result["status"] == "complete"
    assert [symbol["id"] for symbol in result["symbols"]] == ["types.ts::Payload#interface"]
    assert result["symbols"][0]["source"] == "interface Payload { value: string; }"
    reference = result["references"][0]
    assert reference["owner_id"] == "consumer.ts::second#function"
    assert reference["edge"]["from"] == "consumer.ts::second#function"
    assert reference["edge"]["type"] == "uses_type"
    assert reference["edge"]["evidence"]["line"] == 3
    raw = (repo / "consumer.ts").read_bytes()
    span = reference["reference"]
    assert raw[span["start_byte"]:span["end_byte"]] == b"Payload"
    assert span["start_byte"] > raw.index(b"function second")
    assert any(item["file"] == "consumer.ts" and item["start_line"] == 1 for item in result["evidence"])


def test_legacy_record_still_retains_original_collapsed_edge_identity(indexed):
    repo = simple_repo(indexed)
    roots = service.get_symbols(repo, ["consumer.ts::second#function"])
    store, nodes, state = service._load_graph_context(repo, ensure_fresh=False)
    result = expand_type_context(repo, store, nodes, replace(state, type_relations=()), roots)
    reference, = result["references"]
    assert result["scope"] == "existing_imported_type_references"
    assert reference["owner_id"] == "consumer.ts::second#function"
    assert reference["edge"]["from"] == "consumer.ts::__file__#file"
    assert reference["edge"]["evidence"]["line"] == 2
    assert reference["edge"]["type"] == "references_type"


def test_reexport_support_and_deduplication_are_deterministic(indexed):
    repo = indexed({
        "types.ts": "export interface Payload { value: string; }\n",
        "wrong.ts": "export interface Payload { wrong: boolean; }\n",
        "barrel.ts": 'export type { Payload as Public } from "./types";\n',
        "consumer.ts": 'import type { Public as Input } from "./barrel";\n'
        "export function a(x: Input): Input { return x; }\n"
        "export function b(x: Input): Input { return x; }\n",
    })
    a, b = "consumer.ts::a#function", "consumer.ts::b#function"
    first = context(repo, [b, a, a])
    second = context(repo, [a, b])
    assert first["symbols"] == second["symbols"]
    assert first["references"] == second["references"]
    assert len(first["symbols"]) == 1
    assert len(first["references"]) == 2
    assert first["symbols"][0]["id"] == "types.ts::Payload#interface"
    keys = [(item["file"], item["start_line"]) for item in first["evidence"]]
    assert len(keys) == len(set(keys))
    assert ("barrel.ts", 1) in keys


def test_parent_excludes_nested_declaration_type_references(indexed):
    repo = indexed({
        "types.ts": "export interface Secret { value: string; }\n",
        "consumer.ts": 'import type { Secret } from "./types";\n'
        "export function outer() { function inner(x: Secret): Secret { return x; } return 1; }\n",
    })
    parent = context(repo, ["consumer.ts::outer#function"])
    assert not parent["symbols"] and not parent["references"]
    assert parent["omissions"]["nested_owner"] == 2
    inner = next(symbol["id"] for file in service.outline_repo(repo)
                 for symbol in file["symbols"] if symbol["name"] == "inner")
    assert context(repo, [inner])["symbols"][0]["id"] == "types.ts::Secret#interface"


@pytest.mark.parametrize(("body", "target"), [
    ('import type { Payload } from "./types";\nexport function f<Payload>(x: Payload): Payload { return x; }\n', None),
    ('interface Local { value: string; }\nexport function f(x: Local): Local { return x; }\n', "consumer.ts::Local#interface"),
    ('import { Payload } from "./types";\nexport function f(x: Payload): Payload { return x; }\n', "types.ts::Payload#interface"),
])
def test_new_local_and_ordinary_import_types_resolve_while_generics_remain_unresolved(indexed, body, target):
    repo = indexed({"types.ts": "export interface Payload { value: string; }\n", "consumer.ts": body})
    result = context(repo, ["consumer.ts::f#function"])
    assert [item["id"] for item in result["symbols"]] == ([target] if target else [])
    assert [item["target_id"] for item in result["references"]] == ([target] if target else [])
    assert result["scope"] == "declared_type_relations"


def test_ambiguous_exports_remain_unresolved(indexed):
    repo = indexed({
        "a.ts": "export interface Payload { a: string; }\n",
        "b.ts": "export interface Payload { b: string; }\n",
        "barrel.ts": 'export * from "./a";\nexport * from "./b";\n',
        "consumer.ts": 'import type { Payload } from "./barrel";\nexport function f(x: Payload) { return x; }\n',
    })
    result = context(repo, ["consumer.ts::f#function"])
    assert not result["symbols"] and not result["references"]
    assert result["omissions"]["unresolved_reference"] == 1


def test_cycles_terminate_and_hop_limit_is_explicit(indexed):
    repo = indexed({
        "a.ts": 'import type { B } from "./b";\nexport interface A { child: B; }\n',
        "b.ts": 'import type { A } from "./a";\nexport interface B { parent: A; }\n',
        "consumer.ts": 'import type { A } from "./a";\nexport function f(x: A) { return x; }\n',
    })
    result = context(repo, ["consumer.ts::f#function"])
    assert [symbol["id"] for symbol in result["symbols"]] == ["a.ts::A#interface", "b.ts::B#interface"]
    assert len(result["references"]) == 3
    assert result["status"] == "complete"
    bounded = context(repo, ["consumer.ts::f#function"], max_hops=1)
    assert len(bounded["symbols"]) == 1
    assert bounded["omissions"]["hop_limit"] == 1


def test_already_delivered_nonanchor_can_be_reached_and_expanded(indexed):
    repo = indexed({
        "a.ts": 'import type { B } from "./b";\nexport function f(x: B) { return x; }\n',
        "b.ts": 'import type { C } from "./c";\nexport interface B { child: C; }\n',
        "c.ts": "export interface C { value: string; }\n",
    })
    result = context(repo, ["a.ts::f#function", "b.ts::B#interface"], max_anchors=1)
    assert [symbol["id"] for symbol in result["symbols"]] == ["c.ts::C#interface"]
    assert len(result["references"]) == 2
    assert result["omissions"] == {"anchor_limit": 1}


@pytest.mark.parametrize(("limits", "reason"), [
    ({"max_nodes": 1}, "node_limit"),
    ({"max_references": 0}, "reference_limit"),
    ({"max_neighbors_per_owner": 0}, "neighbor_limit"),
    ({"max_hops": 0}, "hop_limit"),
    ({"max_source_spans": 2}, "source_spans"),
    ({"max_serialized_bytes": 2500}, "serialized_bytes"),
])
def test_budget_exhaustion_withholds_whole_bundle(indexed, limits, reason):
    repo = simple_repo(indexed)
    result = context(repo, ["consumer.ts::second#function"], **limits)
    assert not result["symbols"] and not result["references"] and not result["evidence"]
    assert result["status"] == "partial"
    assert result["omissions"][reason] >= 1


def test_large_first_candidate_does_not_block_later_small_definition(indexed):
    repo = indexed({
        "types.ts": "export interface Big { " + "x: string; " * 150 + "}\nexport interface Small { ok: boolean; }\n",
        "consumer.ts": 'import type { Big, Small } from "./types";\nexport function f(x: Big, y: Small) { return y; }\n',
    })
    result = context(repo, ["consumer.ts::f#function"], max_source_bytes=600)
    assert [symbol["id"] for symbol in result["symbols"]] == ["types.ts::Small#interface"]
    assert result["omissions"]["source_bytes"] == 1


def test_exact_roots_have_priority_and_no_anchor_is_explicit(indexed):
    repo = simple_repo(indexed)
    symbol_id = "consumer.ts::second#function"
    root = service.get_symbols(repo, [symbol_id])
    result = context(repo, [symbol_id], max_source_bytes=1)
    assert result["omissions"]["root_budget"] == 1 and not result["symbols"]
    assert service.get_symbols_result(repo, [symbol_id])["symbols"] == root
    file_result = context(repo, ["consumer.ts::__file__#file"])
    assert file_result["omissions"] == {"no_anchor": 1}


def test_missing_graph_leaves_exact_source_and_diagnostics_explicit(indexed, monkeypatch):
    repo = simple_repo(indexed)
    symbol_id = "consumer.ts::second#function"
    exact = service.get_symbols(repo, [symbol_id])

    def missing(*args, **kwargs):
        raise service.LociError("INVALID_GRAPH_SCHEMA", "Persisted graph state is missing", {})

    monkeypatch.setattr(service, "_load_graph_context", missing)
    result = service.get_symbols_result(repo, [symbol_id], include_type_context=True)
    assert result["symbols"] == exact
    assert result["type_context"]["status"] == "unavailable"
    assert result["type_context"]["omissions"] == {"INVALID_GRAPH_SCHEMA": 1}


def test_ambiguous_ownership_and_missing_matching_edge_cannot_deliver(indexed):
    repo = simple_repo(indexed)
    symbol_id = "consumer.ts::second#function"
    roots = service.get_symbols(repo, [symbol_id])
    store, nodes, state = service._load_graph_context(repo, ensure_fresh=False)
    duplicate = {**nodes[symbol_id], "id": "duplicate-owner"}
    tied = expand_type_context(repo, store, {**nodes, duplicate["id"]: duplicate}, state, roots)
    assert tied["omissions"]["ambiguous_owner"] == 1 and not tied["symbols"]
    no_edge = expand_type_context(repo, store, nodes, replace(state, edges=()), roots)
    assert no_edge["omissions"]["edge_unavailable"] == 1 and not no_edge["symbols"]


def test_changed_cached_definition_cannot_be_attached_as_proven_context(indexed):
    repo = simple_repo(indexed)
    roots = service.get_symbols(repo, ["consumer.ts::second#function"])
    store, nodes, state = service._load_graph_context(repo, ensure_fresh=False)
    cached = store._sources_dir(repo) / "types.ts"
    cached.write_text(cached.read_text().replace("string", "number"))
    result = expand_type_context(repo, store, nodes, state, roots)
    assert result["omissions"] == {"source_unavailable": 1}
    assert not result["symbols"] and not result["references"]
    assert roots[0]["source"] == service.get_symbols(repo, [roots[0]["id"]])[0]["source"]
