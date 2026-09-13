from pathlib import Path

import pytest

from loci.service import index_repo
from loci.storage.index_store import IndexStore


def _index(tmp_path, monkeypatch, suffix, source, *, value=False):
    base = tmp_path / 'cache'
    monkeypatch.setenv('LOCI_BASE_DIR', str(base))
    repo = tmp_path / 'repo'
    repo.mkdir()
    definitions = (
        'export function Payload() { return 1; }\n'
        if value else 'export interface Payload { required: string; }\n'
    )
    definitions += 'export interface Constraint { required: string; }\n'
    (repo / f'types{suffix}').write_text(definitions)
    (repo / f'distractor{suffix}').write_text(definitions)
    (repo / f'consumer{suffix}').write_text(source)
    index_repo(repo, incremental=False)
    return IndexStore(base_dir=base).load(repo.resolve())['graph']


FORMS = [
    'export function f<Payload>(x: Payload): Payload { return x; }',
    'const f = <Payload,>(x: Payload): Payload => x;',
    'const f = function<Payload>(x: Payload): Payload { return x; };',
    'export class C<Payload> { value: Payload; read(): Payload { throw 0; } }',
    'export interface C<Payload> { value: Payload; read(): Payload; }',
    'export type C<Payload> = [Payload, Payload];',
    'export class C { read<Payload>(x: Payload): Payload { return x; } }',
    'export interface C { read<Payload>(x: Payload): Payload; }',
    'export type C = <Payload>(x: Payload) => Payload;',
    'export type C = new<Payload>(x: Payload) => Payload;',
    'export interface C { <Payload>(x: Payload): Payload; }',
    'export interface C { new<Payload>(x: Payload): Payload; }',
    'declare function f<Payload>(x: Payload): Payload;',
]


@pytest.mark.parametrize('suffix', ['.ts', '.tsx'])
@pytest.mark.parametrize('declaration', FORMS)
def test_generic_names_are_excluded_and_uses_never_prove_an_import(
    tmp_path: Path, monkeypatch, suffix, declaration,
):
    source = 'import type { Payload } from "./types.js";\n' + declaration + '\n'
    graph = _index(tmp_path, monkeypatch, suffix, source)
    references = graph['symbol_references']
    assert len(references) == 2
    declaration_start = source.index('<Payload') + 1
    expected_starts = []
    offset = declaration_start + len('Payload')
    while (offset := source.find('Payload', offset)) != -1:
        expected_starts.append(offset)
        offset += len('Payload')
    assert [ref['raw']['start_byte'] for ref in references] == expected_starts
    for ref in references:
        raw = ref['raw']
        assert raw['text'] == 'Payload'
        assert raw['binding_state'] == 'shadowed'
        assert source.encode()[raw['start_byte']:raw['end_byte']] == b'Payload'
        assert raw['start_byte'] != declaration_start
        assert ref['status'] == 'unresolved'
        assert ref['unresolved_reason'] == 'binding_shadowed'
        assert ref['target_id'] is None
        assert ref['support'] == []
    assert not [edge for edge in graph['edges'] if edge['type'].startswith('references')]


@pytest.mark.parametrize('suffix', ['.ts', '.tsx'])
def test_constraints_defaults_and_outside_scope_keep_exact_import_evidence(
    tmp_path: Path, monkeypatch, suffix,
):
    source = '''import type { Payload, Constraint } from "./types.js";
export function f<Payload extends Constraint = Constraint>(x: Payload): Payload { return x; }
export function outside(x: Payload): Payload { return x; }
'''
    graph = _index(tmp_path, monkeypatch, suffix, source)
    refs = graph['symbol_references']
    assert [(r['raw']['text'], r['raw']['binding_state']) for r in refs] == [
        ('Constraint', 'definite'), ('Constraint', 'definite'),
        ('Payload', 'shadowed'), ('Payload', 'shadowed'),
        ('Payload', 'definite'), ('Payload', 'definite'),
    ]
    for ref in refs:
        if ref['raw']['binding_state'] == 'shadowed':
            assert ref['target_id'] is None
        else:
            assert ref['status'] == 'resolved'
            assert ref['target_id'] == f"types{suffix}::{ref['raw']['text']}#interface"
            assert ref['support']
    assert {edge['to'] for edge in graph['edges'] if edge['type'] == 'references_type'} == {
        f'types{suffix}::Payload#interface', f'types{suffix}::Constraint#interface',
    }


def test_nested_scope_ends_before_sibling_and_type_parameter_defaults_bind_locally(
    tmp_path: Path, monkeypatch,
):
    source = '''import type { Payload } from "./types.js";
export function outer() {
  function inner<Payload, Other = Payload>(x: Payload): Payload {
    function nested(x: Payload): Payload { return x; }
    return x;
  }
  function sibling(x: Payload): Payload { return x; }
}
'''
    refs = _index(tmp_path, monkeypatch, '.ts', source)['symbol_references']
    assert [r['raw']['binding_state'] for r in refs] == ['shadowed'] * 5 + ['definite'] * 2
    assert all(r['target_id'] is None for r in refs[:5])
    assert all(r['target_id'] == 'types.ts::Payload#interface' for r in refs[5:])


@pytest.mark.parametrize('suffix', ['.ts', '.tsx'])
def test_generic_does_not_shadow_same_named_value_calls_or_typeof(
    tmp_path: Path, monkeypatch, suffix,
):
    source = '''import { Payload } from "./types.js";
export function f<Payload>(x: Payload): Payload {
  type Factory = typeof Payload;
  Payload();
  return x;
}
'''
    graph = _index(tmp_path, monkeypatch, suffix, source, value=True)
    refs = graph['symbol_references']
    assert [r['raw']['binding_state'] for r in refs] == ['shadowed', 'shadowed', 'definite', 'definite']
    assert [r['target_id'] for r in refs] == [None, None, f'types{suffix}::Payload#function', f'types{suffix}::Payload#function']
    call, = graph['calls']
    assert (call['status'], call['target_id']) == ('resolved', f'types{suffix}::Payload#function')
    assert (f'consumer{suffix}::f#function', f'types{suffix}::Payload#function', 'calls') in {
        (edge['from'], edge['to'], edge['type']) for edge in graph['edges']
    }


def test_underscore_is_a_real_typescript_generic_name(tmp_path: Path, monkeypatch):
    source = '''import type { Payload as _ } from "./types.js";
export function f<_>(x: _): _ { return x; }
export function outside(x: _): _ { return x; }
'''
    refs = _index(tmp_path, monkeypatch, '.ts', source)['symbol_references']
    assert [r['raw']['binding_state'] for r in refs] == ['shadowed', 'shadowed', 'definite', 'definite']
    assert [r['target_id'] for r in refs] == [None, None, 'types.ts::Payload#interface', 'types.ts::Payload#interface']
