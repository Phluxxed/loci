from __future__ import annotations
from pathlib import Path
from typing import Any, Optional
import ast
import hashlib
import re
import textwrap
import yaml

from .symbols import Symbol, make_symbol_id
from .languages import get_language_spec, EXTENSION_MAP, MARKDOWN_SUFFIXES, LanguageSpec


FRONTMATTER_SCALAR_FIELDS = (
    "title",
    "type",
    "category",
    "status",
    "source",
    "description",
    "created",
    "last_reviewed",
    "timestamp",
)
FRONTMATTER_LIST_FIELDS = ("tags",)


def parse_file(path: Path) -> list[Symbol]:
    """Parse a source file and return all symbols with byte offsets."""
    suffix = path.suffix.lower()
    if suffix in MARKDOWN_SUFFIXES:
        return parse_markdown(path)

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

    rel_path = str(path)

    try:
        from tree_sitter_language_pack import get_parser
        parser = get_parser(spec.ts_language)
        parse = getattr(parser, "parse", None)
        if parse is None:
            raise AttributeError("tree-sitter parser has no parse() method")
        tree = parse(source_bytes)
    except Exception:
        return _parse_file_with_process(source_bytes, spec, language, rel_path)

    symbols: list[Symbol] = []
    _walk(tree.root_node, source_bytes, spec, language, rel_path, symbols, parent_name=None)
    _disambiguate(symbols)
    return symbols


def _parse_file_with_process(source: bytes, spec: LanguageSpec, language: str, file_path: str) -> list[Symbol]:
    """Parse using tree-sitter-language-pack's newer high-level process() API."""
    try:
        from tree_sitter_language_pack import ProcessConfig, process

        text = source.decode("utf-8", errors="replace")
        result = process(
            text,
            ProcessConfig(
                language=spec.ts_language,
                structure=True,
                symbols=True,
                comments=True,
                docstrings=True,
            ),
        )
    except Exception:
        return []

    symbols: list[Symbol] = []
    seen: set[tuple[str, str, int, int]] = set()

    def add_symbol(
        name: str | None,
        kind: str,
        start: int,
        end: int,
        parent_name: Optional[str] = None,
        decorators: Optional[list[str]] = None,
        docstring: Optional[str] = None,
    ) -> None:
        if not name or end <= start:
            return
        if kind == "constant" and spec.constant_name_pattern and not re.fullmatch(spec.constant_name_pattern, name):
            return

        key = (name, kind, start, end)
        if key in seen:
            return
        seen.add(key)

        qualified_name = f"{parent_name}.{name}" if parent_name else name
        byte_length = end - start
        line = source[:start].count(b"\n") + 1
        end_line = source[:end].count(b"\n") + 1
        if docstring is not None:
            doc = docstring
        elif kind == "constant":
            doc = ""
        else:
            doc = _docstring_from_source(language, source, start, end)
        decs = decorators or []
        if language == "python":
            decs = [*decs, *_python_decorators_before(source, start)]
        if language == "rust":
            decs = [*decs, *_rust_decorators_before(source, start)]

        symbols.append(Symbol(
            id=make_symbol_id(file_path, qualified_name, kind),
            name=name,
            qualified_name=qualified_name,
            kind=kind,
            language=language,
            file_path=file_path,
            byte_offset=start,
            byte_length=byte_length,
            signature=_extract_signature_from_bytes(source, start, end),
            docstring=doc,
            content_hash=hashlib.sha256(source[start:end]).hexdigest(),
            decorators=sorted(set(decs)),
            keywords=sorted(_name_words(name)),
            line=line,
            end_line=end_line,
        ))

    def walk_structure(items, parent_name: Optional[str] = None) -> None:
        for item in items:
            name = getattr(item, "name", None)
            span = getattr(item, "span", None)
            kind = _process_structure_kind(getattr(item, "kind", None), parent_name)
            if name and span is not None and kind:
                start, end = _span_bounds(span)
                add_symbol(
                    name,
                    kind,
                    start,
                    end,
                    parent_name=parent_name,
                    decorators=list(getattr(item, "decorators", None) or []),
                    docstring=getattr(item, "doc_comment", None),
                )

            child_parent = name if kind in {"class", "struct", "impl", "trait", "interface"} else parent_name
            walk_structure(getattr(item, "children", None) or [], child_parent)

    walk_structure(getattr(result, "structure", None) or [])

    for item in getattr(result, "symbols", None) or []:
        kind = _process_symbol_kind(getattr(item, "kind", None), language)
        if not kind:
            continue
        span = getattr(item, "span", None)
        if span is None:
            continue
        start, end = _span_bounds(span)
        add_symbol(getattr(item, "name", None), kind, start, end, docstring=getattr(item, "doc", None))

    _add_fallback_constants(source, language, spec, add_symbol)
    _disambiguate(symbols)
    return symbols


