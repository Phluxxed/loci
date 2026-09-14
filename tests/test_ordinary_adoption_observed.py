from __future__ import annotations

import json
from pathlib import Path

import pytest

from benchmarks.ordinary_adoption_observed import (
    ObservationError,
    _main,
    evidence_registry,
    observe_rollout,
)


THREAD = "thread-1"
TURN = "turn-1"


def _metadata(**changes: object) -> dict[str, object]:
    value: dict[str, object] = {
        "run_id": "run-1",
        "case_id": "case-1",
        "condition": "ordinary_delegate",
        "purpose": "ordinary",
        "thread_id": THREAD,
        "turn_id": TURN,
        "target_repo": "/repo",
        "requested_model": "gpt-5.6-terra",
        "requested_effort": "high",
    }
    value.update(changes)
    return value


def _mcp(
    item_id: str,
    tool: str,
    arguments: dict,
    structured: dict,
    *,
    status: str = "completed",
    is_error: bool = False,
) -> dict:
    return {
        "type": "event_msg",
        "payload": {
            "type": "item_completed",
            "thread_id": THREAD,
            "turn_id": TURN,
            "started_at_ms": 100,
            "completed_at_ms": 125,
            "item": {
                "type": "McpToolCall",
                "id": item_id,
                "server": "loci",
                "tool": tool,
                "arguments": arguments,
                "status": status,
                "duration": {"secs": 0, "nanos": 25_000_000},
                "result": {"content": [], "structuredContent": structured, "isError": is_error},
            },
        },
    }


def _shell(item_id: str = "shell-1") -> dict:
    return {
        "type": "event_msg",
        "payload": {
            "type": "item_completed",
            "thread_id": THREAD,
            "turn_id": TURN,
            "started_at_ms": 130,
            "completed_at_ms": 135,
            "item": {
                "type": "CommandExecution",
                "id": item_id,
                "status": "completed",
                "process_id": "42",
                "command": ["/bin/zsh", "-lc", "sed -n '1,20p' src/a.ts"],
                "parsed_cmd": [{"type": "read", "cmd": "sed", "path": "src/a.ts"}],
                "cwd": "file:///repo",
                "source": "unified_exec_startup",
                "exit_code": 0,
                "duration": {"secs": 0, "nanos": 5_000_000},
                "stdout": "source\n",
                "stderr": "",
            },
        },
    }


def _outer_request(call_id: str = "outer-1", source: str = "dynamic.map(call)") -> dict:
    return {
        "type": "response_item",
        "payload": {
            "type": "custom_tool_call",
            "id": f"request-{call_id}",
            "call_id": call_id,
            "name": "exec",
            "status": "completed",
            "input": source,
        },
    }


def _outer_output(call_id: str, *texts: str) -> dict:
    return {
        "type": "response_item",
        "payload": {
            "type": "custom_tool_call_output",
            "id": f"output-{call_id}",
            "call_id": call_id,
            "output": [{"type": "input_text", "text": text} for text in texts],
        },
    }


def _wait_request(call_id: str = "wait-1") -> dict:
    return {
        "type": "response_item",
        "payload": {
            "type": "function_call",
            "id": f"request-{call_id}",
            "call_id": call_id,
            "name": "wait",
            "arguments": json.dumps({"cell_id": "17"}),
        },
    }


def _wait_output(call_id: str, *texts: str) -> dict:
    return {
        "type": "response_item",
        "payload": {
            "type": "function_call_output",
            "id": f"output-{call_id}",
            "call_id": call_id,
            "output": [{"type": "input_text", "text": text} for text in texts],
        },
    }


def _usage(total: int) -> dict:
    usage = {
        "input_tokens": total - 2,
        "cached_input_tokens": 0,
        "cache_write_input_tokens": 0,
        "output_tokens": 2,
        "reasoning_output_tokens": 1,
        "total_tokens": total,
    }
    return {
        "type": "token_usage_record",
        "payload": {
            "thread_id": THREAD,
            "turn_id": TURN,
            "response_id": f"response-{total}",
            "usage": usage,
            "turn_token_usage": usage,
        },
    }


