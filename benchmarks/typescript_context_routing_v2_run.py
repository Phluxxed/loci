"""Freeze and qualify repaired exploration with the same tools in both arms."""
from __future__ import annotations

import argparse
import io
import json
from pathlib import Path
import subprocess
import tarfile
import time
from typing import Any

from benchmarks.typescript_context_baseline import (
    ROOT, child_environment, command, environment, execute, launch_args, prepare_catalog, sha,
)
from benchmarks.typescript_context_three_arm import save
from benchmarks.typescript_context_corpus import (
    _isolated_store, load_controls, load_corpus, materialize_snapshot, preflight,
)
from benchmarks.typescript_context_routing_v2 import POLICY_PATH, build_prompt, prompt_manifest

COMPARISON = 'typescript-context-routing-v2'
COMPARISON_ROOT = ROOT / 'benchmarks/comparisons' / COMPARISON
CORPUS_ROOT = ROOT / 'benchmarks/corpora/typescript-context-v3'
ENGINE_COMMIT = 'c14b2a87a8dde6543c7c790888619bad94711430'
TOOLS_MODULE = 'benchmarks.typescript_context_routing_v2_tools'
NEW_HARNESS = [f'benchmarks/typescript_context_routing_v2{suffix}.py' for suffix in
               ('', '_transport', '_tools', '_run', '_run_transport', '_observed', '_report', '_replay')] + [
    'benchmarks/comparisons/typescript-context-routing-v1/freeze.json',
    'benchmarks/comparisons/typescript-context-routing-v1/measurement-transport-verification.json',
]




def git(*args):
    return command(['git', *args], cwd=ROOT)


def engine_identity():
    archive = subprocess.check_output(['git', 'archive', ENGINE_COMMIT, 'src'], cwd=ROOT)
    with tarfile.open(fileobj=io.BytesIO(archive)) as source:
        files = {}
        for member in source.getmembers():
            if member.isfile():
                content = source.extractfile(member)
                if content is None:
                    raise ValueError('missing source archive member: ' + member.name)
                files[member.name] = sha(content.read())
    return {'commit': ENGINE_COMMIT, 'source_tree': git('rev-parse', ENGINE_COMMIT + ':src'),
            'extractor_version': 25, 'files': files}


def verify_engine(identity):
    from loci import service
    from loci.storage.index_store import EXTRACTOR_VERSION
    files = {str(p.relative_to(ROOT)): sha(p.read_bytes()) for p in (ROOT / 'src').rglob('*')
             if p.is_file() and '__pycache__' not in p.parts}
    if files != identity['files']:
        raise ValueError('runtime source differs from the shared pinned engine')
    if (Path(service.__file__).resolve() != ROOT / 'src/loci/service.py'
            or EXTRACTOR_VERSION != identity['extractor_version']):
        raise ValueError('runner imported a different engine')


def schedule(corpus):
    if corpus['version'] != 'typescript-context-v3' or len(corpus['cases']) != 17:
        raise ValueError('the original 17-case corpus is required')
    return [{'attempt_id': f"{case['id']}-r{repetition}-{arm}", 'case_id': case['id'],
             'snapshot': case['snapshot'], 'repetition': repetition, 'arm': arm}
            for ordinal, case in enumerate(corpus['cases']) for repetition in range(1, 4)
            for arm in (('A', 'B') if (ordinal * 3 + repetition - 1) % 2 == 0 else ('B', 'A'))]


def harness_files():
    original = json.loads((ROOT / 'benchmarks/comparisons/typescript-context-routing-v1/freeze.json').read_text())
    for name, digest in original['harness_files'].items():
        if sha((ROOT / name).read_bytes()) != digest:
            raise ValueError('historical frozen harness changed: ' + name)
    names = set(original['harness_files']) | set(NEW_HARNESS) | {
        'benchmarks/typescript_context_three_arm.py',
    }
    return {name: sha((ROOT / name).read_bytes()) for name in sorted(names)}


