from __future__ import annotations

import json
import stat
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from itertools import islice
from pathlib import Path
from typing import Any, Literal

from loci.storage.index_store import IndexStore, index_versions_current
from loci.storage.repository_catalog import (
    CATALOG_FILE_NAME,
    CATALOG_SCHEMA_VERSION,
    PENDING_MUTATION_FILE_NAME,
    RepositoryCatalogEntry,
)


STORE_HEALTH_SCHEMA_VERSION = 1
DEFAULT_HEALTH_LIMIT = 100
MAX_HEALTH_LIMIT = 500
DEFAULT_MAX_CATALOG_BYTES = 4 * 1024 * 1024
DEFAULT_MAX_INDEX_BYTES = 64 * 1024 * 1024
DEFAULT_MAX_PROBE_PATHS = 100_000
DEFAULT_MAX_PROBE_BYTES = 512 * 1024 * 1024

HealthState = Literal["healthy", "stale", "missing", "corrupt", "overlapping"]
ProbeStatus = Literal["complete", "unavailable"]

_STATE_ORDER: tuple[HealthState, ...] = (
    "healthy",
    "stale",
    "missing",
    "corrupt",
    "overlapping",
)


@dataclass(frozen=True, slots=True)
class HealthReason:
    state: HealthState
    code: str
    details: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "state": self.state,
            "code": self.code,
            "details": dict(self.details),
        }


@dataclass(frozen=True, slots=True)
class ProbeUnavailableReason:
    code: str
    details: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "details": dict(self.details),
        }


@dataclass(frozen=True, slots=True)
class FreshnessProbe:
    status: ProbeStatus
    reasons: tuple[HealthReason, ...] = ()
    paths_scanned: int = 0
    bytes_scanned: int = 0
    unavailable_reason: ProbeUnavailableReason | None = None

    @classmethod
    def complete(
        cls,
        *,
        reasons: tuple[HealthReason, ...] = (),
        paths_scanned: int = 0,
        bytes_scanned: int = 0,
    ) -> FreshnessProbe:
        return cls(
            status="complete",
            reasons=reasons,
            paths_scanned=paths_scanned,
            bytes_scanned=bytes_scanned,
        )

    @classmethod
    def unavailable(
        cls,
        code: str,
        details: Mapping[str, Any],
    ) -> FreshnessProbe:
        return cls(
            status="unavailable",
            unavailable_reason=ProbeUnavailableReason(code, details),
        )

    def to_dict(
        self,
        *,
        index_bytes: int | None,
    ) -> dict[str, Any]:
        result: dict[str, Any] = {
            "status": self.status,
            "index_bytes": index_bytes,
            "repository_paths_scanned": self.paths_scanned,
            "repository_bytes_scanned": self.bytes_scanned,
        }
        if self.unavailable_reason is not None:
            result["reason"] = self.unavailable_reason.to_dict()
        return result


@dataclass(frozen=True, slots=True)
class RepositoryProbeLimitExceeded(Exception):
    code: str
    limit: int
    observed: int


FreshnessProbeFunction = Callable[[Path, dict[str, Any], int, int], FreshnessProbe]


