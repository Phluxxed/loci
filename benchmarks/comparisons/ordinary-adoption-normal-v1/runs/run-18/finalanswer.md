`renderActiveTask` returns `["Active task:", "- none"]` when `activeTask` is null/falsy.

With a task, it returns:

1. `"Active task:"`
2. `- [<event_id>] (recorded <recorded_at first 10 chars>) <summary>`
3. `- state: <state>`
4. `- next step: <next_step>`

It therefore displays `event_id`, `recorded_at` (date portion only), `summary`, `state`, and `next_step`; `summary` and `next_step` pass through `truncateText`. Evidence: [src/continuity/render.ts](/tmp/anvil-source-tasks-20260914/t18/src/continuity/render.ts:67). No material uncertainty.