from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace
from typing import Any

from jsonschema import Draft202012Validator
from mcp import Client, ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
import pytest
from mcp.server.mcpserver.exceptions import ToolError
from pydantic import ValidationError

from loci import mcp_server
from loci.mcp_output_models import LociReadOutput, LociRetrieveOutput


_HASH = "a" * 64


def _retrieve_payload() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "policy": "normal-graph-v1",
        "snapshot": _HASH,
        "status": "ok",
        "selection": {"mode": "inferred", "candidate_count": 1, "omitted_candidates": 0},
        "scope": {
            "source": "indexed_supported_source",
            "coverage": "complete",
            "matching": "symbol_metadata",
            "relationships": "known_static_relationships",
            "exhaustive": False,
        },
        "anchors": [{"node_id": "a", "score": 1.0, "matched_terms": ["a"], "match_scope": ["name"]}],
        "nodes": [
            {"id": "a", "name": "a", "kind": "function", "file": "sample.py"},
            {"id": "b", "name": "b", "kind": "function", "file": "sample.py"},
        ],
        "items": [{
            "node_id": "a", "role": "anchor", "depth": 0, "why": "best match",
            "source_ids": [1], "complete": True,
            "extent": {"file": "sample.py", "content_hash": _HASH, "start_byte": 0, "end_byte": 9},
            "source_ref": "ref-a",
        }],
        "ownership": [],
        "relationships": [{
            "id": 1,
            "edge": {
                "from": "a", "to": "b", "type": "calls", "directed": True,
                "namespace": "loci", "resolution": "exact",
                "evidence": {"file": "sample.py", "line": 1, "content_hash": _HASH},
            },
            "traversed": "forward", "source_ids": [1], "proof": "complete",
            "resolution_configuration": None,
        }],
        "sources": [{
            "id": 1, "file": "sample.py", "start_byte": 0, "end_byte": 9,
            "start_line": 1, "end_line": 1, "content_hash": _HASH,
            "content": "def a():\n", "source_ref": "ref-a",
        }],
        "omissions": [],
        "limits": {
            "max_hops": 2, "max_nodes": 64, "max_neighbors": 32, "max_items": 12,
            "max_anchors": 3, "max_explicit_anchors": 5, "max_owner_members": 3,
            "max_evidence_bytes": 8192, "max_output_bytes": 16384,
            "max_anchor_source_bytes": 1024, "max_related_source_bytes": 768,
            "max_lookup_bytes": 33554432, "max_lookup_files": 4096,
            "max_literal_matches": 256,
        },
        "usage": {
            "nodes_examined": 2, "eligible_edges_considered": 1, "edges_traversed": 1,
            "relationships_delivered": 1, "lookup_bytes": 0, "lookup_files": 0,
            "evidence_bytes": 9, "output_bytes": 1000, "estimated_tokens": 250,
            "token_estimate_method": "utf8_bytes_div_4", "output_encoding": "mcp_result_json_utf8",
        },
    }


def _read_payload() -> dict[str, Any]:
    payload = _retrieve_payload()
    return {
        "schema_version": 1,
        "status": "ok",
        "source": payload["sources"][0],
        "complete": True,
        "next_source_ref": None,
        "usage": {
            "evidence_bytes": 9,
            "output_bytes": 200,
            "output_encoding": "mcp_result_json_utf8",
        },
    }


def _contract_validator(definition: str) -> Draft202012Validator:
    schema_path = Path(__file__).parents[1] / ".scratch" / "deterministic-graph-retrieval" / "contract.schema.json"
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    schema["$ref"] = f"#/$defs/{definition}"
    return Draft202012Validator(schema)


def test_normal_catalog_only_exposes_frozen_operations() -> None:
    tools = asyncio.run(mcp_server.create_server("normal").list_tools())
    assert {tool.name for tool in tools} == {"loci_retrieve", "loci_read"}


def test_diagnostic_catalog_preserves_existing_operations() -> None:
    tools = asyncio.run(mcp_server.create_server("diagnostic").list_tools())
    assert len(tools) == 21
    assert "loci_explore" in {tool.name for tool in tools}
    assert "loci_retrieve" not in {tool.name for tool in tools}


