# Native-host adoption accounting

W1.2.3. Contract version 1, 14 September 2026. No new scored provider attempt
has started under this contract. The ordinary task agents receive no observer
instructions. Collection reads their native Codex rollout after the task.

## Selected capture route

Use a small passive adapter for native rollout JSONL. Preserve exact terminal
MCP results and shell executions, outer Code Mode requests/outputs, final answer
and available provider usage. Do not add a model-facing wrapper, replace tools,
reconfigure the host, or add permanent product telemetry for this audit.

The native host retains `event_msg` / `item_completed` records containing
`McpToolCall` and `CommandExecution` items. MCP items carry unique IDs, server,
tool, arguments, status, duration and the native `result`, including camelCase
`structuredContent`. Events carry thread/turn IDs and start/completion times.
These are executed operations, including loop/dynamic calls, not source sites.

Evidence: retained session `01a09d82-8731-73b2-8c07-58b872b7feac`, 14 September:
the Code Mode request at line 123 maps eleven files; native outline completions
are at 125–134 and 137, including the completion after a yield. Three parallel
explore requests at 167 have individual native completions at 169–171 and outer
output at 172. Shell completions at 33–36 independently identify commands.
The initial adoption diagnostic also retains its thirteenth shell completion
at line 103, before the first answer/task completion at 109/112; the earlier
report's line 101 is the last request, not the end of the result interval.

| Alternative | Decision |
| --- | --- |
| Literal call-site scan | Keep historical results as diagnostic context. Cannot count loop iterations or establish native outcomes. |
| Existing benchmark observers | Reuse semantic distinctions and integrity lessons. Their `codex exec --json` event dialect and instrumented adapter traces do not match this native rollout. Do not silently feed native records into them. |
| Stdio boundary observer | Unnecessary for current terminal records; would require a different installed host boundary. The unrelated old scratch proxy only traces initialization and is stale. |
| Product usage events | Potential later product decision. Current get/outline statistics do not supply graph/host attribution and cannot backfill this audit. |
| Native rollout adapter | Selected: bounded normalization, validation and readout, with no task prompt contamination. |

## Identity and retention

Each scheduled row declares run ID, case ID, condition, repetition, role,
purpose (`ordinary`, `visibility_diagnostic`, `capability_probe`, `primary_check`
or `post_change`), requested model/effort, target snapshot root and identity,
prompt hash and instruction/catalog identities. Collection adds actual native
session/thread/turn IDs, agent path, observed model/effort and host version.
Requested settings and observed settings remain separate if they disagree.

Use one fresh agent/session and physically separate identical source copy per
scored delegated attempt. Read only its first task interval, through the first
`task_complete` or recorded interruption. Later catalog probes and follow-ups
have separate purpose and are excluded from ordinary counts. Parent collection
and evaluator-side probes never contribute to the agent's retrieval totals.

Retain an immutable hash of the selected raw interval and a normalized artifact
with line references/hashes. Raw private host sessions remain local; publish
only the selected task evidence and bounded summaries. Do not copy unrelated
prompts, reasoning, credentials, or other workspace records into audit artifacts.
Retain failures and partial artifacts through this Objective's verification.

## Execution and delivery records

- MCP request identity is native thread + turn + item ID. Store exact server,
  operation, arguments, target repo, status, start/end/duration, result and
  source line. A terminal tool error is still an invocation. Validate both
  native item status and `isError` / structured error. A failed native item may
  carry a complete application-error result; that is not evidence of a network
  failure or a corrupt missing result. A source-free validation rejection may
  have only content and `isError`, without `structuredContent`.
- Shell identity is native item ID, with process ID, command/argv, cwd, source,
  status, exit code, duration and available stdout/stderr. Shell commands count
  as executed commands; do not pretend an opaque script's inner operations are
  individually observed. CLI Loci, file reads and other opaque programs remain
  distinct channels. Unknown script internals do not become zero graph calls.
