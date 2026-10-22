# R0.1 correction — native execution and telemetry

**2026-10-22. Native execution and completed-response telemetry: verified within the scope below. First measured pilot: NO-GO pending the remaining experiment prerequisites.** No measured pilot or native-versus-Loci model comparison ran.

This supersedes the custom-profile and supplementary Seatbelt requirements in the [original audit](2026-10-22-r0-1-harness-qualification.md). Those requirements are removed from the R0 path. Their historical failures are not current R0 blockers. The earlier reusable-component inventory, corpus proposal and independent-oracle findings remain useful with the execution-policy corrections here.

## The simplified path

[`benchmarks.complete_work.r0`](../../benchmarks/complete_work/r0.py) prepares independent source snapshots and reads back fresh native agent rollouts. **It starts neither a model process nor a sandbox.** Agents run through the existing native host with its existing protection settings. There is no dependency on `loci_episode_read`, `loci_episode_write`, their builder, or a Seatbelt probe. A regression test verifies that importing R0 loads neither the historical controller nor its isolation module.

Snapshot creation, hash checks, replay and JSON writing reuse [evaluate.py](../../benchmarks/complete_work/evaluate.py). Shared helpers moved there from the controller; the historical controller re-exports them, preserving its callers. Native readback reuses the [existing accounting reducer](../../benchmarks/complete_work/accounting.py) through a version-specific adapter. The historical graph-on/off controller retains its permission behaviour and campaign contract.

The R0 sequence is:

1. Prepare an evaluator-approved source export. Create one fresh copy per task/arm/repetition, with content-addressed initial source and observer/results stored outside the copy. Reject overlapping paths and existing destinations. Keep gold and prior results out of the exported source and agent brief.
2. Start a native agent thread with `fork_turns: none`, the assigned model/effort and task snapshot. Use that snapshot as each command's working directory. Keep native permissions unchanged; record actual settings and delivered instructions. Continue the same thread for fixed follow-ups. Capture stage source with the existing snapshot helper before sending the next prompt.
3. Retain the closed native rollout, source snapshots and hashes. R0 readback checks session/turn identity, terminal events, usage reconciliation, native protection/model settings and command working directories. It rejects delegated trial work outside the captured thread. Results and unsuccessful attempts stay in the assigned run.
4. Restore the retained candidate into evaluator-owned storage and invoke the existing task-specific oracle and arm-blinded review. Evaluation output does not return to the agent. A prospective experiment freeze must bind this sequence and the actual inputs before measured execution.

The native host exposes the same tool catalog to these helpers. Consequently the minimal proposed comparison is **native-only navigation instructions versus normal Loci permitted alongside native tools**, rather than a claim that Loci is physically absent from the native catalog. Native-only runs invoking Loci fail the policy check. Independent copies and fresh no-history threads provide experimental separation; they do not claim an additional OS prohibition on reading observer files. Any observed contamination must invalidate the affected attempt while retaining its resources.

`r0.prepare` and `r0.qualify` are preparation/readback operations, not a new experiment scheduler. The existing native host supplies sessions and cancellation; existing snapshot/oracle functions supply capture and independent grading. No replacement sandbox, permission manager, new dependency, global configuration edit or production retrieval change was added.

## Live evidence under unchanged protections

The [configuration receipt](../../.scratch/loci-r0-1/native-correction/configuration-check.json) records identical before/after SHA-256 hashes of the global Codex configuration. Protection overrides were empty. Native turn records retained the existing managed permission profile, sandbox, approval policy and reviewer. None was disabled or replaced. Qualification used bounded task-assistance fixtures, not historical corpus tasks or paid API inference experiments.

| Actual check | Observation and provenance |
| --- | --- |
| Fresh prepared-snapshot execution | [Assigned-control readback](../../.scratch/loci-r0-1/native-correction/assigned-control-current-summary.json): native thread `01a161d3-be4b-7351-91c0-9e684f0bf449`; copy/assert passed; deliberate exit 7 retained. Two inner command receipts, two outer calls and three response usage records. Initial/final source identities and the raw trace hash are retained. |
| Source binding and settings | Both commands used the assigned independent snapshot. Native command cwd is encoded as a local `file://` URI; readback supports that observed format. Effective native protections matched the original host; global configuration hash remained unchanged. |
| Independent replay and grading | [Evaluator receipt](../../.scratch/loci-r0-1/native-correction/independent-evaluation.json): restored the archived final snapshot outside the agent copy, independently verified the original and copied bytes, expected file set and native terminal outcome. All four checks passed without using agent-authored tests. This grades the qualification fixture only. |
| Same-thread continuation | [Continuation/cancellation receipt](../../.scratch/loci-r0-1/native-correction/continuation-cancellation-summary.json): thread `01a161d0-247c-7210-b798-85c4c4e0809f` completed two turns. Per-response sums reconciled with both turn and thread totals; second-turn usage was counted once. Initial path mistakes and the deliberate failed command remain in the trace. |
| Actual interruption | The third turn was explicitly interrupted through the native agent control. Its observed `turn_aborted` event is retained, elapsed 23,208 ms. One inner completion arrived 3,301 ms later; that cleanup tail is retained separately. Interrupted usage stays **unknown**, with its observed token lower bound preserved. No replacement or successful retry was substituted. |
| Historical compatibility and negative controls | [Final suite](../../.scratch/loci-r0-1/native-correction/final-tests.txt): **100 passed, 11 subtests passed**. Includes historical controller/oracles, real local MCP integration, R0 separation/equality guards and native accounting controls. |

