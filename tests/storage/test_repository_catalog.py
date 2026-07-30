import json
from pathlib import Path

import pytest

import loci.storage.repository_catalog as catalog_module
from loci.parser.symbols import Symbol
from loci.storage.index_store import IndexStore
from loci.storage.repository_catalog import (
    CATALOG_FILE_NAME,
    PENDING_MUTATION_FILE_NAME,
    RepositoryCatalogError,
)
from loci.storage.store_layout import repository_cache_key


def _symbol(name: str) -> Symbol:
    return Symbol(
        id=f"src/example.py::{name}#function",
        name=name,
        qualified_name=name,
        kind="function",
        language="python",
        file_path="src/example.py",
        byte_offset=0,
        byte_length=10,
    )


def _repo(tmp_path: Path, name: str = "repo") -> Path:
    repo = tmp_path / name
    source = repo / "src" / "example.py"
    source.parent.mkdir(parents=True)
    source.write_text("def example():\n    return 1\n")
    return repo


def test_list_repos_reads_catalog_without_reading_repository_indexes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = IndexStore(base_dir=tmp_path / "store")
    repo = _repo(tmp_path)
    store.write(repo, [_symbol("example")], file_hashes={})
    expected_path = str(repo.resolve())
    expected_cache_key = repository_cache_key(repo)
    original_read_text = Path.read_text

    def guarded_read_text(path: Path, *args, **kwargs):
        if path.name == "index.json":
            raise AssertionError("normal inventory must not read repository indexes")
        return original_read_text(path, *args, **kwargs)

    def resolve_forbidden(*_args, **_kwargs):
        raise AssertionError("normal inventory must not resolve repository roots")

    monkeypatch.setattr(Path, "read_text", guarded_read_text)
    monkeypatch.setattr(Path, "resolve", resolve_forbidden)

    assert store.list_repos() == [{
        "cache_key": expected_cache_key,
        "symbols": 1,
        "path": expected_path,
    }]


