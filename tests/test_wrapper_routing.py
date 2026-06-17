"""Per-host base-dir routing in .shared/loci-wrapper.sh.

The wrapper picks LOCI_BASE_DIR so Claude Code and Codex keep separate index
stores: Claude Code -> ~/.claude/loci-index, everything else -> ~/.codex/loci-index.
The split is a security boundary (Codex's sandbox denies ~/.claude and must not
index repos it can't read), so these tests pin the routing down.

The real wrapper resolves its repo root from its own location and execs
`<repo>/.venv/bin/loci`. We reproduce that layout under tmp_path with a fake
`loci` that just echoes the resolved LOCI_BASE_DIR, so we can assert the path
without running the real entry point.
"""

import os
import stat
import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
WRAPPER = REPO_ROOT / ".shared" / "loci-wrapper.sh"


def _build_fake_repo(tmp_path: Path) -> Path:
    """Lay out <repo>/.shared/loci-wrapper.sh + <repo>/.venv/bin/loci."""
    repo = tmp_path / "repo"
    shared = repo / ".shared"
    venv_bin = repo / ".venv" / "bin"
    shared.mkdir(parents=True)
    venv_bin.mkdir(parents=True)

    wrapper_copy = shared / "loci-wrapper.sh"
    wrapper_copy.write_text(WRAPPER.read_text())
    wrapper_copy.chmod(wrapper_copy.stat().st_mode | stat.S_IXUSR)

    fake_loci = venv_bin / "loci"
    fake_loci.write_text('#!/usr/bin/env bash\nprintf "%s" "$LOCI_BASE_DIR"\n')
    fake_loci.chmod(fake_loci.stat().st_mode | stat.S_IXUSR)

    return wrapper_copy


def _run_wrapper(wrapper: Path, home: Path, extra_env: dict) -> str:
    env = os.environ.copy()
    env["HOME"] = str(home)
    env.pop("CLAUDECODE", None)
    env.pop("LOCI_BASE_DIR", None)
    env.update(extra_env)
    result = subprocess.run(
        ["bash", str(wrapper)],
        capture_output=True,
        text=True,
        env=env,
        check=True,
    )
    return result.stdout


def test_claude_code_routes_to_claude_store(tmp_path: Path):
    wrapper = _build_fake_repo(tmp_path)
    home = tmp_path / "home"
    home.mkdir()

    out = _run_wrapper(wrapper, home, {"CLAUDECODE": "1"})

    assert out == str(home / ".claude" / "loci-index")


def test_non_claude_routes_to_codex_store(tmp_path: Path):
    wrapper = _build_fake_repo(tmp_path)
    home = tmp_path / "home"
    home.mkdir()

    # CLAUDECODE unset (Codex, or a bare terminal) -> Codex store.
    out = _run_wrapper(wrapper, home, {})

    assert out == str(home / ".codex" / "loci-index")
    # The Codex store must never live under the sandbox-denied ~/.claude.
    assert str(home / ".claude") not in out


def test_explicit_base_dir_always_wins(tmp_path: Path):
    wrapper = _build_fake_repo(tmp_path)
    home = tmp_path / "home"
    home.mkdir()
    custom = tmp_path / "custom-store"

    # Even with CLAUDECODE=1, an explicit caller value takes precedence.
    out = _run_wrapper(
        wrapper, home, {"CLAUDECODE": "1", "LOCI_BASE_DIR": str(custom)}
    )

    assert out == str(custom)
