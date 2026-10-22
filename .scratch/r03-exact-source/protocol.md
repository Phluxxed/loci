# R0.3 frozen deterministic comparison

Question: can generation-bound exact-source metadata avoid full semantic graph
reconstruction for an already identified extent without changing source delivery
or source-access rejection? This is an experimental branch, not an integration.

- Control: `4cadfe1a233b9ec34b8ef25244d163d64297a8f4`.
- Candidate: `a38e17d1456581786e950b892b2cd49684c08229`.
- Observer: the subsequent committed direct-read extension of the existing
  `benchmarks.architecture` runner; its revision and exact sources are retained
  automatically in every result.
- Mechanism: validated, generation-bound source projection versus ordinary full
  semantic reconstruction in `service.read`. Both retain graph compilation,
  storage, full repository freshness and enrichment enabled. Neither is graph-free.
- No model calls, arbitrary resource cutoffs or composite scores.

Run three serial comparisons with two fresh repetitions each, alternating
control/variant order. Each arm gets its own implementation worktree, fixture
export, store root/namespace, process, cache and output. Every input file is checked
before and after execution. Independent scoring uses frozen source bytes, not
candidate index claims.

1. Maintained TypeScript v3 Anvil snapshot, selected case
   `anvil_retrieval_limits`, whole `anvil:src/brain-context/render.ts`.
2. Deterministic small suite built by `architecture_reads.build_small_suite`,
   whole `imported_interface:unicode.md`, `go.mod`, `Cargo.toml`, `jsconfig.json`.
3. The same small suite and whole `unicode.md`, plus fixed foreign/extent/hash/
   unindexed/malformed/UTF-8/stale/stale-with-refresh/outside-symlink probes.

Each read process starts after indexing in a separate process: first call is
process-cold (OS cache coldness is not claimed), followed by the repeated first
page, no-refresh diagnostic and all continuation pages. Ordinary first/repeat/
continuation calls use `ensure_fresh=True`. Mutations occur only in owned small
exports, are restored, and include refresh/restoration costs. Report per-phase
wall, CPU, process high-water memory, output bytes, indexing work and observed
service calls. Nested diagnostic timings are not added to operation totals.
Separate index + read process resources and total operation costs remain visible.

Acceptance: every delivered byte/span/hash/line/UTF-8 boundary/page/output-size
check passes; repeated/no-refresh pages agree; both arms agree after normalizing
only root-bound opaque handles and repository paths in error details. Required
negative errors have the same codes and details. Independent artifact replay
passes, owned cleanup succeeds, and both main working states remain byte-identical
to preservation-before.json. No latency superiority threshold is imposed.

Known five semantic proof-support discrepancies from R0 remain unresolved and
visible as separate historical evidence. The semantic scorer is unchanged and no
passing full-corpus retrieval result will be claimed from direct reads. This
comparison establishes source access only, not relationship proof or agent task
correctness. Focused source projection tests additionally cover corrupt/missing/
forged projections, missing/altered root anchors, legacy fallback and refresh locks.

Resource claims are descriptive for these fixed fixtures and this host. A passing
comparison may justify a separate integration decision, but does not authorize it.
