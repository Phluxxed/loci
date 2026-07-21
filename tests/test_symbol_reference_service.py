from __future__ import annotations

from pathlib import Path

import pytest

from loci import service as service_module
from loci.parser.imports import ImportExtractionError
from loci.service import graph_health, index_repo, search_symbols
from loci.storage.index_store import IndexStore


def _write_python_reference_repo(repo: Path) -> None:
    repo.mkdir()
    (repo / "target.py").write_text(
        "class Thing:\n    pass\n\nclass Other:\n    pass\n",
        encoding="utf-8",
    )
    (repo / "consumer.py").write_text(
        "from target import Thing\n\ndef build():\n    return Thing()\n",
        encoding="utf-8",
    )


def _load_graph(base: Path, repo: Path) -> dict:
    index = IndexStore(base_dir=base).load(repo.resolve())
    assert index is not None
    graph = index["graph"]
    assert isinstance(graph, dict)
    return graph


def test_service_indexes_resolved_symbol_references_and_health_counts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    base = tmp_path / ".codeindex"
    monkeypatch.setenv("LOCI_BASE_DIR", str(base))
    repo = tmp_path / "repo"
    _write_python_reference_repo(repo)

    indexed = index_repo(repo, incremental=False)
    graph = _load_graph(base, repo)
    health = graph_health(repo)

    assert indexed["graph_symbol_references_indexed"] == 1
    assert indexed["graph_symbol_references_resolved"] == 1
    assert indexed["graph_symbol_references_unresolved"] == 0
    assert health["counts"]["graph_symbol_references_indexed"] == 1
    assert health["counts"]["graph_symbol_references_resolved"] == 1
    assert health["counts"]["graph_symbol_references_unresolved"] == 0
    assert len(graph["exports"]) == 4
    assert graph["symbol_references"][0]["status"] == "resolved"
    assert graph["symbol_references"][0]["source_id"] == (
        "consumer.py::build#function"
    )
    assert graph["symbol_references"][0]["target_id"] == "target.py::Thing#class"
    assert [
        (edge["type"], edge["from"], edge["to"])
        for edge in graph["edges"]
        if edge["type"] in {"references", "references_type"}
    ] == [(
        "references",
        "consumer.py::build#function",
        "target.py::Thing#class",
    )]


@pytest.mark.parametrize(
    ("reexport", "consumer_import"),
    [
        (
            'export { default } from "elkjs/lib/elk.bundled.js";\n',
            'import ELK from "./elk-runtime.js";\n',
        ),
        (
            'export { ELK } from "elkjs";\n',
            'import { ELK } from "./elk-runtime.js";\n',
        ),
    ],
    ids=("default", "named"),
)
def test_service_preserves_external_reexport_failure_behind_resolved_local_import(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    reexport: str,
    consumer_import: str,
):
    base = tmp_path / ".codeindex"
    monkeypatch.setenv("LOCI_BASE_DIR", str(base))
    repo = tmp_path / "repo"
    source = repo / "src"
    source.mkdir(parents=True)
    (source / "elk-runtime.js").write_text(reexport, encoding="utf-8")
    (source / "layout.ts").write_text(
        consumer_import + "export function layout() { return ELK; }\n",
        encoding="utf-8",
    )
    store = IndexStore(base_dir=base)

    indexed = index_repo(repo, incremental=False)
    full = store.load(repo.resolve())
    incremental_result = index_repo(repo, incremental=True)
    incremental = store.load(repo.resolve())

    assert full is not None
    graph = full["graph"]
    record = next(
        item
        for item in graph["symbol_references"]
        if item["raw"]["source_file"] == "src/layout.ts"
    )
    assert indexed["graph_symbol_references_unresolved"] == 1
    assert record["import_target_id"] == "src/elk-runtime.js::__file__#file"
    assert record["unresolved_reason"] == "import_unresolved"
    assert record["import_unresolved_reason"] == "external"
    assert [
        (support["kind"], support["file"], support["endpoint_id"])
        for support in record["support"]
    ] == [
        (
            "import_binding",
            "src/layout.ts",
            "src/elk-runtime.js::__file__#file",
        ),
        (
            "reexport",
            "src/elk-runtime.js",
            "src/elk-runtime.js::__file__#file",
        ),
    ]
    assert not [
        edge
        for edge in graph["edges"]
        if edge["type"] in {"references", "references_type"}
    ]
    assert incremental_result["files_skipped"] == 2
    assert incremental == full


