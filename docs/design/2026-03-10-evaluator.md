# loci Evaluator Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add three self-healing mechanisms to loci: ground-truth test fixtures, index-time 0-symbol warnings, and a `loci verify` command that checks byte offset correctness.

**Architecture:** Three independent additions — richer fixtures live in `tests/fixtures/`, warnings are added to `cmd_index` output in `cli.py`, and `verify` is a new command in `cli.py` backed by a new `IndexStore.verify_index` method.

**Tech Stack:** Python, pytest, tree-sitter (existing), pathlib (existing)

---

## Chunk 1: Ground-truth test fixtures

**Files:**
- Modify: `tests/fixtures/sample.py`
- Modify: `tests/fixtures/sample.ts`
- Modify: `tests/parser/test_extractor.py` (add ground-truth extraction tests)

### Task 1: Expand sample.py fixture

The current `sample.py` has only 3 symbols. It needs to cover every extraction path: top-level functions, decorated functions, classes, methods, and nested classes.

- [ ] **Step 1: Replace `tests/fixtures/sample.py`**

```python
"""Sample Python module for testing."""


def add(x: int, y: int) -> int:
    """Add two numbers."""
    return x + y


def decorator(func):
    """A simple decorator."""
    return func


@decorator
def decorated_function() -> None:
    """A decorated function."""
    pass


class Calculator:
    """A simple calculator."""

    def multiply(self, x: int, y: int) -> int:
        """Multiply two numbers."""
        return x * y

    def divide(self, x: float, y: float) -> float:
        return x / y


class Outer:
    """An outer class with a nested class."""

    class Inner:
        """A nested inner class."""

        def inner_method(self) -> str:
            return "inner"


# Module-level constant — should NOT be extracted as a symbol
MY_CONSTANT = 42
```

- [ ] **Step 2: Replace `tests/fixtures/sample.ts`**

```typescript
/** A simple greeter function. */
function greet(name: string): string {
    return `Hello, ${name}`;
}

/** An arrow function assigned to a const — NOT extracted (not a declaration). */
const helper = (x: number) => x * 2;

/** A user class. */
class User {
    name: string;

    /** Create a new user. */
    constructor(name: string) {
        this.name = name;
    }

    /** Get the display name. */
    getDisplayName(): string {
        return this.name.toUpperCase();
    }
}

/** A type alias. */
type UserId = string;

/** An interface. */
interface UserRepository {
    findById(id: UserId): User | null;
}
```

### Task 2: Add ground-truth extraction tests

- [ ] **Step 3: Add EXPECTED_SYMBOLS constants and tests to `tests/parser/test_extractor.py`**

Open `tests/parser/test_extractor.py` and add at the bottom:

```python
# ── Ground-truth fixture tests ──────────────────────────────────────────────

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"

# (name, kind) pairs that MUST appear in sample.py
PYTHON_EXPECTED = [
    ("add", "function"),
    ("decorator", "function"),
    ("decorated_function", "function"),
    ("Calculator", "class"),
    ("multiply", "method"),
    ("divide", "method"),
    ("Outer", "class"),
    ("Inner", "class"),
    ("inner_method", "method"),
]

# (name, kind) pairs that MUST appear in sample.ts
# Note: constructor is a method_definition in tree-sitter TypeScript but omitted
# here until confirmed working - add ("constructor", "method") once verified.
TS_EXPECTED = [
    ("greet", "function"),
    ("User", "class"),
    ("getDisplayName", "method"),
    ("UserId", "type"),
    ("UserRepository", "interface"),
]


def _extracted(fixture_name: str) -> list[tuple[str, str]]:
    path = FIXTURES_DIR / fixture_name
    symbols = parse_file(path)
    return [(s.name, s.kind) for s in symbols]


def test_python_fixture_ground_truth():
    extracted = _extracted("sample.py")
    for name, kind in PYTHON_EXPECTED:
        assert (name, kind) in extracted, (
            f"Expected ({name!r}, {kind!r}) in sample.py symbols, got: {extracted}"
        )


def test_python_fixture_no_spurious_symbols():
    extracted = _extracted("sample.py")
    names = [name for name, _ in extracted]
    # Module-level constants should NOT be extracted
    assert "MY_CONSTANT" not in names


def test_ts_fixture_ground_truth():
    extracted = _extracted("sample.ts")
    for name, kind in TS_EXPECTED:
        assert (name, kind) in extracted, (
            f"Expected ({name!r}, {kind!r}) in sample.ts symbols, got: {extracted}"
        )


def test_ts_fixture_no_spurious_symbols():
    extracted = _extracted("sample.ts")
    names = [name for name, _ in extracted]
    assert "helper" not in names  # arrow function const, should not be extracted


```

