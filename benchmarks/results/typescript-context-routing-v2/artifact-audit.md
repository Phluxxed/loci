# Routing-v2 artifact audit

Status: **complete**.
Audited 102/102 completed attempts; completion sentinel present: **True**.

## Counts

| Arm | Attempts | Correct | Task-correct | Measurements complete | Calls | Output bytes | Gross input tokens |
|---|---:|---:|---:|---:|---:|---:|---:|
| A | 51 | 51 | 51 | 51 | 260 | 399029 | 2119855 |
| B | 51 | 50 | 50 | 51 | 205 | 363404 | 1803600 |

## Maintained B source exposure

Native requested-anchor receipts: 9/9; stored maintained exposure true: 9/9; replay complete: True.
Source receipt is retained separately from the stored context-recall value.

## Known correctness evidence

- `generic_shadow-r1-B`: answer_correct=False, task_correct=False

## Audit failures

None.

The JSON artifact retains complete per-attempt maintained-anchor records, raw failures, replay fingerprint checks, lifecycle joins, and binding checks.

The [retained audit checker](artifact-audit.py) independently reads the native
events and frozen snapshot archives. It verifies 465 observed tool calls,
1,634 source spans and all 1,023 replay fingerprints, with zero provider calls.
The primary corrected its initial assumptions about normalized null byte limits
and source-free rejected deliveries before publishing this audit. Frozen source,
measurement code and result records remained unchanged.
