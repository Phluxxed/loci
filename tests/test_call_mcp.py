from __future__ import annotations

import asyncio
import hashlib
import os
import shutil
from pathlib import Path
from typing import Any

import pytest
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from loci.storage.index_store import IndexStore


CALL_FIXTURES = {
    "python": {
        "files": {
            "main.py": (
                "def target():\n    return 1\n\n"
                "def caller():\n    return target()\n"
            ),
        },
        "file": "main.py",
        "caller_id": "main.py::caller#function",
        "target_id": "main.py::target#function",
    },
    "typescript": {
        "files": {
            "main.ts": (
                "export function target() { return 1; }\n"
                "export function caller() { return target(); }\n"
            ),
        },
        "file": "main.ts",
        "caller_id": "main.ts::caller#function",
        "target_id": "main.ts::target#function",
    },
    "go": {
        "files": {
            "go.mod": "module example.com/calls\n\ngo 1.22\n",
            "main.go": (
                "package calls\n\n"
                "func Target() {}\n\n"
                "func Caller() { Target() }\n"
            ),
        },
        "file": "main.go",
        "caller_id": "main.go::Caller#function",
        "target_id": "main.go::Target#function",
    },
    "rust": {
        "files": {
            "Cargo.toml": (
                '[package]\nname = "calls"\nversion = "0.1.0"\n'
                'edition = "2021"\n'
            ),
            "src/lib.rs": (
                "pub fn target() {}\n\n"
                "pub fn caller() { target(); }\n"
            ),
        },
        "file": "src/lib.rs",
        "caller_id": "src/lib.rs::caller#function",
        "target_id": "src/lib.rs::target#function",
    },
}


def _write_fixture(repo: Path, language: str) -> dict[str, Any]:
    fixture = CALL_FIXTURES[language]
    repo.mkdir()
    for relative, content in fixture["files"].items():
        path = repo / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    return fixture


def _server(cache_dir: Path) -> StdioServerParameters:
    command = shutil.which("loci-mcp")
    assert command is not None, "installed loci-mcp wrapper is required"
    env = os.environ.copy()
    env["LOCI_BASE_DIR"] = str(cache_dir)
    return StdioServerParameters(command=command, args=[], env=env, cwd=Path.cwd())


@pytest.mark.parametrize("language", tuple(CALL_FIXTURES))
def test_installed_mcp_call_diagnostics_survive_fresh_process_for_each_language(
    tmp_path: Path,
    language: str,
):
    result = asyncio.run(_call_diagnostics_after_restart(
        tmp_path / language,
        tmp_path / f".{language}-index",
        language,
    ))
    fixture = CALL_FIXTURES[language]

    assert result["schema"]["required"] == ["repo"]
    assert set(result["schema"]["properties"]) == {
        "repo",
        "file",
        "status",
        "offset",
        "limit",
    }
    assert result["schema"]["properties"]["file"]["default"] is None
    assert result["schema"]["properties"]["status"]["default"] == "all"
    assert result["schema"]["properties"]["offset"]["default"] == 0
    assert result["schema"]["properties"]["limit"]["default"] == 100
    assert result["tools"].count("loci_graph_calls") == 1

    calls = result["calls"]
    assert calls["counts"] == {
        "total": 1,
        "resolved": 1,
        "unresolved": 0,
        "returned": 1,
    }
    assert calls["items"][0]["caller_id"] == fixture["caller_id"]
    assert calls["items"][0]["target_id"] == fixture["target_id"]
    assert calls["items"][0]["resolution"] == "exact"
    assert result["empty"]["items"] == []
    assert result["empty"]["pagination"]["next_offset"] is None

    outgoing = result["outgoing"]["results"][0]["neighbors"][0]
    incoming = result["incoming"]["results"][0]["neighbors"][0]
    assert outgoing["node"]["id"] == fixture["target_id"]
    assert outgoing["edge"]["type"] == "calls"
    assert outgoing["edge"]["resolution"] == "exact"
    assert outgoing["traversed"] == "forward"
    assert incoming["node"]["id"] == fixture["caller_id"]
    assert incoming["traversed"] == "reverse"
    assert result["compatibility"]["results"][0]["neighbors"] == []
    assert result["health"]["counts"]["graph_calls_indexed"] == 1
    assert result["health"]["counts"]["graph_calls_resolved"] == 1
    assert result["health"]["counts"]["graph_calls_unresolved"] == 0
    assert result["verify"]["failed"] == []
    assert result["index_before"] == result["index_after"]

    for existing_schema in (result["imports_schema"], result["references_schema"]):
        assert existing_schema["required"] == ["repo"]
        assert set(existing_schema["properties"]) == {
            "repo",
            "file",
            "status",
            "offset",
            "limit",
        }


