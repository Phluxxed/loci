# Plan: Extensible Graph Retrieval Stage 1

**Status:** implemented and approved; Stage 2 may begin

**Date:** 2026-07-13

**Scope:** production graph contracts plus one exact, persisted, MCP-readable
vertical slice

**Frozen benchmark:**
`/Users/brummerv/llm-wiki/tests/fixtures/graph_shape_traversal_stage3.json`

## Goal

Establish the smallest trustworthy graph substrate in loci: versioned graph
contracts, atomic persistence of one exact edge type, and one MCP read that
returns a seeded one-hop neighbour with inspectable evidence.

Stage 1 will implement direct Markdown section containment:

```text
parent page root or section --contains/exact--> direct child section
```

This slice uses hierarchy data loci already derives deterministically. It does
not introduce name matching, import resolution, profile loading, arbitrary
plugins, traversal, ranking, or benchmark-specific behaviour.

## Source Reconciliation

### Extensible graph retrieval design

`docs/design/2026-07-13-extensible-graph-retrieval-design.md` is the governing
direction. It requires Stage 1 to:

- define versioned node, edge, provenance, and contribution contracts;
- persist one exact edge type;
- expose one seeded, one-hop MCP read with supporting evidence;
- reject invalid endpoints and evidence;
- prove persistence across a fresh MCP process.

It also supersedes import-specific storage: import relationships are a later
built-in contributor to the shared graph substrate.

### Earlier graph-layer design

`docs/design/2026-06-10-graph-layer-design.md` supplies the trust rules:

- unresolved guesses never become facts;
- direction is part of the contract;
- deterministic local edges come first;
- `contains` is the safest first exact relationship.

Stage 1 deliberately selects only `contains`, not the earlier Phase 1 bundle of
`contains`, intra-file `calls`, and local `references`. A single edge type keeps
the first review gate narrow and prevents call-resolution work from entering
the substrate contract prematurely.

### Import dependency plan

`docs/plans/2026-07-01-import-dependency-graph.md` remains useful research for:

- keeping `parse_file()` compatible;
- tree-sitter import extraction;
- deterministic language-specific resolution;
- unresolved-edge diagnostics;
- incremental retention and stale-index tests.

The following parts of that plan do not land in Stage 1:

- a top-level import-specific `imports` store;
- `import_graph`, `loci_imports`, or a CLI `imports` command;
- `RawImport`, resolver implementation, language mappings, or import fixtures;
- import-specific schema decisions.

Those become inputs to the generic graph substrate in a later stage.

## Stage 1 Decisions

### Exact vertical slice

The only persisted Stage 1 relationship is:

```json
{
  "from": "guide.md::Guide#section",
  "to": "guide.md::Guide > Install#section",
  "type": "contains",
  "directed": true,
  "namespace": "loci",
  "resolution": "exact",
  "evidence": {
    "file": "guide.md",
    "line": 5,
    "content_hash": "sha256-of-child-section"
  }
}
```

The edge is parent to direct child. No transitive containment edge is stored.

Although the design permits `contains` edges to omit evidence eventually,
Stage 1 requires evidence on every persisted edge. This makes the first slice
meet the strongest provenance rule and directly exercises evidence validation.

### Nodes remain indexed symbols

Do not duplicate every symbol into a second graph-node table. The existing
`symbols` list remains the authoritative node registry. A `GraphNodeRef` is the
stable retrieval and contribution representation of an indexed node.

Domain node-attribute overlays are deferred to Stage 2 and can be added to the
graph envelope without changing existing symbol records.

### Contribution contract versus ingestion

Stage 1 defines and tests the versioned `GraphContribution` data contract. It
does not discover, load, register, or persist external contribution documents.

This resolves the boundary between the July design stages:

- Stage 1 freezes serialization and validation contracts.
- Stage 2 owns profile location, contribution ingress, namespace/type
  registration, freshness, and external contribution retention.

