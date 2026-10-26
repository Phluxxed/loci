# R0.5 demand-driven semantics ablation

Request-scoped use of Loci's native resolvers recovered all seven source spans
missed by R0.4, and all 187 authored spans across the retained 36-case corpus.
It delivered 39/84 strict semantic dependency links, with no invalid complete
proof claims. It performed no semantic preparation during source indexing or
ordinary source access. The architecture deserves further investigation as an
explicit optional semantic capability; this prototype does not establish full
semantic equivalence or production adoption.

The implementation, experiment stores and evidence are isolated in
`experiment/r05-demand-semantics`. Production service, launchers, both main
working trees, R0.3 and R0.4 references are unchanged. No agent/model evaluation
campaign, production merge or Loci V2 implementation occurred.

## Mechanism and fixed policy

Candidate `5fe8f42` starts from R0.4 `2b3b60e`. `DemandSource(GraphFreeSource)`
inherits the unchanged file-hash inventory, search and source reads. Its separate
`semantic_context(original_entry_query)` lazily imports native parsing and
resolution. It scans admitted JS/TS/Rust source and controls, builds a full
**path-only** inventory so omitted filenames cannot manufacture unique module
bindings, and copies admitted source/control bytes into a contained temporary
snapshot. Complete selected-file extraction and native import/reference/call/type
resolution operate on the requested slice. It follows bounded local import and
Rust module/control closure, then native edges forward/reverse to two hops.
It never invokes `service.index_repo`, full `materialize_graph`, or the persistent
semantic store for a demand request.

Source-only work does not import graph/parser modules. Semantic source extents
are narrow, hash-bound, contained and UTF8-aligned. Proof uses full caller/target,
import/reexport/module support and configuration controls. It emits a relationship
only when complete relation-linked support fits 8 KiB unique source and a 16 KiB
MCP envelope; otherwise it omits the claim explicitly while retaining useful
source items. Current source/control inventory is rechecked after analysis.
A one-entry memory cache binds the exact question to a fresh whole-inventory
digest. Changed source, controls, membership or eligibility invalidate reuse.

The [prospective protocol](protocol.md) fixes five acquisition slots, sixteen
continuations, soft 128 KiB source and 256 KiB packet-response admission limits,
and separately charged filename/hash/size inventory. Demand spends its second
slot on the semantic question. R0.4 spends all five on lexical source acquisition;
R0.3 supplies implicit graph context in its five retrieval calls. This interface
and policy difference is part of the comparison. Requests use only original
entry identity and actually observed source/inventory, never evaluator context,
expected relations, missing scores or answers. No implementation or acquisition
policy was tuned after scored misses.

Each case runs first and then immediately repeats the full sequence in the same
worker. Two fresh repetitions alternate arm order. Indexing is fresh per store;
OS caches are not flushed. Repeat cache-hit results characterize an immediate
identical question, not arbitrary interleaving or cross-session persistence.
Native prepared state, source byte copies, file scans, cache validation, imports,
proof packing, child CPU and archival remain charged.

## Targeted investigation and broader gate

The four targeted cases are `anvil_temporal_arguments`,
`anvil_retrieval_limits`, `rust_contained_optional_reexport`, and
`rust_unproven_contracts`. Source/query inputs are the existing authored tasks.
The uncertainty case is not required to invent a positive relationship.
Both targeted pairs completed and independently replayed before broader work.
The predeclared [gate](gate.json) passed: useful missing-source recovery,
nonzero strict proof, and no invalid complete claim. The unchanged candidate and
policy then ran all 36 retained cases.

| Targeted outcomes, first and repeat agree | R0.4 | Demand | R0.3 eager |
| --- | ---: | ---: | ---: |
| Authored source spans | 21/28 | 28/28 | 27/28 |
| Strict delivered semantic links | 0/13 | 7/13 | 9/13 |
| Native candidate matches, not delivered proof | 0/13 | 13/13 | 13/13 |
| All worker elapsed, index + first + repeat + overhead | 4.89 s | 6.87 s | 98.31 s |
| First acquisition operations | 2.20 s | 3.63 s | 45.87 s |
| Repeated acquisition operations | 2.16 s | 2.48 s | 45.91 s |
| Peak worker RSS | 39.5 MB | 95.3 MB | 729.6 MB |

Means of two fresh repetitions; RSS is the mean of per-repetition worker high
water marks. The demand arm was measured in both pairs; its second measurements
and all exact repetitions are retained separately in summary.json.

**Anvil:** all five previously missed spans (`input`, `omission`, `stop`,
`reporting`, `diagnostic`) were acquired. They live in `retrieve.ts`, directly
imported by `render.ts` as `BrainRetrievalResult` / `BrainCompiledEvidence`.
Recovery therefore demonstrates **forward imported-contract discovery**. It
does not establish that reverse-call analysis was necessary to locate them.
The generic question also checks callers, and all actually emitted caller/type
claims receive normal independent proof checks. It is not an exhaustive impact
result. Source recovery, a valid caller edge and an argument that callers were
necessary are different findings.

