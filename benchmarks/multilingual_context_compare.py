"""Frozen matched multilingual exact-retrieval versus workflow comparison.

This module intentionally owns only host execution and immutable attempt
retention.  The evaluator view, tools, scorer, report, and freeze declaration
are separate versioned inputs.  No command here substitutes a provider result
for a failed or interrupted attempt.
"""
from __future__ import annotations

import argparse
import http.server
import json
from pathlib import Path
import shutil
import subprocess
import threading
import time
from typing import Any
import uuid

from benchmarks.typescript_context_baseline import (
    ROOT, child_environment, command, execute, launch_args, prepare_catalog, save, settings as base_settings,
    sha,
)
from benchmarks.multilingual_context_inputs import load_inputs
from benchmarks.typescript_context_corpus import _isolated_store, materialize_snapshot


COMPARISON = "multilingual-context-workflow-v1"
COMPARISON_ROOT = ROOT / "benchmarks" / "comparisons" / COMPARISON
INPUTS_ROOT = COMPARISON_ROOT / "inputs"
TOOLS_MODULE = "benchmarks.multilingual_context_tools"
OBSERVED_MODULE = "benchmarks.multilingual_context_observed"
MODEL = "gpt-5.6-luna"
REASONING_EFFORT = "high"
SERVICE_TIER = "default"
# Codex 0.154.0 rejects overrides of its reserved built-in OpenAI provider.
# These describe the frozen host fact, while the comparison itself still
# performs no outcome or selective retry under a scheduled attempt identity.
REQUEST_MAX_RETRIES = "builtin_cli_default_not_overridden"
STREAM_MAX_RETRIES = "builtin_cli_default_not_overridden"
REPETITIONS = 3
ARMS = ("A", "B")
EXPECTED_CASES = 19
EXPECTED_RUNS = EXPECTED_CASES * REPETITIONS * len(ARMS)


def schedule(corpus: dict[str, Any]) -> list[dict[str, Any]]:
    """Return the fixed 114-slot serial AB/BA schedule."""

    if corpus.get("version") != "multilingual-context-v1" or len(corpus.get("cases", [])) != EXPECTED_CASES:
        raise ValueError("W4.7 requires the frozen 19-case multilingual corpus")
    plan: list[dict[str, Any]] = []
    for ordinal, case in enumerate(corpus["cases"]):
        for repetition in range(1, REPETITIONS + 1):
            order = ARMS if (ordinal * REPETITIONS + repetition - 1) % 2 == 0 else tuple(reversed(ARMS))
            for arm in order:
                plan.append({
                    "attempt_id": f"{case['id']}-r{repetition}-{arm}",
                    "case_id": case["id"], "snapshot": case["snapshot"],
                    "repetition": repetition, "arm": arm,
                })
    if len(plan) != EXPECTED_RUNS or len({item["attempt_id"] for item in plan}) != EXPECTED_RUNS:
        raise ValueError("invalid fixed multilingual schedule")
    return plan


def build_prompt(corpus: dict[str, Any], controls: dict[str, Any], case_id: str, arm: str) -> str:
    """Construct only model-visible task text; corpus gold remains evaluator-side."""

    if arm not in ARMS:
        raise ValueError("comparison requires arm A or B")
    case = next((item for item in corpus["cases"] if item["id"] == case_id), None)
    if case is None:
        raise ValueError("unknown frozen case")
    agent = controls["agent"]
    guide = "" if arm == "A" else agent["workflow_guide"]
    if not isinstance(guide, str) or (arm == "B" and not guide.strip()):
        raise ValueError("B requires a frozen language-neutral workflow guide")
    return agent["common_prompt"] + guide + case["prompt"]


def settings(run_file: Path, catalog: Path, store: Path) -> dict[str, Any]:
    """Return the isolated Codex host configuration pinned by the W4 freeze."""

    value = base_settings(run_file, catalog, store)
    value.update({
        "service_tier": SERVICE_TIER,
        "mcp_servers.evaluation.args": ["-m", TOOLS_MODULE, str(run_file)],
    })
    return value


def _request_tools(request: dict[str, Any]) -> list[tuple[str, str]]:
    tools: list[tuple[str, str]] = []
    for item in request.get("input", []):
        if item.get("type") == "additional_tools":
            for namespace in item.get("tools", []):
                if namespace.get("type") != "namespace":
                    raise ValueError("unexpected hosted/discovery tool in evaluation request")
                tools.extend((namespace.get("name"), tool.get("name")) for tool in namespace.get("tools", []))
    return tools


