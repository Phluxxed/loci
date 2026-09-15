"""Fixed three-turn controller. Measured execution requires a verified freeze.

This module never evaluates an answer to decide the next prompt. Its only
branches are normal completion, explicit runtime failure and a fixed deadline.
"""
from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import sys
import time
from typing import Callable

from .accounting import summarize
from .isolation import READ_PROFILE, WRITE_PROFILE, build_overrides, verify_profile
from .runtime import AppServer, Journal, RuntimeFailure, command_with_config

MODEL = "gpt-5.6-terra"
EFFORT = "high"
IGNORED = {".git", "node_modules", ".venv", ".episode-tmp", ".episode-store"}


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def write_json(path: Path, value: dict) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n")
    temporary.replace(path)


def source_snapshot(repo: Path, destination: Path) -> dict:
    """Retain actual source bytes, excluding only declared runtime/dependency data."""
    files = {}
    total = 0
    paths = []
    for directory, children, filenames in os.walk(repo, followlinks=False):
        children[:] = sorted(x for x in children if x not in IGNORED)
        for name in [*children, *filenames]:
            if name not in IGNORED:
                paths.append(Path(directory) / name)
    for path in sorted(paths):
        relative = path.relative_to(repo)
        if path.is_symlink():
            raise RuntimeFailure(f"unexpected source symlink: {relative}")
        if not path.is_file():
            continue
        data = path.read_bytes()
        total += len(data)
        if len(data) > 32 * 1024 * 1024 or total > 256 * 1024 * 1024:
            raise RuntimeFailure("source snapshot bound exceeded")
        digest = sha(data)
        files[relative.as_posix()] = digest
        target = destination / "blobs" / digest
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.exists():
            target.write_bytes(data)
        elif sha(target.read_bytes()) != digest:
            raise RuntimeFailure("source archive content address mismatch")
    return {"files": files, "content_bytes": total,
            "sha256": sha(json.dumps(files, sort_keys=True).encode())}


def verify_freeze(path: Path, expected_sha256: str, required: list[Path]) -> dict:
    raw = path.read_bytes()
    if sha(raw) != expected_sha256:
        raise RuntimeFailure("campaign freeze identity differs")
    value = json.loads(raw)
    if value.get("kind") != "complete-work-campaign-freeze" or value.get("schema_version") != 1:
        raise RuntimeFailure("not a complete-work campaign freeze")
    files = value.get("files")
    if not isinstance(files, dict) or not files:
        raise RuntimeFailure("freeze has no input identities")
    paths = {}
    for name, expected in files.items():
        candidate = Path(name)
        candidate = candidate if candidate.is_absolute() else path.parent / candidate
        candidate = candidate.resolve(strict=True)
        if candidate in paths or sha(candidate.read_bytes()) != expected:
            raise RuntimeFailure(f"frozen input differs: {name}")
        paths[candidate] = expected
    if any(p.resolve() not in paths for p in required):
        raise RuntimeFailure("freeze omits a required controller/design/run input")
    return value


