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
        for key, value in env_extra.items():
            if value is None:
                env.pop(key, None)
            else:
                env[key] = value
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


def test_index_skips_uv_cache_directories(tmp_path: Path):
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "sample.py").write_text("def should_be_indexed(): pass\n")
    uv_cache = repo / "debug" / "uv-cache" / "archive-v0" / "package"
    uv_cache.mkdir(parents=True)
    (uv_cache / "cached_dependency.py").write_text("def should_not_be_indexed(): pass\n")

    base = str(tmp_path / ".codeindex")
    result = run_loci("index", str(repo), env_extra={"LOCI_BASE_DIR": base})

    assert result.returncode == 0, result.stderr
    search = run_loci("search", "should_not_be_indexed", "--repo", str(repo), env_extra={"LOCI_BASE_DIR": base})
    names = [r["name"] for r in json.loads(search.stdout)]
    assert "should_not_be_indexed" not in names


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


def test_search_finds_markdown_frontmatter_tag(tmp_path: Path):
    repo = tmp_path / "wiki_repo"
    repo.mkdir()
    (repo / "ideas").mkdir()
    (repo / "_templates").mkdir()
    (repo / "ideas" / "governed-hybrid-retrieval-pipeline.md").write_text(
        "---\n"
        "title: Governed Hybrid Retrieval Pipeline\n"
        "type: ideas\n"
        "category: Retrieval Governance\n"
        "description: Build bounded graph/vector context packs.\n"
        "tags:\n"
        "  - retrieval-governance\n"
        "  - context-packs\n"
        "---\n\n"
        "# Governed Hybrid Retrieval Pipeline\n\n"
        "Body.\n",
        encoding="utf-8",
    )
    (repo / "_templates" / "idea.md").write_text(
        "---\n"
        "title: Idea Template\n"
        "category: Retrieval Governance\n"
        "tags: [retrieval-governance]\n"
        "---\n\n"
        "# Idea Template\n\n"
        "Template body.\n",
        encoding="utf-8",
    )
    base = str(tmp_path / ".codeindex")

    index = run_loci("index", str(repo), env_extra={"LOCI_BASE_DIR": base})
    result = run_loci(
        "search",
        "retrieval-governance",
        "--repo",
        str(repo),
        "--lang",
        "markdown",
        env_extra={"LOCI_BASE_DIR": base},
    )
    data = json.loads(result.stdout)

    assert index.returncode == 0, index.stderr
    assert result.returncode == 0, result.stderr
    assert data[0]["file_path"] == "ideas/governed-hybrid-retrieval-pipeline.md"
    assert data[0]["metadata"]["frontmatter"]["tags"] == [
        "retrieval-governance",
        "context-packs",
    ]
    assert data[0]["span_kind"] == "page_root"
    assert data[0]["saved_pct"] >= 0
    assert data[0]["file_bytes"] > 0
    assert "page_frontmatter.tags" in data[0]["match_scope"]


def test_outline_exposes_markdown_retrieval_cost(tmp_path: Path):
    repo = tmp_path / "wiki_repo"
    repo.mkdir()
    (repo / "README.md").write_text(
        "# Title\n\n"
        "Intro.\n\n"
        "## Usage\n\n"
        "Use bounded section retrieval.\n",
        encoding="utf-8",
    )
    base = str(tmp_path / ".codeindex")

    index = run_loci("index", str(repo), env_extra={"LOCI_BASE_DIR": base})
    result = run_loci(
        "outline",
        str(repo),
        "--file",
        "README.md",
        env_extra={"LOCI_BASE_DIR": base},
    )
    data = json.loads(result.stdout)
    symbols = data[0]["symbols"]
    root = next(s for s in symbols if s["name"] == "Title")
    usage = next(s for s in symbols if s["name"] == "Usage")

    assert index.returncode == 0, index.stderr
    assert result.returncode == 0, result.stderr
    assert root["span_kind"] == "page_root"
    assert usage["span_kind"] == "section"
    assert usage["saved_pct"] > root["saved_pct"]


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
    assert data["store"]["base_dir"] == base
    assert data["store"]["source"] == "env"


def test_cli_help_excludes_removed_agent_maintenance_commands():
    result = run_loci("--help")

    assert result.returncode == 0, result.stderr
    assert "summarize" not in result.stdout
    assert "analyze" not in result.stdout


