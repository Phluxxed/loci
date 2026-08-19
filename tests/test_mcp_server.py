import asyncio
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
from mcp import Client, ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from loci.storage.store_identity import initialize_store


@pytest.fixture(autouse=True)
def _explicit_test_store_namespace(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LOCI_STORE_NAMESPACE", "test")


def test_mcp_process_requires_explicit_store_configuration(tmp_path: Path):
    env = os.environ.copy()
    env.pop("LOCI_BASE_DIR", None)
    env.pop("LOCI_STORE_NAMESPACE", None)

    result = subprocess.run(
        [sys.executable, "-m", "loci.mcp_server"],
        capture_output=True,
        text=True,
        env=env,
        timeout=5,
    )

    assert result.returncode == 78
    error = json.loads(result.stderr)["error"]
    assert error["code"] == "MCP_STORE_CONFIG_MISSING"
    assert error["details"]["missing"] == [
        "LOCI_BASE_DIR",
        "LOCI_STORE_NAMESPACE",
    ]


def test_mcp_process_refuses_store_from_another_namespace(tmp_path: Path):
    root = tmp_path / "index"
    initialize_store(root, "codex")
    env = os.environ.copy()
    env["LOCI_BASE_DIR"] = str(root)
    env["LOCI_STORE_NAMESPACE"] = "claude"

    result = subprocess.run(
        [sys.executable, "-m", "loci.mcp_server"],
        capture_output=True,
        text=True,
        env=env,
        timeout=5,
    )

    assert result.returncode == 78
    error = json.loads(result.stderr)["error"]
    assert error["code"] == "STORE_NAMESPACE_MISMATCH"


def test_mcp_processes_bind_distinct_harness_stores(tmp_path: Path):
    codex_root = tmp_path / "codex-index"
    claude_root = tmp_path / "claude-index"

    codex = asyncio.run(_store_stats(codex_root, "codex"))
    claude = asyncio.run(_store_stats(claude_root, "claude"))

    assert codex["base_dir"] == str(codex_root.resolve())
    assert codex["namespace"] == "codex"
    assert claude["base_dir"] == str(claude_root.resolve())
    assert claude["namespace"] == "claude"
    assert codex["store_id"] != claude["store_id"]


def test_mcp_index_outline_get_round_trip(tmp_path: Path, fixtures_dir: Path):
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "sample.py").write_text((fixtures_dir / "sample.py").read_text())

    result = asyncio.run(_round_trip(repo, tmp_path / ".codeindex"))

    assert result["indexed"]["symbols_indexed"] > 0
    assert result["tools"] == [
        "loci_analyze",
        "loci_file",
        "loci_get",
        "loci_graph_anchors",
        "loci_graph_calls",
        "loci_graph_health",
        "loci_graph_imports",
        "loci_graph_neighbors",
        "loci_graph_paths",
        "loci_graph_references",
        "loci_graph_retrieve",
        "loci_graph_traverse_neighbors",
        "loci_grep",
        "loci_index",
        "loci_list",
        "loci_outline",
        "loci_search",
        "loci_stats",
        "loci_store_health",
        "loci_verify",
    ]
    assert result["outline"]["files"][0]["file"] == "sample.py"
    assert any(symbol["name"] == "add" for symbol in result["search"]["symbols"])
    assert "def add" in result["get"]["symbols"][0]["source"]
    assert "def add" in result["file"]["content"]
    assert result["grep"]["matches"][0]["file"] == "sample.py"
    assert result["anchors"]["selection"] == "inferred"
    assert result["anchors"]["anchors"][0]["node"]["id"] == (
        result["get"]["symbols"][0]["id"]
    )
    assert result["graph"]["results"][0]["neighbors"] == []
    assert result["health"]["status"] == "healthy"
    assert result["health"]["counts"]["profiles"] == 0
    assert result["store_health"]["status"] == "healthy"
    assert result["store_health"]["complete"] is True
    assert result["store_health"]["items"][0]["states"] == ["healthy"]
    assert result["invalid_store_health"]["error"]["code"] == "INVALID_INPUT"
    assert result["verify"]["failed"] == []
    assert any(entry["path"] == str(repo.resolve()) for entry in result["list"]["repos"])
    assert result["stats"]["total_gets"] >= 1
    assert result["stats"]["store"]["base_dir"] == str((tmp_path / ".codeindex").resolve())
    assert result["stats"]["store"]["namespace"] == "test"
    assert result["stats"]["store"]["store_id"]
    assert "summary" in result["analyze"]
    assert result["analyze"]["store"]["base_dir"] == str((tmp_path / ".codeindex").resolve())
    assert result["invalid_grep"]["error"]["code"] == "INVALID_REGEX"


def test_mcp_modern_protocol_index_read_error_round_trip(tmp_path: Path) -> None:
    result = asyncio.run(
        _modern_protocol_round_trip(
            tmp_path / "repo",
            tmp_path / ".codeindex",
        )
    )

    assert result["protocol_version"] == "2026-07-28"
    assert result["indexed"]["symbols_indexed"] > 0
    assert result["outline"]["files"][0]["file"] == "sample.py"
    assert result["error_is_error"] is True
    assert result["error"]["code"] == "INVALID_REGEX"


def test_mcp_legacy_initialize_remains_supported(tmp_path: Path) -> None:
    indexed = asyncio.run(
        _legacy_initialize_round_trip(
            tmp_path / "repo",
            tmp_path / ".codeindex",
        )
    )

    assert indexed["symbols_indexed"] > 0


def test_mcp_repository_scoped_tools_use_one_root_parameter(tmp_path: Path) -> None:
    result = asyncio.run(
        _repository_parameter_round_trip(
            tmp_path / "repo",
            tmp_path / ".codeindex",
        )
    )

    repository_tools = {
        "loci_index",
        "loci_outline",
        "loci_get",
        "loci_graph_anchors",
        "loci_graph_neighbors",
        "loci_graph_traverse_neighbors",
        "loci_graph_paths",
        "loci_graph_retrieve",
        "loci_graph_health",
        "loci_graph_imports",
        "loci_graph_references",
        "loci_graph_calls",
        "loci_search",
        "loci_file",
        "loci_grep",
        "loci_verify",
    }
    for tool_name, schema in result["schemas"].items():
        assert "path" not in schema["properties"], tool_name
        if tool_name in repository_tools:
            assert "repo" in schema["properties"], tool_name
            assert "repo" in schema["required"], tool_name

    file_schema = result["schemas"]["loci_file"]
    assert "file_path" in file_schema["properties"]
    assert "file_path" in file_schema["required"]
    assert "file" not in file_schema["properties"]

    outline_schema = result["schemas"]["loci_outline"]
    assert "file" in outline_schema["properties"]
    assert "file_path" not in outline_schema["properties"]

    store_health_schema = result["schemas"]["loci_store_health"]
    assert "repo" not in store_health_schema["properties"]
    assert set(store_health_schema["properties"]) == {
        "offset",
        "limit",
        "max_catalog_bytes",
        "max_index_bytes",
        "max_probe_paths",
        "max_probe_bytes",
    }

    assert result["canonical"]["indexed"]["symbols_indexed"] > 0
    assert result["canonical"]["outline"]["files"][0]["file"] == "sample.py"
    assert result["canonical"]["verify"]["failed"] == []
    assert result["legacy"]["indexed"]["symbols_indexed"] > 0
    assert result["legacy"]["outline"]["files"][0]["file"] == "sample.py"
    assert result["legacy"]["verify"]["failed"] == []
    assert result["duplicate"]["is_error"] is True
    assert "provide only 'repo'" in result["duplicate"]["message"]


