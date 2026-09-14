import json
import multiprocessing
import shutil
import threading
from pathlib import Path

import pytest

import loci.storage.repository_catalog as catalog_module
from loci.parser.symbols import Symbol
from loci.storage.index_store import IndexStore
from loci.storage.repository_catalog import (
    CATALOG_FILE_NAME,
    PENDING_MUTATION_FILE_NAME,
    RepositoryCatalog,
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


def _write_in_process(
    base_dir: str,
    repo: str,
    name: str,
    owner_ready,
    owner_release,
    waiter_ready,
    errors,
    *,
    pause_after_metadata: bool,
) -> None:
    try:
        store = IndexStore(base_dir=Path(base_dir))
        if pause_after_metadata:
            original_write_metadata = store._catalog.write_repository_metadata

            def pause_write_metadata(entry):
                original_write_metadata(entry)
                owner_ready.set()
                if not owner_release.wait(10):
                    raise TimeoutError("timed out waiting to release catalog owner")

            store._catalog.write_repository_metadata = pause_write_metadata
        else:
            original_acquire_lock = store._catalog._acquire_lock

            def observe_lock(*args, **kwargs):
                waiter_ready.set()
                return original_acquire_lock(*args, **kwargs)

            store._catalog._acquire_lock = observe_lock
        store.write(Path(repo), [_symbol(name)], file_hashes={})
    except BaseException as exc:
        errors.put((name, repr(exc)))
    else:
        errors.put((name, None))


def _repair_in_process(
    base_dir: str,
    name: str,
    scan_started,
    scan_release,
    errors,
    *,
    pause_before_scan: bool,
) -> None:
    try:
        catalog = RepositoryCatalog(Path(base_dir))
        original_directories = catalog._repository_directories

        def observe_directories():
            scan_started.set()
            if pause_before_scan and not scan_release.wait(10):
                raise TimeoutError("timed out waiting to release repair")
            return original_directories()

        catalog._repository_directories = observe_directories
        catalog.repair()
    except BaseException as exc:
        errors.put((name, repr(exc)))
    else:
        errors.put((name, None))


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


def test_legacy_pending_marker_still_requires_explicit_repair(tmp_path: Path) -> None:
    store = IndexStore(base_dir=tmp_path / "store")
    repo = _repo(tmp_path)
    store.write(repo, [_symbol("example")], file_hashes={})
    (store.base_dir / PENDING_MUTATION_FILE_NAME).write_text(json.dumps({
        "schema_version": 1,
        "operation": "write",
        "cache_key": repository_cache_key(repo),
    }))

    with pytest.raises(RepositoryCatalogError) as exc_info:
        store.list_repos()
    assert exc_info.value.code == "REPOSITORY_CATALOG_REPAIR_REQUIRED"


def test_only_mutation_owner_can_finish_marker(tmp_path: Path) -> None:
    catalog = RepositoryCatalog(tmp_path / "store")
    catalog.base_dir.mkdir()
    owner_token = catalog.begin_mutation("write", "owner")

    with pytest.raises(RepositoryCatalogError) as exc_info:
        catalog.finish_mutation("not-the-owner")
    assert exc_info.value.code == "REPOSITORY_CATALOG_MUTATION_OWNER_MISMATCH"
    assert catalog.pending_path.exists()

    catalog.finish_mutation(owner_token)
    assert not catalog.pending_path.exists()


def test_live_mutation_is_busy_after_bounded_wait(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    catalog = RepositoryCatalog(tmp_path / "store")
    catalog.base_dir.mkdir()
    monkeypatch.setattr(catalog_module, "DEFAULT_LIVE_MUTATION_WAIT_SECONDS", 0.01)
    monkeypatch.setattr(catalog_module, "LIVE_MUTATION_POLL_SECONDS", 0.001)
    owner_token = catalog.begin_mutation("write", "owner")

    with pytest.raises(RepositoryCatalogError) as exc_info:
        catalog.entries_for_mutation()
    assert exc_info.value.code == "REPOSITORY_CATALOG_BUSY"

    with pytest.raises(RepositoryCatalogError) as exc_info:
        catalog.repair()
    assert exc_info.value.code == "REPOSITORY_CATALOG_BUSY"
    assert catalog.pending_path.exists()

    catalog.finish_mutation(owner_token)


def test_reader_waits_across_marker_publication_and_owner_release(
    tmp_path: Path,
) -> None:
    base_dir = tmp_path / "store"
    base_dir.mkdir()
    owner = RepositoryCatalog(base_dir)
    reader = RepositoryCatalog(base_dir)
    publication_started = threading.Event()
    allow_publication = threading.Event()
    mutation_started = threading.Event()
    reader_started = threading.Event()
    reader_finished = threading.Event()
    token: list[str] = []
    results: list[object] = []
    original_publish = owner._publish_marker

    def pause_publication(marker):
        publication_started.set()
        assert allow_publication.wait(10)
        original_publish(marker)

    def begin_owner() -> None:
        token.append(owner.begin_mutation("write", "owner"))
        mutation_started.set()

    def read_catalog() -> None:
        reader_started.set()
        try:
            results.append(reader.entries_for_mutation())
        except BaseException as exc:
            results.append(exc)
        finally:
            reader_finished.set()

    owner._publish_marker = pause_publication
    owner_thread = threading.Thread(target=begin_owner)
    owner_thread.start()
    assert publication_started.wait(10)
    reader_thread = threading.Thread(target=read_catalog)
    reader_thread.start()
    assert reader_started.wait(10)
    assert not reader_finished.wait(0.1)
    allow_publication.set()
    assert mutation_started.wait(10)
    owner.finish_mutation(token[0])
    assert reader_finished.wait(10)
    owner_thread.join(10)
    reader_thread.join(10)

    assert results == [{}]


def test_concurrent_process_writes_wait_and_preserve_both_catalog_entries(
    tmp_path: Path,
) -> None:
    base_dir = tmp_path / "store"
    first_repo = _repo(tmp_path, "first")
    second_repo = _repo(tmp_path, "second")
    context = multiprocessing.get_context("spawn")
    owner_ready = context.Event()
    owner_release = context.Event()
    waiter_ready = context.Event()
    errors = context.Queue()
    first = context.Process(
        target=_write_in_process,
        args=(
            str(base_dir), str(first_repo), "first", owner_ready, owner_release,
            waiter_ready, errors,
        ),
        kwargs={"pause_after_metadata": True},
    )
    second = context.Process(
        target=_write_in_process,
        args=(
            str(base_dir), str(second_repo), "second", owner_ready, owner_release,
            waiter_ready, errors,
        ),
        kwargs={"pause_after_metadata": False},
    )
    first.start()
    assert owner_ready.wait(10)
    second.start()
    assert waiter_ready.wait(10)
    owner_release.set()
    first.join(10)
    second.join(10)

    assert first.exitcode == 0
    assert second.exitcode == 0
    assert sorted(errors.get(timeout=1) for _ in range(2)) == [
        ("first", None),
        ("second", None),
    ]
    assert {
        (entry["cache_key"], entry["symbols"], entry["path"])
        for entry in IndexStore(base_dir=base_dir).list_repos()
    } == {
        (repository_cache_key(first_repo), 1, str(first_repo.resolve())),
        (repository_cache_key(second_repo), 1, str(second_repo.resolve())),
    }


def test_concurrent_repairs_serialize_an_inherited_marker(tmp_path: Path) -> None:
    base_dir = tmp_path / "store"
    repo = _repo(tmp_path)
    store = IndexStore(base_dir=base_dir)
    store.write(repo, [_symbol("example")], file_hashes={})
    (base_dir / PENDING_MUTATION_FILE_NAME).write_text("{")
    context = multiprocessing.get_context("spawn")
    first_scan_started = context.Event()
    second_scan_started = context.Event()
    release_first = context.Event()
    errors = context.Queue()
    first = context.Process(
        target=_repair_in_process,
        args=(
            str(base_dir), "first", first_scan_started, release_first, errors,
        ),
        kwargs={"pause_before_scan": True},
    )
    second = context.Process(
        target=_repair_in_process,
        args=(
            str(base_dir), "second", second_scan_started, release_first, errors,
        ),
        kwargs={"pause_before_scan": False},
    )
    first.start()
    assert first_scan_started.wait(10)
    second.start()
    assert not second_scan_started.wait(0.1)
    release_first.set()
    first.join(10)
    second.join(10)

    assert first.exitcode == 0
    assert second.exitcode == 0
    assert sorted(errors.get(timeout=1) for _ in range(2)) == [
        ("first", None),
        ("second", None),
    ]
    assert IndexStore(base_dir=base_dir).list_repos() == [{
        "cache_key": repository_cache_key(repo),
        "symbols": 1,
        "path": str(repo.resolve()),
    }]


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