### Production surface

MCP is the production interface. Stage 1 adds one MCP tool and no CLI command.
The service implementation remains independently testable.

## Frozen Benchmark Boundary

The frozen benchmark currently has:

- schema version `1`;
- ten fixtures across Brain and `ai_graph_ideas`;
- SHA-256
  `c52def1bdf592ad735149d199910f74183598eccd9ccf8064335fa0cd0e84e27`.

Stage 1 must not import, copy, rewrite, or tune against this fixture. Its
questions exercise anchor selection and traversal, which begin in Stages 3 and
4. The Stage 1 review records the checksum only to prove the benchmark remained
frozen.

No loci test may depend on the absolute external fixture path. Stage 1 tests use
purpose-built temporary repositories containing no private content.

## Exact Contract APIs

Create `src/loci/graph/contracts.py`.

```python
from dataclasses import dataclass
from typing import Any, Literal, Mapping, TypeAlias

JSONValue: TypeAlias = (
    None | bool | int | float | str | list["JSONValue"] | dict[str, "JSONValue"]
)

GRAPH_SCHEMA_VERSION = 1

ResolutionTier: TypeAlias = Literal[
    "exact",
    "declared",
    "import-resolved",
    "heuristic",
]


@dataclass(frozen=True, slots=True)
class GraphNodeRef:
    id: str
    namespace: str
    kind: str
    attributes: dict[str, JSONValue]

    def to_dict(self) -> dict[str, JSONValue]: ...

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "GraphNodeRef": ...


@dataclass(frozen=True, slots=True)
class GraphEvidence:
    file: str
    line: int
    content_hash: str

    def to_dict(self) -> dict[str, JSONValue]: ...

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "GraphEvidence": ...


@dataclass(frozen=True, slots=True)
class GraphEdge:
    from_id: str
    to_id: str
    type: str
    directed: bool
    namespace: str
    resolution: ResolutionTier
    evidence: GraphEvidence

    def to_dict(self) -> dict[str, JSONValue]: ...

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "GraphEdge": ...


@dataclass(frozen=True, slots=True)
class GraphContribution:
    schema_version: int
    namespace: str
    nodes: tuple[GraphNodeRef, ...]
    edges: tuple[GraphEdge, ...]

    def to_dict(self) -> dict[str, JSONValue]: ...

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "GraphContribution": ...


class GraphContractError(ValueError):
    code: str
    message: str
    details: dict[str, JSONValue]


def validate_graph_edges(
    edges: list[GraphEdge],
    *,
    indexed_nodes: Mapping[str, Mapping[str, Any]],
) -> None: ...
```

`GraphEdge.to_dict()` serializes `from_id` and `to_id` as JSON fields `from`
and `to`. Deserialization accepts only the versioned contract shape; it does not
silently coerce malformed values.

### Resolution tiers

Freeze these categorical values now:

| JSON value | Meaning | Trusted by default |
| --- | --- | --- |
| `exact` | Deterministically proven from indexed source structure | Yes |
| `declared` | Explicit domain assertion with source evidence | Yes, after Stage 2 validation |
| `import-resolved` | Deterministically resolved through import semantics | Yes, after its contributor lands |
| `heuristic` | Ambiguous or inferred relationship | No |

No numeric confidence field is introduced. Stage 1 persists only `exact`.

### Validation errors

Contract and graph validation use these stable codes:

| Code | Condition |
| --- | --- |
| `INVALID_GRAPH_SCHEMA` | Missing or unsupported graph schema version |
| `INVALID_GRAPH_EDGE` | Missing fields, wrong types, self-edge, or invalid direction |
| `GRAPH_EDGE_TYPE_UNSUPPORTED` | Edge type is not registered for its namespace |
| `GRAPH_RESOLUTION_UNSUPPORTED` | Unknown resolution tier or tier not permitted for the contributor |
| `GRAPH_ENDPOINT_NOT_FOUND` | One or both edge endpoints are absent from indexed nodes |
| `GRAPH_EVIDENCE_INVALID` | Evidence path, line, or hash is malformed or inconsistent |