def test_mcp_search_and_grep_expose_honest_coverage(tmp_path: Path):
    result = asyncio.run(
        _query_coverage_round_trip(
            tmp_path / "repo",
            tmp_path / ".codeindex",
        )
    )

    assert result["search_present"]["symbols"]
    assert result["search_absent"]["symbols"] == []
    assert result["grep_present"]["matches"]
    assert result["grep_absent"]["matches"] == []
    search_coverage = result["search_present"]["coverage"]
    grep_coverage = result["grep_present"]["coverage"]
    assert result["search_absent"]["coverage"] == search_coverage
    assert result["grep_absent"]["coverage"] == grep_coverage
    common_coverage = {
        "schema_version": 1,
        "state": "partial",
        "scope": "repository",
        "source_scope": "indexed_supported_source",
        "indexed_files": 1,
        "excluded_paths": 2,
        "exclusions": [
            {
                "reason": "ignored",
                "paths": 1,
                "samples": ["ignored.py"],
                "omitted_samples": 0,
            },
            {
                "reason": "unsupported_file_type",
                "paths": 1,
                "samples": [".gitignore"],
                "omitted_samples": 0,
            },
        ],
        "unknown_reason": None,
    }
    assert search_coverage == {
        **common_coverage,
        "query_scope": "indexed_symbols",
    }
    assert grep_coverage == {
        **common_coverage,
        "query_scope": "indexed_source_text",
    }


def test_mcp_search_file_allowlist_schema_filtering_and_errors(tmp_path: Path):
    result = asyncio.run(
        _search_file_allowlist_round_trip(
            tmp_path / "repo",
            tmp_path / ".codeindex",
        )
    )

    file_paths_schema = result["schema"]["properties"]["file_paths"]
    assert any(
        option.get("type") == "array" and option["items"]["type"] == "string"
        for option in file_paths_schema["anyOf"]
    )
    assert result["unscoped"]["symbols"][0]["file_path"] == "excluded.py"
    assert result["scoped"]["symbols"][0]["file_path"] == "allowed.py"
    assert result["empty"]["symbols"] == []
    assert (
        result["unscoped"]["coverage"]
        == result["scoped"]["coverage"]
        == result["empty"]["coverage"]
    )
    assert result["invalid"]["error"] == {
        "code": "INVALID_INPUT",
        "message": "Each file path must be a normalized repository-relative POSIX path",
        "details": {"field": "file_paths", "index": 0},
    }
    assert result["non_string"]["error"]["code"] == "INVALID_INPUT"
    assert result["non_string"]["error"]["details"] == {
        "field": "file_paths",
        "index": 0,
    }
    assert result["oversized"]["error"]["code"] == "INVALID_INPUT"
    assert result["oversized"]["error"]["details"] == {
        "field": "file_paths",
        "count": 501,
        "maximum": 500,
    }


def test_mcp_loci_mcp_command_round_trip(tmp_path: Path, fixtures_dir: Path):
    if shutil.which("loci-mcp") is None:
        pytest.skip("loci-mcp is not installed on PATH")

    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "sample.py").write_text((fixtures_dir / "sample.py").read_text())

    result = asyncio.run(
        _round_trip(repo, tmp_path / ".codeindex", command="loci-mcp", args=[])
    )

    assert "loci_graph_imports" in result["tools"]
    assert result["indexed"]["symbols_indexed"] > 0
    assert result["verify"]["failed"] == []


def test_mcp_errors_include_loci_error_data(tmp_path: Path):
    error_data = asyncio.run(_outline_missing_repo(tmp_path / ".codeindex", tmp_path / "repo"))

    assert error_data["code"] == "REPO_NOT_INDEXED"
    assert error_data["details"]["repo"] == str((tmp_path / "repo").resolve())


def test_mcp_search_refreshes_stale_index(tmp_path: Path):
    result = asyncio.run(_search_after_repo_change(tmp_path / "repo", tmp_path / ".codeindex"))

    assert any(symbol["name"] == "fresh_symbol" for symbol in result["symbols"])


def test_mcp_grep_refresh_removes_deleted_files(tmp_path: Path):
    result = asyncio.run(_grep_after_indexed_file_deleted(tmp_path / "repo", tmp_path / ".codeindex"))

    assert result["matches"] == []


def test_mcp_markdown_search_and_outline_include_retrieval_cost(tmp_path: Path):
    result = asyncio.run(_markdown_search_and_outline(tmp_path / "repo", tmp_path / ".codeindex"))

    outline_symbols = result["outline"]["files"][0]["symbols"]
    usage = next(symbol for symbol in outline_symbols if symbol["name"] == "Usage")
    search_symbol = result["search"]["symbols"][0]

    assert usage["span_kind"] == "section"
    assert usage["saved_pct"] > 0
    assert search_symbol["span_kind"] in {"page_root", "section"}
    assert search_symbol["file_bytes"] > 0
    assert search_symbol["match_scope"]


def test_mcp_graph_neighbors_survives_fresh_process(tmp_path: Path):
    result = asyncio.run(
        _graph_neighbors_after_restart(
            tmp_path / "repo",
            tmp_path / ".codeindex",
        )
    )

    neighbor = result["valid"]["results"][0]["neighbors"][0]
    assert neighbor["node"]["id"] == "guide.md::Guide > Install#section"
    assert neighbor["edge"]["type"] == "contains"
    assert neighbor["edge"]["resolution"] == "exact"
    assert neighbor["edge"]["evidence"]["file"] == "guide.md"
    assert len(neighbor["edge"]["evidence"]["content_hash"]) == 64


def test_mcp_graph_neighbors_returns_structured_error(tmp_path: Path):
    result = asyncio.run(
        _graph_neighbors_after_restart(
            tmp_path / "repo",
            tmp_path / ".codeindex",
        )
    )

    assert result["invalid"]["error"]["code"] == "GRAPH_ENDPOINT_NOT_FOUND"
    assert result["invalid"]["error"]["details"]["missing_ids"] == [
        "guide.md::Missing#section"
    ]


def test_mcp_graph_health_survives_fresh_process_with_diagnostics(
    tmp_path: Path,
    fixtures_dir: Path,
):
    result = asyncio.run(_graph_health_after_restart(
        tmp_path / "repo",
        tmp_path / ".codeindex",
        fixtures_dir,
    ))

    assert result["status"] == "degraded"
    assert result["profiles"][0]["namespace"] == "example"
    assert result["counts"]["contributions"] == 1
    assert result["diagnostics"][0]["code"] == "INVALID_GRAPH_CONTRIBUTION"


