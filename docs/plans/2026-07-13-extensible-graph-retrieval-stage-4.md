# Plan: Extensible Graph Retrieval Stage 4

**Status:** implemented; technical review gate passed; Stage 5 consumer integration gate passed with explicit rollback retained

**Date:** 2026-07-13

**Scope:** bounded filtered neighbours, evidence-backed path search, and
question-shaped graph retrieval with semantic bridge rejection

**Depends on:** Stage 1 commit `797e881`, the approved uncommitted Stage 2
implementation, and the approved uncommitted Stage 3 implementation

**Frozen benchmark:**
`/Users/brummerv/llm-wiki/tests/fixtures/graph_shape_traversal_stage3.json`

**Frozen benchmark SHA-256:**
`c52def1bdf592ad735149d199910f74183598eccd9ccf8064335fa0cd0e84e27`

## Goal

Turn exact indexed edges and Stage 3 anchors into bounded, inspectable graph
evidence. Every selected path must contain the exact persisted edge records,
their source provenance, and hydrated evidence lines. Traversal must preserve
edge direction, stop at explicit hop/node/path/evidence budgets, avoid cycles,
penalize hubs, and reject multi-hop routes that connect names without evidence
for the relationship expressed by the question.

Stage 4 returns retrieval evidence. It does not claim that the caller's
question is answered, that a path proves a domain assertion, or that an
answer should be accepted. `llm-wiki` retains those decisions in Stage 5.

## Authorization and Review Posture

Stage 3 passed its technical review gate and the project owner authorized
continued implementation on 2026-07-13. The owner has delegated routine
implementation review to the agent. Stage 4 therefore ends at an evidence-based
technical gate; another product decision is required only if the frozen replay
shows that the approved architecture cannot distinguish meaningful bridges
from the two frozen false-relation cases.

The Stage 1 `graph_neighbors()` and `loci_graph_neighbors` contracts remain
unchanged. Their exact `loci/contains/exact/outgoing` behavior is a useful
vertical slice and must not silently widen when domain graph data is loaded.
Filtered traversal is additive.

## Governing Evidence

### Extensible graph design

`docs/design/2026-07-13-extensible-graph-retrieval-design.md` requires Stage 4
to add:

- neighbours with edge and trust filters;
- supported paths between explicit nodes;
- question-shaped traversal from a small anchor set;
- hop, node, path, byte, and estimated-token limits;
- cycle control, hub penalties, and semantic bridge requirements;
- selected and rejected paths with complete edge evidence;
- omissions, continuation information, cost, and graph diagnostics;
- no domain-level `sufficient` assertion.

### Earlier graph trust design

`docs/design/2026-06-10-graph-layer-design.md` makes direction and provenance
part of the fact. Stage 4 may traverse a directed edge in reverse only when the
caller explicitly chooses `incoming` or `either`, and the response must record
that the traversal direction was `reverse`. The stored `from` and `to` fields
are never rewritten.

Resolution is a categorical filter, not numeric confidence. Safe defaults admit
only `exact` and `declared`; `heuristic` is excluded unless a future contract
explicitly adds and exposes it. No score can upgrade a disallowed resolution.

### Frozen benchmark

The frozen contract contains ten questions and fifteen expected endpoint
slots. Four fixtures name a positive direct or meaningful-bridge path, two name
forbidden hub shortcuts, two are exact-attribute questions, and two require an
answerability refusal owned by the later consumer.

Stage 3 selected 14/15 expected endpoints at a ten-anchor ceiling, but mean
anchor precision was 14.0%. Stage 4 must use graph evidence to rank or reject
routes; it must not hide this broad candidate set or convert reach into support.

The benchmark's expected pages and paths are scoring data only. Production
code must not read the contract or contain corpus names, fixture IDs, expected
paths, question strings, or wiki-specific vocabulary.

### Live implementation audit

The persisted Stage 2 graph already supplies the required traversal facts:

```text
GraphIndexState
    edges: GraphEdge[]
        from / to / type / directed / namespace / resolution
        evidence: file / line / content_hash
    diagnostics: GraphDiagnostic[]
```

`IndexStore.get_file_content()` can hydrate an exact cached line without
reading live source. The index freshness boundary validates source hashes
before graph retrieval. Stage 4 should use that cached method directly and add
retrieval logging only when the existing public file/symbol APIs are invoked;
internal edge evidence hydration must not pretend to be a separate agent read.

The current `llm-wiki` graph supplies directed `body_link` and `mentioned_in`
edges. Its legacy provider searches those edges as undirected paths and accepts
reach without a semantic bridge, which is the exact behavior the frozen false
fixtures expose. Stage 4 must not copy that provider into Loci.

## Stage 4 Decisions

### Three additive capabilities

Stage 4 adds three separate service and MCP capabilities:

1. filtered one-hop neighbours for callers that know their graph domain;
2. exact endpoint-to-endpoint path search, which reports an evidenced edge
   sequence but makes no question-level claim;
