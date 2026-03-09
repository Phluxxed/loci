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