def _span_bounds(span) -> tuple[int, int]:
    return int(getattr(span, "start_byte", 0) or 0), int(getattr(span, "end_byte", 0) or 0)


def _process_structure_kind(kind, parent_name: Optional[str]) -> str:
    value = str(kind).lower()
    mapping = {
        "function": "function",
        "method": "method",
        "class": "class",
        "struct": "struct",
        "interface": "interface",
        "enum": "enum",
        "trait": "trait",
        "impl": "impl",
    }
    result = mapping.get(value, "")
    if parent_name and result == "function":
        return "method"
    return result


def _process_symbol_kind(kind, language: str) -> str:
    value = str(kind).lower()
    if value == "constant":
        return "constant"
    if value == "type":
        return "type"
    if language == "go" and value == "interface":
        return "type"
    return ""


def _extract_signature_from_bytes(source: bytes, start: int, end: int) -> str:
    text = source[start:end].decode("utf-8", errors="replace")
    first_line = text.split("\n")[0].rstrip(":")
    return first_line.strip()


def _docstring_from_source(language: str, source: bytes, start: int, end: int) -> str:
    if language == "python":
        text = source[start:end].decode("utf-8", errors="replace")
        try:
            module = ast.parse(textwrap.dedent(text))
        except SyntaxError:
            return ""
        if not module.body:
            return ""
        return ast.get_docstring(module.body[0]) or ""

    return _preceding_doc_comment_from_bytes(source, start)


def _preceding_doc_comment_from_bytes(source: bytes, start: int) -> str:
    prefix = source[:start].decode("utf-8", errors="replace")
    lines = prefix.splitlines()
    index = len(lines) - 1
    while index >= 0 and not lines[index].strip():
        index -= 1
    if index < 0:
        return ""

    stripped = lines[index].strip()
    if stripped.endswith("*/"):
        collected: list[str] = []
        while index >= 0:
            collected.append(lines[index])
            if lines[index].strip().startswith("/*"):
                break
            index -= 1
        return _clean_doc_comment("\n".join(reversed(collected)))

    collected = []
    while index >= 0:
        stripped = lines[index].strip()
        if not stripped.startswith(("//", "///", "//!")):
            break
        collected.append(lines[index])
        index -= 1
    return _clean_doc_comment("\n".join(reversed(collected)))


def _clean_doc_comment(raw: str) -> str:
    raw = raw.strip()
    if raw.startswith("/**") or raw.startswith("/*"):
        raw = re.sub(r"^/\*\*?", "", raw)
        raw = re.sub(r"\*/$", "", raw).strip()
        lines = [re.sub(r"^\s*\*\s?", "", line) for line in raw.split("\n")]
        return " ".join(line.strip() for line in lines if line.strip())

    lines = []
    for line in raw.split("\n"):
        line = re.sub(r"^\s*//!?\s?", "", line)
        line = re.sub(r"^\s*///?\s?", "", line)
        if line.strip():
            lines.append(line.strip())
    return "\n".join(lines)


def _line_start_offsets(source: bytes) -> list[int]:
    offsets = [0]
    for index, byte in enumerate(source):
        if byte == 10:
            offsets.append(index + 1)
    return offsets


def _offset_for_position(line_starts: list[int], line: int, column: int) -> int:
    if line <= 0 or line > len(line_starts):
        return 0
    return line_starts[line - 1] + column


def _add_fallback_constants(source: bytes, language: str, spec: LanguageSpec, add_symbol) -> None:
    if language == "python":
        _add_python_constants(source, spec, add_symbol)
    elif language in {"typescript", "tsx", "javascript"}:
        _add_javascript_constants(source, add_symbol)
    elif language == "go":
        _add_go_constants(source, add_symbol)


