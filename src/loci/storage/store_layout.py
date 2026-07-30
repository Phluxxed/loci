from __future__ import annotations

import hashlib
from pathlib import Path


def repository_cache_key(repo_path: str | Path) -> str:
    """Return the stable on-disk directory name for one repository index."""
    repo = Path(repo_path)
    return canonical_repository_cache_key(str(repo.resolve()))


def canonical_repository_cache_key(repo_path: str) -> str:
    """Hash an already-canonical absolute path without touching the filesystem."""
    repo = Path(repo_path)
    if not repo.is_absolute():
        raise ValueError("canonical repository path must be absolute")
    digest = hashlib.md5(repo_path.encode()).hexdigest()[:12]
    return f"{digest}_{repo.name}"
