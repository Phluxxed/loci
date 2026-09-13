"""Publishable, tamper-evident W4.7 inputs; never executes provider calls."""
from __future__ import annotations

import argparse
import importlib.metadata
import json
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import time

from benchmarks.typescript_context_baseline import ROOT, save, sha

COMPARISON = "multilingual-context-workflow-v1"
COMPARISON_ROOT = ROOT / "benchmarks/comparisons" / COMPARISON
ORIGINAL = ROOT / "benchmarks/corpora/multilingual-context-v1"
ENGINE_COMMIT = "4f2668160df59bfb114a28a2069f9a0198da469b"
IMMUTABLE_INPUTS = ("corpus.json", "corpus.sha256", "fixtures.tar.gz")


def git(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()


def hashes(paths) -> dict[str, str]:
    return {p.relative_to(ROOT).as_posix(): sha(p.read_bytes()) for p in sorted(paths)}


def engine_identity() -> dict:
    from loci import service
    from loci.storage.index_store import EXTRACTOR_VERSION

    if Path(service.__file__).resolve() != ROOT / "src/loci/service.py":
        raise ValueError("a different loci engine is imported")
    paths = [ROOT / p for p in git("ls-tree", "-r", "--name-only", ENGINE_COMMIT, "--", "src").splitlines()]
    actual = hashes(paths)
    for name, digest in actual.items():
        original = subprocess.check_output(["git", "show", ENGINE_COMMIT + ":" + name], cwd=ROOT)
        if sha(original) != digest:
            raise ValueError("engine differs from accepted W4.6 source: " + name)
    if git("status", "--porcelain", "--", "src"):
        raise ValueError("engine must be clean")
    if EXTRACTOR_VERSION != 30:
        raise ValueError("extractor changed")
    return {"commit": ENGINE_COMMIT, "source_tree": git("rev-parse", ENGINE_COMMIT + ":src"),
            "extractor_version": EXTRACTOR_VERSION, "graph_state_version": 14, "files": actual}


def harness_files() -> dict[str, str]:
    # Include transitive legacy helpers rather than infer an incomplete import graph.
    paths = list((ROOT / "benchmarks").glob("*.py"))
    paths += list((ROOT / "tests").glob("test_multilingual_context*.py"))
    paths += [ROOT / "pyproject.toml", ROOT / "uv.lock"]
    return hashes(paths)


def environment_identity() -> dict:
    executable = shutil.which("codex")
    if executable is None:
        raise ValueError("frozen Codex CLI is unavailable")
    return {"python": sys.version, "platform": platform.platform(), "machine": platform.machine(),
            "packages": dict(sorted((p.metadata["Name"], p.version) for p in importlib.metadata.distributions())),
            "pyproject_sha256": sha((ROOT / "pyproject.toml").read_bytes()),
            "uv_lock_sha256": sha((ROOT / "uv.lock").read_bytes()),
            "codex_cli_sha256": sha(Path(executable).resolve().read_bytes())}


def _input_identity() -> tuple[dict, dict]:
    from benchmarks.multilingual_context_inputs import load_inputs

    corpus, controls = load_inputs()
    for name in IMMUTABLE_INPUTS:
        if (ORIGINAL / name).read_bytes() != (Path(corpus["_root"]) / name).read_bytes():
            raise ValueError("evaluator view changed frozen source: " + name)
    if controls["environment"] != environment_identity():
        raise ValueError("environment differs from comparison controls")
    return corpus, controls


def build_freeze() -> dict:
    from benchmarks.multilingual_context_compare import build_prompt, schedule

    corpus, controls = _input_identity()
    transport = json.loads((COMPARISON_ROOT / "transport-verification.json").read_text())
    scorer = json.loads((COMPARISON_ROOT / "scorer-verification.json").read_text())
    replay = json.loads((COMPARISON_ROOT / "replay-preflight.json").read_text())
    if not transport.get("passed") or not scorer.get("passed") or not replay.get("passed"):
        raise ValueError("successful actual-output scorer, offline transport and replay proofs are required")
    catalog = COMPARISON_ROOT / "host-preflight/model-catalog.json"
    if not catalog.is_file():
        raise ValueError("retained current model catalog is required")
    paths = [p for p in COMPARISON_ROOT.rglob("*") if p.is_file() and p.name != "freeze.json"]
    if any(p.is_symlink() for p in paths):
        raise ValueError("comparison evidence cannot contain symlinks")
    file_hashes = {**harness_files(), **hashes(paths), **hashes(ORIGINAL / n for n in IMMUTABLE_INPUTS)}
    if git("status", "--porcelain", "--", *file_hashes):
        raise ValueError("preparation code, controls and proofs must be committed before freezing")
    return {"schema_version": 1, "version": COMPARISON,
            "freeze_commit": git("rev-parse", "HEAD"),
            "frozen_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "engine": engine_identity(), "files": file_hashes,
            "harness_files": harness_files(), "environment": environment_identity(),
            "model": controls["agent"]["model"], "reasoning_effort": controls["agent"]["reasoning_effort"],
            "service_tier": controls["agent"]["service_tier"],
            "request_max_retries": controls["agent"]["request_max_retries"],
            "stream_max_retries": controls["agent"]["stream_max_retries"],
            "corpus_sha256": controls["corpus_sha256"],
            "controls_sha256": sha((Path(corpus["_root"]) / "comparison-controls.json").read_bytes()),
            "workflow_guide_sha256": sha(controls["agent"]["workflow_guide"].encode()),
            "model_catalog_sha256": sha(catalog.read_bytes()),
            "canonical_tool_schemas_sha256": transport["canonical_tool_schemas_sha256"],
            "prompt_sha256": {f"{c['id']}-{a}": sha(build_prompt(corpus, controls, c["id"], a).encode())
                              for c in corpus["cases"] for a in ("A", "B")},
            "plan": schedule(corpus),
            "claims_limit": "Local request serialization, raw CLI/MCP payloads and usage; no retained production HTTP bodies or pinned backend model snapshot."}


def validate_freeze(path: Path, *, require_published: bool = True) -> dict:
    from benchmarks.multilingual_context_compare import build_prompt, schedule

    path = Path(path).resolve()
    value = json.loads(path.read_text())
    corpus, controls = _input_identity()
    if value.get("version") != COMPARISON or value["plan"] != schedule(corpus):
        raise ValueError("freeze identity or plan changed")
    if value["engine"] != engine_identity() or value["harness_files"] != harness_files():
        raise ValueError("frozen engine or harness changed")
    for name, digest in value["files"].items():
        target = ROOT / name
        if target.is_symlink() or sha(target.read_bytes()) != digest:
            raise ValueError("frozen input changed: " + name)
        committed = subprocess.check_output(["git", "show", value["freeze_commit"] + ":" + name], cwd=ROOT)
        if sha(committed) != digest:
            raise ValueError("freeze does not match preparation commit: " + name)
    if value["environment"] != environment_identity():
        raise ValueError("frozen runtime environment changed")
    for key in ("model", "reasoning_effort", "service_tier", "request_max_retries", "stream_max_retries"):
        if value[key] != controls["agent"][key]:
            raise ValueError("frozen model/transport setting changed: " + key)
    if value["corpus_sha256"] != controls["corpus_sha256"] or value["controls_sha256"] != sha((Path(corpus["_root"]) / "comparison-controls.json").read_bytes()):
        raise ValueError("frozen corpus/controls changed")
    prompts = {f"{c['id']}-{a}": sha(build_prompt(corpus, controls, c["id"], a).encode())
               for c in corpus["cases"] for a in ("A", "B")}
    if value["prompt_sha256"] != prompts or value["workflow_guide_sha256"] != sha(controls["agent"]["workflow_guide"].encode()):
        raise ValueError("frozen prompt changed")
    relative = path.relative_to(ROOT).as_posix()
    if git("status", "--porcelain", "--", *value["files"], relative):
        raise ValueError("frozen files must be committed")
    if subprocess.check_output(["git", "show", "HEAD:" + relative], cwd=ROOT) != path.read_bytes():
        raise ValueError("freeze must be committed")
    if require_published:
        branch = git("branch", "--show-current")
        if branch != "feat/evidence-backed-exploration":
            raise ValueError("unexpected execution branch")
        remote = git("ls-remote", "origin", "refs/heads/" + branch).split()[0]
        # A later local report commit is acceptable once the declaration itself
        # is present at the published remote head.
        if subprocess.check_output(["git", "show", remote + ":" + relative], cwd=ROOT) != path.read_bytes():
            raise ValueError("freeze must be published before provider outcomes")
    return {**value, "freeze_json_sha256": sha(path.read_bytes())}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("build", "validate"))
    parser.add_argument("--path", type=Path, default=COMPARISON_ROOT / "freeze.json")
    args = parser.parse_args()
    if args.mode == "build":
        if args.path.exists():
            raise ValueError("a freeze declaration is never overwritten")
        save(args.path, build_freeze())
        print(json.dumps({"freeze": str(args.path), "provider_calls": 0}))
    else:
        value = validate_freeze(args.path)
        print(json.dumps({"valid": True, "planned_runs": len(value["plan"]),
                          "freeze_json_sha256": value["freeze_json_sha256"]}))


if __name__ == "__main__":
    main()
