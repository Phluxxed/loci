from __future__ import annotations

import asyncio
import copy
import os
import sys
from pathlib import Path
from typing import Any

import pytest
from mcp import Client, StdioServerParameters
from mcp.client.stdio import stdio_client
from pydantic import ValidationError

from loci.mcp_output_models import (
    LociGetOutput,
    LociGraphHealthOutput,
    LociGraphReferencesOutput,
    LociIndexOutput,
)


def test_type_relationships_are_available_through_the_mcp_subprocess(
    tmp_path: Path,
) -> None:
    result = asyncio.run(_exercise_type_relationship_server(tmp_path))

    assert result["index"]["graph_type_relations_indexed"] > 0
    assert result["index"]["graph_type_relations_unresolved"] > 0

    schema = result["references_schema"]
    assert schema["required"] == ["repo"]
    assert set(schema["properties"]) == {
        "repo",
        "file",
        "status",
        "offset",
        "limit",
        "family",
    }
    assert schema["properties"]["family"]["default"] == "symbol"

    symbol = result["symbol"]
    assert set(symbol) == {
        "schema_version",
        "repo",
        "file",
        "status",
        "items",
        "counts",
        "pagination",
    }
    LociGraphReferencesOutput.model_validate(symbol)

    type_page = result["type_page"]
    assert type_page["family"] == "type"
    assert type_page["pagination"]["next_offset"] is not None
    assert type_page["counts"]["total"] > type_page["counts"]["returned"]
    assert type_page["items"]
    LociGraphReferencesOutput.model_validate(type_page)
    with pytest.raises(ValidationError):
        LociGraphReferencesOutput.model_validate({**type_page, "unexpected": True})
    malformed_type_page = copy.deepcopy(type_page)
    malformed_type_page["items"][0]["raw"]["start_byte"] = True
    with pytest.raises(ValidationError):
        LociGraphReferencesOutput.model_validate(malformed_type_page)

    unresolved = result["unresolved"]
    assert unresolved["family"] == "type"
    assert unresolved["items"]
    assert all(item["status"] == "unresolved" for item in unresolved["items"])
    assert {
        item["unresolved_reason"] for item in unresolved["items"]
    } & {"type_parameter", "binding_ambiguous", "binding_not_found"}
    LociGraphReferencesOutput.model_validate(unresolved)

    health = result["health"]
    LociGraphHealthOutput.model_validate(health)
    assert health["counts"]["graph_type_relations_indexed"] > 0
    assert isinstance(health["counts"]["graph_type_relations_resolved_by_basis"], dict)
    assert isinstance(health["counts"]["graph_type_relations_unresolved_by_reason"], dict)

    context = result["context"]
    LociGetOutput.model_validate(context)
    assert context["type_context"]["scope"] in {
        "existing_imported_type_references",
        "declared_type_relations",
    }
    assert any(
        support["kind"] == "type_site"
        for reference in context["type_context"]["references"]
        for support in reference["support"]
    )

    traversal = result["traversal"]
    assert traversal["results"][0]["neighbors"][0]["node"]["id"] == (
        "types.ts::Base#interface"
    )
    assert traversal["results"][0]["neighbors"][0]["edge"]["type"] == "extends"

    path = result["path"]["paths"][0]
    assert [node["id"] for node in path["nodes"]] == [
        "types.ts::Derived#interface",
        "types.ts::Base#interface",
    ]
    assert path["steps"][0]["evidence_span"]["file"] == "types.ts"


