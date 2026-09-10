"""Focused runner controls; model-free request and delivery accounting checks."""
import copy
import json
from pathlib import Path

import pytest

from benchmarks.typescript_context_baseline import CATALOG_OVERRIDES, launch_args, measure, save
from benchmarks.typescript_context_corpus import load_corpus
from benchmarks.typescript_context_trace import ReadTrace, replay


def packet(tmp_path):
    corpus = load_corpus()
    case = corpus['cases'][0]
    trace = ReadTrace(corpus, case['id'], 'runner-test')
    result = {'symbols': [], 'search_id': None, '_evaluation': {'event_id': 'runner-test:1'}}
    trace.record(operation='search', reason='task_context', detail='Find requested function',
                 response_json=json.dumps(result, separators=(',', ':')), spans=[], elapsed_ms=1,
                 arguments={'query': 'processOrder'})
    run = {'case_id': case['id'], 'session_id': 'runner-test', 'arm': 'A', 'repetition': 1,
           'trace_path': str(tmp_path / 'trace.json')}
    save(Path(run['trace_path']), {'identity': trace.identity, 'events': trace.events, 'failures': [], 'attempts': 1})
    events = [{'type': 'thread.started', 'thread_id': 'provider-session'},
              {'type': 'item.completed', 'item': {'id': 'call', 'type': 'mcp_tool_call',
               'server': 'evaluation', 'tool': 'read', 'result': {'structured_content': result}, 'error': None}},
              {'type': 'item.completed', 'item': {'id': 'answer', 'type': 'agent_message', 'text': json.dumps(case['answer'])}},
              {'type': 'turn.completed', 'usage': {'input_tokens': 100, 'cached_input_tokens': 20,
               'output_tokens': 10, 'reasoning_output_tokens': 4}}]
    index = {'symbols': [], 'graph': {'nodes': [], 'edges': []}}
    return corpus, case, run, events, index


def test_effective_cli_arguments_keep_frozen_flags_and_toml_env(tmp_path):
    args = launch_args(tmp_path, {'mcp_servers.evaluation.env': {'LOCI_BASE_DIR': '/tmp/index'}}, 'exact prompt')
    assert args[-1] == 'exact prompt'
    assert '--ignore-user-config' in args and '--ephemeral' in args
    assert args[args.index('-m') + 1] == 'gpt-5.6-luna'
    assert args[args.index('--sandbox') + 1] == 'read-only'
    assert 'mcp_servers.evaluation.env={"LOCI_BASE_DIR"="/tmp/index"}' in args
    assert CATALOG_OVERRIDES == {'apply_patch_tool_type': None, 'tool_mode': 'direct',
                                'supports_search_tool': False, 'multi_agent_version': None}


def test_delivered_json_matches_trace_and_core_artifact_replays(tmp_path):
    corpus, case, run, events, index = packet(tmp_path)
    artifact = measure(corpus, case, run, events, 2.0, 0, False, index)
    assert artifact['measurement']['task_correct'] is True
    assert artifact['baseline']['tool_delivery_verified'] is True
    assert artifact['baseline']['provider_thread_id'] == 'provider-session'
    assert artifact['baseline']['end_to_end_seconds'] == 2
    assert replay(corpus, artifact) == artifact['measurement']


@pytest.mark.parametrize('mutation', ['missing', 'changed', 'other_server'])
def test_unaccounted_output_cannot_be_a_success(tmp_path, mutation):
    corpus, case, run, events, index = packet(tmp_path)
    if mutation == 'missing':
        events.pop(1)
    if mutation == 'changed':
        events[1]['item']['result']['structured_content']['extra'] = 'unaccounted'
    if mutation == 'other_server':
        events[1]['item']['server'] = 'ambient'
    artifact = measure(corpus, case, run, events, 2.0, 0, False, index)
    assert artifact['measurement']['task_correct'] is False
    assert artifact['baseline']['tool_delivery_verified'] is False


def test_timeout_and_reported_token_overshoot_retain_costs(tmp_path):
    corpus, case, run, events, index = packet(tmp_path)
    timed = measure(corpus, case, run, events, 183.2, -15, True, index)
    assert timed['measurement']['outcome'] == 'timeout'
    assert timed['baseline']['end_to_end_seconds'] == 180
    assert timed['baseline']['actual_process_seconds'] == 183.2
    assert timed['measurement']['read_count'] == 1
    events[-1]['usage']['input_tokens'] = 200001
    exceeded = measure(corpus, case, run, events, 2.0, 0, False, index)
    assert exceeded['measurement']['outcome'] == 'budget_exhausted'
    assert exceeded['measurement']['provider_usage']['input_tokens'] == 200001
    assert exceeded['measurement']['task_correct'] is False


def test_missing_tokens_are_not_invented_and_malformed_answer_fails(tmp_path):
    corpus, case, run, events, index = packet(tmp_path)
    events.pop()
    events[-1]['item']['text'] = 'not JSON'
    artifact = measure(corpus, case, run, events, 2.0, 0, False, index)
    assert artifact['measurement']['token_status'] == 'unavailable'
    assert artifact['measurement']['outcome'] == 'malformed_answer'
    assert artifact['measurement']['task_correct'] is False
