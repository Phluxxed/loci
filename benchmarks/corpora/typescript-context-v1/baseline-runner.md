# W2.1.7 — Current retrieval baseline runner

Run the frozen A-only baseline from the isolated exploration checkout:

```sh
.venv/bin/python -m benchmarks.typescript_context_baseline --output benchmarks/results/typescript-context-baseline-v1
```

The output directory must be new. `--resume` continues missing planned attempts
only when environment and harness hashes still match. It never retries a saved
answer. A partial attempt without a result stops resumption for explicit evidence
inspection. `--case` and `--repetition` produce a labelled incomplete batch.

The runner validates the frozen production source tree, CLI and complete Python
environment, verifies corpus integrity, and runs source preflight before any
model attempt. Each of the 17 cases gets three serial, fresh sessions and an
independent snapshot/index. Cold indexing is measured separately from the
180-second agent deadline.

## Effective isolation

Each Codex child uses a temporary configuration home. The live child reuses the
existing ChatGPT authentication through a temporary symlink; credential contents
are never included in artifacts. Temporary homes and source/store directories
are removed after each attempt. No ambient configuration, skills, Brain,
continuity or prior conversation is inherited.

The model catalog preserves the requested Luna model and its instructions while
disabling patch, hosted search, delegation and Code Mode capabilities. The only
source operation exposed is the read-only evaluation adapter. Codex's three MCP
resource helpers remain present; the sole configured server supplies no resources
or templates. Shell and repository execution are unavailable.

Before each live attempt, the same launch profile sends one request to an offline,
no-auth loopback endpoint. The runner inspects the actual model-visible input and
tool schemas, requires the exact common-plus-case prompt and Luna/high settings,
and rejects ambient instruction markers or unexpected tools. The endpoint returns
an error without calling a model. This verifies the launch profile; it is not a
claim that the provider exposes an immutable backend model revision. Every live
tool result is also matched against the adapter's recorded JSON before scoring.

## Measurements and limits

The adapter validates exact snapshot inventory and bytes before exposing index
metadata. Caller-supplied repository paths, unknown files/IDs and budget overrides
are rejected. All existing logical retrieval routes remain available, including
import/reference/call diagnostics. The same adapter contract applies to future
arms. Graph traversal uses existing validated resolution filters and frozen caps.

Complete compact UTF-8 structured JSON is the serialized-output measure. Codex's
transport timing prefix is outside that JSON and remains included in provider
tokens. Every actual source-string occurrence counts, including overlapping grep
contexts and repeated hydration. Per-operation and cumulative limits are checked
before delivery; an oversized result is replaced with bounded budget metadata
and the run is failed. The cumulative JSON check reserves 1 KiB per remaining
permitted call for bounded error metadata, within the frozen 256 KiB ceiling.
An attempted 25th read delivers no source and fails the run. Provider token limits
are checked at reported usage boundaries; overshoot remains visible.

Raw events, stderr, effective request audit, configuration hashes, source hashes,
causal trace, final answer and scored artifact are retained for each attempt.
Timeouts retain measured cost and use 180 seconds in the latency statistic; actual
process duration is recorded separately. Missing tokens are unavailable. Invalid
lineage or mismatched tool delivery cannot become a successful measurement.

Relationship scoring separates graph availability from delivered dependencies,
and generic type adjacency from precise relationship semantics. Negative counts
cover authored forbidden endpoints; zero does not establish exhaustive semantic
soundness. Source recall requires exact gold source coverage independently of
relationship recall. The earlier read-lineage protocol governs avoidable reads.

## Evidence and failure handling

The baseline is descriptive A-only evidence, not an improvement or candidate
acceptance claim. Preserve failed answers and all costs in the denominator.
Do not retry correctness failures. A suspected provider/host outage requires
inspection of preserved raw evidence before classification; the runner does not
automatically turn runtime errors into replacement attempts. Any replacement
must follow the frozen protocol's single-replacement allowance and retain the
original attempt separately. A second confirmed outage leaves the batch
incomplete. Harness faults stop the batch with existing evidence preserved;
changed harness hashes require a new evidence directory, not mixed resumption.

Generate the per-case report with
`python -m benchmarks.typescript_context_baseline_report --output <directory>`.
Future A/B and A/B/C decisions require new matched batches under the frozen
comparison controls. Historical A-only runs must not substitute for those runs.
