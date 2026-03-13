# Telemetry & Self-Healing Audit Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Enrich loci's event log with search/miss/kind data and add `loci analyze` to produce actionable findings I can use to improve the tool.

**Architecture:** Enrich `log_retrieval` with `kind`/`language`/search correlation; add `log_search` (writes event + `last_search.json`) and `log_miss`; add `analyze()` to `IndexStore` that reads all event types and emits findings with suggestions.

**Tech Stack:** Python 3.11+, stdlib only (json, time, uuid, pathlib). No new dependencies.

---

## Chunk 1: Enrich the event log + search→get correlation

### Task 1: Enrich `log_retrieval` with kind, language, and search correlation

**Files:**
- Modify: `src/loci/storage/index_store.py:181-190`
- Test: `tests/storage/test_index_store.py`

- [ ] **Step 1: Write failing tests for enriched log entry**

```python
# In tests/storage/test_index_store.py

def test_log_retrieval_includes_kind_and_language(tmp_path):
    store = IndexStore(tmp_path)
    store.log_retrieval(
        "src/foo.py::bar", symbol_bytes=100, file_bytes=1000,
        repo_path="/repo", kind="function", language="python"
    )
    entries = [json.loads(l) for l in (tmp_path / "session.jsonl").read_text().splitlines()]
    assert entries[0]["event"] == "get"
    assert entries[0]["kind"] == "function"
    assert entries[0]["language"] == "python"

def test_log_retrieval_includes_search_correlation(tmp_path):
    store = IndexStore(tmp_path)
    store.log_retrieval(
        "src/foo.py::bar", symbol_bytes=100, file_bytes=1000,
        repo_path="/repo", kind="function", language="python",
        search_id="abc123", search_rank=2
    )
    entry = json.loads((tmp_path / "session.jsonl").read_text().strip())
    assert entry["search_id"] == "abc123"
    assert entry["search_rank"] == 2

def test_log_retrieval_search_correlation_defaults_to_null(tmp_path):
    store = IndexStore(tmp_path)
    store.log_retrieval("src/foo.py::bar", symbol_bytes=100, file_bytes=1000, repo_path="/repo")
    entry = json.loads((tmp_path / "session.jsonl").read_text().strip())
    assert entry["search_id"] is None
    assert entry["search_rank"] is None

def test_log_retrieval_old_stats_aggregation_unaffected(tmp_path):
    """get_session_stats must still work with enriched entries."""
    store = IndexStore(tmp_path)
    store.log_retrieval("src/foo.py::bar", symbol_bytes=100, file_bytes=1000,
                        repo_path="/repo", kind="function", language="python")
    stats = store.get_session_stats()
    assert stats["total_gets"] == 1
    assert stats["symbol_bytes_retrieved"] == 100
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
source .venv/bin/activate && pytest tests/storage/test_index_store.py -k "log_retrieval" -v
```
Expected: FAIL — `log_retrieval` missing `kind`/`language`/`search_id`/`search_rank` params.

- [ ] **Step 3: Update `log_retrieval` signature and entry**

In `src/loci/storage/index_store.py`, replace `log_retrieval`:

```python
def log_retrieval(
    self,
    symbol_id: str,
    symbol_bytes: int,
    file_bytes: int,
    repo_path: str = "",
    kind: Optional[str] = None,
    language: Optional[str] = None,
    search_id: Optional[str] = None,
    search_rank: Optional[int] = None,
) -> None:
    entry = {
        "ts": time.time(),
        "event": "get",
        "symbol_id": symbol_id,
        "symbol_bytes": symbol_bytes,
        "file_bytes": file_bytes,
        "repo": repo_path,
        "kind": kind,
        "language": language,
        "search_id": search_id,
        "search_rank": search_rank,
    }
    with open(self._session_log_path(), "a") as f:
        f.write(json.dumps(entry) + "\n")
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/storage/test_index_store.py -k "log_retrieval" -v
```
Expected: all 4 PASS.

- [ ] **Step 5: Commit**

```bash
git add src/loci/storage/index_store.py tests/storage/test_index_store.py
git commit -m "feat: enrich log_retrieval with kind, language, search correlation"
```

---

### Task 2: Add `log_search` and `log_miss` methods

`log_search` writes the search event AND updates `last_search.json` atomically — callers never call `_write_last_search` directly.

**Files:**
- Modify: `src/loci/storage/index_store.py`
- Test: `tests/storage/test_index_store.py`

- [ ] **Step 1: Write failing tests**

