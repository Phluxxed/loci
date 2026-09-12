"""Offline Codex/MCP acceptance for repaired byte limits and failed observations.

This is a scripted transport proof, not a provider comparison or adoption result.
The old transport runner is reused through its explicit dependency parameters.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from benchmarks.typescript_context_adapter import wire
from benchmarks.typescript_context_baseline_v3 import (
    child_environment, execute, launch_args, save, sha,
)
from benchmarks.typescript_context_corpus import (
    _isolated_store, load_corpus, materialize_snapshot,
)
from benchmarks.typescript_context_delivery import payload_texts
from benchmarks.typescript_context_explore_transport import (
    _verify_mode, settings as original_settings,
)
from benchmarks.typescript_context_routing_v2_observed import (
    observe_routing, reconcile_observed, replay_trace,
)
from benchmarks.typescript_context_routing_v2_tools import VERSION, normalize_arguments
from loci import service
from loci.mcp_output_models import LociExploreSuccess


ROOT = Path(__file__).resolve().parents[1]
TOOLS_MODULE = "benchmarks.typescript_context_routing_v2_tools"


def settings(run_file: Path, catalog: Path, store: Path) -> dict:
    config = original_settings(run_file, catalog, store)
    config["mcp_servers.evaluation.args"] = ["-m", TOOLS_MODULE, str(run_file)]
    return config


def modes() -> list[dict]:
    cases = [
        ("omitted", {}, "recorded"),
        ("null", {"max_output_bytes": None, "max_evidence_bytes": None}, "recorded"),
        ("explicit", {"max_output_bytes": 8_192, "max_evidence_bytes": 512}, "recorded"),
        ("zero_evidence", {"max_output_bytes": None, "max_evidence_bytes": 0}, "recorded"),
        ("minimum_output", {"max_output_bytes": 2_048, "max_evidence_bytes": None}, "recorded"),
        ("maximum", {"max_output_bytes": 32_768, "max_evidence_bytes": 16_384}, "recorded"),
        ("output_over_cap", {"max_output_bytes": 32_769}, "schema_error"),
        ("evidence_over_cap", {"max_evidence_bytes": 16_385}, "schema_error"),
        ("output_below_minimum", {"max_output_bytes": 2_047}, "schema_error"),
        ("negative_evidence", {"max_evidence_bytes": -1}, "schema_error"),
        ("coercible_string", {"max_output_bytes": "8192"}, "schema_error"),
    ]
    return [{
        "id": name, "arm": "B", "namespace": "mcp__evaluation",
        "tool": "loci_explore", "arguments": {
            "intent": "type_dependencies", "query": "processOrder", **limits,
        }, "expected": expected,
    } for name, limits, expected in cases]


def verify_transport(corpus: dict, catalog: Path, output: Path) -> dict:
    output = output.resolve()
    evidence = output.with_name(output.stem + "-evidence")
    if output.exists() or evidence.exists():
        raise ValueError("repair transport evidence cannot be overwritten")
    evidence.mkdir(parents=True)
    # Declare the matrix and source identity before any host run. This is not
    # a trial freeze; provider qualification gets a separate declaration.
    declaration = {
        "version": VERSION, "purpose": "byte-limit repair acceptance",
        "provider_calls": 0, "model_adoption_measured": False, "modes": modes(),
        "source_sha256": {
            str(path.relative_to(ROOT)): sha(path.read_bytes()) for path in (
                Path(__file__), ROOT / "benchmarks/typescript_context_routing_v2_tools.py",
                ROOT / "benchmarks/typescript_context_routing_v2_observed.py",
                ROOT / "src/loci/mcp_server.py",
            )
        },
        "catalog_sha256": sha(catalog.read_bytes()),
    }
    save(evidence / "declaration.json", declaration)
    case = next(item for item in corpus["cases"] if item["id"] == "imported_interface")
    observations = []
    for mode in declaration["modes"]:
        observed = _verify_mode(
            corpus=corpus, catalog=catalog.resolve(), output_root=evidence,
            mode=mode, settings=settings, launch_args=launch_args,
            child_environment=child_environment, execute=execute, save=save,
            materialize_snapshot=materialize_snapshot, isolated_store=_isolated_store,
            service=service, payload_texts=payload_texts, reconcile_observed=reconcile_observed,
        )
        folder = evidence / mode["id"]
        raw = json.loads((folder / "trace.json").read_text())
        events = json.loads((folder / "events.json").read_text())
        routing = observe_routing(corpus, {**case, "group": "maintained_task"}, raw, events)
        save(folder / "routing.json", routing)
        if not routing["observations_complete"] or routing["initial_type_route"] is not True:
            raise ValueError(f"{mode['id']}: initial call was not fully observed")
        if mode["expected"] == "schema_error":
            if (observed["call_item"]["status"] != "failed"
                    or routing["maintained_exposure"] is not False
                    or observed["observed_accounting"]["source_bytes"] != 0):
                raise ValueError(f"{mode['id']}: native failure was not a costed, source-free failure")
        else:
            effective = normalize_arguments("loci_explore", mode["arguments"])
            if raw["deliveries"][0]["arguments"] != effective:
                raise ValueError(f"{mode['id']}: default limits changed before the adapter")
            native = observed["call_item"]["result"]["structured_content"]
            body = {key: value for key, value in native.items() if key != "_evaluation"}
            LociExploreSuccess.model_validate(body)
            envelope_bytes = len(wire({"content": [], "structuredContent": body, "isError": False}).encode())
            if envelope_bytes > effective["max_output_bytes"]:
                raise ValueError(f"{mode['id']}: product output exceeded its byte limit")
            if observed["observed_accounting"]["source_bytes"] > effective["max_evidence_bytes"]:
                raise ValueError(f"{mode['id']}: source exceeded its byte limit")
            files = replay_trace(corpus, raw).files
            for source in body["sources"]:
                content = files[source["file"]]
                if (sha(content) != source["content_hash"] or
                        content[source["start_byte"]:source["end_byte"]] != source["content"].encode()):
                    raise ValueError(f"{mode['id']}: source differs from the snapshot")
            if mode["id"] in {"omitted", "null", "maximum"} and routing["maintained_exposure"] is not True:
                raise ValueError(f"{mode['id']}: default/maximum call did not deliver the requested source")
            observed.update(effective_arguments=effective, product_envelope_bytes=envelope_bytes,
                            snapshot_source_verified=True)
        observed["routing"] = routing
        observations.append(observed)
        print(json.dumps({"mode": mode["id"], "verified": True}), flush=True)
    hashes = {item["canonical_tool_schemas_sha256"] for item in observations}
    if len(hashes) != 1:
        raise ValueError("repair tool schema changed between modes")
    result = {
        **declaration, "modes": observations,
        "meaning": "Real Codex/MCP; scripted loopback Responses endpoint; no provider outcomes.",
        "canonical_tool_schemas_sha256": next(iter(hashes)),
        "product_budget_scope": "Native product MCP envelope; evaluator metadata is separately costed.",
    }
    save(output, result)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = verify_transport(load_corpus(ROOT / "benchmarks/corpora/typescript-context-v3"),
                              args.catalog, args.output)
    print(json.dumps({"verified_modes": len(result["modes"]), "provider_calls": 0}))


if __name__ == "__main__":
    main()
