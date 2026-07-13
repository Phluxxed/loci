---
name: loci
description: Use at the start of any non-trivial codebase task to navigate symbols efficiently. Prefer the local loci MCP server; configure it when missing.
---

# loci - Agent Workflow Guide

loci is your primary tool for codebase navigation. It indexes symbols with byte-precise offsets so you fetch exactly what you need instead of reading entire files. MCP is the production interface; the CLI is legacy/debug and temporary bridge tooling.

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
`loci_graph_traverse_neighbors`, `loci_graph_paths`, `loci_graph_retrieve`, and
`loci_graph_health`) refresh stale indexes before returning cached data.
Freshness includes repository-local graph profiles and contributions.
`loci_index` is still required for a repo that has never been indexed, and
remains useful for explicit rebuilds or after large changes.

If MCP tools are not configured in Claude Code, configure MCP first. Do not quietly continue with the CLI as the steady-state path.

```bash
claude mcp add loci -s local -e LOCI_BASE_DIR="$HOME/.claude/loci-index" -- loci-mcp
claude mcp get loci
```

If `loci-mcp` is not on `PATH`, fix the install or wrapper symlink first. For this repo-local install, `~/.local/bin/loci-mcp` should resolve to `.shared/loci-mcp-wrapper.sh`. Use `/absolute/path/to/python -m loci.mcp_server` only as a diagnostic fallback, not as the permanent MCP client config.

After adding MCP, tell the user a fresh Claude session may be required before the new `loci_*` tools are visible. Use CLI fallback only as a temporary bridge when MCP was just configured but the current Claude session cannot see the new tools yet, when MCP configuration fails, or when the user explicitly asks to continue without restarting.

```
loci index <path> [--incremental]    # first index or explicit CLI refresh
loci outline <path>                  # get ALL symbols + IDs in one call
loci get ID1 ID2 ...  --repo <path>  # fetch specific symbol source by ID
```

When MCP tools are not visible in Claude, say this once before configuring MCP:

```text
loci MCP is not configured in this Claude session; I am adding it as a local stdio MCP server with command `loci-mcp`. A fresh Claude session may be required before the `loci_*` tools are visible.
```

`outline -> get` is the key flow. `outline` gives you every symbol ID in one shot; use those IDs to call `get`. `search -> get` is the right flow when you know the concept or symbol name but not the file. This replaces 15-20 iterative Read/Grep calls.

## MCP Tools

| Tool | Use when |
|---------|----------|
| `loci_index` | First indexing, explicit rebuilds, or large changes |
| `loci_outline` | Getting the full symbol map |
| `loci_search` | Finding symbols by name/concept |
| `loci_get` | Fetching symbol source |
| `loci_file` | Reading targeted non-symbol files |
| `loci_grep` | Hunting string literals, error messages, config keys |
| `loci_graph_anchors` | Selecting bounded, explained graph starts from a question or exact seed IDs |
| `loci_graph_neighbors` | Reading exact outgoing one-hop neighbours from explicit seed IDs |
| `loci_graph_traverse_neighbors` | Reading filtered one-hop neighbours with explicit direction and omissions |
| `loci_graph_paths` | Finding bounded evidence-backed paths between exact endpoint IDs |
| `loci_graph_retrieve` | Retrieving and ranking question-shaped paths with inspected rejections |
| `loci_graph_health` | Inspecting loaded graph profiles, active counts, and degraded diagnostics |
| `loci_verify` | Checking index integrity + content drift |
| `loci_list` | Listing indexed repos |
| `loci_stats` | Reading structured usage and savings stats |
| `loci_analyze` | Finding search or extraction blind spots |

## CLI Fallback

| Command | Use when MCP is unavailable |
|---------|----------|
| `loci index <path> [--incremental]` | First indexing or explicit CLI refresh |
| `loci outline <path> [--file <rel>]` | Getting the full symbol map |
| `loci get ID1 [ID2 ...] --repo <path> [--context N]` | Fetching symbol source |
| `loci search <query> --repo <path> [--kind K] [--lang L]` | Finding symbols by name/concept |
| `loci file <rel_path> --repo <path> [--start N] [--end N]` | Reading non-symbol files (config, docs) |
| `loci grep <pattern> --repo <path>` | Hunting string literals, error messages, config keys |
| `loci verify <path>` | Checking index integrity + content drift |
| `loci stats [--repo <path>] [--pretty]` | Checking token savings |
| `loci list` | Listing indexed repos |
| `loci invalidate <path>` | Clearing stale cache |

## Symbol Fields

Every symbol has: `id`, `name`, `qualified_name`, `kind`, `language`, `file_path`, `byte_offset`, `byte_length`, `line`, `end_line`, `signature`, `docstring`, `summary`, `keywords`, `decorators`, `content_hash`

