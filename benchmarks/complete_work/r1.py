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
    if "common_context" in plan and type(plan["common_context"]) is not bool:
        raise ValueError("common_context must explicitly opt in with true or false")
    root_agents = None
    if plan.get("common_context"):
        instructions = []
        for task in plan["tasks"]:
            path = Path(task["source"]) / "AGENTS.md"
            instructions.append(path.read_bytes().decode("utf-8") if path.exists() else None)
        if any(content != instructions[0] for content in instructions):
            raise ValueError("common context requires identical root AGENTS.md in every task source")
        root_agents = instructions[0]
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
    if plan.get("common_context"):
        bound["common_context"] = availability.context_policy(root_agents)
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
               str(Path(availability.__file__).resolve()),
               str(root / ".scratch/r1-integrated/pilot-execute.py")}
    policy = amendment.get("host_observation_policy")
    if policy is not None:
        if policy != r0.HOST_OBSERVATION_POLICY:
            raise ValueError("unsupported host observation policy")
        allowed.add(str(Path(r0.__file__).resolve()))
    capture = amendment.get("catalog_capture_policy")
    if capture is not None:
        if (not _common_context(frozen) or capture != "r1-common-context-v2"
                or amendment.get("catalog_capture_policy_sha256") != identity(
                    availability.capture_policy(frozen["common_context"]["root_agents_md"]))):
            raise ValueError("unsupported or changed catalog capture policy")
    elif "catalog_capture_policy_sha256" in amendment:
        raise ValueError("catalog capture policy selector is missing")
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
    observe_host = (amendment is not None and json.loads(amendment.read_text()).get(
        "host_observation_policy") == r0.HOST_OBSERVATION_POLICY)
    observations = {"policy": r0.HOST_OBSERVATION_POLICY, "startup_instructions": []} if observe_host else None
    if runtime:
        validation = r0.check_native_config(Path(frozen["native_config"]), frozen["native_config_sha256"],
                               frozen.get("native_config_binding"), host_observations=observe_host)
        if observe_host:
            observations["config_validation"] = validation
    if runtime and r0.digest(Path(frozen["host"]["executable"])) != frozen["host"]["sha256"]:
        raise ValueError("native executable changed after freeze")
    for name, expected in frozen["host"].get("startup_context_files", {}).items() if runtime else ():
        observed = r0.digest(Path(name))
        if observe_host and Path(name) == Path(frozen["native_config"]).parent / "AGENTS.md":
            observations["startup_instructions"].append({"path": name, "frozen_sha256": expected,
                                                        "observed_sha256": observed, "changed": observed != expected})
        elif observed != expected:
            raise ValueError("shared startup context changed after freeze")
    for name, expected in frozen["host"].get("orchestration_files", {}).items() if runtime else ():
        expected = changes.get(name, {}).get("after_sha256", expected)
        if r0.digest(Path(name)) != expected:
            raise ValueError("orchestration changed outside the recorded instrumentation amendment")
    for condition in frozen["conditions"].values() if runtime else ():
        for name, expected in condition.get("implementation_files", {}).items():
            if r0.digest(Path(name)) != expected:
                raise ValueError("condition implementation changed after freeze")
    if observe_host:
        frozen["host_observations"] = observations
    if amendment is not None and json.loads(amendment.read_text()).get("catalog_capture_policy"):
        frozen["capture_context"] = availability.capture_policy(frozen["common_context"]["root_agents_md"])
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
    if _common_context(frozen):
        overrides.update(frozen["common_context"]["cli_overrides"])
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


def _common_context(frozen: dict) -> bool:
    if "common_context" not in frozen:
        return False
    context = frozen["common_context"]
    if (not isinstance(context, dict) or "root_agents_md" not in context
            or context != availability.context_policy(context["root_agents_md"])):
        raise ValueError("prospective common-context policy is missing or changed; use a new freeze")
    return True


def _probe_prompt(frozen: dict, condition: str, workspace: Path) -> str:
    prompt = availability.probe_prompt(condition, workspace, frozen["conditions"][condition]["tools"],
                                       common_context=_common_context(frozen))
    if frozen.get("capture_context"):
        prompt = prompt.replace(availability.COMMON_MEASURED_PREFIX,
                                availability.capture_prefix(workspace.parent / "observer/common-tool-catalog.json"))
    return prompt