def load_run_config(path: Path) -> tuple[dict, dict, list[dict]]:
    config = json.loads(path.read_text())
    if config.get("schema_version") != 1:
        raise RuntimeFailure("invalid run configuration version")
    if config.get("dependencies_status") != "prepared":
        raise RuntimeFailure("target dependencies have not been prepared and verified")
    if config.get("preindex", {}).get("status") != "prepared":
        raise RuntimeFailure("target index has not been prepared before the episode")
    repo = Path(config["repo"]).resolve(strict=True)
    serving = Path(config["serving_root"]).resolve(strict=True)
    output = Path(config["output_dir"]).resolve()
    if (repo.is_relative_to(serving) or serving.is_relative_to(repo)
            or output.is_relative_to(repo) or repo.is_relative_to(output)):
        raise RuntimeFailure("source, serving code and observer output are not isolated")
    hidden = [serving / "benchmarks", serving / ".scratch", output.parent,
              Path(config["episodes_path"]).parent, Path(config["schedule_path"]).parent]
    for name in config["readonly_roots"]:
        dependency = Path(name).resolve(strict=True)
        if any(p.resolve().is_relative_to(dependency) or dependency.is_relative_to(p.resolve())
               for p in hidden):
            raise RuntimeFailure("dependency read permission exposes hidden observer inputs")
    marker = json.loads((repo / ".complete-work-isolation.json").read_text())
    if marker.get("run_id") != config["run_id"]:
        raise RuntimeFailure("isolated target does not belong to this episode")
    definitions = json.loads(Path(config["episodes_path"]).read_text())
    schedule = json.loads(Path(config["schedule_path"]).read_text())
    rows = [x for x in schedule["rows"] if x["episode_run_id"] == config["run_id"]]
    if len(rows) != 1:
        raise RuntimeFailure("run must occur exactly once in the designed schedule")
    row = rows[0]
    if row["model"] != MODEL or row["effort"] != EFFORT or row["fork"] != "none":
        raise RuntimeFailure("requested worker settings differ from the fixed design")
    if row["graph_enrichment"] != config["arm"]:
        raise RuntimeFailure("run arm differs from schedule")
    cases = [x for x in definitions["episodes"] if x["id"] == row["episode_id"]]
    if len(cases) != 1:
        raise RuntimeFailure("episode definition missing or duplicated")
    stages = []
    for index, stage in enumerate(cases[0]["stages"]):
        if sha(stage["prompt"].encode()) != stage["prompt_sha256"]:
            raise RuntimeFailure("stage prompt differs from its design identity")
        prefix = (definitions["common_initial_prompt_template"].format(repo=repo)
                  if index == 0 else "")
        stages.append({"stage_id": stage["id"], "prompt": prefix + stage["prompt"],
                       "cap_seconds": stage["cap_seconds"]})
    if ([s["stage_id"] for s in stages] != ["orient", "implement", "continue"]
            or [s["cap_seconds"] for s in stages] != [120, 360, 240]):
        raise RuntimeFailure("stage schedule differs from the selected design")
    return config, row, stages


def isolation_probe(client: AppServer, repo: Path, hidden: Path) -> dict:
    """Prove visibility/write boundaries without a model request or private read."""
    visible = repo / ".episode-tmp" / "visible-canary"
    visible.parent.mkdir(exist_ok=True)
    visible.write_text("visible-canary")
    hidden.write_text("hidden-evaluator-canary")
    protected = repo / ".complete-work-isolation.json"
    original_protected = protected.read_bytes()
    writable = repo / "complete-work-write-canary"
    # Never probe actual denied user directories: this tests our own canaries.
    script = (
        "from pathlib import Path; import json; r={};\n"
        f"for k,p in {repr({'visible': str(visible), 'hidden': str(hidden)})}.items():\n"
        " try:r[k]=Path(p).read_text()\n"
        " except OSError:r[k]='denied'\n"
        f"for k,p in {repr({'source_write': str(writable), 'protected_write': str(protected)})}.items():\n"
        " try:\n"
        "  with Path(p).open('ab'):pass\n"
        "  r[k]='allowed'\n"
        " except OSError:r[k]='denied'\n"
        "print(json.dumps(r))"
    )
    result = client.call("command/exec", {
        "command": ["/usr/bin/python3", "-c", script], "cwd": str(repo),
        "permissionProfile": READ_PROFILE, "timeoutMs": 10000,
    }, timeout=15)
    if result.get("exitCode") != 0:
        return {"status": "unavailable", "reason": "native sandbox could not execute",
                "command_result": result}
    try:
        values = json.loads(result["stdout"])
    except (KeyError, ValueError):
        values = {}
    expected = {"visible": "visible-canary", "hidden": "denied",
                "source_write": "denied", "protected_write": "denied"}
    passed = values == expected
    writable.unlink(missing_ok=True)
    write_result = client.call("command/exec", {
        "command": ["/usr/bin/python3", "-c", script], "cwd": str(repo),
        "permissionProfile": WRITE_PROFILE, "timeoutMs": 10000,
    }, timeout=15)
    try:
        write_values = json.loads(write_result.get("stdout", ""))
    except ValueError:
        write_values = {}
    expected["source_write"] = "allowed"
    passed = (passed and write_result.get("exitCode") == 0 and write_values == expected
              and protected.read_bytes() == original_protected)
    writable.unlink(missing_ok=True)
    return {"status": "passed" if passed else "failed", "observed": values,
            "write_observed": write_values, "command_result": result,
            "write_command_result": write_result}