3. question-shaped graph retrieval, which reuses Stage 3 anchors and applies
   query-aware ranking and semantic rejection.

This separation prevents an explicit path-inspection tool from smuggling in
unstated natural-language semantics, while allowing the question-shaped tool
to explain why a reachable route was rejected.

### Safe filtering defaults

All new traversal calls accept optional allow-lists:

- `namespaces`;
- `edge_types`;
- `resolutions`.

`None` means all values currently present after applying the safe trust floor.
An explicit empty list is invalid. Every string is non-empty, duplicate values
are removed, and each list is capped at 32 values.

When `resolutions is None`, the effective allow-list is `exact, declared`.
Callers may explicitly narrow it. Unsupported resolution names fail with
`GRAPH_RESOLUTION_UNSUPPORTED`; they do not degrade to a wildcard.

An empty filtered graph is a successful empty result with counts. Unknown
namespace or edge-type names are not schema errors because a valid repository
may simply have no matching edge.

### Direction stays visible

`direction` is one of:

- `outgoing`: traverse stored `from -> to` only;
- `incoming`: traverse stored `to -> from` only;
- `either`: permit both orientations.

For an undirected edge, both orientations are available regardless of the
requested direction. Persisted Stage 2 domain edge policies are directed, but
the pure traversal engine remains correct for the generic contract.

Each returned step contains `traversed: forward | reverse` while preserving the
original edge record. Path node order describes traversal order, not a rewrite
of edge direction.

### Bounded deterministic search

The pure engine uses breadth-first simple-path search with deterministic
adjacency ordering. A node already in the current path is not revisited, so
cycles cannot enter a returned path.

Limits are validated before work:

| Limit | Default | Allowed |
| --- | ---: | ---: |
| `max_hops` | 3 | 1..6 |
| `max_nodes` | 64 | 2..512 |
| `max_paths` | 8 | 1..32 |
| `path_offset` | 0 | 0..256 |
| `max_evidence_bytes` | 32,768 | 1,024..262,144 |
| `max_estimated_tokens` | 8,192 | 256..65,536 |

The node budget counts distinct nodes admitted to the search frontier,
including endpoints. The path budget counts returned paths after
deduplication, ranking, and `path_offset`. The engine searches for one extra
candidate beyond the requested window so it can emit a deterministic
`next_path_offset`; it never promises a complete count after a node or hop
budget truncates the search.

Evidence hydration stops at the smaller of the byte budget and four times the
token budget. Paths that would exceed the remaining evidence budget are moved
to `rejected_paths` with `EVIDENCE_BUDGET_EXCEEDED`; no partial path is emitted.
Estimated tokens are `ceil(UTF-8 evidence bytes / 4)` and are labeled as an
estimate.

### Evidence-backed paths

Every selected path contains:

- ordered indexed node references;
- ordered traversal steps;
- the full persisted edge record for every step;
- `forward` or `reverse` traversal orientation;
- the cached evidence line named by the edge provenance;
- a deterministic ranking score and its components.

If an evidence file or line cannot be hydrated, the path is rejected with
`EVIDENCE_UNAVAILABLE` and a structured diagnostic. The service never returns
an edge with invented, empty, or live-source-substituted evidence.

Parallel edges are distinct candidates because type and evidence are
meaningful. Identical node/edge/orientation sequences are deduplicated.

### Exact paths do not assert semantic composition

The explicit endpoint API labels every result `support_kind: edge_sequence`.
This means only that each constituent edge is present and evidenced. It does
not mean the edge types are transitive or that the path proves a caller's
unstated proposition.

Semantic composition policies are not added to the Stage 2 profile contract in
this stage. No approved domain has supplied a declarative transitivity rule,
and inventing one in Loci would widen the public extension contract without
evidence.

### Question-shaped traversal classifies intent conservatively

The question-shaped API first runs the Stage 3 selector. It then classifies
whether graph traversal is useful using bounded, domain-neutral wording:

- relationship intent includes relation, support, connection, transition, or
  definition predicates between candidate entities;
- exact-result or measured-attribute wording suppresses graph expansion unless
  the caller supplies explicit seeds.

The classification is returned as retrieval routing evidence, not an
answerability decision. A suppressed traversal returns anchors, an empty path
set, and `routing.reason = attribute_or_measurement_question`.

Explicit seeds override anchor inference but do not bypass edge filters,
budgets, evidence requirements, or semantic bridge rejection.

### Candidate endpoints and ranking

Question-shaped traversal searches from selected anchors toward:

- other selected anchors; and
- bounded reached nodes whose indexed name, path, metadata, or symbol fields
  match meaningful question terms.

This permits a direct evidenced edge to recover a relevant endpoint that fell
just below the Stage 3 anchor cap. It does not expand every reached node into
output.

Ranking uses only domain-neutral observable inputs:

- anchor rank and Stage 3 retrieval score;
- endpoint term overlap;
- edge-evidence term overlap;
- fewer hops;
- lower intermediate-node degree;
- deterministic path identity as the final tie-break.

