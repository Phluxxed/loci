# Frozen three-arm comparison: rejected candidates

W2.5.1 completed all **153 serial attempts** under the unchanged v3 controls.
**B/A, C/B and C/A all reject.** C reduces eligible retrieval calls substantially,
but fails the maintained full-pass and serialized-output gates. The first useful
milestone is not accepted by this comparison.

The [declaration and source pins](../../comparisons/typescript-context-three-arm-v1/README.md)
were published before measurement. A is current exact retrieval; B automatically
expands get over existing imported type references; C applies the same get policy
with declaration-owned type dependencies and heritage. **W2.4 `loci_explore`, its
intent selection and compact result packer are not exposed by this frozen schema.**
This batch does not measure that workflow's agent efficiency.

## Result

| Arm | Correct answers | Fixture full passes | Maintained full passes | Complete measurements | Budget-failed runs |
|---|---:|---:|---:|---:|---:|
| A | 51/51 | 42/42 | 9/9 | 51/51 | 0 |
| B | 51/51 | 42/42 | 5/9 | 51/51 | 4 |
| C | 51/51 | 42/42 | 7/9 | 51/51 | 2 |

A full pass requires a correct answer, complete verified measurement and compliance
with the frozen hard budgets. Correct answers after a budget violation remain
failed full passes. There were no correctness retries, replacement blocks,
provider/host outages, timeouts or missing usage measurements.

| Frozen comparison | Eligible maintained tasks | Sum of eligible task median calls | Call reduction | Maintained output-byte ratio | Maintained gross-input ratio | Maintained p95-latency ratio | Verdict |
|---|---:|---:|---:|---:|---:|---:|---|
| B/A | 1 | 8 → 8 | 0% | 0.9856 | 0.8922 | 0.8324 | Reject |
| C/B | 1 | 8 → 4 | 50% | 1.9742 | 0.7565 | 0.8977 | Reject |
| C/A | 2 | 15 → 6 | 60% | 1.9457 | 0.6749 | 0.7472 | Reject |

Call eligibility requires all three repetitions to be full passes in both arms.
Only the renderer task qualifies for B/A and C/B, below the required two tasks.
Temporal arguments and the renderer qualify for C/A, and both save at least one
median call. Output bytes and gross input use sums of task medians across **all
three maintained tasks, including failed runs**; latency uses the frozen nearest-rank
p95 over all nine maintained attempts. These denominators must not be mixed.

C/A passes the 20% call-reduction rule, source-recall non-regression, input-token
and latency gates. It fails 8/9 maintained full passes, per-task full-pass
non-regression, and the no-output-growth gate: **72,049 → 140,186 bytes (+94.57%)**.
C/B also lacks the required two eligible tasks and its output grows 97.42%.
Its one-task saving does not establish incremental new-semantics benefit under
the frozen acceptance rule.

## What the maintained tasks show

| Task | Median calls A/B/C | Full passes A/B/C | Median required-source recall A/B/C | Median output bytes A/B/C |
|---|---|---|---|---|
| Temporal arguments | 7 / 6 / 2 | 3 / 2 / 3 | 1 / 1 / 1 | 16,958 / 15,991 / 11,067 |
| Retrieval limits | 12 / 10 / 6 | 3 / 0 / 1 | 1 / 1 / 1 | 28,521 / 27,377 / 63,202 |
| Renderer result contract | 8 / 8 / 4 | 3 / 3 / 3 | 0.8 / 1 / 1 | 26,570 / 27,640 / 65,917 |

The extra type context is useful in this automatic-get workflow: C reaches the
temporal answer in two calls in every repetition and the renderer answer in four.
The larger retrieval-limits and renderer payloads erase acceptance under the
separate output-size requirement. Fewer turns can reduce cumulative model input
while each delivered result carries more bytes.

Seven budget-rejected calls occurred across six runs: three repository-wide
outlines and four broad grep operations. The common guard withheld oversized
source before delivery. They were not failed type-context expansion calls.
B also made six rejected calls involving an invalid symbol ID or search lineage;
all calls, errors and later recovery work remain charged. The frozen raw failure
list has eleven non-budget validation events because lineage failures carry both
tool-error and invalid-trace records. The individual operations are preserved in
[measurement-limitations.json](measurement-limitations.json).

## Relationship measurement boundary

The unchanged scorer reports the following sums across repeated attempts:

| Arm | Required relationship instances | Available | Delivered | Authored forbidden relationships reported |
|---|---:|---:|---:|---:|
| A | 102 | 15 | 1 | 0 |
| B | 102 | 15 | 1 | 0 |
| C | 102 | 33 | 16 | 0 |

These are **frozen scorer counts, not complete recall of C's added type relations**.
The scorer maps unmatched fixture subtype labels to `references_type`, excluding
`uses_type`, and only extracts delivered edges from neighbor/path responses,
excluding `get.type_context.references`. Consequently all three maintained arms
score 3 available and 0 delivered out of 42 repeated relationship instances.
That is a measurement-coverage limit, not evidence that C's type relationships
are absent. The retained C temporal get explicitly returns four exact,
declaration-owned `uses_type` edges joining the expected endpoints. Exact generic
type dependency does not establish a precise parameter/property/type-query subtype.

The [scorer](../../typescript_context_relationships.py) and the representative raw
[C result](anvil_temporal_arguments-r1-C/result.json) are retained unchanged.
Zero forbidden relationships means zero detected within the authored frozen
checks and scorer coverage; it is not an exhaustive unsupported-claim rate.
No retrospective vocabulary or scoring change was applied to improve the result.

## Accounting and verification

| All 51 attempts per arm | A | B | C |
|---|---:|---:|---:|
| Observed top-level retrieval calls | 284 | 276 | 190 |
| Serialized tool-output bytes | 385,153 | 439,949 | 667,720 |
| Source bytes, including repeated delivery | 86,554 | 77,519 | 107,840 |
| Estimated source tokens | 21,658 | 19,401 | 26,978 |
| Measured gross input tokens | 2,245,727 | 2,206,260 | 1,697,736 |
| Measured cached input tokens | 1,659,904 | 1,624,832 | 1,107,968 |
| Measured output tokens | 28,792 | 28,858 | 24,774 |
| Maintained run-time p95, seconds | 60.42 | 50.29 | 45.14 |

Cached input is a subset of gross input; output includes reasoning tokens. Source
token estimates are not added to provider usage. Indexing time is recorded
separately in the full report. Dollar costs are unavailable under the frozen
ChatGPT accounting contract. V1/v2 causal “avoidable reads” were not collected;
the read gate counts every observed top-level retrieval operation, including
necessary verification, errors, duplicates and helpers.

[Independent verification](artifact-verification.json) passes all 153 identities,
raw trace/source replays, host-output reconciliations, provider usage records,
measurement replays and pinned-engine relationship replays, with zero integrity
failures. Three-engine endpoint preflight and all twelve fresh batch transport
probes pass. Fourteen focused harness checks passed before measurement; the
independent verifier's five focused checks pass after its CLI correction.

The [initial verifier failure](verifier-initial-failure.json) is retained: its
parent parser incorrectly required `--output` for the child worker mode. The
postmeasurement verifier was repaired and rerun. No measured request, raw result,
frozen harness, source engine, corpus, gold, setting or acceptance gate changed.

See the [full report](report.md), [machine-readable gates](report-summary.json),
[raw batch summary](summary.json), [batch manifest](manifest.json), and
[artifact inventory](artifact-inventory.json). This is three source-comprehension
tasks from one maintained repository and does not establish broad coding gains.
The candidates remain isolated; milestone review is next, with no automatic
merge or runtime promotion.
