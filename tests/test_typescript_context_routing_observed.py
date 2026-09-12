from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from typing import Any

import pytest

from benchmarks.typescript_context_adapter import wire
from benchmarks.typescript_context_corpus import _isolated_store, load_corpus, materialize_snapshot
from benchmarks.typescript_context_explore_v2_observed import measure as v2_measure
from benchmarks.typescript_context_explore_tools import ExploreAdapter
from benchmarks.typescript_context_routing_observed import (
    VERSION,
    measure,
    observe_routing,
    reconcile_observed,
    replay_trace,
)
from loci import service


CORPUS_ROOT = Path(__file__).parents[1] / "benchmarks" / "corpora" / "typescript-context-v3"


def _lifecycle(call: dict[str, Any]) -> list[dict[str, Any]]:
    started = {
        key: copy.deepcopy(call[key])
        for key in ("id", "type", "server", "tool", "arguments")
    }
    return [
        {"type": "item.started", "item": started},
        {"type": "item.completed", "item": copy.deepcopy(call)},
    ]


def _events(
    calls: list[dict[str, Any]],
    *,
    answer: dict[str, Any] | None = None,
    usage: dict[str, int] | None = None,
) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = [{"type": "thread.started", "thread_id": "routing-test-thread"}]
    for call in calls:
        events.extend(_lifecycle(call))
    events.append(
        {
            "type": "item.completed",
            "item": {"id": "answer", "type": "agent_message", "text": json.dumps(answer or {})},
        }
    )
    if usage is not None:
        events.append({"type": "turn.completed", "usage": copy.deepcopy(usage)})
    return events


def _call(
    item_id: str,
    tool: str,
    arguments: dict[str, Any],
    payload: dict[str, Any] | None,
    *,
    status: str = "completed",
) -> dict[str, Any]:
    return {
        "id": item_id,
        "type": "mcp_tool_call",
        "server": "evaluation",
        "tool": tool,
        "arguments": copy.deepcopy(arguments),
        "status": status,
        "error": None,
        "result": (
            {"content": [], "structured_content": copy.deepcopy(payload)}
            if payload is not None
            else None
        ),
    }


def _helper(item_id: str) -> dict[str, Any]:
    return {
        "id": item_id,
        "type": "mcp_tool_call",
        "server": "codex",
        "tool": "list_mcp_resources",
        "arguments": {"server": "codex"},
        "status": "completed",
        "error": None,
        "result": {
            "structured_content": None,
            "content": [{"type": "text", "text": '{"resources":[],"server":"codex"}'}],
        },
    }


def _fixture(
    tmp_path: Path,
    *,
    arm: str = "B",
    case_id: str = "imported_interface",
    intent: str = "type_dependencies",
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any], ExploreAdapter]:
    corpus = load_corpus(CORPUS_ROOT)
    case = next(case for case in corpus["cases"] if case["id"] == case_id)
    repo = tmp_path / "snapshot"
    materialize_snapshot(corpus, case["snapshot"], repo)
    trace_path = tmp_path / "trace.json"
    run = {
        "repo": str(repo),
        "corpus_root": str(CORPUS_ROOT),
        "case_id": case_id,
        "session_id": "routing-observed",
        "arm": arm,
        "repetition": 1,
        "trace_path": str(trace_path),
    }
    with _isolated_store(tmp_path / "store"):
        service.index_repo(repo, incremental=False)
        adapter = ExploreAdapter(run)
        result = adapter.read_operation("loci_explore", {"intent": intent, "query": "processOrder"})
    payload = result.structured_content
    assert isinstance(payload, dict)
    raw = json.loads(trace_path.read_text(encoding="utf-8"))
    arguments = copy.deepcopy(adapter.deliveries[0]["arguments"])
    call = _call("explore-call", "loci_explore", arguments, payload)
    return corpus, case, run, raw, payload, adapter


