from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path

import pytest

from benchmarks.ordinary_adoption_delivery_v3 import supplement_delivery as supplement_v3
from benchmarks.ordinary_adoption_delivery_v4 import (
    DELIVERY_ADAPTER_VERSION,
    supplement_delivery,
)


CONTROL = Path(
    "benchmarks/comparisons/ordinary-adoption-repair-binding-v1/"
    "runs/binding-repair-01/observation.json"
)


def _result(value: int | float) -> dict:
    return {
        "content": [],
        "structuredContent": {"schema_version": 1, "status": "ok", "value": value},
        "isError": False,
    }


def _call(item_id: str, line: int, result: dict) -> dict:
    compact = json.dumps(result, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    return {
        "item_id": item_id,
        "line": line,
        "server": "loci",
        "tool": "loci_retrieve",
        "result": result,
        "canonical_result_json_bytes": len(compact.encode()),
        "canonical_result_json_sha256": "a" * 64,
        "model_delivery": {"status": "unknown", "matches": []},
    }


def _observation(calls: list[dict], text: str) -> dict:
    return {
        "run": {"run_id": "test", "thread_id": "thread", "turn_id": "turn"},
        "retained_interval": {"sha256": "b" * 64},
        "mcp_calls": calls,
        "outer_code_mode": [
            {
                "call_id": "outer",
                "output_line": 50,
                "output": [{"type": "text", "text": text}],
            }
        ],
    }


def _delivery(observation: dict, index: int = 0) -> dict:
    return supplement_delivery(observation)["calls"][index]["supplemental_model_delivery"]


def test_complete_nested_result_keeps_its_span_when_wrapper_trails_off() -> None:
    result = _result(7)
    rendered = json.dumps(result, ensure_ascii=False, separators=(",", ":"))
    text = f'{{"envelope":{{"loci":{rendered},"unfinished":'
    observation = _observation([_call("native", 10, result)], text)
    unchanged = deepcopy(observation)

    supplement = supplement_delivery(observation)
    delivery = supplement["calls"][0]["supplemental_model_delivery"]
    match = delivery["nested_wrapper_matches"][0]

    assert observation == unchanged
    assert supplement["adapter_version"] == DELIVERY_ADAPTER_VERSION
    assert delivery["status"] == "full_exact"
    assert match["json_path"] == ["envelope", "loci"]
    assert match["outer_wrapper_complete"] is False
    assert json.loads(text.encode()[match["start_byte"] : match["end_byte"]]) == result
    assert supplement["nested_wrapper_scan"]["status"] == "partial"
    assert supplement["nested_wrapper_scan"]["omissions"]


@pytest.mark.parametrize(
    "render",
    [
        lambda value: '{"wrap":' + json.dumps(value, separators=(",", ":"))[:-1],
        lambda value: '{"wrap":' + json.dumps(json.dumps(value, separators=(",", ":"))),
        lambda value: (
            '{"wrap":{"content":[],"structuredContent":{"schema_version":1,'
            '"status":"ok","value":1},"isError":false,"isError":false}}'
        ),
        lambda value: (
            '{"wrap":{"content":[],"structuredContent":{"schema_version":1,'
            '"status":"ok","value":NaN},"isError":false}}'
        ),
        lambda value: '{"note":' + json.dumps("{" + json.dumps(value) + "}") + "}",
        lambda value: "Example: {\"wrap\":" + json.dumps(value, separators=(",", ":")) + "}",
    ],
)
def test_partial_encoded_duplicate_nonfinite_and_textual_fragments_are_not_matches(render) -> None:
    result = _result(1)
    delivery = _delivery(_observation([_call("native", 10, result)], render(result)))

    assert delivery["status"] == "unproven"
    assert delivery["nested_wrapper_matches"] == []


def test_equal_native_calls_share_one_nested_value_ambiguously_with_numeric_equivalence() -> None:
    integer, floating = _result(1), _result(1.0)
    text = '{"packet":' + json.dumps(integer, separators=(",", ":")) + "}"
    observation = _observation(
        [_call("integer", 10, integer), _call("floating", 11, floating)],
        text,
    )

    supplement = supplement_delivery(observation)
    deliveries = [call["supplemental_model_delivery"] for call in supplement["calls"]]

    assert [delivery["status"] for delivery in deliveries] == [
        "ambiguous_exact",
        "ambiguous_exact",
    ]
    assert all(len(delivery["nested_wrapper_matches"]) == 1 for delivery in deliveries)
    assert {
        (
            delivery["nested_wrapper_matches"][0]["start_byte"],
            delivery["nested_wrapper_matches"][0]["end_byte"],
        )
        for delivery in deliveries
    } == {(10, len(text.encode()) - 1)}


def test_line_and_nested_records_for_one_native_call_do_not_create_ambiguity() -> None:
    result = _result(1)
    rendered = json.dumps(result, separators=(",", ":"))
    text = f"[\n{rendered}\n]"

    delivery = _delivery(_observation([_call("one", 10, result)], text))

    assert delivery["status"] == "full_exact"
    assert [match["match"] for match in delivery["exact_matches"]] == [
        "result_json_line",
        "result_json_nested",
    ]
    assert {
        (match["start_byte"], match["end_byte"])
        for match in delivery["exact_matches"]
    } == {(2, 2 + len(rendered.encode()))}


def test_large_and_deep_wrappers_are_explicitly_omitted() -> None:
    result = _result(1)
    large = '{"padding":' + json.dumps("x" * 2_000_000) + ',"result":' + json.dumps(result) + "}"
    large_supplement = supplement_delivery(_observation([_call("large", 10, result)], large))

    assert large_supplement["calls"][0]["supplemental_model_delivery"]["status"] == "unproven"
    assert any(
        omission["reason"] == "block_byte_limit"
        for omission in large_supplement["nested_wrapper_scan"]["omissions"]
    )

    deep_value: object = result
    for _ in range(66):
        deep_value = {"next": deep_value}
    deep = json.dumps(deep_value, separators=(",", ":"))
    deep_supplement = supplement_delivery(_observation([_call("deep", 10, result)], deep))

    assert deep_supplement["calls"][0]["supplemental_model_delivery"]["status"] == "unproven"
    assert any(
        omission["reason"] == "depth_limit"
        for omission in deep_supplement["nested_wrapper_scan"]["omissions"]
    )


def test_retained_two_wrapper_control_reconciles_exact_adjudicated_spans() -> None:
    observation = json.loads(CONTROL.read_text(encoding="utf-8"))["observation"]
    unchanged = deepcopy(observation)
    baseline = supplement_v3(observation)

    supplement = supplement_delivery(observation)
    calls = {call["native_line"]: call for call in supplement["calls"]}

    assert observation == unchanged
    assert supplement["source"] == baseline["source"]
    assert supplement["outer_blocks"] == baseline["outer_blocks"]
    assert supplement["frozen_outcome_unchanged"] is True
    expected = {
        36: (
            "outer:call_VZh5rFt61VIhMCVMFGgd18X0:line:37:block:1",
            ["loci"],
            87,
            16268,
            "2618d9a95732ed85f7a7a025525445d60a0b26d229753516bf0fe8373ed85496",
        ),
        44: (
            "outer:call_SkmayUb3D0gdo9xVNYMJiInb:line:45:block:1",
            ["packet"],
            10,
            16175,
            "811d1c85d5fa752557303f023384297503654a5cf998ced8ebb3e39b84d0a4b7",
        ),
    }
    for native_line, (output_ref, path, start, end, emitted_hash) in expected.items():
        call = calls[native_line]
        delivery = call["supplemental_model_delivery"]
        match = delivery["nested_wrapper_matches"][0]
        assert delivery["status"] == "full_exact"
        assert (
            match["output_ref"],
            match["json_path"],
            match["start_byte"],
            match["end_byte"],
            match["emitted_value_sha256"],
        ) == (output_ref, path, start, end, emitted_hash)
        assert match["line_truncation"] == "none"
        assert match["outer_truncation_marker_outside_value"] is (native_line == 36)
        baseline_call = next(
            candidate for candidate in baseline["calls"] if candidate["native_line"] == native_line
        )
        assert call["original_model_delivery"] == baseline_call["original_model_delivery"]
        assert call["original_status"] == baseline_call["original_status"]
