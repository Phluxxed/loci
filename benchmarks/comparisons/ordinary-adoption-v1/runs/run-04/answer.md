`renderActiveTask` returns a `string[]`.

- No active task (`null`): `["Active task:", "- none"]`. [src/continuity/render.ts](/tmp/anvil-source-tasks-20260914/t04/src/continuity/render.ts:67)

- With an active task, it returns:
  1. `"Active task:"`
  2. `- [<event_id>] (recorded <recorded_at YYYY-MM-DD>) <summary>`
  3. `- state: <state>`
  4. `- next step: <next_step>`

It shows `event_id`, the first 10 characters of `recorded_at`, `summary`, `state`, and `next_step`. `summary` and `next_step` pass through `truncateText`, which normalizes whitespace and truncates overlong text with `...`; the timestamp is sliced to its date. [src/continuity/render.ts](/tmp/anvil-source-tasks-20260914/t04/src/continuity/render.ts:12) [src/continuity/render.ts](/tmp/anvil-source-tasks-20260914/t04/src/continuity/render.ts:69)

The `ActiveTask` schema confirms those five fields. [src/continuity/schema.ts](/tmp/anvil-source-tasks-20260914/t04/src/continuity/schema.ts:41)

No material uncertainty.