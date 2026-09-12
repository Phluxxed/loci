"""Shared W4.6 acceptance through the normal stdio MCP boundary.

These checks intentionally reuse the language-specific delivery suites for each
language's exhaustive corpus facts.  They cover the common transport contract,
the two frozen non-language controls, and freshness/isolation that must hold for
every language slice.
"""
from __future__ import annotations

import asyncio
import hashlib
from pathlib import Path

from mcp import Client
from mcp.client.stdio import stdio_client
from mcp.types import CallToolResult

from benchmarks.typescript_context_corpus import load_corpus, materialize_snapshot
from loci.mcp_output_models import LociExploreOutput
from tests.test_exploration_mcp import _server_params
from tests.test_python_context_delivery import CORPUS_ROOT


def _source_by_id(payload: dict) -> dict[int, dict]:
    return {source["id"]: source for source in payload["sources"]}


def _interval_bytes(payload: dict) -> int:
    """Count delivered source as unique same-version byte intervals."""

    intervals: dict[tuple[str, str], list[tuple[int, int]]] = {}
    for source in payload["sources"]:
        intervals.setdefault((source["file"], source["content_hash"]), []).append(
            (source["start_byte"], source["end_byte"])
        )
    total = 0
    for ranges in intervals.values():
        start = end = -1
        for current_start, current_end in sorted(ranges):
            if start < 0:
                start, end = current_start, current_end
            elif current_start <= end:
                end = max(end, current_end)
            else:
                total += end - start
                start, end = current_start, current_end
        if start >= 0:
            total += end - start
    return total


def _assert_shared_packet(repo: Path, response, payload: dict, output_limit: int) -> None:
    """Verify source truth, atomic paths, deduplication, and both byte accounts."""

    LociExploreOutput.model_validate(payload)
    encoded = CallToolResult(
        content=response.content,
        structured_content=payload,
        is_error=response.is_error,
    ).model_dump_json(by_alias=True, exclude_unset=True).encode("utf-8")
    assert len(encoded) == payload["usage"]["output_bytes"]
    assert len(encoded) <= output_limit
    assert payload["usage"]["evidence_bytes"] == _interval_bytes(payload)
    assert payload["usage"]["evidence_bytes"] <= payload["limits"]["max_evidence_bytes"]

    sources = _source_by_id(payload)
    assert len(sources) == len(payload["sources"])
    assert len({
        (source["file"], source["content_hash"], source["start_byte"], source["end_byte"])
        for source in payload["sources"]
    }) == len(payload["sources"])
    for source in sources.values():
        raw = (repo / source["file"]).read_bytes()
        assert source["content_hash"] == hashlib.sha256(raw).hexdigest()
        assert source["content"].encode("utf-8") == raw[
            source["start_byte"]:source["end_byte"]
        ]

    items = {item["id"]: item for item in payload["items"]}
    assert len(items) == len(payload["items"])
    relations = {relation["id"]: relation for relation in payload["relationships"]}
    assert len(relations) == len(payload["relationships"])
    for item in items.values():
        assert item["source_id"] in sources
        assert item["depth"] == len(item["path"])
        assert all(relation_id in relations for relation_id in item["path"])
        if item["path"]:
            relation = relations[item["path"][-1]]
            endpoint = "to" if relation["traversed"] == "forward" else "from"
            assert relation["edge"][endpoint] == item["id"]
    for relation in relations.values():
        assert relation["edge"]["from"] in items
        assert relation["edge"]["to"] in items
        assert relation["source_ids"]
        assert len(relation["source_ids"]) == len(set(relation["source_ids"]))
        assert all(source_id in sources for source_id in relation["source_ids"])


