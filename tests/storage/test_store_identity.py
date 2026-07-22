from __future__ import annotations

import json
import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from loci.storage.store_identity import (
    STORE_IDENTITY_FILE,
    StoreIdentityError,
    bind_mcp_store,
    initialize_store,
)


def test_bind_mcp_store_requires_explicit_base_dir() -> None:
    with pytest.raises(StoreIdentityError) as exc_info:
        bind_mcp_store({"LOCI_STORE_NAMESPACE": "claude"})

    assert exc_info.value.code == "MCP_STORE_CONFIG_MISSING"
    assert exc_info.value.details == {"missing": ["LOCI_BASE_DIR"]}


def test_bind_mcp_store_requires_explicit_namespace(tmp_path: Path) -> None:
    with pytest.raises(StoreIdentityError) as exc_info:
        bind_mcp_store({"LOCI_BASE_DIR": str(tmp_path / "index")})

    assert exc_info.value.code == "MCP_STORE_CONFIG_MISSING"
    assert exc_info.value.details == {"missing": ["LOCI_STORE_NAMESPACE"]}


def test_bind_mcp_store_rejects_relative_base_dir() -> None:
    with pytest.raises(StoreIdentityError) as exc_info:
        bind_mcp_store({
            "LOCI_BASE_DIR": "relative/index",
            "LOCI_STORE_NAMESPACE": "claude",
        })

    assert exc_info.value.code == "INVALID_MCP_STORE_CONFIGURATION"
    assert exc_info.value.details["field"] == "LOCI_BASE_DIR"


@pytest.mark.parametrize("namespace", ["", "../claude", "claude/code", "a b", "."])
def test_bind_mcp_store_rejects_unsafe_namespace(
    tmp_path: Path,
    namespace: str,
) -> None:
    with pytest.raises(StoreIdentityError) as exc_info:
        bind_mcp_store({
            "LOCI_BASE_DIR": str(tmp_path / "index"),
            "LOCI_STORE_NAMESPACE": namespace,
        })

    assert exc_info.value.code in {
        "MCP_STORE_CONFIG_MISSING",
        "INVALID_MCP_STORE_CONFIGURATION",
    }


def test_bind_mcp_store_initializes_empty_root(tmp_path: Path) -> None:
    root = tmp_path / "claude-index"

    binding = bind_mcp_store({
        "LOCI_BASE_DIR": str(root),
        "LOCI_STORE_NAMESPACE": "claude",
    })

    marker = json.loads((root / STORE_IDENTITY_FILE).read_text())
    assert binding.base_dir == root.resolve()
    assert binding.namespace == "claude"
    assert binding.store_id == marker["store_id"]
    assert marker == {
        "schema_version": 1,
        "namespace": "claude",
        "store_id": binding.store_id,
    }
    if os.name == "posix":
        assert root.stat().st_mode & 0o777 == 0o700


def test_bind_mcp_store_refuses_nonempty_unmarked_root(tmp_path: Path) -> None:
    root = tmp_path / "legacy-index"
    root.mkdir()
    existing = root / "existing-index.json"
    existing.write_text("preserve me")

    with pytest.raises(StoreIdentityError) as exc_info:
        bind_mcp_store({
            "LOCI_BASE_DIR": str(root),
            "LOCI_STORE_NAMESPACE": "codex",
        })

    assert exc_info.value.code == "STORE_IDENTITY_REQUIRED"
    assert existing.read_text() == "preserve me"
    assert not (root / STORE_IDENTITY_FILE).exists()


def test_initialize_store_explicitly_adopts_existing_root(tmp_path: Path) -> None:
    root = tmp_path / "legacy-index"
    root.mkdir()
    existing = root / "existing-index.json"
    existing.write_text("preserve me")

    binding = initialize_store(root, "codex", adopt_existing=True)

    assert binding.namespace == "codex"
    assert existing.read_text() == "preserve me"
    assert (root / STORE_IDENTITY_FILE).exists()


