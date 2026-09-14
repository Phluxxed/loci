# Deterministic retrieval implementation worklog

Task authority is the existing Manifest. This file records delegated evidence
and primary decisions; it does not introduce additional completion gates.

## W1.7.2.1 — contract evidence, 14 September 2026

- `contract_graph_evidence`: Sol / high / fork none. Read-only ownership:
  existing graph edge record and source-proof assembly feasibility, including
  imports, references and calls across supported languages. Contribution:
  prevent the default policy promising evidence the resolver cannot deliver.
  Acceptance: source-backed minimal implementation seam, supported relationship
  matrix, concrete proof/ambiguity/budget gaps; no source edits or trials.
- `contract_acceptance`: Terra / high / fork none. Read-only ownership:
  existing frozen audit inputs and observer contracts. Contribution: specify
  honest numerical value gates and the smallest observer adapter needed before
  reserved post-change execution. Acceptance: preserve all historical rows,
  prompts, accounting semantics and ten reserved rows; separate mechanism,
  delivery and ordinary value. No model trials or mutations.

Primary owns the request/response, traversal/ranking policy, migration,
contract artifact and Manifest state. Both workers must complete their
assignment directly without spawning agents.

`contract_acceptance` returned source-backed findings against frozen protocol,
accounting, results and the existing observer. Primary adopted the 8/8 strict
correctness, exact-delivery and separate primary gates, with the proposed 25%
per-case cost ceiling as an explicit tradeoff rather than an efficiency claim.
The observer seam is versioned; historical rows/helpers remain unchanged.
Result is recorded in contract.md's Ordinary value acceptance section.

Reuse `contract_acceptance` (Terra/high; retained context fits the frozen audit)
for a read-only contradiction review of contract.md: identify unresolved rules,
hidden model-selected policy, unsupported claims and acceptance weakening.
Scope now includes the written interface contract, not source implementation.
Acceptance is an actionable list of material gaps or a qualified pass. No edits.

`contract_graph_evidence` returned a supported language matrix and import
endpoint proof decision. Primary adopted separate indexed ownership, unchanged
native file/package/module/crate endpoints, unique parsed full declaration
hydration and explicit proof omission on unsupported source. The normal packer
must not force zero-width endpoints into symbol-only exploration bundles.
Source owners: exploration.py `_records`/`_Source`, graph/imports.py
`ImportRecord`/`materialize_import_edges`, graph/state.py, graph/anchors.py,
graph/traversal.py, parser/symbols.py, graph/go_modules.py,
graph/_rust_resolution.py, graph/swift_modules.py and graph/builtins.py.
Result is incorporated in contract.md Structural traversal/File and package
context. The existing parser/resolver guarantees are unchanged.

The contract review identified five material gaps: model-visible proof gates,
exact-file query representation, source-reference provenance, typed response
shapes and target-degree definition. Primary resolved them explicitly in
contract.md and added contract.schema.json. The operation/byte accounting flags
remain reported flags, as the frozen protocol requires. The same reviewer is
checking these specific corrections to close the outstanding review; no new
review scope or model trials were added.

Final review closed those five gaps, conditional on correcting character-count
limits to UTF-8 byte validation. Primary removed the accidental shared string
maxLength values, recorded x-maxUtf8Bytes for query and retained runtime byte
limits. Draft 2020-12 schema validation passes. Disposition: adopted, corrected,
contract frozen. This is design acceptance, not product test evidence.

## Implementation assignments after contract freeze

- Reuse `contract_graph_evidence` as the engine implementer, Sol/high, original
  fork none. Retained source/proof context is directly relevant. Owned scope:
  new normal graph selection/source assembly/packing modules and focused engine
  tests only. Primary supplies retrieval_io.py helpers and service/MCP adapters.
  Contribution: W1.7.2.2 executes the frozen policy. Acceptance: current fixture
  source proves incoming/outgoing relationships, native import endpoints,
  bounded repeatability and truthful partial results through the normal engine.
