Start at [`src/continuity/service.ts:327`](/tmp/anvil-source-tasks-20260914/t15/src/continuity/service.ts:327). The MCP tool is registered in [`src/mcp/server.ts:269`](/tmp/anvil-source-tasks-20260914/t15/src/mcp/server.ts:269), and its handler validates the host-supplied binding then calls the service in [`src/mcp/tools.ts:807`](/tmp/anvil-source-tasks-20260914/t15/src/mcp/tools.ts:807).

`checkpointActiveTask` derives a deterministic event ID from `workspace.key + checkpointId` ([`service.ts:303`](/tmp/anvil-source-tasks-20260914/t15/src/continuity/service.ts:303)), records an event, then projects:

```text
event summary/details (including nextStep)
  → events log
  → current.active_task { summary, state, next_step }
  → next SessionStart renders active_task
```

The event append and current-frame write are in [`src/continuity/store.ts:343`](/tmp/anvil-source-tasks-20260914/t15/src/continuity/store.ts:343) and [`store.ts:394`](/tmp/anvil-source-tasks-20260914/t15/src/continuity/store.ts:394). A new session reads and renders that stored `active_task` in [`bin/anvil.ts:656`](/tmp/anvil-source-tasks-20260914/t15/bin/anvil.ts:656); the rendered next step comes directly from `active_task.next_step` ([`render.ts:67`](/tmp/anvil-source-tasks-20260914/t15/src/continuity/render.ts:67)). The cross-session test demonstrates this exact path at [`test/codex-hook.test.ts:543`](/tmp/anvil-source-tasks-20260914/t15/test/codex-hook.test.ts:543).

Retry behavior:

- **Same checkpoint key, identical task content:** it finds the same deterministic event and does not append another. If the current frame already matches, `changed` is false. If the frame was reset or differs, it re-projects the old task and `changed` is true ([`service.ts:362`](/tmp/anvil-source-tasks-20260914/t15/src/continuity/service.ts:362), [`service.ts:391`](/tmp/anvil-source-tasks-20260914/t15/src/continuity/service.ts:391), [`service.ts:403`](/tmp/anvil-source-tasks-20260914/t15/src/continuity/service.ts:403)). This can restore an old next step.
- **Same key, changed task content:** it throws `VALIDATION_ERROR` before any write: “checkpointId … was already used for different task content” ([`service.ts:366`](/tmp/anvil-source-tasks-20260914/t15/src/continuity/service.ts:366)). Changed summary, state, next step, outcome, or details changes the comparison because state/next step are encoded into event details ([`service.ts:308`](/tmp/anvil-source-tasks-20260914/t15/src/continuity/service.ts:308)). The existing active task therefore remains intact. Updating work requires a **new checkpoint ID**, which supersedes the prior task ([`service.ts:380`](/tmp/anvil-source-tasks-20260914/t15/src/continuity/service.ts:380)).
- **Clear:** a fresh clear checkpoint writes a `correction` event, resolves the prior task event, and sets `current.active_task` to `null` ([`service.ts:381`](/tmp/anvil-source-tasks-20260914/t15/src/continuity/service.ts:381), [`service.ts:403`](/tmp/anvil-source-tasks-20260914/t15/src/continuity/service.ts:403)). It preserves event history. Clearing a missing frame, or a frame with no active task, is rejected for a new key ([`service.ts:373`](/tmp/anvil-source-tasks-20260914/t15/src/continuity/service.ts:373)); immediate identical clear replay is a no-op.

The service test covers normal retry, recovery/reprojection, replacement, clearing, and no duplicate events at [`test/continuity-service.test.ts:368`](/tmp/anvil-source-tasks-20260914/t15/test/continuity-service.test.ts:368).

Material caveat: identical replay does not check that the currently projected task is still the one originally checkpointed. It will reassert its old task over whatever is currently in `active_task`; similarly, an old clear replay can clear a newer active task. The source does not establish whether that is the cause of the reported resume.