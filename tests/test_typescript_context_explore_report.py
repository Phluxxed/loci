from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from benchmarks.typescript_context_explore_report import (
    ARMS,
    EXPECTED_RUNS,
    evaluate,
    generate_report,
)


ROOT = Path(__file__).parents[1]
CORPUS_ROOT = ROOT / "benchmarks" / "corpora" / "typescript-context-v3"


def _controls_and_cases() -> tuple[dict, list[dict]]:
    corpus = json.loads((CORPUS_ROOT / "corpus.json").read_text(encoding="utf-8"))
    controls = json.loads((CORPUS_ROOT / "comparison-controls.json").read_text(encoding="utf-8"))
    return controls, corpus["cases"]


def _runs() -> tuple[list[dict], dict]:
    controls, cases = _controls_and_cases()
    runs = []
    for case in cases:
        for repetition in range(1, 4):
            for arm in ARMS:
                calls = 10 if arm == "A" else 8
                runs.append({
                    "task_id": case["id"],
                    "group": case["group"],
                    "arm": arm,
                    "repetition": repetition,
                    "answer_correct": True,
                    "task_correct": True,
                    "measurement_complete": True,
                    "outcome": "completed",
                    "failures": [],
                    "read_count": calls,
                    "validated_read_count": calls,
                    "context_recall": 1.0,
                    "serialized_tool_output_bytes": calls * 1000,
                    "source_bytes": 1000,
                    "unique_source_bytes": 900,
                    "duplicate_source_bytes": 100,
                    "recorded_payload_bytes": calls * 1000,
                    "input_tokens": calls * 1000,
                    "cached_input_tokens": 100,
                    "output_tokens": 100,
                    "end_to_end_seconds": 20,
                    "index_seconds": 1,
                    "relationships": {
                        "required_semantic_dependencies_total": 1,
                        "available_dependency_links_total": 1,
                        "delivered_dependency_links_total": 1,
                        "forbidden_proven_relationships": 0,
                        "precise_kind_links_available_total": 1,
                        "precise_kind_links_delivered_total": 1,
                        "generic_dependency_links_available_total": 0,
                    },
                })
    return runs, controls


def _artifact(run: dict, *, failure: list[dict] | None = None, proof_violations: int = 0) -> dict:
    usage = {
        "input_tokens": run["input_tokens"],
        "cached_input_tokens": run["cached_input_tokens"],
        "output_tokens": run["output_tokens"],
    }
    events: list[dict[str, Any]] = [{"spans": [{"file": "source.ts", "start_byte": 0, "end_byte": 10}]}]
    if run["arm"] == "B":
        events.append({"operation": "explore", "spans": []})
    relationships = dict(run["relationships"])
    if proof_violations:
        relationships["delivery_integrity_violations"] = [
            {"reason": "invalid_relationship_proof"}
            for _ in range(proof_violations)
        ]
    measurement = {
        key: value
        for key, value in run.items()
        if key not in {
            "group",
            "failures",
            "relationships",
            "end_to_end_seconds",
            "index_seconds",
            "recorded_payload_bytes",
        }
    }
    measurement["schema_version"] = 3
    measurement["provider_usage"] = usage
    return {
        "schema_version": 3,
        "identity": {
            "task_id": run["task_id"],
            "repetition": run["repetition"],
            "arm": run["arm"],
        },
        "measurement": measurement,
        "baseline": {
            "end_to_end_seconds": run["end_to_end_seconds"],
            "failures": failure or [],
            "relationships": relationships,
            "output_accounting": {
                "recorded_payload_bytes": run["recorded_payload_bytes"],
            },
        },
        "events": events,
    }


def _write_batch(root: Path, *, first_failure: bool = False, proof_violations: int = 0) -> None:
    runs, _ = _runs()
    for position, run in enumerate(runs):
        folder = root / f"{run['task_id']}-r{run['repetition']}-{run['arm']}"
        folder.mkdir(parents=True)
        artifact = _artifact(
            run,
            failure=[{"category": "retained_failure"}] if first_failure and position == 0 else None,
            proof_violations=proof_violations if position == 1 else 0,
        )
        (folder / "result.json").write_text(json.dumps(artifact), encoding="utf-8")
        provider_events = []
        if run["arm"] == "B":
            provider_events.append({
                "type": "item.completed",
                "item": {
                    "id": f"{run['task_id']}-{run['repetition']}-explore",
                    "type": "mcp_tool_call",
                    "server": "evaluation",
                    "tool": "loci_explore",
                },
            })
        (folder / "events.jsonl").write_text(
            "\n".join(json.dumps(event) for event in provider_events) + "\n",
            encoding="utf-8",
        )
        (folder / "provenance.json").write_text(
            json.dumps({"index_seconds": run["index_seconds"], "source_tree": "pinned-current"}),
            encoding="utf-8",
        )


