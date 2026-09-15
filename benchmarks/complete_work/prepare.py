"""Prepare one isolated, unmeasured complete-work episode target.

This module only constructs matched source, control, and dependency inputs.  It
does not create a campaign freeze, start a model turn, or invoke a provider.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
from typing import Any, Mapping, Sequence

from . import controller
from .oracles import anvil


SCHEMA_VERSION = 1
LOCI_COMMIT = "f3d9134aece5156bec1dcc302d4330522d1d96e5"
DESIGN_ROOT = Path(__file__).resolve().parents[1] / "complete-work" / "design-v1"
EPISODES_PATH = DESIGN_ROOT / "episodes.json"
SCHEDULE_PATH = DESIGN_ROOT / "schedule.json"
LOCI_ENVIRONMENT = Path(__file__).with_name("oracles") / "loci_environment.json"
RUNTIME_DIRECTORIES = frozenset({".complete-work-isolation.json", ".venv", "node_modules", ".episode-tmp", ".episode-store"})
LOCI_EXCLUDED_TOP_LEVEL = frozenset({"benchmarks", ".scratch", ".manifest", "ISSUES_LIST", "ISSUES_LIST.md", ".claude"})
DEPENDENCY_TIMEOUT_SECONDS = 300
LOCI_TREE_SITTER_REQUIREMENT = "tree-sitter==0.25.2"  # Pinned by the exported commit's uv.lock.


class PreparationError(ValueError):
    """The requested disposable target cannot be prepared safely."""


class DependencyPreparationError(PreparationError):
    def __init__(self, message: str, provenance: dict[str, Any]) -> None:
        super().__init__(message)
        self.provenance = provenance


def prepare_target_index(control_path: Path, *, executable: Path, serving_root: Path) -> dict[str, Any]:
    """Run the control's positional CLI with ``--prepare`` before timed work."""
    environment = os.environ.copy()
    environment["PYTHONPATH"] = os.pathsep.join((str(serving_root), str(serving_root / "src")))
    command = [str(executable), "-m", "benchmarks.complete_work.control", "--prepare", str(control_path)]
    try:
        completed = subprocess.run(command, cwd=serving_root, env=environment, text=True, capture_output=True, timeout=DEPENDENCY_TIMEOUT_SECONDS, check=False)
    except subprocess.TimeoutExpired as error:
        raise DependencyPreparationError(
            "control preindex timed out",
            {"commands": [{"command": command, "timeout_seconds": DEPENDENCY_TIMEOUT_SECONDS, "timed_out": True, "stdout": error.stdout or "", "stderr": error.stderr or ""}]},
        ) from error
    if completed.returncode != 0:
        raise DependencyPreparationError(
            "control preindex could not prepare the clean target",
            {"commands": [{"command": command, "timeout_seconds": DEPENDENCY_TIMEOUT_SECONDS, "timed_out": False, "returncode": completed.returncode, "stdout": completed.stdout, "stderr": completed.stderr}]},
        )
    try:
        return json.loads(completed.stdout)
    except json.JSONDecodeError as error:
        raise DependencyPreparationError(
            "control preindex returned invalid JSON",
            {"commands": [{"command": command, "timeout_seconds": DEPENDENCY_TIMEOUT_SECONDS, "timed_out": False, "returncode": completed.returncode, "stdout": completed.stdout, "stderr": completed.stderr}]},
        ) from error


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_json(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)


def _run_command(command: list[str], *, cwd: Path, timeout: int = DEPENDENCY_TIMEOUT_SECONDS) -> dict[str, Any]:
    """Run a preparation command with complete, evaluator-visible receipts."""
    try:
        completed = subprocess.run(command, cwd=cwd, text=True, capture_output=True, timeout=timeout, check=False)
    except subprocess.TimeoutExpired as error:
        return {
            "command": command,
            "cwd": str(cwd),
            "timeout_seconds": timeout,
            "timed_out": True,
            "returncode": None,
            "stdout": error.stdout or "",
            "stderr": error.stderr or "",
        }
    except OSError as error:
        return {
            "command": command,
            "cwd": str(cwd),
            "timeout_seconds": timeout,
            "timed_out": False,
            "returncode": None,
            "stdout": "",
            "stderr": str(error),
        }
    return {
        "command": command,
        "cwd": str(cwd),
        "timeout_seconds": timeout,
        "timed_out": False,
        "returncode": completed.returncode,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
    }


def _require_command(result: dict[str, Any], message: str, provenance: dict[str, Any]) -> None:
    if result["timed_out"] or result["returncode"] != 0:
        provenance["commands"].append(result)
        raise DependencyPreparationError(message, provenance)
    provenance["commands"].append(result)


