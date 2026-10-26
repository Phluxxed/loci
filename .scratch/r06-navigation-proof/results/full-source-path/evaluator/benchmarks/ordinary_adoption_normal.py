"""Versioned normal-surface readout for ordinary-adoption native captures.

This adapter layers on the versioned native-envelope compatibility reader.
Frozen helpers retain interval and exact outer-output correlation semantics;
this module interprets the two public normal
operations introduced by ``normal-graph-v1``.  In particular, it does not use
the older observer's source aggregates for normal calls: source content and
proof linkage are recomputed from each retained normal result.
"""
from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from benchmarks.ordinary_adoption_native_v2 import NATIVE_ADAPTER_VERSION, observe_rollout
from benchmarks.ordinary_adoption_observed import ObservationError


NORMAL_ADAPTER_VERSION = "ordinary-adoption-normal-v2"
_NORMAL_TOOLS = {
    "loci_retrieve": "normal_context_retrieval",
    "loci_read": "exact_source_hydration",
}
_SEMANTIC_FAMILIES = frozenset(
    {
        "calls",
        "uses_type",
        "extends",
        "implements",
        "embeds",
        "supertrait",
        "impl_trait",
        "impl_self_type",
        "references_type",
        "references",
        "imports",
        "imports_type",
    }
)
_RESOLUTIONS = frozenset({"exact", "declared", "import-resolved"})


def _nonnegative_int(value: Any) -> int | None:
    return value if type(value) is int and value >= 0 else None


def _sha256(value: Any) -> bool:
    return isinstance(value, str) and len(value) == 64 and all(
        character in "0123456789abcdef" for character in value
    )


def _source_record(value: Any) -> tuple[dict[str, Any] | None, str]:
    """Normalize a contract source record without claiming its preview is a file.

    ``content_hash`` identifies the indexed file, while ``content`` can be a
    bounded preview.  Hashing the preview would therefore manufacture a false
    corruption result.  The record's identity, bounds, line coverage and UTF-8
    content are all nevertheless checked before it can support an edge.
    """

    if not isinstance(value, Mapping):
        return None, "malformed_source"
    source_id = value.get("id")
    file_name = value.get("file")
    start_byte, end_byte = value.get("start_byte"), value.get("end_byte")
    start_line, end_line = value.get("start_line"), value.get("end_line")
    content_hash, content, source_ref = (
        value.get("content_hash"),
        value.get("content"),
        value.get("source_ref"),
    )
    if (
        type(source_id) is not int
        or source_id < 1
        or not isinstance(file_name, str)
        or not file_name
        or _nonnegative_int(start_byte) is None
        or _nonnegative_int(end_byte) is None
        or start_byte > end_byte
        or type(start_line) is not int
        or type(end_line) is not int
        or start_line < 1
        or end_line < start_line
        or not _sha256(content_hash)
        or not isinstance(content, str)
        or not isinstance(source_ref, str)
        or not source_ref
        or end_byte - start_byte != len(content.encode("utf-8"))
    ):
        return None, "malformed_source"
    return {
        "id": source_id,
        "file": file_name,
        "start_byte": start_byte,
        "end_byte": end_byte,
        "start_line": start_line,
        "end_line": end_line,
        "content_hash": content_hash,
        "content_bytes": len(content.encode("utf-8")),
    }, "complete"


def _unique_extent_bytes(sources: Sequence[Mapping[str, Any]]) -> int:
    intervals: dict[tuple[str, str], list[tuple[int, int]]] = {}
    for source in sources:
        intervals.setdefault(
            (str(source["file"]), str(source["content_hash"])), []
        ).append((int(source["start_byte"]), int(source["end_byte"])))
    total = 0
    for ranges in intervals.values():
        start = end = -1
        for current_start, current_end in sorted(ranges):
            if start < 0:
                start, end = current_start, current_end
            elif current_start <= end:
                end = max(end, current_end)
            else:
                total += end - start
                start, end = current_start, current_end
        if start >= 0:
            total += end - start
    return total


def _sources(value: Any, *, singular: bool) -> dict[str, Any]:
    raw = [value] if singular else value
    if not isinstance(raw, list):
        return {
            "status": "unknown_schema",
            "source_record_count": None,
            "source_content_bytes": None,
            "by_id": {},
        }
    normalized: dict[int, dict[str, Any]] = {}
    for raw_source in raw:
        source, status = _source_record(raw_source)
        if status != "complete" or source is None or source["id"] in normalized:
            return {
                "status": "unknown_malformed_source",
                "source_record_count": None,
                "source_content_bytes": None,
                "by_id": {},
            }
        normalized[source["id"]] = source
    return {
        "status": "complete",
        "source_record_count": len(normalized),
        "source_content_bytes": _unique_extent_bytes(list(normalized.values())),
        "by_id": normalized,
    }


