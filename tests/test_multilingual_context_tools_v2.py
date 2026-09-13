"""Contract and loopback-MCP checks for the future multilingual tool surface."""
from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
import sys
from typing import cast

import pytest
from mcp import Client, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import CallToolResult

from benchmarks.multilingual_context_observed import MultilingualObservedTrace
from benchmarks.multilingual_context_tools_v2 import (
    PROTOCOL,
    TOOL_NAMES_A,
    TOOL_NAMES_B,
    MultilingualAdapter,
    create_server,
    normalize_arguments,
)
from benchmarks.multilingual_context_inputs import load_inputs
from benchmarks.typescript_context_corpus import _isolated_store, materialize_snapshot
from loci import service


CONTROLS_PATH = (
    Path(__file__).parents[1]
    / "benchmarks"
    / "comparisons"
    / "multilingual-context-workflow-v1"
    / "inputs"
    / "comparison-controls.json"
)
ROOT = Path(__file__).parents[1]


def _server_params(run_file: Path) -> StdioServerParameters:
    """Start the versioned module's real ``main`` over its stdio boundary."""

    env = os.environ.copy()
    python_path = [str(ROOT), str(ROOT / "src")]
    if env.get("PYTHONPATH"):
        python_path.append(env["PYTHONPATH"])
    env["PYTHONPATH"] = os.pathsep.join(python_path)
    return StdioServerParameters(
        command=sys.executable,
        args=["-m", "benchmarks.multilingual_context_tools_v2", str(run_file)],
        env=env,
        cwd=ROOT,
    )


class _FakeAdapter:
    def __init__(self, arm: str) -> None:
        self.lock = asyncio.Lock()
        self.run = {"arm": arm}
        self.calls: list[tuple[str, dict]] = []

    def read_operation(self, operation: str, parameters: dict) -> CallToolResult:
        self.calls.append((operation, parameters))
        return CallToolResult(content=[], structured_content={"operation": operation, "arguments": parameters})


class _BoundedFakeAdapter(_FakeAdapter):
    """Exercise the same normalization entrypoint as the concrete v2 adapter."""

    def read_operation(self, operation: str, parameters: dict) -> CallToolResult:
        public = "loci_explore" if operation == "explore" else operation
        return super().read_operation(operation, normalize_arguments(public, parameters))


def _write_snapshot(repo: Path) -> dict[str, bytes]:
    sources = {
        "go.mod": b"module example.test/control\n\ngo 1.25\n// caf\xc3\xa9\n",
        "main.go": b"package main\n\nfunc main() {}\n",
        "crates/widget/Cargo.toml": (
            b"[package]\nname = \"widget\"\nversion = \"0.1.0\"\n"
            b"edition = \"2024\"\n# caf\xc3\xa9\n"
        ),
        "crates/widget/src/lib.rs": b"pub fn widget() {}\n",
    }
    for relative, content in sources.items():
        target = repo / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
    return sources


def _adapter(repo: Path, files: dict[str, bytes], arm: str) -> MultilingualAdapter:
    controls = json.loads(CONTROLS_PATH.read_text(encoding="utf-8"))
    index = service.get_store().load(repo)
    assert index is not None

    trace = MultilingualObservedTrace.__new__(MultilingualObservedTrace)
    trace.files = files
    trace.identity = {
        "task_id": "v2-tool-contract",
        "session_id": f"v2-tool-contract-{arm}",
        "arm": arm,
        "repetition": 1,
        "snapshot": "temporary-v2-tool-contract",
    }
    trace.events = []

    adapter = MultilingualAdapter.__new__(MultilingualAdapter)
    adapter.run = {"arm": arm}
    adapter.repo = repo.resolve()
    adapter.limits = dict(controls["limits"])
    adapter.trace = trace
    adapter.symbols = {symbol["id"]: symbol for symbol in index["symbols"]}
    adapter.lines = {name: content.decode("utf-8").splitlines(keepends=True) for name, content in files.items()}
    adapter.failures = []
    adapter.deliveries = []
    adapter.lock = asyncio.Lock()
    adapter.attempts = 0
    adapter.is_v2 = True
    return adapter


