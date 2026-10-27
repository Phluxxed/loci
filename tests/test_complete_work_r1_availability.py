"""Shared-entrypoint availability gates; native launches are always blocked or mocked."""
from copy import deepcopy
import json
from pathlib import Path
import shutil
import subprocess

import pytest

from benchmarks.complete_work import accounting, availability, r0, r1
from benchmarks.complete_work.evaluate import write_json
from loci.integrated import IntegratedSource
from tests.test_complete_work_r1 import _freeze
from tests.test_complete_work_availability import _trace, _write


def test_prepare_cannot_expose_task_before_native_availability(tmp_path):
    path = _freeze(tmp_path)
    destination = tmp_path / 'must-not-exist'
    with pytest.raises(ValueError, match='availability gate'):
        r1.prepare(path, 'task-0-native', destination)
    assert not destination.exists()


def test_legacy_freeze_cannot_measure_with_a_fake_passed_gate(tmp_path, monkeypatch):
    path = _freeze(tmp_path)
    frozen = json.loads(path.read_text())
    frozen.pop('availability')
    frozen.pop('freeze_sha256')
    frozen['freeze_sha256'] = r1.identity(frozen)
    write_json(path, frozen)
    gate = tmp_path / 'gate.json'
    write_json(gate, {'status': 'passed'})
    monkeypatch.setattr(subprocess, 'run', lambda *a, **k: pytest.fail('native launch forbidden'))
    with pytest.raises(ValueError, match='protocol is missing'):
        r1.prepare(path, 'task-0-native', tmp_path / 'run', availability_gate=gate)


def test_unpinned_availability_validator_cannot_authorize_preparation(tmp_path):
    path = _freeze(tmp_path)
    frozen = json.loads(path.read_text())
    frozen['host']['orchestration_files'].pop(str(Path(availability.__file__).resolve()))
    frozen.pop('freeze_sha256'); frozen['freeze_sha256'] = r1.identity(frozen)
    write_json(path, frozen)
    with pytest.raises(ValueError, match='implementation is not pinned'):
        r1.prepare(path, 'task-0-native', tmp_path / 'run')
    assert not (tmp_path / 'run').exists()


@pytest.fixture
def host_gate(tmp_path, monkeypatch):
    path = _freeze(tmp_path)
    frozen = r1.read_freeze(path)
    source = tmp_path / 'probe-source'
    source.mkdir()
    for name, content in availability.PROBE_FILES.items():
        (source / name).write_text(content)
    directory = tmp_path / 'retained-probes'
    directory.mkdir()
    gate = {'kind': 'r1-native-host-availability', 'status': 'passed',
            'freeze_sha256': frozen['freeze_sha256'], 'deterministic_gate_sha256': 'd' * 64, 'probes': []}
    captured = {}
    originals = []
    for condition in r1.CONDITIONS:
        folder = tmp_path / ('live-' + condition)
        manifest = r0.prepare(source, folder, run_id='availability-' + condition,
                              arm='native' if condition == 'native' else 'loci',
                              native_config=Path(frozen['native_config']),
                              conditions={'model': frozen['model'], 'effort': frozen['effort'],
                                          'native_protection': frozen['native_protection'],
                                          'freeze_sha256': frozen['freeze_sha256']})
        observer, workspace = Path(manifest['observer']), Path(manifest['workspace'])
        manifest['r1'] = {'phase': 'availability', 'condition': condition,
                          'freeze': str(path.resolve()), 'argv': r1.command(frozen, condition, workspace, observer)}
        write_json(observer / 'run.json', manifest)
        (observer / 'prompt.txt').write_text(availability.probe_prompt(condition, workspace, frozen['conditions'][condition]['tools']))
        packets = []
        if condition != 'native':
            service = IntegratedSource(tmp_path / ('packet-store-' + condition))
            retrieved = service.retrieve(workspace, 'entry.ts')
            ref = retrieved['items'][0]['source_ref']
            packets += [('loci_retrieve', {'query': 'entry.ts'}, retrieved),
                        ('loci_read', {'source_ref': ref}, service.read(workspace, ref))]
            if condition == 'integrated':
                semantic = service.semantic_context(workspace, 'entry', anchor_file='entry.ts')
                node = semantic['anchors'][0]['node_id']
                packets += [('loci_semantic', {'query': 'entry', 'anchor_file': 'entry.ts'}, semantic),
                            ('loci_proof', {'node_id': node}, service.proof_context(workspace, node))]
        probe_data = _trace(observer, (workspace, packets), condition)
        _, rows, account, _, _ = probe_data
        account.update(usage_status='known', native_errors=[], turn_contexts=[{
            **frozen['native_protection'], 'cwd': str(workspace), 'model': frozen['model'], 'effort': frozen['effort']}])
        account['stages'][0]['items'].insert(0, {'type': 'UserMessage', 'content': [{
            'type': 'text', 'text': (observer / 'prompt.txt').read_text()}]})
        qualified = observer / 'qualification'
        qualified.mkdir()
        trace = qualified / 'native-rollout.jsonl'
        _write(trace, rows)
        thread = 'probe-' + condition
        write_json(observer / 'execution.json', {'thread_id': thread, 'status': 'closed', 'exit_code': 0,
                   'measured': False, 'freeze_sha256': frozen['freeze_sha256'], 'gate_sha256': 'd' * 64})
        write_json(qualified / 'result.json', {'status': 'qualified_observations', 'thread_id': thread,
                   'config_sha256': r0.digest(observer / 'run.json'), 'native_trace_sha256': r0.digest(trace),
                   'source_before': manifest['source_identity'], 'source_after': manifest['source_identity'],
                   'native_config_sha256': frozen['native_config_sha256'], 'conditions': manifest['conditions'],
                   'accounting': account})
        evidence = availability.audit_probe(trace, account, condition, workspace, frozen['conditions'][condition]['tools'])
        write_json(observer / 'availability.json', evidence)
        archive = directory / condition
        shutil.copytree(folder, archive)
        files = {'config': 'run.json', 'prompt': 'prompt.txt', 'execution': 'execution.json',
                 'qualification': 'qualification/result.json', 'trace': 'qualification/native-rollout.jsonl', 'evidence': 'availability.json'}
        gate['probes'].append({'condition': condition, 'files': {
            label: {'path': str(archive / 'observer' / name), 'sha256': r0.digest(archive / 'observer' / name)}
            for label, name in files.items()}})
        captured[str((archive / 'observer/qualification/native-rollout.jsonl').resolve())] = account
        originals.append(folder)
    gate_path = directory / 'gate.json'
    write_json(gate_path, gate)
    monkeypatch.setattr(accounting, 'summarize_native', lambda trace, thread: deepcopy(captured[str(trace.resolve())]))
    monkeypatch.setattr(subprocess, 'run', lambda *a, **k: pytest.fail('native launch forbidden'))
    return path, frozen, gate_path, gate, originals