```python
def test_log_search_writes_event_and_last_search_file(tmp_path):
    store = IndexStore(tmp_path)
    store.log_search("abc123", "get_user", "/repo", ["src/users.py::get_user", "src/auth.py::get_user_by_id"])
    # Check session.jsonl
    entry = json.loads((tmp_path / "session.jsonl").read_text().strip())
    assert entry["event"] == "search"
    assert entry["search_id"] == "abc123"
    assert entry["query"] == "get_user"
    assert entry["repo"] == "/repo"
    assert entry["result_ids"] == ["src/users.py::get_user", "src/auth.py::get_user_by_id"]
    assert entry["result_count"] == 2
    # Check last_search.json was also written
    last = json.loads((tmp_path / "last_search.json").read_text())
    assert last["search_id"] == "abc123"
    assert last["result_ids"] == ["src/users.py::get_user", "src/auth.py::get_user_by_id"]

def test_log_miss_search_empty(tmp_path):
    store = IndexStore(tmp_path)
    store.log_miss("search_empty", repo_path="/repo", query="handle_error")
    entry = json.loads((tmp_path / "session.jsonl").read_text().strip())
    assert entry["event"] == "miss"
    assert entry["miss_type"] == "search_empty"
    assert entry["query"] == "handle_error"

def test_log_miss_get_not_found(tmp_path):
    store = IndexStore(tmp_path)
    store.log_miss("get_not_found", repo_path="/repo", symbol_id="src/foo.py::missing")
    entry = json.loads((tmp_path / "session.jsonl").read_text().strip())
    assert entry["event"] == "miss"
    assert entry["miss_type"] == "get_not_found"
    assert entry["symbol_id"] == "src/foo.py::missing"
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/storage/test_index_store.py -k "log_search or log_miss" -v
```
Expected: FAIL — methods don't exist.

- [ ] **Step 3: Add `log_search` and `log_miss` to IndexStore**

```python
def log_search(
    self,
    search_id: str,
    query: str,
    repo_path: str,
    result_ids: list[str],
    result_count: Optional[int] = None,
) -> None:
    # result_count is the true total from search; result_ids may be top-N subset
    entry = {
        "ts": time.time(),
        "event": "search",
        "search_id": search_id,
        "query": query,
        "repo": repo_path,
        "result_ids": result_ids,
        "result_count": result_count if result_count is not None else len(result_ids),
    }
    with open(self._session_log_path(), "a") as f:
        f.write(json.dumps(entry) + "\n")
    self._write_last_search(search_id, query, result_ids)

def log_miss(
    self,
    miss_type: str,
    repo_path: str = "",
    query: Optional[str] = None,
    symbol_id: Optional[str] = None,
) -> None:
    entry = {
        "ts": time.time(),
        "event": "miss",
        "miss_type": miss_type,
        "repo": repo_path,
        "query": query,
        "symbol_id": symbol_id,
    }
    with open(self._session_log_path(), "a") as f:
        f.write(json.dumps(entry) + "\n")
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/storage/test_index_store.py -k "log_search or log_miss" -v
```
Expected: all 3 PASS.

- [ ] **Step 5: Commit**

```bash
git add src/loci/storage/index_store.py tests/storage/test_index_store.py
git commit -m "feat: add log_search (writes event + last_search.json) and log_miss"
```

---

### Task 3: Search→get correlation helpers

**Files:**
- Modify: `src/loci/storage/index_store.py`
- Test: `tests/storage/test_index_store.py`

- [ ] **Step 1: Write failing tests**

```python
import time as time_module

def test_last_search_path(tmp_path):
    store = IndexStore(tmp_path)
    assert store._last_search_path() == tmp_path / "last_search.json"

def test_write_and_read_last_search(tmp_path):
    store = IndexStore(tmp_path)
    store._write_last_search("abc123", "get_user", ["id1", "id2"])
    data = store._read_last_search()
    assert data is not None
    assert data["search_id"] == "abc123"
    assert data["query"] == "get_user"
    assert data["result_ids"] == ["id1", "id2"]

def test_read_last_search_returns_none_when_missing(tmp_path):
    store = IndexStore(tmp_path)
    assert store._read_last_search() is None

def test_read_last_search_returns_none_when_stale(tmp_path):
    store = IndexStore(tmp_path)
    store._write_last_search("abc123", "q", ["id1"])
    stale_ts = time_module.time() - 400
    data = json.loads((tmp_path / "last_search.json").read_text())
    data["ts"] = stale_ts
    (tmp_path / "last_search.json").write_text(json.dumps(data))
    assert store._read_last_search() is None

def test_resolve_search_correlation_found(tmp_path):
    store = IndexStore(tmp_path)
    store._write_last_search("abc123", "get_user", ["id1", "id2", "id3"])
    search_id, rank = store.resolve_search_correlation("id2")
    assert search_id == "abc123"
    assert rank == 1

def test_resolve_search_correlation_not_in_results(tmp_path):
    store = IndexStore(tmp_path)
    store._write_last_search("abc123", "get_user", ["id1", "id2"])
    search_id, rank = store.resolve_search_correlation("id_other")
    assert search_id == "abc123"
    assert rank is None  # preceded by a search but symbol not in results

def test_resolve_search_correlation_no_recent_search(tmp_path):
    store = IndexStore(tmp_path)
    search_id, rank = store.resolve_search_correlation("id1")
    assert search_id is None
    assert rank is None
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/storage/test_index_store.py -k "last_search or resolve_search" -v
```
Expected: FAIL — methods don't exist.

- [ ] **Step 3: Add correlation helpers to IndexStore**

