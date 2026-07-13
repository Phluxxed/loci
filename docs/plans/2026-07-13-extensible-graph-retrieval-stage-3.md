# Plan: Extensible Graph Retrieval Stage 3

**Status:** implemented; technical review gate passed; Stage 4 authorized

**Date:** 2026-07-13

**Scope:** precise, explained graph-anchor selection from a question or explicit
indexed seeds

**Depends on:** Stage 1 commit `797e881` and the approved, currently uncommitted
Stage 2 implementation

**Frozen benchmark:**
`/Users/brummerv/llm-wiki/tests/fixtures/graph_shape_traversal_stage3.json`

**Frozen benchmark SHA-256:**
`c52def1bdf592ad735149d199910f74183598eccd9ccf8064335fa0cd0e84e27`

## Goal

Turn a natural-language question into a small set of indexed graph start nodes
without treating broad corpus overlap as evidence. Every inferred anchor must
explain which terms and indexed fields caused its selection. Explicit indexed
seeds bypass inference completely.

Stage 3 selects starting nodes only. It does not traverse edges, claim that two
anchors are related, hydrate answer evidence, rank paths, or decide whether a
question is answerable.

## Authorization and Review Posture

Stage 2 passed its technical gate and the project owner authorized continued
implementation on 2026-07-13. Implementation mechanics remain delegated to the
agent; a product-level review is required only if benchmark evidence forces a
change to the approved direction.

The existing `loci_search` contract remains unchanged. Anchor selection is a
new graph-retrieval capability because its output has different semantics:
search returns matching symbols for navigation, while anchors are bounded,
collapsed graph start nodes for later traversal.

## Governing Evidence

### Extensible graph design

`docs/design/2026-07-13-extensible-graph-retrieval-design.md` requires Stage 3
to:

- produce a small, explained anchor set from a question;
- let explicit seeds override inferred anchors;
- collapse Markdown page-root and section duplication;
- prevent broad term overlap from nominating the whole corpus;
- replay the ten frozen questions without traversal;
- report anchor precision, endpoint recall, bytes, estimated tokens, and
  latency against the accepted baseline.

### Earlier graph trust design

`docs/design/2026-06-10-graph-layer-design.md` requires unresolved guesses to
remain distinguishable from exact facts. An inferred anchor therefore means
only “this indexed node matched the question.” It is not a graph edge, a
supported relationship, or an answerability claim.

### Frozen baseline

The accepted `llm-wiki` run recorded:

- 5.6% expected endpoint-page recall for the no-graph/current-compiler routes;
- 121/121 or 115/121 raw anchors in `ai_graph_ideas`;
- 25/25 or 24/25 raw anchors in Brain;
- mean raw direct-graph candidate output of about 190,133 bytes;
- no required semantic bridge evidence despite broad endpoint reach.

The benchmark contains ten mirrored question shapes: direct relation,
meaningful bridge, false hub shortcut, exact attribute, and cannot answer. Its
gold pages are evaluation data only. Production ranking must not read the
benchmark or special-case its paths, corpora, domains, or questions.

### Live implementation audit

The current search path is:

```text
loci_search MCP
    -> service.search_symbols()
    -> IndexStore.search()
    -> _score_symbol_detail()
```

Current search correctly exposes symbol scores, Markdown hierarchy, retrieval
cost, and `match_scope`. It intentionally returns symbol matches, so one file
may occupy many rows. On the frozen questions, long `log.md` headings and
repeated sections often outrank the expected page even though the relevant page
is present in the index.

Stage 3 must use the same indexed symbol fields but apply graph-anchor-specific
normalization, file collapse, corpus specificity, and hard output bounds.

## Stage 3 Decisions

### Existing search remains compatible

Do not change `IndexStore.search()`, `search_symbols()`, `loci_search`, their
scoring weights, result shapes, or usage logging. Search is a navigation API
with valid existing consumers and tests.

Add a separate pure anchor selector under `loci.graph`. The service supplies
the already validated index and graph diagnostics; the MCP handler remains a
thin transport boundary.

### Markdown inference collapses by file

All indexed Markdown symbols from one `file_path` form one inferred anchor
unit. The selector:

1. scores individual symbols and page metadata;
2. keeps the strongest matching symbol as the explanation span;
3. uses the file's earliest indexed page root as its canonical graph node;
4. falls back to the matching symbol's valid `root_id`, then the matching
   symbol itself, when no page root exists;
5. returns at most one anchor for the file.

