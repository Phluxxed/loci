from pathlib import Path

import pytest

import loci.service as service_module
from loci.service import LociError, index_repo
from loci.storage.index_store import IndexStore
from loci.storage.repository_catalog import RepositoryCatalogEntry
from loci.storage.store_layout import repository_cache_key


def _write_repo(path: Path, name: str = "module.py") -> None:
    path.mkdir(parents=True)
    (path / name).write_text("def value():\n    return 1\n", encoding="utf-8")


def _assert_overlap(
    exc_info: pytest.ExceptionInfo[LociError],
    *,
    requested_root: Path,
    existing_root: Path,
    relationship: str,
) -> None:
    error = exc_info.value
    assert error.code == "REPOSITORY_ROOT_OVERLAP"
    assert error.details["requested_root"] == str(requested_root.resolve())
    assert error.details["existing_root"] == str(existing_root.resolve())
    assert error.details["relationship"] == relationship
    assert error.details["action"]


def test_index_rejects_new_ancestor_before_scanning(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LOCI_BASE_DIR", str(tmp_path / "store"))
    existing = tmp_path / "existing"
    nested = existing / "nested"
    _write_repo(nested)
    index_repo(nested, incremental=False)

    def unexpected_scan(*args, **kwargs):
        raise AssertionError("overlap must be rejected before scanning")

    monkeypatch.setattr(service_module, "_scan_repository_files", unexpected_scan)
    with pytest.raises(LociError) as exc_info:
        index_repo(existing, incremental=False)

    _assert_overlap(
        exc_info,
        requested_root=existing,
        existing_root=nested,
        relationship="requested_ancestor",
    )


def test_index_rejects_new_descendant(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LOCI_BASE_DIR", str(tmp_path / "store"))
    existing = tmp_path / "existing"
    _write_repo(existing)
    index_repo(existing, incremental=False)

    nested = existing / "nested"
    _write_repo(nested)
    with pytest.raises(LociError) as exc_info:
        index_repo(nested, incremental=False)

    _assert_overlap(
        exc_info,
        requested_root=nested,
        existing_root=existing,
        relationship="requested_descendant",
    )


def test_exact_root_and_sibling_roots_are_allowed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LOCI_BASE_DIR", str(tmp_path / "store"))
    first = tmp_path / "first"
    sibling = tmp_path / "sibling"
    _write_repo(first)
    _write_repo(sibling)

    index_repo(first, incremental=False)
    index_repo(first, incremental=False)
    index_repo(sibling, incremental=False)


def test_exact_root_reindex_remains_valid_when_store_already_overlaps(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store_dir = tmp_path / "store"
    monkeypatch.setenv("LOCI_BASE_DIR", str(store_dir))
    existing = tmp_path / "existing"
    nested = existing / "nested"
    _write_repo(nested)
    index_repo(existing, incremental=False)

    store = IndexStore(store_dir)
    entries = store._catalog.entries_for_mutation()
    nested_key = repository_cache_key(nested)
    entries[nested_key] = RepositoryCatalogEntry(
        cache_key=nested_key,
        symbols=0,
        path=str(nested.resolve()),
    )
    store._catalog.commit(entries)

    index_repo(existing, incremental=False)


def test_symlink_alias_is_exact_but_symlinked_descendant_overlaps(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LOCI_BASE_DIR", str(tmp_path / "store"))
    existing = tmp_path / "existing"
    _write_repo(existing)
    alias = tmp_path / "alias"
    alias.symlink_to(existing, target_is_directory=True)
    index_repo(existing, incremental=False)
    index_repo(alias, incremental=False)

    nested = existing / "nested"
    _write_repo(nested)
    nested_alias = tmp_path / "nested-alias"
    nested_alias.symlink_to(nested, target_is_directory=True)
    with pytest.raises(LociError) as exc_info:
        index_repo(nested_alias, incremental=False)

    _assert_overlap(
        exc_info,
        requested_root=nested,
        existing_root=existing,
        relationship="requested_descendant",
    )


def test_linked_worktree_canonical_root_is_exact_even_when_nested(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LOCI_BASE_DIR", str(tmp_path / "store"))
    main = tmp_path / "main"
    _write_repo(main)
    (main / ".git" / "worktrees" / "nested").mkdir(parents=True)
    worktree = main / "nested-worktree"
    _write_repo(worktree, "worktree.py")
    (worktree / ".git").write_text(
        f"gitdir: {main / '.git' / 'worktrees' / 'nested'}\n",
        encoding="utf-8",
    )

    index_repo(main, incremental=False)
    index_repo(worktree, incremental=False)

    entries = IndexStore(tmp_path / "store").list_repos()
    assert len(entries) == 1
    assert entries[0]["path"] == str(main.resolve())
