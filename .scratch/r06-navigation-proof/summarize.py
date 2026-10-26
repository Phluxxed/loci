"""Read retained R0.6 JSON only; never retrieve, parse, resolve, or score source.

Run after measurement jobs finish. Default: print without writing. --write
requires all six completed result sets and writes this directory's summary.json.
R0.5's aggregation layout is retained, but its arm() cannot be reused safely:
it omits source_selection/focused_proof and substitutes zero for absent fields.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from statistics import mean

BASE = Path(__file__).resolve().parent
PAIRS = ("source-path", "demand-focused", "focused-wide")
FIRST_PHASES = {"retrieval", "followup", "continuation", "semantic_context",
                "source_selection", "focused_proof"}
CPU_FIELDS = ("user_cpu_s", "system_cpu_s", "children_user_cpu_s", "children_system_cpu_s")


def read(path):
    return json.loads(path.read_text())


def total(values):
    values = list(values)
    return sum(values) if all(isinstance(v, (int, float)) for v in values) else None


def maximum(values):
    values = list(values)
    return max(values) if values and all(isinstance(v, (int, float)) for v in values) else None


def at(value, *keys):
    for key in keys:
        if not isinstance(value, dict) or key not in value:
            return None
        value = value[key]
    return value


def cpu(resources):
    return total(resources.get(key) for key in CPU_FIELDS)


def timing(rows):
    elapsed = total(row.get("elapsed_ns") for row in rows)
    return {"operations": len(rows), "elapsed_s": elapsed / 1e9 if elapsed is not None else None,
            "cpu_s": total(cpu(row.get("resources", {})) for row in rows)}


def tree_bytes(root):
    return sum(path.stat().st_size for path in root.rglob("*") if path.is_file())


def relationships(value):
    if not isinstance(value, dict):
        return None
    keys = ("required_semantic_dependencies_total", "available_dependency_links_total",
            "delivered_dependency_links_total", "forbidden_proven_relationships")
    result = {key: value.get(key) for key in keys}
    result["delivery_integrity_violations"] = value.get("delivery_integrity_violations")
    result["requirements"] = [{key: row.get(key) for key in
                               ("index", "from", "to", "kind", "available", "delivered",
                                "from_status", "to_status")}
                              for row in value.get("required_semantic_dependencies", [])]
    return result


def case_projection(case):
    return {"case_id": case["case_id"], "source": case.get("source_coverage"),
            "packet_proof": relationships(case.get("relationships")),
            "session_proof": relationships(case.get("session_relationships")),
            "packet_integrity": case.get("integrity_ok"),
            "session_integrity": case.get("acquisition_integrity_ok"),
            "negative_cases": case.get("negative_cases"),
            "output_integrity": case.get("output_integrity"),
            "structural": case.get("structural_proof"),
            "task_answer": case.get("preserved_guarantees"),
            "efficiency": case.get("efficiency"), "acquisition": case.get("acquisition")}


def capability(cases):
    def summed(*keys):
        return total(at(case, *keys) for case in cases)
    result = {"cases": len(cases),
              "source_spans": summed("source_coverage", "covered"),
              "required_spans": summed("source_coverage", "required"),
              "complete_cases": sum(at(c, "source_coverage", "covered") is not None and
                                    at(c, "source_coverage", "covered") ==
                                    at(c, "source_coverage", "required") for c in cases),
              "anchors": summed("acquisition", "anchor_source_acquired"),
              "required_links": summed("session_relationships", "required_semantic_dependencies_total"),
              "native_available_links": summed("session_relationships", "available_dependency_links_total"),
              "packet_proof_links": summed("relationships", "delivered_dependency_links_total"),
              "strict_session_proof_links": summed("session_relationships", "delivered_dependency_links_total"),
              "forbidden_proven_claims": summed("negative_cases", "forbidden_proven_relationships"),
              "forbidden_delivered_claims": summed("negative_cases", "forbidden_delivered_relationships"),
              "packet_invalid_cases": [c["case_id"] for c in cases if c.get("integrity_ok") is False],
              "session_invalid_cases": [c["case_id"] for c in cases if c.get("acquisition_integrity_ok") is False],
              "unknown_task_answer_cases": [c["case_id"] for c in cases
                                            if at(c, "preserved_guarantees", "task_answer_correct") is None],
              "observed_correct_task_answers": sum(at(c, "preserved_guarantees", "task_answer_correct") is True for c in cases),
              "source_bytes": summed("efficiency", "source_bytes"),
              "unique_source_bytes": summed("efficiency", "unique_source_bytes"),
              "repeated_source_bytes": summed("efficiency", "repeated_source_bytes"),
              "output_bytes": summed("efficiency", "output_bytes"),
              "inventory_output_bytes": summed("efficiency", "discovery_output_bytes"),
              "total_delivered_bytes": summed("efficiency", "total_delivered_bytes"),
              "structural_claims": summed("structural_proof", "claims")}
    for label, key in (("packet", "relationships"), ("session", "session_relationships")):
        rows = [at(c, key, "delivery_integrity_violations") for c in cases]
        result[label + "_claim_integrity_violations"] = total(len(r) if isinstance(r, list) else None for r in rows)
    result["missing_or_unrecorded_metrics"] = [k for k, value in result.items() if value is None]
    return result


def fingerprint(cases):
    """Compare capabilities, not timing, cache metadata, output size, or paths."""
    return {c["case_id"]: {key: value for key, value in case_projection(c).items()
                           if key not in {"efficiency", "acquisition"}} for c in cases}


def equality(left, right):
    keys = set(left) | set(right)
    mismatches = sorted(key for key in keys if left.get(key) != right.get(key))
    return {"equal": not mismatches, "different_cases": mismatches,
            "cases_compared": len(keys)}


def semantic_receipts(rows):
    work_rows = [row for row in rows if row["phase"].removeprefix("repeat_") in {"semantic_context", "focused_proof"}]
    receipts = []
    for row in work_rows:
        work = row.get("work")
        if work is None:
            receipts.append({"phase": row["phase"], "case_id": row.get("case_id"), "work": None})
            continue
        keys = ("cache_hit", "cache_kind", "bytes_discovered", "bytes_parsed", "bytes_controls",
                "bytes_rust_snapshot", "bytes_snapshot_parsed", "semantic_calls", "native_resolution_calls",
                "retained_raw_bytes", "retained_native_index_proxy_bytes", "cache_serialized_proxy_bytes",
                "parsed_paths", "focused_node_id", "proof_failures", "budget_rejections", "omissions")
        receipts.append({"phase": row["phase"], "case_id": row.get("case_id"),
                         "query": row.get("query"), "work": {key: work.get(key) for key in keys}})
    focused = [row for row in rows if row["phase"].removeprefix("repeat_") == "focused_proof"]
    rejections = [{"phase": row["phase"], "case_id": row.get("case_id"),
                   "query": row.get("query"), **rejection}
                  for row in work_rows for rejection in row.get("work", {}).get("budget_rejections", [])]
    result = {"calls": len(work_rows), "focused": timing(focused), "receipts": receipts,
              "budget_rejection_receipts": rejections,
              "budget_rejection_receipts_recorded": len(rejections),
              "rows_without_budget_rejection_field": sum("budget_rejections" not in row.get("work", {}) for row in work_rows),
              "budget_rejection_qualification": "Absent fields mean no rejection receipt recorded; not an inferred zero-size proof."}
    for key in ("retained_raw_bytes", "retained_native_index_proxy_bytes", "cache_serialized_proxy_bytes"):
        present = [row["work"][key] for row in work_rows if key in row.get("work", {})]
        result["max_" + key] = maximum(present)
        result[key + "_rows_recorded"] = len(present)
    return result


def language_groups(root):
    result = {}
    for corpus_path in sorted((root / "inputs").glob("*/corpus.json")):
        for case in read(corpus_path)["cases"]:
            result[case["id"]] = case.get("language", "typescript")
    return result


def summarize_arm(root, result, arm_name):
    repetitions = []
    languages = language_groups(root)
    for repetition in sorted({r["repetition"] for r in result["runs"]}):
        runs = [r for r in result["runs"] if r["arm"] == arm_name and r["repetition"] == repetition]
        workers = [read(root / "artifacts" / run["id"] / "worker.json") for run in runs]
        rows = [row for worker in workers for row in worker["phases"]]
        first = [case for run in runs for case in read(root / run["capability"])]
        repeated = [case for run in runs for case in read(root / run["repeat_capability"])]
        setup = [row for row in result["setup"] if row["run_id"] == f"{arm_name}-{repetition}"
                 or row["run_id"].startswith(f"{arm_name}-{repetition}-")]
        observers = [row for row in result.get("observer_phases", [])
                     if row["run_id"] in {run["id"] for run in runs}]
        first_rows = [row for row in rows if row["phase"] in FIRST_PHASES]
        repeat_rows = [row for row in rows if row["phase"].startswith("repeat_")]
        provenance = {trial: [{"case_id": case["case_id"], **query["navigation"]}
                              for case in cases for query in case["acquisition"]["queries"] if "navigation" in query]
                      for trial, cases in (("first", first), ("repeat", repeated))}
        source_selection = {trial: timing([row for row in trial_rows if row["phase"].removeprefix("repeat_") == "source_selection"])
                            for trial, trial_rows in (("first", first_rows), ("repeat", repeat_rows))}
        selection_work = {}
        for trial, trial_rows in (("first", first_rows), ("repeat", repeat_rows)):
            receipts = [row["work"] for row in trial_rows if row["phase"].removeprefix("repeat_") == "source_selection" and "work" in row]
            selection_work[trial] = {key: total(receipt.get(key) for receipt in receipts)
                                     for key in sorted({key for receipt in receipts for key in receipt})}
        fingerprints = {"first": fingerprint(first), "repeat": fingerprint(repeated)}
        repetitions.append({"repetition": repetition, "first": capability(first), "repeat": capability(repeated),
            "first_repeat_capabilities": equality(fingerprints["first"], fingerprints["repeat"]),
            "first_operations": timing(first_rows), "repeat_operations": timing(repeat_rows),
            "index": timing([r for r in rows if r["phase"] == "indexing"]),
            "runtime_setup": timing([r for r in rows if r["phase"] == "runtime_setup"]),
            "setup": timing(setup), "observer_validation": timing(observers),
            "observer_first": timing([r for r in observers if r.get("trial") == "first"]),
            "observer_repeat": timing([r for r in observers if r.get("trial") == "repeat"]),
            "worker_elapsed_s": total(r["execution"]["elapsed_ns"] / 1e9 for r in runs),
            "worker_cpu_s": total(cpu(w.get("process_resources", {})) for w in workers),
            "peak_rss_bytes": maximum(at(w, "process_resources", "peak_rss_bytes") for w in workers),
            "prequestion_peak_rss_bytes": maximum(at(w, "resources_before_questions", "peak_rss_bytes") for w in workers),
            "prequestion_semantic_modules": [w.get("semantic_modules_before_questions") for w in workers],
            "runtime_store_bytes": total(r.get("store_bytes") for r in runs),
            "external_cache_bytes": total(r.get("cache_bytes") for r in runs),
            "phase_totals": {phase: timing([row for row in rows if row["phase"] == phase]) for phase in sorted({r["phase"] for r in rows})},
            "semantic_first": semantic_receipts(first_rows), "semantic_repeat": semantic_receipts(repeat_rows),
            "source_selection": source_selection, "source_selection_work_totals": selection_work,
            "path_query_provenance": provenance,
            "language_groups": {language: capability([c for c in first if languages.get(c["case_id"], "unknown") == language])
                                for language in sorted({languages.get(c["case_id"], "unknown") for c in first})},
            "cases": [case_projection(c) for c in first], "repeat_cases": [case_projection(c) for c in repeated],
            "capability_fingerprints": fingerprints})
    scalar_paths = [(key,) for key in ("worker_elapsed_s", "worker_cpu_s", "peak_rss_bytes", "runtime_store_bytes", "external_cache_bytes")]
    scalar_paths += [(key, field) for key in ("first_operations", "repeat_operations", "index", "setup", "observer_validation") for field in ("elapsed_s", "cpu_s")]
    means = {}
    for keys in scalar_paths:
        values = [at(r, *keys) for r in repetitions]
        means["_".join(keys)] = mean(values) if values and all(isinstance(v, (int, float)) for v in values) else None
    return {"architecture": result["architectures"][arm_name], "arm": arm_name,
            "implementation": result["implementations"][arm_name], "repetitions": repetitions, "means": means,
            "retained_arm_artifact_bytes": sum(tree_bytes(root / "artifacts" / run["id"]) for run in result["runs"] if run["arm"] == arm_name)}


def pair(root):
    result = read(root / "result.json")
    arms = {arm: summarize_arm(root, result, arm) for arm in result["architectures"]}
    changes = []
    for control, variant in zip(arms["control"]["repetitions"], arms["variant"]["repetitions"]):
        source_changes = []
        controls = {case["case_id"]: case for case in control["cases"]}
        variants = {case["case_id"]: case for case in variant["cases"]}
        for case_id in sorted(set(controls) | set(variants)):
            before = set(at(controls.get(case_id), "source", "covered_context_ids") or [])
            after = set(at(variants.get(case_id), "source", "covered_context_ids") or [])
            if before != after:
                source_changes.append({"case_id": case_id, "gained_context_ids": sorted(after - before),
                                       "lost_context_ids": sorted(before - after)})
        metrics = ("source_spans", "native_available_links", "packet_proof_links", "strict_session_proof_links")
        deltas = {}
        for metric in metrics:
            before, after = control["first"][metric], variant["first"][metric]
            deltas[metric] = after - before if before is not None and after is not None else None
        changes.append({"repetition": control["repetition"], "first_metric_deltas": deltas,
                        "first_source_context_changes": source_changes})
    return {"result": str(root / "result.json"), "status": result["status"],
            "harness_revision": result.get("harness_revision"), "harness_dirty": result.get("harness_dirty"),
            "retained_pair_evidence_bytes": tree_bytes(root),
            "arms": arms, "control_to_variant_changes": changes}


def collect():
    data = {"qualification": ["Retained deterministic evidence only; no source retrieval or rescoring.",
             "Source spans, native availability, packet proof and strict session proof are distinct.",
             "Task answers remain unobserved; no agent utility conclusion.",
             "Null is missing/unrecorded, never substituted with zero; empty phase groups have measured operation count zero.",
             "Nested work receipts overlap top-level phase timing and are not added to it.",
             "Archive storage includes retained inputs/evaluator/artifacts; raw/native/cache measures are serialized proxies, not heap size.",
             "OS caches are not claimed cold; peak RSS is a process lifetime high-water mark."],
            "targeted": {}, "full": {}, "missing_pairs": []}
    for section in ("targeted", "full"):
        for name in PAIRS:
            root = BASE / "results" / f"{section}-{name}"
            if not (root / "result.json").is_file():
                data["missing_pairs"].append(root.name)
                continue
            data[section][name] = pair(root)
        left = data[section].get("demand-focused", {}).get("arms", {}).get("variant")
        right = data[section].get("focused-wide", {}).get("arms", {}).get("control")
        data[section + "_focused_cross_pair"] = None
        if left and right:
            comparisons = []
            for lrep, rrep in zip(left["repetitions"], right["repetitions"]):
                comparisons.append({"repetition": lrep["repetition"], **{
                    trial: equality(lrep["capability_fingerprints"][trial], rrep["capability_fingerprints"][trial])
                    for trial in ("first", "repeat")}})
            data[section + "_focused_cross_pair"] = comparisons
    return data


def display(data):
    for section in ("targeted", "full"):
        for name, evidence in data[section].items():
            for arm in evidence["arms"].values():
                for rep in arm["repetitions"]:
                    first, repeated = rep["first"], rep["repeat"]
                    print(section, name, arm["architecture"], "rep", rep["repetition"], json.dumps({
                        "source": [first["source_spans"], first["required_spans"]],
                        "native_packet_session_required": [first["native_available_links"], first["packet_proof_links"], first["strict_session_proof_links"], first["required_links"]],
                        "repeat_source_session": [repeated["source_spans"], repeated["strict_session_proof_links"]],
                        "first_repeat_equal": rep["first_repeat_capabilities"]["equal"],
                        "first_s_cpu": [rep["first_operations"]["elapsed_s"], rep["first_operations"]["cpu_s"]],
                        "repeat_s_cpu": [rep["repeat_operations"]["elapsed_s"], rep["repeat_operations"]["cpu_s"]],
                        "focused_calls": rep["semantic_first"]["focused"]["operations"],
                        "peak_rss_bytes": rep["peak_rss_bytes"],
                        "packet_invalid": first["packet_invalid_cases"], "session_invalid": first["session_invalid_cases"]}, sort_keys=True))
        print(section, "focused_cross_pair", json.dumps(data[section + "_focused_cross_pair"]))
    if data["missing_pairs"]:
        print("Missing pairs:", ", ".join(data["missing_pairs"]))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true", help="Write summary.json after all six completed pairs exist")
    args = parser.parse_args()
    data = collect()
    if args.write:
        incomplete = [f"{section}-{name}" for section in ("targeted", "full")
                      for name, result in data[section].items() if result["status"] != "completed"]
        if data["missing_pairs"] or incomplete:
            parser.error("--write requires six completed pairs; missing/incomplete: " + ", ".join(data["missing_pairs"] + incomplete))
        (BASE / "summary.json").write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")
    display(data)


if __name__ == "__main__":
    main()
