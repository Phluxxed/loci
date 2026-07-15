from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Any, Literal, Mapping, TypeAlias, cast

from loci.parser.imports import ImportUnresolvedReason, RawImport
from loci.parser.symbols import Symbol

from .contracts import (
    GraphContractError,
    GraphEdge,
    GraphEvidence,
    JSONValue,
)


ImportStatus: TypeAlias = Literal["resolved", "unresolved"]
ImportTargetKind: TypeAlias = Literal["file", "package"]
_IMPORT_STATUSES = frozenset({"resolved", "unresolved"})
_IMPORT_TARGET_KINDS = frozenset({"file", "package"})
_UNRESOLVED_REASONS = frozenset({
    "external",
    "not_indexed",
    "ambiguous",
    "unsupported_language",
    "invalid_specifier",
    "inaccessible",
})
_RAW_IMPORT_FIELDS = {
    "source_file",
    "language",
    "line",
    "text",
    "specifier",
    "imported_name",
    "type_only",
    "is_reexport",
    "source_hash",
}
_IMPORT_RECORD_FIELDS = {
    "raw",
    "source_id",
    "target_file",
    "target_package",
    "target_kind",
    "target_id",
    "status",
    "unresolved_reason",
}
_SHA256_RE = re.compile(r"[0-9a-f]{64}")
_JAVASCRIPT_LANGUAGES = frozenset({"javascript", "typescript"})
_JAVASCRIPT_EXTENSIONS = (".ts", ".tsx", ".js")