def test_v2_schema_publishes_the_dispatch_boundaries_for_both_arms() -> None:
    server_a = create_server(cast(MultilingualAdapter, _FakeAdapter("A")), "A")
    server_b = create_server(cast(MultilingualAdapter, _FakeAdapter("B")), "B")
    tools_a = {tool.name: tool for tool in asyncio.run(server_a.list_tools())}
    tools_b = {tool.name: tool for tool in asyncio.run(server_b.list_tools())}

    assert PROTOCOL == "multilingual-context-workflow-v2"
    assert set(tools_a) == set(TOOL_NAMES_A)
    assert set(tools_b) == set(TOOL_NAMES_B)
    assert set(tools_b) - set(tools_a) == {"loci_explore"}
    for name in TOOL_NAMES_A:
        assert tools_a[name].input_schema == tools_b[name].input_schema

    for name in ("graph_imports", "graph_references", "graph_calls"):
        properties = tools_a[name].input_schema["properties"]
        assert properties["offset"]["minimum"] == 0
        assert properties["offset"]["maximum"] == 10_000
        assert properties["limit"]["minimum"] == 0
        assert properties["limit"]["maximum"] == 32
    for name, fields in {
        "graph_anchors": ("seed_ids",),
        "graph_neighbors": ("seed_ids",),
        "graph_traverse_neighbors": ("seed_ids",),
        "graph_paths": ("source_ids", "target_ids"),
        "graph_retrieve": ("seed_ids",),
    }.items():
        for field in fields:
            property_schema = tools_a[name].input_schema["properties"][field]
            array_schema = property_schema if property_schema.get("type") == "array" else property_schema["anyOf"][0]
            assert array_schema["maxItems"] == 5
            assert "uniqueItems" not in array_schema


def test_v2_normalization_keeps_v1_null_and_duplicate_semantics_at_boundaries() -> None:
    assert normalize_arguments("graph_imports", {"offset": 0, "limit": 32}) == {
        "status": "all", "offset": 0, "limit": 32,
    }
    assert normalize_arguments("graph_references", {"offset": 10_000, "limit": 0}) == {
        "status": "all", "offset": 10_000, "limit": 0,
    }
    assert normalize_arguments("graph_anchors", {"question": "q", "seed_ids": ["a"] * 5}) == {
        "question": "q", "seed_ids": ["a"] * 5,
    }
    assert normalize_arguments("graph_retrieve", {"question": "q", "seed_ids": None}) == {"question": "q"}
    assert normalize_arguments("graph_paths", {"source_ids": [], "target_ids": []}) == {
        "source_ids": [], "target_ids": [],
    }

    invalid = [
        ("graph_imports", {"offset": -1}),
        ("graph_imports", {"offset": 10_001}),
        ("graph_imports", {"limit": -1}),
        ("graph_imports", {"limit": 33}),
        ("graph_imports", {"limit": True}),
        ("graph_imports", {"limit": None}),
        ("graph_neighbors", {"seed_ids": None}),
        ("graph_neighbors", {"seed_ids": ["id"] * 6}),
        ("graph_paths", {"source_ids": ["id"] * 6, "target_ids": []}),
        ("graph_paths", {"source_ids": [], "target_ids": ["id"] * 6}),
    ]
    for tool, raw in invalid:
        with pytest.raises((TypeError, ValueError)):
            normalize_arguments(tool, raw)


def test_loopback_mcp_rejects_invalid_boundaries_before_fake_dispatch() -> None:
    adapter = _BoundedFakeAdapter("A")
    server = create_server(cast(MultilingualAdapter, adapter), "A")

    async def check() -> None:
        response = await server.call_tool("graph_calls", {"offset": 10_000, "limit": 32})
        assert response.structured_content == {
            "operation": "graph_calls",
            "arguments": {"status": "all", "offset": 10_000, "limit": 32},
        }
        for name, arguments in (
            ("graph_imports", {"limit": 33}),
            ("graph_references", {"offset": -1}),
            ("graph_neighbors", {"seed_ids": ["id"] * 6}),
        ):
            with pytest.raises(ToolError):
                await server.call_tool(name, arguments)

    asyncio.run(check())
    assert adapter.calls == [("graph_calls", {"status": "all", "offset": 10_000, "limit": 32})]


