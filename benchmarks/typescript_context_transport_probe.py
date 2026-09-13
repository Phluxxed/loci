"""Verify Codex transport payload rendering with a loopback fake-SSE server.

The probe exercises the shipped request/response boundary without authenticating
or calling a provider model.  It is a protocol check, not a benchmark attempt.
"""

from __future__ import annotations

import argparse
import http.server
import json
import tempfile
import threading
import uuid
from pathlib import Path
from typing import Any


MODES = (
    (
        "structured_read",
        "mcp__evaluation",
        "read",
        {
            "operation": "search",
            "parameters": {"query": "processOrder"},
            "reason": "task_context",
            "detail": "Inspect the requested declaration",
        },
    ),
    (
        "invalid_lineage_read",
        "mcp__evaluation",
        "read",
        {
            "operation": "search",
            "parameters": {"query": "processOrder"},
            "reason": "missing_context",
            "detail": "Inspect a missing declaration",
            "because": "not-an-event",
        },
    ),
    (
        "schema_error_read",
        "mcp__evaluation",
        "read",
        {
            "operation": "invalid",
            "parameters": {},
            "reason": "task_context",
            "detail": "Probe schema errors",
        },
    ),
    (
        "list_resources_evaluation",
        "functions",
        "list_mcp_resources",
        {"server": "evaluation"},
    ),
    (
        "list_resources_all_servers",
        "functions",
        "list_mcp_resources",
        {},
    ),
    (
        "list_resource_templates_evaluation",
        "functions",
        "list_mcp_resource_templates",
        {"server": "evaluation"},
    ),
    (
        "read_resource_missing",
        "functions",
        "read_mcp_resource",
        {"server": "evaluation", "uri": "missing://probe"},
    ),
)


def _request_tool_set(request: dict[str, Any]) -> tuple[list[tuple[str, str]], str]:
    tools: list[tuple[str, str]] = []
    namespaces = []
    for item in request.get("input", []):
        if item.get("type") != "additional_tools":
            continue
        namespaces.extend(item.get("tools", []))
    for namespace in namespaces:
        if namespace.get("type") != "namespace":
            raise ValueError("unexpected non-namespace additional tool")
        for tool in namespace.get("tools", []):
            tools.append((namespace.get("name"), tool.get("name")))
    return tools, _sha(_wire({"tools": [item['tools'] for item in request.get("input", [])
                                      if item.get("type") == "additional_tools"]}))


def _wire(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), allow_nan=False)


def _sha(value: str | bytes) -> str:
    if isinstance(value, str):
        value = value.encode("utf-8")
    import hashlib

    return hashlib.sha256(value).hexdigest()


def _sse_response(namespace: str, name: str, arguments: dict[str, Any]) -> bytes:
    item = {
        "type": "function_call",
        "id": "fc_probe",
        "call_id": "call_probe",
        "namespace": namespace,
        "name": name,
        "arguments": json.dumps(arguments, ensure_ascii=False, separators=(",", ":")),
    }
    response = {
        "id": "resp_probe",
        "object": "response",
        "created_at": 0,
        "model": "gpt-5.6-luna",
        "status": "completed",
        "output": [item],
        "usage": {"input_tokens": 1, "output_tokens": 1, "total_tokens": 2},
    }
    events = [
        {
            "type": "response.created",
            "response": {**response, "status": "in_progress", "output": []},
        },
        {
            "type": "response.output_item.added",
            "output_index": 0,
            "item": {**item, "arguments": ""},
        },
        {
            "type": "response.function_call_arguments.delta",
            "item_id": "fc_probe",
            "output_index": 0,
            "delta": item["arguments"],
        },
        {"type": "response.output_item.done", "output_index": 0, "item": item},
        {"type": "response.completed", "response": response},
    ]
    return "".join(
        f"event: {event['type']}\ndata: {json.dumps(event, ensure_ascii=False)}\n\n"
        for event in events
    ).encode("utf-8")


