"""W2.4 source selection acceptance, independent of the packing implementation."""
from __future__ import annotations

import hashlib
import json

import pytest

from loci import service
from loci.exploration import explore_context
from tests.reproductions.typescript_context_gaps import fixtures
from tests.test_type_relation_service import _setup


def _names(result):
    return [item['name'] for item in result['items']]


def _reasons(result):
    return {item['reason']: item['count'] for item in result['omissions']}


def _verify_packet(repo, result):
    encoded = json.dumps({'content': [], 'structuredContent': result, 'isError': False},
                         ensure_ascii=False, separators=(',', ':')).encode('utf-8')
    assert len(encoded) == result['usage']['output_bytes'] <= result['limits']['max_output_bytes']
    assert result['usage']['evidence_bytes'] <= result['limits']['max_evidence_bytes']
    sources = {source['id']: source for source in result['sources']}
    relations = {relation['id']: relation for relation in result['relationships']}
    ids = {item['id'] for item in result['items']}
    for source in sources.values():
        raw = (repo / source['file']).read_bytes()
        assert source['content_hash'] == hashlib.sha256(raw).hexdigest()
        assert source['content'].encode('utf-8') == raw[source['start_byte']:source['end_byte']]
        assert source['start_line'] == raw[:source['start_byte']].count(b'\n') + 1
        assert source['end_line'] == raw[:source['end_byte'] - 1].count(b'\n') + 1
    for relation in relations.values():
        assert relation['edge']['from'] in ids and relation['edge']['to'] in ids
        assert relation['source_ids'] and len(set(relation['source_ids'])) == len(relation['source_ids'])
        assert all(source in sources for source in relation['source_ids'])
    for item in result['items']:
        assert item['source_id'] in sources
        assert item['depth'] == len(item['path'])
        assert all(relation in relations for relation in item['path'])
        if item['path']:
            final = relations[item['path'][-1]]
            assert final['edge']['to' if final['traversed'] == 'forward' else 'from'] == item['id']


@pytest.mark.parametrize('name,case', fixtures().items())
def test_frozen_source_cases_preserve_proven_types_and_negative_controls(tmp_path, monkeypatch, name, case):
    repo, _ = _setup(tmp_path, monkeypatch, case['files'])
    root = case['anchor']
    exact = service.get_symbols_result(repo, [root])
    result = service.explore(repo, intent='type_dependencies', seed_ids=[root])
    _verify_packet(repo, result)
    names = set(_names(result))
    if 'alias_chain' in name:
        assert names == {'processOrder', 'Second', 'First', 'Payload'}
    elif 'heritage' in name:
        assert names == {'Processor', 'Base', 'Contract'}
    elif case.get('targets'):
        assert {item['id'] for item in result['items']} == {root, *case['targets']}
    else:
        assert len(result['items']) == 1 and not result['relationships']
    if name in {'ambiguous_star_exports', 'generic_shadow'}:
        assert _reasons(result)['unresolved_relation'] > 0
        assert result['status'] == 'partial'
    assert exact == service.get_symbols_result(repo, [root])


def test_field_focus_prunes_siblings_including_generic_and_type_query_properties(tmp_path, monkeypatch):
    repo, _ = _setup(tmp_path, monkeypatch, {'a.ts':
        'interface Customer { id: string }; interface Audit { msg: string };\n'
        'type List<T> = T[]; const LEVELS = ["trace"] as const;\n'
        'interface Order { customer: Customer; audits: List<Audit>; levels: typeof LEVELS };\n'
        'function run(x: Order): void {}\n'})
    root = 'a.ts::run#function'
    result = service.explore(repo, 'Explain run customer', intent='type_dependencies', seed_ids=[root])
    assert _names(result) == ['run', 'Order', 'Customer']
    assert _reasons(result)['not_selected'] >= 2
    _verify_packet(repo, result)
    generic = service.explore(repo, 'run audits', intent='type_dependencies', seed_ids=[root])
    assert {'List', 'Audit'} <= set(_names(generic)) and 'Customer' not in _names(generic)
    value = service.explore(repo, 'run levels', intent='type_dependencies', seed_ids=[root])
    assert 'LEVELS' in _names(value) and 'Audit' not in _names(value)


