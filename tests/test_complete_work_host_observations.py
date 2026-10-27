"""Explicit host observations tolerate personal defaults without relaxing trial pins."""
import json
from pathlib import Path

import pytest

from benchmarks.complete_work import r0, r1
from benchmarks.complete_work.evaluate import write_json
from tests.test_complete_work_r1 import _freeze, _write_amendment


CONFIG = '''model = "existing-model"
model_reasoning_effort = "high"
approval_policy = "on-request"
service_tier = "priority"
model_context_window = 1000000
unknown_setting = "private-original-value"

[agents]
default_subagent_model = "existing-worker"
max_threads = 4

[mcp_servers.existing]
command = "existing-command"

[features]
existing = true
'''


def _host_freeze(tmp_path):
    """Create a real freeze plus a policy amendment; all host files are temporary."""
    path = _freeze(tmp_path)
    frozen = json.loads(path.read_text())
    config = Path(frozen["native_config"])
    config.write_text(CONFIG)
    binding = r0.native_config_binding(config.read_bytes())
    frozen.update(native_config_binding=binding, native_config_sha256=binding["raw_sha256"])
    startup = {"global": config.parent / "AGENTS.md",
               "hook": tmp_path / "hooks/session-start.py",
               "project": tmp_path / "project/AGENTS.md",
               "skill": tmp_path / "skills/loci/SKILL.md"}
    for target in startup.values():
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("original startup content\n")
    frozen["host"]["startup_context_files"] = {str(target): r0.digest(target) for target in startup.values()}
    source = str(Path(r0.__file__).resolve())
    frozen["host"]["orchestration_files"][source] = "1" * 64
    frozen.pop("freeze_sha256")
    frozen["freeze_sha256"] = r1.identity(frozen)
    write_json(path, frozen)
    amendment = tmp_path / "host-observation-amendment.json"
    _write_amendment(amendment, {
        "schema_version": 1, "kind": "r1-instrumentation-amendment",
        "freeze_sha256": frozen["freeze_sha256"],
        "host_observation_policy": r0.HOST_OBSERVATION_POLICY,
        "changes": {source: {"before_sha256": "1" * 64,
                             "after_sha256": r0.digest(Path(source))}},
    })
    return path, amendment, config, startup


def test_personal_defaults_and_agents_are_observed_while_contract_stays_fixed(tmp_path):
    path, amendment, config, _ = _host_freeze(tmp_path)
    original = r1.read_freeze(path, runtime=False)
    before = path.read_bytes()
    config.write_text(CONFIG.replace('"existing-model"', '"new-model"')
                      .replace('model_reasoning_effort = "high"', 'model_reasoning_effort = "max"')
                      .replace('"existing-worker"', '"new-worker"'))
    frozen = r1.read_freeze(path, amendment=amendment)
    receipt = frozen["host_observations"]["config_validation"]
    assert receipt["raw_sha256"] == r0.digest(config)
    assert receipt["raw_sha256"] != original["native_config_sha256"]
    assert receipt["effective_sha256"] != original["native_config_binding"]["effective_sha256"]
    assert receipt["contract_sha256"] == r0.native_config_contract(original["native_config_binding"])
    assert receipt["observed_only_changes"] == ["agents"]
    assert receipt["overridden_default_changes"] == ["model", "model_reasoning_effort"]
    assert frozen["host_observations"]["policy"] == r0.HOST_OBSERVATION_POLICY
    assert r1._run_conditions(frozen) == r1._run_conditions(original)
    assert r1.command(frozen, "native", tmp_path / "workspace", tmp_path / "observer") == r1.command(
        original, "native", tmp_path / "workspace", tmp_path / "observer")
    assert path.read_bytes() == before


@pytest.mark.parametrize("before,after,key", [
    ('approval_policy = "on-request"', 'approval_policy = "never"', "approval_policy"),
    ('service_tier = "priority"', 'service_tier = "flex"', "service_tier"),
    ("model_context_window = 1000000", "model_context_window = 2000000", "model_context_window"),
    ('command = "existing-command"', 'command = "private-new-command"', "mcp_servers"),
    ("existing = true", "existing = false", "features"),
    ('unknown_setting = "private-original-value"', 'unknown_setting = "private-new-value"', "unknown_setting"),
])
def test_host_policy_preserves_every_other_config_contract(tmp_path, before, after, key):
    path, amendment, config, _ = _host_freeze(tmp_path)
    baseline = json.loads(path.read_text())["native_config_binding"]
    config.write_text(CONFIG.replace(before, after).replace('"existing-worker"', '"new-worker"'))
    assert r0.native_config_contract(r0.native_config_binding(config.read_bytes())) != r0.native_config_contract(baseline)
    with pytest.raises(ValueError) as rejected:
        r1.read_freeze(path, amendment=amendment)
    assert key in str(rejected.value)
    assert "private-" not in str(rejected.value)


