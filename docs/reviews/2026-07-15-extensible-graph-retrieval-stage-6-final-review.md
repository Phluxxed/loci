# Extensible Graph Retrieval Stage 6 Final Review

**Status:** Pending owner approval

**Recommendation:** Accept

**Review date:** 2026-07-15

**Repository:** `/Users/brummerv/loci`

**Implementation baseline:** `79c7b155c4bb82ca4d6237fac4135bfc66996009`

**Reviewed implementation head:** `b17adba74b2b8b026a575135c923ccedeb024e0a`

**Canonical plan:** [Extensible Graph Retrieval Stage 6](../plans/2026-07-14-extensible-graph-retrieval-stage-6.md)

## Decision requested

Approve Stage 6 as shipped through `b17adba74b2b8b026a575135c923ccedeb024e0a`.

The review found no critical or required changes. The implementation meets the
approved Stage 6 contract: Loci extracts and persists import observations,
resolves the deliberately supported Python and JavaScript/TypeScript subset,
materializes only evidence-backed file dependency edges, exposes bounded import
records, and includes trusted resolved imports in opt-in graph traversal. Existing
exact-navigation and graph-extension behavior remains compatible.

Approval closes Stage 6. It does **not** authorize resolved-reference or call-graph
work; either capability requires its own design and review boundary.

## Scope under review

The review covers the following 14 commits after the approved pre-Stage-6
baseline:

| Commit | Change |
| --- | --- |
| `73f780da355e82d0d8ac668991b72cd1de58fa66` | `docs: approve Stage 6 import graph plan` |
| `cb198e65d837b4294ddd603b8d0f492f4d14e0d3` | `feat: add Stage 6 import graph contracts` |
| `f49da4cbf2ef4e9ef8cbf214be5c287c86be1793` | `feat: configure import syntax nodes` |
| `af3267ecf5a9de9a5471899b1f7d261fe26afe38` | `feat: extract raw import observations` |
| `b2a161c12c57a032425f02feb68e8e2cefc02683` | `feat: resolve Python import observations` |
| `d9243e57fd235a1a4106ddbb9dd5c43461224f68` | `feat: materialize Python import edges` |
| `fa593398ddb7a8931c1b6366fd4f3a02c86b1080` | `feat: resolve JavaScript and TypeScript imports` |
| `0ead068c54355d7195913a11ad63a7ed2235f854` | `feat: integrate import graph indexing` |
| `008c1c96c3362a2edc96f61c02460dff7d40fb27` | `feat: harden built-in import edge validation` |
| `137f4ffb5577b80e113e1d680d009c45c2fe4514` | `test: prove import graph persistence and freshness` |
| `263d5ef16f9dcd1c2952a750dfd3f27c4d8e0cf2` | `feat: expose bounded import records` |
| `721cd57036143961b0099205be0f1cfb4eb05b14` | `feat: expose import records through MCP` |
| `2c52de546bbfeb8b86fd6454d423f348cd51225d` | `feat: trust resolved imports in graph traversal` |
| `b17adba74b2b8b026a575135c923ccedeb024e0a` | `docs: document import-aware graph retrieval` |

The baseline-to-head diff contains 29 changed files, 5,156 insertions, and 213
deletions. It does not change project dependencies or lockfile resolution.

## Verification summary

All checks were run against the reviewed implementation head unless noted.

| Check | Result |
| --- | --- |
| Focused Stage 6 and graph regression suite | 262 passed in 12.01 seconds |
| Full Loci test suite | 475 passed in 38.58 seconds |
| `llm-wiki` Loci graph-provider compatibility suite | 14 passed in 0.78 seconds |
| Source and test bytecode compilation | Passed |
| Source distribution and wheel build | Passed |
| Baseline-to-head `git diff --check` | Passed |
| Baseline-to-head secret-pattern scan | Passed |
| Frozen benchmark checksum | Unchanged |
| Isolated installed-wrapper MCP review | Passed |

The focused suite command was:

```text
.venv/bin/python -m pytest \
  tests/parser/test_imports.py \
  tests/graph/test_imports.py \
  tests/graph/test_state.py \
  tests/graph/test_contracts.py \
  tests/graph/test_materialize.py \
  tests/graph/test_traversal.py \
  tests/storage/test_index_store.py \
  tests/test_service.py \
  tests/test_mcp_server.py \
  tests/test_wrapper_routing.py -q
```

The full suite command was:

```text
.venv/bin/python -m pytest tests/ -q
```

Packaging and compilation were checked with:

```text
uv build
.venv/bin/python -m compileall -q src tests
```

The frozen benchmark remains at:

```text
/Users/brummerv/llm-wiki/tests/fixtures/graph_shape_traversal_stage3.json
SHA-256: c52def1bdf592ad735149d199910f74183598eccd9ccf8064335fa0cd0e84e27
```

The benchmark itself was not rerun. The approved plan reserves a rerun for a
focused regression signal; none appeared. Its checksum is unchanged, Loci's full
suite passed, and `llm-wiki`'s compatibility provider still explicitly requests
declared-resolution graph data.