`service.py` translates `GraphContractError` into `LociError` without changing
the code, message, or details, so MCP continues using the existing structured
error envelope.

### Evidence validation

Every Stage 1 edge must satisfy:

- `file` is a normalized repository-relative path;
- `file` is not absolute and contains no `..` segment;
- `line >= 1`;
- `content_hash` is exactly 64 lowercase hexadecimal characters;
- both endpoints exist in the complete final symbol index;
- `from_id != to_id`;
- for `loci:contains`, both endpoints are Markdown symbols in the same file;
- for `loci:contains`, evidence file, line, and hash identify the child symbol;
- `directed` is `true` and `resolution` is `exact`.

## Built-in Edge API

Create `src/loci/graph/builtins.py`.

```python
from collections.abc import Sequence

from loci.graph.contracts import GraphEdge
from loci.parser.symbols import Symbol


def extract_markdown_contains_edges(
    symbols: Sequence[Symbol],
) -> list[GraphEdge]: ...
```

Rules:

1. Run only after `index_repo()` has assigned repository-relative symbol IDs and
   remapped Markdown hierarchy IDs.
2. Read `metadata["markdown"]["parent_id"]`; do not infer parents from names or
   `qualified_name`.
3. Emit one parent-to-direct-child edge for every non-empty `parent_id`.
4. Emit no edge for page roots or preamble nodes without a parent.
5. Use the child symbol's `file_path`, `line`, and `content_hash` as evidence.
6. Validate against the complete final symbol set.
7. Deduplicate by `(namespace, type, from_id, to_id)`.
8. Sort by `(namespace, type, from_id, to_id)` before persistence.

Do not change `parse_file()`, `parse_markdown()`, or `Symbol` in Stage 1.

## Persistence API

Modify `src/loci/storage/index_store.py`.

- Increment `INDEX_SCHEMA_VERSION` from `3` to `4`.
- Keep `EXTRACTOR_VERSION` at `3`; symbol extraction has not changed.
- Add a versioned `graph` envelope to every newly written index, including
  repositories with zero graph edges.

```python
def write(
    self,
    repo_path: Path,
    symbols: list[Symbol],
    file_hashes: dict[str, str],
    *,
    graph_edges: Sequence[GraphEdge] = (),
) -> None: ...


def get_graph_edges(self, repo_path: Path) -> list[GraphEdge]: ...
```

Persist:

```json
{
  "schema_version": 4,
  "extractor_version": 3,
  "symbols": [],
  "file_hashes": {},
  "repo_path": "/absolute/repo",
  "graph": {
    "schema_version": 1,
    "edges": []
  }
}
```

The graph envelope and symbols must use the existing atomic temp-file rename.
Do not introduce `edges.json`, SQLite, a graph database, or a graph-analysis
dependency in Stage 1.

An index at schema version `3` is stale. Existing version handling must force a
full reindex rather than returning a silent empty graph.

## Indexing Integration

Modify `src/loci/service.py` after all symbols have final IDs:

```python
indexed_nodes = {symbol.id: symbol.to_dict() for symbol in all_symbols}
graph_edges = extract_markdown_contains_edges(all_symbols)
validate_graph_edges(graph_edges, indexed_nodes=indexed_nodes)
store.write(
    repo_path,
    all_symbols,
    file_hashes=new_file_hashes,
    graph_edges=graph_edges,
)
```

Add `graph_edges_indexed` to the additive `index_repo()` result.

Incremental indexing already reconstructs `all_symbols` from unchanged and
fresh files. Recompute all built-in containment edges from that complete set on
each write. This makes changed and deleted Markdown hierarchy deterministic
without an edge-specific merge path.

External contribution retention remains Stage 2.

## Service Retrieval API

Add to `src/loci/service.py`:

