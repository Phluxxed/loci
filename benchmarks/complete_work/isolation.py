"""Build explicit, matched local Codex permissions without editing user config."""
from __future__ import annotations

from pathlib import Path
import tomllib

READ_PROFILE = "loci_episode_read"
WRITE_PROFILE = "loci_episode_write"
DENIED = ("/Users/brummerv/.claude", "/Users/brummerv/Downloads",
          "/Users/brummerv/work", "/Users/brummerv/improvements",
          "/Users/brummerv/claude-otel")


def build_overrides(workspace: Path, readonly_roots: list[Path],
                    mcp_command: str, mcp_args: list[str], mcp_env: dict[str, str],
                    *, user_config: Path) -> dict:
    workspace = workspace.resolve(strict=True)
    readonly = [p.resolve(strict=True) for p in readonly_roots]
    if any(workspace.is_relative_to(p) or p.is_relative_to(workspace) for p in readonly):
        raise ValueError("read-only dependencies must be outside the writable source")
    if any(str(p) == d or p.is_relative_to(Path(d)) for p in [workspace, *readonly] for d in DENIED):
        raise ValueError("an input points into a denied root")
    current = tomllib.loads(user_config.read_text()) if user_config.exists() else {}
    overrides: dict = {
        "default_permissions": READ_PROFILE,
        "approval_policy": "never",
        "features.hooks": False,
        "features.memories": False,
        "features.apps": False,
        "features.plugins": False,
        "features.multi_agent": False,
        "features.skip_host_skill_discovery": True,
        "features.network_proxy": True,
        "web_search": "disabled",
        "model_reasoning_effort": "high",
        "shell_environment_policy.set": {
            "TMPDIR": str(workspace / ".episode-tmp"),
            "LOCI_BASE_DIR": str(workspace / ".episode-store"),
            "PYTHONDONTWRITEBYTECODE": "1",
        },
    }
    # Disable every configured connector, then install the one controlled
    # navigation server. This is process-local configuration, not user mutation.
    for name in current.get("mcp_servers", {}):
        if name != "loci":
            overrides[f"mcp_servers.{name}.enabled"] = False
    overrides["mcp_servers.loci"] = {
        "enabled": True, "required": True, "command": mcp_command,
        "args": mcp_args, "env": mcp_env,
        "startup_timeout_sec": 60, "tool_timeout_sec": 60,
    }
    for profile, access in ((READ_PROFILE, "read"), (WRITE_PROFILE, "write")):
        files: dict = {
            ":root": "deny", ":minimal": "read", ":tmpdir": "deny",
            ":slash_tmp": "deny", ":workspace_roots": {
                ".": access, ".git": "read", ".codex": "read", ".agents": "read",
                ".complete-work-isolation.json": "read",
                "node_modules": "read", ".venv": "read",
                ".episode-tmp": "write", ".episode-store": "write",
            },
        }
        for path in readonly:
            files[str(path)] = "read"
        for path in DENIED:
            files[path] = "deny"
            files[path + "/**"] = "deny"
        overrides[f"permissions.{profile}"] = {
            "description": "Isolated complete-work source and prepared dependencies",
            "filesystem": files,
            "network": {"enabled": True,
                        "domains": {"127.0.0.1": "allow", "localhost": "allow", "[::1]": "allow"}},
        }
    return overrides


def verify_profile(response: dict, expected: str, workspace: Path) -> None:
    if response.get("activePermissionProfile", {}).get("id") != expected:
        raise ValueError("runtime did not activate the requested permission profile")
    roots = response.get("runtimeWorkspaceRoots", [])
    if [str(Path(x).resolve()) for x in roots] != [str(workspace.resolve())]:
        raise ValueError("runtime workspace roots differ from the isolated target")
    if Path(response["cwd"]).resolve() != workspace.resolve():
        raise ValueError("runtime cwd differs from the isolated target")