def test_service_noop_incremental_reuses_reference_evidence_without_reparse(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    base = tmp_path / ".codeindex"
    monkeypatch.setenv("LOCI_BASE_DIR", str(base))
    repo = tmp_path / "repo"
    _write_python_reference_repo(repo)
    store = IndexStore(base_dir=base)

    index_repo(repo, incremental=False)
    full = store.load(repo.resolve())

    def fail_if_reparsed(*args, **kwargs):
        raise AssertionError("unchanged source was reparsed")

    monkeypatch.setattr(service_module, "parse_file", fail_if_reparsed)
    monkeypatch.setattr(
        service_module,
        "extract_import_batch",
        fail_if_reparsed,
        raising=False,
    )
    incremental_result = index_repo(repo, incremental=True)
    incremental = store.load(repo.resolve())

    assert full is not None
    assert incremental is not None
    assert incremental_result["files_skipped"] == 2
    assert incremental_result["graph_symbol_references_resolved"] == 1
    assert incremental == full


def test_service_changed_source_replaces_and_deleted_source_drops_references(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    base = tmp_path / ".codeindex"
    monkeypatch.setenv("LOCI_BASE_DIR", str(base))
    repo = tmp_path / "repo"
    _write_python_reference_repo(repo)
    consumer = repo / "consumer.py"

    index_repo(repo, incremental=False)
    consumer.write_text(
        "from target import Other\n\ndef build():\n    return Other()\n",
        encoding="utf-8",
    )
    changed = index_repo(repo, incremental=True)
    changed_graph = _load_graph(base, repo)

    assert changed["files_skipped"] == 1
    assert changed["graph_symbol_references_resolved"] == 1
    assert changed_graph["symbol_references"][0]["raw"]["path"] == ["Other"]
    assert changed_graph["symbol_references"][0]["target_id"] == (
        "target.py::Other#class"
    )

    consumer.unlink()
    deleted = index_repo(repo, incremental=True)
    deleted_graph = _load_graph(base, repo)

    assert deleted["files_skipped"] == 1
    assert deleted["graph_symbol_references_indexed"] == 0
    assert deleted_graph["symbol_references"] == []
    assert all(
        edge["type"] not in {"references", "references_type"}
        for edge in deleted_graph["edges"]
    )


def test_service_target_addition_and_deletion_reresolve_unchanged_reference(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    base = tmp_path / ".codeindex"
    monkeypatch.setenv("LOCI_BASE_DIR", str(base))
    repo = tmp_path / "repo"
    repo.mkdir()
    target = repo / "target.py"
    target.write_text("class Other:\n    pass\n", encoding="utf-8")
    (repo / "consumer.py").write_text(
        "from target import Thing\n\ndef build():\n    return Thing()\n",
        encoding="utf-8",
    )

    initial = index_repo(repo, incremental=False)
    initial_record = _load_graph(base, repo)["symbol_references"][0]

    target.write_text("class Thing:\n    pass\n", encoding="utf-8")
    added = index_repo(repo, incremental=True)
    added_record = _load_graph(base, repo)["symbol_references"][0]

    target.unlink()
    deleted = index_repo(repo, incremental=True)
    deleted_record = _load_graph(base, repo)["symbol_references"][0]

    assert initial["graph_symbol_references_unresolved"] == 1
    assert initial_record["unresolved_reason"] == "target_not_indexed"
    assert added["files_skipped"] == 1
    assert added["graph_symbol_references_resolved"] == 1
    assert added_record["target_id"] == "target.py::Thing#class"
    assert deleted["files_skipped"] == 1
    assert deleted["graph_symbol_references_unresolved"] == 1
    assert deleted_record["unresolved_reason"] == "import_unresolved"
    assert deleted_record["import_unresolved_reason"] == "not_indexed"


def test_service_reexport_change_reresolves_and_matches_fresh_full_index(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    base = tmp_path / ".codeindex"
    monkeypatch.setenv("LOCI_BASE_DIR", str(base))
    repo = tmp_path / "repo"
    package = repo / "pkg"
    package.mkdir(parents=True)
    reexport = package / "__init__.py"
    reexport.write_text("from .model import Thing\n", encoding="utf-8")
    (package / "model.py").write_text(
        "class Thing:\n    pass\n\nclass Other:\n    pass\n",
        encoding="utf-8",
    )
    (repo / "consumer.py").write_text(
        "from pkg import Thing\n\ndef build():\n    return Thing()\n",
        encoding="utf-8",
    )
    store = IndexStore(base_dir=base)

    initial = index_repo(repo, incremental=False)
    initial_record = _load_graph(base, repo)["symbol_references"][0]

    reexport.write_text("from .model import Other\n", encoding="utf-8")
    changed = index_repo(repo, incremental=True)
    changed_record = _load_graph(base, repo)["symbol_references"][0]

    reexport.write_text("from .model import Thing\n", encoding="utf-8")
    restored = index_repo(repo, incremental=True)
    incremental_index = store.load(repo.resolve())
    index_repo(repo, incremental=False)
    full_index = store.load(repo.resolve())

    assert initial["graph_symbol_references_resolved"] == 1
    assert initial_record["resolution_basis"] == "reexport_chain"
    assert changed["files_skipped"] == 2
    assert changed["graph_symbol_references_unresolved"] == 1
    assert changed_record["unresolved_reason"] == "target_not_indexed"
    assert restored["files_skipped"] == 2
    assert restored["graph_symbol_references_resolved"] == 1
    assert incremental_index == full_index


def test_service_javascript_control_change_reresolves_unchanged_reference(
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
        'export * from "./model.js";\n',
        encoding="utf-8",
    )
    (core / "src" / "model.ts").write_text(
        "export class Thing {}\n",
        encoding="utf-8",
    )
    (web / "src" / "use.ts").write_text(
        (
            'import {Thing} from "@repo/core";\n'
            "export function build() { return Thing; }\n"
        ),
        encoding="utf-8",
    )

    initial = index_repo(repo, incremental=False)
    initial_record = _load_graph(base, repo)["symbol_references"][0]

    web_manifest.write_text(
        '{"name":"@repo/web","dependencies":{"@repo/core":"workspace:*"}}',
        encoding="utf-8",
    )
    added = index_repo(repo, incremental=True)
    added_record = _load_graph(base, repo)["symbol_references"][0]

    web_manifest.write_text('{"name":"@repo/web"}', encoding="utf-8")
    removed = index_repo(repo, incremental=True)
    removed_record = _load_graph(base, repo)["symbol_references"][0]

    assert initial["graph_symbol_references_unresolved"] == 1
    assert initial_record["unresolved_reason"] == "import_unresolved"
    assert added["files_skipped"] == 3
    assert added["graph_symbol_references_resolved"] == 1
    assert added_record["target_id"] == "packages/core/src/model.ts::Thing#class"
    assert added_record["resolution_control_files"] == [
        "apps/web/package.json",
        "package.json",
        "packages/core/package.json",
    ]
    assert removed["files_skipped"] == 3
    assert removed["graph_symbol_references_unresolved"] == 1
    assert removed_record["unresolved_reason"] == "import_unresolved"


def test_service_reference_extraction_failure_is_atomic_stable_and_reused(
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

    def fail_reference_extraction(*args, **kwargs):
        nonlocal extraction_calls
        extraction_calls += 1
        cause = ValueError("references exceeds the per-file limit")
        raise ImportExtractionError(
            "consumer.py reference extraction failed: "
            "references exceeds the per-file limit"
        ) from cause

    monkeypatch.setattr(
        service_module,
        "extract_import_batch",
        fail_reference_extraction,
    )

    initial = index_repo(repo, incremental=False)
    incremental = index_repo(repo, incremental=True)
    graph = _load_graph(base, repo)
    health = graph_health(repo)
    navigation = search_symbols(repo, "keep_navigation")

    expected_diagnostic = {
        "severity": "warning",
        "code": "GRAPH_REFERENCE_EXTRACTION_FAILED",
        "message": "Reference observations could not be extracted",
        "source": "consumer.py",
        "details": {
            "reason": (
                "consumer.py reference extraction failed: "
                "references exceeds the per-file limit"
            ),
        },
    }
    assert extraction_calls == 1
    assert initial["graph_status"] == "degraded"
    assert initial["graph_symbol_references_indexed"] == 0
    assert incremental["files_skipped"] == 1
    assert incremental["graph_diagnostics"] == [expected_diagnostic]
    assert health["status"] == "degraded"
    assert health["diagnostics"] == [expected_diagnostic]
    assert graph["exports"] == []
    assert graph["symbol_references"] == []
    assert [symbol["name"] for symbol in navigation] == ["keep_navigation"]
