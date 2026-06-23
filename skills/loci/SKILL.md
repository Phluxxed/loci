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
```

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
loci index <path> --incremental
loci outline <path>
loci get <id> [<id> ...] --repo <path>
```

When MCP tools are not visible, say this once before configuring MCP:

```text
loci MCP is not configured in this session; I am adding it as a local stdio MCP server with command `loci-mcp`. A fresh agent session may be required before the `loci_*` tools are visible.
```

Choose `<path>` as the actual repository or workspace being changed, not automatically the shell cwd. If the user names files under another root, or investigation shows the relevant code lives outside cwd, run loci against that target root.

Use `outline -> get` first for non-trivial code work. Use `search -> get` when you know the concept or symbol name but not the file. Do not ask the user to operate loci for you.

1. Run `loci_index` for the target repo, or `loci index` as CLI fallback.
2. Run `loci_outline` or `loci_search` to get symbol IDs.
3. Fetch only relevant symbols with `loci_get`, or `loci get` as CLI fallback.
4. Use `loci_file` only for targeted non-symbol reads after loci identifies the relevant file/range.

If loci is unavailable, fails, or the task is a standalone doc/config check where symbol navigation is clearly irrelevant, say so briefly and continue with normal tools.

## MCP Tools

| Tool | Use when |
| --- | --- |
| `loci_index` | Starting work, or after edits |
| `loci_outline` | Getting symbols and IDs by repo or file |
| `loci_search` | Finding symbols by name or concept |
| `loci_get` | Fetching exact symbol source |
| `loci_file` | Reading targeted non-symbol file content |
| `loci_grep` | Hunting string literals, errors, or config keys |
| `loci_verify` | Checking index integrity and content drift |
| `loci_list` | Listing indexed repos |

## CLI Fallback

| Command | Use when MCP is unavailable |
| --- | --- |
| `loci index <path> [--incremental]` | Starting work, or after edits |
| `loci outline <path> [--file <rel>]` | Getting symbols and IDs |
| `loci get <id> [<id> ...] --repo <path> [--context N]` | Fetching symbol source |
| `loci search <query> --repo <path> [--kind K] [--lang L]` | Finding symbols by name or concept |
| `loci file <rel_path> --repo <path> [--start N] [--end N]` | Reading non-symbol files |
| `loci grep <pattern> --repo <path>` | Hunting string literals, errors, or config keys |
| `loci verify <path>` | Checking index integrity and content drift |
| `loci summarize <path>` | Checking for unsummarized symbols |
| `loci stats [--repo <path>] [--pretty]` | Checking token savings |
| `loci list` | Listing indexed repos |
| `loci invalidate <path>` | Clearing stale cache |
| `loci analyze [--repo <path>]` | Finding search or extraction blind spots |

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

MCP tool errors are structured under `structuredContent.error` with `code`, `message`, and `details`.

## Selection Rules

- Know the file, want symbols: `loci_outline` with `file`.
- Know the symbol name: `loci_search`, then `loci_get`.
- Know the symbol ID from outline: `loci_get` directly.
- Hunting string literals or error text: `loci_grep`.
- Need exact surrounding context: `loci_get` with `context` or `loci_file`.
- Non-code file such as JSON, YAML, TOML, or Markdown: `loci_file` or a normal targeted read.

## Summaries

After indexing a repo you expect to keep using, run the CLI maintenance command `loci summarize <path>` to report symbols without summaries. If it returns an empty array, continue with `loci_outline`, `loci_search`, and `loci_get`.

Generate summaries as agent maintenance only when better symbol summaries would materially help repeated navigation, conceptual search, or ranking. If summarization is not worth the extra work for the task, skip it.

When generating summaries:

1. Split the unsummarized symbol array into chunks of up to 200 symbols.
2. Use `summarizer-prompt.md` from this skill directory as the prompt for each chunk.
3. Require raw JSON only. If the response includes markdown fences or extra text, strip them. If JSON is still malformed, retry once with: `Return only a raw JSON array, no markdown`.
4. Merge chunk results into one JSON array of `{ "id": "...", "summary": "..." }` objects.
5. Write the merged array to a temp file, apply it, then delete the temp file.

To apply generated summaries:

```bash
loci summarize <path> --apply /path/to/summaries.json
```

The expected summaries file is a JSON array of summary objects.
