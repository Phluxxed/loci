"""Source-grounded W2.3 acceptance across extraction, resolution and persistence."""
from __future__ import annotations

from dataclasses import replace
import hashlib
import json
from pathlib import Path

import pytest

from loci import service
from loci.graph.contracts import GRAPH_STATE_SCHEMA_VERSION, GraphContractError
from loci.storage.index_store import IndexStore
from tests.reproductions.typescript_context_gaps import fixtures


def _setup(tmp_path, monkeypatch, files):
    repo = tmp_path / "repo"
    repo.mkdir()
    base = tmp_path / "store"
    monkeypatch.setenv("LOCI_BASE_DIR", str(base))
    for name, source in files.items():
        path = repo / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(source, encoding="utf-8")
    service.index_repo(repo, incremental=False)
    return repo, IndexStore(base_dir=base)


def _state(repo, store):
    index = store.load(repo)
    assert index is not None
    return index, store.validate_graph_state(index)


def _edges(state):
    return {(edge.from_id, edge.type, edge.to_id) for edge in state.edges
            if edge.type in {"uses_type", "extends", "implements"}}


def _id(file, name, kind):
    return f"{file}.ts::{name}#{kind}"


def _expected(case):
    f = _id("consumer", "processOrder", "function")
    payload = _id("types", "Payload", "interface")
    if case in {"imported_interface", "same_name_wrong_file", "named_type_reexport_chain"}:
        return {(f, "uses_type", payload)}
    if case == "local_interface":
        return {(f, "uses_type", _id("consumer", "Payload", "interface"))}
    if case in {"local_alias_chain", "imported_alias_chain"}:
        origin = "consumer" if case.startswith("local") else "types"
        first, second = (_id(origin, name, "type") for name in ("First", "Second"))
        return {(f, "uses_type", second), (second, "uses_type", first),
                (first, "uses_type", _id(origin, "Payload", "interface"))}
    if case in {"local_heritage", "imported_heritage"}:
        origin = "consumer" if case.startswith("local") else "types"
        contract = _id(origin, "Contract", "interface")
        processor = _id("consumer", "Processor", "class")
        return {(_id("consumer", "ChildContract", "interface"), "extends", contract),
                (processor, "extends", _id(origin, "Base", "class")),
                (processor, "implements", contract)}
    return set()


@pytest.mark.parametrize("case", list(fixtures()))
def test_frozen_source_cases_have_exact_type_edges_and_retain_negative_outcomes(tmp_path, monkeypatch, case):
    source = fixtures()[case]["files"]
    repo, store = _setup(tmp_path, monkeypatch, source)
    index, state = _state(repo, store)
    assert state.schema_version == GRAPH_STATE_SCHEMA_VERSION
    assert _edges(state) == _expected(case)
    assert not state.diagnostics
    for record in state.type_relations:
        raw = record.raw
        assert source[raw.source_file].encode()[raw.start_byte:raw.end_byte].decode() == raw.text
        assert raw.owner.start_byte <= raw.start_byte < raw.end_byte <= raw.owner.end_byte
        if record.status == "resolved":
            assert record.candidate_ids == (record.target_id,)
            assert record.candidates_complete and not record.candidates_truncated
            assert {item.kind for item in record.support} >= {"type_site", "owner", "definition"}
    if case == "generic_shadow":
        assert len(state.type_relations) == 2
        assert {record.unresolved_reason for record in state.type_relations} == {"type_parameter"}
    if case == "ambiguous_star_exports":
        record, = state.type_relations
        assert record.unresolved_reason == "ambiguous_target"
        assert not record.candidates_complete
        assert record.target_id is None
    # The existing imported reference keeps its file-owned meaning.
    if case == "imported_interface":
        reference, = state.symbol_references
        assert reference.source_id == "consumer.ts::__file__#file"
        assert reference.target_id == "types.ts::Payload#interface"


