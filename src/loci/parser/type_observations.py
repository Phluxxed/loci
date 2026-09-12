"""Bounded authored type-site extraction, with language-specific adapters.

This module deliberately only records authored syntax.  Resolving a record to
an indexed declaration belongs to the graph layer; extraction must never make
repository-wide guesses from a spelling.
"""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from dataclasses import dataclass
import hashlib
from pathlib import Path
from typing import Any, Literal

from ._javascript_bindings import extract_javascript_import_bindings
from .reference_models import ImportBinding
from .symbols import Symbol
from .type_models import LocalTypeBinding, RawTypeObservation, TypeDeclarationOwner


MAX_TYPE_OBSERVATIONS_PER_FILE = 100_000
MAX_TYPE_BINDINGS_PER_OBSERVATION = 16
MAX_TYPE_PATH_SEGMENTS = 16

_PRIMITIVES = {
    "any", "unknown", "never", "void", "undefined", "null", "boolean",
    "number", "string", "symbol", "bigint", "object", "this",
}
_UNSUPPORTED_TYPE_NODES = {
    "conditional_type", "mapped_type_clause", "infer_type", "template_type",
    "import_type", "internal_module", "module", "ambient_declaration",
}
_DECLARATION_NODES = {
    "class_declaration": "class",
    "interface_declaration": "interface",
    "type_alias_declaration": "type",
    "enum_declaration": "enum",
    "function_declaration": "function",
    "method_definition": "method",
    "variable_declarator": "constant",
    "arrow_function": "unindexed",
    "function_expression": "unindexed",
}