def _model_payload(output: Any, payload_kind: str) -> list[str]:
    if payload_kind == "compact_json":
        if not isinstance(output, str) or "\nOutput:\n" not in output:
            raise ValueError("structured output lacks the expected timing/output separator")
        return [output.split("\nOutput:\n", 1)[1]]
    if isinstance(output, str):
        return [output]
    if not isinstance(output, list) or not output:
        raise ValueError("text output is neither a string nor an input_text array")
    if any(not isinstance(part, dict) or part.get("type") != "input_text"
           or not isinstance(part.get("text"), str) for part in output):
        raise ValueError("text output contains a non-input_text part")
    first = output[0]["text"]
    if not first.startswith("Wall time:") or not first.endswith("\nOutput:"):
        raise ValueError("text output array lacks the expected timing prefix")
    return [part["text"] for part in output[1:]]


def _verify_mode(
    *,
    corpus: dict[str, Any],
    catalog: Path,
    mode: str,
    namespace: str,
    name: str,
    arguments: dict[str, Any],
    payload_texts,
    baseline,
    corpus_tools,
) -> dict[str, Any]:
    settings = baseline["settings"]
    launch_args = baseline["launch_args"]
    child_environment = baseline["child_environment"]
    execute = baseline["execute"]
    save = baseline["save"]
    service = corpus_tools["service"]
    isolated_store = corpus_tools["isolated_store"]
    materialize_snapshot = corpus_tools["materialize_snapshot"]

    with tempfile.TemporaryDirectory(prefix="loci-v2-transport-") as temporary:
        temp = Path(temporary)
        repo, store = temp / "snapshot", temp / "store"
        materialize_snapshot(corpus, "imported_interface", repo)
        with isolated_store(store):
            service.index_repo(repo, incremental=False)
        run = {
            "repo": str(repo.resolve()),
            "corpus_root": corpus["_root"],
            "case_id": "imported_interface",
            "session_id": str(uuid.uuid4()),
            "arm": "A",
            "repetition": 1,
            "trace_path": str(temp / "trace.json"),
        }
        save(temp / "run.json", run)
        captured: list[dict[str, Any]] = []

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_POST(self):  # noqa: N802
                length = int(self.headers["content-length"])
                captured.append(json.loads(self.rfile.read(length)))
                if len(captured) == 1:
                    body = _sse_response(namespace, name, arguments)
                    self.send_response(200)
                    self.send_header("Content-Type", "text/event-stream")
                    self.end_headers()
                    self.wfile.write(body)
                    self.wfile.flush()
                else:
                    self.send_response(400)
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    self.wfile.write(
                        b'{"error":{"message":"offline transport probe complete",'
                        b'"type":"invalid_request_error"}}'
                    )

            def log_message(self, *_args):
                pass

        server = http.server.HTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        config = settings(temp / "run.json", catalog, store)
        config.update(
            {
                "model_provider": "inspection",
                "model_providers.inspection.name": "Offline transport probe",
                "model_providers.inspection.base_url":
                    f"http://127.0.0.1:{server.server_port}/v1",
                "model_providers.inspection.wire_api": "responses",
                "model_providers.inspection.requires_openai_auth": False,
            }
        )
        try:
            code, stdout, stderr, elapsed, timed_out = execute(
                launch_args(repo, config, "Offline transport verification."),
                child_environment(temp / "runtime", False),
                25,
            )
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)

        events = [json.loads(line) for line in stdout.splitlines() if line.strip()]
        call_events = [
            event
            for event in events
            if event.get("type") == "item.completed"
            and isinstance(event.get("item"), dict)
            and event["item"].get("type") == "mcp_tool_call"
        ]
        if len(captured) != 2:
            raise ValueError(f"{mode}: expected exactly two requests, got {len(captured)}: {stderr[-2000:]}")
        if timed_out or code not in {0, 1}:
            raise ValueError(f"{mode}: unexpected Codex termination code={code}, timed_out={timed_out}: {stderr[-2000:]}")
        if len(call_events) != 1:
            raise ValueError(f"{mode}: expected one terminal mcp_tool_call, got {len(call_events)}")
        call_event = call_events[0]
        call = call_event["item"]
        if call.get("status") not in {"completed", "failed"}:
            raise ValueError(f"{mode}: terminal call has invalid status {call.get('status')!r}")
        outputs = [
            item
            for item in captured[-1].get("input", [])
            if item.get("type") == "function_call_output"
        ]
        if len(outputs) != 1:
            raise ValueError(f"{mode}: expected one model function_call_output, got {len(outputs)}")
        try:
            payload_kind, expected = payload_texts(call)
        except ValueError as exc:
            raise ValueError(f"{mode}: {exc}; call={_wire(call)}; model_outputs={_wire(outputs)}") from exc
        actual = _model_payload(outputs[0].get("output"), payload_kind)
        if actual != expected:
            raise ValueError(f"{mode}: model output does not match delivered payload")

        tool_set, tool_schemas_sha256 = _request_tool_set(captured[0])
        expected_tools = {
            ("mcp__evaluation", "read"),
            ("functions", "list_mcp_resources"),
            ("functions", "list_mcp_resource_templates"),
            ("functions", "read_mcp_resource"),
        }
        if set(tool_set) != expected_tools:
            raise ValueError(f"{mode}: unexpected tool set {tool_set!r}")
        request = captured[0]
        if request.get("model") != "gpt-5.6-luna":
            raise ValueError(f"{mode}: unexpected model {request.get('model')!r}")
        if request.get("reasoning", {}).get("effort") != "high":
            raise ValueError(f"{mode}: unexpected reasoning settings")
        return {
            "mode": mode,
            "case_id": "imported_interface",
            "requested_case_mode": "imported_interface",
            "request_count": len(captured),
            "exit_code": code,
            "timed_out": timed_out,
            "elapsed_seconds": elapsed,
            "model": request["model"],
            "reasoning": request["reasoning"],
            "tool_set": tool_set,
            "tool_schemas_sha256": tool_schemas_sha256,
            "call_event": call_event,
            "call_item": call,
            "model_tool_outputs": outputs,
            "payload_kind": payload_kind,
            "payload_texts": expected,
            "output_verified": True,
        }


