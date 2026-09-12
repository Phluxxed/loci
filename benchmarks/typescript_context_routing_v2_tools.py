"""Repaired routing surface; frozen v1 tools and traces remain unchanged.

Only null byte-limit defaults differ from the original exploration contract.
The adapter ledger records effective integers; host events retain raw arguments.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Annotated, Any, Literal

from mcp.server.mcpserver import MCPServer
from mcp.types import CallToolResult
from pydantic import Field

from benchmarks import typescript_context_explore_tools as original
from benchmarks import typescript_context_tools_v3 as exact
from benchmarks.typescript_context_routing_tools import RoutingAdapter as OriginalAdapter


VERSION = "typescript-context-routing-v2"
PROTOCOL = VERSION
TOOL_NAMES = original.TOOL_NAMES_B
DEFAULT_OUTPUT_BYTES = 16_384
DEFAULT_EVIDENCE_BYTES = 8_192


def normalize_arguments(tool_name: str, raw_args: dict[str, Any]) -> dict[str, Any]:
    """Resolve only absent/null byte limits; retain every original strict bound."""
    if tool_name == "loci_explore":
        raw_args = dict(exact._require_mapping(tool_name, raw_args))
        for field, default in (
            ("max_output_bytes", DEFAULT_OUTPUT_BYTES),
            ("max_evidence_bytes", DEFAULT_EVIDENCE_BYTES),
        ):
            if raw_args.get(field) is None:
                raw_args[field] = default
    return original.normalize_arguments(tool_name, raw_args)


class RoutingAdapter(OriginalAdapter):
    """Use repaired argument defaults with the existing snapshot/cost ledger."""

    def read_operation(self, operation: str, parameters: dict) -> CallToolResult:
        public = "loci_explore" if operation == "explore" else operation
        return super().read_operation(public, normalize_arguments(public, parameters))


def create_server(adapter: RoutingAdapter) -> MCPServer:
    """Expose the same fourteen tools in both routing conditions."""
    server = exact.create_server(adapter)

    @server.tool(
        annotations=exact._READ_ONLY,
        structured_output=False,
    )
    async def loci_explore(
        intent: Literal["locate", "type_dependencies", "impact"],
        query: Annotated[str, Field(json_schema_extra={"maxLength": 4096})] = "",
        seed_ids: Annotated[
            list[str] | None, Field(json_schema_extra={"maxItems": 5, "uniqueItems": True}),
        ] = None,
        max_hops: Annotated[
            int | None, Field(json_schema_extra={"minimum": 0, "maximum": 3}),
        ] = None,
        max_output_bytes: Annotated[
            int | None, Field(json_schema_extra={"minimum": 2048, "maximum": 32_768}),
        ] = DEFAULT_OUTPUT_BYTES,
        max_evidence_bytes: Annotated[
            int | None, Field(json_schema_extra={"minimum": 0, "maximum": 16_384}),
        ] = DEFAULT_EVIDENCE_BYTES,
        resolutions: list[str] | None = None,
    ) -> CallToolResult:
        """Select bounded source for one explicit retrieval intent.

        ``locate`` returns anchors only; ``type_dependencies`` follows outgoing
        proven TypeScript/TSX type and heritage edges; ``impact`` follows incoming known static
        dependents. Query text is at most 4096 UTF-8 bytes; seeds are at most five
        unique IDs; hops are 0..3 (defaults: locate 0, type 3, impact 1), output
        is 2048..32768 bytes for the complete MCP result, and source evidence
        is 0..16384 bytes. Omitted or null byte limits use defaults 16384 and 8192.
        Use query terms to focus deeper type fields; inspect omissions and incomplete
        anchors. Impact is non-exhaustive. Use ``loci_get`` for an exact symbol read
        and graph tools for diagnostics or other edges.
        """
        arguments = normalize_arguments("loci_explore", {
            "intent": intent, "query": query, "seed_ids": seed_ids,
            "max_hops": max_hops, "max_output_bytes": max_output_bytes,
            "max_evidence_bytes": max_evidence_bytes, "resolutions": resolutions,
        })
        async with adapter.lock:
            return adapter.read_operation("loci_explore", arguments)

    exact._strict_tool_arguments(server)
    return server


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run", type=Path)
    args = parser.parse_args()
    create_server(RoutingAdapter(json.loads(args.run.read_text(encoding="utf-8")))).run()


if __name__ == "__main__":
    main()
