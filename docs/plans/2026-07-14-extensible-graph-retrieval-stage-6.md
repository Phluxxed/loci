# Plan: Extensible Graph Retrieval Stage 6

**Status:** implemented, reviewed, and owner-accepted 2026-07-15

**Date:** 2026-07-14

**Repository:** `/Users/brummerv/loci`

**Stage:** 6 of the extensible graph-retrieval roadmap

## Goal

Make the graph substrate useful over ordinary code repositories by adding
trustworthy, directed, file-level import relationships.

The first completed vertical slice must let an agent:

1. identify a source-code file as a stable graph node;
2. inspect the indexed file that it imports;
3. traverse the dependency in the correct direction through the existing graph
   service and MCP tools;
4. inspect the exact import statement that supports the edge;
5. see unresolved imports with explicit reasons instead of losing them; and
6. repeat the read after a fresh process or incremental reindex with the same
   deterministic result.

Stage 6 does not add call graphs, symbol-to-symbol reference resolution,
orientation analysis, a graph database, model-assisted extraction, or a second
import-specific traversal engine.

## Approval Boundary

Owner approval on 2026-07-15 authorized implementation of the following
decisions:

- code files become additive `kind="file"` symbols so graph endpoints remain in
  the authoritative symbol registry;
- import edges use `namespace="loci"`, `type="imports"` or
  `type="imports_type"`, and `resolution="import-resolved"`;
- raw and resolved import records persist inside `index.json.graph`, not in a
  separate top-level import graph;
- existing generic traversal tools read resolved import edges;
- a new bounded `loci_graph_imports` read exists only to inspect resolved and
  unresolved import records;
- `loci_graph_neighbors` remains compatibility-stable and continues to return
  only exact outgoing `loci:contains` edges; and
- Python and JavaScript/TypeScript/TSX resolve exactly in this stage, while Go
  and Rust imports are extracted and reported without pretending that their
  module systems were resolved.

Owner approval of this plan authorizes implementation of Stage 6 only. A second
review gate is required before Stage 6 is called complete or work begins on
resolved references or calls.

## Reconciled Sources

### Extensible graph-retrieval design

`docs/design/2026-07-13-extensible-graph-retrieval-design.md` establishes the
current ownership boundary:

- loci owns generic indexed nodes, typed edges, provenance, freshness,
  traversal, ranking, budgets, and diagnostics;
- built-in import and resolved-reference edges belong in loci;
- domain consumers own answerability and sufficiency; and
- every asserted edge must retain direction, resolution tier, and evidence.

Stages 1 through 5 have implemented and reviewed the graph contract, profiles
and contributions, anchor selection, bounded traversal, and the llm-wiki
consumer integration. Stage 6 is therefore additive work on the proven graph
substrate, not a fresh graph architecture.

### Original graph-layer design

`docs/design/2026-06-10-graph-layer-design.md` supplies the trust rules retained
here:

- a definite in-repository import uses `import-resolved` rather than `exact`;
- the edge is directed from importer to imported file;
- unresolved or ambiguous names never become asserted edges;
- extraction and resolution are deterministic and model-free; and
- cross-file calls remain deferred until import resolution is trustworthy.

### Import/dependency research plan

`docs/plans/2026-07-01-import-dependency-graph.md` remains valuable for its
tree-sitter node research, Python and JS/TS resolution rules, same-name
collision guard, re-export coverage, type-only import flag, and incremental
staleness warnings.

Its pre-substrate architecture is superseded as follows:

| Earlier proposal | Stage 6 decision |
| --- | --- |
| Top-level `index.json.imports` list | Persist typed import records inside `index.json.graph` |
| Separate resolved import graph | Materialize standard `GraphEdge` records in the shared graph |
| `loci_imports` plus generic CLI command | Add bounded MCP-first `loci_graph_imports`; no CLI command |
| File paths as implicit endpoints | Add stable indexed file symbols and use their IDs |
| Import-specific traversal | Use `loci_graph_traverse_neighbors`, `loci_graph_paths`, and `loci_graph_retrieve` |
| `parse_file()` return-type change considered risky | Keep `parse_file()` unchanged; use a separate import extractor |
| Resolved records retained incrementally | Retain observations, then re-resolve all current observations against the current file set |

## Live Baseline

The plan is grounded in the implementation at Loci commit `79c7b15`:

- `GRAPH_SCHEMA_VERSION == 1` for public graph contributions and retrieval
  envelopes; persisted `GraphIndexState` also used that shared constant before
  Stage 6;
- `INDEX_SCHEMA_VERSION == 5`;
- `EXTRACTOR_VERSION == 4`;
- `symbols` is the authoritative graph-node registry;
- `GraphIndexState` persists profiles, node overlays, edges, contributions,
  input hashes, and diagnostics;
- `GraphEdge` already supports `resolution="import-resolved"`;
- `src/loci/graph/builtins.py` currently emits only exact Markdown
  `loci:contains` edges;
