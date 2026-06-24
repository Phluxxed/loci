from pathlib import Path

import pytest

import loci.service as service_module
from loci.service import (
    LociError,
    get_cached_file,
    get_symbols,
    grep_repo,
    index_repo,
    list_repos,
    outline_repo,
    search_symbols,
    verify_repo,
)


@pytest.fixture
def sample_repo(tmp_path: Path, fixtures_dir: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "sample.py").write_text((fixtures_dir / "sample.py").read_text())
    return repo


def test_service_index_outline_get_round_trip(sample_repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("LOCI_BASE_DIR", str(tmp_path / ".codeindex"))

    indexed = index_repo(sample_repo, incremental=False)
    outline = outline_repo(sample_repo)
    symbol_id = next(
        symbol["id"]
        for entry in outline
        for symbol in entry["symbols"]
        if symbol["name"] == "add"
    )
    results = get_symbols(sample_repo, [symbol_id], context=1)

    assert indexed["symbols_indexed"] > 0
    assert outline[0]["file"] == "sample.py"
    assert len(results) == 1
    assert results[0]["id"] == symbol_id
    assert "def add" in results[0]["source"]
    assert "context_before" in results[0]
    assert "context_after" in results[0]


def test_service_index_warns_on_short_nonempty_markdown_with_zero_symbols(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setenv("LOCI_BASE_DIR", str(tmp_path / ".codeindex"))
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "README.md").write_text("# Heading\n")
    monkeypatch.setattr(service_module, "parse_file", lambda path: [])

    indexed = index_repo(repo, incremental=False)

    assert indexed["warnings"] == [{
        "file": "README.md",
        "lines": 1,
        "reason": "0 symbols extracted",
    }]


def test_service_index_missing_path_raises_structured_error(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("LOCI_BASE_DIR", str(tmp_path / ".codeindex"))

    with pytest.raises(LociError) as exc_info:
        index_repo(tmp_path / "missing", incremental=False)

    assert exc_info.value.code == "PATH_NOT_FOUND"
    assert "path" in exc_info.value.details


def test_service_get_unknown_symbol_raises_structured_error(
    sample_repo: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setenv("LOCI_BASE_DIR", str(tmp_path / ".codeindex"))
    index_repo(sample_repo, incremental=False)

    with pytest.raises(LociError) as exc_info:
        get_symbols(sample_repo, ["sample.py::missing#function"])

    assert exc_info.value.code == "SYMBOL_NOT_FOUND"
    assert exc_info.value.details["symbol_id"] == "sample.py::missing#function"


def test_service_search_file_grep_verify_list(sample_repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("LOCI_BASE_DIR", str(tmp_path / ".codeindex"))
    index_repo(sample_repo, incremental=False)

    search_results = search_symbols(sample_repo, "add", limit=5)
    cached_file = get_cached_file(sample_repo, "sample.py", start_line=4, end_line=5)
    grep_results = grep_repo(sample_repo, r"def add")
    verification = verify_repo(sample_repo)
    repos = list_repos()

    assert any(result["name"] == "add" for result in search_results)
    assert cached_file["file"] == "sample.py"
    assert "def add" in cached_file["content"]
    assert any(result["file"] == "sample.py" for result in grep_results)
    assert verification["failed"] == []
    assert any(repo["path"] == str(sample_repo.resolve()) for repo in repos)


def test_service_invalid_grep_pattern_raises_structured_error(
    sample_repo: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setenv("LOCI_BASE_DIR", str(tmp_path / ".codeindex"))
    index_repo(sample_repo, incremental=False)

    with pytest.raises(LociError) as exc_info:
        grep_repo(sample_repo, "[")

    assert exc_info.value.code == "INVALID_REGEX"