The score is named `retrieval_score`, not confidence. The response exposes
`anchor`, `endpoint`, `evidence`, `hop`, and `hub_penalty` components.

### Semantic bridge rule

A direct one-edge route between question-relevant endpoints may be selected as
`direct_authored_edge` because the edge itself supplies the authored
connection and evidence line. It still does not prove a stronger proposition
than that line expresses.

A route with two or more edges must additionally contain bridge evidence for a
relationship predicate not explained merely by the endpoint names. The
deterministic check:

1. tokenizes and lightly normalizes the question, endpoint labels, and edge
   evidence;
2. removes terms already explained by the two endpoint labels;
3. retains relationship-bearing residual terms;
4. requires at least one residual stem in the combined edge evidence.

If the requirement is absent, the route is rejected:

- `HUB_SHORTCUT` when any intermediate node exceeds the deterministic hub
  threshold `max(4, ceil(sqrt(filtered_edge_count)))`;
- `SEMANTIC_BRIDGE_MISSING` otherwise.

The threshold is computed from the filtered graph, reported in the response,
and never taken from the frozen benchmark's generic-hub lists. A relevant
bridge can survive a hub penalty; degree alone never upgrades a path.

The lightweight normalization handles common inflections such as
`incubated/incubating` without a domain dictionary. Production code must not
contain named relation synonyms tuned to the two corpora. If this rule cannot
admit the frozen meaningful bridge while rejecting both false shortcuts, Stage
4 stops for an architecture decision instead of adding fixture vocabulary.

## Pure Traversal API

Add `src/loci/graph/traversal.py`:

```python
MAX_GRAPH_FILTER_VALUES = 32
MAX_GRAPH_HOPS = 6
MAX_GRAPH_NODES = 512
MAX_GRAPH_PATHS = 32
MAX_GRAPH_PATH_OFFSET = 256
MAX_GRAPH_EVIDENCE_BYTES = 262_144
MAX_GRAPH_ESTIMATED_TOKENS = 65_536

GraphDirection = Literal["outgoing", "incoming", "either"]
TraversalOrientation = Literal["forward", "reverse"]

@dataclass(frozen=True, slots=True)
class GraphTraversalStep:
    from_id: str
    to_id: str
    edge: GraphEdge
    traversed: TraversalOrientation

@dataclass(frozen=True, slots=True)
class GraphPath:
    node_ids: tuple[str, ...]
    steps: tuple[GraphTraversalStep, ...]

@dataclass(frozen=True, slots=True)
class GraphTraversalResult:
    paths: tuple[GraphPath, ...]
    filtered_edge_count: int
    examined_nodes: int
    examined_paths: int
    omitted_nodes: int
    omitted_paths: int
    hop_limit_reached: bool
    node_limit_reached: bool
    next_path_offset: int | None

def filter_graph_edges(
    edges: Sequence[GraphEdge],
    *,
    namespaces: Sequence[str] | None,
    edge_types: Sequence[str] | None,
    resolutions: Sequence[str] | None,
) -> tuple[GraphEdge, ...]: ...

def graph_adjacency(
    edges: Sequence[GraphEdge],
    *,
    direction: GraphDirection,
) -> Mapping[str, tuple[GraphTraversalStep, ...]]: ...

def find_graph_paths(
    edges: Sequence[GraphEdge],
    source_ids: Sequence[str],
    target_ids: Sequence[str],
    *,
    direction: GraphDirection,
    max_hops: int,
    max_nodes: int,
    max_paths: int,
    path_offset: int = 0,
    node_priorities: Mapping[str, float] | None = None,
) -> GraphTraversalResult: ...

def graph_hub_threshold(filtered_edge_count: int) -> int: ...

def semantic_bridge_terms(
    question: str,
    source_text: str,
    target_text: str,
) -> tuple[str, ...]: ...

def graph_relation_terms(question: str) -> tuple[str, ...]: ...

def graph_text_terms(text: str) -> tuple[str, ...]: ...
```

The pure module raises `GraphContractError` with:

- `INVALID_INPUT` for malformed IDs, direction, filters, or limits;
- `GRAPH_RESOLUTION_UNSUPPORTED` for unsupported resolution values;
- `GRAPH_ENDPOINT_NOT_FOUND` is reserved for the service, which owns the
  current indexed-node set.

## Filtered Neighbour Service API

Add to `src/loci/service.py`:

```python
def graph_traverse_neighbors(
    repo: str | Path,
    seed_ids: list[str],
    *,
    namespaces: list[str] | None = None,
    edge_types: list[str] | None = None,
    resolutions: list[str] | None = None,
    direction: Literal["outgoing", "incoming", "either"] = "outgoing",
    max_neighbors: int = 64,
    ensure_fresh: bool = False,
) -> dict[str, Any]: ...
```

