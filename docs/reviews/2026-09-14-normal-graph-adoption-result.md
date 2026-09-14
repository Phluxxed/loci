# Normal graph retrieval: frozen ordinary adoption result

> Subsequent diagnosis: some `unknown_truncated` classifications undercounted
> intact JSON-line delivery. In particular, five of six run21 retrievals were
> intact. See [the separate diagnosis](2026-09-14-normal-graph-repair-diagnosis.md).
> The original computed scores below and frozen evidence are preserved;
> provider-token and answer-completeness failures remain valid.

The graph policy is active and ordinary agents are invoking it. The frozen value
acceptance is **negative**: required-context delivery, complete answers and cost
do not yet meet the agreed bar. **W1.8.3 measurement is complete; W1.8.4 and the
Objective remain open.** Successful activation does not close that outcome.

## Evidence and scope

Implementation `90068fa`, actual-host/accounting acceptance `006923b`, and the
pre-outcome freeze `8ef9b4d` are published. The [freeze](../../benchmarks/comparisons/ordinary-adoption-normal-v1/freeze.json)
has SHA256 `00f47b4eafcc7e3bbca6814c78fe0bcaded4e3a2916dbdd6e397043932e2d9dd`.
[Results](../../benchmarks/comparisons/ordinary-adoption-normal-v1/results.json),
[execution receipts](../../benchmarks/comparisons/ordinary-adoption-normal-v1/execution-ledger.json)
and per-run observation, answer, access and review records retain all ten rows.
The fourteen baseline observations and frozen helpers were not changed.

Eight fresh Terra/high delegates received the exact original task prompts on
separate fixed Anvil source copies, in the reserved pair order. All completed
within 300 seconds. There were no reminders, replacement trials, source edits,
tests or services in the task repositories. Two known-answer primary checks
followed serially. All 638 file identities in every source copy, all returned
source byte extents, frozen inputs and installed runtime hashes passed the final
check. Archive bytes themselves were unavailable, as disclosed before launch.

## What changed in the observed ordinary work

| Measure | Frozen baseline | Post-change | Required post result |
| --- | ---: | ---: | ---: |
| Agents invoking Loci | 4/8 | 8/8 | Recorded, not a separate quota |
| At least one positive complete graph delivery | 2/8 | 6/8 | At least 4/8: pass |
| Binding/browser rows with that delivery | See retained baseline | 2/4 | At least 3/4: fail |
| Answers satisfying every required fact | 6/8 | 5/8 | 8/8: fail |
| Answers with validated relationship-support annotations | See retained baseline | 4/8 | At least 2/8: pass |
| Primary expected relationship proof | Separate historical checks | 1/2 | 2/2: fail |
| Assigned-source access condition | Historical records retained | 7/8 | 8/8: fail |

There were **45 normal retrieval invocations** and 11 exact-source hydrations.
Graph traversal runs inside normal retrieval, so an explicit `graph_*` call
count of zero remains entirely compatible with real graph use. Every successful
normal retrieval runs the maintained policy; neither graph families nor hops
are agent-selected arguments.

`full_exact` means the original native result is uniquely attributable to a
complete model-visible output. It does not establish internal reliance or useful
selection. Rows 15 and 22 received complete graph context that did not support
the final relationship claims. Four answers had supported annotations; two were
renderer answers whose `truncateText` call was also directly readable in source.
This is observable corroboration, not a measured causal benefit.

## Every ordinary row

| Row / case | All facts | Positive full_exact graph | Supported answer | MCP / shell | Visible bytes | Input tokens | Elapsed ms |
| --- | --- | --- | --- | ---: | ---: | ---: | ---: |
| 15 checkpoint | No | Yes | No | 5 / 7 | 238882 | 710491 | 128324 |
| 16 binding | Yes | Yes | Yes | 8 / 9 | 167756 | 924970 | 123569 |
| 17 browser | Yes | Yes | Yes | 5 / 5 | 108658 | 280032 | 75996 |
| 18 renderer | Yes | Yes | Yes | 1 / 4 | 41371 | 116039 | 37528 |
| 19 renderer | Yes | Yes | Yes | 2 / 5 | 71710 | 219373 | 55618 |
| 20 browser | No | No | No | 2 / 9 | 108081 | 371473 | 68872 |
| 21 binding | Yes | No | No | 7 / 7 | 147236 | 433023 | 96850 |
| 22 checkpoint | No | Yes | No | 26 / 5 | 205783 | 941716 | 270548 |