def _loci_python() -> Path:
    """Choose a supported interpreter before creating a target Loci environment."""
    for name in ("python3.13", "python3.12", "python3.11", "python3.10"):
        found = shutil.which(name)
        if found is not None:
            return Path(found).resolve(strict=True)
    raise PreparationError("Loci preparation needs a Python 3.10 through 3.13 interpreter")


def _interpreter_baseprefix(executable: Path) -> Path:
    result = _run_command([str(executable), "-c", "import sys; print(sys.base_prefix)"], cwd=Path.cwd(), timeout=30)
    if result["timed_out"] or result["returncode"] != 0:
        raise PreparationError("could not identify the interpreter base prefix")
    return Path(result["stdout"].strip()).resolve(strict=True)


def _contains(parent: Path, child: Path) -> bool:
    try:
        child.relative_to(parent)
        return True
    except ValueError:
        return False


def _load_selected_run(run_id: str) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    episodes = json.loads(EPISODES_PATH.read_text(encoding="utf-8"))
    schedule = json.loads(SCHEDULE_PATH.read_text(encoding="utf-8"))
    rows = [row for row in schedule.get("rows", []) if row.get("episode_run_id") == run_id]
    if len(rows) != 1:
        raise PreparationError("run_id must name exactly one design schedule row")
    row = rows[0]
    definitions = [item for item in episodes.get("episodes", []) if item.get("id") == row.get("episode_id")]
    if len(definitions) != 1:
        raise PreparationError("selected schedule row has no unique episode definition")
    return episodes, row, definitions[0]


def _source_file_map(root: Path) -> dict[str, str]:
    files: dict[str, str] = {}
    for directory, children, filenames in os.walk(root, followlinks=False):
        children[:] = sorted(name for name in children if name not in RUNTIME_DIRECTORIES)
        for name in sorted(filenames):
            if name in RUNTIME_DIRECTORIES:
                continue
            path = Path(directory) / name
            if path.is_symlink():
                raise PreparationError("prepared target contains a source symlink")
            files[path.relative_to(root).as_posix()] = _sha256(path)
    return files


def _safe_member_name(name: str) -> Path:
    candidate = Path(name)
    if candidate.is_absolute() or ".." in candidate.parts:
        raise PreparationError("git archive contains an unsafe member path")
    return candidate


