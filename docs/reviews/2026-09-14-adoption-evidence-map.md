# Prior evidence for the ordinary-adoption audit

W1.2.1, 14 September 2026. This is an evidence reconciliation, not a new
experiment or a rescore. Source baseline at reconciliation: `9499d75`, which
includes the compact reference/call response change `03685a4`. The installed
skill points into this checkout and has an unrelated local edit; later trials
must freeze its actual bytes as well as the engine revision.

The question is whether ordinary agent work discovers and uses useful Loci
relationships, and whether the resulting answers justify the retrieval cost.
The original private Claude test is inaccessible and is not part of the
evidence below.

## What each observation means

| Observation | Evidence required | What it does not establish |
| --- | --- | --- |
| Availability | A particular host/role can discover a callable operation at a known time and revision. | An agent noticed or selected it. |
| Discovery | The task agent received the description or performed the discovery that exposed it. | Invocation or successful delivery. |
| Invocation | An executed request, with arguments and correlated outcome. | A textual mention, loop body, successful result, or useful relationship. |
| Relationship delivery | The returned semantic edges/proof, source, status and omissions; account separately for what the model actually received. | Hidden cognition or a correct answer. |
| Observable answer support | A final answer claim is supported by an identifiable delivered relationship and its exact source evidence. | That the agent internally relied on it, or could not have answered another way. |
| Practical benefit | Correctness/completeness and total workflow cost on comparable tasks, with failures retained. | Benefit inferred from a high graph-call share. |

Dependency, type-dependency and impact exploration can deliver relationships;
so can `get(include_type_context=true)`. `locate`, graph anchors/health,
containment-only neighborhoods and background indexing are separate categories.
Empty, partial, unsupported and failed requests remain visible. Supporting gets
inside a composite request must not become extra agent invocations.

## Retained evidence