def _final(text: str = "Answer") -> dict:
    return {
        "type": "event_msg",
        "payload": {
            "type": "item_completed",
            "thread_id": THREAD,
            "turn_id": TURN,
            "item": {
                "type": "AgentMessage",
                "id": "answer-1",
                "phase": "final",
                "content": [{"type": "Text", "text": text}],
            },
        },
    }


def _records(body: list[dict], *, boundary: str = "task_complete") -> list[dict]:
    records = [
        {
            "type": "session_meta",
            "payload": {
                "id": THREAD,
                "parent_thread_id": "parent-1",
                "originator": "codex-tui",
                "cli_version": "0.154.0",
                "model_provider": "openai",
                "agent_path": "/root/test",
                "source": {"subagent": {"depth": 1}},
            },
        },
        {"type": "event_msg", "payload": {"type": "task_started", "turn_id": TURN}},
        {
            "type": "turn_context",
            "payload": {
                "turn_id": TURN,
                "root_turn_id": "root-turn-1",
                "cwd": "/repo",
                "model": "gpt-5.6-terra",
                "effort": "high",
            },
        },
        *body,
        {
            "type": "event_msg",
            "payload": {
                "type": boundary,
                "turn_id": TURN,
                **({"reason": "interrupted", "duration_ms": 99} if boundary == "turn_aborted" else {}),
            },
        },
    ]
    for ordinal, record in enumerate(records):
        record["ordinal"] = ordinal
        record["timestamp"] = f"2026-09-14T00:00:{ordinal:02d}Z"
    return records


def _write(tmp_path: Path, records: list[dict]) -> Path:
    path = tmp_path / "rollout.jsonl"
    path.write_text("".join(json.dumps(record) + "\n" for record in records), encoding="utf-8")
    return path


def _observe(tmp_path: Path, body: list[dict], *, boundary: str = "task_complete") -> dict:
    return observe_rollout(_write(tmp_path, _records(body, boundary=boundary)), _metadata())


def test_records_dynamic_shaped_mcp_shell_relationships_and_exact_model_delivery(tmp_path: Path) -> None:
    relationship = {
        "status": "complete",
        "relationships": [
            {"edge": {"from": "a", "to": "b", "type": "calls"}},
            {"edge": {"from": "file", "to": "a", "type": "contains"}},
        ],
        "sources": [{"content": "function a() {}"}],
    }
    type_context = {
        "symbols": [{"id": "a", "source": "type A = string"}],
        "type_context": {
            "status": "complete",
            "references": [{"edge": {"from": "a", "to": "b", "type": "uses_type"}}],
        },
    }
    body = [
        _outer_request(source="const rs = await Promise.all(files.map(dynamicCall));"),
        _mcp("mcp-1", "loci_explore", {"repo": "/repo", "intent": "dependencies"}, relationship),
        _mcp(
            "mcp-2",
            "loci_get",
            {"repo": "/repo", "symbol_ids": ["a"], "include_type_context": True},
            type_context,
        ),
        _shell(),
        _outer_output(
            "outer-1",
            json.dumps(relationship, separators=(",", ":")),
            json.dumps({"wrapped": type_context}, separators=(",", ":")),
        ),
        _usage(20),
        _final(),
    ]

    observed = _observe(tmp_path, body)

    assert [call["item_id"] for call in observed["mcp_calls"]] == ["mcp-1", "mcp-2"]
    assert [call["invocation_category"] for call in observed["mcp_calls"]] == [
        "explore_relationship",
        "type_context_get",
    ]
    assert observed["mcp_calls"][0]["relationship_delivery"] == {
        "application_error": False,
        "result_status": "complete",
        "type_context_status": None,
        "edge_families": {"calls": 1, "contains": 1},
        "edge_count": 2,
        "semantic_edge_count": 1,
        "containment_edge_count": 1,
        "resolved_record_count": 0,
        "unresolved_record_count": 0,
        "unresolved_record_families": {},
        "unknown_record_count": 0,
        "relationship_shape_status": "complete",
        "omissions": None,
        "reported_evidence_bytes": None,
        "reported_output_bytes": None,
        "returned_source_text_bytes": len("function a() {}"),
        "source_text_bytes_status": "complete",
        "requested_output_budget_bytes": None,
        "requested_evidence_budget_bytes": None,
        "returned_limits": None,
    }
    assert observed["mcp_calls"][1]["relationship_delivery"]["semantic_edge_count"] == 1
    assert {call["model_delivery"]["status"] for call in observed["mcp_calls"]} == {"full_exact"}
    assert observed["shell_calls"][0]["invocation_category"] == "shell_source_retrieval"
    assert observed["cost"]["terminal_mcp_invocations"] == 2
    assert observed["cost"]["terminal_shell_commands"] == 1
    registry = evidence_registry(observed)
    assert registry["mcp-1"]["semantic_relationship_count"] == 1
    assert registry["mcp-1"]["model_output_refs"] == [
        observed["mcp_calls"][0]["model_delivery"]["matches"][0]["output_ref"]
    ]