def run_stages(client: AppServer, journal: Journal, thread_id: str,
               repo: Path, stages: list[dict], output: Path,
               *, clock: Callable[[], float] = time.monotonic) -> list[dict]:
    """Transport-driven state machine; fake transports can exercise every branch."""
    rows = []
    stopped = False
    for index, stage in enumerate(stages):
        base = {"stage_id": stage["stage_id"], "turn_id": None,
                "prompt_sha256": sha(stage["prompt"].encode()),
                "cap_seconds": stage["cap_seconds"]}
        if stopped:
            rows.append({**base, "outcome": "not_reached", "elapsed_ms": None})
            write_json(output / "stages.json", {"stages": rows})
            continue
        start = clock()
        journal.write("controller", {"event": "stage_submitted", **base})
        row = {**base, "started_monotonic": start, "outcome": "runtime_failed"}
        deadline = start + stage["cap_seconds"]
        try:
            response = client.call("turn/start", {
                "threadId": thread_id,
                "input": [{"type": "text", "text": stage["prompt"]}],
                "cwd": str(repo), "runtimeWorkspaceRoots": [str(repo)],
                "model": MODEL, "effort": EFFORT, "approvalPolicy": "never",
                "permissions": READ_PROFILE if index == 0 else WRITE_PROFILE,
            }, timeout=max(0, deadline - clock()))
            turn = response.get("turn", {})
            if not isinstance(turn.get("id"), str):
                raise RuntimeFailure("turn/start returned no turn identity")
            row["turn_id"] = turn["id"]
            journal.write("controller", {"event": "stage_turn_bound", **row})
            while True:
                remaining = deadline - clock()
                if remaining <= 0:
                    raise TimeoutError("stage deadline")
                event = client.next_event(remaining)
                if clock() > deadline:
                    raise TimeoutError("stage deadline")
                params = event.get("params", {})
                if event.get("method") == "turn/completed":
                    actual = params.get("turn", {})
                    if params.get("threadId") != thread_id or actual.get("id") != row["turn_id"]:
                        raise RuntimeFailure("completion identity differs from active turn")
                    row["outcome"] = actual.get("status", "unknown")
                    row["error"] = actual.get("error")
                    break
                if event.get("method") in ("model/rerouted", "model/verification"):
                    raise RuntimeFailure("runtime model changed or needs verification")
        except TimeoutError as exc:
            row["outcome"] = "timed_out"
            row["error"] = str(exc)
            if row["turn_id"]:
                # Interrupt once. The caller then closes this owned process;
                # neither action creates a replacement episode.
                try:
                    client.call("turn/interrupt", {"threadId": thread_id,
                                "turnId": row["turn_id"]}, timeout=1)
                except (RuntimeFailure, TimeoutError) as interrupt_error:
                    row["interrupt_error"] = str(interrupt_error)
        except (RuntimeFailure, OSError, ValueError, TypeError) as exc:
            row["outcome"] = "runtime_failed"
            row["error"] = str(exc)
        rows.append(row)
        stopped = row["outcome"] != "completed"
        if stopped:
            client.close()
        row["ended_monotonic"] = clock()
        row["elapsed_ms"] = round((row["ended_monotonic"] - start) * 1000, 3)
        row["deadline_overrun_ms"] = max(0, row["elapsed_ms"] - 1000 * stage["cap_seconds"])
        try:
            snap = source_snapshot(repo, output / "source-history")
            write_json(output / f"source-after-{stage['stage_id']}.json", snap)
            row["source_snapshot_sha256"] = snap["sha256"]
            if index == 0:
                before = json.loads((output / "source-before.json").read_text())
                if before["files"] != snap["files"]:
                    row["outcome"] = "protocol_violation"
                    row["error"] = "source changed during read-only orientation"
                    stopped = True
                    client.close()
        except (RuntimeFailure, OSError, ValueError) as exc:
            row["outcome"] = "capture_failed"
            row["snapshot_error"] = str(exc)
            stopped = True
            client.close()
        journal.write("controller", {"event": "stage_finished", **row})
        write_json(output / "stages.json", {"stages": rows})
    return rows


