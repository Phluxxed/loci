from __future__ import annotations

import unicodedata
from typing import Any, Sequence

from loci.parser.reference_models import (
    MAX_LOCAL_EXPORTS_PER_FILE,
    RawLocalExport,
)


_IDENTIFIER_TYPES = {
    "identifier",
    "type_identifier",
    "package_identifier",
}

_RUST_ITEM_TYPES = {
    "function_item",
    "struct_item",
    "enum_item",
    "trait_item",
    "const_item",
    "static_item",
    "type_item",
}


def _node_text(node: Any, source: bytes) -> str:
    return source[node.start_byte : node.end_byte].decode("utf-8", errors="replace")


def _walk_nodes(node: Any):
    yield node
    for child in node.named_children:
        yield from _walk_nodes(child)


def _field_children(node: Any, field_name: str) -> list[Any]:
    return [
        child
        for index, child in enumerate(node.children)
        if child.is_named and node.field_name_for_child(index) == field_name
    ]


def _has_token(node: Any, token_type: str) -> bool:
    return any(child.type == token_type for child in node.children)


def _extract_local_exports(
    root: Any,
    source: bytes,
    *,
    source_file: str,
    language: str,
    source_hash: str,
    imports: Sequence[Any],
) -> list[RawLocalExport]:
    exports: list[RawLocalExport] = []
    if language == "python":
        _extract_python_exports(
            root,
            source,
            exports,
            source_file=source_file,
            source_hash=source_hash,
            imports=imports,
        )
    elif language in {"javascript", "typescript"}:
        _extract_javascript_exports(
            root,
            source,
            exports,
            source_file=source_file,
            language=language,
            source_hash=source_hash,
        )
    elif language == "go":
        _extract_go_exports(
            root,
            source,
            exports,
            source_file=source_file,
            source_hash=source_hash,
        )
    else:
        _extract_rust_exports(
            root,
            source,
            exports,
            source_file=source_file,
            source_hash=source_hash,
        )
    return exports


def _append_export(
    exports: list[RawLocalExport],
    *,
    evidence_node: Any,
    source: bytes,
    source_file: str,
    language: str,
    source_hash: str,
    local_name: str | None,
    exported_name: str,
    type_only: bool,
    definition_node: Any | None,
) -> None:
    if len(exports) >= MAX_LOCAL_EXPORTS_PER_FILE:
        raise ValueError("exports exceeds the per-file limit")
    exports.append(
        RawLocalExport(
            source_file=source_file,
            language=language,
            line=evidence_node.start_point[0] + 1,
            text=_node_text(evidence_node, source),
            local_name=local_name,
            exported_name=exported_name,
            type_only=type_only,
            definition_start_byte=(
                definition_node.start_byte if definition_node is not None else None
            ),
            definition_end_byte=(
                definition_node.end_byte if definition_node is not None else None
            ),
            source_hash=source_hash,
        )
    )


def _extract_python_exports(
    root: Any,
    source: bytes,
    exports: list[RawLocalExport],
    *,
    source_file: str,
    source_hash: str,
    imports: Sequence[Any],
) -> None:
    import_bindings_by_start: dict[int, list[Any]] = {}
    for raw_import in imports:
        for binding in raw_import.bindings:
            if (
                binding.module_level
                and binding.kind == "symbol"
                and binding.local_name is not None
            ):
                import_bindings_by_start.setdefault(
                    binding.declaration_start_byte,
                    [],
                ).append(binding)

    for child in root.named_children:
        for binding in import_bindings_by_start.get(child.start_byte, ()):
            if len(exports) >= MAX_LOCAL_EXPORTS_PER_FILE:
                raise ValueError("exports exceeds the per-file limit")
            exports.append(
                RawLocalExport(
                    source_file=source_file,
                    language="python",
                    line=binding.import_line,
                    text=binding.import_text,
                    local_name=binding.local_name,
                    exported_name=binding.local_name,
                    type_only=binding.type_only,
                    definition_start_byte=None,
                    definition_end_byte=None,
                    source_hash=source_hash,
                )
            )
        declaration = child
        if child.type == "decorated_definition":
            declaration = next(
                (
                    nested
                    for nested in child.named_children
                    if nested.type in {"function_definition", "class_definition"}
                ),
                child,
            )
        if declaration.type in {"function_definition", "class_definition"}:
            name = declaration.child_by_field_name("name")
            if name is not None:
                value = _node_text(name, source)
                _append_export(
                    exports,
                    evidence_node=child,
                    source=source,
                    source_file=source_file,
                    language="python",
                    source_hash=source_hash,
                    local_name=value,
                    exported_name=value,
                    type_only=False,
                    definition_node=child,
                )
        elif declaration.type == "assignment":
            target = declaration.child_by_field_name("left")
            if target is not None and target.type == "identifier":
                value = _node_text(target, source)
                if _python_constant_name(value):
                    _append_export(
                        exports,
                        evidence_node=child,
                        source=source,
                        source_file=source_file,
                        language="python",
                        source_hash=source_hash,
                        local_name=value,
                        exported_name=value,
                        type_only=False,
                        definition_node=declaration,
                    )


def _python_constant_name(name: str) -> bool:
    return bool(name) and name[0] in "ABCDEFGHIJKLMNOPQRSTUVWXYZ" and all(
        character in "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_" for character in name
    )


