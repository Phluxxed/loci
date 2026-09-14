`renderActiveTask` returns these lines when there is no active task:

```text
Active task:
- none
```

When present, it renders:

- `event_id`
- `recorded_at` (date only: first 10 characters)
- `summary` (truncated)
- `state`
- `next_step` (truncated)

The exact implementation is [src/continuity/render.ts](/tmp/anvil-source-tasks-20260914/t12/src/continuity/render.ts:67), lines 67–75. No material uncertainty.