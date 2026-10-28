"""Bounded repair requests never launch work or bypass normal retained resumption."""
import argparse
import copy
from pathlib import Path
import sys

import pytest

from benchmarks.complete_work import r0, r1
from benchmarks.complete_work.evaluate import write_json
from tests.test_complete_work_r1_resume import pilot


@pytest.fixture
def waiting(pilot, monkeypatch):
    runner = pilot['runner']
    pilot['frozen']['freeze_sha256'] = 'f' * 64
    write_json(pilot['freeze'], pilot['frozen'])
    first = pilot['retain'](0)
    first['evidence_error'] = 'original observer reader failed'
    first.pop('evaluation')
    pilot['save']([first])
    args = argparse.Namespace(freeze=pilot['freeze'], gate=pilot['gate'], amendment=pilot['amendment'],
                              availability_gate=pilot['availability_gate'])
    failure = {'status': 'blocked', 'error': 'retained observer recovery failed'}
    state = runner.repair_wait_state(args, pilot['root'], pilot['frozen'], failure)
    updated = pilot['root'] / 'repaired-amendment.json'
    write_json(updated, {'status': 'repaired instrumentation'})
    checks = []

    def read_freeze(path, *, amendment=None):
        checks.append((path, amendment))
        return pilot['frozen']

    monkeypatch.setattr(r1, 'read_freeze', read_freeze)
    request = {'schema_version': 1, 'freeze_sha256': state['freeze_sha256'],
               'execution_index_sha256': state['execution_index_sha256'],
               'amendment': {'path': str(updated), 'sha256': r0.digest(updated)}}
    return {**pilot, 'args': args, 'state': state, 'request': request, 'updated': updated,
            'checks': checks, 'failure': failure}


def test_valid_request_reexecs_exact_same_runner_and_retains_receipt(waiting, monkeypatch):
    runner, root = waiting['runner'], waiting['root']
    write_json(root / 'repair-request.json', waiting['request'])
    original_index = (root / 'execution-index.json').read_bytes()
    archived = {path: path.read_bytes() for path in (root / 'archived-runs').rglob('*') if path.is_file()}
    launches = []
    monkeypatch.setattr(runner.os, 'execv', lambda executable, argv: launches.append((executable, argv)))
    monkeypatch.setattr(r1, 'require_availability', lambda *a, **k: pytest.fail('old observer reader called'))
    result = runner.wait_for_repair(waiting['args'], root, waiting['state'])
    expected = [sys.executable, '-u', str(Path(runner.__file__).resolve()),
                '--freeze', str(waiting['freeze']), '--gate', str(waiting['gate']),
                '--output-root', str(root), '--availability-gate', str(waiting['availability_gate']),
                '--amendment', str(waiting['updated']), '--resume', '--wait-for-repair']
    assert launches == [(sys.executable, expected)]
    assert result['status'] == 'restarting'
    assert waiting['checks'] == [(waiting['freeze'], waiting['updated'])]
    assert not (root / 'repair-request.json').exists()
    receipts = list((root / 'repair-requests').glob('*.receipt.json'))
    assert len(receipts) == 1 and runner.read(receipts[0])['status'] == 'accepted'
    assert runner.read(Path(runner.read(receipts[0])['request'])) == waiting['request']
    assert (root / 'execution-index.json').read_bytes() == original_index
    assert all(path.read_bytes() == content for path, content in archived.items())
    assert not any(waiting['calls'].values())


def test_exec_failure_is_retained_and_returns_blocked_without_retry(waiting, monkeypatch):
    runner, root = waiting['runner'], waiting['root']
    write_json(root / 'repair-request.json', waiting['request'])
    attempts = []
    def fail(executable, argv):
        attempts.append((executable, argv))
        raise OSError('replacement executable unavailable')
    monkeypatch.setattr(runner.os, 'execv', fail)
    monkeypatch.setattr(runner.time, 'sleep', lambda *a: pytest.fail('failed exec must not retry or wait'))
    result = runner.wait_for_repair(waiting['args'], root, waiting['state'])
    receipt = runner.read(next((root / 'repair-requests').glob('*.receipt.json')))
    marker = runner.read(root / 'repair-wait.json')
    assert len(attempts) == 1
    assert result['status'] == 'blocked' and result['stage'] == 'repair_restart'
    assert receipt['status'] == marker['status'] == 'restart_failed'
    assert receipt['error'] == marker['error'] == result['error'] == 'OSError: replacement executable unavailable'
    assert result['original_failure'] == waiting['failure']
    assert not any(waiting['calls'].values())


