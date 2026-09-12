"""Bounded end-to-end acceptance for the W4.3 JavaScript dependency slice."""
from __future__ import annotations

from contextlib import contextmanager
import hashlib
from pathlib import Path

import pytest

from benchmarks.typescript_context_corpus import _isolated_store, load_corpus
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
    _sources,
)


@pytest.fixture
def corpus():
    return load_corpus(CORPUS_ROOT)


def _resolved_references(repo: Path, file: str) -> list[dict]:
    return service.graph_references(repo, file=file, status="resolved")["items"]


def _resolved_calls(repo: Path, file: str | None = None) -> list[dict]:
    return service.graph_calls(repo, file=file, status="resolved")["items"]


@contextmanager
def _indexed_files(tmp_path: Path, files: dict[str, str]):
    """Index a small authored fixture in the same isolated service store."""

    repo = tmp_path / "repo"
    for name, source in files.items():
        path = repo / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(source, encoding="utf-8")
    with _isolated_store(tmp_path / "store"):
        service.index_repo(repo, incremental=False)
        yield repo


def test_javascript_value_dependencies_deliver_calls_and_reexport_proof(tmp_path, corpus):
    case = _case(corpus, "javascript_value_dependencies")
    with _indexed_snapshot(tmp_path, corpus, case["snapshot"]) as repo:
        references = _resolved_references(repo, "app.js")
        imported = {
            reference["raw"]["text"]: reference
            for reference in references
            if reference["raw"]["text"] in {"make", "add"}
        }
        assert set(imported) == {"make", "add"}
        for name, target in {
            "make": "helper.js::make#function",
            "add": "helper.js::add#function",
        }.items():
            reference = imported[name]
            assert reference["target_id"] == target
            assert reference["target_file"] == "helper.js"
            assert reference["resolution"] == "import-resolved"
            assert reference["resolution_basis"] == "reexport_chain"
            assert {support["kind"] for support in reference["support"]} >= {
                "import_binding",
                "reexport",
                "definition",
            }
            assert {support["file"] for support in reference["support"]} >= {
                "app.js",
                "barrel.js",
                "helper.js",
            }

        app_calls = _resolved_calls(repo, "app.js")
        assert {
            (call["caller_id"], call["target_id"], call["raw"]["callee_text"])
            for call in app_calls
        } == {
            (
                "app.js::run#function",
                "helper.js::make#function",
                "make",
            ),
            (
                "app.js::run#function",
                "helper.js::add#function",
                "add",
            ),
            (
                "app.js::Worker.work#method",
                "helper.js::add#function",
                "add",
            ),
        }
        for call in app_calls:
            assert call["resolution"] == "import-resolved"
            assert {support["kind"] for support in call["support"]} >= {
                "call_site",
                "caller_definition",
                "symbol_reference",
            }

        helper_calls = _resolved_calls(repo, "helper.js")
        assert len(helper_calls) == 1
        make_call = helper_calls[0]
        assert make_call["caller_id"] == "helper.js::make#function"
        assert make_call["target_id"] == "helper.js::add#function"
        assert make_call["resolution"] == "exact"
        assert make_call["raw"]["callee_text"] == "add"
        assert {support["kind"] for support in make_call["support"]} >= {
            "call_site",
            "caller_definition",
            "local_definition",
        }

        result = service.explore(
            repo,
            query=case["prompt"],
            intent="dependencies",
            seed_ids=["app.js::run#function"],
        )
        assert set(_items(result)) == {
            "app.js::run#function",
            "helper.js::make#function",
            "helper.js::add#function",
        }
        assert _edges(result) == {
            (
                "app.js::run#function",
                "calls",
                "helper.js::make#function",
            ),
            (
                "app.js::run#function",
                "calls",
                "helper.js::add#function",
            ),
        }
        assert all(
            relation["edge"]["type"] == "calls"
            for relation in result["relationships"]
        )
        assert any(
            omission["reason"] == "alternative_path"
            for omission in result["omissions"]
        )
        _assert_packet(repo, result)
        _assert_item_definitions_match_get(repo, result)
        _assert_required_context(
            repo,
            result,
            case,
            {"run", "add", "make", "import", "barrel", "default", "arrow_export"},
            exact_symbol_ids={"run", "add", "make"},
        )


