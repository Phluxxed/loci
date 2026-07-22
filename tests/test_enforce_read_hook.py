from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


HOOK = Path(__file__).parents[1] / ".claude" / "hooks" / "loci-enforce-read.py"


def _write_store(store: Path, namespace: str, repos: list[Path]) -> None:
    store.mkdir(parents=True)
    (store / ".loci-store.json").write_text(
        json.dumps({
            "schema_version": 1,
            "namespace": namespace,
            "store_id": "ae5cab56-c999-4bb1-b0cf-b258f7c3e5dc",
        })
    )
    for position, repo in enumerate(repos):
        entry = store / f"repo-{position}"
        entry.mkdir()
        (entry / "index.json").write_text(
            json.dumps({"repo_path": str(repo.resolve())})
        )


def _write_legacy_store(store: Path, repo: Path) -> None:
    store.mkdir(parents=True)
    entry = store / "repo"
    entry.mkdir()
    (entry / "index.json").write_text(
        json.dumps({"repo_path": str(repo.resolve())})
    )


def _run_hook(
    home: Path,
    file_path: Path,
    *,
    base_dir: Path | None = None,
    namespace: str | None = None,
    offset: int | None = None,
    limit: int | None = None,
) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["HOME"] = str(home)
    env.pop("LOCI_BASE_DIR", None)
    env.pop("LOCI_STORE_NAMESPACE", None)
    if base_dir is not None:
        env["LOCI_BASE_DIR"] = str(base_dir)
    if namespace is not None:
        env["LOCI_STORE_NAMESPACE"] = namespace
    tool_input: dict[str, object] = {"file_path": str(file_path)}
    if offset is not None:
        tool_input["offset"] = offset
    if limit is not None:
        tool_input["limit"] = limit
    return subprocess.run(
        [sys.executable, str(HOOK)],
        input=json.dumps({"tool_name": "Read", "tool_input": tool_input}),
        capture_output=True,
        text=True,
        env=env,
        timeout=5,
        check=False,
    )


def _denial(result: subprocess.CompletedProcess[str]) -> str:
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    return payload["hookSpecificOutput"]["permissionDecisionReason"]


def test_default_claude_store_enforces_whole_source_reads(tmp_path: Path) -> None:
    home = tmp_path / "home"
    repo = tmp_path / "repo"
    source = repo / "sample.py"
    source.parent.mkdir()
    source.write_text("value = 1\n")
    _write_store(home / ".claude" / "loci-index", "claude", [repo])

    result = _run_hook(home, source)

    reason = _denial(result)
    assert str(repo.resolve()) in reason
    assert "loci_outline" in reason


def test_explicit_store_and_namespace_override_claude_default(tmp_path: Path) -> None:
    home = tmp_path / "home"
    repo = tmp_path / "repo"
    source = repo / "sample.py"
    source.parent.mkdir()
    source.write_text("value = 1\n")
    custom_store = tmp_path / "custom-store"
    _write_store(custom_store, "shared", [repo])

    result = _run_hook(
        home,
        source,
        base_dir=custom_store,
        namespace="shared",
    )

    assert str(repo.resolve()) in _denial(result)


def test_namespace_mismatch_fails_open_instead_of_using_legacy_store(
    tmp_path: Path,
) -> None:
    home = tmp_path / "home"
    repo = tmp_path / "repo"
    source = repo / "sample.py"
    source.parent.mkdir()
    source.write_text("value = 1\n")
    _write_legacy_store(home / ".codeindex", repo)
    custom_store = tmp_path / "custom-store"
    _write_store(custom_store, "codex", [repo])

    result = _run_hook(
        home,
        source,
        base_dir=custom_store,
        namespace="claude",
    )

    assert result.returncode == 0
    assert result.stdout == ""


def test_nested_indexed_repo_uses_longest_matching_root(tmp_path: Path) -> None:
    home = tmp_path / "home"
    parent = tmp_path / "repo"
    nested = parent / "packages" / "nested"
    source = nested / "sample.py"
    source.parent.mkdir(parents=True)
    source.write_text("value = 1\n")
    _write_store(
        home / ".claude" / "loci-index",
        "claude",
        [parent, nested],
    )

    result = _run_hook(home, source)

    reason = _denial(result)
    assert f"'{nested.resolve()}'" in reason
    assert "file='sample.py'" in reason


def test_targeted_read_passes_through_valid_claude_store(tmp_path: Path) -> None:
    home = tmp_path / "home"
    repo = tmp_path / "repo"
    source = repo / "sample.py"
    source.parent.mkdir()
    source.write_text("value = 1\n")
    _write_store(home / ".claude" / "loci-index", "claude", [repo])

    result = _run_hook(home, source, offset=1, limit=1)

    assert result.returncode == 0
    assert result.stdout == ""
