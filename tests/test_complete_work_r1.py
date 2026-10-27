"""Prospective binding, native host command, and archived independent replay."""
import json
import hashlib
from pathlib import Path
import subprocess

import pytest

from benchmarks.complete_work import availability, r0, r1
from benchmarks.complete_work.evaluate import source_snapshot, write_json


def _freeze(tmp_path: Path) -> Path:
    config = tmp_path / 'config.toml'
    config.write_text('default_permissions="existing"\n')
    host = tmp_path / 'codex'
    host.write_text('existing native executable')
    tasks = []
    for number in range(4):
        folder = tmp_path / f'task-{number}'
        folder.mkdir()
        source = folder / 'source'
        source.mkdir()
        (source / 'original.js').write_text('export const n=1;\n')
        prompt = folder / 'prompt.txt'
        prompt.write_text('Read original.js; write answer.json.\n')
        oracle = folder / 'oracle.mjs'
        oracle.write_text("import fs from 'node:fs';import assert from 'node:assert/strict';assert.deepEqual(JSON.parse(fs.readFileSync(process.argv[2]+'/answer.json')),{n:1});\n")
        tasks.append({'id':f'task-{number}', 'source':str(source),'prompt':str(prompt),
                      'oracle':str(oracle), 'criteria':{'allowed_changes':['answer.json']}})
    conditions = {name:{'command':'python','args':['-m','loci.integrated_mcp'],
                         'env':{'LOCI_R1_STORE':'{store}'},'tools':availability.TOOLS_BY_CONDITION[name]}
                  for name in r1.CONDITIONS}
    plan = {'tasks':tasks,'native_config':str(config), 'conditions':conditions,
            'model':'gpt-6.1-sol','effort':'high',
            'native_protection':{field:None for field in r0.PROTECTION_FIELDS},
            'host':{'executable':str(host),'sha256':r0.digest(host)}}
    plan_path = tmp_path / 'plan.json'
    write_json(plan_path,plan)
    r1.freeze(plan_path,tmp_path/'frozen')
    return tmp_path/'frozen/freeze.json'


@pytest.fixture(autouse=True)
def native_gate_for_existing_snapshot_unit_checks(monkeypatch):
    # These existing tests isolate snapshots, pinning and the native launcher.
    # Real fail-closed gate integration has separate no-bypass tests below.
    monkeypatch.setattr(r1, 'require_availability', lambda frozen, gate: {
        'path': '/unit-test-only/gate.json', 'sha256': 'f' * 64, 'threads': [],
        'deterministic_gate_sha256': hashlib.sha256((json.dumps({'status': 'passed'}, indent=2, sort_keys=True) + '\n').encode()).hexdigest()})


def test_freeze_is_balanced_and_source_copies_are_independent(tmp_path):
    path = _freeze(tmp_path)
    frozen = r1.read_freeze(path)
    positions = [tuple(r1.CONDITIONS.index(row['condition']) for row in frozen['schedule'][i:i+4])
                 for i in range(0,16,4)]
    assert positions == list(r1.ORDERS)
    assert all(len({row[i] for row in positions}) == 4 for i in range(4))
    assert len({pair for row in positions for pair in zip(row,row[1:])}) == 12
    manifests = [r1.prepare(path,f'task-0-{arm}',tmp_path/arm) for arm in r1.CONDITIONS]
    assert len({m['source_identity'] for m in manifests}) == 1
    assert len({m['workspace'] for m in manifests}) == 4
    for manifest in manifests:
        assert manifest['permission_overrides'] == {}
        argv = manifest['r1']['argv']
        assert not any(x in argv for x in ['--sandbox','--approve-for-me','--ignore-user-config','--ephemeral','--ignore-rules'])
        assert 'forced_login_method="chatgpt"' in argv
        assert 'model_provider="openai"' in argv
    assert 'mcp_servers.loci.enabled=false' in manifests[0]['r1']['argv']