def test_mcp_graph_anchors_survives_fresh_process_and_refreshes(
    tmp_path: Path,
):
    result = asyncio.run(
        _graph_anchors_after_restart(
            tmp_path / "repo",
            tmp_path / ".codeindex",
        )
    )

    assert result["inferred"]["selection"] == "inferred"
    assert result["inferred"]["anchors"][0]["matched_symbol_id"] == (
        "guide.md::Guide > Query Aware Traversal#section"
    )
    assert result["explicit"]["selection"] == "explicit"
    assert result["explicit"]["anchors"][0]["node"]["id"] == (
        "guide.md::Guide > Install#section"
    )
    assert result["invalid"]["error"]["code"] == "GRAPH_ENDPOINT_NOT_FOUND"


def test_mcp_graph_paths_and_retrieve_survive_fresh_process(tmp_path: Path):
    result = asyncio.run(
        _graph_paths_after_restart(
            tmp_path / "repo",
            tmp_path / ".codeindex",
        )
    )

    assert result["paths"]["support_kind"] == "edge_sequence"
    assert result["paths"]["paths"][0]["steps"][0]["evidence_span"]["content"]
    assert result["retrieve"]["paths"][0]["support_kind"] == "direct_authored_edge"
    assert result["neighbors"]["results"][0]["neighbors"][0]["traversed"] == "forward"
    schemas = result["schemas"]
    assert "max_evidence_bytes" in schemas["loci_graph_paths"]["properties"]
    assert "question" in schemas["loci_graph_retrieve"]["required"]
    assert "direction" in schemas["loci_graph_traverse_neighbors"]["properties"]


def test_mcp_graph_imports_contract_survives_fresh_process(tmp_path: Path):
    result = asyncio.run(
        _graph_imports_after_restart(
            tmp_path / "repo",
            tmp_path / ".codeindex",
        )
    )

    schema = result["schema"]
    properties = schema["properties"]
    assert schema["required"] == ["repo"]
    assert set(properties) == {"repo", "file", "status", "offset", "limit"}
    assert properties["repo"]["type"] == "string"
    assert properties["file"]["anyOf"] == [
        {"type": "string"},
        {"type": "null"},
    ]
    assert properties["file"]["default"] is None
    assert properties["status"]["type"] == "string"
    assert properties["status"]["default"] == "all"
    assert properties["offset"]["type"] == "integer"
    assert properties["offset"]["default"] == 0
    assert properties["limit"]["type"] == "integer"
    assert properties["limit"]["default"] == 100

    imports = result["imports"]
    assert imports["counts"] == {
        "total": 2,
        "resolved": 1,
        "unresolved": 1,
        "returned": 2,
    }
    assert [item["specifier"] for item in imports["items"]] == [
        "target",
        "missing",
    ]
    assert imports["items"][0]["target_id"] == "target.py::__file__#file"
    assert imports["items"][0]["target_kind"] == "file"
    assert imports["items"][0]["target_package"] is None
    assert imports["items"][0]["resolution_basis"] is None
    assert imports["items"][0]["resolution_control_files"] == []
    assert imports["items"][1]["unresolved_reason"] == "not_indexed"
    assert imports["items"][1]["target_kind"] is None
    assert imports["items"][1]["target_package"] is None
    assert imports["items"][1]["resolution_basis"] is None
    assert imports["items"][1]["resolution_control_files"] == []

    neighbor = result["neighbors"]["results"][0]["neighbors"][0]
    assert neighbor["node"]["id"] == "target.py::__file__#file"
    assert neighbor["edge"]["type"] == "imports"
    assert neighbor["edge"]["resolution"] == "import-resolved"
    assert neighbor["traversed"] == "forward"

    assert {
        field: error["error"]["details"]["field"]
        for field, error in result["errors"].items()
    } == {
        "status": "status",
        "offset": "offset",
        "limit": "limit",
    }
    assert all(
        error["error"]["code"] == "INVALID_INPUT"
        for error in result["errors"].values()
    )


def test_mcp_javascript_workspace_resolution_survives_fresh_process(
    tmp_path: Path,
):
    result = asyncio.run(
        _javascript_workspace_import_after_restart(
            tmp_path / "repo",
            tmp_path / ".codeindex",
        )
    )

    assert result["input_properties"] == {
        "repo",
        "file",
        "status",
        "offset",
        "limit",
    }
    item = result["imports"]["items"][0]
    assert item["target_file"] == "packages/core/src/format.ts"
    assert item["target_id"] == "packages/core/src/format.ts::__file__#file"
    assert item["resolution_basis"] == "workspace_exports"
    assert item["resolution_control_files"] == [
        "apps/web/package.json",
        "package.json",
        "packages/core/package.json",
    ]
    neighbor = result["neighbors"]["results"][0]["neighbors"][0]
    assert neighbor["node"]["id"] == item["target_id"]
    assert neighbor["edge"]["resolution"] == "import-resolved"


