"""Summarize retained R0 architectural observations; no new retrieval/scoring."""
import json
from pathlib import Path
from statistics import mean

BASE = Path(__file__).resolve().parent


def arm(directory, architecture, name):
    root = BASE / 'results' / directory
    result = json.loads((root / 'result.json').read_text())
    arm_name = next(k for k,v in result['architectures'].items() if v == architecture)
    repetitions = []
    for repetition in sorted({r['repetition'] for r in result['runs']}):
        runs = [r for r in result['runs'] if r['arm'] == arm_name and r['repetition'] == repetition]
        first = [c for r in runs for c in json.loads((root / r['capability']).read_text())]
        repeated = [c for r in runs for c in json.loads((root / r['repeat_capability']).read_text())]
        workers = [json.loads((root / 'artifacts' / r['id'] / 'worker.json').read_text()) for r in runs]
        rows = [p for w in workers for p in w['phases']]
        first_rows = [p for p in rows if p['phase'] in {'retrieval','followup','continuation','semantic_context'}]
        repeat_rows = [p for p in rows if p['phase'].startswith('repeat_')]
        cpu = lambda r: sum(r.get(k,0) for k in ('user_cpu_s','system_cpu_s','children_user_cpu_s','children_system_cpu_s'))
        phase_totals = {}
        for p in rows:
            v=phase_totals.setdefault(p['phase'],{'elapsed_s':0,'cpu_s':0,'operations':0})
            v['elapsed_s']+=p['elapsed_ns']/1e9;v['cpu_s']+=cpu(p['resources']);v['operations']+=1
        def capability(cases):
            return {'cases':len(cases),'source_spans':sum(c['source_coverage']['covered'] for c in cases),
                'required_spans':sum(c['source_coverage']['required'] for c in cases),
                'complete_cases':sum(c['source_coverage']['covered']==c['source_coverage']['required'] for c in cases),
                'anchors':sum(c['acquisition']['anchor_source_acquired'] for c in cases),
                'semantic_links':sum(c['session_relationships']['delivered_dependency_links_total'] for c in cases),
                'required_links':sum(c['session_relationships']['required_semantic_dependencies_total'] for c in cases),
                'native_candidate_links':sum(c['session_relationships']['available_dependency_links_total'] for c in cases),
                'packet_proof_failed_cases':[c['case_id'] for c in cases if not c['integrity_ok']],
                'session_invalid_cases':[c['case_id'] for c in cases if not c['acquisition_integrity_ok']],
                'source_bytes':sum(c['efficiency']['source_bytes'] for c in cases),
                'unique_source_bytes':sum(c['efficiency']['unique_source_bytes'] for c in cases),
                'repeated_source_bytes':sum(c['efficiency']['repeated_source_bytes'] for c in cases),
                'delivered_bytes':sum(c['efficiency']['total_delivered_bytes'] for c in cases),
                'structural_claims':sum(c.get('structural_proof',{}).get('claims',0) for c in cases),
                'structural_violations':sum(len(c.get('structural_proof',{}).get('violations',[])) for c in cases)}
        work = [c['semantic_work'] for w in workers for c in w['cases'] if 'semantic_work' in c]
        warm = [c['repeat_semantic_work'] for w in workers for c in w['cases'] if 'repeat_semantic_work' in c]
        setup = [r for r in result['setup'] if r['run_id']==f'{arm_name}-{repetition}' or r['run_id'].startswith(f'{arm_name}-{repetition}-')]
        observer = [r for r in result.get('observer_phases',[]) if r['run_id'].startswith(f'{arm_name}-{repetition}-')]
        repetitions.append({'repetition':repetition,'first':capability(first),'repeat':capability(repeated),
            'index_s':sum(r['elapsed_ns'] for r in rows if r['phase']=='indexing')/1e9,
            'first_operations_s':sum(r['elapsed_ns'] for r in first_rows)/1e9,
            'repeat_operations_s':sum(r['elapsed_ns'] for r in repeat_rows)/1e9,
            'first_operations_cpu_s':sum(cpu(r['resources']) for r in first_rows),
            'repeat_operations_cpu_s':sum(cpu(r['resources']) for r in repeat_rows),
            'worker_elapsed_s':sum(r['execution']['elapsed_ns'] for r in runs)/1e9,
            'worker_cpu_s':sum(cpu(w['process_resources']) for w in workers),
            'peak_rss_bytes':max(w['process_resources']['peak_rss_bytes'] for w in workers),
            'prequestion_peak_rss_bytes':max(w['resources_before_questions']['peak_rss_bytes'] for w in workers),
            'prequestion_semantic_modules':[w['semantic_modules_before_questions'] for w in workers],
            'runtime_store_bytes':sum(r['store_bytes'] for r in runs),
            'external_cache_bytes':sum(r['cache_bytes'] for r in runs),
            'setup_s':sum(r['elapsed_ns'] for r in setup)/1e9,
            'setup_cpu_s':sum(cpu(r['resources']) for r in setup),
            'observer_validation_s':sum(r['elapsed_ns'] for r in observer)/1e9,
            'observer_validation_cpu_s':sum(cpu(r['resources']) for r in observer),
            'phase_totals':phase_totals,
            'semantic_first':{'calls':len(work),'cache_hits':sum(w['cache_hit'] for w in work),
                'discovered_bytes':sum(w['bytes_discovered'] for w in work),
                'parsed_file_executions':sum(len(w['parsed_paths']) for w in work),
                'parser_input_bytes':sum(w['bytes_parsed'] for w in work),
                'snapshot_bytes_written':sum(w['bytes_controls']+w['bytes_rust_snapshot']+w.get('bytes_snapshot_parsed',0) for w in work),
                'max_cache_serialized_proxy_bytes':max((w.get('cache_serialized_proxy_bytes',0) for w in work),default=0)},
            'semantic_repeat':{'calls':len(warm),'cache_hits':sum(w['cache_hit'] for w in warm),
                'discovered_bytes':sum(w['bytes_discovered'] for w in warm),
                'parsed_file_executions':sum(len(w['parsed_paths']) for w in warm)},
            'cases':[{'case_id':c['case_id'],'source':c['source_coverage'],'semantic':c['session_relationships'],
                'packet_integrity':c['integrity_ok'],'session_integrity':c['acquisition_integrity_ok'],
                'efficiency':c['efficiency'],'queries':c['acquisition']['queries'],
                'structural':c.get('structural_proof')} for c in first]})
    scalars=[k for k,v in repetitions[0].items() if type(v) in (float,int) and k!='repetition']
    return {'architecture':name,'result':str(root/'result.json'),'status':result['status'],
        'means':{k:mean(r[k] for r in repetitions) for k in scalars},'repetitions':repetitions,
        'retained_pair_evidence_bytes':sum(p.stat().st_size for p in root.rglob('*') if p.is_file()),
        'retained_arm_artifact_bytes':sum(p.stat().st_size for r in result['runs'] if r['arm']==arm_name
            for p in (root/'artifacts'/r['id']).rglob('*') if p.is_file())}


if __name__=='__main__':
    data={'qualification':'fixed-fixture, two repetitions; first and repeated queries distinct; no agent/task-answer inference',
          'targeted':[], 'full':[]}
    for section,prefix in [('targeted','targeted'),('full','full')]:
        if not (BASE/'results'/f'{prefix}-eager-demand'/'result.json').exists():continue
        data[section]=[arm(f'{prefix}-source-demand','graph-free','R0.4 graph-free'),
                       arm(f'{prefix}-source-demand','demand','Demand-driven'),
                       arm(f'{prefix}-eager-demand','graph','R0.3 eager graph')]
        data[section+'_demand_cross_pair']=arm(f'{prefix}-eager-demand','demand','Demand second paired measurement')
    (BASE/'summary.json').write_text(json.dumps(data,indent=2,sort_keys=True)+'\n')
    for section in ('targeted','full'):
        for a in data[section]:
            print(section,a['architecture'],json.dumps(a['means']),a['repetitions'][0]['first'])
