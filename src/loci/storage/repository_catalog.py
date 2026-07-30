from __future__ import annotations

import json
import os
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

from loci.storage.store_layout import canonical_repository_cache_key


CATALOG_SCHEMA_VERSION = 1
REPOSITORY_METADATA_SCHEMA_VERSION = 1
CATALOG_FILE_NAME = ".loci-repositories.json"
PENDING_MUTATION_FILE_NAME = ".loci-repositories.pending.json"
REPOSITORY_METADATA_FILE_NAME = ".loci-repository.json"
DEFAULT_MAX_REPOSITORIES = 1024
DEFAULT_MAX_TOTAL_INDEX_BYTES = 2 * 1024 * 1024 * 1024
_MAX_METADATA_TOKEN_CHARS = 64 * 1024


@dataclass
class RepositoryCatalogError(Exception):
    code: str
    message: str
    details: dict[str, Any] = field(default_factory=dict)

    def __str__(self) -> str:
        return self.message

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "message": self.message,
            "details": self.details,
        }


@dataclass(frozen=True, slots=True)
class RepositoryCatalogEntry:
    cache_key: str
    symbols: int
    path: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "cache_key": self.cache_key,
            "symbols": self.symbols,
            "path": self.path,
        }

    @classmethod
    def from_dict(
        cls,
        value: Mapping[str, Any],
        *,
        expected_cache_key: str | None = None,
    ) -> RepositoryCatalogEntry:
        cache_key = value.get("cache_key")
        symbols = value.get("symbols")
        path = value.get("path")
        if (
            not isinstance(cache_key, str)
            or not cache_key
            or isinstance(symbols, bool)
            or not isinstance(symbols, int)
            or symbols < 0
            or not isinstance(path, str)
            or not path
        ):
            raise ValueError("invalid repository catalog entry")
        if expected_cache_key is not None and cache_key != expected_cache_key:
            raise ValueError("repository metadata cache key does not match its directory")
        if not Path(path).is_absolute():
            raise ValueError("repository catalog path must be absolute")
        if canonical_repository_cache_key(path) != cache_key:
            raise ValueError("repository catalog cache key does not match its path")
        return cls(cache_key=cache_key, symbols=symbols, path=path)