- [ ] **Step 3b: Add get round-trip test to `tests/test_cli.py`**

This test verifies that `loci get` returns source bytes containing the symbol name — it belongs in `test_cli.py` where `run_loci` already exists (not `test_extractor.py`).

Add to `tests/test_cli.py`:

```python
def test_get_round_trip_contains_symbol_name(indexed_repo: tuple[Path, str]):
    """loci get should return source that contains the symbol name."""
    repo, base = indexed_repo
    outline_result = run_loci("outline", str(repo), env_extra={"LOCI_BASE_DIR": base})
    outline = json.loads(outline_result.stdout)
    first_sym = outline[0]["symbols"][0]
    sym_id = first_sym["id"]
    sym_name = first_sym["name"]

    result = run_loci("get", sym_id, "--repo", str(repo), env_extra={"LOCI_BASE_DIR": base})
    assert result.returncode == 0
    data = json.loads(result.stdout)
    assert sym_name in data["source"], (
        f"Expected {sym_name!r} in retrieved source, got: {data['source'][:200]}"
    )
```

Note: `indexed_repo` and `fixtures_dir` fixtures are pre-existing in `tests/test_cli.py` and `tests/conftest.py` respectively.

- [ ] **Step 4: Run the new tests to see current state**

```bash
cd /home/brummerv/exploration/loci && source .venv/bin/activate && pytest tests/parser/test_extractor.py::test_python_fixture_ground_truth tests/parser/test_extractor.py::test_ts_fixture_ground_truth -v
```

Expected: some may fail if the new fixture symbols aren't extracted yet. Note which ones fail — those identify real gaps.

- [ ] **Step 5: Run full test suite to confirm nothing broke**

```bash
pytest tests/ -v --tb=short 2>&1 | tail -20
```

Expected: existing tests pass (fixture changes may affect counts — update any hardcoded `total_lines` or `symbols_indexed` assertions if needed).

- [ ] **Step 6: Fix any count assertions broken by fixture changes**

Search for hardcoded counts referencing the old fixture shape:

```bash
grep -rn "total_lines\|symbols_indexed\|== 17\|== 3\|== 4\|== 5" tests/
```

Update as needed to match new fixture sizes.

- [ ] **Step 7: Commit**

```bash
cd /home/brummerv/exploration/loci
git add tests/fixtures/sample.py tests/fixtures/sample.ts tests/parser/test_extractor.py
git commit -m "test: expand ground-truth fixtures and add extraction correctness tests"
```

---

## Chunk 2: Index-time warnings

**Files:**
- Modify: `src/loci/cli.py` (lines 50–106, `cmd_index`)
- Modify: `tests/test_cli.py` (add warning tests)

The goal: when `loci index` finds a file with a known extension that produces 0 symbols and has more than 10 lines, emit a warning entry. The `warnings` key is absent from the output when there are no warnings (keeps existing output clean).

**Intentional behaviour:** Files skipped by `--incremental` (hash unchanged) do NOT re-check for 0 symbols. They were already processed and warnings are only generated at parse time. This is correct — if the file was previously indexed with 0 symbols, the issue was at the original index time and won't be caught by a re-index with `--incremental`. Use `loci verify` to detect pre-existing issues after the fact.

### Task 3: Add 0-symbol warning collection to cmd_index

- [ ] **Step 8: Write the failing test first**

Add to `tests/test_cli.py`:

```python
def test_index_warns_on_zero_symbol_file(tmp_path: Path):
    """A non-trivial Python file that yields 0 symbols should appear in warnings."""
    repo = tmp_path / "warn_repo"
    repo.mkdir()
    # Write a file that is all comments — valid Python, but no extractable symbols
    lines = ["# comment\n"] * 15
    (repo / "no_symbols.py").write_text("".join(lines))
    base = str(tmp_path / ".codeindex")
    result = run_loci("index", str(repo), env_extra={"LOCI_BASE_DIR": base})
    assert result.returncode == 0
    data = json.loads(result.stdout)
    assert "warnings" in data
    warning_files = [w["file"] for w in data["warnings"]]
    assert "no_symbols.py" in warning_files


def test_index_no_warnings_key_when_clean(sample_repo: Path, tmp_path: Path):
    """Normal repo with symbols should not have a warnings key."""
    base = str(tmp_path / ".codeindex")
    result = run_loci("index", str(sample_repo), env_extra={"LOCI_BASE_DIR": base})
    data = json.loads(result.stdout)
    assert "warnings" not in data
```

- [ ] **Step 9: Run to verify tests fail**

```bash
pytest tests/test_cli.py::test_index_warns_on_zero_symbol_file tests/test_cli.py::test_index_no_warnings_key_when_clean -v
```

Expected: both FAIL (no `warnings` key in output yet).

- [ ] **Step 10: Implement warnings in `cmd_index`**

In `src/loci/cli.py`, modify `cmd_index`. After the loop body where `symbols = parse_file(src_file)` is called, collect warnings. Then conditionally include in output.

Replace the section from `all_symbols: list[Symbol] = []` through the `print(json.dumps(...))` block:

```python
    all_symbols: list[Symbol] = []
    new_file_hashes: dict[str, str] = dict(existing_hashes)
    files_skipped = 0
    language_counts: dict[str, int] = defaultdict(int)
    zero_symbol_warnings: list[dict] = []
    gitignore = _load_gitignore(repo_path)

    for src_file in sorted(repo_path.rglob("*")):
        if not src_file.is_file():
            continue
        if any(part in SKIP_DIRS for part in src_file.parts):
            continue
        if _should_skip_file(src_file):
            continue

        rel_path = str(src_file.relative_to(repo_path))
        if gitignore and gitignore.match_file(rel_path):
            continue
        file_hash = store.hash_file(src_file)

        if args.incremental and existing_hashes.get(rel_path) == file_hash:
            kept = [Symbol.from_dict(s) for s in existing_symbols if s["file_path"] == rel_path]
            all_symbols.extend(kept)
            files_skipped += 1
            lang = EXTENSION_MAP.get(src_file.suffix, "unknown")
            language_counts[lang] += 1
            continue

        symbols = parse_file(src_file)
        for sym in symbols:
            sym.file_path = rel_path
            sym.id = f"{rel_path}::{sym.qualified_name}#{sym.kind}"
        all_symbols.extend(symbols)
        new_file_hashes[rel_path] = file_hash
        lang = EXTENSION_MAP.get(src_file.suffix, "unknown")
        if symbols:
            language_counts[lang] += 1
        else:
            # Warn on non-trivial files with known extensions that yield 0 symbols
            try:
                line_count = len(src_file.read_bytes().splitlines())
            except OSError:
                line_count = 0
            if line_count > 10:
                zero_symbol_warnings.append({
                    "file": rel_path,
                    "lines": line_count,
                    "reason": "0 symbols extracted",
                })

    store.write(repo_path, all_symbols, file_hashes=new_file_hashes)

    output: dict = {
        "path": str(repo_path),
        "symbols_indexed": len(all_symbols),
        "files_skipped": files_skipped,
        "languages": dict(language_counts),
    }
    if zero_symbol_warnings:
        output["warnings"] = zero_symbol_warnings

    print(json.dumps(output))
    return 0
```

- [ ] **Step 11: Run tests to verify they pass**