@pytest.mark.parametrize('mutation',['freeze','source','oracle','host','config'])
def test_frozen_evidence_rejects_drift(tmp_path, mutation):
    path = _freeze(tmp_path)
    frozen = r1.read_freeze(path)
    if mutation == 'freeze':
        frozen['model']='changed'
        write_json(path,frozen)
    elif mutation == 'source':
        (Path(frozen['tasks'][0]['source'])/'original.js').write_text('changed')
    elif mutation == 'oracle':
        Path(frozen['tasks'][0]['oracle']).write_text('changed')
    else:
        Path(frozen['host']['executable'] if mutation=='host' else frozen['native_config']).write_text('changed')
    with pytest.raises((ValueError,RuntimeError)):
        r1.prepare(path,'task-0-native',tmp_path/'run')


def test_execute_requires_gate_before_any_native_call(tmp_path, monkeypatch):
    path = _freeze(tmp_path)
    manifest = r1.prepare(path,'task-0-native',tmp_path/'run')
    gate = tmp_path/'gate.json'
    write_json(gate,{'status':'failed'})
    monkeypatch.setattr(subprocess,'run',lambda *args,**kwargs:pytest.fail('must not launch'))
    with pytest.raises(ValueError,match='passing deterministic'):
        r1.execute(Path(manifest['observer'])/'run.json',gate)


def test_replay_uses_archived_source_and_rejects_unallowed_changes(tmp_path):
    path = _freeze(tmp_path)
    manifest = r1.prepare(path,'task-0-native',tmp_path/'run')
    observer, workspace = Path(manifest['observer']),Path(manifest['workspace'])
    (workspace/'answer.json').write_text('{"n":1}')
    (observer/'qualification').mkdir()
    after=source_snapshot(workspace,observer/'source-history')
    write_json(observer/'qualification/source-after.json',after)
    (workspace/'answer.json').write_text('live workspace is not the graded source')
    result=r1.replay(observer/'run.json',tmp_path/'replay')
    assert result['correct'] is True
    assert result['changes'] == ['answer.json']
    (workspace/'answer.json').write_text('{"n":1}')
    (workspace/'original.js').write_text('changed')
    write_json(observer/'qualification/source-after.json',source_snapshot(workspace,observer/'source-history'))
    result=r1.replay(observer/'run.json',tmp_path/'replay-two')
    assert result['correct'] is False
    assert result['unexpected_changes'] == ['original.js']


def test_execute_pins_subscription_auth_scrubs_keys_and_never_retries(tmp_path, monkeypatch):
    path = _freeze(tmp_path)
    manifest = r1.prepare(path,'task-0-native',tmp_path/'run')
    observer = Path(manifest['observer'])
    gate = tmp_path/'gate.json'
    write_json(gate,{'status':'passed'})
    for key in ['OPENAI_API_KEY','CODEX_API_KEY','OPENAI_BASE_URL']:
        monkeypatch.setenv(key,'must-not-reach-native-child')
    calls=[]
    def native(argv, **kwargs):
        calls.append(argv)
        assert all(key not in kwargs['env'] for key in ['OPENAI_API_KEY','CODEX_API_KEY','OPENAI_BASE_URL'])
        if argv[1:]==['login','status']:
            return subprocess.CompletedProcess(argv,0,'Logged in using ChatGPT','')
        assert argv==manifest['r1']['argv']
        kwargs['stdout'].write(b'{"type":"thread.started","thread_id":"new-thread"}\n')
        return subprocess.CompletedProcess(argv,0)
    monkeypatch.setattr(subprocess,'run',native)
    result=r1.execute(observer/'run.json',gate)
    assert result['status']=='closed' and result['thread_id']=='new-thread'
    with pytest.raises(ValueError,match='already attempted'):
        r1.execute(observer/'run.json',gate)
    assert sum(argv[1]=='exec' for argv in calls)==1


def _amended_freeze(tmp_path):
    path = _freeze(tmp_path)
    frozen = json.loads(path.read_text())
    name = str(Path(r1.__file__).with_name('accounting.py').resolve())
    frozen['host']['orchestration_files'][name] = '1' * 64
    frozen.pop('freeze_sha256')
    frozen['freeze_sha256'] = r1.identity(frozen)
    write_json(path, frozen)
    payload = {'schema_version':1, 'kind':'r1-instrumentation-amendment',
               'freeze_sha256':frozen['freeze_sha256'],
               'changes':{name:{'before_sha256':'1'*64,'after_sha256':r0.digest(Path(name))}}}
    amendment = tmp_path/'instrumentation-amendment.json'
    _write_amendment(amendment, payload)
    return path, amendment


