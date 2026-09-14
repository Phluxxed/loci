`renderActiveTask` returns:

- No active task: `["Active task:", "- none"]`.
- Active task: four strings:
  1. `"Active task:"`
  2. `- [<event_id>] (recorded <recorded_at YYYY-MM-DD>) <summary>`
  3. `- state: <state>`
  4. `- next step: <next_step>`

It displays `event_id`, `recorded_at` (only its first 10 characters), `summary`, `state`, and `next_step`; `summary` and `next_step` pass through `truncateText`. See [src/continuity/render.ts](/tmp/anvil-source-tasks-20260914/t19/src/continuity/render.ts:67). The schema confirms these are the complete strict task fields, with `state` constrained to `active` or `waiting`: [src/continuity/schema.ts](/tmp/anvil-source-tasks-20260914/t19/src/continuity/schema.ts:38).

No material uncertainty: the function body was directly inspected; Loci reported partial graph coverage, which does not affect this exact source finding.