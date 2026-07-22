from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from loci.storage.store_identity import StoreBinding, StoreIdentityError


@dataclass(frozen=True)
class StoreResolution:
    base_dir: Path
    source: str
    config_path: Path | None = None
    namespace: str | None = None
    store_id: str | None = None

    def to_dict(self) -> dict[str, str]:
        data = {
            "base_dir": str(self.base_dir),
            "source": self.source,
        }
        if self.config_path is not None:
            data["config_path"] = str(self.config_path)
        if self.namespace is not None:
            data["namespace"] = self.namespace
        if self.store_id is not None:
            data["store_id"] = self.store_id
        return data


_active_mcp_store: StoreResolution | None = None


def resolve_store_base_dir() -> StoreResolution:
    if _active_mcp_store is not None:
        return _active_mcp_store
    env_base = os.environ.get("LOCI_BASE_DIR")
    if env_base:
        return StoreResolution(Path(env_base).expanduser(), "env")

    codex_home = Path(os.environ.get("CODEX_HOME", Path.home() / ".codex")).expanduser()
    config_path = codex_home / "config.toml"
    config_base = _read_codex_mcp_loci_base_dir(config_path)
    if config_base:
        return StoreResolution(
            Path(config_base).expanduser(),
            "codex_mcp_config",
            config_path=config_path,
        )

    codex_default = codex_home / "loci-index"
    if codex_default.exists():
        return StoreResolution(codex_default, "codex_default")

    return StoreResolution(Path.home() / ".codeindex", "legacy_default")


def activate_mcp_store(binding: StoreBinding) -> StoreResolution:
    global _active_mcp_store
    candidate = StoreResolution(
        base_dir=binding.base_dir,
        source="mcp_environment",
        namespace=binding.namespace,
        store_id=binding.store_id,
    )
    if _active_mcp_store is not None:
        if _active_mcp_store == candidate:
            return _active_mcp_store
        raise StoreIdentityError(
            "MCP_STORE_ALREADY_BOUND",
            "The Loci MCP process is already bound to another store",
            {
                "active": _active_mcp_store.to_dict(),
                "requested": candidate.to_dict(),
            },
        )
    _active_mcp_store = candidate
    return _active_mcp_store


def _read_codex_mcp_loci_base_dir(config_path: Path) -> str | None:
    if not config_path.exists():
        return None
    try:
        import tomllib
    except ModuleNotFoundError:
        return None

    try:
        data: dict[str, Any] = tomllib.loads(config_path.read_text())
    except (OSError, tomllib.TOMLDecodeError):
        return None

    mcp_servers = data.get("mcp_servers")
    if not isinstance(mcp_servers, dict):
        return None
    loci = mcp_servers.get("loci")
    if not isinstance(loci, dict):
        return None
    env = loci.get("env")
    if not isinstance(env, dict):
        return None
    base = env.get("LOCI_BASE_DIR")
    return base if isinstance(base, str) and base else None
