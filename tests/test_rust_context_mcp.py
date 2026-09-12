"""Rust context acceptance through the actual stdio MCP server."""
from __future__ import annotations

import asyncio
import hashlib
from pathlib import Path

from mcp import Client
from mcp.client.stdio import stdio_client
from mcp.types import CallToolResult

from benchmarks.typescript_context_corpus import load_corpus, materialize_snapshot
from loci.mcp_output_models import LociExploreOutput, LociGraphReferencesOutput
from tests.test_exploration_mcp import _server_params
from tests.test_python_context_delivery import CORPUS_ROOT


def _snapshot(tmp_path: Path, corpus: dict, name: str) -> Path:
    repo = tmp_path / name
    materialize_snapshot(corpus, name, repo)
    return repo


def _assert_wire_budget(response, payload: dict, output_limit: int) -> None:
    encoded = CallToolResult(
        content=response.content,
        structured_content=payload,
        is_error=response.is_error,
    ).model_dump_json(by_alias=True, exclude_unset=True).encode("utf-8")
    assert len(encoded) == payload["usage"]["output_bytes"]
    assert len(encoded) <= output_limit


def _assert_exact_sources(repo: Path, payload: dict) -> None:
    for source in payload["sources"]:
        data = (repo / source["file"]).read_bytes()
        span = data[source["start_byte"]:source["end_byte"]]
        assert span.decode("utf-8") == source["content"]
        assert hashlib.sha256(data).hexdigest() == source["content_hash"]


def test_rust_context_crosses_the_actual_mcp_boundary(tmp_path: Path) -> None:
    corpus = load_corpus(CORPUS_ROOT)
    contracts = _snapshot(tmp_path, corpus, "rust_contracts")
    workspace = _snapshot(tmp_path, corpus, "rust_workspace")

    async def check() -> None:
        async with Client(stdio_client(_server_params(contracts, tmp_path / "cache"))) as session:
            complete_response = await session.call_tool(
                "loci_explore",
                {
                    "repo": str(contracts),
                    "intent": "type_dependencies",
                    "seed_ids": ["src/lib.rs::build#function", "src/lib.rs::Receipt#struct"],
                    "max_evidence_bytes": 8192,
                    "max_output_bytes": 16384,
                },
            )
            assert not complete_response.is_error
            complete = complete_response.structured_content
            LociExploreOutput.model_validate(complete)
            assert {
                "src/lib.rs::build#function",
                "src/lib.rs::UserId#type",
                "src/lib.rs::Format#trait",
                "src/lib.rs::Render#trait",
                "src/lib.rs::Receipt#struct",
                "src/lib.rs::Envelope#struct",
            } <= {item["id"] for item in complete["items"]}
            assert len([item for item in complete["items"] if item["kind"] == "impl"]) == 2
            assert complete["limits"]["max_evidence_bytes"] == 8192
            assert complete["limits"]["max_output_bytes"] == 16384
            assert complete["usage"]["evidence_bytes"] <= 8192
            assert {source["file"] for source in complete["sources"]} >= {
                "src/lib.rs", "Cargo.toml",
            }
            assert all(
                relation["resolution_configuration"] == "unconditional"
                for relation in complete["relationships"]
            )
            _assert_exact_sources(contracts, complete)
            _assert_wire_budget(complete_response, complete, 16384)

            diagnostics_response = await session.call_tool(
                "loci_graph_references",
                {
                    "repo": str(contracts),
                    "file": "src/lib.rs",
                    "family": "type",
                    "status": "resolved",
                },
            )
            assert not diagnostics_response.is_error
            diagnostics = diagnostics_response.structured_content
            LociGraphReferencesOutput.model_validate(diagnostics)
            assert {
                item["raw"]["relation"] for item in diagnostics["items"]
            } >= {"uses_type", "supertrait", "impl_trait", "impl_self_type"}
            assert all(item["raw"]["language"] == "rust" for item in diagnostics["items"])

            reduced_response = await session.call_tool(
                "loci_explore",
                {
                    "repo": str(contracts),
                    "intent": "type_dependencies",
                    "seed_ids": ["src/lib.rs::build#function"],
                    "max_evidence_bytes": 4096,
                    "max_output_bytes": 8192,
                },
            )
            assert not reduced_response.is_error
            reduced = reduced_response.structured_content
            LociExploreOutput.model_validate(reduced)
            assert reduced["usage"]["evidence_bytes"] <= 4096
            _assert_wire_budget(reduced_response, reduced, 8192)

            zero_response = await session.call_tool(
                "loci_explore",
                {
                    "repo": str(contracts),
                    "intent": "type_dependencies",
                    "seed_ids": ["src/lib.rs::build#function"],
                    "max_evidence_bytes": 0,
                    "max_output_bytes": 2048,
                },
            )
            assert not zero_response.is_error
            zero = zero_response.structured_content
            LociExploreOutput.model_validate(zero)
            assert zero["status"] == "empty"
            assert not zero["items"] and not zero["relationships"] and not zero["sources"]
            assert zero["usage"]["evidence_bytes"] == 0
            _assert_wire_budget(zero_response, zero, 2048)

        async with Client(stdio_client(_server_params(workspace, tmp_path / "workspace-cache"))) as session:
            response = await session.call_tool(
                "loci_explore",
                {
                    "repo": str(workspace),
                    "intent": "type_dependencies",
                    "seed_ids": ["app/src/lib.rs::use_it#function"],
                    "max_evidence_bytes": 8192,
                    "max_output_bytes": 16384,
                },
            )
            assert not response.is_error
            payload = response.structured_content
            LociExploreOutput.model_validate(payload)
            assert {
                relation["resolution_configuration"]
                for relation in payload["relationships"]
            } == {"declared_possible"}
            assert {source["file"] for source in payload["sources"]} >= {
                "app/src/lib.rs", "core/src/lib.rs", "core/src/api.rs",
                "Cargo.toml", "app/Cargo.toml", "core/Cargo.toml",
            }
            _assert_exact_sources(workspace, payload)
            _assert_wire_budget(response, payload, 16384)

    asyncio.run(check())
