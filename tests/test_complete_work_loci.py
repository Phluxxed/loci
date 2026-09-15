from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from benchmarks.complete_work.oracles.loci import EPISODE_ID, TARGET_COMMIT, evaluate


PROJECT = Path(__file__).resolve().parents[1]


def export_target(destination: Path) -> Path:
    subprocess.run(
        ["git", "archive", TARGET_COMMIT], cwd=PROJECT, check=True,
        stdout=(archive := destination.with_suffix(".tar")).open("wb"),
    )
    shutil.unpack_archive(archive, destination)
    archive.unlink()
    return destination


def reference_patch(repo: Path) -> None:
    indexability = repo / "src/loci/indexability.py"
    indexability.write_text(
        indexability.read_text(encoding="utf-8").replace('    ".cache",\n', '    ".cache",\n    ".direnv",\n'),
        encoding="utf-8",
    )
    policy = repo / "tests/test_indexability.py"
    policy.write_text(policy.read_text(encoding="utf-8") + '''\n\ndef test_direnv_is_exact_nested_disposable_source() -> None:\n    path = PurePath("tools/.direnv/lib/site.py")\n    assert is_excluded_repository_path(path)\n    assert not is_indexable_source_path(path)\n    assert is_indexable_source_path(PurePath("tools/.direnv-tools/site.py"))\n    with pytest.raises(ValueError):\n        is_indexable_source_path(PurePath("../outside.py"))\n''', encoding="utf-8")
    service = repo / "tests/test_service.py"
    service.write_text(service.read_text(encoding="utf-8") + '''\n\ndef test_service_incremental_direnv_removes_moved_symbol(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):\n    monkeypatch.setenv("LOCI_BASE_DIR", str(tmp_path / ".codeindex"))\n    repo = tmp_path / "repo"\n    repo.mkdir()\n    moved = repo / "moved.py"\n    moved.write_text("def episode_moved_symbol():\\n    return 1\\n", encoding="utf-8")\n    (repo / "sibling.py").write_text("def episode_sibling_symbol():\\n    return 1\\n", encoding="utf-8")\n    index_repo(repo, incremental=False)\n    destination = repo / "tools/.direnv/lib/moved.py"\n    destination.parent.mkdir(parents=True)\n    moved.replace(destination)\n    index_repo(repo, incremental=True)\n    assert not any(item["name"] == "episode_moved_symbol" for item in search_symbols(repo, "episode_moved_symbol"))\n    assert any(item["name"] == "episode_sibling_symbol" for item in search_symbols(repo, "episode_sibling_symbol"))\n''', encoding="utf-8")


def receipt_by_id(receipt: dict) -> dict[str, dict]:
    return {check["id"]: check for check in receipt["checks"]}


def test_baseline_fails_and_reference_patch_passes(tmp_path: Path) -> None:
    baseline = export_target(tmp_path / "baseline")
    failed = evaluate(baseline, work_dir=tmp_path / "baseline-work", python_executable=sys.executable)
    assert failed["episode_id"] == EPISODE_ID
    assert failed["status"] == "failed"
    assert not receipt_by_id(failed)["nested_exclusion"]["passed"]

    patched = export_target(tmp_path / "patched")
    reference_patch(patched)
    passed = evaluate(patched, work_dir=tmp_path / "patched-work", python_executable=sys.executable)
    assert passed["status"] == "passed", json.dumps(passed, indent=2)
    assert receipt_by_id(passed)["target_source_import"]["passed"]


@pytest.mark.parametrize(
    ("name", "mutate", "check_id"),
    [
        (
            "broad-name",
            lambda repo: (repo / "src/loci/indexability.py").write_text(
                (repo / "src/loci/indexability.py").read_text(encoding="utf-8").replace('    ".direnv",\n', '    ".direnv",\n    ".direnv-tools",\n'), encoding="utf-8"),
            "negative_policy_controls",
        ),
        (
            "path-safety",
            lambda repo: (repo / "src/loci/indexability.py").write_text(
                (repo / "src/loci/indexability.py").read_text(encoding="utf-8").replace('if path.is_absolute() or ".." in path.parts:', 'if path.is_absolute():'), encoding="utf-8"),
            "path_safety",
        ),
        (
            "stale-state",
            lambda repo: (repo / "src/loci/service.py").write_text(
                (repo / "src/loci/service.py").read_text(encoding="utf-8").replace('new_file_hashes: dict[str, str] = {}', 'new_file_hashes: dict[str, str] = dict(existing_hashes)', 1), encoding="utf-8"),
            "incremental_terminal_state",
        ),
    ],
)
def test_oracle_rejects_targeted_regressions(tmp_path: Path, name: str, mutate, check_id: str) -> None:
    target = export_target(tmp_path / name)
    reference_patch(target)
    mutate(target)
    receipt = evaluate(target, work_dir=tmp_path / f"{name}-work", python_executable=sys.executable)
    assert receipt["status"] == "failed", json.dumps(receipt, indent=2)
    assert not receipt_by_id(receipt)[check_id]["passed"]


def test_cli_writes_a_receipt(tmp_path: Path) -> None:
    target = export_target(tmp_path / "target")
    reference_patch(target)
    output = tmp_path / "receipt.json"
    result = subprocess.run(
        [sys.executable, "-m", "benchmarks.complete_work.oracles.loci", "--repo", str(target),
         "--work-dir", str(tmp_path / "work"), "--output", str(output)],
        cwd=PROJECT, text=True, capture_output=True, check=False,
    )
    assert result.returncode == 0, result.stderr
    receipt = json.loads(output.read_text(encoding="utf-8"))
    assert receipt["schema_version"] == 1
    assert receipt["status"] == "passed"
