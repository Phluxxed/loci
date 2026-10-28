"""Offline runner integration: native-shaped delivery, real readers and oracles.

No Codex or MCP process runs. The native process double delivers synthetic raw
sessions and real local source/proof packets; it does not validate a live host.
The only other doubles inject one process interruption or reader exception,
without replacing any successful validation, accounting or grading result.
"""
from copy import deepcopy
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess

import pytest

from benchmarks.complete_work import accounting, availability, r0, r1
from benchmarks.complete_work.evaluate import write_json
from loci.integrated import IntegratedSource


SCRIPT = Path(__file__).resolve().parents[1] / '.scratch/r1-integrated/pilot-execute.py'
ACTIVE_AMENDMENT = SCRIPT.with_name('terminal-observation-amendment.json')
PROTECTIONS = {
    'approval_policy': 'on-request', 'approvals_reviewer': 'auto_review',
    'sandbox_policy': {'type': 'workspace-write'}, 'permission_profile': {'type': 'managed'},
    'active_permission_profile': {'id': 'offline-fixture'},
    'file_system_sandbox_policy': {'kind': 'restricted'},
}
COMMON_TOOLS = [
    {'name': 'apply_patch', 'description': 'Write the requested local file.'},
    {'name': 'exec_command', 'description': 'Run a native shell command.'},
]


def bytes_under(root):
    return {str(p.relative_to(root)): p.read_bytes() for p in root.rglob('*') if p.is_file()}


def _freeze(tmp_path):
    config = tmp_path / 'config.toml'
    config.write_text('approval_policy="on-request"\n')
    global_agents = tmp_path / 'AGENTS.md'
    global_agents.write_text('Personal instructions when the experiment was frozen.\n')
    host = tmp_path / 'native-process-delivery-only'
    host.write_text('This fixture is never executed.\n')
    tasks = []
    for number in range(4):
        source = tmp_path / f'task-{number}'
        source.mkdir()
        (source / 'original.js').write_text(f'export const n={number};\n')
        (source / 'AGENTS.md').write_text('Shared fixture repository instructions.\n')
        prompt = tmp_path / f'prompt-{number}.txt'
        prompt.write_text('Read original.js; write answer.json containing its n value.\n')
        oracle = tmp_path / f'oracle-{number}.mjs'
        oracle.write_text("import fs from 'node:fs';import assert from 'node:assert/strict';"
                          "assert.deepEqual(JSON.parse(fs.readFileSync(process.argv[2]+'/answer.json')),{n:"
                          + str(number) + '});\n')
        tasks.append({'id': f'task-{number}', 'source': str(source), 'prompt': str(prompt),
                      'oracle': str(oracle), 'criteria': {'allowed_changes': ['answer.json']}})
    conditions = {name: {'command': 'not-launched', 'args': ['fixture-only'],
                          'env': {'LOCI_R1_STORE': '{store}'},
                          'tools': availability.TOOLS_BY_CONDITION[name]} for name in r1.CONDITIONS}
    # A synthetic historical runner pin makes the explicit policy amendment real
    # without changing production files during a test.
    plan = {'tasks': tasks, 'native_config': str(config), 'conditions': conditions,
            'model': 'gpt-6.1-terra', 'effort': 'max', 'native_protection': PROTECTIONS,
            'common_context': True, 'host': {'executable': str(host), 'sha256': r0.digest(host),
                'startup_context_files': {str(global_agents): r0.digest(global_agents)},
                'orchestration_files': {str(SCRIPT): '1' * 64}}}
    plan_path = tmp_path / 'plan.json'
    write_json(plan_path, plan)
    frozen = r1.freeze(plan_path, tmp_path / 'frozen')
    # Exercise the policy selectors in the amendment actually supplied to the
    # operator, including a personal-instruction change after the freeze.
    active = json.loads(ACTIVE_AMENDMENT.read_text())
    claimed = active.pop('amendment_sha256')
    assert r1.identity(active) == claimed
    amendment = {'schema_version': 1, 'kind': 'r1-instrumentation-amendment',
                 'freeze_sha256': frozen['freeze_sha256'],
                 'host_observation_policy': active['host_observation_policy'],
                 'catalog_capture_policy': active['catalog_capture_policy'],
                 'catalog_capture_policy_sha256': r1.identity(availability.capture_policy(
                     frozen['common_context']['root_agents_md'])),
                 'changes': {str(SCRIPT): {'before_sha256': '1' * 64, 'after_sha256': r0.digest(SCRIPT)}}}
    amendment['amendment_sha256'] = r1.identity(amendment)
    amendment_path = tmp_path / 'instrumentation-amendment.json'
    write_json(amendment_path, amendment)
    global_agents.write_text('Current personal instructions shared by all conditions.\n')
    gate = tmp_path / 'deterministic-gate.json'
    write_json(gate, {'status': 'passed', 'fixture': 'independent frozen gate'})
    return tmp_path / 'frozen/freeze.json', amendment_path, gate