def audit_request(request: dict[str, Any], prompt: str, arm: str) -> dict[str, Any]:
    """Validate one local no-auth request serialization before any outcome call."""

    tools = _request_tools(request)
    allowed_helpers = {
        ("functions", "list_mcp_resources"),
        ("functions", "list_mcp_resource_templates"),
        ("functions", "read_mcp_resource"),
    }
    if any(namespace not in {"mcp__evaluation", "functions"} for namespace, _ in tools):
        raise ValueError("evaluation request exposes an unexpected tool namespace")
    names = {name for namespace, name in tools if namespace == "mcp__evaluation"}
    if arm == "A" and "loci_explore" in names:
        raise ValueError("A unexpectedly exposes loci_explore")
    if arm == "B" and "loci_explore" not in names:
        raise ValueError("B is missing loci_explore")
    if {item for item in tools if item[0] == "functions"} != allowed_helpers:
        raise ValueError("unexpected host helper surface")
    for item in request.get("input", []):
        for part in item.get("content", []):
            text = part.get("text", "")
            if any(marker in text for marker in (
                "# AGENTS.md instructions", "## Brain Context", "Anvil Continuity Frame",
                "<skills_instructions>", "LOCI_ADAPTER_READY",
            )):
                raise ValueError("ambient instructions reached the evaluation prompt")
    if request.get("input", [])[-1].get("content") != [{"type": "input_text", "text": prompt}]:
        raise ValueError("effective task prompt differs from frozen prompt construction")
    if request.get("model") != MODEL or request.get("reasoning", {}).get("effort") != REASONING_EFFORT:
        raise ValueError("effective model/reasoning differs from W4 controls")
    observed_tier = request.get("service_tier", SERVICE_TIER)
    if observed_tier != SERVICE_TIER:
        raise ValueError("effective service tier differs from W4 controls")
    visible = {key: request[key] for key in ("model", "input", "reasoning", "text", "service_tier") if key in request}
    return {
        "request": visible,
        "request_sha256": sha(json.dumps(visible, ensure_ascii=False, separators=(",", ":")).encode()),
        "tools": tools,
        "canonical_tool_schemas_sha256": sha(json.dumps(
            {"tools": [item["tools"] for item in request["input"] if item.get("type") == "additional_tools"]},
            ensure_ascii=False, separators=(",", ":"),
        ).encode()),
        "model": MODEL, "reasoning_effort": REASONING_EFFORT,
        "service_tier": observed_tier,
        "inspection": "actual Codex request, local no-auth Responses transport; no model called",
    }


def inspect_request(repo: Path, config: dict[str, Any], prompt: str, runtime_home: Path, *, arm: str) -> dict[str, Any]:
    """Capture the effective local Responses request without calling a provider."""

    captured: list[dict[str, Any]] = []

    class Capture(http.server.BaseHTTPRequestHandler):
        def do_POST(self) -> None:  # noqa: N802
            captured.append(json.loads(self.rfile.read(int(self.headers["content-length"]))))
            self.send_response(400)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"error":{"message":"offline request inspection complete","type":"invalid_request_error"}}')

        def log_message(self, *_args: object) -> None:
            pass

    server = http.server.HTTPServer(("127.0.0.1", 0), Capture)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    inspection = {**config,
        "model_provider": "inspection",
        "model_providers.inspection.name": "Offline multilingual request inspection",
        "model_providers.inspection.base_url": f"http://127.0.0.1:{server.server_port}/v1",
        "model_providers.inspection.wire_api": "responses",
        "model_providers.inspection.requires_openai_auth": False,
        "model_providers.inspection.request_max_retries": 0,
        "model_providers.inspection.stream_max_retries": 0,
    }
    try:
        result = subprocess.run(launch_args(repo, inspection, prompt), capture_output=True, text=True,
                                env=child_environment(runtime_home, False), timeout=25)
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
    if len(captured) != 1:
        raise ValueError("Codex did not emit exactly one offline inspection request: " + result.stderr[-2000:])
    return audit_request(captured[0], prompt, arm)


