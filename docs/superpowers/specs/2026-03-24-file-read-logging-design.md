# File Read Logging — Design Spec

**Date:** 2026-03-24
**Status:** Approved

## Problem

loci tracks `get`, `search`, `outline`, and `miss` events but has no visibility into Claude's `Read` tool calls. When an agent reads a whole source file instead of using `loci get`, loci can't detect it — meaning extraction gaps, ranking failures, and interface cascade fallbacks are invisible to `analyze`.

## Goal

Log direct file reads for files in indexed repos so `analyze` can surface which files agents fall back to reading whole, indicating where loci is failing them.

## Out of Scope (v1)

- Cascade detection (type/interface reads clustering after function fetches) — requires log data to validate first
- Logging reads of non-source files (config, docs, markdown)

---

## Components

### 1. `IndexStore.log_file_read(file_path: str) -> None`

New method alongside existing `log_*` methods in `src/loci/storage/index_store.py`.

**Behaviour:**
- Resolve `file_path` to absolute path via `Path.resolve()` — this handles symlinks correctly by operating on the real path
- Check extension is in `EXTENSION_MAP` (imported from `loci.parser.languages`) — return silently if not a source file
- Iterate `list_repos()` — each entry is a dict with a `"path"` string key (always absolute) — and find the first repo where `resolved_file.is_relative_to(Path(repo["path"]))`. Return silently if none match.
- Compute `rel_path = str(resolved_file.relative_to(Path(repo["path"])))`
- Write to `session.jsonl`:

```json
{"ts": 1234567890.0, "event": "file_read", "file_path": "/abs/path/to/file.py", "rel_path": "src/foo.py", "repo": "/repo/root"}
```

**Error handling:** Any exception is swallowed — this must never raise. Called from a hook that cannot fail.

---

### 2. `loci log-read` CLI Subcommand

Purpose-built hook handler in `src/loci/cli.py`. Reads the Claude Code hook JSON payload from stdin.

```
loci log-read
```

- Reads stdin, parses JSON, extracts `.tool_input.file_path`
- Calls `store.log_file_read(file_path)`
- Always exits 0, including on any error (malformed JSON, missing field, store error)
- Produces no stdout output (silent by design)

Claude Code hooks deliver tool input as JSON on stdin:
```json
{"hook_event_name": "PostToolUse", "tool_name": "Read", "tool_input": {"file_path": "/abs/path"}, ...}
```

---

### 3. Claude Code Hook

Added to `~/.claude/settings.json` under `hooks.PostToolUse`:

```json
{
  "matcher": "Read",
  "hooks": [{
    "type": "command",
    "command": "loci log-read"
  }]
}
```

Fires after every `Read` tool call. `log_file_read` filters to indexed source files, so non-source reads are silently ignored.

---

### 4. `analyze` Finding: `file_read_fallback`

New finding type in `IndexStore.analyze()`. The existing event collection loop (which currently accumulates `get`, `search`, and `miss` events) must be extended to also collect `file_read` events into a `file_reads` list. `file_read` events are subject to the same `repo_filter` as all other events.

**Detection logic:**
- Collect all `file_read` events from the log window
- Group by `file_path`, count occurrences per file
- Files read more than once are considered fallbacks (single reads may be intentional)
- Fire finding if total fallback reads ≥ 5 or fallback file count ≥ 3

**Output:**

```json
{
  "type": "file_read_fallback",
  "severity": "medium",
  "data": {
    "total_fallback_reads": 12,
    "fallback_file_count": 4,
    "top_files": [
      {"file": "src/loci/storage/index_store.py", "repo": "/home/brummerv/loci", "reads": 5},
      {"file": "src/loci/cli.py", "repo": "/home/brummerv/loci", "reads": 4}
    ]
  },
  "suggestion": "4 source files read whole 12 times — agents fell back to raw reads. Check extraction and search ranking for these files."
}
```

**Pretty output** (`loci analyze --pretty`): rendered under findings with top files listed.

---

## Data Flow

```
Claude Read tool
    → PostToolUse hook
    → loci log-read  (reads stdin JSON, extracts .tool_input.file_path)
    → IndexStore.log_file_read(file_path)
    → filter: source file? in indexed repo?
    → append file_read event to session.jsonl

loci analyze
    → read session.jsonl
    → collect file_read events
    → group by file, count reads > 1
    → emit file_read_fallback finding if threshold met
```

---

## Thresholds

| Trigger | Value | Rationale |
|---------|-------|-----------|
| Min reads per file to count as fallback | > 1 | Single reads may be intentional (checking a config section, one-off inspection) |
| Min total fallback reads to fire finding | ≥ 5 | Counts all reads for qualifying files (e.g. a file read 5 times = 5 total). Catches a single heavily-read file. |
| Min fallback file count to fire finding | ≥ 3 | Catches many lightly-read files (e.g. 3 files × 2 reads each = 6 total) |

The two thresholds are independent OR conditions: either a single file is read many times, or many files are each read more than once. Both patterns indicate systematic loci failure.

---

## Testing

- Unit test `log_file_read`: non-source file → no log entry; file not in indexed repo → no log entry; valid source file → correct entry written
- Unit test `loci log-read` CLI: malformed stdin → exits 0; empty stdin → exits 0; stdin missing `tool_input.file_path` → exits 0; valid payload → log entry written
- Unit test `analyze` finding: synthetic log with file_read events → finding fires at threshold; below threshold → no finding
- Manual: install hook, do a session with some `Read` calls on indexed source files, run `loci analyze --pretty` and confirm fallback files appear