class NativeDelivery:
    """Only a process/session boundary double; all downstream readers are real."""
    def __init__(self, home, host, stores, original_run):
        self.home, self.host, self.stores, self.original_run = home, host, stores, original_run
        self.launches = []
        self.run_roots = set()
        self.catalog_drift = None
        self.catalog_syntax_failure = None
        self.memory_truncation_run = None
        self.catalog_runtime_failure_run = None

    def __call__(self, argv, **kwargs):
        if str(argv[0]) != str(self.host):
            assert argv[0] in {'node', 'git'}, f'unexpected process: {argv}'
            return self.original_run(argv, **kwargs)
        if argv[1:] == ['login', 'status']:
            return subprocess.CompletedProcess(argv, 0, 'Logged in using ChatGPT', '')
        assert argv[1] == 'exec'
        observer = Path(argv[argv.index('-o') + 1]).parent
        self.run_roots.add(observer.parent.parent)
        manifest = json.loads((observer / 'run.json').read_text())
        assert argv == manifest['r1']['argv']
        assert kwargs['input'] == (observer / 'prompt.txt').read_bytes()
        assert all(key not in kwargs['env'] for key in ['OPENAI_API_KEY', 'CODEX_API_KEY', 'OPENAI_BASE_URL'])
        thread = f'offline-native-thread-{len(self.launches):03}'
        self.launches.append({'thread': thread, 'run_id': manifest['run_id'],
                              'condition': manifest['r1']['condition'],
                              'probe': manifest['r1'].get('phase') == 'availability'})
        trace = self.home / '.codex/sessions' / (thread + '.jsonl')
        trace.parent.mkdir(parents=True, exist_ok=True)
        rows = self._rows(manifest, observer, thread)
        trace.write_text(''.join(json.dumps(row) + '\n' for row in rows))
        (observer / 'final.txt').write_text('Offline native delivery fixture.\n')
        kwargs['stdout'].write((json.dumps({'type': 'thread.started', 'thread_id': thread}) + '\n').encode())
        return subprocess.CompletedProcess(argv, 0)

    def _rows(self, manifest, observer, thread):
        workspace = Path(manifest['workspace'])
        condition = manifest['r1']['condition']
        tools = availability.TOOLS_BY_CONDITION[condition]
        turn, session = thread + '-turn', thread + '-session'
        def row(kind, payload):
            return {'timestamp': '2026-10-27T00:00:00Z', 'type': kind, 'payload': payload}
        def response(kind, **fields):
            return row('response_item', {'type': kind,
                'internal_chat_message_metadata_passthrough': {'turn_id': turn}, **fields})
        def event(kind, **fields):
            return row('event_msg', {'type': kind, 'thread_id': thread, 'turn_id': turn, **fields})
        def text(value):
            return {'type': 'input_text', 'text': value}
        def operation(item):
            started = deepcopy(item)
            started['status'] = 'inProgress'
            return [event('item_started', item=started, started_at_ms=100001),
                    event('item_completed', item=item, completed_at_ms=100002)]
        schemas = [{'type': 'namespace', 'name': 'functions', 'description': 'Native tools.', 'tools': [
            {'type': 'function', 'name': 'exec', 'description': 'Run Code Mode.',
             'parameters': {'type': 'object', 'properties': {'code': {'type': 'string'}}}}]}]
        schemas += [{'type': 'function', 'name': 'mcp__loci__' + name, 'description': name,
                     'parameters': {'type': 'object'}} for name in tools]
        bootstrap_metadata = {'turn_id': turn, 'create_time': 100,
            'content_item_kinds': ['agents_md.instructions', 'environments.environment_context'],
            'content_item_metadata': [{'provenance': {'type': 'agents_md'}},
                                      {'provenance': {'type': 'harness', 'hook': False}}]}
        prompt = (observer / 'prompt.txt').read_text()
        memory_count = 5316 if manifest['run_id'] == self.memory_truncation_run else 5091
        rows = [row('session_meta', {'id': thread, 'session_id': session, 'cwd': str(workspace),
                    'cli_version': 'offline-native-shape', 'source': 'cli', 'thread_source': 'user'}),
                event('task_started', started_at=100),
                row('turn_context', {'turn_id': turn, 'cwd': str(workspace),
                     'model': 'gpt-6.1-terra', 'effort': 'max', **PROTECTIONS}),
                response('additional_tools', role='developer', id='startup-envelope', tools=schemas),
                response('message', role='developer', content=[text('Common developer instructions.'),
                         text('Preserve native tools and permissions.')]),
                response('message', role='developer', content=[text(
                    '========= MEMORY_SUMMARY BEGINS =========\n'
                    f'Visible prefix…{memory_count} tokens truncated…Visible suffix\n'
                    '========= MEMORY_SUMMARY ENDS =========')],
                    internal_chat_message_metadata_passthrough={'turn_id': turn,
                        'content_item_kinds': ['memories.instructions'],
                        'content_item_metadata': [{'provenance': {'type': 'harness', 'hook': False}}]}),
                response('message', role='user', content=[text(
                         (Path(manifest['native_config']).parent / 'AGENTS.md').read_text()
                         + 'Shared fixture repository instructions.\n'),
                         text('Workspace: ' + str(workspace) + '\nObserver: ' + str(observer))],
                         internal_chat_message_metadata_passthrough=bootstrap_metadata),
                response('message', role='user', content=[text(prompt)]),
                event('item_completed', item={'type': 'UserMessage', 'id': 'submitted-task',
                      'content': [{'type': 'text', 'text': prompt}]})]
        # Typed startup hook follows submission but precedes model activity.
        rows.append(response('message', role='developer', content=[text('Common same-turn startup hook.')],
            internal_chat_message_metadata_passthrough={'turn_id': turn, 'create_time': 101,
                'content_item_kinds': ['hooks.additional_context'],
                'content_item_metadata': [{'provenance': {'type': 'harness', 'hook': True}}]}))
        values = deepcopy(COMMON_TOOLS)
        if self.catalog_drift == condition:
            values[1]['description'] = 'PRIVATE altered shell descriptor.'
        artifact = observer / 'common-tool-catalog.json'
        raw = json.dumps(values, ensure_ascii=False, separators=(',', ':')).encode() + b'\n'
        fingerprint = {'count': len(values), 'sha256': hashlib.sha256(raw[:-1]).hexdigest()}
        capture = availability.capture_program(artifact) in prompt
        program = availability.capture_program(artifact) if capture else availability.COMMON_CATALOG_PROGRAM
        capture_failed = manifest['run_id'] == self.catalog_runtime_failure_run
        if capture_failed:
            program = program.replace('0xab1c5ed5', '0xab1c5d5', 1)
        if manifest['run_id'] == self.catalog_syntax_failure:
            rows.append(response('custom_tool_call', name='functions.exec', call_id='failed-catalog',
                                 input=program.replace('0xa81a664b', '00xa81a664b', 1)))
            rows.append(response('custom_tool_call_output', call_id='failed-catalog', output=[
                text('Script failed\nWall time 0.0 seconds\nOutput:\n'),
                text('Script error:\nSyntaxError: Invalid or unexpected token')]))
        rows.append(response('custom_tool_call', name='functions.exec', call_id='catalog', input=program))
        if capture:
            artifact.write_bytes(raw)
            rows += operation({'type': 'FileChange', 'id': 'catalog-write', 'status': 'completed', 'stderr': '',
                               'changes': {str(artifact): {'type': 'add', 'content': raw.decode()}}})
            rows += operation({'type': 'CommandExecution', 'id': 'catalog-readback', 'status': 'completed',
                               'cwd': str(workspace), 'exit_code': 0,
                               'command': ['/bin/zsh', '-lc', availability.capture_check_command(artifact)],
                               'aggregated_output': json.dumps(fingerprint) + '\n'})
        receipt = {'loci_runtime_catalog_v1': sorted('mcp__loci__' + name for name in tools),
                   'common_runtime_catalog_v1': fingerprint}
        if capture:
            receipt['native_access_v1'] = {'apply_patch': True, 'exec_command': True}
        output = ([text('Script failed\nWall time 0.5 seconds\nOutput:\n'),
                   text('Script error:\nError: Catalog capture failed: retained bytes differ from the first-call registry')]
                  if capture_failed else json.dumps(receipt))
        rows.append(response('custom_tool_call_output', call_id='catalog', output=output))
        if manifest['r1'].get('phase') == 'availability' and tools:
            service = IntegratedSource(self.stores / thread)
            retrieved = service.retrieve(workspace, 'entry.ts')
            ref = retrieved['items'][0]['source_ref']
            packets = [('loci_retrieve', {'query': 'entry.ts'}, retrieved),
                       ('loci_read', {'source_ref': ref}, service.read(workspace, ref))]
            if condition == 'integrated':
                semantic = service.semantic_context(workspace, 'entry', anchor_file='entry.ts')
                node = semantic['anchors'][0]['node_id']
                packets += [('loci_semantic', {'query': 'entry', 'anchor_file': 'entry.ts'}, semantic),
                            ('loci_proof', {'node_id': node}, service.proof_context(workspace, node))]
            for name, args, packet in packets:
                call_id = 'probe-' + name
                rows.append(response('custom_tool_call', name='functions.exec', call_id=call_id,
                                     input='/* native-delivery fixture MCP action */'))
                rows += operation({'type': 'McpToolCall', 'id': call_id, 'server': 'loci', 'tool': name,
                    'arguments': {'repo': str(workspace), **args}, 'status': 'completed',
                    'result': {'content': [], 'structuredContent': packet, 'isError': False}})
                rows.append(response('custom_tool_call_output', call_id=call_id, output='Native tool completed.'))
        elif manifest['r1'].get('phase') != 'availability' and not capture_failed:
            number = int(manifest['r1']['task'].split('-')[-1])
            if manifest['run_id'] == 'task-2-eager':
                number = -1  # A wrong answer must remain a valid measured outcome.
            content = json.dumps({'n': number}) + '\n'
            (workspace / 'answer.json').write_text(content)
            rows.append(response('custom_tool_call', name='functions.exec', call_id='answer', input='/* fixture answer */'))
            rows += operation({'type': 'FileChange', 'id': 'answer-write', 'status': 'completed',
                'changes': {str(workspace / 'answer.json'): {'type': 'add', 'content': content}}})
            rows.append(response('custom_tool_call_output', call_id='answer', output='Answer written.'))
        rows.append(response('message', role='assistant', phase='final_answer', content=[{'type': 'output_text',
            'text': 'Capture failed; stopped before the task.' if capture_failed else 'Done.'}]))
        usage = {'input_tokens': 100, 'cached_input_tokens': 20, 'cache_write_input_tokens': 0,
                 'output_tokens': 10, 'reasoning_output_tokens': 2, 'total_tokens': 110}
        rows += [row('token_usage_record', {'thread_id': thread, 'session_id': session, 'turn_id': turn,
                     'response_id': thread + '-response', 'usage': usage,
                     'turn_token_usage': usage, 'thread_token_usage': usage}),
                 event('task_complete', started_at=100, completed_at=101, duration_ms=1000)]
        return rows