@pytest.mark.parametrize('change,error', [
    ('stale-index', 'execution_index_sha256 is stale'),
    ('wrong-freeze', 'freeze_sha256 differs'),
    ('extra-field', 'request fields must be exactly'),
    ('extra-amendment-field', 'amendment must contain exactly'),
    ('wrong-amendment-hash', 'amendment file/hash differs'),
    ('same-amendment', 'bytes must differ'),
    ('relative-amendment', 'path must be absolute'),
    ('boolean-version', 'schema_version must be 1'),
])
def test_rejected_request_is_retained_and_wait_continues(waiting, monkeypatch, change, error):
    runner, root = waiting['runner'], waiting['root']
    request = copy.deepcopy(waiting['request'])
    if change == 'stale-index':
        request['execution_index_sha256'] = '0' * 64
    elif change == 'wrong-freeze':
        request['freeze_sha256'] = '0' * 64
    elif change == 'extra-field':
        request['command'] = 'never execute arbitrary commands'
    elif change == 'extra-amendment-field':
        request['amendment']['root'] = '/arbitrary-root'
    elif change == 'wrong-amendment-hash':
        request['amendment']['sha256'] = '0' * 64
    elif change == 'same-amendment':
        request['amendment'] = waiting['state']['amendment']
    elif change == 'relative-amendment':
        request['amendment']['path'] = 'relative.json'
    elif change == 'boolean-version':
        request['schema_version'] = True
    write_json(root / 'repair-request.json', request)
    monkeypatch.setattr(runner.os, 'execv', lambda *a: pytest.fail('rejected repair must not exec'))

    def stop(seconds):
        assert seconds == 1
        assert runner.read(root / 'repair-wait.json')['status'] == 'waiting'
        raise KeyboardInterrupt

    monkeypatch.setattr(runner.time, 'sleep', stop)
    result = runner.wait_for_repair(waiting['args'], root, waiting['state'])
    receipt = runner.read(next((root / 'repair-requests').glob('*.receipt.json')))
    assert receipt['status'] == 'rejected' and error in receipt['error']
    assert runner.read(Path(receipt['request'])) == request
    assert result['original_failure'] == waiting['failure']
    assert waiting['state']['diagnostics']['evidence_error'] == 'original observer reader failed'
    assert not any(waiting['calls'].values())


@pytest.mark.parametrize('changed', ['freeze', 'execution-index'])
def test_changed_wait_binding_rejects_valid_request(waiting, changed):
    target = waiting['freeze'] if changed == 'freeze' else waiting['root'] / 'execution-index.json'
    target.write_bytes(target.read_bytes() + b'\n')
    with pytest.raises(ValueError, match='changed while waiting'):
        waiting['runner'].repair_request(waiting['args'], waiting['root'], waiting['state'], waiting['request'])


def test_malformed_request_is_retained_then_later_valid_request_can_restart(waiting, monkeypatch):
    runner, root = waiting['runner'], waiting['root']
    (root / 'repair-request.json').write_text('{invalid JSON')
    launches = []
    monkeypatch.setattr(runner.os, 'execv', lambda *args: launches.append(args))
    def repaired_request(seconds):
        assert not any(waiting['calls'].values())
        write_json(root / 'repair-request.json', waiting['request'])
    monkeypatch.setattr(runner.time, 'sleep', repaired_request)
    runner.wait_for_repair(waiting['args'], root, waiting['state'])
    receipts = [runner.read(path) for path in (root / 'repair-requests').glob('*.receipt.json')]
    assert {receipt['status'] for receipt in receipts} == {'accepted', 'rejected'}
    rejected = next(receipt for receipt in receipts if receipt['status'] == 'rejected')
    assert 'JSONDecodeError' in rejected['error']
    assert Path(rejected['request']).read_text() == '{invalid JSON'
    assert len(launches) == 1


def test_unsafe_repair_amendment_rejected_by_current_runtime_validation(waiting, monkeypatch):
    def reject(*args, **kwargs):
        raise ValueError('native configuration protections changed')
    monkeypatch.setattr(r1, 'read_freeze', reject)
    with pytest.raises(ValueError, match='protections changed'):
        waiting['runner'].repair_request(waiting['args'], waiting['root'], waiting['state'], waiting['request'])