def test_javascript_direct_class_base_is_authored_dependency(tmp_path, corpus):
    case = _case(corpus, "javascript_direct_class_base")
    with _indexed_snapshot(tmp_path, corpus, case["snapshot"]) as repo:
        parent_refs = [
            reference
            for reference in _resolved_references(repo, "app.js")
            if reference["raw"]["text"] == "Parent"
        ]
        assert len(parent_refs) == 1
        parent = parent_refs[0]
        assert parent["target_id"] == "contracts.js::Base#class"
        assert parent["resolution"] == "import-resolved"
        assert parent["resolution_basis"] == "reexport_chain"
        assert {support["kind"] for support in parent["support"]} >= {
            "import_binding",
            "reexport",
            "definition",
        }
        assert {support["file"] for support in parent["support"]} >= {
            "app.js",
            "barrel.js",
            "contracts.js",
        }

        result = service.explore(
            repo,
            query=case["prompt"],
            intent="dependencies",
            seed_ids=["app.js::Worker#class"],
        )
        assert set(_items(result)) == {
            "app.js::Worker#class",
            "contracts.js::Base#class",
        }
        assert _edges(result) == {
            (
                "app.js::Worker#class",
                "extends",
                "contracts.js::Base#class",
            )
        }
        assert all(
            relation["edge"]["type"] not in {"uses_type", "implements"}
            for relation in result["relationships"]
        )
        assert "app.js::Worker.work#method" not in _items(result)
        assert "helper.js::add#function" not in _items(result)
        _assert_packet(repo, result)
        _assert_item_definitions_match_get(repo, result)
        _assert_required_context(
            repo,
            result,
            case,
            {"entry", "base", "import", "base_export"},
            exact_symbol_ids={"entry", "base"},
        )


def test_javascript_known_call_impact_delivers_incoming_static_callers(tmp_path, corpus):
    case = _case(corpus, "javascript_known_call_impact")
    with _indexed_snapshot(tmp_path, corpus, case["snapshot"]) as repo:
        calls = _resolved_calls(repo)
        add_calls = [
            call for call in calls if call["target_id"] == "helper.js::add#function"
        ]
        assert {
            (call["caller_id"], call["raw"]["callee_text"])
            for call in add_calls
        } == {
            ("app.js::run#function", "add"),
            ("app.js::Worker.work#method", "add"),
            ("helper.js::make#function", "add"),
        }
        for call in add_calls:
            assert call["status"] == "resolved"
            assert call["target_file"] == "helper.js"
            assert {support["kind"] for support in call["support"]} >= {
                "call_site",
                "caller_definition",
            }

        result = service.explore(
            repo,
            query=case["prompt"],
            intent="impact",
            seed_ids=["helper.js::add#function"],
        )
        assert set(_items(result)) == {
            "helper.js::add#function",
            "app.js::run#function",
            "app.js::Worker.work#method",
            "helper.js::make#function",
        }
        assert _edges(result) == {
            (
                "app.js::run#function",
                "calls",
                "helper.js::add#function",
            ),
            (
                "app.js::Worker.work#method",
                "calls",
                "helper.js::add#function",
            ),
            (
                "helper.js::make#function",
                "calls",
                "helper.js::add#function",
            ),
        }
        assert all(
            relation["traversed"] == "reverse"
            for relation in result["relationships"]
        )
        assert all(
            relation["edge"]["type"] == "calls"
            for relation in result["relationships"]
        )
        for relation in result["relationships"]:
            assert {source["file"] for source in _relation_sources(result, relation)} >= {
                "helper.js",
            }
        _assert_packet(repo, result)
        _assert_item_definitions_match_get(repo, result)
        _assert_required_context(
            repo,
            result,
            case,
            {"add", "run", "make", "method", "import", "barrel", "arrow_export"},
            exact_symbol_ids={"add", "run", "make", "method"},
        )


