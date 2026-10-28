"""Sequential frozen native pilot with validated, non-destructive resumption."""
import argparse
import copy
import json
import os
from pathlib import Path
import plistlib
import shutil
import subprocess
import sys
import tempfile
import time
import traceback
import uuid

from benchmarks.complete_work import r0, r1
from benchmarks.complete_work.evaluate import verify_snapshot, write_json


def read(path):
    return json.loads(Path(path).read_text())


def require(condition, message):
    if not condition:
        raise ValueError(message)


def validate_prefix(index, frozen, root, verified, *, completed_count=None):
    """Skip only completed assignments bound to retained, independently graded bytes."""
    require(index.get('freeze_sha256') == frozen['freeze_sha256'], 'index freeze differs')
    require(index.get('availability_gate') == verified, 'index availability gate differs')
    runs = index.get('runs')
    require(isinstance(runs, list) and len(runs) <= len(frozen['schedule']), 'invalid retained prefix')
    run_root = Path(index['run_root']).resolve()
    count = len(runs) if completed_count is None else completed_count
    require(count in {len(runs), len(runs) - 1} and count >= 0, 'invalid completed prefix length')
    require(all(entry.get('run_id') == scheduled['run_id']
                for entry, scheduled in zip(runs, frozen['schedule'])),
            'retained prefix differs from frozen schedule')
    threads = set(verified['threads'])
    for entry, scheduled in zip(runs[:count], frozen['schedule']):
        run_id = scheduled['run_id']
        require(entry.get('run_id') == run_id, 'retained prefix differs from frozen schedule')
        execution, result = entry.get('execution', {}), entry.get('evaluation', {})
        require(not entry.get('evidence_error') and not entry.get('archive_error'),
                'retained assignment has an unresolved observer or archive failure')
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
        require(config.resolve() == expected_observer / 'run.json', 'retained config is outside assigned run')
        archived_config = observer / 'run.json'
        if config.exists():
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
        retained = {'retained_observer': observer} if frozen.get('common_context') else {}
        treatment = {'status': 'verified', **r1.audit_treatment(frozen, manifest, trace, verified, **retained)}
        treatment_path = Path(entry.get('treatment_result', observer / 'treatment.json'))
        if 'treatment_result' in entry:
            require(r0.digest(treatment_path) == entry['treatment_result_sha256'], 'retained treatment bytes differ')
        require(result.get('treatment_validity') == treatment
                and read(treatment_path) == treatment, 'retained tool catalog is unverified or differs')
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


def record_results(entry, observer):
    for label, relative in [('evaluation', 'evaluation/result.json'),
                            ('qualification', 'qualification/result.json'),
                            ('replay', 'replay/oracle.json'), ('treatment', 'treatment.json')]:
        path = observer / relative
        if path.is_file():
            entry[label + '_result'] = str(path)
            entry[label + '_result_sha256'] = r0.digest(path)


