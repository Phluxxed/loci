# loci

A local MCP server for LLM agent code navigation. loci parses your codebase into a byte-precise symbol index so an agent can fetch exactly the code it needs — no full-file reads, no grep loops.

**60–90% token savings** on typical codebase navigation tasks.

## How it works

loci uses [tree-sitter](https://tree-sitter.github.io/tree-sitter/) to parse source files into an AST, extracts symbols (functions, classes, methods, constants) with their byte offsets, and stores them in a local index. Retrieval is a direct byte-range read — no scanning.

The MCP workflow replaces 15–20 iterative Read/Grep calls with a small tool chain:

```text
loci_index -> loci_outline/loci_search/loci_graph_anchors -> loci_get/loci_graph_retrieve/loci_file -> loci_verify
```

The CLI still exists for debugging, scripts, and migration safety, but MCP is the production interface.

## Supported languages

Python, TypeScript, JavaScript, Go, Rust, Markdown

## Install

```bash
pip install loci
```

Or from source:

```bash
git clone https://github.com/phluxxed/loci
cd loci
pip install -e .
```

For repo-local dogfooding, install the tracked wrappers so both commands are
globally resolvable. The wrappers honor an explicit `LOCI_BASE_DIR`; otherwise
Claude Code uses `~/.claude/loci-index` via `CLAUDECODE=1`, and bare terminal
calls fall through to the Python store resolver. Codex and Claude MCP configs
should pass their agent-specific stores explicitly:

```bash
mkdir -p ~/.local/bin
ln -sf "$PWD/.shared/loci-wrapper.sh" ~/.local/bin/loci
ln -sf "$PWD/.shared/loci-mcp-wrapper.sh" ~/.local/bin/loci-mcp
```

This installs both command entrypoints:

| Command | Status | Purpose |
|---|---|---|
| `loci-mcp` | Primary | Local stdio MCP server for agents |
| `loci` | Legacy/debug | CLI for manual checks, scripts, and migration safety |

## MCP Setup

### Codex

Codex has a built-in MCP server manager. After installing loci, register the local stdio server:

```bash
codex mcp add --env LOCI_BASE_DIR="$HOME/.codex/loci-index" loci -- loci-mcp
codex mcp get --json loci
```

If `loci-mcp` is not on `PATH`, fix the install first. For repo-local
dogfooding, `~/.local/bin/loci-mcp` should symlink to
`.shared/loci-mcp-wrapper.sh`.

Direct `python -m loci.mcp_server` registration is useful for diagnostics, but
it should not be the permanent local config because it bypasses the tracked
wrapper.

Custom cache location:

```bash
codex mcp add --env LOCI_BASE_DIR=/absolute/path/to/.codeindex loci -- loci-mcp
```

### Claude Code

Claude Code has a built-in MCP server manager. After installing loci, register the local stdio server:

```bash
claude mcp add loci -s local -e LOCI_BASE_DIR="$HOME/.claude/loci-index" -- loci-mcp
claude mcp get loci
```

If `loci-mcp` is not on `PATH`, fix the install first. For repo-local
dogfooding, `~/.local/bin/loci-mcp` should symlink to
`.shared/loci-mcp-wrapper.sh`.

Direct `python -m loci.mcp_server` registration is useful for diagnostics, but
it should not be the permanent local config because it bypasses the tracked
wrapper.

Claude can also load MCP servers from config JSON. For a one-off launch:

```bash
claude --mcp-config '{"mcpServers":{"loci":{"command":"loci-mcp","args":[],"env":{"LOCI_BASE_DIR":"/absolute/path/to/.claude/loci-index"}}}}'
```

Or put the same config in a JSON file and pass the file path:

```json
{
  "mcpServers": {
    "loci": {
      "command": "loci-mcp",
      "args": [],
      "env": {
        "LOCI_BASE_DIR": "/absolute/path/to/.claude/loci-index"
      }
    }
  }
}
```

```bash
claude --mcp-config /absolute/path/to/loci-mcp.json
```

The diagnostic JSON form for the Python module is:

```json
{
  "mcpServers": {
    "loci": {
      "command": "/absolute/path/to/python",
      "args": ["-m", "loci.mcp_server"]
    }
  }
}
```

### Generic stdio MCP clients

For clients that use `mcpServers` JSON, configure the server as a local stdio process:

```json
{
  "mcpServers": {
    "loci": {
      "command": "loci-mcp",
      "args": [],
      "env": {
        "LOCI_BASE_DIR": "/absolute/path/to/.codeindex"
      }
    }
  }
}
```

`LOCI_BASE_DIR` is optional. If omitted, loci first looks for a configured
Codex MCP `LOCI_BASE_DIR`, then an existing `~/.codex/loci-index`, then falls
back to `~/.codeindex`.

### MCP Tools

MCP read tools refresh stale indexes before returning cached data. `loci_index`
still performs explicit indexing, while `loci_outline`, `loci_search`,
`loci_get`, `loci_file`, `loci_grep`, `loci_graph_anchors`,
`loci_graph_neighbors`, `loci_graph_traverse_neighbors`, `loci_graph_paths`,
`loci_graph_retrieve`, `loci_graph_imports`, `loci_graph_references`, and
`loci_graph_calls`, and `loci_graph_health` first check indexed source, profile,
and contribution hashes against the current repository and run a locked
incremental refresh if needed.
Freshness also includes Go module/workspace controls, JavaScript/TypeScript
project/package/workspace controls, and Cargo manifests.

| Tool | Purpose |
|---|---|
| `loci_index` | Index a local repo path, optionally incrementally |
| `loci_outline` | Return indexed symbols grouped by file |
| `loci_search` | Search indexed symbols by query |
| `loci_get` | Return exact source for one or more symbol IDs |
| `loci_file` | Return cached file content with optional line range |
| `loci_grep` | Regex-search cached files |
| `loci_graph_anchors` | Select a bounded, explained set of graph start nodes from a question or exact seeds |
| `loci_graph_neighbors` | Return exact outgoing one-hop neighbours for indexed seed nodes |
| `loci_graph_traverse_neighbors` | Return filtered one-hop neighbours with explicit traversal orientation and omissions |
| `loci_graph_paths` | Find bounded, evidence-backed paths between exact endpoint IDs |
| `loci_graph_retrieve` | Rank question-shaped paths and expose rejected semantic or hub shortcuts |
| `loci_graph_imports` | Inspect bounded resolved and unresolved built-in import records |
| `loci_graph_references` | Inspect bounded resolved and unresolved imported-symbol references |
| `loci_graph_calls` | Inspect bounded resolved and unresolved definite-call records |
| `loci_graph_health` | Report loaded graph profiles, active record counts, and diagnostics |
| `loci_verify` | Verify index integrity and content drift |
| `loci_list` | List indexed repos |
| `loci_stats` | Return structured retrieval savings stats |
| `loci_analyze` | Return structured search and extraction diagnostics |

## CLI Usage

The CLI is retained as legacy/debug tooling. New production agent workflows should use MCP.

```bash
# First index or explicit CLI refresh
loci index /path/to/repo
loci index /path/to/repo --incremental

# Get all symbols + IDs
loci outline /path/to/repo
loci outline /path/to/repo --file src/foo.py   # single file

# Fetch symbol source by ID
loci get abc123 def456 --repo /path/to/repo
loci get abc123 --repo /path/to/repo --context 5  # +5 lines surrounding context

# Search by name or concept
loci search "parse file" --repo /path/to/repo
loci search "auth" --repo /path/to/repo --kind function --lang python

# Read a non-symbol file (config, docs, etc.)
loci file pyproject.toml --repo /path/to/repo
loci file src/foo.py --repo /path/to/repo --start 10 --end 40

# Search file contents by regex
loci grep "TODO|FIXME" --repo /path/to/repo

# Index health
loci verify /path/to/repo          # check for content drift
loci list                           # all indexed repos
loci invalidate /path/to/repo      # clear stale cache

# Human token savings analytics
loci stats
loci stats --pretty
loci stats --repo /path/to/repo
```

## Symbol fields

Every symbol carries: `id`, `name`, `qualified_name`, `kind`, `language`, `file_path`, `byte_offset`, `byte_length`, `line`, `end_line`, `signature`, `docstring`, `summary`, `keywords`, `decorators`, `metadata`, `content_hash`.

Markdown files are indexed as `kind="section"` symbols. YAML frontmatter is parsed with PyYAML and attached to page-root markdown symbols under `metadata.frontmatter`; frontmatter fields such as `tags`, `category`, `type`, `source`, and `description` contribute to search. Frontmatter is metadata only, not a separate symbol.

Markdown symbols also carry hierarchy and retrieval-cost data under `metadata.markdown`: `heading_level`, `parent_id`, `root_id`, `page_root`, `synthetic_name`, `file_bytes`, `saved_pct`, and `span_kind`. `loci_outline` and `loci_search` copy `file_bytes`, `saved_pct`, and `span_kind` to the top level for markdown rows so agents can see when a page root is valid but expensive and a child section is the better retrieval target.

Markdown search results include `match_scope`, for example `section_heading`, `page_frontmatter.tags`, or `inherited_page_frontmatter.tags`. Child sections do not own page frontmatter; inherited scopes only explain why search surfaced that section from its page's metadata. `loci_get` still returns the exact requested byte range.

## Graph extensions

Repositories may declare bounded graph profiles in
`.loci/graph/profiles/*.json` and contribution documents in
`.loci/graph/contributions/*.json`. Profiles can select explicit Markdown
frontmatter fields for page-root node overlays and declared domain edges.
Invalid, stale, or conflicting extension records are excluded from the active
graph and reported by `loci_graph_health`; they do not hide an otherwise valid
symbol index.

`loci_graph_neighbors` remains compatibility-stable and exact-only: it returns
directed `loci:contains` edges and never mixes in declared domain or built-in
import edges. Use `loci_graph_traverse_neighbors` for dependencies. It is the
additive filtered form: callers choose namespaces, edge types, resolution
tiers, and direction, and every result keeps the stored edge plus
`traversed: forward|reverse`.

Use `loci_graph_anchors` when only the graph starts are needed. It collapses
inferred Markdown matches to one anchor per file, explains matched indexed
fields, and lets exact seed IDs bypass inference. Use `loci_graph_paths` when
both endpoint sets are known; its `support_kind: edge_sequence` means every
edge and cached evidence line exists, not that the composed path proves an
unstated claim. Use `loci_graph_retrieve` for a relationship question. It
ranks bounded paths and returns unsupported compositions under
`rejected_paths` with stable reasons such as `SEMANTIC_BRIDGE_MISSING` and
`HUB_SHORTCUT`.

Traversal defaults to the categorical `exact`, `declared`, and
`import-resolved` resolution tiers; heuristic edges are not admitted
implicitly. Hop, node, path, offset, evidence byte, and estimated-token budgets
are validated and reported. Graph retrieval never returns an `answerable` or
`sufficient` decision. Anchor and retrieval scores rank observable evidence
only. Use `loci_graph_health` to inspect the persisted extension state and any
excluded records.

### Built-in import relationships

Every indexed Python, Go, Rust, and supported JavaScript/TypeScript source file
has a stable, zero-width `kind="file"` graph node. The JavaScript/TypeScript
family is `.ts`, `.tsx`, `.mts`, `.cts`, `.js`, `.jsx`, `.mjs`, and `.cjs`.
A file-node ID is the normalized repository-relative path followed by
`::__file__#file`, for example `src/loci/mcp_server.py::__file__#file`.
Markdown keeps its existing page and section nodes and does not receive a
duplicate file node.

Resolved Python and JavaScript/TypeScript imports become directed
`namespace="loci"` edges from importer to imported file. Runtime dependencies
use `type="imports"`; type-only TypeScript dependencies use
`type="imports_type"`; both use `resolution="import-resolved"` and retain the
exact source statement as evidence. Re-exports remain distinguishable on the
diagnostic record.

Resolved Go imports target one stable `kind="package"` node, never an arbitrary
`.go` file. A package node ID combines its repository-relative directory and
effective import path, for example
`internal/store::example.com/project/internal/store#package`. The node is
anchored to a deterministic indexed non-test Go file for outline and retrieval,
but has a zero-width span and exposes validated `directory`, `import_path`, and
`package_name` attributes. An import record distinguishes this package target
with `target_kind="package"`, `target_package`, and null file/crate fields.
Resolved Python and JavaScript/TypeScript records instead use
`target_kind="file"`, `target_file`, and null package/crate fields.

Resolved Rust observations target either the exact external module file or a
stable zero-width `kind="crate"` node for one Cargo target. A crate-node ID is
`<manifest>::<target-kind>:<crate-name>#crate`, for example
`core/Cargo.toml::lib:core#crate`. Crate endpoints expose validated manifest,
package root/name, target kind/name, crate name/root, edition, and required
features. Import records distinguish crate targets with
`target_kind="crate"`, `target_crate`, and null file/package target fields.
Their strict `raw.rust` context preserves the observation kind, lexical module
ancestry, visibility, scope, configuration, and literal path override needed
to reproduce resolution after an incremental restart. Its exact fields are
`kind`, `lexical_module_path`, `lexical_module_visibilities`,
`lexical_module_configurations`, `visibility`, `module_level`, `configuration`,
`path_override`, and `inline`.

JavaScript/TypeScript resolution is static, deterministic, and contained in
the indexed repository. Loci understands relative imports, bounded
`tsconfig.json`/`jsconfig.json` options (`paths`, `baseUrl`, `rootDirs`,
`moduleSuffixes`, local `extends`, and the package-map switches), package-json
workspaces, restricted `pnpm-workspace.yaml` membership, package `exports` and
private `imports`, self-references, and conservative legacy package entries.
Workspace imports require both a unique active package and an explicit source
package dependency declaration. Each diagnostic import item reports
`resolution_basis` and the repository-relative `resolution_control_files` that
justify the result.

Loci does not inspect `node_modules`, lockfiles, package-manager stores, custom
loader or bundler aliases, package-based TypeScript config inheritance, or
generated files that are absent from the index. It does not execute Node,
TypeScript, package managers, scripts, bundlers, generators, or repository
code, and it does not use the network. Dynamic `import()` and shadowable
`require()` calls are outside this static observation contract. Missing,
ambiguous, inaccessible, or unsupported routes remain explicit unresolved
records rather than guessed source links.

Use the MCP diagnostic read to inspect observations, including imports that did
not become graph edges:

```text
loci_graph_imports(
  repo="/path/to/repo",
  file="src/loci/mcp_server.py",
  status="all",
  offset=0,
  limit=100,
)
```

Use generic traversal for the dependency graph. The outgoing call answers
"what does this file import?"; changing `direction` to `incoming` answers
"which files import this file or package?" without reversing the stored edge:

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

`loci_graph_paths` can use the same filters for bounded, evidence-backed
dependency chains. Do not use `loci_graph_neighbors` for imports; that tool is
intentionally pinned to exact outgoing containment for compatibility.

Go resolution is repository-contained and conservative. Loci parses bounded,
regular, non-symlink `go.mod` and `go.work` files without running Go or
repository code. It resolves same-module packages, explicitly active contained
workspace modules, and contained local replacements backed by direct,
unambiguous requirements. It enforces nested-module ownership and Go
`internal` visibility, excludes `vendor`, test-only directories, invalid or
conflicting package declarations, and `package main` commands as targets, and
never guesses by package name.

Loci deliberately does not download modules, inspect Go caches or environment
workspace settings, implement minimal version selection, follow remote
replacements, model vendoring, or evaluate build, platform, architecture, or
cgo constraints. Those cases remain explicit unresolved observations.

Rust resolution is Cargo-aware, deterministic, and repository-contained. Loci
loads bounded regular, non-symlink `Cargo.toml` files and supports standalone
packages, root or virtual workspaces, contained members, inherited workspace
dependencies, and contained path dependencies. It constructs library, binary,
example, test, benchmark, and build-script crate targets; expands Rust `use`
trees; records `extern crate`; builds the explicit inline/external module tree;
applies edition-aware `crate`/`self`/`super`/extern paths, definite module
aliases/re-exports, dependency-kind availability, and known module visibility.
It never resolves by repository-wide filename, package-name, or crate-name
similarity.

Rust edges describe declared-possible static dependencies, not one active
Cargo build. `resolution_configuration="unconditional"` means no supported
configuration gate was observed; `"declared_possible"` means the one proven
endpoint depends on a declared `cfg`, optional or target-specific dependency,
or required feature. Divergent conditional endpoints remain
`unresolved/ambiguous`. Registry/git dependencies and standard-library crates
remain external even if a same-named local package exists.

Loci never runs Cargo, rustc, rustdoc, build scripts, macros, generators,
tests, examples, or repository binaries, and never uses the network, Cargo
home, target directory, ambient workspace, environment/toolchain state, or
lockfiles. It does not choose features, target triples, profiles, or `cfg`
truth; expand macros or generated modules; infer undeclared source files;
or create call edges from an import alone. A Rust import edge alone never
resolves a terminal item; the separate resolved-symbol reference layer can do
so only for the bounded, visibility-checked, configuration-convergent subset
documented below. Unsupported,
missing, external, inaccessible, and ambiguous routes remain inspectable
records rather than guessed edges.

Unresolved, ambiguous, external, inaccessible, unsupported-configuration, and
unsupported-language observations remain bounded records with an explicit
`unresolved_reason`. They are visible through `loci_graph_imports`, do not
become edges, and do not degrade graph health when they are normal resolution
outcomes. `loci_graph_health` reports
`graph_file_nodes_indexed`, `graph_go_packages_indexed`,
`graph_rust_crates_indexed`, `graph_imports_indexed`,
`graph_imports_resolved`, `graph_imports_unresolved`,
`graph_symbol_references_indexed`, `graph_symbol_references_resolved`, and
`graph_symbol_references_unresolved`, plus `graph_calls_indexed`,
`graph_calls_resolved`, and `graph_calls_unresolved`; invalid controls,
extraction failures, or persistence failures still appear as diagnostics.
Loci never falls back to a repository-wide name guess. There is no import CLI
command or separate top-level import store.

### Built-in resolved symbol references

Loci can refine a proven file, package, or crate import into a directed
symbol-level relationship when the source syntax establishes one definite
local binding and the imported endpoint exposes one exact accessible indexed
symbol. Runtime references use `type="references"`; explicitly type-only
TypeScript references use `type="references_type"`. Both use
`namespace="loci"`, `resolution="import-resolved"`, and retain the exact source
line and content hash as evidence.

The source endpoint is the unique smallest indexed function, method, or class
that contains the reference. Module-level code uses the source file node. The
target is always the exact indexed definition reached through the matched
import and supported export surface. A same-named symbol elsewhere in the
repository is never a candidate.

Inspect stored outcomes through the MCP-only diagnostic read:

```text
loci_graph_references(
  repo="/path/to/repo",
  file="src/consumer.py",
  status="all",       # all | resolved | unresolved
  offset=0,
  limit=100,          # 1..500
)
```

The response reports the raw reference, selected import binding, source and
import endpoints, exact target when resolved, support records, resolution
basis and controls, and explicit reference/import failure reasons. `file`
filters before counts; `status` filters the returned items after total,
resolved, and unresolved counts are calculated; `offset` and `limit` paginate
the stable source-position order. Current reads do not rewrite a current
index.

Use the generic graph tools to navigate trusted reference edges. Outgoing
traversal answers “which imported symbols does this function name?”; incoming
traversal answers “which indexed symbols name this definition?” without
reversing the stored edge:

```text
loci_graph_traverse_neighbors(
  repo="/path/to/repo",
  seed_ids=["src/consumer.py::build#function"],
  namespaces=["loci"],
  edge_types=["references", "references_type"],
  resolutions=["import-resolved"],
  direction="outgoing",
)
```

`loci_graph_paths` accepts the same filters and hydrates the cached reference
line. `loci_get` then retrieves the exact target source. Compatibility
`loci_graph_neighbors` remains contains-only and never widens to references.

Reference resolution alone does not claim invocation. A call edge requires the
separate static call-site and caller-ownership proof below. References still do
not choose runtime overloads or trait implementations, expand macros/generated
code, interpret dynamic imports or computed member access, or compensate for
unresolved, shadowed, ambiguous, inaccessible, external, unsupported, or
configuration-divergent evidence. Those cases stay inspectable unresolved
records and create no trusted reference edge. There is no reference CLI
command, model call, runtime/toolchain execution, repository-code execution,
package-manager access, or network access in this path.

### Built-in trustworthy call relationships

Loci records a directed `namespace="loci"`, `type="calls"` edge only when a
static call expression has one definite caller and one definite indexed
function or method target. A same-file call uses `resolution="exact"` after
lexical scope, visibility, shadowing, and declaration ownership prove one
callable. A cross-file call uses `resolution="import-resolved"` only when the
callee span exactly matches one already-resolved symbol-reference record.

Caller ownership follows executable bodies. Calls in decorators, annotations,
default arguments, class/module initialization, nested named functions, and
anonymous functions are not silently assigned to a broader enclosing symbol.
Module-level calls use the source file node; named nested functions keep their
own indexed identity. A proven recursive call may be a trusted self-edge, while
every other graph self-edge remains invalid.

Inspect every stored outcome through the MCP-only diagnostic read:

```text
loci_graph_calls(
  repo="/path/to/repo",
  file="src/consumer.py",
  status="all",       # all | resolved | unresolved
  offset=0,
  limit=100,          # 1..500
)
```

Each item retains the exact raw call/callee bytes, line, column, text, path,
caller ownership, source hash, local binding candidates or symbol-reference
support, target when resolved, support records, inherited control/configuration
provenance, and an explicit unresolved reason. `file` filters before counts;
`status` filters before pagination; stable ordering starts with source
file/line/column/call byte/callee byte. Current reads preserve a current
index's serialized hash and mtime.

Use the generic graph tools for call navigation. Outgoing traversal answers
“what does this function definitely call?”; incoming traversal answers “what
definitely calls this function?” without reversing stored edge direction:

```text
loci_graph_traverse_neighbors(
  repo="/path/to/repo",
  seed_ids=["src/consumer.py::build#function"],
  namespaces=["loci"],
  edge_types=["calls"],
  resolutions=["exact", "import-resolved"],
  direction="outgoing",
)
```

`loci_graph_paths` accepts the same filters and hydrates the exact call line;
`loci_get` retrieves the final target. Compatibility
`loci_graph_neighbors` remains contains-only.

This is deliberately not whole-program call analysis. Constructors, computed
or dynamic callees, optional JavaScript calls, callable variables/fields,
receiver/interface/trait/virtual dispatch, overload selection, macros,
reflection, generated code, external targets, type-only bindings, non-callable
targets, ambiguous or shadowed bindings, and divergent configurations create
no trusted call edge. Loci never falls back to a repository-wide same-name
search. There is no call CLI, model or judge call, runtime/toolchain execution,
repository-code execution, package-manager access, or network access in this
path.

## Analytics

loci logs every search and get to a session file. The `loci_analyze` MCP tool
reads that log and surfaces actionable findings:

| Finding type | What it means |
|---|---|
| `search_miss` | Symbol exists but search returned nothing — fix keyword extraction |
| `search_blind_spot` | A symbol kind is never surfaced by search |
| `search_ranking_poor` | Correct symbol exists but ranked too low |
| `poor_extraction` | High refetch rate on a symbol kind |
| `refetch_hotspot` | Same symbol fetched repeatedly in a session |
| `kind_dead_weight` | A symbol kind is indexed but never retrieved |

For a shell or tmux stats readout, use `loci stats --pretty`. Without
`LOCI_BASE_DIR`, CLI stats prefer the configured Codex MCP store when it is
discoverable. Set `LOCI_BASE_DIR=/path/to/store` to inspect a specific store.

## Agent configuration

For loci to be useful, your agent needs to know it exists and how to use it. The full workflow guide is in `skills/loci/SKILL.md` — paste it into your system prompt or agent instructions if your agent does not load skills automatically.

The one-line version to add to any agent's instructions:

```
Use loci for codebase navigation. Prefer MCP tools (`loci_index`,
`loci_outline`/`loci_search`, then `loci_get`) over reading files directly.
If MCP is unavailable, configure the local stdio MCP server first. Use the
`loci` CLI only as a temporary bridge until the agent runtime can see the MCP
tools.
```

For Claude specifically, add this to your `CLAUDE.md`:

```
**MANDATORY**: Use the `loci` skill at the start of any non-trivial codebase task.
Prefer the local `loci` MCP server. If MCP tools are not visible, configure
loci first with `claude mcp add loci -s local -e LOCI_BASE_DIR="$HOME/.claude/loci-index" -- loci-mcp` and `claude mcp get loci`.
Tell the user a fresh Claude session may be required before the new `loci_*`
tools are visible. Use `loci` CLI fallback only as a temporary bridge.
```

## Claude Code integration

loci is most useful inside Claude Code when the MCP server is available. The SessionStart hook can seed an uncached repo and inject context, but MCP read tools are the freshness guarantee. The hooks live in `.claude/`; the reusable skill lives in `skills/loci/` and is symlinked into Claude.

The Claude hooks do not silently mutate Claude MCP config during session start. They keep CLI bridge tooling available, and they instruct Claude to configure MCP first when the `loci_*` tools are not visible.

**Install**

```bash
python3 .claude/install-hooks.sh
```

This symlinks the hooks and skill files into `~/.claude/` and patches `~/.claude/settings.json` to register them. Restart Claude Code after running it.

**What gets installed**

| Component | Location | Effect |
|---|---|---|
| `loci-session-start.sh` | `~/.claude/hooks/` | Reports an existing index, or runs bounded initial `loci index --incremental` when no cache exists |
| `loci-agent-inject.sh` | `~/.claude/hooks/` | Injects the skill into subagent prompts before `Agent` tool calls |
| `SKILL.md` | `~/.claude/skills/loci/` | The agent workflow guide Claude loads via the `loci` skill |

## Codex integration

loci can run as a local MCP server inside Codex. This is the preferred Codex integration.

```bash
codex mcp add --env LOCI_BASE_DIR="$HOME/.codex/loci-index" loci -- loci-mcp
codex mcp get --json loci
```

The older Codex hooks in `.codex/` can still seed uncached repos and inject a context line, but they are now optional CLI-era compatibility tooling. MCP reads enforce freshness when Codex actually uses the index.

**Prerequisites**

- loci installed (`pip install loci`)
- Codex using the default `~/.codex` home
- root direnv Python available at `~/.direnv/python-*`

**Install**

```bash
python3 .codex/install-hooks.py
```

This symlinks the repo hooks into `~/.codex/hooks/` and patches `~/.codex/hooks.json` to register the `SessionStart` hook. Restart Codex after running it.

The session-start hook sources the shared root direnv Python environment before resolving `loci`, so installing `loci` into that root environment is the intended setup.

**What gets installed**

| Component | Location | Effect |
|---|---|---|
| `loci-session-start.sh` | `~/.codex/hooks/` | Reports an existing index, or runs bounded initial CLI `loci index --incremental` when no cache exists |

## Development

```bash
# Install with dev deps
pip install -e ".[dev]"

# Run tests
python -m pytest tests/
```

## License

MIT