def _add_python_constants(source: bytes, spec: LanguageSpec, add_symbol) -> None:
    text = source.decode("utf-8", errors="replace")
    line_starts = _line_start_offsets(source)
    try:
        module = ast.parse(text)
    except SyntaxError:
        return

    def visit_body(body: list[ast.stmt], parent_name: Optional[str] = None) -> None:
        for node in body:
            if isinstance(node, ast.ClassDef):
                visit_body(node.body, node.name)
                continue

            targets: list[ast.expr] = []
            if isinstance(node, ast.Assign):
                targets = list(node.targets)
            elif isinstance(node, ast.AnnAssign):
                targets = [node.target]

            for target in targets:
                if not isinstance(target, ast.Name):
                    continue
                if spec.constant_name_pattern and not re.fullmatch(spec.constant_name_pattern, target.id):
                    continue
                if not all(getattr(node, attr, None) is not None for attr in ("lineno", "col_offset", "end_lineno", "end_col_offset")):
                    continue
                start = _offset_for_position(line_starts, node.lineno, node.col_offset)
                end = _offset_for_position(line_starts, node.end_lineno, node.end_col_offset)
                add_symbol(target.id, "constant", start, end, parent_name=parent_name)

    visit_body(module.body)


def _add_javascript_constants(source: bytes, add_symbol) -> None:
    pattern = re.compile(rb"(?m)^(?:export\s+)?(?:const|let|var)\s+([A-Z][A-Z0-9_]*)\b")
    for match in pattern.finditer(source):
        name = match.group(1).decode("utf-8", errors="replace")
        add_symbol(name, "constant", match.start(), _statement_end(source, match.start()))


def _add_go_constants(source: bytes, add_symbol) -> None:
    pattern = re.compile(rb"(?m)^const\s+([A-Za-z_][A-Za-z0-9_]*)\b[^\n]*")
    for match in pattern.finditer(source):
        name = match.group(1).decode("utf-8", errors="replace")
        add_symbol(name, "constant", match.start(), match.end())


def _statement_end(source: bytes, start: int) -> int:
    depth = 0
    quote = 0
    escaped = False
    index = start
    while index < len(source):
        byte = source[index]
        if quote:
            if escaped:
                escaped = False
            elif byte == 92:
                escaped = True
            elif byte == quote:
                quote = 0
            index += 1
            continue

        if byte in (34, 39, 96):
            quote = byte
        elif byte in (40, 91, 123):
            depth += 1
        elif byte in (41, 93, 125) and depth > 0:
            depth -= 1
        elif byte == 59 and depth == 0:
            return index + 1
        elif byte == 10 and depth == 0 and index > start:
            return index
        index += 1
    return len(source)


def _python_decorators_before(source: bytes, start: int) -> list[str]:
    prefix = source[:start].decode("utf-8", errors="replace")
    lines = prefix.splitlines()
    decorators: list[str] = []
    index = len(lines) - 1
    while index >= 0:
        stripped = lines[index].strip()
        if not stripped.startswith("@"):
            break
        match = re.match(r"@\s*([A-Za-z_][A-Za-z0-9_\.]*)(?:\(|$)", stripped)
        if match:
            decorators.append(match.group(1).split(".")[-1])
        index -= 1
    return list(reversed(decorators))


def _rust_decorators_before(source: bytes, start: int) -> list[str]:
    prefix = source[:start].decode("utf-8", errors="replace")
    lines = prefix.splitlines()
    decorators: list[str] = []
    index = len(lines) - 1
    while index >= 0 and not lines[index].strip():
        index -= 1
    while index >= 0:
        stripped = lines[index].strip()
        if not stripped.startswith("#["):
            break
        match = re.match(r"#\[\s*([A-Za-z_][A-Za-z0-9_]*)", stripped)
        if match:
            decorators.append(match.group(1))
        index -= 1
    return list(reversed(decorators))


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

    # Line numbers (1-indexed) derived from byte offsets
    line = source[:byte_offset].count(b"\n") + 1
    end_line = source[:byte_offset + byte_length].count(b"\n") + 1

    # Keywords: camelCase/snake_case word split of the symbol name
    keywords = _name_words(name)

    # Decorators: child-type (Python/TS/JS) or preceding-sibling-type (Rust)
    decorators: list[str] = []
    if spec.decorator_child_type:
        dec_source = decorator_node if decorator_node else node
        decorators = _extract_decorators(dec_source, source, spec.decorator_child_type)
    if spec.decorator_sibling_type:
        decorators.extend(_extract_sibling_decorators(node, source, spec.decorator_sibling_type))

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
        keywords=sorted(keywords),
        line=line,
        end_line=end_line,
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


