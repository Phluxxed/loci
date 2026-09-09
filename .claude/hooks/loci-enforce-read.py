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
    # `#!/usr/bin/env python3` is usually a system interpreter without the loci
    # package, which silently turned this guard into a no-op. Re-exec once under
    # the repo's own virtualenv (this file is symlinked from <loci>/.claude/hooks).
    if os.environ.get("LOCI_HOOK_REEXEC") != "1":
        _venv_python = Path(__file__).resolve().parents[2] / ".venv" / "bin" / "python3"
        if _venv_python.is_file():
            os.environ["LOCI_HOOK_REEXEC"] = "1"
            os.execv(str(_venv_python), [str(_venv_python), str(Path(__file__).resolve()), *sys.argv[1:]])
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


READ_COMMANDS = frozenset({"cat", "head", "tail", "sed", "awk", "less", "more"})
SEARCH_COMMANDS = frozenset({"grep", "egrep", "fgrep", "rg", "ag", "ack"})
SEGMENT_OPERATORS = frozenset({"|", "||", "&&", ";", "&", "\n"})


def git_repo_root(path: Path) -> Path | None:
    """Nearest ancestor (or self) holding a .git entry, else None."""
    for candidate in (path, *path.parents):
        if (candidate / ".git").exists():
            return candidate
    return None


def repo_is_indexed(base_dir: Path, repo: Path) -> bool:
    if repository_cache_key is None:
        return False
    return (base_dir / repository_cache_key(repo) / "index.json").is_file()


def unindexed_repo_recipe(repo: Path) -> str:
    return (
        f"  loci_index path={json.dumps(str(repo))}\n"
        "      → index this repository once, then use loci_grep / loci_search for "
        "content, loci_outline → loci_get for symbols, loci_file for a whole file\n"
    )


def search_recipe(repo: Path) -> str:
    r = json.dumps(str(repo))
    return (
        f"  loci_grep repo={r} pattern=<regex>\n"
        "      → exact content matches with file:line, scoped to the indexed repo\n"
        f"  loci_search repo={r} query=<terms>\n"
        "      → symbol / semantic search when you don't know the literal\n"
        f"  loci_outline repo={r} file=<relative path> → loci_get\n"
        "      → read one symbol or section instead of a whole file\n"
    )


def command_segments(command: str) -> list[list[str]] | None:
    """Split a shell command into pipeline/list segments of tokens.

    Returns None when the command cannot be tokenised (heredocs, unbalanced
    quotes) — callers fail open on None.
    """
    try:
        lexer = shlex.shlex(command, posix=True, punctuation_chars=True)
        lexer.whitespace_split = True
        tokens = list(lexer)
    except ValueError:
        return None
    segments: list[list[str]] = [[]]
    for tok in tokens:
        if tok in SEGMENT_OPERATORS or tok in ("<", ">", ">>", "<<"):
            if segments[-1]:
                segments.append([])
            continue
        segments[-1].append(tok)
    return [s for s in segments if s]


def strip_assignments(tokens: list[str]) -> list[str]:
    index = 0
    while index < len(tokens) and "=" in tokens[index] and not tokens[index].startswith("-"):
        name = tokens[index].partition("=")[0]
        if not name.replace("_", "a").isalnum() or name[:1].isdigit():
            break
        index += 1
    return tokens[index:]


def repo_read_targets(command: str, cwd: str) -> tuple[str, Path, bool] | None:
    """Find the first read/search segment aimed at source inside a git repo.

    Returns (command_name, repo_root, is_search) or None. Tracks `cd` across
    segments so `cd repo && grep …` resolves against the right directory.
    """
    if is_indexable_source_path is None:
        return None
    segments = command_segments(command)
    if not segments:
        return None
    current = Path(cwd)
    for seg in segments:
        seg = strip_assignments(seg)
        if not seg:
            continue
        name = os.path.basename(seg[0])
        if name == "cd" and len(seg) >= 2:
            dest = Path(seg[1]).expanduser()
            current = (dest if dest.is_absolute() else current / dest)
            continue
        if name not in READ_COMMANDS and name not in SEARCH_COMMANDS:
            continue
        is_search = name in SEARCH_COMMANDS
        args = [a for a in seg[1:] if not a.startswith("-") and a != "--"]
        if is_search and args:
            args = args[1:]  # first positional is the pattern
        for arg in args:
            candidate = Path(arg).expanduser()
            if not candidate.is_absolute():
                candidate = current / candidate
            try:
                candidate = candidate.resolve()
            except OSError:
                continue
            if not candidate.exists():
                continue
            repo = git_repo_root(candidate)
            if repo is None:
                continue
            if candidate.is_file():
                relative = candidate.relative_to(repo)
                if not is_indexable_source_path(PurePosixPath(relative.as_posix())):
                    continue
            return name, repo, is_search
    return None


def handle_read(payload: dict, base_dir: Path) -> None:
    tool_input = payload.get("tool_input") or {}
    file_path = tool_input.get("file_path", "")
    if not file_path:
        allow()

    # Targeted reads pass through — they are the sanctioned Edit path.
    if tool_input.get("offset") is not None or tool_input.get("limit") is not None:
        allow()

    target = indexed_source_target(base_dir, file_path)
    if target is None:
        source = Path(file_path).expanduser()
        if source.is_file() and is_indexable_source_path is not None:
            repo = git_repo_root(source.resolve())
            if repo is not None and not repo_is_indexed(base_dir, repo):
                relative = source.resolve().relative_to(repo)
                if is_indexable_source_path(PurePosixPath(relative.as_posix())):
                    deny(
                        f"Read blocked: '{relative.as_posix()}' is source in a git "
                        f"repository that Loci has not indexed yet ('{repo}'). "
                        "Index it first, then navigate through Loci:\n"
                        + unindexed_repo_recipe(repo)
                        + f"  Read {file_path} offset=<line> limit=<n>\n"
                        "      → targeted read, only when you intend to Edit\n"
                    )
        allow()
    if not loci_can_answer(base_dir, target):
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
        # Not a plain `cat FILE`: look for grep/sed/head/tail/awk… aimed at
        # repository source, including inside pipelines and after `cd`.
        found = repo_read_targets(command, cwd)
        if found is None:
            allow()
        name, repo, is_search = found
        if not repo_is_indexed(base_dir, repo):
            deny(
                f"Bash `{name}` blocked: it targets source in a git repository "
                f"Loci has not indexed yet ('{repo}'). Index it, then search "
                "through Loci:\n" + unindexed_repo_recipe(repo)
            )
        deny(
            f"Bash `{name}` blocked: it targets source inside a Loci-indexed "
            f"repository ('{repo}'). Use Loci instead of shell "
            f"{'search' if is_search else 'reads'}:\n" + search_recipe(repo)
            + "find/ls/Glob by name still pass through — filesystem discovery "
            "is not what Loci replaces."
        )

    target = indexed_source_target(base_dir, source)
    if target is None:
        repo = git_repo_root(source)
        if (
            repo is not None
            and not repo_is_indexed(base_dir, repo)
            and is_indexable_source_path is not None
            and is_indexable_source_path(PurePosixPath(source.relative_to(repo).as_posix()))
        ):
            deny(
                f"Bash `cat` blocked: '{source}' is in a git repository Loci has "
                f"not indexed yet ('{repo}'). Index it first:\n"
                + unindexed_repo_recipe(repo)
            )
        allow()
    if not loci_can_answer(base_dir, target):
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