These checks establish working native execution, continuation, failure capture, explicit cancellation and readback. They do not require or retest a supplementary sandbox. Native cancellation is not proof that every inner operation stops immediately: this control directly observed delayed cleanup and accounts for it.

The [worker note](../../.scratch/loci-r0-1/native-correction/worker-note.md) describes the first control before it closed; the primary continuation/cancellation receipt contains its final outcomes. Raw trace locations and hashes are retained in the receipts. Spawned threads share their parent's session-tree ID while maintaining distinct thread IDs and no inherited conversation for these `fork_turns: none` launches; accounting binds both identities rather than treating a shared tree ID as shared task history.

## Telemetry contract and rejection tests

Native `token_usage_record` supplies per-response usage and cumulative turn/thread usage. The adapter validates all required fields, deduplicates response IDs and reconciles the three levels. Completed turns additionally require final-answer usage after the final assistant message and before `task_complete`. An early positive usage update alone is insufficient. Missing final usage, corrupt or conflicting records, wrong identities, inherited-history evidence and incomplete captures cannot become known totals.

Outer `response_item` calls and outputs remain distinct from typed inner `event_msg.item_completed` receipts. Inner commands preserve argv, cwd, output, exit status and timing, including failed commands. The existing Loci delivery join now also accepts the observed native MCP result shape with explicit `isError: false`; `true` remains unsuccessful/unknown. Exact packet/source validation and independent scoring are unchanged.

[Native accounting tests](../../tests/test_complete_work_native_accounting.py) cover completed multi-turn usage, duplicates, missing final usage, unpaired outputs, corruption and interrupted partial usage including late completion. [R0 tests](../../tests/test_complete_work_r0.py) reject unequal source/config/protection conditions, shared threads/storage, changed global configuration, wrong command workspace, native-only Loci invocation, delegation, corrupt traces and missing usage. They also prove source copies are independent and R0 does not import the historical permission machinery. Prior snapshot corruption and oracle negative controls remain in the full suite.

Observed completed-response counts are **completion lower bounds**, not complete upstream request/retry or billing counts. Interrupted totals are not fabricated from the last update. Full raw records and partial observations remain available; resource comparisons with missing required totals must remain unproven. Loci packet bytes and native command outputs are evidence, not direct provider-token measurements or proof of model reliance.

## Revised protocol and remaining prerequisites

Retain the [draft historical task proposal](2026-10-22-r0-1-harness-qualification.md#proposed-corpus-and-provenance): the two full-work tasks are developmental fixtures selected for graph-context value; TypeScript answer-only cases are separate diagnostics. Independently selected ordinary tasks are needed before broad claims, not as an invented prerequisite for a narrowly labelled developmental pilot. Preserve all historical results and frozen scoring.

For the proposed R0 contrast, match source/dependencies, model/effort, task prompts/follow-ups, native protection configuration and common bootstrap/instructions. Declare the arm-specific navigation policy explicitly. Freeze fresh-thread identities, source-copy paths, limits and the complete assigned run-ID set. Count every attempt, including non-use, wrong answers, tool failures, interruption and invalid evidence. Report completion first, then observed time/U/K/O and per-correct resources only where evidence is complete; separate indexing/setup, cleanup and evaluation. Source versions and ambiguous read attribution remain explicit. No requirement to deny evaluator paths through a new sandbox is retained.

**Genuine remaining prerequisites for a measured pilot:**

- No prospective R0 paired-task/schedule/input freeze exists yet. The current controls exercised qualification fixtures, not the selected corpus with its full dependency environments and effective instruction bootstrap.
- Source capture, native terminal readback, independent replay and grading are demonstrated end to end for the live qualification fixture. The real corpus still needs its stage/snapshot/oracle/reviewer bindings fixed in the prospective protocol; the two historical task oracles are not replaced by copy/assert controls.
- Per-call Loci receipts and native source/output attribution have existing components and partial coverage, but their full association during an actual corrected-path task has not been live-qualified. Unresolved attribution must stay unknown; it must not silently support an information-efficiency claim.
- Explicit native interruption is verified; an automatically enforced frozen stage deadline was not exercised here. Invisible provider retries and complete interrupted usage remain unavailable in the observed trace contract. These limit the claims possible, rather than justifying another sandbox.

**Decision:** the corrected native execution and observed telemetry path passes the checks reported above. The first measured pilot remains **NO-GO** until its task-level evidence bindings and prospective freeze are ready. R0.1 is not declared fully qualified from deterministic tests or fixture execution alone. No host protection change or additional sandbox investigation is required by this decision.