`max_neighbors` is per seed and is bounded to 1..256. The response includes
effective filters, ordered neighbours, the stored edge plus traversal
orientation, returned/omitted counts, and persisted diagnostics. This API does
not hydrate evidence content; the complete provenance record remains present
and exact-path/question retrieval performs bounded line hydration.

Add MCP:

```python
loci_graph_traverse_neighbors(
    repo: str,
    seed_ids: list[str],
    namespaces: list[str] | None = None,
    edge_types: list[str] | None = None,
    resolutions: list[str] | None = None,
    direction: str = "outgoing",
    max_neighbors: int = 64,
) -> CallToolResult
```

## Exact Path Service API

Add to `src/loci/service.py`:

```python
def graph_paths(
    repo: str | Path,
    source_ids: list[str],
    target_ids: list[str],
    *,
    namespaces: list[str] | None = None,
    edge_types: list[str] | None = None,
    resolutions: list[str] | None = None,
    direction: Literal["outgoing", "incoming", "either"] = "outgoing",
    max_hops: int = 3,
    max_nodes: int = 64,
    max_paths: int = 8,
    path_offset: int = 0,
    max_evidence_bytes: int = 32_768,
    max_estimated_tokens: int = 8_192,
    ensure_fresh: bool = False,
) -> dict[str, Any]: ...
```

Exact success envelope:

```json
{
  "schema_version": 1,
  "repo": "/absolute/repo",
  "support_kind": "edge_sequence",
  "sources": [{"id": "..."}],
  "targets": [{"id": "..."}],
  "filters": {
    "namespaces": ["llm-wiki"],
    "edge_types": ["body_link", "mentioned_in"],
    "resolutions": ["declared"],
    "direction": "either"
  },
  "paths": [
    {
      "nodes": [{"id": "..."}, {"id": "..."}],
      "steps": [
        {
          "traversed": "forward",
          "edge": {"from": "...", "to": "...", "evidence": {}},
          "evidence_span": {
            "file": "concepts/a.md",
            "start_line": 18,
            "end_line": 18,
            "content": "authored source line"
          }
        }
      ]
    }
  ],
  "rejected_paths": [],
  "counts": {
    "filtered_edges": 2,
    "examined_nodes": 3,
    "examined_paths": 1,
    "returned_paths": 1,
    "omitted_nodes": 0,
    "omitted_paths": 0
  },
  "budget": {
    "max_hops": 3,
    "max_nodes": 64,
    "max_paths": 8,
    "path_offset": 0,
    "evidence_bytes": 20,
    "estimated_tokens": 5,
    "max_evidence_bytes": 32768,
    "max_estimated_tokens": 8192,
    "hop_limit_reached": false,
    "node_limit_reached": false,
    "next_path_offset": null
  },
  "diagnostics": []
}
```

Missing endpoint IDs fail together with `GRAPH_ENDPOINT_NOT_FOUND`. A source ID
may not also be its own only target. Duplicate IDs preserve first occurrence.

Add MCP `loci_graph_paths` with the same arguments except
`ensure_fresh`; the handler always refreshes before reading.

## Question-Shaped Service API

Add to `src/loci/service.py`:

```python
def graph_retrieve(
    repo: str | Path,
    question: str,
    seed_ids: list[str] | None = None,
    *,
    namespaces: list[str] | None = None,
    edge_types: list[str] | None = None,
    resolutions: list[str] | None = None,
    direction: Literal["outgoing", "incoming", "either"] = "either",
    max_anchors: int = 10,
    max_hops: int = 3,
    max_nodes: int = 64,
    max_paths: int = 8,
    path_offset: int = 0,
    max_evidence_bytes: int = 32_768,
    max_estimated_tokens: int = 8_192,
    ensure_fresh: bool = False,
) -> dict[str, Any]: ...
```

The response contains:

- the exact Stage 3 anchor records and selection diagnostics;
- `routing: {kind, reason}` explaining expansion or suppression;
- selected paths with `support_kind`, `semantic_bridge`, retrieval score, score
  components, nodes, steps, and evidence spans;
- rejected paths with nodes, edge identities, and one stable reason code;
- effective filters, hub threshold, counts, budget use, omissions,
  continuation, and persisted graph diagnostics.

Stable rejection reasons in Stage 4:

- `SEMANTIC_BRIDGE_MISSING`;
- `HUB_SHORTCUT`;
- `EVIDENCE_UNAVAILABLE`;
- `EVIDENCE_BUDGET_EXCEEDED`;
- `DUPLICATE_PATH` is counted but not serialized as a rejected path.

The response does not contain `answerable`, `sufficient`, `supported_claim`, or
an equivalent boolean.

Add MCP `loci_graph_retrieve` with the same arguments except
`ensure_fresh`; the handler always refreshes before reading.

## Evidence Hydration Helpers

Keep cache-specific hydration private to `src/loci/graph/retrieval.py`:

```python
def _hydrate_graph_path(
    repo_path: Path,
    store: IndexStore,
    indexed_nodes: dict[str, dict[str, Any]],
    path: GraphPath,
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]: ...

def _graph_evidence_span(
    repo_path: Path,
    store: IndexStore,
    edge: GraphEdge,
) -> dict[str, Any] | None: ...
```

