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