@dataclass(frozen=True, slots=True)
class ImportRecord:
    raw: RawImport
    source_id: str
    target_file: str | None
    target_package: str | None
    target_kind: ImportTargetKind | None
    target_id: str | None
    status: ImportStatus
    unresolved_reason: ImportUnresolvedReason | None

    def __post_init__(self) -> None:
        _validate_raw_import(self.raw)
        _nonempty_string(self.source_id, "source_id")
        if self.target_file is not None:
            _relative_path(self.target_file, "target_file")
        if self.target_package is not None:
            _nonempty_string(self.target_package, "target_package")
        if (
            self.target_kind is not None
            and (
                not isinstance(self.target_kind, str)
                or self.target_kind not in _IMPORT_TARGET_KINDS
            )
        ):
            raise _error("Invalid import target kind", field="target_kind")
        if self.target_id is not None:
            _nonempty_string(self.target_id, "target_id")
        if not isinstance(self.status, str) or self.status not in _IMPORT_STATUSES:
            raise _error("Invalid import status", field="status")
        if (
            self.unresolved_reason is not None
            and (
                not isinstance(self.unresolved_reason, str)
                or self.unresolved_reason not in _UNRESOLVED_REASONS
            )
        ):
            raise _error(
                "Invalid import unresolved reason",
                field="unresolved_reason",
            )
        if self.status == "resolved":
            if self.target_kind is None:
                raise _error("Resolved import requires a target kind")
            if self.target_kind == "file":
                if self.target_file is None or self.target_id is None:
                    raise _error("Resolved file import requires a target file and ID")
                if self.target_package is not None:
                    raise _error("Resolved file import cannot have a target package")
                if self.raw.language == "go":
                    raise _error("Go imports must target packages")
            else:
                if self.target_file is not None:
                    raise _error("Resolved package import cannot have a target file")
                if self.target_package is None or self.target_id is None:
                    raise _error(
                        "Resolved package import requires a target package and ID"
                    )
                if self.raw.language != "go":
                    raise _error("Only Go imports may target packages")
            if self.raw.language == "rust":
                raise _error("Rust imports cannot be resolved")
            if self.unresolved_reason is not None:
                raise _error("Resolved import cannot have an unresolved reason")
        else:
            if any((
                self.target_file is not None,
                self.target_package is not None,
                self.target_kind is not None,
                self.target_id is not None,
            )):
                raise _error("Unresolved import cannot have a target")
            if self.unresolved_reason is None:
                raise _error("Unresolved import requires an unresolved reason")

    def to_dict(self) -> dict[str, JSONValue]:
        return {
            "raw": _raw_import_to_dict(self.raw),
            "source_id": self.source_id,
            "target_file": self.target_file,
            "target_package": self.target_package,
            "target_kind": self.target_kind,
            "target_id": self.target_id,
            "status": self.status,
            "unresolved_reason": self.unresolved_reason,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> ImportRecord:
        _require_keys(value, _IMPORT_RECORD_FIELDS, "import record")
        raw_value = value["raw"]
        if not isinstance(raw_value, Mapping):
            raise _error("Import raw observation must be an object", field="raw")
        target_file = _optional_relative_path(value["target_file"], "target_file")
        target_package = _optional_nonempty_string(
            value["target_package"],
            "target_package",
        )
        target_kind = value["target_kind"]
        if target_kind is not None and (
            not isinstance(target_kind, str)
            or target_kind not in _IMPORT_TARGET_KINDS
        ):
            raise _error("Invalid import target kind", field="target_kind")
        target_id = _optional_nonempty_string(value["target_id"], "target_id")
        status = value["status"]
        if not isinstance(status, str) or status not in _IMPORT_STATUSES:
            raise _error("Invalid import status", field="status")
        unresolved_reason = value["unresolved_reason"]
        if unresolved_reason is not None and (
            not isinstance(unresolved_reason, str)
            or unresolved_reason not in _UNRESOLVED_REASONS
        ):
            raise _error(
                "Invalid import unresolved reason",
                field="unresolved_reason",
            )
        return cls(
            raw=_raw_import_from_dict(raw_value),
            source_id=_nonempty_string(value["source_id"], "source_id"),
            target_file=target_file,
            target_package=target_package,
            target_kind=cast(ImportTargetKind | None, target_kind),
            target_id=target_id,
            status=cast(ImportStatus, status),
            unresolved_reason=cast(ImportUnresolvedReason | None, unresolved_reason),
        )


def resolve_import(
    raw: RawImport,
    *,
    file_nodes: Mapping[str, Symbol],
) -> ImportRecord:
    """Resolve one raw import against deterministic indexed file nodes."""
    return resolve_imports((raw,), file_nodes=file_nodes)[0]


def resolve_imports(
    raw_imports: Sequence[RawImport],
    *,
    file_nodes: Mapping[str, Symbol],
) -> list[ImportRecord]:
    """Resolve a batch while deriving indexed language layouts only once."""
    indexed_python_files = _indexed_python_files(file_nodes)
    python_package_roots = _python_package_roots(indexed_python_files)
    indexed_javascript_files = _indexed_javascript_files(file_nodes)
    return [
        _resolve_import(
            raw,
            file_nodes=file_nodes,
            indexed_python_files=indexed_python_files,
            python_package_roots=python_package_roots,
            indexed_javascript_files=indexed_javascript_files,
        )
        for raw in raw_imports
    ]


def _resolve_import(
    raw: RawImport,
    *,
    file_nodes: Mapping[str, Symbol],
    indexed_python_files: frozenset[str],
    python_package_roots: tuple[PurePosixPath, ...],
    indexed_javascript_files: frozenset[str],
) -> ImportRecord:
    _validate_raw_import(raw)
    source = _require_file_node(file_nodes, raw.source_file, field="source_file")
    if raw.language == "python":
        target_file, unresolved_reason = _resolve_python_target(
            raw,
            indexed_python_files,
            python_package_roots,
        )
    elif raw.language in _JAVASCRIPT_LANGUAGES:
        target_file, unresolved_reason = _resolve_javascript_target(
            raw,
            indexed_javascript_files,
        )
    else:
        return _unresolved(raw, source.id, "unsupported_language")
    if target_file is None:
        return _unresolved(raw, source.id, unresolved_reason)

    target = _require_file_node(file_nodes, target_file, field="target_file")
    return ImportRecord(
        raw=raw,
        source_id=source.id,
        target_file=target_file,
        target_package=None,
        target_kind="file",
        target_id=target.id,
        status="resolved",
        unresolved_reason=None,
    )


def materialize_import_edges(
    records: Sequence[ImportRecord],
    *,
    file_nodes: Mapping[str, Symbol],
) -> list[GraphEdge]:
    """Build one deterministic evidence-backed edge per resolved dependency."""
    edges: dict[tuple[str, str, str, str], GraphEdge] = {}
    evidence_ranks: dict[tuple[str, str, str, str], tuple[int, str, str, str]] = {}

    for record in records:
        source = _require_file_node(
            file_nodes,
            record.raw.source_file,
            field="source_file",
        )
        if source.id != record.source_id:
            raise _error(
                "Import record source does not match its file node",
                field="source_id",
                source_id=record.source_id,
            )
        if record.status != "resolved":
            continue
        if record.target_file is None or record.target_id is None:
            raise _error("Resolved import requires a target file and ID")
        target = _require_file_node(
            file_nodes,
            record.target_file,
            field="target_file",
        )
        if target.id != record.target_id:
            raise _error(
                "Import record target does not match its file node",
                field="target_id",
                target_id=record.target_id,
            )
        if source.id == target.id:
            continue

        edge_type = "imports_type" if record.raw.type_only else "imports"
        edge = GraphEdge(
            from_id=source.id,
            to_id=target.id,
            type=edge_type,
            directed=True,
            namespace="loci",
            resolution="import-resolved",
            evidence=GraphEvidence(
                file=record.raw.source_file,
                line=record.raw.line,
                content_hash=record.raw.source_hash,
            ),
        )
        key = (edge.namespace, edge.type, edge.from_id, edge.to_id)
        rank = (
            record.raw.line,
            record.raw.text,
            record.raw.specifier,
            record.raw.imported_name or "",
        )
        if key not in evidence_ranks or rank < evidence_ranks[key]:
            edges[key] = edge
            evidence_ranks[key] = rank

    return [edges[key] for key in sorted(edges)]


def _resolve_python_target(
    raw: RawImport,
    indexed_files: frozenset[str],
    package_roots: tuple[PurePosixPath, ...],
) -> tuple[str | None, ImportUnresolvedReason]:
    imported_name = raw.imported_name
    if imported_name is not None and not imported_name.isidentifier():
        return None, "invalid_specifier"

    specifier = raw.specifier
    if specifier.startswith("."):
        base = _relative_python_base(raw.source_file, specifier)
        if base is None:
            return None, "invalid_specifier"
        bases = (base,)
    else:
        parts = _dotted_parts(specifier)
        if parts is None:
            return None, "invalid_specifier"
        bases = tuple(
            root.joinpath(*parts)
            for root in package_roots
        )

    targets = {
        target
        for base in bases
        if (target := _resolve_python_base(base, imported_name, indexed_files))
        is not None
    }
    if not targets:
        return None, "not_indexed"
    if len(targets) > 1:
        return None, "ambiguous"
    return targets.pop(), "not_indexed"


def _indexed_python_files(file_nodes: Mapping[str, Symbol]) -> frozenset[str]:
    return frozenset(
        path
        for path, node in file_nodes.items()
        if (
            path == node.file_path
            and node.kind == "file"
            and node.language == "python"
            and path.endswith(".py")
        )
    )


def _indexed_javascript_files(file_nodes: Mapping[str, Symbol]) -> frozenset[str]:
    return frozenset(
        path
        for path, node in file_nodes.items()
        if (
            path == node.file_path
            and node.kind == "file"
            and node.language in _JAVASCRIPT_LANGUAGES
            and path.endswith(_JAVASCRIPT_EXTENSIONS)
        )
    )


def _resolve_javascript_target(
    raw: RawImport,
    indexed_files: frozenset[str],
) -> tuple[str | None, ImportUnresolvedReason]:
    specifier = raw.specifier
    if not specifier or "\\" in specifier or specifier.startswith("/"):
        return None, "invalid_specifier"
    if not specifier.startswith(("./", "../")):
        return None, "external"

    base = _relative_javascript_base(raw.source_file, specifier)
    if base is None:
        return None, "invalid_specifier"

    base_path = base.as_posix()
    candidates = (
        f"{base_path}.ts",
        f"{base_path}.tsx",
        f"{base_path}.js",
        (base / "index.ts").as_posix(),
        (base / "index.tsx").as_posix(),
        (base / "index.js").as_posix(),
    )
    target = next(
        (candidate for candidate in candidates if candidate in indexed_files),
        None,
    )
    if target is None:
        return None, "not_indexed"
    return target, "not_indexed"


def _relative_javascript_base(
    source_file: str,
    specifier: str,
) -> PurePosixPath | None:
    parts = [*PurePosixPath(source_file).parent.parts]
    for part in specifier.split("/"):
        if part in {"", "."}:
            continue
        if part == "..":
            if not parts:
                return None
            parts.pop()
        else:
            parts.append(part)
    if not parts:
        return None
    return PurePosixPath(*parts)


def _python_package_roots(indexed_files: frozenset[str]) -> tuple[PurePosixPath, ...]:
    package_dirs = {
        PurePosixPath(path).parent
        for path in indexed_files
        if PurePosixPath(path).name == "__init__.py"
    }
    roots = {PurePosixPath(".")}
    roots.update(
        directory.parent
        for directory in package_dirs
        if directory.parent not in package_dirs
    )
    return tuple(sorted(roots, key=lambda path: path.as_posix()))


def _relative_python_base(
    source_file: str,
    specifier: str,
) -> PurePosixPath | None:
    dot_count = len(specifier) - len(specifier.lstrip("."))
    remainder = specifier[dot_count:]
    parts = _dotted_parts(remainder, allow_empty=True)
    if parts is None:
        return None

    base = PurePosixPath(source_file).parent
    for _ in range(dot_count - 1):
        if base == PurePosixPath("."):
            return None
        base = base.parent
    return base.joinpath(*parts)


def _dotted_parts(
    value: str,
    *,
    allow_empty: bool = False,
) -> tuple[str, ...] | None:
    if not value:
        return () if allow_empty else None
    parts = tuple(value.split("."))
    if any(not part or not part.isidentifier() for part in parts):
        return None
    return parts


def _resolve_python_base(
    base: PurePosixPath,
    imported_name: str | None,
    indexed_files: frozenset[str],
) -> str | None:
    if imported_name is not None:
        submodule = _indexed_python_module(base / imported_name, indexed_files)
        if submodule is not None:
            return submodule
    return _indexed_python_module(base, indexed_files)


def _indexed_python_module(
    base: PurePosixPath,
    indexed_files: frozenset[str],
) -> str | None:
    candidates: list[str] = []
    if base != PurePosixPath("."):
        candidates.append(f"{base.as_posix()}.py")
    candidates.append((base / "__init__.py").as_posix())
    return next(
        (candidate for candidate in candidates if candidate in indexed_files),
        None,
    )


def _unresolved(
    raw: RawImport,
    source_id: str,
    reason: ImportUnresolvedReason,
) -> ImportRecord:
    return ImportRecord(
        raw=raw,
        source_id=source_id,
        target_file=None,
        target_package=None,
        target_kind=None,
        target_id=None,
        status="unresolved",
        unresolved_reason=reason,
    )


def _require_file_node(
    file_nodes: Mapping[str, Symbol],
    path: str,
    *,
    field: str,
) -> Symbol:
    node = file_nodes.get(path)
    if node is None or node.kind != "file" or node.file_path != path:
        raise _error(
            "Import path does not identify an indexed file node",
            field=field,
            path=path,
        )
    return node


def _raw_import_to_dict(raw: RawImport) -> dict[str, JSONValue]:
    return {
        "source_file": raw.source_file,
        "language": raw.language,
        "line": raw.line,
        "text": raw.text,
        "specifier": raw.specifier,
        "imported_name": raw.imported_name,
        "type_only": raw.type_only,
        "is_reexport": raw.is_reexport,
        "source_hash": raw.source_hash,
    }


def _raw_import_from_dict(value: Mapping[str, Any]) -> RawImport:
    _require_keys(value, _RAW_IMPORT_FIELDS, "raw import")
    imported_name = value["imported_name"]
    if imported_name is not None:
        imported_name = _nonempty_string(imported_name, "imported_name")
    type_only = _boolean(value["type_only"], "type_only")
    is_reexport = _boolean(value["is_reexport"], "is_reexport")
    line = value["line"]
    if isinstance(line, bool) or not isinstance(line, int) or line < 1:
        raise _error("Import line must be a positive integer", field="line")
    raw = RawImport(
        source_file=_relative_path(value["source_file"], "source_file"),
        language=_nonempty_string(value["language"], "language"),
        line=line,
        text=_nonempty_string(value["text"], "text"),
        specifier=_string(value["specifier"], "specifier"),
        imported_name=imported_name,
        type_only=type_only,
        is_reexport=is_reexport,
        source_hash=_sha256(value["source_hash"], "source_hash"),
    )
    _validate_raw_import(raw)
    return raw


def _validate_raw_import(raw: RawImport) -> None:
    if not isinstance(raw, RawImport):
        raise _error("Import raw observation must be a RawImport", field="raw")
    _relative_path(raw.source_file, "source_file")
    _nonempty_string(raw.language, "language")
    if isinstance(raw.line, bool) or not isinstance(raw.line, int) or raw.line < 1:
        raise _error("Import line must be a positive integer", field="line")
    _nonempty_string(raw.text, "text")
    _string(raw.specifier, "specifier")
    if raw.imported_name is not None:
        _nonempty_string(raw.imported_name, "imported_name")
    _boolean(raw.type_only, "type_only")
    _boolean(raw.is_reexport, "is_reexport")
    _sha256(raw.source_hash, "source_hash")


def _require_keys(value: Mapping[str, Any], expected: set[str], record: str) -> None:
    actual = set(value)
    if actual != expected:
        raise _error(
            f"Invalid graph {record} fields",
            record=record,
            missing=sorted(expected - actual),
            unknown=sorted(actual - expected),
        )


def _relative_path(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value or "\\" in value:
        raise _error(f"Import {field} must be a relative path", field=field)
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts or path.as_posix() != value:
        raise _error(f"Import {field} must be a relative path", field=field)
    return value


def _optional_relative_path(value: Any, field: str) -> str | None:
    return None if value is None else _relative_path(value, field)


def _nonempty_string(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value:
        raise _error(f"Import {field} must be a non-empty string", field=field)
    return value


def _optional_nonempty_string(value: Any, field: str) -> str | None:
    return None if value is None else _nonempty_string(value, field)


def _string(value: Any, field: str) -> str:
    if not isinstance(value, str):
        raise _error(f"Import {field} must be a string", field=field)
    return value


def _boolean(value: Any, field: str) -> bool:
    if not isinstance(value, bool):
        raise _error(f"Import {field} must be a boolean", field=field)
    return value


def _sha256(value: Any, field: str) -> str:
    if not isinstance(value, str) or not _SHA256_RE.fullmatch(value):
        raise _error(f"Import {field} must be a SHA-256 hash", field=field)
    return value


def _error(message: str, **details: Any) -> GraphContractError:
    return GraphContractError(
        "INVALID_GRAPH_SCHEMA",
        message,
        cast(dict[str, JSONValue], details),
    )
