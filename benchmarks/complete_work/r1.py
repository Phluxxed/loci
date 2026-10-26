"""Prospective four-condition pilot using R0 snapshots and native Codex readback.

No SDK, API key, permission override, sandbox implementation or automatic retry.
Freeze first; a separately supplied passing deterministic gate permits execution.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time

from . import r0
from .evaluate import restore_snapshot, source_snapshot, verify_snapshot, write_json


CONDITIONS = ("native", "path-only", "integrated", "eager")
# Balanced Williams design: each condition occupies every position once, and
# each ordered adjacent pair occurs once. Task order is fixed prospectively.
ORDERS = ((0, 1, 3, 2), (1, 2, 0, 3), (2, 3, 1, 0), (3, 0, 2, 1))
MEASUREMENTS = (
    "independent_correctness", "elapsed_ms", "uncached_input_tokens",
    "cached_input_tokens", "output_tokens", "reasoning_output_tokens",
    "outer_tool_calls", "shell_calls", "mcp_calls", "failed_shell_calls",
    "observed_completed_model_requests", "context_compactions",
    "loci_source_bytes", "loci_semantic_requests", "loci_proof_requests",
)


def identity(value: dict) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def freeze(plan_path: Path, destination: Path) -> dict:
    """Bind source, prompts, independent oracles, settings and schedule before launch."""
    plan = json.loads(plan_path.read_text())
    if len(plan["tasks"]) != 4 or len({t["id"] for t in plan["tasks"]}) != 4:
        raise ValueError("exactly four independent tasks required")
    if set(plan["conditions"]) != set(CONDITIONS):
        raise ValueError("all four conditions required")
    if set(plan["native_protection"]) != set(r0.PROTECTION_FIELDS):
        raise ValueError("complete existing native protection evidence required")
    destination = destination.resolve()
    destination.mkdir(parents=True, exist_ok=False)
    tasks = []
    for task in plan["tasks"]:
        root = destination / task["id"]
        root.mkdir()
        snapshot = source_snapshot(Path(task["source"]), root / "source-history")
        restore_snapshot(snapshot, root / "source-history", root / "source")
        write_json(root / "source.json", snapshot)
        prompt = Path(task["prompt"]).read_text()
        (root / "prompt.txt").write_text(prompt)
        oracle = root / "oracle.mjs"
        oracle.write_bytes(Path(task["oracle"]).read_bytes())
        tasks.append({"id": task["id"], "source": str(root / "source"),
                      "source_identity": snapshot["sha256"], "prompt": prompt,
                      "prompt_sha256": r0.digest(root / "prompt.txt"),
                      "oracle": str(oracle), "oracle_sha256": r0.digest(oracle),
                      "criteria": task["criteria"]})
    bound = {"schema_version": 1, "kind": "r1-prospective-native-pilot",
             "model": plan["model"], "effort": plan["effort"],
             "native_protection": plan["native_protection"],
             "native_config": plan["native_config"],
             "native_config_sha256": r0.digest(Path(plan["native_config"])),
             "host": plan["host"], "conditions": plan["conditions"],
             "tasks": tasks, "measurements": MEASUREMENTS,
             "timeout_seconds": plan.get("timeout_seconds", 600),
             "schedule": [{"run_id": f"{task['id']}-{CONDITIONS[c]}",
                           "task": task["id"], "condition": CONDITIONS[c]}
                          for task, order in zip(tasks, ORDERS) for c in order],
             "analysis": {"unit": "paired task", "primary": "independent correctness",
                          "secondary": "elapsed and observed tokens per correct task",
                          "unknowns": "retain; never impute missing usage as zero",
                          "claims": "small constructed-task pilot; no population generalization"},
             "measured": False}
    bound["freeze_sha256"] = identity(bound)
    write_json(destination / "freeze.json", bound)
    return bound


def read_freeze(path: Path, *, runtime: bool = True) -> dict:
    frozen = json.loads(path.read_text())
    claimed = frozen.pop("freeze_sha256")
    if identity(frozen) != claimed:
        raise ValueError("prospective freeze changed")
    frozen["freeze_sha256"] = claimed
    if runtime and r0.digest(Path(frozen["native_config"])) != frozen["native_config_sha256"]:
        raise ValueError("native configuration changed after freeze")
    if runtime and r0.digest(Path(frozen["host"]["executable"])) != frozen["host"]["sha256"]:
        raise ValueError("native executable changed after freeze")
    pinned_host_files = {**frozen["host"].get("startup_context_files", {}),
                         **frozen["host"].get("orchestration_files", {})}
    for name, expected in pinned_host_files.items() if runtime else ():
        if r0.digest(Path(name)) != expected:
            raise ValueError("shared startup context changed after freeze")
    for condition in frozen["conditions"].values() if runtime else ():
        for name, expected in condition.get("implementation_files", {}).items():
            if r0.digest(Path(name)) != expected:
                raise ValueError("condition implementation changed after freeze")
    return frozen


def command(frozen: dict, condition: str, workspace: Path, observer: Path) -> list[str]:
    """Preserve native configuration; intentionally override only model and Loci."""
    settings = frozen["conditions"][condition]
    argv = [frozen["host"]["executable"], "exec", "--json", "--color", "never",
            "--skip-git-repo-check", "-C", str(workspace), "-m", frozen["model"],
            "-c", "model_reasoning_effort=" + json.dumps(frozen["effort"]),
            "-o", str(observer / "final.txt")]
    overrides = {"mcp_servers.loci.enabled": condition != "native",
                 "forced_login_method": "chatgpt", "model_provider": "openai"}
    if condition != "native":
        overrides.update({"mcp_servers.loci.command": settings["command"],
                          "mcp_servers.loci.args": settings["args"],
                          "mcp_servers.loci.enabled_tools": settings["tools"]})
        for key, value in settings["env"].items():
            overrides["mcp_servers.loci.env." + key] = value.replace("{store}", str(observer / "loci-store"))
    for key, value in overrides.items():
        argv.extend(["-c", key + "=" + json.dumps(value)])
    return argv + ["-"]


def prepare(freeze_path: Path, run_id: str, destination: Path) -> dict:
    frozen = read_freeze(freeze_path)
    # The unchanged global SessionStart hook indexes any Git ancestor. An
    # exported source directory outside Git makes that hook take its existing
    # no-repository exit without changing hook settings or native permissions.
    if any((parent / ".git").exists() for parent in (destination.resolve(), *destination.resolve().parents)):
        raise ValueError("run copies must be outside Git to avoid shared startup indexing")
    scheduled = next(row for row in frozen["schedule"] if row["run_id"] == run_id)
    task = next(task for task in frozen["tasks"] if task["id"] == scheduled["task"])
    probe = source_snapshot(Path(task["source"]), freeze_path.parent / "verification-blobs")
    verify_snapshot(probe, task["source_identity"])
    if r0.digest(Path(task["oracle"])) != task["oracle_sha256"]:
        raise ValueError("independent evaluator changed after freeze")
    manifest = r0.prepare(Path(task["source"]), destination, run_id=run_id,
                          arm="native" if scheduled["condition"] == "native" else "loci",
                          native_config=Path(frozen["native_config"]),
                          conditions={"model": frozen["model"], "effort": frozen["effort"],
                                      "native_protection": frozen["native_protection"],
                                      "freeze_sha256": frozen["freeze_sha256"]})
    observer, workspace = Path(manifest["observer"]), Path(manifest["workspace"])
    manifest["r1"] = {**scheduled, "freeze": str(freeze_path.resolve()),
                      "argv": command(frozen, scheduled["condition"], workspace, observer)}
    # Identical task text in all arms. Tool availability is host configuration.
    (observer / "prompt.txt").write_text(task["prompt"])
    write_json(observer / "run.json", manifest)
    return manifest


def execute(config: Path, gate: Path) -> dict:
    """Run exactly one fresh native thread; archive failure without substituting a run."""
    manifest = json.loads(config.read_text())
    frozen = read_freeze(Path(manifest["r1"]["freeze"]))
    permission = json.loads(gate.read_text())
    if permission.get("status") != "passed":
        raise ValueError("a passing deterministic qualification gate is required")
    if manifest["conditions"]["freeze_sha256"] != frozen["freeze_sha256"]:
        raise ValueError("run is not bound to this prospective freeze")
    observer = Path(manifest["observer"])
    task = next(t for t in frozen["tasks"] if t["id"] == manifest["r1"]["task"])
    if r0.digest(observer / "prompt.txt") != task["prompt_sha256"]:
        raise ValueError("run prompt changed after freeze")
    if manifest["r1"]["argv"] != command(frozen, manifest["r1"]["condition"], Path(manifest["workspace"]), observer):
        raise ValueError("native invocation changed after freeze")
    child_environment = dict(os.environ)
    for variable in ("OPENAI_API_KEY", "CODEX_API_KEY", "OPENAI_BASE_URL"):
        child_environment.pop(variable, None)
    login = subprocess.run([frozen["host"]["executable"], "login", "status"],
                           capture_output=True, text=True, check=False, env=child_environment)
    if login.returncode or "Logged in using ChatGPT" not in login.stdout + login.stderr:
        raise ValueError("existing ChatGPT subscription authentication required")
    marker = observer / "execution.json"
    if marker.exists():
        raise ValueError("run already attempted; no automatic retry")
    record = {"run_id": manifest["run_id"], "status": "started", "gate_sha256": r0.digest(gate),
              "freeze_sha256": frozen["freeze_sha256"], "measured": True}
    write_json(marker, record)
    start = time.monotonic()
    with (observer / "exec.jsonl").open("wb") as out, (observer / "exec.stderr").open("wb") as err:
        try:
            result = subprocess.run(manifest["r1"]["argv"], input=(observer / "prompt.txt").read_bytes(),
                                    cwd=manifest["workspace"], stdout=out, stderr=err,
                                    timeout=frozen["timeout_seconds"], check=False, env=child_environment)
            record.update(status="closed" if result.returncode == 0 else "failed", exit_code=result.returncode)
        except subprocess.TimeoutExpired:
            record.update(status="timed_out", exit_code=None)
    record["elapsed_ms"] = round((time.monotonic() - start) * 1000, 3)
    record["thread_id"] = None
    for line in (observer / "exec.jsonl").read_text().splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if event.get("type") == "thread.started":
            record["thread_id"] = event.get("thread_id")
    write_json(marker, record)
    return record


def replay(config: Path, destination: Path) -> dict:
    """Replay only archived bytes and frozen oracle, independently of the live workspace."""
    manifest = json.loads(config.read_text())
    frozen = read_freeze(Path(manifest["r1"]["freeze"]), runtime=False)
    task = next(t for t in frozen["tasks"] if t["id"] == manifest["r1"]["task"])
    if r0.digest(Path(task["oracle"])) != task["oracle_sha256"]:
        raise ValueError("independent evaluator changed after freeze")
    observer = Path(manifest["observer"])
    destination.mkdir(parents=True, exist_ok=False)
    retained = destination / "candidate"
    after = json.loads((observer / "qualification" / "source-after.json").read_text())
    restore_snapshot(after, observer / "source-history", retained)
    before = json.loads((observer / "source-before.json").read_text())
    verify_snapshot(before, task["source_identity"])
    changes = sorted(name for name in before["files"].keys() | after["files"].keys()
                     if before["files"].get(name) != after["files"].get(name))
    unexpected = sorted(set(changes) - set(task["criteria"]["allowed_changes"]))
    oracle = subprocess.run(["node", task["oracle"], str(retained)],
                            capture_output=True, text=True, timeout=30, check=False)
    result = {"run_id": manifest["run_id"], "source_identity": after["sha256"],
              "oracle_sha256": task["oracle_sha256"], "changes": changes,
              "unexpected_changes": unexpected, "correct": oracle.returncode == 0 and not unexpected,
              "oracle_stdout": oracle.stdout, "oracle_stderr": oracle.stderr}
    write_json(destination / "oracle.json", result)
    return result


def evaluate(config: Path, trace: Path, thread_id: str) -> dict:
    """Use R0's native accounting and independently grade the retained source copy."""
    manifest = json.loads(config.read_text())
    frozen = read_freeze(Path(manifest["r1"]["freeze"]))
    qualification = r0.qualify(config, trace, thread_id=thread_id)
    observer = Path(manifest["observer"])
    oracle = replay(config, observer / "evaluation")
    result = {"run_id": manifest["run_id"], "condition": manifest["r1"]["condition"],
              "thread_id": thread_id, "freeze_sha256": frozen["freeze_sha256"],
              **oracle, "qualification_status": qualification["status"],
              "accounting": qualification["accounting"],
              "host_execution": (json.loads((observer / "execution.json").read_text())
                                 if (observer / "execution.json").exists() else None),
              "loci_telemetry": {"source_bytes": None, "semantic_requests": None,
                                 "proof_requests": None, "status": "requires_captured_call_attribution"},
              "manual_review": "pending_arm_blinded_review", "measured": True,
              "limitations": qualification["limitations"][:3] + [
                  "Native tool availability follows unchanged host config; other MCP tools remain available.",
                  "Loci use, semantic/proof requests and evidence bytes require captured-call attribution; unavailable values remain unknown.",
                  "Small independently constructed tasks do not establish ordinary-repository population effects."]}
    write_json(observer / "evaluation" / "result.json", result)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="operation", required=True)
    f = sub.add_parser("freeze")
    f.add_argument("--plan", type=Path, required=True)
    f.add_argument("--destination", type=Path, required=True)
    p = sub.add_parser("prepare")
    p.add_argument("--freeze", type=Path, required=True)
    p.add_argument("--run-id", required=True)
    p.add_argument("--destination", type=Path, required=True)
    e = sub.add_parser("execute")
    e.add_argument("--config", type=Path, required=True)
    e.add_argument("--gate", type=Path, required=True)
    q = sub.add_parser("evaluate")
    q.add_argument("--config", type=Path, required=True)
    q.add_argument("--trace", type=Path, required=True)
    q.add_argument("--thread-id", required=True)
    r = sub.add_parser("replay")
    r.add_argument("--config", type=Path, required=True)
    r.add_argument("--destination", type=Path, required=True)
    args = parser.parse_args()
    if args.operation == "freeze":
        result = freeze(args.plan, args.destination)
    elif args.operation == "prepare":
        result = prepare(args.freeze, args.run_id, args.destination)
    elif args.operation == "execute":
        result = execute(args.config, args.gate)
    elif args.operation == "evaluate":
        result = evaluate(args.config, args.trace, args.thread_id)
    else:
        result = replay(args.config, args.destination)
    print(json.dumps({k: result[k] for k in ("run_id", "status", "freeze_sha256", "correct", "thread_id") if k in result}))


if __name__ == "__main__":
    main()
