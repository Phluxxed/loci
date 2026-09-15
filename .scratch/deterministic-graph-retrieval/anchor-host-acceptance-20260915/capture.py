#!/usr/bin/env python3
"""Verify one restarted-host normal Loci retrieval without reissuing it.

The original rollout JSONL is the wire authority.  This script retains only
bounded provenance, hashes, source locators, and validation results; it does
not copy unrelated native payloads or construct a completed provider trial.
"""
from __future__ import annotations

import hashlib
import importlib.util
from itertools import islice
import json
from pathlib import Path
import subprocess
import sys
from typing import Any, Mapping


HERE = Path(__file__).resolve().parent
WORKSPACE = HERE.parents[2]
sys.path.insert(0, str(WORKSPACE))

from benchmarks.ordinary_adoption_delivery_v3 import _json_equal, supplement_delivery
from benchmarks.ordinary_adoption_native_v2 import _collect_operations
from benchmarks.ordinary_adoption_observed import _collect_outer


ROLLOUT = Path(
    "/Users/brummerv/.codex/sessions/2026/09/14/"
    "rollout-2026-09-14T14-07-34-01a09e19-5048-79d3-96dd-697eda8a4ac8.jsonl"
)
THREAD_ID = "01a09e19-5048-79d3-96dd-697eda8a4ac8"
TURN_ID = "01a0a26d-b6f9-7fb1-8a1c-e74ed3f85119"
TURN_START_LINE = 7744
NATIVE_LINE = 7777
OUTER_REQUEST_LINE = 7775
OUTER_OUTPUT_LINE = 7778
QUERY = "captureCommandResult work context binding accepted type imported public contract"
ARG_REPO = "/tmp/anvil-source-tasks-20260914/t16"
TARGET_REPO = Path("/private/tmp/anvil-source-tasks-20260914/t16")
ITEM_ID = "exec-08b9574c-a485-4e4d-bb45-6ffab458fad8"
OUTER_CALL_ID = "call_dvtldIyAQ6FgptamwxiB8NiU"
EXPECTED_OUTPUT_BYTES = 16251
EXPECTED_EVIDENCE_BYTES = 3099
EXPECTED_WIRE_SHA256 = "bf4042f79b68a52ab7aac4cf962f3e692ebd06e3e8f92a81e91d642bfff71488"
PUBLISHED_COMMIT = "44d1074e20ef8c2e54ca92f48aa0229a4a0e4fb3"

RAW_CALL = HERE / "raw-call.json"
RECEIPT = HERE / "receipt.json"
CASES = WORKSPACE / "benchmarks/comparisons/ordinary-adoption-v1/cases.json"
REPAIR_DIR = HERE.parent / "repair-host-acceptance-20260915"
RESTORATION = REPAIR_DIR / "source-restoration-receipt.json"
DIAGNOSIS_DIR = HERE.parent / "diagnosis"
PUBLISHED_ENVELOPE = DIAGNOSIS_DIR / "anchor-identity-after-envelope.json"
REPLAY_RECEIPT = DIAGNOSIS_DIR / "anchor-identity-replay.json"
REPLAY_SCRIPT = DIAGNOSIS_DIR / "anchor-identity-replay.py"
REPLAY_REPORT = DIAGNOSIS_DIR / "anchor-identity-report.md"
PRIOR_CAPTURE = REPAIR_DIR / "capture-native-repaired.py"

FUNCTION = "src/tool-results/service.ts::captureCommandResult#function"
OPTIONS = "src/tool-results/service.ts::CaptureCommandResultOptions#type"
BINDING = "src/work-context/binding.ts::WorkContextBinding#type"
VIEW = "src/work-context/binding.ts::WorkContextBindingView#type"
REQUIRED_EDGES = {
    (FUNCTION, "uses_type", OPTIONS),
    (OPTIONS, "uses_type", BINDING),
}


def load_prior() -> Any:
    spec = importlib.util.spec_from_file_location("repair_capture_helpers", PRIOR_CAPTURE)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load helper module {PRIOR_CAPTURE}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.TARGET_REPO = TARGET_REPO
    module.CASES = CASES
    module.EXPECTED_EDGES["anchor"] = REQUIRED_EDGES
    return module


