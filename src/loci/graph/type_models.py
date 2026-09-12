"""Immutable graph records for resolved authored type observations."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Any, Literal, TypeAlias

from loci.parser.reference_models import _sha256
from loci.parser.type_models import RawTypeObservation, valid_type_import_path


TypeSupportKind: TypeAlias = Literal[
    "type_site",
    "owner",
    "definition",
    "import_binding",
    "local_export",
    "reexport",
    "package_clause",
]
TypeRelationStatus: TypeAlias = Literal["resolved", "unresolved"]
TypeResolutionBasis: TypeAlias = Literal[
    "lexical_binding",
    "package_binding",
    "direct_binding",
    "qualified_member",
    "reexport_chain",
]
TypeCandidateUniverse: TypeAlias = Literal[
    "lexical_scope",
    "package_scope",
    "import_surface",
    "unavailable",
]
TypeUnresolvedReason: TypeAlias = Literal[
    "unsupported_syntax",
    "unsupported_owner",
    "ambiguous_owner",
    "type_parameter",
    "binding_shadowed",
    "unsupported_configuration",
    "binding_not_found",
    "binding_ambiguous",
    "binding_unindexed",
    "target_not_indexed",
    "ambiguous_target",
    "unsupported_target",
    "unsupported_reference",
    "import_unresolved",
    "binding_limit",
    "self_heritage",
    "type_only_value",
]

TYPE_SUPPORT_KINDS = frozenset(
    {"type_site", "owner", "definition", "import_binding", "local_export", "reexport", "package_clause"}
)
TYPE_RELATION_STATUSES = frozenset({"resolved", "unresolved"})
TYPE_RESOLUTION_BASES = frozenset(
    {"lexical_binding", "package_binding", "direct_binding", "qualified_member", "reexport_chain"}
)
TYPE_CANDIDATE_UNIVERSES = frozenset(
    {"lexical_scope", "package_scope", "import_surface", "unavailable"}
)
TYPE_UNRESOLVED_REASONS = frozenset(
    {
        "unsupported_syntax",
        "unsupported_owner",
        "ambiguous_owner",
        "type_parameter",
        "binding_shadowed",
        "unsupported_configuration",
        "binding_not_found",
        "binding_ambiguous",
        "binding_unindexed",
        "target_not_indexed",
        "ambiguous_target",
        "unsupported_target",
        "unsupported_reference",
        "import_unresolved",
        "binding_limit",
        "self_heritage",
        "type_only_value",
    }
)
MAX_TYPE_CANDIDATES = 16
MAX_TYPE_SUPPORT_RECORDS = 256


def _require_fields(value: Any, expected: set[str], record: str) -> None:
    if not isinstance(value, Mapping):
        raise ValueError(f"{record} must be an object with exact fields")
    actual = set(value)
    if actual != expected:
        raise ValueError(
            f"{record} fields must match exactly; "
            f"missing={sorted(expected - actual)}, "
            f"unknown={sorted(repr(field) for field in actual - expected)}"
        )


def _nonempty_string(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{field} must be a non-empty string")
    return value


def _relative_path(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value or "\\" in value:
        raise ValueError(f"{field} must be a normalized relative path")
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts or path.as_posix() != value:
        raise ValueError(f"{field} must be a normalized relative path")
    return value


def _integer(value: Any, field: str, *, minimum: int = 0) -> int:
    if type(value) is not int or value < minimum:
        raise ValueError(f"{field} must be an integer greater than or equal to {minimum}")
    return value


def _boolean(value: Any, field: str) -> bool:
    if type(value) is not bool:
        raise ValueError(f"{field} must be a boolean")
    return value


def _tuple(value: Any, field: str, item_type: type) -> tuple[Any, ...]:
    if not isinstance(value, tuple):
        raise ValueError(f"{field} must be an immutable tuple")
    if any(not isinstance(item, item_type) for item in value):
        raise ValueError(f"{field} contains an invalid item")
    return value


def _list(value: Any, field: str) -> list[Any]:
    if not isinstance(value, list):
        raise ValueError(f"{field} must be a list")
    return value


@dataclass(frozen=True, slots=True)
class TypeSupport:
    kind: TypeSupportKind
    file: str
    line: int
    content_hash: str
    endpoint_id: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.kind, str) or self.kind not in TYPE_SUPPORT_KINDS:
            raise ValueError("kind must be a supported type support kind")
        _relative_path(self.file, "file")
        _integer(self.line, "line", minimum=1)
        _sha256(self.content_hash, "content_hash")
        if self.endpoint_id is not None:
            _nonempty_string(self.endpoint_id, "endpoint_id")

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "file": self.file,
            "line": self.line,
            "content_hash": self.content_hash,
            "endpoint_id": self.endpoint_id,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> TypeSupport:
        _require_fields(
            value,
            {"kind", "file", "line", "content_hash", "endpoint_id"},
            "type support",
        )
        return cls(
            kind=value["kind"],
            file=value["file"],
            line=value["line"],
            content_hash=value["content_hash"],
            endpoint_id=value["endpoint_id"],
        )


@dataclass(frozen=True, slots=True)
class TypeControl:
    file: str
    content_hash: str

    def __post_init__(self) -> None:
        _relative_path(self.file, "file")
        _sha256(self.content_hash, "content_hash")

    def to_dict(self) -> dict[str, Any]:
        return {"file": self.file, "content_hash": self.content_hash}

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> TypeControl:
        _require_fields(value, {"file", "content_hash"}, "type control")
        return cls(file=value["file"], content_hash=value["content_hash"])


@dataclass(frozen=True, slots=True)
class TypeRelationRecord:
    raw: RawTypeObservation
    source_id: str | None
    source_kind: str | None
    target_id: str | None
    target_file: str | None
    target_kind: str | None
    status: TypeRelationStatus
    unresolved_reason: TypeUnresolvedReason | None
    resolution_basis: TypeResolutionBasis | None
    support: tuple[TypeSupport, ...]
    resolution_controls: tuple[TypeControl, ...]
    candidate_universe: TypeCandidateUniverse
    candidate_scope_file: str | None
    candidate_ids: tuple[str, ...]
    candidates_complete: bool
    candidates_truncated: int

    def __post_init__(self) -> None:
        if not isinstance(self.raw, RawTypeObservation):
            raise ValueError("raw must be a RawTypeObservation")
        if self.source_id is None:
            if self.source_kind is not None:
                raise ValueError("source_kind requires source_id")
        else:
            _nonempty_string(self.source_id, "source_id")
            _nonempty_string(self.source_kind, "source_kind")
        if not isinstance(self.status, str) or self.status not in TYPE_RELATION_STATUSES:
            raise ValueError("status must be resolved or unresolved")
        if self.unresolved_reason is not None and (
            not isinstance(self.unresolved_reason, str)
            or self.unresolved_reason not in TYPE_UNRESOLVED_REASONS
        ):
            raise ValueError("unresolved_reason is not controlled")
        if self.resolution_basis is not None and (
            not isinstance(self.resolution_basis, str)
            or self.resolution_basis not in TYPE_RESOLUTION_BASES
        ):
            raise ValueError("resolution_basis is not supported")
        if (
            not isinstance(self.candidate_universe, str)
            or self.candidate_universe not in TYPE_CANDIDATE_UNIVERSES
        ):
            raise ValueError("candidate_universe is not supported")
        if self.candidate_scope_file is not None:
            _relative_path(self.candidate_scope_file, "candidate_scope_file")
        _tuple(self.support, "support", TypeSupport)
        _tuple(self.resolution_controls, "resolution_controls", TypeControl)
        if len(self.support) > MAX_TYPE_SUPPORT_RECORDS:
            raise ValueError("support exceeds the type support limit")
        if len({item.file for item in self.resolution_controls}) != len(self.resolution_controls):
            raise ValueError("resolution control files must be unique")
        _tuple(self.candidate_ids, "candidate_ids", str)
        if len(self.candidate_ids) > MAX_TYPE_CANDIDATES:
            raise ValueError("candidate_ids exceeds the type candidate limit")
        if len(set(self.candidate_ids)) != len(self.candidate_ids):
            raise ValueError("candidate_ids must be unique")
        for candidate_id in self.candidate_ids:
            _nonempty_string(candidate_id, "candidate_id")
        _boolean(self.candidates_complete, "candidates_complete")
        _integer(self.candidates_truncated, "candidates_truncated")
        if self.candidates_complete and self.candidates_truncated:
            raise ValueError("complete candidates cannot report truncation")
        if self.candidate_universe == "unavailable":
            if self.candidate_scope_file is not None:
                raise ValueError("unavailable candidate universes cannot name a scope file")
            if self.candidates_complete:
                raise ValueError("unavailable candidate universes cannot be complete")
        elif self.candidate_scope_file is None:
            raise ValueError("available candidate universes require a scope file")
        support_kinds = {item.kind for item in self.support}
        if "type_site" not in support_kinds:
            raise ValueError("type relation support must include the source type site")

        if self.status == "resolved":
            if self.source_id is None or self.source_kind is None:
                raise ValueError("resolved relations require a source endpoint")
            if self.unresolved_reason is not None:
                raise ValueError("resolved relations cannot have an unresolved reason")
            if self.resolution_basis is None:
                raise ValueError("resolved relations require a resolution basis")
            if self.target_id is None or self.target_file is None or self.target_kind is None:
                raise ValueError("resolved relations require a complete target endpoint")
            _nonempty_string(self.target_id, "target_id")
            _relative_path(self.target_file, "target_file")
            _nonempty_string(self.target_kind, "target_kind")
            if not self.candidates_complete or self.candidates_truncated:
                raise ValueError("resolved relations require a complete candidate universe")
            if self.candidate_ids != (self.target_id,):
                raise ValueError("resolved relations require one candidate equal to the target")
            if not self.raw.candidates_complete or self.raw.candidates_truncated:
                raise ValueError("resolved relations require a complete raw candidate set")
            if self.resolution_basis == "lexical_binding":
                if (
                    self.candidate_universe != "lexical_scope"
                    or self.raw.binding_state != "local"
                    or len(self.raw.local_bindings) != 1
                    or len(self.raw.path) != 1
                ):
                    raise ValueError("lexical resolutions require local lexical evidence")
            elif self.resolution_basis == "package_binding":
                if self.raw.language != "go" or self.raw.binding_state != "package" or self.candidate_universe != "package_scope" or "package_clause" not in support_kinds:
                    raise ValueError("package resolutions require Go package evidence")
            else:
                if self.candidate_universe != "import_surface":
                    raise ValueError("import resolutions require an import surface")
                if self.raw.language == "go" and self.raw.binding_state == "deferred":
                    if self.resolution_basis != "qualified_member" or "package_clause" not in support_kinds:
                        raise ValueError("deferred package lookup requires qualified package evidence")
                elif self.raw.binding_state != "imported" or len(self.raw.import_bindings) != 1:
                    raise ValueError("import resolutions require imported binding evidence")
                if not all(valid_type_import_path(self.raw.language, self.raw.path, binding) for binding in self.raw.import_bindings):
                    raise ValueError("resolved import paths must match their binding kind")
            if "owner" not in support_kinds or "definition" not in support_kinds:
                raise ValueError(
                    "resolved relations require type-site, owner, and definition support"
                )
        else:
            if self.target_id is not None or self.target_file is not None or self.target_kind is not None:
                raise ValueError("unresolved relations cannot carry a target endpoint")
            if self.unresolved_reason is None:
                raise ValueError("unresolved relations require a controlled reason")
            if self.resolution_basis is not None:
                raise ValueError("unresolved relations cannot carry a resolution basis")

    @property
    def resolution(self) -> str | None:
        """Return the public graph resolution tier derived from the basis."""

        if self.status != "resolved":
            return None
        if self.resolution_basis in {"lexical_binding", "package_binding"}:
            return "exact"
        return "import-resolved"

    def to_dict(self) -> dict[str, Any]:
        return {
            "raw": self.raw.to_dict(),
            "source_id": self.source_id,
            "source_kind": self.source_kind,
            "target_id": self.target_id,
            "target_file": self.target_file,
            "target_kind": self.target_kind,
            "status": self.status,
            "unresolved_reason": self.unresolved_reason,
            "resolution_basis": self.resolution_basis,
            "support": [item.to_dict() for item in self.support],
            "resolution_controls": [item.to_dict() for item in self.resolution_controls],
            "candidate_universe": self.candidate_universe,
            "candidate_scope_file": self.candidate_scope_file,
            "candidate_ids": list(self.candidate_ids),
            "candidates_complete": self.candidates_complete,
            "candidates_truncated": self.candidates_truncated,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> TypeRelationRecord:
        _require_fields(
            value,
            {
                "raw",
                "source_id",
                "source_kind",
                "target_id",
                "target_file",
                "target_kind",
                "status",
                "unresolved_reason",
                "resolution_basis",
                "support",
                "resolution_controls",
                "candidate_universe",
                "candidate_scope_file",
                "candidate_ids",
                "candidates_complete",
                "candidates_truncated",
            },
            "type relation record",
        )
        if not isinstance(value["raw"], Mapping):
            raise ValueError("raw must be an object")
        support = _list(value["support"], "support")
        controls = _list(value["resolution_controls"], "resolution_controls")
        candidate_ids = _list(value["candidate_ids"], "candidate_ids")
        return cls(
            raw=RawTypeObservation.from_dict(value["raw"]),
            source_id=value["source_id"],
            source_kind=value["source_kind"],
            target_id=value["target_id"],
            target_file=value["target_file"],
            target_kind=value["target_kind"],
            status=value["status"],
            unresolved_reason=value["unresolved_reason"],
            resolution_basis=value["resolution_basis"],
            support=tuple(TypeSupport.from_dict(item) for item in support),
            resolution_controls=tuple(
                TypeControl.from_dict(item) for item in controls
            ),
            candidate_universe=value["candidate_universe"],
            candidate_scope_file=value["candidate_scope_file"],
            candidate_ids=tuple(candidate_ids),
            candidates_complete=value["candidates_complete"],
            candidates_truncated=value["candidates_truncated"],
        )


__all__ = [
    "MAX_TYPE_CANDIDATES",
    "MAX_TYPE_SUPPORT_RECORDS",
    "TYPE_CANDIDATE_UNIVERSES",
    "TYPE_RELATION_STATUSES",
    "TYPE_RESOLUTION_BASES",
    "TYPE_SUPPORT_KINDS",
    "TYPE_UNRESOLVED_REASONS",
    "TypeCandidateUniverse",
    "TypeControl",
    "TypeRelationRecord",
    "TypeRelationStatus",
    "TypeResolutionBasis",
    "TypeSupport",
    "TypeSupportKind",
    "TypeUnresolvedReason",
]
