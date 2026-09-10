"""Causal read accounting against real frozen gold; no model runs."""
import copy
import json

import pytest

from benchmarks.typescript_context_corpus import load_corpus
from benchmarks.typescript_context_trace import ReadTrace, replay


@pytest.fixture
def trace():
    return ReadTrace(load_corpus(), 'imported_interface', 'session-one')


def read(trace, context=None, *, operation='get', reason='task_context', because=None,
         arguments=None, payload=None):
    spans = []
    if context:
        gold = next(g for g in trace.case['context'] if g['id'] == context)
        text = trace.files[gold['file']][gold['start_byte']:gold['end_byte']].decode()
        spans = [{'file': gold['file'], 'start_byte': gold['start_byte'], 'text': text}]
        payload = {'source': text, **(payload or {})}
    return trace.record(operation=operation, reason=reason, detail='Explicit test read intent',
                        because=because, arguments=arguments, spans=spans,
                        response_json=json.dumps(payload or {}, ensure_ascii=False), elapsed_ms=2)


def report(trace, **kwargs):
    return trace.report(trace.case['answer'], **kwargs)


def test_declared_gap_search_and_selected_get_count_once_each(trace):
    anchor = read(trace, 'entry')
    search = read(trace, operation='search', reason='missing_context', because=anchor,
                  payload={'search_id': 'search-one', 'symbols': [{'id': 'payload-symbol'}]})
    read(trace, 'payload', reason='missing_context', because=search,
         arguments={'selected_from_search_id': 'search-one', 'symbol_ids': ['payload-symbol']})
    result = report(trace)
    assert result['avoidable_reads'] == 2
    assert result['task_correct'] is True
    assert result['context_recall'] == 2 / 3
    assert result['classifications'][1]['recovered_gold'] == ['payload']
    assert result['source_bytes'] == 159
    assert result['serialized_tool_output_bytes'] == sum(len(e['response_json'].encode()) for e in trace.events)
    assert result['estimated_source_tokens'] == 40
    assert result['tool_elapsed_ms'] == 6
    assert replay(trace.corpus, trace.artifact(trace.case['answer'])) == result


@pytest.mark.parametrize('reason', ['hydration', 'verification', 'setup', 'unrelated', 'task_context'])
def test_nearby_reads_are_not_causal_and_all_cost_counts(trace, reason):
    read(trace, 'entry')
    read(trace, 'payload', reason=reason)
    result = report(trace)
    assert result['avoidable_reads'] == 0
    assert result['read_count'] == 2
    assert result['source_bytes'] == 159


def test_missing_cause_is_unproven_never_a_zero_pass(trace):
    read(trace, 'entry')
    read(trace, 'payload', reason='missing_context')
    result = report(trace)
    assert result['avoidable_reads'] is None
    assert result['lineage_status'] == 'inconclusive'
    assert result['proven_avoidable_reads'] == 0


@pytest.mark.parametrize('reason', ['hydration', 'verification', 'setup', 'unrelated'])
def test_excluded_parent_cannot_manufacture_a_gap(trace, reason):
    parent = read(trace, 'entry', reason=reason)
    read(trace, 'payload', reason='missing_context', because=parent)
    assert report(trace)['avoidable_reads'] is None


def test_previous_delivery_and_repeat_are_not_new_missing_context(trace):
    root = read(trace, 'entry')
    read(trace, 'payload', reason='hydration')
    read(trace, 'payload', reason='missing_context', because=root)
    result = report(trace)
    assert result['avoidable_reads'] is None
    assert result['source_bytes'] == 227


def test_names_and_graph_edges_do_not_supply_source(trace):
    root = read(trace, 'entry')
    read(trace, operation='graph', reason='missing_context', because=root,
         payload={'target': 'Payload', 'kind': 'parameter_type'})
    result = report(trace)
    assert result['context_recall'] == 1 / 3
    assert result['avoidable_reads'] is None


def test_partial_fragments_count_only_when_complete(trace):
    root = read(trace, 'entry')
    gold = trace.case['context'][1]
    source = trace.files['types.ts'].decode()
    for start, end in [(0, 20), (20, gold['end_byte'])]:
        text = source[start:end]
        trace.record(operation='file', reason='missing_context', detail='Recover remaining type body',
                     because=root, spans=[{'file': 'types.ts', 'start_byte': start, 'text': text}],
                     response_json=json.dumps({'source': text}), elapsed_ms=1)
    # Sibling partial reads are not retrospectively assigned a causal chain.
    assert report(trace)['proven_avoidable_reads'] == 1
    assert report(trace)['lineage_status'] == 'inconclusive'
    assert report(trace)['context_recall'] == 2 / 3


