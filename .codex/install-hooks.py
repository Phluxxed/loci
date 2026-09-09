#!/usr/bin/env python3
"""
Install loci Codex hooks.

Symlinks the repo hooks into ~/.codex/hooks/ and patches ~/.codex/hooks.json
to register the SessionStart hook.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path


CODEX_INSTALLER_DIR = Path(__file__).resolve().parent
REPO_ROOT = CODEX_INSTALLER_DIR.parent
REPO_HOOKS = CODEX_INSTALLER_DIR / "hooks"
REPO_SKILL = REPO_ROOT / "skills" / "loci"
CODEX_HOME = Path(os.environ.get("CODEX_HOME", Path.home() / ".codex"))
CODEX_HOOKS = CODEX_HOME / "hooks"
CODEX_SKILL = CODEX_HOME / "skills" / "loci"
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


def symlink_skill() -> None:
    """Link the repo's Loci skill into the Codex skill directory safely."""
    source = REPO_SKILL.resolve()
    if not source.is_dir():
        raise RuntimeError(f"Loci skill source does not exist: {source}")

    if CODEX_SKILL.is_symlink():
        if CODEX_SKILL.resolve(strict=False) == source:
            print(f"  skill already linked: {CODEX_SKILL} -> {source}")
            return
        CODEX_SKILL.unlink()
    elif CODEX_SKILL.exists():
        raise RuntimeError(
            f"refusing to replace existing file or directory at {CODEX_SKILL}; "
            "move it aside and rerun the installer"
        )

    CODEX_SKILL.parent.mkdir(parents=True, exist_ok=True)
    try:
        CODEX_SKILL.symlink_to(source, target_is_directory=True)
    except FileExistsError as exc:
        raise RuntimeError(
            f"could not install the Loci skill at {CODEX_SKILL}: "
            "another path appeared during installation"
        ) from exc
    print(f"  linked skill: {CODEX_SKILL} -> {source}")


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


def main() -> int:
    print("Installing loci Codex integration...\n")
    try:
        print("Symlinking skill:")
        symlink_skill()
        print("\nSymlinking hooks:")
        symlink_hooks()
        print("\nPatching hooks.json:")
        patch_hooks_json()
    except (OSError, RuntimeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print("\nDone.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