def _preflight(path: Path, controls: dict) -> None:
    payload = {
        "schema_version": 1,
        "arms": {
            arm: {
                "arm": arm,
                "cases": [
                    {"id": case_id, "endpoints": [{"status": "indexed"}]}
                    for case_id in controls["case_ids"]
                ],
            }
            for arm in ARMS
        },
    }
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_evaluate_delegates_frozen_gates_and_keeps_original_thresholds() -> None:
    runs, controls = _runs()

    result = evaluate(runs, controls, endpoints_available=True)

    assert result["sum_of_eligible_median_calls"] == {"A": 30, "B": 24}
    assert len(result["eligible_maintained_tasks"]) == 3
    assert result["verdict"] == "keep"
    assert not result["failed_gates"] and not result["unknown_gates"]


def test_proof_integrity_violations_are_forbidden_relationships() -> None:
    runs, controls = _runs()
    selected = next(run for run in runs if run["arm"] == "B")
    selected["relationships"]["delivery_integrity_violations"] = [{"reason": "bad-proof"}]

    result = evaluate(runs, controls, endpoints_available=True)

    assert result["arms"]["B"]["relationships"]["forbidden_proven_relationships"] == 1
    assert "authored_false_relationships" in result["failed_gates"]
    assert result["verdict"] == "reject"


def test_generate_report_requires_exact_two_arm_identity_set(tmp_path: Path) -> None:
    _, cases = _controls_and_cases()
    expected = [
        f"{case['id']}-r{repetition}-{arm}"
        for case in cases
        for repetition in range(1, 4)
        for arm in ARMS
    ]
    assert len(expected) == EXPECTED_RUNS
    for name in expected[:-1]:
        folder = tmp_path / name
        folder.mkdir()
        (folder / "result.json").write_text("{}", encoding="utf-8")

    with pytest.raises(ValueError, match="exact 102"):
        generate_report(tmp_path, CORPUS_ROOT, tmp_path / "preflight.json")


def test_generate_report_preserves_failures_labels_metadata_and_usage(tmp_path: Path) -> None:
    runs, controls = _runs()
    _write_batch(tmp_path, first_failure=True, proof_violations=1)
    preflight = tmp_path / "preflight.json"
    _preflight(preflight, controls)
    (tmp_path / "manifest.json").write_text(
        json.dumps({"protocol": "typescript-context-explore-v1", "planned_runs": EXPECTED_RUNS}),
        encoding="utf-8",
    )

    summary = generate_report(tmp_path, CORPUS_ROOT, preflight)

    assert summary["planned_runs"] == EXPECTED_RUNS
    assert summary["recorded_runs"] == EXPECTED_RUNS
    assert summary["arm_labels"] == {"A": "current exact retrieval", "B": "exact retrieval plus loci_explore"}
    assert summary["endpoint_availability"] == {"A": True, "B": True}
    assert summary["manifest"]["planned_runs"] == EXPECTED_RUNS
    assert summary["actual_loci_explore_usage"]["B"]["usage_accounting_complete"] is True
    assert summary["actual_loci_explore_usage"]["B"]["calls"] == 51
    assert summary["raw_failures"][0]["failure"] == {"category": "retained_failure"}
    assert summary["runs"][1]["relationships"]["forbidden_proven_relationships"] == 1
    assert summary["failed_gates"] == ["authored_false_relationships"]

    report = (tmp_path / "report.md").read_text(encoding="utf-8")
    assert "A is current exact retrieval; B also makes the actual" in report
    assert "actual `loci_explore`" in report
    assert "retained_failure" in report
    assert "153" not in report


def test_optional_tool_choice_and_missing_host_events_are_disclosed(tmp_path: Path) -> None:
    _, controls = _runs()
    _write_batch(tmp_path)
    preflight = tmp_path / 'preflight.json'
    _preflight(preflight, controls)
    (tmp_path / 'imported_interface-r1-B/events.jsonl').write_text('')
    summary = generate_report(tmp_path, CORPUS_ROOT, preflight)
    usage = summary['actual_loci_explore_usage']['B']
    assert usage['calls'] == 50 and usage['usage_accounting_complete']
    assert usage['attempts_without_explore'] == ['imported_interface-r1-B']
    assert summary['verdict'] == 'keep'
    assert summary['qualification_verdict'] == 'inconclusive'
    assert not summary['replay_complete']
    # A source trace with an explore event cannot replace missing host evidence.
    (tmp_path / 'imported_interface-r2-B/events.jsonl').write_text('invalid JSON')
    usage = generate_report(tmp_path, CORPUS_ROOT, preflight)['actual_loci_explore_usage']['B']
    assert usage['calls'] is None and not usage['usage_accounting_complete']
    (tmp_path / 'imported_interface-r2-B/events.jsonl').write_text(json.dumps({
        'type': 'item.completed', 'item': {'type': 'mcp_tool_call', 'server': 'evaluation', 'tool': 'loci_explore'}}))
    assert generate_report(tmp_path, CORPUS_ROOT, preflight)['actual_loci_explore_usage']['B']['calls'] is None
