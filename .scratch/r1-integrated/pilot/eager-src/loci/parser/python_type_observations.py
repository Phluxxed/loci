"""Authored Python annotation, explicit alias and direct-base observations.

No annotation is evaluated. Lexical bindings identify declarations; runtime
members, class MROs and computed type expressions are deliberately unproven.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
import hashlib
from pathlib import Path
from typing import Any, Sequence

from ._python_type_syntax import is_python_type_alias, name_path, text, walk
from .imports import ImportExtractionError, _extract_python_imports
from .reference_models import ImportBinding
from .symbols import Symbol
from .type_models import (
    MAX_TYPE_BINDINGS_PER_OBSERVATION, MAX_TYPE_OBSERVATIONS_PER_FILE,
    MAX_TYPE_PATH_SEGMENTS, LocalTypeBinding, RawTypeObservation, TypeDeclarationOwner,
)
from .type_observations import TypeExtractionError


_SCOPES = {"module", "function_definition", "class_definition", "lambda"}
_CONDITIONAL = {"if_statement", "for_statement", "while_statement", "try_statement",
                "with_statement", "match_statement", "case_clause"}
_BUILTINS = {"str", "bytes", "int", "float", "complex", "bool", "object", "type",
             "list", "dict", "tuple", "set", "frozenset", "None", "memoryview", "bytearray"}
_TYPING_MARKERS = {"Any", "TypeAlias", "Optional", "Union", "List", "Dict", "Set",
                   "Tuple", "FrozenSet", "Literal", "Annotated", "Callable", "ClassVar",
                   "Final", "Type", "Never", "NoReturn", "Self", "Sequence", "Mapping",
                   "Iterable", "Iterator", "Generator", "Collection", "MutableMapping"}


def _key(node: Any) -> tuple[int, int]:
    return node.start_byte, node.end_byte


def _contains(container: Any, node: Any) -> bool:
    return container.start_byte <= node.start_byte and node.end_byte <= container.end_byte


def _binding_scope(node: Any) -> Any:
    parent = node.parent
    while parent is not None and parent.type not in _SCOPES:
        parent = parent.parent
    return parent


def _conditional(node: Any, scope: Any) -> bool:
    parent = node.parent
    while parent is not None and parent != scope:
        if parent.type in _CONDITIONAL:
            return True
        parent = parent.parent
    return False


def _lookup_scopes(node: Any) -> tuple[Any, ...]:
    """Definition-time annotations exclude their own callable's body scope."""
    scopes = []
    callable_body = False
    parent = node.parent
    while parent is not None:
        if parent.type == "module":
            scopes.append(parent)
        elif parent.type in _SCOPES:
            body = parent.child_by_field_name("body")
            inside_body = body is not None and _contains(body, node)
            if inside_body and not (parent.type == "class_definition" and callable_body):
                scopes.append(parent)
            if parent.type in {"function_definition", "lambda"} and inside_body:
                callable_body = True
        parent = parent.parent
    return tuple(scopes)


@dataclass(frozen=True)
class _Local:
    value: LocalTypeBinding
    supported: bool