- `catalog_integrity`: Terra/high/fork none. Owned scope:
  storage/repository_catalog.py, narrowly necessary IndexStore call-site changes
  and focused catalog concurrency tests. Contribution: W1.7.4 makes parallel
  ordinary retrieval usable. Acceptance: live owner waits/busy without crash
  repair, owner-only release, abandoned marker behavior and both roots retained.
  No live catalog repair. Do not edit retrieval/service/MCP or Manifest files.

Primary owns retrieval_io.py, service.py, mcp_server.py, output schemas,
integration, installed surfaces, Manifest and final judgment. Workers complete
directly without spawning agents. No benchmark/model trials until runtime freeze.

Transfer the MCP/models scope from primary to reused `contract_acceptance`
(Terra/high; original fork none). Retained reviewed contract/schema context fits.
Owned files: mcp_server.py, mcp_output_models.py, new normal MCP tests and the
minimal explicit-diagnostic setup of existing MCP tests. Contribution W1.7.2.3:
publish two normal operations with strict controls and validated response types,
preserving explicit diagnostic compatibility. Primary retains service.py and
retrieval_io.py. Acceptance: two-tool normal catalog, strict normal input/output,
normal/diagnostic startup selection and real stdio operation once engine lands.
No skill/installer/audit/Manifest edits or model trials.

Catalog primary review found three reachable races in the first implementation:
partial marker publication, completion between existence/read, and concurrent
repairs of an inherited marker. Worker replaced serialization with one POSIX
advisory lock covering readers/writers/repairs and atomic complete marker
publication. Primary inspected the corrected lock/repair paths. The reported
85 focused tests include deterministic publication overlap, spawned two-root
writes and inherited-marker repairs. Disposition: adopted. Filesystem advisory
locking remains a stated platform requirement; no live catalog was repaired.

`normal_observer_adapter`: Terra/high/fork none. Owned scope: new versioned
normal observer/readout module and its tests only. Contribution W1.6.1–W1.6.3:
measure normal source/proof delivery through the existing retained capture.
Acceptance: preserve frozen observer/review files and all old results; classify
normal calls once, validate complete source-backed edges, keep full_exact host
delivery separate, report invalid proof as unknown and source-free errors
honestly. Adapt existing readout without a new store or model trials.

`normal_observer_adapter` returned
`benchmarks/ordinary_adoption_normal.py` and
`tests/test_ordinary_adoption_normal.py`. The adapter wraps the frozen observer
without modifying it, recomputes normal source bytes/proof linkage, and exposes
a reviewer-compatible registry only for fully emitted validated results. Focused
normal, frozen observer, and frozen review tests passed. Primary disposition:
pending review.

Primary normal-service acceptance found JavaScript package-map imports lacked
their named control proof. Engine worker corrected exact tracked control
hydration for imports/calls/references/types, refusing missing/stale hashes.
The package-map reproducer passes, alongside explicit endpoints, cycles,
fan-out, large-source pagination, ambiguity, Rust and unsupported-call cases.

Reuse `contract_acceptance` (Terra/high, retained normal MCP interface context)
for the required first-party hook migration. Owned scope extends to
.claude/hooks/loci-enforce-read.py and tests/test_enforce_read_hook.py only.
Contribution W1.7.1: stop issuing legacy-only tool recipes in the normal host.
Acceptance: normal whole-file redirect is issued only after an isolated current
normal-service probe returns an exact whole-file source locator and validates
its first page; recipe uses retrieve/read. Existing broader/ranged/unsupported
operations remain outside the answer-equivalence redirect. Preserve explicit
diagnostic compatibility and namespace isolation. No private Claude home reads,
actual host/model trials, or registration changes.

Full-suite run retained at /tmp/loci-normal-integration-pytest.log: 2248 pass,
40 fail. Most failures are legacy subprocess tests still requesting diagnostic
tools without their new explicit surface. Primary is correcting the shared
proof reader's single-line compatibility. Reuse `contract_graph_evidence`
(Sol/high, retained resolver context) for read-only baseline attribution of
the remaining graph-schema/count/normalization and pinned-environment failures.
Acceptance: compare the exact failures against e8bb8fd using an isolated source
checkout that does not materialize a second Manifest; do not fix unrelated
baseline defects or edit frozen artifacts. Return reproduced versus new failures.

