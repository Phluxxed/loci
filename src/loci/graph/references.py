from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Any, Literal, Mapping, Sequence, TypeAlias, cast

from loci.parser.imports import ImportUnresolvedReason
from loci.parser.reference_models import ImportBinding, RawSymbolReference

from .contracts import GraphContractError, JSONValue
from .rust_crates import RustResolutionConfiguration


MAX_REFERENCE_REEXPORT_PASSES = 128
MAX_REFERENCE_SUPPORT_RECORDS = 256

ReferenceStatus: TypeAlias = Literal["resolved", "unresolved"]
ReferenceUnresolvedReason: TypeAlias = Literal[
    "import_unresolved",
    "binding_shadowed",
    "ambiguous_binding",
    "ambiguous_source",
    "target_not_indexed",
    "target_inaccessible",
    "ambiguous_target",
    "unsupported_reference",
    "configuration_divergent",
]
ReferenceResolutionBasis: TypeAlias = Literal[
    "direct_binding",
    "qualified_member",
    "reexport_chain",
]
ReferenceSupportKind: TypeAlias = Literal[
    "import_binding",
    "local_export",
    "reexport",
    "definition",
]

_REFERENCE_STATUSES = frozenset({"resolved", "unresolved"})
_REFERENCE_UNRESOLVED_REASONS = frozenset({
    "import_unresolved",
    "binding_shadowed",
    "ambiguous_binding",
    "ambiguous_source",
    "target_not_indexed",
    "target_inaccessible",
    "ambiguous_target",
    "unsupported_reference",
    "configuration_divergent",
})
_REFERENCE_RESOLUTION_BASES = frozenset({
    "direct_binding",
    "qualified_member",
    "reexport_chain",
})
_REFERENCE_SUPPORT_KINDS = frozenset({
    "import_binding",
    "local_export",
    "reexport",
    "definition",
})
_IMPORT_UNRESOLVED_REASONS = frozenset({
    "external",
    "not_indexed",
    "ambiguous",
    "unsupported_language",
    "invalid_specifier",
    "inaccessible",
    "unsupported_configuration",
})
_RUST_RESOLUTION_CONFIGURATIONS = frozenset({
    "unconditional",
    "declared_possible",
})
_REFERENCE_SUPPORT_FIELDS = {
    "kind",
    "file",
    "line",
    "content_hash",
    "endpoint_id",
}
_SYMBOL_REFERENCE_RECORD_FIELDS = {
    "raw",
    "binding",
    "source_id",
    "source_kind",
    "import_source_id",
    "import_target_id",
    "target_file",
    "target_id",
    "target_kind",
    "status",
    "unresolved_reason",
    "import_unresolved_reason",
    "resolution_basis",
    "support",
    "resolution_control_files",
    "resolution_configuration",
}
_SHA256_RE = re.compile(r"[0-9a-f]{64}")


