"""Reconcile the retained primary and delegate calls without inventing trials."""
from pathlib import Path
import hashlib
import json

from benchmarks.ordinary_adoption_normal import observe_normal_rollout, normal_evidence_registry

REPO = Path(__file__).resolve().parents[3]
OUT = Path(__file__).resolve().parent
CASES = [
    {
        "name": "primary",
        "rollout": "/Users/brummerv/.codex/sessions/2026/09/14/rollout-2026-09-14T14-07-34-01a09e19-5048-79d3-96dd-697eda8a4ac8.jsonl",
        "thread_id": "01a09e19-5048-79d3-96dd-697eda8a4ac8",
        "turn_id": "01a09f76-8dc6-7cc1-a0c3-4974e6a44eed",
        "model": "gpt-6-astra",
        "effort": "ultra",
        "ids": {"exec-c8514d58-90b1-492d-95f2-a01ad023396e", "exec-8f209bbf-2470-4e5a-a363-2d8de814b9d1"},
    },
    {
        "name": "delegate",
        "rollout": "/Users/brummerv/.codex/sessions/2026/09/14/rollout-2026-09-14T20-32-22-01a09f79-9b7f-7bf3-aa2a-7ac3fbce62da.jsonl",
        "thread_id": "01a09f79-9b7f-7bf3-aa2a-7ac3fbce62da",
        "turn_id": "01a09f79-9c55-7470-9216-b87646e6b870",
        "model": "gpt-5.6-terra",
        "effort": "high",
        "ids": {"exec-673098ac-c42f-414d-b1e1-9dd2b47e6aaf", "exec-872cd197-eb3d-4363-80c0-f5fe49b99d09", "exec-b1d9dd11-661b-44ae-a6b5-9a839b90c7b2", "exec-ca6bba60-f567-43a7-938c-12970e783897"},
    },
    {
        "name": "delegate-once",
        "rollout": "/Users/brummerv/.codex/sessions/2026/09/14/rollout-2026-09-14T20-52-21-01a09f8b-e916-7661-a38e-22934f951bcc.jsonl",
        "thread_id": "01a09f8b-e916-7661-a38e-22934f951bcc",
        "turn_id": "01a09f8b-ea05-72e2-adbc-30d70d905a98",
        "model": "gpt-5.6-terra",
        "effort": "high",
        "ids": {"exec-5548e86d-1dc2-4da0-ae5f-dc880c257727", "exec-1e9bd455-7f9e-41d6-832b-3f85ba2f3c49"},
    },
]


def main():
    summaries = []
    for case in CASES:
        metadata = {
            "run_id": "functional-W1.6.3-" + case["name"],
            "purpose": "capability_probe",
            "thread_id": case["thread_id"],
            "turn_id": case["turn_id"],
            "target_repo": str(REPO),
            "requested_model": case["model"],
            "requested_effort": case["effort"],
        }
        result = observe_normal_rollout(case["rollout"], metadata)
        observed = result["observation"]
        assert not observed["native_identity"]["condition_deviations"]
        calls = [c for c in observed["mcp_calls"] if c["item_id"] in case["ids"]]
        assert len(calls) == len(case["ids"])
        readouts = [c for c in result["normal_calls"] if c["item_id"] in case["ids"]]
        assert len(readouts) == len(calls)
        if case["name"] != "delegate":
            assert all(c["model_delivery"]["status"] == "full_exact" for c in calls)
            assert all(c["actual_host_proof_status"] == "validated" for c in readouts)
            assert any(c["relationships"]["semantic_relationship_count"] > 0 for c in readouts)
        source_checks = []
        for call in calls:
            packet = call["result"]["structuredContent"]
            sources = packet.get("sources", [packet["source"]] if "source" in packet else [])
            for source in sources:
                raw = (REPO / source["file"]).read_bytes()
                assert hashlib.sha256(raw).hexdigest() == source["content_hash"]
                assert raw[source["start_byte"]:source["end_byte"]].decode("utf-8") == source["content"]
            source_checks.append({"item_id": call["item_id"], "source_records_verified": len(sources)})
        refs = {m["output_ref"] for c in calls for m in c["model_delivery"].get("matches", [])}
        receipt = {
            "schema_version": 1,
            "kind": "functional_native_selected_calls",
            "adapter_version": result["adapter_version"],
            "native_adapter_version": result["native_adapter_version"],
            "rollout_path_local": case["rollout"],
            "native_identity": observed["native_identity"],
            "observed_turn_boundary": observed["outcome"]["boundary"],
            "reserved_row": False,
            "per_case_provider_cost": "not_applicable_functional_acceptance",
            "whole_turn_cost_excluded": True,
            "selected_mcp_calls": calls,
            "selected_normal_readout": readouts,
            "source_checks": source_checks,
            "matched_model_output_blocks": [b for b in observed["model_output_blocks"] if b.get("output_ref") in refs],
            "evidence_registry": {k: v for k, v in normal_evidence_registry(result).items() if k in case["ids"]},
            "limitations": ["No completed primary boundary is invented.", "This directed functional acceptance is outside all ordinary/post denominators and does not prove unprimed adoption or answer benefit."] + (["The first delegate made an extra retrieve/read pair; all four calls and attribution limits are retained."] if case["name"] == "delegate" else []),
        }
        path = OUT / (case["name"] + "-native-check.json")
        path.write_text(json.dumps(receipt, indent=2) + "\n")
        summaries.append({
            "host": case["name"], "artifact": str(path),
            "calls": [{"tool": c["tool"], "item_id": c["item_id"], "delivery": c["model_delivery"]["status"], "bytes": c["canonical_result_json_bytes"]} for c in calls],
            "normal_readouts": [{"item_id": c["item_id"], "host_proof": c["actual_host_proof_status"], "relationships": c["relationships"]["semantic_relationship_count"], "byte_accounting": c["byte_accounting"]} for c in readouts],
            "source_checks": "all passed", "turn_boundary": observed["outcome"]["boundary"],
        })
    print(json.dumps({"operation": "verify_actual_host_acceptance", "status": "complete", "hosts": summaries}))


if __name__ == "__main__":
    main()