def _node_ids(value: Any) -> set[str] | None:
    if not isinstance(value, list):
        return None
    ids: set[str] = set()
    for node in value:
        node_id = node.get("id") if isinstance(node, Mapping) else None
        if not isinstance(node_id, str) or not node_id or node_id in ids:
            return None
        ids.add(node_id)
    return ids


def _relationships(
    value: Any, sources: Mapping[int, Mapping[str, Any]], node_ids: set[str] | None
) -> dict[str, Any]:
    if not isinstance(value, list):
        return {
            "status": "unknown_schema",
            "semantic_relationship_count": None,
            "proof_validated_relationship_count": None,
        }
    if node_ids is None:
        return _unknown_relationships()
    seen_ids: set[int] = set()
    for relationship in value:
        if not isinstance(relationship, Mapping):
            return _unknown_relationships()
        relationship_id, edge, source_ids, proof = (
            relationship.get("id"),
            relationship.get("edge"),
            relationship.get("source_ids"),
            relationship.get("proof"),
        )
        if (
            type(relationship_id) is not int
            or relationship_id < 1
            or relationship_id in seen_ids
            or not isinstance(edge, Mapping)
            or not isinstance(source_ids, list)
            or not source_ids
            or proof != "complete"
            or relationship.get("traversed") not in {"forward", "reverse"}
        ):
            return _unknown_relationships()
        seen_ids.add(relationship_id)
        evidence = edge.get("evidence")
        if (
            not isinstance(edge.get("from"), str)
            or not edge.get("from")
            or edge["from"] not in node_ids
            or not isinstance(edge.get("to"), str)
            or not edge.get("to")
            or edge["to"] not in node_ids
            or not isinstance(edge.get("type"), str)
            or not edge.get("type")
            or edge["type"] not in _SEMANTIC_FAMILIES
            or edge.get("directed") is not True
            or edge.get("namespace") != "loci"
            or edge.get("resolution") not in _RESOLUTIONS
            or not isinstance(evidence, Mapping)
            or not isinstance(evidence.get("file"), str)
            or not evidence.get("file")
            or type(evidence.get("line")) is not int
            or evidence["line"] < 1
            or not _sha256(evidence.get("content_hash"))
        ):
            return _unknown_relationships()
        if any(type(source_id) is not int for source_id in source_ids):
            return _unknown_relationships()
        if len(set(source_ids)) != len(source_ids):
            return _unknown_relationships()
        linked = [sources.get(source_id) for source_id in source_ids]
        if any(source is None for source in linked):
            return _unknown_relationships()
        if not any(
            source["file"] == evidence["file"]
            and source["content_hash"] == evidence["content_hash"]
            and source["start_line"] <= evidence["line"] <= source["end_line"]
            for source in linked
            if source is not None
        ):
            return _unknown_relationships()
    return {
        "status": "complete",
        "semantic_relationship_count": len(value),
        "proof_validated_relationship_count": len(value),
    }


def _unknown_relationships() -> dict[str, Any]:
    return {
        "status": "unknown_malformed_proof",
        "semantic_relationship_count": None,
        "proof_validated_relationship_count": None,
    }


def _ownership(value: Any) -> dict[str, Any]:
    if not isinstance(value, list):
        return {"status": "unknown_schema", "ownership_association_count": None}
    for association in value:
        if not isinstance(association, Mapping) or not all(
            isinstance(association.get(key), str) and association[key]
            for key in ("owner_id", "member_id", "basis")
        ):
            return {"status": "unknown_malformed_ownership", "ownership_association_count": None}
    return {"status": "complete", "ownership_association_count": len(value)}


def _usage(value: Any, key: str) -> tuple[int | None, str]:
    if not isinstance(value, Mapping):
        return None, "unknown_schema"
    count = _nonnegative_int(value.get(key))
    return (count, "complete") if count is not None else (None, "unknown_schema")


def _compact_result_bytes(value: Any) -> int | None:
    if not isinstance(value, Mapping):
        return None
    try:
        return len(
            json.dumps(
                value,
                ensure_ascii=False,
                allow_nan=False,
                separators=(",", ":"),
            ).encode("utf-8")
        )
    except (TypeError, ValueError, UnicodeError):
        return None