@pytest.mark.parametrize("arm", ["A", "B"])
def test_both_arms_deliver_exact_go_and_cargo_controls_through_v2_server(tmp_path: Path, arm: str) -> None:
    repo = tmp_path / "snapshot"
    files = _write_snapshot(repo)

    with _isolated_store(tmp_path / "cache"):
        service.index_repo(repo, incremental=False)
        adapter = _adapter(repo, files, arm)
        server = create_server(adapter, arm)
        for file_path, start_line, end_line in (
            ("go.mod", 2, 4),
            ("crates/widget/Cargo.toml", 2, 5),
        ):
            result = asyncio.run(server.call_tool("file", {
                "file_path": file_path, "start_line": start_line, "end_line": end_line,
            })).structured_content
            assert isinstance(result, dict)
            lines = files[file_path].decode("utf-8").splitlines(keepends=True)
            assert result["file"] == file_path
            assert result["content"] == "".join(lines[start_line - 1:end_line])
            assert result["start_line"] == start_line
            assert result["end_line"] == end_line
        with pytest.raises(ToolError):
            asyncio.run(server.call_tool("graph_imports", {"limit": 33}))
        assert not adapter.failures
        assert len(adapter.deliveries) == 2


def test_v2_main_stdio_preflight_binds_schema_boundaries_and_frozen_go_rust_controls(
    tmp_path: Path,
) -> None:
    """Exercise the actual constructor, v2 trace, and stdio protocol for both arms."""

    corpus, _controls = load_inputs()
    scenarios = (
        ("go_alias_generic_contract", "go_contracts", "go.mod"),
        ("rust_authored_trait_contract", "rust_contracts", "Cargo.toml"),
    )

    async def check() -> None:
        for case_id, snapshot, control_file in scenarios:
            repo = tmp_path / snapshot
            materialize_snapshot(corpus, snapshot, repo)
            service.index_repo(repo, incremental=False)
            index = service.get_store().load(repo)
            assert index is not None
            seed_ids = [symbol["id"] for symbol in index["symbols"][:5]]
            assert len(seed_ids) == 5
            expected = (repo / control_file).read_text(encoding="utf-8")
            for arm in ("A", "B"):
                trace_path = tmp_path / f"{snapshot}-{arm}-trace.json"
                run_file = tmp_path / f"{snapshot}-{arm}-run.json"
                run_file.write_text(json.dumps({
                    "repo": str(repo.resolve()),
                    "corpus_root": corpus["_root"],
                    "case_id": case_id,
                    "session_id": f"v2-stdio-{snapshot}-{arm}",
                    "arm": arm,
                    "repetition": 1,
                    "trace_path": str(trace_path),
                }), encoding="utf-8")
                async with Client(stdio_client(_server_params(run_file))) as session:
                    listed = {tool.name: tool for tool in (await session.list_tools()).tools}
                    assert ("loci_explore" in listed) is (arm == "B")
                    pagination = listed["graph_imports"].input_schema["properties"]
                    assert pagination["limit"]["maximum"] == 32
                    assert pagination["offset"]["minimum"] == 0

                    response = await session.call_tool("file", {"file_path": control_file})
                    assert not response.is_error, response.structured_content
                    assert response.structured_content["content"] == expected

                    record_boundary = await session.call_tool(
                        "graph_imports", {"offset": 10_000, "limit": 32}
                    )
                    assert not record_boundary.is_error, record_boundary.structured_content
                    assert "error" not in record_boundary.structured_content
                    anchor_boundary = await session.call_tool(
                        "graph_anchors", {"question": "frozen fixture anchors", "seed_ids": seed_ids}
                    )
                    assert not anchor_boundary.is_error, anchor_boundary.structured_content
                    assert "error" not in anchor_boundary.structured_content

                    invalid_pagination = await session.call_tool("graph_imports", {"limit": 33})
                    assert invalid_pagination.is_error
                    invalid_anchors = await session.call_tool("graph_neighbors", {"seed_ids": ["id"] * 6})
                    assert invalid_anchors.is_error

                trace = json.loads(trace_path.read_text(encoding="utf-8"))
                assert trace["protocol"] == PROTOCOL
                assert trace["attempts"] == 3
                assert [entry["operation"] for entry in trace["deliveries"]] == [
                    "file", "graph_imports", "graph_anchors",
                ]
                assert trace["deliveries"][1]["arguments"] == {
                    "status": "all", "offset": 10_000, "limit": 32,
                }
                assert trace["deliveries"][2]["arguments"] == {
                    "question": "frozen fixture anchors", "seed_ids": seed_ids,
                }

    with _isolated_store(tmp_path / "store"):
        asyncio.run(check())
