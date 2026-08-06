# Spec and Plan: Trustworthy Repository Coverage and Store Lifecycle

## Objective

Make Loci trustworthy about both the repository content it can answer from and
the lifecycle of the indexes it retains.

Maintained test code and fixtures are repository source and must be navigable
like production code. Loci may exclude generated, vendored, cached, build,
temporary, ignored, or explicitly throwaway material, but it must never turn a
coverage exclusion into a confident-looking repository-wide miss.

The store must maintain a cheap, current inventory; detect missing repositories,
stale or corrupt indexes, and overlapping roots; and automatically clean up
only derived entries whose canonical repository roots no longer exist when the
store opens for normal use. Cleanup is deterministic, recoverable, and never
touches repository/source roots.

## Accepted Decisions

- Index maintained tests, test helpers, and maintained fixtures.
- Centralize the definition of indexable repository content so the indexer,
  read tools, diagnostics, and enforcement hooks cannot drift.
- Preserve explicit coverage information on search and grep results, including
  empty results.
- Treat missing repository roots, stale or corrupt indexes, and overlapping
  roots as first-class store health findings.
- Keep normal inventory reads independent of full `index.json` parsing.
- Make normal store startup perform deterministic per-entry dead-root cleanup
  under the existing catalog mutation protocol; record only bounded removal
  count/byte diagnostics. No manual, dry-run, apply, age, size, stale, corrupt,
  overlap, or indexability pruning is part of this contract.
- Reject new overlapping roots in one store unless a later approved use case
  earns an explicit exception contract.
- Guarantee test processes cannot write into an operator store by default.
- Normalize MCP repository-root parameter naming and update all first-party
  consumers through one reviewed migration.
- Use the same nearest-named-executable-body ownership contract for Python
  imported references and calls. Decorators, annotations, defaults, and other
  definition-time expressions belong to their enclosing executable scope, or
  the file node at repository top level; they never inherit the callable they
  define.

## Commands

```bash
# Focused tests during implementation
.venv/bin/python -m pytest -q tests/test_service.py
.venv/bin/python -m pytest -q tests/test_mcp_server.py
.venv/bin/python -m pytest -q tests/test_enforce_read_hook.py
.venv/bin/python -m pytest -q tests/storage

# Static/runtime qualification for changed Python
.venv/bin/python -m compileall -q src tests
.venv/bin/python -m pytest -q <focused test targets>

# Packaging verification when public MCP/CLI surfaces change
.venv/bin/python -m build
```

Repository-wide verification is not a default. It requires a demonstrated risk
that focused proofs cannot cover and Vik's explicit approval.

## Project Structure

- `src/loci/service.py` — repository scanning, freshness, and service contracts.
- `src/loci/storage/` — store identity, catalog, health, and cleanup mechanics.
- `src/loci/mcp_server.py` — typed MCP boundary and public tool schemas.
- `src/loci/cli.py` — human maintenance commands where retained.
- `.claude/hooks/` — Claude enforcement consumers of Loci's authoritative
  coverage and tool contracts.
- `tests/` — unit, service, MCP, hook, and store lifecycle regression tests.
- `docs/` and `skills/loci/` — operator and agent-facing contracts.

## Code Style

Use small typed domain values and structured outcomes at boundaries:

```python
@dataclass(frozen=True)
class RepositoryHealth:
    repo: str
    state: Literal["healthy", "stale", "missing", "corrupt", "overlapping"]
    reasons: tuple[str, ...]
```

Do not encode health or coverage as an empty list, `None`, timing behavior, or
free-form warning text when a typed result can state it directly.

## Testing Strategy

- Add failing regression tests before each behavior change.
- Prove maintained test files are indexed and returned by outline, search, grep,
  file, and get where applicable.
- Prove excluded material remains excluded and every query reports the relevant
  coverage boundary.
- Use temporary, explicitly named stores for all tests and subprocesses.
- Exercise catalog updates, interrupted writes, missing roots, corruption,
  overlaps, automatic startup cleanup, pending-mutation recovery, and
  post-cleanup integrity.
- Contract-test MCP schemas and first-party guidance rather than checking only
  that a tool name appears in an error message.
- Measure `loci list` against store size so its cost cannot regress to parsing
  all repository indexes.

## Boundaries

### Always

- Treat current repository files and focused tests as authoritative evidence.
- Keep store metadata writes atomic and recoverable.
- Return machine-readable coverage and health state.
- Preserve healthy and source repositories; automatic cleanup may remove only a
  derived index/cache directory and its catalog entry when the canonical root
  is missing.
- Update first-party hooks, docs, and skills with public MCP contract changes.

### Ask First

- Add a new dependency.
- Permit overlapping roots in one store.
- Change the store identity or namespace model.
- Run repository-wide qualification.

### Never

- Exclude maintained tests merely because they are tests.
- Represent excluded coverage as a definitive repository-wide absence.
- Delete a store entry during list, search, freshness refresh, or doctor reads.
- Auto-select which side of an overlap to keep.
- Let tests resolve to a real operator store.

## Success Criteria