def freeze_inputs():
    """Build a declaration only after model-free proofs and code are committed."""
    corpus = load_corpus(CORPUS_ROOT)
    engine = engine_identity()
    verify_engine(engine)
    files = [p for p in COMPARISON_ROOT.rglob('*') if p.is_file() and p.name != 'freeze.json']
    if not (COMPARISON_ROOT / 'measurement-transport-verification.json').is_file():
        raise ValueError('actual offline transport proof is required before freezing')
    declared = json.loads((COMPARISON_ROOT / 'prompt-manifest.json').read_text())
    if declared != prompt_manifest(corpus, load_controls(corpus)):
        raise ValueError('prompt declaration differs from the published policy')
    return {'schema_version': 1, 'version': COMPARISON, 'freeze_commit': git('rev-parse', 'HEAD'),
        'frozen_at_utc': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
        'engine': engine, 'harness_files': harness_files(),
        'corpus_files': {str(p.relative_to(CORPUS_ROOT)): sha(p.read_bytes())
                         for p in CORPUS_ROOT.rglob('*') if p.is_file()},
        'comparison_files': {str(p.relative_to(ROOT)): sha(p.read_bytes()) for p in sorted(files)},
        'plan': schedule(corpus),
        'policy_definition_commit': 'b2c0362c837f65ce07d0eb2556c95f3d5a5534d4',
        'repair_commit': ENGINE_COMMIT,
        'policy_sha256': sha(POLICY_PATH.read_bytes()),
        'prompt_manifest_sha256': sha((COMPARISON_ROOT / 'prompt-manifest.json').read_bytes()),
        'capability_arms': {'A': 'B', 'B': 'B'},
        'canonical_tool_schemas_sha256': json.loads((COMPARISON_ROOT / 'measurement-transport-verification.json').read_text())['canonical_tool_schemas_sha256']}


def validate_freeze(path):
    value = json.loads(Path(path).read_text())
    if value['version'] != COMPARISON or value['harness_files'] != harness_files():
        raise ValueError('exploration harness differs from its freeze')
    if value['engine'] != engine_identity() or value['plan'] != schedule(load_corpus(CORPUS_ROOT)):
        raise ValueError('shared engine or fixed schedule changed')
    if value.get('repair_commit') != ENGINE_COMMIT:
        raise ValueError('repair source identity differs from qualification')
    verify_engine(value['engine'])
    if (value['policy_sha256'] != sha(POLICY_PATH.read_bytes())
            or value['prompt_manifest_sha256'] != sha((COMPARISON_ROOT / 'prompt-manifest.json').read_bytes())
            or value['capability_arms'] != {'A': 'B', 'B': 'B'}):
        raise ValueError('routing policy or capability declaration changed')
    corpus = load_corpus(CORPUS_ROOT)
    if json.loads((COMPARISON_ROOT / 'prompt-manifest.json').read_text()) != prompt_manifest(corpus, load_controls(corpus)):
        raise ValueError('effective prompts differ from the published declaration')
    for name, digest in value['corpus_files'].items():
        if sha((CORPUS_ROOT / name).read_bytes()) != digest:
            raise ValueError('frozen corpus changed: ' + name)
    for name, digest in value['comparison_files'].items():
        if sha((ROOT / name).read_bytes()) != digest:
            raise ValueError('frozen comparison input changed: ' + name)
    paths = list(value['harness_files']) + list(value['comparison_files']) + [
        str(CORPUS_ROOT.relative_to(ROOT)), str(Path(path).resolve().relative_to(ROOT))]
    if git('status', '--porcelain', '--', *paths):
        raise ValueError('frozen inputs must be committed before measurement')
    if subprocess.check_output(['git', 'show', 'HEAD:' + paths[-1]], cwd=ROOT) != Path(path).read_bytes():
        raise ValueError('freeze differs from committed declaration')
    subprocess.run(['git', 'merge-base', '--is-ancestor', value['freeze_commit'], 'HEAD'],
                   cwd=ROOT, check=True, capture_output=True)
    for name, digest in value['harness_files'].items():
        if sha(subprocess.check_output(['git', 'show', value['freeze_commit'] + ':' + name], cwd=ROOT)) != digest:
            raise ValueError('harness does not match freeze commit: ' + name)
    return {**value, 'freeze_json_sha256': sha(Path(path).read_bytes())}


def settings(run_file, catalog, store):
    from benchmarks.typescript_context_explore_transport import settings as original
    value = original(run_file, catalog, store)
    value['mcp_servers.evaluation.args'] = ['-m', TOOLS_MODULE, str(run_file)]
    return value


def inspect_request(repo, config, prompt, runtime_home):
    from benchmarks.typescript_context_explore_transport import inspect_request as original
    return original(repo, config, prompt, runtime_home, arm='B')