def test_javascript_unproven_dependencies_never_guess_targets(tmp_path, corpus):
    case = _case(corpus, "javascript_unproven_dependencies")
    with _indexed_snapshot(tmp_path, corpus, case["snapshot"]) as repo:
        imports = service.graph_imports(repo, file="bad.js", status="all")["items"]
        external = next(
            item for item in imports if item["specifier"] == "uninstalled-package"
        )
        assert external["status"] == "unresolved"
        assert external["unresolved_reason"] == "external"
        assert external["target_id"] is None
        assert external["target_file"] is None

        references = service.graph_references(repo, file="bad.js", status="all")["items"]
        assert references
        assert not [reference for reference in references if reference["status"] == "resolved"]
        assert all(reference["target_id"] is None for reference in references)
        assert all(reference["target_file"] is None for reference in references)
        assert {reference["raw"]["text"] for reference in references} >= {
            "Thing",
            "Factory",
            "External",
            "model[key]",
        }
        unproven_thing = next(
            reference
            for reference in references
            if reference["raw"]["text"] == "Thing" and reference["raw"]["line"] == 5
        )
        shadowed_thing = next(
            reference
            for reference in references
            if reference["raw"]["text"] == "Thing" and reference["raw"]["line"] == 6
        )
        external_ref = next(
            reference for reference in references if reference["raw"]["text"] == "External"
        )
        computed_ref = next(
            reference for reference in references if reference["raw"]["text"] == "model[key]"
        )
        factory_ref = next(
            reference for reference in references if reference["raw"]["text"] == "Factory"
        )
        assert unproven_thing["unresolved_reason"] == "ambiguous_target"
        assert shadowed_thing["unresolved_reason"] == "binding_shadowed"
        assert external_ref["import_unresolved_reason"] == "external"
        assert computed_ref["unresolved_reason"] == "unsupported_reference"
        assert factory_ref["target_id"] is None

        calls = service.graph_calls(repo, file="bad.js", status="all")["items"]
        assert calls
        assert not [call for call in calls if call["status"] == "resolved"]
        assert all(call["target_id"] is None for call in calls)
        assert all(call["target_file"] is None for call in calls)
        assert {call["raw"]["callee_text"] for call in calls} >= {
            "Thing",
            "model[key]",
            "require",
            "import",
            "chooseBase",
        }

        unproven = service.explore(
            repo,
            query=case["prompt"],
            intent="dependencies",
            seed_ids=["bad.js::unproven#function"],
        )
        assert set(_items(unproven)) == {"bad.js::unproven#function"}
        assert not unproven["relationships"]
        assert any(
            omission["reason"] == "unresolved_relation"
            for omission in unproven["omissions"]
        )
        _assert_packet(repo, unproven)
        _assert_item_definitions_match_get(repo, unproven)
        _assert_required_context(
            repo,
            unproven,
            case,
            {"entry"},
            exact_symbol_ids={"entry"},
        )

        dynamic = service.explore(
            repo,
            query=case["prompt"],
            intent="dependencies",
            seed_ids=["bad.js::Dynamic#class"],
        )
        assert set(_items(dynamic)) == {"bad.js::Dynamic#class"}
        assert not dynamic["relationships"]
        _assert_packet(repo, dynamic)

        forbidden = {
            "left.js::Thing#class",
            "right.js::Thing#class",
            "left.js::Factory#function",
        }
        assert not forbidden.intersection(
            {reference["target_id"] for reference in references if reference["target_id"]}
        )
        assert not forbidden.intersection(
            {call["target_id"] for call in calls if call["target_id"]}
        )
        assert not forbidden.intersection(set(_items(unproven)))
        assert not forbidden.intersection(set(_items(dynamic)))


def test_javascript_zero_and_reduced_evidence_are_explicit_omissions(tmp_path, corpus):
    case = _case(corpus, "javascript_value_dependencies")
    with _indexed_snapshot(tmp_path, corpus, case["snapshot"]) as repo:
        full = service.explore(
            repo,
            query=case["prompt"],
            intent="dependencies",
            seed_ids=["app.js::run#function"],
        )
        anchor = _items(full)["app.js::run#function"]
        anchor_source = _sources(full)[anchor["source_id"]]
        anchor_bytes = anchor_source["end_byte"] - anchor_source["start_byte"]

        reduced = service.explore(
            repo,
            query=case["prompt"],
            intent="dependencies",
            seed_ids=["app.js::run#function"],
            max_evidence_bytes=anchor_bytes,
        )
        assert set(_items(reduced)) == {"app.js::run#function"}
        assert not reduced["relationships"]
        assert reduced["usage"]["evidence_bytes"] <= anchor_bytes
        assert any(
            omission["reason"] in {"evidence_budget", "ancestor_unavailable"}
            for omission in reduced["omissions"]
        )
        _assert_packet(repo, reduced)

        empty = service.explore(
            repo,
            query=case["prompt"],
            intent="dependencies",
            seed_ids=["app.js::run#function"],
            max_evidence_bytes=0,
        )
        assert empty["status"] == "empty"
        assert not empty["items"]
        assert not empty["relationships"]
        assert not empty["sources"]
        assert empty["usage"]["evidence_bytes"] == 0
        assert any(
            omission["reason"] == "evidence_budget"
            for omission in empty["omissions"]
        )
        _assert_packet(repo, empty)