- `validate_graph_edges()` currently accepts only those containment edges;
- `loci_graph_neighbors` is deliberately pinned to exact outgoing containment;
- `loci_graph_traverse_neighbors`, `loci_graph_paths`, and
  `loci_graph_retrieve` already support namespace, edge-type, resolution, and
  direction filters; and
- the traversal engine's safe default resolutions are currently `exact` and
  `declared`, with `import-resolved` reserved for this contributor.

There are no indexed file nodes today. Import edges cannot honestly use a
function, class, or same-named symbol as a proxy for a file. Stage 6 must close
that node-model gap before extracting edges.

## Scope

### In scope

- one deterministic file node for every indexed Python, TypeScript, TSX,
  JavaScript, Go, and Rust source file;
- tree-sitter extraction of import observations from those languages;
- exact in-repository resolution for Python and relative JS/TS/TSX imports;
- JS/TS re-export extraction;
- TS type-only import classification;
- Go and Rust extract-and-report records with no false resolved edge;
- generic graph edges for resolved imports;
- persisted import observations and incremental re-resolution;
- additive graph-health counts;
- a paginated MCP diagnostic read for all/resolved/unresolved import records;
- fresh-process, schema-migration, and incremental correctness tests; and
- agent navigation examples over a purpose-built code repository and Loci
  itself.

### Out of scope

- symbol-to-symbol reference or call edges;
- bare-name repository-wide matching;
- dynamic non-literal `import()` or `require()` calls;
- CommonJS `require()` extraction;
- `.jsx`, `.mjs`, or `.cjs` support before those extensions are indexed;
- TypeScript `baseUrl` or `paths` aliases;
- Node package `exports` resolution;
- Python installed-environment, namespace-package, or `pyproject.toml`
  package-root interpretation;
- `go.mod`, workspaces, vendor resolution, or standard-library classification;
- Cargo module-tree or crate resolution;
- following re-export chains to an original definition;
- treating `TYPE_CHECKING` imports differently from ordinary Python imports;
- a CLI import command;
- a graph database or new graph-analysis dependency;
- model calls, semantic judges, or LLM-generated relationships; and
- changes to llm-wiki answerability, sufficiency, or final context policy.

## Architecture Decisions

### 1. File nodes remain ordinary indexed symbols

Stage 1 deliberately made `symbols` the authoritative node registry. Stage 6
preserves that decision by adding one synthetic `Symbol` for each indexed code
file rather than creating a parallel file-node table.

The exact helper is:

```python
FILE_NODE_QUALIFIED_NAME = "__file__"

def make_file_symbol(
    relative_path: str,
    *,
    language: str,
    content_hash: str,
) -> Symbol:
    ...
```

The symbol contract is:

```json
{
  "id": "src/loci/service.py::__file__#file",
  "name": "service.py",
  "qualified_name": "__file__",
  "kind": "file",
  "language": "python",
  "file_path": "src/loci/service.py",
  "byte_offset": 0,
  "byte_length": 0,
  "signature": "src/loci/service.py",
  "docstring": "",
  "summary": "",
  "content_hash": "<sha256-of-whole-file>",
  "decorators": [],
  "keywords": ["loci", "service"],
  "metadata": {"loci": {"file_node": true}},
  "line": 1,
  "end_line": 1
}
```

Rules:

- the ID is produced by
  `make_symbol_id(relative_path, "__file__", "file")`;
- `byte_length` is zero so `loci_get` does not accidentally return an entire
  file when an agent asks for a graph anchor;
- the path remains available through `file_path` and `signature`;
- the full file hash supplies stable freshness identity;
- file nodes are emitted after zero-symbol warning calculation so they do not
  hide extraction failures;
- file nodes are emitted for supported code files even when no ordinary symbol
  was extracted; and
- Markdown keeps its existing page-root and section model. Stage 6 does not add
  duplicate Markdown file nodes or perturb the frozen wiki benchmark corpus.

`loci_outline` and `loci_search` will observe the additive `kind="file"`
symbols. Existing symbol IDs and ordinary symbol shapes remain unchanged.

### 2. Import extraction stays separate from `parse_file()`

Add `src/loci/parser/imports.py` with these contracts:

```python
ImportUnresolvedReason = Literal[
    "external",
    "not_indexed",
    "ambiguous",
    "unsupported_language",
    "invalid_specifier",
]

@dataclass(frozen=True, slots=True)
class RawImport:
    source_file: str
    language: str
    line: int
    text: str
    specifier: str
    imported_name: str | None
    type_only: bool
    is_reexport: bool
    source_hash: str

def extract_imports(
    path: Path,
    *,
    source_file: str,
    language: str,
    source_hash: str,
) -> list[RawImport]:
    ...
```

`parse_file()` retains its current input and `list[Symbol]` return contract.
Only changed files pay for the additional deterministic tree-sitter parse.
Index-time measurement in the review gate will decide whether a later shared
parse artifact is worth the added coupling; Stage 6 does not pre-optimize it.

Add an optional defaulted field to `LanguageSpec`:

```python
import_node_types: tuple[str, ...] = ()
```