## Integration disposition

Engine and MCP deliveries are adopted after primary source review and public
acceptance. Root review corrected ownership-previsited edge suppression, anchor
starvation, full edge-record verification, named JS package-control proof,
large-source proof and source-free output failure for oversized mandatory anchor
identities. Explicit omissions retain supported-subset limits. Result locators:
src/loci/retrieval.py, _retrieval_source.py, _retrieval_output.py, retrieval_io.py,
service.py and tests/test_normal_retrieval_acceptance.py.

The observer adapter is adopted after primary review. Returned corrections reject
malformed source spans/identities, unsupported families, unproven traversal and
inconsistent delivered/traversed counts; source-free errors keep traversal
unknown. The final normal/frozen observer/review set passes 49 tests. This closes
code-level accounting work, not actual host capture in W1.6.3.

The MCP worker's final reuse (Terra/high; retained contract and stdio context)
was limited to explicit diagnostic setup in legacy subprocess fixtures. Six
direct helper environments changed; language tests inherit the shared helper.
Store isolation needed no change. All 57 affected legacy and normal MCP tests
pass. No suite-wide diagnostic override or frozen helper change was introduced.
Primary reviewed and adopted the fixture and hook changes. Hook acceptance
passes 20; canonical guidance and temporary installation checks pass 15.

The engine worker's read-only baseline attribution is adopted with its evidence
limitation: all six remaining unrelated assertions reproduce on clean detached
e8bb8fd (6 failures in 1.40 seconds). The sparse checkout excluded .manifest and
was removed afterward. Baseline output is in the session tool record only; no
separate baseline log was retained. Exact failure descriptions are in
docs/reviews/2026-09-14-normal-graph-retrieval-delivery.md. Primary restored exact
single-line proof newline compatibility; the TS frozen proof/replay and normal
retrieval set now passes 72 without changing frozen helpers or outcomes.

The current host still exposes its old catalog. Source implementation and local
stdio evidence cannot close actual-host activation. W1.6.3 remains next after
a fresh session, with W1.8 runtime acceptance, reserved post rows and final
benefit judgment still outstanding. See the delivery report for exact activation
requests, installed ownership and measured limitations.

Final full suite: 2282 passed, seven failed in 202.09 seconds. Six match the
attributed baseline. One additional store-binding subprocess test failed, though
it passed in the first suite and focused run. This leaves a concrete integration
gap. Reuse contract_graph_evidence (Sol/high, original fork none; retained
baseline and storage boundary context) to inspect that exact failure and fixture
ordering, reproduce the cause if possible, and correct only a demonstrated
regression in test setup or owned catalog code. Acceptance: explained failure
and the directly relevant store-boundary check passes under its triggering
conditions; no frozen or unrelated test changes. Return source/error evidence,
changed paths and verification. Primary continues delivery/Brain closeout.

The diagnostic repeat reproduced the seventh failure: MCP binding refuses a
non-empty root without an identity marker. Root identified the new persistent
catalog advisory-lock file as a plausible cause and directed a narrow check of
empty-store eligibility. The same worker may extend ownership to
storage/store_identity.py and its regression tests only if that known harmless
lock artifact is causal; real contents and active/abandoned mutation evidence
must still fail closed. This is an observed new compatibility gap, not another
confidence run. No further expanded suites are requested after the in-flight
prefix isolation finishes.

Final store compatibility disposition: adopted after primary diff review.
The deterministic trigger is a catalog read on an empty root leaving only the
zero-byte .loci-repositories.lock. initialize_store then refused first MCP
binding as unowned populated data. store_identity.py now ignores only the safe
named empty regular lock owned by the current user and without group/other write
permission. Mutation evidence, real contents, symlinks and unsafe/nonempty locks
remain refused. The existing subprocess test forces this trigger and exposes
stderr; additional safe-lock and mutation/data regressions cover the boundary.
Worker result: 40 focused store/catalog checks pass in 2.44 seconds, plus compile
and diff checks. Primary adopted src/loci/storage/store_identity.py and
tests/test_store_isolation.py. No further suite was needed after this directly
reproduced correction; the report retains both 2282-pass/seven-failure pre-fix
suite outcomes and six independently reproduced baseline failures.

