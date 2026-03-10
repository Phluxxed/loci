# loci: file, grep, batch get — Design

**Goal:** Add three agent-workflow capabilities missing from loci: file content retrieval, full-text search, and batch symbol retrieval.

**Architecture:** All three operate against the existing sources cache (`_sources_dir`). No new index structures required. Two new subcommands (`file`, `grep`) and one extension to the existing `get` command.

**Tech Stack:** Python stdlib only (`re`, `pathlib`). No new dependencies.

---

## Feature 1: `loci file`

**Command:** `loci file <file_path> --repo <repo> [--start N] [--end N]`

Reads the cached copy of a source file (same `sources/` dir used by `loci get`). Returns the full file or a line-range slice.

**Output:**
```json
{
  "file": "src/foo.py",
  "content": "...",
  "total_lines": 120,
  "start_line": 1,
  "end_line": 120
}
```

- `--start` and `--end` are 1-indexed, inclusive. Omitting either gives open-ended slices.
- Error if repo not indexed or file not in cache: JSON error to stderr, exit 1.
- Logs retrieval to session log: `symbol_bytes` = bytes returned, `file_bytes` = total file size.

---

## Feature 2: `loci grep`

**Command:** `loci grep <pattern> --repo <repo>`

Walks the sources dir, applies `re.search(pattern, line)` per line. Returns all matches with 2 lines of context before and after.

**Output:**
```json
[
  {
    "file": "src/foo.py",
    "line": 42,
    "match": "  raise ValueError(msg)",
    "context_before": ["  if not msg:", "    msg = default"],
    "context_after": ["", "def other_func():"]
  }
]
```

- Pattern is a Python regex.
- Results sorted by file path then line number.
- Returns empty array if no matches (not an error).
- Error if repo not indexed: JSON error to stderr, exit 1.

---

## Feature 3: Batch `loci get`

**Command:** `loci get ID1 [ID2 ...] --repo <repo>`

Extends the existing `get` command to accept one or more symbol IDs (`nargs='+'`).

- **Single ID**: returns same single-object format as today (backwards compatible).
- **Multiple IDs**: returns a JSON array of result objects, in the order requested.
- Missing symbols included as `{"id": "...", "error": "Symbol not found"}` rather than aborting the whole batch.
- Stats logging applies to each symbol individually.

---

## Error Handling

All errors follow existing loci convention: JSON to stderr, non-zero exit code.

## Testing

TDD throughout. Each feature gets tests before implementation:
- `loci file`: full file, sliced, missing file, out-of-range lines
- `loci grep`: match found, no match, invalid regex, unindexed repo
- `loci get` batch: two valid IDs, mixed valid/invalid, single ID still works