def test_multilingual_context_packets_cross_one_stdio_host(tmp_path: Path) -> None:
    """One repository exercises all five source languages and frozen controls.

    The established language suites retain the exhaustive language facts.  This
    uses their isolated snapshots under separate directories to prove the shared
    host never crosses language/source roots, while TSX and Markdown retain the
    two W4.6 regression controls.
    """
    corpus = load_corpus(CORPUS_ROOT)
    repo = tmp_path / "multilingual"
    repo.mkdir()
    snapshots = {
        "python": "python_contracts",
        "javascript": "javascript_dependencies",
        "go": "go_contracts",
        "rust": "rust_contracts",
        "tsx": "tsx_props",
        "markdown": "markdown_navigation",
    }
    for directory, snapshot in snapshots.items():
        materialize_snapshot(corpus, snapshot, repo / directory)

    async def check() -> None:
        async with Client(stdio_client(_server_params(repo, tmp_path / "cache"))) as session:
            tsx_search = await session.call_tool(
                "loci_search",
                {
                    "repo": str(repo), "query": "Badge", "lang": "typescript",
                    "file_paths": ["tsx/badge.tsx"],
                },
            )
            assert not tsx_search.is_error
            tsx_seed = next(
                symbol["id"]
                for symbol in tsx_search.structured_content["symbols"]
                if symbol["name"] == "Badge" and symbol["kind"] == "function"
            )
            tsx_get = await session.call_tool(
                "loci_get",
                {
                    "repo": str(repo), "symbol_ids": [tsx_seed],
                    "selected_from_search_id": tsx_search.structured_content["search_id"],
                    "include_type_context": True,
                },
            )
            assert not tsx_get.is_error
            assert tsx_get.structured_content["symbols"][0]["source"] == (
                'function Badge(props: Props) { return <span>{props.label}</span>; }'
            )
            assert {
                symbol["id"] for symbol in tsx_get.structured_content["type_context"]["symbols"]
            } == {"tsx/props.ts::Props#interface"}

            markdown_search = await session.call_tool(
                "loci_search",
                {
                    "repo": str(repo), "query": "Limits", "lang": "markdown",
                    "file_paths": ["markdown/guide.md"],
                },
            )
            assert not markdown_search.is_error
            markdown_seed = next(
                symbol["id"]
                for symbol in markdown_search.structured_content["symbols"]
                if symbol["name"] == "Limits" and symbol["kind"] == "section"
            )
            markdown_get = await session.call_tool(
                "loci_get",
                {
                    "repo": str(repo), "symbol_ids": [markdown_seed],
                    "selected_from_search_id": markdown_search.structured_content["search_id"],
                },
            )
            assert not markdown_get.is_error
            assert markdown_get.structured_content["symbols"][0]["source"] == (
                "## Limits\n\nBudget: 8,192 UTF-8 bytes; café remains intact.\n\n"
                "### Omissions\n\nReport missing evidence explicitly.\n\n"
            )

            checks = [
                ("locate", "python/consumer.py::decode#function", {"python/consumer.py::decode#function"}),
                ("locate", "javascript/app.js::run#function", {"javascript/app.js::run#function"}),
                ("locate", "go/app/main.go::Build#function", {"go/app/main.go::Build#function"}),
                ("locate", "rust/src/lib.rs::build#function", {"rust/src/lib.rs::build#function"}),
                ("type_dependencies", tsx_seed, {tsx_seed, "tsx/props.ts::Props#interface"}),
                ("locate", markdown_seed, {markdown_seed}),
            ]
            for intent, seed_id, expected_ids in checks:
                response = await session.call_tool(
                    "loci_explore",
                    {
                        "repo": str(repo), "intent": intent, "seed_ids": [seed_id],
                        "max_hops": 3, "max_evidence_bytes": 8192, "max_output_bytes": 16384,
                    },
                )
                assert not response.is_error
                payload = response.structured_content
                assert expected_ids <= {item["id"] for item in payload["items"]}
                _assert_shared_packet(repo, response, payload, 16384)

                # Delivered definitions must agree with the public exact-read endpoint.
                if seed_id == tsx_seed:
                    expected_sources = {
                        tsx_seed: tsx_get.structured_content["symbols"][0]["source"],
                        "tsx/props.ts::Props#interface": tsx_get.structured_content[
                            "type_context"
                        ]["symbols"][0]["source"],
                    }
                elif seed_id == markdown_seed:
                    expected_sources = {
                        markdown_seed: markdown_get.structured_content["symbols"][0]["source"]
                    }
                else:
                    exact = await session.call_tool(
                        "loci_get", {"repo": str(repo), "symbol_ids": sorted(expected_ids)},
                    )
                    assert not exact.is_error
                    expected_sources = {
                        symbol["id"]: symbol["source"]
                        for symbol in exact.structured_content["symbols"]
                    }
                delivered = _source_by_id(payload)
                for item_id in expected_ids:
                    source_id = next(
                        item["source_id"]
                        for item in payload["items"]
                        if item["id"] == item_id
                    )
                    assert delivered[source_id]["content"] == expected_sources[item_id]

    asyncio.run(check())