Main Brain Steward maintenance is committed and pushed at b0cc51d, with canonical
temporal history validation and passing lint/render. Historical exploration
completion is qualified, normal graph guidance is corrected, and actual-host
activation/adoption remain explicitly open. Unrelated Brain files and the
pre-existing skill frontmatter edit remain outside this delivery's commits.

Manifest mutation applied and read back: all 38 task nodes are marked decomposed,
with 25 of 30 required implementation leaves complete. W1.6.3 is Current with
the explicit fresh-session blocker; all its implementation prerequisites are
complete. The five remaining leaves are real capture/readout reconciliation,
final review, actual-host acceptance, reserved post observations and verdict.
W1.8.2 terminology now follows the frozen retrieve/read normal interface.

## Restarted-host acceptance — 14 September 2026

Vik restarted Codex. The first resumed discovery exposes exactly loci_retrieve
and loci_read. The primary's actual normal request for retrieve_context returned
two source-backed relationships, reported 84 traversals and explicit partial
coverage/omissions. A following actual read returned the full selected function.
These raw host results are being retained and reconciled at W1.6.3; they are
functional host acceptance, not reserved ordinary-task outcomes.

Independent assignments (fresh tree inspected: three worker slots free):

- host_normal_acceptance: Terra/high/fork none. Owned scope: actual fresh
  delegate discovery and one normal retrieve/read functional case, with raw
  receipts only under host-acceptance/delegate/. Contribution W1.8.2: verify
  delegate delivery independently of the primary. Acceptance: exactly normal
  tools, valid exact source and at least one supported relationship if present,
  full raw results emitted to the model and saved with honest provenance. No
  alternate client, product edits, audit post rows or invented graph success.
- normal_delivery_review: Sol/high/fork none. Owned scope: one read-only review
  of the final normal contract, selection/proof/packing, default MCP and adapter
  validation against implemented source and the primary host packet. Contribution
  W1.8.1: identify any required correctness/contract gap. Acceptance: findings
  have a concrete reproducer or source evidence; negative/inconclusive results
  and supported-subset limits are valid. Return a bounded review artifact; no
  broad new experiments, code edits or frozen artifact changes.
- post_protocol_preflight: Terra/high/fork none. Owned scope: read-only inspection
  of the retained ordinary-adoption protocol, post template and existing capture
  route. Contribution W1.8.3 preparation: identify exact reserved rows, prompts,
  roles, models, control/freeze fields and launch/readout procedure needed to run
  only the authorized ten rows. Acceptance: concrete execution recipe and any
  unresolved pre-run field; no launches, edits to frozen evidence or new criteria.

All workers complete directly without spawning agents. Primary owns raw
capture/readout reconciliation, runtime freeze, actual post launch decisions,
Manifest, Brain, commits and final judgment.

The independent reviewer returned one required accounting defect: the new
normal adapter accepts false declared evidence/output bytes as complete and can
mark their full_exact delivery validated. The actual primary packets have exact
declared/observed byte equality (16224 retrieve, 8962 read; 7979 read source).
Reuse normal_delivery_review, Sol/high with retained contract/adapter context,
for the bounded correction in benchmarks/ordinary_adoption_normal.py and its
tests only. Acceptance: recompute full native response bytes and unique selected
source bytes according to the frozen normal contract; missing/mismatched values
remain unknown/mismatch and cannot certify host proof. Correct real packets
must remain valid, including overlapping source spans. Preserve frozen observer,
review and baseline artifacts. Root owns final diff judgment and native capture.

Delegate functional acceptance has both normal tools and valid exact read
source, but zero delivered relationships. Its worker repeated the same pair
once to retain raw packets; all four native calls must remain visible in the
acceptance provenance. This is not a reserved trial or a positive graph-delivery
claim. The original brief requested one pair; the additional pair is retained
as a scope deviation, not removed from accounting.