- A symbol added under `tests/` is discoverable through Loci without native
  grep or whole-file reads.
- Index exclusions are limited to generated/cache/vendor/build/temporary,
  ignored, or explicitly configured throwaway material.
- Search and grep results state their coverage; empty results cannot be
  mistaken for a complete repository-wide absence when exclusions apply.
- Hook enforcement only redirects an operation when Loci can answer an
  equivalent query and its guidance matches the live MCP schemas.
- Repository inventory does not parse every `index.json`.
- Store health identifies missing roots, stale/corrupt entries, and overlaps
  with bounded evidence.
- Normal store startup deterministically removes only entries whose canonical
  roots are missing, leaves healthy entries and source repositories untouched,
  and records bounded removed-count/removed-byte diagnostics.
- New overlapping roots fail with a structured conflict naming the existing
  root and a safe operator action.
- The full test harness is isolated from Codex, Claude, and legacy stores.
- MCP repository parameters use one predictable contract, with first-party
  consumers migrated and compatibility handled deliberately.

## Open Questions

- The initial prune policy removes only entries whose canonical repository root
  no longer exists. Age- or size-based retention is intentionally outside the
  accepted scope until real store evidence justifies it.
- Maintained fixture data is indexed when it has a supported source/document
  type and is not ignored or generated. A later need for fixture-specific
  policy must be evidence-backed.

## Implementation Plan

<a id="coverage-thread"></a>
### Thread 1: Make repository coverage complete and explicit

Deliver one authoritative indexability contract, restore maintained test
coverage, and make every query and enforcement decision honest about what Loci
can answer.

<a id="coverage-policy-task"></a>
#### Task 1.1: Centralize indexability and restore maintained test coverage

Remove test-directory and test-filename exclusions, centralize the remaining
path policy, and prove maintained tests and fixtures enter the index while
generated/cache/vendor/build/temp/ignored material does not.

Acceptance:

- Maintained test symbols appear in index, outline, search, grep, file, and get
  proofs where supported.
- One authoritative policy owns indexer and consumer decisions.
- Existing legitimate exclusions retain focused regression coverage.

Verification:

- Focused service, CLI, and repository-scan regression tests.

<a id="coverage-results-task"></a>
#### Task 1.2: Expose query coverage and honest empty-result semantics

Add a stable typed coverage envelope to repository search/grep results and any
shared service result needed to prevent excluded content from looking absent.

Acceptance:

- Empty and non-empty results carry predictable coverage state.
- Exclusions and incompleteness are machine-readable and bounded.
- Existing consumers receive a deliberate compatibility treatment.

Verification:

- Focused service and MCP contract tests for complete and incomplete coverage.

<a id="coverage-hook-task"></a>
#### Task 1.3: Make Claude enforcement coverage-equivalent

Replace the hook's duplicated path policy and hand-written tool recipes with
authoritative coverage and schema contracts, and remove full-store work from
the gated hot path.

Acceptance:

- The hook never blocks a native read/search unless the recommended Loci call
  can answer the same content scope.
- Guidance uses the exact live MCP argument shapes.
- Gated latency is independent of aggregate `index.json` bytes.

Verification:

- Focused hook contract tests including `tests/`, repository-root grep, invalid
  guidance prevention, unreachable Loci, and nested repositories.

<a id="definition-time-owner-task"></a>
#### Task 1.4: Align definition-time reference and call ownership and restore refresh

Correct the imported-reference owner projection so it uses the same
nearest-named-executable-body contract already applied to call records. This
is a blocking correction exposed when maintained decorated tests entered the
index: current-source stale refresh otherwise creates call/reference records
that cannot satisfy graph validation.

Acceptance:

- Decorator, annotation, default-argument, and other definition-time imported
  references use their enclosing executable or file node, matching call
  ownership.
- Graph validation remains strict and accepts the resulting unique
  call/reference evidence without dropping or weakening records.
- A stale read can refresh a current Loci checkout in an isolated store.

Verification:

- Focused Python reference-owner and call-materialization regression tests.
- One disposable-store stale-refresh proof using current source.

<a id="store-thread"></a>
### Thread 2: Make store inventory and lifecycle healthy

Give the store a cheap authoritative catalog, bounded health diagnosis,
recoverable cleanup, and safe overlap prevention.

<a id="store-catalog-task"></a>
#### Task 2.1: Build an atomic repository catalog and fast inventory

Persist the small metadata needed to list repositories without loading their
full indexes, and rebuild or repair the catalog deterministically when needed.

Acceptance:

- `list` cost scales with catalog entries, not index bytes.
- Index write/invalidate and catalog state cannot silently diverge.
- Legacy stores gain a bounded repair path.

Verification:

- Focused catalog atomicity, recovery, compatibility, and performance tests.

<a id="store-health-task"></a>
#### Task 2.2: Diagnose freshness, dead roots, corruption, and overlaps

Define one bounded store health projection that distinguishes repository
content freshness from store-entry liveness and structural conflicts.

Acceptance:

- Health reports healthy, stale, missing, corrupt, and overlapping states with
  exact reasons.