def _capture_arguments(frozen: dict, observer: Path, retained_observer: Path | None = None) -> dict:
    if not frozen.get("capture_context"):
        return {}
    if frozen["capture_context"] != availability.capture_policy(frozen["common_context"]["root_agents_md"]):
        raise ValueError("effective catalog capture policy differs")
    return {"catalog_artifact": (retained_observer or observer) / "common-tool-catalog.json",
            "catalog_destination": observer / "common-tool-catalog.json"}


def _probe_agents(frozen: dict, workspace: Path) -> None:
    """Root instructions are part of the probe fixture, never stripped on readback."""
    if not _common_context(frozen):
        return
    path = workspace / "AGENTS.md"
    expected = frozen["common_context"]["root_agents_md"]
    if (path.exists() if expected is None else not path.is_file() or path.read_bytes() != expected.encode("utf-8")):
        raise ValueError("availability root AGENTS.md differs from frozen task instructions")


def _protocol(frozen: dict) -> None:
    _common_context(frozen)
    if frozen.get("availability") != availability.policy():
        raise ValueError("native-host availability protocol is missing or changed; use a new freeze")
    for name in ("r0.py", "r1.py", "accounting.py", "evaluate.py", "availability.py"):
        source = Path(__file__).with_name(name).resolve()
        if str(source) not in frozen["host"].get("orchestration_files", {}):
            raise ValueError("native-host availability implementation is not pinned to this freeze")
    for condition, tools in availability.TOOLS_BY_CONDITION.items():
        if set(frozen["conditions"][condition]["tools"]) != set(tools):
            raise ValueError("condition tool set differs from native-host availability protocol")


def measured_prompt(frozen: dict, task: dict, condition: str, *, observer: Path | None = None) -> str:
    _protocol(frozen)
    common = _common_context(frozen)
    prefix = availability.COMMON_MEASURED_PREFIX if common else availability.MEASURED_PREFIX
    if frozen.get("capture_context"):
        if observer is None:
            raise ValueError("captured catalog requires the assigned observer path")
        prefix = availability.capture_prefix(observer / "common-tool-catalog.json")
    card = "\nCapability card: " + frozen["common_context"]["capability_cards"][condition] if common else ""
    return (prefix + "Expected tools: "
            + json.dumps(frozen["conditions"][condition]["tools"])
            + card + "\n\nOriginal task follows:\n" + task["prompt"])


def _run_conditions(frozen: dict) -> dict:
    conditions = {"model": frozen["model"], "effort": frozen["effort"],
                  "native_protection": frozen["native_protection"], "freeze_sha256": frozen["freeze_sha256"]}
    if "native_config_binding" in frozen:
        conditions["native_config_binding"] = frozen["native_config_binding"]
    if frozen.get("capture_context"):
        conditions["catalog_capture_policy_sha256"] = identity(frozen["capture_context"])
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


