from __future__ import annotations

import copy
import hashlib
from pathlib import Path

import pytest

from benchmarks.typescript_context_corpus import load_controls, load_corpus
from benchmarks.typescript_context_routing_v2 import VERSION
from benchmarks.typescript_context_routing_v2_observed import RAW_PROTOCOL
from benchmarks.typescript_context_routing_v2_replay import (
    EXPECTED_RUNS,
    TOOLS_MODULE,
    _validate_current_protocol,
    _validate_provenance,
)


ROOT = Path(__file__).parents[1]
CORPUS_ROOT = ROOT / "benchmarks" / "corpora" / "typescript-context-v3"


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _provenance_fixture(tmp_path: Path) -> tuple[dict, dict, dict, dict, dict, dict, dict]:
    corpus = load_corpus(CORPUS_ROOT)
    controls = load_controls(corpus)
    case = corpus["cases"][0]
    plan = {
        "attempt_id": f"{case['id']}-r1-B",
        "case_id": case["id"],
        "snapshot": case["snapshot"],
        "repetition": 1,
        "arm": "B",
    }
    identity = {
        "task_id": case["id"],
        "repetition": 1,
        "arm": "B",
        "snapshot": case["snapshot"],
    }
    freeze = {
        "freeze_json_sha256": "freeze-digest",
        "engine": {"commit": "engine", "source_tree": "tree", "extractor_version": 25},
    }
    root = Path(corpus["_root"])
    provenance = {
        "attempt_id": plan["attempt_id"],
        "case_id": plan["case_id"],
        "snapshot": plan["snapshot"],
        "repetition": 1,
        "arm": "B",
        "adapter_module": TOOLS_MODULE,
        "corpus_sha256": _sha(root / "corpus.json"),
        "controls_sha256": _sha(root / "comparison-controls.json"),
        "snapshot_files": copy.deepcopy(corpus["snapshots"][case["snapshot"]]["files"]),
        "source": {
            "engine": copy.deepcopy(freeze["engine"]),
            "freeze_json_sha256": freeze["freeze_json_sha256"],
        },
        "routing": {"version": VERSION, "condition": "B", "capability_arm": "B"},
    }
    result = {
        "provenance": provenance,
        "attempt_id": plan["attempt_id"],
        "arm": "B",
        "routing": {},
        "identity": identity,
    }
    run = {
        "attempt_id": plan["attempt_id"],
        "case_id": plan["case_id"],
        "arm": "B",
        "repetition": 1,
    }
    raw = {"identity": identity}
    return result, provenance, raw, run, plan, freeze, corpus


def test_replay_requires_current_result_and_preserves_historical_raw_trace() -> None:
    current = {"protocol": VERSION}
    _validate_current_protocol(current, {"protocol": RAW_PROTOCOL})

    with pytest.raises(ValueError, match="measurement protocol"):
        _validate_current_protocol({"protocol": "typescript-context-routing-v1"}, {"protocol": RAW_PROTOCOL})
    with pytest.raises(ValueError, match="raw Explore trace"):
        _validate_current_protocol(current, {"protocol": VERSION})


def test_replay_rejects_source_and_provenance_tampering(tmp_path: Path) -> None:
    result, provenance, raw, run, plan, freeze, corpus = _provenance_fixture(tmp_path)

    _validate_provenance(result, provenance, raw, run, plan, corpus, freeze, tmp_path)

    tampered = copy.deepcopy(provenance)
    tampered["snapshot_files"]["consumer.ts"] = "tampered"
    with pytest.raises(ValueError, match="source provenance"):
        _validate_provenance({**result, "provenance": tampered}, tampered, raw, run, plan, corpus, freeze, tmp_path)

    tampered = copy.deepcopy(provenance)
    tampered["source"]["engine"]["commit"] = "different-engine"
    with pytest.raises(ValueError, match="source provenance"):
        _validate_provenance({**result, "provenance": tampered}, tampered, raw, run, plan, corpus, freeze, tmp_path)


def test_replay_keeps_the_fixed_batch_size_constant() -> None:
    assert EXPECTED_RUNS == 17 * 3 * 2
