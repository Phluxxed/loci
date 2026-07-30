from __future__ import annotations

from pathlib import PurePath

from loci.parser.languages import EXTENSION_MAP

EXCLUDED_DIRECTORY_NAMES = frozenset({
    ".cache",
    ".git",
    ".mypy_cache",
    ".pip-cache",
    ".pytest_cache",
    ".ruff_cache",
    ".temp",
    ".tmp",
    ".tox",
    ".uv-cache",
    ".venv",
    "__pycache__",
    "build",
    "dist",
    "generated",
    "node_modules",
    "target",
    "temp",
    "tmp",
    "uv-cache",
    "vendor",
    "venv",
})

EXCLUDED_FILE_NAMES = frozenset({
    ".env",
    ".env.local",
    "credentials.json",
    "secrets.json",
})

EXCLUDED_FILE_EXTENSIONS = frozenset({
    ".bin",
    ".dll",
    ".dylib",
    ".exe",
    ".key",
    ".p12",
    ".pem",
    ".pyc",
    ".pyo",
    ".so",
})


def is_excluded_repository_path(path: PurePath) -> bool:
    """Return whether a repository-relative path is operationally disposable."""
    if path.is_absolute() or ".." in path.parts:
        raise ValueError("indexability paths must be repository-relative")
    return any(part in EXCLUDED_DIRECTORY_NAMES for part in path.parts)


def is_indexable_source_path(path: PurePath) -> bool:
    """Return whether a repository-relative path is supported maintained source."""
    if is_excluded_repository_path(path):
        return False
    if path.name in EXCLUDED_FILE_NAMES:
        return False
    suffix = path.suffix.lower()
    if suffix in EXCLUDED_FILE_EXTENSIONS:
        return False
    return suffix in EXTENSION_MAP
