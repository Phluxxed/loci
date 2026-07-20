from __future__ import annotations

from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Any, Literal, Mapping, TypeAlias


ImportBindingKind: TypeAlias = Literal[
    "symbol",
    "namespace",
    "module",
    "glob",
    "side_effect",
    "blank",
]
BindingState: TypeAlias = Literal[
    "definite",
    "deferred",
    "shadowed",
    "ambiguous",
    "unsupported",
]

MAX_IMPORT_BINDINGS_PER_DECLARATION = 1_024
MAX_SYMBOL_REFERENCES_PER_FILE = 250_000
MAX_LOCAL_EXPORTS_PER_FILE = 100_000
MAX_REFERENCE_PATH_SEGMENTS = 128
MAX_REFERENCE_RESOLUTION_CANDIDATES = 256

_IMPORT_BINDING_KINDS = {
    "symbol",
    "namespace",
    "module",
    "glob",
    "side_effect",
    "blank",
}
_BINDING_STATES = {
    "definite",
    "deferred",
    "shadowed",
    "ambiguous",
    "unsupported",
}


@dataclass(frozen=True, slots=True)
class ImportBinding:
    local_name: str | None
    imported_name: str | None
    exported_name: str | None
    kind: ImportBindingKind
    type_only: bool
    module_level: bool
    declaration_start_byte: int
    scope_start_byte: int
    scope_end_byte: int
    import_line: int
    import_text: str
    import_specifier: str

    def __post_init__(self) -> None:
        _optional_nonempty_string(self.local_name, "local_name")
        _optional_nonempty_string(self.imported_name, "imported_name")
        _optional_nonempty_string(self.exported_name, "exported_name")
        if not isinstance(self.kind, str) or self.kind not in _IMPORT_BINDING_KINDS:
            raise ValueError("kind must be a supported import binding kind")
        _boolean(self.type_only, "type_only")
        _boolean(self.module_level, "module_level")
        declaration = _integer(
            self.declaration_start_byte,
            "declaration_start_byte",
            minimum=0,
        )
        scope_start = _integer(self.scope_start_byte, "scope_start_byte", minimum=0)
        scope_end = _integer(self.scope_end_byte, "scope_end_byte", minimum=1)
        if scope_start > declaration or declaration >= scope_end:
            raise ValueError("declaration_start_byte must be inside the binding scope")
        _integer(self.import_line, "import_line", minimum=1)
        _nonempty_string(self.import_text, "import_text")
        _nonempty_string(self.import_specifier, "import_specifier")
        if self.kind in {"side_effect", "glob"} and any(
            name is not None
            for name in (self.local_name, self.imported_name, self.exported_name)
        ):
            raise ValueError(f"{self.kind} bindings cannot carry names")
        if self.kind == "blank" and (
            self.local_name is not None or self.exported_name is not None
        ):
            raise ValueError("blank bindings cannot introduce or export a name")
        if self.kind in {"symbol", "module"} and (
            self.local_name is None and self.exported_name is None
        ):
            raise ValueError(f"{self.kind} bindings must introduce or export a name")
        if self.kind in {"side_effect", "blank"} and self.type_only:
            raise ValueError(f"{self.kind} bindings cannot be type-only")

    def to_dict(self) -> dict[str, Any]:
        return {
            "local_name": self.local_name,
            "imported_name": self.imported_name,
            "exported_name": self.exported_name,
            "kind": self.kind,
            "type_only": self.type_only,
            "module_level": self.module_level,
            "declaration_start_byte": self.declaration_start_byte,
            "scope_start_byte": self.scope_start_byte,
            "scope_end_byte": self.scope_end_byte,
            "import_line": self.import_line,
            "import_text": self.import_text,
            "import_specifier": self.import_specifier,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> ImportBinding:
        _require_fields(
            value,
            {
                "local_name",
                "imported_name",
                "exported_name",
                "kind",
                "type_only",
                "module_level",
                "declaration_start_byte",
                "scope_start_byte",
                "scope_end_byte",
                "import_line",
                "import_text",
                "import_specifier",
            },
            "import binding",
        )
        return cls(
            local_name=value["local_name"],
            imported_name=value["imported_name"],
            exported_name=value["exported_name"],
            kind=value["kind"],
            type_only=value["type_only"],
            module_level=value["module_level"],
            declaration_start_byte=value["declaration_start_byte"],
            scope_start_byte=value["scope_start_byte"],
            scope_end_byte=value["scope_end_byte"],
            import_line=value["import_line"],
            import_text=value["import_text"],
            import_specifier=value["import_specifier"],
        )


@dataclass(frozen=True, slots=True)
class RawLocalExport:
    source_file: str
    language: str
    line: int
    text: str
    local_name: str | None
    exported_name: str
    type_only: bool
    definition_start_byte: int | None
    definition_end_byte: int | None
    source_hash: str

    def __post_init__(self) -> None:
        _relative_path(self.source_file, "source_file")
        _nonempty_string(self.language, "language")
        _integer(self.line, "line", minimum=1)
        _nonempty_string(self.text, "text")
        _optional_nonempty_string(self.local_name, "local_name")
        _nonempty_string(self.exported_name, "exported_name")
        _boolean(self.type_only, "type_only")
        if (self.definition_start_byte is None) != (self.definition_end_byte is None):
            raise ValueError("definition byte fields must both be present or absent")
        if self.definition_start_byte is not None:
            start = _integer(
                self.definition_start_byte,
                "definition_start_byte",
                minimum=0,
            )
            end = _integer(
                self.definition_end_byte,
                "definition_end_byte",
                minimum=0,
            )
            if start >= end:
                raise ValueError("definition byte range must be non-empty and ordered")
        _sha256(self.source_hash, "source_hash")

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_file": self.source_file,
            "language": self.language,
            "line": self.line,
            "text": self.text,
            "local_name": self.local_name,
            "exported_name": self.exported_name,
            "type_only": self.type_only,
            "definition_start_byte": self.definition_start_byte,
            "definition_end_byte": self.definition_end_byte,
            "source_hash": self.source_hash,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> RawLocalExport:
        _require_fields(
            value,
            {
                "source_file",
                "language",
                "line",
                "text",
                "local_name",
                "exported_name",
                "type_only",
                "definition_start_byte",
                "definition_end_byte",
                "source_hash",
            },
            "local export",
        )
        return cls(
            source_file=value["source_file"],
            language=value["language"],
            line=value["line"],
            text=value["text"],
            local_name=value["local_name"],
            exported_name=value["exported_name"],
            type_only=value["type_only"],
            definition_start_byte=value["definition_start_byte"],
            definition_end_byte=value["definition_end_byte"],
            source_hash=value["source_hash"],
        )


@dataclass(frozen=True, slots=True)
class RawSymbolReference:
    source_file: str
    language: str
    line: int
    column: int
    start_byte: int
    end_byte: int
    text: str
    path: tuple[str, ...]
    candidate_bindings: tuple[ImportBinding, ...]
    binding_state: BindingState
    source_hash: str

    def __post_init__(self) -> None:
        _relative_path(self.source_file, "source_file")
        _nonempty_string(self.language, "language")
        _integer(self.line, "line", minimum=1)
        _integer(self.column, "column", minimum=1)
        start = _integer(self.start_byte, "start_byte", minimum=0)
        end = _integer(self.end_byte, "end_byte", minimum=0)
        if start >= end:
            raise ValueError("reference byte range must be non-empty and ordered")
        _nonempty_string(self.text, "text")
        _typed_tuple(self.path, "path", str)
        if not self.path or len(self.path) > MAX_REFERENCE_PATH_SEGMENTS:
            raise ValueError("path must contain a bounded number of segments")
        for segment in self.path:
            _nonempty_string(segment, "path segment")
        _typed_tuple(self.candidate_bindings, "candidate_bindings", ImportBinding)
        if not self.candidate_bindings:
            raise ValueError("candidate_bindings cannot be empty")
        if len(self.candidate_bindings) > MAX_REFERENCE_RESOLUTION_CANDIDATES:
            raise ValueError("candidate_bindings exceeds the candidate limit")
        if (
            not isinstance(self.binding_state, str)
            or self.binding_state not in _BINDING_STATES
        ):
            raise ValueError("binding_state must be a supported state")
        if self.binding_state == "definite" and len(self.candidate_bindings) != 1:
            raise ValueError("definite references require exactly one candidate")
        if self.binding_state == "ambiguous" and len(self.candidate_bindings) < 2:
            raise ValueError("ambiguous references require multiple candidates")
        if self.binding_state == "deferred":
            if self.language != "go" or any(
                binding.kind != "namespace" or binding.local_name is not None
                for binding in self.candidate_bindings
            ):
                raise ValueError(
                    "deferred references require unresolved Go package bindings"
                )
        elif any(binding.local_name is None for binding in self.candidate_bindings):
            raise ValueError("non-deferred reference candidates must bind a local name")
        for binding in self.candidate_bindings:
            if not (
                binding.scope_start_byte <= start
                and end <= binding.scope_end_byte
            ):
                raise ValueError("candidate binding scope must contain the reference")
            if binding.local_name is not None and binding.local_name != self.path[0]:
                raise ValueError("candidate binding local name must match the path root")
        _sha256(self.source_hash, "source_hash")

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_file": self.source_file,
            "language": self.language,
            "line": self.line,
            "column": self.column,
            "start_byte": self.start_byte,
            "end_byte": self.end_byte,
            "text": self.text,
            "path": list(self.path),
            "candidate_bindings": [
                binding.to_dict() for binding in self.candidate_bindings
            ],
            "binding_state": self.binding_state,
            "source_hash": self.source_hash,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> RawSymbolReference:
        _require_fields(
            value,
            {
                "source_file",
                "language",
                "line",
                "column",
                "start_byte",
                "end_byte",
                "text",
                "path",
                "candidate_bindings",
                "binding_state",
                "source_hash",
            },
            "symbol reference",
        )
        path = _list(value["path"], "path")
        candidates = _list(value["candidate_bindings"], "candidate_bindings")
        return cls(
            source_file=value["source_file"],
            language=value["language"],
            line=value["line"],
            column=value["column"],
            start_byte=value["start_byte"],
            end_byte=value["end_byte"],
            text=value["text"],
            path=tuple(path),
            candidate_bindings=tuple(
                ImportBinding.from_dict(candidate) for candidate in candidates
            ),
            binding_state=value["binding_state"],
            source_hash=value["source_hash"],
        )


@dataclass(frozen=True, slots=True)
class ReferenceExtractionBatch:
    exports: tuple[RawLocalExport, ...]
    references: tuple[RawSymbolReference, ...]

    def __post_init__(self) -> None:
        _typed_tuple(self.exports, "exports", RawLocalExport)
        _typed_tuple(self.references, "references", RawSymbolReference)
        if len(self.exports) > MAX_LOCAL_EXPORTS_PER_FILE:
            raise ValueError("exports exceeds the per-file limit")
        if len(self.references) > MAX_SYMBOL_REFERENCES_PER_FILE:
            raise ValueError("references exceeds the per-file limit")

    def to_dict(self) -> dict[str, Any]:
        return {
            "exports": [export.to_dict() for export in self.exports],
            "references": [reference.to_dict() for reference in self.references],
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> ReferenceExtractionBatch:
        _require_fields(value, {"exports", "references"}, "reference extraction batch")
        exports = _list(value["exports"], "exports")
        references = _list(value["references"], "references")
        return cls(
            exports=tuple(RawLocalExport.from_dict(export) for export in exports),
            references=tuple(
                RawSymbolReference.from_dict(reference) for reference in references
            ),
        )


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


def _optional_nonempty_string(value: Any, field: str) -> str | None:
    if value is None:
        return None
    return _nonempty_string(value, field)


def _boolean(value: Any, field: str) -> bool:
    if not isinstance(value, bool):
        raise ValueError(f"{field} must be a boolean")
    return value


def _integer(value: Any, field: str, *, minimum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise ValueError(f"{field} must be an integer greater than or equal to {minimum}")
    return value


def _relative_path(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value or "\\" in value:
        raise ValueError(f"{field} must be a normalized relative path")
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts or path.as_posix() != value:
        raise ValueError(f"{field} must be a normalized relative path")
    return value


def _sha256(value: Any, field: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise ValueError(f"{field} must be a lowercase SHA-256 digest")
    return value


def _typed_tuple(value: Any, field: str, item_type: type) -> tuple[Any, ...]:
    if not isinstance(value, tuple):
        raise ValueError(f"{field} must be an immutable tuple")
    if any(not isinstance(item, item_type) for item in value):
        raise ValueError(f"{field} contains an invalid item")
    return value


def _list(value: Any, field: str) -> list[Any]:
    if not isinstance(value, list):
        raise ValueError(f"{field} must be a JSON array")
    return value
