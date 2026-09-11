from copy import deepcopy
import json

import pytest

from benchmarks import typescript_context_compare as prior
from benchmarks import typescript_context_explore as runner
from benchmarks.typescript_context_corpus import load_corpus
from benchmarks.typescript_context_explore_replay import verify_request
from benchmarks.typescript_context_explore_transport import audit_request, tool_names


def test_schedule_pairs_all_original_cases_without_retry_and_alternates_order():
    corpus = load_corpus(runner.CORPUS_ROOT)
    plan = runner.schedule(corpus)
    assert len(plan) == len({row['attempt_id'] for row in plan}) == 102
    pairs = [plan[offset:offset + 2] for offset in range(0, 102, 2)]
    assert sum(pair[0]['arm'] == 'A' for pair in pairs) == 26
    assert sum(pair[0]['arm'] == 'B' for pair in pairs) == 25
    for ordinal, pair in enumerate(pairs):
        assert {row['arm'] for row in pair} == {'A', 'B'}
        assert pair[0]['case_id'] == pair[1]['case_id'] == corpus['cases'][ordinal // 3]['id']
        assert pair[0]['repetition'] == pair[1]['repetition'] == ordinal % 3 + 1
        if ordinal:
            assert pair[0]['arm'] != pairs[ordinal - 1][0]['arm']


@pytest.mark.parametrize('fail', [False, True])
def test_shared_lifecycle_selects_new_adapter_and_restores_scoped_overrides(monkeypatch, tmp_path, fail):
    # Exercise the integration seam without starting a provider process.
    monkeypatch.setattr(runner, 'verify_engine', lambda _: None)
    modules, callback = prior.ARM_MODULES, prior._source_provenance
    freeze = {'engine': {'commit': 'engine', 'source_tree': 'tree', 'extractor_version': 25},
              'freeze_commit': 'harness', 'freeze_json_sha256': 'freeze',
              'canonical_tool_schemas_sha256': {'A': 'schema-a', 'B': 'schema-b'}}

    def lifecycle(**kwargs):
        assert prior.ARM_MODULES == {'A': runner.TOOLS_MODULE, 'B': runner.TOOLS_MODULE}
        assert kwargs['expected_schema_hash'] == 'schema-b'
        assert prior._source_provenance({}, {})['engine'] == freeze['engine']
        if fail:
            raise ValueError('retained failure')
        return {'worked': True}

    monkeypatch.setattr(prior, '_run_attempt', lifecycle)
    if fail:
        with pytest.raises(ValueError, match='retained failure'):
            runner.run_attempt({}, {}, {'arm': 'B'}, tmp_path, tmp_path / 'catalog', freeze)
    else:
        assert runner.run_attempt({}, {}, {'arm': 'B'}, tmp_path, tmp_path / 'catalog', freeze) == {'worked': True}
    assert prior.ARM_MODULES is modules and prior._source_provenance is callback


def _request(arm):
    return {'model': 'gpt-5.6-luna', 'reasoning': {'effort': 'high'}, 'input': [
        {'type': 'additional_tools', 'tools': [
            {'type': 'namespace', 'name': 'mcp__evaluation', 'tools': [{'name': name} for name in sorted(tool_names(arm))]},
            {'type': 'namespace', 'name': 'functions', 'tools': [{'name': name} for name in
                ('list_mcp_resources', 'list_mcp_resource_templates', 'read_mcp_resource')]},
        ]},
        {'type': 'message', 'content': [{'type': 'input_text', 'text': 'frozen prompt'}]},
    ]}


@pytest.mark.parametrize('arm', ['A', 'B'])
def test_request_audit_replay_agrees_and_rejects_effective_prompt_change(arm):
    from benchmarks.typescript_context_adapter import wire
    request = _request(arm)
    audited = audit_request(request, 'frozen prompt', arm)
    provenance = {'canonical_tool_schemas_sha256': audited['canonical_tool_schemas_sha256'],
                  'prompt_sha256': runner.sha(b'frozen prompt'), 'config': {},
                  'config_sha256': runner.sha(wire({}).encode())}
    verify_request(audited, provenance, 'frozen prompt', arm, audited['canonical_tool_schemas_sha256'])
    changed = deepcopy(audited)
    changed['request']['input'][-1]['content'][0]['text'] = 'changed prompt'
    with pytest.raises(ValueError, match='prompt'):
        verify_request(changed, provenance, 'frozen prompt', arm, audited['canonical_tool_schemas_sha256'])


def test_duplicate_or_cross_arm_workflow_tool_cannot_pass_request_audit():
    with pytest.raises(ValueError, match='tool set'):
        audit_request(_request('B'), 'frozen prompt', 'A')
    request = _request('B')
    request['input'][0]['tools'][0]['tools'].append({'name': 'loci_explore'})
    with pytest.raises(ValueError, match='tool set'):
        audit_request(request, 'frozen prompt', 'B')


@pytest.mark.parametrize('replay_fails', [False, True])
def test_batch_completion_waits_for_independent_replay(monkeypatch, tmp_path, replay_fails):
    from benchmarks import typescript_context_explore_replay as replay
    from benchmarks import typescript_context_explore_report as report
    corpus = load_corpus(runner.CORPUS_ROOT)
    freeze = {'plan': runner.schedule(corpus), 'canonical_tool_schemas_sha256': {'A': 'a', 'B': 'b'}}
    protocol = tmp_path / 'protocol'
    protocol.mkdir()
    for name in ('model-catalog.json', 'model-catalog-provenance.json'):
        (protocol / name).write_text('{}')
    monkeypatch.setattr(runner, 'COMPARISON_ROOT', protocol)
    monkeypatch.setattr(runner, 'validate_freeze', lambda _: freeze)
    monkeypatch.setattr(runner, 'environment', lambda _: {})
    monkeypatch.setattr(runner, 'command', lambda _: 'codex-cli 0.154.0')
    order = []

    def attempt(*args):
        order.append('attempt')
        return {'measurement': {'task_correct': True, 'read_count': 1,
                                'outcome': 'completed', 'measurement_complete': True}}

    def verify(output):
        assert order == ['attempt'] * 102
        order.append('replay')
        # A failed fresh replay must override even a stale successful status.
        runner.save(output / 'replay-verification.json', {'complete': True, 'comparison': runner.COMPARISON})
        if replay_fails:
            raise ValueError('independent replay failed')
        return {'complete': True}

    def generate(output, *_):
        assert order[-1] == 'replay'
        assert not (output / 'completion.json').exists()
        order.append('report')
        complete = json.loads((output / 'replay-verification.json').read_text())['complete']
        return {'replay_complete': complete, 'verdict': 'keep',
                'qualification_verdict': 'keep' if complete else 'inconclusive'}

    monkeypatch.setattr(runner, 'run_attempt', attempt)
    monkeypatch.setattr(replay, 'verify', verify)
    monkeypatch.setattr(report, 'generate_report', generate)
    output = tmp_path / 'results'
    runner.run_batch(protocol / 'freeze.json', output)
    completion = json.loads((output / 'completion.json').read_text())
    assert completion['replay_complete'] is not replay_fails
    assert completion['verdict'] == ('inconclusive' if replay_fails else 'keep')
    assert order[-2:] == ['replay', 'report']