Demand emitted 3/4 strict links for `anvil_temporal_arguments` and 1/6 for
`anvil_retrieval_limits`; eager emitted 4/4 and 2/6. Native demand records matched
all these authored dependencies, but output/proof budgets and incomplete closure
prevented complete delivery. Anvil queries parsed **7 and 16 files**, respectively,
after scanning **1,908,137 source/control bytes each**. They did not parse the
entire Anvil repository. Relevant incomplete import/reexport closure and omitted
proofs are explicit in each work receipt.

**Rust:** both missing `core/src/lib.rs` spans (module and reexport) were acquired.
The optional workspace case emitted **2/2 strict typed dependency links** to the
canonical declaration, with the public alias/module route and Cargo controls
available as exact support. Configuration stays `declared_possible`; active
features are not proven. This request parsed three Rust files and read the
513-byte source/control fixture. The uncertainty case delivered 1/1 supported
link while leaving ambiguous cfg/name namespaces, private access, macro expansion
and external standard-library relationships unproved. It parsed five files.
No demand packet in these runs emitted a separate structural import/module
relationship. Resolved import/reexport records and support-source availability
must not be relabelled as extra delivered structural links.

## Full deterministic corpus

The source-versus-demand pair completed both repetitions with identical first
and repeat capabilities. All 36 demand cases acquired their entry source and
every authored source span:

| Dimension | R0.4 | Demand | R0.3 eager |
| --- | ---: | ---: | ---: |
| Source spans | 180/187 | 187/187 | 186/187 |
| Cases with every source span | 34/36 | 36/36 | 35/36 |
| Strict session semantic links | 0/84 | 39/84 | 78/84 |
| Invalid demand complete claims | — | 0 | — |

Demand supports JS/TS and Rust semantics in this experiment. Python and Go
remain source-only; their 25 authored positive links receive zero semantic
credit. Native demand records matched all 59 remaining authored relationships
under the existing scorer, but **only 39 were delivered with complete proof**.
The existing TypeScript scorer permits generic dependency credit for some type
categories; these numbers do not establish every precise parameter/property
subtype. Empty graph-free claims earn no positive proof and their zero forbidden
claims are vacuous. Demand made no forbidden proven/delivered claims in the
retained negative cases. Closure, ambiguity and unsupported-language omissions
are retained, not converted to negative facts.

High coverage still has a fixture limitation inherited from R0.4: 32 cases have
snapshots smaller than 1 KiB, often almost entirely delivered. The Anvil snapshot
is about 2.44 MB and the Python Loci case is one file. These observations do not
establish population-wide repository scalability or an agent's task correctness.

## Full resource accounting

Means across two fresh repetitions; one workload contains 31 initial snapshot
indexes and 36 first-use plus36 immediate-repeat acquisition sequences.

| Complete workload | R0.4 source-only | Demand | R0.3 eager |
| --- | ---: | ---: | ---: |
| Initial indexing | 0.98 s | 0.97 s | 5.56 s |
| First-use acquisition operations | 7.71 s | 10.52 s | 67.21 s |
| Immediate repeated acquisition operations | 8.14 s | 8.83 s | 67.02 s |
| First-use operations CPU | 4.50 s | 6.75 s | 64.72 s |
| Repeated operations CPU | 4.59 s | 5.32 s | 64.56 s |
| All worker elapsed, including imports/archival | 17.29 s | 21.17 s | 141.46 s |
| All worker CPU including children | 9.93 s | 13.27 s | 135.76 s |
| Fixture/worktree setup elapsed | 2.33 s | 2.36 s | 2.41 s |
| Workers + setup elapsed | 19.61 s | 23.53 s | 143.87 s |
| Workers + setup CPU | 11.85 s | 15.21 s | 137.70 s |
| Independent observer proof-validation elapsed | 2.73 s | 3.73 s | 15.01 s |
| Independent observer proof-validation CPU | 1.88 s | 2.58 s | 11.00 s |
| Peak worker RSS | 40.1 MB | 97.2 MB | 595.7 MB |
| Worker peak RSS before any question | 36.8 MB | 39.7 MB | 499.1 MB |
| Runtime working store | 36.3 KB | 36.3 KB | 77.71 MB |
| Delivered source per first sequence suite | 336,926 B | 300,157 B | 459,848 B |
| Unique delivered source, summed per case | 247,720 B | 218,214 B | 278,752 B |
| Delivered context including inventory per suite | 944,497 B | 1,057,127 B | 1,951,173 B |

