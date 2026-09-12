# Pre-measurement verification

Verified on 12 September 2026 before any v2 provider call.

- All 18 new observed-accounting, replay and runner tests pass.
- Pyright reports zero errors or warnings across all five v2 modules and the three new test files.
- All 17 original corpus cases pass endpoint preflight.
- Ten actual Codex/MCP loopback modes pass with zero provider calls: the original eight modes plus graph anchors and graph neighbors.
- The actual A/B tool-schema hashes exactly match the immutable v1 preparation. The common thirteen tool schemas are identical between arms.
- The original v1 freeze remains valid and the shared runtime source still matches pinned engine `36f5e2b1662c2d6bbe2449c3189430469e8c013f`, extractor 25.
- The new runner injects corrected v2 measurement through the original attempt lifecycle. Independent replay must finish before a qualified report or completion marker; a replay exception leaves the verdict inconclusive.
- Recomputed artifacts must identify measurement protocol v2. Raw adapter traces remain on the unchanged v1 protocol.

The graph regression checks cover all eight public graph operation names, rejection of a tampered ledger operation, and real mixed exact-get/exploration/helper accounting. Actual offline transport proves the two graph paths implicated in the invalid v1 measurement. These checks do not replace the frozen 102-attempt trial or predict its verdict.

The original v1 trial remains preserved as aborted and inconclusive. No original code, raw artifact or score was changed, and no measured outcome was used to alter prompts, task gold, source policy or acceptance thresholds.
