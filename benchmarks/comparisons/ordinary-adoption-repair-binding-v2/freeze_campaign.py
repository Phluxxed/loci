"""Freeze the explicitly selected pair once, before any provider attempt."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
target = HERE / 'freeze.json'
if target.exists() or (HERE / 'runs').exists():
    raise SystemExit('Refusing to replace a freeze or freeze after outcomes exist')

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

runtime = json.loads((HERE / 'runtime/runtime-identity.json').read_text())
preflight = json.loads((HERE / 'preflight.json').read_text())
assert preflight['passed'] is True
assert not subprocess.check_output(['git', 'diff', 'HEAD', '--', 'src'], cwd=REPO)
for item in runtime['installed_inputs']:
    assert sha(Path(item['path'])) == item['sha256']
    assert sha(REPO / item['snapshot']) == item['sha256']

schedule_path = HERE / 'schedule.json'
schedule = json.loads(schedule_path.read_text())
schedule['status'] = 'frozen'
schedule_path.write_text(json.dumps(schedule, indent=2) + '\n')
paths = {p for p in HERE.rglob('*') if p.is_file() and '__pycache__' not in p.parts}
paths.update(REPO / p for p in [
    'benchmarks/ordinary_adoption_delivery_v4.py',
    'tests/test_ordinary_adoption_delivery_v4.py',
    'benchmarks/ordinary_adoption_delivery_v3.py',
    'benchmarks/ordinary_adoption_observed.py',
    'benchmarks/ordinary_adoption_normal.py',
    'benchmarks/ordinary_adoption_native_v2.py',
    'benchmarks/ordinary_adoption_review.py',
    'benchmarks/comparisons/ordinary-adoption-v1/cases.json',
    '.scratch/deterministic-graph-retrieval/anchor-host-acceptance-20260915/receipt.json',
    '.scratch/deterministic-graph-retrieval/anchor-host-acceptance-20260915/capture.py',
    '.scratch/deterministic-graph-retrieval/diagnosis/anchor-identity-after-envelope.json',
])
groups = [
    ('ordinary-adoption-v1', ['run-02', 'run-07'], 'observed.json'),
    ('ordinary-adoption-normal-v1', ['run-16', 'run-21'], 'observation.json'),
    ('ordinary-adoption-repair-binding-v1', ['binding-repair-01', 'binding-repair-02'], 'observation.json'),
]
for comparison, runs, observation in groups:
    for run in runs:
        for filename in [observation, 'metadata.json']:
            paths.add(REPO / 'benchmarks/comparisons' / comparison / 'runs' / run / filename)
for comparison in ['ordinary-adoption-normal-v1', 'ordinary-adoption-repair-binding-v1']:
    paths.add(REPO / 'benchmarks/comparisons' / comparison / 'freeze.json')

freeze = {
    'schema_version': 1, 'comparison': HERE.name, 'status': 'frozen_before_outcomes',
    'frozen_at_utc': datetime.now(timezone.utc).isoformat(),
    'selection': {'authority': 'Vik explicit selection', 'user_direction': 'Okay do it',
                  'context': 'Two fresh binding tasks after restarted-host proof acceptance',
                  'attempts': 2},
    'product_implementation_revision': '44d1074e20ef8c2e54ca92f48aa0229a4a0e4fb3',
    'pre_campaign_revision': runtime['source_revision'],
    'product_src_tree': runtime['product_src_tree'],
    'input_sha256': {str(p.relative_to(REPO)): sha(p) for p in sorted(paths)},
    'installed_inputs': runtime['installed_inputs'],
    'execution': {'model': 'gpt-5.6-terra', 'effort': 'high', 'fork_turns': 'none',
                  'attempts': 2, 'max_concurrent': 2, 'wall_cap_ms': 300000,
                  'replacement_attempts': 0, 'in_run_interventions': 0},
    'metrics': {'cost_median_max_ratio_to_original_baseline': 1.25,
                'required_facts': 'All original binding facts, including compound clauses',
                'usage_and_expected_type_proof': 'Report each out of2 independently of cost/facts',
                'full_workload_acceptance_claim': False},
    'capture': {'normal_adapter': 'ordinary-adoption-normal-v2',
                'native_adapter': 'ordinary-adoption-native-v2',
                'delivery_supplement': 'ordinary-adoption-delivery-v4',
                'original_fields_preserved': True, 'first_native_turn_only': True,
                'private_raw_intervals_published': False},
    'review': {'primary': 'Rowan, gpt-6-astra/ultra',
               'independent_semantic_review': 'gpt-5.6-sol/high, outside trial context'},
}
target.write_text(json.dumps(freeze, indent=2) + '\n')
print(json.dumps({'freeze': str(target), 'sha256': sha(target), 'inputs': len(paths), 'attempts_started': 0}))
