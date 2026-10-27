"""Sequential frozen native pilot with validated, non-destructive resumption."""
import argparse
import json
import os
from pathlib import Path
import plistlib
import shutil
import subprocess
import sys
import tempfile
import traceback
import uuid

from benchmarks.complete_work import availability, r0, r1
from benchmarks.complete_work.evaluate import verify_snapshot, write_json


def read(path):
    return json.loads(Path(path).read_text())


def require(condition, message):
    if not condition:
        raise ValueError(message)


def validate_prefix(index, frozen, root, verified):
    """Skip only completed assignments bound to retained, independently graded bytes."""
    require(index.get('freeze_sha256') == frozen['freeze_sha256'], 'index freeze differs')
    require(index.get('availability_gate') == verified, 'index availability gate differs')
    runs = index.get('runs')
    require(isinstance(runs, list) and len(runs) <= len(frozen['schedule']), 'invalid retained prefix')
    run_root = Path(index['run_root']).resolve(strict=True)
    threads = set(verified['threads'])
    for entry, scheduled in zip(runs, frozen['schedule']):
        run_id = scheduled['run_id']
        require(entry.get('run_id') == run_id, 'retained prefix differs from frozen schedule')
        execution, result = entry.get('execution', {}), entry.get('evaluation', {})
        thread = execution.get('thread_id')
        require(execution.get('status') == 'closed' and execution.get('exit_code') == 0,
                'retained attempt did not close successfully')
        require(isinstance(thread, str) and thread and thread not in threads, 'missing or duplicate retained session')
        threads.add(thread)
        require(execution.get('run_id') == run_id and execution.get('freeze_sha256') == frozen['freeze_sha256'],
                'retained execution identity differs')
        require(result.get('qualification_status') == 'qualified_observations'
                and result.get('accounting', {}).get('usage_status') == 'known'
                and result.get('accounting', {}).get('usage') is not None,
                'retained evidence is unqualified or usage is unknown')
        require(type(result.get('correct')) is bool and entry.get('replay_matches') is True,
                'retained independent grade/replay is unavailable')
        for key, expected in {'run_id': run_id, 'thread_id': thread,
                              'freeze_sha256': frozen['freeze_sha256'],
                              'condition': scheduled['condition']}.items():
            require(result.get(key) == expected, f'retained result {key} differs')
        result_path = Path(entry['evaluation_result'])
        require(r0.digest(result_path) == entry['evaluation_result_sha256'] and read(result_path) == result,
                'retained evaluation bytes differ')
        archive = root / 'archived-runs' / run_id
        require(Path(entry['archive']).resolve() == archive.resolve(strict=True), 'retained archive differs')
        observer = archive / 'observer'
        config = Path(entry['config'])
        expected_observer = run_root / run_id / 'observer'
        workspace = run_root / run_id / 'workspace'
        require(config.resolve(strict=True) == expected_observer / 'run.json', 'retained config is outside assigned run')
        archived_config = observer / 'run.json'
        require(r0.digest(config) == r0.digest(archived_config), 'original and archived assignment differ')
        manifest = read(archived_config)
        require(manifest.get('run_id') == run_id and manifest.get('permission_overrides') == {},
                'retained assignment identity or native permissions differ')
        require(Path(manifest['workspace']).resolve() == workspace and Path(manifest['observer']).resolve() == expected_observer,
                'retained workspace or store assignment differs')
        require(manifest['r1']['run_id'] == run_id and manifest['r1']['task'] == scheduled['task']
                and manifest['r1']['condition'] == scheduled['condition'], 'retained condition differs')
        require(manifest['conditions']['freeze_sha256'] == frozen['freeze_sha256']
                and manifest['r1']['argv'] == r1.command(frozen, scheduled['condition'], workspace, expected_observer),
                'retained invocation or condition-local store differs')
        require(manifest['r1'].get('availability_gate') == verified
                and execution.get('availability_gate') == verified, 'retained availability gate differs')
        require(read(observer / 'execution.json') == execution, 'archived execution differs')
        original_qualification = read(observer / 'qualification/result.json')
        trace = observer / 'qualification/native-rollout.jsonl'
        with trace.open() as stream:
            metadata = json.loads(stream.readline())
        require(metadata.get('type') == 'session_meta' and metadata.get('payload', {}).get('id') == thread,
                'archived native session differs')
        require(original_qualification.get('run_id') == run_id and original_qualification.get('thread_id') == thread
                and original_qualification.get('config_sha256') == r0.digest(archived_config)
                and original_qualification.get('native_trace_sha256') == r0.digest(trace),
                'archived qualification bindings differ')
        treatment = {'status': 'verified', **availability.audit_catalog(
            trace, frozen['conditions'][scheduled['condition']]['tools'])}
        require(result.get('treatment_validity') == treatment
                and read(observer / 'treatment.json') == treatment, 'retained tool catalog is unverified or differs')
        qualified_path = Path(entry['qualification_result'])
        require(r0.digest(qualified_path) == entry['qualification_result_sha256'], 'corrected qualification bytes differ')
        qualified = read(qualified_path)
        require(qualified.get('status') == 'qualified_observations'
                and qualified.get('run_id') == run_id and qualified.get('thread_id') == thread
                and qualified.get('config_sha256') == r0.digest(archived_config)
                and qualified.get('native_trace_sha256') == r0.digest(trace)
                and qualified.get('accounting') == result['accounting'], 'corrected native qualification differs')
        replay_path = Path(entry['replay_result'])
        require(r0.digest(replay_path) == entry['replay_result_sha256'], 'retained replay bytes differ')
        replay = read(replay_path)
        require(all(replay.get(key) == result.get(key) for key in
                    ['run_id', 'source_identity', 'oracle_sha256', 'correct', 'changes', 'unexpected_changes']),
                'retained independent replay differs')
        task = next(task for task in frozen['tasks'] if task['id'] == scheduled['task'])
        before = read(observer / 'source-before.json')
        after = read(observer / 'qualification/source-after.json')
        verify_snapshot(before, task['source_identity'])
        verify_snapshot(after, result['source_identity'])
        require(original_qualification.get('source_before') == before['sha256']
                and original_qualification.get('source_after') == after['sha256']
                and qualified.get('source_before') == before['sha256']
                and qualified.get('source_after') == after['sha256']
                and result.get('oracle_sha256') == task['oracle_sha256'], 'retained source/oracle bindings differ')
    # A partial or failed pending attempt cannot be silently restarted.
    for scheduled in frozen['schedule'][len(runs):]:
        run_id = scheduled['run_id']
        require(not (run_root / run_id).exists() and not (root / 'archived-runs' / run_id).exists(),
                'pending assignment already attempted or archived')
    archive_names = {p.name for p in (root / 'archived-runs').iterdir()} if (root / 'archived-runs').exists() else set()
    require(archive_names == {entry['run_id'] for entry in runs},
            'archive contains assignments outside retained prefix')
    return run_root


