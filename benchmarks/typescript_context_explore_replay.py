"""Recompute all exploration trial measurements from retained host events.

Fresh indexes use the shared frozen engine. No provider call is made, and no
recorded attempt or score is overwritten.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import tempfile

from benchmarks.typescript_context_adapter import wire
from benchmarks.typescript_context_explore import (
    COMPARISON, COMPARISON_ROOT, CORPUS_ROOT, save, sha, validate_freeze,
)
from benchmarks.typescript_context_corpus import _isolated_store, load_corpus, materialize_snapshot
from benchmarks.typescript_context_explore_transport import HELPERS, tool_names


def verify_request(audit, provenance, prompt, arm, schema_hash):
    request = audit['request']
    visible_tools = [(namespace['name'], tool['name']) for item in request['input']
                     if item['type'] == 'additional_tools' for namespace in item['tools']
                     for tool in namespace['tools']]
    expected = {('mcp__evaluation', name) for name in tool_names(arm)} | HELPERS
    if len(visible_tools) != len(expected) or set(visible_tools) != expected:
        raise ValueError('request exposed a different tool set')
    if request['model'] != 'gpt-5.6-luna' or request['reasoning']['effort'] != 'high':
        raise ValueError('request model or reasoning effort changed')
    if request['input'][-1].get('content') != [{'type': 'input_text', 'text': prompt}]:
        raise ValueError('retained request prompt differs from the frozen task')
    for item in request['input']:
        for part in item.get('content', []):
            if any(marker in part.get('text', '') for marker in ('# AGENTS.md instructions',
                    '## Brain Context', 'Anvil Continuity Frame', '<skills_instructions>', 'LOCI_ADAPTER_READY')):
                raise ValueError('ambient context appears in retained request')
    actual = sha(wire({'tools': [item['tools'] for item in request['input']
                                 if item['type'] == 'additional_tools']}).encode())
    if not (actual == schema_hash == audit['canonical_tool_schemas_sha256']
            == provenance['canonical_tool_schemas_sha256']):
        raise ValueError('retained request schemas differ from frozen transport proof')
    if sha(wire(request).encode()) != audit['request_sha256']:
        raise ValueError('retained request digest mismatch')
    if (sha(prompt.encode()) != provenance['prompt_sha256']
            or sha(wire(provenance['config']).encode()) != provenance['config_sha256']):
        raise ValueError('provenance prompt/config digest mismatch')


def replay_attempt(folder, corpus, case, plan, freeze, index):
    from benchmarks.typescript_context_explore_observed import measure

    result = json.loads((folder / 'result.json').read_text())
    run = json.loads((folder / 'run.json').read_text())
    provenance = json.loads((folder / 'provenance.json').read_text())
    raw = json.loads((folder / 'adapter-trace.json').read_text())
    if raw != json.loads((folder / 'adapter-trace-copy.json').read_text()):
        raise ValueError('retained trace copies differ')
    identity = result['identity']
    if (identity['task_id'], identity['repetition'], identity['arm']) != (
            case['id'], plan['repetition'], plan['arm']):
        raise ValueError('result differs from planned identity')
    if (raw['identity'] != identity or run['session_id'] != identity['session_id']
            or result['attempt_id'] != plan['attempt_id'] or run['attempt_id'] != plan['attempt_id']
            or result['provenance'] != provenance):
        raise ValueError('trace, run, result and provenance identities disagree')
    expected_engine = {key: freeze['engine'][key] for key in ('commit', 'source_tree', 'extractor_version')}
    if (provenance['source']['engine'] != expected_engine
            or provenance['source']['freeze_json_sha256'] != freeze['freeze_json_sha256']
            or provenance['snapshot_files'] != corpus['snapshots'][case['snapshot']]['files']):
        raise ValueError('attempt uses a different engine, freeze or snapshot')
    from benchmarks.typescript_context_corpus import load_controls
    prompt = load_controls(corpus)['agent']['common_prompt'] + case['prompt']
    if (folder / 'request-audit.json').exists():
        verify_request(json.loads((folder / 'request-audit.json').read_text()), provenance,
                       prompt, plan['arm'], freeze['canonical_tool_schemas_sha256'][plan['arm']])
    elif not result.get('runner_failures'):
        raise ValueError('successful attempt has no audited request')
    events = [json.loads(line) for line in (folder / 'events.jsonl').read_text().splitlines() if line.strip()]
    if events != json.loads((folder / 'events.json').read_text()):
        raise ValueError('raw host events differ from retained parsed events')
    run = {**run, 'trace_path': str(folder / 'adapter-trace.json')}
    baseline = result['baseline']
    if 'relationships' not in baseline:
        raise ValueError('relationship score is unavailable; full replay cannot be certified')
    recomputed = measure(corpus, case, run, events, baseline['actual_process_seconds'],
                         baseline['exit_code'], result['measurement']['outcome'] == 'timeout',
                         index)
    failures = result.get('runner_failures', [])
    if failures:
        recomputed['measurement']['measurement_complete'] = False
        recomputed['measurement']['task_correct'] = False
        recomputed['baseline']['tool_delivery_verified'] = False
        for failure in failures:
            if failure not in recomputed['baseline']['failures']:
                recomputed['baseline']['failures'].append(failure)
    for name in ('identity', 'events', 'measurement'):
        if result[name] != recomputed[name]:
            raise ValueError('independent replay differs in ' + name)
    for name, value in recomputed['baseline'].items():
        if baseline.get(name) != value:
            raise ValueError('independent replay differs in baseline.' + name)
    return {'attempt_id': plan['attempt_id'], 'verified': True,
            'measurement_complete': recomputed['measurement'].get('measurement_complete'),
            'task_correct': recomputed['measurement']['task_correct']}


def verify(output):
    from loci import service

    output = Path(output).resolve()
    corpus = load_corpus(CORPUS_ROOT)
    freeze = validate_freeze(COMPARISON_ROOT / 'freeze.json')
    manifest = json.loads((output / 'manifest.json').read_text())
    if (manifest['comparison'] != COMPARISON or manifest['plan'] != freeze['plan']
            or manifest['freeze'] != freeze or manifest['planned_runs'] != 102):
        raise ValueError('batch manifest differs from the frozen trial')
    expected = {plan['attempt_id'] for plan in freeze['plan']}
    if {path.parent.name for path in output.glob('*/result.json')} != expected:
        raise ValueError('replay requires every one of the exact 102 attempts')
    if sha((output / 'model-catalog.json').read_bytes()) != manifest['catalog_sha256']:
        raise ValueError('retained model catalog changed')
    cases = {case['id']: case for case in corpus['cases']}
    rows, failures = [], []
    with tempfile.TemporaryDirectory(prefix='loci-explore-replay-') as temporary:
        temp = Path(temporary)
        indexes = {}
        for snapshot in corpus['snapshots']:
            repo, store = temp / snapshot, temp / ('store-' + snapshot)
            materialize_snapshot(corpus, snapshot, repo)
            with _isolated_store(store):
                service.index_repo(repo, incremental=False)
                indexes[snapshot] = service.get_store().load(repo.resolve())
        for plan in freeze['plan']:
            try:
                row = replay_attempt(output / plan['attempt_id'], corpus, cases[plan['case_id']],
                                     plan, freeze, indexes[plan['snapshot']])
                rows.append(row)
            except (KeyError, TypeError, ValueError, OSError) as exc:
                failures.append({'attempt_id': plan['attempt_id'], 'error': str(exc)})
    inventory = {str(path.relative_to(output)): sha(path.read_bytes()) for path in output.rglob('*')
                 if path.is_file() and path.name not in {'replay-verification.json', 'replay-verification.md'}}
    report = {'schema_version': 1, 'comparison': COMPARISON, 'expected_runs': 102,
        'verified_runs': len(rows), 'complete': len(rows) == 102 and not failures,
        'meaning': 'Fresh frozen-engine indexes; raw host events, exact delivered source, relationship proofs and every measured score recomputed without provider calls.',
        'failures': failures, 'attempts': rows, 'artifact_sha256': inventory}
    save(output / 'replay-verification.json', report)
    if not report['complete']:
        raise ValueError('replay failed: ' + json.dumps(failures[:3]))
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    report = verify(args.output)
    print(json.dumps({'verified_runs': report['verified_runs'], 'complete': report['complete']}))


if __name__ == '__main__':
    main()