class TypeExtractionError(RuntimeError):
    """A typed extraction failure suitable for the index diagnostic layer."""

    def __init__(self, code: str, message: str, reason: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.reason = reason


@dataclass(frozen=True, slots=True)
class _Owner:
    node: Any
    kind: str
    symbol: Symbol | None


@dataclass(frozen=True, slots=True)
class _Binding:
    value: LocalTypeBinding


def extract_type_observations(
    path: Path,
    *,
    source_file: str,
    language: str,
    source_hash: str,
    symbols: Sequence[Symbol],
) -> tuple[RawTypeObservation, ...]:
    """Return exact supported type-site observations for one source file.

    A separate parse is intentional.  Import/reference extraction shares a
    batch today, while this family needs declaration ownership rather than an
    executable owner and must leave that established payload untouched.
    """
    if language == "python":
        from .python_type_observations import extract_python_type_observations

        return extract_python_type_observations(
            path, source_file=source_file, source_hash=source_hash, symbols=symbols,
        )
    if language != "typescript":
        return ()
    try:
        source = path.read_bytes()
    except OSError as exc:
        raise TypeExtractionError(
            "TYPE_SOURCE_READ_FAILED", f"could not read {source_file}: {exc}", "read_failed"
        ) from exc
    if hashlib.sha256(source).hexdigest() != source_hash:
        raise TypeExtractionError(
            "TYPE_SOURCE_HASH_MISMATCH",
            f"{source_file} changed after symbol extraction",
            "source_hash_mismatch",
        )
    try:
        from tree_sitter import Parser
        from tree_sitter_language_pack import get_language

        grammar = "tsx" if path.suffix.lower() == ".tsx" else "typescript"
        root = Parser(get_language(grammar)).parse(source).root_node
    except Exception as exc:
        raise TypeExtractionError(
            "TYPE_PARSE_FAILED", f"could not parse {source_file} for TypeScript types", "parse_failed"
        ) from exc
    if root.has_error:
        raise TypeExtractionError(
            "TYPE_PARSE_FAILED", f"{source_file} could not be parsed for TypeScript types", "parse_error"
        )

    file_symbols = tuple(symbol for symbol in symbols if symbol.file_path == source_file)
    owners = _owners(root, source, file_symbols)
    local_bindings = _local_bindings(root, source, file_symbols)
    imports = _import_bindings(root, source)
    observations: list[RawTypeObservation] = []
    consumed: set[tuple[int, int, str]] = set()

    def add(
        node: Any,
        path_value: tuple[str, ...],
        *,
        relation: Literal["uses_type", "extends", "implements"] = "uses_type",
        context: str = "annotation",
        lookup_space: Literal["type", "value"] = "type",
        unsupported_reason: str | None = None,
    ) -> None:
        if len(observations) >= MAX_TYPE_OBSERVATIONS_PER_FILE:
            raise TypeExtractionError(
                "TYPE_OBSERVATION_LIMIT", f"{source_file} exceeds the type-site limit", "site_limit"
            )
        key = (node.start_byte, node.end_byte, relation)
        if key in consumed:
            return
        consumed.add(key)
        if len(path_value) > MAX_TYPE_PATH_SEGMENTS:
            path_value = ()
            unsupported_reason = unsupported_reason or "path_too_deep"
        owner = _owner_for(node, owners)
        bindings, truncated, local_scope = _visible_bindings(
            local_bindings,
            path_value[0] if path_value else "",
            node.start_byte,
            lookup_space,
        )
        import_candidates, import_truncated, import_scope = _visible_imports(
            imports,
            path_value[0] if path_value else "",
            node.start_byte,
            lookup_space,
            remaining=max(0, MAX_TYPE_BINDINGS_PER_OBSERVATION - len(bindings)),
        )
        if bindings and local_scope != import_scope:
            # A binding in the nearest lexical scope hides an import from an
            # enclosing scope.  It is not a second candidate for resolution.
            import_candidates = ()
            import_truncated = 0
        truncated += import_truncated
        binding_state = _binding_state(
            path_value,
            bindings,
            import_candidates,
            unsupported_reason,
        )
        if binding_state == "unsupported" and unsupported_reason is None:
            unsupported_reason = _unsupported_binding_reason(
                path_value,
                bindings,
                import_candidates,
            )
        observations.append(
            RawTypeObservation(
                source_file=source_file,
                language="typescript",
                source_hash=source_hash,
                line=_line(source, node.start_byte),
                column=_column(source, node.start_byte),
                start_byte=node.start_byte,
                end_byte=node.end_byte,
                text=_text(source, node),
                path=path_value,
                relation=relation,
                context=context,
                lookup_space=lookup_space,
                owner=owner,
                local_bindings=bindings,
                import_bindings=import_candidates,
                binding_state=binding_state,
                candidates_complete=not truncated,
                candidates_truncated=truncated,
                unsupported_reason=unsupported_reason,
            )
        )

    def visit(node: Any) -> None:
        unsupported = _unsupported_container(node)
        if unsupported is node:
            add(node, (), context=_context(node), unsupported_reason=f"unsupported_{node.type}")
            return
        if node.type == "import_statement":
            return
        if node.type == "export_statement":
            # Export clauses are import-like surface syntax, but an exported
            # declaration remains the actual owner of its type sites.
            for child in node.named_children:
                if child.type != "export_clause":
                    visit(child)
            return
        if node.type in {"extends_clause", "extends_type_clause", "implements_clause"}:
            _heritage(node, source, add)
            # The helper consumes heads but leaves generic arguments to this
            # visitor so that they remain ordinary uses_type sites.
            for child in node.named_children:
                if child.type == "type_arguments":
                    visit(child)
                elif child.type == "generic_type":
                    for argument in child.named_children:
                        if argument.type == "type_arguments":
                            visit(argument)
            return
        if node.type == "type_query":
            target = next((child for child in node.named_children if child.type == "identifier"), None)
            if target is None:
                add(node, (), context="type_query", lookup_space="value", unsupported_reason="unsupported_type_query")
            else:
                add(target, (_text(source, target),), context="type_query", lookup_space="value")
            return
        if node.type == "nested_type_identifier":
            path_value = _nested_path(node, source)
            if len(path_value) != 2:
                add(node, (), context=_context(node), unsupported_reason="qualified_type_path")
            else:
                add(node, path_value, context=_context(node))
            return
        if node.type == "type_identifier":
            if not _declaration_name(node):
                value = _text(source, node)
                if value not in _PRIMITIVES and _in_type_position(node):
                    add(node, (value,), context=_context(node))
            return
        for child in node.named_children:
            visit(child)

    visit(root)
    return tuple(observations)


def _walk(node: Any) -> Iterator[Any]:
    yield node
    for child in node.named_children:
        yield from _walk(child)


def _owners(root: Any, source: bytes, symbols: Sequence[Symbol]) -> tuple[_Owner, ...]:
    result: list[_Owner] = []
    for node in _walk(root):
        kind = _DECLARATION_NODES.get(node.type)
        if kind is None:
            continue
        if node.type == "arrow_function" and node.parent is not None and node.parent.type == "variable_declarator":
            # The variable declarator is the declaration selected by the
            # ordinary symbol extractor.  Treating its arrow body as a second,
            # anonymous declaration would incorrectly steal parameter/return
            # annotations from that indexed owner.
            continue
        # A variable only owns type syntax when it carries a declared type or
        # introduces a named arrow; an arbitrary initializer must not own it.
        if node.type == "variable_declarator" and not _is_type_owner_variable(node):
            continue
        result.append(_Owner(node, kind, _matching_symbol(node, source, symbols, kind)))
    return tuple(result)


def _owner_kind_matches(owner_kind: str, symbol_kind: str) -> bool:
    if owner_kind == "unindexed":
        return False
    return owner_kind == symbol_kind or (owner_kind == "constant" and symbol_kind == "function")


def _is_type_owner_variable(node: Any) -> bool:
    return any(child.type in {"type_annotation", "arrow_function"} for child in node.named_children)


def _owner_for(node: Any, owners: Sequence[_Owner]) -> TypeDeclarationOwner:
    candidates = [
        owner for owner in owners
        if owner.node.start_byte <= node.start_byte and node.end_byte <= owner.node.end_byte
    ]
    if not candidates:
        return TypeDeclarationOwner(kind="unindexed", start_byte=node.start_byte, end_byte=node.end_byte)
    nearest = min(candidates, key=lambda owner: (owner.node.end_byte - owner.node.start_byte, -owner.node.start_byte))
    if nearest.symbol is None:
        return TypeDeclarationOwner(kind="unindexed", start_byte=nearest.node.start_byte, end_byte=nearest.node.end_byte)
    return TypeDeclarationOwner(
        kind=nearest.symbol.kind,
        start_byte=nearest.symbol.byte_offset,
        end_byte=nearest.symbol.byte_offset + nearest.symbol.byte_length,
    )


def _local_bindings(
    root: Any,
    source: bytes,
    symbols: Sequence[Symbol],
) -> tuple[_Binding, ...]:
    result: list[_Binding] = []
    root_end = root.end_byte
    for node in _walk(root):
        kind_namespace = _local_kind(node)
        if kind_namespace is None:
            continue
        kind, namespace = kind_namespace
        name_node = _declaration_name_node(node)
        if name_node is None:
            continue
        symbol = _matching_symbol(node, source, symbols, kind)
        if node.type == "variable_declarator" and symbol is not None and symbol.kind == "function":
            kind = "function"
        start = symbol.byte_offset if symbol is not None else node.start_byte
        end = start + symbol.byte_length if symbol is not None else node.end_byte
        scope = _binding_scope(node, root_end)
        result.append(_Binding(LocalTypeBinding(
            name=_text(source, name_node), kind=kind, namespace=namespace,
            declaration_start_byte=start, declaration_end_byte=end,
            scope_start_byte=scope[0], scope_end_byte=scope[1],
        )))
    for node in _walk(root):
        parameters = next(
            (child for child in node.named_children if child.type == "type_parameters"),
            None,
        )
        if parameters is None:
            continue
        for parameter in parameters.named_children:
            name = next(
                (child for child in parameter.named_children if child.type == "type_identifier"),
                None,
            )
            if name is not None:
                result.append(_Binding(LocalTypeBinding(
                    name=_text(source, name), kind="type_parameter", namespace="type",
                    declaration_start_byte=name.start_byte, declaration_end_byte=name.end_byte,
                    scope_start_byte=node.start_byte, scope_end_byte=node.end_byte,
                )))
    return tuple(result)


def _local_kind(node: Any) -> tuple[str, str] | None:
    mapping = {
        "class_declaration": ("class", "both"), "interface_declaration": ("interface", "type"),
        "type_alias_declaration": ("type", "type"), "enum_declaration": ("enum", "both"),
        "function_declaration": ("function", "value"), "method_definition": ("function", "value"),
        "variable_declarator": ("constant", "value"), "required_parameter": ("parameter", "value"),
        "optional_parameter": ("parameter", "value"),
    }
    return mapping.get(node.type)


def _declaration_name_node(node: Any) -> Any | None:
    if node.type == "variable_declarator":
        return node.child_by_field_name("name")
    return next((child for child in node.named_children if child.type in {"identifier", "type_identifier", "property_identifier"}), None)


def _node_decl_name(node: Any, source: bytes) -> str | None:
    """Name used to distinguish a symbol enclosing an export wrapper."""
    name = _declaration_name_node(node)
    if name is None:
        return None
    return _text(source, name)


def _binding_scope(node: Any, root_end: int) -> tuple[int, int]:
    if node.type in {"required_parameter", "optional_parameter"}:
        current = node.parent
        while current is not None:
            if current.type in _PARAMETER_SCOPE_NODES:
                return current.start_byte, current.end_byte
            current = current.parent
    current = node.parent
    while current is not None:
        if current.type in {"statement_block", "class_body", "interface_body", "program"}:
            return current.start_byte, current.end_byte
        current = current.parent
    return 0, root_end


_PARAMETER_SCOPE_NODES = {
    "function_declaration",
    "function_expression",
    "arrow_function",
    "method_definition",
    "method_signature",
    "function_type",
    "constructor_type",
    "call_signature",
    "construct_signature",
}


def _matching_symbol(
    node: Any,
    source: bytes,
    symbols: Sequence[Symbol],
    kind: str,
) -> Symbol | None:
    """Match one indexed declaration, including an enclosing export wrapper."""
    name = _node_decl_name(node, source)
    if name is None:
        return None
    candidates = [
        symbol for symbol in symbols
        if _owner_kind_matches(kind, symbol.kind)
        and symbol.name == name
        and symbol.byte_offset <= node.start_byte
        and node.end_byte <= symbol.byte_offset + symbol.byte_length
    ]
    return candidates[0] if len(candidates) == 1 else None


def _import_bindings(root: Any, source: bytes) -> tuple[ImportBinding, ...]:
    bindings: list[ImportBinding] = []
    for node in _walk(root):
        if node.type not in {"import_statement", "export_statement"}:
            continue
        source_node = node.child_by_field_name("source")
        if source_node is None:
            continue
        text = _text(source, source_node)
        specifier = text[1:-1] if len(text) >= 2 and text[:1] in {"'", '"'} else text
        bindings.extend(extract_javascript_import_bindings(
            node,
            source,
            specifier=specifier,
            import_line=_line(source, node.start_byte),
            import_text=_text(source, node),
        ))
    return tuple(bindings)


def _visible_bindings(
    values: Sequence[_Binding], name: str, offset: int, lookup_space: str,
) -> tuple[tuple[LocalTypeBinding, ...], int, tuple[int, int] | None]:
    matches = [
        item.value
        for item in values
        if item.value.name == name
        and item.value.scope_start_byte <= offset <= item.value.scope_end_byte
        and item.value.namespace in {lookup_space, "both"}
    ]
    if not matches:
        return (), 0, None
    matches.sort(
        key=lambda item: (
            item.scope_end_byte - item.scope_start_byte,
            -item.scope_start_byte,
            item.declaration_start_byte,
        )
    )
    scope = (matches[0].scope_start_byte, matches[0].scope_end_byte)
    nearest = [
        item
        for item in matches
        if (item.scope_start_byte, item.scope_end_byte) == scope
    ]
    return (
        tuple(nearest[:MAX_TYPE_BINDINGS_PER_OBSERVATION]),
        max(0, len(nearest) - MAX_TYPE_BINDINGS_PER_OBSERVATION),
        scope,
    )


def _visible_imports(
    values: Sequence[ImportBinding], name: str, offset: int, lookup_space: str,
    *, remaining: int,
) -> tuple[tuple[ImportBinding, ...], int, tuple[int, int] | None]:
    # ImportBinding already supplies an exact lexical scope.  Type-only imports
    # are valid in the type namespace; ordinary imports can also name classes.
    matches = [
        item
        for item in values
        if item.local_name == name
        and item.scope_start_byte <= offset <= item.scope_end_byte
    ]
    if not matches:
        return (), 0, None
    matches.sort(
        key=lambda item: (
            item.scope_end_byte - item.scope_start_byte,
            -item.scope_start_byte,
            item.declaration_start_byte,
        )
    )
    scope = (matches[0].scope_start_byte, matches[0].scope_end_byte)
    nearest = [
        item
        for item in matches
        if (item.scope_start_byte, item.scope_end_byte) == scope
    ]
    return tuple(nearest[:remaining]), max(0, len(nearest) - remaining), scope


def _binding_state(path: tuple[str, ...], local: tuple[LocalTypeBinding, ...], imported: tuple[ImportBinding, ...], unsupported: str | None) -> str:
    if unsupported is not None or not path:
        return "unsupported"
    if len(path) > 1 and (not imported or imported[0].kind != "namespace"):
        return "unsupported"
    if local:
        if imported:
            return "ambiguous"
        if local[0].kind in {"type_parameter", "parameter"}:
            return "shadowed"
        return "ambiguous" if len(local) > 1 and _same_scope(local[0], local[1]) else "local"
    if imported:
        return "ambiguous" if len(imported) > 1 else "imported"
    return "unbound"


def _unsupported_binding_reason(
    path: tuple[str, ...],
    local: tuple[LocalTypeBinding, ...],
    imported: tuple[ImportBinding, ...],
) -> str:
    if len(path) > 1:
        if local:
            return "qualified_local_namespace"
        if imported:
            return "qualified_non_namespace_import"
        return "qualified_unbound_namespace"
    return "unsupported_binding"


def _same_scope(left: LocalTypeBinding, right: LocalTypeBinding) -> bool:
    return (left.scope_start_byte, left.scope_end_byte) == (right.scope_start_byte, right.scope_end_byte)


def _heritage(node: Any, source: bytes, add: Any) -> None:
    relation = "extends" if node.type in {"extends_clause", "extends_type_clause"} else "implements"
    for child in node.named_children:
        head = child
        if child.type == "generic_type":
            head = child.named_children[0] if child.named_children else child
        lookup_space = "value" if node.type == "extends_clause" else "type"
        if head.type == "type_identifier":
            add(
                head,
                (_text(source, head),),
                relation=relation,
                context="heritage",
                lookup_space=lookup_space,
            )
        elif head.type == "nested_type_identifier":
            value = _nested_path(head, source)
            if len(value) == 2:
                add(
                    head,
                    value,
                    relation=relation,
                    context="heritage",
                    lookup_space=lookup_space,
                )
            else:
                add(child, (), relation=relation, context="heritage", unsupported_reason="qualified_heritage")
        elif head.type == "identifier":
            add(
                head,
                (_text(source, head),),
                relation=relation,
                context="heritage",
                lookup_space=lookup_space,
            )
        elif head.type == "member_expression":
            members = [
                child
                for child in head.named_children
                if child.type in {"identifier", "property_identifier"}
            ]
            if len(members) == 2:
                add(
                    head,
                    tuple(_text(source, member) for member in members),
                    relation=relation,
                    context="heritage",
                    lookup_space=lookup_space,
                )
            else:
                add(child, (), relation=relation, context="heritage", unsupported_reason="qualified_heritage")
        else:
            add(child, (), relation=relation, context="heritage", unsupported_reason="dynamic_heritage")


def _nested_path(node: Any, source: bytes) -> tuple[str, ...]:
    parts = []
    for child in node.named_children:
        if child.type in {"identifier", "type_identifier", "nested_type_identifier"}:
            if child.type == "nested_type_identifier":
                parts.extend(_nested_path(child, source))
            else:
                parts.append(_text(source, child))
    return tuple(parts)


def _declaration_name(node: Any) -> bool:
    parent = node.parent
    if parent is None:
        return False
    if parent.type in {"class_declaration", "interface_declaration", "type_alias_declaration", "enum_declaration"}:
        return node == _declaration_name_node(parent)
    if parent.type == "type_parameter":
        return node == _declaration_name_node(parent)
    return False


def _in_type_position(node: Any) -> bool:
    current = node.parent
    while current is not None:
        if current.type in {"type_annotation", "type_alias_declaration", "type_arguments", "type_parameter", "extends_clause", "implements_clause", "class_heritage", "type_query", "as_expression", "satisfies_expression"}:
            return True
        if current.type in {"program", "statement_block", "class_body", "interface_body"}:
            return False
        current = current.parent
    return False


def _context(node: Any) -> str:
    current = node.parent
    while current is not None:
        if current.type == "type_query": return "type_query"
        if current.type == "type_arguments": return "type_argument"
        if current.type == "constraint": return "constraint"
        if current.type == "default_type": return "constraint"
        if current.type in {"property_signature", "public_field_definition", "method_signature"}: return "property"
        if current.type == "type_alias_declaration": return "alias"
        if current.type == "type_annotation":
            owner = current.parent
            if owner is not None and owner.type in {"property_signature", "public_field_definition", "method_signature"}:
                return "property"
            if owner is not None and owner.type in {"function_declaration", "method_definition", "arrow_function", "method_signature"}:
                return "return"
            return "annotation"
        current = current.parent
    return "annotation"


def _unsupported_container(node: Any) -> Any | None:
    if node.type in _UNSUPPORTED_TYPE_NODES:
        return node
    if node.type == "nested_type_identifier" and len(node.named_children) > 2:
        return node
    return None


def _text(source: bytes, node: Any) -> str:
    return source[node.start_byte:node.end_byte].decode("utf-8", errors="replace")


def _line(source: bytes, offset: int) -> int:
    return source[:offset].count(b"\n") + 1


def _column(source: bytes, offset: int) -> int:
    previous = source.rfind(b"\n", 0, offset)
    return offset + 1 if previous < 0 else offset - previous
