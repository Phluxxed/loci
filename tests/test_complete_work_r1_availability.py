"""Shared-entrypoint availability gates; native launches are always blocked or mocked."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import runpy
import sys

import pytest

from benchmarks.complete_work import accounting, availability, r0, r1
from benchmarks.complete_work.evaluate import write_json
from loci.integrated import IntegratedSource
from tests.test_complete_work_r1 import _freeze
from tests.test_complete_work_availability import _trace, _write


def _startup_rows(rows, workspace, observer, prompt, tools):
    """Offline native-shaped context; no host process is involved."""
    def response(kind, **fields):
        return {'type': 'response_item', 'payload': {'type': kind, **fields}}
    content = lambda text: {'type': 'input_text', 'text': text}
    rows = deepcopy(rows)
    rows[0]['payload']['content'] = [content(prompt)]
    rows[1]['payload']['input'] = availability.COMMON_CATALOG_PROGRAM
    common = [{'name': 'exec_command', 'description': 'Run a native shell command.'}]
    rows[2]['payload']['output'] = json.dumps({
        'loci_runtime_catalog_v1': sorted('mcp__loci__' + tool for tool in tools),
        'common_runtime_catalog_v1': {'count': len(common), 'sha256': hashlib.sha256(
            json.dumps(common, ensure_ascii=False, separators=(',', ':')).encode()).hexdigest()}})
    schemas = [{'type': 'namespace', 'name': 'functions', 'description': 'Native tools.', 'tools': [
        {'type': 'function', 'name': 'exec', 'description': 'Run Code Mode.',
         'parameters': {'type': 'object', 'properties': {'code': {'type': 'string'}}}}]}]
    schemas += [{'type': 'function', 'name': 'mcp__loci__' + tool, 'description': tool,
                 'parameters': {'type': 'object'}} for tool in tools]
    header = [
        {'type': 'event_msg', 'payload': {'type': 'task_started', 'turn_id': 'turn'}},
        response('additional_tools', role='developer', id='variable-envelope-id', tools=schemas),
        response('message', role='developer', content=[content('Common developer instructions.'),
                  content('Keep all native tools and existing permissions.')]),
        response('message', role='user', content=[content('Common root AGENTS instructions.'),
                  content('Workspace: ' + str(workspace) + '\nObserver: ' + str(observer))],
                  internal_chat_message_metadata_passthrough={
                      'turn_id': 'turn', 'content_item_kinds': ['agents_md.instructions', 'environments.environment_context'],
                      'content_item_metadata': [{'provenance': {'type': 'agents_md'}},
                                                {'provenance': {'type': 'harness', 'hook': False}}]}),
    ]
    return header + rows


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
def host_gate(tmp_path, monkeypatch, request):
    path = _freeze(tmp_path, **getattr(request, 'param', {}))
    frozen = r1.read_freeze(path)
    source = tmp_path / 'probe-source'
    source.mkdir()
    for name, content in availability.PROBE_FILES.items():
        (source / name).write_text(content)
    common = r1._common_context(frozen)
    if common and frozen['common_context']['root_agents_md'] is not None:
        (source / 'AGENTS.md').write_bytes(frozen['common_context']['root_agents_md'].encode())
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
                              conditions=r1._run_conditions(frozen))
        observer, workspace = Path(manifest['observer']), Path(manifest['workspace'])
        manifest['r1'] = {'phase': 'availability', 'condition': condition,
                          'freeze': str(path.resolve()), 'argv': r1.command(frozen, condition, workspace, observer)}
        write_json(observer / 'run.json', manifest)
        (observer / 'prompt.txt').write_text(r1._probe_prompt(frozen, condition, workspace))
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
        if common:
            rows = _startup_rows(rows, workspace, observer, (observer / 'prompt.txt').read_text(),
                                 frozen['conditions'][condition]['tools'])
        account.update(usage_status='known', native_errors=[], turn_contexts=[{
            **frozen['native_protection'], 'cwd': str(workspace), 'model': frozen['model'], 'effort': frozen['effort']}])
        account['stages'][0]['items'].insert(0, {'type': 'UserMessage', 'content': [{
            'type': 'text', 'text': (observer / 'prompt.txt').read_text()}]})
        qualified = observer / 'qualification'
        qualified.mkdir()
        trace = qualified / 'native-rollout.jsonl'
        _write(trace, rows)
        account['native_provenance'] = {'rollout_path': str(trace)}
        thread = 'probe-' + condition
        write_json(observer / 'execution.json', {'thread_id': thread, 'status': 'closed', 'exit_code': 0,
                   'measured': False, 'freeze_sha256': frozen['freeze_sha256'], 'gate_sha256': 'd' * 64})
        write_json(qualified / 'result.json', {'status': 'qualified_observations', 'thread_id': thread,
                   'config_sha256': r0.digest(observer / 'run.json'), 'native_trace_sha256': r0.digest(trace),
                   'source_before': manifest['source_identity'], 'source_after': manifest['source_identity'],
                   'native_config_sha256': frozen['native_config_sha256'], 'conditions': manifest['conditions'],
                   'config_validation': manifest['config_validation'],
                   'accounting': account})
        evidence = availability.audit_probe(trace, account, condition, workspace, frozen['conditions'][condition]['tools'],
                                             common_context=common)
        if common:
            evidence['common_context'] = availability.audit_common_context(
                trace, workspace, observer, (observer / 'prompt.txt').read_text(),
                frozen['conditions'][condition]['tools'])
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
    def replay_accounting(trace, thread):
        result = deepcopy(captured[str(trace.resolve())])
        result['native_provenance']['rollout_path'] = str(trace)
        return result
    monkeypatch.setattr(accounting, 'summarize_native', replay_accounting)
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


def test_preparation_accepts_only_pinned_cli_defaults_drift_after_probe(host_gate, tmp_path):
    path, frozen, gate_path, _, _ = host_gate
    config = Path(frozen['native_config'])
    config.write_text(config.read_text() + 'model="other-default"\nmodel_reasoning_effort="low"\n')
    manifest = r1.prepare(path, 'task-0-integrated', tmp_path / 'measured', availability_gate=gate_path)
    assert manifest['native_config_sha256'] != frozen['native_config_sha256']
    assert manifest['config_validation']['overridden_default_changes'] == ['model', 'model_reasoning_effort']
    argv = manifest['r1']['argv']
    assert argv[argv.index('-m') + 1] == frozen['model']
    assert 'model_reasoning_effort=' + json.dumps(frozen['effort']) in argv


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


def test_actual_cli_handoff_survives_default_drift_up_to_process_boundary(tmp_path, monkeypatch):
    path = _freeze(tmp_path)
    frozen = r1.read_freeze(path)
    native_config = Path(frozen['native_config'])
    native_config.write_text(native_config.read_text() + 'model="changed-default"\nmodel_reasoning_effort="max"\n')
    gate = tmp_path / 'deterministic.json'; write_json(gate, {'status': 'passed'})
    output = tmp_path / 'cli-receipts'
    seen = []
    class InterceptedBeforeProcessCreation(Exception):
        pass
    def intercept(argv, **kwargs):
        if argv[1:] == ['login', 'status']:
            return subprocess.CompletedProcess(argv, 0, 'Logged in using ChatGPT', '')
        seen.append((argv, kwargs))
        raise InterceptedBeforeProcessCreation('offline check: native process was not started')
    monkeypatch.setattr(subprocess, 'run', intercept)
    script = Path(__file__).resolve().parents[1] / '.scratch/r1-integrated/pilot-execute.py'
    monkeypatch.setattr(sys, 'argv', [str(script), '--freeze', str(path), '--gate', str(gate),
                                    '--output-root', str(output), '--preflight-only'])
    with pytest.raises(SystemExit) as stopped:
        runpy.run_path(str(script), run_name='__main__')
    assert stopped.value.code == 1 and len(seen) == 1
    argv, kwargs = seen[0]
    assert argv[argv.index('-m') + 1] == frozen['model']
    assert 'model_reasoning_effort=' + json.dumps(frozen['effort']) in argv
    assert all(key not in kwargs['env'] for key in ['OPENAI_API_KEY', 'CODEX_API_KEY', 'OPENAI_BASE_URL'])
    assert availability.CATALOG_PROGRAM.encode() in kwargs['input']
    result = json.loads((output / 'availability/gate.json').read_text())
    assert result['status'] == 'failed' and 'InterceptedBeforeProcessCreation' in result['probes'][0]['error']
    config = json.loads((output / 'availability/native/observer/run.json').read_text())
    assert config['native_config_sha256'] != frozen['native_config_sha256']
    assert config['config_validation']['effective_sha256'] == frozen['native_config_binding']['effective_sha256']
    assert not (output / 'execution-index.json').exists()


def test_real_native_probes_replay_after_archive_relocation(tmp_path, monkeypatch):
    """Real accounting and MCP audits; the live probe directories are unnecessary."""
    root = Path(__file__).resolve().parents[1] / '.scratch/r1-integrated/pilot-availability-v2'
    frozen = r1.read_freeze(root / 'freeze.json', runtime=False)
    gate = json.loads((root / 'availability/gate.json').read_text())
    gate['status'] = 'passed'
    gate.pop('error', None)
    gate_path = tmp_path / 'replayed-gate.json'
    write_json(gate_path, gate)
    monkeypatch.setattr(subprocess, 'run', lambda *a, **k: pytest.fail('native launch forbidden'))
    verified = r1.require_availability(frozen, gate_path)
    assert len(verified['threads']) == 4


@pytest.mark.parametrize('mutation', ['rollout_path', 'session_id', 'usage'])
def test_archived_gate_rejects_changed_qualification_accounting(host_gate, mutation):
    _, frozen, gate_path, gate, _ = host_gate
    entry = gate['probes'][0]
    qualification = Path(entry['files']['qualification']['path'])
    value = json.loads(qualification.read_text())
    if mutation == 'usage':
        value['accounting']['usage'] = {'input_tokens': 999999}
    else:
        value['accounting']['native_provenance'][mutation] = 'forged'
    write_json(qualification, value)
    entry['files']['qualification']['sha256'] = r0.digest(qualification)
    write_json(gate_path, gate)
    with pytest.raises(ValueError, match='accounting differs'):
        r1.require_availability(frozen, gate_path)
