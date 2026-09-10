"""Run the frozen A-only TypeScript baseline through isolated local Codex."""
from __future__ import annotations

import argparse
import hashlib
import http.server
import importlib.metadata
import json
import os
import platform
import signal
import subprocess
import sys
import tempfile
import threading
import time
import uuid
from pathlib import Path

from benchmarks.typescript_context_adapter import wire
from benchmarks.typescript_context_corpus import (
    DEFAULT_ROOT, _isolated_store, load_controls, load_corpus, materialize_snapshot, preflight,
)
from benchmarks.typescript_context_trace import ReadTrace
from loci import service
from loci.storage.index_store import EXTRACTOR_VERSION

ROOT = Path(__file__).resolve().parents[1]
HARNESS_FILES = [ROOT / 'benchmarks' / f'typescript_context_{name}.py'
                 for name in ('adapter', 'baseline', 'corpus', 'relationships', 'trace')]
DISABLED_FEATURES = ['shell_tool', 'multi_agent', 'apps', 'plugins', 'hooks', 'memories',
                     'skill_search', 'skill_mcp_dependency_install', 'view_image', 'image_generation',
                     'browser_use', 'computer_use', 'in_app_browser', 'code_mode', 'code_mode_host',
                     'sleep_tool', 'goals', 'context_management']
