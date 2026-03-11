from __future__ import annotations
import hashlib
import json
import re
import shutil
import time
from pathlib import Path
from typing import Any, Optional

from loci.parser.symbols import Symbol

LAST_SEARCH_TTL = 300  # 5 minutes


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
                if entry.get("event", "get") != "get":
                    continue
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

    def _last_search_path(self) -> Path:
        return self.base_dir / "last_search.json"

    def _write_last_search(self, search_id: str, query: str, result_ids: list[str]) -> None:
        data = {"search_id": search_id, "ts": time.time(), "query": query, "result_ids": result_ids}
        self._last_search_path().write_text(json.dumps(data))

    def _read_last_search(self) -> Optional[dict]:
        p = self._last_search_path()
        if not p.exists():
            return None
        try:
            data = json.loads(p.read_text())
            if time.time() - data["ts"] > LAST_SEARCH_TTL:
                return None
            return data
        except (json.JSONDecodeError, KeyError):
            return None

    def resolve_search_correlation(self, symbol_id: str) -> tuple[Optional[str], Optional[int]]:
        """Return (search_id, rank) for symbol_id against last search, or (None, None)."""
        data = self._read_last_search()
        if data is None:
            return None, None
        search_id = data["search_id"]
        result_ids = data["result_ids"]
        try:
            rank = result_ids.index(symbol_id)
        except ValueError:
            rank = None
        return search_id, rank

    def log_search(
        self,
        search_id: str,
        query: str,
        repo_path: str,
        result_ids: list[str],
        result_count: Optional[int] = None,
    ) -> None:
        # result_count is the true total from search; result_ids may be top-N subset
        entry = {
            "ts": time.time(),
            "event": "search",
            "search_id": search_id,
            "query": query,
            "repo": repo_path,
            "result_ids": result_ids,
            "result_count": result_count if result_count is not None else len(result_ids),
        }
        with open(self._session_log_path(), "a") as f:
            f.write(json.dumps(entry) + "\n")
        self._write_last_search(search_id, query, result_ids)

    def log_miss(
        self,
        miss_type: str,
        repo_path: str = "",
        query: Optional[str] = None,
        symbol_id: Optional[str] = None,
    ) -> None:
        entry = {
            "ts": time.time(),
            "event": "miss",
            "miss_type": miss_type,
            "repo": repo_path,
            "query": query,
            "symbol_id": symbol_id,
        }
        with open(self._session_log_path(), "a") as f:
            f.write(json.dumps(entry) + "\n")

    def analyze(self, since_days: int = 30, repo_filter: Optional[str] = None) -> dict[str, Any]:
        """Read session log and produce actionable findings."""
        from collections import Counter, defaultdict

        log_path = self._session_log_path()
        cutoff = time.time() - since_days * 86400

        gets: list[dict] = []
        searches: list[dict] = []
        misses: list[dict] = []

        if log_path.exists():
            for line in log_path.read_text().splitlines():
                if not line.strip():
                    continue
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if entry.get("ts", 0) < cutoff:
                    continue
                if repo_filter and entry.get("repo", "") != repo_filter:
                    continue
                event = entry.get("event", "get")  # backwards compat: old entries have no event field
                if event == "get":
                    gets.append(entry)
                elif event == "search":
                    searches.append(entry)
                elif event == "miss":
                    misses.append(entry)

        findings: list[dict] = []

        # --- search_miss: queries returning 0 results ---
        empty_queries = [e["query"] for e in misses
                         if e.get("miss_type") == "search_empty" and e.get("query")]
        if empty_queries:
            counts = Counter(empty_queries)
            findings.append({
                "type": "search_miss",
                "severity": "high",
                "data": {"queries": list(counts.keys()), "count": len(empty_queries)},
                "suggestion": (
                    f"{len(counts)} unique queries return 0 results. "
                    "Check keyword extraction handles these name patterns."
                ),
            })

        # --- search_blind_spot: fetched symbol not returned by preceding search ---
        # 15% threshold suppresses noise when a few gets happen to precede unrelated searches.
        # Below 15%, individual outliers are more likely than a systemic gap.
        correlated_gets = [g for g in gets if g.get("search_id") is not None]
        blind_spots = [g for g in correlated_gets if g.get("search_rank") is None]
        if correlated_gets and len(blind_spots) / len(correlated_gets) >= 0.15:
            blind_pct = len(blind_spots) / len(correlated_gets)
            findings.append({
                "type": "search_blind_spot",
                "severity": "high",
                "data": {
                    "blind_spot_count": len(blind_spots),
                    "correlated_gets": len(correlated_gets),
                    "blind_pct": round(blind_pct, 3),
                },
                "suggestion": (
                    f"{round(blind_pct * 100)}% of gets fetch symbols not returned by "
                    "the preceding search. Search is missing entire symbol classes — "
                    "check indexing and scoring."
                ),
            })

        # --- search_ranking_poor: fetched symbol ranked ≥3 too often ---
        ranked_gets = [g for g in correlated_gets if g.get("search_rank") is not None]
        poor_ranked = [g for g in ranked_gets if g["search_rank"] >= 3]
        if ranked_gets and len(poor_ranked) / len(ranked_gets) >= 0.20:
            poor_pct = len(poor_ranked) / len(ranked_gets)
            avg_rank = sum(g["search_rank"] for g in ranked_gets) / len(ranked_gets)
            findings.append({
                "type": "search_ranking_poor",
                "severity": "medium",
                "data": {
                    "poor_ranked_count": len(poor_ranked),
                    "ranked_gets": len(ranked_gets),
                    "poor_pct": round(poor_pct, 3),
                    "avg_rank": round(avg_rank, 1),
                },
                "suggestion": (
                    f"Fetched symbols ranked \u22653 in {round(poor_pct * 100)}% of correlated "
                    f"searches (avg rank {avg_rank:.1f}). Adjust scoring weights for "
                    "name/keyword matches."
                ),
            })

        # --- kind_dead_weight: kind indexed many times but never fetched ---
        # list_repos() returns list[dict] with "path" key — use that to load each index
        fetched_kinds: set[str] = {g["kind"] for g in gets if g.get("kind")}
        indexed_by_kind: dict[str, int] = Counter()
        for repo_info in self.list_repos():
            index = self.load(Path(repo_info["path"]))
            if index is None:
                continue
            for sym in index.get("symbols", []):
                k = sym.get("kind")
                if k:
                    indexed_by_kind[k] += 1
        for kind, count in indexed_by_kind.items():
            if count > 50 and kind not in fetched_kinds:
                findings.append({
                    "type": "kind_dead_weight",
                    "severity": "low",
                    "data": {"kind": kind, "indexed_count": count, "fetched_count": 0},
                    "suggestion": (
                        f"'{kind}' symbols are indexed ({count} across all repos) but never "
                        "fetched. Consider excluding from index or lowering search score weight."
                    ),
                })

        # --- poor_extraction: language avg savings ratio < 50% ---
        lang_bytes: dict[str, dict[str, int]] = defaultdict(lambda: {"symbol": 0, "file": 0})
        for g in gets:
            lang = g.get("language")
            if lang:
                lang_bytes[lang]["symbol"] += g.get("symbol_bytes", 0)
                lang_bytes[lang]["file"] += g.get("file_bytes", 0)
        for lang, b in lang_bytes.items():
            if b["file"] == 0:
                continue
            ratio = (b["file"] - b["symbol"]) / b["file"]
            if ratio < 0.50:
                findings.append({
                    "type": "poor_extraction",
                    "severity": "medium",
                    "data": {"language": lang, "avg_ratio_pct": round(ratio * 100)},
                    "suggestion": (
                        f"{lang} symbols average {round(ratio * 100)}% savings ratio. "
                        "Extractor may be including too much context per symbol."
                    ),
                })

        # --- refetch_hotspot: same symbol fetched 3+ times ---
        fetch_counts = Counter(g["symbol_id"] for g in gets if g.get("symbol_id"))
        hotspots = sorted(
            [{"symbol_id": sid, "fetch_count": cnt} for sid, cnt in fetch_counts.items() if cnt >= 3],
            key=lambda x: x["fetch_count"], reverse=True,
        )
        if hotspots:
            findings.append({
                "type": "refetch_hotspot",
                "severity": "low",
                "data": {"symbols": hotspots[:10]},
                "suggestion": (
                    f"{len(hotspots)} symbol(s) fetched 3+ times. "
                    "They may be too large to stay in context — consider splitting or summarizing."
                ),
            })

        # --- Summary ---
        all_ts = [e["ts"] for e in gets + searches + misses if e.get("ts")]
        period_from = min(all_ts) if all_ts else time.time()
        period_to = max(all_ts) if all_ts else time.time()
        total_events = len(gets) + len(misses)
        miss_rate = len(misses) / total_events if total_events > 0 else 0.0
        correlated_pct = len(correlated_gets) / len(gets) if gets else 0.0

        return {
            "period": {
                "from": _ts_to_iso(period_from),
                "to": _ts_to_iso(period_to),
            },
            "summary": {
                "total_gets": len(gets),
                "total_searches": len(searches),
                "total_misses": len(misses),
                "miss_rate": round(miss_rate, 3),
                "correlated_pct": round(correlated_pct, 3),
            },
            "findings": findings,
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


def _ts_to_iso(ts: float) -> str:
    from datetime import datetime, timezone
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


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
