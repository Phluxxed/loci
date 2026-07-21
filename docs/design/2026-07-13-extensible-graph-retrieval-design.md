# loci: Extensible Graph Retrieval Layer — Design

**Status:** Stages 1-10 implemented, reviewed, and accepted; Stage 11
implemented and engineering-reviewed, with final owner evidence acceptance
pending

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

The owner selected module-aware Go import resolution on 2026-07-15 and accepted
the detailed implementation plan on 2026-07-16. Stage 7 is implemented and
accepted as of 2026-07-17. Go observations now become deterministic
repository-local edges when the contained module evidence is sufficient,
without guessing from string, filename, or package-name similarity.

Detailed implementation plan:
`docs/plans/2026-07-15-extensible-graph-retrieval-stage-7-go-import-resolution.md`.

The implemented contract adds stable zero-width Go `kind="package"` nodes and
directed `loci:imports` / `import-resolved` edges from importer file nodes to
those package nodes. `loci_graph_imports` distinguishes package targets with
`target_kind="package"`, `target_package`, and `target_file=null`; existing
Python and JavaScript/TypeScript targets remain file-shaped. Generic filtered
traversal exposes package `directory`, `import_path`, and `package_name`
attributes. `loci_graph_neighbors` remains containment-only.

Resolution supports same-module packages, explicitly active contained
workspace modules, and conservative contained local replacements backed by
direct unambiguous requirements. It is a pure, bounded read of repository
controls: indexing does not run Go or repository code, use the network, inherit
an ambient workspace, inspect module caches, implement minimal version
selection, follow remote replacements, model vendor mode, or evaluate build or
platform constraints. Nested-module ownership and Go `internal` visibility are
enforced; invalid, ambiguous, external, missing, inaccessible, or deliberately
unsupported cases remain inspectable records without trusted edges.

At Stage 7 acceptance, Rust import resolution remained deferred because no
current Rust consumer had been identified. That rationale was superseded on
2026-07-18: Anvil now has an explicit near-term Rust requirement, so Cargo-aware
Rust resolution became a committed dependency-layer stage. Stage 9 now
implements that bounded contract; Stage 7 remains the historical record of the
earlier deferral.

The accepted plan freezes exact module-resolution rules, package-node semantics,
APIs, files, fixtures, compatibility checks, rollback behavior, and the final
implementation review gate. The final review packet records the completed gate:
`docs/reviews/2026-07-15-extensible-graph-retrieval-stage-7-final-review.md`.

### Stage 8: Deterministic JavaScript/TypeScript import resolution

The owner approved the bounded Stage 8 contract and explicitly accepted the
completed final evidence packet on 2026-07-18. Stage 8 is implemented,
reviewed, and accepted.

Detailed implementation plan:
`docs/plans/2026-07-18-extensible-graph-retrieval-stage-8-javascript-typescript-import-resolution.md`.
Final review packet:
`docs/reviews/2026-07-18-extensible-graph-retrieval-stage-8-final-review.md`.

Stage 8 extends file-level JavaScript/TypeScript resolution across `.ts`,
`.tsx`, `.mts`, `.cts`, `.js`, `.jsx`, `.mjs`, and `.cjs`. It uses contained,
bounded repository evidence from standard TypeScript/JavaScript project
configs, package manifests, declared package-json or pnpm workspaces, package
maps, self-references, and conservative legacy entries. Resolved observations
retain exact file targets and add a resolution basis plus the controls that
justified the result. Control hashes participate in freshness, so an unchanged
source import is re-resolved when its project or package configuration changes.

The resolver does not inspect installed dependencies or lockfiles, execute a
runtime, compiler, package manager, script, bundler, generator, or repository
code, or use the network. Dynamic imports, shadowable `require()` calls,
custom loaders, bundler aliases, and missing generated output remain outside
the trusted static contract. Unsupported or insufficient evidence stays an
inspectable unresolved observation and never becomes an edge.

The owner corrected the post-Stage-7 roadmap on 2026-07-18. Dependency
resolution must be trustworthy across the language portfolio before higher
semantic layers depend on it. Stage 9 implements the first item in the
corrected order. With Stage 9 accepted, the remaining order is:

1. add resolved symbol references that follow definite imports;
2. add cross-file calls only where binding and import resolution are definite;
3. expose heuristic candidates as opt-in diagnostics, never trusted defaults;
   and
4. add graph orientation or architecture analysis after the underlying edges
   have enough real-repository evidence.

"Complete" here means complete for an explicitly documented, bounded static
resolution contract. It does not authorize executing repository tools or code,
using the network, or silently approximating every runtime loader behavior.

### Stage 9: Cargo-aware Rust dependency resolution (implemented and accepted)

The owner selected Cargo-aware Rust resolution as the next dependency-layer
stage on 2026-07-18 and approved its separate implementation boundary. The
implementation and final evidence packet were explicitly accepted by the owner
on 2026-07-20:
`docs/plans/2026-07-18-extensible-graph-retrieval-stage-9-cargo-aware-rust-dependency-resolution.md`.
The completed final evidence packet is
`docs/reviews/2026-07-18-extensible-graph-retrieval-stage-9-final-review.md`.

The implementation adds bounded Cargo package/workspace/target loading, stable Rust
crate nodes, contained path and inherited workspace dependencies, explicit
module-tree construction, edition-aware paths, definite module aliases and
re-exports, and module visibility enforcement. It keeps registry/git
dependencies external and never runs Cargo, rustc, build scripts, macros,
repository code, or the network.

