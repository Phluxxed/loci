"""Main Steward: supersede stale pending-restart orientation, preserve history."""
import json,re,yaml
from pathlib import Path
from llm_wiki_core.temporal_persistence import build_temporal_claim_revision,parse_temporal_claim_revisions
R=Path('/Users/brummerv/.anvil-brain/codex');D=json.loads(Path('/Users/brummerv/loci/.scratch/deterministic-graph-retrieval/brain-post-maintenance.json').read_text());source='sources/loci-normal-graph-adoption-result-2026-09-14.md';p=R/source
assert not p.exists()
changes={}
for c in D['proposal']['candidates']:
 name=c['subject']['page'];p=R/name;original=p.read_text();a,front,body=original.split('---',2);f=yaml.safe_load(front);old=parse_temporal_claim_revisions(f);prior=next(x for x in reversed(old) if x.predicate==c['predicate']);new=build_temporal_claim_revision(subject=c['subject'],predicate=c['predicate'],object_ref=c['object'],world_validity=c['proposed_world_validity'],recorded_at=D['recorded_at'],candidate_ids=[c['candidate_id']],observation_ids=c['supporting_observation_ids'],steward_evidence_refs=[source],decision="supersede",supersedes_revision_ids=[prior.revision_id]).to_dict();history=f['temporal_claim_revisions']+[new];parse_temporal_claim_revisions(history)
 # History is the final frontmatter field; append a native YAML list record.
 assert list(f)[-1]=='temporal_claim_revisions'
 updated=front.rstrip()+'\n'+yaml.safe_dump([new],sort_keys=False,allow_unicode=True)
 indent=re.search(r'evidence:\n( *)-',front).group(1)
 updated=updated.replace('evidence:\n','evidence:\n'+indent+'- '+source+'\n',1)
 updated=re.sub(r'^timestamp:.*$', 'timestamp: '+D['recorded_at'],updated,flags=re.M)
 desc='Actual-host deterministic retrieval; frozen ordinary value comparison negative, W1.8.4 required acceptance remains open.' if name.startswith('projects/') else 'Activated deterministic retrieval with measured selection and output-delivery limits; ordinary value acceptance remains negative.'
 updated=re.sub(r'^description:.*$', 'description: '+desc,updated,flags=re.M)
 if name.startswith('projects/'):
  start=body.index('## Current Orientation');end=body.index('### Previous exploration Objective')
  body=body[:start]+'''## Current Orientation

The ordinary graph-adoption Objective remains in Implementation. Deterministic
normal graph retrieval is activated in actual Codex hosts, with exact source,
complete selected proof and native output accounting verified. Agents supply
queries or known anchors; Loci owns the graph policy and budgets.

**W1.8.3 is complete with a negative value verdict. Next: W1.8.4.** All ten
reserved observations are retained. All eight fresh ordinary agents invoked
Loci, versus four at baseline; six received a complete positive graph delivery,
versus two. But only two of four binding/browser rows met that delivery check,
strict answer completeness fails, only one of two primary expected-proof checks
passes, and several case cost medians exceed the frozen 25% allowance.

The browser caller proof is delivered. The selected binding identity relationship
is still omitted; truncated outputs and repeated-call attribution also prevent
complete evidence delivery. Activation and graph counts therefore do not close
required useful-context, correctness or cost acceptance. Preserve both frozen
comparisons. No further provider batch is selected by this closeout. This small
workload establishes neither general adoption nor internal reliance or efficiency.

See [actual-host and frozen result evidence](./sources/loci-normal-graph-adoption-result-2026-09-14.md).
Use the current [ordinary adoption Objective](http://127.0.0.1:27247/objectives/obj_47c29425d32907d2bde961f1fd313970?repository=%2FUsers%2Fbrummerv%2Floci).
Manifest owns planning and implementation; use card IDs in user-facing updates.

'''+body[end:]
 else:
  body=body.replace('Objective. Its deterministic normal retrieval interface is implemented; actual\nhost activation and the reserved adoption observations remain open. The earlier\nexploration Objective is completed history, not the current planning state.', 'Objective. Its deterministic normal retrieval interface is active in actual\nCodex hosts. The reserved ordinary comparison completed with a negative value\nverdict; W1.8.4 remains open for required selection, delivery and cost acceptance.\nThe earlier exploration Objective remains completed history.')
  oldtext='''unsupported observations never become guessed trusted edges. Check the loaded
host before claiming activation: the current session still has the older catalog,
so W1.6.3 starts with actual-host discovery and capture after a fresh session.
Standalone service/stdio tests establish implementation, not ordinary uptake or
answer benefit.'''
  newtext='''unsupported observations never become guessed trusted edges. Actual native
retrieve/read receipts now prove host activation and complete selected evidence.
The frozen ordinary workload shows invocation in eight of eight attempts and
complete positive graph delivery in six, but only two of four binding/browser
rows meet that delivery check. Required answer, primary-proof and cost gates fail.
Budget omissions, outer-output truncation and repeated-call attribution remain
measured limits. Complete delivery does not establish useful selection, internal
reliance or causal answer benefit. Check each loaded host before assuming it has
the same activated surface.'''
  assert oldtext in body;body=body.replace(oldtext,newtext)
  body=body.replace('## Evidence\n','## Evidence\n\n- [Activated normal graph retrieval and negative ordinary value result](./sources/loci-normal-graph-adoption-result-2026-09-14.md)\n',1)
 final=a+'---'+updated+'---'+body;parsed=parse_temporal_claim_revisions(yaml.safe_load(final.split('---',2)[1]));assert len(parsed)==len(old)+1;assert [x.to_dict() for x in parsed[:-1]]==[x.to_dict() for x in old];changes[p]=final;print(name,'history',len(old),'->',len(parsed),'new',new['revision_id'])
(R/source).write_text(D['source'])
for p,text in changes.items():p.write_text(text)
p=R/'index.md';s=p.read_text();s=re.sub(r'^\* \[Loci\]\(\./projects/loci.md\).*$', '* [Loci](./projects/loci.md) - Actual-host deterministic retrieval activated; frozen ordinary value verdict negative, W1.8.4 required acceptance remains open.',s,flags=re.M);p.write_text(s)
with (R/'log.md').open('a') as f:f.write('''
## [2026-09-14] correction | Activated Loci graph retrieval; frozen value acceptance remains negative

Main Steward accepted two read-only proposal candidates after original native
host, source/hash and frozen comparison checks. Superseded stale pending-restart
claims with activation, measured8/8 invocation and6/8 complete graph delivery,
failed required-context/answer/cost gates, and open W1.8.4 acceptance. Preserved
all prior temporal records and validated complete histories before writing.
Added one immutable bounded source; no raw private runtime store was copied.
Primitive classifications remain appropriate and unchanged; no classification
counts or Collaboration Kernel surface changed. Unrelated Brain edits retained.
''')
