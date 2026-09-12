"""Focused contract checks for the multilingual comparison tool adapter."""
from __future__ import annotations

import asyncio
from typing import cast

import pytest
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import CallToolResult

from benchmarks.multilingual_context_tools import (
    TOOL_NAMES_A,
    TOOL_NAMES_B,
    MultilingualAdapter,
    create_server,
    normalize_arguments,
)


class _FakeAdapter:
    def __init__(self, arm: str) -> None:
        self.lock = asyncio.Lock()
        self.run = {"arm": arm}
        self.calls: list[tuple[str, dict]] = []

    def read_operation(self, operation: str, parameters: dict) -> CallToolResult:
        self.calls.append((operation, parameters))
        return CallToolResult(content=[], structured_content={"operation": operation, "arguments": parameters})


def test_arms_share_exact_schemas_and_b_adds_only_explore() -> None:
    server_a = create_server(cast(MultilingualAdapter, _FakeAdapter("A")), "A")
    server_b = create_server(cast(MultilingualAdapter, _FakeAdapter("B")), "B")
    tools_a = {tool.name: tool for tool in asyncio.run(server_a.list_tools())}
    tools_b = {tool.name: tool for tool in asyncio.run(server_b.list_tools())}

    assert set(tools_a) == set(TOOL_NAMES_A)
    assert set(tools_b) == set(TOOL_NAMES_B)
    assert set(tools_b) - set(tools_a) == {"loci_explore"}
    for name in tools_a:
        assert tools_a[name].input_schema == tools_b[name].input_schema
    schema = tools_b["loci_explore"].input_schema
    assert schema["required"] == ["intent"]
    assert schema["additionalProperties"] is False
    assert schema["properties"]["max_hops"]["maximum"] == 3
    assert schema["properties"]["max_output_bytes"]["maximum"] == 16_384
    assert schema["properties"]["max_evidence_bytes"]["maximum"] == 8_192
    assert set(schema["properties"]["intent"]["enum"]) == {
        "locate", "type_dependencies", "dependencies", "impact",
    }
    assert "TypeScript-only" not in tools_b["loci_explore"].description
    assert "JavaScript definite calls" in tools_b["loci_explore"].description


def test_explore_normalization_resolves_null_and_rejects_wrong_types() -> None:
    assert normalize_arguments("loci_explore", {"intent": "dependencies"}) == {
        "intent": "dependencies",
        "query": "",
        "max_output_bytes": 16_384,
        "max_evidence_bytes": 8_192,
    }
    assert normalize_arguments(
        "loci_explore",
        {"intent": "locate", "max_output_bytes": None, "max_evidence_bytes": None},
    )["max_output_bytes"] == 16_384
    assert normalize_arguments(
        "loci_explore",
        {"intent": "locate", "max_output_bytes": None, "max_evidence_bytes": None},
    )["max_evidence_bytes"] == 8_192
    assert normalize_arguments(
        "loci_explore",
        {"intent": "locate", "max_output_bytes": 2_048, "max_evidence_bytes": 0},
    )["max_evidence_bytes"] == 0

    invalid = [
        {"intent": "missing"},
        {"intent": "locate", "repo": "outside"},
        {"intent": "locate", "ensure_fresh": True},
        {"intent": "locate", "max_hops": 4},
        {"intent": "locate", "max_output_bytes": 16_385},
        {"intent": "locate", "max_evidence_bytes": 8_193},
        {"intent": "locate", "max_evidence_bytes": False},
        {"intent": "locate", "resolutions": ["heuristic"]},
        {"intent": "locate", "seed_ids": ["same", "same"]},
    ]
    for raw in invalid:
        with pytest.raises((TypeError, ValueError)):
            normalize_arguments("loci_explore", raw)


def test_server_forwards_dependencies_and_rejects_invalid_stdio_arguments() -> None:
    adapter = _FakeAdapter("B")
    server = create_server(cast(MultilingualAdapter, adapter), "B")

    async def check() -> None:
        response = await server.call_tool(
            "loci_explore",
            {"intent": "dependencies", "max_output_bytes": None, "max_evidence_bytes": 0},
        )
        assert response.structured_content == {
            "operation": "loci_explore",
            "arguments": {
                "intent": "dependencies", "query": "", "max_output_bytes": 16_384,
                "max_evidence_bytes": 0,
            },
        }
        with pytest.raises(ToolError):
            await server.call_tool("loci_explore", {"intent": "locate", "max_hops": "3"})
        server_a = create_server(cast(MultilingualAdapter, _FakeAdapter("A")), "A")
        with pytest.raises(ToolError):
            await server_a.call_tool("loci_explore", {"intent": "locate"})

    asyncio.run(check())
    assert adapter.calls == [("loci_explore", adapter.calls[0][1])]
