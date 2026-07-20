# Plan: Extensible Graph Retrieval Stage 10 — Resolved Symbol References

**Status:** approved for implementation
**Date:** 2026-07-20
**Governing design:** `docs/design/2026-07-13-extensible-graph-retrieval-design.md`
**Accepted predecessor:** Stage 9, commit `11f21f8`
**Frozen compatibility benchmark:**
`/Users/brummerv/llm-wiki/tests/fixtures/graph_shape_traversal_stage3.json`
**Frozen benchmark SHA-256:**
`c52def1bdf592ad735149d199910f74183598eccd9ccf8064335fa0cd0e84e27`

## Goal

Add deterministic symbol-level reference relationships that begin at a real
indexed source symbol (or its file node for module-level code), follow a
definite static import binding, and end at one exact indexed symbol.

Stage 10 turns the file/package/crate dependency graph from Stages 6–9 into a
safe symbol-navigation graph. It must answer questions such as:

- “Which functions refer to this imported class?”
- “Where is this imported Go type used?”
- “Which exact symbol does this aliased TypeScript import refer to?”
- “Can I traverse from this function to the Rust struct it names?”

It must not claim that a use resolved when the import is unresolved, the local
name is shadowed, the exported item is ambiguous or inaccessible, or the
language/runtime behavior falls outside the bounded static contract.

## Plain-language Outcome

Today Loci can prove that one file depends on another file, Go package, or Rust
crate. It cannot yet prove that a particular function in the first file uses a
particular class, function, struct, type, or constant in the second.

After Stage 10, it can make that narrower claim when the source code provides a
complete chain of evidence:

```text
function run
  -> uses local name Alias
  -> Alias came from this exact static import
  -> that import reached this exact repository file/package/crate
  -> that endpoint exports exactly one indexed symbol named Thing
  -> references Thing
```

If any link in that chain is missing, Loci keeps an inspectable unresolved
record and emits no graph edge. In ordinary use this means better “show me the
real definition” and “who depends on this symbol?” navigation without reviving
the bare-name guessing failure that motivated the graph work.

This stage does **not** say that one function calls another. A reference proves
that code names an imported symbol. Stage 11 will add cross-file calls only
where this stage and call-site syntax together prove the callee.

## Authorization and Review Posture

Vik approved this implementation contract on 2026-07-20.

After approval, implementation may proceed task by task on `master` under the
standing repository workflow:

1. write the failing tests for one task;
2. implement only that task;
3. run its focused verification and the affected regression slice;
4. review the staged diff for scope and secrets;
5. commit and push the verified save point directly to GitHub; and
6. continue without a pull request.

No judge runs or delegated subagents are part of this plan. A final owner review
gate remains mandatory before Stage 10 is marked accepted.

## Reconciliation with Governing Documents

### Extensible graph retrieval design

`docs/design/2026-07-13-extensible-graph-retrieval-design.md` says the next
accepted-roadmap item after Stage 9 is “resolved symbol references that follow
definite imports.” This plan implements exactly that item.

It preserves the accepted generic graph substrate:

- stable indexed symbols remain the only built-in endpoints;
- built-in edges use `namespace="loci"`;
- every edge is directed and evidence-backed;
- generic traversal remains filtered by namespace, type, resolution, and
  direction;
- heuristic resolution is never admitted by default; and
- local stdio MCP remains the production agent interface.

### Original graph trust design

`docs/design/2026-06-10-graph-layer-design.md` established the central rule:
Loci must be structurally incapable of presenting a repository-wide name guess
as fact. It reserved `resolution="import-resolved"` for relationships that
follow a definite import.

Stage 10 applies that rule at symbol granularity. Same-named symbols elsewhere
in the repository are not candidates. A target must be reachable through the
matched import binding and the imported endpoint's supported export surface.

The earlier document discussed references and calls together. The accepted
2026-07 roadmap now separates them: Stage 10 adds references; Stage 11 may use
those references to add calls. This later accepted ordering takes precedence.

### Superseded import plan

`docs/plans/2026-07-01-import-dependency-graph.md` explicitly left
symbol-to-symbol resolution out of scope and was superseded for implementation
by Stage 6. Its useful constraints still apply:

- parse syntax rather than grep text;
- retain unresolved observations;
- never collide same-named symbols across files;
- preserve incremental records for unchanged files; and
- do not introduce a second top-level graph store or a separate CLI contract.

Stage 10 therefore stores reference records inside `index.json.graph`, exposes
one MCP diagnostic tool, and relies on the existing generic graph traversal
tools for resolved edges.

## Official Semantics Used

The supported subset is grounded in the language references, then checked
against the actual tree-sitter grammars installed by Loci.

- Python import search and binding:
  <https://docs.python.org/3/reference/import.html>
- Python `import` statement and local name rules:
  <https://docs.python.org/3/reference/simple_stmts.html#the-import-statement>
- Python binding and scope rules:
  <https://docs.python.org/3/reference/executionmodel.html#binding-of-names>
- TypeScript module/import/export syntax, including type-only forms:
  <https://www.typescriptlang.org/docs/handbook/modules/reference>
- Go import declarations, qualified identifiers, scope, and exported names:
  <https://go.dev/ref/spec>
- Rust `use` declarations and re-exports:
  <https://doc.rust-lang.org/stable/reference/items/use-declarations.html>
- Rust paths:
  <https://doc.rust-lang.org/stable/reference/paths.html>
- Rust visibility and privacy:
  <https://doc.rust-lang.org/stable/reference/visibility-and-privacy.html>
- Rust conditional compilation:
  <https://doc.rust-lang.org/stable/reference/conditional-compilation.html>
- Rust namespaces and name resolution:
  <https://doc.rust-lang.org/stable/reference/names/namespaces.html>

Live dependency evidence on 2026-07-20:

- Python requirement: `>=3.10`;
- `tree-sitter-language-pack` declared as `>=0.7.0` and locked/installed at
  `0.13.0`;
- MCP declared as `>=1.27,<2` and locked/installed at `1.28.0`; and
- pytest declared as `>=7.0` and installed at `9.0.2`.

Implementation tests must use the installed grammar node shapes rather than
assuming compiler AST APIs that Loci does not depend on.

## Live Implementation Baseline

Loci MCP refreshed the repository index before this plan was written. The live
index contained 1,741 symbols, 897 graph edges, 37 code file nodes, and 513
import observations; 253 imports were resolved and 260 were unresolved. Graph
health was `healthy`.

The exact current insertion points are:

- `src/loci/parser/imports.py`
  - `RawImport` stores statement evidence and limited imported-name data;
  - JavaScript/TypeScript and Go records currently do not preserve local
    binding aliases or individual named bindings;
  - `extract_import_batch()` already performs one dependency parse per changed
    file and is the correct place to add binding/reference observations without
    adding a third parse.
- `src/loci/parser/extractor.py`
  - `parse_file()` produces the authoritative indexed `Symbol` objects and
    byte spans;
  - it does not currently retain Rust item visibility/module ownership needed
    for terminal-item access checks.
- `src/loci/graph/imports.py`
  - `ImportRecord`, `resolve_imports()`, and `materialize_import_edges()` own the
    file/package/crate dependency chain;
  - all resolved built-in imports use `resolution="import-resolved"`.
- `src/loci/graph/materialize.py`
  - `materialize_graph()` resolves all imports before composing built-in,
    profile, and contributed edges;
  - it is the correct orchestration point for resolving references after
    imports and before edge deduplication.
- `src/loci/graph/contracts.py`
  - `GraphEdge` already has the required stable shape;
  - built-in validation currently recognizes only `contains`, `imports`, and
    `imports_type`.
- `src/loci/graph/state.py`
  - private graph-state schema version is 6;
  - strict round-trip state stores imports and private inline Rust module
    observations but no symbol references or export observations.
- `src/loci/service.py`
  - `index_repo()` retains raw import observations for unchanged files and
    re-resolves them against current source/control state;
  - `graph_imports()` is the existing pattern for a bounded diagnostic API;
  - `graph_health()` and index output already expose additive import counts.
- `src/loci/storage/index_store.py`
  - outer index schema is 5 and extractor version is 9;
  - `IndexStore.write()` strict-round-trips graph state and validates reserved
    built-in edges before atomic persistence.
- `src/loci/mcp_server.py`
  - MCP is the production surface;
  - no standalone import CLI exists, and Stage 10 will keep the same boundary.

The live baseline exposes the reason this cannot be implemented as a simple
name lookup: the import resolver proves endpoints, but the parser does not yet
prove which local identifier a later expression is bound to.

## Frozen Stage 10 Contract

