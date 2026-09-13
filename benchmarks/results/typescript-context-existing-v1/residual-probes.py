"""Retain diagnostic source probes separately from measured B deliveries."""
import json
import sys
import tempfile
from collections import Counter
from pathlib import Path

ROOT = Path('/Users/brummerv/phluxxed/loci-exploration')
sys.path.insert(0, str(ROOT))
from benchmarks.typescript_context_corpus import load_corpus, materialize_snapshot, _isolated_store
from loci import service
from loci.type_context import _real_declaration, _contains

CORPUS = ROOT / 'benchmarks/corpora/typescript-context-v3'
RESULTS = ROOT / 'benchmarks/results/typescript-context-existing-v1'
PROBES = Path('/tmp/loci-existing-context-probes.json')
corpus = load_corpus(CORPUS)
preflight = json.loads((ROOT / 'benchmarks/comparisons/typescript-context-existing-v1/preflight.json').read_text())
endpoint_sets = {item['id']: {endpoint['id']: endpoint['symbol_ids'] for endpoint in item['endpoints']}
                 for item in preflight['cases']}

if not PROBES.exists():
    probes = {}
    with tempfile.TemporaryDirectory(prefix='loci-existing-context-probes-') as tmp:
        base = Path(tmp)
        with _isolated_store(base / 'store'):
            repos = {}
            for case in corpus['cases']:
                if case['snapshot'] not in repos:
                    repo = base / case['snapshot']
                    materialize_snapshot(corpus, case['snapshot'], repo)
                    service.index_repo(repo, incremental=False)
                    repos[case['snapshot']] = repo
                repo = repos[case['snapshot']]
                _, nodes, graph = service._load_graph_context(repo, ensure_fresh=False)
                declarations = {key: node for key, node in nodes.items() if _real_declaration(node)}
                outputs = {}
                for label, ids in endpoint_sets[case['id']].items():
                    for symbol_id in ids:
                        result = service.get_symbols_result(repo, [symbol_id], include_type_context=True,
                                                            ensure_fresh=False)
                        owner = declarations.get(symbol_id)
                        records = []
                        if owner:
                            for record in graph.symbol_references:
                                raw = record.raw
                                if raw.source_file != owner['file_path'] or not _contains(owner, raw.start_byte, raw.end_byte):
                                    continue
                                containers = [node for node in declarations.values()
                                              if node['file_path'] == raw.source_file
                                              and _contains(node, raw.start_byte, raw.end_byte)]
                                minimum = min(node['byte_length'] for node in containers)
                                narrowest = sorted(node['id'] for node in containers if node['byte_length'] == minimum)
                                records.append({'text': raw.text, 'file': raw.source_file,
                                                'start_byte': raw.start_byte, 'end_byte': raw.end_byte,
                                                'status': record.status, 'original_source_id': record.source_id,
                                                'target_id': record.target_id,
                                                'has_type_only_candidate': any(binding.type_only for binding in raw.candidate_bindings),
                                                'smallest_declaration_ids': narrowest})
                        outputs[symbol_id] = {'gold_label': label, 'source': result['symbols'][0],
                                              'type_context': result['type_context'],
                                              'contained_reference_records': records}
                probes[case['id']] = {'entry_ids': endpoint_sets[case['id']][case['anchor']],
                                     'gold_relationships': case['relationships'], 'endpoint_probes': outputs}
    PROBES.write_text(json.dumps({'schema_version': 1,
                                 'meaning': 'Gold-seeded diagnostic source probes; excluded from all measured calls, source, cost and latency.',
                                 'candidate_source_tree': 'a7b0f5e94df1c25a8554a8119d3254d2c60771cc',
                                 'cases': probes}, indent=2) + '\n')

probes = json.loads(PROBES.read_text())['cases']
rows = []
for case in corpus['cases']:
    calls = []
    completed = []
    for repetition in (1, 2, 3):
        attempt = f"{case['id']}-r{repetition}-B"
        folder = RESULTS / attempt
        if not (folder / 'result.json').exists():
            continue
        completed.append(attempt)
        trace = json.loads((folder / 'adapter-trace.json').read_text())
        for delivery in trace['deliveries']:
            if delivery['operation'] != 'get':
                continue
            payload = json.loads(delivery['response_json'])
            context = payload.get('type_context')
            calls.append({'attempt_id': attempt, 'trace_event_id': delivery.get('trace_event_id'),
                          'requested_ids': delivery['arguments'].get('symbol_ids'),
                          'delivery_status': delivery['status'],
                          'type_context': context})
    contexts = [call['type_context'] for call in calls if call['type_context'] is not None]
    omissions = Counter()
    for context in contexts:
        omissions.update(context['omissions'])
    probe = probes[case['id']]
    entry = {symbol_id: probe['endpoint_probes'][symbol_id]['type_context'] for symbol_id in probe['entry_ids']}
    row = {'case_id': case['id'], 'group': case['group'], 'completed_B_attempts': completed,
           'actual_gets': calls, 'actual_omissions': dict(sorted(omissions.items())),
           'actual_added_definition_occurrences': sum(len(context['symbols']) for context in contexts),
           'actual_selected_reference_occurrences': sum(len(context['references']) for context in contexts),
           'actual_distinct_added_symbol_ids': sorted({symbol['id'] for context in contexts for symbol in context['symbols']}),
           'actual_distinct_requested_ids': sorted({symbol_id for call in calls for symbol_id in call['requested_ids']}),
           'diagnostic_entry_expansions': entry,
           'diagnostic_endpoint_probe_file': PROBES.name}
    rows.append(row)
output = {'schema_version': 1, 'complete': all(len(row['completed_B_attempts']) == 3 for row in rows),
          'scope': 'Actual B deliveries and separately labeled diagnostic get probes. Canonical edge IDs remain unchanged; selected reference occurrences are not semantic gold dependency-link recall.',
          'cases': rows}
Path('/tmp/loci-existing-residuals.json').write_text(json.dumps(output, indent=2) + '\n')
lines = ['# Existing-edge context delivery evidence', '', output['scope'], '',
         '| Case | Completed B runs | Added definition occurrences | Selected reference occurrences | Actual omissions |',
         '|---|---:|---:|---:|---|']
for row in rows:
    lines.append(f"| {row['case_id']} | {len(row['completed_B_attempts'])} | {row['actual_added_definition_occurrences']} | {row['actual_selected_reference_occurrences']} | {json.dumps(row['actual_omissions'])} |")
Path('/tmp/loci-existing-residuals.md').write_text('\n'.join(lines) + '\n')
print(json.dumps({'complete': output['complete'], 'cases': len(rows),
                  'completed_B_runs': sum(len(row['completed_B_attempts']) for row in rows),
                  'added_definition_occurrences': sum(row['actual_added_definition_occurrences'] for row in rows),
                  'selected_reference_occurrences': sum(row['actual_selected_reference_occurrences'] for row in rows)}))