def test_mcp_go_package_target_survives_fresh_process(tmp_path: Path):
    result = asyncio.run(
        _go_package_target_after_restart(
            tmp_path / "repo",
            tmp_path / ".codeindex",
        )
    )

    source_id = "cmd/server/main.go::__file__#file"
    package_id = "internal/store::example.com/project/internal/store#package"
    assert result["tool_names"].count("loci_graph_imports") == 1
    assert set(result["imports_schema"]["properties"]) == {
        "repo",
        "file",
        "status",
        "offset",
        "limit",
    }
    assert result["indexed"]["graph_go_packages_indexed"] == 1
    assert result["health"]["counts"]["graph_go_packages_indexed"] == 1
    assert result["initial_imports"] == result["imports"]
    assert result["initial_outgoing"] == result["outgoing"]

    item = result["imports"]["items"][0]
    assert item["target_file"] is None
    assert item["target_kind"] == "package"
    assert item["target_package"] == "example.com/project/internal/store"
    assert item["target_id"] == package_id

    outgoing = result["outgoing"]["results"][0]["neighbors"][0]
    assert outgoing["node"] == {
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
    assert outgoing["traversed"] == "forward"
    assert outgoing["edge"]["from"] == source_id
    assert outgoing["edge"]["to"] == package_id

    path = result["paths"]["paths"][0]
    assert [node["id"] for node in path["nodes"]] == [source_id, package_id]
    assert path["steps"][0]["edge"] == outgoing["edge"]
    assert path["steps"][0]["evidence_span"]["content"] == (
        'import "example.com/project/internal/store"\n'
    )

    incoming = result["incoming"]["results"][0]["neighbors"][0]
    assert incoming["node"]["id"] == source_id
    assert incoming["traversed"] == "reverse"
    assert incoming["edge"]["from"] == source_id
    assert incoming["edge"]["to"] == package_id
    assert result["compatibility"]["results"][0]["neighbors"] == []


def test_mcp_rust_crate_target_survives_fresh_process(tmp_path: Path):
    result = asyncio.run(
        _rust_crate_target_after_restart(
            tmp_path / "repo",
            tmp_path / ".codeindex",
        )
    )

    source_id = "src/main.rs::__file__#file"
    crate_id = "Cargo.toml::lib:app#crate"
    assert result["tool_names"].count("loci_graph_imports") == 1
    assert set(result["imports_schema"]["properties"]) == {
        "repo",
        "file",
        "status",
        "offset",
        "limit",
    }
    assert result["indexed"]["graph_rust_crates_indexed"] == 2
    assert result["health"]["counts"]["graph_rust_crates_indexed"] == 2
    assert result["initial_imports"] == result["imports"]
    assert result["initial_outgoing"] == result["outgoing"]

    item = result["imports"]["items"][0]
    assert item["raw"]["rust"] == {
        "kind": "use",
        "lexical_module_path": [],
        "lexical_module_visibilities": [],
        "lexical_module_configurations": [],
        "visibility": "private",
        "module_level": True,
        "configuration": "unconditional",
        "path_override": None,
        "inline": False,
    }
    assert item["target_file"] is None
    assert item["target_package"] is None
    assert item["target_crate"] == "Cargo.toml::lib:app"
    assert item["target_kind"] == "crate"
    assert item["target_id"] == crate_id
    assert item["resolution_basis"] == "cargo_package_library"
    assert item["resolution_control_files"] == ["Cargo.toml"]
    assert item["resolution_configuration"] == "unconditional"

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
    outgoing = result["outgoing"]["results"][0]["neighbors"][0]
    assert outgoing["node"] == crate_ref
    assert outgoing["traversed"] == "forward"
    assert outgoing["edge"]["from"] == source_id
    assert outgoing["edge"]["to"] == crate_id
    assert result["paths"]["paths"][0]["nodes"] == [
        {
            "id": source_id,
            "namespace": "loci",
            "kind": "file",
            "attributes": {
                "language": "rust",
                "file": "src/main.rs",
                "line": 1,
                "end_line": 1,
            },
        },
        crate_ref,
    ]
    assert result["retrieved"]["paths"][0]["nodes"][1] == crate_ref
    assert result["compatibility"]["results"][0]["neighbors"] == []


async def _round_trip(
    repo: Path,
    cache_dir: Path,
    command: str | None = None,
    args: list[str] | None = None,
) -> dict[str, Any]:
    env = os.environ.copy()
    env["LOCI_BASE_DIR"] = str(cache_dir)
    env["PYTHONPATH"] = str(Path.cwd() / "src")
    server_params = StdioServerParameters(
        command=command or sys.executable,
        args=args if args is not None else ["-m", "loci.mcp_server"],
        env=env,
        cwd=Path.cwd(),
    )

    async with Client(stdio_client(server_params)) as session:
        tools = await session.list_tools()
        tool_names = sorted(tool.name for tool in tools.tools)

        indexed = await session.call_tool(
            "loci_index",
            arguments={"repo": str(repo), "incremental": False},
        )
        outline = await session.call_tool(
            "loci_outline",
            arguments={"repo": str(repo)},
        )
        symbol_id = next(
            symbol["id"]
            for entry in outline.structured_content["files"]
            for symbol in entry["symbols"]
            if symbol["name"] == "add"
        )
        source = await session.call_tool(
            "loci_get",
            arguments={
                "repo": str(repo),
                "symbol_ids": [symbol_id],
                "context": 1,
            },
        )
        search = await session.call_tool(
            "loci_search",
            arguments={"repo": str(repo), "query": "add", "limit": 5},
        )
        file_result = await session.call_tool(
            "loci_file",
            arguments={
                "repo": str(repo),
                "file_path": "sample.py",
                "start_line": 4,
                "end_line": 5,
            },
        )
        grep = await session.call_tool(
            "loci_grep",
            arguments={"repo": str(repo), "pattern": r"def add"},
        )
        graph = await session.call_tool(
            "loci_graph_neighbors",
            arguments={"repo": str(repo), "seed_ids": [symbol_id]},
        )
        anchors = await session.call_tool(
            "loci_graph_anchors",
            arguments={"repo": str(repo), "question": "add"},
        )
        health = await session.call_tool(
            "loci_graph_health",
            arguments={"repo": str(repo)},
        )
        store_health = await session.call_tool(
            "loci_store_health",
            arguments={"offset": 0, "limit": 10},
        )
        invalid_store_health = await session.call_tool(
            "loci_store_health",
            arguments={"limit": 0},
        )
        assert invalid_store_health.is_error is True
        verify = await session.call_tool(
            "loci_verify",
            arguments={"repo": str(repo)},
        )
        repos = await session.call_tool("loci_list", arguments={})
        stats = await session.call_tool(
            "loci_stats",
            arguments={"repo": str(repo), "since_days": 7},
        )
        analyze = await session.call_tool(
            "loci_analyze",
            arguments={"repo": str(repo), "since_days": 7},
        )
        invalid_grep = await session.call_tool(
            "loci_grep",
            arguments={"repo": str(repo), "pattern": "["},
        )
        assert invalid_grep.is_error is True

    return {
        "tools": tool_names,
        "indexed": indexed.structured_content,
        "outline": outline.structured_content,
        "get": source.structured_content,
        "search": search.structured_content,
        "file": file_result.structured_content,
        "grep": grep.structured_content,
        "anchors": anchors.structured_content,
        "graph": graph.structured_content,
        "health": health.structured_content,
        "store_health": store_health.structured_content,
        "invalid_store_health": invalid_store_health.structured_content,
        "verify": verify.structured_content,
        "list": repos.structured_content,
        "stats": stats.structured_content,
        "analyze": analyze.structured_content,
        "invalid_grep": invalid_grep.structured_content,
    }


async def _modern_protocol_round_trip(
    repo: Path,
    cache_dir: Path,
) -> dict[str, Any]:
    repo.mkdir()
    (repo / "sample.py").write_text("def sample():\n    return 1\n")

    env = os.environ.copy()
    env["LOCI_BASE_DIR"] = str(cache_dir)
    env["LOCI_STORE_NAMESPACE"] = "test"
    env["PYTHONPATH"] = str(Path.cwd() / "src")
    server_params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "loci.mcp_server"],
        env=env,
        cwd=Path.cwd(),
    )

    async with Client(stdio_client(server_params)) as client:
        indexed = await client.call_tool(
            "loci_index",
            {"repo": str(repo), "incremental": False},
        )
        outline = await client.call_tool("loci_outline", {"repo": str(repo)})
        invalid = await client.call_tool(
            "loci_grep",
            {"repo": str(repo), "pattern": "["},
        )

        return {
            "protocol_version": client.protocol_version,
            "indexed": indexed.structured_content,
            "outline": outline.structured_content,
            "error_is_error": invalid.is_error,
            "error": invalid.structured_content["error"],
        }


