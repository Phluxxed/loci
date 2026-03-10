# loci: file, grep, batch get — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add three commands to loci that close agent-workflow gaps: `file` (read cached file content with optional line range), `grep` (full-text regex search across cached files), and batch `get` (retrieve multiple symbols in one call).

**Architecture:** All three operate against the existing sources cache at `_sources_dir(repo_path)`. Two new methods go in `IndexStore` (`get_file_content`, `grep_files`). CLI changes go in `cli.py`. No new files, no new dependencies beyond stdlib `re`.

**Tech Stack:** Python stdlib only. `re` for grep. Existing `IndexStore` sources cache for content. TDD throughout — write the failing test, watch it fail, implement, watch it pass.

---

## Context: Key files

- `src/loci/cli.py` — all CLI commands and argparse setup
- `src/loci/storage/index_store.py` — IndexStore class (add new methods here)
- `tests/test_cli.py` — all CLI tests (add new tests here)
- `tests/fixtures/sample.py` — 18-line fixture: `add()` function (lines 4–6), `Calculator` class (lines 9–17)

The `indexed_repo` fixture (already in `tests/test_cli.py`) runs `loci index` and returns `(repo_path, base_dir_str)`. Use it for all new tests.

The `run_loci(*args, env_extra={"LOCI_BASE_DIR": base})` helper (already in `tests/test_cli.py`) runs loci as a subprocess. Use it for all new tests.

---

## Task 1: `loci file` — read cached file content with optional line range

**Files:**
- Modify: `src/loci/storage/index_store.py`
- Modify: `src/loci/cli.py`
- Test: `tests/test_cli.py`

---

### Step 1: Write the failing tests

Add these tests to the bottom of `tests/test_cli.py`:

```python
def test_file_returns_full_content(indexed_repo):
    repo, base = indexed_repo
    result = run_loci("file", "sample.py", "--repo", str(repo), env_extra={"LOCI_BASE_DIR": base})
    assert result.returncode == 0, result.stderr
    data = json.loads(result.stdout)
    assert data["file"] == "sample.py"
    assert "content" in data
    assert "def add" in data["content"]
    assert data["total_lines"] == 18
    assert data["start_line"] == 1
    assert data["end_line"] == 18


def test_file_with_line_range(indexed_repo):
    repo, base = indexed_repo
    result = run_loci("file", "sample.py", "--repo", str(repo), "--start", "4", "--end", "6", env_extra={"LOCI_BASE_DIR": base})
    assert result.returncode == 0, result.stderr
    data = json.loads(result.stdout)
    assert data["start_line"] == 4
    assert data["end_line"] == 6
    assert "def add" in data["content"]
    assert len(data["content"].splitlines()) == 3


def test_file_unknown_file_returns_error(indexed_repo):
    repo, base = indexed_repo
    result = run_loci("file", "nonexistent.py", "--repo", str(repo), env_extra={"LOCI_BASE_DIR": base})
    assert result.returncode != 0
    data = json.loads(result.stderr)
    assert "error" in data
```

### Step 2: Run tests to verify they fail

```bash
cd /home/brummerv/exploration/loci
pytest tests/test_cli.py::test_file_returns_full_content tests/test_cli.py::test_file_with_line_range tests/test_cli.py::test_file_unknown_file_returns_error -v
```

