# loci Telemetry & Self-Healing Audit — Design Spec

**Date:** 2026-03-11
**Status:** Approved

## Purpose

Instrument loci so I (the agent) can periodically run `loci analyze` and get actionable findings that tell me exactly what to fix in the parser, search scorer, or index configuration. The loop: use loci → log events → analyze → findings → fix code → loci improves.

---

## Data Model

Three event types written to the existing `~/.codeindex/session.jsonl`.

### `get` event (enriched from current)
```json
{
  "ts": 1234567890,
  "event": "get",
  "symbol_id": "src/foo.py::bar",
  "symbol_bytes": 1200,
  "file_bytes": 8000,
  "repo": "/path/to/repo",
  "kind": "function",
  "language": "python",
  "search_id": "abc123",
  "search_rank": 2
}
```
- `kind` + `language`: pulled from the symbol at log time
- `search_id`: UUID of the preceding search (from temp file), null if no recent search
- `search_rank`: 0-based rank of this symbol in search results, null if symbol wasn't in results

### `search` event (new)
```json
{
  "ts": 1234567890,
  "event": "search",
  "search_id": "abc123",
  "query": "get_user",
  "repo": "/path/to/repo",
  "result_ids": ["src/users.py::get_user", "src/auth.py::get_user_by_id"],
  "result_count": 5
}
```

### `miss` event (new)
```json
{"ts": 1234567890, "event": "miss", "miss_type": "search_empty", "query": "handle_error", "repo": "..."}
{"ts": 1234567890, "event": "miss", "miss_type": "get_not_found", "symbol_id": "src/foo.py::missing", "repo": "..."}
```

### Backwards compatibility
Old entries (no `event` field) are treated as `event: "get"` with missing fields defaulting to null. No migration required.

---

## Search→Get Correlation

When `loci search` runs, it writes:
```
~/.codeindex/last_search.json
{"search_id": "abc123", "ts": 1234567890, "query": "get_user", "result_ids": ["id1", "id2"]}
```

When `loci get` runs:
- File exists and age < 5 minutes → read `search_id`, compute `search_rank` (0-based index in `result_ids`, or null if symbol not present)
- Stale or missing → `search_id: null`, `search_rank: null`

File is overwritten on every search. TTL handles cleanup passively.

**Three ranking signals:**
- `search_rank: 0` — top result fetched, ranking correct
- `search_rank: 3+` — right symbol but buried, ranking needs work
- `search_rank: null` with non-null `search_id` — fetched symbol not in results at all, serious miss

---

## `loci analyze` Command

```
loci analyze [--repo PATH] [--since DAYS] [--pretty]
```

- Default `--since 30` (last 30 days of log entries)
- Default output: JSON (machine-readable for agent consumption)
- `--pretty`: human-readable table format

### Output schema
```json
{
  "period": {"from": "2026-02-09T00:00:00", "to": "2026-03-11T12:00:00"},
  "summary": {
    "total_gets": 87,
    "total_searches": 23,
    "miss_rate": 0.13,
    "correlated_pct": 0.61
  },
  "findings": [
    {
      "type": "search_miss",
      "severity": "high",
      "data": {"queries": ["handle_error", "BaseModel"], "count": 5},
      "suggestion": "These queries return 0 results. Check keyword extraction handles these patterns."
    }
  ]
}
```

### Findings

| Type | Triggers | Severity | Suggestion targets |
|---|---|---|---|
| `search_miss` | queries with 0 results | high | keyword extraction, synonyms |
| `search_blind_spot` | fetched symbol not in results despite preceding search | high | missing symbol classes in search |
| `search_ranking_poor` | fetched rank ≥3 in >20% of correlated searches | medium | scoring weight adjustment |
| `poor_extraction` | language avg savings ratio <50% | medium | extractor context size per symbol |
| `kind_dead_weight` | kind has >50 indexed, 0 fetched | low | drop kind from index or cut weight |
| `refetch_hotspot` | same symbol fetched 3+ times in a session | low | symbol too large for context retention |

Empty `findings` array = tool is working well, no action needed.

---

## Changes Required

### `storage/index_store.py`
- `log_retrieval()` → accepts `kind`, `language`, `search_id`, `search_rank`; writes enriched `get` event
- `log_search()` → new method, writes `search` event + updates `last_search.json`
- `log_miss()` → new method, writes `miss` event
- `get_session_stats()` → unchanged (reads only `get` events for backwards compat)
- `analyze()` → new method, reads all event types and produces findings

### `cli.py`
- `cmd_get` → reads `last_search.json`, passes correlation data to `log_retrieval`
- `cmd_search` → calls `log_search` after results computed
- `cmd_get` on miss → calls `log_miss`
- `cmd_search` on 0 results → calls `log_miss`
- `cmd_analyze` → new command wired to `store.analyze()`
- Argument parser → add `analyze` subcommand

### `~/.codeindex/last_search.json`
- New temp file, written by `loci search`, read by `loci get`
- TTL: 5 minutes
