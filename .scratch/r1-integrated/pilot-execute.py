"""Sequential frozen native pilot, stopping on a common host/evidence blocker."""
import argparse
import json
from pathlib import Path
import shutil
import tempfile

from benchmarks.complete_work import r1
from benchmarks.complete_work.evaluate import write_json

parser=argparse.ArgumentParser()
parser.add_argument('--freeze',type=Path,required=True)
parser.add_argument('--gate',type=Path,required=True)
args=parser.parse_args()
root=Path(__file__).resolve().parent/'pilot'
frozen=r1.read_freeze(args.freeze)
gate=json.loads(args.gate.read_text())
assert gate['status']=='passed','deterministic gate must pass before execution'
run_root=Path(tempfile.mkdtemp(prefix='loci-r1-native-',dir='/private/tmp'))
index={'freeze_sha256':frozen['freeze_sha256'],'run_root':str(run_root),'runs':[],'status':'running'}
write_json(root/'execution-index.json',index)
for scheduled in frozen['schedule']:
    run_id=scheduled['run_id']
    manifest=r1.prepare(args.freeze,run_id,run_root/run_id)
    config=Path(manifest['observer'])/'run.json'
    execution=r1.execute(config,args.gate)
    entry={'run_id':run_id,'config':str(config),'execution':execution}
    index['runs'].append(entry)
    write_json(root/'execution-index.json',index)
    print(json.dumps({'run_id':run_id,'execution_status':execution['status'],'thread_id':execution['thread_id']}),flush=True)
    if execution['thread_id']:
        matches=list((Path.home()/'.codex/sessions').rglob('*'+execution['thread_id']+'.jsonl'))
    else:
        matches=[]
    if len(matches)==1:
        result=r1.evaluate(config,matches[0],execution['thread_id'])
        entry['evaluation']=result
        print(json.dumps({'run_id':run_id,'correct':result['correct'],'qualification':result['qualification_status'],'usage':result['accounting']['usage_status']}),flush=True)
        # Independent replay uses frozen evaluator and archived retained bytes;
        # it never starts another measured agent or consults the live workspace.
        replay=r1.replay(config,Path(manifest['observer'])/'replay')
        entry['replay_matches']=all(replay[k]==result[k] for k in ['source_identity','oracle_sha256','correct','changes','unexpected_changes'])
        assert entry['replay_matches']
    else:
        entry['evidence_error']='unique native rollout unavailable'
        result=None
    archive=root/'archived-runs'/run_id
    archive.parent.mkdir(exist_ok=True)
    shutil.copytree(run_root/run_id,archive)
    entry['archive']=str(archive)
    # Wrong answers are scored outcomes and do not stop the schedule. Missing
    # usage/protection/closed-thread evidence is a common-host blocker.
    if execution['status']!='closed' or result is None or result['qualification_status']!='qualified_observations':
        index['status']='blocked'
        index['blocker_run']=run_id
        write_json(root/'execution-index.json',index)
        break
    write_json(root/'execution-index.json',index)
else:
    index['status']='complete'
    write_json(root/'execution-index.json',index)
print(json.dumps({'status':index['status'],'attempted':len(index['runs']),'scheduled':len(frozen['schedule']),'run_root':str(run_root)}),flush=True)