def test_stats_without_env_prefers_codex_mcp_store(tmp_path):
    import pytest
    pytest.importorskip("tomllib")

    from loci.storage.index_store import IndexStore

    codex_home = tmp_path / ".codex"
    mcp_store = tmp_path / "mcp-store"
    codex_home.mkdir()
    (codex_home / "config.toml").write_text(
        "[mcp_servers.loci]\n"
        "command = \"loci-mcp\"\n"
        "[mcp_servers.loci.env]\n"
        f"LOCI_BASE_DIR = \"{mcp_store}\"\n"
    )
    store = IndexStore(base_dir=mcp_store)
    store.log_retrieval("src/app.py::run#function", 20, 120, repo_path="/tmp/repo")

    result = run_loci(
        "stats",
        env_extra={"CODEX_HOME": str(codex_home), "LOCI_BASE_DIR": None},
    )

    assert result.returncode == 0, result.stderr
    data = json.loads(result.stdout)
    assert data["total_gets"] == 1
    assert data["store"]["base_dir"] == str(mcp_store)
    assert data["store"]["source"] == "codex_mcp_config"


def test_stats_env_override_wins_over_codex_mcp_store(tmp_path):
    import pytest
    pytest.importorskip("tomllib")

    from loci.storage.index_store import IndexStore

    codex_home = tmp_path / ".codex"
    mcp_store = tmp_path / "mcp-store"
    override_store = tmp_path / "override-store"
    codex_home.mkdir()
    (codex_home / "config.toml").write_text(
        "[mcp_servers.loci]\n"
        "command = \"loci-mcp\"\n"
        "[mcp_servers.loci.env]\n"
        f"LOCI_BASE_DIR = \"{mcp_store}\"\n"
    )
    IndexStore(base_dir=mcp_store).log_retrieval(
        "src/app.py::run#function",
        20,
        120,
        repo_path="/tmp/repo",
    )

    result = run_loci(
        "stats",
        env_extra={
            "CODEX_HOME": str(codex_home),
            "LOCI_BASE_DIR": str(override_store),
        },
    )

    assert result.returncode == 0, result.stderr
    data = json.loads(result.stdout)
    assert data["total_gets"] == 0
    assert data["store"]["base_dir"] == str(override_store)
    assert data["store"]["source"] == "env"


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
    # Two side-by-side panels: a Code panel and a Markdown panel
    assert "Gets" in result.stdout
    assert "Code" in result.stdout
    assert "Markdown" in result.stdout


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


@pytest.fixture
def indexed_repo_with_docs(tmp_path: Path, fixtures_dir: Path) -> tuple[Path, str]:
    repo = tmp_path / "docrepo"
    repo.mkdir()
    import shutil
    shutil.copy(fixtures_dir / "sample.py", repo / "sample.py")
    (repo / "README.md").write_text(
        "# Title\n\nIntro.\n\n## Section A\n\nBody A.\n\n## Section B\n\nBody B.\n"
    )
    base = str(tmp_path / ".codeindex")
    run_loci("index", str(repo), env_extra={"LOCI_BASE_DIR": base})
    return repo, base


def _get_one_code_and_doc(repo: Path, base: str) -> tuple[str, str]:
    """Outline the repo and return (code_symbol_id, markdown_symbol_id).

    outline groups symbols by file, so the file extension tells us which
    bucket a symbol belongs to without needing a language field in the row.
    """
    outline = json.loads(
        run_loci("outline", str(repo), env_extra={"LOCI_BASE_DIR": base}).stdout
    )
    code_id = doc_id = None
    for f in outline:
        for s in f["symbols"]:
            if f["file"].endswith(".py") and code_id is None:
                code_id = s["id"]
            if f["file"].endswith(".md") and doc_id is None:
                doc_id = s["id"]
    assert code_id and doc_id, f"missing ids: {code_id=} {doc_id=}"
    return code_id, doc_id


def test_stats_splits_code_and_docs(indexed_repo_with_docs):
    repo, base = indexed_repo_with_docs
    code_id, doc_id = _get_one_code_and_doc(repo, base)
    run_loci("get", code_id, "--repo", str(repo), env_extra={"LOCI_BASE_DIR": base})
    run_loci("get", doc_id, "--repo", str(repo), env_extra={"LOCI_BASE_DIR": base})

    data = json.loads(run_loci("stats", env_extra={"LOCI_BASE_DIR": base}).stdout)
    # Combined totals stay (back-compat)
    assert data["total_gets"] == 2
    # Split summaries
    assert data["code"]["gets"] == 1
    assert data["docs"]["gets"] == 1
    # Separate doc table holds the markdown file; code file table excludes it
    assert data["by_doc"] and "README.md" in data["by_doc"][0]["name"]
    assert data["by_file_code"] and all(
        "README.md" not in r["name"] for r in data["by_file_code"]
    )
    assert any("sample.py" in r["name"] for r in data["by_file_code"])


