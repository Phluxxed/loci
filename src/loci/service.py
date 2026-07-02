from __future__ import annotations

import os
import time
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pathspec

from loci.parser.extractor import parse_file
from loci.parser.languages import EXTENSION_MAP, MARKDOWN_SUFFIXES
from loci.parser.symbols import Symbol
from loci.storage.index_store import IndexStore
from loci.storage.store_resolver import StoreResolution, resolve_store_base_dir

SKIP_DIRS = {
    ".git", "node_modules", "__pycache__", ".venv", "venv",
    ".tox", "dist", "build", ".mypy_cache", ".pytest_cache",
    ".ruff_cache", ".uv-cache", "uv-cache", "__tests__", "tests",
}
TEST_FILE_SUFFIXES = (
    ".test.ts", ".test.tsx", ".test.js", ".test.jsx",
    ".spec.ts", ".spec.tsx", ".spec.js", ".spec.jsx",
)
SKIP_FILES = {".env", ".env.local", "credentials.json", "secrets.json"}
SKIP_EXTENSIONS = {
    ".pyc", ".pyo", ".so", ".dylib", ".dll", ".exe",
    ".bin", ".pem", ".key", ".p12",
}
REFRESH_LOCK_POLL_SECONDS = 0.05


@dataclass
class LociError(Exception):
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


def get_store() -> IndexStore:
    return _get_store_with_resolution()[0]


def get_store_resolution() -> StoreResolution:
    return resolve_store_base_dir()


def _get_store_with_resolution() -> tuple[IndexStore, StoreResolution]:
    resolution = resolve_store_base_dir()
    return IndexStore(base_dir=resolution.base_dir), resolution


def index_repo(path: str | Path, incremental: bool = True) -> dict[str, Any]:
    repo_path = Path(path).resolve()
    if not repo_path.exists():
        raise LociError(
            "PATH_NOT_FOUND",
            "Path not found",
            {"path": str(repo_path)},
        )
    if not repo_path.is_dir():
        raise LociError(
            "INVALID_INPUT",
            "Path is not a directory",
            {"path": str(repo_path)},
        )

    store = get_store()
    existing = store.load(repo_path) if incremental else None
    existing_hashes: dict[str, str] = existing.get("file_hashes", {}) if existing else {}
    existing_symbols: list[dict[str, Any]] = existing.get("symbols", []) if existing else []

    all_symbols: list[Symbol] = []
    new_file_hashes: dict[str, str] = {}
    files_skipped = 0
    language_counts: dict[str, int] = defaultdict(int)
    zero_symbol_warnings: list[dict[str, Any]] = []

    for src_file, rel_path, file_hash in _iter_indexable_files(repo_path, store):
        new_file_hashes[rel_path] = file_hash

        if incremental and existing_hashes.get(rel_path) == file_hash:
            kept = [Symbol.from_dict(s) for s in existing_symbols if s["file_path"] == rel_path]
            all_symbols.extend(kept)
            files_skipped += 1
            lang = EXTENSION_MAP.get(src_file.suffix, "unknown")
            language_counts[lang] += 1
            continue

        symbols = parse_file(src_file)
        for sym in symbols:
            sym.file_path = rel_path
            sym.id = f"{rel_path}::{sym.qualified_name}#{sym.kind}"
        all_symbols.extend(symbols)
        lang = EXTENSION_MAP.get(src_file.suffix, "unknown")
        if symbols:
            language_counts[lang] += 1
        else:
            try:
                file_bytes = src_file.read_bytes()
            except OSError:
                file_bytes = b""
            line_count = len(file_bytes.splitlines())
            is_nonempty_markdown = (
                src_file.suffix.lower() in MARKDOWN_SUFFIXES
                and bool(file_bytes.strip())
            )
            if line_count > 10 or is_nonempty_markdown:
                zero_symbol_warnings.append({
                    "file": rel_path,
                    "lines": line_count,
                    "reason": "0 symbols extracted",
                })

    store.write(repo_path, all_symbols, file_hashes=new_file_hashes)

    output: dict[str, Any] = {
        "path": str(repo_path),
        "symbols_indexed": len(all_symbols),
        "files_skipped": files_skipped,
        "languages": dict(language_counts),
    }
    if zero_symbol_warnings:
        output["warnings"] = zero_symbol_warnings
    return output


