from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Sequence

from loci.parser._reference_exports import (
    _RUST_ITEM_TYPES,
    _extract_local_exports,
    _field_children,
    _node_text,
    _walk_nodes,
)
from loci.parser._reference_paths import (
    _go_path,
    _javascript_path,
    _python_path,
    _rust_path,
)
from loci.parser.reference_models import (
    MAX_REFERENCE_RESOLUTION_CANDIDATES,
    MAX_SYMBOL_REFERENCES_PER_FILE,
    BindingState,
    ImportBinding,
    RawSymbolReference,
    ReferenceExtractionBatch,
)

if TYPE_CHECKING:
    from loci.parser.imports import RawImport


_IDENTIFIER_TYPES = {
    "identifier",
    "type_identifier",
    "package_identifier",
}


@dataclass(frozen=True, slots=True)
class _LocalBinding:
    name: str
    scope_start_byte: int
    scope_end_byte: int
    scope_type: str
    declaration_start_byte: int
    active_start_byte: int


@dataclass(slots=True)
class _SyntaxContext:
    local_bindings: list[_LocalBinding]
    excluded_subtrees: set[tuple[int, int, str]]
    unsupported_import_starts: set[int]


@dataclass(frozen=True, slots=True)
class _PathObservation:
    node: Any
    path: tuple[str, ...]
    supported: bool = True


def extract_reference_batch(
    root_node: Any,
    source: bytes,
    *,
    source_file: str,
    language: str,
    source_hash: str,
    imports: Sequence[RawImport],
) -> ReferenceExtractionBatch:
    """Extract local exports and import-rooted references from an existing tree."""
    if language not in {"python", "javascript", "typescript", "go", "rust"}:
        raise ValueError(f"unsupported reference language: {language}")

    context = _collect_syntax_context(root_node, source, language)
    exports = _extract_local_exports(
        root_node,
        source,
        source_file=source_file,
        language=language,
        source_hash=source_hash,
        imports=imports,
    )
    bindings_by_name: dict[str, list[ImportBinding]] = {}
    go_deferred: list[ImportBinding] = []
    for raw_import in imports:
        for binding in raw_import.bindings:
            if binding.local_name is not None:
                bindings_by_name.setdefault(binding.local_name, []).append(binding)
            elif language == "go" and binding.kind == "namespace":
                go_deferred.append(binding)
    local_bindings_by_name: dict[str, list[_LocalBinding]] = {}
    for binding in context.local_bindings:
        local_bindings_by_name.setdefault(binding.name, []).append(binding)
    references: list[RawSymbolReference] = []
    for observation in _iter_path_observations(
        root_node,
        source,
        language,
        context.excluded_subtrees,
    ):
        reference = _match_observation(
            observation,
            source,
            source_file=source_file,
            language=language,
            source_hash=source_hash,
            named_bindings=bindings_by_name.get(observation.path[0], ()),
            deferred_bindings=go_deferred,
            local_bindings=local_bindings_by_name.get(observation.path[0], ()),
            unsupported_import_starts=context.unsupported_import_starts,
        )
        if reference is None:
            continue
        if len(references) >= MAX_SYMBOL_REFERENCES_PER_FILE:
            raise ValueError("references exceeds the per-file limit")
        references.append(reference)

    return ReferenceExtractionBatch(
        exports=tuple(exports),
        references=tuple(references),
    )


