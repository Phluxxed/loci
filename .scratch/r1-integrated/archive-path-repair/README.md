# Native probe archive replay repair

The four actual external native sessions passed their individual availability audits. Final validation failed because accounting records the input rollout path: qualification used the live temporary path; replay used the retained archive path. Every other accounting field matched exactly in all four traces.

The validator now reconstructs the original qualification path from the bound run manifest when comparing accounting. It still compares every remaining accounting field, verifies the recorded original path, and checks archived trace hashes, source bytes, task prompts, native model/effort/protections, usage, catalogs and real MCP evidence. It does not require the temporary directory to survive.

The original failed gate is retained byte-for-byte in `original-failed-gate.json`. `replay.json` records all 79 unchanged probe-file hashes and the four original threads. `replayed-gate.json` passed the complete validator before being published to the existing availability gate path. No probe, trace, qualification, prompt, task, candidate, grader, model, protection or freeze was changed. No Codex process was launched during recovery.

The explicit `instrumentation-amendment.json` replaces only the existing r1.py harness pin. The original freeze is unchanged. The actual runner's `--check-only` revalidated this gate and reports 16 pending scored assignments, zero retained scored attempts. Focused regression checks: 110 passed, including full replay of all four real archived probes and rejection of altered accounting/provenance.

Availability is now verified for this native host configuration. This does not establish task utility or whether optional semantics helps: the four checks were unscored operational probes. The next step is the frozen 16-assignment pilot in a normal top-level Terminal:

```sh
cd /Users/brummerv/phluxxed/loci/.worktrees/r1-integrated
PYTHONPATH=src:. /Users/brummerv/phluxxed/loci/.venv/bin/python -u \
  .scratch/r1-integrated/pilot-execute.py \
  --freeze .scratch/r1-integrated/pilot-availability-v2/freeze.json \
  --gate .scratch/r1-integrated/qualification-gate.json \
  --output-root .scratch/r1-integrated/pilot-availability-v2 \
  --amendment .scratch/r1-integrated/archive-path-repair/instrumentation-amendment.json
```

This reuses the validated four-probe gate. It does not rerun those sessions. Each scored session retains its own mandatory catalog check; engineering tool use remains voluntary.
