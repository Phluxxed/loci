"""Run the frozen Ember navigation pilot through isolated Codex App Servers.

Usage: /Users/brummerv/loci/.venv/bin/python -m benchmarks.navigation_pilot.run
       [--output ~/phluxxed/tmp/run-name] [--preflight-only] [--graph-toggle]
"""
from __future__ import annotations

import argparse
from collections import OrderedDict
import hashlib
import io
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
import tarfile
import time
from types import SimpleNamespace
from typing import Any, Awaitable, Callable

from benchmarks.complete_work.isolation import READ_PROFILE, build_overrides, verify_profile
from benchmarks.complete_work.runtime import AppServer, Journal, RuntimeFailure, command_with_config


HERE = Path(__file__).resolve().parent
HARNESS = HERE.parents[1]
ORIGINAL = Path("/Users/brummerv/loci")
PYTHON = ORIGINAL / ".venv/bin/python"
USER_CONFIG = Path.home() / ".codex/config.toml"
ARMS = ("vanilla", "production", "source_context")
PRODUCTION_COMMIT = "9655a287ca28d758a8848b6622887c54f8f81a41"
USAGE_FIELDS = ("inputTokens", "cachedInputTokens", "outputTokens", "reasoningOutputTokens", "totalTokens")


def write_json(path: Path, value: dict) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n")
    temporary.replace(path)


def load_case() -> tuple[dict, str]:
    raw = (HERE / "case.json").read_bytes()
    case = json.loads(raw)
    if (case.get("schema_version") != 1 or case.get("case_id") != "ember-dependency-lifecycle"
            or list(case.get("conditions", {})) != list(ARMS)
            or case["conditions"]["vanilla"] is not None
            or case.get("time_cap_seconds") != 300):
        raise ValueError("frozen pilot case has an unexpected shape")
    for key in ("source_commit", "model", "reasoning_effort", "instructions", "prompt"):
        if not isinstance(case.get(key), str) or not case[key]:
            raise ValueError(f"frozen pilot case lacks {key}")
    return case, hashlib.sha256(raw).hexdigest()


def check_output_location(output: Path, case: dict) -> Path:
    output = output.expanduser().resolve()
    roots = (ORIGINAL.resolve(), HARNESS.resolve(), Path(case["source_repository"]).resolve(strict=True))
    if any(output == root or output.is_relative_to(root) or root.is_relative_to(output) for root in roots):
        raise ValueError("output must be outside the Loci and Ember source repositories")
    return output


def archive(repo: Path, commit: str, destination: Path) -> dict:
    actual = subprocess.run(["git", "-C", str(repo), "rev-parse", "--verify", commit + "^{commit}"],
                            capture_output=True, text=True, check=True).stdout.strip()
    if actual != commit:
        raise ValueError(f"commit identity differs for {repo}")
    tar = subprocess.run(["git", "-C", str(repo), "archive", "--format=tar", commit],
                         capture_output=True, check=True).stdout
    destination.mkdir(parents=True, exist_ok=False)
    with tarfile.open(fileobj=io.BytesIO(tar)) as archive_file:
        archive_file.extractall(destination, filter="data")
    # Git archives contain source without worktree changes or Git metadata.
    return {"commit": commit, "archive_sha256": hashlib.sha256(tar).hexdigest(),
            "archive_bytes": len(tar), "path": str(destination)}


def target_guard(
    delegate: Callable[..., Awaitable[Any]], target: Path, tool_error: type[Exception]
) -> Callable[..., Awaitable[Any]]:
    """Constrain the unchanged normal tool catalog to one archived repository."""
    target = target.resolve(strict=True)

    async def guarded(name: str, arguments: dict, context: Any = None) -> Any:
        if name not in {"loci_retrieve", "loci_read"}:
            raise tool_error("pilot exposes only the two normal navigation tools")
        repo = arguments.get("repo") if isinstance(arguments, dict) else None
        try:
            valid = isinstance(repo, str) and Path(repo).resolve(strict=True) == target
        except (OSError, ValueError):
            valid = False
        if not valid:
            raise tool_error("pilot tool access is restricted to its archived target")
        return await delegate(name, arguments, context)

    return guarded


