"""Runner recovery never substitutes native work for retained evidence."""
import json
from pathlib import Path
import shutil
import subprocess

import pytest

from benchmarks.complete_work import r0, r1
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


def failed_treatment(pilot, monkeypatch, run_id):
    original = r1.observe_treatment
    def observe(frozen, manifest, trace, verified, **kwargs):
        if manifest['run_id'] == run_id:
            return {'status': 'unqualified', 'code': 'treatment_observation_failed',
                    'error': 'capture program supplied a mismatched SHA constant',
                    'native_trace_sha256': r0.digest(trace)}
        return original(frozen, manifest, trace, verified, **kwargs)
    monkeypatch.setattr(r1, 'observe_treatment', observe)
    return observe


def retain_unqualified(pilot, monkeypatch):
    first = pilot['retain'](0, correct=False)
    observer = Path(first['archive']) / 'observer'
    observe = failed_treatment(pilot, monkeypatch, first['run_id'])
    treatment = observe(pilot['frozen'], pilot['runner'].read(observer / 'run.json'),
                        observer / 'qualification/native-rollout.jsonl', {})
    first['evaluation'].update(treatment_validity=treatment, comparison_status='unqualified')
    write_json(observer / 'evaluation/result.json', first['evaluation'])
    write_json(observer / 'treatment.json', treatment)
    pilot['runner'].record_results(first, observer)
    return first


def test_terminal_unqualified_comparison_retains_false_oracle_and_continues(pilot, monkeypatch):
    first = retain_unqualified(pilot, monkeypatch)
    pilot['save']([first])
    archive_before = file_bytes(Path(first['archive']))
    assert pilot['run'](resume=True)['status'] == 'complete'
    assert len(pilot['calls']['execute']) == 15
    assert first['run_id'] not in pilot['calls']['execute']
    retained = pilot['runner'].read(pilot['root'] / 'execution-index.json')['runs'][0]
    assert retained['evaluation']['correct'] is False
    assert retained['evaluation']['comparison_status'] == 'unqualified'
    assert retained['evaluation']['qualification_status'] == 'qualified_observations'
    assert file_bytes(Path(first['archive'])) == archive_before


def test_new_unqualified_comparison_prints_status_and_continues(pilot, monkeypatch, capsys):
    run_id = pilot['frozen']['schedule'][0]['run_id']
    observe = failed_treatment(pilot, monkeypatch, run_id)
    original_evaluate = r1.evaluate
    def evaluate(config, trace, thread, *, amendment=None):
        result = original_evaluate(config, trace, thread, amendment=amendment)
        if result['run_id'] == run_id:
            treatment = observe(pilot['frozen'], pilot['runner'].read(config), trace, {})
            result.update(correct=False, treatment_validity=treatment, comparison_status='unqualified')
            write_json(config.parent / 'evaluation/result.json', result)
            write_json(config.parent / 'treatment.json', treatment)
        return result
    monkeypatch.setattr(r1, 'evaluate', evaluate)
    pilot['frozen']['schedule'] = pilot['frozen']['schedule'][:2]
    assert pilot['run']()['status'] == 'complete'
    assert len(pilot['calls']['execute']) == 2
    progress = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    graded = next(record for record in progress if record.get('run_id') == run_id and 'correct' in record)
    assert graded['correct'] is False
    assert graded['qualification'] == 'qualified_observations'
    assert graded['comparison_status'] == 'unqualified'


@pytest.mark.parametrize('damage', ['comparison-qualified', 'comparison-missing', 'usage', 'source', 'replay', 'native'])
def test_unqualified_comparison_keeps_all_existing_integrity_guards(pilot, monkeypatch, damage):
    first = retain_unqualified(pilot, monkeypatch)
    observer = Path(first['archive']) / 'observer'
    result = first['evaluation']
    if damage == 'comparison-qualified':
        result['comparison_status'] = 'qualified'
    elif damage == 'comparison-missing':
        result.pop('comparison_status')
    elif damage == 'usage':
        result['accounting']['usage_status'] = 'unknown'
    elif damage == 'source':
        result['source_identity'] = '0' * 64
        replay = pilot['runner'].read(observer / 'replay/oracle.json')
        replay['source_identity'] = result['source_identity']
        write_json(observer / 'replay/oracle.json', replay)
    elif damage == 'replay':
        replay = pilot['runner'].read(observer / 'replay/oracle.json')
        replay['correct'] = True
        write_json(observer / 'replay/oracle.json', replay)
    elif damage == 'native':
        first['execution']['status'] = 'running'
        write_json(observer / 'execution.json', first['execution'])
    write_json(observer / 'evaluation/result.json', result)
    pilot['runner'].record_results(first, observer)
    pilot['save']([first])
    with pytest.raises((ValueError, RuntimeError)):
        pilot['run'](resume=True, check_only=True)
    assert not any(pilot['calls'].values())


def test_closed_failed_tail_recovers_as_unqualified_false_result_without_native_retry(pilot, monkeypatch):
    first = pilot['retain'](0, correct=False)
    first['evidence_error'] = 'old reader rejected unsuccessful capture'
    first.pop('evaluation')
    pilot['save']([first])
    index_path = pilot['root'] / 'execution-index.json'
    original_index = index_path.read_bytes()
    archive = Path(first['archive'])
    original_archive = file_bytes(archive)
    observe = failed_treatment(pilot, monkeypatch, first['run_id'])

    def evaluate(config, trace, thread, *, amendment, retained_observer, output):
        result = pilot['runner'].read(retained_observer / 'evaluation/result.json')
        treatment = observe(pilot['frozen'], pilot['runner'].read(config), trace, {})
        result.update(treatment_validity=treatment, comparison_status='unqualified')
        for relative in ['qualification/result.json', 'evaluation/result.json']:
            target = output / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes((retained_observer / relative).read_bytes())
        write_json(output / 'evaluation/result.json', result)
        write_json(output / 'treatment.json', treatment)
        return result

    def replay(config, destination, *, retained_observer):
        destination.mkdir(parents=True)
        value = pilot['runner'].read(retained_observer / 'replay/oracle.json')
        write_json(destination / 'oracle.json', value)
        return value

    monkeypatch.setattr(r1, 'evaluate', evaluate)
    monkeypatch.setattr(r1, 'replay', replay)
    pilot['frozen']['schedule'] = pilot['frozen']['schedule'][:1]
    assert pilot['run'](resume=True)['status'] == 'complete'
    recovered = pilot['runner'].read(index_path)['runs'][0]
    assert recovered['evaluation']['correct'] is False
    assert recovered['evaluation']['comparison_status'] == 'unqualified'
    assert recovered['evaluation']['qualification_status'] == 'qualified_observations'
    assert Path(recovered['recovery']['original_index']).read_bytes() == original_index
    assert file_bytes(archive) == original_archive
    assert not any(pilot['calls'].values())
