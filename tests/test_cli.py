import json
import subprocess
import sys
from pathlib import Path
from typing import Optional
import pytest


def run_loci(*args: str, env_extra: Optional[dict] = None) -> subprocess.CompletedProcess:
    import os
    env = os.environ.copy()
    if env_extra:
        env.update(env_extra)
    return subprocess.run(
        [sys.executable, "-m", "loci.cli"] + list(args),
        capture_output=True,
        text=True,
        env=env,
    )


@pytest.fixture
def sample_repo(tmp_path: Path, fixtures_dir: Path) -> Path:
    repo = tmp_path / "myrepo"
    repo.mkdir()
    import shutil
    shutil.copy(fixtures_dir / "sample.py", repo / "sample.py")
    return repo


def test_index_respects_gitignore(tmp_path: Path, fixtures_dir: Path):
    repo = tmp_path / "gitignore_repo"
    repo.mkdir()
    import shutil
    shutil.copy(fixtures_dir / "sample.py", repo / "sample.py")
    # Create a file with a unique symbol that should be ignored
    (repo / "secret.py").write_text("def should_not_be_indexed(): pass\n")
    (repo / ".gitignore").write_text("secret.py\n")
    base = str(tmp_path / ".codeindex")
    result = run_loci("index", str(repo), env_extra={"LOCI_BASE_DIR": base})
    assert result.returncode == 0, result.stderr
    data = json.loads(result.stdout)
    search = run_loci("search", "should_not_be_indexed", "--repo", str(repo), env_extra={"LOCI_BASE_DIR": base})
    names = [r["name"] for r in json.loads(search.stdout)]
    assert "should_not_be_indexed" not in names
    # sample.py symbols still indexed
    assert data["symbols_indexed"] > 0


def test_index_exits_zero(sample_repo: Path, tmp_path: Path):
    result = run_loci("index", str(sample_repo), env_extra={"LOCI_BASE_DIR": str(tmp_path / ".codeindex")})
    assert result.returncode == 0, result.stderr


def test_index_outputs_json(sample_repo: Path, tmp_path: Path):
    result = run_loci("index", str(sample_repo), env_extra={"LOCI_BASE_DIR": str(tmp_path / ".codeindex")})
    data = json.loads(result.stdout)
    assert "symbols_indexed" in data
    assert data["symbols_indexed"] > 0


def test_index_reports_language_counts(sample_repo: Path, tmp_path: Path):
    result = run_loci("index", str(sample_repo), env_extra={"LOCI_BASE_DIR": str(tmp_path / ".codeindex")})
    data = json.loads(result.stdout)
    assert "languages" in data
    assert data["languages"].get("python", 0) > 0


def test_index_incremental_skips_unchanged(sample_repo: Path, tmp_path: Path):
    base = str(tmp_path / ".codeindex")
    run_loci("index", str(sample_repo), env_extra={"LOCI_BASE_DIR": base})
    result = run_loci("index", str(sample_repo), "--incremental", env_extra={"LOCI_BASE_DIR": base})
    data = json.loads(result.stdout)
    assert data.get("files_skipped", 0) > 0


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


@pytest.fixture
def indexed_repo(sample_repo: Path, tmp_path: Path) -> tuple[Path, str]:
    base = str(tmp_path / ".codeindex")
    run_loci("index", str(sample_repo), env_extra={"LOCI_BASE_DIR": base})
    return sample_repo, base


def test_search_returns_json_array(indexed_repo):
    repo, base = indexed_repo
    result = run_loci("search", "add", "--repo", str(repo), env_extra={"LOCI_BASE_DIR": base})
    assert result.returncode == 0, result.stderr
    data = json.loads(result.stdout)
    assert isinstance(data, list)


def test_search_finds_function(indexed_repo):
    repo, base = indexed_repo
    result = run_loci("search", "add", "--repo", str(repo), env_extra={"LOCI_BASE_DIR": base})
    data = json.loads(result.stdout)
    names = [r["name"] for r in data]
    assert "add" in names


def test_search_respects_limit(indexed_repo):
    repo, base = indexed_repo
    result = run_loci("search", "calculator", "--repo", str(repo), "--limit", "1", env_extra={"LOCI_BASE_DIR": base})
    data = json.loads(result.stdout)
    assert len(data) <= 1


