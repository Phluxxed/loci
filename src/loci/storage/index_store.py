from __future__ import annotations
import hashlib
import json
import re
import shutil
import time
from pathlib import Path
from typing import Any, Optional

from loci.parser.symbols import Symbol


class IndexStore:
    def __init__(self, base_dir: Optional[Path] = None) -> None:
        self.base_dir = base_dir or Path.home() / ".codeindex"
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def _cache_key(self, repo_path: Path) -> str:
        abs_path = str(repo_path.resolve())
        h = hashlib.md5(abs_path.encode()).hexdigest()[:12]
        return f"{h}_{repo_path.name}"

    def _repo_dir(self, repo_path: Path) -> Path:
        return self.base_dir / self._cache_key(repo_path)

    def _index_path(self, repo_path: Path) -> Path:
        return self._repo_dir(repo_path) / "index.json"

    def _sources_dir(self, repo_path: Path) -> Path:
        return self._repo_dir(repo_path) / "sources"

    def hash_file(self, path: Path) -> str:
        h = hashlib.sha256()
        h.update(path.read_bytes())
        return h.hexdigest()

    def write(
        self,
        repo_path: Path,
        symbols: list[Symbol],
        file_hashes: dict[str, str],
    ) -> None:
        repo_dir = self._repo_dir(repo_path)
        repo_dir.mkdir(parents=True, exist_ok=True)

        # Mirror source files
        sources_dir = self._sources_dir(repo_path)
        for sym in symbols:
            src = repo_path / sym.file_path
            if src.exists():
                dest = sources_dir / sym.file_path
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dest)

        # Atomic write: temp file + rename
        index_data = {
            "symbols": [s.to_dict() for s in symbols],
            "file_hashes": file_hashes,
            "repo_path": str(repo_path.resolve()),
        }
        index_path = self._index_path(repo_path)
        tmp_path = index_path.with_suffix(".tmp")
        tmp_path.write_text(json.dumps(index_data, indent=2))
        tmp_path.replace(index_path)

    def load(self, repo_path: Path) -> Optional[dict[str, Any]]:
        index_path = self._index_path(repo_path)
        if not index_path.exists():
            return None
        return json.loads(index_path.read_text())

    def get_symbol_content(self, repo_path: Path, symbol_id: str) -> Optional[str]:
        index = self.load(repo_path)
        if index is None:
            return None

        sym_data = next(
            (s for s in index["symbols"] if s["id"] == symbol_id),
            None,
        )
        if sym_data is None:
            return None

        source_file = self._sources_dir(repo_path) / sym_data["file_path"]
        if not source_file.exists():
            return None

        with open(source_file, "rb") as f:
            f.seek(sym_data["byte_offset"])
            raw = f.read(sym_data["byte_length"])

        return raw.decode("utf-8", errors="replace")

    def get_symbol_context(
        self,
        repo_path: Path,
        symbol_id: str,
        context_lines: int,
    ) -> Optional[dict[str, list[str]]]:
        """Return N lines of context before and after a symbol in the cached source."""
        index = self.load(repo_path)
        if index is None:
            return None
        sym_data = next((s for s in index["symbols"] if s["id"] == symbol_id), None)
        if sym_data is None:
            return None
        source_file = self._sources_dir(repo_path) / sym_data["file_path"]
        if not source_file.exists():
            return None

        raw = source_file.read_bytes()
        all_lines = raw.decode("utf-8", errors="replace").splitlines()

        byte_offset = sym_data["byte_offset"]
        byte_length = sym_data["byte_length"]
        start_line = raw[:byte_offset].count(b"\n")           # 0-indexed
        end_line = start_line + raw[byte_offset:byte_offset + byte_length].count(b"\n")

        return {
            "context_before": all_lines[max(0, start_line - context_lines):start_line],
            "context_after": all_lines[end_line + 1:end_line + 1 + context_lines],
        }

    def search(
        self,
        repo_path: Path,
        query: str,
        kind: Optional[str] = None,
        lang: Optional[str] = None,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        index = self.load(repo_path)
        if index is None:
            return []

        q = query.lower()
        q_words = set(q.split()) if q else set()
        scored: list[tuple[float, dict]] = []

        for sym in index["symbols"]:
            if kind and sym.get("kind") != kind:
                continue
            if lang and sym.get("language") != lang:
                continue
            score = _score_symbol(sym, q, q_words)
            scored.append((score, sym))

        scored.sort(key=lambda x: x[0], reverse=True)
        results = []
        for score, sym in scored[:limit]:
            if not q or score > 0:
                entry = dict(sym)
                entry["score"] = round(score, 2)
                results.append(entry)

        return results


    def list_repos(self) -> list[dict[str, Any]]:
        repos = []
        for repo_dir in self.base_dir.iterdir():
            if not repo_dir.is_dir():
                continue
            index_file = repo_dir / "index.json"
            if not index_file.exists():
                continue
            try:
                data = json.loads(index_file.read_text())
                repos.append({
                    "cache_key": repo_dir.name,
                    "symbols": len(data.get("symbols", [])),
                    "path": data.get("repo_path", repo_dir.name),
                })
            except Exception:
                continue
        return repos

    def _session_log_path(self) -> Path:
        return self.base_dir / "session.jsonl"

    def log_retrieval(
        self,
        symbol_id: str,
        symbol_bytes: int,
        file_bytes: int,
        repo_path: str = "",
        kind: Optional[str] = None,
        language: Optional[str] = None,
        search_id: Optional[str] = None,
        search_rank: Optional[int] = None,
    ) -> None:
        entry = {
            "ts": time.time(),
            "event": "get",
            "symbol_id": symbol_id,
            "symbol_bytes": symbol_bytes,
            "file_bytes": file_bytes,
            "repo": repo_path,
            "kind": kind,
            "language": language,
            "search_id": search_id,
            "search_rank": search_rank,
        }
        with open(self._session_log_path(), "a") as f:
            f.write(json.dumps(entry) + "\n")

    def get_session_stats(self, repo_filter: Optional[str] = None) -> dict[str, Any]:
        log_path = self._session_log_path()
        total_gets = 0
        symbol_bytes_total = 0
        file_bytes_total = 0
        by_file: dict[str, dict[str, int]] = {}
        by_repo: dict[str, dict[str, int]] = {}

        if log_path.exists():
            for line in log_path.read_text().splitlines():
                if not line.strip():
                    continue
                entry = json.loads(line)
                repo = entry.get("repo", "")
                if repo_filter and repo != repo_filter:
                    continue
                total_gets += 1
                sb = entry["symbol_bytes"]
                fb = entry["file_bytes"]
                symbol_bytes_total += sb
                file_bytes_total += fb

                repo_key = repo or "unknown"

                file_path = entry["symbol_id"].split("::", 1)[0]
                file_key = f"{repo_key}/{file_path}" if repo_key != "unknown" else file_path
                if file_key not in by_file:
                    by_file[file_key] = {"gets": 0, "symbol_bytes": 0, "file_bytes": 0}
                by_file[file_key]["gets"] += 1
                by_file[file_key]["symbol_bytes"] += sb
                by_file[file_key]["file_bytes"] += fb
                if repo_key not in by_repo:
                    by_repo[repo_key] = {"gets": 0, "symbol_bytes": 0, "file_bytes": 0}
                by_repo[repo_key]["gets"] += 1
                by_repo[repo_key]["symbol_bytes"] += sb
                by_repo[repo_key]["file_bytes"] += fb

        not_loaded = max(0, file_bytes_total - symbol_bytes_total)
        tokens_not_loaded = not_loaded // 4
        ratio = f"{int(not_loaded / file_bytes_total * 100)}%" if file_bytes_total > 0 else "0%"

        def _make_rows(mapping: dict[str, dict[str, int]], key: str) -> list[dict]:
            rows = []
            for name, d in mapping.items():
                saved = max(0, d["file_bytes"] - d["symbol_bytes"])
                ratio_pct = int(saved / d["file_bytes"] * 100) if d["file_bytes"] > 0 else 0
                rows.append({"name": name if key == "repo" else name, "gets": d["gets"],
                              "saved_bytes": saved, "ratio_pct": ratio_pct})
            rows.sort(key=lambda r: r["saved_bytes"], reverse=True)
            return rows

        return {
            "total_gets": total_gets,
            "symbol_bytes_retrieved": symbol_bytes_total,
            "file_bytes_not_loaded": not_loaded,
            "tokens_not_loaded": tokens_not_loaded,
            "savings_ratio": ratio,
            "by_file": _make_rows(by_file, "file"),
            "by_repo": _make_rows(by_repo, "repo"),
        }

    def reset_session(self) -> None:
        log_path = self._session_log_path()
        if log_path.exists():
            log_path.unlink()

    def get_file_content(
        self,
        repo_path: Path,
        file_path: str,
        start_line: Optional[int] = None,
        end_line: Optional[int] = None,
    ) -> Optional[dict]:
        source_file = self._sources_dir(repo_path) / file_path
        if not source_file.resolve().is_relative_to(self._sources_dir(repo_path).resolve()):
            return None
        if not source_file.exists():
            return None
        raw = source_file.read_bytes()
        content = raw.decode("utf-8", errors="replace")
        lines = content.splitlines(keepends=True)
        total_lines = len(lines)
        file_bytes = len(raw)

        start = (start_line - 1) if start_line is not None else 0
        end = end_line if end_line is not None else total_lines
        start = max(0, min(start, total_lines))
        end = max(start, min(end, total_lines))
        sliced = "".join(lines[start:end])

        return {
            "file": file_path,
            "content": sliced,
            "total_lines": total_lines,
            "start_line": start + 1,
            "end_line": end,
            "file_bytes": file_bytes,
        }

    def grep_files(self, repo_path: Path, pattern: str) -> list[dict[str, Any]]:
        try:
            regex = re.compile(pattern)
        except re.error as exc:
            raise ValueError(f"Invalid regex pattern: {exc}") from exc

        sources = self._sources_dir(repo_path)
        if not sources.exists():
            return []

        results: list[dict[str, Any]] = []
        for src_file in sorted(sources.rglob("*")):
            if not src_file.is_file():
                continue
            rel_path = str(src_file.relative_to(sources))
            try:
                lines = src_file.read_text(encoding="utf-8", errors="replace").splitlines()
            except OSError:
                continue
            for i, line in enumerate(lines):
                if regex.search(line):
                    results.append({
                        "file": rel_path,
                        "line": i + 1,
                        "match": line,
                        "context_before": lines[max(0, i - 2):i],
                        "context_after": lines[i + 1:min(len(lines), i + 3)],
                    })
        return results

    def get_symbol_file_size(self, repo_path: Path, symbol_id: str) -> Optional[int]:
        index = self.load(repo_path)
        if index is None:
            return None
        sym_data = next((s for s in index["symbols"] if s["id"] == symbol_id), None)
        if sym_data is None:
            return None
        source_file = self._sources_dir(repo_path) / sym_data["file_path"]
        if not source_file.exists():
            return None
        return source_file.stat().st_size

    def invalidate(self, repo_path: Path) -> None:
        repo_dir = self._repo_dir(repo_path)
        if repo_dir.exists():
            shutil.rmtree(repo_dir)

    def verify_index(self, repo_path: Path) -> dict[str, Any]:
        """Check that every symbol's byte offset points to text containing its name.

        Returns a dict with 'repo', 'checked', 'passed', 'failed'. Each failure
        has the symbol id, name, kind, file, and the issue description.

        Note: uses name-in-bytes check (not a full re-parse). Catches byte offset
        corruption and wrong-node-type extraction.
        """
        index = self.load(repo_path)
        if index is None:
            return {"repo": str(repo_path), "error": "Repo not indexed"}

        sources = self._sources_dir(repo_path)
        checked = 0
        failed: list[dict[str, Any]] = []

        for sym in index["symbols"]:
            checked += 1
            sym_id = sym.get("id", "")
            name = sym.get("name", "")
            kind = sym.get("kind", "")
            file_path = sym.get("file_path", "")
            byte_offset = sym.get("byte_offset", 0)
            byte_length = sym.get("byte_length", 0)

            source_file = sources / file_path
            if not source_file.exists():
                failed.append({
                    "id": sym_id,
                    "name": name,
                    "kind": kind,
                    "file": file_path,
                    "issue": "source_file_missing",
                })
                continue

            try:
                with open(source_file, "rb") as f:
                    f.seek(byte_offset)
                    raw = f.read(byte_length)
                text = raw.decode("utf-8", errors="replace")
            except OSError as exc:
                failed.append({
                    "id": sym_id,
                    "name": name,
                    "kind": kind,
                    "file": file_path,
                    "issue": f"read_error: {exc}",
                })
                continue

            if name and name not in text:
                failed.append({
                    "id": sym_id,
                    "name": name,
                    "kind": kind,
                    "file": file_path,
                    "issue": "name_not_in_bytes",
                })
                continue

            # Drift check: if we have a stored hash, compare against the live file.
            stored_hash = sym.get("content_hash", "")
            if stored_hash:
                live_file = repo_path / file_path
                if live_file.exists():
                    try:
                        with open(live_file, "rb") as lf:
                            lf.seek(byte_offset)
                            live_raw = lf.read(byte_length)
                        live_hash = hashlib.sha256(live_raw).hexdigest()
                        if live_hash != stored_hash:
                            failed.append({
                                "id": sym_id,
                                "name": name,
                                "kind": kind,
                                "file": file_path,
                                "issue": "content_drift",
                            })
                    except OSError:
                        pass  # live file unreadable; skip drift check

        return {
            "repo": str(repo_path),
            "checked": checked,
            "passed": checked - len(failed),
            "failed": failed,
        }

    def apply_summaries(self, repo_path: Path, summaries: list[dict[str, str]]) -> int:
        index = self.load(repo_path)
        if index is None:
            return 0
        summary_map = {s["id"]: s["summary"] for s in summaries}
        applied = 0
        for sym in index["symbols"]:
            if sym["id"] in summary_map:
                sym["summary"] = summary_map[sym["id"]]
                applied += 1
        index_path = self._index_path(repo_path)
        tmp_path = index_path.with_suffix(".tmp")
        tmp_path.write_text(json.dumps(index, indent=2))
        tmp_path.replace(index_path)
        return applied


def _name_words(name: str) -> set[str]:
    """Split a symbol name into words for overlap scoring.

    Handles snake_case, SCREAMING_SNAKE, camelCase, PascalCase.
    e.g. "getUserById" → {"get", "user", "by", "id"}
         "MAX_RETRY_COUNT" → {"max", "retry", "count"}
    """
    # Split on underscores first, then split each part on camelCase boundaries
    parts: list[str] = []
    for segment in name.split("_"):
        # Insert a space before each uppercase letter that follows a lowercase letter
        camel_split = re.sub(r"([a-z])([A-Z])", r"\1 \2", segment)
        parts.extend(camel_split.lower().split())
    return {p for p in parts if len(p) > 1}  # skip single-char fragments


def _score_symbol(sym: dict[str, Any], q: str, q_words: set[str]) -> float:
    if not q:
        return 0.0

    score = 0.0
    name = sym.get("name", "").lower()
    qualified = sym.get("qualified_name", "").lower()
    sig = sym.get("signature", "").lower()
    summary = sym.get("summary", "").lower()
    docstring = sym.get("docstring", "").lower()

    # Exact and substring matches on qualified name (highest signal)
    if qualified == q:
        score += 25
    elif q in qualified:
        score += 12

    # Exact and substring matches on bare name
    if name == q:
        score += 20
    elif q in name:
        score += 10

    # Name word overlap: "get user" matches getUserById
    name_words = _name_words(sym.get("name", ""))
    for word in q_words:
        if word in name_words:
            score += 5

    if q in sig:
        score += 8
    else:
        for word in q_words:
            if word in sig:
                score += 2

    if summary:
        if q in summary:
            score += 5
        else:
            for word in q_words:
                if word in summary:
                    score += 1

    for word in q_words:
        if word in docstring:
            score += 1

    # Keyword match (+3 per matching keyword)
    keywords = set(sym.get("keywords", []))
    score += len(q_words & keywords) * 3

    return score