def test_gate_reaudits_all_operations_and_retained_fixture_after_live_removal(host_gate):
    path, frozen, gate_path, _, originals = host_gate
    for folder in originals:
        shutil.rmtree(folder)
    verified = r1.require_availability(frozen, gate_path)
    assert len(verified['threads']) == 4
    destination = gate_path.parent / 'measured'
    manifest = r1.prepare(path, 'task-0-integrated', destination, availability_gate=gate_path)
    assert manifest['r1']['availability_gate'] == verified
    prompt = (destination / 'observer/prompt.txt').read_text()
    assert prompt.endswith(frozen['tasks'][0]['prompt'])
    assert availability.CATALOG_PROGRAM in prompt
    assert 'mcp_servers.loci.required=true' in manifest['r1']['argv']


@pytest.mark.parametrize('mutation', ['failed', 'wrong_freeze', 'missing_condition', 'changed_trace', 'changed_fixture', 'wrong_verdict', 'wrong_prompt'])
def test_gate_rejects_stale_or_false_pass_before_measured_preparation(host_gate, tmp_path, mutation):
    path, _, gate_path, gate, _ = host_gate
    if mutation == 'failed':
        gate['status'] = 'failed'
    elif mutation == 'wrong_freeze':
        gate['freeze_sha256'] = '0' * 64
    elif mutation == 'missing_condition':
        gate['probes'].pop()
    else:
        entry = gate['probes'][2]
        label = {'changed_trace': 'trace', 'wrong_verdict': 'evidence', 'wrong_prompt': 'prompt'}.get(mutation)
        if label:
            file = Path(entry['files'][label]['path'])
            if mutation == 'wrong_verdict':
                value = json.loads(file.read_text()); value['tools'] = []; write_json(file, value)
                entry['files'][label]['sha256'] = r0.digest(file)
            elif mutation == 'wrong_prompt':
                file.write_text('model says tools work')
                entry['files'][label]['sha256'] = r0.digest(file)
            else:
                file.write_text('changed')
        else:
            (Path(entry['files']['config']['path']).parent.parent / 'workspace/entry.ts').write_text('changed')
    write_json(gate_path, gate)
    destination = tmp_path / 'must-not-start'
    with pytest.raises((ValueError, KeyError)):
        r1.prepare(path, 'task-0-native', destination, availability_gate=gate_path)
    assert not destination.exists()