def test_mcp_call_diagnostics_return_structured_boundary_errors(
    tmp_path: Path,
):
    errors = asyncio.run(_call_errors(
        tmp_path / "repo",
        tmp_path / ".codeindex",
    ))

    for field in ("file", "status", "offset", "limit"):
        assert errors[field]["error"]["code"] == "INVALID_INPUT"
        assert errors[field]["error"]["details"]["field"] == field


def test_mcp_call_diagnostics_refresh_stale_source(
    tmp_path: Path,
):
    result = asyncio.run(_call_refresh_after_change(
        tmp_path / "repo",
        tmp_path / ".codeindex",
    ))

    assert result["counts"] == {
        "total": 1,
        "resolved": 0,
        "unresolved": 1,
        "returned": 1,
    }
    assert result["items"][0]["unresolved_reason"] == "callee_not_proven"


async def _call_diagnostics_after_restart(
    repo: Path,
    cache_dir: Path,
    language: str,
) -> dict[str, Any]:
    fixture = _write_fixture(repo, language)
    server = _server(cache_dir)

    async with stdio_client(server) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            indexed = await session.call_tool(
                "loci_index",
                arguments={"path": str(repo), "incremental": False},
            )
            assert indexed.structuredContent is not None
            assert indexed.structuredContent["graph_calls_resolved"] == 1

    index_path = IndexStore(base_dir=cache_dir)._index_path(repo.resolve())
    index_before = (
        hashlib.sha256(index_path.read_bytes()).hexdigest(),
        index_path.stat().st_mtime_ns,
    )

    async with stdio_client(server) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            listed = await session.list_tools()
            tools = [tool.name for tool in listed.tools]
            schemas = {tool.name: tool.inputSchema for tool in listed.tools}
            calls = await session.call_tool(
                "loci_graph_calls",
                arguments={"repo": str(repo), "file": fixture["file"]},
            )
            empty = await session.call_tool(
                "loci_graph_calls",
                arguments={"repo": str(repo), "file": "not-indexed.py"},
            )
            edge_filters = {
                "repo": str(repo),
                "namespaces": ["loci"],
                "edge_types": ["calls"],
                "resolutions": ["exact"],
            }
            outgoing = await session.call_tool(
                "loci_graph_traverse_neighbors",
                arguments={**edge_filters, "seed_ids": [fixture["caller_id"]]},
            )
            incoming = await session.call_tool(
                "loci_graph_traverse_neighbors",
                arguments={
                    **edge_filters,
                    "seed_ids": [fixture["target_id"]],
                    "direction": "incoming",
                },
            )
            compatibility = await session.call_tool(
                "loci_graph_neighbors",
                arguments={"repo": str(repo), "seed_ids": [fixture["caller_id"]]},
            )
            health = await session.call_tool(
                "loci_graph_health",
                arguments={"repo": str(repo)},
            )
            verify = await session.call_tool(
                "loci_verify",
                arguments={"path": str(repo)},
            )

    index_after = (
        hashlib.sha256(index_path.read_bytes()).hexdigest(),
        index_path.stat().st_mtime_ns,
    )
    return {
        "tools": tools,
        "schema": schemas["loci_graph_calls"],
        "imports_schema": schemas["loci_graph_imports"],
        "references_schema": schemas["loci_graph_references"],
        "calls": calls.structuredContent,
        "empty": empty.structuredContent,
        "outgoing": outgoing.structuredContent,
        "incoming": incoming.structuredContent,
        "compatibility": compatibility.structuredContent,
        "health": health.structuredContent,
        "verify": verify.structuredContent,
        "index_before": index_before,
        "index_after": index_after,
    }


async def _call_errors(repo: Path, cache_dir: Path) -> dict[str, Any]:
    _write_fixture(repo, "python")
    server = _server(cache_dir)
    async with stdio_client(server) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            await session.call_tool(
                "loci_index",
                arguments={"path": str(repo), "incremental": False},
            )
            errors = {}
            for field, arguments in (
                ("file", {"file": "../main.py"}),
                ("status", {"status": "invalid"}),
                ("offset", {"offset": -1}),
                ("limit", {"limit": 501}),
            ):
                result = await session.call_tool(
                    "loci_graph_calls",
                    arguments={"repo": str(repo), **arguments},
                )
                assert result.isError is True
                errors[field] = result.structuredContent
    return errors


async def _call_refresh_after_change(repo: Path, cache_dir: Path) -> dict[str, Any]:
    _write_fixture(repo, "python")
    server = _server(cache_dir)
    async with stdio_client(server) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            await session.call_tool(
                "loci_index",
                arguments={"path": str(repo), "incremental": False},
            )

    (repo / "main.py").write_text(
        "def caller():\n    return missing()\n",
        encoding="utf-8",
    )
    async with stdio_client(server) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            calls = await session.call_tool(
                "loci_graph_calls",
                arguments={"repo": str(repo)},
            )
    assert calls.structuredContent is not None
    return calls.structuredContent
