from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Literal, TypeAlias

from loci.parser._binding_context import ExecutableOwner
from loci.parser.reference_models import (
    _integer,
    _list,
    _nonempty_string,
    _relative_path,
    _require_fields,
    _sha256,
    _typed_tuple,
)


MAX_CALL_SITES_PER_FILE = 250_000
MAX_CALL_BINDING_CANDIDATES = 256
MAX_CALL_PATH_SEGMENTS = 128

CallCalleeForm: TypeAlias = Literal["identifier", "static_path", "dynamic"]
CallBindingState: TypeAlias = Literal[
    "definite",
    "shadowed",
    "ambiguous",
    "absent",
    "unsupported",
]
CallableKind: TypeAlias = Literal["function", "method"]

_CALL_CALLEE_FORMS = {"identifier", "static_path", "dynamic"}
_CALL_BINDING_STATES = {
    "definite",
    "shadowed",
    "ambiguous",
    "absent",
    "unsupported",
}
_CALLABLE_KINDS = {"function", "method"}
_SUPPORTED_LANGUAGES = {"python", "javascript", "typescript", "go", "rust"}


@dataclass(frozen=True, slots=True)
class LocalCallableBinding:
    name: str
    callable_kind: CallableKind
    definition_start_byte: int
    definition_end_byte: int
    definition_line: int
    scope_start_byte: int
    scope_end_byte: int

    def __post_init__(self) -> None:
        _nonempty_string(self.name, "name")
        if self.callable_kind not in _CALLABLE_KINDS:
            raise ValueError("callable_kind must be function or method")
        definition_start = _integer(
            self.definition_start_byte,
            "definition_start_byte",
            minimum=0,
        )
        definition_end = _integer(
            self.definition_end_byte,
            "definition_end_byte",
            minimum=1,
        )
        if definition_start >= definition_end:
            raise ValueError("definition byte range must be non-empty and ordered")
        _integer(self.definition_line, "definition_line", minimum=1)
        scope_start = _integer(
            self.scope_start_byte,
            "scope_start_byte",
            minimum=0,
        )
        scope_end = _integer(self.scope_end_byte, "scope_end_byte", minimum=1)
        if scope_start >= scope_end:
            raise ValueError("scope byte range must be non-empty and ordered")

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "callable_kind": self.callable_kind,
            "definition_start_byte": self.definition_start_byte,
            "definition_end_byte": self.definition_end_byte,
            "definition_line": self.definition_line,
            "scope_start_byte": self.scope_start_byte,
            "scope_end_byte": self.scope_end_byte,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> LocalCallableBinding:
        _require_fields(
            value,
            {
                "name",
                "callable_kind",
                "definition_start_byte",
                "definition_end_byte",
                "definition_line",
                "scope_start_byte",
                "scope_end_byte",
            },
            "local callable binding",
        )
        return cls(
            name=value["name"],
            callable_kind=value["callable_kind"],
            definition_start_byte=value["definition_start_byte"],
            definition_end_byte=value["definition_end_byte"],
            definition_line=value["definition_line"],
            scope_start_byte=value["scope_start_byte"],
            scope_end_byte=value["scope_end_byte"],
        )


