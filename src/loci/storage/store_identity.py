from __future__ import annotations

import json
import os
import re
import stat
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Mapping

STORE_IDENTITY_FILE = ".loci-store.json"
STORE_IDENTITY_SCHEMA_VERSION = 1
_NAMESPACE_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}\Z")


@dataclass(frozen=True, slots=True)
class StoreBinding:
    base_dir: Path
    namespace: str
    store_id: str
    adopted_existing: bool = False

    def to_dict(self) -> dict[str, str | bool]:
        return {
            "base_dir": str(self.base_dir),
            "namespace": self.namespace,
            "store_id": self.store_id,
            "adopted_existing": self.adopted_existing,
        }


@dataclass
class StoreIdentityError(Exception):
    code: str
    message: str
    details: dict[str, object] = field(default_factory=dict)

    def __str__(self) -> str:
        return self.message

    def to_dict(self) -> dict[str, object]:
        return {
            "code": self.code,
            "message": self.message,
            "details": self.details,
        }


def bind_mcp_store(
    environment: Mapping[str, str] | None = None,
) -> StoreBinding:
    env = os.environ if environment is None else environment
    missing = [
        name
        for name in ("LOCI_BASE_DIR", "LOCI_STORE_NAMESPACE")
        if not env.get(name)
    ]
    if missing:
        raise StoreIdentityError(
            "MCP_STORE_CONFIG_MISSING",
            "Loci MCP requires an explicit store root and namespace",
            {"missing": missing},
        )
    return initialize_store(
        env["LOCI_BASE_DIR"],
        env["LOCI_STORE_NAMESPACE"],
        adopt_existing=False,
    )