The configured nodes are:

| Language | Nodes |
| --- | --- |
| Python | `import_statement`, `import_from_statement` |
| JavaScript/TypeScript/TSX | `import_statement`, source-bearing `export_statement` |
| Go | recursively nested `import_spec` |
| Rust | `use_declaration` |

`.tsx` uses the existing `typescript` language spec through `EXTENSION_MAP`;
do not populate an unused parallel TSX configuration.

The extractor emits one `RawImport` per independently resolvable target:

- `import a, b` emits two observations;
- `from pkg import a, b` emits one observation for `a` and one for `b`;
- `from pkg import *` resolves to `pkg` itself;
- one JS/TS import or re-export emits one observation; and
- each Go import spec emits one observation even inside a grouped declaration.

Extraction failure raises a typed internal `ImportExtractionError`. The service
catches it per file, keeps the valid symbol index, and persists one warning
diagnostic with code `GRAPH_IMPORT_EXTRACTION_FAILED`. It must never silently
turn a failed parse into a trustworthy empty import set.

### 3. Persist observations inside the graph envelope

Add `src/loci/graph/imports.py`:

```python
ImportStatus = Literal["resolved", "unresolved"]

@dataclass(frozen=True, slots=True)
class ImportRecord:
    raw: RawImport
    source_id: str
    target_file: str | None
    target_id: str | None
    status: ImportStatus
    unresolved_reason: ImportUnresolvedReason | None

    def to_dict(self) -> dict[str, JSONValue]: ...

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> ImportRecord: ...

def resolve_import(
    raw: RawImport,
    *,
    file_nodes: Mapping[str, Symbol],
) -> ImportRecord:
    ...

def materialize_import_edges(
    records: Sequence[ImportRecord],
    *,
    file_nodes: Mapping[str, Symbol],
) -> list[GraphEdge]:
    ...
```

Add a required `imports: tuple[ImportRecord, ...]` field to
`GraphIndexState`. It serializes under `index.json.graph.imports`. Introduce
`GRAPH_STATE_SCHEMA_VERSION = 2` for that persisted envelope while keeping
`GRAPH_SCHEMA_VERSION = 1` for existing contribution and retrieval contracts.
This separation prevents an internal cache migration from invalidating valid
repository-owned graph extensions.

The top-level `index.json` shape does not change, so `INDEX_SCHEMA_VERSION`
remains `5`. Bump `EXTRACTOR_VERSION` from `4` to `5` because new file symbols
and import observations require a complete rebuild of old indexes.

An old graph state or extractor version causes the existing freshness path to
perform a full reindex. It must not produce a valid-looking graph with zero
imports.

### 4. Re-resolve retained observations on every index

Incremental indexing retains raw observations for unchanged source files,
replaces them for changed files, and drops them for deleted files. It then
re-runs deterministic resolution over the complete current observation set and
current file-node map.

This order is required because an unchanged import can change meaning when:

- a previously missing target file is added;
- its target file is deleted;
- a more specific Python submodule appears; or
- an extension/index candidate changes under the fixed JS/TS resolution order.

Retaining previously resolved edges without re-resolution is forbidden.

The exact `materialize_graph()` addition is keyword-only:

```python
def materialize_graph(
    repo_path: Path,
    symbols: Sequence[Symbol],
    file_hashes: Mapping[str, str],
    profiles: Sequence[LoadedGraphProfile],
    contributions: Sequence[LoadedGraphContribution],
    *,
    raw_imports: Sequence[RawImport] = (),
    input_hashes: Mapping[str, str] | None = None,
    diagnostics: Sequence[GraphDiagnostic] = (),
) -> GraphIndexState:
    ...
```

It resolves imports before combining:

1. exact built-in Markdown containment;
2. import-resolved built-in code edges;
3. declared profile edges; and
4. validated external contribution edges.

Final edge deduplication remains deterministic.

### 5. Edge contract and evidence

A runtime import produces:

```json
{
  "from": "src/loci/service.py::__file__#file",
  "to": "src/loci/graph/state.py::__file__#file",
  "type": "imports",
  "directed": true,
  "namespace": "loci",
  "resolution": "import-resolved",
  "evidence": {
    "file": "src/loci/service.py",
    "line": 23,
    "content_hash": "<sha256-of-whole-source-file>"
  }
}
```

Type-only TypeScript imports use `type="imports_type"`. This preserves the
old plan's requirement that data-flow consumers can exclude type-only
dependencies through the existing `edge_types` filter without expanding the
stable `GraphEdge` schema.

`type_only` is true only when the whole dependency is type-only. A mixed
`import {type X, Y} from "./m"` remains a runtime `imports` edge because `Y`
requires the module at runtime. `export type ... from` is type-only.

Re-exports remain dependency edges of the appropriate runtime or type-only
type. `ImportRecord.is_reexport` preserves the distinction for the diagnostic
read.

If several statements create the same `(type, source file, target file)` edge,
the graph keeps one edge using the earliest supporting statement. The import
record read retains every statement.