def _byte_status(reported: int | None, actual: int | None) -> str:
    if reported is None or actual is None:
        return "unknown"
    return "complete" if reported == actual else "mismatch"


def _byte_accounting(
    result: Any,
    structured: Any,
    source: Mapping[str, Any],
) -> dict[str, Any]:
    usage = structured.get("usage") if isinstance(structured, Mapping) else None
    reported_evidence = (
        _nonnegative_int(usage.get("evidence_bytes"))
        if isinstance(usage, Mapping)
        else None
    )
    reported_output = (
        _nonnegative_int(usage.get("output_bytes"))
        if isinstance(usage, Mapping)
        else None
    )
    actual_evidence = (
        _nonnegative_int(source.get("source_content_bytes"))
        if source.get("status") in {"complete", "known_source_free_error"}
        else None
    )
    actual_output = _compact_result_bytes(result)
    evidence_status = _byte_status(reported_evidence, actual_evidence)
    output_status = _byte_status(reported_output, actual_output)
    status = (
        "mismatch"
        if "mismatch" in {evidence_status, output_status}
        else "complete"
        if evidence_status == output_status == "complete"
        else "unknown"
    )
    return {
        "reported_evidence_bytes": reported_evidence,
        "actual_evidence_bytes": actual_evidence,
        "evidence_bytes_status": evidence_status,
        "reported_output_bytes": reported_output,
        "actual_output_bytes": actual_output,
        "output_bytes_status": output_status,
        "status": status,
    }


def _error_readout(category: str, result: Any) -> dict[str, Any]:
    source = {
        "status": "known_source_free_error",
        "source_record_count": 0,
        "source_content_bytes": 0,
    }
    return {
        "category": category,
        "public_invocation_count": 1,
        "application_error": True,
        "source": source,
        "relationships": {
            "status": "known_source_free_error",
            "semantic_relationship_count": 0,
            "proof_validated_relationship_count": 0,
            "actual_traversed_edge_count": None,
            "actual_traversed_edge_count_status": "unknown_after_error",
            "delivered_relationship_count": 0,
            "delivered_relationship_count_status": "known_source_free_error",
        },
        "ownership": {"status": "known_source_free_error", "ownership_association_count": 0},
        "byte_accounting": _byte_accounting(result, None, source),
        "actual_host_proof_status": "not_model_delivered",
    }


def _retrieve_readout(call: Mapping[str, Any]) -> dict[str, Any]:
    result = call.get("result")
    structured = result.get("structuredContent") if isinstance(result, Mapping) else None
    error = (
        isinstance(result, Mapping)
        and (result.get("isError") is True or (isinstance(structured, Mapping) and "error" in structured))
    )
    if error:
        return _error_readout("normal_context_retrieval", result)
    if not isinstance(structured, Mapping):
        return _unknown_readout("normal_context_retrieval", result)
    source = _sources(structured.get("sources"), singular=False)
    relationships = _relationships(
        structured.get("relationships"), source["by_id"], _node_ids(structured.get("nodes"))
    )
    ownership = _ownership(structured.get("ownership"))
    traversed, traversed_status = _usage(structured.get("usage"), "edges_traversed")
    delivered, delivered_status = _usage(structured.get("usage"), "relationships_delivered")
    if relationships["semantic_relationship_count"] is None or delivered is None:
        delivered_status = "unknown" if delivered is None else "reported_but_unvalidated"
    elif delivered != relationships["semantic_relationship_count"]:
        delivered_status = "mismatch"
    if traversed is not None and delivered is not None and traversed < delivered:
        traversed_status = "mismatch"
    return {
        "category": "normal_context_retrieval",
        "public_invocation_count": 1,
        "application_error": False,
        "source": {key: value for key, value in source.items() if key != "by_id"},
        "relationships": {
            **relationships,
            "actual_traversed_edge_count": traversed,
            "actual_traversed_edge_count_status": traversed_status,
            "delivered_relationship_count": delivered,
            "delivered_relationship_count_status": delivered_status,
        },
        "ownership": ownership,
        "byte_accounting": _byte_accounting(result, structured, source),
        "actual_host_proof_status": "pending_model_delivery",
    }


