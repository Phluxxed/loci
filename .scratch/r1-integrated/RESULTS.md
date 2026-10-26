# Loci R1: implementation qualified; native pilot blocked

**Recommendation: revise; do not advance to production.** The integrated
experimental interface works and passes deterministic source/proof integrity
qualification. Its bounded fixture consumer has material evidence-delivery losses
and higher acquisition cost. The real Codex comparison could not start a model
session, so there is no agent-level evidence of correct completion or improved
efficiency. This does not reject optional native semantics as a capability.

## Delivered implementation

Branch `experiment/r1-integrated` starts exactly at R0.6 `1fed52dc`. It lives in
`/Users/brummerv/phluxxed/loci/.worktrees/r1-integrated`, under the already-ignored
primary repository worktree directory. Both main checkouts, existing experimental
refs, production source and production entrypoints are preserved.

The [usage document](../../docs/r1-integrated.md) describes the working MCP
interface. `python -m loci.integrated_mcp` uses an explicit experimental
`LOCI_R1_STORE` and exposes:

- `loci_retrieve`: lexical/exact-file source plus bounded path candidates, with
  optional file reanchoring from one delivered identity.
- `loci_read`: the existing exact hash-bound source/semantic extent format and
  continuation semantics.
- `loci_semantic`: explicitly requested, bounded JS/TS/Rust native resolution.
- `loci_proof`: focused evidence for an identity delivered by the latest semantic
  slice or its proof followups, without further native resolution.

`LOCI_R1_SOURCE_ONLY=1` exposes just the first two tools. Source operations load
no parser, graph or semantic store. Source references retain containment,
eligibility, freshness and exact hashes. Native resolution remains demand driven;
its existing single-entry cache is revalidated, while focused proof reuses the
retained native slice. The server serializes operations because MCP dispatches
synchronous tools in worker threads. No planner, routing framework, new graph,
persistent semantic/proof store, global installation or production integration
was added. Python/Go semantic support remains absent.

Path candidates are alternatives from delivered source text, never resolved
relationships. Semantic/proof responses retain complete required supporting
source for emitted claims, native unresolved observation counts/examples,
configuration uncertainty and bounded omissions. Missing output never proves
absence. Proof is never requested automatically by the product interface.

Compatibility limits: experimental source references are opaque but longer than
production handles, and identity reanchoring is one identity at file granularity.
Another semantic request replaces proof eligibility from the previous slice.
Source-only path hints do not implement alias/package binding or macro expansion;
static proof does not establish runtime dispatch, active configuration or
exhaustive reverse impact.

## Deterministic qualification

[qualification.md](qualification.md), [qualification-gate.json](qualification-gate.json)
and [final-independent-replay.txt](final-independent-replay.txt) retain the
combined implementation's results. All 54 directly relevant mechanism,
integration, MCP and native-orchestration tests passed. Twelve integration tests
include actual stdio 4/2 tool catalogs and calls, concurrent operation
serialization, source/control mutation invalidation, source references, native
uncertainty equality and strict negative controls.

The unchanged architectural acquisition/scoring components ran both frozen R0
corpora: 36 cases, source-only and integrated, first/immediate-repeat sequences,
two repetitions with alternating arm order. Independent replay verified all
288 case executions from frozen source archives and retained original packets,
indexes, inventories and traces. Replay also passed after deleting only this
session's ephemeral source exports/stores. Integrity failures and forbidden
proven claims were zero. Python/Go delivered zero semantic claims; source-only
performed zero semantic/proof requests. Unsupported precision in the historical
TypeScript scorer remains qualified by its generic dependency matching.

These are actual combined costs, not sums of historical R0.6 measurements.
Means below cover a complete 36-case acquisition workload per repetition:

| Condition | First sequence | Immediate repeat | Required source spans | Packet/session authored links |
| --- | ---: | ---: | ---: | ---: |
| Source-only | 6.577 s | 6.578 s | 185/187 | 0/84 |
| Integrated | 17.973 s | 12.679 s | 180/187 | 24/84 |

Both acquired entry source in 36/36 cases. Full worker costs including runtime
setup, inventory, first/repeat sequences and artifact writing averaged 14.097 s
source-only and 34.214 s integrated. Full envelopes per first workload were
951,584 versus 1,621,584 bytes. Cache validation/proof freshness and navigation
are charged inside operation/sequence costs. Repeats parsed zero new bytes but
still incurred freshness and packing work. Two first-pass cases were already
cache hits; these are first sequences, not universally cold measurements.
Detailed CPU, process RSS, source/duplicate bytes, cache proxies, operation phases
and store sizes remain in the archived worker records.

The fixture consumer chooses the semantic query from the next path query in
slot two and spends one of five source slots on semantics, even for unsupported
languages. It missed five Python/Go source spans and two Rust Cargo controls;
source-only missed two different Rust spans. Only 24 of 84 authored links were
delivered; 25 of the denominator are unsupported Python/Go links, and supported
JS/TS/Rust misses remain. These are evidence-selection/delivery limits of the
recorded combined policy, not fabricated proof, nor measured final task failure.
The native interface leaves semantic timing/query choice to the agent.