def _validate_freeze(corpus: dict[str, Any], controls: dict[str, Any], freeze_path: Path) -> dict[str, Any]:
    from benchmarks.multilingual_context_freeze import validate_freeze

    validated = validate_freeze(freeze_path, require_published=True)
    path = Path(freeze_path).resolve()
    value = json.loads(path.read_text(encoding="utf-8"))
    if value.get("version") != COMPARISON or value.get("plan") != schedule(corpus):
        raise ValueError("freeze differs from the fixed multilingual plan")
    if value.get("model") != MODEL or value.get("reasoning_effort") != REASONING_EFFORT:
        raise ValueError("freeze model controls differ")
    if value.get("service_tier") != SERVICE_TIER or value.get("request_max_retries") != REQUEST_MAX_RETRIES or value.get("stream_max_retries") != STREAM_MAX_RETRIES:
        raise ValueError("freeze transport controls differ")
    if value.get("corpus_sha256") != sha((Path(corpus["_root"]) / "corpus.json").read_bytes()):
        raise ValueError("freeze corpus identity differs")
    if value.get("controls_sha256") != sha((Path(corpus["_root"]) / "comparison-controls.json").read_bytes()):
        raise ValueError("freeze controls identity differs")
    expected_guide = sha(controls["agent"]["workflow_guide"].encode())
    if value.get("workflow_guide_sha256") != expected_guide:
        raise ValueError("freeze workflow guide differs")
    relative = path.relative_to(ROOT).as_posix()
    if validated["freeze_json_sha256"] != sha(path.read_bytes()):
        raise ValueError("freeze hash changed during validation")
    return validated


def run_attempt(corpus: dict[str, Any], controls: dict[str, Any], plan: dict[str, Any], output: Path,
                catalog: Path, freeze: dict[str, Any]) -> dict[str, Any]:
    """Execute exactly one immutable scheduled slot via the proven host lifecycle."""

    from benchmarks import typescript_context_compare as prior
    from benchmarks import multilingual_context_observed as observed
    from loci import service

    effective_controls = controls
    if plan["arm"] == "B":
        # `_run_attempt` deliberately knows only common_prompt + case.prompt.
        # Bind the frozen workflow guide here, before its request audit and
        # provenance hash, without exposing any corpus facts to the task agent.
        effective_controls = {**controls, "agent": {**controls["agent"],
            "common_prompt": controls["agent"]["common_prompt"] + controls["agent"]["workflow_guide"]}}
    previous_modules, previous_provenance, previous_initial = prior.ARM_MODULES, prior._source_provenance, prior._initial_trace
    prior.ARM_MODULES = {"A": TOOLS_MODULE, "B": TOOLS_MODULE}
    prior._source_provenance = lambda *_: {
        "freeze_commit": freeze.get("freeze_commit"),
        "freeze_json_sha256": freeze["freeze_json_sha256"],
        "source_scope": "W4 evaluator snapshot; A exact retrieval/graph, B adds current loci_explore plus frozen guide",
    }
    neutral_session = "session-" + str(uuid.uuid4())

    def neutral_save(path: Path, value: Any) -> None:
        """Keep evaluator case identity out of the task-visible MCP attempt id."""
        if Path(path).name == "run.json" and isinstance(value, dict) and "session_id" in value:
            value["session_id"] = neutral_session
        save(path, value)

    def multilingual_initial_trace(current_corpus: dict[str, Any], run: dict[str, Any]) -> dict[str, Any]:
        trace = observed.MultilingualObservedTrace(
            current_corpus, run["case_id"], run["session_id"], run["arm"], run["repetition"],
        )
        return {
            "schema_version": 3, "protocol": observed.PROTOCOL, "identity": trace.identity,
            "events": [], "failures": [], "attempts": 0, "deliveries": [],
        }

    prior._initial_trace = multilingual_initial_trace
    try:
        result = prior._run_attempt(
            corpus=corpus, controls=effective_controls, plan=plan, output=Path(output), catalog=Path(catalog),
            expected_schema_hash=freeze["canonical_tool_schemas_sha256"][plan["arm"]], freeze=freeze,
            inspect_request=lambda repo, config, prompt, runtime: inspect_request(repo, config, prompt, runtime, arm=plan["arm"]),
            settings=settings, launch_args=launch_args, child_environment=child_environment, execute=execute,
            save=neutral_save, materialize_snapshot=materialize_snapshot, isolated_store=_isolated_store,
            service=service, measure=observed.measure,
        )
        # The legacy lifecycle predates the multilingual scorer's explicit
        # full-pass field.  A retained runner/setup failure cannot qualify even
        # if a partial scorer result looked complete before that failure was
        # appended to the artifact.
        if result.get("runner_failures"):
            measurement = result.get("measurement")
            if isinstance(measurement, dict):
                measurement["measurement_complete"] = False
                measurement["task_correct"] = False
                measurement["full_pass"] = False
            save(Path(output) / plan["attempt_id"] / "result.json", result)
        return result
    finally:
        prior.ARM_MODULES, prior._source_provenance, prior._initial_trace = previous_modules, previous_provenance, previous_initial


