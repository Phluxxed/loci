from pathlib import Path
import json

import pytest

from benchmarks.complete_work.controller import isolation_probe
from benchmarks.complete_work.isolation import READ_PROFILE, WRITE_PROFILE, build_overrides, verify_profile


def test_overrides_are_local_restrictive_and_keep_only_controlled_mcp(tmp_path: Path) -> None:
    workspace = tmp_path / "repo"
    workspace.mkdir()
    dependency = tmp_path / "dependency"
    dependency.mkdir()
    config = tmp_path / "config.toml"
    original = '[mcp_servers.other]\ncommand="example"\n[mcp_servers.loci]\ncommand="original"\n'
    config.write_text(original)
    overrides = build_overrides(workspace, [dependency], "/python", ["control"], {}, user_config=config)
    assert config.read_text() == original
    assert overrides["mcp_servers.other.enabled"] is False
    assert "mcp_servers.loci.enabled" not in overrides
    assert overrides["mcp_servers.loci"]["command"] == "/python"
    for profile, access in ((READ_PROFILE, "read"), (WRITE_PROFILE, "write")):
        files = overrides[f"permissions.{profile}"]["filesystem"]
        assert files[":root"] == "deny"
        assert files[":workspace_roots"]["."] == access
        assert files[":workspace_roots"][".complete-work-isolation.json"] == "read"
        assert files[str(dependency)] == "read"
    with pytest.raises(ValueError, match="outside"):
        build_overrides(workspace, [workspace], "x", [], {}, user_config=config)
    with pytest.raises(ValueError, match="profile"):
        verify_profile({}, READ_PROFILE, workspace)


def test_unavailable_native_sandbox_stops_probe_without_write_profile(tmp_path: Path) -> None:
    workspace = tmp_path / "repo"
    workspace.mkdir()
    (workspace / ".complete-work-isolation.json").write_text("{}")

    class Unavailable:
        calls = []

        def call(self, method, params, **kwargs):
            self.calls.append((method, params))
            return {"exitCode": 71, "stdout": "", "stderr": "sandbox_apply: Operation not permitted"}

    client = Unavailable()
    report = isolation_probe(client, workspace, tmp_path / "hidden")
    assert report["status"] == "unavailable"
    assert [x[1]["permissionProfile"] for x in client.calls] == [READ_PROFILE]


@pytest.mark.parametrize("violation", [None, "hidden_read", "orientation_write", "protected_write", "missing_source_access", "missing_write_access"])
def test_canaries_reject_excess_or_missing_access(tmp_path: Path, violation: str | None) -> None:
    workspace = tmp_path / "repo"
    workspace.mkdir()
    (workspace / ".complete-work-isolation.json").write_text("{}")

    class BoundaryClient:
        def call(self, method, params, **kwargs):
            assert method == "command/exec"
            write = params["permissionProfile"] == WRITE_PROFILE
            observed = {"visible": "visible-canary", "source_read": "{}", "hidden": "denied",
                        "source_write": "allowed" if write else "denied", "protected_write": "denied"}
            if violation == "hidden_read":
                observed["hidden"] = "hidden-evaluator-canary"
            if violation == "orientation_write" and not write:
                observed["source_write"] = "allowed"
            if violation == "protected_write":
                observed["protected_write"] = "allowed"
            if violation == "missing_source_access":
                observed["source_read"] = "denied"
            if violation == "missing_write_access" and write:
                observed["source_write"] = "denied"
            return {"exitCode": 0, "stdout": json.dumps(observed), "stderr": ""}

    result = isolation_probe(BoundaryClient(), workspace, tmp_path / "hidden")
    assert result["status"] == ("passed" if violation is None else "failed")


@pytest.mark.parametrize("field,value", [("activePermissionProfile", {"id": WRITE_PROFILE}),
                                         ("runtimeWorkspaceRoots", []), ("cwd", "/")])
def test_effective_profile_or_workspace_mismatch_is_rejected(tmp_path: Path, field, value) -> None:
    response = {"activePermissionProfile": {"id": READ_PROFILE},
                "runtimeWorkspaceRoots": [str(tmp_path)], "cwd": str(tmp_path)}
    verify_profile(response, READ_PROFILE, tmp_path)
    response[field] = value
    with pytest.raises(ValueError):
        verify_profile(response, READ_PROFILE, tmp_path)
