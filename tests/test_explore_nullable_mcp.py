from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import pytest
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import CallToolResult

from loci import mcp_server
from loci.mcp_server import create_server


def _fixture_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "main.py").write_text(
        "def run():\n"
        "    return 1\n",
        encoding="utf-8",
    )
    return repo


def _explore_arguments(repo: Path, **budgets: Any) -> dict[str, Any]:
    return {
        "repo": str(repo),
        "intent": "locate",
        "seed_ids": ["main.py::run#function"],
        **budgets,
    }


def test_loci_explore_advertises_nullable_byte_budgets() -> None:
    tool = next(
        tool for tool in asyncio.run(create_server().list_tools()) if tool.name == "loci_explore"
    )

    assert tool.input_schema["required"] == ["repo", "intent"]
    for name, minimum, maximum in (
        ("max_output_bytes", 2048, 262144),
        ("max_evidence_bytes", 0, 65536),
    ):
        property_schema = tool.input_schema["properties"][name]
        assert property_schema["default"] == {
            "max_output_bytes": 16_384,
            "max_evidence_bytes": 8_192,
        }[name]
        assert {branch.get("type") for branch in property_schema["anyOf"]} == {
            "integer",
            "null",
        }
        assert property_schema["minimum"] == minimum
        assert property_schema["maximum"] == maximum


def test_loci_explore_normalizes_nullable_budgets_and_forwards_integers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _fixture_repo(tmp_path)
    server = create_server()
    forwarded: list[tuple[int, int]] = []
    service = mcp_server._service()
    explore = service.explore

    def record_explore(*args: Any, **kwargs: Any) -> Any:
        forwarded.append((kwargs["max_output_bytes"], kwargs["max_evidence_bytes"]))
        return explore(*args, **kwargs)

    monkeypatch.setattr(service, "explore", record_explore)

    cases = (
        ({}, (16_384, 8_192)),
        ({"max_output_bytes": None, "max_evidence_bytes": None}, (16_384, 8_192)),
        ({"max_output_bytes": None, "max_evidence_bytes": 0}, (16_384, 0)),
        ({"max_output_bytes": 2_048, "max_evidence_bytes": None}, (2_048, 8_192)),
        ({"max_output_bytes": 262_144, "max_evidence_bytes": 65_536}, (262_144, 65_536)),
    )

    async def exercise() -> None:
        indexed = await server.call_tool(
            "loci_index", {"repo": str(repo), "incremental": False}
        )
        assert isinstance(indexed, CallToolResult)
        assert indexed.is_error is False
        for budgets, expected_limits in cases:
            result = await server.call_tool(
                "loci_explore", _explore_arguments(repo, **budgets)
            )
            assert isinstance(result, CallToolResult)
            assert result.is_error is False
            assert (
                result.structured_content["limits"]["max_output_bytes"],
                result.structured_content["limits"]["max_evidence_bytes"],
            ) == expected_limits

    asyncio.run(exercise())
    assert forwarded == [expected for _budgets, expected in cases]


@pytest.mark.parametrize(
    ("field", "value", "expected"),
    (
        ("max_output_bytes", 2_047, "structured"),
        ("max_output_bytes", 262_145, "structured"),
        ("max_evidence_bytes", -1, "structured"),
        ("max_evidence_bytes", 65_537, "structured"),
        ("max_output_bytes", "2048", "tool_error"),
        ("max_evidence_bytes", "0", "tool_error"),
        ("max_output_bytes", 2_048.0, "tool_error"),
        ("max_evidence_bytes", 0.0, "tool_error"),
        ("max_output_bytes", True, "tool_error"),
        ("max_evidence_bytes", False, "tool_error"),
    ),
)
def test_loci_explore_rejects_invalid_byte_budgets(
    tmp_path: Path, field: str, value: Any, expected: str
) -> None:
    repo = _fixture_repo(tmp_path)
    server = create_server()

    if expected == "tool_error":
        with pytest.raises(ToolError):
            asyncio.run(
                server.call_tool(
                    "loci_explore",
                    _explore_arguments(repo, **{field: value}),
                )
            )
        return

    async def indexed_call() -> CallToolResult:
        indexed = await server.call_tool(
            "loci_index", {"repo": str(repo), "incremental": False}
        )
        assert isinstance(indexed, CallToolResult)
        assert indexed.is_error is False
        result = await server.call_tool(
            "loci_explore",
            _explore_arguments(repo, **{field: value}),
        )
        assert isinstance(result, CallToolResult)
        return result

    result = asyncio.run(indexed_call())
    assert result.is_error is True
    assert result.structured_content["error"]["code"] == "INVALID_INPUT"