This works for documents with one page root, documents with several top-level
roots, and section-only Markdown. It neither invents a synthetic graph node nor
requires Stage 2 profile materialization.

Non-Markdown symbols remain separate anchor units because two functions in one
source file are not interchangeable graph starts.

### Explicit seeds are exact

When `seed_ids` is non-empty:

- validate every seed against the current index;
- remove exact duplicate IDs while preserving input order;
- return those exact nodes;
- do not tokenize, search, infer, normalize to a Markdown root, or append
  question-derived anchors.

An explicit section seed therefore remains that section. This makes override
semantics literal and avoids silently changing caller intent.

### Inferred ranking is deterministic and domain-neutral

Question normalization:

- Unicode input is bounded before work begins;
- alphanumeric terms are case-folded deterministically;
- grammatical/question and generic request-intent stop words are removed;
- duplicate terms preserve first occurrence;
- at most 32 meaningful terms participate in scoring.

Candidate ranking uses only indexed, domain-neutral fields:

- relative file path and basename;
- symbol name and qualified name;
- signature;
- summary and docstring;
- indexed keywords;
- retained frontmatter scalar/string-list fields.

The selector computes corpus document frequency for query terms. Rare terms
receive more weight; terms present across much of the corpus contribute less.
Short title/path matches receive a density bonus, while long headings do not
win merely by containing many common query words. `_templates` paths are
excluded from inferred anchors but remain legal explicit seeds.

Candidates qualify when they have either a title/path/name signal or at least
two meaningful matched terms. This admits exact named entities such as `Codex`
or `Rowan` while rejecting one-word body overlap from broad prose.

Ordering is deterministic by descending score, then file path, then node ID.
Scores are retrieval ranking evidence only and must not be described as truth
confidence.

### Inferred anchors have two hard caps

The caller supplies `max_anchors`, default 10 and bounded to 1..32. The
ten-anchor default is the smallest tested bound that clears the frozen Stage 3
endpoint-recall gate while remaining far below the corpus-relative cap.

The effective inferred cap is the smaller of:

- `max_anchors`; and
- a corpus cap strictly below 10% of eligible anchor units when the corpus has
  at least 11 units.

For smaller corpora, one inferred anchor is allowed. Explicit seeds are bounded
only by `max_anchors` because the caller intentionally selected them.

The response reports the requested and effective caps, eligible units,
qualified candidates, collapsed symbols, returned anchors, and omitted count.

## Pure Anchor API

Add `src/loci/graph/anchors.py`:

```python
MAX_GRAPH_QUESTION_BYTES = 16_384
MAX_GRAPH_QUERY_TERMS = 32
MAX_GRAPH_ANCHORS = 32

@dataclass(frozen=True, slots=True)
class GraphAnchor:
    node_id: str
    matched_symbol_id: str
    name: str
    score: float | None
    matched_terms: tuple[str, ...]
    match_scope: tuple[str, ...]

@dataclass(frozen=True, slots=True)
class GraphAnchorSelection:
    mode: Literal["explicit", "inferred"]
    anchors: tuple[GraphAnchor, ...]
    question_terms: tuple[str, ...]
    eligible_units: int
    qualified_candidates: int
    collapsed_symbols: int
    requested_max_anchors: int
    effective_max_anchors: int
    omitted_candidates: int

def select_graph_anchors(
    symbols: Sequence[Mapping[str, Any]],
    question: str,
    seed_ids: Sequence[str],
    *,
    max_anchors: int,
) -> GraphAnchorSelection: ...
```

The pure selector raises `GraphContractError` with existing boundary codes:

- `INVALID_INPUT` for an empty question without seeds, oversized question,
  invalid limits, invalid seed values, or too many explicit seeds;
- `GRAPH_ENDPOINT_NOT_FOUND` for explicit seeds absent from the index.

The service translates these errors into `LociError` without changing their
codes, messages, or details.

## Service API

Add to `src/loci/service.py`:

```python
def graph_anchors(
    repo: str | Path,
    question: str,
    seed_ids: list[str] | None = None,
    *,
    max_anchors: int = 10,
    ensure_fresh: bool = False,
) -> dict[str, Any]: ...
```

Exact inferred success shape:

