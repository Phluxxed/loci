# Trustworthy Analyzer Findings

Status: ready-for-agent

## Problem Statement

Loci's usage analyzer currently presents two recommendations whose evidence does not support their stated mechanisms.

The `poor_extraction` finding applies a savings-ratio threshold without an evidence floor. In the weekly tooling review, six Go retrievals and one JavaScript retrieval were enough to produce medium-severity findings. One full-file retrieval can therefore look like a recurring extractor problem even when the dominant languages show strong savings and no durable cost has been established. The finding also omits the retrieval and byte denominators needed to judge its weight.

The `refetch_hotspot` finding counts repeated symbol retrievals across an entire analysis window and suggests that frequently retrieved symbols may be too large to remain in context. Durable retrieval events do not carry session identity, so Loci cannot distinguish repeated retrieval within one agent context from expected reuse across independent sessions. The recommendation asserts a context-retention mechanism that the available evidence cannot observe.

These findings feed the weekly improvement review. Unqualified severity and unsupported causal language can direct Vik and Rowan toward speculative optimization work instead of trustworthy, demonstrated tooling improvements.

## Solution

Make `poor_extraction` decision-ready by requiring at least ten eligible retrievals for a language before emitting the finding. Preserve the existing savings threshold, but include the retrieval count, total symbol bytes, and total file bytes alongside the average savings percentage so every emitted finding exposes its evidence denominator.

Suppress `refetch_hotspot` completely while retrieval telemetry lacks a session boundary. Remove its analyzer output, advertised output-schema branch, documentation claim, and tests that assert the unsupported recommendation. Preserve ordinary retrieval events and retrieval-cost statistics unchanged; this work does not add session telemetry or replace the finding with another inference.

Accept the behavior through one representative end-to-end stdio MCP test of `loci_analyze`. The test exercises the shipped agent-facing serialization and validation boundary: low-sample extraction evidence remains silent, sufficient evidence emits a denominator-rich finding, and repeated retrievals never produce or advertise a refetch finding.

## User Stories

1. As a Codex agent, I want analyzer findings to require enough observations, so that isolated retrievals do not masquerade as recurring tooling problems.
2. As a Codex agent, I want `poor_extraction` to remain silent below ten eligible retrievals for a language, so that the weekly review does not overreact to tiny samples.
3. As a Codex agent, I want the tenth eligible retrieval to satisfy the evidence-count floor, so that the boundary is deterministic and testable.
4. As a Codex agent, I want the existing savings-ratio threshold preserved after the evidence floor is met, so that this change repairs confidence rather than redefining extraction quality.
5. As a Codex agent, I want a language with ten efficient retrievals to remain free of a finding, so that sample sufficiency alone does not imply poor extraction.
6. As a Codex agent, I want a language with ten poorly saving retrievals to produce a finding, so that repeated low-savings behavior remains visible.
7. As a Codex agent, I want each extraction finding to report its eligible retrieval count, so that I can judge whether the pattern is marginal or well established.
8. As a Codex agent, I want each extraction finding to report total retrieved symbol bytes, so that I can see the amount of source actually loaded.
9. As a Codex agent, I want each extraction finding to report total corresponding file bytes, so that the savings ratio has a visible denominator.
10. As a Codex agent, I want the average savings percentage and byte totals to describe the same selected evidence, so that the finding is internally consistent.
11. As a Codex agent, I want retrievals without a language classification excluded from the per-language evidence floor, so that unknown data does not inflate a named language's confidence.
12. As a Codex agent, I want retrievals with no usable file-byte denominator to remain ineligible for an extraction finding, so that Loci never divides by or reports meaningless evidence.
13. As a Codex agent, I want the requested analysis window applied before the evidence floor is counted, so that old retrievals cannot make a recent weak pattern look durable.
14. As a Codex agent, I want repository filtering applied before the evidence floor is counted, so that one repository's activity cannot qualify another repository's finding.
15. As a Codex agent, I want analyzer severity to remain medium only after the evidence floor and poor-savings threshold both pass, so that severity communicates qualified evidence.
16. As a Codex agent, I want extraction findings serialized through the public MCP output contract with their denominators intact, so that hosts and weekly reviews receive the same evidence the analyzer evaluated.
17. As a Codex agent, I want repeated retrievals across independent work to remain ordinary retrieval telemetry, so that expected reuse is not presented as context failure.
18. As a Codex agent, I want `refetch_hotspot` omitted from analyzer findings while no session identity exists, so that Loci makes no unsupported retention claim.
19. As a Codex agent, I want the public analyzer schema to stop advertising `refetch_hotspot`, so that unavailable behavior is not represented as a live capability.
20. As a Codex agent, I want user-facing analyzer documentation to stop promising refetch diagnosis, so that documentation matches the shipped evidence boundary.
21. As a Codex agent, I want existing retrieval events preserved, so that savings, volume, language, repository, and symbol statistics continue to work.
22. As a Codex agent, I want no session identifier inferred from timestamps or call ordering, so that suppression is not replaced by another weak correlation.
23. As a Codex agent, I want no new session-tracking protocol added by this repair, so that a small evidence correction does not expand Loci's architecture.
24. As a Codex agent, I want historical retrieval logs to remain readable, so that correcting analyzer semantics does not require migration or deletion.
25. As a Codex agent, I want other analyzer findings to retain their current contracts, so that this repair does not silently widen into a general analyzer redesign.
26. As a Codex agent, I want one public stdio MCP scenario to prove the complete change, so that internal green tests cannot hide a disconnected output contract.
27. As a Codex agent, I want the acceptance test to prove both sides of the ten-retrieval boundary, so that the evidence floor cannot drift through an off-by-one error.
28. As a Codex agent, I want the acceptance test to prove denominator fields survive serialization, so that the decision evidence is available outside the storage layer.
29. As a Codex agent, I want the acceptance test to include repeated retrievals without producing `refetch_hotspot`, so that the unsupported recommendation cannot reappear through another output path.
30. As Vik, I want the weekly review to surface only mechanism-backed findings, so that decisions focus on demonstrated improvements rather than telemetry artifacts.