def _execute(config_path: Path, *, preflight_only: bool = False,
            freeze_path: Path | None = None, freeze_sha256: str | None = None) -> dict:
    config, scheduled, stages = load_run_config(config_path)
    actual_config = Path(os.environ.get("CODEX_HOME", str(Path.home() / ".codex"))) / "config.toml"
    if Path(config["user_config"]).resolve() != actual_config.resolve():
        raise RuntimeFailure("inspected user_config differs from the config loaded by Codex")
    repo = Path(config["repo"]).resolve()
    output = Path(config["output_dir"])
    if preflight_only:
        output = output.with_name(output.name + "-preflight")
    if not preflight_only:
        if freeze_path is None or freeze_sha256 is None:
            raise RuntimeFailure("measured execution requires a published campaign freeze")
        required = [config_path, Path(config["episodes_path"]), Path(config["schedule_path"]),
                    *(p for p in Path(__file__).parent.rglob("*")
                      if p.is_file() and "__pycache__" not in p.parts),
                    *(p for p in (Path(config["serving_root"]) / "src").rglob("*")
                      if p.is_file() and "__pycache__" not in p.parts),
                    Path(config["mcp_config_path"]), Path(config["instruction_text_path"]),
                    Path(config["user_config"]),
                    *(Path(p) for p in config.get("frozen_inputs", []))]
        verify_freeze(freeze_path, freeze_sha256, required)
    output.mkdir(parents=True, exist_ok=False)
    (repo / ".episode-tmp").mkdir(exist_ok=True)
    (repo / ".episode-store").mkdir(exist_ok=True)
    before = source_snapshot(repo, output / "source-history")
    marker = json.loads((repo / ".complete-work-isolation.json").read_text())
    expected_files = marker["source_files"]
    actual_files = {k: v for k, v in before["files"].items() if k != ".complete-work-isolation.json"}
    if actual_files != expected_files:
        raise RuntimeFailure("prepared source was modified before the episode")
    write_json(output / "source-before.json", before)
    overrides = build_overrides(
        repo, [Path(p) for p in config["readonly_roots"]],
        config["mcp_command"], config["mcp_args"], config["mcp_env"],
        user_config=Path(config["user_config"]),
    )
    write_json(output / "runtime-overrides.json", overrides)
    journal = Journal(output / "wire.jsonl")
    client = None
    result: dict = {"schema_version": 1, "run_id": config["run_id"],
                    "episode_id": scheduled["episode_id"], "arm": config["arm"],
                    "measured": not preflight_only, "status": "runtime_unavailable",
                    "correct": None, "stages": [], "errors": []}
    started = None
    try:
        client = AppServer(command_with_config(config.get("codex", "codex"), overrides),
                           journal, output / "stderr.txt", cwd=repo)
        result["initialize"] = client.initialize()
        catalog = client.call("model/list", {"includeHidden": True, "limit": 100})
        result["models"] = catalog
        matches = [x for x in catalog.get("data", []) if x.get("model") == MODEL]
        if not matches or not any(x.get("reasoningEffort") == EFFORT
                                  for x in matches[0].get("supportedReasoningEfforts", [])):
            raise RuntimeFailure("pinned Terra/high is not advertised by this runtime")
        thread = client.call("thread/start", {
            "cwd": str(repo), "runtimeWorkspaceRoots": [str(repo)],
            "permissions": READ_PROFILE, "approvalPolicy": "never",
            "model": MODEL, "allowProviderModelFallback": False,
            "ephemeral": False, "experimentalRawEvents": True,
            "developerInstructions": Path(config["instruction_text_path"]).read_text(),
        }, timeout=90)
        result["thread_start"] = thread
        if thread.get("model") != MODEL:
            raise RuntimeFailure("runtime selected a different model")
        verify_profile(thread, READ_PROFILE, repo)
        thread_id = thread["thread"]["id"]
        result["thread_id"] = thread_id
        inventory = client.call("mcpServerStatus/list", {"threadId": thread_id, "limit": 100})
        result["mcp_inventory"] = inventory
        servers = inventory.get("data", [])
        active = [x for x in servers if x.get("tools")]
        if len(active) != 1 or active[0].get("name") != "loci":
            raise RuntimeFailure("unexpected or missing MCP tool surface")
        names = set(active[0]["tools"])
        if names != {"loci_retrieve", "loci_read"}:
            raise RuntimeFailure("MCP tool inventory differs from the matched surface")
        result["isolation"] = isolation_probe(client, repo, output / "hidden-canary")
        if result["isolation"]["status"] != "passed":
            raise RuntimeFailure("native filesystem isolation preflight did not pass")
        if preflight_only:
            result["status"] = "preflight_passed_no_generation"
        else:
            started = time.monotonic()
            result["stages"] = run_stages(client, journal, thread_id, repo, stages, output)
            result["elapsed_ms"] = round((time.monotonic() - started) * 1000, 3)
            result["status"] = ("completed" if all(x["outcome"] == "completed" for x in result["stages"])
                                else "unsuccessful")
    except (RuntimeFailure, OSError, ValueError, KeyError, TypeError, TimeoutError) as exc:
        result["errors"].append(str(exc))
        if started is not None:
            result["elapsed_ms"] = round((time.monotonic() - started) * 1000, 3)
            result["status"] = "unsuccessful"
    finally:
        if client is not None:
            client.close()
            result["cleanup_errors"] = getattr(client, "cleanup_errors", [])
        journal.close()
        if started is not None:
            closed_at = time.monotonic()
            result["complete_wall_ms"] = round((closed_at - started) * 1000, 3)
            if not result["stages"] and (output / "stages.json").exists():
                result["stages"] = json.loads((output / "stages.json").read_text())["stages"]
            reached = [x for x in result["stages"] if x.get("ended_monotonic") is not None]
            if reached:
                episode_start = reached[0]["started_monotonic"]
                episode_end = reached[-1]["ended_monotonic"]
                result["elapsed_ms"] = round((episode_end - episode_start) * 1000, 3)
                result["post_episode_capture_cleanup_ms"] = round((closed_at - episode_end) * 1000, 3)
            else:
                result["elapsed_ms"] = None
            result["controller_delay_ms"] = max(0, result["elapsed_ms"] - sum(
                x.get("elapsed_ms") or 0 for x in result["stages"])) if reached else None
    if result.get("thread_id") and result["stages"]:
        result["accounting"] = summarize(output / "wire.jsonl", result["stages"], result["thread_id"])
        from .evidence import summarize_delivery
        control = json.loads(Path(config["mcp_config_path"]).read_text())
        result["delivery"] = summarize_delivery(Path(control["receipt_dir"]), result["accounting"])
    if result.get("cleanup_errors"):
        result["status"] = "cleanup_failed"
        result["errors"].extend(result["cleanup_errors"])
        if "accounting" in result:
            result["accounting"]["usage_status"] = "unknown"
            result["accounting"]["usage"] = None
    result["limitations"] = [
        "This receipt is not an independent behavioral grade or final Objective acceptance.",
        "Deadline cleanup and overrun are retained; none are silently removed from wall time.",
        "Measured generation is forbidden without exact freeze inputs; preflight makes no model turn.",
    ]
    write_json(output / "result.json", result)
    return result


def execute(config_path: Path, *, preflight_only: bool = False,
            freeze_path: Path | None = None, freeze_sha256: str | None = None) -> dict:
    if preflight_only:
        return _execute(config_path, preflight_only=True)
    if freeze_path is None or freeze_sha256 is None:
        raise RuntimeFailure("measured execution requires a published campaign freeze")
    # One lock per campaign protects all eight configs. Exclusive output creation
    # separately forbids reusing a consumed episode identity after interruption.
    with freeze_path.with_suffix(".execution.lock").open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise RuntimeFailure("another measured episode is running") from exc
        return _execute(config_path, freeze_path=freeze_path, freeze_sha256=freeze_sha256)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("preflight", "run"))
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--freeze", type=Path)
    parser.add_argument("--freeze-sha256")
    args = parser.parse_args()
    result = execute(args.config, preflight_only=args.operation == "preflight",
                     freeze_path=args.freeze, freeze_sha256=args.freeze_sha256)
    print(json.dumps({k: result.get(k) for k in
                      ("run_id", "status", "measured", "elapsed_ms", "errors")}))
    if result["status"] not in ("completed", "preflight_passed_no_generation"):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
