# loci: Extensible Graph Retrieval Layer — Design

**Status:** Stages 1-6 implemented, reviewed, and accepted; Stage 7 Go
import-resolution design pending

**Date:** 2026-07-13

**Primary consumer:** any agent navigating an indexed repository

**First domain integration:** `llm-wiki`, exercised against Brain and
`ai_graph_ideas`

## Objective

Build one trustworthy graph-retrieval substrate in loci instead of allowing
each consumer to grow its own traversal engine.

Loci will own domain-neutral retrieval mechanics:

- indexed nodes and typed edges;
- precise anchor selection;
- bounded neighbours and path traversal;
- query-aware path ranking and hub control;
- evidence, provenance, cost, omissions, and structured diagnostics.

Consumers will own domain meaning. `llm-wiki`, for example, defines knowledge
state, wiki-specific relation types, authority, answerability, sufficiency, and
the final context envelope. It supplies those semantics to loci through
validated data contracts rather than by adding wiki vocabulary to loci core.

The user experience is one agent-owned retrieval workflow that works across
code repositories and managed wikis while allowing a particular domain to add
meaning without forking loci.

## Existing Evidence

The frozen `llm-wiki` Stage 3 benchmark contains ten mirrored questions across
Brain and `ai_graph_ideas`. It established that:

- the current compiler retrieved 5.6% of expected endpoint pages;
- naive graph matching made almost every page an anchor;
- two-hop traversal produced an unsupported path on 50% of false-relation
  fixtures and three-hop traversal did so on 100%;
- page reach and path existence did not supply semantic bridge evidence;
- response envelopes could reach roughly 94,000 estimated tokens.

The benchmark therefore becomes an acceptance suite for loci. It is not a
reason to tune hop depth inside `llm-wiki`.

This design extends the trust rules in
`docs/design/2026-06-10-graph-layer-design.md`: unresolved guesses must never be
presented as facts, direction is information, edges require provenance, and
deterministic local work comes before optional model-assisted work.

The existing `docs/plans/2026-07-01-import-dependency-graph.md` remains useful
extractor research, but its proposed import-specific storage should not land
before the generic edge contract is approved. Import relationships should
become one built-in contributor to the shared graph substrate.

## Architecture

```text
Agent question or explicit seeds
              |
              v
        loci graph retrieval
   anchor search -> bounded traversal -> ranked evidence
       ^                                  |
       |                                  v
built-in extractors                 structured result
domain graph contributions          paths + evidence + cost
       ^
       |
code / markdown / llm-wiki profile
```

### Ownership boundary

| Concern | Owner |
| --- | --- |
| Symbol, file, page-root, and section indexing | loci |
| Generic `contains`, Markdown-link, and import edges; later resolved-reference edges | loci built-ins |
| Wiki relation names and knowledge-state attributes | llm-wiki profile |
| Edge validation, storage, freshness, traversal, and ranking | loci |
| Whether retrieved evidence is sufficient to answer | llm-wiki |
| Final answer and synthesis | calling agent |

Loci returns retrieval evidence. It must not claim that a question is answered
or that a domain assertion is true.

## Extension Contract

The first extension mechanism is data, not arbitrary executable plugins.
Domain code stays outside the loci MCP process and contributes validated graph
records. This keeps loci local, deterministic, testable, and safe to run over
any repository.

Two additive contracts are required.

### Graph profile

A versioned declarative profile identifies a namespace and describes how
existing indexed metadata and explicit source links map to graph attributes and
edge types. A profile may define:

- page-root or symbol selectors;
- metadata fields that may be projected onto nodes;
- explicit source fields that create directed edge types;
- allowed resolution tiers and relation types;
- default ranking hints, never unconditional truth weights;
- source roots and state filters owned by the domain.

A repository works without a profile. Profiles enrich the generic graph; they
do not replace built-in indexing.

### Graph contribution

A domain adapter may emit a versioned contribution document when declarative
mapping is insufficient. Loci validates and stores the data but does not execute
the adapter.

