from __future__ import annotations

import asyncio
import copy
from dataclasses import FrozenInstanceError
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from loci import retrieval, service
from loci._retrieval_output import LIMITS
from loci.mcp_output_models import LociRetrieveOutput


@pytest.fixture
def indexed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    repo = tmp_path / "repo"
    repo.mkdir()
    files = {
        "types.py": "class Payload:\n    pass\n",
        "worker.py": (
            "from types import Payload\n\n"
            "def leaf():\n    return '§§§'\n\n"
            "def root(value: Payload):\n    return leaf()\n\n"
            "def unrelated():\n    return 42\n"
        ),
        "entry.py": "from worker import root\n\ndef caller():\n    return root(None)\n",
        "large.py": (
            "def large():\n"
            + "".join(f"    value_{index} = {index}\n" for index in range(100))
            + "    return value_99\n"
        ),
    }
    for name, content in files.items():
        (repo / name).write_text(content, encoding="utf-8")
    monkeypatch.setenv("LOCI_BASE_DIR", str(tmp_path / "store"))
    service.index_repo(repo, incremental=False)
    return repo


# Full graph-on packet fingerprints captured from production at 0ed601c, before
# the refactor. Only repo-bound source_ref values are normalized; budgets, usage,
# selection metadata, ordering, source extents/content and proofs are included.
@pytest.mark.parametrize(("query", "seed_ids", "graph_on_fingerprint"), [
    ("root", None, "fc149f269f6f445854414259e6cce491b0e198a78d23df54706b8dd0fd72a867"),
    ("worker.py", None, "c658ee5306dad3686c0319681016ff3fe4b9c83de16d6f1a09d083250e677ff7"),
    ("§§§", None, "2dc8cf8f5c6bc257929c6f74c62944b19b2c5c2a968f839d0425f95a912090a2"),
    ("no-matching-source-§§§", None,
     "d71f67a7f863303e7bd8dcc9bc0051bd055edf3904756572fcc8afe1faa580ae"),
    ("", ["worker.py::root#function", "worker.py::leaf#function"],
     "0a002ed6c086f1c482b08f719cfe47fdf1d0959c534e3211e491e6ff0dbdca28"),
    ("large", None, "98ede841bbf91031d9e3f71eddad9c3ec2edbe1253073fc3fcc53abe9204916d"),
])
def test_modes_share_preparation_and_identical_baseline(
    indexed: Path, monkeypatch: pytest.MonkeyPatch, query: str, seed_ids: list[str] | None,
    graph_on_fingerprint: str,
):
    prepare = Mock(wraps=retrieval._prepare_context)
    load = Mock(wraps=service._load_graph_context)
    coverage = Mock(wraps=service.query_coverage_from_index)
    anchor_addition = Mock(wraps=retrieval._anchor_addition)
    monkeypatch.setattr(retrieval, "_prepare_context", prepare)
    monkeypatch.setattr(service, "_load_graph_context", load)
    monkeypatch.setattr(service, "query_coverage_from_index", coverage)
    monkeypatch.setattr(retrieval, "_anchor_addition", anchor_addition)
    pack = retrieval._pack_anchor_sources
    baselines = []
    prepared_requests = []

    def capture_baseline(prepared, nodes):
        first_addition = anchor_addition.call_count
        visits = pack(prepared, nodes)
        assert all(
            call.args[0] is prepared.source
            for call in anchor_addition.call_args_list[first_addition:]
        )
        prepared_requests.append(prepared)
        packer = prepared.packer
        baselines.append(copy.deepcopy((
            packer.state, packer.snapshots, packer.usage, packer.omissions,
            packer.anchors, packer.selection, packer.scope, packer.snapshot, visits,
        )))
        return visits

    monkeypatch.setattr(retrieval, "_pack_anchor_sources", capture_baseline)
    default = service.retrieve(indexed, query, seed_ids=seed_ids)
    enabled = service.retrieve(indexed, query, seed_ids=seed_ids, graph_enrichment=True)
    disabled = service.retrieve(indexed, query, seed_ids=seed_ids, graph_enrichment=False)

    assert default == enabled
    normalized = copy.deepcopy(default)
    for item in (*normalized["items"], *normalized["sources"]):
        item["source_ref"] = "<source-ref>"
    encoded = json.dumps(normalized, ensure_ascii=False, sort_keys=True,
                         separators=(",", ":")).encode("utf-8")
    assert hashlib.sha256(encoded).hexdigest() == graph_on_fingerprint
    assert len(baselines) == prepare.call_count == load.call_count == coverage.call_count == 3
    assert baselines[0] == baselines[1] == baselines[2]
    assert load.call_args_list == [load.call_args_list[0]] * 3
    assert coverage.call_args_list == [coverage.call_args_list[0]] * 3
    preparation_inputs = [
        (call.args[0], call.args[1].source_reference_path(indexed), call.args[2:], call.kwargs)
        for call in prepare.call_args_list
    ]
    assert preparation_inputs == [preparation_inputs[0]] * 3
    assert all(isinstance(prepared.source, retrieval.RetrievalSource)
               for prepared in prepared_requests)

    baseline_state = baselines[0][0]
    assert disabled["nodes"] == [baseline_state.nodes[key] for key in baseline_state.node_order]
    assert disabled["items"] == baseline_state.items
    assert disabled["ownership"] == baseline_state.ownership
    assert disabled["relationships"] == baseline_state.relationships == []
    assert disabled["omissions"] == [
        {"reason": reason, "count": count} for reason, count in baselines[0][3].items()
    ]
    assert disabled.keys() == default.keys()
    for key in ("anchors", "selection", "snapshot", "limits", "policy", "schema_version"):
        assert disabled[key] == default[key]
    assert disabled["scope"] == default["scope"]
    assert default["scope"]["relationships"] == "known_static_relationships"
    assert disabled["items"] == [item for item in default["items"] if item["role"] == "anchor"]
    assert disabled["sources"] == default["sources"][:len(disabled["sources"])]
    assert disabled["limits"] == LIMITS
    assert disabled["usage"]["nodes_examined"] == len(disabled["anchors"])
    assert disabled["usage"]["eligible_edges_considered"] == 0
    assert disabled["usage"]["edges_traversed"] == 0
    assert disabled["usage"]["relationships_delivered"] == 0
    envelope = {"content": [], "structuredContent": disabled, "isError": False}
    assert disabled["usage"]["output_bytes"] == len(json.dumps(
        envelope, ensure_ascii=False, separators=(",", ":"),
    ).encode("utf-8"))
    LociRetrieveOutput.model_validate(default)
    LociRetrieveOutput.model_validate(disabled)


