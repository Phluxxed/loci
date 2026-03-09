from __future__ import annotations
from dataclasses import dataclass
from typing import Any


@dataclass
class Symbol:
    id: str
    name: str
    qualified_name: str
    kind: str  # function | class | method | type | constant
    language: str
    file_path: str
    byte_offset: int
    byte_length: int
    signature: str = ""
    docstring: str = ""
    summary: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "qualified_name": self.qualified_name,
            "kind": self.kind,
            "language": self.language,
            "file_path": self.file_path,
            "byte_offset": self.byte_offset,
            "byte_length": self.byte_length,
            "signature": self.signature,
            "docstring": self.docstring,
            "summary": self.summary,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Symbol:
        return cls(
            id=data["id"],
            name=data["name"],
            qualified_name=data["qualified_name"],
            kind=data["kind"],
            language=data["language"],
            file_path=data["file_path"],
            byte_offset=data["byte_offset"],
            byte_length=data["byte_length"],
            signature=data.get("signature", ""),
            docstring=data.get("docstring", ""),
            summary=data.get("summary", ""),
        )


def make_symbol_id(file_path: str, qualified_name: str, kind: str) -> str:
    return f"{file_path}::{qualified_name}#{kind}"
