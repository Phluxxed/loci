# Graph navigation and relationship contracts

## Contents

- Compact source by intent
- Graph starts, neighbours, paths, and retrieval
- Authored contracts and heritage
- Built-in import relationships
- Imported-symbol references
- Definite calls

Use these contracts for source exploration and graph-shaped questions. Read
[language-resolution.md](language-resolution.md) for JavaScript/TypeScript,
Go, and Rust resolver limits.

## Compact source by intent

Use `loci_explore(repo, intent, query, seed_ids=None)` when you need selected
source with its proof paths. Choose the meaning explicitly:

| Intent | Use | Traversal |
|---|---|---|
| `locate` | Find source declarations or pages. | Anchors only. |
| `type_dependencies` | Understand a TypeScript/TSX, Python, Go or Rust declaration's contract. | Authored type relations, three hops by default; Rust self types also select explicit impl sites in reverse. |
| `dependencies` | Understand a contract or JavaScript value/call dependencies. | Same type selection for the four families above; outgoing JavaScript calls, imported values and direct class bases. |
| `impact` | Inspect known static dependents before a change. | Incoming calls, references and types, one hop by default. |

Pass exact symbol seeds when known; otherwise the query selects anchors.
For a question about `processOrder`'s customer field, say so in `query`.
Immediate types and alias/heritage continuation receive priority; deeper
property branches need a matching query term. This is a relevance heuristic.
Every relationship still requires an existing exact or import-resolved edge.

