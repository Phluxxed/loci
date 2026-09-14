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
