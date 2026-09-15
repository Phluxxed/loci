# Anvil episode candidate: task-creation evidence in the Manifest view

**Corpus identity.** Evaluate against the retained Anvil snapshot at
`/tmp/anvil-source-tasks-20260914/t21` (638 files; supplied source commit
`53bf29e60cece2335aa39fe301935a07e8e8d4e4`). The snapshot is an exported
tree, not a Git worktree, so it cannot itself supply the historical commits
that the production feature reads. The existing focused tests create temporary
Git repositories for that reason.

## Real user outcome

A reviewer looking at a Manifest task can currently tell its derived creation
phase, but cannot tell whether that label came from a deliberate marker in the
task details, a Git-history inference, or neither. The episode makes that
evidence visible while retaining the crucial boundary that creation metadata is
advisory display information, not graph or execution state.

### Exact prompts, in order

Give these exact prompts to both arms, in separate turns, with no added hint to
use a graph, retrieval feature, named file, or particular tool.

1. **Orientation, read-only**

   > Before I change the Manifest card's task-creation explanation, explain how the view decides that a task was added during Implementation. Identify the inputs, the fallbacks when history is missing or ambiguous, and the boundary between display metadata and graph state. Do not change files.

2. **Bounded useful change**

   > Improve the Manifest task detail so a reviewer can tell whether its creation-phase label came from an explicit task-details marker, committed Git history, or neither. Keep this advisory only: do not change graph JSON, scheduling or availability, completion, or the existing “Added during Implementation” card marker. Add focused tests.

3. **Related follow-up**

   > Extend the same creation-evidence explanation to the HTTP API and the embedded page data, and prove they agree for an explicit marker, a Git-derived task, and an unknown task. Keep the result free of repository paths, commit hashes, and raw Git errors.

## Grounded current behavior and likely change boundary

`deriveTaskCreation` returns only a phase union (`planning`, `implementation`,
or `unknown`) ([`src/manifest/task-creation.ts:7`](/tmp/anvil-source-tasks-20260914/t21/src/manifest/task-creation.ts:7),
[`src/manifest/task-creation.ts:40`](/tmp/anvil-source-tasks-20260914/t21/src/manifest/task-creation.ts:40)). It gives a standalone details marker precedence over history
([`src/manifest/task-creation.ts:47`](/tmp/anvil-source-tasks-20260914/t21/src/manifest/task-creation.ts:47)-[`src/manifest/task-creation.ts:64`](/tmp/anvil-source-tasks-20260914/t21/src/manifest/task-creation.ts:64)); scans only valid
committed objective snapshots ([`src/manifest/task-creation.ts:104`](/tmp/anvil-source-tasks-20260914/t21/src/manifest/task-creation.ts:104)-[`src/manifest/task-creation.ts:151`](/tmp/anvil-source-tasks-20260914/t21/src/manifest/task-creation.ts:151)); and deliberately emits `unknown` when the first Implementation snapshot or malformed history cannot prove an origin
([`src/manifest/task-creation.ts:121`](/tmp/anvil-source-tasks-20260914/t21/src/manifest/task-creation.ts:121)-[`src/manifest/task-creation.ts:140`](/tmp/anvil-source-tasks-20260914/t21/src/manifest/task-creation.ts:140)). Explicit markers exclude fenced examples and turn conflicting markers into `unknown`
([`src/manifest/task-creation.ts:248`](/tmp/anvil-source-tasks-20260914/t21/src/manifest/task-creation.ts:248)-[`src/manifest/task-creation.ts:276`](/tmp/anvil-source-tasks-20260914/t21/src/manifest/task-creation.ts:276)).

The human-view builder currently accepts the phase-only record and combines the
two proven sources in one string, so it cannot answer the reviewer's question
([`src/manifest/view-server.ts:78`](/tmp/anvil-source-tasks-20260914/t21/src/manifest/view-server.ts:78)-[`src/manifest/view-server.ts:82`](/tmp/anvil-source-tasks-20260914/t21/src/manifest/view-server.ts:82),
[`src/manifest/view-server.ts:140`](/tmp/anvil-source-tasks-20260914/t21/src/manifest/view-server.ts:140)-[`src/manifest/view-server.ts:159`](/tmp/anvil-source-tasks-20260914/t21/src/manifest/view-server.ts:159)). It already calls the classifier once in the common view-loading path
([`src/manifest/view-server.ts:287`](/tmp/anvil-source-tasks-20260914/t21/src/manifest/view-server.ts:287)-[`src/manifest/view-server.ts:291`](/tmp/anvil-source-tasks-20260914/t21/src/manifest/view-server.ts:291)). Both the objective API and the page use that path
([`src/manifest/view-server.ts:242`](/tmp/anvil-source-tasks-20260914/t21/src/manifest/view-server.ts:242)-[`src/manifest/view-server.ts:257`](/tmp/anvil-source-tasks-20260914/t21/src/manifest/view-server.ts:257)); the page embeds the same `ManifestHumanView` as `manifest-human-view` JSON
([`src/manifest/view-server.ts:308`](/tmp/anvil-source-tasks-20260914/t21/src/manifest/view-server.ts:308)-[`src/manifest/view-server.ts:321`](/tmp/anvil-source-tasks-20260914/t21/src/manifest/view-server.ts:321)).

