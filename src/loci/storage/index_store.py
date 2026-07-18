from __future__ import annotations
import hashlib
import json
import re
import shutil
import time
from pathlib import Path
from typing import Any, Mapping, Optional

from loci.graph.contracts import (
    GraphContractError,
    GraphEdge,
    validate_graph_edges,
)
from loci.graph.state import GraphIndexState
from loci.parser.symbols import Symbol

LAST_SEARCH_TTL = 300  # 5 minutes
INDEX_SCHEMA_VERSION = 5
EXTRACTOR_VERSION = 7


def _resolve_worktree_root(path: str) -> str:
    """If path is a git worktree, return the main repo root. Otherwise return path unchanged."""
    p = Path(path)
    git_entry = p / ".git"
    if not git_entry.is_file():
        return path
    # .git file content: "gitdir: /abs/path/to/.git/worktrees/<name>"
    content = git_entry.read_text().strip()
    if not content.startswith("gitdir:"):
        return path
    gitdir = Path(content[len("gitdir:"):].strip())
    # worktrees live at <main_git_dir>/worktrees/<name> — main repo root is gitdir.parent.parent
    if gitdir.parent.name == "worktrees":
        main_git = gitdir.parent.parent  # the main .git dir
        return str(main_git.parent)
    return path


def index_versions_current(index: dict[str, Any]) -> bool:
    return (
        index.get("schema_version") == INDEX_SCHEMA_VERSION
        and index.get("extractor_version") == EXTRACTOR_VERSION
    )


