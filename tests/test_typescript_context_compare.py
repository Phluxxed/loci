"""Model-free checks for the matched v3 A/B comparison runner."""

from __future__ import annotations

import copy
import hashlib
import json
from contextlib import contextmanager
from pathlib import Path

import pytest

from benchmarks.typescript_context_compare import (
    AB_ARM_ORDERS,
    ARM_MODULES,
    EXPECTED_RUNS,
    TRANSPORT_MODE_IDS,
    _retain_catalog,
    _validate_expansion_transport_proof,
    _validate_transport_proof,
    _manifest,
    _run_attempt,
    attempt_id,
    planned_attempts,
)
from benchmarks.typescript_context_baseline_v3 import measure, save
from benchmarks.typescript_context_corpus import load_corpus, materialize_snapshot


def _controls_and_corpus() -> tuple[dict, dict]:
    corpus = {
        "version": "typescript-context-v3",
        "_root": "/tmp/typescript-context-v3",
        "cases": [{"id": f"case_{n:02d}", "snapshot": "snapshot"} for n in range(17)],
    }
    controls = {
        "corpus_version": "typescript-context-v3",
        "corpus_sha256": "0" * 64,
        "case_ids": [case["id"] for case in corpus["cases"]],
        "arms": {"A": "current", "B": "expansion", "C": "future"},
        "staged_schedule": {"AB_arm_orders": [list(order) for order in AB_ARM_ORDERS],
                            "AB_runs": EXPECTED_RUNS},
    }
    return corpus, controls


def test_attempt_identity_is_arm_specific_and_bounded() -> None:
    assert attempt_id("imported_interface", 1, "A") == "imported_interface-r1-A"
    assert attempt_id("imported_interface", 1, "B") == "imported_interface-r1-B"
    with pytest.raises(ValueError):
        attempt_id("case", 4, "A")
    with pytest.raises(ValueError):
        attempt_id("case", 1, "C")


def test_both_arms_launch_the_same_adapter_and_select_by_run_identity() -> None:
    assert ARM_MODULES["A"] == "benchmarks.typescript_context_expansion_tools"
    assert ARM_MODULES["B"] == ARM_MODULES["A"]


def test_planned_attempts_are_exactly_102_in_case_major_staged_order() -> None:
    corpus, controls = _controls_and_corpus()
    plan = planned_attempts(corpus, controls)

    assert len(plan) == 102
    assert plan[:6] == [
        {"attempt_id": "case_00-r1-A", "case_id": "case_00", "snapshot": "snapshot", "repetition": 1, "arm": "A"},
        {"attempt_id": "case_00-r1-B", "case_id": "case_00", "snapshot": "snapshot", "repetition": 1, "arm": "B"},
        {"attempt_id": "case_00-r2-B", "case_id": "case_00", "snapshot": "snapshot", "repetition": 2, "arm": "B"},
        {"attempt_id": "case_00-r2-A", "case_id": "case_00", "snapshot": "snapshot", "repetition": 2, "arm": "A"},
        {"attempt_id": "case_00-r3-A", "case_id": "case_00", "snapshot": "snapshot", "repetition": 3, "arm": "A"},
        {"attempt_id": "case_00-r3-B", "case_id": "case_00", "snapshot": "snapshot", "repetition": 3, "arm": "B"},
    ]
    assert {item["arm"] for item in plan} == {"A", "B"}
    assert len({item["attempt_id"] for item in plan}) == len(plan)


def test_schedule_rejects_mutation_or_case_order_drift() -> None:
    corpus, controls = _controls_and_corpus()
    changed = copy.deepcopy(controls)
    changed["staged_schedule"]["AB_arm_orders"][0] = ["B", "B"]
    with pytest.raises(ValueError, match="arm order"):
        planned_attempts(corpus, changed)

    changed = copy.deepcopy(controls)
    changed["case_ids"][0], changed["case_ids"][1] = changed["case_ids"][1], changed["case_ids"][0]
    with pytest.raises(ValueError, match="case order"):
        planned_attempts(corpus, changed)


def test_manifest_pins_catalog_runner_transport_and_source_provenance(tmp_path: Path) -> None:
    corpus, controls = _controls_and_corpus()
    corpus_root = tmp_path / "corpus"
    corpus_root.mkdir()
    (corpus_root / "corpus.json").write_text("{}", encoding="utf-8")
    (corpus_root / "comparison-controls.json").write_text("{}", encoding="utf-8")
    (corpus_root / "transport-verification.json").write_text("{}", encoding="utf-8")
    corpus["_root"] = str(corpus_root)
    controls["corpus_sha256"] = hashlib.sha256((corpus_root / "corpus.json").read_bytes()).hexdigest()
    catalog = tmp_path / "catalog.json"
    catalog.write_text("{}", encoding="utf-8")
    freeze = {
        "version": "typescript-context-existing-v1-freeze",
        "freeze_commit": "f" * 40,
        "candidate_source_tree": "c" * 40,
        "candidate_diff_sha256": "d" * 64,
        "current_commit": "f" * 40,
        "current_source_tree": "c" * 40,
        "baseline_commit": "b" * 40,
        "baseline_source_tree": "a" * 40,
        "harness_files": {"benchmarks/typescript_context_compare.py": "e" * 64},
        "corpus_files": {"corpus.json": "1" * 64},
    }
    manifest = _manifest(corpus, controls, catalog, freeze, "2" * 64,
                         [{"attempt_id": "case_00-r1-A"}])
    assert manifest["planned_runs"] == 1
    assert manifest["canonical_tool_schemas_sha256"] == "2" * 64
    assert manifest["freeze"]["candidate_source_tree"] == "c" * 40
    assert manifest["catalog_sha256"] == hashlib.sha256(b"{}").hexdigest()