@pytest.fixture
def integrated_runner(tmp_path, monkeypatch):
    freeze, amendment, gate = _freeze(tmp_path)
    frozen = r1.read_freeze(freeze, amendment=amendment)
    spec = importlib.util.spec_from_file_location('pilot_integration', SCRIPT)
    runner = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(runner)
    root = tmp_path / 'execution'
    home = tmp_path / 'home'
    monkeypatch.setattr(Path, 'home', classmethod(lambda cls: home))
    native = NativeDelivery(home, Path(frozen['host']['executable']), tmp_path / 'packet-stores', subprocess.run)
    monkeypatch.setattr(subprocess, 'run', native)
    argv = ['--freeze', str(freeze), '--amendment', str(amendment), '--gate', str(gate), '--output-root', str(root)]
    try:
        yield runner, native, root, argv, freeze, amendment, gate
    finally:
        for run_root in native.run_roots:
            shutil.rmtree(run_root, ignore_errors=True)


def test_first_preflight_measured_checkpoint_resume_and_archive_only_readback(integrated_runner, monkeypatch):
    runner, native, root, argv, freeze, amendment, gate = integrated_runner
    effective = r1.read_freeze(freeze, amendment=amendment)
    assert effective['host_observations']['startup_instructions'][0]['changed'] is True
    assert effective['capture_context']['schema'] == 'r1-common-context-v2'
    frozen_bytes = freeze.read_bytes()
    preflight = runner.main(argv + ['--preflight-only'])
    assert preflight['status'] == 'passed'
    assert len(native.launches) == 4 and all(item['probe'] for item in native.launches)
    shutil.rmtree(Path(preflight['run_root']))
    assert runner.main(argv + ['--preflight-only'])['status'] == 'passed'
    assert len(native.launches) == 4
    original_gate = root / 'availability/gate.json'
    failed_reader = runner.read(original_gate)
    failed_reader.update(status='failed', error='injected aggregate reader failure after completed probes')
    write_json(original_gate, failed_reader)
    original_probes = bytes_under(root / 'availability')
    reprocessed = runner.main(argv + ['--reprocess'])
    assert reprocessed['status'] == 'passed' and len(native.launches) == 4
    assert bytes_under(root / 'availability') == original_probes
    verified = r1.require_availability(r1.read_freeze(freeze, amendment=amendment), Path(reprocessed['gate_path']))
    assert len(verified['threads']) == 4
    argv += ['--availability-gate', reprocessed['gate_path']]
    original_write = runner.write_json
    def interrupt_after_first_archive(path, value):
        original_write(path, value)
        runs = value.get('runs', [])
        if Path(path) == root / 'execution-index.json' and len(runs) == 1 and runs[0].get('replay_result'):
            raise KeyboardInterrupt('injected interruption after durable first-run checkpoint')
    with monkeypatch.context() as fault:
        fault.setattr(runner, 'write_json', interrupt_after_first_archive)
        with pytest.raises(KeyboardInterrupt, match='durable first-run checkpoint'):
            runner.main(argv)
    index = runner.read(root / 'execution-index.json')
    assert len(index['runs']) == 1 and len(native.launches) == 5
    first_archive = Path(index['runs'][0]['archive'])
    first_bytes = bytes_under(first_archive)
    shutil.rmtree(Path(index['run_root']))
    before_check = bytes_under(root)
    assert runner.main(argv + ['--resume', '--check-only']) == {
        'status': 'checked', 'next_run_id': 'task-0-path-only', 'pending': 15, 'retained': 1}
    assert bytes_under(root) == before_check and len(native.launches) == 5
    assert runner.main(argv + ['--resume'])['status'] == 'complete'
    index = runner.read(root / 'execution-index.json')
    assert len(index['runs']) == 16 and len(native.launches) == 20
    assert len({item['thread'] for item in native.launches}) == 20
    assert len({item['run_id'] for item in native.launches if not item['probe']}) == 16
    assert bytes_under(first_archive) == first_bytes and freeze.read_bytes() == frozen_bytes
    assert sum(entry['evaluation']['correct'] for entry in index['runs']) == 15
    shutil.rmtree(Path(index['run_root']))
    for entry in index['runs']:
        observer = Path(entry['archive']) / 'observer'
        trace = observer / 'qualification/native-rollout.jsonl'
        reduced = accounting.summarize_native(trace, entry['execution']['thread_id'])
        assert reduced['usage_status'] == 'known' and not reduced['native_errors']
        assert reduced['usage']['totalTokens'] == 110
        replay = r1.replay(observer / 'run.json', root / 'independent-archive-replay' / entry['run_id'],
                           retained_observer=observer)
        assert replay['correct'] == entry['evaluation']['correct']
        assert replay['source_identity'] == entry['evaluation']['source_identity']
    assert runner.main(argv + ['--resume', '--check-only'])['pending'] == 0
    assert len(native.launches) == 20


