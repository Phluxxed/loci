from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, TypeAlias, cast

from loci.parser._javascript_bindings import extract_javascript_import_bindings
from loci.parser.languages import get_language_spec
from loci.parser.reference_models import (
    MAX_IMPORT_BINDINGS_PER_DECLARATION,
    ImportBinding,
    ImportBindingKind,
    RawLocalExport,
    RawSymbolReference,
)
from loci.parser.references import extract_reference_batch


ImportUnresolvedReason: TypeAlias = Literal[
    "external",
    "not_indexed",
    "ambiguous",
    "unsupported_language",
    "invalid_specifier",
    "inaccessible",
    "unsupported_configuration",
]
RustObservationKind: TypeAlias = Literal["use", "module", "extern_crate"]
RustConfiguration: TypeAlias = Literal[
    "unconditional",
    "conditional",
    "unsupported",
]

MAX_RUST_USE_LEAVES_PER_DECLARATION = MAX_IMPORT_BINDINGS_PER_DECLARATION


@dataclass(frozen=True, slots=True)
class RustImportContext:
    kind: RustObservationKind
    lexical_module_path: tuple[str, ...]
    visibility: str
    module_level: bool
    configuration: RustConfiguration
    path_override: str | None = None
    lexical_module_visibilities: tuple[str, ...] = ()
    lexical_module_configurations: tuple[RustConfiguration, ...] = ()
    inline: bool = False


@dataclass(frozen=True, slots=True)
class RawImport:
    source_file: str
    language: str
    line: int
    text: str
    specifier: str
    imported_name: str | None
    type_only: bool
    is_reexport: bool
    source_hash: str
    bindings: tuple[ImportBinding, ...]
    rust: RustImportContext | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.bindings, tuple):
            raise ValueError("bindings must be an immutable tuple")
        if len(self.bindings) > MAX_IMPORT_BINDINGS_PER_DECLARATION:
            raise ValueError("bindings exceeds the per-declaration limit")
        for binding in self.bindings:
            if not isinstance(binding, ImportBinding):
                raise ValueError("bindings contains an invalid item")
            if (
                binding.import_line != self.line
                or binding.import_text != self.text
                or binding.import_specifier != self.specifier
            ):
                raise ValueError("binding locator does not match its raw import")


@dataclass(frozen=True, slots=True)
class GoPackageDeclaration:
    name: str
    line: int


@dataclass(frozen=True, slots=True)
class ImportExtractionBatch:
    imports: tuple[RawImport, ...]
    go_package: GoPackageDeclaration | None
    exports: tuple[RawLocalExport, ...]
    references: tuple[RawSymbolReference, ...]


class ImportExtractionError(RuntimeError):
    """Import observations could not be extracted reliably from a source file."""


def extract_imports(
    path: Path,
    *,
    source_file: str,
    language: str,
    source_hash: str,
) -> list[RawImport]:
    """Extract deterministic import observations without changing symbol parsing."""
    return list(
        extract_import_batch(
            path,
            source_file=source_file,
            language=language,
            source_hash=source_hash,
        ).imports
    )


