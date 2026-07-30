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

ENFORCE_READ_HOOK = {
    "type": "command",
    "command": f"{CLAUDE_HOOKS}/loci-enforce-read.py",
    "timeout": 12,
}


def symlink_hooks() -> None:
    CLAUDE_HOOKS.mkdir(parents=True, exist_ok=True)
    # .sh hooks invoked via `bash <path>` and .py hooks invoked directly via
    # their shebang — both need symlinking + execute bit.
    for hook in list(REPO_HOOKS.glob("*.sh")) + list(REPO_HOOKS.glob("*.py")):
        dest = CLAUDE_HOOKS / hook.name
        if dest.exists() or dest.is_symlink():
            dest.unlink()
        dest.symlink_to(hook.resolve())
        # chmod the source so the symlink is executable via shebang too.
        hook.chmod(0o755)
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

    # PreToolUse — whole-file Read and answer-equivalent simple cat enforcement.
    for matcher in ("Read", "Bash"):
        enforce_entry = next(
            (e for e in cfg["hooks"]["PreToolUse"] if e.get("matcher") == matcher),
            None,
        )
        if enforce_entry is None:
            enforce_entry = {"matcher": matcher, "hooks": []}
            cfg["hooks"]["PreToolUse"].append(enforce_entry)
        existing_index = next(
            (
                index
                for index, hook in enumerate(enforce_entry["hooks"])
                if "loci-enforce-read" in hook.get("command", "")
            ),
            None,
        )
        if existing_index is None:
            enforce_entry["hooks"].append(ENFORCE_READ_HOOK)
            changed = True
            print(f"  added loci-enforce-read to PreToolUse[{matcher}]")
        elif enforce_entry["hooks"][existing_index] != ENFORCE_READ_HOOK:
            enforce_entry["hooks"][existing_index] = ENFORCE_READ_HOOK
            changed = True
            print(f"  updated loci-enforce-read in PreToolUse[{matcher}]")

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
