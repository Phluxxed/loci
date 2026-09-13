from __future__ import annotations

import asyncio
import json

from mcp import Client
from mcp.client.stdio import stdio_client

from loci.mcp_output_models import LociExploreOutput, LociGraphReferencesOutput
from tests.test_exploration_mcp import _server_params


def test_javascript_dependencies_cross_the_actual_mcp_boundary(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "schema.js").write_text(
        "export const CONFIG = 3;\nexport const helper = x => x + 1;\n"
        "export class Base {}\n"
    )
    (repo / "barrel.js").write_text('export { CONFIG, helper, Base } from "./schema.js";\n')
    (repo / "consumer.js").write_text(
        'import { CONFIG, helper, Base } from "./barrel.js";\n'
        "export function run() { return helper(CONFIG); }\n"
        "export class Child extends Base {}\n"
    )

    async def check():
        async with Client(stdio_client(_server_params(repo, tmp_path / "cache"))) as session:
            for seed, names in [("run#function", {"run", "CONFIG", "helper"}),
                                ("Child#class", {"Child", "Base"})]:
                response = await session.call_tool("loci_explore", {
                    "repo": str(repo), "intent": "dependencies",
                    "seed_ids": ["consumer.js::" + seed],
                })
                assert not response.is_error
                result = response.structured_content
                LociExploreOutput.model_validate(result)
                assert {item["name"] for item in result["items"]} == names
                assert result["scope"]["relationships"] == "authored_dependencies"
                assert "barrel.js" in {source["file"] for source in result["sources"]}
                assert result["usage"]["output_bytes"] == len(json.dumps(
                    {"content": [], "structuredContent": result, "isError": False},
                    separators=(",", ":"), ensure_ascii=False,
                ).encode())
            diagnostics = await session.call_tool("loci_graph_references", {
                "repo": str(repo), "family": "type",
            })
            assert not diagnostics.is_error
            data = diagnostics.structured_content
            LociGraphReferencesOutput.model_validate(data)
            assert len(data["items"]) == 1
            raw = data["items"][0]["raw"]
            assert (raw["language"], raw["relation"], raw["lookup_space"]) == (
                "javascript", "extends", "value",
            )

    asyncio.run(check())
