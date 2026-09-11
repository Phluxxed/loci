# V3 A-only baseline runner

Run from the isolated exploration checkout after committing and publishing the
v3 corpus, controls and measurement harness:

```sh
.venv/bin/python -m benchmarks.typescript_context_baseline_v3 --corpus-root benchmarks/corpora/typescript-context-v3 --output benchmarks/results/typescript-context-baseline-v3
```

The output directory must be new. The runner verifies the published working
files against freeze.json, production source, environment, CLI and source
snapshots. It audits the actual model-visible request before each attempt.
Ten deterministic offline probes verify the actual Codex tool-output transport
using the batch's fresh model catalog before any measured provider request.
These probes use a loopback fake response with no authentication or provider call.

There are 17 cases with three fresh serial A attempts each. Every attempt has a
fresh source snapshot, prebuilt index and isolated Codex session. Cold indexing
is timed separately. The existing isolation and process-deadline mechanics are
reused without changing the historical v1/v2 runners or artifacts.

Each result keeps raw host events, provider usage, trace, every adapter attempt,
exact payload text and source spans, request audit and provenance. Schema
rejections before adapter execution and resource-helper errors are reconciled
against the host log as well. No agent-declared causal attribution is collected.
All observed calls count. Missing or unexpected evidence remains inconclusive.
A bounded recoverable error retains its cost and may precede a valid answer;
hard-limit violations, process failures and incomplete measurements cannot pass.

The runner's summary.json remains unchanged evidence. Generate a separate
report-summary.json and report.md after the complete batch:

```sh
.venv/bin/python -m benchmarks.typescript_context_report_v3 --corpus-root benchmarks/corpora/typescript-context-v3 --output benchmarks/results/typescript-context-baseline-v3
```

Independently replay every trace and reconcile every cost from raw events before
publishing results. Retain failed attempts; no correctness retries or post-answer
scoring changes are permitted. Future B/C comparisons rerun A in a fresh matched
batch using the v3 contract. This A-only batch cannot establish an improvement.
