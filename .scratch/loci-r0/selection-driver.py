#!/usr/bin/env python3
"""One fixed fixture set for the R0 anchor-priority ablation."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path


FILES = {
    "collision/a_connection.py": "def connection():\n    return 'unrelated transport helper'\n",
    "collision/b_handler.py": (
        "def execute():\n"
        "    message = 'connection reset §42§'\n"
        "    return message\n"
    ),
    "semantic/schema.ts": "export interface WireEnvelope { value: string }\n",
    "semantic/assemble.ts": (
        "import { type WireEnvelope } from './schema';\n"
        "export function encodeEnvelope(value: WireEnvelope) { return value.value; }\n"
        "export function assembleEnvelope(value: WireEnvelope) { return encodeEnvelope(value); }\n"
    ),
    "semantic/entry.ts": (
        "import { assembleEnvelope } from './assemble';\n"
        "export function start() { return assembleEnvelope({ value: 'x' }); }\n"
    ),
    "semantic/guide.md": "# Guide\n\nA literal-only telescope §§§.\n",
}

REQUESTS = (
    ("mixed_collision", "connection reset §42§", None, "collision/b_handler.py::execute#function"),
    ("literal_only", "§42§", None, "collision/b_handler.py::execute#function"),
    ("ordinary_symbol", "assembleEnvelope", None, "semantic/assemble.ts::assembleEnvelope#function"),
    ("ordinary_type", "WireEnvelope", None, "semantic/schema.ts::WireEnvelope#interface"),
    ("ordinary_words", "assemble envelope", None, "semantic/assemble.ts::assembleEnvelope#function"),
    ("exact_file", "semantic/assemble.ts", None, "semantic/assemble.ts::__file__#file"),
    ("explicit_seed", "connection reset §42§", ["collision/b_handler.py::execute#function"],
     "collision/b_handler.py::execute#function"),
)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--worktree", type=Path, required=True)
    parser.add_argument("--variant", choices=("control", "literal_first"), required=True)
    parser.add_argument("--run-id", default="first")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    worktree = args.worktree.resolve()
    if worktree.name != "r0-selection" or not (worktree / ".git").exists():
        raise SystemExit("expected isolated r0-selection worktree")
    fixture = worktree / ".scratch" / "r0-selection-fixture"
    store_root = worktree / ".scratch" / f"r0-selection-store-{args.variant}-{args.run_id}"
    if store_root.exists():
        raise SystemExit(f"store already exists: {store_root}")
    for relative, content in FILES.items():
        path = fixture / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists() and path.read_text() != content:
            raise SystemExit(f"fixture changed: {path}")
        path.write_text(content)
    os.environ["LOCI_BASE_DIR"] = str(store_root)
    os.environ["LOCI_STORE_NAMESPACE"] = f"r0-selection-{args.variant}"
    sys.path.insert(0, str(worktree / "src"))

    from loci import service
    from loci.retrieval import retrieve_context

    index_summary = service.index_repo(fixture, incremental=False)
    store = service.get_store()
    index = store.load(fixture)
    if index is None:
        raise RuntimeError("fixture index missing")
    nodes = {node["id"]: node for node in index["symbols"]}
    state = store.validate_graph_state(index)
    rows = []
    for label, query, seeds, target in REQUESTS:
        wall = time.perf_counter_ns()
        cpu = time.process_time_ns()
        result = retrieve_context(fixture, store, nodes, state, query,
                                  seed_ids=seeds, coverage="complete")
        row = {
            "label": label,
            "query": query,
            "seed_ids": seeds,
            "target": target,
            "target_anchor": target in [item["node_id"] for item in result["anchors"]],
            "target_item": target in [item["node_id"] for item in result["items"]],
            "wall_ns": time.perf_counter_ns() - wall,
            "cpu_ns": time.process_time_ns() - cpu,
            "result": result,
        }
        rows.append(row)
    artifact = {
        "variant": args.variant,
        "commit": subprocess.check_output(["git", "-C", str(worktree), "rev-parse", "HEAD"], text=True).strip(),
        "retrieval_py_sha256": sha256(worktree / "src" / "loci" / "retrieval.py"),
        "python": sys.version,
        "worktree": str(worktree),
        "fixture": str(fixture),
        "fixture_sha256": {relative: sha256(fixture / relative) for relative in FILES},
        "store_root": str(store_root),
        "index_summary": index_summary,
        "node_count": len(nodes),
        "rows": rows,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(artifact, ensure_ascii=False, indent=2, default=str) + "\n")
    for row in rows:
        result = row["result"]
        print(json.dumps({
            "label": row["label"],
            "target_anchor": row["target_anchor"],
            "target_item": row["target_item"],
            "matching": result["scope"]["matching"],
            "anchors": [item["node_id"] for item in result["anchors"]],
            "omissions": result["omissions"],
            "wall_ms": round(row["wall_ns"] / 1e6, 3),
            "cpu_ms": round(row["cpu_ns"] / 1e6, 3),
            "usage": result["usage"],
        }, ensure_ascii=False))


if __name__ == "__main__":
    main()
