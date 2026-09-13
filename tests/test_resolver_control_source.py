"""Exact control reads preserve indexed identity and retrieval accounting."""

from pathlib import Path

import pytest

from loci import service
from loci.storage.index_store import IndexStore


@pytest.fixture
def repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("LOCI_BASE_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv("LOCI_STORE_NAMESPACE", "test")
    root = tmp_path / "repo"
    root.mkdir()
    (root / "main.go").write_text("package main\nfunc main() {}\n")
    (root / "go.mod").write_text("module example.com/app\n\ngo 1.22\n")
    service.index_repo(root)
    return root


def test_control_requires_indexed_hash_until_refresh(repo: Path) -> None:
    changed = b"module example.com/changed\n\ngo 1.22\n"
    (repo / "go.mod").write_bytes(changed)
    with pytest.raises(service.LociError) as raised:
        service.get_cached_file(repo, "go.mod")
    assert raised.value.code == "CONTROL_SOURCE_UNAVAILABLE"
    assert raised.value.details["reason"] == "indexed_hash_mismatch"
    result = service.get_cached_file(repo, "go.mod", ensure_fresh=True)
    assert result["content"].encode("utf-8") == changed


def test_control_checks_bytes_even_after_freshness_check(
    repo: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_read = service.read_contained_file

    def changed_read(*args, **kwargs):
        (repo / "go.mod").write_text("module example.com/raced\n")
        return original_read(*args, **kwargs)

    monkeypatch.setattr(service, "read_contained_file", changed_read)
    with pytest.raises(service.LociError) as raised:
        service.get_cached_file(repo, "go.mod", ensure_fresh=True)
    assert raised.value.code == "CONTROL_SOURCE_UNAVAILABLE"
    assert raised.value.details["reason"] == "indexed_hash_mismatch"


def test_control_range_accounts_for_selected_and_full_raw_bytes(
    repo: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    raw = "module example.com/app\r\n// café\r\ngo 1.22\r\n".encode("utf-8")
    (repo / "go.mod").write_bytes(raw)
    service.ensure_fresh_index(repo)
    logged = []
    monkeypatch.setattr(IndexStore, "log_retrieval", lambda self, *a, **kw: logged.append((a, kw)))
    result = service.get_cached_file(repo, "go.mod", start_line=2, end_line=2)
    assert result == {
        "file": "go.mod", "content": "// café\r\n", "total_lines": 3,
        "start_line": 2, "end_line": 2,
    }
    assert logged == [(("go.mod", len("// café\r\n".encode("utf-8")), len(raw)), {
        "repo_path": str(repo.resolve()), "language": None,
    })]


@pytest.mark.parametrize("raw", [b"", b"not valid module syntax\n"])
def test_readable_control_does_not_require_valid_resolver_syntax(repo: Path, raw: bytes) -> None:
    (repo / "go.mod").write_bytes(raw)
    result = service.get_cached_file(repo, "go.mod", ensure_fresh=True)
    assert result["content"].encode("utf-8") == raw


def test_non_utf8_control_never_returns_replacement_bytes(repo: Path) -> None:
    (repo / "go.mod").write_bytes(b"module example.com/app\n// \xff\n")
    with pytest.raises(service.LociError) as raised:
        service.get_cached_file(repo, "go.mod", ensure_fresh=True)
    assert raised.value.code == "CONTROL_SOURCE_UNAVAILABLE"
    assert raised.value.details["reason"] == "invalid_utf8"


def test_untracked_control_is_not_an_arbitrary_file_read(repo: Path) -> None:
    nested = repo / "unindexed"
    nested.mkdir()
    (nested / "Cargo.toml").write_text('[package]\nname = "new"\n')
    with pytest.raises(service.LociError) as raised:
        service.get_cached_file(repo, "unindexed/Cargo.toml")
    assert raised.value.code == "FILE_NOT_FOUND"


def test_go_work_uses_the_same_exact_control_route(repo: Path) -> None:
    raw = b"go 1.22\n\nuse .\n"
    (repo / "go.work").write_bytes(raw)
    result = service.get_cached_file(repo, "go.work", ensure_fresh=True)
    assert result["content"].encode("utf-8") == raw
