# Implementation Plan: Trustworthy Loci Coverage and Store Lifecycle

## Overview

Make maintained repository code—including tests—fully navigable, make query
coverage explicit, and give each isolated Loci store a fast, diagnosable, and
recoverable lifecycle.

## Architecture Decisions

- Maintained tests and fixtures are source, not index noise.
- One authoritative coverage policy owns indexing, diagnostics, and hook
  enforcement.
- Search and grep state what they covered, including empty results.
- A small atomic catalog serves inventory without parsing every index.
- Health detection is read-only; normal store opens automatically remove only
  entries whose canonical repository roots no longer exist.
- New overlapping roots fail closed with a structured conflict.
- The test harness always selects a temporary namespaced store.
- MCP repository-root naming is normalized through a reviewed migration.

## Task List

### Thread 1: Repository coverage

- [x] Task 1.1: Centralize indexability and restore maintained test coverage.
- [x] Task 1.2: Expose query coverage and honest empty-result semantics.
- [x] Task 1.3: Make Claude enforcement coverage-equivalent.
- [x] Task 1.4: Align definition-time reference and call ownership and restore
  stale-index refresh.

### Thread 2: Store lifecycle

- [x] Task 2.1: Build an atomic repository catalog and fast inventory.
- [x] Task 2.2: Diagnose freshness, dead roots, corruption, and overlaps.
- [x] Task 2.3: Automatically prune dead roots during normal store startup.
- [ ] Task 2.4: Prevent new overlapping repository roots.

### Thread 3: Harness and public contracts

- [ ] Task 3.1: Guarantee test-store isolation.
- [x] Task 3.2: Normalize MCP repository-root parameters.
- [ ] Task 3.3: Qualify the complete trust contract.

## Checkpoints

- [x] Coverage: maintained tests are discoverable and empty results are honest.
- [x] Store: catalog recovery, health diagnosis, and startup dead-root cleanup
  pass focused disposable-store proofs.
- [ ] Integration: hook, cleanup, overlap, isolation, and MCP migration pass
  focused end-to-end proofs.

## Risks and Mitigations

| Risk | Impact | Mitigation |
| --- | --- | --- |
| Test indexing grows stores | Medium | Measure the real delta; optimize representation instead of deleting maintained code |
| Catalog/index interruption | High | Atomic protocol and deterministic repair |
| Prune removes unavailable work | High | Read-only detection plus exact reviewed apply targets |
| MCP aliases preserve confusion | High | One canonical contract with tested migration |
| Hook redirects beyond coverage | High | Shared policy and repository-root regression cases |

## Open Questions

- Age- or size-based eviction remains out of scope until store evidence justifies
  a retention policy beyond dead-root pruning.

## Governing Artifact

`docs/plans/2026-07-30-loci-trustworthy-coverage-and-store-lifecycle.md`