def test_bind_mcp_store_reuses_matching_identity(tmp_path: Path) -> None:
    root = tmp_path / "index"
    first = bind_mcp_store({
        "LOCI_BASE_DIR": str(root),
        "LOCI_STORE_NAMESPACE": "codex",
    })

    second = bind_mcp_store({
        "LOCI_BASE_DIR": str(root),
        "LOCI_STORE_NAMESPACE": "codex",
    })

    assert second == first


def test_bind_mcp_store_initialization_is_race_safe(tmp_path: Path) -> None:
    root = tmp_path / "index"
    environment = {
        "LOCI_BASE_DIR": str(root),
        "LOCI_STORE_NAMESPACE": "codex",
    }

    with ThreadPoolExecutor(max_workers=2) as executor:
        bindings = list(executor.map(lambda _: bind_mcp_store(environment), range(2)))

    assert bindings[0].store_id == bindings[1].store_id
    assert json.loads((root / STORE_IDENTITY_FILE).read_text())["store_id"] == (
        bindings[0].store_id
    )


def test_bind_mcp_store_refuses_namespace_mismatch(tmp_path: Path) -> None:
    root = tmp_path / "index"
    bind_mcp_store({
        "LOCI_BASE_DIR": str(root),
        "LOCI_STORE_NAMESPACE": "codex",
    })

    with pytest.raises(StoreIdentityError) as exc_info:
        bind_mcp_store({
            "LOCI_BASE_DIR": str(root),
            "LOCI_STORE_NAMESPACE": "claude",
        })

    assert exc_info.value.code == "STORE_NAMESPACE_MISMATCH"
    assert exc_info.value.details["expected_namespace"] == "claude"
    assert exc_info.value.details["actual_namespace"] == "codex"


def test_bind_mcp_store_refuses_malformed_identity(tmp_path: Path) -> None:
    root = tmp_path / "index"
    root.mkdir()
    marker = root / STORE_IDENTITY_FILE
    marker.write_text("not-json")

    with pytest.raises(StoreIdentityError) as exc_info:
        bind_mcp_store({
            "LOCI_BASE_DIR": str(root),
            "LOCI_STORE_NAMESPACE": "codex",
        })

    assert exc_info.value.code == "INVALID_STORE_IDENTITY"
    assert marker.read_text() == "not-json"


@pytest.mark.skipif(os.name != "posix", reason="POSIX filesystem contract")
def test_bind_mcp_store_refuses_symlink_identity(tmp_path: Path) -> None:
    root = tmp_path / "index"
    root.mkdir()
    external = tmp_path / "external.json"
    external.write_text(
        json.dumps({
            "schema_version": 1,
            "namespace": "codex",
            "store_id": "ae5cab56-c999-4bb1-b0cf-b258f7c3e5dc",
        })
    )
    (root / STORE_IDENTITY_FILE).symlink_to(external)

    with pytest.raises(StoreIdentityError) as exc_info:
        bind_mcp_store({
            "LOCI_BASE_DIR": str(root),
            "LOCI_STORE_NAMESPACE": "codex",
        })

    assert exc_info.value.code == "INVALID_STORE_IDENTITY"


@pytest.mark.skipif(os.name != "posix", reason="POSIX permission contract")
@pytest.mark.parametrize("mode", [0o720, 0o702])
def test_bind_mcp_store_refuses_root_writable_by_others(
    tmp_path: Path,
    mode: int,
) -> None:
    root = tmp_path / "index"
    root.mkdir(mode=mode)
    root.chmod(mode)

    with pytest.raises(StoreIdentityError) as exc_info:
        bind_mcp_store({
            "LOCI_BASE_DIR": str(root),
            "LOCI_STORE_NAMESPACE": "codex",
        })

    assert exc_info.value.code == "UNSAFE_MCP_STORE"


def test_bind_mcp_store_resolves_symlink_once(tmp_path: Path) -> None:
    target = tmp_path / "target"
    target.mkdir()
    link = tmp_path / "link"
    link.symlink_to(target, target_is_directory=True)

    binding = bind_mcp_store({
        "LOCI_BASE_DIR": str(link),
        "LOCI_STORE_NAMESPACE": "claude",
    })

    assert binding.base_dir == target.resolve()
