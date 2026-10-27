"""One-shot host dispatch of the existing runner, without a child Codex launch."""
import argparse
from pathlib import Path
import plistlib
import runpy
import subprocess

import pytest


SCRIPT = Path(__file__).resolve().parents[1] / '.scratch/r1-integrated/pilot-execute.py'


@pytest.mark.parametrize('exit_code', [0, 5])
def test_background_submits_exact_runner_and_retains_host_rejection(tmp_path, monkeypatch, exit_code):
    module = runpy.run_path(str(SCRIPT))
    monkeypatch.setattr(module['r1'], 'read_freeze', lambda *a, **k: {'freeze_sha256': 'f' * 64})
    validations = []
    module['background'].__globals__['run'] = lambda *a, **k: validations.append(k)
    calls = []
    def submit(argv, **kwargs):
        calls.append((argv, kwargs))
        return subprocess.CompletedProcess(argv, exit_code, '', 'host rejection' if exit_code else '')
    monkeypatch.setattr(subprocess, 'run', submit)
    args = argparse.Namespace(freeze=tmp_path / 'freeze.json', gate=tmp_path / 'gate.json',
                              amendment=tmp_path / 'amendment.json', resume=True, preflight_only=False)
    result = module['background'](args, tmp_path)
    assert validations == [{'resume': True, 'check_only': True,
                            'availability_gate': tmp_path / 'availability/gate.json'}]
    assert result['status'] == ('submitted' if exit_code == 0 else 'blocked')
    assert len(calls) == 1 and calls[0][0][:2] == ['/bin/launchctl', 'bootstrap']
    assert calls[0][1].get('shell') is None
    job = plistlib.loads((tmp_path / 'background/job.plist').read_bytes())
    argv = job['ProgramArguments']
    assert argv[2] == str(SCRIPT) and '--resume' in argv and '--background' not in argv
    assert not any(x in argv for x in ['--sandbox', '--yolo', '--dangerously-bypass-approvals-and-sandbox'])
    assert job['RunAtLoad'] is True and job['KeepAlive'] is False
    assert set(job['EnvironmentVariables']) == {'PATH', 'PYTHONPATH'}
    assert (tmp_path / 'background/submission.json').is_file()
    with pytest.raises(FileExistsError):
        module['background'](args, tmp_path)
    assert len(calls) == 1


def test_invalid_resume_cannot_submit_a_host_job(tmp_path, monkeypatch):
    module = runpy.run_path(str(SCRIPT))
    monkeypatch.setattr(module['r1'], 'read_freeze', lambda *a, **k: {'freeze_sha256': 'f' * 64})
    def reject(*args, **kwargs):
        raise ValueError('invalid retained prefix')
    module['background'].__globals__['run'] = reject
    monkeypatch.setattr(subprocess, 'run', lambda *a, **k: pytest.fail('host job must not be submitted'))
    args = argparse.Namespace(freeze=tmp_path / 'freeze.json', gate=tmp_path / 'gate.json',
                              amendment=None, resume=True, preflight_only=False)
    with pytest.raises(ValueError, match='invalid retained prefix'):
        module['background'](args, tmp_path)
    assert not (tmp_path / 'background').exists()
