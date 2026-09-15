from __future__ import annotations

import sqlite3
import threading
from pathlib import Path

import pytest

from loci.graph.contracts import GraphContractError
from loci.storage.index_store import IndexStore
from loci.storage.source_refs import SourceRefStore, is_source_handle


def _store(tmp_path: Path, repo: Path, **limits: int) -> SourceRefStore:
    repo.mkdir(exist_ok=True)
    return SourceRefStore(repo, IndexStore(tmp_path / "cache"), **limits)


def _locator(repo: Path, *, offset: int = 0) -> dict[str, object]:
    return {
        "v": 1,
        "repo": str(repo.resolve()),
        "file": "src/example.py",
        "hash": "a" * 64,
        "start": 0,
        "end": 16,
        "offset": offset,
    }


def test_stage_does_not_create_cache_file(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    refs = _store(tmp_path, repo)

    handle = refs.stage(_locator(repo))

    assert is_source_handle(handle)
    assert len(handle) == 30
    assert not refs.path.exists()


def test_selective_flush_survives_reopen_and_returns_exact_locator(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    refs = _store(tmp_path, repo)
    first = _locator(repo)
    second = _locator(repo, offset=1)
    first_handle = refs.stage(first)
    refs.stage(second)

    refs.flush([first_handle])
    reopened = _store(tmp_path, repo)

    assert reopened.resolve(first_handle) == first
    with pytest.raises(GraphContractError) as absent:
        reopened.resolve(refs.stage(second))
    assert absent.value.code == "INVALID_SOURCE_REF"


def test_identity_includes_canonical_payload_repository_and_offset(tmp_path: Path) -> None:
    first_repo = tmp_path / "one"
    second_repo = tmp_path / "two"
    first = _store(tmp_path, first_repo)
    second = _store(tmp_path, second_repo)

    same = _locator(first_repo)
    assert first.stage(same) == first.stage(dict(reversed(list(same.items()))))
    assert first.stage(_locator(first_repo, offset=1)) != first.stage(same)
    assert second.stage(_locator(second_repo)) != first.stage(same)
    with pytest.raises(GraphContractError):
        first.stage(_locator(second_repo))


def test_unknown_and_corrupt_records_fail_closed(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    refs = _store(tmp_path, repo)
    locator = _locator(repo)
    handle = refs.stage(locator)
    refs.flush([handle])

    with pytest.raises(GraphContractError) as unknown:
        refs.resolve("sr1_aaaaaaaaaaaaaaaaaaaaaaaaaa")
    assert unknown.value.code == "INVALID_SOURCE_REF"

    with sqlite3.connect(refs.path) as connection:
        connection.execute("UPDATE source_refs SET payload = ? WHERE handle = ?", (b"[]", handle))
    with pytest.raises(GraphContractError) as corrupt:
        refs.resolve(handle)
    assert corrupt.value.code == "INVALID_SOURCE_REF"
    assert "Retrieve fresh" in corrupt.value.message


def test_collision_never_retargets_persisted_handle(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = tmp_path / "repo"
    refs = _store(tmp_path, repo)
    original = _locator(repo)
    handle = refs.stage(original)
    refs.flush([handle])

    monkeypatch.setattr("loci.storage.source_refs._handle_for", lambda _payload: handle)
    colliding = refs.stage(_locator(repo, offset=1))
    assert colliding == handle
    with pytest.raises(GraphContractError):
        refs.stage(_locator(repo, offset=2))
    with pytest.raises(GraphContractError) as collision:
        refs.flush([colliding])
    assert collision.value.code == "INVALID_SOURCE_REF"
    monkeypatch.undo()
    assert refs.resolve(handle) == original


def test_bounded_eviction_keeps_current_batch(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    refs = _store(tmp_path, repo, max_references=2, max_payload_bytes=10_000)
    first = refs.stage(_locator(repo))
    second = refs.stage(_locator(repo, offset=1))
    refs.flush([first, second])
    third_value = _locator(repo, offset=2)
    third = refs.stage(third_value)
    refs.flush([third])

    assert refs.resolve(third) == third_value
    retained = max(first, second)
    evicted = min(first, second)
    assert refs.resolve(retained)["offset"] in {0, 1}
    with pytest.raises(GraphContractError):
        refs.resolve(evicted)


def test_concurrent_flushes_preserve_both_selected_references(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    left = _store(tmp_path, repo)
    right = _store(tmp_path, repo)
    left_handle = left.stage(_locator(repo))
    right_handle = right.stage(_locator(repo, offset=1))
    barrier = threading.Barrier(2)
    failures: list[BaseException] = []

    def flush(refs: SourceRefStore, handle: str) -> None:
        try:
            barrier.wait()
            refs.flush([handle])
        except BaseException as exc:  # assertions below retain both failures
            failures.append(exc)

    left_thread = threading.Thread(target=flush, args=(left, left_handle))
    right_thread = threading.Thread(target=flush, args=(right, right_handle))
    left_thread.start()
    right_thread.start()
    left_thread.join()
    right_thread.join()
    assert not failures
    check = _store(tmp_path, repo)
    assert check.resolve(left_handle)["offset"] == 0
    assert check.resolve(right_handle)["offset"] == 1