Because feature, target, and `cfg` activation depend on an absent build
invocation, the implemented graph is explicitly a declared-possible static
dependency graph. Rust import records distinguish unconditional relationships
from configuration-dependent relationships; divergent conditional endpoints
remain unresolved. Terminal item/symbol resolution and calls stay in later
stages.

Cargo controls participate in freshness, invalid controls degrade health
without creating refresh loops, and stable crate endpoints expose only
validated manifest/package/target/root/edition/feature attributes. The public
MCP tool set and `loci_graph_imports` input schema are unchanged. Its items add
the strict raw observation, `target_crate`, Cargo/Rust resolution provenance,
and `resolution_configuration`; graph health adds
`graph_rust_crates_indexed`.

Stages 1-10 are implemented, reviewed, and accepted. Vik explicitly accepted
the Stage 10 resolved-symbol-reference production evidence on 2026-07-20.

### Stage 10: Resolved symbol references (implemented and accepted)

The detailed Stage 10 plan was approved by the owner on 2026-07-20 for bounded,
task-by-task production implementation:
`docs/plans/2026-07-20-extensible-graph-retrieval-stage-10-resolved-symbol-references.md`.

The approved boundary adds symbol-level `references` and `references_type`
edges only where a static local binding follows an already definite import to
one exact accessible indexed symbol. It includes conservative shadowing checks
and bounded definite re-export chains across the supported Python,
JavaScript/TypeScript, Go, and Rust subsets. Unresolved imports, shadowed or
ambiguous bindings, inaccessible or unindexed targets, dynamic syntax, and
configuration-divergent Rust targets remain inspectable without becoming
edges.

Cross-file calls, heuristic candidates, and graph orientation remain later
roadmap stages. Stage 10 does not authorize executing repository code,
compilers, runtimes, package managers, or network operations.

The implementation now extracts strict import bindings, local export surfaces,
lexically owned symbol uses, and conservative shadowing evidence across the
supported Python, JavaScript/TypeScript, Go, and Rust subsets. Language-specific
resolvers can select a target only inside the exact endpoint and export surface
proven by the matched resolved import. Strict reference records are validated
against current source hashes, imports, symbols, visibility, and support before
they can materialize a directed `loci:references|references_type` edge with
`resolution="import-resolved"`.

Reference records live inside private graph-state schema 7; the outer index
schema remains 5, public graph envelopes remain schema 1, and extractor version
10 forces stale indexes through the existing complete rebuild path. Incremental
indexing reuses unchanged observations but re-resolves them when a source,
target, re-export, module/workspace/package control, or Cargo control changes.

The additive `loci_graph_references(repo, file, status, offset, limit)` MCP read
exposes bounded resolved and unresolved records. Existing generic traversal and
path tools consume the standard edges in either direction, while
`loci_graph_neighbors` remains contains-only. There is no reference CLI,
parallel traversal engine, new dependency, model call, runtime/toolchain
execution, repository-code execution, or network access.

The final evidence packet is
`docs/reviews/2026-07-20-extensible-graph-retrieval-stage-10-final-review.md`.
It records the complete 1,013-test repository gate, frozen benchmark checksum,
package build, live Loci dogfood, and installed-wrapper disposable MCP fixtures
for all four language families plus cross-language decoys. Vik explicitly
accepted that evidence on 2026-07-20.

### Stage 11: Trustworthy call relationships (implemented; owner acceptance pending)

The detailed Stage 11 implementation is governed by
`docs/plans/2026-07-20-extensible-graph-retrieval-stage-11-trustworthy-calls.md`.
It reconciles two previously separated boundaries:

- the original graph trust design's same-file calls, which were specified but
  never delivered as a dedicated stage; and
- the current roadmap's cross-file calls, which Stage 10 deliberately deferred
  until an exact imported-symbol reference existed.

The implemented stage adds one complete trustworthy call layer rather
than shipping cross-file calls while leaving the simpler local gap behind.
A directed `loci:calls` edge is permitted only when static call syntax proves
the call site and either a unique visible same-file callable binding proves the
callee with `resolution="exact"`, or one resolved Stage 10 symbol-reference
record proves it with `resolution="import-resolved"`.

The implementation remains deliberately narrower than full language call semantics.
It includes direct calls to indexed functions and methods only when binding and
caller ownership are exact. It excludes constructors, computed or dynamic
callees, receiver/trait/interface dispatch, callable values, macros, reflection,
generated code, and repository-wide name matching. Unsupported and unresolved
sites remain diagnostic records and never become trusted edges. Recursive calls
are valid trusted self-edges only when backed by a resolved call record; all
other self-edges remain invalid.

Stage 11 does not add general same-file `references` edges. Local binding proof
is used only to establish a definite call. A broader local-reference feature
remains deferred until it has a separate retrieval use case and review.

The final engineering evidence packet is
`docs/reviews/2026-07-20-extensible-graph-retrieval-stage-11-final-review.md`.
It records the complete 1,185-test repository gate, unchanged frozen benchmark,
package build, exact installed-wrapper fixtures for all four language families,
execution/network/toolchain/package-manager/judge tripwires, and fresh-process
live dogfood over Loci's own repository. Stage 11 is not marked accepted until
Vik explicitly approves that packet.

After an accepted Stage 11, architecture/orientation analysis becomes the next
planned graph capability. Heuristic candidate diagnostics remain deferred
until live dogfood shows that the trusted graph's unresolved cases justify
their cost and noise.

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

Stage 10 resolved-reference work follows its separately approved plan. Future
call work remains a new proposal, not an unanswered part of this design.