def test_execute_revalidates_gate_before_login_or_model(host_gate, tmp_path):
    path, _, gate_path, gate, _ = host_gate
    manifest = r1.prepare(path, 'task-0-native', tmp_path / 'measured', availability_gate=gate_path)
    gate['status'] = 'failed'; write_json(gate_path, gate)
    deterministic = tmp_path / 'deterministic.json'; write_json(deterministic, {'status': 'passed'})
    with pytest.raises(ValueError, match='availability gate failed'):
        r1.execute(Path(manifest['observer']) / 'run.json', deterministic, availability_gate=gate_path)


def test_another_passed_deterministic_gate_cannot_authorize_launch_or_probe_reuse(host_gate, tmp_path):
    path, _, gate_path, _, _ = host_gate
    manifest = r1.prepare(path, 'task-0-native', tmp_path / 'measured', availability_gate=gate_path)
    other = tmp_path / 'other-gate.json'; write_json(other, {'status': 'passed'})
    with pytest.raises(ValueError, match='deterministic gate differs'):
        r1.execute(Path(manifest['observer']) / 'run.json', other, availability_gate=gate_path)
    with pytest.raises(ValueError, match='deterministic gate differs'):
        r1.preflight(path, other, gate_path.parent)


def test_catalog_failure_is_retained_and_never_graded(host_gate, tmp_path, monkeypatch):
    path, _, gate_path, _, _ = host_gate
    manifest = r1.prepare(path, 'task-0-native', tmp_path / 'measured', availability_gate=gate_path)
    observer = Path(manifest['observer']); trace = tmp_path / 'native.jsonl'
    trace.write_text(json.dumps({'type': 'response_item', 'payload': {'type': 'message', 'role': 'assistant'}}) + '\n')
    def qualify(config, trace, *, thread_id):
        return {'status': 'qualified_observations', 'accounting': {}}
    monkeypatch.setattr(r0, 'qualify', qualify)
    monkeypatch.setattr(r1, 'replay', lambda *a, **k: pytest.fail('oracle must not grade invalid treatment'))
    with pytest.raises(ValueError, match='treatment invalid; no correctness grade'):
        r1.evaluate(observer / 'run.json', trace, 'new-measured-thread')
    assert json.loads((observer / 'treatment.json').read_text())['status'] == 'invalid'
    assert not (observer / 'evaluation').exists()


@pytest.mark.parametrize('content', [[], [{'text': 'another task'}], [{'image': 'not text'}]])
def test_recorded_native_prompt_must_match_submission(content):
    account = {'stages': [{'items': [{'type': 'UserMessage', 'content': content}]}]}
    with pytest.raises(ValueError, match='native task message differs'):
        r1._verify_native_prompt(account, 'the frozen prompt')


def test_real_archived_native_shapes_match_prompts_but_fail_new_availability_gate():
    root = Path(__file__).resolve().parents[1] / '.scratch/r1-integrated/pilot-terra-max'
    frozen = json.loads((root / 'freeze.json').read_text())
    index = json.loads((root / 'execution-index.json').read_text())
    for entry in index['runs']:
        scheduled = next(r for r in frozen['schedule'] if r['run_id'] == entry['run_id'])
        task = next(t for t in frozen['tasks'] if t['id'] == scheduled['task'])
        r1._verify_native_prompt(entry['evaluation']['accounting'], task['prompt'])
        trace = root / 'archived-runs' / entry['run_id'] / 'observer/qualification/native-rollout.jsonl'
        with pytest.raises(ValueError, match='fixed live catalog program'):
            availability.audit_catalog(trace, frozen['conditions'][scheduled['condition']]['tools'])


def test_preflight_failure_is_unscored_archived_and_stops_without_retry(tmp_path, monkeypatch):
    path = _freeze(tmp_path); gate = tmp_path / 'deterministic.json'; write_json(gate, {'status': 'passed'})
    calls = []
    def fail(config, gate, frozen, *, measured, amendment=None):
        assert measured is False
        calls.append(config)
        result = {'status': 'failed', 'thread_id': None, 'exit_code': 1, 'measured': False}
        write_json(config.parent / 'execution.json', result)
        return result
    monkeypatch.setattr(r1, '_execute_native', fail)
    destination = tmp_path / 'preflight'
    result = r1.preflight(path, gate, destination)
    assert result['status'] == 'failed' and len(calls) == 1
    assert (destination / 'native/observer/execution.json').is_file()
    with pytest.raises(ValueError, match='availability gate failed'):
        r1.preflight(path, gate, destination)
    assert len(calls) == 1
