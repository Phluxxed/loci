# Plan: Extensible Graph Retrieval Stage 7 — Module-aware Go Import Resolution

- **Status:** accepted by the owner on 2026-07-16; implementation authorized
- **Date:** 2026-07-15
- **Repository:** `/Users/brummerv/loci`
- **Governing design:** `docs/design/2026-07-13-extensible-graph-retrieval-design.md`
- **Predecessor:** `docs/plans/2026-07-14-extensible-graph-retrieval-stage-6.md`

## Goal

Turn the Go import observations that Stage 6 already extracts into
trustworthy, directed, repository-local dependency edges.

Stage 7 succeeds when Loci can:

- read contained `go.mod` and `go.work` files without invoking the Go
  toolchain, executing repository code, or using the network;
- map an importing Go file to its owning module;
- resolve same-module packages, active workspace modules, and conservative
  contained local replacements;
- represent the imported Go package as a stable package node instead of
  pretending that a package import targets one arbitrary `.go` file;
- emit the existing `namespace="loci"`, `type="imports"`,
  `resolution="import-resolved"` edge from the importing file node to that
  package node;
- keep external, missing, ambiguous, invalid, and unsupported imports as
  inspectable records without trusted edges; and
- preserve every accepted Stage 6 Python, JavaScript, TypeScript, graph,
  service, persistence, freshness, traversal, and MCP contract.

This plan is the Stage 7 specification and implementation handoff. It does not
authorize implementation until the owner approves the final plan.

## User-visible Outcome

Given:

~~~text
repo/
├── go.mod                         module example.com/project
├── cmd/server/main.go             imports example.com/project/internal/store
└── internal/store/
    ├── reader.go
    └── writer.go
~~~

Loci will persist:

~~~text
cmd/server/main.go::__file__#file
    -- loci:imports / import-resolved -->
internal/store::example.com/project/internal/store#package
~~~

The target is one package node, not `reader.go`, `writer.go`, or a fan-out to
both. The node is anchored to a deterministic indexed Go source file for
retrieval, but its identity and API contract remain package-level.

`loci_graph_imports` will report the resolved observation with:

~~~json
{
  "source_file": "cmd/server/main.go",
  "source_id": "cmd/server/main.go::__file__#file",
  "target_file": null,
  "target_package": "example.com/project/internal/store",
  "target_kind": "package",
  "target_id": "internal/store::example.com/project/internal/store#package",
  "specifier": "example.com/project/internal/store",
  "language": "go",
  "status": "resolved",
  "resolution": "import-resolved",
  "unresolved_reason": null
}
~~~

Existing resolved Python and JavaScript/TypeScript records retain
`target_kind="file"`, their current `target_file`, and
`target_package=null`.

## Non-goals

Stage 7 does not:

- resolve Rust imports or Cargo modules;
- resolve symbols, identifiers, methods, interfaces, or cross-file calls;
- execute `go list`, `go env`, `go mod`, build scripts, generators, tests, or
  repository binaries;
- download modules, inspect `GOMODCACHE`, read `GOPATH`, contact `GOPROXY`,
  or follow remote replacements;
- inherit an ambient parent-directory workspace or `GOWORK` environment value;
- implement Go minimal version selection or transitive module-graph loading;
- model vendored dependencies;
- apply build tags, operating-system tags, architecture tags, or cgo selection;
- add an import CLI command or a Go-specific MCP tool;
- widen `loci_graph_neighbors` beyond its exact Markdown containment contract;
- admit heuristic edges into safe defaults;
- run a model, judge, wiki audit, or benchmark scorer during indexing; or
- begin the later resolved-reference, call-graph, heuristic, or architecture
  stages.

## Threat Model

The indexed repository is untrusted input. Stage 7 must protect host files,
index integrity, diagnostic privacy, and bounded local availability.

The concrete abuse cases are:

- a `go.mod`, `go.work`, `use`, or `replace` path attempts to escape the
  repository or traverse a symlink to read host data;
- a control file, directive list, replacement set, or package layout attempts
  to consume unbounded memory or indexing time;
- repository text attempts to reach a shell, Go toolchain, network client, or
  environment-dependent module cache;
- malformed controls attempt to leave a partial graph that looks trusted; or
- malicious contents or absolute paths attempt to leak through diagnostics.

The required controls are lexical normalization plus real-path containment,
`lstat`-based non-symlink reads, fixed byte/count ceilings, no subprocess or
network path, allowlisted persisted fields, bounded redacted diagnostics, and
atomic replacement only after complete graph validation. The adversarial test
matrix below proves each boundary.

## Governing Evidence

### Repository decisions

`docs/design/2026-07-13-extensible-graph-retrieval-design.md` is the current
roadmap. It says Stage 7 must use Go module semantics, must not guess by string
or filename similarity, and must leave Rust unresolved.

`docs/plans/2026-07-14-extensible-graph-retrieval-stage-6.md` is the accepted
implementation baseline. Stage 7 extends its persisted import records and
generic graph edges rather than creating another store or traversal API.

`docs/design/2026-06-10-graph-layer-design.md` remains correct about edge
orientation and trust: `A imports B` is stored source-to-target with
`resolution="import-resolved"`. Stage 7 changes the truthful Go target from a
file-shaped placeholder to a package node; it does not reverse or duplicate
the edge.

`docs/plans/2026-07-01-import-dependency-graph.md` remains superseded
research. Its "best effort" Go filename mapping is explicitly rejected.

### Official Go semantics

The implementation is grounded in the official Go documentation:

- [Go Modules Reference](https://go.dev/ref/mod): a package path is a module
  path joined with the package directory relative to the module root; package
  resolution is ambiguous when multiple modules provide a package.
- [`go.mod` file reference](https://go.dev/doc/modules/gomod-ref): the
  `module` directive supplies the import prefix, while local `replace`
  directives redirect module contents without changing source import strings.
- [Go workspaces](https://go.dev/ref/mod#workspaces): `use` adds explicit
  modules on disk to the workspace, and workspace `replace` directives
  override module replacements.
- [How to Write Go Code](https://go.dev/doc/code): a module stops at a nested
  directory containing another `go.mod` file.
- [`internal` directory rule](https://go.dev/cmd/go/#hdr-Internal_Directories):
  code beneath `internal` is importable only from the tree rooted at that
  directory's parent.

Stage 7 intentionally implements a conservative, repository-contained subset.
When reproducing an exact Go build would require environment state, version
selection, downloaded modules, vendor mode, or build constraints, Loci leaves
the observation unresolved rather than asserting a false edge.

## Live Baseline

The following contracts exist at the start of Stage 7.

### Extraction

`src/loci/parser/imports.py` already exposes:

~~~python
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
) -> list[RawImport]: ...
~~~

Grouped Go imports are already found recursively through `import_spec` nodes.
The current extractor does not return the `package_clause`. Stage 7 must add a
batch wrapper while preserving `extract_imports()`:

~~~python
@dataclass(frozen=True, slots=True)
class GoPackageDeclaration:
    name: str
    line: int

@dataclass(frozen=True, slots=True)
class ImportExtractionBatch:
    imports: tuple[RawImport, ...]
    go_package: GoPackageDeclaration | None

def extract_import_batch(
    path: Path,
    *,
    source_file: str,
    language: str,
    source_hash: str,
) -> ImportExtractionBatch: ...
~~~

`extract_imports()` becomes a compatibility wrapper returning
`list(extract_import_batch(...).imports)`. The service uses the batch so Go
imports and the package clause come from one tree-sitter parse.

### Resolution and persistence

`src/loci/graph/imports.py` already owns `ImportRecord`,
`resolve_import()`, `resolve_imports()`, and
`materialize_import_edges()`. Python and JavaScript/TypeScript resolve there;
Go and Rust currently return `unresolved/unsupported_language`.

`GraphIndexState.imports` persists those records under
`index.json.graph.imports`. Resolved records produce generic `GraphEdge`
records. Unresolved records never become edges.

### Indexing and freshness

`src/loci/service.py::index_repo()`:

1. retains raw imports for unchanged files;
2. re-extracts changed files;
3. adds stable `kind="file"` nodes;
4. re-resolves the complete raw-import set against current nodes;
5. materializes and validates graph state; and
6. atomically writes symbols and graph state.

`_iter_indexable_files()` currently ignores `go.mod` and `go.work` because
they are not source extensions. `_index_is_stale()` therefore cannot yet see
module-control changes. Stage 7 must close both gaps.

### Public reads

`graph_imports()` and `loci_graph_imports` already provide bounded,
status-filtered, paginated import records. Generic graph traversal and path
tools consume `import-resolved` edges. No new public operation is required.

### Versions at the boundary

The live values are:

~~~text
INDEX_SCHEMA_VERSION = 5
EXTRACTOR_VERSION = 5
GRAPH_SCHEMA_VERSION = 1
GRAPH_STATE_SCHEMA_VERSION = 2
~~~

## Architecture Decisions

### 1. Go imports target package nodes

A Go import names a package. A package may contain several `.go` files, so a
file-to-file edge would either select an arbitrary representative or fan out
one statement into several misleading edges.

Stage 7 adds one synthetic `kind="package"` symbol per indexed effective Go
package identity. The import edge targets that symbol.

The package node:

- has a stable ID derived from repository-relative package directory and
  effective import path;
- is zero-width so `loci_get` does not return an arbitrary whole file;
- is anchored to the lexicographically first indexed non-test Go file in the
  package directory;
- carries the one validated declared package name shared by the directory's
  indexed Go files;
- exposes the effective import path in `qualified_name`, `signature`, and
  metadata;
- remains searchable and outline-visible as an additive symbol kind; and
- does not introduce package-to-file containment edges in Stage 7.

Package membership edges remain deferred. Stage 7 needs a truthful dependency
endpoint, not a second hierarchy feature.

The service stores each valid Go package declaration in its file node's
`metadata.loci.go_package` object:

~~~json
{
  "name": "store",
  "line": 1
}
~~~

Unchanged file nodes retain this observation incrementally. Package
construction requires every indexed non-test Go file in a directory to have
one valid declaration with the same name. A missing or conflicting declaration
excludes that directory as a package target. A valid `package main` directory
is indexed as source but is not an importable package target.

### 2. Module parsing is pure, bounded, and repository-contained

Stage 7 adds a strict parser for only the official directives needed for local
resolution:

- `go.mod`: `module`, `require`, `exclude`, and `replace`;
- `go.work`: the required `go` directive, `use`, and `replace`; and
- single-line and parenthesized block forms, comments, identifiers, interpreted
  strings, and raw strings.

Unknown valid directives are ignored. Malformed lexical structure, malformed
relevant directives, duplicate required directives, unsafe contained paths, or
conflicting local bindings produce structured warning diagnostics and no edge
from the affected binding.

No external `go` executable is required. This keeps indexing deterministic on
machines without Go and prevents repository-controlled commands or network
access during navigation.

Each control candidate is limited to 1 MiB, must be a regular non-symlink file,
and must resolve inside the indexed repository. Valid readable files contribute
their content hash. Rejected entry types and oversized controls contribute a
stable typed sentinel hash derived without reading or following the entry, so
an unchanged invalid control does not create a freshness loop.

The deterministic resource ceilings are:

~~~python
MAX_GO_CONTROL_BYTES = 1_048_576
MAX_GO_DIRECTIVES_PER_FILE = 10_000
MAX_GO_PACKAGE_BINDINGS = 10_000
MAX_GO_PACKAGE_NODES = 10_000
~~~

Crossing a directive, binding, or package-node ceiling rejects the affected Go
context as a whole. It never persists a truncated, valid-looking Go graph.

### 3. One repository scan discovers source and Go controls

Do not add a second full `rglob` pass.

Replace the private `_iter_indexable_files()` helper with one private scan
result:

~~~python
@dataclass(frozen=True, slots=True)
class RepositoryScan:
    indexable_files: tuple[tuple[Path, str, str], ...]
    go_control_candidates: tuple[Path, ...]

def _scan_repository_files(
    repo_path: Path,
    store: IndexStore,
) -> RepositoryScan: ...
~~~

The scan preserves current source filtering, test-file exclusion, root
`.gitignore` handling, secret-name exclusions, and skip directories. It adds
contained filesystem entries named exactly `go.mod` or `go.work` to the
control-candidate list whether or not they are source files. It never follows
symlinked directories. The loader uses `lstat` semantics and rejects a symlink
or other non-regular control candidate without reading its target.

`vendor` is not a Go package target in Stage 7. Existing vendor source symbols
may remain indexable under current repository policy, but package-node
construction excludes any directory at or below a `vendor` path component.

### 4. Module and workspace context is explicit

Add `src/loci/graph/go_modules.py` with these contracts:

~~~python
@dataclass(frozen=True, slots=True)
class GoRequirement:
    module_path: str
    version: str

@dataclass(frozen=True, slots=True)
class GoExclusion:
    module_path: str
    version: str

@dataclass(frozen=True, slots=True)
class GoReplacement:
    module_path: str
    version: str | None
    local_root: str | None
    remote_path: str | None
    remote_version: str | None

@dataclass(frozen=True, slots=True)
class GoModule:
    source: str
    root: str
    module_path: str
    requirements: tuple[GoRequirement, ...]
    exclusions: tuple[GoExclusion, ...]
    replacements: tuple[GoReplacement, ...]

@dataclass(frozen=True, slots=True)
class GoWorkspace:
    source: str
    root: str
    go_version: str
    use_roots: tuple[str, ...]
    replacements: tuple[GoReplacement, ...]

@dataclass(frozen=True, slots=True)
class GoModuleProblem:
    code: Literal[
        "GRAPH_GO_MODULE_INVALID",
        "GRAPH_GO_WORKSPACE_INVALID",
        "GRAPH_GO_PACKAGE_INVALID",
        "GRAPH_GO_INDEX_LIMIT_EXCEEDED",
    ]
    message: str
    source: str
    details: dict[str, JSONValue]

@dataclass(frozen=True, slots=True)
class GoModuleContext:
    modules: tuple[GoModule, ...]
    workspaces: tuple[GoWorkspace, ...]

@dataclass(frozen=True, slots=True)
class GoModuleLoad:
    context: GoModuleContext
    input_hashes: dict[str, str]
    problems: tuple[GoModuleProblem, ...]

def load_go_module_context(
    repo_path: Path,
    control_candidates: Sequence[Path],
) -> GoModuleLoad: ...
~~~

All stored roots and sources are normalized repository-relative POSIX paths.
Use `"."` for the repository root. Results sort by source and declaration
order is normalized into stable tuples.

The loader hashes valid and invalid contained control candidates. Their hashes
join `GraphIndexState.input_hashes` so a control-file edit, add, or delete
invalidates freshness even when no `.go` source changed.

An explicit `use` or local `replace` path that lexically leaves the repository
is a normal non-local outcome. A path that is lexically contained but escapes
through a symlink or other real-path mismatch is an unsafe control diagnostic.

### 5. Effective package bindings are conservative

Add:

~~~python
@dataclass(frozen=True, slots=True)
class GoPackageBinding:
    import_prefix: str
    module_root: str
    declared_module_path: str
    source: str

@dataclass(frozen=True, slots=True)
class GoPackageIndex:
    modules: tuple[GoModule, ...]
    package_nodes: tuple[Symbol, ...]
    bindings_by_source_module: Mapping[str, tuple[GoPackageBinding, ...]]
    packages_by_binding: Mapping[tuple[str, str], Symbol]
    command_packages: frozenset[tuple[str, str]]

@dataclass(frozen=True, slots=True)
class GoPackageBuild:
    index: GoPackageIndex
    problems: tuple[GoModuleProblem, ...]

def build_go_package_index(
    context: GoModuleContext,
    *,
    file_nodes: Mapping[str, Symbol],
) -> GoPackageBuild: ...

def resolve_go_import_target(
    raw: RawImport,
    *,
    package_index: GoPackageIndex,
) -> tuple[Symbol | None, ImportUnresolvedReason | None]: ...
~~~

For each source module, eligible bindings are:

1. its own declared module path and root;
2. declared modules in the nearest enclosing `go.work` only when the source
   module itself appears in that workspace's `use` set; and
3. contained local replacements that are active for an explicit `require` in
   the source module.

A `go.work` replacement overrides a matching module replacement. A wildcard
replacement applies to any explicitly required version. A version-specific
replacement applies only when the explicit requirement version matches
exactly and is not excluded. In workspace mode, a version-specific replacement
is admitted only when the workspace modules' explicit requirements for that
module agree on one non-excluded version.
Conflicting versions or bindings are unresolved/ambiguous; Stage 7 does not
reimplement minimal version selection.

Remote replacements and contained control paths that point outside the
repository create no local binding. They are normal external outcomes, not
graph-health failures.

A contained local replacement root must contain one valid discovered
`go.mod`. A missing or invalid replacement module is a control diagnostic and
the binding is excluded.

Every binding excludes:

- a nested module root unless that nested module is independently eligible;
- any `vendor` directory;
- directories with no indexed non-test `.go` file;
- directories whose indexed Go files lack one consistent valid package
  declaration;
- valid `package main` directories as import targets; and
- paths that escape the binding root.

The package node ID contract is:

~~~python
def make_go_package_id(directory: str, import_path: str) -> str:
    normalized_directory = directory or "."
    return f"{normalized_directory}::{import_path}#package"
~~~

Example:

~~~text
internal/store::example.com/project/internal/store#package
~~~

Package symbol shape:

~~~json
{
  "id": "internal/store::example.com/project/internal/store#package",
  "name": "store",
  "qualified_name": "example.com/project/internal/store",
  "kind": "package",
  "language": "go",
  "file_path": "internal/store/reader.go",
  "byte_offset": 0,
  "byte_length": 0,
  "signature": "example.com/project/internal/store",
  "content_hash": "<anchor-file-sha256>",
  "keywords": ["example", "com", "project", "internal", "store"],
  "metadata": {
    "loci": {
      "go_package_node": true,
      "directory": "internal/store",
      "import_path": "example.com/project/internal/store",
      "package_name": "store",
      "module_root": ".",
      "declared_module_path": "example.com/project"
    }
  },
  "line": 1,
  "end_line": 1
}
~~~

If the anchor file changes, the package ID remains stable. Its `file_path` and
`content_hash` move to the next lexicographically first current file.
`name` and metadata `package_name` are the validated declared Go package
identifier; they need not equal the final import-path segment.
`packages_by_binding` is keyed by
`(module_root, effective_import_path)`. `command_packages` uses the same key
for valid `package main` directories that are source-indexed but not
importable. `GoPackageBuild.problems` carries package-declaration, binding,
and package-limit diagnostics back to the service; no invalid package is
silently omitted without an inspectable reason.

### 6. Exact Go resolution rules

Extend `resolve_import()` and `resolve_imports()` additively:

~~~python
def resolve_import(
    raw: RawImport,
    *,
    file_nodes: Mapping[str, Symbol],
    go_packages: GoPackageIndex | None = None,
) -> ImportRecord: ...

def resolve_imports(
    raw_imports: Sequence[RawImport],
    *,
    file_nodes: Mapping[str, Symbol],
    go_packages: GoPackageIndex | None = None,
) -> list[ImportRecord]: ...
~~~

The default `None` preserves current direct unit-test and internal call sites.
With no Go package index, Go remains `unresolved/unsupported_language`.

For a Go observation:

1. reject empty strings, absolute paths, relative `./` or `../` paths,
   backslashes, dot segments, control characters, or non-canonical separators
   as `invalid_specifier`;
2. treat `C` and standard-library-style paths with no eligible contained
   module prefix as `external`;
3. locate the importing file's deepest enclosing valid module root;
4. return `external` when the importing file has no contained module owner;
5. obtain only that source module's eligible package bindings;
6. select bindings whose import prefix equals the specifier or is a
   slash-boundary prefix;
7. keep only the longest import prefix;
8. return `ambiguous` when the longest candidates map to distinct contained
   package directories or node IDs;
9. return `external` when no eligible contained binding matches;
10. map the suffix after the prefix to a package directory;
11. return `not_indexed` when the binding is eligible but no package node
    exists for that exact directory and effective import path;
12. return `inaccessible` when the exact directory is a valid
    `package main` command;
13. enforce the Go `internal` rule using effective import paths; an importing
    package outside the parent prefix receives `inaccessible` and no edge;
14. return the exact package node when one valid target remains.

There is no shorter-prefix fallback after a more specific nested module path is
recognized but is not eligible. This prevents a parent module from claiming a
nested module's packages.

Build constraints are not used to decide whether a directory provides a
package. The package exists for Stage 7 when Loci has at least one indexed
non-test `.go` file in the exact directory, matching the Go module reference's
package-presence rule while preserving Loci's current test-file exclusion.

### 7. Import records distinguish file and package targets

Extend `ImportRecord`:

~~~python
ImportUnresolvedReason = Literal[
    "external",
    "not_indexed",
    "ambiguous",
    "unsupported_language",
    "invalid_specifier",
    "inaccessible",
]

ImportTargetKind = Literal["file", "package"]

@dataclass(frozen=True, slots=True)
class ImportRecord:
    raw: RawImport
    source_id: str
    target_file: str | None
    target_package: str | None
    target_kind: ImportTargetKind | None
    target_id: str | None
    status: ImportStatus
    unresolved_reason: ImportUnresolvedReason | None
~~~

Invariants:

- resolved file target: `target_kind="file"`, `target_file` and `target_id`
  required, `target_package=null`;
- resolved package target: `target_kind="package"`, `target_package` and
  `target_id` required, `target_file=null`;
- unresolved: all four target fields are null and `unresolved_reason` is
  required;
- Python and JavaScript/TypeScript produce only file targets;
- Go produces only package targets; and
- Rust remains unresolved/unsupported.

`ImportRecord.to_dict()` and `from_dict()` remain strict about missing and
unknown fields. Therefore:

~~~text
GRAPH_STATE_SCHEMA_VERSION = 3
EXTRACTOR_VERSION = 6
INDEX_SCHEMA_VERSION = 5
GRAPH_SCHEMA_VERSION = 1
~~~

The graph-state bump protects persisted record shape. The extractor bump forces
old indexes to rebuild so package symbols and Go resolution cannot appear
silently empty. The top-level index and generic graph/MCP envelopes do not
change incompatibly.

### 8. Edge materialization and validation remain generic

`materialize_graph()` receives the prepared package index through one new
keyword-only parameter:

~~~python
def materialize_graph(
    repo_path: Path,
    symbols: Sequence[Symbol],
    file_hashes: Mapping[str, str],
    profiles: Sequence[LoadedGraphProfile],
    contributions: Sequence[LoadedGraphContribution],
    *,
    raw_imports: Sequence[RawImport] = (),
    go_packages: GoPackageIndex | None = None,
    input_hashes: Mapping[str, str] | None = None,
    diagnostics: Sequence[GraphDiagnostic] = (),
) -> GraphIndexState: ...
~~~

The default preserves current direct callers. `materialize_graph()` does not
discover or parse Go controls and does not construct package symbols.

A Go import edge is:

~~~json
{
  "from": "cmd/server/main.go::__file__#file",
  "to": "internal/store::example.com/project/internal/store#package",
  "type": "imports",
  "directed": true,
  "namespace": "loci",
  "resolution": "import-resolved",
  "evidence": {
    "file": "cmd/server/main.go",
    "line": 4,
    "content_hash": "<importing-file-sha256>"
  }
}
~~~

`materialize_import_edges()` must look up the resolved target by `target_id`.
It validates file targets as before and package targets against exact package
node metadata. Duplicate statements from one source file to one package retain
all records but produce one edge using the earliest evidence statement.

`_validate_import_edge()` accepts:

- source `kind="file"` for every import edge;
- target `kind="file"` only for a matching resolved file-target record; or
- target `kind="package"` and `language="go"` only for a matching resolved
  package-target record.

For a Go target it additionally requires:

- `record.target_package == target.qualified_name`;
- package metadata `go_package_node=true`;
- metadata import path equals `record.target_package`;
- metadata package name is a valid non-`main` Go identifier;
- target ID equals the persisted record target ID; and
- source evidence file, line, and hash match the persisted Go observation.

No package edge uses `imports_type`.

### 9. Incremental indexing always rebuilds module context and package nodes

Raw import retention remains unchanged. Go control files and package nodes do
not use per-file retention.

On every full or incremental index:

1. scan current source and Go control candidates;
2. load and parse current Go module/workspace context;
3. retain ordinary symbols/raw imports and retained Go file-node package
   metadata, or re-extract changed Go imports/package clauses as one batch;
4. explicitly exclude old synthetic `kind="package"` symbols from retained
   per-file symbols;
5. construct current file nodes and add `metadata.loci.go_package` in the
   service after `make_file_symbol()` returns, without changing that helper's
   API;
6. rebuild all current Go package nodes from context and current Go file nodes,
   and merge `GoPackageBuild.problems` with control and import diagnostics;
7. append package nodes to the authoritative symbol list;
8. re-resolve every current raw import against current package bindings;
9. materialize and validate current edges; and
10. atomically replace the persisted index.

This guarantees that an unchanged Go import changes correctly when:

- `go.mod` changes module path;
- a nested `go.mod` is added or deleted;
- `go.work` adds or removes a `use` root;
- a local replacement changes;
- a package directory gains or loses its last indexed Go file;
- the deterministic package anchor file changes; or
- an import becomes ambiguous or unambiguous.

`GraphIndexState.input_hashes` becomes the sorted union of graph extension
hashes and contained Go control hashes. `_index_is_stale()` computes the same
union. A malformed control file is still hashed, so an unchanged invalid file
does not cause a perpetual refresh loop.

### 10. Service and MCP changes are additive

`graph_imports()` keeps its signature, filters, counts, pagination, error
semantics, and `schema_version=1` envelope.

Every item adds:

~~~json
{
  "target_package": null,
  "target_kind": null
}
~~~

Existing resolved file records return `target_kind="file"`. Resolved Go
records return `target_kind="package"` and `target_package`. Unresolved records
return both as null.

`index_repo()` and `graph_health()` add:

~~~json
{
  "graph_go_packages_indexed": 0
}
~~~

The existing aggregate import counts continue to count all languages.
Language-specific counts remain derivable through `loci_graph_imports` item
data; Stage 7 does not add a second count family.

`_graph_node_ref()` adds `import_path`, `package_name`, and `directory`
attributes only when
the indexed symbol has validated `go_package_node=true` metadata. Existing
file, Markdown, and ordinary symbol node references remain byte-for-byte
unchanged. This lets traversal consumers understand a package target without
parsing its ID or mistaking its anchor file for the imported package.

No MCP registration or tool signature changes. The installed wrapper and fresh
stdio process must expose the same `loci_graph_imports` tool with the additive
item fields.

`loci_graph_neighbors` remains exact outgoing Markdown `loci:contains` only.
Go dependency traversal uses `loci_graph_traverse_neighbors`,
`loci_graph_paths`, or `loci_graph_retrieve` with `imports` and
`import-resolved` filters.

### 11. Failure and health semantics

Normal outcomes stay healthy:

- standard library;
- external module;
- remote replacement;
- outside-repository workspace use or local replacement;
- missing indexed package;
- valid source outside a local module; and
- Rust unsupported.

They remain bounded unresolved import records.

The following produce warning diagnostics and degraded graph health while
preserving ordinary symbol navigation:

- malformed contained `go.mod`;
- missing or duplicate `module` directive;
- malformed contained `go.work`;
- unsafe symlink or contained-path escape;
- a missing or duplicate required `go.work` `go` directive;
- a contained `use` path that claims a module root without a valid `go.mod`;
- a contained local replacement root without a valid `go.mod`;
- conflicting or missing Go package declarations in one indexed directory;
- conflicting duplicate module paths or local bindings;
- a directive, binding, or package-node resource ceiling being exceeded.

Diagnostic codes are `GRAPH_GO_MODULE_INVALID`,
`GRAPH_GO_WORKSPACE_INVALID`, and `GRAPH_GO_PACKAGE_INVALID`, with
`GRAPH_GO_INDEX_LIMIT_EXCEEDED` reserved for the deterministic ceilings. Their
details must not contain file contents, environment values, or host paths
outside the repository.

An internal package/resolver or edge-contract invariant failure aborts the
atomic write and preserves the last valid index. It is not converted into a
healthy-looking partial Stage 7 graph.

## Exact File Plan

| File | Planned change |
| --- | --- |
| `src/loci/graph/go_modules.py` | New strict control parser, typed module/workspace model, binding construction, package nodes, and Go target resolution |
| `src/loci/parser/imports.py` | Add `ImportExtractionBatch` and Go package-clause extraction behind the unchanged `extract_imports()` compatibility API; add the `inaccessible` reason |
| `src/loci/graph/imports.py` | Extend record target shape, accept Go package index, resolve Go, and materialize package-target edges |
| `src/loci/graph/contracts.py` | Bump graph-state schema and validate file/package import endpoints |
| `src/loci/graph/materialize.py` | Accept current Go package index and pass it into import resolution without adding control parsing here |
| `src/loci/service.py` | Single repository scan, control loading, package-symbol rebuild, freshness hash union, additive counts and read fields |
| `src/loci/storage/index_store.py` | Bump extractor version from 5 to 6; package nodes use the current default zero kind weight |
| `tests/graph/test_go_modules.py` | New parser, workspace, replacement, binding, nested-module, internal, package-node, and safety tests |
| `tests/parser/test_imports.py` | Package-clause batch extraction, compatibility wrapper, `package main`, and parse-failure tests |
| `tests/graph/test_imports.py` | Record invariants, Go resolution dispatch, edge materialization, and file-target regressions |
| `tests/graph/test_contracts.py` | Package-target validation and rejection cases |
| `tests/graph/test_state.py` | Schema 3 round trip and stale schema rejection |
| `tests/graph/test_materialize.py` | Mixed file/package import materialization and deterministic ordering |
| `tests/test_service.py` | Full/incremental/freshness/health/read integration |
| `tests/test_mcp_server.py` | Fresh-process additive response and generic Go traversal proof |
| `tests/storage/test_index_store.py` | Extractor-version rebuild assertion |
| `README.md` | Document Go package targets, supported module semantics, and limitations |
| `skills/loci/SKILL.md` | Agent workflow examples for Go records and package-node traversal |
| `.claude/skills/loci/SKILL.md` | Exact mirror of the canonical skill |
| `docs/design/2026-07-13-extensible-graph-retrieval-design.md` | Mark Stage 7 implementation/review status only after the gate |
| `docs/reviews/2026-07-15-extensible-graph-retrieval-stage-7-final-review.md` | Final evidence packet created after implementation |

`src/loci/graph/materialize.py` is already near the review size threshold.
Go parsing, binding, and package construction must stay in
`src/loci/graph/go_modules.py`. Materialization receives prepared context and
does not absorb another feature-specific subsystem.

## Implementation Tasks

### Task 1: Freeze control-file parsing and safety

**Description:** Add `go_modules.py` with the typed directive model, strict
bounded parser, containment checks, deterministic hashes, and structured
problems. Do not resolve imports yet.

**Acceptance criteria:**

- single-line and block `module`, `require`, `exclude`, `replace`, and `use`
  forms parse, and a valid workspace requires one `go` directive;
- comments and quoted/raw tokens follow the documented lexical subset;
- relevant malformed directives produce one stable problem per control file;
- unknown directives do not fail a valid relevant model;
- symlinks, paths outside the repository, and files over 1 MiB are never read;
- no subprocess, Go executable, environment workspace, or network path exists.

**Verification:**

~~~bash
.venv/bin/python -m pytest tests/graph/test_go_modules.py -q
~~~

**Dependencies:** none.

**Files:** `src/loci/graph/go_modules.py`,
`tests/graph/test_go_modules.py`.

**Estimated scope:** medium, two files.

### Checkpoint 1: Parser contract

- official directive examples pass;
- malformed inputs fail closed with bounded diagnostics;
- repository containment tests pass; and
- owner-visible plan semantics still match the implementation.

### Task 2: Build modules, workspaces, bindings, and package nodes

**Description:** Extract one package clause in the existing Go import parse,
then convert valid controls and current Go file-node package metadata into
module ownership, workspace membership, replacement bindings, and stable
package symbols.

**Acceptance criteria:**

- deepest containing `go.mod` owns a source file;
- nested module directories are excluded from parent packages;
- nearest valid workspace applies only when it includes the source module;
- same-module, workspace-use, and conservative explicit-require local replacement
  bindings are deterministic;
- all files in an importable directory agree on one non-`main` package name;
- `package main` is retained as a command marker but never a package node;
- remote and outside-repository bindings are not local;
- package IDs do not depend on anchor filename;
- vendor and directories without indexed Go files do not become packages.

**Verification:**

~~~bash
.venv/bin/python -m pytest \
  tests/parser/test_imports.py \
  tests/graph/test_go_modules.py \
  -q
~~~

**Dependencies:** Task 1.

**Files:** `src/loci/parser/imports.py`,
`src/loci/graph/go_modules.py`,
`tests/parser/test_imports.py`,
`tests/graph/test_go_modules.py`.

**Estimated scope:** medium, four files.

### Task 3: Extend import records and Go resolution

**Description:** Add target kind/package fields, state schema 3 serialization,
the optional Go package index parameter, and exact Go resolver outcomes. Keep
current Python and JavaScript/TypeScript behavior byte-for-byte equivalent
apart from additive serialized fields.

**Acceptance criteria:**

- file/package/unresolved record invariants reject impossible combinations;
- old record shape is rejected under schema 3 rather than partially loaded;
- same-module, workspace, and local-replacement imports resolve to package IDs;
- standard library/external, missing, ambiguous, invalid, and internal-rule
  cases receive the exact reason specified above;
- Rust remains `unsupported_language`;
- direct callers that omit `go_packages` retain current Go behavior.

**Verification:**

~~~bash
.venv/bin/python -m pytest \
  tests/graph/test_imports.py \
  tests/graph/test_state.py \
  -q
~~~

**Dependencies:** Task 2.

**Files:** `src/loci/parser/imports.py`,
`src/loci/graph/imports.py`,
`src/loci/graph/contracts.py`,
`tests/graph/test_imports.py`,
`tests/graph/test_state.py`.

**Estimated scope:** medium, five files.

### Checkpoint 2: Resolver truthfulness

- no Go record targets an arbitrary file;
- every resolved Go target is an indexed package node;
- same-name and shorter-prefix traps produce no edge;
- nested-module and `internal` restrictions pass; and
- all pre-Stage-7 import unit tests remain green.

### Task 4: Materialize and validate package-target edges

**Description:** Thread the current package index into graph materialization,
emit one standard import edge per source/package pair, and validate exact record
and package metadata provenance.

**Acceptance criteria:**

- earliest evidence deduplication works for Go package edges;
- source is always a file node and target is the matching Go package node;
- file-target validation remains unchanged;
- wrong kind, language, metadata, package path, target ID, line, or source hash
  is rejected;
- no new edge type or resolution tier is introduced.

**Verification:**

~~~bash
.venv/bin/python -m pytest \
  tests/graph/test_contracts.py \
  tests/graph/test_imports.py \
  tests/graph/test_materialize.py \
  -q
~~~

**Dependencies:** Task 3.

**Files:** `src/loci/graph/contracts.py`,
`src/loci/graph/imports.py`,
`src/loci/graph/materialize.py`,
`tests/graph/test_contracts.py`,
`tests/graph/test_materialize.py`.

**Estimated scope:** medium, five files.

### Task 5: Integrate scan, freshness, versions, and incremental rebuild

**Description:** Replace the private source-only iterator with the single scan,
extract changed Go files through `extract_import_batch()`, persist their package
declarations on file-node metadata, load module context, exclude retained
package nodes, rebuild packages every index, merge control hashes into graph
input hashes, and bump cache versions.

**Acceptance criteria:**

- current source skip and `.gitignore` behavior is unchanged;
- one repository walk supplies source and Go controls;
- changed Go files update both raw imports and package-declaration metadata from
  one parse, while unchanged Go file nodes retain both observations;
- missing or conflicting declarations produce `GRAPH_GO_PACKAGE_INVALID`, and
  valid `package main` files remain source-indexed without a package node;
- adding, changing, or deleting `go.mod`/`go.work` makes the index stale;
- unchanged invalid controls do not create refresh loops;
- full and no-change incremental digests match;
- unchanged imports re-resolve after control or package changes;
- extractor version 5 and graph-state schema 2 caches force a full rebuild;
- write remains atomic and ordinary source navigation survives config failure.

**Verification:**

~~~bash
.venv/bin/python -m pytest \
  tests/test_service.py \
  tests/storage/test_index_store.py \
  -q
~~~

**Dependencies:** Tasks 1–4.

**Files:** `src/loci/service.py`,
`src/loci/storage/index_store.py`,
`tests/test_service.py`,
`tests/storage/test_index_store.py`.

**Estimated scope:** medium, four files.

### Checkpoint 3: Persisted vertical slice

Index one temporary single-module repository and prove:

1. one Go package node exists;
2. one Go import record resolves to it;
3. one `import-resolved` edge points to it;
4. a fresh process reads the same timing-excluded digest;
5. an incremental `go.mod` edit updates the node and edge; and
6. Python/TypeScript records in the same repository are unchanged.

### Task 6: Expose additive service and MCP output

**Description:** Add target kind/package fields and package count to existing
service responses, then prove generic traversal over the package target through
a fresh MCP server.

**Acceptance criteria:**

- `graph_imports()` signature, filters, pagination, counts, and error envelopes
  do not change;
- every item includes target kind/package fields;
- `graph_health()` and `index_repo()` include package-node count;
- traversed package nodes expose exact import-path and directory attributes;
- MCP tool name and input schema stay unchanged;
- outgoing and incoming traversal preserve stored direction;
- `loci_graph_neighbors` still excludes imports.

**Verification:**

~~~bash
.venv/bin/python -m pytest \
  tests/test_service.py \
  tests/test_mcp_server.py \
  tests/graph/test_traversal.py \
  -q
~~~

**Dependencies:** Task 5.

**Files:** `src/loci/service.py`,
`tests/test_service.py`,
`tests/test_mcp_server.py`.

**Estimated scope:** medium, three files.

### Task 7: Run the complete compatibility and adversarial gate

**Description:** Run the complete fixture matrix added alongside Tasks 1–6,
then rehearse the isolated MCP and real-repository review. If a case is
missing, return it to the task that owns that behavior instead of creating a
late cross-cutting test batch.

**Acceptance criteria:**

- every required behavioral case below is owned by and present in Tasks 1–6;
- no test calls a network service or requires Go installed;
- temporary repositories live under `tmp_path`, never under the skipped
  repository `tests/` directory;
- timing and temporary absolute paths are excluded from digest comparisons;
- the full Loci test suite passes.

**Verification:**

~~~bash
.venv/bin/python -m pytest tests/ -q
uv build
~~~

**Dependencies:** Tasks 1–6.

**Files:** no planned files; verification only.

**Estimated scope:** verification checkpoint.

### Task 8: Update durable docs and prepare final review packet

**Description:** Update user and agent documentation only after runtime
behavior is proven, keep the two Loci skill copies identical, and create the
Stage 7 final review packet.

**Acceptance criteria:**

- docs distinguish package targets from file targets;
- supported and deliberately unsupported Go semantics are explicit;
- Rust remains deferred;
- no docs instruct agents to use `loci_graph_neighbors` for imports;
- the review packet records exact commits, commands, counts, timings,
  compatibility evidence, risks, and recommendation;
- no model judge or expensive frozen benchmark is run without the trigger
  defined in the final gate.

**Verification:**

~~~bash
diff -u skills/loci/SKILL.md .claude/skills/loci/SKILL.md
git diff --check
~~~

**Dependencies:** Task 7.

**Files:** `README.md`, both skill copies, governing design, and final review
packet.

**Estimated scope:** medium, five files.

## Required Test Matrix

### Control parsing

- root `go.mod` with one module directive;
- nested module;
- quoted and raw-string module paths;
- single and block require directives;
- single and block exclude directives;
- wildcard and version-specific local replace;
- remote replace retained as non-local;
- root and nested `go.work`;
- required workspace `go` version;
- single and block use directives;
- workspace replacement precedence;
- comments and irrelevant valid directives;
- malformed tokens, blocks, and relevant directive arity;
- missing and duplicate module directives;
- oversized, symlinked, and escaping controls;
- directive, binding, and package-node ceilings reject without partial output;
- deterministic ordering and input hashes.

### Package nodes

- batch extraction returns current raw imports and the exact package-clause
  name/line from one parse;
- `extract_imports()` returns the same list shape and observations as before;
- valid non-`main` declaration persists on file-node metadata;
- valid `package main` is recorded as a command package but is not importable;
- missing, malformed, and conflicting declarations produce no package node;
- root package and subpackage;
- multi-file package emits one node;
- anchor filename changes while package ID remains stable;
- nested module files excluded from parent binding;
- vendor directory excluded;
- directory with only skipped `_test.go` has no package node;
- same directory under declared and replacement import identities has distinct
  package IDs;
- metadata, keywords, zero-width span, and anchor hash are exact;
- package nodes are outline-visible and retrievable without whole-file output.

### Resolution

- same-module root package;
- same-module subpackage;
- import of an exact local `package main` command is inaccessible and edge-free;
- standard library and `C` external;
- external module;
- relative import invalid;
- missing package not indexed;
- workspace `use` across two contained modules;
- sibling module not in workspace or replacement remains external;
- nested module prevents shorter parent-prefix fallback;
- explicit-require wildcard local replacement;
- exact-version local replacement;
- mismatched or conflicting version-specific replacement remains unresolved;
- workspace replacement overrides module replacement;
- outside-repository replacement remains external;
- longest eligible module prefix wins;
- duplicate longest bindings are ambiguous;
- valid internal import from allowed parent;
- invalid internal import from outside parent;
- same-named directories/files elsewhere never participate;
- Rust remains unsupported and edge-free.

### Records, edges, and contracts

- file target round trip with additive target fields;
- package target round trip;
- unresolved target fields all null;
- unknown/missing fields rejected;
- impossible target-kind combinations rejected;
- one Go runtime edge with exact source evidence;
- duplicate Go statements deduplicate to earliest evidence;
- wrong target kind/language/metadata/path/ID rejected;
- no `imports_type` Go edge;
- persisted graph-state schema 2 rejected as stale;
- Graph schema 1 and top-level index schema 5 remain current.

### Incremental and freshness

- unchanged source records retained;
- old package symbols never retained directly;
- control add/change/delete re-resolves unchanged import;
- nested module add/delete changes ownership;
- workspace use add/remove changes cross-module resolution;
- replacement add/remove changes resolution;
- target package add/delete changes unresolved/resolved status;
- last Go file deletion removes package node and edge;
- anchor file deletion preserves package ID with a new anchor;
- full and incremental digest equality;
- invalid-control diagnostic retained without perpetual refresh;
- fresh process reads identical records, nodes, and edges.

### Service, graph, and MCP

- exact additive `graph_imports` item schema;
- existing filter/count/pagination behavior;
- package-node count in index and health;
- expected unresolved Go records do not degrade health;
- malformed contained controls do degrade health;
- outgoing dependency traversal reaches package node;
- incoming traversal identifies importing file;
- bounded path preserves edge evidence;
- safe defaults admit `import-resolved` and exclude `heuristic`;
- compatibility neighbors stay Markdown containment-only;
- fresh installed-wrapper MCP process advertises and executes
  `loci_graph_imports`;
- Python, JavaScript, TypeScript, graph profile, contribution, search, outline,
  and get regressions stay green.

## Full Verification

Run focused tests after every task. After all tasks:

~~~bash
.venv/bin/python -m pytest tests/ -q
uv build
git diff --check
diff -u skills/loci/SKILL.md .claude/skills/loci/SKILL.md
~~~

Use an isolated cache and a real MCP stdio process:

~~~bash
LOCI_BASE_DIR=/tmp/loci-stage7-review .venv/bin/python -m loci.mcp_server
~~~

The review harness creates a temporary repository containing:

- one root module with a multi-file internal package;
- one nested module deliberately outside the workspace;
- two workspace modules with a valid cross-module import;
- one direct-require local replacement;
- one standard-library import;
- one remote external import;
- one missing local package;
- one invalid `internal` import;
- one same-name collision trap;
- one Rust observation; and
- one Python plus one TypeScript dependency for regression comparison.

It proves through MCP:

1. `loci_graph_imports` reports every record with correct target kind;
2. Go resolved records target package nodes, never arbitrary file nodes;
3. outgoing and incoming generic traversal preserve direction;
4. `loci_graph_paths` returns an evidence-backed source-to-package path;
5. normal external/missing/unsupported observations keep health healthy;
6. an invalid contained control file degrades health without breaking search;
7. a fresh process returns the same timing-excluded digest;
8. incremental module/workspace/replacement changes re-resolve unchanged source;
9. `loci_graph_neighbors` remains containment-only; and
10. mixed Python/TypeScript records and edges are unchanged except for additive
    target-kind fields.

Then index two real repositories in an isolated cache:

- `/Users/brummerv/loci` for current self-navigation compatibility; and
- one current Go repository selected at review time, recorded by exact path and
  commit, for real module/workspace evidence.

Record:

- full and no-change incremental wall time;
- symbols, file nodes, Go package nodes, imports, and edges;
- resolved/unresolved Go reason distribution;
- at least one real outgoing dependency read;
- at least one real incoming blast-radius read; and
- any unsupported module layout encountered.

## Frozen Benchmark Policy

The frozen benchmark remains:

~~~text
/Users/brummerv/llm-wiki/tests/fixtures/graph_shape_traversal_stage3.json
SHA-256 c52def1bdf592ad735149d199910f74183598eccd9ccf8064335fa0cd0e84e27
~~~

Stage 7 must verify the path and checksum in the final packet.

No judge, whole-wiki audit, or expensive frozen benchmark run is required by
default. Stage 7 adds only Go package nodes and Go import resolution; it does
not change Markdown symbols, anchor scoring rules, traversal algorithms, or the
llm-wiki adapter's explicit filters.

Run the expensive frozen benchmark only if a focused compatibility test shows
any Markdown ID, anchor, traversal, path, retrieval, or adapter output drift.
If triggered, compare against the frozen fixture without modifying it and stop
the release gate on any unexplained regression.

## Final Review Gate

Stage 7 passes only when the owner receives and approves
`docs/reviews/2026-07-15-extensible-graph-retrieval-stage-7-final-review.md`
containing:

- exact implementation and documentation commits;
- focused and full test results;
- build, skill-mirror, and `git diff --check` results;
- cache migration proof for extractor 6 and graph-state schema 3;
- parser safety proof: no subprocess, Go executable, environment workspace,
  repository execution, or network;
- single-module, nested-module, workspace, replacement, internal, ambiguous,
  external, missing, and Rust fixture results;
- proof that every resolved Go import targets a package node;
- proof that package IDs survive anchor-file replacement;
- full versus incremental digest equality;
- fresh-process MCP transcript;
- real Go repository counts, timings, and navigation examples;
- confirmation that `loci_graph_neighbors` stayed Markdown containment-only;
- confirmation that `heuristic` remains excluded;
- confirmation that normal unresolved records remain healthy and inspectable;
- frozen benchmark path and checksum verification, plus benchmark output only
  if the trigger fired;
- compatibility findings for Python, JavaScript, TypeScript, search, outline,
  get, graph profiles, contributions, traversal, retrieval, and llm-wiki;
- unresolved risks or deviations from this plan; and
- an explicit recommendation to accept, revise, or roll back Stage 7.

Owner approval is the gate. Do not begin resolved symbol-reference or call-edge
work until this packet is accepted.

## Rollback

Stage 7 is additive to repository source and destructive only to disposable
Loci caches.

Rollback:

1. revert the Stage 7 implementation and documentation commits;
2. restore extractor version 5 and graph-state schema 2 code;
3. rebuild affected indexes under the restored code; and
4. verify Go observations return to `unresolved/unsupported_language` with no
   package nodes or Go import edges.

No indexed repository content, `go.mod`, `go.work`, graph profile,
contribution, or llm-wiki fixture is modified by implementation or rollback.

During implementation, failures must not leave a valid-looking partial graph:

- invalid persisted schema forces reindex or a structured error;
- invalid Go control excludes affected bindings and persists a warning;
- unresolved imports persist and produce no edge;
- package-node or edge contract failure aborts the atomic index write; and
- no fallback guesses by filename, directory name, package name, or symbol.

## Risks and Mitigations

| Risk | Impact | Mitigation |
| --- | --- | --- |
| A Go package is misrepresented as one source file | High | Introduce stable package nodes; never emit arbitrary file targets |
| Pure parser diverges from Go syntax | High | Implement only official needed directives, fixture official examples, reject malformed/unsupported relevant forms |
| A control-heavy repository creates unbounded work | High | Fixed byte/directive/binding/package ceilings; reject whole Go context rather than truncate |
| Ambient Go state changes results | High | Ignore `GOWORK`/`GOPATH`/cache/toolchain; use contained controls only |
| Parent module claims nested module package | High | Deepest module ownership and no shorter-prefix fallback |
| Workspace or replace invents a local dependency | High | Require contained roots, explicit use/direct require, conservative version agreement |
| Version-specific replacement needs MVS | Medium | Resolve only direct unambiguous agreement; otherwise unresolved |
| `internal` package becomes visible illegally | High | Enforce parent-prefix rule before resolution |
| Vendor copy appears as first-party source | High | Exclude vendor package targets |
| Package nodes perturb search/outline | Medium | Additive kind, zero-width span, focused ranking and output regressions |
| Control edit fails to refresh | High | Hash controls into graph input hashes and test add/change/delete |
| Invalid control causes refresh loop | Medium | Persist invalid-file hash with diagnostic |
| Materialize module grows past healthy size | Medium | Keep Go subsystem in `go_modules.py`; thread prepared context only |
| Record shape silently misloads | High | Strict fields, graph-state schema 3, extractor 6 full rebuild |
| Go resolution changes wiki behavior | Low | No Markdown changes; focused compatibility first; expensive benchmark only on drift |

## Deliberately Deferred

At Stage 7 acceptance, resolved symbols, calls, heuristics, architecture
analysis, and Cargo-aware Rust resolution were all deliberately outside this
plan. Rust remained extract-and-report because no current consumer had yet been
identified.

### Post-acceptance roadmap correction — 2026-07-18

The owner subsequently identified Anvil as a definite near-term Rust consumer
and required dependency-layer language parity before higher semantic graph
work. This does not change Stage 7's accepted implementation or evidence. It
supersedes only the follow-on order:

1. complete deterministic JavaScript/TypeScript repository-local dependency
   resolution beyond the current relative-import subset;
2. implement deterministic Cargo-aware Rust dependency resolution;
3. add resolved symbol references that follow definite imports;
4. add cross-file calls only when binding and import resolution are definite;
5. expose heuristic candidates as opt-in diagnostics, never trusted defaults;
   and
6. add graph orientation or architecture analysis after enough real edges
   exist.

Each item requires its own bounded design and review gate. Until the Rust stage
lands, current Rust behavior remains extract-and-report with no trusted edge.

## Open Questions

None block implementation after owner approval.

If real-repository review exposes a common, safe Go layout outside the
conservative subset—most likely vendor mode or version selection—it must be
recorded as a separate follow-up. It must not be patched into Stage 7 with a
guess.
