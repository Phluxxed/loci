"""Promptfoo adapter for the bounded, local search/delivery ablation.

Each case owns its sequential warmup and seven interleaved rounds. No LLM,
remote grader, production server, or global agent configuration is involved.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import statistics
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from evals.search_ablation import backend, delivery

PRIVATE = ROOT / ".scratch/search-ablation/private"
ROUNDS = 7
DELIVERY_MODES = ("r1", "direct_full_refresh", "direct")


def _digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _inputs():
    freeze = json.loads((PRIVATE / "freeze.json").read_text())
    for relative, expected in freeze["files"].items():
        if _digest(ROOT / relative) != expected:
            raise ValueError(f"Frozen experiment input changed: {relative}")
    return json.loads((PRIVATE / "cases.json").read_text()), freeze


def _order(modes, number):
    # First six rounds cover all permutations of three modes; the seventh is
    # the declared extra repeat. Warmup is recorded separately.
    shift = number % len(modes)
    order = list(modes[shift:] + modes[:shift])
    return list(reversed(order)) if number % 2 else order


def _summaries(rows, modes, time_key, divisor=1):
    summaries = {}
    for mode in modes:
        group = [row for row in rows if row["mode"] == mode]
        times = [row[time_key] / divisor for row in group]
        summaries[mode] = {"n": len(group), "median_ms": statistics.median(times),
                           "min_ms": min(times), "max_ms": max(times)}
        for key in ("tool_calls", "encoded_output_bytes", "delivered_source_bytes",
                    "extra_source_bytes", "duplicate_source_bytes", "match_count"):
            if all(key in row and row[key] is not None for row in group):
                summaries[mode][key] = sorted(set(row[key] for row in group))
        if any("routing" in row for row in group):
            summaries[mode]["routing"] = sorted(set(row["routing"] for row in group))
    return summaries


def _search(case, run_dir):
    config = backend.default_config(ROOT)
    config["private_dir"] = str(run_dir / "backend")
    Path(config["private_dir"]).mkdir(parents=True, exist_ok=True)
    modes = backend.MODES
    with backend.service(config) as server:
        warmup = [backend.run_case(case, mode, config) for mode in modes]
        warmup_equal = backend.verify_equivalence(warmup)
        if not warmup_equal["equal"]:
            return {"ok": False, "error": "Warmup result mismatch/error; timing not started",
                    "warmup": warmup, "warmup_equivalence": warmup_equal,
                    "server": server, "trials": [], "expected_trial_count": ROUNDS * len(modes)}
        trials = []
        for round_id in range(ROUNDS):
            for position, mode in enumerate(_order(modes, round_id)):
                result = backend.run_case(case, mode, config)
                trials.append({**result, "round": round_id, "position": position})
        equivalence = backend.verify_equivalence([*warmup, *trials])
    summaries = _summaries(trials, modes, "elapsed_ms")
    native = summaries["rg"]["median_ms"]
    indexed = summaries["tgrep_index"]["median_ms"]
    saving = native - indexed
    return {"ok": equivalence["equal"], "error": None if equivalence["equal"] else "Measured results differ",
            "warmup": warmup, "warmup_equivalence": warmup_equal, "server": server,
            "trials": trials, "expected_trial_count": ROUNDS * len(modes),
            "equivalence": equivalence, "summary": summaries,
            "index_saving_ms": saving, "index_saving_fraction": saving / native,
            "mechanically_material_index_gain": equivalence["equal"] and saving >= 10 and saving / native >= .20}


def _delivered_ok(row):
    return (row.get("error") is None and row.get("complete") is True
            and row.get("required_bytes", 0) > 0
            and row["required_bytes"] == row["covered_required_bytes"]
            and row["required_sha256"] == row["delivered_required_sha256"])


def _delivery(case, source_root, run_dir):
    config = {"source_root": source_root, "output_dir": run_dir / "delivery",
              "store": run_dir / "r1-store"}
    warmup = [delivery.run_case(case, mode, {**config, "run_id": f"{case['id']}-warmup"})
              for mode in DELIVERY_MODES]
    if not all(_delivered_ok(row) for row in warmup):
        return {"ok": False, "error": "Warmup delivery incomplete; timing not started",
                "warmup": warmup, "trials": [], "expected_trial_count": ROUNDS * len(DELIVERY_MODES)}
    trials = []
    for round_id in range(ROUNDS):
        for position, mode in enumerate(_order(DELIVERY_MODES, round_id)):
            result = delivery.run_case(case, mode, {**config, "run_id": f"{case['id']}-round-{round_id}"})
            trials.append({**result, "round": round_id, "position": position})
    complete = all(_delivered_ok(row) for row in [*warmup, *trials])
    return {"ok": complete, "error": None if complete else "Measured delivery incomplete",
            "warmup": warmup, "trials": trials, "expected_trial_count": ROUNDS * len(DELIVERY_MODES),
            "required_bytes": warmup[0]["required_bytes"],
            "summary": _summaries(trials, DELIVERY_MODES, "elapsed_ns", 1e6)}


def call_api(prompt, options, context):
    del prompt
    try:
        config = options.get("config", {})
        run_id = config["run_id"]
        if not re.fullmatch(r"[A-Za-z0-9_-]+", run_id):
            raise ValueError("run_id must be a simple unique label")
        cases, freeze = _inputs()
        variables = context["vars"]
        kind, case_id = variables["kind"], variables["case_id"]
        if kind not in {"search", "delivery"}:
            raise ValueError("Unknown experiment kind")
        case = next(row for row in cases[f"{kind}_cases"] if row["id"] == case_id)
        run_dir = PRIVATE / run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        output_path = run_dir / f"{kind}-{case_id}.json"
        if output_path.exists():
            raise ValueError("Case already recorded; choose a new explicit run_id to rerun")
        result = (_search(case, run_dir) if kind == "search"
                  else _delivery(case, cases["source_root"], run_dir))
        result.update(schema=1, kind=kind, case_id=case_id, case_kind=case.get("kind", "observed_source_span"),
                      frozen_input_sha256=freeze["identity"], rounds=ROUNDS,
                      result_path=str(output_path), whole_agent_measurement=False)
        output_path.write_text(json.dumps(result, indent=2) + "\n")
        return {"output": json.dumps(result)}
    except Exception as exc:
        return {"error": f"{type(exc).__name__}: {exc}"}
