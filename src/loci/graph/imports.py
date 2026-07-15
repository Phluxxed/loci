from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Any, Literal, Mapping, TypeAlias, cast

from loci.parser.imports import ImportUnresolvedReason, RawImport

from .contracts import GraphContractError, JSONValue


ImportStatus: TypeAlias = Literal["resolved", "unresolved"]
_IMPORT_STATUSES = frozenset({"resolved", "unresolved"})
_UNRESOLVED_REASONS = frozenset({
    "external",
    "not_indexed",
    "ambiguous",
    "unsupported_language",
    "invalid_specifier",
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
    "target_id",
    "status",
    "unresolved_reason",
}
_SHA256_RE = re.compile(r"[0-9a-f]{64}")


@dataclass(frozen=True, slots=True)
class ImportRecord:
    raw: RawImport
    source_id: str
    target_file: str | None
    target_id: str | None
    status: ImportStatus
    unresolved_reason: ImportUnresolvedReason | None

    def __post_init__(self) -> None:
        _validate_raw_import(self.raw)
        _nonempty_string(self.source_id, "source_id")
        if self.target_file is not None:
            _relative_path(self.target_file, "target_file")
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
            if self.target_file is None or self.target_id is None:
                raise _error("Resolved import requires a target file and ID")
            if self.unresolved_reason is not None:
                raise _error("Resolved import cannot have an unresolved reason")
        else:
            if self.target_file is not None or self.target_id is not None:
                raise _error("Unresolved import cannot have a target file or ID")
            if self.unresolved_reason is None:
                raise _error("Unresolved import requires an unresolved reason")

    def to_dict(self) -> dict[str, JSONValue]:
        return {
            "raw": _raw_import_to_dict(self.raw),
            "source_id": self.source_id,
            "target_file": self.target_file,
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
            target_id=target_id,
            status=cast(ImportStatus, status),
            unresolved_reason=cast(ImportUnresolvedReason | None, unresolved_reason),
        )


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
