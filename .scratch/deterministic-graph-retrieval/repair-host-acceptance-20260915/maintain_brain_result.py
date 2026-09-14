"""Main Steward maintenance after the selected binding comparison."""
import hashlib
import json
from pathlib import Path
import re
import yaml
from llm_wiki_core.temporal_persistence import build_temporal_claim_revision, parse_temporal_claim_revisions

ROOT = Path('/Users/brummerv/.anvil-brain/codex')
data = json.loads(Path(__file__).with_name('brain-result-maintenance.json').read_text())
source = data['proposal']['source']['source_ref']
assert not (ROOT / source).exists()
assert hashlib.sha256(data['source'].encode()).hexdigest() == data['proposal']['source']['content_hash']
changes = {}
for candidate in data['proposal']['candidates']:
    name = candidate['subject']['page']
    path = ROOT / name
    prefix, front, body = path.read_text().split('---', 2)
    metadata = yaml.safe_load(front)
    old = parse_temporal_claim_revisions(metadata)
    prior = next(r for r in reversed(old) if r.predicate == candidate['predicate'])
    revision = build_temporal_claim_revision(
        subject=candidate['subject'], predicate=candidate['predicate'], object_ref=candidate['object'],
        world_validity=candidate['proposed_world_validity'], recorded_at=data['recorded_at'],
        candidate_ids=[candidate['candidate_id']], observation_ids=candidate['supporting_observation_ids'],
        steward_evidence_refs=[source], decision='supersede', supersedes_revision_ids=[prior.revision_id],
    ).to_dict()
    parse_temporal_claim_revisions(metadata['temporal_claim_revisions'] + [revision])
    assert list(metadata)[-1] == 'temporal_claim_revisions'
    updated = front.rstrip() + '\n' + yaml.safe_dump([revision], sort_keys=False, allow_unicode=True)
    indent = re.search(r'evidence:\n( *)-', front).group(1)
    updated = updated.replace('evidence:\n', 'evidence:\n' + indent + '- ' + source + '\n', 1)
    updated = re.sub(r'^timestamp:.*$', 'timestamp: ' + data['recorded_at'], updated, flags=re.M)
    description = ('Live repair verified; two binding attempts reduce input but still fail cost and ordinary uptake acceptance.'
                   if name.startswith('projects/') else
                   'Active deterministic graph retrieval with measured host discovery, anchor-selection and wrapper-accounting limits.')
    updated = re.sub(r'^description:.*$', 'description: ' + description, updated, flags=re.M)
    if name.startswith('projects/'):
        start, end = body.index('## Current Orientation'), body.index('### Previous exploration Objective')
        body = body[:start] + '''## Current Orientation

The ordinary graph-adoption Objective remains in Implementation. Normal context
retrieval runs graph policy deterministically. The repaired selection policy is
now active in the actual restarted Codex host: binding options/pair proof,
browser and renderer relationships, native byte accounting and exact two-page
source hydration passed. The old restart blocker is resolved.

**Next: W1.8.4.4 follow-through on the negative ordinary result.** Vik selected
two fresh binding tasks under a separate pre-outcome freeze. Median input fell
47.4% from the pre-repair pair to 357,203 tokens, but remains 1.4328 times the
original baseline, above the unchanged 1.25 limit. Visible bytes and elapsed
time pass. Both answers identify the accepted binding and view-field difference;
strict compound-fact reviews remain separate from core-answer correctness.

Only one of the two agents invoked Loci. Its two requests returned nine semantic
relationships but missed the specific repaired binding type edge. The other
agent's broad tool-description dump was truncated, hiding both normal Loci tool
names from its displayed discovery result; it continued with shell searches.
These results do not establish graph-only savings or reliable ordinary uptake.

Both Loci result objects were intact inside JSON wrappers. Frozen delivery-v3
missed those nested values; separate strict decoded-object adjudication retains
their complete original byte provenance. Earlier frozen scores stay unchanged.
The remaining observed gaps are bounded host discovery, normal-question anchor
selection and separately versioned wrapper accounting. The two selected attempts
are complete; no additional campaign or product fix is selected by the result.

See [live repair and binding measurement evidence](./sources/loci-live-repair-binding-measurement-2026-09-15.md).
Use the current [ordinary adoption Objective](http://127.0.0.1:27247/objectives/obj_47c29425d32907d2bde961f1fd313970?repository=%2FUsers%2Fbrummerv%2Floci).
Manifest owns planning and implementation; use card IDs in user-facing updates.

''' + body[end:]
    else:
        old_text = 'accounting; W1.8.4.4 awaits repaired host activation and ordinary value acceptance.'
        assert old_text in body
        body = body.replace(old_text, 'accounting. Repaired host activation now passes; W1.8.4.4 retains failed ordinary\nvalue acceptance after the selected two-task comparison.')
        start = body.index('unsupported observations never become guessed trusted edges.')
        end = body.index('\nStages 7-11', start)
        body = body[:start] + '''unsupported observations never become guessed trusted edges. Actual native
receipts now establish the repaired host's complete binding proof, browser and
renderer controls, exact source paging and byte accounting. The selection policy
gives direct selected-anchor relationships priority over incidental ownership
expansion without increasing budgets or weakening proof.

Ordinary routing remains unreliable in the selected two-binding workload: only
one agent invoked Loci, and its broad-query/file anchors did not deliver the
specific repaired type edge. The other agent's truncated broad discovery output
omitted both normal Loci tool names before it used shell reads. A missing name
in truncated discovery is not proof that the server is unavailable.

The two complete result objects in the first attempt were wrapped in larger JSON.
Frozen delivery-v3 undercounts this shape; separate exact nested-object evidence
preserves original byte provenance without changing frozen scores. Complete
delivery does not establish cognition or the right anchor selection. Median
input improved from the pre-repair pair but still exceeds the original cost
allowance; broader ordinary answer/cost acceptance remains open.
''' + body[end:]
        body = body.replace('## Evidence\n', '## Evidence\n\n- [Live repair and two binding measurements](./' + source + ')\n', 1)
    final = prefix + '---' + updated + '---' + body
    parsed_metadata = yaml.safe_load(final.split('---', 2)[1])
    parsed = parse_temporal_claim_revisions(parsed_metadata)
    assert len(parsed) == len(old) + 1
    assert [r.to_dict() for r in parsed[:-1]] == [r.to_dict() for r in old]
    assert parsed_metadata['evidence'] == [source] + metadata['evidence']
    changes[path] = final
    print(name, len(old), '->', len(parsed), revision['revision_id'])
(ROOT / source).write_text(data['source'])
for path, text in changes.items():
    path.write_text(text)
path = ROOT / 'index.md'
text, count = re.subn(r'^\* \[Loci\]\(\./projects/loci.md\).*$', '* [Loci](./projects/loci.md) - Live graph repair verified; two binding attempts improve input but leave W1.8.4.4 cost, discovery and anchor-selection acceptance open.', path.read_text(), flags=re.M)
assert count == 1
path.write_text(text)
with (ROOT / 'log.md').open('a') as stream:
    stream.write('''
## [2026-09-15] correction | Loci live repair and negative two-binding comparison

Main Steward accepted two read-only candidates after native source/proof/paging,
exact output and frozen cost checks. Replaced stale pending-restart orientation
with verified activation and the completed user-selected pair: lower input than
before repair, still above the original limit, one-of-two Loci invocation and
missed ordinary type-edge selection. Preserved nested-wrapper undercount and
separate exact adjudication rather than rewriting frozen scores. No causal or
full-workload acceptance claim. Added one immutable source and validated full
temporal histories/evidence arrays before writing. Primitive classifications
remain appropriate and unchanged; no kernel or coverage-count change. Unrelated
Brain edits remain intact.
''')