def extract_import_batch(
    path: Path,
    *,
    source_file: str,
    language: str,
    source_hash: str,
) -> ImportExtractionBatch:
    """Extract import/dependency observations and language file metadata from one parse."""
    spec = get_language_spec(language)
    if spec is None or not spec.import_node_types:
        raise ImportExtractionError(f"unsupported language: {language}")

    try:
        source = path.read_bytes()
    except OSError as exc:
        raise ImportExtractionError(f"could not read {source_file}: {exc}") from exc

    try:
        from tree_sitter import Parser
        from tree_sitter_language_pack import get_language

        tree_sitter_language = (
            "tsx"
            if language == "typescript" and path.suffix.lower() == ".tsx"
            else spec.ts_language
        )
        tree = Parser(get_language(cast(Any, tree_sitter_language))).parse(source)
    except Exception as exc:
        raise ImportExtractionError(
            f"could not parse {source_file} for {language} imports"
        ) from exc

    if tree.root_node.has_error:
        raise ImportExtractionError(
            f"{source_file} could not be parsed for {language} imports"
        )

    imports: list[RawImport] = []
    go_packages: list[GoPackageDeclaration] = []
    for node in _walk_nodes(tree.root_node):
        if language == "go" and node.type == "package_clause":
            go_packages.append(_extract_go_package(node, source))
        if node.type not in spec.import_node_types:
            continue
        imports.extend(
            _extract_node_imports(
                node,
                source,
                source_file=source_file,
                language=language,
                source_hash=source_hash,
            )
        )
    if len(go_packages) > 1:
        raise ImportExtractionError(
            f"{source_file} has multiple Go package declarations"
        )
    try:
        reference_batch = extract_reference_batch(
            tree.root_node,
            source,
            source_file=source_file,
            language=language,
            source_hash=source_hash,
            imports=imports,
        )
    except ValueError as exc:
        raise ImportExtractionError(
            f"{source_file} reference extraction failed: {exc}"
        ) from exc
    return ImportExtractionBatch(
        imports=tuple(imports),
        go_package=go_packages[0] if go_packages else None,
        exports=reference_batch.exports,
        references=reference_batch.references,
    )


def _walk_nodes(node):
    yield node
    for child in node.children:
        yield from _walk_nodes(child)


def _extract_node_imports(
    node,
    source: bytes,
    *,
    source_file: str,
    language: str,
    source_hash: str,
) -> list[RawImport]:
    common = {
        "source_file": source_file,
        "language": language,
        "line": node.start_point[0] + 1,
        "text": _node_text(node, source),
        "source_hash": source_hash,
    }

    if language == "python":
        return _extract_python_imports(node, source, common)
    if language in {"javascript", "typescript"}:
        return _extract_javascript_import(node, source, common)
    if language == "go":
        return _extract_go_import(node, source, common)
    if language == "rust":
        return _extract_rust_import(node, source, common)
    raise ImportExtractionError(f"unsupported language: {language}")


def _extract_python_imports(node, source: bytes, common: dict) -> list[RawImport]:
    if node.type == "import_statement":
        import_names = _children_by_field_name(node, "name")
        _enforce_import_binding_limit(len(import_names))
        imports: list[RawImport] = []
        for child in import_names:
            specifier, alias = _python_import_parts(child, source)
            local_name = alias or specifier.split(".", 1)[0]
            imports.append(
                RawImport(
                    **common,
                    specifier=specifier,
                    imported_name=None,
                    type_only=False,
                    is_reexport=False,
                    bindings=(
                        _import_binding(
                            node,
                            common,
                            specifier=specifier,
                            local_name=local_name,
                            imported_name=None,
                            exported_name=None,
                            kind="module",
                            type_only=False,
                        ),
                    ),
                )
            )
        return imports

    module = node.child_by_field_name("module_name")
    specifier = _node_text(module, source) if module is not None else ""
    import_names = _children_by_field_name(node, "name")
    has_wildcard = any(
        child.type == "wildcard_import" for child in node.named_children
    )
    _enforce_import_binding_limit(len(import_names) + int(has_wildcard))
    imports = []
    for child in import_names:
        imported_name, alias = _python_import_parts(child, source)
        local_name = alias or imported_name
        imports.append(
            RawImport(
                **common,
                specifier=specifier,
                imported_name=imported_name,
                type_only=False,
                is_reexport=False,
                bindings=(
                    _import_binding(
                        node,
                        common,
                        specifier=specifier,
                        local_name=local_name,
                        imported_name=imported_name,
                        exported_name=None,
                        kind="symbol",
                        type_only=False,
                    ),
                ),
            )
        )
    if has_wildcard:
        imports.append(
            RawImport(
                **common,
                specifier=specifier,
                imported_name=None,
                type_only=False,
                is_reexport=False,
                bindings=(
                    _import_binding(
                        node,
                        common,
                        specifier=specifier,
                        local_name=None,
                        imported_name=None,
                        exported_name=None,
                        kind="glob",
                        type_only=False,
                    ),
                ),
            )
        )
    return imports