CATALOG_OVERRIDES = {'apply_patch_tool_type': None, 'tool_mode': 'direct',
                     'supports_search_tool': False, 'multi_agent_version': None}


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def save(path: Path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n')


def command(args: list[str], **kwargs) -> str:
    return subprocess.run(args, check=True, capture_output=True, text=True, **kwargs).stdout.strip()


def environment(controls: dict) -> dict:
    observed = {'python': sys.version, 'platform': platform.platform(), 'machine': platform.machine(),
                'packages': {p.metadata['Name']: p.version for p in importlib.metadata.distributions()},
                'pyproject_sha256': sha((ROOT / 'pyproject.toml').read_bytes()),
                'uv_lock_sha256': sha((ROOT / 'uv.lock').read_bytes())}
    if observed != controls['environment']:
        changed = [key for key in observed if observed[key] != controls['environment'].get(key)]
        raise ValueError(f'environment differs from frozen controls: {changed}')
    return observed


def prepare_catalog(output: Path, model: str) -> Path:
    raw = command(['codex', 'debug', 'models'])
    catalog = json.loads(raw)
    original = next(m for m in catalog['models'] if m['slug'] == model)
    selected = {**original, **CATALOG_OVERRIDES}
    path = output / 'model-catalog.json'
    save(path, {'models': [selected]})
    save(output / 'model-catalog-provenance.json', {'original_model': original,
         'overrides': CATALOG_OVERRIDES,
         'purpose': 'Remove non-evaluation capabilities; preserve requested model and model instructions.',
         'catalog_stdout_sha256': sha(raw.encode()), 'effective_catalog_sha256': sha(path.read_bytes())})
    return path


def settings(run_file: Path, catalog: Path, store: Path) -> dict:
    result = {'project_doc_max_bytes': 0, 'web_search': 'disabled',
              'skills.include_instructions': False, 'developer_instructions': '',
              'model_reasoning_effort': 'high', 'model_catalog_json': str(catalog.resolve()),
              'include_collaboration_mode_instructions': False,
              'tools.update_plan.enabled': False, 'tools.experimental_request_user_input.enabled': False,
              'features.skip_host_skill_discovery': True,
              'mcp_servers.evaluation.command': sys.executable,
              'mcp_servers.evaluation.args': ['-m', 'benchmarks.typescript_context_adapter', str(run_file)],
              'mcp_servers.evaluation.cwd': str(ROOT),
              'mcp_servers.evaluation.env': {'LOCI_BASE_DIR': str(store),
                                           'LOCI_STORE_NAMESPACE': 'typescript-context-preflight'},
              'mcp_servers.evaluation.required': True,
              'mcp_servers.evaluation.default_tools_approval_mode': 'auto',
              'mcp_servers.evaluation.tool_timeout_sec': 12,
              'tool_output_token_limit': 32768}
    result.update({'features.' + name: False for name in DISABLED_FEATURES})
    return result


def launch_args(repo: Path, config: dict, prompt: str) -> list[str]:
    args = ['codex', 'exec', '--ignore-user-config', '--ephemeral', '--skip-git-repo-check',
            '--sandbox', 'read-only', '--json', '--color', 'never', '-m', 'gpt-5.6-luna', '-C', str(repo)]
    for key, value in config.items():
        # CLI overrides are TOML; dicts need inline-table '=' syntax.
        if isinstance(value, dict):
            value_text = '{' + ', '.join(json.dumps(k) + '=' + json.dumps(v) for k, v in value.items()) + '}'
        else:
            value_text = json.dumps(value)
        args += ['-c', key + '=' + value_text]
    return args + [prompt]


def child_environment(runtime_home: Path, authenticate: bool) -> dict:
    runtime_home.mkdir(mode=0o700, exist_ok=True)
    if authenticate:
        auth = Path.home() / '.codex' / 'auth.json'
        if not auth.is_file():
            raise ValueError('existing ChatGPT login file unavailable')
        link = runtime_home / 'auth.json'
        if not link.exists():
            link.symlink_to(auth)
    env = os.environ.copy()
    # Set the runtime's intended configuration location only in this child.
    # No credential contents are read, copied into evidence, or printed.
    env['CODEX_HOME'] = str(runtime_home)
    return env


def inspect_request(repo: Path, config: dict, prompt: str, runtime_home: Path) -> dict:
    captured = []

    class Capture(http.server.BaseHTTPRequestHandler):
        def do_POST(self):
            captured.append(json.loads(self.rfile.read(int(self.headers['content-length']))))
            self.send_response(400)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(b'{"error":{"message":"offline request inspection complete","type":"invalid_request_error"}}')

        def log_message(self, *_args):
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
    request = captured[0]
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
    expected = {('mcp__evaluation', 'read'), ('functions', 'list_mcp_resources'),
                ('functions', 'list_mcp_resource_templates'), ('functions', 'read_mcp_resource')}
    if set(tools) != expected:
        raise ValueError(f'unexpected evaluation tool set: {tools}')
    if request['input'][-1].get('content') != [{'type': 'input_text', 'text': prompt}]:
        raise ValueError('effective task prompt differs from frozen common prompt plus case')
    if request['model'] != 'gpt-5.6-luna' or request['reasoning']['effort'] != 'high':
        raise ValueError('effective model settings differ from frozen controls')
    # Request IDs are transport metadata. Retain all actual model-visible input.
    visible = {k: request[k] for k in ('model', 'input', 'reasoning', 'text') if k in request}
    return {'request': visible, 'request_sha256': sha(wire(visible).encode()), 'tools': tools,
            'tool_schemas_sha256': sha(wire({'tools': [i for i in request['input'] if i['type'] == 'additional_tools']}).encode()),
            'inspection': 'actual Codex request, local no-auth transport; no model called',
            'resource_helpers': 'Only evaluation server configured; no resources or templates exposed.'}


def execute(args: list[str], env: dict, timeout: float) -> tuple[int, str, str, float, bool]:
    start = time.monotonic()
    proc = subprocess.Popen(args, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            text=True, env=env, start_new_session=True)
    timed_out = False
    try:
        stdout, stderr = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        timed_out = True
        os.killpg(proc.pid, signal.SIGTERM)
        try:
            stdout, stderr = proc.communicate(timeout=3)
        except subprocess.TimeoutExpired:
            os.killpg(proc.pid, signal.SIGKILL)
            stdout, stderr = proc.communicate()
    return proc.returncode, stdout, stderr, time.monotonic() - start, timed_out


def measure(corpus: dict, case: dict, run: dict, events: list[dict], elapsed: float,
            exit_code: int, timed_out: bool, index: dict) -> dict:
    from benchmarks.typescript_context_relationships import score_relationships

    raw_trace = json.loads(Path(run['trace_path']).read_text())
    trace = ReadTrace(corpus, case['id'], run['session_id'], 'A', run['repetition'])
    for event in raw_trace['events']:
        trace.record(**{k: event[k] for k in ('operation', 'reason', 'detail', 'response_json',
                                             'elapsed_ms', 'arguments', 'because')},
                     spans=[{k: s[k] for k in ('file', 'start_byte', 'text')} for s in event['spans']])
        if trace.events[-1] != event:
            raise ValueError('recorded event failed exact replay')
    messages = [e['item']['text'] for e in events if e.get('type') == 'item.completed'
                and e.get('item', {}).get('type') == 'agent_message']
    outcome = 'timeout' if timed_out else 'tool_failure' if exit_code else 'completed'
    answer = {}
    try:
        answer = json.loads(messages[-1])
        if not isinstance(answer, dict):
            raise ValueError('answer must be a JSON object')
    except (ValueError, IndexError):
        if outcome == 'completed':
            outcome = 'malformed_answer'
        answer = {}
    completed = [e for e in events if e.get('type') == 'turn.completed']
    usage = completed[-1].get('usage') if completed else None
    limits = load_controls(corpus)['limits']
    failures = list(raw_trace['failures'])
    if usage and (usage['input_tokens'] > limits['max_reported_input_tokens_per_run']
                  or usage['output_tokens'] > limits['max_reported_output_tokens_per_run']):
        failures.append({'category': 'budget_exhausted', 'limit': 'reported_tokens'})
    if failures and outcome == 'completed':
        outcome = 'budget_exhausted' if all(f['category'] == 'budget_exhausted' for f in failures) else 'tool_failure'
    calls = [e['item'] for e in events if e.get('type') == 'item.completed'
             and e.get('item', {}).get('type') == 'mcp_tool_call']
    delivered = []
    for call in calls:
        result = call.get('result') or {}
        if call.get('server') != 'evaluation' or call.get('tool') != 'read' or not isinstance(result.get('structured_content'), dict):
            failures.append({'category': 'unaccounted_tool_output', 'item': call['id']})
            continue
        delivered.append(result['structured_content'])
    expected_results = [json.loads(e['response_json']) for e in trace.events]
    if delivered != expected_results:
        failures.append({'category': 'delivery_trace_mismatch'})
    if failures and outcome == 'completed':
        outcome = 'tool_failure'
    artifact = trace.artifact(answer, usage=usage,
                             usage_semantics='Codex turn.completed gross input; cached_input is a subset; output includes reasoning_output_tokens.' if usage else None,
                             outcome=outcome)
    artifact['baseline'] = {'end_to_end_seconds': min(elapsed, 180) if timed_out else elapsed,
                     'actual_process_seconds': elapsed, 'exit_code': exit_code,
                     'provider_thread_id': next((e['thread_id'] for e in events if e.get('type') == 'thread.started'), None),
                     'failures': failures, 'tool_delivery_verified': not any(f['category'] in
                      {'unaccounted_tool_output', 'delivery_trace_mismatch', 'invalid_trace'} for f in failures),
                     'relationships': score_relationships(case, index, delivered)}
    return artifact


def run_case(corpus: dict, controls: dict, case: dict, repetition: int, output: Path, catalog: Path) -> dict:
    destination = output / f"{case['id']}-r{repetition}"
    destination.mkdir()
    with tempfile.TemporaryDirectory(prefix='loci-baseline-') as temporary:
        temp = Path(temporary)
        repo, store = temp / 'snapshot', temp / 'store'
        materialize_snapshot(corpus, case['snapshot'], repo)
        start = time.monotonic()
        with _isolated_store(store):
            service.index_repo(repo, incremental=False)
            index = service.get_store().load(repo.resolve())
        index_seconds = time.monotonic() - start
        run = {'repo': str(repo.resolve()), 'corpus_root': corpus['_root'], 'case_id': case['id'],
               'session_id': str(uuid.uuid4()), 'arm': 'A', 'repetition': repetition,
               'trace_path': str(destination / 'adapter-trace.json')}
        run_file = temp / 'run.json'
        save(run_file, run)
        # Retain a valid empty trace even when the adapter never starts.
        empty = ReadTrace(corpus, case['id'], run['session_id'], 'A', repetition)
        save(Path(run['trace_path']), {'identity': empty.identity, 'events': [], 'failures': [], 'attempts': 0})
        config = settings(run_file, catalog, store)
        prompt = controls['agent']['common_prompt'] + case['prompt']
        inspection = inspect_request(repo, config, prompt, temp / 'inspection-runtime')
        save(destination / 'request-audit.json', inspection)
        save(destination / 'provenance.json', {'run': run, 'config': config,
             'config_sha256': sha(wire(config).encode()), 'prompt_sha256': sha(prompt.encode()),
             'index_seconds': index_seconds, 'extractor_version': EXTRACTOR_VERSION,
             'snapshot_files': corpus['snapshots'][case['snapshot']]['files']})
        args = launch_args(repo, config, prompt)
        code, stdout, stderr, elapsed, timed_out = execute(args, child_environment(temp / 'agent-runtime', True),
                                                         controls['limits']['max_end_to_end_seconds_per_run'])
        (destination / 'events.jsonl').write_text(stdout)
        (destination / 'stderr.txt').write_text(stderr)
        events = [json.loads(line) for line in stdout.splitlines() if line.strip()]
        artifact = measure(corpus, case, run, events, elapsed, code, timed_out, index)
        # The snapshot is immutable even if a model tried an unsupported operation.
        actual = {str(p.relative_to(repo)): sha(p.read_bytes()) for p in repo.rglob('*') if p.is_file()}
        if actual != corpus['snapshots'][case['snapshot']]['files']:
            raise ValueError('source snapshot changed during baseline')
        save(destination / 'result.json', artifact)
        return {**artifact['measurement'], **artifact['baseline']}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--case', help='Run the named case only; this is not a complete baseline')
    parser.add_argument('--repetition', type=int, choices=[1, 2, 3])
    parser.add_argument('--resume', action='store_true', help='Continue missing planned runs; completed attempts are never retried')
    args = parser.parse_args()
    corpus = load_corpus()
    controls = load_controls(corpus)
    if args.case and args.case not in {c['id'] for c in corpus['cases']}:
        parser.error('unknown frozen case')
    if args.repetition and not args.case:
        parser.error('--repetition requires --case')
    if command(['git', 'rev-parse', 'HEAD:src'], cwd=ROOT) != controls['baseline_source_tree']:
        raise ValueError('production source differs from repaired baseline')
    if command(['git', 'status', '--porcelain', '--', 'src'], cwd=ROOT):
        raise ValueError('production source has uncommitted changes')
    cli_version = command(['codex', '--version'])
    if cli_version != 'codex-cli ' + controls['agent']['cli_version']:
        raise ValueError('CLI changed; declare a new matched environment before measuring')
    observed_environment = environment(controls)
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=args.resume)
    catalog = output / 'model-catalog.json'
    if not args.resume:
        catalog = prepare_catalog(output, controls['agent']['model'])
        save(output / 'preflight.json', preflight(corpus))
        save(output / 'environment.json', {'cli_version': cli_version, **observed_environment,
             'baseline_source_tree': controls['baseline_source_tree'],
             'baseline_commit': controls['baseline_engine']['commit'],
             'harness_commit': command(['git', 'rev-parse', 'HEAD'], cwd=ROOT),
             'harness_files': {str(p.relative_to(ROOT)): sha(p.read_bytes()) for p in HARNESS_FILES},
             'corpus_sha256': sha((DEFAULT_ROOT / 'corpus.json').read_bytes()),
             'controls_sha256': sha((DEFAULT_ROOT / 'comparison-controls.json').read_bytes()),
             'started_at_utc': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())})
    else:
        previous = json.loads((output / 'environment.json').read_text())
        if any(previous[key] != value for key, value in observed_environment.items()):
            raise ValueError('cannot resume across environment changes')
        current_harness = {str(p.relative_to(ROOT)): sha(p.read_bytes()) for p in HARNESS_FILES}
        if previous['harness_files'] != current_harness:
            raise ValueError('cannot mix changed harness code into a measured batch')
    results = []
    for case in corpus['cases']:
        if args.case and case['id'] != args.case:
            continue
        for repetition in range(1, 4):
            if args.repetition and repetition != args.repetition:
                continue
            path = output / f"{case['id']}-r{repetition}" / 'result.json'
            if path.exists():
                if not args.resume:
                    raise ValueError('existing attempt cannot be overwritten')
                saved = json.loads(path.read_text())
                measured = {**saved['measurement'], **saved['baseline']}
            else:
                print(wire({'starting': case['id'], 'repetition': repetition}), flush=True)
                measured = run_case(corpus, controls, case, repetition, output, catalog)
            results.append(measured)
            print(wire({'completed': case['id'], 'repetition': repetition,
                        'correct': measured['task_correct'], 'outcome': measured['outcome'],
                        'avoidable_reads': measured['avoidable_reads'], 'seconds': round(measured['end_to_end_seconds'], 2)}), flush=True)
    save(output / 'summary.json', {'arm': 'A', 'planned_runs': 51, 'recorded_runs': len(results),
         'complete_batch': len(results) == 51, 'results': results,
         'meaning': 'Current retrieval baseline; no candidate comparison or improvement claim.'})


if __name__ == '__main__':
    main()
