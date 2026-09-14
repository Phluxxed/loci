"""Collect one frozen normal-adoption rollout without mutating shared inputs."""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parent
REPO = ROOT.parents[2]
sys.path.insert(0, str(REPO))

from benchmarks.ordinary_adoption_normal import observe_normal_rollout  # noqa: E402


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _strings(value: Any, locator: str = "$") -> Iterable[tuple[str, str]]:
    if isinstance(value, str):
        yield locator, value
    elif isinstance(value, list):
        for index, item in enumerate(value):
            yield from _strings(item, f"{locator}[{index}]")
    elif isinstance(value, dict):
        for key, item in value.items():
            yield from _strings(item, f"{locator}.{key}")


def _message_text(payload: dict[str, Any]) -> str:
    content = payload.get("content")
    if not isinstance(content, list):
        return content if isinstance(content, str) else ""
    return "".join(
        item.get("text", "")
        for item in content
        if isinstance(item, dict) and isinstance(item.get("text"), str)
    )


def _iso_deadline(timestamp: str, seconds: int) -> str:
    started = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    return (started + timedelta(seconds=seconds)).astimezone(timezone.utc).isoformat()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--rollout", required=True, type=Path)
    parser.add_argument("--thread-id", required=True)
    parser.add_argument("--turn-id", required=True)
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args()

    freeze_path = ROOT / "freeze.json"
    schedule_path = ROOT / "schedule.json"
    source_copies_path = ROOT / "runtime/source-copies.json"
    freeze = _json(freeze_path)
    schedule = _json(schedule_path)
    source_copies = _json(source_copies_path)
    row = next((item for item in schedule["rows"] if item["run_id"] == args.run_id), None)
    source_copy = next((item for item in source_copies["rows"] if item["run_id"] == args.run_id), None)
    if row is None or source_copy is None:
        raise SystemExit(f"unknown frozen run: {args.run_id}")
    if _sha256(row["prompt"].encode("utf-8")) != row["prompt_sha256"]:
        raise SystemExit("scheduled prompt digest mismatch")

    raw = args.rollout.read_bytes()
    raw_lines = raw.splitlines(keepends=True)
    records = [json.loads(line) for line in raw_lines]
    session = records[0].get("payload", {})
    if session.get("id") != args.thread_id:
        raise SystemExit("rollout session id differs from --thread-id")
    starts = [
        record
        for record in records
        if record.get("type") == "event_msg"
        and record.get("payload", {}).get("type") == "task_started"
        and record.get("payload", {}).get("turn_id") == args.turn_id
    ]
    if len(starts) != 1:
        raise SystemExit("selected turn does not have exactly one task_started record")

    observer_metadata = {
        "run_id": row["run_id"],
        "purpose": row["purpose"],
        "thread_id": args.thread_id,
        "turn_id": args.turn_id,
        "target_repo": row["source_root"],
        "requested_model": row["model"],
        "requested_effort": row["effort"],
        "case_id": row["case_id"],
        "condition": row["condition"],
        "repetition": row["repetition"],
        "role": row["role"],
        "prompt_sha256": row["prompt_sha256"],
        "source_canonical_root": source_copy["canonical_root"],
        "task_source_commit": row["task_source_commit"],
        "task_source_archive_sha256": row["task_source_archive_sha256"],
        "agent_task_name": row["agent_task_name"],
    }
    first = observe_normal_rollout(args.rollout, observer_metadata)
    interval = first["observation"]["retained_interval"]
    observer_metadata["expected_interval_sha256"] = interval["sha256"]
    observed = observe_normal_rollout(args.rollout, observer_metadata)
    if observed["observation"]["retained_interval"] != interval:
        raise SystemExit("replayed interval changed")

    start, end = interval["start_line"], interval["end_line"]
    retained = b"".join(raw_lines[start - 1 : end])
    if _sha256(retained) != interval["sha256"]:
        raise SystemExit("retained interval bytes differ from adapter digest")

    prompt_hits: list[dict[str, Any]] = []
    user_messages: list[dict[str, Any]] = []
    for line_number, record in enumerate(records, 1):
        for locator, text in _strings(record):
            if text == row["prompt"]:
                prompt_hits.append({"line": line_number, "locator": locator, "match": "exact_string"})
            elif row["prompt"] in text:
                prompt_hits.append({"line": line_number, "locator": locator, "match": "exact_substring"})
        payload = record.get("payload")
        if (
            start <= line_number <= end
            and record.get("type") == "response_item"
            and isinstance(payload, dict)
            and payload.get("type") == "message"
            and payload.get("role") == "user"
        ):
            text = _message_text(payload)
            user_messages.append(
                {
                    "line": line_number,
                    "message_id": payload.get("id"),
                    "bytes": len(text.encode("utf-8")),
                    "sha256": _sha256(text.encode("utf-8")),
                    "equals_scheduled_prompt": text == row["prompt"],
                }
            )

    observation = observed["observation"]
    final = observation["outcome"]["final_answer"]
    output_dir = args.output_dir or ROOT / "runs" / args.run_id
    output_dir.mkdir(parents=True, exist_ok=False)
    (output_dir / "retained-native-interval.jsonl").write_bytes(retained)
    _write_json(output_dir / "observation.json", observed)
    answer_receipt: dict[str, Any] = {"status": "missing"}
    if final.get("status") == "present":
        blocks = final.get("content")
        if not isinstance(blocks, list) or any(
            not isinstance(block, dict)
            or block.get("type") != "Text"
            or not isinstance(block.get("text"), str)
            for block in blocks
        ):
            raise SystemExit("final answer contains a non-Text or malformed block")
        answer_bytes = "".join(block["text"] for block in blocks).encode("utf-8")
        (output_dir / "finalanswer.md").write_bytes(answer_bytes)
        answer_receipt = {
            "status": "present",
            "file": "finalanswer.md",
            "bytes": len(answer_bytes),
            "sha256": _sha256(answer_bytes),
            "native_content_bytes": final["bytes"],
            "native_content_sha256": final["sha256"],
        }

    normal_cost = observed["normal_cost"]
    total_operations = observation["cost"]["terminal_mcp_invocations"] + observation["cost"]["terminal_shell_commands"]
    duration_ms = observation["outcome"].get("duration_ms")
    visible_bytes = observation["cost"]["model_visible_outer_output_bytes"]
    provider = observation["provider_usage"]
    metadata = {
        "schema_version": 1,
        "observer_metadata": observer_metadata,
        "schedule": {
            "path": str(schedule_path),
            "sha256": _sha256(schedule_path.read_bytes()),
            "status": "frozen",
            "row": row,
        },
        "source_preflight": {
            "receipt_path": str(source_copies_path),
            "receipt_sha256": _sha256(source_copies_path.read_bytes()),
            "recorded_before_post_outcomes": True,
            "archive_bytes_available": source_copies["archive_bytes_available"],
            "verification": source_copies["verification"],
            "files_verified": source_copy["files_verified"],
            "no_extra_files_verified": "no extra files" in source_copies["verification"],
        },
        "native": {
            "rollout_path": str(args.rollout),
            "whole_file_bytes": len(raw),
            "whole_file_sha256": _sha256(raw),
            "interval_start_line": start,
            "interval_end_line": end,
            "interval_bytes": len(retained),
            "interval_sha256": interval["sha256"],
            "parent_thread_id": session.get("parent_thread_id"),
        },
        "answer": answer_receipt,
        "prompt_capture": {
            "scheduled_prompt_bytes": len(row["prompt"].encode("utf-8")),
            "scheduled_prompt_sha256": row["prompt_sha256"],
            "exact_plaintext_hits": prompt_hits,
            "selected_interval_plaintext_user_messages": user_messages,
            "status": "exact_plaintext_present" if prompt_hits else "scheduled_assignment_not_plaintext_in_native_rollout",
            "qualification": (
                "The scheduled assignment is supplied by the native subagent spawn envelope, which records identity but not task text; "
                "the retained plaintext user message is the inherited host envelope and is hashed separately."
                if not prompt_hits
                else None
            ),
        },
        "capture_validation": {
            "status": "condition_valid" if not observation["native_identity"]["condition_deviations"] else "condition_deviation",
            "observed_model": observation["native_identity"]["observed_model"],
            "observed_effort": observation["native_identity"]["observed_effort"],
            "condition_deviations": observation["native_identity"]["condition_deviations"],
            "first_turn_within_wall_cap": isinstance(duration_ms, (int, float)) and duration_ms <= freeze["execution"]["wall_cap_ms"],
            "duration_ms": duration_ms,
            "operation_count": total_operations,
            "operation_flag": freeze["execution"]["operation_flag"],
            "operation_flag_pass": total_operations <= freeze["execution"]["operation_flag"],
            "model_visible_output_bytes": visible_bytes,
            "visible_output_flag_bytes": freeze["execution"]["visible_output_flag_bytes"],
            "visible_output_flag_pass": visible_bytes <= freeze["execution"]["visible_output_flag_bytes"],
            "provider_input_tokens": provider.get("usage", {}).get("input_tokens") if provider.get("status") == "available" else None,
            "normal_structural_proof": {
                "validated_call_count": sum(call["actual_host_proof_status"] == "validated" for call in observed["normal_calls"]),
                "normal_cost": normal_cost,
                "legacy_complete_for_graph_use_claim": observation["integrity"]["complete_for_graph_use_claim"],
            },
        },
    }
    _write_json(output_dir / "metadata.json", metadata)

    access_review = {
        "schema_version": 1,
        "run_id": row["run_id"],
        "target_repo": row["source_root"],
        "source_canonical_root": source_copy["canonical_root"],
        "status": "pending_semantic_review",
        "scope_rule": "Task-source and installed operating-instruction access only; cwd alone is not evidence of scope.",
        "mcp_records": [
            {
                "line": call["line"],
                "item_id": call["item_id"],
                "server": call["server"],
                "tool": call["tool"],
                "arguments": call["arguments"],
                "status": call["status"],
                "result_is_error": call["result"].get("isError") is True,
            }
            for call in observation["mcp_calls"]
        ],
        "shell_records": [
            {
                "line": call["line"],
                "item_id": call["item_id"],
                "command": call["command"],
                "cwd": call["cwd"],
                "category": call["invocation_category"],
                "graph_activity": call["graph_activity"],
                "status": call["status"],
                "exit_code": call["exit_code"],
            }
            for call in observation["shell_calls"]
        ],
        "qualification": "Opaque shell activity remains unknown until command text and referenced paths are reviewed.",
    }
    _write_json(output_dir / "access-review.json", access_review)
    print(
        json.dumps(
            {
                "run_id": row["run_id"],
                "output_dir": str(output_dir),
                "duration_ms": duration_ms,
                "model_visible_output_bytes": visible_bytes,
                "provider_input_tokens": metadata["capture_validation"]["provider_input_tokens"],
                "normal_public_invocations": normal_cost["public_invocations"],
                "validated_normal_calls": metadata["capture_validation"]["normal_structural_proof"]["validated_call_count"],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