def _extract_javascript_import(node, source: bytes, common: dict) -> list[RawImport]:
    source_node = node.child_by_field_name("source")
    if source_node is None:
        return []
    specifier = _unquote(_node_text(source_node, source))
    bindings = extract_javascript_import_bindings(
        node,
        source,
        specifier=specifier,
        import_line=common["line"],
        import_text=common["text"],
    )
    _enforce_import_binding_limit(len(bindings))
    return [
        RawImport(
            **common,
            specifier=specifier,
            imported_name=None,
            type_only=_javascript_dependency_is_type_only(node),
            is_reexport=node.type == "export_statement",
            bindings=bindings,
        )
    ]


def _javascript_dependency_is_type_only(node) -> bool:
    if any(child.type == "type" for child in node.children):
        return True

    specifiers = [
        descendant
        for descendant in _walk_nodes(node)
        if descendant.type in {"import_specifier", "export_specifier"}
    ]
    return bool(specifiers) and all(
        any(child.type == "type" for child in specifier.children)
        for specifier in specifiers
    )


def _extract_go_import(node, source: bytes, common: dict) -> list[RawImport]:
    path = node.child_by_field_name("path")
    if path is None:
        return []
    specifier = _unquote(_node_text(path, source))
    name_node = node.child_by_field_name("name")
    explicit_name = _node_text(name_node, source) if name_node is not None else None
    if explicit_name == "_":
        local_name = None
        kind = "blank"
    elif explicit_name == ".":
        local_name = None
        kind = "glob"
    else:
        local_name = explicit_name
        kind = "namespace"
    return [
        RawImport(
            **common,
            specifier=specifier,
            imported_name=None,
            type_only=False,
            is_reexport=False,
            bindings=(
                _import_binding(
                    node,
                    common,
                    specifier=specifier,
                    local_name=local_name,
                    imported_name=None,
                    exported_name=None,
                    kind=kind,
                    type_only=False,
                    module_level=True,
                ),
            ),
        )
    ]


def _extract_go_package(node, source: bytes) -> GoPackageDeclaration:
    identifiers = [
        child for child in node.named_children if child.type == "package_identifier"
    ]
    if len(identifiers) != 1:
        raise ImportExtractionError("Go package clause has no package identifier")
    return GoPackageDeclaration(
        name=_node_text(identifiers[0], source),
        line=node.start_point[0] + 1,
    )


def _extract_rust_import(node, source: bytes, common: dict) -> list[RawImport]:
    if node.type == "extern_crate_declaration":
        return _extract_rust_extern_crate(node, source, common)
    if node.type == "mod_item":
        return _extract_rust_module(node, source, common)
    if node.type != "use_declaration":
        raise ImportExtractionError("unsupported Rust dependency declaration")

    argument = node.child_by_field_name("argument")
    if argument is None:
        raise ImportExtractionError("unsupported Rust use declaration")
    leaves: list[tuple[str, str | None, ImportBindingKind]] = []
    _expand_rust_use_tree(argument, source, prefix="", leaves=leaves)
    context = _rust_context(node, source, kind="use")
    return [
        RawImport(
            **common,
            specifier=specifier,
            imported_name=imported_name,
            type_only=False,
            is_reexport=context.visibility != "private",
            rust=context,
            bindings=(
                _import_binding(
                    node,
                    common,
                    specifier=specifier,
                    local_name=(
                        None if binding_kind in {"glob", "blank"} else imported_name
                    ),
                    imported_name=(
                        _rust_imported_name(specifier)
                        if binding_kind != "glob"
                        else None
                    ),
                    exported_name=(
                        imported_name
                        if context.visibility != "private"
                        and binding_kind not in {"glob", "blank"}
                        else None
                    ),
                    kind=binding_kind,
                    type_only=False,
                    module_level=context.module_level,
                ),
            ),
        )
        for specifier, imported_name, binding_kind in leaves
    ]