def serve_target(target: Path, *, graph_enrichment: bool | None = None) -> None:
    from loci import mcp_server
    from mcp.server.mcpserver.exceptions import ToolError

    if os.environ.get("LOCI_MCP_SURFACE") != "normal":
        raise RuntimeError("pilot requires the normal Loci tool surface")
    if graph_enrichment is not None:
        from loci import service

        runtime = service.RetrievalRuntime(graph_enrichment=graph_enrichment)
        mcp_server._service_module = SimpleNamespace(
            retrieve=runtime.retrieve, read=service.read, LociError=service.LociError,
        )
    mcp_server.mcp.call_tool = target_guard(mcp_server.mcp.call_tool, target, ToolError)
    mcp_server.main()


def arm_overrides(workspace: Path, arm: str, serving: Path | None, namespace: str,
                  *, user_config: Path = USER_CONFIG) -> dict:
    overrides = build_overrides(workspace, [], str(PYTHON), [], {}, user_config=user_config)
    overrides["project_doc_max_bytes"] = 0
    overrides["agents.enabled"] = False
    overrides["features.multi_agent_v2"] = False
    # Stores belong to the server, outside the source and the agent's shell access.
    overrides["shell_environment_policy.set"].pop("LOCI_BASE_DIR", None)
    overrides[f"permissions.{READ_PROFILE}"]["filesystem"][":workspace_roots"].pop(
        ".episode-store", None
    )
    if arm == "vanilla":
        # The ambient Loci entry is explicitly disabled, with no replacement.
        del overrides["mcp_servers.loci"]
        overrides["mcp_servers.loci.enabled"] = False
    else:
        assert serving is not None
        overrides["mcp_servers.loci"] = {
            "enabled": True, "required": True, "command": str(PYTHON),
            "args": ["-m", "benchmarks.navigation_pilot.run", "--serve-target", str(workspace)],
            "env": {
                "PYTHONPATH": os.pathsep.join((str(HARNESS), str(serving / "src"))),
                "PYTHONDONTWRITEBYTECODE": "1", "PYTHONNOUSERSITE": "1",
                "LOCI_MCP_SURFACE": "normal", "LOCI_BASE_DIR": str(workspace.parent / "loci-store"),
                "LOCI_STORE_NAMESPACE": namespace,
            },
            "startup_timeout_sec": 60, "tool_timeout_sec": 60,
        }
        if arm in {"graph_on", "graph_off"}:
            overrides["mcp_servers.loci"]["args"] += [
                "--graph-enrichment", "on" if arm == "graph_on" else "off",
            ]
    return overrides


def arm_instructions(case: dict, serving: Path | None) -> tuple[str, dict]:
    text = case["instructions"]
    skill = None
    if serving is not None:
        skill = serving / "skills/loci/SKILL.md"
        text += "\n\n" + skill.read_text(encoding="utf-8")
    data = text.encode("utf-8")
    return text, {"sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data),
                  "bundled_skill": str(skill) if skill else None}


def canary(client: AppServer, workspace: Path, outside: Path) -> dict:
    visible = workspace / ".episode-tmp/visible-canary"
    visible.write_text("visible\n")
    outside.write_text("hidden\n")
    source_write = workspace / ".pilot-write-canary"
    source_write.write_text("unchanged")
    script = f"""\
canary_visible=denied
IFS= read -r canary_visible < {shlex.quote(str(visible))} || canary_visible=denied
if IFS= read -r canary_hidden < {shlex.quote(str(outside))}; then
    canary_hidden=allowed
else
    canary_hidden=denied
fi
if printf changed > {shlex.quote(str(source_write))}; then
    canary_write=allowed
else
    canary_write=denied
fi
printf '{{"visible":"%s","hidden":"%s","source_write":"%s"}}\\n' "$canary_visible" "$canary_hidden" "$canary_write"
"""
    try:
        response = client.call("command/exec", {
            "command": ["/bin/sh", "-c", script], "cwd": str(workspace),
            "permissionProfile": READ_PROFILE, "timeoutMs": 10000,
        }, timeout=15)
        try:
            observed = json.loads(response.get("stdout", ""))
        except (TypeError, ValueError):
            observed = None
        passed = (response.get("exitCode") == 0
                  and observed == {"visible": "visible", "hidden": "denied", "source_write": "denied"}
                  and source_write.read_text() == "unchanged")
        return {"status": "passed" if passed else "failed", "observed": observed,
                "command_result": response}
    finally:
        source_write.unlink(missing_ok=True)


