from __future__ import annotations

import json
import sys
from collections.abc import Sequence
from typing import Any, Literal, cast

from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.exceptions import ToolError
from mcp.types import CallToolResult, ContentBlock, TextContent

from loci.graph.traversal import GraphDirection
from loci.service import (
    LociError,
    analyze_usage,
    graph_anchors,
    graph_calls,
    graph_health,
    graph_imports,
    graph_neighbors,
    graph_paths,
    graph_references,
    graph_retrieve,
    graph_traverse_neighbors,
    get_cached_file,
    get_symbols,
    grep_repo_result,
    index_repo,
    list_repos,
    outline_repo,
    search_symbols_result,
    session_stats,
    store_health,
    verify_repo,
)
from loci.storage.store_identity import StoreIdentityError, bind_mcp_store
from loci.storage.store_health import (
    DEFAULT_HEALTH_LIMIT,
    DEFAULT_MAX_CATALOG_BYTES,
    DEFAULT_MAX_INDEX_BYTES,
    DEFAULT_MAX_PROBE_BYTES,
    DEFAULT_MAX_PROBE_PATHS,
)
from loci.storage.store_resolver import activate_mcp_store


_LEGACY_PATH_PARAMETER_TOOLS = frozenset({
    "loci_index",
    "loci_outline",
    "loci_verify",
})


class LociMCP(FastMCP):
    async def call_tool(
        self,
        name: str,
        arguments: dict[str, Any],
    ) -> Sequence[ContentBlock] | dict[str, Any]:
        return await super().call_tool(
            name,
            _normalize_repository_arguments(name, arguments),
        )


def _normalize_repository_arguments(
    tool_name: str,
    arguments: dict[str, Any],
) -> dict[str, Any]:
    if tool_name not in _LEGACY_PATH_PARAMETER_TOOLS or "path" not in arguments:
        return arguments
    if "repo" in arguments:
        raise ToolError(
            f"{tool_name} received both 'repo' and legacy 'path'; provide only 'repo'"
        )
    normalized = dict(arguments)
    normalized["repo"] = normalized.pop("path")
    return normalized


def create_server() -> FastMCP:
    mcp = LociMCP(
        "loci",
        instructions=(
            "Local code navigation server. Index local repositories, inspect symbol "
            "outlines, retrieve exact symbol source, select explained graph anchors, "
            "inspect exact or filtered graph neighbours, retrieve evidence-backed "
            "paths, and report graph-extension or bounded repository-store health "
            "from the loci cache."
        ),
    )

    @mcp.tool()
    def loci_index(repo: str, incremental: bool = True) -> CallToolResult:
        """Index a local repository path into the loci cache."""
        return _handle_loci_error(lambda: index_repo(repo, incremental=incremental))

    @mcp.tool()
    def loci_outline(repo: str, file: str | None = None) -> CallToolResult:
        """Return indexed symbols grouped by file."""
        return _handle_loci_error(
            lambda: {"files": outline_repo(repo, file=file, ensure_fresh=True)}
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
                direction=cast(GraphDirection, direction),
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
                direction=cast(GraphDirection, direction),
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
                direction=cast(GraphDirection, direction),
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
    def loci_graph_imports(
        repo: str,
        file: str | None = None,
        status: str = "all",
        offset: int = 0,
        limit: int = 100,
    ) -> CallToolResult:
        """Inspect bounded resolved and unresolved built-in import records."""
        return _handle_loci_error(
            lambda: graph_imports(
                repo,
                file=file,
                status=cast(Literal["all", "resolved", "unresolved"], status),
                offset=offset,
                limit=limit,
                ensure_fresh=True,
            )
        )

    @mcp.tool()
    def loci_graph_references(
        repo: str,
        file: str | None = None,
        status: str = "all",
        offset: int = 0,
        limit: int = 100,
    ) -> CallToolResult:
        """Inspect bounded resolved and unresolved imported-symbol references."""
        return _handle_loci_error(
            lambda: graph_references(
                repo,
                file=file,
                status=cast(Literal["all", "resolved", "unresolved"], status),
                offset=offset,
                limit=limit,
                ensure_fresh=True,
            )
        )

    @mcp.tool()
    def loci_graph_calls(
        repo: str,
        file: str | None = None,
        status: str = "all",
        offset: int = 0,
        limit: int = 100,
    ) -> CallToolResult:
        """Inspect bounded resolved and unresolved definite-call records."""
        return _handle_loci_error(
            lambda: graph_calls(
                repo,
                file=file,
                status=cast(Literal["all", "resolved", "unresolved"], status),
                offset=offset,
                limit=limit,
                ensure_fresh=True,
            )
        )

    @mcp.tool()
    def loci_search(
        repo: str,
        query: str,
        kind: str | None = None,
        lang: str | None = None,
        limit: int = 20,
    ) -> CallToolResult:
        """Search indexed symbols and report bounded repository coverage."""
        return _handle_loci_error(
            lambda: search_symbols_result(
                repo,
                query,
                kind=kind,
                lang=lang,
                limit=limit,
                ensure_fresh=True,
            )
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
        """Regex-search cached files and report bounded repository coverage."""
        return _handle_loci_error(
            lambda: grep_repo_result(repo, pattern, ensure_fresh=True)
        )

    @mcp.tool()
    def loci_verify(repo: str) -> CallToolResult:
        """Verify index integrity and content drift for an indexed repository."""
        return _handle_loci_error(lambda: verify_repo(repo))

    @mcp.tool()
    def loci_list() -> CallToolResult:
        """List repositories present in the loci cache."""
        return _handle_loci_error(lambda: {"repos": list_repos()})

    @mcp.tool()
    def loci_store_health(
        offset: int = 0,
        limit: int = DEFAULT_HEALTH_LIMIT,
        max_catalog_bytes: int = DEFAULT_MAX_CATALOG_BYTES,
        max_index_bytes: int = DEFAULT_MAX_INDEX_BYTES,
        max_probe_paths: int = DEFAULT_MAX_PROBE_PATHS,
        max_probe_bytes: int = DEFAULT_MAX_PROBE_BYTES,
    ) -> CallToolResult:
        """Inspect bounded read-only freshness, liveness, integrity, and overlaps."""
        return _handle_loci_error(
            lambda: store_health(
                offset=offset,
                limit=limit,
                max_catalog_bytes=max_catalog_bytes,
                max_index_bytes=max_index_bytes,
                max_probe_paths=max_probe_paths,
                max_probe_bytes=max_probe_bytes,
            )
        )

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
    try:
        activate_mcp_store(bind_mcp_store())
    except StoreIdentityError as exc:
        print(json.dumps({"error": exc.to_dict()}), file=sys.stderr)
        raise SystemExit(78) from exc
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