def _read_readout(call: Mapping[str, Any]) -> dict[str, Any]:
    result = call.get("result")
    structured = result.get("structuredContent") if isinstance(result, Mapping) else None
    error = (
        isinstance(result, Mapping)
        and (result.get("isError") is True or (isinstance(structured, Mapping) and "error" in structured))
    )
    if error:
        return _error_readout("exact_source_hydration", result)
    if not isinstance(structured, Mapping):
        return _unknown_readout("exact_source_hydration", result)
    source = _sources(structured.get("source"), singular=True)
    return {
        "category": "exact_source_hydration",
        "public_invocation_count": 1,
        "application_error": False,
        "source": {key: value for key, value in source.items() if key != "by_id"},
        "relationships": {
            "status": "not_applicable",
            "semantic_relationship_count": 0,
            "proof_validated_relationship_count": 0,
            "actual_traversed_edge_count": 0,
            "actual_traversed_edge_count_status": "not_applicable",
            "delivered_relationship_count": 0,
            "delivered_relationship_count_status": "not_applicable",
        },
        "ownership": {"status": "not_applicable", "ownership_association_count": 0},
        "byte_accounting": _byte_accounting(result, structured, source),
        "actual_host_proof_status": "pending_model_delivery",
    }


def _unknown_readout(category: str, result: Any) -> dict[str, Any]:
    source = {"status": "unknown_schema", "source_record_count": None, "source_content_bytes": None}
    return {
        "category": category,
        "public_invocation_count": 1,
        "application_error": False,
        "source": source,
        "relationships": {
            "status": "unknown_schema",
            "semantic_relationship_count": None,
            "proof_validated_relationship_count": None,
            "actual_traversed_edge_count": None,
            "delivered_relationship_count": None,
        },
        "ownership": {"status": "unknown_schema", "ownership_association_count": None},
        "byte_accounting": _byte_accounting(result, None, source),
        "actual_host_proof_status": "pending_model_delivery",
    }


def _set_host_proof(readout: dict[str, Any], model_delivery: Any) -> None:
    if not isinstance(model_delivery, Mapping) or model_delivery.get("status") != "full_exact":
        readout["actual_host_proof_status"] = "not_model_delivered"
        return
    relationships = readout["relationships"]
    source = readout["source"]
    byte_accounting = readout["byte_accounting"]
    if readout["application_error"]:
        readout["actual_host_proof_status"] = "source_free_error"
    elif (
        source["status"] == "complete"
        and relationships["status"] in {"complete", "not_applicable"}
        and relationships.get("actual_traversed_edge_count_status", "complete")
        in {"complete", "not_applicable"}
        and relationships.get("delivered_relationship_count_status", "complete")
        in {"complete", "not_applicable"}
        and byte_accounting["status"] == "complete"
    ):
        readout["actual_host_proof_status"] = "validated"
    else:
        readout["actual_host_proof_status"] = "unknown"


def _total(
    entries: Sequence[Mapping[str, Any]],
    section: str,
    key: str,
    *,
    status_key: str | None = None,
) -> tuple[int | None, str]:
    values = [entry[section].get(key) for entry in entries]
    if any(value is None for value in values):
        return None, "unknown"
    if any(type(value) is not int or value < 0 for value in values):
        return None, "unknown"
    total = sum(values)
    if status_key is None:
        return total, "complete"
    statuses = [entry[section].get(status_key) for entry in entries]
    if any(status == "mismatch" for status in statuses):
        return total, "mismatch"
    if any(status not in {"complete", "known_source_free_error", "not_applicable"} for status in statuses):
        return total, "unknown"
    return total, "complete"


def _combined_status(entries: Sequence[Mapping[str, Any]], key: str) -> str:
    statuses = [entry["byte_accounting"].get(key) for entry in entries]
    if any(status == "mismatch" for status in statuses):
        return "mismatch"
    if all(status == "complete" for status in statuses):
        return "complete"
    return "unknown"