def test_javascript_dependency_refreshes_source_target_and_reexport_support(tmp_path, corpus):
    case = _case(corpus, "javascript_value_dependencies")
    with _indexed_snapshot(tmp_path, corpus, case["snapshot"]) as repo:
        before = service.explore(
            repo,
            query=case["prompt"],
            intent="dependencies",
            seed_ids=["app.js::run#function"],
        )
        before_anchor = _sources(before)[
            _items(before)["app.js::run#function"]["source_id"]
        ]
        before_target = next(
            source
            for source in before["sources"]
            if source["file"] == "helper.js" and "add" in source["content"]
        )

        helper = repo / "helper.js"
        helper.write_text(
            helper.read_text(encoding="utf-8").replace("value + 1", "value + 2"),
            encoding="utf-8",
        )
        changed_target = service.explore(
            repo,
            query=case["prompt"],
            intent="dependencies",
            seed_ids=["app.js::run#function"],
            ensure_fresh=True,
        )
        changed_target_source = next(
            source
            for source in changed_target["sources"]
            if source["file"] == "helper.js" and "value + 2" in source["content"]
        )
        assert changed_target_source["content_hash"] != before_target["content_hash"]
        assert _edges(changed_target) == _edges(before)
        _assert_packet(repo, changed_target)

        barrel = repo / "barrel.js"
        app = repo / "app.js"
        barrel.write_text(
            barrel.read_text(encoding="utf-8").replace(
                "default as make, add",
                "default as make, add as plus",
            ),
            encoding="utf-8",
        )
        app.write_text(
            app.read_text(encoding="utf-8").replace(
                "{ make, add, Parent }",
                "{ make, plus as add, Parent }",
            ),
            encoding="utf-8",
        )
        changed_reexport = service.explore(
            repo,
            query=case["prompt"],
            intent="dependencies",
            seed_ids=["app.js::run#function"],
            ensure_fresh=True,
        )
        assert "helper.js::add#function" in _items(changed_reexport)
        assert _edges(changed_reexport) == _edges(before)
        relation_sources = [
            source
            for relation in changed_reexport["relationships"]
            for source in _relation_sources(changed_reexport, relation)
        ]
        assert any(
            source["file"] == "barrel.js" and "add as plus" in source["content"]
            for source in relation_sources
        )
        assert any(
            source["file"] == "app.js" and "plus as add" in source["content"]
            for source in relation_sources
        )
        _assert_packet(repo, changed_reexport)

        app.write_text(
            app.read_text(encoding="utf-8").replace(
                "return make() + add(1)",
                "return make() + add(2)",
            ),
            encoding="utf-8",
        )
        changed_source = service.explore(
            repo,
            query=case["prompt"],
            intent="dependencies",
            seed_ids=["app.js::run#function"],
            ensure_fresh=True,
        )
        current_anchor = _sources(changed_source)[
            _items(changed_source)["app.js::run#function"]["source_id"]
        ]
        assert "return make() + add(2)" in current_anchor["content"]
        assert current_anchor["content_hash"] != before_anchor["content_hash"]
        assert _edges(changed_source) == _edges(before)
        _assert_packet(repo, changed_source)


def test_javascript_imported_value_references_keep_definition_ownership(tmp_path):
    files = {
        "app.js": """\
import { CONFIG } from "./config.js";
import { Thing } from "./model.js";

export function read() {
  return CONFIG;
}

export class Reader {
  get() {
    return CONFIG;
  }
}

export function useThing() {
  return Thing();
}
""",
        "config.js": "export const CONFIG = { enabled: true };\n",
        "model.js": "export function Thing() { return 1; }\n",
        "wrong.js": "export function Thing() { return 2; }\n",
    }
    with _indexed_files(tmp_path, files) as repo:
        references = service.graph_references(repo, file="app.js", status="resolved")["items"]
        config_references = [
            reference
            for reference in references
            if reference["raw"]["text"] == "CONFIG"
        ]
        assert {
            reference["source_id"] for reference in config_references
        } == {
            "app.js::read#function",
            "app.js::Reader.get#method",
        }
        assert {
            reference["target_id"] for reference in config_references
        } == {"config.js::CONFIG#constant"}
        for reference in config_references:
            assert reference["resolution"] == "import-resolved"
            assert reference["resolution_basis"] == "direct_binding"
            assert {support["kind"] for support in reference["support"]} >= {
                "import_binding",
                "definition",
            }
            assert {support["file"] for support in reference["support"]} >= {
                "app.js",
                "config.js",
            }

        thing_reference = next(
            reference
            for reference in references
            if reference["raw"]["text"] == "Thing"
        )
        assert thing_reference["source_id"] == "app.js::useThing#function"
        assert thing_reference["target_id"] == "model.js::Thing#function"
        assert thing_reference["target_id"] != "wrong.js::Thing#function"

        calls = _resolved_calls(repo, "app.js")
        assert [
            (call["caller_id"], call["target_id"], call["raw"]["callee_text"])
            for call in calls
        ] == [
            (
                "app.js::useThing#function",
                "model.js::Thing#function",
                "Thing",
            )
        ]
        call = calls[0]
        assert {support["kind"] for support in call["support"]} >= {
            "call_site",
            "caller_definition",
            "symbol_reference",
        }

        for seed_id, target_id in (
            ("app.js::read#function", "config.js::CONFIG#constant"),
            ("app.js::Reader.get#method", "config.js::CONFIG#constant"),
        ):
            result = service.explore(
                repo,
                query="Which authored value does this JavaScript code read?",
                intent="dependencies",
                seed_ids=[seed_id],
            )
            assert set(_items(result)) == {seed_id, target_id}
            assert _edges(result) == {(seed_id, "references", target_id)}
            assert all(
                relation["edge"]["type"] == "references"
                for relation in result["relationships"]
            )
            assert all(
                relation["edge"]["type"] not in {"calls", "uses_type", "implements"}
                for relation in result["relationships"]
            )
            _assert_packet(repo, result)
            _assert_item_definitions_match_get(repo, result)
            delivered = [source["content"] for source in result["sources"]]
            assert any('import { CONFIG } from "./config.js";' in source for source in delivered)
            assert any("export const CONFIG" in source for source in delivered)


