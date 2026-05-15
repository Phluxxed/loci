import os
import stat
import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
HOOK = REPO_ROOT / ".claude" / "hooks" / "loci-session-start.sh"


def _fake_loci(bin_dir: Path, symbols: int = 42) -> Path:
    """Create a fake `loci` executable in bin_dir that returns the given
    symbol count for `loci index ...` and an empty list for `loci list`."""
    bin_dir.mkdir(parents=True, exist_ok=True)
    fake = bin_dir / "loci"
    fake.write_text(
        f"""#!/usr/bin/env bash
if [ "$1" = "index" ]; then
  printf '{{"symbols_indexed": {symbols}}}\\n'
  exit 0
fi
if [ "$1" = "list" ]; then
  printf '[]\\n'
  exit 0
fi
exit 1
"""
    )
    fake.chmod(fake.stat().st_mode | stat.S_IXUSR)
    return fake


def _env_with_path(tmp_path: Path, fake_bin: Path) -> dict:
    fake_home = tmp_path / "home"
    fake_home.mkdir(exist_ok=True)
    env = os.environ.copy()
    env["HOME"] = str(fake_home)
    env["PATH"] = f"{fake_bin}:{env['PATH']}"
    return env


def _run_hook(cwd: Path, env: dict) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["bash", str(HOOK)],
        cwd=cwd,
        capture_output=True,
        text=True,
        env=env,
    )


def _git_init(repo: Path) -> None:
    subprocess.run(
        ["git", "init", "-q", "-b", "main"], cwd=repo, check=True, capture_output=True
    )


def test_claude_hook_indexes_when_cwd_is_repo_root(tmp_path: Path):
    repo = tmp_path / "repo"
    repo.mkdir()
    _git_init(repo)
    fake_bin = tmp_path / "bin"
    _fake_loci(fake_bin, symbols=42)
    env = _env_with_path(tmp_path, fake_bin)

    result = _run_hook(repo, env)
    assert result.returncode == 0, result.stderr
    assert "loci: repo indexed at" in result.stdout
    assert str(repo) in result.stdout
    assert "(42 symbols)" in result.stdout


def test_claude_hook_bails_silently_when_not_in_git_repo(tmp_path: Path):
    not_repo = tmp_path / "not_a_repo"
    not_repo.mkdir()
    # Deliberately NO `git init` here.
    fake_bin = tmp_path / "bin"
    _fake_loci(fake_bin, symbols=99)
    env = _env_with_path(tmp_path, fake_bin)
    # Ensure git rev-parse can't walk up into a parent repo by isolating
    # the no-repo dir under a fresh tmp tree that has no .git ancestor.
    env["GIT_CEILING_DIRECTORIES"] = str(tmp_path)

    result = _run_hook(not_repo, env)
    assert result.returncode == 0, result.stderr
    assert result.stdout == "", f"expected silent exit, got: {result.stdout!r}"


def test_claude_hook_indexes_repo_root_when_run_from_subdir(tmp_path: Path):
    repo = tmp_path / "repo"
    repo.mkdir()
    _git_init(repo)
    subdir = repo / "src" / "pkg"
    subdir.mkdir(parents=True)
    fake_bin = tmp_path / "bin"
    _fake_loci(fake_bin, symbols=7)
    env = _env_with_path(tmp_path, fake_bin)

    result = _run_hook(subdir, env)
    assert result.returncode == 0, result.stderr
    assert "(7 symbols)" in result.stdout
    # Index path in the message should be the repo root, not the subdir.
    assert f"loci: repo indexed at {repo} " in result.stdout
    assert str(subdir) not in result.stdout