def test_search_filters_by_kind(indexed_repo):
    repo, base = indexed_repo
    result = run_loci("search", "calculator", "--repo", str(repo), "--kind", "class", env_extra={"LOCI_BASE_DIR": base})
    data = json.loads(result.stdout)
    assert all(r["kind"] == "class" for r in data)


def test_get_returns_source(indexed_repo):
    repo, base = indexed_repo
    search_result = run_loci("search", "add", "--repo", str(repo), env_extra={"LOCI_BASE_DIR": base})
    symbols = json.loads(search_result.stdout)
    sym_id = next(s["id"] for s in symbols if s["name"] == "add")

    result = run_loci("get", sym_id, "--repo", str(repo), env_extra={"LOCI_BASE_DIR": base})
    assert result.returncode == 0, result.stderr
    data = json.loads(result.stdout)
    assert "source" in data
    assert "def add" in data["source"]


def test_get_unknown_id_returns_error(indexed_repo):
    repo, base = indexed_repo
    result = run_loci("get", "nonexistent::id#function", "--repo", str(repo), env_extra={"LOCI_BASE_DIR": base})
    assert result.returncode != 0


def test_list_returns_indexed_repos(indexed_repo):
    repo, base = indexed_repo
    result = run_loci("list", env_extra={"LOCI_BASE_DIR": base})
    assert result.returncode == 0
    data = json.loads(result.stdout)
    assert isinstance(data, list)
    assert len(data) >= 1
    paths = [r.get("path", "") for r in data]
    assert any(str(repo) in p for p in paths)


def test_invalidate_removes_cache(indexed_repo):
    repo, base = indexed_repo
    result = run_loci("invalidate", str(repo), env_extra={"LOCI_BASE_DIR": base})
    assert result.returncode == 0
    from loci.storage.index_store import IndexStore
    store = IndexStore(base_dir=Path(base))
    assert store.load(repo) is None


def test_summarize_outputs_unsummarized(indexed_repo):
    repo, base = indexed_repo
    result = run_loci("summarize", str(repo), env_extra={"LOCI_BASE_DIR": base})
    assert result.returncode == 0
    data = json.loads(result.stdout)
    assert isinstance(data, list)
    assert all(not s.get("summary") for s in data)


def test_outline_returns_files_with_symbols(indexed_repo):
    repo, base = indexed_repo
    result = run_loci("outline", str(repo), env_extra={"LOCI_BASE_DIR": base})
    assert result.returncode == 0, result.stderr
    data = json.loads(result.stdout)
    assert isinstance(data, list)
    assert len(data) >= 1
    entry = data[0]
    assert "file" in entry
    assert "symbols" in entry
    assert isinstance(entry["symbols"], list)
    assert len(entry["symbols"]) >= 1


def test_outline_symbol_has_expected_fields(indexed_repo):
    repo, base = indexed_repo
    result = run_loci("outline", str(repo), env_extra={"LOCI_BASE_DIR": base})
    data = json.loads(result.stdout)
    sym = data[0]["symbols"][0]
    assert "name" in sym
    assert "kind" in sym
    assert "signature" in sym
    assert "id" in sym


def test_outline_file_filter(indexed_repo):
    repo, base = indexed_repo
    result = run_loci("outline", str(repo), "--file", "sample.py", env_extra={"LOCI_BASE_DIR": base})
    assert result.returncode == 0, result.stderr
    data = json.loads(result.stdout)
    assert len(data) == 1
    assert data[0]["file"] == "sample.py"


def test_outline_file_filter_unknown_returns_empty(indexed_repo):
    repo, base = indexed_repo
    result = run_loci("outline", str(repo), "--file", "nonexistent.py", env_extra={"LOCI_BASE_DIR": base})
    assert result.returncode == 0
    data = json.loads(result.stdout)
    assert data == []


def test_outline_unindexed_repo_returns_error(tmp_path):
    result = run_loci("outline", str(tmp_path / "norepo"), env_extra={"LOCI_BASE_DIR": str(tmp_path / ".ci")})
    assert result.returncode != 0


def test_stats_empty_session_returns_zeros(tmp_path):
    base = str(tmp_path / ".codeindex")
    result = run_loci("stats", env_extra={"LOCI_BASE_DIR": base})
    assert result.returncode == 0, result.stderr
    data = json.loads(result.stdout)
    assert data["total_gets"] == 0
    assert data["symbol_bytes_retrieved"] == 0
    assert data["file_bytes_not_loaded"] == 0
    assert data["tokens_not_loaded"] == 0