```python
LAST_SEARCH_TTL = 300  # 5 minutes

def _last_search_path(self) -> Path:
    return self.base_dir / "last_search.json"

def _write_last_search(self, search_id: str, query: str, result_ids: list[str]) -> None:
    data = {"search_id": search_id, "ts": time.time(), "query": query, "result_ids": result_ids}
    self._last_search_path().write_text(json.dumps(data))

def _read_last_search(self) -> Optional[dict]:
    p = self._last_search_path()
    if not p.exists():
        return None
    data = json.loads(p.read_text())
    if time.time() - data["ts"] > LAST_SEARCH_TTL:
        return None
    return data

def resolve_search_correlation(self, symbol_id: str) -> tuple[Optional[str], Optional[int]]:
    """Return (search_id, rank) for symbol_id against last search, or (None, None)."""
    data = self._read_last_search()
    if data is None:
        return None, None
    search_id = data["search_id"]
    result_ids = data["result_ids"]
    try:
        rank = result_ids.index(symbol_id)
    except ValueError:
        rank = None
    return search_id, rank
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/storage/test_index_store.py -k "last_search or resolve_search" -v
```
Expected: all 7 PASS.

- [ ] **Step 5: Commit**

```bash
git add src/loci/storage/index_store.py tests/storage/test_index_store.py
git commit -m "feat: search→get correlation helpers (_write/read_last_search, resolve_search_correlation)"
```

---

### Task 4: Wire logging into `cmd_search` and `cmd_get`

Key rule: `log_search` is only called when results > 0 (it writes `last_search.json`). Empty searches call `log_miss` only — no `last_search.json` write, preventing false blind_spot signals.

**Files:**
- Modify: `src/loci/cli.py:126-184`
- Test: `tests/test_cli.py`

- [ ] **Step 1: Write failing tests**

Before adding tests, check `tests/test_cli.py` for the existing `run_loci`, `_index_repo`, and fixture patterns — use what's already there rather than reinventing helpers.

```python
def test_cmd_search_logs_search_event(tmp_path, monkeypatch):
    """search with results writes a search event to session.jsonl."""
    monkeypatch.setenv("LOCI_BASE_DIR", str(tmp_path / "idx"))
    repo = tmp_path / "repo"
    _index_repo(repo)
    run_loci(["search", "--repo", str(repo), "some_function"])
    log_path = tmp_path / "idx" / "session.jsonl"
    entries = [json.loads(l) for l in log_path.read_text().splitlines() if l.strip()]
    search_events = [e for e in entries if e.get("event") == "search"]
    assert len(search_events) == 1
    assert search_events[0]["query"] == "some_function"
    assert "search_id" in search_events[0]
    assert "result_ids" in search_events[0]

def test_cmd_search_logs_miss_on_empty_results(tmp_path, monkeypatch):
    """search with 0 results writes a miss event, NOT a search event."""
    monkeypatch.setenv("LOCI_BASE_DIR", str(tmp_path / "idx"))
    repo = tmp_path / "repo"
    _index_repo(repo)
    run_loci(["search", "--repo", str(repo), "zzz_nonexistent_xyz"])
    log_path = tmp_path / "idx" / "session.jsonl"
    entries = [json.loads(l) for l in log_path.read_text().splitlines() if l.strip()]
    assert any(e.get("event") == "miss" and e["miss_type"] == "search_empty" for e in entries)
    assert all(e.get("event") != "search" for e in entries)

def test_cmd_search_empty_does_not_write_last_search(tmp_path, monkeypatch):
    """Empty search result must not write last_search.json (prevents false blind_spot)."""
    monkeypatch.setenv("LOCI_BASE_DIR", str(tmp_path / "idx"))
    repo = tmp_path / "repo"
    _index_repo(repo)
    run_loci(["search", "--repo", str(repo), "zzz_nonexistent_xyz"])
    assert not (tmp_path / "idx" / "last_search.json").exists()

def test_cmd_get_logs_kind_and_language(tmp_path, monkeypatch):
    """get command enriches the log entry with kind and language."""
    monkeypatch.setenv("LOCI_BASE_DIR", str(tmp_path / "idx"))
    repo = tmp_path / "repo"
    symbol_id = _index_repo_and_get_symbol(repo)
    run_loci(["get", "--repo", str(repo), symbol_id])
    log_path = tmp_path / "idx" / "session.jsonl"
    entries = [json.loads(l) for l in log_path.read_text().splitlines() if l.strip()]
    get_events = [e for e in entries if e.get("event") == "get"]
    assert len(get_events) == 1
    assert get_events[0]["kind"] is not None
    assert get_events[0]["language"] is not None

def test_cmd_get_logs_miss_on_not_found(tmp_path, monkeypatch):
    """get on a missing symbol writes a miss event."""
    monkeypatch.setenv("LOCI_BASE_DIR", str(tmp_path / "idx"))
    repo = tmp_path / "repo"
    _index_repo(repo)
    run_loci(["get", "--repo", str(repo), "src/foo.py::nonexistent"], expect_fail=True)
    log_path = tmp_path / "idx" / "session.jsonl"
    entries = [json.loads(l) for l in log_path.read_text().splitlines() if l.strip()]
    assert any(e.get("event") == "miss" and e["miss_type"] == "get_not_found" for e in entries)

def test_cmd_get_records_search_correlation(tmp_path, monkeypatch):
    """get after search records search_id on the get event."""
    monkeypatch.setenv("LOCI_BASE_DIR", str(tmp_path / "idx"))
    repo = tmp_path / "repo"
    symbol_id = _index_repo_and_get_symbol(repo)
    run_loci(["search", "--repo", str(repo), "some_function"])
    run_loci(["get", "--repo", str(repo), symbol_id])
    log_path = tmp_path / "idx" / "session.jsonl"
    entries = [json.loads(l) for l in log_path.read_text().splitlines() if l.strip()]
    get_events = [e for e in entries if e.get("event") == "get"]
    assert len(get_events) == 1
    assert get_events[0]["search_id"] is not None
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_cli.py -k "logs_search or logs_miss or logs_kind or logs_search_correlation or empty_does_not_write" -v
```
Expected: FAIL.