def audit_treatment(frozen: dict, manifest: dict, trace: Path, verified: dict,
                    *, retained_observer: Path | None = None) -> dict:
    """One retained-evidence check for grading and completed-prefix readback."""
    condition = manifest["r1"]["condition"]
    observer = Path(manifest["observer"])
    capture = _capture_arguments(frozen, observer, retained_observer)
    treatment = availability.audit_catalog(trace, frozen["conditions"][condition]["tools"],
                                            common_context=_common_context(frozen), **capture)
    if _common_context(frozen):
        task = next(task for task in frozen["tasks"] if task["id"] == manifest["r1"]["task"])
        context = availability.audit_common_context(trace, Path(manifest["workspace"]), Path(manifest["observer"]),
            measured_prompt(frozen, task, condition, observer=observer),
            frozen["conditions"][condition]["tools"], **capture)
        baseline = verified["common_context"]
        common_matches = context["common_sha256"] == baseline["common_sha256"]
        if not common_matches:
            probes = json.loads(Path(verified["path"]).read_text())["probes"]
            record = next(probe for probe in probes if probe["condition"] == "native")["files"]["evidence"]
            if r0.digest(Path(record["path"])) != record["sha256"]:
                raise ValueError("qualified common-context evidence changed")
            expected = json.loads(Path(record["path"]).read_text())["common_context"]["common"]
            comparison = availability.compare_common_context(expected, context["common"])
            common_matches = comparison["equivalent"]
            if common_matches:
                treatment["startup_rendering_variations"] = comparison["memory_truncation_counts"]
        if (not common_matches
                or context["loci_contracts_sha256"] != baseline["loci_contracts_sha256"][condition]):
            detail = ""
            if capture and baseline.get("catalog_artifact"):
                detail = "; catalog difference: " + json.dumps(availability.catalog_difference(
                    Path(baseline["catalog_artifact"]), capture["catalog_artifact"]), sort_keys=True)
            raise ValueError("measured rendered startup context differs from qualified probes" + detail)
        treatment["common_context"] = context
    return treatment


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
    contexts = {}
    catalogs = {}
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
                if (validation.get("effective_sha256") != frozen["native_config_binding"]["effective_sha256"]
                        and not (frozen.get("host_observations") and validation.get("contract_sha256")
                                 == r0.native_config_contract(frozen["native_config_binding"]))):
                    raise ValueError("availability effective native configuration differs")
            if manifest["config_validation"].get("raw_sha256") != manifest["native_config_sha256"]:
                raise ValueError("availability preparation configuration receipt differs")
        elif manifest.get("native_config_sha256") != frozen["native_config_sha256"]:
            raise ValueError("availability native configuration differs")
        threads.add(thread)
        # Use the archived fixture for byte checks, but preserve the original
        # repository argument used by the actual native MCP calls.
        workspace = Path(manifest["workspace"])
        retained_observer = Path(files["config"]["path"]).parent
        capture = _capture_arguments(frozen, Path(manifest["observer"]), retained_observer)
        if capture:
            if files.get("catalog", {}).get("path") != str(capture["catalog_artifact"]):
                raise ValueError("availability probe lacks the frozen full catalog capture; legacy hashes cannot be reconstructed")
            catalogs[condition] = capture["catalog_artifact"]
        expected_prompt = _probe_prompt(frozen, condition, workspace)
        if Path(files["prompt"]["path"]).read_text() != expected_prompt:
            raise ValueError("native availability prompt differs from frozen protocol")
        archived_workspace = Path(files["config"]["path"]).parent.parent / "workspace"
        for name, content in availability.PROBE_FILES.items():
            if (archived_workspace / name).read_bytes() != content.encode():
                raise ValueError("archived availability fixture changed")
        _probe_agents(frozen, archived_workspace)
        from .accounting import summarize_native
        accounting = (summarize_native(Path(files["trace"]["path"]), thread, allow_instruction_updates=True)
                      if frozen.get("host_observations") else summarize_native(Path(files["trace"]["path"]), thread))
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
        _verify_native_prompt(accounting, expected_prompt)
        for context in accounting["turn_contexts"]:
            if (context.get("model") != frozen["model"] or context.get("effort") != frozen["effort"]
                    or context.get("cwd") != manifest["workspace"]
                    or {field: context.get(field) for field in r0.PROTECTION_FIELDS} != frozen["native_protection"]):
                raise ValueError("availability host settings differ")
        # audit_probe checks fixture bytes as well. Retained probes are never
        # silently remapped to live source: supply the retained fixture separately.
        observed = availability.audit_probe(Path(files["trace"]["path"]), accounting,
                                            condition, workspace, frozen["conditions"][condition]["tools"],
                                            fixture=archived_workspace, common_context=_common_context(frozen), **capture)
        if _common_context(frozen):
            observed["common_context"] = availability.audit_common_context(
                Path(files["trace"]["path"]), workspace, Path(manifest["observer"]), expected_prompt,
                frozen["conditions"][condition]["tools"], **capture)
            contexts[condition] = observed["common_context"]
        if observed != evidence:
            raise ValueError("availability verdict differs from raw native evidence")
    verified = {"path": str(gate.resolve()), "sha256": r0.digest(gate), "threads": sorted(threads),
                "deterministic_gate_sha256": result["deterministic_gate_sha256"]}
    if _common_context(frozen):
        baseline = contexts["native"]["common"]
        differences = {}
        rendering_variations = {}
        for condition, context in contexts.items():
            if context["common"] != baseline:
                comparison = availability.compare_common_context(baseline, context["common"])
                if comparison["equivalent"]:
                    rendering_variations[condition] = comparison["memory_truncation_counts"]
                    continue
                differences[condition] = {"instructions_differ": context["common"]["instructions"] != baseline["instructions"],
                                          "catalog_differ": context["common"]["catalog"] != baseline["catalog"]}
                if catalogs:
                    differences[condition]["catalog_difference"] = availability.catalog_difference(
                        catalogs["native"], catalogs[condition])
        if differences:
            raise ValueError("rendered common startup context differs across availability probes: "
                             + json.dumps(differences, sort_keys=True))
        verified["common_context"] = {
            "common_sha256": contexts["native"]["common_sha256"],
            "loci_contracts_sha256": {condition: context["loci_contracts_sha256"]
                                      for condition, context in contexts.items()},
        }
        if catalogs:
            verified["common_context"]["catalog_artifact"] = str(catalogs["native"])
        if rendering_variations:
            verified["common_context"]["startup_rendering_variations"] = rendering_variations
    return verified


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
                          conditions=_run_conditions(frozen), host_observations=bool(frozen.get("host_observations")))
    observer, workspace = Path(manifest["observer"]), Path(manifest["workspace"])
    manifest["r1"] = {**scheduled, "freeze": str(freeze_path.resolve()),
                      "argv": command(frozen, scheduled["condition"], workspace, observer),
                      "availability_gate": verified}
    if frozen.get("host_observations"):
        manifest["r1"]["host_observations"] = frozen["host_observations"]
    if amendment is not None:
        manifest["r1"]["instrumentation_amendment"] = _amendment_record(amendment)
    # Identical discovery wrapper; original task text is unchanged in all arms.
    (observer / "prompt.txt").write_text(measured_prompt(frozen, task, scheduled["condition"], observer=observer))
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
    if (observer / "prompt.txt").read_text() != measured_prompt(frozen, task, manifest["r1"]["condition"], observer=observer):
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
        return {**json.loads(result_path.read_text()), "gate_path": str(result_path.resolve())}
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
    if _common_context(frozen) and frozen["common_context"]["root_agents_md"] is not None:
        (source / "AGENTS.md").write_bytes(frozen["common_context"]["root_agents_md"].encode("utf-8"))
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
                                  conditions=_run_conditions(frozen), host_observations=bool(frozen.get("host_observations")))
            observer, workspace = Path(manifest["observer"]), Path(manifest["workspace"])
            config = observer / "run.json"
            manifest["r1"] = {"phase": "availability", "condition": condition,
                              "freeze": str(freeze_path.resolve()),
                              "argv": command(frozen, condition, workspace, observer)}
            (observer / "prompt.txt").write_text(_probe_prompt(frozen, condition, workspace))
            write_json(config, manifest)
            executed = _execute_native(config, deterministic_gate, frozen, measured=False, amendment=amendment)
            thread = executed["thread_id"]
            entry["thread_id"] = thread
            if executed["status"] != "closed" or not thread or thread in threads:
                raise ValueError("native availability probe failed to close as a fresh session")
            threads.add(thread)
            traces = list((Path.home() / ".codex/sessions").rglob("*" + thread + ".jsonl"))
            if len(traces) != 1:
                raise ValueError("unique native availability rollout unavailable")
            qualified = (r0.qualify(config, traces[0], thread_id=thread, host_observations=True)
                         if frozen.get("host_observations") else r0.qualify(config, traces[0], thread_id=thread))
            if qualified["status"] != "qualified_observations" or qualified["source_before"] != qualified["source_after"]:
                raise ValueError("native availability probe was unqualified or modified its fixture")
            _verify_native_prompt(qualified["accounting"], (observer / "prompt.txt").read_text())
            evidence = availability.audit_probe(observer / "qualification/native-rollout.jsonl",
                                               qualified["accounting"], condition, workspace,
                                               frozen["conditions"][condition]["tools"],
                                               common_context=_common_context(frozen), **_capture_arguments(frozen, observer))
            if _common_context(frozen):
                _probe_agents(frozen, workspace)
                evidence["common_context"] = availability.audit_common_context(
                    observer / "qualification/native-rollout.jsonl", workspace, observer,
                    (observer / "prompt.txt").read_text(), frozen["conditions"][condition]["tools"],
                    **_capture_arguments(frozen, observer))
            write_json(observer / "availability.json", evidence)
            entry.update(status="passed", thread_id=thread)
        except Exception as exc:
            entry.update(status="failed", error=f"{type(exc).__name__}: {exc}")
            result["status"] = "failed"
        finally:
            # Retain even an incomplete probe. No replacement or automatic retry.
            try:
                if folder.exists():
                    archive = destination / condition
                    shutil.copytree(folder, archive)
                    entry["archive"] = str(archive.resolve())
                    files = {"config": "run.json", "prompt": "prompt.txt", "execution": "execution.json",
                             "qualification": "qualification/result.json",
                             "trace": "qualification/native-rollout.jsonl", "evidence": "availability.json",
                             "catalog": "common-tool-catalog.json"}
                    entry["files"] = {label: {"path": str((archive / "observer" / relative).resolve()),
                                                      "sha256": r0.digest(archive / "observer" / relative)}
                                      for label, relative in files.items() if (archive / "observer" / relative).is_file()}
            except Exception as exc:
                entry.update(status="failed", archive_error=f"{type(exc).__name__}: {exc}")
                result["status"] = "failed"
            write_json(result_path, result)
        print(json.dumps({"availability_condition": condition, "status": entry["status"],
                          "thread_id": entry.get("thread_id"), "error": entry.get("error")}), flush=True)
        if entry["status"] != "passed":
            return {**result, "gate_path": str(result_path.resolve())}
    result["status"] = "passed"
    write_json(result_path, result)
    try:
        require_availability(frozen, result_path)
    except Exception as exc:
        result.update(status="failed", error=f"gate validation: {type(exc).__name__}: {exc}")
        write_json(result_path, result)
    return {**result, "gate_path": str(result_path.resolve())}


