from __future__ import annotations

import json
from pathlib import Path

from benchmarks.typescript_context_baseline_report import generate_report
from benchmarks.typescript_context_corpus import load_corpus


def _artifact(
    case_id: str,
    repetition: int,
    *,
    latency: float,
    correct: bool = True,
    timeout: bool = False,
    unverified: bool = False,
    missing_tokens: bool = False,
    duplicate_source: bool = False,
) -> dict:
    usage = None if missing_tokens else {
        "input_tokens": 100,
        "cached_input_tokens": 20,
        "output_tokens": 10,
    }
    failures = []
    outcome = "completed"
    if timeout:
        outcome = "timeout"
        failures.append({"category": "timeout", "limit": "end_to_end"})
    if unverified:
        outcome = "tool_failure"
        failures.append({"category": "invalid_trace"})
    spans = [{"file": "consumer.ts", "start_byte": 0, "end_byte": 4}]
    if duplicate_source:
        spans.append({"file": "consumer.ts", "start_byte": 0, "end_byte": 4})
    source_bytes = sum(span["end_byte"] - span["start_byte"] for span in spans)
    return {
        "schema_version": 1,
        "identity": {
            "task_id": case_id,
            "session_id": f"session-{case_id}-{repetition}",
            "arm": "A",
            "repetition": repetition,
            "snapshot": "fixture-v1",
        },
        "events": [{"spans": spans}],
        "measurement": {
            "schema_version": 1,
            "outcome": outcome,
            "task_correct": correct,
            "answer": {"case": case_id, "repetition": repetition},
            "read_count": repetition,
            "avoidable_reads": 0,
            "proven_avoidable_reads": 0,
            "lineage_status": "complete",
            "required_context_delivered": ["entry", "callee"],
            "required_context_total": 2,
            "context_recall": 1.0,
            "serialized_tool_output_bytes": 100 + repetition,
            "source_bytes": source_bytes,
            "estimated_source_tokens": (source_bytes + 3) // 4,
            "tool_elapsed_ms": 5.0 * repetition,
            "provider_usage": usage,
            "usage_semantics": "synthetic test measurement",
            "token_status": "unavailable" if usage is None else "measured",
        },
        "baseline": {
            "end_to_end_seconds": latency,
            "actual_process_seconds": latency + 0.25,
            "exit_code": -15 if timeout else 0,
            "provider_thread_id": f"thread-{case_id}-{repetition}",
            "failures": failures,
            "tool_delivery_verified": not unverified,
            "relationships": {
                "available_dependency_links_total": 1,
                "delivered_dependency_links_total": 1,
                "forbidden_proven_relationships": 0,
            },
        },
    }


def _write_artifact(root: Path, artifact: dict, name: str | None = None) -> None:
    identity = artifact["identity"]
    directory = root / (name or f'{identity["task_id"]}-r{identity["repetition"]}')
    directory.mkdir(parents=True)
    (directory / "result.json").write_text(json.dumps(artifact), encoding="utf-8")
    (directory / "provenance.json").write_text(
        json.dumps({"index_seconds": artifact["baseline"]["end_to_end_seconds"] / 10}),
        encoding="utf-8",
    )