- [ ] **Step 3: Update `cmd_search` in `cli.py`**

```python
import uuid

def cmd_search(args: argparse.Namespace) -> int:
    repo_path = Path(args.repo).resolve()
    store = _get_store()
    results = store.search(
        repo_path,
        args.query,
        kind=args.kind,
        lang=args.lang,
        limit=args.limit,
    )
    if results:
        search_id = str(uuid.uuid4())
        result_ids = [r["id"] for r in results]
        store.log_search(search_id, args.query, str(repo_path), result_ids)
        # log_search also writes last_search.json for get correlation
    else:
        store.log_miss("search_empty", repo_path=str(repo_path), query=args.query)
    print(json.dumps(results))
    return 0
```

- [ ] **Step 4: Update `cmd_get` in `cli.py`**

Replace the `_fetch` inner function body:

```python
    def _fetch(symbol_id: str) -> dict:
        if index is None:
            return {"id": symbol_id, "error": "Repo not indexed"}
        meta = next((s for s in index["symbols"] if s["id"] == symbol_id), None)
        if meta is None:
            store.log_miss("get_not_found", repo_path=str(repo_path), symbol_id=symbol_id)
            return {"id": symbol_id, "error": f"Symbol not found: {symbol_id}"}
        content = store.get_symbol_content(repo_path, symbol_id)
        if content is None:
            store.log_miss("get_not_found", repo_path=str(repo_path), symbol_id=symbol_id)
            return {"id": symbol_id, "error": f"Symbol not found: {symbol_id}"}
        symbol_bytes = len(content.encode("utf-8"))
        file_bytes = store.get_symbol_file_size(repo_path, symbol_id)
        if file_bytes is not None:
            search_id, search_rank = store.resolve_search_correlation(symbol_id)
            store.log_retrieval(
                symbol_id, symbol_bytes, file_bytes,
                repo_path=str(repo_path),
                kind=meta.get("kind"),
                language=meta.get("language"),
                search_id=search_id,
                search_rank=search_rank,
            )
        result: dict = {
            "id": symbol_id,
            "source": content,
            **{k: meta.get(k) for k in ("byte_offset", "byte_length", "line", "end_line", "signature", "kind", "language")},
        }
        if meta.get("decorators"):
            result["decorators"] = meta["decorators"]
        if context_lines > 0:
            ctx = store.get_symbol_context(repo_path, symbol_id, context_lines)
            if ctx:
                result["context_before"] = ctx["context_before"]
                result["context_after"] = ctx["context_after"]
        return result
```

- [ ] **Step 5: Run all tests**

```bash
pytest tests/ -v
```
Expected: all passing (117 + new tests).

- [ ] **Step 6: Commit**

```bash
git add src/loci/cli.py tests/test_cli.py
git commit -m "feat: wire search/miss/correlation logging into cmd_search and cmd_get"
```

---

## Chunk 2: `loci analyze` command

### Task 5: `IndexStore.analyze()` — findings engine

Summary fields use floats (0.0–1.0) for `miss_rate` and `correlated_pct` — matching the spec schema contract for agent consumption.

**Files:**
- Modify: `src/loci/storage/index_store.py`
- Test: `tests/storage/test_index_store.py`

- [ ] **Step 1: Write failing tests for each finding type**

