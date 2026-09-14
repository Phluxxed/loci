#!/usr/bin/env python3
"""Verify an isolated frozen Anvil source materialization against its manifest."""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def actual_files(root: Path) -> tuple[dict[str, str], list[str]]:
    files: dict[str, str] = {}
    unsupported: list[str] = []
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root).as_posix()
        if path.is_symlink() or not path.is_file():
            if not path.is_dir():
                unsupported.append(relative)
            continue
        files[relative] = sha256(path)
    return files, unsupported


def git_output(repository: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repository), *args],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    ).stdout.strip()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--receipt", required=True, type=Path)
    parser.add_argument("--origin-repository", required=True)
    parser.add_argument("--origin-method", required=True)
    args = parser.parse_args()

    manifest_path = args.manifest.resolve()
    root = args.root.resolve()
    receipt_path = args.receipt.resolve()
    origin_repository = Path(args.origin_repository).resolve()
    manifest: dict[str, Any] = json.loads(manifest_path.read_text(encoding="utf-8"))
    expected = manifest["source_files"]
    origin_commit = git_output(origin_repository, "rev-parse", f"{manifest['source_commit']}^{{commit}}")
    if origin_commit != manifest["source_commit"]:
        raise SystemExit(f"origin commit mismatch: {origin_commit}")
    origin_tree_file_count = len(git_output(
        origin_repository, "ls-tree", "-r", "--name-only", origin_commit
    ).splitlines())
    actual, unsupported = actual_files(root)
    missing = sorted(set(expected) - set(actual))
    extra = sorted(set(actual) - set(expected))
    mismatched = [
        {"file": path, "expected_sha256": expected[path], "actual_sha256": actual[path]}
        for path in sorted(set(expected) & set(actual))
        if expected[path] != actual[path]
    ]
    passed = not missing and not extra and not mismatched and not unsupported
    receipt = {
        "schema_version": 1,
        "kind": "frozen_anvil_source_restoration",
        "root": str(root),
        "canonical_root": str(root),
        "manifest": str(manifest_path),
        "manifest_sha256": sha256(manifest_path),
        "expected_commit": manifest["source_commit"],
        "expected_file_count": len(expected),
        "actual_file_count": len(actual),
        "origin": {
            "repository": str(origin_repository),
            "method": args.origin_method,
            "commit": origin_commit,
            "tree_file_count": origin_tree_file_count,
        },
        "historical_archive": {
            "expected_sha256": manifest["source_archive_sha256"],
            "bytes_available": False,
            "verification": "historical archive bytes unavailable; this receipt verifies the frozen file manifest only",
        },
        "missing": missing,
        "extra": extra,
        "mismatched": mismatched,
        "unsupported_entries": unsupported,
        "passed": passed,
    }
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    receipt_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if not passed:
        raise SystemExit("frozen source verification failed")
    print(json.dumps({
        "passed": passed,
        "files_verified": len(actual),
        "receipt": str(receipt_path),
    }, sort_keys=True))


if __name__ == "__main__":
    main()