def test_javascript_local_and_namespace_class_bases_keep_method_ownership(tmp_path):
    files = {
        "app.js": """\
import * as contracts from "./contracts.js";

export class LocalBase {
  enabled() {
    return true;
  }
}

export class LocalChild extends LocalBase {}
export class RemoteChild extends contracts.Base {}
export class Worker extends contracts.Base {
  work() {
    return contracts.helper();
  }
}
""",
        "contracts.js": """\
export class Base {}
export function helper() {
  return 1;
}
""",
    }
    with _indexed_files(tmp_path, files) as repo:
        references = service.graph_references(
            repo, file="app.js", family="type", status="resolved"
        )["items"]
        bases = [
            reference
            for reference in references
            if reference["raw"]["text"] in {"LocalBase", "contracts.Base"}
        ]
        assert {
            (reference["source_id"], reference["raw"]["text"], reference["target_id"])
            for reference in bases
        } == {
            (
                "app.js::LocalChild#class",
                "LocalBase",
                "app.js::LocalBase#class",
            ),
            (
                "app.js::RemoteChild#class",
                "contracts.Base",
                "contracts.js::Base#class",
            ),
            (
                "app.js::Worker#class",
                "contracts.Base",
                "contracts.js::Base#class",
            ),
        }
        value_references = service.graph_references(
            repo, file="app.js", family="symbol", status="resolved"
        )["items"]
        helper_reference = next(
            reference
            for reference in value_references
            if reference["raw"]["text"] == "contracts.helper"
        )
        assert helper_reference["source_id"] == "app.js::Worker.work#method"
        assert helper_reference["target_id"] == "contracts.js::helper#function"

        calls = _resolved_calls(repo, "app.js")
        assert {
            (call["caller_id"], call["target_id"], call["raw"]["callee_text"])
            for call in calls
        } == {
            (
                "app.js::Worker.work#method",
                "contracts.js::helper#function",
                "contracts.helper",
            )
        }
        for seed_id, target_id in (
            ("app.js::LocalChild#class", "app.js::LocalBase#class"),
            ("app.js::RemoteChild#class", "contracts.js::Base#class"),
            ("app.js::Worker#class", "contracts.js::Base#class"),
        ):
            result = service.explore(
                repo,
                query="Which direct authored JavaScript base does this class extend?",
                intent="dependencies",
                seed_ids=[seed_id],
            )
            assert set(_items(result)) == {seed_id, target_id}
            assert _edges(result) == {(seed_id, "extends", target_id)}
            assert not {
                relation["edge"]["type"]
                for relation in result["relationships"]
            }.intersection({"uses_type", "implements"})
            _assert_packet(repo, result)
            _assert_item_definitions_match_get(repo, result)
        worker = service.explore(
            repo,
            query="Which direct authored JavaScript base does this class extend?",
            intent="dependencies",
            seed_ids=["app.js::Worker#class"],
        )
        assert "app.js::Worker.work#method" not in _items(worker)
        assert "contracts.js::helper#function" not in _items(worker)