### Included

Stage 10 includes all of the following:

1. Static import-binding observations for Python, JavaScript/TypeScript, Go,
   and Rust using the language extensions already supported by Loci.
2. Static reference observations rooted at those imported local bindings.
3. Conservative lexical shadow detection. A possibly shadowed binding cannot
   create an edge.
4. Exact selection of the smallest indexed source symbol whose byte span
   contains the reference; module-level references use the source file node.
5. Exact target-symbol lookup constrained to the resolved import endpoint and
   its supported export surface.
6. Definite named re-export chains for Python, JavaScript/TypeScript, and Rust,
   with bounded cycle/ambiguity handling.
7. Go package-qualified references to uniquely indexed exported package-level
   symbols.
8. Directed `loci:references` and `loci:references_type` edges with
   `resolution="import-resolved"` and reference-site evidence.
9. Strict persisted resolved/unresolved reference records and private export
   observations.
10. Additive index/health counters and a bounded `loci_graph_references` MCP
    diagnostic tool.
11. Exact full/incremental parity, fresh-process MCP proof, existing traversal
    compatibility, and the frozen Stage 3 benchmark guard.

### Explicitly outside Stage 10

Stage 10 does not add:

- cross-file `calls` edges or caller/callee claims;
- repository-wide bare-name fallback;
- heuristic symbol candidates in trusted traversal;
- wildcard/glob/dot import expansion;
- dynamic `import()`, runtime `require()`, `__import__()`, `importlib`,
  `getattr`, reflection, `eval`, `exec`, or computed-property resolution;
- compiler, runtime, package-manager, build-script, macro, generated-code, or
  plugin execution;
- network, installed dependency, lockfile, Cargo cache, Go toolchain, Node
  resolver, or Python environment inspection;
- TypeScript language-service/type-checker execution;
- JavaScript CommonJS export inference or shadowable `require()` binding;
- Python module `__getattr__`, namespace-package runtime merging, or `__all__`
  expansion for star imports;
- Go dot-import references, blank-import references, methods selected through
  a value, fields, or build-tag evaluation;
- Rust prelude/glob expansion, macro-generated items, trait method selection,
  associated-item resolution, generic inference, or active feature/cfg choice;
- architecture metrics, hubs, communities, subsystem naming, or graph
  orientation; or
- a new CLI command, database, dependency, model call, or LLM judge.

Unsupported syntax is either absent from reference observations because no
static import binding exists, or retained with an explicit unresolved reason
when a supported import-rooted candidate was observed but could not be proven.

## Language Resolution Contract

### Python

Supported bindings:

- `from pkg.mod import Thing`;
- `from pkg.mod import Thing as Alias`;
- `import pkg.mod as alias` followed by `alias.Thing`; and
- unaliased `import pkg.mod` only when the observed path retains the declared
  module suffix, for example `pkg.mod.Thing`.

Target symbols must be uniquely indexed module-level symbols in the exact
resolved target file. A top-level `from ... import ...` binding may act as a
named re-export for a later explicit import. Re-export cycles or multiple
reachable targets are unresolved.

`from ... import *`, dynamic module attributes, and runtime replacement of an
imported name are not resolved. Any local parameter, assignment target,
definition, nested import, loop/with/except binding, pattern binding, or other
name-binding construct that may shadow the import in the reference's lexical
scope suppresses the edge.

### JavaScript and TypeScript

Supported bindings:

- static ESM named imports, with aliases;
- namespace imports followed by a static member name;
- default imports only when a unique indexed named/default export is proven;
- `import type` and per-specifier `type` imports; and
- named or wildcard re-export chains when every hop and final export are
  unique.

Supported exports:

- exported named declarations;
- `export { local as publicName }`;
- named re-exports;
- `export * from` with ECMAScript-style ambiguity suppression; and
- a named `export default` declaration that maps to one indexed symbol.

Anonymous default exports, computed members such as `ns[name]`, CommonJS
mutation, custom loaders, ambient module synthesis, and conflicting star
exports remain unresolved or unsupported. Any possibly shadowing parameter,
variable, function, class, catch, or block binding suppresses a reference.

`references_type` is used only when the matched import binding is explicitly
type-only. A normal import used in a type position remains `references` because
the declaration itself did not guarantee runtime elision.

### Go

Supported bindings:

- the imported package's declared package name;
- an explicit package alias; and
- a selector with one statically named first member, for example
  `store.Record`.

The target must be a unique indexed package-level function, type, or constant
whose name is exported under the Go specification. The search is restricted to
the exact package node reached by the Stage 7 import record. Package-level
duplicates—commonly possible when ignored build constraints describe
alternatives—remain ambiguous.

Dot imports, blank imports, unexported identifiers, methods/fields reached
through values, and selectors whose package root may be shadowed do not create
edges. A conservative match against parameters and local declarations is
required before a package binding is definite.

### Rust

Supported bindings:

- named `use` leaves and `as` aliases;
- module bindings followed by a static path segment;
- `extern crate` bindings where the edition rules require or allow them;
- definite named `pub use` re-exports; and
- `self`, `super`, `crate`, dependency, and alias routes already proven by the
  Stage 9 crate/module resolver.

The terminal item must map to one indexed item in the exact resolved module
and be accessible from the source module under Rust's item visibility rules.
The existing module visibility chain remains authoritative. New parser
metadata records the terminal item's lexical module path, declared visibility,
and configuration status so the resolver does not infer them from names.

If `Type::method` is observed after importing `Type`, Stage 10 may link to the
imported `Type`; it does not claim that `method` is the exact associated item or
that a call occurred. Glob/prelude names, qualified trait paths, macro output,
and ambiguous value/type namespace results do not create edges.

Configuration-dependent imports may resolve only when every supported declared
alternative converges on the same terminal symbol. The reference record retains
`resolution_configuration="declared_possible"`; divergent alternatives remain
unresolved.

## Architecture Decisions

### 1. References are import-binding records before they are graph edges

The parser records the local binding established by each supported import and
the syntax of each matching use. The resolver then joins that observation to a
resolved `ImportRecord`.

There is no second resolver that starts from the referenced text and searches
the repository. This makes the unsafe operation—repo-wide same-name matching—
absent from the implementation rather than merely discouraged.

### 2. One dependency parse yields imports, exports, and references

`extract_import_batch()` already parses every changed non-Markdown source file
for imports. It will return import bindings, local export observations, and
import-rooted reference observations from the same tree. Stage 10 does not add
a third tree-sitter parse per file.

`extract_imports()` keeps its current return type and remains a compatibility
wrapper over `extract_import_batch().imports`.

### 3. Binding identity is structural and local

Each `RawImport` gains a tuple of `ImportBinding` values. A binding records its
local name, imported/exported name, kind, type-only status, module-level status,
declaration byte offset, and lexical scope byte range.

A `RawSymbolReference` embeds the bounded candidate binding set plus each parent
import's source file, line, specifier, and statement text. It never stores only
a bare local name. Most languages produce one candidate at parse time. An
unaliased Go import is the intentional exception: the package's declared local
name is known only after the Stage 7 package endpoint resolves, so the parser
retains the bounded candidate imports and the graph resolver selects the one
whose exact package metadata matches the selector root.

### 4. Shadowing fails closed

Reference extraction builds conservative lexical binding sets from syntax.
A reference is `definite` only when exactly one visible import binding owns its
root and no possibly active local binding shadows it. It is `deferred` only for
the Go default-package-name case described above; that state cannot resolve
without one exact Stage 7 package match.

Control-flow evaluation is not required. If static syntax cannot prove which
binding wins, the observation is unresolved with `binding_shadowed` or
`ambiguous_binding`. Over-suppression is acceptable; a false trusted edge is
not.

### 5. Source ownership uses indexed byte spans

For every raw reference, resolution selects the unique smallest non-synthetic
indexed symbol in the same file whose byte span contains the reference. If no
indexed symbol contains it, the stable file node is the source endpoint.

Equal-span ambiguity is unresolved rather than broken by list order. Markdown,
Go package, and Rust crate synthetic nodes are never selected as source owners.
The explicit record outcome is `ambiguous_source`; it is distinct from
`ambiguous_target` because no target was selected or evaluated.

### 6. Target lookup never leaves the imported endpoint

Target indexes are keyed by the exact Stage 6–9 endpoint:

- Python and JavaScript/TypeScript: resolved file node;
- Go: resolved package node/directory; and
- Rust: resolved module file and crate/module ownership from `RustCrateIndex`.

Only supported exports reachable from that endpoint are candidates. A symbol
with the right name in any other file or package is invisible to the resolver.