The repeat suite delivers the same bytes/capabilities again; charge both suites
for the measured full workload. Working-cache directories record 0 B; the demand
memory cache is separately accounted below. Demand's 36 semantic operations took
4.24 s first-use versus 2.46 s cached reuse, including fresh inventory validation.
First/repeat source continuation took 1.17/1.19 s for demand and 4.62/4.61 s for
eager. Full phase, case, nested-work and repetition values are in
[summary.json](summary.json), generated directly from immutable results by
[summarize.py](summarize.py). There is no extra retrieval or hidden rescoring.

Demand was measured independently in both pairs. Its second full pair had
20.44 s worker elapsed and 97.0 MB peak RSS, with exactly equal first/repeat
capabilities across pairs. Absolute timing differences are descriptive noise;
no statistical significance or cold-filesystem claim is made.

All worker elapsed includes fresh indexing once per snapshot, first and repeated
acquisition, native preparation, source delivery, cache validation, imports and
archival. CPU includes worker children. Setup and independent observer proof
validation are separately measured, so neither is hidden as product work.
Native phase timings overlap (closure extraction occurs within resolution) and
are attribution only; do not add them to their enclosing operation again.
Peak RSS is process high-water memory, not a separately sampled phase peak or
an aggregate concurrent-process memory sum. MB/KB are decimal.

The source and demand arms retain the same file-only working store; demand does
not persist a semantic graph there. That is **not zero semantic storage/memory**:
its one-entry cache reached a 3,578,764-byte serialized packet/index proxy in this
suite, while actual Python/native memory is included in process RSS. Temporary
source/control copies are counted and removed. Raw sparse observer projections
are intentionally archived as evaluation evidence; retained artifact bytes are
reported separately from runtime store bytes. Across both repetitions and both trial phases, retained
arm-specific artifacts are about 6.56 MB for source-only,12.16 MB for demand,
and20.63 MB for eager in these respective pairs (exact values in summary.json).
Input/evaluator files are shared comparison overhead; source/demand and
eager/demand result directories total20.27 MB and34.33 MB. This evidence archive
is charged storage, but is not runtime cache persistence. The shared dependency installation
and implementation checkout remain common infrastructure, not a claimed package
footprint reduction.

Across one full first-use suite, demand recorded 36 semantic calls, 5,731,725
source/control bytes of discovery, 94 parsed-file executions (1,307,121 parser
input bytes over the native extraction passes), and 441,187 snapshot bytes
written. Initial/final inventory passes and lexical retrieval's freshness scans
are additional work contained in operation CPU/wall time. The immediate repeat
suite has 36 cache hits and **zero semantic discovery/parsing**, while refreshing
the complete inventory on every reuse. Cached repeat work is therefore nonzero.

## Proof validity and historical limitations

The strict TypeScript and multilingual semantic scorers are unchanged. The
R0.4 distinction between relation-linked **packet proof** and acquired **session
proof** remains. Legacy eager claims can omit full caller support from their
own source IDs even when later source pages provide it. Those packet failures
remain failures; a distinct strict session measure may validate actually acquired
same-case support without adding an edge or fetching source during scoring.
Demand avoids that particular overclaim: incomplete packet support means no
complete relationship claim. This stronger upfront emission choice partly
explains its delivery deficit; the deficit is not solely a resolver or
architectural impossibility. Native candidates, source availability and delivered
proof are reported separately.

The narrow [structural observer](../../benchmarks/architecture_structural.py)
independently checks native import-record identity, source/control bytes, module
ancestors, endpoint hashes, incomplete closure and optional/possible configuration.
It supplements the existing scorer, which deliberately excludes structural
imports from semantic link credit. It is tested against valid and corrupted
native Rust import packets, missing controls/module ancestry, forged configuration,
unknown endpoints and capped closure. Demand's actual emitted structural count is
zero, so no structural-proof success is inferred merely from vacuous checks.
Native resolved Rust typed links still require their route and configuration
support through the unchanged multilingual scorer.

**Uncertainty exposure is incomplete.** In the actual `rust_unproven_contracts`
response, the packet reports `scope.coverage=complete`, `exhaustive=false` and
no omissions, while the separately retained native observer records one external
import, four unresolved references (ambiguous target, divergent configuration,
inaccessible target and unresolved import), and two unresolved type-parameter
observations. Those relationships were correctly refused; no corresponding
proof is claimed. Their specific unknown reasons are nevertheless visible only
in audit records, not the normal consumer packet. Treat `complete` as bounded
selection/source coverage, not full semantic uncertainty visibility. This
consumer-facing uncertainty requirement remains incomplete and rules out a
production-readiness conclusion. The independent auditor confirmed the issue;
it was retained as a negative finding rather than repaired after scoring.

