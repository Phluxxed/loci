"""Independent terminal evaluator for the Loci ``.direnv`` episode.

This module deliberately imports no product code itself.  Every behavioral
probe is a child process with the evaluated checkout's ``src`` first on
``PYTHONPATH`` and a fresh store below the caller's work directory.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import textwrap
import time
from pathlib import Path
from typing import Any


SCHEMA_VERSION = 1
EPISODE_ID = "loci-direnv-exclusion"
TARGET_COMMIT = "f3d9134aece5156bec1dcc302d4330522d1d96e5"
ENVIRONMENT_ASSET = Path(__file__).with_name("loci_environment.json")


def _asset() -> dict[str, Any]:
    return json.loads(ENVIRONMENT_ASSET.read_text(encoding="utf-8"))


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _child_environment(repo: Path, store: Path) -> dict[str, str]:
    env = os.environ.copy()
    source = str(repo / "src")
    env["PYTHONPATH"] = source + (
        os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else ""
    )
    env["LOCI_BASE_DIR"] = str(store)
    return env


def _run_python(
    executable: str,
    repo: Path,
    store: Path,
    source: str,
    *arguments: str,
    timeout: int = 90,
) -> dict[str, Any]:
    command = [executable, "-c", textwrap.dedent(source), *arguments]
    try:
        completed = subprocess.run(
            command,
            cwd=repo,
            env=_child_environment(repo, store),
            text=True,
            capture_output=True,
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"ok": False, "unavailable": True, "error": str(exc)}
    payload: dict[str, Any] | None = None
    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError:
        pass
    return {
        "ok": completed.returncode == 0 and payload is not None,
        "returncode": completed.returncode,
        "payload": payload,
        "stdout": completed.stdout[-4000:],
        "stderr": completed.stderr[-4000:],
    }


def _check(check_id: str, passed: bool, details: dict[str, Any]) -> dict[str, Any]:
    return {"id": check_id, "passed": passed, "details": details}


def _runtime_probe(executable: str, repo: Path, store: Path) -> dict[str, Any]:
    return _run_python(
        executable,
        repo,
        store,
        """
        import json, sys
        from importlib.metadata import version
        import loci
        print(json.dumps({
            "executable": sys.executable,
            "loci_file": loci.__file__,
            "dependencies": {name: version(name) for name in
                ("tree-sitter-language-pack", "pathspec", "mcp", "PyYAML", "pytest")},
        }))
        """,
    )


def _policy_probe(executable: str, repo: Path, store: Path) -> dict[str, Any]:
    return _run_python(
        executable,
        repo,
        store,
        """
        import json
        from pathlib import PurePath
        from loci.indexability import (
            is_excluded_repository_path, is_indexable_source_path,
            repository_path_exclusion_root, source_exclusion_reason,
        )

        excluded = [
            "tools/.direnv/lib/site.py",
            ".direnv/node_modules/pkg/index.js",
            "deep/tools/.direnv/lib/component.ts",
        ]
        result = {"excluded": {}, "controls": {}, "path_errors": {}}
        for raw in excluded:
            path = PurePath(raw)
            result["excluded"][raw] = {
                "excluded": is_excluded_repository_path(path),
                "indexable": is_indexable_source_path(path),
                "root": str(repository_path_exclusion_root(path)),
                "reason": source_exclusion_reason(path),
            }
        for raw in (
            "tools/.direnv-tools/site.py", "src/loci/indexability.py",
            "tests/fixtures/sample.rs", "tools/.uv-cache/probe.py",
        ):
            path = PurePath(raw)
            result["controls"][raw] = {
                "excluded": is_excluded_repository_path(path),
                "indexable": is_indexable_source_path(path),
                "reason": source_exclusion_reason(path),
            }
        for raw in ("/tmp/outside.py", "../outside.py"):
            try:
                is_indexable_source_path(PurePath(raw))
            except ValueError as exc:
                result["path_errors"][raw] = type(exc).__name__
            except Exception as exc:
                result["path_errors"][raw] = type(exc).__name__
            else:
                result["path_errors"][raw] = None
        print(json.dumps(result))
        """,
    )


def _scan_probe(executable: str, repo: Path, store: Path, fixture: Path) -> dict[str, Any]:
    return _run_python(
        executable,
        repo,
        store,
        """
        import json, sys
        from pathlib import Path
        from loci.service import get_store, index_repo

        root = Path(sys.argv[1])
        root.mkdir(parents=True, exist_ok=True)
        (root / ".gitignore").write_text("ignored.py\\n", encoding="utf-8")
        (root / "kept.py").write_text("def scan_kept_symbol():\\n    return 1\\n", encoding="utf-8")
        (root / "ignored.py").write_text("def ignored_symbol():\\n    return 1\\n", encoding="utf-8")
        cache = root / "nested" / ".uv-cache"
        cache.mkdir(parents=True, exist_ok=True)
        (cache / "cached.py").write_text("def cache_symbol():\\n    return 1\\n", encoding="utf-8")
        index_repo(root, incremental=False)
        index = get_store().load(root.resolve())
        print(json.dumps({"files": sorted(index["file_hashes"]),
                          "symbols": sorted(item["name"] for item in index["symbols"])}))
        """,
        str(fixture),
    )


def _incremental_probe(
    executable: str, repo: Path, store: Path, fixture: Path
) -> dict[str, Any]:
    return _run_python(
        executable,
        repo,
        store,
        """
        import json, sys
        from pathlib import Path
        from loci.service import get_store, index_repo, search_symbols

        root = Path(sys.argv[1])
        root.mkdir(parents=True, exist_ok=True)
        moved = root / "move_me.py"
        sibling = root / "sibling.py"
        moved.write_text("def episode_moved_symbol():\\n    return 'moved'\\n", encoding="utf-8")
        sibling.write_text("def episode_sibling_symbol():\\n    return 'sibling'\\n", encoding="utf-8")
        index_repo(root, incremental=False)
        before = get_store().load(root.resolve())
        destination = root / "tools" / ".direnv" / "lib" / "moved.py"
        destination.parent.mkdir(parents=True, exist_ok=True)
        moved.replace(destination)
        indexed = index_repo(root, incremental=True)
        after = get_store().load(root.resolve())
        moved_search = search_symbols(root, "episode_moved_symbol", limit=20)
        sibling_search = search_symbols(root, "episode_sibling_symbol", limit=20)
        print(json.dumps({
            "before_files": sorted(before["file_hashes"]),
            "after_files": sorted(after["file_hashes"]),
            "after_symbols": [{"name": item["name"], "file": item["file_path"]}
                              for item in after["symbols"]],
            "moved_search": [{"name": item["name"], "file": item["file_path"]}
                             for item in moved_search],
            "sibling_search": [{"name": item["name"], "file": item["file_path"]}
                               for item in sibling_search],
            "incremental": indexed,
        }))
        """,
        str(fixture),
        timeout=120,
    )


def _agent_regression_check(repo: Path) -> dict[str, Any]:
    policy = repo / "tests" / "test_indexability.py"
    service = repo / "tests" / "test_service.py"
    missing = [str(path.relative_to(repo)) for path in (policy, service) if not path.is_file()]
    if missing:
        return {"passed": False, "missing": missing}
    policy_text = policy.read_text(encoding="utf-8")
    service_text = service.read_text(encoding="utf-8")
    policy_terms = {
        "direnv": ".direnv" in policy_text,
        "lookalike": ".direnv-tools" in policy_text,
        "both_policy_functions": (
            "is_excluded_repository_path" in policy_text
            and "is_indexable_source_path" in policy_text
        ),
        "path_safety": "ValueError" in policy_text,
    }
    service_terms = {
        "direnv": ".direnv" in service_text,
        "index": "index_repo" in service_text,
        "incremental": "incremental=True" in service_text,
        "search_or_stored_symbols": (
            "search_symbols" in service_text or "[\"symbols\"]" in service_text
        ),
    }
    return {
        "passed": all(policy_terms.values()) and all(service_terms.values()),
        "policy": policy_terms,
        "integration": service_terms,
    }


def _focused_tests(executable: str, repo: Path, store: Path) -> dict[str, Any]:
    commands = [
        [executable, "-m", "pytest", "-q", "tests/test_indexability.py"],
        [executable, "-m", "pytest", "-q", "tests/test_cli.py", "-k", "gitignore or uv_cache or direnv"],
        [executable, "-m", "pytest", "-q", "tests/test_service.py", "-k", "direnv or incremental"],
    ]
    results: list[dict[str, Any]] = []
    for command in commands:
        try:
            completed = subprocess.run(
                command, cwd=repo, env=_child_environment(repo, store), text=True,
                capture_output=True, timeout=180, check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            results.append({"command": command[2:], "passed": False, "error": str(exc)})
            continue
        results.append({
            "command": command[2:], "passed": completed.returncode == 0,
            "stdout": completed.stdout[-2000:], "stderr": completed.stderr[-2000:],
        })
    return {"passed": all(item["passed"] for item in results), "commands": results}


def evaluate(
    repo: Path,
    *,
    work_dir: Path,
    python_executable: str | None = None,
) -> dict[str, Any]:
    """Evaluate one final Loci episode snapshot without importing its product code.

    ``repo`` is the agent's isolated target checkout.  ``work_dir`` is evaluator
    writable space; fixtures and every fresh ``LOCI_BASE_DIR`` live beneath it.
    """
    started = time.monotonic()
    repo = Path(repo).resolve()
    work_dir = Path(work_dir).resolve()
    executable = python_executable or sys.executable
    errors: list[dict[str, str]] = []
    checks: list[dict[str, Any]] = []
    runtime: dict[str, Any] = {"python_executable": executable}
    provenance: dict[str, Any] = {
        "target_commit": TARGET_COMMIT,
        "target_repo": str(repo),
        "environment_asset": str(ENVIRONMENT_ASSET),
        "environment_asset_sha256": _sha256(ENVIRONMENT_ASSET),
        "target_source_contract": "child process PYTHONPATH begins with <repo>/src",
    }
    if not repo.is_dir() or not (repo / "src" / "loci").is_dir():
        return {
            "schema_version": SCHEMA_VERSION, "episode_id": EPISODE_ID,
            "status": "unavailable", "checks": [],
            "errors": [{"code": "TARGET_SOURCE_UNAVAILABLE", "message": "repo/src/loci is required"}],
            "runtime": runtime, "provenance": provenance,
        }
    work_dir.mkdir(parents=True, exist_ok=True)
    root = work_dir / "loci-oracle-fixtures"
    root.mkdir(parents=True, exist_ok=True)

    runtime_probe = _runtime_probe(executable, repo, root / "runtime-store")
    if not runtime_probe.get("ok"):
        errors.append({"code": "RUNTIME_UNAVAILABLE", "message": runtime_probe.get("error") or runtime_probe.get("stderr", "runtime probe failed")})
        return {
            "schema_version": SCHEMA_VERSION, "episode_id": EPISODE_ID,
            "status": "unavailable", "checks": [], "errors": errors,
            "runtime": runtime, "provenance": provenance,
        }
    runtime.update(runtime_probe["payload"])
    loci_file = Path(runtime["loci_file"]).resolve()
    expected_source = (repo / "src").resolve()
    import_is_target = loci_file.is_relative_to(expected_source)
    checks.append(_check("target_source_import", import_is_target, {
        "loci_file": str(loci_file), "expected_source": str(expected_source),
    }))
    pinned_dependencies = _asset()["dependencies"]
    observed_dependencies = runtime["dependencies"]
    environment_matches = observed_dependencies == pinned_dependencies
    checks.append(_check("pinned_target_environment", environment_matches, {
        "expected": pinned_dependencies, "observed": observed_dependencies,
    }))
    if not environment_matches:
        errors.append({
            "code": "PINNED_ENVIRONMENT_MISMATCH",
            "message": "The evaluator dependency environment does not match loci_environment.json",
        })
        return {
            "schema_version": SCHEMA_VERSION, "episode_id": EPISODE_ID,
            "status": "unavailable", "checks": checks, "errors": errors,
            "runtime": runtime, "provenance": provenance,
        }

    policy = _policy_probe(executable, repo, root / "policy-store")
    if not policy.get("ok"):
        errors.append({"code": "POLICY_PROBE_FAILED", "message": policy.get("stderr", policy.get("error", "failed"))})
        checks.append(_check("nested_exclusion", False, {"probe": policy}))
        checks.append(_check("negative_policy_controls", False, {"probe": policy}))
        checks.append(_check("path_safety", False, {"probe": policy}))
    else:
        observed = policy["payload"]
        expected_paths = {
            "tools/.direnv/lib/site.py": "tools/.direnv",
            ".direnv/node_modules/pkg/index.js": ".direnv",
            "deep/tools/.direnv/lib/component.ts": "deep/tools/.direnv",
        }
        nested = all(
            observed["excluded"][path] == {
                "excluded": True, "indexable": False, "root": root_path,
                "reason": "policy_excluded",
            }
            for path, root_path in expected_paths.items()
        )
        controls = observed["controls"]
        negative = (
            controls["tools/.direnv-tools/site.py"]["indexable"] is True
            and controls["src/loci/indexability.py"]["indexable"] is True
            and controls["tests/fixtures/sample.rs"]["indexable"] is True
            and controls["tools/.uv-cache/probe.py"] == {
                "excluded": True, "indexable": False, "reason": "policy_excluded",
            }
        )
        path_safety = observed["path_errors"] == {
            "/tmp/outside.py": "ValueError", "../outside.py": "ValueError",
        }
        checks.extend([
            _check("nested_exclusion", nested, observed["excluded"]),
            _check("negative_policy_controls", negative, controls),
            _check("path_safety", path_safety, observed["path_errors"]),
        ])

    scan = _scan_probe(executable, repo, root / "scan-store", root / "scan-repo")
    if scan.get("ok"):
        files = scan["payload"]["files"]
        scan_passed = (
            files == ["kept.py"]
            and "scan_kept_symbol" in scan["payload"]["symbols"]
            and "ignored_symbol" not in scan["payload"]["symbols"]
            and "cache_symbol" not in scan["payload"]["symbols"]
        )
        checks.append(_check("gitignore_uv_cache", scan_passed, scan["payload"]))
    else:
        errors.append({"code": "SCAN_PROBE_FAILED", "message": scan.get("stderr", scan.get("error", "failed"))})
        checks.append(_check("gitignore_uv_cache", False, {"probe": scan}))

    incremental = _incremental_probe(
        executable, repo, root / "incremental-store", root / "incremental-repo"
    )
    if incremental.get("ok"):
        result = incremental["payload"]
        after_files = result["after_files"]
        moved_in_index = any("move_me.py" in name or ".direnv" in name for name in after_files)
        moved_symbols = [item for item in result["after_symbols"] if item["name"] == "episode_moved_symbol"]
        sibling_symbols = [item for item in result["sibling_search"] if item["name"] == "episode_sibling_symbol"]
        moved_search = [item for item in result["moved_search"] if item["name"] == "episode_moved_symbol"]
        incremental_passed = (
            "move_me.py" in result["before_files"] and not moved_in_index
            and not moved_symbols and not moved_search
            and sibling_symbols and sibling_symbols[0]["file"] == "sibling.py"
        )
        checks.append(_check("incremental_terminal_state", incremental_passed, result))
    else:
        errors.append({"code": "INCREMENTAL_PROBE_FAILED", "message": incremental.get("stderr", incremental.get("error", "failed"))})
        checks.append(_check("incremental_terminal_state", False, {"probe": incremental}))

    regression = _agent_regression_check(repo)
    checks.append(_check("regression_deliverable", regression.pop("passed"), regression))
    focused = _focused_tests(executable, repo, root / "focused-test-store")
    checks.append(_check("focused_target_tests", focused.pop("passed"), focused))

    source_files = [repo / "src" / "loci" / "indexability.py", repo / "tests" / "test_indexability.py", repo / "tests" / "test_service.py"]
    provenance["evaluated_file_hashes"] = {
        str(path.relative_to(repo)): _sha256(path) for path in source_files if path.is_file()
    }
    runtime["elapsed_seconds"] = round(time.monotonic() - started, 3)
    status = "passed" if all(check["passed"] for check in checks) else "failed"
    return {
        "schema_version": SCHEMA_VERSION, "episode_id": EPISODE_ID, "status": status,
        "checks": checks, "errors": errors, "runtime": runtime, "provenance": provenance,
        "limitations": [
            "The evaluator scores terminal behavior and regression shape; it does not score the read-only orientation explanation or an agent's prose summary.",
            "Regression-deliverable inspection confirms focused policy and integration evidence exists and the target tests execute, while independent fixture probes remain the behavior oracle.",
        ],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", required=True, type=Path)
    parser.add_argument("--work-dir", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--python-executable")
    args = parser.parse_args(argv)
    receipt = evaluate(args.repo, work_dir=args.work_dir, python_executable=args.python_executable)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return 0 if receipt["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