def test_preserves_failed_app_error_empty_partial_and_type_context_states(tmp_path: Path) -> None:
    body = [
        _mcp("failed", "loci_get", {"repo": "/repo"}, {"error": {"code": "HOST"}}, status="failed", is_error=True),
        _mcp("app-error", "loci_get", {"repo": "/repo"}, {"error": {"code": "SYMBOL_NOT_FOUND"}}, is_error=True),
        _mcp("empty", "loci_explore", {"repo": "/repo", "intent": "locate"}, {"status": "complete", "items": []}),
        _mcp(
            "partial",
            "loci_explore",
            {"repo": "/repo", "intent": "impact"},
            {
                "status": "partial",
                "relationships": [{"edge": {"from": "a", "to": "b", "type": "calls"}}],
                "omissions": [{"reason": "budget", "count": 1}],
            },
        ),
        _mcp(
            "type-context",
            "loci_get",
            {"repo": "/repo", "include_type_context": True},
            {
                "type_context": {
                    "status": "partial",
                    "references": [{"edge": {"from": "a", "to": "T", "type": "uses_type"}}],
                }
            },
        ),
        _final(),
    ]
    calls = {call["item_id"]: call for call in _observe(tmp_path, body)["mcp_calls"]}

    assert calls["failed"]["status"] == "failed"
    assert calls["failed"]["relationship_delivery"]["application_error"] is True
    assert calls["app-error"]["status"] == "completed"
    assert calls["app-error"]["relationship_delivery"]["result_status"] == "error"
    assert calls["empty"]["relationship_delivery"]["edge_count"] == 0
    assert calls["partial"]["relationship_delivery"]["result_status"] == "partial"
    assert calls["partial"]["relationship_delivery"]["omissions"] == [{"reason": "budget", "count": 1}]
    assert calls["type-context"]["invocation_category"] == "type_context_get"
    assert calls["type-context"]["relationship_delivery"]["type_context_status"] == "partial"


def test_scans_calls_after_yield_and_matches_wait_output_without_parent_guess(tmp_path: Path) -> None:
    first, second = {"status": "complete", "value": 1}, {"status": "complete", "value": 2}
    body = [
        _outer_request(),
        _mcp("before-yield", "loci_file", {"repo": "/repo"}, first),
        _outer_output("outer-1", "Script running with cell ID 17"),
        _mcp("after-yield", "loci_file", {"repo": "/repo"}, second),
        _wait_request(),
        _wait_output(
            "wait-1",
            json.dumps({"result": first}, separators=(",", ":")),
            json.dumps({"result": second}, separators=(",", ":")),
        ),
        _final(),
    ]
    observed = _observe(tmp_path, body)

    assert [call["item_id"] for call in observed["mcp_calls"]] == ["before-yield", "after-yield"]
    assert [call["model_delivery"]["status"] for call in observed["mcp_calls"]] == [
        "full_exact",
        "full_exact",
    ]
    assert [item["kind"] for item in observed["outer_code_mode"]] == ["exec", "wait"]


def test_marks_truncated_and_unemitted_model_delivery(tmp_path: Path) -> None:
    structured = {"status": "complete", "content": "large"}
    truncated = _observe(
        tmp_path,
        [
            _outer_request(),
            _mcp("mcp-1", "loci_file", {"repo": "/repo"}, structured),
            _outer_output("outer-1", "Warning: truncated output (original token count: 10000)"),
            _final(),
        ],
    )
    assert truncated["mcp_calls"][0]["model_delivery"]["status"] == "unknown_truncated"

    second = tmp_path / "unemitted"
    second.mkdir()
    unemitted = _observe(
        second,
        [_mcp("mcp-1", "loci_file", {"repo": "/repo"}, structured), _final()],
    )
    assert unemitted["mcp_calls"][0]["model_delivery"]["status"] == "not_emitted"