```json
{
  "schema_version": 1,
  "repo": "/absolute/repository/path",
  "question": "How are Codex and Rowan related?",
  "selection": "inferred",
  "question_terms": ["codex", "rowan", "related"],
  "anchors": [
    {
      "node": {
        "id": "entities/codex.md::Codex#section",
        "namespace": "loci",
        "kind": "section",
        "attributes": {
          "language": "markdown",
          "file": "entities/codex.md",
          "line": 1,
          "end_line": 40
        }
      },
      "matched_symbol_id": "entities/codex.md::Codex#section",
      "name": "Codex",
      "score": 12.345,
      "reason": {
        "kind": "inferred",
        "matched_terms": ["codex"],
        "match_scope": ["file_path", "symbol_name"]
      }
    }
  ],
  "counts": {
    "indexed_nodes": 100,
    "eligible_units": 30,
    "qualified_candidates": 4,
    "collapsed_symbols": 70,
    "returned_anchors": 2,
    "omitted_candidates": 2
  },
  "budget": {
    "requested_max_anchors": 10,
    "effective_max_anchors": 2
  },
  "diagnostics": []
}
```

Explicit responses use the same stable fields with:

- `selection: "explicit"`;
- `question_terms: []`;
- `score: null`;
- `reason.kind: "explicit_seed"`;
- empty `matched_terms` and `match_scope`;
- requested and effective caps equal to the unique seed count limit.

Persisted Stage 2 graph diagnostics are copied into the response. Anchor
selection still succeeds against the valid symbol index when graph extensions
are degraded.

The response never contains `sufficient`, `answerable`, `supported`, or a
relationship assertion.

## MCP API

Add to `src/loci/mcp_server.py`:

```python
@mcp.tool()
def loci_graph_anchors(
    repo: str,
    question: str,
    seed_ids: list[str] | None = None,
    max_anchors: int = 10,
) -> CallToolResult:
    """Select a small, explained set of graph anchors for a question."""
    return _handle_loci_error(
        lambda: graph_anchors(
            repo,
            question,
            seed_ids,
            max_anchors=max_anchors,
            ensure_fresh=True,
        )
    )
```

No CLI command is added. The Stage 3 production interface is MCP-first.

## Benchmark Replay

Add `benchmarks/graph_anchor_stage3.py` as a read-only runner. It accepts:

```bash
.venv/bin/python benchmarks/graph_anchor_stage3.py \
  --contract /Users/brummerv/llm-wiki/tests/fixtures/graph_shape_traversal_stage3.json \
  --ai-graph-root /Users/brummerv/phluxxed/ai_graph_ideas \
  --brain-root /Users/brummerv/.anvil-brain/codex \
  --output /tmp/loci-graph-anchor-stage3.json
```

The runner:

- validates the frozen schema fields it consumes;
- calls `graph_anchors()` without explicit seeds or traversal;
- records returned IDs/files and explanations for inspection;
- scores expected-page hits after Markdown file collapse;
- records per-fixture precision, endpoint recall, anchor fraction, serialized
  bytes, estimated tokens, and latency;
- records aggregate expected endpoint slots/hits and mean metrics;
- emits a deterministic digest that excludes latency;
- never edits either corpus or the frozen contract.

`tests/graph/test_anchor_benchmark.py` exercises contract validation, scoring,
and deterministic digest behavior with temporary public fixtures. The normal
test suite does not require the private live corpora or external frozen file.

## Exact Files

### New production and benchmark files

- `src/loci/graph/anchors.py`
- `benchmarks/__init__.py`
- `benchmarks/graph_anchor_stage3.py`

### Modified production files

- `src/loci/service.py`
- `src/loci/mcp_server.py`

### New tests

- `tests/graph/test_anchors.py`
- `tests/graph/test_anchor_benchmark.py`

### Modified tests

- `tests/test_service.py`
- `tests/test_mcp_server.py`

### Documentation

- `README.md`
- `skills/loci/SKILL.md`
- `.claude/skills/loci/SKILL.md`
- this plan

No index schema or persisted graph schema changes in Stage 3.

## Implementation Tasks

### Task 1: Freeze pure anchor contracts and validation

**Files:**

- `src/loci/graph/anchors.py`
- `tests/graph/test_anchors.py`

**Acceptance criteria:**

- empty/oversized questions, invalid limits, invalid seeds, excessive seeds,
  and missing seed IDs fail with exact structured codes;
- explicit seeds bypass inference, preserve exact order, and de-duplicate IDs;
- constants bound question bytes, terms, and anchor count;
- serialization inputs contain only finite JSON-compatible values.

**Verification:**

```bash
.venv/bin/python -m pytest tests/graph/test_anchors.py -q
```

### Task 2: Implement inferred ranking and Markdown collapse

**Files:**

- `src/loci/graph/anchors.py`
- `tests/graph/test_anchors.py`

**Acceptance criteria:**