def _rewrite_explore(raw: dict[str, Any], payload: dict[str, Any], *, spans: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    rewritten = copy.deepcopy(raw)
    response = wire(payload)
    event = rewritten["events"][0]
    delivery = rewritten["deliveries"][0]
    effective_spans = copy.deepcopy(event["spans"]) if spans is None else spans
    event.update(
        response_json=response,
        serialized_bytes=len(response.encode("utf-8")),
        source_bytes=sum(span["end_byte"] - span["start_byte"] for span in effective_spans),
        spans=copy.deepcopy(effective_spans),
    )
    delivery.update(
        response_json=response,
        serialized_bytes=len(response.encode("utf-8")),
        source_bytes=sum(span["end_byte"] - span["start_byte"] for span in effective_spans),
        spans=copy.deepcopy(effective_spans),
    )
    return rewritten


def _maintained(case: dict[str, Any]) -> dict[str, Any]:
    value = copy.deepcopy(case)
    value["group"] = "maintained_task"
    return value


def test_success_and_helper_before_explore_are_observed_from_actual_adapter(tmp_path: Path) -> None:
    corpus, case, _run, raw, payload, adapter = _fixture(tmp_path)
    arguments = copy.deepcopy(adapter.deliveries[0]["arguments"])
    call = _call("explore-call", "loci_explore", arguments, payload)
    observed = observe_routing(corpus, _maintained(case), raw, _events([_helper("helper"), call]))

    assert observed["observations_complete"] is True
    assert observed["first_repository_call"] == {
        "item_id": "explore-call",
        "tool": "loci_explore",
        "intent": "type_dependencies",
        "status": "completed",
    }
    assert observed["initial_route_expected"] == "type_dependencies"
    assert observed["initial_type_route"] is True
    assert observed["requested_anchor_received"] is True
    assert observed["maintained_exposure"] is True
    assert observed["helper_call_count"] == 1
    assert observed["explore_calls"][0]["successful_delivery"] is True
    assert observed["explore_calls"][0]["status"] == "ok"
    assert observed["explore_calls"][0]["anchor_ids"] == ["consumer.ts::processOrder#function"]
    assert observed["explore_calls"][0]["requested_anchor_received"] is True
    assert observed["explore_calls"][0]["anchor_complete"] is True


def test_search_first_then_explore_with_consistent_trace_is_false_and_records_fallback(tmp_path: Path) -> None:
    corpus = load_corpus(CORPUS_ROOT)
    case = _maintained(next(case for case in corpus["cases"] if case["id"] == "imported_interface"))
    repo = tmp_path / "snapshot"
    materialize_snapshot(corpus, case["snapshot"], repo)
    trace_path = tmp_path / "trace.json"
    run = {
        "repo": str(repo),
        "corpus_root": str(CORPUS_ROOT),
        "case_id": case["id"],
        "session_id": "routing-search-first",
        "arm": "B",
        "repetition": 1,
        "trace_path": str(trace_path),
    }
    with _isolated_store(tmp_path / "store"):
        service.index_repo(repo, incremental=False)
        adapter = ExploreAdapter(run)
        search = adapter.read_operation("search", {"query": "processOrder"})
        explore = adapter.read_operation("loci_explore", {"intent": "type_dependencies", "query": "processOrder"})
    assert isinstance(search.structured_content, dict)
    assert isinstance(explore.structured_content, dict)
    calls = [
        _call("search-call", "search", adapter.deliveries[0]["arguments"], search.structured_content),
        _call("explore-call", "loci_explore", adapter.deliveries[1]["arguments"], explore.structured_content),
    ]
    observed = observe_routing(corpus, case, json.loads(trace_path.read_text()), _events(calls))
    assert observed["observations_complete"] is True
    assert observed["first_repository_call"]["tool"] == "search"
    assert observed["initial_type_route"] is False
    assert observed["requested_anchor_received"] is True
    assert observed["maintained_exposure"] is False
    assert observed["fallback_calls"] == []


@pytest.mark.parametrize("variant", ["wrong", "missing", "failed"])
def test_wrong_missing_and_native_failed_explore_never_claim_exposure(tmp_path: Path, variant: str) -> None:
    corpus, case, _run, raw, payload, adapter = _fixture(tmp_path)
    changed = copy.deepcopy(payload)
    spans: list[dict[str, Any]] | None = None
    if variant == "wrong":
        changed["items"][0]["id"] = "consumer.ts::Other#function"
        changed["items"][0]["name"] = "Other"
    elif variant == "missing":
        changed["status"] = "empty"
        changed["items"] = []
        changed["relationships"] = []
        changed["sources"] = []
        changed["omissions"] = [{"reason": "no_anchor", "count": 1}]
        spans = []
    else:
        changed = {"error": {"code": "NATIVE_ERROR", "message": "broken", "details": {}}, "_evaluation": payload["_evaluation"]}
        spans = []
    rewritten = _rewrite_explore(raw, changed, spans=spans)
    call = _call("explore-call", "loci_explore", adapter.deliveries[0]["arguments"], changed)
    observed = observe_routing(corpus, _maintained(case), rewritten, _events([call]))

    assert observed["observations_complete"] is True
    assert observed["maintained_exposure"] is False
    assert observed["requested_anchor_received"] is False
    assert observed["explore_calls"][0]["requested_anchor_received"] is False
    assert observed["explore_calls"][0]["anchor_complete"] is False
    if variant == "failed":
        assert observed["explore_calls"][0]["successful_delivery"] is False


def test_clipped_anchor_source_is_exposed_but_not_complete(tmp_path: Path) -> None:
    corpus, case, _run, raw, payload, adapter = _fixture(tmp_path)
    changed = copy.deepcopy(payload)
    anchor_source = changed["sources"][0]
    prefix = anchor_source["content"][:20]
    anchor_source["content"] = prefix
    anchor_source["end_byte"] = anchor_source["start_byte"] + len(prefix.encode("utf-8"))
    changed["items"][0]["complete"] = False
    changed["status"] = "partial"
    changed["omissions"] = [{"reason": "source_clipped", "count": 1}]
    spans = [
        {
            "file": raw["events"][0]["spans"][0]["file"],
            "start_byte": raw["events"][0]["spans"][0]["start_byte"],
            "end_byte": anchor_source["end_byte"],
            "sha256": hashlib.sha256(prefix.encode("utf-8")).hexdigest(),
            "text": prefix,
        }
    ]
    rewritten = _rewrite_explore(raw, changed, spans=spans)
    call = _call("explore-call", "loci_explore", adapter.deliveries[0]["arguments"], changed)
    observed = observe_routing(corpus, _maintained(case), rewritten, _events([call]))

    assert observed["observations_complete"] is True
    assert observed["maintained_exposure"] is True
    assert observed["requested_anchor_received"] is True
    assert observed["explore_calls"][0]["anchor_complete"] is False
    assert observed["explore_calls"][0]["status"] == "partial"


def test_no_explore_keeps_exposure_false_and_call_target_route_distinct(tmp_path: Path) -> None:
    corpus, case, _run, raw, _payload, _adapter = _fixture(
        tmp_path, case_id="exported_arrow", intent="type_dependencies"
    )
    # The fixture trace includes the explore delivery, so use an empty valid
    # v1 trace with the same identity to model an arm that never explored.
    raw["events"] = []
    raw["deliveries"] = []
    raw["attempts"] = 0
    observed = observe_routing(corpus, case, raw, _events([]))

    assert observed["observations_complete"] is True
    assert observed["initial_route_expected"] == "call_target"
    assert observed["maintained_exposure"] is None
    assert observed["requested_anchor_received"] is False


def test_malformed_duplicate_orphan_and_terminal_before_start_fail_closed(tmp_path: Path) -> None:
    corpus, case, _run, raw, payload, adapter = _fixture(tmp_path)
    arguments = copy.deepcopy(adapter.deliveries[0]["arguments"])
    call = _call("explore-call", "loci_explore", arguments, payload)
    lifecycle = _lifecycle(call)
    duplicate = copy.deepcopy(lifecycle[1])
    orphan = copy.deepcopy(lifecycle[1])
    orphan["item"]["id"] = "orphan"
    observed = observe_routing(
        corpus,
        _maintained(case),
        raw,
        [lifecycle[1], lifecycle[0], lifecycle[1], duplicate, orphan],
    )

    assert observed["observations_complete"] is False
    assert observed["maintained_exposure"] is None
    categories = {failure["category"] for failure in observed["failures"]}
    assert {"terminal_before_start", "duplicate_tool_event", "orphan_terminal_tool_event"} <= categories


def test_measure_matches_v2_everywhere_except_protocol_and_routing(tmp_path: Path) -> None:
    corpus, case, run, raw, payload, adapter = _fixture(tmp_path)
    call = _call("explore-call", "loci_explore", adapter.deliveries[0]["arguments"], payload)
    events = _events(
        [call],
        answer=case["answer"],
        usage={"input_tokens": 100, "cached_input_tokens": 20, "output_tokens": 10},
    )
    old = v2_measure(corpus, case, run, events, 1.0, 0, False)
    new = measure(corpus, case, run, events, 1.0, 0, False)

    assert new["protocol"] == VERSION
    assert new["routing"]["schema_version"] == 1
    new_without_routing = copy.deepcopy(new)
    del new_without_routing["routing"]
    new_without_routing["protocol"] = old["protocol"]
    assert new_without_routing == old
    assert replay_trace(corpus, raw).identity["arm"] == raw["identity"]["arm"]
    assert reconcile_observed(raw, _events([call]))["complete"] is True
