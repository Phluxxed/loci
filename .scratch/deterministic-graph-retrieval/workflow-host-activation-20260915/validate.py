#!/usr/bin/env python3
"""Offline acceptance validator for W1.8.4.4 actual-host captures.

This script never imports or invokes Loci. It validates saved full MCP result
objects against the retained local oracle and the canonical 638-file source
snapshot.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path, PurePosixPath
from typing import Any


HERE = Path(__file__).resolve().parent
ROOT = Path(__file__).resolve().parents[3]
ORACLE = ROOT / ".scratch/deterministic-graph-retrieval/diagnosis/ordinary-workflow"
CASES = ROOT / "benchmarks/comparisons/ordinary-adoption-v1/cases.json"
REPO_ARGUMENT = "/tmp/anvil-source-tasks-20260914/t16"
SOURCE = Path(REPO_ARGUMENT).resolve()

MAX_EVIDENCE_BYTES = 8192
MAX_OUTPUT_BYTES = 16384
SHORT_REF = re.compile(r"sr1_[a-z2-7]{26}\Z")

FUNCTION = "src/tool-results/service.ts::captureCommandResult#function"
OPTIONS = "src/tool-results/service.ts::CaptureCommandResultOptions#type"
BINDING = "src/work-context/binding.ts::WorkContextBinding#type"

RETRIEVES = {
    "function": {
        "query": "captureCommandResult",
    },
    "rich-query": {
        "query": "captureCommandResult work context binding accepted type imported public contract",
    },
    "explicit-pair": {
        "query": "binding contract",
        "seed_ids": [OPTIONS, BINDING],
    },
    "binding-file": {
        "query": "src/work-context/binding.ts",
    },
    "browser": {
        "query": "runBrowserCli",
    },
    "renderer": {
        "query": "renderActiveTask",
    },
}


def load_json(path: Path) -> Any:
    return json.loads(path.read_text())


def compact_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode()


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def request_key(operation: str, request: dict[str, Any]) -> tuple[str, str]:
    return operation, json.dumps(request, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


class Audit:
    def __init__(self) -> None:
        self.failures: list[dict[str, Any]] = []

    def require(self, condition: bool, code: str, **details: Any) -> bool:
        if not condition:
            self.failures.append({"code": code, **details})
        return condition


def source_identity(expected_hashes: dict[str, str]) -> dict[str, Any]:
    symlinks = sorted(
        path.relative_to(SOURCE).as_posix()
        for path in SOURCE.rglob("*")
        if path.is_symlink()
    )
    actual = {
        path.relative_to(SOURCE).as_posix(): sha256_bytes(path.read_bytes())
        for path in SOURCE.rglob("*")
        if path.is_file() and not path.is_symlink()
    }
    expected_names = set(expected_hashes)
    actual_names = set(actual)
    mismatches = sorted(
        name
        for name in expected_names & actual_names
        if expected_hashes[name] != actual[name]
    )
    return {
        "expected_files": len(expected_hashes),
        "actual_files": len(actual),
        "hashes_exact": actual == expected_hashes,
        "extra_files": sorted(actual_names - expected_names),
        "missing_files": sorted(expected_names - actual_names),
        "hash_mismatches": mismatches,
        "symlinks": symlinks,
        "no_extras_or_symlinks": not (actual_names - expected_names) and not symlinks,
    }


def valid_relative_source_path(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    path = PurePosixPath(value)
    return not path.is_absolute() and ".." not in path.parts and value == path.as_posix()


def validate_source(
    audit: Audit,
    source: dict[str, Any],
    expected_hashes: dict[str, str],
    context: str,
) -> int:
    required = {
        "file",
        "start_byte",
        "end_byte",
        "start_line",
        "end_line",
        "content_hash",
        "content",
        "source_ref",
    }
    audit.require(required <= set(source), "source_fields_missing", context=context)
    file = source.get("file")
    if not audit.require(valid_relative_source_path(file), "unsafe_source_path", context=context, file=file):
        return 0
    assert isinstance(file, str)
    audit.require(file in expected_hashes, "source_not_in_canonical_snapshot", context=context, file=file)
    path = SOURCE / file
    if not audit.require(path.is_file(), "source_file_missing", context=context, file=file):
        return 0
    data = path.read_bytes()
    actual_hash = sha256_bytes(data)
    audit.require(
        source.get("content_hash") == actual_hash == expected_hashes.get(file),
        "source_hash_mismatch",
        context=context,
        file=file,
    )
    start = source.get("start_byte")
    end = source.get("end_byte")
    if not audit.require(
        isinstance(start, int) and isinstance(end, int) and 0 <= start <= end <= len(data),
        "invalid_source_span",
        context=context,
        file=file,
        start_byte=start,
        end_byte=end,
        file_bytes=len(data),
    ):
        return 0
    assert isinstance(start, int) and isinstance(end, int)
    selected = data[start:end]
    content = source.get("content")
    audit.require(
        isinstance(content, str) and content.encode("utf-8") == selected,
        "source_content_not_exact_bytes",
        context=context,
        file=file,
        start_byte=start,
        end_byte=end,
    )
    start_line = data[:start].count(b"\n") + 1
    end_line = start_line + selected.count(b"\n") - (1 if selected.endswith(b"\n") else 0)
    audit.require(
        source.get("start_line") == start_line and source.get("end_line") == end_line,
        "source_line_span_mismatch",
        context=context,
        file=file,
    )
    reference = source.get("source_ref")
    audit.require(
        isinstance(reference, str) and len(reference) == 30 and SHORT_REF.fullmatch(reference) is not None,
        "invalid_source_short_reference",
        context=context,
        source_ref=reference,
    )
    return len(selected)


def validate_usage(
    audit: Audit,
    result: dict[str, Any],
    packet: dict[str, Any],
    evidence_bytes: int,
    context: str,
) -> dict[str, Any]:
    usage = packet.get("usage", {})
    saved_value_bytes = len(compact_bytes(result))
    audit.require(
        usage.get("evidence_bytes") == evidence_bytes,
        "evidence_byte_accounting_mismatch",
        context=context,
        declared=usage.get("evidence_bytes"),
        actual=evidence_bytes,
    )
    audit.require(
        isinstance(usage.get("output_bytes"), int) and usage["output_bytes"] <= MAX_OUTPUT_BYTES,
        "output_budget_exceeded",
        context=context,
        output_bytes=usage.get("output_bytes"),
    )
    audit.require(
        isinstance(usage.get("evidence_bytes"), int) and usage["evidence_bytes"] <= MAX_EVIDENCE_BYTES,
        "evidence_budget_exceeded",
        context=context,
        evidence_bytes=usage.get("evidence_bytes"),
    )
    audit.require(
        usage.get("output_encoding") == "mcp_result_json_utf8",
        "unexpected_output_encoding",
        context=context,
        output_encoding=usage.get("output_encoding"),
    )
    return {
        "declared_native_output_bytes": usage.get("output_bytes"),
        "saved_value_compact_reencoding_bytes": saved_value_bytes,
        "saved_reencoding_minus_declared_bytes": (
            saved_value_bytes - usage["output_bytes"]
            if isinstance(usage.get("output_bytes"), int)
            else None
        ),
        "declared_evidence_bytes": usage.get("evidence_bytes"),
        "validated_unique_evidence_interval_bytes": evidence_bytes,
        "original_live_wire_bytes_independently_observed": False,
    }


def unique_interval_bytes(sources: list[dict[str, Any]]) -> int:
    """Count the union of source byte intervals for each file/hash identity."""
    groups: dict[tuple[str, str], list[tuple[int, int]]] = {}
    for source in sources:
        file = source.get("file")
        content_hash = source.get("content_hash")
        start = source.get("start_byte")
        end = source.get("end_byte")
        if (
            isinstance(file, str)
            and isinstance(content_hash, str)
            and isinstance(start, int)
            and isinstance(end, int)
        ):
            groups.setdefault((file, content_hash), []).append((start, end))
    total = 0
    for intervals in groups.values():
        merged: list[list[int]] = []
        for start, end in sorted(intervals):
            if not merged or start > merged[-1][1]:
                merged.append([start, end])
            else:
                merged[-1][1] = max(merged[-1][1], end)
        total += sum(end - start for start, end in merged)
    return total


def validate_retrieve(
    audit: Audit,
    label: str,
    result: dict[str, Any],
    expected_hashes: dict[str, str],
) -> dict[str, Any]:
    packet = result.get("structuredContent", {})
    sources = packet.get("sources", [])
    valid_sources: list[dict[str, Any]] = []
    for index, source in enumerate(sources):
        if isinstance(source, dict):
            validate_source(audit, source, expected_hashes, f"{label}.sources[{index}]")
            valid_sources.append(source)
        else:
            audit.require(False, "source_not_object", context=f"{label}.sources[{index}]")
    evidence_bytes = unique_interval_bytes(valid_sources)
    source_by_id = {
        source.get("id"): source
        for source in sources
        if isinstance(source, dict) and isinstance(source.get("id"), int)
    }
    audit.require(len(source_by_id) == len(sources), "duplicate_or_invalid_source_ids", context=label)

    items = packet.get("items", [])
    for index, item in enumerate(items):
        reference = item.get("source_ref") if isinstance(item, dict) else None
        audit.require(
            isinstance(reference, str) and len(reference) == 30 and SHORT_REF.fullmatch(reference) is not None,
            "invalid_item_short_reference",
            context=f"{label}.items[{index}]",
            source_ref=reference,
        )
        extent = item.get("extent", {}) if isinstance(item, dict) else {}
        file = extent.get("file")
        audit.require(
            valid_relative_source_path(file) and file in expected_hashes,
            "invalid_item_extent_file",
            context=f"{label}.items[{index}]",
            file=file,
        )
        if isinstance(file, str) and file in expected_hashes:
            data = (SOURCE / file).read_bytes()
            audit.require(
                extent.get("content_hash") == expected_hashes[file] == sha256_bytes(data),
                "item_extent_hash_mismatch",
                context=f"{label}.items[{index}]",
            )
            start, end = extent.get("start_byte"), extent.get("end_byte")
            audit.require(
                isinstance(start, int) and isinstance(end, int) and 0 <= start <= end <= len(data),
                "invalid_item_extent_span",
                context=f"{label}.items[{index}]",
            )

    node_ids = {
        node.get("id") for node in packet.get("nodes", []) if isinstance(node, dict)
    }
    relationships = packet.get("relationships", [])
    for index, relation in enumerate(relationships):
        context = f"{label}.relationships[{index}]"
        if not isinstance(relation, dict):
            audit.require(False, "relationship_not_object", context=context)
            continue
        audit.require(relation.get("proof") == "complete", "relationship_proof_incomplete", context=context)
        edge = relation.get("edge", {})
        audit.require(
            edge.get("from") in node_ids and edge.get("to") in node_ids,
            "relationship_endpoint_missing",
            context=context,
        )
        linked_ids = relation.get("source_ids", [])
        audit.require(
            isinstance(linked_ids, list) and bool(linked_ids) and all(value in source_by_id for value in linked_ids),
            "relationship_source_link_incomplete",
            context=context,
            source_ids=linked_ids,
        )
        evidence = edge.get("evidence", {})
        evidence_file = evidence.get("file")
        evidence_hash = evidence.get("content_hash")
        evidence_line = evidence.get("line")
        audit.require(
            isinstance(evidence_file, str)
            and evidence_file in expected_hashes
            and evidence_hash == expected_hashes[evidence_file],
            "relationship_evidence_identity_invalid",
            context=context,
        )
        linked_proof = any(
            source_by_id[source_id].get("file") == evidence_file
            and source_by_id[source_id].get("content_hash") == evidence_hash
            and isinstance(evidence_line, int)
            and source_by_id[source_id].get("start_line", evidence_line + 1)
            <= evidence_line
            <= source_by_id[source_id].get("end_line", evidence_line - 1)
            for source_id in linked_ids
            if source_id in source_by_id
        )
        audit.require(linked_proof, "relationship_evidence_not_covered_by_linked_source", context=context)

    limits = packet.get("limits", {})
    audit.require(limits.get("max_output_bytes") == MAX_OUTPUT_BYTES, "unexpected_output_limit", context=label)
    audit.require(limits.get("max_evidence_bytes") == MAX_EVIDENCE_BYTES, "unexpected_evidence_limit", context=label)
    accounting = validate_usage(audit, result, packet, evidence_bytes, label)
    audit.require(packet.get("status") == "partial", "retrieval_partial_status_not_preserved", context=label)
    audit.require(
        packet.get("scope", {}).get("coverage") == "partial"
        and packet.get("scope", {}).get("exhaustive") is False,
        "retrieval_partial_scope_not_preserved",
        context=label,
    )
    audit.require(bool(packet.get("omissions")), "retrieval_omissions_not_preserved", context=label)
    return {
        "status": packet.get("status"),
        "coverage": packet.get("scope", {}).get("coverage"),
        "exhaustive": packet.get("scope", {}).get("exhaustive"),
        "omissions": packet.get("omissions"),
        "items": len(items),
        "sources": len(sources),
        "relationships": len(relationships),
        "usage": packet.get("usage"),
        "accounting": accounting,
    }


def validate_read(
    audit: Audit,
    label: str,
    result: dict[str, Any],
    expected_hashes: dict[str, str],
) -> dict[str, Any]:
    packet = result.get("structuredContent", {})
    source = packet.get("source")
    evidence_bytes = 0
    if isinstance(source, dict):
        evidence_bytes = validate_source(audit, source, expected_hashes, f"{label}.source")
    else:
        audit.require(False, "read_source_not_object", context=label)
        source = {}
    reference = packet.get("next_source_ref")
    audit.require(
        reference is None
        or (isinstance(reference, str) and len(reference) == 30 and SHORT_REF.fullmatch(reference) is not None),
        "invalid_next_short_reference",
        context=label,
        next_source_ref=reference,
    )
    accounting = validate_usage(audit, result, packet, evidence_bytes, label)
    audit.require(packet.get("status") == "ok", "read_status_not_ok", context=label)
    return {
        "status": packet.get("status"),
        "complete": packet.get("complete"),
        "next_source_ref": reference,
        "source": {
            "file": source.get("file"),
            "start_byte": source.get("start_byte"),
            "end_byte": source.get("end_byte"),
            "source_ref": source.get("source_ref"),
        },
        "usage": packet.get("usage"),
        "accounting": accounting,
    }


def relation_set(packet: dict[str, Any]) -> set[tuple[str, str, str, str]]:
    return {
        (
            relation["edge"]["from"],
            relation["edge"]["to"],
            relation["edge"]["type"],
            relation["traversed"],
        )
        for relation in packet.get("relationships", [])
    }


def build_expected_calls() -> tuple[
    dict[tuple[str, str], tuple[str, str, dict[str, Any]]],
    dict[str, dict[str, Any]],
]:
    calls: dict[tuple[str, str], tuple[str, str, dict[str, Any]]] = {}
    retrieve_results: dict[str, dict[str, Any]] = {}
    for label, args in RETRIEVES.items():
        result = load_json(ORACLE / f"{label}-envelope.json")
        retrieve_results[label] = result
        request = {"repo": REPO_ARGUMENT, **args}
        calls[request_key("loci_retrieve", request)] = (label, "retrieve", result)

    for retrieve_label in ("function", "binding-file"):
        packets = load_json(ORACLE / f"{retrieve_label}-read-pages.json")
        anchor = next(
            item
            for item in retrieve_results[retrieve_label]["structuredContent"]["items"]
            if item["role"] == "anchor"
        )
        reference = anchor["source_ref"]
        for index, packet in enumerate(packets, start=1):
            label = f"{retrieve_label}-read-{index}"
            request = {"repo": REPO_ARGUMENT, "source_ref": reference}
            result = {"content": [], "structuredContent": packet, "isError": False}
            calls[request_key("loci_read", request)] = (label, "read", result)
            reference = packet["next_source_ref"]
        if reference is not None:
            raise ValueError(f"oracle read sequence for {retrieve_label} is incomplete")
    return calls, retrieve_results


def validate_read_sequence(
    audit: Audit,
    retrieve_label: str,
    read_labels: list[str],
    expected_bytes: int,
    matched: dict[str, dict[str, Any]],
) -> dict[str, Any] | None:
    if retrieve_label not in matched or any(label not in matched for label in read_labels):
        return None
    retrieve_packet = matched[retrieve_label]["result"]["structuredContent"]
    anchor = next(item for item in retrieve_packet["items"] if item["role"] == "anchor")
    extent = anchor["extent"]
    offset = extent["start_byte"]
    pieces: list[bytes] = []
    requested_reference = anchor["source_ref"]
    pages: list[dict[str, Any]] = []
    for index, label in enumerate(read_labels):
        record = matched[label]
        packet = record["result"]["structuredContent"]
        source = packet["source"]
        audit.require(
            record["request"].get("source_ref") == requested_reference,
            "read_chain_request_reference_mismatch",
            context=label,
        )
        audit.require(
            source["file"] == extent["file"] and source["content_hash"] == extent["content_hash"],
            "read_owning_extent_identity_mismatch",
            context=label,
        )
        audit.require(source["start_byte"] == offset, "read_pages_not_contiguous", context=label)
        offset = source["end_byte"]
        pieces.append(source["content"].encode("utf-8"))
        requested_reference = packet["next_source_ref"]
        expected_complete = index == len(read_labels) - 1
        audit.require(packet["complete"] is expected_complete, "read_complete_flag_mismatch", context=label)
        pages.append(
            {
                "label": label,
                "request_source_ref": record["request"].get("source_ref"),
                "returned_source_ref": source["source_ref"],
                "start_byte": source["start_byte"],
                "end_byte": source["end_byte"],
                "complete": packet["complete"],
                "next_source_ref": packet["next_source_ref"],
            }
        )
    audit.require(requested_reference is None, "read_sequence_has_continuation", context=retrieve_label)
    audit.require(offset == extent["end_byte"], "read_sequence_does_not_end_at_extent", context=retrieve_label)
    file_bytes = (SOURCE / extent["file"]).read_bytes()
    expected = file_bytes[extent["start_byte"] : extent["end_byte"]]
    reconstructed = b"".join(pieces)
    audit.require(reconstructed == expected, "read_sequence_bytes_not_exact_extent", context=retrieve_label)
    audit.require(len(reconstructed) == expected_bytes, "read_sequence_length_mismatch", context=retrieve_label)
    return {
        "anchor_node_id": anchor["node_id"],
        "extent": extent,
        "pages": pages,
        "reconstructed_bytes": len(reconstructed),
        "exact_owning_extent": reconstructed == expected,
        "contiguous": offset == extent["end_byte"],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=HERE / "validation.json")
    args = parser.parse_args()
    output = args.output.resolve()
    if output.parent != HERE or not output.name.startswith("validation") or output.suffix != ".json":
        raise SystemExit("output must be a validation*.json file in the activation evidence directory")

    audit = Audit()
    cases = load_json(CASES)
    expected_hashes = cases["source_files"]
    source_before = source_identity(expected_hashes)
    audit.require(source_before["hashes_exact"], "source_snapshot_not_exact", phase="before")
    audit.require(not source_before["symlinks"], "source_snapshot_has_symlinks", phase="before")

    expected_calls, _ = build_expected_calls()
    raw_paths = sorted(HERE.glob("raw-call-*.json"))
    matched: dict[str, dict[str, Any]] = {}
    records: list[dict[str, Any]] = []
    for path in raw_paths:
        try:
            raw_bytes = path.read_bytes()
            record = json.loads(raw_bytes)
        except (OSError, json.JSONDecodeError) as error:
            audit.require(False, "raw_record_unreadable", file=path.name, error=str(error))
            continue
        audit.require(
            isinstance(record, dict) and set(record) == {"operation", "request", "result"},
            "raw_record_shape_invalid",
            file=path.name,
        )
        if not isinstance(record, dict):
            continue
        operation, request, result = record.get("operation"), record.get("request"), record.get("result")
        if not isinstance(operation, str) or not isinstance(request, dict) or not isinstance(result, dict):
            audit.require(False, "raw_record_types_invalid", file=path.name)
            continue
        key = request_key(operation, request)
        expected = expected_calls.get(key)
        if expected is None:
            audit.require(False, "unexpected_raw_call", file=path.name, operation=operation, request=request)
            continue
        label, kind, expected_result = expected
        if label in matched:
            audit.require(False, "duplicate_raw_call", file=path.name, label=label)
            continue
        matched[label] = {"path": path, "request": request, "result": result}
        exact = result == expected_result
        audit.require(exact, "complete_envelope_not_equal_to_local_oracle", file=path.name, label=label)
        audit.require(
            set(result) == {"content", "structuredContent", "isError"}
            and result.get("content") == []
            and result.get("isError") is False
            and isinstance(result.get("structuredContent"), dict),
            "native_mcp_result_shape_invalid",
            file=path.name,
            label=label,
        )
        details = (
            validate_retrieve(audit, label, result, expected_hashes)
            if kind == "retrieve"
            else validate_read(audit, label, result, expected_hashes)
        )
        records.append(
            {
                "label": label,
                "kind": kind,
                "raw_record": path.name,
                "raw_record_sha256": sha256_bytes(raw_bytes),
                "complete_envelope_equal_to_local_oracle": exact,
                "equality_basis": "complete parsed JSON object equality; not original live-wire byte identity",
                "result_sha256": sha256_bytes(compact_bytes(result)),
                **details,
            }
        )

    expected_labels = {value[0] for value in expected_calls.values()}
    missing = sorted(expected_labels - set(matched))
    for label in missing:
        audit.require(False, "expected_raw_call_missing", label=label)

    function_path = {
        (FUNCTION, OPTIONS, "uses_type"),
        (OPTIONS, BINDING, "uses_type"),
    }
    path_checks: dict[str, bool] = {}
    for label in ("function", "rich-query", "explicit-pair"):
        if label in matched:
            relations = relation_set(matched[label]["result"]["structuredContent"])
            triples = {(origin, target, kind) for origin, target, kind, _ in relations}
            path_checks[label] = function_path <= triples
            audit.require(path_checks[label], "required_function_binding_path_missing", context=label)

    controls = {
        "browser_forward_call": (
            "browser",
            "src/browser/cli.ts::runBrowserCli#function",
            "src/browser/cli.ts::browserCliUsage#function",
            "calls",
            "forward",
        ),
        "browser_reverse_call": (
            "browser",
            "bin/anvil.ts::main#function",
            "src/browser/cli.ts::runBrowserCli#function",
            "calls",
            "reverse",
        ),
        "renderer_forward_call": (
            "renderer",
            "src/continuity/render.ts::renderActiveTask#function",
            "src/continuity/render.ts::truncateText#function",
            "calls",
            "forward",
        ),
        "renderer_reverse_call": (
            "renderer",
            "src/continuity/render.ts::renderContinuityFrame#function",
            "src/continuity/render.ts::renderActiveTask#function",
            "calls",
            "reverse",
        ),
    }
    control_checks: dict[str, bool] = {}
    for check, (label, origin, target, kind, traversal) in controls.items():
        if label in matched:
            present = (origin, target, kind, traversal) in relation_set(
                matched[label]["result"]["structuredContent"]
            )
            control_checks[check] = present
            audit.require(present, "required_call_control_missing", context=check)

    reads = {
        "function": validate_read_sequence(
            audit, "function", ["function-read-1"], 4468, matched
        ),
        "binding-file": validate_read_sequence(
            audit,
            "binding-file",
            ["binding-file-read-1", "binding-file-read-2"],
            14082,
            matched,
        ),
    }

    source_after = source_identity(expected_hashes)
    audit.require(source_after["hashes_exact"], "source_snapshot_not_exact", phase="after")
    audit.require(not source_after["symlinks"], "source_snapshot_has_symlinks", phase="after")
    audit.require(source_before == source_after, "source_snapshot_changed_during_validation")

    missing_only = bool(audit.failures) and all(
        failure["code"] == "expected_raw_call_missing" for failure in audit.failures
    )
    passed = not audit.failures and len(matched) == len(expected_calls)
    status = "passed" if passed else ("pending" if missing_only else "failed")
    result = {
        "schema_version": 1,
        "task": "W1.8.4.4",
        "status": status,
        "passed": passed,
        "scope": "Offline validation of primary-saved actual-host full MCP result objects; no Loci invocation and no token/provider benchmark.",
        "validator": {
            "model": "GPT-5.6 Sol",
            "reasoning_effort": "high",
            "fork_turns": "none",
            "independent_from_call_execution": True,
        },
        "canonical_source": {
            "root": REPO_ARGUMENT,
            "source_commit": cases.get("source_commit"),
            "expected_hashes": len(expected_hashes),
            "before": source_before,
            "after": source_after,
        },
        "call_set": {
            "expected": len(expected_calls),
            "observed": len(raw_paths),
            "matched": len(matched),
            "missing": missing,
            "records": sorted(records, key=lambda row: row["label"]),
        },
        "graph_acceptance": {
            "function_to_options_to_binding": path_checks,
            "browser_renderer_controls": control_checks,
            "relationship_rule": "Every delivered relationship must have proof=complete and a linked, byte-validated source spanning its evidence line.",
        },
        "owning_extent_reads": reads,
        "preserved_semantics": {
            "retrieval_status": "partial",
            "coverage": "partial",
            "exhaustive": False,
            "omissions_are_retained_per_record": True,
            "unsupported_or_omitted_relationships_are_not_treated_as_absent": True,
        },
        "provenance": {
            "basis": "Saved raw-call records containing operation, exact request, and the full MCP result object.",
            "raw_record_hashes_recorded": True,
            "complete_envelope_comparison": "Exact parsed JSON object equality against retained local results.",
            "saved_reencoding_qualification": "The raw artifacts were saved after JavaScript JSON normalization. Integral producer floats can re-encode with fewer bytes, so the saved value's compact size is reported separately from usage.output_bytes.",
            "independent_host_transport_observation": False,
            "original_live_wire_byte_equality": "not observed",
            "completed_provider_interval": None,
            "full_outer_model_visible_delivery": "not established by these raw result objects",
        },
        "failures": audit.failures,
        "limitations": [
            "The validator did not execute or observe the host calls; actual-host attribution comes from the primary-owned raw-call capture process.",
            "The saved full MCP result objects establish the native response contents, but do not establish a completed provider interval.",
            "Reduced UI or model-visible displays do not establish that the complete native response was delivered through the outer model context.",
            "Partial coverage and recorded omissions remain limitations; unsupported or omitted semantics are not negative evidence.",
        ],
    }
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(
        json.dumps(
            {
                "status": status,
                "passed": passed,
                "matched_calls": len(matched),
                "expected_calls": len(expected_calls),
                "failures": len(audit.failures),
                "output": output.relative_to(ROOT).as_posix(),
            }
        )
    )
    return 0 if passed else (2 if status == "pending" else 1)


if __name__ == "__main__":
    raise SystemExit(main())