def _extract_sibling_decorators(node, source: bytes, sibling_type: str) -> list[str]:
    """Collect decorator names from consecutive preceding named siblings of the given type."""
    result = []
    prev = node.prev_named_sibling
    while prev is not None and prev.type == sibling_type:
        name = _decorator_name(prev, source)
        if name:
            result.append(name)
        prev = prev.prev_named_sibling
    return list(reversed(result))  # restore top-to-bottom order


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
        # Rust attribute node: recurse to find the identifier within it
        if child.type == "attribute":
            return _decorator_name(child, source)
    return None


def _name_words(name: str) -> set[str]:
    """Split a symbol name into words for keyword extraction.

    Handles snake_case, SCREAMING_SNAKE, camelCase, PascalCase,
    and leading/trailing underscores (_private, __dunder__).
    e.g. "getUserById"      → {"get", "user", "by", "id"}
         "_forecast_model"  → {"forecast", "model"}
         "__init__"         → {"init"}
    """
    parts: list[str] = []
    for segment in name.strip("_").split("_"):
        camel_split = re.sub(r"([a-z])([A-Z])", r"\1 \2", segment)
        parts.extend(camel_split.lower().split())
    return {p for p in parts if len(p) > 1}


def parse_markdown(path: Path) -> list[Symbol]:
    """Parse a markdown file into one Symbol per heading section.

    Each section spans its heading through the end of its nested subtree, nested
    by heading level via a ' > ' qualified-name path. Returns the same Symbol
    dataclass as the code path so all downstream commands work unchanged.
    """
    try:
        source = path.read_bytes()
    except (OSError, PermissionError):
        return []

    rel_path = str(path)

    from tree_sitter import Parser
    from tree_sitter_language_pack import get_language

    parser = Parser(get_language("markdown"))
    tree = parser.parse(source)
    frontmatter = _parse_frontmatter(source, path)
    frontmatter_keywords = _frontmatter_keywords(frontmatter)
    file_bytes = len(source)

    sections = [c for c in tree.root_node.children if c.type == "section"]
    has_heading = any(_md_heading_node(sec) is not None for sec in sections)

    symbols: list[Symbol] = []
    for sec in sections:
        _walk_md_section(
            sec,
            source,
            rel_path,
            parent_path=[],
            parent_index=None,
            root_index=None,
            out=symbols,
            emit_preamble=has_heading,
            frontmatter=frontmatter,
            frontmatter_keywords=frontmatter_keywords,
            file_bytes=file_bytes,
        )

    if not has_heading and source.strip():
        # No headings anywhere — index the whole file as a single section named
        # after the file stem.
        _append_md_symbol(
            source, rel_path, out=symbols,
            name=path.stem, qualified_name=path.stem,
            signature=path.stem, start=0, end=len(source),
            docstring=_md_first_paragraph(tree.root_node, source),
            summary=frontmatter.get("description", ""),
            keywords=frontmatter_keywords,
            metadata=_markdown_metadata(
                frontmatter,
                page_root=True,
                synthetic_name=True,
                heading_level=0,
                span_kind="flat_page",
                file_bytes=file_bytes,
                byte_length=len(source),
            ),
        )

    _disambiguate(symbols)
    _finalize_markdown_hierarchy(symbols)
    return symbols