@pytest.mark.parametrize("explicit_false", [False, True])
def test_agents_drift_still_rejected_without_host_observation_opt_in(tmp_path, explicit_false):
    _, _, config, _ = _host_freeze(tmp_path)
    baseline = r0.native_config_binding(config.read_bytes())
    config.write_text(CONFIG.replace('"existing-worker"', '"new-worker"'))
    kwargs = {"host_observations": False} if explicit_false else {}
    with pytest.raises(ValueError, match="agents"):
        r0.check_native_config(config, baseline["raw_sha256"], baseline, **kwargs)


def test_legacy_raw_pin_is_not_relaxed_by_host_observation_flag(tmp_path):
    _, _, config, _ = _host_freeze(tmp_path)
    baseline = r0.digest(config)
    config.write_text(CONFIG.replace('"existing-worker"', '"new-worker"'))
    with pytest.raises(ValueError, match="configuration changed"):
        r0.check_native_config(config, baseline, host_observations=True)


@pytest.mark.parametrize("kind", ["global", "hook", "project", "skill"])
def test_only_global_agents_startup_file_is_observed(tmp_path, kind):
    path, amendment, _, startup = _host_freeze(tmp_path)
    old_hash = r0.digest(startup[kind])
    startup[kind].write_text("changed startup content\n")
    if kind != "global":
        with pytest.raises(ValueError, match="shared startup context"):
            r1.read_freeze(path, amendment=amendment)
        return
    frozen = r1.read_freeze(path, amendment=amendment)
    assert frozen["host_observations"]["startup_instructions"] == [{
        "path": str(startup["global"]), "frozen_sha256": old_hash,
        "observed_sha256": r0.digest(startup["global"]), "changed": True,
    }]


@pytest.mark.parametrize("policy", [None, "r1-personal-host-observations-v2", ""])
def test_r0_pin_amendment_requires_exact_host_policy(tmp_path, policy):
    path, amendment, _, _ = _host_freeze(tmp_path)
    payload = json.loads(amendment.read_text())
    if policy is None:
        payload.pop("host_observation_policy")
    else:
        payload["host_observation_policy"] = policy
    _write_amendment(amendment, payload)
    with pytest.raises(ValueError, match="host observation policy|disallowed paths"):
        r1.read_freeze(path, amendment=amendment)


@pytest.mark.parametrize("field", ["before_sha256", "after_sha256"])
def test_host_policy_still_checks_amendment_before_and_after_pins(tmp_path, field):
    path, amendment, _, _ = _host_freeze(tmp_path)
    payload = json.loads(amendment.read_text())
    change = next(iter(payload["changes"].values()))
    change[field] = "2" * 64
    _write_amendment(amendment, payload)
    with pytest.raises(ValueError, match="original pin|orchestration changed"):
        r1.read_freeze(path, amendment=amendment)


@pytest.mark.parametrize("wrong_model", [False, True])
def test_prepare_and_qualification_record_each_observation_and_check_actual_context(tmp_path, monkeypatch, wrong_model):
    path, amendment, config, _ = _host_freeze(tmp_path)
    config.write_text(CONFIG.replace('"existing-worker"', '"first-worker"'))
    frozen = r1.read_freeze(path, amendment=amendment)
    conditions = r1._run_conditions(frozen)
    source = Path(frozen["tasks"][0]["source"])
    manifest = r0.prepare(source, tmp_path / "run", run_id="test", arm="native",
                          native_config=config, conditions=conditions, host_observations=True)
    prepared_raw = r0.digest(config)
    assert manifest["native_config_sha256"] == prepared_raw
    assert manifest["config_validation"]["observed_only_changes"] == ["agents"]
    config.write_text(CONFIG.replace('"existing-worker"', '"second-worker"'))
    context = {**conditions["native_protection"], "model": conditions["model"], "effort": conditions["effort"]}
    if wrong_model:
        context["model"] = "unexpected-model"
    calls = []

    def summarize(trace, thread, **kwargs):
        calls.append(kwargs)
        return {"usage_status": "known", "native_errors": [], "turn_contexts": [context],
                "stages": [{"items": [{"type": "commandExecution", "cwd": manifest["workspace"]}]}]}

    monkeypatch.setattr(r0, "summarize_native", summarize)
    trace = tmp_path / "trace.jsonl"
    trace.write_text('{"fixture":true}\n')
    result = r0.qualify(Path(manifest["observer"]) / "run.json", trace,
                        thread_id="test", host_observations=True)
    assert calls == [{"allow_instruction_updates": True}]
    assert result["status"] == ("unqualified" if wrong_model else "qualified_observations")
    assert result["native_config_sha256"] == prepared_raw
    assert result["config_validation"]["raw_sha256"] == r0.digest(config) != prepared_raw
    assert result["config_validation"]["effective_sha256"] != manifest["config_validation"]["effective_sha256"]
    assert result["config_validation"]["contract_sha256"] == manifest["config_validation"]["contract_sha256"]
    assert result["config_validation"]["observed_only_changes"] == ["agents"]
