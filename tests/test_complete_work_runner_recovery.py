"""Runner recovery never substitutes native work for retained evidence."""
import json
from pathlib import Path
import shutil
import subprocess

import pytest

from benchmarks.complete_work import r1
from benchmarks.complete_work.evaluate import write_json
from tests.test_complete_work_r1_resume import pilot


def file_bytes(root):
    return {str(p.relative_to(root)): p.read_bytes() for p in root.rglob('*') if p.is_file()}


def test_archives_remain_authoritative_after_live_run_root_is_deleted(pilot):
    first = pilot['retain'](0)
    pilot['save']([first])
    shutil.rmtree(pilot['run_root'])
    assert pilot['run'](resume=True, check_only=True)['retained'] == 1
    result = pilot['run'](resume=True)
    assert result['status'] == 'complete' and result['attempted'] == 16
    assert len(pilot['calls']['execute']) == 15


def test_changed_optional_live_config_is_still_rejected(pilot):
    first = pilot['retain'](0)
    pilot['save']([first])
    Path(first['config']).write_text('{}')
    with pytest.raises(ValueError, match='original and archived assignment differ'):
        pilot['run'](resume=True, check_only=True)
    assert not pilot['calls']['execute']


def test_closed_tail_reprocesses_without_native_and_keeps_original_failure(pilot, monkeypatch):
    first = pilot['retain'](0)
    first['evidence_error'] = 'original observer failure'
    first.pop('evaluation')
    pilot['save']([first])
    original_index = (pilot['root'] / 'execution-index.json').read_bytes()
    archive = Path(first['archive'])
    original_archive = file_bytes(archive)
    shutil.rmtree(pilot['run_root'])
    seen = []

    def evaluate(config, trace, thread, *, amendment, retained_observer, output):
        seen.append(('evaluate', config, trace, thread))
        assert config == archive / 'observer/run.json'
        assert retained_observer == archive / 'observer'
        for relative in ['qualification/result.json', 'treatment.json', 'evaluation/result.json']:
            target = output / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes((retained_observer / relative).read_bytes())
        return json.loads((output / 'evaluation/result.json').read_text())

    def replay(config, destination, *, retained_observer):
        seen.append(('replay', config))
        destination.mkdir(parents=True)
        value = json.loads((retained_observer / 'replay/oracle.json').read_text())
        write_json(destination / 'oracle.json', value)
        return value

    monkeypatch.setattr(r1, 'evaluate', evaluate)
    monkeypatch.setattr(r1, 'replay', replay)
    runner = pilot['runner']
    verified = r1.require_availability(pilot['frozen'], pilot['availability_gate'])
    pilot['frozen']['schedule'] = pilot['frozen']['schedule'][:1]
    assert pilot['run'](resume=True)['status'] == 'complete'
    recovered = runner.read(pilot['root'] / 'execution-index.json')
    assert [item[0] for item in seen] == ['evaluate', 'replay']
    assert not pilot['calls']['execute']
    assert file_bytes(archive) == original_archive
    entry = recovered['runs'][0]
    checkpoint = Path(entry['recovery']['original_index'])
    assert checkpoint.read_bytes() == original_index
    assert 'original observer failure' in checkpoint.read_text()
    assert 'evidence_error' not in entry
    assert Path(entry['treatment_result']).is_relative_to(pilot['root'] / 'reprocessed')
    assert runner.validate_prefix(recovered, pilot['frozen'], pilot['root'], verified) == pilot['run_root']


@pytest.mark.parametrize('missing', ['qualification/result.json', 'qualification/native-rollout.jsonl',
                                    'qualification/source-after.json'])
def test_incomplete_closed_tail_is_never_relaunched_or_reprocessed(pilot, monkeypatch, missing):
    first = pilot['retain'](0)
    first['evidence_error'] = 'observer failed'
    pilot['save']([first])
    (Path(first['archive']) / 'observer' / missing).unlink()
    before = file_bytes(pilot['root'])
    monkeypatch.setattr(r1, 'evaluate', lambda *a, **k: pytest.fail('incomplete evidence must not be processed'))
    with pytest.raises(ValueError, match='missing archived'):
        pilot['run'](resume=True)
    assert file_bytes(pilot['root']) == before
    assert not pilot['calls']['execute']


def test_prepare_failure_is_indexed_and_original_error_survives_archive_failure(pilot, monkeypatch):
    def prepare(*args, **kwargs):
        raise RuntimeError('source export unavailable')
    monkeypatch.setattr(r1, 'prepare', prepare)
    result = pilot['run']()
    assert result['status'] == 'blocked' and result['attempted'] == 1
    entry = pilot['runner'].read(pilot['root'] / 'execution-index.json')['runs'][0]
    assert 'source export unavailable' in entry['evidence_error']
    assert entry['archive_error'] and entry['execution']['status'] == 'execution_exception'
    assert not pilot['calls']['execute']
    with pytest.raises(ValueError, match='did not close successfully'):
        pilot['run'](resume=True)


