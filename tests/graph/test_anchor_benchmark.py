from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from benchmarks.graph_anchor_stage3 import (
    deterministic_digest,
    load_contract,
    run_benchmark,
    validate_contract,
)


def _contract() -> dict:
    return {
        "schema_version": "1",
        "approved_on": "2026-07-13",
        "corpora": {
            "first": {"alias": "first", "generic_hubs": []},
            "second": {"alias": "second", "generic_hubs": []},
        },
        "fixtures": [
            {
                "id": "F-1",
                "corpus": "first",
                "shape": "exact_attribute",
                "question": "What does query aware traversal require?",
                "expected_pages": ["query-aware.md"],
                "bridge_paths_any": [],
                "bridge_literals_any": [],
                "forbidden_paths": [],
                "required_literals": [],
                "answerable": True,
                "graph_expected": False,
            },
            {
                "id": "F-2",
                "corpus": "second",
                "shape": "cannot_answer",
                "question": "What measured result does missing evidence prove?",
                "expected_pages": [],
                "bridge_paths_any": [],
                "bridge_literals_any": [],
                "forbidden_paths": [],
                "required_literals": [],
                "answerable": False,
                "graph_expected": False,
            },
        ],
    }


def test_load_contract_validates_frozen_fields(tmp_path: Path):
    path = tmp_path / "contract.json"
    path.write_text(json.dumps(_contract()), encoding="utf-8")

    assert load_contract(path) == _contract()


@pytest.mark.parametrize(
    "mutation, message",
    [
        (lambda contract: contract.update(schema_version="2"), "schema version"),
        (lambda contract: contract.pop("corpora"), "corpora"),
        (lambda contract: contract["fixtures"][0].pop("question"), "question"),
        (lambda contract: contract["fixtures"][0].update(corpus="missing"), "corpus"),
    ],
)
def test_validate_contract_rejects_malformed_contract(mutation, message: str):
    contract = _contract()
    mutation(contract)

    with pytest.raises(ValueError, match=message):
        validate_contract(contract)


def test_run_benchmark_scores_pages_cost_and_empty_gold(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setenv("LOCI_BASE_DIR", str(tmp_path / ".codeindex"))
    first = tmp_path / "first"
    second = tmp_path / "second"
    first.mkdir()
    second.mkdir()
    (first / "query-aware.md").write_text(
        "# Query Aware Traversal\n\nUse explicit graph budgets.\n",
        encoding="utf-8",
    )
    (second / "unrelated.md").write_text(
        "# Unrelated Guide\n\nNothing relevant.\n",
        encoding="utf-8",
    )

    result = run_benchmark(
        _contract(),
        {"first": first, "second": second},
    )

    first_score = result["fixtures"][0]["score"]
    second_score = result["fixtures"][1]["score"]
    assert first_score["endpoint_hits"] == ["query-aware.md"]
    assert first_score["endpoint_recall"] == 1.0
    assert first_score["anchor_precision"] == 1.0
    assert first_score["anchor_fraction"] == 1.0
    assert first_score["response_bytes"] > 0
    assert first_score["estimated_tokens"] == (first_score["response_bytes"] + 3) // 4
    assert second_score["endpoint_recall"] is None
    assert second_score["anchor_precision"] == 1.0
    assert result["summary"]["expected_endpoint_slots"] == 1
    assert result["summary"]["expected_endpoint_hits"] == 1
    assert result["summary"]["endpoint_recall"] == 1.0
    assert result["deterministic_digest"]


def test_empty_gold_with_anchor_has_zero_precision(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setenv("LOCI_BASE_DIR", str(tmp_path / ".codeindex"))
    first = tmp_path / "first"
    second = tmp_path / "second"
    first.mkdir()
    second.mkdir()
    (first / "query-aware.md").write_text("# Query Aware Traversal\n", encoding="utf-8")
    (second / "missing-evidence.md").write_text("# Missing Evidence Result\n", encoding="utf-8")

    result = run_benchmark(
        _contract(),
        {"first": first, "second": second},
    )

    assert result["fixtures"][1]["anchors"]
    assert result["fixtures"][1]["score"]["anchor_precision"] == 0.0


def test_deterministic_digest_excludes_latency_and_absolute_roots():
    result = {
        "roots": {"first": "/tmp/one"},
        "fixtures": [{"latency_ms": 1.0, "anchors": [{"id": "a"}]}],
        "summary": {"mean_latency_ms": 1.0, "endpoint_recall": 1.0},
    }
    changed = copy.deepcopy(result)
    changed["roots"]["first"] = "/different/machine"
    changed["fixtures"][0]["latency_ms"] = 999.0
    changed["summary"]["mean_latency_ms"] = 999.0

    assert deterministic_digest(result) == deterministic_digest(changed)
