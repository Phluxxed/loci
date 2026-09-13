"""Exercise the repaired routing runner with a scripted local Responses endpoint."""
from __future__ import annotations

import http.server
import json
from pathlib import Path
import threading
from typing import Any
from unittest.mock import patch

from benchmarks import typescript_context_routing_v2_run as runner
from benchmarks.typescript_context_corpus import load_controls
from benchmarks.typescript_context_delivery import payload_texts
from benchmarks.typescript_context_explore_transport import HELPERS, tool_names
from benchmarks.typescript_context_routing_v2 import (
    VERSION, audit_request, build_prompt, prompt_manifest,
)
from benchmarks.typescript_context_routing_v2_observed import (
    observe_routing, reconcile_observed,
)
from benchmarks.typescript_context_transport_probe import _model_payload, _sse_response
from benchmarks.typescript_context_transport_v3 import _save, _terminal_calls


def _verify_mode(corpus, catalog: Path, evidence: Path, arm: str, freeze):
    controls = load_controls(corpus)
    plan = next(
        item
        for item in runner.schedule(corpus)
        if item["case_id"] == "imported_interface"
        and item["repetition"] == 1
        and item["arm"] == arm
    )
    # Keep the probe on the repaired nullable-default path. The host-visible
    # request carries explicit nulls; the v2 adapter records resolved defaults.
    arguments = {
        "intent": "type_dependencies",
        "query": "processOrder",
        "max_output_bytes": None,
        "max_evidence_bytes": None,
    }
    captured: list[dict[str, Any]] = []

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_POST(self):  # noqa: N802
            captured.append(json.loads(self.rfile.read(int(self.headers.get("content-length", "0")))))
            if len(captured) == 1:
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.end_headers()
                self.wfile.write(_sse_response("mcp__evaluation", "loci_explore", arguments))
            else:
                self.send_response(400)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(
                    b'{"error":{"message":"offline runner probe complete",'
                    b'"type":"invalid_request_error"}}'
                )
            self.wfile.flush()

        def log_message(self, format: str, *args):
            pass

    server = http.server.HTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    execute = runner.execute

    def local_execute(args, env, timeout):
        # Keep the real runner's launch/settings/prompt/identity path. Only the
        # provider endpoint is replaced, so no inference request leaves the host.
        config = {
            "model_provider": "inspection",
            "model_providers.inspection.name": "Offline routing runner probe",
            "model_providers.inspection.base_url": f"http://127.0.0.1:{server.server_port}/v1",
            "model_providers.inspection.wire_api": "responses",
            "model_providers.inspection.requires_openai_auth": False,
        }
        overrides = [
            part
            for key, value in config.items()
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

    destination = evidence / plan["attempt_id"]
    _save(destination / "captured-requests.json", captured)
    if len(captured) != 2 or result.get("runner_failures"):
        raise ValueError(
            f"{arm}: incomplete real-runner transport: {len(captured)=}; "
            f"{result.get('runner_failures')=}"
        )

    prompt = build_prompt(corpus, controls, plan["case_id"], arm)
    audit = audit_request(captured[0], prompt)
    runner.save(destination / "actual-request-audit.json", audit)
    expected_tools = {("mcp__evaluation", name) for name in tool_names("B")} | HELPERS
    if len(audit["tools"]) != 17 or set(audit["tools"]) != expected_tools:
        raise ValueError(f"{arm}: actual request did not expose the shared 14+3 tool surface")

    events = json.loads((destination / "events.json").read_text())
    trace = json.loads((destination / "adapter-trace.json").read_text())
    run = json.loads((destination / "run.json").read_text())
    expected_identity = runner.routing_identity(corpus, controls, plan, freeze)
    manifest = prompt_manifest(corpus, controls)
    if (
        run["arm"] != arm
        or run["attempt_id"] != plan["attempt_id"]
        or trace["identity"]["arm"] != arm
        or result["identity"]["arm"] != arm
        or result["identity"]["session_id"] != trace["identity"]["session_id"]
        or result["attempt_id"] != plan["attempt_id"]
        or result["arm"] != arm
        or result["provenance"]["attempt_id"] != plan["attempt_id"]
        or result["provenance"]["routing"] != expected_identity
        or result["provenance"]["prompt_sha256"] != audit["prompt_sha256"]
        or audit["prompt_sha256"] != manifest["cases"][
            next(i for i, item in enumerate(manifest["cases"]) if item["case_id"] == plan["case_id"])
        ]["prompts"][arm]["sha256"]
    ):
        raise ValueError(f"{arm}: actual runner lost routing identity or prompt binding")

    calls = _terminal_calls(events)
    if len(calls) != 1 or (
        calls[0].get("server"),
        calls[0].get("tool"),
        calls[0].get("arguments"),
    ) != ("evaluation", "loci_explore", arguments):
        raise ValueError(f"{arm}: actual runner did not execute the requested null-budget call")
    outputs = [
        item for item in captured[1]["input"] if item.get("type") == "function_call_output"
    ]
    kind, payload = payload_texts(calls[0])
    if len(outputs) != 1 or _model_payload(outputs[0].get("output"), kind) != payload:
        raise ValueError(f"{arm}: native output changed before next request")

    accounting = reconcile_observed(trace, events)
    case = next(item for item in corpus["cases"] if item["id"] == plan["case_id"])
    routing = observe_routing(corpus, case, trace, events)
    runner.save(destination / "observed-accounting.json", accounting)
    if (
        not accounting["complete"]
        or accounting["tool_call_count"] != 1
        or not routing["observations_complete"]
        or routing["initial_type_route"] is not True
        or routing["requested_anchor_received"] is not True
        or routing["maintained_exposure"] is not None
        or result["routing"] != routing
    ):
        raise ValueError(f"{arm}: source-bearing route was not measured through actual runner: {routing}")

    return {
        "routing_arm": arm,
        "adapter_identity_arm": trace["identity"]["arm"],
        "capability_arm": "B",
        "case_id": plan["case_id"],
        "request_count": len(captured),
        "tool_count": len(audit["tools"]),
        "canonical_tool_schemas_sha256": audit["canonical_tool_schemas_sha256"],
        "prompt_sha256": audit["prompt_sha256"],
        "identity_verified": True,
        "native_output_verified": True,
        "source_and_routing_verified": True,
        "observed_call_count": accounting["tool_call_count"],
        "routing": routing,
        "evidence_dir": str(destination.relative_to(evidence.parent)),
        "model_adoption_measured": False,
        "expected_provider_error": "offline runner probe complete",
    }


def verify_transport(corpus, catalog: Path, output: Path):
    output = output.resolve()
    evidence = output.with_name(output.stem + "-evidence")
    if output.exists() or evidence.exists():
        raise ValueError("actual-runner transport evidence cannot be overwritten")
    evidence.mkdir(parents=True)

    controls = load_controls(corpus)
    declaration = prompt_manifest(corpus, controls)
    manifest_path = runner.COMPARISON_ROOT / "prompt-manifest.json"
    if json.loads(manifest_path.read_text(encoding="utf-8")) != declaration:
        raise ValueError("published routing prompt manifest differs from the policy declaration")
    if declaration["policy_utf8_bytes"] != 1_154 or declaration["candidate_prefix_utf8_bytes"] != 1_155:
        raise ValueError("routing policy prefix must remain the published 1154-byte policy")

    published = json.loads(
        (runner.COMPARISON_ROOT / "byte-limit-transport.json").read_text(encoding="utf-8")
    )
    expected_schema_hash = published["canonical_tool_schemas_sha256"]
    if not isinstance(expected_schema_hash, str) or not expected_schema_hash:
        raise ValueError("published repaired transport schema hash is missing")

    # This explicit local probe declaration is a fake freeze for transport
    # acceptance. It binds the repaired engine at current HEAD and the new
    # policy/manifest, without requiring a real qualification freeze.
    engine = runner.engine_identity()
    freeze_commit = runner.git("rev-parse", "HEAD")
    if engine["commit"] != freeze_commit:
        raise ValueError("offline probe engine must be the current HEAD engine")
    freeze = {
        "engine": engine,
        "freeze_commit": freeze_commit,
        "canonical_tool_schemas_sha256": {"A": expected_schema_hash, "B": expected_schema_hash},
        "policy_sha256": declaration["policy_sha256"],
        "prompt_manifest_sha256": runner.sha(manifest_path.read_bytes()),
    }
    runner.save(evidence / "offline-probe-declaration.json", freeze)
    freeze["freeze_json_sha256"] = runner.sha(
        (evidence / "offline-probe-declaration.json").read_bytes()
    )
    observations = [_verify_mode(corpus, catalog.resolve(), evidence, arm, freeze) for arm in ("A", "B")]
    hashes = {item["routing_arm"]: item["canonical_tool_schemas_sha256"] for item in observations}
    expected_hashes = {"A": expected_schema_hash, "B": expected_schema_hash}
    if hashes != expected_hashes or len(set(hashes.values())) != 1:
        raise ValueError("actual runner tool schemas differ from the published repaired transport")

    result = {
        "schema_version": 1,
        "version": VERSION,
        "engine": freeze["engine"],
        "meaning": "Actual run_attempt entrypoint, real Codex/MCP, scripted loopback Responses endpoint.",
        "provider_calls": 0,
        "model_adoption_measured": False,
        "canonical_tool_schemas_sha256": hashes,
        "identical_tool_schemas": True,
        "tool_counts": {"A": 17, "B": 17},
        "modes": observations,
        "policy_sha256": declaration["policy_sha256"],
        "candidate_prefix_utf8_bytes": declaration["candidate_prefix_utf8_bytes"],
        "catalog_sha256": runner.sha(catalog.read_bytes()),
    }
    runner.save(output, result)
    return result


__all__ = ["_verify_mode", "verify_transport"]