- Markdown root/section matches collapse to one file anchor;
- the best matching section remains visible as `matched_symbol_id`;
- code symbols in one file remain separate anchor units;
- rare title/path terms outrank common long-prose overlap;
- inferred templates are excluded;
- one-word exact entity names remain eligible;
- broad generic overlap cannot exceed the corpus-relative cap;
- ties are deterministic.

### Checkpoint A: Pure selection

- focused anchor tests pass;
- no service, MCP, storage, or persisted schema changes have entered the diff;
- `git diff --check` is clean.

### Task 3: Add service envelope and degraded-health behavior

**Files:**

- `src/loci/service.py`
- `tests/test_service.py`

**Acceptance criteria:**

- inferred and explicit responses match the exact envelope;
- graph diagnostics are preserved without blocking symbol selection;
- no answerability or relationship assertion appears;
- existing search and graph-neighbour results are unchanged.

### Task 4: Expose the MCP tool through a fresh process

**Files:**

- `src/loci/mcp_server.py`
- `tests/test_mcp_server.py`

**Acceptance criteria:**

- `loci_graph_anchors` appears in the exact tool list;
- inferred anchors survive a fresh stdio process;
- explicit seed override and structured missing-seed errors cross MCP intact;
- the read performs the existing freshness check.

### Task 5: Add deterministic benchmark replay

**Files:**

- `benchmarks/graph_anchor_stage3.py`
- `tests/graph/test_anchor_benchmark.py`

**Acceptance criteria:**

- public temporary fixtures prove scoring and digest stability;
- the frozen live contract runs without mutation;
- every fixture records inspectable selected anchors and explanations;
- timing is measured but excluded from the deterministic digest.

### Task 6: Update agent-facing documentation

**Files:**

- `README.md`
- `skills/loci/SKILL.md`
- `.claude/skills/loci/SKILL.md`

**Acceptance criteria:**

- all three surfaces list `loci_graph_anchors` accurately;
- docs distinguish search matches, anchors, exact neighbours, and graph health;
- docs do not imply that Stage 3 performs traversal or answers questions.

## Test Matrix

### Validation and explicit seeds

- non-string, empty, and whitespace-only question without seeds;
- question over 16 KiB;
- `max_anchors` below 1 or above 32;
- invalid seed value;
- more unique seeds than `max_anchors`;
- missing seed endpoint;
- duplicate seed order;
- explicit section remains exact;
- explicit template remains legal;
- explicit seeds suppress all inference.

### Inferred anchors

- stop-word removal and 32-term bound;
- Markdown root/child duplicate collapse;
- multiple top-level Markdown roots collapse by file;
- matched section explanation retained;
- non-Markdown symbol separation;
- path/title/entity signal;
- metadata signal;
- rare-term weighting;
- long-heading density control;
- template exclusion;
- deterministic tie order;
- caller cap;
- strict-below-10% corpus cap;
- one-anchor behavior for tiny corpora;
- zero qualified candidates is a successful empty result.

### Service and MCP

- exact inferred envelope;
- exact explicit envelope;
- persisted degraded diagnostics preserved;
- missing repo and missing seed errors;
- stale source refresh;
- fresh-process tool discovery and round trip;
- unchanged `loci_search`, `loci_graph_neighbors`, and `loci_graph_health`.

### Benchmark

- malformed contract rejection;
- expected-page precision/recall scoring;
- empty-gold behavior;
- response byte/token accounting;
- latency-excluded deterministic digest;
- frozen checksum unchanged;
- all ten frozen questions replayed without traversal.

## Verification Commands

```bash
.venv/bin/python -m pytest tests/graph/test_anchors.py -q
.venv/bin/python -m pytest tests/graph/test_anchor_benchmark.py -q
.venv/bin/python -m pytest tests/test_service.py tests/test_mcp_server.py -q
.venv/bin/python -m pytest tests/ -q
.venv/bin/python -m compileall -q src benchmarks
uv build
.venv/bin/python benchmarks/graph_anchor_stage3.py \
  --contract /Users/brummerv/llm-wiki/tests/fixtures/graph_shape_traversal_stage3.json \
  --ai-graph-root /Users/brummerv/phluxxed/ai_graph_ideas \
  --brain-root /Users/brummerv/.anvil-brain/codex \
  --output /tmp/loci-graph-anchor-stage3.json
loci index /Users/brummerv/loci --incremental
loci verify /Users/brummerv/loci
git diff --check
shasum -a 256 \
  /Users/brummerv/llm-wiki/tests/fixtures/graph_shape_traversal_stage3.json
```