def test_catalog_mismatch_is_actionable_and_retained_reprocessing_never_launches(integrated_runner):
    runner, native, root, argv, freeze, amendment, gate = integrated_runner
    native.catalog_drift = 'eager'
    result = runner.main(argv)
    assert result['status'] == 'failed'
    assert len(native.launches) == 4 and not (root / 'execution-index.json').exists()
    rendered = json.dumps(result)
    assert 'exec_command' in rendered and 'PRIVATE altered shell descriptor.' not in rendered
    original = bytes_under(root / 'availability')
    reread = runner.main(argv + ['--reprocess'])
    assert reread['status'] == 'failed' and 'exec_command' in json.dumps(reread)
    assert len(native.launches) == 4 and bytes_under(root / 'availability') == original
    assert not (root / 'execution-index.json').exists()


def test_closed_treatment_reader_failure_recovers_same_native_assignment(integrated_runner, monkeypatch):
    runner, native, root, argv, freeze, amendment, gate = integrated_runner
    native.catalog_syntax_failure = 'task-1-integrated'
    assert runner.main(argv + ['--preflight-only'])['status'] == 'passed'
    original_audit = r1.audit_treatment
    def fail_after_real_validation(*args, **kwargs):
        result = original_audit(*args, **kwargs)
        if result.get('pre_capture_failures'):
            raise ValueError('injected treatment reader failure after raw validation')
        return result
    with monkeypatch.context() as fault:
        fault.setattr(r1, 'audit_treatment', fail_after_real_validation)
        blocked = runner.main(argv)
    assert blocked['status'] == 'blocked' and blocked['attempted'] == 6
    index_path = root / 'execution-index.json'
    original_index = index_path.read_bytes()
    original = runner.read(index_path)['runs'][-1]
    archive = Path(original['archive'])
    archive_bytes = bytes_under(archive)
    assert original['execution']['status'] == 'closed' and len(native.launches) == 10
    shutil.rmtree(Path(runner.read(index_path)['run_root']))
    assert runner.main(argv + ['--resume'])['status'] == 'complete'
    completed = runner.read(index_path)
    recovered = completed['runs'][5]
    assert recovered['execution']['thread_id'] == original['execution']['thread_id']
    assert recovered['evaluation']['correct'] is True
    assert len(recovered['evaluation']['treatment_validity']['pre_capture_failures']) == 1
    assert Path(recovered['recovery']['original_index']).read_bytes() == original_index
    assert bytes_under(archive) == archive_bytes
    assert Path(recovered['treatment_result']).is_relative_to(root / 'reprocessed')
    assert len(native.launches) == 20
    assert sum(item['run_id'] == original['run_id'] for item in native.launches) == 1
    assert runner.main(argv + ['--resume', '--check-only'])['pending'] == 0


