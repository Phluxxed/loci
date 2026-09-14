"""Call-level primary receipts; no fabricated completed primary task interval."""
import hashlib,json
from pathlib import Path
from benchmarks.ordinary_adoption_observed import _read_rollout,_collect_outer,_correlate_delivery
from benchmarks.ordinary_adoption_native_v2 import _collect_operations
from benchmarks.ordinary_adoption_normal import _retrieve_readout,_set_host_proof
R=Path(__file__).resolve().parent
P=Path('/Users/brummerv/.codex/sessions/2026/09/14/rollout-2026-09-14T14-07-34-01a09e19-5048-79d3-96dd-697eda8a4ac8.jsonl')
THREAD='01a09e19-5048-79d3-96dd-697eda8a4ac8';TURN='01a09f76-8dc6-7cc1-a0c3-4974e6a44eed'
records,raw=_read_rollout(P)
start=next(i for i,x in enumerate(records) if x['type']=='event_msg' and x['payload'].get('type')=='task_started' and x['payload'].get('turn_id')==TURN)
interval=[(i+1,x) for i,x in enumerate(records) if i>=start]
outer,blocks=_collect_outer(interval)
contexts=[{'line':i,'model':x['payload'].get('model'),'effort':x['payload'].get('effort')} for i,x in interval if x['type']=='turn_context' and x['payload'].get('turn_id')==TURN]
assert all(x['model']=='gpt-6-astra' and x['effort']=='ultra' for x in contexts)
for n in [23,24]:
 row=next(x for x in json.loads((R/'schedule.json').read_text())['rows'] if x['run_id']==f'run-{n}')
 metadata={'thread_id':THREAD,'turn_id':TURN,'target_repo':row['source_root']}
 all_calls,_=_collect_operations(interval,metadata);_correlate_delivery(all_calls,blocks)
 calls=[x for x in all_calls if x['arguments'].get('repo')==row['source_root']];normal=[];expected=[]
 for c in calls:
  readout=_retrieve_readout(c);_set_host_proof(readout,c.get('model_delivery'));normal.append({'item_id':c['item_id'],**readout})
  packet=c['result']['structuredContent']
  for source in packet['sources']:
   b=(Path(row['source_root'])/source['file']).read_bytes();assert hashlib.sha256(b).hexdigest()==source['content_hash'];assert b[source['start_byte']:source['end_byte']].decode()==source['content']
  for rel in packet['relationships']:
   e=rel['edge'];wanted=(n==23 and e['from']=='src/tool-results/service.ts::CaptureCommandResultOptions#type' and e['to']=='src/work-context/binding.ts::WorkContextBinding#type' and e['type']=='uses_type') or (n==24 and e['from']=='bin/anvil.ts::main#function' and e['to']=='src/browser/cli.ts::runBrowserCli#function' and e['type']=='calls')
   if wanted:expected.append({'item_id':c['item_id'],'relationship':rel,'model_delivery':c['model_delivery'],'normal_proof_status':readout['actual_host_proof_status']})
 out={'run_id':row['run_id'],'schedule':row,'native_rollout_path':str(P),'thread_id':THREAD,'turn_id':TURN,'native_contexts':contexts,'parent_observer_limitation':'The whole-turn observer rejects two turn_context records caused by compaction. These call-level receipts use its unchanged operation/correlation helpers and normal-v2 proof/byte validators on original native line numbers; no synthetic turn or per-case provider costs.','parent_prefix':{'start_line':start+1,'end_line':len(records),'sha256':hashlib.sha256(b''.join(raw[start:])).hexdigest()},'mcp_calls':calls,'normal_calls':normal,'all_returned_source_hashes_and_spans_valid':True,'expected_relationships':expected,'pass':any(x['normal_proof_status']=='validated' and x['model_delivery']['status']=='full_exact' for x in expected),'scope':'Known-answer primary functional check; normal query continuations retained. Not unprimed or a per-case completed provider-cost sample.'}
 (R/'runs'/row['run_id']/'primary-check.json').write_text(json.dumps(out,indent=2)+'\n')
 print(n,out['pass'],[(x['item_id'],x['model_delivery']['status']) for x in calls],len(expected))
