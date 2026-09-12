from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from benchmarks.typescript_context_compare_report import evaluate as frozen_evaluate
from benchmarks.typescript_context_corpus import load_controls, load_corpus
from benchmarks.typescript_context_routing_v2 import VERSION
from benchmarks.typescript_context_routing_v2_observed import PROTOCOL as OBSERVED_PROTOCOL, RAW_PROTOCOL
from benchmarks.typescript_context_routing_v2_report import (
    ARMS,
    CANDIDATE_REQUIRED,
    EXPECTED_RUNS,
    MEASUREMENT_PROTOCOL,
    _validate_current_artifact,
    _validate_source_denominator,
    evaluate,
)
from benchmarks.typescript_context_routing_v2_replay import (
    COMPARISON as REPLAY_COMPARISON,
    POLICY_PATH as REPLAY_POLICY_PATH,
)
from benchmarks.typescript_context_routing_v2_run import (
    COMPARISON as RUN_COMPARISON,
    COMPARISON_ROOT as RUN_COMPARISON_ROOT,
)
from benchmarks.typescript_context_routing_v2 import POLICY_PATH


ROOT = Path(__file__).parents[1]
CORPUS_ROOT = ROOT / "benchmarks" / "corpora" / "typescript-context-v3"


def _examples() -> tuple[list[dict], dict]:
    corpus = load_corpus(CORPUS_ROOT)
    controls = load_controls(corpus)
    runs = []
    for case in corpus["cases"]:
        for repetition in range(3):
            for arm in ARMS:
                runs.append(
                    {
                        "task_id": case["id"],
                        "group": case["group"],
                        "arm": arm,
                        "repetition": repetition,
                        "answer_correct": True,
                        "task_correct": True,
                        "measurement_complete": True,
                        "outcome": "completed",
                        "failures": [],
                        "read_count": 10 if arm == "A" else 8,
                        "context_recall": 1.0,
                        "serialized_tool_output_bytes": 10000 if arm == "A" else 9000,
                        "input_tokens": 10000 if arm == "A" else 9000,
                        "end_to_end_seconds": 20,
                        "relationships": {
                            "required_semantic_dependencies_total": 1,
                            "available_dependency_links_total": 1,
                            "delivered_dependency_links_total": 1,
                            "forbidden_proven_relationships": 0,
                        },
                    }
                )
    return runs, controls


def test_v2_report_binds_version_owners_and_preserves_frozen_numeric_gates() -> None:
    runs, controls = _examples()

    assert VERSION == OBSERVED_PROTOCOL == MEASUREMENT_PROTOCOL
    assert REPLAY_COMPARISON == RUN_COMPARISON == VERSION
    assert REPLAY_POLICY_PATH == POLICY_PATH
    assert RUN_COMPARISON_ROOT.name == VERSION
    assert evaluate(copy.deepcopy(runs), controls, endpoints_available=True) == frozen_evaluate(
        runs, controls, endpoints_available=True
    )


def test_report_rejects_old_result_protocol_and_wrong_raw_trace_protocol(tmp_path: Path) -> None:
    folder = tmp_path / "case-r1-B"
    folder.mkdir()
    provenance = {
        "attempt_id": folder.name,
        "routing": {"version": VERSION, "condition": "B", "capability_arm": "B"},
    }
    result = {
        "protocol": VERSION,
        "schema_version": 3,
        "provenance": provenance,
        "identity": {"task_id": "case", "repetition": 1, "arm": "B"},
        "attempt_id": folder.name,
        "arm": "B",
    }
    run = {"task_id": "case", "repetition": 1, "arm": "B"}
    trace = folder / "adapter-trace.json"
    trace.write_text(json.dumps({"protocol": RAW_PROTOCOL}), encoding="utf-8")

    _validate_current_artifact(result, provenance, folder, run)

    old_result = {**result, "protocol": "typescript-context-routing-v1"}
    with pytest.raises(ValueError, match="current typescript-context-routing-v2"):
        _validate_current_artifact(old_result, provenance, folder, run)

    trace.write_text(json.dumps({"protocol": VERSION}), encoding="utf-8")
    with pytest.raises(ValueError, match="incompatible protocol"):
        _validate_current_artifact(result, provenance, folder, run)


def test_report_requires_the_complete_nine_attempt_maintained_denominator() -> None:
    runs = [
        {"group": "maintained_task", "arm": arm}
        for arm in ARMS
        for _ in range(CANDIDATE_REQUIRED)
    ]
    runs.extend({"group": "fixture", "arm": "A"} for _ in range(EXPECTED_RUNS - len(runs)))

    _validate_source_denominator(runs)

    with pytest.raises(ValueError, match="exact 102"):
        _validate_source_denominator(runs[:-1])