```bash
pytest tests/test_cli.py::test_index_warns_on_zero_symbol_file tests/test_cli.py::test_index_no_warnings_key_when_clean -v
```

Expected: both PASS.

- [ ] **Step 12: Run full test suite**

```bash
pytest tests/ -v --tb=short 2>&1 | tail -20
```

Expected: all tests pass.

- [ ] **Step 13: Commit**

```bash
git add src/loci/cli.py tests/test_cli.py
git commit -m "feat: add 0-symbol warnings to loci index output"
```

---

## Chunk 3: loci verify command

**Files:**
- Modify: `src/loci/storage/index_store.py` (add `verify_index` method)
- Modify: `src/loci/cli.py` (add `cmd_verify`, register subparser)
- Modify: `tests/test_cli.py` (add verify tests)

### Task 4: Implement `IndexStore.verify_index`

The method checks every indexed symbol: reads `byte_offset` + `byte_length` bytes from the cached source file, and verifies the symbol's name appears in that text. A failure means the byte offset is wrong or the symbol was extracted incorrectly.

**Note:** This is an intentional simplification — the check is "does the symbol name appear in the bytes at the stored offset?" rather than a full tree-sitter re-parse. This catches byte offset corruption and wrong-node-type extraction, which are the most common failure modes. It won't catch cases where the name coincidentally appears in a comment at a wrong offset, but that's an acceptable trade-off for the implementation cost.

**Pre-existing fixtures:** `indexed_repo` and `fixtures_dir` are already defined in `tests/test_cli.py` and `tests/conftest.py` respectively. No need to create them.

- [ ] **Step 14: Write the failing test**

Add to `tests/test_cli.py`:

```python
def test_verify_clean_repo_passes(indexed_repo: tuple[Path, str]):
    repo, base = indexed_repo
    result = run_loci("verify", str(repo), env_extra={"LOCI_BASE_DIR": base})
    assert result.returncode == 0
    data = json.loads(result.stdout)
    assert data["checked"] > 0
    assert data["failed"] == []
    assert data["passed"] == data["checked"]
    assert data["repo"] == str(repo)


def test_verify_unindexed_repo_errors(tmp_path: Path):
    repo = tmp_path / "empty_repo"
    repo.mkdir()
    base = str(tmp_path / ".codeindex")
    result = run_loci("verify", str(repo), env_extra={"LOCI_BASE_DIR": base})
    assert result.returncode == 1
    data = json.loads(result.stderr)
    assert "error" in data


def test_verify_detects_corrupted_offset(tmp_path: Path, fixtures_dir: Path):
    """Manually corrupt a byte_offset in the index and verify it's caught."""
    import hashlib
    import shutil
    repo = tmp_path / "corrupt_repo"
    repo.mkdir()
    shutil.copy(fixtures_dir / "sample.py", repo / "sample.py")
    base = str(tmp_path / ".codeindex")

    # Index first
    run_loci("index", str(repo), env_extra={"LOCI_BASE_DIR": base})

    # Corrupt the index: set a non-zero-offset symbol's byte range to 1 byte at offset 1
    abs_path = str(repo.resolve())
    h = hashlib.md5(abs_path.encode()).hexdigest()[:12]
    cache_key = f"{h}_{repo.name}"
    index_file = Path(base) / cache_key / "index.json"
    data = json.loads(index_file.read_text())
    # Pick a non-trivial symbol (not one at offset 0) and corrupt its offset
    for sym in data["symbols"]:
        if sym["byte_offset"] > 10:
            sym["byte_offset"] = 1
            sym["byte_length"] = 1
            break
    index_file.write_text(json.dumps(data))

    result = run_loci("verify", str(repo), env_extra={"LOCI_BASE_DIR": base})
    assert result.returncode == 1
    out = json.loads(result.stdout)
    assert len(out["failed"]) > 0
```

- [ ] **Step 15: Run to verify tests fail**

```bash
pytest tests/test_cli.py::test_verify_clean_repo_passes tests/test_cli.py::test_verify_unindexed_repo_errors tests/test_cli.py::test_verify_detects_corrupted_offset -v
```

