"""Normal source freshness does not depend on semantic graph state."""

from __future__ import annotations

import asyncio
import hashlib
import json
from pathlib import Path

import pytest

from loci import mcp_server, service
from loci._exploration_output import Span
from loci.retrieval_io import source_ref
from loci.storage.index_store import IndexStore


def _repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, files: dict[str, str]) -> tuple[Path, IndexStore]:
    repo = tmp_path / "repo"
    repo.mkdir()
    for name, content in files.items():
        path = repo / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    base = tmp_path / "store"
    monkeypatch.setenv("LOCI_BASE_DIR", str(base))
    return repo, IndexStore(base_dir=base)


def _forbid_semantic_work(monkeypatch: pytest.MonkeyPatch) -> None:
    def forbidden(*args: object, **kwargs: object) -> None:
        pytest.fail("normal source path entered semantic graph work")

    monkeypatch.setattr(IndexStore, "validate_graph_state", forbidden)
    monkeypatch.setattr(service, "materialize_graph", forbidden)
    monkeypatch.setattr(service, "extract_import_batch", forbidden)


def _mcp_call(server: object, name: str, **arguments: object) -> dict:
    result = asyncio.run(server.call_tool(name, arguments))
    assert result.is_error is False
    assert isinstance(result.structured_content, dict)
    return result.structured_content


def test_normal_mcp_first_use_and_changed_source_never_enter_graph(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo, store = _repo(tmp_path, monkeypatch, {
        "worker.py": "def worker():\n    return 1\n",
    })
    _forbid_semantic_work(monkeypatch)
    server = mcp_server.create_server("normal")

    first = _mcp_call(server, "loci_retrieve", repo=str(repo), query="worker.py")
    assert first["relationships"] == []
    assert first["sources"][0]["content"] == (repo / "worker.py").read_text()
    read = _mcp_call(server, "loci_read", repo=str(repo),
                     source_ref=first["items"][0]["source_ref"])
    assert read["source"]["content"] == (repo / "worker.py").read_text()

    changed = "def worker():\n    return 2\n"
    (repo / "worker.py").write_text(changed, encoding="utf-8")
    second = _mcp_call(server, "loci_retrieve", repo=str(repo), query="worker.py")
    assert second["sources"][0]["content"] == changed
    assert second["sources"][0]["content_hash"] == hashlib.sha256(changed.encode()).hexdigest()
    read = _mcp_call(server, "loci_read", repo=str(repo),
                     source_ref=second["items"][0]["source_ref"])
    assert read["source"]["content"] == changed
    index = store.load(repo)
    assert index is not None
    assert index["graph"] is None
    assert index["graph_resolver_version"] is None


def test_corrupt_graph_does_not_block_normal_source_and_later_graph_rebuilds(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo, store = _repo(tmp_path, monkeypatch, {
        "helper.py": "def target():\n    return 1\n",
        "main.py": "from helper import target\n\ndef caller():\n    return target()\n",
    })
    service.index_repo(repo, incremental=False)
    index = store.load(repo)
    assert index is not None
    index["graph"]["edges"].append({"corrupt": True})
    store._index_path(repo).write_text(json.dumps(index), encoding="utf-8")

    with monkeypatch.context() as guard:
        _forbid_semantic_work(guard)
        first = service.retrieve(repo, query="main.py", ensure_fresh=True)
        assert "def caller" in service.read(repo, first["items"][0]["source_ref"],
                                            ensure_fresh=True)["source"]["content"]
        (repo / "main.py").write_text(
            "from helper import target\n\ndef caller():\n    return target() + 1\n",
            encoding="utf-8",
        )
        refreshed = service.retrieve(repo, query="main.py", ensure_fresh=True)
        assert "target() + 1" in service.read(repo, refreshed["items"][0]["source_ref"],
                                             ensure_fresh=True)["source"]["content"]
        assert store.load(repo)["graph"] is None

    calls = service.graph_calls(repo, ensure_fresh=True)["items"]
    imports = service.graph_imports(repo, ensure_fresh=True)["items"]
    assert any(item["status"] == "resolved" and item["raw"]["source_file"] == "main.py"
               for item in calls)
    assert any(item["status"] == "resolved" and item["raw"]["source_file"] == "main.py"
               for item in imports)
    rebuilt = store.load(repo)
    assert rebuilt is not None and rebuilt["graph"] is not None
    store.validate_graph_state(rebuilt)


@pytest.mark.parametrize("manifest", ["go.mod", "Cargo.toml"])
def test_resolver_control_handle_requires_valid_graph_authorization(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, manifest: str,
) -> None:
    control = ("module example.com/app\ngo 1.23\n" if manifest == "go.mod"
               else '[package]\nname = "app"\nversion = "0.1.0"\nedition = "2021"\n')
    source = {"go.mod": {"main.go": "package app\n"},
              "Cargo.toml": {"src/lib.rs": "pub fn run() {}\n"}}[manifest]
    repo, store = _repo(tmp_path, monkeypatch, {manifest: control, **source})
    service.index_repo(repo, incremental=False)
    raw = control.encode()
    reference = source_ref(repo, Span(manifest, 0, len(raw), 1,
                                      control.count("\n"), hashlib.sha256(raw).hexdigest(), control))
    assert service.read(repo, reference, ensure_fresh=True)["source"]["content"] == control

    index = store.load(repo)
    assert index is not None
    index["graph"] = None
    store._index_path(repo).write_text(json.dumps(index), encoding="utf-8")
    with pytest.raises(service.LociError) as missing:
        service.read(repo, reference, ensure_fresh=True)
    assert missing.value.code == "INVALID_SOURCE_REF"

    index["graph"] = {"corrupt": True}
    store._index_path(repo).write_text(json.dumps(index), encoding="utf-8")
    with pytest.raises(service.LociError) as corrupt:
        service.read(repo, reference, ensure_fresh=True)
    assert corrupt.value.code == "INVALID_GRAPH_SCHEMA"


@pytest.mark.parametrize("damage", ["hash", "metadata", "duplicate"])
@pytest.mark.parametrize("ensure_fresh", [False, True])
def test_malformed_source_metadata_fails_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, damage: str, ensure_fresh: bool,
) -> None:
    repo, store = _repo(tmp_path, monkeypatch, {
        "module.py": "def usable():\n    return 1\n",
    })
    service.index_repo(repo, incremental=False)
    index = store.load(repo)
    assert index is not None
    if damage == "hash":
        index["file_hashes"]["module.py"] = "bad"
    elif damage == "metadata":
        index["symbols"][0]["keywords"] = [42]
    else:
        index["symbols"].append(dict(index["symbols"][0]))
    store._index_path(repo).write_text(json.dumps(index), encoding="utf-8")

    with pytest.raises(service.LociError) as raised:
        service.retrieve(repo, query="module.py", ensure_fresh=ensure_fresh)
    assert raised.value.code == "INVALID_SOURCE_INDEX"