def test_multilingual_context_bounds_cycles_and_hops_over_stdio(tmp_path: Path) -> None:
    repo = tmp_path / "cycle"
    repo.mkdir()
    (repo / "cycle.ts").write_text(
        "interface Alpha extends Beta {}\n"
        "interface Beta extends Alpha {}\n"
        "function consume(value: Alpha): void {}\n",
        encoding="utf-8",
    )

    async def check() -> None:
        async with Client(stdio_client(_server_params(repo, tmp_path / "cache"))) as session:
            response = await session.call_tool(
                "loci_explore",
                {
                    "repo": str(repo), "intent": "type_dependencies",
                    "seed_ids": ["cycle.ts::consume#function"], "max_hops": 2,
                },
            )
            assert not response.is_error
            payload = response.structured_content
            _assert_shared_packet(repo, response, payload, 16384)
            assert {item["id"] for item in payload["items"]} == {
                "cycle.ts::consume#function", "cycle.ts::Alpha#interface", "cycle.ts::Beta#interface",
            }
            assert all(item["depth"] <= 2 for item in payload["items"])
            assert any(omission["reason"] == "cycle" for omission in payload["omissions"])

            zero = await session.call_tool(
                "loci_explore",
                {
                    "repo": str(repo), "intent": "type_dependencies",
                    "seed_ids": ["cycle.ts::consume#function"], "max_evidence_bytes": 0,
                    "max_output_bytes": 2048,
                },
            )
            assert not zero.is_error
            assert zero.structured_content["status"] == "empty"
            assert not zero.structured_content["items"]
            _assert_shared_packet(repo, zero, zero.structured_content, 2048)

    asyncio.run(check())


