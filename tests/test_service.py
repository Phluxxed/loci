from pathlib import Path
import hashlib
import json
import subprocess
import sys

import pytest

import loci.service as service_module
from loci.graph.contracts import GRAPH_SCHEMA_VERSION, GRAPH_STATE_SCHEMA_VERSION
from loci.parser.imports import ImportExtractionError
from loci.service import (
    LociError,
    analyze_usage,
    ensure_fresh_index,
    graph_anchors,
    graph_health,
    graph_imports,
    graph_neighbors,
    graph_paths,
    graph_retrieve,
    graph_traverse_neighbors,
    get_cached_file,
    get_symbols,
    grep_repo,
    index_repo,
    list_repos,
    outline_repo,
    search_symbols,
    session_stats,
    verify_repo,
)
from loci.storage.index_store import EXTRACTOR_VERSION, IndexStore


def _run_python_json(source: str, *args: Path) -> dict:
    completed = subprocess.run(
        [sys.executable, "-c", source, *(str(arg) for arg in args)],
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    )
    return json.loads(completed.stdout)


def _import_read_repo(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> Path:
    monkeypatch.setenv("LOCI_BASE_DIR", str(tmp_path / ".codeindex"))
    repo = tmp_path / "import-repo"
    repo.mkdir()
    (repo / "a.py").write_text(
        "import local_target\nimport missing\n",
        encoding="utf-8",
    )
    (repo / "local_target.py").write_text("VALUE = 1\n", encoding="utf-8")
    (repo / "main.go").write_text(
        'package main\nimport "fmt"\nfunc main() {}\n',
        encoding="utf-8",
    )
    (repo / "z.ts").write_text(
        'import React from "react";\n',
        encoding="utf-8",
    )
    index_repo(repo, incremental=False)
    return repo


def _domain_graph_repo(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    pages: dict[str, tuple[str, list[str]]],
    edges: list[tuple[str, str, int]],
) -> tuple[Path, dict[str, str]]:
    base = tmp_path / ".codeindex"
    monkeypatch.setenv("LOCI_BASE_DIR", str(base))
    repo = tmp_path / "graph-repo"
    repo.mkdir()
    ids: dict[str, str] = {}
    for file_path, (title, lines) in pages.items():
        path = repo / file_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("\n".join([f"# {title}", *lines]) + "\n", encoding="utf-8")
        ids[file_path] = f"{file_path}::{title}#section"
    index_repo(repo, incremental=False)

    profile_dir = repo / ".loci" / "graph" / "profiles"
    contribution_dir = repo / ".loci" / "graph" / "contributions"
    profile_dir.mkdir(parents=True)
    contribution_dir.mkdir(parents=True)
    (profile_dir / "test.json").write_text(json.dumps({
        "schema_version": 1,
        "namespace": "test",
        "node_rules": [],
        "edge_types": [{
            "type": "links",
            "directed": True,
            "allowed_resolutions": ["declared"],
        }],
        "edge_rules": [],
    }))
    records = []
    for source, target, line in edges:
        records.append({
            "from": ids[source],
            "to": ids[target],
            "type": "links",
            "directed": True,
            "namespace": "test",
            "resolution": "declared",
            "evidence": {
                "file": source,
                "line": line,
                "content_hash": hashlib.sha256((repo / source).read_bytes()).hexdigest(),
            },
        })
    (contribution_dir / "test.json").write_text(json.dumps({
        "schema_version": 1,
        "namespace": "test",
        "nodes": [],
        "edges": records,
    }))
    indexed = index_repo(repo, incremental=True)
    assert indexed["graph_status"] == "healthy"
    return repo, ids


@pytest.fixture
def sample_repo(tmp_path: Path, fixtures_dir: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "sample.py").write_text((fixtures_dir / "sample.py").read_text())
    return repo


def test_service_index_outline_get_round_trip(sample_repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("LOCI_BASE_DIR", str(tmp_path / ".codeindex"))

    indexed = index_repo(sample_repo, incremental=False)
    outline = outline_repo(sample_repo)
    symbol_id = next(
        symbol["id"]
        for entry in outline
        for symbol in entry["symbols"]
        if symbol["name"] == "add"
    )
    results = get_symbols(sample_repo, [symbol_id], context=1)

    assert indexed["symbols_indexed"] > 0
    assert outline[0]["file"] == "sample.py"
    assert len(results) == 1
    assert results[0]["id"] == symbol_id
    assert "def add" in results[0]["source"]
    assert "context_before" in results[0]
    assert "context_after" in results[0]


def test_service_index_warns_on_short_nonempty_markdown_with_zero_symbols(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setenv("LOCI_BASE_DIR", str(tmp_path / ".codeindex"))
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "README.md").write_text("# Heading\n")
    monkeypatch.setattr(service_module, "parse_file", lambda path: [])

    indexed = index_repo(repo, incremental=False)

    assert indexed["warnings"] == [{
        "file": "README.md",
        "lines": 1,
        "reason": "0 symbols extracted",
    }]


def test_service_incremental_reindexes_old_version_metadata(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    base = tmp_path / ".codeindex"
    monkeypatch.setenv("LOCI_BASE_DIR", str(base))
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "idea.md").write_text(
        "---\n"
        "title: Governed Hybrid Retrieval Pipeline\n"
        "tags: [retrieval-governance]\n"
        "description: Build bounded context packs.\n"
        "---\n\n"
        "# Governed Hybrid Retrieval Pipeline\n\n"
        "Body.\n",
        encoding="utf-8",
    )
    index_repo(repo, incremental=False)

    store = IndexStore(base_dir=base)
    index_path = store._index_path(repo.resolve())
    old_index = json.loads(index_path.read_text())
    old_index["schema_version"] = 2
    old_index["extractor_version"] = 2
    for symbol in old_index["symbols"]:
        symbol["metadata"] = {}
        symbol["summary"] = ""
        symbol["keywords"] = []
    index_path.write_text(json.dumps(old_index))

    indexed = index_repo(repo, incremental=True)
    loaded = store.load(repo.resolve())
    markdown_symbols = [s for s in loaded["symbols"] if s["language"] == "markdown"]

    assert indexed["files_skipped"] == 0
    assert markdown_symbols[0]["metadata"]["frontmatter"]["tags"] == ["retrieval-governance"]
    assert markdown_symbols[0]["metadata"]["markdown"]["span_kind"] == "page_root"


def test_service_old_extractor_cache_forces_full_reindex(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    base = tmp_path / ".codeindex"
    monkeypatch.setenv("LOCI_BASE_DIR", str(base))
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "module.py").write_text("VALUE = 1\n", encoding="utf-8")
    index_repo(repo, incremental=False)
    store = IndexStore(base_dir=base)
    index_path = store._index_path(repo.resolve())
    old_index = json.loads(index_path.read_text())
    old_index["extractor_version"] = 5
    index_path.write_text(json.dumps(old_index))

    indexed = index_repo(repo, incremental=True)

    assert indexed["files_skipped"] == 0
    assert store.load(repo.resolve())["extractor_version"] == EXTRACTOR_VERSION


def test_service_markdown_outline_exposes_retrieval_cost_and_repo_relative_ids(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setenv("LOCI_BASE_DIR", str(tmp_path / ".codeindex"))
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "idea.md").write_text(
        "# Governed Hybrid Retrieval Pipeline\n\n"
        "Root body.\n\n"
        "## Proposed Graph Move\n\n"
        "Use page-level governance metadata to route bounded context.\n",
        encoding="utf-8",
    )
    index_repo(repo, incremental=False)

    outline = outline_repo(repo, file="idea.md")
    symbols = outline[0]["symbols"]
    root = next(s for s in symbols if s["name"] == "Governed Hybrid Retrieval Pipeline")
    child = next(s for s in symbols if s["name"] == "Proposed Graph Move")

    assert root["span_kind"] == "page_root"
    assert root["file_bytes"] > 0
    assert root["saved_pct"] >= 0
    assert child["span_kind"] == "section"
    assert child["saved_pct"] > root["saved_pct"]

    store = IndexStore(base_dir=tmp_path / ".codeindex")
    loaded = store.load(repo.resolve())
    loaded_child = next(s for s in loaded["symbols"] if s["name"] == "Proposed Graph Move")
    assert loaded_child["metadata"]["markdown"]["parent_id"] == root["id"]
    assert loaded_child["metadata"]["markdown"]["root_id"] == root["id"]


def test_service_indexes_markdown_contains_edge(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    base = tmp_path / ".codeindex"
    monkeypatch.setenv("LOCI_BASE_DIR", str(base))
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "guide.md").write_text(
        "# Guide\n\n## Install\n\nInstall locally.\n",
        encoding="utf-8",
    )

    indexed = index_repo(repo, incremental=False)
    loaded = IndexStore(base_dir=base).load(repo.resolve())

    assert indexed["graph_edges_indexed"] == 1
    assert loaded is not None
    assert loaded["graph"]["schema_version"] == GRAPH_STATE_SCHEMA_VERSION
    edge = loaded["graph"]["edges"][0]
    assert edge["from"] == "guide.md::Guide#section"
    assert edge["to"] == "guide.md::Guide > Install#section"
    assert edge["type"] == "contains"
    assert edge["resolution"] == "exact"
    assert edge["evidence"]["file"] == "guide.md"
    assert edge["evidence"]["line"] == 3


def test_service_schema_upgrade_rebuilds_graph(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    base = tmp_path / ".codeindex"
    monkeypatch.setenv("LOCI_BASE_DIR", str(base))
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "guide.md").write_text(
        "# Guide\n\n## Install\n\nInstall locally.\n",
        encoding="utf-8",
    )
    index_repo(repo, incremental=False)

    store = IndexStore(base_dir=base)
    index_path = store._index_path(repo.resolve())
    old_index = json.loads(index_path.read_text())
    old_index["schema_version"] = 3
    old_index.pop("graph")
    index_path.write_text(json.dumps(old_index))

    indexed = index_repo(repo, incremental=True)
    loaded = store.load(repo.resolve())

    assert indexed["files_skipped"] == 0
    assert indexed["graph_edges_indexed"] == 1
    assert loaded is not None
    assert loaded["graph"]["schema_version"] == GRAPH_STATE_SCHEMA_VERSION
    assert len(loaded["graph"]["edges"]) == 1


def test_service_graph_state_upgrade_forces_full_reindex(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    base = tmp_path / ".codeindex"
    monkeypatch.setenv("LOCI_BASE_DIR", str(base))
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "consumer.py").write_text("import missing\n", encoding="utf-8")
    index_repo(repo, incremental=False)

    store = IndexStore(base_dir=base)
    index_path = store._index_path(repo.resolve())
    old_index = json.loads(index_path.read_text())
    old_index["graph"]["schema_version"] = GRAPH_STATE_SCHEMA_VERSION - 1
    index_path.write_text(json.dumps(old_index))

    indexed = index_repo(repo, incremental=True)
    loaded = store.load(repo.resolve())

    assert indexed["files_skipped"] == 0
    assert indexed["graph_imports_unresolved"] == 1
    assert loaded is not None
    assert loaded["graph"]["schema_version"] == GRAPH_STATE_SCHEMA_VERSION


def test_service_refresh_repairs_invalid_current_graph_state(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    base = tmp_path / ".codeindex"
    monkeypatch.setenv("LOCI_BASE_DIR", str(base))
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "guide.md").write_text("# Guide\n", encoding="utf-8")
    index_repo(repo, incremental=False)
    store = IndexStore(base_dir=base)
    index_path = store._index_path(repo.resolve())
    corrupted = json.loads(index_path.read_text())
    corrupted["graph"]["input_hashes"] = {"../outside": "bad"}
    index_path.write_text(json.dumps(corrupted))

    refreshed = ensure_fresh_index(repo)
    loaded = store.load(repo.resolve())

    assert refreshed["refreshed"] is True
    assert loaded is not None
    assert loaded["graph"]["input_hashes"] == {}


def test_service_incremental_reindex_recomputes_contains_edges(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    base = tmp_path / ".codeindex"
    monkeypatch.setenv("LOCI_BASE_DIR", str(base))
    repo = tmp_path / "repo"
    repo.mkdir()
    guide = repo / "guide.md"
    guide.write_text(
        "# Guide\n\n## Install\n\nInstall locally.\n",
        encoding="utf-8",
    )
    index_repo(repo, incremental=False)

    guide.write_text(
        "# Guide\n\n## Configure\n\nConfigure locally.\n",
        encoding="utf-8",
    )
    indexed = index_repo(repo, incremental=True)
    loaded = IndexStore(base_dir=base).load(repo.resolve())

    assert indexed["graph_edges_indexed"] == 1
    assert loaded is not None
    edges = loaded["graph"]["edges"]
    assert [edge["to"] for edge in edges] == [
        "guide.md::Guide > Configure#section"
    ]


def test_service_indexes_file_nodes_imports_and_additive_counts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    base = tmp_path / ".codeindex"
    monkeypatch.setenv("LOCI_BASE_DIR", str(base))
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "consumer.py").write_text("import target\n", encoding="utf-8")
    (repo / "target.py").write_text("VALUE = 1\n", encoding="utf-8")

    indexed = index_repo(repo, incremental=False)
    loaded = IndexStore(base_dir=base).load(repo.resolve())

    assert indexed["graph_file_nodes_indexed"] == 2
    assert indexed["graph_imports_indexed"] == 1
    assert indexed["graph_imports_resolved"] == 1
    assert indexed["graph_imports_unresolved"] == 0
    assert loaded is not None
    assert {
        symbol["id"]
        for symbol in loaded["symbols"]
        if symbol["kind"] == "file"
    } == {
        "consumer.py::__file__#file",
        "target.py::__file__#file",
    }
    assert loaded["graph"]["imports"][0]["target_file"] == "target.py"
    assert loaded["graph"]["edges"] == [{
        "from": "consumer.py::__file__#file",
        "to": "target.py::__file__#file",
        "type": "imports",
        "directed": True,
        "namespace": "loci",
        "resolution": "import-resolved",
        "evidence": {
            "file": "consumer.py",
            "line": 1,
            "content_hash": hashlib.sha256(
                (repo / "consumer.py").read_bytes()
            ).hexdigest(),
        },
    }]


def test_graph_imports_returns_stable_sorted_bounded_records(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    repo = _import_read_repo(tmp_path, monkeypatch)

    result = graph_imports(repo, limit=2)

    assert result == {
        "schema_version": GRAPH_SCHEMA_VERSION,
        "repo": str(repo.resolve()),
        "file": None,
        "status": "all",
        "items": [
            {
                "raw": {
                    "source_file": "a.py",
                    "language": "python",
                    "line": 1,
                    "text": "import local_target",
                    "specifier": "local_target",
                    "imported_name": None,
                    "type_only": False,
                    "is_reexport": False,
                    "source_hash": hashlib.sha256(
                        (repo / "a.py").read_bytes()
                    ).hexdigest(),
                    "rust": None,
                },
                "source_file": "a.py",
                "source_id": "a.py::__file__#file",
                "target_file": "local_target.py",
                "target_package": None,
                "target_crate": None,
                "target_kind": "file",
                "target_id": "local_target.py::__file__#file",
                "specifier": "local_target",
                "imported_name": None,
                "language": "python",
                "line": 1,
                "text": "import local_target",
                "type_only": False,
                "is_reexport": False,
                "status": "resolved",
                "resolution": "import-resolved",
                "unresolved_reason": None,
                "resolution_basis": None,
                "resolution_control_files": [],
                "resolution_configuration": None,
            },
            {
                "raw": {
                    "source_file": "a.py",
                    "language": "python",
                    "line": 2,
                    "text": "import missing",
                    "specifier": "missing",
                    "imported_name": None,
                    "type_only": False,
                    "is_reexport": False,
                    "source_hash": hashlib.sha256(
                        (repo / "a.py").read_bytes()
                    ).hexdigest(),
                    "rust": None,
                },
                "source_file": "a.py",
                "source_id": "a.py::__file__#file",
                "target_file": None,
                "target_package": None,
                "target_crate": None,
                "target_kind": None,
                "target_id": None,
                "specifier": "missing",
                "imported_name": None,
                "language": "python",
                "line": 2,
                "text": "import missing",
                "type_only": False,
                "is_reexport": False,
                "status": "unresolved",
                "resolution": None,
                "unresolved_reason": "not_indexed",
                "resolution_basis": None,
                "resolution_control_files": [],
                "resolution_configuration": None,
            },
        ],
        "counts": {
            "total": 4,
            "resolved": 1,
            "unresolved": 3,
            "returned": 2,
        },
        "pagination": {
            "offset": 0,
            "limit": 2,
            "next_offset": 2,
        },
    }


def test_graph_imports_filters_before_counts_status_and_pagination(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    repo = _import_read_repo(tmp_path, monkeypatch)

    result = graph_imports(
        repo,
        file="a.py",
        status="unresolved",
        offset=0,
        limit=1,
    )
    middle = graph_imports(repo, status="unresolved", offset=1, limit=1)
    final = graph_imports(repo, status="unresolved", offset=2, limit=1)
    empty = graph_imports(repo, file="not-indexed.py", status="resolved")

    assert [item["specifier"] for item in result["items"]] == ["missing"]
    assert result["counts"] == {
        "total": 2,
        "resolved": 1,
        "unresolved": 1,
        "returned": 1,
    }
    assert result["pagination"] == {
        "offset": 0,
        "limit": 1,
        "next_offset": None,
    }
    assert [item["specifier"] for item in middle["items"]] == ["fmt"]
    assert middle["pagination"]["next_offset"] == 2
    assert [item["specifier"] for item in final["items"]] == ["react"]
    assert final["pagination"]["next_offset"] is None
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
        ({"file": "../a.py"}, "file"),
        ({"file": "./a.py"}, "file"),
        ({"file": "/a.py"}, "file"),
        ({"file": "a\\b.py"}, "file"),
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
def test_graph_imports_rejects_invalid_filters_and_pagination(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    kwargs: dict[str, object],
    field: str,
):
    repo = _import_read_repo(tmp_path, monkeypatch)

    with pytest.raises(LociError) as exc_info:
        graph_imports(repo, **kwargs)

    assert exc_info.value.code == "INVALID_INPUT"
    assert exc_info.value.details["field"] == field


def test_graph_health_counts_imports_without_degrading_normal_unresolved_records(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    repo = _import_read_repo(tmp_path, monkeypatch)

    health = graph_health(repo)
    unresolved = graph_imports(repo, status="unresolved")

    assert health["status"] == "healthy"
    assert health["counts"] == {
        "profiles": 0,
        "node_overlays": 0,
        "edges": 1,
        "contributions": 0,
        "diagnostics": 0,
        "graph_file_nodes_indexed": 4,
        "graph_go_packages_indexed": 0,
        "graph_rust_crates_indexed": 0,
        "graph_imports_indexed": 4,
        "graph_imports_resolved": 1,
        "graph_imports_unresolved": 3,
    }
    assert health["diagnostics"] == []
    assert {
        item["unresolved_reason"] for item in unresolved["items"]
    } == {"external", "not_indexed"}
    assert all(
        item["target_id"] is None
        and item["target_kind"] is None
        and item["target_package"] is None
        and item["resolution"] is None
        for item in unresolved["items"]
    )


def test_service_full_and_incremental_import_digests_match(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    base = tmp_path / ".codeindex"
    monkeypatch.setenv("LOCI_BASE_DIR", str(base))
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "consumer.py").write_text(
        "from target import VALUE\n",
        encoding="utf-8",
    )
    (repo / "target.py").write_text("VALUE = 1\n", encoding="utf-8")
    store = IndexStore(base_dir=base)

    full = index_repo(repo, incremental=False)
    full_index = store.load(repo.resolve())
    incremental = index_repo(repo, incremental=True)
    incremental_index = store.load(repo.resolve())

    assert full_index is not None
    assert incremental_index is not None
    assert incremental["files_skipped"] == 2

    def import_digest(indexed: dict, loaded: dict) -> str:
        graph = loaded["graph"]
        payload = {
            "counts": {
                key: indexed[key]
                for key in (
                    "graph_file_nodes_indexed",
                    "graph_imports_indexed",
                    "graph_imports_resolved",
                    "graph_imports_unresolved",
                )
            },
            "imports": graph["imports"],
            "edges": [
                edge
                for edge in graph["edges"]
                if edge["namespace"] == "loci"
                and edge["type"] in {"imports", "imports_type"}
            ],
        }
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    assert import_digest(full, full_index) == import_digest(
        incremental,
        incremental_index,
    )


def test_service_indexes_go_package_nodes_records_and_edges(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    base = tmp_path / ".codeindex"
    monkeypatch.setenv("LOCI_BASE_DIR", str(base))
    repo = tmp_path / "repo"
    source = repo / "cmd" / "server" / "main.go"
    target = repo / "internal" / "store" / "store.go"
    source.parent.mkdir(parents=True)
    target.parent.mkdir(parents=True)
    (repo / "go.mod").write_text(
        "module example.com/project\n\ngo 1.23\n",
        encoding="utf-8",
    )
    source.write_text(
        'package main\n\nimport "example.com/project/internal/store"\n',
        encoding="utf-8",
    )
    target.write_text("package store\n", encoding="utf-8")

    indexed = index_repo(repo, incremental=False)
    loaded = IndexStore(base_dir=base).load(repo.resolve())

    assert loaded is not None
    file_nodes = {
        symbol["file_path"]: symbol
        for symbol in loaded["symbols"]
        if symbol["kind"] == "file"
    }
    package_nodes = [
        symbol for symbol in loaded["symbols"] if symbol["kind"] == "package"
    ]
    assert file_nodes["cmd/server/main.go"]["metadata"]["loci"]["go_package"] == {
        "name": "main",
        "line": 1,
    }
    assert file_nodes["internal/store/store.go"]["metadata"]["loci"][
        "go_package"
    ] == {"name": "store", "line": 1}
    assert [node["id"] for node in package_nodes] == [
        "internal/store::example.com/project/internal/store#package"
    ]
    assert indexed["graph_go_packages_indexed"] == 1
    assert indexed["graph_imports_resolved"] == 1
    assert loaded["graph"]["imports"][0]["target_kind"] == "package"
    assert loaded["graph"]["imports"][0]["target_package"] == (
        "example.com/project/internal/store"
    )
    assert loaded["graph"]["edges"] == [{
        "from": "cmd/server/main.go::__file__#file",
        "to": "internal/store::example.com/project/internal/store#package",
        "type": "imports",
        "directed": True,
        "namespace": "loci",
        "resolution": "import-resolved",
        "evidence": {
            "file": "cmd/server/main.go",
            "line": 3,
            "content_hash": hashlib.sha256(source.read_bytes()).hexdigest(),
        },
    }]
    assert loaded["graph"]["diagnostics"] == []

    imports = graph_imports(repo)
    health = graph_health(repo)
    source_id = "cmd/server/main.go::__file__#file"
    package_id = "internal/store::example.com/project/internal/store#package"
    outgoing = graph_traverse_neighbors(repo, [source_id])
    incoming = graph_traverse_neighbors(
        repo,
        [package_id],
        direction="incoming",
    )
    paths = graph_paths(
        repo,
        [source_id],
        [package_id],
        max_hops=1,
        max_nodes=2,
        max_paths=1,
    )
    compatibility = graph_neighbors(repo, [source_id])
    outline = outline_repo(repo, file="internal/store/store.go")
    package_source = get_symbols(repo, [package_id])[0]

    assert imports["items"][0]["target_file"] is None
    assert imports["items"][0]["target_kind"] == "package"
    assert imports["items"][0]["target_package"] == (
        "example.com/project/internal/store"
    )
    assert health["counts"]["graph_go_packages_indexed"] == 1

    package_neighbor = outgoing["results"][0]["neighbors"][0]
    assert package_neighbor["node"] == {
        "id": package_id,
        "namespace": "loci",
        "kind": "package",
        "attributes": {
            "language": "go",
            "file": "internal/store/store.go",
            "line": 1,
            "end_line": 1,
            "import_path": "example.com/project/internal/store",
            "package_name": "store",
            "directory": "internal/store",
        },
    }
    assert package_neighbor["traversed"] == "forward"
    assert package_neighbor["edge"]["from"] == source_id
    assert package_neighbor["edge"]["to"] == package_id

    importing_neighbor = incoming["results"][0]["neighbors"][0]
    assert importing_neighbor["node"]["id"] == source_id
    assert importing_neighbor["traversed"] == "reverse"
    assert importing_neighbor["edge"]["from"] == source_id
    assert importing_neighbor["edge"]["to"] == package_id

    path = paths["paths"][0]
    assert [node["id"] for node in path["nodes"]] == [source_id, package_id]
    assert path["steps"][0]["edge"] == package_neighbor["edge"]
    assert path["steps"][0]["evidence_span"]["content"] == (
        'import "example.com/project/internal/store"\n'
    )
    assert compatibility["results"][0]["neighbors"] == []

    outlined_package = next(
        symbol
        for symbol in outline[0]["symbols"]
        if symbol["kind"] == "package"
    )
    assert outlined_package == {
        "id": package_id,
        "name": "store",
        "kind": "package",
        "line": 1,
        "end_line": 1,
        "signature": "example.com/project/internal/store",
        "summary": "",
    }
    assert package_source["id"] == package_id
    assert package_source["kind"] == "package"
    assert package_source["source"] == ""
    assert package_source["byte_length"] == 0


def test_service_go_control_change_reresolves_unchanged_imports(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    base = tmp_path / ".codeindex"
    monkeypatch.setenv("LOCI_BASE_DIR", str(base))
    repo = tmp_path / "repo"
    repo.mkdir()
    module = repo / "go.mod"
    module.write_text("module example.com/old\n\ngo 1.23\n", encoding="utf-8")
    (repo / "main.go").write_text(
        'package main\n\nimport "example.com/old/store"\n',
        encoding="utf-8",
    )
    store_file = repo / "store" / "store.go"
    store_file.parent.mkdir()
    store_file.write_text("package store\n", encoding="utf-8")
    store = IndexStore(base_dir=base)

    initial = index_repo(repo, incremental=False)
    module.write_text("module example.com/new\n\ngo 1.23\n", encoding="utf-8")
    updated = index_repo(repo, incremental=True)
    loaded = store.load(repo.resolve())

    assert initial["graph_imports_resolved"] == 1
    assert updated["files_skipped"] == 2
    assert updated["graph_imports_resolved"] == 0
    assert updated["graph_imports_unresolved"] == 1
    assert loaded is not None
    assert loaded["graph"]["imports"][0]["unresolved_reason"] == "external"
    assert loaded["graph"]["edges"] == []
    assert [
        symbol["id"]
        for symbol in loaded["symbols"]
        if symbol["kind"] == "package"
    ] == ["store::example.com/new/store#package"]


def test_service_full_and_incremental_go_digests_match(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    base = tmp_path / ".codeindex"
    monkeypatch.setenv("LOCI_BASE_DIR", str(base))
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "go.mod").write_text(
        "module example.com/project\n\ngo 1.23\n",
        encoding="utf-8",
    )
    (repo / "main.go").write_text(
        'package main\n\nimport "example.com/project/store"\n',
        encoding="utf-8",
    )
    target = repo / "store" / "first.go"
    target.parent.mkdir()
    target.write_text("package store\n", encoding="utf-8")
    (target.parent / "second.go").write_text(
        "package store\n",
        encoding="utf-8",
    )
    store = IndexStore(base_dir=base)

    index_repo(repo, incremental=False)
    full = store.load(repo.resolve())
    incremental_result = index_repo(repo, incremental=True)
    incremental = store.load(repo.resolve())

    assert full is not None
    assert incremental is not None
    assert incremental_result["files_skipped"] == 3
    assert full == incremental
    assert sum(
        symbol["kind"] == "package" for symbol in incremental["symbols"]
    ) == 1

    package_id = "store::example.com/project/store#package"
    target.unlink()
    moved_result = index_repo(repo, incremental=True)
    moved = store.load(repo.resolve())

    assert moved_result["graph_imports_resolved"] == 1
    assert moved is not None
    package = next(
        symbol for symbol in moved["symbols"] if symbol["kind"] == "package"
    )
    assert package["id"] == package_id
    assert package["file_path"] == "store/second.go"
    assert moved["graph"]["edges"][0]["to"] == package_id


def test_service_go_package_addition_and_deletion_reresolve_unchanged_import(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    base = tmp_path / ".codeindex"
    monkeypatch.setenv("LOCI_BASE_DIR", str(base))
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "go.mod").write_text(
        "module example.com/project\n\ngo 1.23\n",
        encoding="utf-8",
    )
    (repo / "main.go").write_text(
        'package main\n\nimport "example.com/project/store"\n',
        encoding="utf-8",
    )

    initial = index_repo(repo, incremental=False)
    target = repo / "store" / "store.go"
    target.parent.mkdir()
    target.write_text("package store\n", encoding="utf-8")
    added = index_repo(repo, incremental=True)
    target.unlink()
    removed = index_repo(repo, incremental=True)
    loaded = IndexStore(base_dir=base).load(repo.resolve())

    assert initial["graph_imports_unresolved"] == 1
    assert added["files_skipped"] == 1
    assert added["graph_imports_resolved"] == 1
    assert removed["files_skipped"] == 1
    assert removed["graph_imports_resolved"] == 0
    assert removed["graph_imports_unresolved"] == 1
    assert loaded is not None
    assert loaded["graph"]["imports"][0]["unresolved_reason"] == "not_indexed"
    assert not any(
        symbol["kind"] == "package" for symbol in loaded["symbols"]
    )


def test_service_go_control_add_change_delete_drives_freshness(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    base = tmp_path / ".codeindex"
    monkeypatch.setenv("LOCI_BASE_DIR", str(base))
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "pkg.go").write_text("package pkg\n", encoding="utf-8")
    index_repo(repo, incremental=False)
    module = repo / "go.mod"

    module.write_text("module example.com/one\n\ngo 1.23\n", encoding="utf-8")
    assert ensure_fresh_index(repo)["refreshed"] is True
    assert ensure_fresh_index(repo) == {"repo": str(repo.resolve()), "refreshed": False}

    module.write_text("module example.com/two\n\ngo 1.23\n", encoding="utf-8")
    assert ensure_fresh_index(repo)["refreshed"] is True
    assert ensure_fresh_index(repo) == {"repo": str(repo.resolve()), "refreshed": False}

    module.unlink()
    assert ensure_fresh_index(repo)["refreshed"] is True
    assert ensure_fresh_index(repo) == {"repo": str(repo.resolve()), "refreshed": False}


def test_service_nested_module_add_delete_reassigns_unchanged_package(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    base = tmp_path / ".codeindex"
    monkeypatch.setenv("LOCI_BASE_DIR", str(base))
    repo = tmp_path / "repo"
    target = repo / "nested" / "pkg" / "pkg.go"
    target.parent.mkdir(parents=True)
    (repo / "go.mod").write_text(
        "module example.com/root\n\ngo 1.23\n",
        encoding="utf-8",
    )
    (repo / "main.go").write_text(
        'package main\n\nimport "example.com/root/nested/pkg"\n',
        encoding="utf-8",
    )
    target.write_text("package pkg\n", encoding="utf-8")
    nested_module = repo / "nested" / "go.mod"

    initial = index_repo(repo, incremental=False)
    nested_module.write_text(
        "module example.com/nested\n\ngo 1.23\n",
        encoding="utf-8",
    )
    nested = index_repo(repo, incremental=True)
    nested_module.unlink()
    restored = index_repo(repo, incremental=True)
    loaded = IndexStore(base_dir=base).load(repo.resolve())

    package_id = "nested/pkg::example.com/root/nested/pkg#package"
    assert initial["graph_imports_resolved"] == 1
    assert nested["files_skipped"] == 2
    assert nested["graph_imports_unresolved"] == 1
    assert restored["files_skipped"] == 2
    assert restored["graph_imports_resolved"] == 1
    assert loaded is not None
    assert loaded["graph"]["imports"][0]["target_id"] == package_id
    assert loaded["graph"]["edges"][0]["to"] == package_id


def test_service_workspace_use_add_remove_reresolves_unchanged_import(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setenv("LOCI_BASE_DIR", str(tmp_path / ".codeindex"))
    repo = tmp_path / "repo"
    app = repo / "app"
    lib = repo / "lib"
    app.mkdir(parents=True)
    (lib / "pkg").mkdir(parents=True)
    (app / "go.mod").write_text(
        "module example.com/app\n\ngo 1.23\n",
        encoding="utf-8",
    )
    (lib / "go.mod").write_text(
        "module example.com/lib\n\ngo 1.23\n",
        encoding="utf-8",
    )
    (app / "main.go").write_text(
        'package main\n\nimport "example.com/lib/pkg"\n',
        encoding="utf-8",
    )
    (lib / "pkg" / "pkg.go").write_text("package pkg\n", encoding="utf-8")
    workspace = repo / "go.work"
    workspace.write_text(
        "go 1.23\n\nuse (\n\t./app\n\t./lib\n)\n",
        encoding="utf-8",
    )

    initial = index_repo(repo, incremental=False)
    workspace.write_text("go 1.23\n\nuse ./app\n", encoding="utf-8")
    removed = index_repo(repo, incremental=True)
    workspace.write_text(
        "go 1.23\n\nuse (\n\t./app\n\t./lib\n)\n",
        encoding="utf-8",
    )
    restored = index_repo(repo, incremental=True)

    assert initial["graph_imports_resolved"] == 1
    assert removed["files_skipped"] == 2
    assert removed["graph_imports_unresolved"] == 1
    assert restored["files_skipped"] == 2
    assert restored["graph_imports_resolved"] == 1


def test_service_local_replacement_add_remove_reresolves_unchanged_import(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setenv("LOCI_BASE_DIR", str(tmp_path / ".codeindex"))
    repo = tmp_path / "repo"
    app = repo / "app"
    dep = repo / "dep"
    app.mkdir(parents=True)
    (dep / "client").mkdir(parents=True)
    app_module = app / "go.mod"
    module_without_replacement = (
        "module example.com/app\n\n"
        "go 1.23\n\n"
        "require example.com/dep v1.0.0\n"
    )
    app_module.write_text(module_without_replacement, encoding="utf-8")
    (dep / "go.mod").write_text(
        "module example.com/dep\n\ngo 1.23\n",
        encoding="utf-8",
    )
    (app / "main.go").write_text(
        'package main\n\nimport "example.com/dep/client"\n',
        encoding="utf-8",
    )
    (dep / "client" / "client.go").write_text(
        "package client\n",
        encoding="utf-8",
    )

    initial = index_repo(repo, incremental=False)
    app_module.write_text(
        module_without_replacement + "replace example.com/dep => ../dep\n",
        encoding="utf-8",
    )
    added = index_repo(repo, incremental=True)
    app_module.write_text(module_without_replacement, encoding="utf-8")
    removed = index_repo(repo, incremental=True)

    assert initial["graph_imports_unresolved"] == 1
    assert added["files_skipped"] == 2
    assert added["graph_imports_resolved"] == 1
    assert removed["files_skipped"] == 2
    assert removed["graph_imports_unresolved"] == 1


def test_service_invalid_go_control_is_stable_and_keeps_navigation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    base = tmp_path / ".codeindex"
    monkeypatch.setenv("LOCI_BASE_DIR", str(base))
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "go.mod").write_text("module\n", encoding="utf-8")
    (repo / "pkg.go").write_text(
        "package pkg\n\nfunc Navigate() {}\n",
        encoding="utf-8",
    )

    indexed = index_repo(repo, incremental=False)
    freshness = ensure_fresh_index(repo)
    results = search_symbols(repo, "Navigate")

    assert indexed["graph_status"] == "degraded"
    assert [item["code"] for item in indexed["graph_diagnostics"]] == [
        "GRAPH_GO_MODULE_INVALID"
    ]
    assert freshness == {"repo": str(repo.resolve()), "refreshed": False}
    assert [item["name"] for item in results] == ["Navigate"]


def test_service_conflicting_go_packages_degrade_without_package_node(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    base = tmp_path / ".codeindex"
    monkeypatch.setenv("LOCI_BASE_DIR", str(base))
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "go.mod").write_text(
        "module example.com/project\n\ngo 1.23\n",
        encoding="utf-8",
    )
    (repo / "first.go").write_text("package first\n", encoding="utf-8")
    (repo / "second.go").write_text("package second\n", encoding="utf-8")

    indexed = index_repo(repo, incremental=False)
    loaded = IndexStore(base_dir=base).load(repo.resolve())

    assert indexed["graph_status"] == "degraded"
    assert [item["code"] for item in indexed["graph_diagnostics"]] == [
        "GRAPH_GO_PACKAGE_INVALID"
    ]
    assert loaded is not None
    assert not any(
        symbol["kind"] == "package" for symbol in loaded["symbols"]
    )


def test_service_missing_go_package_declaration_is_diagnostic(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    base = tmp_path / ".codeindex"
    monkeypatch.setenv("LOCI_BASE_DIR", str(base))
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "go.mod").write_text(
        "module example.com/project\n\ngo 1.23\n",
        encoding="utf-8",
    )
    (repo / "broken.go").write_text("func Broken() {}\n", encoding="utf-8")

    indexed = index_repo(repo, incremental=False)
    loaded = IndexStore(base_dir=base).load(repo.resolve())

    assert "GRAPH_GO_PACKAGE_INVALID" in {
        item["code"] for item in indexed["graph_diagnostics"]
    }
    assert loaded is not None
    assert not any(
        symbol["kind"] == "package" for symbol in loaded["symbols"]
    )


def test_service_uses_one_root_scan_for_source_and_language_controls(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setenv("LOCI_BASE_DIR", str(tmp_path / ".codeindex"))
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "go.mod").write_text(
        "module example.com/project\n\ngo 1.23\n",
        encoding="utf-8",
    )
    (repo / "pkg.go").write_text("package pkg\n", encoding="utf-8")
    (repo / "package.json").write_text('{"name":"repo"}', encoding="utf-8")
    (repo / "tsconfig.json").write_text("{}", encoding="utf-8")
    _write_cargo_package(repo, package_name="repo")
    rust_source = repo / "src" / "lib.rs"
    rust_source.parent.mkdir()
    rust_source.write_text("pub fn indexed() {}\n", encoding="utf-8")
    original_rglob = Path.rglob
    root_scans = 0

    def count_root_scan(path: Path, pattern: str):
        nonlocal root_scans
        if path == repo:
            root_scans += 1
        return original_rglob(path, pattern)

    monkeypatch.setattr(Path, "rglob", count_root_scan)

    index_repo(repo, incremental=False)

    assert root_scans == 1


def _write_javascript_workspace_repo(repo: Path, *, export_target: str) -> tuple[Path, Path]:
    (repo / "package.json").write_text(
        json.dumps({"name": "root", "workspaces": ["apps/*", "packages/*"]}),
        encoding="utf-8",
    )
    app = repo / "apps" / "web"
    app.mkdir(parents=True)
    (app / "package.json").write_text(
        json.dumps({
            "name": "@repo/web",
            "dependencies": {"@repo/core": "workspace:*"},
        }),
        encoding="utf-8",
    )
    core = repo / "packages" / "core"
    core.mkdir(parents=True)
    (core / "package.json").write_text(
        json.dumps({
            "name": "@repo/core",
            "exports": {"./format": export_target},
        }),
        encoding="utf-8",
    )
    source = app / "page.ts"
    source.write_text(
        'import {format} from "@repo/core/format";\n',
        encoding="utf-8",
    )
    target = core / "src" / "format.ts"
    target.parent.mkdir()
    target.write_text("export const format = () => 'ok';\n", encoding="utf-8")
    return source, target


def test_service_resolves_workspace_import_and_exposes_control_provenance(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    base = tmp_path / ".codeindex"
    monkeypatch.setenv("LOCI_BASE_DIR", str(base))
    repo = tmp_path / "repo"
    repo.mkdir()
    _write_javascript_workspace_repo(repo, export_target="./src/format.ts")

    indexed = index_repo(repo, incremental=False)
    imports = graph_imports(repo)

    assert indexed["graph_imports_resolved"] == 1
    assert indexed["graph_status"] == "healthy"
    assert imports["items"][0]["target_file"] == "packages/core/src/format.ts"
    assert imports["items"][0]["resolution_basis"] == "workspace_exports"
    assert imports["items"][0]["resolution_control_files"] == [
        "apps/web/package.json",
        "package.json",
        "packages/core/package.json",
    ]


def test_service_javascript_control_change_and_delete_reresolve_unchanged_source(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    base = tmp_path / ".codeindex"
    monkeypatch.setenv("LOCI_BASE_DIR", str(base))
    repo = tmp_path / "repo"
    repo.mkdir()
    source, _ = _write_javascript_workspace_repo(
        repo,
        export_target="./dist/format.js",
    )
    source_hash = hashlib.sha256(source.read_bytes()).hexdigest()

    initial = index_repo(repo, incremental=False)
    core_manifest = repo / "packages" / "core" / "package.json"
    core_manifest.write_text(
        json.dumps({
            "name": "@repo/core",
            "exports": {"./format": "./src/format.ts"},
        }),
        encoding="utf-8",
    )
    changed = index_repo(repo, incremental=True)
    changed_item = graph_imports(repo)["items"][0]
    core_manifest.unlink()
    deleted = index_repo(repo, incremental=True)
    deleted_item = graph_imports(repo)["items"][0]

    assert initial["graph_imports_unresolved"] == 1
    assert changed["files_skipped"] == 2
    assert changed["graph_imports_resolved"] == 1
    assert changed_item["target_file"] == "packages/core/src/format.ts"
    assert hashlib.sha256(source.read_bytes()).hexdigest() == source_hash
    assert deleted["files_skipped"] == 2
    assert deleted["graph_imports_unresolved"] == 1
    assert deleted_item["target_file"] is None


def test_service_invalid_typescript_control_is_stable_and_keeps_navigation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    base = tmp_path / ".codeindex"
    monkeypatch.setenv("LOCI_BASE_DIR", str(base))
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "tsconfig.json").write_text(
        '{"compilerOptions":{},"compilerOptions":{}}',
        encoding="utf-8",
    )
    (repo / "module.ts").write_text(
        "export function Navigate() { return true; }\n",
        encoding="utf-8",
    )

    indexed = index_repo(repo, incremental=False)
    freshness = ensure_fresh_index(repo)
    results = search_symbols(repo, "Navigate")

    assert indexed["graph_status"] == "degraded"
    assert indexed["graph_diagnostics"] == [{
        "severity": "warning",
        "code": "GRAPH_TYPESCRIPT_CONFIG_INVALID",
        "message": "TypeScript project control file is invalid",
        "source": "tsconfig.json",
        "details": {"reason": "duplicate_key"},
    }]
    assert freshness == {"repo": str(repo.resolve()), "refreshed": False}
    assert [item["name"] for item in results] == ["Navigate"]


def test_service_javascript_full_and_incremental_graph_state_match(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    base = tmp_path / ".codeindex"
    monkeypatch.setenv("LOCI_BASE_DIR", str(base))
    repo = tmp_path / "repo"
    repo.mkdir()
    _write_javascript_workspace_repo(repo, export_target="./src/format.ts")
    store = IndexStore(base_dir=base)

    index_repo(repo, incremental=False)
    full_graph = store.load(repo.resolve())["graph"]
    incremental = index_repo(repo, incremental=True)
    incremental_graph = store.load(repo.resolve())["graph"]

    assert incremental["files_skipped"] == 2
    assert incremental_graph == full_graph


def _write_rust_lib_and_bin_repo(repo: Path, *, package_name: str = "app") -> None:
    _write_cargo_package(repo, package_name=package_name)
    source = repo / "src"
    source.mkdir(parents=True, exist_ok=True)
    (source / "lib.rs").write_text("pub struct Thing;\n", encoding="utf-8")
    (source / "main.rs").write_text(
        "use app::Thing;\n\nfn main() {}\n",
        encoding="utf-8",
    )


def _write_cargo_package(repo: Path, *, package_name: str) -> None:
    (repo / "Cargo.toml").write_text(
        (
            "[package]\n"
            f'name = "{package_name}"\n'
            'version = "0.1.0"\n'
            'edition = "2021"\n'
        ),
        encoding="utf-8",
    )


def test_service_indexes_rust_crates_imports_edges_and_retrieval(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    base = tmp_path / ".codeindex"
    monkeypatch.setenv("LOCI_BASE_DIR", str(base))
    repo = tmp_path / "repo"
    repo.mkdir()
    _write_rust_lib_and_bin_repo(repo)

    indexed = index_repo(repo, incremental=False)
    loaded = IndexStore(base_dir=base).load(repo.resolve())
    imports = graph_imports(repo)
    health = graph_health(repo)

    assert loaded is not None
    crate_nodes = [
        symbol for symbol in loaded["symbols"] if symbol["kind"] == "crate"
    ]
    assert [node["id"] for node in crate_nodes] == [
        "Cargo.toml::bin:app#crate",
        "Cargo.toml::lib:app#crate",
    ]
    assert indexed["graph_rust_crates_indexed"] == 2
    assert indexed["graph_imports_resolved"] == 1
    assert health["counts"]["graph_rust_crates_indexed"] == 2

    item = imports["items"][0]
    assert item["raw"]["rust"]["kind"] == "use"
    assert item["target_file"] is None
    assert item["target_package"] is None
    assert item["target_crate"] == "Cargo.toml::lib:app"
    assert item["target_kind"] == "crate"
    assert item["target_id"] == "Cargo.toml::lib:app#crate"
    assert item["resolution_basis"] == "cargo_package_library"
    assert item["resolution_control_files"] == ["Cargo.toml"]
    assert item["resolution_configuration"] == "unconditional"

    source_id = "src/main.rs::__file__#file"
    crate_id = "Cargo.toml::lib:app#crate"
    traversal = graph_traverse_neighbors(
        repo,
        [source_id],
        namespaces=["loci"],
        edge_types=["imports"],
        resolutions=["import-resolved"],
    )
    paths = graph_paths(
        repo,
        [source_id],
        [crate_id],
        namespaces=["loci"],
        edge_types=["imports"],
        resolutions=["import-resolved"],
        max_hops=1,
        max_nodes=2,
        max_paths=1,
    )
    retrieved = graph_retrieve(
        repo,
        "How does the Rust binary import the app library crate?",
        [source_id, crate_id],
        namespaces=["loci"],
        edge_types=["imports"],
        resolutions=["import-resolved"],
        max_hops=1,
        max_nodes=2,
        max_paths=1,
    )

    crate_ref = {
        "id": crate_id,
        "namespace": "loci",
        "kind": "crate",
        "attributes": {
            "language": "rust",
            "file": "src/lib.rs",
            "line": 1,
            "end_line": 1,
            "manifest": "Cargo.toml",
            "package_name": "app",
            "package_root": ".",
            "target_kind": "lib",
            "target_name": "app",
            "crate_name": "app",
            "crate_root": "src/lib.rs",
            "edition": "2021",
            "required_features": [],
        },
    }
    assert traversal["results"][0]["neighbors"][0]["node"] == crate_ref
    assert paths["paths"][0]["nodes"][1] == crate_ref
    assert retrieved["paths"][0]["nodes"][1] == crate_ref

    malformed = json.loads(json.dumps(crate_nodes[-1]))
    malformed["metadata"]["loci"]["package_root"] = "wrong"
    malformed_ref = service_module._graph_node_ref(malformed)
    assert malformed_ref["attributes"] == {
        "language": "rust",
        "file": "src/lib.rs",
        "line": 1,
        "end_line": 1,
    }


def test_service_resolves_contained_cargo_path_dependency(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setenv("LOCI_BASE_DIR", str(tmp_path / ".codeindex"))
    repo = tmp_path / "repo"
    app = repo / "app"
    core = repo / "core"
    (app / "src").mkdir(parents=True)
    (core / "src").mkdir(parents=True)
    (app / "Cargo.toml").write_text(
        (
            '[package]\nname = "app"\nversion = "0.1.0"\nedition = "2021"\n'
            "[dependencies]\n"
            'core_alias = { package = "core", path = "../core" }\n'
        ),
        encoding="utf-8",
    )
    (core / "Cargo.toml").write_text(
        '[package]\nname = "core"\nversion = "0.1.0"\nedition = "2021"\n',
        encoding="utf-8",
    )
    (app / "src" / "lib.rs").write_text(
        "use core_alias::Thing;\n",
        encoding="utf-8",
    )
    (core / "src" / "lib.rs").write_text(
        "pub struct Thing;\n",
        encoding="utf-8",
    )

    indexed = index_repo(repo, incremental=False)
    item = graph_imports(repo)["items"][0]

    assert indexed["graph_rust_crates_indexed"] == 2
    assert indexed["graph_imports_resolved"] == 1
    assert item["target_id"] == "core/Cargo.toml::lib:core#crate"
    assert item["resolution_basis"] == "cargo_path_dependency"
    assert item["resolution_control_files"] == [
        "app/Cargo.toml",
        "core/Cargo.toml",
    ]
    assert item["resolution_configuration"] == "unconditional"


def test_service_invalid_cargo_control_is_stable_and_keeps_navigation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    base = tmp_path / ".codeindex"
    monkeypatch.setenv("LOCI_BASE_DIR", str(base))
    repo = tmp_path / "repo"
    source = repo / "src" / "lib.rs"
    source.parent.mkdir(parents=True)
    (repo / "Cargo.toml").write_text(
        '[package]\nname = "first"\nname = "second"\n',
        encoding="utf-8",
    )
    source.write_text("pub fn navigate() {}\n", encoding="utf-8")

    indexed = index_repo(repo, incremental=False)
    freshness = ensure_fresh_index(repo)
    results = search_symbols(repo, "navigate")

    assert indexed["graph_status"] == "degraded"
    assert indexed["graph_rust_crates_indexed"] == 0
    assert indexed["graph_diagnostics"] == [{
        "severity": "warning",
        "code": "GRAPH_CARGO_MANIFEST_INVALID",
        "message": "Cargo manifest is invalid",
        "source": "Cargo.toml",
        "details": {"reason": "invalid_toml"},
    }]
    assert freshness == {"repo": str(repo.resolve()), "refreshed": False}
    assert [item["name"] for item in results] == ["navigate"]


def test_service_cargo_control_add_change_delete_drives_freshness(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setenv("LOCI_BASE_DIR", str(tmp_path / ".codeindex"))
    repo = tmp_path / "repo"
    source = repo / "src"
    source.mkdir(parents=True)
    (source / "lib.rs").write_text("pub struct Thing;\n", encoding="utf-8")
    (source / "main.rs").write_text(
        "use app::Thing;\n\nfn main() {}\n",
        encoding="utf-8",
    )

    initial = index_repo(repo, incremental=False)
    _write_cargo_package(repo, package_name="app")
    added = ensure_fresh_index(repo)
    added_import = graph_imports(repo)["items"][0]
    _write_cargo_package(repo, package_name="renamed")
    changed = ensure_fresh_index(repo)
    changed_import = graph_imports(repo)["items"][0]
    (repo / "Cargo.toml").unlink()
    deleted = ensure_fresh_index(repo)

    assert initial["graph_rust_crates_indexed"] == 0
    assert initial["graph_imports_unresolved"] == 1
    assert added["refreshed"] is True
    assert added["index"]["files_skipped"] == 2
    assert added["index"]["graph_rust_crates_indexed"] == 2
    assert added_import["target_id"] == "Cargo.toml::lib:app#crate"
    assert changed["refreshed"] is True
    assert changed["index"]["files_skipped"] == 2
    assert changed["index"]["graph_rust_crates_indexed"] == 2
    assert changed_import["status"] == "unresolved"
    assert changed_import["unresolved_reason"] == "external"
    assert deleted["refreshed"] is True
    assert deleted["index"]["files_skipped"] == 2
    assert deleted["index"]["graph_rust_crates_indexed"] == 0
    assert ensure_fresh_index(repo) == {
        "repo": str(repo.resolve()),
        "refreshed": False,
    }


def test_service_rust_source_add_change_delete_reresolves_retained_imports(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setenv("LOCI_BASE_DIR", str(tmp_path / ".codeindex"))
    repo = tmp_path / "repo"
    source = repo / "src"
    source.mkdir(parents=True)
    _write_cargo_package(repo, package_name="app")
    (source / "lib.rs").write_text(
        "pub mod api;\npub use crate::api::Thing;\n",
        encoding="utf-8",
    )

    initial = index_repo(repo, incremental=False)
    target = source / "api.rs"
    target.write_text("pub struct Thing;\n", encoding="utf-8")
    added = ensure_fresh_index(repo)
    added_imports = graph_imports(repo)
    target.write_text("pub struct Thing;\npub struct Changed;\n", encoding="utf-8")
    changed = ensure_fresh_index(repo)
    changed_symbols = search_symbols(repo, "Changed")
    target.unlink()
    deleted = ensure_fresh_index(repo)
    deleted_imports = graph_imports(repo)

    assert initial["graph_imports_resolved"] == 1
    assert initial["graph_imports_unresolved"] == 1
    assert added["refreshed"] is True
    assert added["index"]["files_skipped"] == 1
    assert added["index"]["graph_imports_resolved"] == 2
    assert {item["target_file"] for item in added_imports["items"]} == {
        "src/api.rs"
    }
    assert changed["refreshed"] is True
    assert changed["index"]["files_skipped"] == 1
    assert [item["name"] for item in changed_symbols] == ["Changed"]
    assert deleted["refreshed"] is True
    assert deleted["index"]["files_skipped"] == 1
    assert deleted["index"]["graph_imports_resolved"] == 1
    assert deleted["index"]["graph_imports_unresolved"] == 1
    deleted_by_specifier = {
        item["specifier"]: item for item in deleted_imports["items"]
    }
    assert deleted_by_specifier["api"]["unresolved_reason"] == "not_indexed"
    assert deleted_by_specifier["crate::api::Thing"]["target_id"] == (
        "Cargo.toml::lib:app#crate"
    )


def test_service_rust_full_and_incremental_serialized_indexes_match(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    base = tmp_path / ".codeindex"
    monkeypatch.setenv("LOCI_BASE_DIR", str(base))
    repo = tmp_path / "repo"
    repo.mkdir()
    _write_rust_lib_and_bin_repo(repo)
    store = IndexStore(base_dir=base)

    index_repo(repo, incremental=False)
    full = store.load(repo.resolve())
    incremental_result = index_repo(repo, incremental=True)
    incremental = store.load(repo.resolve())

    assert full is not None
    assert incremental is not None
    assert incremental_result["files_skipped"] == 2
    assert full == incremental
    assert sum(
        symbol["kind"] == "crate" for symbol in incremental["symbols"]
    ) == 2


def test_service_import_state_survives_fresh_process_read(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    base = tmp_path / ".codeindex"
    monkeypatch.setenv("LOCI_BASE_DIR", str(base))
    repo = tmp_path / "repo"
    repo.mkdir()
    source = repo / "consumer.py"
    source.write_text("import target\n", encoding="utf-8")
    (repo / "target.py").write_text("VALUE = 1\n", encoding="utf-8")

    indexed = _run_python_json(
        "import json, sys; "
        "from loci.service import index_repo; "
        "print(json.dumps(index_repo(sys.argv[1], incremental=False), "
        "sort_keys=True))",
        repo,
    )
    reloaded = _run_python_json(
        "import json, sys; "
        "from pathlib import Path; "
        "from loci.storage.index_store import IndexStore; "
        "loaded = IndexStore(base_dir=Path(sys.argv[2])).load("
        "Path(sys.argv[1]).resolve()); "
        "assert loaded is not None; "
        "graph = loaded['graph']; "
        "imports = graph['imports']; "
        "edges = [edge for edge in graph['edges'] "
        "if edge['namespace'] == 'loci' "
        "and edge['type'] in {'imports', 'imports_type'}]; "
        "file_nodes = [symbol for symbol in loaded['symbols'] "
        "if symbol['kind'] == 'file']; "
        "print(json.dumps({'counts': {"
        "'graph_file_nodes_indexed': len(file_nodes), "
        "'graph_imports_indexed': len(imports), "
        "'graph_imports_resolved': sum(record['status'] == 'resolved' "
        "for record in imports), "
        "'graph_imports_unresolved': sum(record['status'] == 'unresolved' "
        "for record in imports)}, 'imports': imports, 'edges': edges}, "
        "sort_keys=True))",
        repo,
        base,
    )

    expected_counts = {
        key: indexed[key]
        for key in (
            "graph_file_nodes_indexed",
            "graph_imports_indexed",
            "graph_imports_resolved",
            "graph_imports_unresolved",
        )
    }
    assert reloaded["counts"] == expected_counts
    assert reloaded["imports"] == [{
        "raw": {
            "source_file": "consumer.py",
            "language": "python",
            "line": 1,
            "text": "import target",
            "specifier": "target",
            "imported_name": None,
            "type_only": False,
            "is_reexport": False,
            "source_hash": hashlib.sha256(source.read_bytes()).hexdigest(),
            "rust": None,
        },
        "source_id": "consumer.py::__file__#file",
        "status": "resolved",
        "target_file": "target.py",
        "target_kind": "file",
        "target_package": None,
        "target_crate": None,
        "target_id": "target.py::__file__#file",
        "unresolved_reason": None,
        "resolution_basis": None,
        "resolution_control_files": [],
        "resolution_configuration": None,
    }]
    assert reloaded["edges"] == [{
        "from": "consumer.py::__file__#file",
        "to": "target.py::__file__#file",
        "type": "imports",
        "directed": True,
        "namespace": "loci",
        "resolution": "import-resolved",
        "evidence": {
            "file": "consumer.py",
            "line": 1,
            "content_hash": hashlib.sha256(source.read_bytes()).hexdigest(),
        },
    }]


def test_service_file_nodes_do_not_suppress_zero_symbol_warnings(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    base = tmp_path / ".codeindex"
    monkeypatch.setenv("LOCI_BASE_DIR", str(base))
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "empty.py").write_text("# comment\n" * 11, encoding="utf-8")
    monkeypatch.setattr(service_module, "parse_file", lambda path: [])

    indexed = index_repo(repo, incremental=False)
    loaded = IndexStore(base_dir=base).load(repo.resolve())

    assert indexed["warnings"] == [{
        "file": "empty.py",
        "lines": 11,
        "reason": "0 symbols extracted",
    }]
    assert indexed["graph_file_nodes_indexed"] == 1
    assert indexed["symbols_indexed"] == 1
    assert loaded is not None
    assert loaded["symbols"][0]["id"] == "empty.py::__file__#file"


def test_service_incremental_addition_resolves_unchanged_source_import(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    base = tmp_path / ".codeindex"
    monkeypatch.setenv("LOCI_BASE_DIR", str(base))
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "consumer.py").write_text("import target\n", encoding="utf-8")

    initial = index_repo(repo, incremental=False)
    (repo / "target.py").write_text("VALUE = 1\n", encoding="utf-8")
    updated = index_repo(repo, incremental=True)
    loaded = IndexStore(base_dir=base).load(repo.resolve())

    assert initial["graph_imports_unresolved"] == 1
    assert updated["files_skipped"] == 1
    assert updated["graph_imports_resolved"] == 1
    assert updated["graph_imports_unresolved"] == 0
    assert loaded is not None
    assert loaded["graph"]["imports"][0]["target_file"] == "target.py"
    assert [edge["type"] for edge in loaded["graph"]["edges"]] == ["imports"]


def test_service_incremental_target_deletion_unresolves_retained_import(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    base = tmp_path / ".codeindex"
    monkeypatch.setenv("LOCI_BASE_DIR", str(base))
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "consumer.py").write_text("import target\n", encoding="utf-8")
    target = repo / "target.py"
    target.write_text("VALUE = 1\n", encoding="utf-8")
    index_repo(repo, incremental=False)

    target.unlink()
    updated = index_repo(repo, incremental=True)
    loaded = IndexStore(base_dir=base).load(repo.resolve())

    assert updated["files_skipped"] == 1
    assert updated["graph_file_nodes_indexed"] == 1
    assert updated["graph_imports_resolved"] == 0
    assert updated["graph_imports_unresolved"] == 1
    assert loaded is not None
    assert loaded["graph"]["edges"] == []
    assert loaded["graph"]["imports"][0]["target_file"] is None
    assert loaded["graph"]["imports"][0]["unresolved_reason"] == "not_indexed"


def test_service_incremental_source_change_replaces_then_deletion_drops_imports(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    base = tmp_path / ".codeindex"
    monkeypatch.setenv("LOCI_BASE_DIR", str(base))
    repo = tmp_path / "repo"
    repo.mkdir()
    consumer = repo / "consumer.py"
    consumer.write_text("import first\n", encoding="utf-8")
    (repo / "first.py").write_text("VALUE = 1\n", encoding="utf-8")
    (repo / "second.py").write_text("VALUE = 2\n", encoding="utf-8")
    index_repo(repo, incremental=False)

    consumer.write_text("import second\n", encoding="utf-8")
    changed = index_repo(repo, incremental=True)
    store = IndexStore(base_dir=base)
    changed_graph = store.load(repo.resolve())["graph"]

    assert changed["files_skipped"] == 2
    assert changed["graph_imports_indexed"] == 1
    assert changed_graph["imports"][0]["raw"]["specifier"] == "second"
    assert changed_graph["imports"][0]["target_file"] == "second.py"
    assert changed_graph["edges"][0]["evidence"]["content_hash"] == hashlib.sha256(
        consumer.read_bytes()
    ).hexdigest()

    consumer.unlink()
    deleted = index_repo(repo, incremental=True)
    deleted_graph = store.load(repo.resolve())["graph"]

    assert deleted["graph_file_nodes_indexed"] == 2
    assert deleted["graph_imports_indexed"] == 0
    assert deleted_graph["imports"] == []
    assert deleted_graph["edges"] == []


def test_service_retains_import_extraction_warning_for_unchanged_source(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    base = tmp_path / ".codeindex"
    monkeypatch.setenv("LOCI_BASE_DIR", str(base))
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "consumer.py").write_text(
        "def keep_navigation():\n    return True\n",
        encoding="utf-8",
    )
    extraction_calls = 0

    def fail_extraction(*args, **kwargs):
        nonlocal extraction_calls
        extraction_calls += 1
        raise ImportExtractionError("broken import parse")

    monkeypatch.setattr(
        service_module,
        "extract_imports",
        fail_extraction,
        raising=False,
    )

    initial = index_repo(repo, incremental=False)
    incremental = index_repo(repo, incremental=True)
    loaded = IndexStore(base_dir=base).load(repo.resolve())
    navigation = search_symbols(repo, "keep_navigation")
    health = graph_health(repo)

    assert extraction_calls == 1
    assert initial["graph_status"] == "degraded"
    assert incremental["files_skipped"] == 1
    assert incremental["graph_status"] == "degraded"
    assert incremental["graph_diagnostics"] == [{
        "severity": "warning",
        "code": "GRAPH_IMPORT_EXTRACTION_FAILED",
        "message": "Import observations could not be extracted",
        "source": "consumer.py",
        "details": {"reason": "broken import parse"},
    }]
    assert loaded is not None
    assert [symbol["name"] for symbol in navigation] == ["keep_navigation"]
    assert health["status"] == "degraded"
    assert loaded["graph"]["imports"] == []


def test_service_materializes_profile_without_leaking_declared_neighbors(
    tmp_path: Path,
    fixtures_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    base = tmp_path / ".codeindex"
    monkeypatch.setenv("LOCI_BASE_DIR", str(base))
    repo = tmp_path / "repo"
    profile_dir = repo / ".loci" / "graph" / "profiles"
    profile_dir.mkdir(parents=True)
    (profile_dir / "generic.json").write_text(
        (fixtures_dir / "graph_profiles" / "generic.json").read_text()
    )
    (repo / "guide.md").write_text(
        "---\nstatus: current\nrelated: [other.md]\n---\n"
        "# Guide\n\n## Child\n\nBody.\n",
        encoding="utf-8",
    )
    (repo / "other.md").write_text("# Other\n", encoding="utf-8")

    indexed = index_repo(repo, incremental=False)
    loaded = IndexStore(base_dir=base).load(repo.resolve())
    neighbors = graph_neighbors(repo, ["guide.md::Guide#section"])

    assert indexed["graph_profiles_loaded"] == 1
    assert indexed["graph_node_overlays_indexed"] == 1
    assert indexed["graph_status"] == "healthy"
    assert loaded is not None
    guide = next(
        symbol for symbol in loaded["symbols"]
        if symbol["id"] == "guide.md::Guide#section"
    )
    assert guide["metadata"]["frontmatter"]["status"] == "current"
    assert loaded["graph"]["nodes"][0]["attributes"] == {"status": "current"}
    assert {edge["type"] for edge in loaded["graph"]["edges"]} == {
        "contains",
        "related_to",
    }
    returned_types = {
        neighbor["edge"]["type"]
        for neighbor in neighbors["results"][0]["neighbors"]
    }
    assert returned_types == {"contains"}
    health = graph_health(repo)
    assert health == {
        "schema_version": GRAPH_SCHEMA_VERSION,
        "repo": str(repo.resolve()),
        "status": "healthy",
        "profiles": [{
            "namespace": "example",
            "source": ".loci/graph/profiles/generic.json",
            "content_hash": loaded["graph"]["profiles"][0]["content_hash"],
            "node_attributes": ["status"],
            "edge_types": [{
                "type": "related_to",
                "directed": True,
                "allowed_resolutions": ["declared"],
            }],
        }],
        "counts": {
            "profiles": 1,
            "node_overlays": 1,
            "edges": 2,
            "contributions": 0,
            "diagnostics": 0,
            "graph_file_nodes_indexed": 0,
            "graph_go_packages_indexed": 0,
            "graph_rust_crates_indexed": 0,
            "graph_imports_indexed": 0,
            "graph_imports_resolved": 0,
            "graph_imports_unresolved": 0,
        },
        "diagnostics": [],
    }


def test_service_profile_addition_triggers_freshness_refresh(
    tmp_path: Path,
    fixtures_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    base = tmp_path / ".codeindex"
    monkeypatch.setenv("LOCI_BASE_DIR", str(base))
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "guide.md").write_text(
        "---\nstatus: current\n---\n# Guide\n",
        encoding="utf-8",
    )
    index_repo(repo, incremental=False)
    profile_dir = repo / ".loci" / "graph" / "profiles"
    profile_dir.mkdir(parents=True)
    (profile_dir / "generic.json").write_text(
        (fixtures_dir / "graph_profiles" / "generic.json").read_text()
    )

    refreshed = ensure_fresh_index(repo)
    loaded = IndexStore(base_dir=base).load(repo.resolve())

    assert refreshed["refreshed"] is True
    assert loaded is not None
    assert loaded["graph"]["nodes"][0]["attributes"] == {"status": "current"}


def test_service_reference_symlink_drift_triggers_refresh(
    tmp_path: Path,
    fixtures_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    base = tmp_path / ".codeindex"
    monkeypatch.setenv("LOCI_BASE_DIR", str(base))
    repo = tmp_path / "repo"
    profile_dir = repo / ".loci" / "graph" / "profiles"
    profile_dir.mkdir(parents=True)
    (profile_dir / "generic.json").write_text(
        (fixtures_dir / "graph_profiles" / "generic.json").read_text()
    )
    (repo / "guide.md").write_text(
        "---\nrelated: [other.md]\n---\n# Guide\n",
        encoding="utf-8",
    )
    other = repo / "other.md"
    other.write_text("# Other\n", encoding="utf-8")
    index_repo(repo, incremental=False)
    outside = tmp_path / "outside.md"
    outside.write_text("# Other\n", encoding="utf-8")
    other.unlink()
    other.symlink_to(outside)

    refreshed = ensure_fresh_index(repo)
    loaded = IndexStore(base_dir=base).load(repo.resolve())

    assert refreshed["refreshed"] is True
    assert loaded is not None
    assert loaded["graph"]["edges"] == []
    assert loaded["graph"]["diagnostics"][0]["code"] == "GRAPH_REFERENCE_UNRESOLVED"


def test_service_reuses_unchanged_contribution_but_revalidates_it(
    tmp_path: Path,
    fixtures_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    base = tmp_path / ".codeindex"
    monkeypatch.setenv("LOCI_BASE_DIR", str(base))
    repo = tmp_path / "repo"
    profile_dir = repo / ".loci" / "graph" / "profiles"
    contribution_dir = repo / ".loci" / "graph" / "contributions"
    profile_dir.mkdir(parents=True)
    contribution_dir.mkdir(parents=True)
    (profile_dir / "generic.json").write_text(
        (fixtures_dir / "graph_profiles" / "generic.json").read_text()
    )
    guide = repo / "guide.md"
    guide.write_text("# Guide\nEvidence\n", encoding="utf-8")
    (repo / "other.md").write_text("# Other\n", encoding="utf-8")
    payload = json.loads(
        (fixtures_dir / "graph_contributions" / "example-valid.json").read_text()
    )
    payload["edges"][0]["evidence"]["content_hash"] = hashlib.sha256(
        guide.read_bytes()
    ).hexdigest()
    (contribution_dir / "example.json").write_text(json.dumps(payload))
    index_repo(repo, incremental=False)

    indexed = index_repo(repo, incremental=True)

    assert indexed["graph_contributions_loaded"] == 1
    assert indexed["graph_contributions_reused"] == 1
    assert indexed["graph_status"] == "healthy"

    guide.write_text("# Guide\nChanged evidence\n", encoding="utf-8")
    reindexed = index_repo(repo, incremental=True)
    loaded = IndexStore(base_dir=base).load(repo.resolve())

    assert reindexed["graph_contributions_reused"] == 1
    assert reindexed["graph_status"] == "degraded"
    assert reindexed["graph_diagnostics"][0]["code"] == "GRAPH_EVIDENCE_STALE"
    assert loaded is not None
    assert loaded["graph"]["edges"] == []

    guide.unlink()
    deleted_evidence = index_repo(repo, incremental=True)

    assert deleted_evidence["graph_contributions_reused"] == 1
    assert deleted_evidence["graph_status"] == "degraded"
    assert deleted_evidence["graph_diagnostics"][0]["code"] == "GRAPH_ENDPOINT_NOT_FOUND"


def test_service_profile_policy_change_revalidates_reused_contribution(
    tmp_path: Path,
    fixtures_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    base = tmp_path / ".codeindex"
    monkeypatch.setenv("LOCI_BASE_DIR", str(base))
    repo = tmp_path / "repo"
    profile_dir = repo / ".loci" / "graph" / "profiles"
    contribution_dir = repo / ".loci" / "graph" / "contributions"
    profile_dir.mkdir(parents=True)
    contribution_dir.mkdir(parents=True)
    profile_path = profile_dir / "generic.json"
    profile = json.loads(
        (fixtures_dir / "graph_profiles" / "generic.json").read_text()
    )
    profile_path.write_text(json.dumps(profile))
    (repo / "other.md").write_text("# Other\n", encoding="utf-8")
    contribution = {
        "schema_version": 1,
        "namespace": "example",
        "nodes": [{
            "id": "other.md::Other#section",
            "namespace": "example",
            "kind": "section",
            "attributes": {"status": "historical"},
        }],
        "edges": [],
    }
    (contribution_dir / "example.json").write_text(json.dumps(contribution))
    index_repo(repo, incremental=False)
    profile["node_rules"][0]["attributes"][0]["allowed_values"] = ["current"]
    profile_path.write_text(json.dumps(profile))

    indexed = index_repo(repo, incremental=True)
    loaded = IndexStore(base_dir=base).load(repo.resolve())

    assert indexed["graph_contributions_reused"] == 1
    assert indexed["graph_status"] == "degraded"
    assert indexed["graph_diagnostics"][0]["code"] == "GRAPH_NODE_ATTRIBUTE_INVALID"
    assert loaded is not None
    assert loaded["graph"]["nodes"] == []


def test_service_extension_deletions_trigger_refresh(
    tmp_path: Path,
    fixtures_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    base = tmp_path / ".codeindex"
    monkeypatch.setenv("LOCI_BASE_DIR", str(base))
    repo = tmp_path / "repo"
    profile_dir = repo / ".loci" / "graph" / "profiles"
    contribution_dir = repo / ".loci" / "graph" / "contributions"
    profile_dir.mkdir(parents=True)
    contribution_dir.mkdir(parents=True)
    profile_path = profile_dir / "generic.json"
    contribution_path = contribution_dir / "example.json"
    profile_path.write_text(
        (fixtures_dir / "graph_profiles" / "generic.json").read_text()
    )
    (repo / "other.md").write_text("# Other\n", encoding="utf-8")
    contribution_path.write_text(json.dumps({
        "schema_version": 1,
        "namespace": "example",
        "nodes": [{
            "id": "other.md::Other#section",
            "namespace": "example",
            "kind": "section",
            "attributes": {"status": "current"},
        }],
        "edges": [],
    }))
    index_repo(repo, incremental=False)

    contribution_path.unlink()
    contribution_refresh = ensure_fresh_index(repo)
    profile_path.unlink()
    profile_refresh = ensure_fresh_index(repo)
    loaded = IndexStore(base_dir=base).load(repo.resolve())

    assert contribution_refresh["refreshed"] is True
    assert profile_refresh["refreshed"] is True
    assert loaded is not None
    assert loaded["graph"]["profiles"] == []
    assert loaded["graph"]["contributions"] == []


def test_service_invalid_profile_degrades_graph_without_hiding_symbols(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    base = tmp_path / ".codeindex"
    monkeypatch.setenv("LOCI_BASE_DIR", str(base))
    repo = tmp_path / "repo"
    profile_dir = repo / ".loci" / "graph" / "profiles"
    profile_dir.mkdir(parents=True)
    (profile_dir / "bad.json").write_text('{"schema_version": 1,')
    (repo / "guide.md").write_text("# Guide\n", encoding="utf-8")

    indexed = index_repo(repo, incremental=False)
    loaded = IndexStore(base_dir=base).load(repo.resolve())

    assert indexed["symbols_indexed"] == 1
    assert indexed["graph_status"] == "degraded"
    assert indexed["graph_diagnostics"][0]["code"] == "INVALID_GRAPH_PROFILE"
    assert loaded is not None
    assert loaded["graph"]["profiles"] == []
    assert graph_health(repo)["status"] == "degraded"


def test_graph_neighbors_returns_seeded_one_hop_with_evidence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setenv("LOCI_BASE_DIR", str(tmp_path / ".codeindex"))
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "guide.md").write_text(
        "# Guide\n\n## Install\n\nInstall locally.\n",
        encoding="utf-8",
    )
    index_repo(repo, incremental=False)

    result = graph_neighbors(repo, ["guide.md::Guide#section"])

    assert result["schema_version"] == GRAPH_SCHEMA_VERSION
    assert result["repo"] == str(repo.resolve())
    assert result["diagnostics"] == []
    seed_result = result["results"][0]
    assert seed_result["seed"] == {
        "id": "guide.md::Guide#section",
        "namespace": "loci",
        "kind": "section",
        "attributes": {
            "language": "markdown",
            "file": "guide.md",
            "line": 1,
            "end_line": 6,
        },
    }
    neighbor = seed_result["neighbors"][0]
    assert neighbor["node"]["id"] == "guide.md::Guide > Install#section"
    assert neighbor["edge"]["from"] == "guide.md::Guide#section"
    assert neighbor["edge"]["to"] == "guide.md::Guide > Install#section"
    assert neighbor["edge"]["evidence"]["file"] == "guide.md"
    assert neighbor["edge"]["evidence"]["line"] == 3
    assert len(neighbor["edge"]["evidence"]["content_hash"]) == 64


def test_graph_neighbors_requires_seed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setenv("LOCI_BASE_DIR", str(tmp_path / ".codeindex"))

    with pytest.raises(LociError) as exc_info:
        graph_neighbors(tmp_path / "repo", [])

    assert exc_info.value.code == "INVALID_INPUT"


def test_graph_neighbors_rejects_unknown_seed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setenv("LOCI_BASE_DIR", str(tmp_path / ".codeindex"))
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "guide.md").write_text("# Guide\n", encoding="utf-8")
    index_repo(repo, incremental=False)

    with pytest.raises(LociError) as exc_info:
        graph_neighbors(
            repo,
            ["guide.md::Guide#section", "guide.md::Missing#section"],
        )

    assert exc_info.value.code == "GRAPH_ENDPOINT_NOT_FOUND"
    assert exc_info.value.details["missing_ids"] == [
        "guide.md::Missing#section"
    ]


def test_graph_neighbors_preserves_seed_order_and_deduplicates(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setenv("LOCI_BASE_DIR", str(tmp_path / ".codeindex"))
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "guide.md").write_text(
        "# Guide\n\n## Install\n\nInstall locally.\n",
        encoding="utf-8",
    )
    index_repo(repo, incremental=False)
    parent_id = "guide.md::Guide#section"
    child_id = "guide.md::Guide > Install#section"

    result = graph_neighbors(repo, [child_id, parent_id, child_id])

    assert [entry["seed"]["id"] for entry in result["results"]] == [
        child_id,
        parent_id,
    ]
    assert result["results"][0]["neighbors"] == []
    assert len(result["results"][1]["neighbors"]) == 1


def test_graph_neighbors_empty_neighbors_is_success(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setenv("LOCI_BASE_DIR", str(tmp_path / ".codeindex"))
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "guide.md").write_text("# Guide\n", encoding="utf-8")
    index_repo(repo, incremental=False)

    result = graph_neighbors(repo, ["guide.md::Guide#section"])

    assert result["results"][0]["neighbors"] == []


def test_graph_anchors_returns_bounded_explained_inferred_envelope(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setenv("LOCI_BASE_DIR", str(tmp_path / ".codeindex"))
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "guide.md").write_text(
        "# Retrieval Guide\n\n"
        "## Query Aware Traversal\n\n"
        "Use a bounded graph walk.\n",
        encoding="utf-8",
    )
    index_repo(repo, incremental=False)

    result = graph_anchors(repo, "How should query aware traversal stay bounded?")

    assert set(result) == {
        "schema_version",
        "repo",
        "question",
        "selection",
        "question_terms",
        "anchors",
        "counts",
        "budget",
        "diagnostics",
    }
    assert result["schema_version"] == GRAPH_SCHEMA_VERSION
    assert result["repo"] == str(repo.resolve())
    assert result["selection"] == "inferred"
    assert result["question_terms"] == ["query", "aware", "traversal", "stay", "bounded"]
    assert len(result["anchors"]) == 1
    anchor = result["anchors"][0]
    assert anchor["node"]["id"] == "guide.md::Retrieval Guide#section"
    assert anchor["matched_symbol_id"] == (
        "guide.md::Retrieval Guide > Query Aware Traversal#section"
    )
    assert anchor["reason"]["kind"] == "inferred"
    assert set(anchor["reason"]["matched_terms"]) >= {"query", "aware", "traversal"}
    assert "symbol_name" in anchor["reason"]["match_scope"]
    assert result["counts"] == {
        "indexed_nodes": 2,
        "eligible_units": 1,
        "qualified_candidates": 1,
        "collapsed_symbols": 1,
        "returned_anchors": 1,
        "omitted_candidates": 0,
    }
    assert result["budget"] == {
        "requested_max_anchors": 10,
        "effective_max_anchors": 1,
    }
    assert result["diagnostics"] == []
    assert "sufficient" not in result
    assert "answerable" not in result


def test_graph_anchors_explicit_seed_overrides_question_and_remains_exact(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setenv("LOCI_BASE_DIR", str(tmp_path / ".codeindex"))
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "guide.md").write_text(
        "# Retrieval Guide\n\n## Install\n\nInstall locally.\n",
        encoding="utf-8",
    )
    index_repo(repo, incremental=False)
    section_id = "guide.md::Retrieval Guide > Install#section"

    result = graph_anchors(
        repo,
        "retrieval guide",
        [section_id, section_id],
        max_anchors=1,
    )

    assert result["selection"] == "explicit"
    assert result["question_terms"] == []
    assert [anchor["node"]["id"] for anchor in result["anchors"]] == [section_id]
    assert result["anchors"][0]["matched_symbol_id"] == section_id
    assert result["anchors"][0]["score"] is None
    assert result["anchors"][0]["reason"] == {
        "kind": "explicit_seed",
        "matched_terms": [],
        "match_scope": [],
    }


def test_graph_anchors_translates_missing_seed_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setenv("LOCI_BASE_DIR", str(tmp_path / ".codeindex"))
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "guide.md").write_text("# Guide\n", encoding="utf-8")
    index_repo(repo, incremental=False)

    with pytest.raises(LociError) as raised:
        graph_anchors(repo, "", ["guide.md::Missing#section"])

    assert raised.value.code == "GRAPH_ENDPOINT_NOT_FOUND"
    assert raised.value.details["missing_ids"] == ["guide.md::Missing#section"]


def test_graph_anchors_preserves_degraded_graph_diagnostics(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setenv("LOCI_BASE_DIR", str(tmp_path / ".codeindex"))
    repo = tmp_path / "repo"
    profiles = repo / ".loci" / "graph" / "profiles"
    profiles.mkdir(parents=True)
    (profiles / "bad.json").write_text("{}", encoding="utf-8")
    (repo / "guide.md").write_text("# Graph Guide\n", encoding="utf-8")
    indexed = index_repo(repo, incremental=False)

    result = graph_anchors(repo, "graph guide")

    assert indexed["graph_status"] == "degraded"
    assert result["anchors"]
    assert result["diagnostics"]
    assert result["diagnostics"][0]["code"] == "INVALID_GRAPH_PROFILE"


def test_graph_traverse_neighbors_filters_direction_and_reports_omissions(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    repo, ids = _domain_graph_repo(
        tmp_path,
        monkeypatch,
        pages={
            "a.md": ("Alpha", ["Alpha links to two pages."]),
            "b.md": ("Beta", ["Beta body."]),
            "c.md": ("Gamma", ["Gamma body."]),
        },
        edges=[("a.md", "b.md", 2), ("a.md", "c.md", 2)],
    )

    outgoing = graph_traverse_neighbors(
        repo,
        [ids["a.md"]],
        namespaces=["test"],
        edge_types=["links"],
        resolutions=["declared"],
        max_neighbors=1,
    )
    incoming = graph_traverse_neighbors(
        repo,
        [ids["b.md"]],
        namespaces=["test"],
        edge_types=["links"],
        resolutions=["declared"],
        direction="incoming",
    )

    assert outgoing["results"][0]["neighbors"][0]["node"]["id"] == ids["b.md"]
    assert outgoing["results"][0]["neighbors"][0]["traversed"] == "forward"
    assert outgoing["results"][0]["returned"] == 1
    assert outgoing["results"][0]["omitted"] == 1
    assert incoming["results"][0]["neighbors"][0]["node"]["id"] == ids["a.md"]
    assert incoming["results"][0]["neighbors"][0]["traversed"] == "reverse"
    assert incoming["results"][0]["neighbors"][0]["edge"]["from"] == ids["a.md"]
    assert incoming["filters"]["direction"] == "incoming"


def test_import_edges_join_generic_defaults_without_widening_exact_neighbors(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setenv("LOCI_BASE_DIR", str(tmp_path / ".codeindex"))
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "consumer.py").write_text("import target\n", encoding="utf-8")
    (repo / "target.py").write_text("VALUE = 1\n", encoding="utf-8")
    index_repo(repo, incremental=False)
    consumer_id = "consumer.py::__file__#file"
    target_id = "target.py::__file__#file"

    outgoing = graph_traverse_neighbors(repo, [consumer_id])
    incoming = graph_traverse_neighbors(
        repo,
        [target_id],
        direction="incoming",
    )
    exact_only = graph_traverse_neighbors(
        repo,
        [consumer_id],
        resolutions=["exact"],
    )
    paths = graph_paths(repo, [consumer_id], [target_id])
    compatibility = graph_neighbors(repo, [consumer_id])

    assert outgoing["filters"]["resolutions"] == [
        "exact",
        "declared",
        "import-resolved",
    ]
    outgoing_neighbor = outgoing["results"][0]["neighbors"][0]
    assert outgoing_neighbor["node"]["id"] == target_id
    assert outgoing_neighbor["traversed"] == "forward"
    assert outgoing_neighbor["edge"]["type"] == "imports"
    assert outgoing_neighbor["edge"]["resolution"] == "import-resolved"

    incoming_neighbor = incoming["results"][0]["neighbors"][0]
    assert incoming_neighbor["node"]["id"] == consumer_id
    assert incoming_neighbor["traversed"] == "reverse"
    assert incoming_neighbor["edge"]["from"] == consumer_id
    assert incoming_neighbor["edge"]["to"] == target_id

    assert exact_only["filters"]["resolutions"] == ["exact"]
    assert exact_only["results"][0]["neighbors"] == []

    assert paths["filters"]["resolutions"] == [
        "exact",
        "declared",
        "import-resolved",
    ]
    step = paths["paths"][0]["steps"][0]
    assert step["edge"]["type"] == "imports"
    assert step["edge"]["resolution"] == "import-resolved"
    assert step["evidence_span"] == {
        "file": "consumer.py",
        "start_line": 1,
        "end_line": 1,
        "content": "import target\n",
    }

    assert compatibility["results"][0]["neighbors"] == []


def test_graph_paths_hydrates_evidence_and_preserves_reverse_direction(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    repo, ids = _domain_graph_repo(
        tmp_path,
        monkeypatch,
        pages={
            "a.md": ("Alpha", ["Alpha explicitly links Beta."]),
            "b.md": ("Beta", ["Beta body."]),
        },
        edges=[("a.md", "b.md", 2)],
    )

    result = graph_paths(
        repo,
        [ids["b.md"]],
        [ids["a.md"]],
        namespaces=["test"],
        edge_types=["links"],
        resolutions=["declared"],
        direction="either",
    )

    assert result["support_kind"] == "edge_sequence"
    assert len(result["paths"]) == 1
    step = result["paths"][0]["steps"][0]
    assert step["traversed"] == "reverse"
    assert step["edge"]["from"] == ids["a.md"]
    assert step["edge"]["to"] == ids["b.md"]
    assert step["evidence_span"] == {
        "file": "a.md",
        "start_line": 2,
        "end_line": 2,
        "content": "Alpha explicitly links Beta.\n",
    }
    assert result["budget"]["evidence_bytes"] > 0
    assert "sufficient" not in result


def test_graph_paths_rejects_whole_path_when_evidence_budget_is_exceeded(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    long_line = "bridge " + ("x" * 1_100)
    repo, ids = _domain_graph_repo(
        tmp_path,
        monkeypatch,
        pages={
            "a.md": ("Alpha", [long_line]),
            "b.md": ("Beta", ["Beta body."]),
        },
        edges=[("a.md", "b.md", 2)],
    )

    result = graph_paths(
        repo,
        [ids["a.md"]],
        [ids["b.md"]],
        namespaces=["test"],
        max_evidence_bytes=1_024,
    )

    assert result["paths"] == []
    assert result["rejected_paths"][0]["reason"] == "EVIDENCE_BUDGET_EXCEEDED"
    assert result["budget"]["evidence_bytes"] == 0


def test_graph_paths_reports_all_missing_endpoints(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    repo, ids = _domain_graph_repo(
        tmp_path,
        monkeypatch,
        pages={"a.md": ("Alpha", ["Body."])},
        edges=[],
    )

    with pytest.raises(LociError) as raised:
        graph_paths(repo, [ids["a.md"], "missing-source"], ["missing-target"])

    assert raised.value.code == "GRAPH_ENDPOINT_NOT_FOUND"
    assert raised.value.details["missing_ids"] == ["missing-source", "missing-target"]


def test_graph_retrieve_selects_direct_authored_edge_without_claiming_sufficiency(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    repo, ids = _domain_graph_repo(
        tmp_path,
        monkeypatch,
        pages={
            "source.md": ("Faithful Source", ["Faithful Source supports Sparse Rule."]),
            "rule.md": ("Sparse Rule", ["Sparse Rule body."]),
        },
        edges=[("source.md", "rule.md", 2)],
    )

    result = graph_retrieve(
        repo,
        "What source supports the Faithful Source and Sparse Rule relationship?",
        [ids["source.md"], ids["rule.md"]],
        namespaces=["test"],
        edge_types=["links"],
        resolutions=["declared"],
    )

    assert result["routing"]["kind"] == "relationship"
    assert result["paths"][0]["support_kind"] == "direct_authored_edge"
    assert result["paths"][0]["semantic_bridge"]["required"] is False
    assert result["paths"][0]["steps"][0]["evidence_span"]["content"]
    assert result["counts"]["duplicate_paths"] >= 1
    assert "sufficient" not in result
    assert "answerable" not in result


def test_graph_retrieve_accepts_meaningful_multi_hop_bridge(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    repo, ids = _domain_graph_repo(
        tmp_path,
        monkeypatch,
        pages={
            "idea.md": ("AI Graph Ideas", ["Incubating ideas through the bridge."]),
            "bridge.md": ("Maintenance Bridge", ["Bridge to durable maintenance."]),
            "brain.md": ("Brain Steward Handoff", ["Handoff body."]),
        },
        edges=[("idea.md", "bridge.md", 2), ("bridge.md", "brain.md", 2)],
    )

    result = graph_retrieve(
        repo,
        "How can incubated AI Graph Ideas become durable Brain Steward maintenance?",
        [ids["idea.md"], ids["brain.md"]],
        namespaces=["test"],
        direction="outgoing",
    )

    selected = next(path for path in result["paths"] if len(path["steps"]) == 2)
    assert selected["support_kind"] == "semantic_bridge"
    assert selected["semantic_bridge"]["matched_terms"]
    assert selected["nodes"][1]["id"] == ids["bridge.md"]


def test_graph_retrieve_does_not_use_endpoint_name_as_bridge_evidence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    repo, ids = _domain_graph_repo(
        tmp_path,
        monkeypatch,
        pages={
            "source.md": ("Support Bridge", ["Support Bridge links Middle."]),
            "middle.md": ("Middle", ["Middle links Target."]),
            "target.md": ("Target", ["Target body."]),
        },
        edges=[("source.md", "middle.md", 2), ("middle.md", "target.md", 2)],
    )

    result = graph_retrieve(
        repo,
        "How does Support Bridge support Target?",
        [ids["source.md"], ids["target.md"]],
        namespaces=["test"],
        direction="outgoing",
    )

    assert result["paths"] == []
    assert result["rejected_paths"][0]["reason"] == "SEMANTIC_BRIDGE_MISSING"


def test_graph_retrieve_rejects_unsupported_hub_shortcut(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    pages = {
        "source.md": ("Code Graph RAG", ["Code Graph RAG links Generic Hub."]),
        "hub.md": ("Generic Hub", ["Generic Hub links Recall Traversal."]),
        "target.md": ("Recall Efficient Wiki Traversal", ["Target body."]),
        **{
            f"extra-{index}.md": (f"Extra {index}", [f"Extra {index} body."])
            for index in range(4)
        },
    }
    edges = [
        ("source.md", "hub.md", 2),
        ("hub.md", "target.md", 2),
        *[("hub.md", f"extra-{index}.md", 2) for index in range(4)],
    ]
    repo, ids = _domain_graph_repo(
        tmp_path,
        monkeypatch,
        pages=pages,
        edges=edges,
    )

    result = graph_retrieve(
        repo,
        "What evidence shows Code Graph RAG improved Recall Efficient Wiki Traversal?",
        [ids["source.md"], ids["target.md"]],
        namespaces=["test"],
        direction="outgoing",
    )

    assert result["paths"] == []
    assert result["rejected_paths"][0]["reason"] == "HUB_SHORTCUT"
    assert result["rejected_paths"][0]["nodes"] == [
        ids["source.md"],
        ids["hub.md"],
        ids["target.md"],
    ]


def test_graph_retrieve_suppresses_inferred_measurement_question(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    repo, _ids = _domain_graph_repo(
        tmp_path,
        monkeypatch,
        pages={
            "result.md": ("Traversal Result", ["A measured result."]),
            "other.md": ("Other", ["Other body."]),
        },
        edges=[("result.md", "other.md", 2)],
    )

    result = graph_retrieve(
        repo,
        "What measured recall improvement did traversal produce?",
        namespaces=["test"],
    )

    assert result["routing"] == {
        "kind": "suppressed",
        "reason": "attribute_or_measurement_question",
    }
    assert result["paths"] == []
    assert result["rejected_paths"] == []


def test_graph_retrieve_does_not_treat_which_as_measurement_by_itself(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    repo, _ids = _domain_graph_repo(
        tmp_path,
        monkeypatch,
        pages={
            "alpha.md": ("Alpha", ["Alpha connects Beta."]),
            "beta.md": ("Beta", ["Beta body."]),
        },
        edges=[("alpha.md", "beta.md", 2)],
    )

    result = graph_retrieve(
        repo,
        "Which page connects Alpha and Beta?",
        namespaces=["test"],
    )

    assert result["routing"] == {
        "kind": "relationship",
        "reason": "relationship_intent",
    }


def test_service_markdown_search_exposes_match_scope_and_cost(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setenv("LOCI_BASE_DIR", str(tmp_path / ".codeindex"))
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "idea.md").write_text(
        "---\n"
        "title: Governed Hybrid Retrieval Pipeline\n"
        "category: Retrieval Governance\n"
        "tags: [retrieval-governance]\n"
        "description: Build bounded context packs.\n"
        "---\n\n"
        "# Governed Hybrid Retrieval Pipeline\n\n"
        "Root body.\n\n"
        "## Proposed Graph Move\n\n"
        "Use page-level governance metadata to route bounded context.\n",
        encoding="utf-8",
    )
    index_repo(repo, incremental=False)

    results = search_symbols(repo, "retrieval-governance", lang="markdown", limit=5)

    child = next(r for r in results if r["name"] == "Proposed Graph Move")
    assert child["span_kind"] == "section"
    assert child["saved_pct"] > 0
    assert "section_summary" in child["match_scope"]
    assert "inherited_page_frontmatter.tags" in child["match_scope"]


def test_service_session_stats_reads_codex_mcp_store_without_env(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    pytest.importorskip("tomllib")

    monkeypatch.delenv("LOCI_BASE_DIR", raising=False)
    codex_home = tmp_path / ".codex"
    mcp_store = tmp_path / "mcp-store"
    codex_home.mkdir()
    (codex_home / "config.toml").write_text(
        "[mcp_servers.loci]\n"
        "command = \"loci-mcp\"\n"
        "[mcp_servers.loci.env]\n"
        f"LOCI_BASE_DIR = \"{mcp_store}\"\n"
    )
    monkeypatch.setenv("CODEX_HOME", str(codex_home))
    IndexStore(base_dir=mcp_store).log_retrieval(
        "src/app.py::run#function",
        20,
        120,
        repo_path="/tmp/repo",
    )

    stats = session_stats()

    assert stats["total_gets"] == 1
    assert stats["store"]["base_dir"] == str(mcp_store)
    assert stats["store"]["source"] == "codex_mcp_config"


def test_service_analyze_includes_store_metadata(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("LOCI_BASE_DIR", str(tmp_path / ".codeindex"))

    result = analyze_usage(since_days=7)

    assert "summary" in result
    assert result["store"]["base_dir"] == str(tmp_path / ".codeindex")
    assert result["store"]["source"] == "env"


def test_service_index_missing_path_raises_structured_error(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("LOCI_BASE_DIR", str(tmp_path / ".codeindex"))

    with pytest.raises(LociError) as exc_info:
        index_repo(tmp_path / "missing", incremental=False)

    assert exc_info.value.code == "PATH_NOT_FOUND"
    assert "path" in exc_info.value.details


def test_service_get_unknown_symbol_raises_structured_error(
    sample_repo: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setenv("LOCI_BASE_DIR", str(tmp_path / ".codeindex"))
    index_repo(sample_repo, incremental=False)

    with pytest.raises(LociError) as exc_info:
        get_symbols(sample_repo, ["sample.py::missing#function"])

    assert exc_info.value.code == "SYMBOL_NOT_FOUND"
    assert exc_info.value.details["symbol_id"] == "sample.py::missing#function"


def test_service_search_file_grep_verify_list(sample_repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("LOCI_BASE_DIR", str(tmp_path / ".codeindex"))
    index_repo(sample_repo, incremental=False)

    search_results = search_symbols(sample_repo, "add", limit=5)
    cached_file = get_cached_file(sample_repo, "sample.py", start_line=4, end_line=5)
    grep_results = grep_repo(sample_repo, r"def add")
    verification = verify_repo(sample_repo)
    repos = list_repos()

    assert any(result["name"] == "add" for result in search_results)
    assert cached_file["file"] == "sample.py"
    assert "def add" in cached_file["content"]
    assert any(result["file"] == "sample.py" for result in grep_results)
    assert verification["failed"] == []
    assert any(repo["path"] == str(sample_repo.resolve()) for repo in repos)


def test_service_verify_valid_markdown_synthetic_sections(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setenv("LOCI_BASE_DIR", str(tmp_path / ".codeindex"))
    repo = tmp_path / "markdown_repo"
    repo.mkdir()
    (repo / "doc.md").write_text(
        "Preamble before the first heading.\n\n"
        "# Real Heading\n\n"
        "Body.\n",
        encoding="utf-8",
    )
    (repo / "flat.md").write_text(
        "A headingless markdown note whose content does not name the file.\n",
        encoding="utf-8",
    )
    index_repo(repo, incremental=False)

    verification = verify_repo(repo)

    assert verification["failed"] == []


def test_service_invalid_grep_pattern_raises_structured_error(
    sample_repo: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setenv("LOCI_BASE_DIR", str(tmp_path / ".codeindex"))
    index_repo(sample_repo, incremental=False)

    with pytest.raises(LociError) as exc_info:
        grep_repo(sample_repo, "[")

    assert exc_info.value.code == "INVALID_REGEX"
