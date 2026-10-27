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
import shutil
import subprocess
import tempfile
import time

from . import availability, r0
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
    host = dict(plan["host"])
    pins = dict(host.get("orchestration_files", {}))
    for name in ("r0.py", "r1.py", "accounting.py", "evaluate.py", "availability.py"):
        source = Path(__file__).with_name(name).resolve()
        pins[str(source)] = r0.digest(source)
    host["orchestration_files"] = pins
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
    config_binding = r0.native_config_binding(Path(plan["native_config"]).read_bytes())
    bound = {"schema_version": 1, "kind": "r1-prospective-native-pilot",
             "model": plan["model"], "effort": plan["effort"],
             "native_protection": plan["native_protection"],
             "native_config": plan["native_config"],
             "native_config_sha256": config_binding["raw_sha256"],
             "native_config_binding": config_binding,
             "host": host, "conditions": plan["conditions"],
             "tasks": tasks, "measurements": MEASUREMENTS,
             "timeout_seconds": plan.get("timeout_seconds", 600),
             "schedule": [{"run_id": f"{task['id']}-{CONDITIONS[c]}",
                           "task": task["id"], "condition": CONDITIONS[c]}
                          for task, order in zip(tasks, ORDERS) for c in order],
             "analysis": {"unit": "paired task", "primary": "independent correctness",
                          "secondary": "elapsed and observed tokens per correct task",
                          "unknowns": "retain; never impute missing usage as zero",
                          "claims": "small constructed-task pilot; no population generalization"},
             "availability": availability.policy(), "measured": False}
    bound["freeze_sha256"] = identity(bound)
    write_json(destination / "freeze.json", bound)
    return bound


def _instrumentation_changes(path: Path, frozen: dict) -> dict:
    """An explicit amendment may replace only these existing harness pins."""
    amendment = json.loads(path.read_text())
    claimed = amendment.pop("amendment_sha256", None)
    if (identity(amendment) != claimed or amendment.get("schema_version") != 1
            or amendment.get("kind") != "r1-instrumentation-amendment"
            or amendment.get("freeze_sha256") != frozen["freeze_sha256"]):
        raise ValueError("instrumentation amendment identity or base freeze differs")
    root = Path(__file__).resolve().parents[2]
    allowed = {str(Path(__file__).resolve()),
               str(Path(__file__).with_name("accounting.py").resolve()),
               str(root / ".scratch/r1-integrated/pilot-execute.py")}
    changes = amendment.get("changes")
    original = frozen["host"].get("orchestration_files", {})
    if not isinstance(changes, dict) or not changes or set(changes) - allowed:
        raise ValueError("instrumentation amendment contains disallowed paths")
    for name, change in changes.items():
        if (name not in original or not isinstance(change, dict)
                or set(change) != {"before_sha256", "after_sha256"}
                or change["before_sha256"] != original[name]
                or not isinstance(change["after_sha256"], str)
                or len(change["after_sha256"]) != 64
                or any(c not in "0123456789abcdef" for c in change["after_sha256"])
                or change["after_sha256"] == change["before_sha256"]):
            raise ValueError("instrumentation amendment does not replace an original pin")
    return changes


def _amendment_record(path: Path | None) -> dict | None:
    return None if path is None else {"path": str(path.resolve()), "sha256": r0.digest(path)}