def test_legacy_hash_only_probes_cannot_gain_missing_capture_by_reprocessing(integrated_runner):
    runner, native, root, argv, freeze, amendment, gate = integrated_runner
    legacy = runner.read(amendment)
    legacy.pop('catalog_capture_policy')
    legacy.pop('catalog_capture_policy_sha256')
    legacy.pop('amendment_sha256')
    legacy['amendment_sha256'] = r1.identity(legacy)
    legacy_path = amendment.with_name('legacy-instrumentation-amendment.json')
    write_json(legacy_path, legacy)
    legacy_argv = list(argv)
    legacy_argv[legacy_argv.index('--amendment') + 1] = str(legacy_path)
    assert runner.main(legacy_argv + ['--preflight-only'])['status'] == 'passed'
    assert len(native.launches) == 4
    source = root / 'availability'
    assert not list(source.rglob('common-tool-catalog.json'))
    original = bytes_under(source)
    result = runner.main(argv + ['--reprocess'])
    assert result['status'] == 'failed'
    assert 'only catalog hashes' in result['error'] or 'cannot reconstruct' in result['error']
    assert bytes_under(source) == original and len(native.launches) == 4
    assert not (root / 'execution-index.json').exists()


def test_waiting_existing_runner_accepts_bound_repair_and_finishes_without_repeating_native_work(integrated_runner, monkeypatch):
    runner, native, root, argv, freeze, amendment, gate = integrated_runner
    native.catalog_syntax_failure = 'task-1-integrated'
    native.memory_truncation_run = 'task-1-native'
    real_audit = r1.audit_treatment
    def old_reader(*args, **kwargs):
        treatment = real_audit(*args, **kwargs)
        if treatment.get('startup_rendering_variations'):
            raise ValueError('injected old reader rejects a host rendering count')
        return treatment
    with monkeypatch.context() as fault:
        fault.setattr(r1, 'audit_treatment', old_reader)
        blocked = runner.main(argv)
    assert blocked['status'] == 'blocked' and blocked['attempted'] == 7
    assert len(native.launches) == 11
    archived_before = bytes_under(root / 'archived-runs')
    prior_index = (root / 'execution-index.json').read_bytes()
    repaired = runner.read(amendment)
    repaired.pop('amendment_sha256')
    repaired['note'] = 'Test repair request; successful readers remain real.'
    repaired['amendment_sha256'] = r1.identity(repaired)
    repair_path = amendment.with_name('requested-repair.json')
    write_json(repair_path, repaired)
    restarted = []
    class ReplacedProcess(BaseException):
        pass
    def resume_request(seconds):
        assert seconds == 1 and len(native.launches) == 11
        state = runner.read(root / 'repair-wait.json')
        assert state['status'] == 'waiting'
        write_json(root / 'repair-request.json', {'schema_version': 1,
            'freeze_sha256': state['freeze_sha256'],
            'execution_index_sha256': state['execution_index_sha256'],
            'amendment': {'path': str(repair_path), 'sha256': r0.digest(repair_path)}})
    def replace_process(executable, arguments):
        restarted.append((executable, arguments))
        raise ReplacedProcess
    with monkeypatch.context() as host:
        host.setattr(r1, 'audit_treatment', old_reader)
        host.setattr(runner.time, 'sleep', resume_request)
        host.setattr(runner.os, 'execv', replace_process)
        with pytest.raises(ReplacedProcess):
            runner.main(argv + ['--resume', '--wait-for-repair'])
    assert len(restarted) == 1 and len(native.launches) == 11
    assert (root / 'execution-index.json').read_bytes() == prior_index
    assert bytes_under(root / 'archived-runs') == archived_before
    executable, restart_argv = restarted[0]
    assert restart_argv[:3] == [executable, '-u', str(SCRIPT)]
    assert restart_argv[-2:] == ['--resume', '--wait-for-repair']
    assert runner.main(restart_argv[3:])['status'] == 'complete'
    final = runner.read(root / 'execution-index.json')
    assert len(final['runs']) == 16 and len(native.launches) == 20
    assert len({item['run_id'] for item in native.launches}) == 20
    assert final['runs'][6]['evaluation']['correct'] is True
    changes = final['runs'][6]['evaluation']['treatment_validity']['startup_rendering_variations']
    assert changes[0]['expected_tokens'] == 5091 and changes[0]['observed_tokens'] == 5316
    assert all((root / 'archived-runs' / name).read_bytes() == raw for name, raw in archived_before.items())


