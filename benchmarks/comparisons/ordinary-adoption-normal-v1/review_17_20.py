"""Replay the primary's explicit semantic judgments for rows17–20."""
import json,hashlib
from pathlib import Path
from benchmarks.ordinary_adoption_normal import normal_evidence_registry
from benchmarks.ordinary_adoption_review import assess_review
R=Path(__file__).resolve().parent
C=json.loads((R.parent/'ordinary-adoption-v1/cases.json').read_text())
for n in [17,18,19,20]:
 p=R/'runs'/f'run-{n}';d=json.loads((p/'observation.json').read_text());m=json.loads((p/'metadata.json').read_text());m=m.get('observer_metadata',m);o=d['observation'];answer=''.join(x['text'] for x in o['outcome']['final_answer']['content'] if x['type']=='Text');(p/'finalanswer.md').write_text(answer);case=next(x for x in C['cases'] if x['id']==m['case_id']);reg=normal_evidence_registry(d)
 facts=[]
 for f in case['required_facts']:
  if n==20 and f['id'] in ['main_browser_branch_calls_feature','import_reexport_path']:
   facts.append({'fact_id':f['id'],'judgment':'missing'})
  else:facts.append({'fact_id':f['id'],'judgment':'correct','answer_quote':answer,'source_references':f['sources']})
 rel=[]
 if n in [18,19]:
  quote='`summary` and `next_step` pass through `truncateText`.';item=next(k for k,v in reg.items() if v['model_output_refs']);rel=[{'answer_quote':quote,'status':'supported','native_item_id':item,'model_output_evidence_reference':reg[item]['model_output_refs'][0]}]
 if n==17:
  item=next(k for k,v in reg.items() if v['model_output_refs']);rel=[{'answer_quote':'re-exports the implementation from `cli.ts`.','status':'supported','native_item_id':item,'model_output_evidence_reference':reg[item]['model_output_refs'][0]}, {'answer_quote':'Loci’s static graph proves the `main → runBrowserCli` call at line 1463.','status':'ambiguous_provenance'}]
 q={17:['All three required facts are present. Browser runner defaults exist at cli.ts216,335,385,430,524; answer groups that correct claim under imprecise555–557 citation. Package registration is9–10, citation8 points immediately above. These location imprecisions are retained, not material false claims.','The full_exact packet proves index.ts imports/re-exports cli.ts and supplies declaration evidence. The later main-to-runBrowserCli graph packet is truncated; no full_exact support credit for that separate claim. Malformed source_ref error and all truncated packets remain counted.'],18:['Exact renderer strings and truncateText calls match67–75; complete delivered calls edge corroborates stated relationship without establishing internal reliance.'],19:['Exact strings matchrender67–75; strict five-field schema and state enum verifiedschema38–50. Delivered call edge supports truncateText statement.'],20:['Required main branch fact is incomplete: answer omits nonzero return propagation to process.exitCode. Import path fact gives the barrel re-export but does not state the production entrypoint imports through that barrel. Both incomplete compound facts are marked missing under strict all-facts gate, not false source claims.','Both identical retrieval results are ambiguous_exact; no graph-delivery credit despite relationships in backend results. Failed git status on source copy without.git is retained.']}[n]
 review={'reviewer':'primary gpt-6-astra/ultra','fact_judgments':facts,'relationship_support':rel,'material_unsupported_claims':[],'qualifications':q};(p/'review.json').write_text(json.dumps(review,indent=2)+'\n');assessment=assess_review(case,answer,review,reg);assessment['strict_correct']=all(x['judgment']=='correct' for x in facts);(p/'assessment.json').write_text(json.dumps(assessment,indent=2)+'\n')
 cmds=[{'item_id':x['item_id'],'command':x['command'],'cwd':x.get('cwd'),'native_graph_activity':x.get('graph_activity'),'review':'Only assigned source paths or installed Loci operating instructions; no tests/services/mutations or outside source evidence observed.'} for x in o['shell_calls']]
 access={'reviewer':'primary','status':'valid','all_shell_commands_reviewed':True,'commands':cmds,'mcp_calls':[{'item_id':x['item_id'],'tool':x['tool'],'target_repo':x.get('target_repo'),'arguments':x['arguments']} for x in o['mcp_calls']],'limitations':['Native opaque shell classification retained; manual command review does not change frozen cost or graph metrics.','Upstream silent native omissions remain undetectable.']};(p/'access-review.json').write_text(json.dumps(access,indent=2)+'\n')
 print(n,assessment['judgment_counts'],assessment['strict_correct'],len(rel))
