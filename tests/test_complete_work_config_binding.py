"""R1 binds effective native settings while its CLI pins model and effort."""
import copy
import hashlib
import json
from pathlib import Path
import subprocess

import pytest

from benchmarks.complete_work import r0


BASE = b'''model = "gpt-6-sol"
model_reasoning_effort = "high"
service_tier = "priority"
model_context_window = 1000000
approval_policy = "on-request"
unrecognized_setting = "private-baseline-value"

[permissions.existing]
sandbox_mode = "workspace-write"

[mcp_servers.existing]
command = "existing-command"
env = { TOKEN = "private-token-value" }

[features]
enabled = true

[profiles.existing]
model = "profile-model"
model_reasoning_effort = "medium"
'''


def _bound(tmp_path: Path) -> tuple[Path, dict]:
    path = tmp_path / "config.toml"
    path.write_bytes(BASE)
    return path, r0.native_config_binding(BASE)


def _check(path: Path, binding: dict) -> dict:
    return r0.check_native_config(path, hashlib.sha256(BASE).hexdigest(), binding)


def test_binding_contains_hashes_without_config_values_or_side_effects(tmp_path, monkeypatch):
    path = tmp_path / "config.toml"
    path.write_bytes(BASE)

    def forbidden(*args, **kwargs):
        pytest.fail("config validation must neither write files nor launch a process")

    monkeypatch.setattr(Path, "write_bytes", forbidden)
    monkeypatch.setattr(Path, "write_text", forbidden)
    monkeypatch.setattr(subprocess, "run", forbidden)
    monkeypatch.setattr(subprocess, "Popen", forbidden)
    binding = r0.native_config_binding(BASE)
    result = _check(path, binding)
    assert binding["schema"] == "r1-cli-model-defaults-v1"
    assert binding["raw_sha256"] == hashlib.sha256(BASE).hexdigest()
    assert set(binding["field_sha256"]) == {
        "model", "model_reasoning_effort", "service_tier", "model_context_window",
        "approval_policy", "unrecognized_setting", "permissions", "mcp_servers",
        "features", "profiles",
    }
    for value in [binding["effective_sha256"], *binding["field_sha256"].values()]:
        assert len(value) == 64 and int(value, 16) >= 0
    serialized = json.dumps({"binding": binding, "result": result})
    assert "private-baseline-value" not in serialized
    assert "private-token-value" not in serialized
    assert "existing-command" not in serialized
    assert path.read_bytes() == BASE


@pytest.mark.parametrize("before,after,changed", [
    (b'model = "gpt-6-sol"', b'model = "gpt-6.1-sol"', ["model"]),
    (b'model_reasoning_effort = "high"', b'model_reasoning_effort = "max"',
     ["model_reasoning_effort"]),
    (b'model = "gpt-6-sol"\nmodel_reasoning_effort = "high"\n', b"",
     ["model", "model_reasoning_effort"]),
])
def test_only_cli_overridden_root_defaults_can_change(tmp_path, before, after, changed):
    path, binding = _bound(tmp_path)
    path.write_bytes(BASE.replace(before, after))
    current = r0.native_config_binding(path.read_bytes())
    result = _check(path, binding)
    assert result["raw_sha256"] == hashlib.sha256(path.read_bytes()).hexdigest()
    assert result["raw_sha256"] != binding["raw_sha256"]
    assert current["effective_sha256"] == result["effective_sha256"] == binding["effective_sha256"]
    assert sorted(result["overridden_default_changes"]) == changed


@pytest.mark.parametrize("key,before,after", [
    ("approval_policy", b'approval_policy = "on-request"', b'approval_policy = "never"'),
    ("permissions", b'sandbox_mode = "workspace-write"', b'sandbox_mode = "danger-full-access"'),
    ("service_tier", b'service_tier = "priority"', b'service_tier = "flex"'),
    ("model_context_window", b"model_context_window = 1000000", b"model_context_window = 2000000"),
    ("mcp_servers", b'command = "existing-command"', b'command = "private-changed-command"'),
    ("features", b"enabled = true", b"enabled = false"),
    ("profiles", b'model = "profile-model"', b'model = "private-changed-profile"'),
    ("unrecognized_setting", b'"private-baseline-value"', b'"private-changed-setting"'),
])
def test_every_other_semantic_field_remains_bound(tmp_path, key, before, after):
    path, binding = _bound(tmp_path)
    path.write_bytes(BASE.replace(before, after).replace(b'"gpt-6-sol"', b'"gpt-6.1-sol"'))
    with pytest.raises(ValueError) as rejected:
        _check(path, binding)
    assert key in str(rejected.value)
    assert "private-" not in str(rejected.value)
    assert "danger-full-access" not in str(rejected.value)