def model_advertised(catalog: dict, model: str, effort: str) -> bool:
    return any(x.get("model") == model and any(
        e.get("reasoningEffort") == effort for e in x.get("supportedReasoningEfforts", []))
        for x in catalog.get("data", []))


def verify_inventory(inventory: dict, arm: str) -> dict:
    servers = inventory.get("data")
    if not isinstance(servers, list):
        raise ValueError("MCP inventory has no data array")
    active = {x.get("name"): sorted(x.get("tools", {})) for x in servers if x.get("tools")}
    expected = {} if arm == "vanilla" else {"loci": ["loci_read", "loci_retrieve"]}
    if active != expected:
        raise ValueError(f"MCP tool inventory differs: {active}")
    return {"active_tools": active, "server_count": len(servers)}


def preflight(client: AppServer, case: dict, workspace: Path, arm: str, outside: Path,
              instructions: str) -> dict:
    initialized = client.initialize()
    catalog = client.call("model/list", {"includeHidden": True, "limit": 100})
    if catalog.get("nextCursor") is not None or not model_advertised(
            catalog, case["model"], case["reasoning_effort"]):
        raise RuntimeFailure("pinned model/effort is absent from the complete runtime catalog")
    thread = client.call("thread/start", {
        "cwd": str(workspace), "runtimeWorkspaceRoots": [str(workspace)],
        "permissions": READ_PROFILE, "approvalPolicy": "never",
        "model": case["model"], "allowProviderModelFallback": False,
        "ephemeral": True, "experimentalRawEvents": True,
        "config": {"model_reasoning_effort": case["reasoning_effort"]},
        "developerInstructions": instructions,
    }, timeout=90)
    verify_profile(thread, READ_PROFILE, workspace)
    if thread.get("model") != case["model"] or thread.get("reasoningEffort") != case["reasoning_effort"]:
        raise RuntimeFailure("thread selected a different model or reasoning effort")
    thread_id = thread["thread"]["id"]
    inventory = verify_inventory(client.call("mcpServerStatus/list", {
        "threadId": thread_id, "limit": 100,
    }, timeout=90), arm)
    checked = canary(client, workspace, outside)
    if checked["status"] != "passed":
        raise RuntimeFailure(f"strict command canary failed: {checked['command_result']}")
    return {"status": "passed", "thread_id": thread_id, "model": thread["model"],
            "reasoning_effort": thread["reasoningEffort"], "inventory": inventory,
            "canary": checked, "runtime": initialized.get("userAgent")}


def _usage(value: dict) -> dict:
    if not isinstance(value, dict):
        raise ValueError("usage is not an object")
    result = {}
    for field in USAGE_FIELDS:
        number = value.get(field)
        if type(number) is not int or number < 0:
            raise ValueError(f"missing or invalid {field}")
        result[field] = number
    if result["cachedInputTokens"] > result["inputTokens"]:
        raise ValueError("cached input exceeds input")
    optional = value.get("cacheWriteInputTokens")
    if optional is not None and (type(optional) is not int or optional < 0):
        raise ValueError("invalid cacheWriteInputTokens")
    result["cacheWriteInputTokens"] = optional
    result["uncachedInputTokens"] = result["inputTokens"] - result["cachedInputTokens"]
    return result


