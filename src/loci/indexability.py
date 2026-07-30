from __future__ import annotations

from pathlib import PurePath
from typing import Literal

from loci.parser.languages import EXTENSION_MAP

SourceExclusionReason = Literal[
    "policy_excluded",
    "sensitive_or_binary",
    "unsupported_file_type",
]

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
    return repository_path_exclusion_root(path) is not None


def repository_path_exclusion_root(path: PurePath) -> PurePath | None:
    """Return the bounded policy root excluding a repository-relative path."""
    if path.is_absolute() or ".." in path.parts:
        raise ValueError("indexability paths must be repository-relative")
    for index, part in enumerate(path.parts):
        if part in EXCLUDED_DIRECTORY_NAMES:
            return type(path)(*path.parts[: index + 1])
    return None


def source_exclusion_reason(path: PurePath) -> SourceExclusionReason | None:
    """Classify why a repository-relative file is not indexable source."""
    if repository_path_exclusion_root(path) is not None:
        return "policy_excluded"
    if path.name in EXCLUDED_FILE_NAMES:
        return "sensitive_or_binary"
    suffix = path.suffix.lower()
    if suffix in EXCLUDED_FILE_EXTENSIONS:
        return "sensitive_or_binary"
    if suffix not in EXTENSION_MAP:
        return "unsupported_file_type"
    return None


def is_indexable_source_path(path: PurePath) -> bool:
    """Return whether a repository-relative path is supported maintained source."""
    return source_exclusion_reason(path) is None