Extend `validate_graph_edges()` by dispatching built-in validation by
`(namespace, type)`:

```python
def validate_graph_edges(
    edges: list[GraphEdge],
    *,
    indexed_nodes: Mapping[str, Mapping[str, Any]],
    file_hashes: Mapping[str, str] | None = None,
    imports: Sequence[ImportRecord] = (),
) -> None:
    ...
```

The existing defaults preserve current containment-only call sites. Import
validation requires:

- both endpoints exist and have `kind="file"`;
- source and target are different;
- namespace is `loci`;
- type is `imports` or `imports_type`;
- direction is true;
- resolution is `import-resolved`;
- evidence file equals the source node's file;
- evidence line matches a resolved persisted import record;
- evidence hash equals the current source-file hash; and
- the matching record resolves to the edge's target ID.

Same-named files or symbols never participate in resolution.

### 6. Resolution algorithms

#### Python

Resolution is path arithmetic over the current indexed `.py` file-node set.
It does not import Python modules, inspect the active environment, or execute
packaging configuration.

Before resolving absolute names, derive candidate package roots from indexed
`__init__.py` chains:

- the repository root is always one candidate root;
- for each topmost contiguous package directory, its parent is a candidate
  root (`src/loci/__init__.py` makes `src` a root for module `loci`);
- namespace packages without `__init__.py` are not inferred in Stage 6; and
- if more than one candidate root produces a distinct valid target, the import
  is `unresolved/ambiguous` rather than first-root-wins.

- Absolute `a.b.c` maps to base path `a/b/c`.
- Relative dots walk from the importing file's directory: one dot keeps the
  current package directory, two dots move up one directory, and so on.
- A module base tries `B.py` before `B/__init__.py`.
- `from M import N` first tries `M/N.py`, then `M/N/__init__.py`; if neither is
  indexed, it falls back to the resolved file for `M`.
- `from M import *` targets `M`.
- `import a.b.c` emits one edge to the deepest exact indexed target.
- No bare symbol-name fallback is allowed.
- A specifier with no indexed target is `unresolved/not_indexed`.

#### JavaScript, TypeScript, and TSX

Only relative `./` and `../` specifiers resolve in Stage 6. Bare package names
are `unresolved/external`.

For a relative base `P`, try exactly:

1. `P.ts`
2. `P.tsx`
3. `P.js`
4. `P/index.ts`
5. `P/index.tsx`
6. `P/index.js`

The first indexed file wins. This ordering is public behavior and is covered by
tests. A relative specifier with no candidate is `unresolved/not_indexed`.

#### Go and Rust

Stage 6 extracts source text and specifiers but records
`unresolved/unsupported_language`. It emits no `import-resolved` edge for Go or
Rust. This is preferable to pretending that string similarity implements
`go.mod` or Cargo module semantics.

### 7. Generic traversal remains the graph API

Resolved edges are available through the existing calls:

```python
graph_traverse_neighbors(
    repo,
    ["src/loci/service.py::__file__#file"],
    namespaces=["loci"],
    edge_types=["imports"],
    resolutions=["import-resolved"],
    direction="outgoing",
)
```

Incoming traversal answers "what imports this file?" without reversing the
stored edge. `graph_paths()` supplies bounded dependency paths between known
file nodes. `graph_retrieve()` may use import edges for question-shaped code
navigation.

Update `src/loci/graph/traversal.py` safe defaults from:

```python
("exact", "declared")
```

to:

```python
("exact", "declared", "import-resolved")
```

This activates the tier that Stage 1 explicitly reserved as trusted after its
built-in contributor lands. Heuristic edges remain excluded.

Do not widen `graph_neighbors()` or `loci_graph_neighbors`; their documented
Stage 1 compatibility contract remains exact outgoing Markdown containment.

### 8. Bounded import-record inspection

Unresolved imports cannot become graph edges because they have no trustworthy
target. A dedicated read is therefore required for observability, not
traversal.

Add this service API:

```python
def graph_imports(
    repo: str | Path,
    *,
    file: str | None = None,
    status: Literal["all", "resolved", "unresolved"] = "all",
    offset: int = 0,
    limit: int = 100,
    ensure_fresh: bool = False,
) -> dict[str, Any]:
    ...
```

Validation:

- `file`, when supplied, must be a normalized repository-relative path;
- `status` must be one of the three exact values;
- `offset >= 0`;
- `1 <= limit <= 500`; and
- invalid input uses the existing `LociError` structured envelope.

The stable response is:

```json
{
  "schema_version": 1,
  "repo": "/absolute/repo",
  "file": null,
  "status": "all",
  "items": [
    {
      "source_file": "src/loci/service.py",
      "source_id": "src/loci/service.py::__file__#file",
      "target_file": "src/loci/graph/state.py",
      "target_id": "src/loci/graph/state.py::__file__#file",
      "specifier": "loci.graph.state",
      "imported_name": "GraphIndexState",
      "language": "python",
      "line": 23,
      "text": "from loci.graph.state import GraphIndexState",
      "type_only": false,
      "is_reexport": false,
      "status": "resolved",
      "resolution": "import-resolved",
      "unresolved_reason": null
    }
  ],
  "counts": {
    "total": 1,
    "resolved": 1,
    "unresolved": 0,
    "returned": 1
  },
  "pagination": {
    "offset": 0,
    "limit": 100,
    "next_offset": null
  }
}
```

