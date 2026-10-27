# R1 startup reader repair

Subsequent result: all four probes passed this reader, but an
[unresolved common catalog difference](catalog-drift-report.md) blocked the gate.
The command below is retained history, not a new retry recommendation.

The normal Terminal native probe closed successfully and its observation
accounting qualified. The harness then incorrectly rejected a standard Code
Mode startup instruction. No scored assignment started.

The retained trace places the submitted task at row14, the typed startup hook
at row16, and first model activity at row17's native Reasoning completion event.
The validator used task submission as its startup boundary. It also retained
internal envelope creation timestamps in cross-session comparisons.

The reader now accepts only same-turn, typed harness hooks before first model
activity. It retains their ordered text, boundaries, kinds and provenance.
Response reasoning, assistant/tool actions and native item activity close that
exception. Second user/bootstrap messages, malformed/untyped hooks and later
instruction updates remain rejected. Only the explicit transport metadata
create_time joins the existing envelope ID exclusions; nested metadata is kept.
Failed probes now retain a known closed thread ID in their summary.

The existing instrumentation amendment mechanism now permits the exact pinned
availability reader file alongside r1.py. The
[explicit amendment](startup-hook-instrumentation-amendment.json) records both
original and replacement hashes. The frozen tasks, prompts, oracles, source,
model, effort, conditions, native argv, stores, order and protections are
unchanged. No global configuration, sandbox, profile or launcher changed.

Validation: [195 offline tests passed](startup-hook-tests.txt), including a
sanitized regression for actual envelope ordering, four-probe integration and
negative controls. Reprocessing the exact retained native trace now passes
and preserves all three startup hooks. Transport-only changes compare equal;
changed hook text changes the digest; foreign provenance/turn and a hook moved
after the first Reasoning event are rejected. [Check receipt](startup-hook-repair-checks.json).
A bounded Astra review independently confirmed the boundary, metadata exclusions
and amendment scope; primary implemented and verified the repair.

The original failed gate and raw trace remain untouched in the local private
archive. Reprocessing is reader evidence, not a passing four-condition gate.
The other conditions and measured work remain pending. No new native process
was launched from this Codex session.

From normal macOS Terminal, this uses the same freeze and existing runner with
the explicit reader amendment. A separate output root preserves the failed
preflight. Preflight runs first and stops on an actual qualification error.

~~~sh
cd /Users/brummerv/phluxxed/loci/.worktrees/r1-integrated
PYTHONPATH=src:. /Users/brummerv/phluxxed/loci/.venv/bin/python -u \
  .scratch/r1-integrated/pilot-execute.py \
  --freeze .scratch/r1-integrated/real-repo-pilot/frozen-final/freeze.json \
  --gate .scratch/r1-integrated/qualification-gate.json \
  --amendment .scratch/r1-integrated/startup-hook-instrumentation-amendment.json \
  --output-root .scratch/r1-integrated/real-repo-pilot/execution-reader-v1
~~~