def test_generate_report_aggregates_complete_batch_and_preserves_nulls(tmp_path: Path) -> None:
    corpus = load_corpus()
    for case_index, case in enumerate(corpus["cases"]):
        for repetition in range(1, 4):
            is_first = case_index == 0 and repetition == 1
            maintained = case["group"] == "maintained_task"
            maintained_latency = (case_index - 14) * 3 + repetition if maintained else 2 + repetition
            _write_artifact(
                tmp_path,
                _artifact(
                    case["id"],
                    repetition,
                    latency=maintained_latency,
                    correct=not is_first,
                    timeout=case_index == 16 and repetition == 3,
                    unverified=is_first,
                    missing_tokens=is_first,
                    duplicate_source=is_first,
                ),
            )
    (tmp_path / "environment.json").write_text(
        json.dumps({"synthetic": True}), encoding="utf-8"
    )

    summary = generate_report(tmp_path)

    assert (tmp_path / "summary.json").is_file()
    assert (tmp_path / "report.md").is_file()
    assert summary["batch"]["complete_batch"] is True
    assert summary["batch"]["unique_identity_count"] == 51
    assert summary["corpus"]["fixture_case_count"] == 14
    assert summary["corpus"]["maintained_case_count"] == 3
    assert summary["groups"]["fixture14"]["case_count"] == 14
    assert summary["groups"]["maintained3"]["case_count"] == 3
    assert summary["cases"][0]["eligible"] is False
    assert len(summary["runs"]) == 51
    assert summary["runs"][0]["raw_result"]["measurement"]["answer"]["case"] == summary["cases"][0]["id"]

    assert summary["costs"]["serialized_tool_output_bytes"]["total"] is None
    assert summary["costs"]["serialized_tool_output_bytes"]["recorded_subtotal"] == 5202
    assert summary["costs"]["serialized_tool_output_bytes"]["unavailable_count"] == 1
    assert summary["accounting_complete"] is False
    assert summary["batch"]["all_costs_counted_for_parsed_runs"] is False
    assert summary["costs"]["source_bytes"]["total"] == 208
    assert summary["costs"]["duplicate_source_bytes"]["total"] == 4
    assert summary["costs"]["provider_tokens"]["gross_input_tokens"]["total"] is None
    assert summary["costs"]["provider_tokens"]["gross_input_tokens"]["measured_subtotal"] == 5000
    assert summary["costs"]["provider_tokens"]["gross_input_tokens"]["unavailable_count"] == 1

    causal = summary["context_and_causality"]
    assert causal["avoidable_reads"]["values"][0] is None
    assert causal["avoidable_reads"]["unavailable_count"] == 1
    assert summary["cases"][0]["medians"]["serialized_tool_output_bytes"]["median"] is None
    assert summary["cases"][0]["medians"]["serialized_tool_output_bytes"]["observed_subset_median"] == 102.5
    assert causal["null_or_inconclusive_runs"] == ["imported_interface-r1/result.json"]
    assert summary["failure_categories"]["invalid_trace"] == 1
    assert summary["latency"]["maintained_p95_end_to_end_seconds"]["p95_seconds"] == 9
    assert summary["latency"]["maintained_p95_end_to_end_seconds"]["sample_count"] == 9
    assert summary["latency"]["maintained_p95_end_to_end_seconds"]["failure_run_count"] == 1
    assert summary["relationships"]["forbidden_scope"].startswith("proven_forbidden relationship count")
    report = (tmp_path / "report.md").read_text(encoding="utf-8")
    assert "JSON tool-output bytes: unavailable" in report
    assert "None" not in report


def test_generate_report_requires_the_exact_planned_identity_set(tmp_path: Path) -> None:
    corpus = load_corpus()
    case_id = corpus["cases"][0]["id"]
    _write_artifact(tmp_path, _artifact(case_id, 1, latency=1), name="first")
    _write_artifact(tmp_path, _artifact(case_id, 1, latency=2), name="duplicate")

    summary = generate_report(tmp_path)

    assert summary["batch"]["complete_batch"] is False
    assert summary["batch"]["unique_identity_count"] == 1
    assert summary["batch"]["duplicate_identities"] == [[case_id, 1]]
    assert len(summary["batch"]["missing_identities"]) == 50
    assert summary["groups"]["fixture14"]["run_count"] == 2
    assert summary["costs"]["source_bytes"]["total"] == 8


def test_generate_report_surfaces_partial_attempt_directories(tmp_path: Path) -> None:
    partial = tmp_path / "partial-attempt"
    partial.mkdir()
    (partial / "adapter-trace.json").write_text("{}", encoding="utf-8")
    (partial / "events.jsonl").write_text("", encoding="utf-8")

    summary = generate_report(tmp_path)

    assert summary["batch"]["complete_batch"] is False
    assert summary["batch"]["partial_attempt_directories"] == [{
        "path": "partial-attempt",
        "present_files": ["adapter-trace.json", "events.jsonl"],
        "category": "partial_attempt",
    }]
    assert summary["failure_categories"]["partial_attempt"] == 1


def test_maintained_p95_requires_nine_unique_a_identities(tmp_path: Path) -> None:
    corpus = load_corpus()
    maintained = [case for case in corpus["cases"] if case["group"] == "maintained_task"]
    for case in maintained:
        for repetition in range(1, 4):
            if case is maintained[-1] and repetition == 3:
                continue
            _write_artifact(
                tmp_path,
                _artifact(case["id"], repetition, latency=float(repetition)),
            )
    duplicate = _artifact(maintained[0]["id"], 1, latency=50)
    _write_artifact(tmp_path, duplicate, name="duplicate-maintained-r1")

    summary = generate_report(tmp_path)
    p95 = summary["latency"]["maintained_p95_end_to_end_seconds"]

    assert p95["candidate_run_count"] == 9
    assert p95["sample_count"] == 7
    assert p95["missing_identities"] == [[maintained[-1]["id"], 3]]
    assert p95["duplicate_identities"] == [[maintained[0]["id"], 1]]
    assert p95["p95_seconds"] is None
    assert p95["status"] == "unavailable"