def recover_tail(index, index_path, frozen, root, verified, amendment):
    """Reprocess a closed observer failure from its immutable archive, never rerun it."""
    runs = index['runs']
    require(runs, 'no retained assignment to reprocess')
    original = runs[-1]
    execution = original.get('execution', {})
    require(execution.get('status') == 'closed' and execution.get('exit_code') == 0,
            'retained attempt did not close successfully; cannot reprocess or rerun')
    validate_prefix(index, frozen, root, verified, completed_count=len(runs) - 1)
    run_id = frozen['schedule'][len(runs) - 1]['run_id']
    archive = root / 'archived-runs' / run_id
    require(Path(original.get('archive', '')).resolve() == archive.resolve() and archive.is_dir(),
            'complete original archive is required for reprocessing')
    observer = archive / 'observer'
    for relative in ('run.json', 'execution.json', 'source-before.json', 'qualification/result.json',
                     'qualification/native-rollout.jsonl', 'qualification/source-after.json'):
        require((observer / relative).is_file(), 'cannot reprocess: missing archived ' + relative)
    require(read(observer / 'execution.json') == execution, 'archived execution differs')
    qualified = read(observer / 'qualification/result.json')
    require(qualified.get('status') == 'qualified_observations'
            and qualified.get('accounting', {}).get('usage_status') == 'known',
            'cannot reprocess incomplete or unknown original qualification')
    threads = set(verified['threads']) | {entry.get('execution', {}).get('thread_id') for entry in runs[:-1]}
    thread = execution.get('thread_id')
    require(isinstance(thread, str) and thread and thread not in threads, 'missing or duplicate retained session')
    config = observer / 'run.json'
    derived = root / 'reprocessed' / run_id / uuid.uuid4().hex
    derived.parent.mkdir(parents=True, exist_ok=True)
    history = root / 'index-history'
    history.mkdir(exist_ok=True)
    checkpoint = history / ('execution-index-' + uuid.uuid4().hex + '.json')
    shutil.copyfile(index_path, checkpoint)
    try:
        result = r1.evaluate(config, observer / 'qualification/native-rollout.jsonl', thread,
                             amendment=amendment, retained_observer=observer, output=derived)
        replay = r1.replay(config, derived / 'replay', retained_observer=observer)
        require(all(replay.get(key) == result.get(key) for key in
                    ('run_id', 'source_identity', 'oracle_sha256', 'correct', 'changes', 'unexpected_changes')),
                'independent replay differs')
        entry = copy.deepcopy(original)
        entry.update(evaluation=result, replay_matches=True,
                     recovery={'original_index': str(checkpoint), 'original_index_sha256': r0.digest(checkpoint)})
        entry.pop('evidence_error', None)
        entry.pop('archive_error', None)
        record_results(entry, derived)
        candidate = copy.deepcopy(index)
        candidate['runs'][-1] = entry
        validate_prefix(candidate, frozen, root, verified)
    except Exception as exc:
        derived.mkdir(parents=True, exist_ok=True)
        write_json(derived / 'recovery-error.json', {'status': 'blocked', 'run_id': run_id,
                   'error': f'{type(exc).__name__}: {exc}', 'original_index': str(checkpoint)})
        raise ValueError(f'retained reprocessing failed; no native retry: {exc}; evidence: {derived}') from exc
    write_json(index_path, candidate)
    return candidate


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
        try:
            run_root = validate_prefix(index, frozen, root, verified)
        except (ValueError, OSError):
            tail = index.get('runs', [])[-1] if index.get('runs') else {}
            if check_only or not tail or not (tail.get('evidence_error') or tail.get('archive_error')
                                            or not tail.get('evaluation')):
                raise
            index = recover_tail(index, index_path, frozen, root, verified, amendment)
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
    run_root.mkdir(parents=True, exist_ok=True)
    index['status'] = 'running'
    index.pop('blocker_run', None)
    write_json(index_path, index)
    for scheduled in pending:
        run_id = scheduled['run_id']
        config = run_root / run_id / 'observer/run.json'
        entry = {'run_id': run_id, 'config': str(config)}
        result = None
        index['runs'].append(entry)
        write_json(index_path, index)
        try:
            manifest = r1.prepare(freeze, run_id, run_root / run_id, amendment=amendment,
                                  availability_gate=availability_gate)
            execution = r1.execute(config, gate, amendment=amendment, availability_gate=availability_gate)
            entry['execution'] = execution
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
            execution_path = config.parent / 'execution.json'
            if 'execution' not in entry:
                entry['execution'] = {'status': 'execution_exception'}
                if execution_path.exists():
                    try:
                        entry['execution'] = read(execution_path)
                    except (OSError, ValueError) as marker_error:
                        entry['execution_error'] = f'{type(marker_error).__name__}: {marker_error}'
        archive = root / 'archived-runs' / run_id
        try:
            archive.parent.mkdir(exist_ok=True)
            shutil.copytree(run_root / run_id, archive)
            entry['archive'] = str(archive)
            record_results(entry, archive / 'observer')
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
    availability_gate = getattr(args, 'availability_gate', None) or root / 'availability/gate.json'
    if args.resume:
        run(args.freeze, args.gate, args.amendment, root, resume=True, check_only=True,
            availability_gate=availability_gate)
    else:
        require(read(args.gate).get('status') == 'passed', 'deterministic gate must pass before execution')
        if availability_gate.exists():
            verified = r1.require_availability(frozen, availability_gate)
            require(r0.digest(args.gate) == verified['deterministic_gate_sha256'],
                    'availability gate belongs to another deterministic gate')
        if not args.preflight_only:
            require(not (root / 'execution-index.json').exists() and not (root / 'archived-runs').exists(),
                    'existing execution index/archive requires --resume')
    folder = root.resolve() / 'background'
    folder.mkdir(parents=True, exist_ok=False)
    label = 'loci.r1.' + uuid.uuid4().hex
    argv = [sys.executable, '-u', str(Path(__file__).resolve()),
            '--freeze', str(args.freeze.resolve()), '--gate', str(args.gate.resolve()),
            '--output-root', str(root.resolve())]
    if args.amendment:
        argv += ['--amendment', str(args.amendment.resolve())]
    if getattr(args, 'availability_gate', None):
        argv += ['--availability-gate', str(args.availability_gate.resolve())]
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