def test_identical_exact_payloads_remain_ambiguous_and_leave_supported_registry_empty(tmp_path: Path) -> None:
    structured = {
        "status": "complete",
        "relationships": [{"edge": {"from": "a", "to": "b", "type": "calls"}}],
    }
    observed = _observe(
        tmp_path,
        [
            _outer_request(),
            _mcp("mcp-1", "loci_explore", {"repo": "/repo", "intent": "dependencies"}, structured),
            _mcp("mcp-2", "loci_explore", {"repo": "/repo", "intent": "dependencies"}, structured),
            _outer_output("outer-1", json.dumps(structured, separators=(",", ":"))),
            _final(),
        ],
    )
    assert [call["model_delivery"]["status"] for call in observed["mcp_calls"]] == [
        "ambiguous_exact",
        "ambiguous_exact",
    ]
    assert evidence_registry(observed) == {
        "mcp-1": {"semantic_relationship_count": 1, "model_output_refs": []},
        "mcp-2": {"semantic_relationship_count": 1, "model_output_refs": []},
    }


def test_distinct_packets_in_one_wrapper_are_each_unambiguous(tmp_path: Path) -> None:
    first = {
        "status": "complete",
        "relationships": [{"edge": {"from": "a", "to": "b", "type": "calls"}}],
    }
    second = {
        "status": "complete",
        "relationships": [{"edge": {"from": "x", "to": "y", "type": "uses_type"}}],
    }
    observed = _observe(
        tmp_path,
        [
            _outer_request(),
            _mcp("mcp-1", "loci_explore", {"repo": "/repo", "intent": "dependencies"}, first),
            _mcp("mcp-2", "loci_explore", {"repo": "/repo", "intent": "dependencies"}, second),
            _outer_output("outer-1", json.dumps({"results": [first, second]}, separators=(",", ":"))),
            _final(),
        ],
    )

    assert [call["model_delivery"]["status"] for call in observed["mcp_calls"]] == [
        "full_exact",
        "full_exact",
    ]
    registry = evidence_registry(observed)
    assert registry["mcp-1"]["model_output_refs"]
    assert registry["mcp-2"]["model_output_refs"]
    assert registry["mcp-1"]["model_output_refs"] == registry["mcp-2"]["model_output_refs"]


PRIMARY_COMPACT_PROBE = Path(
    "benchmarks/comparisons/ordinary-adoption-v1/runtime/primary-compact-probe.json"
)


@pytest.mark.skipif(
    not PRIMARY_COMPACT_PROBE.exists(), reason="local primary compact probe is unavailable"
)
def test_real_compact_reference_record_counts_one_semantic_relationship(tmp_path: Path) -> None:
    result = json.loads(PRIMARY_COMPACT_PROBE.read_text(encoding="utf-8"))
    structured = result["structuredContent"]
    observed = _observe(
        tmp_path,
        [
            _mcp(
                "compact-reference",
                "loci_graph_references",
                {"repo": "/repo", "file": "consumer.ts"},
                structured,
            ),
            _final(),
        ],
    )
    delivery = observed["mcp_calls"][0]["relationship_delivery"]

    assert delivery["semantic_edge_count"] == 1
    assert delivery["edge_families"] == {"references_type": 1}
    assert delivery["resolved_record_count"] == 1
    assert delivery["unresolved_record_count"] == 0
    assert delivery["relationship_shape_status"] == "complete"
    assert delivery["returned_source_text_bytes"] == len("Payload")
    assert delivery["reported_output_bytes"] == 832