The proposed implementation should therefore carry a small per-task advisory
evidence result through this existing seam: phase plus one safe source such as
`task-details`, `git-history`, or `unproven`. It should expose a stable
human-readable `Creation evidence` value in each task node's `data` alongside
the existing `Creation phase`; its precise private type and helper names are
implementation choices. It must not add a field to `ObjectiveGraph`, alter
`Task`, or use provenance to drive derivation. `HumanNode.creationPhase` and
the existing Implementation-added marker remain compatible.

The current tests already establish the important cases: a later committed
Implementation addition is classified as Implementation
([`test/manifest-task-creation.test.ts:89`](/tmp/anvil-source-tasks-20260914/t21/test/manifest-task-creation.test.ts:89)-[`test/manifest-task-creation.test.ts:100`](/tmp/anvil-source-tasks-20260914/t21/test/manifest-task-creation.test.ts:100)); a transition-commit addition remains unknown
([`test/manifest-task-creation.test.ts:102`](/tmp/anvil-source-tasks-20260914/t21/test/manifest-task-creation.test.ts:102)-[`test/manifest-task-creation.test.ts:113`](/tmp/anvil-source-tasks-20260914/t21/test/manifest-task-creation.test.ts:113)); malformed history cannot prove a later origin
([`test/manifest-task-creation.test.ts:153`](/tmp/anvil-source-tasks-20260914/t21/test/manifest-task-creation.test.ts:153)-[`test/manifest-task-creation.test.ts:167`](/tmp/anvil-source-tasks-20260914/t21/test/manifest-task-creation.test.ts:167)); and explicit, recursive, moved markers work even without usable Git history
([`test/manifest-task-creation.test.ts:169`](/tmp/anvil-source-tasks-20260914/t21/test/manifest-task-creation.test.ts:169)-[`test/manifest-task-creation.test.ts:221`](/tmp/anvil-source-tasks-20260914/t21/test/manifest-task-creation.test.ts:221)). The view test already asserts that creation labels leave progress, availability, and edges unchanged
([`test/manifest-view.test.ts:260`](/tmp/anvil-source-tasks-20260914/t21/test/manifest-view.test.ts:260)-[`test/manifest-view.test.ts:280`](/tmp/anvil-source-tasks-20260914/t21/test/manifest-view.test.ts:280)).

## Independent terminal acceptance

An episode is complete only if all of the following are true after step 3.

- The orientation answer correctly describes details-marker precedence, the
  history fallback, the intentionally ambiguous first-Implementation case, and
  that the result does not alter graph execution state. It makes no source or
  product edit.
- Task detail distinguishes all three evidence sources: a valid standalone
  marker reports task-details evidence; a phase proven by valid committed
  history reports Git-history evidence; and absent, unavailable, conflicting,
  malformed, or ambiguous evidence reports unproven. A fenced or quoted marker
  must not be reported as task-details evidence. An explicit valid marker still
  wins over any different history inference.
- Existing phase results remain correct, including recursive tasks and a task
  that is renamed or reparented. A later Implementation addition is still
  marked as added during Implementation. A task added in the transition commit
  and a task after malformed history remain unknown; neither may be silently
  labelled Planning or Implementation.
- The graph schema and serialized objective JSON do not gain creation-evidence
  state. For an unchanged graph, derived progress, current/next/available work,
  completion, blockers, and graph edges are unchanged. The existing
  “Added during Implementation” card marker remains.
- `/api/objectives/<objective-id>` and the page's embedded
  `manifest-human-view` JSON contain the same `Creation phase` and `Creation
  evidence` for fixtures covering task-details, Git-history, and unproven
  cases. The evidence contains only the fixed safe category or explanatory
  text; it contains no absolute repository path, commit hash, command output,
  or raw Git error.
- Focused tests cover the three sources and their negative cases, and the
  relevant TypeScript and test commands pass.

## Relevant checks and setup limits

Run from the Anvil checkout after dependencies are available:

```sh
npm run typecheck
node --test --test-concurrency=1 test/manifest-task-creation.test.ts test/manifest-view.test.ts
```

`npm test` is the repository's broader scripted check (`typecheck` followed by
all `test/*.test.ts` files), defined in
[`package.json:14`](/tmp/anvil-source-tasks-20260914/t21/package.json:14)-[`package.json:18`](/tmp/anvil-source-tasks-20260914/t21/package.json:18).
The snapshot requires Node 22.18 or later and dependencies including TypeScript
([`package.json:6`](/tmp/anvil-source-tasks-20260914/t21/package.json:6)-[`package.json:29`](/tmp/anvil-source-tasks-20260914/t21/package.json:29)). Do not interpret the snapshot's lack of `.git` as a product failure: the focused task-creation tests intentionally make isolated temporary repositories and commits. The view tests start an ephemeral loopback server internally; no external service or provider is needed.

## Why follow-on reuse is plausible

Step 1 establishes the non-obvious contract that explicit details override Git,
unknown is deliberate, and creation provenance is display-only. Step 2 must
trace that contract through `task-creation.ts`, `view-server.ts`, and both test
suites to carry source information without accidentally making it graph state.
Step 3 then reuses the same learned common path: adding a second, ad-hoc API
projection would risk disagreement with the embedded view and repeat the
history analysis. A context that preserves the classifier-to-view-server
relationship should reduce rediscovery and avoid that rework, while the final
acceptance checks remain independent of how either arm found the relationship.
