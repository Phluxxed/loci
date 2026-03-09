from __future__ import annotations
import hashlib
import json
import shutil
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

    def invalidate(self, repo_path: Path) -> None:
        repo_dir = self._repo_dir(repo_path)
        if repo_dir.exists():
            shutil.rmtree(repo_dir)

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


def _score_symbol(sym: dict[str, Any], q: str, q_words: set[str]) -> float:
    if not q:
        return 0.0

    score = 0.0
    name = sym.get("name", "").lower()
    sig = sym.get("signature", "").lower()
    summary = sym.get("summary", "").lower()
    docstring = sym.get("docstring", "").lower()

    if name == q:
        score += 20
    elif q in name:
        score += 10

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
            score += 2

    return score