async def _legacy_initialize_round_trip(
    repo: Path,
    cache_dir: Path,
) -> dict[str, Any]:
    repo.mkdir()
    (repo / "sample.py").write_text("def sample():\n    return 1\n")

    env = os.environ.copy()
    env["LOCI_BASE_DIR"] = str(cache_dir)
    env["LOCI_STORE_NAMESPACE"] = "test"
    env["PYTHONPATH"] = str(Path.cwd() / "src")
    server_params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "loci.mcp_server"],
        env=env,
        cwd=Path.cwd(),
    )

    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            indexed = await session.call_tool(
                "loci_index",
                arguments={"repo": str(repo), "incremental": False},
            )

    assert indexed.structured_content is not None
    return indexed.structured_content


async def _repository_parameter_round_trip(
    repo: Path,
    cache_dir: Path,
) -> dict[str, Any]:
    repo.mkdir()
    (repo / "sample.py").write_text("def sample():\n    return 1\n")

    env = os.environ.copy()
    env["LOCI_BASE_DIR"] = str(cache_dir)
    env["LOCI_STORE_NAMESPACE"] = "test"
    env["PYTHONPATH"] = str(Path.cwd() / "src")
    server_params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "loci.mcp_server"],
        env=env,
        cwd=Path.cwd(),
    )

    async with Client(stdio_client(server_params)) as session:
        tools = await session.list_tools()
        schemas = {tool.name: tool.input_schema for tool in tools.tools}

        indexed = await session.call_tool(
            "loci_index",
            arguments={"repo": str(repo), "incremental": False},
        )
        outline = await session.call_tool(
            "loci_outline",
            arguments={"repo": str(repo)},
        )
        verify = await session.call_tool(
            "loci_verify",
            arguments={"repo": str(repo)},
        )
        legacy_indexed = await session.call_tool(
            "loci_index",
            arguments={"path": str(repo), "incremental": True},
        )
        legacy_outline = await session.call_tool(
            "loci_outline",
            arguments={"path": str(repo)},
        )
        legacy_verify = await session.call_tool(
            "loci_verify",
            arguments={"path": str(repo)},
        )
        duplicate = await session.call_tool(
            "loci_outline",
            arguments={"repo": str(repo), "path": str(repo)},
        )

    return {
        "schemas": schemas,
        "canonical": {
            "indexed": indexed.structured_content,
            "outline": outline.structured_content,
            "verify": verify.structured_content,
        },
        "legacy": {
            "indexed": legacy_indexed.structured_content,
            "outline": legacy_outline.structured_content,
            "verify": legacy_verify.structured_content,
        },
        "duplicate": {
            "is_error": duplicate.is_error,
            "message": duplicate.content[0].text,
        },
    }


async def _store_stats(cache_dir: Path, namespace: str) -> dict[str, Any]:
    env = os.environ.copy()
    env["LOCI_BASE_DIR"] = str(cache_dir)
    env["LOCI_STORE_NAMESPACE"] = namespace
    env["PYTHONPATH"] = str(Path.cwd() / "src")
    server_params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "loci.mcp_server"],
        env=env,
        cwd=Path.cwd(),
    )

    async with Client(stdio_client(server_params)) as session:
        stats = await session.call_tool("loci_stats", arguments={})
        return stats.structured_content["store"]


async def _query_coverage_round_trip(
    repo: Path,
    cache_dir: Path,
) -> dict[str, dict[str, Any]]:
    repo.mkdir()
    (repo / ".gitignore").write_text("ignored.py\n", encoding="utf-8")
    (repo / "source.py").write_text(
        "def present_symbol():\n    return True\n",
        encoding="utf-8",
    )
    (repo / "ignored.py").write_text(
        "def ignored_symbol():\n    return True\n",
        encoding="utf-8",
    )
    env = os.environ.copy()
    env["LOCI_BASE_DIR"] = str(cache_dir)
    env["LOCI_STORE_NAMESPACE"] = "test"
    env["PYTHONPATH"] = str(Path.cwd() / "src")
    server_params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "loci.mcp_server"],
        env=env,
        cwd=Path.cwd(),
    )

    async with Client(stdio_client(server_params)) as session:
        await session.call_tool(
            "loci_index",
            arguments={"repo": str(repo), "incremental": False},
        )
        calls = {
            "search_present": (
                "loci_search",
                {"repo": str(repo), "query": "present_symbol"},
            ),
            "search_absent": (
                "loci_search",
                {"repo": str(repo), "query": "xyzzy_no_match_ever_12345"},
            ),
            "grep_present": (
                "loci_grep",
                {"repo": str(repo), "pattern": "present_symbol"},
            ),
            "grep_absent": (
                "loci_grep",
                {"repo": str(repo), "pattern": "absent_symbol"},
            ),
        }
        results: dict[str, dict[str, Any]] = {}
        for name, (tool, arguments) in calls.items():
            response = await session.call_tool(tool, arguments=arguments)
            results[name] = response.structured_content
        return results


async def _search_file_allowlist_round_trip(
    repo: Path,
    cache_dir: Path,
) -> dict[str, Any]:
    repo.mkdir()
    (repo / "excluded.py").write_text("def target():\n    return True\n")
    (repo / "allowed.py").write_text("def target_helper():\n    return True\n")
    env = os.environ.copy()
    env["LOCI_BASE_DIR"] = str(cache_dir)
    env["LOCI_STORE_NAMESPACE"] = "test"
    env["PYTHONPATH"] = str(Path.cwd() / "src")
    server_params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "loci.mcp_server"],
        env=env,
        cwd=Path.cwd(),
    )

    async with Client(stdio_client(server_params)) as session:
        await session.call_tool(
            "loci_index",
            arguments={"repo": str(repo), "incremental": False},
        )
        tools = await session.list_tools()
        schema = next(tool.input_schema for tool in tools.tools if tool.name == "loci_search")
        unscoped = await session.call_tool(
            "loci_search",
            arguments={"repo": str(repo), "query": "target", "limit": 1},
        )
        scoped = await session.call_tool(
            "loci_search",
            arguments={
                "repo": str(repo),
                "query": "target",
                "limit": 1,
                "file_paths": ["allowed.py", "allowed.py"],
            },
        )
        empty = await session.call_tool(
            "loci_search",
            arguments={"repo": str(repo), "query": "target", "file_paths": []},
        )
        invalid = await session.call_tool(
            "loci_search",
            arguments={"repo": str(repo), "query": "target", "file_paths": ["/absolute.py"]},
        )
        non_string = await session.call_tool(
            "loci_search",
            arguments={"repo": str(repo), "query": "target", "file_paths": [7]},
        )
        oversized = await session.call_tool(
            "loci_search",
            arguments={
                "repo": str(repo),
                "query": "target",
                "file_paths": [f"pages/{index}.md" for index in range(501)],
            },
        )

        assert invalid.is_error is True
        assert non_string.is_error is True
        assert oversized.is_error is True
        return {
            "schema": schema,
            "unscoped": unscoped.structured_content,
            "scoped": scoped.structured_content,
            "empty": empty.structured_content,
            "invalid": invalid.structured_content,
            "non_string": non_string.structured_content,
            "oversized": oversized.structured_content,
        }