- Keep outer Code Mode call IDs and their exact outputs. Explicit request/output
  correlation uses those IDs. Native nested items have no explicit outer call
  ID: temporal containment is a candidate association, never a fabricated
  authoritative parent. Concurrency/yields may leave that association unknown.
- Native MCP result delivery is delivery to Code Mode JavaScript. Separately
  record what outer output exposed to the model: full result, selected fields,
  textual summary, truncation, absent or unknown. A result stored but not emitted
  is not model-visible proof. Do not charge a raw native result's bytes as if
  all of them entered model context.

Classify invocation by operation and actual arguments: exact retrieval;
explore `locate`; explore dependency/type-dependency/impact; opt-in type-context
get; explicit graph query; graph discovery/health; other; unknown. Also record
the actual returned semantic edge families/counts, relationship status,
omissions, source snippets/bytes and available output-budget declarations.
Containment-only edges are not semantic relationship delivery. Empty/partial
packets, unsupported resolution and errors remain distinct. Composite supporting
gets are internal evidence, not additional agent tool invocations.

Tool discovery is established by the agent's actual exposed catalog/description
output, with outer call/line evidence. Merely having `ALL_TOOLS` available, a
tool-name string in code, or a later sidecar catalog probe is not discovery by
the ordinary agent. Catalog-only work has its own cost and no graph-delivery
credit.

## Integrity and unknowns

Reject malformed JSON, missing/noncontiguous retained ordinals, duplicate terminal IDs, invalid terminal/result shapes,
unmatched outer results, conflicting metadata and altered retained hashes.
Missing required result, usage, final answer or task boundary has an explicit
missing state; it cannot become a successful zero. An interrupted task remains
in the schedule with partial accounting and no imputed final answer.

The native format is terminal-only. An intact completed host interval supports
a count of recorded completed invocations; it cannot prove that the host never
failed to record an upstream operation. Before freeze, validate known multiple,
dynamic, failed, empty/partial and type-context calls against expected native
events. Missing/corrupt retained records must fail those checks. A run without
a trustworthy terminal boundary or with opaque unobserved retrieval cannot
support a complete graph-use claim. Do not backfill missing runtime evidence
from regular expressions over agent-written source.

## Answer and cost accounting

The evaluator-only case rubric identifies required facts, acceptable source
identities and unsupported claims. A reviewer marks every required fact correct,
incorrect, missing or uncertain and cites answer text plus source evidence.
Ordinary prose and correct alternate routes are valid; no hidden JSON-format,
path-spelling or mandatory-graph requirement is used. Extra correct supported
facts are permitted. An unsupported assertion is a failure only when material
to the requested answer or contradicting its uncertainty boundary.

For every relationship-supported answer claim, cite the native proof item and
the model-visible output that exposed it. Record `supported`, `not_delivered`,
`not_used_in_answer`, `ambiguous_provenance` or `unknown` as applicable. Exact
source obtained independently can support a correct answer without graph
delivery. Observable support does not prove internal reliance or causal value.

Report per attempted run: answer status and required-fact coverage; terminal
MCP invocations by category; shell command executions; outer tool round trips;
serialized native response bytes, model-visible outer-output bytes and exact source bytes
as separate measures; elapsed task time; summed tool durations (which may
overlap); and provider input/cached-input/output/reasoning usage where recorded.
Do not double-count nested calls as extra outer round trips, call JSON byte
counts token counts, sum cumulative token snapshots, or subtract failures.
Missing usage remains missing; report completeness for every metric.
Specify the JSON serialization used for native-result byte counts; do not call
that reconstructed representation an observed wire size. Preserve a server's
own output-byte declaration separately where one exists.

The schedule denominator is all declared attempts, including failures,
interruptions and incomplete accounting. Per-case quality/cost comparisons use
the same rubric and matching source/model/role conditions. Report both the
complete-pair subset and all attempted outcomes; never discard a failed row to
improve a median. A graph-call fraction is descriptive only. Correctness and
useful source-supported answers take priority over invocation count.

W1.2.5 will validate the adapter and annotation contract on deterministic native
fixtures and retained known executions before W1.2.6 freezes the run schedule.
