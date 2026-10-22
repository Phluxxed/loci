"""Exact reads use a validated source projection without weakening graph fallback."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from loci import service
from loci.graph.state import GraphIndexState
from loci.retrieval_io import source_ref
from loci._exploration_output import Span
from loci.source_access import active_paths, control_files, source_digest
from loci.storage.index_store import IndexStore


@pytest.fixture
def indexed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    repo = tmp_path / "repo"
    repo.mkdir()
    raw = ("🙂 \"quoted\" \\ slash\n" * 1000).encode("utf-8")
    (repo / "page.md").write_bytes(raw)
    (repo / "extra.md").write_text("# Extra\n", encoding="utf-8")
    (repo / "private.txt").write_text("not indexed\n", encoding="utf-8")
    (repo / "main.go").write_text("package main\nfunc main() {}\n", encoding="utf-8")
    (repo / "go.mod").write_text("module example.com/app\n\ngo 1.22\n", encoding="utf-8")
    cache = tmp_path / "cache"
    monkeypatch.setenv("LOCI_BASE_DIR", str(cache))
    service.index_repo(repo, incremental=False)
    return repo, IndexStore(cache), raw


def _reference(repo: Path, file: str, raw: bytes) -> str:
    return source_ref(repo, Span(file, 0, len(raw), 1, raw.count(b"\n") + 1,
                                 hashlib.sha256(raw).hexdigest(), raw.decode("utf-8")))


def _pages(repo: Path, reference: str, *, ensure_fresh: bool = False) -> list[dict]:
    pages = []
    while reference is not None:
        page = service.read(repo, reference, ensure_fresh=ensure_fresh)
        pages.append(page)
        reference = page["next_source_ref"]
    return pages


def _receipt(store: IndexStore, repo: Path) -> Path:
    return store._repo_dir(repo) / "source-access.json"


def _rewrite_receipt_for_index(store: IndexStore, repo: Path, value: dict) -> None:
    value["index_sha256"] = hashlib.sha256(store._index_path(repo).read_bytes()).hexdigest()
    payload = {key: item for key, item in value.items() if key != "checksum"}
    value["checksum"] = hashlib.sha256(json.dumps(
        payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"),
        allow_nan=False,
    ).encode()).hexdigest()
    _receipt(store, repo).write_text(json.dumps(value), encoding="utf-8")


def test_matching_receipt_reads_and_pages_without_loading_graph(indexed, monkeypatch):
    repo, store, raw = indexed
    reference = _reference(repo, "page.md", raw)
    receipt = _receipt(store, repo)
    receipt.rename(receipt.with_suffix(".saved"))
    legacy = _pages(repo, reference)
    receipt.with_suffix(".saved").rename(receipt)

    def unexpected(*_args, **_kwargs):
        raise AssertionError("exact read loaded semantic graph")

    with monkeypatch.context() as patch:
        patch.setattr(IndexStore, "load", unexpected)
        patch.setattr(IndexStore, "validate_graph_state", unexpected)
        patch.setattr(GraphIndexState, "from_dict", unexpected)
        projected = _pages(repo, reference, ensure_fresh=True)

    assert projected == legacy
    assert len(projected) > 1
    assert b"".join(page["source"]["content"].encode() for page in projected) == raw
    assert all(page["usage"]["output_bytes"] <= 16384 for page in projected)
    assert all(page["usage"]["evidence_bytes"] <= 8192 for page in projected)


@pytest.mark.parametrize("damage", ["missing", "malformed", "checksum", "generation"])
def test_untrusted_receipt_uses_validated_legacy_path(indexed, monkeypatch, damage):
    repo, store, raw = indexed
    receipt = _receipt(store, repo)
    if damage == "missing":
        receipt.unlink()
    elif damage == "malformed":
        receipt.write_text("[", encoding="utf-8")
    else:
        value = json.loads(receipt.read_text())
        value["checksum" if damage == "checksum" else "index_sha256"] = "0" * 64
        receipt.write_text(json.dumps(value), encoding="utf-8")
    assert store.load_source_index(repo) is None

    calls = []
    original = IndexStore.validate_graph_state

    def validated(self, index):
        calls.append(1)
        return original(self, index)

    monkeypatch.setattr(IndexStore, "validate_graph_state", validated)
    assert service.read(repo, _reference(repo, "page.md", raw))["status"] == "ok"
    assert calls
    # A fabricated locator for an existing but unindexed file cannot gain access.
    private = (repo / "private.txt").read_bytes()
    with pytest.raises(service.LociError) as error:
        service.read(repo, _reference(repo, "private.txt", private))
    assert error.value.code == "INVALID_SOURCE_REF"


def test_rewritten_receipt_cannot_add_unindexed_source(indexed):
    repo, store, _ = indexed
    receipt = _receipt(store, repo)
    value = json.loads(receipt.read_text())
    raw = (repo / "private.txt").read_bytes()
    value["source_index"]["file_hashes"]["private.txt"] = hashlib.sha256(raw).hexdigest()
    _rewrite_receipt_for_index(store, repo, value)

    with pytest.raises(service.LociError) as error:
        service.read(repo, _reference(repo, "private.txt", raw))
    assert error.value.code == "INVALID_SOURCE_REF"


@pytest.mark.parametrize("footer", ["missing", "altered"])
def test_receipt_requires_index_footer_even_with_matching_raw_hash(indexed, footer):
    repo, store, raw = indexed
    value = json.loads(_receipt(store, repo).read_text())
    index_path = store._index_path(repo)
    index = json.loads(index_path.read_text())
    if footer == "missing":
        index.pop("source_access_sha256")
    else:
        index["source_access_sha256"] = "0" * 64
    index_path.write_text(json.dumps(index, indent=2), encoding="utf-8")
    _rewrite_receipt_for_index(store, repo, value)

    assert store.load_source_index(repo) is None
    assert service.read(repo, _reference(repo, "page.md", raw))["status"] == "ok"


def test_receipt_with_old_index_version_uses_legacy_path(indexed):
    repo, store, raw = indexed
    value = json.loads(_receipt(store, repo).read_text())
    value["source_index"]["extractor_version"] -= 1
    index_path = store._index_path(repo)
    index = json.loads(index_path.read_text())
    index["source_access_sha256"] = source_digest(value["source_index"])
    index_path.write_text(json.dumps(index, indent=2), encoding="utf-8")
    _rewrite_receipt_for_index(store, repo, value)

    assert store.load_source_index(repo) is None
    assert service.read(repo, _reference(repo, "page.md", raw))["status"] == "ok"


@pytest.mark.parametrize("ensure_fresh", [False, True])
def test_corrupt_index_with_stale_receipt_keeps_legacy_repair_semantics(
    indexed, ensure_fresh,
):
    repo, store, raw = indexed
    index_path = store._index_path(repo)
    value = json.loads(index_path.read_text())
    value["graph"]["input_hashes"] = {"../outside": "bad"}
    index_path.write_text(json.dumps(value))
    assert store.load_source_index(repo) is None
    reference = _reference(repo, "page.md", raw)
    if ensure_fresh:
        assert service.ensure_fresh_index(repo, source_only=True)["refreshed"] is True
        assert service.read(repo, reference)["status"] == "ok"
    else:
        with pytest.raises(service.LociError) as error:
            service.read(repo, reference)
        assert error.value.code == "INVALID_GRAPH_SCHEMA"


@pytest.mark.parametrize("change", ["source", "control", "coverage"])
def test_source_freshness_refreshes_under_writer_lock(indexed, monkeypatch, change):
    repo, store, _ = indexed
    if change == "source":
        (repo / "extra.md").write_text("# Changed\n", encoding="utf-8")
    elif change == "control":
        (repo / "go.mod").write_text("module example.com/new\n\ngo 1.22\n", encoding="utf-8")
    else:
        (repo / "another.txt").write_text("unsupported\n", encoding="utf-8")
    observed = []
    original = service._index_repo_unlocked

    def checked(path, *, incremental):
        observed.append(store.refresh_lock_path(path).exists())
        return original(path, incremental=incremental)

    monkeypatch.setattr(service, "_index_repo_unlocked", checked)
    assert service.ensure_fresh_index(repo, source_only=True)["refreshed"] is True
    assert observed == [True]
    assert service.ensure_fresh_index(repo, source_only=True)["refreshed"] is False
    assert not store.refresh_lock_path(repo).exists()


def test_projection_preserves_control_and_active_path_sets(indexed):
    repo, store, _ = indexed
    index = store.load(repo)
    assert index is not None
    state = store.validate_graph_state(index)
    source = store.load_source_index(repo)
    assert source is not None
    assert set(source["resolver_control_files"]) == control_files(state)
    assert set(source["active_paths"]) == active_paths(index)
    assert "go.mod" in source["resolver_control_files"]
    raw = (repo / "go.mod").read_bytes()
    assert service.read(repo, _reference(repo, "go.mod", raw))["source"]["content"].encode() == raw


def test_active_extension_symlink_is_unsafe_in_both_paths(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    outside = tmp_path / "outside.py"
    outside.write_text("pass\n")
    (repo / "linked.py").symlink_to(outside)
    full = {"symbols": [{"id": "linked", "file_path": "linked.py"}],
            "graph": {"nodes": [{"id": "linked"}], "edges": []}}
    projected = {"active_paths": sorted(active_paths(full))}
    assert not service._active_graph_paths_are_safe(repo, full)
    assert not service._active_graph_paths_are_safe(repo, projected, source_only=True)
