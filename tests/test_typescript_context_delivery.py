"""V2 keeps all delivered costs without legitimising rejected read chains."""
import json
from pathlib import Path

import pytest

from loci import service
from benchmarks.typescript_context_adapter import Adapter, wire
from benchmarks.typescript_context_baseline import measure, save
from benchmarks.typescript_context_baseline_report import generate_report
from benchmarks.typescript_context_corpus import DEFAULT_ROOT, _isolated_store, load_corpus, materialize_snapshot
from benchmarks.typescript_context_delivery import payload_texts
from benchmarks.typescript_context_trace import replay

V2_ROOT = DEFAULT_ROOT.with_name('typescript-context-v2')


@pytest.fixture
def session(tmp_path):
    corpus = load_corpus(V2_ROOT)
    case = corpus['cases'][0]
    repo = tmp_path / 'snapshot'
    materialize_snapshot(corpus, case['snapshot'], repo)
    run = {'repo': str(repo), 'corpus_root': corpus['_root'], 'case_id': case['id'],
           'session_id': 'delivery-test', 'arm': 'A', 'repetition': 1,
           'trace_path': str(tmp_path / 'trace.json')}
    with _isolated_store(tmp_path / 'store'):
        service.index_repo(repo, incremental=False)
        index = service.get_store().load(repo.resolve())
        yield corpus, case, run, Adapter(run), index


def adapter_call(adapter, **arguments):
    result = adapter.read(**arguments)
    return {'id': f'call-{adapter.attempts}', 'type': 'mcp_tool_call', 'server': 'evaluation',
            'tool': 'read', 'arguments': arguments, 'status': 'completed', 'error': None,
            'result': {'content': [], 'structured_content': result.structured_content}}


def text_call(text, *, tool='list_mcp_resources', server='codex', status='completed'):
    return {'id': 'host-call', 'type': 'mcp_tool_call', 'server': server,
            'tool': tool, 'arguments': {}, 'status': status, 'error': None,
            'result': {'structured_content': None, 'content': [{'type': 'text', 'text': text}]}}


def score(session, calls):
    corpus, case, run, adapter, index = session
    events = [{'type': 'item.completed', 'item': call} for call in calls]
    events += [
        {'type': 'item.completed', 'item': {'type': 'agent_message', 'text': json.dumps(case['answer'])}},
        {'type': 'turn.completed', 'usage': {'input_tokens': 1000, 'cached_input_tokens': 200, 'output_tokens': 30}},
    ]
    return measure(corpus, case, run, events, 3.0, 0, False, index)


def test_helper_output_counts_without_changing_core_replay(session):
    corpus, _, _, adapter, _ = session
    read = adapter_call(adapter, operation='file', parameters={'file_path': 'consumer.ts'},
                        reason='task_context', detail='Read the function and import')
    helper = text_call('{"resources":[]}')
    artifact = score(session, [read, helper])
    accounting = artifact['baseline']['output_accounting']
    assert accounting['complete'] is True
    assert accounting['complete_payload_bytes'] == len(wire(read['result']['structured_content']).encode()) + len('{"resources":[]}'.encode())
    assert accounting['tool_call_count'] == 2
    assert artifact['measurement']['read_count'] == 1
    assert artifact['measurement']['task_correct'] is True
    assert replay(corpus, artifact) == artifact['measurement']


