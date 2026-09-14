Start with `src/continuity/service.ts:327`. It is the complete checkpoint state machine.

- MCP validates `checkpointId` and task shape, requires a trusted binding, then calls the service: `src/mcp/tools.ts:213-228`, `805-830`.
- The service derives the bound workspace’s stored paths (`current.json`, `events.jsonl`) and locks the workspace: `src/continuity/service.ts:228-233`; `src/continuity/workspace.ts:30-45`; `service.ts:357-365`.
- It assigns a deterministic event ID from `(workspace key, checkpoint ID)`: `service.ts:303-305`. It appends a `next_action` event (or `correction` for clear) to `events.jsonl`, then projects the desired task into `current.json`: `service.ts:381-420`; persistence is `src/continuity/store.ts:369-391,402-419`.
- The injected/rendered Continuity frame reads `active_task.next_step`, so that is exactly where old text surfaces: `src/continuity/render.ts:67-93`.

Same key behavior:

- **Identical task content:** the existing deterministic event is reused; no duplicate event is created. The desired active-task projection is still reapplied if it was missing or different; otherwise `changed` is false. This means retrying an old identical checkpoint can restore its old next step after a reset or replacement: `service.ts:362-370,391-420`. The source test explicitly covers unchanged retry (`changed === false`) and recovery after the current frame is reset (`changed === true`): `test/continuity-service.test.ts:416-423`.
- **Changed task content:** it throws `VALIDATION_ERROR` before recording or updating the frame: `service.ts:366-371`. The equality check covers event type, summary/outcome, and generated details, which include state, next step, and optional details: `service.ts:308-324`. Therefore, updating a next step requires a **new checkpoint ID**; that new event supersedes the prior active-task event: `service.ts:380-389`.

Clearing:

- A new clear checkpoint writes a `correction` event, records its outcome, resolves/relates to the prior active task, and sets `current.active_task = null`; it does not delete historical events: `service.ts:373-420`.
- Its rendered result becomes `Active task: - none`: `render.ts:67-69`.
- Retrying the same clear checkpoint is normally idempotent (`changed === false`); the test also confirms no duplicate events: `test/continuity-service.test.ts:440-458`.
- Subtle consequence: an identical retry is still a projection operation. If a task has since reappeared, retrying the old clear key will set `active_task` back to `null`; likewise an old identical active checkpoint can reassert its old next step. That follows directly from `service.ts:391-420`.

Material uncertainty: this traces the implemented semantics and source tests; I did not inspect a live Continuity store or a particular resumed session, so it cannot establish which caller retried which key in the reported incident.