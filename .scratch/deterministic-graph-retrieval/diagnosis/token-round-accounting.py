#!/usr/bin/env python3
"""Build compact per-provider-round accounting for eight retained adoption runs.

The retained native intervals are read locally. Published outputs deliberately
contain counters, operation identities, byte counts, and hashes rather than raw
messages, commands, source, or tool-result bodies.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from hashlib import sha256
import json
from pathlib import Path
from statistics import median
from typing import Any


ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
SCHEDULE_PATH = HERE / "token-schedule.json"
RESULTS_PATH = HERE / "token-results.json"
LINKAGE_PATH = HERE / "token-baseline-linkage.json"
METADATA_PATH = HERE / "token-metadata.json"
USAGE_FIELDS = (
    "input_tokens",
    "cached_input_tokens",
    "cache_write_input_tokens",
    "output_tokens",
    "reasoning_output_tokens",
    "total_tokens",
)


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def compact(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")


def digest_bytes(value: bytes) -> str:
    return sha256(value).hexdigest()


def file_receipt(path: Path) -> dict[str, Any]:
    data = path.read_bytes()
    return {"path": str(path.relative_to(ROOT)), "bytes": len(data), "sha256": digest_bytes(data)}


def write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def output_texts(raw: Any) -> list[str]:
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
    return [compact(raw).decode("utf-8")]


def usage_delta(current: dict[str, Any], previous: dict[str, Any]) -> dict[str, int]:
    return {field: int(current.get(field, 0)) - int(previous.get(field, 0)) for field in USAGE_FIELDS}


def usage_equal(left: dict[str, Any], right: dict[str, Any]) -> bool:
    return all(int(left.get(field, 0)) == int(right.get(field, 0)) for field in USAGE_FIELDS)


def ratio(numerator: float, denominator: float) -> float | None:
    return round(numerator / denominator, 6) if denominator else None


def percent(numerator: float, denominator: float) -> float | None:
    return round((numerator / denominator - 1) * 100, 4) if denominator else None


def normalized_number(value: float) -> int | float:
    return int(value) if float(value).is_integer() else value


def unwrap_observation(value: dict[str, Any]) -> dict[str, Any]:
    observation = value.get("observation")
    return observation if isinstance(observation, dict) else value


def frozen_rows(schedule: dict[str, Any]) -> dict[tuple[str, str], dict[str, Any]]:
    baseline = read_json(ROOT / schedule["frozen_sources"]["baseline_results"])
    post = read_json(ROOT / schedule["frozen_sources"]["post_results"])
    rows: dict[tuple[str, str], dict[str, Any]] = {}
    for row in baseline["rows"]:
        rows[("baseline", row["run_id"])] = row
    for row in post["ordinary_rows"]:
        rows[("post", row["run_id"])] = row
    return rows


def operation_maps(observation: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    return (
        {item["item_id"]: item for item in observation.get("mcp_calls", [])},
        {item["item_id"]: item for item in observation.get("shell_calls", [])},
    )


def mcp_summary(item: dict[str, Any], local_line: int, original_line: int, observed: dict[str, Any] | None) -> dict[str, Any]:
    result = item.get("result")
    result = result if isinstance(result, dict) else {}
    result_bytes = compact(result)
    arguments = item.get("arguments")
    arguments = arguments if isinstance(arguments, dict) else {}
    structured = result.get("structuredContent")
    structured = structured if isinstance(structured, dict) else {}
    reported_usage = structured.get("usage")
    reported_usage = reported_usage if isinstance(reported_usage, dict) else {}
    output_bytes = reported_usage.get("output_bytes")
    sources = structured.get("sources") if isinstance(structured.get("sources"), list) else []
    source = structured.get("source") if isinstance(structured.get("source"), dict) else None
    source_content_bytes = sum(
        len(value.get("content", "").encode("utf-8"))
        for value in sources
        if isinstance(value, dict) and isinstance(value.get("content"), str)
    )
    if source and isinstance(source.get("content"), str):
        source_content_bytes += len(source["content"].encode("utf-8"))
    omissions = structured.get("omissions") if isinstance(structured.get("omissions"), list) else []
    summary = {
        "operation_ref": f"native-event:{item.get('id')}",
        "item_id": item.get("id"),
        "local_line": local_line,
        "original_line": original_line,
        "server": item.get("server"),
        "tool": item.get("tool"),
        "status": item.get("status"),
        "arguments_sha256": digest_bytes(compact(arguments)),
        "result_envelope_bytes": len(result_bytes),
        "result_envelope_sha256": digest_bytes(result_bytes),
        "reported_output_bytes": int(output_bytes) if isinstance(output_bytes, int) else None,
        "reported_evidence_bytes": reported_usage.get("evidence_bytes"),
        "source_content_bytes": source_content_bytes,
        "relationship_count": len(structured.get("relationships", [])) if isinstance(structured.get("relationships"), list) else None,
        "item_count": len(structured.get("items", [])) if isinstance(structured.get("items"), list) else None,
        "omission_counts": {
            value.get("reason"): value.get("count")
            for value in omissions
            if isinstance(value, dict) and isinstance(value.get("reason"), str)
        },
    }
    if observed:
        summary["invocation_category"] = observed.get("invocation_category")
    return summary


def shell_summary(item: dict[str, Any], local_line: int, original_line: int, observed: dict[str, Any] | None) -> dict[str, Any]:
    stdout = item.get("stdout") if isinstance(item.get("stdout"), str) else ""
    stderr = item.get("stderr") if isinstance(item.get("stderr"), str) else ""
    command_bytes = compact(item.get("command"))
    return {
        "operation_ref": f"native-event:{item.get('id')}",
        "item_id": item.get("id"),
        "local_line": local_line,
        "original_line": original_line,
        "status": item.get("status"),
        "exit_code": item.get("exit_code"),
        "invocation_category": observed.get("invocation_category") if observed else None,
        "command_sha256": digest_bytes(command_bytes),
        "stdout_bytes": len(stdout.encode("utf-8")),
        "stdout_sha256": digest_bytes(stdout.encode("utf-8")),
        "stderr_bytes": len(stderr.encode("utf-8")),
        "stderr_sha256": digest_bytes(stderr.encode("utf-8")),
    }


def classify_preceding(mcp: list[dict[str, Any]], shell: list[dict[str, Any]], outer: list[dict[str, Any]]) -> str:
    if mcp and shell:
        return "mixed_mcp_shell"
    if mcp:
        return "mcp_only"
    if shell:
        return "shell_only"
    if outer:
        return "outer_output_without_terminal_operation"
    return "no_tool_delivery"


def analyze_run(entry: dict[str, Any], cohort: str, case_id: str, frozen: dict[str, Any]) -> dict[str, Any]:
    metadata_path = ROOT / entry["metadata"]
    observation_path = ROOT / entry["observation"]
    interval_path = ROOT / entry["retained_interval"]
    metadata = read_json(metadata_path)
    observation = unwrap_observation(read_json(observation_path))
    raw = interval_path.read_bytes()
    raw_lines = raw.splitlines(keepends=True)
    records = [json.loads(line) for line in raw_lines]
    native = metadata["native"]
    observer_metadata = metadata["observer_metadata"]
    start_line = int(native["interval_start_line"])
    expected_end_line = int(native["interval_end_line"])
    mcp_observed, shell_observed = operation_maps(observation)

    def original(local_line: int) -> int:
        return start_line + local_line - 1

    outer_requests: dict[str, dict[str, Any]] = {}
    outer_outputs: list[dict[str, Any]] = []
    terminals: list[dict[str, Any]] = []
    finals: list[dict[str, Any]] = []
    boundaries: list[dict[str, Any]] = []
    usage_records: list[dict[str, Any]] = []

    for local_line, record in enumerate(records, 1):
        payload = record.get("payload")
        payload = payload if isinstance(payload, dict) else {}
        if record.get("type") == "response_item":
            kind = payload.get("type")
            call_id = payload.get("call_id")
            is_exec = kind == "custom_tool_call" and payload.get("name") == "exec"
            is_wait = kind == "function_call" and payload.get("name") == "wait"
            if isinstance(call_id, str) and (is_exec or is_wait):
                request_blob = payload.get("input") if is_exec else payload.get("arguments")
                request_bytes = compact(request_blob)
                outer_requests[call_id] = {
                    "outer_ref": f"outer:{call_id}",
                    "call_id": call_id,
                    "kind": "exec" if is_exec else "wait",
                    "local_line": local_line,
                    "original_line": original(local_line),
                    "request_bytes": len(request_bytes),
                    "request_sha256": digest_bytes(request_bytes),
                }
            elif isinstance(call_id, str) and kind in {"custom_tool_call_output", "function_call_output"}:
                blocks = []
                for index, text in enumerate(output_texts(payload.get("output"))):
                    encoded = text.encode("utf-8")
                    blocks.append(
                        {
                            "block_index": index,
                            "bytes": len(encoded),
                            "sha256": digest_bytes(encoded),
                            "truncated": "Warning: truncated output" in text,
                        }
                    )
                outer_outputs.append(
                    {
                        "outer_ref": f"outer:{call_id}",
                        "call_id": call_id,
                        "local_line": local_line,
                        "original_line": original(local_line),
                        "blocks": blocks,
                        "bytes": sum(block["bytes"] for block in blocks),
                    }
                )
        elif record.get("type") == "event_msg":
            event_type = payload.get("type")
            item = payload.get("item")
            item = item if isinstance(item, dict) else {}
            if event_type in {"item_completed", "item_failed"} and item.get("type") == "McpToolCall":
                terminals.append(
                    {
                        "kind": "mcp",
                        "line": local_line,
                        "value": mcp_summary(item, local_line, original(local_line), mcp_observed.get(item.get("id"))),
                    }
                )
            elif event_type in {"item_completed", "item_failed"} and item.get("type") == "CommandExecution":
                terminals.append(
                    {
                        "kind": "shell",
                        "line": local_line,
                        "value": shell_summary(item, local_line, original(local_line), shell_observed.get(item.get("id"))),
                    }
                )
            if event_type == "item_completed" and item.get("type") == "AgentMessage" and item.get("phase") in {"final", "final_answer"}:
                content_bytes = compact(item.get("content"))
                finals.append(
                    {
                        "item_id": item.get("id"),
                        "local_line": local_line,
                        "original_line": original(local_line),
                        "bytes": len(content_bytes),
                        "sha256": digest_bytes(content_bytes),
                    }
                )
            if event_type in {"task_complete", "turn_aborted"}:
                boundaries.append(
                    {
                        "type": event_type,
                        "local_line": local_line,
                        "original_line": original(local_line),
                    }
                )
        elif record.get("type") == "token_usage_record":
            if payload.get("thread_id") == observer_metadata["thread_id"] and payload.get("turn_id") == observer_metadata["turn_id"]:
                usage_records.append({"line": local_line, "payload": payload})

    rounds = []
    prior_cumulative = {field: 0 for field in USAGE_FIELDS}
    prior_usage_line = 0
    for index, usage_record in enumerate(usage_records, 1):
        line = usage_record["line"]
        payload = usage_record["payload"]
        cumulative = payload.get("turn_token_usage")
        per_response = payload.get("usage")
        if not isinstance(cumulative, dict) or not isinstance(per_response, dict):
            raise ValueError(f"{entry['run_id']} has malformed provider usage at local line {line}")
        delta = usage_delta(cumulative, prior_cumulative)
        preceding_mcp = [op["value"] for op in terminals if op["kind"] == "mcp" and prior_usage_line < op["line"] < line]
        preceding_shell = [op["value"] for op in terminals if op["kind"] == "shell" and prior_usage_line < op["line"] < line]
        preceding_outer = [value for value in outer_outputs if prior_usage_line < value["local_line"] < line]
        issued_outer = [value for value in outer_requests.values() if prior_usage_line < value["local_line"] <= line]
        final_markers = [value for value in finals if prior_usage_line < value["local_line"] < line]
        preceding = {
            "local_line_window_exclusive": [prior_usage_line, line],
            "original_line_window_exclusive": [original(prior_usage_line) if prior_usage_line else start_line - 1, original(line)],
            "activity_class": classify_preceding(preceding_mcp, preceding_shell, preceding_outer),
            "outer_output_refs": [item["outer_ref"] for item in preceding_outer],
            "mcp_operation_refs": [item["operation_ref"] for item in preceding_mcp],
            "shell_operation_refs": [item["operation_ref"] for item in preceding_shell],
            "contains_loci_mcp": any(item.get("server") == "loci" for item in preceding_mcp),
            "outer_output_bytes": sum(item["bytes"] for item in preceding_outer),
            "mcp_result_envelope_bytes": sum(item["result_envelope_bytes"] for item in preceding_mcp),
            "mcp_reported_output_bytes": sum(item["reported_output_bytes"] or 0 for item in preceding_mcp),
            "shell_output_bytes": sum(item["stdout_bytes"] + item["stderr_bytes"] for item in preceding_shell),
            "temporal_alignment_only": True,
        }
        rounds.append(
            {
                "round": index,
                "response_id": payload.get("response_id"),
                "usage_record_local_line": line,
                "usage_record_original_line": original(line),
                "provider_usage_semantics": "per_response_snapshot_and_cumulative_turn_total",
                "per_response": {field: int(per_response.get(field, 0)) for field in USAGE_FIELDS},
                "cumulative": {field: int(cumulative.get(field, 0)) for field in USAGE_FIELDS},
                "delta_matches_per_response": usage_equal(delta, per_response),
                "preceding_delivery": preceding,
                "issued_outer_request_refs": [item["outer_ref"] for item in issued_outer],
                "final_answer_refs": [f"native-event:{item['item_id']}" for item in final_markers],
            }
        )
        prior_cumulative = cumulative
        prior_usage_line = line

    if not rounds:
        raise ValueError(f"{entry['run_id']} has no selected provider usage records")
    final_usage = rounds[-1]["cumulative"]
    frozen_metrics = frozen["metrics"] if "metrics" in frozen else {
        "provider_input_tokens": frozen["provider_usage"]["usage"]["input_tokens"],
        "provider_cached_input_tokens": frozen["provider_usage"]["usage"]["cached_input_tokens"],
        "provider_output_tokens": frozen["provider_usage"]["usage"]["output_tokens"],
        "outer_round_trips": frozen["cost"]["outer_round_trips"],
        "model_visible_output_bytes": frozen["cost"]["model_visible_outer_output_bytes"],
        "mcp_calls": frozen["mcp_calls"],
        "shell_commands": frozen["shell_commands"],
    }
    totals_from_rounds = {field: sum(item["per_response"][field] for item in rounds) for field in USAGE_FIELDS}
    actual_interval_sha = digest_bytes(raw)
    expected_interval_sha = native["interval_sha256"]
    expected_records = expected_end_line - start_line + 1
    final_answer = finals[-1] if finals else None
    boundary = boundaries[-1] if boundaries else None
    outer_output_bytes = sum(item["bytes"] for item in outer_outputs)
    shell_output_bytes = sum(
        item["value"]["stdout_bytes"] + item["value"]["stderr_bytes"] for item in terminals if item["kind"] == "shell"
    )
    mcp_result_bytes = sum(item["value"]["result_envelope_bytes"] for item in terminals if item["kind"] == "mcp")
    anomalies = []
    checks = {
        "retained_interval_sha256_matches_metadata": actual_interval_sha == expected_interval_sha,
        "retained_record_count_matches_metadata_lines": len(records) == expected_records,
        "all_cumulative_deltas_match_per_response_usage": all(item["delta_matches_per_response"] for item in rounds),
        "summed_per_response_usage_matches_final_cumulative": usage_equal(totals_from_rounds, final_usage),
        "final_input_matches_frozen_result": final_usage["input_tokens"] == frozen_metrics["provider_input_tokens"],
        "final_cached_input_matches_frozen_result": final_usage["cached_input_tokens"] == frozen_metrics["provider_cached_input_tokens"],
        "final_output_matches_frozen_result": final_usage["output_tokens"] == frozen_metrics["provider_output_tokens"],
        "outer_request_count_matches_frozen_result": len(outer_requests) == frozen_metrics["outer_round_trips"],
        "outer_output_bytes_match_frozen_result": outer_output_bytes == frozen_metrics["model_visible_output_bytes"],
        "mcp_count_matches_frozen_result": sum(1 for item in terminals if item["kind"] == "mcp") == frozen_metrics["mcp_calls"],
        "shell_count_matches_frozen_result": sum(1 for item in terminals if item["kind"] == "shell") == frozen_metrics["shell_commands"],
        "final_answer_precedes_last_usage_snapshot": bool(final_answer and final_answer["local_line"] < rounds[-1]["usage_record_local_line"]),
        "last_usage_snapshot_precedes_boundary": bool(boundary and rounds[-1]["usage_record_local_line"] < boundary["local_line"]),
    }
    for name, passed in checks.items():
        if not passed:
            anomalies.append(name)
    if len(rounds) != len(outer_requests) + 1:
        anomalies.append("provider_snapshot_count_is_not_outer_round_trips_plus_one")
    if any(value < 0 for item in rounds for value in item["per_response"].values()):
        anomalies.append("negative_per_response_usage")

    by_activity: dict[str, dict[str, int]] = defaultdict(lambda: {"rounds": 0, "input_tokens": 0, "cached_input_tokens": 0, "uncached_input_tokens": 0, "outer_output_bytes": 0})
    for item in rounds:
        key = item["preceding_delivery"]["activity_class"]
        bucket = by_activity[key]
        bucket["rounds"] += 1
        bucket["input_tokens"] += item["per_response"]["input_tokens"]
        bucket["cached_input_tokens"] += item["per_response"]["cached_input_tokens"]
        bucket["uncached_input_tokens"] += item["per_response"]["input_tokens"] - item["per_response"]["cached_input_tokens"]
        bucket["outer_output_bytes"] += item["preceding_delivery"]["outer_output_bytes"]
    temporal_loci_rounds = [item for item in rounds if item["preceding_delivery"]["contains_loci_mcp"]]
    temporal_any_tool_rounds = [item for item in rounds if item["preceding_delivery"]["mcp_operation_refs"] or item["preceding_delivery"]["shell_operation_refs"]]
    temporal_outer_rounds = [item for item in rounds if item["preceding_delivery"]["outer_output_refs"]]

    run = {
        "run_id": entry["run_id"],
        "case_id": case_id,
        "cohort": cohort,
        "provenance": {
            "native_rollout": native.get("rollout_path") or native.get("local_uri"),
            "native_whole_file_bytes": native.get("whole_file_bytes"),
            "native_whole_file_sha256": native.get("whole_file_sha256"),
            "thread_id": observer_metadata["thread_id"],
            "turn_id": observer_metadata["turn_id"],
            "original_interval_start_line": start_line,
            "original_interval_end_line": expected_end_line,
            "interval_bytes": len(raw),
            "interval_sha256": actual_interval_sha,
            "retained_interval": str(interval_path.relative_to(ROOT)),
            "retained_interval_publication": "local_only_source_not_copied",
            "metadata_receipt": file_receipt(metadata_path),
            "observation_receipt": file_receipt(observation_path),
        },
        "totals": {
            "provider_snapshots": len(rounds),
            "outer_round_trips": len(outer_requests),
            "provider_input_tokens": final_usage["input_tokens"],
            "provider_cached_input_tokens": final_usage["cached_input_tokens"],
            "provider_uncached_input_tokens": final_usage["input_tokens"] - final_usage["cached_input_tokens"],
            "provider_output_tokens": final_usage["output_tokens"],
            "outer_output_bytes": outer_output_bytes,
            "mcp_operations": sum(1 for item in terminals if item["kind"] == "mcp"),
            "mcp_result_envelope_bytes": mcp_result_bytes,
            "shell_operations": sum(1 for item in terminals if item["kind"] == "shell"),
            "shell_output_bytes": shell_output_bytes,
        },
        "frozen_qualifications": {
            "access_status": frozen.get("access_status") or frozen.get("raw_integrity", {}).get("structural"),
            "scope_deviation_count": len(frozen.get("scope_deviations", [])),
            "strict_correct": frozen.get("strict_correct", frozen.get("rubric_coverage", {}).get("complete")),
            "supported_answer": frozen.get("supported_answer"),
            "source": entry["observation"],
            "regraded": False,
        },
        "descriptive_accounting": {
            "exclusive_preceding_activity": dict(sorted(by_activity.items())),
            "input_after_temporally_preceding_loci_terminal_operations": sum(item["per_response"]["input_tokens"] for item in temporal_loci_rounds),
            "input_after_temporally_preceding_any_terminal_operations": sum(item["per_response"]["input_tokens"] for item in temporal_any_tool_rounds),
            "input_after_temporally_preceding_outer_outputs": sum(item["per_response"]["input_tokens"] for item in temporal_outer_rounds),
            "shares_of_total_input": {
                "after_loci_terminal_operations": ratio(sum(item["per_response"]["input_tokens"] for item in temporal_loci_rounds), final_usage["input_tokens"]),
                "after_any_terminal_operations": ratio(sum(item["per_response"]["input_tokens"] for item in temporal_any_tool_rounds), final_usage["input_tokens"]),
                "after_outer_outputs": ratio(sum(item["per_response"]["input_tokens"] for item in temporal_outer_rounds), final_usage["input_tokens"]),
            },
            "qualification": "These overlapping temporal buckets describe provider responses after result delivery. Native nested operations have no outer call id, and the buckets are not causal token allocations.",
        },
        "rounds": rounds,
        "operation_ledger": {
            "outer_requests": list(outer_requests.values()),
            "outer_outputs": outer_outputs,
            "mcp": [item["value"] for item in terminals if item["kind"] == "mcp"],
            "shell": [item["value"] for item in terminals if item["kind"] == "shell"],
        },
        "final_answer": final_answer,
        "boundary": boundary,
        "reconciliation": {"checks": checks, "anomalies": anomalies},
    }
    return run


def metric_value(run: dict[str, Any], metric: str) -> int | float:
    return run["totals"][metric]


def summarize_metric(baseline: list[dict[str, Any]], post: list[dict[str, Any]], metric: str) -> dict[str, Any]:
    baseline_values = [metric_value(run, metric) for run in baseline]
    post_values = [metric_value(run, metric) for run in post]
    baseline_median = normalized_number(median(baseline_values))
    post_median = normalized_number(median(post_values))
    return {
        "baseline_values": baseline_values,
        "baseline_median": baseline_median,
        "post_values": post_values,
        "post_median": post_median,
        "post_to_baseline_ratio": ratio(float(post_median), float(baseline_median)),
        "percent_change": percent(float(post_median), float(baseline_median)),
    }


def summarize_case(case: dict[str, Any], runs: list[dict[str, Any]]) -> dict[str, Any]:
    case_runs = [run for run in runs if run["case_id"] == case["case_id"]]
    baseline = [run for run in case_runs if run["cohort"] == "baseline"]
    post = [run for run in case_runs if run["cohort"] == "post"]
    metrics = {}
    for metric in (
        "provider_input_tokens",
        "provider_cached_input_tokens",
        "provider_uncached_input_tokens",
        "provider_output_tokens",
        "outer_output_bytes",
        "outer_round_trips",
        "provider_snapshots",
        "mcp_operations",
        "mcp_result_envelope_bytes",
        "shell_operations",
        "shell_output_bytes",
    ):
        metrics[metric] = summarize_metric(baseline, post, metric)
    baseline_max_snapshots = max(run["totals"]["provider_snapshots"] for run in baseline)
    late_rounds = []
    for run in post:
        selected = [item for item in run["rounds"] if item["round"] > baseline_max_snapshots]
        late_input = sum(item["per_response"]["input_tokens"] for item in selected)
        late_rounds.append(
            {
                "run_id": run["run_id"],
                "baseline_max_provider_snapshots": baseline_max_snapshots,
                "post_rounds_beyond_baseline_max": len(selected),
                "input_tokens_in_those_rounds": late_input,
                "share_of_run_input": ratio(late_input, run["totals"]["provider_input_tokens"]),
                "qualification": "Counterfactual-free descriptive slice; it does not estimate tokens saved by truncating the run.",
            }
        )
    return {
        "case_id": case["case_id"],
        "short_name": case["short_name"],
        "baseline_run_ids": [run["run_id"] for run in baseline],
        "post_run_ids": [run["run_id"] for run in post],
        "metrics": metrics,
        "post_late_round_accounting": late_rounds,
    }


def main() -> None:
    schedule = read_json(SCHEDULE_PATH)
    frozen = frozen_rows(schedule)
    runs = []
    for case in schedule["cases"]:
        for cohort in ("baseline", "post"):
            for entry in case[cohort]:
                runs.append(analyze_run(entry, cohort, case["case_id"], frozen[(cohort, entry["run_id"])]))
    cases = [summarize_case(case, runs) for case in schedule["cases"]]
    results = {
        "schema_version": 1,
        "diagnosis_id": schedule["diagnosis_id"],
        "measurement_status": "passive_reanalysis_of_eight_existing_retained_runs",
        "provider_usage_semantics": {
            "payload_usage": "per-response usage snapshot",
            "payload_turn_token_usage": "cumulative within the selected turn",
            "round_value": "cumulative delta, verified against payload.usage",
            "temporal_window": "Terminal operations and outer outputs strictly after the previous usage record and before the current usage record are candidates for content consumed by the current response.",
            "causality": "No exact token allocation to a tool, byte, or workflow step is inferred.",
        },
        "cases": cases,
        "runs": runs,
        "global_reconciliation": {
            "run_count": len(runs),
            "all_run_checks_pass": all(all(run["reconciliation"]["checks"].values()) for run in runs),
            "runs_with_anomalies": [
                {"run_id": run["run_id"], "anomalies": run["reconciliation"]["anomalies"]}
                for run in runs
                if run["reconciliation"]["anomalies"]
            ],
        },
        "limitations": [
            "Two attempts per condition provide descriptive medians only; no significance or causal effect is estimated.",
            "Provider input tokens include the full model request context; visible result bytes are not token counts.",
            "Nested MCP and shell terminal events do not carry an outer Code Mode call id, so temporal co-location cannot prove parentage or exact consumption.",
            "Cached and uncached token splits are provider accounting fields, not direct measures of useful source evidence.",
            "Raw retained intervals remain local-only and are represented here by exact hashes, line bounds, normalized counters, and operation references.",
        ],
    }
    linkage = {
        "schema_version": 1,
        "diagnosis_id": schedule["diagnosis_id"],
        "schedule": file_receipt(SCHEDULE_PATH),
        "frozen_sources": {
            name: file_receipt(ROOT / path) for name, path in schedule["frozen_sources"].items()
        },
        "case_linkage": [
            {
                "case_id": case["case_id"],
                "baseline_run_ids": [entry["run_id"] for entry in case["baseline"]],
                "post_run_ids": [entry["run_id"] for entry in case["post"]],
            }
            for case in schedule["cases"]
        ],
    }
    write_json(RESULTS_PATH, results)
    write_json(LINKAGE_PATH, linkage)
    metadata = {
        "schema_version": 1,
        "diagnosis_id": schedule["diagnosis_id"],
        "generator": file_receipt(Path(__file__).resolve()),
        "schedule": file_receipt(SCHEDULE_PATH),
        "results": file_receipt(RESULTS_PATH),
        "baseline_linkage": file_receipt(LINKAGE_PATH),
        "run_provenance": [
            {
                "run_id": run["run_id"],
                "native_rollout": run["provenance"]["native_rollout"],
                "thread_id": run["provenance"]["thread_id"],
                "turn_id": run["provenance"]["turn_id"],
                "original_interval_start_line": run["provenance"]["original_interval_start_line"],
                "original_interval_end_line": run["provenance"]["original_interval_end_line"],
                "interval_bytes": run["provenance"]["interval_bytes"],
                "interval_sha256": run["provenance"]["interval_sha256"],
                "retained_interval": run["provenance"]["retained_interval"],
                "retained_interval_publication": run["provenance"]["retained_interval_publication"],
            }
            for run in runs
        ],
        "publication_scope": {
            "published": [
                str(path.relative_to(ROOT))
                for path in (
                    RESULTS_PATH,
                    LINKAGE_PATH,
                    METADATA_PATH,
                    SCHEDULE_PATH,
                    Path(__file__).resolve(),
                    HERE / "token-diagnosis.md",
                )
            ],
            "raw_native_intervals": "local_only_not_copied",
        },
    }
    write_json(METADATA_PATH, metadata)


if __name__ == "__main__":
    main()
