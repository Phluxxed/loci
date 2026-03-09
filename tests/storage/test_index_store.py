import pytest
import json
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
