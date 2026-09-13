"""Verify one deterministic B-arm type-context get over the frozen v3 transport.

The provider endpoint is a loopback fake Responses server supplied by the
frozen verifier.  Codex, the MCP host, and the expansion adapter are real;
there is no provider request.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from benchmarks.typescript_context_baseline_v3 import (
    child_environment,
    execute,
    launch_args,
    save as baseline_save,
    settings as baseline_settings,
)
from benchmarks.typescript_context_corpus import (
    _isolated_store,
    load_corpus,
    materialize_snapshot,
)
from benchmarks.typescript_context_delivery import payload_texts
from benchmarks.typescript_context_observed import reconcile_observed, replay_trace
from benchmarks.typescript_context_transport_v3 import _verify_mode
from loci import service


CANONICAL_TOOL_SCHEMAS_SHA256 = (
    "cbe5ad1aa9f5d7be192d239989d3a3365a0d1435e6ad3178ad1b58f1cde9818d"
)
MODE = {
    "id": "expanded_get",
    "namespace": "mcp__evaluation",
    "tool": "get",
    "arguments": {"symbol_ids": ["consumer.ts::processOrder#function"]},
    "expected": "recorded",
}
TARGET_SOURCE = "interface Payload {\n  requestId: string;\n  amount: number;\n}"


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _settings(run_file: Path, catalog: Path, store: Path) -> dict[str, Any]:
    config = baseline_settings(run_file, catalog, store)
    config["mcp_servers.evaluation.args"] = [
        "-m",
        "benchmarks.typescript_context_expansion_tools",
        str(run_file),
    ]
    return config


def _save_b_arm(path: Path, value: Any) -> None:
    # _verify_mode deliberately creates the run as A.  Mutating this same
    # object before forwarding makes both persisted run records and the empty
    # trace use B, which is the adapter identity under test.
    if isinstance(value, dict) and {
        "repo", "case_id", "arm", "trace_path"
    } <= value.keys():
        value["arm"] = "B"
    baseline_save(path, value)


def _relative(path: Path, parent: Path) -> str:
    return str(path.resolve().relative_to(parent.resolve()))


def verify_transport(corpus: dict[str, Any], catalog: Path, output: Path) -> dict[str, Any]:
    """Run one offline expanded-get proof and write its hashed evidence."""
    output = Path(output).resolve()
    if output.exists():
        raise ValueError(f"transport proof output already exists: {output}")
    catalog = Path(catalog).resolve()
    if not catalog.is_file():
        raise ValueError(f"model catalog does not exist: {catalog}")
    if corpus.get("version") != "typescript-context-v3":
        raise ValueError("typescript-context-v3 corpus required")
    if "imported_interface" not in {case["id"] for case in corpus.get("cases", [])}:
        raise ValueError("imported_interface corpus case required")

    output.parent.mkdir(parents=True, exist_ok=True)
    evidence_root = output.with_name(output.stem + "-evidence")
    evidence_root.mkdir(parents=True, exist_ok=False)
    observation = _verify_mode(
        corpus=corpus,
        catalog=catalog,
        output_root=evidence_root,
        mode=MODE,
        settings=_settings,
        launch_args=launch_args,
        child_environment=child_environment,
        execute=execute,
        save=_save_b_arm,
        materialize_snapshot=materialize_snapshot,
        isolated_store=_isolated_store,
        service=service,
        payload_texts=payload_texts,
        reconcile_observed=reconcile_observed,
    )

    mode_evidence = evidence_root / MODE["id"]
    retained_trace = json.loads((mode_evidence / "trace.json").read_text(encoding="utf-8"))
    retained_run = json.loads((mode_evidence / "run.json").read_text(encoding="utf-8"))
    if retained_run.get("arm") != "B" or retained_trace.get("identity", {}).get("arm") != "B":
        raise ValueError("retained run and trace must both identify arm B")
    replay_trace(corpus, retained_trace)

    accounting = observation["observed_accounting"]
    if (not accounting.get("complete")
            or accounting.get("tool_call_count") != 1
            or observation.get("adapter_attempts") != 1
            or observation.get("adapter_deliveries") != 1):
        raise ValueError(f"expanded_get accounting is incomplete: {accounting}")
    call = observation["call_item"]
    if call.get("status") != "completed":
        raise ValueError("expanded_get MCP call did not complete")
    payload = (call.get("result") or {}).get("structured_content")
    context = payload.get("type_context") if isinstance(payload, dict) else None
    if not isinstance(context, dict):
        raise ValueError("expanded_get payload omitted type_context")
    targets = [item for item in context.get("symbols", []) if item.get("id") == "types.ts::Payload#interface"]
    if len(targets) != 1 or targets[0].get("source") != TARGET_SOURCE:
        raise ValueError("expanded_get payload omitted the full Payload declaration")
    if not context.get("references") or not context.get("evidence"):
        raise ValueError("expanded_get payload omitted reference/evidence context")

    next_request = json.loads((mode_evidence / "next-request.json").read_text(encoding="utf-8"))
    delivered = [item for item in next_request.get("input", [])
                 if item.get("type") == "function_call_output"]
    expected_kind, expected_texts = payload_texts(call)
    if len(delivered) != 1 or delivered[0].get("output") != observation["model_tool_outputs"][0].get("output"):
        raise ValueError("model follow-up request payload differs from observed call payload")
    if expected_kind != observation.get("payload_kind") or expected_texts != observation.get("payload_texts"):
        raise ValueError("payload accounting representation changed")
    if observation.get("canonical_tool_schemas_sha256") != CANONICAL_TOOL_SCHEMAS_SHA256:
        raise ValueError("canonical v3 tool schema hash changed")

    files = []
    for path in sorted(p for p in evidence_root.rglob("*") if p.is_file()):
        files.append({
            "path": _relative(path, output.parent),
            "bytes": path.stat().st_size,
            "sha256": _sha(path.read_bytes()),
        })
    proof = {
        "schema_version": 1,
        "probe": "typescript-context-expanded-get-transport",
        "meaning": "Deterministic offline Codex/MCP B-arm verification; no provider model call.",
        "case_id": "imported_interface",
        "arm": "B",
        "model": "gpt-5.6-luna",
        "reasoning_effort": "high",
        "canonical_tool_schemas_sha256": CANONICAL_TOOL_SCHEMAS_SHA256,
        "observation": observation,
        "evidence_root": _relative(evidence_root, output.parent),
        "artifacts": files,
    }
    baseline_save(output, proof)
    return proof


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus-root", type=Path, required=True)
    parser.add_argument("--catalog", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    proof = verify_transport(load_corpus(args.corpus_root), args.catalog, args.output)
    print(json.dumps({
        "output": str(args.output),
        "evidence_root": proof["evidence_root"],
        "arm": proof["arm"],
        "canonical_tool_schemas_sha256": proof["canonical_tool_schemas_sha256"],
    }))


if __name__ == "__main__":
    main()