def test_normal_operations_refresh_and_validate_typed_output(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[str, tuple[Any, ...], dict[str, Any]]] = []

    def retrieve(*args: Any, **kwargs: Any) -> dict[str, Any]:
        calls.append(("retrieve", args, kwargs))
        return _retrieve_payload()

    def read(*args: Any, **kwargs: Any) -> dict[str, Any]:
        calls.append(("read", args, kwargs))
        return _read_payload()

    fake_service = SimpleNamespace(retrieve=retrieve, read=read)
    monkeypatch.setattr(mcp_server, "_service_module", fake_service)
    server = mcp_server.create_server("normal")

    retrieved = asyncio.run(server.call_tool(
        "loci_retrieve", {"repo": "/repo", "query": "a", "seed_ids": ["a"]},
    ))
    read_result = asyncio.run(server.call_tool(
        "loci_read", {"repo": "/repo", "source_ref": "ref-a"},
    ))

    assert retrieved.is_error is False
    assert read_result.is_error is False
    LociRetrieveOutput.model_validate(retrieved.structured_content)
    LociReadOutput.model_validate(read_result.structured_content)
    _contract_validator("retrieve_response").validate(retrieved.structured_content)
    _contract_validator("read_response").validate(read_result.structured_content)
    assert calls == [
        ("retrieve", ("/repo",), {"query": "a", "seed_ids": ["a"], "ensure_fresh": True}),
        ("read", ("/repo", "ref-a"), {"ensure_fresh": True}),
    ]


def test_normal_retrieve_rejects_empty_extra_and_over_utf8_byte_inputs() -> None:
    server = mcp_server.create_server("normal")
    with pytest.raises(ToolError):
        asyncio.run(server.call_tool("loci_retrieve", {"repo": "/repo"}))
    with pytest.raises(ToolError):
        asyncio.run(server.call_tool(
            "loci_retrieve", {"repo": "/repo", "query": "€" * 1366},
        ))
    with pytest.raises(ToolError):
        asyncio.run(server.call_tool(
            "loci_retrieve", {"repo": "/repo", "query": "a", "direction": "incoming"},
        ))


def test_normal_input_schema_advertises_fixed_surface_and_utf8_limit() -> None:
    tools = asyncio.run(mcp_server.create_server("normal").list_tools())
    retrieve = next(tool for tool in tools if tool.name == "loci_retrieve")
    assert set(retrieve.input_schema["properties"]) == {"repo", "query", "seed_ids"}
    assert retrieve.input_schema["properties"]["query"]["x-maxUtf8Bytes"] == 4096
    assert retrieve.input_schema["properties"]["seed_ids"]["anyOf"][0]["maxItems"] == 5
    assert retrieve.input_schema["properties"]["seed_ids"]["uniqueItems"] is True


@pytest.mark.parametrize("control", ["graph", "graph_enrichment"])
def test_normal_retrieve_rejects_agent_selected_graph_control(control: str) -> None:
    server = mcp_server.create_server("normal")
    with pytest.raises(ToolError, match="unsupported arguments"):
        asyncio.run(server.call_tool(
            "loci_retrieve", {"repo": "/repo", "query": "a", control: False},
        ))


def test_normal_output_rejects_execution_state_in_relationship_scope() -> None:
    payload = _retrieve_payload()
    payload["scope"]["relationships"] = "disabled"
    with pytest.raises(ValidationError):
        LociRetrieveOutput.model_validate(payload)


def test_normal_output_rejects_unlinked_or_unproven_relationships() -> None:
    payload = _retrieve_payload()
    payload["relationships"][0]["source_ids"] = [99]
    with pytest.raises(ValidationError):
        LociRetrieveOutput.model_validate(payload)


def test_normal_read_allows_an_empty_exact_extent() -> None:
    payload = _read_payload()
    payload["source"].update({"content": "", "start_byte": 0, "end_byte": 0})
    payload["usage"]["evidence_bytes"] = 0
    LociReadOutput.model_validate(payload)