def test_stats_groups_markdown_by_repo(indexed_repo_with_docs):
    repo, base = indexed_repo_with_docs
    _code_id, doc_id = _get_one_code_and_doc(repo, base)
    run_loci("get", doc_id, "--repo", str(repo), env_extra={"LOCI_BASE_DIR": base})

    data = json.loads(run_loci("stats", env_extra={"LOCI_BASE_DIR": base}).stdout)

    assert data["by_repo_doc"] == [{
        "name": str(repo),
        "gets": 1,
        "saved_bytes": data["by_doc"][0]["saved_bytes"],
        "ratio_pct": data["by_doc"][0]["ratio_pct"],
        "last_ts": data["by_doc"][0]["last_ts"],
    }]


def test_stats_outlines_split_by_language(indexed_repo_with_docs):
    repo, base = indexed_repo_with_docs
    # A whole-repo outline surfaces both python and markdown symbols, so it
    # counts toward both lanes.
    run_loci("outline", str(repo), env_extra={"LOCI_BASE_DIR": base})
    data = json.loads(run_loci("stats", env_extra={"LOCI_BASE_DIR": base}).stdout)
    assert data["total_outlines"] == 1
    assert data["code"]["outlines"] == 1
    assert data["docs"]["outlines"] == 1


def test_stats_outline_of_code_file_only_counts_code(indexed_repo_with_docs):
    repo, base = indexed_repo_with_docs
    run_loci("outline", str(repo), "--file", "sample.py",
             env_extra={"LOCI_BASE_DIR": base})
    data = json.loads(run_loci("stats", env_extra={"LOCI_BASE_DIR": base}).stdout)
    assert data["code"]["outlines"] == 1
    assert data["docs"]["outlines"] == 0


def test_stats_pretty_shows_doc_lane(indexed_repo_with_docs):
    repo, base = indexed_repo_with_docs
    code_id, doc_id = _get_one_code_and_doc(repo, base)
    run_loci("get", code_id, "--repo", str(repo), env_extra={"LOCI_BASE_DIR": base})
    run_loci("get", doc_id, "--repo", str(repo), env_extra={"LOCI_BASE_DIR": base})

    out = run_loci("stats", "--pretty", env_extra={"LOCI_BASE_DIR": base}).stdout
    assert "Code" in out and "Markdown" in out
    assert "By Repo (markdown)" in out
    assert repo.name in out
    assert "README.md" in out


def test_stats_file_read_of_markdown_lands_in_docs_lane(indexed_repo_with_docs):
    repo, base = indexed_repo_with_docs
    # A raw `loci file` read (not a section get) of a markdown file should still
    # be attributed to the docs lane via its extension.
    run_loci("file", "README.md", "--repo", str(repo), env_extra={"LOCI_BASE_DIR": base})

    data = json.loads(run_loci("stats", env_extra={"LOCI_BASE_DIR": base}).stdout)
    assert data["docs"]["gets"] == 1
    assert data["code"]["gets"] == 0
    assert data["by_doc"] and "README.md" in data["by_doc"][0]["name"]


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


def test_get_context_lines_returned(indexed_repo: tuple[Path, str]):
    """loci get --context N should include context_before and context_after."""
    repo, base = indexed_repo
    outline_result = run_loci("outline", str(repo), env_extra={"LOCI_BASE_DIR": base})
    sym_id = json.loads(outline_result.stdout)[0]["symbols"][0]["id"]

    result = run_loci("get", sym_id, "--repo", str(repo), "--context", "3",
                      env_extra={"LOCI_BASE_DIR": base})
    assert result.returncode == 0
    data = json.loads(result.stdout)
    assert "context_before" in data
    assert "context_after" in data
    assert isinstance(data["context_before"], list)
    assert isinstance(data["context_after"], list)


def test_get_no_context_by_default(indexed_repo: tuple[Path, str]):
    """loci get without --context should not include context keys."""
    repo, base = indexed_repo
    outline_result = run_loci("outline", str(repo), env_extra={"LOCI_BASE_DIR": base})
    sym_id = json.loads(outline_result.stdout)[0]["symbols"][0]["id"]

    result = run_loci("get", sym_id, "--repo", str(repo), env_extra={"LOCI_BASE_DIR": base})
    assert result.returncode == 0
    data = json.loads(result.stdout)
    assert "context_before" not in data
    assert "context_after" not in data


