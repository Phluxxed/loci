`renderActiveTask` returns:

- No active task: `["Active task:", "- none"]`.
- Active task:
  - `"Active task:"`
  - `- [${event_id}] (recorded ${recorded_at.slice(0, 10)}) ${truncateText(summary)}`
  - `- state: ${state}`
  - `- next step: ${truncateText(next_step)}`

It shows `event_id`, the date portion of `recorded_at`, `summary`, `state`, and `next_step`. `summary` and `next_step` are passed through `truncateText`.

Evidence: [`src/continuity/render.ts`](/tmp/anvil-source-tasks-20260914/t05/src/continuity/render.ts:67). No material uncertainty.