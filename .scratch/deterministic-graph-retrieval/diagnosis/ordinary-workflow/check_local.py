"""Retained-source checks for the selected workflow repair; no provider trials."""
import hashlib
import json
import os
from pathlib import Path
import tempfile

ROOT = Path(__file__).resolve().parents[4]
HERE = Path(__file__).resolve().parent
REPO = Path('/tmp/anvil-source-tasks-20260914/t16').resolve()
EXPECTED = json.loads((ROOT / 'benchmarks/comparisons/ordinary-adoption-v1/cases.json').read_text())['source_files']


def source_identity():
    actual = {p.relative_to(REPO).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
              for p in REPO.rglob('*') if p.is_file() and not p.is_symlink()}
    assert actual == EXPECTED
    assert not any(p.is_symlink() for p in REPO.rglob('*'))
    return {'files': len(actual), 'hashes_exact': True, 'no_extras_or_symlinks': True}


def encoded(packet):
    return json.dumps({'content': [], 'structuredContent': packet, 'isError': False},
                      ensure_ascii=False, separators=(',', ':')).encode()


def validate(packet):
    assert len(encoded(packet)) == packet['usage']['output_bytes'] <= 16384
    assert packet['usage']['evidence_bytes'] <= 8192
    records = packet.get('sources', [packet['source']] if 'source' in packet else [])
    for source in records:
        data = (REPO / source['file']).read_bytes()
        assert hashlib.sha256(data).hexdigest() == source['content_hash']
        assert data[source['start_byte']:source['end_byte']].decode() == source['content']
        assert source['source_ref'].startswith('sr1_') and len(source['source_ref']) == 30
    sources = {source['id']: source for source in records}
    for relation in packet.get('relationships', []):
        assert relation['proof'] == 'complete'
        evidence = relation['edge']['evidence']
        assert all(i in sources for i in relation['source_ids'])
        assert any(sources[i]['file'] == evidence['file']
                   and sources[i]['content_hash'] == evidence['content_hash']
                   and sources[i]['start_line'] <= evidence['line'] <= sources[i]['end_line']
                   for i in relation['source_ids'])
    return len(records)


before = source_identity()
os.environ['LOCI_BASE_DIR'] = tempfile.mkdtemp(prefix='loci-ordinary-workflow-')
from loci import service

service.index_repo(REPO, incremental=False)
function = 'src/tool-results/service.ts::captureCommandResult#function'
options = 'src/tool-results/service.ts::CaptureCommandResultOptions#type'
binding = 'src/work-context/binding.ts::WorkContextBinding#type'
requests = [
    ('function', {'query': 'captureCommandResult'}, [(function, options), (options, binding)]),
    ('rich-query', {'query': 'captureCommandResult work context binding accepted type imported public contract'}, [(function, options), (options, binding)]),
    ('explicit-pair', {'query': 'binding contract', 'seed_ids': [options, binding]}, [(options, binding)]),
    ('binding-file', {'query': 'src/work-context/binding.ts'}, []),
    ('browser', {'query': 'runBrowserCli'}, [
        ('src/browser/cli.ts::runBrowserCli#function', 'src/browser/cli.ts::browserCliUsage#function'),
        ('bin/anvil.ts::main#function', 'src/browser/cli.ts::runBrowserCli#function')]),
    ('renderer', {'query': 'renderActiveTask'}, [
        ('src/continuity/render.ts::renderActiveTask#function', 'src/continuity/render.ts::truncateText#function'),
        ('src/continuity/render.ts::renderContinuityFrame#function', 'src/continuity/render.ts::renderActiveTask#function')]),
]
rows = []
for name, request, expected in requests:
    packet = service.retrieve(REPO, **request)
    count = validate(packet)
    edges = {(r['edge']['from'], r['edge']['to']) for r in packet['relationships']}
    (HERE / f'{name}-envelope.json').write_bytes(encoded(packet) + b'\n')
    assert set(expected) <= edges, (name, expected, edges)
    assert all(len(item['source_ref']) == 30 for item in packet['items'])
    rows.append({'name': name, 'request': request, 'required_edges': expected,
                 'validated_sources': count, 'usage': packet['usage'],
                 'omissions': packet['omissions'], 'envelope_sha256': hashlib.sha256(encoded(packet)).hexdigest()})
    if name in {'function', 'binding-file'}:
        item = next(item for item in packet['items'] if item['role'] == 'anchor')
        parts = []
        pages = []
        reference = item['source_ref']
        offset = item['extent']['start_byte']
        while reference is not None:
            page = service.read(REPO, reference)
            validate(page)
            assert page['source']['start_byte'] == offset
            offset = page['source']['end_byte']
            parts.append(page['source']['content'])
            pages.append(page)
            reference = page['next_source_ref']
        expected_source = (REPO / item['extent']['file']).read_bytes()[item['extent']['start_byte']:item['extent']['end_byte']]
        assert ''.join(parts).encode() == expected_source
        (HERE / f'{name}-read-pages.json').write_text(json.dumps(pages, indent=2) + '\n')
        rows[-1]['exact_owning_extent_read'] = {'pages': len(pages), 'bytes': len(expected_source), 'initial_reference': item['source_ref']}

result = {'scope': 'Local normal service on fixed source; no host activation or provider-value claim',
          'isolated_store': os.environ['LOCI_BASE_DIR'], 'source_before': before,
          'source_after': source_identity(), 'checks': rows, 'passed': True}
(HERE / 'local-results.json').write_text(json.dumps(result, indent=2) + '\n')
print(json.dumps({'passed': True, 'source_files': len(EXPECTED),
                  'rows': [{'name': r['name'], 'output_bytes': r['usage']['output_bytes'],
                            'relationships': r['usage']['relationships_delivered']} for r in rows]}))