| Evidence and conditions | Availability, discovery and invocation | Delivery, answer and cost | Use in this audit |
| --- | --- | --- | --- |
| [Initial fresh-context diagnostic](2026-09-14-graph-adoption-audit.md#fresh-context-observation): Terra/high, no history, ordinary Anvil prompt, 14 September. | 13 shell calls and zero Loci/discovery calls before the answer. A subsequent catalog probe exposed 21 Loci tools. The agent reported assuming unavailability without checking deferred discovery. | The answer was not independently graded. No graph evidence was delivered during the task. | **Reuse:** one concrete discovery failure. The post-task probe is not a pre-task visibility measurement; no failure frequency or engine defect follows. |
| [Retained-history scan](2026-09-14-graph-adoption-audit.md#historical-evidence-and-limits): 208 Codex rollouts, 11–14 September. | 3,683 ordinary retrieval invocation sites, 29 explore sites and 11 type-context gets. Counts are literal sites, not a complete execution ledger. | Two ordinary Anvil investigations retain dependency packets with 7/6/2 relationships and an impact packet with 4. Answer support and savings were not scored. | **Reuse:** nonzero team invocation and delivery. **Exclude:** adoption-rate denominators. The period also spans the [13 September host activation](2026-09-13-shared-runtime-activation.md), so availability was not constant. |
| [Automatic type-context comparison](../../benchmarks/results/typescript-context-existing-v1/README.md), [contract](../../benchmarks/comparisons/typescript-context-existing-v1/README.md): 102 attempts, 17 TS/TSX cases, Luna/high, old candidate source. | B's adapter forced the opt-in on every get. This did not measure voluntary discovery or choice. | All 102 answers correct; B added 24 definition and 35 reference occurrences. Frozen verdict **reject**: maintained calls 16→15, output bytes 72,909→83,988, input tokens 271,370→277,311. B's one full-pass failure began with an oversized outline, not expanded-get overflow. | **Context:** forced expansion can deliver unnecessary/repeated material. Preserve the decision against automatic expansion of every get. No natural-adoption claim. |
| [Routing-v1 interpretation](../../benchmarks/results/typescript-context-routing-v1/interpretation.md), [protocol](../../benchmarks/comparisons/typescript-context-routing-v1/protocol.md): 102 attempts, Luna/high, equal direct tool visibility, B adds routing policy. | Explore in 4/51 A versus 51/51 B attempts. Six of nine maintained B first requests failed null-limit validation; only 3/9 delivered source initially. | All answers passed the scorer; maintained median-call sum 14→6. Frozen qualification **inconclusive** despite cost gains: initial delivery and failed-status accounting were defective. Recoveries and costs remained charged. | **Context:** policy can change selection. **Reuse:** first-call exposure and failed-call accounting lessons. Superseded as current tool-reliability evidence. |
| [Routing-v2 interpretation](../../benchmarks/results/typescript-context-routing-v2/interpretation.md), [protocol](../../benchmarks/comparisons/typescript-context-routing-v2/protocol.md): 102 fresh attempts, Luna/high, `c14b2a8`, extractor 25, same repaired tools, B adds the same 1,155-byte policy. | Explore in 7/51 A versus 50/51 B attempts. All nine maintained B first calls delivered their required source. This is an explicit policy condition with direct tools, not deferred discovery. | Maintained calls 23→10, output bytes 68,076→48,572, input tokens 222,138→118,217; both maintained arms 9/9 full passes. Overall A 51/51 versus B 50/51 correct. Frozen verdict **reject**, 12/14 gates passed: one generic-shadow answer got two booleans wrong despite correct source/proof. Cause is unknown. | **Context:** substantial scoped savings coexist with the failed correctness gate. **Reuse:** protocols and validated exposure/cost definitions. No causal attribution of the error to routing, broad promotion or current adoption claim. |
| [Multilingual measurement](2026-09-13-multilingual-workflow-measurement.md), [protocol](../../benchmarks/comparisons/multilingual-context-workflow-v1/protocol.md): 114 attempts, 19 cases, Luna/high, `4f26681`, extractor 30, graph state 14; B adds exploration and guide. | Controlled agents invoked the exposed workflow. Public-operation/internal-trace mismatch left 63 rows with incomplete graph accounting. | 51 complete measurements, 44 exact answers, 11 full passes. Only the Markdown navigation control passed all workflow gates; no programming-language efficiency recommendation. | **Context:** retain all original scores and limits. **Exclude:** broad efficiency and ordinary-adoption claims; direct-control parity and answer-contract defects cannot be repaired by selectively rescoring old results. |
| [Evaluator repair](2026-09-13-evaluator-contract-repair.md): isolated future v2 observer/control/answer components. | Native public operations reconcile to internal traces through normalized arguments, bytes, spans and unique IDs; subprocess acceptance covered eight graph routes. | Deterministic accounting/control repair, not another provider-agent comparison. | **Reuse:** tested reconciliation and explicit answer-contract lessons where applicable. Nested Code Mode and actual host attribution still require validation. |
| [Canonical integration](2026-09-13-canonical-source-integration.md) and [shared-runtime activation](2026-09-13-shared-runtime-activation.md): real restarted Codex, editable shared Loci source. | Integration alone did not install/restart anything. Activation then exposed 21 tools and exercised actual host calls. | 16 retained responses validated fixture source/proof, bounds, freshness and omissions. No ordinary answer/cost comparison. | **Reuse:** installation/restart and actual-host verification method. **Context:** activation predates the latest compact-record revision and does not prove every still-running host loaded it. |
| Compact reference/call response change `03685a4`: [MCP routes](../../src/loci/mcp_server.py#L407), [page construction](../../src/loci/mcp_record_pages.py). | Current source defaults to compact detail and a 16,384-byte complete-response budget. | Pages preserve continuation; an oversized first record returns an explicit error rather than skipping it. Current-host delivery and ordinary outcome effect still need verification. | **Reuse as source baseline:** do not propose the already-delivered size repair again from an older oversized-packet report. |

The older controlled studies used Codex 0.154.0 and ChatGPT-authenticated
Luna/high runs, with each retained protocol/manifest identifying its source,
tools and scoring rules. Their scores remain scoped to those frozen conditions.
Direct tool exposure in a benchmark is not evidence of discovery through this
host's deferred Code Mode surface.

## Questions that justify new observations

| Gap | Specific unanswered question | Bounded observation and decision use |
| --- | --- | --- |
| G1: delivered surface | What current tool descriptions and installed instructions do the primary and fresh delegates actually receive? | Record source/skill/runtime identity and separate catalog/host probes. Distinguish configuration, reachable catalog and agent-observed descriptions. Select the owner of a demonstrated delivery defect. |
| G2: ordinary discovery and selection | With ordinary task wording, does a fresh delegate discover Loci and choose a useful route? Does a visibility-only diagnostic change that? | Frozen small case block; record discovery and executed requests. Keep ordinary, visibility and task-shaped routing conditions separate. A local failure is actionable; a small sample is not a population rate. |
| G3: graph opportunity | Can the current graph deliver the particular identity/dependency/impact evidence that each task needs, within its bounds? | Independent case truth followed by evaluator-only capability probes. Separate unsupported/partial capability from a selection failure. Accept sufficient non-graph answers. |
| G4: observable answer support and value | Are final claims supported by delivered proof, and how do correctness and total retrieval cost compare? | Score source-grounded claims without a hidden output-format trap; count all retrieval channels and retained failures. Label support, provenance ambiguity and causal uncertainty explicitly. |
| G5: trustworthy accounting | Can actual nested/dynamic Code Mode requests and native outcomes be correlated, including shell fallbacks and omissions? | Choose the smallest observer; validate multiple calls, dynamic dispatch, missing/duplicate/error records and type context before scored collection. Unobservable fields stay unknown. |
| G6: warranted correction | Which observed defect has an owned, usable correction, and does its actual-host delivery improve the frozen task outcome? | Disposition findings, deliver selected changes and run bounded post-change checks. No inherited 102/114-attempt campaign or telemetry platform is required. |

Current product statistics cannot substitute for G5: get/outline events lack
operation/intent and host/session/run attribution, graph/explore has no matching
usage event, and type-context source can appear as ordinary gets
([retained source audit](2026-09-14-graph-adoption-audit.md#why-current-product-stats-cannot-answer-the-question)).
This is a confirmed measurement limit, not yet a mandate to add permanent
product telemetry. Audit capture and a later product measurement decision remain
separate.

W1.2.1 is satisfied by this cited separation and the six named gaps. W1.2.2
selects independent case truth; W1.2.3 chooses accounting; W1.2.4–W1.2.6 pin
conditions, validate the observer and freeze the finite schedule before new
scored outcomes.
