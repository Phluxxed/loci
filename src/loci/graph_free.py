"""File-only source acquisition for the isolated graph-free architecture arm.

The store contains an inventory of text files and their hashes. Search reads
current source; no parser, symbol table, or relationship state is involved.
"""
from __future__ import annotations

import base64
import hashlib
import json
import math
import os
from pathlib import Path, PurePosixPath
import re
import stat
import subprocess
from typing import Any


MAX_FILES = 4096
MAX_FILE_BYTES = 2 * 1024 * 1024
MAX_SCAN_BYTES = 64 * 1024 * 1024
MAX_RESULTS = 3
MAX_PREVIEW_BYTES = 1024
MAX_READ_BYTES = 8192
MAX_OUTPUT_BYTES = 16384
_SKIP_DIRS = frozenset({
    ".git", ".venv", "venv", "node_modules", "__pycache__", ".pytest_cache",
    ".mypy_cache", ".ruff_cache", "build", "dist", "target", "vendor",
})
_SKIP_NAMES = frozenset({".env", ".env.local", "credentials.json", "secrets.json"})
_SKIP_SUFFIXES = frozenset({".key", ".pem", ".p12", ".pyc", ".pyo"})
_STOPWORDS = frozenset({
    "a", "an", "and", "are", "by", "does", "for", "from", "how", "in", "is",
    "of", "on", "or", "the", "to", "what", "where", "which", "with",
})


class GraphFreeError(Exception):
    def __init__(self, code: str, message: str, details: dict[str, Any] | None = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details or {}


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, ensure_ascii=False,
                      separators=(",", ":")).encode("utf-8")


def _repo(path: str | Path) -> Path:
    root = Path(path).resolve(strict=True)
    if not root.is_dir():
        raise GraphFreeError("INVALID_REPOSITORY", "Repository root is not a directory")
    return root


def _relative(value: str) -> bool:
    if not value or "\\" in value or "\x00" in value:
        return False
    path = PurePosixPath(value)
    return not path.is_absolute() and ".." not in path.parts and path.as_posix() == value


def _source_bytes(root: Path, relative: str, limit: int = MAX_FILE_BYTES) -> bytes:
    """Open every path component without following a symlink, then bound the read."""
    if not _relative(relative):
        raise GraphFreeError("SOURCE_UNAVAILABLE", "Source path is not repository-relative")
    fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY)
    try:
        parts = PurePosixPath(relative).parts
        for part in parts[:-1]:
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd)
            fd = child
        source_fd = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=fd)
        try:
            info = os.fstat(source_fd)
            if not stat.S_ISREG(info.st_mode) or info.st_size > limit:
                raise GraphFreeError("SOURCE_UNAVAILABLE", "Source is not a bounded regular file")
            chunks: list[bytes] = []
            length = 0
            while True:
                chunk = os.read(source_fd, min(65536, limit + 1 - length))
                if not chunk:
                    return b"".join(chunks)
                chunks.append(chunk)
                length += len(chunk)
                if length > limit:
                    raise GraphFreeError("SOURCE_UNAVAILABLE", "Source exceeds the file byte limit")
        finally:
            os.close(source_fd)
    except OSError as exc:
        raise GraphFreeError("SOURCE_UNAVAILABLE", "Source cannot be read", {"file": relative}) from exc
    finally:
        os.close(fd)