def routing_identity(corpus, controls, plan, freeze):
    if sha(POLICY_PATH.read_bytes()) != freeze['policy_sha256']:
        raise ValueError('routing policy changed before attempt')
    manifest_path = COMPARISON_ROOT / 'prompt-manifest.json'
    if sha(manifest_path.read_bytes()) != freeze['prompt_manifest_sha256']:
        raise ValueError('prompt manifest changed before attempt')
    expected = next(case for case in json.loads(manifest_path.read_text())['cases'] if case['case_id'] == plan['case_id'])
    arm = plan['arm']
    base_prompt = build_prompt(corpus, controls, plan['case_id'], 'A')
    effective_prompt = build_prompt(corpus, controls, plan['case_id'], arm)
    if sha(effective_prompt.encode()) != expected['prompts'][arm]['sha256']:
        raise ValueError('effective routing prompt differs from declaration')
    return {
        'version': COMPARISON, 'condition': arm,
        'policy_sha256': freeze['policy_sha256'] if arm == 'B' else None,
        'base_prompt_sha256': sha(base_prompt.encode()),
        'effective_prompt_sha256': sha(effective_prompt.encode()),
        'candidate_prefix_utf8_bytes': len(effective_prompt.encode()) - len(base_prompt.encode()),
        'capability_arm': 'B',
    }


def run_attempt(corpus, controls, plan, output, catalog, freeze):
    from benchmarks import typescript_context_compare as prior
    from benchmarks.typescript_context_routing_v2_observed import measure
    from loci import service

    verify_engine(freeze['engine'])
    routing = routing_identity(corpus, controls, plan, freeze)
    if plan['arm'] == 'B':
        controls = {**controls, 'agent': {**controls['agent'],
            'common_prompt': POLICY_PATH.read_text(encoding='utf-8') + '\n' + controls['agent']['common_prompt']}}

    def save_bound(path, value):
        if Path(path) == output / plan['attempt_id'] / 'provenance.json':
            value['routing'] = routing
        save(path, value)

    modules, source_provenance = prior.ARM_MODULES, prior._source_provenance
    prior.ARM_MODULES = {arm: TOOLS_MODULE for arm in ('A', 'B')}
    prior._source_provenance = lambda *_: {
        'engine': {key: freeze['engine'][key] for key in ('commit', 'source_tree', 'extractor_version')},
        'freeze_commit': freeze['freeze_commit'], 'freeze_json_sha256': freeze['freeze_json_sha256'],
        'source_scope': 'same pinned repaired engine and exploration-capable tools; candidate adds the unchanged routing policy',
    }
    try:
        artifact = prior._run_attempt(corpus=corpus, controls=controls, plan=plan, output=output,
            catalog=catalog, expected_schema_hash=freeze['canonical_tool_schemas_sha256'][plan['arm']],
            freeze=freeze, inspect_request=inspect_request,
            settings=settings, launch_args=launch_args, child_environment=child_environment,
            execute=execute, save=save_bound, materialize_snapshot=materialize_snapshot,
            isolated_store=_isolated_store, service=service, measure=measure)
    finally:
        prior.ARM_MODULES, prior._source_provenance = modules, source_provenance
    artifact['protocol'] = COMPARISON
    artifact.setdefault('routing', {
        'schema_version': 1, 'observations_complete': False,
        'first_repository_call': None, 'initial_route_expected': None,
        'initial_type_route': None, 'requested_anchor_received': None,
        'maintained_exposure': None, 'explore_calls': [], 'fallback_calls': [],
        'helper_call_count': 0, 'failures': [{'category': 'routing_measurement_unavailable'}],
    })
    save(output / plan['attempt_id'] / 'result.json', artifact)
    return artifact