def test_javascript_shadowed_bindings_never_guess_imported_targets(tmp_path):
    files = {
        "app.js": """\
import { Thing } from "./model.js";

export function parameter(Thing) {
  return Thing();
}

export function block() {
  {
    const Thing = () => 1;
    return Thing();
  }
}

export function variable() {
  var Thing = () => 2;
  return Thing();
}
""",
        "model.js": "export function Thing() { return 1; }\n",
        "wrong.js": "export function Thing() { return 2; }\n",
    }
    owners = {
        "app.js::parameter#function",
        "app.js::block#function",
        "app.js::variable#function",
    }
    with _indexed_files(tmp_path, files) as repo:
        references = service.graph_references(repo, file="app.js", status="all")["items"]
        shadowed_references = [
            reference
            for reference in references
            if reference["raw"]["text"] == "Thing"
            and reference["source_id"] in owners
        ]
        assert {reference["source_id"] for reference in shadowed_references} == owners
        assert all(reference["status"] == "unresolved" for reference in shadowed_references)
        assert all(reference["target_id"] is None for reference in shadowed_references)
        assert all(reference["target_file"] is None for reference in shadowed_references)
        assert not any(
            reference["target_id"] == "model.js::Thing#function"
            for reference in shadowed_references
        )
        assert not any(
            reference["target_id"] == "wrong.js::Thing#function"
            for reference in shadowed_references
        )

        calls = service.graph_calls(repo, file="app.js", status="all")["items"]
        shadowed_calls = [
            call
            for call in calls
            if call["raw"]["callee_text"] == "Thing"
            and call["caller_id"] in owners
        ]
        assert {call["caller_id"] for call in shadowed_calls} == owners
        shadowed_by_owner = {call["caller_id"]: call for call in shadowed_calls}
        for owner in owners - {"app.js::block#function"}:
            assert shadowed_by_owner[owner]["status"] == "unresolved"
            assert shadowed_by_owner[owner]["target_id"] is None
            assert shadowed_by_owner[owner]["target_file"] is None
        block_call = shadowed_by_owner["app.js::block#function"]
        assert block_call["status"] == "resolved"
        assert block_call["target_id"] == "app.js::block.Thing#function"
        assert block_call["target_file"] == "app.js"
        assert block_call["resolution"] == "exact"
        assert not any(
            call["target_id"] in {
                "model.js::Thing#function",
                "wrong.js::Thing#function",
            }
            for call in shadowed_calls
        )

        for owner in sorted(owners):
            result = service.explore(
                repo,
                query="Which exact JavaScript callable does this shadowed name invoke?",
                intent="dependencies",
                seed_ids=[owner],
            )
            if owner == "app.js::block#function" and block_call["target_id"]:
                assert set(_items(result)) == {
                    owner,
                    "app.js::block.Thing#function",
                }
                assert _edges(result) == {
                    (owner, "calls", "app.js::block.Thing#function")
                }
            else:
                assert set(_items(result)) == {owner}
                assert not result["relationships"]
            _assert_packet(repo, result)
            if owner == "app.js::block#function":
                exact = service.get_symbols_result(
                    repo, ["app.js::block.Thing#function"]
                )["symbols"]
                assert len(exact) == 1
                assert exact[0]["source"] == "Thing = () => 1"
                local_support = next(
                    support
                    for support in block_call["support"]
                    if support["kind"] == "local_definition"
                )
                assert local_support["content_hash"] == hashlib.sha256(
                    exact[0]["source"].encode("utf-8")
                ).hexdigest()
            else:
                _assert_item_definitions_match_get(repo, result)


def test_javascript_mutated_base_and_callable_assignment_stay_unresolved(tmp_path):
    files = {
        "app.js": """\
import { Base as ImportedBase, target as importedTarget } from "./model.js";

let BaseAlias = ImportedBase;
BaseAlias = replacementBase;
export class Dynamic extends BaseAlias {}

let fn = importedTarget;
fn = replacement;
export function assigned() {
  return fn();
}
""",
        "model.js": """\
export class Base {}
export function target() {
  return 1;
}
""",
    }
    with _indexed_files(tmp_path, files) as repo:
        type_references = service.graph_references(repo, file="app.js", family="type", status="all")["items"]
        dynamic = next(
            reference
            for reference in type_references
            if reference["source_id"] == "app.js::Dynamic#class"
        )
        assert dynamic["raw"]["text"] == "BaseAlias"
        assert dynamic["status"] == "unresolved"
        assert dynamic["target_id"] is None
        assert dynamic["target_file"] is None
        assert dynamic["unresolved_reason"] == "unsupported_syntax"
        assert dynamic["raw"]["unsupported_reason"] == "mutated_heritage_binding"
        assert not any(
            reference["target_id"] == "model.js::Base#class"
            for reference in type_references
        )

        calls = service.graph_calls(repo, file="app.js", status="all")["items"]
        assigned = next(
            call
            for call in calls
            if call["raw"]["callee_text"] == "fn"
        )
        assert assigned["raw"]["callee_text"] == "fn"
        assert assigned["status"] == "unresolved"
        assert assigned["target_id"] is None
        assert assigned["target_file"] is None
        assert not any(
            call["target_id"] == "model.js::target#function" for call in calls
        )

        for owner in ("app.js::Dynamic#class", "app.js::assigned#function"):
            result = service.explore(
                repo,
                query="Which exact authored JavaScript dependency remains provable after mutation?",
                intent="dependencies",
                seed_ids=[owner],
            )
            assert set(_items(result)) == {owner}
            assert not result["relationships"]
            _assert_packet(repo, result)