## Output Schemas

**loci_outline** (grouped by file):
```json
{"files":[{"file": "src/foo.py", "symbols": [{"id": "...", "name": "...", "kind": "...", "line": 1, "end_line": 10, "signature": "...", "summary": ""}]}]}
```

**loci_get**:
```json
{"symbols":[{"id": "...", "source": "...", "line": 1, "end_line": 10, "byte_offset": 0, "byte_length": 200, "signature": "...", "kind": "function", "language": "python"}]}
```

**loci_search**:
```json
{"symbols":[{"id": "...", "name": "...", "kind": "...", "score": 20.0, "signature": "...", "summary": ""}]}
```

**loci_grep**:
```json
{"matches":[{"file": "...", "line": 42, "match": "...", "context_before": [...], "context_after": [...]}]}
```

**loci_graph_anchors**:
```json
{"schema_version":1,"repo":"...","question":"...","selection":"inferred|explicit","question_terms":[],"anchors":[{"node":{"id":"...","namespace":"loci","kind":"section","attributes":{"language":"markdown","file":"guide.md","line":1,"end_line":20}},"matched_symbol_id":"...","name":"Guide","score":12.3,"reason":{"kind":"inferred","matched_terms":["guide"],"match_scope":["file_basename"]}}],"counts":{"indexed_nodes":1,"eligible_units":1,"qualified_candidates":1,"collapsed_symbols":0,"returned_anchors":1,"omitted_candidates":0},"budget":{"requested_max_anchors":10,"effective_max_anchors":1},"diagnostics":[]}
```

**loci_graph_health**:
```json
{"schema_version":1,"repo":"...","status":"healthy|degraded","profiles":[],"counts":{"profiles":0,"node_overlays":0,"edges":0,"contributions":0,"diagnostics":0},"diagnostics":[]}
```

`loci_graph_paths` returns `support_kind: "edge_sequence"`, ordered nodes,
stored edges, exact cached evidence lines, counts, and enforced budgets. Treat
that as evidenced reachability only. `loci_graph_retrieve` adds retrieval
scores and semantic bridge checks; inspect both `paths` and `rejected_paths`.
Neither tool decides whether the user's question is answerable or sufficient.
Filters default to the safe `exact` and `declared` resolution tiers.

MCP tool errors are structured under `structuredContent.error` with `code`, `message`, and `details`.

## When to Use What

- **Know the file, want all symbols** -> `loci_outline` with `file`
- **Know the symbol name** -> `loci_search` then `loci_get`
- **Know the symbol ID** (from outline) -> `loci_get` directly
- **Hunting a string/regex** -> `loci_grep`
- **Need graph start nodes for a question** -> `loci_graph_anchors`; pass exact
  `seed_ids` to bypass inference
- **Need one filtered hop** -> `loci_graph_traverse_neighbors`; set namespace,
  edge type, resolution, and direction explicitly when the domain is known
- **Know both endpoint sets** -> `loci_graph_paths`; interpret the result as an
  evidenced edge sequence, not semantic proof
- **Need relationship-shaped evidence** -> `loci_graph_retrieve`; inspect
  rejected semantic bridges and hub shortcuts as well as selected paths
- **Need surrounding file context** -> `loci_get` with `context` or `loci_file`
- **Non-code file** (JSON, YAML, Markdown) -> `loci_file`

## Diagnostics

Use `loci_analyze` when search misses, poor ranking, repeated refetches, or
extraction quality look suspect. Treat findings as diagnostics to inspect, not
orders to follow blindly.

| type | severity | action |
|------|----------|--------|
| `search_miss` | high | fix keyword extraction so the symbol surfaces |
| `search_blind_spot` | high | add/improve keywords for that symbol kind |
| `search_ranking_poor` | medium | adjust scoring weights |
| `poor_extraction` | medium | fix parser for the affected language/kind |
| `kind_dead_weight` | low | consider dropping that kind from index |
| `refetch_hotspot` | low | check why the same symbol is fetched repeatedly |

Output schema:
```json
{"repo": "...", "period_days": 7, "findings": [{"type": "...", "severity": "high|medium|low", "data": {}, "suggestion": "..."}]}
```

Use CLI `loci stats --pretty` only for a human-readable shell/tmux savings
view. Agents should prefer `loci_stats` for structured stats.

## loci vs Other Tools

| Situation | Use |
|-----------|-----|
| Indexed repo, exploring symbols | loci (always) |
| Non-indexed repo, quick 1-2 file lookup | Read/Grep directly |
| Non-indexed repo, broad exploration | Explore agent |
| Repo you'll work in for a while | Index it, then use loci |