def diagnose_store(
    store: IndexStore,
    *,
    freshness_probe: FreshnessProbeFunction,
    offset: int,
    limit: int,
    max_catalog_bytes: int,
    max_index_bytes: int,
    max_probe_paths: int,
    max_probe_bytes: int,
) -> dict[str, Any]:
    bounds = {
        "max_catalog_bytes": max_catalog_bytes,
        "max_index_bytes": max_index_bytes,
        "max_probe_paths": max_probe_paths,
        "max_probe_bytes": max_probe_bytes,
    }
    entries, catalog_problem = _read_catalog(
        store,
        max_catalog_bytes=max_catalog_bytes,
        max_store_entries=max_probe_paths,
    )
    if catalog_problem is not None:
        return _catalog_problem_result(
            catalog_problem,
            offset=offset,
            limit=limit,
            bounds=bounds,
        )

    assert entries is not None

    page = entries[offset:offset + limit]
    overlaps = _overlap_reasons(entries)
    items = [
        _diagnose_repository(
            store,
            entry,
            overlap_reasons=overlaps.get(entry["cache_key"], ()),
            freshness_probe=freshness_probe,
            max_index_bytes=max_index_bytes,
            max_probe_paths=max_probe_paths,
            max_probe_bytes=max_probe_bytes,
        )
        for entry in page
    ]
    pending_path = store.base_dir / PENDING_MUTATION_FILE_NAME
    if pending_path.exists() or pending_path.is_symlink():
        return _catalog_problem_result(
            {
                "state": "corrupt",
                "code": "REPOSITORY_CATALOG_MUTATION_INTERRUPTED",
                "details": {"pending": str(pending_path)},
            },
            offset=offset,
            limit=limit,
            bounds=bounds,
        )
    next_offset = offset + len(page)
    if next_offset >= len(entries):
        next_offset = None
    complete_scope = offset == 0 and next_offset is None
    incomplete_items = sum(item["probe"]["status"] == "unavailable" for item in items)
    complete = complete_scope and incomplete_items == 0
    unhealthy = any(
        state != "healthy"
        for item in items
        for state in item["states"]
    )
    status = (
        "unhealthy"
        if unhealthy
        else "healthy"
        if complete
        else "incomplete"
    )
    state_counts = {
        state: sum(state in item["states"] for item in items)
        for state in _STATE_ORDER
    }
    return {
        "schema_version": STORE_HEALTH_SCHEMA_VERSION,
        "status": status,
        "complete": complete,
        "items": items,
        "counts": {
            "repositories": len(entries),
            "returned": len(items),
            **state_counts,
            "incomplete": incomplete_items,
        },
        "pagination": {
            "offset": offset,
            "limit": limit,
            "next_offset": next_offset,
        },
        "bounds": bounds,
        "diagnostics": [],
    }


def _read_catalog(
    store: IndexStore,
    *,
    max_catalog_bytes: int,
    max_store_entries: int,
) -> tuple[list[dict[str, Any]] | None, dict[str, Any] | None]:
    catalog_path = store.base_dir / CATALOG_FILE_NAME
    pending_path = store.base_dir / PENDING_MUTATION_FILE_NAME
    if pending_path.exists() or pending_path.is_symlink():
        return None, {
            "state": "corrupt",
            "code": "REPOSITORY_CATALOG_MUTATION_INTERRUPTED",
            "details": {"pending": str(pending_path)},
        }
    if catalog_path.is_symlink():
        return None, {
            "state": "corrupt",
            "code": "REPOSITORY_CATALOG_SYMLINK",
            "details": {"catalog": str(catalog_path)},
        }
    try:
        with catalog_path.open("rb") as handle:
            payload = handle.read(max_catalog_bytes + 1)
    except FileNotFoundError:
        return _read_store_without_catalog(
            store,
            max_store_entries=max_store_entries,
        )
    except OSError as exc:
        return None, {
            "state": "unavailable",
            "code": "REPOSITORY_CATALOG_READ_FAILED",
            "details": {
                "catalog": str(catalog_path),
                "error": str(exc)[:500],
            },
        }
    if len(payload) > max_catalog_bytes:
        return None, {
            "state": "unavailable",
            "code": "CATALOG_BYTES_LIMIT_EXCEEDED",
            "details": {
                "catalog": str(catalog_path),
                "limit": max_catalog_bytes,
                "observed": len(payload),
            },
        }
    try:
        raw = json.loads(payload.decode("utf-8"))
        entries = _decode_catalog(raw)
    except (UnicodeError, json.JSONDecodeError, ValueError) as exc:
        return None, {
            "state": "corrupt",
            "code": "REPOSITORY_CATALOG_INVALID",
            "details": {
                "catalog": str(catalog_path),
                "error": str(exc)[:500],
            },
        }
    if pending_path.exists() or pending_path.is_symlink():
        return None, {
            "state": "corrupt",
            "code": "REPOSITORY_CATALOG_MUTATION_INTERRUPTED",
            "details": {"pending": str(pending_path)},
        }
    return entries, None