```python
def graph_neighbors(
    repo: str | Path,
    seed_ids: list[str],
    *,
    ensure_fresh: bool = False,
) -> dict[str, Any]: ...
```

Stage 1 behaviour:

- require at least one seed;
- deduplicate seeds while preserving caller order;
- reject the request if any seed is absent;
- return outgoing direct `contains` neighbours only;
- return an empty neighbour list as success;
- sort neighbours deterministically;
- return evidence references, not answerability or sufficiency claims;
- do not expose hop, direction, trust-filter, budget, continuation, or ranking
  options until the relevant later stage.

Exact result envelope:

```json
{
  "schema_version": 1,
  "repo": "/absolute/repo",
  "results": [
    {
      "seed": {
        "id": "guide.md::Guide#section",
        "namespace": "loci",
        "kind": "section",
        "attributes": {
          "language": "markdown",
          "file": "guide.md",
          "line": 1,
          "end_line": 9
        }
      },
      "neighbors": [
        {
          "node": {
            "id": "guide.md::Guide > Install#section",
            "namespace": "loci",
            "kind": "section",
            "attributes": {
              "language": "markdown",
              "file": "guide.md",
              "line": 5,
              "end_line": 9
            }
          },
          "edge": {
            "from": "guide.md::Guide#section",
            "to": "guide.md::Guide > Install#section",
            "type": "contains",
            "directed": true,
            "namespace": "loci",
            "resolution": "exact",
            "evidence": {
              "file": "guide.md",
              "line": 5,
              "content_hash": "sha256-of-child-section"
            }
          }
        }
      ]
    }
  ],
  "diagnostics": []
}
```

## MCP API

Add to `src/loci/mcp_server.py`:

```python
@mcp.tool()
def loci_graph_neighbors(
    repo: str,
    seed_ids: list[str],
) -> CallToolResult:
    """Return exact outgoing one-hop graph neighbours for indexed seed nodes."""
    return _handle_loci_error(
        lambda: graph_neighbors(repo, seed_ids, ensure_fresh=True)
    )
```

The MCP handler remains transport-only. It must not load indexes, validate graph
records, or traverse edges itself.

No Stage 1 CLI command is added.

## Implementation Tasks

### Task 1: Freeze graph contracts

**Files:**

- `src/loci/graph/__init__.py`
- `src/loci/graph/contracts.py`
- `tests/graph/__init__.py`
- `tests/graph/test_contracts.py`

**Acceptance criteria:**

- Valid node, evidence, edge, and contribution records round-trip to stable
  JSON-compatible dictionaries.
- Malformed schema, edge, endpoint, and evidence records fail with the exact
  structured codes defined above.
- Stage 1 permits only `loci:contains` with `resolution=exact` for persistence.
- No profile or contribution-loading behaviour is introduced.

**Verification:**

```bash
.venv/bin/python -m pytest tests/graph/test_contracts.py -q
```

**Dependencies:** none.

### Task 2: Extract exact Markdown containment

**Files:**

- `src/loci/graph/builtins.py`
- `tests/graph/test_builtins.py`

**Required tests:**

- `test_markdown_contains_edges_use_final_repo_relative_ids`
- `test_markdown_contains_edges_are_directed_and_exact`
- `test_markdown_root_and_preamble_emit_no_parent_edge`
- `test_contains_evidence_identifies_child_heading`
- `test_contains_edges_are_deterministically_sorted`

**Acceptance criteria:**

- Only metadata-backed direct containment is emitted.
- No name-based, cross-file, transitive, or heuristic edge is emitted.
- Evidence identifies the child section exactly.

**Verification:**

```bash
.venv/bin/python -m pytest tests/graph/test_builtins.py -q
```

**Dependencies:** Task 1.

### Task 3: Persist the graph atomically

**Files:**

- `src/loci/storage/index_store.py`
- `src/loci/service.py`
- `tests/storage/test_index_store.py`
- `tests/test_service.py`