Read `items` alongside their shared `sources` and `relationships`. Each
relationship retains its original direction and records forward or reverse
traversal. Treat `impact` as known static dependents, with non-exhaustive scope.
For execution paths or affected tests, select source with `locate` and inspect
the appropriate diagnostic tools and implementation. Consult the
[capability matrix](language-resolution.md#exploration-capabilities) for each
language's supported meaning and uncertainty boundaries.

Inspect `omissions` before concluding. A clipped anchor has `complete=false`;
use `loci_get` for its full definition before editing. Related definitions and
required proof source fit together or are omitted. Use `max_hops` and the two
byte limits for deliberate bounded follow-up, or use exact graph diagnostics
for a particular edge or rejected binding. The [output contract](tool-contracts.md#compact-exploration-output)
explains source IDs, coverage and byte accounting.

## Authored contracts and heritage

Use `loci_graph_references(repo, family="type", file=..., status="all",
detail="full")` to inspect declaration-owned observations and their exact
sites, bindings, support/control hashes and unresolved reasons. This includes
local type uses, aliases, supported bounds and explicit language-specific
contract clauses. The default `family="symbol"` retains executable
imported-reference ownership.

Traverse the language's stored relation with `exact` or `import-resolved`:
`uses_type`, `extends`, `implements`, Go `embeds`, or Rust `supertrait`,
`impl_trait` and `impl_self_type`. Inspect context and declaration ownership;
these relationships have different meanings. A longer path establishes no
structural compatibility, implicit satisfaction or runtime dispatch. Generic
shadowing, ambiguous exports and unsupported computations remain unresolved.

## Graph starts and traversal

Use `loci_graph_anchors` for a small explained set of graph starts. Pass exact
`seed_ids` when the start nodes are known. It does not traverse or decide
answerability.

Use `loci_graph_traverse_neighbors` for one filtered hop. Set namespace, edge
type, resolution, and direction explicitly when the domain is known. Use
`loci_graph_neighbors` only for exact outgoing `loci:contains` edges; it is not
an import/reference/call traversal tool.

Use `loci_graph_paths` when both endpoint sets are known. It returns ordered
nodes, stored edges, exact cached evidence lines, counts, and enforced budgets;
treat the result as evidenced reachability only. `loci_graph_retrieve` adds
retrieval scores and semantic bridge checks; inspect both `paths` and
`rejected_paths`. Neither tool decides whether a question is answerable or
sufficient. Filters default to `exact`, `declared`, and `import-resolved`;
never admit `heuristic` implicitly.

## Built-in import relationships

Indexed code files are stable zero-width `kind="file"` graph nodes. Build the
ID as `<normalized-repository-relative-path>::__file__#file`, for example
`src/loci/mcp_server.py::__file__#file`. Markdown keeps its existing page and
section nodes and receives no duplicate file node.

Resolved Python and JavaScript/TypeScript imports target file nodes and report
`target_kind="file"`, `target_file`, and null package/crate fields. Resolved
Go imports target one stable zero-width `kind="package"` node and report
`target_kind="package"`, `target_package`, and null file/crate fields. Go
package IDs have the form `<directory>::<effective-import-path>#package`; node
refs expose validated `directory`, `import_path`, and `package_name`.
Treat the node as the imported package even though a deterministic non-test Go
file anchors it for outline and retrieval.

Resolved Rust observations target an exact external module file or one stable
zero-width `kind="crate"` Cargo target. Crate IDs use
`<manifest>::<target-kind>:<crate-name>#crate`; records report
`target_kind="crate"`, `target_crate`, and null file/package fields. Node refs
expose validated `manifest`, `package_name`, `package_root`, `target_kind`,
`target_name`, `crate_name`, `crate_root`, `edition`, and `required_features`.
Inspect `raw.rust`, `resolution_basis`, `resolution_control_files`, and
`resolution_configuration` before explaining a Rust edge. The strict Rust
context fields are `kind`, `lexical_module_path`,
`lexical_module_visibilities`, `lexical_module_configurations`, `visibility`,
`module_level`, `configuration`, `path_override`, and `inline`.

Use `loci_graph_imports` to inspect every import observation, including
unresolved records:

```text
loci_graph_imports(
  repo="/path/to/repo",
  file="src/loci/mcp_server.py",
  status="all",
  offset=0,
  limit=100,
)
```

Each returned item retains raw syntax, source/target endpoints, target kind,
resolution tier, control provenance, and an explicit unresolved reason. The
bounded JSON envelope is:

```json
{"schema_version":1,"repo":"...","file":null,"status":"all","items":[{"raw":{"source_file":"src/a.py","language":"python","line":1,"text":"import b","specifier":"b","imported_name":null,"type_only":false,"is_reexport":false,"source_hash":"...","rust":null},"source_file":"src/a.py","source_id":"src/a.py::__file__#file","target_file":"src/b.py","target_package":null,"target_crate":null,"target_kind":"file","target_id":"src/b.py::__file__#file","specifier":"b","imported_name":null,"language":"python","line":1,"text":"import b","type_only":false,"is_reexport":false,"status":"resolved","resolution":"import-resolved","unresolved_reason":null,"resolution_basis":null,"resolution_control_files":[],"resolution_configuration":null}],"counts":{"total":1,"resolved":1,"unresolved":0,"returned":1},"pagination":{"offset":0,"limit":100,"next_offset":null}}
```

`loci_graph_references` and `loci_graph_calls` retain the import read's
item/count/pagination structure but add `detail` and `budget`; they are not the
same envelope as `loci_graph_imports`. Both default to `detail="compact"`.
Compact items expose source/target identity and files, relation, language,
line, column, byte offsets, text, status, resolution, unresolved reason, and
resolution configuration. Reference items also include nullable string
`context` (from `raw.context`) and `import_unresolved_reason`; call items also
include call-site `start_byte`/`end_byte`, callee-expression
`callee_start_byte`/`callee_end_byte`, and `reference_unresolved_reason`; a
call's `source_id` identifies its caller.
Use `detail="full"` for the former diagnostic item shape: raw syntax, selected
bindings or candidates, support records, and control provenance. A resolved
reference materializes an edge with `type="references"` (or
`references_type` for explicitly type-only TypeScript); a resolved call
materializes an edge with `type="calls"`. These are edge types, not top-level
fields of either compact or full record item.

Use `loci_graph_traverse_neighbors` for dependencies. Resolved runtime imports
use `namespace="loci"`, `type="imports"`, and
`resolution="import-resolved"`; type-only TypeScript imports use
`type="imports_type"`:

```text
loci_graph_traverse_neighbors(
  repo="/path/to/repo",
  seed_ids=["src/loci/mcp_server.py::__file__#file"],
  namespaces=["loci"],
  edge_types=["imports", "imports_type"],
  resolutions=["import-resolved"],
  direction="outgoing",
)
```

Use `direction="incoming"` to find importers; the stored edge still points
from importer to imported file and reports reverse traversal. Use
`loci_graph_paths` with the same filters for bounded dependency chains.

## Imported-symbol references

Use `loci_graph_references` for an imported class, function, type, constant,
interface, struct, or other indexed definition, rather than only its file,
package, or crate:

```text
loci_graph_references(
  repo="/path/to/repo",
  file="src/use.py",
  status="all",
  offset=0,
  limit=100,
  max_output_bytes=16384,
)
```

`file` is normalized and repository-relative, and selects the reference-site
file: this is an outgoing authored-record read, not an incoming search for
references to declarations in that file. `status` is `all`, `resolved`, or
`unresolved`; `offset` is non-negative; `limit` is 1..500. File filtering
precedes `total`, `resolved`, and `unresolved` counts; status filtering then
precedes pagination. Stable order is source file/line/column/byte, then binding
and target identity. Current reads preserve serialized hash and mtime. For
incoming consumers, use `loci_graph_traverse_neighbors` with the
exact target symbol ID, `references`/`references_type`, and
`direction="incoming"`; use `loci_explore(intent="impact")` for bounded known
dependents.

Resolved records materialize directed `namespace="loci"`,
`resolution="import-resolved"` edges: runtime `type="references"` and
explicitly type-only TypeScript `type="references_type"`. Source ownership
follows the nearest named executable body, matching call ownership: references
in decorators, annotations, defaults, and other definition-time expressions
belong to the enclosing executable scope, or the file node at repository top
level; they never inherit the callable being defined. The target is one exact
indexed symbol reached through the matched definite import and supported
export surface.

Compact reference records carry `source_id`, `source_file`, `target_id`,
`target_file`, `relation`, `language`, `line`, `column`, `start_byte`,
`end_byte`, `text`, `status`, `resolution`, `unresolved_reason`,
`resolution_configuration`, nullable string `context`, and
`import_unresolved_reason` where applicable. Request `detail="full"` for raw
syntax, selected import bindings, support records, and control provenance.

Traverse references with `loci_graph_traverse_neighbors` or `loci_graph_paths`
using `references`/`references_type` and `import-resolved`, in the required
direction. Use `loci_get` for the final target; do not use
`loci_graph_neighbors`. A reference never becomes a call. Shadowing,
ambiguous ownership, dynamic/computed syntax, inaccessible/external items,
divergent configurations, generated/macro output, overload or trait dispatch
remain unresolved or outside scope. Never substitute a repository-wide
same-name search.

## Definite calls

Use `loci_graph_calls` for definite static invocation:

```text
loci_graph_calls(
  repo="/path/to/repo",
  file="src/use.py",
  status="all",
  offset=0,
  limit=100,
  max_output_bytes=16384,
)
```

The file/status/page rules match `loci_graph_references`. `file` selects the
call-site file and returns outgoing authored calls, rather than incoming calls
to a declaration in that file. For callers, use
`loci_graph_traverse_neighbors` with the exact target symbol ID,
`edge_types=["calls"]`, and `direction="incoming"`; use
`loci_explore(intent="impact")` for bounded known dependents. Stable ordering
is source file/line/column/call byte/callee byte, then caller and target
identity. Current reads preserve serialized hash and mtime. A resolved record
materializes one directed `namespace="loci"`, `type="calls"` edge. Same-file
bindings use `resolution="exact"`; imported calls use
`resolution="import-resolved"` only when the callee span exactly joins one
accepted symbol-reference record.

Compact call records carry the common compact fields plus call-site
`start_byte`/`end_byte`, callee-expression
`callee_start_byte`/`callee_end_byte`, and `reference_unresolved_reason`.
Request `detail="full"` for raw call/callee syntax, caller ownership, local
binding candidates, resolved target support, and inherited reference/control
provenance.

For both record tools, `max_output_bytes` is a strict integer in 2,048..262,144
and defaults to 16,384. It caps the complete UTF-8 JSON MCP result for the
chosen detail, including `content`, `structuredContent`, and `isError`, but
excludes the JSON-RPC wrapper. `budget` reports `max_output_bytes`,
`output_bytes`, and `byte_limit_reached`. Counts and filtering retain their
usual meaning, but the cap may return fewer items than `limit`; follow
`pagination.next_offset` until null and advance only through delivered records.
If a compact or full record cannot fit on an otherwise empty page,
`OUTPUT_BUDGET_EXCEEDED` reports `required_output_bytes`, `offset`, and the
current maximum. Increase the budget or choose compact detail; the tool does
not silently skip a record.

Caller ownership follows executable bodies; module-level calls belong to the
file node, named nested callables keep their identity, and anonymous or
unindexed owners create no trusted edge. A proven recursive call is the only
valid call self-edge. Traverse calls with
`loci_graph_traverse_neighbors` or `loci_graph_paths` using `calls` and
`exact|import-resolved`:

```text
loci_graph_traverse_neighbors(
  repo="/path/to/repo",
  seed_ids=["src/provider.py::target#function"],
  namespaces=["loci"],
  edge_types=["calls"],
  resolutions=["exact", "import-resolved"],
  direction="incoming",
)
```

Use incoming direction for “what definitely calls this target?”,
`loci_graph_paths` for the exact cached call line, and `loci_get` for the
target. The supported static subset covers direct same-file named
functions/methods and imported calls across Python, JavaScript/TypeScript, Go,
and Rust where lexical binding, visibility, caller ownership, and inherited
configuration converge. Constructors, computed/dynamic/optional callees,
callable values or fields, receiver/interface/trait/virtual dispatch,
overloads, macros, reflection, generated code, external targets, type-only or
non-callable references, ambiguous/shadowed bindings, and divergent
configurations create no edge. There is no call CLI, model/judge call,
runtime/toolchain execution, repository-code execution, package-manager
access, or network access.