def test_noop_roundtrip_preserves_records_and_repeated_sites(tmp_path, monkeypatch):
    repo, store = _setup(tmp_path, monkeypatch, {
        "a.ts": "interface Payload { id: string }; function f(x: Payload): Payload { return x; }\n",
    })
    before, state = _state(repo, store)
    assert len(state.type_relations) == 2
    assert len(_edges(state)) == 1
    result = service.index_repo(repo, incremental=True)
    after, reloaded = _state(repo, store)
    assert result["files_skipped"] == 1
    assert state.to_dict() == reloaded.to_dict()
    assert before["symbols"] == after["symbols"]
    assert len({record.raw.start_byte for record in reloaded.type_relations}) == 2


def test_changed_target_removed_target_and_changed_owner_refresh_real_records(tmp_path, monkeypatch):
    repo, store = _setup(tmp_path, monkeypatch, fixtures()["imported_interface"]["files"])
    before, state = _state(repo, store)
    raw = state.type_relations[0].raw
    target = repo / "types.ts"
    target.write_text("export interface Payload { changed: boolean; }\n")
    service.index_repo(repo, incremental=True)
    _, changed = _state(repo, store)
    record, = changed.type_relations
    assert record.raw == raw
    assert next(s.content_hash for s in record.support if s.kind == "definition") == hashlib.sha256(target.read_bytes()).hexdigest()
    target.unlink()
    service.index_repo(repo, incremental=True)
    _, removed = _state(repo, store)
    assert removed.type_relations[0].raw == raw
    assert removed.type_relations[0].status == "unresolved"
    assert not _edges(removed)
    target.write_text("export interface Payload { restored: string; }\n")
    consumer = repo / "consumer.ts"
    consumer.write_text(consumer.read_text().replace("processOrder", "processAdjusted"))
    service.index_repo(repo, incremental=True)
    _, restored = _state(repo, store)
    assert _edges(restored) == {("consumer.ts::processAdjusted#function", "uses_type", "types.ts::Payload#interface")}
    assert all("processOrder" not in edge.from_id for edge in restored.edges)


def test_configuration_change_reresolves_unchanged_observation_and_control_hash(tmp_path, monkeypatch):
    config = {"compilerOptions": {"baseUrl": ".", "paths": {"@payload": ["./left.ts"]}}}
    repo, store = _setup(tmp_path, monkeypatch, {
        "consumer.ts": 'import type { Payload } from "@payload"; export function f(p: Payload) {}\n',
        "left.ts": "export interface Payload { left: string; }\n",
        "right.ts": "export interface Payload { right: number; }\n",
        "tsconfig.json": json.dumps(config),
    })
    _, before = _state(repo, store)
    record, = before.type_relations
    assert record.target_id == "left.ts::Payload#interface"
    assert record.resolution_controls
    config["compilerOptions"]["paths"]["@payload"] = ["./right.ts"]
    (repo / "tsconfig.json").write_text(json.dumps(config))
    service.index_repo(repo, incremental=True)
    _, after = _state(repo, store)
    current, = after.type_relations
    assert current.raw == record.raw
    assert current.target_id == "right.ts::Payload#interface"
    assert current.resolution_controls != record.resolution_controls
    assert all(after.input_hashes[item.file] == item.content_hash for item in current.resolution_controls)


def test_persisted_forged_target_support_and_candidate_metadata_are_rejected(tmp_path, monkeypatch):
    repo, store = _setup(tmp_path, monkeypatch, fixtures()["same_name_wrong_file"]["files"])
    index, state = _state(repo, store)
    record, = state.type_relations
    forged = replace(record, target_id="wrong.ts::Payload#interface", target_file="wrong.ts",
                     candidate_ids=("wrong.ts::Payload#interface",),
                     support=tuple(replace(item, file="wrong.ts", endpoint_id="wrong.ts::Payload#interface",
                                           content_hash=index["file_hashes"]["wrong.ts"])
                                   if item.kind == "definition" else item for item in record.support))
    tampered = dict(index, graph=replace(state, type_relations=(forged,)).to_dict())
    with pytest.raises(GraphContractError, match="binding evidence"):
        store.validate_graph_state(tampered)
    tampered = json.loads(json.dumps(index))
    tampered["graph"]["type_relations"][0]["candidates_complete"] = False
    with pytest.raises(GraphContractError, match="persisted type relation"):
        store.validate_graph_state(tampered)
    tampered = json.loads(json.dumps(index))
    tampered["graph"]["schema_version"] -= 1
    with pytest.raises(GraphContractError, match="schema version"):
        store.validate_graph_state(tampered)


