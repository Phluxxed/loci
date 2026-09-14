"""Native observer compatibility layer for optional ``CallToolResult.isError``.

This module preserves the frozen v1 observer and reuses its interval, outer
output, delivery-correlation, and accounting helpers.  It accepts the native
host's successful MCP envelope when ``isError`` is omitted, without inserting a
synthetic field into the retained result before byte accounting or correlation.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
import hashlib
from pathlib import Path
from typing import Any

from benchmarks.ordinary_adoption_observed import (
    BOUNDARY_EVENTS,
    SCHEMA_VERSION,
    TERMINAL_EVENTS,
    ObservationError,
    _bytes_hash,
    _canonical_repo,
    _collect_outer,
    _compact,
    _correlate_delivery,
    _error,
    _final_answer,
    _find_interval,
    _invocation_category,
    _provider_usage,
    _read_rollout,
    _relationship_delivery,
    _require_item_fields,
    _shell_category,
    _validate_metadata,
)


NATIVE_ADAPTER_VERSION = "ordinary-adoption-native-v2"


def _collect_operations(
    interval: Sequence[tuple[int, dict[str, Any]]], metadata: Mapping[str, Any]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Collect terminal operations with the native optional-isError rule.

    The stored ``result`` stays untouched.  In particular, absence means
    successful only for validation and relationship classification through the
    frozen helper's existing ``result.get('isError') is True`` check.
    """

    mcp: list[dict[str, Any]] = []
    shell: list[dict[str, Any]] = []
    identities: set[str] = set()
    for line, record in interval:
        if record.get("type") != "event_msg":
            continue
        payload = record.get("payload")
        if not isinstance(payload, dict):
            _error("invalid_payload", f"line {line} has no object payload")
        if payload.get("type") not in TERMINAL_EVENTS:
            continue
        item = payload.get("item")
        if not isinstance(item, dict) or item.get("type") not in {"McpToolCall", "CommandExecution"}:
            continue
        if payload.get("thread_id") != metadata["thread_id"] or payload.get("turn_id") != metadata["turn_id"]:
            _error("conflicting_terminal_identity", f"line {line} has a different thread or turn")
        for timestamp_field in ("started_at_ms", "completed_at_ms"):
            if not isinstance(payload.get(timestamp_field), (int, float)):
                _error("missing_terminal_field", f"line {line} has no numeric {timestamp_field}")
        _require_item_fields(item, ("id", "type", "status"), line)
        identity = item["id"]
        if not isinstance(identity, str) or not identity:
            _error("invalid_terminal_id", f"line {line} has an invalid item id")
        if identity in identities:
            _error("duplicate_terminal_id", f"duplicate terminal id {identity!r} at line {line}")
        identities.add(identity)
        if item["status"] not in {"completed", "failed"}:
            _error("invalid_terminal_shape", f"line {line} has invalid native status {item['status']!r}")
        if payload["type"] == "item_failed" and item["status"] != "failed":
            _error("invalid_terminal_shape", f"line {line} item_failed is not status=failed")
        if "duration" not in item:
            _error("missing_terminal_field", f"line {line} has no duration")

        common = {
            "line": line,
            "event_type": payload["type"],
            "item_id": identity,
            "thread_id": payload["thread_id"],
            "turn_id": payload["turn_id"],
            "started_at_ms": payload.get("started_at_ms"),
            "completed_at_ms": payload.get("completed_at_ms"),
            "status": item["status"],
            "duration": item.get("duration"),
        }
        if item["type"] == "McpToolCall":
            _require_item_fields(item, ("server", "tool", "arguments", "result"), line)
            if not isinstance(item["server"], str) or not isinstance(item["tool"], str):
                _error("invalid_terminal_shape", f"line {line} has invalid MCP server/tool")
            if not isinstance(item["arguments"], dict) or not isinstance(item["result"], dict):
                _error("invalid_terminal_shape", f"line {line} has invalid MCP arguments/result")
            result = item["result"]
            if not isinstance(result.get("content"), list):
                _error("invalid_terminal_shape", f"line {line} has invalid native MCP result envelope")
            if "isError" in result and not isinstance(result["isError"], bool):
                _error("invalid_terminal_shape", f"line {line} has invalid native MCP result envelope")
            if "structuredContent" in result and not isinstance(result["structuredContent"], dict):
                _error("invalid_terminal_shape", f"line {line} has invalid structuredContent")
            response_bytes, response_hash = _bytes_hash(result)
            mcp.append(
                {
                    **common,
                    "server": item["server"],
                    "tool": item["tool"],
                    "arguments": item["arguments"],
                    "target_repo": item["arguments"].get("repo"),
                    "result": result,
                    "canonical_result_json_bytes": response_bytes,
                    "canonical_result_json_sha256": response_hash,
                    "invocation_category": _invocation_category(item["tool"], item["arguments"]),
                    "relationship_delivery": _relationship_delivery(result, item["arguments"], item["tool"]),
                }
            )
        else:
            _require_item_fields(item, ("command", "cwd", "stdout", "stderr", "exit_code"), line)
            if not isinstance(item["stdout"], str) or not isinstance(item["stderr"], str):
                _error("invalid_terminal_shape", f"line {line} has invalid shell output")
            category = _shell_category(item)
            shell.append(
                {
                    **common,
                    "process_id": item.get("process_id"),
                    "command": item["command"],
                    "parsed_cmd": item.get("parsed_cmd"),
                    "cwd": item["cwd"],
                    "source": item.get("source"),
                    "exit_code": item["exit_code"],
                    "stdout": item["stdout"],
                    "stderr": item["stderr"],
                    "stdout_bytes": len(item["stdout"].encode("utf-8")),
                    "stderr_bytes": len(item["stderr"].encode("utf-8")),
                    "invocation_category": category,
                    "graph_activity": "unknown" if category in {"shell_loci_cli", "shell_opaque_or_other"} else "none_observed",
                }
            )
    return mcp, shell