Items sort by `(source_file, line, specifier, imported_name, target_file)`.
Counts apply after the optional `file` filter but before status filtering and
pagination; `returned` is the current page size. `next_offset` is null when the
status-filtered result is exhausted, and otherwise advances within that same
status-filtered ordering.

Add the MCP wrapper:

```python
@mcp.tool()
def loci_graph_imports(
    repo: str,
    file: str | None = None,
    status: str = "all",
    offset: int = 0,
    limit: int = 100,
) -> CallToolResult:
    """Inspect bounded resolved and unresolved built-in import records."""
    return _handle_loci_error(
        lambda: graph_imports(
            repo,
            file=file,
            status=status,
            offset=offset,
            limit=limit,
            ensure_fresh=True,
        )
    )
```

No CLI command is added. The production boundary remains MCP-first.

### 9. Health and index output are additive

`index_repo()` adds:

```json
{
  "graph_file_nodes_indexed": 42,
  "graph_imports_indexed": 137,
  "graph_imports_resolved": 96,
  "graph_imports_unresolved": 41
}
```

`graph_health().counts` adds the same four fields.

Ordinary external or unsupported imports do not degrade graph health. They are
expected unresolved records available through `loci_graph_imports`. Extraction
failures, invalid persisted records, unsafe paths, or corrupt evidence remain
warning/error diagnostics and set health to `degraded` through the existing
status rule.

This avoids dumping thousands of normal package imports into the unpaginated
health diagnostic list.

## Dependency Order

```text
Persisted import contracts + schema bump
                 |
                 v
Code-file symbols -----> tree-sitter observations
                 |                 |
                 +--------+--------+
                          v
                deterministic resolution
                          |
                          v
               generic GraphEdge materialization
                     /             \
                    v               v
          existing traversal    import-record read
                    \               /
                     v             v
                 MCP + fresh-process tests
                          |
                          v
                  review evidence and docs
```

Implementation is sequential through the first materialized Python edge.
Language fixtures can then be added independently, but no parallel work is
required or assumed.

## Implementation Tasks

### Task 1: Add file-node and persisted import contracts

**Description:** Define stable code-file symbols, raw import observations,
resolved import records, exact serialization, and the graph schema migration.

**Files:**

- `src/loci/parser/symbols.py`
- `src/loci/parser/imports.py` (new)
- `src/loci/graph/imports.py` (new)
- `src/loci/graph/state.py`
- `tests/graph/test_state.py`

**Acceptance criteria:**

- file-node IDs and shapes match this plan exactly;
- `ImportRecord` serialization is deterministic and rejects unknown/missing
  fields and invalid status/reason combinations;
- persisted graph-state schema 1 is rejected as stale rather than read as
  empty, while contribution schema 1 remains valid; and
- no existing symbol ID or `parse_file()` signature changes.

**Verification:**

```bash
.venv/bin/python -m pytest tests/parser/test_symbols.py tests/graph/test_state.py -q
```

**Dependencies:** none.

**Estimated scope:** medium, five files.

### Task 2: Extract import observations without changing symbol parsing

**Description:** Add per-language import-node configuration and tree-sitter
extraction for Python, JS/TS/TSX, Go, and Rust. Use inline temporary sources in
tests so repository skip rules cannot hide integration fixtures.

**Files:**

- `src/loci/parser/languages.py`
- `src/loci/parser/imports.py`
- `tests/parser/test_languages.py`
- `tests/parser/test_imports.py` (new)

**Acceptance criteria:**

- all specified syntax forms produce exact line, text, specifier, flags, and
  source hash;
- grouped Go imports are found recursively;
- TS type-only imports and source-bearing re-exports are classified;
- multiple Python targets produce separate observations; and
- malformed/unsupported syntax cannot become a resolved record silently.

**Verification:**

```bash
.venv/bin/python -m pytest tests/parser/test_languages.py tests/parser/test_imports.py -q
```

**Dependencies:** Task 1.

**Estimated scope:** medium, four files.

### Task 3: Resolve Python imports and emit the first graph edge

**Description:** Implement Python path arithmetic and one complete service-level
vertical slice from two temporary `.py` files to an `import-resolved` graph
edge with exact source evidence.

**Files:**

- `src/loci/graph/imports.py`
- `src/loci/graph/builtins.py`
- `src/loci/graph/materialize.py`
- `tests/graph/test_imports.py` (new)
- `tests/graph/test_materialize.py`

**Acceptance criteria:**

- absolute, relative, package, submodule, star, and deepest-module rules match
  this plan;
- repository-root and inferred `src/`-layout packages resolve, while duplicate
  valid package roots report `ambiguous`;
