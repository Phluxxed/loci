"""Bounded end-to-end acceptance for the W4.5 Rust context slice."""
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
)
from tests.test_go_type_resolution import _repo


EVIDENCE_BUDGET = 8192
OUTPUT_BUDGET = 16384


@pytest.fixture
def corpus():
    return load_corpus(CORPUS_ROOT)


def _explore(repo: Path, *, intent: str, seed_ids: list[str], **kwargs) -> dict:
    result = service.explore(
        repo,
        intent=intent,
        seed_ids=seed_ids,
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


def _type_records(repo: Path, file: str) -> list[dict]:
    return service.graph_references(
        repo, file=file, family="type", status="all"
    )["items"]


def _record_sites(records: list[dict]) -> set[tuple[str | None, str | None, str, str]]:
    return {
        (
            record["source_id"],
            record["target_id"],
            record["raw"]["relation"],
            record["raw"]["context"],
        )
        for record in records
        if record["status"] == "resolved"
    }


def test_rust_authored_trait_contract_delivers_impl_sites_and_source_proof(tmp_path, corpus):
    case = _case(corpus, "rust_authored_trait_contract")
    with _indexed_snapshot(tmp_path, corpus, case["snapshot"]) as repo:
        result = _explore(
            repo,
            intent="type_dependencies",
            seed_ids=["src/lib.rs::build#function", "src/lib.rs::Receipt#struct"],
        )

        expected = {
            "src/lib.rs::build#function",
            "src/lib.rs::UserId#type",
            "src/lib.rs::Format#trait",
            "src/lib.rs::Render#trait",
            "src/lib.rs::Receipt#struct",
            "src/lib.rs::Envelope#struct",
        }
        assert expected <= set(_items(result))
        impl_items = [item for item in result["items"] if item["kind"] == "impl"]
        assert len(impl_items) == 2
        assert all(item["id"] not in expected for item in impl_items)

        impl_ids = {
            source["content"]: item["id"]
            for item in impl_items
            for source in result["sources"]
            if source["id"] == item["source_id"]
        }
        contexts = {context["id"]: context for context in case["context"]}
        raw = (repo / "src/lib.rs").read_bytes()
        format_impl = raw[contexts["format_impl"]["start_byte"]:contexts["format_impl"]["end_byte"]].decode()
        render_impl = raw[contexts["render_impl"]["start_byte"]:contexts["render_impl"]["end_byte"]].decode()
        assert set(impl_ids) == {format_impl, render_impl}

        delivered_impl_edges = [
            relation
            for relation in result["relationships"]
            if relation["edge"]["type"] == "impl_self_type"
        ]
        assert {
            relation["edge"]["from"] for relation in delivered_impl_edges
        } == {impl_ids[format_impl], impl_ids[render_impl]}
        assert all(relation["traversed"] == "reverse" for relation in delivered_impl_edges)
        _assert_delivery(
            repo,
            result,
            case,
            {"entry", "id", "format", "render", "receipt", "format_impl", "render_impl", "envelope", "cargo"},
        )

        sites = _record_sites(_type_records(repo, "src/lib.rs"))
        assert {
            ("src/lib.rs::build#function", "src/lib.rs::Render#trait", "uses_type", "constraint"),
            ("src/lib.rs::build#function", "src/lib.rs::UserId#type", "uses_type", "annotation"),
            ("src/lib.rs::build#function", "src/lib.rs::Envelope#struct", "uses_type", "return"),
            ("src/lib.rs::Envelope#struct", "src/lib.rs::Render#trait", "uses_type", "constraint"),
            ("src/lib.rs::Envelope#struct", "src/lib.rs::UserId#type", "uses_type", "property"),
            ("src/lib.rs::Render#trait", "src/lib.rs::Format#trait", "supertrait", "supertrait"),
            ("src/lib.rs::Receipt#struct", "src/lib.rs::UserId#type", "uses_type", "property"),
            (impl_ids[format_impl], "src/lib.rs::Format#trait", "impl_trait", "impl_trait"),
            (impl_ids[format_impl], "src/lib.rs::Receipt#struct", "impl_self_type", "impl_self_type"),
            (impl_ids[render_impl], "src/lib.rs::Render#trait", "impl_trait", "impl_trait"),
            (impl_ids[render_impl], "src/lib.rs::Receipt#struct", "impl_self_type", "impl_self_type"),
        } <= sites
        assert all(record["target_id"] is None for record in _type_records(repo, "src/lib.rs") if record["raw"]["text"] in {"T", "u64", "String"})
        assert not service.graph_calls(repo, file="src/lib.rs", status="resolved")["items"]


def test_rust_contained_optional_reexport_delivers_configuration_and_refreshes_cargo_proof(tmp_path, corpus):
    case = _case(corpus, "rust_contained_optional_reexport")
    with _indexed_snapshot(tmp_path, corpus, case["snapshot"]) as repo:
        result = _explore(
            repo,
            intent="type_dependencies",
            seed_ids=["app/src/lib.rs::use_it#function"],
        )
        assert set(_items(result)) == {
            "app/src/lib.rs::use_it#function",
            "core/src/api.rs::Thing#struct",
        }
        assert _edges(result) == {
            ("app/src/lib.rs::use_it#function", "uses_type", "core/src/api.rs::Thing#struct"),
        }
        assert {
            relation["resolution_configuration"]
            for relation in result["relationships"]
        } == {"declared_possible"}
        _assert_delivery(
            repo, result, case,
            {"entry", "thing", "import", "reexport", "module", "workspace", "core_cargo", "app_cargo"},
        )

        records = _type_records(repo, "app/src/lib.rs")
        assert {
            ("app/src/lib.rs::use_it#function", "core/src/api.rs::Thing#struct"),
        } <= {
            (source_id, target_id)
            for source_id, target_id, relation, context in _record_sites(records)
            if relation == "uses_type" and context in {"annotation", "return"}
        }
        resolved = [record for record in records if record["status"] == "resolved"]
        assert resolved and all(record["resolution_configuration"] == "declared_possible" for record in resolved)
        assert all(record["target_file"] != "wrong.rs" for record in resolved)

        manifest = repo / "app/Cargo.toml"
        manifest.write_text(
            manifest.read_text(encoding="utf-8").replace(", optional = true", ""),
            encoding="utf-8",
        )
        refreshed = _explore(
            repo,
            intent="type_dependencies",
            seed_ids=["app/src/lib.rs::use_it#function"],
            ensure_fresh=True,
        )
        assert _edges(refreshed) == _edges(result)
        assert {
            relation["resolution_configuration"]
            for relation in refreshed["relationships"]
        } == {"unconditional"}
        assert any(
            source["file"] == "app/Cargo.toml" and "optional" not in source["content"]
            for source in refreshed["sources"]
        )
        assert all(
            record["resolution_configuration"] == "unconditional"
            for record in _type_records(repo, "app/src/lib.rs")
            if record["status"] == "resolved"
        )
        _assert_packet(repo, refreshed)


def test_rust_known_call_impact_delivers_incoming_caller_and_type_context(tmp_path, corpus):
    case = _case(corpus, "rust_known_call_impact")
    with _indexed_snapshot(tmp_path, corpus, case["snapshot"]) as repo:
        impact = _explore(
            repo,
            intent="impact",
            seed_ids=["src/api.rs::parse#function"],
        )
        assert set(_items(impact)) == {
            "src/api.rs::parse#function",
            "src/lib.rs::caller#function",
        }
        assert _edges(impact) == {
            ("src/lib.rs::caller#function", "calls", "src/api.rs::parse#function"),
        }
        assert impact["relationships"][0]["resolution_configuration"] == "unconditional"
        assert all(relation["traversed"] == "reverse" for relation in impact["relationships"])
        _assert_delivery(repo, impact, case, {"entry", "caller", "module", "import", "cargo"})

        types = _explore(
            repo,
            intent="type_dependencies",
            seed_ids=["src/api.rs::parse#function"],
        )
        assert set(_items(types)) == {
            "src/api.rs::parse#function",
            "src/api.rs::Config#struct",
        }
        assert _edges(types) == {
            ("src/api.rs::parse#function", "uses_type", "src/api.rs::Config#struct"),
        }
        _assert_delivery(repo, types, case, {"entry", "config", "cargo"})
        sites = _record_sites(_type_records(repo, "src/api.rs") + _type_records(repo, "src/lib.rs"))
        assert {
            ("src/api.rs::parse#function", "src/api.rs::Config#struct", "uses_type", "annotation"),
            ("src/lib.rs::caller#function", "src/api.rs::Config#struct", "uses_type", "annotation"),
        } <= sites


def test_rust_unproven_contracts_never_guess_namespaces_cfg_or_macro_targets(tmp_path, corpus):
    case = _case(corpus, "rust_unproven_contracts")
    with _indexed_snapshot(tmp_path, corpus, case["snapshot"]) as repo:
        result = _explore(
            repo,
            intent="type_dependencies",
            seed_ids=["src/lib.rs::probe#function"],
        )
        assert set(_items(result)) == {
            "src/lib.rs::probe#function",
            "src/model.rs::Thing#struct",
        }
        assert _edges(result) == {
            ("src/lib.rs::probe#function", "uses_type", "src/model.rs::Thing#struct"),
        }
        assert result["relationships"][0]["resolution_configuration"] == "unconditional"
        _assert_delivery(repo, result, case, {"entry", "thing", "imports", "cargo"})

        generic = _explore(
            repo,
            intent="type_dependencies",
            seed_ids=["src/lib.rs::generic#function"],
        )
        assert set(_items(generic)) == {"src/lib.rs::generic#function"}
        assert not generic["relationships"]
        _assert_delivery(repo, generic, case, {"generic"})

        records = _type_records(repo, "src/lib.rs")
        probe_thing = [
            record for record in records
            if record["source_id"] == "src/lib.rs::probe#function"
            and record["raw"]["text"] == "Thing"
        ]
        assert probe_thing and all(record["target_id"] == "src/model.rs::Thing#struct" for record in probe_thing)
        generic_thing = [
            record for record in records
            if record["source_id"] == "src/lib.rs::generic#function"
            and record["raw"]["text"] == "Thing"
        ]
        assert generic_thing and all(record["target_id"] is None for record in generic_thing)
        assert any(record["unresolved_reason"] == "type_parameter" for record in generic_thing)

        reference_records = service.graph_references(
            repo, file="src/lib.rs", family="symbol", status="all"
        )["items"]
        unresolved = {
            record["raw"]["text"]: record
            for record in reference_records
            if record["raw"]["text"] in {"Shared", "Choice", "Hidden", "Display"}
        }
        assert set(unresolved) == {"Shared", "Choice", "Hidden", "Display"}
        assert all(record["target_id"] is None and record["target_file"] is None for record in unresolved.values())
        assert unresolved["Shared"]["unresolved_reason"] == "ambiguous_target"
        assert unresolved["Choice"]["unresolved_reason"] == "configuration_divergent"
        assert unresolved["Hidden"]["unresolved_reason"] == "target_inaccessible"
        assert unresolved["Display"]["import_unresolved_reason"] == "external"
        assert not {
            "wrong.rs", "src/a.rs", "src/b.rs", "src/model.rs",
        }.intersection({record["target_file"] for record in unresolved.values() if record["target_file"]})
        calls = service.graph_calls(repo, file="src/lib.rs", status="all")["items"]
        generated = [call for call in calls if call["raw"]["callee_text"] == "Generated!"]
        assert all(call["target_id"] is None for call in generated)


def test_rust_nested_external_module_and_multiline_use_deliver_exact_route_proof(tmp_path):
    with _repo(tmp_path, {
        "Cargo.toml": '[package]\nname = "nested"\nversion = "0.1.0"\nedition = "2021"\n',
        "src/lib.rs": (
            "pub mod outer;\n"
            "use crate::outer::{\n"
            "    inner::Item,\n"
            "};\n"
            "pub fn entry(value: Item) -> Item { value }\n"
        ),
        "src/outer.rs": "pub mod inner;\n",
        "src/outer/inner.rs": "pub struct Item;\n",
    }) as repo:
        result = _explore(
            repo,
            intent="type_dependencies",
            seed_ids=["src/lib.rs::entry#function"],
        )
        assert _edges(result) == {
            ("src/lib.rs::entry#function", "uses_type", "src/outer/inner.rs::Item#struct"),
        }
        sources = [source["content"] for source in result["sources"]]
        assert any("use crate::outer::{\n    inner::Item,\n};" in source for source in sources)
        assert any("pub mod outer;" in source for source in sources)
        assert any("pub mod inner;" in source for source in sources)
        _assert_packet(repo, result)


def test_rust_declared_possible_relationship_delivers_exact_cfg_attribute(tmp_path):
    with _repo(tmp_path, {
        "Cargo.toml": '[package]\nname = "configured"\nversion = "0.1.0"\nedition = "2021"\n',
        "src/lib.rs": (
            '#[cfg(feature = "a")]\n'
            "pub struct Item;\n"
            "pub fn use_it(value: Item) {}\n"
        ),
    }) as repo:
        result = _explore(
            repo,
            intent="type_dependencies",
            seed_ids=["src/lib.rs::use_it#function"],
        )
        assert {
            relation["resolution_configuration"]
            for relation in result["relationships"]
        } == {"declared_possible"}
        assert any(
            source["content"] == '#[cfg(feature = "a")]'
            for source in result["sources"]
        )
        _assert_packet(repo, result)
