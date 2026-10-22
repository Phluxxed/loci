"""No-generation diagnostic, using the existing complete-work permission profiles.

Never issue turn/start. No MCP server is needed to reproduce command isolation.
Each invocation must use a new observer directory.
"""
from pathlib import Path
import hashlib
import json
import os
import platform
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from benchmarks.complete_work.controller import MODEL, isolation_probe
from benchmarks.complete_work.isolation import READ_PROFILE, build_overrides, verify_profile
from benchmarks.complete_work.runtime import AppServer, Journal, command_with_config

output = Path(sys.argv[1]).resolve()
output.mkdir(parents=True, exist_ok=False)
base = Path(tempfile.mkdtemp(prefix="loci-r01-host-"))
repo = base / "workspace"
repo.mkdir()
(repo / ".complete-work-isolation.json").write_text("{}")
(repo / ".episode-store").mkdir()
config = Path(os.environ.get("CODEX_HOME", str(Path.home() / ".codex"))) / "config.toml"
overrides = build_overrides(repo, [], "/usr/bin/false", [], {}, user_config=config)
overrides["mcp_servers.loci.enabled"] = False
(output / "overrides.json").write_text(json.dumps(overrides, indent=2)+"\n")
executable = Path(shutil.which("codex")).resolve()
receipt = {"schema_version": 1, "kind": "r01_host_no_generation_probe",
           "utc": datetime.now(timezone.utc).isoformat(), "workspace": str(repo),
           "platform": platform.platform(), "codex": str(executable),
           "codex_sha256": hashlib.sha256(executable.read_bytes()).hexdigest(),
           "codex_version": subprocess.check_output([str(executable), "--version"], text=True).strip(),
           "user_config_sha256": hashlib.sha256(config.read_bytes()).hexdigest(),
           "model_generation": False, "errors": []}
journal = Journal(output / "wire.jsonl")
app = None
try:
    app = AppServer(command_with_config(str(executable), overrides), journal,
                    output / "stderr.txt", cwd=repo)
    receipt["initialize"] = app.initialize()
    receipt["profiles"] = app.call("permissionProfile/list", {"cwd": str(repo)})
    receipt["isolation"] = isolation_probe(app, repo, base / "hidden-evaluator-canary")
    # Thread creation loads instructions but does not generate. Match historical
    # model identity, disable fallback and retain any fatal instruction-load error.
    try:
        thread = app.call("thread/start", {
            "cwd": str(repo), "runtimeWorkspaceRoots": [str(repo)],
            "permissions": READ_PROFILE, "approvalPolicy": "never", "model": MODEL,
            "allowProviderModelFallback": False, "ephemeral": True,
            "experimentalRawEvents": True,
        }, timeout=30)
        receipt["thread_start"] = thread
        verify_profile(thread, READ_PROFILE, repo)
    except Exception as exc:
        receipt["errors"].append(str(exc))
except Exception as exc:
    receipt["errors"].append(str(exc))
finally:
    if app is not None:
        app.close()
        receipt["cleanup_errors"] = app.cleanup_errors
    journal.close()
records = [json.loads(line) for line in (output / "wire.jsonl").read_text().splitlines()]
receipt["submitted_turns"] = sum(r["direction"] == "sent" and r["message"].get("method") == "turn/start" for r in records)
assert receipt["submitted_turns"] == 0
receipt["status"] = ("isolation_passed_no_generation" if receipt.get("isolation", {}).get("status") == "passed" and not receipt["errors"] else "unqualified")
receipt["files"] = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in output.iterdir() if p.is_file()}
(output / "result.json").write_text(json.dumps(receipt, indent=2)+"\n")
print(json.dumps({k: receipt.get(k) for k in ("status", "isolation", "submitted_turns", "errors")}))
