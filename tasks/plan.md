# Implementation Plan: Loci MCP Harness Store Isolation

## Overview

Replace ambient host guessing with an explicit, persistent MCP store identity,
preserve CLI convenience behavior, and qualify safe same-harness concurrency.

## Architecture Decisions

- MCP startup configuration is immutable and process-owned; tools receive only
  repository paths.
- `LOCI_BASE_DIR` selects the canonical root and `LOCI_STORE_NAMESPACE` selects
  its identity. Matching custom values intentionally share a store.
- A versioned marker prevents accidental cross-namespace reuse. Non-empty
  legacy stores require explicit adoption rather than silent mutation.
- CLI resolution remains backward compatible and separate from MCP bootstrap.
- Direct indexing and freshness refresh share one repository lock.

## Task List

### Phase 1: Store identity foundation

- [x] Task 1: Add validated marker initialization and adoption contracts with
  failing-first unit tests.
- [x] Task 2: Bind MCP startup and wrappers to the explicit identity contract;
  update host registration documentation and fresh-process tests.

### Checkpoint: Isolation

- [x] Missing configuration and namespace mismatch fail closed.
- [x] Codex and Claude examples select distinct stores.
- [x] Focused storage, wrapper, and MCP tests pass.

### Phase 2: Same-harness concurrency

- [x] Task 3: Apply the existing per-repository lock to direct indexing and add
  regression coverage proving refresh does not deadlock.

### Checkpoint: Complete

- [ ] Full tests, type checks, compile, lockfile, package build, and runtime MCP
  smoke checks pass.
- [ ] Five-axis code review finds no unresolved required issues.
- [ ] Manifest evidence is attached and the task is completed.

## Risks and Mitigations

| Risk | Impact | Mitigation |
| --- | --- | --- |
| Existing unmarked store is claimed by the wrong harness | Cross-harness leakage | Refuse non-empty adoption without explicit CLI acknowledgement |
| Two MCP sessions initialize or index concurrently | Corruption or partial reads | Exclusive marker creation, repository lock, atomic replace |
| Config examples drift from real client syntax | Fresh-host failure | Verify installed client help and run stdio process smoke tests |
| Stricter MCP startup breaks human CLI workflows | Operator regression | Keep CLI resolver unchanged and test both modes |

## Open Questions

- None blocking implementation.