def repair_wait_state(args, root, frozen, failure):
    """Require complete original evidence without using the failing observer reader."""
    index_path = root / 'execution-index.json'
    index = read(index_path)
    runs = index.get('runs', [])
    require(index.get('status') == 'blocked' and runs, 'repair wait requires a blocked assignment')
    require(index.get('freeze_sha256') == frozen['freeze_sha256'], 'index freeze differs')
    require(len(frozen['schedule']) == 16 and len(runs) <= 16,
            'repair wait is limited to the frozen16 pilot')
    require([entry['run_id'] for entry in runs] ==
            [entry['run_id'] for entry in frozen['schedule'][:len(runs)]], 'retained schedule differs')
    tail = runs[-1]
    require(tail.get('evidence_error') and not tail.get('archive_error'),
            'repair wait requires an observer failure with a complete archive')
    execution = tail.get('execution', {})
    require(execution.get('status') == 'closed' and execution.get('exit_code') == 0,
            'repair wait cannot retry incomplete native execution')
    run_id = tail['run_id']
    archive = root / 'archived-runs' / run_id
    require(Path(tail.get('archive', '')).resolve() == archive.resolve() and archive.is_dir(),
            'complete original archive is required for repair wait')
    observer = archive / 'observer'
    for relative in ('run.json', 'execution.json', 'source-before.json', 'qualification/result.json',
                     'qualification/native-rollout.jsonl', 'qualification/source-after.json'):
        require((observer / relative).is_file(), 'repair wait missing archived ' + relative)
    require(read(observer / 'execution.json') == execution, 'archived execution differs')
    manifest = read(observer / 'run.json')
    qualified = read(observer / 'qualification/result.json')
    trace = observer / 'qualification/native-rollout.jsonl'
    with trace.open() as stream:
        metadata = json.loads(stream.readline())
    thread = execution.get('thread_id')
    require(isinstance(thread, str) and thread
            and metadata.get('type') == 'session_meta' and metadata.get('payload', {}).get('id') == thread,
            'archived native session differs')
    require(manifest.get('run_id') == run_id and manifest.get('permission_overrides') == {}
            and execution.get('run_id') == run_id
            and execution.get('freeze_sha256') == frozen['freeze_sha256'], 'archived execution identity differs')
    require(qualified.get('status') == 'qualified_observations'
            and qualified.get('accounting', {}).get('usage_status') == 'known'
            and qualified.get('accounting', {}).get('usage') is not None,
            'repair wait requires qualified original observations and known usage')
    require(qualified.get('run_id') == run_id and qualified.get('thread_id') == thread
            and qualified.get('config_sha256') == r0.digest(observer / 'run.json')
            and qualified.get('native_trace_sha256') == r0.digest(trace), 'archived qualification bindings differ')
    before = read(observer / 'source-before.json')
    after = read(observer / 'qualification/source-after.json')
    task = next(task for task in frozen['tasks'] if task['id'] == frozen['schedule'][len(runs) - 1]['task'])
    verify_snapshot(before, task['source_identity'])
    verify_snapshot(after, after['sha256'])
    require(qualified.get('source_before') == before['sha256']
            and qualified.get('source_after') == after['sha256'], 'archived source bindings differ')
    verified = index.get('availability_gate', {})
    availability_gate = args.availability_gate or root / 'availability/gate.json'
    require(verified.get('path') == str(availability_gate.resolve())
            and verified.get('sha256') == r0.digest(availability_gate)
            and read(args.gate).get('status') == 'passed'
            and verified.get('deterministic_gate_sha256') == r0.digest(args.gate), 'retained gate bindings differ')
    return {'schema_version': 1, 'status': 'waiting', 'pid': os.getpid(),
            'freeze_sha256': frozen['freeze_sha256'], 'freeze_file_sha256': r0.digest(args.freeze),
            'execution_index_sha256': r0.digest(index_path), 'blocker_run': run_id,
            'amendment': None if args.amendment is None else
                {'path': str(args.amendment.resolve()), 'sha256': r0.digest(args.amendment)},
            'diagnostics': {'original_failure': failure, 'evidence_error': tail['evidence_error']}}


