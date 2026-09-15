"""Read-only verification of frozen inputs, installed instructions and source copies."""
import hashlib
import json
from pathlib import Path
import subprocess

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

freeze = json.loads((HERE / 'freeze.json').read_text())
errors = []
for relative, expected in freeze['input_sha256'].items():
    p = REPO / relative
    if not p.is_file() or sha(p) != expected:
        errors.append('frozen input differs: ' + relative)
for item in freeze['installed_inputs']:
    p = Path(item['path'])
    if not p.is_file() or str(p.resolve()) != item['resolved'] or sha(p) != item['sha256']:
        errors.append('installed input differs: ' + str(p))
tree = subprocess.check_output(['git', 'rev-parse', 'HEAD:src'], cwd=REPO, text=True).strip()
if tree != freeze['product_src_tree'] or subprocess.check_output(['git', 'diff', 'HEAD', '--', 'src'], cwd=REPO):
    errors.append('product source differs')
expected = json.loads((REPO / 'benchmarks/comparisons/ordinary-adoption-v1/cases.json').read_text())['source_files']
sources = []
for row in json.loads((HERE / 'schedule.json').read_text())['rows']:
    root = Path(row['source_root']).resolve()
    actual = {p.relative_to(root).as_posix(): sha(p) for p in root.rglob('*') if p.is_file() and not p.is_symlink()}
    unsupported = [str(p) for p in root.rglob('*') if p.is_symlink()]
    passed = actual == expected and not unsupported
    sources.append({'run_id': row['run_id'], 'files': len(actual), 'exact': passed})
    if not passed:
        errors.append('source identity differs: ' + row['source_root'])
result = {'freeze_sha256': sha(HERE / 'freeze.json'), 'passed': not errors,
          'input_count': len(freeze['input_sha256']), 'sources': sources, 'errors': errors}
print(json.dumps(result))
if errors:
    raise SystemExit(1)