def summarize_wire(path: Path, thread_id: str, turn_id: str | None,
                   *, completed: bool = True) -> dict:
    """Reduce retained native events without assuming optional telemetry exists."""
    usage = None
    usage_errors: list[str] = []
    updates = 0
    raw_responses: OrderedDict[str, dict] = OrderedDict()
    raw_calls: OrderedDict[str, dict] = OrderedDict()
    items: OrderedDict[str, dict] = OrderedDict()
    item_payloads: dict[str, dict] = {}
    capture_errors: list[str] = []
    for line in path.read_text().splitlines():
        row = json.loads(line)
        if row.get("direction") != "received":
            continue
        event = row.get("message", {})
        params = event.get("params", {})
        if (not isinstance(params, dict) or turn_id is None
                or params.get("threadId") != thread_id or params.get("turnId") != turn_id):
            continue
        method = event.get("method")
        if method == "thread/tokenUsage/updated":
            try:
                current = _usage(params["tokenUsage"]["total"])
                if usage and any(current[k] < usage[k] for k in USAGE_FIELDS):
                    raise ValueError("nonmonotonic cumulative usage")
                if current != usage:
                    updates += 1
                usage = current
            except (KeyError, TypeError, ValueError) as exc:
                usage_errors.append(str(exc))
        elif method == "rawResponse/completed":
            ident = params.get("responseId")
            if isinstance(ident, str):
                raw_responses[ident] = {"response_id": ident, "usage": params.get("usage"),
                                        "usage_metadata": params.get("usageMetadata")}
        elif method == "rawResponseItem/completed":
            item = params.get("item", {})
            if isinstance(item, dict) and item.get("type") in {"function_call", "custom_tool_call"}:
                ident = item.get("call_id", item.get("id"))
                if isinstance(ident, str):
                    raw_calls[ident] = {"id": ident, "name": item.get("name"), "type": item.get("type")}
        elif method == "item/completed":
            item = params.get("item", {})
            if not isinstance(item, dict):
                continue
            kind = item.get("type")
            entry = {"ordinal": row["ordinal"], "monotonic": row["monotonic"],
                     "utc": row["utc"], "type": kind, "id": item.get("id")}
            if kind == "mcpToolCall":
                packet = item.get("result")
                size = len(json.dumps(packet, ensure_ascii=False, separators=(",", ":")).encode()) if packet is not None else None
                entry.update(server=item.get("server"), tool=item.get("tool"),
                             arguments=item.get("arguments"), result=item.get("result"),
                             status=item.get("status"), error=item.get("error"),
                             duration_ms=item.get("durationMs"),
                             result_json_bytes=size)
            elif kind == "commandExecution":
                output = item.get("aggregatedOutput")
                size = len(output.encode()) if isinstance(output, str) else None
                entry.update(command=item.get("command"), output=output,
                             output_bytes=size, exit_code=item.get("exitCode"),
                             status=item.get("status"), duration_ms=item.get("durationMs"))
            elif kind == "agentMessage":
                entry["text"] = item.get("text")
                entry["phase"] = item.get("phase")
            elif kind == "subAgentActivity":
                entry.update(kind=item.get("kind"), agent_thread_id=item.get("agentThreadId"))
            elif kind in {"contextCompaction", "fileChange"}:
                entry["changes"] = item.get("changes") if kind == "fileChange" else None
            else:
                continue
            ident = item.get("id")
            if isinstance(ident, str):
                if ident in items:
                    if item_payloads[ident] != item:
                        capture_errors.append(f"conflicting completed item {ident}")
                    continue
                items[ident] = entry
                item_payloads[ident] = item
    trace = list(items.values())
    output_bytes = {"mcp_result_json": sum(x["result_json_bytes"] or 0 for x in trace
                                        if x["type"] == "mcpToolCall"),
                    "shell_aggregated": sum(x["output_bytes"] or 0 for x in trace
                                            if x["type"] == "commandExecution")}
    mcp = [x for x in trace if x["type"] == "mcpToolCall"]
    shell = [x for x in trace if x["type"] == "commandExecution"]
    answers = [x for x in trace if x["type"] == "agentMessage" and isinstance(x.get("text"), str)]
    final = [x for x in answers if x.get("phase") == "final_answer"]
    subagent_starts = sum(x["type"] == "subAgentActivity" and x.get("kind") == "started"
                         for x in trace)
    selected = final[-1] if final else None
    known = completed and usage is not None and not usage_errors and not subagent_starts
    return {"usage_status": "known" if known else "unknown",
            "usage": usage if known else None, "observed_usage_lower_bound": usage,
            "usage_updates": updates,
            "usage_errors": usage_errors, "raw_response_completions": list(raw_responses.values()),
            "capture_errors": capture_errors,
            "completed_response_count_lower_bound": len(raw_responses),
            "outer_tool_calls": list(raw_calls.values()), "navigation_trace": trace,
            "final_answer": selected["text"] if selected else None,
            "last_agent_message": answers[-1]["text"] if answers else None,
            "subagent_starts": subagent_starts,
            "usage_scope": "requested_root_thread_only",
            "mcp_calls": len(mcp), "mcp_failures": sum(
                x.get("status") == "failed" or bool(x.get("error"))
                or (isinstance(x.get("result"), dict) and (
                    x["result"].get("isError") is True
                    or isinstance(x["result"].get("structuredContent"), dict)
                    and bool(x["result"]["structuredContent"].get("error")))) for x in mcp),
            "shell_calls": len(shell), "shell_failures": sum(
                x.get("status") == "failed" or x.get("exit_code") not in (None, 0) for x in shell),
            "context_compactions": sum(x["type"] == "contextCompaction" for x in trace),
            "file_changes": sum(x["type"] == "fileChange" for x in trace),
            "captured_tool_output_bytes": output_bytes,
            "graph_records_status": "not_reduced_see_navigation_trace",
            "delivery_limit": "Native item output is captured; provider context delivery and model reliance are not proven."}


