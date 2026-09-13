"""Deterministic scorer checks before any multilingual provider outcomes."""
from __future__ import annotations

import copy
from pathlib import Path

import pytest

from benchmarks.multilingual_context_inputs import load_inputs
from benchmarks.multilingual_context_relationships import score_relationships, validate_relation_mappings
from benchmarks.typescript_context_corpus import _isolated_store, materialize_snapshot
from loci import service


def _indexed(corpus: dict, snapshot: str, tmp_path: Path) -> tuple[Path, dict]:
    repo = tmp_path / snapshot
    materialize_snapshot(corpus, snapshot, repo)
    service.index_repo(repo, incremental=False)
    index = service.get_store().load(repo.resolve())
    assert index is not None
    return repo, index


def test_all_50_frozen_meanings_map_to_actual_persisted_records(tmp_path: Path) -> None:
    corpus, _ = load_inputs()
    validate_relation_mappings(corpus)
    required = available = forbidden = 0
    with _isolated_store(tmp_path / "store"):
        for snapshot in corpus["snapshots"]:
            _repo, index = _indexed(corpus, snapshot, tmp_path)
            for case in (item for item in corpus["cases"] if item["snapshot"] == snapshot):
                scored = score_relationships(case, index, [], [])
                required += scored["required_semantic_dependencies_total"]
                available += scored["available_dependency_links_total"]
                forbidden += scored["forbidden_proven_relationships"]
                assert scored["endpoint_issues"] == []
    assert (required, available, forbidden) == (50, 50, 0)


def test_actual_product_packets_deliver_all_18_frozen_meaning_kinds(tmp_path: Path) -> None:
    corpus, _ = load_inputs()
    observed: set[str] = set()
    with _isolated_store(tmp_path / "store"):
        for snapshot in corpus["snapshots"]:
            repo, index = _indexed(corpus, snapshot, tmp_path)
            for case in (item for item in corpus["cases"] if item["snapshot"] == snapshot and item["relationships"]):
                available = score_relationships(case, index, [], [])
                requests: set[tuple[str, str]] = set()
                for relation in available["required_semantic_dependencies"]:
                    edge = relation["available_edges"][0]
                    if relation["graph_type"] == "calls":
                        requests.update({("dependencies", edge["from"]), ("impact", edge["to"])})
                    else:
                        intent = "dependencies" if case["language"] == "javascript" else "type_dependencies"
                        requests.add((intent, edge["from"]))
                packets = [
                    service.explore(
                        repo, intent=intent, seed_ids=[seed],
                        max_output_bytes=16_384, max_evidence_bytes=8_192,
                    )
                    for intent, seed in sorted(requests)
                ]
                scored = score_relationships(case, index, packets)
                assert scored["delivered_dependency_links_total"] == scored["required_semantic_dependencies_total"]
                assert scored["delivery_integrity_violations"] == []
                observed.update(item["kind"] for item in scored["delivered_dependency_links"])
    assert observed == {
        relation["kind"] for case in corpus["cases"] for relation in case["relationships"]
    }
    assert len(observed) == 18


def test_actual_explore_proof_is_required_for_every_delivered_claim(tmp_path: Path) -> None:
    corpus, _ = load_inputs()
    case = next(item for item in corpus["cases"] if item["id"] == "python_alias_annotation")
    with _isolated_store(tmp_path / "store"):
        repo, index = _indexed(corpus, case["snapshot"], tmp_path)
        packet = service.explore(
            repo,
            intent="type_dependencies",
            seed_ids=["consumer.py::decode#function"],
            max_output_bytes=16_384,
            max_evidence_bytes=8_192,
        )
        valid = score_relationships(case, index, [packet])
        assert valid["delivered_dependency_links_total"] >= 1
        assert valid["delivery_integrity_violations"] == []

        incomplete = copy.deepcopy(packet)
        # Keep the packet structurally referential, but replace complete edge
        # proof with only the anchor source.
        anchor_source = next(
            item["source_id"] for item in incomplete["items"]
            if item["id"] == "consumer.py::decode#function"
        )
        incomplete["relationships"][0]["source_ids"] = [anchor_source]
        scored = score_relationships(case, index, [incomplete])
        assert scored["delivered_dependency_links_total"] < valid["delivered_dependency_links_total"]
        assert any("complete persisted proof" in item["reason"] for item in scored["delivery_integrity_violations"])


def test_wrong_origin_record_is_detected_and_unknown_kind_is_rejected(tmp_path: Path) -> None:
    corpus, _ = load_inputs()
    case = next(item for item in corpus["cases"] if item["id"] == "python_alias_annotation")
    with _isolated_store(tmp_path / "store"):
        _repo, original = _indexed(corpus, case["snapshot"], tmp_path)
        index = copy.deepcopy(original)
        record = next(
            item for item in index["graph"]["type_relations"]
            if item.get("source_id") == "consumer.py::decode#function"
            and item.get("target_id") == "schema.py::Payload#class"
        )
        edge = next(
            item for item in index["graph"]["edges"]
            if item.get("from") == record["source_id"] and item.get("to") == record["target_id"]
            and item.get("type") == record["raw"]["relation"]
            and item.get("evidence", {}).get("line") == record["raw"]["line"]
        )
        wrong_record, wrong_edge = copy.deepcopy(record), copy.deepcopy(edge)
        wrong_record.update(target_id="wrong.py::Payload#class", target_file="wrong.py")
        wrong_edge["to"] = "wrong.py::Payload#class"
        index["graph"]["type_relations"].append(wrong_record)
        index["graph"]["edges"].append(wrong_edge)
        scored = score_relationships(case, index, [], [])
        assert scored["forbidden_available_relationships"] == 1
        assert scored["forbidden_proven_relationships"] == 1

    invalid = copy.deepcopy(corpus)
    invalid["cases"][0]["relationships"][0]["kind"] = "unknown_future_kind"
    with pytest.raises(ValueError, match="unsupported multilingual relationship mappings"):
        validate_relation_mappings(invalid)
