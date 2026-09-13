"""Rust type origin, namespace, freshness and persisted proof boundaries."""
from dataclasses import replace

import pytest

from loci import service
from loci.graph._type_validation import validate_type_records
from loci.graph.contracts import GraphContractError
from tests.test_go_type_resolution import _repo, _records


CARGO = '[package]\nname = "contracts"\nversion = "0.1.0"\nedition = "2021"\n'


def test_rust_trait_positions_do_not_bind_same_name_structs_or_generic_parameters(tmp_path):
    with _repo(tmp_path, {
        "Cargo.toml": CARGO,
        "src/lib.rs": '''pub struct Bound;
pub trait Real {}
pub struct Item;
pub fn bad<T: Bound>(x: T) {}
pub fn good<T: Real>(x: T) {}
pub fn shadow<Real>(x: Real) {}
impl Bound for Item {}
impl Real for Item {}
''',
        "wrong.rs": "pub trait Bound {}\npub struct Real;\n",
    }) as repo:
        records = _records(repo, "src/lib.rs")
        bounds = [r for r in records if r["raw"]["text"] == "Bound"]
        assert bounds and all(r["status"] == "unresolved" and r["unresolved_reason"] == "unsupported_target" for r in bounds)
        assert any(r["target_id"] == "src/lib.rs::Real#trait" and r["source_id"] == "src/lib.rs::good#function" for r in records)
        shadow = [r for r in records if r["source_id"] == "src/lib.rs::shadow#function"]
        assert shadow and all(r["target_id"] is None and r["unresolved_reason"] == "type_parameter" for r in shadow)
        assert not any((r["target_file"] or "").startswith("wrong") for r in records)


def test_rust_conditional_authored_items_remain_possible_and_alternatives_ambiguous(tmp_path):
    with _repo(tmp_path, {
        "Cargo.toml": CARGO,
        "src/lib.rs": '''#[cfg(feature = "a")]
pub struct Item;
pub fn use_it(x: Item) {}
#[cfg(feature = "a")]
pub struct Choice;
#[cfg(not(feature = "a"))]
pub struct Choice;
pub fn choose(x: Choice) {}
''',
    }) as repo:
        records = _records(repo, "src/lib.rs")
        item = next(r for r in records if r["raw"]["text"] == "Item")
        assert item["status"] == "resolved" and item["resolution_configuration"] == "declared_possible"
        choices = [r for r in records if r["raw"]["text"] == "Choice"]
        assert choices and all(r["target_id"] is None for r in choices)


def test_rust_imported_alias_target_and_source_edits_refresh_exact_contracts(tmp_path):
    with _repo(tmp_path, {
        "Cargo.toml": CARGO,
        "src/lib.rs": "pub mod model;\nuse model::Alias;\npub fn use_it(x: Alias) -> Alias { x }\n",
        "src/model.rs": "pub struct Item;\npub type Alias = Item;\n",
        "wrong.rs": "pub type Alias = u64;\n",
    }) as repo:
        records = _records(repo, "src/lib.rs")
        assert len(records) == 2 and all(r["target_id"] == "src/model.rs::Alias#type" for r in records)
        old_hash = records[0]["raw"]["source_hash"]
        (repo / "src/model.rs").write_text("pub struct Item;\npub type Renamed = Item;\n")
        assert all(r["target_id"] is None for r in _records(repo, "src/lib.rs"))
        (repo / "src/lib.rs").write_text("pub mod model;\nuse model::Renamed;\npub fn use_it(x: Renamed) -> Renamed { x }\n")
        changed = _records(repo, "src/lib.rs")
        assert all(r["target_id"] == "src/model.rs::Renamed#type" and r["raw"]["source_hash"] != old_hash for r in changed)


def test_rust_replay_rejects_type_target_or_configuration_without_matching_reference(tmp_path):
    with _repo(tmp_path, {
        "Cargo.toml": CARGO,
        "src/lib.rs": "pub mod model;\nuse model::Item;\npub fn use_it(x: Item) {}\n",
        "src/model.rs": "pub struct Item;\n",
        "wrong.rs": "pub struct Item;\n",
    }) as repo:
        _, nodes, state = service._load_graph_context(repo, ensure_fresh=False)
        record = next(r for r in state.type_relations if r.status == "resolved")
        file_hashes = {n["file_path"]: n["content_hash"] for n in nodes.values() if n["kind"] == "file"}
        for tampered in (
            replace(record, target_id="wrong.rs::Item#struct", target_file="wrong.rs", candidate_ids=("wrong.rs::Item#struct",)),
            replace(record, resolution_configuration="declared_possible"),
        ):
            with pytest.raises(GraphContractError, match="does not match"):
                validate_type_records(
                    [tampered], imports=state.imports, exports=state.exports,
                    indexed_nodes=nodes, file_hashes=file_hashes, input_hashes=state.input_hashes,
                    symbol_references=state.symbol_references,
                )


def test_rust_associated_type_does_not_leak_into_bare_module_scope(tmp_path):
    with _repo(tmp_path, {
        "Cargo.toml": CARGO,
        "src/lib.rs": '''pub struct Item;
pub trait Trait { type Out; }
impl Trait for Item { type Out = Item; }
pub fn leak(x: Out) {}
''',
    }) as repo:
        records = _records(repo, "src/lib.rs")
        leak = next(r for r in records if r["source_id"] == "src/lib.rs::leak#function")
        assert leak["target_id"] is None and leak["unresolved_reason"] == "binding_not_found"
        assert any(r["source_id"] == "src/lib.rs::Item.Out#type" and r["target_id"] == "src/lib.rs::Item#struct" for r in records)


def test_rust_local_contract_inherits_external_module_configuration(tmp_path):
    with _repo(tmp_path, {
        "Cargo.toml": CARGO,
        "src/lib.rs": '#[cfg(feature = "a")]\npub mod api;\n',
        "src/api.rs": 'pub struct Item;\npub fn use_it(x: Item) {}\n',
    }) as repo:
        record = _records(repo, "src/api.rs")[0]
        assert record["target_id"] == "src/api.rs::Item#struct"
        assert record["resolution_configuration"] == "declared_possible"
        assert any(s["kind"] == "module_declaration" and s["file"] == "src/lib.rs" for s in record["support"])
        (repo / "src/lib.rs").write_text("pub mod api;\n")
        assert _records(repo, "src/api.rs")[0]["resolution_configuration"] == "unconditional"


def test_rust_unowned_file_keeps_local_contract_outside_declared_module_proof(tmp_path):
    with _repo(tmp_path, {
        "Cargo.toml": CARGO,
        "src/lib.rs": "pub struct Real;\n",
        "wrong.rs": "pub struct Ghost;\npub fn use_it(x: Ghost) {}\n",
    }) as repo:
        record = _records(repo, "wrong.rs")[0]
        assert record["source_id"] == "wrong.rs::use_it#function"
        assert record["target_id"] is None
        assert record["unresolved_reason"] == "unsupported_configuration"