def test_formatting_and_comment_changes_preserve_effective_binding(tmp_path):
    path, binding = _bound(tmp_path)
    path.write_bytes(b"# same native settings\n" + BASE.replace(b" = ", b"="))
    result = _check(path, binding)
    assert result["raw_sha256"] != binding["raw_sha256"]
    assert result["effective_sha256"] == binding["effective_sha256"]
    assert result["overridden_default_changes"] == []


@pytest.mark.parametrize("change", [False, True])
def test_legacy_config_binding_retains_strict_raw_comparison(tmp_path, change):
    path = tmp_path / "config.toml"
    path.write_bytes(BASE)
    if change:
        path.write_bytes(BASE.replace(b'"gpt-6-sol"', b'"gpt-6.1-sol"'))
        with pytest.raises(ValueError):
            r0.check_native_config(path, hashlib.sha256(BASE).hexdigest())
    else:
        result = r0.check_native_config(path, hashlib.sha256(BASE).hexdigest())
        assert result["raw_sha256"] == hashlib.sha256(BASE).hexdigest()
        assert result["effective_sha256"] is None
        assert result["overridden_default_changes"] == []


def test_malformed_toml_fails_at_binding_and_later_validation(tmp_path):
    path, binding = _bound(tmp_path)
    malformed = b'model = "private-malformed-value\n'
    with pytest.raises(ValueError):
        r0.native_config_binding(malformed)
    path.write_bytes(malformed)
    with pytest.raises(ValueError) as rejected:
        _check(path, binding)
    assert "private-malformed-value" not in str(rejected.value)


@pytest.mark.parametrize("field,value", [
    ("schema", "unsupported-config-policy"),
    ("raw_sha256", "f" * 64),
    ("effective_sha256", "invalid-digest"),
    ("field_sha256", {"model": "invalid-digest"}),
])
def test_invalid_binding_or_wrong_baseline_fails_closed(tmp_path, field, value):
    path, binding = _bound(tmp_path)
    invalid = copy.deepcopy(binding)
    invalid[field] = value
    with pytest.raises(ValueError):
        _check(path, invalid)


@pytest.mark.parametrize("violation", [None, "observed_model", "permissions"])
def test_qualification_uses_binding_and_still_checks_actual_native_context(tmp_path, monkeypatch, violation):
    path, binding = _bound(tmp_path)
    source = tmp_path / "source"
    source.mkdir()
    (source / "value.txt").write_text("control\n")
    conditions = {"model": "gpt-6.1-terra", "effort": "max",
                  "native_config_binding": binding,
                  "native_protection": {field: None for field in r0.PROTECTION_FIELDS}}
    manifest = r0.prepare(source, tmp_path / "run", run_id="control", arm="native",
                          native_config=path, conditions=conditions)
    changed = BASE.replace(b'"gpt-6-sol"', b'"gpt-6.1-sol"')
    if violation == "permissions":
        changed = changed.replace(b'sandbox_mode = "workspace-write"',
                                  b'sandbox_mode = "danger-full-access"')
    path.write_bytes(changed)
    context = {**conditions["native_protection"], "model": conditions["model"], "effort": "max"}
    if violation == "observed_model":
        context["model"] = "gpt-6.1-sol"
    accounting = {"usage_status": "known", "native_errors": [], "turn_contexts": [context],
                  "stages": [{"items": [{"type": "commandExecution", "cwd": manifest["workspace"]}]}]}
    monkeypatch.setattr(r0, "summarize_native", lambda *args: accounting)
    trace = tmp_path / "trace.jsonl"
    trace.write_text('{"fixture":true}\n')
    result = r0.qualify(Path(manifest["observer"]) / "run.json", trace, thread_id="control")
    assert result["status"] == ("qualified_observations" if violation is None else "unqualified")
    assert result["native_config_sha256"] == hashlib.sha256(BASE).hexdigest()
    if violation != "permissions":
        assert result["config_validation"]["raw_sha256"] == hashlib.sha256(changed).hexdigest()
        assert result["config_validation"]["effective_sha256"] == binding["effective_sha256"]
        assert result["config_validation"]["overridden_default_changes"] == ["model"]
