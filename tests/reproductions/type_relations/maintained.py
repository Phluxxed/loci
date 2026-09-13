"""W2.3 deterministic acceptance against independent, frozen Anvil source gold.

Run with: python -m tests.reproductions.type_relations.maintained --output PATH
No agent calls, comparison scoring or frozen-artifact changes.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import tempfile

from benchmarks.typescript_context_corpus import (
    _isolated_store, load_corpus, materialize_snapshot,
)
from loci import service
from loci.graph.contracts import GRAPH_STATE_SCHEMA_VERSION
from loci.storage.index_store import EXTRACTOR_VERSION, IndexStore


TYPE_KINDS = frozenset({
    "parameter_type", "property_type", "type_query", "return_type", "intersection_member",
})


def verify() -> dict:
    corpus = load_corpus()
    result = {
        "work_id": "W2.3", "schema_version": 1,
        "meaning": "Deterministic authored relationship and opt-in source availability; no agent-efficiency claim.",
        "corpus_sha256": (Path(corpus["_root"]) / "corpus.sha256").read_text().strip(),
        "snapshot_sha256": corpus["snapshots"]["anvil"]["archive_sha256"],
        "extractor_version": EXTRACTOR_VERSION,
        "graph_schema_version": GRAPH_STATE_SCHEMA_VERSION,
        "cases": [],
    }
    with tempfile.TemporaryDirectory(prefix="loci-w23-maintained-") as directory:
        temp = Path(directory)
        repo, base = temp / "anvil", temp / "store"
        materialize_snapshot(corpus, "anvil", repo)
        with _isolated_store(base):
            info = service.index_repo(repo, incremental=False)
            assert info["graph_status"] == "healthy", info
            index = IndexStore(base_dir=base).load(repo)
            assert index is not None
            result["type_observations"] = len(index["graph"]["type_relations"])
            for case in corpus["cases"]:
                if case["snapshot"] != "anvil":
                    continue
                ids = {}
                for item in case["context"]:
                    if item["symbol"] is None:
                        continue
                    matches = [s for s in index["symbols"]
                               if s["file_path"] == item["file"]
                               and s["name"] == item["symbol"]["name"]
                               and s["kind"] == item["symbol"]["kind"]
                               and item["start_byte"] <= s["byte_offset"]
                               and s["byte_offset"] + s["byte_length"] <= item["end_byte"]]
                    assert len(matches) == 1, (case["id"], item["id"], matches)
                    ids[item["id"]] = matches[0]["id"]
                wanted = []
                for relation in case["relationships"]:
                    assert relation["kind"] in TYPE_KINDS | {"calls"}
                    kind = "uses_type" if relation["kind"] in TYPE_KINDS else "calls"
                    edges = [e for e in index["graph"]["edges"]
                             if e["from"] == ids[relation["from"]]
                             and e["to"] == ids[relation["to"]] and e["type"] == kind]
                    assert len(edges) == 1, (case["id"], relation, edges)
                    wanted.append({"gold": relation, "edge": edges[0]})
                exact = service.get_symbols_result(repo, [ids[case["anchor"]]])
                expanded = service.get_symbols_result(repo, [ids[case["anchor"]]], include_type_context=True)
                assert expanded["symbols"] == exact["symbols"]
                context = expanded["type_context"]
                delivered = {s["id"] for s in context["symbols"]}
                required_types = {ids[r["to"]] for r in case["relationships"] if r["kind"] in TYPE_KINDS}
                assert required_types <= delivered, (case["id"], required_types - delivered)
                result["cases"].append({
                    "id": case["id"], "ids": ids, "required_edges": wanted,
                    "required_type_definitions": sorted(required_types),
                    "delivered_type_definitions": sorted(delivered),
                    "omissions": context["omissions"],
                    "default_get_preserved": True,
                })
    assert len(result["cases"]) == 3
    result["passed"] = True
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = verify()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({"passed": result["passed"], "cases": len(result["cases"]),
                      "type_observations": result["type_observations"]}))


if __name__ == "__main__":
    main()