@pytest.mark.parametrize(
    ("tool", "item", "family"),
    [
        (
            "loci_graph_calls",
            {"caller_id": "a", "target_id": "b", "status": "resolved"},
            "calls",
        ),
        (
            "loci_graph_imports",
            {"source_id": "a", "target_id": "b", "status": "resolved", "type_only": True},
            "imports_type",
        ),
    ],
)
def test_declared_full_record_shapes_are_counted(
    tmp_path: Path, tool: str, item: dict, family: str
) -> None:
    observed = _observe(
        tmp_path,
        [_mcp("record", tool, {"repo": "/repo"}, {"items": [item]}), _final()],
    )
    delivery = observed["mcp_calls"][0]["relationship_delivery"]
    assert delivery["semantic_edge_count"] == 1
    assert delivery["edge_families"] == {family: 1}


def test_unresolved_records_stay_separate_and_unknown_shapes_are_explicit(tmp_path: Path) -> None:
    unresolved = _observe(
        tmp_path,
        [
            _mcp(
                "unresolved",
                "loci_graph_references",
                {"repo": "/repo"},
                {
                    "items": [
                        {
                            "source_id": "a",
                            "target_id": None,
                            "status": "unresolved",
                            "relation": "references_type",
                        }
                    ]
                },
            ),
            _final(),
        ],
    )
    delivery = unresolved["mcp_calls"][0]["relationship_delivery"]
    assert delivery["semantic_edge_count"] == 0
    assert delivery["unresolved_record_count"] == 1
    assert delivery["unresolved_record_families"] == {"references_type": 1}

    unknown_dir = tmp_path / "unknown"
    unknown_dir.mkdir()
    unknown = _observe(
        unknown_dir,
        [
            _mcp(
                "unknown",
                "loci_graph_calls",
                {"repo": "/repo"},
                {"items": [{"status": "resolved", "caller_id": "a"}]},
            ),
            _final(),
        ],
    )
    unknown_delivery = unknown["mcp_calls"][0]["relationship_delivery"]
    assert unknown_delivery["semantic_edge_count"] is None
    assert unknown_delivery["relationship_shape_status"] == "unknown"
    assert evidence_registry(unknown)["unknown"]["semantic_relationship_count"] is None
    assert unknown["integrity"]["complete_for_graph_use_claim"] is False


def test_unknown_source_schema_makes_total_unknown_but_known_errors_remain_zero(tmp_path: Path) -> None:
    observed = _observe(
        tmp_path,
        [
            _mcp(
                "future-source",
                "loci_future_source",
                {"repo": "/repo"},
                {"content": "source whose schema is undeclared"},
            ),
            _mcp(
                "known-error",
                "loci_get",
                {"repo": "/repo"},
                {"error": {"code": "SYMBOL_NOT_FOUND"}},
                is_error=True,
            ),
            _final(),
        ],
    )
    calls = {call["item_id"]: call for call in observed["mcp_calls"]}
    assert calls["future-source"]["relationship_delivery"]["returned_source_text_bytes"] is None
    assert calls["future-source"]["relationship_delivery"]["source_text_bytes_status"] == "unknown_schema"
    assert calls["known-error"]["relationship_delivery"]["returned_source_text_bytes"] == 0
    assert calls["known-error"]["relationship_delivery"]["source_text_bytes_status"] == "known_source_free_error"
    assert observed["cost"]["returned_source_text_bytes"] is None
    assert observed["cost"]["returned_source_text_bytes_status"] == "unknown"


def test_aborted_run_has_no_imputed_final_and_uses_last_cumulative_usage(tmp_path: Path) -> None:
    observed = _observe(
        tmp_path,
        [
            _mcp("mcp-1", "loci_search", {"repo": "/repo"}, {"status": "complete"}),
            _usage(10),
            _usage(30),
        ],
        boundary="turn_aborted",
    )

    assert observed["outcome"] == {
        "boundary": "turn_aborted",
        "boundary_line": 7,
        "boundary_reason": "interrupted",
        "duration_ms": 99,
        "final_answer": {"status": "missing"},
        "task_completed": False,
    }
    assert observed["provider_usage"]["usage"]["total_tokens"] == 30
    assert observed["provider_usage"]["snapshots_observed"] == 2
    assert observed["provider_usage"]["cumulative"] is True
    assert observed["cost"]["terminal_mcp_invocations"] == 1
    assert observed["integrity"]["complete_for_graph_use_claim"] is False


