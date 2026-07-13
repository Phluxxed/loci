from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP
from mcp.types import CallToolResult, TextContent

from loci.service import (
    LociError,
    analyze_usage,
    graph_anchors,
    graph_health,
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


def create_server() -> FastMCP:
    mcp = FastMCP(
        "loci",
        instructions=(
            "Local code navigation server. Index local repositories, inspect symbol "
            "outlines, retrieve exact symbol source, select explained graph anchors, "
            "inspect exact or filtered graph neighbours, retrieve evidence-backed "
            "paths, and report graph-extension health from the loci cache."
        ),
    )

    @mcp.tool()
    def loci_index(path: str, incremental: bool = True) -> CallToolResult:
        """Index a local repository path into the loci cache."""
        return _handle_loci_error(lambda: index_repo(path, incremental=incremental))

    @mcp.tool()
    def loci_outline(path: str, file: str | None = None) -> CallToolResult:
        """Return indexed symbols grouped by file."""
        return _handle_loci_error(
            lambda: {"files": outline_repo(path, file=file, ensure_fresh=True)}
        )

    @mcp.tool()
    def loci_get(repo: str, symbol_ids: list[str], context: int = 0) -> CallToolResult:
        """Return exact source for one or more indexed symbol ids."""
        return _handle_loci_error(
            lambda: {
                "symbols": get_symbols(
                    repo,
                    symbol_ids,
                    context=context,
                    ensure_fresh=True,
                )
            }
        )

    @mcp.tool()
    def loci_graph_anchors(
        repo: str,
        question: str,
        seed_ids: list[str] | None = None,
        max_anchors: int = 10,
    ) -> CallToolResult:
        """Select a small, explained set of graph anchors for a question."""
        return _handle_loci_error(
            lambda: graph_anchors(
                repo,
                question,
                seed_ids,
                max_anchors=max_anchors,
                ensure_fresh=True,
            )
        )

    @mcp.tool()
    def loci_graph_neighbors(
        repo: str,
        seed_ids: list[str],
    ) -> CallToolResult:
        """Return exact outgoing one-hop graph neighbours for indexed seed nodes."""
        return _handle_loci_error(
            lambda: graph_neighbors(repo, seed_ids, ensure_fresh=True)
        )

    @mcp.tool()
    def loci_graph_traverse_neighbors(
        repo: str,
        seed_ids: list[str],
        namespaces: list[str] | None = None,
        edge_types: list[str] | None = None,
        resolutions: list[str] | None = None,
        direction: str = "outgoing",
        max_neighbors: int = 64,
    ) -> CallToolResult:
        """Return filtered one-hop graph neighbours without widening exact reads."""
        return _handle_loci_error(
            lambda: graph_traverse_neighbors(
                repo,
                seed_ids,
                namespaces=namespaces,
                edge_types=edge_types,
                resolutions=resolutions,
                direction=direction,
                max_neighbors=max_neighbors,
                ensure_fresh=True,
            )
        )

    @mcp.tool()
    def loci_graph_paths(
        repo: str,
        source_ids: list[str],
        target_ids: list[str],
        namespaces: list[str] | None = None,
        edge_types: list[str] | None = None,
        resolutions: list[str] | None = None,
        direction: str = "outgoing",
        max_hops: int = 3,
        max_nodes: int = 64,
        max_paths: int = 8,
        path_offset: int = 0,
        max_evidence_bytes: int = 32_768,
        max_estimated_tokens: int = 8_192,
    ) -> CallToolResult:
        """Find bounded endpoint paths with exact edge evidence."""
        return _handle_loci_error(
            lambda: graph_paths(
                repo,
                source_ids,
                target_ids,
                namespaces=namespaces,
                edge_types=edge_types,
                resolutions=resolutions,
                direction=direction,
                max_hops=max_hops,
                max_nodes=max_nodes,
                max_paths=max_paths,
                path_offset=path_offset,
                max_evidence_bytes=max_evidence_bytes,
                max_estimated_tokens=max_estimated_tokens,
                ensure_fresh=True,
            )
        )

    @mcp.tool()
    def loci_graph_retrieve(
        repo: str,
        question: str,
        seed_ids: list[str] | None = None,
        namespaces: list[str] | None = None,
        edge_types: list[str] | None = None,
        resolutions: list[str] | None = None,
        direction: str = "either",
        max_anchors: int = 10,
        max_hops: int = 3,
        max_nodes: int = 64,
        max_paths: int = 8,
        path_offset: int = 0,
        max_evidence_bytes: int = 32_768,
        max_estimated_tokens: int = 8_192,
    ) -> CallToolResult:
        """Retrieve bounded question-shaped graph evidence and rejected paths."""
        return _handle_loci_error(
            lambda: graph_retrieve(
                repo,
                question,
                seed_ids,
                namespaces=namespaces,
                edge_types=edge_types,
                resolutions=resolutions,
                direction=direction,
                max_anchors=max_anchors,
                max_hops=max_hops,
                max_nodes=max_nodes,
                max_paths=max_paths,
                path_offset=path_offset,
                max_evidence_bytes=max_evidence_bytes,
                max_estimated_tokens=max_estimated_tokens,
                ensure_fresh=True,
            )
        )

    @mcp.tool()
    def loci_graph_health(repo: str) -> CallToolResult:
        """Inspect loaded graph profiles, active record counts, and diagnostics."""
        return _handle_loci_error(
            lambda: graph_health(repo, ensure_fresh=True)
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
                    ensure_fresh=True,
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
                ensure_fresh=True,
            )
        )

    @mcp.tool()
    def loci_grep(repo: str, pattern: str) -> CallToolResult:
        """Regex-search cached files."""
        return _handle_loci_error(
            lambda: {"matches": grep_repo(repo, pattern, ensure_fresh=True)}
        )

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
