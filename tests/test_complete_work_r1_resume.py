"""Resumption validation is read-only; every native-launch boundary is mocked."""
import copy
import importlib.util
import json
from pathlib import Path
import shutil
import runpy
import sys

import pytest

from benchmarks.complete_work import availability, r0, r1
from benchmarks.complete_work.evaluate import source_snapshot, write_json


@pytest.mark.parametrize('status,exit_code', [('passed', 0), ('failed', 1)])
def test_preflight_cli_exit_code_matches_gate_outcome(monkeypatch, status, exit_code):
    monkeypatch.setattr(r1, 'preflight', lambda *args, **kwargs: {'status': status})
    monkeypatch.setattr(sys, 'argv', ['pilot-execute.py', '--freeze', 'freeze.json',
                                    '--gate', 'gate.json', '--preflight-only'])
    with pytest.raises(SystemExit) as stopped:
        runpy.run_path(str(SCRIPT), run_name='__main__')
    assert stopped.value.code == exit_code


SCRIPT = Path(__file__).resolve().parents[1] / '.scratch/r1-integrated/pilot-execute.py'


@pytest.fixture
def pilot(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location('pilot_resume', SCRIPT)
    runner = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(runner)
    root = tmp_path / 'pilot'
    root.mkdir()
    run_root = tmp_path / 'original-run-root'
    run_root.mkdir()
    fake_home = tmp_path / 'home'
    sessions = fake_home / '.codex/sessions'
    sessions.mkdir(parents=True)
    monkeypatch.setattr(Path, 'home', classmethod(lambda cls: fake_home))
    source = tmp_path / 'source'
    source.mkdir()
    (source / 'source.txt').write_text('frozen source')
    before = source_snapshot(source, tmp_path / 'source-history')
    schedule = [{'run_id': f'task-{n}-{condition}', 'task': f'task-{n}', 'condition': condition}
                for n in range(4) for condition in r1.CONDITIONS]
    frozen = {'freeze_sha256': 'frozen-identity', 'schedule': schedule,
              'host': {'executable': '/never-launch-codex'}, 'model': 'fixed', 'effort': 'high',
              'availability': availability.policy(),
              'conditions': {condition: {'command': '/never-launch-mcp', 'args': [],
                                         'tools': availability.TOOLS_BY_CONDITION[condition],
                                         'env': {'LOCI_R1_STORE': '{store}'}} for condition in r1.CONDITIONS},
              'tasks': [{'id': f'task-{n}', 'source_identity': before['sha256'], 'oracle_sha256': 'oracle'}
                        for n in range(4)]}
    freeze, gate, amendment = (tmp_path / name for name in ['freeze.json', 'gate.json', 'amendment.json'])
    write_json(gate, {'status': 'passed'})
    write_json(amendment, {'status': 'test-amendment'})
    calls = {'prepare': [], 'execute': [], 'evaluate': [], 'replay': []}
    availability_gate = root / 'availability/gate.json'
    availability_gate.parent.mkdir()
    write_json(availability_gate, {'status': 'passed', 'conditions': list(r1.CONDITIONS)})
    deterministic_gate_sha256 = r0.digest(gate)
    def require_availability(frozen, path):
        if path is None or not path.is_file():
            raise ValueError('verified native-host availability gate is required before measured work')
        record = runner.read(path)
        if record.get('status') != 'passed' or record.get('conditions') != list(r1.CONDITIONS):
            raise ValueError('native-host availability gate failed')
        return {'path': str(path.resolve()), 'sha256': r0.digest(path),
                'deterministic_gate_sha256': deterministic_gate_sha256,
                'threads': ['probe-' + condition for condition in r1.CONDITIONS]}
    monkeypatch.setattr(r1, 'require_availability', require_availability)
    verified = require_availability(frozen, availability_gate)
    def read_freeze(path, *, amendment=None):
        assert amendment == tmp_path / 'amendment.json'
        return frozen
    monkeypatch.setattr(r1, 'read_freeze', read_freeze)
    def create_assignment(run_id, destination):
        row = next(row for row in schedule if row['run_id'] == run_id)
        observer, workspace = destination / 'observer', destination / 'workspace'
        observer.mkdir(parents=True)
        shutil.copytree(source, workspace)
        manifest = {'run_id': run_id, 'workspace': str(workspace), 'observer': str(observer),
                    'permission_overrides': {}, 'conditions': {'freeze_sha256': frozen['freeze_sha256']},
                    'r1': {**row, 'availability_gate': copy.deepcopy(verified), 'argv': r1.command(frozen, row['condition'], workspace, observer)}}
        write_json(observer / 'run.json', manifest)
        write_json(observer / 'source-before.json', before)
        return manifest
    def execution(manifest, thread):
        result = {'run_id': manifest['run_id'], 'thread_id': thread, 'status': 'closed', 'exit_code': 0,
                  'freeze_sha256': frozen['freeze_sha256'], 'availability_gate': copy.deepcopy(verified)}
        write_json(Path(manifest['observer']) / 'execution.json', result)
        tools = sorted('mcp__loci__' + name for name in
                       frozen['conditions'][manifest['r1']['condition']]['tools'])
        rows = [{'type': 'session_meta', 'payload': {'id': thread}},
                {'type': 'response_item', 'payload': {'type': 'custom_tool_call', 'name': 'functions.exec',
                 'input': availability.CATALOG_PROGRAM, 'call_id': 'catalog'}},
                {'type': 'response_item', 'payload': {'type': 'custom_tool_call_output', 'call_id': 'catalog',
                 'output': json.dumps({'loci_runtime_catalog_v1': tools})}}]
        (sessions / (thread + '.jsonl')).write_text(''.join(json.dumps(row) + '\n' for row in rows))
        return result
    def grade(config, trace, thread, *, amendment=None, correct=True):
        manifest = runner.read(config)
        observer = Path(manifest['observer'])
        qualification_dir = observer / 'qualification'
        qualification_dir.mkdir()
        shutil.copy2(trace, qualification_dir / 'native-rollout.jsonl')
        after = source_snapshot(Path(manifest['workspace']), observer / 'source-history')
        write_json(qualification_dir / 'source-after.json', after)
        accounting = {'usage_status': 'known', 'usage': {'totalTokens': 100}}
        qualification = {'run_id': manifest['run_id'], 'thread_id': thread, 'status': 'qualified_observations',
                         'config_sha256': r0.digest(config), 'native_trace_sha256': r0.digest(trace),
                         'source_before': before['sha256'], 'source_after': after['sha256'], 'accounting': accounting}
        write_json(qualification_dir / 'result.json', qualification)
        treatment = {'status': 'verified', **availability.audit_catalog(
            trace, frozen['conditions'][manifest['r1']['condition']]['tools'])}
        write_json(observer / 'treatment.json', treatment)
        result = {'run_id': manifest['run_id'], 'thread_id': thread, 'freeze_sha256': frozen['freeze_sha256'],
                  'condition': manifest['r1']['condition'], 'qualification_status': 'qualified_observations',
                  'accounting': accounting, 'source_identity': after['sha256'], 'oracle_sha256': 'oracle',
                  'correct': correct, 'changes': [], 'unexpected_changes': [], 'treatment_validity': treatment}
        (observer / 'evaluation').mkdir()
        write_json(observer / 'evaluation/result.json', result)
        return result
    def replay(config, destination):
        result = runner.read(config.parent / 'evaluation/result.json')
        result = {key: result[key] for key in ['run_id', 'source_identity', 'oracle_sha256', 'correct', 'changes', 'unexpected_changes']}
        destination.mkdir()
        write_json(destination / 'oracle.json', result)
        return result
    def retain(number, *, correct=True, separate=False):
        row = schedule[number]
        manifest = create_assignment(row['run_id'], run_root / row['run_id'])
        config = Path(manifest['observer']) / 'run.json'
        thread = f'original-thread-{number}'
        closed = execution(manifest, thread)
        result = grade(config, sessions / (thread + '.jsonl'), thread, correct=correct)
        replay(config, config.parent / 'replay')
        archive = root / 'archived-runs' / row['run_id']
        archive.parent.mkdir(exist_ok=True)
        shutil.copytree(run_root / row['run_id'], archive)
        evidence = archive / 'observer'
        if separate:
            # The corrected readback lives separately; retain the original
            # archive's unqualified accounting and never overwrite it.
            corrected = root / 'reprocessed' / row['run_id'] / 'observer'
            shutil.copytree(evidence, corrected)
            original_q = runner.read(evidence / 'qualification/result.json')
            original_q.update(status='unqualified', accounting={'usage_status': 'unknown', 'usage': None})
            write_json(evidence / 'qualification/result.json', original_q)
            original_result = runner.read(evidence / 'evaluation/result.json')
            original_result.update(qualification_status='unqualified', accounting=original_q['accounting'])
            write_json(evidence / 'evaluation/result.json', original_result)
            evidence = corrected
        entry = {'run_id': row['run_id'], 'config': str(config), 'execution': closed, 'evaluation': result,
                 'replay_matches': True, 'archive': str(archive)}
        for label, relative in [('evaluation', 'evaluation/result.json'), ('qualification', 'qualification/result.json'), ('replay', 'replay/oracle.json')]:
            path = evidence / relative
            entry[label + '_result'], entry[label + '_result_sha256'] = str(path), r0.digest(path)
        return entry
    def prepare(path, run_id, destination, *, amendment=None, availability_gate=None):
        assert availability_gate == root / 'availability/gate.json'
        calls['prepare'].append(run_id)
        assert amendment == tmp_path / 'amendment.json'
        return create_assignment(run_id, destination)
    def execute(config, gate, *, amendment=None, availability_gate=None):
        manifest = runner.read(config)
        assert availability_gate == root / 'availability/gate.json'
        calls['execute'].append(manifest['run_id'])
        assert amendment == tmp_path / 'amendment.json'
        return execution(manifest, 'new-thread-' + manifest['run_id'])
    def evaluate(config, trace, thread, *, amendment=None):
        calls['evaluate'].append(runner.read(config)['run_id'])
        return grade(config, trace, thread, amendment=amendment)
    def replay_mock(config, destination):
        calls['replay'].append(runner.read(config)['run_id'])
        return replay(config, destination)
    monkeypatch.setattr(r1, 'prepare', prepare)
    monkeypatch.setattr(r1, 'execute', execute)
    monkeypatch.setattr(r1, 'evaluate', evaluate)
    monkeypatch.setattr(r1, 'replay', replay_mock)
    def save(entries):
        index = {'freeze_sha256': frozen['freeze_sha256'], 'availability_gate': copy.deepcopy(verified), 'run_root': str(run_root), 'runs': entries, 'status': 'blocked'}
        write_json(root / 'execution-index.json', index)
        return index
    def run(**kwargs):
        return runner.run(freeze, gate, amendment, root, **kwargs)
    return {'root': root, 'run_root': run_root, 'retain': retain, 'save': save, 'run': run,
            'calls': calls, 'runner': runner, 'frozen': frozen, 'freeze': freeze,
            'gate': gate, 'amendment': amendment, 'availability_gate': availability_gate}


def test_resume_full_schedule_skips_original_thread_and_keeps_original_archive(pilot):
    first = pilot['retain'](0, separate=True)
    pilot['save']([first])
    original = Path(first['archive']) / 'observer/qualification/result.json'
    before = original.read_bytes()
    result = pilot['run'](resume=True)
    assert result['status'] == 'complete' and result['attempted'] == 16
    assert len(pilot['calls']['execute']) == 15
    assert first['run_id'] not in pilot['calls']['prepare'] + pilot['calls']['execute']
    assert original.read_bytes() == before
    assert pilot['runner'].read(pilot['root'] / 'execution-index.json')['runs'][0] == first
    assert pilot['run'](resume=True, check_only=True)['pending'] == 0


def test_check_only_is_read_only_and_does_not_prepare_or_launch(pilot):
    first = pilot['retain'](0, separate=True)
    pilot['save']([first])
    before = {str(path): path.read_bytes() for path in pilot['root'].rglob('*') if path.is_file()}
    result = pilot['run'](resume=True, check_only=True)
    assert result == {'status': 'checked', 'next_run_id': 'task-0-path-only', 'pending': 15, 'retained': 1}
    assert all(not values for values in pilot['calls'].values())
    assert {str(path): path.read_bytes() for path in pilot['root'].rglob('*') if path.is_file()} == before


@pytest.mark.parametrize('violation', ['order', 'unqualified', 'unknown_usage', 'failed_attempt', 'changed_result', 'pending_attempt', 'wrong_store'])
def test_invalid_prefix_is_rejected_before_launch(pilot, violation):
    first = pilot['retain'](0)
    if violation == 'order':
        first['run_id'] = 'wrong-slot'
    elif violation == 'unqualified':
        first['evaluation']['qualification_status'] = 'unqualified'
    elif violation == 'unknown_usage':
        first['evaluation']['accounting']['usage_status'] = 'unknown'
    elif violation == 'failed_attempt':
        first['execution']['status'] = 'failed'
    elif violation == 'changed_result':
        Path(first['evaluation_result']).write_text('{}')
    elif violation == 'pending_attempt':
        (pilot['run_root'] / 'task-0-path-only').mkdir()
    else:
        path = Path(first['archive']) / 'observer/run.json'
        manifest = pilot['runner'].read(path)
        manifest['r1']['argv'].append('LOCI_R1_STORE=shared')
        write_json(path, manifest)
    pilot['save']([first])
    with pytest.raises(ValueError):
        pilot['run'](resume=True, check_only=True)
    assert all(not values for values in pilot['calls'].values())


def test_wrong_answer_is_a_completed_valid_prefix(pilot):
    first = pilot['retain'](0, correct=False)
    pilot['save']([first])
    assert pilot['run'](resume=True, check_only=True)['pending'] == 15


def test_nonresume_refuses_existing_state_before_overwrite(pilot):
    first = pilot['retain'](0)
    pilot['save']([first])
    path = pilot['root'] / 'execution-index.json'
    before = path.read_bytes()
    with pytest.raises(ValueError, match='requires --resume'):
        pilot['run']()
    assert path.read_bytes() == before and all(not values for values in pilot['calls'].values())


def test_duplicate_sessions_rejected(pilot):
    entries = [pilot['retain'](0), pilot['retain'](1)]
    entries[1]['execution']['thread_id'] = entries[0]['execution']['thread_id']
    pilot['save'](entries)
    with pytest.raises(ValueError, match='duplicate retained session'):
        pilot['run'](resume=True, check_only=True)
    assert all(not values for values in pilot['calls'].values())


def test_evaluation_exception_archives_failed_attempt_and_stops(pilot, monkeypatch):
    first = pilot['retain'](0)
    pilot['save']([first])
    def broken(*args, **kwargs):
        raise RuntimeError('incomplete telemetry')
    monkeypatch.setattr(r1, 'evaluate', broken)
    result = pilot['run'](resume=True)
    assert result['status'] == 'blocked' and len(pilot['calls']['execute']) == 1
    index = pilot['runner'].read(pilot['root'] / 'execution-index.json')
    assert 'incomplete telemetry' in index['runs'][-1]['evidence_error']
    assert (Path(index['runs'][-1]['archive']) / 'observer/execution.json').is_file()
    with pytest.raises(ValueError):
        pilot['run'](resume=True, check_only=True)


@pytest.mark.parametrize('state', ['missing', 'failed', 'incomplete'])
def test_availability_gate_blocks_before_prepare_or_output_mutation(pilot, state):
    path = pilot['availability_gate']
    if state == 'missing':
        path.unlink()
    else:
        write_json(path, {'status': 'failed' if state == 'failed' else 'passed',
                          'conditions': list(r1.CONDITIONS) if state == 'failed' else ['native']})
    before = {str(p): p.read_bytes() for p in pilot['root'].rglob('*') if p.is_file()}
    with pytest.raises(ValueError, match='availability gate'):
        pilot['run']()
    assert all(not values for values in pilot['calls'].values())
    assert {str(p): p.read_bytes() for p in pilot['root'].rglob('*') if p.is_file()} == before


@pytest.mark.parametrize(('violation', 'error'), [
    ('unverified', 'tool catalog is unverified'),
    ('catalog', 'first tool action'),
    ('manifest_gate', 'retained availability gate differs'),
    ('execution_gate', 'retained availability gate differs'),
    ('probe_thread', 'duplicate retained session'),
])
def test_resume_rechecks_catalog_and_availability_bindings(pilot, violation, error):
    first = pilot['retain'](0)
    observer = Path(first['archive']) / 'observer'
    if violation == 'unverified':
        first['evaluation'].pop('treatment_validity')
        write_json(Path(first['evaluation_result']), first['evaluation'])
        first['evaluation_result_sha256'] = r0.digest(Path(first['evaluation_result']))
    elif violation == 'catalog':
        trace = observer / 'qualification/native-rollout.jsonl'
        rows = [json.loads(line) for line in trace.read_text().splitlines()]
        rows[1]['payload']['input'] = 'text({loci_runtime_catalog_v1: []});'
        trace.write_text(''.join(json.dumps(row) + '\n' for row in rows))
        qualified_path = Path(first['qualification_result'])
        qualified = pilot['runner'].read(qualified_path)
        qualified['native_trace_sha256'] = r0.digest(trace)
        write_json(qualified_path, qualified)
        first['qualification_result_sha256'] = r0.digest(qualified_path)
    elif violation == 'manifest_gate':
        for config in [Path(first['config']), observer / 'run.json']:
            manifest = pilot['runner'].read(config)
            manifest['r1']['availability_gate']['sha256'] = 'different'
            write_json(config, manifest)
    elif violation == 'execution_gate':
        first['execution']['availability_gate']['sha256'] = 'different'
        write_json(observer / 'execution.json', first['execution'])
    else:
        first['execution']['thread_id'] = 'probe-native'
    pilot['save']([first])
    with pytest.raises(ValueError, match=error):
        pilot['run'](resume=True, check_only=True)
    assert all(not values for values in pilot['calls'].values())


def test_treatment_failure_archives_attempt_without_replay_or_grade(pilot, monkeypatch):
    original_execute = r1.execute
    def wrong_catalog(config, gate, **kwargs):
        result = original_execute(config, gate, **kwargs)
        trace = Path.home() / '.codex/sessions' / (result['thread_id'] + '.jsonl')
        rows = [json.loads(line) for line in trace.read_text().splitlines()]
        rows[1]['payload']['input'] = 'text({loci_runtime_catalog_v1: []});'
        trace.write_text(''.join(json.dumps(row) + '\n' for row in rows))
        return result
    monkeypatch.setattr(r1, 'execute', wrong_catalog)
    result = pilot['run']()
    assert result['status'] == 'blocked' and result['attempted'] == 1
    assert len(pilot['calls']['execute']) == 1 and pilot['calls']['replay'] == []
    index = pilot['runner'].read(pilot['root'] / 'execution-index.json')
    failed = index['runs'][0]
    assert 'first tool action' in failed['evidence_error'] and 'evaluation' not in failed
    assert (Path(failed['archive']) / 'observer/qualification/native-rollout.jsonl').is_file()
    assert not (Path(failed['archive']) / 'observer/evaluation/result.json').exists()
    with pytest.raises(ValueError):
        pilot['run'](resume=True)
    assert len(pilot['calls']['execute']) == 1


def test_cli_check_only_never_preflights_or_launches(pilot, monkeypatch):
    pilot['availability_gate'].unlink()
    def forbidden(*args, **kwargs):
        pytest.fail('check-only must not launch availability probes')
    monkeypatch.setattr(r1, 'preflight', forbidden)
    before = {str(p): p.read_bytes() for p in pilot['root'].rglob('*') if p.is_file()}
    with pytest.raises(ValueError, match='availability gate'):
        pilot['runner'].main(['--freeze', str(pilot['freeze']), '--gate', str(pilot['gate']),
                              '--amendment', str(pilot['amendment']), '--output-root', str(pilot['root']),
                              '--check-only'])
    assert all(not values for values in pilot['calls'].values())
    assert {str(p): p.read_bytes() for p in pilot['root'].rglob('*') if p.is_file()} == before


def test_cli_failed_preflight_stops_before_measured_work(pilot, monkeypatch):
    calls = []
    def failed(freeze, gate, destination, *, amendment=None):
        calls.append((freeze, gate, destination, amendment))
        return {'status': 'failed', 'error': 'native catalog absent'}
    monkeypatch.setattr(r1, 'preflight', failed)
    result = pilot['runner'].main(['--freeze', str(pilot['freeze']), '--gate', str(pilot['gate']),
                                   '--amendment', str(pilot['amendment']), '--output-root', str(pilot['root'])])
    assert result['status'] == 'failed'
    assert calls == [(pilot['freeze'], pilot['gate'], pilot['root'] / 'availability', pilot['amendment'])]
    assert all(not values for values in pilot['calls'].values())
    assert not (pilot['root'] / 'execution-index.json').exists()


def test_cli_preflight_only_defaults_to_freeze_parent_and_does_not_run(pilot, monkeypatch):
    calls = []
    def passed(freeze, gate, destination, *, amendment=None):
        calls.append((freeze, gate, destination, amendment))
        return {'status': 'passed'}
    monkeypatch.setattr(r1, 'preflight', passed)
    result = pilot['runner'].main(['--freeze', str(pilot['freeze']), '--gate', str(pilot['gate']), '--preflight-only'])
    assert result == {'status': 'passed'}
    assert calls == [(pilot['freeze'], pilot['gate'], pilot['freeze'].parent / 'availability', None)]
    assert all(not values for values in pilot['calls'].values())


def test_another_passed_deterministic_gate_blocks_before_prepare_or_mutation(pilot):
    write_json(pilot['gate'], {'status': 'passed', 'another_gate': True})
    before = {str(p): p.read_bytes() for p in pilot['root'].rglob('*') if p.is_file()}
    with pytest.raises(ValueError, match='another deterministic gate'):
        pilot['run']()
    assert all(not values for values in pilot['calls'].values())
    assert {str(p): p.read_bytes() for p in pilot['root'].rglob('*') if p.is_file()} == before