def test_decorators_extracted_for_decorated_function(tmp_path: Path, fixtures_dir: Path):
    """@decorator functions should have decorator names in symbol metadata."""
    import shutil
    repo = tmp_path / "dec_repo"
    repo.mkdir()
    shutil.copy(fixtures_dir / "sample.py", repo / "sample.py")
    base = str(tmp_path / ".codeindex")

    run_loci("index", str(repo), env_extra={"LOCI_BASE_DIR": base})
    outline = run_loci("outline", str(repo), env_extra={"LOCI_BASE_DIR": base})
    symbols = json.loads(outline.stdout)[0]["symbols"]

    # decorated_function has @decorator applied
    decorated = next((s for s in symbols if s["name"] == "decorated_function"), None)
    assert decorated is not None
    assert "decorators" in decorated
    assert "decorator" in decorated["decorators"]


def test_verify_clean_repo_passes(indexed_repo: tuple[Path, str]):
    repo, base = indexed_repo
    result = run_loci("verify", str(repo), env_extra={"LOCI_BASE_DIR": base})
    assert result.returncode == 0
    data = json.loads(result.stdout)
    assert data["checked"] > 0
    assert data["failed"] == []
    assert data["passed"] == data["checked"]
    assert data["repo"] == str(repo)


def test_verify_valid_markdown_synthetic_sections_pass(tmp_path: Path):
    repo = tmp_path / "markdown_repo"
    repo.mkdir()
    (repo / "doc.md").write_text(
        "---\n"
        "title: Markdown Doc\n"
        "---\n\n"
        "Preamble before the first heading.\n\n"
        "# Real Heading\n\n"
        "Body.\n",
        encoding="utf-8",
    )
    (repo / "flat.md").write_text(
        "A headingless markdown note whose content does not name the file.\n",
        encoding="utf-8",
    )
    base = str(tmp_path / ".codeindex")
    run_loci("index", str(repo), env_extra={"LOCI_BASE_DIR": base})

    result = run_loci("verify", str(repo), env_extra={"LOCI_BASE_DIR": base})
    data = json.loads(result.stdout)

    assert result.returncode == 0, result.stderr
    assert data["failed"] == []


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


def test_get_returns_line_numbers(sample_repo: Path, tmp_path: Path):
    base = str(tmp_path / ".codeindex")
    run_loci("index", str(sample_repo), env_extra={"LOCI_BASE_DIR": base})
    search = run_loci("search", "add", "--repo", str(sample_repo), env_extra={"LOCI_BASE_DIR": base})
    sym_id = next(r["id"] for r in json.loads(search.stdout) if r["name"] == "add")
    result = run_loci("get", sym_id, "--repo", str(sample_repo), env_extra={"LOCI_BASE_DIR": base})
    out = json.loads(result.stdout)
    assert out["line"] > 0
    assert out["end_line"] >= out["line"]


def test_outline_includes_line_numbers(sample_repo: Path, tmp_path: Path):
    base = str(tmp_path / ".codeindex")
    run_loci("index", str(sample_repo), env_extra={"LOCI_BASE_DIR": base})
    result = run_loci("outline", str(sample_repo), env_extra={"LOCI_BASE_DIR": base})
    symbols = json.loads(result.stdout)[0]["symbols"]
    assert all("line" in s and "end_line" in s for s in symbols)
    assert all(s["line"] > 0 for s in symbols)


def test_keywords_extracted_for_camel_case(tmp_path: Path):
    from loci.parser.extractor import parse_file
    f = tmp_path / "sample.py"
    f.write_text("def getUserById(user_id): pass\n")
    symbols = parse_file(f)
    assert len(symbols) == 1
    kws = set(symbols[0].keywords)
    assert "get" in kws
    assert "user" in kws
    assert "by" in kws
    assert "id" in kws


def test_keywords_boost_search(sample_repo: Path, tmp_path: Path):
    """A query matching a keyword should still score the symbol."""
    base = str(tmp_path / ".codeindex")
    run_loci("index", str(sample_repo), env_extra={"LOCI_BASE_DIR": base})
    # "multiply" name has keyword "multiply"; query "mult" won't exact-match but keyword helps
    result = run_loci("search", "multiply", "--repo", str(sample_repo), env_extra={"LOCI_BASE_DIR": base})
    names = [r["name"] for r in json.loads(result.stdout)]
    assert "multiply" in names


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


# ---------------------------------------------------------------------------
# Helpers for logging tests
# ---------------------------------------------------------------------------

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def _index_repo(repo: Path) -> str:
    """Create a minimal repo with sample.py and index it. Returns the base dir path."""
    import shutil
    repo.mkdir(parents=True, exist_ok=True)
    shutil.copy(FIXTURES_DIR / "sample.py", repo / "sample.py")
    base = str(repo.parent / ".idx")
    result = run_loci("index", str(repo), env_extra={"LOCI_BASE_DIR": base})
    assert result.returncode == 0, f"index failed: {result.stderr}"
    return base


