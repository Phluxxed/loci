"""Verify routing prompt and native tool transport with scripted loopback responses."""
from __future__ import annotations

import argparse
import http.server
import json
from pathlib import Path
import tempfile
import threading
import uuid
from typing import Any

from benchmarks.typescript_context_baseline_v3 import child_environment, execute, launch_args, sha
from benchmarks.typescript_context_corpus import _isolated_store, load_controls, load_corpus, materialize_snapshot
from benchmarks.typescript_context_delivery import payload_texts
from benchmarks.typescript_context_explore_transport import settings
from benchmarks.typescript_context_explore_v2 import engine_identity, verify_engine
from benchmarks.typescript_context_explore_v2_observed import reconcile_observed
from benchmarks.typescript_context_routing import ROOT, VERSION, audit_request, build_prompt, prompt_manifest
from benchmarks.typescript_context_transport_probe import _model_payload, _sse_response
from benchmarks.typescript_context_transport_v3 import _empty_trace, _jsonl, _save, _terminal_calls
from loci import service


def _verify_mode(corpus: dict[str, Any], catalog: Path, evidence: Path, arm: str) -> dict[str, Any]:
    destination = evidence / arm
    destination.mkdir(exist_ok=False)
    prompt = build_prompt(corpus, load_controls(corpus), "imported_interface", arm)
    arguments = {"intent": "type_dependencies", "query": "processOrder"}
    with tempfile.TemporaryDirectory(prefix="loci-routing-transport-") as temporary:
        temp = Path(temporary)
        repo, store = temp / "snapshot", temp / "store"
        materialize_snapshot(corpus, "imported_interface", repo)
        with _isolated_store(store):
            service.index_repo(repo, incremental=False)
        run = {
            "repo": str(repo.resolve()), "corpus_root": corpus["_root"],
            "case_id": "imported_interface", "session_id": str(uuid.uuid4()),
            "arm": "B", "repetition": 1, "trace_path": str(temp / "trace.json"),
        }
        _save(temp / "run.json", run)
        initial = _empty_trace(corpus, run)
        _save(Path(run["trace_path"]), initial)
        _save(destination / "initial-trace.json", initial)
        _save(destination / "run.json", run)
        (destination / "prompt.txt").write_text(prompt, encoding="utf-8")
        captured: list[dict[str, Any]] = []

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_POST(self):
                captured.append(json.loads(self.rfile.read(int(self.headers.get("content-length", "0")))))
                if len(captured) == 1:
                    self.send_response(200)
                    self.send_header("Content-Type", "text/event-stream")
                    self.send_header("Cache-Control", "no-cache")
                    self.end_headers()
                    self.wfile.write(_sse_response("mcp__evaluation", "loci_explore", arguments))
                    self.wfile.flush()
                else:
                    self.send_response(400)
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    self.wfile.write(b'{"error":{"message":"offline transport probe complete",'
                                     b'"type":"invalid_request_error"}}')

            def log_message(self, format: str, *args):
                pass

        server = http.server.HTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        config = settings(temp / "run.json", catalog, store)
        config.update({
            "model_provider": "inspection",
            "model_providers.inspection.name": "Offline routing transport probe",
            "model_providers.inspection.base_url": f"http://127.0.0.1:{server.server_port}/v1",
            "model_providers.inspection.wire_api": "responses",
            "model_providers.inspection.requires_openai_auth": False,
        })
        try:
            code, stdout, stderr, elapsed, timed_out = execute(
                launch_args(repo, config, prompt), child_environment(temp / "runtime", False), 25,
            )
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)

        events = _jsonl(stdout)
        trace = json.loads(Path(run["trace_path"]).read_text())
        _save(destination / "events.json", events)
        _save(destination / "trace.json", trace)
        _save(destination / "effective-request.json", captured[0] if captured else {})
        _save(destination / "next-request.json", captured[1] if len(captured) > 1 else {})
        (destination / "stdout.jsonl").write_text(stdout)
        (destination / "stderr.txt").write_text(stderr)
        if len(captured) != 2 or timed_out or code not in {0, 1}:
            raise ValueError(f"{arm}: incomplete offline round trip: {len(captured)=}, {code=}, {timed_out=}: {stderr[-1500:]}")
        audit = audit_request(captured[0], prompt)
        _save(destination / "request-audit.json", audit)
        calls = _terminal_calls(events)
        if len(calls) != 1:
            raise ValueError(f"{arm}: expected one host-observed call")
        call = calls[0]
        if (call.get("server"), call.get("tool"), call.get("arguments")) != ("evaluation", "loci_explore", arguments):
            raise ValueError(f"{arm}: host call differs from scripted request")
        outputs = [item for item in captured[1]["input"] if item.get("type") == "function_call_output"]
        kind, expected_payload = payload_texts(call)
        if len(outputs) != 1 or _model_payload(outputs[0].get("output"), kind) != expected_payload:
            raise ValueError(f"{arm}: native result changed before the next request")
        accounting = reconcile_observed(trace, events)
        _save(destination / "accounting.json", accounting)
        if not accounting.get("complete") or accounting.get("tool_call_count") != 1:
            raise ValueError(f"{arm}: incomplete source/call accounting")
        native = call["result"]["structured_content"]
        sources = native.get("sources", [])
        anchors = [item for item in native.get("items", []) if item.get("role") == "anchor"]
        if native.get("status") != "ok" or not sources or not any(
            item.get("id") == "consumer.ts::processOrder#function" and item.get("complete") for item in anchors
        ):
            raise ValueError(f"{arm}: source-bearing requested anchor was not delivered")
        for source in sources:
            path = (repo / source["file"]).resolve()
            if not path.is_relative_to(repo.resolve()):
                raise ValueError(f"{arm}: source path left snapshot")
            content = path.read_bytes()
            if (sha(content) != source["content_hash"] or
                    content[source["start_byte"]:source["end_byte"]] != source["content"].encode("utf-8")):
                raise ValueError(f"{arm}: delivered source differs from frozen snapshot")
        return {
            "routing_arm": arm, "adapter_arm": "B", "case_id": "imported_interface",
            "request_count": 2, "exit_code": code, "timed_out": timed_out,
            "elapsed_seconds": elapsed, "prompt_sha256": audit["prompt_sha256"],
            "canonical_tool_schemas_sha256": audit["canonical_tool_schemas_sha256"],
            "prompt_verified": True, "native_output_verified": True,
            "snapshot_source_verified": True, "source_count": len(sources),
            "anchor_ids": [item["id"] for item in anchors],
            "observed_accounting": accounting, "evidence_dir": str(destination.relative_to(evidence.parent)),
            "call_selection": "scripted_loopback", "model_adoption_measured": False,
        }


