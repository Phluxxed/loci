"""Offline R0.5 delivery diagnosis. Never imported by acquisition policy."""
from collections import Counter
import gzip
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / '.scratch/r05-demand-semantics/results/full-source-demand/artifacts'


def edge_key(edge):
    proof = edge['evidence']
    return (edge['type'], edge['from'], edge['to'], proof['file'], proof['line'], proof['content_hash'])


def audit(repetition):
    rows = []
    for suite in (0, 1):
        directory = BASE / f'variant-{repetition}-suite-{suite}'
        capability = json.loads((directory / 'capability.json').read_text())
        worker = json.loads((directory / 'worker.json').read_text())
        cases = {case['case_id']: case for case in worker['cases']}
        for case in capability:
            gaps = [link for link in case['relationships']['available_dependency_links']
                    if link['available'] and not link['delivered']]
            if not gaps:
                continue
            record = cases[case['case_id']]
            index = json.loads(gzip.decompress((directory / record['index']).read_bytes()))
            packets = json.loads((directory / record['packets']).read_text())
            packet = next(item['structuredContent'] for item in packets
                          if item.get('structuredContent', {}).get('policy') == 'demand-semantic-v1')
            anchors = {anchor['node_id'] for anchor in packet['anchors']}
            eligible = set()
            for direction in ('forward', 'reverse'):
                frontier, visited = set(anchors), set(anchors)
                for _depth in (1, 2):
                    following = set()
                    for edge in index['graph']['edges']:
                        if ((direction == 'forward' and edge['from'] in frontier)
                                or (direction == 'reverse' and edge['to'] in frontier)):
                            eligible.add(edge_key(edge))
                            following.add(edge['to'] if direction == 'forward' else edge['from'])
                    frontier = following - visited
                    visited.update(following)
            failures = {edge_key(failure['edge']): failure['reason']
                        for failure in record['semantic_work'].get('proof_failures', [])}
            for link in gaps:
                matches = []
                for edge in link['available_edges']:
                    key = edge_key(edge)
                    failure = failures.get(key)
                    status = ('packet_capacity' if failure == 'proof exceeds packet budget'
                              else 'support_failure' if failure
                              else 'selection' if key not in eligible else 'unexplained')
                    matches.append({'edge': edge, 'eligible': key in eligible,
                                    'observer_failure': failure, 'status': status})
                statuses = sorted({match['status'] for match in matches})
                rows.append({'case_id': case['case_id'], 'required_link_index': link['index'],
                             'evaluator_context_from': link['from'], 'evaluator_context_to': link['to'],
                             'status': statuses[0] if len(statuses) == 1 else 'mixed',
                             'native_available': True, 'delivered': False, 'matches': matches,
                             'consumer_anchor_ids': sorted(anchors),
                             'packet_evidence_bytes': packet['usage']['evidence_bytes'],
                             'packet_output_bytes': packet['usage']['output_bytes'],
                             'work_omissions': record['semantic_work']['omissions'],
                             'artifacts': {name: str((directory / relative).relative_to(ROOT))
                                           for name, relative in [('capability', 'capability.json'),
                                                                  ('worker', 'worker.json'),
                                                                  ('index', record['index']),
                                                                  ('packets', record['packets'])]}})
    return {'repetition': repetition, 'missing_supported_links': len(rows),
            'counts': dict(sorted(Counter(row['status'] for row in rows).items())), 'links': rows}


if __name__ == '__main__':
    result = {'schema_version': 1,
              'method': 'Offline retained-artifact exact-edge join and reconstruction of native directional two-hop eligibility. Not acquisition policy.',
              'limits': 'Packet-capacity failure combines evidence and envelope limits; no per-attempt sizes were retained. Existing native support excludes absent-edge closure as the explanation for these links.',
              'repetitions': [audit(1), audit(2)]}
    target = Path(__file__).with_name('delivery-audit.json')
    target.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps([{'repetition': row['repetition'], 'counts': row['counts']} for row in result['repetitions']]))
