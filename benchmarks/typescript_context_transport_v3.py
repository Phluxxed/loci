"""Verify the frozen v3 typed tool boundary with a local fake Responses server.

The verifier starts the real Codex CLI and the real MCP server, but the model
endpoint is a loopback HTTP server that returns one deterministic tool call and
then a bounded HTTP error.  It therefore checks request schemas, host
validation, delivered payloads, and v3 observation accounting without making a
provider request.
"""

from __future__ import annotations

import argparse
import http.server
import json
import tempfile
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Callable

from benchmarks.typescript_context_transport_probe import (
    _model_payload,
    _request_tool_set,
    _sse_response,
)


_SYMBOL_ID = "consumer.ts::processOrder#function"
_MODES: tuple[dict[str, Any], ...] = (
    {
        "id": "typed_search",
        "namespace": "mcp__evaluation",
        "tool": "search",
        "arguments": {"query": "processOrder"},
        "expected": "recorded",
    },
    {
        "id": "typed_get",
        "namespace": "mcp__evaluation",
        "tool": "get",
        "arguments": {"symbol_ids": [_SYMBOL_ID]},
        "expected": "recorded",
    },
    {
        "id": "grep_unknown_file_paths",
        "namespace": "mcp__evaluation",
        "tool": "grep",
        "arguments": {"pattern": "processOrder", "file_paths": ["consumer.ts"]},
        "expected": "schema_error",
    },
    {
        "id": "get_bool_context",
        "namespace": "mcp__evaluation",
        "tool": "get",
        "arguments": {"symbol_ids": [_SYMBOL_ID], "context": True},
        "expected": "schema_error",
    },
    {
        "id": "get_invalid_selection",
        "namespace": "mcp__evaluation",
        "tool": "get",
        "arguments": {"symbol_ids": [_SYMBOL_ID], "selected_from_search_id": "missing-search"},
        "expected": "bounded_error",
    },
    {
        "id": "list_resources_evaluation",
        "namespace": "functions",
        "tool": "list_mcp_resources",
        "arguments": {"server": "evaluation"},
        "expected": "helper",
    },
    {
        "id": "list_resources_all_servers",
        "namespace": "functions",
        "tool": "list_mcp_resources",
        "arguments": {},
        "expected": "helper",
    },
    {
        "id": "list_templates_evaluation",
        "namespace": "functions",
        "tool": "list_mcp_resource_templates",
        "arguments": {"server": "evaluation"},
        "expected": "helper",
    },
    {
        "id": "read_missing_resource",
        "namespace": "functions",
        "tool": "read_mcp_resource",
        "arguments": {"server": "evaluation", "uri": "missing://probe"},
        "expected": "helper",
    },
    {
        "id": "read_unknown_server",
        "namespace": "functions",
        "tool": "read_mcp_resource",
        "arguments": {"server": "mcp__evaluation", "uri": "missing://probe"},
        "expected": "helper",
    },
)


def _wire(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), allow_nan=False)


def _sha(value: str | bytes) -> str:
    import hashlib

    if isinstance(value, str):
        value = value.encode("utf-8")
    return hashlib.sha256(value).hexdigest()


def _save(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
                    encoding="utf-8")


def _jsonl(text: str) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for line in text.splitlines():
        if line.strip():
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise ValueError(f"Codex emitted non-JSON output: {line[:240]}") from exc
    return events


def _empty_trace(corpus: dict[str, Any], run: dict[str, Any]) -> dict[str, Any]:
    from benchmarks.typescript_context_observed import ObservedTrace

    trace = ObservedTrace(corpus, run["case_id"], run["session_id"], run["arm"], run["repetition"])
    return {
        "schema_version": 3,
        "identity": trace.identity,
        "events": [],
        "failures": [],
        "attempts": 0,
        "deliveries": [],
    }


def _expected_tools() -> set[tuple[str, str]]:
    from benchmarks.typescript_context_tools_v3 import TOOL_NAMES

    return {("mcp__evaluation", name) for name in TOOL_NAMES} | {
        ("functions", "list_mcp_resources"),
        ("functions", "list_mcp_resource_templates"),
        ("functions", "read_mcp_resource"),
    }


def _terminal_calls(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        event["item"]
        for event in events
        if event.get("type") in {"item.completed", "item.failed"}
        and isinstance(event.get("item"), dict)
        and event["item"].get("type") == "mcp_tool_call"
    ]