PRIOR = load_prior()


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def compact(value: Any, *, sort_keys: bool = False) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=sort_keys,
    ).encode("utf-8")


def require(condition: bool, message: str, errors: list[str]) -> bool:
    if not condition:
        errors.append(message)
    return condition


def raw_line_identity(raw: bytes, line: int) -> dict[str, Any]:
    record = raw.rstrip(b"\r\n")
    return {
        "line": line,
        "record_bytes": len(record),
        "record_sha256": sha256_bytes(record),
        "physical_line_bytes": len(raw),
        "physical_line_sha256": sha256_bytes(raw),
        "physical_hash_includes_line_terminator": True,
    }


def git_bytes(commit: str, relative: str) -> bytes:
    result = subprocess.run(
        ["git", "show", f"{commit}:{relative}"],
        cwd=WORKSPACE,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return result.stdout


def local_envelope_token(path: Path, errors: list[str], *, label: str) -> tuple[bytes, dict[str, Any]]:
    raw = path.read_bytes()
    require(raw.endswith(b"\n") and not raw.endswith(b"\n\n"), f"{label}: expected one final LF", errors)
    token = raw[:-1] if raw.endswith(b"\n") else raw
    try:
        parsed = json.loads(token)
    except (UnicodeError, json.JSONDecodeError) as exc:
        errors.append(f"{label}: invalid JSON: {exc}")
        parsed = None
    return token, {
        "path": str(path),
        "file_bytes": len(raw),
        "file_sha256": sha256_bytes(raw),
        "json_token_bytes": len(token),
        "json_token_sha256": sha256_bytes(token),
        "valid_json": parsed is not None,
    }


def edge_key(relationship: Mapping[str, Any]) -> tuple[str, str, str] | None:
    return PRIOR.edge_key(relationship)


def proof_role_checks(structured: Mapping[str, Any], errors: list[str]) -> dict[str, Any]:
    sources = {
        source.get("id"): source
        for source in structured.get("sources", [])
        if isinstance(source, Mapping) and type(source.get("id")) is int
    }
    relationships = {
        edge_key(relationship): relationship
        for relationship in structured.get("relationships", [])
        if isinstance(relationship, Mapping) and edge_key(relationship) is not None
    }
    path_one = relationships.get((FUNCTION, "uses_type", OPTIONS))
    path_two = relationships.get((OPTIONS, "uses_type", BINDING))

    role_specs = [
        ("function_signature", 5, "src/tool-results/service.ts", "captureCommandResult(options: CaptureCommandResultOptions)"),
        ("options_definition", 4, "src/tool-results/service.ts", "binding: WorkContextBinding"),
        ("type_import", 6, "src/tool-results/service.ts", 'import type { WorkContextBinding } from "../work-context/index.ts"'),
        ("public_barrel", 7, "src/work-context/index.ts", "WorkContextBindingView,"),
        ("binding_definition", 8, "src/work-context/binding.ts", "export type WorkContextBinding ="),
        ("package_module_config", 9, "package.json", '"type": "module"'),
        ("typescript_resolution_config", 10, "tsconfig.json", '"module": "nodenext"'),
    ]
    roles: list[dict[str, Any]] = []
    for role, source_id, file, needle in role_specs:
        source = sources.get(source_id)
        valid = bool(
            isinstance(source, Mapping)
            and source.get("file") == file
            and isinstance(source.get("content"), str)
            and needle in source["content"]
        )
        require(valid, f"proof role {role} is missing or malformed", errors)
        roles.append({"role": role, "source_id": source_id, "file": file, "valid": valid})

    first_ids = path_one.get("source_ids") if isinstance(path_one, Mapping) else None
    second_ids = path_two.get("source_ids") if isinstance(path_two, Mapping) else None
    first_valid = first_ids == [1, 5, 4]
    second_valid = second_ids == [4, 6, 7, 8, 9, 10]
    require(first_valid, "function-to-options proof source chain changed", errors)
    require(second_valid, "options-to-binding import/barrel/config proof chain changed", errors)
    return {
        "function_to_options": {
            "edge": {"from": FUNCTION, "type": "uses_type", "to": OPTIONS},
            "source_ids": first_ids,
            "expected_source_ids": [1, 5, 4],
            "valid": first_valid,
        },
        "options_to_binding": {
            "edge": {"from": OPTIONS, "type": "uses_type", "to": BINDING},
            "source_ids": second_ids,
            "expected_source_ids": [4, 6, 7, 8, 9, 10],
            "valid": second_valid,
        },
        "roles": roles,
        "complete_linked_type_import_barrel_config_proof": first_valid and second_valid and all(role["valid"] for role in roles),
    }


def item_locator_checks(structured: Mapping[str, Any], errors: list[str]) -> list[dict[str, Any]]:
    checks: list[dict[str, Any]] = []
    for index, item in enumerate(structured.get("items", [])):
        if not isinstance(item, Mapping):
            require(False, f"items[{index}] is not an object", errors)
            continue
        source_ref = item.get("source_ref")
        decoded = PRIOR.validate_ref(source_ref, errors, context=f"items[{index}].source_ref")
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
        require(valid, f"items[{index}] locator differs from extent", errors)
        checks.append(
            {
                "index": index,
                "node_id": item.get("node_id"),
                "role": item.get("role"),
                "source_ids": item.get("source_ids"),
                "source_ref": source_ref,
                "decoded": decoded,
                "valid": valid,
            }
        )
    return checks


def main() -> None:
    errors: list[str] = []
    with ROLLOUT.open("rb") as stream:
        raw_lines = list(islice(stream, OUTER_OUTPUT_LINE))
    records = [json.loads(line) for line in raw_lines]
    require(len(records) >= OUTER_OUTPUT_LINE, "rollout ends before fixed acceptance prefix", errors)
    interval = [(line, records[line - 1]) for line in range(TURN_START_LINE, OUTER_OUTPUT_LINE + 1)]
    interval_raw = b"".join(raw_lines[TURN_START_LINE - 1 : OUTER_OUTPUT_LINE])

    start = records[TURN_START_LINE - 1]
    require(
        start.get("type") == "event_msg"
        and start.get("payload", {}).get("type") == "task_started"
        and start.get("payload", {}).get("turn_id") == TURN_ID,
        "fixed interval does not start at the selected task_started event",
        errors,
    )
    contexts = [
        {"line": line, "model": record["payload"].get("model"), "effort": record["payload"].get("effort"), "cwd": record["payload"].get("cwd")}
        for line, record in interval
        if record.get("type") == "turn_context" and record.get("payload", {}).get("turn_id") == TURN_ID
    ]
    require(
        contexts == [{"line": 7746, "model": "gpt-6-astra", "effort": "ultra", "cwd": "/Users/brummerv/loci"}],
        "selected native model/effort/cwd context changed",
        errors,
    )
    boundaries = [
        {"line": line, "type": record.get("payload", {}).get("type")}
        for line, record in interval
        if record.get("type") == "event_msg"
        and record.get("payload", {}).get("type") in {"task_complete", "turn_aborted"}
        and record.get("payload", {}).get("turn_id") == TURN_ID
    ]
    require(not boundaries, "fixed acceptance prefix unexpectedly has a terminal turn boundary", errors)

    metadata = {"thread_id": THREAD_ID, "turn_id": TURN_ID}
    mcp, _ = _collect_operations(interval, metadata)
    outer, _ = _collect_outer(interval)
    calls = [
        call
        for call in mcp
        if call["server"] == "loci"
        and call["tool"] == "loci_retrieve"
        and call["arguments"] == {"repo": ARG_REPO, "query": QUERY}
    ]
    require(len(calls) == 1, f"expected one exact target call, found {len(calls)}", errors)
    call = calls[0] if calls else {}
    require(call.get("line") == NATIVE_LINE and call.get("item_id") == ITEM_ID, "native call identity changed", errors)
    result = call.get("result") if isinstance(call.get("result"), Mapping) else {}
    structured = result.get("structuredContent") if isinstance(result.get("structuredContent"), Mapping) else {}
    require(result.get("isError") is False and result.get("content") == [] and bool(structured), "native result is not a successful structured normal envelope", errors)

    prefix_exact: list[dict[str, Any]] = []
    prefix_same_query: list[dict[str, Any]] = []
    for line, record in enumerate(records[:OUTER_OUTPUT_LINE], 1):
        if record.get("type") != "event_msg":
            continue
        payload = record.get("payload")
        item = payload.get("item") if isinstance(payload, Mapping) else None
        if not isinstance(item, Mapping) or item.get("type") != "McpToolCall":
            continue
        arguments = item.get("arguments")
        if not isinstance(arguments, Mapping) or arguments.get("query") != QUERY:
            continue
        summary = {
            "line": line,
            "timestamp": record.get("timestamp"),
            "turn_id": payload.get("turn_id"),
            "item_id": item.get("id"),
            "server": item.get("server"),
            "tool": item.get("tool"),
            "repo": arguments.get("repo"),
            "status": item.get("status"),
        }
        prefix_same_query.append(summary)
        if item.get("server") == "loci" and item.get("tool") == "loci_retrieve" and dict(arguments) == {"repo": ARG_REPO, "query": QUERY}:
            prefix_exact.append(summary)
    require(prefix_exact == [{
        "line": NATIVE_LINE,
        "timestamp": "2026-09-15T00:19:16.448Z",
        "turn_id": TURN_ID,
        "item_id": ITEM_ID,
        "server": "loci",
        "tool": "loci_retrieve",
        "repo": ARG_REPO,
        "status": "completed",
    }], "fixed-prefix exact native call inventory changed", errors)
    require(prefix_same_query == prefix_exact, "another native call used the retained query", errors)

    native_token = PRIOR.extract_native_result(raw_lines[NATIVE_LINE - 1].rstrip(b"\r\n"))
    require(_json_equal(json.loads(native_token), result), "native result token differs from parsed result", errors)
    require(len(native_token) == EXPECTED_OUTPUT_BYTES, "native result token byte count changed", errors)
    require(sha256_bytes(native_token) == EXPECTED_WIRE_SHA256, "native result token hash changed", errors)
    usage = structured.get("usage", {})
    require(usage.get("output_bytes") == len(native_token) == EXPECTED_OUTPUT_BYTES, "reported output bytes differ from native token", errors)
    require(usage.get("evidence_bytes") == EXPECTED_EVIDENCE_BYTES, "reported evidence bytes changed", errors)

    local_token, local_identity = local_envelope_token(RAW_CALL, errors, label="raw-call")
    published_token, published_identity = local_envelope_token(PUBLISHED_ENVELOPE, errors, label="published-envelope")
    require(local_token == native_token, "saved raw-call bytes differ from native result token", errors)
    require(published_token == native_token, "published diagnosis envelope differs from native result token", errors)

    published_relative = PUBLISHED_ENVELOPE.relative_to(WORKSPACE).as_posix()
    committed_blob = git_bytes(PUBLISHED_COMMIT, published_relative)
    require(committed_blob == PUBLISHED_ENVELOPE.read_bytes(), "published commit envelope blob differs from working copy", errors)

    outer_requests = [entry for entry in outer if entry.get("call_id") == OUTER_CALL_ID]
    require(len(outer_requests) == 1, f"expected one outer exec request, found {len(outer_requests)}", errors)
    outer_request = outer_requests[0] if outer_requests else {}
    require(
        outer_request.get("request_line") == OUTER_REQUEST_LINE and outer_request.get("output_line") == OUTER_OUTPUT_LINE,
        "outer request/output line identity changed",
        errors,
    )
    outer_request_body = outer_request.get("request")
    request_bytes = outer_request_body.encode("utf-8") if isinstance(outer_request_body, str) else compact(outer_request_body)
    requested_full_emit_once = isinstance(outer_request_body, str) and outer_request_body.count("text(r)") == 1
    requested_store = isinstance(outer_request_body, str) and "store(" in outer_request_body
    require(requested_full_emit_once and requested_store, "outer request no longer stores and emits the result exactly once", errors)
    delivery = supplement_delivery(
        {
            "run": {"run_id": "anchor-host-acceptance-20260915", **metadata},
            "retained_interval": {"sha256": sha256_bytes(interval_raw)},
            "mcp_calls": calls,
            "outer_code_mode": outer,
        }
    )
    delivery_call = delivery["calls"][0] if delivery.get("calls") else {}
    delivery_proof = delivery_call.get("supplemental_model_delivery", {})
    exact_matches = delivery_proof.get("exact_matches", [])
    require(delivery_proof.get("status") == "full_exact", "model delivery is not full_exact", errors)
    require(len(exact_matches) == 1, f"expected one exact model-visible match, found {len(exact_matches)}", errors)
    exact = exact_matches[0] if exact_matches else {}
    require(
        exact.get("call_id") == OUTER_CALL_ID
        and exact.get("output_line") == OUTER_OUTPUT_LINE
        and exact.get("block_index") == 1
        and exact.get("start_byte") == 0
        and exact.get("end_byte") == EXPECTED_OUTPUT_BYTES
        and exact.get("match") in {"result_json_line", "result_json_block"},
        "exact model-visible match identity or extent changed",
        errors,
    )
    output_blocks = PRIOR._text_blocks(outer_request.get("output"))
    emitted = output_blocks[1].encode("utf-8") if len(output_blocks) > 1 else b""
    require(emitted == native_token, "model-visible block bytes differ from native result token", errors)

    expected_anchors = [FUNCTION, BINDING, VIEW]
    actual_anchors = [anchor.get("node_id") for anchor in structured.get("anchors", []) if isinstance(anchor, Mapping)]
    require(actual_anchors == expected_anchors, "repaired anchor identities changed", errors)
    require(structured.get("status") == "partial", "result status changed", errors)
    require(usage.get("relationships_delivered") == 3, "relationship count changed", errors)

    source_checks = [
        PRIOR.validate_source(source, errors, context=f"sources[{index}]")
        for index, source in enumerate(structured.get("sources", []))
    ]
    require(len(source_checks) == 10, f"expected 10 proof sources, found {len(source_checks)}", errors)
    locator_checks = item_locator_checks(structured, errors)
    relationship_check = PRIOR.validate_relationships("anchor", structured, errors)
    proof_roles = proof_role_checks(structured, errors)

    source_state = PRIOR.source_manifest(errors)
    cases = json.loads(CASES.read_text(encoding="utf-8"))
    replay = json.loads(REPLAY_RECEIPT.read_text(encoding="utf-8"))
    require(replay.get("query") == QUERY, "replay receipt query changed", errors)
    require(replay.get("after_anchors") == expected_anchors, "replay receipt repaired anchors changed", errors)
    require(replay.get("required_path")[:2] == [
        {"from": FUNCTION, "type": "uses_type", "to": OPTIONS, "resolution": "exact", "proof": "complete"},
        {"from": OPTIONS, "type": "uses_type", "to": BINDING, "resolution": "import-resolved", "proof": "complete", "source_ids": [4, 6, 7, 8, 9, 10]},
    ], "replay receipt required path changed", errors)
    require(replay.get("canonical_envelope_bytes") == EXPECTED_OUTPUT_BYTES, "replay envelope bytes changed", errors)
    require(replay.get("canonical_envelope_sha256") == EXPECTED_WIRE_SHA256, "replay envelope hash changed", errors)
    require(replay.get("source_files_verified") == 638 and replay.get("source_hash_mismatches") == 0, "replay source identity changed", errors)

    restoration = json.loads(RESTORATION.read_text(encoding="utf-8"))
    restoration_lineage_valid = bool(
        restoration.get("passed") is True
        and restoration.get("expected_commit") == cases.get("source_commit")
        and restoration.get("expected_file_count") == 638
        and restoration.get("actual_file_count") == 638
        and not restoration.get("missing")
        and not restoration.get("extra")
        and not restoration.get("mismatched")
        and not restoration.get("unsupported_entries")
        and restoration.get("manifest_sha256") == sha256_bytes(CASES.read_bytes())
    )
    require(restoration_lineage_valid, "source restoration lineage receipt changed", errors)

    checks = {
        "one_exact_restarted_host_call": len(calls) == 1 and call.get("item_id") == ITEM_ID,
        "fixed_prefix_has_no_competing_native_query_call": prefix_same_query == prefix_exact and len(prefix_exact) == 1,
        "successful_structured_normal_envelope": result.get("isError") is False and result.get("content") == [] and bool(structured),
        "native_result_token_matches_reported_16251_bytes": len(native_token) == usage.get("output_bytes") == EXPECTED_OUTPUT_BYTES,
        "native_result_token_hash_matches_published_replay": sha256_bytes(native_token) == EXPECTED_WIRE_SHA256,
        "saved_raw_call_byte_equal_to_native_token": local_token == native_token,
        "published_commit_envelope_byte_equal_to_native_token": published_token == native_token and committed_blob == PUBLISHED_ENVELOPE.read_bytes(),
        "unique_full_model_visible_output": delivery_proof.get("status") == "full_exact" and len(exact_matches) == 1 and emitted == native_token,
        "repaired_function_binding_view_anchors": actual_anchors == expected_anchors,
        "expected_partial_16251_3099_usage": structured.get("status") == "partial" and usage.get("output_bytes") == 16251 and usage.get("evidence_bytes") == 3099,
        "all_source_hashes_spans_lines_and_refs_valid": len(source_checks) == 10 and all(check.get("valid") for check in source_checks),
        "all_item_locators_match_extents": len(locator_checks) == len(structured.get("items", [])) and all(check.get("valid") for check in locator_checks),
        "all_relationships_complete_and_linked": relationship_check.get("valid") is True,
        "complete_type_import_barrel_config_proof": proof_roles["complete_linked_type_import_barrel_config_proof"],
        "frozen_638_file_source_identity_no_extras": source_state.get("passed") is True and source_state.get("actual_file_count") == 638 and not source_state.get("extra"),
        "restoration_lineage_matches_manifest_and_commit": restoration_lineage_valid,
        "fixed_interval_is_open_prefix": not boundaries,
    }
    acceptance_passed = all(checks.values()) and not errors

    receipt = {
        "schema_version": 1,
        "kind": "restarted_host_single_normal_retrieval_acceptance",
        "acceptance_passed": acceptance_passed,
        "reproduce": ".venv/bin/python .scratch/deterministic-graph-retrieval/anchor-host-acceptance-20260915/capture.py",
        "scope": {
            "query": QUERY,
            "argument_repo": ARG_REPO,
            "canonical_repo": str(TARGET_REPO),
            "normal_tool": "mcp__loci__loci_retrieve",
            "native_server_tool": "loci/loci_retrieve",
            "provider_trial": False,
            "loci_reissued_by_capture": False,
        },
        "native_provenance": {
            "rollout_path_local": str(ROLLOUT),
            "thread_id": THREAD_ID,
            "turn_id": TURN_ID,
            "contexts": contexts,
            "retained_interval": {
                "start_line": TURN_START_LINE,
                "end_line": OUTER_OUTPUT_LINE,
                "record_count": OUTER_OUTPUT_LINE - TURN_START_LINE + 1,
                "sha256": sha256_bytes(interval_raw),
                "boundary": "missing_at_selected_end",
                "selection": "task_started through the exact outer output for the selected call",
                "qualification": "open turn prefix, not a completed trial interval",
                "terminal_boundaries": boundaries,
            },
            "native_item": {
                "item_id": ITEM_ID,
                "event_type": call.get("event_type"),
                "status": call.get("status"),
                "line_identity": raw_line_identity(raw_lines[NATIVE_LINE - 1], NATIVE_LINE),
                "started_at_ms": call.get("started_at_ms"),
                "completed_at_ms": call.get("completed_at_ms"),
            },
            "fixed_prefix_native_query_inventory": {
                "fixed_prefix_record_count": len(records),
                "exact_server_tool_arguments_matches": prefix_exact,
                "same_query_native_matches": prefix_same_query,
                "raw_payloads_retained": False,
                "qualification": "native terminal MCP items only; textual mentions and local/service replays are excluded",
            },
            "native_result_token": {
                "bytes": len(native_token),
                "sha256": sha256_bytes(native_token),
                "reported_output_bytes": usage.get("output_bytes"),
                "authority": "exact result JSON token in the original native JSONL item",
            },
            "outer_output": {
                "call_id": OUTER_CALL_ID,
                "request_line_identity": raw_line_identity(raw_lines[OUTER_REQUEST_LINE - 1], OUTER_REQUEST_LINE),
                "request_bytes": len(request_bytes),
                "request_sha256": sha256_bytes(request_bytes),
                "request_stores_result": requested_store,
                "request_emits_text_r_once": requested_full_emit_once,
                "output_line_identity": raw_line_identity(raw_lines[OUTER_OUTPUT_LINE - 1], OUTER_OUTPUT_LINE),
                "matched_output_ref": exact.get("output_ref"),
                "block_index": exact.get("block_index"),
                "block_bytes": len(emitted),
                "block_sha256": sha256_bytes(emitted),
                "byte_equal_to_native_result_token": emitted == native_token,
                "supplemental_delivery": delivery_proof,
            },
        },
        "envelope_identity": {
            "saved_raw_call": {**local_identity, "byte_equal_to_native_result_token": local_token == native_token},
            "published_diagnosis": {**published_identity, "byte_equal_to_native_result_token": published_token == native_token},
            "published_commit": {
                "commit": PUBLISHED_COMMIT,
                "path": published_relative,
                "blob_bytes": len(committed_blob),
                "blob_sha256": sha256_bytes(committed_blob),
                "byte_equal_to_working_copy": committed_blob == PUBLISHED_ENVELOPE.read_bytes(),
            },
        },
        "semantic_result": {
            "status": structured.get("status"),
            "snapshot": structured.get("snapshot"),
            "anchors": actual_anchors,
            "usage": usage,
            "omissions": structured.get("omissions"),
            "nodes": [
                {key: node.get(key) for key in ("id", "kind", "name", "file")}
                for node in structured.get("nodes", [])
                if isinstance(node, Mapping)
            ],
            "source_checks": source_checks,
            "item_locator_checks": locator_checks,
            "relationship_check": relationship_check,
            "proof_roles": proof_roles,
        },
        "frozen_source_identity": source_state,
        "diagnosis_lineage": {
            "replay_receipt": {
                "path": str(REPLAY_RECEIPT),
                "sha256": sha256_bytes(REPLAY_RECEIPT.read_bytes()),
                "query": replay.get("query"),
                "after_anchors": replay.get("after_anchors"),
                "required_path": replay.get("required_path"),
                "canonical_envelope_bytes": replay.get("canonical_envelope_bytes"),
                "canonical_envelope_sha256": replay.get("canonical_envelope_sha256"),
                "source_files_verified": replay.get("source_files_verified"),
                "source_hash_mismatches": replay.get("source_hash_mismatches"),
            },
            "replay_script": {"path": str(REPLAY_SCRIPT), "sha256": sha256_bytes(REPLAY_SCRIPT.read_bytes()), "executed_for_this_acceptance": False},
            "report": {"path": str(REPLAY_REPORT), "sha256": sha256_bytes(REPLAY_REPORT.read_bytes())},
            "source_restoration_receipt": {
                "path": str(RESTORATION),
                "sha256": sha256_bytes(RESTORATION.read_bytes()),
                "root": restoration.get("root"),
                "different_root_lineage_only": restoration.get("root") != str(TARGET_REPO),
                "manifest_and_commit_match": restoration_lineage_valid,
            },
        },
        "checks": checks,
        "errors": errors,
        "limitations": [
            "The fixed native interval is an open primary-turn prefix ending at the exact outer output; it is not a completed provider trial.",
            "This receipt verifies one directed restarted-host normal retrieval and makes no provider-cost or ordinary-adoption claim.",
            "The local replay script is hashed for lineage but was not executed; this acceptance issues no new Loci call.",
            "The restoration receipt is for t23 and is used only as same-manifest/same-commit lineage; t16 is independently rechecked against all 638 frozen file hashes with no extras.",
            "The result remains partial and non-exhaustive with its reported omissions; acceptance is for the required anchors and complete linked proof delivered within that envelope.",
        ],
    }
    RECEIPT.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"acceptance_passed": acceptance_passed, "receipt": str(RECEIPT), "receipt_sha256": sha256_bytes(RECEIPT.read_bytes()), "errors": errors}, sort_keys=True))
    if not acceptance_passed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
