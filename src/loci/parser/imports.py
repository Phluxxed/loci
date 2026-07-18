from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal, TypeAlias

from loci.parser.languages import get_language_spec


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

MAX_RUST_USE_LEAVES_PER_DECLARATION = 1_024


@dataclass(frozen=True, slots=True)
class RustImportContext:
    kind: RustObservationKind
    lexical_module_path: tuple[str, ...]
    visibility: str
    module_level: bool
    configuration: RustConfiguration
    path_override: str | None = None


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
    rust: RustImportContext | None = None


@dataclass(frozen=True, slots=True)
class GoPackageDeclaration:
    name: str
    line: int


@dataclass(frozen=True, slots=True)
class ImportExtractionBatch:
    imports: tuple[RawImport, ...]
    go_package: GoPackageDeclaration | None


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
    """Extract dependency observations and language metadata from one parse."""
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

        tree = Parser(get_language(spec.ts_language)).parse(source)
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
    return ImportExtractionBatch(
        imports=tuple(imports),
        go_package=go_packages[0] if go_packages else None,
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
        return [
            RawImport(
                **common,
                specifier=_python_import_name(child, source),
                imported_name=None,
                type_only=False,
                is_reexport=False,
            )
            for child in _children_by_field_name(node, "name")
        ]

    module = node.child_by_field_name("module_name")
    specifier = _node_text(module, source) if module is not None else ""
    imported_names = [
        _python_import_name(child, source)
        for child in _children_by_field_name(node, "name")
    ]
    if any(child.type == "wildcard_import" for child in node.named_children):
        imported_names.append(None)

    return [
        RawImport(
            **common,
            specifier=specifier,
            imported_name=imported_name,
            type_only=False,
            is_reexport=False,
        )
        for imported_name in imported_names
    ]


def _extract_javascript_import(node, source: bytes, common: dict) -> list[RawImport]:
    source_node = node.child_by_field_name("source")
    if source_node is None:
        return []
    return [
        RawImport(
            **common,
            specifier=_unquote(_node_text(source_node, source)),
            imported_name=None,
            type_only=_javascript_dependency_is_type_only(node),
            is_reexport=node.type == "export_statement",
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
    return [
        RawImport(
            **common,
            specifier=_unquote(_node_text(path, source)),
            imported_name=None,
            type_only=False,
            is_reexport=False,
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
    if node.type != "use_declaration":
        return []
    argument = node.child_by_field_name("argument")
    if argument is None:
        return []
    leaves: list[tuple[str, str | None]] = []
    _expand_rust_use_tree(argument, source, prefix="", leaves=leaves)
    context = RustImportContext(
        kind="use",
        lexical_module_path=(),
        visibility="private",
        module_level=True,
        configuration="unconditional",
    )
    return [
        RawImport(
            **common,
            specifier=specifier,
            imported_name=imported_name,
            type_only=False,
            is_reexport=False,
            rust=context,
        )
        for specifier, imported_name in leaves
    ]


def _expand_rust_use_tree(
    node,
    source: bytes,
    *,
    prefix: str,
    leaves: list[tuple[str, str | None]],
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
        _append_rust_use_leaf(
            leaves,
            _join_rust_path(prefix, _normalized_rust_path(path, source)),
            _node_text(alias, source),
        )
        return

    if node.type == "use_wildcard":
        wildcard = _normalized_rust_path(node, source)
        _append_rust_use_leaf(leaves, _join_rust_path(prefix, wildcard), None)
        return

    if node.type in {"identifier", "scoped_identifier", "crate", "self", "super"}:
        path = _join_rust_path(prefix, _normalized_rust_path(node, source))
        path = _collapse_trailing_rust_self(path)
        _append_rust_use_leaf(leaves, path, _rust_imported_name(path))
        return

    raise ImportExtractionError("unsupported Rust use declaration")


def _append_rust_use_leaf(
    leaves: list[tuple[str, str | None]],
    specifier: str,
    imported_name: str | None,
) -> None:
    if len(leaves) >= MAX_RUST_USE_LEAVES_PER_DECLARATION:
        raise ImportExtractionError("Rust use declaration exceeds leaf limit")
    leaves.append((specifier, imported_name))


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


def _children_by_field_name(node, field_name: str) -> list:
    return [
        child
        for index, child in enumerate(node.children)
        if node.field_name_for_child(index) == field_name
    ]


def _python_import_name(node, source: bytes) -> str:
    name = node.child_by_field_name("name")
    return _node_text(name or node, source)


def _node_text(node, source: bytes) -> str:
    return source[node.start_byte:node.end_byte].decode("utf-8", errors="replace")


def _unquote(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'", "`"}:
        return value[1:-1]
    return value
