import asyncio
from pathlib import Path

import pytest
from mcp.types import CallToolResult
from pydantic import ValidationError

from loci.mcp_output_models import (
    LociFileOutput,
    LociGetOutput,
    LociGraphAnchorsOutput,
    LociGraphCallsOutput,
    LociGraphHealthOutput,
    LociGraphImportsOutput,
    LociGraphNeighborsOutput,
    LociGraphPathsOutput,
    LociGraphReferencesOutput,
    LociGraphRetrieveOutput,
    LociGraphTraverseNeighborsOutput,
    LociGrepOutput,
    LociIndexOutput,
    LociListOutput,
    LociOutlineOutput,
    LociSearchOutput,
    LociAnalyzeOutput,
    LociStatsOutput,
    LociStoreHealthOutput,
    LociVerifyOutput,
)
from loci.mcp_server import create_server


EXPECTED_LOCI_TOOLS = {
    "loci_analyze",
    "loci_file",
    "loci_get",
    "loci_graph_anchors",
    "loci_graph_calls",
    "loci_graph_health",
    "loci_graph_imports",
    "loci_graph_neighbors",
    "loci_graph_paths",
    "loci_graph_references",
    "loci_graph_retrieve",
    "loci_graph_traverse_neighbors",
    "loci_grep",
    "loci_index",
    "loci_list",
    "loci_outline",
    "loci_search",
    "loci_stats",
    "loci_store_health",
    "loci_verify",
}


def test_loci_file_advertises_success_and_error_output_schema() -> None:
    tools = asyncio.run(create_server().list_tools())
    schema = next(tool.output_schema for tool in tools if tool.name == "loci_file")

    assert schema is not None
    assert "result" not in schema.get("properties", {})
    assert len(schema["anyOf"]) == 2


def test_loci_file_real_success_and_error_payloads_validate(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "sample.py").write_text("def sample():\n    return 1\n")
    server = create_server()

    indexed = asyncio.run(
        server.call_tool(
            "loci_index",
            {"repo": str(repo), "incremental": False},
        )
    )
    success = asyncio.run(
        server.call_tool(
            "loci_file",
            {"repo": str(repo), "file_path": "sample.py"},
        )
    )
    error = asyncio.run(
        server.call_tool(
            "loci_file",
            {"repo": str(repo), "file_path": "missing.py"},
        )
    )

    assert indexed.is_error is False
    assert success.is_error is False
    assert success.structured_content == {
        "file": "sample.py",
        "content": "def sample():\n    return 1\n",
        "total_lines": 2,
        "start_line": 1,
        "end_line": 2,
    }
    LociFileOutput.model_validate(success.structured_content)
    assert error.is_error is True
    assert error.structured_content == {
        "error": {
            "code": "FILE_NOT_FOUND",
            "message": "File not found in cache",
            "details": {"repo": str(repo.resolve()), "file": "missing.py"},
        }
    }
    LociFileOutput.model_validate(error.structured_content)


def test_loci_file_sdk_rejects_malformed_explicit_result() -> None:
    server = create_server()
    tool = server._tool_manager.get_tool("loci_file")
    assert tool is not None

    with pytest.raises(ValidationError):
        tool.fn_metadata.convert_result(
            CallToolResult(
                content=[],
                structured_content={"file": "sample.py"},
                is_error=False,
            )
        )


def test_loci_file_known_objects_reject_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        LociFileOutput.model_validate(
            {
                "file": "sample.py",
                "content": "",
                "total_lines": 0,
                "start_line": 1,
                "end_line": 0,
                "unexpected": True,
            }
        )