def run(freeze, gate, amendment, root, *, resume=False, check_only=False,
        availability_gate: Path | None = None):
    frozen = r1.read_freeze(freeze, amendment=amendment)
    require(read(gate).get('status') == 'passed', 'deterministic gate must pass before execution')
    availability_gate = availability_gate if availability_gate is not None else root / 'availability/gate.json'
    verified = r1.require_availability(frozen, availability_gate)
    require(r0.digest(gate) == verified['deterministic_gate_sha256'],
            'availability gate belongs to another deterministic gate')
    index_path = root / 'execution-index.json'
    if resume:
        require(index_path.is_file(), 'resume requires retained execution index')
        index = read(index_path)
        run_root = validate_prefix(index, frozen, root, verified)
    else:
        require(not index_path.exists() and not (root / 'archived-runs').exists(),
                'existing execution index/archive requires --resume')
        index = {'freeze_sha256': frozen['freeze_sha256'], 'availability_gate': verified,
                 'runs': [], 'status': 'running'}
        run_root = None
    pending = frozen['schedule'][len(index['runs']):]
    if check_only:
        return {'status': 'checked', 'next_run_id': pending[0]['run_id'] if pending else None,
                'pending': len(pending), 'retained': len(index['runs'])}
    if run_root is None:
        run_root = Path(tempfile.mkdtemp(prefix='loci-r1-native-', dir='/private/tmp'))
        index['run_root'] = str(run_root)
    index['status'] = 'running'
    index.pop('blocker_run', None)
    write_json(index_path, index)
    for scheduled in pending:
        run_id = scheduled['run_id']
        manifest = r1.prepare(freeze, run_id, run_root / run_id, amendment=amendment,
                              availability_gate=availability_gate)
        config = Path(manifest['observer']) / 'run.json'
        entry = {'run_id': run_id, 'config': str(config)}
        result = None
        try:
            execution = r1.execute(config, gate, amendment=amendment, availability_gate=availability_gate)
            entry['execution'] = execution
            index['runs'].append(entry)
            write_json(index_path, index)
            print(json.dumps({'run_id': run_id, 'execution_status': execution['status'],
                              'thread_id': execution['thread_id']}), flush=True)
            matches = (list((Path.home() / '.codex/sessions').rglob('*' + execution['thread_id'] + '.jsonl'))
                       if execution['thread_id'] else [])
            require(len(matches) == 1, 'unique native rollout unavailable')
            result = r1.evaluate(config, matches[0], execution['thread_id'], amendment=amendment)
            entry['evaluation'] = result
            replay = r1.replay(config, Path(manifest['observer']) / 'replay')
            entry['replay_matches'] = all(replay[k] == result[k] for k in
                                         ['source_identity', 'oracle_sha256', 'correct', 'changes', 'unexpected_changes'])
            require(entry['replay_matches'], 'independent replay differs')
            print(json.dumps({'run_id': run_id, 'correct': result['correct'],
                              'qualification': result['qualification_status'],
                              'usage': result['accounting']['usage_status']}), flush=True)
        except Exception as exc:
            entry['evidence_error'] = f'{type(exc).__name__}: {exc}'
            if not index['runs'] or index['runs'][-1] is not entry:
                execution_path = Path(manifest['observer']) / 'execution.json'
                entry['execution'] = read(execution_path) if execution_path.exists() else {'status': 'execution_exception'}
                index['runs'].append(entry)
        archive = root / 'archived-runs' / run_id
        try:
            archive.parent.mkdir(exist_ok=True)
            shutil.copytree(run_root / run_id, archive)
            entry['archive'] = str(archive)
            for label, relative in [('evaluation', 'evaluation/result.json'),
                                    ('qualification', 'qualification/result.json'), ('replay', 'replay/oracle.json')]:
                result_path = archive / 'observer' / relative
                if result_path.exists():
                    entry[label + '_result'] = str(result_path)
                    entry[label + '_result_sha256'] = r0.digest(result_path)
        except Exception as exc:
            entry['archive_error'] = f'{type(exc).__name__}: {exc}'
        # Wrong answers remain valid outcomes. Missing native/accounting/archive
        # evidence stops the schedule, without replacing the failed assignment.
        if (entry.get('evidence_error') or entry.get('archive_error')
                or entry['execution'].get('status') != 'closed' or result is None
                or result['qualification_status'] != 'qualified_observations'
                or result['accounting']['usage_status'] != 'known'):
            index['status'] = 'blocked'
            index['blocker_run'] = run_id
            write_json(index_path, index)
            break
        write_json(index_path, index)
    else:
        index['status'] = 'complete'
        write_json(index_path, index)
    outcome = {'status': index['status'], 'attempted': len(index['runs']),
               'scheduled': len(frozen['schedule']), 'run_root': str(run_root)}
    if index['status'] == 'blocked':
        failed = index['runs'][-1]
        outcome['blocker'] = {key: failed[key] for key in
                              ('run_id', 'evidence_error', 'archive_error', 'archive') if key in failed}
        if failed.get('evaluation'):
            outcome['blocker']['qualification_status'] = failed['evaluation'].get('qualification_status')
            outcome['blocker']['usage_status'] = failed['evaluation'].get('accounting', {}).get('usage_status')
    return outcome