def run_batch(freeze_path: Path, output: Path, catalog: Path, *, resume: bool = False) -> dict[str, Any]:
    """Run only the serial untouched suffix; retain every failed or partial slot."""

    corpus, controls = load_inputs(INPUTS_ROOT)
    freeze = _validate_freeze(corpus, controls, freeze_path)
    plan = schedule(corpus)
    output, catalog = Path(output).resolve(), Path(catalog).resolve()
    if not catalog.is_file():
        raise ValueError("explicit retained model catalog is required")
    if sha(catalog.read_bytes()) != freeze.get("model_catalog_sha256"):
        raise ValueError("provided model catalog differs from the published freeze")
    if not resume:
        output.mkdir(parents=True, exist_ok=False)
        save(output / "manifest.json", {
            "schema_version": 1, "comparison": COMPARISON, "planned_runs": EXPECTED_RUNS,
            "plan": plan, "freeze": freeze, "catalog_sha256": sha(catalog.read_bytes()),
            "started_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        })
        (output / "model-catalog.json").write_bytes(catalog.read_bytes())
    elif not (output / "manifest.json").is_file() or (output / "model-catalog.json").read_bytes() != catalog.read_bytes():
        raise ValueError("resume requires unchanged retained manifest and catalog")
    expected = [item["attempt_id"] for item in plan]
    unexpected = sorted(path.name for path in output.iterdir()
                        if path.is_dir() and path.name not in set(expected))
    if unexpected:
        raise ValueError("output contains unscheduled attempt directories: " + ", ".join(unexpected))
    existing = [item for item in expected if (output / item).exists()]
    manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
    if (manifest.get("freeze") != freeze or manifest.get("plan") != plan
            or manifest.get("catalog_sha256") != sha(catalog.read_bytes())
            or manifest.get("planned_runs") != EXPECTED_RUNS):
        raise ValueError("resume manifest differs from the published batch identity")
    if existing != expected[:len(existing)] or any(not (output / item / "result.json").is_file() for item in existing):
        raise ValueError("only a fully recorded serial prefix may be resumed; no attempt is retried or overwritten")
    results = [json.loads((output / item / "result.json").read_text()) for item in existing]
    for item in plan[len(existing):]:
        result = run_attempt(corpus, controls, item, output, output / "model-catalog.json", freeze)
        results.append(result)
    save(output / "completion.json", {"recorded_runs": len(results), "complete": len(results) == EXPECTED_RUNS})
    return {"recorded_runs": len(results), "complete": len(results) == EXPECTED_RUNS}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("prepare", "run"), required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--catalog", type=Path)
    parser.add_argument("--freeze", type=Path, default=COMPARISON_ROOT / "freeze.json")
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()
    if args.mode == "prepare":
        args.output.mkdir(parents=True, exist_ok=False)
        cli_version = command(["codex", "--version"])
        login = subprocess.run(["codex", "login", "status"], capture_output=True, text=True, check=True)
        authentication = (login.stdout + login.stderr).strip()
        if cli_version != "codex-cli 0.154.0" or authentication != "Logged in using ChatGPT":
            raise ValueError("matched W4 host route is unavailable")
        catalog = prepare_catalog(args.output, MODEL)
        binary = Path(shutil.which("codex") or "").resolve()
        if not binary.is_file():
            raise ValueError("Codex CLI binary is unavailable")
        save(args.output / "host-preflight.json", {
            "schema_version": 1, "cli_version": cli_version, "authentication": authentication,
            "model": MODEL, "reasoning_effort": REASONING_EFFORT, "service_tier": SERVICE_TIER,
            "request_max_retries": REQUEST_MAX_RETRIES, "stream_max_retries": STREAM_MAX_RETRIES,
            "cli_binary_sha256": sha(binary.read_bytes()),
            "builtin_retry_override": {
                "effective": "not overridden; reserved built-in provider settings are not configurable by this CLI",
                "preparation_failure": "../preparation-failures/builtin-retry-override/preflight-failure.json",
            },
            "catalog_sha256": sha(catalog.read_bytes()), "provider_calls": 0,
            "meaning": "Local CLI/catalog/login availability only. Scheduled outcomes and selective replacements remain zero; ordinary built-in host transport recovery is not configured or inferred. No provider entitlement or outcome claim.",
        })
        print(json.dumps({"catalog": str(catalog), "model": MODEL, "provider_calls": 0}))
        return
    if args.catalog is None:
        parser.error("--catalog required for run")
    print(json.dumps(run_batch(args.freeze, args.output, args.catalog, resume=args.resume)))


if __name__ == "__main__":
    main()