def extract_python_type_observations(
    path: Path, *, source_file: str, source_hash: str, symbols: Sequence[Symbol],
) -> tuple[RawTypeObservation, ...]:
    try:
        source = path.read_bytes()
    except OSError as exc:
        raise TypeExtractionError("TYPE_SOURCE_READ_FAILED", str(exc), "read_failed") from exc
    if hashlib.sha256(source).hexdigest() != source_hash:
        raise TypeExtractionError("TYPE_SOURCE_HASH_MISMATCH",
                                  f"{source_file} changed after symbol extraction", "source_hash_mismatch")
    try:
        source.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise TypeExtractionError("TYPE_SOURCE_ENCODING", f"{source_file} is not UTF-8", "unsupported_encoding") from exc
    try:
        from tree_sitter import Parser
        from tree_sitter_language_pack import get_language

        root = Parser(get_language("python")).parse(source).root_node
    except Exception as exc:
        raise TypeExtractionError("TYPE_PARSE_FAILED", str(exc), "parse_failed") from exc
    if root.has_error:
        raise TypeExtractionError("TYPE_PARSE_FAILED",
                                  f"{source_file} could not be parsed for Python types", "parse_error")

    nodes = tuple(walk(root))
    indexed = {(s.byte_offset, s.byte_offset + s.byte_length): s
               for s in symbols if s.file_path == source_file and s.kind != "file"}
    locals_by_scope: dict[tuple[int, int], dict[str, list[_Local]]] = defaultdict(lambda: defaultdict(list))
    imports_by_scope: dict[tuple[int, int], list[tuple[ImportBinding, bool]]] = defaultdict(list)
    parameters: dict[tuple[int, int], list[_Local]] = defaultdict(list)
    owners: list[tuple[Any, Symbol | None]] = []
    blocked_scopes: set[tuple[int, int]] = set()

    def symbol_for(node: Any) -> Symbol | None:
        decorated = node.parent if node.parent is not None and node.parent.type == "decorated_definition" else node
        return indexed.get(_key(decorated))

    def local(name: Any, declaration: Any, scope: Any, *, parameter: bool = False) -> _Local:
        symbol = symbol_for(declaration)
        kind = "type_parameter" if parameter else symbol.kind if symbol and symbol.kind in {"type", "class"} else "unindexed"
        start, end = ((symbol.byte_offset, symbol.byte_offset + symbol.byte_length)
                      if symbol else _key(declaration))
        return _Local(LocalTypeBinding(
            name=text(name, source), kind=kind, namespace="both" if kind == "class" else "type",
            declaration_start_byte=start, declaration_end_byte=end,
            scope_start_byte=scope.start_byte, scope_end_byte=scope.end_byte,
        ), supported=kind in {"type", "class", "type_parameter"} and not _conditional(declaration, scope))

    def record_targets(target: Any, declaration: Any, scope: Any) -> None:
        if target is None:
            return
        if target.type == "identifier":
            value = local(target, declaration, scope)
            locals_by_scope[_key(scope)][value.value.name].append(value)
        elif target.type in {"pattern_list", "tuple_pattern", "list_pattern", "list_splat_pattern",
                             "dictionary_splat_pattern", "as_pattern_target"}:
            for child in target.named_children:
                record_targets(child, declaration, scope)

    for node in nodes:
        scope = _binding_scope(node)
        if node.type in {"function_definition", "class_definition"}:
            owners.append((node, symbol_for(node)))
            record_targets(node.child_by_field_name("name"), node, scope)
            type_parameters = node.child_by_field_name("type_parameters")
            if type_parameters is not None:
                for child in type_parameters.named_children:
                    name = next((n for n in walk(child) if n.type == "identifier"), None)
                    if name is not None:
                        parameters[_key(node)].append(local(name, name, node, parameter=True))
            arguments = node.child_by_field_name("parameters")
            if arguments is not None:
                for argument in arguments.named_children:
                    name = argument.child_by_field_name("name") or argument.child_by_field_name("pattern")
                    if name is None:
                        name = argument if argument.type == "identifier" else next(
                            (n for n in argument.named_children if n.type == "identifier"), None)
                    record_targets(name, argument, node)
        elif node.type in {"assignment", "augmented_assignment", "named_expression"}:
            record_targets(node.child_by_field_name("left") or node.child_by_field_name("name"), node, scope)
            if node.type == "assignment" and symbol_for(node) is not None:
                owners.append((node, symbol_for(node)))
        elif node.type in {"for_statement", "for_in_clause"}:
            record_targets(node.child_by_field_name("left"), node, scope)
        elif node.type == "as_pattern":
            record_targets(node.child_by_field_name("alias"), node, scope)
        elif node.type in {"global_statement", "nonlocal_statement", "delete_statement", "case_clause"}:
            blocked_scopes.add(_key(scope))
        elif node.type in {"import_statement", "import_from_statement"}:
            common = dict(source_file=source_file, language="python", line=node.start_point.row + 1,
                          text=text(node, source), source_hash=source_hash)
            try:
                records = _extract_python_imports(node, source, common)
            except ImportExtractionError as exc:
                raise TypeExtractionError("TYPE_BINDING_LIMIT", str(exc), "binding_limit") from exc
            for record in records:
                for binding in record.bindings:
                    imports_by_scope[_key(scope)].append((binding, not _conditional(node, scope)))

    observations: list[RawTypeObservation] = []
    consumed: set[tuple[int, int, str]] = set()

    def add(node: Any, path_value: tuple[str, ...], *, context: str, relation: str = "uses_type",
            unsupported: str | None = None) -> None:
        key = (*_key(node), relation)
        if key in consumed:
            return
        consumed.add(key)
        if len(observations) >= MAX_TYPE_OBSERVATIONS_PER_FILE:
            raise TypeExtractionError("TYPE_OBSERVATION_LIMIT", f"{source_file} exceeds the type-site limit", "site_limit")
        if len(path_value) > MAX_TYPE_PATH_SEGMENTS:
            path_value, unsupported = (), "path_too_deep"
        local_values: list[_Local] = []
        import_values: list[tuple[ImportBinding, bool]] = []
        name = path_value[0] if path_value else ""
        # PEP 695 binders apply to the declaration's annotations and body.
        ancestor = node.parent
        while ancestor is not None:
            local_values = [v for v in parameters.get(_key(ancestor), ()) if v.value.name == name]
            if local_values:
                break
            ancestor = ancestor.parent
        if not local_values:
            for scope in _lookup_scopes(node):
                if _key(scope) in blocked_scopes:
                    unsupported = unsupported or "unsupported_scope_rebinding"
                local_values = locals_by_scope[_key(scope)].get(name, [])
                import_values = [(b, supported) for b, supported in imports_by_scope[_key(scope)]
                                 if b.local_name == name or b.kind == "glob"]
                if local_values or import_values:
                    break
        if not unsupported and not local_values and not import_values and len(path_value) == 1 and name in _BUILTINS:
            return
        if not unsupported and not local_values and len(import_values) == 1:
            binding, supported = import_values[0]
            marker = (binding.imported_name if len(path_value) == 1 and binding.kind == "symbol"
                      else path_value[1] if len(path_value) == 2 and binding.kind == "module" else None)
            if supported and binding.import_specifier in {"typing", "typing_extensions"} and marker in _TYPING_MARKERS:
                return
        total = len(local_values) + len(import_values)
        truncated = max(0, total - MAX_TYPE_BINDINGS_PER_OBSERVATION)
        local_values = local_values[:MAX_TYPE_BINDINGS_PER_OBSERVATION]
        import_values = import_values[:MAX_TYPE_BINDINGS_PER_OBSERVATION - len(local_values)]
        if any(not item.supported for item in local_values):
            unsupported = unsupported or "value_or_conditional_binding"
        if any(not supported or binding.kind == "glob" for binding, supported in import_values):
            unsupported = unsupported or "conditional_or_wildcard_import"
        if unsupported:
            state = "unsupported"
        elif total > 1:
            state = "ambiguous"
        elif local_values:
            state = "shadowed" if local_values[0].value.kind == "type_parameter" else "local"
        elif import_values:
            state = "imported"
        else:
            state = "unbound"
        candidates = [(owner, symbol) for owner, symbol in owners if _contains(owner, node)]
        owner_node, owner_symbol = min(candidates, key=lambda item: item[0].end_byte - item[0].start_byte) if candidates else (node, None)
        owner = TypeDeclarationOwner(
            kind=owner_symbol.kind if owner_symbol else "unindexed",
            start_byte=owner_symbol.byte_offset if owner_symbol else owner_node.start_byte,
            end_byte=owner_symbol.byte_offset + owner_symbol.byte_length if owner_symbol else owner_node.end_byte,
        )
        observations.append(RawTypeObservation(
            source_file=source_file, language="python", source_hash=source_hash,
            line=node.start_point.row + 1, column=node.start_point.column + 1,
            start_byte=node.start_byte, end_byte=node.end_byte, text=text(node, source), path=path_value,
            relation=relation, context=context, lookup_space="type", owner=owner,
            local_bindings=tuple(item.value for item in local_values),
            import_bindings=tuple(binding for binding, _ in import_values), binding_state=state,
            candidates_complete=not truncated, candidates_truncated=truncated, unsupported_reason=unsupported,
        ))

    def expression(node: Any, context: str, *, relation: str = "uses_type") -> None:
        path_value = name_path(node, source)
        if path_value:
            # Unwrap type grammar nodes to retain the name's exact site.
            while node.type == "type":
                node = node.named_children[0]
            add(node, path_value, context=context, relation=relation)
        elif node.type == "type" and len(node.named_children) == 1:
            expression(node.named_children[0], context, relation=relation)
        elif node.type == "string" and relation == "uses_type":
            value = text(node, source)
            if (len(value) >= 3 and value[0] in {"'", '"'} and value[-1] == value[0]
                    and all(part.isidentifier() for part in value[1:-1].split("."))):
                add(node, tuple(value[1:-1].split(".")), context=context)
            else:
                add(node, (), context=context, unsupported="unsupported_forward_expression")
        elif node.type in {"generic_type", "subscript"}:
            head = node.child_by_field_name("value") or node.named_children[0]
            head_path = name_path(head, source)
            if head_path and head_path[-1] in {"Literal", "Annotated"}:
                # Their arguments include values/metadata. Treating a quoted
                # Literal value as a forward type name would invent an edge.
                add(node, (), context=context, relation=relation,
                    unsupported="unsupported_value_type_arguments")
                return
            expression(head, context, relation=relation)
            for child in node.named_children:
                if child == head:
                    continue
                if child.type == "type_parameter":
                    for argument in child.named_children:
                        expression(argument, "type_argument")
                else:
                    expression(child, "type_argument")
        elif node.type in {"binary_operator", "union_type"} and relation == "uses_type" and any(
            child.type == "|" for child in node.children
        ):
            for child in node.named_children:
                expression(child, context)
        elif node.type in {"list", "tuple"} and relation == "uses_type":
            for child in node.named_children:
                expression(child, "type_argument")
        elif node.type in {"none", "ellipsis"}:
            return
        else:
            add(node, (), context=context, relation=relation, unsupported=f"unsupported_{node.type}")

    for node in nodes:
        if node.type in {"typed_parameter", "typed_default_parameter", "assignment"}:
            annotation = node.child_by_field_name("type")
            if annotation is not None:
                if is_python_type_alias(node, source):
                    expression(node.child_by_field_name("right"), "alias")
                else:
                    expression(annotation, "property" if node.type == "assignment" else "annotation")
        elif node.type == "function_definition":
            annotation = node.child_by_field_name("return_type")
            if annotation is not None:
                expression(annotation, "return")
        elif node.type == "class_definition":
            bases = node.child_by_field_name("superclasses")
            if bases is not None:
                for base in bases.named_children:
                    if base.type == "keyword_argument":
                        add(base, (), context="heritage", relation="extends",
                            unsupported="unsupported_metaclass_or_class_keyword")
                    else:
                        expression(base, "heritage", relation="extends")
    return tuple(observations)
