import asyncio
import os
import shutil
import sys
from pathlib import Path
from typing import Any

import pytest
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


def test_mcp_index_outline_get_round_trip(tmp_path: Path, fixtures_dir: Path):
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "sample.py").write_text((fixtures_dir / "sample.py").read_text())

    result = asyncio.run(_round_trip(repo, tmp_path / ".codeindex"))

    assert result["indexed"]["symbols_indexed"] > 0
    assert result["tools"] == [
        "loci_file",
        "loci_get",
        "loci_grep",
        "loci_index",
        "loci_list",
        "loci_outline",
        "loci_search",
        "loci_verify",
    ]
    assert result["outline"]["files"][0]["file"] == "sample.py"
    assert any(symbol["name"] == "add" for symbol in result["search"]["symbols"])
    assert "def add" in result["get"]["symbols"][0]["source"]
    assert "def add" in result["file"]["content"]
    assert result["grep"]["matches"][0]["file"] == "sample.py"
    assert result["verify"]["failed"] == []
    assert any(entry["path"] == str(repo.resolve()) for entry in result["list"]["repos"])
    assert result["invalid_grep"]["error"]["code"] == "INVALID_REGEX"


def test_mcp_loci_mcp_command_round_trip(tmp_path: Path, fixtures_dir: Path):
    if shutil.which("loci-mcp") is None:
        pytest.skip("loci-mcp is not installed on PATH")

    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "sample.py").write_text((fixtures_dir / "sample.py").read_text())

    result = asyncio.run(
        _round_trip(repo, tmp_path / ".codeindex", command="loci-mcp", args=[])
    )

    assert "loci_index" in result["tools"]
    assert result["indexed"]["symbols_indexed"] > 0
    assert result["verify"]["failed"] == []


def test_mcp_errors_include_loci_error_data(tmp_path: Path):
    error_data = asyncio.run(_outline_missing_repo(tmp_path / ".codeindex", tmp_path / "repo"))

    assert error_data["code"] == "REPO_NOT_INDEXED"
    assert error_data["details"]["repo"] == str((tmp_path / "repo").resolve())


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

    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = await session.list_tools()
            tool_names = sorted(tool.name for tool in tools.tools)

            indexed = await session.call_tool(
                "loci_index",
                arguments={"path": str(repo), "incremental": False},
            )
            outline = await session.call_tool(
                "loci_outline",
                arguments={"path": str(repo)},
            )
            symbol_id = next(
                symbol["id"]
                for entry in outline.structuredContent["files"]
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
            verify = await session.call_tool(
                "loci_verify",
                arguments={"path": str(repo)},
            )
            repos = await session.call_tool("loci_list", arguments={})
            invalid_grep = await session.call_tool(
                "loci_grep",
                arguments={"repo": str(repo), "pattern": "["},
            )
            assert invalid_grep.isError is True

    return {
        "tools": tool_names,
        "indexed": indexed.structuredContent,
        "outline": outline.structuredContent,
        "get": source.structuredContent,
        "search": search.structuredContent,
        "file": file_result.structuredContent,
        "grep": grep.structuredContent,
        "verify": verify.structuredContent,
        "list": repos.structuredContent,
        "invalid_grep": invalid_grep.structuredContent,
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

    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool("loci_outline", arguments={"path": str(repo)})
            assert result.isError is True
            return result.structuredContent["error"]

    raise AssertionError("Expected loci_outline to return an error result")
