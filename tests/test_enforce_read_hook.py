from __future__ import annotations

import json
import os
import runpy
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from loci.indexability import is_indexable_source_path
from loci.storage.repository_catalog import CATALOG_FILE_NAME
from loci.storage.store_layout import repository_cache_key


HOOK = Path(__file__).parents[1] / ".claude" / "hooks" / "loci-enforce-read.py"


def _cache_key(repo: Path) -> str:
    return repository_cache_key(repo)


def _write_store(store: Path, namespace: str, repos: list[Path]) -> None:
    store.mkdir(parents=True)
    (store / ".loci-store.json").write_text(
        json.dumps({
            "schema_version": 1,
            "namespace": namespace,
            "store_id": "ae5cab56-c999-4bb1-b0cf-b258f7c3e5dc",
        })
    )
    catalog_entries: list[dict[str, object]] = []
    for repo in repos:
        entry = store / _cache_key(repo)
        entry.mkdir()
        sources = entry / "sources"
        sources.mkdir()
        file_hashes: dict[str, str] = {}
        for candidate in repo.rglob("*"):
            if not candidate.is_file():
                continue
            relative = candidate.relative_to(repo)
            if not is_indexable_source_path(relative):
                continue
            destination = sources / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(candidate, destination)
            file_hashes[relative.as_posix()] = "fixture"
        (entry / "index.json").write_text(
            json.dumps(
                {
                    "repo_path": str(repo.resolve()),
                    "symbols": [],
                    "file_hashes": file_hashes,
                }
            )
        )
        catalog_entries.append({
            "cache_key": _cache_key(repo),
            "symbols": 0,
            "path": str(repo.resolve()),
        })
    (store / CATALOG_FILE_NAME).write_text(
        json.dumps({"schema_version": 1, "repositories": catalog_entries})
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
    path_override: str | None = None,
) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["HOME"] = str(home)
    env.pop("LOCI_BASE_DIR", None)
    env.pop("LOCI_STORE_NAMESPACE", None)
    if base_dir is not None:
        env["LOCI_BASE_DIR"] = str(base_dir)
    if namespace is not None:
        env["LOCI_STORE_NAMESPACE"] = namespace
    if path_override is not None:
        env["PATH"] = path_override
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
    assert "loci_file" in reason


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
    assert 'file="sample.py"' in reason


@pytest.mark.parametrize(
    ("offset", "limit"),
    [
        (1, 1),
        (1, None),
        (None, 1),
    ],
)
def test_targeted_read_passes_through_valid_claude_store(
    tmp_path: Path,
    offset: int | None,
    limit: int | None,
) -> None:
    home = tmp_path / "home"
    repo = tmp_path / "repo"
    source = repo / "sample.py"
    source.parent.mkdir()
    source.write_text("value = 1\n")
    _write_store(home / ".claude" / "loci-index", "claude", [repo])

    result = _run_hook(home, source, offset=offset, limit=limit)

    assert result.returncode == 0
    assert result.stdout == ""


def test_ignored_source_read_passes_when_fresh_loci_cannot_answer(
    tmp_path: Path,
) -> None:
    home = tmp_path / "home"
    repo = tmp_path / "repo"
    source = repo / "ignored.py"
    source.parent.mkdir()
    source.write_text("value = 1\n")
    (repo / ".gitignore").write_text("ignored.py\n")
    _write_store(home / ".claude" / "loci-index", "claude", [repo])

    result = _run_hook(home, source)

    assert result.returncode == 0
    assert result.stdout == ""


def test_whole_read_of_indexed_test_source_is_blocked(tmp_path: Path) -> None:
    home = tmp_path / "home"
    repo = tmp_path / "repo"
    source = repo / "tests" / "test_sample.py"
    source.parent.mkdir(parents=True)
    source.write_text("def test_sample():\n    assert True\n")
    _write_store(home / ".claude" / "loci-index", "claude", [repo])

    result = _run_hook(home, source)

    reason = _denial(result)
    assert 'file_path="tests/test_sample.py"' in reason


def test_read_fails_open_when_exact_loci_probe_cannot_answer(tmp_path: Path) -> None:
    home = tmp_path / "home"
    repo = tmp_path / "repo"
    source = repo / "sample.py"
    source.parent.mkdir()
    source.write_text("value = 1\n")
    _write_store(home / ".claude" / "loci-index", "claude", [repo])
    bin_dir = tmp_path / "bin"
    _stub_loci(bin_dir, "echo '[]'\n")

    result = _run_hook(
        home,
        source,
        path_override=f"{bin_dir}:/usr/bin:/bin",
    )

    assert result.returncode == 0
    assert result.stdout == ""


def test_indexed_source_resolution_does_not_enumerate_store(
    tmp_path: Path,
    monkeypatch,
) -> None:
    store = tmp_path / "store"
    repo = tmp_path / "repo"
    source = repo / "sample.py"
    source.parent.mkdir()
    source.write_text("value = 1\n")
    _write_store(store, "claude", [repo])
    namespace = runpy.run_path(str(HOOK))

    def fail_iterdir(_path: Path):
        raise AssertionError("hook enumerated aggregate store entries")

    monkeypatch.setattr(Path, "iterdir", fail_iterdir)

    target = namespace["indexed_source_target"](store, source)

    assert target is not None
    assert target.repo == repo.resolve()
    assert target.relative_path == "sample.py"


