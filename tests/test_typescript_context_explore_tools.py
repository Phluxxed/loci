from __future__ import annotations

import asyncio
import hashlib
from pathlib import Path
from typing import cast

import pytest
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import CallToolResult

from benchmarks.typescript_context_corpus import _isolated_store, load_corpus, materialize_snapshot
from benchmarks.typescript_context_explore_tools import (
    ExploreAdapter,
    TOOL_NAMES_A,
    TOOL_NAMES_B,
    create_server,
    normalize_arguments,
)
from loci import service


CORPUS_ROOT = Path(__file__).parents[1] / "benchmarks" / "corpora" / "typescript-context-v3"


class _FakeAdapter:
    def __init__(self, arm: str = "B") -> None:
        self.lock = asyncio.Lock()
        self.run = {"arm": arm}
        self.calls: list[tuple[str, dict]] = []

    def read_operation(self, operation: str, parameters: dict) -> CallToolResult:
        self.calls.append((operation, parameters))
        return CallToolResult(content=[], structured_content={"operation": operation, "arguments": parameters})


@pytest.fixture
def explore_adapter(tmp_path: Path):
    corpus = load_corpus(CORPUS_ROOT)
    repo = tmp_path / "snapshot"
    materialize_snapshot(corpus, "imported_interface", repo)
    run = {
        "repo": str(repo),
        "corpus_root": str(CORPUS_ROOT),
        "case_id": "imported_interface",
        "session_id": "explore-tools-imported-interface",
        "arm": "B",
        "repetition": 1,
        "trace_path": str(tmp_path / "trace.json"),
    }
    store = tmp_path / "cache"
    with _isolated_store(store):
        service.index_repo(repo, incremental=False)
        yield ExploreAdapter(run), corpus, run


def test_arm_tool_sets_are_closed_and_explore_is_b_only() -> None:
    assert "loci_explore" not in TOOL_NAMES_A
    assert TOOL_NAMES_B == TOOL_NAMES_A | {"loci_explore"}
    server_a = create_server(cast(ExploreAdapter, _FakeAdapter("A")), "A")
    server_b = create_server(cast(ExploreAdapter, _FakeAdapter("B")), "B")
    names_a = {tool.name for tool in asyncio.run(server_a.list_tools())}
    names_b = {tool.name for tool in asyncio.run(server_b.list_tools())}
    assert names_a == set(TOOL_NAMES_A)
    assert names_b == set(TOOL_NAMES_B)

    explore = next(tool for tool in asyncio.run(server_b.list_tools()) if tool.name == "loci_explore")
    schema = explore.input_schema
    assert schema["required"] == ["intent"]
    assert set(schema["properties"]) == {
        "intent",
        "query",
        "seed_ids",
        "max_hops",
        "max_output_bytes",
        "max_evidence_bytes",
        "resolutions",
    }
    assert schema["additionalProperties"] is False
    assert schema["properties"]["max_hops"]["maximum"] == 3
    assert "repo" not in schema["properties"]
    assert "ensure_fresh" not in schema["properties"]


def test_explore_normalization_has_product_defaults_and_strict_bounds() -> None:
    assert normalize_arguments("loci_explore", {"intent": "locate"}) == {
        "intent": "locate",
        "query": "",
        "max_output_bytes": 16_384,
        "max_evidence_bytes": 8_192,
    }
    assert normalize_arguments(
        "loci_explore",
        {
            "intent": "type_dependencies",
            "query": "ImportedPayload",
            "seed_ids": [],
            "max_hops": 3,
            "max_output_bytes": 32_768,
            "max_evidence_bytes": 16_384,
            "resolutions": [],
        },
    ) == {
        "intent": "type_dependencies",
        "query": "ImportedPayload",
        "seed_ids": [],
        "max_hops": 3,
        "max_output_bytes": 32_768,
        "max_evidence_bytes": 16_384,
        "resolutions": [],
    }
    bad = [
        {"intent": "unknown"},
        {"intent": "locate", "repo": "snapshot"},
        {"intent": "locate", "ensure_fresh": True},
        {"intent": "locate", "query": "x" * 4097},
        {"intent": "locate", "seed_ids": ["a"] * 6},
        {"intent": "locate", "seed_ids": ["a", "a"]},
        {"intent": "locate", "max_hops": 5},
        {"intent": "locate", "max_output_bytes": 2_047},
        {"intent": "locate", "max_evidence_bytes": 65_537},
        {"intent": "locate", "resolutions": ["declared"]},
    ]
    for arguments in bad:
        with pytest.raises((TypeError, ValueError)):
            normalize_arguments("loci_explore", arguments)