def run_batch(freeze_path, output, resume=False):
    from benchmarks.typescript_context_routing_v2_report import generate_report
    from benchmarks.typescript_context_routing_v2_replay import verify

    freeze = validate_freeze(freeze_path)
    corpus = load_corpus(CORPUS_ROOT)
    controls = load_controls(corpus)
    observed = environment(controls)
    cli_version = command(['codex', '--version'])
    if cli_version != 'codex-cli ' + controls['agent']['cli_version']:
        raise ValueError('CLI differs from the matched environment')
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=resume)
    catalog = output / 'model-catalog.json'
    for name in ('model-catalog.json', 'model-catalog-provenance.json'):
        original = (COMPARISON_ROOT / name).read_bytes()
        if resume:
            if (output / name).read_bytes() != original:
                raise ValueError('retained catalog changed')
        else:
            (output / name).write_bytes(original)
    manifest = {'schema_version': 3, 'comparison': COMPARISON, 'planned_runs': 102,
        'plan': freeze['plan'], 'freeze': freeze, 'environment': observed,
        'cli_version': cli_version, 'catalog_sha256': sha(catalog.read_bytes()),
        'canonical_tool_schemas_sha256': freeze['canonical_tool_schemas_sha256']}
    if resume:
        previous = json.loads((output / 'manifest.json').read_text())
        if any(previous.get(key) != value for key, value in manifest.items()):
            raise ValueError('batch identity changed; cannot resume')
    else:
        save(output / 'manifest.json', {**manifest, 'started_at_utc': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())})
    expected = {p['attempt_id'] for p in freeze['plan']}
    if {p.name for p in output.iterdir() if p.is_dir()} - expected:
        raise ValueError('unexpected attempt directory')
    results = []
    for plan in freeze['plan']:
        destination = output / plan['attempt_id']
        if destination.exists():
            if not resume or not (destination / 'result.json').is_file():
                raise ValueError('existing or interrupted attempt cannot be retried or overwritten; '
                                 'partial batch remains inconclusive with raw evidence retained: ' + plan['attempt_id'])
            result = json.loads((destination / 'result.json').read_text())
        else:
            print(json.dumps({'starting': plan['attempt_id'], 'completed': len(results)}), flush=True)
            result = run_attempt(corpus, controls, plan, output, catalog, freeze)
        results.append(result)
        measured = result['measurement']
        print(json.dumps({'completed': plan['attempt_id'], 'count': len(results),
            'correct': measured['task_correct'], 'calls': measured['read_count'],
            'outcome': measured['outcome'], 'complete': measured.get('measurement_complete')}), flush=True)
    try:
        verify(output)
    except ValueError as exc:
        path = output / 'replay-verification.json'
        failed: dict[str, Any] = json.loads(path.read_text()) if path.exists() else {'comparison': COMPARISON}
        failed['complete'] = False
        failed.setdefault('failures', []).append({'category': 'replay_unavailable', 'error': str(exc)})
        save(path, failed)
    summary = generate_report(output, CORPUS_ROOT, COMPARISON_ROOT / 'preflight.json')
    save(output / 'completion.json', {'recorded_runs': len(results),
         'replay_complete': summary['replay_complete'], 'verdict': summary['qualification_verdict'],
         'frozen_gate_verdict': summary['verdict']})
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mode', choices=['prepare', 'freeze', 'run'], required=True)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--resume', action='store_true')
    args = parser.parse_args()
    if args.mode == 'prepare':
        from benchmarks.typescript_context_routing_v2_run_transport import verify_transport
        corpus = load_corpus(CORPUS_ROOT)
        verify_engine(engine_identity())
        observed = environment(load_controls(corpus))
        cli = command(['codex', '--version'])
        if cli != 'codex-cli ' + load_controls(corpus)['agent']['cli_version']:
            raise ValueError('CLI differs from frozen controls')
        login = subprocess.run(['codex', 'login', 'status'], text=True, capture_output=True, check=True)
        login_status = (login.stdout + login.stderr).strip()
        if login_status != 'Logged in using ChatGPT':
            raise ValueError('matched comparison requires existing ChatGPT authentication')
        COMPARISON_ROOT.mkdir(parents=True, exist_ok=True)
        if (COMPARISON_ROOT / 'model-catalog.json').exists():
            raise ValueError('preparation already has a catalog; preserve it and run explicit remaining checks')
        save(COMPARISON_ROOT / 'environment-verification.json',
             {'environment': observed, 'cli_version': cli, 'authentication': login_status})
        catalog = prepare_catalog(COMPARISON_ROOT, 'gpt-5.6-luna')
        save(COMPARISON_ROOT / 'preflight.json', preflight(corpus))
        verify_transport(corpus, catalog, COMPARISON_ROOT / 'measurement-transport-verification.json')
    elif args.mode == 'freeze':
        path = COMPARISON_ROOT / 'freeze.json'
        if path.exists():
            raise ValueError('freeze already exists')
        save(path, freeze_inputs())
    else:
        if args.output is None:
            parser.error('--output required for run')
        result = run_batch(COMPARISON_ROOT / 'freeze.json', args.output, args.resume)
        print(json.dumps({'qualification_verdict': result['qualification_verdict'],
                          'frozen_gate_verdict': result['verdict'], 'recorded_runs': result['recorded_runs']}))


if __name__ == '__main__':
    main()
