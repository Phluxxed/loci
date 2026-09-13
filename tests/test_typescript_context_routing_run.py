"""Keep shared capability and per-condition identity correct in the real adapter."""
import copy
import json
from pathlib import Path

import pytest

from benchmarks.typescript_context_corpus import _isolated_store, load_corpus, materialize_snapshot
from benchmarks.typescript_context_routing_observed import reconcile_observed, replay_trace
from benchmarks.typescript_context_routing import ROOT
from benchmarks.typescript_context_routing_tools import RoutingAdapter
from loci import service


@pytest.mark.parametrize("arm", ["A", "B"])
def test_both_conditions_deliver_exploration_with_their_own_trace_identity(tmp_path, arm):
    corpus = load_corpus(ROOT / "benchmarks/corpora/typescript-context-v3")
    repo = tmp_path / "snapshot"
    materialize_snapshot(corpus, "imported_interface", repo)
    run = {"repo": str(repo), "corpus_root": corpus["_root"], "case_id": "imported_interface",
           "session_id": f"routing-{arm}", "arm": arm, "repetition": 1,
           "trace_path": str(tmp_path / "trace.json")}
    before = copy.deepcopy(run)
    with _isolated_store(tmp_path / "store"):
        service.index_repo(repo, incremental=False)
        adapter = RoutingAdapter(run)
        args = {"intent": "type_dependencies", "query": "processOrder"}
        result = adapter.read_operation("loci_explore", args)
        assert result.structured_content is not None
        assert result.structured_content["status"] == "ok"
        assert any(item["name"] == "Payload" for item in result.structured_content["items"])
        raw = json.loads(Path(run["trace_path"]).read_text())
        assert raw["identity"]["arm"] == arm
        assert all(event["arm"] == arm for event in raw["events"])
        assert replay_trace(corpus, raw).identity["arm"] == arm
        terminal = {
            "id": "item_1", "type": "mcp_tool_call", "server": "evaluation",
            "tool": "loci_explore", "arguments": args, "status": "completed", "error": None,
            "result": {"content": [], "structured_content": result.structured_content},
        }
        started = {**terminal, "status": "in_progress", "result": None}
        events = [{"type": "item.started", "item": started},
                  {"type": "item.completed", "item": terminal}]
        accounting = reconcile_observed(raw, events)
        assert accounting["complete"], accounting["failures"]
        exact = adapter.read_operation("get", {"symbol_ids": ["consumer.ts::processOrder#function"]})
        assert exact.structured_content is not None
        assert "type_context" not in exact.structured_content
    assert run == before