@pytest.mark.parametrize("enabled", [True, False])
def test_runtime_retains_trusted_configuration_and_delegates(
    indexed: Path, monkeypatch: pytest.MonkeyPatch, enabled: bool,
):
    runtime = service.RetrievalRuntime(graph_enrichment=enabled)
    assert service.RetrievalRuntime().graph_enrichment is True
    assert runtime.graph_enrichment is enabled
    with pytest.raises(FrozenInstanceError):
        runtime.graph_enrichment = not enabled
    delegate = Mock(wraps=service.retrieve)
    monkeypatch.setattr(service, "retrieve", delegate)
    seeds = ["worker.py::root#function"]
    result = runtime.retrieve(indexed, "root", seed_ids=seeds, ensure_fresh=True)
    delegate.assert_called_once_with(
        indexed, "root", seed_ids=seeds, ensure_fresh=True, graph_enrichment=enabled,
    )
    assert "graph_enrichment" not in result
    with pytest.raises(TypeError, match="graph_enrichment"):
        runtime.retrieve(indexed, "root", graph_enrichment=not enabled)


def test_internal_state_is_distinct_even_when_visible_packets_are_identical(indexed: Path):
    enabled = service.RetrievalRuntime()
    disabled = service.RetrievalRuntime(graph_enrichment=False)
    # No anchors: enabled does not traverse either. Counts cannot identify the
    # configured arm, and the complete model-visible packets must be identical.
    query = "no-matching-source-§§§"
    on = enabled.retrieve(indexed, query)
    off = disabled.retrieve(indexed, query)
    assert on == off
    assert on["relationships"] == []
    assert on["scope"]["relationships"] == "known_static_relationships"
    assert on["scope"]["exhaustive"] is False
    assert enabled.graph_enrichment is True
    assert disabled.graph_enrichment is False