def read_freeze(path: Path, *, runtime: bool = True, amendment: Path | None = None) -> dict:
    frozen = json.loads(path.read_text())
    claimed = frozen.pop("freeze_sha256")
    if identity(frozen) != claimed:
        raise ValueError("prospective freeze changed")
    frozen["freeze_sha256"] = claimed
    changes = {} if amendment is None else _instrumentation_changes(amendment, frozen)
    if runtime:
        r0.check_native_config(Path(frozen["native_config"]), frozen["native_config_sha256"],
                               frozen.get("native_config_binding"))
    if runtime and r0.digest(Path(frozen["host"]["executable"])) != frozen["host"]["sha256"]:
        raise ValueError("native executable changed after freeze")
    for name, expected in frozen["host"].get("startup_context_files", {}).items() if runtime else ():
        if r0.digest(Path(name)) != expected:
            raise ValueError("shared startup context changed after freeze")
    for name, expected in frozen["host"].get("orchestration_files", {}).items() if runtime else ():
        expected = changes.get(name, {}).get("after_sha256", expected)
        if r0.digest(Path(name)) != expected:
            raise ValueError("orchestration changed outside the recorded instrumentation amendment")
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
        if frozen.get("availability"):
            overrides["mcp_servers.loci.required"] = True
    for key, value in overrides.items():
        argv.extend(["-c", key + "=" + json.dumps(value)])
    return argv + ["-"]


def _protocol(frozen: dict) -> None:
    if frozen.get("availability") != availability.policy():
        raise ValueError("native-host availability protocol is missing or changed; use a new freeze")
    for name in ("r0.py", "r1.py", "accounting.py", "evaluate.py", "availability.py"):
        source = Path(__file__).with_name(name).resolve()
        if str(source) not in frozen["host"].get("orchestration_files", {}):
            raise ValueError("native-host availability implementation is not pinned to this freeze")
    for condition, tools in availability.TOOLS_BY_CONDITION.items():
        if set(frozen["conditions"][condition]["tools"]) != set(tools):
            raise ValueError("condition tool set differs from native-host availability protocol")


def measured_prompt(frozen: dict, task: dict, condition: str) -> str:
    _protocol(frozen)
    return (availability.MEASURED_PREFIX + "Expected tools: "
            + json.dumps(frozen["conditions"][condition]["tools"])
            + "\n\nOriginal task follows:\n" + task["prompt"])


def _run_conditions(frozen: dict) -> dict:
    conditions = {"model": frozen["model"], "effort": frozen["effort"],
                  "native_protection": frozen["native_protection"], "freeze_sha256": frozen["freeze_sha256"]}
    if "native_config_binding" in frozen:
        conditions["native_config_binding"] = frozen["native_config_binding"]
    return conditions


def _verify_native_prompt(accounting: dict, expected: str) -> None:
    messages = [item for stage in accounting.get("stages", []) for item in stage.get("items", [])
                if item.get("type") == "UserMessage"]
    if len(messages) != 1:
        raise ValueError("native availability session must contain exactly one task message")
    parts = messages[0].get("content")
    if (not isinstance(parts, list) or any(not isinstance(part, dict) or not isinstance(part.get("text"), str)
                                          for part in parts)
            or "".join(part["text"] for part in parts) != expected):
        raise ValueError("native task message differs from submitted frozen prompt")


