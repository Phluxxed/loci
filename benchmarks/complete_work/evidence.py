"""Join retained benchmark-control receipts to native MCP delivery telemetry.

The join describes delivery observed at two boundaries.  It never turns an MCP
call, a graph relationship, or retained source bytes into evidence that a model
used that material.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping

from .control import load_receipts


SCHEMA_VERSION = 1
# These are the only names normalised before the otherwise exact match.  The
# controlled MCP server advertises the canonical names; the two host-qualified
# aliases are the App Server's declared native item spelling.
TOOL_ALIASES = {
    "loci_retrieve": "loci_retrieve",
    "loci_read": "loci_read",
    "mcp__loci__loci_retrieve": "loci_retrieve",
    "mcp__loci__loci_read": "loci_read",
}
SERVER_ALIASES = {"loci": "loci"}


def _canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _artifact_bytes(root: Path, descriptor: Mapping[str, Any]) -> bytes:
    path = root / str(descriptor["path"])
    raw = path.read_bytes()
    if len(raw) != descriptor["bytes"] or hashlib.sha256(raw).hexdigest() != descriptor["sha256"]:
        raise ValueError("validated receipt artifact changed during delivery join")
    return raw


def _native_calls(accounting: Mapping[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    calls: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    stages = accounting.get("stages")
    if not isinstance(stages, list):
        return [], [{"code": "ACCOUNTING_STAGES_UNAVAILABLE", "detail": "accounting.stages is not an array"}]
    for stage in stages:
        if not isinstance(stage, Mapping) or not isinstance(stage.get("stage_id"), str):
            errors.append({"code": "ACCOUNTING_STAGE_INVALID", "detail": "stage has no string stage_id"})
            continue
        items = stage.get("items")
        if not isinstance(items, list):
            errors.append({"code": "NATIVE_MCP_TELEMETRY_UNAVAILABLE", "stage_id": stage["stage_id"], "detail": "items is not an array"})
            continue
        for index, item in enumerate(items):
            if not isinstance(item, Mapping) or item.get("type") != "mcpToolCall":
                continue
            tool = TOOL_ALIASES.get(item.get("tool"))
            server = SERVER_ALIASES.get(item.get("server"))
            arguments, result = item.get("arguments"), item.get("result")
            if tool is None or server is None or not isinstance(arguments, Mapping):
                errors.append({
                    "code": "NATIVE_MCP_ITEM_UNMATCHABLE", "stage_id": stage["stage_id"], "item_index": index,
                    "detail": "tool, server and arguments must use the declared protocol shape",
                })
                continue
            packet: dict[str, Any] | None = None
            if (item.get("status") == "completed" and item.get("error") in (None, {})
                    and isinstance(result, Mapping) and "isError" not in result):
                # ThreadStartResponse.McpToolCallResult omits ``isError`` for a
                # successful native item.  This is the sole default applied by
                # the join; failed/error items stay unknown unless a future
                # protocol adds an exact result shape for them.
                packet = dict(result)
                if packet.get("_meta") is None:
                    packet.pop("_meta", None)
                packet["isError"] = False
            else:
                errors.append({
                    "code": "NATIVE_MCP_ITEM_UNMATCHABLE", "stage_id": stage["stage_id"], "item_index": index,
                    "detail": "native item is not a completed successful McpToolCallResult",
                })
                continue
            calls.append({
                "stage_id": stage["stage_id"], "item_index": index, "tool": tool,
                "server": server, "arguments": dict(arguments), "result": packet,
                "capture_started": item.get("capture_started"), "capture_completed": item.get("capture_completed"),
            })
    if not calls and not errors:
        errors.append({"code": "NATIVE_MCP_TELEMETRY_UNAVAILABLE", "detail": "no native mcpToolCall items were retained"})
    return calls, errors


def _capture_interval(call: Mapping[str, Any]) -> tuple[int, int] | None:
    start, end = call.get("capture_started"), call.get("capture_completed")
    if not isinstance(start, Mapping) or not isinstance(end, Mapping):
        return None
    if not isinstance(start.get("emitted_at_ms"), (int, float)) or not isinstance(end.get("emitted_at_ms"), (int, float)):
        return None
    if start["emitted_at_ms"] > end["emitted_at_ms"]:
        return None
    try:
        def epoch_ns(value: Any) -> int:
            if not isinstance(value, str):
                raise ValueError("utc is missing")
            return int(datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp() * 1_000_000_000)
        lower, upper = epoch_ns(start.get("utc")), epoch_ns(end.get("utc"))
    except ValueError:
        return None
    return (lower, upper) if lower <= upper else None


def _declared_arguments(operation: str, arguments: Mapping[str, Any]) -> dict[str, Any]:
    """Apply only defaults declared by the controlled two-tool protocol."""
    normalized = dict(arguments)
    if operation == "loci_retrieve":
        normalized.setdefault("query", "")
        normalized.setdefault("seed_ids", None)
    return normalized


def _match_receipt(receipt: Mapping[str, Any], packet: Mapping[str, Any], native: list[dict[str, Any]]) -> list[int]:
    operation = TOOL_ALIASES.get(receipt.get("operation"))
    arguments = receipt.get("arguments")
    if operation is None or not isinstance(arguments, Mapping):
        return []
    expected = _canonical(packet)
    expected_arguments = _declared_arguments(operation, arguments)
    return [
        index for index, call in enumerate(native)
        if call["server"] == "loci" and call["tool"] == operation
        and _canonical(_declared_arguments(operation, call["arguments"])) == _canonical(expected_arguments)
        and _canonical(call["result"]) == expected
    ]


def _timed_candidates(receipt: Mapping[str, Any], candidates: list[int], native: list[dict[str, Any]]) -> list[int]:
    """Use capture intervals only to disambiguate otherwise exact duplicates."""
    started, recorded = receipt.get("started_unix_ns"), receipt.get("recorded_unix_ns")
    if type(started) is not int or type(recorded) is not int or started > recorded:
        return candidates
    bounded = []
    for index in candidates:
        interval = _capture_interval(native[index])
        if interval is None:
            return candidates  # An unbounded identical call cannot be ruled out.
        if interval[0] <= started <= recorded <= interval[1]:
            bounded.append(index)
    return bounded if bounded else candidates


def _payload_delivery(packet: Mapping[str, Any]) -> dict[str, Any]:
    payload = packet.get("structuredContent")
    if not isinstance(payload, Mapping):
        return {"source_spans": [], "source_content_bytes": 0, "relationships": 0, "proofs": 0}
    source_values: list[Any] = []
    if "source" in payload:
        source_values.append(payload["source"])
    if isinstance(payload.get("sources"), list):
        source_values.extend(payload["sources"])
    spans: list[dict[str, Any]] = []
    for source in source_values:
        if not isinstance(source, Mapping):
            continue
        file, digest = source.get("file"), source.get("content_hash")
        start, end, content = source.get("start_byte"), source.get("end_byte"), source.get("content")
        if (isinstance(file, str) and isinstance(digest, str) and type(start) is int
                and type(end) is int and 0 <= start <= end and isinstance(content, str)):
            spans.append({"file": file, "sha256": digest, "start_byte": start, "end_byte": end,
                          "content_bytes": len(content.encode("utf-8"))})
    relationships = payload.get("relationships")
    if not isinstance(relationships, list):
        relationships = []
    proofs = sum(
        1 for relationship in relationships
        if isinstance(relationship, Mapping)
        and isinstance(relationship.get("edge"), Mapping)
        and isinstance(relationship["edge"].get("evidence"), Mapping)
    )
    return {"source_spans": spans, "source_content_bytes": sum(x["content_bytes"] for x in spans),
            "relationships": len(relationships), "proofs": proofs}


def _stage_row(stage_id: str) -> dict[str, Any]:
    return {
        "stage_id": stage_id, "status": "known", "calls": [], "errors": [], "source_versions": [],
        "packet_bytes": 0, "source_content_bytes": 0, "relationships_delivered": 0,
        "proofs_delivered": 0, "repeated_unchanged_source_bytes": 0,
    }


def _overlap_and_add(intervals: list[tuple[int, int]], start: int, end: int) -> int:
    overlap = 0
    for prior_start, prior_end in intervals:
        overlap += max(0, min(end, prior_end) - max(start, prior_start))
    intervals.append((start, end))
    intervals.sort()
    merged: list[tuple[int, int]] = []
    for item_start, item_end in intervals:
        if merged and item_start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], item_end))
        else:
            merged.append((item_start, item_end))
    intervals[:] = merged
    return overlap


def summarize_delivery(receipt_dir: Path, accounting: dict) -> dict:
    """Return auditable delivery evidence, preserving unmatched uncertainty.

    Receipt loading validates ordered control records and their content-addressed
    full packets/source versions before any native item is considered a match.
    """
    errors: list[dict[str, Any]] = []
    try:
        root = Path(receipt_dir).resolve(strict=True)
        receipts = load_receipts(root)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        return {
            "schema_version": SCHEMA_VERSION, "status": "unknown", "stages": [], "episode": {},
            "arm": None, "source_versions": [],
            "errors": [{"code": "RECEIPT_LOAD_FAILED", "detail": str(exc)}],
            "limitations": ["Receipt validation failed; no delivery attribution is made."],
        }
    native, native_errors = _native_calls(accounting)
    errors.extend(native_errors)
    stage_rows: dict[str, dict[str, Any]] = {}
    for stage in accounting.get("stages", []) if isinstance(accounting.get("stages"), list) else []:
        if isinstance(stage, Mapping) and isinstance(stage.get("stage_id"), str):
            stage_rows[stage["stage_id"]] = _stage_row(stage["stage_id"])
    intervals: dict[tuple[str, str], list[tuple[int, int]]] = {}
    versions: dict[tuple[str, str], dict[str, Any]] = {}
    packet_bytes = source_bytes = relationships = proofs = repeated = 0
    matched_count = unmatched_count = ambiguous_count = 0
    episode_calls: list[dict[str, Any]] = []
    arms = {receipt.get("arm") for receipt in receipts if isinstance(receipt.get("arm"), str)}
    prepared: list[tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]], list[int]]] = []
    for receipt in receipts:
        try:
            delivered_packet = json.loads(_artifact_bytes(root, receipt["packet"]))
        except (KeyError, ValueError, TypeError, json.JSONDecodeError) as exc:
            errors.append({"code": "RECEIPT_PACKET_UNAVAILABLE", "sequence": receipt.get("sequence"), "detail": str(exc)})
            continue
        receipt_versions = []
        for version in receipt.get("source_versions", []):
            if not isinstance(version, Mapping) or not isinstance(version.get("file"), str) or not isinstance(version.get("sha256"), str):
                errors.append({"code": "RECEIPT_SOURCE_VERSION_INVALID", "sequence": receipt.get("sequence")})
                continue
            receipt_versions.append(dict(version))
        for version in receipt_versions:
            versions[(version.get("file"), version.get("sha256"))] = version
        candidates = _match_receipt(receipt, delivered_packet, native)
        if len(candidates) > 1:
            candidates = _timed_candidates(receipt, candidates, native)
        prepared.append((dict(receipt), delivered_packet, receipt_versions, candidates))

    owners: dict[int, list[int]] = {}
    for receipt_index, (_receipt, _packet, _versions, candidates) in enumerate(prepared):
        for native_index in candidates:
            owners.setdefault(native_index, []).append(receipt_index)
    paired = {
        receipt_index: candidates[0]
        for receipt_index, (_receipt, _packet, _versions, candidates) in enumerate(prepared)
        if len(candidates) == 1 and len(owners[candidates[0]]) == 1
    }

    for receipt_index, (receipt, delivered_packet, receipt_versions, candidates) in enumerate(prepared):
        record = {
            "sequence": receipt.get("sequence"), "operation": receipt.get("operation"),
            "backend_outcome": receipt.get("operation_outcome"), "returned_outcome": receipt.get("outcome"),
            "receipt_packet_bytes": receipt["packet"]["bytes"],
            "backend_receipt_packet_bytes": receipt["operation_packet"]["bytes"],
            "native_delivery_packet": dict(receipt["packet"]),
            "backend_operation_packet": dict(receipt["operation_packet"]),
        }
        native_index = paired.get(receipt_index)
        if native_index is None:
            conflict = len(candidates) == 1 and len(owners[candidates[0]]) > 1
            code = "NATIVE_MATCH_CONFLICT" if conflict else ("NATIVE_MATCH_AMBIGUOUS" if candidates else "NATIVE_MATCH_UNAVAILABLE")
            record.update({"status": "unknown", "candidate_count": len(candidates), "error": code})
            errors.append({"code": code, "sequence": receipt.get("sequence"), "candidate_count": len(candidates)})
            for candidate in candidates:
                stage = stage_rows.setdefault(native[candidate]["stage_id"], _stage_row(native[candidate]["stage_id"]))
                stage["errors"].append(record)
            if code == "NATIVE_MATCH_UNAVAILABLE":
                unmatched_count += 1
            else:
                ambiguous_count += 1
            episode_calls.append(record)
            continue
        native_call = native[native_index]
        stage = stage_rows.setdefault(native_call["stage_id"], _stage_row(native_call["stage_id"]))
        delivery = _payload_delivery(delivered_packet)
        record.update({"status": "matched", "stage_id": native_call["stage_id"],
                       "native_item_index": native_call["item_index"],
                       "delivery": {k: delivery[k] for k in ("source_content_bytes", "relationships", "proofs")}})
        stage["calls"].append(record)
        stage["packet_bytes"] += record["receipt_packet_bytes"]
        stage["source_content_bytes"] += delivery["source_content_bytes"]
        stage["relationships_delivered"] += delivery["relationships"]
        stage["proofs_delivered"] += delivery["proofs"]
        packet_bytes += record["receipt_packet_bytes"]
        source_bytes += delivery["source_content_bytes"]
        relationships += delivery["relationships"]
        proofs += delivery["proofs"]
        for span in delivery["source_spans"]:
            key = (span["file"], span["sha256"])
            overlap = _overlap_and_add(intervals.setdefault(key, []), span["start_byte"], span["end_byte"])
            repeated += overlap
            stage["repeated_unchanged_source_bytes"] += overlap
        stage["source_versions"].extend(receipt_versions)
        episode_calls.append(record)
        matched_count += 1
    paired_native = set(paired.values())
    for native_index, native_call in enumerate(native):
        if native_index not in paired_native:
            error = {"code": "NATIVE_CALL_UNPAIRED", "stage_id": native_call["stage_id"],
                     "item_index": native_call["item_index"]}
            errors.append(error)
            stage_rows.setdefault(native_call["stage_id"], _stage_row(native_call["stage_id"]))["errors"].append(error)
    if not native:
        for stage in stage_rows.values():
            stage["errors"].append({"code": "NATIVE_MCP_TELEMETRY_UNAVAILABLE", "stage_id": stage["stage_id"]})
    for stage in stage_rows.values():
        if stage["errors"] or any(error.get("stage_id") == stage["stage_id"] for error in errors):
            stage["status"] = "unknown"
    status = "known" if not errors and matched_count == len(receipts) and receipts else "unknown"
    return {
        "schema_version": SCHEMA_VERSION, "status": status,
        "arm": next(iter(arms)) if len(arms) == 1 else None,
        "stages": [stage_rows[key] for key in sorted(stage_rows)],
        "episode": {
            "receipt_calls": len(receipts), "matched_calls": matched_count,
            "unmatched_calls": unmatched_count, "ambiguous_calls": ambiguous_count,
            "packet_bytes": packet_bytes, "source_content_bytes": source_bytes,
            "relationships_delivered": relationships, "proofs_delivered": proofs,
            "repeated_unchanged_source_bytes": repeated,
            "unique_unchanged_source_bytes": sum(end - start for values in intervals.values() for start, end in values),
            "calls": episode_calls,
        },
        "source_versions": sorted(versions.values(), key=lambda item: (item["file"], item["sha256"])),
        "errors": errors,
        "limitations": [
            "Packet bytes are exact serialized retained CallToolResult transport bytes, not provider-token accounting.",
            "Relationships, proof and source bytes describe delivery only; they do not establish model reliance or causal attribution.",
            "Missing, unmatched or ambiguous native MCP telemetry remains unknown rather than being estimated.",
        ],
    }