async def _graph_neighbors_after_restart(repo: Path, cache_dir: Path) -> dict[str, Any]:
    repo.mkdir()
    (repo / "guide.md").write_text(
        "# Guide\n\n## Install\n\nInstall locally.\n",
        encoding="utf-8",
    )
    env = os.environ.copy()
    env["LOCI_BASE_DIR"] = str(cache_dir)
    env["PYTHONPATH"] = str(Path.cwd() / "src")
    server_params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "loci.mcp_server"],
        env=env,
        cwd=Path.cwd(),
    )

    async with Client(stdio_client(server_params)) as session:
        indexed = await session.call_tool(
            "loci_index",
            arguments={"repo": str(repo), "incremental": False},
        )
        assert indexed.structured_content["graph_edges_indexed"] == 1

    async with Client(stdio_client(server_params)) as session:
        valid = await session.call_tool(
            "loci_graph_neighbors",
            arguments={
                "repo": str(repo),
                "seed_ids": ["guide.md::Guide#section"],
            },
        )
        invalid = await session.call_tool(
            "loci_graph_neighbors",
            arguments={
                "repo": str(repo),
                "seed_ids": ["guide.md::Missing#section"],
            },
        )
        assert invalid.is_error is True
        return {
            "valid": valid.structured_content,
            "invalid": invalid.structured_content,
        }


async def _graph_health_after_restart(
    repo: Path,
    cache_dir: Path,
    fixtures_dir: Path,
) -> dict[str, Any]:
    profile_dir = repo / ".loci" / "graph" / "profiles"
    contribution_dir = repo / ".loci" / "graph" / "contributions"
    profile_dir.mkdir(parents=True)
    contribution_dir.mkdir(parents=True)
    (profile_dir / "generic.json").write_text(
        (fixtures_dir / "graph_profiles" / "generic.json").read_text()
    )
    (contribution_dir / "invalid.json").write_text('{"schema_version": 1,')
    (repo / "guide.md").write_text("# Guide\n", encoding="utf-8")
    env = os.environ.copy()
    env["LOCI_BASE_DIR"] = str(cache_dir)
    env["PYTHONPATH"] = str(Path.cwd() / "src")
    server_params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "loci.mcp_server"],
        env=env,
        cwd=Path.cwd(),
    )

    async with Client(stdio_client(server_params)) as session:
        await session.call_tool(
            "loci_index",
            arguments={"repo": str(repo), "incremental": False},
        )

    async with Client(stdio_client(server_params)) as session:
        health = await session.call_tool(
            "loci_graph_health",
            arguments={"repo": str(repo)},
        )
        return health.structured_content


async def _graph_anchors_after_restart(
    repo: Path,
    cache_dir: Path,
) -> dict[str, Any]:
    repo.mkdir()
    guide = repo / "guide.md"
    guide.write_text(
        "# Guide\n\n## Install\n\nInstall locally.\n",
        encoding="utf-8",
    )
    env = os.environ.copy()
    env["LOCI_BASE_DIR"] = str(cache_dir)
    env["PYTHONPATH"] = str(Path.cwd() / "src")
    server_params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "loci.mcp_server"],
        env=env,
        cwd=Path.cwd(),
    )

    async with Client(stdio_client(server_params)) as session:
        await session.call_tool(
            "loci_index",
            arguments={"repo": str(repo), "incremental": False},
        )

    guide.write_text(
        "# Guide\n\n"
        "## Install\n\nInstall locally.\n\n"
        "## Query Aware Traversal\n\nUse bounded graph anchors.\n",
        encoding="utf-8",
    )
    async with Client(stdio_client(server_params)) as session:
        inferred = await session.call_tool(
            "loci_graph_anchors",
            arguments={
                "repo": str(repo),
                "question": "query aware traversal anchors",
            },
        )
        explicit = await session.call_tool(
            "loci_graph_anchors",
            arguments={
                "repo": str(repo),
                "question": "",
                "seed_ids": ["guide.md::Guide > Install#section"],
            },
        )
        invalid = await session.call_tool(
            "loci_graph_anchors",
            arguments={
                "repo": str(repo),
                "question": "",
                "seed_ids": ["guide.md::Missing#section"],
            },
        )
        assert invalid.is_error is True
        return {
            "inferred": inferred.structured_content,
            "explicit": explicit.structured_content,
            "invalid": invalid.structured_content,
        }


async def _graph_paths_after_restart(
    repo: Path,
    cache_dir: Path,
) -> dict[str, Any]:
    repo.mkdir()
    (repo / "guide.md").write_text(
        "# Guide\n\n## Install\n\nInstall locally.\n",
        encoding="utf-8",
    )
    env = os.environ.copy()
    env["LOCI_BASE_DIR"] = str(cache_dir)
    env["PYTHONPATH"] = str(Path.cwd() / "src")
    server_params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "loci.mcp_server"],
        env=env,
        cwd=Path.cwd(),
    )

    async with Client(stdio_client(server_params)) as session:
        await session.call_tool(
            "loci_index",
            arguments={"repo": str(repo), "incremental": False},
        )

    async with Client(stdio_client(server_params)) as session:
        tools = await session.list_tools()
        schemas = {tool.name: tool.input_schema for tool in tools.tools}
        root_id = "guide.md::Guide#section"
        child_id = "guide.md::Guide > Install#section"
        paths = await session.call_tool(
            "loci_graph_paths",
            arguments={
                "repo": str(repo),
                "source_ids": [root_id],
                "target_ids": [child_id],
                "namespaces": ["loci"],
                "edge_types": ["contains"],
                "resolutions": ["exact"],
            },
        )
        retrieve = await session.call_tool(
            "loci_graph_retrieve",
            arguments={
                "repo": str(repo),
                "question": "How are Guide and Install related?",
                "seed_ids": [root_id, child_id],
                "namespaces": ["loci"],
                "edge_types": ["contains"],
                "resolutions": ["exact"],
            },
        )
        neighbors = await session.call_tool(
            "loci_graph_traverse_neighbors",
            arguments={
                "repo": str(repo),
                "seed_ids": [root_id],
                "namespaces": ["loci"],
                "edge_types": ["contains"],
                "resolutions": ["exact"],
            },
        )
        return {
            "paths": paths.structured_content,
            "retrieve": retrieve.structured_content,
            "neighbors": neighbors.structured_content,
            "schemas": schemas,
        }