Primary native readout found a second concrete compatibility gap: the current
anvil_manifest_inquire terminal result at native line 4472 validly omits the
optional isError field; the frozen observer rejects that envelope before it can
account for the normal calls. Do not rewrite the frozen observer or fabricate a
completed primary interval. Reuse post_protocol_preflight (Terra/high, retained
native protocol/source context) for a separate versioned native adapter module
and focused tests. Scope: compose frozen parsing/interval/correlation helpers,
accept only absent optional isError as false for validation, retain the original
captured result shape for byte accounting and model-output correlation. Explicit
invalid flag values still reject. No shared monkeypatch or modified raw rollout.
Acceptance: actual omitted-flag shape parses with exact raw result bytes and
full_exact correlation; legacy valid captures remain equivalent; corruption and
missing boundaries retain their existing limits. Root alone integrates the new
entry point into the normal adapter after both exclusive worker scopes return.

Both accounting corrections are adopted after primary diff/source review.
The integrated normal-v2/native-v2/frozen observer/review checks pass 58/58.
Primary native reconciliation now proves both selected normal calls full_exact,
with current source hashes/spans and exact byte equality. The ongoing primary
turn remains boundary missing; it is not a per-case completed cost sample.

The first delegate's actual four-call trace is retained in delegate-native-check:
the repeated retrieval payloads are ambiguous_exact under the fixed correlator;
only its first preview read is full_exact and its second read is unknown. Thus
the missing required W1.8.2 evidence is uniquely attributable normal delivery in
a fresh delegate. This is an acceptance-instrumentation failure, not a scored
ordinary row. New bounded assignment host_normal_once (Terra/high/fork none),
after inspecting idle capacity, changes the intervention: exactly one fixed
retrieve_context request, immediately store and emit its entire result, then
exactly one returned-item read with the same recording procedure. No reissue for
persistence. Owned scope is host-acceptance/delegate-once only. Acceptance:
actual native retrieve/read results each correlate full_exact; retain any failure
without a trial loop. Primary does native reconciliation; no model task trials
or source changes are included.

host_normal_once returned its two raw records and catalog. Primary independently
reconciled the original native first turn: exactly one retrieve and one read,
both full_exact and byte-accounting validated, with two delivered relationships
and all source hashes/spans matching. Disposition: adopted. The first delegate's
four-call attribution failure stays retained. The source preparation recipe is
adopted with two corrections: these functional packets cannot stand in for
reserved rows23/24, and post freeze names normal-v2/native-v2 after the reviewed
accounting repairs. Ten separate Anvil source copies now match all 638 frozen
hashes; no reserved row has run. The host activation report links final evidence.

Host/accounting delivery is published at 006923b; the separate immutable post
freeze is published at 8ef9b4d (freeze SHA256 00f47b4eafcc7e3bbca6814c78fe0bcaded4e3a2916dbdd6e397043932e2d9dd).
W1.6.3/W1.8.1/W1.8.2 are complete, 28/30 required leaves. W1.8.3 launches only
the reserved eight ordinary delegates and two serial primary checks. Each
delegate assignment is its exact frozen schedule prompt, Terra/high/fork none,
with no source edits or child agents, two concurrent maximum and a 300-second
cap. Owned evidence is each assigned t15–t22 root; root retains native capture,
all failures and the fixed rubric. Before each pair, verify frozen/live inputs
and all 638 source hashes; after each return retain source/access checks and
the observer result. This is the authorized terminal-value measurement.

First pair queued after successful input checks: inspection_15 (checkpoint)
and inspection_16 (binding), Terra/high/fork none. No repeated or substituted
rows are allowed. Check live capacity immediately before launching.

W1.8.3 launch record: inspection_17 and inspection_18, fresh Terra/high/fork none. Exclusive source t17/t18 read-only, exact frozen prompts; required first-turn correctness/capture/cost under 300s and no nudges/replacements. Prior pair completed; capacity available. Parent owns collection and verdict.

W1.8.3 bounded capture/review delegation: post_capture_15_16, Sol/high/fork none. Own new runs/run-15 and runs/run-16 records and a new reusable collector under ordinary-adoption-normal-v1 only; no frozen inputs or shared execution-ledger edits. Acceptance: actual native first intervals, exact prompt/model/capture validation, all commands access reviewed, final facts/source/evidence support reviewed with frozen helpers, all metrics and negative/unknown preserved. Root owns launch/runtime/gates. Two trial workers running, one slot available.

