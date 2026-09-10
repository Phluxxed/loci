import collections,json,hashlib
from pathlib import Path
from benchmarks.typescript_context_baseline import HARNESS_FILES,ROOT,environment,sha,wire,save
from benchmarks.typescript_context_corpus import load_corpus,load_controls,check_answer
from benchmarks.typescript_context_trace import replay
corpus=load_corpus(); controls=load_controls(corpus)
root=ROOT/'benchmarks/results/typescript-context-baseline-v1'
env=json.loads((root/'environment.json').read_text())
assert environment(controls)=={k:env[k] for k in controls['environment']}
assert env['harness_files']=={str(p.relative_to(ROOT)):sha(p.read_bytes()) for p in HARNESS_FILES}
assert env['harness_commit']=='310caddedbf085ed28f395b0cc799bbd164c75a6'
summary=json.loads((root/'summary.json').read_text())
assert summary['batch']['complete_batch'] and summary['batch']['recorded_runs']==51
identities=set(); sessions=set(); provider_sessions=set(); schemas=set(); groups=collections.defaultdict(collections.Counter); limits=collections.Counter(); mismatches=[]
for case in corpus['cases']:
 for repetition in range(1,4):
  directory=root/f"{case['id']}-r{repetition}"
  artifact=json.loads((directory/'result.json').read_text()); measurement=artifact['measurement']; baseline=artifact['baseline']
  assert replay(corpus,artifact)==measurement
  identity=(measurement['task_id'],measurement['arm'],measurement['repetition'])
  assert identity==(case['id'],'A',repetition) and identity not in identities; identities.add(identity)
  assert measurement['session_id'] not in sessions; sessions.add(measurement['session_id'])
  assert baseline['provider_thread_id'] and baseline['provider_thread_id'] not in provider_sessions; provider_sessions.add(baseline['provider_thread_id'])
  audit=json.loads((directory/'request-audit.json').read_text()); request=audit['request']
  assert audit['request_sha256']==sha(wire(request).encode())
  assert request['model']=='gpt-5.6-luna' and request['reasoning']['effort']=='high'
  assert request['input'][-1]['content']==[{'type':'input_text','text':controls['agent']['common_prompt']+case['prompt']}]
  schemas.add(sha(wire({'tools':[x['tools'] for x in request['input'] if x['type']=='additional_tools']}).encode()))
  provenance=json.loads((directory/'provenance.json').read_text())
  assert provenance['snapshot_files']==corpus['snapshots'][case['snapshot']]['files']
  assert provenance['config_sha256']==sha(wire(provenance['config']).encode())
  assert provenance['run']['session_id']==measurement['session_id']
  group='maintained3' if case['group']=='maintained_task' else 'fixture14'
  groups[group]['runs']+=1; groups[group]['fully_passing_runs']+=measurement['task_correct']; groups[group]['oracle_matching_answers']+=check_answer(corpus,case['id'],measurement['answer'])
  groups[group][measurement['outcome']]+=1
  if measurement['outcome']=='completed' and not measurement['task_correct']: groups[group]['incorrect_answer']+=1
  for failure in baseline['failures']:
   limits.update(failure.get('limits',[]))
  if not check_answer(corpus,case['id'],measurement['answer']):
   mismatches.append({'case':case['id'],'repetition':repetition,'differences':[{'key':k,'expected':v,'actual':measurement['answer'].get(k)} for k,v in case['answer'].items() if measurement['answer'].get(k)!=v]})
assert len(schemas)==1
verification={'verified':True,'recorded_runs':len(identities),'exact_trace_replays':51,'unique_trace_sessions':len(sessions),'unique_provider_sessions':len(provider_sessions),'canonical_tool_schema_sha256':next(iter(schemas)),'frozen_environment_and_harness_hashes':'unchanged','effective_prompts_models_and_snapshot_manifests':'51 verified','groups':dict(groups),'budget_limits_triggered':dict(limits),'oracle_answer_mismatches':mismatches,'meaning':'Artifact integrity verified; failed runs and incomplete measurement remain failures/inconclusive, not acceptance.'}
save(root/'verification.json',verification)
print(json.dumps({**verification,'oracle_answer_mismatches':len(mismatches),'costs':summary['costs'],'maintained_p95':summary['latency']['maintained_p95_end_to_end_seconds'],'inconclusive_reads':len(summary['context_and_causality']['null_or_inconclusive_runs'])},indent=2))
