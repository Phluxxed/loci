from __future__ import annotations

import asyncio
import hashlib
import os
import sys
from pathlib import Path
from typing import Any

import pytest
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from loci.graph.contracts import GRAPH_SCHEMA_VERSION
from loci.service import LociError, graph_references, index_repo
from loci.storage.index_store import IndexStore


def _reference_repo(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> Path:
    monkeypatch.setenv("LOCI_BASE_DIR", str(tmp_path / ".codeindex"))
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "target.py").write_text(
        "class Thing:\n    pass\n",
        encoding="utf-8",
    )
    (repo / "consumer.py").write_text(
        (
            "from target import Thing\n"
            "from missing import Lost\n\n"
            "def build():\n"
            "    return Thing()\n\n"
            "def broken():\n"
            "    return Lost()\n"
        ),
        encoding="utf-8",
    )
    index_repo(repo, incremental=False)
    return repo


def test_graph_references_returns_stable_bounded_record_page(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    repo = _reference_repo(tmp_path, monkeypatch)

    result = graph_references(repo, limit=1)

    assert result["schema_version"] == GRAPH_SCHEMA_VERSION
    assert result["repo"] == str(repo.resolve())
    assert result["file"] is None
    assert result["status"] == "all"
    assert result["counts"] == {
        "total": 2,
        "resolved": 1,
        "unresolved": 1,
        "returned": 1,
    }
    assert result["pagination"] == {
        "offset": 0,
        "limit": 1,
        "next_offset": 1,
    }
    assert len(result["items"]) == 1
    item = result["items"][0]
    assert set(item) == {
        "raw",
        "binding",
        "source_file",
        "source_id",
        "source_kind",
        "import_source_id",
        "import_target_id",
        "target_file",
        "target_id",
        "target_kind",
        "status",
        "resolution",
        "unresolved_reason",
        "import_unresolved_reason",
        "resolution_basis",
        "support",
        "resolution_control_files",
        "resolution_configuration",
    }
    assert item["source_file"] == "consumer.py"
    assert item["source_id"] == "consumer.py::build#function"
    assert item["import_source_id"] == "consumer.py::__file__#file"
    assert item["import_target_id"] == "target.py::__file__#file"
    assert item["target_id"] == "target.py::Thing#class"
    assert item["status"] == "resolved"
    assert item["resolution"] == "import-resolved"
    assert item["raw"]["path"] == ["Thing"]
    assert item["binding"]["local_name"] == "Thing"
    assert [support["kind"] for support in item["support"]] == [
        "import_binding",
        "definition",
    ]


def test_graph_references_filters_before_counts_status_and_pagination(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    repo = _reference_repo(tmp_path, monkeypatch)

    unresolved = graph_references(
        repo,
        file="consumer.py",
        status="unresolved",
        limit=1,
    )
    second = graph_references(repo, offset=1, limit=1)
    empty = graph_references(repo, file="not-indexed.py", status="resolved")

    assert unresolved["counts"] == {
        "total": 2,
        "resolved": 1,
        "unresolved": 1,
        "returned": 1,
    }
    assert unresolved["items"][0]["raw"]["path"] == ["Lost"]
    assert unresolved["items"][0]["status"] == "unresolved"
    assert unresolved["items"][0]["unresolved_reason"] == "import_unresolved"
    assert unresolved["items"][0]["import_unresolved_reason"] == "not_indexed"
    assert unresolved["items"][0]["resolution"] is None
    assert unresolved["pagination"]["next_offset"] is None
    assert second["items"][0]["raw"]["path"] == ["Lost"]
    assert second["pagination"]["next_offset"] is None
    assert empty["counts"] == {
        "total": 0,
        "resolved": 0,
        "unresolved": 0,
        "returned": 0,
    }
    assert empty["items"] == []
    assert empty["pagination"]["next_offset"] is None


@pytest.mark.parametrize(
    ("kwargs", "field"),
    [
        ({"file": ""}, "file"),
        ({"file": "../consumer.py"}, "file"),
        ({"file": "./consumer.py"}, "file"),
        ({"file": "/consumer.py"}, "file"),
        ({"file": "consumer\\file.py"}, "file"),
        ({"file": 1}, "file"),
        ({"status": "RESOLVED"}, "status"),
        ({"status": None}, "status"),
        ({"status": []}, "status"),
        ({"offset": -1}, "offset"),
        ({"offset": True}, "offset"),
        ({"offset": "0"}, "offset"),
        ({"limit": 0}, "limit"),
        ({"limit": 501}, "limit"),
        ({"limit": True}, "limit"),
        ({"limit": "1"}, "limit"),
    ],
)
def test_graph_references_rejects_invalid_filters_and_pagination(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    kwargs: dict[str, Any],
    field: str,
):
    repo = _reference_repo(tmp_path, monkeypatch)

    with pytest.raises(LociError) as exc_info:
        graph_references(repo, **kwargs)

    assert exc_info.value.code == "INVALID_INPUT"
    assert exc_info.value.details["field"] == field


def test_mcp_reference_diagnostics_and_traversal_survive_fresh_process(
    tmp_path: Path,
):
    result = asyncio.run(_reference_mcp_after_restart(
        tmp_path / "repo",
        tmp_path / ".codeindex",
    ))

    schema = result["schema"]
    assert schema["required"] == ["repo"]
    assert set(schema["properties"]) == {
        "repo",
        "file",
        "status",
        "offset",
        "limit",
    }
    assert schema["properties"]["file"]["default"] is None
    assert schema["properties"]["status"]["default"] == "all"
    assert schema["properties"]["offset"]["default"] == 0
    assert schema["properties"]["limit"]["default"] == 100

    first = result["first"]
    second = result["second"]
    unresolved = result["unresolved"]
    assert first["counts"] == {
        "total": 2,
        "resolved": 1,
        "unresolved": 1,
        "returned": 1,
    }
    assert first["items"][0]["raw"]["path"] == ["Thing"]
    assert first["pagination"]["next_offset"] == 1
    assert second["items"][0]["raw"]["path"] == ["Lost"]
    assert second["pagination"]["next_offset"] is None
    assert unresolved["items"][0]["unresolved_reason"] == "import_unresolved"
    assert unresolved["items"][0]["import_unresolved_reason"] == "not_indexed"

    outgoing = result["outgoing"]["results"][0]["neighbors"][0]
    incoming = result["incoming"]["results"][0]["neighbors"][0]
    assert outgoing["node"]["id"] == "target.py::Thing#class"
    assert outgoing["traversed"] == "forward"
    assert outgoing["edge"]["type"] == "references"
    assert outgoing["edge"]["resolution"] == "import-resolved"
    assert incoming["node"]["id"] == "consumer.py::build#function"
    assert incoming["traversed"] == "reverse"
    assert incoming["edge"]["from"] == "consumer.py::build#function"
    assert incoming["edge"]["to"] == "target.py::Thing#class"

    path = result["paths"]["paths"][0]
    assert [node["id"] for node in path["nodes"]] == [
        "consumer.py::build#function",
        "target.py::Thing#class",
    ]
    assert path["steps"][0]["edge"]["type"] == "references"
    assert "Thing" in path["steps"][0]["evidence_span"]["content"]
    assert "class Thing" in result["target"]["symbols"][0]["source"]
    assert result["compatibility"]["results"][0]["neighbors"] == []

    for field in ("file", "status", "offset", "limit"):
        assert result["errors"][field]["error"]["code"] == "INVALID_INPUT"
        assert result["errors"][field]["error"]["details"]["field"] == field
    assert result["index_before"] == result["index_after"]


async def _reference_mcp_after_restart(
    repo: Path,
    cache_dir: Path,
) -> dict[str, Any]:
    repo.mkdir()
    (repo / "target.py").write_text(
        "class Thing:\n    pass\n",
        encoding="utf-8",
    )
    (repo / "consumer.py").write_text(
        (
            "from target import Thing\n"
            "from missing import Lost\n\n"
            "def build():\n"
            "    return Thing()\n\n"
            "def broken():\n"
            "    return Lost()\n"
        ),
        encoding="utf-8",
    )
    env = os.environ.copy()
    env["LOCI_BASE_DIR"] = str(cache_dir)
    env["LOCI_STORE_NAMESPACE"] = "test"
    env["PYTHONPATH"] = str(Path.cwd() / "src")
    server_params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "loci.mcp_server"],
        env=env,
        cwd=Path.cwd(),
    )

    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            indexed = await session.call_tool(
                "loci_index",
                arguments={"path": str(repo), "incremental": False},
            )
            indexed_content = indexed.structuredContent
            assert indexed_content is not None
            assert indexed_content["graph_symbol_references_resolved"] == 1
            assert indexed_content["graph_symbol_references_unresolved"] == 1

    index_path = IndexStore(base_dir=cache_dir)._index_path(repo.resolve())
    index_before = (
        hashlib.sha256(index_path.read_bytes()).hexdigest(),
        index_path.stat().st_mtime_ns,
    )

    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = await session.list_tools()
            schema = next(
                tool.inputSchema
                for tool in tools.tools
                if tool.name == "loci_graph_references"
            )
            first = await session.call_tool(
                "loci_graph_references",
                arguments={"repo": str(repo), "limit": 1},
            )
            second = await session.call_tool(
                "loci_graph_references",
                arguments={"repo": str(repo), "offset": 1, "limit": 1},
            )
            unresolved = await session.call_tool(
                "loci_graph_references",
                arguments={
                    "repo": str(repo),
                    "file": "consumer.py",
                    "status": "unresolved",
                },
            )
            edge_arguments = {
                "repo": str(repo),
                "namespaces": ["loci"],
                "edge_types": ["references", "references_type"],
                "resolutions": ["import-resolved"],
            }
            outgoing = await session.call_tool(
                "loci_graph_traverse_neighbors",
                arguments={
                    **edge_arguments,
                    "seed_ids": ["consumer.py::build#function"],
                },
            )
            incoming = await session.call_tool(
                "loci_graph_traverse_neighbors",
                arguments={
                    **edge_arguments,
                    "seed_ids": ["target.py::Thing#class"],
                    "direction": "incoming",
                },
            )
            paths = await session.call_tool(
                "loci_graph_paths",
                arguments={
                    **edge_arguments,
                    "source_ids": ["consumer.py::build#function"],
                    "target_ids": ["target.py::Thing#class"],
                },
            )
            target = await session.call_tool(
                "loci_get",
                arguments={
                    "repo": str(repo),
                    "symbol_ids": ["target.py::Thing#class"],
                },
            )
            compatibility = await session.call_tool(
                "loci_graph_neighbors",
                arguments={
                    "repo": str(repo),
                    "seed_ids": ["consumer.py::build#function"],
                },
            )
            errors = {}
            for field, arguments in (
                ("file", {"file": "../consumer.py"}),
                ("status", {"status": "invalid"}),
                ("offset", {"offset": -1}),
                ("limit", {"limit": 501}),
            ):
                error = await session.call_tool(
                    "loci_graph_references",
                    arguments={"repo": str(repo), **arguments},
                )
                assert error.isError is True
                errors[field] = error.structuredContent

    index_after = (
        hashlib.sha256(index_path.read_bytes()).hexdigest(),
        index_path.stat().st_mtime_ns,
    )
    return {
        "schema": schema,
        "first": first.structuredContent,
        "second": second.structuredContent,
        "unresolved": unresolved.structuredContent,
        "outgoing": outgoing.structuredContent,
        "incoming": incoming.structuredContent,
        "paths": paths.structuredContent,
        "target": target.structuredContent,
        "compatibility": compatibility.structuredContent,
        "errors": errors,
        "index_before": index_before,
        "index_after": index_after,
    }
