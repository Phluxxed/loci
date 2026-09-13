from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import CallToolResult

from benchmarks.typescript_context_tools_v3 import (
    ObservedAdapter,
    TOOL_NAMES,
    create_server,
    normalize_arguments,
)
from benchmarks.typescript_context_corpus import (
    _isolated_store,
    load_corpus,
    materialize_snapshot,
)
from loci.service import index_repo


CORPUS_ROOT = Path(__file__).parents[1] / "benchmarks" / "corpora" / "typescript-context-v3"


class _FakeAdapter:
    def __init__(self) -> None:
        self.lock = asyncio.Lock()
        self.calls: list[tuple[str, dict]] = []

    def read_operation(self, operation: str, parameters: dict) -> CallToolResult:
        self.calls.append((operation, parameters))
        return CallToolResult(content=[], structured_content={
            "operation": operation,
            "arguments": parameters,
        })


@pytest.fixture
def observed_adapter(tmp_path: Path):
    corpus = load_corpus(CORPUS_ROOT)
    repo = tmp_path / "snapshot"
    materialize_snapshot(corpus, "imported_interface", repo)
    trace_path = tmp_path / "trace.json"
    run = {
        "repo": str(repo),
        "corpus_root": str(CORPUS_ROOT),
        "case_id": "imported_interface",
        "session_id": "adapter-v3-imported-interface",
        "arm": "A",
        "repetition": 1,
        "trace_path": str(trace_path),
    }
    with _isolated_store(tmp_path / "cache"):
        index_repo(repo, incremental=False)
        yield ObservedAdapter(run), trace_path


def test_normalize_arguments_uses_contract_defaults_and_omits_none() -> None:
    assert normalize_arguments("search", {"query": "Thing", "kind": None}) == {
        "query": "Thing",
    }
    assert normalize_arguments("get", {"symbol_ids": ["thing"]}) == {
        "symbol_ids": ["thing"],
        "context": 0,
    }
    assert normalize_arguments("graph_imports", {}) == {
        "status": "all",
        "offset": 0,
        "limit": 20,
    }

    with pytest.raises((TypeError, ValueError)):
        normalize_arguments("grep", {"pattern": "x", "because": "event"})
    with pytest.raises((TypeError, ValueError)):
        normalize_arguments("get", {"symbol_ids": ["thing"], "context": True})


def test_v3_server_advertises_closed_typed_tools_without_intent_fields() -> None:
    server = create_server(_FakeAdapter())
    tools = asyncio.run(server.list_tools())
    assert {tool.name for tool in tools} == set(TOOL_NAMES)

    for tool in tools:
        assert tool.input_schema["type"] == "object"
        assert tool.input_schema["additionalProperties"] is False
        assert not ({"reason", "detail", "because"} & set(tool.input_schema["properties"]))

    schemas = {tool.name: tool.input_schema for tool in tools}
    assert schemas["search"]["required"] == ["query"]
    assert schemas["get"]["properties"]["context"]["default"] == 0
    assert schemas["graph_imports"]["properties"]["limit"]["default"] == 20
    assert "limit" not in schemas["search"]["properties"]


def test_v3_server_forwards_normalized_arguments_and_preserves_result() -> None:
    adapter = _FakeAdapter()
    server = create_server(adapter)

    async def calls() -> list[CallToolResult]:
        return [
            await server.call_tool("search", {"query": "Thing"}),
            await server.call_tool("get", {"symbol_ids": ["id"]}),
            await server.call_tool("grep", {"pattern": "return"}),
        ]

    results = asyncio.run(calls())
    assert [result.structured_content for result in results] == [
        {"operation": "search", "arguments": {"query": "Thing"}},
        {"operation": "get", "arguments": {"symbol_ids": ["id"], "context": 0}},
        {"operation": "grep", "arguments": {"pattern": "return"}},
    ]
    assert adapter.calls == [
        ("search", {"query": "Thing"}),
        ("get", {"symbol_ids": ["id"], "context": 0}),
        ("grep", {"pattern": "return"}),
    ]


def test_v3_server_runtime_rejects_extra_and_coercible_arguments() -> None:
    server = create_server(_FakeAdapter())

    async def invalid_calls() -> None:
        with pytest.raises(ToolError):
            await server.call_tool("search", {"query": "Thing", "because": "event"})
        with pytest.raises(ToolError):
            await server.call_tool("get", {"symbol_ids": ["id"], "context": True})
        with pytest.raises(ToolError):
            await server.call_tool("grep", {"pattern": 42})

    asyncio.run(invalid_calls())


def test_observed_adapter_records_v3_shape_without_intent_fields(observed_adapter) -> None:
    adapter, trace_path = observed_adapter
    result = adapter.read_operation("search", {"query": "processOrder"})
    payload = result.structured_content

    assert payload["_evaluation"] == {
        "attempt_id": "adapter-v3-imported-interface/attempt/1",
        "calls_remaining": 23,
    }
    assert set(adapter.deliveries[0]) == {
        "attempt_id", "operation", "arguments", "response_json", "serialized_bytes",
        "source_bytes", "elapsed_ms", "trace_event_id", "status", "spans",
    }
    assert {"reason", "detail", "because"}.isdisjoint(adapter.trace.events[0])
    saved = json.loads(trace_path.read_text(encoding="utf-8"))
    assert saved["schema_version"] == 3
    assert saved["deliveries"] == adapter.deliveries
    assert saved["events"] == adapter.trace.events
