from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import pytest

from benchmarks.typescript_context_adapter import wire
from benchmarks.typescript_context_corpus import (
    _isolated_store,
    load_controls,
    load_corpus,
    materialize_snapshot,
)
from benchmarks.typescript_context_explore_v2 import sha
from benchmarks.typescript_context_explore_v2_observed import measure
from benchmarks.typescript_context_explore_v2_replay import replay_attempt
from benchmarks.typescript_context_explore_tools import ExploreAdapter, normalize_arguments
from benchmarks.typescript_context_explore_transport import HELPERS, audit_request, tool_names
from loci import service


ROOT = Path(__file__).parents[1]
CORPUS_ROOT = ROOT / "benchmarks" / "corpora" / "typescript-context-v3"


def _call(
    item_id: str,
    *,
    tool: str,
    arguments: dict[str, Any],
    structured: dict[str, Any],
) -> dict[str, Any]:
    return {
        "id": item_id,
        "type": "mcp_tool_call",
        "server": "evaluation",
        "tool": tool,
        "arguments": copy.deepcopy(arguments),
        "status": "completed",
        "error": None,
        "result": {"content": [], "structured_content": copy.deepcopy(structured)},
    }


def _lifecycle(call: dict[str, Any]) -> list[dict[str, Any]]:
    started = {
        key: copy.deepcopy(call[key])
        for key in ("id", "type", "server", "tool", "arguments")
    }
    return [
        {"type": "item.started", "item": started},
        {"type": "item.completed", "item": copy.deepcopy(call)},
    ]


def _request(prompt: str) -> dict[str, Any]:
    return {
        "model": "gpt-5.6-luna",
        "reasoning": {"effort": "high"},
        "input": [
            {
                "type": "additional_tools",
                "tools": [
                    {
                        "type": "namespace",
                        "name": "mcp__evaluation",
                        "tools": [{"name": name} for name in sorted(tool_names("B"))],
                    },
                    {
                        "type": "namespace",
                        "name": "functions",
                        "tools": [{"name": name} for _, name in sorted(HELPERS)],
                    },
                ],
            },
            {"type": "message", "content": [{"type": "input_text", "text": prompt}]},
        ],
    }


