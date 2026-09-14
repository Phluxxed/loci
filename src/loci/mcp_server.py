from __future__ import annotations

import json
import os
import sys
import time
from importlib import import_module
from types import ModuleType
from typing import Annotated, Any, Callable, Literal, cast


_STARTED_AT = time.monotonic()
_STARTUP_TRACE_MAX_BYTES = 256 * 1024


def _startup_phase(phase: str) -> None:
    trace_path = os.environ.get("LOCI_MCP_STARTUP_TRACE")
    if not trace_path:
        return
    record = json.dumps(
        {
            "event": "loci_mcp_startup",
            "phase": phase,
            "pid": os.getpid(),
            "elapsed_ms": round((time.monotonic() - _STARTED_AT) * 1000, 3),
        },
        separators=(",", ":"),
    )
    print(record, file=sys.stderr, flush=True)
    try:
        flags = os.O_APPEND | os.O_CREAT | os.O_WRONLY
        fd = os.open(trace_path, flags, 0o600)
        try:
            if os.fstat(fd).st_size > _STARTUP_TRACE_MAX_BYTES:
                os.ftruncate(fd, 0)
            os.write(fd, f"{record}\n".encode())
        finally:
            os.close(fd)
    except OSError:
        pass


_startup_phase("module_entered")

from mcp.server.mcpserver import Context, MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import CallToolResult, InputRequiredResult, TextContent
from pydantic import Field, SkipValidation

