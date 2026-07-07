from pathlib import Path
import json

import pytest

import loci.service as service_module
from loci.service import (
    LociError,
    analyze_usage,
    get_cached_file,
    get_symbols,
    grep_repo,
    index_repo,
    list_repos,
    outline_repo,
    search_symbols,
    session_stats,
    verify_repo,
)
from loci.storage.index_store import IndexStore


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


def test_service_incremental_reindexes_old_version_metadata(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    base = tmp_path / ".codeindex"
    monkeypatch.setenv("LOCI_BASE_DIR", str(base))
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "idea.md").write_text(
        "---\n"
        "title: Governed Hybrid Retrieval Pipeline\n"
        "tags: [retrieval-governance]\n"
        "description: Build bounded context packs.\n"
        "---\n\n"
        "# Governed Hybrid Retrieval Pipeline\n\n"
        "Body.\n",
        encoding="utf-8",
    )
    index_repo(repo, incremental=False)

    store = IndexStore(base_dir=base)
    index_path = store._index_path(repo.resolve())
    old_index = json.loads(index_path.read_text())
    old_index["schema_version"] = 2
    old_index["extractor_version"] = 2
    for symbol in old_index["symbols"]:
        symbol["metadata"] = {}
        symbol["summary"] = ""
        symbol["keywords"] = []
    index_path.write_text(json.dumps(old_index))

    indexed = index_repo(repo, incremental=True)
    loaded = store.load(repo.resolve())
    markdown_symbols = [s for s in loaded["symbols"] if s["language"] == "markdown"]

    assert indexed["files_skipped"] == 0
    assert markdown_symbols[0]["metadata"]["frontmatter"]["tags"] == ["retrieval-governance"]
    assert markdown_symbols[0]["metadata"]["markdown"]["span_kind"] == "page_root"


def test_service_markdown_outline_exposes_retrieval_cost_and_repo_relative_ids(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setenv("LOCI_BASE_DIR", str(tmp_path / ".codeindex"))
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "idea.md").write_text(
        "# Governed Hybrid Retrieval Pipeline\n\n"
        "Root body.\n\n"
        "## Proposed Graph Move\n\n"
        "Use page-level governance metadata to route bounded context.\n",
        encoding="utf-8",
    )
    index_repo(repo, incremental=False)

    outline = outline_repo(repo, file="idea.md")
    symbols = outline[0]["symbols"]
    root = next(s for s in symbols if s["name"] == "Governed Hybrid Retrieval Pipeline")
    child = next(s for s in symbols if s["name"] == "Proposed Graph Move")

    assert root["span_kind"] == "page_root"
    assert root["file_bytes"] > 0
    assert root["saved_pct"] >= 0
    assert child["span_kind"] == "section"
    assert child["saved_pct"] > root["saved_pct"]

    store = IndexStore(base_dir=tmp_path / ".codeindex")
    loaded = store.load(repo.resolve())
    loaded_child = next(s for s in loaded["symbols"] if s["name"] == "Proposed Graph Move")
    assert loaded_child["metadata"]["markdown"]["parent_id"] == root["id"]
    assert loaded_child["metadata"]["markdown"]["root_id"] == root["id"]


def test_service_markdown_search_exposes_match_scope_and_cost(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setenv("LOCI_BASE_DIR", str(tmp_path / ".codeindex"))
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "idea.md").write_text(
        "---\n"
        "title: Governed Hybrid Retrieval Pipeline\n"
        "category: Retrieval Governance\n"
        "tags: [retrieval-governance]\n"
        "description: Build bounded context packs.\n"
        "---\n\n"
        "# Governed Hybrid Retrieval Pipeline\n\n"
        "Root body.\n\n"
        "## Proposed Graph Move\n\n"
        "Use page-level governance metadata to route bounded context.\n",
        encoding="utf-8",
    )
    index_repo(repo, incremental=False)

    results = search_symbols(repo, "retrieval-governance", lang="markdown", limit=5)

    child = next(r for r in results if r["name"] == "Proposed Graph Move")
    assert child["span_kind"] == "section"
    assert child["saved_pct"] > 0
    assert "section_summary" in child["match_scope"]
    assert "inherited_page_frontmatter.tags" in child["match_scope"]


def test_service_session_stats_reads_codex_mcp_store_without_env(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    pytest.importorskip("tomllib")

    monkeypatch.delenv("LOCI_BASE_DIR", raising=False)
    codex_home = tmp_path / ".codex"
    mcp_store = tmp_path / "mcp-store"
    codex_home.mkdir()
    (codex_home / "config.toml").write_text(
        "[mcp_servers.loci]\n"
        "command = \"loci-mcp\"\n"
        "[mcp_servers.loci.env]\n"
        f"LOCI_BASE_DIR = \"{mcp_store}\"\n"
    )
    monkeypatch.setenv("CODEX_HOME", str(codex_home))
    IndexStore(base_dir=mcp_store).log_retrieval(
        "src/app.py::run#function",
        20,
        120,
        repo_path="/tmp/repo",
    )

    stats = session_stats()

    assert stats["total_gets"] == 1
    assert stats["store"]["base_dir"] == str(mcp_store)
    assert stats["store"]["source"] == "codex_mcp_config"


def test_service_analyze_includes_store_metadata(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("LOCI_BASE_DIR", str(tmp_path / ".codeindex"))

    result = analyze_usage(since_days=7)

    assert "summary" in result
    assert result["store"]["base_dir"] == str(tmp_path / ".codeindex")
    assert result["store"]["source"] == "env"


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


def test_service_verify_valid_markdown_synthetic_sections(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setenv("LOCI_BASE_DIR", str(tmp_path / ".codeindex"))
    repo = tmp_path / "markdown_repo"
    repo.mkdir()
    (repo / "doc.md").write_text(
        "Preamble before the first heading.\n\n"
        "# Real Heading\n\n"
        "Body.\n",
        encoding="utf-8",
    )
    (repo / "flat.md").write_text(
        "A headingless markdown note whose content does not name the file.\n",
        encoding="utf-8",
    )
    index_repo(repo, incremental=False)

    verification = verify_repo(repo)

    assert verification["failed"] == []


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
