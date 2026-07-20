from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from loci.parser._reference_exports import (
    _RUST_ITEM_TYPES,
    _field_children,
    _node_text,
    _walk_nodes,
)


_IDENTIFIER_TYPES = {
    "identifier",
    "type_identifier",
    "package_identifier",
}
_JAVASCRIPT_FUNCTION_NODES = {
    "function_declaration",
    "function_expression",
    "generator_function_declaration",
    "generator_function",
    "arrow_function",
    "method_definition",
}


@dataclass(frozen=True, slots=True)
class LexicalBinding:
    name: str
    scope_start_byte: int
    scope_end_byte: int
    scope_type: str
    declaration_start_byte: int
    active_start_byte: int


@dataclass(frozen=True, slots=True)
class SyntaxContext:
    local_bindings: tuple[LexicalBinding, ...]
    excluded_subtrees: frozenset[tuple[int, int, str]]
    unsupported_import_starts: frozenset[int]


@dataclass(slots=True)
class _SyntaxContextBuilder:
    local_bindings: list[LexicalBinding]
    excluded_subtrees: set[tuple[int, int, str]]
    unsupported_import_starts: set[int]


def collect_syntax_context(
    root: Any,
    source: bytes,
    language: str,
) -> SyntaxContext:
    if language not in {"python", "javascript", "typescript", "go", "rust"}:
        raise ValueError(f"unsupported syntax context language: {language}")
    context = _SyntaxContextBuilder(
        local_bindings=[],
        excluded_subtrees=set(),
        unsupported_import_starts=set(),
    )
    if language == "python":
        _collect_python_context(root, source, context)
    elif language in {"javascript", "typescript"}:
        _collect_javascript_context(root, source, context)
    elif language == "go":
        _collect_go_context(root, source, context)
    else:
        _collect_rust_context(root, source, context)
    return SyntaxContext(
        local_bindings=tuple(context.local_bindings),
        excluded_subtrees=frozenset(context.excluded_subtrees),
        unsupported_import_starts=frozenset(context.unsupported_import_starts),
    )


def node_key(node: Any) -> tuple[int, int, str]:
    return (node.start_byte, node.end_byte, node.type)


def python_scope(node: Any) -> Any:
    return _scope_node(
        node,
        {"function_definition", "class_definition", "lambda"},
    )


def _exclude(context: _SyntaxContextBuilder, node: Any | None) -> None:
    if node is not None:
        context.excluded_subtrees.add(node_key(node))


def _root_node(node: Any) -> Any:
    while node.parent is not None:
        node = node.parent
    return node


def _nearest_ancestor(node: Any, node_types: set[str]) -> Any | None:
    current = node.parent
    while current is not None:
        if current.type in node_types:
            return current
        current = current.parent
    return None


def _scope_node(node: Any, node_types: set[str]) -> Any:
    return _nearest_ancestor(node, node_types) or _root_node(node)


def _add_local_binding(
    context: _SyntaxContextBuilder,
    *,
    name_node: Any,
    source: bytes,
    scope: Any,
    declaration_start_byte: int,
    active_start_byte: int,
    scope_type: str | None = None,
) -> None:
    name = _node_text(name_node, source)
    if not name or name == "_":
        return
    context.local_bindings.append(
        LexicalBinding(
            name=name,
            scope_start_byte=scope.start_byte,
            scope_end_byte=scope.end_byte,
            scope_type=scope_type or scope.type,
            declaration_start_byte=declaration_start_byte,
            active_start_byte=active_start_byte,
        )
    )


def _identifier_nodes(node: Any | None) -> list[Any]:
    if node is None:
        return []
    if node.type in _IDENTIFIER_TYPES:
        return [node]
    if node.type in {"attribute", "subscript", "member_expression", "field_expression"}:
        return []
    identifiers: list[Any] = []
    for child in node.named_children:
        identifiers.extend(_identifier_nodes(child))
    return identifiers


