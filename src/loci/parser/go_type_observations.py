"""Exact, declaration-owned Go type observations.

Go's import declarations deliberately do not guess a package name from a path.
An unaliased qualified use is therefore deferred to graph resolution, which has
the complete package surface; a bare package type is likewise retained as a
same-package observation rather than being resolved from this file alone.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
from pathlib import Path
from typing import Any, Sequence

from .imports import ImportExtractionError, _extract_go_import
from .reference_models import ImportBinding
from .symbols import Symbol
from .type_models import LocalTypeBinding, RawTypeObservation, TypeDeclarationOwner
from .type_observations import (
    MAX_TYPE_BINDINGS_PER_OBSERVATION,
    MAX_TYPE_OBSERVATIONS_PER_FILE,
    MAX_TYPE_PATH_SEGMENTS,
    TypeExtractionError,
)


_BUILTINS = frozenset({
    "any", "bool", "byte", "comparable", "complex64", "complex128", "error",
    "float32", "float64", "int", "int8", "int16", "int32", "int64", "rune",
    "string", "uint", "uint8", "uint16", "uint32", "uint64", "uintptr",
})
_TYPE_OWNERS = frozenset({"function_declaration", "method_declaration", "func_literal", "type_spec", "type_alias"})


@dataclass(frozen=True, slots=True)
class _Owner:
    node: Any
    symbol: Symbol | None


@dataclass(frozen=True, slots=True)
class _Local:
    binding: LocalTypeBinding
    active_start: int


def extract_go_type_observations(
    path: Path, *, source_file: str, source_hash: str, symbols: Sequence[Symbol],
) -> tuple[RawTypeObservation, ...]:
    """Extract supported Go declaration type sites from ``path``."""
    try:
        source = path.read_bytes()
    except OSError as exc:
        raise TypeExtractionError("TYPE_SOURCE_READ_FAILED", str(exc), "read_failed") from exc
    if hashlib.sha256(source).hexdigest() != source_hash:
        raise TypeExtractionError(
            "TYPE_SOURCE_HASH_MISMATCH", f"{source_file} changed after symbol extraction",
            "source_hash_mismatch",
        )
    try:
        from tree_sitter import Parser
        from tree_sitter_language_pack import get_language

        root = Parser(get_language("go")).parse(source).root_node
    except Exception as exc:
        raise TypeExtractionError("TYPE_PARSE_FAILED", str(exc), "parse_failed") from exc
    if root.has_error:
        raise TypeExtractionError(
            "TYPE_PARSE_FAILED", f"{source_file} could not be parsed for Go types", "parse_error"
        )

    file_symbols = tuple(symbol for symbol in symbols if symbol.file_path == source_file)
    owners = _owners(root, file_symbols)
    imports = _imports(root, source, source_file, source_hash)
    locals_ = _locals(root, source)
    observations: list[RawTypeObservation] = []
    consumed: set[tuple[int, int, str]] = set()

    def add(
        node: Any,
        path_value: tuple[str, ...],
        *,
        context: str,
        relation: str = "uses_type",
        unsupported_reason: str | None = None,
    ) -> None:
        key = (node.start_byte, node.end_byte, relation)
        if key in consumed:
            return
        consumed.add(key)
        if len(observations) >= MAX_TYPE_OBSERVATIONS_PER_FILE:
            raise TypeExtractionError(
                "TYPE_OBSERVATION_LIMIT", f"{source_file} exceeds the type-site limit", "site_limit"
            )
        if len(path_value) > MAX_TYPE_PATH_SEGMENTS:
            path_value, unsupported_reason = (), unsupported_reason or "path_too_deep"

        local_values = _visible_locals(locals_, path_value[:1], node.start_byte)
        explicit = _explicit_imports(imports, path_value[:1], node)
        deferred = () if explicit else _deferred_imports(imports, path_value, node)
        total = len(local_values) + len(explicit) + len(deferred)
        truncated = max(0, total - MAX_TYPE_BINDINGS_PER_OBSERVATION)
        if local_values:
            local_values = local_values[:MAX_TYPE_BINDINGS_PER_OBSERVATION]
            explicit = ()
            deferred = ()
        elif explicit:
            explicit = explicit[:MAX_TYPE_BINDINGS_PER_OBSERVATION]
            deferred = ()
        else:
            deferred = deferred[:MAX_TYPE_BINDINGS_PER_OBSERVATION]

        if unsupported_reason is not None:
            state = "unsupported"
        elif len(local_values) > 1:
            state = "ambiguous"
        elif local_values and local_values[0].binding.kind == "type":
            state = "local"
        elif local_values:
            state = "shadowed"
        elif len(explicit) == 1:
            state = "imported"
        elif len(explicit) > 1:
            state = "ambiguous"
        elif deferred:
            state = "deferred"
        elif len(path_value) == 1:
            state = "package"
        else:
            state, unsupported_reason = "unsupported", "unproven_qualified_package"

        observations.append(RawTypeObservation(
            source_file=source_file,
            language="go",
            source_hash=source_hash,
            line=source[:node.start_byte].count(b"\n") + 1,
            column=node.start_byte - source.rfind(b"\n", 0, node.start_byte),
            start_byte=node.start_byte,
            end_byte=node.end_byte,
            text=source[node.start_byte:node.end_byte].decode("utf-8"),
            path=path_value,
            relation=relation,
            context=context,
            lookup_space="type",
            owner=_owner_for(node, owners),
            local_bindings=tuple(item.binding for item in local_values),
            import_bindings=tuple(explicit or deferred),
            binding_state=state,
            candidates_complete=not truncated,
            candidates_truncated=truncated,
            unsupported_reason=unsupported_reason,
        ))

    def type_expression(node: Any, context: str, *, relation: str = "uses_type") -> None:
        if node is None:
            return
        if node.type == "type_identifier":
            name = _text(source, node)
            if name not in _BUILTINS:
                add(node, (name,), context=context, relation=relation)
            return
        if node.type == "qualified_type":
            package = node.child_by_field_name("package")
            name = node.child_by_field_name("name")
            if package is not None and name is not None:
                add(node, (_text(source, package), _text(source, name)), context=context, relation=relation)
            else:
                add(node, (), context=context, relation=relation, unsupported_reason="malformed_qualified_type")
            return
        if node.type == "generic_type":
            head = node.child_by_field_name("type")
            type_expression(head, context, relation=relation)
            arguments = node.child_by_field_name("type_arguments")
            if arguments is not None:
                for element in arguments.named_children:
                    type_expression(element, "type_argument")
            return
        if node.type == "type_elem":
            if any(child.type in {"|", "~"} for child in node.children):
                add(node, (), context=context, relation=relation,
                    unsupported_reason="unsupported_approximation_or_union")
            else:
                for child in node.named_children:
                    type_expression(child, context, relation=relation)
            return
        if node.type in {"pointer_type", "slice_type", "array_type", "channel_type", "parenthesized_type"}:
            for child in node.named_children:
                type_expression(child, context, relation=relation)
            return
        if node.type == "map_type":
            key = node.child_by_field_name("key")
            value = node.child_by_field_name("value")
            type_expression(key, context, relation=relation)
            type_expression(value, context, relation=relation)
            return
        if node.type == "function_type":
            _signature_types(node, type_expression)
            return
        if node.type == "struct_type":
            fields = next((child for child in node.named_children if child.type == "field_declaration_list"), None)
            if fields is not None:
                for field in fields.named_children:
                    field_type = field.child_by_field_name("type")
                    embedded = field.child_by_field_name("name") is None
                    type_expression(field_type, "struct_embedding" if embedded else "property",
                                    relation="embeds" if embedded else relation)
            return
        if node.type == "interface_type":
            for child in node.named_children:
                if child.type == "type_elem":
                    type_expression(child, "interface_embedding", relation="embeds")
                elif child.type == "method_elem":
                    _signature_types(child, type_expression)
            return
        if node.type == "type_constraint":
            for child in node.named_children:
                type_expression(child, "constraint", relation=relation)
            return
        if node.type in {"nil", "variadic_parameter_declaration"}:
            return
        add(node, (), context=context, relation=relation, unsupported_reason=f"unsupported_{node.type}")

    for node in _walk(root):
        if node.type in {"function_declaration", "method_declaration", "func_literal"}:
            _signature_types(node, type_expression)
        elif node.type in {"type_spec", "type_alias"}:
            parameters = node.child_by_field_name("type_parameters")
            if parameters is not None:
                for declaration in parameters.named_children:
                    constraint = declaration.child_by_field_name("type")
                    type_expression(constraint, "constraint")
            type_expression(node.child_by_field_name("type"), "alias")
    return tuple(observations)


def _signature_types(node: Any, expression: Any) -> None:
    parameters_type = node.child_by_field_name("type_parameters")
    if parameters_type is not None:
        for declaration in parameters_type.named_children:
            expression(declaration.child_by_field_name("type"), "constraint")
    receiver = node.child_by_field_name("receiver")
    if receiver is not None:
        for parameter in receiver.named_children:
            expression(parameter.child_by_field_name("type"), "annotation")
    parameters = node.child_by_field_name("parameters")
    if parameters is not None:
        for parameter in parameters.named_children:
            expression(parameter.child_by_field_name("type"), "annotation")
    result = node.child_by_field_name("result")
    if result is None:
        return
    if result.type == "parameter_list":
        for parameter in result.named_children:
            expression(parameter.child_by_field_name("type"), "return")
    else:
        expression(result, "return")


def _owners(root: Any, symbols: Sequence[Symbol]) -> tuple[_Owner, ...]:
    by_span = {(symbol.byte_offset, symbol.byte_offset + symbol.byte_length): symbol for symbol in symbols}
    result: list[_Owner] = []
    for node in _walk(root):
        if node.type not in _TYPE_OWNERS:
            continue
        symbol = None if node.type == "func_literal" else by_span.get((node.start_byte, node.end_byte))
        result.append(_Owner(node, symbol))
    return tuple(result)


def _owner_for(node: Any, owners: Sequence[_Owner]) -> TypeDeclarationOwner:
    containing = [owner for owner in owners if owner.node.start_byte <= node.start_byte and node.end_byte <= owner.node.end_byte]
    if not containing:
        return TypeDeclarationOwner(kind="unindexed", start_byte=node.start_byte, end_byte=node.end_byte)
    nearest = min(containing, key=lambda owner: (owner.node.end_byte - owner.node.start_byte, -owner.node.start_byte))
    if nearest.symbol is None:
        return TypeDeclarationOwner(kind="unindexed", start_byte=nearest.node.start_byte, end_byte=nearest.node.end_byte)
    return TypeDeclarationOwner(kind=nearest.symbol.kind, start_byte=nearest.symbol.byte_offset,
                                end_byte=nearest.symbol.byte_offset + nearest.symbol.byte_length)


def _imports(root: Any, source: bytes, source_file: str, source_hash: str) -> tuple[ImportBinding, ...]:
    result: list[ImportBinding] = []
    for node in _walk(root):
        if node.type != "import_spec":
            continue
        common = {"source_file": source_file, "language": "go", "line": node.start_point.row + 1,
                  "text": _text(source, node), "source_hash": source_hash}
        try:
            for record in _extract_go_import(node, source, common):
                result.extend(record.bindings)
        except ImportExtractionError as exc:
            raise TypeExtractionError("TYPE_BINDING_LIMIT", str(exc), "binding_limit") from exc
    return tuple(result)


def _locals(root: Any, source: bytes) -> tuple[_Local, ...]:
    result: list[_Local] = []
    for node in _walk(root):
        if node.type in {"function_declaration", "method_declaration", "func_literal"}:
            end = node.end_byte
            for parameter in _type_parameters(node, source):
                _append_local(result, parameter, _text(source, parameter), "type_parameter", "type", node.start_byte, end, node.start_byte)
            if node.type == "method_declaration":
                receiver = node.child_by_field_name("receiver")
                if receiver is not None:
                    for generic in _walk(receiver):
                        if generic.type == "type_arguments":
                            for argument in generic.named_children:
                                if argument.type == "type_elem":
                                    for identifier in argument.named_children:
                                        if identifier.type == "type_identifier":
                                            _append_local(result, identifier, _text(source, identifier), "type_parameter", "type", node.start_byte, end, node.start_byte)
        elif node.type in {"type_spec", "type_alias"}:
            for parameter in _type_parameters(node, source):
                _append_local(result, parameter, _text(source, parameter), "type_parameter", "type", node.start_byte, node.end_byte, node.start_byte)
            if not _package_level(node):
                scope = _scope(node)
                if scope is not None:
                    name = node.child_by_field_name("name")
                    if name is not None:
                        _append_local(result, name, _text(source, name), "type", "type",
                                      scope.start_byte, scope.end_byte, node.start_byte,
                                      declaration=node)
        elif node.type in {"parameter_declaration", "var_spec", "const_spec", "short_var_declaration", "range_clause"}:
            scope = _scope(node)
            if scope is None:
                continue
            active_start = (
                _function_body_start(node)
                if node.type == "parameter_declaration"
                else node.end_byte
            )
            for name in _value_names(node):
                _append_local(result, name, _text(source, name), "unindexed", "both",
                              scope.start_byte, scope.end_byte, active_start)
    return tuple(result)


def _type_parameters(node: Any, source: bytes) -> tuple[Any, ...]:
    parameters = node.child_by_field_name("type_parameters")
    if parameters is None:
        return ()
    result: list[Any] = []
    for declaration in parameters.named_children:
        result.extend(declaration.children_by_field_name("name"))
    return tuple(result)


def _value_names(node: Any) -> tuple[Any, ...]:
    if node.type == "parameter_declaration":
        return tuple(name for name in node.children_by_field_name("name") if name.type == "identifier")
    if node.type in {"var_spec", "const_spec"}:
        return tuple(child for child in node.named_children if child.type == "identifier")
    if node.type == "short_var_declaration":
        left = node.child_by_field_name("left")
        return tuple(child for child in _walk(left) if child.type == "identifier") if left is not None else ()
    if node.type == "range_clause":
        return tuple(child for child in node.named_children[:2] if child.type == "identifier")
    return ()


def _local(name: Any, value: str, kind: str, namespace: str, start: int, end: int,
           active_start: int, *, declaration: Any | None = None) -> _Local:
    declaration = declaration or name
    return _Local(LocalTypeBinding(name=value, kind=kind, namespace=namespace,
                                  declaration_start_byte=declaration.start_byte, declaration_end_byte=declaration.end_byte,
                                  scope_start_byte=start, scope_end_byte=end), active_start)


def _append_local(result: list[_Local], name: Any, value: str, kind: str, namespace: str,
                  start: int, end: int, active_start: int, *, declaration: Any | None = None) -> None:
    """Ignore grammar placeholders, which cannot bind a Go type lookup."""
    if value and value != "_":
        result.append(_local(name, value, kind, namespace, start, end, active_start,
                             declaration=declaration))


def _visible_locals(locals_: Sequence[_Local], root: tuple[str, ...], offset: int) -> tuple[_Local, ...]:
    if not root:
        return ()
    matches = [item for item in locals_ if item.binding.scope_start_byte <= offset <= item.binding.scope_end_byte
               and item.active_start <= offset]
    matches = [item for item in matches if item.binding.name == root[0]]
    if not matches:
        return ()
    nearest_start = max(item.binding.scope_start_byte for item in matches)
    return tuple(item for item in matches if item.binding.scope_start_byte == nearest_start)


def _explicit_imports(imports: Sequence[ImportBinding], root: tuple[str, ...], node: Any) -> tuple[ImportBinding, ...]:
    if not root:
        return ()
    return tuple(binding for binding in imports if binding.kind == "namespace" and binding.local_name == root[0]
                 and binding.scope_start_byte <= node.start_byte and node.end_byte <= binding.scope_end_byte)


def _deferred_imports(imports: Sequence[ImportBinding], path: tuple[str, ...], node: Any) -> tuple[ImportBinding, ...]:
    if len(path) != 2:
        return ()
    return tuple(binding for binding in imports if binding.kind == "namespace" and binding.local_name is None
                 and binding.scope_start_byte <= node.start_byte and node.end_byte <= binding.scope_end_byte)


def _scope(node: Any) -> Any | None:
    current = node.parent
    while current is not None:
        if current.type in {"block", "function_declaration", "method_declaration", "func_literal"}:
            return current
        current = current.parent
    return None


def _function_body_start(node: Any) -> int:
    current = node.parent
    while current is not None:
        if current.type in {"function_declaration", "method_declaration", "func_literal"}:
            body = current.child_by_field_name("body")
            return body.start_byte if body is not None else current.end_byte
        current = current.parent
    return node.end_byte


def _package_level(node: Any) -> bool:
    current = node.parent
    while current is not None:
        if current.type == "source_file":
            return True
        if current.type in {"function_declaration", "method_declaration", "func_literal"}:
            return False
        current = current.parent
    return False


def _walk(node: Any | None):
    if node is None:
        return
    yield node
    for child in node.named_children:
        yield from _walk(child)


def _text(source: bytes, node: Any) -> str:
    return source[node.start_byte:node.end_byte].decode("utf-8")
