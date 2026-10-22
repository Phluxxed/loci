"""Exercise real isolated execution and retained replay, without inference."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

from benchmarks.architecture import ROOT, run_process, usage, verify
from benchmarks.typescript_context_corpus import load_corpus


def small_suite(destination: Path) -> Path:
    root = ROOT / 'benchmarks/corpora/typescript-context-v1'
    corpus = load_corpus(root)
    case = next(c for c in corpus['cases'] if c['id'] == 'imported_interface')
    corpus.pop('_root')
    corpus['cases'] = [case]
    corpus['snapshots'] = {case['snapshot']: corpus['snapshots'][case['snapshot']]}
    destination.mkdir()
    archive = corpus['snapshots'][case['snapshot']]['archive']
    shutil.copyfile(root / archive, destination / archive)
    raw = json.dumps(corpus).encode()
    (destination / 'corpus.json').write_bytes(raw)
    (destination / 'corpus.sha256').write_text(hashlib.sha256(raw).hexdigest())
    return destination


def test_real_comparison_isolated_replay_and_tamper_rejection(tmp_path):
    suite = small_suite(tmp_path / 'suite')
    output = tmp_path / 'comparison'
    existing_worktrees = subprocess.check_output(['git', 'worktree', 'list', '--porcelain'], cwd=ROOT)
    result = subprocess.run([sys.executable, '-B', '-m', 'benchmarks.architecture', 'run',
                             '--output', str(output), '--corpus', str(suite)],
                            cwd=ROOT, capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr + (output / 'result.json').read_text()
    report = json.loads((output / 'result.json').read_text())
    assert report['primary_unchanged']
    assert report['graph_free'] is False
    assert all(r['status'] == 'completed' for r in report['runs'])
    assert len({r['binding']['store_id'] for r in report['runs']}) == 2
    assert len({r['binding']['base_dir'] for r in report['runs']}) == 2
    assert len({r['binding']['namespace'] for r in report['runs']}) == 2
    assert report['comparisons'][0]['regressed_cases'] == ['imported_interface']
    for run in report['runs']:
        assert run['phase_totals']['indexing']['operations'] == 1
        assert run['process_resources']['peak_rss_bytes'] > 0
    assert all(row['exit_code'] == 0 and not Path(row['path']).exists() for row in report['cleanup'])
    assert not (output / '.owned').exists()
    assert subprocess.check_output(['git', 'worktree', 'list', '--porcelain'], cwd=ROOT) == existing_worktrees
    assert verify(output) == 0
    packet = next((output / 'artifacts').rglob('packets/*.json'))
    packet.write_text('[]')
    with pytest.raises(ValueError, match='inventory/hash mismatch'):
        verify(output)
    repeat = subprocess.run([sys.executable, '-B', '-m', 'benchmarks.architecture', 'run',
                             '--output', str(output), '--corpus', str(suite)],
                            cwd=ROOT, capture_output=True, text=True)
    assert repeat.returncode != 0


def test_failed_worker_is_retained_and_not_a_measurement(tmp_path):
    log = tmp_path / 'process.log'
    result = run_process([sys.executable, '-c', 'raise RuntimeError("negative control")'],
                         tmp_path, dict(__import__('os').environ), log)
    assert result['exit_code'] != 0
    assert 'negative control' in log.read_text()
    assert result['elapsed_ns'] > 0
    assert usage()['peak_rss_bytes'] > 0


def test_invalid_fixture_is_retained_and_owned_checkouts_are_cleaned(tmp_path, monkeypatch):
    from argparse import Namespace
    from benchmarks import architecture

    suite = small_suite(tmp_path / 'suite')
    output = tmp_path / 'invalid'
    original = architecture.run_process

    def corrupt_after_execution(command, cwd, env, log):
        result = original(command, cwd, env, log)
        config = json.loads(Path(command[-1]).read_text())
        fixture = Path(next(iter(config['snapshots'].values())))
        (fixture / 'unexpected.py').write_text('corrupted = True\n')
        return result

    monkeypatch.setattr(architecture, 'run_process', corrupt_after_execution)
    args = Namespace(repo=str(ROOT), output=str(output), corpus=[str(suite)], repetitions=1,
                     control_ref='HEAD', variant_ref='HEAD', control_enrichment='on', variant_enrichment='off')
    assert architecture.run(args) == 1
    result = json.loads((output / 'result.json').read_text())
    assert result['status'] == 'invalid'
    assert 'snapshot inventory or content differs' in result['error']
    assert result['primary_unchanged']
    assert not (output / '.owned').exists()
    assert all(not Path(row['path']).exists() for row in result['cleanup'])
    with pytest.raises(ValueError, match='invalid'):
        verify(output)


def test_no_worker_receipt_cannot_become_success(tmp_path, monkeypatch):
    from argparse import Namespace
    from benchmarks import architecture

    suite = small_suite(tmp_path / 'suite')
    output = tmp_path / 'failed'
    monkeypatch.setattr(architecture, 'run_process', lambda *args: {'exit_code': 17, 'elapsed_ns': 1})
    args = Namespace(repo=str(ROOT), output=str(output), corpus=[str(suite)], repetitions=1,
                     control_ref='HEAD', variant_ref='HEAD', control_enrichment='on', variant_enrichment='off')
    assert architecture.run(args) == 1
    result = json.loads((output / 'result.json').read_text())
    assert result['status'] == 'failed'
    assert len(result['runs']) == 2
    assert all(row['status'] == 'failed' and 'phase_totals' not in row for row in result['runs'])
    assert result['comparisons'][0]['status'] == 'unavailable'


def test_empty_assignment_cannot_vacuously_pass(tmp_path):
    from argparse import Namespace
    from benchmarks import architecture

    suite = small_suite(tmp_path / 'suite')
    corpus = json.loads((suite / 'corpus.json').read_text())
    corpus['cases'] = []
    raw = json.dumps(corpus).encode()
    (suite / 'corpus.json').write_bytes(raw)
    (suite / 'corpus.sha256').write_text(hashlib.sha256(raw).hexdigest())
    output = tmp_path / 'empty'
    args = Namespace(repo=str(ROOT), output=str(output), corpus=[str(suite)], repetitions=1,
                     control_ref='HEAD', variant_ref='HEAD', control_enrichment='on', variant_enrichment='off')
    assert architecture.run(args) == 1
    result = json.loads((output / 'result.json').read_text())
    assert result['status'] == 'invalid'
    assert 'at least one case' in result['error']
    assert result['runs'] == []


def test_interruption_remains_incomplete_and_cleans_only_owned_resources(tmp_path, monkeypatch):
    from argparse import Namespace
    from benchmarks import architecture

    suite = small_suite(tmp_path / 'suite')
    output = tmp_path / 'interrupted'
    def interrupt(*args):
        raise KeyboardInterrupt
    monkeypatch.setattr(architecture, 'run_process', interrupt)
    args = Namespace(repo=str(ROOT), output=str(output), corpus=[str(suite)], repetitions=1,
                     control_ref='HEAD', variant_ref='HEAD', control_enrichment='on', variant_enrichment='off')
    assert architecture.run(args) == 1
    result = json.loads((output / 'result.json').read_text())
    assert result['status'] == 'incomplete'
    assert result['primary_unchanged']
    assert all(not Path(row['path']).exists() for row in result['cleanup'])
    assert not (output / '.owned').exists()