def _extract_rust_extern_crate(
    node,
    source: bytes,
    common: dict,
) -> list[RawImport]:
    name = node.child_by_field_name("name")
    alias = node.child_by_field_name("alias")
    if name is None:
        raise ImportExtractionError("unsupported Rust extern crate declaration")
    specifier = _node_text(name, source)
    imported_name = _node_text(alias, source) if alias is not None else specifier
    context = _rust_context(node, source, kind="extern_crate")
    return [
        RawImport(
            **common,
            specifier=specifier,
            imported_name=imported_name,
            type_only=False,
            is_reexport=context.visibility != "private",
            rust=context,
            bindings=(
                _import_binding(
                    node,
                    common,
                    specifier=specifier,
                    local_name=imported_name,
                    imported_name=None,
                    exported_name=(
                        imported_name if context.visibility != "private" else None
                    ),
                    kind="module",
                    type_only=False,
                    module_level=context.module_level,
                ),
            ),
        )
    ]


def _extract_rust_module(node, source: bytes, common: dict) -> list[RawImport]:
    inline = node.child_by_field_name("body") is not None
    name = node.child_by_field_name("name")
    if name is None:
        raise ImportExtractionError("unsupported Rust module declaration")
    specifier = _node_text(name, source)
    context = _rust_context(node, source, kind="module", inline=inline)
    return [
        RawImport(
            **common,
            specifier=specifier,
            imported_name=specifier,
            type_only=False,
            is_reexport=False,
            rust=context,
            bindings=(
                _import_binding(
                    node,
                    common,
                    specifier=specifier,
                    local_name=specifier,
                    imported_name=specifier,
                    exported_name=None,
                    kind="module",
                    type_only=False,
                    module_level=context.module_level,
                ),
            ),
        )
    ]


def _rust_context(
    node,
    source: bytes,
    *,
    kind: RustObservationKind,
    inline: bool = False,
) -> RustImportContext:
    visibility, visibility_supported = _rust_visibility(node, source)
    configuration, path_override = _rust_attributes(node, source, kind=kind)
    if not visibility_supported:
        configuration = "unsupported"
    (
        lexical_module_path,
        lexical_module_visibilities,
        lexical_module_configurations,
    ) = _rust_lexical_module_context(node, source)
    return RustImportContext(
        kind=kind,
        lexical_module_path=lexical_module_path,
        visibility=visibility,
        module_level=_rust_is_module_level(node),
        configuration=configuration,
        path_override=path_override,
        lexical_module_visibilities=lexical_module_visibilities,
        lexical_module_configurations=lexical_module_configurations,
        inline=inline,
    )


def _rust_visibility(node, source: bytes) -> tuple[str, bool]:
    modifier = next(
        (child for child in node.named_children if child.type == "visibility_modifier"),
        None,
    )
    if modifier is None:
        return "private", True
    compact = "".join(_node_text(modifier, source).split())
    if compact in {"pub", "pub(crate)", "pub(self)", "pub(super)"}:
        return compact, True
    if compact.startswith("pub(in") and compact.endswith(")"):
        path = compact[len("pub(in") : -1]
        if path and modifier.named_children:
            return f"pub(in {path})", True
    return "private", False


def _rust_attributes(
    node,
    source: bytes,
    *,
    kind: RustObservationKind,
) -> tuple[RustConfiguration, str | None]:
    configuration: RustConfiguration = "unconditional"
    path_values: list[str | None] = []
    for attribute in _rust_outer_attributes(node):
        body = next(
            (child for child in attribute.named_children if child.type == "attribute"),
            None,
        )
        if body is None or not body.named_children:
            continue
        name = _node_text(body.named_children[0], source)
        if name == "cfg" and configuration != "unsupported":
            configuration = "conditional"
        elif name == "cfg_attr" and _rust_cfg_attr_changes_resolution(body, source):
            configuration = "unsupported"
        elif name == "path" and kind == "module":
            path_values.append(_rust_path_attribute_value(body, source))

    path_override: str | None = None
    if path_values:
        if len(path_values) != 1 or path_values[0] is None:
            configuration = "unsupported"
        else:
            path_override = path_values[0]
    return configuration, path_override


def _rust_outer_attributes(node) -> list:
    attributes = []
    sibling = node.prev_named_sibling
    while sibling is not None:
        if sibling.type == "attribute_item":
            attributes.append(sibling)
        elif sibling.type not in {"block_comment", "line_comment"}:
            break
        sibling = sibling.prev_named_sibling
    attributes.reverse()
    return attributes


