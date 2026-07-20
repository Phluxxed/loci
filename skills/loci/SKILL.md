---
name: loci
description: Agent-owned codebase navigation infrastructure. Use at the start of any codebase task to navigate symbols efficiently, reduce broad file reads, and fetch targeted source from indexed repos.
---

# loci - Codex Workflow Guide

loci is agent-owned codebase navigation infrastructure. The user is not expected to run it; you run it yourself to avoid broad file reads, reduce token waste, and fetch exactly the functions, classes, and methods you need.

## Core Workflow

Prefer the local MCP server when its tools are available:

```text
loci_index(path, incremental=true)
loci_outline(path) or loci_search(repo, query)
loci_get(repo, symbol_ids)
loci_analyze(repo) when diagnostics are needed
```

MCP read tools (`loci_outline`, `loci_search`, `loci_get`, `loci_file`,
`loci_grep`, `loci_graph_anchors`, `loci_graph_neighbors`,
`loci_graph_traverse_neighbors`, `loci_graph_paths`, `loci_graph_retrieve`,
`loci_graph_imports`, and `loci_graph_health`) refresh stale indexes before
returning cached data. Freshness includes repository-local graph profiles,
contributions, built-in import records, Go module/workspace controls, and
JavaScript/TypeScript package, workspace, and project controls, plus Cargo
manifests.
`loci_index` is still required for a repo that has never been indexed, and
remains useful for explicit rebuilds or after large changes.

If MCP tools are not configured in the current agent runtime, configure MCP first. Do not quietly continue with the CLI as the steady-state path.

For Claude Code, run:

```bash
claude mcp add loci -s local -e LOCI_BASE_DIR="$HOME/.claude/loci-index" -- loci-mcp
claude mcp get loci
```

For Codex, run:

```bash
codex mcp add --env LOCI_BASE_DIR="$HOME/.codex/loci-index" loci -- loci-mcp
codex mcp get --json loci
```

If `loci-mcp` is not on `PATH`, fix the install or wrapper symlink first. For this repo-local install, `~/.local/bin/loci-mcp` should resolve to `.shared/loci-mcp-wrapper.sh`. Use `/absolute/path/to/python -m loci.mcp_server` only as a diagnostic fallback, not as the permanent MCP client config.

After adding MCP, tell the user a fresh agent session may be required before the new `loci_*` tools are visible. Use CLI fallback only as a temporary bridge when MCP was just configured but the current runtime cannot see the new tools yet, when MCP configuration fails, or when the user explicitly asks to continue without restarting.

```bash
loci index <path> [--incremental]
loci outline <path>
loci get <id> [<id> ...] --repo <path>
```

When MCP tools are not visible, say this once before configuring MCP:

```text
loci MCP is not configured in this session; I am adding it as a local stdio MCP server with command `loci-mcp`. A fresh agent session may be required before the `loci_*` tools are visible.
```

Choose `<path>` as the actual repository or workspace being changed, not automatically the shell cwd. If the user names files under another root, or investigation shows the relevant code lives outside cwd, run loci against that target root.

Use `outline -> get` first for non-trivial code work. Use `search -> get` when you know the concept or symbol name but not the file. Do not ask the user to operate loci for you.

1. Run `loci_index` for an unindexed target repo, or `loci index` as CLI fallback.
2. Run `loci_outline` or `loci_search` to get symbol IDs.
3. Fetch only relevant symbols with `loci_get`, or `loci get` as CLI fallback.
4. Use `loci_file` only for targeted non-symbol reads after loci identifies the relevant file/range.

If loci is unavailable, fails, or the task is a standalone doc/config check where symbol navigation is clearly irrelevant, say so briefly and continue with normal tools.

## MCP Tools