# --- Bash arm ------------------------------------------------------------
#
# Gating Read alone locks the expensive door and leaves the cheap one open:
# grep/cat reach the same bytes and produced no deny at all, so drift off loci
# was both free and silent. These cover the shell path and, more importantly,
# the fallback contract: only an unreachable loci reopens it.


def _stub_loci(bin_dir: Path, body: str) -> None:
    bin_dir.mkdir(parents=True, exist_ok=True)
    stub = bin_dir / "loci"
    stub.write_text("#!/bin/sh\n" + body)
    stub.chmod(0o755)


def _run_bash_hook(
    home: Path,
    command: str,
    cwd: Path,
    *,
    base_dir: Path | None = None,
    path_override: str | None = None,
) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["HOME"] = str(home)
    env.pop("LOCI_BASE_DIR", None)
    env.pop("LOCI_STORE_NAMESPACE", None)
    if base_dir is not None:
        env["LOCI_BASE_DIR"] = str(base_dir)
    if path_override is not None:
        env["PATH"] = path_override
    return subprocess.run(
        [sys.executable, str(HOOK)],
        input=json.dumps(
            {
                "tool_name": "Bash",
                "cwd": str(cwd),
                "tool_input": {"command": command},
            }
        ),
        capture_output=True,
        text=True,
        env=env,
        timeout=30,
        check=False,
    )


def _bash_fixture(tmp_path: Path) -> tuple[Path, Path]:
    """A home with a store indexing one repo that holds a source file."""
    home = tmp_path / "home"
    repo = tmp_path / "repo"
    (repo / "docs").mkdir(parents=True)
    (repo / "sample.py").write_text("value = 1\n")
    (repo / "docs" / "notes.md").write_text("# notes\n")
    _write_store(home / ".claude" / "loci-index", "claude", [repo])
    return home, repo


def test_bash_cat_of_indexed_source_is_blocked(tmp_path: Path) -> None:
    home, repo = _bash_fixture(tmp_path)

    result = _run_bash_hook(home, "cat sample.py", repo)

    reason = _denial(result)
    assert "sample.py" in reason
    assert "loci_outline" in reason


def test_bash_grep_over_source_directory_passes_without_equivalent_scope(
    tmp_path: Path,
) -> None:
    home, repo = _bash_fixture(tmp_path)

    result = _run_bash_hook(home, "grep -rn value .", repo)

    assert result.stdout == "", result.stdout


def test_bash_grep_over_indexed_tests_directory_passes_without_scope_filter(
    tmp_path: Path,
) -> None:
    home = tmp_path / "home"
    repo = tmp_path / "repo"
    tests_dir = repo / "tests"
    tests_dir.mkdir(parents=True)
    (tests_dir / "test_hook.py").write_text("def test_hook():\n    pass\n")
    _write_store(home / ".claude" / "loci-index", "claude", [repo])

    result = _run_bash_hook(home, "grep -rn test_hook tests", repo)

    assert result.stdout == "", result.stdout


def test_bash_grep_over_docs_only_directory_passes(tmp_path: Path) -> None:
    home, repo = _bash_fixture(tmp_path)

    result = _run_bash_hook(home, "grep -rn notes docs", repo)

    assert result.stdout == "", result.stdout


def test_bash_non_read_command_passes(tmp_path: Path) -> None:
    home, repo = _bash_fixture(tmp_path)

    result = _run_bash_hook(home, "git status --porcelain", repo)

    assert result.stdout == "", result.stdout


def test_bash_pipeline_passes_when_mcp_call_cannot_preserve_processing(
    tmp_path: Path,
) -> None:
    home, repo = _bash_fixture(tmp_path)

    result = _run_bash_hook(home, "cat sample.py | wc -l", repo)

    assert result.stdout == "", result.stdout


def test_bash_fallback_opens_only_when_loci_is_unreachable(tmp_path: Path) -> None:
    home, repo = _bash_fixture(tmp_path)
    bin_dir = tmp_path / "bin"

    # Binary missing entirely -> loci cannot answer -> allow the fallback.
    bin_dir.mkdir()
    result = _run_bash_hook(
        home, "cat sample.py", repo, path_override=f"{bin_dir}:/usr/bin:/bin"
    )
    assert result.stdout == "", "absent loci must reopen the fallback"

    # Probe returns an empty repo list -> loci has absolutely nothing -> allow.
    _stub_loci(bin_dir, "echo '[]'")
    result = _run_bash_hook(
        home, "cat sample.py", repo, path_override=f"{bin_dir}:/usr/bin:/bin"
    )
    assert result.stdout == "", "empty loci store must reopen the fallback"

    # Probe fails outright -> allow.
    _stub_loci(bin_dir, "echo broken >&2; exit 3")
    result = _run_bash_hook(
        home, "cat sample.py", repo, path_override=f"{bin_dir}:/usr/bin:/bin"
    )
    assert result.stdout == "", "failing loci must reopen the fallback"


def test_bash_fails_open_when_exact_loci_probe_cannot_answer(tmp_path: Path) -> None:
    home, repo = _bash_fixture(tmp_path)
    bin_dir = tmp_path / "bin"
    _stub_loci(bin_dir, """echo '[{"path":"/somewhere/else","symbols":7}]'""")

    result = _run_bash_hook(
        home, "cat sample.py", repo, path_override=f"{bin_dir}:/usr/bin:/bin"
    )

    assert result.stdout == ""
