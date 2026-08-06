# Graph navigation and relationship contracts

## Contents

- Graph starts, neighbours, paths, and retrieval
- Built-in import relationships
- Imported-symbol references
- Definite calls

Use these contracts only for graph-shaped questions. Read
[language-resolution.md](language-resolution.md) for JavaScript/TypeScript,
Go, and Rust resolver limits.

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

`loci_graph_references` and `loci_graph_calls` use the same bounded envelope;
each item retains exact raw spans, selected bindings, source ownership,
support records, control provenance, target identity, and explicit failure
reasons. A resolved reference item has `type="references"` (or
`references_type` for explicit type-only TypeScript), while a resolved call
item has `type="calls"` and carries caller/callee spans and support records.

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
)
```

`file` is normalized and repository-relative. `status` is `all`, `resolved`,
or `unresolved`; `offset` is non-negative; `limit` is 1..500. Filter by file
and status before counts/pagination; stable order is source file/line/column/
byte, then binding and target identity. Current reads preserve serialized hash
and mtime.

Resolved records materialize directed `namespace="loci"`,
`resolution="import-resolved"` edges: runtime `type="references"` and
explicitly type-only TypeScript `type="references_type"`. Source ownership
follows the nearest named executable body, matching call ownership: references
in decorators, annotations, defaults, and other definition-time expressions
belong to the enclosing executable scope, or the file node at repository top
level; they never inherit the callable being defined. The target is one exact
indexed symbol reached through the matched definite import and supported
export surface.

Reference records retain raw syntax, the selected import binding, source and
import endpoints, exact target, support records, control provenance, and
failure reasons. A resolved item carries `resolution_basis` plus support
entries for the import binding and definition.

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
)
```

The file/status/page rules match `loci_graph_references`; stable ordering is
source file/line/column/call byte/callee byte, then caller and target identity.
Current reads preserve serialized hash and mtime. A resolved record materializes
one directed `namespace="loci"`, `type="calls"` edge. Same-file bindings use
`resolution="exact"`; imported calls use `resolution="import-resolved"` only
when the callee span exactly joins one accepted symbol-reference record.

Call records retain the exact raw call/callee span, caller owner, local binding
candidates, resolved target, support records, inherited reference/control
provenance, and explicit failure reasons. A resolved item includes `caller_id`,
`caller_kind`, `target_file`, `target_id`, `target_kind`, `resolution_basis`,
and support entries for the call site, caller definition, and local/imported
definition.

Caller ownership follows executable bodies; module-level calls belong to the
file node, named nested callables keep their identity, and anonymous or
unindexed owners create no trusted edge. A proven recursive call is the only
valid call self-edge. Traverse calls with
`loci_graph_traverse_neighbors` or `loci_graph_paths` using `calls` and
`exact|import-resolved`:

```text
loci_graph_traverse_neighbors(
  repo="/path/to/repo",
  seed_ids=["src/use.py::build#function"],
  namespaces=["loci"],
  edge_types=["calls"],
  resolutions=["exact", "import-resolved"],
  direction="outgoing",
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