All rows remained below the 60-operation and 400000-visible-byte flags. Those
flags were never used to exclude answers. Full provider usage, including cached
input and output, individual ranges and call records are in results.json.

Strict omissions remain omissions rather than false source assertions: row 15
omits matching next-action projection removal and the atomic current-frame
write; row 20 omits nonzero exit-code propagation and an explicit importer leg;
row 22 omits the projection/write details and both new-clear rejection cases.
Row 17 has two imprecise nearby citations, retained in its review; its underlying
additional source claims are supported. No material false extra source claim
was established by review.

## Cost against each frozen baseline pair

Each entry is the unrounded post median divided by the baseline median; shown
here to three decimals. Every cell must be at most 1.25 for cost acceptance.

| Case | Visible bytes | Provider input tokens | Elapsed time |
| --- | ---: | ---: | ---: |
| Checkpoint | 1.139 | 1.177 | **1.543** |
| Binding | **1.282** | **2.724** | **1.497** |
| Browser | 1.082 | **1.329** | 1.197 |
| Renderer | 0.933 | 0.775 | 0.837 |

The cost gate fails in five case/metric cells. Renderer work improved on all
three measures. This does not support an aggregate efficiency claim. Input
counts include cached tokens and are not a dollar-cost estimate. New source
accounting uses unique extents per operation and is not silently compared with
the baseline's different returned-source sums.

## Concrete remaining gaps

The [primary binding check](../../benchmarks/comparisons/ordinary-adoption-normal-v1/runs/run-23/primary-check.json)
made three retained normal requests: options identity, binding identity, then
both returned anchors. Each delivered valid complete context, but none delivered
the binding identity relationship through the public barrel. The endpoint
sources fit; ownership context and other relationships consumed the selection
budget, with explicit output-budget omissions. This establishes missing delivery
for these requests, not that the underlying graph contains no such relationship
or that budget pressure is the sole cause.

The [browser check](../../benchmarks/comparisons/ordinary-adoption-normal-v1/runs/run-24/primary-check.json)
returned the expected `main → runBrowserCli` call with complete source/import/
re-export proof and uniquely attributable full output. The normal policy can
therefore deliver useful static context on this same source snapshot.

Output delivery also remains a problem. Row 20 repeated an identical result,
leaving both calls `ambiguous_exact`. Row 21's relationship packets were truncated
at the outer output boundary; its exact source hydration was complete. Row 17
retains truncated packets and a malformed source-reference error. The adapter
preserves those failures instead of promoting backend edge counts to delivered
proof. These are measured selection/delivery/workflow gaps, not justification
for asking agents to remember an opt-in graph tool.

W1.8.4 must resolve the required-context selection and complete-delivery gaps,
and establish acceptable correctness/cost, before Objective acceptance. The
frozen measurement ends here with its negative result. Further implementation
must preserve this evidence; this closeout does not select another provider
batch or authorize changing these thresholds. No optional platform, telemetry
store or broader graph feature is needed to publish the result.

## Qualifications and reproducibility

One row violated assigned-source scope: row 22 enumerated sibling task-copy
`AGENTS.md` filenames under their parent directory. It did not read sibling
contents. The row remains in every denominator and cost comparison, with the
condition failure recorded.

The native child NEW_TASK payloads are encrypted. The primary attests exact
frozen spawn submissions in this conversation; independent native plaintext
prompt hashes are unavailable. Models, efforts, native first-turn boundaries,
source identities and operations are retained separately. Opaque shell activity
and silent upstream native logging omissions remain unknown.

Parent compaction produced two turn_context records, so the whole-turn observer
refused primary accounting. The separate primary receipts apply the unchanged
frozen operation/correlation and normal proof/byte helpers to original native
records and line numbers. They do not fabricate a completed primary interval
or per-case provider costs. Raw private intervals remain local only; normalized
observations, provenance hashes and selected result packets are published.

The collector, explicit review replay and result summary scripts live alongside
the comparison. Every review was validated with the frozen structural reviewer,
which checks evidence/quotation identities but does not grade prose. Semantic
judgment belongs to the named reviewer and primary dispositions. Source/runtime
acceptance remains qualified by the prior delivery report: 58 relevant adapter
checks passed; historical full-suite failures were not erased or rerun for this
measurement.

This is a selected eight-attempt source/instruction/runtime intervention. It
cannot establish population adoption, significance, internal cognition, graph-
only causality or Claude behavior in Vik's inaccessible work repository.
