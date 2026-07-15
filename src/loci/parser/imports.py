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
]


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
    for node in _walk_nodes(tree.root_node):
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
    return imports


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


def _extract_rust_import(node, source: bytes, common: dict) -> list[RawImport]:
    argument = node.child_by_field_name("argument")
    if argument is None:
        return []
    return [
        RawImport(
            **common,
            specifier=_node_text(argument, source),
            imported_name=None,
            type_only=False,
            is_reexport=False,
        )
    ]


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