def test_javascript_prototype_dispatch_and_anonymous_callback_do_not_invent_calls(tmp_path):
    files = {
        "app.js": """\
import { method, target } from "./model.js";

Object.prototype.method = method;

export function dispatch(obj) {
  return obj.method();
}

export function outer() {
  return [1].map((value) => target(value));
}
""",
        "model.js": """\
export function method() {
  return 1;
}
export function target(value) {
  return value;
}
""",
    }
    with _indexed_files(tmp_path, files) as repo:
        calls = service.graph_calls(repo, file="app.js", status="all")["items"]
        assert not any(call["status"] == "resolved" for call in calls)
        assert not any(
            call["target_id"] in {
                "model.js::method#function",
                "model.js::target#function",
            }
            for call in calls
        )
        dispatch_calls = [
            call
            for call in calls
            if call["caller_id"] == "app.js::dispatch#function"
        ]
        assert dispatch_calls
        assert all(call["target_id"] is None for call in dispatch_calls)
        assert any(call["raw"]["callee_text"] == "obj.method" for call in dispatch_calls)

        for owner in ("app.js::dispatch#function", "app.js::outer#function"):
            result = service.explore(
                repo,
                query="Which exact JavaScript call target is proven here?",
                intent="dependencies",
                seed_ids=[owner],
            )
            assert set(_items(result)) == {owner}
            assert not result["relationships"]
            _assert_packet(repo, result)
            _assert_item_definitions_match_get(repo, result)


def test_javascript_jsdoc_type_and_anonymous_callback_have_no_dependency_target(tmp_path):
    files = {
        "app.js": """\
import { Thing } from "./model.js";

/** @param {Thing} value */
export function documented(value) {
  return value;
}

export function outer() {
  return [1].map((value) => value + 1);
}
""",
        "model.js": "export function Thing(value) { return value; }\n",
    }
    with _indexed_files(tmp_path, files) as repo:
        references = service.graph_references(repo, file="app.js", status="all")["items"]
        assert not any(
            reference["target_id"] == "model.js::Thing#function"
            for reference in references
        )
        calls = service.graph_calls(repo, file="app.js", status="all")["items"]
        assert not any(
            call["target_id"] == "model.js::Thing#function" for call in calls
        )
        result = service.explore(
            repo,
            query="Which documented JavaScript type dependency is proven?",
            intent="dependencies",
            seed_ids=["app.js::documented#function"],
        )
        assert set(_items(result)) == {"app.js::documented#function"}
        assert not result["relationships"]
        _assert_packet(repo, result)
        _assert_item_definitions_match_get(repo, result)


def test_javascript_arrow_call_before_initializer_is_not_resolved(tmp_path):
    files = {
        "app.js": """\
export function before() {
  return later();
}

const later = () => 1;
""",
    }
    with _indexed_files(tmp_path, files) as repo:
        calls = service.graph_calls(repo, file="app.js", status="all")["items"]
        before = next(
            call
            for call in calls
            if call["caller_id"] == "app.js::before#function"
        )
        assert before["raw"]["callee_text"] == "later"
        assert before["status"] == "unresolved"
        assert before["target_id"] is None
        assert before["target_file"] is None
        assert before["unresolved_reason"] in {
            "local_binding_shadowed",
            "binding_shadowed",
            "unsupported_call",
        }
        result = service.explore(
            repo,
            query="Which exact JavaScript call target is initialized before use?",
            intent="dependencies",
            seed_ids=["app.js::before#function"],
        )
        assert set(_items(result)) == {"app.js::before#function"}
        assert not result["relationships"]
        _assert_packet(repo, result)


def test_javascript_origin_reassignment_drops_export_definition_proof(tmp_path):
    files = {
        "provider.js": """\
import { replacement, Other } from "./wrong.js";

export function make() {
  return 1;
}
export class Base {}

make = replacement;
Base = Other;
""",
        "barrel.js": 'export { make, Base } from "./provider.js";\n',
        "consumer.js": """\
import { make, Base } from "./barrel.js";

export function run() {
  return make();
}

export class Child extends Base {}
""",
        "wrong.js": """\
export function replacement() {
  return 2;
}
export class Other {}
""",
    }
    with _indexed_files(tmp_path, files) as repo:
        references = service.graph_references(
            repo, file="consumer.js", family="symbol", status="all"
        )["items"]
        run_make = next(
            reference
            for reference in references
            if reference["source_id"] == "consumer.js::run#function"
        )
        type_references = service.graph_references(
            repo, file="consumer.js", family="type", status="all"
        )["items"]
        child_base = next(
            reference
            for reference in type_references
            if reference["source_id"] == "consumer.js::Child#class"
        )
        assert run_make["raw"]["text"] == "make"
        assert child_base["raw"]["text"] == "Base"
        assert run_make["status"] == "unresolved"
        assert child_base["status"] == "unresolved"
        assert run_make["target_id"] is None
        assert child_base["target_id"] is None
        assert run_make["unresolved_reason"] in {
            "ambiguous_target",
            "mutated_export",
            "unsupported_reference",
        }
        assert child_base["unresolved_reason"] in {
            "ambiguous_target",
            "mutated_export",
            "mutated_heritage_binding",
            "unsupported_reference",
        }
        assert not any(
            reference["target_id"] in {
                "provider.js::make#function",
                "provider.js::Base#class",
                "wrong.js::replacement#function",
                "wrong.js::Other#class",
            }
            for reference in [*references, *type_references]
        )
        calls = service.graph_calls(repo, file="consumer.js", status="all")["items"]
        assert not any(
            call["target_id"] in {
                "provider.js::make#function",
                "wrong.js::replacement#function",
            }
            for call in calls
        )
        for owner in ("consumer.js::run#function", "consumer.js::Child#class"):
            result = service.explore(
                repo,
                query="Which exact JavaScript origin survives an export reassignment?",
                intent="dependencies",
                seed_ids=[owner],
            )
            assert set(_items(result)) == {owner}
            assert not result["relationships"]
            _assert_packet(repo, result)


