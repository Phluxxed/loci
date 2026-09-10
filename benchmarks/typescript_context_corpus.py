"""Frozen source-grounded TypeScript task corpus; no retrieval-arm evaluation."""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import tarfile
import tempfile
from typing import Any

DEFAULT_ROOT = Path(__file__).parent / 'corpora' / 'typescript-context-v1'


def _hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _relative(value: str) -> str:
    path = PurePosixPath(value)
    if not value or path.is_absolute() or '..' in path.parts or str(path) != value:
        raise ValueError(f'unsafe relative path: {value!r}')
    return value


def _snapshot_files(corpus: dict, snapshot_id: str) -> dict[str, bytes]:
    snapshot = corpus['snapshots'][snapshot_id]
    archive = Path(corpus['_root']) / _relative(snapshot['archive'])
    if _hash(archive.read_bytes()) != snapshot['archive_sha256']:
        raise ValueError(f'archive hash mismatch: {snapshot_id}')
    prefix = snapshot.get('prefix', '')
    if prefix:
        _relative(prefix)
        prefix += '/'
    files = {}
    with tarfile.open(archive, 'r:gz') as tar:
        for member in tar:
            if member.isdir():
                continue
            if not member.isfile():
                raise ValueError(f'non-regular archive member: {member.name}')
            name = _relative(member.name)
            if not name.startswith(prefix):
                continue
            relative = _relative(name[len(prefix):])
            if relative in files:
                raise ValueError(f'duplicate archive member: {relative}')
            stream = tar.extractfile(member)
            assert stream is not None
            files[relative] = stream.read()
    actual = {name: _hash(data) for name, data in files.items()}
    if actual != snapshot['files']:
        raise ValueError(f'snapshot inventory mismatch: {snapshot_id}')
    return files


def load_corpus(root: Path = DEFAULT_ROOT) -> dict[str, Any]:
    root = Path(root).resolve()
    raw = (root / 'corpus.json').read_bytes()
    if _hash(raw) != (root / 'corpus.sha256').read_text().strip():
        raise ValueError('corpus hash mismatch')
    corpus = json.loads(raw)
    if corpus['schema_version'] != 1:
        raise ValueError('unsupported corpus schema')
    corpus['_root'] = str(root)
    snapshots = {key: _snapshot_files(corpus, key) for key in corpus['snapshots']}
    ids = set()
    for case in corpus['cases']:
        if case['id'] in ids:
            raise ValueError('duplicate case id')
        ids.add(case['id'])
        if not case['prompt'].strip() or not isinstance(case['answer'], dict):
            raise ValueError('case needs a prompt and an independent answer')
        files = snapshots[case['snapshot']]
        item_ids = set()
        for item in case['context']:
            if item['id'] in item_ids:
                raise ValueError('duplicate context id')
            item_ids.add(item['id'])
            data = files[_relative(item['file'])]
            start, end = item['start_byte'], item['end_byte']
            if type(start) is not int or type(end) is not int or not 0 <= start < end <= len(data):
                raise ValueError('invalid gold source span')
            if _hash(data[start:end]) != item['sha256']:
                raise ValueError('gold source hash mismatch')
            if not item['reason'].strip():
                raise ValueError('gold source needs task relevance')
        if case['anchor'] not in item_ids:
            raise ValueError('anchor must name required source context')
        for relation in case['relationships']:
            if relation['from'] not in item_ids or relation['to'] not in item_ids:
                raise ValueError('relationship endpoint is not in required context')
    return corpus


def materialize_snapshot(corpus: dict, snapshot_id: str, destination: Path) -> None:
    destination = Path(destination)
    if destination.is_symlink() or (destination.exists() and any(destination.iterdir())):
        raise ValueError('snapshot destination must be absent or empty')
    files = _snapshot_files(corpus, snapshot_id)
    destination.mkdir(parents=True, exist_ok=True)
    for relative, data in files.items():
        path = destination / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)


def check_answer(corpus: dict, case_id: str, answer: dict) -> bool:
    """Compare authored structured facts, independently of graph/retrieval output.

    Object key order is irrelevant; array order is part of each explicit prompt.
    JSON numbers compare by value; booleans are not numbers.
    """
    case = next(case for case in corpus['cases'] if case['id'] == case_id)
    json.dumps(answer, allow_nan=False)
    return _same_json(answer, case['answer'])


