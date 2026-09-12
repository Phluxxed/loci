"""Immutable records emitted by authored type observation extractors.

The parser records deliberately contain only authored source evidence.  Graph
resolution is kept in :mod:`loci.graph.type_models` so raw observations can be
cached and replayed without carrying inferred endpoints.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Any, Literal, TypeAlias

from loci.parser.reference_models import ImportBinding


def valid_type_import_path(language: str, path: Sequence[str], binding: Any) -> bool:
    """Validate path shape; graph resolution must still prove its exact endpoint."""
    if language == "typescript":
        return ((binding.kind == "symbol" and len(path) == 1)
                or (binding.kind == "namespace" and len(path) == 2))
    if language != "python":
        return False
    if binding.kind == "symbol":
        # Two segments are valid only when the imported endpoint proves a
        # submodule, which the Python graph resolver checks independently.
        return len(path) in {1, 2} and path[0] == binding.local_name
    if binding.kind != "module" or binding.local_name is None:
        return False
    module = tuple(part for part in binding.import_specifier.split(".") if part)
    if not module:
        return False
    prefix = module if binding.local_name == module[0] else (binding.local_name,)
    return len(path) == len(prefix) + 1 and tuple(path[:-1]) == prefix


TypeDeclarationOwnerKind: TypeAlias = Literal[
    "function",
    "method",
    "class",
    "interface",
    "type",
    "constant",
    "unindexed",
]
TypeBindingKind: TypeAlias = Literal[
    "class",
    "interface",
    "type",
    "enum",
    "function",
    "constant",
    "type_parameter",
    "parameter",
    "namespace",
    "unindexed",
]
TypeNamespace: TypeAlias = Literal["type", "value", "both"]
TypeRelationKind: TypeAlias = Literal["uses_type", "extends", "implements"]
TypeObservationContext: TypeAlias = Literal[
    "annotation",
    "return",
    "property",
    "alias",
    "type_argument",
    "constraint",
    "type_query",
    "heritage",
]
TypeLookupSpace: TypeAlias = Literal["type", "value"]
TypeBindingState: TypeAlias = Literal[
    "local",
    "imported",
    "shadowed",
    "ambiguous",
    "unbound",
    "unsupported",
]

TYPE_DECLARATION_OWNER_KINDS = frozenset(
    {"function", "method", "class", "interface", "type", "constant", "unindexed"}
)
TYPE_BINDING_KINDS = frozenset(
    {
        "class",
        "interface",
        "type",
        "enum",
        "function",
        "constant",
        "type_parameter",
        "parameter",
        "namespace",
        "unindexed",
    }
)
TYPE_NAMESPACES = frozenset({"type", "value", "both"})
TYPE_RELATIONS = frozenset({"uses_type", "extends", "implements"})
TYPE_CONTEXTS = frozenset(
    {
        "annotation",
        "return",
        "property",
        "alias",
        "type_argument",
        "constraint",
        "type_query",
        "heritage",
    }
)
TYPE_LOOKUP_SPACES = frozenset({"type", "value"})
TYPE_BINDING_STATES = frozenset(
    {"local", "imported", "shadowed", "ambiguous", "unbound", "unsupported"}
)

MAX_TYPE_BINDINGS_PER_OBSERVATION = 16
MAX_TYPE_PATH_SEGMENTS = 16
MAX_TYPE_OBSERVATIONS_PER_FILE = 100_000
MAX_UNSUPPORTED_REASON_LENGTH = 256


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
    if type(value) is not bool:
        raise ValueError(f"{field} must be a boolean")
    return value


def _integer(value: Any, field: str, *, minimum: int = 0) -> int:
    if type(value) is not int or value < minimum:
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


def _range(start: Any, end: Any, field: str) -> tuple[int, int]:
    start_value = _integer(start, f"{field}_start_byte")
    end_value = _integer(end, f"{field}_end_byte")
    if start_value >= end_value:
        raise ValueError(f"{field} byte range must be non-empty and ordered")
    return start_value, end_value


@dataclass(frozen=True, slots=True)
class TypeDeclarationOwner:
    kind: TypeDeclarationOwnerKind
    start_byte: int
    end_byte: int

    def __post_init__(self) -> None:
        if not isinstance(self.kind, str) or self.kind not in TYPE_DECLARATION_OWNER_KINDS:
            raise ValueError("kind must be a supported type declaration owner kind")
        _range(self.start_byte, self.end_byte, "owner")

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "start_byte": self.start_byte,
            "end_byte": self.end_byte,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> TypeDeclarationOwner:
        _require_fields(value, {"kind", "start_byte", "end_byte"}, "type declaration owner")
        return cls(
            kind=value["kind"],
            start_byte=value["start_byte"],
            end_byte=value["end_byte"],
        )


@dataclass(frozen=True, slots=True)
class LocalTypeBinding:
    name: str
    kind: TypeBindingKind
    namespace: TypeNamespace
    declaration_start_byte: int
    declaration_end_byte: int
    scope_start_byte: int
    scope_end_byte: int

    def __post_init__(self) -> None:
        _nonempty_string(self.name, "name")
        if not isinstance(self.kind, str) or self.kind not in TYPE_BINDING_KINDS:
            raise ValueError("kind must be a supported local type binding kind")
        if not isinstance(self.namespace, str) or self.namespace not in TYPE_NAMESPACES:
            raise ValueError("namespace must be type, value, or both")
        declaration_start, declaration_end = _range(
            self.declaration_start_byte,
            self.declaration_end_byte,
            "declaration",
        )
        scope_start, scope_end = _range(
            self.scope_start_byte,
            self.scope_end_byte,
            "scope",
        )
        if not (scope_start <= declaration_start and declaration_end <= scope_end):
            raise ValueError("declaration span must be contained by the binding scope")
        expected_namespaces = {
            "interface": {"type"},
            "type": {"type"},
            "type_parameter": {"type"},
            "function": {"value"},
            "constant": {"value"},
            "parameter": {"value"},
            "class": {"both"},
            "enum": {"both"},
            "namespace": {"both"},
            "unindexed": TYPE_NAMESPACES,
        }
        if self.namespace not in expected_namespaces[self.kind]:
            raise ValueError(f"{self.kind} bindings cannot use the {self.namespace} namespace")

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "kind": self.kind,
            "namespace": self.namespace,
            "declaration_start_byte": self.declaration_start_byte,
            "declaration_end_byte": self.declaration_end_byte,
            "scope_start_byte": self.scope_start_byte,
            "scope_end_byte": self.scope_end_byte,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> LocalTypeBinding:
        _require_fields(
            value,
            {
                "name",
                "kind",
                "namespace",
                "declaration_start_byte",
                "declaration_end_byte",
                "scope_start_byte",
                "scope_end_byte",
            },
            "local type binding",
        )
        return cls(
            name=value["name"],
            kind=value["kind"],
            namespace=value["namespace"],
            declaration_start_byte=value["declaration_start_byte"],
            declaration_end_byte=value["declaration_end_byte"],
            scope_start_byte=value["scope_start_byte"],
            scope_end_byte=value["scope_end_byte"],
        )


@dataclass(frozen=True, slots=True)
class RawTypeObservation:
    source_file: str
    language: str
    line: int
    column: int
    start_byte: int
    end_byte: int
    text: str
    path: tuple[str, ...]
    relation: TypeRelationKind
    context: TypeObservationContext
    lookup_space: TypeLookupSpace
    owner: TypeDeclarationOwner
    local_bindings: tuple[LocalTypeBinding, ...]
    import_bindings: tuple[ImportBinding, ...]
    binding_state: TypeBindingState
    candidates_complete: bool
    candidates_truncated: int
    unsupported_reason: str | None
    source_hash: str

    def __post_init__(self) -> None:
        _relative_path(self.source_file, "source_file")
        if self.language not in {"typescript", "python"}:
            raise ValueError("language must be typescript or python")
        _integer(self.line, "line", minimum=1)
        _integer(self.column, "column", minimum=1)
        start, end = _range(self.start_byte, self.end_byte, "observation")
        _nonempty_string(self.text, "text")
        if len(self.text.encode("utf-8")) != end - start:
            raise ValueError("text UTF-8 byte length must match the observation span")
        _tuple(self.path, "path", str)
        if len(self.path) > MAX_TYPE_PATH_SEGMENTS:
            raise ValueError("path exceeds the type path segment limit")
        for segment in self.path:
            _nonempty_string(segment, "path segment")
        if self.binding_state != "unsupported" and not self.path:
            raise ValueError("supported observations require a non-empty path")
        if not isinstance(self.relation, str) or self.relation not in TYPE_RELATIONS:
            raise ValueError("relation must be a supported type relation")
        if not isinstance(self.context, str) or self.context not in TYPE_CONTEXTS:
            raise ValueError("context must be a supported type observation context")
        if not isinstance(self.lookup_space, str) or self.lookup_space not in TYPE_LOOKUP_SPACES:
            raise ValueError("lookup_space must be type or value")
        if not isinstance(self.owner, TypeDeclarationOwner):
            raise ValueError("owner must be a TypeDeclarationOwner")
        if not (
            self.owner.start_byte <= start
            and end <= self.owner.end_byte
        ):
            raise ValueError("observation span must be contained by its declaration owner")
        _tuple(self.local_bindings, "local_bindings", LocalTypeBinding)
        _tuple(self.import_bindings, "import_bindings", ImportBinding)
        if len(self.local_bindings) + len(self.import_bindings) > MAX_TYPE_BINDINGS_PER_OBSERVATION:
            raise ValueError("observation exceeds the type binding limit")
        if not isinstance(self.binding_state, str) or self.binding_state not in TYPE_BINDING_STATES:
            raise ValueError("binding_state must be a supported type binding state")
        _boolean(self.candidates_complete, "candidates_complete")
        _integer(self.candidates_truncated, "candidates_truncated")
        if self.candidates_complete and self.candidates_truncated:
            raise ValueError("complete candidates cannot report truncation")
        if self.binding_state == "unsupported":
            reason = _nonempty_string(self.unsupported_reason, "unsupported_reason")
            if len(reason) > MAX_UNSUPPORTED_REASON_LENGTH:
                raise ValueError("unsupported_reason exceeds the bounded length")
        elif self.unsupported_reason is not None:
            raise ValueError("unsupported_reason is only valid for unsupported observations")
        if self.binding_state != "unsupported":
            if self.binding_state == "local" and not self.local_bindings:
                raise ValueError("local observations require a local binding")
            if self.binding_state == "imported" and not self.import_bindings:
                raise ValueError("imported observations require an import binding")
            if self.binding_state == "ambiguous" and (
                len(self.local_bindings) + len(self.import_bindings) < 2
            ):
                raise ValueError("ambiguous observations require multiple candidates")
            if self.binding_state == "unbound" and (
                self.local_bindings or self.import_bindings
            ):
                raise ValueError("unbound observations cannot carry bindings")
        for binding in self.local_bindings:
            if not (
                binding.scope_start_byte <= start
                and end <= binding.scope_end_byte
            ):
                raise ValueError("local binding scope must contain the observation")
            if self.binding_state != "unsupported" and binding.name != self.path[0]:
                raise ValueError("local binding name must match the path root")
            if binding.namespace != "both" and self.lookup_space != binding.namespace:
                raise ValueError("local binding namespace does not contain lookup space")
        for binding in self.import_bindings:
            if not (
                binding.scope_start_byte <= start
                and end <= binding.scope_end_byte
            ):
                raise ValueError("import binding scope must contain the observation")
            if (
                self.binding_state != "unsupported"
                and binding.local_name is not None
                and binding.local_name != self.path[0]
            ):
                raise ValueError("import binding local name must match the path root")
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
            "relation": self.relation,
            "context": self.context,
            "lookup_space": self.lookup_space,
            "owner": self.owner.to_dict(),
            "local_bindings": [binding.to_dict() for binding in self.local_bindings],
            "import_bindings": [binding.to_dict() for binding in self.import_bindings],
            "binding_state": self.binding_state,
            "candidates_complete": self.candidates_complete,
            "candidates_truncated": self.candidates_truncated,
            "unsupported_reason": self.unsupported_reason,
            "source_hash": self.source_hash,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> RawTypeObservation:
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
                "relation",
                "context",
                "lookup_space",
                "owner",
                "local_bindings",
                "import_bindings",
                "binding_state",
                "candidates_complete",
                "candidates_truncated",
                "unsupported_reason",
                "source_hash",
            },
            "raw type observation",
        )
        path = _list(value["path"], "path")
        local_bindings = _list(value["local_bindings"], "local_bindings")
        import_bindings = _list(value["import_bindings"], "import_bindings")
        if not isinstance(value["owner"], Mapping):
            raise ValueError("owner must be an object")
        return cls(
            source_file=value["source_file"],
            language=value["language"],
            line=value["line"],
            column=value["column"],
            start_byte=value["start_byte"],
            end_byte=value["end_byte"],
            text=value["text"],
            path=tuple(path),
            relation=value["relation"],
            context=value["context"],
            lookup_space=value["lookup_space"],
            owner=TypeDeclarationOwner.from_dict(value["owner"]),
            local_bindings=tuple(
                LocalTypeBinding.from_dict(binding) for binding in local_bindings
            ),
            import_bindings=tuple(
                ImportBinding.from_dict(binding) for binding in import_bindings
            ),
            binding_state=value["binding_state"],
            candidates_complete=value["candidates_complete"],
            candidates_truncated=value["candidates_truncated"],
            unsupported_reason=value["unsupported_reason"],
            source_hash=value["source_hash"],
        )


__all__ = [
    "LocalTypeBinding",
    "MAX_TYPE_BINDINGS_PER_OBSERVATION",
    "MAX_TYPE_OBSERVATIONS_PER_FILE",
    "MAX_TYPE_PATH_SEGMENTS",
    "MAX_UNSUPPORTED_REASON_LENGTH",
    "MAX_TYPE_SITES_PER_FILE",
    "RawTypeObservation",
    "TYPE_BINDING_KINDS",
    "TYPE_BINDING_STATES",
    "TYPE_CONTEXTS",
    "TYPE_DECLARATION_OWNER_KINDS",
    "TYPE_LOOKUP_SPACES",
    "TYPE_NAMESPACES",
    "TYPE_RELATIONS",
    "TypeBindingKind",
    "TypeBindingState",
    "TypeDeclarationOwner",
    "TypeDeclarationOwnerKind",
    "TypeLookupSpace",
    "TypeNamespace",
    "TypeObservationContext",
    "TypeRelationKind",
]