W1.8.3 launch record: inspection_19/20, Terra/high/fork none, exact frozen prompts, exclusive t19/t20 source, read-only. Prior pair completed; capture worker remains useful. Acceptance: first-turn facts/capture/cost under fixed300s, all failures retained.

W1.8.3 launch record: inspection_21/22, Terra/high/fork none, exact frozen prompts and exclusive read-only t21/t22 evidence. Six ordinary attempts completed without intervention. Preserve useful capture worker; two capacity slots available after prior pair completion. Acceptance remains original source/prompt/native/facts/cost criteria and 300s cap; no replacements.

W1.8.3 primary checks23 then24: actual root Astra/ultra, known-answer directed checks on exclusive frozen t23/t24, normal host tools with complete raw output and native proof correlation. Not unprimed delegates or per-case provider cost. All eight ordinary attempts completed; no replacements/timeouts.

W1.8.3 remaining semantic review delegation: post_review_21_22, Sol/high/fork none. Own only runs/run-21 and run-22 review.json, assessment.json and access-review.json after capture. Acceptance: exact frozen required facts, all extra material claims/source references and delivered relationship support; retain incomplete compound facts and uncertain attribution. Both trial turns completed without nudges; two slots available. Root owns primary evidence/aggregate/verdict.

post_capture_15_16 disposition: adopted captures/access/semantic findings at runs/run-15 and run-16. Modified row15 omission-based incorrect to missing; no score change. Row16 supports two answer annotations. Native prompt payload encryption prevents independent plaintext proof; exact parent submissions attested. Collector adopted for17–22; raw intervals local-only, normalized observations/provenance published. Root17–20 judgments:17–19 strict correct;20 omits exit-code propagation and explicit importer leg.

post_review_21_22 disposition: adopted. Row21 all3 facts correct, no full_exact relevant graph annotation. Row22 lacks two compound facts and enumerated sibling-copy AGENTS filenames (no sibling file contents), retained as scope deviation. Both native turns completed under300s. Result locators runs/run-21 and run-22. Primary23 missing expected binding identity proof after3 normal continuations;24 full_exact expected browser proof. Whole-primary observer duplicate turn_context from compaction is preserved; individual original call receipts reuse frozen helpers, not synthetic task intervals.

W1.8.3 final disposition: negative, all10 reserved rows retained. 8/8 ordinary invoked,6/8 full_exact positive,2/4 binding/browser,4/8 supported answer,5/8 strict facts,1/2 primary expected proof,7/8 access condition. Five case/cost medians exceed1.25. W1.8.4 and Objective remain open for unresolved required context/answer/cost acceptance. Report docs/reviews/2026-09-14-normal-graph-adoption-result.md; no new provider batch or runtime change selected.

W1.8.4 follow-through planning, 14 September: Vik asks whether to proceed and what else must be recorded, emphasizing the 2.72x token regression. Bounded retained-evidence assignment token_breakdown: Sol/high/fork none, read-only existing baseline/post binding JSON only. Contribution: distinguish repeated-context/input amplification from raw returned bytes, and establish what the numbers do and do not explain before selecting repair. Acceptance: exact cached/uncached totals, round-trip comparison, no dollar or causal claim without evidence, concise recommendations for recorded work. No new provider trial or source/runtime mutation. Live tree has no active workers; primary owns Manifest planning and user response.

token_breakdown returned exact arithmetic and retained-record locators. Disposition: adopted total2.723634x, cached2.895118x, uncached1.738010x, outputbytes1.281794x and rounds2.090909x; no causal/dollar attribution. Modified recommendation to recover existing per-round native snapshots first, rather than prematurely create future instrumentation; per-round correlation alone is not causal proof. Result locator: .scratch/deterministic-graph-retrieval/follow-through.md. Manifest readback verifies children W1.8.4.1–W1.8.4.4; none marked fully decomposed or implemented. Current next card is W1.8.4.1. Existing Brain orientation (activated, negative acceptance, W1.8.4 open) remains accurate; granular work lives in canonical Manifest.

