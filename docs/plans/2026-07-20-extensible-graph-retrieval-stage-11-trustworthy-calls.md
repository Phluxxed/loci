# Plan: Extensible Graph Retrieval Stage 11 — Trustworthy Calls

**Status:** implemented, reviewed, and accepted

**Date:** 2026-07-20

**Governing design:**
`docs/design/2026-07-13-extensible-graph-retrieval-design.md`

**Accepted prerequisite:**
`docs/plans/2026-07-20-extensible-graph-retrieval-stage-10-resolved-symbol-references.md`

**Frozen external benchmark:**
`/Users/brummerv/llm-wiki/tests/fixtures/graph_shape_traversal_stage3.json`

**Frozen benchmark SHA-256:**
`c52def1bdf592ad735149d199910f74183598eccd9ccf8064335fa0cd0e84e27`

## Goal

Add one conservative call-relationship layer for the supported Python,
JavaScript/TypeScript, Go, and Rust subsets. Loci may create a directed
`loci:calls` edge only when it can prove both:

1. which indexed function, method, or file owns the executable call site; and
2. which one indexed function or method the call definitely targets.

The stage covers exact same-file calls and import-resolved cross-file calls.
It never guesses from a bare name, receiver type, repository-wide name match,
or model-generated candidate.

## Plain-language Outcome

Today Loci can show that code mentions an imported symbol, but it deliberately
does not claim that one function calls another. After Stage 11, questions such
as “what calls this function?”, “what does this function call?”, and “show the
definite path from this entry point to that helper” can use trusted call edges.

The important word is *definite*. Loci will understand simple local calls and
imported function calls. It will keep uncertain calls visible in a diagnostic
list, but will not put them into trusted traversal. That makes the graph more
useful without turning ordinary name similarity into invented architecture.

## Authorization and Review Posture

This document authorizes no production-code change by itself. Its commit may
update only this plan and the governing design. Vik must explicitly approve
implementation after reviewing this proposal.

Once approved, implementation proceeds task by task with tests first. Each
substantial accepted task is committed and pushed directly to `master`, under
the repository's existing owner-approved workflow. No pull request is required.
No LLM judge is part of the planned gate. A judge may be proposed separately
only if deterministic evidence leaves a specific high-risk question unresolved.

## Reconciliation with the Existing Roadmap

### Original graph trust design

`docs/design/2026-06-10-graph-layer-design.md` put same-file calls in Phase 1
and cross-file calls in Phase 3. The same-file call work was never delivered as
a distinct accepted stage. Building only cross-file calls now would leave that
earlier, simpler gap in place.

Stage 11 closes both gaps as one coherent call contract:

- same-file calls require a unique visible callable declaration and use
  `resolution="exact"`;
- cross-file calls require one resolved Stage 10 reference at the exact callee
  span and use `resolution="import-resolved"`.

The original Phase 1 also mentioned local references. Stage 11 does **not** add
general same-file `references` edges. Local binding evidence is collected only
to prove a call target. A general local-reference feature needs its own use
case and review.

### Extensible graph retrieval design

The accepted design made Stage 10 references the prerequisite for cross-file
calls. Stage 11 preserves that boundary and broadens it only enough to include
the still-missing exact local calls. It does not alter the extension profile,
contribution, retrieval, budget, or freshness contracts accepted in Stages
1-10.

After Stage 11 is accepted, architecture/orientation analysis is the next
planned graph capability. Heuristic candidate diagnostics remain deferred
until dogfood shows which unresolved cases are valuable enough to justify a
separate noisy layer.

## Official Semantics Used

The supported subset is intentionally stricter than each language's complete
runtime semantics:

- [Python call expressions](https://docs.python.org/3/reference/expressions.html#calls)
- [Python name binding and resolution](https://docs.python.org/3/reference/executionmodel.html#naming-and-binding)
- [ECMAScript function calls](https://tc39.es/ecma262/multipage/ecmascript-language-expressions.html#sec-function-calls)
- [ECMAScript function declarations](https://tc39.es/ecma262/multipage/ecmascript-language-statements-and-declarations.html#sec-function-definitions)
- [Go calls](https://go.dev/ref/spec#Calls)
- [Go declarations and scope](https://go.dev/ref/spec#Declarations_and_scope)
- [Rust call expressions](https://doc.rust-lang.org/reference/expressions/call-expr.html)
- [Rust method calls](https://doc.rust-lang.org/reference/expressions/method-call-expr.html)
- [Rust name resolution](https://doc.rust-lang.org/reference/names/name-resolution.html)
- [Rust scopes](https://doc.rust-lang.org/reference/names/scopes.html)

The implementation must record the installed tree-sitter grammar package and
version in the final review. A live probe against the currently locked parser
confirmed these relevant syntax shapes:

| Language | Included call node | Included callee shapes | Explicit exclusions |
| --- | --- | --- | --- |
| Python | `call` | `identifier`, static `attribute` path | `subscript`, dynamic callable values |
| JavaScript/TypeScript | `call_expression` | `identifier`, non-computed `member_expression` | `new_expression`, `subscript_expression`, optional/dynamic calls |
| Go | `call_expression` | `identifier`, package `selector_expression` | conversions selected as types, receiver/interface dispatch |
| Rust | `call_expression` | `identifier`, import-rooted `scoped_identifier` | `field_expression` method dispatch, `macro_invocation`, callable values |

Syntax shape proves only that a call exists. Binding and indexed-symbol evidence
must still prove the caller and callee.

## Live Implementation Baseline

The proposal is grounded in the accepted implementation at commit
`28383a50b577aa9f5682433f1190285d16345a71`:

- `extract_import_batch()` performs one dependency tree parse for every changed
  supported source file and already derives imports, exports, and Stage 10
  references from that tree.
- `references.py` owns the current lexical-scope, import-binding, shadowing, and
  static-path logic. It is close to 1,000 lines, so Stage 11 must share a small
  private lexical-context module rather than duplicate or further concentrate
  those rules.
- `materialize_graph()` resolves imports before references and validates records
  before adding built-in edges.
- private graph state schema is 7, outer index schema is 5, and extractor
  version is 10.
- public graph envelopes are schema 1.
- `graph_references()` and `loci_graph_references()` provide the accepted
  bounded record-query pattern.
- all graph self-edges are currently rejected. Stage 11 must narrow that rule
  safely so a proven recursive call is valid without permitting arbitrary
  self-edges.
- generic traversal and path retrieval already support filtered standard graph
  edges; `loci_graph_neighbors` intentionally remains contains-only.

The accepted Stage 10 repository gate recorded 1,013 passing tests. Stage 11
must record its own complete count; it must not copy that number as new evidence.

## Frozen Stage 11 Contract

### Included

1. Static call-site observations from the existing per-file dependency parse.
2. Exact executable caller ownership by an indexed function/method body or the
   source file node for module/package initialization.
3. Exact same-file direct-identifier calls to a unique visible indexed function
   or method.
4. Cross-file calls whose exact callee byte span matches one resolved Stage 10
   symbol-reference record targeting an indexed function or method.
5. Directed `loci:calls` edges with call-site evidence and `exact` or
   `import-resolved` resolution.
6. Strict persisted resolved and unresolved call records.
7. A bounded `graph_calls()` service read and `loci_graph_calls` MCP tool.
8. Existing traversal/path/hydration support through the standard edge list.
9. Safe recursive-call self-edges backed by validated call records.
10. Full/incremental parity, control-file freshness, fresh-process MCP proof,
    four-language fixtures, and the frozen benchmark guard.

### Explicitly outside Stage 11

Stage 11 does not add:

- general same-file reference edges;
- constructor or allocation relationships (`new`, type construction, struct or
  enum construction); a later feature may define a distinct `constructs` edge;
- calls through variables, closures, lambdas, callbacks, function pointers,
  callable objects, indexing, computed properties, optional chaining, or other
  dynamic expressions;
- Python `self.method()`/`cls.method()` or arbitrary attribute dispatch;
- JavaScript/TypeScript prototype, class-instance, union, overload, or language-
  service resolution;
- Go receiver, interface, embedded-method, generic-instantiation, or method-
  expression resolution;
- Rust method lookup, traits, associated-item inference, deref coercion, macros,
  function pointers, closures, or active `cfg` selection;
- repository-wide bare-name fallback or name-similarity matching;
- heuristic/candidate edges in trusted traversal;
- architecture metrics, hubs, communities, subsystem naming, or visualization;
- execution of repository code, compilers, runtimes, package managers, build
  scripts, macros, plugins, or network operations;
- a new CLI command, database, dependency, model call, or LLM judge.

## Core Trust Rules

### 1. Calls are records before edges

Every observed call becomes a bounded `CallRecord`. Resolution may succeed or
fail, but only a validated resolved record may materialize an edge. Diagnostic
records preserve individual sites; edges deduplicate repeated calls between the
same caller and callee at the same resolution tier.

### 2. Caller ownership follows executable bodies

The caller is the nearest enclosing named function/method **body**, not merely
the smallest symbol span. This prevents calls in decorators, annotations,
default arguments, class initializers, and other definition-time expressions
from being attributed to the function being defined.

Calls outside a named executable body belong to the source file node. A call
inside an unindexed lambda, arrow function, closure expression, or anonymous
function is unresolved with `caller_not_indexed`; it is not attributed to an
outer named function.

The resolver maps the recorded owner definition span to exactly one current
indexed function/method. Zero matches produce `caller_not_indexed`; multiple
matches produce `caller_ambiguous`.

### 3. Local resolution is lexical and exact

A direct identifier may resolve locally only when the parser records exactly
one visible callable declaration in the correct lexical scope and no closer
non-callable declaration or import shadows it. The declaration span must map to
exactly one current indexed `function` or `method` symbol in the same file.

Language order/hoisting rules are used only to identify the lexical binding,
not to predict runtime reachability. Multiple declarations that could bind the
same call fail closed as `local_binding_ambiguous`.

### 4. Cross-file resolution is a Stage 10 join

An identifier or static path may resolve across files only when exactly one
persisted Stage 10 `SymbolReferenceRecord` has the same source file, source
hash, callee start byte, and callee end byte. That record must be resolved, must
not be type-only, and must target `function` or `method`.

Stage 11 does not independently repeat import or export resolution. It consumes
Stage 10's proven endpoint, target, support chain, control files, and Rust
configuration. A Stage 10 unresolved record remains unresolved in Stage 11 and
its reason is exposed separately.

### 5. Conflicting proof fails closed

If local-binding evidence and a resolved imported reference both claim the same
callee span, no edge is emitted. The record uses `conflicting_resolution`. This
is an invariant alarm, not a tie-breaking opportunity.

### 6. Only indexed callables are targets

The accepted target kinds are exactly `function` and `method`. A Stage 10
reference to a class, type, interface, struct, enum, trait, impl, constant, or
file cannot become a call edge. This rule separates calls from construction and
type conversion.

### 7. Recursive calls are the only supported self-edge

A `loci:calls` edge may have equal endpoints only when a resolved `CallRecord`
with matching endpoints, resolution, evidence file, line, and content hash
exists. `GraphEdge.from_dict()` and `validate_graph_edges()` continue to reject
all other self-edges. Contribution/profile data cannot manufacture a trusted
recursive call.

Traversal remains cycle-safe and bounded; a recursive edge may appear once in
one-hop output but cannot cause repeated expansion or an infinite path.

### 8. One parse, bounded work, no execution

Call extraction receives the already parsed root and source bytes from
`extract_import_batch()`. It does not parse a second time. Resolution uses
current in-memory symbols, imports, references, and hashes only.

## Exact Parser Contracts

### `src/loci/parser/_binding_context.py` (new, private)

Move the reusable lexical observations from `references.py` into a private
module without changing Stage 10 behavior:

```python
@dataclass(frozen=True, slots=True)
class LexicalBinding:
    name: str
    kind: str
    scope_start_byte: int
    scope_end_byte: int
    scope_type: str
    declaration_start_byte: int
    declaration_end_byte: int
    active_start_byte: int
    callable_kind: Literal["function", "method"] | None

@dataclass(frozen=True, slots=True)
class ExecutableOwner:
    kind: Literal["file", "callable", "unindexed"]
    definition_start_byte: int | None
    definition_end_byte: int | None
    body_start_byte: int | None
    body_end_byte: int | None

@dataclass(frozen=True, slots=True)
class SyntaxContext:
    local_bindings: tuple[LexicalBinding, ...]
    executable_owners: tuple[ExecutableOwner, ...]
    excluded_subtrees: frozenset[tuple[int, int, str]]
    unsupported_import_starts: frozenset[int]

def collect_syntax_context(
    root_node: Any,
    source: bytes,
    language: str,
) -> SyntaxContext: ...

def nearest_executable_owner(
    context: SyntaxContext,
    node: Any,
) -> ExecutableOwner: ...
```

`references.py` imports these types/helpers and must retain byte-for-byte
equivalent serialized Stage 10 observations across its existing fixture matrix.
The module is private because its shapes may evolve with parser internals.

### `src/loci/parser/call_models.py` (new)

```python
MAX_CALL_SITES_PER_FILE = 250_000
MAX_CALL_BINDING_CANDIDATES = 256
MAX_CALL_PATH_SEGMENTS = 128

CallCalleeForm = Literal["identifier", "static_path", "dynamic"]
CallBindingState = Literal[
    "definite",
    "shadowed",
    "ambiguous",
    "absent",
    "unsupported",
]

@dataclass(frozen=True, slots=True)
class LocalCallableBinding:
    name: str
    callable_kind: Literal["function", "method"]
    definition_start_byte: int
    definition_end_byte: int
    definition_line: int
    scope_start_byte: int
    scope_end_byte: int

@dataclass(frozen=True, slots=True)
class RawCallSite:
    source_file: str
    language: str
    line: int
    column: int
    start_byte: int
    end_byte: int
    callee_start_byte: int
    callee_end_byte: int
    callee_text: str
    callee_path: tuple[str, ...]
    callee_form: CallCalleeForm
    local_candidates: tuple[LocalCallableBinding, ...]
    local_binding_state: CallBindingState
    owner: ExecutableOwner
    source_hash: str
```

Constructors validate immutable tuples, supported language/enums, normalized
repository-relative paths, 1-based line/column, ordered contained byte ranges,
non-empty callee text, bounded paths/candidates, owner range consistency, and
lowercase SHA-256. `callee_path` is non-empty only for `identifier` and
`static_path`. A dynamic call is retained with an empty path and
`local_binding_state="unsupported"`.

`ExecutableOwner` receives strict `to_dict()`/`from_dict()` support in this
module or a cycle-free shared model module; no parser-runtime node object is
persisted.

### `src/loci/parser/calls.py` (new)

```python
def extract_call_sites(
    root_node: Any,
    source: bytes,
    *,
    source_file: str,
    language: str,
    source_hash: str,
    context: SyntaxContext,
) -> tuple[RawCallSite, ...]: ...
```

This function performs no I/O and no parse. It walks call nodes, records the
complete call and exact callee spans, selects the nearest executable owner,
classifies the supported static callee form, and applies the shared lexical
binding/shadow rules to direct identifiers. Nested calls are separate records.
Ordering is deterministic by source file, call start/end, and callee span.

### `src/loci/parser/imports.py`

`ImportExtractionBatch` becomes:

```python
@dataclass(frozen=True, slots=True)
class ImportExtractionBatch:
    imports: tuple[RawImport, ...]
    go_package: GoPackageDeclaration | None
    exports: tuple[RawLocalExport, ...]
    references: tuple[RawSymbolReference, ...]
    calls: tuple[RawCallSite, ...]
```

`extract_import_batch()` builds one `SyntaxContext`, passes it to reference and
call extraction, and returns both observations. `extract_imports()` keeps its
existing return type and behavior. There is no public standalone file-reading
call extractor.

`extract_reference_batch()` gains this exact optional keyword:

```python
context: SyntaxContext | None = None
```

Production passes the shared context so scopes are collected once. Direct test
and library callers that omit it retain current behavior by collecting their
own context.

## Exact Graph Contracts

### `src/loci/graph/calls.py` (new)

```python
CallStatus = Literal["resolved", "unresolved"]
CallResolution = Literal["exact", "import-resolved"]
CallResolutionBasis = Literal["local_callable", "imported_reference"]
CallUnresolvedReason = Literal[
    "unsupported_callee",
    "caller_not_indexed",
    "caller_ambiguous",
    "local_binding_shadowed",
    "local_binding_ambiguous",
    "local_target_not_indexed",
    "callee_not_proven",
    "reference_unresolved",
    "target_not_callable",
    "conflicting_resolution",
]
CallSupportKind = Literal[
    "call_site",
    "caller_definition",
    "local_definition",
    "symbol_reference",
]

@dataclass(frozen=True, slots=True)
class CallSupport:
    kind: CallSupportKind
    file: str
    line: int
    content_hash: str
    endpoint_id: str

@dataclass(frozen=True, slots=True)
class CallRecord:
    raw: RawCallSite
    caller_id: str | None
    caller_kind: str | None
    target_file: str | None
    target_id: str | None
    target_kind: str | None
    status: CallStatus
    resolution: CallResolution | None
    unresolved_reason: CallUnresolvedReason | None
    reference_unresolved_reason: ReferenceUnresolvedReason | None
    resolution_basis: CallResolutionBasis | None
    support: tuple[CallSupport, ...]
    resolution_control_files: tuple[str, ...]
    resolution_configuration: RustResolutionConfiguration | None

def resolve_calls(
    observations: Sequence[RawCallSite],
    *,
    symbols: Sequence[Symbol],
    symbol_references: Sequence[SymbolReferenceRecord],
    file_hashes: Mapping[str, str],
) -> list[CallRecord]: ...

def materialize_call_edges(
    records: Sequence[CallRecord],
) -> list[GraphEdge]: ...
```

Strict construction and deserialization enforce these invariants:

- resolved records have non-null caller/target/resolution/basis, no unresolved
  reasons, current call/caller/target support, and callable target kind;
- every resolved record includes `call_site` support; a named callable owner
  also includes `caller_definition` support, while a file owner is proven by
  the indexed file endpoint and current call-site hash;
- exact records use `local_callable`, stay in the same file, and include
  `local_definition` support;
- import-resolved records use `imported_reference`, match one resolved Stage 10
  record at the exact callee span, inherit its controls/configuration, and
  include `symbol_reference` support;
- unresolved records have null target/resolution/basis and exactly one primary
  unresolved reason; `reference_unresolved_reason` is present only with
  `reference_unresolved`;
- support is an immutable, bounded, deterministically ordered tuple;
- stale hashes, unsafe paths, missing endpoints, mismatched spans, and unknown
  enum values are contract errors rather than ordinary unresolved outcomes.

The record cap is the parser cap. Support reuses the Stage 10 maximum of 256.

### Resolution order

For each raw site:

1. Resolve caller ownership. Stop unresolved if the named executable owner does
   not map to exactly one indexed function/method.
2. Build the exact Stage 10 reference match for the callee span, if any.
3. Build the exact local callable match, if `local_binding_state="definite"`.
4. If both are resolved, emit `conflicting_resolution` and no edge.
5. If one local match exists, emit an `exact` resolved record.
6. Otherwise, if one resolved non-type Stage 10 match targets a callable, emit
   an `import-resolved` record.
7. Otherwise retain the most specific bounded unresolved reason.

Unresolved precedence is: unsupported syntax, caller failure, conflicting
proof, local shadow/ambiguity, unresolved exact reference, non-callable target,
missing indexed local target, then `callee_not_proven`.

### `src/loci/graph/_call_validation.py` (new, private)

```python
def validate_call_records(
    records: Sequence[CallRecord],
    *,
    symbol_references: Sequence[SymbolReferenceRecord],
    indexed_nodes: Mapping[str, Mapping[str, Any]],
    file_hashes: Mapping[str, str],
) -> None: ...

def index_call_edge_records(
    records: Sequence[CallRecord],
) -> Mapping[tuple[str, str, str], tuple[CallRecord, ...]]: ...
```

The edge index key is `(caller_id, target_id, resolution)`. Validation requires
matching record support and call-site evidence. Duplicate records are allowed;
duplicate materialized edges are not.

### `src/loci/graph/contracts.py`

`validate_graph_edges()` becomes:

```python
def validate_graph_edges(
    edges: list[GraphEdge],
    *,
    indexed_nodes: Mapping[str, Mapping[str, Any]],
    file_hashes: Mapping[str, str] | None = None,
    imports: Sequence[ImportRecord] = (),
    symbol_references: Sequence[SymbolReferenceRecord] = (),
    calls: Sequence[CallRecord] = (),
) -> None: ...
```

It reserves `("loci", "calls")`. Such an edge must be directed, have
`exact|import-resolved` resolution, connect an indexed file/function/method
caller to an indexed function/method target, and match a resolved call record.

`GraphEdge.from_dict()` permits equal endpoints only for a directed
`loci:calls` edge with `exact|import-resolved` resolution. Context-free parsing
does not establish trust: later `validate_graph_edges()` still requires the
supporting call record. Every other self-edge remains `INVALID_GRAPH_EDGE`.

Public `GRAPH_SCHEMA_VERSION` remains 1. Private
`GRAPH_STATE_SCHEMA_VERSION` becomes 8.

### `src/loci/graph/materialize.py`

`materialize_graph()` adds:

```python
raw_calls: Sequence[RawCallSite] = (),
```

The built-in order is fixed:

1. resolve imports;
2. resolve and validate symbol references;
3. resolve and validate calls using those exact reference records;
4. materialize contains, import, reference, and call edges;
5. process extension contributions;
6. deterministically deduplicate the complete edge set, after built-in edges
   have passed built-in validation and contributions have passed their existing
   profile/evidence validation.

Call edge deduplication keeps the earliest site by `(source_file, line, column,
start_byte)` as graph evidence for each
`(namespace, type, caller, target, resolution)` relationship. All call records
remain available through diagnostics.

### `src/loci/graph/state.py`

`GraphIndexState` adds:

```python
calls: tuple[CallRecord, ...]
```

The field appears after `symbol_references` in strict serialized order. Empty
state uses `calls=()`. `from_dict()` rejects missing, extra, malformed, stale,
or unsupported schema-8 call state.

## Exact Service and MCP APIs

### Indexing and freshness

`index_repo()` accumulates `raw_calls`. Changed files supply `batch.calls`.
Unchanged files reuse `record.raw` from previous call records. All observations
are re-resolved during every graph materialization, so a changed source, target,
reference, export, import, module/workspace/package control, or Cargo control
can update call outcomes without reparsing unrelated source files.

The index response and graph health counts add:

```json
{
  "graph_calls_indexed": 0,
  "graph_calls_resolved": 0,
  "graph_calls_unresolved": 0
}
```

Outer `INDEX_SCHEMA_VERSION` remains 5. `EXTRACTOR_VERSION` becomes 11, causing
older persisted indexes to take the existing safe complete-rebuild path. No
in-place migration is added.

### Service API

`src/loci/service.py` adds:

```python
def graph_calls(
    repo: str | Path,
    *,
    file: str | None = None,
    status: Literal["all", "resolved", "unresolved"] = "all",
    offset: int = 0,
    limit: int = 100,
    ensure_fresh: bool = False,
) -> dict[str, Any]: ...
```

It reuses `_validate_graph_record_query()`: `file` must be a normalized safe
repository-relative path, status is `all|resolved|unresolved`, offset is a
non-boolean integer at least zero, and limit is a non-boolean integer from 1 to
500. Invalid input remains `LociError(code="INVALID_INPUT")`.

Records sort by source file, line, column, call start, callee start, caller ID,
target file, target ID, and resolution. Filtering occurs before pagination.
Fresh-process reads are non-mutating unless `ensure_fresh=True` detects stale
inputs through the existing index path.

### MCP API

`src/loci/mcp_server.py` registers:

```python
@mcp.tool()
def loci_graph_calls(
    repo: str,
    file: str | None = None,
    status: str = "all",
    offset: int = 0,
    limit: int = 100,
) -> CallToolResult:
    """Inspect bounded resolved and unresolved definite-call records."""
```

The wrapper casts status to the service literal, calls `graph_calls(...,
ensure_fresh=True)`, and uses the existing `_handle_loci_error()` envelope.
There is no call CLI.

### MCP response

```json
{
  "schema_version": 1,
  "repo": "/absolute/repo",
  "file": "src/app.py",
  "status": "all",
  "items": [
    {
      "raw": {
        "source_file": "src/app.py",
        "language": "python",
        "line": 8,
        "column": 5,
        "start_byte": 96,
        "end_byte": 110,
        "callee_start_byte": 96,
        "callee_end_byte": 102,
        "callee_text": "helper",
        "callee_path": ["helper"],
        "callee_form": "identifier",
        "local_candidates": [],
        "local_binding_state": "absent",
        "owner": {
          "kind": "callable",
          "definition_start_byte": 40,
          "definition_end_byte": 120,
          "body_start_byte": 72,
          "body_end_byte": 120
        },
        "source_hash": "<sha256>"
      },
      "caller_id": "src/app.py::run#function",
      "caller_kind": "function",
      "target_file": "src/helpers.py",
      "target_id": "src/helpers.py::helper#function",
      "target_kind": "function",
      "status": "resolved",
      "resolution": "import-resolved",
      "unresolved_reason": null,
      "reference_unresolved_reason": null,
      "resolution_basis": "imported_reference",
      "support": [
        {
          "kind": "call_site",
          "file": "src/app.py",
          "line": 8,
          "content_hash": "<sha256>",
          "endpoint_id": "src/app.py::run#function"
        },
        {
          "kind": "caller_definition",
          "file": "src/app.py",
          "line": 4,
          "content_hash": "<sha256>",
          "endpoint_id": "src/app.py::run#function"
        },
        {
          "kind": "symbol_reference",
          "file": "src/app.py",
          "line": 8,
          "content_hash": "<sha256>",
          "endpoint_id": "src/helpers.py::helper#function"
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

The response shape mirrors `loci_graph_references`. Resolved and unresolved
items use the exact serialized `raw` record. Empty filters return counts for the
selected file before status filtering, an empty item list, and null next offset.

### Retrieval compatibility

- `loci_graph_traverse_neighbors`, `loci_graph_paths`, and
  `loci_graph_retrieve` consume `calls` via their existing namespace/type/
  resolution filters.
- hydration returns the standard edge evidence and current endpoint symbols.
- `loci_graph_neighbors` remains contains-only for compatibility.
- no alternate call-specific traversal engine or graph response schema is
  introduced.

## Exact File Changes

### New production files

- `src/loci/parser/_binding_context.py`
- `src/loci/parser/call_models.py`
- `src/loci/parser/calls.py`
- `src/loci/graph/calls.py`
- `src/loci/graph/_call_validation.py`

### Existing production files

- `src/loci/parser/references.py`
- `src/loci/parser/imports.py`
- `src/loci/graph/contracts.py`
- `src/loci/graph/materialize.py`
- `src/loci/graph/state.py`
- `src/loci/storage/index_store.py`
- `src/loci/service.py`
- `src/loci/mcp_server.py`

### New test files

- `tests/parser/test_calls.py`
- `tests/graph/test_calls.py`
- `tests/graph/test_call_contracts.py`
- `tests/storage/test_call_index_store.py`
- `tests/test_call_service.py`
- `tests/test_call_mcp.py`

### Existing tests updated for strict/additive contracts

- `tests/parser/test_references.py`
- `tests/graph/test_reference_contracts.py`
- `tests/graph/test_state.py`
- `tests/graph/test_materialize.py`
- `tests/graph/test_traversal.py`
- `tests/storage/test_reference_index_store.py`
- `tests/test_symbol_reference_service.py`
- `tests/test_symbol_reference_mcp.py`
- `tests/test_service.py`
- `tests/test_mcp_server.py`

### Documentation

- `docs/design/2026-07-13-extensible-graph-retrieval-design.md`
- `README.md`
- `skills/loci/SKILL.md`
- `docs/reviews/2026-07-20-extensible-graph-retrieval-stage-11-final-review.md`

No other production or test file is in scope without a documented plan
amendment and Vik's approval when the change is material.

## Incremental Implementation Tasks

Each task begins with a failing test or a behavior-preservation test, ends with
focused verification and `git diff --check`, and is committed/pushed only when
the bounded task is accepted locally.

### Task 1 — Extract shared lexical context without behavior change

1. Add characterization fixtures for every Stage 10 language covering nested
   scopes, parameters, declarations, imports, shadowing, and excluded subtrees.
2. Move lexical context types/collection into `_binding_context.py`.
3. Make `references.py` consume the shared immutable context.
4. Prove serialized exports and references are identical before/after the
   refactor and run the complete Stage 10 parser/reference matrix.

**Gate:** no call model or edge exists yet; all accepted reference behavior is
unchanged.

### Task 2 — Freeze strict call models and extract call sites

1. Add strict model round-trip/rejection tests and resource-limit tests.
2. Add four-language syntax fixtures for included and excluded callee forms,
   nested calls, exact byte spans, executable owners, file-level calls, and
   anonymous-owner suppression.
3. Implement `call_models.py` and `calls.py` from the existing parse/context.
4. Add `calls` to `ImportExtractionBatch` and prove one parse per changed file.

**Gate:** raw observations are deterministic and bounded; no resolution or edge
exists.

### Checkpoint A — Parser contract review

Review exact serialized shapes, per-language AST assumptions, owner-body rules,
scope reuse, limits, and Stage 10 parity before graph resolution begins.

### Task 3 — Resolve exact same-file calls

1. Add failing tests for module/package functions, nested functions, forward
   lexical declarations, recursion, file-level initialization, and methods only
   where a bare binding is exact.
2. Add negative tests for shadowing, duplicate declarations, parameters/local
   variables with the same name, unindexed closures, types/conversions, and
   repository-wide same-name decoys.
3. Implement local callable lookup by recorded declaration span and current
   indexed symbol.
4. Persist unresolved reasons without materializing edges.

**Gate:** every resolved local record has one same-file indexed target and
`resolution="exact"`; no imported call resolves yet.

### Task 4 — Resolve imported calls through Stage 10 references

1. Add failing direct/aliased/namespace/package/module-path fixtures for all
   four language families supported by Stage 10.
2. Join only on exact file/hash/callee byte span.
3. Reject unresolved, ambiguous, shadowed, type-only, inaccessible,
   configuration-divergent, and non-callable Stage 10 targets.
4. Prove controls/configuration/support provenance is inherited exactly.
5. Add cross-language same-name decoys and conflicting-proof invariant tests.

**Gate:** target lookup never leaves the accepted Stage 10 record.

### Checkpoint B — Four-language call resolver review

Review positive and negative resolution tables, unresolved reason stability,
caller ownership, target kinds, and absence of runtime/toolchain/network use.

### Task 5 — Materialize and validate `calls` edges

1. Add contract tests for reserved type, direction, endpoint kinds, resolution,
   evidence, missing support, stale hashes, and deduplication.
2. Add recursive-call self-edge tests and prove every non-call self-edge remains
   rejected by construction, deserialization, and final validation.
3. Implement call validation/materialization after references.
4. Add traversal/path tests for outgoing/incoming calls, resolution filters,
   hydration, cycles, budgets, and deterministic ordering.

**Gate:** no `calls` edge survives without a matching current resolved record;
recursive traversal remains bounded.

### Task 6 — Persist schema 8 and prove incremental integrity

1. Add strict schema-8 round-trip, missing/extra/malformed/stale record tests.
2. Add `calls` to `GraphIndexState`; bump private graph schema to 8 and
   extractor to 11; keep public/outer schemas unchanged.
3. Reuse unchanged raw sites and re-resolve them against current references and
   symbols.
4. Prove full/no-op incremental byte identity, zero reparses for unchanged
   files, add/change/delete behavior, and stale-schema rebuild.
5. Prove import/export/module/workspace/package/Cargo control changes update
   affected call resolution without refresh loops.

**Gate:** persisted state is deterministic and a fresh process validates every
record before serving it.

### Task 7 — Add service, health, and MCP diagnostics

1. Add failing service input/filter/pagination/order/count/freshness tests.
2. Implement `graph_calls()` and health/index counters.
3. Add MCP schema, success, empty, error, and ensure-fresh tests.
4. Run an installed-wrapper fresh-process fixture for each language family and
   verify the index hash/mtime is stable on a fresh read.
5. Confirm there is no call CLI and old MCP input schemas are unchanged.

**Gate:** a real host-mediated MCP client can inspect calls and traverse their
edges after restart.

### Task 8 — Documentation and production acceptance

**Implementation status:** complete through reviewed implementation head
`2ba9f6c`. The final evidence packet is
`docs/reviews/2026-07-20-extensible-graph-retrieval-stage-11-final-review.md`;
Vik explicitly accepted it on 2026-07-21.

1. Update README and the Loci skill with trusted-call semantics, examples,
   filters, and explicit exclusions.
2. Run all focused suites, complete suite, package/build/integrity checks, live
   Loci dogfood, frozen benchmark, and execution/network traps.
3. Record exact commands, versions, counts, hashes, fixture outcomes, limitations,
   and commit IDs in the final review packet.
4. Stop for Vik's explicit evidence approval before marking Stage 11 accepted.

## Required Test Matrix

### Parser and ownership

- Python identifier/attribute/subscript, decorators/defaults, nested functions,
  lambdas, file initialization, recursion.
- JS and TS identifier/member/computed/new/optional, function/method bodies,
  arrow/anonymous functions, nested calls.
- Go identifier/package selector/type conversion/receiver method, function and
  package initialization.
- Rust identifier/scoped identifier/field method/macro/closure/constructor-like
  syntax, function and module initialization.
- exact call/callee/owner bytes, lines, columns, source hashes, stable ordering,
  maximum limits, malformed model rejection.

### Same-file resolution

- unique direct callable, nested callable, recursion, file caller;
- lexical shadow by parameter/local/import/non-callable declaration;
- duplicate/ambiguous binding, missing indexed target, anonymous owner;
- same-name symbol in another file never selected;
- function/method targets accepted; class/type/constant/file targets rejected.

### Imported resolution

- every accepted Stage 10 direct/alias/namespace/package/module form used as a
  call in Python, JS/TS, Go, and Rust;
- exact reference-span join and mismatched-span rejection;
- unresolved reference reason passthrough;
- type-only and non-callable target rejection;
- re-export support/control/configuration inheritance;
- ambiguous, inaccessible, external, shadowed, unsupported, and divergent
  references create no call edge;
- local/import proof conflict creates no edge.

### Contracts, persistence, and freshness

- strict `CallSupport`/`CallRecord` round trips and unknown/missing/extra fields;
- stale source/caller/target/reference evidence rejection;
- edge dedupe while site records remain distinct;
- validated recursive self-edge and rejection of every other self-edge;
- schema 8/extractor 11 rebuild and outer/public schema stability;
- full/no-op incremental serialized equality and no unchanged-file reparse;
- source/target/control add, change, delete, and rename behavior;
- health/count status and no refresh loop on invalid controls.

### Service, MCP, and retrieval

- file/status filters, offset/limit boundaries, deterministic pages and counts;
- invalid path/status/boolean numeric inputs preserve `INVALID_INPUT` behavior;
- fresh-process MCP response for all four languages;
- incoming/outgoing traversal, exact/import-resolved filters, hydration, paths,
  cycle safety, and existing budgets;
- `loci_graph_neighbors` stays contains-only;
- old service/MCP schemas and Stage 10 records remain unchanged.

## Verification Commands

Exact focused commands may expand as test files land, but the final gate must
include at least:

```bash
uv run pytest -q \
  tests/parser/test_references.py \
  tests/parser/test_calls.py

uv run pytest -q \
  tests/graph/test_references.py \
  tests/graph/test_reference_contracts.py \
  tests/graph/test_calls.py \
  tests/graph/test_call_contracts.py \
  tests/graph/test_materialize.py \
  tests/graph/test_state.py \
  tests/graph/test_traversal.py

uv run pytest -q \
  tests/storage/test_reference_index_store.py \
  tests/storage/test_call_index_store.py \
  tests/test_symbol_reference_service.py \
  tests/test_symbol_reference_mcp.py \
  tests/test_call_service.py \
  tests/test_call_mcp.py \
  tests/test_service.py \
  tests/test_mcp_server.py

uv run pytest -q tests
uv lock --check
uv run python -m compileall -q src tests
uv build
git diff --check
shasum -a 256 \
  /Users/brummerv/llm-wiki/tests/fixtures/graph_shape_traversal_stage3.json
```

The production acceptance harness must use the installed `loci-mcp` wrapper or
equivalent registered stdio host path, create disposable four-language repos,
index them in a fresh process, restart, inspect `loci_graph_calls`, traverse
both directions, run `loci_verify`, and confirm no repository code, runtime,
toolchain, package manager, network client, or judge was invoked.

## Frozen Benchmark Policy

The external benchmark is read-only evidence. Stage 11 must:

1. verify the checksum before and after implementation;
2. run the existing benchmark test unchanged;
3. never rewrite expected output to make new call behavior pass; and
4. keep new call fixtures separate because the frozen corpus is Markdown-
   oriented and is expected to produce no new call edges.

A checksum mismatch stops the final gate and requires owner review.

## Final Review Gate

Implementation is ready for Vik only when a final review packet proves every
implementation item below.

### Contract and scope

- [x] Same-file calls require one exact lexical callable binding.
- [x] Cross-file calls require one exact resolved Stage 10 reference.
- [x] Caller ownership follows executable bodies, not broad symbol spans.
- [x] Dynamic/constructor/dispatch/type-only/non-callable cases create no edge.
- [x] No general local references, heuristics, architecture analysis, execution,
      network, dependency, model call, CLI, or judge entered Stage 11.

### APIs and compatibility

- [x] `calls` is reserved, directed, evidence-backed, and limited to
      `exact|import-resolved`.
- [x] `graph_calls()` and `loci_graph_calls` match the frozen query/response/
      error/pagination contract.
- [x] Generic traversal consumes calls; `loci_graph_neighbors` remains
      contains-only.
- [x] Public graph schema is 1; outer index schema is 5; private graph schema is
      8; extractor version is 11.
- [x] Existing Stage 10 record and MCP schemas are unchanged.

### Language and trust evidence

- [x] Positive and negative Python call matrix passes.
- [x] Positive and negative JavaScript/TypeScript call matrix passes.
- [x] Positive and negative Go call matrix passes.
- [x] Positive and negative Rust call matrix passes.
- [x] Recursive self-calls work and all other self-edges remain rejected.
- [x] Official sources and installed parser versions are recorded.

### Persistence and operation

- [x] Full/no-op incremental serialized hashes match all acceptance fixtures.
- [x] No-op incremental runs do not reparse unchanged files.
- [x] Add/change/delete and all relevant control-change cases pass.
- [x] Fresh-process reads preserve index hash and mtime when already fresh.
- [x] Execution/network/toolchain/package-manager/judge traps remain untriggered.
- [x] `loci_verify` passes every disposable fixture and live Loci dogfood.

### Repository verification

- [x] Every focused matrix passes with counts recorded.
- [x] Complete `tests/` suite passes with exact count recorded.
- [x] `uv lock --check`, `compileall`, package build, and `git diff --check` pass.
- [x] Frozen benchmark hash remains
      `c52def1bdf592ad735149d199910f74183598eccd9ccf8064335fa0cd0e84e27`.
- [x] Final worktree contains only intended Stage 11 changes.

### Owner gate

- [x] `docs/reviews/2026-07-20-extensible-graph-retrieval-stage-11-final-review.md`
      contains exact commands, hashes, counts, versions, fixture outcomes,
      unresolved limits, and commit IDs.
- [x] Vik explicitly accepts the final evidence.
- [x] Only after that acceptance is Stage 11 marked implemented, reviewed, and
      accepted in the governing design.

## Rollback

Each implementation task lands as an atomic direct-to-`master` commit. A failed
checkpoint reverts only that task and restores the last verified state.

Feature-level rollback removes call parser models/extraction, call resolution
and validation, `calls` private state, call edges/counters, and the service/MCP
diagnostic. It restores private graph schema 7 and extractor version 10.
Contains/import/reference behavior remains the accepted fallback. No external
data migration or cleanup is required because a schema mismatch causes a safe
full rebuild.

## Owner Review Decision

Vik approved the bounded implementation plan on 2026-07-20 and explicitly
accepted the final engineering and production evidence on 2026-07-21. Stage 11
is implemented, reviewed, accepted, and closed. That acceptance does not widen
the delivered scope to heuristic candidates, general local references,
constructors, dynamic dispatch, architecture analysis, visualization, new
dependencies, or any adjacent roadmap stage.