| Tool | Use when |
| --- | --- |
| `loci_index` | First indexing, explicit rebuilds, or large changes |
| `loci_outline` | Getting symbols and IDs by repo or file |
| `loci_search` | Finding symbols by name or concept |
| `loci_get` | Fetching exact symbol source |
| `loci_file` | Reading targeted non-symbol file content |
| `loci_grep` | Hunting string literals, errors, or config keys |
| `loci_graph_anchors` | Selecting bounded, explained graph starts from a question or exact seed IDs |
| `loci_graph_neighbors` | Reading exact outgoing one-hop neighbours from explicit seed IDs |
| `loci_graph_traverse_neighbors` | Reading filtered one-hop neighbours with explicit direction and omissions |
| `loci_graph_paths` | Finding bounded evidence-backed paths between exact endpoint IDs |
| `loci_graph_retrieve` | Retrieving and ranking question-shaped paths with inspected rejections |
| `loci_graph_imports` | Inspecting bounded resolved and unresolved built-in import records |
| `loci_graph_health` | Inspecting loaded graph profiles, active counts, and degraded diagnostics |
| `loci_verify` | Checking index integrity and content drift |
| `loci_list` | Listing indexed repos |
| `loci_stats` | Reading structured usage and savings stats |
| `loci_analyze` | Finding search or extraction blind spots |

## CLI Fallback

| Command | Use when MCP is unavailable |
| --- | --- |
| `loci index <path> [--incremental]` | First indexing or explicit CLI refresh |
| `loci outline <path> [--file <rel>]` | Getting symbols and IDs |
| `loci get <id> [<id> ...] --repo <path> [--context N]` | Fetching symbol source |
| `loci search <query> --repo <path> [--kind K] [--lang L]` | Finding symbols by name or concept |
| `loci file <rel_path> --repo <path> [--start N] [--end N]` | Reading non-symbol files |
| `loci grep <pattern> --repo <path>` | Hunting string literals, errors, or config keys |
| `loci verify <path>` | Checking index integrity and content drift |
| `loci stats [--repo <path>] [--pretty]` | Checking token savings |
| `loci list` | Listing indexed repos |
| `loci invalidate <path>` | Clearing stale cache |

There is no CLI import command. Use `loci_graph_imports` through MCP for import
diagnostics and the generic graph MCP tools for dependency traversal.

## Output Schemas

`loci_outline` returns grouped files and symbols:

```json
{"files":[{"file":"src/foo.py","symbols":[{"id":"...","name":"...","kind":"function","line":1,"end_line":10,"signature":"...","summary":""}]}]}
```

`loci_get` returns exact source for the requested symbols:

```json
{"symbols":[{"id":"...","source":"...","line":1,"end_line":10,"byte_offset":0,"byte_length":200,"signature":"...","kind":"function","language":"python"}]}
```

`loci_search` returns ranked symbols:

```json
{"symbols":[{"id":"...","name":"...","kind":"function","score":20.0,"signature":"...","summary":""}]}
```

`loci_grep` returns matching lines with context:

```json
{"matches":[{"file":"...","line":42,"match":"...","context_before":[],"context_after":[]}]}
```

`loci_graph_anchors` returns inferred or explicit graph starts without
traversal or answerability claims:

```json
{"schema_version":1,"repo":"...","question":"...","selection":"inferred|explicit","question_terms":[],"anchors":[{"node":{"id":"...","namespace":"loci","kind":"section","attributes":{"language":"markdown","file":"guide.md","line":1,"end_line":20}},"matched_symbol_id":"...","name":"Guide","score":12.3,"reason":{"kind":"inferred","matched_terms":["guide"],"match_scope":["file_basename"]}}],"counts":{"indexed_nodes":1,"eligible_units":1,"qualified_candidates":1,"collapsed_symbols":0,"returned_anchors":1,"omitted_candidates":0},"budget":{"requested_max_anchors":10,"effective_max_anchors":1},"diagnostics":[]}
```

`loci_graph_health` returns persisted extension status and diagnostics:

```json
{"schema_version":1,"repo":"...","status":"healthy|degraded","profiles":[],"counts":{"profiles":0,"node_overlays":0,"edges":0,"contributions":0,"diagnostics":0,"graph_file_nodes_indexed":0,"graph_go_packages_indexed":0,"graph_rust_crates_indexed":0,"graph_imports_indexed":0,"graph_imports_resolved":0,"graph_imports_unresolved":0},"diagnostics":[]}
```

`loci_graph_imports` returns a bounded diagnostic page:

```json
{"schema_version":1,"repo":"...","file":null,"status":"all","items":[{"raw":{"source_file":"src/a.py","language":"python","line":1,"text":"import b","specifier":"b","imported_name":null,"type_only":false,"is_reexport":false,"source_hash":"...","rust":null},"source_file":"src/a.py","source_id":"src/a.py::__file__#file","target_file":"src/b.py","target_package":null,"target_crate":null,"target_kind":"file","target_id":"src/b.py::__file__#file","specifier":"b","imported_name":null,"language":"python","line":1,"text":"import b","type_only":false,"is_reexport":false,"status":"resolved","resolution":"import-resolved","unresolved_reason":null,"resolution_basis":null,"resolution_control_files":[],"resolution_configuration":null}],"counts":{"total":1,"resolved":1,"unresolved":0,"returned":1},"pagination":{"offset":0,"limit":100,"next_offset":null}}
```

`loci_graph_paths` returns `support_kind: "edge_sequence"`, ordered nodes,
stored edges, exact cached evidence lines, counts, and enforced budgets. Treat
that as evidenced reachability only. `loci_graph_retrieve` adds retrieval
scores and semantic bridge checks; inspect both `paths` and `rejected_paths`.
Neither tool decides whether the user's question is answerable or sufficient.
Filters default to the safe `exact`, `declared`, and `import-resolved`
resolution tiers. `heuristic` is never admitted implicitly.

MCP tool errors are structured under `structuredContent.error` with `code`, `message`, and `details`.

## Built-in Import Relationships

Indexed code files are stable zero-width `kind="file"` graph nodes. Build the
ID as `<normalized-repository-relative-path>::__file__#file`, for example
`src/loci/mcp_server.py::__file__#file`. Markdown uses its existing page and
section nodes and does not receive a duplicate file node.

Resolved Python and JavaScript/TypeScript imports target file nodes and report
`target_kind="file"`, `target_file`, and null package/crate fields. Resolved Go
imports target one stable zero-width `kind="package"` node and report
`target_kind="package"`, `target_package`, and null file/crate fields. Go package
IDs have the form `<directory>::<effective-import-path>#package`; node refs
expose validated `directory`, `import_path`, and `package_name` attributes.
Treat the node as the imported package even though a deterministic non-test Go
file anchors it for outline and retrieval.

Resolved Rust observations target an exact external module file or one stable
zero-width `kind="crate"` Cargo target. Crate IDs use
`<manifest>::<target-kind>:<crate-name>#crate`; records use
`target_kind="crate"`, `target_crate`, and null file/package fields for crate
targets. Node refs expose validated `manifest`, `package_name`, `package_root`,
`target_kind`, `target_name`, `crate_name`, `crate_root`, `edition`, and
`required_features`. Inspect `raw.rust`, `resolution_basis`,
`resolution_control_files`, and `resolution_configuration` before explaining a
Rust edge. The strict Rust context fields are `kind`, `lexical_module_path`,
`lexical_module_visibilities`, `lexical_module_configurations`, `visibility`,
`module_level`, `configuration`, `path_override`, and `inline`.

For JavaScript/TypeScript, inspect `resolution_basis` and
`resolution_control_files` before explaining why a file target was selected.
Supported sources are `.ts`, `.tsx`, `.mts`, `.cts`, `.js`, `.jsx`, `.mjs`,
and `.cjs`. The bounded resolver can use relative paths, standard
`tsconfig.json`/`jsconfig.json` controls, declared package-json or pnpm
workspaces, package `exports`/`imports`, self-references, and conservative
legacy entries. Workspace edges require a unique active package and an
explicit dependency declaration by the importing package.

Treat an unresolved result as evidence that Loci did not prove a repository
edge. Never compensate with a repository-wide filename or package-name guess.
Loci intentionally does not inspect installs or lockfiles, execute toolchains
or repository code, use the network, model custom loaders/bundler aliases, or
resolve dynamic `import()` and shadowable `require()` calls. Invalid controls
degrade graph health; normal missing, external, inaccessible, ambiguous, and
unsupported-configuration routes remain inspectable without becoming edges.

