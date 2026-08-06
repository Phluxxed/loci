import json
from pathlib import Path

import pytest

from loci.service import index_repo, store_health
from loci.storage.repository_catalog import CATALOG_FILE_NAME
from loci.storage.store_layout import repository_cache_key


def _repo(tmp_path: Path, name: str, source: str = "def example():\n    return 1\n") -> Path:
    repo = tmp_path / name
    repo.mkdir(parents=True)
    (repo / "example.py").write_text(source, encoding="utf-8")
    return repo


def _item_for(result: dict, repo: Path) -> dict:
    expected = str(repo.resolve())
    return next(item for item in result["items"] if item["repo"] == expected)


def _tree_contents(root: Path) -> dict[str, bytes]:
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def _tree_snapshot(root: Path) -> dict[str, tuple[bytes, int, int]]:
    return {
        path.relative_to(root).as_posix(): (
            path.read_bytes(),
            path.stat().st_mtime_ns,
            path.stat().st_ino,
        )
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


@pytest.fixture
def health_store(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    store = tmp_path / "store"
    store.mkdir()
    monkeypatch.setenv("LOCI_BASE_DIR", str(store))
    return store


def test_store_health_reports_healthy_and_stale_with_exact_reasons(
    tmp_path: Path,
    health_store: Path,
) -> None:
    healthy_repo = _repo(tmp_path, "healthy")
    stale_repo = _repo(tmp_path, "stale")
    index_repo(healthy_repo, incremental=False)
    index_repo(stale_repo, incremental=False)
    (stale_repo / "example.py").write_text(
        "def example():\n    return 2\n",
        encoding="utf-8",
    )

    result = store_health(limit=10)

    assert result["status"] == "unhealthy"
    assert result["complete"] is True
    assert _item_for(result, healthy_repo)["states"] == ["healthy"]
    assert _item_for(result, healthy_repo)["reasons"] == [{
        "state": "healthy",
        "code": "INDEX_CURRENT",
        "details": {},
    }]
    stale = _item_for(result, stale_repo)
    assert stale["states"] == ["stale"]
    assert stale["reasons"][0]["state"] == "stale"
    assert stale["reasons"][0]["code"] == "SOURCE_CONTENT_CHANGED"
    assert stale["reasons"][0]["details"]["changed"] == ["example.py"]


def test_store_health_preserves_missing_corrupt_and_overlapping_findings(
    tmp_path: Path,
    health_store: Path,
) -> None:
    parent = _repo(tmp_path, "parent")
    child = _repo(parent, "child")
    missing = _repo(tmp_path, "missing")
    corrupt = _repo(tmp_path, "corrupt")
    for repo in (parent, child, missing, corrupt):
        index_repo(repo, incremental=False)

    missing.rename(tmp_path / "missing-moved")
    corrupt_index = (
        health_store
        / repository_cache_key(corrupt)
        / "index.json"
    )
    corrupt_index.write_text("{not json", encoding="utf-8")
    (parent / "example.py").write_text(
        "def example():\n    return 2\n",
        encoding="utf-8",
    )

    result = store_health(limit=10)

    parent_item = _item_for(result, parent)
    assert parent_item["states"] == ["stale", "overlapping"]
    assert {reason["code"] for reason in parent_item["reasons"]} == {
        "SOURCE_CONTENT_CHANGED",
        "REPOSITORY_ROOT_CONTAINS_INDEXED_ROOT",
    }
    child_item = _item_for(result, child)
    assert child_item["states"] == ["overlapping"]
    assert child_item["reasons"][0]["code"] == (
        "REPOSITORY_ROOT_INSIDE_INDEXED_ROOT"
    )
    assert _item_for(result, missing)["states"] == ["missing"]
    assert _item_for(result, missing)["reasons"][0]["code"] == (
        "REPOSITORY_ROOT_MISSING"
    )
    assert _item_for(result, corrupt)["states"] == ["corrupt"]
    assert _item_for(result, corrupt)["reasons"][0]["code"] == (
        "INDEX_JSON_INVALID"
    )
    assert result["counts"]["stale"] == 1
    assert result["counts"]["missing"] == 1
    assert result["counts"]["corrupt"] == 1
    assert result["counts"]["overlapping"] == 2


def test_store_health_paginates_catalog_and_reports_unprobed_scope(
    tmp_path: Path,
    health_store: Path,
) -> None:
    repos = [_repo(tmp_path, f"repo-{number}") for number in range(3)]
    for repo in repos:
        index_repo(repo, incremental=False)

    first = store_health(offset=0, limit=2)
    second = store_health(offset=2, limit=2)

    assert first["status"] == "incomplete"
    assert first["complete"] is False
    assert first["counts"]["repositories"] == 3
    assert first["counts"]["returned"] == 2
    assert first["pagination"] == {
        "offset": 0,
        "limit": 2,
        "next_offset": 2,
    }
    assert second["counts"]["returned"] == 1
    assert second["pagination"]["next_offset"] is None
    assert second["status"] == "incomplete"
    assert second["complete"] is False


def test_store_health_bounds_large_catalog_pages(
    tmp_path: Path,
    health_store: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    entries = []
    for number in range(550):
        repo = tmp_path / f"missing-{number:03d}"
        entries.append({
            "cache_key": repository_cache_key(repo),
            "symbols": number,
            "path": str(repo.resolve()),
        })
    (health_store / CATALOG_FILE_NAME).write_text(
        json.dumps({
            "schema_version": 1,
            "repositories": entries,
        }),
        encoding="utf-8",
    )
    page_keys = {
        entry["cache_key"]
        for entry in sorted(entries, key=lambda value: value["cache_key"])[:7]
    }
    original_open = Path.open

    def bounded_open(path: Path, *args, **kwargs):
        if path.name == "index.json" and path.parent.name not in page_keys:
            raise AssertionError("health must not inspect indexes outside its page")
        return original_open(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", bounded_open)

    result = store_health(offset=0, limit=7)

    assert result["counts"]["repositories"] == 550
    assert result["counts"]["returned"] == 7
    assert result["pagination"]["next_offset"] == 7
    assert len(result["items"]) == 7
    assert all("missing" in item["states"] for item in result["items"])


def test_store_health_reports_probe_budget_exhaustion_without_claiming_health(
    tmp_path: Path,
    health_store: Path,
) -> None:
    repo = _repo(tmp_path, "large")
    index_repo(repo, incremental=False)

    result = store_health(limit=10, max_index_bytes=1)

    item = _item_for(result, repo)
    assert result["status"] == "incomplete"
    assert result["complete"] is False
    assert item["states"] == []
    assert item["reasons"] == []
    assert item["probe"]["status"] == "unavailable"
    assert item["probe"]["reason"]["code"] == "INDEX_BYTES_LIMIT_EXCEEDED"
    assert item["probe"]["reason"]["details"]["limit"] == 1
    assert item["probe"]["reason"]["details"]["observed"] > 1
    assert result["counts"]["incomplete"] == 1


def test_store_health_reports_catalog_budget_exhaustion(
    tmp_path: Path,
    health_store: Path,
) -> None:
    repo = _repo(tmp_path, "repo")
    index_repo(repo, incremental=False)

    result = store_health(max_catalog_bytes=1)

    assert result["status"] == "incomplete"
    assert result["complete"] is False
    assert result["items"] == []
    assert result["diagnostics"][0]["state"] == "unavailable"
    assert result["diagnostics"][0]["code"] == "CATALOG_BYTES_LIMIT_EXCEEDED"


@pytest.mark.parametrize(
    ("kwargs", "code"),
    [
        ({"max_probe_paths": 0}, "REPOSITORY_PATHS_LIMIT_EXCEEDED"),
        ({"max_probe_bytes": 0}, "REPOSITORY_BYTES_LIMIT_EXCEEDED"),
    ],
)
def test_store_health_reports_repository_probe_bounds(
    tmp_path: Path,
    health_store: Path,
    kwargs: dict,
    code: str,
) -> None:
    repo = _repo(tmp_path, "bounded")
    index_repo(repo, incremental=False)

    result = store_health(limit=10, **kwargs)

    item = _item_for(result, repo)
    assert result["status"] == "incomplete"
    assert item["states"] == []
    assert item["probe"]["status"] == "unavailable"
    assert item["probe"]["reason"]["code"] == code


def test_store_health_is_repeatable_and_does_not_write_store_or_repositories(
    tmp_path: Path,
    health_store: Path,
) -> None:
    repo = _repo(tmp_path, "repo")
    index_repo(repo, incremental=False)
    store_before = _tree_snapshot(health_store)
    repo_before = _tree_snapshot(repo)

    first = store_health(limit=10)
    second = store_health(limit=10)

    assert first == second
    assert _tree_snapshot(health_store) == store_before
    assert _tree_snapshot(repo) == repo_before


@pytest.mark.parametrize(
    ("kwargs", "parameter"),
    [
        ({"offset": -1}, "offset"),
        ({"limit": 0}, "limit"),
        ({"limit": 501}, "limit"),
        ({"max_catalog_bytes": -1}, "max_catalog_bytes"),
        ({"max_index_bytes": -1}, "max_index_bytes"),
        ({"max_probe_paths": -1}, "max_probe_paths"),
        ({"max_probe_bytes": -1}, "max_probe_bytes"),
    ],
)
def test_store_health_rejects_invalid_bounds(
    health_store: Path,
    kwargs: dict,
    parameter: str,
) -> None:
    with pytest.raises(Exception) as exc_info:
        store_health(**kwargs)

    assert getattr(exc_info.value, "code", None) == "INVALID_INPUT"
    assert exc_info.value.details["parameter"] == parameter


def test_store_health_reports_corrupt_catalog_without_repairing_it(
    health_store: Path,
) -> None:
    catalog = health_store / ".loci-repositories.json"
    catalog.write_text("{not json", encoding="utf-8")
    before = catalog.read_bytes()

    first = store_health()
    second = store_health()

    assert first == second
    assert first["status"] == "unhealthy"
    assert first["complete"] is False
    assert first["items"] == []
    assert first["diagnostics"][0]["state"] == "corrupt"
    assert first["diagnostics"][0]["code"] == "REPOSITORY_CATALOG_INVALID"
    assert catalog.read_bytes() == before


def test_store_health_reports_legacy_indexes_without_catalog(
    tmp_path: Path,
    health_store: Path,
) -> None:
    repo = tmp_path / "legacy"
    repo.mkdir()
    repo_dir = health_store / repository_cache_key(repo)
    repo_dir.mkdir(parents=True)
    index = repo_dir / "index.json"
    index.write_text("{}", encoding="utf-8")
    before = _tree_contents(health_store)

    result = store_health()

    assert result["status"] == "unhealthy"
    assert result["items"] == []
    assert result["diagnostics"][0]["code"] == "REPOSITORY_CATALOG_MISSING"
    assert _tree_contents(health_store) == before


def test_store_health_does_not_create_a_missing_store_root(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    missing_store = tmp_path / "not-created"
    monkeypatch.setenv("LOCI_BASE_DIR", str(missing_store))

    result = store_health()

    assert result["status"] == "incomplete"
    assert result["complete"] is False
    assert result["diagnostics"][0]["code"] == "STORE_INVENTORY_READ_FAILED"
    assert not missing_store.exists()