def _read_store_without_catalog(
    store: IndexStore,
    *,
    max_store_entries: int,
) -> tuple[list[dict[str, Any]] | None, dict[str, Any] | None]:
    try:
        store_entries = list(islice(
            store.base_dir.iterdir(),
            max_store_entries + 1,
        ))
    except OSError as exc:
        return None, {
            "state": "unavailable",
            "code": "STORE_INVENTORY_READ_FAILED",
            "details": {
                "store": str(store.base_dir),
                "error": str(exc)[:500],
            },
        }
    if len(store_entries) > max_store_entries:
        return None, {
            "state": "unavailable",
            "code": "STORE_ENTRIES_LIMIT_EXCEEDED",
            "details": {
                "store": str(store.base_dir),
                "limit": max_store_entries,
                "observed": len(store_entries),
            },
        }
    symlinks = sorted(entry.name for entry in store_entries if entry.is_symlink())
    if symlinks:
        return None, {
            "state": "corrupt",
            "code": "STORE_ENTRY_SYMLINK",
            "details": {
                "store": str(store.base_dir),
                "entries": symlinks[:20],
                "omitted_entries": max(0, len(symlinks) - 20),
            },
        }
    legacy_keys = sorted(
        entry.name
        for entry in store_entries
        if not entry.is_symlink()
        and entry.is_dir()
        and (entry / "index.json").exists()
    )
    if legacy_keys:
        return None, {
            "state": "corrupt",
            "code": "REPOSITORY_CATALOG_MISSING",
            "details": {
                "catalog": str(store.base_dir / CATALOG_FILE_NAME),
                "cache_keys": legacy_keys[:20],
                "omitted_cache_keys": max(0, len(legacy_keys) - 20),
            },
        }
    return [], None


def _decode_catalog(raw: Any) -> list[dict[str, Any]]:
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
    return [
        entries[cache_key].to_dict()
        for cache_key in sorted(entries)
    ]


def _catalog_problem_result(
    diagnostic: dict[str, Any],
    *,
    offset: int,
    limit: int,
    bounds: dict[str, int],
) -> dict[str, Any]:
    status = "unhealthy" if diagnostic["state"] == "corrupt" else "incomplete"
    return {
        "schema_version": STORE_HEALTH_SCHEMA_VERSION,
        "status": status,
        "complete": False,
        "items": [],
        "counts": {
            "repositories": None,
            "returned": 0,
            **{state: 0 for state in _STATE_ORDER},
            "incomplete": int(diagnostic["state"] == "unavailable"),
        },
        "pagination": {
            "offset": offset,
            "limit": limit,
            "next_offset": None,
        },
        "bounds": bounds,
        "diagnostics": [diagnostic],
    }


def _overlap_reasons(
    entries: list[dict[str, Any]],
) -> dict[str, tuple[HealthReason, ...]]:
    entries_by_path = {
        Path(entry["path"]): entry
        for entry in entries
    }
    contains: dict[str, list[dict[str, str]]] = {
        entry["cache_key"]: []
        for entry in entries
    }
    contains_counts = {
        entry["cache_key"]: 0
        for entry in entries
    }
    inside: dict[str, list[dict[str, str]]] = {
        entry["cache_key"]: []
        for entry in entries
    }
    inside_counts = {
        entry["cache_key"]: 0
        for entry in entries
    }
    for descendant in entries:
        descendant_path = Path(descendant["path"])
        for parent_path in descendant_path.parents:
            ancestor = entries_by_path.get(parent_path)
            if ancestor is None:
                continue
            ancestor_key = ancestor["cache_key"]
            descendant_key = descendant["cache_key"]
            contains_counts[ancestor_key] += 1
            inside_counts[descendant_key] += 1
            if len(contains[ancestor_key]) < 20:
                contains[ancestor_key].append({
                    "cache_key": descendant_key,
                    "repo": descendant["path"],
                })
            if len(inside[descendant_key]) < 20:
                inside[descendant_key].append({
                    "cache_key": ancestor_key,
                    "repo": ancestor["path"],
                })

    result: dict[str, tuple[HealthReason, ...]] = {}
    for entry in entries:
        cache_key = entry["cache_key"]
        values: list[HealthReason] = []
        if contains[cache_key]:
            values.append(HealthReason(
                "overlapping",
                "REPOSITORY_ROOT_CONTAINS_INDEXED_ROOT",
                _bounded_overlap_details(
                    contains[cache_key],
                    total=contains_counts[cache_key],
                ),
            ))
        if inside[cache_key]:
            values.append(HealthReason(
                "overlapping",
                "REPOSITORY_ROOT_INSIDE_INDEXED_ROOT",
                _bounded_overlap_details(
                    inside[cache_key],
                    total=inside_counts[cache_key],
                ),
            ))
        result[cache_key] = tuple(values)
    return result


