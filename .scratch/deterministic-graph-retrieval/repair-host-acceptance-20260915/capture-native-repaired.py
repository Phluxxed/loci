#!/usr/bin/env python3
"""Capture the bounded repaired-host Loci calls from the original native rollout.

This is a call-level functional receipt.  It deliberately does not construct a
completed primary turn, calculate provider cost, or retain unrelated native
tool payloads.
"""
from __future__ import annotations

import base64
from collections import Counter
import hashlib
import json
from pathlib import Path, PurePosixPath
import sys
from typing import Any, Mapping

HERE = Path(__file__).resolve().parent
WORKSPACE = HERE.parents[2]
sys.path.insert(0, str(WORKSPACE))

from benchmarks.ordinary_adoption_delivery_v3 import (
    _json_equal,
    _text_blocks,
    supplement_delivery,
)
from benchmarks.ordinary_adoption_native_v2 import _collect_operations
from benchmarks.ordinary_adoption_normal import (
    _read_readout,
    _retrieve_readout,
    _set_host_proof,
)
from benchmarks.ordinary_adoption_observed import (
    _collect_outer,
    _correlate_delivery,
    _read_rollout,
)


ROLLOUT = Path(
    "/Users/brummerv/.codex/sessions/2026/09/14/"
    "rollout-2026-09-14T14-07-34-01a09e19-5048-79d3-96dd-697eda8a4ac8.jsonl"
)
THREAD_ID = "01a09e19-5048-79d3-96dd-697eda8a4ac8"
TURN_ID = "01a0a225-8986-7463-9346-9279213d9749"
START_LINE = 6309
END_LINE = 6533
TARGET_REPO = Path("/private/tmp/anvil-source-tasks-20260914/t23")
CASES = WORKSPACE / "benchmarks/comparisons/ordinary-adoption-v1/cases.json"
RESTORATION = HERE / "source-restoration-receipt.json"
CAPTURE_OUT = HERE / "capture-native-receipt.json"
VALIDATION_OUT = HERE / "validation-summary.json"

CAPTURE = "src/tool-results/service.ts::CaptureCommandResultOptions#type"
BINDING = "src/work-context/binding.ts::WorkContextBinding#type"
RUN_BROWSER = "src/browser/cli.ts::runBrowserCli#function"
BROWSER_USAGE = "src/browser/cli.ts::browserCliUsage#function"
MAIN = "bin/anvil.ts::main#function"
RENDER_ACTIVE = "src/continuity/render.ts::renderActiveTask#function"
TRUNCATE = "src/continuity/render.ts::truncateText#function"
RENDER_FRAME = "src/continuity/render.ts::renderContinuityFrame#function"

EXPECTED_EDGES = {
    "options": {(CAPTURE, "uses_type", BINDING)},
    "explicit_pair": {(CAPTURE, "uses_type", BINDING)},
    "browser": {
        (RUN_BROWSER, "calls", BROWSER_USAGE),
        (MAIN, "calls", RUN_BROWSER),
    },
    "renderer": {
        (RENDER_ACTIVE, "calls", TRUNCATE),
        (RENDER_FRAME, "calls", RENDER_ACTIVE),
    },
    "binding_file": set(),
}

RAW_FILES = {
    "missing_source": "missing-source.json",
    "options": "raw-call-01-options.json",
    "explicit_pair": "raw-call-02-pair.json",
    "browser": "raw-call-03-browser.json",
    "renderer": "raw-call-04-renderer.json",
    "binding_file": "raw-call-05-binding-file.json",
    "read_page_1": "raw-call-06-read-page1.json",
    "read_page_2": "raw-call-07-read-page2.json",
}


def compact(value: Any, *, sort_keys: bool = False) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=sort_keys,
    ).encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def require(condition: bool, message: str, errors: list[str]) -> bool:
    if not condition:
        errors.append(message)
    return condition


def application_error(result: Any) -> bool:
    structured = result.get("structuredContent") if isinstance(result, Mapping) else None
    return bool(
        isinstance(result, Mapping)
        and (
            result.get("isError") is True
            or (isinstance(structured, Mapping) and "error" in structured)
        )
    )


def classify(call: Mapping[str, Any]) -> str:
    args = call["arguments"]
    result = call["result"]
    if call["tool"] == "loci_read":
        decoded = decode_ref(args["source_ref"])
        return "read_page_1" if decoded["offset"] == decoded["start"] else "read_page_2"
    query = args.get("query")
    seeds = args.get("seed_ids")
    if query == "CaptureCommandResultOptions" and application_error(result):
        return "missing_source"
    if query == "CaptureCommandResultOptions" and seeds is None:
        return "options"
    if query == "binding contract" and seeds == [CAPTURE, BINDING]:
        return "explicit_pair"
    if query == "runBrowserCli" and seeds is None:
        return "browser"
    if query == "renderActiveTask" and seeds is None:
        return "renderer"
    if query == "src/work-context/binding.ts" and seeds is None:
        return "binding_file"
    return "unexpected"