async def _graph_imports_after_restart(
    repo: Path,
    cache_dir: Path,
) -> dict[str, Any]:
    repo.mkdir()
    (repo / "consumer.py").write_text(
        "import target\nimport missing\n",
        encoding="utf-8",
    )
    (repo / "target.py").write_text("VALUE = 1\n", encoding="utf-8")
    env = os.environ.copy()
    env["LOCI_BASE_DIR"] = str(cache_dir)
    env["PYTHONPATH"] = str(Path.cwd() / "src")
    server_params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "loci.mcp_server"],
        env=env,
        cwd=Path.cwd(),
    )

    async with Client(stdio_client(server_params)) as session:
        indexed = await session.call_tool(
            "loci_index",
            arguments={"repo": str(repo), "incremental": False},
        )
        assert indexed.structured_content["graph_imports_resolved"] == 1
        assert indexed.structured_content["graph_imports_unresolved"] == 1

    async with Client(stdio_client(server_params)) as session:
        tools = await session.list_tools()
        schema = next(
            tool.input_schema
            for tool in tools.tools
            if tool.name == "loci_graph_imports"
        )
        imports = await session.call_tool(
            "loci_graph_imports",
            arguments={"repo": str(repo)},
        )
        neighbors = await session.call_tool(
            "loci_graph_traverse_neighbors",
            arguments={
                "repo": str(repo),
                "seed_ids": ["consumer.py::__file__#file"],
                "namespaces": ["loci"],
                "edge_types": ["imports"],
                "resolutions": ["import-resolved"],
            },
        )
        errors = {}
        for field, arguments in (
            ("status", {"status": "invalid"}),
            ("offset", {"offset": -1}),
            ("limit", {"limit": 501}),
        ):
            error = await session.call_tool(
                "loci_graph_imports",
                arguments={"repo": str(repo), **arguments},
            )
            assert error.is_error is True
            errors[field] = error.structured_content

        return {
            "schema": schema,
            "imports": imports.structured_content,
            "neighbors": neighbors.structured_content,
            "errors": errors,
        }


async def _javascript_workspace_import_after_restart(
    repo: Path,
    cache_dir: Path,
) -> dict[str, Any]:
    source = repo / "apps" / "web" / "page.ts"
    target = repo / "packages" / "core" / "src" / "format.ts"
    source.parent.mkdir(parents=True)
    target.parent.mkdir(parents=True)
    (repo / "package.json").write_text(
        json.dumps({"name": "root", "workspaces": ["apps/*", "packages/*"]}),
        encoding="utf-8",
    )
    (source.parent / "package.json").write_text(
        json.dumps({
            "name": "@repo/web",
            "dependencies": {"@repo/core": "workspace:*"},
        }),
        encoding="utf-8",
    )
    core_manifest = repo / "packages" / "core" / "package.json"
    core_manifest.write_text(
        json.dumps({
            "name": "@repo/core",
            "exports": {"./format": "./src/format.ts"},
        }),
        encoding="utf-8",
    )
    source.write_text(
        'import {format} from "@repo/core/format";\n',
        encoding="utf-8",
    )
    target.write_text("export const format = () => 'ok';\n", encoding="utf-8")
    env = os.environ.copy()
    env["LOCI_BASE_DIR"] = str(cache_dir)
    env["PYTHONPATH"] = str(Path.cwd() / "src")
    server_params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "loci.mcp_server"],
        env=env,
        cwd=Path.cwd(),
    )
    source_id = "apps/web/page.ts::__file__#file"

    async with Client(stdio_client(server_params)) as session:
        indexed = await session.call_tool(
            "loci_index",
            arguments={"repo": str(repo), "incremental": False},
        )
        assert indexed.structured_content["graph_imports_resolved"] == 1

    async with Client(stdio_client(server_params)) as session:
        tools = await session.list_tools()
        imports_tool = next(
            tool for tool in tools.tools if tool.name == "loci_graph_imports"
        )
        imports = await session.call_tool(
            "loci_graph_imports",
            arguments={"repo": str(repo)},
        )
        neighbors = await session.call_tool(
            "loci_graph_traverse_neighbors",
            arguments={
                "repo": str(repo),
                "seed_ids": [source_id],
                "namespaces": ["loci"],
                "edge_types": ["imports"],
                "resolutions": ["import-resolved"],
            },
        )
        return {
            "input_properties": set(imports_tool.input_schema["properties"]),
            "imports": imports.structured_content,
            "neighbors": neighbors.structured_content,
        }


async def _go_package_target_after_restart(
    repo: Path,
    cache_dir: Path,
) -> dict[str, Any]:
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
    env = os.environ.copy()
    env["LOCI_BASE_DIR"] = str(cache_dir)
    env["PYTHONPATH"] = str(Path.cwd() / "src")
    server_params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "loci.mcp_server"],
        env=env,
        cwd=Path.cwd(),
    )
    source_id = "cmd/server/main.go::__file__#file"
    package_id = "internal/store::example.com/project/internal/store#package"

    async with Client(stdio_client(server_params)) as session:
        indexed = await session.call_tool(
            "loci_index",
            arguments={"repo": str(repo), "incremental": False},
        )
        initial_imports = await session.call_tool(
            "loci_graph_imports",
            arguments={"repo": str(repo)},
        )
        initial_outgoing = await session.call_tool(
            "loci_graph_traverse_neighbors",
            arguments={
                "repo": str(repo),
                "seed_ids": [source_id],
                "namespaces": ["loci"],
                "edge_types": ["imports"],
                "resolutions": ["import-resolved"],
            },
        )

    async with Client(stdio_client(server_params)) as session:
        tools = await session.list_tools()
        imports_tool = next(
            tool for tool in tools.tools if tool.name == "loci_graph_imports"
        )
        imports = await session.call_tool(
            "loci_graph_imports",
            arguments={"repo": str(repo)},
        )
        health = await session.call_tool(
            "loci_graph_health",
            arguments={"repo": str(repo)},
        )
        outgoing = await session.call_tool(
            "loci_graph_traverse_neighbors",
            arguments={
                "repo": str(repo),
                "seed_ids": [source_id],
                "namespaces": ["loci"],
                "edge_types": ["imports"],
                "resolutions": ["import-resolved"],
            },
        )
        incoming = await session.call_tool(
            "loci_graph_traverse_neighbors",
            arguments={
                "repo": str(repo),
                "seed_ids": [package_id],
                "namespaces": ["loci"],
                "edge_types": ["imports"],
                "resolutions": ["import-resolved"],
                "direction": "incoming",
            },
        )
        paths = await session.call_tool(
            "loci_graph_paths",
            arguments={
                "repo": str(repo),
                "source_ids": [source_id],
                "target_ids": [package_id],
                "namespaces": ["loci"],
                "edge_types": ["imports"],
                "resolutions": ["import-resolved"],
                "max_hops": 1,
                "max_nodes": 2,
                "max_paths": 1,
            },
        )
        compatibility = await session.call_tool(
            "loci_graph_neighbors",
            arguments={"repo": str(repo), "seed_ids": [source_id]},
        )
        return {
            "indexed": indexed.structured_content,
            "initial_imports": initial_imports.structured_content,
            "initial_outgoing": initial_outgoing.structured_content,
            "tool_names": [tool.name for tool in tools.tools],
            "imports_schema": imports_tool.input_schema,
            "imports": imports.structured_content,
            "health": health.structured_content,
            "outgoing": outgoing.structured_content,
            "incoming": incoming.structured_content,
            "paths": paths.structured_content,
            "compatibility": compatibility.structured_content,
        }


