"""R0.5 observer rejects privileged requests and replays actual warm sequences."""
from argparse import Namespace
from copy import deepcopy
import json
from pathlib import Path

import pytest

from benchmarks.architecture import ROOT, run, verify
from benchmarks.architecture_cases import load_suite, prepare_snapshots, score_acquisition


def test_repeated_source_acquisition_is_archived_and_independently_replayed(tmp_path):
    args = Namespace(repo=str(ROOT), output=str(tmp_path / "repeat"),
        control_ref="2b3b60e", variant_ref="2b3b60e", control_architecture="graph-free",
        variant_architecture="graph-free", control_enrichment="on", variant_enrichment="on",
        operation="acquisition", mechanism="repeat observer contract", repeat_queries=True,
        corpus=[str(ROOT / "benchmarks/corpora/typescript-context-v3")],
        case=["imported_interface"], repetitions=1)
    assert run(args) == 0
    output = Path(args.output)
    report = json.loads((output / "result.json").read_text())
    for entry in report["runs"]:
        assert entry["repeat_capability"]
        first = json.loads((output / entry["capability"]).read_text())
        repeated = json.loads((output / entry["repeat_capability"]).read_text())
        assert first == repeated
        assert entry["phase_totals"]["repeat_retrieval"]["operations"] == 1
        assert entry["phase_totals"]["repeat_followup"]["operations"] > 0
    assert verify(output) == 0


def test_semantic_question_cannot_use_gold_or_a_later_policy_slot(tmp_path):
    corpus = load_suite(ROOT / "benchmarks/corpora/typescript-context-v3")
    case = next(c for c in corpus["cases"] if c["id"] == "imported_interface")
    corpus["cases"] = [case]
    corpus["snapshots"] = {case["snapshot"]: corpus["snapshots"][case["snapshot"]]}
    repo = Path(prepare_snapshots(corpus, tmp_path / "fixtures")[case["snapshot"]])
    trace = {"queries": [
        {"query": "processOrder", "packet_start": 0, "packet_end": 1},
        {"query": "Order", "packet_start": 1, "packet_end": 2, "operation": "semantic_context"}]}
    inventory = {"schema_version": 1, "files": {}}
    with pytest.raises(ValueError, match="frozen gold-blind policy"):
        score_acquisition(corpus, case["id"], repo, {}, [{}, {}], trace, inventory, demand=True)
    wrong_slot = deepcopy(trace)
    wrong_slot["queries"][0]["operation"] = "semantic_context"
    with pytest.raises(ValueError, match="second-slot policy"):
        score_acquisition(corpus, case["id"], repo, {}, [{}, {}], wrong_slot, inventory, demand=True)