def test_repository_tool_schemas_validate_real_success_payloads(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "sample.py").write_text("def sample():\n    return 1\n")
    server = create_server()

    results = {}
    results["loci_index"] = asyncio.run(
        server.call_tool(
            "loci_index",
            {"repo": str(repo), "incremental": False},
        )
    )
    results["loci_outline"] = asyncio.run(
        server.call_tool("loci_outline", {"repo": str(repo)})
    )
    symbol_id = results["loci_outline"].structured_content["files"][0]["symbols"][
        0
    ]["id"]
    results["loci_get"] = asyncio.run(
        server.call_tool(
            "loci_get",
            {"repo": str(repo), "symbol_ids": [symbol_id], "context": 1},
        )
    )
    results["loci_search"] = asyncio.run(
        server.call_tool("loci_search", {"repo": str(repo), "query": "sample"})
    )
    results["loci_grep"] = asyncio.run(
        server.call_tool("loci_grep", {"repo": str(repo), "pattern": "return"})
    )
    results["loci_verify"] = asyncio.run(
        server.call_tool("loci_verify", {"repo": str(repo)})
    )
    results["loci_list"] = asyncio.run(server.call_tool("loci_list", {}))

    models = {
        "loci_index": LociIndexOutput,
        "loci_outline": LociOutlineOutput,
        "loci_get": LociGetOutput,
        "loci_search": LociSearchOutput,
        "loci_grep": LociGrepOutput,
        "loci_verify": LociVerifyOutput,
        "loci_list": LociListOutput,
    }
    advertised = {tool.name: tool for tool in asyncio.run(server.list_tools())}
    for name, model in models.items():
        result = results[name]
        assert result.is_error is False
        model.model_validate(result.structured_content)
        assert advertised[name].output_schema is not None