def test_stats_accumulates_after_get(indexed_repo):
    repo, base = indexed_repo
    search_result = run_loci("search", "add", "--repo", str(repo), env_extra={"LOCI_BASE_DIR": base})
    sym_id = next(s["id"] for s in json.loads(search_result.stdout) if s["name"] == "add")

    run_loci("get", sym_id, "--repo", str(repo), env_extra={"LOCI_BASE_DIR": base})

    result = run_loci("stats", env_extra={"LOCI_BASE_DIR": base})
    data = json.loads(result.stdout)
    assert data["total_gets"] == 1
    assert data["symbol_bytes_retrieved"] > 0
    assert data["file_bytes_not_loaded"] >= 0
    assert data["tokens_not_loaded"] >= 0


def test_stats_reset_clears_session(indexed_repo):
    repo, base = indexed_repo
    search_result = run_loci("search", "add", "--repo", str(repo), env_extra={"LOCI_BASE_DIR": base})
    sym_id = next(s["id"] for s in json.loads(search_result.stdout) if s["name"] == "add")
    run_loci("get", sym_id, "--repo", str(repo), env_extra={"LOCI_BASE_DIR": base})

    run_loci("stats", "--reset", env_extra={"LOCI_BASE_DIR": base})

    result = run_loci("stats", env_extra={"LOCI_BASE_DIR": base})
    data = json.loads(result.stdout)
    assert data["total_gets"] == 0


def test_stats_shows_savings_ratio(indexed_repo):
    repo, base = indexed_repo
    search_result = run_loci("search", "add", "--repo", str(repo), env_extra={"LOCI_BASE_DIR": base})
    sym_id = next(s["id"] for s in json.loads(search_result.stdout) if s["name"] == "add")
    run_loci("get", sym_id, "--repo", str(repo), env_extra={"LOCI_BASE_DIR": base})

    result = run_loci("stats", env_extra={"LOCI_BASE_DIR": base})
    data = json.loads(result.stdout)
    assert "savings_ratio" in data


def test_stats_pretty_shows_formatted_header(indexed_repo):
    repo, base = indexed_repo
    search_result = run_loci("search", "add", "--repo", str(repo), env_extra={"LOCI_BASE_DIR": base})
    sym_id = next(s["id"] for s in json.loads(search_result.stdout) if s["name"] == "add")
    run_loci("get", sym_id, "--repo", str(repo), env_extra={"LOCI_BASE_DIR": base})

    result = run_loci("stats", "--pretty", env_extra={"LOCI_BASE_DIR": base})
    assert result.returncode == 0
    assert "loci" in result.stdout
    assert "Savings" in result.stdout
    assert "Total gets" in result.stdout


def test_stats_pretty_shows_savings_meter(indexed_repo):
    repo, base = indexed_repo
    search_result = run_loci("search", "add", "--repo", str(repo), env_extra={"LOCI_BASE_DIR": base})
    sym_id = next(s["id"] for s in json.loads(search_result.stdout) if s["name"] == "add")
    run_loci("get", sym_id, "--repo", str(repo), env_extra={"LOCI_BASE_DIR": base})

    result = run_loci("stats", "--pretty", env_extra={"LOCI_BASE_DIR": base})
    assert "█" in result.stdout or "░" in result.stdout


def test_stats_pretty_shows_by_repo_section(indexed_repo):
    repo, base = indexed_repo
    search_result = run_loci("search", "add", "--repo", str(repo), env_extra={"LOCI_BASE_DIR": base})
    sym_id = next(s["id"] for s in json.loads(search_result.stdout) if s["name"] == "add")
    run_loci("get", sym_id, "--repo", str(repo), env_extra={"LOCI_BASE_DIR": base})

    result = run_loci("stats", "--pretty", env_extra={"LOCI_BASE_DIR": base})
    assert "By Repo" in result.stdout
    assert repo.name in result.stdout


def test_stats_repo_filter_shows_by_file(indexed_repo):
    repo, base = indexed_repo
    search_result = run_loci("search", "add", "--repo", str(repo), env_extra={"LOCI_BASE_DIR": base})
    sym_id = next(s["id"] for s in json.loads(search_result.stdout) if s["name"] == "add")
    run_loci("get", sym_id, "--repo", str(repo), env_extra={"LOCI_BASE_DIR": base})

    result = run_loci("stats", "--repo", str(repo), "--pretty", env_extra={"LOCI_BASE_DIR": base})
    assert "By File" in result.stdout
    assert "sample.py" in result.stdout