def require_availability(frozen: dict, gate: Path | None) -> dict:
    """Recheck retained native-host evidence, not a passed flag or model assertion."""
    _protocol(frozen)
    if gate is None or not gate.is_file():
        raise ValueError("verified native-host availability gate is required before measured work")
    result = json.loads(gate.read_text())
    if (result.get("kind") != "r1-native-host-availability" or result.get("status") != "passed"
            or result.get("freeze_sha256") != frozen["freeze_sha256"]
            or result.get("deterministic_gate_sha256") is None):
        raise ValueError("native-host availability gate failed or belongs to another freeze")
    probes = result.get("probes", [])
    if len(probes) != 4 or {p.get("condition") for p in probes} != set(CONDITIONS):
        raise ValueError("availability gate must verify all four conditions")
    threads = set()
    for probe in probes:
        condition = probe["condition"]
        files = probe["files"]
        for record in files.values():
            if r0.digest(Path(record["path"])) != record["sha256"]:
                raise ValueError("availability evidence bytes changed")
        manifest = json.loads(Path(files["config"]["path"]).read_text())
        qualified = json.loads(Path(files["qualification"]["path"]).read_text())
        executed = json.loads(Path(files["execution"]["path"]).read_text())
        evidence = json.loads(Path(files["evidence"]["path"]).read_text())
        thread = executed.get("thread_id")
        if (not thread or thread in threads or executed.get("status") != "closed"
                or executed.get("exit_code") != 0 or executed.get("measured") is not False
                or executed.get("freeze_sha256") != frozen["freeze_sha256"]
                or executed.get("gate_sha256") != result["deterministic_gate_sha256"]
                or qualified.get("status") != "qualified_observations"
                or qualified.get("thread_id") != thread
                or qualified.get("config_sha256") != files["config"]["sha256"]
                or qualified.get("native_trace_sha256") != files["trace"]["sha256"]
                or qualified.get("source_before") != qualified.get("source_after")
                or qualified.get("source_before") != manifest.get("source_identity")
                or qualified.get("conditions") != manifest.get("conditions")
                or qualified.get("native_config_sha256") != manifest.get("native_config_sha256")
                or manifest.get("permission_overrides") != {}
                or manifest.get("conditions") != _run_conditions(frozen)
                or manifest["r1"].get("phase") != "availability"
                or manifest["r1"].get("condition") != condition
                or manifest["r1"]["argv"] != command(frozen, condition, Path(manifest["workspace"]), Path(manifest["observer"]))):
            raise ValueError("availability probe assignment or qualification differs")
        if "native_config_binding" in frozen:
            for artifact in (manifest, qualified):
                validation = artifact.get("config_validation", {})
                if validation.get("effective_sha256") != frozen["native_config_binding"]["effective_sha256"]:
                    raise ValueError("availability effective native configuration differs")
            if manifest["config_validation"].get("raw_sha256") != manifest["native_config_sha256"]:
                raise ValueError("availability preparation configuration receipt differs")
        elif manifest.get("native_config_sha256") != frozen["native_config_sha256"]:
            raise ValueError("availability native configuration differs")
        threads.add(thread)
        # Use the archived fixture for byte checks, but preserve the original
        # repository argument used by the actual native MCP calls.
        workspace = Path(manifest["workspace"])
        if Path(files["prompt"]["path"]).read_text() != availability.probe_prompt(
                condition, workspace, frozen["conditions"][condition]["tools"]):
            raise ValueError("native availability prompt differs from frozen protocol")
        archived_workspace = Path(files["config"]["path"]).parent.parent / "workspace"
        for name, content in availability.PROBE_FILES.items():
            if (archived_workspace / name).read_bytes() != content.encode():
                raise ValueError("archived availability fixture changed")
        from .accounting import summarize_native
        accounting = summarize_native(Path(files["trace"]["path"]), thread)
        # Qualification read the live trace before copying it into this archive.
        # Reconstruct that exact provenance path; every other field must replay
        # identically, and the archived trace bytes were hash-checked above.
        qualification_accounting = {**accounting, "native_provenance": {
            **accounting["native_provenance"],
            "rollout_path": str(Path(manifest["observer"]) / "qualification/native-rollout.jsonl"),
        }}
        if (qualification_accounting != qualified["accounting"] or accounting.get("usage_status") != "known"
                or accounting.get("native_errors") or not accounting.get("turn_contexts")):
            raise ValueError("availability accounting differs from native trace")
        _verify_native_prompt(accounting, availability.probe_prompt(
            condition, workspace, frozen["conditions"][condition]["tools"]))
        for context in accounting["turn_contexts"]:
            if (context.get("model") != frozen["model"] or context.get("effort") != frozen["effort"]
                    or context.get("cwd") != manifest["workspace"]
                    or {field: context.get(field) for field in r0.PROTECTION_FIELDS} != frozen["native_protection"]):
                raise ValueError("availability host settings differ")
        # audit_probe checks fixture bytes as well. Retained probes are never
        # silently remapped to live source: supply the retained fixture separately.
        observed = availability.audit_probe(Path(files["trace"]["path"]), accounting,
                                            condition, workspace, frozen["conditions"][condition]["tools"],
                                            fixture=archived_workspace)
        if observed != evidence:
            raise ValueError("availability verdict differs from raw native evidence")
    return {"path": str(gate.resolve()), "sha256": r0.digest(gate), "threads": sorted(threads),
            "deterministic_gate_sha256": result["deterministic_gate_sha256"]}