def _collect_python_context(
    root: Any,
    source: bytes,
    context: _SyntaxContextBuilder,
) -> None:
    for node in _walk_nodes(root):
        if node.type in {"import_statement", "import_from_statement"}:
            _exclude(context, node)
            if _python_import_is_conditional(node):
                context.unsupported_import_starts.add(node.start_byte)
            continue
        if node.type in {"function_definition", "class_definition"}:
            name = node.child_by_field_name("name")
            _exclude(context, name)
            if name is not None:
                scope = python_scope(node)
                _add_local_binding(
                    context,
                    name_node=name,
                    source=source,
                    scope=scope,
                    declaration_start_byte=node.start_byte,
                    active_start_byte=node.end_byte,
                )
            parameters = node.child_by_field_name("parameters")
            if parameters is not None:
                for parameter in _python_parameter_names(parameters):
                    _exclude(context, parameter)
                    _add_local_binding(
                        context,
                        name_node=parameter,
                        source=source,
                        scope=node,
                        declaration_start_byte=node.start_byte,
                        active_start_byte=node.start_byte,
                    )
            if node.type == "function_definition" and name is not None:
                body = node.child_by_field_name("body")
                if body is not None:
                    _add_local_binding(
                        context,
                        name_node=name,
                        source=source,
                        scope=body,
                        declaration_start_byte=node.start_byte,
                        active_start_byte=body.start_byte,
                        scope_type="definition_body",
                    )
            continue
        if node.type == "lambda":
            parameters = node.child_by_field_name("parameters")
            if parameters is not None:
                for parameter in _python_parameter_names(parameters):
                    _exclude(context, parameter)
                    _add_local_binding(
                        context,
                        name_node=parameter,
                        source=source,
                        scope=node,
                        declaration_start_byte=node.start_byte,
                        active_start_byte=node.start_byte,
                    )
            continue
        if node.type in {
            "assignment",
            "augmented_assignment",
            "annotated_assignment",
            "named_expression",
        }:
            target = (
                node.child_by_field_name("left")
                or node.child_by_field_name("name")
            )
            _record_python_targets(
                context,
                target,
                source,
                declaration=node,
                active_start=node.end_byte,
            )
            continue
        if node.type in {"for_statement", "for_in_clause"}:
            target = node.child_by_field_name("left")
            body = node.child_by_field_name("body")
            _record_python_targets(
                context,
                target,
                source,
                declaration=node,
                active_start=body.start_byte if body is not None else node.end_byte,
            )
            continue
        if node.type == "as_pattern":
            alias = node.child_by_field_name("alias")
            if alias is not None:
                _record_python_targets(
                    context,
                    alias,
                    source,
                    declaration=node,
                    active_start=node.end_byte,
                )
            continue
        if node.type == "case_clause":
            pattern = next(
                (
                    child
                    for child in node.named_children
                    if child.type == "case_pattern"
                ),
                None,
            )
            consequence = node.child_by_field_name("consequence")
            _record_python_targets(
                context,
                pattern,
                source,
                declaration=node,
                active_start=(
                    consequence.start_byte
                    if consequence is not None
                    else node.end_byte
                ),
            )
            continue
        if node.type == "delete_statement":
            _record_python_targets(
                context,
                node,
                source,
                declaration=node,
                active_start=node.end_byte,
            )


def _python_import_is_conditional(node: Any) -> bool:
    ancestor = node.parent
    while ancestor is not None:
        if ancestor.type in {
            "module",
            "function_definition",
            "class_definition",
            "lambda",
        }:
            return False
        if ancestor.type in {
            "if_statement",
            "for_statement",
            "while_statement",
            "try_statement",
            "with_statement",
            "match_statement",
            "case_clause",
        }:
            return True
        ancestor = ancestor.parent
    return True


def _python_parameter_names(parameters: Any) -> list[Any]:
    names: list[Any] = []
    for child in parameters.named_children:
        if child.type == "identifier":
            names.append(child)
            continue
        name = (
            child.child_by_field_name("name")
            or child.child_by_field_name("pattern")
        )
        names.extend(_identifier_nodes(name))
    return names


