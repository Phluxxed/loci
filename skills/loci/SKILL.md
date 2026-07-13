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
`loci_graph_traverse_neighbors`, `loci_graph_paths`, `loci_graph_retrieve`, and
`loci_graph_health`) refresh stale indexes before returning cached data.
Freshness includes repository-local graph profiles and contributions.
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
{"schema_version":1,"repo":"...","status":"healthy|degraded","profiles":[],"counts":{"profiles":0,"node_overlays":0,"edges":0,"contributions":0,"diagnostics":0},"diagnostics":[]}
```

`loci_graph_paths` returns `support_kind: "edge_sequence"`, ordered nodes,
stored edges, exact cached evidence lines, counts, and enforced budgets. Treat
that as evidenced reachability only. `loci_graph_retrieve` adds retrieval
scores and semantic bridge checks; inspect both `paths` and `rejected_paths`.
Neither tool decides whether the user's question is answerable or sufficient.
Filters default to the safe `exact` and `declared` resolution tiers.

MCP tool errors are structured under `structuredContent.error` with `code`, `message`, and `details`.

## Selection Rules

- Know the file, want symbols: `loci_outline` with `file`.
- Know the symbol name: `loci_search`, then `loci_get`.
- Know the symbol ID from outline: `loci_get` directly.
- Hunting string literals or error text: `loci_grep`.
- Need graph start nodes for a question: `loci_graph_anchors`; pass exact
  `seed_ids` to bypass inference.
- Need one filtered hop: `loci_graph_traverse_neighbors`; set namespace, edge
  type, resolution, and direction explicitly when the domain is known.
- Know both endpoint sets: `loci_graph_paths`; interpret the result as an
  evidenced edge sequence, not semantic proof.
- Need relationship-shaped evidence: `loci_graph_retrieve`; inspect rejected
  semantic bridges and hub shortcuts as well as selected paths.
- Need exact surrounding context: `loci_get` with `context` or `loci_file`.
- Non-code file such as JSON, YAML, TOML, or Markdown: `loci_file` or a normal targeted read.

## Diagnostics

Use `loci_analyze` when search misses, poor ranking, repeated refetches, or extraction quality look suspect. Treat findings as diagnostics to inspect, not orders to follow blindly.

Use CLI `loci stats --pretty` only for a human-readable shell/tmux savings view. Agents should prefer `loci_stats` for structured stats.
