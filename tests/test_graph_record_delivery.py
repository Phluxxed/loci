from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Any

import pytest
from mcp import Client, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.types import CallToolResult

from loci.mcp_output_models import LociGraphReferencesOutput
from loci.mcp_server import create_server
from loci.service import graph_calls, graph_references, index_repo


REFERENCE_COMPACT_KEYS = {
    "source_id",
    "source_file",
    "target_id",
    "target_file",
    "language",
    "line",
    "column",
    "start_byte",
    "end_byte",
    "text",
    "status",
    "resolution",
    "unresolved_reason",
    "resolution_configuration",
    "relation",
    "context",
    "import_unresolved_reason",
}

CALL_COMPACT_KEYS = {
    "source_id",
    "source_file",
    "target_id",
    "target_file",
    "language",
    "line",
    "column",
    "start_byte",
    "end_byte",
    "text",
    "status",
    "resolution",
    "unresolved_reason",
    "resolution_configuration",
    "relation",
    "callee_start_byte",
    "callee_end_byte",
    "reference_unresolved_reason",
}


def _wire_bytes(payload: dict[str, Any]) -> int:
    return len(
        json.dumps(
            {"content": [], "structuredContent": payload, "isError": False},
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")
    )


def _large_typescript_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    names = [f"Payload{i:03d}" for i in range(72)]
    (repo / "types.ts").write_text(
        "export class Base {}\n"
        "export interface Contract {}\n"
        + "".join(f"export interface {name} {{ value: string; }}\n" for name in names),
        encoding="utf-8",
    )
    (repo / "decoy.ts").write_text(
        "".join(f"export interface {name} {{ decoy: true; }}\n" for name in names),
        encoding="utf-8",
    )
    (repo / "consumer.ts").write_text(
        'import { Base, Contract } from "./types.js";\n'
        f'import type {{ {", ".join(names)} }} from "./types.js";\n'
        f"export class Worker extends Base implements Contract {{ value!: {names[0]}; }}\n"
        + "".join(
            f"export function use{i:03d}(value: {name}): {name} {{ return value; }}\n"
            for i, name in enumerate(names)
        )
        + "export function broken(value: Missing): Missing { return value; }\n",
        encoding="utf-8",
    )
    return repo


async def _collect_pages(
    server: Any,
    tool: str,
    arguments: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    offset = 0
    items: list[dict[str, Any]] = []
    pages: list[dict[str, Any]] = []
    while True:
        response = await server.call_tool(tool, {**arguments, "offset": offset})
        assert isinstance(response, CallToolResult)
        assert response.is_error is False
        assert response.content == []
        page = response.structured_content
        assert page["pagination"]["offset"] == offset
        assert page["counts"]["returned"] == len(page["items"])
        assert page["budget"]["output_bytes"] == _wire_bytes(page)
        assert page["budget"]["output_bytes"] <= page["budget"]["max_output_bytes"]
        pages.append(page)
        items.extend(page["items"])
        next_offset = page["pagination"]["next_offset"]
        if next_offset is None:
            break
        assert page["items"], "successful pagination must always make progress"
        assert next_offset == offset + len(page["items"])
        offset = next_offset
    return items, pages


def _compact_reference_identity(item: dict[str, Any]) -> tuple[Any, ...]:
    return (
        item["source_file"],
        item["start_byte"],
        item["end_byte"],
        item["text"],
        item["source_id"],
        item["target_id"],
    )


def _full_reference_identity(item: dict[str, Any]) -> tuple[Any, ...]:
    raw = item["raw"]
    return (
        raw["source_file"],
        raw["start_byte"],
        raw["end_byte"],
        raw["text"],
        item["source_id"],
        item["target_id"],
    )


def test_compact_type_reference_byte_pages_deliver_every_stable_site(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LOCI_BASE_DIR", str(tmp_path / "store"))
    repo = _large_typescript_repo(tmp_path)
    index_repo(repo, incremental=False)
    rich = graph_references(repo, family="type", limit=500)
    expected = [_full_reference_identity(item) for item in rich["items"]]
    assert rich["counts"] == {
        "total": 149,
        "resolved": 147,
        "unresolved": 2,
        "returned": 149,
    }

    async def exercise() -> tuple[Any, ...]:
        server = create_server()
        default_items, default_pages = await _collect_pages(
            server,
            "loci_graph_references",
            {"repo": str(repo), "family": "type", "limit": 500},
        )
        bounded_items, bounded_pages = await _collect_pages(
            server,
            "loci_graph_references",
            {
                "repo": str(repo),
                "family": "type",
                "limit": 500,
                "max_output_bytes": 4096,
            },
        )
        full = await server.call_tool(
            "loci_graph_references",
            {
                "repo": str(repo),
                "family": "type",
                "limit": 1,
                "detail": "full",
                "max_output_bytes": 262_144,
            },
        )
        symbols = await server.call_tool(
            "loci_graph_references",
            {
                "repo": str(repo),
                "family": "symbol",
                "limit": 500,
                "max_output_bytes": 262_144,
            },
        )
        return default_items, default_pages, bounded_items, bounded_pages, full, symbols

    default_items, default_pages, bounded_items, bounded_pages, full, symbols = (
        asyncio.run(exercise())
    )

    assert len(default_pages) > 1
    assert len(bounded_pages) > len(default_pages)
    assert all(page["detail"] == "compact" for page in default_pages + bounded_pages)
    assert any(page["budget"]["byte_limit_reached"] for page in default_pages)
    assert [_compact_reference_identity(item) for item in default_items] == expected
    assert [_compact_reference_identity(item) for item in bounded_items] == expected
    assert len(set(expected)) == len(expected)

    source = (repo / "consumer.ts").read_bytes()
    assert all(set(item) == REFERENCE_COMPACT_KEYS for item in default_items)
    assert all(
        source[item["start_byte"]:item["end_byte"]].decode("utf-8") == item["text"]
        for item in default_items
    )
    assert {item["relation"] for item in default_items} >= {
        "uses_type",
        "extends",
        "implements",
    }
    assert {item["context"] for item in default_items} >= {
        "annotation",
        "return",
        "heritage",
    }
    assert {item["unresolved_reason"] for item in default_items} >= {
        None,
        "binding_not_found",
    }
    assert all(
        item["target_file"] != "decoy.ts"
        for item in default_items
        if item["target_file"] is not None
    )
    assert all(item["import_unresolved_reason"] is None for item in default_items)

    assert full.is_error is False
    full_payload = full.structured_content
    service_page = graph_references(repo, family="type", limit=1)
    assert full_payload["detail"] == "full"
    assert full_payload["items"] == service_page["items"]
    assert "raw" in full_payload["items"][0]
    assert "support" in full_payload["items"][0]

    assert symbols.is_error is False
    symbol_items = symbols.structured_content["items"]
    assert symbol_items
    assert all(set(item) == REFERENCE_COMPACT_KEYS for item in symbol_items)
    assert {item["relation"] for item in symbol_items} == {
        "references",
        "references_type",
    }
    assert all(item["context"] is None for item in symbol_items)


def test_compact_calls_preserve_call_and_callee_spans_with_utf8_accounting(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LOCI_BASE_DIR", str(tmp_path / "store"))
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "target.py").write_text("def café():\n    return 1\n", encoding="utf-8")
    (repo / "use.py").write_text(
        "from target import café\n"
        "from missing import lost\n\n"
        "def caller():\n"
        "    café()\n"
        "    return lost()\n",
        encoding="utf-8",
    )
    index_repo(repo, incremental=False)

    async def exercise() -> tuple[CallToolResult, CallToolResult]:
        server = create_server()
        compact = await server.call_tool(
            "loci_graph_calls", {"repo": str(repo), "limit": 500}
        )
        full = await server.call_tool(
            "loci_graph_calls",
            {
                "repo": str(repo),
                "limit": 500,
                "detail": "full",
                "max_output_bytes": 262_144,
            },
        )
        return compact, full

    compact, full = asyncio.run(exercise())
    assert compact.is_error is False
    payload = compact.structured_content
    assert payload["detail"] == "compact"
    assert payload["budget"]["output_bytes"] == _wire_bytes(payload)
    assert payload["budget"]["output_bytes"] <= 16_384
    assert payload["counts"] == {
        "total": 2,
        "resolved": 1,
        "unresolved": 1,
        "returned": 2,
    }
    source = (repo / "use.py").read_bytes()
    assert all(set(item) == CALL_COMPACT_KEYS for item in payload["items"])
    assert all(item["relation"] == "calls" for item in payload["items"])
    for item in payload["items"]:
        assert source[item["callee_start_byte"]:item["callee_end_byte"]].decode() == item["text"]
        call_text = source[item["start_byte"]:item["end_byte"]].decode()
        assert call_text == f'{item["text"]}()'
    resolved = next(item for item in payload["items"] if item["status"] == "resolved")
    unresolved = next(item for item in payload["items"] if item["status"] == "unresolved")
    assert resolved["text"] == "café"
    assert resolved["source_id"] == "use.py::caller#function"
    assert resolved["target_id"] == "target.py::café#function"
    assert unresolved["reference_unresolved_reason"] == "import_unresolved"

    assert full.is_error is False
    assert full.structured_content["items"] == graph_calls(repo, limit=500)["items"]
    assert all("raw" in item and "support" in item for item in full.structured_content["items"])


def test_compact_symbol_references_accept_swift_records(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LOCI_BASE_DIR", str(tmp_path / "store"))
    repo = tmp_path / "repo"
    (repo / "Feature/Sources/Feature").mkdir(parents=True)
    (repo / "App").mkdir()
    (repo / "Feature/Package.swift").write_text(
        "// swift-tools-version:5.9\n"
        "import PackageDescription\n\n"
        'let package = Package(name: "Feature", '
        'targets: [.target(name: "Feature")])\n',
        encoding="utf-8",
    )
    (repo / "Feature/Sources/Feature/Model.swift").write_text(
        "public struct Ticket {}\n",
        encoding="utf-8",
    )
    (repo / "App/Main.swift").write_text(
        "import Feature\nfunc run() { record(Ticket) }\n",
        encoding="utf-8",
    )
    index_repo(repo, incremental=False)

    result = asyncio.run(
        create_server().call_tool("loci_graph_references", {"repo": str(repo)})
    )
    assert result.is_error is False
    payload = result.structured_content
    LociGraphReferencesOutput.model_validate(payload)
    item, = payload["items"]
    assert set(item) == REFERENCE_COMPACT_KEYS
    assert item["language"] == "swift"
    assert item["relation"] == "references"
    assert item["text"] == "Ticket"
    assert item["target_id"] == "Feature/Sources/Feature/Model.swift::Ticket#class"


@pytest.mark.parametrize(
    ("tool", "arguments"),
    [
        ("loci_graph_references", {"detail": "diagnostic"}),
        ("loci_graph_calls", {"detail": "diagnostic"}),
        ("loci_graph_references", {"max_output_bytes": None}),
        ("loci_graph_calls", {"max_output_bytes": True}),
        ("loci_graph_references", {"max_output_bytes": "2048"}),
        ("loci_graph_calls", {"max_output_bytes": 2048.0}),
        ("loci_graph_references", {"max_output_bytes": 2047}),
        ("loci_graph_calls", {"max_output_bytes": 262145}),
    ],
)
def test_graph_record_tools_reject_invalid_delivery_inputs(
    tmp_path: Path,
    tool: str,
    arguments: dict[str, Any],
) -> None:
    server = create_server()
    result = asyncio.run(
        server.call_tool(tool, {"repo": str(tmp_path / "missing"), **arguments})
    )
    assert isinstance(result, CallToolResult)
    assert result.is_error is True
    assert result.structured_content["error"]["code"] == "INVALID_INPUT"


def test_oversized_record_reports_required_budget_and_exact_retry_succeeds(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LOCI_BASE_DIR", str(tmp_path / "store"))
    repo = tmp_path / "repo"
    repo.mkdir()
    identifier = "target_" + "x" * 1800
    (repo / "main.py").write_text(
        f"def {identifier}():\n    return 1\n\n"
        f"def caller():\n    return {identifier}()\n",
        encoding="utf-8",
    )
    index_repo(repo, incremental=False)
    server = create_server()

    error = asyncio.run(
        server.call_tool(
            "loci_graph_calls",
            {"repo": str(repo), "limit": 1, "max_output_bytes": 2048},
        )
    )
    assert error.is_error is True
    failure = error.structured_content["error"]
    assert failure["code"] == "OUTPUT_BUDGET_EXCEEDED"
    assert failure["details"]["offset"] == 0
    assert failure["details"]["detail"] == "compact"
    assert failure["details"]["max_output_bytes"] == 2048
    required = failure["details"]["required_output_bytes"]
    assert 2048 < required <= 262_144

    retry = asyncio.run(
        server.call_tool(
            "loci_graph_calls",
            {"repo": str(repo), "limit": 1, "max_output_bytes": required},
        )
    )
    assert retry.is_error is False
    assert retry.structured_content["counts"]["returned"] == 1
    assert retry.structured_content["pagination"]["next_offset"] is None
    assert retry.structured_content["budget"]["output_bytes"] == required


def test_default_compact_page_crosses_actual_mcp_subprocess_under_16k(
    tmp_path: Path,
) -> None:
    repo = _large_typescript_repo(tmp_path)
    env = os.environ.copy()
    env["LOCI_BASE_DIR"] = str(tmp_path / "subprocess-store")
    env["LOCI_STORE_NAMESPACE"] = "graph-record-delivery"
    env["PYTHONPATH"] = str(Path.cwd() / "src")
    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "loci.mcp_server"],
        env=env,
        cwd=Path.cwd(),
    )

    async def exercise() -> tuple[dict[str, Any], CallToolResult]:
        async with Client(stdio_client(params)) as session:
            tools = await session.list_tools()
            schema = next(
                tool.input_schema
                for tool in tools.tools
                if tool.name == "loci_graph_references"
            )
            response = await session.call_tool(
                "loci_graph_references",
                {"repo": str(repo), "family": "type", "limit": 500},
            )
            return schema, response

    schema, response = asyncio.run(exercise())
    assert schema["required"] == ["repo"]
    assert schema["properties"]["detail"]["default"] == "compact"
    budget_schema = schema["properties"]["max_output_bytes"]
    assert budget_schema["default"] == 16_384
    assert budget_schema["minimum"] == 2_048
    assert budget_schema["maximum"] == 262_144

    assert response.is_error is False
    assert response.content == []
    payload = response.structured_content
    assert payload["detail"] == "compact"
    assert payload["budget"]["max_output_bytes"] == 16_384
    assert payload["budget"]["output_bytes"] == _wire_bytes(payload)
    sdk_result_bytes = CallToolResult(
        content=response.content,
        structured_content=payload,
        is_error=response.is_error,
    ).model_dump_json(by_alias=True, exclude_unset=True).encode("utf-8")
    assert payload["budget"]["output_bytes"] == len(sdk_result_bytes)
    assert payload["budget"]["output_bytes"] <= 16_384
    assert payload["budget"]["byte_limit_reached"] is True
    assert 0 < payload["counts"]["returned"] < payload["counts"]["total"]
    assert all(set(item) == REFERENCE_COMPACT_KEYS for item in payload["items"])
