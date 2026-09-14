"""Normalize one passive native Codex rollout interval for the adoption audit.

The native rollout is the authority for executed terminal operations.  Outer
Code Mode output is a separate model-delivery boundary: nested MCP events do
not carry an outer call id, so this module correlates only exact payload or
wrapper equality and never invents a temporal parent.
"""
from __future__ import annotations

import argparse
from collections import Counter
from collections.abc import Mapping, Sequence
import hashlib
import json
from pathlib import Path
import sys
from typing import Any


SCHEMA_VERSION = 1
PURPOSES = frozenset(
    {"ordinary", "visibility_diagnostic", "capability_probe", "primary_check", "post_change"}
)
REQUIRED_METADATA = ("run_id", "purpose", "thread_id", "turn_id", "target_repo")
TERMINAL_EVENTS = frozenset({"item_completed", "item_failed"})
BOUNDARY_EVENTS = frozenset({"task_complete", "turn_aborted"})
CONTAINMENT_EDGES = frozenset({"contains"})


class ObservationError(ValueError):
    """A retained rollout or its selection metadata violates the contract."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code


def _error(code: str, message: str) -> None:
    raise ObservationError(code, message)


def _compact(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def _bytes_hash(value: Any) -> tuple[int, str]:
    encoded = _compact(value).encode("utf-8")
    return len(encoded), hashlib.sha256(encoded).hexdigest()


def _canonical_repo(value: Any) -> str | None:
    if not isinstance(value, str) or not value:
        return None
    path = Path(value)
    if not path.is_absolute():
        return None
    return str(path.resolve(strict=False))


def _read_rollout(path: Path) -> tuple[list[dict[str, Any]], list[bytes]]:
    try:
        raw_lines = path.read_bytes().splitlines(keepends=True)
    except OSError as exc:
        _error("rollout_unreadable", str(exc))
    if not raw_lines:
        _error("empty_rollout", f"{path} has no records")

    records: list[dict[str, Any]] = []
    for line_number, raw in enumerate(raw_lines, 1):
        try:
            value = json.loads(raw)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            _error("malformed_jsonl", f"line {line_number}: {exc}")
        if not isinstance(value, dict):
            _error("invalid_record", f"line {line_number} is not an object")
        ordinal = value.get("ordinal")
        if ordinal != line_number - 1:
            _error(
                "noncontiguous_ordinal",
                f"line {line_number} has ordinal {ordinal!r}; expected {line_number - 1}",
            )
        records.append(value)
    return records, raw_lines


def _validate_metadata(metadata: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(metadata, Mapping):
        _error("invalid_metadata", "run metadata must be an object")
    missing = [key for key in REQUIRED_METADATA if key not in metadata]
    if missing:
        _error("missing_metadata", f"missing fields: {', '.join(missing)}")
    result = dict(metadata)
    for key in REQUIRED_METADATA:
        if not isinstance(result[key], str) or not result[key]:
            _error("invalid_metadata", f"{key} must be a non-empty string")
    if result["purpose"] not in PURPOSES:
        _error("invalid_metadata", f"unsupported purpose {result['purpose']!r}")
    try:
        _compact(result)
    except (TypeError, ValueError) as exc:
        _error("invalid_metadata", f"metadata is not JSON serializable: {exc}")
    return result


def _payload(record: Mapping[str, Any], line: int) -> dict[str, Any]:
    value = record.get("payload")
    if not isinstance(value, dict):
        _error("invalid_payload", f"line {line} has no object payload")
    return value


def _find_interval(
    records: Sequence[dict[str, Any]], metadata: Mapping[str, Any]
) -> tuple[int, int, str, dict[str, Any], dict[str, Any]]:
    thread_id, turn_id = metadata["thread_id"], metadata["turn_id"]
    metas = [
        (index, _payload(record, index + 1))
        for index, record in enumerate(records)
        if record.get("type") == "session_meta"
    ]
    if len(metas) != 1:
        _error("invalid_session_metadata", f"expected one session_meta record, found {len(metas)}")
    session = metas[0][1]
    if session.get("id") != thread_id:
        _error(
            "conflicting_metadata",
            f"selected thread {thread_id!r} differs from session id {session.get('id')!r}",
        )

    starts: list[int] = []
    contexts: list[tuple[int, dict[str, Any]]] = []
    for index, record in enumerate(records):
        payload = record.get("payload")
        if not isinstance(payload, dict):
            continue
        if record.get("type") == "event_msg" and payload.get("type") == "task_started":
            if payload.get("turn_id") == turn_id:
                starts.append(index)
        if record.get("type") == "turn_context" and payload.get("turn_id") == turn_id:
            contexts.append((index, payload))
    if len(starts) != 1:
        _error("invalid_task_start", f"expected one selected task_started record, found {len(starts)}")
    if len(contexts) != 1:
        _error("invalid_turn_context", f"expected one selected turn_context record, found {len(contexts)}")
    start = starts[0]
    if contexts[0][0] < start:
        _error("invalid_turn_context", "turn context precedes the selected task start")

    boundary = "missing"
    end = len(records) - 1
    for index in range(start, len(records)):
        record = records[index]
        payload = record.get("payload")
        if (
            record.get("type") == "event_msg"
            and isinstance(payload, dict)
            and payload.get("type") in BOUNDARY_EVENTS
            and payload.get("turn_id") == turn_id
        ):
            end = index
            boundary = str(payload["type"])
            break
    return start, end, boundary, session, contexts[0][1]


def _require_item_fields(item: Mapping[str, Any], fields: Sequence[str], line: int) -> None:
    missing = [field for field in fields if field not in item]
    if missing:
        _error("missing_terminal_field", f"line {line} is missing: {', '.join(missing)}")


def _invocation_category(tool: str, arguments: Mapping[str, Any]) -> str:
    if tool == "loci_get":
        return "type_context_get" if arguments.get("include_type_context") is True else "exact_retrieval"
    if tool == "loci_explore":
        intent = arguments.get("intent")
        if intent == "locate":
            return "explore_locate"
        if intent in {"dependencies", "type_dependencies", "impact", "callers"}:
            return "explore_relationship"
        return "explore_unknown"
    if tool in {
        "loci_graph_neighbors",
        "loci_graph_traverse_neighbors",
        "loci_graph_paths",
        "loci_graph_retrieve",
        "loci_graph_imports",
        "loci_graph_references",
        "loci_graph_calls",
    }:
        return "explicit_graph_query"
    if tool in {"loci_graph_anchors", "loci_graph_health", "loci_store_health"}:
        return "graph_discovery_health"
    if tool in {"loci_search", "loci_get", "loci_outline", "loci_file", "loci_grep"}:
        return "exact_retrieval"
    if tool.startswith("loci_"):
        return "other"
    return "unknown"


def _edge_objects(value: Any) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []

    def visit(node: Any, parent_key: str | None = None) -> None:
        if isinstance(node, dict):
            edge = node.get("edge")
            if isinstance(edge, dict) and isinstance(edge.get("type"), str):
                found.append(edge)
            if (
                parent_key in {"edges", "relationships", "references"}
                and isinstance(node.get("type"), str)
                and ("from" in node or "to" in node)
            ):
                found.append(node)
            for key, child in node.items():
                if key != "edge":
                    visit(child, key)
        elif isinstance(node, list):
            for child in node:
                visit(child, parent_key)

    visit(value)
    unique: dict[str, dict[str, Any]] = {}
    for edge in found:
        unique.setdefault(_compact(edge), edge)
    return list(unique.values())


def _source_text_measure(
    tool: str, structured: Any, *, application_error: bool
) -> tuple[int | None, str]:
    if application_error:
        return 0, "known_source_free_error"
    if not isinstance(structured, dict):
        return None, "unknown_schema"
    texts: list[str] = []
    content = structured.get("content")
    if isinstance(content, str):
        texts.append(content)
    for key, text_key in (("sources", "content"), ("symbols", "source"), ("evidence", "content")):
        values = structured.get(key)
        if isinstance(values, list):
            texts.extend(
                item[text_key]
                for item in values
                if isinstance(item, dict) and isinstance(item.get(text_key), str)
            )
    context = structured.get("type_context")
    if isinstance(context, dict):
        texts.extend(
            item["content"]
            for item in context.get("evidence", [])
            if isinstance(item, dict) and isinstance(item.get("content"), str)
        )
        texts.extend(
            item["source"]
            for item in context.get("symbols", [])
            if isinstance(item, dict) and isinstance(item.get("source"), str)
        )
    if tool in {"loci_graph_references", "loci_graph_calls", "loci_graph_imports"}:
        items = structured.get("items")
        if not isinstance(items, list):
            return None, "unknown_schema"
        for item in items:
            if not isinstance(item, dict):
                return None, "unknown_schema"
            text = item.get("text")
            raw = item.get("raw")
            if isinstance(text, str):
                texts.append(text)
            elif isinstance(raw, dict) and isinstance(raw.get("text"), str):
                texts.append(raw["text"])
            elif isinstance(raw, dict) and isinstance(raw.get("callee_text"), str):
                texts.append(raw["callee_text"])
    known_source_tools = {
        "loci_file",
        "loci_get",
        "loci_explore",
        "loci_graph_neighbors",
        "loci_graph_traverse_neighbors",
        "loci_graph_paths",
        "loci_graph_retrieve",
        "loci_graph_references",
        "loci_graph_calls",
        "loci_graph_imports",
    }
    known_source_free_tools = {
        "loci_search",
        "loci_outline",
        "loci_grep",
        "loci_list",
        "loci_index",
        "loci_verify",
        "loci_stats",
        "loci_analyze",
        "loci_graph_anchors",
        "loci_graph_health",
        "loci_store_health",
    }
    if tool not in known_source_tools | known_source_free_tools:
        return None, "unknown_schema"
    return sum(len(text.encode("utf-8")) for text in texts), "complete"


def _record_relationships(
    structured: Any, tool: str
) -> tuple[list[dict[str, Any]], int, int, int, Counter[str]]:
    """Return declared graph-record relations and resolved/unresolved/unknown counts."""

    if tool not in {"loci_graph_references", "loci_graph_calls", "loci_graph_imports"}:
        return [], 0, 0, 0, Counter()
    if not isinstance(structured, dict) or not isinstance(structured.get("items"), list):
        return [], 0, 0, 1, Counter()
    relationships: list[dict[str, Any]] = []
    unresolved_families: Counter[str] = Counter()
    resolved = unresolved = unknown = 0
    for item in structured["items"]:
        if not isinstance(item, dict) or item.get("status") not in {"resolved", "unresolved"}:
            unknown += 1
            continue
        relation = item.get("relation")
        if not isinstance(relation, str):
            raw = item.get("raw")
            if isinstance(raw, dict) and isinstance(raw.get("relation"), str):
                relation = raw["relation"]
            elif tool == "loci_graph_calls":
                relation = "calls"
            elif tool == "loci_graph_imports":
                relation = "imports_type" if item.get("type_only") is True else "imports"
            elif tool == "loci_graph_references":
                relation = "references"
        if not isinstance(relation, str):
            unknown += 1
            continue
        if item["status"] == "unresolved":
            unresolved += 1
            unresolved_families[relation] += 1
            continue
        source_id = item.get("source_id") or item.get("caller_id")
        target_id = item.get("target_id")
        if not isinstance(source_id, str) or not source_id or not isinstance(target_id, str) or not target_id:
            unknown += 1
            continue
        resolved += 1
        relationships.append({"from": source_id, "to": target_id, "type": relation})
    return relationships, resolved, unresolved, unknown, unresolved_families


def _relationship_delivery(
    result: Mapping[str, Any], arguments: Mapping[str, Any], tool: str
) -> dict[str, Any]:
    structured = result.get("structuredContent")
    if not isinstance(structured, dict):
        structured = None
    application_error = result.get("isError") is True or (
        structured is not None and "error" in structured
    )
    edges = _edge_objects(structured)
    if application_error:
        records, resolved_records, unresolved_records, unknown_records = [], 0, 0, 0
        unresolved_families: Counter[str] = Counter()
    else:
        (
            records,
            resolved_records,
            unresolved_records,
            unknown_records,
            unresolved_families,
        ) = _record_relationships(structured, tool)
    edges.extend(records)
    edges = list({_compact(edge): edge for edge in edges}.values())
    families = Counter(edge.get("type") for edge in edges if isinstance(edge.get("type"), str))
    containment = sum(count for family, count in families.items() if family in CONTAINMENT_EDGES)
    usage = structured.get("usage") if structured else None
    reported = usage.get("evidence_bytes") if isinstance(usage, dict) else None
    if not isinstance(reported, int) or isinstance(reported, bool) or reported < 0:
        reported = None
    reported_output = usage.get("output_bytes") if isinstance(usage, dict) else None
    if reported_output is None and structured:
        budget = structured.get("budget")
        reported_output = budget.get("output_bytes") if isinstance(budget, dict) else None
    if not isinstance(reported_output, int) or isinstance(reported_output, bool) or reported_output < 0:
        reported_output = None
    status = structured.get("status") if structured else None
    type_context = structured.get("type_context") if structured else None
    type_context_status = type_context.get("status") if isinstance(type_context, dict) else None
    source_bytes, source_status = _source_text_measure(
        tool, structured, application_error=application_error
    )
    edge_count: int | None = sum(families.values()) if not unknown_records else None
    semantic_edge_count: int | None = (
        edge_count - containment if edge_count is not None else None
    )
    return {
        "application_error": application_error,
        "result_status": status if isinstance(status, str) else "error" if application_error else "unknown",
        "type_context_status": type_context_status if isinstance(type_context_status, str) else None,
        "edge_families": dict(sorted(families.items())),
        "edge_count": edge_count,
        "semantic_edge_count": semantic_edge_count,
        "containment_edge_count": containment,
        "resolved_record_count": resolved_records,
        "unresolved_record_count": unresolved_records,
        "unresolved_record_families": dict(sorted(unresolved_families.items())),
        "unknown_record_count": unknown_records,
        "relationship_shape_status": "unknown" if unknown_records else "complete",
        "omissions": structured.get("omissions") if structured else None,
        "reported_evidence_bytes": reported,
        "reported_output_bytes": reported_output,
        "returned_source_text_bytes": source_bytes,
        "source_text_bytes_status": source_status,
        "requested_output_budget_bytes": arguments.get("max_output_bytes"),
        "requested_evidence_budget_bytes": arguments.get("max_evidence_bytes"),
        "returned_limits": structured.get("limits") if structured else None,
    }


def _shell_category(item: Mapping[str, Any]) -> str:
    parsed = item.get("parsed_cmd")
    parsed_items = parsed if isinstance(parsed, list) else []
    kinds = {
        part.get("type")
        for part in parsed_items
        if isinstance(part, dict) and isinstance(part.get("type"), str)
    }
    command = item.get("command")
    command_text = " ".join(command) if isinstance(command, list) else str(command)
    if "loci-mcp" in command_text or "loci " in command_text or " -m loci" in command_text:
        return "shell_loci_cli"
    if kinds and kinds <= {"read", "search", "list_files"}:
        return "shell_source_retrieval"
    if "unknown" in kinds or not kinds:
        return "shell_opaque_or_other"
    return "shell_other"


def _output_texts(raw: Any) -> list[str]:
    if isinstance(raw, str):
        return [raw]
    if isinstance(raw, list):
        return [
            item["text"]
            for item in raw
            if isinstance(item, dict)
            and item.get("type") in {"input_text", "text"}
            and isinstance(item.get("text"), str)
        ]
    if raw is None:
        return []
    return [_compact(raw)]


def _contains_exact(node: Any, target: Any) -> bool:
    if node == target:
        return True
    if isinstance(target, (dict, list)) and not target:
        return False
    if isinstance(node, dict):
        return any(_contains_exact(value, target) for value in node.values())
    if isinstance(node, list):
        return any(_contains_exact(value, target) for value in node)
    return False


def _candidate_payloads(result: Mapping[str, Any]) -> list[tuple[str, Any]]:
    candidates: list[tuple[str, Any]] = []
    if "structuredContent" in result:
        candidates.append(("structuredContent", result["structuredContent"]))
    candidates.append(("result", result))
    content = result.get("content")
    if isinstance(content, list):
        for index, block in enumerate(content):
            if isinstance(block, dict) and isinstance(block.get("text"), str):
                candidates.append((f"content[{index}].text", block["text"]))
    return candidates


def _collect_outer(
    interval: Sequence[tuple[int, dict[str, Any]]]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    requests: dict[str, dict[str, Any]] = {}
    all_requests: set[str] = set()
    outputs: list[tuple[int, dict[str, Any]]] = []
    for line, record in interval:
        if record.get("type") != "response_item":
            continue
        payload = _payload(record, line)
        kind, call_id = payload.get("type"), payload.get("call_id")
        if kind in {"custom_tool_call", "function_call"} and isinstance(call_id, str):
            if call_id in all_requests:
                _error("duplicate_outer_request", f"duplicate call id {call_id!r} at line {line}")
            all_requests.add(call_id)
            is_exec = kind == "custom_tool_call" and payload.get("name") == "exec"
            is_wait = kind == "function_call" and payload.get("name") == "wait"
            if is_exec or is_wait:
                requests[call_id] = {
                    "call_id": call_id,
                    "kind": "exec" if is_exec else "wait",
                    "request_line": line,
                    "request": payload.get("input") if is_exec else payload.get("arguments"),
                    "output": None,
                    "output_line": None,
                }
        elif kind in {"custom_tool_call_output", "function_call_output"}:
            if not isinstance(call_id, str):
                _error("invalid_outer_output", f"line {line} has no call id")
            if "output" not in payload:
                _error("missing_outer_output_field", f"line {line} has no output field")
            if not isinstance(payload["output"], (str, list)):
                _error("invalid_outer_output", f"line {line} output must be a string or list")
            outputs.append((line, payload))

    for line, payload in outputs:
        call_id = payload["call_id"]
        request = requests.get(call_id)
        if request is None:
            if call_id in all_requests:
                continue
            _error("unmatched_outer_output", f"line {line} refers to unknown call id {call_id!r}")
        if request["output_line"] is not None:
            _error("duplicate_outer_output", f"call id {call_id!r} has multiple outputs")
        request["output"] = payload["output"]
        request["output_line"] = line

    blocks: list[dict[str, Any]] = []
    for request in requests.values():
        for index, text in enumerate(_output_texts(request["output"])):
            encoded = text.encode("utf-8")
            parsed: Any = None
            try:
                parsed = json.loads(text)
            except (TypeError, json.JSONDecodeError):
                pass
            blocks.append(
                {
                    "call_id": request["call_id"],
                    "output_line": request["output_line"],
                    "block_index": index,
                    "output_ref": f"outer:{request['call_id']}:line:{request['output_line']}:block:{index}",
                    "text": text,
                    "bytes": len(encoded),
                    "sha256": hashlib.sha256(encoded).hexdigest(),
                    "truncated": "Warning: truncated output" in text,
                    "_parsed": parsed,
                }
            )
    return list(requests.values()), blocks


def _collect_operations(
    interval: Sequence[tuple[int, dict[str, Any]]], metadata: Mapping[str, Any]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    mcp: list[dict[str, Any]] = []
    shell: list[dict[str, Any]] = []
    identities: set[str] = set()
    for line, record in interval:
        if record.get("type") != "event_msg":
            continue
        payload = _payload(record, line)
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
            if not isinstance(item["result"].get("content"), list) or not isinstance(
                item["result"].get("isError"), bool
            ):
                _error("invalid_terminal_shape", f"line {line} has invalid native MCP result envelope")
            if "structuredContent" in item["result"] and not isinstance(
                item["result"]["structuredContent"], dict
            ):
                _error("invalid_terminal_shape", f"line {line} has invalid structuredContent")
            response_bytes, response_hash = _bytes_hash(item["result"])
            mcp.append(
                {
                    **common,
                    "server": item["server"],
                    "tool": item["tool"],
                    "arguments": item["arguments"],
                    "target_repo": item["arguments"].get("repo"),
                    "result": item["result"],
                    "canonical_result_json_bytes": response_bytes,
                    "canonical_result_json_sha256": response_hash,
                    "invocation_category": _invocation_category(item["tool"], item["arguments"]),
                    "relationship_delivery": _relationship_delivery(
                        item["result"], item["arguments"], item["tool"]
                    ),
                }
            )
        else:
            _require_item_fields(item, ("command", "cwd", "stdout", "stderr", "exit_code"), line)
            if not isinstance(item["stdout"], str) or not isinstance(item["stderr"], str):
                _error("invalid_terminal_shape", f"line {line} has invalid shell output")
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
                    "invocation_category": _shell_category(item),
                    "graph_activity": "unknown" if _shell_category(item) in {"shell_loci_cli", "shell_opaque_or_other"} else "none_observed",
                }
            )
    return mcp, shell


def _correlate_delivery(mcp: list[dict[str, Any]], blocks: list[dict[str, Any]]) -> None:
    match_users: Counter[tuple[Any, ...]] = Counter()
    for call in mcp:
        matches: list[dict[str, Any]] = []
        for block in blocks:
            for label, candidate in _candidate_payloads(call["result"]):
                exact_text = isinstance(candidate, str) and block["text"] == candidate
                exact_json = block["_parsed"] is not None and _contains_exact(block["_parsed"], candidate)
                if exact_text or exact_json:
                    candidate_hash = hashlib.sha256(_compact(candidate).encode("utf-8")).hexdigest()
                    reference = {
                        "call_id": block["call_id"],
                        "output_line": block["output_line"],
                        "block_index": block["block_index"],
                        "output_ref": block["output_ref"],
                        "match": label if exact_text else f"{label}_json_or_wrapper",
                        "_candidate_hash": candidate_hash,
                    }
                    if reference not in matches:
                        matches.append(reference)
                    break
        call["model_delivery"] = {"status": "pending", "matches": matches}
        for match in matches:
            match_users[
                (match["call_id"], match["output_line"], match["block_index"], match["_candidate_hash"])
            ] += 1

    has_truncation = any(block["truncated"] for block in blocks)
    for call in mcp:
        matches = call["model_delivery"]["matches"]
        if matches:
            ambiguous = any(
                match_users[
                    (match["call_id"], match["output_line"], match["block_index"], match["_candidate_hash"])
                ]
                > 1
                for match in matches
            )
            call["model_delivery"]["status"] = "ambiguous_exact" if ambiguous else "full_exact"
        elif not blocks:
            call["model_delivery"]["status"] = "not_emitted"
        elif has_truncation:
            call["model_delivery"]["status"] = "unknown_truncated"
        else:
            call["model_delivery"]["status"] = "unknown"
        for match in matches:
            match.pop("_candidate_hash", None)


def evidence_registry(observation: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    """Expose unambiguous observer proof IDs for the independent answer reviewer.

    Ambiguous exact matches remain useful visibility evidence in the normalized
    artifact, but they cannot prove which native invocation supplied one output.
    """

    calls = observation.get("mcp_calls")
    if not isinstance(calls, list):
        _error("invalid_observation", "mcp_calls must be a list")
    registry: dict[str, dict[str, Any]] = {}
    for call in calls:
        if not isinstance(call, dict) or not isinstance(call.get("item_id"), str):
            _error("invalid_observation", "mcp_calls contains an invalid item")
        relationship = call.get("relationship_delivery")
        delivery = call.get("model_delivery")
        count = relationship.get("semantic_edge_count") if isinstance(relationship, dict) else None
        if count is not None and (
            not isinstance(count, int) or isinstance(count, bool) or count < 0
        ):
            _error("invalid_observation", f"invalid semantic edge count for {call['item_id']}")
        refs: list[str] = []
        if isinstance(delivery, dict) and delivery.get("status") == "full_exact":
            matches = delivery.get("matches")
            if not isinstance(matches, list):
                _error("invalid_observation", f"invalid model matches for {call['item_id']}")
            refs = [
                match["output_ref"]
                for match in matches
                if isinstance(match, dict) and isinstance(match.get("output_ref"), str)
            ]
        registry[call["item_id"]] = {
            "semantic_relationship_count": count,
            "model_output_refs": refs,
        }
    return registry


def _final_answer(interval: Sequence[tuple[int, dict[str, Any]]]) -> dict[str, Any]:
    answers: list[dict[str, Any]] = []
    for line, record in interval:
        if record.get("type") != "event_msg":
            continue
        payload = _payload(record, line)
        item = payload.get("item")
        if (
            payload.get("type") == "item_completed"
            and isinstance(item, dict)
            and item.get("type") == "AgentMessage"
            and item.get("phase") in {"final", "final_answer"}
        ):
            content = item.get("content")
            if not isinstance(content, list):
                _error("invalid_final_answer", f"line {line} has invalid final content")
            encoded = _compact(content).encode("utf-8")
            answers.append(
                {
                    "status": "present",
                    "line": line,
                    "item_id": item.get("id"),
                    "content": content,
                    "bytes": len(encoded),
                    "sha256": hashlib.sha256(encoded).hexdigest(),
                }
            )
    if len(answers) > 1:
        _error("duplicate_final_answer", "selected interval contains multiple final AgentMessage records")
    return answers[0] if answers else {"status": "missing"}


def _provider_usage(interval: Sequence[tuple[int, dict[str, Any]]], metadata: Mapping[str, Any]) -> dict[str, Any]:
    candidates: list[tuple[int, dict[str, Any]]] = []
    for line, record in interval:
        if record.get("type") != "token_usage_record":
            continue
        payload = _payload(record, line)
        if payload.get("thread_id") == metadata["thread_id"] and payload.get("turn_id") == metadata["turn_id"]:
            candidates.append((line, payload))
    if not candidates:
        return {"status": "missing"}
    line, payload = candidates[-1]
    usage = payload.get("turn_token_usage")
    if not isinstance(usage, dict):
        _error("invalid_provider_usage", f"line {line} has no cumulative turn_token_usage")
    return {
        "status": "available",
        "line": line,
        "response_id": payload.get("response_id"),
        "cumulative": True,
        "usage": usage,
        "snapshots_observed": len(candidates),
    }


def observe_rollout(rollout: str | Path, run_metadata: Mapping[str, Any]) -> dict[str, Any]:
    """Return one validated, normalized native-turn observation artifact."""

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
                deviations.append(
                    {
                        "field": "target_repo",
                        "item_id": call["item_id"],
                        "expected_root": expected_repo,
                        "actual_root": actual_repo,
                    }
                )

    missing_outer = [item["call_id"] for item in outer if item["output_line"] is None]
    boundary_line = end + 1 if boundary != "missing" else None
    boundary_payload = records[end].get("payload", {}) if boundary != "missing" else {}
    visible_blocks = [
        {key: value for key, value in block.items() if key != "_parsed"} for block in blocks
    ]
    native_bytes = sum(call["canonical_result_json_bytes"] for call in mcp)
    model_bytes = sum(block["bytes"] for block in blocks)
    shell_bytes = sum(call["stdout_bytes"] + call["stderr_bytes"] for call in shell)
    source_byte_values = [
        call["relationship_delivery"]["returned_source_text_bytes"] for call in mcp
    ]
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
            "sha256": interval_hash,
            "record_count": end - start + 1,
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
            "returned_source_text_bytes": (
                sum(source_byte_values) if source_bytes_complete else None
            ),
            "returned_source_text_bytes_status": (
                "complete" if source_bytes_complete else "unknown"
            ),
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
                and all(
                    call["relationship_delivery"]["relationship_shape_status"] == "complete"
                    for call in mcp
                )
                and not any(call["graph_activity"] == "unknown" for call in shell)
            ),
        },
    }


def _main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("rollout", type=Path)
    parser.add_argument("metadata", type=Path, help="JSON object selecting run/thread/turn/purpose")
    parser.add_argument("--output", type=Path, help="write normalized JSON here instead of stdout")
    args = parser.parse_args(argv)
    try:
        metadata = json.loads(args.metadata.read_text(encoding="utf-8"))
        artifact = observe_rollout(args.rollout, metadata)
    except (OSError, json.JSONDecodeError, ObservationError) as exc:
        print(str(exc), file=sys.stderr)
        return 2
    rendered = json.dumps(artifact, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.output is None:
        sys.stdout.write(rendered)
    else:
        args.output.write_text(rendered, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
