from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP
from mcp.types import CallToolResult, TextContent

from loci.service import (
    LociError,
    analyze_usage,
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


def create_server() -> FastMCP:
    mcp = FastMCP(
        "loci",
        instructions=(
            "Local code navigation server. Index local repositories, inspect symbol "
            "outlines, and retrieve exact symbol source from the loci cache."
        ),
    )

    @mcp.tool()
    def loci_index(path: str, incremental: bool = True) -> CallToolResult:
        """Index a local repository path into the loci cache."""
        return _handle_loci_error(lambda: index_repo(path, incremental=incremental))

    @mcp.tool()
    def loci_outline(path: str, file: str | None = None) -> CallToolResult:
        """Return indexed symbols grouped by file."""
        return _handle_loci_error(lambda: {"files": outline_repo(path, file=file)})

    @mcp.tool()
    def loci_get(repo: str, symbol_ids: list[str], context: int = 0) -> CallToolResult:
        """Return exact source for one or more indexed symbol ids."""
        return _handle_loci_error(
            lambda: {"symbols": get_symbols(repo, symbol_ids, context=context)}
        )

    @mcp.tool()
    def loci_search(
        repo: str,
        query: str,
        kind: str | None = None,
        lang: str | None = None,
        limit: int = 20,
    ) -> CallToolResult:
        """Search indexed symbols by query."""
        return _handle_loci_error(
            lambda: {
                "symbols": search_symbols(
                    repo,
                    query,
                    kind=kind,
                    lang=lang,
                    limit=limit,
                )
            }
        )

    @mcp.tool()
    def loci_file(
        repo: str,
        file_path: str,
        start_line: int | None = None,
        end_line: int | None = None,
    ) -> CallToolResult:
        """Return cached file content by relative path and optional line range."""
        return _handle_loci_error(
            lambda: get_cached_file(
                repo,
                file_path,
                start_line=start_line,
                end_line=end_line,
            )
        )

    @mcp.tool()
    def loci_grep(repo: str, pattern: str) -> CallToolResult:
        """Regex-search cached files."""
        return _handle_loci_error(lambda: {"matches": grep_repo(repo, pattern)})

    @mcp.tool()
    def loci_verify(path: str) -> CallToolResult:
        """Verify index integrity and content drift for an indexed repository."""
        return _handle_loci_error(lambda: verify_repo(path))

    @mcp.tool()
    def loci_list() -> CallToolResult:
        """List repositories present in the loci cache."""
        return _handle_loci_error(lambda: {"repos": list_repos()})

    @mcp.tool()
    def loci_stats(
        repo: str | None = None,
        since_days: int = 7,
        all_time: bool = False,
    ) -> CallToolResult:
        """Return structured session retrieval stats for the active loci store."""
        return _handle_loci_error(
            lambda: session_stats(
                repo=repo,
                since_days=None if all_time else since_days,
            )
        )

    @mcp.tool()
    def loci_analyze(repo: str | None = None, since_days: int = 30) -> CallToolResult:
        """Analyze loci usage logs and return actionable tool-quality findings."""
        return _handle_loci_error(
            lambda: analyze_usage(repo=repo, since_days=since_days)
        )

    return mcp


def _handle_loci_error(operation):
    try:
        return _success(operation())
    except LociError as exc:
        return CallToolResult(
            content=[
                TextContent(
                    type="text",
                    text=f"{exc.code}: {exc.message}",
                )
            ],
            structuredContent={"error": exc.to_dict()},
            isError=True,
        )


def _success(payload: dict[str, Any]) -> CallToolResult:
    return CallToolResult(
        content=[],
        structuredContent=payload,
        isError=False,
    )


mcp = create_server()


def main() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