def reprocess_availability(freeze_path: Path, deterministic_gate: Path, source_gate: Path,
                          destination: Path, *, amendment: Path | None = None) -> dict:
    """Replay completed archived probes into a new gate without native execution."""
    from copy import deepcopy
    from .accounting import summarize_native

    frozen = read_freeze(freeze_path, amendment=amendment)
    _protocol(frozen)
    original = json.loads(source_gate.read_text())
    if (json.loads(deterministic_gate.read_text()).get("status") != "passed"
            or original.get("kind") != "r1-native-host-availability"
            or original.get("freeze_sha256") != frozen["freeze_sha256"]
            or original.get("deterministic_gate_sha256") != r0.digest(deterministic_gate)):
        raise ValueError("retained availability or deterministic gate differs")
    destination.mkdir(parents=True, exist_ok=False)
    result_path = destination / "gate.json"
    result = deepcopy(original)
    result.update(status="failed", reprocessed_from={"path": str(source_gate.resolve()), "sha256": r0.digest(source_gate)},
                  reader_amendment=_amendment_record(amendment))
    result.pop("error", None)
    try:
        probes = result.get("probes", [])
        if len(probes) != 4 or {p.get("condition") for p in probes} != set(CONDITIONS):
            raise ValueError("all four completed probe archives are required; native sessions will not be repeated")
        for probe in probes:
            files = probe["files"]
            for record in files.values():
                if r0.digest(Path(record["path"])) != record["sha256"]:
                    raise ValueError("retained availability evidence bytes changed")
            manifest = json.loads(Path(files["config"]["path"]).read_text())
            observer, workspace = Path(manifest["observer"]), Path(manifest["workspace"])
            retained = Path(files["config"]["path"]).parent
            capture = _capture_arguments(frozen, observer, retained)
            if capture and "catalog" not in files:
                raise ValueError("legacy probes retained only catalog hashes, not the full catalog; cannot reconstruct or qualify capture v2")
            thread = json.loads(Path(files["execution"]["path"]).read_text()).get("thread_id")
            trace = Path(files["trace"]["path"])
            accounting = summarize_native(trace, thread, allow_instruction_updates=bool(frozen.get("host_observations")))
            condition = probe["condition"]
            evidence = availability.audit_probe(trace, accounting, condition, workspace,
                frozen["conditions"][condition]["tools"], fixture=retained.parent / "workspace",
                common_context=_common_context(frozen), **capture)
            if _common_context(frozen):
                evidence["common_context"] = availability.audit_common_context(trace, workspace, observer,
                    _probe_prompt(frozen, condition, workspace), frozen["conditions"][condition]["tools"], **capture)
            path = destination / condition / "availability.json"
            path.parent.mkdir()
            write_json(path, evidence)
            files["evidence"] = {"path": str(path.resolve()), "sha256": r0.digest(path)}
            probe.update(status="passed", thread_id=thread)
            probe.pop("error", None)
            probe.pop("archive_error", None)
        result["status"] = "passed"
        write_json(result_path, result)
        require_availability(frozen, result_path)
    except Exception as exc:
        result.update(status="failed", error=f"reader reprocessing: {type(exc).__name__}: {exc}")
    write_json(result_path, result)
    return {**result, "gate_path": str(result_path.resolve())}