class RepositoryCatalog:
    """Small authoritative repository inventory with explicit crash recovery."""

    def __init__(self, base_dir: Path) -> None:
        self.base_dir = base_dir
        self.catalog_path = base_dir / CATALOG_FILE_NAME
        self.pending_path = base_dir / PENDING_MUTATION_FILE_NAME

    def list_entries(self) -> list[dict[str, Any]]:
        entries = self.entries_for_mutation()
        return [
            entries[cache_key].to_dict()
            for cache_key in sorted(entries)
        ]

    def entries_for_mutation(self) -> dict[str, RepositoryCatalogEntry]:
        if self.pending_path.exists():
            raise self._repair_required("an interrupted catalog mutation is pending")
        if not self.catalog_path.exists():
            legacy_keys = self._repository_cache_keys()
            if legacy_keys:
                raise self._repair_required(
                    "the store contains repository indexes but has no catalog",
                    cache_keys=legacy_keys,
                )
            return {}
        try:
            raw = json.loads(self.catalog_path.read_text(encoding="utf-8"))
            return self._decode_catalog(raw)
        except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
            raise self._repair_required(
                "the repository catalog is unreadable or invalid",
                error=str(exc),
            ) from exc

    def begin_mutation(self, operation: str, cache_key: str | None = None) -> None:
        marker = {
            "schema_version": CATALOG_SCHEMA_VERSION,
            "operation": operation,
        }
        if cache_key is not None:
            marker["cache_key"] = cache_key
        payload = (json.dumps(marker, sort_keys=True) + "\n").encode("utf-8")
        try:
            fd = os.open(
                self.pending_path,
                os.O_CREAT | os.O_EXCL | os.O_WRONLY,
                0o600,
            )
        except FileExistsError as exc:
            raise self._repair_required(
                "an interrupted catalog mutation is already pending"
            ) from exc
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            _fsync_directory(self.base_dir)
        except BaseException:
            # A partial marker deliberately remains visible. Repair treats even a
            # malformed marker as evidence that normal inventory is unsafe.
            raise

    def commit(
        self,
        entries: Mapping[str, RepositoryCatalogEntry],
    ) -> None:
        payload = {
            "schema_version": CATALOG_SCHEMA_VERSION,
            "repositories": [
                entries[cache_key].to_dict()
                for cache_key in sorted(entries)
            ],
        }
        _atomic_write_json(self.catalog_path, payload)

    def finish_mutation(self) -> None:
        self.pending_path.unlink(missing_ok=True)
        _fsync_directory(self.base_dir)

    def write_repository_metadata(self, entry: RepositoryCatalogEntry) -> None:
        metadata_path = (
            self.base_dir
            / entry.cache_key
            / REPOSITORY_METADATA_FILE_NAME
        )
        _atomic_write_json(
            metadata_path,
            {
                "schema_version": REPOSITORY_METADATA_SCHEMA_VERSION,
                **entry.to_dict(),
            },
        )

    def repair(
        self,
        *,
        max_repositories: int = DEFAULT_MAX_REPOSITORIES,
        max_total_index_bytes: int = DEFAULT_MAX_TOTAL_INDEX_BYTES,
    ) -> dict[str, Any]:
        if max_repositories < 0 or max_total_index_bytes < 0:
            raise RepositoryCatalogError(
                "REPOSITORY_CATALOG_REPAIR_LIMIT_INVALID",
                "Repository catalog repair limits must be non-negative",
                {
                    "max_repositories": max_repositories,
                    "max_total_index_bytes": max_total_index_bytes,
                },
            )

        created_repair_marker = False
        if not self.pending_path.exists():
            self.begin_mutation("repair")
            created_repair_marker = True

        try:
            repo_dirs = self._repository_directories()
            if len(repo_dirs) > max_repositories:
                raise self._limit_exceeded(
                    repositories=len(repo_dirs),
                    legacy_index_bytes=0,
                    max_repositories=max_repositories,
                    max_total_index_bytes=max_total_index_bytes,
                )

            pending_cache_key, pending_is_valid = self._pending_cache_key()
            metadata_entries: dict[str, RepositoryCatalogEntry] = {}
            indexes_to_scan: list[tuple[Path, Path]] = []
            total_index_bytes = 0
            for repo_dir in repo_dirs:
                cache_key = repo_dir.name
                entry = None
                if pending_is_valid and pending_cache_key == cache_key:
                    # The index and sidecar are separate atomic replacements.
                    # For an interrupted key, the index decides old versus new.
                    entry = None
                elif pending_is_valid:
                    entry = self._read_repository_metadata(repo_dir)
                if entry is not None:
                    metadata_entries[cache_key] = entry
                    continue
                index_path = repo_dir / "index.json"
                index_bytes = index_path.stat().st_size
                total_index_bytes += index_bytes
                indexes_to_scan.append((repo_dir, index_path))

            if total_index_bytes > max_total_index_bytes:
                raise self._limit_exceeded(
                    repositories=len(repo_dirs),
                    legacy_index_bytes=total_index_bytes,
                    max_repositories=max_repositories,
                    max_total_index_bytes=max_total_index_bytes,
                )

            parsed_entries: list[RepositoryCatalogEntry] = []
            for repo_dir, index_path in indexes_to_scan:
                entry = self._read_legacy_index_metadata(
                    index_path,
                    repo_dir.name,
                )
                metadata_entries[repo_dir.name] = entry
                parsed_entries.append(entry)
        except BaseException:
            if created_repair_marker:
                self.finish_mutation()
            raise

        try:
            for entry in parsed_entries:
                self.write_repository_metadata(entry)
            self.commit(metadata_entries)
            self.finish_mutation()
        except BaseException:
            # Whether inherited from an interrupted mutation or created above,
            # the marker remains until a later deterministic repair succeeds.
            raise

        return {
            "status": "repaired",
            "repositories": len(metadata_entries),
            "legacy_indexes_scanned": len(indexes_to_scan),
            "legacy_index_bytes_scanned": total_index_bytes,
        }

    def _decode_catalog(
        self,
        raw: Any,
    ) -> dict[str, RepositoryCatalogEntry]:
        if not isinstance(raw, Mapping):
            raise ValueError("repository catalog root must be an object")
        if raw.get("schema_version") != CATALOG_SCHEMA_VERSION:
            raise ValueError("unsupported repository catalog schema")
        repositories = raw.get("repositories")
        if not isinstance(repositories, list):
            raise ValueError("repository catalog repositories must be a list")
        entries: dict[str, RepositoryCatalogEntry] = {}
        for raw_entry in repositories:
            if not isinstance(raw_entry, Mapping):
                raise ValueError("repository catalog entry must be an object")
            entry = RepositoryCatalogEntry.from_dict(raw_entry)
            if entry.cache_key in entries:
                raise ValueError("repository catalog contains duplicate cache keys")
            entries[entry.cache_key] = entry
        return entries

    def _repository_directories(self) -> list[Path]:
        repo_dirs: list[Path] = []
        for entry in self.base_dir.iterdir():
            if entry.is_symlink():
                raise RepositoryCatalogError(
                    "REPOSITORY_CATALOG_LEGACY_INDEX_INVALID",
                    "Repository catalog repair does not follow store symlinks",
                    {"entry": str(entry)},
                )
            if not entry.is_dir():
                continue
            index_path = entry / "index.json"
            if index_path.is_symlink():
                raise RepositoryCatalogError(
                    "REPOSITORY_CATALOG_LEGACY_INDEX_INVALID",
                    "Repository catalog repair does not follow index symlinks",
                    {"index": str(index_path)},
                )
            if index_path.is_file():
                repo_dirs.append(entry)
        return sorted(repo_dirs, key=lambda path: path.name)

    def _repository_cache_keys(self) -> list[str]:
        return [path.name for path in self._repository_directories()]

    def _read_repository_metadata(
        self,
        repo_dir: Path,
    ) -> RepositoryCatalogEntry | None:
        metadata_path = repo_dir / REPOSITORY_METADATA_FILE_NAME
        if not metadata_path.is_file():
            return None
        try:
            raw = json.loads(metadata_path.read_text(encoding="utf-8"))
            if not isinstance(raw, Mapping):
                return None
            if raw.get("schema_version") != REPOSITORY_METADATA_SCHEMA_VERSION:
                return None
            return RepositoryCatalogEntry.from_dict(
                raw,
                expected_cache_key=repo_dir.name,
            )
        except (OSError, UnicodeError, json.JSONDecodeError, ValueError):
            return None

    def _pending_cache_key(self) -> tuple[str | None, bool]:
        if not self.pending_path.exists():
            return None, True
        try:
            raw = json.loads(self.pending_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError):
            return None, False
        if not isinstance(raw, Mapping):
            return None, False
        operation = raw.get("operation")
        cache_key = raw.get("cache_key")
        if operation == "repair":
            return None, True
        if operation not in {"write", "invalidate"}:
            return None, False
        if not isinstance(cache_key, str) or not cache_key:
            return None, False
        return cache_key, True

    def _read_legacy_index_metadata(
        self,
        index_path: Path,
        cache_key: str,
    ) -> RepositoryCatalogEntry:
        if _uses_pretty_index_layout(index_path):
            result = _scan_pretty_index_metadata(index_path)
            if result is None:
                raise _legacy_index_invalid(
                    index_path,
                    "Legacy index does not contain readable repository metadata",
                )
        else:
            result = _scan_compact_index_metadata(index_path)
        path, symbol_count = result
        return RepositoryCatalogEntry(
            cache_key=cache_key,
            symbols=symbol_count,
            path=path,
        )

    def _repair_required(
        self,
        reason: str,
        **details: Any,
    ) -> RepositoryCatalogError:
        return RepositoryCatalogError(
            "REPOSITORY_CATALOG_REPAIR_REQUIRED",
            "Repository catalog repair is required before inventory can continue",
            {
                "reason": reason,
                "catalog": str(self.catalog_path),
                "repair_command": "loci store repair-catalog",
                **details,
            },
        )

    def _limit_exceeded(
        self,
        *,
        repositories: int,
        legacy_index_bytes: int,
        max_repositories: int,
        max_total_index_bytes: int,
    ) -> RepositoryCatalogError:
        return RepositoryCatalogError(
            "REPOSITORY_CATALOG_REPAIR_LIMIT_EXCEEDED",
            "Repository catalog repair would exceed its explicit work bounds",
            {
                "repositories": repositories,
                "legacy_index_bytes": legacy_index_bytes,
                "max_repositories": max_repositories,
                "max_total_index_bytes": max_total_index_bytes,
            },
        )


