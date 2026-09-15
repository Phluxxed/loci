"""Compare all eight retained binding samples under the predeclared metrics."""
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
    'previous_repair': ('ordinary-adoption-repair-binding-v1', ['binding-repair-01', 'binding-repair-02'], 'observation.json'),
    'repaired': ('ordinary-adoption-repair-binding-v2', ['binding-repair-v2-01', 'binding-repair-v2-02'], 'observation.json'),
}
rows = []
for group, (comparison, ids, filename) in GROUPS.items():
    for run_id in ids:
        path = REPO / 'benchmarks/comparisons' / comparison / 'runs' / run_id / filename
        if group == 'repaired' and not path.exists():
            rows.append({'group': group, 'run_id': run_id,
                         'provenance': {'path': str(path.relative_to(REPO))},
                         'measurement_status': 'missing_capture'})
            continue
        data = path.read_bytes()
        captured = json.loads(data)
        observed = captured.get('observation', captured)
        usage = observed['provider_usage']
        measured = usage.get('usage', {}) if usage.get('status') == 'available' else {}
        cost = observed['cost']
        lineage = {'path': str(path.relative_to(REPO)), 'sha256': hashlib.sha256(data).hexdigest()}
        if group != 'repaired':
            committed = subprocess.check_output(['git', 'show', 'b9272f2:' + str(path.relative_to(REPO))], cwd=REPO)
            assert data == committed
            lineage['matches_pre_outcome_commit'] = 'b9272f238eed5dda35f6567dbf2ea3f3b97710a5'
        rows.append({
            'group': group, 'run_id': run_id, 'provenance': lineage,
            'measurement_status': usage.get('status', 'unknown'),
            'input_tokens': measured.get('input_tokens'),
            'cached_input_tokens': measured.get('cached_input_tokens'),
            'uncached_input_tokens': (measured['input_tokens'] - measured['cached_input_tokens']
                                     if all(type(measured.get(k)) is int for k in
                                            ('input_tokens', 'cached_input_tokens')) else None),
            'output_tokens': measured.get('output_tokens'),
            'provider_snapshots': usage.get('snapshots_observed'),
            'outer_round_trips': cost['outer_round_trips'],
            'visible_output_bytes': cost['model_visible_outer_output_bytes'],
            'elapsed_ms': observed['outcome']['duration_ms'],
            'mcp_calls': cost['terminal_mcp_invocations'],
            'shell_calls': cost['terminal_shell_commands'],
        })
metrics = ['input_tokens', 'cached_input_tokens', 'uncached_input_tokens', 'output_tokens',
           'provider_snapshots', 'outer_round_trips', 'visible_output_bytes', 'elapsed_ms',
           'mcp_calls', 'shell_calls']
def pair_median(group, key):
    values = [row.get(key) for row in rows if row['group'] == group]
    return median(values) if len(values) == 2 and all(type(v) in (int, float) for v in values) else None


medians = {group: {key: pair_median(group, key) for key in metrics} for group in GROUPS}
comparisons = {
    f'{new}_over_{old}': {key: medians[new][key] / medians[old][key]
                         if medians[old][key] and medians[new][key] is not None
                         else None for key in metrics}
    for new, old in [('pre_repair', 'baseline'), ('repaired', 'baseline'), ('repaired', 'pre_repair'), ('repaired', 'previous_repair'), ('previous_repair', 'baseline')]
}
gates = {key: {'max_ratio': 1.25, 'ratio': comparisons['repaired_over_baseline'][key],
               'passed': (comparisons['repaired_over_baseline'][key] <= 1.25
                          if comparisons['repaired_over_baseline'][key] is not None else None)}
         for key in ['input_tokens', 'visible_output_bytes', 'elapsed_ms']}
result = {'schema_version': 1, 'rows': rows, 'medians': medians, 'ratios': comparisons,
          'original_per_case_cost_gates': gates,
          'all_cost_gates_pass': all(g['passed'] is True for g in gates.values()),
          'cost_evidence_complete': all(g['passed'] is not None for g in gates.values()),
          'limits': ['Two samples per condition; no population or graph-only causal inference.',
                     'Input includes cached tokens and is not billed dollars.',
                     'Baseline observed.json and prior observations match the pre-outcome product commit; earlier artifacts are not rewritten.',
                     'This binding-only comparison cannot establish full-workload acceptance.']}
(HERE / 'cost-results.json').write_text(json.dumps(result, indent=2) + '\n')
print(json.dumps({'medians': medians, 'ratios': comparisons, 'gates': gates}))