**Required tests:**

- `test_store_write_load_round_trips_graph_envelope`
- `test_store_graph_write_is_atomic`
- `test_store_rejects_invalid_graph_endpoint`
- `test_store_rejects_invalid_graph_evidence`
- `test_store_writes_empty_graph_for_repo_without_edges`
- `test_service_schema_upgrade_rebuilds_graph`
- `test_service_incremental_reindex_recomputes_contains_edges`

**Acceptance criteria:**

- Schema version `4` persists symbols and graph in one atomic index.
- Old indexes fully rebuild instead of appearing graph-empty.
- Incremental indexing retains unchanged edges and removes deleted hierarchy.
- Existing `IndexStore.write()` call sites remain compatible.

**Verification:**

```bash
.venv/bin/python -m pytest \
  tests/storage/test_index_store.py \
  tests/test_service.py -q
```

**Dependencies:** Tasks 1 and 2.

### Task 4: Expose seeded one-hop service retrieval

**Files:**

- `src/loci/service.py`
- `tests/test_service.py`

**Required tests:**

- `test_service_indexes_markdown_contains_edge`
- `test_graph_neighbors_returns_seeded_one_hop_with_evidence`
- `test_graph_neighbors_requires_seed`
- `test_graph_neighbors_rejects_unknown_seed`
- `test_graph_neighbors_preserves_seed_order`
- `test_graph_neighbors_empty_neighbors_is_success`

**Acceptance criteria:**

- The service returns the exact envelope above.
- Outgoing direction is preserved.
- Invalid seeds fail atomically rather than returning partial results.
- Results are deterministic across repeated calls.

**Verification:**

```bash
.venv/bin/python -m pytest tests/test_service.py -q
```

**Dependencies:** Task 3.

### Task 5: Prove the real MCP and restart boundary

**Files:**

- `src/loci/mcp_server.py`
- `tests/test_mcp_server.py`

**Required tests:**

- Add `loci_graph_neighbors` to the exact MCP tool-list assertion.
- `test_mcp_graph_neighbors_survives_fresh_process`
- `test_mcp_graph_neighbors_returns_structured_error`

The fresh-process test must:

1. Start MCP process A with a temporary `LOCI_BASE_DIR`.
2. Index a temporary Markdown repository.
3. Close process A.
4. Start MCP process B against the same cache directory.
5. Call `loci_graph_neighbors` and assert the persisted edge and evidence.

Run through `python -m loci.mcp_server` and through the installed `loci-mcp`
entrypoint when it is available.

**Verification:**

```bash
.venv/bin/python -m pytest tests/test_mcp_server.py -q
```

**Dependencies:** Task 4.

## Stage 1 Review Gate

### Approval before implementation

No code work begins until a reviewer explicitly approves all of these choices:

- Markdown direct-parent `contains` is the sole Stage 1 edge slice.
- Every persisted Stage 1 edge carries evidence.
- Existing symbols remain the node registry.
- Contribution serialization lands now; contribution ingress waits for Stage 2.
- `index.json.graph` is the persistence envelope.
- `loci_graph_neighbors(repo, seed_ids)` is the only new public operation.
- No CLI, import resolver, profile loader, graph-health API, traversal, ranking,
  benchmark scoring, or new third-party dependency enters Stage 1.

If any item is rejected, update this plan before implementation.

### Evidence required after implementation

Run:

```bash
.venv/bin/python -m pytest tests/graph -q
.venv/bin/python -m pytest \
  tests/test_service.py \
  tests/test_mcp_server.py \
  tests/storage/test_index_store.py -q
.venv/bin/python -m pytest tests/ -q
uv build
loci index /Users/brummerv/loci --incremental
loci verify /Users/brummerv/loci
git diff --check
shasum -a 256 \
  /Users/brummerv/llm-wiki/tests/fixtures/graph_shape_traversal_stage3.json
```

