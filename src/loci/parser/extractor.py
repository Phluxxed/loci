from __future__ import annotations
from pathlib import Path
from typing import Optional
import hashlib
import re

from .symbols import Symbol, make_symbol_id
from .languages import get_language_spec, EXTENSION_MAP, LanguageSpec


def parse_file(path: Path) -> list[Symbol]:
    """Parse a source file and return all symbols with byte offsets."""
    suffix = path.suffix.lower()
    language = EXTENSION_MAP.get(suffix)
    if language is None:
        return []

    spec = get_language_spec(language)
    if spec is None:
        return []

    try:
        source_bytes = path.read_bytes()
    except (OSError, PermissionError):
        return []

    try:
        from tree_sitter_language_pack import get_parser
        parser = get_parser(spec.ts_language)
        tree = parser.parse(source_bytes)
    except Exception:
        return []

    rel_path = str(path)
    symbols: list[Symbol] = []
    _walk(tree.root_node, source_bytes, spec, language, rel_path, symbols, parent_name=None)
    _disambiguate(symbols)
    return symbols


def _walk(
    node,
    source: bytes,
    spec: LanguageSpec,
    language: str,
    file_path: str,
    out: list[Symbol],
    parent_name: Optional[str],
) -> None:
    node_type = node.type

    # Handle decorated_definition in Python — unwrap to inner definition
    if node_type == "decorated_definition":
        for child in node.children:
            if child.type in spec.symbol_node_types and child.type != "decorated_definition":
                _extract_symbol(child, source, spec, language, file_path, out, parent_name, node)
                _recurse_body(child, source, spec, language, file_path, out)
        return

    if node_type in spec.symbol_node_types:
        _extract_symbol(node, source, spec, language, file_path, out, parent_name, None)
        _recurse_body(node, source, spec, language, file_path, out)
        return

    for child in node.children:
        _walk(child, source, spec, language, file_path, out, parent_name)


def _recurse_body(
    node,
    source: bytes,
    spec: LanguageSpec,
    language: str,
    file_path: str,
    out: list[Symbol],
) -> None:
    """Recurse into a container node (class body) to find methods."""
    node_type = node.type
    if node_type not in spec.container_node_types:
        return

    name = _extract_name(node, spec, source)
    if not name:
        return

    # For TypeScript, the body is in the "body" field (class_body node);
    # we need to walk the body's children with this class as parent.
    body = node.child_by_field_name("body")
    if body is not None:
        for child in body.children:
            _walk(child, source, spec, language, file_path, out, parent_name=name)
    else:
        # Python class_definition: body is directly the block child
        for child in node.children:
            _walk(child, source, spec, language, file_path, out, parent_name=name)


def _extract_symbol(
    node,
    source: bytes,
    spec: LanguageSpec,
    language: str,
    file_path: str,
    out: list[Symbol],
    parent_name: Optional[str],
    decorator_node,
) -> None:
    name = _extract_name(node, spec, source)
    if not name:
        return

    kind = spec.symbol_node_types.get(node.type, "function")
    # Functions inside a class container become methods
    if parent_name and kind == "function":
        kind = "method"

    # For constants, apply the name pattern filter if the spec defines one
    if kind == "constant" and spec.constant_name_pattern:
        if not re.fullmatch(spec.constant_name_pattern, name):
            return

    qualified_name = f"{parent_name}.{name}" if parent_name else name

    # Use decorator node start offset if present (covers entire decorated definition)
    start = decorator_node.start_byte if decorator_node else node.start_byte
    end = node.end_byte
    byte_offset = start
    byte_length = end - start

    signature = _extract_signature(node, source)
    docstring = _extract_docstring(node, spec, source)
    content_hash = hashlib.sha256(source[byte_offset:byte_offset + byte_length]).hexdigest()

    # Decorators: for Python use the decorated_definition node; for TS/JS use node itself
    decorators: list[str] = []
    if spec.decorator_child_type:
        dec_source = decorator_node if decorator_node else node
        decorators = _extract_decorators(dec_source, source, spec.decorator_child_type)

    sym_id = make_symbol_id(file_path, qualified_name, kind)

    out.append(Symbol(
        id=sym_id,
        name=name,
        qualified_name=qualified_name,
        kind=kind,
        language=language,
        file_path=file_path,
        byte_offset=byte_offset,
        byte_length=byte_length,
        signature=signature,
        docstring=docstring,
        content_hash=content_hash,
        decorators=decorators,
    ))