def _match_observation(
    observation: _PathObservation,
    source: bytes,
    *,
    source_file: str,
    language: str,
    source_hash: str,
    named_bindings: Sequence[ImportBinding],
    deferred_bindings: Sequence[ImportBinding],
    local_bindings: Sequence[_LocalBinding],
    unsupported_import_starts: set[int],
) -> RawSymbolReference | None:
    node = observation.node
    root_name = observation.path[0]
    all_named = [
        binding
        for binding in named_bindings
        if binding.kind not in {"blank", "glob", "side_effect"}
        and _binding_contains(binding, node)
    ]
    visible_named = [
        binding
        for binding in all_named
        if language != "python"
        or (
            binding.declaration_start_byte < node.start_byte
            and _python_import_scope_is_visible(binding, node)
        )
    ]
    candidates = _nearest_import_candidates(visible_named, language)

    if candidates:
        if len(candidates) > MAX_REFERENCE_RESOLUTION_CANDIDATES:
            raise ValueError("candidate bindings exceeds the candidate limit")
        state: BindingState
        if not observation.supported or any(
            candidate.declaration_start_byte in unsupported_import_starts
            for candidate in candidates
        ):
            state = "unsupported"
        elif len(candidates) > 1:
            state = "ambiguous"
        elif _binding_is_shadowed(
            candidates[0],
            node,
            language=language,
            local_bindings=local_bindings,
            all_named_imports=all_named,
        ):
            state = "shadowed"
        else:
            state = "definite"
        return _raw_reference(
            observation,
            source,
            source_file=source_file,
            language=language,
            source_hash=source_hash,
            candidates=tuple(candidates),
            state=state,
        )

    if language != "go" or not observation.supported or len(observation.path) < 2:
        return None

    deferred = [
        binding
        for binding in deferred_bindings
        if _binding_contains(binding, node)
    ]
    if not deferred or _unbound_go_root_is_shadowed(
        node,
        local_bindings,
    ):
        return None
    if len(deferred) > MAX_REFERENCE_RESOLUTION_CANDIDATES:
        raise ValueError("candidate bindings exceeds the candidate limit")
    return _raw_reference(
        observation,
        source,
        source_file=source_file,
        language=language,
        source_hash=source_hash,
        candidates=tuple(deferred),
        state="deferred",
    )


def _raw_reference(
    observation: _PathObservation,
    source: bytes,
    *,
    source_file: str,
    language: str,
    source_hash: str,
    candidates: tuple[ImportBinding, ...],
    state: BindingState,
) -> RawSymbolReference:
    node = observation.node
    return RawSymbolReference(
        source_file=source_file,
        language=language,
        line=node.start_point[0] + 1,
        column=node.start_point[1] + 1,
        start_byte=node.start_byte,
        end_byte=node.end_byte,
        text=_node_text(node, source),
        path=observation.path,
        candidate_bindings=candidates,
        binding_state=state,
        source_hash=source_hash,
    )


def _binding_contains(binding: ImportBinding, node: Any) -> bool:
    return (
        binding.scope_start_byte <= node.start_byte
        and node.end_byte <= binding.scope_end_byte
    )


def _nearest_import_candidates(
    bindings: list[ImportBinding],
    language: str,
) -> list[ImportBinding]:
    if not bindings:
        return []
    smallest_scope = min(
        binding.scope_end_byte - binding.scope_start_byte
        for binding in bindings
    )
    nearest = [
        binding
        for binding in bindings
        if binding.scope_end_byte - binding.scope_start_byte == smallest_scope
    ]
    if language == "python" and nearest:
        latest_declaration = max(
            binding.declaration_start_byte for binding in nearest
        )
        nearest = [
            binding
            for binding in nearest
            if binding.declaration_start_byte == latest_declaration
        ]
    return nearest


def _binding_is_shadowed(
    binding: ImportBinding,
    node: Any,
    *,
    language: str,
    local_bindings: Sequence[_LocalBinding],
    all_named_imports: list[ImportBinding],
) -> bool:
    matching_locals = [
        local
        for local in local_bindings
        if local.scope_start_byte <= node.start_byte
        and node.end_byte <= local.scope_end_byte
    ]
    if language == "python":
        for other in all_named_imports:
            if (
                _scope_span(other.scope_start_byte, other.scope_end_byte)
                < _scope_span(binding.scope_start_byte, binding.scope_end_byte)
            ):
                return True
        for local in matching_locals:
            same_scope = (
                local.scope_start_byte == binding.scope_start_byte
                and local.scope_end_byte == binding.scope_end_byte
            )
            if not same_scope:
                if local.scope_type in {
                    "function_definition",
                    "lambda",
                    "definition_body",
                }:
                    return True
                nearest_scope = _python_scope(node)
                if (
                    nearest_scope.start_byte != local.scope_start_byte
                    or nearest_scope.end_byte != local.scope_end_byte
                ):
                    continue
                if local.active_start_byte <= node.start_byte:
                    return True
                continue
            if (
                local.active_start_byte <= node.start_byte
                and local.declaration_start_byte > binding.declaration_start_byte
            ):
                return True
        return False
    if language == "javascript" or language == "typescript":
        return bool(matching_locals)
    return any(local.active_start_byte <= node.start_byte for local in matching_locals)