```python
import time

def _write_log(path, entries):
    (path / "session.jsonl").write_text("\n".join(json.dumps(e) for e in entries) + "\n")

def test_analyze_search_miss_finding(tmp_path):
    store = IndexStore(tmp_path)
    _write_log(tmp_path, [
        {"ts": time.time(), "event": "miss", "miss_type": "search_empty",
         "query": "handle_error", "repo": "/r"},
        {"ts": time.time(), "event": "miss", "miss_type": "search_empty",
         "query": "handle_error", "repo": "/r"},
        {"ts": time.time(), "event": "miss", "miss_type": "search_empty",
         "query": "BaseModel", "repo": "/r"},
    ])
    result = store.analyze()
    finding = next(f for f in result["findings"] if f["type"] == "search_miss")
    assert set(finding["data"]["queries"]) == {"handle_error", "BaseModel"}
    assert finding["severity"] == "high"
    assert "suggestion" in finding

def test_analyze_search_blind_spot_finding(tmp_path):
    store = IndexStore(tmp_path)
    _write_log(tmp_path, [
        {"ts": time.time(), "event": "get", "symbol_id": "c", "symbol_bytes": 100,
         "file_bytes": 1000, "repo": "/r", "kind": "function", "language": "python",
         "search_id": "s1", "search_rank": None},
        {"ts": time.time(), "event": "get", "symbol_id": "d", "symbol_bytes": 100,
         "file_bytes": 1000, "repo": "/r", "kind": "function", "language": "python",
         "search_id": "s1", "search_rank": None},
        {"ts": time.time(), "event": "get", "symbol_id": "e", "symbol_bytes": 100,
         "file_bytes": 1000, "repo": "/r", "kind": "function", "language": "python",
         "search_id": "s1", "search_rank": None},
    ])
    result = store.analyze()
    finding = next((f for f in result["findings"] if f["type"] == "search_blind_spot"), None)
    assert finding is not None
    assert finding["severity"] == "high"

def test_analyze_search_ranking_poor_finding(tmp_path):
    store = IndexStore(tmp_path)
    entries = []
    for i in range(5):
        entries.append({"ts": time.time(), "event": "get", "symbol_id": f"s{i}",
                        "symbol_bytes": 100, "file_bytes": 1000, "repo": "/r",
                        "kind": "function", "language": "python",
                        "search_id": "abc", "search_rank": 4})
    _write_log(tmp_path, entries)
    result = store.analyze()
    finding = next((f for f in result["findings"] if f["type"] == "search_ranking_poor"), None)
    assert finding is not None
    assert finding["severity"] == "medium"

def test_analyze_kind_dead_weight_finding(tmp_path):
    """kind_dead_weight triggers when a kind is indexed but never fetched."""
    store = IndexStore(tmp_path)
    repo_path = tmp_path / "fakerepo"
    repo_path.mkdir()
    # Use store's own path helper — avoids replicating internal hashing logic
    index_path = store._index_path(repo_path)
    index_path.parent.mkdir(parents=True, exist_ok=True)
    fake_symbols = [
        {"id": f"src/c.py::CONST_{i}#constant", "name": f"CONST_{i}", "kind": "constant",
         "language": "python", "file_path": "src/c.py", "byte_offset": i * 20, "byte_length": 10,
         "signature": f"CONST_{i} = {i}", "docstring": "", "summary": "", "content_hash": "",
         "decorators": [], "keywords": [], "line": i + 1, "end_line": i + 1}
        for i in range(60)
    ]
    index_path.write_text(json.dumps({
        "repo_path": str(repo_path), "indexed_at": time.time(), "symbols": fake_symbols
    }))
    # Log only function fetches — no constants
    _write_log(tmp_path, [
        {"ts": time.time(), "event": "get", "symbol_id": "src/foo.py::bar",
         "symbol_bytes": 100, "file_bytes": 1000, "repo": str(repo_path),
         "kind": "function", "language": "python", "search_id": None, "search_rank": None},
    ])
    result = store.analyze()
    finding = next((f for f in result["findings"] if f["type"] == "kind_dead_weight"), None)
    assert finding is not None
    assert finding["data"]["kind"] == "constant"
    assert finding["data"]["indexed_count"] >= 50
    assert finding["data"]["fetched_count"] == 0
    assert finding["severity"] == "low"

def test_analyze_poor_extraction_finding(tmp_path):
    store = IndexStore(tmp_path)
    _write_log(tmp_path, [
        {"ts": time.time(), "event": "get", "symbol_id": "src/foo.rs::bar",
         "symbol_bytes": 800, "file_bytes": 1000, "repo": "/r",
         "kind": "function", "language": "rust",
         "search_id": None, "search_rank": None},
    ] * 5)
    result = store.analyze()
    finding = next((f for f in result["findings"] if f["type"] == "poor_extraction"), None)
    assert finding is not None
    assert finding["data"]["language"] == "rust"
    assert finding["severity"] == "medium"

def test_analyze_refetch_hotspot_finding(tmp_path):
    store = IndexStore(tmp_path)
    _write_log(tmp_path, [
        {"ts": time.time(), "event": "get", "symbol_id": "src/foo.py::bar",
         "symbol_bytes": 100, "file_bytes": 1000, "repo": "/r",
         "kind": "function", "language": "python",
         "search_id": None, "search_rank": None},
    ] * 4)
    result = store.analyze()
    finding = next((f for f in result["findings"] if f["type"] == "refetch_hotspot"), None)
    assert finding is not None
    assert finding["data"]["symbols"][0]["symbol_id"] == "src/foo.py::bar"
    assert finding["data"]["symbols"][0]["fetch_count"] == 4

def test_analyze_summary_fields_are_floats(tmp_path):
    """miss_rate and correlated_pct are floats 0.0–1.0 per spec schema."""
    store = IndexStore(tmp_path)
    _write_log(tmp_path, [
        {"ts": time.time(), "event": "get", "symbol_id": "s1",
         "symbol_bytes": 100, "file_bytes": 1000, "repo": "/r",
         "kind": "function", "language": "python", "search_id": "x", "search_rank": 0},
        {"ts": time.time(), "event": "search", "search_id": "x", "query": "foo",
         "repo": "/r", "result_ids": ["s1"], "result_count": 1},
        {"ts": time.time(), "event": "miss", "miss_type": "search_empty",
         "query": "bar", "repo": "/r"},
    ])
    result = store.analyze()
    assert result["summary"]["total_gets"] == 1
    assert result["summary"]["total_searches"] == 1
    assert result["summary"]["total_misses"] == 1
    assert isinstance(result["summary"]["miss_rate"], float)
    assert 0.0 <= result["summary"]["miss_rate"] <= 1.0
    assert isinstance(result["summary"]["correlated_pct"], float)
    assert 0.0 <= result["summary"]["correlated_pct"] <= 1.0
    assert "period" in result
    assert "findings" in result

def test_analyze_empty_log(tmp_path):
    store = IndexStore(tmp_path)
    result = store.analyze()
    assert result["findings"] == []
    assert result["summary"]["total_gets"] == 0

def test_analyze_since_days_filter(tmp_path):
    store = IndexStore(tmp_path)
    old_ts = time.time() - (35 * 86400)
    _write_log(tmp_path, [
        {"ts": old_ts, "event": "miss", "miss_type": "search_empty",
         "query": "old_query", "repo": "/r"},
    ])
    result = store.analyze(since_days=30)
    assert all(f["type"] != "search_miss" for f in result["findings"])
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/storage/test_index_store.py -k "analyze" -v
```
Expected: FAIL — `analyze` method doesn't exist.

