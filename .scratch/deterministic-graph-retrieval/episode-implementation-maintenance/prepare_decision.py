"""Main Steward's minimal body updates; canonical records use the existing helper."""
from pathlib import Path
import json

folder = Path(__file__).parent
path = folder / 'decision.json'
data = json.loads(path.read_text())
root = Path('/Users/brummerv/.anvil-brain/codex')
source = data['proposal']['source']['source_ref']
start_old = '**Next: W1.8.4.4.10.2.2 — implement the matched comparison and episode accounting.**'
common = '''**W1.8.4.4.10.2.2 is complete, published at `57b91ee`.**
The matched control, three-turn native controller, source-version and cumulative
usage accounting, isolated dependency preparation and independent Anvil/Loci
oracles now exist. Five implementation leaves have evidence; Manifest reads
54/58 completed leaves. Local scripted and real MCP integration checks pass for
both arms, source edits and stage-snapshot replay. Unchanged and faulty oracle
controls fail; disposable reference changes pass. Normal Loci gains an internal
shared selection seam and no public graph switch or .direnv feature change.

Accounting separates orientation from downstream effort, retains unsuccessful
work, requires every scheduled row and marks interrupted complete totals unknown
while preserving observed partial usage. Native delivery joins distinguish exact,
ambiguous and missing evidence, and count repeated spans only for the same source
version. Graph proof delivered still does not establish internal model reliance.
Final claims, invariants and rework need the predeclared arm-blinded review.

**Next: W1.8.4.4.10.2.3 — actual-host preflight and campaign freeze.**
The installed App Server advertises Terra/high, but native filesystem sandbox
setup fails with exit71, `sandbox_apply: Operation not permitted`. Both own-canary
probes and the integrated thread/start fail before a model turn; an approved
retry also failed. This is an OS/runtime limitation, not an approval-review
rejection. No isolation was weakened, freeze published or episode launched.
A host capable of enforcing the profile is required. Native context/partial
usage/outer-call capture, effective instructions and dependency equality still
need verification before the eight episodes in .10.2.4 can start.

A fresh396-file Loci export installed dependencies and indexed successfully.
Preparation constrains tree-sitter0.25.2 from its uv.lock after0.26 segfaulted;
full environment and failed setup provenance remain retained. Anvil's original
638-file map and lockfile support its passing original regression controls.
The prepared config and runnable commands are recorded in the implementation
README and native-preflight receipt. Prepared diagnostic output is not a
campaign freeze and must not be overwritten as a retry.

The complete-work design remains eight episodes, two task types, two repetitions,
graph-on/off throughout120/360/240-second same-thread turns. Correct terminal
behavior comes before the prospective whole/downstream time and normalized-cost
comparison. Historical1.25 binding gates, all older outcomes and final Objective
acceptance .10.3 remain unchanged. No value result, initial-packet causal claim,
verified billing or general workload acceptance is established.
See [the implementation and host limitation](./SOURCE),
[the completed protocol](./sources/loci-complete-work-protocol-2026-09-15.md)
and [the reframe](./sources/loci-complete-work-measurement-reframe-2026-09-15.md).

'''.replace('SOURCE', source)
page_edits = {}
for name in ['projects/loci.md', 'entities/loci.md']:
    body = (root/name).read_text().split('---', 2)[2]
    if name.startswith('projects'):
        begin = 'The ordinary graph-adoption Objective remains in Implementation.'
        end = "Normal retrieval's supported input-path priority"
        old_intro = '''The ordinary graph-adoption Objective remains in Implementation.
The complete-work protocol is defined. Next is **W1.8.4.4.10.2.2**: implement
the matched comparison, episode accounting and independent behavior checks.
Final acceptance is deferred behind the unperformed measurement.'''
        new_intro = '''The ordinary graph-adoption Objective remains in Implementation.
**W1.8.4.4.10.2.2 is complete at `57b91ee`.** Next is **W1.8.4.4.10.2.3**:
validate the native host and freeze the complete-work campaign. Native sandbox
setup currently blocks that preflight. No measured episode has run; final
acceptance remains deferred behind the unperformed measurement.'''
    else:
        begin = 'The [Loci project page]'
        end = 'Separately versioned delivery-v4 accounts'
        old_intro = '''Objective in Implementation. The complete-work design is finished; next is W1.8.4.4.10.2.2:
implement matched control, episode accounting and independent behavior checks. Deterministic normal retrieval and the installed'''
        new_intro = '''Objective in Implementation. The complete-work harness is implemented at `57b91ee`;
next is W1.8.4.4.10.2.3 actual-host preflight/freeze, blocked by native sandbox
setup before any model turn. No measured episode has run. Deterministic normal
retrieval and the installed'''
    original = body[body.index(begin):body.index(end, body.index(begin))]
    assert old_intro in original and start_old in original
    revised = original.replace(old_intro, new_intro, 1)
    revised = revised[:revised.index(start_old)] + common
    page_edits[name] = {'start': begin, 'end': end, 'new': revised}
data['page_edits'] = page_edits
data['index_line'] = '* [Loci](./projects/loci.md) - deterministic graph retrieval; complete-work harness published, next native preflight/freeze blocked by sandbox setup.'
data['log_entry'] = '\n## [2026-09-15] implementation | Loci complete-work harness published at57b91ee; native sandbox preflight remains blocked\n\nMain Steward adopted two canonical revisions after one candidate-only proposal. Matched control, source/usage accounting, isolated preparation and independent oracles are implemented and locally verified. No measured episodes ran. W1.8.4.4.10.2.3 needs a host that can enforce native isolation before campaign freeze. Historical gates and final acceptance remain unchanged.\n'
path.write_text(json.dumps(data, indent=2) + '\n')
