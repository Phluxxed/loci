# Exploration tool availability: completed matched trial

The frozen qualification verdict is **reject**. All 102 planned attempts ran
once and independently replayed; all 102 answers are correct. Candidate B
fully passes all 51 attempts, but fails the call-reduction, source-recall and
output-cost gates.

The central interpretation limit is actual use: B selected `loci_explore` in
**3 of 51 attempts**, and **none of its nine maintained-repository attempts**.
The trial measures the effect of making the tool available under the frozen
task instructions. It does not establish the efficiency of using the compact
exploration workflow on those maintained tasks.

## Conditions and verification

- A: the original thirteen exact-retrieval and graph tools.
- B: the same thirteen tools plus the actual, optional `loci_explore` tool.
- Both: the same three source-free helpers, pinned engine `36f5e2b`, extractor
  25, original seventeen task prompts and gold, Luna high through Codex
  0.154.0, three repetitions, numerical gates and run budgets.
- The [v2 freeze](../../comparisons/typescript-context-explore-v2/freeze.json)
  was published at `d84517e` before measured calls. Harness commit `9dfd5f3`;
  freeze SHA-256 `e7936753b97c8e590a1716dee7e288eff6aaaf2b72e2399dcd1fc7e0dc4253c9`.
- All 102 source, host-output, relationship, usage and score records
  independently replay against fresh frozen-engine indexes. The replay
  retains 1,023 artifact fingerprints and reports no failures.
- No whole-attempt retries, replacements, timeouts, missing measurements or
  post-freeze scoring changes occurred.

The [protocol](../../comparisons/typescript-context-explore-v2/protocol.md),
[pre-measurement verification](../../comparisons/typescript-context-explore-v2/validation.md),
[raw-run manifest](manifest.json), [independent replay](replay-verification.json),
[complete generated report](report.md) and [machine-readable scores](report-summary.json)
retain the full method and evidence.

## Frozen result

| Measure | A | B | Acceptance |
| --- | ---: | ---: | --- |
| Correct answers | 51/51 | 51/51 | Preserved |
| Fixture full passes | 42/42 | 42/42 | Pass |
| Maintained full passes | 8/9 | 9/9 | Pass; at least 8/9, no task regression |
| Eligible maintained tasks | 2 | 2 | Pass; at least two |
| Sum of eligible median calls | 15 | 14 | **Fail: 6.67% reduction; at least 20% required** |
| Eligible tasks saving a median call | — | 1 | **Fail: at least two required** |
| Temporal-arguments source recall, median | 1.0 | 0.8 | **Fail: no per-task regression allowed** |
| Sum of all maintained output-byte medians | 69,636 | 78,423 | **Fail: +12.62%; no increase allowed** |
| Sum of all maintained gross-input medians | 250,465 | 215,428 | Pass: −13.99% |
| Maintained p95 runtime | 49.91 s | 50.21 s | Pass: 1.006×; at most 1.25× |
| Authored forbidden relationships detected | 0 | 0 | Pass within the authored checks and proof validation |

The call-reduction denominator contains temporal arguments and renderer
results. Retrieval limits is ineligible because one A repetition hit a hard
budget. Its results and costs remain in the report and in the all-maintained
cost and latency gates. Its median-call change from 11 to 7 cannot be added to
the eligible-call result.

| Maintained task | Full passes A → B | Median calls A → B | Median recall A → B | Output bytes, median A → B |
| --- | --- | --- | --- | --- |
| Temporal arguments | 3/3 → 3/3 | 7 → 6 | 1.0 → 0.8 | 16,697 → 20,882 |
| Retrieval limits | 2/3 → 3/3 | 11 → 7 | 1.0 → 1.0 | 25,577 → 30,950 |
| Renderer results | 3/3 → 3/3 | 8 → 8 | 0.8 → 0.8 | 27,362 → 26,591 |

These are sums of task medians where stated, not totals across all attempts.
Across the entire 102-attempt trial, A/B recorded 276/291 tool calls,
390,957/441,517 output bytes and 2,170,964/2,314,519 gross input tokens.
Cached input is already included in gross input and is not added again to the counts.

## Actual exploration use and causal limits

All three observed exploration calls used `type_dependencies` and returned
status `ok`, four selected items and three relationships, without omissions
or proof-integrity violations:

| Attempt | Output bytes | Source bytes | Required dependency links delivered |
| --- | ---: | ---: | ---: |
| `local_alias_chain-r3-B` | 4,273 | 313 | 3 |
| `imported_alias_chain-r1-B` | 4,454 | 355 | 3 |
| `imported_alias_chain-r2-B` | 4,454 | 355 | 3 |

B delivered ten scored dependency links across all attempts: nine in these
three runs and one through existing graph tools in another imported-alias run.
All required dependency links were available in both arms' frozen indexes.
No maintained attempt delivered a scored relationship proof. Correct answers,
required source coverage and delivered relationship proof are distinct measures.

Every maintained attempt used the existing tools. The temporal recall
regression is the missing complete `TemporalTransition` source span in B
repetitions 1 and 3; both still produced correct answers. Maintained output
growth therefore cannot be attributed to `loci_explore` packing. The data also
does not establish why the model selected the new tool so rarely.

The frozen instructions mention exact retrieval, existing graph tools and
bounded fallback. The added tool exposes its production intent description,
but there is no requirement to choose it. This was declared before measurement.
The next unresolved boundary is agent workflow selection and an explicitly
declared intervention that actually exercises exploration on maintained tasks.
Changing that intervention would require a new pre-measurement declaration;
the completed batch and its gates remain unchanged.

[Interpretation data](interpretation.json) links the actual calls, tool counts,
source gaps and the separate invalid-trial cost disclosure.

## Retained failure and previous invalid trial

`anvil_retrieval_limits-r1-A` began with an unscoped repository outline.
The oversized response was withheld before source delivery; the 412-byte
budget error and subsequent recovery calls remain charged. Its answer is
correct, its accounting is complete, and its outcome remains `budget_exhausted`.

The [first workflow trial](../typescript-context-explore-v1/ABORTED.md) was
aborted for a demonstrated graph-call accounting defect, preserving seventeen
complete result files, one partial attempt and 84 unstarted attempts. All its
code, raw evidence and scores remain unchanged. Its seventeen complete records
report 496,663 gross input tokens (307,456 cached), 7,271 output tokens and
312.35 seconds of process time. The partial attempt's usage and complete outcome
remain unknown; these figures are a known subtotal, not its complete trial cost.
Those invalid outcomes are not pooled with this v2 comparison.

## Delivery status

The experiment is complete; W2.5 delivery acceptance is **still open** because
four frozen gates are unmet. This result neither reverses the rejected
historical three-arm comparison nor qualifies the new workflow conditional on
use. The required Python, JavaScript, Go and Rust work and per-language outcome
qualification in W4 remain unstarted. No new batch, product change, source merge
or shared-runtime promotion is part of this outcome record.
