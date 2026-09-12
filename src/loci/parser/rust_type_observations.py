"""Exact, declaration-owned Rust type observations.

Only names written in Rust declaration syntax are collected here.  Resolution
is deliberately left to the graph layer: a spelling without a lexical type
binding or an authored ``use`` binding is never given a repository origin.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
from pathlib import Path
from typing import Any, Sequence

from .imports import ImportExtractionError, _extract_rust_import
from .reference_models import ImportBinding
from .symbols import Symbol
from .type_models import LocalTypeBinding, RawTypeObservation, TypeDeclarationOwner
from .type_observations import (
    MAX_TYPE_BINDINGS_PER_OBSERVATION,
    MAX_TYPE_OBSERVATIONS_PER_FILE,
    MAX_TYPE_PATH_SEGMENTS,
    TypeExtractionError,
)


_PRIMITIVES = frozenset({
    "bool", "char", "str", "i8", "i16", "i32", "i64", "i128", "isize",
    "u8", "u16", "u32", "u64", "u128", "usize", "f32", "f64",
})
_OWNER_NODES = frozenset({
    "function_item", "function_signature_item", "struct_item", "enum_item",
    "trait_item", "impl_item", "type_item",
})
_LOCAL_TYPE_NODES = frozenset({"type_item", "struct_item", "enum_item", "trait_item"})


@dataclass(frozen=True, slots=True)
class _Owner:
    node: Any
    symbol: Symbol | None


@dataclass(frozen=True, slots=True)
class _Local:
    binding: LocalTypeBinding
    active_start: int
    module_start: int
    module_end: int


@dataclass(frozen=True, slots=True)
class _Import:
    binding: ImportBinding
    module_start: int
    module_end: int


def extract_rust_type_observations(
    path: Path, *, source_file: str, source_hash: str, symbols: Sequence[Symbol],
) -> tuple[RawTypeObservation, ...]:
    """Extract supported authored Rust declaration type sites from ``path``."""
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

        root = Parser(get_language("rust")).parse(source).root_node
    except Exception as exc:
        raise TypeExtractionError("TYPE_PARSE_FAILED", str(exc), "parse_failed") from exc
    if root.has_error:
        raise TypeExtractionError(
            "TYPE_PARSE_FAILED", f"{source_file} could not be parsed for Rust types", "parse_error"
        )

    file_symbols = tuple(symbol for symbol in symbols if symbol.file_path == source_file)
    owners = _owners(root, file_symbols)
    imports = _imports(root, source, source_file, source_hash)
    locals_ = _locals(root, source, file_symbols)
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

        local_values = _visible_locals(locals_, path_value[:1], node)
        import_values = _visible_imports(imports, path_value[:1], node)
        # A binding in a strictly narrower lexical scope shadows an outer
        # ``use``.  Same-scope declarations remain ambiguous: this extractor
        # does not invent Rust name-resolution precedence for an invalid or
        # conditionally compiled collision.
        if local_values and import_values and all(
            local.binding.scope_start_byte > imported.scope_start_byte
            or local.binding.scope_end_byte < imported.scope_end_byte
            for local in local_values for imported in import_values
        ):
            import_values = ()
        total = len(local_values) + len(import_values)
        truncated = max(0, total - MAX_TYPE_BINDINGS_PER_OBSERVATION)
        local_values = local_values[:MAX_TYPE_BINDINGS_PER_OBSERVATION]
        import_values = import_values[:MAX_TYPE_BINDINGS_PER_OBSERVATION - len(local_values)]

        if unsupported_reason is not None:
            state = "unsupported"
        elif len(local_values) > 1 or (local_values and import_values) or len(import_values) > 1:
            state = "ambiguous"
        elif local_values:
            state = "shadowed" if local_values[0].binding.kind == "type_parameter" else "local"
        elif import_values:
            state = "imported"
        else:
            state = "unbound"

        observations.append(RawTypeObservation(
            source_file=source_file,
            language="rust",
            source_hash=source_hash,
            line=source[:node.start_byte].count(b"\n") + 1,
            column=node.start_byte - source.rfind(b"\n", 0, node.start_byte),
            start_byte=node.start_byte,
            end_byte=node.end_byte,
            text=_text(source, node),
            path=path_value,
            relation=relation,
            context=context,
            lookup_space="type",
            owner=_owner_for(node, owners),
            local_bindings=tuple(item.binding for item in local_values),
            import_bindings=tuple(import_values),
            binding_state=state,
            candidates_complete=not truncated,
            candidates_truncated=truncated,
            unsupported_reason=unsupported_reason,
        ))

    def expression(node: Any | None, context: str, *, relation: str = "uses_type") -> None:
        if node is None:
            return
        if node.type == "type_identifier":
            name = _text(source, node)
            if name not in _PRIMITIVES and name != "Self":
                add(node, (name,), context=context, relation=relation)
            elif name == "Self":
                add(node, (name,), context=context, relation=relation)
            return
        if node.type == "scoped_type_identifier":
            path_value = _scoped_path(node, source)
            if path_value is None:
                add(node, (), context=context, relation=relation,
                    unsupported_reason="unsupported_associated_type_projection")
            elif _visible_locals(locals_, path_value[:1], node):
                add(node, (), context=context, relation=relation,
                    unsupported_reason="unsupported_associated_type_projection")
            else:
                # A qualified path is supported only through the binding for its
                # first segment; later graph resolution proves any member.
                add(node, path_value, context=context, relation=relation)
            return
        if node.type == "generic_type":
            expression(node.child_by_field_name("type"), context, relation=relation)
            arguments = node.child_by_field_name("type_arguments")
            if arguments is not None:
                for argument in arguments.named_children:
                    expression(argument, "type_argument")
            return
        if node.type in {"reference_type", "pointer_type", "slice_type", "parenthesized_type"}:
            for child in node.named_children:
                expression(child, context, relation=relation)
            return
        if node.type == "array_type":
            expression(node.child_by_field_name("element"), context, relation=relation)
            return
        if node.type in {"tuple_type", "function_type"}:
            for child in node.named_children:
                expression(child, context, relation=relation)
            return
        if node.type == "bounded_type":
            for child in node.named_children:
                if child.type == "dynamic_type":
                    expression(child.child_by_field_name("trait"), context, relation=relation)
                else:
                    expression(child, context, relation=relation)
            return
        if node.type == "dynamic_type":
            expression(node.child_by_field_name("trait"), context, relation=relation)
            return
        if node.type == "trait_bounds":
            for child in node.named_children:
                expression(child, context, relation=relation)
            return
        if node.type in {"abstract_type", "impl_trait_type", "qualified_type", "bracketed_type",
                         "macro_invocation", "macro_type"}:
            add(node, (), context=context, relation=relation,
                unsupported_reason=f"unsupported_{node.type}")
            return
        if node.type in {"unit_type", "never_type", "lifetime", "primitive_type"}:
            return
        add(node, (), context=context, relation=relation,
            unsupported_reason=f"unsupported_{node.type}")

    def bounds(node: Any | None, *, context: str, relation: str = "uses_type") -> None:
        if node is None:
            return
        for child in node.named_children:
            expression(child, context, relation=relation)

    def where_clause(node: Any | None) -> None:
        if node is None:
            return
        for predicate in node.named_children:
            if predicate.type != "where_predicate":
                add(predicate, (), context="constraint", unsupported_reason="unsupported_where_predicate")
                continue
            expression(predicate.child_by_field_name("left"), "constraint")
            bounds(predicate.child_by_field_name("bounds"), context="constraint")

    def generic_constraints(node: Any | None) -> None:
        if node is None:
            return
        for parameter in node.named_children:
            if parameter.type != "type_parameter":
                continue
            bounds(parameter.child_by_field_name("bounds"), context="constraint")
            expression(parameter.child_by_field_name("default_type"), "type_argument")

    def signature(node: Any) -> None:
        generic_constraints(node.child_by_field_name("type_parameters"))
        parameters = node.child_by_field_name("parameters")
        if parameters is not None:
            for parameter in parameters.named_children:
                expression(parameter.child_by_field_name("type"), "annotation")
        expression(node.child_by_field_name("return_type"), "return")
        where_clause(next((child for child in node.named_children if child.type == "where_clause"), None))

    for node in _walk(root):
        if node.type in {"function_item", "function_signature_item"}:
            signature(node)
        elif node.type == "type_item":
            generic_constraints(node.child_by_field_name("type_parameters"))
            where_clause(next((child for child in node.named_children if child.type == "where_clause"), None))
            expression(node.child_by_field_name("type"), "alias")
        elif node.type == "struct_item":
            generic_constraints(node.child_by_field_name("type_parameters"))
            where_clause(next((child for child in node.named_children if child.type == "where_clause"), None))
            for field in _fields(node):
                expression(field.child_by_field_name("type") if field.type == "field_declaration" else field, "property")
        elif node.type == "enum_item":
            generic_constraints(node.child_by_field_name("type_parameters"))
            where_clause(next((child for child in node.named_children if child.type == "where_clause"), None))
            for field in _fields(node):
                expression(field.child_by_field_name("type") if field.type == "field_declaration" else field, "property")
        elif node.type == "trait_item":
            generic_constraints(node.child_by_field_name("type_parameters"))
            bounds(node.child_by_field_name("bounds"), context="supertrait", relation="supertrait")
            where_clause(next((child for child in node.named_children if child.type == "where_clause"), None))
            for associated in (child for child in _walk(node) if child.type == "associated_type"):
                bounds(associated.child_by_field_name("bounds"), context="constraint")
        elif node.type == "impl_item":
            generic_constraints(node.child_by_field_name("type_parameters"))
            expression(node.child_by_field_name("trait"), "impl_trait", relation="impl_trait")
            expression(node.child_by_field_name("type"), "impl_self_type", relation="impl_self_type")
            where_clause(next((child for child in node.named_children if child.type == "where_clause"), None))
    return tuple(observations)


def _owners(root: Any, symbols: Sequence[Symbol]) -> tuple[_Owner, ...]:
    indexed = {(symbol.byte_offset, symbol.byte_offset + symbol.byte_length): symbol for symbol in symbols}
    result: list[_Owner] = []
    for node in _walk(root):
        if node.type not in _OWNER_NODES:
            continue
        symbol = indexed.get((node.start_byte, node.end_byte))
        if symbol is None:
            # Rust attributes are preceding siblings, while extracted symbols
            # intentionally include them in the declaration span.
            decorated = [
                candidate for candidate in symbols
                if candidate.byte_offset <= node.start_byte
                and candidate.byte_offset + candidate.byte_length == node.end_byte
            ]
            if len(decorated) == 1:
                symbol = decorated[0]
        result.append(_Owner(node, symbol))
    return tuple(result)


def _owner_for(node: Any, owners: Sequence[_Owner]) -> TypeDeclarationOwner:
    containing = [owner for owner in owners if owner.node.start_byte <= node.start_byte and node.end_byte <= owner.node.end_byte]
    if not containing:
        return TypeDeclarationOwner(kind="unindexed", start_byte=node.start_byte, end_byte=node.end_byte)
    nearest = min(containing, key=lambda owner: (owner.node.end_byte - owner.node.start_byte, -owner.node.start_byte))
    if nearest.symbol is None:
        return TypeDeclarationOwner(kind="unindexed", start_byte=nearest.node.start_byte, end_byte=nearest.node.end_byte)
    return TypeDeclarationOwner(
        kind=nearest.symbol.kind,
        start_byte=nearest.symbol.byte_offset,
        end_byte=nearest.symbol.byte_offset + nearest.symbol.byte_length,
    )


def _imports(root: Any, source: bytes, source_file: str, source_hash: str) -> tuple[_Import, ...]:
    result: list[_Import] = []
    for node in _walk(root):
        if node.type not in {"use_declaration", "extern_crate_declaration", "mod_item"}:
            continue
        common = {
            "source_file": source_file, "language": "rust", "line": node.start_point.row + 1,
            "text": _text(source, node), "source_hash": source_hash,
        }
        module = _module_scope(node)
        if module is None:
            continue
        try:
            for record in _extract_rust_import(node, source, common):
                result.extend(_Import(binding, module.start_byte, module.end_byte) for binding in record.bindings)
        except ImportExtractionError as exc:
            raise TypeExtractionError("TYPE_BINDING_LIMIT", str(exc), "binding_limit") from exc
    return tuple(result)


def _locals(root: Any, source: bytes, symbols: Sequence[Symbol]) -> tuple[_Local, ...]:
    indexed = {(symbol.byte_offset, symbol.byte_offset + symbol.byte_length): symbol for symbol in symbols}
    result: list[_Local] = []
    for node in _walk(root):
        if node.type in _LOCAL_TYPE_NODES:
            name = node.child_by_field_name("name")
            scope = _lexical_scope(node)
            module = _module_scope(node)
            if name is not None and scope is not None and module is not None:
                symbol = indexed.get((node.start_byte, node.end_byte))
                kind = symbol.kind if symbol is not None else "unindexed"
                namespace = "both" if kind == "enum" else "type"
                result.append(_make_local(
                    name, _text(source, name), kind, namespace, scope, scope.start_byte,
                    declaration_start=(symbol.byte_offset if symbol is not None else node.start_byte),
                    declaration_end=(symbol.byte_offset + symbol.byte_length if symbol is not None else node.end_byte),
                    module_start=module.start_byte,
                    module_end=module.end_byte,
                ))
        if node.type in _OWNER_NODES:
            module = _module_scope(node)
            if module is None:
                continue
            for parameter in _type_parameters(node):
                result.append(_make_local(
                    parameter, _text(source, parameter), "type_parameter", "type", node, node.start_byte,
                    module_start=module.start_byte, module_end=module.end_byte,
                ))
            if node.type in {"trait_item", "impl_item"}:
                # Rust supplies an implicit ``Self`` type parameter in these
                # declarations.  Retaining it prevents a same-spelled indexed
                # declaration from becoming an invented dependency.
                result.append(_make_local(
                    node, "Self", "type_parameter", "type", node, node.start_byte,
                    module_start=module.start_byte, module_end=module.end_byte,
                ))
    return tuple(result)


def _make_local(
    name: Any,
    value: str,
    kind: str,
    namespace: str,
    scope: Any,
    active_start: int,
    *,
    declaration_start: int | None = None,
    declaration_end: int | None = None,
    module_start: int | None = None,
    module_end: int | None = None,
) -> _Local:
    return _Local(
        LocalTypeBinding(
            name=value,
            kind=kind,
            namespace=namespace,
            declaration_start_byte=name.start_byte if declaration_start is None else declaration_start,
            declaration_end_byte=name.end_byte if declaration_end is None else declaration_end,
            scope_start_byte=scope.start_byte,
            scope_end_byte=scope.end_byte,
        ),
        active_start,
        scope.start_byte if module_start is None else module_start,
        scope.end_byte if module_end is None else module_end,
    )


def _type_parameters(node: Any) -> tuple[Any, ...]:
    parameters = node.child_by_field_name("type_parameters")
    if parameters is None:
        return ()
    return tuple(
        parameter.child_by_field_name("name")
        for parameter in parameters.named_children
        if parameter.type == "type_parameter" and parameter.child_by_field_name("name") is not None
    )


def _lexical_scope(node: Any) -> Any | None:
    current = node.parent
    while current is not None:
        if current.type in {"source_file", "block"}:
            return current
        if current.type == "declaration_list" and current.parent is not None:
            if current.parent.type == "mod_item":
                return current
            if current.parent.type in {"trait_item", "impl_item"}:
                # An associated type is named through Self or a qualified
                # projection. It is not a bare item in the enclosing module.
                return None
        current = current.parent
    return None


def _module_scope(node: Any) -> Any | None:
    """Return the source unit or nearest inline module containing ``node``."""
    current = node
    while current is not None:
        if current.type == "source_file":
            return current
        if current.type == "declaration_list" and current.parent is not None and current.parent.type == "mod_item":
            return current
        current = current.parent
    return None


def _visible_locals(locals_: Sequence[_Local], root: tuple[str, ...], node: Any) -> tuple[_Local, ...]:
    if not root:
        return ()
    module = _module_scope(node)
    if module is None:
        return ()
    offset = node.start_byte
    matches = [
        item for item in locals_
        if item.binding.name == root[0]
        and item.binding.scope_start_byte <= offset <= item.binding.scope_end_byte
        and item.active_start <= offset
        and (item.module_start, item.module_end) == (module.start_byte, module.end_byte)
    ]
    if not matches:
        return ()
    nearest_start = max(item.binding.scope_start_byte for item in matches)
    return tuple(item for item in matches if item.binding.scope_start_byte == nearest_start)


def _visible_imports(imports: Sequence[_Import], root: tuple[str, ...], node: Any) -> tuple[ImportBinding, ...]:
    if not root:
        return ()
    module = _module_scope(node)
    if module is None:
        return ()
    return tuple(
        item.binding for item in imports
        if (item.module_start, item.module_end) == (module.start_byte, module.end_byte)
        and item.binding.local_name == root[0]
        and item.binding.kind in {"symbol", "module", "namespace"}
        and item.binding.scope_start_byte <= node.start_byte
        and node.end_byte <= item.binding.scope_end_byte
    )


def _scoped_path(node: Any, source: bytes) -> tuple[str, ...] | None:
    """Return simple authored module-qualified paths, never projections."""
    pieces = tuple(piece for piece in _text(source, node).split("::") if piece)
    if not pieces or any(not piece.isidentifier() for piece in pieces):
        return None
    if pieces[0] in {"Self", "crate", "self", "super"}:
        return None
    return pieces


def _fields(node: Any) -> tuple[Any, ...]:
    result: list[Any] = []
    for child in _walk(node):
        if child.type == "field_declaration":
            result.append(child)
        elif child.type == "ordered_field_declaration_list":
            result.extend(child.named_children)
    return tuple(result)


def _walk(node: Any | None):
    if node is None:
        return
    yield node
    for child in node.named_children:
        yield from _walk(child)


def _text(source: bytes, node: Any) -> str:
    return source[node.start_byte:node.end_byte].decode("utf-8")