- no name-based fallback exists;
- source-to-target direction and `import-resolved` tier are exact; and
- duplicate source/target statements choose the earliest edge evidence while
  retaining all records.

**Verification:**

```bash
.venv/bin/python -m pytest tests/graph/test_imports.py tests/graph/test_materialize.py -q
```

**Dependencies:** Tasks 1 and 2.

**Estimated scope:** medium, five files.

### Checkpoint A: First exact import slice

- [ ] A two-file Python repository produces two file symbols.
- [ ] `A imports B` persists as `A -> B`, never `B -> A`.
- [ ] The edge points to file-node IDs and carries the importing statement's
      file, line, and current source hash.
- [ ] A missing module produces an unresolved record and no edge.
- [ ] Focused tests pass with no model or judge call.

### Task 4: Add JS/TS/TSX resolution and type-only edge separation

**Description:** Implement the fixed relative-candidate order, re-export
handling, external bare-specifier reporting, and `imports_type` edges.

**Files:**

- `src/loci/graph/imports.py`
- `src/loci/graph/builtins.py`
- `tests/graph/test_imports.py`
- `tests/graph/test_materialize.py`

**Acceptance criteria:**

- candidate order is deterministic and tested when multiple candidates exist;
- bare packages are unresolved/external;
- re-exports preserve `is_reexport` in the record;
- type-only imports materialize as `imports_type`; and
- unsupported extensions do not appear through accidental filesystem probing.

**Verification:**

```bash
.venv/bin/python -m pytest tests/graph/test_imports.py tests/graph/test_materialize.py -q
```

**Dependencies:** Task 3.

**Estimated scope:** medium, four files.

### Task 5: Integrate indexing and incremental re-resolution

**Description:** Create file nodes during indexing, retain observations for
unchanged files, replace changed observations, drop deleted sources, and
re-resolve the full current set before every write.

**Files:**

- `src/loci/service.py`
- `src/loci/storage/index_store.py`
- `src/loci/graph/materialize.py`
- `tests/test_service.py`
- `tests/storage/test_index_store.py`

**Acceptance criteria:**

- old extractor/graph versions trigger a full reindex;
- unchanged source observations survive incremental indexing;
- adding a target resolves an unchanged observation;
- deleting a target removes the edge and marks the record unresolved;
- changing/deleting a source updates or removes its observations and evidence;
- file nodes do not suppress existing zero-symbol warnings; and
- index output includes the four additive counts.

**Verification:**

```bash
.venv/bin/python -m pytest tests/test_service.py tests/storage/test_index_store.py tests/graph/test_materialize.py -q
```

**Dependencies:** Tasks 3 and 4.

**Estimated scope:** medium, five files.

### Task 6: Harden built-in edge validation

**Description:** Extend the store boundary to validate containment and import
edges by type without weakening the existing exact containment contract.

**Files:**

- `src/loci/graph/contracts.py`
- `src/loci/storage/index_store.py`
- `tests/graph/test_contracts.py`
- `tests/storage/test_index_store.py`

**Acceptance criteria:**

- corrupt endpoint kinds, direction, tier, evidence path, line, hash, or target
  record fail with structured graph contract errors;
- valid containment still serializes unchanged;
- profile/contribution namespaces cannot assert reserved built-in import edges;
  and
- a same-named symbol or file cannot satisfy an import endpoint.

**Verification:**

```bash
.venv/bin/python -m pytest tests/graph/test_contracts.py tests/storage/test_index_store.py tests/graph/test_profiles.py -q
```

**Dependencies:** Task 5.

**Estimated scope:** medium, four files.

### Checkpoint B: Persistence and freshness

- [ ] Full and incremental indexes produce the same timing-excluded import
      digest.
- [ ] Fresh-process reads preserve edges, records, counts, and evidence.
- [ ] Added/deleted source and target files transition records correctly.
- [ ] Corrupt built-in state fails loudly; valid symbol navigation remains
      available after recoverable extraction warnings.
- [ ] Existing graph-profile and contribution tests remain green.

### Task 7: Expose bounded import records and additive health counts

**Description:** Add `graph_imports()` and extend `graph_health()` without
turning normal unresolved packages into degraded health.

**Files:**

- `src/loci/service.py`
- `tests/test_service.py`
- `tests/graph/test_state.py`

**Acceptance criteria:**

- exact response, sorting, filtering, validation, counts, and pagination match
  this plan;
- resolved and unresolved records are both inspectable;
- external/unsupported records do not create graph edges or degraded status;
  and
- extraction/corruption diagnostics still degrade health.

**Verification:**

```bash
.venv/bin/python -m pytest tests/test_service.py tests/graph/test_state.py -q
```

**Dependencies:** Tasks 5 and 6.

**Estimated scope:** small, three files.

### Task 8: Register and prove the MCP contract

**Description:** Add `loci_graph_imports`, update exact tool discovery, and
prove a fresh stdio process can inspect records and traverse the corresponding
generic graph edge.

