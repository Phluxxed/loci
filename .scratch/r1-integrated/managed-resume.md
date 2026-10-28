# R1 bounded repair wait and seventh-run recovery

Seven native assignments are qualified and correct; nine remain pending. The
seventh passed the independent grader and replay using its original archive.
The first six results, all native traces and the failed-index checkpoint remain
preserved. No native task was repeated during recovery.

The seventh reader rejection concerned only the host's typed memory-summary
rendering label: 5091 tokens truncated became 5316 tokens truncated. All visible
memory text, other instructions and tool descriptors matched. The comparison
now permits that numeric rendering variation only inside a memories.instructions
part with exact non-hook harness provenance and MEMORY_SUMMARY boundaries. Raw
context is still retained unchanged; the count variation is separately recorded.
Different visible text, marker positions/counts, provenance, permission content,
catalogs or tool contracts remain differences. This does not assert that unseen
external memory files are identical; observed command traces in these seven
runs contain no memory-file reads.

The opt-in --resume --wait-for-repair mode keeps the existing normal-Terminal
runner alive after a closed native session with complete, known observations
encounters an observer-reader failure. It writes repair-wait.json and accepts
only a local request bound to the same freeze and blocked execution-index bytes.
The request selects a changed, hash-bound instrumentation amendment that must
pass the existing runtime checks. The process then replaces itself with this
same runner and the same freeze, gates, output root and resume flags. Normal
archive reprocessing and validation still run before any pending native work.

This is not a general command executor. Requests cannot change tasks, models,
permissions, gates or the schedule, or provide arbitrary shell commands.
Rejected requests and failed replacements retain their errors. A completed
pilot exits. Incomplete native executions, missing/unknown original evidence
and genuine native failures stop; they are never silently repeated.

182 focused checks passed. The integrated test exercises seven assignments,
a reader failure, waiting, a bound repair request, process replacement and the
remaining nine assignments with no duplicate delivery. It uses synthetic native
delivery and a mocked final execv, with real readers, source snapshots, grading,
replay and amendment validation. Actual seventh-run recovery preserved all
16,797 original archive files. [Machine evidence](managed-resume-checks.json).

The [explicit amendment](managed-resume-amendment.json) changes only reader and
runner instrumentation. Frozen task text, source, capture program, graders,
Terra 6.1 max, four conditions/stores, order and native protections are unchanged.
No new launcher, server, global configuration or permission profile was added.

## Start the existing runner once in normal macOS Terminal

The previous process already exited, so this initial external restart remains
necessary. Once running in this mode, subsequent eligible reader repairs can
be applied through the local request file without another operator relaunch.

~~~sh
cd /Users/brummerv/phluxxed/loci/.worktrees/r1-integrated
PYTHONPATH=src:. /Users/brummerv/phluxxed/loci/.venv/bin/python -u \
  .scratch/r1-integrated/pilot-execute.py \
  --freeze .scratch/r1-integrated/real-repo-pilot/frozen-final/freeze.json \
  --gate .scratch/r1-integrated/qualification-gate.json \
  --amendment .scratch/r1-integrated/managed-resume-amendment.json \
  --output-root .scratch/r1-integrated/real-repo-pilot/execution-capture-v2 \
  --resume --wait-for-repair
~~~

The assistant reads the execution index and archives directly; terminal-output
pasting is unnecessary. If a reader failure produces repair-wait.json, the
assistant can atomically write repair-request.json with exactly:

~~~json
{
  "schema_version": 1,
  "freeze_sha256": "value from repair-wait.json",
  "execution_index_sha256": "value from repair-wait.json",
  "amendment": {"path": "/absolute/new-amendment.json", "sha256": "file SHA-256"}
}
~~~

Stop waiting with Ctrl-C. Original failures and all request receipts remain
retained. The architecture recommendation remains pending the complete pilot.