async def _exercise_type_relationship_server(tmp_path: Path) -> dict[str, Any]:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "types.ts").write_text(
        "export interface Base { value: string; }\n"
        "export interface Payload { id: string; }\n"
        "export interface Derived extends Base { payload: Payload; }\n"
        "export type Alias = Payload;\n",
        encoding="utf-8",
    )
    (repo / "left.ts").write_text(
        "export interface SharedLeft { left: string; }\n",
        encoding="utf-8",
    )
    (repo / "right.ts").write_text(
        "export interface SharedRight { right: string; }\n",
        encoding="utf-8",
    )
    (repo / "consumer.ts").write_text(
        'import type { Payload as Imported } from "./types.js";\n'
        "export function process(value: Imported): Imported { return value; }\n"
        "interface Local extends Derived {}\n"
        "function generic<T extends Payload>(x: T): T { return x; }\n"
        "function missing(x: Missing): Missing { return x; }\n",
        encoding="utf-8",
    )
    (repo / "ambiguous.ts").write_text(
        'import type { SharedLeft as Shared } from "./left.js";\n'
        'import type { SharedRight as Shared } from "./right.js";\n'
        "export function ambiguous(value: Shared): Shared { return value; }\n",
        encoding="utf-8",
    )

    env = os.environ.copy()
    env["LOCI_BASE_DIR"] = str(tmp_path / "store")
    env["LOCI_STORE_NAMESPACE"] = "type-relations-mcp"
    source_root = str(Path.cwd() / "src")
    env["PYTHONPATH"] = os.pathsep.join(
        part for part in (source_root, env.get("PYTHONPATH")) if part
    )
    server_params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "loci.mcp_server"],
        env=env,
        cwd=Path.cwd(),
    )

    async with Client(stdio_client(server_params)) as session:
        indexed = await session.call_tool(
            "loci_index",
            arguments={"repo": str(repo), "incremental": False},
        )
        assert indexed.is_error is False
        index = indexed.structured_content
        assert index is not None
        LociIndexOutput.model_validate(index)

        tools = await session.list_tools()
        references_schema = next(
            tool.input_schema
            for tool in tools.tools
            if tool.name == "loci_graph_references"
        )

        symbol_response = await session.call_tool(
            "loci_graph_references",
            arguments={"repo": str(repo), "limit": 2},
        )
        assert symbol_response.is_error is False
        symbol = symbol_response.structured_content
        assert symbol is not None

        type_response = await session.call_tool(
            "loci_graph_references",
            arguments={
                "repo": str(repo),
                "family": "type",
                "limit": 2,
            },
        )
        assert type_response.is_error is False
        type_page = type_response.structured_content
        assert type_page is not None

        unresolved_response = await session.call_tool(
            "loci_graph_references",
            arguments={
                "repo": str(repo),
                "family": "type",
                "status": "unresolved",
            },
        )
        assert unresolved_response.is_error is False
        unresolved = unresolved_response.structured_content
        assert unresolved is not None

        health_response = await session.call_tool(
            "loci_graph_health",
            arguments={"repo": str(repo)},
        )
        assert health_response.is_error is False
        health = health_response.structured_content
        assert health is not None

        search_response = await session.call_tool(
            "loci_search",
            arguments={"repo": str(repo), "query": "process"},
        )
        assert search_response.is_error is False
        search = search_response.structured_content
        assert search is not None
        process_id = "consumer.ts::process#function"
        assert any(symbol["id"] == process_id for symbol in search["symbols"])

        context_response = await session.call_tool(
            "loci_get",
            arguments={
                "repo": str(repo),
                "symbol_ids": [process_id],
                "selected_from_search_id": search["search_id"],
                "include_type_context": True,
            },
        )
        assert context_response.is_error is False
        context = context_response.structured_content
        assert context is not None

        traversal_response = await session.call_tool(
            "loci_graph_traverse_neighbors",
            arguments={
                "repo": str(repo),
                "seed_ids": ["types.ts::Derived#interface"],
                "namespaces": ["loci"],
                "edge_types": ["extends"],
            },
        )
        assert traversal_response.is_error is False
        traversal = traversal_response.structured_content
        assert traversal is not None

        path_response = await session.call_tool(
            "loci_graph_paths",
            arguments={
                "repo": str(repo),
                "source_ids": ["types.ts::Derived#interface"],
                "target_ids": ["types.ts::Base#interface"],
                "namespaces": ["loci"],
                "edge_types": ["extends"],
            },
        )
        assert path_response.is_error is False
        path = path_response.structured_content
        assert path is not None

    return {
        "index": index,
        "references_schema": references_schema,
        "symbol": symbol,
        "type_page": type_page,
        "unresolved": unresolved,
        "health": health,
        "context": context,
        "traversal": traversal,
        "path": path,
    }
