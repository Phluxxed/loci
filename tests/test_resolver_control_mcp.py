"""Resolver-control retrieval acceptance through the normal stdio MCP server."""
from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path
from typing import Any

from mcp import Client, StdioServerParameters
from mcp.client.stdio import stdio_client


def _server_params(cache_dir: Path) -> StdioServerParameters:
    env = os.environ.copy()
    env["LOCI_BASE_DIR"] = str(cache_dir)
    env["LOCI_STORE_NAMESPACE"] = "resolver-control-mcp"
    env["LOCI_MCP_SURFACE"] = "diagnostic"
    env["PYTHONPATH"] = str(Path.cwd() / "src")
    return StdioServerParameters(
        command=sys.executable,
        args=["-m", "loci.mcp_server"],
        env=env,
        cwd=Path.cwd(),
    )


async def _index(session: Client, repo: Path) -> None:
    response = await session.call_tool(
        "loci_index", arguments={"repo": str(repo), "incremental": False}
    )
    assert not response.is_error, response.structured_content


async def _file(session: Client, repo: Path, path: str, **range_: int) -> Any:
    return await session.call_tool(
        "loci_file",
        arguments={"repo": str(repo), "file_path": path, **range_},
    )


def _go_repo(repo: Path, content: bytes) -> Path:
    repo.mkdir()
    (repo / "go.mod").write_bytes(content)
    (repo / "main.go").write_text("package control\n\nfunc Run() {}\n", encoding="utf-8")
    return repo


def _rust_repo(repo: Path, content: bytes) -> Path:
    (repo / "src").mkdir(parents=True)
    (repo / "Cargo.toml").write_bytes(content)
    (repo / "src" / "lib.rs").write_text("pub fn run() {}\n", encoding="utf-8")
    return repo


def _assert_file(
    response: Any,
    *,
    file: str,
    content: str,
    total_lines: int,
    start_line: int,
    end_line: int,
) -> None:
    assert not response.is_error, response.structured_content
    assert response.structured_content == {
        "file": file,
        "content": content,
        "total_lines": total_lines,
        "start_line": start_line,
        "end_line": end_line,
    }


def _assert_error(response: Any, code: str) -> None:
    assert response.is_error is True
    assert response.structured_content["error"]["code"] == code


def test_resolver_controls_return_exact_bytes_and_refresh_through_stdio_mcp(
    tmp_path: Path,
) -> None:
    go_bytes = "module example.com/control\r\n\r\n// snowman: ☃\r\n".encode("utf-8")
    cargo_bytes = (
        "[package]\nname = \"control\"\nversion = \"0.1.0\"\nedition = \"2021\"\n"
    ).encode("utf-8")
    go_repo = _go_repo(tmp_path / "go", go_bytes)
    rust_repo = _rust_repo(tmp_path / "rust", cargo_bytes)

    async def check() -> None:
        async with Client(stdio_client(_server_params(tmp_path / "cache"))) as session:
            await _index(session, go_repo)
            await _index(session, rust_repo)

            _assert_file(
                await _file(session, go_repo, "go.mod"),
                file="go.mod",
                content=go_bytes.decode("utf-8"),
                total_lines=3,
                start_line=1,
                end_line=3,
            )
            _assert_file(
                await _file(session, go_repo, "go.mod", start_line=2, end_line=3),
                file="go.mod",
                content="\r\n// snowman: ☃\r\n",
                total_lines=3,
                start_line=2,
                end_line=3,
            )
            _assert_file(
                await _file(session, rust_repo, "Cargo.toml", start_line=2, end_line=3),
                file="Cargo.toml",
                content='name = "control"\nversion = "0.1.0"\n',
                total_lines=4,
                start_line=2,
                end_line=3,
            )
            _assert_file(
                await _file(session, rust_repo, "Cargo.toml"),
                file="Cargo.toml",
                content=cargo_bytes.decode("utf-8"),
                total_lines=4,
                start_line=1,
                end_line=4,
            )

            refreshed = b"module example.com/control\n\ngo 1.23\n"
            (go_repo / "go.mod").write_bytes(refreshed)
            _assert_file(
                await _file(session, go_repo, "go.mod"),
                file="go.mod",
                content=refreshed.decode("utf-8"),
                total_lines=3,
                start_line=1,
                end_line=3,
            )
            refreshed_cargo = (
                b"[package]\nname = \"control-refresh\"\nversion = \"0.2.0\"\nedition = \"2021\"\n"
            )
            (rust_repo / "Cargo.toml").write_bytes(refreshed_cargo)
            _assert_file(
                await _file(session, rust_repo, "Cargo.toml"),
                file="Cargo.toml",
                content=refreshed_cargo.decode("utf-8"),
                total_lines=4,
                start_line=1,
                end_line=4,
            )

    asyncio.run(check())


def test_resolver_controls_reject_untracked_and_unsafe_paths_through_stdio_mcp(
    tmp_path: Path,
) -> None:
    repo = _go_repo(tmp_path / "repo", b"module example.com/control\n")
    (repo / "nested").mkdir()
    (repo / "package.json").write_text('{"name":"untracked"}\n', encoding="utf-8")
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "go.mod").write_text("module example.com/outside\n", encoding="utf-8")
    symlink_repo = tmp_path / "symlink-repo"
    symlink_repo.mkdir()
    (symlink_repo / "main.go").write_text("package control\n", encoding="utf-8")
    (symlink_repo / "go.mod").symlink_to(outside / "go.mod")

    async def check() -> None:
        async with Client(stdio_client(_server_params(tmp_path / "cache"))) as session:
            await _index(session, repo)
            await _index(session, symlink_repo)

            for path in (
                "missing.toml",
                "missing/go.mod",
                "package.json",
                "nested",
                str(repo / "go.mod"),
                "../outside/go.mod",
            ):
                _assert_error(await _file(session, repo, path), "FILE_NOT_FOUND")

            symlink = await _file(session, symlink_repo, "go.mod")
            _assert_error(symlink, "CONTROL_SOURCE_UNAVAILABLE")
            assert symlink.structured_content["error"]["details"]["reason"] == "read_failed"

    asyncio.run(check())


def test_resolver_controls_enforce_the_one_mebibyte_source_bound_through_stdio_mcp(
    tmp_path: Path,
) -> None:
    content = b"module example.com/control\n//" + (b"x" * (1024 * 1024)) + b"\n"
    repo = _go_repo(tmp_path / "repo", content)

    async def check() -> None:
        async with Client(stdio_client(_server_params(tmp_path / "cache"))) as session:
            await _index(session, repo)
            response = await _file(session, repo, "go.mod")
            _assert_error(response, "CONTROL_SOURCE_UNAVAILABLE")
            assert response.structured_content["error"]["details"]["reason"] == "read_failed"
            assert response.structured_content["error"]["details"]["limit_bytes"] == 1024 * 1024
            assert "content" not in response.structured_content

    asyncio.run(check())