### 7. Re-exports use a bounded fixed point

Named export aliases and supported wildcard re-exports are compiled into a
finite export-surface index. Resolution iterates in deterministic source order
until stable or until `MAX_REFERENCE_REEXPORT_PASSES` is reached.

Cycles that stabilize on one target are permitted. Conflicts, candidate
explosion, non-convergence, or missing endpoints remain unresolved. Every
resolved re-export retains the import/export support records that justified the
final target.

### 8. Export and Rust item observations survive incremental reuse

Local export observations are private graph state, not a second public graph.
Rust terminal-item binding metadata is stored on the authoritative `Symbol`
record under validated `metadata["loci"]["rust_item"]` fields.

Unchanged files restore raw imports, exports, and raw reference observations
without reparsing. Every index run rebuilds endpoint/export indexes and
re-resolves all observations against current files and controls.

### 9. Resolved and unresolved references are both persisted

`GraphIndexState.symbol_references` retains one strict
`SymbolReferenceRecord` for every supported import-rooted candidate. Resolved
records identify the exact source/import/target chain. Unresolved records carry
no target and one explicit reason.

Normal unresolved outcomes do not degrade graph health. Malformed persisted
contracts, invalid parser metadata, or resource-limit extraction failures do.

### 10. Two reserved edge types preserve type-only filtering

Resolved runtime/value bindings materialize:

```json
{
  "from": "src/use.py::run#function",
  "to": "src/model.py::Thing#class",
  "type": "references",
  "directed": true,
  "namespace": "loci",
  "resolution": "import-resolved",
  "evidence": {
    "file": "src/use.py",
    "line": 8,
    "content_hash": "<sha256>"
  }
}
```

An explicitly type-only TypeScript binding uses `type="references_type"`.
Both names are reserved to the `loci` namespace. Extension namespaces cannot
publish edges under either reserved type.

### 11. Reference edges deduplicate, records do not

All observations remain in `symbol_references`. Graph materialization emits at
most one edge per `(namespace, type, from_id, to_id)`, selecting the earliest
deterministic evidence by line, column, text, and import binding.

This keeps graph size bounded without hiding repeated uses from the diagnostic
tool.

### 12. Generic traversal remains the navigation API

`loci_graph_traverse_neighbors`, `loci_graph_paths`, and
`loci_graph_retrieve` already admit `import-resolved` edges and arbitrary edge
type filters. No new traversal implementation is needed.

`loci_graph_neighbors` remains the compatibility surface for exact outgoing
`loci:contains` edges and must not widen to references.

When generic traversal omits `edge_types`, trusted reference edges join other
trusted graph edges. Consumers that want only reference relationships pass
`edge_types=["references", "references_type"]` explicitly.

### 13. MCP gains one additive diagnostic tool; CLI does not

`loci_graph_references` mirrors the bounded input and pagination contract of
`loci_graph_imports`. It exposes why a reference resolved or failed. Resolved
navigation still uses the generic graph tools.

There is no `loci references` CLI command. CLI remains an operator/diagnostic
surface, while stdio MCP is the production agent interface.

### 14. Public schemas stay additive; private graph state bumps

- `GRAPH_SCHEMA_VERSION` remains `1`: existing graph response and edge shapes
  do not change.
- `INDEX_SCHEMA_VERSION` remains `5`: the outer index envelope is unchanged.
- `GRAPH_STATE_SCHEMA_VERSION` increments from `6` to `7` because strict
  private state gains bindings, exports, and reference records.
- `EXTRACTOR_VERSION` increments from `9` to `10` because authoritative symbol
  metadata gains Rust item scope/visibility/configuration fields.

Either private-state or extractor mismatch forces one safe full reindex. There
is no in-place migration of old graph state.

### 15. No new dependency or executable trust boundary

Resolution uses Python, the installed tree-sitter grammars, immutable lookup
indexes, and existing cached source evidence. It performs no subprocess,
socket/network, compiler, runtime, package-manager, or repository-code
execution.

## Threat Model and Resource Bounds

The implementation must define and enforce these constants:

```python
MAX_IMPORT_BINDINGS_PER_DECLARATION = 1_024
MAX_SYMBOL_REFERENCES_PER_FILE = 250_000
MAX_LOCAL_EXPORTS_PER_FILE = 100_000
MAX_REFERENCE_PATH_SEGMENTS = 128
MAX_REFERENCE_RESOLUTION_CANDIDATES = 256
MAX_REFERENCE_REEXPORT_PASSES = 128
MAX_REFERENCE_SUPPORT_RECORDS = 256
```

Required safety behavior:

- exceeding a per-file extraction bound yields
  `GRAPH_REFERENCE_EXTRACTION_FAILED`, retains ordinary symbols/navigation,
  and creates no partial reference records for that file;
- exceeding a resolution/re-export bound yields an unresolved record or a
  stable graph diagnostic, never a partial edge;
- all paths remain normalized repository-relative paths;
- symlink/path containment continues to use the existing repository scan and
  evidence validation boundaries;
- current file hashes must match every reference and support record before
  persistence;
- malformed state fails strict load and triggers a full rebuild through the
  existing freshness path; and
- normal `external`, `not_indexed`, inaccessible, ambiguous, shadowed, and
  unsupported outcomes do not create edges or degrade health.

## Exact Parser Contracts

### `src/loci/parser/reference_models.py` (new)

```python
ImportBindingKind = Literal[
    "symbol",
    "namespace",
    "module",
    "glob",
    "side_effect",
    "blank",
]

BindingState = Literal[
    "definite",
    "deferred",
    "shadowed",
    "ambiguous",
    "unsupported",
]

@dataclass(frozen=True, slots=True)
class ImportBinding:
    local_name: str | None
    imported_name: str | None
    exported_name: str | None
    kind: ImportBindingKind
    type_only: bool
    module_level: bool
    declaration_start_byte: int
    scope_start_byte: int
    scope_end_byte: int
    import_line: int
    import_text: str
    import_specifier: str

@dataclass(frozen=True, slots=True)
class RawLocalExport:
    source_file: str
    language: str
    line: int
    text: str
    local_name: str | None
    exported_name: str
    type_only: bool
    definition_start_byte: int | None
    definition_end_byte: int | None
    source_hash: str

@dataclass(frozen=True, slots=True)
class RawSymbolReference:
    source_file: str
    language: str
    line: int
    column: int
    start_byte: int
    end_byte: int
    text: str
    path: tuple[str, ...]
    candidate_bindings: tuple[ImportBinding, ...]
    binding_state: BindingState
    source_hash: str

@dataclass(frozen=True, slots=True)
class ReferenceExtractionBatch:
    exports: tuple[RawLocalExport, ...]
    references: tuple[RawSymbolReference, ...]
```

Each candidate binding carries its parent `RawImport` locator through the
binding's declaration offset and the import record's file/line/specifier/text.
The serialized candidate form includes those parent fields so it can be
cross-validated after restart. All constructors validate non-empty names where
required, 1-based line/column, non-negative ordered byte ranges, safe relative
source paths, supported enums, path length, scope containment, candidate
bounds, and SHA-256 formatting.

### `src/loci/parser/imports.py`

`RawImport` adds one required strict field:

```python
bindings: tuple[ImportBinding, ...]
```

`ImportExtractionBatch` becomes:

```python
@dataclass(frozen=True, slots=True)
class ImportExtractionBatch:
    imports: tuple[RawImport, ...]
    go_package: GoPackageDeclaration | None
    exports: tuple[RawLocalExport, ...]
    references: tuple[RawSymbolReference, ...]
```

Existing call signatures remain:

```python
def extract_imports(
    path: Path,
    *,
    source_file: str,
    language: str,
    source_hash: str,
) -> list[RawImport]: ...

def extract_import_batch(
    path: Path,
    *,
    source_file: str,
    language: str,
    source_hash: str,
) -> ImportExtractionBatch: ...
```

`extract_imports()` continues to return only imports. `extract_import_batch()`
calls the reference extractor with the already parsed root/source and the
completed import observations.

### `src/loci/parser/references.py` (new)

```python
def extract_reference_batch(
    root_node: Any,
    source: bytes,
    *,
    source_file: str,
    language: str,
    source_hash: str,
    imports: Sequence[RawImport],
) -> ReferenceExtractionBatch: ...
```

The function performs no I/O and does not parse again. Language-specific
helpers collect lexical bindings, local exports, and maximal static identifier
or member/path references. Import/export declaration names are not counted as
uses. Child identifiers within one maximal path are not emitted again.

### `src/loci/parser/extractor.py`

Rust item symbols add strictly shaped metadata:

```json
{
  "loci": {
    "rust_item": {
      "lexical_module_path": ["outer", "inner"],
      "visibility": "private|pub|pub(crate)|pub(self)|pub(super)|pub(in ...)",
      "visibility_scope": ["outer"],
      "configuration": "unconditional|declared_possible"
    }
  }
}
```

The metadata is derived from the item's real tree-sitter ancestors and
attributes. `visibility_scope` is the normalized ancestor module path within
which access is allowed: `[]` means crate root, a non-empty list is a resolved
module scope, and `null` is permitted only for unrestricted `pub`. It is not
inferred from `qualified_name`. Non-Rust symbol metadata is unchanged.

## Exact Graph Contracts

### `src/loci/graph/references.py` (new)

```python
ReferenceStatus = Literal["resolved", "unresolved"]

ReferenceUnresolvedReason = Literal[
    "import_unresolved",
    "binding_shadowed",
    "ambiguous_binding",
    "ambiguous_source",
    "target_not_indexed",
    "target_inaccessible",
    "ambiguous_target",
    "unsupported_reference",
    "configuration_divergent",
]

ReferenceResolutionBasis = Literal[
    "direct_binding",
    "qualified_member",
    "reexport_chain",
]

ReferenceSupportKind = Literal[
    "import_binding",
    "local_export",
    "reexport",
    "definition",
]

@dataclass(frozen=True, slots=True)
class ReferenceSupport:
    kind: ReferenceSupportKind
    file: str
    line: int
    content_hash: str
    endpoint_id: str

@dataclass(frozen=True, slots=True)
class SymbolReferenceRecord:
    raw: RawSymbolReference
    binding: ImportBinding | None
    source_id: str
    source_kind: str
    import_source_id: str
    import_target_id: str | None
    target_file: str | None
    target_id: str | None
    target_kind: str | None
    status: ReferenceStatus
    unresolved_reason: ReferenceUnresolvedReason | None
    import_unresolved_reason: ImportUnresolvedReason | None
    resolution_basis: ReferenceResolutionBasis | None
    support: tuple[ReferenceSupport, ...]
    resolution_control_files: tuple[str, ...]
    resolution_configuration: RustResolutionConfiguration | None
```

Resolved records require one selected binding, all source/import/target fields,
one basis, non-empty support, and no unresolved reasons. Unresolved records
require one reference reason, prohibit final target fields/basis, and may carry
the selected binding and underlying import reason when known. Cross-language
provenance is rejected. A `deferred` Go observation must either select exactly
one package binding or become `ambiguous_binding`/`import_unresolved`; it cannot
be treated as definite by parser order.

Resolver APIs:

```python
@dataclass(frozen=True, slots=True)
class ReferenceResolverIndex:
    # Frozen language/endpoint/export lookups; exact fields remain private.
    ...

def build_reference_resolver_index(
    symbols: Sequence[Symbol],
    imports: Sequence[ImportRecord],
    exports: Sequence[RawLocalExport],
    *,
    go_packages: GoPackageIndex | None = None,
    rust_crates: RustCrateIndex | None = None,
) -> ReferenceResolverIndex: ...

def resolve_symbol_references(
    observations: Sequence[RawSymbolReference],
    *,
    imports: Sequence[ImportRecord],
    index: ReferenceResolverIndex,
) -> list[SymbolReferenceRecord]: ...

def materialize_reference_edges(
    records: Sequence[SymbolReferenceRecord],
) -> list[GraphEdge]: ...
```

The index is built once per materialization. Individual resolution performs no
I/O and no repository-wide name search.

Language-specific pure helpers live in:

- `src/loci/graph/_python_references.py`;
- `src/loci/graph/_javascript_references.py`;
- `src/loci/graph/_go_references.py`; and
- `src/loci/graph/_rust_references.py`.

Each helper accepts the frozen common index plus one raw observation and
returns either one exact target/support chain or one bounded failure outcome.

### `src/loci/graph/contracts.py`

`validate_graph_edges()` adds:

```python
symbol_references: Sequence[SymbolReferenceRecord] = ()
```

It recognizes only these new built-in pairs:

```python
("loci", "references")
("loci", "references_type")
```

`_validate_reference_edge()` requires:

- `directed is True`;
- `resolution == "import-resolved"`;
- an indexed source symbol/file and an indexed non-synthetic code-symbol
  target;
- evidence file/hash/line matching the current source and one resolved
  `SymbolReferenceRecord`;
- `references_type` iff the matched import binding is explicitly type-only;
- exact `from_id`/`to_id` equality with the record; and
- no matching unresolved record as substitute evidence.

Add:

```python
def validate_symbol_reference_records(
    records: Sequence[SymbolReferenceRecord],
    *,
    imports: Sequence[ImportRecord],
    exports: Sequence[RawLocalExport],
    indexed_nodes: Mapping[str, Mapping[str, Any]],
    file_hashes: Mapping[str, str],
) -> None: ...
```

This cross-validates binding snapshots against strict import records, support
against current hashes and import/export observations, source ownership, and
final target identity before any index write.

### `src/loci/graph/materialize.py`

`materialize_graph()` adds keyword-only inputs:

```python
raw_exports: Sequence[RawLocalExport] = ()
raw_symbol_references: Sequence[RawSymbolReference] = ()
```

Ordered materialization becomes:

1. resolve import records;
2. build the frozen reference/export index;
3. resolve all raw symbol-reference observations;
4. materialize Markdown contains edges;
5. materialize import edges;
6. materialize reference edges;
7. validate/merge profile and contribution data; and
8. deterministically deduplicate/sort final nodes, records, diagnostics, and
   edges.

### `src/loci/graph/state.py`

Private graph-state schema 7 is exactly:

```python
@dataclass(frozen=True, slots=True)
class GraphIndexState:
    schema_version: int
    profiles: tuple[LoadedGraphProfile, ...]
    nodes: tuple[GraphNodeRef, ...]
    edges: tuple[GraphEdge, ...]
    imports: tuple[ImportRecord, ...]
    rust_module_observations: tuple[RawImport, ...]
    exports: tuple[RawLocalExport, ...]
    symbol_references: tuple[SymbolReferenceRecord, ...]
    contributions: tuple[LoadedGraphContribution, ...]
    input_hashes: dict[str, str]
    diagnostics: tuple[GraphDiagnostic, ...]
```

Strict `to_dict()`/`from_dict()` fields are additive only through the private
version bump. Unknown/missing fields, invalid enums, unsafe paths, malformed
hashes, impossible resolved/unresolved combinations, invalid Rust metadata,
and non-JSON values fail closed.

## Exact Service and MCP APIs

### Indexing and freshness

`src/loci/service.py::index_repo()` adds:

```python
raw_exports: list[RawLocalExport]
raw_symbol_references: list[RawSymbolReference]
```

For an unchanged file it restores:

- raw imports from `previous_graph.imports`;
- inline Rust module observations from
  `previous_graph.rust_module_observations`;
- raw local exports from `previous_graph.exports`; and
- raw reference observations from
  `previous_graph.symbol_references[*].raw`.

For a changed file it calls `extract_import_batch()` for every supported code
language, retaining Go package metadata as today and adding the batch's
imports/exports/references. A per-file extraction failure retains no partial
dependency/reference batch and emits the appropriate stable diagnostic.

Index output and `graph_health()` add:

```json
{
  "graph_symbol_references_indexed": 0,
  "graph_symbol_references_resolved": 0,
  "graph_symbol_references_unresolved": 0
}
```

These counts describe records, not deduplicated edges.

### Service API

```python
def graph_references(
    repo: str | Path,
    *,
    file: str | None = None,
    status: Literal["all", "resolved", "unresolved"] = "all",
    offset: int = 0,
    limit: int = 100,
    ensure_fresh: bool = False,
) -> dict[str, Any]: ...
```

Validation exactly mirrors `graph_imports()`:

- `file`, when present, is a normalized repository-relative path;
- `status` is `all`, `resolved`, or `unresolved`;
- `offset` is a non-boolean integer `>= 0`; and
- `limit` is a non-boolean integer in `1..500`.

Filtering occurs before pagination. Counts describe the file-filtered set;
`returned` describes the current status-filtered page.

Stable record order is:

```python
key=lambda record: (
    record.raw.source_file,
    record.raw.line,
    record.raw.column,
    record.raw.start_byte,
    record.binding.import_line if record.binding is not None else 0,
    record.binding.import_specifier if record.binding is not None else "",
    record.binding.local_name if record.binding is not None else "",
    record.target_file or "",
    record.target_id or "",
)
```

