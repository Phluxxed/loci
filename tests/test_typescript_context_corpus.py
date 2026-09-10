from copy import deepcopy
import hashlib
import json
from pathlib import Path
import shutil

import pytest

from benchmarks.typescript_context_corpus import (
    DEFAULT_ROOT, check_answer, load_controls, load_corpus, materialize_snapshot, preflight,
)


def _copy(tmp_path):
    root=tmp_path/'corpus'
    shutil.copytree(DEFAULT_ROOT,root)
    return root


def _write_manifest(root,manifest):
    raw=(json.dumps(manifest)+'\n').encode()
    (root/'corpus.json').write_bytes(raw)
    (root/'corpus.sha256').write_text(hashlib.sha256(raw).hexdigest()+'\n')


def test_frozen_corpus_is_complete_and_source_spans_are_verified():
    corpus=load_corpus()
    assert len(corpus['cases'])==17
    assert sum(c['group']=='maintained_task' for c in corpus['cases'])==3
    assert corpus['baseline_engine']['extractor_version']==24
    assert len(corpus['snapshots']['anvil']['files'])==187


@pytest.mark.parametrize('tamper',['manifest','archive','gold_span'])
def test_corruption_cannot_be_loaded(tmp_path,tamper):
    root=_copy(tmp_path)
    if tamper=='manifest':
        with (root/'corpus.json').open('a') as out:out.write(' ')
    elif tamper=='archive':
        path=root/'anvil.tar.gz'
        data=bytearray(path.read_bytes());data[-1]^=1;path.write_bytes(data)
    else:
        manifest=json.loads((root/'corpus.json').read_text())
        manifest['cases'][0]['context'][0]['sha256']='0'*64
        _write_manifest(root,manifest)
    with pytest.raises(ValueError,match='hash mismatch'):
        load_corpus(root)


def test_archive_inventory_remains_binding_even_with_a_new_manifest_checksum(tmp_path):
    root=_copy(tmp_path)
    manifest=json.loads((root/'corpus.json').read_text())
    manifest['snapshots']['anvil']['files'].pop('package.json')
    _write_manifest(root,manifest)
    with pytest.raises(ValueError,match='inventory mismatch'):
        load_corpus(root)


def test_materialization_preserves_real_repository_and_refuses_overwrite(tmp_path):
    corpus=load_corpus();destination=tmp_path/'anvil'
    materialize_snapshot(corpus,'anvil',destination)
    expected=corpus['snapshots']['anvil']['files']
    actual={str(p.relative_to(destination)):hashlib.sha256(p.read_bytes()).hexdigest()
            for p in destination.rglob('*') if p.is_file()}
    assert actual==expected
    assert (destination/'src/brain-context/render.ts').stat().st_size>10000
    with pytest.raises(ValueError,match='absent or empty'):
        materialize_snapshot(corpus,'anvil',destination)
    assert actual=={str(p.relative_to(destination)):hashlib.sha256(p.read_bytes()).hexdigest()
                   for p in destination.rglob('*') if p.is_file()}


@pytest.mark.parametrize(('case_id','field','wrong'),[
    ('generic_shadow','requires_imported_fields',True),
    ('same_name_wrong_file','origin_file','wrong.ts'),
    ('imported_alias_chain','alias_chain',['Second','Payload']),
    ('ambiguous_star_exports','unique_target','left.ts'),
    ('anvil_renderer_result_contract','matchedProject_for_v1','projects/anvil.md'),
    ('anvil_temporal_arguments','accepted_views',['current']),
])
def test_success_check_rejects_semantically_wrong_answers(case_id,field,wrong):
    corpus=load_corpus()
    correct=next(c['answer'] for c in corpus['cases'] if c['id']==case_id)
    assert check_answer(corpus,case_id,dict(reversed(list(correct.items()))))
    altered=deepcopy(correct);altered[field]=wrong
    assert not check_answer(corpus,case_id,altered)


def test_json_numbers_are_values_but_boolean_is_not_number():
    corpus=load_corpus()
    answer=deepcopy(next(c['answer'] for c in corpus['cases'] if c['id']=='exported_arrow'))
    answer['result']=1.0
    assert check_answer(corpus,'exported_arrow',answer)
    answer['result']=True
    assert not check_answer(corpus,'exported_arrow',answer)


def test_preflight_keeps_missing_endpoint_and_frozen_gold(tmp_path,monkeypatch):
    from loci.storage.index_store import IndexStore
    corpus=load_corpus();before=deepcopy(corpus)
    original=IndexStore.load
    def omit_payload(self,*args,**kwargs):
        result=original(self,*args,**kwargs)
        if result is not None:
            result=deepcopy(result)
            result['symbols']=[s for s in result['symbols'] if s['id']!='types.ts::Payload#interface']
        return result
    monkeypatch.setattr(IndexStore,'load',omit_payload)
    monkeypatch.setenv('LOCI_BASE_DIR','original-store-value')
    monkeypatch.setenv('LOCI_STORE_NAMESPACE','original-namespace')
    result=preflight(corpus)
    case=next(c for c in result['cases'] if c['id']=='imported_interface')
    endpoint=next(e for e in case['endpoints'] if e['id']=='payload')
    assert endpoint=={'id':'payload','status':'missing','symbol_ids':[]}
    assert len(result['cases'])==17
    assert corpus==before
    assert load_corpus()==before
    import os
    assert os.environ['LOCI_BASE_DIR']=='original-store-value'
    assert os.environ['LOCI_STORE_NAMESPACE']=='original-namespace'


def test_frozen_controls_bind_all_cases_without_starting_measurements():
    corpus = load_corpus()
    controls = load_controls(corpus)
    assert controls['schedule']['planned_runs'] == 153
    assert controls['case_ids'] == [case['id'] for case in corpus['cases']]
    assert controls['baseline_engine'] == corpus['baseline_engine']
    assert controls['measurement_status'].startswith('not_started')


@pytest.mark.parametrize('filename', ['comparison-controls.json', 'comparison-controls.md'])
def test_controls_and_protocol_corruption_are_rejected(tmp_path, filename):
    root = _copy(tmp_path)
    with (root / filename).open('a') as stream:
        stream.write(' ')
    with pytest.raises(ValueError, match='hash mismatch'):
        load_controls(load_corpus(root))


@pytest.mark.parametrize('change', [
    'corpus', 'baseline', 'case_order', 'arm_order', 'run_count', 'negative_limit', 'bool_limit',
])
def test_rehashed_controls_cannot_break_bound_corpus_or_schedule(tmp_path, change):
    root = _copy(tmp_path)
    controls = json.loads((root / 'comparison-controls.json').read_text())
    if change == 'corpus':
        controls['corpus_sha256'] = '0' * 64
    elif change == 'baseline':
        controls['baseline_engine']['extractor_version'] -= 1
    elif change == 'case_order':
        controls['case_ids'].reverse()
    elif change == 'arm_order':
        controls['schedule']['arm_orders'][0] = ['A', 'A', 'C']
    elif change == 'run_count':
        controls['schedule']['planned_runs'] -= 1
    else:
        controls['limits']['max_nodes'] = -1 if change == 'negative_limit' else True
    raw = (json.dumps(controls) + '\n').encode()
    (root / 'comparison-controls.json').write_bytes(raw)
    (root / 'comparison-controls.sha256').write_text(hashlib.sha256(raw).hexdigest() + '\n')
    with pytest.raises(ValueError):
        load_controls(load_corpus(root))