def _bounded_overlap_details(
    overlaps: list[dict[str, str]],
    *,
    total: int,
) -> dict[str, Any]:
    ordered = sorted(
        overlaps,
        key=lambda value: (value["repo"], value["cache_key"]),
    )
    return {
        "others": ordered,
        "omitted": max(0, total - len(ordered)),
    }


def _diagnose_repository(
    store: IndexStore,
    entry: dict[str, Any],
    *,
    overlap_reasons: tuple[HealthReason, ...],
    freshness_probe: FreshnessProbeFunction,
    max_index_bytes: int,
    max_probe_paths: int,
    max_probe_bytes: int,
) -> dict[str, Any]:
    reasons = list(overlap_reasons)
    repo_path, root_is_directory, root_reasons, root_probe = (
        _inspect_repository_root(entry)
    )
    reasons.extend(root_reasons)
    if root_probe is not None:
        return _repository_result(entry, reasons, root_probe, index_bytes=None)

    index, index_bytes, index_reasons, index_probe = _inspect_repository_index(
        store,
        entry,
        max_index_bytes=max_index_bytes,
    )
    reasons.extend(index_reasons)
    if index_probe is not None:
        return _repository_result(entry, reasons, index_probe, index_bytes=index_bytes)
    assert index is not None

    if not root_is_directory:
        return _repository_result(
            entry,
            reasons,
            FreshnessProbe.complete(),
            index_bytes=index_bytes,
        )
    try:
        probe = freshness_probe(
            repo_path,
            index,
            max_probe_paths,
            max_probe_bytes,
        )
    except Exception as exc:
        probe = FreshnessProbe.unavailable(
            "FRESHNESS_PROBE_FAILED",
            {
                "error_type": type(exc).__name__,
                "error": str(exc)[:500],
            },
        )
    reasons.extend(probe.reasons)
    return _repository_result(entry, reasons, probe, index_bytes=index_bytes)


def _inspect_repository_root(
    entry: dict[str, Any],
) -> tuple[Path, bool, tuple[HealthReason, ...], FreshnessProbe | None]:
    repo_path = Path(entry["path"])
    try:
        if repo_path.is_symlink():
            reason = HealthReason(
                "corrupt",
                "REPOSITORY_ROOT_SYMLINK",
                {"repo": entry["path"]},
            )
            return repo_path, False, (reason,), None
        if not stat.S_ISDIR(repo_path.stat().st_mode):
            reason = HealthReason(
                "missing",
                "REPOSITORY_ROOT_NOT_DIRECTORY",
                {"repo": entry["path"]},
            )
            return repo_path, False, (reason,), None
        return repo_path, True, (), None
    except FileNotFoundError:
        reason = HealthReason(
            "missing",
            "REPOSITORY_ROOT_MISSING",
            {"repo": entry["path"]},
        )
        return repo_path, False, (reason,), None
    except OSError as exc:
        probe = FreshnessProbe.unavailable(
            "REPOSITORY_ROOT_STAT_FAILED",
            {"repo": entry["path"], "error": str(exc)[:500]},
        )
        return repo_path, False, (), probe


def _inspect_repository_index(
    store: IndexStore,
    entry: dict[str, Any],
    *,
    max_index_bytes: int,
) -> tuple[
    dict[str, Any] | None,
    int | None,
    tuple[HealthReason, ...],
    FreshnessProbe | None,
]:
    index_path = store.base_dir / entry["cache_key"] / "index.json"
    index, index_bytes, problem = _read_index(
        index_path,
        max_index_bytes=max_index_bytes,
    )
    if isinstance(problem, ProbeUnavailableReason):
        probe = FreshnessProbe(
            status="unavailable",
            unavailable_reason=problem,
        )
        return None, index_bytes, (), probe
    if isinstance(problem, HealthReason):
        return None, index_bytes, (problem,), FreshnessProbe.complete()
    assert index is not None

    structural_problem = _validate_index_structure(entry, index)
    if structural_problem is not None:
        return (
            None,
            index_bytes,
            (structural_problem,),
            FreshnessProbe.complete(),
        )
    if not index_versions_current(index):
        reason = HealthReason(
            "stale",
            "INDEX_VERSION_OUTDATED",
            {
                "schema_version": index.get("schema_version"),
                "extractor_version": index.get("extractor_version"),
            },
        )
        return None, index_bytes, (reason,), FreshnessProbe.complete()
    return index, index_bytes, (), None