def replay(config: Path, destination: Path, *, retained_observer: Path | None = None) -> dict:
    """Replay only archived bytes and frozen oracle, independently of the live workspace."""
    manifest = json.loads(config.read_text())
    frozen = read_freeze(Path(manifest["r1"]["freeze"]), runtime=False)
    task = next(t for t in frozen["tasks"] if t["id"] == manifest["r1"]["task"])
    if r0.digest(Path(task["oracle"])) != task["oracle_sha256"]:
        raise ValueError("independent evaluator changed after freeze")
    observer = retained_observer or Path(manifest["observer"])
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


def _retained_qualification(config: Path, trace: Path, thread_id: str, frozen: dict,
                            observer: Path) -> dict:
    """Verify original qualification against raw archived observations, without live paths."""
    from .accounting import summarize_native
    from urllib.parse import unquote, urlsplit

    manifest = json.loads(config.read_text())
    qualified = json.loads((observer / "qualification/result.json").read_text())
    if (qualified.get("status") != "qualified_observations" or qualified.get("errors")
            or qualified.get("run_id") != manifest["run_id"] or qualified.get("thread_id") != thread_id
            or qualified.get("config_sha256") != r0.digest(config)
            or qualified.get("native_trace_sha256") != r0.digest(trace)
            or qualified.get("conditions") != manifest.get("conditions")
            or manifest.get("conditions") != _run_conditions(frozen)
            or manifest.get("permission_overrides") != {}
            or qualified.get("native_config_sha256") != manifest.get("native_config_sha256")):
        raise ValueError("retained qualification is incomplete or its bindings differ")
    accounting = summarize_native(trace, thread_id, allow_instruction_updates=bool(frozen.get("host_observations")))
    # Only the location of identical retained bytes changes on archival.
    accounting["native_provenance"]["rollout_path"] = str(Path(manifest["observer"]) / "qualification/native-rollout.jsonl")
    if (accounting != qualified["accounting"] or accounting.get("usage_status") != "known"
            or accounting.get("native_errors") or not accounting.get("turn_contexts")):
        raise ValueError("retained qualification accounting differs from native trace")
    for context in accounting["turn_contexts"]:
        if (context.get("model") != frozen["model"] or context.get("effort") != frozen["effort"]
                or context.get("cwd") != manifest["workspace"]
                or {field: context.get(field) for field in r0.PROTECTION_FIELDS} != frozen["native_protection"]):
            raise ValueError("retained native host settings differ")
    for stage in accounting.get("stages", []):
        for item in stage.get("items", []):
            if item.get("type") == "collabAgentToolCall":
                raise ValueError("retained session delegated outside its captured thread")
            if manifest["arm"] == "native" and item.get("server") == "loci":
                raise ValueError("retained native assignment invoked Loci")
            if item.get("type") == "commandExecution":
                cwd = item.get("cwd")
                if isinstance(cwd, str) and cwd.startswith("file://"):
                    uri = urlsplit(cwd)
                    cwd = unquote(uri.path) if uri.netloc in {"", "localhost"} else None
                if not isinstance(cwd, str) or not Path(cwd).is_absolute() or Path(cwd).resolve() != Path(manifest["workspace"]):
                    raise ValueError("retained command working directory differs")
    if "native_config_binding" in frozen:
        for artifact in (manifest, qualified):
            validation = artifact.get("config_validation", {})
            if (validation.get("effective_sha256") != frozen["native_config_binding"]["effective_sha256"]
                    and not (frozen.get("host_observations") and validation.get("contract_sha256")
                             == r0.native_config_contract(frozen["native_config_binding"]))):
                raise ValueError("retained effective native configuration differs")
        if manifest["config_validation"].get("raw_sha256") != manifest["native_config_sha256"]:
            raise ValueError("retained native configuration receipt differs")
    elif manifest.get("native_config_sha256") != frozen["native_config_sha256"]:
        raise ValueError("retained native configuration differs")
    before = json.loads((observer / "source-before.json").read_text())
    after = json.loads((observer / "qualification/source-after.json").read_text())
    verify_snapshot(before, manifest["source_identity"])
    verify_snapshot(after, qualified["source_after"])
    if before["sha256"] != qualified["source_before"]:
        raise ValueError("retained qualification source differs")
    return qualified