def decode_ref(reference: str) -> dict[str, Any]:
    raw = base64.b64decode(
        reference + "=" * (-len(reference) % 4), altchars=b"-_", validate=True
    )
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise ValueError("source reference does not decode to an object")
    return value


def encode_ref(value: Mapping[str, Any]) -> str:
    raw = compact(value, sort_keys=True)
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def validate_ref(reference: Any, errors: list[str], *, context: str) -> dict[str, Any] | None:
    try:
        require(isinstance(reference, str) and bool(reference), f"{context}: missing source_ref", errors)
        if not isinstance(reference, str) or not reference:
            return None
        value = decode_ref(reference)
    except (ValueError, UnicodeError, json.JSONDecodeError) as exc:
        errors.append(f"{context}: invalid source_ref: {exc}")
        return None
    require(
        set(value) == {"v", "repo", "file", "hash", "start", "end", "offset"},
        f"{context}: wrong source_ref fields",
        errors,
    )
    require(value.get("v") == 1 and type(value.get("v")) is int, f"{context}: wrong version", errors)
    require(value.get("repo") == str(TARGET_REPO), f"{context}: wrong canonical repo", errors)
    file = value.get("file")
    require(
        isinstance(file, str)
        and bool(file)
        and "\\" not in file
        and not PurePosixPath(file).is_absolute()
        and ".." not in PurePosixPath(file).parts,
        f"{context}: unsafe file",
        errors,
    )
    require(
        isinstance(value.get("hash"), str) and len(value["hash"]) == 64,
        f"{context}: invalid hash",
        errors,
    )
    offsets = [value.get(key) for key in ("start", "offset", "end")]
    require(
        all(type(item) is int for item in offsets)
        and 0 <= offsets[0] <= offsets[1] <= offsets[2],
        f"{context}: invalid offsets",
        errors,
    )
    require(encode_ref(value) == reference, f"{context}: noncanonical encoding", errors)
    return value


def extract_native_result(raw_line: bytes) -> bytes:
    """Return the exact result JSON token embedded in one native JSONL record."""
    item_at = raw_line.find(b'"item":')
    if item_at < 0:
        raise ValueError("native line has no item field")
    result_at = raw_line.find(b'"result":', item_at)
    if result_at < 0:
        raise ValueError("native item has no result field")
    start = result_at + len(b'"result":')
    while start < len(raw_line) and raw_line[start] in b" \t\r\n":
        start += 1
    if start >= len(raw_line) or raw_line[start] != ord("{"):
        raise ValueError("native result is not an object token")
    depth = 0
    quoted = False
    escaped = False
    for index in range(start, len(raw_line)):
        byte = raw_line[index]
        if quoted:
            if escaped:
                escaped = False
            elif byte == ord("\\"):
                escaped = True
            elif byte == ord('"'):
                quoted = False
            continue
        if byte == ord('"'):
            quoted = True
        elif byte in (ord("{"), ord("[")):
            depth += 1
        elif byte in (ord("}"), ord("]")):
            depth -= 1
            if depth == 0:
                return raw_line[start : index + 1]
    raise ValueError("unterminated native result object")


def source_line_bounds(raw: bytes, content: str, start: int) -> tuple[int, int]:
    start_line = raw[:start].count(b"\n") + 1
    end_line = max(
        start_line,
        start_line + content.count("\n") - int(content.endswith("\n")),
    )
    return start_line, end_line