def _record_python_targets(
    context: _SyntaxContextBuilder,
    target: Any | None,
    source: bytes,
    *,
    declaration: Any,
    active_start: int,
) -> None:
    if target is None:
        return
    _exclude(context, target)
    scope = python_scope(declaration)
    for identifier in _identifier_nodes(target):
        _add_local_binding(
            context,
            name_node=identifier,
            source=source,
            scope=scope,
            declaration_start_byte=declaration.start_byte,
            active_start_byte=active_start,
        )


def _javascript_lexical_scope(node: Any) -> Any:
    return _scope_node(node, {"statement_block", "class_static_block", "program"})


def _javascript_function_scope(node: Any) -> Any:
    return _scope_node(node, _JAVASCRIPT_FUNCTION_NODES | {"program"})


def _collect_javascript_context(
    root: Any,
    source: bytes,
    context: _SyntaxContextBuilder,
) -> None:
    declaration_types = {
        "function_declaration",
        "generator_function_declaration",
        "class_declaration",
        "type_alias_declaration",
        "interface_declaration",
        "enum_declaration",
    }
    for node in _walk_nodes(root):
        if node.type == "import_statement":
            _exclude(context, node)
            continue
        if node.type in {"export_clause", "namespace_export"}:
            _exclude(context, node)
            continue
        if node.type in declaration_types:
            name = node.child_by_field_name("name")
            _exclude(context, name)
            if name is not None:
                scope = _javascript_lexical_scope(node)
                _add_local_binding(
                    context,
                    name_node=name,
                    source=source,
                    scope=scope,
                    declaration_start_byte=node.start_byte,
                    active_start_byte=scope.start_byte,
                )
        if node.type in _JAVASCRIPT_FUNCTION_NODES:
            parameters = node.child_by_field_name("parameters")
            if parameters is not None:
                for parameter in parameters.named_children:
                    pattern = parameter.child_by_field_name("pattern") or parameter
                    _exclude(context, pattern)
                    for identifier in _identifier_nodes(pattern):
                        _add_local_binding(
                            context,
                            name_node=identifier,
                            source=source,
                            scope=node,
                            declaration_start_byte=node.start_byte,
                            active_start_byte=node.start_byte,
                        )
            continue
        if node.type == "variable_declarator":
            name = node.child_by_field_name("name")
            if name is None:
                continue
            _exclude(context, name)
            declaration = _nearest_ancestor(
                node,
                {"lexical_declaration", "variable_declaration"},
            ) or node
            if _node_text(declaration, source).lstrip().startswith("var "):
                scope = _javascript_function_scope(node)
            else:
                scope = _javascript_lexical_scope(node)
            for identifier in _identifier_nodes(name):
                _add_local_binding(
                    context,
                    name_node=identifier,
                    source=source,
                    scope=scope,
                    declaration_start_byte=declaration.start_byte,
                    active_start_byte=scope.start_byte,
                )
            continue
        if node.type == "catch_clause":
            parameter = node.child_by_field_name("parameter")
            body = node.child_by_field_name("body")
            if parameter is None or body is None:
                continue
            _exclude(context, parameter)
            for identifier in _identifier_nodes(parameter):
                _add_local_binding(
                    context,
                    name_node=identifier,
                    source=source,
                    scope=body,
                    declaration_start_byte=node.start_byte,
                    active_start_byte=body.start_byte,
                )