def prepare(freeze_path: Path, run_id: str, destination: Path,
            *, amendment: Path | None = None, availability_gate: Path | None = None) -> dict:
    frozen = read_freeze(freeze_path, amendment=amendment)
    verified = require_availability(frozen, availability_gate)
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
                          conditions=_run_conditions(frozen))
    observer, workspace = Path(manifest["observer"]), Path(manifest["workspace"])
    manifest["r1"] = {**scheduled, "freeze": str(freeze_path.resolve()),
                      "argv": command(frozen, scheduled["condition"], workspace, observer),
                      "availability_gate": verified}
    if amendment is not None:
        manifest["r1"]["instrumentation_amendment"] = _amendment_record(amendment)
    # Identical discovery wrapper; original task text is unchanged in all arms.
    (observer / "prompt.txt").write_text(measured_prompt(frozen, task, scheduled["condition"]))
    write_json(observer / "run.json", manifest)
    return manifest


def execute(config: Path, gate: Path, *, amendment: Path | None = None,
            availability_gate: Path | None = None) -> dict:
    """Run exactly one fresh native thread; archive failure without substituting a run."""
    manifest = json.loads(config.read_text())
    frozen = read_freeze(Path(manifest["r1"]["freeze"]), amendment=amendment)
    if manifest["r1"].get("instrumentation_amendment") != _amendment_record(amendment):
        raise ValueError("run instrumentation amendment differs from preparation")
    permission = json.loads(gate.read_text())
    if permission.get("status") != "passed":
        raise ValueError("a passing deterministic qualification gate is required")
    if manifest["conditions"] != _run_conditions(frozen):
        raise ValueError("run is not bound to this prospective freeze")
    verified = require_availability(frozen, availability_gate)
    if r0.digest(gate) != verified["deterministic_gate_sha256"]:
        raise ValueError("deterministic gate differs from verified availability probes")
    if manifest["r1"].get("availability_gate") != verified or manifest["r1"].get("phase") is not None:
        raise ValueError("measured run availability gate differs from preparation")
    observer = Path(manifest["observer"])
    task = next(t for t in frozen["tasks"] if t["id"] == manifest["r1"]["task"])
    if (observer / "prompt.txt").read_text() != measured_prompt(frozen, task, manifest["r1"]["condition"]):
        raise ValueError("run prompt changed after freeze")
    if manifest["r1"]["argv"] != command(frozen, manifest["r1"]["condition"], Path(manifest["workspace"]), observer):
        raise ValueError("native invocation changed after freeze")
    return _execute_native(config, gate, frozen, measured=True, amendment=amendment)


def _execute_native(config: Path, gate: Path, frozen: dict, *, measured: bool,
                    amendment: Path | None = None) -> dict:
    """One shared native launch path for unscored probes and gated measured runs."""
    manifest = json.loads(config.read_text())
    observer = Path(manifest["observer"])
    marker = observer / "execution.json"
    if marker.exists():
        raise ValueError("run already attempted; no automatic retry")
    child_environment = dict(os.environ)
    for variable in ("OPENAI_API_KEY", "CODEX_API_KEY", "OPENAI_BASE_URL"):
        child_environment.pop(variable, None)
    login = subprocess.run([frozen["host"]["executable"], "login", "status"],
                           capture_output=True, text=True, check=False, env=child_environment)
    if login.returncode or "Logged in using ChatGPT" not in login.stdout + login.stderr:
        raise ValueError("existing ChatGPT subscription authentication required")
    record = {"run_id": manifest["run_id"], "status": "started", "gate_sha256": r0.digest(gate),
              "freeze_sha256": frozen["freeze_sha256"], "measured": measured}
    if measured:
        record["availability_gate"] = manifest["r1"]["availability_gate"]
    if amendment is not None:
        record["instrumentation_amendment"] = _amendment_record(amendment)
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