async def _rust_crate_target_after_restart(
    repo: Path,
    cache_dir: Path,
) -> dict[str, Any]:
    source = repo / "src" / "main.rs"
    target = repo / "src" / "lib.rs"
    source.parent.mkdir(parents=True)
    (repo / "Cargo.toml").write_text(
        (
            "[package]\n"
            'name = "app"\n'
            'version = "0.1.0"\n'
            'edition = "2021"\n'
        ),
        encoding="utf-8",
    )
    source.write_text("use app::Thing;\n\nfn main() {}\n", encoding="utf-8")
    target.write_text("pub struct Thing;\n", encoding="utf-8")
    env = os.environ.copy()
    env["LOCI_BASE_DIR"] = str(cache_dir)
    env["PYTHONPATH"] = str(Path.cwd() / "src")
    server_params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "loci.mcp_server"],
        env=env,
        cwd=Path.cwd(),
    )
    source_id = "src/main.rs::__file__#file"
    crate_id = "Cargo.toml::lib:app#crate"

    async with Client(stdio_client(server_params)) as session:
        indexed = await session.call_tool(
            "loci_index",
            arguments={"repo": str(repo), "incremental": False},
        )
        initial_imports = await session.call_tool(
            "loci_graph_imports",
            arguments={"repo": str(repo)},
        )
        initial_outgoing = await session.call_tool(
            "loci_graph_traverse_neighbors",
            arguments={
                "repo": str(repo),
                "seed_ids": [source_id],
                "namespaces": ["loci"],
                "edge_types": ["imports"],
                "resolutions": ["import-resolved"],
            },
        )

    async with Client(stdio_client(server_params)) as session:
        tools = await session.list_tools()
        imports_tool = next(
            tool for tool in tools.tools if tool.name == "loci_graph_imports"
        )
        imports = await session.call_tool(
            "loci_graph_imports",
            arguments={"repo": str(repo)},
        )
        health = await session.call_tool(
            "loci_graph_health",
            arguments={"repo": str(repo)},
        )
        outgoing = await session.call_tool(
            "loci_graph_traverse_neighbors",
            arguments={
                "repo": str(repo),
                "seed_ids": [source_id],
                "namespaces": ["loci"],
                "edge_types": ["imports"],
                "resolutions": ["import-resolved"],
            },
        )
        paths = await session.call_tool(
            "loci_graph_paths",
            arguments={
                "repo": str(repo),
                "source_ids": [source_id],
                "target_ids": [crate_id],
                "namespaces": ["loci"],
                "edge_types": ["imports"],
                "resolutions": ["import-resolved"],
                "max_hops": 1,
                "max_nodes": 2,
                "max_paths": 1,
            },
        )
        retrieved = await session.call_tool(
            "loci_graph_retrieve",
            arguments={
                "repo": str(repo),
                "question": "How does the Rust binary import its library crate?",
                "seed_ids": [source_id, crate_id],
                "namespaces": ["loci"],
                "edge_types": ["imports"],
                "resolutions": ["import-resolved"],
                "max_hops": 1,
                "max_nodes": 2,
                "max_paths": 1,
            },
        )
        compatibility = await session.call_tool(
            "loci_graph_neighbors",
            arguments={"repo": str(repo), "seed_ids": [source_id]},
        )
        return {
            "indexed": indexed.structured_content,
            "initial_imports": initial_imports.structured_content,
            "initial_outgoing": initial_outgoing.structured_content,
            "tool_names": [tool.name for tool in tools.tools],
            "imports_schema": imports_tool.input_schema,
            "imports": imports.structured_content,
            "health": health.structured_content,
            "outgoing": outgoing.structured_content,
            "paths": paths.structured_content,
            "retrieved": retrieved.structured_content,
            "compatibility": compatibility.structured_content,
        }


async def _search_after_repo_change(repo: Path, cache_dir: Path) -> dict[str, Any]:
    repo.mkdir()
    source = repo / "sample.py"
    source.write_text("def old_symbol():\n    return 1\n")

    env = os.environ.copy()
    env["LOCI_BASE_DIR"] = str(cache_dir)
    env["PYTHONPATH"] = str(Path.cwd() / "src")
    server_params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "loci.mcp_server"],
        env=env,
        cwd=Path.cwd(),
    )

    async with Client(stdio_client(server_params)) as session:
        await session.call_tool(
            "loci_index",
            arguments={"repo": str(repo), "incremental": False},
        )
        source.write_text("def fresh_symbol():\n    return 2\n")
        search = await session.call_tool(
            "loci_search",
            arguments={"repo": str(repo), "query": "fresh_symbol"},
        )
        return search.structured_content


async def _grep_after_indexed_file_deleted(repo: Path, cache_dir: Path) -> dict[str, Any]:
    repo.mkdir()
    source = repo / "sample.py"
    source.write_text("def deleted_symbol():\n    return 1\n")

    env = os.environ.copy()
    env["LOCI_BASE_DIR"] = str(cache_dir)
    env["PYTHONPATH"] = str(Path.cwd() / "src")
    server_params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "loci.mcp_server"],
        env=env,
        cwd=Path.cwd(),
    )

    async with Client(stdio_client(server_params)) as session:
        await session.call_tool(
            "loci_index",
            arguments={"repo": str(repo), "incremental": False},
        )
        source.unlink()
        grep = await session.call_tool(
            "loci_grep",
            arguments={"repo": str(repo), "pattern": "deleted_symbol"},
        )
        return grep.structured_content


async def _markdown_search_and_outline(repo: Path, cache_dir: Path) -> dict[str, Any]:
    repo.mkdir()
    (repo / "README.md").write_text(
        "---\n"
        "title: Markdown Manual\n"
        "tags: [retrieval-governance]\n"
        "---\n\n"
        "# Markdown Manual\n\n"
        "Root body.\n\n"
        "## Usage\n\n"
        "Use retrieval governance for bounded section context.\n",
        encoding="utf-8",
    )

    env = os.environ.copy()
    env["LOCI_BASE_DIR"] = str(cache_dir)
    env["PYTHONPATH"] = str(Path.cwd() / "src")
    server_params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "loci.mcp_server"],
        env=env,
        cwd=Path.cwd(),
    )

    async with Client(stdio_client(server_params)) as session:
        await session.call_tool(
            "loci_index",
            arguments={"repo": str(repo), "incremental": False},
        )
        outline = await session.call_tool(
            "loci_outline",
            arguments={"repo": str(repo), "file": "README.md"},
        )
        search = await session.call_tool(
            "loci_search",
            arguments={
                "repo": str(repo),
                "query": "retrieval-governance",
                "lang": "markdown",
                "limit": 5,
            },
        )
        return {
            "outline": outline.structured_content,
            "search": search.structured_content,
        }


async def _outline_missing_repo(cache_dir: Path, repo: Path) -> dict[str, Any]:
    env = os.environ.copy()
    env["LOCI_BASE_DIR"] = str(cache_dir)
    env["PYTHONPATH"] = str(Path.cwd() / "src")
    server_params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "loci.mcp_server"],
        env=env,
        cwd=Path.cwd(),
    )

    async with Client(stdio_client(server_params)) as session:
        result = await session.call_tool("loci_outline", arguments={"repo": str(repo)})
        assert result.is_error is True
        return result.structured_content["error"]

    raise AssertionError("Expected loci_outline to return an error result")