def verify_transport(corpus: dict, catalog: Path, output: Path) -> dict[str, Any]:
    """Run all deterministic transport modes and save their evidence."""
    if output.exists():
        raise ValueError(f"transport probe output already exists: {output}")
    catalog = Path(catalog).resolve()
    if not catalog.is_file():
        raise ValueError(f"model catalog does not exist: {catalog}")
    case_ids = {case["id"] for case in corpus.get("cases", [])}
    if "imported_interface" not in case_ids:
        raise ValueError("v2 transport probe requires imported_interface")

    # Keep benchmark imports local: importing this module alone must not create
    # stores, inspect credentials, or initialize a transport.
    from benchmarks.typescript_context_baseline import (
        child_environment,
        execute,
        launch_args,
        save,
        settings,
    )
    from benchmarks.typescript_context_corpus import (
        _isolated_store,
        materialize_snapshot,
    )
    from benchmarks.typescript_context_delivery import payload_texts
    from loci import service

    output.parent.mkdir(parents=True, exist_ok=True)
    baseline = {
        "settings": settings,
        "launch_args": launch_args,
        "child_environment": child_environment,
        "execute": execute,
        "save": save,
    }
    corpus_tools = {
        "service": service,
        "isolated_store": _isolated_store,
        "materialize_snapshot": materialize_snapshot,
    }
    observations = []
    for mode, namespace, name, arguments in MODES:
        observations.append(
            _verify_mode(
                corpus=corpus,
                catalog=catalog,
                mode=mode,
                namespace=namespace,
                name=name,
                arguments=arguments,
                payload_texts=payload_texts,
                baseline=baseline,
                corpus_tools=corpus_tools,
            )
        )
    schemas = {mode['tool_schemas_sha256'] for mode in observations}
    if len(schemas) != 1:
        raise ValueError('tool schemas changed during transport verification')
    result = {
        "schema_version": 1,
        "probe": "typescript-context-v2-transport",
        "meaning": "Deterministic offline transport verification; no provider model call or agent baseline measurement.",
        "corpus_root": corpus["_root"],
        "corpus_sha256": (Path(corpus["_root"]) / "corpus.sha256").read_text().strip(),
        "script_sha256": _sha(Path(__file__).read_bytes()),
        "requested_case_mode": "imported_interface",
        "catalog_sha256": _sha(catalog.read_bytes()),
        "canonical_tool_schemas_sha256": next(iter(schemas)),
        "modes": observations,
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

    corpus = load_corpus(args.corpus_root)
    result = verify_transport(corpus, args.catalog, args.output)
    print(json.dumps({'output': str(args.output), 'verified_modes': len(result['modes']),
                      'canonical_tool_schemas_sha256': result['canonical_tool_schemas_sha256']}))


if __name__ == "__main__":
    main()