@pytest.mark.parametrize('damage', ['complete', 'running', 'exit', 'unknown-usage', 'missing-trace', 'missing-source'])
def test_complete_or_incomplete_execution_never_enters_wait(waiting, damage):
    runner, root = waiting['runner'], waiting['root']
    index = runner.read(root / 'execution-index.json')
    entry = index['runs'][-1]
    observer = Path(entry['archive']) / 'observer'
    if damage == 'complete':
        index['status'] = 'complete'
    elif damage in {'running', 'exit'}:
        entry['execution'].update(status='running' if damage == 'running' else 'closed', exit_code=1)
        write_json(observer / 'execution.json', entry['execution'])
    elif damage == 'unknown-usage':
        qualification = runner.read(observer / 'qualification/result.json')
        qualification['accounting'] = {'usage_status': 'unknown', 'usage': None}
        write_json(observer / 'qualification/result.json', qualification)
    elif damage == 'missing-trace':
        (observer / 'qualification/native-rollout.jsonl').unlink()
    elif damage == 'missing-source':
        (observer / 'qualification/source-after.json').unlink()
    write_json(root / 'execution-index.json', index)
    with pytest.raises(ValueError):
        runner.repair_wait_state(waiting['args'], root, waiting['frozen'], waiting['failure'])
    assert not (root / 'repair-wait.json').exists()


def cli(waiting):
    return ['--freeze', str(waiting['freeze']), '--gate', str(waiting['gate']),
            '--amendment', str(waiting['amendment']), '--output-root', str(waiting['root']), '--resume']


def test_main_defaults_do_not_read_or_wait_for_repair(waiting, monkeypatch):
    runner = waiting['runner']
    expected = {'status': 'blocked', 'blocker': 'ordinary retained failure'}
    monkeypatch.setattr(runner, 'run', lambda *a, **k: expected)
    monkeypatch.setattr(r1, 'read_freeze', lambda *a, **k: pytest.fail('extra freeze validation in default main'))
    monkeypatch.setattr(runner, 'wait_for_repair', lambda *a, **k: pytest.fail('default must not wait'))
    assert runner.main(cli(waiting)) == expected


def test_main_complete_does_not_wait(waiting, monkeypatch):
    runner = waiting['runner']
    monkeypatch.setattr(runner, 'run', lambda *a, **k: {'status': 'complete'})
    monkeypatch.setattr(runner, 'wait_for_repair', lambda *a, **k: pytest.fail('completed pilot must stop'))
    assert runner.main(cli(waiting) + ['--wait-for-repair']) == {'status': 'complete'}


def test_main_incomplete_native_result_does_not_wait(waiting, monkeypatch):
    runner, root = waiting['runner'], waiting['root']
    index = runner.read(root / 'execution-index.json')
    index['runs'][-1]['execution']['status'] = 'running'
    write_json(root / 'execution-index.json', index)
    result = {'status': 'blocked', 'blocker': 'native session incomplete'}
    monkeypatch.setattr(runner, 'run', lambda *a, **k: result)
    monkeypatch.setattr(runner, 'wait_for_repair', lambda *a, **k: pytest.fail('incomplete execution must stop'))
    assert runner.main(cli(waiting) + ['--wait-for-repair']) == result
    assert not any(waiting['calls'].values())


def test_main_recovery_exception_waits_and_preserves_failure(waiting, monkeypatch):
    runner = waiting['runner']
    def recover(*a, **k):
        raise RuntimeError('reader recovery failed')
    monkeypatch.setattr(runner, 'run', recover)
    seen = []
    def wait(args, root, state):
        seen.append(state)
        return {'status': 'blocked', 'stage': 'test wait'}
    monkeypatch.setattr(runner, 'wait_for_repair', wait)
    assert runner.main(cli(waiting) + ['--wait-for-repair'])['stage'] == 'test wait'
    assert 'reader recovery failed' in seen[0]['diagnostics']['original_failure']['error']
    assert seen[0]['diagnostics']['evidence_error'] == 'original observer reader failed'


def test_main_unsafe_initial_configuration_never_waits(waiting, monkeypatch):
    runner = waiting['runner']
    monkeypatch.setattr(runner, 'wait_for_repair', lambda *a, **k: pytest.fail('unsafe configuration must stop'))
    def reject(*a, **k):
        raise ValueError('unsafe configuration')
    monkeypatch.setattr(r1, 'read_freeze', reject)
    with pytest.raises(ValueError, match='unsafe configuration'):
        runner.main(cli(waiting) + ['--wait-for-repair'])


@pytest.mark.parametrize('flags', [[], ['--preflight-only'], ['--check-only'], ['--reprocess'], ['--background']])
def test_wait_flag_requires_resume_and_rejects_other_modes(waiting, flags):
    args = cli(waiting)
    if not flags:
        args.remove('--resume')
    with pytest.raises(SystemExit) as stopped:
        waiting['runner'].main(args + flags + ['--wait-for-repair'])
    assert stopped.value.code == 2