def _export_loci(serving_root: Path, target: Path) -> dict[str, Any]:
    """Extract the selected commit while retaining a concrete exclusion receipt."""
    result = subprocess.run(
        ["git", "-C", str(serving_root), "archive", "--format=tar", LOCI_COMMIT],
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        raise PreparationError("git archive could not export the pinned Loci commit")
    excluded: dict[str, int] = {name: 0 for name in sorted(LOCI_EXCLUDED_TOP_LEVEL)}
    with tarfile.open(fileobj=io.BytesIO(result.stdout), mode="r:") as archive:
        for member in archive.getmembers():
            relative = _safe_member_name(member.name)
            top = relative.parts[0] if relative.parts else ""
            if top in LOCI_EXCLUDED_TOP_LEVEL:
                excluded[top] += 1
                continue
            if member.isdir():
                (target / relative).mkdir(parents=True, exist_ok=True)
                continue
            if not member.isfile():
                raise PreparationError("git archive contains a non-regular source member")
            destination = target / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            source = archive.extractfile(member)
            if source is None:
                raise PreparationError("git archive member could not be read")
            with destination.open("xb") as output:
                shutil.copyfileobj(source, output)
    return {
        "kind": "git_archive",
        "commit": LOCI_COMMIT,
        "excluded_top_level": sorted(LOCI_EXCLUDED_TOP_LEVEL),
        "excluded_members": excluded,
        "full_git_history": False,
    }


def _prepare_anvil(target: Path) -> dict[str, Any]:
    metadata = anvil.prepare_target(target)
    return {
        "kind": "retained_file_manifest",
        "commit": anvil.SOURCE_COMMIT,
        "file_count": anvil.SOURCE_FILE_COUNT,
        "package_lock_sha256": metadata["package_lock_sha256"],
    }


def _install_dependencies(target: Path, episode_id: str) -> dict[str, Any]:
    if episode_id == "anvil-creation-evidence":
        provenance: dict[str, Any] = {
            "kind": "npm_ci",
            "commands": [],
            "package_lock_sha256": _sha256(target / "package-lock.json"),
        }
        _require_command(
            _run_command(["npm", "ci"], cwd=target),
            "npm ci could not prepare the pinned Anvil dependencies",
            provenance,
        )
        node = _run_command(["node", "--version"], cwd=target, timeout=30)
        _require_command(node, "Node runtime is unavailable after npm ci", provenance)
        provenance["node_version"] = node["stdout"].strip()
        return {"status": "prepared", "kind": "npm_ci", "lockfile": "package-lock.json", "provenance": provenance}
    if episode_id == "loci-direnv-exclusion":
        asset = json.loads(LOCI_ENVIRONMENT.read_text(encoding="utf-8"))
        environment = target / ".venv"
        base_python = _loci_python()
        version = _run_command([str(base_python), "--version"], cwd=target, timeout=30)
        provenance = {"kind": "venv_pip", "commands": [], "environment_asset_sha256": _sha256(LOCI_ENVIRONMENT), "base_python": str(base_python), "base_prefix": str(_interpreter_baseprefix(base_python)), "python_version": version["stdout"].strip() or version["stderr"].strip()}
        _require_command(version, "selected Python runtime is unavailable", provenance)
        _require_command(
            _run_command([str(base_python), "-m", "venv", str(environment)], cwd=target),
            "Python venv creation could not prepare Loci dependencies",
            provenance,
        )
        executable = environment / "bin" / "python"
        requirements = [f"{name}=={version}" for name, version in asset["dependencies"].items()] + [LOCI_TREE_SITTER_REQUIREMENT]
        _require_command(
            _run_command([str(executable), "-m", "pip", "install", *requirements], cwd=target),
            "pip could not prepare the pinned Loci dependencies",
            provenance,
        )
        freeze = _run_command([str(executable), "-m", "pip", "freeze", "--all"], cwd=target, timeout=60)
        _require_command(freeze, "pip freeze could not verify pinned Loci dependencies", provenance)
        provenance["pip_freeze"] = freeze["stdout"]
        provenance["archive_lock_constraint"] = LOCI_TREE_SITTER_REQUIREMENT
        return {"status": "prepared", "kind": "venv_pip", "environment": ".venv", "requirements": requirements, "provenance": provenance}
    raise PreparationError("selected episode has no dependency preparation contract")


def _instruction_text() -> str:
    return (
        "The configured Loci tools provide normal repository retrieval. Their retrieve operation returns bounded context and source references; "
        "their read operation expands a returned source reference when exact source is needed. Their use remains an ordinary navigation choice. "
        "Treat returned source and proof as evidence, and use ordinary local source and test tools as needed.\n"
    )


def _runtime_readonly_roots(episode_id: str, dependencies: Mapping[str, Any]) -> list[str]:
    interpreter = _loci_python() if episode_id == "loci-direnv-exclusion" else Path(sys.executable).resolve(strict=True)
    roots = [str(_interpreter_baseprefix(interpreter))]
    if episode_id == "anvil-creation-evidence":
        node = shutil.which("node")
        if node is None:
            raise PreparationError("Node runtime is unavailable for the Anvil target")
        node_path = Path(node).resolve(strict=True)
        system = _contains(Path("/usr"), node_path) or _contains(Path("/System"), node_path)
        if not system:
            roots.append(str(node_path.parent.parent))
    return list(dict.fromkeys(roots))


def prepare_run(
    run_id: str,
    destination: Path,
    *,
    serving_root: Path,
    user_config: Path | None = None,
    install_dependencies: bool = False,
    preindex: bool = False,
) -> dict[str, Any]:
    """Construct a single matched run directory without launching the episode."""
    _, row, episode = _load_selected_run(run_id)
    destination = destination.resolve()
    serving_root = serving_root.resolve(strict=True)
    repo_root = Path(__file__).resolve().parents[2]
    if destination.exists():
        raise PreparationError("destination must not already exist")
    if _contains(repo_root, destination) or _contains(destination, repo_root):
        raise PreparationError("destination must be outside the serving repository")
    if _contains(serving_root, destination) or _contains(destination, serving_root):
        raise PreparationError("destination and serving_root must be disjoint")
    if row["episode_id"] not in {"anvil-creation-evidence", "loci-direnv-exclusion"}:
        raise PreparationError("selected episode is not supported by preparation")

    target = destination / "workspaces" / run_id
    observer = destination / "observer"
    controls = observer / "controls"
    preparation = observer / "preparation"
    receipts = observer / "receipts"
    store = observer / "store"
    output = observer / "output"
    for directory in (target.parent, controls, receipts, store, preparation):
        directory.mkdir(parents=True, exist_ok=False)
    if row["episode_id"] == "anvil-creation-evidence":
        source = _prepare_anvil(target)
    else:
        target.mkdir()
        source = _export_loci(serving_root, target)
    source_files = _source_file_map(target)
    marker = {
        "schema_version": SCHEMA_VERSION,
        "run_id": run_id,
        "episode_id": row["episode_id"],
        "source": source,
        "source_files": source_files,
        "runtime_directories": sorted(RUNTIME_DIRECTORIES),
    }
    _write_json(target / ".complete-work-isolation.json", marker)
    try:
        dependencies = (
            _install_dependencies(target, row["episode_id"])
            if install_dependencies
            else {"status": "unprepared", "reason": "use --install-deps before any controller run"}
        )
    except DependencyPreparationError as error:
        _write_json(preparation / "dependency-failure.json", {"error": str(error), "provenance": error.provenance})
        raise
    instruction = controls / "instructions.txt"
    instruction.write_text(_instruction_text(), encoding="utf-8")
    control_path = controls / "loci-control.json"
    control_value = {
        "schema_version": 1,
        "target_root": str(target),
        "arm": row["graph_enrichment"],
        "store_dir": str(store),
        "receipt_dir": str(receipts),
        "store_namespace": run_id,
    }
    _write_json(control_path, control_value)
    config_path = observer / "run.json"
    default_user_config = Path(os.environ.get("CODEX_HOME", "~/.codex")).expanduser() / "config.toml"
    selected_user_config = (user_config.resolve(strict=True) if user_config is not None else default_user_config.resolve(strict=True))
    if not selected_user_config.is_file():
        raise PreparationError("user_config must exist so the future freeze can digest its identity")
    environment_asset = (anvil.SOURCE_MANIFEST if row["episode_id"] == "anvil-creation-evidence" else LOCI_ENVIRONMENT)
    provenance_path = preparation / "provenance.json"
    config = {
        "schema_version": SCHEMA_VERSION,
        "run_id": run_id,
        "repo": str(target),
        "serving_root": str(serving_root),
        "output_dir": str(output),
        "episodes_path": str(EPISODES_PATH),
        "schedule_path": str(SCHEDULE_PATH),
        "arm": row["graph_enrichment"],
        "readonly_roots": _runtime_readonly_roots(row["episode_id"], dependencies),
        "mcp_command": str(target / ".venv" / "bin" / "python") if row["episode_id"] == "loci-direnv-exclusion" and dependencies["status"] == "prepared" else str(_loci_python() if row["episode_id"] == "loci-direnv-exclusion" else Path(sys.executable).absolute()),
        "mcp_args": ["-m", "benchmarks.complete_work.control", str(control_path)],
        "mcp_env": {"PYTHONPATH": os.pathsep.join((str(serving_root), str(serving_root / "src")))},
        "mcp_config_path": str(control_path),
        "user_config": str(selected_user_config),
        "instruction_text_path": str(instruction),
        "dependencies_status": dependencies["status"],
        "dependency_preparation": dependencies,
        "oracle": {
            "episode_id": row["episode_id"],
            "settings": str(environment_asset),
            "python_executable": str(target / ".venv" / "bin" / "python") if row["episode_id"] == "loci-direnv-exclusion" and dependencies["status"] == "prepared" else None,
        },
        "preindex": {"requested": preindex, "status": "not_requested"},
        "freeze": {"status": "not_created"},
        "frozen_inputs": [str(environment_asset), str(provenance_path)],
    }
    snapshot = controller.source_snapshot(target, preparation / "source-history")
    provenance: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "run_id": run_id,
        "source": source,
        "source_snapshot": snapshot,
        "environment_asset": {"path": str(environment_asset), "sha256": _sha256(environment_asset)},
        "dependencies": dependencies,
        "runtime_readonly_roots": config["readonly_roots"],
    }
    _write_json(provenance_path, provenance)
    if preindex:
        if dependencies["status"] != "prepared":
            _write_json(provenance_path, provenance)
            raise PreparationError("--prepare requires --install-deps so indexing uses the pinned target environment")
        executable = target / ".venv" / "bin" / "python" if row["episode_id"] == "loci-direnv-exclusion" else Path(sys.executable)
        try:
            indexed = prepare_target_index(control_path, executable=executable, serving_root=serving_root)
        except DependencyPreparationError as error:
            provenance["preindex"] = {"requested": True, "status": "failed", "error": str(error), "provenance": error.provenance}
            _write_json(provenance_path, provenance)
            raise
        config["preindex"] = {"requested": True, "status": "prepared", "result": indexed}
        provenance["preindex"] = config["preindex"]
        _write_json(provenance_path, provenance)
    _write_json(config_path, config)
    return {"config_path": str(config_path), "target": str(target), "observer": str(observer), "run_id": run_id, "dependencies_status": dependencies["status"], "preindex": config["preindex"], "source": source}


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--destination", type=Path, required=True)
    parser.add_argument("--serving-root", type=Path, required=True)
    parser.add_argument("--user-config", type=Path)
    parser.add_argument("--install-deps", action="store_true")
    parser.add_argument("--prepare", action="store_true", help="preindex the bound target outside a timed turn")
    args = parser.parse_args(argv)
    try:
        result = prepare_run(args.run_id, args.destination, serving_root=args.serving_root, user_config=args.user_config, install_dependencies=args.install_deps, preindex=args.prepare)
    except PreparationError as error:
        parser.error(str(error))
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
