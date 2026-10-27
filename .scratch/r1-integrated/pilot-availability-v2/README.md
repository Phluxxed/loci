# R1 native availability preflight — configuration handoff repair

**Current status:** all four actual external probes passed full archive replay after the narrow [archive path repair](../archive-path-repair/README.md). That record retains the original failed final gate and the required instrumentation amendment. The 16 scored assignments are pending.

The prior rejection was reproduced: the global default model changed from `gpt-6-sol` to `gpt-6.1-sol`. Replacing that single value reconstructs the old raw file SHA256 exactly. The pilot explicitly supplies `gpt-6.1-terra` and `max`; its actual native contexts must match both.

This freeze keeps the old raw configuration hash and adds a versioned identity of all parsed TOML settings except the two root defaults explicitly overridden by the CLI. Every other setting remains bound, including permissions, MCP servers, features, context limits, nested profiles and unknown fields. Preparation and qualification retain separate raw/effective hash receipts and changed-default names. Legacy freezes remain byte-strict. Global configuration was not edited.

Vik also supplied a new AGENTS section during repair. Only removal of that section reproduces the old instructions hash. The new freeze pins the updated instructions rather than ignoring instruction changes.

The actual CLI entrypoint was exercised with the actual global configuration file through the process-creation boundary. The old rejection reproduced, and this version reached the pinned Terra/max native command with API-key environment overrides removed. Process creation and login status were intercepted: **this is not a native host or MCP success receipt.** See [handoff evidence](../config-handoff-repair/cli-handoff-summary.json).

Run the real four-condition check from a normal top-level macOS Terminal:

```sh
cd /Users/brummerv/phluxxed/loci/.worktrees/r1-integrated
PYTHONPATH=src:. /Users/brummerv/phluxxed/loci/.venv/bin/python -u \
  .scratch/r1-integrated/pilot-execute.py \
  --freeze .scratch/r1-integrated/pilot-availability-v2/freeze.json \
  --gate .scratch/r1-integrated/qualification-gate.json \
  --output-root .scratch/r1-integrated/pilot-availability-v2 \
  --amendment .scratch/r1-integrated/archive-path-repair/instrumentation-amendment.json \
  --preflight-only
```

This starts only four unscored native Codex checks. Each must discover its exact Loci tool set and positively exercise every enabled operation against independent probe source/stores; the native control must expose no Loci tools. Failure retains evidence and exits nonzero. No scored assignment starts. The saved actual receipts now pass; this command revalidates the existing gate without rerunning the probes.

After the saved gate passes, the existing command without `--preflight-only` can run the separate 16-assignment repair replication. Every measured session still needs its own catalog evidence before grading. Task-level tool use remains voluntary; mandatory discovery cost is counted. Original engineering task bodies, graders, condition tools, order and Terra/max pins are unchanged. Earlier runs remain availability-unverified and are not pooled with this protocol.