def test_interrupted_write_is_visible_and_repair_converges_to_new_index(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = IndexStore(base_dir=tmp_path / "store")
    repo = _repo(tmp_path)
    store.write(repo, [_symbol("old")], file_hashes={})
    original_catalog = json.loads(
        (store.base_dir / CATALOG_FILE_NAME).read_text()
    )
    original_replace = catalog_module.os.replace

    def fail_catalog_replace(source, destination):
        if Path(destination).name == CATALOG_FILE_NAME:
            raise OSError("simulated catalog replacement failure")
        return original_replace(source, destination)

    monkeypatch.setattr(catalog_module.os, "replace", fail_catalog_replace)

    with pytest.raises(OSError, match="replacement failure"):
        store.write(repo, [_symbol("old"), _symbol("new")], file_hashes={})

    with pytest.raises(RepositoryCatalogError) as exc_info:
        store.list_repos()
    assert exc_info.value.code == "REPOSITORY_CATALOG_REPAIR_REQUIRED"
    assert json.loads(
        (store.base_dir / CATALOG_FILE_NAME).read_text()
    ) == original_catalog

    monkeypatch.undo()
    repaired = store.repair_catalog()

    assert repaired["repositories"] == 1
    assert store.list_repos()[0]["symbols"] == 2


def test_interrupted_invalidation_is_visible_and_repair_converges_to_absence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = IndexStore(base_dir=tmp_path / "store")
    repo = _repo(tmp_path)
    store.write(repo, [_symbol("example")], file_hashes={})

    def fail_catalog_commit(_entries):
        raise OSError("simulated catalog replacement failure")

    monkeypatch.setattr(store._catalog, "commit", fail_catalog_commit)

    with pytest.raises(OSError, match="replacement failure"):
        store.invalidate(repo)

    with pytest.raises(RepositoryCatalogError):
        store.list_repos()

    monkeypatch.undo()
    repaired = store.repair_catalog()

    assert repaired["repositories"] == 0
    assert store.list_repos() == []


def test_corrupt_catalog_has_explicit_repeatable_repair(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = IndexStore(base_dir=tmp_path / "store")
    repo = _repo(tmp_path)
    store.write(repo, [_symbol("example")], file_hashes={})
    (store.base_dir / CATALOG_FILE_NAME).write_text("{not json")

    with pytest.raises(RepositoryCatalogError) as exc_info:
        store.list_repos()
    assert exc_info.value.code == "REPOSITORY_CATALOG_REPAIR_REQUIRED"

    def legacy_parse_forbidden(*_args, **_kwargs):
        raise AssertionError("valid repository metadata should avoid legacy parsing")

    monkeypatch.setattr(store._catalog, "_read_legacy_index_metadata", legacy_parse_forbidden)

    first = store.repair_catalog()
    second = store.repair_catalog()

    assert first["repositories"] == 1
    assert second["repositories"] == 1
    assert store.list_repos()[0]["path"] == str(repo.resolve())


def test_partial_pending_marker_forces_index_backed_recovery(tmp_path: Path) -> None:
    store = IndexStore(base_dir=tmp_path / "store")
    repo = _repo(tmp_path)
    store.write(repo, [_symbol("example")], file_hashes={})
    (store.base_dir / PENDING_MUTATION_FILE_NAME).write_text("{")

    with pytest.raises(RepositoryCatalogError):
        store.list_repos()

    repaired = store.repair_catalog()

    assert repaired["legacy_indexes_scanned"] == 1
    assert store.list_repos()[0]["symbols"] == 1


def test_repair_serializes_inventory_snapshot_before_scanning(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = IndexStore(base_dir=tmp_path / "store")
    original_repository_directories = store._catalog._repository_directories

    def guarded_repository_directories():
        assert (store.base_dir / PENDING_MUTATION_FILE_NAME).exists()
        return original_repository_directories()

    monkeypatch.setattr(
        store._catalog,
        "_repository_directories",
        guarded_repository_directories,
    )

    assert store.repair_catalog()["repositories"] == 0
    assert not (store.base_dir / PENDING_MUTATION_FILE_NAME).exists()


def test_legacy_store_requires_bounded_repair_before_listing(tmp_path: Path) -> None:
    base_dir = tmp_path / "legacy-store"
    repo = _repo(tmp_path)
    repo_dir = base_dir / repository_cache_key(repo)
    repo_dir.mkdir(parents=True)
    (repo_dir / "index.json").write_text(json.dumps({
        "symbols": [
            {"id": "src/example.py::one#function"},
            {"id": "src/example.py::two#function"},
        ],
        "repo_path": str(repo.resolve()),
    }))
    store = IndexStore(base_dir=base_dir)

    with pytest.raises(RepositoryCatalogError):
        store.list_repos()

    with pytest.raises(RepositoryCatalogError) as exc_info:
        store.repair_catalog(max_repositories=0)
    assert exc_info.value.code == "REPOSITORY_CATALOG_REPAIR_LIMIT_EXCEEDED"
    assert not (base_dir / CATALOG_FILE_NAME).exists()
    assert not (base_dir / PENDING_MUTATION_FILE_NAME).exists()

    repaired = store.repair_catalog(max_repositories=1, max_total_index_bytes=4096)

    assert repaired["repositories"] == 1
    assert repaired["legacy_indexes_scanned"] == 1
    assert store.list_repos() == [{
        "cache_key": repository_cache_key(repo),
        "symbols": 2,
        "path": str(repo.resolve()),
    }]


def test_legacy_repair_refuses_to_cross_index_byte_budget(tmp_path: Path) -> None:
    base_dir = tmp_path / "legacy-store"
    repo = _repo(tmp_path)
    repo_dir = base_dir / repository_cache_key(repo)
    repo_dir.mkdir(parents=True)
    index_path = repo_dir / "index.json"
    index_path.write_text(json.dumps({
        "symbols": [{"id": "src/example.py::one#function"}],
        "repo_path": str(repo.resolve()),
    }))
    store = IndexStore(base_dir=base_dir)

    with pytest.raises(RepositoryCatalogError) as exc_info:
        store.repair_catalog(max_total_index_bytes=index_path.stat().st_size - 1)

    assert exc_info.value.code == "REPOSITORY_CATALOG_REPAIR_LIMIT_EXCEEDED"
    assert not (base_dir / CATALOG_FILE_NAME).exists()
    assert not (base_dir / PENDING_MUTATION_FILE_NAME).exists()
