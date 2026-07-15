from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, TypeAlias


ImportUnresolvedReason: TypeAlias = Literal[
    "external",
    "not_indexed",
    "ambiguous",
    "unsupported_language",
    "invalid_specifier",
]


@dataclass(frozen=True, slots=True)
class RawImport:
    source_file: str
    language: str
    line: int
    text: str
    specifier: str
    imported_name: str | None
    type_only: bool
    is_reexport: bool
    source_hash: str