Expected: all FAIL (command doesn't exist yet).

- [ ] **Step 16: Add `verify_index` to `IndexStore`**

Add to `src/loci/storage/index_store.py` after the `invalidate` method:

```python
    def verify_index(self, repo_path: Path) -> dict[str, Any]:
        """Check that every symbol's byte offset points to text containing its name.

        Returns a dict with 'checked' count and 'failed' list. Each failure
        has the symbol id, name, kind, file, and the issue description.
        """
        index = self.load(repo_path)
        if index is None:
            return {"repo": str(repo_path), "error": "Repo not indexed"}

        sources = self._sources_dir(repo_path)
        checked = 0
        failed: list[dict[str, Any]] = []

        for sym in index["symbols"]:
            checked += 1
            sym_id = sym.get("id", "")
            name = sym.get("name", "")
            kind = sym.get("kind", "")
            file_path = sym.get("file_path", "")
            byte_offset = sym.get("byte_offset", 0)
            byte_length = sym.get("byte_length", 0)

            source_file = sources / file_path
            if not source_file.exists():
                failed.append({
                    "id": sym_id,
                    "name": name,
                    "kind": kind,
                    "file": file_path,
                    "issue": "source_file_missing",
                })
                continue

            try:
                with open(source_file, "rb") as f:
                    f.seek(byte_offset)
                    raw = f.read(byte_length)
                text = raw.decode("utf-8", errors="replace")
            except OSError as exc:
                failed.append({
                    "id": sym_id,
                    "name": name,
                    "kind": kind,
                    "file": file_path,
                    "issue": f"read_error: {exc}",
                })
                continue

            if name and name not in text:
                failed.append({
                    "id": sym_id,
                    "name": name,
                    "kind": kind,
                    "file": file_path,
                    "issue": "name_not_in_bytes",
                })

        return {
            "repo": str(repo_path),
            "checked": checked,
            "passed": checked - len(failed),
            "failed": failed,
        }
```

- [ ] **Step 17: Add `cmd_verify` to `cli.py`**

Add after `cmd_grep`:

```python
def cmd_verify(args: argparse.Namespace) -> int:
    repo_path = Path(args.path).resolve()
    store = _get_store()
    result = store.verify_index(repo_path)
    if "error" in result:
        print(json.dumps(result), file=sys.stderr)
        return 1
    has_failures = len(result["failed"]) > 0
    print(json.dumps(result))
    return 1 if has_failures else 0
```

- [ ] **Step 18: Register the `verify` subparser in `main()`**

In the `main()` function, add after the `p_grep` block:

```python
    p_verify = sub.add_parser("verify", help="Verify byte offsets for all indexed symbols")
    p_verify.add_argument("path", help="Path to repo")
```

And add the dispatch in the `if args.command ==` chain:

```python
    elif args.command == "verify":
        sys.exit(cmd_verify(args))
```

- [ ] **Step 19: Run tests to verify they pass**

```bash
pytest tests/test_cli.py::test_verify_clean_repo_passes tests/test_cli.py::test_verify_unindexed_repo_errors tests/test_cli.py::test_verify_detects_corrupted_offset -v
```

Expected: all PASS.

- [ ] **Step 20: Run full test suite**

```bash
pytest tests/ -v --tb=short 2>&1 | tail -20
```

Expected: all tests pass.

- [ ] **Step 21: Commit**

```bash
git add src/loci/storage/index_store.py src/loci/cli.py tests/test_cli.py
git commit -m "feat: add loci verify command for byte offset self-checking"
```

---

## Final verification

- [ ] **Step 22: Run complete test suite one final time**

```bash
cd /home/brummerv/exploration/loci && source .venv/bin/activate && pytest tests/ -v 2>&1 | tail -30
```

Expected: all tests pass, count higher than 90.

- [ ] **Step 23: Smoke test the new commands manually**

```bash
loci index /home/brummerv/exploration/loci
loci verify /home/brummerv/exploration/loci
```

Expected: `verify` returns `{"checked": N, "failed": []}` with exit code 0.