def _verify_mode(
    *,
    corpus: dict[str, Any],
    catalog: Path,
    output_root: Path,
    mode: dict[str, Any],
    settings: Callable[[Path, Path, Path], dict[str, Any]],
    launch_args: Callable[[Path, dict[str, Any], str], list[str]],
    child_environment: Callable[[Path, bool], dict[str, str]],
    execute: Callable[[list[str], dict[str, str], float], tuple[int, str, str, float, bool]],
    save: Callable[[Path, Any], None],
    materialize_snapshot: Callable[[dict[str, Any], str, Path], None],
    isolated_store,
    service,
    payload_texts: Callable[[dict[str, Any]], tuple[str, list[str]]],
    reconcile_observed: Callable[[dict[str, Any], list[dict[str, Any]]], dict[str, Any]],
) -> dict[str, Any]:
    """Run one fake-SSE call and persist all request, output, and trace evidence."""

    evidence = output_root / mode["id"]
    evidence.mkdir(parents=True, exist_ok=False)
    with tempfile.TemporaryDirectory(prefix="loci-v3-transport-") as temporary:
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
        initial_trace = _empty_trace(corpus, run)
        save(Path(run["trace_path"]), initial_trace)
        save(evidence / "initial-trace.json", initial_trace)
        save(evidence / "run.json", run)

        captured: list[dict[str, Any]] = []

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_POST(self):  # noqa: N802
                length = int(self.headers.get("content-length", "0"))
                captured.append(json.loads(self.rfile.read(length)))
                if len(captured) == 1:
                    body = _sse_response(mode["namespace"], mode["tool"], mode["arguments"])
                    self.send_response(200)
                    self.send_header("Content-Type", "text/event-stream")
                    self.send_header("Cache-Control", "no-cache")
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
        config.update({
            "model_provider": "inspection",
            "model_providers.inspection.name": "Offline typed transport probe",
            "model_providers.inspection.base_url": f"http://127.0.0.1:{server.server_port}/v1",
            "model_providers.inspection.wire_api": "responses",
            "model_providers.inspection.requires_openai_auth": False,
        })
        try:
            code, stdout, stderr, elapsed, timed_out = execute(
                launch_args(repo, config, "Offline typed transport verification."),
                child_environment(temp / "runtime", False),
                25,
            )
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)

        events = _jsonl(stdout)
        trace = json.loads(Path(run["trace_path"]).read_text(encoding="utf-8"))
        _save(evidence / "events.json", events)
        _save(evidence / "trace.json", trace)
        _save(evidence / "effective-request.json", captured[0] if captured else {})
        _save(evidence / "next-request.json", captured[1] if len(captured) > 1 else {})
        (evidence / "stdout.jsonl").write_text(stdout, encoding="utf-8")
        (evidence / "stderr.txt").write_text(stderr, encoding="utf-8")

        if len(captured) != 2:
            raise ValueError(f"{mode['id']}: expected first request, follow-up request, got {len(captured)}: {stderr[-2000:]}")
        if timed_out or code not in {0, 1}:
            raise ValueError(f"{mode['id']}: unexpected Codex termination code={code}, timed_out={timed_out}: {stderr[-2000:]}")
        calls = _terminal_calls(events)
        if len(calls) != 1:
            raise ValueError(f"{mode['id']}: expected one terminal mcp_tool_call, got {len(calls)}")
        call = calls[0]
        if mode["namespace"] == "mcp__evaluation" and call.get("server") != "evaluation":
            raise ValueError(f"{mode['id']}: unexpected tool server {call.get('server')!r}")
        if call.get("arguments") != mode["arguments"]:
            raise ValueError(f"{mode['id']}: host-observed arguments differ from injected request")
        if call.get("tool") != mode["tool"]:
            raise ValueError(f"{mode['id']}: expected tool {mode['tool']!r}, got {call.get('tool')!r}")

        outputs = [item for item in captured[-1].get("input", [])
                   if item.get("type") == "function_call_output"]
        if len(outputs) != 1:
            raise ValueError(f"{mode['id']}: expected one model function_call_output, got {len(outputs)}")
        payload_kind, expected_payload = payload_texts(call)
        actual_payload = _model_payload(outputs[0].get("output"), payload_kind)
        if actual_payload != expected_payload:
            raise ValueError(f"{mode['id']}: follow-up payload differs from delivered tool payload")

        tool_set, schema_sha = _request_tool_set(captured[0])
        expected_tools = _expected_tools()
        if len(tool_set) != 16 or set(tool_set) != expected_tools:
            raise ValueError(f"{mode['id']}: unexpected fixed tool set {tool_set!r}")
        request = captured[0]
        if request.get("model") != "gpt-5.6-luna":
            raise ValueError(f"{mode['id']}: unexpected model {request.get('model')!r}")
        if request.get("reasoning", {}).get("effort") != "high":
            raise ValueError(f"{mode['id']}: unexpected reasoning settings")

        accounting = reconcile_observed(trace, events)
        _save(evidence / "accounting.json", accounting)
        if not accounting.get("complete") or accounting.get("tool_call_count") != 1:
            raise ValueError(f"{mode['id']}: incomplete observed accounting: {_wire(accounting)}")

        # Schema failures are intentionally host-side: the generated MCP
        # argument model must reject them before ObservedAdapter._read_v2.
        if mode["expected"] == "schema_error":
            if trace.get("attempts") != 0 or trace.get("deliveries") or trace.get("events"):
                raise ValueError(f"{mode['id']}: schema error entered adapter body")
        if mode["expected"] == "bounded_error":
            if trace.get("attempts") != 1 or len(trace.get("deliveries", [])) != 1:
                raise ValueError(f"{mode['id']}: bounded adapter rejection was not ledgered")
            if trace["deliveries"][0].get("status") != "rejected":
                raise ValueError(f"{mode['id']}: invalid selection did not produce a rejected delivery")

        return {
            "mode": mode["id"],
            "case_id": "imported_interface",
            "request_count": len(captured),
            "exit_code": code,
            "timed_out": timed_out,
            "elapsed_seconds": elapsed,
            "model": request["model"],
            "reasoning": request["reasoning"],
            "tool_set": tool_set,
            "tool_schemas_sha256": schema_sha,
            "canonical_tool_schemas_sha256": schema_sha,
            "call_event": next((event for event in events
                                 if event.get("type") in {"item.completed", "item.failed"}
                                 and event.get("item") is call), None),
            "call_item": call,
            "model_tool_outputs": outputs,
            "payload_kind": payload_kind,
            "payload_texts": expected_payload,
            "observed_accounting": accounting,
            "trace_schema_version": trace.get("schema_version"),
            "expected_mode": mode["expected"],
            "adapter_attempts": trace.get("attempts"),
            "adapter_deliveries": len(trace.get("deliveries", [])),
            "evidence_dir": str(evidence.relative_to(output_root.parent)),
            "output_verified": True,
        }


