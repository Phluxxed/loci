# Directly observed TypeScript retrieval baseline

The dependable-baseline repair is complete. All **51 fresh A-only attempts**
produce correct answers and pass the predeclared v3 validity rules: 42 fixture
attempts and nine maintained-repository attempts. Every call count, delivered
payload cost and provider token total is complete. All 51 exact source replays
and raw-event reconciliations pass with 51 distinct trace and provider sessions.

The three maintained tasks are eligible for comparison. Their median observed
call counts are **5, 7 and 10**, giving a positive comparator sum of **22**.
This measures all retrieval work, including planned reads; it does not identify
which individual calls are avoidable or prove that expansion will reduce them.
Future B/C comparisons must rerun A in a fresh matched batch.

The protocol, corpus and harness were published at
[`e06da38`](https://github.com/Phluxxed/loci/commit/e06da38caee106d2cb47a6a48f84b5508654e4b3)
before any measured v3 request. There were no correctness retries, replacements,
timeouts, hard-budget failures or post-freeze scoring changes.

## What was repaired

V2 asked the agent to label the cause of its own reads and exposed one loosely
typed wrapper. V3 records host-observed calls directly and exposes 13 separate,
strictly validated operation schemas. It also counts exact schema-error and
resource-helper payloads, including a nonexistent-server error. Missing or
unexpected evidence remains inconclusive; it is never converted to zero.

The 17 questions, expected answers, 71 required source spans, 34 authored
relationships, source archives, production baseline, model route and numerical
limits/gates are identical to v2. V3 explicitly changes the read denominator
and recoverable-error treatment before measurement. A bounded input error may
precede a passing answer while retaining its full cost. V1/v2 remain unchanged
historical evidence and cannot be paired with these results to claim a gain.

## Maintained-task measurements

| Task | Full passes | Call counts | Median calls | Median source recall | Median output bytes | Median gross input tokens |
|---|---:|---|---:|---:|---:|---:|
| Temporal arguments | 3/3 | 5, 4, 5 | 5 | 0.8 | 11,419 | 40,778 |
| Retrieval limits | 3/3 | 7, 8, 6 | 7 | 1.0 | 20,641 | 67,681 |
| Renderer result contract | 3/3 | 8, 10, 10 | 10 | 1.0 | 30,667 | 102,444 |

All-nine maintained p95 latency is **50.258 seconds** (nearest rank).
Cold-index medians, timed separately, are 3.876, 3.834 and 3.725 seconds.
A full pass establishes the exact answer, complete measurement and compliance
with hard limits; required-source recall remains a separate quality measure.
Across all attempts, 198 of 213 repeated required source spans were delivered;
37 attempts delivered every required span. Names and inferred metadata receive
no source credit. Future candidates must retain each task's median source recall.

## Complete costs and retained errors

- **271** observed tool calls; **364,008** bytes of delivered result payloads.
- **101,089** delivered source bytes: 72,320 unique within runs and 28,769 duplicate.
- **2,050,985** gross provider input tokens; 1,493,248 cached input tokens are a subset.
- **29,650** provider output tokens, including reasoning. Byte-derived source-token
  estimates are separate. ChatGPT authentication provides no API dollar total.
- Maintained attempts account for 63 calls, 189,051 output bytes and 592,946 gross
  input tokens. Their costs include all nine attempts.

One recoverable invalid-pagination error occurred in `ambiguous_star_exports-r3`.
Its call and exact output are retained; the agent then answered correctly within
all limits. There are no omitted or replaced failed attempts.

The frozen relationship oracle has 102 repeated requirements: 15 links are
available and none were delivered as graph links in these agent runs. Zero
**authored forbidden** proven relationships were observed. That negative check
is not exhaustive soundness, and correct source-comprehension answers do not
establish new semantic capability or broad code-editing performance.

## Verification and reproduction

Before measurement, **122 focused checks**, **ten actual offline Codex transport
modes**, the effective-request audit and all 17 endpoint preflights passed. The
batch repeated its ten offline probes using its fresh model catalog. Every run's
actual request was audited for the frozen prompt, Luna high and the fixed tool
surface. Gold and ambient Brain/instructions stayed outside the agent snapshot.
The unversioned model slug does not pin provider backend weights.

The independent verifier checks current and committed harness/corpus bytes,
environment, every request/provenance binding, exact source replay, complete
host-call lifecycle and cost reconciliation, provider identities and saved totals.
Raw offline transport evidence is independently replayed too.

```sh
.venv/bin/python benchmarks/results/typescript-context-baseline-v3/verify.py --corpus-root benchmarks/corpora/typescript-context-v3 --output benchmarks/results/typescript-context-baseline-v3
```

See [all run outcomes](report.md), [aggregated measurements](report-summary.json),
[independent verification](verification.json), [frozen controls](../../corpora/typescript-context-v3/comparison-controls.md),
[batch environment](environment.json), [transport evidence](transport-verification.json)
and [artifact fingerprints](artifact-sha256.json). `summary.json` is the unchanged
runner output; each run directory retains its raw events, trace, result, effective
request and provenance. The verifier does not start a model or alter measurements.