The helper reads exactly `evidence.line` from the cached source. Stage 4 does
not widen evidence to a whole page, follow source links, or synthesize missing
context. Broader domain hydration belongs to the Stage 5 compiler envelope.

## MCP Compatibility

Modify `src/loci/mcp_server.py` to register:

- `loci_graph_traverse_neighbors`;
- `loci_graph_paths`;
- `loci_graph_retrieve`.

Keep all existing tool names and signatures unchanged. Update server
instructions to distinguish exact neighbours, filtered traversal, exact paths,
and question-shaped retrieval. MCP failures continue to use the existing
structured `LociError` envelope.

Fresh-process tests must inspect the generated tool schemas and execute at
least one successful `loci_graph_paths` and one successful
`loci_graph_retrieve` request. Importing the Python function in-process is not
sufficient evidence that the stdio server exposes the tools.

## Frozen Benchmark Adapter

Add `benchmarks/graph_traversal_stage4.py`. It is development-only and
read-only with respect to both source wikis.

For each corpus it:

1. imports `collect_pages()` and `collect_typed_edges()` from the checked-out
   `llm-wiki` source supplied by `--llm-wiki-root`;
2. creates a temporary mirror containing only canonical pages returned by
   `collect_pages()`;
3. indexes that mirror once to obtain canonical Loci page-root IDs;
4. writes a declarative `llm-wiki` profile defining directed `body_link` and
   `mentioned_in` edges at `declared` resolution;
5. writes one contribution whose endpoints are the indexed page-root IDs and
   whose evidence hashes and line numbers point at the mirrored authored
   source;
6. re-indexes the mirror so Loci validates and persists the contribution;
7. runs `graph_retrieve()` for all ten frozen questions with only the explicit
   `llm-wiki` namespace/type/resolution filters and Stage 4 budgets;
8. scores selected paths, rejected paths, endpoint reach, forbidden shortcuts,
   evidence hydration, bytes, tokens, latency, omissions, and deterministic
   digest;
9. deletes the temporary mirrors on exit.

The adapter may translate `llm-wiki`'s established page/edge contract into
Loci records, but it must not be imported by production code. This proves the
retrieval substrate before Stage 5 chooses the permanent adapter integration.

Evidence lines are found deterministically:

- `body_link`: the first authored source line whose resolved Markdown link
  equals the edge target;
- `mentioned_in`: the frontmatter line that declares the target page's
  `mentioned_in` relationship.

If an edge cannot be assigned an exact line, the benchmark adapter fails
loudly rather than emitting fabricated provenance.

CLI:

```bash
.venv/bin/python benchmarks/graph_traversal_stage4.py \
  --contract /Users/brummerv/llm-wiki/tests/fixtures/graph_shape_traversal_stage3.json \
  --llm-wiki-root /Users/brummerv/llm-wiki \
  --ai-graph-root /Users/brummerv/phluxxed/ai_graph_ideas \
  --brain-root /Users/brummerv/.anvil-brain/codex \
  --output /tmp/loci-graph-traversal-stage4.json
```

The script never writes to the frozen fixture, either source wiki, or their
Loci extension directories. Gold fields are used only after retrieval for
scoring.

## Exact File Changes

### New production files

- `src/loci/graph/traversal.py`
  - filter validation;
  - directed adjacency;
  - bounded simple-path search;
  - deterministic path identity/deduplication;
  - hub threshold and semantic bridge term helpers.
- `src/loci/graph/retrieval.py`
  - filtered-neighbour, exact-path, and question-shaped query engine;
  - cached evidence hydration, ranking, rejection, budgets, and envelopes.

### Modified production files

- `src/loci/service.py`
  - add the three public APIs as thin context-loading and error-mapping
    wrappers, leaving the existing Stage 1 API unchanged.
- `src/loci/mcp_server.py`
  - register three additive tools and update instructions.

### New benchmark files

- `benchmarks/graph_traversal_stage4.py`
  - temporary wiki mirror and contribution adapter;
  - frozen replay and scoring;
  - latency-independent deterministic digest.

### New tests

- `tests/graph/test_traversal.py`
  - pure filtering, direction, cycles, limits, offsets, ordering, hub threshold,
    and semantic term behavior.
- `tests/graph/test_traversal_benchmark.py`
  - temporary adapter provenance, scorer, checksum, gold isolation, digest, and
    all-ten-fixture replay shape using bounded local fixtures.

### Modified tests

- `tests/test_service.py`
  - filtered neighbours, exact paths, evidence hydration, unavailable evidence,
    byte/token rejection, question routing, direct selection, meaningful bridge,
    false hub rejection, diagnostics, and errors.
- `tests/test_mcp_server.py`
  - exact tool list, schemas, error mapping, and fresh-process round trips.

### Documentation

- `README.md`
  - add the three new tools, safe trust defaults, path-vs-proof distinction,
    budgets, and no-sufficiency boundary.
