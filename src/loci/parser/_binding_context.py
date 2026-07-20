from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Literal, TypeAlias

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

CallableKind: TypeAlias = Literal["function", "method"]
ExecutableOwnerKind: TypeAlias = Literal["file", "callable", "unindexed"]
_CALLABLE_KINDS = {"function", "method"}
_EXECUTABLE_OWNER_KINDS = {"file", "callable", "unindexed"}


@dataclass(frozen=True, slots=True)
class LexicalBinding:
    name: str
    kind: str
    scope_start_byte: int
    scope_end_byte: int
    scope_type: str
    declaration_start_byte: int
    declaration_end_byte: int
    active_start_byte: int
    callable_kind: CallableKind | None


@dataclass(frozen=True, slots=True)
class ExecutableOwner:
    kind: ExecutableOwnerKind
    definition_start_byte: int | None
    definition_end_byte: int | None
    body_start_byte: int | None
    body_end_byte: int | None

    def __post_init__(self) -> None:
        if self.kind not in _EXECUTABLE_OWNER_KINDS:
            raise ValueError("kind must be a supported executable owner kind")
        ranges = (
            self.definition_start_byte,
            self.definition_end_byte,
            self.body_start_byte,
            self.body_end_byte,
        )
        if self.kind == "file":
            if any(value is not None for value in ranges):
                raise ValueError("file owners cannot carry definition or body ranges")
            return
        if any(type(value) is not int or value < 0 for value in ranges):
            raise ValueError("callable and unindexed owners require non-negative ranges")
        definition_start = self.definition_start_byte
        definition_end = self.definition_end_byte
        body_start = self.body_start_byte
        body_end = self.body_end_byte
        assert definition_start is not None
        assert definition_end is not None
        assert body_start is not None
        assert body_end is not None
        if not (
            definition_start < definition_end
            and body_start < body_end
            and definition_start <= body_start
            and body_end <= definition_end
        ):
            raise ValueError("owner definition and body ranges must be ordered and nested")

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "definition_start_byte": self.definition_start_byte,
            "definition_end_byte": self.definition_end_byte,
            "body_start_byte": self.body_start_byte,
            "body_end_byte": self.body_end_byte,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> ExecutableOwner:
        expected = {
            "kind",
            "definition_start_byte",
            "definition_end_byte",
            "body_start_byte",
            "body_end_byte",
        }
        if not isinstance(value, Mapping) or set(value) != expected:
            raise ValueError("executable owner fields are missing or unknown")
        return cls(
            kind=value["kind"],
            definition_start_byte=value["definition_start_byte"],
            definition_end_byte=value["definition_end_byte"],
            body_start_byte=value["body_start_byte"],
            body_end_byte=value["body_end_byte"],
        )


@dataclass(frozen=True, slots=True)
class SyntaxContext:
    local_bindings: tuple[LexicalBinding, ...]
    executable_owners: tuple[ExecutableOwner, ...]
    excluded_subtrees: frozenset[tuple[int, int, str]]
    unsupported_import_starts: frozenset[int]


@dataclass(slots=True)
class _SyntaxContextBuilder:
    local_bindings: list[LexicalBinding]
    executable_owners: list[ExecutableOwner]
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
        executable_owners=[],
        excluded_subtrees=set(),
        unsupported_import_starts=set(),
    )
    _collect_executable_owners(root, language, context)
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
        executable_owners=tuple(context.executable_owners),
        excluded_subtrees=frozenset(context.excluded_subtrees),
        unsupported_import_starts=frozenset(context.unsupported_import_starts),
    )