Minimum node reference:

```json
{
  "id": "existing-loci-symbol-or-page-root-id",
  "namespace": "llm-wiki",
  "kind": "page",
  "attributes": {"knowledge_state": "verified"}
}
```

Minimum edge record:

```json
{
  "from": "page-a-id",
  "to": "page-b-id",
  "type": "supports",
  "directed": true,
  "namespace": "llm-wiki",
  "resolution": "declared",
  "evidence": {
    "file": "concepts/page-a.md",
    "line": 18,
    "content_hash": "sha256-of-supporting-source"
  }
}
```

Rules:

- both endpoints must resolve to indexed nodes;
- evidence is mandatory for every non-`contains` edge;
- source hashes participate in freshness checks;
- unknown schema versions, edge types, endpoints, or malformed evidence fail
  loudly with structured diagnostics;
- heuristic edges remain distinguishable and excluded from trusted traversal by
  default;
- numeric confidence cannot upgrade an unresolved edge into a trusted edge;
- a profile or contribution cannot mutate repository source files.

Executable third-party extractors are explicitly deferred. Add them only if a
real domain cannot be represented through built-ins, a declarative profile, or
an externally generated contribution document.

## Retrieval Contract

The production interface remains MCP-first, backed by typed service functions.
Exact tool names are fixed during implementation planning, but the public
capabilities must remain separable:

1. inspect registered graph profiles and graph health;
2. fetch neighbours from explicit seeds with edge and trust filters;
3. find supported paths between explicit nodes;
4. retrieve question-shaped graph evidence by selecting a small anchor set and
   traversing within explicit cost limits.

Question-shaped retrieval accepts:

- repository;
- question and optional explicit seeds;
- optional domain profile;
- allowed edge types and minimum resolution tier;
- maximum hops, nodes, paths, bytes, and estimated tokens.

It returns:

- selected anchors and why each matched;
- ranked paths with every edge and its evidence;
- hydrated source spans required to interpret those paths;
- rejected paths and concise rejection reasons;
- budget usage, omissions, and continuation information;
- diagnostics for stale, missing, invalid, or degraded graph inputs.

It does not return a domain-level `sufficient: true` assertion.

## Delivery Stages and Review Gates

Each stage must be independently reviewable and leave loci working. No later
stage begins without explicit human approval.

### Stage 1: Production graph contract and one exact vertical slice

Add the versioned node, edge, provenance, and contribution contracts; persist a
single exact edge type; expose one MCP read that retrieves a seeded one-hop
neighbour with supporting evidence.

Review evidence: a tiny repository indexes cleanly, retrieves the expected edge
through MCP, rejects invalid endpoints/evidence, and survives a fresh process.

### Stage 2: Freshness and extension profiles

Add profile loading, contribution validation, incremental retention, stale
source invalidation, and structured graph-health diagnostics. Prove one generic
profile and one `llm-wiki` fixture profile without integrating the compiler.

Review evidence: changed and deleted source invalidates affected graph records;
unchanged records survive incremental indexing; repositories without profiles
retain current behaviour.

### Stage 3: Precise anchor selection

Extend current indexed search so a question produces a small, explained anchor
set. Explicit seeds override inferred anchors. Page-root/section duplication is
collapsed, and broad term overlap cannot nominate the whole corpus.

Review evidence: replay the ten frozen questions without traversal and compare
anchor precision, endpoint recall, bytes, tokens, and latency against the Stage
3 baseline.

### Stage 4: Bounded traversal and path ranking

Add neighbours, supported paths, edge filtering, hop/node/path budgets, cycle
control, hub penalties, and semantic bridge requirements. A path is returned
only with edge evidence; node reach alone is not a supported relationship.

Review evidence: replay the frozen benchmark through loci and inspect every
selected and rejected path before any llm-wiki runtime integration.

### Stage 5: llm-wiki adapter and compiler integration

