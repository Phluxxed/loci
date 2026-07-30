#!/usr/bin/env python3
"""PreToolUse hook: redirect only answer-equivalent source reads to Loci.

The hook denies a whole-file Read, or a simple ``cat FILE``, only after the
authoritative Loci policy, exact store layout, mirrored source, and fresh
``loci file`` path all agree that Loci can answer for that same file. Native
directory searches, pipelines, transformed reads, uncovered paths, and
unreachable or stale Loci processes pass through.

That fail-open boundary is deliberate. A broader native operation must never
be redirected to a repository-wide Loci call with a different content scope.
The hook performs no aggregate store listing and never parses sibling
``index.json`` files; lookup cost depends on target path depth and the one
candidate repository.

Store resolution mirrors the Claude session-start hook: LOCI_BASE_DIR if set,
else ~/.claude/loci-index — Claude Code's own store, never codex's or the
legacy ~/.codeindex. If LOCI_STORE_NAMESPACE is set and the store's identity
marker names a different namespace, the hook fails open rather than enforce
against a store that is not this harness's.

Outputs JSON per the Claude Code PreToolUse hook spec: `deny` with a reason
that names the exact loci call to make instead, else exits silently (allow).
Any unexpected error fails open — a broken guardrail must not block all work.
"""
from __future__ import annotations

import json
import os
import shlex
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from pathlib import PurePosixPath
from typing import NoReturn

STORE_IDENTITY_FILE = ".loci-store.json"
PROBE_TIMEOUT_S = 8.0
SHELL_META = frozenset("|&;<>\n")

try:
    from loci.indexability import is_indexable_source_path
    from loci.storage.store_layout import repository_cache_key
except Exception:
    is_indexable_source_path = None
    repository_cache_key = None


@dataclass(frozen=True)
class IndexedSourceTarget:
    repo: Path
    relative_path: str


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


def indexed_source_target(
    base_dir: Path,
    path: str | Path,
) -> IndexedSourceTarget | None:
    """Resolve one exact file without enumerating or parsing the aggregate store."""
    if is_indexable_source_path is None or repository_cache_key is None:
        return None
    source = Path(path).expanduser().resolve()
    if not source.is_file():
        return None
    for repo in (source.parent, *source.parents[1:]):
        repo_dir = base_dir / repository_cache_key(repo)
        if not (repo_dir / "index.json").is_file():
            continue
        relative = source.relative_to(repo)
        if not is_indexable_source_path(PurePosixPath(relative.as_posix())):
            return None
        if not (repo_dir / "sources" / relative).is_file():
            return None
        return IndexedSourceTarget(repo=repo, relative_path=relative.as_posix())
    return None


def loci_can_answer(base_dir: Path, target: IndexedSourceTarget) -> bool:
    """Probe the same fresh file service used by the MCP tool."""
    binary = shutil.which("loci")
    if binary is None:
        return False
    env = dict(os.environ)
    env["LOCI_BASE_DIR"] = str(base_dir)
    try:
        proc = subprocess.run(
            [
                binary,
                "file",
                target.relative_path,
                "--repo",
                str(target.repo),
                "--start",
                "1",
                "--end",
                "1",
                "--ensure-fresh",
            ],
            capture_output=True,
            text=True,
            timeout=PROBE_TIMEOUT_S,
            env=env,
        )
    except (subprocess.TimeoutExpired, OSError, ValueError):
        return False
    if proc.returncode != 0:
        return False
    try:
        result = json.loads(proc.stdout)
    except (json.JSONDecodeError, TypeError):
        return False
    return isinstance(result, dict) and isinstance(result.get("content"), str)


def loci_recipe(target: IndexedSourceTarget) -> str:
    """Exact MCP calls whose required arguments match the live schemas."""
    repo = json.dumps(str(target.repo))
    relative = json.dumps(target.relative_path)
    return (
        f"  loci_file repo={repo} file_path={relative}\n"
        "      → exact indexed content for this file\n"
        f"  loci_outline repo={repo} file={relative}\n"
        "      → symbol boundaries for targeted navigation\n"
    )


