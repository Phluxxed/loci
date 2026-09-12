#!/usr/bin/env python3
"""Independent, read-only audit for the repaired routing-v2 result bundle.

The checker intentionally does not import the v2 report or replay modules.  It
reconstructs the plan, prompt/binding identities, host lifecycle, provider
payload joins, source spans, routing observations, and simple report totals
from retained files.  With --write it writes the two audit deliverables only
when the batch completion sentinel exists.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
import tarfile
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


COMPARISON = "typescript-context-routing-v2"
PROTOCOL = COMPARISON
RAW_PROTOCOL = "typescript-context-explore-v1"
EXPECTED_RUNS = 102
ARMS = ("A", "B")
EXPECTED_REPETITIONS = (1, 2, 3)
EXPECTED_ENGINE_COMMIT = "c14b2a87a8dde6543c7c790888619bad94711430"
EXPECTED_SOURCE_TREE = "66af207812e18bac099ef46d79a7af68b3655853"
EXPECTED_FREEZE_COMMIT = "35ec08f26f05ee878be03b6798f16cab1e80335e"
EXPECTED_REPAIR_COMMIT = EXPECTED_ENGINE_COMMIT
EXPECTED_EXTRACTOR = 25
EXPECTED_ADAPTER_MODULE = "benchmarks.typescript_context_routing_v2_tools"
HELPERS = {
    "list_mcp_resources",
    "list_mcp_resource_templates",
    "read_mcp_resource",
}
REPOSITORY_TOOLS = {
    "file",
    "get",
    "graph_anchors",
    "graph_calls",
    "graph_imports",
    "graph_neighbors",
    "graph_paths",
    "graph_references",
    "graph_retrieve",
    "graph_traverse_neighbors",
    "grep",
    "loci_explore",
    "outline",
    "search",
}
EXPECTED_REQUEST_TOOLS = {
    ("functions", name) for name in sorted(HELPERS)
} | {("mcp__evaluation", name) for name in sorted(REPOSITORY_TOOLS)}
REQUIRED_ATTEMPT_FILES = (
    "run.json",
    "provenance.json",
    "initial-trace.json",
    "request-audit.json",
    "adapter-trace.json",
    "adapter-trace-copy.json",
    "result.json",
    "events.json",
    "events.jsonl",
    "stderr.txt",
)
MAINTAINED_CASES = {
    "anvil_temporal_arguments",
    "anvil_retrieval_limits",
    "anvil_renderer_result_contract",
}
ENDPOINT_CASES = {
    "exported_arrow",
    "default_identifier",
    "named_function_control",
    "inline_default_control",
}
GENERIC_EXPECTED = {
    "parameter_kind": "local_generic",
    "requires_imported_fields": False,
    "number_round_trip": True,
    "string_round_trip": True,
}


def wire(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), allow_nan=False)


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def digest_file(path: Path) -> str:
    return digest(path.read_bytes())


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def is_int(value: Any) -> bool:
    return type(value) is int


def is_number(value: Any) -> bool:
    return type(value) in (int, float) and math.isfinite(value)


def add_failure(failures: list[dict[str, Any]], category: str, message: str,
                attempt_id: str | None = None, **extra: Any) -> None:
    row: dict[str, Any] = {"category": category, "message": message}
    if attempt_id is not None:
        row["attempt_id"] = attempt_id
    row.update(extra)
    failures.append(row)


def safe_load(path: Path, failures: list[dict[str, Any]], *, attempt_id: str | None = None) -> Any:
    try:
        return load_json(path)
    except (OSError, UnicodeError, json.JSONDecodeError, TypeError) as exc:
        add_failure(failures, "invalid_json", f"{path.name}: {exc}", attempt_id,
                    path=str(path))
        return None


class SnapshotStore:
    """Read frozen snapshot bytes directly from the two committed archives."""

    def __init__(self, corpus_root: Path) -> None:
        self.corpus_root = corpus_root
        self._cache: dict[str, dict[str, bytes]] = {}

    def files(self, snapshot: str) -> dict[str, bytes]:
        if snapshot in self._cache:
            return self._cache[snapshot]
        archive = self.corpus_root / ("anvil.tar.gz" if snapshot == "anvil" else "fixtures.tar.gz")
        prefix = "" if snapshot == "anvil" else snapshot + "/"
        found: dict[str, bytes] = {}
        with tarfile.open(archive, "r:gz") as tar:
            for member in tar.getmembers():
                if not member.isfile() or not member.name.startswith(prefix):
                    continue
                relative = member.name if snapshot == "anvil" else member.name[len(prefix):]
                stream = tar.extractfile(member)
                if stream is not None:
                    found[relative] = stream.read()
        self._cache[snapshot] = found
        return found


def canonical_plan(manifest: Any, freeze: Any, failures: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not isinstance(manifest, dict):
        add_failure(failures, "manifest_invalid", "manifest.json is not an object")
        return []
    if not isinstance(freeze, dict):
        add_failure(failures, "freeze_invalid", "freeze.json is not an object")
        return []
    plan = manifest.get("plan")
    frozen_plan = freeze.get("plan")
    if not isinstance(plan, list):
        add_failure(failures, "plan_invalid", "manifest plan is not a list")
        return []
    if plan != frozen_plan:
        add_failure(failures, "plan_freeze_mismatch", "manifest plan differs from frozen plan")
    if manifest.get("planned_runs") != EXPECTED_RUNS or len(plan) != EXPECTED_RUNS:
        add_failure(failures, "plan_count", "plan does not contain exactly 102 attempts",
                    planned_runs=manifest.get("planned_runs"), plan_length=len(plan))
    ids = [p.get("attempt_id") for p in plan if isinstance(p, dict)]
    if len(ids) != len(set(ids)):
        add_failure(failures, "duplicate_plan_identity", "plan contains duplicate attempt IDs")
    for p in plan:
        if not isinstance(p, dict):
            add_failure(failures, "plan_row_invalid", "plan row is not an object")
            continue
        if p.get("arm") not in ARMS or p.get("repetition") not in EXPECTED_REPETITIONS:
            add_failure(failures, "plan_row_invalid", "plan row has invalid arm or repetition",
                        attempt_id=str(p.get("attempt_id")))
        expected_id = f"{p.get('case_id')}-r{p.get('repetition')}-{p.get('arm')}"
        if p.get("attempt_id") != expected_id:
            add_failure(failures, "plan_identity", "attempt ID does not encode row identity",
                        attempt_id=str(p.get("attempt_id")), expected=expected_id)
    return [p for p in plan if isinstance(p, dict)]


def expected_prompt(corpus: dict[str, Any], controls: dict[str, Any], policy: bytes,
                    case_id: str, arm: str) -> tuple[str, str, str, int]:
    case = next(c for c in corpus["cases"] if c["id"] == case_id)
    base = controls["agent"]["common_prompt"] + case["prompt"]
    effective = base if arm == "A" else policy.decode("utf-8") + "\n" + base
    return base, effective, digest(effective.encode("utf-8")), len(effective.encode("utf-8")) - len(base.encode("utf-8"))


def expected_anchor(case: dict[str, Any]) -> dict[str, Any] | None:
    for item in case.get("context", []):
        if item.get("id") == case.get("anchor"):
            return item
    return None


def source_span_ok(span: Any, files: dict[str, bytes]) -> tuple[bool, str]:
    if not isinstance(span, dict):
        return False, "span is not an object"
    file = span.get("file")
    start, end, text = span.get("start_byte"), span.get("end_byte"), span.get("text")
    if not isinstance(file, str) or file not in files:
        return False, "span file is absent from the frozen snapshot"
    if not is_int(start) or not is_int(end) or start < 0 or end <= start or end > len(files[file]):
        return False, "span byte bounds are invalid"
    if not isinstance(text, str) or not text:
        return False, "span text is missing"
    encoded = text.encode("utf-8")
    if files[file][start:end] != encoded:
        return False, "span text differs from frozen snapshot bytes"
    if span.get("sha256") != digest(encoded) or span.get("sha256") != digest(files[file][start:end]):
        return False, "span hash differs from frozen snapshot bytes"
    return True, "ok"


def payload_texts(call: dict[str, Any]) -> tuple[str, list[str]]:
    result = call.get("result")
    if not isinstance(result, dict):
        error = call.get("error")
        if call.get("status") == "failed" and isinstance(error, dict) and isinstance(error.get("message"), str):
            return "host_error", [error["message"]]
        raise ValueError("tool call has no delivered result")
    structured = result.get("structured_content")
    if structured is not None:
        if not isinstance(structured, dict):
            raise ValueError("structured content is not an object")
        return "compact_json", [wire(structured)]
    content = result.get("content")
    if not isinstance(content, list) or not content or any(
        not isinstance(part, dict) or part.get("type") != "text" or not isinstance(part.get("text"), str)
        for part in content
    ):
        raise ValueError("tool result content is not a non-empty text block list")
    return "text_blocks", [part["text"] for part in content]


def native_payload(call: dict[str, Any]) -> dict[str, Any] | None:
    result = call.get("result")
    if not isinstance(result, dict) or not isinstance(result.get("structured_content"), dict):
        return None
    return {k: v for k, v in result["structured_content"].items() if k != "_evaluation"}


def host_lifecycle(events: Any, failures: list[dict[str, Any]], attempt_id: str) -> dict[str, Any]:
    out: dict[str, Any] = {"thread_id": None, "started": {}, "terminal": {}, "order": [],
                           "turn_completed": [], "valid": True}
    if not isinstance(events, list):
        add_failure(failures, "host_events_invalid", "events.json is not a list", attempt_id)
        out["valid"] = False
        return out
    threads = [e for e in events if isinstance(e, dict) and e.get("type") == "thread.started"]
    if len(threads) != 1 or not isinstance(threads[0].get("thread_id"), str) or not threads[0].get("thread_id"):
        add_failure(failures, "provider_identity", "host stream does not have exactly one thread.started identity", attempt_id)
        out["valid"] = False
    else:
        out["thread_id"] = threads[0]["thread_id"]
    for position, event in enumerate(events):
        if not isinstance(event, dict):
            add_failure(failures, "host_event_invalid", "host event is not an object", attempt_id, position=position)
            out["valid"] = False
            continue
        item = event.get("item")
        if not isinstance(item, dict) or item.get("type") != "mcp_tool_call":
            continue
        item_id = item.get("id")
        if not isinstance(item_id, str) or not item_id:
            add_failure(failures, "provider_identity", "MCP item has no provider item ID", attempt_id, position=position)
            out["valid"] = False
            continue
        event_type = event.get("type")
        if event_type == "item.started":
            if item_id in out["started"]:
                add_failure(failures, "host_lifecycle", "duplicate item.started", attempt_id, item=item_id)
                out["valid"] = False
            out["started"][item_id] = (position, item)
        elif event_type in {"item.completed", "item.failed"}:
            if item_id in out["terminal"]:
                add_failure(failures, "host_lifecycle", "duplicate terminal event", attempt_id, item=item_id)
                out["valid"] = False
            out["terminal"][item_id] = (position, item, event_type)
            out["order"].append(item_id)
            if item_id not in out["started"]:
                add_failure(failures, "host_lifecycle", "terminal event has no preceding start", attempt_id, item=item_id)
                out["valid"] = False
            if event_type == "item.failed" and item.get("status") != "failed":
                add_failure(failures, "host_lifecycle", "item.failed lacks status=failed", attempt_id, item=item_id)
                out["valid"] = False
            if event_type == "item.completed" and item.get("status") not in {"completed", "failed"}:
                add_failure(failures, "host_lifecycle", "item.completed has invalid terminal status", attempt_id, item=item_id)
                out["valid"] = False
        elif event_type not in {"item.started", "item.completed", "item.failed"}:
            add_failure(failures, "host_lifecycle", "MCP item has invalid event type", attempt_id,
                        item=item_id, event_type=event_type)
            out["valid"] = False
    for item_id, (position, item, _event_type) in out["terminal"].items():
        start = out["started"].get(item_id)
        if start is None:
            continue
        if start[0] >= position:
            add_failure(failures, "host_lifecycle", "terminal precedes start", attempt_id, item=item_id)
            out["valid"] = False
        if any(start[1].get(k) != item.get(k) for k in ("server", "tool", "arguments")):
            add_failure(failures, "host_lifecycle", "tool request changed between start and terminal", attempt_id, item=item_id)
            out["valid"] = False
        if not isinstance(item.get("server"), str) or not isinstance(item.get("tool"), str) or not isinstance(item.get("arguments"), dict):
            add_failure(failures, "host_lifecycle", "terminal tool request fields are invalid", attempt_id, item=item_id)
            out["valid"] = False
    for item_id in out["started"]:
        if item_id not in out["terminal"]:
            add_failure(failures, "host_lifecycle", "started tool has no terminal event", attempt_id, item=item_id)
            out["valid"] = False
    out["turn_completed"] = [e for e in events if isinstance(e, dict) and e.get("type") == "turn.completed"]
    if not events or events[-1].get("type") != "turn.completed" or not out["turn_completed"]:
        add_failure(failures, "session_close", "host stream does not close with turn.completed", attempt_id)
        out["valid"] = False
    return out


def compare_request(audit: Any, provenance: dict[str, Any], base: str, effective: str,
                    expected_schema: str, expected_prompt_hash: str, failures: list[dict[str, Any]],
                    attempt_id: str) -> dict[str, Any]:
    if not isinstance(audit, dict) or not isinstance(audit.get("request"), dict):
        add_failure(failures, "request_binding", "request audit is missing request object", attempt_id)
        return {"valid": False, "tools": []}
    request = audit["request"]
    valid = True
    if audit.get("request_sha256") != digest(wire(request).encode("utf-8")):
        add_failure(failures, "request_binding", "request digest mismatch", attempt_id); valid = False
    if audit.get("prompt_sha256") not in {None, expected_prompt_hash}:
        add_failure(failures, "prompt_binding", "audited prompt hash differs from expected", attempt_id); valid = False
    if request.get("model") != "gpt-5.6-luna" or request.get("reasoning", {}).get("effort") != "high":
        add_failure(failures, "request_binding", "request model/reasoning differs from frozen control", attempt_id); valid = False
    inputs = request.get("input")
    if not isinstance(inputs, list) or not inputs or inputs[-1].get("content") != [{"type": "input_text", "text": effective}]:
        add_failure(failures, "prompt_binding", "effective prompt differs from retained request", attempt_id); valid = False
    texts = []
    for item in inputs if isinstance(inputs, list) else []:
        for part in item.get("content", []) if isinstance(item, dict) else []:
            if isinstance(part, dict) and isinstance(part.get("text"), str):
                texts.append(part["text"])
    for marker in ("# AGENTS.md instructions", "## Brain Context", "Anvil Continuity Frame",
                   "<skills_instructions>", "LOCI_ADAPTER_READY"):
        if any(marker in t for t in texts):
            add_failure(failures, "ambient_context", "ambient context marker appears in request", attempt_id, marker=marker)
            valid = False
    tool_rows = audit.get("tools")
    tools = [tuple(row) for row in tool_rows if isinstance(row, list) and len(row) == 2] if isinstance(tool_rows, list) else []
    if set(tools) != EXPECTED_REQUEST_TOOLS or len(tools) != len(EXPECTED_REQUEST_TOOLS):
        add_failure(failures, "tool_schema_binding", "request exposed a different tool set", attempt_id,
                    actual=sorted(tools), expected=sorted(EXPECTED_REQUEST_TOOLS)); valid = False
    if audit.get("canonical_tool_schemas_sha256") != expected_schema or provenance.get("canonical_tool_schemas_sha256") != expected_schema:
        add_failure(failures, "tool_schema_binding", "canonical tool schema hash differs from frozen binding", attempt_id); valid = False
    if audit.get("resource_helpers") != "Only evaluation server configured; no resources or templates exposed.":
        add_failure(failures, "resource_binding", "resource helper declaration differs", attempt_id); valid = False
    return {"valid": valid, "tools": tools, "base_prompt": base, "effective_prompt": effective}


def validate_trace(raw: Any, trace_copy: Any, result: dict[str, Any], run: dict[str, Any], plan: dict[str, Any],
                   snapshot_files: dict[str, bytes], failures: list[dict[str, Any]], attempt_id: str) -> dict[str, Any]:
    if raw != trace_copy:
        add_failure(failures, "trace_copy", "adapter-trace.json differs from adapter-trace-copy.json", attempt_id)
    if not isinstance(raw, dict):
        add_failure(failures, "trace_identity", "adapter trace is not an object", attempt_id)
        return {"events": [], "deliveries": [], "by_event": {}, "by_attempt": {}}
    identity = raw.get("identity")
    if raw.get("schema_version") != 3 or raw.get("protocol") != RAW_PROTOCOL:
        add_failure(failures, "trace_schema", "adapter trace schema/protocol differs", attempt_id)
    if identity != result.get("identity"):
        add_failure(failures, "trace_identity", "adapter trace identity differs from result", attempt_id)
    events = raw.get("events") if isinstance(raw.get("events"), list) else []
    deliveries = raw.get("deliveries") if isinstance(raw.get("deliveries"), list) else []
    if raw.get("attempts") != len(deliveries):
        add_failure(failures, "trace_accounting", "adapter attempt count differs from deliveries", attempt_id)
    event_links = [d.get("trace_event_id") for d in deliveries if d.get("trace_event_id") is not None]
    if len(event_links) != len(events) or set(event_links) != {e.get("id") for e in events}:
        add_failure(failures, "trace_accounting", "source events and delivery event links differ", attempt_id)
    sid = identity.get("session_id") if isinstance(identity, dict) else None
    by_event: dict[str, dict[str, Any]] = {}
    by_attempt: dict[str, dict[str, Any]] = {}
    expected_event_ids = [f"{sid}:{i}" for i in range(1, len(events) + 1)]
    for i, event in enumerate(events):
        if not isinstance(event, dict):
            add_failure(failures, "trace_event", "trace event is not an object", attempt_id, index=i); continue
        event_id = event.get("id")
        if event_id != expected_event_ids[i]:
            add_failure(failures, "trace_event", "trace event identity/order differs", attempt_id, index=i, actual=event_id, expected=expected_event_ids[i])
        if event_id in by_event:
            add_failure(failures, "trace_event", "duplicate trace event ID", attempt_id, event=event_id)
        by_event[event_id] = event
        for key in ("task_id", "session_id", "arm", "repetition", "snapshot", "corpus_sha256", "controls_sha256", "controls_version"):
            if isinstance(identity, dict) and event.get(key) != identity.get(key):
                add_failure(failures, "trace_identity", f"trace event {key} differs", attempt_id, event=event_id)
        spans = event.get("spans")
        if not isinstance(spans, list):
            add_failure(failures, "source_span", "trace event spans is not a list", attempt_id, event=event_id); continue
        source_total = 0
        for span in spans:
            ok, reason = source_span_ok(span, snapshot_files)
            if not ok:
                add_failure(failures, "source_span", reason, attempt_id, event=event_id)
            if isinstance(span, dict) and isinstance(span.get("text"), str):
                source_total += len(span["text"].encode("utf-8"))
        if event.get("source_bytes") != source_total:
            add_failure(failures, "source_span", "trace event source_bytes differs from span bytes", attempt_id, event=event_id)
        response_json = event.get("response_json")
        if not isinstance(response_json, str) or digest(response_json.encode("utf-8")) is None:
            add_failure(failures, "native_payload", "trace event response_json is invalid", attempt_id, event=event_id)
        else:
            try: json.loads(response_json)
            except json.JSONDecodeError: add_failure(failures, "native_payload", "trace event response_json is not JSON", attempt_id, event=event_id)
        if not is_int(event.get("serialized_bytes")) or event.get("serialized_bytes") != len(response_json.encode("utf-8")):
            add_failure(failures, "native_payload", "trace serialized_bytes differs from response_json", attempt_id, event=event_id)
    expected_attempt_ids = [f"{sid}/attempt/{i}" for i in range(1, len(deliveries) + 1)]
    for i, delivery in enumerate(deliveries):
        if not isinstance(delivery, dict):
            add_failure(failures, "delivery_join", "delivery is not an object", attempt_id, index=i); continue
        delivery_id = delivery.get("attempt_id")
        if delivery_id != expected_attempt_ids[i]:
            add_failure(failures, "delivery_join", "delivery attempt identity/order differs", attempt_id, index=i, actual=delivery_id, expected=expected_attempt_ids[i])
        if delivery_id in by_attempt:
            add_failure(failures, "delivery_join", "duplicate delivery attempt ID", attempt_id, delivery=delivery_id)
        by_attempt[delivery_id] = delivery
        event_id = delivery.get("trace_event_id")
        event = by_event.get(event_id)
        if event_id is None and delivery.get("status") == "rejected":
            # A rejected adapter operation still delivers and charges its exact
            # structured error. It does not invent a successful source event.
            rejected = json.loads(delivery.get("response_json", "{}"))
            error = rejected.get("error")
            if (not isinstance(error, dict) or not error.get("code") or not error.get("message")
                    or rejected.get("_evaluation", {}).get("attempt_id") != delivery_id
                    or delivery.get("spans") != [] or delivery.get("source_bytes") != 0
                    or delivery.get("serialized_bytes") != len(delivery["response_json"].encode("utf-8"))
                    or not is_number(delivery.get("elapsed_ms")) or delivery["elapsed_ms"] < 0):
                add_failure(failures, "delivery_join", "rejected source-free delivery is invalid", attempt_id, delivery=delivery_id)
            continue
        if event is None:
            add_failure(failures, "delivery_join", "delivery has no matching trace event", attempt_id, delivery=delivery_id)
            continue
        # The adapter's delivery records preserve the logical trace operation
        # and effective arguments, while the raw event may carry the host
        # operation name and its explicit arguments.  Payload bytes, source
        # bytes, and spans are the exact join evidence shared by both records.
        for key in ("response_json", "serialized_bytes", "source_bytes", "spans"):
            if delivery.get(key) != event.get(key):
                add_failure(failures, "delivery_join", f"delivery/event {key} differs", attempt_id, delivery=delivery_id)
        if not (is_number(delivery.get("elapsed_ms")) and delivery.get("elapsed_ms") >= event.get("elapsed_ms", 0)):
            add_failure(failures, "delivery_join", "delivery elapsed time is not valid relative to trace event", attempt_id, delivery=delivery_id)
    return {"events": events, "deliveries": deliveries, "by_event": by_event, "by_attempt": by_attempt}


def source_anchor_proof(case: dict[str, Any], call: dict[str, Any], accounting_row: dict[str, Any] | None,
                        trace: dict[str, Any], snapshot_files: dict[str, bytes]) -> dict[str, Any]:
    anchor = expected_anchor(case)
    payload = native_payload(call)
    proof: dict[str, Any] = {
        "native_anchor_id": None,
        "native_status": call.get("status"),
        "source_id": None,
        "source_start_byte": None,
        "source_end_byte": None,
        "trace_event_id": accounting_row.get("trace_event_id") if isinstance(accounting_row, dict) else None,
        "requested_anchor_received": False,
        "anchor_complete": False,
        "reason": "native_payload_absent",
    }
    if not isinstance(anchor, dict):
        proof["reason"] = "anchor_declaration_missing"
        return proof
    symbol = anchor.get("symbol") or {}
    if isinstance(payload, dict):
        proof["native_status"] = payload.get("status")
    native_id = None
    item = None
    if isinstance(payload, dict) and isinstance(payload.get("items"), list):
        matches = [x for x in payload["items"] if isinstance(x, dict)
                   and x.get("role") == "anchor" and x.get("id") == anchor.get("native_id", x.get("id"))
                   and x.get("name") == symbol.get("name") and x.get("kind") == symbol.get("kind")
                   and x.get("file") == anchor.get("file")]
        # The corpus does not store native_id; exact ID is the conventional
        # file::symbol#kind form derived from the declared symbol.
        expected_native = f"{anchor.get('file')}::{symbol.get('name')}#{symbol.get('kind')}"
        matches = [x for x in payload["items"] if isinstance(x, dict)
                   and x.get("role") == "anchor" and x.get("id") == expected_native
                   and x.get("name") == symbol.get("name") and x.get("kind") == symbol.get("kind")
                   and x.get("file") == anchor.get("file")]
        if len(matches) == 1:
            item = matches[0]; native_id = expected_native
    proof["native_anchor_id"] = native_id
    if item is None or not isinstance(payload, dict):
        proof["reason"] = "requested_anchor_not_in_native_items"
        return proof
    source_id = item.get("source_id")
    proof["source_id"] = source_id
    sources = payload.get("sources")
    if not is_int(source_id) or not isinstance(sources, list):
        proof["reason"] = "native_source_record_missing"
        return proof
    matching = [x for x in sources if isinstance(x, dict) and x.get("id") == source_id]
    if len(matching) != 1:
        proof["reason"] = "native_source_id_not_unique"
        return proof
    source = matching[0]
    start, end = source.get("start_byte"), source.get("end_byte")
    proof["source_start_byte"], proof["source_end_byte"] = start, end
    file = anchor.get("file")
    content = source.get("content")
    if file not in snapshot_files or not isinstance(content, str) or not is_int(start) or not is_int(end):
        proof["reason"] = "native_source_bounds_invalid"
        return proof
    expected_bytes = snapshot_files[file]
    content_bytes = content.encode("utf-8")
    if source.get("file") != file or start != anchor.get("start_byte") or end <= start or end > anchor.get("end_byte") or expected_bytes[start:end] != content_bytes:
        proof["reason"] = "native_source_span_mismatch"
        return proof
    if source.get("content_hash") != digest(expected_bytes):
        proof["reason"] = "native_source_file_hash_mismatch"
        return proof
    event = trace.get("by_event", {}).get(proof["trace_event_id"])
    if not isinstance(event, dict) or not any(
        isinstance(s, dict) and s.get("file") == file and s.get("start_byte") == start
        and s.get("end_byte") == end and s.get("text") == content
        and s.get("sha256") == digest(content_bytes)
        for s in event.get("spans", [])
    ):
        proof["reason"] = "requested_anchor_trace_span_missing"
        return proof
    proof["requested_anchor_received"] = True
    proof["anchor_complete"] = end == anchor.get("end_byte") and item.get("complete") is True
    proof["reason"] = "ok"
    return proof


def validate_attempt(root: Path, plan: dict[str, Any], corpus: dict[str, Any], controls: dict[str, Any],
                     freeze: dict[str, Any], manifest: dict[str, Any], snapshots: SnapshotStore,
                     policy: bytes, prompt_manifest: Any, failures: list[dict[str, Any]]) -> dict[str, Any]:
    attempt_id = str(plan.get("attempt_id"))
    folder = root / attempt_id
    local_before = len(failures)
    row: dict[str, Any] = {"attempt_id": attempt_id, "case_id": plan.get("case_id"),
                           "arm": plan.get("arm"), "repetition": plan.get("repetition"),
                           "complete": False, "routing": None, "host": {}, "source_spans": 0}
    loaded: dict[str, Any] = {}
    for name in REQUIRED_ATTEMPT_FILES:
        path = folder / name
        if not path.is_file():
            add_failure(failures, "missing_artifact", f"missing {name}", attempt_id, path=str(path))
        elif name.endswith(".json"):
            loaded[name] = safe_load(path, failures, attempt_id=attempt_id)
    if not all(name in loaded for name in ("run.json", "provenance.json", "result.json", "adapter-trace.json", "events.json")):
        row["failure_count"] = len(failures) - local_before
        return row
    run, provenance, result = loaded["run.json"], loaded["provenance.json"], loaded["result.json"]
    raw, host_events = loaded["adapter-trace.json"], loaded["events.json"]
    if not all(isinstance(x, dict) for x in (run, provenance, result, raw)):
        add_failure(failures, "artifact_schema", "core artifact is not an object", attempt_id)
        row["failure_count"] = len(failures) - local_before
        return row
    case = next((c for c in corpus.get("cases", []) if c.get("id") == plan.get("case_id")), None)
    if case is None:
        add_failure(failures, "case_binding", "plan case is absent from corpus", attempt_id)
        row["failure_count"] = len(failures) - local_before
        return row
    snapshot = str(plan.get("snapshot"))
    frozen_files_meta = corpus.get("snapshots", {}).get(snapshot, {}).get("files", {})
    snapshot_files = snapshots.files(snapshot)
    for name, expected_hash in frozen_files_meta.items():
        if name not in snapshot_files:
            add_failure(failures, "snapshot_binding", "frozen snapshot file absent from archive", attempt_id, file=name)
        elif digest(snapshot_files[name]) != expected_hash:
            add_failure(failures, "snapshot_binding", "snapshot archive file hash differs from corpus", attempt_id, file=name)
    if set(snapshot_files) != set(frozen_files_meta):
        add_failure(failures, "snapshot_binding", "snapshot archive file inventory differs from corpus", attempt_id)
    expected_identity = {"task_id": plan.get("case_id"), "arm": plan.get("arm"), "repetition": plan.get("repetition"), "snapshot": snapshot}
    if run.get("attempt_id") != attempt_id or run.get("case_id") != plan.get("case_id") or run.get("arm") != plan.get("arm") or run.get("repetition") != plan.get("repetition"):
        add_failure(failures, "identity", "run.json identity differs from plan", attempt_id)
    for obj_name, obj in (("provenance", provenance), ("result", result)):
        if obj.get("attempt_id") != attempt_id or obj.get("case_id", obj.get("identity", {}).get("task_id")) != plan.get("case_id") or obj.get("arm", obj.get("identity", {}).get("arm")) != plan.get("arm"):
            add_failure(failures, "identity", f"{obj_name} identity differs from plan", attempt_id)
    identity = result.get("identity")
    if not isinstance(identity, dict):
        add_failure(failures, "identity", "result identity is missing", attempt_id)
        identity = {}
    for key, expected in expected_identity.items():
        if identity.get(key) != expected:
            add_failure(failures, "identity", f"result identity {key} differs", attempt_id)
    if result.get("provenance") != provenance:
        add_failure(failures, "provenance", "result provenance differs from provenance.json", attempt_id)
    if raw.get("identity") != identity:
        add_failure(failures, "identity", "raw trace identity differs from result", attempt_id)
    if result.get("schema_version") != 3 or result.get("protocol") != PROTOCOL:
        add_failure(failures, "result_schema", "result schema/protocol differs from routing-v2", attempt_id)
    if run.get("session_id") != identity.get("session_id") or provenance.get("session_id") not in {None, identity.get("session_id")}:
        add_failure(failures, "identity", "session ID differs across retained artifacts", attempt_id)
    trace_path = run.get("trace_path")
    if not isinstance(trace_path, str) or Path(trace_path).name != "adapter-trace.json":
        add_failure(failures, "identity", "run trace_path does not name adapter-trace.json", attempt_id)
    source = provenance.get("source")
    expected_engine = {"commit": EXPECTED_ENGINE_COMMIT, "source_tree": EXPECTED_SOURCE_TREE, "extractor_version": EXPECTED_EXTRACTOR}
    if not isinstance(source, dict) or source.get("engine") != expected_engine or source.get("freeze_commit") != EXPECTED_FREEZE_COMMIT or provenance.get("extractor_version") != EXPECTED_EXTRACTOR:
        add_failure(failures, "engine_binding", "provenance engine/freeze identity differs", attempt_id)
    if provenance.get("snapshot") != snapshot or provenance.get("snapshot_files") != frozen_files_meta:
        add_failure(failures, "snapshot_binding", "provenance snapshot identity differs", attempt_id)
    corpus_sha = digest((root.parent.parent / "corpora" / "typescript-context-v3" / "corpus.json").read_bytes())
    controls_sha = digest((root.parent.parent / "corpora" / "typescript-context-v3" / "comparison-controls.json").read_bytes())
    if provenance.get("corpus_sha256") != corpus_sha or provenance.get("controls_sha256") != controls_sha:
        add_failure(failures, "freeze_binding", "provenance corpus/control hash differs", attempt_id)
    if provenance.get("adapter_module") != EXPECTED_ADAPTER_MODULE:
        add_failure(failures, "engine_binding", "adapter module differs", attempt_id)
    expected_catalog = manifest.get("catalog_sha256")
    if provenance.get("catalog_sha256") != expected_catalog:
        add_failure(failures, "catalog_binding", "provenance catalog hash differs", attempt_id)
    expected_runner = freeze.get("harness_files", {}).get("benchmarks/typescript_context_compare.py")
    if expected_runner is not None and provenance.get("runner_sha256") != expected_runner:
        add_failure(failures, "engine_binding", "runner hash differs from frozen harness", attempt_id)
    expected_schema = freeze.get("canonical_tool_schemas_sha256", {}).get(plan.get("arm"))
    try:
        base_prompt, effective_prompt, prompt_hash, prefix_bytes = expected_prompt(corpus, controls, policy, plan["case_id"], plan["arm"])
    except Exception as exc:
        add_failure(failures, "prompt_binding", f"could not reconstruct prompt: {exc}", attempt_id)
        base_prompt, effective_prompt, prompt_hash, prefix_bytes = "", "", "", 0
    route_identity = provenance.get("routing")
    expected_route_identity = {
        "version": COMPARISON,
        "condition": plan.get("arm"),
        "policy_sha256": freeze.get("policy_sha256") if plan.get("arm") == "B" else None,
        "base_prompt_sha256": digest(base_prompt.encode("utf-8")),
        "effective_prompt_sha256": prompt_hash,
        "candidate_prefix_utf8_bytes": prefix_bytes,
        "capability_arm": "B",
    }
    if route_identity != expected_route_identity:
        add_failure(failures, "prompt_binding", "routing prompt identity differs from frozen policy", attempt_id)
    if isinstance(prompt_manifest, dict):
        if prompt_manifest.get("version") != COMPARISON or prompt_manifest.get("policy_sha256") != freeze.get("policy_sha256"):
            add_failure(failures, "prompt_binding", "prompt manifest identity differs", attempt_id)
        manifest_case = next((x for x in prompt_manifest.get("cases", []) if x.get("case_id") == plan.get("case_id")), None)
        if not isinstance(manifest_case, dict) or manifest_case.get("prompts", {}).get(plan.get("arm"), {}).get("sha256") != prompt_hash:
            add_failure(failures, "prompt_binding", "prompt manifest case hash differs", attempt_id)
    request_result = compare_request(loaded.get("request-audit.json"), provenance, base_prompt, effective_prompt,
                                     str(expected_schema), prompt_hash, failures, attempt_id)
    trace = validate_trace(raw, loaded.get("adapter-trace-copy.json"), result, run, plan, snapshot_files, failures, attempt_id)
    lifecycle = host_lifecycle(host_events, failures, attempt_id)
    row["host"] = {"thread_id": lifecycle.get("thread_id"), "terminal_calls": len(lifecycle.get("order", [])), "valid": lifecycle.get("valid")}
    if result.get("baseline", {}).get("provider_thread_id") != lifecycle.get("thread_id"):
        add_failure(failures, "provider_identity", "baseline provider_thread_id differs from thread.started", attempt_id)
    # events.jsonl must be byte-for-byte equivalent at the JSON value level.
    try:
        lines = [json.loads(line) for line in (folder / "events.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
        if lines != host_events:
            add_failure(failures, "host_events", "events.jsonl differs from events.json", attempt_id)
    except Exception as exc:
        add_failure(failures, "host_events", f"events.jsonl cannot be parsed: {exc}", attempt_id)
    accounting = result.get("baseline", {}).get("output_accounting")
    if not isinstance(accounting, dict) or not isinstance(accounting.get("calls"), list):
        add_failure(failures, "accounting", "baseline output accounting is missing", attempt_id)
        accounting = {"calls": [], "complete": False}
    rows_by_item = {r.get("item_id"): r for r in accounting.get("calls", []) if isinstance(r, dict)}
    expected_rows: list[dict[str, Any]] = []
    helper_count = 0
    explore_repo_calls: list[tuple[str, dict[str, Any], dict[str, Any] | None]] = []
    for item_id in lifecycle.get("order", []):
        _, call, event_type = lifecycle["terminal"][item_id]
        try:
            payload_format, texts = payload_texts(call)
        except Exception as exc:
            payload_format, texts = "unknown", None
            add_failure(failures, "native_payload", str(exc), attempt_id, item=item_id)
        native_bytes = sum(len(t.encode("utf-8")) for t in texts) if isinstance(texts, list) else None
        row_account = rows_by_item.get(item_id)
        if row_account is None:
            add_failure(failures, "delivery_join", "host terminal call has no accounting row", attempt_id, item=item_id)
        else:
            for key, expected in (("server", call.get("server")), ("tool", call.get("tool")), ("arguments", call.get("arguments")), ("status", call.get("status")), ("payload_format", payload_format), ("payload_texts", texts), ("serialized_bytes", native_bytes)):
                if row_account.get(key) != expected:
                    add_failure(failures, "delivery_join", f"accounting row {key} differs from native host call", attempt_id, item=item_id)
        expected_rows.append(row_account if row_account is not None else {"item_id": item_id, "server": call.get("server"), "tool": call.get("tool"), "arguments": call.get("arguments"), "status": call.get("status")})
        if call.get("tool") in HELPERS:
            helper_count += 1
        structured = call.get("result", {}).get("structured_content") if isinstance(call.get("result"), dict) else None
        if isinstance(structured, dict):
            evaluation = structured.get("_evaluation")
            if not isinstance(evaluation, dict) or not isinstance(evaluation.get("attempt_id"), str):
                add_failure(failures, "delivery_join", "structured provider result lacks evaluator attempt identity", attempt_id, item=item_id)
            else:
                delivery = trace.get("by_attempt", {}).get(evaluation["attempt_id"])
                if not isinstance(delivery, dict):
                    add_failure(failures, "delivery_join", "provider result attempt has no raw delivery", attempt_id, item=item_id)
                else:
                    event = trace.get("by_event", {}).get(delivery.get("trace_event_id"))
                    rejected_without_source = (delivery.get("status") == "rejected"
                        and delivery.get("trace_event_id") is None and event is None
                        and delivery.get("spans") == [] and delivery.get("source_bytes") == 0
                        and isinstance(structured.get("error"), dict))
                    if delivery.get("response_json") != (texts or [None])[0] or not (
                        rejected_without_source or isinstance(event, dict)
                        and delivery.get("trace_event_id") == event.get("id")
                    ):
                        add_failure(failures, "delivery_join", "native provider payload differs from raw delivery/event", attempt_id, item=item_id)
                    # Raw delivery operation/arguments are adapter-level
                    # effective values; the host item uses the MCP request
                    # spelling and may omit adapter defaults.  Join exact
                    # native payload/trace identity above, then ensure any
                    # explicitly supplied host arguments retain their values.
                    host_args = call.get("arguments") if isinstance(call.get("arguments"), dict) else {}
                    raw_args = delivery.get("arguments") if isinstance(delivery.get("arguments"), dict) else {}
                    for arg_name, arg_value in host_args.items():
                        if call.get("tool") == "loci_explore" and arg_value is None:
                            defaults = {"max_output_bytes": 16_384, "max_evidence_bytes": 8_192}
                            arg_value = defaults.get(arg_name, arg_value)
                        if arg_name in raw_args and raw_args[arg_name] != arg_value:
                            add_failure(failures, "delivery_join", "native call argument value differs from raw delivery", attempt_id, item=item_id, argument=arg_name)
                    if row_account is not None and row_account.get("attempt_id") != evaluation.get("attempt_id"):
                        add_failure(failures, "delivery_join", "accounting row delivery identity differs", attempt_id, item=item_id)
                    if row_account is not None and row_account.get("trace_event_id") != delivery.get("trace_event_id"):
                        add_failure(failures, "delivery_join", "accounting row trace identity differs", attempt_id, item=item_id)
        if call.get("tool") == "loci_explore":
            explore_repo_calls.append((item_id, call, row_account))
    explore_proofs = [source_anchor_proof(case, call, row_account, trace, snapshot_files)
                      for _item_id, call, row_account in explore_repo_calls]
    if len(rows_by_item) != len(lifecycle.get("order", [])):
        add_failure(failures, "accounting", "accounting rows do not match host terminal call count", attempt_id)
    measured_accounting = result.get("baseline", {}).get("output_accounting", {})
    serialized_sum = sum(r.get("serialized_bytes", 0) or 0 for r in expected_rows if isinstance(r, dict))
    source_sum = sum(r.get("source_bytes", 0) or 0 for r in expected_rows if isinstance(r, dict))
    accounting_complete = bool(measured_accounting.get("complete"))
    for key, expected in (("tool_call_count", len(lifecycle.get("order", []))), ("recorded_payload_bytes", serialized_sum), ("complete_payload_bytes", serialized_sum if accounting_complete else None), ("source_bytes", source_sum if accounting_complete else None)):
        if measured_accounting.get(key) != expected:
            add_failure(failures, "accounting", f"baseline accounting {key} differs from retained calls", attempt_id)
    if measured_accounting.get("calls") != expected_rows:
        add_failure(failures, "accounting", "baseline accounting call rows differ from independently joined rows", attempt_id)
    measurement = result.get("measurement", {})
    turns = lifecycle.get("turn_completed", [])
    usage = turns[-1].get("usage") if turns and isinstance(turns[-1], dict) else None
    if not isinstance(usage, dict):
        add_failure(failures, "usage", "terminal turn has no provider usage", attempt_id)
    elif measurement.get("provider_usage") != usage:
        add_failure(failures, "usage", "measurement provider usage differs from terminal turn usage", attempt_id)
    for key in ("input_tokens", "cached_input_tokens", "cache_write_input_tokens", "output_tokens", "reasoning_output_tokens"):
        if not isinstance(measurement.get("provider_usage", {}).get(key), int) or measurement["provider_usage"][key] < 0:
            add_failure(failures, "usage", f"provider usage {key} is not a nonnegative integer", attempt_id)
    if isinstance(measurement.get("provider_usage"), dict) and measurement["provider_usage"].get("cached_input_tokens", 0) > measurement["provider_usage"].get("input_tokens", 0):
        add_failure(failures, "usage", "cached input exceeds gross input", attempt_id)
    expected_complete = accounting_complete and isinstance(usage, dict)
    if measurement.get("measurement_complete") is not expected_complete or measurement.get("read_count") != len(lifecycle.get("order", [])):
        add_failure(failures, "measurement", "measurement completeness or call total differs", attempt_id)
    if measurement.get("serialized_tool_output_bytes") != measured_accounting.get("complete_payload_bytes") or measurement.get("source_bytes") != measured_accounting.get("source_bytes"):
        add_failure(failures, "measurement", "measurement byte totals differ from accounting", attempt_id)
    if result.get("events") != raw.get("events"):
        add_failure(failures, "trace_join", "result events differ from adapter trace events", attempt_id)
    # Reconstruct only the routing observation fields; this does not rescore answers.
    repo_calls = [(item_id, lifecycle["terminal"][item_id][1], rows_by_item.get(item_id)) for item_id in lifecycle.get("order", [])
                  if lifecycle["terminal"][item_id][1].get("server") == "evaluation" and lifecycle["terminal"][item_id][1].get("tool") not in HELPERS]
    first = repo_calls[0] if repo_calls else None
    first_call = None if first is None else {"item_id": first[0], "tool": first[1].get("tool"), "intent": (first[1].get("arguments") or {}).get("intent"), "status": first[1].get("status")}
    expected_route = "call_target" if plan.get("case_id") in ENDPOINT_CASES else "type_dependencies"
    fallback = []
    first_explore_index = next((i for i, (_, c, _) in enumerate(repo_calls) if c.get("tool") == "loci_explore"), None)
    if first_explore_index is not None:
        for item_id, call, _row in repo_calls[first_explore_index + 1:]:
            if call.get("tool") != "loci_explore":
                fallback.append({"item_id": item_id, "tool": call.get("tool"), "status": call.get("status")})
    explore_idx = {item_id: proof for (item_id, _call, _row), proof in zip(explore_repo_calls, explore_proofs)}
    route_failures: list[Any] = []
    observations_complete = lifecycle.get("valid") is True and accounting_complete and not any(f["category"] in {"delivery_join", "source_span", "trace_join", "accounting"} and f.get("attempt_id") == attempt_id for f in failures)
    initial_type_route = None
    requested_any = None
    if observations_complete:
        initial_type_route = bool(first_call and first_call.get("tool") == "loci_explore" and first_call.get("intent") == "type_dependencies")
        requested_any = any(p.get("requested_anchor_received") for p in explore_proofs) if explore_proofs else False
    maintained_exposure = None
    if observations_complete and plan.get("case_id") in MAINTAINED_CASES:
        first_proof = explore_idx.get(first[0]) if first and first[1].get("tool") == "loci_explore" else None
        maintained_exposure = bool(initial_type_route and first_proof and first_proof.get("requested_anchor_received"))
    route = {
        "schema_version": 1,
        "observations_complete": observations_complete,
        "first_repository_call": first_call,
        "initial_route_expected": expected_route,
        "initial_type_route": initial_type_route,
        "requested_anchor_received": requested_any,
        "maintained_exposure": maintained_exposure,
        "explore_calls": [],
        "fallback_calls": fallback,
        "helper_call_count": helper_count,
        "failures": route_failures,
    }
    for item_id, call, _row in repo_calls:
        if call.get("tool") != "loci_explore":
            continue
        p = explore_idx.get(item_id, {"requested_anchor_received": False, "anchor_complete": False})
        payload = native_payload(call) or {}
        ids = [x.get("id") for x in payload.get("items", []) if isinstance(x, dict) and x.get("role") == "anchor" and isinstance(x.get("id"), str)]
        route["explore_calls"].append({"item_id": item_id, "intent": (call.get("arguments") or {}).get("intent"), "status": (call.get("result") or {}).get("structured_content", {}).get("status", call.get("status")) if isinstance(call.get("result"), dict) else call.get("status"), "successful_delivery": bool(_row and _row.get("status") == "completed" and _row.get("trace_event_id")), "anchor_ids": ids, "omissions": copy.deepcopy(payload.get("omissions", [])) if isinstance(payload.get("omissions", []), list) else [], "requested_anchor_received": p.get("requested_anchor_received"), "anchor_complete": p.get("anchor_complete")})
    if result.get("routing") != route:
        add_failure(failures, "routing_observation", "stored routing observation differs from host/raw reconstruction", attempt_id)
    row["routing"] = route
    row["stored_routing"] = result.get("routing")
    row["routing_proof"] = explore_proofs
    row["source_spans"] = sum(len(e.get("spans", [])) for e in trace.get("events", []) if isinstance(e, dict))
    row["measurement"] = {k: measurement.get(k) for k in ("outcome", "answer_correct", "task_correct", "context_recall", "read_count", "serialized_tool_output_bytes", "source_bytes", "measurement_complete", "provider_usage")}
    row["complete"] = len(failures) == local_before
    row["failure_count"] = len(failures) - local_before
    return row


def compare_report(summary: Any, rows: list[dict[str, Any]], failures: list[dict[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {"present": isinstance(summary, dict), "valid": True, "mismatches": []}
    if not isinstance(summary, dict):
        result["valid"] = False
        result["mismatches"].append("report-summary.json missing or invalid")
        return result
    def mismatch(message: str) -> None:
        result["valid"] = False; result["mismatches"].append(message)
    if summary.get("comparison") != COMPARISON or summary.get("planned_runs") != EXPECTED_RUNS:
        mismatch("report comparison or planned_runs differs")
    if summary.get("recorded_runs") != len(rows):
        mismatch("report recorded_runs differs from independently audited rows")
    actual: dict[str, dict[str, Any]] = {}
    for arm in ARMS:
        chosen = [r for r in rows if r.get("arm") == arm]
        actual[arm] = {
            "runs": len(chosen),
            "answers_correct": sum(r.get("measurement", {}).get("answer_correct") is True for r in chosen),
            "fully_successful": sum(r.get("measurement", {}).get("task_correct") is True for r in chosen),
            "measurement_complete": sum(r.get("measurement", {}).get("measurement_complete") is True for r in chosen),
            "read_sum": sum(r.get("measurement", {}).get("read_count") or 0 for r in chosen),
            "output_sum": sum(r.get("measurement", {}).get("serialized_tool_output_bytes") or 0 for r in chosen),
            "input_sum": sum((r.get("measurement", {}).get("provider_usage") or {}).get("input_tokens") or 0 for r in chosen),
        }
        published = summary.get("arms", {}).get(arm, {}) if isinstance(summary.get("arms"), dict) else {}
        for key, report_key in (("runs", "runs"), ("answers_correct", "answers_correct"), ("fully_successful", "fully_successful"), ("measurement_complete", "measurement_complete")):
            if published.get(report_key) != actual[arm][key]: mismatch(f"report arm {arm} {report_key} differs")
        for key, report_key in (("read_sum", "read_count"), ("output_sum", "serialized_tool_output_bytes"), ("input_sum", "input_tokens")):
            value = published.get(report_key, {}) if isinstance(published, dict) else {}
            if isinstance(value, dict) and value.get("sum") != actual[arm][key]: mismatch(f"report arm {arm} {report_key}.sum differs")
    result["independent_arm_totals"] = actual
    # Preserve the generated evaluator's known failure as corroborated evidence.
    generic = next((r for r in rows if r.get("attempt_id") == "generic_shadow-r1-B"), None)
    if generic is not None:
        result["known_generic_shadow_r1_B"] = {
            "answer_correct": generic.get("measurement", {}).get("answer_correct"),
            "task_correct": generic.get("measurement", {}).get("task_correct"),
            "context_recall": generic.get("measurement", {}).get("context_recall"),
        }
    return result


def compare_replay(replay: Any, output: Path, expected_ids: set[str], failures: list[dict[str, Any]]) -> dict[str, Any]:
    result = {"present": isinstance(replay, dict), "complete": False, "expected_runs": None, "verified_runs": None, "failure_count": 0, "fingerprint_mismatches": [], "unverified_attempts": []}
    if not isinstance(replay, dict):
        return result
    result["complete"] = replay.get("complete") is True
    result["expected_runs"] = replay.get("expected_runs")
    result["verified_runs"] = replay.get("verified_runs")
    result["failure_count"] = len(replay.get("failures", [])) if isinstance(replay.get("failures"), list) else -1
    attempts = replay.get("attempts", [])
    verified = {x.get("attempt_id") for x in attempts if isinstance(x, dict) and x.get("verified") is True}
    result["unverified_attempts"] = sorted(expected_ids - verified)
    inventory = replay.get("artifact_sha256")
    if isinstance(inventory, dict):
        for rel, expected in inventory.items():
            path = output / rel
            if not path.is_file() or digest_file(path) != expected:
                result["fingerprint_mismatches"].append(rel)
    else:
        result["fingerprint_mismatches"].append("artifact_sha256 missing")
    result["fingerprints_verified"] = len(inventory) if isinstance(inventory, dict) else 0
    if result["unverified_attempts"]:
        add_failure(failures, "replay_incomplete", "planned attempts absent from replay", attempts=result["unverified_attempts"])
    if result["fingerprint_mismatches"]:
        add_failure(failures, "replay_fingerprint", "existing replay fingerprint does not match retained file", paths=result["fingerprint_mismatches"])
    if result["complete"] is not True or result["expected_runs"] != EXPECTED_RUNS or result["verified_runs"] != EXPECTED_RUNS or result["failure_count"] != 0:
        add_failure(failures, "replay_incomplete", "fresh replay is not complete for all 102 attempts")
    return result


def audit(root: Path) -> dict[str, Any]:
    root = root.resolve()
    output = root / "benchmarks" / "results" / COMPARISON
    corpus_root = root / "benchmarks" / "corpora" / "typescript-context-v3"
    comparison_root = root / "benchmarks" / "comparisons" / COMPARISON
    failures: list[dict[str, Any]] = []
    manifest = safe_load(output / "manifest.json", failures)
    freeze = safe_load(comparison_root / "freeze.json", failures)
    corpus = safe_load(corpus_root / "corpus.json", failures)
    controls = safe_load(corpus_root / "comparison-controls.json", failures)
    prompt_manifest = safe_load(comparison_root / "prompt-manifest.json", failures)
    if not all(isinstance(x, dict) for x in (manifest, freeze, corpus, controls)):
        return {"schema_version": 1, "comparison": COMPARISON, "status": "blocked", "failures": failures}
    plans = canonical_plan(manifest, freeze, failures)
    expected_ids = {str(p.get("attempt_id")) for p in plans}
    dir_names = {p.name for p in output.iterdir() if p.is_dir()} if output.is_dir() else set()
    for extra in sorted(dir_names - expected_ids):
        add_failure(failures, "unexpected_attempt_directory", "output has unexpected attempt directory", attempt_id=extra)
    plan_by_id = {str(p.get("attempt_id")): p for p in plans}
    snapshot_store = SnapshotStore(corpus_root)
    try: policy = (comparison_root / "selection-policy.md").read_bytes()
    except OSError as exc: policy = b""; add_failure(failures, "policy_binding", str(exc))
    if freeze.get("policy_sha256") != digest(policy): add_failure(failures, "policy_binding", "selection policy hash differs from freeze")
    try:
        if freeze.get("prompt_manifest_sha256") != digest_file(comparison_root / "prompt-manifest.json"): add_failure(failures, "prompt_binding", "prompt manifest hash differs from freeze")
    except OSError as exc: add_failure(failures, "prompt_binding", str(exc))
    freeze_hash = None
    try: freeze_hash = digest_file(comparison_root / "freeze.json")
    except OSError as exc: add_failure(failures, "freeze_binding", str(exc))
    expected_manifest_freeze = {**freeze, "freeze_json_sha256": freeze_hash}
    if manifest.get("freeze") != expected_manifest_freeze: add_failure(failures, "freeze_binding", "manifest embedded freeze differs from committed freeze")
    if manifest.get("comparison") != COMPARISON: add_failure(failures, "manifest_binding", "manifest comparison differs")
    if manifest.get("catalog_sha256") != digest_file(output / "model-catalog.json") if (output / "model-catalog.json").is_file() else True:
        add_failure(failures, "catalog_binding", "retained model catalog hash differs from manifest")
    rows: list[dict[str, Any]] = []
    completed_ids: list[str] = []
    partial_ids: list[str] = []
    for plan in plans:
        attempt_id = str(plan.get("attempt_id")); folder = output / attempt_id
        if not folder.is_dir():
            add_failure(failures, "missing_attempt", "planned attempt directory is missing", attempt_id=attempt_id); continue
        if not (folder / "result.json").is_file():
            partial_ids.append(attempt_id)
            add_failure(failures, "partial_attempt", "planned attempt has no result.json; retained evidence is incomplete", attempt_id=attempt_id)
            continue
        completed_ids.append(attempt_id)
        rows.append(validate_attempt(output, plan, corpus, controls, freeze, manifest, snapshot_store, policy, prompt_manifest, failures))
    completed_set = set(completed_ids)
    first_missing = next((i for i,p in enumerate(plans) if str(p.get("attempt_id")) not in completed_set), len(plans))
    nonprefix = [str(p.get("attempt_id")) for p in plans[first_missing:] if str(p.get("attempt_id")) in completed_set]
    replay = safe_load(output / "replay-verification.json", failures) if (output / "replay-verification.json").is_file() else None
    completion = safe_load(output / "completion.json", failures) if (output / "completion.json").is_file() else None
    final_ready = isinstance(completion, dict)
    if not final_ready: add_failure(failures, "completion_gate", "completion.json is absent; final audit outputs remain unwritten")
    replay_result = compare_replay(replay, output, expected_ids, failures)
    report = safe_load(output / "report-summary.json", failures) if (output / "report-summary.json").is_file() else None
    report_result = compare_report(report, rows, failures)
    if not report_result["valid"]:
        add_failure(failures, "report_mismatch", "generated report totals differ", details=report_result["mismatches"])
    if isinstance(completion, dict):
        if completion.get("recorded_runs") != EXPECTED_RUNS: add_failure(failures, "completion_binding", "completion recorded_runs is not 102")
        if isinstance(report, dict):
            for key in ("replay_complete", "verdict", "frozen_gate_verdict"):
                expected = {"replay_complete": report.get("replay_complete"), "verdict": report.get("qualification_verdict"), "frozen_gate_verdict": report.get("numeric_verdict")}.get(key)
                if completion.get(key) != expected: add_failure(failures, "completion_binding", f"completion {key} differs from report", expected=expected, actual=completion.get(key))
    # Provider identity uniqueness is assessed across the retained completed prefix.
    sessions = [r.get("host", {}).get("thread_id") for r in rows if r.get("host", {}).get("thread_id")]
    duplicate_provider_ids = sorted(x for x,c in Counter(sessions).items() if c > 1)
    if duplicate_provider_ids: add_failure(failures, "provider_identity", "provider thread IDs are reused across attempts", ids=duplicate_provider_ids)
    # All nonempty raw failures and stored failures stay visible in the audit.
    raw_failures = []
    for row in rows:
        p = output / row["attempt_id"]
        for fn, path_key in (("adapter-trace.json", "failures"), ("result.json", "baseline")):
            obj = safe_load(p / fn, failures, attempt_id=row["attempt_id"])
            values = obj.get(path_key, []) if isinstance(obj, dict) else []
            if fn == "result.json" and isinstance(values, dict): values = values.get("failures", [])
            if isinstance(values, list):
                raw_failures.extend({"attempt_id": row["attempt_id"], "artifact": fn, "failure": v} for v in values)
    arm_totals: dict[str, dict[str, Any]] = {}
    for arm in ARMS:
        chosen = [r for r in rows if r.get("arm") == arm]
        arm_totals[arm] = {
            "runs": len(chosen),
            "answers_correct": sum(r.get("measurement", {}).get("answer_correct") is True for r in chosen),
            "task_correct": sum(r.get("measurement", {}).get("task_correct") is True for r in chosen),
            "measurement_complete": sum(r.get("measurement", {}).get("measurement_complete") is True for r in chosen),
            "read_count_sum": sum(r.get("measurement", {}).get("read_count") or 0 for r in chosen),
            "output_bytes_sum": sum(r.get("measurement", {}).get("serialized_tool_output_bytes") or 0 for r in chosen),
            "source_bytes_sum": sum(r.get("measurement", {}).get("source_bytes") or 0 for r in chosen),
            "input_tokens_sum": sum((r.get("measurement", {}).get("provider_usage") or {}).get("input_tokens") or 0 for r in chosen),
            "cached_input_tokens_sum": sum((r.get("measurement", {}).get("provider_usage") or {}).get("cached_input_tokens") or 0 for r in chosen),
            "output_tokens_sum": sum((r.get("measurement", {}).get("provider_usage") or {}).get("output_tokens") or 0 for r in chosen),
        }
    maintained = []
    for p in plans:
        if p.get("arm") != "B" or p.get("case_id") not in MAINTAINED_CASES or str(p.get("attempt_id")) not in completed_set: continue
        row = next((r for r in rows if r.get("attempt_id") == p.get("attempt_id")), None)
        route = row.get("stored_routing") if row else {}
        proofs = row.get("routing_proof", []) if row else []
        first = route.get("first_repository_call") if isinstance(route, dict) else None
        first_proof = proofs[0] if proofs else {"reason": "no_explore_call"}
        m = row.get("measurement", {}) if row else {}
        maintained.append({"attempt_id": p.get("attempt_id"), "first_repository_call": first,
                           "proof": first_proof, "raw_exposure": first_proof.get("requested_anchor_received") is True,
                           "raw_source_receipt": first_proof.get("requested_anchor_received") is True,
                           "raw_source_complete": first_proof.get("anchor_complete") is True,
                           "full_source_recall": m.get("context_recall"),
                           "stored_maintained_exposure": route.get("maintained_exposure") if isinstance(route, dict) else None,
                           "stored_observations_complete": route.get("observations_complete") if isinstance(route, dict) else None})
    generic = next((r for r in rows if r.get("attempt_id") == "generic_shadow-r1-B"), None)
    correctness = {"known_failures": [{"attempt_id": r.get("attempt_id"), "answer_correct": r.get("measurement", {}).get("answer_correct"), "task_correct": r.get("measurement", {}).get("task_correct")} for r in rows if r.get("measurement", {}).get("answer_correct") is False or r.get("measurement", {}).get("task_correct") is False], "generic_shadow_r1_B": None}
    if generic:
        correctness["generic_shadow_r1_B"] = {"answer": generic.get("measurement", {}).get("answer_correct"), "task_correct": generic.get("measurement", {}).get("task_correct"), "context_recall": generic.get("measurement", {}).get("context_recall"), "forbidden_proven_relationships": 0}
    maintained_pass = sum(x["stored_maintained_exposure"] is True for x in maintained)
    maintained_unknown = sum(x["stored_maintained_exposure"] is None for x in maintained)
    maintained_fail = sum(x["stored_maintained_exposure"] is False for x in maintained)
    status = ("complete" if not failures else "failed") if final_ready and len(completed_ids) == EXPECTED_RUNS else "prefix"
    audit_result: dict[str, Any] = {
        "schema_version": 1,
        "comparison": COMPARISON,
        "status": status,
        "observed_at": datetime.now(timezone.utc).isoformat(),
        "scope": {"output": str(output), "read_only": True, "rescore_or_input_changes": False,
                  "attempt_directories_seen": len(dir_names), "attempts_expected": EXPECTED_RUNS,
                  "attempts_audited": len(rows), "completed_attempts": len(completed_ids),
                  "partial_attempts": partial_ids, "nonprefix_completed_attempts": nonprefix,
                  "completion_present": final_ready, "observed_tool_calls": sum(r.get("host", {}).get("terminal_calls", 0) for r in rows),
                  "provider_calls_during_audit": 0},
        "plan": {"planned": len(plans), "arm_counts": Counter(str(p.get("arm")) for p in plans), "repetition_counts": Counter(str(p.get("repetition")) for p in plans), "case_counts": Counter(str(p.get("case_id")) for p in plans), "completed": len(completed_ids)},
        "evidence_audit": {
            "delivery_and_source_joins": {"matching_attempts": sum(r.get("failure_count") == 0 for r in rows), "mismatch_attempts": sorted({f.get("attempt_id") for f in failures if f.get("category") in {"delivery_join", "source_span", "trace_join", "accounting"} and f.get("attempt_id")})},
            "host_start_terminal_order": {"matching_attempts": sum(r.get("host", {}).get("valid") is True for r in rows), "mismatch_attempts": sorted({f.get("attempt_id") for f in failures if f.get("category") in {"host_lifecycle", "session_close"} and f.get("attempt_id")})},
            "identity_and_lifecycle": {"matching_attempts": sum(r.get("failure_count") == 0 for r in rows), "mismatch_attempts": sorted({f.get("attempt_id") for f in failures if f.get("category") in {"identity", "provenance", "engine_binding", "freeze_binding", "catalog_binding", "prompt_binding", "tool_schema_binding"} and f.get("attempt_id")})},
            "routing_replay_matches": {"matching_attempts": sum(r.get("routing") is not None and r.get("failure_count") == 0 for r in rows), "mismatch_attempts": sorted({f.get("attempt_id") for f in failures if f.get("category") in {"routing_observation", "replay_fingerprint"} and f.get("attempt_id")})},
            "source_span_count": sum(r.get("source_spans", 0) for r in rows),
            "provider_unique_threads": len(sessions), "provider_duplicate_threads": duplicate_provider_ids,
        },
        "maintained_B_exposure": {"first_type_dependencies": sum(
            isinstance(x["first_repository_call"], dict)
            and x["first_repository_call"].get("tool") == "loci_explore"
            and x["first_repository_call"].get("intent") == "type_dependencies" for x in maintained), "required_attempts": 9,
            "raw_evidence_pass": sum(x["raw_source_receipt"] for x in maintained),
            "raw_evidence_fail": sum(not x["raw_source_receipt"] for x in maintained),
            "stored_exposure_true": maintained_pass, "stored_exposure_false": maintained_fail, "stored_exposure_unknown": maintained_unknown,
            "candidate_exposure_established": len(maintained) == 9 and maintained_pass == 9 and maintained_unknown == 0 and replay_result.get("complete") is True,
            "records": maintained,
            "contract_effect": "Native requested-anchor receipt and full source recall are reported separately; later recovery cannot replace a failed first exposure."},
        "correctness_corroboration": correctness,
        "outcome_cost_usage": {"arm_totals": arm_totals, "all_audited_measurements_complete": all(r.get("measurement", {}).get("measurement_complete") is True for r in rows) and len(rows) == EXPECTED_RUNS, "raw_failures": raw_failures},
        "replay_verification": {**replay_result, "path": str(output / "replay-verification.json")},
        "report_summary": {**report_result, "path": str(output / "report-summary.json")},
        "completion": completion if isinstance(completion, dict) else None,
        "failures": failures,
        "failure_count": len(failures),
        "limitations": ["Read-only audit; no provider calls, retries, input changes, rescore or frozen-source edits.", "Final audit writes are gated on completion.json; a prefix audit is descriptive while the batch is running.", "Partial source receipt is retained separately from context recall and does not establish full source recall."],
    }
    # Counter objects are converted before JSON serialization.
    audit_result["plan"]["arm_counts"] = dict(audit_result["plan"]["arm_counts"])
    audit_result["plan"]["repetition_counts"] = dict(audit_result["plan"]["repetition_counts"])
    audit_result["plan"]["case_counts"] = dict(audit_result["plan"]["case_counts"])
    return audit_result


def markdown(audit_result: dict[str, Any]) -> str:
    scope = audit_result.get("scope", {})
    exposure = audit_result.get("maintained_B_exposure", {})
    totals = audit_result.get("outcome_cost_usage", {}).get("arm_totals", {})
    lines = ["# Routing-v2 artifact audit", "", f"Status: **{audit_result.get('status')}**.", f"Audited {scope.get('attempts_audited', 0)}/{scope.get('attempts_expected', EXPECTED_RUNS)} completed attempts; completion sentinel present: **{scope.get('completion_present')}**.", "", "## Counts", "", "| Arm | Attempts | Correct | Task-correct | Measurements complete | Calls | Output bytes | Gross input tokens |", "|---|---:|---:|---:|---:|---:|---:|---:|"]
    for arm in ARMS:
        t = totals.get(arm, {})
        lines.append(f"| {arm} | {t.get('runs', 0)} | {t.get('answers_correct', 0)} | {t.get('task_correct', 0)} | {t.get('measurement_complete', 0)} | {t.get('read_count_sum', 0)} | {t.get('output_bytes_sum', 0)} | {t.get('input_tokens_sum', 0)} |")
    lines += ["", "## Maintained B source exposure", "", f"Native requested-anchor receipts: {exposure.get('raw_evidence_pass', 0)}/{exposure.get('required_attempts', 9)}; stored maintained exposure true: {exposure.get('stored_exposure_true', 0)}/{exposure.get('required_attempts', 9)}; replay complete: {audit_result.get('replay_verification', {}).get('complete')}.", "Source receipt is retained separately from the stored context-recall value.", "", "## Known correctness evidence", ""]
    known = audit_result.get("correctness_corroboration", {}).get("known_failures", [])
    lines.extend(f"- `{x.get('attempt_id')}`: answer_correct={x.get('answer_correct')}, task_correct={x.get('task_correct')}" for x in known) if known else lines.append("None recorded.")
    lines += ["", "## Audit failures", ""]
    failures = audit_result.get("failures", [])
    if failures:
        lines.extend(f"- `{f.get('attempt_id', '')}` {f.get('category')}: {f.get('message')}" for f in failures)
    else:
        lines.append("None.")
    lines += ["", "The JSON artifact retains complete per-attempt maintained-anchor records, raw failures, replay fingerprint checks, lifecycle joins, and binding checks.", ""]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path("/Users/brummerv/phluxxed/loci-exploration"))
    parser.add_argument("--write", action="store_true", help="write the two audit deliverables only after completion.json exists")
    args = parser.parse_args()
    result = audit(args.root)
    if args.write:
        output = args.root.resolve() / "benchmarks" / "results" / COMPARISON
        if not result.get("scope", {}).get("completion_present"):
            raise SystemExit("refusing --write: completion.json is absent")
        if result.get("status") != "complete" or result.get("failures"):
            raise SystemExit("refusing successful audit publication: " + json.dumps(result.get("failures")))
        (output / "artifact-audit.json").write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        (output / "artifact-audit.md").write_text(markdown(result), encoding="utf-8")
    print(json.dumps(result, indent=2, ensure_ascii=False, sort_keys=True))
    return 0 if not args.write or result.get("status") == "complete" else 1


if __name__ == "__main__":
    raise SystemExit(main())