Focused checks also cover source-only isolation, stale source and membership,
mutation during semantic resolution, cache invalidation after Cargo optional flag
changes, cross-root/symlink/UTF8 source reads, exact byte accounting, ambiguous
anchors, capped imports, original-query provenance, complete-source corruption,
and all five historical caller-proof missing-support cases. A root Cargo package
represented by `.` needed a touched-crate correction before scored execution;
that failed development check and its fix are recorded in work.md. No valid
negative result was repaired to improve measured coverage.

## Architectural judgment

**Further investigation is justified; production integration is not.** This
experiment demonstrates genuinely deferred semantic preparation and complete
source recovery with materially less work than this eager reference. It retains
trustworthy selected proofs, but delivers only 39/84 semantic links and leaves
whole language families unsupported. Its consumer packet also fails to surface
some important uncertainty reasons retained in native records. It cannot replace
the eager reference's semantic capability or meet the complete uncertainty-facing
contract on current evidence.

Broader work is still necessary in several places: complete path alternatives
and freshness inventory, global text prefiltering for reverse candidates, native
module/configuration discovery and touched Rust crate closure. Reverse aliases
may escape a literal prefilter, so scope remains non-exhaustive. Large reexport
and module closure can expand toward an entire repository; parse/closure caps
must then produce partial evidence rather than a false unique binding. These
costs are measured here. No fixture establishes that a *persistent* repository-
wide semantic graph is logically unavoidable, nor that this prefilter proves
complete reverse impact.

Source targeting improved together with semantic analysis in this ablation.
Anvil's direct import route could also inform a simpler source-only routing
policy; this experiment does not isolate how much source gain *requires*
semantic resolution. The extra independently validated 39 links establish a
separate semantic capability beyond raw source acquisition.

The clearest next question is whether complete proof delivery can recover more
of the already computed native relationships through bounded follow-up, while
preserving the same strict support requirements and accounting. Native resolver
reuse for the unsupported languages is a separate capability gap. Neither is
implemented here. An agent-level comparison would be needed to value agent
navigation choices, interpretation of uncertainty, completed task correctness,
and model/tool-call effort; no such campaign was launched.

This compares specific implementations, not a lower bound on every eager graph.
Much eager latency is full graph/state reconstruction in retrieval; a different
store/loader could change that trade-off. Likewise the frozen second-slot policy
asks for semantics even on source-only questions and unsupported languages; this
is a mechanism ablation, not an optimized decision policy. No broad adoption
claim follows from fixed-fixture resource gains.

## Preservation and reproduction

All four comparisons passed independent replay:32 executions per targeted
pair and288 per full pair, **640 first/repeat case executions total**. The
[replay receipt](replay.json) pins manifests/results and records exact case
inventories, packet/session proof qualifications, cache behavior and cleanup.
All32 worker suites completed. All16 owned execution worktrees and runtime
stores/source exports were removed; implementation/evidence remain retained.
Both main working trees and the prior R0.3/R0.4 worktrees match their recorded
HEAD, staged diff, dirty/untracked inventory and file bytes; see
[preservation-after.json](preservation-after.json).

All retained experiments include input hashes, exact evaluator sources, complete
packets, native sparse projections, work/CPU/RSS receipts, first/repeat traces and
independent manifest pins. Scoring does not require original execution stores
or source roots. Candidate and evaluator implementation bytes match5fe8f42;
full-run metadata correctly records `harness_dirty=true` because tracked work
notes and an additional Cargo cache regression assertion changed after the first
scored run. No product, request-policy or scorer bytes changed after scoring;
archived evaluator hashes replay exactly. There were35 distinct focused checks:
34 passed together, then the added root-Cargo regression and all demand/structural
checks passed; the later Cargo cache assertion also passed in all8 demand tests.

Preliminary inspection qualification: two delegates used normal Loci navigation
before the lead prohibited ambient MCP for experimental inspection; one timed
out and one returned a snapshot, potentially refreshing a derived navigation
index. This cache was never used by a measured run. All subsequent inspection
was direct, and all measured inputs/stores/source snapshots were isolated.

Use the committed experiment worktree to replay after store/worktree cleanup:

```sh
PYTHONPATH=src /Users/brummerv/phluxxed/loci/.venv/bin/python -B -m benchmarks.architecture verify --output .scratch/r05-demand-semantics/results/targeted-source-demand
PYTHONPATH=src /Users/brummerv/phluxxed/loci/.venv/bin/python -B -m benchmarks.architecture verify --output .scratch/r05-demand-semantics/results/targeted-eager-demand
PYTHONPATH=src /Users/brummerv/phluxxed/loci/.venv/bin/python -B -m benchmarks.architecture verify --output .scratch/r05-demand-semantics/results/full-source-demand
PYTHONPATH=src /Users/brummerv/phluxxed/loci/.venv/bin/python -B -m benchmarks.architecture verify --output .scratch/r05-demand-semantics/results/full-eager-demand
python3 .scratch/r05-demand-semantics/summarize.py
```