def handle_read(payload: dict, base_dir: Path) -> None:
    tool_input = payload.get("tool_input") or {}
    file_path = tool_input.get("file_path", "")
    if not file_path:
        allow()

    # Targeted reads pass through — they are the sanctioned Edit path.
    if tool_input.get("offset") is not None or tool_input.get("limit") is not None:
        allow()

    target = indexed_source_target(base_dir, file_path)
    if target is None or not loci_can_answer(base_dir, target):
        allow()

    deny(
        f"Read blocked: Loci just proved it can answer the same whole-file scope "
        f"for '{target.relative_path}' in '{target.repo}'. Use:\n"
        + loci_recipe(target)
        + f"  Read {file_path} offset=<line> limit=<end_line - line + 1>\n"
        f"      → targeted read; use this when you intend to Edit (it makes the "
        f"receipt Edit needs)\n"
        "Directory searches and transformed shell reads are not blocked because "
        "the current MCP tools cannot preserve those native scopes exactly."
    )


def simple_cat_target(command: str, cwd: str) -> Path | None:
    """Return the sole file from a plain ``cat FILE`` command."""
    if any(operator in command for operator in SHELL_META):
        return None
    try:
        tokens = shlex.split(command)
    except ValueError:
        return None
    index = 0
    while index < len(tokens) and "=" in tokens[index]:
        name, _, _value = tokens[index].partition("=")
        if not name.replace("_", "a").isalnum() or name[:1].isdigit():
            break
        index += 1
    if index >= len(tokens) or os.path.basename(tokens[index]) != "cat":
        return None
    arguments = tokens[index + 1 :]
    if len(arguments) == 2 and arguments[0] == "--":
        arguments = arguments[1:]
    if len(arguments) != 1 or arguments[0].startswith("-"):
        return None
    candidate = Path(arguments[0]).expanduser()
    if not candidate.is_absolute():
        candidate = Path(cwd) / candidate
    return candidate.resolve() if candidate.is_file() else None


def handle_bash(payload: dict, base_dir: Path) -> None:
    tool_input = payload.get("tool_input") or {}
    command = tool_input.get("command", "")
    if not command:
        allow()

    cwd = payload.get("cwd") or os.getcwd()
    source = simple_cat_target(command, cwd)
    if source is None:
        allow()

    target = indexed_source_target(base_dir, source)
    if target is None or not loci_can_answer(base_dir, target):
        allow()

    deny(
        f"Bash read blocked: plain `cat` would read the same whole file Loci just "
        f"proved it can answer for '{target.relative_path}' in '{target.repo}'. "
        "Use:\n"
        + loci_recipe(target)
        + "Shell pipelines, range transforms, and directory searches pass through "
        "because replacing them would change the operation's content scope."
    )


def main() -> None:
    try:
        payload = json.load(sys.stdin)
    except Exception:
        allow()

    tool = payload.get("tool_name")
    if tool not in ("Read", "Bash"):
        allow()

    base_dir = store_base_dir()

    # Store isolation: if this harness declares a namespace and the store's
    # identity marker names a different one, the store is not ours — fail open
    # rather than enforce against another harness's index.
    want_ns = os.environ.get("LOCI_STORE_NAMESPACE")
    if want_ns is not None:
        have_ns = store_namespace(base_dir)
        if have_ns is not None and have_ns != want_ns:
            allow()

    if tool == "Read":
        handle_read(payload, base_dir)
    else:
        handle_bash(payload, base_dir)
    allow()


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception:
        # A guardrail that crashes must not become a guardrail that blocks
        # everything. Fail open, loudly enough to notice in hook debug output.
        print("loci-enforce-read: internal error, allowing", file=sys.stderr)
        sys.exit(0)
