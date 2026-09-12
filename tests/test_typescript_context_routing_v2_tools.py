from __future__ import annotations

import asyncio
import copy
from typing import cast

import pytest
from mcp.server.mcpserver.exceptions import ToolError

from benchmarks.typescript_context_routing_v2_tools import (
    RoutingAdapter, TOOL_NAMES, create_server, normalize_arguments,
)
from tests.test_typescript_context_explore_tools import _FakeAdapter


@pytest.mark.parametrize("limits", [
    {}, {"max_output_bytes": None, "max_evidence_bytes": None},
    {"max_output_bytes": None}, {"max_evidence_bytes": None},
])
def test_omitted_and_null_limits_have_identical_effective_defaults(limits):
    arguments = {"intent": "type_dependencies", **limits}
    before = copy.deepcopy(arguments)
    assert normalize_arguments("loci_explore", arguments) == {
        "intent": "type_dependencies", "query": "",
        "max_output_bytes": 16_384, "max_evidence_bytes": 8_192,
    }
    assert arguments == before


def test_same_nullable_schema_and_common_tools_for_both_conditions():
    schemas = []
    for arm in ("A", "B"):
        server = create_server(cast(RoutingAdapter, _FakeAdapter(arm)))
        tools = asyncio.run(server.list_tools())
        assert {tool.name for tool in tools} == TOOL_NAMES
        schemas.append([tool.model_dump() for tool in tools])
        schema = next(tool.input_schema for tool in tools if tool.name == "loci_explore")
        assert schema["additionalProperties"] is False
        for field, default, maximum in (
            ("max_output_bytes", 16_384, 32_768),
            ("max_evidence_bytes", 8_192, 16_384),
        ):
            value = schema["properties"][field]
            assert {item["type"] for item in value["anyOf"]} == {"integer", "null"}
            assert value["default"] == default
            assert value["maximum"] == maximum
    assert schemas[0] == schemas[1]


@pytest.mark.parametrize("limits,expected", [
    ({}, (16_384, 8_192)),
    ({"max_output_bytes": None, "max_evidence_bytes": None}, (16_384, 8_192)),
    ({"max_output_bytes": None, "max_evidence_bytes": 0}, (16_384, 0)),
    ({"max_output_bytes": 2_048, "max_evidence_bytes": None}, (2_048, 8_192)),
    ({"max_output_bytes": 32_768, "max_evidence_bytes": 16_384}, (32_768, 16_384)),
])
def test_mcp_dispatch_preserves_valid_limits(limits, expected):
    adapter = _FakeAdapter()
    server = create_server(cast(RoutingAdapter, adapter))
    asyncio.run(server.call_tool("loci_explore", {"intent": "type_dependencies", **limits}))
    operation, arguments = adapter.calls[0]
    assert operation == "loci_explore"
    assert (arguments["max_output_bytes"], arguments["max_evidence_bytes"]) == expected


@pytest.mark.parametrize("field,value", [
    ("max_output_bytes", 2_047), ("max_output_bytes", 32_769),
    ("max_evidence_bytes", -1), ("max_evidence_bytes", 16_385),
    *[(field, value) for field in ("max_output_bytes", "max_evidence_bytes")
      for value in (True, "8192", 8192.0, [], {})],
])
def test_invalid_explicit_values_never_enter_adapter(field, value):
    adapter = _FakeAdapter()
    server = create_server(cast(RoutingAdapter, adapter))
    arguments = {"intent": "locate", field: value}
    with pytest.raises((TypeError, ValueError)):
        normalize_arguments("loci_explore", arguments)
    with pytest.raises(ToolError):
        asyncio.run(server.call_tool("loci_explore", arguments))
    assert adapter.calls == []
