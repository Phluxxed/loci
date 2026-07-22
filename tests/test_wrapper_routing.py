"""Per-host base-dir routing in the tracked loci wrappers.

The CLI wrapper retains host-specific convenience routing. The MCP wrapper is
different: its client registration must supply an explicit base directory and
namespace, so the wrapper must not infer either value from ambient host state.

The real wrappers resolve their repo root from their own location and exec
`<repo>/.venv/bin/loci*`. We reproduce that layout under tmp_path with fake
entry points that echo the resolved LOCI_BASE_DIR, so we can assert the path
without running the real commands.
"""

import os
import stat
import subprocess
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parent.parent
WRAPPERS = (
    ("loci-wrapper.sh", "loci"),
    ("loci-mcp-wrapper.sh", "loci-mcp"),
)


def _build_fake_repo(tmp_path: Path, wrapper_name: str, entrypoint_name: str) -> Path:
    """Lay out <repo>/.shared/<wrapper> + <repo>/.venv/bin/<entrypoint>."""
    repo = tmp_path / "repo"
    shared = repo / ".shared"
    venv_bin = repo / ".venv" / "bin"
    shared.mkdir(parents=True)
    venv_bin.mkdir(parents=True)

    wrapper_copy = shared / wrapper_name
    wrapper_copy.write_text((REPO_ROOT / ".shared" / wrapper_name).read_text())
    wrapper_copy.chmod(wrapper_copy.stat().st_mode | stat.S_IXUSR)

    fake_entrypoint = venv_bin / entrypoint_name
    fake_entrypoint.write_text('#!/usr/bin/env bash\nprintf "%s" "$LOCI_BASE_DIR"\n')
    fake_entrypoint.chmod(fake_entrypoint.stat().st_mode | stat.S_IXUSR)

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


def test_claude_code_routes_to_claude_store(
    tmp_path: Path,
):
    wrapper = _build_fake_repo(tmp_path, "loci-wrapper.sh", "loci")
    home = tmp_path / "home"
    home.mkdir()

    out = _run_wrapper(wrapper, home, {"CLAUDECODE": "1"})

    assert out == str(home / ".claude" / "loci-index")


def test_non_claude_leaves_store_resolution_to_python(
    tmp_path: Path,
):
    wrapper = _build_fake_repo(tmp_path, "loci-wrapper.sh", "loci")
    home = tmp_path / "home"
    home.mkdir()

    # CLAUDECODE unset and no explicit store -> Python resolver decides.
    out = _run_wrapper(wrapper, home, {})

    assert out == ""


def test_mcp_wrapper_does_not_guess_store_from_claude_ambient_state(
    tmp_path: Path,
):
    wrapper = _build_fake_repo(tmp_path, "loci-mcp-wrapper.sh", "loci-mcp")
    home = tmp_path / "home"
    home.mkdir()

    out = _run_wrapper(wrapper, home, {"CLAUDECODE": "1"})

    assert out == ""


@pytest.mark.parametrize(("wrapper_name", "entrypoint_name"), WRAPPERS)
def test_explicit_base_dir_always_wins(
    tmp_path: Path, wrapper_name: str, entrypoint_name: str
):
    wrapper = _build_fake_repo(tmp_path, wrapper_name, entrypoint_name)
    home = tmp_path / "home"
    home.mkdir()
    custom = tmp_path / "custom-store"

    # Even with CLAUDECODE=1, an explicit caller value takes precedence.
    out = _run_wrapper(
        wrapper, home, {"CLAUDECODE": "1", "LOCI_BASE_DIR": str(custom)}
    )

    assert out == str(custom)