def _retained_attempt(
    tmp_path: Path,
) -> tuple[Path, dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]:
    corpus = load_corpus(CORPUS_ROOT)
    controls = load_controls(corpus)
    case = next(case for case in corpus["cases"] if case["id"] == "imported_interface")
    attempt_id = "imported_interface-r1-B"
    plan = {
        "attempt_id": attempt_id,
        "case_id": case["id"],
        "snapshot": case["snapshot"],
        "repetition": 1,
        "arm": "B",
    }
    freeze = {
        "freeze_json_sha256": "offline-freeze",
        "engine": {"commit": "offline-engine", "source_tree": "offline-tree", "extractor_version": 25},
    }
    folder = tmp_path / attempt_id
    folder.mkdir()
    repo = tmp_path / "snapshot"
    store = tmp_path / "store"
    materialize_snapshot(corpus, case["snapshot"], repo)
    trace_path = folder / "adapter-trace.json"
    run = {
        "repo": str(repo),
        "corpus_root": str(CORPUS_ROOT.resolve()),
        "case_id": case["id"],
        "session_id": "offline-replay-session",
        "arm": "B",
        "repetition": 1,
        "trace_path": str(trace_path),
        "attempt_id": attempt_id,
    }
    with _isolated_store(store):
        service.index_repo(repo, incremental=False)
        index = service.get_store().load(repo.resolve())
        assert index is not None
        adapter = ExploreAdapter(run)
        get_arguments = normalize_arguments(
            "get", {"symbol_ids": ["consumer.ts::processOrder#function"], "context": 2}
        )
        get_result = adapter.read_operation("get", get_arguments).structured_content
        assert isinstance(get_result, dict)
        explore_arguments = normalize_arguments(
            "loci_explore",
            {
                "intent": "type_dependencies",
                "seed_ids": ["consumer.ts::processOrder#function"],
            },
        )
        explore_result = adapter.read_operation("loci_explore", explore_arguments).structured_content
        assert isinstance(explore_result, dict)

        get_call = _call("get-call", tool="get", arguments=get_arguments, structured=get_result)
        explore_call = _call(
            "explore-call",
            tool="loci_explore",
            arguments=explore_arguments,
            structured=explore_result,
        )
        events = [
            {"type": "thread.started", "thread_id": "offline-thread"},
            *_lifecycle(get_call),
            *_lifecycle(explore_call),
            {
                "type": "item.completed",
                "item": {"id": "answer", "type": "agent_message", "text": json.dumps(case["answer"])},
            },
            {
                "type": "turn.completed",
                "usage": {"input_tokens": 100, "cached_input_tokens": 20, "output_tokens": 10},
            },
        ]
        artifact = measure(corpus, case, run, events, 1.25, 0, False, index)

    prompt = controls["agent"]["common_prompt"] + case["prompt"]
    audited = audit_request(_request(prompt), prompt, "B")
    freeze["canonical_tool_schemas_sha256"] = {"B": audited["canonical_tool_schemas_sha256"]}
    config: dict[str, Any] = {}
    provenance = {
        "attempt_id": attempt_id,
        "case_id": case["id"],
        "snapshot": case["snapshot"],
        "repetition": 1,
        "arm": "B",
        "adapter_module": "benchmarks.typescript_context_explore_tools",
        "model": "gpt-5.6-luna",
        "reasoning_effort": "high",
        "corpus_sha256": sha((CORPUS_ROOT / "corpus.json").read_bytes()),
        "controls_sha256": sha((CORPUS_ROOT / "comparison-controls.json").read_bytes()),
        "catalog_sha256": "offline-catalog",
        "runner_sha256": "offline-runner",
        "source": {"engine": freeze["engine"], "freeze_json_sha256": freeze["freeze_json_sha256"]},
        "config": config,
        "config_sha256": sha(wire(config).encode()),
        "prompt_sha256": sha(prompt.encode()),
        "index_seconds": 0.01,
        "snapshot_files": corpus["snapshots"][case["snapshot"]]["files"],
        "extractor_version": 25,
        "canonical_tool_schemas_sha256": audited["canonical_tool_schemas_sha256"],
    }
    artifact["attempt_id"] = attempt_id
    artifact["arm"] = "B"
    artifact["provenance"] = provenance
    (folder / "run.json").write_text(json.dumps(run), encoding="utf-8")
    (folder / "provenance.json").write_text(json.dumps(provenance), encoding="utf-8")
    (folder / "request-audit.json").write_text(json.dumps(audited), encoding="utf-8")
    (folder / "adapter-trace-copy.json").write_bytes(trace_path.read_bytes())
    (folder / "events.jsonl").write_text(
        "\n".join(json.dumps(event, separators=(",", ":")) for event in events) + "\n",
        encoding="utf-8",
    )
    (folder / "events.json").write_text(json.dumps(events), encoding="utf-8")
    (folder / "result.json").write_text(json.dumps(artifact), encoding="utf-8")
    return folder, corpus, case, plan, freeze, index


def test_replay_attempt_remeasures_real_get_and_explore_delivery(tmp_path: Path) -> None:
    folder, corpus, case, plan, freeze, index = _retained_attempt(tmp_path)

    report = replay_attempt(folder, corpus, case, plan, freeze, index)

    assert report == {
        "attempt_id": plan["attempt_id"],
        "verified": True,
        "measurement_complete": True,
        "task_correct": True,
    }
    trace = json.loads((folder / "adapter-trace.json").read_text(encoding="utf-8"))
    assert trace["protocol"] == "typescript-context-explore-v1"
    assert [event["operation"] for event in trace["events"]] == ["get", "explore"]
    assert trace["deliveries"][1]["operation"] == "explore"
    artifact = json.loads((folder / "result.json").read_text(encoding="utf-8"))
    assert artifact["protocol"] == "typescript-context-explore-v2"
    relationships = artifact["baseline"]["relationships"]
    assert relationships["delivered_dependency_links_total"] == 1
    assert relationships["delivery_integrity_violations"] == []


def test_replay_attempt_rejects_legacy_measurement_protocol(tmp_path: Path) -> None:
    folder, corpus, case, plan, freeze, index = _retained_attempt(tmp_path)
    result_path = folder / "result.json"
    result = json.loads(result_path.read_text(encoding="utf-8"))
    result["protocol"] = "typescript-context-explore-v1"
    result_path.write_text(json.dumps(result), encoding="utf-8")

    with pytest.raises(ValueError, match="measurement protocol"):
        replay_attempt(folder, corpus, case, plan, freeze, index)


def test_replay_attempt_rejects_missing_relationship_score(tmp_path: Path) -> None:
    folder, corpus, case, plan, freeze, index = _retained_attempt(tmp_path)
    path = folder / "result.json"
    result = json.loads(path.read_text(encoding="utf-8"))
    del result["baseline"]["relationships"]
    path.write_text(json.dumps(result), encoding="utf-8")

    with pytest.raises(ValueError, match="relationship score is unavailable"):
        replay_attempt(folder, corpus, case, plan, freeze, index)