def _candidates(root: Path) -> list[str]:
    probe = subprocess.run(
        ["git", "-C", str(root), "rev-parse", "--show-toplevel"],
        capture_output=True, text=True, check=False,
    )
    if probe.returncode == 0 and Path(probe.stdout.strip()).resolve() == root:
        result = subprocess.run(
            ["git", "-C", str(root), "ls-files", "--cached", "--others",
             "--exclude-standard", "-z"],
            capture_output=True, check=True,
        )
        paths = sorted(set(os.fsdecode(path) for path in result.stdout.split(b"\x00") if path))
        if not paths:
            return []
        # Git lists tracked paths even after an ignore rule is added. The
        # acquisition policy applies the current ignore rules to both kinds.
        ignored_result = subprocess.run(
            ["git", "-C", str(root), "check-ignore", "--no-index", "-z", "--stdin"],
            input=b"\x00".join(os.fsencode(path) for path in paths) + b"\x00",
            capture_output=True, check=False,
        )
        if ignored_result.returncode not in (0, 1):
            raise GraphFreeError("INVENTORY_UNAVAILABLE", "Git ignore check failed")
        ignored = {os.fsdecode(path) for path in ignored_result.stdout.split(b"\x00") if path}
        return [path for path in paths if path not in ignored]

    # A plain directory is useful for small fixtures. Match its root ignore
    # rules; Git repositories above use Git itself, including nested rules.
    import pathspec

    ignore_path = root / ".gitignore"
    rules = pathspec.PathSpec.from_lines(
        "gitwildmatch",
        ignore_path.read_text(encoding="utf-8", errors="replace").splitlines()
        if ignore_path.is_file() else [],
    )
    result: list[str] = []
    for directory, dirs, files in os.walk(root, followlinks=False):
        base = Path(directory)
        dirs[:] = sorted(d for d in dirs if d not in _SKIP_DIRS
                         and not rules.match_file((base / d).relative_to(root).as_posix() + "/"))
        result.extend((base / name).relative_to(root).as_posix() for name in files)
    return sorted(path for path in result if not rules.match_file(path))


def _skipped(path: str) -> bool:
    relative = PurePosixPath(path)
    return (not _relative(path) or any(part in _SKIP_DIRS for part in relative.parts[:-1])
            or relative.name in _SKIP_NAMES or relative.suffix.lower() in _SKIP_SUFFIXES)


def _reference(root: Path, file: str, digest: str, end: int, offset: int = 0) -> str:
    value = {"v": 1, "repo": str(root), "file": file, "hash": digest,
             "start": 0, "end": end, "offset": offset}
    return base64.urlsafe_b64encode(_canonical(value)).decode("ascii").rstrip("=")


def _decode_reference(root: Path, reference: str) -> dict[str, Any]:
    if not isinstance(reference, str) or not reference or len(reference) > 16384:
        raise GraphFreeError("INVALID_SOURCE_REF", "Source reference is invalid")
    try:
        raw = base64.b64decode(reference + "=" * (-len(reference) % 4),
                               altchars=b"-_", validate=True)
        value = json.loads(raw)
    except (ValueError, UnicodeError) as exc:
        raise GraphFreeError("INVALID_SOURCE_REF", "Source reference is invalid") from exc
    if (not isinstance(value, dict) or set(value) !=
            {"v", "repo", "file", "hash", "start", "end", "offset"}
            or type(value["v"]) is not int or value["v"] != 1
            or value["repo"] != str(root)
            or not isinstance(value["file"], str) or not _relative(value["file"])
            or not isinstance(value["hash"], str)
            or re.fullmatch(r"[0-9a-f]{64}", value["hash"]) is None
            or any(type(value[key]) is not int for key in ("start", "end", "offset"))
            or not 0 <= value["start"] <= value["offset"] <= value["end"]
            or value["start"] != 0 or _reference(root, value["file"], value["hash"],
                                                   value["end"], value["offset"]) != reference):
        raise GraphFreeError("INVALID_SOURCE_REF", "Source reference fields are invalid")
    return value


def _account(packet: dict[str, Any], evidence_bytes: int) -> dict[str, Any]:
    usage = packet["usage"]
    usage["evidence_bytes"] = evidence_bytes
    usage["output_encoding"] = "mcp_result_json_utf8"
    for _ in range(16):
        size = len(_canonical({"content": [], "structuredContent": packet,
                               "isError": False}))
        tokens = math.ceil(size / 4)
        if (usage.get("output_bytes") == size
                and ("estimated_tokens" not in usage or usage["estimated_tokens"] == tokens)):
            return packet
        usage["output_bytes"] = size
        if "estimated_tokens" in usage:
            usage["estimated_tokens"] = tokens
    raise RuntimeError("Graph-free output accounting did not converge")


def _line_number(raw: bytes, offset: int) -> int:
    return raw[:offset].count(b"\n") + 1