def test_impact_reverses_stored_edges_and_defaults_to_one_hop(tmp_path, monkeypatch):
    repo, _ = _setup(tmp_path, monkeypatch, {'a.ts':
        'interface Payload { id: string }\nfunction take(x: Payload): void {}\n'
        'function first(x: Payload): void { take(x); }\nfunction second(): void { first({id:"x"}); }\n'})
    root = 'a.ts::take#function'
    one = service.explore(repo, intent='impact', seed_ids=[root])
    assert _names(one) == ['take', 'first']
    assert one['scope']['relationships'] == 'known_static_dependents' and not one['scope']['exhaustive']
    assert one['relationships'][0]['traversed'] == 'reverse'
    assert one['relationships'][0]['edge']['from'] == 'a.ts::first#function'
    two = service.explore(repo, intent='impact', seed_ids=[root], max_hops=2)
    assert 'second' in _names(two) and 'Payload' not in _names(two)
    _verify_packet(repo, two)


def test_resolution_narrowing_and_changed_import_target_are_honored(tmp_path, monkeypatch):
    case = fixtures()['imported_interface']
    repo, _ = _setup(tmp_path, monkeypatch, case['files'])
    root = case['anchor']
    assert len(service.explore(repo, intent='type_dependencies', seed_ids=[root])['items']) == 2
    assert len(service.explore(repo, intent='type_dependencies', seed_ids=[root], resolutions=['exact'])['items']) == 1
    assert len(service.explore(repo, intent='type_dependencies', seed_ids=[root], resolutions=[])['items']) == 1
    target = repo / 'types.ts'
    target.write_text('export interface Removed {}\n')
    changed = service.explore(repo, intent='type_dependencies', seed_ids=[root], ensure_fresh=True)
    assert _names(changed) == ['processOrder'] and _reasons(changed)['unresolved_relation'] == 1
    target.write_text(case['files']['types.ts'].replace('string', 'number'))
    restored = service.explore(repo, intent='type_dependencies', seed_ids=[root], ensure_fresh=True)
    assert 'Payload' in _names(restored)
    _verify_packet(repo, restored)


def test_imported_impact_hydrates_the_joined_reference_export_proof(tmp_path, monkeypatch):
    repo, _ = _setup(tmp_path, monkeypatch, {
        'target.ts': 'export function target(): number { return 1; }\n',
        'barrel.ts': 'export { target as publicTarget } from "./target.js";\n',
        'consumer.ts': 'import { publicTarget as imported } from "./barrel.js";\n'
                       'export function consume(): number { return imported(); }\n',
    })
    result = service.explore(repo, intent='impact', seed_ids=['target.ts::target#function'])
    assert _names(result) == ['target', 'consume']
    relation, = result['relationships']
    assert relation['edge']['type'] == 'calls' and relation['edge']['resolution'] == 'import-resolved'
    support = [s for s in result['sources'] if s['id'] in relation['source_ids']]
    assert any(s['file'] == 'barrel.ts' and 'publicTarget' in s['content'] for s in support)
    assert any('import { publicTarget as imported }' in s['content'] for s in support)
    _verify_packet(repo, result)
    store, nodes, state = service._load_graph_context(repo, ensure_fresh=False)
    cached = store._sources_dir(repo) / 'barrel.ts'
    cached.write_text(cached.read_text().replace('publicTarget', 'other'))
    stale = explore_context(repo, store, nodes, state, intent='impact', seed_ids=['target.ts::target#function'])
    assert _names(stale) == ['target'] and not stale['relationships']
    assert _reasons(stale)['source_unavailable'] > 0


def test_stale_cached_support_cannot_create_a_delivered_path(tmp_path, monkeypatch):
    case = fixtures()['named_type_reexport_chain']
    repo, _ = _setup(tmp_path, monkeypatch, case['files'])
    store, nodes, state = service._load_graph_context(repo, ensure_fresh=False)
    cached = store._sources_dir(repo) / 'barrel.ts'
    cached.write_text(cached.read_text().replace('PublicPayload', 'OtherPayload'))
    result = explore_context(repo, store, nodes, state, intent='type_dependencies', seed_ids=[case['anchor']])
    assert _names(result) == ['processOrder'] and not result['relationships']
    assert _reasons(result)['source_unavailable'] == 1


