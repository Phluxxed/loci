# R1 first top-level run: task passed, frozen reader blocked

The external top-level Terminal launch completed native thread
`01a176ca-a192-7cb1-8351-a0ca42d0d477` for `receipt-location-native`.
Independent answer/behavior grading passed, and archived-source replay agreed.
Only the allowed `answer.json` changed. The original qualification remains
`unqualified`; its telemetry was discarded by the reader before returning.

The precise blocker is `benchmarks/complete_work/accounting.py`'s
`first_turn_users != 1` freshness guard. The trace has two user-role records:
the host-generated AGENTS/environment bootstrap at row 7 (zero based), then
the exact 1,032-byte frozen task prompt at row 13. It has one recorded turn,
unforked `exec` session metadata, and no preceding model work. Counting the
bootstrap as another task message causes `native rollout has no single fresh
first-turn user message`, followed by `native turn settings unavailable`.
The latter is a consequence of the exception, not evidence settings are absent.

Read-only reconciliation of the original archived trace recovered:

| Observation | Value |
| --- | ---: |
| Independent task correctness | Passed |
| Client launch-to-close elapsed | 22.959559 s |
| Native recorded task duration | 21.489 s |
| Provider input tokens | 118,160 |
| Cached input tokens, subset of input | 95,232 |
| Uncached input tokens | 22,928 |
| Provider output tokens | 934 |
| Reasoning tokens, subset of output | 124 |
| Total input plus output tokens | 119,094 |
| Reported response completions | 5 |
| Shell calls / failed shell calls | 4 / 0 |
| File-change items | 1 |
| MCP / semantic / proof calls | 0 / 0 / 0 |

Every response usage record reconciles with the cumulative turn/thread totals;
the final response usage falls after the final answer and before task completion.
CLI `turn.completed` usage agrees. Model/effort and all six recorded native
protection fields match the freeze; command working directories match the
assigned isolated source. This is a supplemental posthoc readback, not a rewrite
of the frozen reducer's result or a claim of complete billing/retry visibility.

The machine-readable checks and trace hash are in
[top-level-first-run-readback.json](top-level-first-run-readback.json).
Original raw trace, unqualified result, grading and replay are preserved under
`pilot/archived-runs/receipt-location-native/observer/`. Previous startup failures
were preserved by the external command under `pilot/pre-top-level.Ddn9oQ/`.

The runner stopped after the first assignment, leaving 15 unattempted. This
native-only task supplies no comparison with Loci and cannot establish whether
optional semantics helps. Correctness/efficiency for the other conditions remain
unknown; do not rerun or replace this successful task.

The remaining action is a narrow accounting compatibility correction that
distinguishes host bootstrap from task history while retaining freshness checks,
followed by readback of this same closed trace and continuation at assignment two.
Accounting and orchestration hashes are pinned by the freeze, so applying that
correction would require an explicit recorded compatibility amendment. No frozen
code, prompt, evaluator, model, effort, condition, store assignment, task order,
sandbox setting or global configuration was changed during this diagnosis.
