# Architectural comparisons

Level A uses one entry point, with no model calls:

```sh
python -m benchmarks.architecture run --output /tmp/loci-enrichment-r1
python -m benchmarks.architecture verify --output /tmp/loci-enrichment-r1
```

Run with the repository's prepared Python interpreter. The default compares
normal graph enrichment on/off against the same committed HEAD, on both frozen
TypeScript v3 (17 cases) and multilingual v1 (19 cases) corpora. These are new
measurements against old authored fixtures, not rescoring of historical campaigns.

For the next architecture experiment, commit the candidate on a local branch
and supply its revision; keep both enrichment settings on unless that switch
is the mechanism under study:

```sh
python -m benchmarks.architecture run \
  --control-ref CONTROL_COMMIT --variant-ref CANDIDATE_COMMIT \
  --control-enrichment on --variant-enrichment on \
  --output /tmp/loci-next-experiment
```

Both revisions must preserve the existing `service.index_repo`, `retrieve`,
`read`, store binding, and retained index/evidence contracts used by the
independent scorers. Indexing, graph construction, retrieval, selection, storage
and context assembly may change behind those contracts. This is a fixed runner,
not a plugin interface. No architectural candidate is bundled with the harness.
A changed evidence format needs an explicit independent scorer adaptation;
unknown schemas must not be scored as successful empty output.

Use `--corpus PATH` repeatedly to select a supported frozen corpus.
Use repeated `--case CASE_ID` to declare a narrower fixture scope before
execution; the selected IDs and full input identities remain in the record. All
snapshots, archive inventories and authored spans are independently verified.
`--repetitions N` creates fresh conditions and alternates their execution order.
There are no inference calls, resource ceilings, acceptance thresholds or
quality/cost composite scores. One repetition demonstrates operation; it does
not establish a timing advantage. Corpus anchor names define fixed queries;
source-only anchors use their authored file. Every incomplete selected item is
hydrated to completion. There is no gold-guided search or task-answer inference.

The primary repository must already ignore `/.worktrees/` (verify with
`git check-ignore .worktrees/probe`). The runner refuses to edit its ignore
rules. Use an external output directory or the implementation worktree; it
rejects output paths in the primary working tree. Existing outputs cannot be
overwritten. It creates detached implementation worktrees under the primary
`.worktrees/`, ordinary source exports, and a separate process, store identity,
namespace, temporary directory and cache for each condition and suite.

Loci canonicalizes a Git worktree root back to its primary repository.
Therefore the indexed fixtures are ordinary exported directories, **not** the
implementation worktrees. Each worker explicitly initializes and activates its
own store binding, checks actual candidate import paths, checks fixture canonical
identity and retains the catalog. The controller independently checks binding
uniqueness, request inventories, and exact fixture files before and after use.
This isolates trusted local variants; it is not a security sandbox for hostile
code. Global Codex configuration and native protections are untouched.

`result.json` retains paired capability dimensions and phase measurements.
`artifacts/` retains full production accounting envelopes, indexes, worker
receipts, errors, dependency identities and process logs. `inputs/` retains
verified frozen inputs, `evaluator/` the actual independent evaluator sources,
and `manifest.json` binds every retained file by SHA-256. Keep the manifest hash
outside the result directory when an externally pinned integrity receipt is
needed. `verify` checks exact artifact inventories/hashes and replays capability
scoring against newly exported fixtures, without the original worktrees/stores.
It requires the same evaluator source bytes; use the recorded implementation
revision for later replay. Candidate commits and harness revision are recorded;
uncommitted evaluator bytes are retained explicitly, not silently called HEAD.

Capability reports anchor selection, gold span coverage, authored semantic
relationships available and delivered, complete linked proof, and forbidden
relationships. TypeScript's historical scorer allows a generic dependency-link
fallback; its precision qualification remains in each score. Structural imports
are validated as normal packet proofs and index edges, separately from the
semantic scorer. Source delivery does not establish an agent's final answer;
`task_answer_correct` remains unknown at Level A. Lower capability remains a
valid negative ablation result, explicitly identified per case. Corrupted input,
malformed output or false proof invalidates the comparison. Failed or interrupted
workers retain partial receipts and cannot become successful measurements.

