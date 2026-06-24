from __future__ import annotations

from pathlib import Path

import pytest

from loci.storage.store_resolver import resolve_store_base_dir


def test_resolve_store_base_dir_env_wins(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    codex_home = tmp_path / ".codex"
    codex_home.mkdir()
    (codex_home / "loci-index").mkdir()
    override = tmp_path / "override"
    monkeypatch.setenv("CODEX_HOME", str(codex_home))
    monkeypatch.setenv("LOCI_BASE_DIR", str(override))

    resolution = resolve_store_base_dir()

    assert resolution.base_dir == override
    assert resolution.source == "env"


def test_resolve_store_base_dir_reads_codex_mcp_config(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    pytest.importorskip("tomllib")

    codex_home = tmp_path / ".codex"
    mcp_store = tmp_path / "mcp-store"
    codex_home.mkdir()
    config_path = codex_home / "config.toml"
    config_path.write_text(
        "[mcp_servers.loci]\n"
        "command = \"loci-mcp\"\n"
        "[mcp_servers.loci.env]\n"
        f"LOCI_BASE_DIR = \"{mcp_store}\"\n"
    )
    monkeypatch.setenv("CODEX_HOME", str(codex_home))
    monkeypatch.delenv("LOCI_BASE_DIR", raising=False)

    resolution = resolve_store_base_dir()

    assert resolution.base_dir == mcp_store
    assert resolution.source == "codex_mcp_config"
    assert resolution.config_path == config_path


def test_resolve_store_base_dir_uses_existing_codex_default(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    codex_home = tmp_path / ".codex"
    codex_default = codex_home / "loci-index"
    codex_default.mkdir(parents=True)
    monkeypatch.setenv("CODEX_HOME", str(codex_home))
    monkeypatch.delenv("LOCI_BASE_DIR", raising=False)

    resolution = resolve_store_base_dir()

    assert resolution.base_dir == codex_default
    assert resolution.source == "codex_default"
