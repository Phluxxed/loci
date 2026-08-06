import json
import shutil
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


def test_store_open_automatically_removes_missing_root_cache_and_reports_summary(
    tmp_path: Path,
) -> None:
    base_dir = tmp_path / "store"
    dead_repo = _repo(tmp_path, "dead")
    live_repo = _repo(tmp_path, "live")
    store = IndexStore(base_dir=base_dir)
    store.write(dead_repo, [_symbol("dead")], file_hashes={})
    store.write(live_repo, [_symbol("live")], file_hashes={})

    dead_cache_dir = base_dir / repository_cache_key(dead_repo)
    dead_cache_bytes = sum(
        path.stat().st_size
        for path in dead_cache_dir.rglob("*")
        if path.is_file()
    )
    dead_repo_source = dead_repo / "src" / "example.py"
    live_repo_source = live_repo / "src" / "example.py"
    dead_repo_source.unlink()
    dead_repo_source.parent.rmdir()
    dead_repo.rmdir()
    original_live_source = live_repo_source.read_bytes()

    reopened = IndexStore(base_dir=base_dir)

    assert not dead_cache_dir.exists()
    assert reopened.list_repos() == [{
        "cache_key": repository_cache_key(live_repo),
        "symbols": 1,
        "path": str(live_repo.resolve()),
    }]
    assert live_repo_source.read_bytes() == original_live_source
    cleanup_events = [
        json.loads(line)
        for line in (base_dir / "session.jsonl").read_text().splitlines()
        if line.strip()
    ]
    assert cleanup_events[-1] == {
        "event": "store_cleanup",
        "removed_count": 1,
        "removed_bytes": dead_cache_bytes,
    }


def test_store_open_does_not_cleanup_while_catalog_mutation_is_pending(
    tmp_path: Path,
) -> None:
    base_dir = tmp_path / "store"
    repo = _repo(tmp_path)
    store = IndexStore(base_dir=base_dir)
    store.write(repo, [_symbol("example")], file_hashes={})
    repo_dir = base_dir / repository_cache_key(repo)
    repo_source = repo / "src" / "example.py"
    repo_source.unlink()
    repo_source.parent.rmdir()
    repo.rmdir()
    (base_dir / PENDING_MUTATION_FILE_NAME).write_text(
        json.dumps({
            "schema_version": 1,
            "operation": "write",
            "cache_key": repository_cache_key(repo),
        })
    )

    IndexStore(base_dir=base_dir)

    assert repo_dir.exists()
    assert (base_dir / PENDING_MUTATION_FILE_NAME).exists()


def test_interrupted_startup_cleanup_recovers_through_catalog_repair(
    tmp_path: Path,
) -> None:
    base_dir = tmp_path / "store"
    repo = _repo(tmp_path)
    store = IndexStore(base_dir=base_dir)
    store.write(repo, [_symbol("example")], file_hashes={})
    repo_dir = base_dir / repository_cache_key(repo)
    repo_source = repo / "src" / "example.py"
    repo_source.unlink()
    repo_source.parent.rmdir()
    repo.rmdir()
    (base_dir / PENDING_MUTATION_FILE_NAME).write_text(
        json.dumps({
            "schema_version": 1,
            "operation": "cleanup",
            "cache_key": repository_cache_key(repo),
        })
    )
    shutil.rmtree(repo_dir)

    reopened = IndexStore(base_dir=base_dir)
    repaired = reopened.repair_catalog()

    assert repaired["repositories"] == 0
    assert reopened.list_repos() == []