def run_turn(client: AppServer, case: dict, workspace: Path, thread_id: str) -> dict:
    started = time.monotonic()
    deadline = started + case["time_cap_seconds"]
    row: dict = {"status": "runtime_failed", "turn_id": None, "started_monotonic": started}
    try:
        response = client.call("turn/start", {
            "threadId": thread_id, "input": [{"type": "text", "text": case["prompt"]}],
            "cwd": str(workspace), "runtimeWorkspaceRoots": [str(workspace)],
            "permissions": READ_PROFILE, "approvalPolicy": "never",
            "model": case["model"], "effort": case["reasoning_effort"],
        }, timeout=max(0, deadline - time.monotonic()))
        row["turn_id"] = response["turn"]["id"]
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError("300-second turn cap")
            event = client.next_event(remaining)
            if time.monotonic() > deadline:
                raise TimeoutError("300-second turn cap")
            params = event.get("params", {})
            if params.get("threadId") not in (None, thread_id):
                continue
            if params.get("turnId") not in (None, row["turn_id"]):
                continue
            item = params.get("item", {})
            if (event.get("method") in {"item/started", "item/completed"}
                    and item.get("type") == "subAgentActivity" and item.get("kind") == "started"):
                row["isolation_failure"] = True
                raise RuntimeFailure("trial delegated despite disabled agents; root-only usage is incomplete")
            if event.get("method") in {"model/rerouted", "model/verification"}:
                row["identity_failure"] = True
                raise RuntimeFailure("model identity changed or requires verification")
            if event.get("method") == "turn/completed":
                actual = params.get("turn", {})
                if params.get("threadId") != thread_id or actual.get("id") != row["turn_id"]:
                    continue
                row["status"] = actual.get("status", "unknown")
                row["error"] = actual.get("error")
                break
    except TimeoutError as exc:
        row.update(status="timed_out", error=str(exc))
        if row["turn_id"]:
            try:
                client.call("turn/interrupt", {"threadId": thread_id, "turnId": row["turn_id"]}, timeout=1)
            except (RuntimeFailure, TimeoutError) as interrupt_error:
                row["interrupt_error"] = str(interrupt_error)
    except (RuntimeFailure, KeyError, OSError, TypeError, ValueError) as exc:
        row.update(status="runtime_failed", error=str(exc))
    row["elapsed_ms"] = round((time.monotonic() - started) * 1000, 3)
    return row