def ensure_fresh_index(repo: str | Path) -> dict[str, Any]:
    repo_path = Path(repo).resolve()
    store = get_store()
    index = _load_required_index(store, repo_path)
    _validate_repo_path(repo_path)
    if not _index_is_stale(repo_path, store, index):
        return {"repo": str(repo_path), "refreshed": False}

    lock_path = store.refresh_lock_path(repo_path)
    timeout = float(os.environ.get("LOCI_REFRESH_LOCK_TIMEOUT", "10"))
    _acquire_refresh_lock(lock_path, timeout=timeout)
    try:
        index = _load_required_index(store, repo_path)
        if not _index_is_stale(repo_path, store, index):
            return {"repo": str(repo_path), "refreshed": False}
        result = index_repo(repo_path, incremental=True)
        return {"repo": str(repo_path), "refreshed": True, "index": result}
    except LociError:
        raise
    except Exception as exc:
        raise LociError(
            "STALE_INDEX_REFRESH_FAILED",
            "Failed to refresh stale index",
            {"repo": str(repo_path), "error": str(exc)},
        ) from exc
    finally:
        lock_path.unlink(missing_ok=True)


def outline_repo(
    path: str | Path,
    file: str | None = None,
    ensure_fresh: bool = False,
) -> list[dict[str, Any]]:
    repo_path = Path(path).resolve()
    store = get_store()
    if ensure_fresh:
        ensure_fresh_index(repo_path)
    index = _load_required_index(store, repo_path)

    grouped: dict[str, list[dict[str, Any]]] = {}
    languages: set[str] = set()
    for symbol in index["symbols"]:
        file_path = symbol["file_path"]
        if file and file_path != file:
            continue
        entry: dict[str, Any] = {
            "id": symbol.get("id", ""),
            "name": symbol.get("name", ""),
            "kind": symbol.get("kind", ""),
            "line": symbol.get("line", 0),
            "end_line": symbol.get("end_line", 0),
            "signature": symbol.get("signature", ""),
            "summary": symbol.get("summary", ""),
        }
        if symbol.get("decorators"):
            entry["decorators"] = symbol["decorators"]
        grouped.setdefault(file_path, []).append(entry)
        if symbol.get("language"):
            languages.add(symbol["language"])

    result = [{"file": fp, "symbols": symbols} for fp, symbols in sorted(grouped.items())]
    symbol_count = sum(len(symbols) for symbols in grouped.values())
    store.log_outline(
        str(repo_path),
        symbol_count,
        file_filter=file,
        languages=sorted(languages),
    )
    return result


def get_symbols(
    repo: str | Path,
    symbol_ids: list[str],
    context: int = 0,
    ensure_fresh: bool = False,
) -> list[dict[str, Any]]:
    repo_path = Path(repo).resolve()
    if not symbol_ids:
        raise LociError(
            "INVALID_INPUT",
            "At least one symbol id is required",
            {"repo": str(repo_path)},
        )
    if context < 0:
        raise LociError(
            "INVALID_INPUT",
            "Context must be greater than or equal to 0",
            {"context": context},
        )

    store = get_store()
    if ensure_fresh:
        ensure_fresh_index(repo_path)
    index = _load_required_index(store, repo_path)

    return [_get_symbol(repo_path, store, index, symbol_id, context) for symbol_id in symbol_ids]


def search_symbols(
    repo: str | Path,
    query: str,
    kind: str | None = None,
    lang: str | None = None,
    limit: int = 20,
    ensure_fresh: bool = False,
) -> list[dict[str, Any]]:
    repo_path = Path(repo).resolve()
    if limit < 1:
        raise LociError(
            "INVALID_INPUT",
            "Limit must be greater than 0",
            {"limit": limit},
        )

    store = get_store()
    if ensure_fresh:
        ensure_fresh_index(repo_path)
    _load_required_index(store, repo_path)

    results = store.search(repo_path, query, kind=kind, lang=lang, limit=limit)
    if results:
        search_id = str(uuid.uuid4())
        store.log_search(search_id, query, str(repo_path), [result["id"] for result in results])
    else:
        store.log_miss("search_empty", repo_path=str(repo_path), query=query)
    return results