@pytest.mark.parametrize("enabled", [True, False])
@pytest.mark.parametrize("query", ["root", "no-matching-source-§§§"])
def test_exact_mcp_envelope_contains_only_packet_not_runtime_state(
    indexed: Path, monkeypatch: pytest.MonkeyPatch, enabled: bool, query: str,
):
    from loci import mcp_server

    runtime = service.RetrievalRuntime(graph_enrichment=enabled)
    packets = []

    def bound_retrieve(*args, **kwargs):
        packet = runtime.retrieve(*args, **kwargs)
        packets.append(copy.deepcopy(packet))
        return packet

    # Trusted adapter binds the runtime; no request field selects the arm.
    monkeypatch.setattr(mcp_server, "_service_module", SimpleNamespace(
        retrieve=bound_retrieve, LociError=service.LociError,
    ))
    server = mcp_server.create_server("normal")
    tools = asyncio.run(server.list_tools())
    tool = next(tool for tool in tools if tool.name == "loci_retrieve")
    assert set(tool.input_schema["properties"]) == {"repo", "query", "seed_ids"}
    result = asyncio.run(server.call_tool(
        "loci_retrieve", {"repo": str(indexed), "query": query},
    ))
    assert len(packets) == 1
    packet = packets[0]
    envelope = result.model_dump(by_alias=True, exclude_none=True)
    packet_envelope = {"content": [], "structuredContent": packet, "isError": False}
    assert envelope == {"resultType": "complete", **packet_envelope}
    wire = json.dumps(envelope, ensure_ascii=False, separators=(",", ":"))
    for marker in ("disabled", "graph_enrichment", "graph_off", "graph_on",
                   '"arm"', '"runtime"', '"receipt"'):
        assert marker not in wire.lower()
    assert runtime.graph_enrichment is enabled
    assert packet["scope"]["relationships"] == "known_static_relationships"
    # Preserve the packer's existing accounting envelope (the SDK transport
    # discriminator is not part of that production budget contract).
    accounted = json.dumps(packet_envelope, ensure_ascii=False, separators=(",", ":"))
    assert packet["usage"]["output_bytes"] == len(accounted.encode("utf-8"))
    assert packet["usage"]["output_bytes"] <= packet["limits"]["max_output_bytes"]
    if query == "root":
        assert bool(packet["relationships"]) is enabled
    LociRetrieveOutput.model_validate(packet)


def test_graph_off_never_enters_enrichment(
    indexed: Path, monkeypatch: pytest.MonkeyPatch,
):
    def forbidden(*args, **kwargs):
        pytest.fail("graph-off entered enrichment")

    for name in (
        "_eligible_edges", "graph_adjacency", "_traverse_relationships",
        "_selected_anchor_type_bridges", "_selected_signature_type_paths",
        "_ownership_lifts", "_count_unresolved",
    ):
        monkeypatch.setattr(retrieval, name, forbidden)
    monkeypatch.setattr(retrieval.RetrievalSource, "proof", forbidden)
    monkeypatch.setattr(retrieval.RetrievalSource, "endpoint_members", forbidden)
    # Both service entry and direct retrieval use the production baseline.
    result = service.retrieve(indexed, "root", graph_enrichment=False)
    store, nodes, state = service._load_graph_context(indexed, ensure_fresh=False)
    direct = retrieval.retrieve_context(
        indexed, store, nodes, state, "root", graph_enrichment=False,
        coverage=result["scope"]["coverage"],
    )
    assert direct == result
    assert result["ownership"] == [{
        "owner_id": "worker.py::__file__#file",
        "member_id": "worker.py::root#function",
        "basis": "indexed_file",
    }]
    assert {node["id"] for node in result["nodes"]} == {
        "worker.py::root#function", "worker.py::__file__#file",
    }
    assert {item["node_id"] for item in result["items"]} == {"worker.py::root#function"}
    file_result = service.retrieve(indexed, "worker.py", graph_enrichment=False)
    assert len(file_result["items"]) == 1
    assert file_result["items"][0]["node_id"] == "worker.py::__file__#file"
    assert file_result["ownership"] == []