def initialize_store(
    base_dir: str | Path,
    namespace: str,
    *,
    adopt_existing: bool = False,
) -> StoreBinding:
    validated_namespace = _validate_namespace(namespace)
    root = _validate_root_path(base_dir)
    created_root = not root.exists()
    try:
        root.mkdir(mode=0o700, parents=True, exist_ok=True)
    except OSError as exc:
        raise StoreIdentityError(
            "MCP_STORE_UNAVAILABLE",
            "Loci could not create the configured store root",
            {"base_dir": str(root), "error": str(exc)},
        ) from exc
    if created_root and os.name == "posix":
        try:
            root.chmod(0o700)
        except OSError as exc:
            raise StoreIdentityError(
                "MCP_STORE_UNAVAILABLE",
                "Loci could not secure the configured store root",
                {"base_dir": str(root), "error": str(exc)},
            ) from exc
    _validate_root_directory(root)

    marker_path = root / STORE_IDENTITY_FILE
    if marker_path.exists():
        return _read_binding(marker_path, root, validated_namespace)

    entries = _list_entries(root)
    if entries and not adopt_existing:
        raise StoreIdentityError(
            "STORE_IDENTITY_REQUIRED",
            "The configured store is non-empty and has no Loci identity marker",
            {
                "base_dir": str(root),
                "namespace": validated_namespace,
                "recovery": (
                    "Run `loci store init --base-dir <path> --namespace <name> "
                    "--adopt-existing` after verifying ownership"
                ),
            },
        )

    store_id = str(uuid.uuid4())
    marker = {
        "schema_version": STORE_IDENTITY_SCHEMA_VERSION,
        "namespace": validated_namespace,
        "store_id": store_id,
    }
    try:
        fd = os.open(marker_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError:
        return _read_binding(marker_path, root, validated_namespace)
    except OSError as exc:
        raise StoreIdentityError(
            "MCP_STORE_UNAVAILABLE",
            "Loci could not create the store identity marker",
            {"marker": str(marker_path), "error": str(exc)},
        ) from exc

    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(marker, handle, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
    except OSError as exc:
        marker_path.unlink(missing_ok=True)
        raise StoreIdentityError(
            "MCP_STORE_UNAVAILABLE",
            "Loci could not persist the store identity marker",
            {"marker": str(marker_path), "error": str(exc)},
        ) from exc

    return StoreBinding(
        base_dir=root,
        namespace=validated_namespace,
        store_id=store_id,
        adopted_existing=bool(entries),
    )


def _validate_namespace(namespace: str) -> str:
    if not _NAMESPACE_PATTERN.fullmatch(namespace):
        raise StoreIdentityError(
            "INVALID_MCP_STORE_CONFIGURATION",
            "LOCI_STORE_NAMESPACE must be 1-64 safe identifier characters",
            {"field": "LOCI_STORE_NAMESPACE", "value": namespace},
        )
    return namespace


def _validate_root_path(base_dir: str | Path) -> Path:
    expanded = Path(base_dir).expanduser()
    if not expanded.is_absolute():
        raise StoreIdentityError(
            "INVALID_MCP_STORE_CONFIGURATION",
            "LOCI_BASE_DIR must be an absolute path",
            {"field": "LOCI_BASE_DIR", "value": str(base_dir)},
        )
    return expanded.resolve(strict=False)


def _validate_root_directory(root: Path) -> None:
    try:
        info = root.stat()
    except OSError as exc:
        raise StoreIdentityError(
            "MCP_STORE_UNAVAILABLE",
            "Loci could not inspect the configured store root",
            {"base_dir": str(root), "error": str(exc)},
        ) from exc
    if not root.is_dir():
        raise StoreIdentityError(
            "INVALID_MCP_STORE_CONFIGURATION",
            "LOCI_BASE_DIR must name a directory",
            {"field": "LOCI_BASE_DIR", "value": str(root)},
        )
    if os.name == "posix" and info.st_uid != os.geteuid():
        raise StoreIdentityError(
            "UNSAFE_MCP_STORE",
            "The configured store root is not owned by the current user",
            {"base_dir": str(root)},
        )
    if info.st_mode & (stat.S_IWGRP | stat.S_IWOTH):
        raise StoreIdentityError(
            "UNSAFE_MCP_STORE",
            "The configured store root is writable by other users",
            {"base_dir": str(root)},
        )
    if not os.access(root, os.R_OK | os.W_OK | os.X_OK):
        raise StoreIdentityError(
            "MCP_STORE_UNAVAILABLE",
            "The configured store root is not readable, writable, and searchable",
            {"base_dir": str(root)},
        )


def _list_entries(root: Path) -> list[Path]:
    try:
        return list(root.iterdir())
    except OSError as exc:
        raise StoreIdentityError(
            "MCP_STORE_UNAVAILABLE",
            "Loci could not inspect the configured store contents",
            {"base_dir": str(root), "error": str(exc)},
        ) from exc


def _read_binding(
    marker_path: Path,
    root: Path,
    expected_namespace: str,
) -> StoreBinding:
    try:
        marker_info = marker_path.lstat()
    except OSError as exc:
        raise StoreIdentityError(
            "INVALID_STORE_IDENTITY",
            "The Loci store identity marker could not be inspected",
            {"marker": str(marker_path), "error": str(exc)},
        ) from exc
    if not stat.S_ISREG(marker_info.st_mode):
        raise StoreIdentityError(
            "INVALID_STORE_IDENTITY",
            "The Loci store identity marker must be a regular file",
            {"marker": str(marker_path)},
        )
    if os.name == "posix" and marker_info.st_uid != os.geteuid():
        raise StoreIdentityError(
            "INVALID_STORE_IDENTITY",
            "The Loci store identity marker is not owned by the current user",
            {"marker": str(marker_path)},
        )
    if marker_info.st_mode & (stat.S_IWGRP | stat.S_IWOTH):
        raise StoreIdentityError(
            "INVALID_STORE_IDENTITY",
            "The Loci store identity marker is writable by other users",
            {"marker": str(marker_path)},
        )
    try:
        marker = json.loads(marker_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise StoreIdentityError(
            "INVALID_STORE_IDENTITY",
            "The Loci store identity marker is unreadable or malformed",
            {"marker": str(marker_path), "error": str(exc)},
        ) from exc
    if (
        not isinstance(marker, dict)
        or marker.get("schema_version") != STORE_IDENTITY_SCHEMA_VERSION
    ):
        raise StoreIdentityError(
            "INVALID_STORE_IDENTITY",
            "The Loci store identity marker has an unsupported schema",
            {"marker": str(marker_path)},
        )
    actual_namespace = marker.get("namespace")
    if actual_namespace != expected_namespace:
        raise StoreIdentityError(
            "STORE_NAMESPACE_MISMATCH",
            "The configured Loci store belongs to a different namespace",
            {
                "base_dir": str(root),
                "expected_namespace": expected_namespace,
                "actual_namespace": actual_namespace,
            },
        )
    store_id = marker.get("store_id")
    if not isinstance(store_id, str):
        raise StoreIdentityError(
            "INVALID_STORE_IDENTITY",
            "The Loci store identity marker has an invalid store ID",
            {"marker": str(marker_path)},
        )
    try:
        uuid.UUID(store_id)
    except ValueError as exc:
        raise StoreIdentityError(
            "INVALID_STORE_IDENTITY",
            "The Loci store identity marker has an invalid store ID",
            {"marker": str(marker_path)},
        ) from exc
    return StoreBinding(
        base_dir=root,
        namespace=expected_namespace,
        store_id=store_id,
    )