def _write_amendment(path, payload):
    payload = {key:value for key,value in payload.items() if key != 'amendment_sha256'}
    write_json(path, {**payload,'amendment_sha256':r1.identity(payload)})


def test_explicit_amendment_preserves_original_freeze_and_native_command(tmp_path):
    path, amendment = _amended_freeze(tmp_path)
    before = path.read_bytes()
    with pytest.raises(ValueError,match='orchestration changed'):
        r1.read_freeze(path)
    original = r1.read_freeze(path,runtime=False)
    frozen = r1.read_freeze(path,amendment=amendment)
    assert frozen == original and path.read_bytes() == before
    manifest = r1.prepare(path,'task-0-native',tmp_path/'run',amendment=amendment)
    observer,workspace=Path(manifest['observer']),Path(manifest['workspace'])
    assert manifest['r1']['argv']==r1.command(original,'native',workspace,observer)
    assert manifest['r1']['instrumentation_amendment']['sha256']==r0.digest(amendment)


@pytest.mark.parametrize('mutation',['self_hash','base','before','after','disallowed','unpinned'])
def test_instrumentation_amendment_rejects_wrong_or_excessive_substitution(tmp_path,mutation):
    path, amendment = _amended_freeze(tmp_path)
    payload=json.loads(amendment.read_text())
    name=next(iter(payload['changes']))
    if mutation=='self_hash':
        payload['note']='unrecorded change'
        write_json(amendment,payload)
    else:
        if mutation=='base':payload['freeze_sha256']='0'*64
        elif mutation=='before':payload['changes'][name]['before_sha256']='0'*64
        elif mutation=='after':payload['changes'][name]['after_sha256']='0'*64
        elif mutation=='disallowed':payload['changes'][str(Path(r0.__file__).resolve())]=payload['changes'].pop(name)
        elif mutation=='unpinned':payload['changes'][str(Path(r1.__file__).resolve())]=payload['changes'].pop(name)
        _write_amendment(amendment,payload)
    with pytest.raises(ValueError):
        r1.read_freeze(path,amendment=amendment)


def test_offline_read_still_rejects_malformed_supplied_amendment(tmp_path):
    path, amendment = _amended_freeze(tmp_path)
    payload=json.loads(amendment.read_text());payload['freeze_sha256']='0'*64
    _write_amendment(amendment,payload)
    with pytest.raises(ValueError,match='amendment identity or base'):
        r1.read_freeze(path,runtime=False,amendment=amendment)


@pytest.mark.parametrize('pin',['startup','candidate','config','host'])
def test_amendment_does_not_relax_scientific_or_native_environment_pins(tmp_path,pin):
    path, amendment = _amended_freeze(tmp_path)
    frozen=json.loads(path.read_text())
    if pin in {'startup','candidate'}:
        target=tmp_path/(pin+'.txt');target.write_text('original')
        if pin=='startup':frozen['host']['startup_context_files']={str(target):r0.digest(target)}
        else:frozen['conditions']['integrated']['implementation_files']={str(target):r0.digest(target)}
        frozen.pop('freeze_sha256');frozen['freeze_sha256']=r1.identity(frozen);write_json(path,frozen)
        payload=json.loads(amendment.read_text());payload['freeze_sha256']=frozen['freeze_sha256'];_write_amendment(amendment,payload)
    else:target=Path(frozen['native_config'] if pin=='config' else frozen['host']['executable'])
    target.write_text('drift')
    with pytest.raises(ValueError):r1.read_freeze(path,amendment=amendment)


def test_execute_requires_the_same_explicit_amendment_as_preparation(tmp_path,monkeypatch):
    path, amendment = _amended_freeze(tmp_path)
    manifest=r1.prepare(path,'task-0-native',tmp_path/'run',amendment=amendment)
    other=tmp_path/'other-amendment.json'
    payload=json.loads(amendment.read_text());payload['note']='different receipt';_write_amendment(other,payload)
    gate=tmp_path/'gate.json';write_json(gate,{'status':'passed'})
    monkeypatch.setattr(subprocess,'run',lambda *args,**kwargs:pytest.fail('must not launch'))
    with pytest.raises(ValueError,match='amendment differs from preparation'):
        r1.execute(Path(manifest['observer'])/'run.json',gate,amendment=other)
