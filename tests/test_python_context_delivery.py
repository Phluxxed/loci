"""Bounded end-to-end acceptance for the W4.2 Python context slice."""
from __future__ import annotations

from contextlib import contextmanager
import hashlib
import json
from pathlib import Path

import pytest

from benchmarks.typescript_context_corpus import (
    _isolated_store,
    load_corpus,
    materialize_snapshot,
)
from loci import service


CORPUS_ROOT = Path(__file__).parents[1] / "benchmarks/corpora/multilingual-context-v1"


@pytest.fixture
def corpus():
    return load_corpus(CORPUS_ROOT)


@contextmanager
def _indexed_snapshot(tmp_path: Path, corpus: dict, snapshot: str):
    repo = tmp_path / "snapshot"
    materialize_snapshot(corpus, snapshot, repo)
    with _isolated_store(tmp_path / "store"):
        service.index_repo(repo, incremental=False)
        yield repo


def _case(corpus: dict, case_id: str) -> dict:
    return next(case for case in corpus["cases"] if case["id"] == case_id)


def _edges(result: dict) -> set[tuple[str, str, str]]:
    return {
        (relation["edge"]["from"], relation["edge"]["type"], relation["edge"]["to"])
        for relation in result["relationships"]
    }


def _sources(result: dict) -> dict[int, dict]:
    return {source["id"]: source for source in result["sources"]}


def _items(result: dict) -> dict[str, dict]:
    return {item["id"]: item for item in result["items"]}