def validate_source(source: Any, errors: list[str], *, context: str) -> dict[str, Any]:
    check: dict[str, Any] = {"context": context, "valid": False}
    if not isinstance(source, Mapping):
        errors.append(f"{context}: source is not an object")
        return check
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
    if not require(required <= set(source), f"{context}: incomplete source schema", errors):
        return check
    file = source["file"]
    if not require(
        isinstance(file, str)
        and file
        and "\\" not in file
        and not PurePosixPath(file).is_absolute()
        and ".." not in PurePosixPath(file).parts,
        f"{context}: unsafe source path",
        errors,
    ):
        return check
    path = TARGET_REPO / file
    if not require(path.is_file() and not path.is_symlink(), f"{context}: source file unavailable", errors):
        return check
    raw = path.read_bytes()
    start, end = source["start_byte"], source["end_byte"]
    if not require(
        type(start) is int and type(end) is int and 0 <= start <= end <= len(raw),
        f"{context}: invalid source span",
        errors,
    ):
        return check
    try:
        content = raw[start:end].decode("utf-8")
    except UnicodeError as exc:
        errors.append(f"{context}: source span is not UTF-8: {exc}")
        return check
    actual_hash = sha256_bytes(raw)
    actual_lines = source_line_bounds(raw, content, start)
    locator = validate_ref(source["source_ref"], errors, context=f"{context}.source_ref")
    matches = [
        actual_hash == source["content_hash"],
        content == source["content"],
        len(content.encode("utf-8")) == end - start,
        actual_lines == (source["start_line"], source["end_line"]),
        locator is not None
        and locator["file"] == file
        and locator["hash"] == actual_hash
        and locator["start"] == start
        and locator["offset"] == start
        and locator["end"] == end,
    ]
    require(all(matches), f"{context}: hash/span/line/locator mismatch", errors)
    check.update(
        {
            "file": file,
            "file_bytes": len(raw),
            "content_hash": actual_hash,
            "start_byte": start,
            "end_byte": end,
            "content_bytes": end - start,
            "start_line": actual_lines[0],
            "end_line": actual_lines[1],
            "source_ref": source["source_ref"],
            "valid": all(matches),
        }
    )
    return check


def edge_key(relationship: Mapping[str, Any]) -> tuple[str, str, str] | None:
    edge = relationship.get("edge")
    if not isinstance(edge, Mapping):
        return None
    values = edge.get("from"), edge.get("type"), edge.get("to")
    return values if all(isinstance(value, str) for value in values) else None


def validate_relationships(
    label: str,
    structured: Mapping[str, Any],
    errors: list[str],
) -> dict[str, Any]:
    relationships = structured.get("relationships")
    sources_list = structured.get("sources")
    if not isinstance(relationships, list) or not isinstance(sources_list, list):
        errors.append(f"{label}: malformed relationships or sources")
        return {"valid": False, "required": [], "delivered": []}
    sources = {
        source.get("id"): source
        for source in sources_list
        if isinstance(source, Mapping) and type(source.get("id")) is int
    }
    all_valid = True
    delivered: set[tuple[str, str, str]] = set()
    selected: list[dict[str, Any]] = []
    for index, relationship in enumerate(relationships):
        context = f"{label}.relationships[{index}]"
        if not isinstance(relationship, Mapping):
            errors.append(f"{context}: relationship is not an object")
            all_valid = False
            continue
        key = edge_key(relationship)
        source_ids = relationship.get("source_ids")
        edge = relationship.get("edge")
        evidence = edge.get("evidence") if isinstance(edge, Mapping) else None
        linked = (
            [sources.get(source_id) for source_id in source_ids]
            if isinstance(source_ids, list)
            else []
        )
        valid = bool(
            key is not None
            and relationship.get("proof") == "complete"
            and isinstance(source_ids, list)
            and source_ids
            and all(type(source_id) is int for source_id in source_ids)
            and len(set(source_ids)) == len(source_ids)
            and all(source is not None for source in linked)
            and isinstance(evidence, Mapping)
            and any(
                source["file"] == evidence.get("file")
                and source["content_hash"] == evidence.get("content_hash")
                and source["start_line"] <= evidence.get("line", 0) <= source["end_line"]
                for source in linked
                if source is not None
            )
        )
        require(valid, f"{context}: incomplete or unlinked proof", errors)
        all_valid &= valid
        if key is not None:
            delivered.add(key)
            if key in EXPECTED_EDGES[label]:
                selected.append(
                    {
                        "edge": {"from": key[0], "type": key[1], "to": key[2]},
                        "proof": relationship.get("proof"),
                        "source_ids": source_ids,
                        "proof_files": sorted(
                            {source["file"] for source in linked if source is not None}
                        ),
                    }
                )
    required = EXPECTED_EDGES[label]
    missing = sorted(required - delivered)
    require(not missing, f"{label}: missing expected edges {missing}", errors)
    if label == "browser":
        reverse = next(
            (item for item in selected if edge_key({"edge": item["edge"]}) == (MAIN, "calls", RUN_BROWSER)),
            None,
        )
        require(
            reverse is not None and "src/browser/index.ts" in reverse["proof_files"],
            "browser: reverse call lacks public barrel proof",
            errors,
        )
    return {
        "valid": all_valid and not missing,
        "all_relationship_count": len(relationships),
        "all_relationships_complete": all_valid,
        "required": [
            {"from": edge[0], "type": edge[1], "to": edge[2]}
            for edge in sorted(required)
        ],
        "delivered": selected,
        "missing": [
            {"from": edge[0], "type": edge[1], "to": edge[2]}
            for edge in missing
        ],
    }