def _javascript_definition_nodes(root: Any, source: bytes) -> dict[str, list[Any]]:
    definitions: dict[str, list[Any]] = {}
    for child in root.named_children:
        declaration = (
            child.child_by_field_name("declaration")
            if child.type == "export_statement"
            else child
        )
        if declaration is None:
            continue
        for name, definition in _javascript_declared_names(declaration, source):
            definitions.setdefault(name, []).append(definition)
    return definitions


def _javascript_declared_names(
    declaration: Any,
    source: bytes,
) -> list[tuple[str, Any]]:
    if declaration.type in {
        "function_declaration",
        "generator_function_declaration",
        "class_declaration",
        "type_alias_declaration",
        "interface_declaration",
        "enum_declaration",
    }:
        name = declaration.child_by_field_name("name")
        return [(_node_text(name, source), declaration)] if name is not None else []
    if declaration.type in {"lexical_declaration", "variable_declaration"}:
        names: list[tuple[str, Any]] = []
        for child in declaration.named_children:
            if child.type != "variable_declarator":
                continue
            name = child.child_by_field_name("name")
            if name is not None and name.type in _IDENTIFIER_TYPES:
                names.append((_node_text(name, source), child))
        return names
    return []


def _extract_javascript_exports(
    root: Any,
    source: bytes,
    exports: list[RawLocalExport],
    *,
    source_file: str,
    language: str,
    source_hash: str,
) -> None:
    definitions = _javascript_definition_nodes(root, source)
    for node in root.named_children:
        if node.type != "export_statement":
            continue
        declaration = node.child_by_field_name("declaration")
        if declaration is not None:
            declared = _javascript_declared_names(declaration, source)
            is_default = _has_token(node, "default")
            for local_name, definition in declared:
                _append_export(
                    exports,
                    evidence_node=node,
                    source=source,
                    source_file=source_file,
                    language=language,
                    source_hash=source_hash,
                    local_name=local_name,
                    exported_name="default" if is_default else local_name,
                    type_only=declaration.type in {
                        "type_alias_declaration",
                        "interface_declaration",
                    },
                    definition_node=definition,
                )
            continue
        if node.child_by_field_name("source") is not None:
            continue
        clause = next(
            (child for child in node.named_children if child.type == "export_clause"),
            None,
        )
        if clause is None:
            continue
        declaration_type_only = _has_token(node, "type")
        for specifier in clause.named_children:
            if specifier.type != "export_specifier":
                continue
            name = specifier.child_by_field_name("name")
            alias = specifier.child_by_field_name("alias")
            if name is None:
                continue
            local_name = _node_text(name, source)
            exported_name = _node_text(alias, source) if alias is not None else local_name
            candidates = definitions.get(local_name, [])
            _append_export(
                exports,
                evidence_node=node,
                source=source,
                source_file=source_file,
                language=language,
                source_hash=source_hash,
                local_name=local_name,
                exported_name=exported_name,
                type_only=declaration_type_only or _has_token(specifier, "type"),
                definition_node=candidates[0] if len(candidates) == 1 else None,
            )


def _go_package_level(node: Any) -> bool:
    parent = node.parent
    while parent is not None and parent.type != "source_file":
        if parent.type in {
            "block",
            "function_declaration",
            "method_declaration",
            "func_literal",
        }:
            return False
        parent = parent.parent
    return parent is not None


def _go_exported_name(name: str) -> bool:
    return bool(name) and unicodedata.category(name[0]) == "Lu"


def _extract_go_exports(
    root: Any,
    source: bytes,
    exports: list[RawLocalExport],
    *,
    source_file: str,
    source_hash: str,
) -> None:
    for node in _walk_nodes(root):
        if node.type not in {"function_declaration", "type_spec", "const_spec"}:
            continue
        if not _go_package_level(node):
            continue
        names = _field_children(node, "name")
        if not names:
            name = node.child_by_field_name("name")
            names = [name] if name is not None else []
        for name in names:
            value = _node_text(name, source)
            if not _go_exported_name(value):
                continue
            _append_export(
                exports,
                evidence_node=node,
                source=source,
                source_file=source_file,
                language="go",
                source_hash=source_hash,
                local_name=value,
                exported_name=value,
                type_only=False,
                definition_node=node,
            )


def _rust_module_item(node: Any) -> bool:
    parent = node.parent
    while parent is not None and parent.type != "source_file":
        if parent.type in {"block", "impl_item", "trait_item", "foreign_mod_item"}:
            return False
        parent = parent.parent
    return parent is not None


def _extract_rust_exports(
    root: Any,
    source: bytes,
    exports: list[RawLocalExport],
    *,
    source_file: str,
    source_hash: str,
) -> None:
    for node in _walk_nodes(root):
        if node.type not in _RUST_ITEM_TYPES or not _rust_module_item(node):
            continue
        name = node.child_by_field_name("name")
        if name is None:
            continue
        value = _node_text(name, source)
        _append_export(
            exports,
            evidence_node=node,
            source=source,
            source_file=source_file,
            language="rust",
            source_hash=source_hash,
            local_name=value,
            exported_name=value,
            type_only=False,
            definition_node=node,
        )