from loci.mcp_output_models import (
    LociAnalyzeOutput,
    LociExploreOutput,
    LociFileOutput,
    LociGetOutput,
    LociGraphAnchorsOutput,
    LociGraphCallsOutput,
    LociGraphHealthOutput,
    LociGraphImportsOutput,
    LociGraphNeighborsOutput,
    LociGraphPathsOutput,
    LociGraphReferencesOutput,
    LociGraphRetrieveOutput,
    LociGraphTraverseNeighborsOutput,
    LociGrepOutput,
    LociIndexOutput,
    LociListOutput,
    LociReadOutput,
    LociRetrieveOutput,
    LociOutlineOutput,
    LociSearchOutput,
    LociStatsOutput,
    LociStoreHealthOutput,
    LociVerifyOutput,
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
from loci.mcp_record_pages import DEFAULT_RECORD_OUTPUT_BYTES, graph_record_page


_LEGACY_PATH_PARAMETER_TOOLS = frozenset({
    "loci_index",
    "loci_outline",
    "loci_verify",
})
_DIAGNOSTIC_TOOL_NAMES = frozenset({
    "loci_analyze",
    "loci_explore",
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
})
_NORMAL_TOOL_NAMES = frozenset({"loci_retrieve", "loci_read"})
_NORMAL_ARGUMENTS = {
    "loci_retrieve": frozenset({"repo", "query", "seed_ids"}),
    "loci_read": frozenset({"repo", "source_ref"}),
}
GraphDirection = Literal["incoming", "outgoing", "either"]
_service_module: ModuleType | None = None


def _service() -> ModuleType:
    global _service_module
    if _service_module is None:
        _service_module = import_module("loci.service")
    return _service_module


class LociMCP(MCPServer):
    async def call_tool(
        self,
        name: str,
        arguments: dict[str, Any],
        context: Context | None = None,
    ) -> CallToolResult | InputRequiredResult:
        return await super().call_tool(
            name,
            _normalize_repository_arguments(name, arguments),
            context,
        )


def _normalize_repository_arguments(
    tool_name: str,
    arguments: dict[str, Any],
) -> dict[str, Any]:
    if tool_name in _NORMAL_ARGUMENTS:
        unexpected = sorted(set(arguments) - _NORMAL_ARGUMENTS[tool_name])
        if unexpected:
            raise ToolError(
                f"{tool_name} received unsupported arguments: {', '.join(unexpected)}"
            )
    if tool_name not in _LEGACY_PATH_PARAMETER_TOOLS or "path" not in arguments:
        return arguments
    if "repo" in arguments:
        raise ToolError(
            f"{tool_name} received both 'repo' and legacy 'path'; provide only 'repo'"
        )
    normalized = dict(arguments)
    normalized["repo"] = normalized.pop("path")
    return normalized


def _configured_surface() -> Literal["normal", "diagnostic"]:
    value = os.environ.get("LOCI_MCP_SURFACE", "normal")
    if value in {"normal", "diagnostic"}:
        return cast(Literal["normal", "diagnostic"], value)
    raise ValueError(
        "LOCI_MCP_SURFACE must be either 'normal' or 'diagnostic'"
    )


def _validate_normal_retrieve_request(query: str, seed_ids: list[str] | None) -> None:
    try:
        query_bytes = len(query.encode("utf-8"))
    except UnicodeEncodeError as exc:
        raise ToolError("query must be valid UTF-8") from exc
    if query_bytes > 4096:
        raise ToolError("query must be at most 4096 UTF-8 bytes")
    if not query.strip() and not seed_ids:
        raise ToolError("loci_retrieve requires a nonblank query or at least one seed_id")
    if seed_ids is not None:
        if len(seed_ids) > 5:
            raise ToolError("seed_ids must contain at most five IDs")
        if any(not seed_id for seed_id in seed_ids):
            raise ToolError("seed_ids must contain only nonempty IDs")
        if len(set(seed_ids)) != len(seed_ids):
            raise ToolError("seed_ids must be unique")


def create_server(
    surface: Literal["normal", "diagnostic"] | None = None,
) -> MCPServer:
    selected_surface = _configured_surface() if surface is None else surface
    if selected_surface not in {"normal", "diagnostic"}:
        raise ValueError("surface must be either 'normal' or 'diagnostic'")
    mcp = LociMCP(
        "loci",
        instructions=(
            "Retrieve deterministic bounded source context and expand exact returned "
            "source extents from the loci cache."
            if selected_surface == "normal"
            else
            "Local code navigation server. Index local repositories, inspect symbol "
            "outlines, retrieve exact symbol source, select explained graph anchors, "
            "inspect exact or filtered graph neighbours, retrieve evidence-backed "
            "paths, and report graph-extension or bounded repository-store health "
            "from the loci cache."
        ),
    )

    @mcp.tool()
    def loci_retrieve(
        repo: Annotated[str, Field(strict=True, min_length=1)],
        query: Annotated[
            str,
            Field(strict=True, json_schema_extra={"x-maxUtf8Bytes": 4096}),
        ] = "",
        seed_ids: Annotated[
            list[Annotated[str, Field(strict=True, min_length=1)]] | None,
            Field(
                default=None,
                max_length=5,
                json_schema_extra={"uniqueItems": True},
            ),
        ] = None,
    ) -> Annotated[CallToolResult, LociRetrieveOutput]:
        """Retrieve deterministic bounded static source context.

        Provide a query or up to five exact seed IDs returned earlier. An exact
        indexed relative file path in ``query`` selects that file; other queries
        select bounded source candidates. The repository refreshes automatically.
        Results include source, relationship proof, ambiguity and omissions. Use
        an incomplete item's ``source_ref`` with ``loci_read`` to hydrate its
        exact source, or pass a returned node ID as a seed to re-anchor under the
        same fixed policy. Relationships are static and non-exhaustive.
        """
        _validate_normal_retrieve_request(query, seed_ids)
        return _handle_loci_error(
            lambda service: service.retrieve(
                repo,
                query=query,
                seed_ids=seed_ids,
                ensure_fresh=True,
            )
        )

    @mcp.tool()
    def loci_read(
        repo: Annotated[str, Field(strict=True, min_length=1)],
        source_ref: Annotated[str, Field(strict=True, min_length=1)],
    ) -> Annotated[CallToolResult, LociReadOutput]:
        """Expand one exact source extent named by a returned ``source_ref``.

        Follow ``next_source_ref`` until it is null to page an incomplete extent.
        ``SOURCE_STALE`` means the indexed source changed; make a fresh
        ``loci_retrieve`` request instead of reusing the old locator.
        """
        return _handle_loci_error(
            lambda service: service.read(
                repo,
                source_ref,
                ensure_fresh=True,
            )
        )

    @mcp.tool()
    def loci_index(
        repo: str,
        incremental: bool = True,
    ) -> Annotated[CallToolResult, LociIndexOutput]:
        """Index a local repository path into the loci cache."""
        return _handle_loci_error(
            lambda service: service.index_repo(repo, incremental=incremental)
        )

    @mcp.tool()
    def loci_outline(
        repo: str,
        file: str | None = None,
    ) -> Annotated[CallToolResult, LociOutlineOutput]:
        """Return indexed symbols grouped by file."""
        return _handle_loci_error(
            lambda service: {
                "files": service.outline_repo(repo, file=file, ensure_fresh=True)
            }
        )

    @mcp.tool()
    def loci_get(
        repo: str,
        symbol_ids: list[str],
        context: int = 0,
        selected_from_search_id: str | None = None,
        include_type_context: bool = False,
    ) -> Annotated[CallToolResult, LociGetOutput]:
        """Return exact source; opt in to bounded outgoing type definitions and supporting lines. Use loci_explore for complete import/re-export statements and Go/Rust control source. Set lineage only for deliberate search selections, not direct or hydration gets."""
        return _handle_loci_error(
            lambda service: service.get_symbols_result(
                repo,
                symbol_ids,
                context=context,
                ensure_fresh=True,
                selected_from_search_id=selected_from_search_id,
                include_type_context=include_type_context,
            )
        )

    @mcp.tool()
    def loci_explore(
        repo: str,
        intent: str,
        query: Annotated[str, Field(json_schema_extra={"maxLength": 4096})] = "",
        seed_ids: Annotated[
            list[str] | None,
            Field(json_schema_extra={"maxItems": 5, "uniqueItems": True}),
        ] = None,
        max_hops: Annotated[
            int | None,
            Field(json_schema_extra={"minimum": 0, "maximum": 4}),
        ] = None,
        max_output_bytes: Annotated[
            int | None,
            Field(
                strict=True,
                json_schema_extra={"minimum": 2048, "maximum": 262144},
            ),
        ] = 16_384,
        max_evidence_bytes: Annotated[
            int | None,
            Field(
                strict=True,
                json_schema_extra={"minimum": 0, "maximum": 65536},
            ),
        ] = 8_192,
        resolutions: list[str] | None = None,
    ) -> Annotated[CallToolResult, LociExploreOutput]:
        """Select bounded source for one explicit retrieval intent.

        ``locate`` returns anchors only. ``type_dependencies`` selects authored
        TypeScript/TSX and Python types/bases, Go types/embeddings, or Rust
        types/bounds/traits/impl sites. ``dependencies`` uses that selection and
        also supports JavaScript definite calls, imported values and direct bases.
        Rust self types can select explicit impl sites by reverse traversal;
        stored relationship direction and possible configuration remain explicit.
        ``impact`` follows incoming known static dependents, without runtime
        dispatch or exhaustive impact claims. Parsing support is broader than
        these semantic subsets; inspect unsupported-language and unresolved omissions.
        Query text is at most 4096 UTF-8 bytes; seeds are at most five
        unique IDs; hops are 0..4 (defaults: locate 0, dependencies 3, impact 1), output
        is 2048..262144 bytes for the complete MCP result, and source evidence
        is 0..65536 bytes. Omitted or null byte limits use 16384 and 8192 bytes.
        Use query terms to focus deeper type fields; inspect
        omissions and incomplete anchors. Impact is non-exhaustive. Use ``loci_get``
        for an exact symbol read and graph tools for diagnostics or other edges.
        """
        return _handle_loci_error(
            lambda service: service.explore(
                repo,
                query=query,
                intent=intent,
                seed_ids=seed_ids,
                max_hops=max_hops,
                max_output_bytes=(
                    16_384 if max_output_bytes is None else max_output_bytes
                ),
                max_evidence_bytes=(
                    8_192 if max_evidence_bytes is None else max_evidence_bytes
                ),
                resolutions=resolutions,
                ensure_fresh=True,
            )
        )

    @mcp.tool()
    def loci_graph_anchors(
        repo: str,
        question: str,
        seed_ids: list[str] | None = None,
        max_anchors: int = 10,
    ) -> Annotated[CallToolResult, LociGraphAnchorsOutput]:
        """Select a small, explained set of graph anchors for a question."""
        return _handle_loci_error(
            lambda service: service.graph_anchors(
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
    ) -> Annotated[CallToolResult, LociGraphNeighborsOutput]:
        """Return exact outgoing one-hop graph neighbours for indexed seed nodes."""
        return _handle_loci_error(
            lambda service: service.graph_neighbors(
                repo, seed_ids, ensure_fresh=True
            )
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
    ) -> Annotated[CallToolResult, LociGraphTraverseNeighborsOutput]:
        """Return filtered one-hop graph neighbours without widening exact reads."""
        return _handle_loci_error(
            lambda service: service.graph_traverse_neighbors(
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
    ) -> Annotated[CallToolResult, LociGraphPathsOutput]:
        """Find bounded endpoint paths with exact edge evidence."""
        return _handle_loci_error(
            lambda service: service.graph_paths(
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
    ) -> Annotated[CallToolResult, LociGraphRetrieveOutput]:
        """Retrieve bounded question-shaped graph evidence and rejected paths."""
        return _handle_loci_error(
            lambda service: service.graph_retrieve(
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
    def loci_graph_health(
        repo: str,
    ) -> Annotated[CallToolResult, LociGraphHealthOutput]:
        """Inspect loaded graph profiles, active record counts, and diagnostics."""
        return _handle_loci_error(
            lambda service: service.graph_health(repo, ensure_fresh=True)
        )

    @mcp.tool()
    def loci_graph_imports(
        repo: str,
        file: str | None = None,
        status: str = "all",
        offset: int = 0,
        limit: int = 100,
    ) -> Annotated[CallToolResult, LociGraphImportsOutput]:
        """Inspect bounded resolved and unresolved built-in import records."""
        return _handle_loci_error(
            lambda service: service.graph_imports(
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
        family: str = "symbol",
        detail: Annotated[
            str, Field(json_schema_extra={"enum": ["compact", "full"]}),
        ] = "compact",
        max_output_bytes: Annotated[
            SkipValidation[int],
            Field(json_schema_extra={"minimum": 2048, "maximum": 262144}),
        ] = DEFAULT_RECORD_OUTPUT_BYTES,
    ) -> Annotated[CallToolResult, LociGraphReferencesOutput]:
        """Inspect compact authored symbol or type reference sites.

        file filters sites written inside that file, not incoming references to
        its declarations. For incoming consumers, traverse from the exact target
        symbol with loci_graph_traverse_neighbors(direction="incoming"), or use
        loci_explore(intent="impact") for bounded known dependents.
        detail="full" includes raw bindings, candidates and supporting evidence.
        max_output_bytes bounds the complete UTF-8 JSON MCP result (2048..262144,
        default 16384); follow pagination.next_offset even when returned < limit.
        A record too large to fit returns OUTPUT_BUDGET_EXCEEDED with the required
        size; increase the budget or use compact detail without skipping it.
        """
        return _handle_loci_error(
            lambda service: graph_record_page(
                lambda: service.graph_references(
                    repo,
                    file=file,
                    status=cast(Literal["all", "resolved", "unresolved"], status),
                    offset=offset,
                    limit=limit,
                    family=cast(Literal["symbol", "type"], family),
                    ensure_fresh=True,
                ),
                kind="references", detail=detail, max_output_bytes=max_output_bytes,
            )
        )

    @mcp.tool()
    def loci_graph_calls(
        repo: str,
        file: str | None = None,
        status: str = "all",
        offset: int = 0,
        limit: int = 100,
        detail: Annotated[
            str, Field(json_schema_extra={"enum": ["compact", "full"]}),
        ] = "compact",
        max_output_bytes: Annotated[
            SkipValidation[int],
            Field(json_schema_extra={"minimum": 2048, "maximum": 262144}),
        ] = DEFAULT_RECORD_OUTPUT_BYTES,
    ) -> Annotated[CallToolResult, LociGraphCallsOutput]:
        """Inspect compact resolved and unresolved definite-call sites.

        file filters call sites inside that file. For incoming callers, traverse
        from the exact callee symbol with direction="incoming" and edge_types=["calls"].
        detail="full" includes raw call/binding spans and supporting evidence.
        max_output_bytes bounds the complete UTF-8 JSON MCP result (2048..262144,
        default 16384); follow pagination.next_offset even when returned < limit.
        A record too large to fit returns OUTPUT_BUDGET_EXCEEDED with the required
        size; increase the budget or use compact detail without skipping it.
        """
        return _handle_loci_error(
            lambda service: graph_record_page(
                lambda: service.graph_calls(
                    repo,
                    file=file,
                    status=cast(Literal["all", "resolved", "unresolved"], status),
                    offset=offset,
                    limit=limit,
                    ensure_fresh=True,
                ),
                kind="calls", detail=detail, max_output_bytes=max_output_bytes,
            )
        )

    @mcp.tool()
    def loci_search(
        repo: str,
        query: str,
        kind: str | None = None,
        lang: str | None = None,
        limit: int = 20,
        file_paths: SkipValidation[list[str] | None] = None,
    ) -> Annotated[CallToolResult, LociSearchOutput]:
        """Search indexed symbols and return an opaque id for explicit downstream selections."""
        return _handle_loci_error(
            lambda service: service.search_symbols_result(
                repo,
                query,
                kind=kind,
                lang=lang,
                limit=limit,
                file_paths=file_paths,
                ensure_fresh=True,
            )
        )

    @mcp.tool()
    def loci_file(
        repo: str,
        file_path: str,
        start_line: int | None = None,
        end_line: int | None = None,
    ) -> Annotated[CallToolResult, LociFileOutput]:
        """Read indexed source or tracked Go/Cargo controls by relative path and line range."""
        return _handle_loci_error(
            lambda service: service.get_cached_file(
                repo,
                file_path,
                start_line=start_line,
                end_line=end_line,
                ensure_fresh=True,
            )
        )

    @mcp.tool()
    def loci_grep(
        repo: str,
        pattern: str,
    ) -> Annotated[CallToolResult, LociGrepOutput]:
        """Regex-search cached files and report bounded repository coverage."""
        return _handle_loci_error(
            lambda service: service.grep_repo_result(
                repo, pattern, ensure_fresh=True
            )
        )

    @mcp.tool()
    def loci_verify(repo: str) -> Annotated[CallToolResult, LociVerifyOutput]:
        """Verify index integrity and content drift for an indexed repository."""
        return _handle_loci_error(lambda service: service.verify_repo(repo))

    @mcp.tool()
    def loci_list() -> Annotated[CallToolResult, LociListOutput]:
        """List repositories present in the loci cache."""
        return _handle_loci_error(lambda service: {"repos": service.list_repos()})

    @mcp.tool()
    def loci_store_health(
        offset: int = 0,
        limit: int = DEFAULT_HEALTH_LIMIT,
        max_catalog_bytes: int = DEFAULT_MAX_CATALOG_BYTES,
        max_index_bytes: int = DEFAULT_MAX_INDEX_BYTES,
        max_probe_paths: int = DEFAULT_MAX_PROBE_PATHS,
        max_probe_bytes: int = DEFAULT_MAX_PROBE_BYTES,
    ) -> Annotated[CallToolResult, LociStoreHealthOutput]:
        """Inspect bounded read-only freshness, liveness, integrity, and overlaps."""
        return _handle_loci_error(
            lambda service: service.store_health(
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
    ) -> Annotated[CallToolResult, LociStatsOutput]:
        """Return structured session retrieval stats for the active loci store."""
        return _handle_loci_error(
            lambda service: service.session_stats(
                repo=repo,
                since_days=None if all_time else since_days,
            )
        )

    @mcp.tool()
    def loci_analyze(
        repo: str | None = None,
        since_days: int = 30,
    ) -> Annotated[CallToolResult, LociAnalyzeOutput]:
        """Analyze loci usage logs and return actionable tool-quality findings."""
        return _handle_loci_error(
            lambda service: service.analyze_usage(repo=repo, since_days=since_days)
        )

    if selected_surface == "normal":
        for tool_name in _DIAGNOSTIC_TOOL_NAMES:
            mcp._tool_manager.remove_tool(tool_name)
    else:
        for tool_name in _NORMAL_TOOL_NAMES:
            mcp._tool_manager.remove_tool(tool_name)
    return mcp


def _handle_loci_error(operation: Callable[[ModuleType], Any]) -> CallToolResult:
    service = _service()
    try:
        return _success(operation(service))
    except service.LociError as exc:
        return CallToolResult(
            content=[
                TextContent(
                    type="text",
                    text=f"{exc.code}: {exc.message}",
                )
            ],
            structured_content={"error": exc.to_dict()},
            is_error=True,
        )


def _success(payload: dict[str, Any]) -> CallToolResult:
    return CallToolResult(
        content=[],
        structured_content=payload,
        is_error=False,
    )


mcp = create_server()
_startup_phase("tool_schemas_ready")


def main() -> None:
    _startup_phase("store_bind_started")
    try:
        activate_mcp_store(bind_mcp_store())
    except StoreIdentityError as exc:
        print(json.dumps({"error": exc.to_dict()}), file=sys.stderr)
        raise SystemExit(78) from exc
    _startup_phase("store_bound")
    _startup_phase("stdio_run_entered")
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