def repair_request(args, root, state, request):
    """Validate only a new instrumentation amendment; execution stays in normal resume."""
    require(isinstance(request, dict) and set(request) ==
            {'schema_version', 'freeze_sha256', 'execution_index_sha256', 'amendment'},
            'request fields must be exactly schema_version, freeze_sha256, execution_index_sha256, amendment')
    require(type(request['schema_version']) is int and request['schema_version'] == 1,
            'request schema_version must be 1')
    require(request['freeze_sha256'] == state['freeze_sha256'], 'request freeze_sha256 differs from blocked freeze')
    require(request['execution_index_sha256'] == state['execution_index_sha256'],
            'request execution_index_sha256 is stale; use repair-wait.json')
    require(r0.digest(root / 'execution-index.json') == state['execution_index_sha256'],
            'execution index changed while waiting; restart and inspect retained state')
    require(r0.digest(args.freeze) == state['freeze_file_sha256'], 'original freeze file changed while waiting')
    amendment = request['amendment']
    require(isinstance(amendment, dict) and set(amendment) == {'path', 'sha256'},
            'request amendment must contain exactly path and sha256')
    require(isinstance(amendment['path'], str) and Path(amendment['path']).is_absolute(),
            'request amendment path must be absolute')
    path = Path(amendment['path'])
    require(path.is_file() and r0.digest(path) == amendment['sha256'], 'request amendment file/hash differs')
    require(state['amendment'] is None or amendment['sha256'] != state['amendment']['sha256'],
            'repair amendment bytes must differ from the blocked amendment')
    frozen = r1.read_freeze(args.freeze, amendment=path)
    require(frozen['freeze_sha256'] == state['freeze_sha256'], 'repair amendment changed frozen identity')
    require(r0.digest(path) == amendment['sha256'], 'repair amendment changed during validation')
    require(r0.digest(root / 'execution-index.json') == state['execution_index_sha256']
            and r0.digest(args.freeze) == state['freeze_file_sha256'],
            'blocked execution index or freeze changed during repair validation')
    return [sys.executable, '-u', str(Path(__file__).resolve()),
            '--freeze', str(args.freeze.resolve()), '--gate', str(args.gate.resolve()),
            '--output-root', str(root.resolve()),
            '--availability-gate', str((args.availability_gate or root / 'availability/gate.json').resolve()),
            '--amendment', str(path.resolve()), '--resume', '--wait-for-repair']