def preflight(freeze_path: Path, deterministic_gate: Path, destination: Path,
              *, amendment: Path | None = None) -> dict:
    """Four unscored native sessions; never read a scored task or warm its store."""
    frozen = read_freeze(freeze_path, amendment=amendment)
    _protocol(frozen)
    if json.loads(deterministic_gate.read_text()).get("status") != "passed":
        raise ValueError("a passing deterministic qualification gate is required")
    result_path = destination / "gate.json"
    if result_path.exists():
        verified = require_availability(frozen, result_path)
        if r0.digest(deterministic_gate) != verified["deterministic_gate_sha256"]:
            raise ValueError("deterministic gate differs from verified availability probes")
        return json.loads(result_path.read_text())
    destination.mkdir(parents=True, exist_ok=False)
    result = {"kind": "r1-native-host-availability", "status": "running", "measured": False,
              "freeze_sha256": frozen["freeze_sha256"], "probes": [],
              "deterministic_gate_sha256": r0.digest(deterministic_gate)}
    write_json(result_path, result)
    run_root = Path(tempfile.mkdtemp(prefix="loci-r1-availability-", dir="/private/tmp"))
    result["run_root"] = str(run_root)
    write_json(result_path, result)
    source = run_root / "fixture"
    source.mkdir()
    for name, content in availability.PROBE_FILES.items():
        (source / name).write_text(content)
    threads = set()
    for condition in CONDITIONS:
        run_id = "availability-" + condition
        folder = run_root / run_id
        entry = {"condition": condition, "status": "started"}
        result["probes"].append(entry)
        write_json(result_path, result)
        try:
            manifest = r0.prepare(source, folder, run_id=run_id,
                                  arm="native" if condition == "native" else "loci",
                                  native_config=Path(frozen["native_config"]),
                                  conditions=_run_conditions(frozen))
            observer, workspace = Path(manifest["observer"]), Path(manifest["workspace"])
            config = observer / "run.json"
            manifest["r1"] = {"phase": "availability", "condition": condition,
                              "freeze": str(freeze_path.resolve()),
                              "argv": command(frozen, condition, workspace, observer)}
            (observer / "prompt.txt").write_text(availability.probe_prompt(
                condition, workspace, frozen["conditions"][condition]["tools"]))
            write_json(config, manifest)
            executed = _execute_native(config, deterministic_gate, frozen, measured=False, amendment=amendment)
            thread = executed["thread_id"]
            if executed["status"] != "closed" or not thread or thread in threads:
                raise ValueError("native availability probe failed to close as a fresh session")
            threads.add(thread)
            traces = list((Path.home() / ".codex/sessions").rglob("*" + thread + ".jsonl"))
            if len(traces) != 1:
                raise ValueError("unique native availability rollout unavailable")
            qualified = r0.qualify(config, traces[0], thread_id=thread)
            if qualified["status"] != "qualified_observations" or qualified["source_before"] != qualified["source_after"]:
                raise ValueError("native availability probe was unqualified or modified its fixture")
            _verify_native_prompt(qualified["accounting"], (observer / "prompt.txt").read_text())
            evidence = availability.audit_probe(observer / "qualification/native-rollout.jsonl",
                                               qualified["accounting"], condition, workspace,
                                               frozen["conditions"][condition]["tools"])
            write_json(observer / "availability.json", evidence)
            entry.update(status="passed", thread_id=thread)
        except Exception as exc:
            entry.update(status="failed", error=f"{type(exc).__name__}: {exc}")
            result["status"] = "failed"
        finally:
            # Retain even an incomplete probe. No replacement or automatic retry.
            if folder.exists():
                archive = destination / condition
                shutil.copytree(folder, archive)
                entry["archive"] = str(archive.resolve())
                files = {"config": "run.json", "prompt": "prompt.txt", "execution": "execution.json",
                         "qualification": "qualification/result.json",
                         "trace": "qualification/native-rollout.jsonl", "evidence": "availability.json"}
                entry["files"] = {label: {"path": str((archive / "observer" / relative).resolve()),
                                                  "sha256": r0.digest(archive / "observer" / relative)}
                                  for label, relative in files.items() if (archive / "observer" / relative).is_file()}
            write_json(result_path, result)
        print(json.dumps({"availability_condition": condition, "status": entry["status"],
                          "thread_id": entry.get("thread_id"), "error": entry.get("error")}), flush=True)
        if entry["status"] != "passed":
            return result
    result["status"] = "passed"
    write_json(result_path, result)
    try:
        require_availability(frozen, result_path)
    except Exception as exc:
        result.update(status="failed", error=f"gate validation: {type(exc).__name__}: {exc}")
        write_json(result_path, result)
    return result


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