@dataclass(frozen=True, slots=True)
class ReferenceSupport:
    kind: ReferenceSupportKind
    file: str
    line: int
    content_hash: str
    endpoint_id: str

    def __post_init__(self) -> None:
        if not isinstance(self.kind, str) or self.kind not in _REFERENCE_SUPPORT_KINDS:
            raise _error("Invalid reference support kind", field="kind")
        _relative_path(self.file, "file")
        _positive_integer(self.line, "line")
        _sha256(self.content_hash, "content_hash")
        _nonempty_string(self.endpoint_id, "endpoint_id")

    def to_dict(self) -> dict[str, JSONValue]:
        return {
            "kind": self.kind,
            "file": self.file,
            "line": self.line,
            "content_hash": self.content_hash,
            "endpoint_id": self.endpoint_id,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> ReferenceSupport:
        _require_keys(value, _REFERENCE_SUPPORT_FIELDS, "reference support")
        kind = value["kind"]
        if not isinstance(kind, str) or kind not in _REFERENCE_SUPPORT_KINDS:
            raise _error("Invalid reference support kind", field="kind")
        return cls(
            kind=cast(ReferenceSupportKind, kind),
            file=_relative_path(value["file"], "file"),
            line=_positive_integer(value["line"], "line"),
            content_hash=_sha256(value["content_hash"], "content_hash"),
            endpoint_id=_nonempty_string(value["endpoint_id"], "endpoint_id"),
        )


@dataclass(frozen=True, slots=True)
class SymbolReferenceRecord:
    raw: RawSymbolReference
    binding: ImportBinding | None
    source_id: str
    source_kind: str
    import_source_id: str
    import_target_id: str | None
    target_file: str | None
    target_id: str | None
    target_kind: str | None
    status: ReferenceStatus
    unresolved_reason: ReferenceUnresolvedReason | None
    import_unresolved_reason: ImportUnresolvedReason | None
    resolution_basis: ReferenceResolutionBasis | None
    support: tuple[ReferenceSupport, ...]
    resolution_control_files: tuple[str, ...]
    resolution_configuration: RustResolutionConfiguration | None

    def __post_init__(self) -> None:
        if not isinstance(self.raw, RawSymbolReference):
            raise _error("Reference raw observation must be a RawSymbolReference")
        if self.binding is not None:
            if not isinstance(self.binding, ImportBinding):
                raise _error("Reference binding must be an ImportBinding")
            if self.binding not in self.raw.candidate_bindings:
                raise _error("Reference binding is not a raw candidate", field="binding")
        _nonempty_string(self.source_id, "source_id")
        _nonempty_string(self.source_kind, "source_kind")
        expected_import_source = f"{self.raw.source_file}::__file__#file"
        if self.import_source_id != expected_import_source:
            raise _error(
                "Reference import source must be the source file node",
                field="import_source_id",
            )
        if self.source_kind == "file" and self.source_id != self.import_source_id:
            raise _error("File-owned reference source identity is inconsistent")
        _optional_nonempty_string(self.import_target_id, "import_target_id")
        if self.target_file is not None:
            _relative_path(self.target_file, "target_file")
        _optional_nonempty_string(self.target_id, "target_id")
        _optional_nonempty_string(self.target_kind, "target_kind")
        if not isinstance(self.status, str) or self.status not in _REFERENCE_STATUSES:
            raise _error("Invalid reference status", field="status")
        if self.unresolved_reason is not None and (
            not isinstance(self.unresolved_reason, str)
            or self.unresolved_reason not in _REFERENCE_UNRESOLVED_REASONS
        ):
            raise _error("Invalid reference unresolved reason", field="unresolved_reason")
        if self.import_unresolved_reason is not None and (
            not isinstance(self.import_unresolved_reason, str)
            or self.import_unresolved_reason not in _IMPORT_UNRESOLVED_REASONS
        ):
            raise _error(
                "Invalid underlying import unresolved reason",
                field="import_unresolved_reason",
            )
        if self.resolution_basis is not None and (
            not isinstance(self.resolution_basis, str)
            or self.resolution_basis not in _REFERENCE_RESOLUTION_BASES
        ):
            raise _error("Invalid reference resolution basis", field="resolution_basis")
        _support_tuple(self.support)
        _control_files(self.resolution_control_files)
        if self.resolution_configuration is not None and (
            not isinstance(self.resolution_configuration, str)
            or self.resolution_configuration not in _RUST_RESOLUTION_CONFIGURATIONS
        ):
            raise _error(
                "Invalid reference resolution configuration",
                field="resolution_configuration",
            )
        self._validate_language_provenance()
        self._validate_outcome()

    def _validate_language_provenance(self) -> None:
        language = self.raw.language
        if language not in {"javascript", "typescript", "rust"} and (
            self.resolution_control_files or self.resolution_configuration is not None
        ):
            raise _error("Reference language cannot carry resolution provenance")
        if language != "rust" and self.resolution_configuration is not None:
            raise _error("Only Rust references may carry resolution configuration")

    def _validate_outcome(self) -> None:
        if self.status == "resolved":
            if self.binding is None:
                raise _error("Resolved reference requires one selected binding")
            if self.raw.binding_state not in {"definite", "deferred"}:
                raise _error("Resolved reference requires a resolvable binding state")
            if any(
                value is None
                for value in (
                    self.import_target_id,
                    self.target_file,
                    self.target_id,
                    self.target_kind,
                    self.resolution_basis,
                )
            ):
                raise _error("Resolved reference requires complete target identity")
            if self.unresolved_reason is not None:
                raise _error("Resolved reference cannot have an unresolved reason")
            if self.import_unresolved_reason is not None:
                raise _error("Resolved reference cannot have an import failure")
            if not self.support:
                raise _error("Resolved reference requires support")
            if self.raw.language == "rust" and self.resolution_configuration is None:
                raise _error("Resolved Rust reference requires configuration")
            return

        if any(
            value is not None
            for value in (
                self.target_file,
                self.target_id,
                self.target_kind,
                self.resolution_basis,
                self.resolution_configuration,
            )
        ):
            raise _error("Unresolved reference cannot have a final target or basis")
        if self.unresolved_reason is None:
            raise _error("Unresolved reference requires an unresolved reason")
        if self.binding is None and self.unresolved_reason != "ambiguous_binding":
            raise _error("Unresolved reference requires its selected binding")
        if (
            self.import_unresolved_reason is not None
            and self.unresolved_reason != "import_unresolved"
        ):
            raise _error("Import failure requires import_unresolved reference outcome")
        expected_by_state = {
            "shadowed": "binding_shadowed",
            "ambiguous": "ambiguous_binding",
            "unsupported": "unsupported_reference",
        }
        expected = expected_by_state.get(self.raw.binding_state)
        if expected is not None and self.unresolved_reason != expected:
            raise _error("Reference outcome does not match its binding state")

    def to_dict(self) -> dict[str, JSONValue]:
        return cast(
            dict[str, JSONValue],
            {
                "raw": self.raw.to_dict(),
                "binding": self.binding.to_dict() if self.binding is not None else None,
                "source_id": self.source_id,
                "source_kind": self.source_kind,
                "import_source_id": self.import_source_id,
                "import_target_id": self.import_target_id,
                "target_file": self.target_file,
                "target_id": self.target_id,
                "target_kind": self.target_kind,
                "status": self.status,
                "unresolved_reason": self.unresolved_reason,
                "import_unresolved_reason": self.import_unresolved_reason,
                "resolution_basis": self.resolution_basis,
                "support": [item.to_dict() for item in self.support],
                "resolution_control_files": list(self.resolution_control_files),
                "resolution_configuration": self.resolution_configuration,
            },
        )

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> SymbolReferenceRecord:
        _require_keys(value, _SYMBOL_REFERENCE_RECORD_FIELDS, "symbol reference record")
        raw_value = value["raw"]
        if not isinstance(raw_value, Mapping):
            raise _error("Reference raw observation must be an object", field="raw")
        binding_value = value["binding"]
        if binding_value is not None and not isinstance(binding_value, Mapping):
            raise _error("Reference binding must be an object", field="binding")
        support_value = value["support"]
        if not isinstance(support_value, list):
            raise _error("Reference support must be a list", field="support")
        controls_value = value["resolution_control_files"]
        if not isinstance(controls_value, list):
            raise _error(
                "Reference resolution control files must be a list",
                field="resolution_control_files",
            )
        return cls(
            raw=RawSymbolReference.from_dict(raw_value),
            binding=(
                ImportBinding.from_dict(binding_value)
                if binding_value is not None
                else None
            ),
            source_id=_nonempty_string(value["source_id"], "source_id"),
            source_kind=_nonempty_string(value["source_kind"], "source_kind"),
            import_source_id=_nonempty_string(
                value["import_source_id"],
                "import_source_id",
            ),
            import_target_id=_optional_nonempty_string(
                value["import_target_id"],
                "import_target_id",
            ),
            target_file=_optional_relative_path(value["target_file"], "target_file"),
            target_id=_optional_nonempty_string(value["target_id"], "target_id"),
            target_kind=_optional_nonempty_string(value["target_kind"], "target_kind"),
            status=cast(
                ReferenceStatus,
                _literal(value["status"], _REFERENCE_STATUSES, "status"),
            ),
            unresolved_reason=cast(
                ReferenceUnresolvedReason | None,
                _optional_literal(
                    value["unresolved_reason"],
                    _REFERENCE_UNRESOLVED_REASONS,
                    "unresolved_reason",
                ),
            ),
            import_unresolved_reason=cast(
                ImportUnresolvedReason | None,
                _optional_literal(
                    value["import_unresolved_reason"],
                    _IMPORT_UNRESOLVED_REASONS,
                    "import_unresolved_reason",
                ),
            ),
            resolution_basis=cast(
                ReferenceResolutionBasis | None,
                _optional_literal(
                    value["resolution_basis"],
                    _REFERENCE_RESOLUTION_BASES,
                    "resolution_basis",
                ),
            ),
            support=tuple(ReferenceSupport.from_dict(item) for item in support_value),
            resolution_control_files=tuple(
                _relative_path(item, "resolution_control_files")
                for item in controls_value
            ),
            resolution_configuration=cast(
                RustResolutionConfiguration | None,
                _optional_literal(
                    value["resolution_configuration"],
                    _RUST_RESOLUTION_CONFIGURATIONS,
                    "resolution_configuration",
                ),
            ),
        )


def _support_tuple(value: Any) -> None:
    if not isinstance(value, tuple):
        raise _error("Reference support must be an immutable tuple", field="support")
    if len(value) > MAX_REFERENCE_SUPPORT_RECORDS:
        raise _error("Reference support exceeds the support limit", field="support")
    if any(not isinstance(item, ReferenceSupport) for item in value):
        raise _error("Reference support contains an invalid item", field="support")


def _control_files(value: Any) -> None:
    if not isinstance(value, tuple):
        raise _error(
            "Reference resolution control files must be an immutable tuple",
            field="resolution_control_files",
        )
    for item in value:
        _relative_path(item, "resolution_control_files")
    if value != tuple(sorted(set(value))):
        raise _error(
            "Reference resolution control files must be unique and sorted",
            field="resolution_control_files",
        )


def _require_keys(value: Mapping[str, Any], expected: set[str], record: str) -> None:
    if not isinstance(value, Mapping) or set(value) != expected:
        raise _error(
            f"Invalid {record} fields",
            missing=sorted(expected - set(value)),
            unknown=sorted(set(value) - expected),
        )


def _relative_path(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value or "\\" in value:
        raise _error(f"Reference {field} must be a relative path", field=field)
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts or path.as_posix() != value:
        raise _error(f"Reference {field} must be a relative path", field=field)
    return value


def _optional_relative_path(value: Any, field: str) -> str | None:
    return None if value is None else _relative_path(value, field)


def _nonempty_string(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value:
        raise _error(f"Reference {field} must be a non-empty string", field=field)
    return value


def _optional_nonempty_string(value: Any, field: str) -> str | None:
    return None if value is None else _nonempty_string(value, field)


def _positive_integer(value: Any, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise _error(f"Reference {field} must be a positive integer", field=field)
    return value


def _sha256(value: Any, field: str) -> str:
    if not isinstance(value, str) or not _SHA256_RE.fullmatch(value):
        raise _error(f"Reference {field} must be a SHA-256 hash", field=field)
    return value


def _literal(value: Any, allowed: frozenset[str], field: str) -> str:
    if not isinstance(value, str) or value not in allowed:
        raise _error(f"Invalid reference {field}", field=field)
    return value


def _optional_literal(
    value: Any,
    allowed: frozenset[str],
    field: str,
) -> str | None:
    return None if value is None else _literal(value, allowed, field)


def _error(message: str, **details: Any) -> GraphContractError:
    return GraphContractError(
        "GRAPH_CONTRACT_INVALID",
        message,
        cast(dict[str, JSONValue], details),
    )
