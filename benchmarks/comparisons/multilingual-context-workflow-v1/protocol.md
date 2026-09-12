# Multilingual workflow measurement v1

W4.7 (`task_ecbfc0ce724b713f2599830d21438a46`) measures the implemented language
slices under one predeclared comparison. This protocol is preparation until its
code, controls, schemas, prompts, scorer proof and schedule are separately frozen
and published. Provider outcomes start only after that freeze validates.

## Question and intervention

Does the recommended compact-context workflow help an agent answer the pinned
source-comprehension tasks, with correct source and relationships, within the
same task budgets as exact retrieval?

- **A, exact retrieval:** existing search, exact get, outline, graph diagnostics
  and bounded file/grep tools; get does not expand type context automatically.
- **B, compact workflow:** identical shared tools plus the actual `loci_explore`
  implementation and a short intent-selection guide. Both see the same ordinary
  task prompt. The guide contains no case IDs, gold, expected source or outcomes.
- Both use the same final implementation and fresh index. This compares a tool
  and guidance package; it does not isolate the causal effect of one component.
  B's additional schema/guidance bytes and all fallback reads count toward cost.

The baseline engine is W4.6 source `4f2668160df59bfb114a28a2069f9a0198da469b`,
extractor 30, graph state 14. Freeze the actual final engine tree and configuration
after deterministic scorer/transport checks; any required pre-outcome correction
must be identified in that freeze. Shared installation and runtime promotion are
outside this comparison.

## Cases and schedule

Retain `multilingual-context-v1` corpus/source hashes, exact prompts, independent
JSON answer facts, required byte intervals, positive relation meanings and
forbidden target claims. An evaluator-only input view may add comparison controls
beside byte-identical corpus files; it may not alter their contents or identity.
Task agents receive only a materialized source snapshot and ordinary task prompt.
Gold, case IDs, group labels, saved outcomes and scorer code remain outside their
tool and filesystem capability.

Run **114 serial attempts**: 19 cases × 3 repetitions × 2 arms. Use corpus order,
repetitions 1–3, alternating AB/BA pair order beginning with AB. Every attempt has
a fresh isolated Codex session, source directory and index. Python has five cases
(four synthetic and one maintained single-module task), JavaScript/Go/Rust four
each, TypeScript one TSX control, and Markdown one navigation control. Report
these origins separately. The single TSX control does not establish broad
TypeScript usefulness; Markdown is not a fifth programming-language success.

The old seventeen-case TypeScript corpus remains an immutable deterministic
control. Do not rerun its historical provider batch, pool old outcomes with this
comparison, or change W2.5 verdicts.

There are no correctness retries, selective replacements, dropped failures or
extensions to obtain a pass. A resume may continue only an exact fully recorded
prefix. Preserve an interrupted attempt and classify missing evidence explicitly;
do not rerun it under the same attempt identity. A provider/setup failure is an
outcome to retain, not permission to choose a new model or batch version.

## Model, host and budget controls

Retain the previous comparison's **GPT-5.6 Luna / high reasoning / default service
tier / ChatGPT-authenticated local Codex** route if current host/catalog checks
verify it. Record the exact installed CLI, environment/packages, model catalog,
effective request, disabled capabilities and authentication mode before freezing.
Catalog availability and login state are not guarantees that a provider request
will succeed; any provider refusal remains a failed measured attempt. The backend
model snapshot is not exposed and is not claimed to be pinned.

The host rejects overrides to its built-in OpenAI provider. Preserve that
preparation failure, pin the actual CLI binary, and leave built-in transport
recovery unchanged in both arms. No scheduled attempt, correctness failure or
provider failure is retried by the runner. The CLI may recover an HTTP request
or stream within an attempt; this is not a replacement attempt. Retain actual
CLI events, exact MCP payloads and provider-reported usage. Local loopback
evidence proves effective request serialization. Production HTTP bodies and
unreported provider work are not captured or claimed. A custom authentication
route is outside this comparison. The no-auth local inspection provider alone
uses explicit zero request and stream retries.

