"""Source acquisition keeps strict proof requirements across continuations."""
from copy import deepcopy
import json
from pathlib import Path

import pytest

from benchmarks.architecture import read_index
from benchmarks.architecture_cases import (
    load_suite, prepare_snapshots, next_acquisition_query, score, score_session_proof,
)
from benchmarks.ordinary_adoption_normal import _unique_extent_bytes

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("case_id,suite", [
    ("anvil_temporal_arguments", 0), ("anvil_retrieval_limits", 0),
    ("python_loci_bundle_contract", 1),
])
def test_all_five_session_proofs_require_actual_caller_delivery(tmp_path, case_id, suite):
    artifacts = ROOT / f".scratch/r0-evaluation/results/full/artifacts/control-1-suite-{suite}"
    corpus = load_suite(ROOT / f".scratch/r0-evaluation/results/full/inputs/{suite}")
    case = next(c for c in corpus["cases"] if c["id"] == case_id)
    corpus["snapshots"] = {case["snapshot"]: corpus["snapshots"][case["snapshot"]]}
    repo = Path(prepare_snapshots(corpus, tmp_path / "fixtures")[case["snapshot"]])
    index = read_index(artifacts / f"indexes/{case['snapshot']}.json.gz")
    packets = json.loads((artifacts / f"packets/{case_id}.json").read_text())
    legacy = score(corpus, case_id, repo, index, packets)
    assert not legacy["integrity_ok"]
    complete = score_session_proof(corpus, case_id, repo, index, packets)
    assert complete["acquisition_integrity_ok"]
    audit = json.loads((ROOT / ".scratch/r04-graph-free/proof-audit.json").read_text())
    audited = next(c for c in audit["cases"] if c["case_id"] == case_id)
    for edge in audited["edges"]:
        caller = edge["caller_symbol"]
        # Remove the caller's final byte from ALL delivered coverage, including
        # support supplied by other relationships. Preserve all original edges.
        reduced = deepcopy(packets)
        for packet in reduced:
            payload = packet["structuredContent"]
            sources = [payload["source"]] if "source" in payload else payload["sources"]
            for source in sources:
                gap = caller["end_byte"] - 1
                if source["file"] == caller["file"] and source["start_byte"] < gap < source["end_byte"]:
                    source["end_byte"] = gap
                    source["content"] = source["content"].encode()[:gap - source["start_byte"]].decode()
                    source["end_line"] = max(source["start_line"], source["start_line"]
                        + source["content"].count("\n") - int(source["content"].endswith("\n")))
            payload["usage"]["evidence_bytes"] = _unique_extent_bytes(sources)
            for _ in range(16):
                size = len(json.dumps(packet, ensure_ascii=False, separators=(",", ":")).encode())
                if payload["usage"]["output_bytes"] == size:
                    break
                payload["usage"]["output_bytes"] = size
        missing = score_session_proof(corpus, case_id, repo, index, reduced)
        assert not missing["acquisition_integrity_ok"]
        assert missing["session_relationships"]["delivery_integrity_violations"]
    corrupted = deepcopy(packets)
    source = corrupted[-1]["structuredContent"].get("source")
    assert source is not None
    source["content"] = "x" + source["content"][1:]
    assert not score_session_proof(corpus, case_id, repo, index, corrupted)["acquisition_integrity_ok"]


def test_followup_policy_uses_only_observed_source_and_inventory():
    inventory = {"files": {"src/app.ts": {"size": 100}, "src/contract.ts": {"size": 20},
                           "tsconfig.json": {"size": 10}}}
    packets = [{"structuredContent": {"sources": [{"file": "src/app.ts", "start_byte": 50,
        "end_byte": 80, "content": "import {Contract} from './contract';"}]}}]
    assert next_acquisition_query(inventory, packets, ["processOrder"]) == "src/app.ts"
    assert next_acquisition_query(inventory, packets, ["processOrder", "src/app.ts"]) == "src/contract.ts"
    assert next_acquisition_query(inventory, packets, ["processOrder", "src/app.ts", "src/contract.ts"]) == "tsconfig.json"