@pytest.mark.parametrize("variant", ["duplicate", "missing_result", "ordinal", "malformed"])
def test_rejects_corrupt_or_missing_native_records(tmp_path: Path, variant: str) -> None:
    records = _records(
        [
            _mcp("same", "loci_file", {"repo": "/repo"}, {"status": "complete"}),
            _mcp("other", "loci_file", {"repo": "/repo"}, {"status": "complete"}),
            _final(),
        ]
    )
    if variant == "duplicate":
        records[4]["payload"]["item"]["id"] = "same"
    elif variant == "missing_result":
        del records[3]["payload"]["item"]["result"]
    elif variant == "ordinal":
        records[3]["ordinal"] = 99
    path = _write(tmp_path, records)
    if variant == "malformed":
        path.write_text(path.read_text(encoding="utf-8") + "{bad\n", encoding="utf-8")

    with pytest.raises(ObservationError):
        observe_rollout(path, _metadata())


def test_rejects_missing_metadata_and_unmatched_outer_output(tmp_path: Path) -> None:
    path = _write(tmp_path, _records([_final()]))
    metadata = _metadata()
    del metadata["turn_id"]
    with pytest.raises(ObservationError, match="missing_metadata"):
        observe_rollout(path, metadata)

    with pytest.raises(ObservationError, match="altered_retained_interval"):
        observe_rollout(path, _metadata(expected_interval_sha256="0" * 64))

    unmatched = _write(tmp_path, _records([_outer_output("absent", "value"), _final()]))
    with pytest.raises(ObservationError, match="unmatched_outer_output"):
        observe_rollout(unmatched, _metadata())

    missing_output_record = _outer_output("outer-1")
    del missing_output_record["payload"]["output"]
    missing_output = _write(
        tmp_path,
        _records([_outer_request(), missing_output_record, _final()]),
    )
    with pytest.raises(ObservationError, match="missing_outer_output_field"):
        observe_rollout(missing_output, _metadata())


def test_target_repo_alias_normalizes_and_mismatch_is_a_condition_deviation(tmp_path: Path) -> None:
    alias = observe_rollout(
        _write(
            tmp_path,
            _records(
                [
                    _mcp(
                        "alias",
                        "loci_search",
                        {"repo": "/private/tmp/adoption-target"},
                        {"status": "complete"},
                    ),
                    _final(),
                ]
            ),
        ),
        _metadata(target_repo="/tmp/adoption-target"),
    )
    assert alias["native_identity"]["condition_deviations"] == []
    assert alias["integrity"]["complete_for_graph_use_claim"] is True

    mismatch_dir = tmp_path / "mismatch"
    mismatch_dir.mkdir()
    mismatch = observe_rollout(
        _write(
            mismatch_dir,
            _records(
                [
                    _mcp(
                        "wrong-repo",
                        "loci_search",
                        {"repo": "/private/tmp/different-target"},
                        {"status": "complete"},
                    ),
                    _final(),
                ]
            ),
        ),
        _metadata(target_repo="/tmp/adoption-target"),
    )
    assert mismatch["native_identity"]["condition_deviations"] == [
        {
            "field": "target_repo",
            "item_id": "wrong-repo",
            "expected_root": "/private/tmp/adoption-target",
            "actual_root": "/private/tmp/different-target",
        }
    ]
    assert mismatch["integrity"]["complete_for_graph_use_claim"] is False


def test_missing_boundary_final_and_usage_are_explicit_states(tmp_path: Path) -> None:
    records = _records([])[:-1]
    path = _write(tmp_path, records)
    observed = observe_rollout(path, _metadata())

    assert observed["outcome"]["boundary"] == "missing"
    assert observed["outcome"]["final_answer"] == {"status": "missing"}
    assert observed["provider_usage"] == {"status": "missing"}
    assert observed["integrity"]["complete_for_graph_use_claim"] is False


