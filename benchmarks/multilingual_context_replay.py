"""Independent source/index/raw-event replay of every frozen multilingual slot."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import tempfile

from benchmarks.multilingual_context_compare import COMPARISON, COMPARISON_ROOT, audit_request, build_prompt, settings
from benchmarks.multilingual_context_freeze import validate_freeze
from benchmarks.multilingual_context_inputs import load_inputs
from benchmarks.typescript_context_baseline import save, sha
from benchmarks.typescript_context_corpus import _isolated_store, materialize_snapshot


def read(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def replay_attempt(folder, corpus, controls, case, plan, freeze, index):
    from benchmarks.multilingual_context_observed import PROTOCOL, measure

    result, run = read(folder / "result.json"), read(folder / "run.json")
    provenance, raw = read(folder / "provenance.json"), read(folder / "adapter-trace.json")
    if raw != read(folder / "adapter-trace-copy.json"):
        raise ValueError("retained adapter trace copies differ")
    identity = result["identity"]
    if (identity["task_id"], identity["repetition"], identity["arm"]) != (case["id"], plan["repetition"], plan["arm"]):
        raise ValueError("attempt identity differs from plan")
    if (raw["identity"] != identity or run["session_id"] != identity["session_id"]
            or result["attempt_id"] != plan["attempt_id"] or run["attempt_id"] != plan["attempt_id"]
            or result["provenance"] != provenance):
        raise ValueError("trace/run/result/provenance identity mismatch")
    if (provenance["source"]["freeze_json_sha256"] != freeze["freeze_json_sha256"]
            or provenance["snapshot_files"] != corpus["snapshots"][case["snapshot"]]["files"]):
        raise ValueError("attempt uses another freeze or snapshot")
    prompt = build_prompt(corpus, controls, case["id"], plan["arm"])
    if (folder / "request-audit.json").is_file():
        retained = read(folder / "request-audit.json")
        actual = json.loads(json.dumps(audit_request(retained["request"], prompt, plan["arm"])))
        if actual != retained:
            raise ValueError("retained effective request audit changed")
        expected_schema = freeze["canonical_tool_schemas_sha256"][plan["arm"]]
        if actual["canonical_tool_schemas_sha256"] != expected_schema or provenance["canonical_tool_schemas_sha256"] != expected_schema:
            raise ValueError("effective schemas differ from frozen transport")
    elif not result.get("runner_failures"):
        raise ValueError("successful setup lacks an effective request audit")
    config = provenance["config"]
    expected_config = settings(Path(config["mcp_servers.evaluation.args"][2]),
                               Path(config["model_catalog_json"]),
                               Path(config["mcp_servers.evaluation.env"]["LOCI_BASE_DIR"]))
    if config != expected_config:
        raise ValueError("attempt does not use the frozen isolated host configuration")
    for key, expected in {"service_tier": "default"}.items():
        if config.get(key) != expected:
            raise ValueError("attempt host controls differ: " + key)
    compact = lambda value: json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode()
    if sha(prompt.encode()) != provenance["prompt_sha256"] or sha(compact(config)) != provenance["config_sha256"]:
        raise ValueError("attempt prompt/configuration hash mismatch")
    events = [json.loads(line) for line in (folder / "events.jsonl").read_text().splitlines() if line.strip()]
    if events != read(folder / "events.json"):
        raise ValueError("raw and parsed CLI events differ")
    run = {**run, "trace_path": str(folder / "adapter-trace.json")}
    baseline = result["baseline"]
    recomputed = measure(corpus, case, run, events, baseline["actual_process_seconds"],
                         baseline["exit_code"], result["measurement"]["outcome"] == "timeout", index)
    if result.get("protocol") != PROTOCOL or recomputed.get("protocol") != PROTOCOL:
        raise ValueError("measurement protocol differs")
    for failure in result.get("runner_failures", []):
        recomputed["measurement"]["measurement_complete"] = False
        recomputed["measurement"]["task_correct"] = False
        recomputed["measurement"]["full_pass"] = False
        recomputed["baseline"]["tool_delivery_verified"] = False
        if failure not in recomputed["baseline"]["failures"]:
            recomputed["baseline"]["failures"].append(failure)
    for key in ("identity", "events", "measurement"):
        if result[key] != recomputed[key]:
            raise ValueError("independent replay differs in " + key)
    for key, value in recomputed["baseline"].items():
        if baseline.get(key) != value:
            raise ValueError("independent replay differs in baseline." + key)
    return {"attempt_id": plan["attempt_id"], "verified": True,
            "measurement_complete": recomputed["measurement"]["measurement_complete"],
            "task_correct": recomputed["measurement"]["task_correct"]}


def verify(output: Path, freeze_path: Path = COMPARISON_ROOT / "freeze.json") -> dict:
    from loci import service

    output = Path(output).resolve()
    corpus, controls = load_inputs()
    freeze = validate_freeze(freeze_path)
    manifest = read(output / "manifest.json")
    if (manifest["comparison"] != COMPARISON or manifest["plan"] != freeze["plan"]
            or manifest["freeze"] != freeze or manifest["planned_runs"] != 114
            or manifest["catalog_sha256"] != freeze["model_catalog_sha256"]
            or sha((output / "model-catalog.json").read_bytes()) != freeze["model_catalog_sha256"]):
        raise ValueError("batch manifest/catalog differs from frozen declaration")
    cases = {case["id"]: case for case in corpus["cases"]}
    expected = {plan["attempt_id"] for plan in freeze["plan"]}
    unexpected = {p.parent.name for p in output.glob("*/result.json")} - expected
    if unexpected:
        raise ValueError("unscheduled results are present")
    rows, failures = [], []
    with tempfile.TemporaryDirectory(prefix="loci-multilingual-replay-") as temporary:
        temp = Path(temporary)
        indexes = {}
        for snapshot in corpus["snapshots"]:
            repo, store = temp / snapshot, temp / ("store-" + snapshot)
            materialize_snapshot(corpus, snapshot, repo)
            with _isolated_store(store):
                service.index_repo(repo, incremental=False)
                indexes[snapshot] = service.get_store().load(repo.resolve())
        for plan in freeze["plan"]:
            try:
                rows.append(replay_attempt(output / plan["attempt_id"], corpus, controls,
                                           cases[plan["case_id"]], plan, freeze, indexes[plan["snapshot"]]))
            except (KeyError, TypeError, ValueError, OSError) as exc:
                failures.append({"attempt_id": plan["attempt_id"], "error": str(exc)})
    raw_names = {"manifest.json", "model-catalog.json", "completion.json"}
    raw_paths = [p for p in output.rglob("*") if p.is_file()
                 and (p.relative_to(output).parts[0] in expected or p.name in raw_names)]
    report = {"schema_version": 1, "comparison": COMPARISON, "expected_runs": 114,
              "verified_runs": len(rows), "complete": len(rows) == 114 and not failures,
              "meaning": "Fresh frozen-engine indexes; raw CLI events, exact model-visible MCP source and proof, scores and usage recomputed without provider calls.",
              "failures": failures, "attempts": rows,
              "artifact_sha256": {p.relative_to(output).as_posix(): sha(p.read_bytes()) for p in sorted(raw_paths)}}
    save(output / "replay-verification.json", report)
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    value = verify(args.output)
    print(json.dumps({key: value[key] for key in ("complete", "verified_runs", "failures")}))
    if not value["complete"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
