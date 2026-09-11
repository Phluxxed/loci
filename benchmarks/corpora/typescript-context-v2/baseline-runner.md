# V2 A-only baseline runner

Run from the isolated exploration checkout after committing and publishing the
v2 corpus and measurement harness:

```sh
.venv/bin/python -m benchmarks.typescript_context_baseline --corpus-root benchmarks/corpora/typescript-context-v2 --output benchmarks/results/typescript-context-baseline-v2
```

The output directory must be new. There are 17 tasks with three fresh serial
attempts each. The runner checks the frozen environment and source snapshots,
then runs seven offline transport probes against the actual Codex CLI and the
batch model catalog before any measured model request. Each attempt also gets
an effective-input and tool-schema audit. These probes use a loopback fake
transport without authentication or a provider call.

Isolation, deadlines, provenance and failure retention follow the original
[runner contract](../typescript-context-v1/baseline-runner.md). V2 supersedes its
successful-read-only JSON reconciliation with the complete terminal-response
accounting in [read-lineage.md](read-lineage.md): structured results, invalid
attempts, schema errors and empty resource helpers retain all their payload
costs. A failed causal attribution remains a failed run even when costs are
complete. The original validated trace remains independently replayable.

Generate the report with the same explicit protocol root:

```sh
.venv/bin/python -m benchmarks.typescript_context_baseline_report --corpus-root benchmarks/corpora/typescript-context-v2 --output benchmarks/results/typescript-context-baseline-v2
```

Preserve every attempt and its outcome. No correctness retries or scoring changes
are allowed after observing the fresh answers. A-only findings are descriptive;
future candidate comparisons must rerun all comparator arms in a matched batch.
