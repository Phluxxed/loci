"""
End-to-end test: index a real Python file, search it, retrieve a symbol by ID.
Verifies the full byte-offset pipeline works correctly.
"""
import json
import os
import subprocess
import sys
from pathlib import Path


def run_loci(*args: str, env: dict) -> subprocess.CompletedProcess:
    full_env = os.environ.copy()
    full_env.update(env)
    return subprocess.run(
        [sys.executable, "-m", "loci.cli"] + list(args),
        capture_output=True,
        text=True,
        env=full_env,
    )


def test_full_pipeline(tmp_path: Path, fixtures_dir: Path):
    repo = tmp_path / "repo"
    repo.mkdir()
    import shutil
    shutil.copy(fixtures_dir / "sample.py", repo / "sample.py")

    env = {"LOCI_BASE_DIR": str(tmp_path / ".codeindex")}

    # 1. Index
    r = run_loci("index", str(repo), env=env)
    assert r.returncode == 0, r.stderr
    index_data = json.loads(r.stdout)
    assert index_data["symbols_indexed"] >= 4  # add, Calculator, multiply, divide

    # 2. Search
    r = run_loci("search", "multiply", "--repo", str(repo), env=env)
    assert r.returncode == 0
    results = json.loads(r.stdout)
    assert any(s["name"] == "multiply" for s in results)
    multiply = next(s for s in results if s["name"] == "multiply")

    # 3. Get — verify byte-offset retrieval matches actual source
    r = run_loci("get", multiply["id"], "--repo", str(repo), env=env)
    assert r.returncode == 0, r.stderr
    sym = json.loads(r.stdout)
    assert "multiply" in sym["source"]
    assert "def multiply" in sym["source"]

    # 4. Verify byte offsets against the original file directly
    source_bytes = (repo / "sample.py").read_bytes()
    extracted = source_bytes[sym["byte_offset"]:sym["byte_offset"] + sym["byte_length"]].decode()
    assert "def multiply" in extracted

    # 5. Incremental re-index skips unchanged files
    r = run_loci("index", str(repo), "--incremental", env=env)
    inc_data = json.loads(r.stdout)
    assert inc_data["files_skipped"] >= 1

    # 6. Invalidate
    r = run_loci("invalidate", str(repo), env=env)
    assert r.returncode == 0

    # 7. After invalidation, get should fail (repo no longer indexed)
    r = run_loci("get", multiply["id"], "--repo", str(repo), env=env)
    assert r.returncode != 0
