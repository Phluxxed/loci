"""Offline endpoint and exact-delivery proofs using the selected arm's engine."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from benchmarks.typescript_context_three_arm import CORPUS_ROOT, ROOT, save, sha


def assert_engine(engine_src: Path, arm: str) -> dict:
    import loci
    from loci import service
    from loci.storage.index_store import EXTRACTOR_VERSION

    expected = engine_src.resolve() / "loci"
    if Path(loci.__file__).resolve().parent != expected or Path(service.__file__).resolve().parent != expected:
        raise ValueError("preflight did not import the assigned source engine")
    if EXTRACTOR_VERSION != (24 if arm in {"A", "B"} else 25):
        raise ValueError("preflight extractor version differs from arm")
    return {"engine_src": str(engine_src.resolve()), "service_file": str(Path(service.__file__).resolve()),
            "extractor_version": EXTRACTOR_VERSION}


def verify_transport(arm: str, engine_src: Path, catalog: Path, output: Path) -> dict:
    from benchmarks.typescript_context_baseline_v3 import child_environment, execute, launch_args, settings
    from benchmarks.typescript_context_corpus import _isolated_store, load_corpus, materialize_snapshot
    from benchmarks.typescript_context_delivery import payload_texts
    from benchmarks.typescript_context_expansion_transport import CANONICAL_TOOL_SCHEMAS_SHA256, MODE, TARGET_SOURCE
    from benchmarks.typescript_context_observed import reconcile_observed, replay_trace
    from benchmarks.typescript_context_transport_v3 import _MODES, _verify_mode
    from loci import service

    engine = assert_engine(engine_src, arm)
    corpus = load_corpus(CORPUS_ROOT)
    if output.exists():
        raise ValueError("transport proof already exists")
    evidence = output.with_name(output.stem + "-evidence")
    evidence.mkdir(parents=True, exist_ok=False)

    def selected_settings(run_file: Path, catalog: Path, store: Path) -> dict:
        config = settings(run_file, catalog, store)
        config["mcp_servers.evaluation.args"] = ["-m", "benchmarks.typescript_context_three_arm_tools", str(run_file)]
        config["mcp_servers.evaluation.env"]["PYTHONPATH"] = os.pathsep.join((str(engine_src), str(ROOT)))
        config["mcp_servers.evaluation.env"]["PYTHONDONTWRITEBYTECODE"] = "1"
        return config

    def selected_save(path: Path, value: dict) -> None:
        if isinstance(value, dict) and {"repo", "case_id", "arm", "trace_path"} <= value.keys():
            value["arm"] = arm
        save(path, value)

    observations = []
    for mode in _MODES if arm == "A" else [MODE]:
        observation = _verify_mode(
            corpus=corpus, catalog=catalog, output_root=evidence, mode=mode,
            settings=selected_settings, launch_args=launch_args, child_environment=child_environment,
            execute=execute, save=selected_save, materialize_snapshot=materialize_snapshot,
            isolated_store=_isolated_store, service=service, payload_texts=payload_texts,
            reconcile_observed=reconcile_observed,
        )
        if observation["canonical_tool_schemas_sha256"] != CANONICAL_TOOL_SCHEMAS_SHA256:
            raise ValueError("model-visible schemas differ from frozen v3")
        trace = json.loads((evidence / mode["id"] / "trace.json").read_text())
        if trace["identity"]["arm"] != arm:
            raise ValueError("transport trace has the wrong arm")
        replay_trace(corpus, trace)
        if arm in {"B", "C"}:
            context = observation["call_item"].get("result", {}).get("structured_content", {}).get("type_context", {})
            target = [item for item in context.get("symbols", []) if item["id"] == "types.ts::Payload#interface"]
            if len(target) != 1 or target[0]["source"] != TARGET_SOURCE:
                raise ValueError("expanded get did not deliver the complete imported type")
            expected_kind = "references_type" if arm == "B" else "uses_type"
            if not any(item["edge"]["type"] == expected_kind for item in context.get("references", [])):
                raise ValueError("expanded get did not use the selected arm's relationship semantics")
            if not context.get("evidence"):
                raise ValueError("expanded get omitted its proof source")
        observations.append(observation)
    proof = {"schema_version": 3, "probe": "three-arm-exact-transport", "arm": arm,
             "meaning": "Offline Codex/MCP requests and exact next-request delivery; no provider model calls.",
             "engine": engine, "catalog_sha256": sha(catalog.read_bytes()),
             "canonical_tool_schemas_sha256": CANONICAL_TOOL_SCHEMAS_SHA256,
             "modes": observations,
             "artifacts": {str(path.relative_to(output.parent)): sha(path.read_bytes())
                           for path in evidence.rglob("*") if path.is_file()}}
    save(output, proof)
    return proof


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=["endpoints", "transport"], required=True)
    parser.add_argument("--arm", choices=["A", "B", "C"], required=True)
    parser.add_argument("--engine-src", type=Path, required=True)
    parser.add_argument("--catalog", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    engine = assert_engine(args.engine_src, args.arm)
    if args.mode == "endpoints":
        from benchmarks.typescript_context_corpus import load_corpus, preflight

        result = preflight(load_corpus(CORPUS_ROOT))
        save(args.output, {**result, "arm": args.arm, "engine": engine})
        print(json.dumps({"preflight": args.arm, "cases": len(result["cases"])}), flush=True)
    else:
        if args.catalog is None:
            parser.error("--catalog is required for transport")
        result = verify_transport(args.arm, args.engine_src.resolve(), args.catalog.resolve(), args.output.resolve())
        print(json.dumps({"transport": args.arm, "modes": len(result["modes"]),
                          "schema": result["canonical_tool_schemas_sha256"]}), flush=True)


if __name__ == "__main__":
    main()
