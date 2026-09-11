"""Source-backed v2 requirements and preservation of the historical protocol."""
import copy
import hashlib
import json
from pathlib import Path

import pytest

from loci import service
from benchmarks.typescript_context_corpus import (
    DEFAULT_ROOT, _isolated_store, _snapshot_files, check_answer, load_controls,
    load_corpus, materialize_snapshot,
)
from benchmarks.typescript_context_trace import ReadTrace, replay

V2_ROOT = DEFAULT_ROOT.with_name('typescript-context-v2')


def record_span(trace, gold, *, reason='task_context', because=None, bounds=None, file=None):
    file = file or gold['file']
    start, end = bounds or (gold['start_byte'], gold['end_byte'])
    source = trace.files[file][start:end].decode()
    return trace.record(operation='get', reason=reason, detail='Read required declaration',
                        response_json=json.dumps({'source': source}), elapsed_ms=1,
                        spans=[{'file': file, 'start_byte': start, 'text': source}], because=because)


def test_v2_changes_questions_without_changing_source_or_acceptance():
    old, new = load_corpus(), load_corpus(V2_ROOT)
    before, after = load_controls(old), load_controls(new)
    assert new['snapshots'] == old['snapshots']
    assert new['baseline_engine'] == old['baseline_engine']
    assert after['acceptance'] == before['acceptance']
    assert after['limits'] == before['limits']
    assert after['schedule'] == before['schedule']
    assert [c['id'] for c in new['cases']] == [c['id'] for c in old['cases']]
    for case in new['cases']:
        prior = next(c for c in old['cases'] if c['id'] == case['id'])
        answer = copy.deepcopy(prior['answer'])
        if case['group'] == 'endpoint_control':
            answer['declared_parameter_type'] = answer.pop('argument_type')
            wrong = {**answer, 'declared_parameter_type': 'number'}
            assert not check_answer(new, case['id'], wrong)
            assert 'number.ts' not in case['prompt']
        if case['id'] == 'anvil_retrieval_limits':
            answer['emitted_message_keys'] = answer.pop('message_keys')
            wrong = {**answer, 'emitted_message_keys': answer['emitted_message_keys'] + ['problem']}
            assert not check_answer(new, case['id'], wrong)
            assert all(g['id'] != 'evidence' for g in case['context'])
        assert case['answer'] == answer
        assert check_answer(new, case['id'], answer)


def test_exact_body_recovery_counts_but_missing_import_is_visible():
    corpus = load_corpus(V2_ROOT)
    trace = ReadTrace(corpus, 'imported_interface', 'body-recovery')
    gold = {g['id']: g for g in trace.case['context']}
    parent = record_span(trace, gold['entry'])
    record_span(trace, gold['payload'], reason='missing_context', because=parent)
    result = trace.report(trace.case['answer'])
    assert result['avoidable_reads'] == 1
    assert result['required_context_delivered'] == ['entry', 'payload']
    assert result['context_recall'] < 1
    assert replay(corpus, trace.artifact(trace.case['answer'])) == result


def test_missing_member_and_wrong_file_cannot_satisfy_source_requirement():
    corpus = load_corpus(V2_ROOT)
    trace = ReadTrace(corpus, 'same_name_wrong_file', 'missing-member')
    gold = {g['id']: g for g in trace.case['context']}
    parent = record_span(trace, gold['entry'])
    payload = gold['payload']
    missing = trace.files[payload['file']].index(b'amount: number')
    record_span(trace, payload, reason='missing_context', because=parent,
                bounds=(payload['start_byte'], missing))
    record_span(trace, payload, reason='missing_context', because=parent,
                bounds=(missing + len(b'amount: number'), payload['end_byte']))
    # Even a complete same-named declaration in the distractor file is not gold.
    distractor = next(f for f in trace.files if f not in {g['file'] for g in trace.case['context']})
    record_span(trace, payload, bounds=(0, len(trace.files[distractor])), file=distractor)
    result = trace.report(trace.case['answer'])
    assert 'payload' not in result['required_context_delivered']
    assert result['avoidable_reads'] is None
    assert result['lineage_status'] == 'inconclusive'


@pytest.mark.parametrize('case_id', ['exported_arrow', 'named_function_control', 'inline_default_control'])
def test_callee_body_and_export_origin_are_independent_requirements(case_id):
    corpus = load_corpus(V2_ROOT)
    trace = ReadTrace(corpus, case_id, 'export-origin')
    gold = {g['id']: g for g in trace.case['context']}
    record_span(trace, gold['callee'])
    assert trace.report(trace.case['answer'])['required_context_delivered'] == ['callee']
    record_span(trace, gold['callee_export'])
    assert trace.report(trace.case['answer'])['required_context_delivered'] == ['callee', 'callee_export']


def test_real_temporal_declaration_gets_cover_v2_bodies(tmp_path):
    corpus = load_corpus(V2_ROOT)
    trace = ReadTrace(corpus, 'anvil_temporal_arguments', 'actual-get')
    repo = tmp_path / 'snapshot'
    materialize_snapshot(corpus, trace.case['snapshot'], repo)
    with _isolated_store(tmp_path / 'index'):
        service.index_repo(repo, incremental=False)
        for gold in trace.case['context']:
            symbol = gold['symbol']
            symbol_id = f"{gold['file']}::{symbol['name']}#{symbol['kind']}"
            result = {'symbols': service.get_symbols(repo, [symbol_id])}
            found = result['symbols'][0]
            trace.record(operation='get', reason='task_context', detail='Read declaration body',
                         response_json=json.dumps(result), elapsed_ms=1,
                         spans=[{'file': gold['file'], 'start_byte': found['byte_offset'], 'text': found['source']}])
    assert trace.report(trace.case['answer'])['context_recall'] == 1


def test_historical_artifact_files_and_strict_replays_are_unchanged():
    root = DEFAULT_ROOT.parents[1] / 'results' / 'typescript-context-baseline-v1'
    inventory = json.loads((root / 'artifact-sha256.json').read_text())
    # The recorded inventory includes all historical artifacts except itself.
    entries = inventory.get('files', inventory)
    for name, digest in entries.items():
        assert hashlib.sha256((root / name).read_bytes()).hexdigest() == digest
    corpus = load_corpus()
    results = list(root.glob('*/result.json'))
    assert len(results) == 51
    for path in results:
        artifact = json.loads(path.read_text())
        assert replay(corpus, artifact) == artifact['measurement']