### MCP API

`src/loci/mcp_server.py` adds exactly one tool:

```python
@mcp.tool()
def loci_graph_references(
    repo: str,
    file: str | None = None,
    status: str = "all",
    offset: int = 0,
    limit: int = 100,
) -> CallToolResult:
    """Inspect bounded resolved and unresolved imported-symbol references."""
```

It calls `graph_references(..., ensure_fresh=True)` through the existing
structured error adapter.

### MCP response

```json
{
  "schema_version": 1,
  "repo": "/repo",
  "file": "src/use.py",
  "status": "all",
  "items": [
    {
      "raw": {
        "source_file": "src/use.py",
        "language": "python",
        "line": 8,
        "column": 12,
        "start_byte": 120,
        "end_byte": 125,
        "text": "Alias",
        "path": ["Alias"],
        "candidate_bindings": [
          {
            "local_name": "Alias",
            "imported_name": "Thing",
            "exported_name": null,
            "kind": "symbol",
            "type_only": false,
            "module_level": true,
            "declaration_start_byte": 0,
            "scope_start_byte": 0,
            "scope_end_byte": 200,
            "import_line": 1,
            "import_text": "from .model import Thing as Alias",
            "import_specifier": ".model"
          }
        ],
        "binding_state": "definite",
        "source_hash": "<sha256>"
      },
      "binding": {
        "local_name": "Alias",
        "imported_name": "Thing",
        "exported_name": null,
        "kind": "symbol",
        "type_only": false,
        "module_level": true,
        "declaration_start_byte": 0,
        "scope_start_byte": 0,
        "scope_end_byte": 200,
        "import_line": 1,
        "import_text": "from .model import Thing as Alias",
        "import_specifier": ".model"
      },
      "source_file": "src/use.py",
      "source_id": "src/use.py::run#function",
      "source_kind": "function",
      "import_source_id": "src/use.py::__file__#file",
      "import_target_id": "src/model.py::__file__#file",
      "target_file": "src/model.py",
      "target_id": "src/model.py::Thing#class",
      "target_kind": "class",
      "status": "resolved",
      "resolution": "import-resolved",
      "unresolved_reason": null,
      "import_unresolved_reason": null,
      "resolution_basis": "direct_binding",
      "support": [
        {
          "kind": "import_binding",
          "file": "src/use.py",
          "line": 1,
          "content_hash": "<sha256>",
          "endpoint_id": "src/model.py::__file__#file"
        },
        {
          "kind": "definition",
          "file": "src/model.py",
          "line": 3,
          "content_hash": "<sha256>",
          "endpoint_id": "src/model.py::Thing#class"
        }
      ],
      "resolution_control_files": [],
      "resolution_configuration": null
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

Unresolved items set `target_file`, `target_id`, `target_kind`, `resolution`,
and `resolution_basis` to null, carry one `unresolved_reason`, and preserve the
matched import binding plus any underlying `import_unresolved_reason`.

## Resolution Outcome Table

| Condition | Record outcome | Edge |
| --- | --- | --- |
| Definite binding, import resolved, one accessible target | `resolved` | Yes |
| Same target reached by multiple identical support routes | `resolved`, deterministic support | Yes |
| Import unresolved for any Stage 6–9 reason | `unresolved/import_unresolved` plus import reason | No |
| Local name may be shadowed | `unresolved/binding_shadowed` | No |
| Multiple visible import bindings own the root | `unresolved/ambiguous_binding` | No |
| Equal smallest source spans prevent unique ownership | `unresolved/ambiguous_source` | No |
| Endpoint has no indexed target symbol | `unresolved/target_not_indexed` | No |
| Target exists but language visibility/export rules reject it | `unresolved/target_inaccessible` | No |
| Export/re-export routes reach multiple symbols | `unresolved/ambiguous_target` | No |
| Computed/dynamic/unsupported reference form | `unresolved/unsupported_reference` when observed | No |
| Rust declared alternatives converge on one symbol | `resolved`, `declared_possible` | Yes |
| Rust declared alternatives reach different symbols | `unresolved/configuration_divergent` | No |
| Wildcard/glob/dot binding has no definite local root | No symbol-reference record; import record remains | No |
| Matching name exists elsewhere in repository only | `unresolved/target_not_indexed` | No |

## Persistence and Freshness

`GraphIndexState` remains the only persisted graph owner. No top-level
`references` key is added to `index.json`.

Full and incremental rules:

1. Schema/extractor mismatch discards the old index and reparses all files.
2. Unchanged files reuse symbols, raw imports, raw exports, raw reference
   observations, and extraction diagnostics.
3. Changed files replace all of those records atomically for that file.
4. Deleted files contribute none of those records.
5. Every run rebuilds Go package, JavaScript module, Rust crate/module, export,
   and reference resolver indexes from current retained/fresh evidence.
6. Every raw reference is re-resolved even when its source file was unchanged.
7. Control-file hashes already tracked by Stages 7–9 continue to trigger
   freshness and therefore import/reference re-resolution.
8. A target definition/export addition, deletion, rename, visibility change,
   or re-export change re-resolves unchanged importing references.
9. A no-op incremental run does not parse unchanged files and serializes the
   exact same index bytes as a full run over the same repository state.
10. Fresh read-only MCP calls do not rewrite a current index.

## Exact File Changes

### New production files

- `src/loci/parser/reference_models.py`
- `src/loci/parser/_javascript_bindings.py`
- `src/loci/parser/references.py`
- `src/loci/graph/references.py`
- `src/loci/graph/_python_references.py`
- `src/loci/graph/_javascript_references.py`
- `src/loci/graph/_go_references.py`
- `src/loci/graph/_rust_references.py`

### Existing production files

- `src/loci/parser/imports.py`
- `src/loci/parser/extractor.py`
- `src/loci/graph/contracts.py`
- `src/loci/graph/materialize.py`
- `src/loci/graph/state.py`
- `src/loci/storage/index_store.py`
- `src/loci/service.py`
- `src/loci/mcp_server.py`

### New test files

- `tests/parser/test_references.py`
- `tests/graph/test_references.py`
- `tests/graph/test_reference_contracts.py`
- `tests/storage/test_reference_index_store.py`
- `tests/test_symbol_reference_service.py`
- `tests/test_symbol_reference_mcp.py`

### Existing tests updated only for changed strict/additive contracts

- `tests/parser/test_imports.py`
- `tests/graph/test_state.py`
- `tests/graph/test_materialize.py`
- `tests/graph/test_contracts.py`
- `tests/storage/test_index_store.py`
- `tests/test_service.py`
- `tests/test_mcp_server.py`
- `tests/graph/test_traversal_benchmark.py`

### Documentation

- `README.md`
- `skills/loci/SKILL.md`
- `docs/design/2026-07-13-extensible-graph-retrieval-design.md`
- `docs/reviews/2026-07-20-extensible-graph-retrieval-stage-10-final-review.md`

The denied `.claude` tree is not read or modified. Generated mirrors, if any,
remain outside this implementation scope.

## Incremental Implementation Tasks

Every task begins with failing tests and ends with focused verification plus an
atomic commit/push save point. No task is accepted merely because later tasks
could repair it.

### Task 1 — Freeze binding/reference/export parser models

**Implementation status:** complete on 2026-07-20. The focused parser gate
passes 75 tests and the full repository suite passes 859 tests. JavaScript and
TypeScript binding extraction lives in the private
`src/loci/parser/_javascript_bindings.py` helper so the existing multi-language
import parser remains below the 1,000-line review signal. Final Stage 10 owner
acceptance remains pending.

**Files:**

- `src/loci/parser/reference_models.py` (new)
- `src/loci/parser/_javascript_bindings.py` (new)
- `src/loci/parser/imports.py`
- `tests/parser/test_imports.py`
- `tests/parser/test_references.py` (new)

**Work:**

- add strict `ImportBinding`, `RawLocalExport`, `RawSymbolReference`, and
  `ReferenceExtractionBatch` contracts;
- add required `RawImport.bindings` serialization/validation;
- extend `ImportExtractionBatch` without changing `extract_imports()` output;
- add bounds and impossible-state validation; and
- prove stable round trips and rejection of missing/unknown fields.

**Acceptance:** all supported import forms produce exact binding data; legacy
call signatures remain; malformed fields fail closed.

**Verify:**

```bash
.venv/bin/python -m pytest tests/parser/test_imports.py tests/parser/test_references.py -q
```

### Task 2 — Extract lexical references and local exports in one parse

**Implementation status:** complete on 2026-07-20. The focused parser gate
passes 97 tests and the full repository suite passes 881 tests. `uv build`
produces both distribution artifacts, the frozen traversal benchmark passes
all 7 tests, and its fixture remains byte-identical at SHA-256
`c52def1bdf592ad735149d199910f74183598eccd9ccf8064335fa0cd0e84e27`.
The private `_reference_exports.py` and `_reference_paths.py` helpers keep the
four-language lexical orchestrator below the 1,000-line review signal without
adding another parse or public API. Final Stage 10 owner acceptance remains
pending.

**Files:**

- `src/loci/parser/references.py` (new)
- `src/loci/parser/_reference_exports.py` (new private helper)
- `src/loci/parser/_reference_paths.py` (new private helper)
- `src/loci/parser/imports.py`
- `tests/parser/test_references.py`
- `tests/parser/test_imports.py`

**Work:**

- implement language-specific binding scopes, maximal path extraction,
  shadow detection, and local export extraction;
- call it from the existing parsed tree in `extract_import_batch()`;
- exclude declaration identifiers and duplicate child paths; and
- enforce per-file/path/binding bounds atomically.

**Acceptance:** representative Python, JS/TS, Go, and Rust fixtures yield exact
lines, columns, byte ranges, paths, binding states, and export records from one
dependency parse; dynamic/unsupported syntax never becomes definite.

**Verify:**

```bash
.venv/bin/python -m pytest tests/parser/test_imports.py tests/parser/test_references.py -q
```

### Checkpoint A — Parser contract review

- [x] Installed tree-sitter 0.13.0 node shapes are covered.
- [x] No third parse was added.
- [x] Every supported alias/type-only/module-level form has a test.
- [x] Shadowing and resource-limit fixtures fail closed.
- [x] Existing import extraction tests remain green.

### Task 3 — Add source ownership, records, and Python resolution

> **TL;DR:** Complete: Loci can now prove exact Python symbol references through
> resolved imports and bounded named re-exports, while every shadowed,
> ambiguous, stale, unsupported, or off-endpoint case remains unresolved.

**Implementation status:** complete on 2026-07-20. The focused Task 3 gate
passes 40 tests, the affected parser/import/reference regression slice passes
219 tests, and the full repository suite passes 921 tests. Targeted Pyright
reports zero errors, `uv lock --check`, `compileall`, and `uv build` pass, and
the 15 frozen anchor/traversal tests pass with the external fixture unchanged
at SHA-256
`c52def1bdf592ad735149d199910f74183598eccd9ccf8064335fa0cd0e84e27`.
Fresh Loci self-index verification passes all 1,988 symbols with healthy graph
state. Final Stage 10 owner acceptance remains pending.

**Files:**

- `src/loci/graph/references.py` (new)
- `src/loci/graph/_python_references.py` (new)
- `tests/graph/test_references.py` (new)
- `tests/graph/test_reference_contracts.py` (new)

**Work:**

- implement strict support/reference records and common resolver index;
- map references to unique smallest source symbols or file nodes;
- resolve direct/module-member Python targets inside exact imported files;
- add bounded top-level named Python re-export chains; and
- retain every import-rooted failure without an edge.

**Acceptance:** same-named off-endpoint symbols never participate; direct,
aliased, module-qualified, re-exported, missing, shadowed, and ambiguous Python
cases produce the frozen outcomes.

**Verify:**

```bash
.venv/bin/python -m pytest tests/graph/test_references.py tests/graph/test_reference_contracts.py -q
```

### Task 4 — Add JavaScript/TypeScript export-surface resolution

> **TL;DR:** Complete: Loci can now prove exact JavaScript and TypeScript
> symbol references through direct ESM imports, aliases, namespace members,
> named defaults, local export clauses, named re-exports, and safe star barrels.
> Conflicts, unsupported syntax/configuration, anonymous defaults, and
> non-convergent routes remain explicit unresolved records.

**Implementation status:** complete on 2026-07-20. The focused Task 4 gate
passes 132 tests and the full repository suite passes 933 tests. Targeted
Pyright reports zero errors, `uv lock --check`, `compileall`, and `uv build`
pass, and the 26 frozen anchor/traversal tests pass with the external fixture
unchanged at SHA-256
`c52def1bdf592ad735149d199910f74183598eccd9ccf8064335fa0cd0e84e27`.
A fresh Loci self-index is healthy with 2,005 symbols, 1,022 graph edges, 45
file nodes, and 629 imports (326 resolved and 303 unresolved); integrity
verification passes all 2,005 symbols. Final Stage 10 owner acceptance remains
pending.

**Files:**

- `src/loci/graph/_javascript_references.py` (new)
- `src/loci/graph/references.py`
- `tests/graph/test_references.py`
- `tests/parser/test_references.py`

**Work:**

- resolve named, namespace, alias, explicit type-only, and provable named
  default bindings;
- compile direct exports, local export clauses, named re-exports, and safe star
  re-exports to a bounded fixed point;
- propagate Stage 8 control provenance; and
- reject anonymous default, computed, conflicting, cyclic-ambiguous, and
  CommonJS-only cases.

**Acceptance:** exact barrel chains work; star conflicts and wrong-file
same-name candidates never create edges; type-only bindings are preserved.

**Verify:**

```bash
.venv/bin/python -m pytest tests/parser/test_references.py tests/graph/test_references.py tests/graph/test_javascript_modules.py -q
```

### Task 5 — Add Go package-symbol resolution

> **TL;DR:** Complete: Loci can now follow a proven Go import into its exact
> Stage 7 package, use either the package's real declared name or an explicit
> alias, and resolve exported package-level functions, types, and constants.
> Uncertain package names, shadowing, dot/blank imports, unexported names,
> methods/fields, duplicate targets, external packages, and off-endpoint
> same-name symbols remain unresolved without guessed relationships.

**Implementation status:** complete on 2026-07-20. The focused Task 5 gate
passes 152 tests and the full repository suite passes 939 tests. Targeted
Pyright reports zero errors, `uv lock --check`, `compileall`, and `uv build`
pass, and the 26 frozen anchor/traversal tests pass with the external fixture
unchanged at SHA-256
`c52def1bdf592ad735149d199910f74183598eccd9ccf8064335fa0cd0e84e27`.
A fresh Loci self-index is healthy with 2,018 symbols, 1,030 graph edges, 46
file nodes, and 653 imports (343 resolved and 310 unresolved); integrity
verification passes all 2,018 symbols. Final Stage 10 owner acceptance remains
pending.

**Files:**

- `src/loci/graph/_go_references.py` (new)
- `src/loci/graph/references.py`
- `tests/graph/test_references.py`
- `tests/graph/test_go_modules.py`

**Work:**

- index package-level exported functions/types/constants by exact Stage 7
  package endpoint;
- resolve declared package names and explicit aliases;
- apply conservative local shadow checks; and
- reject dot/blank imports, unexported names, methods, and duplicate targets.

**Acceptance:** same-module, active-workspace, and contained-replacement package
references resolve only through the already accepted Go import records.

**Verify:**

```bash
.venv/bin/python -m pytest tests/graph/test_references.py tests/graph/test_go_modules.py tests/graph/test_imports.py -q
```

### Task 6 — Add Rust terminal-item metadata and resolution

> **TL;DR:** Complete: Loci can now follow a definite Rust `use`, alias,
> module-qualified path, 2015 `extern crate`, same-package library route, or
> named `pub use` chain to the exact indexed item. It applies both module and
> item privacy, retains Cargo/configuration evidence, and refuses glob,
> macro, namespace-conflicted, inaccessible, wrong-crate, over-limit, and
> configuration-divergent guesses. `Type::method` may identify the imported
> type only; it never claims the associated method or a call.

**Implementation status:** complete on 2026-07-20. The focused Task 6 gate
passes 194 tests and the full repository suite passes 950 tests. Targeted
Pyright reports zero errors for the new Rust resolver and shared resolver;
the six existing extractor findings remain unchanged. `uv lock --check`,
`compileall`, `uv build`, and `git diff --check` pass. The 26 frozen
anchor/traversal tests pass with the external fixture unchanged at SHA-256
`c52def1bdf592ad735149d199910f74183598eccd9ccf8064335fa0cd0e84e27`.
A fresh Loci self-index is healthy with 2,058 symbols, 1,041 graph edges, 47
file nodes, and 680 imports (364 resolved and 316 unresolved); integrity
verification passes all 2,058 symbols. No Cargo, rustc, repository code, or
network execution was added. Final Stage 10 owner acceptance remains pending.

**Files:**

- `src/loci/parser/extractor.py`
- `src/loci/graph/_rust_references.py` (new)
- `src/loci/graph/references.py`
- `tests/parser/test_extractor.py`
- `tests/graph/test_references.py`

**Work:**

- attach validated lexical module, item visibility, and configuration metadata
  to indexed Rust items;
- resolve named/aliased/module-qualified bindings through the Stage 9 crate and
  module index;
- enforce item plus ancestor visibility and named re-export support;
- preserve edition/dependency/control/configuration provenance; and
- fail closed on glob, macro, associated-item, namespace, and divergent cfg
  ambiguity.

**Acceptance:** same-crate and contained path-dependency items resolve when
accessible; private/inaccessible/divergent candidates remain unresolved; no
Cargo/rustc/code execution occurs.

**Verify:**

```bash
.venv/bin/python -m pytest tests/parser/test_extractor.py tests/graph/test_references.py tests/graph/test_rust_crates.py tests/graph/test_imports.py -q
```

### Checkpoint B — Four-language resolver review

- [x] Every target search is endpoint-scoped.
- [x] Every re-export loop is bounded and deterministic.
- [x] Language visibility/export rules have positive and negative tests.
- [x] Same-name adversarial fixtures cannot fabricate a target.
- [x] Rust declared-possible status is preserved, not silently upgraded.
- [x] No resolver performs I/O after its frozen index is built.

### Task 7 — Materialize and validate reserved reference edges

**Files:**

- `src/loci/graph/contracts.py`
- `src/loci/graph/references.py`
- `src/loci/graph/materialize.py`
- `tests/graph/test_reference_contracts.py`
- `tests/graph/test_materialize.py`

**Work:**

- materialize deduplicated `references`/`references_type` edges;
- add cross-record/source/hash/endpoint/support validation;
- reserve both edge names to `namespace="loci"`;
- thread records through materialization after imports; and
- prove unresolved records and invalid evidence cannot become edges.

**Acceptance:** every persisted reference edge is backed by one current resolved
record and every support record validates against current indexed evidence.

**Verify:**

```bash
.venv/bin/python -m pytest tests/graph/test_reference_contracts.py tests/graph/test_materialize.py tests/graph/test_contracts.py -q
```

### Task 8 — Persist schema 7 and prove storage integrity

**Files:**

- `src/loci/graph/state.py`
- `src/loci/graph/contracts.py`
- `src/loci/storage/index_store.py`
- `tests/graph/test_state.py`
- `tests/storage/test_reference_index_store.py` (new)

**Work:**

- add strict export/reference state fields and serializers;
- bump private graph state to 7 and extractor version to 10;
- validate reference records before atomic writes;
- reserve reference edge types across namespaces; and
- prove old schemas rebuild rather than load partially.

**Acceptance:** state round trips byte-stably; corrupt/missing/unknown fields and
unbacked edges fail; ordinary repositories still persist an empty complete
reference envelope.

**Verify:**

```bash
.venv/bin/python -m pytest tests/graph/test_state.py tests/storage/test_index_store.py tests/storage/test_reference_index_store.py -q
```

### Task 9 — Integrate incremental service behavior and health

**Files:**

- `src/loci/service.py`
- `src/loci/graph/materialize.py`
- `tests/test_symbol_reference_service.py` (new)
- `tests/test_service.py`

**Work:**

- retain unchanged raw exports/reference observations without reparsing;
- replace changed-file records and drop deleted-file records;
- re-resolve unchanged references after source/export/control changes;
- add index/health counts and stable diagnostics; and
- prove full/incremental serialized parity plus no-op no-reparse behavior.

**Acceptance:** add/change/delete scenarios for source, target, re-export, and
language controls produce current exact records; fresh full and incremental
indexes serialize identically.

**Verify:**

```bash
.venv/bin/python -m pytest tests/test_symbol_reference_service.py tests/test_service.py -q
```

### Task 10 — Expose fresh-process MCP diagnostics and traversal

**Files:**

- `src/loci/service.py`
- `src/loci/mcp_server.py`
- `tests/test_symbol_reference_mcp.py` (new)
- `tests/test_mcp_server.py`
- `tests/graph/test_traversal.py`

**Work:**

- add the exact bounded `graph_references()` service response;
- add `loci_graph_references` through the existing error adapter;
- prove fresh-process reads, filters, pagination, errors, and no rewrite;
- prove incoming/outgoing reference traversal and paths; and
- keep `loci_graph_neighbors` contains-only.

**Acceptance:** a newly launched real stdio client can inspect resolved and
unresolved records, traverse exact reference edges, hydrate evidence, and
retrieve the final target through `loci_get`.

**Verify:**

```bash
.venv/bin/python -m pytest tests/test_symbol_reference_mcp.py tests/test_mcp_server.py tests/graph/test_traversal.py -q
```

### Task 11 — Document and run the production acceptance gate

**Files:**

- `README.md`
- `skills/loci/SKILL.md`
- `docs/design/2026-07-13-extensible-graph-retrieval-design.md`
- `docs/reviews/2026-07-20-extensible-graph-retrieval-stage-10-final-review.md`
- `tests/graph/test_traversal_benchmark.py` only if an additive checksum guard
  needs clarification; the frozen fixture itself is never edited.

**Work:**

- document edge semantics, MCP input/output, filters, and limitations;
- run the exact full suite, build, integrity, benchmark, and disposable MCP
  acceptance matrix below;
- record hashes, counts, commands, failures/repairs, and remaining limits in the
  final review packet; and
- stop for Vik's explicit acceptance.

**Acceptance:** every final gate item has reproducible evidence; design status
remains implemented-awaiting-acceptance until Vik approves.

## Required Test Matrix

### Parser bindings and evidence

- Python direct/from/alias/dotted imports, nested imports, and star exclusions.
- JS/TS default/named/namespace/alias, statement and per-specifier type-only,
  re-export forms, and every supported extension.
- Go default/alias/dot/blank imports and exact selector roots.
- Rust use trees, aliases, `self`, modules, extern crates, pub use, globs, and
  lexical block/module scopes.
- Exact 1-based line/column and byte ranges with Unicode before references.
- Maximum-path/binding/reference/export limits and atomic file failure.
- Malformed syntax produces no partial reference batch.

### Shadowing and source ownership

- Parameters, assignments, local declarations, nested imports, loops/catches,
  and block bindings suppress possibly shadowed references per language.
- Textual order rules differ correctly where the language requires it.
- The unique smallest containing method/function wins over its class/container.
- Module-level code uses the file node.
- Equal-span ambiguity fails closed.
- Declaration names and member-path children are not duplicate references.

### Python resolution

- Direct imported symbol and alias.
- Imported module alias plus member.
- Unaliased dotted module path.
- Bounded explicit re-export through `__init__.py`.
- Re-export cycle converging to one target.
- Missing, wrong-file same-name, shadowed, dynamic, cyclic-ambiguous, and star
  cases produce no edge.

### JavaScript/TypeScript resolution

- Named/aliased/namespace/static default target.
- Type-only statement and specifier produce `references_type`.
- Local export clause, named re-export, star barrel, and multi-hop workspace
  barrel.
- Star conflict, anonymous default, computed property, CommonJS require,
  custom/unsupported config, external, and wrong-file same-name fail closed.
- Stage 8 control files and resolution basis remain attached.

### Go resolution

- Same-module package, active go.work module, and contained local replacement.
- Declared package name and explicit alias.
- Exported function/type/constant.
- Unexported name, dot/blank import, local shadow, command/inaccessible package,
  duplicate build-alternative name, and external import create no edge.
- No repository-wide package-name or filename fallback.

### Rust resolution

- Same-crate external/inline module items.
- Same-package library from binary target.
- Contained path dependency and inherited workspace dependency.
- Named use, alias, module-qualified use, extern crate, and named pub re-export.
- Public, private, `pub(crate)`, `pub(super)`, `pub(self)`, and `pub(in ...)`
  item visibility with ancestor visibility.
- 2015 versus 2018+ path behavior inherited from Stage 9.
- Unconditional and convergent declared-possible references.
- Divergent configuration, glob/prelude, macro/generated, associated item,
  trait ambiguity, external crate, and wrong-crate same-name create no edge.

### Records, contracts, persistence, and retrieval

- Strict round trip for every new dataclass and graph state 7.
- Missing/unknown fields, wrong enums, unsafe paths, invalid hashes/lines/byte
  ranges, impossible status combinations, and cross-language provenance fail.
- Reference edge requires current matching record and support.
- `references_type` requires explicit type-only binding.
- Reserved edge types reject extension namespaces.
- Repeated uses retain records but deduplicate edge by earliest evidence.
- Generic traversal supports reference-only outgoing and incoming views.
- Paths hydrate the exact reference line from cached source.
- `loci_graph_neighbors` does not widen.
- `loci_graph_references` sorts, filters, paginates, counts, and errors exactly.

### Freshness and operational safety

- Full and no-op incremental index JSON hashes are identical.
- No-op incremental indexing does not call reference/import extraction for
  unchanged files.
- Source add/change/delete replaces or drops observations.
- Target definition/export/re-export add/change/delete re-resolves unchanged
  sources.
- Go/JS/Cargo control changes re-resolve unchanged sources.
- Old extractor/private graph schema triggers one complete rebuild.
- Invalid controls remain stable without refresh loops.
- Fresh-process MCP reads do not rewrite current index hash or mtime.
- Subprocess, network/socket, compiler/runtime/package-manager, and repository
  code execution traps remain untouched throughout indexing and reads.

## Verification Commands

Focused commands appear under each task. Checkpoints and the final review run:

```bash
# Parser/reference extraction
.venv/bin/python -m pytest \
  tests/parser/test_imports.py \
  tests/parser/test_references.py \
  tests/parser/test_extractor.py -q

