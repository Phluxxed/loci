#!/usr/bin/env python3
"""PreToolUse hook for Read: blocks whole-file reads of source files in
loci-indexed repos.

Forces compliance with the CLAUDE.md rule: use `loci outline` then either
`loci get` (for understanding) or a targeted `Read offset=line limit=N`
(for editing) instead of slurping a whole .py/.ts/.tsx/.js/.go/.rs file.

The targeted-read passthrough is what makes `Edit` work on indexed files —
Edit demands a prior Read receipt on the path, and a Read with explicit
offset+limit satisfies that without losing loci's token-efficiency win for
exploration.

Outputs JSON per Claude Code PreToolUse hook spec:
  - permissionDecision "deny" with a reason that points the agent at loci
  - otherwise exits silently (allow)
"""
import json
import os
import sys
from pathlib import Path

LOCI_EXTS = {".py", ".ts", ".tsx", ".js", ".go", ".rs"}
CODEINDEX_DIR = Path.home() / ".codeindex"


def allow():
    sys.exit(0)


def deny(reason: str):
    out = {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason,
        }
    }
    print(json.dumps(out))
    sys.exit(0)


def indexed_repos() -> list[str]:
    repos = []
    if not CODEINDEX_DIR.is_dir():
        return repos
    for entry in CODEINDEX_DIR.iterdir():
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

    abs_path = os.path.realpath(os.path.expanduser(file_path))
    repos = indexed_repos()

    matched_repo = None
    for repo in repos:
        if abs_path == repo or abs_path.startswith(repo.rstrip("/") + "/"):
            matched_repo = repo
            break

    if matched_repo is None:
        allow()

    # Targeted reads pass through. They generate the Read receipt that Edit
    # needs without slurping the whole file, and the agent is expected to
    # source the line range from `loci outline` rather than guessing.
    if tool_input.get("offset") is not None and tool_input.get("limit") is not None:
        allow()

    rel = os.path.relpath(abs_path, matched_repo)
    deny(
        f"Read blocked: '{file_path}' is a {ext} file inside the loci-indexed repo "
        f"'{matched_repo}'. Per CLAUDE.md, use loci instead:\n"
        f"  1. `loci outline {matched_repo} --file {rel}` to see the symbols (incl. line + end_line)\n"
        f"  2. `loci get --repo {matched_repo} <symbol_id>` to fetch a specific symbol body, OR\n"
        f"     `Read {file_path} offset=<line> limit=<end_line - line + 1>` for a targeted read\n"
        f"     (use this form when you intend to Edit — it generates the Read receipt Edit needs).\n"
        f"This is enforced because whole-file Reads on indexed source defeat loci's token savings. "
        f"If you genuinely need the whole file (e.g. you need imports/module-level code that "
        f"aren't symbols), use Bash `cat` as an explicit override."
    )


if __name__ == "__main__":
    main()