def _assert_packet(repo: Path, result: dict) -> None:
    """Check the public packet's byte, source, relationship and path contracts."""

    encoded = json.dumps(
        {"content": [], "structuredContent": result, "isError": False},
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    assert len(encoded) == result["usage"]["output_bytes"]
    assert result["usage"]["evidence_bytes"] <= result["limits"]["max_evidence_bytes"]

    source_by_id = _sources(result)
    item_ids = set(_items(result))
    relation_by_id = {relation["id"]: relation for relation in result["relationships"]}
    for source in source_by_id.values():
        raw = (repo / source["file"]).read_bytes()
        assert source["content_hash"] == hashlib.sha256(raw).hexdigest()
        assert source["content"].encode("utf-8") == raw[source["start_byte"]:source["end_byte"]]
        assert source["start_line"] == raw[:source["start_byte"]].count(b"\n") + 1
        assert source["end_line"] == raw[:source["end_byte"] - 1].count(b"\n") + 1

    for relation in relation_by_id.values():
        assert relation["edge"]["from"] in item_ids
        assert relation["edge"]["to"] in item_ids
        assert relation["traversed"] in {"forward", "reverse"}
        assert relation["source_ids"]
        assert len(relation["source_ids"]) == len(set(relation["source_ids"]))
        assert all(source_id in source_by_id for source_id in relation["source_ids"])

    for item in result["items"]:
        assert item["source_id"] in source_by_id
        assert item["depth"] == len(item["path"])
        assert all(relation_id in relation_by_id for relation_id in item["path"])
        if item["path"]:
            relation = relation_by_id[item["path"][-1]]
            endpoint = "to" if relation["traversed"] == "forward" else "from"
            assert relation["edge"][endpoint] == item["id"]


def _assert_required_context(
    repo: Path,
    result: dict,
    case: dict,
    required_ids: set[str],
    *,
    exact_symbol_ids: set[str] | None = None,
) -> None:
    """Require each frozen context interval to be covered by delivered bytes."""

    exact_symbol_ids = exact_symbol_ids or set()
    delivered = result["sources"]
    for context in case["context"]:
        if context["id"] not in required_ids:
            continue
        raw = (repo / context["file"]).read_bytes()
        start, end = context["start_byte"], context["end_byte"]
        expected = raw[start:end]
        assert hashlib.sha256(expected).hexdigest() == context["sha256"]
        covering = [
            source
            for source in delivered
            if source["file"] == context["file"]
            and source["start_byte"] <= start
            and end <= source["end_byte"]
        ]
        assert covering, f"missing context bytes for {context['id']}"
        assert any(
            source["content"].encode("utf-8")
            [start - source["start_byte"]:end - source["start_byte"]]
            == expected
            for source in covering
        )
        if context.get("symbol") and context["id"] in exact_symbol_ids:
            assert any(
                source["start_byte"] == start and source["end_byte"] == end
                for source in covering
            ), f"definition span was widened for {context['id']}"


def _assert_item_definitions_match_get(repo: Path, result: dict) -> None:
    """Tie delivered definition source to the existing public get endpoint."""

    source_by_id = _sources(result)
    for item in result["items"]:
        if item["kind"] == "file":
            continue
        exact = service.get_symbols_result(repo, [item["id"]])["symbols"]
        assert len(exact) == 1
        assert source_by_id[item["source_id"]]["content"] == exact[0]["source"]


def _relation_sources(result: dict, relation: dict) -> list[dict]:
    source_by_id = _sources(result)
    return [source_by_id[source_id] for source_id in relation["source_ids"]]


def test_python_alias_annotation_delivers_alias_payload_and_reexport_proof(tmp_path, corpus):
    case = _case(corpus, "python_alias_annotation")
    with _indexed_snapshot(tmp_path, corpus, case["snapshot"]) as repo:
        result = service.explore(
            repo,
            intent="type_dependencies",
            seed_ids=["consumer.py::decode#function"],
        )

        assert set(_items(result)) == {
            "consumer.py::decode#function",
            "consumer.py::Alias#type",
            "schema.py::Payload#class",
        }
        assert _edges(result) == {
            (
                "consumer.py::decode#function",
                "uses_type",
                "consumer.py::Alias#type",
            ),
            (
                "consumer.py::decode#function",
                "uses_type",
                "schema.py::Payload#class",
            ),
        }
        # Explore keeps one proof path per selected definition. The additional
        # alias route remains available in the complete type diagnostics below.
        assert any(item["reason"] == "alternative_path" for item in result["omissions"])
        _assert_packet(repo, result)
        _assert_item_definitions_match_get(repo, result)
        _assert_required_context(
            repo,
            result,
            case,
            {"entry", "alias", "payload", "import", "reexport"},
            exact_symbol_ids={"entry", "alias", "payload"},
        )

        symbol_refs = service.graph_references(
            repo, file="consumer.py", status="resolved", family="symbol"
        )["items"]
        p_refs = [reference for reference in symbol_refs if reference["raw"]["text"] == "P"]
        assert p_refs
        for reference in p_refs:
            assert reference["target_id"] == "schema.py::Payload#class"
            assert reference["binding"]["local_name"] == "P"
            assert reference["binding"]["imported_name"] == "Exported"
            assert {item["kind"] for item in reference["support"]} >= {
                "import_binding",
                "reexport",
                "definition",
            }
            assert {item["file"] for item in reference["support"]} >= {
                "consumer.py",
                "barrel.py",
                "schema.py",
            }

        type_refs = service.graph_references(
            repo, file="consumer.py", family="type", status="resolved"
        )["items"]
        assert any(
            reference["source_id"] == "consumer.py::Alias#type"
            and reference["target_id"] == "schema.py::Payload#class"
            for reference in type_refs
        )
        assert any(
            reference["raw"]["path"] == ["P"]
            and reference["target_id"] == "schema.py::Payload#class"
            and reference["raw"]["import_bindings"][0]["local_name"] == "P"
            for reference in type_refs
        )


def test_python_direct_base_and_literal_forward_keep_authored_meaning(tmp_path, corpus):
    case = _case(corpus, "python_base_and_literal_forward")
    with _indexed_snapshot(tmp_path, corpus, case["snapshot"]) as repo:
        child = service.explore(
            repo,
            intent="type_dependencies",
            seed_ids=["consumer.py::Child#class"],
        )
        assert set(_items(child)) == {
            "consumer.py::Child#class",
            "schema.py::Base#class",
        }
        assert _edges(child) == {
            (
                "consumer.py::Child#class",
                "extends",
                "schema.py::Base#class",
            )
        }
        assert "schema.py::Payload#class" not in _items(child)
        _assert_packet(repo, child)
        _assert_item_definitions_match_get(repo, child)
        _assert_required_context(
            repo,
            child,
            case,
            {"entry", "base", "base_import"},
            exact_symbol_ids={"entry", "base"},
        )

        later = service.explore(
            repo,
            intent="type_dependencies",
            seed_ids=["consumer.py::later#function"],
        )
        assert set(_items(later)) == {
            "consumer.py::later#function",
            "schema.py::Payload#class",
        }
        assert _edges(later) == {
            (
                "consumer.py::later#function",
                "uses_type",
                "schema.py::Payload#class",
            )
        }
        _assert_packet(repo, later)
        _assert_item_definitions_match_get(repo, later)
        _assert_required_context(
            repo,
            later,
            case,
            {"later", "payload", "import", "reexport"},
            exact_symbol_ids={"later", "payload"},
        )
        assert all(
            relation["edge"]["type"] != "mro"
            for relation in child["relationships"] + later["relationships"]
        )


def test_python_known_call_impact_delivers_incoming_call_and_proof(tmp_path, corpus):
    case = _case(corpus, "python_known_call_impact")
    with _indexed_snapshot(tmp_path, corpus, case["snapshot"]) as repo:
        calls = service.graph_calls(repo, file="app.py", status="resolved")
        assert calls["counts"] == {"total": 1, "resolved": 1, "unresolved": 0, "returned": 1}
        call, = calls["items"]
        assert call["caller_id"] == "app.py::caller#function"
        assert call["target_id"] == "lib.py::target#function"
        assert call["raw"]["callee_text"] == "alias"
        assert {item["kind"] for item in call["support"]} == {
            "call_site",
            "caller_definition",
            "symbol_reference",
        }

        result = service.explore(
            repo,
            intent="impact",
            seed_ids=["lib.py::target#function"],
        )
        assert list(_items(result)) == [
            "lib.py::target#function",
            "app.py::caller#function",
        ]
        assert _edges(result) == {
            (
                "app.py::caller#function",
                "calls",
                "lib.py::target#function",
            )
        }
        relation, = result["relationships"]
        assert relation["traversed"] == "reverse"
        assert {source["file"] for source in _relation_sources(result, relation)} >= {
            "app.py",
            "lib.py",
        }
        _assert_packet(repo, result)
        _assert_item_definitions_match_get(repo, result)
        _assert_required_context(
            repo,
            result,
            case,
            {"entry", "caller", "import"},
            exact_symbol_ids={"entry", "caller"},
        )


def test_python_loci_bundle_contract_preserves_shared_context_shape(tmp_path, corpus):
    case = _case(corpus, "python_loci_bundle_contract")
    with _indexed_snapshot(tmp_path, corpus, case["snapshot"]) as repo:
        result = service.explore(
            repo,
            intent="type_dependencies",
            query=case["prompt"],
            seed_ids=["src/loci/_exploration_output.py::_validate_bundle#function"],
        )
        assert set(_items(result)) == {
            "src/loci/_exploration_output.py::_validate_bundle#function",
            "src/loci/_exploration_output.py::Bundle#class",
            "src/loci/_exploration_output.py::Span#class",
            "src/loci/_exploration_output.py::Relation#class",
        }
        assert _edges(result) == {
            (
                "src/loci/_exploration_output.py::_validate_bundle#function",
                "uses_type",
                "src/loci/_exploration_output.py::Bundle#class",
            ),
            (
                "src/loci/_exploration_output.py::Bundle#class",
                "uses_type",
                "src/loci/_exploration_output.py::Span#class",
            ),
            (
                "src/loci/_exploration_output.py::Bundle#class",
                "uses_type",
                "src/loci/_exploration_output.py::Relation#class",
            ),
        }
        assert any(item["reason"] == "alternative_path" for item in result["omissions"])
        records = service.graph_references(repo, family="type", status="resolved")["items"]
        assert any(
            record["source_id"] == "src/loci/_exploration_output.py::Relation#class"
            and record["target_id"] == "src/loci/_exploration_output.py::Span#class"
            for record in records
        )
        _assert_packet(repo, result)
        _assert_item_definitions_match_get(repo, result)
        _assert_required_context(
            repo,
            result,
            case,
            {"entry", "bundle", "span", "relation"},
            exact_symbol_ids={"entry", "bundle", "span", "relation"},
        )
        entry = _items(result)[
            "src/loci/_exploration_output.py::_validate_bundle#function"
        ]
        assert "bundle requires a definition source" in _sources(result)[entry["source_id"]]["content"]


def test_python_unproven_contracts_never_guess_origins_or_computed_targets(tmp_path, corpus):
    case = _case(corpus, "python_unproven_contracts")
    with _indexed_snapshot(tmp_path, corpus, case["snapshot"]) as repo:
        unknown = service.explore(
            repo,
            intent="type_dependencies",
            seed_ids=["negative.py::unknown#function"],
        )
        assert set(_items(unknown)) == {"negative.py::unknown#function"}
        assert not unknown["relationships"]
        assert any(item["reason"] == "unresolved_relation" for item in unknown["omissions"])
        _assert_packet(repo, unknown)
        _assert_item_definitions_match_get(repo, unknown)
        _assert_required_context(
            repo,
            unknown,
            case,
            {"entry"},
            exact_symbol_ids={"entry"},
        )

        type_page = service.graph_references(
            repo, file="negative.py", family="type", status="all"
        )
        records = type_page["items"]
        assert records
        assert all(record["status"] == "unresolved" for record in records)
        assert all(record["target_id"] is None for record in records)
        assert all(record["target_file"] is None for record in records)

        source_lines = (repo / "negative.py").read_text(encoding="utf-8").splitlines()
        nested_line = next(index for index, line in enumerate(source_lines, 1) if "def nested" in line)
        generic_line = next(index for index, line in enumerate(source_lines, 1) if "def generic" in line)
        shadowed = [
            record for record in records
            if record["raw"]["line"] == nested_line and record["raw"]["text"] == "P"
        ]
        generic = [
            record for record in records
            if record["raw"]["line"] == generic_line and record["raw"]["text"] == "P"
        ]
        assert shadowed and generic
        assert all(record["target_id"] is None for record in shadowed + generic)
        assert any(
            any(binding["name"] == "P" for binding in record["raw"]["local_bindings"])
            for record in shadowed
        )
        assert any(record["unresolved_reason"] == "type_parameter" for record in generic)

        forbidden = {
            "wrong.py::Payload#class",
            "model.py::Payload#class",
            "left.py::Choice#class",
            "right.py::Choice#class",
        }
        assert not forbidden.intersection(
            {record["target_id"] for record in records if record["target_id"]}
        )
        dynamic = service.explore(
            repo,
            intent="type_dependencies",
            seed_ids=["negative.py::Dynamic#class"],
        )
        assert set(_items(dynamic)) == {"negative.py::Dynamic#class"}
        assert not dynamic["relationships"]
        assert not forbidden.intersection(set(_items(dynamic)))
        assert not any(
            item["target_id"] in forbidden
            for item in records
            if item["target_id"]
        )


def test_python_zero_and_reduced_evidence_are_explicit_omissions(tmp_path, corpus):
    case = _case(corpus, "python_alias_annotation")
    with _indexed_snapshot(tmp_path, corpus, case["snapshot"]) as repo:
        full = service.explore(
            repo,
            intent="type_dependencies",
            seed_ids=["consumer.py::decode#function"],
        )
        anchor = _items(full)["consumer.py::decode#function"]
        anchor_source = _sources(full)[anchor["source_id"]]
        anchor_bytes = anchor_source["end_byte"] - anchor_source["start_byte"]

        reduced = service.explore(
            repo,
            intent="type_dependencies",
            seed_ids=["consumer.py::decode#function"],
            max_evidence_bytes=anchor_bytes,
        )
        assert set(_items(reduced)) == {"consumer.py::decode#function"}
        assert not reduced["relationships"]
        assert reduced["usage"]["evidence_bytes"] <= anchor_bytes
        assert any(
            item["reason"] in {"evidence_budget", "ancestor_unavailable"}
            for item in reduced["omissions"]
        )
        _assert_packet(repo, reduced)

        empty = service.explore(
            repo,
            intent="type_dependencies",
            seed_ids=["consumer.py::decode#function"],
            max_evidence_bytes=0,
        )
        assert empty["status"] == "empty"
        assert not empty["items"] and not empty["relationships"] and not empty["sources"]
        assert empty["usage"]["evidence_bytes"] == 0
        assert any(item["reason"] == "evidence_budget" for item in empty["omissions"])
        _assert_packet(repo, empty)


def test_python_context_refreshes_source_target_and_reexport_support(tmp_path, corpus):
    case = _case(corpus, "python_alias_annotation")
    with _indexed_snapshot(tmp_path, corpus, case["snapshot"]) as repo:
        before = service.explore(
            repo,
            intent="type_dependencies",
            seed_ids=["consumer.py::decode#function"],
        )
        before_anchor = _sources(before)[_items(before)["consumer.py::decode#function"]["source_id"]]
        before_target = next(
            source for source in before["sources"]
            if source["file"] == "schema.py" and "class Payload" in source["content"]
        )

        target = repo / "schema.py"
        target.write_text(
            target.read_text(encoding="utf-8").replace("request_id: str", "request_id: bytes"),
            encoding="utf-8",
        )
        changed_target = service.explore(
            repo,
            intent="type_dependencies",
            seed_ids=["consumer.py::decode#function"],
            ensure_fresh=True,
        )
        assert any(
            source["file"] == "schema.py" and "request_id: bytes" in source["content"]
            for source in changed_target["sources"]
        )
        assert _edges(changed_target) == _edges(before)
        _assert_packet(repo, changed_target)

        barrel = repo / "barrel.py"
        consumer = repo / "consumer.py"
        barrel.write_text("from schema import Payload as Public\n", encoding="utf-8")
        consumer.write_text(
            consumer.read_text(encoding="utf-8").replace(
                "from barrel import Exported as P",
                "from barrel import Public as P",
            ),
            encoding="utf-8",
        )
        changed_reexport = service.explore(
            repo,
            intent="type_dependencies",
            seed_ids=["consumer.py::decode#function"],
            ensure_fresh=True,
        )
        assert "schema.py::Payload#class" in _items(changed_reexport)
        assert _edges(changed_reexport) == _edges(before)
        relation_sources = [
            source
            for relation in changed_reexport["relationships"]
            for source in _relation_sources(changed_reexport, relation)
        ]
        assert any(source["file"] == "barrel.py" and "Public" in source["content"] for source in relation_sources)
        _assert_packet(repo, changed_reexport)

        consumer.write_text(
            consumer.read_text(encoding="utf-8").replace("return [value]", "return [value, value]"),
            encoding="utf-8",
        )
        changed_source = service.explore(
            repo,
            intent="type_dependencies",
            seed_ids=["consumer.py::decode#function"],
            ensure_fresh=True,
        )
        current_anchor = _sources(changed_source)[
            _items(changed_source)["consumer.py::decode#function"]["source_id"]
        ]
        assert "return [value, value]" in current_anchor["content"]
        assert current_anchor["content_hash"] != before_anchor["content_hash"]
        assert before_target["content_hash"] != next(
            source["content_hash"]
            for source in changed_source["sources"]
            if source["file"] == "schema.py" and "class Payload" in source["content"]
        )
        _assert_packet(repo, changed_source)