- [ ] **Step 3: Implement `analyze()` in `IndexStore`**

Add module-level helper above the class:

```python
def _ts_to_iso(ts: float) -> str:
    from datetime import datetime, timezone
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
```

Add `analyze()` method to `IndexStore`:

```python
def analyze(self, since_days: int = 30, repo_filter: Optional[str] = None) -> dict[str, Any]:
    """Read session log and produce actionable findings."""
    from collections import Counter, defaultdict

    log_path = self._session_log_path()
    cutoff = time.time() - since_days * 86400

    gets: list[dict] = []
    searches: list[dict] = []
    misses: list[dict] = []

    if log_path.exists():
        for line in log_path.read_text().splitlines():
            if not line.strip():
                continue
            entry = json.loads(line)
            if entry.get("ts", 0) < cutoff:
                continue
            if repo_filter and entry.get("repo", "") != repo_filter:
                continue
            event = entry.get("event", "get")  # backwards compat: old entries have no event field
            if event == "get":
                gets.append(entry)
            elif event == "search":
                searches.append(entry)
            elif event == "miss":
                misses.append(entry)

    findings: list[dict] = []

    # --- search_miss: queries returning 0 results ---
    empty_queries = [e["query"] for e in misses
                     if e.get("miss_type") == "search_empty" and e.get("query")]
    if empty_queries:
        counts = Counter(empty_queries)
        findings.append({
            "type": "search_miss",
            "severity": "high",
            "data": {"queries": list(counts.keys()), "count": len(empty_queries)},
            "suggestion": (
                f"{len(counts)} unique queries return 0 results. "
                "Check keyword extraction handles these name patterns."
            ),
        })

    # --- search_blind_spot: fetched symbol not returned by preceding search ---
    # 15% threshold suppresses noise when a few gets happen to precede unrelated searches.
    # Below 15%, individual outliers are more likely than a systemic gap.
    correlated_gets = [g for g in gets if g.get("search_id") is not None]
    blind_spots = [g for g in correlated_gets if g.get("search_rank") is None]
    if correlated_gets and len(blind_spots) / len(correlated_gets) >= 0.15:
        blind_pct = len(blind_spots) / len(correlated_gets)
        findings.append({
            "type": "search_blind_spot",
            "severity": "high",
            "data": {
                "blind_spot_count": len(blind_spots),
                "correlated_gets": len(correlated_gets),
                "blind_pct": round(blind_pct, 3),
            },
            "suggestion": (
                f"{round(blind_pct * 100)}% of gets fetch symbols not returned by "
                "the preceding search. Search is missing entire symbol classes — "
                "check indexing and scoring."
            ),
        })

    # --- search_ranking_poor: fetched symbol ranked ≥3 too often ---
    ranked_gets = [g for g in correlated_gets if g.get("search_rank") is not None]
    poor_ranked = [g for g in ranked_gets if g["search_rank"] >= 3]
    if ranked_gets and len(poor_ranked) / len(ranked_gets) >= 0.20:
        poor_pct = len(poor_ranked) / len(ranked_gets)
        avg_rank = sum(g["search_rank"] for g in ranked_gets) / len(ranked_gets)
        findings.append({
            "type": "search_ranking_poor",
            "severity": "medium",
            "data": {
                "poor_ranked_count": len(poor_ranked),
                "ranked_gets": len(ranked_gets),
                "poor_pct": round(poor_pct, 3),
                "avg_rank": round(avg_rank, 1),
            },
            "suggestion": (
                f"Fetched symbols ranked ≥3 in {round(poor_pct * 100)}% of correlated "
                f"searches (avg rank {avg_rank:.1f}). Adjust scoring weights for "
                "name/keyword matches."
            ),
        })

    # --- kind_dead_weight: kind indexed many times but never fetched ---
    # list_repos() returns list[dict] with "path" key — use that to load each index
    fetched_kinds: set[str] = {g["kind"] for g in gets if g.get("kind")}
    indexed_by_kind: dict[str, int] = Counter()
    for repo_info in self.list_repos():
        index = self.load(Path(repo_info["path"]))
        if index is None:
            continue
        for sym in index.get("symbols", []):
            k = sym.get("kind")
            if k:
                indexed_by_kind[k] += 1
    for kind, count in indexed_by_kind.items():
        if count > 50 and kind not in fetched_kinds:
            findings.append({
                "type": "kind_dead_weight",
                "severity": "low",
                "data": {"kind": kind, "indexed_count": count, "fetched_count": 0},
                "suggestion": (
                    f"'{kind}' symbols are indexed ({count} across all repos) but never "
                    "fetched. Consider excluding from index or lowering search score weight."
                ),
            })

    # --- poor_extraction: language avg savings ratio < 50% ---
    lang_bytes: dict[str, dict[str, int]] = defaultdict(lambda: {"symbol": 0, "file": 0})
    for g in gets:
        lang = g.get("language")
        if lang:
            lang_bytes[lang]["symbol"] += g.get("symbol_bytes", 0)
            lang_bytes[lang]["file"] += g.get("file_bytes", 0)
    for lang, b in lang_bytes.items():
        if b["file"] == 0:
            continue
        ratio = (b["file"] - b["symbol"]) / b["file"]
        if ratio < 0.50:
            findings.append({
                "type": "poor_extraction",
                "severity": "medium",
                "data": {"language": lang, "avg_ratio_pct": round(ratio * 100)},
                "suggestion": (
                    f"{lang} symbols average {round(ratio * 100)}% savings ratio. "
                    "Extractor may be including too much context per symbol."
                ),
            })

    # --- refetch_hotspot: same symbol fetched 3+ times ---
    fetch_counts = Counter(g["symbol_id"] for g in gets if g.get("symbol_id"))
    hotspots = sorted(
        [{"symbol_id": sid, "fetch_count": cnt} for sid, cnt in fetch_counts.items() if cnt >= 3],
        key=lambda x: x["fetch_count"], reverse=True,
    )
    if hotspots:
        findings.append({
            "type": "refetch_hotspot",
            "severity": "low",
            "data": {"symbols": hotspots[:10]},
            "suggestion": (
                f"{len(hotspots)} symbol(s) fetched 3+ times. "
                "They may be too large to stay in context — consider splitting or summarizing."
            ),
        })

    # --- Summary ---
    all_ts = [e["ts"] for e in gets + searches + misses if e.get("ts")]
    period_from = min(all_ts) if all_ts else time.time()
    period_to = max(all_ts) if all_ts else time.time()
    total_events = len(gets) + len(misses)
    miss_rate = len(misses) / total_events if total_events > 0 else 0.0
    correlated_pct = len(correlated_gets) / len(gets) if gets else 0.0

    return {
        "period": {
            "from": _ts_to_iso(period_from),
            "to": _ts_to_iso(period_to),
        },
        "summary": {
            "total_gets": len(gets),
            "total_searches": len(searches),
            "total_misses": len(misses),
            "miss_rate": round(miss_rate, 3),
            "correlated_pct": round(correlated_pct, 3),
        },
        "findings": findings,
    }
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/storage/test_index_store.py -k "analyze" -v
```
Expected: all passing.

