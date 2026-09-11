from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

import pytest
from mcp import Client, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.types import CallToolResult
from pydantic import ValidationError

from loci.mcp_output_models import LociExploreOutput, LociGetOutput


def _fixture_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "model.ts").write_text(
        "interface Customer { id: string; }\n"
        "interface Audit { message: string; }\n"
        "interface Order { customer: Customer; audit: Audit; }\n"
        "function run(order: Order): void { return; }\n"
        "function caller(order: Order): void { run(order); }\n",
        encoding="utf-8",
    )
    return repo


def _server_params(repo: Path, cache: Path) -> StdioServerParameters:
    env = os.environ.copy()
    env["LOCI_BASE_DIR"] = str(cache)
    env["LOCI_STORE_NAMESPACE"] = "test"
    env["PYTHONPATH"] = str(Path.cwd() / "src")
    return StdioServerParameters(
        command=sys.executable,
        args=["-m", "loci.mcp_server"],
        env=env,
        cwd=Path.cwd(),
    )


def test_loci_explore_is_discoverable_with_closed_response_schema(tmp_path: Path) -> None:
    repo = _fixture_repo(tmp_path)
    cache = tmp_path / "cache"

    async def check() -> None:
        async with Client(stdio_client(_server_params(repo, cache))) as session:
            tools = await session.list_tools()
            tool = next(tool for tool in tools.tools if tool.name == "loci_explore")
            assert set(tool.input_schema["properties"]) == {
                "repo",
                "intent",
                "query",
                "seed_ids",
                "max_hops",
                "max_output_bytes",
                "max_evidence_bytes",
                "resolutions",
            }
            assert tool.input_schema["required"] == ["repo", "intent"]
            assert "ensure_fresh" not in tool.input_schema["properties"]
            assert tool.output_schema["type"] == "object"
            success = tool.output_schema["$defs"]["LociExploreSuccess"]
            assert success["additionalProperties"] is False
            assert set(success["properties"]) == {
                "schema_version",
                "intent",
                "status",
                "selection",
                "scope",
                "items",
                "relationships",
                "sources",
                "omissions",
                "limits",
                "usage",
            }

    asyncio.run(check())


def test_loci_explore_locate_types_impact_and_exact_get(tmp_path: Path) -> None:
    repo = _fixture_repo(tmp_path)
    cache = tmp_path / "cache"

    async def check() -> None:
        async with Client(stdio_client(_server_params(repo, cache))) as session:
            locate = await session.call_tool(
                "loci_explore",
                {"repo": str(repo), "intent": "locate", "seed_ids": ["model.ts::run#function"]},
            )
            assert not locate.is_error
            assert [item["name"] for item in locate.structured_content["items"]] == ["run"]
            LociExploreOutput.model_validate(locate.structured_content)

            typed = await session.call_tool(
                "loci_explore",
                {
                    "repo": str(repo),
                    "intent": "type_dependencies",
                    "query": "run customer",
                    "seed_ids": ["model.ts::run#function"],
                },
            )
            assert not typed.is_error
            typed_names = [item["name"] for item in typed.structured_content["items"]]
            assert typed_names[:2] == ["run", "Order"]
            assert "Customer" in typed_names
            assert "Audit" not in typed_names
            LociExploreOutput.model_validate(typed.structured_content)

            impact = await session.call_tool(
                "loci_explore",
                {
                    "repo": str(repo),
                    "intent": "impact",
                    "seed_ids": ["model.ts::run#function"],
                },
            )
            assert not impact.is_error
            assert [item["name"] for item in impact.structured_content["items"]] == [
                "run",
                "caller",
            ]
            assert impact.structured_content["relationships"][0]["traversed"] == "reverse"
            LociExploreOutput.model_validate(impact.structured_content)

            exact = await session.call_tool(
                "loci_get",
                {"repo": str(repo), "symbol_ids": ["model.ts::run#function"]},
            )
            assert not exact.is_error
            assert set(exact.structured_content) == {"symbols"}
            LociGetOutput.model_validate(exact.structured_content)

    asyncio.run(check())


def test_loci_explore_bad_inputs_are_structured_service_errors(tmp_path: Path) -> None:
    repo = _fixture_repo(tmp_path)
    cache = tmp_path / "cache"

    async def check() -> None:
        async with Client(stdio_client(_server_params(repo, cache))) as session:
            invalid_intent = await session.call_tool(
                "loci_explore",
                {
                    "repo": str(repo),
                    "intent": "execute",
                    "seed_ids": ["model.ts::run#function"],
                },
            )
            assert invalid_intent.is_error
            assert invalid_intent.structured_content["error"]["code"] == "INVALID_INPUT"
            assert invalid_intent.structured_content["error"]["details"] == {
                "supported_intents": ["locate", "type_dependencies", "impact"],
                "fallback_intent": "locate",
            }

            invalid_limit = await session.call_tool(
                "loci_explore",
                {
                    "repo": str(repo),
                    "intent": "locate",
                    "seed_ids": ["model.ts::run#function"],
                    "max_output_bytes": 2047,
                },
            )
            assert invalid_limit.is_error
            assert invalid_limit.structured_content["error"]["code"] == "INVALID_INPUT"

    asyncio.run(check())


def test_loci_explore_unicode_clip_matches_actual_call_result_bytes(tmp_path: Path) -> None:
    repo = tmp_path / "unicode-repo"
    repo.mkdir()
    (repo / "café.ts").write_text(
        "function café(): void {\n" + "// 世界 π\n" * 1000 + "}\n",
        encoding="utf-8",
    )
    cache = tmp_path / "cache"

    async def check() -> None:
        async with Client(stdio_client(_server_params(repo, cache))) as session:
            result = await session.call_tool(
                "loci_explore",
                {
                    "repo": str(repo),
                    "intent": "locate",
                    "seed_ids": ["café.ts::café#function"],
                    "max_output_bytes": 2048,
                },
            )
            assert not result.is_error
            payload = result.structured_content
            assert payload["items"][0]["complete"] is False
            assert {item["reason"] for item in payload["omissions"]} == {"source_clipped"}
            core_result = CallToolResult(
                content=result.content,
                structured_content=result.structured_content,
                is_error=result.is_error,
            )
            encoded = core_result.model_dump_json(
                by_alias=True, exclude_unset=True
            ).encode("utf-8")
            assert len(encoded) == payload["usage"]["output_bytes"]
            assert len(encoded) <= 2048
            LociExploreOutput.model_validate(payload)

    asyncio.run(check())


def test_exploration_models_reject_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        LociExploreOutput.model_validate(
            {
                "schema_version": 1,
                "intent": "locate",
                "status": "empty",
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
                "limits": {
                    "max_hops": 0,
                    "max_nodes": 64,
                    "max_items": 12,
                    "max_neighbors": 32,
                    "max_output_bytes": 2048,
                    "max_evidence_bytes": 0,
                },
                "usage": {
                    "nodes_examined": 0,
                    "evidence_bytes": 0,
                    "output_bytes": 800,
                    "estimated_tokens": 200,
                    "token_estimate_method": "utf8_bytes_div_4",
                    "output_encoding": "mcp_result_json_utf8",
                },
                "extra": True,
            }
        )
