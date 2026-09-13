from __future__ import annotations

from copy import deepcopy

import pytest

from benchmarks.typescript_context_corpus import load_corpus
from benchmarks.typescript_context_explore_relationships import delivered_edges, score_relationships
from loci import service
from tests.reproductions.typescript_context_gaps import fixtures
from tests.test_type_relation_service import _setup


@pytest.mark.parametrize('name,fixture', fixtures().items())
def test_real_fixture_proofs_are_independently_verified(tmp_path, monkeypatch, name, fixture):
    repo, _ = _setup(tmp_path, monkeypatch, fixture['files'])
    index = service.get_store().load(repo.resolve())
    assert index is not None
    result = service.explore(repo, intent='type_dependencies', seed_ids=[fixture['anchor']])
    edges, violations = delivered_edges(index, [result, result])
    assert not violations
    assert len(edges) == len(result['relationships'])
    case = next(c for c in load_corpus()['cases'] if c['id'] == name)
    scored = score_relationships(case, index, [result])
    assert scored['forbidden_proven_relationships'] == 0
    if name == 'imported_interface':
        assert scored['delivered_dependency_links_total'] == 1
        assert scored['precise_kind_links_delivered_total'] == 0
        heritage_case = deepcopy(case)
        heritage_case['relationships'][0]['kind'] = 'extends'
        assert score_relationships(heritage_case, index, [result])['available_dependency_links_total'] == 0
    if name == 'local_heritage':
        assert scored['precise_kind_links_delivered_total'] == 2


@pytest.mark.parametrize('mutation', ['edge', 'missing_source', 'hash', 'proof_omission'])
def test_changed_relationship_or_missing_proof_cannot_receive_credit(tmp_path, monkeypatch, mutation):
    fixture = fixtures()['named_type_reexport_chain']
    repo, _ = _setup(tmp_path, monkeypatch, fixture['files'])
    index = service.get_store().load(repo.resolve())
    assert index is not None
    result = service.explore(repo, intent='type_dependencies', seed_ids=[fixture['anchor']])
    relation, = result['relationships']
    if mutation == 'edge':
        relation['edge']['resolution'] = 'exact'
    elif mutation == 'missing_source':
        relation['source_ids'] = [100000]
    elif mutation == 'hash':
        next(s for s in result['sources'] if s['id'] in relation['source_ids'])['content_hash'] = '0' * 64
    else:
        relation['source_ids'] = [s['id'] for s in result['sources']
                                  if s['id'] in relation['source_ids'] and s['file'] != 'barrel.ts']
    edges, violations = delivered_edges(index, [result])
    assert edges == []
    assert len(violations) == 1


def test_embedded_get_edges_are_verified_deduplicated_and_keep_direction(tmp_path, monkeypatch):
    fixture = fixtures()['imported_interface']
    repo, _ = _setup(tmp_path, monkeypatch, fixture['files'])
    index = service.get_store().load(repo.resolve())
    assert index is not None
    result = service.explore(repo, intent='type_dependencies', seed_ids=[fixture['anchor']])
    edge = result['relationships'][0]['edge']
    embedded = {'type_context': {'references': [{'edge': edge}]}}
    edges, violations = delivered_edges(index, [embedded, {'symbols': [embedded]}])
    assert edges == [edge] and not violations
    wrong = deepcopy(edge)
    wrong['from'], wrong['to'] = wrong['to'], wrong['from']
    edges, violations = delivered_edges(index, [{'type_context': {'references': [{'edge': wrong}]}}])
    assert not edges and len(violations) == 1


def test_authored_generic_negative_counts_uses_type(tmp_path, monkeypatch):
    fixture = fixtures()['generic_shadow']
    repo, _ = _setup(tmp_path, monkeypatch, fixture['files'])
    index = service.get_store().load(repo.resolve())
    assert index is not None
    case = next(c for c in load_corpus()['cases'] if c['id'] == 'generic_shadow')
    target = next(s for s in index['symbols'] if s['name'] == 'Payload' and s['kind'] == 'interface')
    edge = {'from': fixture['anchor'], 'to': target['id'], 'type': 'uses_type',
            'directed': True, 'namespace': 'loci', 'resolution': 'exact',
            'evidence': {'file': 'consumer.ts', 'line': 1, 'content_hash': 'fake'}}
    index['graph']['edges'].append(edge)
    scored = score_relationships(case, index, [])
    assert scored['forbidden_proven_relationships'] == 1


def test_imported_call_requires_joined_export_proof(tmp_path, monkeypatch):
    repo, _ = _setup(tmp_path, monkeypatch, {
        'target.ts': 'export function target(): number { return 1; }\n',
        'barrel.ts': 'export { target as publicTarget } from "./target.js";\n',
        'consumer.ts': 'import { publicTarget as imported } from "./barrel.js";\n'
                       'export function consume(): number { return imported(); }\n',
    })
    index = service.get_store().load(repo.resolve())
    assert index is not None
    result = service.explore(repo, intent='impact', seed_ids=['target.ts::target#function'])
    edges, violations = delivered_edges(index, [result])
    assert len(edges) == 1 and not violations
    relation = result['relationships'][0]
    relation['source_ids'] = [s['id'] for s in result['sources']
                              if s['id'] in relation['source_ids'] and s['file'] != 'barrel.ts']
    edges, violations = delivered_edges(index, [result])
    assert not edges and len(violations) == 1
