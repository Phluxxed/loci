"""Offline Responses/MCP acceptance for the multilingual workflow harness.

The local server returns scripted function calls.  Codex still builds its real
request, starts the real stdio MCP server, and forwards its actual tool output
into the second request, but no request is sent to a provider.
"""
from __future__ import annotations

import http.server
import json
from pathlib import Path
import tempfile
import threading
from typing import Any
from unittest.mock import patch

from benchmarks import multilingual_context_compare as runner
from benchmarks.multilingual_context_inputs import load_controls, load_inputs
from benchmarks.typescript_context_baseline import child_environment, command, execute, launch_args, save, sha
from benchmarks.typescript_context_corpus import _isolated_store, materialize_snapshot
from benchmarks.typescript_context_delivery import payload_texts
from benchmarks.typescript_context_transport_probe import _model_payload, _sse_response
from loci import service


def _first_case(corpus: dict[str, Any]) -> dict[str, Any]:
    if not corpus.get("cases"):
        raise ValueError("transport requires a nonempty frozen corpus")
    return corpus["cases"][0]


def _symbol_id(case: dict[str, Any]) -> str:
    anchor = next(item for item in case["context"] if item["id"] == case["anchor"])
    symbol = anchor.get("symbol") or {}
    if not all(isinstance(symbol.get(key), str) and symbol[key] for key in ("name", "kind")):
        raise ValueError("transport anchor must have a concrete declaration")
    return f"{anchor['file']}::{symbol['name']}#{symbol['kind']}"


def _offline_config(port: int) -> dict[str, Any]:
    return {
        "model_provider": "inspection",
        "model_providers.inspection.name": "Offline multilingual transport probe",
        "model_providers.inspection.base_url": f"http://127.0.0.1:{port}/v1",
        "model_providers.inspection.wire_api": "responses",
        "model_providers.inspection.requires_openai_auth": False,
        "model_providers.inspection.request_max_retries": 0,
        "model_providers.inspection.stream_max_retries": 0,
    }


def _schema_hashes(corpus: dict[str, Any], controls: dict[str, Any], catalog: Path) -> dict[str, str]:
    """Capture each arm's actual no-auth request before scripted tool delivery."""

    case = _first_case(corpus)
    hashes: dict[str, str] = {}
    with tempfile.TemporaryDirectory(prefix="loci-multilingual-transport-schema-") as directory:
        temp = Path(directory)
        repo, store = temp / "snapshot", temp / "store"
        materialize_snapshot(corpus, case["snapshot"], repo)
        with _isolated_store(store):
            service.index_repo(repo, incremental=False)
            for arm in ("A", "B"):
                run = {
                    "repo": str(repo.resolve()), "corpus_root": corpus["_root"],
                    "case_id": case["id"], "session_id": f"transport-schema-{arm}",
                    "arm": arm, "repetition": 1, "trace_path": str(temp / f"{arm}-trace.json"),
                    "attempt_id": f"transport-schema-{arm}",
                }
                run_file = temp / f"{arm}-run.json"
                save(run_file, run)
                audit = runner.inspect_request(
                    repo, runner.settings(run_file, catalog, store),
                    runner.build_prompt(corpus, controls, case["id"], arm), temp / f"{arm}-runtime", arm=arm,
                )
                hashes[arm] = audit["canonical_tool_schemas_sha256"]
    if not all(isinstance(value, str) and value for value in hashes.values()):
        raise ValueError("offline request inspection did not produce canonical schemas")
    return hashes