def get_cached_file(
    repo: str | Path,
    file_path: str,
    start_line: int | None = None,
    end_line: int | None = None,
    ensure_fresh: bool = False,
) -> dict[str, Any]:
    repo_path = Path(repo).resolve()
    store = get_store()
    if ensure_fresh:
        ensure_fresh_index(repo_path)
    _load_required_index(store, repo_path)

    result = store.get_file_content(
        repo_path,
        file_path,
        start_line=start_line,
        end_line=end_line,
    )
    if result is None:
        raise LociError(
            "FILE_NOT_FOUND",
            "File not found in cache",
            {"repo": str(repo_path), "file": file_path},
        )

    symbol_bytes = len(result["content"].encode("utf-8"))
    file_bytes = result.pop("file_bytes")
    language = EXTENSION_MAP.get(Path(file_path).suffix)
    store.log_retrieval(
        file_path,
        symbol_bytes,
        file_bytes,
        repo_path=str(repo_path),
        language=language,
    )
    return result


def grep_repo(
    repo: str | Path,
    pattern: str,
    ensure_fresh: bool = False,
) -> list[dict[str, Any]]:
    repo_path = Path(repo).resolve()
    store = get_store()
    if ensure_fresh:
        ensure_fresh_index(repo_path)
    _load_required_index(store, repo_path)

    try:
        return store.grep_files(repo_path, pattern)
    except ValueError as exc:
        raise LociError(
            "INVALID_REGEX",
            str(exc),
            {"repo": str(repo_path), "pattern": pattern},
        ) from exc


def verify_repo(path: str | Path) -> dict[str, Any]:
    repo_path = Path(path).resolve()
    store = get_store()
    result = store.verify_index(repo_path)
    if "error" in result:
        raise LociError(
            "REPO_NOT_INDEXED",
            "Repository is not indexed",
            {"repo": str(repo_path)},
        )
    return result


def list_repos() -> list[dict[str, Any]]:
    return get_store().list_repos()


def session_stats(
    repo: str | Path | None = None,
    since_days: int | None = 7,
) -> dict[str, Any]:
    if since_days is not None and since_days < 0:
        raise LociError(
            "INVALID_INPUT",
            "since_days must be greater than or equal to 0",
            {"since_days": since_days},
        )

    store, resolution = _get_store_with_resolution()
    repo_filter = str(Path(repo).resolve()) if repo else None
    stats = store.get_session_stats(repo_filter=repo_filter, since_days=since_days)
    stats["store"] = resolution.to_dict()
    return stats


def reset_session_stats() -> dict[str, Any]:
    store, resolution = _get_store_with_resolution()
    backup = store.reset_session()
    return {
        "reset": True,
        "backup": str(backup) if backup is not None else None,
        "store": resolution.to_dict(),
    }


def analyze_usage(
    repo: str | Path | None = None,
    since_days: int = 30,
) -> dict[str, Any]:
    if since_days < 0:
        raise LociError(
            "INVALID_INPUT",
            "since_days must be greater than or equal to 0",
            {"since_days": since_days},
        )

    store, resolution = _get_store_with_resolution()
    repo_filter = str(Path(repo).resolve()) if repo else None
    result = store.analyze(since_days=since_days, repo_filter=repo_filter)
    result["store"] = resolution.to_dict()
    return result


def _validate_repo_path(repo_path: Path) -> None:
    if not repo_path.exists():
        raise LociError(
            "PATH_NOT_FOUND",
            "Path not found",
            {"path": str(repo_path)},
        )
    if not repo_path.is_dir():
        raise LociError(
            "INVALID_INPUT",
            "Path is not a directory",
            {"path": str(repo_path)},
        )


def _load_required_index(store: IndexStore, repo_path: Path) -> dict[str, Any]:
    index = store.load(repo_path)
    if index is None:
        raise LociError(
            "REPO_NOT_INDEXED",
            "Repository is not indexed",
            {"repo": str(repo_path)},
        )
    return index


def _index_is_stale(repo_path: Path, store: IndexStore, index: dict[str, Any]) -> bool:
    current_hashes = {
        rel_path: file_hash
        for _, rel_path, file_hash in _iter_indexable_files(repo_path, store)
    }
    indexed_hashes = index.get("file_hashes", {})
    return current_hashes != indexed_hashes


