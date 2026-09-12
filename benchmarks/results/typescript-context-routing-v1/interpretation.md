# Explicit routing result — 12 September 2026

The 102-attempt comparison is complete and all 102 measurements independently
replay. Every frozen numerical gate passes. The recorded qualification verdict
is **inconclusive**: the required first-call exposure is established for only
three of nine maintained B attempts. W2.5.1.3 delivery acceptance remains open.

The [generated report](report.md), [machine-readable summary](report-summary.json),
[completion record](completion.json) and [independent replay](replay-verification.json)
are retained unchanged. This interpretation explains their limits; it does not
rescore the batch.

## Measured outcome

Both arms expose the same exploration-capable tools. B alone receives the
published routing instruction. The model selected `loci_explore` in 51/51 B
attempts, including all nine maintained attempts, compared with 4/51 A attempts
and no maintained A attempts. B made 78 exploration calls; A made four.

| Frozen measure | A: available | B: explicit routing | Result |
|---|---:|---:|---|
| Full passes, all attempts | 50/51 | 51/51 | No B regression |
| Full passes, maintained tasks | 8/9 | 9/9 | B exceeds required 8/9 |
| Eligible maintained median calls, summed | 14 | 6 | 57.1% reduction; required 20% |
| Maintained output bytes, sum of task medians | 68,124 | 41,648 | 38.9% reduction |
| Maintained gross input tokens, sum of task medians | 236,264 | 92,074 | 61.0% reduction |
| Maintained p95 elapsed seconds | 58.32 | 34.67 | Ratio 0.595; limit 1.25 |

All answers meet the answer scorer, including A's final renderer-contract
answer. That attempt exceeded the evidence-span budget, so it is correctly
retained as a failed full attempt. Under the frozen eligibility rule, the
renderer task is excluded from the paired call-reduction calculation. The two
eligible tasks have median calls of 7 to 2 and 7 to 4. All three maintained tasks
remain in the recall, output, input and latency gates; the renderer's medians
are 10 and 3 calls. Median required-source recall is 1.0 in both arms for every
maintained task, and B has zero forbidden proven relationships. All 42 B
fixture attempts pass.

The output gate is an aggregate over task medians. Retrieval-limits output
alone increases from 18,745 to 19,189 bytes, while the other two tasks decrease.
The result does not claim an output reduction on every task.

All provider input is charged, including the policy and cached input. Across
the entire 51-attempt arms, gross input totals are 2,358,918 for A and 1,811,245
for B; their included cached-input totals are 1,800,704 and 1,295,872. Output
tokens total 30,045 and 28,533. The maintained percentage above uses the frozen
sum-of-task-medians denominator, rather than these whole-arm totals. These are
token and byte measurements, not a billing-price estimate.

## Why qualification remains open

All nine maintained B attempts first request `type_dependencies`. Six first
calls supply `null` for `max_output_bytes` and `max_evidence_bytes`. The MCP
argument validator requires integers and rejects those calls before source is
returned. Each of the six attempts later corrects the arguments and receives
the requested source anchor. Those recoveries are useful measured behavior,
but the published exposure rule explicitly requires delivery on the first
repository retrieval. A later call cannot repair that gate.

The six affected attempts are all three `anvil_temporal_arguments` repetitions,
`anvil_retrieval_limits` repetitions 1 and 3, and
`anvil_renderer_result_contract` repetition 2. For a concrete retained example,
see [temporal arguments B1 host events](anvil_temporal_arguments-r1-B/events.json):
its first tool call fails integer validation and its next exploration call
returns the requested anchor. The three successful first deliveries are
retrieval-limits B2 and renderer-contract B1/B3.

There is also a frozen observer limitation. The host emits `item.completed`
with tool `status: failed` for these validation errors. The observer expects
`status: completed` on that event type, records `invalid_tool_status`, and
labels the exposure unknown. This affects 15 B attempts: nine fixtures and
six maintained attempts. The raw events show actual first-delivery failures;
they are not missing provider measurements. The generated verdict remains
**inconclusive**, with three exposure passes and six unknowns, exactly as
produced by the frozen observer. No result is rewritten into a pass or a new
verdict.

The 15 host validation failures are included in observed tool-call and cost
accounting, even though they occur before the adapter runs. Other retained
errors include pagination errors, two A search-lineage failures and the A
renderer evidence-span exhaustion. All subsequent in-attempt recoveries remain
part of their original attempts; no scheduled attempt was replaced or retried.

## Evidence and next boundary

Code `182accfca24e3401a2546e656f8758e6e4ae86ae` and the separate published
freeze `3cde32ec8534e56ea7846028b154597e1ebd5749` preceded provider execution.
The [freeze](../../comparisons/typescript-context-routing-v1/freeze.json) has
SHA-256 `20f8b2530dd91e7f9d06d7ba8498e0d6bfe44de304dc17feef801ca3ac5e91b7`.
Source, corpus, gold, settings, schedule and thresholds stayed fixed. The
earlier rejected comparisons remain separate and unchanged.

The [additional artifact audit](artifact-audit.json) checks raw lifecycle order,
identities, retained copies and first-call/source evidence. The frozen observer
orders by terminal events; the audit checks whether that agrees with actual
start order in this batch. Independent replay verifies all 102 retained
attempts and reports zero failures.

This establishes a measured benefit from the routing intervention in this
frozen TypeScript/TSX workload, including its recoveries. Reliable initial
delivery is still unmet. These three maintained tasks and one model/reasoning
setting do not establish multilingual or general deployment performance.

Next remains **W2.5.1.3 — Run and qualify the matched exploration workflow
comparison** (`task_2727497172e9ceadea5ab07538da0b31`): resolve the nullable-limit
call failures and the observer's failed-status classification before deciding
on a separately versioned qualification step. This completed batch remains
immutable; no automatic follow-up experiment is authorized by its outcome.
Manifest progress remains 32/45. W2.5 acceptance stays open, multilingual W4 is
required and unstarted, and the shared runtime has not been promoted.
