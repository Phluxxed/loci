"""Actual Codex/MCP exploration transport proofs using only loopback responses.

Versioned copies of the v3 request/probe validators add the candidate tool set;
all old validators and evidence remain untouched.
"""
from __future__ import annotations

import argparse
import http.server
import json
from pathlib import Path
import subprocess
import tempfile
import threading
import uuid
from typing import Any, Callable

from benchmarks.typescript_context_baseline_v3 import (
    child_environment, execute, launch_args, save, sha, settings as prior_settings,
)
from benchmarks.typescript_context_adapter import wire
from benchmarks.typescript_context_transport_v3 import _empty_trace, _jsonl, _save, _terminal_calls, _wire
from benchmarks.typescript_context_transport_probe import _model_payload, _request_tool_set, _sse_response

HELPERS = {('functions', name) for name in ('list_mcp_resources', 'list_mcp_resource_templates', 'read_mcp_resource')}
TOOLS_MODULE = 'benchmarks.typescript_context_explore_tools'


def tool_names(arm):
    from benchmarks.typescript_context_tools_v3 import TOOL_NAMES
    if arm not in {'A', 'B'}:
        raise ValueError('exploration arm must be A or B')
    return set(TOOL_NAMES) | ({'loci_explore'} if arm == 'B' else set())


def settings(run_file, catalog, store):
    config = prior_settings(run_file, catalog, store)
    config['mcp_servers.evaluation.args'] = ['-m', TOOLS_MODULE, str(run_file)]
    return config


def inspect_request(repo: Path, config: dict, prompt: str, runtime_home: Path, *, arm: str) -> dict:
    captured = []

    class Capture(http.server.BaseHTTPRequestHandler):
        def do_POST(self):
            captured.append(json.loads(self.rfile.read(int(self.headers['content-length']))))
            self.send_response(400)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(b'{"error":{"message":"offline request inspection complete","type":"invalid_request_error"}}')

        def log_message(self, format: str, *args):
            pass

    server = http.server.HTTPServer(('127.0.0.1', 0), Capture)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    inspection = {**config, 'model_provider': 'inspection',
                  'model_providers.inspection.name': 'Offline request inspection',
                  'model_providers.inspection.base_url': f'http://127.0.0.1:{server.server_port}/v1',
                  'model_providers.inspection.wire_api': 'responses',
                  'model_providers.inspection.requires_openai_auth': False}
    try:
        inspected = subprocess.run(launch_args(repo, inspection, prompt), capture_output=True, text=True,
                       env=child_environment(runtime_home, False), timeout=25)
    finally:
        server.shutdown()
        server.server_close()
    if len(captured) != 1:
        raise ValueError('Codex did not emit exactly one offline inspection request: ' + inspected.stderr[-2000:])
    return audit_request(captured[0], prompt, arm)


