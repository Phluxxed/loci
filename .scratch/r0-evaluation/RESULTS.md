# R0 architectural harness closeout

Implemented on `experiment/r0-evaluation`, based on current repository
`ceecb0d2728c64827d005bd2e2f34d5ca481f86b`. Exact implementation revision:
`5f7429ecd4403acafebbbb66a6815816bb120634`. No production source changes or
integration into master. Both the current main checkout and the session's stale
checkout retain their initial working state and untracked file bytes.

**146 tests pass** (23.93 seconds). The command and exact result/input manifests
are in [validation.json](validation.json). It covers isolated real execution,
independent replay, corruption, capability regression, empty/missing assignments,
failed workers, interruption, cleanup, and existing retrieval/source-reference,
normal acceptance, strict scorers and corrected R0.1 accounting/readback checks.

[Scoped final result](results/scoped-final/result.json) and independent replay
passed at the exact implementation revision above. It declares two frozen cases,
`imported_interface` and `python_alias_annotation`, before execution.

| Condition | Gold source spans | Strict gold links delivered | Store bytes | Index wall time | Retrieval wall time |
| --- | --- | --- | --- | --- | --- |
| Enrichment on | 8/9 | 4/4 | 91,361 | 79.266 ms | 52.485 ms |
| Enrichment off | 2/9 | 0/4 | 91,361 | 76.457 ms | 45.461 ms |

All four condition/suite workers had different store roots, namespaces and IDs.
Each used a separate detached implementation checkout per condition and identical
independently verified exports. Both graph compilation and retained graph costs
were charged. **Off is not graph-free.** The source deficit even with on remains
visible; source delivery does not imply an agent answered correctly. These single
small observations do not establish a stable performance advantage.

[Full result](results/full/result.json) retains all 72 case executions over the
17 TypeScript v3 and 19 multilingual cases. It is **invalid**, not a successful
full-corpus comparison. At the first harness revision
`8b21db82cb5d249336b5d3e9936e0df518b185ea`, the independent strict scorer withheld
five proof-support claims in `anvil_temporal_arguments`, `anvil_retrieval_limits`
and `python_loci_bundle_contract`, matching the unresolved R0 review limitation.
Source bytes, index edges, normal schema and accounting envelopes were intact;
complete semantic support was not independently established. Affected paired
comparisons are unavailable, and no efficiency win is inferred from them. All
conditions still ran, resource costs and raw packets remain, and original
implementation/evaluator bytes are retained. New guards at the final revision
reject empty assignments and preserve process interruption resources; they do
not change retrieval or semantic scoring.

For inspection only, the full-corpus raw scorer counts are on 162/187 versus off
38/187 gold spans and on 70/84 versus off 0/84 gold links. These are partial
per-case evidence counts under the invalid overall comparison, not an accepted
capability or efficiency result. Named-anchor queries and automatic hydration
make this protocol different from R0's gold-seeded one-packet experiment;
historical counts have not been rescored or replaced.

[Negative controls](negative-controls.json) demonstrate deliberate source-fixture
corruption and retained-packet tampering are rejected, and both scoped off
conditions are flagged for evidence regression. Temporary corruption copies were
removed; original retained outputs are unchanged. Relevant pytest controls also
reject missing terminal receipts and empty assignments, preserve incomplete
interruption status, and prove only owned worktrees are removed.

Run/replay the same supported fixture scope from this branch:

```sh
/Users/brummerv/phluxxed/loci/.venv/bin/python -B -m benchmarks.architecture run \
  --control-ref 5f7429ecd4403acafebbbb66a6815816bb120634 \
  --variant-ref 5f7429ecd4403acafebbbb66a6815816bb120634 \
  --case imported_interface --case python_alias_annotation \
  --output /tmp/loci-r0-reproduction
/Users/brummerv/phluxxed/loci/.venv/bin/python -B -m benchmarks.architecture verify \
  --output /tmp/loci-r0-reproduction
```

Replay the retained final record with `verify --output
.scratch/r0-evaluation/results/scoped-final`. Earlier records bind their exact
evaluator sources and should be replayed at their recorded harness revision.
The full record intentionally refuses successful verification because its
comparison status is invalid. Output manifests are externally pinned in
validation.json and this Git result commit.

[Run the next experiment](../../benchmarks/ARCHITECTURE.md) using separate
control/candidate refs and the same enrichment setting for both unless that
switch is being tested. The five reviewed R0 mechanisms informed reuse; only
enrichment was exercised here. Exact-source decoupling and graph-free redesign
remain subsequent experiments.

Level B uses corrected `complete_work.r0` preparation and native rollout readback,
existing `summarize_native`, snapshots and behavioral oracles. No agent harness,
new sandbox, paid inference, global configuration change or model campaign was
created. Native R0.1 qualification passed its bounded controls; a measured task
pilot still needs its own prospective freeze and task/evidence bindings.