def wait_for_repair(args, root, state):
    """Wait in the existing Terminal process; a validated request replaces this process."""
    marker = root / 'repair-wait.json'
    write_json(marker, state)
    print(json.dumps(state), flush=True)
    try:
        while True:
            incoming = root / 'repair-request.json'
            if incoming.exists():
                retained = root / 'repair-requests' / (uuid.uuid4().hex + '.json')
                retained.parent.mkdir(exist_ok=True)
                os.replace(incoming, retained)
                receipt = {'schema_version': 1, 'request': str(retained), 'status': 'rejected'}
                try:
                    argv = repair_request(args, root, state, read(retained))
                except Exception as exc:
                    receipt['error'] = f'{type(exc).__name__}: {exc}'
                    state['diagnostics']['last_rejected_request'] = receipt
                    write_json(retained.with_suffix('.receipt.json'), receipt)
                    write_json(marker, state)
                    print(json.dumps(receipt), flush=True)
                else:
                    receipt.update(status='accepted', argv=argv)
                    write_json(retained.with_suffix('.receipt.json'), receipt)
                    state.update(status='restarting', accepted_request=str(retained))
                    write_json(marker, state)
                    try:
                        os.execv(sys.executable, argv)
                    except OSError as exc:
                        error = f'{type(exc).__name__}: {exc}'
                        receipt.update(status='restart_failed', error=error)
                        state.update(status='restart_failed', error=error)
                        write_json(retained.with_suffix('.receipt.json'), receipt)
                        write_json(marker, state)
                        return {'status': 'blocked', 'stage': 'repair_restart', 'error': error,
                                'original_failure': state['diagnostics']['original_failure']}
                    return state  # execv only returns when replaced by a test double.
            time.sleep(1)
    except KeyboardInterrupt:
        state['status'] = 'interrupted'
        write_json(marker, state)
        return {'status': 'blocked', 'stage': 'repair_wait', 'error': 'repair wait interrupted',
                'original_failure': state['diagnostics']['original_failure']}


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
    parser.add_argument('--availability-gate', type=Path)
    parser.add_argument('--wait-for-repair', action='store_true',
                        help='Keep this Terminal process waiting for a validated observer-repair amendment')
    parser.add_argument('--reprocess', action='store_true',
                        help='Reprocess retained availability evidence only; never launch native work')
    args = parser.parse_args(argv)
    root = args.output_root if args.output_root is not None else args.freeze.parent
    if args.wait_for_repair and (not args.resume or args.preflight_only or args.check_only
                                 or args.reprocess or args.background):
        parser.error('--wait-for-repair requires --resume and cannot combine with preflight, check, reprocess or background')
    if args.reprocess:
        if args.resume or args.check_only or args.preflight_only or args.background:
            parser.error('--reprocess cannot be combined with execution or preflight flags')
        destination = root / 'reprocessed-availability' / uuid.uuid4().hex
        destination.parent.mkdir(parents=True, exist_ok=True)
        result = r1.reprocess_availability(args.freeze, args.gate,
            args.availability_gate or root / 'availability/gate.json', destination, amendment=args.amendment)
        print(json.dumps(result), flush=True)
        return result
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
            if args.availability_gate is None:
                preflight = r1.preflight(args.freeze, args.gate, root / 'availability', amendment=args.amendment)
            else:
                frozen = r1.read_freeze(args.freeze, amendment=args.amendment)
                verified = r1.require_availability(frozen, args.availability_gate)
                require(r0.digest(args.gate) == verified['deterministic_gate_sha256'],
                        'availability gate belongs to another deterministic gate')
                preflight = read(args.availability_gate)
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
    # Check runtime pins before catching observer/recovery exceptions. Unsafe
    # configuration must fail normally, rather than becoming a repair wait.
    frozen = r1.read_freeze(args.freeze, amendment=args.amendment) if args.wait_for_repair else None
    try:
        result = run(args.freeze, args.gate, args.amendment, root,
                     resume=args.resume, check_only=args.check_only, availability_gate=args.availability_gate)
    except Exception as exc:
        if not args.wait_for_repair:
            raise
        failure = {'status': 'blocked', 'error': f'{type(exc).__name__}: {exc}',
                   'traceback': traceback.format_exc()}
        try:
            state = repair_wait_state(args, root, frozen, failure)
        except Exception:
            raise exc
        result = wait_for_repair(args, root, state)
    else:
        if args.wait_for_repair and result.get('status') == 'blocked':
            try:
                state = repair_wait_state(args, root, frozen, result)
            except Exception:
                pass  # Incomplete native/archive evidence remains an ordinary hard stop.
            else:
                result = wait_for_repair(args, root, state)
    print(json.dumps(result), flush=True)
    return result


if __name__ == '__main__':
    outcome = main()
    raise SystemExit(0 if outcome['status'] in {'complete', 'checked', 'passed', 'submitted'} else 1)
