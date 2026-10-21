"""Public record-page compatibility fixture, captured before consolidation."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from loci import service


_FIXTURE = Path(__file__).parent / 'fixtures' / 'graph_record_page_contract.json'
_FAMILIES = ('imports', 'symbol', 'type', 'calls')


def _prepare_repo(tmp_path, monkeypatch):
    repo = tmp_path / 'repo'
    repo.mkdir()
    (repo / 'types.ts').write_text(
        'export interface Payload { value: string }\n'
        'export function make(): Payload { return { value: "ok" }; }\n',
        encoding='utf-8',
    )
    (repo / 'use.ts').write_text(
        'import { make, Payload } from "./types.js";\n'
        'import { missing } from "external";\n'
        'export function first<T>(x: Payload): T { make(); missing(); throw 1; }\n'
        'export function second(x: Unknown): Payload { return make(); }\n',
        encoding='utf-8',
    )
    monkeypatch.setenv('LOCI_BASE_DIR', str(tmp_path / 'store'))
    service.index_repo(repo, incremental=False)
    # Existing integration tests cover load/freshness. This matrix reuses one
    # validated snapshot to isolate page policy and avoid hundreds of reloads.
    context = service._load_graph_context(repo, ensure_fresh=False)
    monkeypatch.setattr(service, '_load_graph_context', lambda *a, **kw: context)
    return repo


def _query(family, repo, **kwargs):
    if family == 'imports':
        return service.graph_imports(repo, **kwargs)
    if family == 'calls':
        return service.graph_calls(repo, **kwargs)
    return service.graph_references(repo, family=family, **kwargs)


def _normalize(result):
    return {**result, 'repo': '<repo>'}


@pytest.mark.parametrize('family', _FAMILIES)
def test_graph_record_pages_preserve_baseline_contract(tmp_path, monkeypatch, family):
    repo = _prepare_repo(tmp_path, monkeypatch)
    frozen = json.loads(_FIXTURE.read_text(encoding='utf-8'))[family]
    assert _normalize(_query(family, repo)) == frozen
    for file in (None, 'use.ts', 'types.ts', 'missing.ts'):
        selected = [item for item in frozen['items']
                    if file is None or item['raw']['source_file'] == file]
        counts = {
            'total': len(selected),
            'resolved': sum(item['status'] == 'resolved' for item in selected),
            'unresolved': sum(item['status'] == 'unresolved' for item in selected),
        }
        for status in ('all', 'resolved', 'unresolved'):
            filtered = [item for item in selected if status == 'all' or item['status'] == status]
            for offset, limit in ((0, 1), (1, 2), (len(filtered), 1), (len(filtered) + 3, 500)):
                items = filtered[offset:offset + limit]
                next_offset = offset + len(items)
                expected = {
                    **frozen, 'file': file, 'status': status, 'items': items,
                    'counts': {**counts, 'returned': len(items)},
                    'pagination': {
                        'offset': offset, 'limit': limit,
                        'next_offset': next_offset if next_offset < len(filtered) else None,
                    },
                }
                assert _normalize(_query(family, repo, file=file, status=status,
                                         offset=offset, limit=limit)) == expected
            collected, offset = [], 0
            while True:
                page = _query(family, repo, file=file, status=status, offset=offset, limit=1)
                collected.extend(page['items'])
                next_offset = page['pagination']['next_offset']
                if next_offset is None:
                    break
                assert next_offset > offset
                offset = next_offset
            assert collected == filtered
    for kwargs in ({'file': '../use.ts'}, {'status': 'other'}, {'offset': True}, {'limit': 0}):
        with pytest.raises(service.LociError) as error:
            _query(family, repo, **kwargs)
        assert error.value.code == 'INVALID_INPUT'
        field, value = next(iter(kwargs.items()))
        assert error.value.details['field'] == field
        assert error.value.details['value'] == value


@pytest.mark.parametrize('family', _FAMILIES)
def test_graph_record_pages_serialize_only_returned_records(tmp_path, monkeypatch, family):
    repo = _prepare_repo(tmp_path, monkeypatch)
    state = service._load_graph_context(repo, ensure_fresh=False)[2]
    records = {
        'imports': state.imports, 'symbol': state.symbol_references,
        'type': state.type_relations, 'calls': state.calls,
    }[family]
    record_type = type(records[0])
    original = record_type.to_dict
    serialized = []

    def tracked(record):
        serialized.append(record)
        return original(record)

    monkeypatch.setattr(record_type, 'to_dict', tracked)
    page = _query(family, repo, limit=1)
    assert len(page['items']) == len(serialized) == 1
    serialized.clear()
    assert not _query(family, repo, offset=len(records))['items']
    assert not serialized
