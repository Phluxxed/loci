from __future__ import annotations

from loci.parser.reference_models import ImportBinding


def extract_javascript_import_bindings(
    node,
    source: bytes,
    *,
    specifier: str,
    import_line: int,
    import_text: str,
) -> tuple[ImportBinding, ...]:
    declaration_type_only = any(child.type == "type" for child in node.children)
    root = node
    while root.parent is not None:
        root = root.parent
    bindings: list[ImportBinding] = []

    def add(
        *,
        local_name: str | None,
        imported_name: str | None,
        exported_name: str | None,
        kind: str,
        type_only: bool,
    ) -> None:
        bindings.append(
            ImportBinding(
                local_name=local_name,
                imported_name=imported_name,
                exported_name=exported_name,
                kind=kind,
                type_only=type_only,
                module_level=True,
                declaration_start_byte=node.start_byte,
                scope_start_byte=root.start_byte,
                scope_end_byte=root.end_byte,
                import_line=import_line,
                import_text=import_text,
                import_specifier=specifier,
            )
        )

    if node.type == "import_statement":
        clause = _first_named_child(node, "import_clause")
        if clause is None:
            add(
                local_name=None,
                imported_name=None,
                exported_name=None,
                kind="side_effect",
                type_only=False,
            )
            return tuple(bindings)

        for child in clause.named_children:
            if child.type == "identifier":
                add(
                    local_name=_node_text(child, source),
                    imported_name="default",
                    exported_name=None,
                    kind="symbol",
                    type_only=declaration_type_only,
                )
            elif child.type == "namespace_import":
                local = _first_named_child(child, "identifier")
                if local is not None:
                    add(
                        local_name=_node_text(local, source),
                        imported_name=None,
                        exported_name=None,
                        kind="namespace",
                        type_only=declaration_type_only,
                    )
            elif child.type == "named_imports":
                for import_specifier in child.named_children:
                    if import_specifier.type != "import_specifier":
                        continue
                    name = import_specifier.child_by_field_name("name")
                    alias = import_specifier.child_by_field_name("alias")
                    if name is None:
                        continue
                    imported_name = _node_text(name, source)
                    add(
                        local_name=(
                            _node_text(alias, source)
                            if alias is not None
                            else imported_name
                        ),
                        imported_name=imported_name,
                        exported_name=None,
                        kind="symbol",
                        type_only=(
                            declaration_type_only or _specifier_is_type_only(import_specifier)
                        ),
                    )
        return tuple(bindings)

    export_clause = _first_named_child(node, "export_clause")
    namespace_export = _first_named_child(node, "namespace_export")
    if export_clause is not None:
        for export_specifier in export_clause.named_children:
            if export_specifier.type != "export_specifier":
                continue
            name = export_specifier.child_by_field_name("name")
            alias = export_specifier.child_by_field_name("alias")
            if name is None:
                continue
            imported_name = _node_text(name, source)
            add(
                local_name=None,
                imported_name=imported_name,
                exported_name=(
                    _node_text(alias, source) if alias is not None else imported_name
                ),
                kind="symbol",
                type_only=(
                    declaration_type_only or _specifier_is_type_only(export_specifier)
                ),
            )
    elif namespace_export is not None:
        exported = _first_named_child(namespace_export, "identifier")
        if exported is not None:
            add(
                local_name=None,
                imported_name=None,
                exported_name=_node_text(exported, source),
                kind="namespace",
                type_only=declaration_type_only,
            )
    elif any(child.type == "*" for child in node.children):
        add(
            local_name=None,
            imported_name=None,
            exported_name=None,
            kind="glob",
            type_only=declaration_type_only,
        )
    return tuple(bindings)


def _first_named_child(node, node_type: str):
    return next(
        (child for child in node.named_children if child.type == node_type),
        None,
    )


def _specifier_is_type_only(node) -> bool:
    return any(child.type == "type" for child in node.children)


def _node_text(node, source: bytes) -> str:
    return source[node.start_byte:node.end_byte].decode("utf-8", errors="replace")