def observe_normal_rollout(rollout: str | Path, run_metadata: Mapping[str, Any]) -> dict[str, Any]:
    """Observe a rollout and add normal-operation accounting without mutation.

    The input observer artifact is freshly created for every call.  Thus a
    normal readout cannot patch shared observer functions or inherit stale
    source-count aggregates from the legacy operation shapes.
    """

    observed = observe_rollout(rollout, run_metadata)
    calls = observed["mcp_calls"]
    normal_calls: list[dict[str, Any]] = []
    for call in calls:
        tool = call.get("tool")
        if tool not in _NORMAL_TOOLS:
            continue
        readout = _retrieve_readout(call) if tool == "loci_retrieve" else _read_readout(call)
        _set_host_proof(readout, call.get("model_delivery"))
        normal_calls.append({"item_id": call["item_id"], **readout})

    source_bytes, source_bytes_status = _total(normal_calls, "source", "source_content_bytes")
    semantic, semantic_status = _total(
        normal_calls, "relationships", "semantic_relationship_count"
    )
    proof_validated, proof_validated_status = _total(
        normal_calls, "relationships", "proof_validated_relationship_count"
    )
    traversed, traversed_status = _total(
        normal_calls,
        "relationships",
        "actual_traversed_edge_count",
        status_key="actual_traversed_edge_count_status",
    )
    delivered, delivered_status = _total(
        normal_calls,
        "relationships",
        "delivered_relationship_count",
        status_key="delivered_relationship_count_status",
    )
    ownership, ownership_status = _total(
        normal_calls, "ownership", "ownership_association_count"
    )
    reported_evidence, _ = _total(
        normal_calls, "byte_accounting", "reported_evidence_bytes"
    )
    actual_evidence, _ = _total(
        normal_calls, "byte_accounting", "actual_evidence_bytes"
    )
    reported_output, _ = _total(
        normal_calls, "byte_accounting", "reported_output_bytes"
    )
    actual_output, _ = _total(
        normal_calls, "byte_accounting", "actual_output_bytes"
    )
    normal_cost = {
        "public_invocations": len(normal_calls),
        "normal_context_retrieval_invocations": sum(
            entry["category"] == "normal_context_retrieval" for entry in normal_calls
        ),
        "exact_source_hydration_invocations": sum(
            entry["category"] == "exact_source_hydration" for entry in normal_calls
        ),
        "source_content_bytes": source_bytes,
        "source_content_bytes_status": source_bytes_status,
        "semantic_relationship_count": semantic,
        "semantic_relationship_count_status": semantic_status,
        "proof_validated_relationship_count": proof_validated,
        "proof_validated_relationship_count_status": proof_validated_status,
        "actual_traversed_edge_count": traversed,
        "actual_traversed_edge_count_status": traversed_status,
        "reported_delivered_relationship_count": delivered,
        "reported_delivered_relationship_count_status": delivered_status,
        "ownership_association_count": ownership,
        "ownership_association_count_status": ownership_status,
        "reported_evidence_bytes": reported_evidence,
        "actual_evidence_bytes": actual_evidence,
        "evidence_bytes_status": _combined_status(normal_calls, "evidence_bytes_status"),
        "reported_output_bytes": reported_output,
        "actual_output_bytes": actual_output,
        "output_bytes_status": _combined_status(normal_calls, "output_bytes_status"),
        "byte_accounting_status": _combined_status(normal_calls, "status"),
    }
    return {
        "adapter_version": NORMAL_ADAPTER_VERSION,
        "native_adapter_version": NATIVE_ADAPTER_VERSION,
        "observation": observed,
        "normal_calls": normal_calls,
        "normal_cost": normal_cost,
    }


def normal_evidence_registry(normal_observation: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    """Return the reviewer-compatible support registry for normal graph calls.

    A relationship can be offered to the existing review validator only after
    the source/edge proof validated *and* the exact result was emitted in a
    unique outer Code Mode output block.
    """

    observed = normal_observation.get("observation")
    normal_calls = normal_observation.get("normal_calls")
    if not isinstance(observed, Mapping) or not isinstance(normal_calls, list):
        raise ObservationError("invalid_normal_observation", "normal observation has invalid wrapper fields")
    mcp_by_id = {
        call.get("item_id"): call for call in observed.get("mcp_calls", []) if isinstance(call, Mapping)
    }
    registry: dict[str, dict[str, Any]] = {}
    for entry in normal_calls:
        if not isinstance(entry, Mapping) or not isinstance(entry.get("item_id"), str):
            raise ObservationError("invalid_normal_observation", "normal_calls contains an invalid item")
        item_id = entry["item_id"]
        call = mcp_by_id.get(item_id)
        if not isinstance(call, Mapping):
            raise ObservationError("invalid_normal_observation", f"normal item {item_id} is absent from observer calls")
        relationship = entry.get("relationships")
        count = relationship.get("semantic_relationship_count") if isinstance(relationship, Mapping) else None
        matches = call.get("model_delivery", {}).get("matches", []) if isinstance(call.get("model_delivery"), Mapping) else []
        refs = (
            [match["output_ref"] for match in matches if isinstance(match, Mapping) and isinstance(match.get("output_ref"), str)]
            if entry.get("actual_host_proof_status") == "validated"
            else []
        )
        registry[item_id] = {"semantic_relationship_count": count, "model_output_refs": refs}
    return registry