def verify_transport(corpus: dict[str, Any], catalog: Path, output: Path) -> dict[str, Any]:
    """Run all ten deterministic v3 transport modes and save their evidence."""

    output = Path(output).resolve()
    if output.exists():
        raise ValueError(f"transport verifier output already exists: {output}")
    catalog = Path(catalog).resolve()
    if not catalog.is_file():
        raise ValueError(f"model catalog does not exist: {catalog}")
    if corpus.get("version") != "typescript-context-v3":
        raise ValueError("typescript-context-v3 corpus required")
    if "imported_interface" not in {case["id"] for case in corpus.get("cases", [])}:
        raise ValueError("v3 transport verifier requires imported_interface")

    from benchmarks.typescript_context_baseline_v3 import (
        child_environment,
        execute,
        launch_args,
        save,
        settings,
    )
    from benchmarks.typescript_context_corpus import _isolated_store, load_controls, materialize_snapshot
    from benchmarks.typescript_context_delivery import payload_texts
    from benchmarks.typescript_context_observed import reconcile_observed
    from loci import service

    controls = load_controls(corpus)
    output.parent.mkdir(parents=True, exist_ok=True)
    evidence_root = output.with_name(output.stem + "-evidence")
    evidence_root.mkdir(parents=True, exist_ok=False)
    observations: list[dict[str, Any]] = []
    for mode in _MODES:
        observations.append(_verify_mode(
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
        ))

    schemas = {observation["canonical_tool_schemas_sha256"] for observation in observations}
    if len(schemas) != 1:
        raise ValueError("typed tool schemas changed between transport modes")
    root = Path(corpus["_root"])
    result = {
        "schema_version": 3,
        "probe": "typescript-context-v3-typed-transport",
        "meaning": "Deterministic offline Codex/MCP transport verification; no provider model call.",
        "corpus_root": corpus["_root"],
        "corpus_sha256": _sha((root / "corpus.json").read_bytes()),
        "controls_sha256": _sha((root / "comparison-controls.json").read_bytes()),
        "catalog_sha256": _sha(catalog.read_bytes()),
        "script_sha256": _sha(Path(__file__).read_bytes()),
        "model": "gpt-5.6-luna",
        "reasoning_effort": "high",
        "tool_count": 16,
        "canonical_tool_schemas_sha256": next(iter(schemas)),
        "modes": observations,
        "evidence_root": str(evidence_root.relative_to(output.parent)),
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
    print(json.dumps({
        "output": str(args.output),
        "verified_modes": len(result["modes"]),
        "canonical_tool_schemas_sha256": result["canonical_tool_schemas_sha256"],
    }))


if __name__ == "__main__":
    main()