def _walk_md_section(
    node,
    source: bytes,
    rel_path: str,
    parent_path: list[str],
    parent_index: int | None,
    root_index: int | None,
    out: list[Symbol],
    emit_preamble: bool,
    frontmatter: dict[str, Any],
    frontmatter_keywords: set[str],
    file_bytes: int,
) -> None:
    heading = _md_heading_node(node)

    if heading is None:
        # A top-level section with no heading is document preamble (content
        # before the first heading). Capture it only when the doc has headings.
        if emit_preamble and source[node.start_byte:node.end_byte].strip():
            _append_md_symbol(
                source, rel_path, out=out,
                name="(preamble)", qualified_name="(preamble)",
                signature="(preamble)", start=node.start_byte, end=node.end_byte,
                docstring=_md_first_paragraph(node, source),
                metadata=_markdown_metadata(
                    None,
                    page_root=False,
                    synthetic_name=True,
                    heading_level=0,
                    span_kind="preamble",
                    file_bytes=file_bytes,
                    byte_length=node.end_byte - node.start_byte,
                ),
            )
        return

    name = _md_heading_text(heading, source)
    if not name:
        return
    path_parts = [*parent_path, name]
    qualified_name = " > ".join(path_parts)
    is_page_root = not parent_path
    heading_level = _md_heading_level(heading, source)

    current_index = _append_md_symbol(
        source, rel_path, out=out,
        name=name, qualified_name=qualified_name,
        signature=_md_heading_line(heading, source),
        start=node.start_byte, end=node.end_byte,
        docstring=_md_first_paragraph(node, source),
        summary=frontmatter.get("description", "") if is_page_root else "",
        keywords=frontmatter_keywords if is_page_root else None,
        metadata=_markdown_metadata(
            frontmatter if is_page_root else None,
            page_root=is_page_root,
            synthetic_name=False,
            heading_level=heading_level,
            span_kind="page_root" if is_page_root else "section",
            file_bytes=file_bytes,
            byte_length=node.end_byte - node.start_byte,
            parent_index=parent_index,
            root_index=None if is_page_root else root_index,
        ),
    )

    child_root_index = current_index if is_page_root else root_index
    for child in node.children:
        if child.type == "section":
            _walk_md_section(
                child,
                source,
                rel_path,
                path_parts,
                parent_index=current_index,
                root_index=child_root_index,
                out=out,
                emit_preamble=False,
                frontmatter=frontmatter,
                frontmatter_keywords=frontmatter_keywords,
                file_bytes=file_bytes,
            )


def _append_md_symbol(
    source: bytes,
    rel_path: str,
    out: list[Symbol],
    name: str,
    qualified_name: str,
    signature: str,
    start: int,
    end: int,
    docstring: str,
    summary: str = "",
    keywords: set[str] | None = None,
    metadata: dict[str, Any] | None = None,
) -> int:
    line = source[:start].count(b"\n") + 1
    end_line = source[:end].count(b"\n") + 1
    symbol_keywords = _prose_words(name)
    if keywords:
        symbol_keywords.update(keywords)
    out.append(Symbol(
        id=make_symbol_id(rel_path, qualified_name, "section"),
        name=name,
        qualified_name=qualified_name,
        kind="section",
        language="markdown",
        file_path=rel_path,
        byte_offset=start,
        byte_length=end - start,
        signature=signature,
        docstring=docstring,
        summary=summary,
        content_hash=hashlib.sha256(source[start:end]).hexdigest(),
        keywords=sorted(symbol_keywords),
        metadata=metadata or {},
        line=line,
        end_line=end_line,
    ))
    return len(out) - 1


def _parse_frontmatter(source: bytes, path: Path) -> dict[str, Any]:
    text = _frontmatter_text(source)
    if text is None:
        return {}

    try:
        loaded = yaml.safe_load(text) or {}
    except yaml.YAMLError as exc:
        raise ValueError(f"Invalid markdown frontmatter in {path}: {exc}") from exc

    if not isinstance(loaded, dict):
        return {}

    metadata: dict[str, Any] = {}
    for field in FRONTMATTER_SCALAR_FIELDS:
        value = loaded.get(field)
        if _is_metadata_scalar(value):
            metadata[field] = str(value).strip()

    for field in FRONTMATTER_LIST_FIELDS:
        value = loaded.get(field)
        normalized = _metadata_string_list(value)
        if normalized:
            metadata[field] = normalized

    return metadata


def _frontmatter_text(source: bytes) -> str | None:
    lines = source.splitlines(keepends=True)
    if not lines or lines[0].strip() != b"---":
        return None

    body: list[bytes] = []
    for line in lines[1:]:
        if line.strip() == b"---":
            return b"".join(body).decode("utf-8", errors="replace")
        body.append(line)
    return None


def _is_metadata_scalar(value: Any) -> bool:
    return value is not None and not isinstance(value, (dict, list, tuple, set))