def _run_mode(corpus: dict[str, Any], controls: dict[str, Any], catalog: Path, evidence: Path,
              mode: dict[str, Any], freeze: dict[str, Any]) -> dict[str, Any]:
    case = _first_case(corpus)
    plan = {
        "attempt_id": mode["id"], "case_id": case["id"], "snapshot": case["snapshot"],
        "repetition": 1, "arm": mode["arm"],
    }
    captured: list[dict[str, Any]] = []

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_POST(self) -> None:  # noqa: N802
            captured.append(json.loads(self.rfile.read(int(self.headers.get("content-length", "0")))))
            if len(captured) == 1:
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.end_headers()
                self.wfile.write(_sse_response("mcp__evaluation", mode["tool"], mode["arguments"]))
            else:
                self.send_response(400)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(b'{"error":{"message":"offline multilingual transport complete","type":"invalid_request_error"}}')
            self.wfile.flush()

        def log_message(self, *_args: object) -> None:
            pass

    server = http.server.HTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    def local_execute(args: list[str], env: dict[str, str], timeout: float):
        overrides = [
            part for key, value in _offline_config(server.server_port).items()
            for part in ("-c", key + "=" + json.dumps(value))
        ]
        return execute(args[:-1] + overrides + args[-1:], env, min(timeout, 25))

    try:
        with patch.object(runner, "execute", local_execute):
            result = runner.run_attempt(corpus, controls, plan, evidence, catalog, freeze)
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
    destination = evidence / mode["id"]
    save(destination / "captured-requests.json", captured)
    if len(captured) != 2:
        raise ValueError(f"{mode['id']}: expected request plus tool-output follow-up, got {len(captured)}")
    if result.get("runner_failures"):
        raise ValueError(f"{mode['id']}: runner failed: {result['runner_failures']}")
    prompt = runner.build_prompt(corpus, controls, case["id"], mode["arm"])
    audit = runner.audit_request(captured[0], prompt, mode["arm"])
    save(destination / "actual-request-audit.json", audit)
    events = json.loads((destination / "events.json").read_text(encoding="utf-8"))
    trace = json.loads((destination / "adapter-trace.json").read_text(encoding="utf-8"))
    calls = [event["item"] for event in events if event.get("type") == "item.completed"
             and event.get("item", {}).get("type") == "mcp_tool_call"]
    if len(calls) != 1:
        raise ValueError(f"{mode['id']}: expected one terminal MCP call")
    call = calls[0]
    if (call.get("server"), call.get("tool"), call.get("arguments")) != ("evaluation", mode["tool"], mode["arguments"]):
        raise ValueError(f"{mode['id']}: host call differs from scripted request")
    outputs = [item for item in captured[1].get("input", []) if item.get("type") == "function_call_output"]
    kind, payload = payload_texts(call)
    if len(outputs) != 1 or _model_payload(outputs[0].get("output"), kind) != payload:
        raise ValueError(f"{mode['id']}: model-visible payload differs from host tool result")
    if mode["expected"] == "source":
        deliveries = trace.get("deliveries", [])
        if len(deliveries) != 1 or deliveries[0].get("source_bytes", 0) <= 0:
            raise ValueError(f"{mode['id']}: source-bearing call was not retained")
    elif mode["expected"] == "schema_error":
        if trace.get("attempts") != 0 or trace.get("deliveries"):
            raise ValueError(f"{mode['id']}: schema error entered the adapter")
    return {
        "id": mode["id"], "arm": mode["arm"], "tool": mode["tool"],
        "expected": mode["expected"], "request_count": len(captured),
        "canonical_tool_schemas_sha256": audit["canonical_tool_schemas_sha256"],
        "prompt_sha256": sha(prompt.encode()), "tool_payload_verified": True,
        "trace_attempts": trace.get("attempts"),
        "evidence_dir": str(destination.relative_to(evidence.parent)),
    }


def verify_transport(corpus: dict[str, Any], catalog: Path, output: Path) -> dict[str, Any]:
    """Write zero-provider-call transport evidence for A exact and B workflow."""

    output, catalog = Path(output).resolve(), Path(catalog).resolve()
    evidence = output.with_name(output.stem + "-evidence")
    if output.exists() or evidence.exists():
        raise ValueError("transport evidence cannot be overwritten")
    controls = load_controls(corpus)
    case = _first_case(corpus)
    symbol_id = _symbol_id(case)
    evidence.mkdir(parents=True)
    hashes = _schema_hashes(corpus, controls, catalog)
    declaration = {
        "schema_version": 1, "version": runner.COMPARISON, "provider_calls": 0,
        "model": runner.MODEL, "reasoning_effort": runner.REASONING_EFFORT,
        "service_tier": runner.SERVICE_TIER, "request_max_retries": runner.REQUEST_MAX_RETRIES,
        "stream_max_retries": runner.STREAM_MAX_RETRIES, "catalog_sha256": sha(catalog.read_bytes()),
        "canonical_tool_schemas_sha256": hashes,
    }
    save(evidence / "offline-probe-declaration.json", declaration)
    freeze = {**declaration, "freeze_commit": command(["git", "rev-parse", "HEAD"], cwd=runner.ROOT),
              "freeze_json_sha256": sha((evidence / "offline-probe-declaration.json").read_bytes())}
    modes = (
        {"id": "A_exact_get", "arm": "A", "tool": "get", "arguments": {"symbol_ids": [symbol_id], "context": 0}, "expected": "source"},
        {"id": "B_explore_null", "arm": "B", "tool": "loci_explore", "arguments": {"intent": "locate", "query": case["context"][0]["symbol"]["name"], "max_output_bytes": None, "max_evidence_bytes": None}, "expected": "source"},
        {"id": "B_explore_schema_error", "arm": "B", "tool": "loci_explore", "arguments": {"intent": "locate", "query": "x", "max_hops": True}, "expected": "schema_error"},
    )
    observations = [_run_mode(corpus, controls, catalog, evidence, mode, freeze) for mode in modes]
    if any(item["canonical_tool_schemas_sha256"] != hashes[item["arm"]] for item in observations):
        raise ValueError("delivered transport schema differs from preflight request")
    result = {**declaration, "passed": True,
              "meaning": "Actual Codex/MCP host with scripted local Responses endpoint; no provider outcome.",
              "modes": observations, "guide_sha256": sha(controls["agent"]["workflow_guide"].encode()),
              "guide_utf8_bytes": len(controls["agent"]["workflow_guide"].encode())}
    save(output, result)
    return result


def main() -> None:
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    corpus, _controls = load_inputs(runner.INPUTS_ROOT)
    print(json.dumps(verify_transport(corpus, args.catalog, args.output)))


if __name__ == "__main__":
    main()