Expected: all three FAIL with `error: argument command: invalid choice: 'file'` (command doesn't exist yet).

---

### Step 3: Add `get_file_content` to `IndexStore`

In `src/loci/storage/index_store.py`, add this method after `get_symbol_file_size` (around line 236):

```python
def get_file_content(
    self,
    repo_path: Path,
    file_path: str,
    start_line: Optional[int] = None,
    end_line: Optional[int] = None,
) -> Optional[dict]:
    source_file = self._sources_dir(repo_path) / file_path
    if not source_file.exists():
        return None
    raw = source_file.read_bytes()
    content = raw.decode("utf-8", errors="replace")
    lines = content.splitlines(keepends=True)
    total_lines = len(lines)
    file_bytes = len(raw)

    start = (start_line - 1) if start_line is not None else 0
    end = end_line if end_line is not None else total_lines
    start = max(0, min(start, total_lines))
    end = max(start, min(end, total_lines))
    sliced = "".join(lines[start:end])

    return {
        "file": file_path,
        "content": sliced,
        "total_lines": total_lines,
        "start_line": start + 1,
        "end_line": end,
        "file_bytes": file_bytes,
    }
```

### Step 4: Add `cmd_file` to `cli.py`

Add this function in `src/loci/cli.py` after `cmd_get` (around line 136):

```python
def cmd_file(args: argparse.Namespace) -> int:
    repo_path = Path(args.repo).resolve()
    store = _get_store()
    result = store.get_file_content(
        repo_path, args.file_path, start_line=args.start, end_line=args.end
    )
    if result is None:
        print(json.dumps({"error": f"File not found in cache: {args.file_path}"}), file=sys.stderr)
        return 1
    symbol_bytes = len(result["content"].encode("utf-8"))
    file_bytes = result.pop("file_bytes")
    store.log_retrieval(args.file_path, symbol_bytes, file_bytes, repo_path=str(repo_path))
    print(json.dumps(result))
    return 0
```

### Step 5: Register the subparser and dispatch in `cli.py`

In `main()`, add the subparser after `p_get` (around line 302):

```python
    p_file = sub.add_parser("file", help="Get cached file content")
    p_file.add_argument("file_path", help="Relative file path (as indexed, e.g. src/foo.py)")
    p_file.add_argument("--repo", required=True, help="Path to indexed repo")
    p_file.add_argument("--start", type=int, default=None, help="Start line (1-indexed, inclusive)")
    p_file.add_argument("--end", type=int, default=None, help="End line (1-indexed, inclusive)")
```

In the dispatch block at the bottom of `main()`, add after `elif args.command == "get":`:

```python
    elif args.command == "file":
        sys.exit(cmd_file(args))
```

### Step 6: Run tests to verify they pass

```bash
pytest tests/test_cli.py::test_file_returns_full_content tests/test_cli.py::test_file_with_line_range tests/test_cli.py::test_file_unknown_file_returns_error -v
```

Expected: all three PASS.

### Step 7: Run the full test suite to confirm no regressions

```bash
pytest tests/ -v
```

Expected: all existing tests still PASS, 3 new tests PASS.

### Step 8: Commit

```bash
git add src/loci/storage/index_store.py src/loci/cli.py tests/test_cli.py
git commit -m "feat: add loci file command for cached file content retrieval"
```

---

## Task 2: `loci grep` — full-text regex search across cached files

**Files:**
- Modify: `src/loci/storage/index_store.py`
- Modify: `src/loci/cli.py`
- Test: `tests/test_cli.py`

---

### Step 1: Write the failing tests

Add these tests to the bottom of `tests/test_cli.py`:

```python
def test_grep_finds_match(indexed_repo):
    repo, base = indexed_repo
    result = run_loci("grep", "def add", "--repo", str(repo), env_extra={"LOCI_BASE_DIR": base})
    assert result.returncode == 0, result.stderr
    data = json.loads(result.stdout)
    assert isinstance(data, list)
    assert len(data) >= 1
    assert any("add" in m["match"] for m in data)


def test_grep_returns_context_lines(indexed_repo):
    repo, base = indexed_repo
    result = run_loci("grep", "def add", "--repo", str(repo), env_extra={"LOCI_BASE_DIR": base})
    data = json.loads(result.stdout)
    match = data[0]
    assert "file" in match
    assert "line" in match
    assert "match" in match
    assert "context_before" in match
    assert "context_after" in match
    assert isinstance(match["context_before"], list)
    assert isinstance(match["context_after"], list)


def test_grep_no_match_returns_empty(indexed_repo):
    repo, base = indexed_repo
    result = run_loci("grep", "xyzzy_no_match_ever_12345", "--repo", str(repo), env_extra={"LOCI_BASE_DIR": base})
    assert result.returncode == 0
    data = json.loads(result.stdout)
    assert data == []


def test_grep_invalid_regex_returns_error(indexed_repo):
    repo, base = indexed_repo
    result = run_loci("grep", "[unclosed", "--repo", str(repo), env_extra={"LOCI_BASE_DIR": base})
    assert result.returncode != 0


def test_grep_unindexed_repo_returns_empty(tmp_path):
    result = run_loci(
        "grep", "anything", "--repo", str(tmp_path / "norepo"),
        env_extra={"LOCI_BASE_DIR": str(tmp_path / ".ci")},
    )
    assert result.returncode == 0
    data = json.loads(result.stdout)
    assert data == []
```

### Step 2: Run tests to verify they fail

```bash
pytest tests/test_cli.py::test_grep_finds_match tests/test_cli.py::test_grep_returns_context_lines tests/test_cli.py::test_grep_no_match_returns_empty tests/test_cli.py::test_grep_invalid_regex_returns_error tests/test_cli.py::test_grep_unindexed_repo_returns_empty -v
```

Expected: all five FAIL with `error: argument command: invalid choice: 'grep'`.

---

### Step 3: Add `import re` to `index_store.py`

At the top of `src/loci/storage/index_store.py`, add `import re` to the existing imports block:

```python
from __future__ import annotations
import hashlib
import json
import re
import shutil
import time
from pathlib import Path
from typing import Any, Optional
```

### Step 4: Add `grep_files` to `IndexStore`

In `src/loci/storage/index_store.py`, add this method after `get_file_content`:

```python
def grep_files(self, repo_path: Path, pattern: str) -> list[dict[str, Any]]:
    try:
        regex = re.compile(pattern)
    except re.error as exc:
        raise ValueError(f"Invalid regex pattern: {exc}") from exc

    sources = self._sources_dir(repo_path)
    if not sources.exists():
        return []

    results: list[dict[str, Any]] = []
    for src_file in sorted(sources.rglob("*")):
        if not src_file.is_file():
            continue
        rel_path = str(src_file.relative_to(sources))
        try:
            lines = src_file.read_text(encoding="utf-8", errors="replace").splitlines()
        except Exception:
            continue
        for i, line in enumerate(lines):
            if regex.search(line):
                results.append({
                    "file": rel_path,
                    "line": i + 1,
                    "match": line,
                    "context_before": lines[max(0, i - 2):i],
                    "context_after": lines[i + 1:min(len(lines), i + 3)],
                })
    return results
```

### Step 5: Add `cmd_grep` to `cli.py`

Add this function in `src/loci/cli.py` after `cmd_file`:

```python
def cmd_grep(args: argparse.Namespace) -> int:
    repo_path = Path(args.repo).resolve()
    store = _get_store()
    try:
        results = store.grep_files(repo_path, args.pattern)
    except ValueError as e:
        print(json.dumps({"error": str(e)}), file=sys.stderr)
        return 1
    print(json.dumps(results))
    return 0
```

### Step 6: Register the subparser and dispatch in `cli.py`

In `main()`, add the subparser after `p_file`:

```python
    p_grep = sub.add_parser("grep", help="Search text across cached files")
    p_grep.add_argument("pattern", help="Regex pattern to search for")
    p_grep.add_argument("--repo", required=True, help="Path to indexed repo")
```

In the dispatch block, add after `elif args.command == "file":`:

```python
    elif args.command == "grep":
        sys.exit(cmd_grep(args))
```

### Step 7: Run tests to verify they pass

```bash
pytest tests/test_cli.py::test_grep_finds_match tests/test_cli.py::test_grep_returns_context_lines tests/test_cli.py::test_grep_no_match_returns_empty tests/test_cli.py::test_grep_invalid_regex_returns_error tests/test_cli.py::test_grep_unindexed_repo_returns_empty -v
```

Expected: all five PASS.

### Step 8: Run the full test suite to confirm no regressions

```bash
pytest tests/ -v
```

Expected: all tests PASS.

### Step 9: Commit

```bash
git add src/loci/storage/index_store.py src/loci/cli.py tests/test_cli.py
git commit -m "feat: add loci grep command for full-text search across cached files"
```

---

## Task 3: Batch `loci get` — retrieve multiple symbols in one call

**Files:**
- Modify: `src/loci/cli.py`
- Test: `tests/test_cli.py`

---

### Step 1: Write the failing tests

Add these tests to the bottom of `tests/test_cli.py`:

```python
def test_get_batch_returns_array(indexed_repo):
    repo, base = indexed_repo
    search = run_loci("search", "calculator", "--repo", str(repo), env_extra={"LOCI_BASE_DIR": base})
    symbols = json.loads(search.stdout)
    # Get at least 2 IDs — Calculator class + multiply method
    ids = [s["id"] for s in symbols[:2]]
    assert len(ids) == 2, "Need at least 2 results from search"

    result = run_loci("get", *ids, "--repo", str(repo), env_extra={"LOCI_BASE_DIR": base})
    assert result.returncode == 0, result.stderr
    data = json.loads(result.stdout)
    assert isinstance(data, list)
    assert len(data) == 2
    assert all("source" in entry for entry in data)


def test_get_batch_mixed_valid_invalid(indexed_repo):
    repo, base = indexed_repo
    search = run_loci("search", "add", "--repo", str(repo), env_extra={"LOCI_BASE_DIR": base})
    valid_id = next(s["id"] for s in json.loads(search.stdout) if s["name"] == "add")

    result = run_loci("get", valid_id, "nonexistent::missing#function", "--repo", str(repo), env_extra={"LOCI_BASE_DIR": base})
    assert result.returncode == 0  # batch mode: partial success is exit 0
    data = json.loads(result.stdout)
    assert isinstance(data, list)
    assert len(data) == 2
    assert "source" in data[0]   # valid symbol
    assert "error" in data[1]    # not-found symbol


def test_get_single_still_returns_object_not_array(indexed_repo):
    # Backwards compatibility: single ID must still return a plain object
    repo, base = indexed_repo
    search = run_loci("search", "add", "--repo", str(repo), env_extra={"LOCI_BASE_DIR": base})
    sym_id = next(s["id"] for s in json.loads(search.stdout) if s["name"] == "add")

    result = run_loci("get", sym_id, "--repo", str(repo), env_extra={"LOCI_BASE_DIR": base})
    assert result.returncode == 0, result.stderr
    data = json.loads(result.stdout)
    assert isinstance(data, dict)   # NOT a list
    assert "source" in data
```

### Step 2: Run tests to verify they fail

```bash
pytest tests/test_cli.py::test_get_batch_returns_array tests/test_cli.py::test_get_batch_mixed_valid_invalid tests/test_cli.py::test_get_single_still_returns_object_not_array -v
```

Expected:
- `test_get_batch_returns_array` FAILS — `get` only accepts one positional arg
- `test_get_batch_mixed_valid_invalid` FAILS — same reason
- `test_get_single_still_returns_object_not_array` PASSES (current behavior is a dict) — this is fine; it proves the existing contract we must preserve

---

### Step 3: Refactor `cmd_get` in `cli.py`

Replace the entire `cmd_get` function (lines 110–135) with:

```python
def cmd_get(args: argparse.Namespace) -> int:
    repo_path = Path(args.repo).resolve()
    store = _get_store()
    index = store.load(repo_path)
    single = len(args.symbol_ids) == 1

    def _fetch(symbol_id: str) -> dict:
        if index is None:
            return {"id": symbol_id, "error": "Repo not indexed"}
        meta = next((s for s in index["symbols"] if s["id"] == symbol_id), None)
        if meta is None:
            return {"id": symbol_id, "error": f"Symbol not found: {symbol_id}"}
        content = store.get_symbol_content(repo_path, symbol_id)
        if content is None:
            return {"id": symbol_id, "error": f"Symbol not found: {symbol_id}"}
        symbol_bytes = len(content.encode("utf-8"))
        file_bytes = store.get_symbol_file_size(repo_path, symbol_id)
        if file_bytes is not None:
            store.log_retrieval(symbol_id, symbol_bytes, file_bytes, repo_path=str(repo_path))
        return {
            "id": symbol_id,
            "source": content,
            **{k: meta.get(k) for k in ("byte_offset", "byte_length", "signature", "kind", "language")},  # type: ignore[union-attr]
        }

    if single:
        result = _fetch(args.symbol_ids[0])
        if "error" in result:
            print(json.dumps(result), file=sys.stderr)
            return 1
        print(json.dumps(result))
        return 0

    results = [_fetch(sid) for sid in args.symbol_ids]
    print(json.dumps(results))
    return 0
```

### Step 4: Update the `get` subparser in `main()`

In `main()`, find the `p_get` block (around line 298) and change `symbol_id` to `symbol_ids` with `nargs="+"`:

```python
    p_get = sub.add_parser("get", help="Get symbol source by ID")
    p_get.add_argument("symbol_ids", nargs="+", help="Symbol ID(s)")
    p_get.add_argument("--repo", required=True, help="Path to indexed repo")
```

No change needed to the dispatch line `sys.exit(cmd_get(args))`.

### Step 5: Run the three new tests to verify they pass

```bash
pytest tests/test_cli.py::test_get_batch_returns_array tests/test_cli.py::test_get_batch_mixed_valid_invalid tests/test_cli.py::test_get_single_still_returns_object_not_array -v
```

Expected: all three PASS.

### Step 6: Run the full test suite to confirm no regressions

```bash
pytest tests/ -v
```

Expected: all tests PASS. Pay attention to any existing `get`-related tests — they use single IDs and must still work because `nargs="+"` accepts one argument.

### Step 7: Commit

```bash
git add src/loci/cli.py tests/test_cli.py
git commit -m "feat: extend loci get to accept multiple symbol IDs in one call"
```

---

## Final verification

```bash
pytest tests/ -v --tb=short
```

Expected: all tests pass (existing ~78 + 11 new = ~89 tests).