def _metadata_string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        items = [value]
    elif isinstance(value, (list, tuple, set)):
        items = list(value)
    else:
        items = [value]
    return [text for item in items if (text := str(item).strip())]


def _frontmatter_keywords(frontmatter: dict[str, Any]) -> set[str]:
    keywords: set[str] = set()
    for value in frontmatter.values():
        if isinstance(value, list):
            for item in value:
                keywords.update(_prose_words(item))
        else:
            keywords.update(_prose_words(str(value)))
    return keywords


def _markdown_metadata(
    frontmatter: dict[str, Any] | None,
    *,
    page_root: bool,
    synthetic_name: bool,
    heading_level: int,
    span_kind: str,
    file_bytes: int,
    byte_length: int,
    parent_index: int | None = None,
    root_index: int | None = None,
) -> dict[str, Any]:
    metadata: dict[str, Any] = {}
    if frontmatter:
        metadata["frontmatter"] = {
            key: list(value) if isinstance(value, list) else value
            for key, value in frontmatter.items()
        }
    saved_pct = int((file_bytes - byte_length) / file_bytes * 100) if file_bytes > 0 else 0
    saved_pct = max(0, min(100, saved_pct))
    markdown: dict[str, Any] = {
        "page_root": page_root,
        "synthetic_name": synthetic_name,
        "heading_level": heading_level,
        "parent_id": "",
        "root_id": "",
        "file_bytes": file_bytes,
        "saved_pct": saved_pct,
        "span_kind": span_kind,
    }
    if parent_index is not None:
        markdown["_parent_index"] = parent_index
    if root_index is not None:
        markdown["_root_index"] = root_index
    metadata["markdown"] = markdown
    return metadata


def _finalize_markdown_hierarchy(symbols: list[Symbol]) -> None:
    """Resolve temporary parent/root indexes after duplicate IDs are final."""
    for sym in symbols:
        metadata = sym.metadata if isinstance(sym.metadata, dict) else {}
        markdown = metadata.get("markdown")
        if not isinstance(markdown, dict):
            continue

        parent_index = markdown.pop("_parent_index", None)
        root_index = markdown.pop("_root_index", None)
        markdown["parent_id"] = (
            symbols[parent_index].id
            if isinstance(parent_index, int) and 0 <= parent_index < len(symbols)
            else ""
        )
        markdown["root_id"] = (
            symbols[root_index].id
            if isinstance(root_index, int) and 0 <= root_index < len(symbols)
            else sym.id
        )


def _md_heading_node(section_node):
    """Return the ATX heading child of a section node, or None."""
    for child in section_node.children:
        if child.type == "atx_heading":
            return child
    return None


def _md_heading_text(heading_node, source: bytes) -> str:
    """The heading text, taken from the heading's inline child."""
    for child in heading_node.children:
        if child.type == "inline":
            return source[child.start_byte:child.end_byte].decode("utf-8", errors="replace").strip()
    return ""


def _md_heading_line(heading_node, source: bytes) -> str:
    """The raw heading line including markers, e.g. '### Details'."""
    text = source[heading_node.start_byte:heading_node.end_byte].decode("utf-8", errors="replace")
    return text.split("\n")[0].strip()


def _md_heading_level(heading_node, source: bytes) -> int:
    """Return the ATX heading marker depth, e.g. '### Details' -> 3."""
    line = _md_heading_line(heading_node, source).lstrip()
    return len(line) - len(line.lstrip("#"))


def _md_first_paragraph(node, source: bytes) -> str:
    """First direct-child paragraph's text, whitespace-collapsed."""
    for child in node.children:
        if child.type == "paragraph":
            raw = source[child.start_byte:child.end_byte].decode("utf-8", errors="replace")
            return " ".join(raw.split())
    return ""


def _prose_words(text: str) -> set[str]:
    """Tokenise natural-language heading text into search keywords."""
    return {w for w in re.split(r"[^A-Za-z0-9]+", text.lower()) if len(w) > 1}


def _disambiguate(symbols: list[Symbol]) -> None:
    """Add ~N suffixes to duplicate IDs."""
    seen: dict[str, int] = {}
    for sym in symbols:
        if sym.id in seen:
            seen[sym.id] += 1
            sym.id = f"{sym.id}~{seen[sym.id]}"
        else:
            seen[sym.id] = 0
