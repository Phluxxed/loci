"""Mutable execution receipts only; frozen inputs and task sources are read-only."""
import argparse, datetime, hashlib, json, subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parent
REPO=ROOT.parents[2]
PARENT='01a09e19-5048-79d3-96dd-697eda8a4ac8'
def digest(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def preflight(numbers):
 f=json.loads((ROOT/'freeze.json').read_text());rt=json.loads((ROOT/'runtime/runtime-provenance.json').read_text())
 assert all(digest(REPO/p)==v for p,v in f['input_sha256'].items())
 assert all(digest(x['path'])==x['sha256'] for x in rt['installed_files'])
 assert subprocess.check_output(['git','rev-parse','HEAD:src/loci'],cwd=REPO,text=True).strip()==f['product_src_tree']
 src=json.loads((REPO/'benchmarks/comparisons/ordinary-adoption-v1/cases.json').read_text())['source_files'];d=json.loads((ROOT/'execution-ledger.json').read_text())
 for n in numbers:
  row=next(x for x in d['rows'] if x['run_id']==f'run-{n}');p=Path(row['source_root'])
  assert {str(q.relative_to(p)) for q in p.rglob('*') if q.is_file()}==set(src)
  assert all(digest(p/k)==v for k,v in src.items())
  row['preflight']={'checked_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'frozen_inputs_valid':True,'live_installed_hashes_valid':True,'source_file_hashes_valid':True,'source_file_count':len(src)}
 (ROOT/'execution-ledger.json').write_text(json.dumps(d,indent=2)+'\n')
 print('preflight passed',numbers)
def sync():
 d=json.loads((ROOT/'execution-ledger.json').read_text());found={}
 for p in Path('/Users/brummerv/.codex/sessions/2026/09/14').glob('*.jsonl'):
  with p.open() as f:
   try:m=json.loads(next(f)).get('payload',{})
   except (ValueError,StopIteration):continue
  if m.get('parent_thread_id')!=PARENT:continue
  name=m.get('agent_path','').removeprefix('/root/')
  if name not in [x['agent_task_name'] for x in d['rows']]:continue
  assert name not in found;found[name]=(p,m)
 for row in d['rows']:
  if row['agent_task_name'] not in found:continue
  p,m=found[row['agent_task_name']];ev=[json.loads(x) for x in p.read_text().splitlines()]
  st=next(x for x in ev if x.get('type')=='event_msg' and x['payload'].get('type')=='task_started')
  end=next((x for x in ev if x.get('type')=='event_msg' and x['payload'].get('type') in ['task_complete','turn_aborted']),None)
  row.update(native_rollout_path=str(p),thread_id=m['id'],turn_id=st['payload']['turn_id'],started_at=st['timestamp'],deadline=(datetime.datetime.fromisoformat(st['timestamp'].replace('Z','+00:00'))+datetime.timedelta(seconds=300)).isoformat())
  if row['status']!='captured':row['status']='completed_pending_capture' if end else 'running'
  if end:row['finished_at']=end['timestamp']
  print(row['run_id'],row['status'],row['deadline'])
 (ROOT/'execution-ledger.json').write_text(json.dumps(d,indent=2)+'\n')
if __name__=='__main__':
 a=argparse.ArgumentParser();a.add_argument('operation',choices=['preflight','sync']);a.add_argument('numbers',type=int,nargs='*');args=a.parse_args();preflight(args.numbers) if args.operation=='preflight' else sync()
