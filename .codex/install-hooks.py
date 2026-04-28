#!/usr/bin/env python3
"""
Install loci Codex hooks.

Symlinks the repo hooks into ~/.codex/hooks/ and patches ~/.codex/hooks.json
to register the SessionStart hook.
"""

from __future__ import annotations

import json
import os
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent
REPO_HOOKS = REPO_ROOT / "hooks"
CODEX_HOME = Path(os.environ.get("CODEX_HOME", Path.home() / ".codex"))
CODEX_HOOKS = CODEX_HOME / "hooks"
HOOKS_JSON = CODEX_HOME / "hooks.json"

SESSION_START_HOOK = {
    "type": "command",
    "command": str(CODEX_HOOKS / "loci-session-start.sh"),
    "timeout": 30,
    "statusMessage": "indexing repo with loci",
}


def symlink_hooks() -> None:
    CODEX_HOOKS.mkdir(parents=True, exist_ok=True)
    for hook in REPO_HOOKS.glob("*.sh"):
        dest = CODEX_HOOKS / hook.name
        if dest.exists() or dest.is_symlink():
            dest.unlink()
        dest.symlink_to(hook.resolve())
        dest.chmod(0o755)
        print(f"  linked: {dest} -> {hook.resolve()}")


def load_config() -> dict:
    if not HOOKS_JSON.exists():
        return {"hooks": {}}
    return json.loads(HOOKS_JSON.read_text())


def hook_present(hooks: list[dict], command: str) -> bool:
    return any(hook.get("command") == command for hook in hooks)


def patch_hooks_json() -> None:
    cfg = load_config()
    cfg.setdefault("hooks", {})
    session_entries = cfg["hooks"].setdefault("SessionStart", [])
    changed = False

    if session_entries:
        entry = session_entries[0]
    else:
        entry = {"matcher": "startup|resume|clear|compact", "hooks": []}
        session_entries.append(entry)
        changed = True

    entry.setdefault("matcher", "startup|resume|clear|compact")
    entry.setdefault("hooks", [])

    if not hook_present(entry["hooks"], SESSION_START_HOOK["command"]):
        entry["hooks"].append(SESSION_START_HOOK)
        changed = True

    CODEX_HOME.mkdir(parents=True, exist_ok=True)
    if changed:
        HOOKS_JSON.write_text(json.dumps(cfg, indent=2) + "\n")
        print(f"  updated: {HOOKS_JSON}")
    else:
        print("  hooks.json already up to date")


def main() -> None:
    print("Installing loci Codex hooks...\n")
    print("Symlinking hooks:")
    symlink_hooks()
    print("\nPatching hooks.json:")
    patch_hooks_json()
    print("\nDone.")


if __name__ == "__main__":
    main()