def test_multilingual_context_isolates_same_names_and_refreshes_source_and_config(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "mixed"
    repo.mkdir()
    (repo / "same.py").write_text(
        "class Request:\n    value: str\n\n"
        "def shared(value: Request) -> Request:\n    return value\n",
        encoding="utf-8",
    )
    (repo / "same.ts").write_text(
        "interface Request { value: string; }\n"
        "function shared(value: Request): Request { return value; }\n",
        encoding="utf-8",
    )
    (repo / "go.mod").write_text("module example.com/acme\ngo 1.22\n", encoding="utf-8")
    (repo / "model").mkdir()
    (repo / "model" / "model.go").write_text("package model\ntype Request struct{}\n", encoding="utf-8")
    (repo / "app").mkdir()
    (repo / "app" / "main.go").write_text(
        "package app\nimport \"example.com/acme/model\"\nfunc Keep(value model.Request) {}\n",
        encoding="utf-8",
    )

    async def check() -> None:
        async with Client(stdio_client(_server_params(repo, tmp_path / "cache"))) as session:
            python = await session.call_tool(
                "loci_explore", {"repo": str(repo), "intent": "locate", "seed_ids": ["same.py::shared#function"]},
            )
            typescript = await session.call_tool(
                "loci_explore", {"repo": str(repo), "intent": "locate", "seed_ids": ["same.ts::shared#function"]},
            )
            assert not python.is_error and not typescript.is_error
            _assert_shared_packet(repo, python, python.structured_content, 16384)
            _assert_shared_packet(repo, typescript, typescript.structured_content, 16384)
            assert python.structured_content["items"][0]["file"] == "same.py"
            assert typescript.structured_content["items"][0]["file"] == "same.ts"

            python_types = await session.call_tool(
                "loci_explore",
                {"repo": str(repo), "intent": "type_dependencies", "seed_ids": ["same.py::shared#function"]},
            )
            typescript_types = await session.call_tool(
                "loci_explore",
                {"repo": str(repo), "intent": "type_dependencies", "seed_ids": ["same.ts::shared#function"]},
            )
            assert not python_types.is_error and not typescript_types.is_error
            _assert_shared_packet(repo, python_types, python_types.structured_content, 16384)
            _assert_shared_packet(repo, typescript_types, typescript_types.structured_content, 16384)
            assert {item["id"] for item in python_types.structured_content["items"]} == {
                "same.py::shared#function", "same.py::Request#class",
            }
            assert {item["id"] for item in typescript_types.structured_content["items"]} == {
                "same.ts::shared#function", "same.ts::Request#interface",
            }

            before = await session.call_tool(
                "loci_explore",
                {"repo": str(repo), "intent": "type_dependencies", "seed_ids": ["app/main.go::Keep#function"]},
            )
            assert not before.is_error
            _assert_shared_packet(repo, before, before.structured_content, 16384)
            assert "model/model.go::Request#type" in {item["id"] for item in before.structured_content["items"]}

            (repo / "same.py").write_text(
                "def shared(value: Request) -> Request:\n    return value\n",
                encoding="utf-8",
            )
            missing_python = await session.call_tool(
                "loci_explore",
                {"repo": str(repo), "intent": "type_dependencies", "seed_ids": ["same.py::shared#function"]},
            )
            assert not missing_python.is_error
            _assert_shared_packet(repo, missing_python, missing_python.structured_content, 16384)
            assert {item["id"] for item in missing_python.structured_content["items"]} == {
                "same.py::shared#function"
            }
            assert "same.ts::Request#interface" not in {
                item["id"] for item in missing_python.structured_content["items"]
            }
            assert any(
                omission["reason"] == "unresolved_relation"
                for omission in missing_python.structured_content["omissions"]
            )

            (repo / "same.ts").write_text(
                "interface Request { value: string; }\n"
                "function shared(value: Request): Request { return 'refreshed' as Request; }\n",
                encoding="utf-8",
            )
            (repo / "go.mod").write_text("module example.com/other\ngo 1.22\n", encoding="utf-8")
            refreshed = await session.call_tool(
                "loci_explore", {"repo": str(repo), "intent": "locate", "seed_ids": ["same.ts::shared#function"]},
            )
            invalidated = await session.call_tool(
                "loci_explore",
                {"repo": str(repo), "intent": "type_dependencies", "seed_ids": ["app/main.go::Keep#function"]},
            )
            assert not refreshed.is_error and not invalidated.is_error
            _assert_shared_packet(repo, refreshed, refreshed.structured_content, 16384)
            _assert_shared_packet(repo, invalidated, invalidated.structured_content, 16384)
            assert "refreshed" in _source_by_id(refreshed.structured_content)[refreshed.structured_content["items"][0]["source_id"]]["content"]
            assert {
                "model/model.go::Request#type", "same.py::Request#class", "same.ts::Request#interface",
            }.isdisjoint({item["id"] for item in invalidated.structured_content["items"]})
            assert any(omission["reason"] == "unresolved_relation" for omission in invalidated.structured_content["omissions"])

    asyncio.run(check())