def verify_transport(corpus: dict[str, Any], catalog: Path, output: Path) -> dict[str, Any]:
    identity = engine_identity()
    verify_engine(identity)
    output = output.resolve()
    evidence = output.with_name(output.stem + "-evidence")
    if output.exists() or evidence.exists():
        raise ValueError("routing transport evidence cannot be overwritten")
    evidence.mkdir(parents=True)
    observations = [_verify_mode(corpus, catalog.resolve(), evidence, arm) for arm in ("A", "B")]
    hashes = {item["routing_arm"]: item["canonical_tool_schemas_sha256"] for item in observations}
    old = json.loads((ROOT / "benchmarks/comparisons/typescript-context-explore-v2/transport-verification.json").read_text())
    if set(hashes.values()) != {old["canonical_tool_schemas_sha256"]["B"]}:
        raise ValueError("routing conditions must both preserve the availability trial's B schema")
    declaration = prompt_manifest(corpus, load_controls(corpus))
    expected = next(case for case in declaration["cases"] if case["case_id"] == "imported_interface")
    if any(item["prompt_sha256"] != expected["prompts"][item["routing_arm"]]["sha256"] for item in observations):
        raise ValueError("observed prompts differ from the policy declaration")
    result = {
        "schema_version": 1, "version": VERSION, "engine": identity,
        "meaning": "Real Codex/MCP with scripted loopback calls. No provider calls or model-adoption measurement.",
        "provider_calls": 0, "model_adoption_measured": False,
        "canonical_tool_schemas_sha256": hashes, "identical_tool_schemas": True,
        "tool_counts": {"A": 17, "B": 17}, "modes": observations,
        "policy_sha256": declaration["policy_sha256"],
        "candidate_prefix_utf8_bytes": declaration["candidate_prefix_utf8_bytes"],
        "catalog_sha256": sha(catalog.read_bytes()),
    }
    _save(output, result)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--catalog", type=Path, required=True)
    args = parser.parse_args()
    corpus = load_corpus(ROOT / "benchmarks/corpora/typescript-context-v3")
    result = verify_transport(corpus, args.catalog, args.output)
    print(json.dumps({"output": str(args.output), "modes": len(result["modes"]),
                      "identical_tool_schemas": result["identical_tool_schemas"],
                      "provider_calls": result["provider_calls"]}))


if __name__ == "__main__":
    main()
