"""Compare all six retained binding samples under the predeclared metrics."""
import hashlib
import json
from pathlib import Path
from statistics import median
import subprocess

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
GROUPS = {
    'baseline': ('ordinary-adoption-v1', ['run-02', 'run-07'], 'observed.json'),
    'pre_repair': ('ordinary-adoption-normal-v1', ['run-16', 'run-21'], 'observation.json'),
    'repaired': ('ordinary-adoption-repair-binding-v1', ['binding-repair-01', 'binding-repair-02'], 'observation.json'),
}
rows = []
for group, (comparison, ids, filename) in GROUPS.items():
    for run_id in ids:
        path = REPO / 'benchmarks/comparisons' / comparison / 'runs' / run_id / filename
        data = path.read_bytes()
        captured = json.loads(data)
        observed = captured.get('observation', captured)
        usage = observed['provider_usage']
        assert usage['status'] == 'available'
        cost = observed['cost']
        lineage = {'path': str(path.relative_to(REPO)), 'sha256': hashlib.sha256(data).hexdigest()}
        if group != 'repaired':
            committed = subprocess.check_output(['git', 'show', '4a27a8e:' + str(path.relative_to(REPO))], cwd=REPO)
            assert data == committed
            lineage['matches_pre_outcome_commit'] = '4a27a8ed821993d973cadf5ec597a55f62dd7d77'
        rows.append({
            'group': group, 'run_id': run_id, 'provenance': lineage,
            'input_tokens': usage['usage']['input_tokens'],
            'cached_input_tokens': usage['usage']['cached_input_tokens'],
            'uncached_input_tokens': usage['usage']['input_tokens'] - usage['usage']['cached_input_tokens'],
            'output_tokens': usage['usage']['output_tokens'],
            'provider_snapshots': usage['snapshots_observed'],
            'outer_round_trips': cost['outer_round_trips'],
            'visible_output_bytes': cost['model_visible_outer_output_bytes'],
            'elapsed_ms': observed['outcome']['duration_ms'],
            'mcp_calls': cost['terminal_mcp_invocations'],
            'shell_calls': cost['terminal_shell_commands'],
        })
metrics = ['input_tokens', 'cached_input_tokens', 'uncached_input_tokens', 'output_tokens',
           'provider_snapshots', 'outer_round_trips', 'visible_output_bytes', 'elapsed_ms',
           'mcp_calls', 'shell_calls']
medians = {group: {key: median(row[key] for row in rows if row['group'] == group)
                   for key in metrics} for group in GROUPS}
comparisons = {
    f'{new}_over_{old}': {key: medians[new][key] / medians[old][key]
                         if medians[old][key] else None for key in metrics}
    for new, old in [('pre_repair', 'baseline'), ('repaired', 'baseline'), ('repaired', 'pre_repair')]
}
gates = {key: {'max_ratio': 1.25, 'ratio': comparisons['repaired_over_baseline'][key],
               'passed': comparisons['repaired_over_baseline'][key] <= 1.25}
         for key in ['input_tokens', 'visible_output_bytes', 'elapsed_ms']}
result = {'schema_version': 1, 'rows': rows, 'medians': medians, 'ratios': comparisons,
          'original_per_case_cost_gates': gates, 'all_cost_gates_pass': all(g['passed'] for g in gates.values()),
          'limits': ['Two samples per condition; no population or graph-only causal inference.',
                     'Input includes cached tokens and is not billed dollars.',
                     'Baseline observed.json and prior observations match the pre-outcome product commit; earlier artifacts are not rewritten.',
                     'This binding-only comparison cannot establish full-workload acceptance.']}
(HERE / 'cost-results.json').write_text(json.dumps(result, indent=2) + '\n')
print(json.dumps({'medians': medians, 'ratios': comparisons, 'gates': gates}))