Implement the domain adapter/profile in `llm-wiki`, replace its generic graph
mechanics with loci retrieval, and retain llm-wiki ownership of knowledge state,
answerability, sufficiency, and final response budgeting.

Review evidence: focused integration tests, the full suites in both repos, and
before/after benchmark traces. The old local graph provider is not removed until
compatibility and rollback behaviour are approved.

### Stage 6: Built-in code relationships

Stage 6 has folded trustworthy file-level import/dependency extraction into the
same graph substrate, using the existing import plan as research. It proves
that the layer benefits ordinary repositories rather than only wikis.

Implementation plan:
`docs/plans/2026-07-14-extensible-graph-retrieval-stage-6.md`.

The implemented operational contract is:

- indexed Python, JavaScript, TypeScript, TSX, Go, and Rust files receive stable
  zero-width `kind="file"` nodes with IDs such as
  `src/loci/service.py::__file__#file`; Markdown retains its existing page and
  section nodes without duplicate file nodes;
- exact in-repository Python imports and relative JavaScript/TypeScript imports
  emit directed `namespace="loci"`, `type="imports"|"imports_type"`,
  `resolution="import-resolved"` edges with source evidence;
- `loci_graph_imports` exposes paginated resolved and unresolved observations,
  while `loci_graph_traverse_neighbors`, `loci_graph_paths`, and
  `loci_graph_retrieve` consume the standard graph edges;
- safe unfiltered traversal includes `exact`, `declared`, and
  `import-resolved`, but never `heuristic`;
- `loci_graph_neighbors` remains the compatibility operation for exact outgoing
  `loci:contains` only and is not an import traversal API; and
- normal unresolved, ambiguous, external, or unsupported-language imports stay
  inspectable with an explicit reason, never become asserted edges, and do not
  degrade graph health.

Import observations and their resolved records persist inside
`index.json.graph`; there is no separate top-level import store and no import
CLI command. Resolution uses language-aware path rules only. It never performs
a bare-name repository search or silently manufactures a dependency.

Resolved symbol references, cross-file calls, module-aware Go/Rust resolution,
heuristic diagnostics, and architecture analysis were outside Stage 6. Each
requires its own design and review gate.

Review evidence: language-specific resolution fixtures, same-name collision
tests, bounded unresolved-record inspection, fresh-process and incremental
proofs, and agent navigation examples over a code repository. The owner accepted
the [final Stage 6 review packet](../reviews/2026-07-15-extensible-graph-retrieval-stage-6-final-review.md)
on 2026-07-15.

### Stage 7: Module-aware Go import resolution

The owner selected module-aware Go import resolution as the next graph-roadmap
target on 2026-07-15. Stage 7 will design how current extract-and-report Go
observations become deterministic in-repository edges using Go module semantics
without guessing from string or filename similarity.

Rust import resolution remains deferred because there is no current Rust
consumer. Rust observations continue to be extracted and reported as unresolved;
they must not produce trusted edges.

Stage 7 implementation has not started. Its next deliverable is a detailed plan
with exact module-resolution rules, APIs, files, fixtures, compatibility checks,
rollback behavior, and an owner review gate.

After Go resolution, the approved roadmap order is:

1. resolved symbol references that follow definite imports;
2. cross-file calls only where binding and import resolution are definite;
3. heuristic candidates as opt-in diagnostics, never trusted defaults; and
4. graph orientation or architecture analysis after the underlying edges have
   enough real-repository evidence.

## Technical Fit

### Stack

- Python 3.10+ and the current loci service/storage layers.
- Tree-sitter and current Markdown/YAML metadata extraction for built-in edges.
- Local stdio MCP as the production interface; CLI remains diagnostic only.
- No model call is required for indexing, traversal, ranking, or benchmark
  scoring.
- No graph database or new graph-analysis dependency is assumed by this design.

### Commands

```bash
# Install and run the complete suite
uv sync --extra dev
.venv/bin/python -m pytest tests/ -q

# Build the package
uv build

# Refresh and verify representative repositories
loci index /path/to/repo --incremental
loci verify /path/to/repo
```

