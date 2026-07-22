#!/usr/bin/env python3
"""PreToolUse hook for Read: blocks whole-file reads of source files in
loci-indexed repos.

Forces compliance with the CLAUDE.md rule: use `loci_outline` then either
`loci_get` (for understanding) or a targeted `Read offset=line limit=N`
(for editing) instead of slurping a whole .py/.ts/.tsx/.js/.go/.rs file.

The targeted-read passthrough is what makes `Edit` work on indexed files —
Edit demands a prior Read receipt on the path, and a Read with explicit
offset+limit satisfies that without losing loci's token-efficiency win for
exploration.

Store resolution mirrors the Claude session-start hook: LOCI_BASE_DIR if set,
else ~/.claude/loci-index. That is Claude Code's own store; the hook never
reads codex's store or the legacy ~/.codeindex. If LOCI_STORE_NAMESPACE is set
and the store's identity marker names a different namespace, the hook fails
open rather than enforce against a store that is not this harness's own —
matching loci's MCP store-isolation contract.

Outputs JSON per Claude Code PreToolUse hook spec:
  - permissionDecision "deny" with a reason that points the agent at loci
  - otherwise exits silently (allow)
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import NoReturn

LOCI_EXTS = {".py", ".ts", ".tsx", ".js", ".go", ".rs"}
STORE_IDENTITY_FILE = ".loci-store.json"


def allow() -> NoReturn:
    sys.exit(0)


def deny(reason: str) -> NoReturn:
    out = {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason,
        }
    }
    print(json.dumps(out))
    sys.exit(0)


def store_base_dir() -> Path:
    env = os.environ.get("LOCI_BASE_DIR")
    if env:
        return Path(env).expanduser()
    return Path.home() / ".claude" / "loci-index"


def store_namespace(base_dir: Path) -> str | None:
    try:
        marker = json.loads((base_dir / STORE_IDENTITY_FILE).read_text())
        return marker.get("namespace")
    except Exception:
        return None


def indexed_repos(base_dir: Path) -> list[str]:
    repos = []
    if not base_dir.is_dir():
        return repos
    for entry in base_dir.iterdir():
        if not entry.is_dir():
            continue
        index_file = entry / "index.json"
        if not index_file.exists():
            continue
        try:
            data = json.loads(index_file.read_text())
            rp = data.get("repo_path", "")
            if rp:
                repos.append(os.path.realpath(rp))
        except Exception:
            continue
    return repos


def main():
    try:
        payload = json.load(sys.stdin)
    except Exception:
        allow()

    if payload.get("tool_name") != "Read":
        allow()

    tool_input = payload.get("tool_input") or {}
    file_path = tool_input.get("file_path", "")
    if not file_path:
        allow()

    ext = os.path.splitext(file_path)[1].lower()
    if ext not in LOCI_EXTS:
        allow()

    base_dir = store_base_dir()

    # Store isolation: if this harness declares a namespace and the store's
    # identity marker names a different one, the store is not ours — fail open
    # rather than enforce against another harness's index (and never fall back
    # to a legacy store).
    want_ns = os.environ.get("LOCI_STORE_NAMESPACE")
    if want_ns is not None:
        have_ns = store_namespace(base_dir)
        if have_ns is not None and have_ns != want_ns:
            allow()

    abs_path = os.path.realpath(os.path.expanduser(file_path))
    repos = indexed_repos(base_dir)

    # Longest-prefix wins: a file under a nested indexed repo must be attributed
    # to the nearest (most specific) repo root, not whichever repo happens to be
    # listed first. First-match here is what misdirected reads to an ancestor
    # repo indexed alongside its own subdirectories.
    matched_repo = None
    for repo in repos:
        if abs_path == repo or abs_path.startswith(repo.rstrip("/") + "/"):
            if matched_repo is None or len(repo) > len(matched_repo):
                matched_repo = repo

    if matched_repo is None:
        allow()

    # Targeted reads pass through. They generate the Read receipt that Edit
    # needs without slurping the whole file, and the agent is expected to
    # source the line range from `loci_outline` rather than guessing.
    if tool_input.get("offset") is not None and tool_input.get("limit") is not None:
        allow()

    rel = os.path.relpath(abs_path, matched_repo)
    deny(
        f"Read blocked: '{file_path}' is a {ext} source file inside the "
        f"loci-indexed repo '{matched_repo}' (file='{rel}'). Per CLAUDE.md, "
        f"use loci instead of a whole-file Read:\n"
        f"  1. loci_outline repo='{matched_repo}' file='{rel}' — list the symbols "
        f"(each with line + end_line)\n"
        f"  2. loci_get repo='{matched_repo}' <symbol_id> — fetch one symbol body, OR\n"
        f"     Read {file_path} offset=<line> limit=<end_line - line + 1> — targeted "
        f"read (use this form when you intend to Edit; it also makes the Read receipt Edit needs)\n"
        f"Whole-file Reads on indexed source defeat loci's token savings. If you "
        f"genuinely need the whole file (module-level code that is not a symbol), "
        f"use Bash `cat` as an explicit override."
    )


if __name__ == "__main__":
    main()
