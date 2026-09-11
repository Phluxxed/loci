"""W2.4 deterministic source-selection evidence against frozen Anvil gold.

Run with: python -m tests.reproductions.exploration.maintained --output PATH
No agent calls, comparison scoring or frozen-artifact changes.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import tempfile

from benchmarks.typescript_context_corpus import (
    _isolated_store,
    load_corpus,
    materialize_snapshot,
)
from loci import service
from loci.graph.contracts import GRAPH_STATE_SCHEMA_VERSION
from loci.storage.index_store import EXTRACTOR_VERSION, IndexStore


TYPE_KINDS = frozenset({
    "parameter_type",
    "property_type",
    "type_query",
    "return_type",
    "intersection_member",
})
BASELINE_PATH = Path("docs/evidence/2026-09-11-w23-maintained.json")


def _canonical_envelope(result: dict) -> bytes:
    return json.dumps(
        {"content": [], "structuredContent": result, "isError": False},
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")


def _source_union_bytes(sources: list[dict]) -> int:
    intervals: dict[tuple[str, str], list[tuple[int, int]]] = {}
    for source in sources:
        key = (source["file"], source["content_hash"])
        intervals.setdefault(key, []).append(
            (source["start_byte"], source["end_byte"])
        )
    total = 0
    for values in intervals.values():
        end = -1
        for start, stop in sorted(values):
            if start > end:
                total += stop - start
            elif stop > end:
                total += stop - end
            end = max(end, stop)
    return total


def _resolve_ids(case: dict, index: dict) -> dict[str, str]:
    ids: dict[str, str] = {}
    for item in case["context"]:
        symbol = item.get("symbol")
        if symbol is None:
            continue
        matches = [
            value
            for value in index["symbols"]
            if value["file_path"] == item["file"]
            and value["name"] == symbol["name"]
            and value["kind"] == symbol["kind"]
            and item["start_byte"] <= value["byte_offset"]
            and value["byte_offset"] + value["byte_length"] <= item["end_byte"]
        ]
        if len(matches) != 1:
            raise AssertionError((case["id"], item["id"], matches))
        ids[item["id"]] = matches[0]["id"]
    return ids


def _capture(
    repo: Path,
    case: dict,
    ids: dict[str, str],
    *,
    max_output_bytes: int,
    max_evidence_bytes: int,
) -> dict:
    anchor_id = ids[case["anchor"]]
    required = sorted({
        ids[relation["to"]]
        for relation in case["relationships"]
        if relation["kind"] in TYPE_KINDS
    })
    result = service.explore(
        repo,
        query=case["prompt"],
        intent="type_dependencies",
        seed_ids=[anchor_id],
        max_output_bytes=max_output_bytes,
        max_evidence_bytes=max_evidence_bytes,
    )
    envelope = _canonical_envelope(result)
    delivered_items = [item["id"] for item in result["items"]]
    delivered_related = [item_id for item_id in delivered_items if item_id != anchor_id]
    missing = sorted(set(required) - set(delivered_related))
    extras = sorted(set(delivered_related) - set(required))
    evidence_bytes = _source_union_bytes(result["sources"])
    if len(envelope) != result["usage"]["output_bytes"]:
        raise AssertionError((case["id"], "output_bytes", len(envelope), result["usage"]))
    if evidence_bytes != result["usage"]["evidence_bytes"]:
        raise AssertionError((case["id"], "evidence_bytes", evidence_bytes, result["usage"]))
    return {
        "request": {
            "intent": "type_dependencies",
            "query": case["prompt"],
            "seed_ids": [anchor_id],
            "max_output_bytes": max_output_bytes,
            "max_evidence_bytes": max_evidence_bytes,
        },
        "anchor_id": anchor_id,
        "required_type_target_ids": required,
        "delivered_item_ids": delivered_items,
        "delivered_related_type_definition_ids": delivered_related,
        "missing_required_type_target_ids": missing,
        "extra_definition_ids": extras,
        "omissions": result["omissions"],
        "status": result["status"],
        "canonical_output_bytes": len(envelope),
        "canonical_output_sha256": hashlib.sha256(envelope).hexdigest(),
        "evidence_bytes": result["usage"]["evidence_bytes"],
        "reported_output_bytes": result["usage"]["output_bytes"],
        "reported_estimated_tokens": result["usage"]["estimated_tokens"],
        "source_bytes_union_recomputed": evidence_bytes,
        "response": result,
    }


def _baseline(corpus: dict) -> dict:
    raw = BASELINE_PATH.read_bytes()
    baseline = json.loads(raw)
    expected_corpus = (Path(corpus["_root"]) / "corpus.sha256").read_text().strip()
    expected_snapshot = corpus["snapshots"]["anvil"]["archive_sha256"]
    if baseline["corpus_sha256"] != expected_corpus or baseline["snapshot_sha256"] != expected_snapshot:
        raise AssertionError("W2.3 baseline corpus/snapshot does not match frozen corpus")
    counts = {case["id"]: len(case["delivered_type_definitions"])
              for case in baseline["cases"]}
    expected = {
        "anvil_temporal_arguments": 4,
        "anvil_retrieval_limits": 12,
        "anvil_renderer_result_contract": 14,
    }
    if counts != expected:
        raise AssertionError((counts, expected))
    return {
        "work_id": "W2.3",
        "source": str(BASELINE_PATH),
        "source_sha256": hashlib.sha256(raw).hexdigest(),
        "related_definition_counts": counts,
        "meaning": (
            "Deterministic selection/source-volume comparison only; no agent-efficiency "
            "claim and no complete-answer coverage claim. W2.3 counts include helper/call "
            "context outside W2.4's type_dependencies intent."
        ),
    }


def verify() -> dict:
    corpus = load_corpus()
    corpus_sha256 = (Path(corpus["_root"]) / "corpus.sha256").read_text().strip()
    result = {
        "work_id": "W2.4",
        "schema_version": 1,
        "meaning": (
            "Deterministic explicit type_dependencies source-selection evidence; all "
            "omissions, misses and extras are retained. No agent-efficiency or complete-"
            "answer coverage claim."
        ),
        "corpus_sha256": corpus_sha256,
        "snapshot_id": "anvil",
        "snapshot_sha256": corpus["snapshots"]["anvil"]["archive_sha256"],
        "baseline": _baseline(corpus),
        "extractor_version": EXTRACTOR_VERSION,
        "graph_schema_version": GRAPH_STATE_SCHEMA_VERSION,
        "cases": [],
    }
    with tempfile.TemporaryDirectory(prefix="loci-w24-maintained-") as directory:
        temp = Path(directory)
        repo, base = temp / "anvil", temp / "store"
        materialize_snapshot(corpus, "anvil", repo)
        with _isolated_store(base):
            info = service.index_repo(repo, incremental=False)
            if info.get("graph_status") != "healthy":
                raise AssertionError(info)
            index = IndexStore(base_dir=base).load(repo.resolve())
            if index is None:
                raise AssertionError("fresh snapshot index missing")
            result["index"] = {
                "graph_status": info.get("graph_status"),
                "symbol_count": len(index["symbols"]),
                "type_observations": len(index["graph"]["type_relations"]),
                "fresh_single_index": True,
            }
            for case in corpus["cases"]:
                if case["snapshot"] != "anvil":
                    continue
                ids = _resolve_ids(case, index)
                exact = _capture(
                    repo,
                    case,
                    ids,
                    max_output_bytes=16384,
                    max_evidence_bytes=8192,
                )
                relaxed = _capture(
                    repo,
                    case,
                    ids,
                    max_output_bytes=262144,
                    max_evidence_bytes=65536,
                )
                result["cases"].append({
                    "id": case["id"],
                    "anchor_context_id": case["anchor"],
                    "resolved_ids": ids,
                    "default": exact,
                    "relaxed": relaxed,
                })
    if len(result["cases"]) != 3:
        raise AssertionError(len(result["cases"]))
    result["passed"] = True
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = verify()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({
        "passed": result["passed"],
        "cases": len(result["cases"]),
        "output": str(args.output),
        "default_statuses": [case["default"]["status"] for case in result["cases"]],
        "relaxed_statuses": [case["relaxed"]["status"] for case in result["cases"]],
    }))


if __name__ == "__main__":
    main()
