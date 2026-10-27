"""Read archived R1 evidence and rerun frozen oracles; never launch a model."""
from __future__ import annotations

import copy
import json
from pathlib import Path

from benchmarks.complete_work import r0, r1
from benchmarks.complete_work.accounting import summarize_native
from benchmarks.complete_work.evaluate import verify_snapshot, write_json


ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
INDEX = ROOT / "execution-index.json"
COMPARE = ("run_id", "source_identity", "oracle_sha256", "changes",
           "unexpected_changes", "correct", "oracle_stdout", "oracle_stderr")


def inventory(paths):
    return {str(path): r0.digest(path) for path in sorted(set(paths))}


def main():
    index = json.loads(INDEX.read_text())
    freeze_path = ROOT / "freeze.json"
    frozen = r1.read_freeze(freeze_path, runtime=False)
    assert frozen["freeze_sha256"] == index["freeze_sha256"]
    assert frozen["model"] == "gpt-6.1-terra" and frozen["effort"] == "max"
    protected = [INDEX, freeze_path]
    protected += [p for p in (ROOT / "archived-runs").rglob("*") if p.is_file()]
    protected += [Path(t["oracle"]) for t in frozen["tasks"]]
    before_inventory = inventory(protected)
    write_json(OUT / "protected-before-sha256.json", before_inventory)
    records = []
    all_threads = []
    all_sessions = []
    for entry in index["runs"]:
        run_id = entry["run_id"]
        out = OUT / run_id
        out.mkdir(exist_ok=False)
        observer = Path(entry["archive"]) / "observer"
        original_config = observer / "run.json"
        original = json.loads(original_config.read_text())
        receipts = {}
        hashes = {}
        for name in ("evaluation", "qualification", "replay"):
            path = Path(entry[name + "_result"])
            digest = r0.digest(path)
            assert digest == entry[name + "_result_sha256"], (run_id, name, "receipt digest")
            hashes[name] = {"path": str(path), "sha256": digest}
            receipts[name] = json.loads(path.read_text())
        evaluation, qualification = receipts["evaluation"], receipts["qualification"]
        assert evaluation == entry["evaluation"], (run_id, "index evaluation mismatch")
        assert r0.digest(original_config) == qualification["config_sha256"]
        assert original["run_id"] == qualification["run_id"] == run_id
        assert qualification["status"] == "qualified_observations" and not qualification["errors"]
        assert original["permission_overrides"] == {}
        assert original["conditions"] == qualification["conditions"]
        assert original["conditions"]["model"] == "gpt-6.1-terra"
        assert original["conditions"]["effort"] == "max"
        assert qualification["native_config_sha256"] == original["native_config_sha256"]
        assert original["conditions"]["freeze_sha256"] == frozen["freeze_sha256"]
        assert Path(original["r1"]["freeze"]) == freeze_path
        task = next(t for t in frozen["tasks"] if t["id"] == original["r1"]["task"])
        assert r0.digest(Path(task["oracle"])) == task["oracle_sha256"]
        assert r0.digest(observer / "prompt.txt") == task["prompt_sha256"]
        assert (observer / "prompt.txt").read_text() == task["prompt"]
        source = {}
        for phase, path, expected in (
            ("before", observer / "source-before.json", qualification["source_before"]),
            ("after", observer / "qualification/source-after.json", qualification["source_after"]),
        ):
            snapshot = json.loads(path.read_text())
            verify_snapshot(snapshot, expected)
            if phase == "before":
                assert expected == original["source_identity"] == task["source_identity"]
            blob_hashes = {}
            byte_total = 0
            for name, digest in snapshot["files"].items():
                blob = observer / "source-history/blobs" / digest
                assert r0.digest(blob) == digest, (run_id, phase, name, "blob digest")
                blob_hashes[name] = digest
                byte_total += blob.stat().st_size
            assert byte_total == snapshot["content_bytes"]
            source[phase] = {"snapshot_path": str(path), "snapshot_sha256": r0.digest(path),
                             "source_identity": snapshot["sha256"], "files": blob_hashes,
                             "content_bytes": byte_total}
        trace = observer / "qualification/native-rollout.jsonl"
        trace_sha = r0.digest(trace)
        assert trace_sha == qualification["native_trace_sha256"]
        thread = qualification["thread_id"]
        assert thread == evaluation["thread_id"] == entry["execution"]["thread_id"]
        execution = json.loads((observer / "execution.json").read_text())
        assert execution == entry["execution"]
        assert execution["status"] == "closed" and execution["exit_code"] == 0
        events = [json.loads(line) for line in (observer / "exec.jsonl").read_text().splitlines()]
        starts = [x["thread_id"] for x in events if x.get("type") == "thread.started"]
        assert starts == [thread]
        # This parser performs readback only, not r0.qualify or measurement requalification.
        accounting = summarize_native(trace, thread)
        bound_accounting = copy.deepcopy(accounting)
        bound_accounting["native_provenance"]["rollout_path"] = qualification["accounting"]["native_provenance"]["rollout_path"]
        assert bound_accounting == qualification["accounting"], (run_id, "raw readback mismatch")
        assert evaluation["accounting"] == qualification["accounting"]
        assert accounting["usage_status"] == "known" and not accounting["native_errors"]
        assert not accounting["capture_errors"] and not accounting["usage_errors"]
        provenance = accounting["native_provenance"]
        assert provenance["session_id"] == thread
        assert provenance["cwd"] == original["workspace"]
        assert provenance["source"] == "exec" and provenance["thread_source"] == "user"
        contexts = accounting["turn_contexts"]
        assert contexts
        for context in contexts:
            assert context["model"] == "gpt-6.1-terra" and context["effort"] == "max"
            assert context["cwd"] == original["workspace"]
            assert {key: context.get(key) for key in r0.PROTECTION_FIELDS} == original["conditions"]["native_protection"]
        failed_native_items = []
        failed_outer_calls = []
        for stage in accounting["stages"]:
            assert stage["usage_status"] == "known" and stage["outcome"] == "completed"
            for item in stage["items"]:
                if item["type"] != "commandExecution" and (item.get("status") in ("failed", "errored", "aborted") or item.get("error")):
                    failed_native_items.append(item)
            failed_outer_calls += [call for call in stage["raw_tool_calls"] if call.get("status") not in (None, "completed")]
        assert not failed_native_items and not failed_outer_calls
        all_threads.append(thread)
        all_sessions.append(provenance["session_id"])
        remapped = copy.deepcopy(original)
        remapped["observer"] = str(observer)
        remapped_config = out / "run-remapped.json"
        write_json(remapped_config, remapped)
        differences = {key for key in original.keys() | remapped.keys() if original.get(key) != remapped.get(key)}
        assert differences == {"observer"}
        destination = out / "replay"
        invocation = {
            "call": "benchmarks.complete_work.r1.replay(config, destination)",
            "config": str(remapped_config), "destination": str(destination),
            "original_config": str(original_config), "original_config_sha256": r0.digest(original_config),
            "qualification_bound_config_sha256": qualification["config_sha256"],
            "remapped_config_sha256": r0.digest(remapped_config),
            "exact_remap": {"observer": {"from": original["observer"], "to": str(observer)}},
            "unchanged_other_top_level_fields": sorted(set(original) - {"observer"}),
            "frozen_evaluator": {"path": task["oracle"], "sha256": task["oracle_sha256"]},
            "freeze": {"path": str(freeze_path), "file_sha256": r0.digest(freeze_path),
                       "freeze_sha256": frozen["freeze_sha256"], "runtime": False},
        }
        write_json(out / "invocation.json", invocation)
        replay = r1.replay(remapped_config, destination)
        disagreements = []
        for name, reference in (("archived_evaluation", evaluation), ("index_evaluation", entry["evaluation"]),
                                ("archived_replay", receipts["replay"])):
            for field in COMPARE:
                if replay[field] != reference[field]:
                    disagreements.append({"reference": name, "field": field,
                                          "new": replay[field], "reference_value": reference[field]})
        record = {
            "run_id": run_id, "task": original["r1"]["task"], "condition": original["r1"]["condition"],
            "correct": replay["correct"], "changes": replay["changes"],
            "unexpected_changes": replay["unexpected_changes"], "source_identity": replay["source_identity"],
            "thread_id": thread, "native_session_id": provenance["session_id"],
            "native_provenance": provenance, "actual_contexts": contexts,
            "raw_trace": {"path": str(trace), "sha256": trace_sha},
            "receipt_hashes": hashes, "source_snapshots": source,
            "archived_execution_sha256": r0.digest(observer / "execution.json"),
            "archived_exec_jsonl_sha256": r0.digest(observer / "exec.jsonl"),
            "usage_status": accounting["usage_status"], "native_errors": accounting["native_errors"],
            "failed_non_shell_native_items": failed_native_items, "failed_outer_calls": failed_outer_calls,
            "failed_shell_calls_retained": accounting["operation_totals"]["failed_shell_calls"],
            "replay_invocation": str(out / "invocation.json"),
            "replay_result": str(destination / "oracle.json"),
            "replay_result_sha256": r0.digest(destination / "oracle.json"),
            "disagreements": disagreements,
        }
        write_json(out / "integrity.json", record)
        records.append(record)
    assert len(records) == 16
    assert len(set(all_threads)) == len(set(all_sessions)) == 16
    assert {r["run_id"] for r in records} == {r["run_id"] for r in frozen["schedule"]}
    after_inventory = inventory(protected)
    write_json(OUT / "protected-after-sha256.json", after_inventory)
    assert after_inventory == before_inventory, "protected original evidence changed"
    summary = {
        "status": "complete", "run_count": len(records), "correct_count": sum(r["correct"] for r in records),
        "distinct_fresh_native_threads": len(set(all_threads)), "distinct_native_session_ids": len(set(all_sessions)),
        "all_actual_model_effort": {"model": "gpt-6.1-terra", "effort": "max"},
        "all_receipt_config_trace_snapshot_hashes_valid": True,
        "all_archived_raw_accounting_matches_qualification": True,
        "all_usage_known": True, "failed_native_items_excluding_shell_attempts": 0,
        "failed_outer_calls": 0, "failed_shell_calls_retained": sum(r["failed_shell_calls_retained"] for r in records),
        "disagreements": [d for r in records for d in r["disagreements"]],
        "original_evidence_unchanged": True, "protected_file_count": len(protected),
        "protected_before_inventory_sha256": r0.digest(OUT / "protected-before-sha256.json"),
        "protected_after_inventory_sha256": r0.digest(OUT / "protected-after-sha256.json"),
        "execution_index_sha256": r0.digest(INDEX), "freeze_file_sha256": r0.digest(freeze_path),
        "freeze_sha256": frozen["freeze_sha256"],
        "replay_implementation_sha256": inventory([Path(r1.__file__), Path(r0.__file__),
            Path(r1.__file__).with_name("evaluate.py"), Path(r1.__file__).with_name("accounting.py")]),
        "script_sha256": r0.digest(Path(__file__)),
        "method": "Existing r1.replay reads archived source-history through analysis-local run manifests; only observer is remapped. Frozen oracle bytes are hash checked. Native trace readback is independently recomputed with summarize_native; qualification is not rerun.",
        "limits": [
            "Correctness is the frozen constructed-task oracle and allowed-change policy; replay does not certify broader task correctness or repair oracle limitations.",
            "Freshness is supported by distinct thread/session IDs, exec-origin provenance, parser rejection of inherited pre-turn history and forked_from_id, plus captured native events; no independent upstream session service was queried.",
            "Known usage and no native errors describe observed captured evidence, not billing completeness or invisible retries. Failed shell attempts are retained separately.",
            "runtime=False intentionally skips live native config/executable/startup/implementation checks; no measurement requalification or current environment equivalence claim is made.",
            "Replay invokes local Node frozen evaluators only. It does not launch Codex/models/MCP or read live task workspaces/source-history.",
        ],
        "runs": records,
    }
    write_json(OUT / "summary.json", summary)
    print(json.dumps({key: summary[key] for key in ("status", "run_count", "correct_count", "distinct_fresh_native_threads", "failed_shell_calls_retained", "disagreements", "original_evidence_unchanged")}))


if __name__ == "__main__":
    main()
