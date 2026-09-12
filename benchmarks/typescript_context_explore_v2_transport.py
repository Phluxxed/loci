"""Offline transport proof for the corrected exploration protocol.

The loopback proof reuses the published v1 request runner and tool server.  It
injects only the v2 observed reconciler, so the tool schemas, model settings,
prompt, and raw delivery protocol stay the same while the graph-operation
accounting fix is exercised against real MCP calls.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from benchmarks.typescript_context_delivery import payload_texts
from benchmarks.typescript_context_explore_v2_observed import RAW_PROTOCOL
from benchmarks.typescript_context_explore_transport import (
    HELPERS,
    TOOLS_MODULE,
    _verify_mode,
    audit_request,
    child_environment,
    execute,
    launch_args,
    save,
    settings,
    sha,
    tool_names,
)


PROTOCOL = "typescript-context-explore-v2"

_SYMBOL_ID = "consumer.ts::processOrder#function"

# The first eight modes are the published v1 transport cases.  The final two
# exercise the real inherited graph routes whose public operation names were
# previously collapsed incorrectly by observed reconciliation.
MODES: tuple[dict[str, Any], ...] = (
    {
        "id": "A_exact_get",
        "arm": "A",
        "tool": "get",
        "arguments": {"symbol_ids": [_SYMBOL_ID]},
        "expected": "recorded",
    },
    {
        "id": "B_exact_get",
        "arm": "B",
        "tool": "get",
        "arguments": {"symbol_ids": [_SYMBOL_ID]},
        "expected": "recorded",
    },
    {
        "id": "B_explore_types",
        "arm": "B",
        "tool": "loci_explore",
        "arguments": {"intent": "type_dependencies", "seed_ids": [_SYMBOL_ID]},
        "expected": "recorded",
    },
    {
        "id": "B_explore_query",
        "arm": "B",
        "tool": "loci_explore",
        "arguments": {"intent": "locate", "query": "processOrder"},
        "expected": "recorded",
    },
    {
        "id": "B_explore_empty",
        "arm": "B",
        "tool": "loci_explore",
        "arguments": {
            "intent": "type_dependencies",
            "seed_ids": [_SYMBOL_ID],
            "max_evidence_bytes": 0,
        },
        "expected": "recorded",
    },
    {
        "id": "B_explore_unknown",
        "arm": "B",
        "tool": "loci_explore",
        "arguments": {"intent": "locate", "repo": "/wrong"},
        "expected": "schema_error",
    },
    {
        "id": "B_explore_bool_hops",
        "arm": "B",
        "tool": "loci_explore",
        "arguments": {"intent": "locate", "query": "processOrder", "max_hops": True},
        "expected": "schema_error",
    },
    {
        "id": "B_resources",
        "arm": "B",
        "namespace": "functions",
        "tool": "list_mcp_resources",
        "arguments": {"server": "evaluation"},
        "expected": "helper",
    },
    {
        "id": "A_graph_anchors",
        "arm": "A",
        "tool": "graph_anchors",
        "arguments": {"question": "processOrder"},
        "expected": "recorded",
    },
    {
        "id": "B_graph_neighbors",
        "arm": "B",
        "tool": "graph_neighbors",
        "arguments": {"seed_ids": [_SYMBOL_ID]},
        "expected": "recorded",
    },
)


def _modes() -> list[dict[str, Any]]:
    """Return fresh mode dictionaries so verification never mutates ``MODES``."""

    return [{**mode, "arguments": dict(mode["arguments"])} for mode in MODES]


def verify_transport(
    corpus: dict[str, Any],
    catalog: Path,
    output: Path,
) -> dict[str, Any]:
    """Run ten deterministic loopback proofs and save v2 transport evidence."""

    output = Path(output).resolve()
    catalog = Path(catalog).resolve()
    if output.exists():
        raise ValueError(f"transport evidence cannot be overwritten: {output}")
    if not catalog.is_file():
        raise ValueError(f"model catalog does not exist: {catalog}")
    if corpus.get("version") != "typescript-context-v3":
        raise ValueError("typescript-context-v3 corpus required")
    case_ids = {case["id"] for case in corpus.get("cases", [])}
    if "imported_interface" not in case_ids:
        raise ValueError("v2 transport verifier requires imported_interface")

    from benchmarks.typescript_context_corpus import _isolated_store, load_controls, materialize_snapshot
    from benchmarks.typescript_context_explore_v2_observed import reconcile_observed
    from loci import service

    controls = load_controls(corpus)
    output.parent.mkdir(parents=True, exist_ok=True)
    evidence_root = output.with_name(output.stem + "-evidence")
    evidence_root.mkdir(parents=True, exist_ok=False)
    observations: list[dict[str, Any]] = []
    for original_mode in _modes():
        mode = {"namespace": "mcp__evaluation", **original_mode}
        # ``B_resources`` uses the functions namespace, matching the v1 proof.
        if original_mode.get("namespace") == "functions":
            mode["namespace"] = "functions"
        observations.append(
            _verify_mode(
                corpus=corpus,
                catalog=catalog,
                output_root=evidence_root,
                mode=mode,
                settings=settings,
                launch_args=launch_args,
                child_environment=child_environment,
                execute=execute,
                save=save,
                materialize_snapshot=materialize_snapshot,
                isolated_store=_isolated_store,
                service=service,
                payload_texts=payload_texts,
                reconcile_observed=reconcile_observed,
            )
        )

    hashes: dict[str, str] = {}
    for arm in ("A", "B"):
        values = {
            observation["canonical_tool_schemas_sha256"]
            for observation in observations
            if observation["arm"] == arm
        }
        if len(values) != 1:
            raise ValueError(f"tool schemas changed within arm {arm}")
        hashes[arm] = values.pop()
    if hashes["A"] == hashes["B"]:
        raise ValueError("candidate workflow was not exposed separately")

    # Compare the original thirteen schemas directly from the two exact-get
    # requests.  The candidate's added schema is intentionally excluded here.
    requests = [
        json.loads((evidence_root / name / "effective-request.json").read_text(encoding="utf-8"))
        for name in ("A_exact_get", "B_exact_get")
    ]
    schemas = []
    for request in requests:
        schemas.append(
            {
                (namespace["name"], tool["name"]): tool
                for item in request["input"]
                if item["type"] == "additional_tools"
                for namespace in item["tools"]
                for tool in namespace["tools"]
                if tool["name"] != "loci_explore"
            }
        )
    if schemas[0] != schemas[1]:
        raise ValueError("common tool schemas differ between arms")

    result = {
        "schema_version": 1,
        "comparison": PROTOCOL,
        "protocol": PROTOCOL,
        "raw_delivery_protocol": RAW_PROTOCOL,
        "meaning": "Real Codex and MCP with deterministic loopback responses; zero provider calls.",
        "canonical_tool_schemas_sha256": hashes,
        "common_tool_schemas_identical": True,
        "tool_counts": {"A": len(tool_names("A")) + len(HELPERS), "B": len(tool_names("B")) + len(HELPERS)},
        "modes": observations,
        "catalog_sha256": sha(catalog.read_bytes()),
        "controls_version": controls.get("version"),
    }
    save(output, result)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus-root", type=Path, required=True)
    parser.add_argument("--catalog", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    from benchmarks.typescript_context_corpus import load_corpus

    result = verify_transport(load_corpus(args.corpus_root), args.catalog, args.output)
    print(
        json.dumps(
            {
                "output": str(args.output),
                "verified_modes": len(result["modes"]),
                "canonical_tool_schemas_sha256": result["canonical_tool_schemas_sha256"],
            }
        )
    )


__all__ = [
    "HELPERS",
    "MODES",
    "PROTOCOL",
    "RAW_PROTOCOL",
    "TOOLS_MODULE",
    "audit_request",
    "main",
    "settings",
    "tool_names",
    "verify_transport",
]


if __name__ == "__main__":
    main()