def test_production_retrieval_does_not_depend_on_benchmarks(indexed: Path):
    # Start clean so a cached/top-level benchmark import cannot evade the guard.
    script = """
import importlib.abc
import sys

class NoBenchmarks(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname == 'benchmarks' or fullname.startswith('benchmarks.'):
            raise AssertionError('Production retrieval imported benchmark code')

sys.meta_path.insert(0, NoBenchmarks())
from loci import service

for enabled in (True, False):
    runtime = service.RetrievalRuntime(graph_enrichment=enabled)
    result = runtime.retrieve(sys.argv[1], 'root')
    assert runtime.graph_enrichment is enabled
    assert result['anchors']
    assert bool(result['relationships']) is enabled
"""
    result = subprocess.run(
        [sys.executable, "-c", script, str(indexed)],
        capture_output=True, text=True, timeout=15,
    )
    assert result.returncode == 0, result.stderr


def test_default_direct_retrieval_enriches_relationships_and_ownership(indexed: Path):
    store, nodes, state = service._load_graph_context(indexed, ensure_fresh=False)
    default = retrieval.retrieve_context(indexed, store, nodes, state, "root")
    enabled = retrieval.retrieve_context(indexed, store, nodes, state, "root", graph_enrichment=True)
    assert default == enabled
    assert default["policy"] == "normal-graph-v1"
    assert default["scope"]["relationships"] == "known_static_relationships"
    assert default["usage"]["edges_traversed"] > 0
    assert any(relation["edge"]["type"] == "calls" for relation in default["relationships"])
    file_result = service.retrieve(indexed, "worker.py")
    assert any(item["role"] == "related" for item in file_result["items"])


def test_graph_off_preserves_preview_and_readable_source_refs(indexed: Path):
    enabled = service.retrieve(indexed, "large")
    disabled = service.retrieve(indexed, "large", graph_enrichment=False)
    assert disabled["items"] == enabled["items"]
    item = disabled["items"][0]
    assert item["complete"] is False
    assert item["source_ref"].startswith("sr1_")
    expanded = service.read(indexed, item["source_ref"])
    assert expanded["complete"] is True
    extent = item["extent"]
    expected = (indexed / extent["file"]).read_bytes()[extent["start_byte"]:extent["end_byte"]]
    assert expanded["source"]["content"] == expected.decode("utf-8")
    preview = disabled["sources"][0]
    assert service.read(indexed, preview["source_ref"])["source"]["content"] == preview["content"]


@pytest.mark.parametrize("arguments", [
    {},
    {"query": "é" * 2049},
    {"query": 42},
    {"seed_ids": ["worker.py::root#function"] * 2},
    {"seed_ids": ["not-indexed"]},
    {"seed_ids": "worker.py::root#function"},
])
def test_both_modes_share_request_validation(indexed: Path, arguments: dict):
    errors = []
    for enabled in (True, False):
        with pytest.raises(service.LociError) as error:
            service.retrieve(indexed, **arguments, graph_enrichment=enabled)
        errors.append((error.value.code, error.value.message, error.value.details))
    assert errors[0] == errors[1]
