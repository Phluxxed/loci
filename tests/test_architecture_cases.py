from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

import pytest

from benchmarks.architecture_cases import (
    load_suite, prepare_snapshots, requests, score, verify_snapshots,
)
from benchmarks.typescript_context_corpus import _isolated_store, _snapshot_files


ROOT = Path(__file__).resolve().parents[1] / "benchmarks"


def _envelope(payload: dict) -> dict:
    payload["usage"] = {"evidence_bytes": sum(
        item["end_byte"] - item["start_byte"] for item in payload.get("sources", [])
    ), "output_bytes": 0}
    result = {"content": [], "structuredContent": payload, "isError": False}
    for _ in range(20):
        size = len(json.dumps(result, ensure_ascii=False, separators=(",", ":")).encode())
        if payload["usage"]["output_bytes"] == size:
            return result
        payload["usage"]["output_bytes"] = size
    raise AssertionError("byte count did not converge")


def _source(repo: Path, name: str) -> dict:
    data = (repo / name).read_bytes()
    return {
        "id": 1, "file": name, "start_byte": 0, "end_byte": len(data),
        "start_line": 1, "end_line": len(data.splitlines()),
        "content_hash": hashlib.sha256(data).hexdigest(),
        "content": data.decode("utf-8"), "source_ref": "source-1",
    }


def test_authored_queries_and_snapshot_inventory(tmp_path: Path) -> None:
    corpus = load_suite(ROOT / "corpora/typescript-context-v1")
    multilingual = load_suite(ROOT / "comparisons/multilingual-context-workflow-v1/inputs")
    assert requests(corpus)[0]["query"] == "processOrder"
    assert requests(multilingual)[0]["query"] == "decode"
    paths = prepare_snapshots(corpus, tmp_path / "fixtures")
    verify_snapshots(corpus, paths)
    repo = Path(paths["imported_interface"])
    (repo / "consumer.ts").write_bytes(b"corrupt")
    with pytest.raises(ValueError, match="snapshot inventory or content differs"):
        verify_snapshots(corpus, paths)
    (repo / "consumer.ts").write_bytes(_snapshot_files(corpus, "imported_interface")["consumer.ts"])
    (repo / "extra.ts").write_text("extra")
    with pytest.raises(ValueError, match="snapshot inventory or content differs"):
        verify_snapshots(corpus, paths)


def test_missing_evidence_is_deficit_and_corruption_is_integrity_failure(tmp_path: Path) -> None:
    corpus = load_suite(ROOT / "corpora/typescript-context-v1")
    repo = Path(prepare_snapshots(corpus, tmp_path / "fixtures")["imported_interface"])
    case = next(item for item in corpus["cases"] if item["id"] == "imported_interface")
    anchor = next(item for item in case["context"] if item["id"] == case["anchor"])
    symbol_id = "consumer.ts::processOrder#function"
    index = {"symbols": [{"id": symbol_id, "file_path": anchor["file"],
                           "name": "processOrder", "kind": "function",
                           "byte_offset": anchor["start_byte"],
                           "byte_length": anchor["end_byte"] - anchor["start_byte"]}],
             "graph": {"edges": []}}
    missing = score(corpus, case["id"], repo, index, [])
    assert missing["integrity_ok"] is True
    assert missing["source_coverage"]["ratio"] == 0
    assert missing["relationships"]["delivered_dependency_links_total"] == 0
    assert missing["preserved_guarantees"]["task_answer_correct"] is None

    packet = _envelope({"anchors": [{"node_id": symbol_id}],
                        "nodes": [{"id": symbol_id}], "sources": [_source(repo, "consumer.ts")],
                        "relationships": []})
    delivered = score(corpus, case["id"], repo, index, [packet, copy.deepcopy(packet)])
    assert delivered["integrity_ok"] is True
    assert delivered["anchor_selection"]["selected"] is True
    assert delivered["source_coverage"]["covered_context_ids"] == ["entry", "import"]
    assert delivered["efficiency"]["repeated_source_bytes"] == len((repo / "consumer.ts").read_bytes())

    corrupted = copy.deepcopy(packet)
    corrupted["structuredContent"]["sources"][0]["content"] = "x" * len(
        corrupted["structuredContent"]["sources"][0]["content"]
    )
    corrupted = _envelope({key: value for key, value in corrupted["structuredContent"].items() if key != "usage"})
    result = score(corpus, case["id"], repo, index, [corrupted])
    assert result["integrity_ok"] is False
    assert result["source_coverage"]["covered"] == 0
    assert result["output_integrity"]["failures"][0]["reason"] == "source_bytes_or_hash_mismatch"


def test_output_accounting_and_schema_failures_are_retained(tmp_path: Path) -> None:
    corpus = load_suite(ROOT / "corpora/typescript-context-v1")
    repo = Path(prepare_snapshots(corpus, tmp_path / "fixtures")["imported_interface"])
    packet = _envelope({"sources": [_source(repo, "consumer.ts")], "relationships": [], "nodes": []})
    packet["structuredContent"]["usage"]["output_bytes"] += 1
    result = score(corpus, "imported_interface", repo, {"symbols": [], "graph": {"edges": []}}, [packet])
    assert result["integrity_ok"] is False
    assert any(item["reason"].startswith("byte_accounting_") for item in result["output_integrity"]["failures"])


def test_live_multilingual_normal_packet_keeps_structural_proof_out_of_semantic_score(tmp_path: Path) -> None:
    from loci import service

    corpus = load_suite(ROOT / "comparisons/multilingual-context-workflow-v1/inputs")
    repo = Path(prepare_snapshots(corpus, tmp_path / "fixtures")["python_contracts"])
    with _isolated_store(tmp_path / "store"):
        service.index_repo(repo, incremental=False)
        index = service.get_store().load(repo)
        assert index is not None
        retrieved = service.retrieve(repo, "decode", ensure_fresh=True, graph_enrichment=True)
        packets = [{"content": [], "structuredContent": retrieved, "isError": False}]
        for item in retrieved["items"]:
            reference = item["source_ref"] if not item["complete"] else None
            while reference:
                page = service.read(repo, reference, ensure_fresh=True)
                packets.append({"content": [], "structuredContent": page, "isError": False})
                reference = page.get("next_source_ref") if not page["complete"] else None
        result = score(corpus, "python_alias_annotation", repo, index, packets)
    assert result["integrity_ok"] is True
    assert result["relationships"]["required_semantic_dependencies_total"] == 3
    assert result["relationships"]["delivered_dependency_links_total"] == 3
    assert result["relationships"]["delivery_integrity_violations"] == []