def test_stats_pretty_is_not_json(indexed_repo):
    repo, base = indexed_repo
    result = run_loci("stats", "--pretty", env_extra={"LOCI_BASE_DIR": base})
    assert result.returncode == 0
    with pytest.raises(json.JSONDecodeError):
        json.loads(result.stdout)


def test_summarize_apply_writes_summaries(indexed_repo, tmp_path):
    repo, base = indexed_repo
    result = run_loci("summarize", str(repo), env_extra={"LOCI_BASE_DIR": base})
    symbols = json.loads(result.stdout)
    assert len(symbols) > 0

    summaries = [{"id": s["id"], "summary": "Test summary."} for s in symbols]
    summaries_file = tmp_path / "summaries.json"
    summaries_file.write_text(json.dumps(summaries))

    result = run_loci("summarize", str(repo), "--apply", str(summaries_file), env_extra={"LOCI_BASE_DIR": base})
    assert result.returncode == 0

    result2 = run_loci("summarize", str(repo), env_extra={"LOCI_BASE_DIR": base})
    remaining = json.loads(result2.stdout)
    assert len(remaining) == 0


def test_file_returns_full_content(indexed_repo):
    repo, base = indexed_repo
    result = run_loci("file", "sample.py", "--repo", str(repo), env_extra={"LOCI_BASE_DIR": base})
    assert result.returncode == 0, result.stderr
    data = json.loads(result.stdout)
    assert data["file"] == "sample.py"
    assert "content" in data
    assert "def add" in data["content"]
    assert data["total_lines"] == 42
    assert data["start_line"] == 1
    assert data["end_line"] == 42
    assert "file_bytes" not in data


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


def test_get_batch_returns_array(indexed_repo):
    repo, base = indexed_repo
    # Get 2 IDs — Calculator class + the add function
    search_class = run_loci("search", "calculator", "--repo", str(repo), env_extra={"LOCI_BASE_DIR": base})
    search_fn = run_loci("search", "add", "--repo", str(repo), env_extra={"LOCI_BASE_DIR": base})
    class_id = next(s["id"] for s in json.loads(search_class.stdout) if s["name"] == "Calculator")
    fn_id = next(s["id"] for s in json.loads(search_fn.stdout) if s["name"] == "add")
    ids = [class_id, fn_id]
    assert len(ids) == 2, "Need at least 2 IDs"

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
    assert "source" in data[0]   # valid symbol first
    assert "error" in data[1]    # not-found second


def test_get_single_still_returns_object_not_array(indexed_repo):
    # Backwards compatibility: single ID must return a plain object, NOT an array
    repo, base = indexed_repo
    search = run_loci("search", "add", "--repo", str(repo), env_extra={"LOCI_BASE_DIR": base})
    sym_id = next(s["id"] for s in json.loads(search.stdout) if s["name"] == "add")

    result = run_loci("get", sym_id, "--repo", str(repo), env_extra={"LOCI_BASE_DIR": base})
    assert result.returncode == 0, result.stderr
    data = json.loads(result.stdout)
    assert isinstance(data, dict)   # NOT a list
    assert "source" in data


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
    assert any(f["issue"] == "name_not_in_bytes" for f in out["failed"])


def test_verify_detects_content_drift(tmp_path: Path, fixtures_dir: Path):
    """Modify the live file after indexing — verify should detect content_drift."""
    import shutil
    repo = tmp_path / "drift_repo"
    repo.mkdir()
    shutil.copy(fixtures_dir / "sample.py", repo / "sample.py")
    base = str(tmp_path / ".codeindex")

    run_loci("index", str(repo), env_extra={"LOCI_BASE_DIR": base})

    # Mutate the live file after indexing (simulate a file edit without re-index)
    live = repo / "sample.py"
    original = live.read_text()
    live.write_text(original.replace("def add(", "def add_modified("))

    result = run_loci("verify", str(repo), env_extra={"LOCI_BASE_DIR": base})
    assert result.returncode == 1
    out = json.loads(result.stdout)
    assert any(f["issue"] == "content_drift" for f in out["failed"])
