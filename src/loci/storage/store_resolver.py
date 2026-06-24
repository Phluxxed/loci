from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class StoreResolution:
    base_dir: Path
    source: str
    config_path: Path | None = None

    def to_dict(self) -> dict[str, str]:
        data = {
            "base_dir": str(self.base_dir),
            "source": self.source,
        }
        if self.config_path is not None:
            data["config_path"] = str(self.config_path)
        return data


def resolve_store_base_dir() -> StoreResolution:
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