def _source(root: Path, file: str, digest: str, raw: bytes,
            start: int, end: int, source_id: int) -> dict[str, Any]:
    content = raw[start:end].decode("utf-8")
    start_line = _line_number(raw, start)
    return {"id": source_id, "file": file, "start_byte": start, "end_byte": end,
            "start_line": start_line,
            "end_line": max(start_line, start_line + content.count("\n")
                            - int(content.endswith("\n"))),
            "content_hash": digest, "content": content,
            "source_ref": _reference(root, file, digest, len(raw), start)}


def _preview(raw: bytes, hit: int) -> tuple[int, int]:
    if len(raw) <= MAX_PREVIEW_BYTES:
        return 0, len(raw)
    line_start = raw.rfind(b"\n", 0, hit) + 1
    line_end = raw.find(b"\n", hit)
    if line_end < 0:
        line_end = len(raw)
    else:
        line_end += 1
    if line_end - line_start > MAX_PREVIEW_BYTES:
        start = max(line_start, hit - MAX_PREVIEW_BYTES // 4)
        end = min(line_end, start + MAX_PREVIEW_BYTES)
    else:
        start, end = line_start, line_end
    while start < end and raw[start] & 0xC0 == 0x80:
        start += 1
    while end > start and end < len(raw) and raw[end] & 0xC0 == 0x80:
        end -= 1
    return start, end


class GraphFreeSource:
    """An isolated inventory plus current-source search and exact reads."""

    def __init__(self, store: Path):
        self.store = Path(store)

    def _index_path(self, root: Path) -> Path:
        return self.store / (hashlib.sha256(str(root).encode()).hexdigest() + ".json")

    def index_repo(self, repo: str | Path) -> dict[str, Any]:
        root = _repo(repo)
        candidates = _candidates(root)
        files: dict[str, str] = {}
        omitted: dict[str, int] = {}
        bytes_scanned = 0
        for relative in candidates:
            if _skipped(relative):
                omitted["policy_excluded"] = omitted.get("policy_excluded", 0) + 1
                continue
            if len(files) >= MAX_FILES:
                omitted["file_limit"] = omitted.get("file_limit", 0) + 1
                continue
            if bytes_scanned >= MAX_SCAN_BYTES:
                omitted["scan_budget"] = omitted.get("scan_budget", 0) + 1
                continue
            try:
                raw = _source_bytes(root, relative)
            except GraphFreeError:
                omitted["source_unavailable"] = omitted.get("source_unavailable", 0) + 1
                continue
            bytes_scanned += len(raw)
            if bytes_scanned > MAX_SCAN_BYTES:
                omitted["scan_budget"] = omitted.get("scan_budget", 0) + 1
                continue
            try:
                if b"\x00" in raw:
                    raise UnicodeError("binary source")
                raw.decode("utf-8")
            except UnicodeError:
                omitted["non_text"] = omitted.get("non_text", 0) + 1
                continue
            files[relative] = hashlib.sha256(raw).hexdigest()
        payload = {"schema_version": 1, "repo_path": str(root),
                   "file_hashes": files, "omissions": omitted}
        payload["snapshot"] = hashlib.sha256(_canonical(payload)).hexdigest()
        self.store.mkdir(parents=True, exist_ok=True)
        index_path = self._index_path(root)
        temporary = index_path.with_name(index_path.name + f".{os.getpid()}.tmp")
        temporary.write_bytes(_canonical(payload))
        temporary.replace(index_path)
        return {"files_indexed": len(files), "paths_scanned": len(candidates),
                "bytes_scanned": bytes_scanned, "omissions": omitted,
                "snapshot": payload["snapshot"], "index_path": str(index_path)}

    def inventory(self, repo: str | Path) -> dict[str, Any]:
        root = _repo(repo)
        try:
            value = json.loads(self._index_path(root).read_bytes())
        except (OSError, ValueError) as exc:
            raise GraphFreeError("INDEX_UNAVAILABLE", "Graph-free inventory is unavailable") from exc
        if (not isinstance(value, dict) or value.get("repo_path") != str(root)
                or value.get("schema_version") != 1
                or set(value) != {"schema_version", "repo_path", "file_hashes",
                                  "omissions", "snapshot"}
                or not isinstance(value.get("file_hashes"), dict)
                or not all(_relative(path) and isinstance(digest, str)
                           and re.fullmatch(r"[0-9a-f]{64}", digest)
                           for path, digest in value["file_hashes"].items())
                or value["snapshot"] != hashlib.sha256(_canonical({
                    key: value[key] for key in value if key != "snapshot"
                })).hexdigest()):
            raise GraphFreeError("INDEX_UNAVAILABLE", "Graph-free inventory is invalid")
        return value

    def retrieve(self, repo: str | Path, query: str, **_ignored: Any) -> dict[str, Any]:
        root = _repo(repo)
        if not isinstance(query, str) or not query.strip() or len(query) > 1024:
            raise GraphFreeError("INVALID_QUERY", "Query must be nonempty and at most 1024 characters")
        # Refresh every search so a changed file cannot be silently served from
        # an old inventory. This work is intentionally measured by the harness.
        stats = self.index_repo(root)
        inventory = self.inventory(root)
        hashes = inventory["file_hashes"]
        query = query.strip()
        exact = query in hashes
        terms = list(dict.fromkeys(t for t in re.findall(r"\w+", query, re.UNICODE)
                                  if len(t) > 1 and t.casefold() not in _STOPWORDS))
        matches: list[tuple[int, str, int, bytes, str]] = []
        lookup_bytes = 0
        lookup_files = 0
        stale = 0
        for file, digest in hashes.items():
            if exact and file != query:
                continue
            try:
                raw = _source_bytes(root, file)
            except GraphFreeError:
                stale += 1
                continue
            lookup_bytes += len(raw)
            lookup_files += 1
            if hashlib.sha256(raw).hexdigest() != digest:
                stale += 1
                continue
            content = raw.decode("utf-8")
            if exact:
                matches.append((1000, file, 0, raw, "exact_file"))
                break
            literal = re.search(re.escape(query), content, re.IGNORECASE)
            found = [re.search(re.escape(term), content, re.IGNORECASE) for term in terms]
            path_hits = sum(term.casefold() in file.casefold() for term in terms)
            if literal is None and not any(found) and not path_hits:
                continue
            hit = literal or next((m for m in found if m is not None), None)
            offset = len(content[:hit.start()].encode("utf-8")) if hit else 0
            score = (100 if literal else 0) + 10 * sum(m is not None for m in found) + 5 * path_hits
            matches.append((score, file, offset, raw, "source_literal" if literal else "source_token"))
        matches.sort(key=lambda item: (-item[0], item[1]))
        chosen = matches[:MAX_RESULTS]
        sources: list[dict[str, Any]] = []
        items: list[dict[str, Any]] = []
        for _, file, hit, raw, reason in chosen:
            digest = hashes[file]
            start, end = _preview(raw, hit)
            sid = len(sources) + 1
            source = _source(root, file, digest, raw, start, end, sid)
            sources.append(source)
            ref = _reference(root, file, digest, len(raw))
            node_id = file + "::__file__#file"
            complete = start == 0 and end == len(raw)
            items.append({"node_id": node_id, "role": "anchor", "depth": 0,
                          "why": reason, "source_ids": [sid], "complete": complete,
                          "extent": {"file": file, "content_hash": digest,
                                     "start_byte": 0, "end_byte": len(raw)},
                          "source_ref": ref})
        omissions = [{"reason": reason, "count": count} for reason, count in
                     sorted(stats["omissions"].items())]
        if stale:
            omissions.append({"reason": "source_stale", "count": stale})
        if len(matches) > MAX_RESULTS:
            omissions.append({"reason": "anchor_limit", "count": len(matches) - MAX_RESULTS})
        previews = sum(not item["complete"] for item in items)
        if previews:
            omissions.append({"reason": "source_preview", "count": previews})
        if not matches:
            omissions.append({"reason": "no_anchor", "count": 1})
        omissions.append({"reason": "unsupported_semantics", "count": 1})
        packet = {"schema_version": 1, "policy": "graph-free-file-v1",
                  "snapshot": inventory["snapshot"],
                  "status": "empty" if not items else "partial" if omissions else "ok",
                  "scope": {"coverage": "partial" if stats["omissions"] or stale else "complete",
                            "exhaustive": False,
                            "matching": "exact_file" if exact else
                            "source_literal" if any(m[4] == "source_literal" for m in chosen)
                            else "source_token",
                            "source": "text_repository_files", "relationships": "unsupported"},
                  "selection": {"mode": "file" if exact else "literal",
                                "candidate_count": len(matches),
                                "omitted_candidates": max(0, len(matches) - len(chosen))},
                  "anchors": [], "items": items, "sources": sources,
                  "nodes": [],
                  "ownership": [], "relationships": [], "omissions": omissions,
                  "limits": {"max_files": MAX_FILES, "max_file_bytes": MAX_FILE_BYTES,
                             "max_scan_bytes": MAX_SCAN_BYTES, "max_results": MAX_RESULTS,
                             "max_preview_bytes": MAX_PREVIEW_BYTES,
                             "max_read_bytes": MAX_READ_BYTES},
                  "usage": {"lookup_bytes": lookup_bytes, "lookup_files": lookup_files,
                            "estimated_tokens": 0, "output_bytes": 0}}
        while True:
            result = _account(packet, sum(s["end_byte"] - s["start_byte"]
                                          for s in packet["sources"]))
            if result["usage"]["output_bytes"] <= MAX_OUTPUT_BYTES:
                return result
            if not packet["items"]:
                raise GraphFreeError("OUTPUT_BUDGET_EXCEEDED", "Retrieval framing exceeds output budget")
            packet["items"].pop()
            packet["sources"].pop()
            packet["selection"]["omitted_candidates"] += 1
            packet["omissions"].append({"reason": "output_budget", "count": 1})
            packet["status"] = "partial" if packet["items"] else "empty"

    def read(self, repo: str | Path, source_ref: str, **_ignored: Any) -> dict[str, Any]:
        root = _repo(repo)
        value = _decode_reference(root, source_ref)
        file = value["file"]
        hashes = self.inventory(root)["file_hashes"]
        if file not in hashes:
            raise GraphFreeError("INVALID_SOURCE_REF", "Source is absent from the inventory")
        if file not in _candidates(root) or _skipped(file):
            raise GraphFreeError("SOURCE_UNAVAILABLE", "Source is no longer eligible", {"file": file})
        if hashes[file] != value["hash"]:
            raise GraphFreeError("SOURCE_STALE", "Source reference differs from inventory", {"file": file})
        raw = _source_bytes(root, file)
        if hashlib.sha256(raw).hexdigest() != value["hash"]:
            raise GraphFreeError("SOURCE_STALE", "Source changed after reference selection", {"file": file})
        if value["end"] != len(raw):
            raise GraphFreeError("INVALID_SOURCE_REF", "Source extent is invalid")
        try:
            raw.decode("utf-8")
            raw[:value["offset"]].decode("utf-8")
        except UnicodeError as exc:
            raise GraphFreeError("INVALID_SOURCE_REF", "Reference is not on a UTF-8 boundary") from exc
        start = value["offset"]
        end = min(len(raw), start + MAX_READ_BYTES)
        while end > start and end < len(raw) and raw[end] & 0xC0 == 0x80:
            end -= 1

        def page(stop: int) -> dict[str, Any]:
            complete = stop == len(raw)
            packet = {"schema_version": 1, "status": "ok",
                      "source": _source(root, file, value["hash"], raw, start, stop, 1),
                      "complete": complete,
                      "next_source_ref": None if complete else
                      _reference(root, file, value["hash"], len(raw), stop),
                      "usage": {"output_bytes": 0}}
            return _account(packet, stop - start)

        result = page(end)
        while result["usage"]["output_bytes"] > MAX_OUTPUT_BYTES and end > start:
            end = start + (end - start) // 2
            while end > start and end < len(raw) and raw[end] & 0xC0 == 0x80:
                end -= 1
            result = page(end)
        if result["usage"]["output_bytes"] > MAX_OUTPUT_BYTES or (end == start and start < len(raw)):
            raise GraphFreeError("OUTPUT_BUDGET_EXCEEDED", "Source page cannot fit output budget")
        return result
