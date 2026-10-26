"""Source and proof assembly for the fixed normal retrieval policy."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
from pathlib import Path, PurePosixPath
from typing import Any, Mapping, Sequence

from ._exploration_output import Span
from .exploration import (
    _Source,
    _edge_key as _legacy_edge_key,
    _go_controls,
    _go_package_clause_support,
    _records,
    _rust_controls,
    _rust_module_declaration_support,
)
from .graph.contracts import GraphEdge
from .graph.go_modules import MAX_GO_CONTROL_BYTES
from .graph.imports import ImportRecord
from .graph.profiles import read_contained_file
from .graph.state import GraphIndexState
from .storage.index_store import IndexStore


@dataclass(frozen=True)
class _ImportSupport:
    kind: str
    file: str
    line: int
    content_hash: str
    endpoint_id: str | None = None


def edge_identity(edge: GraphEdge) -> tuple[Any, ...]:
    """Return the complete stable identity used by normal retrieval."""
    return (
        edge.namespace,
        edge.type,
        edge.from_id,
        edge.to_id,
        edge.directed,
        edge.resolution,
        edge.evidence.file,
        edge.evidence.line,
        edge.evidence.content_hash,
    )


def snapshot_id(state: GraphIndexState, file_hashes: Mapping[str, str]) -> str:
    import json

    value = {
        "graph_schema_version": state.schema_version,
        "file_hashes": dict(sorted(file_hashes.items())),
        "input_hashes": dict(sorted(state.input_hashes.items())),
    }
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True,
                         separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


class RetrievalSource:
    """Hydrate definitions and complete proof from the validated graph state."""

    def __init__(
        self,
        repo: Path,
        store: IndexStore,
        nodes: Mapping[str, dict[str, Any]],
        state: GraphIndexState,
    ) -> None:
        self.repo = repo
        self.nodes = nodes
        self.state = state
        self.source = _Source(repo, store, nodes)
        index = store.load(repo)
        hashes = index.get("file_hashes", {}) if isinstance(index, dict) else {}
        self.file_hashes = {
            str(file): str(content_hash)
            for file, content_hash in hashes.items()
            if isinstance(file, str) and isinstance(content_hash, str)
        }
        self.edge_records = _records(state, nodes)
        self.import_records = self._index_imports(state.imports)

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

    def proof(self, edge: GraphEdge) -> tuple[Span, ...] | None:
        """Return complete source proof, or None when the stored edge cannot prove it."""
        try:
            if edge.type in {"imports", "imports_type"}:
                record = self.import_records.get(edge_identity(edge))
                if record is None or record.target_kind == "module":
                    # Swift module identity currently has no complete unique
                    # Package.swift target-declaration span.
                    return None
                return self._import_proof(record)

            record = self.edge_records.get(_legacy_edge_key(edge))
            if record is None or not _record_matches_edge(record.record, edge):
                return None
            spans: list[Span] = []
            site = self._record_site(record.record)
            if site is not None:
                spans.append(site)
            for support in record.support:
                # The exact call/type/reference site identifies its authored
                # owner. Repeating an arbitrarily large caller body adds no
                # binding proof and can starve the related declaration.
                if getattr(support, "kind", None) == "caller_definition":
                    continue
                spans.append(self.source.support(support))
            for control in record.controls:
                spans.append(self.source.control(control))
            spans.extend(self._javascript_controls(record.record))
            spans.extend(self.source.rust_configuration_support(record.record))
            return _unique_spans(spans) or None
        except (KeyError, UnicodeError, ValueError):
            return None

    def resolution_configuration(self, edge: GraphEdge) -> str | None:
        if edge.type in {"imports", "imports_type"}:
            record = self.import_records.get(edge_identity(edge))
            return getattr(record, "resolution_configuration", None)
        record = self.edge_records.get(_legacy_edge_key(edge))
        return getattr(record.record, "resolution_configuration", None) if record else None

    def endpoint_members(
        self,
        owner: Mapping[str, Any],
        query_terms: set[str],
        *,
        limit: int,
    ) -> tuple[dict[str, Any], ...]:
        kind = owner.get("kind")
        loci = _loci_metadata(owner)
        candidates: list[dict[str, Any]] = []
        if kind == "file":
            file = owner.get("file_path")
            candidates = [
                node for node in self.nodes.values()
                if _source_node(node) and node.get("file_path") == file
            ]
        elif kind == "package" and owner.get("language") == "go":
            directory = loci.get("directory")
            if isinstance(directory, str):
                candidates = [
                    node for node in self.nodes.values()
                    if _source_node(node) and node.get("language") == "go"
                    and PurePosixPath(str(node.get("file_path", ""))).parent.as_posix() == directory
                ]
        elif kind == "crate" and owner.get("language") == "rust":
            root = loci.get("crate_root")
            if isinstance(root, str):
                candidates = [
                    node for node in self.nodes.values()
                    if _source_node(node) and node.get("file_path") == root
                ]
        elif kind == "module" and owner.get("language") == "swift":
            directory = loci.get("directory")
            if isinstance(directory, str):
                prefix = directory.rstrip("/") + "/"
                candidates = [
                    node for node in self.nodes.values()
                    if _source_node(node) and node.get("language") == "swift"
                    and str(node.get("file_path", "")).startswith(prefix)
                ]

        ranked = []
        for node in candidates:
            text = " ".join(str(node.get(key, "")) for key in
                            ("name", "file_path", "signature"))
            overlap = len(query_terms & _terms(text))
            ranked.append((-overlap, str(node.get("file_path", "")),
                           int(node.get("byte_offset", 0)), str(node["id"]), node))
        if any(rank[0] < 0 for rank in ranked):
            ranked = [rank for rank in ranked if rank[0] < 0]
        ranked.sort(key=lambda rank: rank[:4])
        return tuple(rank[4] for rank in ranked[:limit])

    def file_owner(self, node: Mapping[str, Any]) -> dict[str, Any] | None:
        if node.get("kind") == "file":
            return None
        file = node.get("file_path")
        matches = [
            candidate for candidate in self.nodes.values()
            if candidate.get("kind") == "file" and candidate.get("file_path") == file
        ]
        return matches[0] if len(matches) == 1 else None

    def _index_imports(
        self,
        records: Sequence[ImportRecord],
    ) -> dict[tuple[Any, ...], ImportRecord]:
        selected: dict[tuple[Any, ...], ImportRecord] = {}
        ranks: dict[tuple[Any, ...], tuple[Any, ...]] = {}
        edges = {
            (edge.type, edge.from_id, edge.to_id, edge.evidence.file,
             edge.evidence.line, edge.evidence.content_hash): edge
            for edge in self.state.edges if edge.namespace == "loci"
            and edge.type in {"imports", "imports_type"}
        }
        for record in records:
            if record.status != "resolved" or record.target_id is None:
                continue
            edge_type = "imports_type" if record.raw.type_only else "imports"
            edge = edges.get((edge_type, record.source_id, record.target_id,
                              record.raw.source_file, record.raw.line,
                              record.raw.source_hash))
            if edge is None:
                continue
            identity = edge_identity(edge)
            rank = (record.raw.line, record.raw.text, record.raw.specifier,
                    record.raw.imported_name or "")
            if identity not in ranks or rank < ranks[identity]:
                ranks[identity] = rank
                selected[identity] = record
        return selected

    def _import_proof(self, record: ImportRecord) -> tuple[Span, ...]:
        support = _ImportSupport(
            "reexport" if record.raw.is_reexport else "import_binding",
            record.raw.source_file,
            record.raw.line,
            record.raw.source_hash,
            record.source_id,
        )
        spans = [self._import_declaration(record, support)]
        if record.raw.language == "go":
            spans.extend(
                self.source.support(item)
                for item in _go_package_clause_support(record, self.nodes)
            )
            spans.extend(self.source.control(item) for item in _go_controls(self.state))
        elif record.raw.language == "rust":
            spans.extend(
                self.source.support(item)
                for item in _rust_module_declaration_support(record, self.state)
            )
            spans.extend(
                self.source.control(item)
                for item in _rust_controls(self.state, record.resolution_control_files)
            )
            spans.extend(self.source.rust_configuration_support(record))
        elif record.raw.language in {"javascript", "typescript"}:
            spans.extend(self._javascript_controls(record))
        return _unique_spans(spans)

    def _javascript_controls(self, record: Any) -> tuple[Span, ...]:
        raw = getattr(record, "raw", None)
        if getattr(raw, "language", None) not in {"javascript", "typescript"}:
            return ()
        expected: dict[str, str] = {}
        for file in getattr(record, "resolution_control_files", ()):
            content_hash = self.state.input_hashes.get(file)
            if not isinstance(content_hash, str):
                raise ValueError("Named JavaScript resolution control is not tracked")
            expected[file] = content_hash
        for control in getattr(record, "resolution_controls", ()):
            file = getattr(control, "file", None)
            content_hash = getattr(control, "content_hash", None)
            if not isinstance(file, str) or not isinstance(content_hash, str):
                raise ValueError("JavaScript type control is invalid")
            if self.state.input_hashes.get(file) != content_hash:
                raise ValueError("JavaScript type control differs from tracked input")
            expected[file] = content_hash
        return tuple(
            self._control_span(file, content_hash)
            for file, content_hash in sorted(expected.items())
        )

    def _control_span(self, file: str, content_hash: str) -> Span:
        if self.state.input_hashes.get(file) != content_hash:
            raise ValueError("Resolver control differs from tracked graph input")
        try:
            data, relative = read_contained_file(
                self.repo,
                Path(file),
                record="Resolver control evidence",
                max_bytes=MAX_GO_CONTROL_BYTES,
            )
        except GraphContractError as exc:
            raise ValueError("Resolver control evidence is unavailable") from exc
        if relative != file or hashlib.sha256(data).hexdigest() != content_hash:
            raise ValueError("Resolver control differs from current source")
        if not data:
            raise ValueError("Resolver control is empty")
        try:
            content = data.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ValueError("Resolver control is not UTF-8") from exc
        return Span(
            file,
            0,
            len(data),
            1,
            max(1, 1 + content.count("\n") - int(content.endswith("\n"))),
            content_hash,
            content,
        )

    def _import_declaration(self, record: ImportRecord, support: _ImportSupport) -> Span:
        if record.raw.language != "python":
            # _Source owns complete JS/TS/Go/Rust declaration hydration.
            return self.source.support(support)
        raw, _ = self.source.cache.file(record.raw.source_file, record.raw.source_hash)
        try:
            from tree_sitter import Parser
            from tree_sitter_language_pack import get_language

            root = Parser(get_language("python")).parse(raw).root_node
        except Exception as exc:
            raise ValueError("Python import proof could not be parsed") from exc
        candidates = []
        pending = [root]
        while pending:
            node = pending.pop()
            if node.type in {"import_statement", "import_from_statement"}:
                start_line = node.start_point[0] + 1
                end_line = node.end_point[0] + 1
                text = raw[node.start_byte:node.end_byte].decode("utf-8")
                if start_line <= record.raw.line <= end_line and text.strip() == record.raw.text.strip():
                    candidates.append(node)
            pending.extend(reversed(node.named_children))
        if len(candidates) != 1:
            raise ValueError("Python import proof has no unique enclosing declaration")
        node = candidates[0]
        content = raw[node.start_byte:node.end_byte].decode("utf-8")
        return Span(record.raw.source_file, node.start_byte, node.end_byte,
                    node.start_point[0] + 1, node.end_point[0] + 1,
                    record.raw.source_hash, content)

    def _record_site(self, record: Any) -> Span | None:
        raw_record = getattr(record, "raw", None)
        file = getattr(raw_record, "source_file", None)
        content_hash = getattr(raw_record, "source_hash", None)
        start = getattr(raw_record, "start_byte", None)
        end = getattr(raw_record, "end_byte", None)
        if not isinstance(file, str) or not isinstance(content_hash, str):
            return None
        if type(start) is not int or type(end) is not int or end <= start:
            return None
        raw, _ = self.source.cache.file(file, content_hash)
        content = raw[start:end].decode("utf-8")
        line = raw[:start].count(b"\n") + 1
        return Span(file, start, end, line,
                    max(line, line + content.count("\n") - int(content.endswith("\n"))),
                    content_hash, content)


def preview_span(span: Span, max_bytes: int) -> tuple[Span, bool]:
    raw = span.content.encode("utf-8")
    if len(raw) <= max_bytes:
        return span, True
    end = max_bytes
    while end > 0 and raw[end] & 0xC0 == 0x80:
        end -= 1
    newline = raw.rfind(b"\n", 0, end)
    if newline >= 0:
        end = newline + 1
    if end <= 0:
        raise ValueError("source preview cannot make UTF-8 progress")
    content = raw[:end].decode("utf-8")
    return Span(
        span.file,
        span.start_byte,
        span.start_byte + end,
        span.start_line,
        max(span.start_line, span.start_line + content.count("\n") - int(content.endswith("\n"))),
        span.content_hash,
        content,
    ), False


def _source_node(node: Mapping[str, Any]) -> bool:
    return (
        type(node.get("byte_length")) is int
        and node["byte_length"] > 0
        and node.get("kind") not in {"file", "package", "crate", "module"}
    )


def _loci_metadata(node: Mapping[str, Any]) -> Mapping[str, Any]:
    metadata = node.get("metadata")
    if not isinstance(metadata, Mapping):
        return {}
    loci = metadata.get("loci")
    return loci if isinstance(loci, Mapping) else {}


def _terms(text: str) -> set[str]:
    import re

    return {term.lower() for term in re.findall(r"[A-Za-z_$][A-Za-z0-9_$]*", text)}


def _unique_spans(spans: Sequence[Span]) -> tuple[Span, ...]:
    result = []
    seen = set()
    for span in spans:
        key = (span.file, span.start_byte, span.end_byte, span.content_hash)
        if key not in seen:
            seen.add(key)
            result.append(span)
    return tuple(result)


def _record_matches_edge(record: Any, edge: GraphEdge) -> bool:
    raw = getattr(record, "raw", None)
    source_id = getattr(record, "source_id", getattr(record, "caller_id", None))
    target_id = getattr(record, "target_id", None)
    if source_id != edge.from_id or target_id != edge.to_id:
        return False
    resolution = getattr(record, "resolution", None)
    if resolution is None and hasattr(record, "import_source_id"):
        resolution = "import-resolved"
    if resolution != edge.resolution:
        return False
    if (
        getattr(raw, "source_file", None) != edge.evidence.file
        or getattr(raw, "line", None) != edge.evidence.line
        or getattr(raw, "source_hash", None) != edge.evidence.content_hash
    ):
        return False
    if hasattr(raw, "relation"):
        return raw.relation == edge.type
    if hasattr(record, "caller_id"):
        return edge.type == "calls"
    binding = getattr(record, "binding", None)
    expected = "references_type" if getattr(binding, "type_only", False) else "references"
    return edge.type == expected
