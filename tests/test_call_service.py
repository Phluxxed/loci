from __future__ import annotations

import json
from pathlib import Path

import pytest

from loci import service as service_module
from loci.service import LociError, graph_calls, graph_health, index_repo
from loci.storage.index_store import IndexStore


def _write_python_call_repo(repo: Path) -> None:
    repo.mkdir()
    (repo / "target.py").write_text(
        "def target():\n    return 1\n\ndef other():\n    return 2\n",
        encoding="utf-8",
    )
    (repo / "use.py").write_text(
        "from target import target\n\ndef caller():\n    return target()\n",
        encoding="utf-8",
    )


def _load_graph(base: Path, repo: Path) -> dict:
    index = IndexStore(base_dir=base).load(repo.resolve())
    assert index is not None
    graph = index["graph"]
    assert isinstance(graph, dict)
    return graph


def test_service_persists_resolved_calls_and_edges(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    base = tmp_path / ".codeindex"
    monkeypatch.setenv("LOCI_BASE_DIR", str(base))
    repo = tmp_path / "repo"
    _write_python_call_repo(repo)

    indexed = index_repo(repo, incremental=False)
    graph = _load_graph(base, repo)
    health = graph_health(repo)

    assert indexed["graph_calls_indexed"] == 1
    assert indexed["graph_calls_resolved"] == 1
    assert indexed["graph_calls_unresolved"] == 0
    assert health["counts"]["graph_calls_indexed"] == 1
    assert health["counts"]["graph_calls_resolved"] == 1
    assert health["counts"]["graph_calls_unresolved"] == 0
    assert len(graph["calls"]) == 1
    assert graph["calls"][0]["status"] == "resolved"
    assert graph["calls"][0]["caller_id"] == "use.py::caller#function"
    assert graph["calls"][0]["target_id"] == "target.py::target#function"
    assert [
        (edge["type"], edge["from"], edge["to"])
        for edge in graph["edges"]
        if edge["type"] == "calls"
    ] == [(
        "calls",
        "use.py::caller#function",
        "target.py::target#function",
    )]


def test_service_noop_incremental_reuses_calls_without_reparse_byte_stably(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    base = tmp_path / ".codeindex"
    monkeypatch.setenv("LOCI_BASE_DIR", str(base))
    repo = tmp_path / "repo"
    _write_python_call_repo(repo)
    store = IndexStore(base_dir=base)

    index_repo(repo, incremental=False)
    full_bytes = store._index_path(repo.resolve()).read_bytes()

    def fail_if_reparsed(*args, **kwargs):
        raise AssertionError("unchanged source was reparsed")

    monkeypatch.setattr(service_module, "parse_file", fail_if_reparsed)
    monkeypatch.setattr(service_module, "extract_import_batch", fail_if_reparsed)
    incremental = index_repo(repo, incremental=True)
    incremental_bytes = store._index_path(repo.resolve()).read_bytes()

    assert incremental["files_skipped"] == 2
    assert incremental_bytes == full_bytes


def test_service_changed_and_deleted_source_replace_then_drop_calls(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    base = tmp_path / ".codeindex"
    monkeypatch.setenv("LOCI_BASE_DIR", str(base))
    repo = tmp_path / "repo"
    _write_python_call_repo(repo)
    source = repo / "use.py"

    index_repo(repo, incremental=False)
    source.write_text(
        "from target import other\n\ndef caller():\n    return other()\n",
        encoding="utf-8",
    )
    changed = index_repo(repo, incremental=True)
    changed_graph = _load_graph(base, repo)

    assert changed["files_skipped"] == 1
    assert len(changed_graph["calls"]) == 1
    assert changed_graph["calls"][0]["target_id"] == "target.py::other#function"

    source.unlink()
    deleted = index_repo(repo, incremental=True)
    deleted_graph = _load_graph(base, repo)

    assert deleted["files_skipped"] == 1
    assert deleted_graph["calls"] == []
    assert all(edge["type"] != "calls" for edge in deleted_graph["edges"])


def test_service_target_add_delete_reresolves_unchanged_call(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    base = tmp_path / ".codeindex"
    monkeypatch.setenv("LOCI_BASE_DIR", str(base))
    repo = tmp_path / "repo"
    repo.mkdir()
    target = repo / "target.py"
    target.write_text("def other():\n    return 2\n", encoding="utf-8")
    (repo / "use.py").write_text(
        "from target import target\n\ndef caller():\n    return target()\n",
        encoding="utf-8",
    )

    index_repo(repo, incremental=False)
    initial = _load_graph(base, repo)["calls"][0]

    target.write_text("def target():\n    return 1\n", encoding="utf-8")
    added = index_repo(repo, incremental=True)
    resolved = _load_graph(base, repo)["calls"][0]

    target.unlink()
    deleted = index_repo(repo, incremental=True)
    unresolved = _load_graph(base, repo)["calls"][0]

    assert initial["status"] == "unresolved"
    assert initial["unresolved_reason"] == "reference_unresolved"
    assert added["files_skipped"] == 1
    assert resolved["status"] == "resolved"
    assert resolved["target_id"] == "target.py::target#function"
    assert deleted["files_skipped"] == 1
    assert unresolved["status"] == "unresolved"
    assert unresolved["unresolved_reason"] == "reference_unresolved"


def test_service_javascript_package_control_reresolves_unchanged_call(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    base = tmp_path / ".codeindex"
    monkeypatch.setenv("LOCI_BASE_DIR", str(base))
    repo = tmp_path / "repo"
    web = repo / "apps" / "web"
    core = repo / "packages" / "core"
    (web / "src").mkdir(parents=True)
    (core / "src").mkdir(parents=True)
    (repo / "package.json").write_text(
        '{"name":"root","private":true,"workspaces":["apps/*","packages/*"]}',
        encoding="utf-8",
    )
    web_manifest = web / "package.json"
    web_manifest.write_text('{"name":"@repo/web"}', encoding="utf-8")
    (core / "package.json").write_text(
        '{"name":"@repo/core","exports":"./src/index.ts"}',
        encoding="utf-8",
    )
    (core / "src" / "index.ts").write_text(
        'export * from "./target.js";\n',
        encoding="utf-8",
    )
    (core / "src" / "target.ts").write_text(
        "export function target() { return 1; }\n",
        encoding="utf-8",
    )
    (web / "src" / "use.ts").write_text(
        (
            'import {target} from "@repo/core";\n'
            "export function caller() { return target(); }\n"
        ),
        encoding="utf-8",
    )

    index_repo(repo, incremental=False)
    initial = _load_graph(base, repo)["calls"]

    web_manifest.write_text(
        '{"name":"@repo/web","dependencies":{"@repo/core":"workspace:*"}}',
        encoding="utf-8",
    )
    added = index_repo(repo, incremental=True)
    resolved = _load_graph(base, repo)["calls"]

    web_manifest.write_text('{"name":"@repo/web"}', encoding="utf-8")
    removed = index_repo(repo, incremental=True)
    unresolved = _load_graph(base, repo)["calls"]

    assert len(initial) == 1
    assert initial[0]["status"] == "unresolved"
    assert added["files_skipped"] == 3
    assert resolved[0]["status"] == "resolved"
    assert resolved[0]["target_id"] == (
        "packages/core/src/target.ts::target#function"
    )
    assert resolved[0]["resolution_control_files"] == [
        "apps/web/package.json",
        "package.json",
        "packages/core/package.json",
    ]
    assert removed["files_skipped"] == 3
    assert unresolved[0]["status"] == "unresolved"


def test_service_python_reexport_change_reresolves_unchanged_call(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    base = tmp_path / ".codeindex"
    monkeypatch.setenv("LOCI_BASE_DIR", str(base))
    repo = tmp_path / "repo"
    package = repo / "pkg"
    package.mkdir(parents=True)
    reexport = package / "__init__.py"
    reexport.write_text("from .model import target\n", encoding="utf-8")
    (package / "model.py").write_text(
        "def target():\n    return 1\n\ndef other():\n    return 2\n",
        encoding="utf-8",
    )
    (repo / "use.py").write_text(
        "from pkg import target\n\ndef caller():\n    return target()\n",
        encoding="utf-8",
    )
    store = IndexStore(base_dir=base)

    index_repo(repo, incremental=False)
    initial = _load_graph(base, repo)["calls"][0]

    reexport.write_text("from .model import other\n", encoding="utf-8")
    changed = index_repo(repo, incremental=True)
    unresolved = _load_graph(base, repo)["calls"][0]

    reexport.write_text("from .model import target\n", encoding="utf-8")
    restored = index_repo(repo, incremental=True)
    incremental_bytes = store._index_path(repo.resolve()).read_bytes()
    index_repo(repo, incremental=False)
    full_bytes = store._index_path(repo.resolve()).read_bytes()

    assert initial["status"] == "resolved"
    assert initial["target_id"] == "pkg/model.py::target#function"
    assert changed["files_skipped"] == 2
    assert unresolved["status"] == "unresolved"
    assert unresolved["unresolved_reason"] == "reference_unresolved"
    assert restored["files_skipped"] == 2
    assert incremental_bytes == full_bytes


def test_service_go_module_change_reresolves_unchanged_package_call(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    base = tmp_path / ".codeindex"
    monkeypatch.setenv("LOCI_BASE_DIR", str(base))
    repo = tmp_path / "repo"
    library = repo / "lib"
    library.mkdir(parents=True)
    go_mod = repo / "go.mod"
    go_mod.write_text("module example.com/project\n\ngo 1.22\n", encoding="utf-8")
    (library / "lib.go").write_text(
        "package lib\n\nfunc Target() {}\n",
        encoding="utf-8",
    )
    (repo / "main.go").write_text(
        (
            "package main\n\n"
            'import "example.com/project/lib"\n\n'
            "func Caller() { lib.Target() }\n"
        ),
        encoding="utf-8",
    )

    index_repo(repo, incremental=False)
    initial = _load_graph(base, repo)["calls"][0]

    go_mod.write_text("module example.com/renamed\n\ngo 1.22\n", encoding="utf-8")
    changed = index_repo(repo, incremental=True)
    unresolved = _load_graph(base, repo)["calls"][0]

    go_mod.write_text("module example.com/project\n\ngo 1.22\n", encoding="utf-8")
    restored = index_repo(repo, incremental=True)
    resolved = _load_graph(base, repo)["calls"][0]

    assert initial["status"] == "resolved"
    assert initial["target_id"] == "lib/lib.go::Target#function"
    assert changed["files_skipped"] == 2
    assert unresolved["status"] == "unresolved"
    assert unresolved["unresolved_reason"] == "reference_unresolved"
    assert restored["files_skipped"] == 2
    assert resolved["status"] == "resolved"


def test_service_cargo_dependency_change_reresolves_unchanged_call(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    base = tmp_path / ".codeindex"
    monkeypatch.setenv("LOCI_BASE_DIR", str(base))
    repo = tmp_path / "repo"
    app = repo / "app"
    core = repo / "core"
    (app / "src").mkdir(parents=True)
    (core / "src").mkdir(parents=True)
    (repo / "Cargo.toml").write_text(
        '[workspace]\nmembers = ["app", "core"]\nresolver = "2"\n',
        encoding="utf-8",
    )
    app_manifest = app / "Cargo.toml"
    app_manifest.write_text(
        (
            '[package]\nname = "app"\nversion = "0.1.0"\nedition = "2021"\n\n'
            '[dependencies]\ncore = { path = "../core" }\n'
        ),
        encoding="utf-8",
    )
    (core / "Cargo.toml").write_text(
        '[package]\nname = "core"\nversion = "0.1.0"\nedition = "2021"\n',
        encoding="utf-8",
    )
    (app / "src" / "lib.rs").write_text(
        "use core::target;\n\npub fn caller() { target(); }\n",
        encoding="utf-8",
    )
    (core / "src" / "lib.rs").write_text(
        "pub fn target() {}\n",
        encoding="utf-8",
    )

    index_repo(repo, incremental=False)
    initial = _load_graph(base, repo)["calls"][0]

    app_manifest.write_text(
        '[package]\nname = "app"\nversion = "0.1.0"\nedition = "2021"\n',
        encoding="utf-8",
    )
    changed = index_repo(repo, incremental=True)
    unresolved = _load_graph(base, repo)["calls"][0]

    app_manifest.write_text(
        (
            '[package]\nname = "app"\nversion = "0.1.0"\nedition = "2021"\n\n'
            '[dependencies]\ncore = { path = "../core" }\n'
        ),
        encoding="utf-8",
    )
    restored = index_repo(repo, incremental=True)
    resolved = _load_graph(base, repo)["calls"][0]

    assert initial["status"] == "resolved"
    assert initial["target_id"] == "core/src/lib.rs::target#function"
    assert changed["files_skipped"] == 2
    assert unresolved["status"] == "unresolved"
    assert unresolved["unresolved_reason"] == "reference_unresolved"
    assert restored["files_skipped"] == 2
    assert resolved["status"] == "resolved"


def test_service_schema_seven_call_cache_forces_full_rebuild(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    base = tmp_path / ".codeindex"
    monkeypatch.setenv("LOCI_BASE_DIR", str(base))
    repo = tmp_path / "repo"
    _write_python_call_repo(repo)
    index_repo(repo, incremental=False)
    store = IndexStore(base_dir=base)
    index_path = store._index_path(repo.resolve())
    payload = json.loads(index_path.read_text())
    payload["graph"]["schema_version"] = 7
    index_path.write_text(json.dumps(payload))

    rebuilt = index_repo(repo, incremental=True)
    graph = _load_graph(base, repo)

    assert rebuilt["files_skipped"] == 0
    assert graph["schema_version"] == 8
    assert graph["calls"][0]["status"] == "resolved"


def test_service_fresh_process_rejects_then_repairs_stale_call_state(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    base = tmp_path / ".codeindex"
    monkeypatch.setenv("LOCI_BASE_DIR", str(base))
    repo = tmp_path / "repo"
    _write_python_call_repo(repo)
    index_repo(repo, incremental=False)
    store = IndexStore(base_dir=base)
    index_path = store._index_path(repo.resolve())
    payload = json.loads(index_path.read_text())
    record = payload["graph"]["calls"][0]
    record["raw"]["source_hash"] = "0" * 64
    for support in record["support"]:
        if support["kind"] in {"call_site", "symbol_reference"}:
            support["content_hash"] = "0" * 64
    index_path.write_text(json.dumps(payload))

    with pytest.raises(LociError, match="stale"):
        graph_health(repo)

    health = graph_health(repo, ensure_fresh=True)
    repaired = _load_graph(base, repo)

    assert health["status"] == "healthy"
    assert repaired["calls"][0]["status"] == "resolved"


def _write_call_diagnostics_repo(repo: Path) -> None:
    repo.mkdir()
    (repo / "target.py").write_text(
        "def target():\n    return 1\n",
        encoding="utf-8",
    )
    (repo / "use.py").write_text(
        (
            "from target import target\n"
            "from missing import lost\n\n"
            "def first():\n"
            "    return target()\n\n"
            "def second():\n"
            "    return lost()\n"
        ),
        encoding="utf-8",
    )


def test_graph_calls_returns_stable_bounded_record_page(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setenv("LOCI_BASE_DIR", str(tmp_path / ".codeindex"))
    repo = tmp_path / "repo"
    _write_call_diagnostics_repo(repo)
    index_repo(repo, incremental=False)

    result = graph_calls(repo, limit=1)

    assert result["schema_version"] == 1
    assert result["repo"] == str(repo.resolve())
    assert result["file"] is None
    assert result["status"] == "all"
    assert result["counts"] == {
        "total": 2,
        "resolved": 1,
        "unresolved": 1,
        "returned": 1,
    }
    assert result["pagination"] == {
        "offset": 0,
        "limit": 1,
        "next_offset": 1,
    }
    item = result["items"][0]
    assert set(item) == {
        "raw",
        "caller_id",
        "caller_kind",
        "target_file",
        "target_id",
        "target_kind",
        "status",
        "resolution",
        "unresolved_reason",
        "reference_unresolved_reason",
        "resolution_basis",
        "support",
        "resolution_control_files",
        "resolution_configuration",
    }
    assert item["raw"]["callee_path"] == ["target"]
    assert item["caller_id"] == "use.py::first#function"
    assert item["target_id"] == "target.py::target#function"
    assert item["status"] == "resolved"
    assert item["resolution"] == "import-resolved"


def test_graph_calls_filters_before_status_and_pagination(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setenv("LOCI_BASE_DIR", str(tmp_path / ".codeindex"))
    repo = tmp_path / "repo"
    _write_call_diagnostics_repo(repo)
    index_repo(repo, incremental=False)

    unresolved = graph_calls(repo, file="use.py", status="unresolved", limit=1)
    second = graph_calls(repo, offset=1, limit=1)
    empty = graph_calls(repo, file="not-indexed.py", status="resolved")

    assert unresolved["counts"] == {
        "total": 2,
        "resolved": 1,
        "unresolved": 1,
        "returned": 1,
    }
    assert unresolved["items"][0]["raw"]["callee_path"] == ["lost"]
    assert unresolved["items"][0]["status"] == "unresolved"
    assert unresolved["items"][0]["resolution"] is None
    assert unresolved["pagination"]["next_offset"] is None
    assert second["items"][0]["raw"]["callee_path"] == ["lost"]
    assert second["pagination"]["next_offset"] is None
    assert empty["counts"] == {
        "total": 0,
        "resolved": 0,
        "unresolved": 0,
        "returned": 0,
    }
    assert empty["items"] == []
    assert empty["pagination"]["next_offset"] is None


@pytest.mark.parametrize(
    ("kwargs", "field"),
    [
        ({"file": ""}, "file"),
        ({"file": "../use.py"}, "file"),
        ({"file": "./use.py"}, "file"),
        ({"file": "/use.py"}, "file"),
        ({"file": "use\\file.py"}, "file"),
        ({"file": 1}, "file"),
        ({"status": "RESOLVED"}, "status"),
        ({"status": None}, "status"),
        ({"status": []}, "status"),
        ({"offset": -1}, "offset"),
        ({"offset": True}, "offset"),
        ({"offset": "0"}, "offset"),
        ({"limit": 0}, "limit"),
        ({"limit": 501}, "limit"),
        ({"limit": True}, "limit"),
        ({"limit": "1"}, "limit"),
    ],
)
def test_graph_calls_rejects_invalid_filters_and_pagination(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    kwargs: dict,
    field: str,
):
    monkeypatch.setenv("LOCI_BASE_DIR", str(tmp_path / ".codeindex"))
    repo = tmp_path / "repo"
    _write_call_diagnostics_repo(repo)
    index_repo(repo, incremental=False)

    with pytest.raises(LociError) as exc_info:
        graph_calls(repo, **kwargs)

    assert exc_info.value.code == "INVALID_INPUT"
    assert exc_info.value.details["field"] == field


def test_graph_calls_refreshes_only_when_requested(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setenv("LOCI_BASE_DIR", str(tmp_path / ".codeindex"))
    repo = tmp_path / "repo"
    _write_python_call_repo(repo)
    index_repo(repo, incremental=False)
    target = repo / "target.py"
    target.write_text("def other():\n    return 2\n", encoding="utf-8")

    stale = graph_calls(repo)
    refreshed = graph_calls(repo, ensure_fresh=True)

    assert stale["items"][0]["status"] == "resolved"
    assert refreshed["items"][0]["status"] == "unresolved"
