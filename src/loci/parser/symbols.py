from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import PurePosixPath
from typing import Any


FILE_NODE_QUALIFIED_NAME = "__file__"
_FILE_KEYWORD_RE = re.compile(r"[A-Za-z0-9]+")


@dataclass
class Symbol:
    id: str
    name: str
    qualified_name: str
    kind: str  # function | class | method | type | constant | file
    language: str
    file_path: str
    byte_offset: int
    byte_length: int
    signature: str = ""
    docstring: str = ""
    summary: str = ""
    content_hash: str = ""  # SHA-256 of symbol bytes at index time; "" for old indexes
    decorators: list[str] = field(default_factory=list)  # decorator/attribute names
    keywords: list[str] = field(default_factory=list)    # name words for search
    metadata: dict[str, Any] = field(default_factory=dict)
    line: int = 0      # 1-indexed start line
    end_line: int = 0  # 1-indexed end line

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
            "content_hash": self.content_hash,
            "decorators": self.decorators,
            "keywords": self.keywords,
            "metadata": self.metadata,
            "line": self.line,
            "end_line": self.end_line,
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
            content_hash=data.get("content_hash", ""),
            decorators=data.get("decorators", []),
            keywords=data.get("keywords", []),
            metadata=data.get("metadata", {}),
            line=data.get("line", 0),
            end_line=data.get("end_line", 0),
        )


def make_symbol_id(file_path: str, qualified_name: str, kind: str) -> str:
    return f"{file_path}::{qualified_name}#{kind}"


def make_file_symbol(
    relative_path: str,
    *,
    language: str,
    content_hash: str,
) -> Symbol:
    path = PurePosixPath(relative_path)
    keyword_parts = path.with_suffix("").parts
    keywords = sorted({
        word.lower()
        for part in keyword_parts
        for word in _FILE_KEYWORD_RE.findall(part)
        if word.lower() != "src"
    })
    return Symbol(
        id=make_symbol_id(relative_path, FILE_NODE_QUALIFIED_NAME, "file"),
        name=path.name,
        qualified_name=FILE_NODE_QUALIFIED_NAME,
        kind="file",
        language=language,
        file_path=relative_path,
        byte_offset=0,
        byte_length=0,
        signature=relative_path,
        content_hash=content_hash,
        keywords=keywords,
        metadata={"loci": {"file_node": True}},
        line=1,
        end_line=1,
    )