# Resolution, contracts, materialization, state
.venv/bin/python -m pytest \
  tests/graph/test_references.py \
  tests/graph/test_reference_contracts.py \
  tests/graph/test_imports.py \
  tests/graph/test_contracts.py \
  tests/graph/test_materialize.py \
  tests/graph/test_state.py -q

# Storage, service, MCP, traversal
.venv/bin/python -m pytest \
  tests/storage/test_index_store.py \
  tests/storage/test_reference_index_store.py \
  tests/test_symbol_reference_service.py \
  tests/test_symbol_reference_mcp.py \
  tests/test_service.py \
  tests/test_mcp_server.py \
  tests/graph/test_traversal.py -q

# Frozen local benchmark and anchors
.venv/bin/python -m pytest \
  tests/graph/test_anchor_benchmark.py \
  tests/graph/test_traversal_benchmark.py -q

# Complete suite
.venv/bin/python -m pytest tests/ -q

# Dependency/build/integrity checks
uv lock --check
.venv/bin/python -m compileall -q src tests
uv build
git diff --check

# Frozen external benchmark checksum
shasum -a 256 \
  /Users/brummerv/llm-wiki/tests/fixtures/graph_shape_traversal_stage3.json
```

The complete suite's pass count will increase as Stage 10 tests are added. The
review packet records the exact collected/pass count rather than freezing a
guessed future number.

## Production MCP Acceptance Harness

The final review creates disposable repositories under `/tmp` and invokes the
actual installed `loci-mcp` command through real stdio clients in separate
processes.

Required fixtures:

1. **Python package** — direct alias, module member, explicit package
   re-export, shadowed local, missing target, and wrong-directory same name.
2. **JavaScript/TypeScript workspace** — named, namespace, type-only, default,
   local export, named/star barrel chain, conflict, unsupported computed use,
   and same-name decoy package.
3. **Go workspace** — default and alias package names, exported and unexported
   symbols, local shadow, dot/blank imports, contained replacement, and package
   duplicate ambiguity.
4. **Cargo workspace** — same-crate and path-dependency items, aliases, named
   pub re-export, item visibility, convergent/divergent configuration, glob,
   and same-name decoy crate/module.
5. **Mixed adversarial repository** — identical symbol names in unrelated
   files/languages plus unresolved imports, proving no cross-endpoint fallback.

For each fixture the harness runs:

1. full index in process A;
2. record serialized index SHA-256 and mtime;
3. fresh process B calls `loci_graph_health`, `loci_graph_imports`,
   `loci_graph_references`, reference-only outgoing/incoming traversal, a
   bounded path, and `loci_get` for the final target;
4. assert process B did not change index SHA-256 or mtime;
5. incremental index in process C;
6. assert full/incremental serialized index hashes are identical;
7. repeat reference diagnostics and traversal after add/change/delete control
   cases; and
8. assert execution/network marker files were never created.

The harness shadows or traps at least:

- Python `subprocess` and `os.system` routes used by production code;
- socket/network creation;
- `cargo`, `rustc`, `go`, `node`, `npm`, `pnpm`, `yarn`, `python`, `git`, and
  `curl` on `PATH`; and
- repository scripts/build hooks in the disposable fixtures.

The test harness itself may launch `loci-mcp`; the production indexing and read
paths may not launch any trapped repository/toolchain command.

## Frozen Benchmark Policy

The fixture at
`/Users/brummerv/llm-wiki/tests/fixtures/graph_shape_traversal_stage3.json` is
read-only acceptance evidence.

Stage 10 must:

- preserve SHA-256
  `c52def1bdf592ad735149d199910f74183598eccd9ccf8064335fa0cd0e84e27`;
- never copy its gold identifiers or expected answers into production code;
- keep the existing frozen benchmark tests green;
- explain any result change before acceptance; and
- never modify the fixture to make Stage 10 pass.

Because the frozen corpus is Markdown-oriented, the expected result is no
change. New code-reference benchmarks use separate disposable fixtures and do
not rewrite Stage 3 evidence.

## Final Review Gate

Implementation is ready for Vik's review only when the final review packet
contains evidence for every item below.

### Contract and scope

- [ ] Every resolved edge follows one exact resolved import binding.
- [ ] Target search never leaves the imported endpoint/export surface.
- [ ] Shadowed, ambiguous, inaccessible, external, unsupported, and divergent
      cases create no edge.
- [ ] No call, heuristic, or architecture-analysis scope entered Stage 10.
- [ ] No runtime/toolchain/repository-code/network execution was added.

### APIs and compatibility

- [ ] `references` and `references_type` are reserved, directed,
      `import-resolved`, and evidence-backed.
- [ ] `loci_graph_references` matches the frozen input/output/error/pagination
      contract.
- [ ] Generic traversal exposes reference edges only under its existing filters.
- [ ] `loci_graph_neighbors` remains contains-only.
- [ ] Public graph schema remains 1; outer index schema remains 5.
- [ ] Private graph schema is 7; extractor version is 10; stale indexes rebuild.
- [ ] No CLI command or dependency was added.

### Language evidence

- [ ] Python direct/module/re-export/shadow cases pass.
- [ ] JS/TS named/namespace/type/default/barrel/conflict cases pass.
- [ ] Go package/alias/export/shadow/ambiguity cases pass.
- [ ] Rust crate/module/re-export/visibility/configuration cases pass.
- [ ] Official source URLs and the installed grammar version are recorded.

### Persistence and operation

- [ ] Full and no-op incremental serialized hashes match for all acceptance
      fixtures.
- [ ] No-op incremental runs do not reparse unchanged files.
- [ ] Add/change/delete and control-change freshness cases pass.
- [ ] Fresh-process reads preserve index hash and mtime.
- [ ] Execution/network traps remain untriggered.
- [ ] `loci_verify` passes for every disposable fixture.

### Repository verification

- [ ] All focused matrices pass.
- [ ] Complete `tests/` suite passes with exact count recorded.
- [ ] `uv lock --check` passes.
- [ ] `compileall` passes.
- [ ] `uv build` produces sdist and wheel.
- [ ] `git diff --check` is clean.
- [ ] Frozen benchmark checksum is unchanged and benchmark tests pass.
- [ ] Final worktree contains only intended Stage 10 changes.

### Owner gate

- [ ] `docs/reviews/2026-07-20-extensible-graph-retrieval-stage-10-final-review.md`
      contains exact commands, hashes, counts, fixture outcomes, unresolved
      limits, and commit IDs.
- [ ] Vik explicitly accepts the final evidence.
- [ ] Only after that acceptance is Stage 10 marked implemented, reviewed, and
      accepted in the governing design.

## Rollback

Each task lands as an atomic direct-to-`master` commit. If a task fails its
checkpoint, revert only that task's commit and restore the last verified state.

Feature-level rollback removes:

- reference parser models/extraction;
- language reference resolvers;
- `exports` and `symbol_references` private state fields;
- `references`/`references_type` materialization and validation;
- service/MCP counts and `loci_graph_references`; and
- Stage 10 documentation.

Then restore graph state schema 6 and extractor version 9. Existing
contains/import graph behavior remains the accepted fallback. No persisted
migration or external data cleanup is required because a schema mismatch
causes a safe full rebuild.

## Owner Review Decision

Approved by Vik on 2026-07-20. Implementation may proceed task by task under
the bounded contract and verification gates above.

Approval authorizes the implementation tasks above, not adjacent Stage 11
cross-file calls, heuristic candidates, or architecture analysis.
