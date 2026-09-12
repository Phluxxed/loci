# Repaired routing qualification: reject

The declared 102-attempt comparison finished on 12 September 2026. All 102
measurements independently replay. The repaired initial-source requirement
passes **9/9 maintained B attempts**, and 12 of the 14 unchanged numerical
gates pass. Qualification is **reject** because one candidate generic-shadow
answer is wrong, failing fixture correctness and per-task success nonregression.

The requested campaign is complete. Delivery acceptance remains open.

## Conditions and preserved evidence

Both arms expose the same repaired fourteen repository tools and three helpers.
A has the original task prompt; B adds the unchanged 1,155-byte routing-policy
prefix. Source is pinned to `c14b2a87a8dde6543c7c790888619bad94711430`, extractor
25. The original seventeen cases, three repetitions, gold, GPT-5.6 Luna high
controls, budgets and numerical evaluator remain fixed.

Qualification code/preparation
[`35ec08f`](https://github.com/Phluxxed/loci/commit/35ec08f26f05ee878be03b6798f16cab1e80335e)
and separate freeze
[`452c07f`](https://github.com/Phluxxed/loci/commit/452c07fe3899369aa60fd20556600d11831ab40e)
were published and validated before the batch began at 07:23:15 UTC. Freeze
SHA-256 is `72db401495d42a7964422ba8bfcf2bf087a8a2b4718112764b3224653eda9691`.
Every scheduled outcome, raw host event, trace, error, recovery and provider
usage record is retained. There were no whole-attempt retries, replacements,
exclusions or post-outcome input/scoring changes.

The [generated report](report.md) and [machine-readable gates](report-summary.json)
retain all fourteen gate results. [Independent replay](replay-verification.json)
verifies all 102 attempts with zero failures and 1,023 artifact fingerprints.
The separate [artifact audit](artifact-audit.md) checks native event ordering,
identity, source joins, accounting and initial source exposure.

## Outcome and maintained-task costs

| Measure | A: available exploration | B: explicit routing |
|---|---:|---:|
| Correct answers and full passes | 51/51 | 50/51 |
| Fixture full passes | 42/42 | 41/42 |
| Maintained full passes | 9/9 | 9/9 |
| Initial maintained source exposure | 0/9 | 9/9 |
| Complete measurements | 51/51 | 51/51 |
| Authored forbidden proven relationships | 0 | 0 |

All three maintained tasks are eligible paired comparators. These are per-task
medians over three repetitions, with all observed calls and costs included:

| Maintained task | Calls A → B | Exact-source recall A → B | Output bytes A → B | Gross input tokens A → B |
|---|---:|---:|---:|---:|
| Temporal arguments | 6 → 1 | 1.0 → 1.0 | 17,409 → 8,179 | 54,472 → 13,526 |
| Retrieval limits | 9 → 5 | 1.0 → 1.0 | 24,469 → 19,258 | 88,095 → 58,462 |
| Renderer result contract | 8 → 4 | 0.8 → 1.0 | 26,198 → 21,135 | 79,571 → 46,229 |
| Sum of task medians | **23 → 10** | — | **68,076 → 48,572** | **222,138 → 118,217** |

The declared maintained-work call reduction is **56.5%**. Summed output medians
fall **28.7%**, and gross input medians fall **46.8%**. Maintained p95 latency is
59.94 seconds for A and 40.54 for B. These benefits do not override the failed
correctness gates.

Across the complete 51-attempt arms, calls total 260/205, tool-output bytes
399,029/363,404 and gross input tokens 2,119,855/1,803,600 (A/B). Cached input,
included in gross input, totals 1,528,832/1,245,696; output tokens total
29,175/28,304. The maintained median reductions are not whole-batch reductions.

## The failed correctness requirement

[`generic_shadow-r1-B`](generic_shadow-r1-B/result.json) correctly answers that
the parameter is a local generic and does not require the imported interface's
fields. It incorrectly returns `false` for both `number_round_trip` and
`string_round_trip`. The frozen gold requires both to be `true`.

The retained [host events](generic_shadow-r1-B/events.json) and
[source trace](generic_shadow-r1-B/adapter-trace-copy.json) contain the relevant
source, including:

```typescript
import type { Payload } from "./types.js";
export function processOrder<Payload>(value: Payload): Payload {
  return value;
}
```

The local generic shadows the imported name, and this function returns its
input unchanged. Exact required-source recall is 1.0. Exploration reports no
proven dependency on the imported `Payload`; zero forbidden relationships and
zero source-integrity violations are recorded. The other two B repetitions and
all three A repetitions answer correctly.

This retained answer therefore fails two gates: candidate fixture full passes
are 41 rather than the required 42, and generic-shadow success regresses from
A 3/3 to B 2/3. The evidence establishes the answer mismatch despite correct
source delivery. The run records no causal explanation for the model's boolean
choices. It does not establish that the routing policy caused the error or
identify a retrieval implementation repair that would guarantee its removal.

## Exposure, recovery and limits

B uses `loci_explore` in 50/51 attempts, with 59 calls; A uses it in 7/51,
with seven calls. All nine maintained B first repository calls select
`type_dependencies` and receive the requested source anchor. All nine exposure
observations are known, with no failures or unknowns. A's maintained exposure is
descriptive and is not an acceptance requirement. Clipped anchor receipt stays
distinct from complete coverage; all maintained B source-recall medians are 1.0.

Initial type-route compliance is B 36/39 and A 0/39. B starts differently on
the three ambiguous-star-export repetitions. All twelve call-target control
attempts per arm satisfy their separate reported route check. These descriptive
results do not add new acceptance requirements after measurement.

Routing remains costly on some fixtures: ambiguous-star-export median calls
are A 9 and B 15. Retained failure events include 21 B pagination tool errors,
one A pagination error and one A invalid-selection call (also recorded as an
invalid-trace event). Their exact payload and recovery costs remain charged.
The frozen full-pass rules permit these recoverable errors; none is excluded
from this comparison. No byte-limit initial-source validation failure remains
in the nine maintained B attempts.

This is one fixed TypeScript/TSX workload and model setting, with three
repetitions per case. It establishes repaired source delivery and measured
maintained-task savings in this trial, alongside a failed correctness
requirement. Authored forbidden-edge checks are bounded by the frozen gold and
scorer; zero detected forbidden links is not an exhaustive unsupported-claim
rate. This trial does not qualify Python, JavaScript, Go or Rust delivery.

Earlier comparisons, freezes and verdicts remain immutable. W2.5.1.3.4
(`task_ea390eab34f135070671da42c06f097d`) remains open because its unchanged
acceptance requirements are unmet; execution and assessment are complete.
W2.5.2 remains prerequisite-blocked. W4 remains required and unstarted. No
further provider experiment, acceptance relaxation, source integration or
shared-runtime promotion follows automatically from this result.