def test_repository_tool_error_branch_validates_without_wire_changes(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    server = create_server()
    asyncio.run(
        server.call_tool(
            "loci_index",
            {"repo": str(repo), "incremental": False},
        )
    )

    result = asyncio.run(
        server.call_tool("loci_grep", {"repo": str(repo), "pattern": "["})
    )

    assert result.is_error is True
    assert result.structured_content["error"]["code"] == "INVALID_REGEX"
    LociGrepOutput.model_validate(result.structured_content)


def test_omittable_repository_fields_do_not_accept_null() -> None:
    LociOutlineOutput.model_validate({"files": []})

    with pytest.raises(ValidationError):
        LociOutlineOutput.model_validate(
            {
                "files": [
                    {
                        "file": "sample.py",
                        "symbols": [
                            {
                                "id": "sample.py::sample#function",
                                "name": "sample",
                                "kind": "function",
                                "line": 1,
                                "end_line": 2,
                                "signature": "def sample()",
                                "summary": "",
                                "decorators": None,
                            }
                        ],
                    }
                ]
            }
        )


def test_store_and_telemetry_schemas_validate_real_payloads(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "sample.py").write_text("def sample():\n    return 1\n")
    server = create_server()
    asyncio.run(
        server.call_tool(
            "loci_index",
            {"repo": str(repo), "incremental": False},
        )
    )

    results = {
        "loci_store_health": asyncio.run(
            server.call_tool("loci_store_health", {"offset": 0, "limit": 10})
        ),
        "loci_stats": asyncio.run(
            server.call_tool("loci_stats", {"repo": str(repo), "since_days": 7})
        ),
        "loci_analyze": asyncio.run(
            server.call_tool("loci_analyze", {"repo": str(repo), "since_days": 7})
        ),
    }
    models = {
        "loci_store_health": LociStoreHealthOutput,
        "loci_stats": LociStatsOutput,
        "loci_analyze": LociAnalyzeOutput,
    }
    advertised = {tool.name: tool for tool in asyncio.run(server.list_tools())}

    for name, model in models.items():
        result = results[name]
        assert result.is_error is False
        model.model_validate(result.structured_content)
        assert advertised[name].output_schema is not None


def test_store_health_structured_error_uses_the_declared_union() -> None:
    result = asyncio.run(
        create_server().call_tool("loci_store_health", {"limit": 0})
    )

    assert result.is_error is True
    assert result.structured_content["error"]["code"] == "INVALID_INPUT"
    LociStoreHealthOutput.model_validate(result.structured_content)


def test_graph_tool_schemas_validate_resolved_real_payloads(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "a.py").write_text(
        "from b import target\n\ndef caller():\n    return target()\n"
    )
    (repo / "b.py").write_text("def target():\n    return 1\n")
    server = create_server()
    asyncio.run(
        server.call_tool(
            "loci_index",
            {"repo": str(repo), "incremental": False},
        )
    )
    outline = asyncio.run(server.call_tool("loci_outline", {"repo": str(repo)}))
    symbols = [
        symbol
        for entry in outline.structured_content["files"]
        for symbol in entry["symbols"]
    ]
    caller_id = next(symbol["id"] for symbol in symbols if symbol["name"] == "caller")

    calls = {
        "loci_graph_anchors": {"repo": str(repo), "question": "caller target"},
        "loci_graph_neighbors": {
            "repo": str(repo),
            "seed_ids": ["a.py::__file__#file"],
        },
        "loci_graph_traverse_neighbors": {
            "repo": str(repo),
            "seed_ids": ["a.py::__file__#file"],
            "edge_types": ["imports"],
            "resolutions": ["import-resolved"],
        },
        "loci_graph_paths": {
            "repo": str(repo),
            "source_ids": ["a.py::__file__#file"],
            "target_ids": ["b.py::__file__#file"],
            "edge_types": ["imports"],
            "resolutions": ["import-resolved"],
        },
        "loci_graph_retrieve": {
            "repo": str(repo),
            "question": "caller target",
            "seed_ids": [caller_id],
        },
        "loci_graph_health": {"repo": str(repo)},
        "loci_graph_imports": {"repo": str(repo)},
        "loci_graph_references": {"repo": str(repo)},
        "loci_graph_calls": {"repo": str(repo)},
    }
    models = {
        "loci_graph_anchors": LociGraphAnchorsOutput,
        "loci_graph_neighbors": LociGraphNeighborsOutput,
        "loci_graph_traverse_neighbors": LociGraphTraverseNeighborsOutput,
        "loci_graph_paths": LociGraphPathsOutput,
        "loci_graph_retrieve": LociGraphRetrieveOutput,
        "loci_graph_health": LociGraphHealthOutput,
        "loci_graph_imports": LociGraphImportsOutput,
        "loci_graph_references": LociGraphReferencesOutput,
        "loci_graph_calls": LociGraphCallsOutput,
    }
    advertised = {tool.name: tool for tool in asyncio.run(server.list_tools())}

    for name, arguments in calls.items():
        result = asyncio.run(server.call_tool(name, arguments))
        assert result.is_error is False, name
        models[name].model_validate(result.structured_content)
        assert advertised[name].output_schema is not None


def test_graph_structured_error_uses_the_declared_union(tmp_path: Path) -> None:
    repo = tmp_path / "missing"
    result = asyncio.run(
        create_server().call_tool(
            "loci_graph_neighbors",
            {"repo": str(repo), "seed_ids": ["missing.py::__file__#file"]},
        )
    )

    assert result.is_error is True
    LociGraphNeighborsOutput.model_validate(result.structured_content)


def test_every_loci_tool_advertises_an_object_root_success_or_error_schema() -> None:
    tools = asyncio.run(create_server().list_tools())

    assert len(tools) == 20
    assert {tool.name for tool in tools} == EXPECTED_LOCI_TOOLS
    assert not [tool.name for tool in tools if tool.output_schema is None]
    for tool in tools:
        schema = tool.output_schema
        assert schema is not None
        assert schema["type"] == "object"
        assert "result" not in schema.get("properties", {})
        assert len(schema["anyOf"]) == 2
        branch_names = {branch["$ref"].rsplit("/", 1)[-1] for branch in schema["anyOf"]}
        assert "LociErrorOutput" in branch_names
        for branch_name in branch_names:
            assert schema["$defs"][branch_name]["type"] == "object"
