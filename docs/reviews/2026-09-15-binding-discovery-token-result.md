# Two binding tasks after discovery and named-anchor repair

The selected comparison is negative on cost. Both fresh agents found and invoked
Loci, and both received complete graph context. Only one received the specific
binding type proof. Median input was **479,060 tokens, 1.9216 times the original
baseline**, above the unchanged 1.25 limit and 34.1% above the previous repaired
pair. The two attempts are complete; W1.8.4.4 and the broader ordinary-value
Objective remain open.

## What ran

Vik explicitly selected two fresh binding tasks after restarted-host acceptance.
The separate v2 freeze was published at `375f1c0` before either launch, with
remote readback. Freeze SHA-256:
`81407b613b9b81852d6e6d6454fb64d7c17355df3f45cd0e00d851a08d75a5dc`.
Both original prompts and all 638 source files in each original t16/t21 root
were preserved. The implementation was `44d1074`; installed instructions and
normal-tool contracts were snapshotted. Existing caches were retained and may
have been warm. Original archive bytes were unavailable; individual source
identity was verified.

Exactly two native Terra/high agents ran with no forked conversation, nudges,
replacements or trial retries. Their first turns completed in 79.151 and 99.156
seconds, within the 300-second cap. Native model/effort, provider usage and
interval hashes are captured. The primary attests exact scheduled spawn text;
encrypted child task payloads limit independent plaintext prompt attribution.

## Cost

These are medians of two attempts per condition. Input includes cached tokens;
it is not a billed-dollar measurement.

| Metric | Original baseline | Before repair | Previous repaired pair | New pair |
| --- | ---: | ---: | ---: | ---: |
| Total input tokens | 249,298 | 678,996.5 | 357,203 | **479,060** |
| Cached input tokens | 212,352 | 614,784 | 315,392 | 428,544 |
| Uncached input tokens | 36,946 | 64,212.5 | 41,811 | 50,516 |
| Output tokens | 1,974.5 | 2,542 | 2,069.5 | 2,474 |
| Provider responses | 6.5 | 12.5 | 8 | 12 |
| Outer tool rounds | 5.5 | 11.5 | 7 | 11 |
| Visible output bytes | 122,871.5 | 157,496 | 125,908 | 128,014 |
| Elapsed milliseconds | 73,603 | 110,209.5 | 63,729.5 | 89,153.5 |

The new input ratio fails at 1.9216. Visible bytes pass at 1.0419 and elapsed time
passes at 1.2113. Input is 29.4% below the original 2.7236-times regression, but
34.1% above the previous repaired pair. Each new attempt used 11 outer rounds,
twice the original baseline median. This identifies remaining workflow overhead;
the experiment does not isolate a graph-only cause or estimate population effects.

Individual input totals are 476,062 and 482,058; visible bytes are 144,550 and
111,478. All eight historical/current samples remain in the cost table. The
largest first-attempt shell search produced 197,034 native bytes and 40,157
visible bytes including its truncation notice. Its broad search and subsequent
reads remained part of the measured attempt.

## Graph use and source delivery

Both agents followed the bounded exact-name discovery procedure and invoked
normal Loci tools. Across the pair there were four retrieves, three reads and
18 returned relationship records, including repeated relationships. All seven
responses were fully delivered as exact structured content; two were error
responses. Both attempts received positive graph context. Delivery establishes
availability to the model, not its internal reliance on that evidence.

Both first retrieves used only `captureCommandResult`. Each correctly selected
the function, but spent its bounded packet on an incidental call, a caller and
the return type. Neither initial packet delivered the function's input-options
path. This preserves a concrete limitation of the current selection policy even
though the richer directed activation query passed.

The second attempt later queried `CaptureCommandResultOptions`. Native call 59,
relationship 3 then delivered the complete imported type edge to
`WorkContextBinding`, including the options field, service import, public barrel,
defining declaration and package/TypeScript controls. The expected binding proof
was therefore delivered in **one of two** ordinary attempts. All 45 returned
source records across successful calls matched the fixed file hashes and byte
spans.

Both agents also damaged a long source reference while copying it into a read
request. The first changed a valid 64-character content hash into a different
55-character hash. The second later omitted `0914/t21` from the encoded repository
path. The valid original references were fully delivered. The second agent's
earlier successful read reused its issued reference exactly. These failures
establish a brittle model-to-tool handoff; they do not show invalid issued
references, host clipping or defective rejection of unchanged references.

## Answer review

Both core contract/view answers are source-correct, and both source-access
reviews pass. The strict original facts score 2/3 and 1/3: both answers omit the
named `CaptureCommandResultOptions` clause, and the second does not explicitly
attribute the view's re-export to the public barrel. Neither satisfies every
required clause. The first view citation begins one line before its name in the
correct export block. Extra static/runtime claims are supported for a bare view;
they do not establish a particular caller's runtime value or rule out adaptation.

The primary adopts the independent review against the frozen explicit clauses.
Earlier v1 reviews credited the options clause without its name; those historical
reviews remain unchanged. Individual fact-count differences therefore are not a
calibrated quality trend. These are completeness omissions, not wrong core
answers, and the cost failure is independent of the scoring distinction. Full
judgments and this disposition are retained in `results.json` and the two
`review.json` files.

## Accounting and next action

Before launch, separately versioned delivery-v4 passed 30 focused v3/v4 checks.
It recognises complete nested JSON results with exact original byte spans and
keeps equal native calls ambiguous when they share one emitted value. Duplicate
provenance for one call no longer creates false ambiguity. Retained collector
controls preserve historical provider usage, intervals, costs and outcomes.
No earlier observer, score or frozen artifact was rewritten.

Postflight verifies all 46 v2 frozen inputs, both 638-file source snapshots and
all 45/28 inputs from the earlier normal/v1 freezes. Source-access and answer
qualifications remain in the per-run reviews. The raw native intervals remain
local; normalized observations and provenance are published with the campaign.

**Recommended next on W1.8.4.4:** use these retained failures to make a lookup of
the function alone deliver its required input-type path, and remove the need for
agents to retype long opaque source references. The latter is an interface
robustness proposal, not a claim that locator validation is broken. Verify those
two boundaries locally before selecting any further provider comparison. The
current two-attempt campaign ends here; a new campaign needs its own selection
and pre-outcome freeze. Binding-only evidence cannot close the broader workload.

Evidence: [campaign protocol](../../benchmarks/comparisons/ordinary-adoption-repair-binding-v2/protocol.md),
[cost results](../../benchmarks/comparisons/ordinary-adoption-repair-binding-v2/cost-results.json),
[graph delivery review](../../benchmarks/comparisons/ordinary-adoption-repair-binding-v2/graph-delivery-review.json),
[source-reference attribution](../../benchmarks/comparisons/ordinary-adoption-repair-binding-v2/source-reference-attribution.json),
[postflight](../../benchmarks/comparisons/ordinary-adoption-repair-binding-v2/postflight.json).