def source_manifest(errors: list[str]) -> dict[str, Any]:
    cases = json.loads(CASES.read_text(encoding="utf-8"))
    expected = cases["source_files"]
    actual: dict[str, str] = {}
    unsupported: list[str] = []
    for path in sorted(TARGET_REPO.rglob("*")):
        relative = path.relative_to(TARGET_REPO).as_posix()
        if path.is_symlink() or (not path.is_file() and not path.is_dir()):
            unsupported.append(relative)
        elif path.is_file():
            actual[relative] = sha256_bytes(path.read_bytes())
    missing = sorted(set(expected) - set(actual))
    extra = sorted(set(actual) - set(expected))
    mismatched = [
        {
            "file": file,
            "expected_sha256": expected[file],
            "actual_sha256": actual[file],
        }
        for file in sorted(set(expected) & set(actual))
        if expected[file] != actual[file]
    ]
    passed = not missing and not extra and not mismatched and not unsupported
    require(passed, "fixed source no longer matches the 638-file frozen manifest", errors)
    return {
        "root": str(TARGET_REPO),
        "cases_file": str(CASES),
        "cases_sha256": sha256_bytes(CASES.read_bytes()),
        "source_commit": cases["source_commit"],
        "expected_file_count": len(expected),
        "actual_file_count": len(actual),
        "missing": missing,
        "extra": extra,
        "mismatched": mismatched,
        "unsupported": unsupported,
        "passed": passed,
    }


def emitted_match_check(
    match: Mapping[str, Any],
    outer_by_id: Mapping[str, Mapping[str, Any]],
    expected: Any,
    errors: list[str],
    *,
    label: str,
) -> dict[str, Any]:
    request = outer_by_id.get(match["call_id"])
    if request is None:
        errors.append(f"{label}: exact match refers to absent outer request")
        return {"valid": False}
    blocks = _text_blocks(request.get("output"))
    block_index = match["block_index"]
    if not (type(block_index) is int and 0 <= block_index < len(blocks)):
        errors.append(f"{label}: exact match block index is invalid")
        return {"valid": False}
    block = blocks[block_index].encode("utf-8")
    start, end = match["start_byte"], match["end_byte"]
    emitted = block[start:end]
    try:
        parsed = json.loads(emitted)
    except (UnicodeError, json.JSONDecodeError) as exc:
        errors.append(f"{label}: exact match slice is invalid JSON: {exc}")
        return {"valid": False}
    valid = _json_equal(parsed, expected)
    require(valid, f"{label}: outer JSON value differs from native structuredContent", errors)
    return {
        "valid": valid,
        "output_ref": match["output_ref"],
        "outer_call_id": match["call_id"],
        "outer_output_line": match["output_line"],
        "block_index": block_index,
        "start_byte": start,
        "end_byte": end,
        "emitted_json_bytes": len(emitted),
        "emitted_json_sha256": sha256_bytes(emitted),
        "comparison": "exact parsed JSON value equality; integral numeric spelling may normalize",
    }