- [ ] **Step 5: Run full suite**

```bash
pytest tests/ -v
```
Expected: all passing.

- [ ] **Step 6: Commit**

```bash
git add src/loci/storage/index_store.py tests/storage/test_index_store.py
git commit -m "feat: IndexStore.analyze() — findings engine for self-healing audit"
```

---

### Task 6: `loci analyze` CLI command

**Files:**
- Modify: `src/loci/cli.py`
- Test: `tests/test_cli.py`

- [ ] **Step 1: Write failing tests**

```python
def test_cmd_analyze_json_output(tmp_path, monkeypatch):
    """analyze outputs valid JSON with required top-level keys."""
    monkeypatch.setenv("LOCI_BASE_DIR", str(tmp_path / "idx"))
    result = run_loci(["analyze"])
    data = json.loads(result.stdout)
    assert "findings" in data
    assert "summary" in data
    assert "period" in data

def test_cmd_analyze_empty_findings_when_no_data(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCI_BASE_DIR", str(tmp_path / "idx"))
    result = run_loci(["analyze"])
    data = json.loads(result.stdout)
    assert data["findings"] == []

def test_cmd_analyze_since_flag(tmp_path, monkeypatch):
    """--since N scopes to last N days."""
    monkeypatch.setenv("LOCI_BASE_DIR", str(tmp_path / "idx"))
    result = run_loci(["analyze", "--since", "7"])
    data = json.loads(result.stdout)
    assert "findings" in data

def test_cmd_analyze_repo_filter(tmp_path, monkeypatch):
    """--repo filters findings to that repo only."""
    monkeypatch.setenv("LOCI_BASE_DIR", str(tmp_path / "idx"))
    repo_a = str(tmp_path / "repo_a")
    repo_b = str(tmp_path / "repo_b")
    (tmp_path / "idx").mkdir(parents=True, exist_ok=True)
    import time as _time
    # Write enough miss events to guarantee search_miss finding fires for both repos
    log_lines = [
        json.dumps({"ts": _time.time(), "event": "miss", "miss_type": "search_empty",
                    "query": "foo_only_in_a", "repo": repo_a}),
        json.dumps({"ts": _time.time(), "event": "miss", "miss_type": "search_empty",
                    "query": "bar_only_in_b", "repo": repo_b}),
    ]
    (tmp_path / "idx" / "session.jsonl").write_text("\n".join(log_lines) + "\n")
    result = run_loci(["analyze", "--repo", repo_a])
    data = json.loads(result.stdout)
    miss_finding = next((f for f in data["findings"] if f["type"] == "search_miss"), None)
    assert miss_finding is not None, "Expected search_miss finding for repo_a"
    assert "foo_only_in_a" in miss_finding["data"]["queries"]
    assert "bar_only_in_b" not in miss_finding["data"]["queries"]  # repo_b excluded

def test_cmd_analyze_pretty_flag(tmp_path, monkeypatch):
    """--pretty outputs human-readable text, not JSON."""
    monkeypatch.setenv("LOCI_BASE_DIR", str(tmp_path / "idx"))
    result = run_loci(["analyze", "--pretty"])
    try:
        json.loads(result.stdout)
        assert False, "Expected non-JSON output"
    except json.JSONDecodeError:
        pass
    assert "findings" in result.stdout.lower() or "no issues" in result.stdout.lower()
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_cli.py -k "cmd_analyze" -v
```
Expected: FAIL — `analyze` subcommand doesn't exist.