**Files:**

- `src/loci/mcp_server.py`
- `tests/test_mcp_server.py`
- `tests/test_wrapper_routing.py`

**Acceptance criteria:**

- generated input schema exposes the exact defaults and types;
- invalid status/offset/limit returns the existing structured error envelope;
- process A indexes, process B reads the persisted records and import edge;
- the installed `loci-mcp` wrapper exposes the new tool; and
- no CLI command is added.

**Verification:**

```bash
.venv/bin/python -m pytest tests/test_mcp_server.py tests/test_wrapper_routing.py -q
```

**Dependencies:** Task 7.

**Estimated scope:** small, three files.

### Task 9: Activate the trusted tier in generic traversal

**Description:** Add `import-resolved` to safe traversal defaults while
preserving the narrow compatibility operation.

**Files:**

- `src/loci/graph/traversal.py`
- `tests/graph/test_traversal.py`
- `tests/test_service.py`

**Acceptance criteria:**

- unfiltered generic traversal includes exact, declared, and import-resolved
  edges but never heuristic edges;
- explicit filters remain authoritative;
- incoming traversal reports importers without reversing stored edges;
- bounded paths can cross import edges with evidence; and
- `graph_neighbors()` still returns only exact outgoing `loci:contains`.

**Verification:**

```bash
.venv/bin/python -m pytest tests/graph/test_traversal.py tests/test_service.py -q
```

**Dependencies:** Tasks 6 and 7.

**Estimated scope:** small, three files.

### Task 10: Update operational documentation

**Description:** Document file-node IDs, import edge types, diagnostic reads,
safe defaults, unresolved semantics, and the no-guess boundary.

**Files:**

- `README.md`
- `skills/loci/SKILL.md`
- `.claude/skills/loci/SKILL.md`
- `docs/design/2026-07-13-extensible-graph-retrieval-design.md`

**Acceptance criteria:**

- MCP-first workflows show exact import traversal and inspection examples;
- both skill copies agree;
- docs do not instruct agents to use `loci_graph_neighbors` for import edges;
- Stage 6 status and deferred resolved-reference work are explicit; and
- no obsolete top-level import store or CLI command is presented as current.

**Verification:**

```bash
diff -u skills/loci/SKILL.md .claude/skills/loci/SKILL.md
git diff --check
```

**Dependencies:** Tasks 8 and 9.

**Estimated scope:** medium, four files.

## Required Tests

The task-level tests are mandatory. The following behavioral cases must be
named or equivalently explicit in the final suite.

### Contracts and file nodes

- stable file-node ID and zero-width content span;
- file nodes exist for code files with and without ordinary symbols;
- no Markdown file-node duplication;
- ImportRecord success round trip;
- unknown/missing fields rejected;
- impossible resolved/unresolved combinations rejected;
- persisted graph-state schema 1 forces rebuild without invalidating
  contribution schema 1; and
- existing ordinary symbol serialization remains unchanged.

### Extraction

- Python `import`, multiple imports, `from`, relative `from`, star import;
- JS/TS import, TS `import type`, named type import, and re-export;
- grouped Go `import_spec` recursion;
- Rust `use_declaration` extraction;
- exact 1-indexed evidence line and statement text;
- source hash retained; and
- extraction failure produces a warning rather than silent emptiness.

### Resolution

- Python module-before-package deterministic order;
- Python repository-root and inferred `src/` package roots;
- two valid package roots produce unresolved/ambiguous, never arbitrary choice;
- relative-dot directory arithmetic;
- submodule-before-symbol fallback;
- deepest Python module only;
- JS/TS fixed file-before-directory-index order;
- bare JS/TS dependency classified external;
- same filename/symbol elsewhere never creates an edge;
- unsupported Go/Rust produces no edge; and
- source-to-target orientation never reverses.

### Incremental behavior

- unchanged source records retained;
- changed source records replaced;
- deleted source records removed;
- newly added target resolves retained source;
- deleted target invalidates retained source edge;
- source evidence hash refreshes;
- full versus incremental deterministic digest; and
- old cache cannot silently report zero imports.

### Service, traversal, and MCP

- exact `graph_imports` success schema;
- file/status filters and pagination;
- invalid input error envelopes;
- health counts and non-degrading normal unresolved imports;
- import edges visible through explicit generic filters;
- safe defaults include `import-resolved` but exclude `heuristic`;
- compatibility `graph_neighbors` remains contains-only;
- incoming traversal identifies importers;
- bounded import path preserves edge evidence;
- exact MCP tool schema/listing;
- fresh-process record and edge read; and
- installed wrapper routing.

## Full Verification

After all focused tests pass:

```bash
.venv/bin/python -m pytest tests/ -q
uv build
git diff --check
```

Then use an isolated cache and real MCP process to avoid treating the active
development cache as test state:

```bash
LOCI_BASE_DIR=/tmp/loci-stage6-review .venv/bin/python -m loci.mcp_server
```

The review harness must index a purpose-built temporary repository containing:

