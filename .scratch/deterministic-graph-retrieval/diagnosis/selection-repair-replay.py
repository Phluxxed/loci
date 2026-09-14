#!/usr/bin/env python3
"""Verify staged normal retrieval against the fixed Anvil source."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
from typing import Any


CAPTURE = "src/tool-results/service.ts::CaptureCommandResultOptions#type"
BINDING = "src/work-context/binding.ts::WorkContextBinding#type"
RUN_BROWSER = "src/browser/cli.ts::runBrowserCli#function"
BROWSER_USAGE = "src/browser/cli.ts::browserCliUsage#function"
MAIN = "bin/anvil.ts::main#function"
RENDER_ACTIVE = "src/continuity/render.ts::renderActiveTask#function"
TRUNCATE = "src/continuity/render.ts::truncateText#function"
RENDER_FRAME = "src/continuity/render.ts::renderContinuityFrame#function"


def source_manifest(repo: Path) -> dict[str, Any]:
    entries = []
    for path in sorted(item for item in repo.rglob("*") if item.is_file()):
        data = path.read_bytes()
        entries.append({
            "file": path.relative_to(repo).as_posix(),
            "bytes": len(data),
            "sha256": hashlib.sha256(data).hexdigest(),
        })
    encoded = json.dumps(entries, sort_keys=True, separators=(",", ":")).encode()
    return {
        "file_count": len(entries),
        "total_bytes": sum(item["bytes"] for item in entries),
        "manifest_sha256": hashlib.sha256(encoded).hexdigest(),
    }


def edge_key(relation: dict[str, Any]) -> tuple[str, str, str]:
    edge = relation["edge"]
    return edge["from"], edge["type"], edge["to"]


def summarize(result: dict[str, Any], required: set[tuple[str, str, str]]) -> dict[str, Any]:
    sources = {source["id"]: source for source in result["sources"]}
    selected = []
    for relation in result["relationships"]:
        key = edge_key(relation)
        if key not in required:
            continue
        selected.append({
            "edge": relation["edge"],
            "traversed": relation["traversed"],
            "proof": relation["proof"],
            "source_ids": relation["source_ids"],
            "proof_sources": [
                {
                    "id": source_id,
                    "file": sources[source_id]["file"],
                    "start_byte": sources[source_id]["start_byte"],
                    "end_byte": sources[source_id]["end_byte"],
                    "start_line": sources[source_id]["start_line"],
                    "end_line": sources[source_id]["end_line"],
                    "content_hash": sources[source_id]["content_hash"],
                    "content_bytes": len(sources[source_id]["content"].encode()),
                }
                for source_id in relation["source_ids"]
            ],
        })
    return {
        "status": result["status"],
        "snapshot": result["snapshot"],
        "required_edges": [
            {"from": source, "type": edge_type, "to": target}
            for source, edge_type, target in sorted(required)
        ],
        "required_edges_delivered": [edge_key(item) for item in selected],
        "required_edge_count": len(selected),
        "selected_relationships": selected,
        "all_relationships": [
            {
                "edge": relation["edge"],
                "traversed": relation["traversed"],
                "source_ids": relation["source_ids"],
                "proof": relation["proof"],
            }
            for relation in result["relationships"]
        ],
        "nodes": [node["id"] for node in result["nodes"]],
        "items": [item["node_id"] for item in result["items"]],
        "omissions": result["omissions"],
        "limits": result["limits"],
        "usage": result["usage"],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", required=True, type=Path)
    parser.add_argument("--store", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    repo = args.repo.resolve()
    store_root = args.store.resolve()
    output = args.output.resolve()
    if repo != Path("/tmp/anvil-source-tasks-20260914/t23").resolve():
        raise SystemExit(f"unexpected fixed source: {repo}")
    if "selection-" not in str(store_root):
        raise SystemExit(f"store must be task-specific: {store_root}")
    os.environ["LOCI_BASE_DIR"] = str(store_root)

    from loci import service
    from loci.retrieval import retrieve_context

    before = source_manifest(repo)
    index_summary = service.index_repo(repo, incremental=False)
    store = service.get_store()
    index = store.load(repo)
    if index is None:
        raise RuntimeError("fresh isolated index is missing")
    nodes = {node["id"]: node for node in index["symbols"]}
    state = store.validate_graph_state(index)

    requests = (
        (
            "capture_query",
            "CaptureCommandResultOptions",
            None,
            {(CAPTURE, "uses_type", BINDING)},
            True,
        ),
        (
            "binding_query",
            "WorkContextBinding",
            None,
            {(CAPTURE, "uses_type", BINDING)},
            False,
        ),
        (
            "explicit_pair",
            "binding contract",
            [CAPTURE, BINDING],
            {(CAPTURE, "uses_type", BINDING)},
            True,
        ),
        (
            "browser_control",
            "runBrowserCli",
            None,
            {
                (RUN_BROWSER, "calls", BROWSER_USAGE),
                (MAIN, "calls", RUN_BROWSER),
            },
            True,
        ),
        (
            "renderer_control",
            "renderActiveTask",
            None,
            {
                (RENDER_ACTIVE, "calls", TRUNCATE),
                (RENDER_FRAME, "calls", RENDER_ACTIVE),
            },
            True,
        ),
    )
    results = {}
    for label, query, seeds, required, require_all in requests:
        first = retrieve_context(
            repo, store, nodes, state, query, seed_ids=seeds, coverage="partial"
        )
        second = retrieve_context(
            repo, store, nodes, state, query, seed_ids=seeds, coverage="partial"
        )
        if first != second:
            raise AssertionError(f"non-deterministic repeated result: {label}")
        summary = summarize(first, required)
        delivered = {
            edge_key(relation) for relation in first["relationships"]
            if edge_key(relation) in required
        }
        if require_all and delivered != required:
            raise AssertionError(
                f"{label} missing required edges: {sorted(required - delivered)}"
            )
        if any(relation["proof"] != "complete" for relation in first["relationships"]):
            raise AssertionError(f"{label} returned incomplete relationship proof")
        if first["usage"]["output_bytes"] > first["limits"]["max_output_bytes"]:
            raise AssertionError(f"{label} exceeded output limit")
        if first["usage"]["evidence_bytes"] > first["limits"]["max_evidence_bytes"]:
            raise AssertionError(f"{label} exceeded evidence limit")
        summary["request"] = {"query": query, "seed_ids": seeds}
        summary["deterministic_repeat_equal"] = True
        summary["require_all_selected_edges"] = require_all
        results[label] = summary

    browser_proof_files = {
        source["file"]
        for relation in results["browser_control"]["selected_relationships"]
        if edge_key(relation) == (MAIN, "calls", RUN_BROWSER)
        for source in relation["proof_sources"]
    }
    if "src/browser/index.ts" not in browser_proof_files:
        raise AssertionError("browser reverse call lost public barrel proof")

    after = source_manifest(repo)
    if before != after:
        raise AssertionError("fixed source changed during replay")
    evidence = {
        "schema_version": 1,
        "kind": "selection_repair_replay",
        "fixed_source": {
            "path": str(repo),
            "expected_commit": "53bf29e60cece2335aa39fe301935a07e8e8d4e4",
            "before": before,
            "after": after,
            "unchanged": True,
        },
        "isolated_store": str(store_root),
        "index_summary": index_summary,
        "requests": results,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({
        "output": str(output),
        "source_unchanged": True,
        "requests": {
            label: {
                "output_bytes": result["usage"]["output_bytes"],
                "evidence_bytes": result["usage"]["evidence_bytes"],
                "required_edge_count": result["required_edge_count"],
                "omissions": result["omissions"],
            }
            for label, result in results.items()
        },
    }, indent=2))


if __name__ == "__main__":
    main()
