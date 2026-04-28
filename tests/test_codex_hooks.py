import json
import os
import stat
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent


def _make_executable(path: Path, content: str) -> None:
    path.write_text(content)
    path.chmod(path.stat().st_mode | stat.S_IXUSR)


def test_codex_session_start_hook_emits_context_json(tmp_path: Path):
    repo = tmp_path / "repo"
    repo.mkdir()
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    fake_loci = fake_bin / "loci"
    _make_executable(
        fake_loci,
        """#!/usr/bin/env bash
if [ "$1" = "index" ]; then
  printf '{"symbols_indexed": 42}\n'
  exit 0
fi
if [ "$1" = "list" ]; then
  printf '[]\n'
  exit 0
fi
exit 1
""",
    )

    fake_home = tmp_path / "home"
    fake_home.mkdir()

    env = os.environ.copy()
    env["HOME"] = str(fake_home)
    env["PATH"] = f"{fake_bin}:{env['PATH']}"
    result = subprocess.run(
        ["bash", str(REPO_ROOT / ".codex" / "hooks" / "loci-session-start.sh")],
        cwd=repo,
        capture_output=True,
        text=True,
        env=env,
        check=True,
    )

    payload = json.loads(result.stdout)
    message = payload["hookSpecificOutput"]["additionalContext"]
    assert payload["additional_context"] == message
    assert "loci: repo indexed at" in message
    assert str(repo) in message
    assert "(42 symbols)" in message


def test_codex_install_hooks_patches_hooks_json_idempotently(tmp_path: Path):
    codex_home = tmp_path / ".codex"
    hooks_dir = codex_home / "hooks"
    hooks_dir.mkdir(parents=True)
    hooks_json = codex_home / "hooks.json"
    hooks_json.write_text(json.dumps({
        "hooks": {
            "SessionStart": [
                {
                    "matcher": "startup|resume",
                    "hooks": [
                        {
                            "type": "command",
                            "command": "/existing/session-start.sh",
                            "timeout": 15,
                        }
                    ],
                }
            ]
        }
    }, indent=2))

    env = os.environ.copy()
    env["CODEX_HOME"] = str(codex_home)

    install_script = REPO_ROOT / ".codex" / "install-hooks.py"

    first = subprocess.run(
        [sys.executable, str(install_script)],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        env=env,
        check=True,
    )
    second = subprocess.run(
        [sys.executable, str(install_script)],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        env=env,
        check=True,
    )

    assert "updated" in first.stdout
    assert "already up to date" in second.stdout

    config = json.loads(hooks_json.read_text())
    session_start = config["hooks"]["SessionStart"]
    assert len(session_start) == 1
    entry = session_start[0]
    assert entry["matcher"] == "startup|resume"
    commands = [hook["command"] for hook in entry["hooks"]]
    assert "/existing/session-start.sh" in commands
    assert any(command.endswith("/hooks/loci-session-start.sh") for command in commands)

    linked_hook = hooks_dir / "loci-session-start.sh"
    assert linked_hook.is_symlink()
    assert linked_hook.resolve() == (REPO_ROOT / ".codex" / "hooks" / "loci-session-start.sh").resolve()


def test_codex_session_start_hook_uses_root_direnv_python(tmp_path: Path):
    repo = tmp_path / "repo"
    repo.mkdir()

    fake_home = tmp_path / "home"
    fake_home.mkdir()
    fake_direnv = fake_home / ".direnv" / "python-3.13.7" / "bin"
    fake_direnv.mkdir(parents=True)
    fake_python = fake_direnv / "activate"
    fake_loci = fake_direnv / "loci"

    fake_python.write_text(
        """export PATH="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd):$PATH"\n"""
    )
    fake_loci.write_text(
        """#!/usr/bin/env bash
if [ "$1" = "index" ]; then
  printf '{"symbols_indexed": 7}\n'
  exit 0
fi
if [ "$1" = "list" ]; then
  printf '[]\n'
  exit 0
fi
exit 1
"""
    )
    fake_loci.chmod(fake_loci.stat().st_mode | stat.S_IXUSR)

    env = os.environ.copy()
    env["HOME"] = str(fake_home)
    env["PATH"] = "/usr/bin:/bin"

    result = subprocess.run(
        ["bash", str(REPO_ROOT / ".codex" / "hooks" / "loci-session-start.sh")],
        cwd=repo,
        capture_output=True,
        text=True,
        env=env,
        check=True,
    )

    payload = json.loads(result.stdout)
    message = payload["hookSpecificOutput"]["additionalContext"]
    assert "(7 symbols)" in message
