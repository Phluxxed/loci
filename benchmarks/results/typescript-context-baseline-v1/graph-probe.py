"""Gold-seeded direct graph capability probes, outside all 51 agent metrics."""
import argparse
import json
import signal
import tempfile
import time
from pathlib import Path

from benchmarks.typescript_context_baseline import ROOT, environment, sha, wire
from benchmarks.typescript_context_corpus import load_corpus, load_controls, materialize_snapshot, _isolated_store
from loci import service
from loci.storage.index_store import EXTRACTOR_VERSION

base = Path(__file__).resolve().parent
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--output', type=Path, default=base / 'explicit-graph-probes.json')
args = parser.parse_args()
if args.output.exists():
    raise ValueError('preserve recorded evidence; choose a new --output path')
corpus = load_corpus()
controls = load_controls(corpus)
environment(controls)
preflight = json.loads((base / 'preflight.json').read_text())
endpoints = {case['id']: {item['id']: item for item in case['endpoints']} for case in preflight['cases']}
rows = []
case_records = []

def deadline(_signal, _frame):
    raise TimeoutError('ten-second graph operation deadline')

for case in corpus['cases']:
    with tempfile.TemporaryDirectory(prefix='loci-direct-graph-') as temporary:
        temp = Path(temporary)
        repo = temp / 'snapshot'
        materialize_snapshot(corpus, case['snapshot'], repo)
        started = time.monotonic()
        with _isolated_store(temp / 'store'):
            service.index_repo(repo, incremental=False)
            index_seconds = time.monotonic() - started
            for ordinal, relationship in enumerate(case['relationships']):
                source = endpoints[case['id']][relationship['from']]
                target = endpoints[case['id']][relationship['to']]
                row = {'case_id': case['id'], 'relationship_ordinal': ordinal,
                       'relationship': relationship, 'source_endpoint': source, 'target_endpoint': target}
                if source['status'] != 'indexed' or target['status'] != 'indexed':
                    row.update(status='skipped_endpoint_unavailable', path_count=0)
                else:
                    edge_types = ['calls'] if relationship['kind'] == 'calls' else ['references_type']
                    parameters = dict(source_ids=source['symbol_ids'], target_ids=target['symbol_ids'],
                                      direction='outgoing', resolutions=['exact', 'declared', 'import-resolved'],
                                      edge_types=edge_types, path_offset=0,
                                      max_estimated_tokens=controls['limits']['max_estimated_evidence_tokens'])
                    parameters.update({k: controls['limits'][k] for k in
                                       ('max_hops', 'max_nodes', 'max_paths', 'max_evidence_bytes')})
                    row['parameters'] = parameters
                    row['semantic_scope'] = 'exact calls' if edge_types == ['calls'] else 'generic type adjacency, not precise subtype semantics'
                    started = time.monotonic()
                    previous = signal.signal(signal.SIGALRM, deadline)
                    signal.setitimer(signal.ITIMER_REAL, controls['limits']['max_retrieval_seconds_per_operation'])
                    try:
                        result = service.graph_paths(repo, **parameters)
                        row.update(status='returned', result=result, path_count=len(result['paths']),
                                   serialized_bytes=len(wire(result).encode()))
                        row['within_serialized_operation_cap'] = row['serialized_bytes'] <= controls['limits']['max_serialized_output_bytes_per_operation']
                    except Exception as exc:
                        row.update(status='error', error={'type': type(exc).__name__, 'message': str(exc)}, path_count=0)
                    finally:
                        signal.setitimer(signal.ITIMER_REAL, 0)
                        signal.signal(signal.SIGALRM, previous)
                        row['elapsed_ms'] = (time.monotonic() - started) * 1000
                rows.append(row)
        case_records.append({'case_id': case['id'], 'snapshot': case['snapshot'],
                             'snapshot_files': corpus['snapshots'][case['snapshot']]['files'],
                             'index_seconds': index_seconds, 'relationship_count': len(case['relationships'])})
assert len(case_records) == 17
assert len(rows) == sum(len(case['relationships']) for case in corpus['cases'])
value = {'kind': 'evaluator_gold_seeded_capability_probes',
         'meaning': 'Direct existing graph retrieval with gold-selected endpoints. Not blind agent measurements; excluded from the 51-run cost, quality and latency totals.',
         'created_at_utc': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
         'baseline_engine': controls['baseline_engine'], 'baseline_source_tree': controls['baseline_source_tree'],
         'extractor_version': EXTRACTOR_VERSION, 'probe_script_sha256': sha(Path(__file__).read_bytes()),
         'corpus_sha256': preflight['corpus_sha256'],
         'controls_sha256': sha((Path(corpus['_root']) / 'comparison-controls.json').read_bytes()),
         'preflight_sha256': sha((base / 'preflight.json').read_bytes()),
         'summary': {'cases': len(case_records), 'relationships': len(rows),
                     'relationships_with_paths': sum(row['path_count'] > 0 for row in rows),
                     'errors': sum(row['status'] == 'error' for row in rows),
                     'skipped': sum(row['status'].startswith('skipped') for row in rows)},
         'cases': case_records, 'probes': rows}
args.output.write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + '\n')
print(json.dumps(value['summary']))
