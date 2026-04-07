---
name: loci
description: Use at the start of any non-trivial codebase task to navigate symbols efficiently. loci is a code symbol indexer that replaces Read/Grep/Explore for indexed repos.
---

# loci — Agent Workflow Guide

loci is your primary tool for codebase navigation. It indexes symbols with byte-precise offsets so you fetch exactly what you need instead of reading entire files.

## Core Workflow

```
loci index <path>                    # index once (or --incremental after edits)
loci outline <path>                  # get ALL symbols + IDs in one call
loci get ID1 ID2 ...  --repo <path>  # fetch specific symbol source by ID
```

`outline → get` is the key flow. `outline` gives you every symbol ID in one shot — use those IDs to call `get`. This replaces 15–20 iterative Read/Grep calls.

## All Commands

| Command | Use when |
|---------|----------|
| `loci index <path> [--incremental]` | Starting work, or after edits |
| `loci outline <path> [--file <rel>]` | Getting the full symbol map |
| `loci get ID1 [ID2 ...] --repo <path> [--context N]` | Fetching symbol source |
| `loci search <query> --repo <path> [--kind K] [--lang L]` | Finding symbols by name/concept |
| `loci file <rel_path> --repo <path> [--start N] [--end N]` | Reading non-symbol files (config, docs) |
| `loci grep <pattern> --repo <path>` | Hunting string literals, error messages, config keys |
| `loci verify <path>` | Checking index integrity + content drift |
| `loci summarize <path>` | Check for unsummarized symbols (run after every index) |
| `loci summarize <path> --apply <file>` | Write generated summaries back (used by Summaries Workflow) |
| `loci stats [--repo <path>] [--pretty]` | Checking token savings |
| `loci list` | Listing indexed repos |
| `loci invalidate <path>` | Clearing stale cache |

## Symbol Fields

Every symbol has: `id`, `name`, `qualified_name`, `kind`, `language`, `file_path`, `byte_offset`, `byte_length`, `line`, `end_line`, `signature`, `docstring`, `summary`, `keywords`, `decorators`, `content_hash`

## Output Schemas

**outline** (grouped by file):
```json
[{"file": "src/foo.py", "symbols": [{"id": "...", "name": "...", "kind": "...", "line": 1, "end_line": 10, "signature": "...", "summary": ""}]}]
```

**get** (single or array for batch):
```json
{"id": "...", "source": "...", "line": 1, "end_line": 10, "byte_offset": 0, "byte_length": 200, "signature": "...", "kind": "function", "language": "python"}
```

**search**:
```json
[{"id": "...", "name": "...", "kind": "...", "score": 20.0, "signature": "...", "summary": ""}]
```

**grep**:
```json
[{"file": "...", "line": 42, "match": "...", "context_before": [...], "context_after": [...]}]
```

## When to Use What

- **Know the file, want all symbols** → `outline --file <rel>`
- **Know the symbol name** → `search <name>` then `get`
- **Know the symbol ID** (from outline) → `get` directly
- **Hunting a string/regex** → `grep`
- **Need surrounding file context** → `get --context N` or `file`
- **Non-code file** (JSON, YAML, Markdown) → `file`

## Summaries Workflow (mandatory after index)

After every `loci index`, run:

```bash
loci summarize <path>
```

If the output is a non-empty JSON array, summarization is **required** — not optional:

1. Split the array into chunks of 200 symbols
2. For each chunk: dispatch a Haiku subagent using `summarizer-prompt.md` in this skills directory, passing the chunk as inline JSON. Use `Agent` tool with `subagent_type=general-purpose`, `model=haiku` (model ID: `claude-haiku-4-5-20251001`)
3. Strip any markdown fences from the subagent response (` ```json ` / ` ``` `) before parsing. If still malformed after stripping: retry once with the reminder "Return only a raw JSON object, no markdown". If still malformed: skip the chunk and continue
4. Merge all chunk results into a single dict
5. Write to `/tmp/loci-summaries-<pid>.json`
6. Run: `loci summarize <path> --apply /tmp/loci-summaries-<pid>.json`
7. Delete the temp file

If `loci summarize` returns an empty array (all symbols already summarized), skip all the above steps.

## Self-Improvement with analyze

Run `loci analyze` periodically or when asked to improve the tool.

```
loci analyze [--repo <path>] [--since DAYS]   # JSON output (default)
loci analyze --pretty                          # human-readable
```

Read the `findings[]` array; act on each `suggestion` directly:

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

## loci vs Other Tools

| Situation | Use |
|-----------|-----|
| Indexed repo, exploring symbols | loci (always) |
| Non-indexed repo, quick 1-2 file lookup | Read/Grep directly |
| Non-indexed repo, broad exploration | Explore agent |
| Repo you'll work in for a while | Index it, then use loci |