- `skills/loci/SKILL.md`
- `.claude/skills/loci/SKILL.md`
  - teach agents when to use anchors, neighbours, exact paths, or
    question-shaped retrieval and how to interpret rejected paths.
- `docs/plans/2026-07-13-extensible-graph-retrieval-stage-3.md`
  - change only status/evidence if Stage 4 verification reveals a required
    generic anchor correction.

No persisted schema version, extension profile schema, CLI command, existing
MCP signature, import extractor, or `llm-wiki` runtime file changes in Stage 4.

## Test Matrix

### Pure traversal

- `None` filters use exact/declared trust tiers;
- explicit filters include only named namespaces/types/resolutions;
- empty, oversized, malformed, and unsupported filters fail;
- outgoing, incoming, and either preserve stored direction;
- undirected edges are traversable both ways;
- deterministic adjacency and path ordering;
- source/target duplicate normalization;
- one-hop and multi-hop path discovery;
- no node repeats in cyclic graphs;
- hop limit excludes deeper routes and records truncation;
- node limit stops frontier growth and records omissions;
- path limit plus offset emits deterministic continuation;
- parallel typed edges remain distinguishable;
- hub threshold is corpus-derived;
- relationship residual stemming handles inflections;
- endpoint-only overlap does not satisfy a semantic bridge.

### Service envelopes

- exact Stage 1 neighbour response remains byte-for-shape compatible;
- filtered neighbours return orientation and omissions;
- missing seed/source/target errors include all missing IDs;
- graph state contract errors remain structured;
- exact paths hydrate every evidence line from cache;
- reverse traversal preserves original edge direction;
- missing evidence rejects rather than partially returns a path;
- evidence byte and token budgets reject whole paths;
- explicit paths use `support_kind: edge_sequence` only;
- inferred and explicit anchor behavior remains Stage 3 compatible;
- attribute/measurement routing suppresses inferred traversal;
- direct authored edge is selectable with evidence;
- meaningful multi-hop bridge contains residual relationship evidence;
- non-hub unsupported composition is rejected as
  `SEMANTIC_BRIDGE_MISSING`;
- high-degree unsupported composition is rejected as `HUB_SHORTCUT`;
- retrieval scores expose components and deterministic ties;
- persisted degraded diagnostics survive in every new response;
- no response contains a sufficiency or answerability assertion.

### MCP

- all existing tools remain present;
- three new tools expose the planned parameter schemas;
- handlers force fresh indexing;
- invalid limits/filters/direction return structured errors;
- fresh stdio process discovers and successfully executes exact-path and
  question-shaped tools.

### Frozen replay

- frozen contract schema and checksum are unchanged;
- all ten questions run through `graph_retrieve`;
- the four positive direct/meaningful fixtures select at least one allowed
  `bridge_paths_any` route;
- both false-relation fixtures select none of their `forbidden_paths`;
- both false-relation fixtures record an inspected rejection with
  `HUB_SHORTCUT` or `SEMANTIC_BRIDGE_MISSING`;
- all selected steps contain non-empty exact evidence spans;
- selected path endpoint recall, path precision, rejected counts, hub rate,
  evidence bytes, estimated tokens, latency, and omissions are reported;
- every fixture stays within configured hop/node/path/byte/token limits;
- deterministic digest excludes roots, temporary paths, and latency;
- production source contains no fixture IDs, corpus aliases, gold paths, or
  benchmark question strings.

## Implementation Tasks

### Task 1: Lock pure traversal contracts

**Files:** `src/loci/graph/traversal.py`, `tests/graph/test_traversal.py`

Write failing tests for validation, filtering, orientation, deterministic
simple paths, cycle control, budgets, offsets, and hub threshold. Implement the
smallest pure engine that passes without filesystem or service imports.

### Task 2: Add filtered one-hop traversal

**Files:** `src/loci/graph/retrieval.py`, `src/loci/service.py`,
`tests/test_service.py`

Write failing tests for domain filters, incoming/either orientation, per-seed
caps, omissions, and diagnostics. Implement the additive service without
touching Stage 1 exact-neighbour behavior.

### Task 3: Add exact evidenced paths

**Files:** `src/loci/graph/retrieval.py`, `src/loci/service.py`,
`tests/test_service.py`

Write failing tests for endpoint validation, direction, evidence hydration,
whole-path rejection, cost accounting, and continuation. Implement the exact
path envelope and keep its claim limited to an evidenced edge sequence.

### Task 4: Add question-shaped ranking and rejection

**Files:** `src/loci/graph/traversal.py`, `src/loci/graph/retrieval.py`,
`src/loci/service.py`, `tests/graph/test_traversal.py`,
`tests/test_service.py`

Write failing direct, meaningful multi-hop, semantic-missing, hub-shortcut, and
attribute-routing tests. Reuse bounded tokenization, expose score components,
and keep every rejection explainable.

### Task 5: Expose MCP contracts