def evaluate(config: Path, trace: Path, thread_id: str,
             *, amendment: Path | None = None, retained_observer: Path | None = None,
             output: Path | None = None) -> dict:
    """Use R0's native accounting and independently grade the retained source copy."""
    manifest = json.loads(config.read_text())
    frozen = read_freeze(Path(manifest["r1"]["freeze"]), amendment=amendment)
    _protocol(frozen)
    gate_record = manifest["r1"].get("availability_gate", {})
    verified = require_availability(frozen, Path(gate_record["path"]) if gate_record else None)
    if verified != gate_record or thread_id in verified["threads"]:
        raise ValueError("measured availability gate or fresh session differs")
    original_observer = Path(manifest["observer"])
    retained = retained_observer or original_observer
    observer = output or original_observer
    task = next(t for t in frozen["tasks"] if t["id"] == manifest["r1"]["task"])
    condition = manifest["r1"]["condition"]
    scheduled = next(row for row in frozen["schedule"] if row["run_id"] == manifest["run_id"])
    if (any(manifest["r1"].get(key) != value for key, value in scheduled.items())
            or manifest.get("source_identity") != task["source_identity"]
            or manifest["conditions"] != _run_conditions(frozen)
            or manifest["r1"]["argv"] != command(frozen, condition, Path(manifest["workspace"]), original_observer)):
        raise ValueError("retained measured assignment differs from freeze")
    if retained_observer is not None:
        if output is None or output.resolve() == retained.resolve():
            raise ValueError("retained reprocessing requires a separate new output directory")
        observer.mkdir(parents=True, exist_ok=False)
        qualification = _retained_qualification(config, trace, thread_id, frozen, retained)
        (observer / "qualification").mkdir()
        write_json(observer / "qualification/result.json", qualification)
    else:
        if output is not None:
            raise ValueError("derived output requires retained observer evidence")
        qualification = (r0.qualify(config, trace, thread_id=thread_id, host_observations=True)
                         if frozen.get("host_observations") else r0.qualify(config, trace, thread_id=thread_id))
    try:
        expected = measured_prompt(frozen, task, condition, observer=original_observer)
        if (retained / "prompt.txt").read_text() != expected:
            raise ValueError("retained measured prompt differs from freeze")
        _verify_native_prompt(qualification["accounting"], expected)
        treatment = audit_treatment(frozen, manifest, trace, verified, retained_observer=retained_observer)
        if qualification["status"] != "qualified_observations":
            raise ValueError("native session qualification failed")
    except ValueError as exc:
        write_json(observer / "treatment.json", {"status": "invalid", "error": str(exc),
                                                "native_trace_sha256": r0.digest(trace)})
        raise ValueError("treatment invalid; no correctness grade: " + str(exc)) from exc
    write_json(observer / "treatment.json", {"status": "verified", **treatment})
    oracle = replay(config, observer / "evaluation", retained_observer=retained_observer)
    result = {"run_id": manifest["run_id"], "condition": manifest["r1"]["condition"],
              "thread_id": thread_id, "freeze_sha256": frozen["freeze_sha256"],
              **oracle, "qualification_status": qualification["status"],
              "accounting": qualification["accounting"],
              "host_execution": (json.loads((retained / "execution.json").read_text())
                                 if (retained / "execution.json").exists() else None),
              "loci_telemetry": {"source_bytes": None, "semantic_requests": None,
                                 "proof_requests": None, "status": "requires_captured_call_attribution"},
              "manual_review": "pending_arm_blinded_review", "measured": True,
              "instrumentation_amendment": _amendment_record(amendment),
              "treatment_validity": {"status": "verified", **treatment},
              "limitations": qualification["limitations"][:3] + [
                  "Native tool availability follows unchanged host config; other MCP tools remain available.",
                  "Loci use, semantic/proof requests and evidence bytes require captured-call attribution; unavailable values remain unknown.",
                  "Small independently constructed tasks do not establish ordinary-repository population effects."]}
    if frozen.get("host_observations"):
        result["host_observations"] = frozen["host_observations"]
        result["limitations"].append("Personal host instructions are observed covariates; they may change during a session. This run does not establish fixed instruction exposure.")
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
