"""Run the frozen v3 observed-call baseline through isolated local Codex."""
from __future__ import annotations

import argparse
import http.server
import json
import subprocess
import tempfile
import threading
import time
import uuid
from pathlib import Path

from benchmarks.typescript_context_baseline import (
    ROOT, HARNESS_FILES as LEGACY_HARNESS_FILES, child_environment, command,
    environment, execute, launch_args, prepare_catalog, save, settings as legacy_settings, sha,
)
from benchmarks.typescript_context_adapter import wire
from benchmarks.typescript_context_corpus import (
    _isolated_store, load_controls, load_corpus, materialize_snapshot, preflight,
)
from benchmarks.typescript_context_observed import ObservedTrace, measure
from benchmarks.typescript_context_tools_v3 import TOOL_NAMES
from loci import service
from loci.storage.index_store import EXTRACTOR_VERSION

HARNESS_FILES = LEGACY_HARNESS_FILES + [ROOT / 'benchmarks' / f'typescript_context_{name}.py'
    for name in ('observed', 'tools_v3', 'baseline_v3', 'transport_v3', 'report_v3')]


def settings(run_file: Path, catalog: Path, store: Path) -> dict:
    config = legacy_settings(run_file, catalog, store)
    config['mcp_servers.evaluation.args'] = ['-m', 'benchmarks.typescript_context_tools_v3', str(run_file)]
    return config


def verify_freeze(corpus_root: Path):
    freeze = json.loads((corpus_root / 'freeze.json').read_text())
    current = {str(path.relative_to(ROOT)): sha(path.read_bytes()) for path in HARNESS_FILES}
    if freeze['harness_files'] != current:
        raise ValueError('measurement harness differs from frozen v3 contract')
    for name, fingerprint in freeze['corpus_files'].items():
        if sha((corpus_root / name).read_bytes()) != fingerprint:
            raise ValueError('corpus contract differs from frozen v3 contract: ' + name)
    paths = list(current) + [str(corpus_root.relative_to(ROOT))]
    if command(['git', 'status', '--porcelain', '--', *paths], cwd=ROOT):
        raise ValueError('measurement harness or corpus has uncommitted changes')


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
    expected = {('mcp__evaluation', name) for name in TOOL_NAMES} | {
        ('functions', 'list_mcp_resources'), ('functions', 'list_mcp_resource_templates'),
        ('functions', 'read_mcp_resource')}
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
            'canonical_tool_schemas_sha256': sha(wire({'tools': [i['tools'] for i in request['input'] if i['type'] == 'additional_tools']}).encode()),
            'inspection': 'actual Codex request, local no-auth transport; no model called',
            'resource_helpers': 'Only evaluation server configured; no resources or templates exposed.'}


def run_case(corpus: dict, controls: dict, case: dict, repetition: int, output: Path, catalog: Path) -> dict:
    destination = output / f"{case['id']}-r{repetition}"
    destination.mkdir()
    with tempfile.TemporaryDirectory(prefix='loci-v3-baseline-') as temporary:
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
        empty = ObservedTrace(corpus, case['id'], run['session_id'], 'A', repetition)
        initial_trace = {'schema_version': 3, 'identity': empty.identity, 'events': [],
                         'failures': [], 'attempts': 0, 'deliveries': []}
        save(Path(run['trace_path']), initial_trace)
        config = settings(run_file, catalog, store)
        prompt = controls['agent']['common_prompt'] + case['prompt']
        inspection = inspect_request(repo, config, prompt, temp / 'inspection-runtime')
        save(destination / 'request-audit.json', inspection)
        verified_transport = json.loads((output / 'transport-verification.json').read_text())
        if inspection['canonical_tool_schemas_sha256'] != verified_transport['canonical_tool_schemas_sha256']:
            raise ValueError('tool schemas differ from the verified batch transport')
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
    parser.add_argument('--corpus-root', type=Path, default=ROOT / "benchmarks/corpora/typescript-context-v3",
                        help='Explicit frozen protocol directory; requires v3')
    args = parser.parse_args()
    corpus = load_corpus(args.corpus_root)
    if corpus['version'] != 'typescript-context-v3':
        raise ValueError('v3 corpus required')
    corpus_root = Path(corpus['_root'])
    verify_freeze(corpus_root)
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
        from benchmarks.typescript_context_transport_v3 import verify_transport
        verify_transport(corpus, catalog, output / 'transport-verification.json')
        save(output / 'environment.json', {'cli_version': cli_version, **observed_environment,
             'baseline_source_tree': controls['baseline_source_tree'],
             'baseline_commit': controls['baseline_engine']['commit'],
             'harness_commit': command(['git', 'rev-parse', 'HEAD'], cwd=ROOT),
             'harness_files': {str(p.relative_to(ROOT)): sha(p.read_bytes()) for p in HARNESS_FILES},
             'corpus_root': str(corpus_root),
             'corpus_sha256': sha((corpus_root / 'corpus.json').read_bytes()),
             'controls_sha256': sha((corpus_root / 'comparison-controls.json').read_bytes()),
             'started_at_utc': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())})
    else:
        previous = json.loads((output / 'environment.json').read_text())
        if any(previous[key] != value for key, value in observed_environment.items()):
            raise ValueError('cannot resume across environment changes')
        current_harness = {str(p.relative_to(ROOT)): sha(p.read_bytes()) for p in HARNESS_FILES}
        if previous['harness_files'] != current_harness:
            raise ValueError('cannot mix changed harness code into a measured batch')
        if (previous['corpus_sha256'] != sha((corpus_root / 'corpus.json').read_bytes())
                or previous['controls_sha256'] != sha((corpus_root / 'comparison-controls.json').read_bytes())):
            raise ValueError('cannot mix protocols into a measured batch')
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
                        'tool_calls': measured['read_count'],
                        'accounting_complete': measured['measurement_complete'], 'seconds': round(measured['end_to_end_seconds'], 2)}), flush=True)
    save(output / 'summary.json', {'arm': 'A', 'planned_runs': 51, 'recorded_runs': len(results),
         'complete_batch': len(results) == 51, 'results': results,
         'meaning': 'Current retrieval baseline; no candidate comparison or improvement claim.'})


if __name__ == '__main__':
    main()