def _collect_go_context(
    root: Any,
    source: bytes,
    context: _SyntaxContextBuilder,
) -> None:
    function_types = {"function_declaration", "method_declaration", "func_literal"}
    for node in _walk_nodes(root):
        if node.type in {"import_spec", "package_clause"}:
            _exclude(context, node)
            continue
        if node.type in {
            "function_declaration",
            "method_declaration",
            "type_spec",
            "const_spec",
        }:
            _exclude(context, node.child_by_field_name("name"))
        if node.type in function_types:
            body = node.child_by_field_name("body")
            if body is None:
                continue
            for field in ("receiver", "parameters"):
                parameters = node.child_by_field_name(field)
                if parameters is None:
                    continue
                for parameter in parameters.named_children:
                    for name in _field_children(parameter, "name"):
                        _exclude(context, name)
                        _add_local_binding(
                            context,
                            name_node=name,
                            source=source,
                            scope=body,
                            declaration_start_byte=node.start_byte,
                            active_start_byte=body.start_byte,
                        )
            continue
        if node.type in {"short_var_declaration", "var_spec"}:
            target = node.child_by_field_name("left")
            if target is None:
                names = _field_children(node, "name")
            else:
                names = _identifier_nodes(target)
                _exclude(context, target)
            scope = _scope_node(node, {"block", "source_file"})
            for name in names:
                _exclude(context, name)
                _add_local_binding(
                    context,
                    name_node=name,
                    source=source,
                    scope=scope,
                    declaration_start_byte=node.start_byte,
                    active_start_byte=node.end_byte,
                )
            continue
        if node.type == "range_clause":
            target = node.child_by_field_name("left")
            loop = _nearest_ancestor(node, {"for_statement"})
            body = loop.child_by_field_name("body") if loop is not None else None
            if target is None or body is None:
                continue
            _exclude(context, target)
            for name in _identifier_nodes(target):
                _add_local_binding(
                    context,
                    name_node=name,
                    source=source,
                    scope=body,
                    declaration_start_byte=node.start_byte,
                    active_start_byte=body.start_byte,
                )


def _rust_scope(node: Any) -> Any:
    return _scope_node(node, {"block", "declaration_list", "source_file"})


def _collect_rust_context(
    root: Any,
    source: bytes,
    context: _SyntaxContextBuilder,
) -> None:
    for node in _walk_nodes(root):
        if node.type in {"use_declaration", "extern_crate_declaration"}:
            _exclude(context, node)
            continue
        if node.type == "mod_item":
            name = node.child_by_field_name("name")
            _exclude(context, name)
            if name is not None:
                scope = _rust_scope(node)
                _add_local_binding(
                    context,
                    name_node=name,
                    source=source,
                    scope=scope,
                    declaration_start_byte=node.start_byte,
                    active_start_byte=scope.start_byte,
                )
            continue
        if node.type in _RUST_ITEM_TYPES:
            name = node.child_by_field_name("name")
            _exclude(context, name)
            if name is not None:
                scope = _rust_scope(node)
                _add_local_binding(
                    context,
                    name_node=name,
                    source=source,
                    scope=scope,
                    declaration_start_byte=node.start_byte,
                    active_start_byte=scope.start_byte,
                )
            parameters = node.child_by_field_name("parameters")
            body = node.child_by_field_name("body")
            if parameters is not None and body is not None:
                for parameter in parameters.named_children:
                    pattern = parameter.child_by_field_name("pattern")
                    if pattern is None:
                        continue
                    _exclude(context, pattern)
                    for identifier in _identifier_nodes(pattern):
                        _add_local_binding(
                            context,
                            name_node=identifier,
                            source=source,
                            scope=body,
                            declaration_start_byte=node.start_byte,
                            active_start_byte=body.start_byte,
                        )
            continue
        if node.type == "let_declaration":
            pattern = node.child_by_field_name("pattern")
            if pattern is None:
                continue
            _exclude(context, pattern)
            scope = _rust_scope(node)
            for identifier in _identifier_nodes(pattern):
                _add_local_binding(
                    context,
                    name_node=identifier,
                    source=source,
                    scope=scope,
                    declaration_start_byte=node.start_byte,
                    active_start_byte=node.end_byte,
                )
            continue
        if node.type == "for_expression":
            pattern = node.child_by_field_name("pattern")
            body = node.child_by_field_name("body")
            if pattern is None or body is None:
                continue
            _exclude(context, pattern)
            for identifier in _identifier_nodes(pattern):
                _add_local_binding(
                    context,
                    name_node=identifier,
                    source=source,
                    scope=body,
                    declaration_start_byte=node.start_byte,
                    active_start_byte=body.start_byte,
                )
        if node.type in {"field_declaration", "enum_variant"}:
            _exclude(context, node.child_by_field_name("name"))
