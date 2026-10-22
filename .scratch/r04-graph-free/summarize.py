"""Summarize retained architectural measurements; performs no retrieval/scoring."""
import json
from pathlib import Path
from statistics import mean

ROOT = Path(__file__).resolve().parent

def summarize(directory, arm, name):
    root = ROOT / 'results' / directory
    report = json.loads((root / 'result.json').read_text())
    repetitions = []
    for rep in sorted({r['repetition'] for r in report['runs']}):
        runs = [r for r in report['runs'] if r['arm'] == arm and r['repetition'] == rep]
        scores = [c for r in runs for c in json.loads((root / r['capability']).read_text())]
        phases = {}
        for r in runs:
            for phase, values in r['phase_totals'].items():
                row = phases.setdefault(phase, {'elapsed_s': 0, 'cpu_s': 0, 'operations': 0})
                row['elapsed_s'] += values['elapsed_ns'] / 1e9
                row['cpu_s'] += sum(values.get(k, 0) for k in ('user_cpu_s','system_cpu_s','children_user_cpu_s','children_system_cpu_s'))
                row['operations'] += values['operations']
        setup = [r for r in report['setup'] if r['run_id'] == f'{arm}-{rep}' or r['run_id'].startswith(f'{arm}-{rep}-')]
        resources = [r['process_resources'] for r in runs]
        cases = []
        for c in scores:
            cases.append({'id': c['case_id'], 'initial_covered': c['acquisition']['initial_source_coverage']['covered'],
                'covered': c['source_coverage']['covered'], 'required': c['source_coverage']['required'],
                'covered_ids': c['source_coverage']['covered_context_ids'],
                'anchor_acquired': c['acquisition']['anchor_source_acquired'],
                'session_relationships': c['session_relationships']['delivered_dependency_links_total'],
                'legacy_packet_integrity_ok': c['integrity_ok'], 'session_integrity_ok': c['acquisition_integrity_ok'],
                'source_bytes': c['efficiency']['source_bytes'], 'unique_source_bytes': c['efficiency']['unique_source_bytes'],
                'repeated_source_bytes': c['efficiency']['repeated_source_bytes'],
                'total_delivered_bytes': c['efficiency']['total_delivered_bytes'],
                'snapshot_fraction_delivered': c['efficiency']['snapshot_fraction_delivered'],
                'snapshot_source_bytes': c['efficiency']['snapshot_source_bytes'],
                'queries': [q['query'] for q in c['acquisition']['queries']],
                'soft_byte_limit_overshoot': c['acquisition']['soft_byte_limit_overshoot']})
        indexing_work = []
        for r in runs:
            worker = json.loads((root / 'artifacts' / r['id'] / 'worker.json').read_text())
            indexing_work.extend(x['work'] for x in worker['phases'] if x['phase'] == 'indexing')
        sum_work = {key: sum(w.get(key, 0) for w in indexing_work) for key in sorted({
            key for w in indexing_work for key, value in w.items() if type(value) is int})}
        repetitions.append({'repetition': rep, 'case_count': len(cases),
            'initial_spans': sum(c['initial_covered'] for c in cases), 'final_spans': sum(c['covered'] for c in cases),
            'required_spans': sum(c['required'] for c in cases), 'anchors': sum(c['anchor_acquired'] for c in cases),
            'complete_cases': sum(c['covered'] == c['required'] for c in cases),
            'semantic_relationships_delivered': sum(c['session_relationships'] for c in cases),
            'semantic_relationships_required': sum(c['relationships']['required_semantic_dependencies_total'] for c in scores),
            'store_bytes': sum(r['store_bytes'] for r in runs),
            'cache_bytes': sum(r['cache_bytes'] for r in runs),
            'worker_elapsed_s': sum(r['execution']['elapsed_ns'] for r in runs) / 1e9,
            'worker_cpu_s': sum(sum(r.get(k, 0) for k in ('user_cpu_s','system_cpu_s','children_user_cpu_s','children_system_cpu_s')) for r in resources),
            'worker_peak_rss_bytes': max(r['peak_rss_bytes'] for r in resources),
            'controller_setup_s': sum(r['elapsed_ns'] for r in setup) / 1e9,
            'controller_setup_cpu_s': sum(sum(r['resources'].get(k, 0) for k in ('user_cpu_s','system_cpu_s','children_user_cpu_s','children_system_cpu_s')) for r in setup),
            'total_delivered_bytes': sum(c['total_delivered_bytes'] for c in cases),
            'source_bytes': sum(c['source_bytes'] for c in cases),
            'unique_source_bytes_per_case_sum': sum(c['unique_source_bytes'] for c in cases),
            'repeated_source_bytes': sum(c['repeated_source_bytes'] for c in cases),
            'phases': phases, 'indexing_work': sum_work, 'cases': cases})
    numeric = [k for k, v in repetitions[0].items() if type(v) in (int, float) and k != 'repetition']
    return {'name': name, 'result': str(root / 'result.json'), 'implementations': report['implementations'],
            'status': report['status'], 'means': {k: mean(r[k] for r in repetitions) for k in numeric},
            'phase_means': {phase: {k: mean(r['phases'][phase][k] for r in repetitions)
                for k in repetitions[0]['phases'][phase]} for phase in repetitions[0]['phases']},
            'repetitions': repetitions}

if __name__ == '__main__':
    data = {'qualification': 'descriptive two-repetition measurements; source acquisition, proof and task correctness are distinct',
            'architectures': [summarize('original-r03-full', 'control', 'Original Loci'),
                              summarize('graph-free-full', 'control', 'Graph-enabled R0.3'),
                              summarize('graph-free-full', 'variant', 'Graph-free candidate')],
            'r03_cross_pair': summarize('original-r03-full', 'variant', 'R0.3 second paired measurement')}
    (ROOT / 'summary.json').write_text(json.dumps(data, indent=2, sort_keys=True) + '\n')
    print(json.dumps([{k: v for k, v in a.items() if k in {'name','means','phase_means'}} for a in data['architectures']], indent=2))