def audit_request(request, prompt, arm):
    tools = []
    for item in request['input']:
        if item['type'] == 'additional_tools':
            for namespace in item['tools']:
                if namespace['type'] != 'namespace':
                    raise ValueError('unexpected hosted/discovery tool in evaluation request')
                tools.extend((namespace['name'], t['name']) for t in namespace['tools'])
        for part in item.get('content', []):
            text = part.get('text', '')
            if any(marker in text for marker in ('# AGENTS.md instructions', '## Brain Context',
                    'Anvil Continuity Frame', '<skills_instructions>', 'LOCI_ADAPTER_READY')):
                raise ValueError('ambient instructions or probe data reached the evaluation prompt: ' + text[:160])
    expected = {('mcp__evaluation', name) for name in tool_names(arm)} | {
        ('functions', 'list_mcp_resources'), ('functions', 'list_mcp_resource_templates'),
        ('functions', 'read_mcp_resource')}
    if len(tools) != len(expected) or set(tools) != expected:
        raise ValueError(f'unexpected evaluation tool set: {tools}')
    if request['input'][-1].get('content') != [{'type': 'input_text', 'text': prompt}]:
        raise ValueError('effective task prompt differs from frozen common prompt plus case')
    if request['model'] != 'gpt-5.6-luna' or request['reasoning']['effort'] != 'high':
        raise ValueError('effective model settings differ from frozen controls')
    # Request IDs are transport metadata. Retain all actual model-visible input.
    visible = {k: request[k] for k in ('model', 'input', 'reasoning', 'text') if k in request}
    return {'request': visible, 'request_sha256': sha(wire(visible).encode()), 'tools': tools,
            'tool_schemas_sha256': sha(wire({'tools': [i for i in request['input'] if i['type'] == 'additional_tools']}).encode()),
            'canonical_tool_schemas_sha256': sha(wire({'tools': [i['tools'] for i in request['input'] if i['type'] == 'additional_tools']}).encode()),
            'inspection': 'actual Codex request, local no-auth transport; no model called',
            'resource_helpers': 'Only evaluation server configured; no resources or templates exposed.'}


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
            "arm": mode["arm"],
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

            def log_message(self, format: str, *args):
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
        from benchmarks.typescript_context_corpus import load_controls
        case = next(c for c in corpus['cases'] if c['id'] == 'imported_interface')
        prompt = load_controls(corpus)['agent']['common_prompt'] + case['prompt']
        try:
            code, stdout, stderr, elapsed, timed_out = execute(
                launch_args(repo, config, prompt),
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
        expected_tools = {("mcp__evaluation", name) for name in tool_names(mode["arm"])} | HELPERS
        if len(tool_set) != len(expected_tools) or set(tool_set) != expected_tools:
            raise ValueError(f"{mode['id']}: unexpected fixed tool set {tool_set!r}")
        request = captured[0]
        _save(evidence / 'request-audit.json', audit_request(request, prompt, mode['arm']))
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
            "arm": mode["arm"],
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


def verify_transport(corpus, catalog, output):
    from benchmarks.typescript_context_corpus import _isolated_store, materialize_snapshot
    from benchmarks.typescript_context_delivery import payload_texts
    from benchmarks.typescript_context_explore_observed import reconcile_observed
    from loci import service

    output = Path(output).resolve()
    if output.exists():
        raise ValueError('transport evidence cannot be overwritten')
    output.parent.mkdir(parents=True, exist_ok=True)
    evidence = output.with_name(output.stem + '-evidence')
    evidence.mkdir()
    modes = [
        {'id': 'A_exact_get', 'arm': 'A', 'tool': 'get', 'arguments': {'symbol_ids': ['consumer.ts::processOrder#function']}, 'expected': 'recorded'},
        {'id': 'B_exact_get', 'arm': 'B', 'tool': 'get', 'arguments': {'symbol_ids': ['consumer.ts::processOrder#function']}, 'expected': 'recorded'},
        {'id': 'B_explore_types', 'arm': 'B', 'tool': 'loci_explore', 'arguments': {'intent': 'type_dependencies', 'seed_ids': ['consumer.ts::processOrder#function']}, 'expected': 'recorded'},
        {'id': 'B_explore_query', 'arm': 'B', 'tool': 'loci_explore', 'arguments': {'intent': 'locate', 'query': 'processOrder'}, 'expected': 'recorded'},
        {'id': 'B_explore_empty', 'arm': 'B', 'tool': 'loci_explore', 'arguments': {'intent': 'type_dependencies', 'seed_ids': ['consumer.ts::processOrder#function'], 'max_evidence_bytes': 0}, 'expected': 'recorded'},
        {'id': 'B_explore_unknown', 'arm': 'B', 'tool': 'loci_explore', 'arguments': {'intent': 'locate', 'repo': '/wrong'}, 'expected': 'schema_error'},
        {'id': 'B_explore_bool_hops', 'arm': 'B', 'tool': 'loci_explore', 'arguments': {'intent': 'locate', 'query': 'processOrder', 'max_hops': True}, 'expected': 'schema_error'},
        {'id': 'B_resources', 'arm': 'B', 'namespace': 'functions', 'tool': 'list_mcp_resources', 'arguments': {'server': 'evaluation'}, 'expected': 'helper'},
    ]
    observations = []
    for mode in modes:
        mode.setdefault('namespace', 'mcp__evaluation')
        observations.append(_verify_mode(corpus=corpus, catalog=Path(catalog), output_root=evidence,
            mode=mode, settings=settings, launch_args=launch_args, child_environment=child_environment,
            execute=execute, save=save, materialize_snapshot=materialize_snapshot,
            isolated_store=_isolated_store, service=service, payload_texts=payload_texts,
            reconcile_observed=reconcile_observed))
    hashes = {}
    for arm in ('A', 'B'):
        values = {o['canonical_tool_schemas_sha256'] for o in observations if o['arm'] == arm}
        if len(values) != 1:
            raise ValueError('schemas changed within an arm')
        hashes[arm] = values.pop()
    if hashes['A'] == hashes['B']:
        raise ValueError('candidate workflow was not exposed separately')
    # The original tool definitions must remain byte-identical in both arms.
    requests = [json.loads((evidence / name / 'effective-request.json').read_text())
                for name in ('A_exact_get', 'B_exact_get')]
    schemas = []
    for request in requests:
        schemas.append({(namespace['name'], tool['name']): tool for item in request['input']
                        if item['type'] == 'additional_tools' for namespace in item['tools']
                        for tool in namespace['tools'] if tool['name'] != 'loci_explore'})
    if schemas[0] != schemas[1]:
        raise ValueError('common tool schemas differ between arms')
    result = {'schema_version': 1, 'comparison': 'typescript-context-explore-v1',
        'meaning': 'Real Codex and MCP with deterministic loopback responses; zero provider calls.',
        'canonical_tool_schemas_sha256': hashes, 'common_tool_schemas_identical': True,
        'tool_counts': {'A': 16, 'B': 17}, 'modes': observations,
        'catalog_sha256': sha(Path(catalog).read_bytes())}
    _save(output, result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--corpus-root', type=Path, required=True)
    parser.add_argument('--catalog', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    from benchmarks.typescript_context_corpus import load_corpus
    result = verify_transport(load_corpus(args.corpus_root), args.catalog, args.output)
    print(json.dumps({'verified_modes': len(result['modes']), 'schema_hashes': result['canonical_tool_schemas_sha256']}))


if __name__ == '__main__':
    main()