def test_imported_initializer_impact_keeps_the_declaring_type_proof(tmp_path, monkeypatch):
    repo, _ = _setup(tmp_path, monkeypatch, {
        'ticket.py': 'class Ticket:\n    def __init__(self):\n        self.id = 1\n',
        'consumer.py': 'from ticket import Ticket\n\ndef consume():\n    return Ticket()\n',
    })
    result = service.explore(repo, intent='impact', seed_ids=['ticket.py::Ticket.__init__#method'])
    assert _names(result) == ['__init__', 'consume']
    assert result['relationships'][0]['edge']['type'] == 'calls'
    assert any('class Ticket:' in s['content'] for s in result['sources'])
    _verify_packet(repo, result)


def test_unicode_clipping_and_zero_evidence_are_explicit(tmp_path, monkeypatch):
    repo, _ = _setup(tmp_path, monkeypatch, {'café.ts': 'function café(): void {\n' + '// 世界 π\n' * 1000 + '}\n'})
    root = 'café.ts::café#function'
    result = service.explore(repo, intent='locate', seed_ids=[root], max_output_bytes=2048)
    assert len(result['items']) == 1 and result['items'][0]['complete'] is False
    assert _reasons(result)['source_clipped'] == 1
    _verify_packet(repo, result)
    empty = service.explore(repo, intent='locate', seed_ids=[root], max_evidence_bytes=0)
    assert empty['status'] == 'empty' and not empty['sources']
    _verify_packet(repo, empty)


def test_missing_inferred_and_unsupported_explicit_anchors(tmp_path, monkeypatch):
    repo, _ = _setup(tmp_path, monkeypatch, {'a.py': 'def specialize_payload():\n    return 1\n'})
    inferred = service.explore(repo, 'specialize_payload', intent='locate')
    assert _names(inferred) == ['specialize_payload'] and inferred['selection'] == 'inferred'
    assert service.explore(repo, 'zxqvnonexistent', intent='locate')['status'] == 'empty'
    unsupported = service.explore(repo, intent='locate', seed_ids=['a.py::__file__#file'])
    assert unsupported['status'] == 'empty' and _reasons(unsupported)['unsupported_anchor'] == 1
    typed = service.explore(repo, intent='type_dependencies', seed_ids=['a.py::specialize_payload#function'])
    assert _reasons(typed)['unsupported_language'] == 1


@pytest.mark.parametrize('overrides', [
    {'intent': 'execute'}, {'intent': []}, {'query': 'π' * 2049}, {'seed_ids': 'bad'},
    {'seed_ids': ['a.ts::run#function'] * 2}, {'max_hops': True}, {'max_hops': 5},
    {'max_output_bytes': 2047}, {'max_evidence_bytes': -1}, {'resolutions': [[]]},
    {'resolutions': ['heuristic']},
])
def test_bad_inputs_return_structured_errors(tmp_path, monkeypatch, overrides):
    repo, _ = _setup(tmp_path, monkeypatch, {'a.ts': 'function run(): void {}\n'})
    args = {'intent': 'locate', 'seed_ids': ['a.ts::run#function'], **overrides}
    with pytest.raises(service.LociError) as error:
        service.explore(repo, **args)
    assert error.value.code == 'INVALID_INPUT'
    if 'intent' in overrides:
        assert error.value.details['fallback_intent'] == 'locate'


def test_cycle_neighbor_node_and_item_bounds_are_visible(tmp_path, monkeypatch):
    source = 'type A = B; type B = A;\n' + ''.join(f'interface I{i} {{ id: string }}\n' for i in range(40))
    source += 'function root(x: A, ' + ', '.join(f'x{i}: I{i}' for i in range(40)) + '): void {}\n'
    repo, _ = _setup(tmp_path, monkeypatch, {'a.ts': source})
    result = service.explore(repo, intent='type_dependencies', seed_ids=['a.ts::root#function'],
                             max_output_bytes=262144, max_evidence_bytes=65536)
    assert len(result['items']) <= 12 and result['usage']['nodes_examined'] <= 64
    assert _reasons(result)['neighbor_limit'] > 0 and _reasons(result)['item_limit'] > 0
    cyclic = service.explore(repo, intent='type_dependencies', seed_ids=['a.ts::A#type'])
    assert _reasons(cyclic)['cycle'] > 0
    _verify_packet(repo, result)