class IndexStore:
    def __init__(self, base_dir: Optional[Path] = None) -> None:
        self.base_dir = base_dir or Path.home() / ".codeindex"
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self._worktree_cache: dict[str, str] = {}

    def _canonical_repo(self, repo_path: str) -> str:
        if repo_path not in self._worktree_cache:
            self._worktree_cache[repo_path] = _resolve_worktree_root(repo_path)
        return self._worktree_cache[repo_path]

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

    def refresh_lock_path(self, repo_path: Path) -> Path:
        repo_dir = self._repo_dir(repo_path)
        repo_dir.mkdir(parents=True, exist_ok=True)
        return repo_dir / "refresh.lock"

    def hash_file(self, path: Path) -> str:
        h = hashlib.sha256()
        h.update(path.read_bytes())
        return h.hexdigest()

    def write(
        self,
        repo_path: Path,
        symbols: list[Symbol],
        file_hashes: dict[str, str],
        *,
        graph_state: GraphIndexState | None = None,
    ) -> None:
        persisted_graph = graph_state or GraphIndexState.empty()
        persisted_graph = GraphIndexState.from_dict(persisted_graph.to_dict())
        indexed_nodes = {symbol.id: symbol.to_dict() for symbol in symbols}
        built_in_edge_candidates = [
            edge
            for edge in persisted_graph.edges
            if (
                edge.namespace == "loci"
                or edge.type in {"imports", "imports_type"}
            )
        ]
        validate_graph_edges(
            built_in_edge_candidates,
            indexed_nodes=indexed_nodes,
            file_hashes=file_hashes,
            imports=persisted_graph.imports,
        )

        repo_dir = self._repo_dir(repo_path)
        repo_dir.mkdir(parents=True, exist_ok=True)

        # Mirror source files
        sources_dir = self._sources_dir(repo_path)
        tmp_sources_dir = sources_dir.with_name(f"{sources_dir.name}.tmp")
        if tmp_sources_dir.exists():
            shutil.rmtree(tmp_sources_dir)
        tmp_sources_dir.mkdir(parents=True, exist_ok=True)
        for sym in symbols:
            src = repo_path / sym.file_path
            if src.exists():
                dest = tmp_sources_dir / sym.file_path
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dest)
        if sources_dir.exists():
            shutil.rmtree(sources_dir)
        tmp_sources_dir.replace(sources_dir)

        # Atomic write: temp file + rename
        index_data = {
            "schema_version": INDEX_SCHEMA_VERSION,
            "extractor_version": EXTRACTOR_VERSION,
            "symbols": [s.to_dict() for s in symbols],
            "file_hashes": file_hashes,
            "repo_path": str(repo_path.resolve()),
            "graph": persisted_graph.to_dict(),
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

    def get_graph_edges(self, repo_path: Path) -> list[GraphEdge]:
        return list(self.get_graph_state(repo_path).edges)

    def get_graph_state(self, repo_path: Path) -> GraphIndexState:
        index = self.load(repo_path)
        if index is None:
            return GraphIndexState.empty()
        graph = index.get("graph")
        if not isinstance(graph, Mapping):
            raise GraphContractError(
                "INVALID_GRAPH_SCHEMA",
                "Index does not contain a graph envelope",
                {},
            )
        return GraphIndexState.from_dict(graph)

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

        q = query.lower().strip()
        q_words = _query_words(q)
        scored: list[tuple[float, dict, list[str]]] = []
        symbols_by_id = {
            sym.get("id", ""): sym
            for sym in index["symbols"]
            if sym.get("id")
        }

        for sym in index["symbols"]:
            if kind and sym.get("kind") != kind:
                continue
            if lang and sym.get("language") != lang:
                continue
            score, match_scope, exact_page_title = _score_symbol_detail(sym, q, q_words)
            if sym.get("language") == "markdown" and q:
                inherited_score, inherited_scopes = _score_inherited_markdown_metadata(
                    sym,
                    symbols_by_id,
                    q,
                    q_words,
                )
                if inherited_score and _has_markdown_local_signal(sym, q, q_words, match_scope):
                    score += inherited_score * 0.55
                    match_scope.extend(inherited_scopes)
            if score > 0 and sym.get("language") == "markdown":
                score = _adjust_markdown_score(sym, score, q_words, match_scope, exact_page_title)
            if score > 0 and _is_template_symbol(sym):
                score *= 0.5
            scored.append((score, sym, match_scope))

        scored.sort(key=lambda x: x[0], reverse=True)
        results = []
        for score, sym, match_scope in scored[:limit]:
            if not q or score > 0:
                entry = dict(sym)
                entry["score"] = round(score, 2)
                _add_markdown_result_fields(entry, sym)
                if sym.get("language") == "markdown":
                    entry["match_scope"] = _unique_scopes(match_scope)
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
        repo_path = self._canonical_repo(repo_path)
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

    def get_session_stats(self, repo_filter: Optional[str] = None, since_days: Optional[int] = None) -> dict[str, Any]:
        log_path = self._session_log_path()
        total_outlines = 0
        cutoff_ts = time.time() - since_days * 86400 if since_days is not None else None
        last_get_ts: Optional[float] = None

        # Per-bucket summary accumulators. A get is a "doc" if its symbol came
        # from a markdown file (heading-section retrieval), else "code".
        buckets = {
            "code": {"gets": 0, "sb": 0, "fb": 0, "last_ts": None, "outlines": 0},
            "docs": {"gets": 0, "sb": 0, "fb": 0, "last_ts": None, "outlines": 0},
        }
        by_file: dict[str, dict] = {}        # combined (back-compat)
        by_repo: dict[str, dict] = {}        # combined (back-compat)
        by_file_code: dict[str, dict] = {}   # code gets only, per file
        by_repo_code: dict[str, dict] = {}   # code gets only, per repo
        by_doc: dict[str, dict] = {}         # markdown gets only, per file
        by_repo_doc: dict[str, dict] = {}    # markdown gets only, per repo

        def _accum(mapping: dict[str, dict], key: str, sb: int, fb: int, ts: Optional[float]) -> None:
            d = mapping.get(key)
            if d is None:
                d = mapping[key] = {"gets": 0, "symbol_bytes": 0, "file_bytes": 0, "last_ts": None}
            d["gets"] += 1
            d["symbol_bytes"] += sb
            d["file_bytes"] += fb
            if ts is not None and (d["last_ts"] is None or ts > d["last_ts"]):
                d["last_ts"] = ts

        if log_path.exists():
            for line in log_path.read_text().splitlines():
                if not line.strip():
                    continue
                entry = json.loads(line)
                if cutoff_ts is not None and entry.get("ts", 0) < cutoff_ts:
                    continue
                event = entry.get("event", "get")
                repo = entry.get("repo", "")
                if repo_filter and repo != repo_filter:
                    continue
                if event == "outline":
                    total_outlines += 1
                    # A whole-repo outline spans both lanes, so it counts toward
                    # each language it surfaced. Events logged before languages
                    # were recorded have none -> attribute to the code lane.
                    langs = entry.get("languages") or []
                    has_md = "markdown" in langs
                    has_code = any(l != "markdown" for l in langs) or not langs
                    if has_code:
                        buckets["code"]["outlines"] += 1
                    if has_md:
                        buckets["docs"]["outlines"] += 1
                    continue
                if event != "get":
                    continue
                ts = entry.get("ts")
                if ts is not None and (last_get_ts is None or ts > last_get_ts):
                    last_get_ts = ts
                sb = entry["symbol_bytes"]
                fb = entry["file_bytes"]
                is_doc = entry.get("language") == "markdown"

                b = buckets["docs" if is_doc else "code"]
                b["gets"] += 1
                b["sb"] += sb
                b["fb"] += fb
                if ts is not None and (b["last_ts"] is None or ts > b["last_ts"]):
                    b["last_ts"] = ts

                repo_key = repo or "unknown"
                file_path = entry["symbol_id"].split("::", 1)[0]
                file_key = f"{repo_key}/{file_path}" if repo_key != "unknown" else file_path

                _accum(by_file, file_key, sb, fb, ts)
                _accum(by_repo, repo_key, sb, fb, ts)
                if is_doc:
                    _accum(by_doc, file_key, sb, fb, ts)
                    _accum(by_repo_doc, repo_key, sb, fb, ts)
                else:
                    _accum(by_file_code, file_key, sb, fb, ts)
                    _accum(by_repo_code, repo_key, sb, fb, ts)

        symbol_bytes_total = buckets["code"]["sb"] + buckets["docs"]["sb"]
        file_bytes_total = buckets["code"]["fb"] + buckets["docs"]["fb"]
        total_gets = buckets["code"]["gets"] + buckets["docs"]["gets"]
        not_loaded = max(0, file_bytes_total - symbol_bytes_total)
        tokens_not_loaded = not_loaded // 4
        ratio = f"{int(not_loaded / file_bytes_total * 100)}%" if file_bytes_total > 0 else "0%"

        def _make_rows(mapping: dict[str, dict[str, int]]) -> list[dict]:
            rows = []
            for name, d in mapping.items():
                saved = max(0, d["file_bytes"] - d["symbol_bytes"])
                ratio_pct = int(saved / d["file_bytes"] * 100) if d["file_bytes"] > 0 else 0
                rows.append({"name": name, "gets": d["gets"],
                              "saved_bytes": saved, "ratio_pct": ratio_pct,
                              "last_ts": d.get("last_ts")})
            rows.sort(key=lambda r: r["saved_bytes"], reverse=True)
            return rows

        def _summary(b: dict) -> dict:
            nl = max(0, b["fb"] - b["sb"])
            r = f"{int(nl / b['fb'] * 100)}%" if b["fb"] > 0 else "0%"
            return {
                "outlines": b["outlines"],
                "gets": b["gets"],
                "symbol_bytes": b["sb"],
                "file_bytes_not_loaded": nl,
                "tokens_not_loaded": nl // 4,
                "savings_ratio": r,
                "last_get_ts": b["last_ts"],
            }

        return {
            "total_gets": total_gets,
            "total_outlines": total_outlines,
            "symbol_bytes_retrieved": symbol_bytes_total,
            "file_bytes_not_loaded": not_loaded,
            "tokens_not_loaded": tokens_not_loaded,
            "savings_ratio": ratio,
            "last_get_ts": last_get_ts,
            "by_file": _make_rows(by_file),
            "by_repo": _make_rows(by_repo),
            # Code / docs split (used by the two-lane pretty view)
            "code": _summary(buckets["code"]),
            "docs": _summary(buckets["docs"]),
            "by_file_code": _make_rows(by_file_code),
            "by_repo_code": _make_rows(by_repo_code),
            "by_doc": _make_rows(by_doc),
            "by_repo_doc": _make_rows(by_repo_doc),
        }

    def reset_session(self) -> Optional[Path]:
        """Clear the session log, backing it up first so a reset is never lossy.

        Copies the current log to a timestamped ``session.jsonl.<ts>.bak`` before
        truncating it. Returns the backup path, or None if there was nothing to
        back up.
        """
        log_path = self._session_log_path()
        if not log_path.exists():
            return None

        timestamp = time.strftime("%Y%m%d-%H%M%S")
        backup_path = log_path.with_name(f"{log_path.name}.{timestamp}.bak")
        # Don't clobber an existing backup (e.g. two resets within one second).
        counter = 1
        while backup_path.exists():
            backup_path = log_path.with_name(f"{log_path.name}.{timestamp}-{counter}.bak")
            counter += 1

        shutil.copy2(log_path, backup_path)
        log_path.unlink()
        return backup_path

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
        """Check indexed symbol spans and synthetic-node anchor hashes.

        Returns a dict with 'repo', 'checked', 'passed', 'failed'. Each failure
        has the symbol id, name, kind, file, and the issue description.

        Ordinary symbols use a name-in-bytes check. File and validated Go
        package nodes use their whole anchor-file hash instead.
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

            if _should_verify_name_in_bytes(sym) and name and name not in text:
                failed.append({
                    "id": sym_id,
                    "name": name,
                    "kind": kind,
                    "file": file_path,
                    "issue": "name_not_in_bytes",
                })
                continue

            signature = sym.get("signature", "")
            if _should_verify_markdown_signature(sym) and signature not in text:
                failed.append({
                    "id": sym_id,
                    "name": name,
                    "kind": kind,
                    "file": file_path,
                    "issue": "signature_not_in_bytes",
                })
                continue

            # Drift check: if we have a stored hash, compare against the live file.
            stored_hash = sym.get("content_hash", "")
            if stored_hash:
                live_file = repo_path / file_path
                if live_file.exists():
                    try:
                        if kind == "file" or _is_go_package_node(sym):
                            live_raw = live_file.read_bytes()
                        else:
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

    def _write_last_search(self, search_id: str, query: str, result_ids: list[str], repo: str = "") -> None:
        data = {"search_id": search_id, "ts": time.time(), "query": query, "result_ids": result_ids, "repo": repo}
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

    def resolve_search_correlation(self, symbol_id: str, repo: str = "") -> tuple[Optional[str], Optional[int]]:
        """Return (search_id, rank) for symbol_id against last search, or (None, None).

        Returns (None, None) if the last search was for a different repo, preventing
        cross-repo correlation noise in analyze findings.
        """
        data = self._read_last_search()
        if data is None:
            return None, None
        if repo and data.get("repo", "") != repo:
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
        repo_path = self._canonical_repo(repo_path)
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
        self._write_last_search(search_id, query, result_ids, repo=repo_path)

    def log_miss(
        self,
        miss_type: str,
        repo_path: str = "",
        query: Optional[str] = None,
        symbol_id: Optional[str] = None,
    ) -> None:
        repo_path = self._canonical_repo(repo_path)
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

    def log_outline(
        self,
        repo_path: str,
        symbol_count: int,
        file_filter: Optional[str] = None,
        languages: Optional[list[str]] = None,
    ) -> None:
        repo_path = self._canonical_repo(repo_path)
        entry = {
            "ts": time.time(),
            "event": "outline",
            "repo": repo_path,
            "symbol_count": symbol_count,
            "file_filter": file_filter,
            "languages": languages or [],
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
        # When a search event is present, only correlate gets to searches in the same repo —
        # cross-repo correlations are an artifact of stale last_search state, not a real signal.
        # Older logs only stored search_id/search_rank on get events; keep those analyzable.
        search_by_id: dict[str, dict] = {s["search_id"]: s for s in searches if s.get("search_id")}
        correlated_gets = [
            g for g in gets
            if g.get("search_id") is not None
            and (
                g["search_id"] not in search_by_id
                or search_by_id[g["search_id"]].get("repo", "") == g.get("repo", "")
            )
        ]
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

def _ts_to_iso(ts: float) -> str:
    from datetime import datetime, timezone
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _name_words(name: str) -> set[str]:
    """Split a symbol name into words for overlap scoring.

    Handles snake_case, SCREAMING_SNAKE, camelCase, PascalCase,
    and leading/trailing underscores (_private, __dunder__).
    e.g. "getUserById"      → {"get", "user", "by", "id"}
         "MAX_RETRY_COUNT"  → {"max", "retry", "count"}
         "_forecast_model"  → {"forecast", "model"}
         "__init__"         → {"init"}
    """
    # Strip leading/trailing underscores before splitting so _private and __dunder__
    # names don't produce empty segments that swallow their keywords.
    parts: list[str] = []
    for segment in name.strip("_").split("_"):
        # Insert a space before each uppercase letter that follows a lowercase letter
        camel_split = re.sub(r"([a-z])([A-Z])", r"\1 \2", segment)
        parts.extend(camel_split.lower().split())
    return {p for p in parts if len(p) > 1}  # skip single-char fragments


def _query_words(text: str) -> set[str]:
    """Tokenise natural-language queries and metadata values for search."""
    return {w for w in re.split(r"[^A-Za-z0-9]+", text.lower()) if len(w) > 1}


_KIND_WEIGHTS: dict[str, dict[str, float]] = {
    "python": {
        "function": 10, "method": 10, "class": 3, "constant": -5,
    },
    "typescript": {
        "function": 10, "method": 10, "class": 8, "type": 8, "constant": -3,
    },
    "javascript": {
        "function": 10, "method": 10, "class": 6, "constant": -3,
    },
    "go": {
        "function": 10, "method": 10, "type": 8, "constant": -3,
    },
    "rust": {
        "function": 10, "method": 10, "type": 6, "constant": -3,
    },
    "_default": {
        "function": 8, "method": 8, "class": 4, "constant": -2,
    },
}


def _kind_weight(kind: str, language: str) -> float:
    lang_weights = _KIND_WEIGHTS.get(language, _KIND_WEIGHTS["_default"])
    return lang_weights.get(kind, 0.0)


def _score_symbol(sym: dict[str, Any], q: str, q_words: set[str]) -> float:
    score, _match_scope, _exact_page_title = _score_symbol_detail(sym, q, q_words)
    if score > 0 and _is_template_symbol(sym):
        score *= 0.5
    return score


def _score_symbol_detail(
    sym: dict[str, Any],
    q: str,
    q_words: set[str],
) -> tuple[float, list[str], bool]:
    if not q:
        return 0.0, [], False

    score = 0.0
    match_scope: list[str] = []
    name = sym.get("name", "").lower()
    qualified = sym.get("qualified_name", "").lower()
    sig = sym.get("signature", "").lower()
    summary = sym.get("summary", "").lower()
    docstring = sym.get("docstring", "").lower()

    if qualified == q:
        score += 25
        match_scope.append("section_heading")
    elif q in qualified:
        score += 12
        match_scope.append("section_heading")

    if name == q:
        score += 20
        match_scope.append("section_heading")
    elif q in name:
        score += 10
        match_scope.append("section_heading")

    name_words = _name_words(sym.get("name", ""))
    for word in q_words:
        if word in name_words:
            score += 5
            match_scope.append("section_heading")

    if q in sig:
        score += 8
        match_scope.append("section_heading")
    else:
        for word in q_words:
            if word in sig:
                score += 2
                match_scope.append("section_heading")

    if summary:
        if q in summary:
            score += 5
            match_scope.append("section_summary")
        else:
            for word in q_words:
                if word in summary:
                    score += 1
                    match_scope.append("section_summary")

    for word in q_words:
        if word in docstring:
            score += 1
            match_scope.append("section_summary")

    keywords = {str(k).lower() for k in sym.get("keywords", [])}
    keyword_hits = q_words & keywords
    if keyword_hits:
        score += len(keyword_hits) * 3
        match_scope.append("section_keywords")

    metadata_score, metadata_scopes, exact_page_title = _score_frontmatter(
        _frontmatter_metadata(sym),
        q,
        q_words,
        prefix="page_frontmatter",
    )
    score += metadata_score
    match_scope.extend(metadata_scopes)

    if score <= 0:
        return 0.0, [], False

    score += _kind_weight(sym.get("kind", ""), sym.get("language", ""))
    return score, _unique_scopes(match_scope), exact_page_title


def _score_metadata(sym: dict[str, Any], q: str, q_words: set[str]) -> float:
    score, _scopes, _exact_page_title = _score_frontmatter(
        _frontmatter_metadata(sym),
        q,
        q_words,
        prefix="page_frontmatter",
    )
    return score


def _score_frontmatter(
    frontmatter: dict[str, Any],
    q: str,
    q_words: set[str],
    *,
    prefix: str,
) -> tuple[float, list[str], bool]:
    if not frontmatter:
        return 0.0, [], False

    score = 0.0
    match_scope: list[str] = []
    exact_page_title = False

    for tag in _metadata_list(frontmatter.get("tags")):
        tag_lower = tag.lower()
        tag_score = 0.0
        if tag_lower == q:
            tag_score += 16
        elif q and q in tag_lower:
            tag_score += 10
        tag_score += len(q_words & _query_words(tag)) * 4
        if tag_score:
            score += tag_score
            match_scope.append(f"{prefix}.tags")

    title = _metadata_scalar(frontmatter.get("title"))
    if title:
        field_score = _score_metadata_text(title, q, q_words, exact=8, word=2)
        if field_score:
            score += field_score
            match_scope.append(f"{prefix}.title")
            exact_page_title = title.lower() == q

    for field in ("category", "type", "source", "status"):
        value = _metadata_scalar(frontmatter.get(field))
        if value:
            field_score = _score_metadata_text(value, q, q_words, exact=7, word=2)
            if field_score:
                score += field_score
                match_scope.append(f"{prefix}.{field}")

    description = _metadata_scalar(frontmatter.get("description"))
    if description:
        field_score = _score_metadata_text(description, q, q_words, exact=5, word=1)
        if field_score:
            score += field_score
            match_scope.append(f"{prefix}.description")

    return score, _unique_scopes(match_scope), exact_page_title


def _score_inherited_markdown_metadata(
    sym: dict[str, Any],
    symbols_by_id: dict[str, dict[str, Any]],
    q: str,
    q_words: set[str],
) -> tuple[float, list[str]]:
    markdown = _markdown_metadata_block(sym)
    if not markdown:
        return 0.0, []
    root_id = str(markdown.get("root_id") or "")
    if not root_id or root_id == sym.get("id"):
        return 0.0, []
    root = symbols_by_id.get(root_id)
    if not root:
        return 0.0, []
    score, scopes, _exact_page_title = _score_frontmatter(
        _frontmatter_metadata(root),
        q,
        q_words,
        prefix="inherited_page_frontmatter",
    )
    return score, scopes


_ACTIONABLE_MARKDOWN_HEADINGS = {
    "problem signal",
    "proposed graph move",
    "evidence to gather",
    "next experiment",
    "risks and failure modes",
    "query",
    "usage",
    "operations",
    "frontmatter",
}

_PAGE_LEVEL_QUERY_WORDS = {"overview", "manual", "page", "document", "doc", "readme", "guide"}


def _has_markdown_local_signal(
    sym: dict[str, Any],
    q: str,
    q_words: set[str],
    match_scope: list[str],
) -> bool:
    if any(scope.startswith("section_") for scope in match_scope):
        return True
    heading = str(sym.get("name", "")).lower()
    if heading in _ACTIONABLE_MARKDOWN_HEADINGS:
        return True
    local_text = " ".join(
        str(sym.get(field, ""))
        for field in ("name", "qualified_name", "summary", "docstring")
    ).lower()
    return bool(q and q in local_text) or bool(q_words & _query_words(local_text))


def _adjust_markdown_score(
    sym: dict[str, Any],
    score: float,
    q_words: set[str],
    match_scope: list[str],
    exact_page_title: bool,
) -> float:
    markdown = _markdown_metadata_block(sym)
    if not markdown:
        return score

    saved_pct = _markdown_saved_pct(sym)
    span_kind = markdown.get("span_kind")
    inherited = any(scope.startswith("inherited_page_frontmatter.") for scope in match_scope)
    local = any(scope.startswith("section_") for scope in match_scope)

    if span_kind == "page_root" and saved_pct < 25 and not exact_page_title:
        if not (q_words & _PAGE_LEVEL_QUERY_WORDS):
            score *= 0.5
    elif span_kind == "section" and saved_pct >= 50 and inherited and local:
        score += 8
    return score


def _add_markdown_result_fields(entry: dict[str, Any], sym: dict[str, Any]) -> None:
    markdown = _markdown_metadata_block(sym)
    if not markdown:
        return
    for key in ("file_bytes", "saved_pct", "span_kind"):
        if key in markdown:
            entry[key] = markdown[key]


def _markdown_metadata_block(sym: dict[str, Any]) -> dict[str, Any]:
    metadata = sym.get("metadata")
    if not isinstance(metadata, dict):
        return {}
    markdown = metadata.get("markdown")
    return markdown if isinstance(markdown, dict) else {}


def _markdown_saved_pct(sym: dict[str, Any]) -> int:
    markdown = _markdown_metadata_block(sym)
    try:
        return int(markdown.get("saved_pct", 0))
    except (TypeError, ValueError):
        return 0


def _unique_scopes(scopes: list[str]) -> list[str]:
    unique: list[str] = []
    seen: set[str] = set()
    for scope in scopes:
        if scope and scope not in seen:
            unique.append(scope)
            seen.add(scope)
    return unique


def _frontmatter_metadata(sym: dict[str, Any]) -> dict[str, Any]:
    metadata = sym.get("metadata")
    if not isinstance(metadata, dict):
        return {}
    frontmatter = metadata.get("frontmatter")
    return frontmatter if isinstance(frontmatter, dict) else {}


def _metadata_scalar(value: Any) -> str:
    if value is None or isinstance(value, (dict, list, tuple, set)):
        return ""
    return str(value)


def _metadata_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        items = [value]
    elif isinstance(value, (list, tuple, set)):
        items = list(value)
    else:
        items = [value]
    return [text for item in items if (text := str(item).strip())]


def _score_metadata_text(text: str, q: str, q_words: set[str], *, exact: float, word: float) -> float:
    text_lower = text.lower()
    score = exact if q and q in text_lower else 0.0
    score += len(q_words & _query_words(text)) * word
    return score


def _is_template_symbol(sym: dict[str, Any]) -> bool:
    parts = Path(sym.get("file_path", "")).parts
    return "_templates" in parts


def _should_verify_name_in_bytes(sym: dict[str, Any]) -> bool:
    return (
        sym.get("kind") != "file"
        and not _is_go_package_node(sym)
        and not _is_synthetic_markdown_name(sym)
    )


def _is_go_package_node(sym: dict[str, Any]) -> bool:
    if sym.get("kind") != "package" or sym.get("language") != "go":
        return False
    metadata = sym.get("metadata")
    loci_metadata = metadata.get("loci") if isinstance(metadata, dict) else None
    if not (
        isinstance(loci_metadata, dict)
        and loci_metadata.get("go_package_node") is True
        and sym.get("byte_offset") == 0
        and sym.get("byte_length") == 0
    ):
        return False
    directory = loci_metadata.get("directory")
    import_path = loci_metadata.get("import_path")
    package_name = loci_metadata.get("package_name")
    return (
        isinstance(directory, str)
        and bool(directory)
        and isinstance(import_path, str)
        and bool(import_path)
        and isinstance(package_name, str)
        and bool(package_name)
        and sym.get("qualified_name") == import_path
        and sym.get("name") == package_name
    )


def _is_synthetic_markdown_name(sym: dict[str, Any]) -> bool:
    if sym.get("language") != "markdown":
        return False
    if sym.get("name") == "(preamble)":
        return True

    metadata = sym.get("metadata")
    markdown = metadata.get("markdown") if isinstance(metadata, dict) else None
    if isinstance(markdown, dict) and markdown.get("synthetic_name"):
        return True

    signature = str(sym.get("signature", ""))
    name = str(sym.get("name", ""))
    return bool(name and signature == name and not _is_markdown_heading_signature(signature))


def _should_verify_markdown_signature(sym: dict[str, Any]) -> bool:
    return sym.get("language") == "markdown" and _is_markdown_heading_signature(str(sym.get("signature", "")))


def _is_markdown_heading_signature(signature: str) -> bool:
    return signature.lstrip().startswith("#")
