"""Hydrate selected definitions from the indexed source cache."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

from ._exploration_output import Span
from .exploration import _Source
from .storage.index_store import EXTRACTOR_VERSION, INDEX_SCHEMA_VERSION, IndexStore


def snapshot_id(file_hashes: Mapping[str, str]) -> str:
    value = {"source_schema_version": INDEX_SCHEMA_VERSION,
             "extractor_version": EXTRACTOR_VERSION,
             "file_hashes": dict(sorted(file_hashes.items()))}
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True,
                         separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


class RetrievalSource:
    """Read source without building semantic proof indexes."""

    def __init__(self, repo: Path, store: IndexStore,
                 nodes: Mapping[str, dict[str, Any]],
                 file_hashes: Mapping[str, str]) -> None:
        self.repo = repo
        self.nodes = nodes
        self.source = _Source(repo, store, nodes)
        self.file_hashes = file_hashes

    def definition(self, node: Mapping[str, Any]) -> Span:
        if node.get("kind") == "file":
            file = str(node["file_path"])
            raw, _ = self.source.cache.file(file, str(node["content_hash"]))
            if not raw:
                raise ValueError("empty files have no source extent")
            content = raw.decode("utf-8")
            return Span(
                file,
                0,
                len(raw),
                1,
                max(1, 1 + content.count("\n") - int(content.endswith("\n"))),
                hashlib.sha256(raw).hexdigest(),
                content,
            )
        return self.source.definition(dict(node))

    def file_owner(self, node: Mapping[str, Any]) -> dict[str, Any] | None:
        if node.get("kind") == "file":
            return None
        file = node.get("file_path")
        matches = [
            candidate for candidate in self.nodes.values()
            if candidate.get("kind") == "file" and candidate.get("file_path") == file
        ]
        return matches[0] if len(matches) == 1 else None


def _source_node(node: Mapping[str, Any]) -> bool:
    return (
        type(node.get("byte_length")) is int
        and node["byte_length"] > 0
        and node.get("kind") not in {"file", "package", "crate", "module"}
    )
