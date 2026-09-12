from __future__ import annotations

import asyncio
import json

from mcp import Client
from mcp.client.stdio import stdio_client

from loci.mcp_output_models import LociExploreOutput, LociGraphReferencesOutput
from tests.test_exploration_mcp import _server_params


def test_python_context_crosses_the_actual_mcp_boundary(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "schema.py").write_text("class Payload:\n    request_id: str\n")
    (repo / "barrel.py").write_text("from schema import Payload as Exported\n")
    (repo / "consumer.py").write_text(
        "from typing import TypeAlias\nfrom barrel import Exported as P\n"
        "Alias: TypeAlias = P\ndef decode(value: Alias) -> list[P]:\n    return [value]\n"
    )

    async def check():
        async with Client(stdio_client(_server_params(repo, tmp_path / "cache"))) as session:
            response = await session.call_tool("loci_explore", {
                "repo": str(repo), "intent": "type_dependencies",
                "seed_ids": ["consumer.py::decode#function"],
            })
            assert not response.is_error
            result = response.structured_content
            LociExploreOutput.model_validate(result)
            assert {item["name"] for item in result["items"]} == {"decode", "Alias", "Payload"}
            assert "barrel.py" in {source["file"] for source in result["sources"]}
            assert result["usage"]["output_bytes"] == len(json.dumps(
                {"content": [], "structuredContent": result, "isError": False},
                separators=(",", ":"), ensure_ascii=False,
            ).encode())
            diagnostics = await session.call_tool("loci_graph_references", {
                "repo": str(repo), "family": "type",
            })
            assert not diagnostics.is_error
            LociGraphReferencesOutput.model_validate(diagnostics.structured_content)
            assert '"language": "python"' in json.dumps(diagnostics.structured_content)

    asyncio.run(check())