@dataclass(frozen=True, slots=True)
class RawCallSite:
    source_file: str
    language: str
    line: int
    column: int
    start_byte: int
    end_byte: int
    callee_start_byte: int
    callee_end_byte: int
    callee_text: str
    callee_path: tuple[str, ...]
    callee_form: CallCalleeForm
    local_candidates: tuple[LocalCallableBinding, ...]
    local_binding_state: CallBindingState
    owner: ExecutableOwner
    source_hash: str

    def __post_init__(self) -> None:
        _relative_path(self.source_file, "source_file")
        if self.language not in _SUPPORTED_LANGUAGES:
            raise ValueError("language must be supported for call extraction")
        _integer(self.line, "line", minimum=1)
        _integer(self.column, "column", minimum=1)
        start = _integer(self.start_byte, "start_byte", minimum=0)
        end = _integer(self.end_byte, "end_byte", minimum=1)
        callee_start = _integer(
            self.callee_start_byte,
            "callee_start_byte",
            minimum=0,
        )
        callee_end = _integer(
            self.callee_end_byte,
            "callee_end_byte",
            minimum=1,
        )
        if start >= end:
            raise ValueError("call byte range must be non-empty and ordered")
        if not (start <= callee_start < callee_end <= end):
            raise ValueError("callee byte range must be non-empty and inside the call")
        _nonempty_string(self.callee_text, "callee_text")
        _typed_tuple(self.callee_path, "callee_path", str)
        if len(self.callee_path) > MAX_CALL_PATH_SEGMENTS:
            raise ValueError("callee path exceeds the path limit")
        for segment in self.callee_path:
            _nonempty_string(segment, "callee path segment")
        if self.callee_form not in _CALL_CALLEE_FORMS:
            raise ValueError("callee_form must be a supported form")
        if self.callee_form == "identifier" and len(self.callee_path) != 1:
            raise ValueError("identifier callees require exactly one path segment")
        if self.callee_form == "static_path" and len(self.callee_path) < 2:
            raise ValueError("static path callees require multiple path segments")
        if self.callee_form == "dynamic" and self.callee_path:
            raise ValueError("dynamic callees cannot carry a static path")
        _typed_tuple(
            self.local_candidates,
            "local_candidates",
            LocalCallableBinding,
        )
        if len(self.local_candidates) > MAX_CALL_BINDING_CANDIDATES:
            raise ValueError("local_candidates exceeds the candidate limit")
        if len(set(self.local_candidates)) != len(self.local_candidates):
            raise ValueError("local_candidates must be unique")
        if self.local_binding_state not in _CALL_BINDING_STATES:
            raise ValueError("local_binding_state must be a supported state")
        candidate_count = len(self.local_candidates)
        if self.local_binding_state == "definite" and candidate_count != 1:
            raise ValueError("definite calls require exactly one local candidate")
        if self.local_binding_state == "ambiguous" and candidate_count < 2:
            raise ValueError("ambiguous calls require multiple local candidates")
        if self.local_binding_state in {"shadowed", "absent", "unsupported"} and (
            candidate_count
        ):
            raise ValueError(
                f"{self.local_binding_state} calls cannot carry local candidates"
            )
        if self.callee_form == "dynamic":
            if self.local_binding_state != "unsupported":
                raise ValueError("dynamic calls must use unsupported binding state")
        elif self.local_binding_state == "unsupported":
            raise ValueError("static callees cannot use unsupported binding state")
        if self.callee_form != "identifier" and candidate_count:
            raise ValueError("only identifier calls can carry local candidates")
        if self.callee_form == "static_path" and self.local_binding_state != "absent":
            raise ValueError("static path calls must use absent local binding state")
        for candidate in self.local_candidates:
            if not (
                candidate.scope_start_byte <= callee_start
                and callee_end <= candidate.scope_end_byte
            ):
                raise ValueError("local candidate scope must contain the callee")
            if candidate.name != self.callee_path[0]:
                raise ValueError("local candidate name must match the callee root")
        if not isinstance(self.owner, ExecutableOwner):
            raise ValueError("owner must be an ExecutableOwner")
        _sha256(self.source_hash, "source_hash")

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_file": self.source_file,
            "language": self.language,
            "line": self.line,
            "column": self.column,
            "start_byte": self.start_byte,
            "end_byte": self.end_byte,
            "callee_start_byte": self.callee_start_byte,
            "callee_end_byte": self.callee_end_byte,
            "callee_text": self.callee_text,
            "callee_path": list(self.callee_path),
            "callee_form": self.callee_form,
            "local_candidates": [
                candidate.to_dict() for candidate in self.local_candidates
            ],
            "local_binding_state": self.local_binding_state,
            "owner": self.owner.to_dict(),
            "source_hash": self.source_hash,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> RawCallSite:
        _require_fields(
            value,
            {
                "source_file",
                "language",
                "line",
                "column",
                "start_byte",
                "end_byte",
                "callee_start_byte",
                "callee_end_byte",
                "callee_text",
                "callee_path",
                "callee_form",
                "local_candidates",
                "local_binding_state",
                "owner",
                "source_hash",
            },
            "raw call site",
        )
        path = _list(value["callee_path"], "callee_path")
        candidates = _list(value["local_candidates"], "local_candidates")
        return cls(
            source_file=value["source_file"],
            language=value["language"],
            line=value["line"],
            column=value["column"],
            start_byte=value["start_byte"],
            end_byte=value["end_byte"],
            callee_start_byte=value["callee_start_byte"],
            callee_end_byte=value["callee_end_byte"],
            callee_text=value["callee_text"],
            callee_path=tuple(path),
            callee_form=value["callee_form"],
            local_candidates=tuple(
                LocalCallableBinding.from_dict(candidate) for candidate in candidates
            ),
            local_binding_state=value["local_binding_state"],
            owner=ExecutableOwner.from_dict(value["owner"]),
            source_hash=value["source_hash"],
        )