def test_javascript_dependency_refresh_tracks_resolver_configuration_control(tmp_path):
    files = {
        "jsconfig.json": """\
{
  "compilerOptions": {
    "baseUrl": ".",
    "paths": {"@model": ["./left.js"]}
  }
}
""",
        "consumer.js": """\
import { CONFIG, Base } from "@model";

export function read() {
  return CONFIG;
}

export class Child extends Base {}
""",
        "left.js": """\
export const CONFIG = { side: "left" };
export class Base {}
""",
        "right.js": """\
export const CONFIG = { side: "right" };
export class Base {}
""",
    }
    with _indexed_files(tmp_path, files) as repo:
        before = service.explore(
            repo,
            query="Which configured JavaScript module supplies this value?",
            intent="dependencies",
            seed_ids=["consumer.js::read#function", "consumer.js::Child#class"],
        )
        before_items = _items(before)
        assert {
            "left.js::CONFIG#constant",
            "left.js::Base#class",
        } <= set(before_items)
        assert "right.js::CONFIG#constant" not in before_items
        assert "right.js::Base#class" not in before_items
        before_sources = {
            source["file"]: source["content_hash"] for source in before["sources"]
        }
        before_symbol = next(
            reference
            for reference in service.graph_references(
                repo, file="consumer.js", family="symbol", status="resolved"
            )["items"]
            if reference["raw"]["text"] == "CONFIG"
        )
        before_type = next(
            reference
            for reference in service.graph_references(
                repo, file="consumer.js", family="type", status="resolved"
            )["items"]
            if reference["raw"]["text"] == "Base"
        )
        assert before_symbol["resolution_control_files"] == ["jsconfig.json"]
        assert before_type["resolution_controls"]
        before_control_hashes = {
            control["file"]: control["content_hash"]
            for control in before_type["resolution_controls"]
        }
        assert "jsconfig.json" in before_control_hashes
        _assert_packet(repo, before)

        config = repo / "jsconfig.json"
        config.write_text(
            config.read_text(encoding="utf-8").replace("./left.js", "./right.js"),
            encoding="utf-8",
        )
        changed = service.explore(
            repo,
            query="Which configured JavaScript module supplies this value?",
            intent="dependencies",
            seed_ids=["consumer.js::read#function", "consumer.js::Child#class"],
            ensure_fresh=True,
        )
        changed_items = _items(changed)
        assert {
            "right.js::CONFIG#constant",
            "right.js::Base#class",
        } <= set(changed_items)
        assert "left.js::CONFIG#constant" not in changed_items
        assert "left.js::Base#class" not in changed_items
        changed_sources = {
            source["file"]: source["content_hash"] for source in changed["sources"]
        }
        assert changed_sources["consumer.js"] == before_sources["consumer.js"]
        changed_symbol = next(
            reference
            for reference in service.graph_references(
                repo, file="consumer.js", family="symbol", status="resolved"
            )["items"]
            if reference["raw"]["text"] == "CONFIG"
        )
        changed_type = next(
            reference
            for reference in service.graph_references(
                repo, file="consumer.js", family="type", status="resolved"
            )["items"]
            if reference["raw"]["text"] == "Base"
        )
        assert changed_symbol["resolution_control_files"] == ["jsconfig.json"]
        changed_control_hashes = {
            control["file"]: control["content_hash"]
            for control in changed_type["resolution_controls"]
        }
        assert changed_control_hashes["jsconfig.json"] != before_control_hashes["jsconfig.json"]
        assert changed_type["resolution_controls"] != before_type["resolution_controls"]
        _assert_packet(repo, changed)
