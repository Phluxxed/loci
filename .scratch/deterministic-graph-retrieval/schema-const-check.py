"""W1.8.4.4.9.6: exact retained-source verification, no provider trial."""
import hashlib
import json
import os
from pathlib import Path
import tempfile

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent / 'schema-const-check'
REPO = Path('/tmp/anvil-source-tasks-20260914/t21')
EXPECTED = json.loads((ROOT / 'benchmarks/comparisons/ordinary-adoption-v1/cases.json').read_text())['source_files']
SCHEMA = 'src/work-context/binding.ts::workContextBindingViewSchema#constant'


def source_identity():
    paths = list(REPO.rglob('*'))
    assert not any(p.is_symlink() for p in paths)
    actual = {p.relative_to(REPO).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
              for p in paths if p.is_file()}
    assert actual == EXPECTED
    return {'files': len(actual), 'hashes_exact': True}


def encoded(packet):
    return json.dumps({'content': [], 'structuredContent': packet, 'isError': False},
                      ensure_ascii=False, separators=(',', ':')).encode()


def validate(packet):
    assert len(encoded(packet)) == packet['usage']['output_bytes'] <= 16384
    assert packet['usage']['evidence_bytes'] <= 8192
    records = packet.get('sources', [packet['source']] if 'source' in packet else [])
    for source in records:
        raw = (REPO / source['file']).read_bytes()
        assert hashlib.sha256(raw).hexdigest() == source['content_hash']
        assert raw[source['start_byte']:source['end_byte']].decode() == source['content']
        assert source['source_ref'].startswith('sr1_') and len(source['source_ref']) == 30
    sources = {s['id']: s for s in records}
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
os.environ['LOCI_BASE_DIR'] = tempfile.mkdtemp(prefix='loci-schema-const-')
os.environ['LOCI_STORE_NAMESPACE'] = 'schema-const-check'
from loci import service
from loci.storage.index_store import EXTRACTOR_VERSION

HERE.mkdir(exist_ok=True)
service.index_repo(REPO, incremental=False)
function = 'src/tool-results/service.ts::captureCommandResult#function'
options = 'src/tool-results/service.ts::CaptureCommandResultOptions#type'
binding = 'src/work-context/binding.ts::WorkContextBinding#type'
requests = [
    ('schema-exact', {'query': 'workContextBindingViewSchema'}, []),
    ('schema-compound', {'query': 'src/work-context/binding.ts workContextBindingViewSchema session_id observed_cwd'}, []),
    ('function', {'query': 'captureCommandResult'}, [(function, options), (options, binding)]),
    ('explicit-pair', {'seed_ids': [options, binding]}, [(options, binding)]),
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
    (HERE / (name + '.json')).write_bytes(encoded(packet) + b'\n')
    count = validate(packet)
    edges = {(r['edge']['from'], r['edge']['to']) for r in packet['relationships']}
    assert set(expected) <= edges, (name, expected, edges)
    row = {'name': name, 'request': request, 'validated_sources': count,
           'selection': packet['selection'], 'anchors': packet['anchors'],
           'usage': packet['usage'], 'omissions': packet['omissions']}
    if name.startswith('schema-'):
        assert packet['selection']['mode'] == 'inferred'
        item = next(i for i in packet['items'] if i['node_id'] == SCHEMA and i['role'] == 'anchor')
        assert any('workContextBindingViewSchema' in s['content'] for s in packet['sources'] if s['id'] in item['source_ids'])
        reference = item['source_ref']
        parts = []
        pages = []
        offset = item['extent']['start_byte']
        while reference is not None:
            page = service.read(REPO, reference)
            validate(page)
            assert page['source']['start_byte'] == offset
            offset = page['source']['end_byte']
            parts.append(page['source']['content'])
            pages.append(page)
            reference = page['next_source_ref']
        exact = (REPO / item['extent']['file']).read_bytes()[item['extent']['start_byte']:item['extent']['end_byte']]
        assert ''.join(parts).encode() == exact
        assert b'.strict()' in exact
        (HERE / (name + '-read.json')).write_text(json.dumps(pages, indent=2) + '\n')
        row['exact_declaration'] = {'bytes': len(exact), 'pages': len(pages), 'extent': item['extent']}
    rows.append(row)
    print(name, 'passed', flush=True)

frozen = []
for campaign in ['ordinary-adoption-normal-v1', 'ordinary-adoption-repair-binding-v1',
                 'ordinary-adoption-repair-binding-v2', 'ordinary-adoption-repair-binding-v3']:
    freeze = json.loads((ROOT / 'benchmarks/comparisons' / campaign / 'freeze.json').read_text())
    mismatches = [p for p, digest in freeze['input_sha256'].items()
                  if hashlib.sha256((ROOT / p).read_bytes()).hexdigest() != digest]
    assert not mismatches, (campaign, mismatches)
    frozen.append({'campaign': campaign, 'inputs': len(freeze['input_sha256']), 'unchanged': True})
result = {'passed': True, 'scope': 'Local retained-source verification; no host activation or provider-value claim',
          'extractor_version': EXTRACTOR_VERSION, 'isolated_store': os.environ['LOCI_BASE_DIR'],
          'source_before': before, 'source_after': source_identity(), 'checks': rows, 'frozen': frozen}
(HERE / 'result.json').write_text(json.dumps(result, indent=2) + '\n')
print(json.dumps({'passed': True, 'checks': len(rows), 'source_files': len(EXPECTED), 'frozen': frozen}))