def _rust_cfg_attr_changes_resolution(attribute, source: bytes) -> bool:
    arguments = attribute.child_by_field_name("arguments")
    if arguments is None:
        return True
    return any(
        child.type == "identifier" and _node_text(child, source) in {"cfg", "path"}
        for child in _walk_nodes(arguments)
    )


def _rust_path_attribute_value(attribute, source: bytes) -> str | None:
    value = attribute.child_by_field_name("value")
    if value is None or value.type not in {"string_literal", "raw_string_literal"}:
        return None
    if any(child.type == "escape_sequence" for child in _walk_nodes(value)):
        return None
    contents = [
        _node_text(child, source)
        for child in value.named_children
        if child.type == "string_content"
    ]
    return "".join(contents)


def _rust_lexical_module_context(
    node,
    source: bytes,
) -> tuple[tuple[str, ...], tuple[str, ...], tuple[RustConfiguration, ...]]:
    modules = []
    ancestor = node.parent
    while ancestor is not None:
        if ancestor.type == "mod_item" and ancestor.child_by_field_name("body") is not None:
            name = ancestor.child_by_field_name("name")
            if name is not None:
                visibility, visibility_supported = _rust_visibility(ancestor, source)
                configuration, _ = _rust_attributes(
                    ancestor,
                    source,
                    kind="module",
                )
                if not visibility_supported:
                    configuration = "unsupported"
                modules.append(
                    (_node_text(name, source), visibility, configuration)
                )
        ancestor = ancestor.parent
    modules.reverse()
    return (
        tuple(name for name, _, _ in modules),
        tuple(visibility for _, visibility, _ in modules),
        tuple(configuration for _, _, configuration in modules),
    )


def _rust_is_module_level(node) -> bool:
    ancestor = node.parent
    while ancestor is not None:
        if ancestor.type == "source_file":
            return True
        if ancestor.type == "declaration_list":
            parent = ancestor.parent
            if (
                parent is None
                or parent.type != "mod_item"
                or parent.child_by_field_name("body") != ancestor
            ):
                return False
        elif ancestor.type != "mod_item" or ancestor.child_by_field_name("body") is None:
            return False
        ancestor = ancestor.parent
    return False


def _expand_rust_use_tree(
    node,
    source: bytes,
    *,
    prefix: str,
    leaves: list[tuple[str, str | None, ImportBindingKind]],
) -> None:
    if node.type == "use_list":
        for child in node.named_children:
            if child.type in {"block_comment", "line_comment"}:
                continue
            _expand_rust_use_tree(child, source, prefix=prefix, leaves=leaves)
        return

    if node.type == "scoped_use_list":
        path = node.child_by_field_name("path")
        use_list = node.child_by_field_name("list")
        if path is None or use_list is None:
            raise ImportExtractionError("unsupported Rust use declaration")
        _expand_rust_use_tree(
            use_list,
            source,
            prefix=_join_rust_path(prefix, _normalized_rust_path(path, source)),
            leaves=leaves,
        )
        return

    if node.type == "use_as_clause":
        path = node.child_by_field_name("path")
        alias = node.child_by_field_name("alias")
        if path is None or alias is None:
            raise ImportExtractionError("unsupported Rust use declaration")
        specifier = _join_rust_path(prefix, _normalized_rust_path(path, source))
        _append_rust_use_leaf(
            leaves,
            _collapse_trailing_rust_self(specifier),
            _node_text(alias, source),
            (
                "blank"
                if _node_text(alias, source) == "_"
                else "module"
                if _rust_path_is_definitely_module(specifier)
                else "symbol"
            ),
        )
        return

    if node.type == "use_wildcard":
        wildcard = _normalized_rust_path(node, source)
        _append_rust_use_leaf(
            leaves,
            _join_rust_path(prefix, wildcard),
            None,
            "glob",
        )
        return

    if node.type in {"identifier", "scoped_identifier", "crate", "self", "super"}:
        original_path = _join_rust_path(prefix, _normalized_rust_path(node, source))
        path = original_path
        path = _collapse_trailing_rust_self(path)
        _append_rust_use_leaf(
            leaves,
            path,
            _rust_imported_name(path),
            "module" if _rust_path_is_definitely_module(original_path) else "symbol",
        )
        return

    raise ImportExtractionError("unsupported Rust use declaration")


