"""R0 separation/equality checks; native protection settings are never replaced."""
import copy
import json
import subprocess
import sys
from pathlib import Path

import pytest

from benchmarks.complete_work import controller, r0


def test_r0_has_no_dependency_on_historical_permission_profiles() -> None:
    subprocess.run([sys.executable, "-c",
                    "import sys; import benchmarks.complete_work.r0; "
                    "assert 'benchmarks.complete_work.isolation' not in sys.modules; "
                    "assert 'benchmarks.complete_work.controller' not in sys.modules"], check=True)


def _conditions() -> dict:
    return {"model": "test-model", "effort": "high", "prompt_hashes": ["fixed"],
            "native_protection": {field: {"existing": True} for field in r0.PROTECTION_FIELDS}}


def test_prepare_makes_independent_snapshots_and_separate_results_without_launch(tmp_path: Path, monkeypatch) -> None:
    def forbidden(*args, **kwargs):
        pytest.fail("R0 must not create an App Server or custom permission profile")

    monkeypatch.setattr(controller, "AppServer", forbidden)
    monkeypatch.setattr(controller, "build_overrides", forbidden)
    source = tmp_path / "source"
    source.mkdir()
    (source / "file.py").write_text("initial\n")
    config = tmp_path / "config.toml"
    config.write_text('default_permissions = "existing-native"\n')
    original = config.read_bytes()
    manifests = [r0.prepare(source, tmp_path / arm, run_id=arm, arm=arm,
                            native_config=config, conditions=_conditions()) for arm in ("native", "loci")]
    assert manifests[0]["source_identity"] == manifests[1]["source_identity"]
    for manifest in manifests:
        assert manifest["permission_overrides"] == {}
        assert r0.disjoint(Path(manifest["workspace"]), Path(manifest["observer"]))
    (Path(manifests[0]["workspace"]) / "file.py").write_text("changed\n")
    assert (Path(manifests[1]["workspace"]) / "file.py").read_text() == "initial\n"
    assert (source / "file.py").read_text() == "initial\n"
    assert config.read_bytes() == original
    with pytest.raises(FileExistsError):
        r0.prepare(source, tmp_path / "native", run_id="again", arm="native", native_config=config, conditions={})
    with pytest.raises(ValueError, match="disjoint"):
        r0.prepare(source, source / "inside", run_id="bad", arm="native", native_config=config, conditions={})


def _pair(tmp_path: Path) -> list[dict]:
    return [{"arm": arm, "run_id": arm, "thread_id": arm, "conditions": _conditions(),
             "native_config_sha256": "unchanged", "source_before": "same-source",
             "workspace": str(tmp_path / arm / "workspace"), "observer": str(tmp_path / arm / "observer"),
             "status": "qualified_observations"} for arm in ("native", "loci")]


@pytest.mark.parametrize("violation", ["permissions", "source", "config", "session", "storage", "usage"])
def test_pair_rejects_unequal_access_inputs_shared_state_or_missing_telemetry(tmp_path: Path, violation: str) -> None:
    left, right = _pair(tmp_path)
    assert r0.check_pair(left, right)["status"] == "matched"
    if violation == "permissions":
        right["conditions"]["native_protection"]["permission_profile"] = {"unequal": True}
    elif violation == "source":
        right["source_before"] = "different"
    elif violation == "config":
        right["native_config_sha256"] = "different"
    elif violation == "session":
        right["thread_id"] = left["thread_id"]
    elif violation == "storage":
        right["observer"] = left["workspace"]
    else:
        right["status"] = "unqualified"
    assert r0.check_pair(left, right)["status"] == "invalid"


@pytest.mark.parametrize("violation", [None, "permissions", "config", "loci_call", "missing_usage", "corrupt_trace", "wrong_workspace", "delegation"])
def test_qualification_preserves_native_settings_and_fails_closed(tmp_path: Path, monkeypatch, violation) -> None:
    source = tmp_path / "source"
    source.mkdir()
    (source / "value.txt").write_text("control\n")
    native_config = tmp_path / "config.toml"
    native_config.write_text('default_permissions = "native"\n')
    conditions = _conditions()
    manifest = r0.prepare(source, tmp_path / "run", run_id="control", arm="native",
                          native_config=native_config, conditions=conditions)
    context = {**copy.deepcopy(conditions["native_protection"]), "model": "test-model", "effort": "high"}
    accounting = {"usage_status": "known", "native_errors": [], "turn_contexts": [context],
                  "stages": [{"items": [{"type": "commandExecution", "cwd": Path(manifest["workspace"]).as_uri()}]}]}
    if violation == "permissions":
        context["permission_profile"] = {"replacement": True}
    elif violation == "config":
        native_config.write_text('default_permissions = "changed"\n')
    elif violation == "loci_call":
        accounting["stages"][0]["items"].append({"server": "loci"})
    elif violation == "missing_usage":
        accounting["usage_status"] = "unknown"
    elif violation == "wrong_workspace":
        accounting["stages"][0]["items"].append({"type": "commandExecution", "cwd": str(tmp_path)})
    elif violation == "delegation":
        accounting["stages"][0]["items"].append({"type": "collabAgentToolCall"})
    def reduce(path, thread):
        if violation == "corrupt_trace":
            raise ValueError("corrupt record")
        return accounting

    monkeypatch.setattr(r0, "summarize_native", reduce)
    trace = tmp_path / "trace.jsonl"
    trace.write_text('{"fixture":true}\n')
    config = Path(manifest["observer"]) / "run.json"
    result = r0.qualify(config, trace, thread_id="control")
    assert result["status"] == ("qualified_observations" if violation is None else "unqualified")
    assert (Path(manifest["observer"]) / "qualification/native-rollout.jsonl").read_bytes() == trace.read_bytes()
    assert result["measured"] is False