def background(args, root):
    """Submit this runner once to the normal macOS user host; never fork Codex here."""
    frozen = r1.read_freeze(args.freeze, amendment=args.amendment)
    if not args.preflight_only:
        run(args.freeze, args.gate, args.amendment, root, resume=args.resume, check_only=True)
    elif (root / 'availability/gate.json').exists():
        r1.require_availability(frozen, root / 'availability/gate.json')
    folder = root.resolve() / 'background'
    folder.mkdir(parents=True, exist_ok=False)
    label = 'loci.r1.' + uuid.uuid4().hex
    argv = [sys.executable, '-u', str(Path(__file__).resolve()),
            '--freeze', str(args.freeze.resolve()), '--gate', str(args.gate.resolve()),
            '--output-root', str(root.resolve())]
    if args.amendment:
        argv += ['--amendment', str(args.amendment.resolve())]
    for flag in ('resume', 'preflight_only'):
        if getattr(args, flag):
            argv.append('--' + flag.replace('_', '-'))
    checkout = Path(__file__).resolve().parents[2]
    job = {'Label': label, 'ProgramArguments': argv, 'WorkingDirectory': str(checkout),
           'RunAtLoad': True, 'KeepAlive': False,
           'EnvironmentVariables': {'PYTHONPATH': str(checkout / 'src') + ':' + str(checkout),
                                    'PATH': os.environ.get('PATH', '/usr/bin:/bin:/usr/sbin:/sbin')},
           'StandardOutPath': str(folder / 'stdout.jsonl'), 'StandardErrorPath': str(folder / 'stderr.log')}
    descriptor = folder / 'job.plist'
    descriptor.write_bytes(plistlib.dumps(job))
    result = {'status': 'submitting', 'label': label, 'domain': f'gui/{os.getuid()}',
              'descriptor': str(descriptor), 'freeze_sha256': frozen['freeze_sha256'],
              'stdout': job['StandardOutPath'], 'stderr': job['StandardErrorPath'],
              'native_protections': 'unchanged; every child still undergoes native qualification'}
    write_json(folder / 'submission.json', result)
    try:
        submitted = subprocess.run(['/bin/launchctl', 'bootstrap', result['domain'], str(descriptor)],
                                   capture_output=True, text=True, check=False)
        result.update(status='submitted' if submitted.returncode == 0 else 'blocked',
                      exit_code=submitted.returncode, host_stdout=submitted.stdout, host_stderr=submitted.stderr)
    except OSError as exc:
        result.update(status='blocked', error=f'{type(exc).__name__}: {exc}')
    write_json(folder / 'submission.json', result)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--freeze', type=Path, required=True)
    parser.add_argument('--gate', type=Path, required=True)
    parser.add_argument('--amendment', type=Path)
    parser.add_argument('--output-root', type=Path)
    parser.add_argument('--preflight-only', action='store_true')
    parser.add_argument('--resume', action='store_true')
    parser.add_argument('--check-only', action='store_true')
    parser.add_argument('--background', action='store_true')
    args = parser.parse_args(argv)
    root = args.output_root if args.output_root is not None else args.freeze.parent
    if args.preflight_only and (args.check_only or args.resume):
        parser.error('--preflight-only cannot be combined with --check-only or --resume')
    if args.background:
        if args.check_only:
            parser.error('--background cannot be combined with --check-only')
        result = background(args, root)
        print(json.dumps(result), flush=True)
        return result
    if not args.check_only and not args.resume:
        try:
            preflight = r1.preflight(args.freeze, args.gate, root / 'availability', amendment=args.amendment)
        except Exception as exc:
            root.mkdir(parents=True, exist_ok=True)
            rejected = {'status': 'blocked', 'stage': 'native_preflight', 'measured': False,
                        'error': f'{type(exc).__name__}: {exc}', 'traceback': traceback.format_exc(),
                        'freeze': str(args.freeze.resolve())}
            with tempfile.NamedTemporaryFile(mode='w', prefix='preflight-rejection-', suffix='.json',
                                             dir=root, delete=False) as stream:
                json.dump(rejected, stream, indent=2)
                evidence = stream.name
            preflight = {key: value for key, value in rejected.items() if key != 'traceback'}
            preflight['evidence'] = evidence
        if args.preflight_only or preflight.get('status') != 'passed':
            print(json.dumps(preflight), flush=True)
            return preflight
    result = run(args.freeze, args.gate, args.amendment, root,
                 resume=args.resume, check_only=args.check_only)
    print(json.dumps(result), flush=True)
    return result


if __name__ == '__main__':
    outcome = main()
    raise SystemExit(0 if outcome['status'] in {'complete', 'checked', 'passed', 'submitted'} else 1)