## Schema and migration review

Stage 6 changes persisted extraction and graph-state data without changing the
public contribution contract:

| Contract | Before | After | Review result |
| --- | ---: | ---: | --- |
| Index storage schema | 5 | 5 | No storage-envelope migration required |
| Extractor version | 4 | 5 | Forces old extraction metadata to reindex |
| Public graph contribution schema | 1 | 1 | Extension authors remain compatible |
| Persisted graph-state envelope | 1 | 2 | Old graph state is rejected and rebuilt |

Migration and freshness behavior is covered by tests that prove:

- graph-state schema version 1 is stale rather than silently accepted;
- a service open upgrades and rebuilds stale graph state;
- incremental indexing reprocesses old extractor-version metadata;
- unchanged raw import observations can be retained while resolution is rerun
  against the complete current file set;
- added and deleted targets change import resolution on the next incremental run.

There is no manual data migration. Opening or incrementally indexing an old cache
causes the affected derived data to be rebuilt from repository source.

## Isolated real-MCP review

The acceptance harness launched the installed wrapper at
`/Users/brummerv/.local/bin/loci-mcp` in fresh processes with an isolated cache.
It indexed a temporary purpose-built repository containing Python,
JavaScript/TypeScript, Go, and Rust examples. This validated the actual stdio MCP
boundary rather than calling service functions in-process.

### Purpose-built repository result

| Measure | Result |
| --- | ---: |
| Symbols | 20 |
| File nodes | 12 |
| Graph edges | 5 |
| Import records | 11 |
| Resolved imports | 5 |
| Unresolved imports | 6 |
| Graph status | Healthy |

`loci_graph_imports` was present in the advertised tool list. Pagination with
`limit=3` returned offsets `0`, `3`, `6`, and `9`, and the combined pages returned
exactly the 11 records reported by the index.

### Traversal transcript

The following outcomes were observed through fresh MCP processes:

- Outgoing traversal from `pyapp/main.py` reached `pyapp/helper.py` and
  `pyapp/shared.py` using forward `dependency` edges in the `import` namespace
  with `import-resolved` resolution.
- Incoming traversal from `pyapp/helper.py` returned the stored
  `pyapp/main.py -> pyapp/helper.py` edge while marking traversal as reverse.
- A bounded path returned `support_kind=edge_sequence` and exact line-1 evidence
  containing `from . import helper`.
- Default traversal resolutions were exactly `exact`, `declared`, and
  `import-resolved`; heuristic edges were absent.
- The legacy `loci_graph_neighbors` compatibility call returned no dependency
  edges. It remains an exact, contains-only read rather than silently widening
  when import edges exist.
- Normal search found `pyapp/main.py::entry#function`; outline returned the
  expected file and function entries; exact get returned the function source.

### Honest unresolved behavior

The six unresolved records remained bounded and inspectable:

| Reason | Count |
| --- | ---: |
| `external` | 1 |
| `not_indexed` | 2 |
| `unsupported_language` | 3 |

A same-name collision remained `unresolved/not_indexed` with no invented target.
Go and Rust observations remained `unsupported_language`, and neither produced a
dependency edge. No heuristic edge was materialized anywhere in the fixture.

### Incremental target changes

An initially missing relative target produced an unresolved record. After the
target file was added, incremental indexing skipped all 12 unchanged source files
and changed the record to resolved with target `late_target.py` and resolution
`import-resolved`. After deletion, another incremental run again skipped the 12
unchanged sources and returned the record to `unresolved/not_indexed` with no
target. This is the required whole-repository re-resolution behavior.

## Determinism and incremental evidence

The purpose-built repository produced the same persisted graph-state digest for
all three relevant paths:

```text
Full index:                 71ac980e5b1deadab4000544ebdc3c0f1f6fc26a8c84472b8d1fb012aba6e5b5
Fresh MCP process reload:   71ac980e5b1deadab4000544ebdc3c0f1f6fc26a8c84472b8d1fb012aba6e5b5
No-change incremental run:  71ac980e5b1deadab4000544ebdc3c0f1f6fc26a8c84472b8d1fb012aba6e5b5
```

The no-change incremental run skipped all 12 files and retained all 11 import
records. This confirms stable serialization, persistence, reload, and reuse.

## Loci self-index and performance

The isolated installed-wrapper review also indexed Loci itself:

| Measure | Full index | No-change incremental |
| --- | ---: | ---: |
| Wall time | 1.299 seconds | 1.156 seconds |
| Symbols | 1,116 | 1,116 |
| File nodes | 27 | 27 |
| Graph edges | 611 | 611 |
| Import records | 322 | 322 |
| Resolved imports | 147 | 147 |
| Unresolved imports | 175 | 175 |
| Files skipped | — | 55 |
| Graph status | Healthy | Healthy |

The self-index exposed an outgoing import dependency from
`src/loci/mcp_server.py` to `src/loci/service.py`. Incoming traversal to
`src/loci/service.py` found four evidence-backed source files:

- `src/loci/graph_anchor_stage3.py`
- `src/loci/graph_traversal_stage4.py`
- `src/loci/cli.py`
- `src/loci/mcp_server.py`

A separate five-run local comparison indexed the same current source tree with
the baseline implementation and the reviewed implementation:

| Implementation | Median | Minimum | Maximum | Symbols | Edges |
| --- | ---: | ---: | ---: | ---: | ---: |
| Baseline `79c7b15` | 1.206 s | 1.136 s | 1.262 s | 1,089 | 563 |
| Reviewed `b17adba` | 1.286 s | 1.249 s | 1.344 s | 1,116 | 611 |

The observed median increase was 0.080 seconds, or approximately 6.7%, while the
reviewed implementation added 27 file nodes and 48 graph edges on that source
tree. These are local wall-clock measurements rather than a stable performance
benchmark, but they show no material indexing regression and provide a recorded
Stage 6 reference point.

## Compatibility review

The implementation preserves the existing boundary in the following ways:

- `search`, `outline`, and exact `get` passed both automated and isolated-MCP
  checks.
- `loci_graph_neighbors` remains exact and contains-only.
- Import edges are added to the opt-in traversal APIs under the existing
  `dependency` edge type, `import` namespace, and new trusted
  `import-resolved` resolution.
- Default traversal includes `import-resolved` but still excludes `heuristic`.
- Profile and contribution loading, validation, freshness, and materialization
  tests pass, including the `llm-wiki` extension fixture.
- `llm-wiki` continues to pass explicit namespaces, edge types, and
  `resolutions=["declared"]`; its targeted provider suite passed.
- Markdown parsing remains profile-driven and does not infer duplicate
  relationships from ordinary document content.
- Public method signatures used by existing callers remain compatible, and no
  new runtime dependency was introduced.

## Five-axis review

### Correctness

No blocking defect found. Extraction, resolution, materialization, persistence,
freshness, bounded querying, traversal direction, and exact evidence are covered
by focused tests and an isolated MCP transcript. Unsupported and ambiguous cases
remain explicit unresolved records rather than guessed edges.

### Readability and maintainability

Language-specific extraction and resolution live in dedicated modules
(`parser/imports.py` and `graph/imports.py`). The MCP layer remains thin. Existing
large orchestration and storage modules received boundary integration rather than
absorbing the resolver implementation. Contracts name provenance and resolution
semantics explicitly.

### Architecture

The feature respects the approved pipeline:

```text
syntax observation -> persisted raw record -> deterministic resolver
-> validated built-in contribution -> materialized graph edge -> opt-in traversal
```

Raw observations remain separate from resolved edges, allowing incremental runs
to reuse parsing while resolving against the current repository snapshot. Built-in
import relationships pass through the same graph-state validation and traversal
contracts as other trusted graph data without masquerading as extension-provided
declared relationships.

### Security and trust

Repository-relative path normalization, source/hash matching, endpoint-kind
checks, evidence-line validation, exact resolution policies, and bounded query
limits are enforced. Symlink and path-boundary protections in the existing graph
extension stack remain covered. The resolver does not execute repository code,
load packages, invoke language toolchains, or access the network.

### Performance

No material regression found. The implementation avoids reparsing unchanged files,
re-resolves the compact observation set when repository membership changes, and
keeps result queries bounded. Current local evidence is recorded above so future
stages can detect drift.

## Findings, risks, and deviations

### Findings

- **Critical:** None.
- **Required:** None.
- **Suggestions:** None required for Stage 6 acceptance.

### Accepted limits

- Go and Rust are extract-only in this stage and deliberately remain unresolved.
- JavaScript and TypeScript resolution is limited to deterministic relative
  specifiers and the approved extension/index candidates.
- Python resolution does not emulate an environment, installed distribution,
  namespace-package configuration, or arbitrary import hooks.
- Resolved symbol references and call relationships remain deferred.
- A long-lived MCP host started before installation may require a restart before
  advertising the new `loci_graph_imports` tool. A fresh installed-wrapper process
  advertised and executed it successfully.

### Deviations from the approved plan

None. The frozen benchmark was checksum-verified but not rerun, exactly as allowed
by the plan when the focused regression gates remain green. The isolated review
harness was intentionally ephemeral; permanent behavior coverage lives in the
automated test suite, while this document preserves its acceptance evidence.

## Rollback

If owner review uncovers a Stage 6 blocker, do not edit cached graph data by hand.
Revert the Stage 6 implementation commits as a unit, reinstall Loci, and run a
fresh or incremental index. Extractor-version and graph-state checks will rebuild
derived cache state under the reverted contracts. The pre-Stage-6 exact navigation
and declared graph-extension behavior remains the rollback boundary.

## Owner review gate

- [ ] Owner accepts the Stage 6 implementation and this evidence packet.
- [ ] Any requested revision is recorded with an exact failing contract or
  reproducible case.
- [ ] If accepted, Stage 6 is marked complete before any next-stage design begins.

## Final verdict

**Recommend ACCEPT.** Stage 6 is complete at the implementation and verification
level. It is awaiting only the explicit owner approval required by the plan.