def test_closed_capture_failure_keeps_false_grade_unqualified_and_continues_without_replacement(integrated_runner, monkeypatch):
    runner, native, root, argv, freeze, amendment, gate = integrated_runner
    native.catalog_runtime_failure_run = 'task-2-integrated'
    # Reproduce the old reader's stop after an actual failed, non-retried capture.
    def old_observe(*args, **kwargs):
        return {'status': 'verified', **r1.audit_treatment(*args, **kwargs)}
    with monkeypatch.context() as old:
        old.setattr(r1, 'observe_treatment', old_observe)
        blocked = runner.main(argv)
    assert blocked['status'] == 'blocked' and blocked['attempted'] == 9
    assert len(native.launches) == 13
    original_index = (root / 'execution-index.json').read_bytes()
    original = runner.read(root / 'execution-index.json')['runs'][-1]
    archive = Path(original['archive'])
    archive_bytes = bytes_under(archive)
    result = runner.main(argv + ['--resume', '--wait-for-repair'])
    assert result['status'] == 'complete' and len(native.launches) == 20
    index = runner.read(root / 'execution-index.json')
    failed = index['runs'][8]
    evaluation = failed['evaluation']
    assert failed['execution']['thread_id'] == original['execution']['thread_id']
    assert evaluation['correct'] is False
    assert evaluation['qualification_status'] == 'qualified_observations'
    assert evaluation['accounting']['usage_status'] == 'known'
    assert evaluation['comparison_status'] == 'unqualified'
    assert evaluation['treatment_validity']['status'] == 'unqualified'
    assert evaluation['changes'] == [] and failed['replay_matches'] is True
    assert Path(failed['recovery']['original_index']).read_bytes() == original_index
    assert bytes_under(archive) == archive_bytes
    assert not (root / 'repair-wait.json').exists()
    assert len({item['run_id'] for item in native.launches}) == 20
    # An ordinary wrong answer with valid treatment still counts as a qualified
    # incorrect outcome; qualification is never chosen from the answer score.
    other_wrong = next(e['evaluation'] for e in index['runs'] if e['run_id'] == 'task-2-eager')
    assert other_wrong['correct'] is False and other_wrong['comparison_status'] == 'qualified'
    assert runner.main(argv + ['--resume', '--check-only'])['pending'] == 0
