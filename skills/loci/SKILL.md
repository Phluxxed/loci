---
name: loci
description: Agent-owned codebase navigation infrastructure. Use at the start of any codebase task to navigate symbols efficiently, reduce broad file reads, and fetch targeted source from indexed repos.
---

# loci - Codex Workflow Guide

loci is agent-owned codebase navigation infrastructure. The user is not expected to run it; you run it yourself to avoid broad file reads, reduce token waste, and fetch exactly the functions, classes, and methods you need.

## Core Workflow

```bash
loci index <path> --incremental
loci outline <path>
loci get <id> [<id> ...] --repo <path>
```

Choose `<path>` as the actual repository or workspace being changed, not automatically the shell cwd. If the user names files under another root, or investigation shows the relevant code lives outside cwd, run loci against that target root.

Use `outline -> get` first for non-trivial code work. Do not ask the user to operate loci for you.

1. Run `loci index <path> --incremental`.
2. Run `loci outline <path>` to get the symbol map.
3. Fetch only relevant symbols with `loci get <ids> --repo <path>`.
4. Use targeted file reads only after loci identifies relevant files, symbols, or flows.

If loci is unavailable, fails, or the task is a standalone doc/config check where symbol navigation is clearly irrelevant, say so briefly and continue with normal tools.

## Commands

| Command | Use when |
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

`outline` returns grouped files and symbols:

```json
[{"file":"src/foo.py","symbols":[{"id":"...","name":"...","kind":"function","line":1,"end_line":10,"signature":"...","summary":""}]}]
```

`get` returns exact source for the requested symbol:

```json
{"id":"...","source":"...","line":1,"end_line":10,"byte_offset":0,"byte_length":200,"signature":"...","kind":"function","language":"python"}
```

`search` returns ranked symbols:

```json
[{"id":"...","name":"...","kind":"function","score":20.0,"signature":"...","summary":""}]
```

`grep` returns matching lines with context:

```json
[{"file":"...","line":42,"match":"...","context_before":[],"context_after":[]}]
```

## Selection Rules

- Know the file, want symbols: `loci outline <path> --file <rel>`.
- Know the symbol name: `loci search <name> --repo <path>`, then `loci get`.
- Know the symbol ID from outline: `loci get` directly.
- Hunting string literals or error text: `loci grep`.
- Need exact surrounding context: `loci get --context N` or `loci file`.
- Non-code file such as JSON, YAML, TOML, or Markdown: `loci file` or a normal targeted read.

## Summaries

After indexing a repo you expect to keep using, run `loci summarize <path>` to report symbols without summaries. If it returns an empty array, continue with `outline`, `search`, and `get`.

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