@pytest.mark.parametrize('mutation', ['wrong_source', 'undelivered', 'wrong_path', 'offset'])
def test_source_evidence_must_match_delivery_and_snapshot(trace, mutation):
    text = trace.files['types.ts'].decode()
    span = {'file': 'types.ts', 'start_byte': 0, 'text': text}
    response = json.dumps({'source': text})
    if mutation == 'wrong_source':
        span['text'] += 'fabricated'
        response = json.dumps(span)
    if mutation == 'undelivered':
        response = '{}'
    if mutation == 'wrong_path':
        span['file'] = '../types.ts'
    if mutation == 'offset':
        span['start_byte'] = 1
    with pytest.raises(ValueError, match='source span'):
        trace.record(operation='file', reason='task_context', detail='source',
                     response_json=response, spans=[span], elapsed_ms=1)
    assert trace.events == []


def test_unknown_cross_session_and_future_causes_rejected(trace):
    other = ReadTrace(trace.corpus, 'imported_interface', 'other-session')
    foreign = read(other, 'entry')
    for parent in [foreign, 'session-one:2']:
        with pytest.raises(ValueError, match='earlier event'):
            read(trace, 'payload', reason='missing_context', because=parent)
    assert trace.events == []


def test_selection_lineage_is_separate_and_run_scoped(trace):
    read(trace, operation='search', payload={'search_id': 's', 'symbols': [{'id': 'one'}]})
    selection = {'selected_from_search_id': 's', 'symbol_ids': ['not-surfaced']}
    read(trace, 'payload', arguments=selection)
    assert report(trace)['avoidable_reads'] == 0
    with pytest.raises(ValueError, match='non-selection'):
        read(trace, 'payload', reason='hydration', arguments=selection)
    with pytest.raises(ValueError, match='earlier search'):
        read(trace, 'payload', arguments={**selection, 'selected_from_search_id': 'foreign'})


def test_tokens_are_measured_separately_and_failures_keep_cost(trace):
    read(trace, 'entry')
    assert report(trace)['provider_usage'] is None
    assert report(trace)['token_status'] == 'unavailable'
    usage = {'input_tokens': 100, 'cached_input_tokens': 20, 'output_tokens': 10, 'reasoning_tokens': 4}
    result = report(trace, usage=usage, usage_semantics='output_tokens includes reasoning_tokens', outcome='timeout')
    assert result['provider_usage'] == usage
    assert result['task_correct'] is False
    assert result['source_bytes'] == 91
    assert trace.report({'wrong': True})['task_correct'] is False
    with pytest.raises(ValueError, match='semantics'):
        report(trace, usage=usage)


@pytest.mark.parametrize('mutation', ['identity', 'bytes', 'classification', 'response'])
def test_replay_rejects_tampered_trace(trace, mutation):
    read(trace, 'entry')
    artifact = copy.deepcopy(trace.artifact(trace.case['answer']))
    if mutation == 'identity':
        artifact['events'][0]['task_id'] = 'other-task'
    if mutation == 'bytes':
        artifact['events'][0]['serialized_bytes'] = 0
    if mutation == 'classification':
        artifact['measurement']['avoidable_reads'] = 5
    if mutation == 'response':
        artifact['events'][0]['response_json'] = '{}'
    with pytest.raises(ValueError):
        replay(trace.corpus, artifact)


def test_real_service_selection_and_source_are_recorded(tmp_path, trace):
    from benchmarks.typescript_context_corpus import _isolated_store, materialize_snapshot
    from loci import service

    repo = tmp_path / 'source'
    materialize_snapshot(trace.corpus, trace.case['snapshot'], repo)
    with _isolated_store(tmp_path / 'store'):
        service.index_repo(repo, incremental=False)
        search = service.search_symbols_result(repo, 'processOrder', limit=5)
        trace.record(operation='search', reason='task_context', detail='Locate requested function',
                     response_json=json.dumps(search), spans=[], elapsed_ms=1)
        selected = next(s for s in search['symbols'] if s['name'] == 'processOrder')
        arguments = {'symbol_ids': [selected['id']], 'selected_from_search_id': search['search_id']}
        result = service.get_symbols(repo, **arguments)
        item = result[0]
        trace.record(operation='get', reason='task_context', detail='Read deliberate search selection',
                     arguments=arguments, response_json=json.dumps({'symbols': result}), elapsed_ms=1,
                     spans=[{'file': selected['file_path'], 'start_byte': item['byte_offset'], 'text': item['source']}])
    measurement = report(trace)
    # Exact gold includes the export wrapper/newline omitted by symbol get.
    assert measurement['required_context_delivered'] == []
    assert measurement['avoidable_reads'] == 0
    assert trace.events[-1]['arguments']['selected_from_search_id'] == search['search_id']

    read(trace, 'payload', reason='missing_context', because=trace.events[-1]['id'])
    assert report(trace)['avoidable_reads'] == 1
