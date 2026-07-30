from __future__ import annotations

import hashlib
from pathlib import Path


def repository_cache_key(repo_path: str | Path) -> str:
    """Return the stable on-disk directory name for one repository index."""
    repo = Path(repo_path)
    digest = hashlib.md5(str(repo.resolve()).encode()).hexdigest()[:12]
    return f"{digest}_{repo.name}"