- [ ] **Step 3: Add `cmd_analyze` and `_format_analyze_pretty` to `cli.py`**

```python
def _format_analyze_pretty(result: dict) -> str:
    lines = []
    summary = result["summary"]
    lines.append(f"loci Audit Report  {result['period']['from']} → {result['period']['to']}")
    lines.append("─" * 72)
    lines.append(
        f"Gets: {summary['total_gets']}  "
        f"Searches: {summary['total_searches']}  "
        f"Misses: {summary['total_misses']}  "
        f"Miss rate: {round(summary['miss_rate'] * 100)}%  "
        f"Correlated: {round(summary['correlated_pct'] * 100)}%"
    )
    lines.append("")
    findings = result["findings"]
    if not findings:
        lines.append("No issues found. Tool is working well.")
        return "\n".join(lines)
    lines.append(f"Findings ({len(findings)}):")
    lines.append("─" * 72)
    for f in findings:
        lines.append(f"[{f['severity'].upper()}] {f['type']}")
        lines.append(f"  {f['suggestion']}")
        lines.append(f"  data: {json.dumps(f['data'])}")
        lines.append("")
    return "\n".join(lines)


def cmd_analyze(args: argparse.Namespace) -> int:
    store = _get_store()
    repo_filter = str(Path(args.repo).resolve()) if getattr(args, "repo", None) else None
    result = store.analyze(since_days=args.since, repo_filter=repo_filter)
    if args.pretty:
        print(_format_analyze_pretty(result))
    else:
        print(json.dumps(result))
    return 0
```

- [ ] **Step 4: Wire into argument parser**

Find the `subparsers.add_parser` block in `main()` and add:

```python
p_analyze = subparsers.add_parser("analyze", help="Audit loci usage and emit improvement findings")
p_analyze.add_argument("--repo", help="Filter to a specific repo path")
p_analyze.add_argument("--since", type=int, default=30,
                       help="Days of history to analyze (default: 30)")
p_analyze.add_argument("--pretty", action="store_true", help="Human-readable output")
p_analyze.set_defaults(func=cmd_analyze)
```

- [ ] **Step 5: Run all tests**

```bash
pytest tests/ -v
```
Expected: all passing.

- [ ] **Step 6: Commit**

```bash
git add src/loci/cli.py tests/test_cli.py
git commit -m "feat: add loci analyze command"
```

---

### Task 7: Update MEMORY.md and loci skill

**Files:**
- Modify: `~/.claude/projects/-home-brummerv-exploration/memory/MEMORY.md`
- Modify: `~/.claude/skills/loci/SKILL.md`

- [ ] **Step 1: Add `analyze` to MEMORY.md commands list**

Add to the commands section:
```
- `loci analyze [--repo <path>] [--since DAYS] [--pretty]` — audit usage log, emit findings for self-improvement
```

- [ ] **Step 2: Add analyze workflow note to loci skill**

Add a section explaining: run `loci analyze` periodically or when asked to improve the tool; read `findings[]` array; each finding has `type`, `severity`, `data`, `suggestion` — act on `suggestion` directly.

- [ ] **Step 3: Final full test run**

```bash
source .venv/bin/activate && pytest tests/ -v
```
Expected: all tests passing.

- [ ] **Step 4: Final commit**

```bash
git add ~/.claude/projects/-home-brummerv-exploration/memory/MEMORY.md
git add ~/.claude/skills/loci/SKILL.md
git commit -m "docs: update MEMORY and loci skill with analyze command"
```
