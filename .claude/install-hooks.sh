#!/usr/bin/env python3
"""
Install loci Claude Code hooks and skill files.

Symlinks hooks and skills from this repo into ~/.claude/ and patches
~/.claude/settings.json to register them.
"""

import json
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).parent
REPO_HOOKS = REPO_ROOT / "hooks"
REPO_SKILLS = REPO_ROOT / "skills" / "loci"
CLAUDE_DIR = Path.home() / ".claude"
CLAUDE_HOOKS = CLAUDE_DIR / "hooks"
CLAUDE_SKILLS = CLAUDE_DIR / "skills" / "loci"
SETTINGS = CLAUDE_DIR / "settings.json"

SESSION_START_HOOK = {
    "type": "command",
    "command": f"bash {CLAUDE_HOOKS}/loci-session-start.sh",
    "timeout": 30,
}

AGENT_INJECT_HOOK = {
    "type": "command",
    "command": f"bash {CLAUDE_HOOKS}/loci-agent-inject.sh",
    "timeout": 5,
}


def symlink_hooks() -> None:
    CLAUDE_HOOKS.mkdir(parents=True, exist_ok=True)
    for hook in REPO_HOOKS.glob("*.sh"):
        dest = CLAUDE_HOOKS / hook.name
        if dest.exists() or dest.is_symlink():
            dest.unlink()
        dest.symlink_to(hook.resolve())
        dest.chmod(0o755)
        print(f"  linked: {dest} -> {hook.resolve()}")


def symlink_skills() -> None:
    CLAUDE_SKILLS.mkdir(parents=True, exist_ok=True)
    for skill_file in REPO_SKILLS.glob("*.md"):
        dest = CLAUDE_SKILLS / skill_file.name
        if dest.exists() or dest.is_symlink():
            dest.unlink()
        dest.symlink_to(skill_file.resolve())
        print(f"  linked: {dest} -> {skill_file.resolve()}")


def _hook_present(hooks: list, command_fragment: str) -> bool:
    return any(command_fragment in h.get("command", "") for h in hooks)


def patch_settings() -> None:
    if not SETTINGS.exists():
        print(f"  settings.json not found at {SETTINGS} — skipping patch")
        print("  Create it manually and add the hooks shown in README.md.")
        return

    with open(SETTINGS) as f:
        cfg = json.load(f)

    cfg.setdefault("hooks", {})
    changed = False

    # SessionStart — add to startup, resume, and clear matchers
    cfg["hooks"].setdefault("SessionStart", [])
    for matcher in ("startup", "resume", "clear"):
        entry = next(
            (e for e in cfg["hooks"]["SessionStart"] if e.get("matcher") == matcher),
            None,
        )
        if entry is None:
            entry = {"matcher": matcher, "hooks": []}
            cfg["hooks"]["SessionStart"].append(entry)
        if not _hook_present(entry["hooks"], "loci-session-start"):
            entry["hooks"].append(SESSION_START_HOOK)
            changed = True
            print(f"  added loci-session-start to SessionStart[{matcher}]")

    # PreToolUse — add to Agent matcher
    cfg["hooks"].setdefault("PreToolUse", [])
    agent_entry = next(
        (e for e in cfg["hooks"]["PreToolUse"] if e.get("matcher") == "Agent"),
        None,
    )
    if agent_entry is None:
        agent_entry = {"matcher": "Agent", "hooks": []}
        cfg["hooks"]["PreToolUse"].append(agent_entry)
    if not _hook_present(agent_entry["hooks"], "loci-agent-inject"):
        agent_entry["hooks"].append(AGENT_INJECT_HOOK)
        changed = True
        print("  added loci-agent-inject to PreToolUse[Agent]")

    if changed:
        with open(SETTINGS, "w") as f:
            json.dump(cfg, f, indent=2)
        print(f"  updated: {SETTINGS}")
    else:
        print("  settings.json already up to date — nothing to change")


def main() -> None:
    print("Installing loci Claude Code hooks and skills...\n")

    print("Symlinking hooks:")
    symlink_hooks()

    print("\nSymlinking skills:")
    symlink_skills()

    print("\nPatching settings.json:")
    patch_settings()

    print("\nDone. Restart Claude Code for the hooks to take effect.")


if __name__ == "__main__":
    main()