def _same_json(left: Any, right: Any) -> bool:
    if isinstance(left, bool) or isinstance(right, bool):
        return type(left) is type(right) and left == right
    if isinstance(left, dict) and isinstance(right, dict):
        return left.keys() == right.keys() and all(_same_json(left[key], right[key]) for key in left)
    if isinstance(left, list) and isinstance(right, list):
        return len(left) == len(right) and all(_same_json(a, b) for a, b in zip(left, right))
    return left == right


@contextmanager
def _isolated_store(base: Path):
    names = ('LOCI_BASE_DIR', 'LOCI_STORE_NAMESPACE')
    before = {name: os.environ.get(name) for name in names}
    os.environ['LOCI_BASE_DIR'] = str(base)
    os.environ['LOCI_STORE_NAMESPACE'] = 'typescript-context-preflight'
    try:
        yield
    finally:
        for name, value in before.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value


def preflight(corpus: dict) -> dict:
    """Report extraction availability without changing the gold or dropping cases."""
    from loci.service import index_repo
    from loci.storage.index_store import EXTRACTOR_VERSION, IndexStore

    cases = []
    with tempfile.TemporaryDirectory(prefix='loci-corpus-preflight-') as directory:
        temp = Path(directory)
        with _isolated_store(temp / 'store'):
            symbols = {}
            for snapshot_id in corpus['snapshots']:
                repo = temp / snapshot_id
                materialize_snapshot(corpus, snapshot_id, repo)
                index_repo(repo, incremental=False)
                index = IndexStore(base_dir=temp / 'store').load(repo.resolve())
                assert index is not None
                symbols[snapshot_id] = index['symbols']
            for case in corpus['cases']:
                endpoints = []
                for item in case['context']:
                    expected = item['symbol']
                    matches = [] if expected is None else [
                        symbol for symbol in symbols[case['snapshot']]
                        if symbol['file_path'] == item['file']
                        and symbol['name'] == expected['name']
                        and symbol['kind'] == expected['kind']
                        and item['start_byte'] <= symbol['byte_offset']
                        and symbol['byte_offset'] + symbol['byte_length'] <= item['end_byte']
                    ]
                    status = ('source_only' if expected is None else
                              'missing' if not matches else
                              'indexed' if len(matches) == 1 else 'ambiguous')
                    endpoints.append({'id': item['id'], 'status': status,
                                      'symbol_ids': sorted(symbol['id'] for symbol in matches)})
                cases.append({'id': case['id'], 'endpoints': endpoints})
    return {'schema_version': 1, 'corpus_version': corpus['version'],
            'corpus_sha256': (Path(corpus['_root']) / 'corpus.sha256').read_text().strip(),
            'extractor_version': EXTRACTOR_VERSION, 'cases': cases,
            'meaning': 'Endpoint availability only; no relationship, delivery or agent-success claim.'}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=DEFAULT_ROOT)
    parser.add_argument('--preflight-output', type=Path)
    parser.add_argument('--case')
    parser.add_argument('--answer', type=Path)
    args = parser.parse_args()
    corpus = load_corpus(args.root)
    if args.case or args.answer:
        if not (args.case and args.answer):
            parser.error('--case and --answer are required together')
        passed = check_answer(corpus, args.case, json.loads(args.answer.read_text()))
        print(json.dumps({'case': args.case, 'passed': passed}))
        raise SystemExit(0 if passed else 1)
    if args.preflight_output:
        result = preflight(corpus)
        args.preflight_output.parent.mkdir(parents=True, exist_ok=True)
        args.preflight_output.write_text(json.dumps(result, indent=2) + '\n')
        print(json.dumps({'output': str(args.preflight_output), 'cases': len(result['cases'])}))
    else:
        print(json.dumps({'version': corpus['version'], 'cases': len(corpus['cases']),
                          'snapshots': len(corpus['snapshots']), 'integrity': 'passed'}))


if __name__ == '__main__':
    main()
