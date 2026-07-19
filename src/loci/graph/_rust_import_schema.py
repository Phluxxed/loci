from __future__ import annotations

from collections.abc import Mapping
from typing import Any, cast

from loci.parser.imports import RawImport, RustImportContext

from .contracts import GraphContractError, JSONValue


_RUST_CONFIGURATIONS = frozenset({
    "unconditional",
    "conditional",
    "unsupported",
})
_RUST_OBSERVATION_KINDS = frozenset({"use", "module", "extern_crate"})
_RUST_SIMPLE_VISIBILITIES = frozenset({
    "private",
    "pub",
    "pub(crate)",
    "pub(self)",
    "pub(super)",
})
_RUST_CONTEXT_FIELDS = {
    "kind",
    "lexical_module_path",
    "visibility",
    "module_level",
    "configuration",
    "path_override",
    "lexical_module_visibilities",
    "lexical_module_configurations",
    "inline",
}


def validate_raw_rust_context(raw: RawImport) -> None:
    if raw.language == "rust":
        if raw.rust is None:
            raise _error("Rust import requires Rust context", field="rust")
        if raw.type_only:
            raise _error("Rust imports cannot be type-only", field="type_only")
        _validate_context(raw.rust)
    elif raw.rust is not None:
        raise _error("Only Rust imports may carry Rust context", field="rust")


def rust_context_to_dict(
    context: RustImportContext | None,
) -> dict[str, JSONValue] | None:
    if context is None:
        return None
    _validate_context(context)
    return {
        "kind": context.kind,
        "lexical_module_path": list(context.lexical_module_path),
        "visibility": context.visibility,
        "module_level": context.module_level,
        "configuration": context.configuration,
        "path_override": context.path_override,
        "lexical_module_visibilities": list(
            context.lexical_module_visibilities
        ),
        "lexical_module_configurations": list(
            context.lexical_module_configurations
        ),
        "inline": context.inline,
    }


def rust_context_from_dict(value: Any) -> RustImportContext | None:
    if value is None:
        return None
    if not isinstance(value, Mapping):
        raise _error("Rust import context must be an object", field="rust")
    _require_keys(value)
    context = RustImportContext(
        kind=cast(Any, _enum(value["kind"], _RUST_OBSERVATION_KINDS, "kind")),
        lexical_module_path=_string_tuple(
            value["lexical_module_path"],
            "lexical_module_path",
        ),
        visibility=_visibility(value["visibility"]),
        module_level=_boolean(value["module_level"], "module_level"),
        configuration=cast(
            Any,
            _enum(
                value["configuration"],
                _RUST_CONFIGURATIONS,
                "configuration",
            ),
        ),
        path_override=_optional_path(value["path_override"]),
        lexical_module_visibilities=tuple(
            _visibility(item)
            for item in _list(
                value["lexical_module_visibilities"],
                "lexical_module_visibilities",
            )
        ),
        lexical_module_configurations=tuple(
            cast(
                Any,
                _enum(item, _RUST_CONFIGURATIONS, "lexical_module_configurations"),
            )
            for item in _list(
                value["lexical_module_configurations"],
                "lexical_module_configurations",
            )
        ),
        inline=_boolean(value["inline"], "inline"),
    )
    _validate_context(context)
    return context


def _validate_context(context: RustImportContext) -> None:
    if not isinstance(context, RustImportContext):
        raise _error("Invalid Rust import context", field="rust")
    _enum(context.kind, _RUST_OBSERVATION_KINDS, "kind")
    _validate_string_tuple(context.lexical_module_path, "lexical_module_path")
    _visibility(context.visibility)
    _boolean(context.module_level, "module_level")
    _enum(context.configuration, _RUST_CONFIGURATIONS, "configuration")
    _optional_path(context.path_override)
    _validate_string_tuple(
        context.lexical_module_visibilities,
        "lexical_module_visibilities",
        validator=_visibility,
    )
    _validate_string_tuple(
        context.lexical_module_configurations,
        "lexical_module_configurations",
        validator=lambda item, field: _enum(
            item,
            _RUST_CONFIGURATIONS,
            field,
        ),
    )
    _boolean(context.inline, "inline")
    count = len(context.lexical_module_path)
    if (
        len(context.lexical_module_visibilities) != count
        or len(context.lexical_module_configurations) != count
    ):
        raise _error(
            "Rust lexical module context lengths must match",
            field="rust",
        )
    if context.inline and context.kind != "module":
        raise _error(
            "Only Rust module observations may be inline",
            field="inline",
        )
    if context.path_override is not None and context.kind != "module":
        raise _error(
            "Only Rust module observations may have path overrides",
            field="path_override",
        )


def _require_keys(value: Mapping[str, Any]) -> None:
    actual = set(value)
    if actual != _RUST_CONTEXT_FIELDS:
        raise _error(
            "Invalid Rust import context fields",
            missing=sorted(_RUST_CONTEXT_FIELDS - actual),
            unknown=sorted(actual - _RUST_CONTEXT_FIELDS),
        )


def _string_tuple(value: Any, field: str) -> tuple[str, ...]:
    return tuple(_path_segment(item, field) for item in _list(value, field))


def _validate_string_tuple(
    value: Any,
    field: str,
    *,
    validator=None,
) -> None:
    if not isinstance(value, tuple):
        raise _error(f"Rust {field} must be a tuple", field=field)
    for item in value:
        (validator or _path_segment)(item, field)


def _list(value: Any, field: str) -> list[Any]:
    if not isinstance(value, list):
        raise _error(f"Rust {field} must be an array", field=field)
    return value


def _path_segment(value: Any, field: str) -> str:
    if (
        not isinstance(value, str)
        or not _valid_rust_identifier(value)
    ):
        raise _error(f"Invalid Rust {field} segment", field=field)
    return value


def _visibility(value: Any, field: str = "visibility") -> str:
    if not isinstance(value, str) or not (
        value in _RUST_SIMPLE_VISIBILITIES
        or _valid_restricted_visibility(value)
    ):
        raise _error("Invalid Rust visibility", field=field)
    return value


def _valid_restricted_visibility(value: str) -> bool:
    if not value.startswith("pub(in ") or not value.endswith(")"):
        return False
    parts = value[len("pub(in ") : -1].split("::")
    if not parts or parts[0] not in {"crate", "self", "super"}:
        return False
    offset = 1
    if parts[0] == "super":
        while offset < len(parts) and parts[offset] == "super":
            offset += 1
    return all(_valid_rust_identifier(part) for part in parts[offset:])


def _valid_rust_identifier(value: str) -> bool:
    identifier = value[2:] if value.startswith("r#") else value
    return bool(identifier) and identifier.isidentifier()


def _enum(value: Any, allowed: frozenset[str], field: str) -> str:
    if not isinstance(value, str) or value not in allowed:
        raise _error(f"Invalid Rust {field}", field=field)
    return value


def _boolean(value: Any, field: str) -> bool:
    if not isinstance(value, bool):
        raise _error(f"Rust {field} must be a boolean", field=field)
    return value


def _optional_path(value: Any) -> str | None:
    if value is None:
        return None
    if (
        not isinstance(value, str)
        or not value
        or any(ord(character) < 32 for character in value)
        or "\\" in value
        or value.startswith("/")
        or any(part == "" for part in value.split("/"))
    ):
        raise _error("Invalid Rust path override", field="path_override")
    return value


def _error(message: str, **details: Any) -> GraphContractError:
    return GraphContractError(
        "INVALID_GRAPH_SCHEMA",
        message,
        cast(dict[str, JSONValue], details),
    )
