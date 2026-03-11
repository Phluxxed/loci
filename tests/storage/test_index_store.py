import pytest
import json
import time as time_module
from pathlib import Path
from loci.parser.symbols import Symbol
from loci.storage.index_store import IndexStore


@pytest.fixture
def store(tmp_path: Path) -> IndexStore:
    return IndexStore(base_dir=tmp_path / ".codeindex")


@pytest.fixture
def sample_symbols() -> list[Symbol]:
    return [
        Symbol(
            id="src/auth.py::login#function",
            name="login",
            qualified_name="login",
            kind="function",
            language="python",
            file_path="src/auth.py",
            byte_offset=10,
            byte_length=100,
            signature="def login(username: str) -> bool",
            docstring="Authenticate a user.",
            summary="",
        ),
        Symbol(
            id="src/auth.py::User#class",
            name="User",
            qualified_name="User",
            kind="class",
            language="python",
            file_path="src/auth.py",
            byte_offset=120,
            byte_length=200,
        ),
    ]


def test_store_write_creates_index_file(store: IndexStore, tmp_path: Path, sample_symbols):
    source_path = tmp_path / "repo"
    source_path.mkdir()
    (source_path / "src").mkdir()
    (source_path / "src" / "auth.py").write_text("def login(): pass\n\nclass User: pass")

    store.write(source_path, sample_symbols, file_hashes={"src/auth.py": "abc123"})

    index_file = store._index_path(source_path)
    assert index_file.exists()


def test_store_write_load_roundtrip(store: IndexStore, tmp_path: Path, sample_symbols):
    source_path = tmp_path / "repo"
    source_path.mkdir()
    (source_path / "src").mkdir()
    (source_path / "src" / "auth.py").write_text("def login(): pass\n\nclass User: pass")

    store.write(source_path, sample_symbols, file_hashes={"src/auth.py": "abc123"})
    loaded = store.load(source_path)

    assert loaded is not None
    assert len(loaded["symbols"]) == 2
    assert loaded["symbols"][0]["id"] == "src/auth.py::login#function"
    assert loaded["file_hashes"]["src/auth.py"] == "abc123"


def test_store_load_returns_none_if_missing(store: IndexStore, tmp_path: Path):
    assert store.load(tmp_path / "nonexistent") is None


def test_store_file_hash(store: IndexStore, tmp_path: Path):
    f = tmp_path / "sample.py"
    f.write_text("def hello(): pass")
    h1 = store.hash_file(f)
    h2 = store.hash_file(f)
    assert h1 == h2
    assert len(h1) == 64  # SHA-256 hex

    f.write_text("def hello(): return 1")
    h3 = store.hash_file(f)
    assert h1 != h3


def test_store_mirrors_source(store: IndexStore, tmp_path: Path, sample_symbols):
    source_path = tmp_path / "repo"
    source_path.mkdir()
    (source_path / "src").mkdir()
    (source_path / "src" / "auth.py").write_text("def login(): pass")

    store.write(source_path, sample_symbols, file_hashes={})

    mirror = store._sources_dir(source_path) / "src" / "auth.py"
    assert mirror.exists()
    assert "login" in mirror.read_text()


def test_store_atomic_write(store: IndexStore, tmp_path: Path, sample_symbols):
    source_path = tmp_path / "repo"
    source_path.mkdir()
    (source_path / "src").mkdir()
    (source_path / "src" / "auth.py").write_text("def login(): pass")

    store.write(source_path, sample_symbols, file_hashes={})
    index_file = store._index_path(source_path)
    # Verify it's valid JSON (not partial)
    data = json.loads(index_file.read_text())
    assert "symbols" in data


def test_get_symbol_content_returns_source(store: IndexStore, tmp_path: Path):
    source_path = tmp_path / "repo"
    source_path.mkdir()
    (source_path / "src").mkdir()
    source_text = "# header\ndef login(): pass\n\nclass User: pass\n"
    (source_path / "src" / "auth.py").write_text(source_text)

    source_bytes = source_text.encode()
    symbols = [
        Symbol(
            id="src/auth.py::login#function",
            name="login",
            qualified_name="login",
            kind="function",
            language="python",
            file_path="src/auth.py",
            byte_offset=source_bytes.index(b"def login"),
            byte_length=len(b"def login(): pass"),
        )
    ]
    store.write(source_path, symbols, file_hashes={})

    content = store.get_symbol_content(source_path, "src/auth.py::login#function")
    assert content is not None
    assert "def login" in content


def test_get_symbol_content_returns_none_for_missing_id(store: IndexStore, tmp_path: Path, sample_symbols):
    source_path = tmp_path / "repo"
    source_path.mkdir()
    (source_path / "src").mkdir()
    (source_path / "src" / "auth.py").write_text("def login(): pass")
    store.write(source_path, sample_symbols, file_hashes={})

    result = store.get_symbol_content(source_path, "src/auth.py::nonexistent#function")
    assert result is None


@pytest.fixture
def store_with_data(store: IndexStore, tmp_path: Path) -> tuple[IndexStore, Path]:
    source_path = tmp_path / "repo"
    source_path.mkdir()
    (source_path / "src").mkdir()
    (source_path / "src" / "auth.py").write_text("def login(): pass\n\nclass User: pass")
    (source_path / "src").mkdir(exist_ok=True)
    # Create utils.py too
    (source_path / "src" / "utils.py").write_text("def hash_password(): pass")

    symbols = [
        Symbol(
            id="src/auth.py::login#function",
            name="login",
            qualified_name="login",
            kind="function",
            language="python",
            file_path="src/auth.py",
            byte_offset=0,
            byte_length=20,
            signature="def login(username: str) -> bool",
            docstring="Authenticate a user by checking credentials.",
            summary="Validates username and password against the database.",
        ),
        Symbol(
            id="src/auth.py::User#class",
            name="User",
            qualified_name="User",
            kind="class",
            language="python",
            file_path="src/auth.py",
            byte_offset=22,
            byte_length=50,
            signature="class User",
            docstring="Represents an authenticated user.",
            summary="",
        ),
        Symbol(
            id="src/utils.py::hash_password#function",
            name="hash_password",
            qualified_name="hash_password",
            kind="function",
            language="python",
            file_path="src/utils.py",
            byte_offset=0,
            byte_length=80,
            signature="def hash_password(password: str) -> str",
            docstring="Hash a password using bcrypt.",
            summary="",
        ),
    ]
    store.write(source_path, symbols, file_hashes={})
    return store, source_path


def test_search_exact_name_match_scores_highest(store_with_data):
    store, path = store_with_data
    results = store.search(path, "login")
    assert results[0]["id"] == "src/auth.py::login#function"


def test_search_returns_list(store_with_data):
    store, path = store_with_data
    results = store.search(path, "user")
    assert isinstance(results, list)


def test_search_respects_limit(store_with_data):
    store, path = store_with_data
    results = store.search(path, "password", limit=1)
    assert len(results) <= 1


def test_search_filters_by_kind(store_with_data):
    store, path = store_with_data
    results = store.search(path, "user", kind="class")
    assert all(r["kind"] == "class" for r in results)


def test_search_filters_by_lang(store_with_data):
    store, path = store_with_data
    results = store.search(path, "login", lang="python")
    assert all(r["language"] == "python" for r in results)


def test_search_returns_score(store_with_data):
    store, path = store_with_data
    results = store.search(path, "login")
    assert all("score" in r for r in results)
    assert results[0]["score"] > 0


def test_search_empty_query_returns_all(store_with_data):
    store, path = store_with_data
    results = store.search(path, "")
    assert len(results) == 3


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