Use `loci_graph_imports` to inspect all import observations, including
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

Use `loci_graph_traverse_neighbors` for dependencies. Resolved runtime imports
have `namespace="loci"`, `type="imports"`, and
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

Use `direction="incoming"` to find importers; the returned stored edge still
points from importer to imported file and reports reverse traversal. Use
`loci_graph_paths` with the same filters for bounded dependency chains.

Do not use `loci_graph_neighbors` for imports. It intentionally returns only
exact outgoing `loci:contains` edges for compatibility.

Go resolution is intentionally bounded and repository-contained. It supports
same-module packages, explicitly active contained workspace modules, and
contained local replacements backed by direct unambiguous requirements. It
enforces nested-module ownership and `internal` visibility, rejects command
packages as targets, and excludes vendor, test-only, missing, invalid, or
conflicting package directories. It never runs Go or repository code, reads an
ambient workspace, downloads modules, implements minimal version selection,
follows remote replacements, models vendoring, or evaluates build/platform/cgo
constraints. Unsupported cases remain inspectable unresolved records rather
than guessed edges.

Rust resolution is intentionally bounded and repository-contained. It supports
strict Cargo packages/workspaces/targets, inherited or direct contained path
dependencies, same-package libraries, explicit inline/external module trees,
edition-aware paths, definite module aliases/re-exports, dependency-kind rules,
and known module visibility. It never binds by repository-wide filename,
package-name, or crate-name similarity. Registry/git/standard-library crates
remain external. Configuration-dependent relationships resolve only when all
supported alternatives converge, and are labeled
`resolution_configuration="declared_possible"`; unconditional relationships
are labeled `"unconditional"`. Divergent alternatives stay ambiguous.

Loci never runs Cargo/rustc/repository code, uses the network or ambient
toolchain state, reads lockfiles or Cargo caches, chooses an active feature,
target, profile, or cfg set, expands macros/generated modules, infers
undeclared files, resolves terminal Rust items, or creates call edges. Treat a
Rust edge as “this declared source can depend on this contained endpoint,” not
“the current default Cargo build activates this edge.”

Unresolved, ambiguous, external, inaccessible, unsupported-configuration, and
unsupported-language observations remain bounded records with an explicit
`unresolved_reason`. They never become graph edges and normal unresolved
outcomes do not degrade graph health. Invalid controls do degrade health.
Inspect aggregate file-node, Go-package, Rust-crate, and import counts with
`loci_graph_health`. Loci does not guess targets by bare name, maintain a
separate top-level import store, or expose an import CLI command.

## Selection Rules

- Know the file, want symbols: `loci_outline` with `file`.
- Know the symbol name: `loci_search`, then `loci_get`.
- Know the symbol ID from outline: `loci_get` directly.
- Hunting string literals or error text: `loci_grep`.
- Need graph start nodes for a question: `loci_graph_anchors`; pass exact
  `seed_ids` to bypass inference.
- Need one filtered hop: `loci_graph_traverse_neighbors`; set namespace, edge
  type, resolution, and direction explicitly when the domain is known.
- Need import observations or unresolved reasons: `loci_graph_imports`; filter
  by normalized repository-relative `file` and `status` when useful.
- Need code dependencies: start from exact file-node IDs and use
  `loci_graph_traverse_neighbors` or `loci_graph_paths`, never
  `loci_graph_neighbors`.
- Know both endpoint sets: `loci_graph_paths`; interpret the result as an
  evidenced edge sequence, not semantic proof.
- Need relationship-shaped evidence: `loci_graph_retrieve`; inspect rejected
  semantic bridges and hub shortcuts as well as selected paths.
- Need exact surrounding context: `loci_get` with `context` or `loci_file`.
- Non-code file such as JSON, YAML, TOML, or Markdown: `loci_file` or a normal targeted read.

## Diagnostics

Use `loci_analyze` when search misses, poor ranking, repeated refetches, or extraction quality look suspect. Treat findings as diagnostics to inspect, not orders to follow blindly.

Use CLI `loci stats --pretty` only for a human-readable shell/tmux savings view. Agents should prefer `loci_stats` for structured stats.