def _read_index(
    index_path: Path,
    *,
    max_index_bytes: int,
) -> tuple[
    dict[str, Any] | None,
    int | None,
    HealthReason | ProbeUnavailableReason | None,
]:
    if index_path.parent.is_symlink():
        return None, None, HealthReason(
            "corrupt",
            "INDEX_DIRECTORY_SYMLINK",
            {"directory": str(index_path.parent)},
        )
    if index_path.is_symlink():
        return None, None, HealthReason(
            "corrupt",
            "INDEX_SYMLINK",
            {"index": str(index_path)},
        )
    try:
        with index_path.open("rb") as handle:
            payload = handle.read(max_index_bytes + 1)
    except FileNotFoundError:
        return None, None, HealthReason(
            "corrupt",
            "INDEX_MISSING",
            {"index": str(index_path)},
        )
    except (IsADirectoryError, PermissionError, OSError) as exc:
        return None, None, HealthReason(
            "corrupt",
            "INDEX_UNREADABLE",
            {
                "index": str(index_path),
                "error": str(exc)[:500],
            },
        )
    index_bytes = len(payload)
    if index_bytes > max_index_bytes:
        return None, index_bytes, ProbeUnavailableReason(
            "INDEX_BYTES_LIMIT_EXCEEDED",
            {
                "index": str(index_path),
                "limit": max_index_bytes,
                "observed": index_bytes,
            },
        )
    try:
        decoded = json.loads(payload.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        return None, index_bytes, HealthReason(
            "corrupt",
            "INDEX_JSON_INVALID",
            {
                "index": str(index_path),
                "error": str(exc)[:500],
            },
        )
    if not isinstance(decoded, dict):
        return None, index_bytes, HealthReason(
            "corrupt",
            "INDEX_ROOT_INVALID",
            {"index": str(index_path)},
        )
    return decoded, index_bytes, None


def _validate_index_structure(
    entry: dict[str, Any],
    index: dict[str, Any],
) -> HealthReason | None:
    if index.get("repo_path") != entry["path"]:
        return HealthReason(
            "corrupt",
            "INDEX_REPOSITORY_MISMATCH",
            {
                "catalog_repo": entry["path"],
                "index_repo": index.get("repo_path"),
            },
        )
    symbols = index.get("symbols")
    if not isinstance(symbols, list):
        return HealthReason(
            "corrupt",
            "INDEX_SYMBOLS_INVALID",
            {"actual_type": type(symbols).__name__},
        )
    if len(symbols) != entry["symbols"]:
        return HealthReason(
            "corrupt",
            "CATALOG_SYMBOL_COUNT_MISMATCH",
            {
                "catalog_symbols": entry["symbols"],
                "index_symbols": len(symbols),
            },
        )
    if not index_versions_current(index):
        return None
    file_hashes = index.get("file_hashes")
    if not isinstance(file_hashes, Mapping) or any(
        not isinstance(path, str) or not isinstance(content_hash, str)
        for path, content_hash in file_hashes.items()
    ):
        return HealthReason(
            "corrupt",
            "INDEX_FILE_HASHES_INVALID",
            {},
        )
    return None


def _repository_result(
    entry: dict[str, Any],
    reasons: list[HealthReason],
    probe: FreshnessProbe,
    *,
    index_bytes: int | None,
) -> dict[str, Any]:
    if not reasons and probe.status == "complete":
        reasons = [HealthReason("healthy", "INDEX_CURRENT")]
    states = [
        state
        for state in _STATE_ORDER
        if any(reason.state == state for reason in reasons)
    ]
    return {
        "cache_key": entry["cache_key"],
        "repo": entry["path"],
        "symbols": entry["symbols"],
        "states": states,
        "reasons": [reason.to_dict() for reason in reasons],
        "probe": probe.to_dict(index_bytes=index_bytes),
    }