## Implementation Decisions

- The analyzer remains the owner of finding qualification. Callers and the weekly review do not reproduce or compensate for its evidence rules.
- `poor_extraction` retains its current definition of poor savings: aggregate symbol bytes versus aggregate corresponding file bytes for eligible retrievals of one language, with a finding below 50% savings.
- A language requires at least ten eligible retrieval events within the requested window and repository scope before `poor_extraction` can be emitted. Ten matches the analyzer's existing durable-evidence convention for search-selection findings and avoids a second confidence vocabulary.
- The evidence count is evaluated together with the savings threshold. Meeting either condition alone produces no finding.
- An eligible extraction retrieval has a non-empty language classification and a usable positive file-byte contribution. Existing handling of malformed or historical events remains fail-soft and does not manufacture denominator values.
- The `poor_extraction` data contract includes `language`, `get_count`, `symbol_bytes`, `file_bytes`, and `avg_ratio_pct`. Byte totals and percentage come from the same eligible event set.
- Existing analysis-window and canonical repository filtering occur before per-language counts and byte totals are accumulated.
- `poor_extraction` remains medium severity once qualified. This work changes the evidence gate and payload, not the severity taxonomy.
- `refetch_hotspot` is suppressed rather than repaired speculatively. The analyzer emits no finding of that type while retrieval events lack a session boundary.
- The `refetch_hotspot` variant is removed from the public analyzer output schema and from maintained analyzer documentation. Tests that treat it as shipped behavior are replaced by the accepted absence contract.
- Ordinary get events, session-log compatibility, retrieval statistics, and savings calculations remain unchanged. Historical records require no migration.
- No session identifier, context identifier, timeout correlation, call-order heuristic, or replacement refetch detector is introduced.
- The recent explicit search-selection lineage is a separate causal contract and remains unchanged. Its event type is not reused as a generic session boundary.
- Search-miss, search-quality, dead-weight, extraction implementation, ranking, indexing, and graph findings retain their current behavior unless compilation requires the narrow schema update described here.
- The change is complete when the shipped stdio `loci_analyze` response enforces the extraction floor, carries all denominators, and cannot serialize or emit `refetch_hotspot`.

## Testing Decisions

- The sole acceptance seam is the existing stdio MCP boundary for `loci_analyze`. It is the highest shipped boundary and covers analyzer execution, service routing, output-schema validation, serialization, and the response received by Codex.
- One representative test uses an isolated temporary store and controlled retrieval events. It first records nine poorly saving retrievals for one language and verifies the public response contains no `poor_extraction` finding for that language.
- The same scenario records the tenth eligible retrieval, calls the public tool again, and verifies one medium `poor_extraction` finding appears with the exact language, retrieval count, symbol-byte total, file-byte total, and derived savings percentage.
- The scenario includes at least three repeated retrievals of one symbol and verifies that no `refetch_hotspot` finding is returned before or after the extraction floor is met.
- The test inspects the advertised MCP output schema and verifies `refetch_hotspot` is no longer an allowed finding variant while `poor_extraction` remains allowed with its denominator-rich data.
- The scenario exercises the existing analysis-window and repository inputs so the qualifying count is proven to reflect only eligible in-scope events.
- Assertions target observable output and schema behavior, not private helper names or accumulator structure.
- Existing analyzer storage tests are prior art for constructing bounded retrieval histories; existing MCP schema and stdio tests are prior art for invoking the real tool and validating structured responses. Obsolete tests that require a refetch finding are removed or converted into setup for the public absence assertion rather than retained as a second acceptance seam.
- Verification ends when this representative stdio contract test passes. Independent review and broad regression testing remain separate opt-in work.

## Out of Scope

- Adding session, conversation, turn, context-window, or request identity to retrieval events.
- Designing a future session-scoped refetch detector or choosing its evidence thresholds.
- Inferring session boundaries from timestamps, process lifetime, search identifiers, repositories, or call ordering.
- Changing the retrieval journal format except where existing readers must tolerate the absence of the retired finding.
- Migrating, deleting, or rewriting historical session logs.
- Changing symbol extraction, context sizing, parser behavior, or language support.
- Changing the 50% poor-savings threshold or the analyzer's severity vocabulary.
- Repairing or recalibrating search-miss, dead-weight, ranking, blind-spot, graph, or store-health diagnostics.
- Changing explicit search-selection lineage, search scoring, or result ordering.
- Modifying the weekly-review skill to compensate for analyzer behavior.
- Adding a service, database, queue, background job, UI, or general telemetry framework.
- Implementing either repair as part of this specification task.

## Further Notes

- The 2026-08-23 weekly review found that the medium extraction warnings were based on six Go gets and one JavaScript get, while Python, Markdown, and TypeScript had hundreds of retrievals and 83.4% to 93.3% savings. The finding is about evidence qualification, not a conclusion that Go or JavaScript extraction is healthy.
- The same review found 201 globally repeated symbols, but durable get events contained no session identity. Global repetition is valid volume evidence; it is not evidence that a symbol failed to remain in one context.
- Suppression is deliberately reversible. A future spec may restore a refetch finding after a real session boundary exists and live evidence shows the signal is worth its added machinery.
- The accepted test seam keeps the producer-consumer contract executable without adding a parallel internal acceptance suite.