def nearest_executable_owner(
    context: SyntaxContext,
    node: Any,
) -> ExecutableOwner:
    containing = [
        owner
        for owner in context.executable_owners
        if owner.body_start_byte is not None
        and owner.body_end_byte is not None
        and owner.body_start_byte <= node.start_byte
        and node.end_byte <= owner.body_end_byte
    ]
    if not containing:
        return ExecutableOwner(
            kind="file",
            definition_start_byte=None,
            definition_end_byte=None,
            body_start_byte=None,
            body_end_byte=None,
        )
    return min(
        containing,
        key=lambda owner: (
            owner.body_end_byte - owner.body_start_byte,
            -owner.body_start_byte,
        ),
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


def _collect_executable_owners(
    root: Any,
    language: str,
    context: _SyntaxContextBuilder,
) -> None:
    callable_types = {
        "python": {"function_definition"},
        "javascript": {"function_declaration", "method_definition"},
        "typescript": {"function_declaration", "method_definition"},
        "go": {"function_declaration", "method_declaration"},
        "rust": {"function_item"},
    }[language]
    unindexed_types = {
        "python": {"lambda"},
        "javascript": {
            "arrow_function",
            "function_expression",
            "generator_function",
            "generator_function_declaration",
        },
        "typescript": {
            "arrow_function",
            "function_expression",
            "generator_function",
            "generator_function_declaration",
        },
        "go": {"func_literal"},
        "rust": {"closure_expression"},
    }[language]
    for node in _walk_nodes(root):
        if node.type not in callable_types | unindexed_types:
            continue
        body = node.child_by_field_name("body")
        if body is None or body.start_byte >= body.end_byte:
            continue
        definition_start = node.start_byte
        definition_end = node.end_byte
        if language == "python":
            definition_start, definition_end = _python_definition_range(node)
        context.executable_owners.append(
            ExecutableOwner(
                kind="callable" if node.type in callable_types else "unindexed",
                definition_start_byte=definition_start,
                definition_end_byte=definition_end,
                body_start_byte=body.start_byte,
                body_end_byte=body.end_byte,
            )
        )


def _add_local_binding(
    context: _SyntaxContextBuilder,
    *,
    name_node: Any,
    source: bytes,
    scope: Any,
    declaration_start_byte: int,
    active_start_byte: int,
    scope_type: str | None = None,
    kind: str = "value",
    declaration_end_byte: int | None = None,
    callable_kind: CallableKind | None = None,
) -> None:
    name = _node_text(name_node, source)
    if not name or name == "_":
        return
    context.local_bindings.append(
        LexicalBinding(
            name=name,
            kind=kind,
            scope_start_byte=scope.start_byte,
            scope_end_byte=scope.end_byte,
            scope_type=scope_type or scope.type,
            declaration_start_byte=declaration_start_byte,
            declaration_end_byte=(
                declaration_end_byte
                if declaration_end_byte is not None
                else declaration_start_byte
            ),
            active_start_byte=active_start_byte,
            callable_kind=callable_kind,
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


def _python_callable_kind(node: Any) -> CallableKind:
    current = node.parent
    while current is not None:
        if current.type in {"function_definition", "lambda"}:
            return "function"
        if current.type == "class_definition":
            return "method"
        current = current.parent
    return "function"


def _python_definition_range(node: Any) -> tuple[int, int]:
    parent = node.parent
    if parent is not None and parent.type == "decorated_definition":
        return parent.start_byte, node.end_byte
    return node.start_byte, node.end_byte


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
                definition_start, definition_end = _python_definition_range(node)
                callable_kind = (
                    _python_callable_kind(node)
                    if node.type == "function_definition"
                    else None
                )
                _add_local_binding(
                    context,
                    name_node=name,
                    source=source,
                    scope=scope,
                    declaration_start_byte=definition_start,
                    active_start_byte=node.end_byte,
                    kind="callable" if callable_kind is not None else "value",
                    declaration_end_byte=definition_end,
                    callable_kind=callable_kind,
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
                    definition_start, definition_end = _python_definition_range(node)
                    _add_local_binding(
                        context,
                        name_node=name,
                        source=source,
                        scope=body,
                        declaration_start_byte=definition_start,
                        active_start_byte=body.start_byte,
                        scope_type="definition_body",
                        kind="callable",
                        declaration_end_byte=definition_end,
                        callable_kind=_python_callable_kind(node),
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
                callable_kind = (
                    "function"
                    if node.type
                    in {"function_declaration", "generator_function_declaration"}
                    else None
                )
                _add_local_binding(
                    context,
                    name_node=name,
                    source=source,
                    scope=scope,
                    declaration_start_byte=node.start_byte,
                    active_start_byte=scope.start_byte,
                    kind="callable" if callable_kind is not None else "value",
                    declaration_end_byte=node.end_byte,
                    callable_kind=callable_kind,
                )
        if node.type in _JAVASCRIPT_FUNCTION_NODES:
            parameters = node.child_by_field_name("parameters")
            if parameters is not None:
                for parameter in parameters.named_children:
                    pattern = (
                        parameter.child_by_field_name("pattern")
                        or parameter.child_by_field_name("left")
                        or parameter.child_by_field_name("name")
                        or parameter
                    )
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
            name = node.child_by_field_name("name")
            _exclude(context, name)
            if name is not None and node.type != "method_declaration":
                scope = _scope_node(node, {"block", "source_file"})
                callable_kind = (
                    "function" if node.type == "function_declaration" else None
                )
                _add_local_binding(
                    context,
                    name_node=name,
                    source=source,
                    scope=scope,
                    declaration_start_byte=node.start_byte,
                    active_start_byte=scope.start_byte,
                    kind="callable" if callable_kind is not None else "value",
                    declaration_end_byte=node.end_byte,
                    callable_kind=callable_kind,
                )
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


def _rust_callable_kind(node: Any) -> CallableKind:
    current = node.parent
    while current is not None:
        if current.type in {"impl_item", "trait_item"}:
            return "method"
        if current.type in {"function_item", "block", "source_file", "mod_item"}:
            break
        current = current.parent
    return "function"


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
                callable_kind = (
                    _rust_callable_kind(node) if node.type == "function_item" else None
                )
                _add_local_binding(
                    context,
                    name_node=name,
                    source=source,
                    scope=scope,
                    declaration_start_byte=node.start_byte,
                    active_start_byte=scope.start_byte,
                    kind="callable" if callable_kind is not None else "value",
                    declaration_end_byte=node.end_byte,
                    callable_kind=callable_kind,
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