def test_real_heritage_refreshes_after_configuration_target_and_owner_changes(tmp_path, monkeypatch):
    config = {"compilerOptions": {"baseUrl": ".", "paths": {"@contracts": ["./left.ts"]}}}
    declarations = "export class Base {}; export interface Contract { id: string }\n"
    repo, store = _setup(tmp_path, monkeypatch, {
        "consumer.ts": 'import { Base, Contract } from "@contracts";\n'
                       'export class Processor extends Base implements Contract {}\n'
                       'export interface Child extends Contract {}\n',
        "left.ts": declarations, "right.ts": declarations,
        "tsconfig.json": json.dumps(config),
    })
    _, initial = _state(repo, store)
    assert len(_edges(initial)) == 3
    assert {r.target_file for r in initial.type_relations} == {"left.ts"}
    config["compilerOptions"]["paths"]["@contracts"] = ["./right.ts"]
    (repo / "tsconfig.json").write_text(json.dumps(config))
    service.index_repo(repo, incremental=True)
    _, redirected = _state(repo, store)
    assert [r.raw for r in redirected.type_relations] == [r.raw for r in initial.type_relations]
    assert len(_edges(redirected)) == 3
    assert {r.target_file for r in redirected.type_relations} == {"right.ts"}
    assert redirected.type_relations[0].resolution_controls != initial.type_relations[0].resolution_controls
    (repo / "right.ts").unlink()
    service.index_repo(repo, incremental=True)
    _, removed = _state(repo, store)
    assert all(r.status == "unresolved" for r in removed.type_relations)
    assert not _edges(removed)
    (repo / "right.ts").write_text(declarations.replace("id: string", "id: number"))
    consumer = repo / "consumer.ts"
    consumer.write_text(consumer.read_text().replace("Processor", "Revised"))
    service.index_repo(repo, incremental=True)
    index, restored = _state(repo, store)
    assert _edges(restored) == {
        ("consumer.ts::Revised#class", "extends", "right.ts::Base#class"),
        ("consumer.ts::Revised#class", "implements", "right.ts::Contract#interface"),
        ("consumer.ts::Child#interface", "extends", "right.ts::Contract#interface"),
    }
    assert all(s.content_hash == index["file_hashes"][s.file]
               for r in restored.type_relations for s in r.support)


def test_persisted_missing_type_edge_is_rejected_and_rebuilt(tmp_path, monkeypatch):
    repo, store = _setup(tmp_path, monkeypatch, {
        "a.ts": "interface Payload {}; function f(x: Payload) {}\n",
    })
    index, state = _state(repo, store)
    index["graph"]["edges"] = [edge for edge in index["graph"]["edges"] if edge["type"] != "uses_type"]
    with pytest.raises(GraphContractError, match="complete record projection"):
        store.validate_graph_state(index)
    store._index_path(repo).write_text(json.dumps(index))
    result = service.index_repo(repo, incremental=True)
    assert result["graph_status"] == "healthy"
    assert _edges(_state(repo, store)[1]) == _edges(state)


def test_recursive_type_and_heritage_cycles_are_bounded_authored_relations(tmp_path, monkeypatch):
    repo, store = _setup(tmp_path, monkeypatch, {
        "a.ts": "interface Node { next: Node }; interface A extends B {}; interface B extends A {}; class C extends C {}\n",
    })
    _, state = _state(repo, store)
    assert ("a.ts::Node#interface", "uses_type", "a.ts::Node#interface") in _edges(state)
    assert ("a.ts::A#interface", "extends", "a.ts::B#interface") in _edges(state)
    assert ("a.ts::B#interface", "extends", "a.ts::A#interface") in _edges(state)
    self_heritage = [record for record in state.type_relations if record.source_id == "a.ts::C#class"]
    assert self_heritage[0].unresolved_reason == "self_heritage"
    found = service.graph_paths(repo, ["a.ts::A#interface"], ["a.ts::B#interface"],
                                edge_types=["extends"], max_hops=3, ensure_fresh=True)
    assert len(found["paths"]) == 1
    assert len(found["paths"][0]["steps"]) == 1
