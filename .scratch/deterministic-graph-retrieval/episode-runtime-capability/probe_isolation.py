"""Read-only capability check of a narrower nested Codex permission profile."""
from pathlib import Path
import json
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from benchmarks.complete_work.runtime import AppServer, Journal, command_with_config
from benchmarks.complete_work.isolation import build_overrides, READ_PROFILE

base = Path(tempfile.mkdtemp(prefix="loci-episode-isolation-"))
work = base / "workspace"
work.mkdir()
(work / ".episode-tmp").mkdir()
(work / ".episode-store").mkdir()
hidden = base / "oracle"
hidden.write_text("hidden-canary")
(work / "visible").write_text("visible-canary")
logs = base / "logs"
logs.mkdir()
journal = Journal(logs / "wire.jsonl")
overrides = build_overrides(work, [], "/usr/bin/false", [], {},
                           user_config=Path("/Users/brummerv/.codex/config.toml"))
overrides["mcp_servers.loci.enabled"] = False
app = AppServer(command_with_config("codex", overrides), journal,
                logs / "stderr.txt", cwd=work)
try:
    app.initialize()
    profiles = app.call("permissionProfile/list", {"cwd": str(work)})
    script = "from pathlib import Path; import json; r={};\nfor p in " + repr([
        str(work / "visible"), str(hidden)]) + ":\n try:r[p]=Path(p).read_text()\n except OSError as e:r[p]=type(e).__name__\nprint(json.dumps(r))"
    result = app.call("command/exec", {"command": ["/usr/bin/python3", "-c", script],
        "cwd": str(work), "permissionProfile": READ_PROFILE, "timeoutMs": 10000}, timeout=15)
    receipt = {"base": str(base), "profiles": profiles, "read_check": result,
               "model_generation": False}
    output = Path(__file__).with_name("isolation-native.json")
    output.write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps({"read_check": result, "saved": str(output)}))
finally:
    app.close()
    journal.close()