def observe_rollout(rollout: str | Path, run_metadata: Mapping[str, Any]) -> dict[str, Any]:
    """Return the v1-compatible observation using native optional-isError rules."""

    metadata = _validate_metadata(run_metadata)
    rollout_path = Path(rollout)
    records, raw_lines = _read_rollout(rollout_path)
    start, end, boundary, session, context = _find_interval(records, metadata)
    interval = [(index + 1, records[index]) for index in range(start, end + 1)]
    mcp, shell = _collect_operations(interval, metadata)
    outer, blocks = _collect_outer(interval)
    _correlate_delivery(mcp, blocks)
    final = _final_answer(interval)
    usage = _provider_usage(interval, metadata)

    requested_model = metadata.get("requested_model")
    requested_effort = metadata.get("requested_effort")
    deviations: list[dict[str, Any]] = []
    if requested_model is not None and requested_model != context.get("model"):
        deviations.append({"field": "model", "requested": requested_model, "observed": context.get("model")})
    if requested_effort is not None and requested_effort != context.get("effort"):
        deviations.append({"field": "effort", "requested": requested_effort, "observed": context.get("effort")})
    expected_repo = _canonical_repo(metadata["target_repo"])
    if expected_repo is not None:
        for call in mcp:
            actual_repo = _canonical_repo(call["target_repo"])
            if actual_repo is not None and actual_repo != expected_repo:
                deviations.append({"field": "target_repo", "item_id": call["item_id"], "expected_root": expected_repo, "actual_root": actual_repo})

    missing_outer = [item["call_id"] for item in outer if item["output_line"] is None]
    boundary_line = end + 1 if boundary != "missing" else None
    boundary_payload = records[end].get("payload", {}) if boundary != "missing" else {}
    visible_blocks = [{key: value for key, value in block.items() if key != "_parsed"} for block in blocks]
    native_bytes = sum(call["canonical_result_json_bytes"] for call in mcp)
    model_bytes = sum(block["bytes"] for block in blocks)
    shell_bytes = sum(call["stdout_bytes"] + call["stderr_bytes"] for call in shell)
    source_byte_values = [call["relationship_delivery"]["returned_source_text_bytes"] for call in mcp]
    source_bytes_complete = all(value is not None for value in source_byte_values)
    raw_interval = b"".join(raw_lines[start : end + 1])
    interval_hash = hashlib.sha256(raw_interval).hexdigest()
    expected_hash = metadata.get("expected_interval_sha256")
    if expected_hash is not None:
        if not isinstance(expected_hash, str) or len(expected_hash) != 64:
            _error("invalid_metadata", "expected_interval_sha256 must be a 64-character string")
        if expected_hash != interval_hash:
            _error("altered_retained_interval", "selected native interval hash differs from metadata")

    final_required_missing = boundary == "task_complete" and final["status"] == "missing"
    return {
        "schema_version": SCHEMA_VERSION,
        "run": metadata,
        "native_identity": {
            "session_id": session.get("id"),
            "parent_thread_id": session.get("parent_thread_id"),
            "thread_id": metadata["thread_id"],
            "turn_id": metadata["turn_id"],
            "root_turn_id": context.get("root_turn_id"),
            "agent_path": session.get("agent_path"),
            "source": session.get("source"),
            "originator": session.get("originator"),
            "cli_version": session.get("cli_version"),
            "model_provider": session.get("model_provider"),
            "observed_model": context.get("model"),
            "observed_effort": context.get("effort"),
            "session_cwd": context.get("cwd"),
            "condition_deviations": deviations,
        },
        "retained_interval": {
            "start_line": start + 1,
            "end_line": end + 1,
            "record_count": end - start + 1,
            "sha256": interval_hash,
        },
        "outcome": {
            "boundary": boundary,
            "boundary_line": boundary_line,
            "boundary_reason": boundary_payload.get("reason"),
            "duration_ms": boundary_payload.get("duration_ms"),
            "final_answer": final,
            "task_completed": boundary == "task_complete" and final["status"] == "present",
        },
        "mcp_calls": mcp,
        "shell_calls": shell,
        "outer_code_mode": outer,
        "model_output_blocks": visible_blocks,
        "provider_usage": usage,
        "cost": {
            "terminal_mcp_invocations": len(mcp),
            "terminal_shell_commands": len(shell),
            "outer_round_trips": len(outer),
            "canonical_result_json_bytes": native_bytes,
            "model_visible_outer_output_bytes": model_bytes,
            "shell_output_bytes": shell_bytes,
            "returned_source_text_bytes": sum(source_byte_values) if source_bytes_complete else None,
            "returned_source_text_bytes_status": "complete" if source_bytes_complete else "unknown",
            "summed_tool_duration_ms": sum(
                (call.get("completed_at_ms") or 0) - (call.get("started_at_ms") or 0)
                for call in [*mcp, *shell]
                if isinstance(call.get("started_at_ms"), (int, float))
                and isinstance(call.get("completed_at_ms"), (int, float))
            ),
        },
        "integrity": {
            "structural": "valid",
            "native_lifecycle": "terminal_only",
            "upstream_omission_detection": "unsupported",
            "boundary": boundary if boundary != "missing" else "missing",
            "final_answer": final["status"],
            "provider_usage": usage["status"],
            "missing_outer_outputs": missing_outer,
            "condition_deviations": deviations,
            "complete_for_graph_use_claim": (
                boundary == "task_complete"
                and final["status"] == "present"
                and not final_required_missing
                and not missing_outer
                and not deviations
                and all(call["relationship_delivery"]["relationship_shape_status"] == "complete" for call in mcp)
                and not any(call["graph_activity"] == "unknown" for call in shell)
            ),
        },
    }