W1.8.4.1 execution, 14 September: Vik directs completion. Three independent diagnostic scopes can proceed while primary inspects retrieval architecture and owns repair/decomposition decisions. Native token accounting: Sol/high/fork none, read only selected original native intervals and baseline/post observations; own new diagnosis/token-* artifacts only, acceptance per-round cumulative deltas reconcile frozen totals with explicit capture/causal limits. Selection diagnosis: Sol/high/fork none, read-only source/store and deterministic replay of retained t23 queries, own diagnosis/selection-* artifacts only; acceptance identify supported-edge/proof/ranking/budget cause with source evidence and one minimal repair proposal, no product edit/provider trial. Delivery diagnosis: Sol/high/fork none, read-only run17/20/21 native/normalized records and relevant output/correlation contracts; own diagnosis/delivery-* artifacts only, acceptance distinguish product serialization, host output cap, agent repeat and observer attribution with concrete fixes/limits. All complete directly without children, preserve frozen files/source copies and unrelated dirty work. No active workers at launch; primary retains one slot.

W1.8.4.1 primary dispositions: token diagnosis adopted with exact per-round reconciliation and causal limits; proposed new numeric ceilings rejected as unselected. Selection diagnosis adopted, including correction that skipping sibling members alone is insufficient for the options query; stage direct anchor semantics before ownership-driven expansion. Delivery diagnosis adopted: five run21 retrieves are exact, one clipped; original frozen observer underclaims delivery. Frozen scores remain historical. Repair contract: .scratch/deterministic-graph-retrieval/repair-contract.md.

Worker reuse record: selection_diagnosis retains the exact fixture, source/scheduler/proof and counterfactual context; reuse Sol/high for W1.8.4.2 implementation in retrieval.py and relevant retrieval tests only. Acceptance is repair-contract ordering and retained/synthetic regressions within existing budgets. delivery_diagnosis retains raw JSONL/correlation evidence; reuse Sol/high for W1.8.4.3 separate supplementary adapter and new tests/artifacts only. Acceptance is exact retained line matrix and honest duplicate ambiguity, frozen files unchanged. Original briefs remain in thread. Primary owns review, contract, shared docs, Manifest and final host check. Diagnostic workers completed; no capacity conflict.

W1.8.4.2 implementation returned: selection-repair-report.md, replay/red/tests receipts. Primary review adopts the staged scheduler and explicit-pair priority; direct acceptance checks already pass. W1.8.4.3 primary review identified a real attribution gap: equal JSON numbers with different spellings share visible output but candidate hashes differ in the ambiguity key. Same delivery worker reused (Sol/high; original fork none and retained adapter context), scope unchanged, to correct location-based ambiguity and preserve strict whole-block JSON compatibility from the selected contract. Acceptance: minimal numeric-equivalence ambiguity and pretty whole-block regressions plus affected delivery checks. This is required evidence integrity, not a new campaign.

W1.8.4.3 final disposition: modified then adopted. Same worker corrected equality-compatible numeric ambiguity using emitted location identity and retained strict whole-block compatibility. Final 19 delivery tests pass; regenerated retained supplements are byte-identical to their existing hashes. Original source/protocol adapter suite had 61 passing checks. Primary source review found no remaining required defect in the selected repair.

W1.8.4.4 partial verification: nine additional normal acceptance checks pass. One actual-host options retrieval exactly equals frozen pre-repair MCP line5297 (16373 bytes), with all source hashes/spans valid and no binding edge. Receipt diagnosis/repair-host-activation-check.json; full host result retained separately. Stop activation-dependent checks until host restart; no standalone client is substituted. All45 frozen inputs match. Manifest readback verifies W1.8.4.1/.2/.3 complete and W1.8.4.4 restart blocker,32/33 required leaves. Objective remains open for actual-host and ordinary value acceptance; no provider campaign or savings claim.