The initial full qualification failure is preserved under `qualification/`:
extra navigation metadata on exact reads violated the strict existing read
schema. The fix removed that extension; no schema/scorer relaxation remained.
All corrections occurred before any native pilot answer or final prospective
freeze. The brief intermediate obsolete-test failure is retained as well.

## Frozen real-Codex pilot and actual blocker

The [final freeze](pilot/frozen-final/freeze.json) identity is
`4c20aff1be5e29ee7400d18c25421c890fcb30f626fd5d322250d208f2e93dfb`.
It pins four independent constructed engineering problems, source snapshots,
identical per-task prompts, independent strict answer/behavior evaluators,
allowed changes, actual MCP catalogs/schemas, model `gpt-6.1-sol` at high effort,
installed Codex 0.164.0/executable, implementation/orchestration hashes, settings,
measurement definitions and a balanced Williams order for all 16 assignments.
Four tasks are exploratory and small; they cannot support population claims.
Oracles passed reference-output and negative dry checks before the final freeze.
An earlier unmeasured freeze is retained with its pre-score supersession record.

The extension is [benchmarks/complete_work/r1.py](../../benchmarks/complete_work/r1.py),
reusing R0.1 snapshot preparation, closed native trace accounting, independent
source restoration and replay. It does not start another model service or use
an API SDK. Installed subscription authentication was verified and locally
pinned to ChatGPT/OpenAI; inherited API-key/base-URL environment overrides are
removed from the child. Native tools and non-Loci services remain available;
Loci is disabled, source-only, integrated or eager by condition-local settings.
Eager runtime source is exported from production reference `ceecb0d2`.

Run workspaces/stores are independent `/private/tmp` copies outside Git
ancestors. This lets the existing startup hook take its normal no-repository
exit instead of indexing a parent worktree. Hooks and global settings are
unchanged; generic ambient Loci guidance remains shared. Preflight catalogs
establish availability, not discovery or use by a model.

The first scheduled native-only assignment failed at `thread/start`, before any
thread ID, rollout, model answer or token telemetry existed:

```
failed to load AGENTS.md instructions for environment local:
fs sandbox helper exit status 71:
sandbox-exec: sandbox_apply: Operation not permitted
```

A bounded Astra review distinguished the parent command sandbox from the child's
frozen native protections. Before one continuation, the original 27 evidence
files/index/status were preserved with verified hashes and relocation mapping.
The prospective [parent launch amendment](pilot/parent-launch-amendment.json)
records a standard auto-reviewed `require_escalated` parent launch, unchanged
child arguments/settings, and the same intended launch mode for all conditions.
That continuation failed at the same helper step, again before thread creation.
No further retry, sandbox investigation, global/native permission modification,
model substitution or alternate billing followed. The initial and continuation
client startup observations were 291.847 and 297.000 ms; neither is time to task
outcome, nor evidence of zero provider usage.

[status.json](pilot/status.json), [comparison.json](pilot/comparison.json), both
attempt archives and their unchanged source snapshots retain the actual state.
There were two launch attempts for one scheduled assignment, zero native model
sessions, and 15 unattempted assignments. No model-discovered/tool-used,
semantic-request, necessary-evidence-missed, repeated-read, context, recovery,
correctness or provider-usage metric can be inferred. Unknown values are null.

| Task | Native Codex | Path-only | Integrated | Eager |
| --- | --- | --- | --- | --- |
| Locate outbound idempotency-key owner | Host start failed twice; outcome unknown | Not attempted | Not attempted | Not attempted |
| Trace inventory input/domain/output contract | Not attempted | Not attempted | Not attempted | Not attempted |
| Resolve registry-handler possibilities and uncertainty | Not attempted | Not attempted | Not attempted | Not attempted |
| Fix shared zero-quantity parser; independent behavior checks | Not attempted | Not attempted | Not attempted | Not attempted |

No condition ranking, aggregate quality score, comparative model cost or agent
superiority claim is justified. Native-pilot deliverables are frozen inputs and
all actual incomplete executions, not a completed four-condition comparison.

## Decision and next step

**Revise / hold advancement.** Preserve the cheap source capability and optional
sound proof interface as this experimental candidate. Do not adopt it based on
fixture source/proof availability. The combined consumer policy needs care:
optional semantics can spend source capacity and return limited useful evidence.
No native answers exist to show that agents choose it effectively or recover
from its omissions. These results do not justify rejecting the semantic family.

The next decision-changing step is to run this same frozen pilot unchanged in
an existing qualified native host once the sandbox-helper startup blocker is
externally resolved. That would answer whether agents discover/request optional
semantics and complete the four tasks correctly, and what acquisition/execution
cost follows. No scored task, prompt, evaluator or candidate tuning is authorized
by this recommendation. This task stops at the evidence-backed recommendation;
production Loci remains unchanged.