**Files:** `src/loci/mcp_server.py`, `tests/test_mcp_server.py`

Register the three thin handlers, assert generated schemas, and prove discovery
and round trips from a new stdio process.

### Task 6: Build the read-only frozen replay

**Files:** `benchmarks/graph_traversal_stage4.py`,
`tests/graph/test_traversal_benchmark.py`

Implement the temporary mirror/contribution adapter and scoring after the
production APIs exist. Keep gold data downstream of retrieval. Run all ten
questions and inspect every selected and rejected path.

### Task 7: Document and run the gate

**Files:** `README.md`, both Loci skill files, this plan

Document interpretation and budgets, run focused/full/fresh-process/build/self-
index verification, record benchmark metrics and digest, then update this plan
to `implemented; technical review gate passed; Stage 5 ready for owner review`
only if every gate claim passes.

## Verification Commands

```bash
.venv/bin/python -m pytest tests/graph/test_traversal.py -q
.venv/bin/python -m pytest tests/test_service.py tests/test_mcp_server.py -q
.venv/bin/python -m pytest tests/graph/test_traversal_benchmark.py -q
.venv/bin/python -m pytest tests/ -q
.venv/bin/python -m compileall -q src benchmarks
uv build
.venv/bin/python benchmarks/graph_traversal_stage4.py \
  --contract /Users/brummerv/llm-wiki/tests/fixtures/graph_shape_traversal_stage3.json \
  --llm-wiki-root /Users/brummerv/llm-wiki \
  --ai-graph-root /Users/brummerv/phluxxed/ai_graph_ideas \
  --brain-root /Users/brummerv/.anvil-brain/codex \
  --output /tmp/loci-graph-traversal-stage4.json
loci index /Users/brummerv/loci --incremental
loci verify /Users/brummerv/loci
git diff --check
shasum -a 256 \
  /Users/brummerv/llm-wiki/tests/fixtures/graph_shape_traversal_stage3.json
```

Self-index and verify must run sequentially. A verify launched concurrently
with index can correctly observe transient content drift and is not valid gate
evidence.

## Implementation Result

Stage 4 passed its technical gate on 2026-07-13. The final implementation keeps
the three public functions in `src/loci/service.py` as context-loading and
error-mapping wrappers; the bounded query engine and evidence hydration live in
`src/loci/graph/retrieval.py`, while `src/loci/graph/traversal.py` remains pure.
The review pass also fixed deterministic offset continuation, reserved declared
endpoints inside the node budget, prevented target-to-target search truncation,
removed an unused shortest-path helper, narrowed measurement routing, and
validated temporary mirror destinations.

Final frozen replay:

| Metric | Result |
| --- | ---: |
| Expected endpoints reached | 15 / 15 |
| Positive path fixtures selected | 4 / 4 |
| False-path rejections observed | 2 / 2 |
| Forbidden paths selected | 0 |
| Selected evidence complete | yes |
| Configured budgets satisfied | yes |
| Mean selected-path precision | 0.452 |
| Mean rejected-path precision on labeled false cases | 0.125 |
| Serialized rejections | 48 |
| Hub-shortcut rejections | 38 (0.792 of serialized rejections) |
| Mean response bytes | 17,961.6 |
| Mean estimated response tokens | 4,490.7 |
| Mean latency | 114.380 ms |
| Deterministic digest | `a90419f35db75fde268234ea91685b5d18878a3c1b743dc8cf7a50f98ea88944` |

Verification evidence:

- focused traversal, benchmark, service, and fresh-process MCP tests:
  `89 passed`;
- complete repository suite: `381 passed`;
- Python compilation: passed for `src` and `benchmarks`;
- source distribution and wheel: built successfully;
- self-index: healthy, 983 symbols and 513 exact graph edges;
- sequential self-verify: 983 / 983 passed, no failures;
- `git diff --check`: passed;
- frozen benchmark checksum remained
  `c52def1bdf592ad735149d199910f74183598eccd9ccf8064335fa0cd0e84e27`.

The review verdict is **approve Stage 4**: correctness, trust boundaries,
boundedness, provenance, compatibility, and benchmark behavior all meet this
plan. This verdict does not authorize Stage 5 automatically. Stage 5 changes
the `llm-wiki` runtime provider, so the owner reviews this evidence and the
legacy-provider rollback boundary before that cross-repository integration.

## Stage 5 Consumer Integration Result

The llm-wiki consumer integration technical gate passed on 2026-07-14 without
changing Loci production code. The Context Compiler now uses
`loci_graph_retrieve` as its default `graph` implementation through an external
read-only mirror; `graph_backend = "legacy"` remains the explicit rollback and
there is no silent fallback.

llm-wiki validates paths and exact authored evidence at its own boundary. For
inferred relationship questions, only paths crossing Loci's distinct explained
anchor clusters carry the compiler's `bridge` role. Accepted paths confined to
one subject cluster remain inspectable support and cannot establish a different
relationship. This preserves the Stage 4 boundary: Loci returns retrieval
evidence, while llm-wiki owns candidate roles, coverage, answerability,
sufficiency, stop semantics, and final budgets.