def _append_rust_use_leaf(
    leaves: list[tuple[str, str | None, ImportBindingKind]],
    specifier: str,
    imported_name: str | None,
    binding_kind: ImportBindingKind,
) -> None:
    if len(leaves) >= MAX_RUST_USE_LEAVES_PER_DECLARATION:
        raise ImportExtractionError("Rust use declaration exceeds leaf limit")
    leaves.append((specifier, imported_name, binding_kind))


def _join_rust_path(prefix: str, suffix: str) -> str:
    if not prefix or suffix.startswith("::"):
        return suffix
    if suffix == "self":
        return prefix
    return f"{prefix}::{suffix}"


def _normalized_rust_path(node, source: bytes) -> str:
    return "".join(_node_text(node, source).split())


def _collapse_trailing_rust_self(path: str) -> str:
    if path.endswith("::self"):
        return path[:-6]
    return path


def _rust_imported_name(path: str) -> str | None:
    if path.endswith("::*") or path == "*":
        return None
    return path.rsplit("::", 1)[-1]


def _rust_path_is_definitely_module(path: str) -> bool:
    return path.rsplit("::", 1)[-1] in {"crate", "self", "super"}


def _children_by_field_name(node, field_name: str) -> list:
    return [
        child
        for index, child in enumerate(node.children)
        if node.field_name_for_child(index) == field_name
    ]


def _enforce_import_binding_limit(count: int) -> None:
    if count > MAX_IMPORT_BINDINGS_PER_DECLARATION:
        raise ImportExtractionError("import declaration exceeds binding limit")


def _python_import_parts(node, source: bytes) -> tuple[str, str | None]:
    name = node.child_by_field_name("name")
    alias = node.child_by_field_name("alias")
    return (
        _node_text(name or node, source),
        _node_text(alias, source) if alias is not None else None,
    )


def _import_binding(
    node,
    common: dict,
    *,
    specifier: str,
    local_name: str | None,
    imported_name: str | None,
    exported_name: str | None,
    kind: ImportBindingKind,
    type_only: bool,
    module_level: bool | None = None,
) -> ImportBinding:
    effective_module_level = (
        _import_is_module_level(node, common["language"])
        if module_level is None
        else module_level
    )
    scope = _import_scope_node(
        node,
        common["language"],
        module_level=effective_module_level,
    )
    return ImportBinding(
        local_name=local_name,
        imported_name=imported_name,
        exported_name=exported_name,
        kind=kind,
        type_only=type_only,
        module_level=effective_module_level,
        declaration_start_byte=node.start_byte,
        scope_start_byte=scope.start_byte,
        scope_end_byte=scope.end_byte,
        import_line=common["line"],
        import_text=common["text"],
        import_specifier=specifier,
    )


def _import_is_module_level(node, language: str) -> bool:
    if language in {"javascript", "typescript", "go"}:
        return True
    ancestor = node.parent
    if language == "python":
        while ancestor is not None:
            if ancestor.type in {"class_definition", "function_definition", "lambda"}:
                return False
            ancestor = ancestor.parent
        return True
    if language == "rust":
        return _rust_is_module_level(node)
    return False


def _import_scope_node(node, language: str, *, module_level: bool):
    root = node
    while root.parent is not None:
        root = root.parent

    ancestor = node.parent
    if language == "python" and not module_level:
        while ancestor is not None:
            if ancestor.type in {"class_definition", "function_definition", "lambda"}:
                return ancestor
            ancestor = ancestor.parent
    elif language == "rust":
        target_type = "declaration_list" if module_level else "block"
        while ancestor is not None:
            if ancestor.type == target_type:
                return ancestor
            ancestor = ancestor.parent
    return root


def _node_text(node, source: bytes) -> str:
    return source[node.start_byte:node.end_byte].decode("utf-8", errors="replace")


def _unquote(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'", "`"}:
        return value[1:-1]
    return value