def main() -> None:
    errors: list[str] = []
    records, raw_lines = _read_rollout(ROLLOUT)
    require(len(records) >= END_LINE, "rollout ends before fixed capture boundary", errors)
    interval = [(line, records[line - 1]) for line in range(START_LINE, END_LINE + 1)]
    interval_raw = b"".join(raw_lines[START_LINE - 1 : END_LINE])
    first = interval[0][1]
    require(
        first.get("type") == "event_msg"
        and first.get("payload", {}).get("type") == "task_started"
        and first.get("payload", {}).get("turn_id") == TURN_ID,
        "fixed interval does not start at the selected task_started event",
        errors,
    )
    contexts = [
        {
            "line": line,
            "model": record["payload"].get("model"),
            "effort": record["payload"].get("effort"),
        }
        for line, record in interval
        if record.get("type") == "turn_context"
        and record.get("payload", {}).get("turn_id") == TURN_ID
    ]
    require(
        contexts == [{"line": 6313, "model": "gpt-6-astra", "effort": "ultra"}],
        "selected native model/effort context changed",
        errors,
    )
    boundaries = [
        {"line": line, "type": record.get("payload", {}).get("type")}
        for line, record in interval
        if record.get("type") == "event_msg"
        and record.get("payload", {}).get("type") in {"task_complete", "turn_aborted"}
        and record.get("payload", {}).get("turn_id") == TURN_ID
    ]
    require(not boundaries, "capture interval unexpectedly claims a completed turn", errors)

    metadata = {"thread_id": THREAD_ID, "turn_id": TURN_ID}
    all_mcp, _ = _collect_operations(interval, metadata)
    outer, outer_blocks = _collect_outer(interval)
    _correlate_delivery(all_mcp, outer_blocks)
    target_calls = [
        call
        for call in all_mcp
        if call["server"] == "loci"
        and call["tool"] in {"loci_retrieve", "loci_read"}
        and Path(str(call["arguments"].get("repo", ""))).resolve(strict=False)
        == TARGET_REPO
    ]
    require(len(target_calls) == 8, f"expected 8 target calls, found {len(target_calls)}", errors)
    labels = [classify(call) for call in target_calls]
    label_counts = Counter(labels)
    require(
        label_counts == Counter(RAW_FILES.keys()),
        f"target call inventory differs: {dict(label_counts)}",
        errors,
    )

    delivery_input = {
        "run": {"run_id": "repair-host-acceptance-20260915", **metadata},
        "retained_interval": {"sha256": sha256_bytes(interval_raw)},
        "mcp_calls": target_calls,
        "outer_code_mode": outer,
    }
    delivery = supplement_delivery(delivery_input)
    supplemental = {
        call["item_id"]: call for call in delivery["calls"]
    }
    outer_by_id = {item["call_id"]: item for item in outer}

    source_state = source_manifest(errors)
    restoration = json.loads(RESTORATION.read_text(encoding="utf-8"))
    restoration_valid = bool(
        restoration.get("passed") is True
        and restoration.get("actual_file_count") == 638
        and restoration.get("root") == str(TARGET_REPO)
        and restoration.get("manifest_sha256") == source_state["cases_sha256"]
        and restoration.get("expected_commit") == source_state["source_commit"]
    )
    require(restoration_valid, "source restoration receipt does not match capture identity", errors)

    signatures = Counter(
        sha256_bytes(compact([call["tool"], call["arguments"], call["result"]], sort_keys=True))
        for call in target_calls
    )
    call_receipts: list[dict[str, Any]] = []
    emitted_refs: dict[str, dict[str, Any]] = {}
    successful_snapshots: set[str] = set()

    for call, label in zip(target_calls, labels, strict=True):
        call_errors: list[str] = []
        result = call["result"]
        structured = result.get("structuredContent")
        is_error = application_error(result)
        raw_result = extract_native_result(raw_lines[call["line"] - 1].rstrip(b"\r\n"))
        parsed_raw_result = json.loads(raw_result)
        require(
            _json_equal(parsed_raw_result, result),
            f"{label}: extracted native envelope differs from parsed result",
            call_errors,
        )
        reported_output = (
            structured.get("usage", {}).get("output_bytes")
            if isinstance(structured, Mapping)
            else None
        )
        native_wire_matches_usage = (
            is_error or reported_output == len(raw_result)
        )
        require(
            native_wire_matches_usage,
            f"{label}: native envelope bytes differ from reported usage",
            call_errors,
        )

        delivery_call = supplemental[call["item_id"]]
        supplemental_delivery = delivery_call["supplemental_model_delivery"]
        expected_delivery = "unproven" if label == "missing_source" else "full_exact"
        require(
            supplemental_delivery["status"] == expected_delivery,
            f"{label}: delivery is {supplemental_delivery['status']}, expected {expected_delivery}",
            call_errors,
        )
        emitted_checks = [
            emitted_match_check(
                match,
                outer_by_id,
                structured,
                call_errors,
                label=label,
            )
            for match in supplemental_delivery["exact_matches"]
            if match["match"].startswith("structuredContent_")
        ]
        if label != "missing_source":
            require(
                bool(emitted_checks) and all(item["valid"] for item in emitted_checks),
                f"{label}: no exact model-visible structured value",
                call_errors,
            )

        raw_path = HERE / RAW_FILES[label]
        raw_copy = json.loads(raw_path.read_text(encoding="utf-8"))
        raw_copy_valid = bool(
            _json_equal(raw_copy.get("args"), call["arguments"])
            and _json_equal(raw_copy.get("result"), result)
        )
        require(raw_copy_valid, f"{label}: durable raw-call copy differs semantically", call_errors)
        raw_copy_result_bytes = len(compact(raw_copy.get("result")))

        source_checks: list[dict[str, Any]] = []
        relationship_check: dict[str, Any] | None = None
        locator_checks: list[dict[str, Any]] = []
        if not is_error and isinstance(structured, Mapping):
            if call["tool"] == "loci_retrieve":
                snapshot = structured.get("snapshot")
                if isinstance(snapshot, str):
                    successful_snapshots.add(snapshot)
                for index, source in enumerate(structured.get("sources", [])):
                    source_checks.append(
                        validate_source(source, call_errors, context=f"{label}.sources[{index}]")
                    )
                    if isinstance(source, Mapping) and isinstance(source.get("source_ref"), str):
                        emitted_refs[source["source_ref"]] = {
                            "producer": label,
                            "kind": "retrieve_source",
                            "native_line": call["line"],
                        }
                for index, item in enumerate(structured.get("items", [])):
                    if not isinstance(item, Mapping) or not isinstance(item.get("source_ref"), str):
                        continue
                    decoded = validate_ref(
                        item["source_ref"], call_errors, context=f"{label}.items[{index}].source_ref"
                    )
                    extent = item.get("extent")
                    valid = bool(
                        decoded is not None
                        and isinstance(extent, Mapping)
                        and decoded["file"] == extent.get("file")
                        and decoded["hash"] == extent.get("content_hash")
                        and decoded["start"] == extent.get("start_byte")
                        and decoded["offset"] == extent.get("start_byte")
                        and decoded["end"] == extent.get("end_byte")
                    )
                    require(valid, f"{label}.items[{index}]: locator differs from extent", call_errors)
                    locator_checks.append(
                        {
                            "node_id": item.get("node_id"),
                            "source_ref": item["source_ref"],
                            "decoded": decoded,
                            "valid": valid,
                        }
                    )
                    emitted_refs[item["source_ref"]] = {
                        "producer": label,
                        "kind": "retrieve_item",
                        "native_line": call["line"],
                    }
                relationship_check = validate_relationships(label, structured, call_errors)
            else:
                source_checks.append(validate_source(structured.get("source"), call_errors, context=label))

        readout = _retrieve_readout(call) if call["tool"] == "loci_retrieve" else _read_readout(call)
        _set_host_proof(readout, {"status": supplemental_delivery["status"]})
        signature = sha256_bytes(compact([call["tool"], call["arguments"], call["result"]], sort_keys=True))
        exact_repeat = signatures[signature] > 1
        require(not exact_repeat, f"{label}: exact repeated invocation/result is attribution-ambiguous", call_errors)

        call_receipts.append(
            {
                "label": label,
                "native_result_ref": f"native:{call['item_id']}:line:{call['line']}",
                "native_line": call["line"],
                "event_type": call["event_type"],
                "item_id": call["item_id"],
                "status": call["status"],
                "server": call["server"],
                "tool": call["tool"],
                "arguments": call["arguments"],
                "application_error": is_error,
                "result_status": structured.get("status") if isinstance(structured, Mapping) else None,
                "snapshot": structured.get("snapshot") if isinstance(structured, Mapping) else None,
                "omissions": structured.get("omissions") if isinstance(structured, Mapping) else None,
                "native_envelope": {
                    "jsonl_line": call["line"],
                    "wire_bytes": len(raw_result),
                    "wire_sha256": sha256_bytes(raw_result),
                    "reported_output_bytes": reported_output,
                    "wire_bytes_match_usage": native_wire_matches_usage,
                    "authority": "exact result JSON token in original native JSONL record",
                },
                "structured_value": {
                    "compact_json_bytes": len(compact(structured, sort_keys=True))
                    if isinstance(structured, Mapping)
                    else None,
                    "canonical_sha256": sha256_bytes(compact(structured, sort_keys=True))
                    if isinstance(structured, Mapping)
                    else None,
                },
                "original_model_delivery": call.get("model_delivery"),
                "supplemental_model_delivery": supplemental_delivery,
                "emitted_structured_value_checks": emitted_checks,
                "durable_raw_copy": {
                    "path": str(raw_path),
                    "file_sha256": sha256_bytes(raw_path.read_bytes()),
                    "semantic_args_and_result_equal": raw_copy_valid,
                    "reserialized_result_bytes": raw_copy_result_bytes,
                    "same_bytes_as_native_envelope": raw_copy_result_bytes == len(raw_result),
                    "wire_authority": False,
                },
                "source_checks": source_checks,
                "item_locator_checks": locator_checks,
                "relationship_check": relationship_check,
                "normal_helper_readout": readout,
                "exact_repeat": exact_repeat,
                "validation_errors": call_errors,
                "call_validation_passed": not call_errors,
            }
        )
        errors.extend(call_errors)

    require(len(successful_snapshots) == 1, "successful retrieves do not share one snapshot", errors)

    # Validate the exact two-page hydration chain after all retrieve/item locators are known.
    read_calls = [item for item in call_receipts if item["tool"] == "loci_read"]
    read_calls.sort(key=lambda item: item["native_line"])
    paging_errors: list[str] = []
    pages: list[dict[str, Any]] = []
    chain_origin: dict[str, Any] | None = None
    expected_incoming: str | None = None
    chain_content = bytearray()
    chain_extent: dict[str, Any] | None = None
    for index, receipt in enumerate(read_calls):
        original = next(call for call in target_calls if call["item_id"] == receipt["item_id"])
        incoming = original["arguments"]["source_ref"]
        decoded_incoming = validate_ref(incoming, paging_errors, context=f"paging[{index}].incoming")
        structured = original["result"].get("structuredContent", {})
        source = structured.get("source", {})
        if index == 0:
            chain_origin = emitted_refs.get(incoming)
            require(chain_origin is not None, "paging: first read ref was not emitted by a prior retrieve", paging_errors)
            chain_extent = decoded_incoming
        else:
            require(incoming == expected_incoming, "paging: next_source_ref was not followed exactly", paging_errors)
        if isinstance(decoded_incoming, Mapping) and isinstance(source, Mapping):
            require(
                decoded_incoming["file"] == source.get("file")
                and decoded_incoming["hash"] == source.get("content_hash")
                and decoded_incoming["offset"] == source.get("start_byte")
                and decoded_incoming["end"] >= source.get("end_byte", decoded_incoming["end"] + 1),
                f"paging[{index}]: returned page differs from incoming locator",
                paging_errors,
            )
        content = source.get("content")
        if isinstance(content, str):
            chain_content.extend(content.encode("utf-8"))
        next_ref = structured.get("next_source_ref")
        complete = structured.get("complete")
        if complete is False:
            decoded_next = validate_ref(next_ref, paging_errors, context=f"paging[{index}].next")
            require(
                decoded_incoming is not None
                and decoded_next is not None
                and {key: decoded_next[key] for key in ("v", "repo", "file", "hash", "start", "end")}
                == {key: decoded_incoming[key] for key in ("v", "repo", "file", "hash", "start", "end")}
                and decoded_next["offset"] == source.get("end_byte"),
                f"paging[{index}]: next locator is not the exact continuation",
                paging_errors,
            )
            expected_incoming = next_ref
            receipt["acceptance_proof_status"] = "partial_page_visible_no_complete_extent_proof"
        else:
            require(next_ref is None, f"paging[{index}]: complete page has a continuation", paging_errors)
            expected_incoming = None
            receipt["acceptance_proof_status"] = "complete_only_as_terminal_page_of_validated_chain"
        pages.append(
            {
                "label": receipt["label"],
                "native_line": receipt["native_line"],
                "incoming_source_ref": incoming,
                "decoded_incoming": decoded_incoming,
                "returned_start_byte": source.get("start_byte"),
                "returned_end_byte": source.get("end_byte"),
                "complete": complete,
                "next_source_ref": next_ref,
            }
        )
    chain_complete = bool(
        len(pages) == 2
        and pages[0]["complete"] is False
        and pages[1]["complete"] is True
        and expected_incoming is None
        and chain_extent is not None
    )
    if chain_complete and chain_extent is not None:
        raw = (TARGET_REPO / chain_extent["file"]).read_bytes()
        expected = raw[chain_extent["start"] : chain_extent["end"]]
        chain_complete = bytes(chain_content) == expected
    require(chain_complete, "paging: two pages do not exactly hydrate the complete extent", paging_errors)
    errors.extend(paging_errors)

    for receipt in call_receipts:
        if receipt["label"] == "missing_source":
            receipt["acceptance_proof_status"] = "preserved_error_no_proof"
        elif receipt["tool"] == "loci_retrieve":
            receipt["acceptance_proof_status"] = (
                "validated_call_and_expected_relationship_proof"
                if receipt["label"] in {"options", "explicit_pair", "browser", "renderer"}
                else "validated_locator_source_call"
            )

    matched_refs = {
        match["output_ref"]
        for receipt in call_receipts
        for match in receipt["supplemental_model_delivery"]["exact_matches"]
    }
    matched_outer_blocks = [
        block for block in delivery["outer_blocks"] if block["output_ref"] in matched_refs
    ]

    repaired_successes = [item for item in call_receipts if item["label"] != "missing_source"]
    inventory_pass = label_counts == Counter(RAW_FILES.keys())
    delivery_pass = all(
        item["supplemental_model_delivery"]["status"] == "full_exact"
        for item in repaired_successes
    )
    byte_pass = all(item["native_envelope"]["wire_bytes_match_usage"] for item in repaired_successes)
    source_pass = all(
        source["valid"]
        for item in repaired_successes
        for source in item["source_checks"]
    )
    proof_pass = all(
        item["relationship_check"] is not None and item["relationship_check"]["valid"]
        for item in repaired_successes
        if item["label"] in EXPECTED_EDGES
    )
    failure_preserved = bool(
        call_receipts
        and call_receipts[0]["label"] == "missing_source"
        and call_receipts[0]["application_error"]
        and call_receipts[0]["supplemental_model_delivery"]["status"] != "full_exact"
        and call_receipts[0]["acceptance_proof_status"] == "preserved_error_no_proof"
    )
    acceptance_pass = bool(
        inventory_pass
        and delivery_pass
        and byte_pass
        and source_pass
        and proof_pass
        and chain_complete
        and source_state["passed"]
        and restoration_valid
        and failure_preserved
        and not errors
    )

    capture = {
        "schema_version": 1,
        "kind": "repaired_actual_host_call_level_native_receipt",
        "rollout_path_local": str(ROLLOUT),
        "thread_id": THREAD_ID,
        "turn_id": TURN_ID,
        "native_contexts": contexts,
        "retained_interval": {
            "start_line": START_LINE,
            "end_line": END_LINE,
            "sha256": sha256_bytes(interval_raw),
            "boundary": "missing",
            "selection": "fixed original native prefix through the final selected outer emission",
        },
        "target_repo": str(TARGET_REPO),
        "source_identity_after_calls": source_state,
        "source_restoration_receipt": {
            "path": str(RESTORATION),
            "sha256": sha256_bytes(RESTORATION.read_bytes()),
            "matched": restoration_valid,
            "historical_archive": restoration.get("historical_archive"),
        },
        "selected_calls": call_receipts,
        "matched_outer_blocks": matched_outer_blocks,
        "paging_chain": {
            "origin": chain_origin,
            "extent": chain_extent,
            "pages": pages,
            "hydrated_bytes": len(chain_content),
            "complete_exact_hydration": chain_complete,
            "errors": paging_errors,
        },
        "excluded_native_operations": {
            "mcp_count": len(all_mcp) - len(target_calls),
            "payloads_retained": False,
        },
        "capture_errors": errors,
    }
    validation = {
        "schema_version": 1,
        "kind": "repaired_actual_host_acceptance_summary",
        "capture": str(CAPTURE_OUT),
        "capture_sha256": None,
        "checks": {
            "exact_call_inventory": inventory_pass,
            "seven_successful_calls_full_exact_model_visible": delivery_pass,
            "native_envelope_wire_bytes_match_reported_usage": byte_pass,
            "all_returned_source_hashes_spans_lines_and_locators_valid": source_pass,
            "all_expected_relationships_have_complete_linked_proof": proof_pass,
            "exact_two_page_binding_source_hydration": chain_complete,
            "fixed_source_still_matches_638_file_manifest": source_state["passed"],
            "restoration_identity_matches": restoration_valid,
            "initial_path_not_found_visible_without_proof": failure_preserved,
        },
        "call_outcomes": [
            {
                "label": item["label"],
                "native_line": item["native_line"],
                "item_id": item["item_id"],
                "result_status": item["result_status"],
                "model_delivery": item["supplemental_model_delivery"]["status"],
                "native_wire_bytes": item["native_envelope"]["wire_bytes"],
                "reported_output_bytes": item["native_envelope"]["reported_output_bytes"],
                "normal_helper_host_proof": item["normal_helper_readout"]["actual_host_proof_status"],
                "acceptance_proof_status": item["acceptance_proof_status"],
                "omissions": item["omissions"],
            }
            for item in call_receipts
        ],
        "acceptance_passed": acceptance_pass,
        "errors": errors,
        "limitations": [
            "The selected primary turn was still incomplete at the fixed capture boundary; no completed trial interval is fabricated.",
            "This is a directed call-level functional acceptance, not an ordinary provider trial, and it has no per-case provider-cost claim.",
            "The preserved pre-restoration PATH_NOT_FOUND response was reduced in model output and has no full_exact delivery or source proof.",
            "The first read page remains a visible incomplete page and gains no complete-extent proof by itself; proof comes only from the exact terminal chain.",
            "No exact repeated invocation/result occurred; any such repeat would remain attribution-ambiguous and would not gain acceptance proof.",
            "Saved raw-call JSON files are semantic duplicates, not wire authorities; native JSONL result-token bytes are authoritative. JSON numeric spelling can differ (for example 0.0 and 0).",
            "Historical source archive bytes remain unavailable; source identity is the frozen 638-file manifest restored from the recorded commit and rechecked after calls.",
            "The historical 5/8 strict-facts result and failed cost medians are unchanged; this receipt does not establish ordinary token savings or answer benefit.",
        ],
    }
    CAPTURE_OUT.write_text(json.dumps(capture, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    validation["capture_sha256"] = sha256_bytes(CAPTURE_OUT.read_bytes())
    VALIDATION_OUT.write_text(
        json.dumps(validation, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "acceptance_passed": acceptance_pass,
                "capture": str(CAPTURE_OUT),
                "validation": str(VALIDATION_OUT),
                "selected_calls": len(call_receipts),
                "errors": errors,
            },
            sort_keys=True,
        )
    )
    if not acceptance_pass:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