def execute(output: Path, *, preflight_only: bool = False, graph_toggle: bool = False) -> dict:
    if Path(sys.prefix).resolve() != PYTHON.parent.parent.resolve():
        raise RuntimeError(f"run with {PYTHON}")
    case, digest = load_case()
    conditions = case["conditions"]
    if graph_toggle:
        if conditions["production"] != PRODUCTION_COMMIT:
            raise ValueError("graph toggle requires the frozen production commit")
        conditions = {"graph_on": PRODUCTION_COMMIT, "graph_off": PRODUCTION_COMMIT}
    arms = tuple(conditions)
    output = check_output_location(output, case)
    output.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    output.mkdir(mode=0o700, parents=False, exist_ok=False)
    run_started = time.monotonic()
    result: dict = {"schema_version": 1, "case_id": case["case_id"], "case_sha256": digest,
                    "model": case["model"], "reasoning_effort": case["reasoning_effort"],
                    "preflight_only": preflight_only, "status": "preparing",
                    "arms": {arm: {"preflight": "not_run", "episode": "not_run"} for arm in arms},
                    "limitations": ["One task and one turn per condition; no statistical winner.",
                                    "Prompt cache warmth is uncontrolled; cached and uncached input are separate.",
                                    "No model reliance or unique source-read count is inferred from tool observations."]}
    if graph_toggle:
        result["experiment"] = {
            "id": "production-graph-toggle", "conditions": conditions, "order": list(arms),
            "runtime_flags": {"graph_on": {"graph_enrichment": True},
                              "graph_off": {"graph_enrichment": False}},
            "runtime_binding": "loci.service.RetrievalRuntime",
            "case_sha256": digest, "target_commit": case["source_commit"],
            "time_cap_seconds": case["time_cap_seconds"], "cold_stores": True,
        }
    write_json(output / "result.json", result)
    owned: list[tuple[AppServer | None, Journal]] = []
    live: dict[str, tuple[AppServer, Journal, Path, str]] = {}
    active_arm: str | None = None
    try:
        source = Path(case["source_repository"]).resolve(strict=True)
        for arm in arms:
            directory = output / "arms" / arm
            directory.mkdir(parents=True)
            workspace = directory / "workspace"
            result["arms"][arm]["target"] = archive(source, case["source_commit"], workspace)
            (workspace / ".episode-tmp").mkdir()
            serving = None
            commit = conditions[arm]
            if commit is not None:
                serving = output / "serving" / arm
                repo = ORIGINAL if arm in {"production", "graph_on", "graph_off"} else HARNESS
                serving.parent.mkdir(parents=True, exist_ok=True)
                result["arms"][arm]["serving"] = archive(repo, commit, serving)
            write_json(output / "result.json", result)
        result["setup_elapsed_ms"] = round((time.monotonic() - run_started) * 1000, 3)
        for arm in arms:
            directory = output / "arms" / arm
            workspace = directory / "workspace"
            serving = output / "serving" / arm if arm != "vanilla" else None
            namespace = "pilot-" + arm + "-" + hashlib.sha256(str(output).encode()).hexdigest()[:12]
            overrides = arm_overrides(workspace, arm, serving, namespace)
            instructions, instruction_meta = arm_instructions(case, serving)
            # Preserve a redacted process-local configuration without auth or user env.
            result["arms"][arm]["configuration"] = {
                "profile": READ_PROFILE, "project_doc_max_bytes": 0,
                "loci_enabled": arm != "vanilla", "namespace": namespace if arm != "vanilla" else None,
                "serving": str(serving) if serving else None,
                "store": str(workspace.parent / "loci-store") if serving else None,
                "agents_enabled": False,
                "instructions": instruction_meta}
            if graph_toggle:
                result["arms"][arm]["configuration"]["graph_enrichment"] = arm == "graph_on"
            journal = Journal(directory / "wire.jsonl")
            client = None
            preflight_started = time.monotonic()
            try:
                client = AppServer(command_with_config("codex", overrides), journal,
                                   directory / "stderr.txt", cwd=workspace)
                owned.append((client, journal))
                checked = preflight(client, case, workspace, arm, directory / "hidden-canary",
                                    instructions)
                result["arms"][arm]["preflight"] = checked
                live[arm] = (client, journal, workspace, checked["thread_id"])
            except (RuntimeFailure, OSError, KeyError, TypeError, ValueError, TimeoutError) as exc:
                if client is None:
                    owned.append((None, journal))
                result["arms"][arm]["preflight"] = {"status": "failed", "error": str(exc)}
                if client is not None:
                    client.close()
            result["arms"][arm]["preflight_elapsed_ms"] = round(
                (time.monotonic() - preflight_started) * 1000, 3)
            write_json(output / "result.json", result)
        if any(result["arms"][arm]["preflight"].get("status") != "passed" for arm in arms):
            result["status"] = "preflight_failed_zero_episodes"
        elif preflight_only:
            result["status"] = "preflight_passed_no_generation"
        else:
            result["status"] = "running"
            write_json(output / "result.json", result)
            for arm in arms:
                client, journal, workspace, thread_id = live[arm]
                active_arm = arm
                result["arms"][arm]["episode"] = {"status": "attempted"}
                write_json(output / "result.json", result)
                row = run_turn(client, case, workspace, thread_id)
                client.close()
                row["telemetry"] = summarize_wire(output / "arms" / arm / "wire.jsonl",
                                                   thread_id, row["turn_id"],
                                                   completed=row["status"] == "completed")
                result["arms"][arm]["episode"] = row
                write_json(output / "result.json", result)
                active_arm = None
                if row.get("identity_failure") or row.get("isolation_failure"):
                    break
            result["status"] = "completed" if all(
                isinstance(result["arms"][arm]["episode"], dict)
                and result["arms"][arm]["episode"].get("status") == "completed" for arm in arms
            ) else "episodes_incomplete"
    except (OSError, subprocess.CalledProcessError, tarfile.TarError, RuntimeFailure, ValueError) as exc:
        result["status"] = ("capture_failed" if result["status"] == "running" or any(
            isinstance(result["arms"][arm]["episode"], dict) for arm in arms)
            else "preparation_failed_zero_episodes")
        result["error"] = str(exc)
    except KeyboardInterrupt:
        result["status"] = "interrupted"
        result["error"] = "operator interrupted the pilot"
        if active_arm is not None:
            result["arms"][active_arm]["episode"] = {"status": "interrupted",
                                                      "wire": str(output / "arms" / active_arm / "wire.jsonl")}
    finally:
        cleanup = []
        for client, journal in owned:
            if client is not None:
                client.close()
                cleanup.extend(client.cleanup_errors)
            journal.close()
        if cleanup:
            result["cleanup_errors"] = cleanup
            result["status"] = "cleanup_failed"
        result["total_elapsed_ms"] = round((time.monotonic() - run_started) * 1000, 3)
        write_json(output / "result.json", result)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--preflight-only", action="store_true")
    parser.add_argument("--graph-toggle", action="store_true",
                        help="compare the frozen production graph enrichment on and off")
    parser.add_argument("--serve-target", type=Path, help=argparse.SUPPRESS)
    parser.add_argument("--graph-enrichment", choices=("on", "off"), help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.serve_target is not None:
        if args.output is not None or args.preflight_only or args.graph_toggle:
            parser.error("server mode accepts only --serve-target and --graph-enrichment")
        serve_target(args.serve_target, graph_enrichment=(
            None if args.graph_enrichment is None else args.graph_enrichment == "on"
        ))
        return
    if args.graph_enrichment is not None:
        parser.error("--graph-enrichment requires --serve-target")
    if args.output is None:
        args.output = Path.home() / "phluxxed/tmp" / (
            ("loci-graph-toggle-" if args.graph_toggle else "loci-navigation-pilot-")
            + time.strftime("%Y%m%d-%H%M%S")
        )
    os.umask(0o077)
    receipt = execute(args.output, preflight_only=args.preflight_only, graph_toggle=args.graph_toggle)
    print(json.dumps({"status": receipt["status"], "result": str(args.output / "result.json")}))
    if receipt["status"] not in {"completed", "preflight_passed_no_generation"}:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