def test_background_fresh_handoff_validates_without_requiring_a_probe_gate(pilot, monkeypatch):
    pilot['availability_gate'].unlink()
    seen = []
    def submit(argv, **kwargs):
        assert argv[:2] == ['/bin/launchctl', 'bootstrap']
        seen.append(argv)
        return subprocess.CompletedProcess(argv, 0, '', '')
    monkeypatch.setattr(subprocess, 'run', submit)
    result = pilot['runner'].main(['--freeze', str(pilot['freeze']), '--gate', str(pilot['gate']),
                                  '--amendment', str(pilot['amendment']), '--output-root', str(pilot['root']),
                                  '--background'])
    assert result['status'] == 'submitted' and len(seen) == 1
    assert not pilot['calls']['execute'] and not (pilot['root'] / 'execution-index.json').exists()


def test_reprocess_cli_calls_only_retained_availability_reader(pilot, monkeypatch):
    seen = []
    def reprocess(freeze, deterministic, source, destination, *, amendment):
        seen.append((freeze, deterministic, source, destination, amendment))
        return {'status': 'passed', 'gate_path': str(destination / 'gate.json')}
    monkeypatch.setattr(r1, 'reprocess_availability', reprocess, raising=False)
    monkeypatch.setattr(r1, 'preflight', lambda *a, **k: pytest.fail('reader recovery must not probe'))
    result = pilot['runner'].main(['--freeze', str(pilot['freeze']), '--gate', str(pilot['gate']),
                                  '--amendment', str(pilot['amendment']), '--output-root', str(pilot['root']),
                                  '--reprocess'])
    assert result['status'] == 'passed' and len(seen) == 1
    assert seen[0][:3] == (pilot['freeze'], pilot['gate'], pilot['availability_gate'])
    assert not pilot['calls']['execute'] and not (pilot['root'] / 'execution-index.json').exists()


def test_unknown_original_qualification_blocks_before_processing(pilot, monkeypatch):
    first = pilot['retain'](0)
    first['evidence_error'] = 'original failure'
    pilot['save']([first])
    qualified = Path(first['archive']) / 'observer/qualification/result.json'
    value = json.loads(qualified.read_text())
    value['accounting']['usage_status'] = 'unknown'
    write_json(qualified, value)
    before = file_bytes(pilot['root'])
    monkeypatch.setattr(r1, 'evaluate', lambda *a, **k: pytest.fail('unknown original cannot be processed'))
    with pytest.raises(ValueError, match='incomplete or unknown original qualification'):
        pilot['run'](resume=True)
    assert file_bytes(pilot['root']) == before and not pilot['calls']['execute']


def test_failed_reprocessing_keeps_index_archive_and_both_failures(pilot, monkeypatch):
    first = pilot['retain'](0)
    first['evidence_error'] = 'original observer failure'
    pilot['save']([first])
    index_path = pilot['root'] / 'execution-index.json'
    before_index = index_path.read_bytes()
    archive = Path(first['archive'])
    before_archive = file_bytes(archive)
    def fail(*args, **kwargs):
        raise ValueError('captured catalog still differs')
    monkeypatch.setattr(r1, 'evaluate', fail)
    with pytest.raises(ValueError, match='no native retry.*captured catalog still differs'):
        pilot['run'](resume=True)
    assert index_path.read_bytes() == before_index and file_bytes(archive) == before_archive
    checkpoints = list((pilot['root'] / 'index-history').glob('*.json'))
    assert len(checkpoints) == 1 and checkpoints[0].read_bytes() == before_index
    errors = list((pilot['root'] / 'reprocessed').rglob('recovery-error.json'))
    assert len(errors) == 1 and 'captured catalog still differs' in errors[0].read_text()
    assert not pilot['calls']['execute']


def test_malformed_execution_marker_does_not_replace_original_failure(pilot, monkeypatch):
    def prepare(freeze, run_id, destination, **kwargs):
        observer = destination / 'observer'
        observer.mkdir(parents=True)
        (observer / 'execution.json').write_text('{')
        raise RuntimeError('original preparation failure')
    monkeypatch.setattr(r1, 'prepare', prepare)
    result = pilot['run']()
    assert result['status'] == 'blocked'
    entry = pilot['runner'].read(pilot['root'] / 'execution-index.json')['runs'][0]
    assert 'original preparation failure' in entry['evidence_error']
    assert 'JSONDecodeError' in entry['execution_error']
    assert (Path(entry['archive']) / 'observer/execution.json').read_text() == '{'
    assert not pilot['calls']['execute']
