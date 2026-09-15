# Binding measurement after input-path and short-reference repair

The selected two-task comparison is complete. Median input fell 16.0% from
479,060 to **402,423 tokens**, but remains **1.6142 times the original baseline**
and fails the unchanged 1.25 limit. Both agents invoked Loci and received the
required binding graph content. All three short-reference reads succeeded.
The input and elapsed-time gates still fail; strict answer completeness also
remains incomplete.

## Frozen comparison

Vik selected this pair with “Sweet let's do it” after actual-host activation at
`c13f84d`. The new freeze was published and remotely verified at `0a4eb40`,
SHA `116c93f6fa49eef858588a78a134fa3e922003a22b8237db6aaa655da646b3b2`,
before either fresh Terra/high, fork-none attempt. Both exact original prompts
and their t16/t21 source roots were retained. Both first attempts completed
under the 300-second cap, without nudges or replacements.

All 54 frozen inputs and both 638-file snapshots pass postflight. Historical
45/28/46 frozen artifact maps are unchanged. The initial unpublished freeze was
superseded only to remove protocol trailing whitespace; it is retained, and no
trial had started. Existing caches remained; this is not a cold-start comparison.
The unchanged collector passed one retained control before publication.

## Cost

| Measure | Attempt 1 | Attempt 2 | Median | Ratio to original baseline |
| --- | ---: | ---: | ---: | ---: |
| Total input tokens | 394,978 | 409,868 | 402,423 | 1.6142 — fail |
| Cached input | 353,024 | 369,920 | 361,472 | 1.7022 |
| Uncached input | 41,954 | 39,948 | 40,951 | 1.1084 |
| Visible output bytes | 120,611 | 109,843 | 115,227 | 0.9378 — pass |
| Elapsed seconds | 88.657 | 107.892 | 98.275 | 1.3352 — fail |
| Outer rounds | 8 | 10 | 9 | 1.6364 |

The original baseline input median was 249,298; the original regression was
678,996.5 (2.7236 times baseline). The first repaired pair used 357,203 and the
previous pair 479,060. This pair is 40.7% below the original regression, 16.0%
below the previous pair and 12.7% above the first repaired pair.

Outer rounds fell from the previous median of 11 to 9 but remain above the
baseline's 5.5. Loci invocations rose from a previous median of 3.5 to 6.
Most total input is cached; these are provider token counts, not billed dollars.
The repeated context across extra rounds is a relevant remaining cost factor,
but these two samples do not isolate its causal contribution from host guidance,
cache state, latency or retrieval changes.

## Graph use and source continuation

Both agents invoked Loci: nine retrieves and three reads returned 53 relationship
records. Both received the complete options-to-binding proof. One has unique
`full_exact` native-call attribution; the other's complete visible packet matches
two identical native calls, so their frozen `ambiguous_exact` classifications
remain. This proves delivered content, not internal model reliance.

All three reads exactly reused an earlier issued 30-character reference, with
zero read errors. Source validation passes for all 131 returned source records.
Partial coverage and omissions remain explicit.

The frozen delivery-v4 supplement reports eight calls `full_exact`, two
`ambiguous_exact` and two `unproven`. Its two unproven calls returned complete
structured values under `view` and `validator`; the original observer marked
them full. A separate strict JSON comparison validates every packet field in
both nested values against the native results. Both original classifications
are retained. This is an observer coverage qualification, not evidence of clipping.

## Answer quality

Independent Sol/high review found the core accepted-binding and bare-view
distinction correct in both answers. Both support two of the three full original
facts: neither explicitly states the named `CaptureCommandResultOptions`
contract, despite receiving it. The second answer also incorrectly calls the
publicly re-exported `WorkContextBinding` type private. Neither answer passes
all-facts acceptance; source access remains within scope for both.

Earlier frozen reviewers were more generous on the options-name clause, so
individual fact counts are not a calibrated historical quality trend. Runtime
rejection conclusions apply to an unadapted bare view; the source does not prove
what a particular caller supplied or exclude caller-side adaptation.

## Next on W1.8.4.4

The selected measurement has finished with a negative value verdict. The graph
path and short-reference repairs work in these attempts. Remaining traces show
wasted rounds: one agent projected empty `content`, discarded `structuredContent`
and repeated the same request; schema searches also returned related context
before the agents fell back to exact file or shell reads.

Recommended next: decompose a deterministic result-presentation and focused
schema/declaration lookup fix against these retained traces, then verify locally
before selecting another benchmark. This result does not select more product
work or provider trials, and the wider Objective remains open.

Evidence: [results](../../benchmarks/comparisons/ordinary-adoption-repair-binding-v3/results.json),
[costs](../../benchmarks/comparisons/ordinary-adoption-repair-binding-v3/cost-results.json),
[graph and reference review](../../benchmarks/comparisons/ordinary-adoption-repair-binding-v3/graph-delivery-review.json),
[protocol](../../benchmarks/comparisons/ordinary-adoption-repair-binding-v3/protocol.md),
[first review](../../benchmarks/comparisons/ordinary-adoption-repair-binding-v3/runs/binding-repair-v3-01/review.json),
[second review](../../benchmarks/comparisons/ordinary-adoption-repair-binding-v3/runs/binding-repair-v3-02/review.json).