def evaluate(config: Path, trace: Path, thread_id: str,
             *, amendment: Path | None = None) -> dict:
    """Use R0's native accounting and independently grade the retained source copy."""
    manifest = json.loads(config.read_text())
    frozen = read_freeze(Path(manifest["r1"]["freeze"]), amendment=amendment)
    _protocol(frozen)
    gate_record = manifest["r1"].get("availability_gate", {})
    verified = require_availability(frozen, Path(gate_record["path"]) if gate_record else None)
    if verified != gate_record or thread_id in verified["threads"]:
        raise ValueError("measured availability gate or fresh session differs")
    qualification = r0.qualify(config, trace, thread_id=thread_id)
    observer = Path(manifest["observer"])
    try:
        task = next(t for t in frozen["tasks"] if t["id"] == manifest["r1"]["task"])
        _verify_native_prompt(qualification["accounting"], measured_prompt(frozen, task, manifest["r1"]["condition"]))
        treatment = availability.audit_catalog(trace, frozen["conditions"][manifest["r1"]["condition"]]["tools"])
        if qualification["status"] != "qualified_observations":
            raise ValueError("native session qualification failed")
    except ValueError as exc:
        write_json(observer / "treatment.json", {"status": "invalid", "error": str(exc),
                                                "native_trace_sha256": r0.digest(trace)})
        raise ValueError("treatment invalid; no correctness grade: " + str(exc)) from exc
    write_json(observer / "treatment.json", {"status": "verified", **treatment})
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
              "instrumentation_amendment": _amendment_record(amendment),
              "treatment_validity": {"status": "verified", **treatment},
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
    e.add_argument("--availability-gate", type=Path, required=True)
    p.add_argument("--availability-gate", type=Path, required=True)
    probe = sub.add_parser("preflight")
    probe.add_argument("--freeze", type=Path, required=True)
    probe.add_argument("--gate", type=Path, required=True)
    probe.add_argument("--destination", type=Path, required=True)
    q = sub.add_parser("evaluate")
    q.add_argument("--config", type=Path, required=True)
    q.add_argument("--trace", type=Path, required=True)
    q.add_argument("--thread-id", required=True)
    r = sub.add_parser("replay")
    r.add_argument("--config", type=Path, required=True)
    r.add_argument("--destination", type=Path, required=True)
    for operation in (p, e, q):
        operation.add_argument("--amendment", type=Path)
    args = parser.parse_args()
    if args.operation == "freeze":
        result = freeze(args.plan, args.destination)
    elif args.operation == "prepare":
        result = prepare(args.freeze, args.run_id, args.destination, amendment=args.amendment,
                         availability_gate=args.availability_gate)
    elif args.operation == "execute":
        result = execute(args.config, args.gate, amendment=args.amendment,
                         availability_gate=args.availability_gate)
    elif args.operation == "preflight":
        result = preflight(args.freeze, args.gate, args.destination)
    elif args.operation == "evaluate":
        result = evaluate(args.config, args.trace, args.thread_id, amendment=args.amendment)
    else:
        result = replay(args.config, args.destination)
    print(json.dumps({k: result[k] for k in ("run_id", "status", "freeze_sha256", "correct", "thread_id") if k in result}))


if __name__ == "__main__":
    main()