Main Brain Steward accepted the two read-only correction/repair candidates, preserved and validated full temporal histories (project49->50; entity3->4) and evidence arrays, added a new immutable source and corrected current pages/index/log. Structural lint passed. Previous broad truncation claims are qualified; frozen scores remain historical. No kernel/classification changes; unrelated Brain files remain untouched by this maintenance.

Brain maintenance published at 67583a3 with remote readback, structural lint and render complete. Existing unrelated Brain dirt remains unstaged. Exactly one manual Brain coverage event records actual maintenance closure. Root implementation closeout preserves all unrelated Loci dirt and every frozen input.

15 September W1.8.4.4 resumed after Vik restarted. Normal tools available; first actual request returned PATH_NOT_FOUND because original /tmp/t23 source materialization is gone. Preserve that failure. Bounded source_restoration delegation: Terra/high/fork none; own new repair-host-acceptance-20260915/source-restoration* artifacts and a recreated /tmp/anvil-source-tasks-20260914/t23 only. Terminal contribution: restore exact frozen source so actual-host repair acceptance remains comparable. Acceptance: all638 frozen file hashes/no extras at original canonical root, read-only origin/commit provenance, explicit original archive availability; no provider/Loci calls, frozen edits or changes to an upstream checkout. Live tree only root; capacity available. Primary owns live requests, evidence interpretation and final disposition.

W1.8.4.4 host_receipts assignment: Sol/high/fork none; own new repair-host-acceptance-20260915/capture* and validation* files only. Contribution: validate original native call provenance, complete returned source/proof, wire accounting and model-visible exact output for the repaired live requests. Root performs all Loci calls and owns raw-call-* files; no worker may reissue retrieval or create a provider trial. Acceptance: include the missing-source failure, all selected retrieve/read attempts in current original root interval, exact JSON equality/native line provenance, fixed-source proof/continuation checks, no fabricated completed primary interval or provider-cost claim. Existing frozen helpers may be imported unchanged; any gaps remain explicit. Source-restoration worker is useful and preserved, one more slot used.

source_restoration disposition: adopted, receipt638/638 without extras at original t23 path. Primary live requests now deliver binding options/pair proof and browser/renderer controls; full binding file reconstructs across two pages. New narrow binding comparison is being prepared under W1.8.4.4 to address the remaining explicit token-cost question; scope preference asked asynchronously, default recommendation two fresh attempts, not a full workload rerun. No provider attempts yet. Reuse source_restoration (Terra/high; original fork none, retained exact origin/manifest restoration context) to prepare only t16/t21 and new campaign runtime/source-copies.json; no calls/freezes/trials or upstream/frozen edits. Acceptance all638 hashes/no extra files for both roots. Main owns final campaign selection/freeze, evaluator identity and launch. Existing host_receipts work remains useful and preserved.

W1.8.4.4 narrow comparison selection: primary selects the recommended two-binding default under Vik's instruction to continue; optional scope preference remained unanswered after several minutes of independent live verification/preparation. This is explicit primary scope selection, not a claimed user reply. Unmet requirement is measured ordinary token/correctness after the now-verified repair; original2.7236x evidence links the two binding attempts to that outcome. Preserve unchanged facts and1.25x per-case thresholds; no full-workload claim. Source-restoration reuse adopted at new runtime/source-copies.json with both638/638 roots. New collector composes unchanged normal/native-v2 capture and separate delivery-v3; retained control cost/usage/interval reproduce exactly. Freeze/publish before launch, exactly two fresh Terra/high/fork-none attempts with300s caps and no replacements.

Before freeze or provider launch, Vik explicitly answered the pending scope preference: "Two binding tasks first (recommended)". The two-attempt campaign is now directly user-selected; no full eight-task repeat is authorized by this selection.

host_receipts disposition: adopted after primary source/method review. Native capture and validation reproduce exactly; nine checks pass, seven full_exact successful calls and one retained unproven PATH_NOT_FOUND. Source/proof/byte/paging identity validated. New repair-binding-v1 freeze records Vik's explicit two-task selection, exact original prompts, fixed source, current source/instructions/capture identities and original per-case thresholds before either attempt. Primary will launch two fresh Terra/high/fork-none agents only after scoped freeze publication and readback.
