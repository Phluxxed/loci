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
- Resolve `file_path` to absolute path
- Check extension is in `EXTENSION_MAP` — return silently if not a source file
- Iterate `list_repos()` to find which indexed repo is a parent of `file_path`
- Return silently if no matching repo found
- Write to `session.jsonl`:

```json
{"ts": 1234567890.0, "event": "file_read", "file_path": "/abs/path/to/file.py", "rel_path": "src/foo.py", "repo": "/repo/root"}
```

**Error handling:** Any exception is swallowed — this must never raise. Called from a hook that cannot fail.

---

### 2. `loci log-read <path>` CLI Subcommand

Thin wrapper in `src/loci/cli.py`.

```
loci log-read <file_path>
```

- Calls `store.log_file_read(args.file_path)`
- Always exits 0, including on error
- Produces no stdout output (silent by design)

---

### 3. Claude Code Hook

Added to `~/.claude/settings.json` under `hooks.PostToolUse`:

```json
{
  "matcher": "Read",
  "hooks": [{
    "type": "command",
    "command": "loci log-read \"$CLAUDE_TOOL_INPUT_FILE_PATH\""
  }]
}
```

Fires after every `Read` tool call. `log_file_read` filters to indexed source files, so non-source reads are silently ignored.

---

### 4. `analyze` Finding: `file_read_fallback`

New finding type in `IndexStore.analyze()`.

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
    → loci log-read <path>
    → IndexStore.log_file_read()
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
| Min reads per file to count as fallback | > 1 | Single reads may be intentional (e.g. checking a config section) |
| Min total fallback reads to fire finding | ≥ 5 | Suppresses noise from occasional reads |
| Min fallback file count to fire finding | ≥ 3 | Either condition triggers the finding |

---

## Testing

- Unit test `log_file_read`: non-source file → no log entry; file not in indexed repo → no log entry; valid source file → correct entry written
- Unit test `analyze` finding: synthetic log with file_read events → finding fires at threshold; below threshold → no finding
- Manual: install hook, do a session with some `Read` calls, run `loci analyze --pretty` and confirm fallback files appear
