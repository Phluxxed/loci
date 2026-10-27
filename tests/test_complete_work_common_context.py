"""Prospective rendered-context qualification, entirely offline."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import subprocess

import pytest

from benchmarks.complete_work import availability, r0, r1
from benchmarks.complete_work.evaluate import write_json
from tests.test_complete_work_availability import _trace, _write
from tests.test_complete_work_r1 import _freeze
from tests.test_complete_work_r1_availability import host_gate, _startup_rows


def test_common_policy_is_prospective_and_binds_cards_root_instructions_and_validator(tmp_path):
    legacy = _freeze(tmp_path)
    old = r1.read_freeze(legacy)
    legacy_bytes = legacy.read_bytes()
    assert 'common_context' not in old
    assert 'skills.include_instructions=false' not in r1.command(old, 'native', tmp_path / 'w', tmp_path / 'o')
    plan_path = tmp_path / 'plan.json'
    plan = json.loads(plan_path.read_text())
    plan['common_context'] = True
    for task in plan['tasks']:
        (Path(task['source']) / 'AGENTS.md').write_bytes(b'Root rules.\r\n')
    write_json(plan_path, plan)
    frozen = r1.freeze(plan_path, tmp_path / 'prospective')
    assert frozen['common_context'] == availability.context_policy('Root rules.\r\n')
    assert frozen['host']['orchestration_files'][str(Path(availability.__file__).resolve())] == r0.digest(Path(availability.__file__))
    assert legacy.read_bytes() == legacy_bytes
    for condition in r1.CONDITIONS:
        command = r1.command(frozen, condition, tmp_path / 'w', tmp_path / 'o')
        assert command.count('skills.include_instructions=false') == 1
        assert not any(x in command for x in ['--sandbox', '--profile', '--ignore-user-config'])
        prompt = r1.measured_prompt(frozen, frozen['tasks'][0], condition)
        assert availability.COMMON_CATALOG_PROGRAM in prompt
        assert availability.CAPABILITY_CARDS[condition] in prompt
        assert 'Loci use is optional' in prompt
        assert prompt.endswith(frozen['tasks'][0]['prompt'])
    assert 'Python and Go semantics are unsupported' in availability.CAPABILITY_CARDS['integrated']
    assert 'Production' in availability.CAPABILITY_CARDS['eager']
    (Path(plan['tasks'][0]['source']) / 'AGENTS.md').write_text('Different instructions')
    with pytest.raises(ValueError, match='identical root AGENTS.md'):
        r1.freeze(plan_path, tmp_path / 'must-not-freeze')
    assert not (tmp_path / 'must-not-freeze').exists()


def test_fixed_common_catalog_retains_complete_descriptions_and_separates_loci():
    tools = [{'name': 'z_native', 'description': 'Complete description\nwith details.'},
             {'name': 'mcp__loci__loci_read', 'description': 'Loci read.'},
             {'name': 'a_native', 'description': 'Another native operation.'}]
    program = ('const ALL_TOOLS=' + json.dumps(tools)
               + ';const text=x=>process.stdout.write(JSON.stringify(x));\n'
               + availability.COMMON_CATALOG_PROGRAM)
    completed = subprocess.run(['node', '-e', program], text=True, capture_output=True, check=True)
    assert json.loads(completed.stdout) == {
        'loci_runtime_catalog_v1': ['mcp__loci__loci_read'],
        'common_runtime_catalog_v1': {'count': 2, 'sha256': hashlib.sha256(json.dumps(
            [tools[2], tools[0]], ensure_ascii=False, separators=(',', ':')).encode()).hexdigest()},
    }


def test_pure_js_sha256_matches_hashlib_for_utf8_and_padding_boundaries():
    vectors = ['', 'abc', 'The quick brown fox jumps over the lazy dog', 'a' * 55, 'a' * 56,
               'a' * 64, 'a' * 1000, 'café 中文 🙂\n\x00']
    program = ('const crypto=undefined,TextEncoder=undefined;\n' + availability.CATALOG_SHA256_PROGRAM
               + 'process.stdout.write(JSON.stringify(' + json.dumps(vectors) + '.map(sha256)));')
    completed = subprocess.run(['node', '-e', program], text=True, capture_output=True, check=True)
    assert json.loads(completed.stdout) == [hashlib.sha256(value.encode()).hexdigest() for value in vectors]


def test_fixed_fingerprint_covers_real_complete_archived_tool_descriptions():
    root = Path(__file__).resolve().parents[1] / '.scratch/r1-integrated/pilot-availability-v2'
    index = json.loads((root / 'execution-index.json').read_text())
    trace = Path(index['runs'][1]['archive']) / 'observer/qualification/native-rollout.jsonl'
    rows = [json.loads(line) for line in trace.read_text().splitlines()]
    namespaces = next(row['payload']['tools'] for row in rows
                      if row['type'] == 'response_item' and row['payload'].get('type') == 'additional_tools')
    tools = [{'name': namespace['name'] + '.' + tool['name'], 'description': tool['description']}
             for namespace in namespaces for tool in namespace['tools']]
    tools += [{'name': 'unicode_fixture', 'description': 'UTF-8 café 中文 🙂 and "quoted" text\n'}]
    program = ('const crypto=undefined,TextEncoder=undefined;'
               'const ALL_TOOLS=JSON.parse(require("node:fs").readFileSync(0,"utf8"));'
               'const text=x=>process.stdout.write(JSON.stringify(x));\n' + availability.COMMON_CATALOG_PROGRAM)
    def fingerprint(values):
        output = subprocess.run(['node', '-e', program], input=json.dumps(values),
                                text=True, capture_output=True, check=True)
        receipt = json.loads(output.stdout)['common_runtime_catalog_v1']
        expected = json.dumps(sorted(values, key=lambda t: t['name']), ensure_ascii=False, separators=(',', ':')).encode()
        assert receipt == {'count': len(values), 'sha256': hashlib.sha256(expected).hexdigest()}
        assert len(output.stdout) < 250
        return receipt['sha256']
    first = fingerprint(tools)
    tools[0]['description'] += ' Full-description drift with unchanged tool names.'
    assert fingerprint(tools) != first


@pytest.mark.parametrize('host_gate', [{'common_context': True, 'root_agents_md': 'Shared real repository rules.\n'}], indirect=True)
def test_four_callable_probes_match_paths_only_and_keep_actual_instructions(host_gate):
    path, frozen, gate_path, _, _ = host_gate
    verified = r1.require_availability(frozen, gate_path)
    assert len(verified['threads']) == 4
    context = verified['common_context']
    assert len(context['loci_contracts_sha256']) == 4
    assert len(set(context['loci_contracts_sha256'].values())) == 3
    gate = json.loads(gate_path.read_text())
    for probe in gate['probes']:
        root = Path(probe['files']['config']['path']).parent.parent / 'workspace'
        assert (root / 'AGENTS.md').read_text() == frozen['common_context']['root_agents_md']
    manifest = r1.prepare(path, 'task-0-integrated', gate_path.parent / 'measured', availability_gate=gate_path)
    assert manifest['r1']['availability_gate'] == verified
    assert 'skills.include_instructions=false' in manifest['r1']['argv']


def _rewrite_probe(gate, condition, mutation):
    """Rebind valid raw readbacks, so negatives exercise the comparison itself."""
    probe = next(p for p in gate['probes'] if p['condition'] == condition)
    files = probe['files']
    trace = Path(files['trace']['path'])
    rows = [json.loads(line) for line in trace.read_text().splitlines()]
    mutation(rows)
    _write(trace, rows)
    manifest = json.loads(Path(files['config']['path']).read_text())
    qualification_path = Path(files['qualification']['path'])
    qualified = json.loads(qualification_path.read_text())
    qualified['native_trace_sha256'] = r0.digest(trace)
    write_json(qualification_path, qualified)
    tools = availability.TOOLS_BY_CONDITION[condition]
    evidence = availability.audit_probe(trace, qualified['accounting'], condition, Path(manifest['workspace']), tools,
        fixture=trace.parents[2] / 'workspace', common_context=True)
    evidence['common_context'] = availability.audit_common_context(trace, Path(manifest['workspace']),
        Path(manifest['observer']), Path(files['prompt']['path']).read_text(), tools)
    write_json(Path(files['evidence']['path']), evidence)
    for record in files.values():
        record['sha256'] = r0.digest(Path(record['path']))


def _drift(rows, kind):
    if kind == 'skills':
        rows[2]['payload']['content'].append({'type': 'input_text', 'text': '<skills_instructions>Unrelated new skill</skills_instructions>'})
    elif kind == 'schema':
        rows[1]['payload']['tools'][0]['tools'][0]['parameters']['properties']['agent_type'] = {'type': 'string'}
    elif kind == 'catalog':
        receipt = json.loads(rows[6]['payload']['output'])
        receipt['common_runtime_catalog_v1']['sha256'] = '0' * 64
        rows[6]['payload']['output'] = json.dumps(receipt)
    elif kind == 'agents':
        rows[3]['payload']['content'][0]['text'] += ' New personal AGENTS rule.'
    elif kind == 'boundaries':
        content = rows[2]['payload']['content']
        content[:] = [{'type': 'input_text', 'text': ''.join(c['text'] for c in content)}]
    elif kind == 'loci_contract':
        rows[1]['payload']['tools'][1]['description'] += ' New Loci contract.'


@pytest.mark.parametrize('host_gate', [{'common_context': True}], indirect=True)
@pytest.mark.parametrize('kind', ['skills', 'schema', 'catalog', 'agents', 'boundaries'])
def test_common_probe_drift_fails_even_with_rebound_valid_receipts(host_gate, kind):
    _, frozen, gate_path, gate, _ = host_gate
    _rewrite_probe(gate, 'integrated', lambda rows: _drift(rows, kind))
    write_json(gate_path, gate)
    with pytest.raises(ValueError, match='common startup context differs'):
        r1.require_availability(frozen, gate_path)


@pytest.mark.parametrize('host_gate', [{'common_context': True, 'root_agents_md': 'Pinned rules.\n'}], indirect=True)
def test_retained_probe_root_agents_bytes_are_verified(host_gate):
    _, frozen, gate_path, gate, _ = host_gate
    root = Path(gate['probes'][0]['files']['config']['path']).parent.parent / 'workspace'
    (root / 'AGENTS.md').write_text('Replaced rules.\n')
    with pytest.raises(ValueError, match='root AGENTS.md differs'):
        r1.require_availability(frozen, gate_path)


@pytest.mark.parametrize('host_gate', [{'common_context': True}], indirect=True)
@pytest.mark.parametrize('kind', [None, 'skills', 'schema', 'catalog', 'agents', 'boundaries', 'loci_contract'])
def test_each_measured_trace_is_checked_before_oracle(host_gate, monkeypatch, kind):
    path, frozen, gate_path, _, _ = host_gate
    condition = 'integrated'
    manifest = r1.prepare(path, 'task-0-' + condition, gate_path.parent / 'measured', availability_gate=gate_path)
    workspace, observer = Path(manifest['workspace']), Path(manifest['observer'])
    prompt = r1.measured_prompt(frozen, frozen['tasks'][0], condition)
    _, rows, _, _, tools = _trace(observer, (workspace, []), condition)
    rows = _startup_rows(rows, workspace, observer, prompt, tools)
    if kind is not None:
        _drift(rows, kind)
    trace = observer / 'measured-native.jsonl'
    _write(trace, rows)
    qualification = {'status': 'qualified_observations', 'limitations': [], 'accounting': {
        'stages': [{'items': [{'type': 'UserMessage', 'content': [{'type': 'text', 'text': prompt}]}]}]}}
    monkeypatch.setattr(r0, 'qualify', lambda *a, **k: deepcopy(qualification))
    grades = []
    def oracle(config, destination):
        grades.append(config)
        destination.mkdir()
        return {'correct': True}
    monkeypatch.setattr(r1, 'replay', oracle)
    if kind is None:
        assert r1.evaluate(observer / 'run.json', trace, 'new-measured-thread')['correct'] is True
        assert len(grades) == 1
    else:
        with pytest.raises(ValueError, match='no correctness grade.*startup context differs'):
            r1.evaluate(observer / 'run.json', trace, 'new-measured-thread')
        assert not grades and not (observer / 'evaluation').exists()
        assert json.loads((observer / 'treatment.json').read_text())['status'] == 'invalid'


@pytest.mark.parametrize('update_role', ['user', 'developer'])
def test_instruction_updates_reject_but_ordinary_agents_tool_output_is_source(tmp_path, update_role):
    workspace, observer = tmp_path / 'w', tmp_path / 'o'
    _, rows, _, _, tools = _trace(tmp_path, (workspace, []), 'native')
    rows = _startup_rows(rows, workspace, observer, 'Frozen task.', tools)
    rows.append({'type': 'response_item', 'payload': {'type': 'custom_tool_call_output', 'call_id': 'read-agents',
        'output': '<skills_instructions>AGENTS.md source bytes, not an instruction update.</skills_instructions>'}})
    trace = tmp_path / 'trace.jsonl'
    _write(trace, rows)
    baseline = availability.audit_common_context(trace, workspace, observer, 'Frozen task.', tools)
    rows.append({'type': 'response_item', 'payload': {'type': 'message', 'role': update_role,
        'content': [{'type': 'input_text', 'text': 'Changed instructions.'}],
        'internal_chat_message_metadata_passthrough': {'content_item_kinds': ['agents_md.instructions']}}})
    _write(trace, rows)
    with pytest.raises(ValueError, match='instruction update'):
        availability.audit_common_context(trace, workspace, observer, 'Frozen task.', tools)
    assert baseline['common']['catalog']['count'] == 1


@pytest.mark.parametrize('kind', ['missing', 'extra', 'hash', 'count', 'boolean_count', 'unbounded'])
def test_common_catalog_requires_a_bounded_complete_fingerprint(tmp_path, kind):
    _, rows, _, _, tools = _trace(tmp_path, (tmp_path / 'w', []), 'native')
    rows = _startup_rows(rows, tmp_path / 'w', tmp_path / 'o', 'Task.', tools)
    receipt = json.loads(rows[6]['payload']['output'])
    common = receipt['common_runtime_catalog_v1']
    if kind == 'missing':
        receipt.pop('common_runtime_catalog_v1')
    elif kind == 'extra':
        common['names'] = ['unexported-descriptor']
    elif kind == 'hash':
        common['sha256'] = 'truncated'
    elif kind == 'count':
        common['count'] = 0
    elif kind == 'boolean_count':
        common['count'] = True
    else:
        receipt['common_runtime_catalog_v1'] = [{'name': 'exec', 'description': 'Unbounded catalog dump'}]
    rows[6]['payload']['output'] = json.dumps(receipt)
    trace = tmp_path / 'trace.jsonl'
    _write(trace, rows)
    with pytest.raises(ValueError):
        availability.audit_catalog(trace, tools, common_context=True)
