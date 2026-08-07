# Trustworthy Loci Coverage and Store Lifecycle

- [x] Task 1.1: Centralize indexability and restore maintained test coverage.
  - Acceptance: maintained tests and fixtures are indexed; only generated,
    cache, vendor, build, temporary, ignored, or explicitly throwaway material
    is excluded.
  - Verify: focused service, CLI, and scan-policy tests.

- [x] Task 1.2: Expose query coverage and honest empty-result semantics.
  - Acceptance: empty and non-empty search/grep outcomes carry typed coverage.
  - Verify: focused service and MCP contract tests.

- [x] Task 1.3: Make Claude enforcement coverage-equivalent.
  - Acceptance: redirects are answer-equivalent, schema-correct, and independent
    of aggregate index bytes.
  - Verify: focused hook tests for tests/, root grep, nested roots, and fallback.

- [x] Task 1.4: Align definition-time reference and call ownership and restore
  stale-index refresh.
  - Acceptance: decorators, annotations, defaults, and other definition-time
    expressions use the enclosing executable/file owner consistently across
    imported references and calls; current-source refresh satisfies graph
    validation without weakening the invariant.
  - Verify: focused reference-owner and call-materialization regressions plus
    one disposable-store stale-refresh proof.

- [x] Task 1.5: Make ambiguous reference evidence non-fatal during stale
  refresh.
  - Acceptance: ambiguous reference sources remain explicitly
    ambiguous/unresolved instead of being treated as resolved or aborting the
    refresh; uniquely resolved relationships and strict validation remain
    unchanged.
  - Verify: a focused regression for the current ambiguous-reference shape and
    one isolated-store stale-refresh proof using the current Loci checkout.
  - Complete: unresolved unindexed-owner references retain their explicit
    reason without aborting refresh; resolved ambiguity remains rejected. The
    focused regression and existing equal-span ambiguity guard both pass.

- [x] Task 2.1: Build an atomic repository catalog and fast inventory.
  - Acceptance: list cost scales with catalog entries and legacy repair is
    deterministic.
  - Verify: focused atomicity, recovery, compatibility, and performance tests.

- [x] Task 2.2: Diagnose freshness, dead roots, corruption, and overlaps.
  - Acceptance: bounded typed health findings with no mutation during reads.
  - Verify: focused mixed-store health fixtures.

- [x] Task 2.3: Automatically prune dead roots during normal store startup.
  - Acceptance: deterministic per-entry cleanup removes only derived cache
    directories and catalog entries whose canonical roots are missing; healthy
    roots and source repositories remain untouched, with bounded removal
    diagnostics and pending-mutation recovery.
  - Verify: focused disposable-store startup, preservation, summary, and
    pending-mutation tests.

- [x] Task 2.4: Prevent new overlapping repository roots.
  - Acceptance: structured conflicts for ancestor/descendant roots; exact-root
    reindex and sibling roots remain valid.
  - Verify: focused path, symlink, and worktree overlap tests.

- [x] Task 3.1: Guarantee test-store isolation.
  - Acceptance: in-process and subprocess tests cannot resolve operator stores.
  - Verify: focused isolation sentinels and subprocess proofs.

- [x] Task 3.2: Normalize MCP repository-root parameters.
  - Acceptance: one canonical root name, deliberate compatibility, and updated
    first-party guidance.
  - Verify: focused schema snapshots and installed stdio smoke.

- [ ] Task 3.3: Qualify the complete trust contract.
  - Acceptance: every Objective criterion has bounded evidence and no required
    review finding remains.
  - Verify: focused end-to-end coverage, store, hook, and MCP scenarios; wider
    checks only with separate approval.
