# Directly observed retrieval protocol v3

V3 fixes the measurement interface exposed by v2. The agent no longer labels
reads or supplies causal parents. Thirteen typed tools expose the same current
retrieval operations, with closed, validated parameter schemas. The evaluator
counts actual calls and verifies actual source, output bytes, tokens and time.

All 17 case prompts, expected answers, 71 required source spans, 34 relationships,
source snapshots, production baseline, model route and numerical limits are
identical to v2. V1 and v2 remain unchanged historical evidence. V3 changes the
measurement denominator and recoverable-error treatment before new measurements;
it does not reinterpret their saved outcomes.

The primary read measure is all observed retrieval-workflow tool calls, including
initial discovery, hydration, verification, duplicate reads, empty results,
errors and resource helpers. It is not a count of proven avoidable reads. A
future matched comparison can establish reduced total work at retained answer
quality and source coverage. No per-call explanation proves a counterfactual.

A bounded recoverable tool error keeps its complete cost and diagnostic but does
not invalidate a later correct answer by itself. Hard-budget violations,
unverified source/output, missing required measurements, process failure,
timeouts and incorrect/malformed answers remain disqualifying. Nothing is
retried to improve correctness. A zero observed opportunity is a valid result.

See [comparison controls](comparison-controls.md) and
[observation accounting](observation-protocol.md). V3 must be committed and
published before any fresh measured corpus attempt.