# ---------------------------------------------------------------------------
# Logging tests: cmd_search
# ---------------------------------------------------------------------------

def test_cmd_search_logs_search_event(tmp_path: Path):
    """search with results writes a search event to session.jsonl."""
    repo = tmp_path / "repo"
    base = _index_repo(repo)
    run_loci("search", "--repo", str(repo), "add", env_extra={"LOCI_BASE_DIR": base})
    log_path = Path(base) / "session.jsonl"
    entries = [json.loads(l) for l in log_path.read_text().splitlines() if l.strip()]
    search_events = [e for e in entries if e.get("event") == "search"]
    assert len(search_events) == 1
    assert search_events[0]["query"] == "add"
    assert "search_id" in search_events[0]
    assert "result_ids" in search_events[0]


def test_cmd_search_logs_miss_on_empty_results(tmp_path: Path):
    """search with 0 results writes a miss event, NOT a search event."""
    repo = tmp_path / "repo"
    base = _index_repo(repo)
    run_loci("search", "--repo", str(repo), "zzz_nonexistent_xyz", env_extra={"LOCI_BASE_DIR": base})
    log_path = Path(base) / "session.jsonl"
    entries = [json.loads(l) for l in log_path.read_text().splitlines() if l.strip()]
    assert any(e.get("event") == "miss" and e["miss_type"] == "search_empty" for e in entries)
    assert all(e.get("event") != "search" for e in entries)


def test_cmd_search_empty_does_not_write_last_search(tmp_path: Path):
    """Empty search result must not write last_search.json (prevents false blind_spot)."""
    repo = tmp_path / "repo"
    base = _index_repo(repo)
    run_loci("search", "--repo", str(repo), "zzz_nonexistent_xyz", env_extra={"LOCI_BASE_DIR": base})
    assert not (Path(base) / "last_search.json").exists()


# ---------------------------------------------------------------------------
# Logging tests: cmd_get
# ---------------------------------------------------------------------------

def test_cmd_get_logs_kind_and_language(tmp_path: Path):
    """get command enriches the log entry with kind and language."""
    repo = tmp_path / "repo"
    base = _index_repo(repo)
    # Get a real symbol ID from the outline
    outline_result = run_loci("outline", str(repo), env_extra={"LOCI_BASE_DIR": base})
    symbols = json.loads(outline_result.stdout)
    symbol_id = symbols[0]["symbols"][0]["id"]
    run_loci("get", symbol_id, "--repo", str(repo), env_extra={"LOCI_BASE_DIR": base})
    log_path = Path(base) / "session.jsonl"
    entries = [json.loads(l) for l in log_path.read_text().splitlines() if l.strip()]
    get_events = [e for e in entries if e.get("event") == "get"]
    assert len(get_events) == 1
    assert get_events[0]["kind"] is not None
    assert get_events[0]["language"] is not None


def test_cmd_get_logs_miss_on_not_found(tmp_path: Path):
    """get on a missing symbol writes a miss event."""
    repo = tmp_path / "repo"
    base = _index_repo(repo)
    run_loci("get", "src/foo.py::nonexistent#function", "--repo", str(repo),
             env_extra={"LOCI_BASE_DIR": base})
    log_path = Path(base) / "session.jsonl"
    entries = [json.loads(l) for l in log_path.read_text().splitlines() if l.strip()]
    assert any(e.get("event") == "miss" and e["miss_type"] == "get_not_found" for e in entries)


def test_cmd_get_records_search_correlation(tmp_path: Path):
    """get after search records search_id on the get event."""
    repo = tmp_path / "repo"
    base = _index_repo(repo)
    # Get a real symbol ID from the outline
    outline_result = run_loci("outline", str(repo), env_extra={"LOCI_BASE_DIR": base})
    symbols = json.loads(outline_result.stdout)
    symbol_id = symbols[0]["symbols"][0]["id"]
    # Extract the bare name for the search query
    bare_name = symbol_id.split("::")[-1].split("#")[0]
    # Search first (ensure results), then get
    run_loci("search", "--repo", str(repo), bare_name, env_extra={"LOCI_BASE_DIR": base})
    run_loci("get", symbol_id, "--repo", str(repo), env_extra={"LOCI_BASE_DIR": base})
    log_path = Path(base) / "session.jsonl"
    entries = [json.loads(l) for l in log_path.read_text().splitlines() if l.strip()]
    get_events = [e for e in entries if e.get("event") == "get"]
    assert len(get_events) == 1
    assert get_events[0]["search_id"] is not None