def _acquire_refresh_lock(lock_path: Path, timeout: float) -> None:
    deadline = time.monotonic() + timeout
    while True:
        try:
            fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            if time.monotonic() >= deadline:
                raise LociError(
                    "STALE_INDEX_REFRESH_FAILED",
                    "Timed out waiting for stale index refresh lock",
                    {"lock": str(lock_path), "timeout_seconds": timeout},
                )
            time.sleep(REFRESH_LOCK_POLL_SECONDS)
            continue
        with os.fdopen(fd, "w") as f:
            f.write(str(os.getpid()))
        return


def _iter_indexable_files(
    repo_path: Path,
    store: IndexStore,
) -> list[tuple[Path, str, str]]:
    gitignore = _load_gitignore(repo_path)
    files: list[tuple[Path, str, str]] = []
    for src_file in sorted(repo_path.rglob("*")):
        if not src_file.is_file():
            continue
        if any(part in SKIP_DIRS for part in src_file.parts):
            continue
        if _should_skip_file(src_file):
            continue

        rel_path = str(src_file.relative_to(repo_path))
        if gitignore and gitignore.match_file(rel_path):
            continue
        files.append((src_file, rel_path, store.hash_file(src_file)))
    return files


def _get_symbol(
    repo_path: Path,
    store: IndexStore,
    index: dict[str, Any],
    symbol_id: str,
    context: int,
) -> dict[str, Any]:
    meta = next((s for s in index["symbols"] if s["id"] == symbol_id), None)
    if meta is None:
        store.log_miss("get_not_found", repo_path=str(repo_path), symbol_id=symbol_id)
        raise LociError(
            "SYMBOL_NOT_FOUND",
            "Symbol not found",
            {"repo": str(repo_path), "symbol_id": symbol_id},
        )

    content = store.get_symbol_content(repo_path, symbol_id)
    if content is None:
        store.log_miss("get_not_found", repo_path=str(repo_path), symbol_id=symbol_id)
        raise LociError(
            "SYMBOL_NOT_FOUND",
            "Symbol source not found",
            {"repo": str(repo_path), "symbol_id": symbol_id},
        )

    symbol_bytes = len(content.encode("utf-8"))
    file_bytes = store.get_symbol_file_size(repo_path, symbol_id)
    if file_bytes is not None:
        search_id, search_rank = store.resolve_search_correlation(symbol_id, repo=str(repo_path))
        store.log_retrieval(
            symbol_id,
            symbol_bytes,
            file_bytes,
            repo_path=str(repo_path),
            kind=meta.get("kind"),
            language=meta.get("language"),
            search_id=search_id,
            search_rank=search_rank,
        )

    result: dict[str, Any] = {
        "id": symbol_id,
        "source": content,
        **{
            key: meta.get(key)
            for key in (
                "byte_offset",
                "byte_length",
                "line",
                "end_line",
                "signature",
                "kind",
                "language",
            )
        },
    }
    if meta.get("decorators"):
        result["decorators"] = meta["decorators"]
    if context > 0:
        symbol_context = store.get_symbol_context(repo_path, symbol_id, context)
        if symbol_context:
            result["context_before"] = symbol_context["context_before"]
            result["context_after"] = symbol_context["context_after"]
    return result


def _load_gitignore(repo_path: Path) -> "pathspec.PathSpec | None":
    gitignore = repo_path / ".gitignore"
    if not gitignore.exists():
        return None
    lines = gitignore.read_text(encoding="utf-8", errors="replace").splitlines()
    return pathspec.PathSpec.from_lines("gitwildmatch", lines)


def _should_skip_file(path: Path) -> bool:
    if path.name in SKIP_FILES:
        return True
    if path.suffix in SKIP_EXTENSIONS:
        return True
    if path.suffix not in EXTENSION_MAP:
        return True
    name = path.name
    if name.startswith("test_") or name.endswith("_test.py") or name.endswith("_test.go"):
        return True
    if any(name.endswith(suffix) for suffix in TEST_FILE_SUFFIXES):
        return True
    return False