def _atomic_write_json(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    payload = (json.dumps(value, sort_keys=True) + "\n").encode("utf-8")
    try:
        fd = os.open(
            tmp_path,
            os.O_CREAT | os.O_EXCL | os.O_WRONLY,
            0o600,
        )
        with os.fdopen(fd, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_path, path)
        _fsync_directory(path.parent)
    finally:
        tmp_path.unlink(missing_ok=True)


def _fsync_directory(path: Path) -> None:
    try:
        fd = os.open(path, os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(fd)
    except OSError:
        # Some filesystems do not support directory fsync. File replacement is
        # still atomic; durability falls back to the filesystem's guarantees.
        pass
    finally:
        os.close(fd)


def _scan_pretty_index_metadata(index_path: Path) -> tuple[str, int] | None:
    """Fast path for Loci's historical ``json.dumps(..., indent=2)`` indexes."""

    in_symbols = False
    saw_symbols_end = False
    symbol_count = 0
    repo_path: str | None = None
    with index_path.open("r", encoding="utf-8") as handle:
        for line in handle:
            stripped = line.lstrip(" ")
            indent = len(line) - len(stripped)
            if not in_symbols and indent == 2 and stripped.startswith('"symbols": ['):
                in_symbols = True
                continue
            if in_symbols:
                if indent == 4 and stripped.startswith("{"):
                    symbol_count += 1
                elif indent == 2 and stripped.startswith("]"):
                    in_symbols = False
                    saw_symbols_end = True
                continue
            if indent == 2 and stripped.startswith('"repo_path":'):
                encoded_value = stripped.split(":", 1)[1].strip().rstrip(",")
                try:
                    decoded = json.loads(encoded_value)
                except json.JSONDecodeError:
                    return None
                if isinstance(decoded, str) and decoded:
                    repo_path = decoded
    if saw_symbols_end and repo_path is not None:
        return repo_path, symbol_count
    return None


def _uses_pretty_index_layout(index_path: Path) -> bool:
    with index_path.open("rb") as handle:
        prefix = handle.read(64 * 1024)
    return b'\n  "symbols": [\n' in prefix


def _scan_compact_index_metadata(index_path: Path) -> tuple[str, int]:
    """Bounded-memory fallback for legacy indexes with arbitrary whitespace."""

    object_depth = 0
    array_depth = 0
    symbols_array_depth: int | None = None
    symbol_count = 0
    saw_symbols = False
    repo_path: str | None = None
    root_closed = False
    expecting_root_key = False
    expecting_colon = False
    expecting_root_value = False
    current_root_key: str | None = None
    in_string = False
    escaped = False
    collect_kind: str | None = None
    collected: list[str] = []

    with index_path.open("r", encoding="utf-8") as handle:
        while chunk := handle.read(1024 * 1024):
            for char in chunk:
                if in_string:
                    if collect_kind is not None:
                        if len(collected) >= _MAX_METADATA_TOKEN_CHARS:
                            raise _legacy_index_invalid(
                                index_path,
                                "Legacy index metadata token exceeds the repair bound",
                            )
                        collected.append(char)
                    if escaped:
                        escaped = False
                        continue
                    if char == "\\":
                        escaped = True
                        continue
                    if char != '"':
                        continue
                    in_string = False
                    if collect_kind is not None:
                        token = '"' + "".join(collected)
                        try:
                            decoded = json.loads(token)
                        except json.JSONDecodeError as exc:
                            raise _legacy_index_invalid(
                                index_path,
                                "Legacy index contains invalid catalog metadata",
                                error=str(exc),
                            ) from exc
                        if collect_kind == "key":
                            current_root_key = decoded
                            expecting_colon = True
                            expecting_root_key = False
                        else:
                            repo_path = decoded
                            expecting_root_value = False
                        collect_kind = None
                        collected = []
                    continue

                if char.isspace():
                    continue
                if root_closed:
                    raise _legacy_index_invalid(
                        index_path,
                        "Legacy index contains data after its root object",
                    )
                if char == '"':
                    in_string = True
                    escaped = False
                    if object_depth == 1 and array_depth == 0:
                        if expecting_root_key:
                            collect_kind = "key"
                            collected = []
                        elif (
                            expecting_root_value
                            and current_root_key == "repo_path"
                        ):
                            collect_kind = "repo_path"
                            collected = []
                    continue
                if char == "{":
                    if (
                        symbols_array_depth is not None
                        and array_depth == symbols_array_depth
                        and object_depth == 1
                    ):
                        symbol_count += 1
                    object_depth += 1
                    if object_depth == 1:
                        expecting_root_key = True
                    continue
                if char == "}":
                    object_depth -= 1
                    if object_depth < 0:
                        break
                    if object_depth == 0:
                        root_closed = True
                    continue
                if char == "[":
                    array_depth += 1
                    if (
                        object_depth == 1
                        and array_depth == 1
                        and expecting_root_value
                        and current_root_key == "symbols"
                    ):
                        symbols_array_depth = array_depth
                        saw_symbols = True
                        expecting_root_value = False
                    continue
                if char == "]":
                    if symbols_array_depth == array_depth:
                        symbols_array_depth = None
                    array_depth -= 1
                    if array_depth < 0:
                        break
                    continue
                if (
                    char == ":"
                    and object_depth == 1
                    and array_depth == 0
                    and expecting_colon
                ):
                    expecting_colon = False
                    expecting_root_value = True
                    continue
                if char == "," and object_depth == 1 and array_depth == 0:
                    expecting_root_key = True
                    expecting_colon = False
                    expecting_root_value = False
                    current_root_key = None

    if (
        in_string
        or object_depth != 0
        or array_depth != 0
        or not root_closed
        or not saw_symbols
        or repo_path is None
        or not isinstance(repo_path, str)
        or not repo_path
    ):
        raise _legacy_index_invalid(
            index_path,
            "Legacy index does not contain readable repository metadata",
        )
    return repo_path, symbol_count


def _legacy_index_invalid(
    index_path: Path,
    message: str,
    **details: Any,
) -> RepositoryCatalogError:
    return RepositoryCatalogError(
        "REPOSITORY_CATALOG_LEGACY_INDEX_INVALID",
        message,
        {"index": str(index_path), **details},
    )