Use isolated runtime configuration, no ambient project/Brain/skill instructions,
no native delegation or goals, no shell/repository execution, and no web or
unrelated connectors. Inspect actual requests against the frozen prompt and
schema hashes. The tool surface and filesystem boundary must keep evaluator
inputs inaccessible. Authentication secrets are neither copied into artifacts
nor printed. Official [Codex configuration documentation](https://learn.chatgpt.com/docs/config-file/config-reference)
describes reasoning, service-tier and transport-retry controls; actual local
catalog and request evidence establish the effective settings for this run.

Preserve the W4.1 budgets: exploration 8,192 source-evidence / 16,384 complete
output bytes; any retrieval operation 16,384 source / 32,768 complete output
bytes and 64 spans; whole task 131,072 source / 262,144 output bytes, 24 observed
tool calls and 180 seconds. Operations have a 10-second bound. Exploration uses
at most five anchors, three requested hops, 64 examined nodes, 12 selected items
and 32 neighbors per node. Existing one-hop graph-tool neighbor limits remain
explicit in its effective schema. Zero/reduced budgets retain truthful omissions.
Preserve the prior accounting guards of 200,000 reported input and 8,192 reported
output tokens per task; these are separate from byte limits and source estimates.

All model-visible tool content and framing counts, including errors, resource
helpers, correlation metadata, policy input and recovery/fallback calls. Source
cost counts repeated delivery repeatedly; required-source recall uses unique
exact original-file intervals. Product evidence-union and native-output usage
remain separate from total observed payload cost. Report gross input, cached
input as its subset, output including reasoning, and wall latency separately.
No dollar or subscription-credit deduction is inferred from token usage.

## Scorer proof before outcomes

Use the existing source/answer/observed-delivery machinery with a bounded new
language adapter. Pin its exact semantic mapping for all corpus relation kinds;
unsupported mappings must fail preparation rather than silently earn no credit.
Keep original edge direction, language meaning and certainty. An authored type
edge is not runtime dispatch, and generic endpoint dependency is not a more
specific claim unless the delivered source and record establish that meaning.

Actual `loci_explore` packets must pass source/hash/interval and persisted-edge
proof verification. Deterministic checks must include each language's positive
output, a same-name wrong origin, missing proof source, and budget-limited output.
An ID, path or metadata label alone earns no source credit. Negative-case source
still has to be read even when no positive relationship is allowed.

Run the existing real Codex/MCP loopback transport with no provider model to
verify both arms, actual shared schemas, effective prompts/controls, source
delivery into the next request, strict null/default/error behavior and observed
accounting. Publish that evidence and code, then publish a separate freeze with
all input/configuration/source/scorer/schema/prompt/catalog hashes and the exact
114-attempt plan. No provider smoke case precedes the measurement freeze.

## Predeclared per-language rules

Publish every attempt and per-case/repetition result. Report task correctness,
full pass (correct answer, required source and relationship coverage, trustworthy
delivery and hard budgets), unique required-source recall, relation coverage,
forbidden/unsupported claims, observed calls, full output/source bytes, measured
provider usage, latency and every hard-budget failure. Report synthetic Python
and its maintained single-module task separately as well as together.

Apply these rules independently to Python, JavaScript, Go, Rust and the bounded
TypeScript/TSX control. Markdown remains a separately reported navigation control.

1. **Measurement evidence:** every planned attempt must have complete raw
   source/tool/usage evidence and independent replay. Missing evidence makes
   that language inconclusive; it is not a success and cannot be hidden by an
   aggregate. Observed provider/tool failures remain in its denominator.
2. **Source trust:** any demonstrated wrong-origin edge, invented certainty,
   incomplete claimed proof, source mutation or unreported budget violation
   requires withholding the affected capability claim pending repair. Explicit
   unsupported or budget omissions are truthful limited delivery, not fabricated
   success. Distinguish a model's failure to request source from a retrieval defect.
3. **Task/context quality:** recommend the measured workflow only when every B
   attempt fully passes, with no per-case task-correctness or required-source
   regression against A. A wrong answer despite full correct source fails this
   rule but does not automatically justify a new reliability study.
4. **Efficiency:** for a workflow-efficiency claim, require at least 20% reduction
   in the sum of per-case median observed calls, at least one case saving one
   median call, output-byte and gross-input-token sums of case medians no greater
   than A, and nearest-rank p95 task latency no more than 1.25× A. Publish the
   underlying counts and medians. Small samples support only these bounded tasks.
5. **Disposition:** complete trust/quality/efficiency evidence supports the
   isolated recommended workflow for the measured scope. Passing trust/quality
   without the cost rule supports source delivery with efficiency unproven.
   Failing quality retains a measured limitation; a demonstrated retrieval defect
   needs an explicit restricted/withheld capability disposition. Missing evidence
   is inconclusive or unmeasured. None of these dispositions promotes the runtime.

Independent replay reconstructs fresh indexes, verifies all frozen identities
and exact model-visible payloads, and recomputes source/relation/answer and usage
accounting for the full plan. Publish the raw result, replay, rule outcomes and
per-language delivery decision. Do not change thresholds or rescore after seeing
provider outcomes. Update canonical Manifest, repository guidance and Brain with
the accepted scope and actual unresolved defects.