def test_cli_emits_the_callable_artifact(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    rollout = _write(tmp_path, _records([_final()]))
    metadata = tmp_path / "metadata.json"
    metadata.write_text(json.dumps(_metadata()), encoding="utf-8")

    assert _main([str(rollout), str(metadata)]) == 0
    rendered = json.loads(capsys.readouterr().out)
    assert rendered["schema_version"] == 1
    assert rendered["run"]["run_id"] == "run-1"


RETAINED = Path(
    "/Users/brummerv/.codex/sessions/2026/09/14/"
    "rollout-2026-09-14T11-22-52-01a09d82-8731-73b2-8c07-58b872b7feac.jsonl"
)


@pytest.mark.skipif(not RETAINED.exists(), reason="local retained native rollout is unavailable")
def test_local_retained_session_sanity() -> None:
    observed = observe_rollout(
        RETAINED,
        {
            "run_id": "retained-capture-sanity",
            "purpose": "capability_probe",
            "thread_id": "01a09d82-8731-73b2-8c07-58b872b7feac",
            "turn_id": "01a09d82-87e1-7a71-9312-32dc56ceb087",
            "target_repo": "/Users/brummerv/phluxxed/anvil_redux",
            "requested_model": "gpt-5.6-sol",
            "requested_effort": "high",
        },
    )

    assert observed["cost"]["terminal_mcp_invocations"] == 35
    assert observed["cost"]["terminal_shell_commands"] == 20
    assert observed["outcome"]["boundary"] == "turn_aborted"
    assert observed["outcome"]["final_answer"] == {"status": "missing"}


INITIAL_DIAGNOSTIC = Path(
    "/Users/brummerv/.codex/sessions/2026/09/14/"
    "rollout-2026-09-14T14-12-30-01a09e1d-d62a-7e40-8243-d7a5add917a2.jsonl"
)


@pytest.mark.skipif(not INITIAL_DIAGNOSTIC.exists(), reason="local initial diagnostic is unavailable")
def test_local_initial_diagnostic_stops_before_followup_catalog_probe() -> None:
    observed = observe_rollout(
        INITIAL_DIAGNOSTIC,
        {
            "run_id": "initial-diagnostic-sanity",
            "purpose": "ordinary",
            "thread_id": "01a09e1d-d62a-7e40-8243-d7a5add917a2",
            "turn_id": "01a09e1d-d722-74e1-927d-c19108e38a9b",
            "target_repo": "/Users/brummerv/phluxxed/anvil_redux",
            "requested_model": "gpt-5.6-terra",
            "requested_effort": "high",
        },
    )

    assert observed["cost"]["terminal_mcp_invocations"] == 0
    assert observed["cost"]["terminal_shell_commands"] == 13
    assert observed["shell_calls"][-1]["line"] == 103
    assert observed["outcome"]["boundary_line"] == 112
    assert observed["outcome"]["final_answer"]["status"] == "present"


NATIVE_PREFLIGHT = Path(
    "/Users/brummerv/.codex/sessions/2026/09/14/"
    "rollout-2026-09-14T15-30-18-01a09e65-0e26-7a32-abae-9f5537052c88.jsonl"
)


@pytest.mark.skipif(not NATIVE_PREFLIGHT.exists(), reason="local native preflight is unavailable")
def test_local_native_preflight_retains_all_failures_recovery_and_type_context() -> None:
    observed = observe_rollout(
        NATIVE_PREFLIGHT,
        {
            "run_id": "native-preflight-sanity",
            "purpose": "capability_probe",
            "thread_id": "01a09e65-0e26-7a32-abae-9f5537052c88",
            "turn_id": "01a09e66-d7e8-72b3-bfcd-58cdfd7cdf10",
            "target_repo": "/tmp/loci-adoption-audit-20260914/native-observer-fixture",
        },
    )

    assert observed["cost"]["terminal_mcp_invocations"] == 12
    calls = {call["line"]: call for call in observed["mcp_calls"]}
    assert calls[56]["status"] == "failed"
    assert calls[56]["relationship_delivery"]["application_error"] is True
    assert calls[57]["status"] == "failed"
    assert calls[74]["invocation_category"] == "type_context_get"
    assert calls[74]["relationship_delivery"]["semantic_edge_count"] == 1
    assert calls[74]["relationship_delivery"]["type_context_status"] == "complete"
    assert calls[75]["relationship_delivery"]["edge_count"] == 0
    assert calls[76]["relationship_delivery"]["edge_count"] == 0
    assert calls[77]["relationship_delivery"]["application_error"] is True
    assert observed["outcome"]["boundary"] == "task_complete"
    assert observed["outcome"]["final_answer"]["status"] == "present"