def test_invalid_lineage_is_fully_costed_but_still_failed_and_inconclusive(session, tmp_path):
    corpus, case, _, adapter, _ = session
    rejected = adapter_call(adapter, operation='file', parameters={'file_path': 'types.ts'},
                            reason='missing_context', detail='Read missing type', because='made-up-parent')
    valid = adapter_call(adapter, operation='file', parameters={'file_path': 'consumer.ts'},
                         reason='task_context', detail='Read the function')
    helper = text_call('{"resources":[]}')
    artifact = score(session, [rejected, valid, helper])
    accounting = artifact['baseline']['output_accounting']
    assert accounting['complete'] is True
    assert accounting['tool_call_count'] == 3
    assert artifact['baseline']['tool_delivery_verified'] is True
    assert artifact['baseline']['lineage_valid'] is False
    assert artifact['measurement']['task_correct'] is False
    assert artifact['measurement']['outcome'] == 'tool_failure'
    assert artifact['measurement']['source_bytes'] == len(adapter.trace.files['consumer.ts'])
    assert artifact['measurement']['provider_usage']['input_tokens'] == 1000
    assert replay(corpus, artifact) == artifact['measurement']
    result = tmp_path / 'report' / (case['id'] + '-r1') / 'result.json'
    result.parent.mkdir(parents=True)
    save(result, artifact)
    summary = generate_report(result.parent.parent, V2_ROOT)
    assert summary['costs']['serialized_tool_output_bytes']['total'] == accounting['complete_payload_bytes']
    assert summary['cases'][0]['medians']['read_count']['values'] == [3]
    assert summary['context_and_causality']['avoidable_reads']['values'] == [None]
    with pytest.raises(ValueError, match='protocol differs'):
        generate_report(result.parent.parent)


def test_host_schema_error_text_and_provider_costs_are_retained(session):
    error = text_call('Error executing tool read: invalid opération', tool='read', server='evaluation', status='failed')
    artifact = score(session, [error])
    accounting = artifact['baseline']['output_accounting']
    assert accounting['complete'] is True
    assert accounting['complete_payload_bytes'] == len(error['result']['content'][0]['text'].encode())
    assert artifact['measurement']['task_correct'] is False
    assert artifact['measurement']['provider_usage']['input_tokens'] == 1000


def test_resource_read_host_error_message_is_counted_and_failed(session):
    message = 'resources/read failed: Unknown resource: missing://probe'
    call = text_call('', tool='read_mcp_resource', server='evaluation', status='failed')
    call.update(result=None, error={'message': message})
    assert payload_texts(call) == ('host_error', [message])
    artifact = score(session, [call])
    assert artifact['baseline']['output_accounting']['complete_payload_bytes'] == len(message.encode())
    assert artifact['baseline']['output_accounting']['complete'] is True
    assert artifact['measurement']['task_correct'] is False


@pytest.mark.parametrize('mutation', ['response', 'source', 'arguments', 'attempt'])
def test_delivery_mismatch_never_becomes_complete_accounting(session, mutation):
    _, _, run, adapter, _ = session
    call = adapter_call(adapter, operation='file', parameters={'file_path': 'consumer.ts'},
                        reason='task_context', detail='Read the function')
    raw = json.loads(Path(run['trace_path']).read_text())
    if mutation == 'response':
        raw['deliveries'][0]['response_json'] = '{}'
    elif mutation == 'source':
        raw['deliveries'][0]['source_bytes'] += 1
    elif mutation == 'arguments':
        call['arguments']['parameters'] = {'file_path': 'types.ts'}
    else:
        raw['deliveries'][0]['attempt_id'] = 'another-session/attempt/1'
    save(Path(run['trace_path']), raw)
    artifact = score(session, [call])
    assert artifact['baseline']['output_accounting']['complete'] is False
    assert artifact['baseline']['output_accounting']['complete_payload_bytes'] is None
    assert artifact['measurement']['task_correct'] is False


def test_resource_helpers_count_against_overall_call_budget(session):
    calls = [{**text_call('{"resources":[]}'), 'id': f'host-{i}'} for i in range(25)]
    artifact = score(session, calls)
    assert artifact['baseline']['output_accounting']['tool_call_count'] == 25
    assert artifact['baseline']['output_accounting']['complete_payload_bytes'] == 25 * len('{"resources":[]}')
    assert artifact['measurement']['outcome'] == 'budget_exhausted'
    assert artifact['measurement']['task_correct'] is False


def test_unverified_content_representation_is_unavailable(session):
    call = text_call('unused')
    call['result']['content'] = [{'type': 'image', 'data': 'unverified'}]
    with pytest.raises(ValueError, match='representation'):
        payload_texts(call)
    artifact = score(session, [call])
    assert artifact['baseline']['output_accounting']['complete_payload_bytes'] is None
    assert artifact['measurement']['task_correct'] is False