def test_retain_catalog_pins_exact_bytes_and_rejects_resume_drift(tmp_path: Path) -> None:
    catalog = tmp_path / "fresh-catalog.json"
    catalog.write_bytes(b'{"models":[{"slug":"gpt-5.6-luna"}]}\n')
    output = tmp_path / "comparison"

    retained = _retain_catalog(catalog, output, resume=False)
    assert retained == output / "model-catalog.json"
    assert retained.read_bytes() == catalog.read_bytes()
    assert _retain_catalog(catalog, output, resume=True) == retained

    catalog.write_bytes(b'{"models":[{"slug":"gpt-5.6-luna","revision":2}]}\n')
    with pytest.raises(ValueError, match="catalog"):
        _retain_catalog(catalog, output, resume=True)


def test_transport_proof_checks_frozen_ten_modes_and_current_script() -> None:
    root = Path(__file__).parents[1]
    corpus = load_corpus(root / "benchmarks" / "corpora" / "typescript-context-v3")
    proof_path = Path(corpus["_root"]) / "transport-verification.json"
    proof = json.loads(proof_path.read_text(encoding="utf-8"))
    catalog = root / "benchmarks" / "results" / "typescript-context-baseline-v2" / "model-catalog.json"

    assert _validate_transport_proof(proof, corpus, catalog) == proof["canonical_tool_schemas_sha256"]
    assert {mode["mode"] for mode in proof["modes"]} == TRANSPORT_MODE_IDS

    changed = copy.deepcopy(proof)
    changed["modes"][0]["mode"] = "unexpected"
    with pytest.raises(ValueError, match="fixed ten modes"):
        _validate_transport_proof(changed, corpus, catalog)


def test_expansion_transport_proof_requires_one_complete_b_get() -> None:
    schema = "a" * 64
    proof = {
        "schema_version": 1,
        "probe": "typescript-context-expanded-get-transport",
        "arm": "B",
        "case_id": "imported_interface",
        "model": "gpt-5.6-luna",
        "reasoning_effort": "high",
        "canonical_tool_schemas_sha256": schema,
        "observation": {
            "output_verified": True,
            "request_count": 2,
            "adapter_attempts": 1,
            "adapter_deliveries": 1,
            "observed_accounting": {"complete": True, "tool_call_count": 1},
        },
    }
    _validate_expansion_transport_proof(proof, schema)
    proof["observation"]["adapter_deliveries"] = 0
    with pytest.raises(ValueError, match="incomplete"):
        _validate_expansion_transport_proof(proof, schema)


def test_subprocess_or_audit_failure_is_saved_without_retry(tmp_path: Path) -> None:
    corpus = load_corpus(Path(__file__).parents[1] / "benchmarks" / "corpora" / "typescript-context-v3")
    controls = json.loads((Path(corpus["_root"]) / "comparison-controls.json").read_text(encoding="utf-8"))
    plan = {
        "attempt_id": "imported_interface-r1-A",
        "case_id": "imported_interface",
        "snapshot": "imported_interface",
        "repetition": 1,
        "arm": "A",
    }
    catalog = Path(__file__).parents[1] / "benchmarks" / "results" / "typescript-context-baseline-v2" / "model-catalog.json"
    freeze = {
        "freeze_commit": "f" * 40,
        "candidate_source_tree": "c" * 40,
        "candidate_diff_sha256": "d" * 64,
        "current_commit": "f" * 40,
        "current_source_tree": "c" * 40,
    }

    class FakeStore:
        def load(self, _repo):
            return {"symbols": [], "graph": {}}

    class FakeService:
        def __init__(self):
            self.calls = 0

        def index_repo(self, _repo, incremental=False):
            self.calls += 1

        def get_store(self):
            return FakeStore()

    fake_service = FakeService()

    @contextmanager
    def isolated_store(_path):
        yield

    execute_calls = []

    def inspect_fails(*_args):
        raise RuntimeError("audit unavailable")

    def execute_must_not_run(*_args):
        execute_calls.append(True)
        raise AssertionError("a failed audit must not retry or launch a provider attempt")

    result = _run_attempt(
        corpus=corpus,
        controls=controls,
        plan=plan,
        output=tmp_path,
        catalog=catalog,
        expected_schema_hash="0" * 64,
        freeze=freeze,
        inspect_request=inspect_fails,
        settings=lambda *_args: {},
        launch_args=lambda *_args: [],
        child_environment=lambda *_args: {},
        execute=execute_must_not_run,
        save=save,
        materialize_snapshot=materialize_snapshot,
        isolated_store=isolated_store,
        service=fake_service,
        measure=measure,
    )

    saved = json.loads((tmp_path / plan["attempt_id"] / "result.json").read_text(encoding="utf-8"))
    failures = saved["baseline"]["failures"]
    assert result["attempt_id"] == plan["attempt_id"]
    assert any(failure["category"] == "request_audit" for failure in failures)
    assert execute_calls == []
    assert saved["measurement"]["task_correct"] is False
    assert saved["provenance"]["arm"] == "A"
