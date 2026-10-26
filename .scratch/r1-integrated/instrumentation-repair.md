# R1 instrumentation repair and external continuation

The retained first native task now has `qualified_observations`, known reconciled
usage, a correct independent grade and matching archived-source replay. Thread
`01a176ca-a192-7cb1-8351-a0ca42d0d477` was not rerun. Original raw trace, rejected
qualification and original evaluation remain byte-identical in `pilot/archived-runs/`.
Corrected readback lives separately in `pilot/reprocessed/receipt-location-native/`.
`pilot/instrumentation-reprocessing.json` records the transition, original archive
hashes, same config/source/thread, and zero pilot launches during repair.

## Reader correction

`accounting.py` recognizes exactly one host bootstrap envelope by recorded
`content_item_kinds` and per-item provenance: `agents_md.instructions`/`agents_md`,
then `environments.environment_context`/`harness, hook=false`. Content lengths,
`input_text` types and explicit active-turn attribution must agree. Text prefixes
alone cannot earn an exception. Duplicated, late, mixed, partial or malformed
bootstrap is rejected. Legacy messages remain ordinary task messages. Pre-turn,
fork/inherited-history, assistant/tool-before-task, multiple-task and missing-final-
usage checks remain active; response/turn/thread usage still reconciles strictly.

## Amendment boundary

The original freeze identity remains
`4c20aff1be5e29ee7400d18c25421c890fcb30f626fd5d322250d208f2e93dfb`;
the original file is byte-for-byte unchanged. Explicit
`pilot/instrumentation-amendment.json` is required for changed runtime pins.
Its self-hash and base freeze identity are validated. Only existing original
orchestration pins for `accounting.py`, `r1.py`, and `pilot-execute.py` may change.
Each original hash must match; each new hash must match actual bytes. Startup
context, candidate implementation, configuration, executable, prompts, source,
model/effort, MCP conditions/stores, order and independent evaluators retain
their original bindings. Preparation and execution require the same amendment.

## Resume behavior

The existing runner now accepts `--resume` and `--check-only`. A retained prefix
must match schedule order, original invocation/workspace/store, source/trace and
oracle identities, distinct closed sessions, known qualified accounting, and
hashed independent grading/replay results. Corrected result locators may be
separate from the preserved original rejected archive. Wrong answers remain
valid scored outcomes and are not rerun. Partial/failed attempts and archive
collisions stop execution. Starting over on an existing index is refused.

Check-only performed no preparation or execution and returned:

```json
{"status":"checked","next_run_id":"receipt-location-path-only","pending":15,"retained":1}
```

Run the following in a normal top-level macOS Terminal, outside any Codex session.
It uses the existing runner and retains the first result; do not move its archive
or restart the schedule.

```sh
cd /Users/brummerv/phluxxed/loci/.worktrees/r1-integrated
PYTHONPATH=src:. /Users/brummerv/phluxxed/loci/.venv/bin/python -u \
  .scratch/r1-integrated/pilot-execute.py \
  --freeze .scratch/r1-integrated/pilot/frozen-final/freeze.json \
  --gate .scratch/r1-integrated/qualification-gate.json \
  --amendment .scratch/r1-integrated/pilot/instrumentation-amendment.json \
  --resume
```

The runner retains telemetry/grading/replay and stops on a launch, protection,
accounting or evidence blocker. No nested Codex launch or sandbox/global change
was made while implementing or verifying this repair.

## Validation and limits

69 focused tests passed: retained real trace and accounting negative controls,
amendment scope/drift/propagation checks, and 13 mocked resume tests. The broader
complete-work suite reported 148 passes and 11 passing subtests, with 5 failures
because its old pinned Anvil source export at `/tmp/anvil-source-tasks-20260914/t21`
is absent. The legacy oracle/prepare source is unchanged; no unrelated source
recovery or harness rebuild was added. Both full logs are retained.

Only the first native task is complete. Fifteen assignments remain unexecuted;
no comparison of Loci conditions or evidence that optional semantics helps is
claimed. Observed provider usage remains distinct from invisible retries/billing.
