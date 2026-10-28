# R1 capture and recovery repair

Superseded execution status: six measured assignments are now qualified, ten
remain pending. Use the [sixth-run recovery and resume command](capture-syntax-recovery.md),
which preserves the frozen capture program and handles non-executing syntax
rejections. The fresh-run command below is historical.

Current execution amendment: [capture plus personal-host observations](capture-host-observation-amendment.json).
The original capture amendment omitted the existing personal-host policy and
rejected a later global AGENTS.md edit before launching a probe. The new amendment
records the current personal instructions while preserving the actual cross-arm
context checks. It changes no runtime code, task inputs or native settings.
Current installed-host validation and 51 focused checks pass; the runner
integration uses the published policy selectors with personal instructions
changed after freezing. [Verification](host-observation-checks.json).
The original amendment and rejected attempt remain preserved.

The harness repair passes 251 tests, including the complete four-probe and
16-assignment runner flow with synthetic native delivery and real accounting,
grading and replay. The exact capture program also passed through the current
operator session's native file and command tools. Fresh top-level qualification
and the real-source scored pilot remain pending; these checks are not agent
performance results.

## Cause and correction

The earlier gate detected different tool catalogs but discarded the catalogs
behind their hashes. It could stop scoring without identifying the changed
tool. Separately, resume depended on live temporary directories and treated
completed native work followed by an observer failure as unrecoverable. Prior
isolated checks did not exercise that complete lifecycle.

The explicit [instrumentation amendment](capture-recovery-instrumentation-amendment.json)
changes the measurement prefix to retain the complete sorted common catalog in
the private observer directory. Its fixed program writes through native
apply_patch, independently reads and hashes the bytes through an isolated
standard-library Python command, and returns a bounded receipt. The reader
binds the exact program, file change, readback, receipt and retained bytes.
Full descriptions stay out of model output. Every arm uses this same protocol.

Catalog mismatches now identify added/removed tool names and changed description
hashes, separately from instruction/schema differences. Actual differences still
block scoring. No normalization or exception was added to admit the old drift.

Completed prefixes validate from archives. A closed native session with complete
qualified evidence can be reprocessed into a separate derived result; the
original archive and an index checkpoint are preserved. Incomplete sessions and
unknown evidence cannot be silently repeated. Preparation and archival errors
retain their own diagnostics instead of hiding the original failure.

The original freeze remains byte-identical; its identity is recorded in the
machine evidence below. Original engineering task text, source snapshots,
graders, Terra 6.1 max, conditions,
stores, order, native permissions and global configuration are preserved.
The amended measurement prefix is explicitly a protocol change; it is not
described as an unchanged delivered prompt.

## Verification

- 251 tests passed, including legacy readers and negative controls.
- The actual runner completed four offline probes and all 16 assignments,
  retained an intentionally wrong outcome, survived an interruption after the
  first checkpoint and resumed the remaining 15 without a repeated delivery.
- After live temporary roots were deleted, archive-only validation, raw
  accounting and independent Node replay still passed for all 16 assignments.
- A changed descriptor blocked all measured work and named the changed tool.
  Reader-only reprocessing recovered a completed valid probe set and a closed
  measured session whose reader had failed. Native process/session delivery was
  synthetic; interruption and reader failures were explicit fault injections.
- The exact program ran through real native helpers in this operator session:
  619 common descriptors, 882,508 retained bytes, independently matching hashes,
  and successful replay of its actual native file/command events. This was not
  a fresh pilot session or evidence that all four live conditions now match.
- All four historical probe archives replayed identically with known usage.
  Their real catalog difference remains rejected. Applying capture v2 to those
  hash-only archives fails explicitly because missing catalogs cannot be
  reconstructed. All 26 checked original evidence files remain unchanged.

[Machine evidence](capture-recovery-checks.json) records hashes and limits.
Private task sources, full catalogs and raw native records remain in the ignored
local real-repo-pilot directory. No new Codex CLI/model process, API billing,
launcher, sandbox/profile or global setting was introduced during this repair.

## Execute once from normal macOS Terminal

The existing runner performs the four fresh capture-v2 probes, then proceeds
through the frozen 16 assignments automatically if qualification passes:

~~~sh
cd /Users/brummerv/phluxxed/loci/.worktrees/r1-integrated
PYTHONPATH=src:. /Users/brummerv/phluxxed/loci/.venv/bin/python -u \
  .scratch/r1-integrated/pilot-execute.py \
  --freeze .scratch/r1-integrated/real-repo-pilot/frozen-final/freeze.json \
  --gate .scratch/r1-integrated/qualification-gate.json \
  --amendment .scratch/r1-integrated/capture-host-observation-amendment.json \
  --output-root .scratch/r1-integrated/real-repo-pilot/execution-capture-v2
~~~

For an interrupted measured schedule, use the same command with --resume;
--resume --check-only validates retained work without launching anything.
A completed native session with a recoverable observer failure is reprocessed
before pending assignments continue. For a completed probe set with a reader
failure, --reprocess performs reader-only recovery and returns gate_path. Pass
that path with --availability-gate to use the derived gate. Neither operation
manufactures missing evidence or repeats an attempted native session.

The old hash-only probes cannot qualify the new capture protocol. Their original
gate stays failed. A genuine new host failure or context difference is retained
and stops execution. Do not rerun blindly or relax the gate.

Recommendation: hold architecture advancement until the real pilot supplies
usable task outcomes. This repair establishes capture/recovery behavior, not
whether optional semantics improve correctness, time or model usage.