The unchanged frozen contract checksum is
`c52def1bdf592ad735149d199910f74183598eccd9ccf8064335fa0cd0e84e27`.
Two stable final runs produced the same timing-excluded Stage 5 digest,
`a8fe96152358f2d4cb3a5e163a5c9402f9581bc776148523defea85ce047d2e2`.
The current compiler achieved 0.944 mean endpoint recall, 1.0 required-path
completion, 1.0 bridge-evidence completion, 1.0 refusal readiness, 1.0 exact
literal recall, and 0.0 unsupported-shortcut rate. The runner now records
corpus content digests and refuses a run if either live corpus changes during
measurement.

Both false-hub and both cannot-answer fixtures stopped insufficient with the
semantic `candidate_exhausted` reason. Normal rejected-path diagnostics remain
inspectable without misreporting the provider as degraded.

Review evidence was `322 passed, 2 skipped, 14 subtests passed` in llm-wiki,
`381 passed` in Loci, successful Python compilation, successful offline source
and wheel builds, clean Loci index/verification, and clean diff checks. The
detailed consumer plan and evidence remain in
`/Users/brummerv/llm-wiki/docs/superpowers/plans/2026-07-13-extensible-graph-retrieval-stage-5.md`.

This result makes Stage 5 ready for owner review. It does not authorize removal
of the legacy provider; that still requires later rollout evidence and an owner
decision.

## Stage 4 Review Gate

The agent must inspect and report these observable claims before recommending
Stage 4:

- Stage 1 exact neighbours and all Stage 2/3 contracts remain compatible;
- filters exclude disallowed namespaces, edge types, and resolution tiers;
- reverse traversal never erases stored edge direction;
- no returned path repeats a node;
- every selected path step has non-empty cached evidence at the persisted line;
- no partial path survives unavailable evidence or evidence-budget exhaustion;
- hop, node, path, byte, and estimated-token limits are enforced and reported;
- explicit path output says `edge_sequence`, not semantic proof;
- all four positive frozen relation fixtures select an allowed path;
- neither frozen false-relation fixture selects a forbidden endpoint route;
- both false-relation traces show the rejected candidate and stable reason;
- exact-attribute and measured/cannot-answer fixtures do not gain a graph-level
  sufficiency or answerability assertion;
- selected/rejected path precision, endpoint reach, hub rate, bytes, estimated
  tokens, latency, omissions, and digest are visible;
- frozen checksum is unchanged;
- no benchmark gold or domain vocabulary entered production code;
- focused and complete tests, compilation, build, fresh-process MCP, self-index,
  sequential verification, and `git diff --check` pass.

If the meaningful and false multi-hop fixtures cannot be separated using
generic edge evidence and degree, stop. Do not add corpus-specific keywords or
expected paths. The architecture decision would be whether Stage 2 profiles
need an explicit semantic composition policy or whether model-assisted bridge
classification belongs in a later optional layer.

Passing Stage 4 does not authorize Stage 5 runtime integration automatically.
Stage 5 changes a second repository and replaces an active compiler provider,
so the owner reviews the benchmark outcome and rollback boundary first.

## Risks and Mitigations

| Risk | Impact | Mitigation |
| --- | --- | --- |
| Reach is mistaken for proof | High | Exact path says edge sequence; question retrieval applies semantic rejection; no sufficiency field |
| Direction disappears under undirected search | High | Stored edge unchanged; every step records forward/reverse |
| Dense hubs create persuasive false routes | High | Corpus-derived degree penalty plus hard rejection when bridge evidence is missing |
| Generic lexical bridge rule overfits benchmark | High | Gold isolation tests; no domain terms; inspect all traces; stop rather than tune fixtures |
| A useful bridge is rejected | Medium | Preserve rejected path and reason; caller can inspect exact path separately |
| Evidence hydration reads stale/live data | High | Refresh first, read cache only, trust persisted hash validation |
| Dense graphs exhaust memory or output | High | Hard filters and hop/node/path/offset/evidence caps before search and serialization |
| Added options widen Stage 1 semantics | High | New filtered-neighbour API; existing exact API untouched |
| Benchmark mutates user wikis | High | Temporary canonical mirrors; read-only source access; cleanup on exit |
| Scores become truth confidence | Medium | Name retrieval score; expose components; categorical trust filter remains separate |

## Explicitly Deferred

- `llm-wiki` adapter installation or compiler/provider replacement;
- answerability, sufficiency, refusal, or final synthesis;
- model-assisted bridge classification;
- semantic edge-composition or transitivity policy in graph profiles;
- executable extractors inside the Loci MCP process;
- whole-page or linked-source hydration;
- heuristic resolution admission by default;
- import/dependency or resolved-reference extraction;
- persisted query/path caches or a new graph database;
- mutation tools;
- removal of the legacy `llm-wiki` graph provider.