def _extract_name(node, spec: LanguageSpec, source: bytes) -> Optional[str]:
    for field_name in spec.name_fields:
        child = node.child_by_field_name(field_name)
        if child:
            return source[child.start_byte:child.end_byte].decode("utf-8", errors="replace")
    return None


def _extract_signature(node, source: bytes) -> str:
    """Extract the first line of the symbol as its signature."""
    text = source[node.start_byte:node.end_byte].decode("utf-8", errors="replace")
    first_line = text.split("\n")[0].rstrip(":")
    return first_line.strip()


def _extract_docstring(node, spec: LanguageSpec, source: bytes) -> str:
    if spec.docstring_strategy == "next_sibling_string":
        return _python_docstring(node, source)
    elif spec.docstring_strategy == "preceding_comment":
        return _preceding_comment(node, source)
    return ""


def _python_docstring(node, source: bytes) -> str:
    """Extract Python docstring from function/class body."""
    body = node.child_by_field_name("body")
    if not body:
        return ""
    # In Python AST, the first child of 'block' is a bare 'string' node
    # (not wrapped in expression_statement) when it's a docstring.
    for child in body.children:
        if child.type == "string":
            # Extract the string content node if present, otherwise raw text
            content_node = child.child_by_field_name("content")
            if content_node is None:
                # Try to find string_content child
                for sub in child.children:
                    if sub.type == "string_content":
                        return source[sub.start_byte:sub.end_byte].decode("utf-8", errors="replace").strip()
            # Fall back to stripping the raw quoted string
            raw = source[child.start_byte:child.end_byte].decode("utf-8", errors="replace").strip()
            for q in ('"""', "'''", '"', "'"):
                if raw.startswith(q) and raw.endswith(q) and len(raw) >= 2 * len(q):
                    return raw[len(q):-len(q)].strip()
            return raw
        # Stop at first non-trivial statement
        if child.type not in ("comment",):
            break
    return ""


def _preceding_comment(node, source: bytes) -> str:
    """Extract preceding JSDoc comment for TypeScript."""
    prev = node.prev_named_sibling
    if prev and prev.type == "comment":
        raw = source[prev.start_byte:prev.end_byte].decode("utf-8", errors="replace").strip()
        if raw.startswith("/**"):
            raw = raw[3:]
            if raw.endswith("*/"):
                raw = raw[:-2]
            lines = [re.sub(r"^\s*\*\s?", "", line) for line in raw.split("\n")]
            return " ".join(l.strip() for l in lines if l.strip())
        if raw.startswith("//"):
            return raw[2:].strip()
    return ""


def _extract_decorators(node, source: bytes, decorator_type: str) -> list[str]:
    """Collect decorator names from children of node matching decorator_type."""
    result = []
    for child in node.children:
        if child.type == decorator_type:
            name = _decorator_name(child, source)
            if name:
                result.append(name)
    return result


def _decorator_name(node, source: bytes) -> Optional[str]:
    """Return the base identifier name of a decorator node."""
    for child in node.children:
        if child.type in ("identifier", "type_identifier"):
            return source[child.start_byte:child.end_byte].decode("utf-8", errors="replace")
        if child.type in ("call", "call_expression"):
            func = child.child_by_field_name("function")
            if func:
                text = source[func.start_byte:func.end_byte].decode("utf-8", errors="replace")
                return text.split(".")[-1]  # last segment for dotted names like app.route
        if child.type == "attribute":
            text = source[child.start_byte:child.end_byte].decode("utf-8", errors="replace")
            return text.split(".")[-1]
    return None


def _disambiguate(symbols: list[Symbol]) -> None:
    """Add ~N suffixes to duplicate IDs."""
    seen: dict[str, int] = {}
    for sym in symbols:
        if sym.id in seen:
            seen[sym.id] += 1
            sym.id = f"{sym.id}~{seen[sym.id]}"
        else:
            seen[sym.id] = 0
