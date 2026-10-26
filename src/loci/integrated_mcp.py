"""R1 experimental stdio interface; never changes the production entrypoint."""
from __future__ import annotations

import os
from pathlib import Path
from threading import Lock
from typing import Annotated, Callable

from mcp.server.mcpserver import MCPServer
from mcp.types import CallToolResult
from pydantic import Field

from .graph_free import GraphFreeError
from .integrated import IntegratedSource


def create_server(store: Path, *, source_only: bool = False) -> MCPServer:
    service = IntegratedSource(store)
    # MCP executes synchronous tools in worker threads. Inventory writes and
    # the single retained proof slice must finish before another operation.
    operation_lock = Lock()
    server = MCPServer("loci", instructions=(
        "Find source with loci_retrieve; use loci_read for incomplete source_ref extents. "
        "Navigation candidates are paths to inspect, not resolved relationships. "
        "Results are in structuredContent, with exact source hashes and explicit omissions. "
        + ("Only source navigation is available." if source_only else
           "Request loci_semantic only when static relationships help the task. "
           "Use loci_proof for focused evidence on a node ID returned by the most recent "
           "semantic request or its proof followups. Proof is bounded and non-exhaustive. "
           "Preserve unresolved observations and configuration uncertainty.")))

    def invoke(operation: Callable[[], dict]) -> CallToolResult:
        try:
            with operation_lock:
                packet = operation()
            return CallToolResult(content=[], structuredContent=packet, isError=False)
        except GraphFreeError as exc:
            error = {"code": exc.code, "message": exc.message, "details": exc.details}
        except (OSError, ValueError) as exc:
            error = {"code": "SOURCE_UNAVAILABLE", "message": str(exc), "details": {}}
        return CallToolResult(content=[], structuredContent={"error": error}, isError=True)

    @server.tool()
    def loci_retrieve(
        repo: Annotated[str, Field(strict=True, min_length=1)],
        query: Annotated[str, Field(strict=True, max_length=1024)] = "",
        seed_ids: Annotated[list[str] | None, Field(max_length=1)] = None,
    ) -> CallToolResult:
        """Find bounded current source by words or exact relative file path.

        Alternatively re-anchor one previously returned node_id in seed_ids.
        Navigation candidates are source paths, including alternatives; inspect
        them with another retrieval. This operation performs no semantic parsing.
        Expand incomplete items with loci_read using the unchanged source_ref.
        """
        return invoke(lambda: service.retrieve(repo, query, seed_ids=seed_ids))

    @server.tool()
    def loci_read(
        repo: Annotated[str, Field(strict=True, min_length=1)],
        source_ref: Annotated[str, Field(strict=True, min_length=1)],
    ) -> CallToolResult:
        """Read a returned hash-bound source extent; follow next_source_ref until complete.

        SOURCE_STALE requires new retrieval or semantic acquisition. Works with
        both ordinary source and semantic proof source references.
        """
        return invoke(lambda: service.read(repo, source_ref))

    if not source_only:
        @server.tool()
        def loci_semantic(
            repo: Annotated[str, Field(strict=True, min_length=1)],
            query: Annotated[str, Field(strict=True, min_length=1, max_length=1024)],
            anchor_file: str | None = None,
        ) -> CallToolResult:
            """Request bounded static JS/TS/Rust relationships for a source question.

            Optionally anchor to a repository-relative file already located.
            Includes complete source proof for emitted relationships and native
            uncertainty; omissions and empty output never prove absence. Python
            and Go semantics are unsupported. Retains one slice for followup proof.
            """
            return invoke(lambda: service.semantic_context(repo, query, anchor_file=anchor_file))

        @server.tool()
        def loci_proof(
            repo: Annotated[str, Field(strict=True, min_length=1)],
            node_id: Annotated[str, Field(strict=True, min_length=1)],
        ) -> CallToolResult:
            """Request focused proof for one previously delivered semantic node ID.

            Reuses the most recent computed slice without new resolution. Can
            follow IDs returned by proof itself. Repository changes require a
            fresh loci_semantic request. Missing proof remains unknown.
            """
            return invoke(lambda: service.proof_context(repo, node_id))
    return server


def main() -> None:
    value = os.environ.get("LOCI_R1_STORE", "")
    if not value or not Path(value).is_absolute():
        raise SystemExit("LOCI_R1_STORE must name an absolute experimental store directory")
    mode = os.environ.get("LOCI_R1_SOURCE_ONLY", "0")
    if mode not in {"0", "1"}:
        raise SystemExit("LOCI_R1_SOURCE_ONLY must be 0 or 1")
    create_server(Path(value), source_only=mode == "1").run(transport="stdio")


if __name__ == "__main__":
    main()