## Stage 3 Review Gate

The agent must inspect and report these observable claims before recommending
Stage 3:

- explicit seeds return exactly the indexed nodes the caller supplied;
- inferred Markdown anchors contain at most one node per file;
- every inferred anchor names its matched terms and indexed match scopes;
- no inferred fixture returns 10% or more of eligible corpus anchor units;
- expected endpoint recall across the fifteen frozen endpoint slots is at
  least 90%;
- anchor precision, bytes, estimated tokens, and latency are reported rather
  than hidden behind the recall target;
- the two false-relation and two cannot-answer questions do not acquire any
  relationship or sufficiency assertion in Stage 3 output;
- the benchmark contract checksum is unchanged;
- existing search, exact-neighbour, health, indexing, and verification behavior
  remains compatible;
- no traversal, path ranking, hub penalty, hydration, compiler integration, or
  import extraction entered the diff.

If endpoint recall misses the target, the agent may adjust only generic ranking
mechanics supported by per-fixture traces. It must not add corpus aliases,
fixture IDs, expected paths, question strings, or domain vocabulary to
production code.

Stage 4 remains blocked until this evidence passes and the agent recommends the
implementation. The project owner has waived routine technical ceremony; only
a product-level change in direction returns for a separate decision.

### Final verification evidence

- Complete suite: `334 passed in 37.71s`.
- Focused graph/service/MCP suite: `69 passed in 6.87s`.
- Source and benchmark compilation: passed.
- Package build: `dist/loci-0.1.0.tar.gz` and
  `dist/loci-0.1.0-py3-none-any.whl` built successfully.
- Fresh self-index: 856 symbols, 463 exact containment edges, healthy graph.
- Self-index verification after the completed refresh: 856 checked, 856
  passed, 0 failed.
- Fresh stdio process: `loci_graph_anchors` present and returned a bounded,
  healthy inferred response.
- Frozen benchmark: 14/15 expected endpoint slots, 93.3% recall, all corpus
  caps satisfied, maximum anchor fraction 5.7471%.
- Benchmark cost: mean 6,320.8 response bytes, 1,580.8 estimated tokens, and
  61.29 ms measured latency.
- Benchmark precision: mean 14.0%. This is intentionally reported as a Stage 4
  ranking input, not hidden by the recall pass.
- The only missed endpoint was
  `papers/tactic-kg-faithful-small-agent-kg-construction.md` on `AI-D1`; the
  paired idea page was selected. No fixture-specific rule was added to recover
  it.
- Benchmark deterministic digest:
  `49183a023f690c4e52d5c7473e0a81a2826215f6e84081774f4f2200822916d1`.
- Frozen benchmark SHA-256 remains
  `c52def1bdf592ad735149d199910f74183598eccd9ccf8064335fa0cd0e84e27`.
- `git diff --check`: clean.

The agent recommends Stage 3. The review gate passed, and the owner's standing
authorization to continue permits Stage 4 implementation without another
routine approval stop.

## Risks and Mitigations

| Risk | Impact | Mitigation |
| --- | --- | --- |
| Anchor score is mistaken for truth confidence | High | Call it ranking evidence; return terms/scopes; make no support assertion |
| Search compatibility regresses | High | Separate selector and API; do not modify current search scoring or shape |
| Markdown sections flood the result | High | One inferred anchor unit per file |
| Long logs dominate through term count | High | Per-symbol density, corpus document frequency, and no cross-section score accumulation |
| Common domain words nominate most pages | High | Stop words, specificity weighting, qualification threshold, and hard corpus cap |
| Exact named entities are lost by a two-term threshold | Medium | One-term path/title/name signal remains eligible |
| Benchmark tuning leaks private domain rules into loci | High | Generic fields only; inspect traces; forbid fixture/corpus vocabulary in production |
| Large questions or seed lists create unbounded work/output | Medium | 16 KiB question, 32 terms, 32 anchors, explicit limit validation |
| Degraded extension data blocks retrieval | Medium | Select against valid symbol index and include persisted diagnostics |

## Explicitly Deferred

- edge traversal of any depth;
- path discovery or ranking;
- edge type/resolution filters;
- hub penalties and cycle control;
- source hydration and literal evidence extraction;
- node/path/byte/token continuation budgets beyond the bounded anchor envelope;
- answerability, sufficiency, refusal, or semantic support;
- llm-wiki adapter/compiler integration;
- profile state filters and ranking hints;
- imports and resolved code references;
- changing existing search behavior;
- persisted query caches or a new storage engine.
