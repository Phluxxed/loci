from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path

import pytest

from benchmarks.ordinary_adoption_delivery_v3 import (
    DELIVERY_ADAPTER_VERSION,
    supplement_delivery,
)


RUN_ROOT = Path("benchmarks/comparisons/ordinary-adoption-normal-v1/runs")


def _result(value: int) -> dict:
    return {
        "content": [],
        "structuredContent": {"schema_version": 1, "status": "ok", "value": value},
        "isError": False,
    }


def _call(item_id: str, line: int, result: dict, status: str = "unknown_truncated") -> dict:
    compact = json.dumps(result, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    return {
        "item_id": item_id,
        "line": line,
        "server": "loci",
        "tool": "loci_retrieve",
        "result": result,
        "canonical_result_json_bytes": len(compact.encode("utf-8")),
        "canonical_result_json_sha256": "a" * 64,
        "model_delivery": {"status": status, "matches": []},
    }


def _outer(call_id: str, text: str, *, output_line: int = 50) -> dict:
    return {
        "call_id": call_id,
        "kind": "exec",
        "request_line": output_line - 1,
        "request": "call",
        "output": [{"type": "input_text", "text": text}],
        "output_line": output_line,
    }


def _observation(calls: list[dict], outer: list[dict]) -> dict:
    return {
        "run": {"run_id": "run-test", "thread_id": "thread", "turn_id": "turn"},
        "retained_interval": {"sha256": "b" * 64},
        "mcp_calls": calls,
        "outer_code_mode": outer,
    }


def _by_line(supplement: dict) -> dict[int, dict]:
    return {call["native_line"]: call for call in supplement["calls"]}


def test_recovers_exact_json_lines_and_keeps_clipping_on_the_candidate_line() -> None:
    first, clipped, last = _result(1), _result(2), _result(3)
    clipped_json = json.dumps(clipped, ensure_ascii=False, separators=(",", ":"))
    cut_start, cut_end = len(clipped_json) // 3, (len(clipped_json) * 2) // 3
    clipped_line = f"{clipped_json[:cut_start]}…123 tokens truncated…{clipped_json[cut_end:]}"
    text = "\n".join(
        [
            "Warning: truncated output (original token count: 10001)",
            "Total output lines: 3",
            "",
            json.dumps(first["structuredContent"], separators=(",", ":")),
            clipped_line,
            json.dumps(last, separators=(",", ":")),
        ]
    )
    observation = _observation(
        [_call("first", 10, first), _call("middle", 11, clipped), _call("last", 12, last)],
        [_outer("outer-1", text)],
    )
    unchanged = deepcopy(observation)

    supplement = supplement_delivery(observation)
    calls = _by_line(supplement)

    assert observation == unchanged
    assert supplement["adapter_version"] == DELIVERY_ADAPTER_VERSION
    assert supplement["frozen_outcome_unchanged"] is True
    assert calls[10]["supplemental_model_delivery"]["status"] == "full_exact"
    assert calls[11]["supplemental_model_delivery"]["status"] == "unproven_clipped"
    assert calls[12]["supplemental_model_delivery"]["status"] == "full_exact"
    first_match = calls[10]["supplemental_model_delivery"]["exact_matches"][0]
    assert first_match["output_ref"] == "outer:outer-1:line:50:block:0"
    assert first_match["line_number"] == 4
    assert first_match["end_byte"] > first_match["start_byte"]
    encoded_output = text.encode("utf-8")
    assert (
        json.loads(encoded_output[first_match["start_byte"] : first_match["end_byte"]])
        == first["structuredContent"]
    )
    last_match = calls[12]["supplemental_model_delivery"]["exact_matches"][0]
    assert json.loads(encoded_output[last_match["start_byte"] : last_match["end_byte"]]) == last
    clipping = calls[11]["supplemental_model_delivery"]["clipping_evidence"][0]
    assert clipping["reported_omitted_tokens"] == 123
    assert clipping["marker_start_byte"] < clipping["marker_end_byte"]
    assert calls[10]["original_status"] == "unknown_truncated"


@pytest.mark.parametrize(
    "render",
    [
        lambda value: json.dumps(json.dumps(value, separators=(",", ":"))),
        lambda value: f"Example: {json.dumps(value, separators=(',', ':'))}",
        lambda value: f"```json\n{json.dumps(value, separators=(',', ':'))}\n```",
        lambda value: f"> {json.dumps(value, separators=(',', ':'))}",
        lambda value: json.dumps(value, separators=(",", ":"))[:-1],
        lambda value: "{malformed",
    ],
)
def test_quoted_partial_and_malformed_json_do_not_promote_exact(render) -> None:
    result = _result(1)
    observation = _observation([_call("call", 10, result, status="unknown")], [_outer("outer", render(result))])

    delivery = supplement_delivery(observation)["calls"][0]["supplemental_model_delivery"]

    assert delivery["status"] == "unproven"
    assert delivery["exact_matches"] == []
    assert delivery["clipping_evidence"] == []


def test_mismatched_payload_and_unrelated_warning_do_not_claim_clipping() -> None:
    expected, other = _result(1), _result(2)
    observation = _observation(
        [_call("expected", 10, expected, status="unknown_truncated")],
        [
            _outer("plain", json.dumps(other, separators=(",", ":"))),
            _outer("truncated", "Warning: truncated output\n…99 tokens truncated…", output_line=60),
        ],
    )

    delivery = supplement_delivery(observation)["calls"][0]["supplemental_model_delivery"]

    assert delivery["status"] == "unproven"
    assert delivery["unrelated_truncation_not_applied"] is True
    assert delivery["clipping_evidence"] == []


@pytest.mark.parametrize(
    "line",
    [
        '{"schema_version":1,"status":"ok","value":true}',
        '{"schema_version":1,"status":"ok","value":1,"value":1}',
        '{"schema_version":1,"status":"ok","value":NaN}',
        '{"schema_version":1,"status":"ok","value":Infinity}',
    ],
)
def test_json_type_corruption_duplicate_keys_and_nonfinite_numbers_are_not_exact(line: str) -> None:
    result = _result(1)
    observation = _observation([_call("call", 10, result, status="unknown")], [_outer("outer", line)])

    delivery = supplement_delivery(observation)["calls"][0]["supplemental_model_delivery"]

    assert delivery["status"] == "unproven"
    assert delivery["exact_matches"] == []


def test_equivalent_json_number_spelling_remains_exact() -> None:
    result = _result(1)
    line = '{"schema_version":1,"status":"ok","value":1.0}'
    observation = _observation([_call("call", 10, result, status="unknown")], [_outer("outer", line)])

    delivery = supplement_delivery(observation)["calls"][0]["supplemental_model_delivery"]

    assert delivery["status"] == "full_exact"


def test_equivalent_number_candidates_at_one_output_location_remain_ambiguous() -> None:
    integer_result, float_result = _result(1), _result(1.0)
    line = json.dumps(integer_result["structuredContent"], separators=(",", ":"))
    observation = _observation(
        [
            _call("integer", 10, integer_result, status="unknown"),
            _call("float", 11, float_result, status="unknown"),
        ],
        [_outer("outer", line)],
    )

    supplement = supplement_delivery(observation)

    assert [call["supplemental_model_delivery"]["status"] for call in supplement["calls"]] == [
        "ambiguous_exact",
        "ambiguous_exact",
    ]


def test_pretty_printed_whole_json_block_remains_exact() -> None:
    result = _result(1)
    pretty = json.dumps(result, ensure_ascii=False, indent=2)
    observation = _observation(
        [_call("call", 10, result, status="full_exact")],
        [_outer("outer", pretty)],
    )

    delivery = supplement_delivery(observation)["calls"][0]["supplemental_model_delivery"]

    assert delivery["status"] == "full_exact"
    assert delivery["exact_matches"] == [
        {
            "output_ref": "outer:outer:line:50:block:0",
            "call_id": "outer",
            "output_line": 50,
            "block_index": 0,
            "line_index": None,
            "line_number": None,
            "start_byte": 0,
            "end_byte": len(pretty.encode("utf-8")),
            "match": "result_json_block",
            "candidate_sha256": delivery["exact_matches"][0]["candidate_sha256"],
            "block_warning_present": False,
            "line_truncation": "not_applicable",
        }
    ]


def test_identical_native_invocations_remain_ambiguous() -> None:
    result = _result(1)
    line = json.dumps(result["structuredContent"], separators=(",", ":"))
    observation = _observation(
        [
            _call("first", 10, result, status="ambiguous_exact"),
            _call("second", 11, deepcopy(result), status="ambiguous_exact"),
        ],
        [_outer("outer", line)],
    )

    supplement = supplement_delivery(observation)

    assert [call["supplemental_model_delivery"]["status"] for call in supplement["calls"]] == [
        "ambiguous_exact",
        "ambiguous_exact",
    ]
    assert all(call["original_status"] == "ambiguous_exact" for call in supplement["calls"])


@pytest.mark.parametrize(
    ("run_id", "expected"),
    [
        (
            "run-17",
            {46: "full_exact", 47: "unproven_clipped", 48: "full_exact", 56: "full_exact"},
        ),
        (
            "run-20",
            {30: "ambiguous_exact", 37: "ambiguous_exact"},
        ),
        (
            "run-21",
            {
                32: "full_exact",
                39: "full_exact",
                40: "full_exact",
                47: "full_exact",
                54: "unproven_clipped",
                55: "full_exact",
                56: "full_exact",
            },
        ),
    ],
)
def test_retained_delivery_matrix(run_id: str, expected: dict[int, str]) -> None:
    wrapped = json.loads((RUN_ROOT / run_id / "observation.json").read_text(encoding="utf-8"))
    observation = wrapped["observation"]
    unchanged = deepcopy(observation)

    supplement = supplement_delivery(observation)
    calls = _by_line(supplement)

    assert observation == unchanged
    assert {line: calls[line]["supplemental_model_delivery"]["status"] for line in expected} == expected
    original_by_line = {
        call["line"]: call["model_delivery"]["status"] for call in observation["mcp_calls"]
    }
    assert all(calls[line]["original_status"] == original_by_line[line] for line in expected)
    assert supplement["source"]["run_id"] == run_id
    assert supplement["kind"] == "supplemental_delivery_interpretation"