def test_normal_output_rejects_missing_node_name_corrupt_source_and_invalid_source_ids() -> None:
    missing_name = _retrieve_payload()
    del missing_name["nodes"][0]["name"]
    with pytest.raises(ValidationError):
        LociRetrieveOutput.model_validate(missing_name)

    corrupt_source = _retrieve_payload()
    corrupt_source["sources"][0]["content"] = "corrupt"
    with pytest.raises(ValidationError):
        LociRetrieveOutput.model_validate(corrupt_source)

    invalid_source_id = _retrieve_payload()
    invalid_source_id["relationships"][0]["source_ids"] = [0]
    with pytest.raises(ValidationError):
        LociRetrieveOutput.model_validate(invalid_source_id)


def test_normal_read_rejects_inconsistent_paging_and_byte_accounting() -> None:
    incomplete_marked_complete = _read_payload()
    incomplete_marked_complete["next_source_ref"] = "next"
    with pytest.raises(ValidationError):
        LociReadOutput.model_validate(incomplete_marked_complete)

    wrong_evidence_bytes = _read_payload()
    wrong_evidence_bytes["usage"]["evidence_bytes"] = 8
    with pytest.raises(ValidationError):
        LociReadOutput.model_validate(wrong_evidence_bytes)

    oversized_result = _read_payload()
    oversized_result["usage"]["output_bytes"] = 16_385
    with pytest.raises(ValidationError):
        LociReadOutput.model_validate(oversized_result)


def test_invalid_surface_fails_before_stdio_startup(tmp_path: Path) -> None:
    env = os.environ.copy()
    env.update({
        "LOCI_MCP_SURFACE": "unsupported",
        "PYTHONPATH": str(Path.cwd() / "src"),
    })
    result = subprocess.run(
        [sys.executable, "-m", "loci.mcp_server"],
        env=env,
        capture_output=True,
        text=True,
        timeout=5,
    )
    assert result.returncode != 0
    assert "LOCI_MCP_SURFACE must be either" in result.stderr


def test_normal_stdio_retrieves_and_reads_returned_source_ref(tmp_path: Path) -> None:
    repo = tmp_path / "fixture"
    repo.mkdir()
    (repo / "callee.py").write_text("def callee() -> int:\n    return 1\n", encoding="utf-8")
    (repo / "caller.py").write_text(
        "from callee import callee\n\ndef caller() -> int:\n    return callee()\n",
        encoding="utf-8",
    )
    cache_dir = tmp_path / "cache"

    async def check() -> None:
        env = os.environ.copy()
        env.update({
            "LOCI_BASE_DIR": str(cache_dir),
            "LOCI_STORE_NAMESPACE": "normal-mcp-test",
            "LOCI_MCP_SURFACE": "normal",
            "PYTHONPATH": str(Path.cwd() / "src"),
        })
        params = StdioServerParameters(
            command=sys.executable,
            args=["-m", "loci.mcp_server"],
            env=env,
            cwd=Path.cwd(),
        )
        async with Client(stdio_client(params)) as session:
            tools = await session.list_tools()
            assert {tool.name for tool in tools.tools} == {"loci_retrieve", "loci_read"}
            retrieved = await session.call_tool(
                "loci_retrieve", arguments={"repo": str(repo), "query": "caller"},
            )
            assert retrieved.is_error is False
            payload = retrieved.structured_content
            assert isinstance(payload, dict)
            LociRetrieveOutput.model_validate(payload)
            assert payload["sources"]
            assert payload["scope"]["relationships"] == "known_static_relationships"
            assert payload["usage"]["edges_traversed"] > 0
            assert payload["relationships"]
            reference = payload["sources"][0]["source_ref"]
            assert reference.startswith("sr1_") and len(reference) == 30
            read = await session.call_tool(
                "loci_read",
                arguments={"repo": str(repo), "source_ref": reference},
            )
            assert read.is_error is False
            assert isinstance(read.structured_content, dict)
            LociReadOutput.model_validate(read.structured_content)
            original_source = read.structured_content["source"]

        # A fresh server resolves the same reference from its configured store.
        async with Client(stdio_client(params)) as restarted:
            read = await restarted.call_tool(
                "loci_read", arguments={"repo": str(repo), "source_ref": reference},
            )
            assert read.is_error is False
            assert read.structured_content["source"] == original_source

    asyncio.run(check())
