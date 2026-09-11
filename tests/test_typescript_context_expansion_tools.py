from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from benchmarks.typescript_context_corpus import _isolated_store, load_corpus, materialize_snapshot
from benchmarks.typescript_context_expansion_tools import ExpansionAdapter, relationship_payloads
from benchmarks.typescript_context_observed import replay_trace
from benchmarks.typescript_context_relationships import _delivered_edges
from benchmarks.typescript_context_tools_v3 import ObservedAdapter, create_server
from loci import service


CORPUS_ROOT = Path(__file__).parents[1] / "benchmarks/corpora/typescript-context-v3"


@pytest.fixture
def adapters(tmp_path):
    corpus = load_corpus(CORPUS_ROOT)
    repo = tmp_path / "snapshot"
    materialize_snapshot(corpus, "imported_interface", repo)
    with _isolated_store(tmp_path / "store"):
        service.index_repo(repo, incremental=False)
        pair = []
        for arm in ("A", "B"):
            run = {"repo": str(repo), "corpus_root": str(CORPUS_ROOT), "case_id": "imported_interface",
                   "session_id": "matched-adapter-" + arm, "arm": arm, "repetition": 1,
                   "trace_path": str(tmp_path / f"trace-{arm}.json")}
            pair.append(ExpansionAdapter(run))
        yield corpus, pair


def test_b_definition_and_support_are_charged_and_replay_exactly(adapters):
    corpus, (a, b) = adapters
    parameters = {"symbol_ids": ["consumer.ts::processOrder#function"]}
    exact = a.read_operation("get", parameters).structured_content
    expanded = b.read_operation("get", parameters).structured_content
    assert exact["symbols"] == expanded["symbols"]
    assert "type_context" not in exact
    assert [item["id"] for item in expanded["type_context"]["symbols"]] == ["types.ts::Payload#interface"]
    expected = []
    for adapter in (a, b):
        raw = json.loads(Path(adapter.run["trace_path"]).read_text())
        trace = replay_trace(corpus, raw)
        assert not raw["failures"]
        assert len(trace.events) == 1
        delivery = raw["deliveries"][0]
        texts = [span["text"] for span in trace.events[0]["spans"]]
        assert delivery["source_bytes"] == sum(len(text.encode()) for text in texts)
        assert delivery["serialized_bytes"] == len(delivery["response_json"].encode())
        expected.append((delivery["source_bytes"], delivery["serialized_bytes"]))
    assert expected[1][0] > expected[0][0]
    assert expected[1][1] > expected[0][1]
    assert expanded["type_context"]["symbols"][0]["source"] in texts
    assert any(text.startswith("import type") for text in texts)


def test_ab_tool_schemas_and_exact_a_dispatch_are_unchanged(adapters):
    _, (a, b) = adapters
    old = ObservedAdapter(a.run)
    parameters = {"symbol_ids": ["consumer.ts::processOrder#function"], "context": 0}
    assert a.dispatch("get", parameters) == old.dispatch("get", parameters)
    schemas = [asyncio.run(create_server(adapter).list_tools()) for adapter in (old, a, b)]
    assert schemas[0] == schemas[1] == schemas[2]


def test_relationship_normalization_preserves_actual_edge_identity(adapters):
    _, (_, b) = adapters
    result = b.read_operation("get", {"symbol_ids": ["consumer.ts::processOrder#function"]}).structured_content
    edge = result["type_context"]["references"][0]["edge"]
    assert _delivered_edges(relationship_payloads([result])) == [edge]
    assert edge["from"] == "consumer.ts::__file__#file"
    assert "owner_id" not in edge