The review must inspect:

- one valid serialized edge and its source evidence;
- structured failures for a missing endpoint and malformed evidence;
- the fresh-process MCP result;
- schema-upgrade and incremental-reindex behaviour;
- existing MCP result compatibility;
- the unchanged frozen benchmark checksum;
- the complete diff for scope creep.

Stage 1 was approved by the project owner on 2026-07-13. Stage 2 may proceed,
subject to its own design decisions and implementation plan.

## Baseline Evidence Before Implementation

Observed on 2026-07-13:

- focused service, MCP, and storage suite: `66 passed`;
- loci index verification: `551 checked`, `551 passed`, `0 failed`;
- full suite: `227 passed`, one Codex session-start timeout test failed;
- the failed timeout test passed immediately when rerun alone;
- worktree: `master...origin/master`, with the July 13 design document already
  untracked.

The timeout result is a pre-existing timing flake, not a graph failure. Stage 1
still requires a clean full-suite run. If the same test flakes, report the full
run and isolated rerun; do not hide or silently discard the failure.

## Implementation Evidence

Observed after implementation on 2026-07-13:

- complete test suite: `258 passed`;
- real stdio MCP tests: `8 passed`, including a two-process persistence proof;
- package build: source distribution and wheel built successfully;
- source compilation: `.venv/bin/python -m compileall -q src` passed;
- fresh-process dogfood index: `612` symbols and `361` exact containment edges;
- loci verification: `612 checked`, `612 passed`, `0 failed`;
- frozen benchmark SHA-256 remained
  `c52def1bdf592ad735149d199910f74183598eccd9ccf8064335fa0cd0e84e27`;
- `git diff --check` passed.

No Stage 2 work, import resolver, profile loader, contribution ingress, graph
health API, graph database, CLI graph command, or new dependency was added.

## Risks and Mitigations

| Risk | Impact | Mitigation |
| --- | --- | --- |
| Public contract is over-designed before traversal exists | Later stages inherit unnecessary compatibility obligations | Keep Stage 1 MCP input minimal and avoid premature filters or budgets |
| Graph data silently disappears on old indexes | Retrieval returns false-empty results | Schema bump forces a full rebuild |
| Incremental indexing retains stale containment | Incorrect neighbours survive edits | Recompute built-in edges from the complete final symbol set |
| Evidence points at the wrong span | Exact edges become untrustworthy | Validate evidence against the child symbol's file, line, and hash |
| Graph storage duplicates node state | Index bloat and divergent sources of truth | Keep `symbols` authoritative and persist edges only |
| Import work leaks into Stage 1 | Scope and trust model expand before substrate review | Defer all resolver and import APIs explicitly |
| Benchmark drives premature tuning | Stage boundaries collapse | Checksum only; no Stage 1 dependency on the benchmark |

## Deferred Work

Explicitly deferred beyond Stage 1:

- graph profile discovery and precedence;
- contribution file/service ingress;
- domain node attributes and relation registration;
- contribution freshness and invalidation;
- graph-health diagnostics;
- Markdown-link edges;
- code-symbol containment;
- import and resolved-reference contributors;
- incoming/bidirectional neighbours;
- trust and edge-type filters;
- multi-hop paths, cycles, budgets, continuation, and ranking;
- question-shaped anchor selection;
- llm-wiki compiler integration;
- benchmark scoring and acceptance thresholds;
- graph analysis, centrality, clustering, and `networkx`.

## Open Questions Assigned to Later Stages

The July design's remaining architecture questions do not block this exact
slice:

1. Profile repository location and registration precedence: Stage 2.
2. Contribution file path versus service-call ingress: Stage 2.
3. Which categorical tiers each domain may activate: Stage 2 and contributor
   review; the serialized tier vocabulary is frozen here.
4. Whether import extraction follows the substrate or waits for benchmark proof:
   decide after Stages 3-5 evidence, before the code-relationship stage.
