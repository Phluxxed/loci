# Two binding tasks after the retrieval repair

The selected two-attempt comparison is complete. Median input fell from
678,996.5 to 357,203 tokens, a 47.4% reduction, but remains 1.4328x the original
249,298-token baseline. The unchanged 1.25x input limit still fails. Neither
causal savings from graph code nor full-workload acceptance is established.

## Cost and execution

| Metric, pair median | Original baseline | Before repair | Repaired | Repaired / baseline |
| --- | ---: | ---: | ---: | ---: |
| Provider input tokens | 249,298 | 678,996.5 | 357,203 | 1.4328 |
| Cached input tokens | 212,352 | 614,784 | 315,392 | 1.4852 |
| Uncached input tokens | 36,946 | 64,212.5 | 41,811 | 1.1317 |
| Provider responses | 6.5 | 12.5 | 8 | 1.2308 |
| Outer tool rounds | 5.5 | 11.5 | 7 | 1.2727 |
| Visible output bytes | 122,871.5 | 157,496 | 125,908 | 1.0247 |
| Elapsed seconds | 73.603 | 110.2095 | 63.7295 | 0.8659 |

New individual inputs are 391,408 and 322,998; durations are 71.015 and
56.444 seconds. Both used eight provider responses and seven outer tool rounds.
Visible bytes and elapsed time pass their original 1.25x limits; input does not.
Input includes cached tokens and is not a dollar estimate.

Both agents used the exact original binding prompts, Terra/high with empty
context forks, and isolated copies of the original 638-file source. Both first
turns completed within five minutes. There were no nudges, retries or replacement
attempts. All source files, frozen inputs and installed instruction hashes
remained unchanged. The second attempt made no Loci calls, so the lower pair
cost cannot be attributed to the graph repair.

## What was actually used

Attempt 1 made two normal `loci_retrieve` calls alongside nine shell commands.
Its broad question selected `WorkContextBinding`, `WorkContextBindingView` and
a planning document. The second request selected the whole service file. The
two packets contain nine validated relationships, but neither contains the
specific `CaptureCommandResultOptions -> WorkContextBinding` type edge that
the directed live acceptance check now delivers. Correct engine activation
therefore does not establish successful ordinary anchor selection.

Both result objects were fully present inside the agent's JSON wrappers.
The first enclosing block was truncated after the complete result object.
The frozen delivery-v3 supplement reports both as unproven because it recognizes
whole JSON lines/blocks and does not descend into wrappers. The old observer
credits the second result. A separate post-outcome adjudication strictly parses
both complete nested objects, verifies equality with every native result field,
and records original byte spans. All frozen observer outputs remain unchanged.
The initial commentary that neither result was intact was an undercount and is
corrected here.

Attempt 2 made eleven shell commands and no Loci MCP or CLI call. It read the
Loci skill, then requested full descriptions for tools matching broad terms
including `read` and `search`. The host reported 120,493 tokens before truncating
that discovery output to 40,112 retained bytes. The displayed result contained
neither normal Loci tool name. The subsequent source work used `rg` and `sed`.
This establishes unsuccessful discovery; it does not establish that the Loci
server was unavailable. It also supplies no graph-benefit evidence.

Both answers identify the full binding type and the view's missing fields.
Each scores 2/3 under the unchanged strict rubric: neither explicitly states
that the public barrel also re-exports `WorkContextBindingView`. The source
paths are correct; this is a missing compound-fact clause. Attempt 1's ownership
persistence statement also needs the artefact-backed-path qualification; the
inline path does not persist that ownership. Primary review adopts these
qualifications. Core correctness does not erase the cost or usage failures. The first attempt's final `git status` failed because the isolated
source is an archive without `.git`; that operation remains in its cost.

## Disposition

**W1.8.4.4 remains open.** The repaired engine is active and delivers the expected
proof in directed live checks. This ordinary pair still fails the input ceiling,
only one agent invokes Loci, and neither ordinary request retrieves the expected
binding type edge. The two-attempt measurement ends with this negative result.
No additional provider campaign is selected.

Recorded follow-ups are bounded tool discovery in the host, exact nested-wrapper
delivery accounting in a separately versioned observer, and anchor selection
when a broader question explicitly names a code identity. These are observed
gaps for follow-through, not claims that further graph expansion or larger
response budgets will fix the workflow.

Evidence: [frozen protocol](../../benchmarks/comparisons/ordinary-adoption-repair-binding-v1/protocol.md),
[cost results](../../benchmarks/comparisons/ordinary-adoption-repair-binding-v1/cost-results.json),
[native observations](../../benchmarks/comparisons/ordinary-adoption-repair-binding-v1/execution-ledger.json),
[wrapper adjudication](../../benchmarks/comparisons/ordinary-adoption-repair-binding-v1/nested-wrapper-delivery-adjudication.json),
and [postflight](../../benchmarks/comparisons/ordinary-adoption-repair-binding-v1/postflight.json).
The freeze was published at `dbf1c96` before either attempt. Earlier baseline
observations are linked to their unchanged pre-outcome commit; none were rescored.

Per-attempt semantic reviews: [attempt 1](../../benchmarks/comparisons/ordinary-adoption-repair-binding-v1/runs/binding-repair-01/review.json), [attempt 2](../../benchmarks/comparisons/ordinary-adoption-repair-binding-v1/runs/binding-repair-02/review.json). [Aggregate disposition](../../benchmarks/comparisons/ordinary-adoption-repair-binding-v1/results.json).