- Python absolute and relative imports;
- TS runtime, type-only, and re-export relationships;
- one unresolved external package;
- one unresolved missing in-repository target;
- one same-name collision trap; and
- one Go or Rust observation that remains explicitly unsupported.

It must then prove through MCP:

1. `loci_graph_imports` counts and paginates all records;
2. `loci_graph_traverse_neighbors` returns outgoing runtime imports;
3. incoming traversal returns importers without reversing edge storage;
4. `loci_graph_paths` returns an evidence-backed dependency chain;
5. `loci_graph_health` remains healthy with normal unresolved imports;
6. a fresh server process returns the same timing-excluded digest; and
7. an incremental target add/delete changes the retained source record and edge
   exactly as specified.

Finally index `/Users/brummerv/loci` in the isolated cache and record:

- symbols and file-node count;
- raw/resolved/unresolved import counts;
- graph edge count;
- full-index wall time compared with the pre-Stage-6 baseline;
- incremental no-change wall time;
- a real `service.py -> graph/state.py` or equivalent outgoing import read; and
- a real incoming blast-radius read for one imported file.

No model, semantic judge, whole-wiki audit, or frozen llm-wiki benchmark run is
required. The llm-wiki adapter supplies explicit namespace/type/resolution
filters, and Stage 6 does not add Markdown file nodes. Run the expensive frozen
benchmark only if focused compatibility tests expose an actual regression.

## Final Review Gate

Stage 6 passes only when the owner receives and approves one review packet with:

- the exact commits under review;
- focused and full test results;
- build and `git diff --check` results;
- graph/index schema migration evidence;
- the isolated real-MCP navigation transcript;
- the full versus incremental digest comparison;
- Loci self-index timing and import counts;
- confirmation that `loci_graph_neighbors` stayed contains-only;
- confirmation that no heuristic or unsupported Go/Rust edge was asserted;
- confirmation that normal unresolved imports are bounded and inspectable;
- compatibility findings for ordinary search, outline, get, graph profiles,
  contributions, and llm-wiki's explicit-filter path;
- unresolved risks or deviations from this plan; and
- an explicit recommendation to accept, revise, or roll back Stage 6.

Do not remove the import records, begin resolved-reference/call extraction, or
declare the graph roadmap complete until this gate is approved.

## Rollback

Stage 6 is additive. Rollback consists of reverting its implementation commit
set and rebuilding indexes under extractor version 4 / graph-state schema 1
code.
No repository source file or domain contribution is mutated.

During implementation, a Stage 6 failure must not leave a valid-looking partial
import graph:

- contract/schema failure forces reindex or returns a structured error;
- per-file extraction failure excludes that file's import records, persists a
  warning diagnostic, and preserves ordinary symbol navigation;
- unresolved imports persist as bounded records and never become edges; and
- no automatic fallback guesses a target.

## Risks and Mitigations

| Risk | Impact | Mitigation |
| --- | --- | --- |
| File symbols change search/outline results | Medium | Additive `kind="file"`, stable IDs, zero-width content, regression tests |
| A second tree-sitter parse slows indexing | Medium | Changed files only; measure full and incremental self-index before optimizing |
| Retained edges become stale when targets change | High | Persist observations and re-resolve the full current set every index |
| External imports flood graph health | High | Paginated import read; aggregate health counts; no per-package warning diagnostics |
| Type-only imports pollute runtime dependency paths | Medium | Separate `imports_type` edge type and preserve record flag |
| Python submodule/symbol ambiguity creates false edges | High | Fixed submodule-first path check, then containing-module fallback; no name search |
| Multiple Python package roots resolve the same module | High | Collect exact candidates and report ambiguous unless exactly one target remains |
| JS/TS resolution pretends to implement Node fully | High | Relative paths only and explicit candidate order; bare packages unresolved |
| Go/Rust strings are mistaken for resolved files | High | Extract-and-report only; no edge until module-aware resolver has its own plan |
| Default trusted tiers widen unexpectedly | Medium | Add only reserved `import-resolved`; keep heuristic excluded; explicit compatibility tests |
| Stage 6 perturbs llm-wiki benchmark behavior | Medium | No Markdown file nodes; llm-wiki explicit filters; focused compatibility tests first |

## Post-Stage-6 Roadmap Decision

The owner accepted Stage 6 on 2026-07-15 and selected the following roadmap
direction:

1. Stage 7 detailed design for module-aware Go import resolution;
2. resolved symbol references that follow definite imports;
3. cross-file calls only where both binding and import resolution are definite;
4. heuristic candidates as opt-in diagnostics, never trusted defaults; and
5. graph orientation or architecture analysis after the underlying edges have
   enough real-repository evidence.

Rust import resolution is explicitly deferred until a real Rust consumer exists.
The existing extract-and-report behavior remains the honest Rust contract.

This decision authorizes Stage 7 planning, not implementation. The Stage 7 plan
must define exact Go module-resolution semantics, APIs, files, tests,
compatibility evidence, rollback behavior, and its own owner review gate before
code changes begin.