Efficiency retains setup, runtime import/binding, full indexing, retrieval and
source continuation elapsed time and CPU, faults/I/O counters, process peak RSS,
store/cache bytes, indexing work, retrieval usage, output and repeated source
bytes. Process wall time and child CPU include startup and archival overhead;
phase timings cover their named operations only. RSS is the process lifetime
high-water mark, not a separately sampled phase peak. Native libraries run in the
worker's CPU accounting. Dependencies are shared read-only through the selected
interpreter; OS filesystem caches are not flushed or claimed cold. Failed work
still has resource receipts; missing resources remain absent, not synthetic zero.

**Graph-enrichment off is not graph-free.** Both default conditions compile,
validate, load and store the full graph. Off skips enrichment during retrieval.
Index and store costs stay charged, including graph work. The report's
`graph_free: false` concerns this switch; a different revision's architecture
must be established from its implementation and measured indexing work.

Only this invocation's implementation worktrees, source exports, stores, caches
and process groups are removed. Raw experiment evidence remains. No global
worktree pruning or ambient store/process cleanup occurs. Primary dirty and
untracked file identities and staged diff are checked before and after.

Level B reuses the corrected native [R0.1 path](complete_work/r0.py), documented
in [native qualification](../docs/reviews/2026-10-22-r0-1-native-qualification.md).
`python -m benchmarks.complete_work.r0 prepare` makes independent source copies;
`qualify` archives/readbacks an existing closed native thread. Existing
`accounting.summarize_native`, source snapshots/restoration, evidence join and
behavioral oracles supply accounting and grading. Execution and continuation use
the current native host with its protections unchanged, fresh `fork_turns:none`
threads and explicit model/effort. The historical custom-profile controller is
not a prerequisite for this corrected path. No second agent runner, sandbox,
global configuration changes or live/paid campaign is added by Level A.

R0.1 verified native execution, completed usage, continuation, failure and
interruption capture on qualification fixtures. A measured task pilot still
needs a prospective input/schedule freeze and its task/oracle/reviewer bindings.
Missing or interrupted telemetry remains unknown/lower-bound; the native catalog
is shared, so native-only policy is checked from observed calls, not asserted as
an OS prohibition. See `r0.py --help` and the qualification report before using it.

The [R0 review](../docs/reviews/2026-10-22-loci-r0-architecture.md) tested enrichment,
representative member expansion, selection precedence, repeated validation and
backend parse reuse. This harness generalizes the retained disposable corpus
runner into separate revision/process/store comparisons, adds full fresh-service
and continuation accounting and independent replay, and reuses its frozen
loaders, span coverage and exploration-shaped semantic scorer adapter. Existing
R0 drivers and all historical data remain unchanged. For the other four ablations,
commit the bounded implementation change in its own worktree and pass its ref;
the runner neither installs nor integrates it. Exact-source decoupling and a
graph-free redesign are subsequent experiments, not part of this implementation.

R0 documents five normal-call proof-support discrepancies under the older strict
semantic scorer. They receive no complete-proof credit here. Per-case raw
source/output/schema corruption and independent proof failures remain explicit;
an affected run/overall full comparison is `invalid`, with all attempted conditions
and measured failed work retained. An unavailable comparison is never reported
as an efficiency win. For an explicitly selected valid end-to-end control:

```sh
python -m benchmarks.architecture run \
  --case imported_interface --case python_alias_annotation \
  --output /tmp/loci-enrichment-valid
python -m benchmarks.architecture verify --output /tmp/loci-enrichment-valid
```

This narrower fixture comparison can establish harness operation without claiming all corpus guarantees passed.
The full-corpus result must be reported alongside it.