MCP contract tests must launch `loci-mcp` through a real stdio client, matching
the existing test pattern.

### Project structure

Likely ownership, to be confirmed against the approved API plan:

```text
src/loci/parser/       built-in edge extraction only
src/loci/storage/      versioned graph persistence and freshness
src/loci/service.py    typed graph operations
src/loci/mcp_server.py thin MCP validation/transport
tests/                 unit, storage, service, and real-MCP contract tests
docs/design/           architecture and approved implementation plan
```

### Code style

Use the existing typed-function and structured-error style:

```python
def graph_neighbors(repo: str | Path, seed_ids: list[str]) -> dict[str, Any]:
    if not seed_ids:
        raise LociError("INVALID_INPUT", "At least one seed is required")
    ...
```

Public results use explicit object envelopes and stable list fields. Existing
tool outputs and function signatures remain compatible.

## Testing Strategy

- Contract tests for schema validation and stable serialization.
- Unit tests for edge filtering, ranking, cycles, budgets, and hub penalties.
- Storage tests for schema migration, atomic writes, deletion, and incremental
  freshness.
- Service tests for missing/stale repositories and structured failures.
- Real stdio MCP tests for every public graph capability.
- Frozen cross-repository benchmark tests using Brain and `ai_graph_ideas`
  snapshots or purpose-built equivalents that contain no private content.
- Deterministic result digests exclude latency while retaining measured latency
  separately.

## Boundaries

### Always

- require provenance for asserted edges;
- preserve direction and resolution tier;
- make budgets hard and omissions visible;
- keep generic repositories working with no domain profile;
- keep MCP handlers thin and core logic independently testable;
- retain a rollback path until the llm-wiki integration is proven.

### Ask first

- add an executable plugin mechanism;
- add a graph database or third-party graph-analysis dependency;
- change existing MCP result shapes or index locations;
- enable heuristic edges in trusted traversal;
- remove or deprecate the llm-wiki graph provider.

### Never

- resolve cross-file relationships by bare name and label them exact;
- treat corpus-wide term overlap as a valid anchor set;
- claim semantic support from node reach alone;
- silently drop invalid, stale, or unresolved contributions;
- let domain profiles decide that evidence is sufficient to answer;
- require the user to manually operate loci during normal agent work.

## Success Criteria

The layer is complete only when:

- the same service and MCP contracts operate over code and Markdown indexes;
- a domain profile can add typed semantics without modifying loci core;
- all returned paths include inspectable edge evidence and trust tiers;
- explicit budgets bound nodes, paths, bytes, and estimated tokens;
- the frozen ten-question benchmark retrieves at least 90% of expected endpoint
  pages while keeping inferred anchors below 10% of each corpus per question;
- both meaningful-bridge fixtures include the required bridge evidence;
- both exact-attribute fixtures include the required literal evidence;
- neither false-relation fixture asserts a supported path;
- the cannot-answer fixtures return no supported path and expose why;
- default graph-retrieval output remains at or below 32,000 bytes unless the
  caller explicitly requests continuation;
- ordinary repositories without profiles preserve current loci behaviour and
  the complete existing test suite remains green.

Benchmark targets are provisional until the design review confirms that the
gold fixtures and thresholds represent the intended user experience.

## Resolved Review Decisions

The staged implementation and its approved plans resolved the design questions:

1. profiles and contribution documents are repository-local under
   `.loci/graph/`; loci validates their data and does not execute domain code;
2. contribution ingress is file-based in the current contract rather than a
   mutable service call;
3. the resolution vocabulary is `exact`, `declared`, `import-resolved`, and
   `heuristic`, with the first three trusted by default and `heuristic`
   opt-in only; and
4. Stage 6 followed the reviewed Stage 5 llm-wiki integration and reused the
   same graph contracts rather than creating an import-specific subsystem.

Future resolved-reference or call work is a new proposal, not an unanswered
part of this design.