- Reads never delete or silently rewrite findings.
- Diagnostics remain bounded for large stores.

Verification:

- Focused health fixtures for every state and mixed-store pagination/bounds.

<a id="store-prune-task"></a>
#### Task 2.3: Automatically prune dead roots during normal store startup

When the store opens for normal use, process catalog entries in deterministic
order. For each entry, perform one canonical-root existence check; keep it when
present, otherwise remove only its derived index/cache directory and catalog
entry using the existing mutation/recovery protocol. Repositories and source
roots are never touched, and no daemon or manual/dry-run/apply interface is
introduced.

Acceptance:

- Missing roots remove exactly one derived cache directory and catalog entry;
  healthy roots remain unchanged.
- Cleanup is deterministic, per-entry recoverable, and cannot collide with a
  pending catalog write/invalidate mutation.
- A bounded diagnostic summary records removed count and bytes; age, size,
  stale, corrupt, overlap, and indexability policies remain out of scope.
- Post-cleanup catalog and store integrity are verified.

Verification:

- Focused disposable-store startup, preservation, summary, and
  pending-mutation recovery tests.

<a id="store-overlap-task"></a>
#### Task 2.4: Prevent new overlapping repository roots

Reject ancestor/descendant root duplication before indexing and provide
diagnostics that let operators deliberately clean existing overlaps.

Acceptance:

- New overlaps return a structured conflict naming both roots.
- Exact-root reindex remains valid.
- Existing overlaps are diagnosed without automatic winner selection.

Verification:

- Focused ancestor, descendant, exact-root, sibling, symlink, and worktree
  cases.

<a id="integration-thread"></a>
### Thread 3: Make harness and public contracts hard to misuse

Remove ambient test-store risk and normalize the repository-root contract
across MCP tools and first-party consumers.

<a id="test-isolation-task"></a>
#### Task 3.1: Guarantee test-store isolation

Establish a suite-wide temporary store boundary inherited by in-process and
subprocess tests, while allowing explicit resolver tests to override it safely.

Acceptance:

- No test can resolve Codex, Claude, or legacy operator stores by default.
- Subprocess and MCP tests inherit an explicit test namespace.
- Resolver tests prove their intentional override without leaking state.

Verification:

- Focused isolation sentinel tests plus bounded subprocess proofs.

<a id="mcp-contract-task"></a>
#### Task 3.2: Normalize MCP repository-root parameters

Define one predictable repository-root name across MCP tools, choose and test
the compatibility strategy, and update hooks, skills, docs, and examples.

Acceptance:

- Repository-scoped MCP tools expose a consistent root parameter.
- Invalid duplicate aliases cannot appear in first-party guidance.
- Migration behavior is contract-tested and documented.

Verification:

- Focused MCP schema snapshots and installed stdio smoke checks.

<a id="qualification-task"></a>
#### Task 3.3: Qualify the complete trust contract

Prove the combined coverage, store lifecycle, isolation, performance, and
public-interface outcomes against purpose-built disposable repositories and
stores.

Acceptance:

- Every Objective success criterion has bounded evidence.
- No unresolved required review finding remains.
- Any proposed broad verification is separately justified and approved.

Verification:

- Focused end-to-end MCP, hook, and store lifecycle scenarios; approved wider
  checks only if a named residual risk requires them.

## Dependency Order

- Task 1.1 blocks Tasks 1.2 and 1.3.
- Task 1.2 blocks Task 1.3.
- Task 1.4 blocks remaining delivery while current-source stale refresh cannot
  satisfy the call/reference ownership invariant.
- Task 2.1 blocks Tasks 2.2, 2.3, and 2.4.
- Task 2.2 blocks Tasks 2.3 and 2.4.
- Task 3.1 can proceed independently after the plan is accepted.
- Task 3.2 blocks Task 1.3.
- All delivery tasks block Task 3.3.

## Risks and Mitigations

| Risk | Impact | Mitigation |
| --- | --- | --- |
| Test indexing materially increases store size | Medium | Measure real delta; optimize representation rather than deleting maintained code |
| Catalog and index commit diverge after interruption | High | Atomic write protocol plus deterministic repair |
| Compatibility aliases preserve confusing MCP schemas | High | Contract-first migration with one canonical public name |
| Prune removes a temporarily unavailable repository | High | Missing-root finding is read-only; apply requires exact reviewed targets |
| Overlap rejection blocks a legitimate workflow | Medium | Report the conflict; require an evidence-backed exception design rather than guessing |
| Hook enforcement overclaims equivalence | High | Shared coverage contract and explicit root-scope regression cases |

## Checkpoints

### Coverage checkpoint

- Tasks 1.1 and 1.2 complete with focused service/MCP proof.
- Review the coverage envelope before changing enforcement behavior.

### Store checkpoint

- Tasks 2.1 and 2.2 complete with catalog recovery and health fixtures.
- Review startup cleanup and pending-mutation recovery evidence before final
  qualification.

### Integration checkpoint

- Tasks 1.3, 2.3, 2.4, 3.1, and 3.2 complete with focused proofs.
- Review residual risks before final qualification.
