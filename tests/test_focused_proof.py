"""Optional proof uses observed identities and the exact already computed slice."""
from copy import deepcopy
import json

import pytest

from benchmarks.architecture_proof import next_proof_query
from benchmarks.architecture_cases import validate_demand_packet
from loci.focused_proof import FocusedDemandSource
from loci.graph_free import GraphFreeError


def source(tmp_path, *, wide=False):
    root = tmp_path / "repo"
    root.mkdir()
    (root / "model.ts").write_text(
        "export type Base = string;\nexport type Middle = Base;\n"
        "export type Public = Middle;\n"
        "export function entry(value: Public): Public { return value; }\n")
    return root, FocusedDemandSource(tmp_path / "store", wide=wide)


def test_focused_repacking_exposes_third_hop_without_resolution(tmp_path, monkeypatch):
    root, service = source(tmp_path)
    initial = service.semantic_context(root, "entry")
    native = service.semantic_observer()["index"]
    original = deepcopy(initial)
    hidden = "model.ts::Base#type"
    assert hidden not in {node["id"] for node in initial["nodes"]}
    with pytest.raises(GraphFreeError, match="previously delivered"):
        service.proof_context(root, hidden)
    monkeypatch.setattr(service, "_resolve_slice", lambda *args: pytest.fail("new resolution"))
    packets = [{"structuredContent": initial}]
    asked = []
    for _ in range(4):
        identity = next_proof_query(packets, asked)
        if identity is None:
            break
        packet = service.proof_context(root, identity)
        validate_demand_packet(packet)
        assert packet["proof_request"]["node_id"] == identity
        assert packet["anchors"][0]["node_id"] == identity
        assert all(identity in {r["edge"]["from"], r["edge"]["to"]} for r in packet["relationships"])
        assert service.proof_observer()["parsed_paths"] == []
        packets.append({"structuredContent": packet})
        asked.append(identity)
    assert any(r["edge"]["to"] == hidden for p in packets for r in p["structuredContent"]["relationships"])
    assert service.semantic_observer()["index"] == native
    assert initial == original
    assert len(service.semantic_observer()["work"]["focused_requests"]) == len(asked)


def test_stale_or_cross_repository_retained_proof_is_refused(tmp_path):
    root, service = source(tmp_path)
    first = service.semantic_context(root, "entry")
    identity = first["anchors"][0]["node_id"]
    other = tmp_path / "other"
    other.mkdir()
    with pytest.raises(GraphFreeError, match="another repository"):
        service.proof_context(other, identity)
    (root / "model.ts").write_text((root / "model.ts").read_text() + "\n// changed\n")
    with pytest.raises(GraphFreeError, match="changed since"):
        service.proof_context(root, identity)


@pytest.mark.parametrize("wide", [False, True])
def test_focus_envelope_is_bounded_and_fully_accounted(tmp_path, wide):
    root, service = source(tmp_path, wide=wide)
    first = service.semantic_context(root, "entry")
    packet = service.proof_context(root, first["anchors"][0]["node_id"])
    validate_demand_packet(packet)
    envelope = {"content": [], "structuredContent": packet, "isError": False}
    assert packet["usage"]["output_bytes"] == len(json.dumps(
        envelope, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode())
    assert packet["usage"]["output_bytes"] <= (65536 if wide else 16384)
    assert packet["usage"]["evidence_bytes"] <= (32768 if wide else 8192)


def test_proof_scheduler_cannot_see_audit_or_gold_identities():
    packet = {"policy": "demand-semantic-v1", "anchors": [{"node_id": "a"}],
              "nodes": [{"id": "b", "kind": "type"}, {"id": "a", "kind": "function"}],
              "observer": {"symbols": [{"id": "gold-only", "kind": "type"}]}}
    envelopes = [{"structuredContent": packet}]
    assert next_proof_query(envelopes, []) == "a"
    assert next_proof_query(envelopes, ["a"]) == "b"
    assert next_proof_query(envelopes, ["a", "b"]) is None


def test_large_complete_caller_proof_is_omitted_until_wider_budget(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    (root / "model.ts").write_text("export type Contract = string;\n")
    (root / "entry.ts").write_text(
        "import { Contract } from './model';\nexport function entry(value: Contract) {\n"
        + "// body padding\n" * 700 + "return value;\n}\n")
    narrow = FocusedDemandSource(tmp_path / "narrow")
    wide = FocusedDemandSource(tmp_path / "wide", wide=True)
    for service in (narrow, wide):
        first = service.semantic_context(root, "entry")
        identity = first["anchors"][0]["node_id"]
        packet = service.proof_context(root, identity)
        validate_demand_packet(packet)
        if service is narrow:
            assert packet["relationships"] == []
            rejected = service.proof_observer()["budget_rejections"]
            assert rejected
            assert all(r["standalone_evidence_bytes"] > 8192 for r in rejected)
        else:
            assert packet["relationships"]


def test_independent_observer_replays_focused_requests_and_rejects_privilege(tmp_path):
    from pathlib import Path
    from benchmarks.architecture import acquire
    from benchmarks.architecture_cases import load_suite, prepare_snapshots, requests, score_acquisition

    corpus = load_suite(Path(__file__).resolve().parents[1] / "benchmarks/corpora/typescript-context-v3")
    case = next(c for c in corpus["cases"] if c["id"] == "imported_interface")
    corpus["cases"] = [case]
    corpus["snapshots"] = {case["snapshot"]: corpus["snapshots"][case["snapshot"]]}
    root = Path(prepare_snapshots(corpus, tmp_path / "fixtures")[case["snapshot"]])
    service = FocusedDemandSource(tmp_path / "store")
    service.index_repo(root)
    hashes = service.inventory(root)["file_hashes"]
    inventory = {"schema_version": 1, "files": {
        name: {"sha256": digest, "size": (root / name).stat().st_size} for name, digest in hashes.items()}}
    packets, trace = acquire(service, root, requests(corpus)[0], inventory, [],
                             graph_free=True, enrichment=True, demand=True, focused=True)
    index = service.semantic_observer()["index"]
    result = score_acquisition(corpus, case["id"], root, index, packets, trace, inventory,
                               demand=True, focused=True)
    assert result["acquisition_integrity_ok"]
    assert trace["focused_calls"]
    privileged = deepcopy(trace)
    next(q for q in privileged["queries"] if q.get("operation") == "focused_proof")["query"] = "hidden#gold"
    with pytest.raises(ValueError, match="frozen gold-blind policy"):
        score_acquisition(corpus, case["id"], root, index, packets, privileged, inventory,
                           demand=True, focused=True)
    corrupted = deepcopy(packets)
    proof_packet = next(p["structuredContent"] for p in corrupted
                        if p["structuredContent"].get("policy") == "focused-semantic-v1")
    proof_packet["sources"][0]["content"] = "forged"
    scored = score_acquisition(corpus, case["id"], root, index, corrupted, trace, inventory,
                               demand=True, focused=True)
    assert not scored["acquisition_integrity_ok"]