def test_server_forwards_explore_arguments_and_keeps_a_closed() -> None:
    adapter = _FakeAdapter("B")
    server = create_server(cast(ExploreAdapter, adapter), "B")

    async def call() -> CallToolResult:
        result = await server.call_tool("loci_explore", {"intent": "locate", "query": "Thing"})
        assert isinstance(result, CallToolResult)
        return result

    result = asyncio.run(call())
    assert result.structured_content == {
        "operation": "loci_explore",
        "arguments": {
            "intent": "locate",
            "query": "Thing",
            "max_output_bytes": 16_384,
            "max_evidence_bytes": 8_192,
        },
    }
    assert adapter.calls == [("loci_explore", result.structured_content["arguments"])]

    server_a = create_server(cast(ExploreAdapter, _FakeAdapter("A")), "A")

    async def missing_tool() -> None:
        with pytest.raises(ToolError):
            await server_a.call_tool("loci_explore", {"intent": "locate", "query": "Thing"})

    asyncio.run(missing_tool())


def test_real_product_explore_dispatch_records_every_shared_source(explore_adapter) -> None:
    adapter, _corpus, _run = explore_adapter
    result = adapter.read_operation(
        "loci_explore",
        {"intent": "type_dependencies", "query": "processOrder"},
    )
    payload = result.structured_content
    assert payload["intent"] == "type_dependencies"
    assert payload["relationships"]
    assert payload["sources"]
    event = adapter.trace.events[-1]
    delivery = adapter.deliveries[-1]
    assert event["operation"] == "explore"
    assert len(event["spans"]) == len(payload["sources"])
    assert delivery["operation"] == "explore"
    assert delivery["source_bytes"] == sum(
        span["end_byte"] - span["start_byte"] for span in event["spans"]
    )
    source_ids = {source["id"] for source in payload["sources"]}
    for relationship in payload["relationships"]:
        assert set(relationship["source_ids"]) <= source_ids
    for source in payload["sources"]:
        raw = adapter.trace.files[source["file"]]
        content = source["content"].encode("utf-8")
        assert raw[source["start_byte"] : source["end_byte"]] == content
        assert hashlib.sha256(raw).hexdigest() == source["content_hash"]


def test_explore_visible_node_guard_withholds_source(monkeypatch, explore_adapter) -> None:
    adapter, _corpus, _run = explore_adapter

    def too_many_nodes(*_args, **_kwargs):
        return {
            "schema_version": 1,
            "intent": "locate",
            "status": "ok",
            "selection": "inferred",
            "scope": {
                "source": "indexed_supported_source",
                "coverage": "complete",
                "relationships": "none",
                "exhaustive": False,
            },
            "items": [],
            "relationships": [],
            "sources": [],
            "omissions": [],
            "limits": {},
            "usage": {"nodes_examined": 33},
        }

    monkeypatch.setattr("benchmarks.typescript_context_explore_tools.service.explore", too_many_nodes)
    result = adapter.read_operation("loci_explore", {"intent": "locate", "query": "processOrder"})
    assert result.structured_content["error"]["code"] == "BUDGET_EXHAUSTED"
    assert result.structured_content["error"]["limits"] == ["max_nodes"]
    assert adapter.trace.events[-1]["spans"] == []
    assert adapter.deliveries[-1]["source_bytes"] == 0
    assert adapter.failures[-1]["category"] == "budget_exhausted"
    assert adapter.failures[-1]["limit"] == "max_nodes"


def test_arm_a_cannot_dispatch_explore(explore_adapter) -> None:
    _adapter, _corpus, run = explore_adapter
    run = {**run, "arm": "A", "session_id": "explore-tools-arm-a"}
    adapter = ExploreAdapter(run)
    with pytest.raises(ValueError, match="arm B"):
        adapter.read_operation("loci_explore", {"intent": "locate", "query": "Thing"})