def _unbound_go_root_is_shadowed(
    node: Any,
    local_bindings: Sequence[_LocalBinding],
) -> bool:
    return any(
        local.scope_start_byte <= node.start_byte
        and node.end_byte <= local.scope_end_byte
        and local.active_start_byte <= node.start_byte
        for local in local_bindings
    )


def _scope_span(start: int, end: int) -> int:
    return end - start


def _python_import_scope_is_visible(binding: ImportBinding, node: Any) -> bool:
    ancestor = node
    while ancestor is not None:
        if (
            ancestor.start_byte == binding.scope_start_byte
            and ancestor.end_byte == binding.scope_end_byte
        ):
            if ancestor.type != "class_definition":
                return True
            nearest_scope = _python_scope(node)
            return (
                nearest_scope.start_byte == ancestor.start_byte
                and nearest_scope.end_byte == ancestor.end_byte
            )
        ancestor = ancestor.parent
    return False


def _collect_syntax_context(
    root: Any,
    source: bytes,
    language: str,
) -> _SyntaxContext:
    context = _SyntaxContext(
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
    return context


def _iter_path_observations(
    root: Any,
    source: bytes,
    language: str,
    excluded_subtrees: set[tuple[int, int, str]],
):
    def visit(node: Any):
        if _node_key(node) in excluded_subtrees:
            return
        observation = _path_observation(node, source, language)
        if observation is not None:
            yield observation
            return
        for child in node.named_children:
            yield from visit(child)

    yield from visit(root)


def _path_observation(
    node: Any,
    source: bytes,
    language: str,
) -> _PathObservation | None:
    if language == "python":
        path = _python_path(node, source)
        if path is not None:
            return _PathObservation(node=node, path=path)
        if node.type == "subscript":
            value = node.child_by_field_name("value")
            root = _python_path(value, source) if value is not None else None
            if root is not None:
                return _PathObservation(node=node, path=(root[0],), supported=False)
        return None
    if language in {"javascript", "typescript"}:
        path = _javascript_path(node, source)
        if path is not None:
            return _PathObservation(node=node, path=path)
        if node.type == "subscript_expression":
            value = node.child_by_field_name("object")
            root = _javascript_path(value, source) if value is not None else None
            if root is not None:
                return _PathObservation(node=node, path=(root[0],), supported=False)
        return None
    if language == "go":
        path = _go_path(node, source)
        return _PathObservation(node=node, path=path) if path is not None else None
    if node.type == "macro_invocation":
        macro = node.child_by_field_name("macro")
        path = _rust_path(macro, source)
        if path is not None:
            return _PathObservation(node=node, path=path, supported=False)
    path = _rust_path(node, source)
    return _PathObservation(node=node, path=path) if path is not None else None


def _node_key(node: Any) -> tuple[int, int, str]:
    return (node.start_byte, node.end_byte, node.type)


def _exclude(context: _SyntaxContext, node: Any | None) -> None:
    if node is not None:
        context.excluded_subtrees.add(_node_key(node))


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
    context: _SyntaxContext,
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
        _LocalBinding(
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


def _python_scope(node: Any) -> Any:
    return _scope_node(
        node,
        {"function_definition", "class_definition", "lambda"},
    )


def _collect_python_context(
    root: Any,
    source: bytes,
    context: _SyntaxContext,
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
                scope = _python_scope(node)
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
    context: _SyntaxContext,
    target: Any | None,
    source: bytes,
    *,
    declaration: Any,
    active_start: int,
) -> None:
    if target is None:
        return
    _exclude(context, target)
    scope = _python_scope(declaration)
    for identifier in _identifier_nodes(target):
        _add_local_binding(
            context,
            name_node=identifier,
            source=source,
            scope=scope,
            declaration_start_byte=declaration.start_byte,
            active_start_byte=active_start,
        )


_JAVASCRIPT_FUNCTION_NODES = {
    "function_declaration",
    "function_expression",
    "generator_function_declaration",
    "generator_function",
    "arrow_function",
    "method_definition",
}


def _javascript_lexical_scope(node: Any) -> Any:
    return _scope_node(node, {"statement_block", "class_static_block", "program"})


def _javascript_function_scope(node: Any) -> Any:
    return _scope_node(node, _JAVASCRIPT_FUNCTION_NODES | {"program"})


def _collect_javascript_context(
    root: Any,
    source: bytes,
    context: _SyntaxContext,
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
    context: _SyntaxContext,
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
    context: _SyntaxContext,
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
