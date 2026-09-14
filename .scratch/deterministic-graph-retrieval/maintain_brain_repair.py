"""Main Steward: correct delivery history and record the bounded repair."""
import hashlib
import json
from pathlib import Path
import re

import yaml
from llm_wiki_core.temporal_persistence import (
    build_temporal_claim_revision,
    parse_temporal_claim_revisions,
)

ROOT = Path('/Users/brummerv/.anvil-brain/codex')
RECEIPT = Path('/Users/brummerv/loci/.scratch/deterministic-graph-retrieval/brain-repair-maintenance.json')
data = json.loads(RECEIPT.read_text())
source = data['proposal']['source']['source_ref']
assert not (ROOT / source).exists()
assert hashlib.sha256(data['source'].encode()).hexdigest() == data['proposal']['source']['content_hash']
changes = {}
for candidate in data['proposal']['candidates']:
    name = candidate['subject']['page']
    path = ROOT / name
    original = path.read_text()
    prefix, front, body = original.split('---', 2)
    metadata = yaml.safe_load(front)
    old = parse_temporal_claim_revisions(metadata)
    prior = next(r for r in reversed(old) if r.predicate == candidate['predicate'])
    revision = build_temporal_claim_revision(
        subject=candidate['subject'], predicate=candidate['predicate'],
        object_ref=candidate['object'], world_validity=candidate['proposed_world_validity'],
        recorded_at=data['recorded_at'], candidate_ids=[candidate['candidate_id']],
        observation_ids=candidate['supporting_observation_ids'],
        steward_evidence_refs=[source], decision='supersede',
        supersedes_revision_ids=[prior.revision_id],
    ).to_dict()
    parse_temporal_claim_revisions(metadata['temporal_claim_revisions'] + [revision])
    assert list(metadata)[-1] == 'temporal_claim_revisions'
    updated = front.rstrip() + '\n' + yaml.safe_dump([revision], sort_keys=False, allow_unicode=True)
    indent = re.search(r'evidence:\n( *)-', front).group(1)
    updated = updated.replace('evidence:\n', 'evidence:\n' + indent + '- ' + source + '\n', 1)
    updated = re.sub(r'^timestamp:.*$', 'timestamp: ' + data['recorded_at'], updated, flags=re.M)
    description = ('Deterministic selection repaired; delivery undercount corrected; W1.8.4.4 awaits host restart and ordinary value acceptance.'
                   if name.startswith('projects/') else
                   'Deterministic anchor-proof selection with bounded evidence; corrected delivery accounting and explicit host activation limits.')
    updated = re.sub(r'^description:.*$', 'description: ' + description, updated, flags=re.M)
    if name.startswith('projects/'):
        start = body.index('## Current Orientation')
        end = body.index('### Previous exploration Objective')
        body = body[:start] + '''## Current Orientation

The ordinary graph-adoption Objective remains in Implementation. Normal context
retrieval runs graph policy deterministically; agents supply queries or known
anchors while Loci owns traversal and budgets.

**W1.8.4.1/.2/.3 are complete. Next: W1.8.4.4 after a host restart.** The
binding proof existed but incidental ownership expansion crowded it out. Repaired
source stages direct anchor relationships first; the fixed options and explicit
pair checks now deliver complete import/barrel/type proof within the unchanged
16 KB ceiling. Browser and renderer relationship controls still pass.

The delivery audit also corrects our earlier reading: the frozen observer
under-counted intact JSON-line values and applied truncation warnings too broadly.
Its six-of-eight delivery count remains a historical computed result. Run 21
actually has five exact retrievals, one clipped retrieval and one exact read.
The separate supplementary observer preserves old scores and original output
provenance. Repeated identical invocations still lack unique host attribution;
outer output caps and callers discarding structured results remain real limits.

The actual-host options check still returns the exact pre-repair packet. Restart
must precede repaired live-path acceptance. All 45 frozen inputs remain intact.
Binding input really increased 2.7236 times baseline (uncached input 1.7380 times),
with more responses and larger contexts. Source regressions and corrected
measurement do not demonstrate savings. The original strict-answer and cost
failures remain open; no additional provider campaign is selected.

See [repair and corrected delivery evidence](./sources/loci-retrieval-selection-and-delivery-repair-2026-09-14.md)
and [historical frozen result](./sources/loci-normal-graph-adoption-result-2026-09-14.md).
Use the current [ordinary adoption Objective](http://127.0.0.1:27247/objectives/obj_47c29425d32907d2bde961f1fd313970?repository=%2FUsers%2Fbrummerv%2Floci).
Manifest owns planning and implementation; use card IDs in user-facing updates.

''' + body[end:]
    else:
        old_status = '''verdict; W1.8.4 remains open for required selection, delivery and cost acceptance.
The earlier exploration Objective remains completed history.'''
        assert old_status in body
        body = body.replace(old_status, '''verdict. W1.8.4.1/.2/.3 now reconcile cost, repair selection and correct delivery
accounting; W1.8.4.4 awaits repaired host activation and ordinary value acceptance.
The earlier exploration Objective remains completed history.''')
        start = body.index('unsupported observations never become guessed trusted edges.')
        end = body.index('\nStages 7-11', start)
        body = body[:start] + '''unsupported observations never become guessed trusted edges. Actual native
retrieve/read receipts establish activation of normal graph retrieval. Repaired
source now gives direct selected-anchor relationships priority over incidental
ownership expansion without increasing budgets or weakening proof. The current
long-lived host still returns the pre-repair packet; restart and verify each
loaded host before claiming the repair is active.

The frozen observer's six-of-eight positive-delivery count under-counted intact
JSON-line values; its scores remain historical. A separate supplement recognizes
exact line and whole-block JSON with original byte provenance and local clipping
qualification. Run 21 had five intact retrieves, one clipped retrieve and an
intact read. Identical invocations remain ambiguous without trusted host identity.
Loci cannot control aggregate outer caps or recover a return value discarded by
caller code. Corrected delivery accounting does not establish cognition, answer
benefit or lower cost; the original ordinary answer and cost failures remain.
''' + body[end:]
        body = body.replace('## Evidence\n', '## Evidence\n\n- [Selection repair and corrected delivery evidence](./' + source + ')\n', 1)
    final = prefix + '---' + updated + '---' + body
    parsed_metadata = yaml.safe_load(final.split('---', 2)[1])
    parsed = parse_temporal_claim_revisions(parsed_metadata)
    assert len(parsed) == len(old) + 1
    assert [r.to_dict() for r in parsed[:-1]] == [r.to_dict() for r in old]
    assert parsed_metadata['evidence'] == [source] + metadata['evidence']
    changes[path] = final
    print(name, 'history', len(old), '->', len(parsed), revision['revision_id'])

(ROOT / source).write_text(data['source'])
for path, text in changes.items():
    path.write_text(text)
path = ROOT / 'index.md'
text = path.read_text()
text, count = re.subn(r'^\* \[Loci\]\(\./projects/loci.md\).*$', '* [Loci](./projects/loci.md) - Selection repaired and delivery undercount corrected; W1.8.4.4 awaits host restart and ordinary value acceptance.', text, flags=re.M)
assert count == 1
path.write_text(text)
with (ROOT / 'log.md').open('a') as stream:
    stream.write('''
## [2026-09-14] correction | Loci proof selection repair and delivery undercount

Main Steward accepted two read-only temporal candidates after direct source,
retained output and actual-host checks. Corrected the broad truncation claim,
qualified frozen delivery counts, and recorded bounded selection repair with
host restart still required. Ordinary correctness/cost remains unaccepted;
no provider campaign or token savings were invented. Preserved and validated
all prior temporal revisions and evidence arrays before writing. Added one
immutable source; no raw private sessions copied. Primitive classifications
remain appropriate and unchanged; no count or Collaboration Kernel change.
Unrelated Brain edits remain intact.
''')
