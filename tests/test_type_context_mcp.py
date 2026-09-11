import asyncio
from pathlib import Path

from loci.mcp_output_models import GraphEdge, LociGetOutput
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


def _call(server, name: str, arguments: dict):
    return asyncio.run(server.call_tool(name, arguments))


def test_mcp_get_type_context_is_opt_in_scoped_and_fresh(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("LOCI_BASE_DIR", str(tmp_path / "store"))
    monkeypatch.setenv("LOCI_STORE_NAMESPACE", "type-context-test")

    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "types.ts").write_text(
        "export interface Payload {\n"
        "  requestId: string;\n"
        "  amount: number;\n"
        "}\n",
        encoding="utf-8",
    )
    (repo / "consumer.ts").write_text(
        'import type { Payload as ImportedPayload } from "./types.js";\n'
        "export function processOrder(value: ImportedPayload): string {\n"
        "  return value.requestId;\n"
        "}\n",
        encoding="utf-8",
    )

    server = create_server()
    indexed = _call(
        server,
        "loci_index",
        {"repo": str(repo), "incremental": False},
    )
    assert indexed.is_error is False

    tools = asyncio.run(server.list_tools())
    assert {tool.name for tool in tools} == EXPECTED_LOCI_TOOLS
    assert len(tools) == len(EXPECTED_LOCI_TOOLS)

    outline = _call(server, "loci_outline", {"repo": str(repo)})
    assert outline.is_error is False
    all_symbols = [
        symbol
        for entry in outline.structured_content["files"]
        for symbol in entry["symbols"]
    ]
    anchor = next(
        symbol["id"]
        for symbol in all_symbols
        if symbol["id"] == "consumer.ts::processOrder#function"
    )

    legacy = _call(
        server,
        "loci_get",
        {"repo": str(repo), "symbol_ids": [anchor]},
    )
    assert legacy.is_error is False
    from loci import service

    assert legacy.structured_content == {
        "symbols": service.get_symbols(repo, [anchor], ensure_fresh=True)
    }
    assert "type_context" not in legacy.structured_content

    search = _call(
        server,
        "loci_search",
        {"repo": str(repo), "query": "processOrder"},
    )
    assert search.is_error is False
    assert search.structured_content["symbols"][0]["id"] == anchor

    opt_in = _call(
        server,
        "loci_get",
        {
            "repo": str(repo),
            "symbol_ids": [anchor],
            "selected_from_search_id": search.structured_content["search_id"],
            "include_type_context": True,
        },
    )
    assert opt_in.is_error is False
    LociGetOutput.model_validate(opt_in.structured_content)

    result = opt_in.structured_content
    context = result["type_context"]
    assert result["symbols"] == [service.get_symbols(repo, [anchor])[0]]
    assert context["scope"] == "existing_imported_type_references"
    assert context["status"] == "complete"
    assert [symbol["id"] for symbol in context["symbols"]] == [
        "types.ts::Payload#interface"
    ]
    assert "selection" not in context
    assert "selected_from_search_id" not in context["symbols"][0]

    reference = context["references"][0]
    assert reference["owner_id"] == anchor
    assert reference["target_id"] == "types.ts::Payload#interface"
    assert reference["reference"] == {
        "file": "consumer.ts",
        "start_byte": 98,
        "end_byte": 113,
    }
    edge = GraphEdge.model_validate(reference["edge"])
    assert edge.from_ == "consumer.ts::__file__#file"
    assert edge.to == "types.ts::Payload#interface"
    assert edge.type == "references_type"
    assert edge.directed is True
    assert edge.namespace == "loci"
    assert edge.resolution == "import-resolved"
    assert any(
        evidence["file"] == "consumer.ts"
        and evidence["content"].startswith("import type")
        for evidence in context["evidence"]
    )
    target = next(
        symbol
        for symbol in context["symbols"]
        if symbol["id"] == "types.ts::Payload#interface"
    )
    assert "amount: number" in target["source"]

    (repo / "types.ts").write_text(
        "export interface Payload {\n"
        "  requestId: string;\n"
        "  amount: number;\n"
        "  currency: string;\n"
        "}\n",
        encoding="utf-8",
    )
    refreshed = _call(
        server,
        "loci_get",
        {
            "repo": str(repo),
            "symbol_ids": [anchor],
            "include_type_context": True,
        },
    )
    assert refreshed.is_error is False
    LociGetOutput.model_validate(refreshed.structured_content)
    refreshed_target = next(
        symbol
        for symbol in refreshed.structured_content["type_context"]["symbols"]
        if symbol["id"] == "types.ts::Payload#interface"
    )
    assert "currency: string" in refreshed_target["source"]
