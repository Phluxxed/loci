# R1 availability-checked protocol: Terra 6.1 / max

**Not executed. Native-host availability remains unverified until the following external checks pass.** This separate protocol preserves the original task bodies, source identities, independent graders, four conditions, order, model and effort. It adds mandatory discovery and real callable-tool gates; it is not a continuation of the availability-unverified comparison.

Run this from a normal top-level macOS Terminal:

```sh
cd /Users/brummerv/phluxxed/loci/.worktrees/r1-integrated
PYTHONPATH=src:. /Users/brummerv/phluxxed/loci/.venv/bin/python -u \
  .scratch/r1-integrated/pilot-execute.py \
  --freeze .scratch/r1-integrated/pilot-availability-v1/freeze.json \
  --gate .scratch/r1-integrated/qualification-gate.json \
  --output-root .scratch/r1-integrated/pilot-availability-v1 \
  --preflight-only
```

This runs only the four unscored native condition checks. It discovers the actual tools through Codex and calls every enabled operation on separate probe source/stores. It retains native threads, prompts, operation results, hashes, tokens, elapsed time and qualification at `availability/`. A failed or incomplete probe stops the check and is not silently retried. A missing/filtered tool is an error, never successful non-use.

After successful external validation, the same existing command **without `--preflight-only`** validates the saved gate and runs the separate 16-assignment repair replication. It does not rerun successful probes. Every measured session must log its actual catalog first; task-level Loci use remains optional. The full discovery cost is measured. `--check-only` is read-only and refuses readiness without a valid gate; `--resume` requires valid retained gate/catalog evidence and never replaces an attempted assignment.

The global configuration was read and pinned without editing it. Native protections remain fixed by the captured policy and are verified in the actual probes. If a frozen environment hash changed, the runner fails closed. Do not override the check or change sandbox/profile/global settings.

See [repair and validity boundaries](../availability-repair/README.md). The engineering task bodies and graders are untouched; previous results are known, so this is a repair replication rather than a new unseen-task experiment. Historical freezes/archives/grades remain available, with their architecture recommendation explicitly withdrawn.
