"""Intent-specific selection over proven graph records and cached source."""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
import hashlib
import heapq
import math
from pathlib import Path, PurePosixPath
import re
from typing import Any, Mapping

from ._exploration_output import Bundle, Relation, Span, pack_exploration
from .graph.anchors import select_graph_anchors
from .graph.contracts import GraphContractError, GraphEdge
from .graph.go_modules import MAX_GO_CONTROL_BYTES
from .graph.profiles import read_contained_file
from .graph.state import GraphIndexState
from .graph.traversal import filter_graph_edges, graph_adjacency, graph_hub_threshold
from .graph.type_relations import TYPE_EDGE_KINDS, type_site_key
from .storage.index_store import IndexStore
from .type_context import _CachedSource


INTENTS = ("locate", "type_dependencies", "dependencies", "impact")
TYPE_WEIGHTS = {
    "uses_type": .9,
    "extends": .95,
    "implements": .9,
    "embeds": .95,
    "supertrait": .95,
    "impl_trait": .9,
    "impl_self_type": .9,
}
IMPACT_WEIGHTS = {**TYPE_WEIGHTS, "calls": .9, "references": .7, "references_type": .75}
DEPENDENCY_WEIGHTS = {**TYPE_WEIGHTS, "calls": .9, "references": .7}
_STRUCTURAL_CONTEXTS = frozenset({"alias", "type_query", "type_argument", "constraint"})
_STOP_WORDS = frozenset("""
    a an and are as at be by can code context define definition dependency depend
    do does exact explicitly explore find for from function have how if in input
    interface is it its locate method of on only or output related relationship
    return returns show source that the their these this to type typed types use
    uses using want what when where which with you your explain field fields
""".split())
_MEMBER = re.compile(r"(?:['\"]([^'\"\n]{1,128})['\"]|([A-Za-z_$][\w$]*))\??\s*:\s*[^:;{}]*$")


def _invalid(message: str, **details: Any) -> GraphContractError:
    return GraphContractError("INVALID_INPUT", message, details)


def _terms(text: str) -> set[str]:
    text = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1 \2", text)
    text = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", text)
    values = set()
    for word in re.findall(r"[^\W_]+", text.casefold()):
        if len(word) > 4 and word.endswith("ies"):
            word = word[:-3] + "y"
        elif len(word) > 3 and word.endswith("s") and not word.endswith(("ss", "us", "is")):
            word = word[:-1]
        if len(word) >= 2 and word not in _STOP_WORDS:
            values.add(word)
    return values


def _limits(query, intent, seed_ids, max_hops, max_output_bytes, max_evidence_bytes, resolutions):
    if not isinstance(intent, str) or intent not in INTENTS:
        raise _invalid("Unsupported retrieval intent", supported_intents=list(INTENTS), fallback_intent="locate")
    if not isinstance(query, str) or len(query.encode("utf-8")) > 4096:
        raise _invalid("Query must be a string of at most 4096 UTF-8 bytes", field="query")
    if seed_ids is None:
        seed_ids = []
    if not isinstance(seed_ids, list) or len(seed_ids) > 5 or any(
        not isinstance(value, str) or not value for value in seed_ids
    ) or len(set(seed_ids)) != len(seed_ids):
        raise _invalid("Provide at most five unique, nonempty symbol IDs", field="seed_ids")
    if not query.strip() and not seed_ids:
        raise _invalid("Provide a query or explicit source symbol IDs", field="query")
    if max_hops is None:
        max_hops = {"locate": 0, "type_dependencies": 3, "dependencies": 3, "impact": 1}[intent]
    for field, value, low, high in (
        ("max_hops", max_hops, 0, 4),
        ("max_output_bytes", max_output_bytes, 2048, 262144),
        ("max_evidence_bytes", max_evidence_bytes, 0, 65536),
    ):
        if type(value) is not int or not low <= value <= high:
            raise _invalid(f"{field} must be an integer between {low} and {high}", field=field)
    if resolutions is None:
        resolutions = ["exact", "import-resolved"]
    if not isinstance(resolutions, list) or any(
        not isinstance(value, str) or value not in {"exact", "import-resolved"} for value in resolutions
    ):
        raise _invalid("Only exact and import-resolved relationships are supported", field="resolutions")
    return seed_ids, resolutions, {
        "max_hops": 0 if intent == "locate" else max_hops,
        "max_nodes": 64, "max_items": 12, "max_neighbors": 32,
        "max_output_bytes": max_output_bytes, "max_evidence_bytes": max_evidence_bytes,
    }


def _source_symbol(node: Mapping[str, Any]) -> bool:
    return (type(node.get("byte_length")) is int and node["byte_length"] > 0
            and node.get("kind") not in {"file", "package", "crate"})


class _Source:
    def __init__(self, repo: Path, store: IndexStore, nodes: Mapping[str, dict]):
        self.cache = _CachedSource(repo, store)
        self.nodes = nodes
        self.hashes = {n["file_path"]: n["content_hash"] for n in nodes.values() if n.get("kind") == "file"}
        self.languages = {n["file_path"]: n.get("language") for n in nodes.values() if n.get("kind") == "file"}
        self.definitions: dict[str, Span] = {}
        self.go_import_declarations: dict[str, tuple[_Declaration, ...]] = {}
        self.rust_declarations: dict[str, tuple[_Declaration, ...]] = {}
        self.rust_configuration_attributes: dict[tuple[str, str, int, int], tuple[Span, ...]] = {}

    def definition(self, node: dict) -> Span:
        if node["id"] not in self.definitions:
            exact = self.cache.symbol(node)
            file = node["file_path"]
            raw, _ = self.cache.file(file, self.hashes.get(file))
            start = exact["byte_offset"]
            content = exact["source"]
            line = raw[:start].count(b"\n") + 1
            self.definitions[node["id"]] = Span(
                file, start, start + len(content.encode("utf-8")), line,
                max(line, line + content.count("\n") - int(content.endswith("\n"))),
                hashlib.sha256(raw).hexdigest(), content,
            )
        return self.definitions[node["id"]]

    def support(self, support) -> Span:
        # Call definition support hashes the symbol; other families hash files.
        if support.kind in {"caller_definition", "local_definition"}:
            node = self.nodes[support.endpoint_id]
            if node["content_hash"] != support.content_hash or node["file_path"] != support.file:
                raise ValueError("Call definition support differs from its indexed endpoint")
            return self.definition(node)
        language = self.languages.get(support.file)
        if support.kind == "import_binding" and language == "go":
            return self.go_import_declaration(support)
        if support.kind in {"import_binding", "reexport", "module_declaration"} and language == "rust":
            return self.rust_declaration(support)
        value = self.cache.support(support)
        return Span(value["file"], value["byte_offset"],
                    value["byte_offset"] + len(value["content"].encode("utf-8")),
                    value["start_line"], value["end_line"], value["content_hash"], value["content"])

    def go_import_declaration(self, support) -> Span:
        raw, _ = self.cache.file(support.file, support.content_hash)
        declarations = self.go_import_declarations.get(support.file)
        if declarations is None:
            declarations = _go_import_declarations(raw)
            self.go_import_declarations[support.file] = declarations
        matches = [
            declaration for declaration in declarations
            if declaration.start_line <= support.line <= declaration.end_line
        ]
        if len(matches) != 1:
            raise ValueError("Go import support has no unique enclosing declaration")
        return _span_from_declaration(raw, support, matches[0])

    def rust_declaration(self, support) -> Span:
        raw, _ = self.cache.file(support.file, support.content_hash)
        declarations = self.rust_declarations.get(support.file)
        if declarations is None:
            declarations = _rust_declarations(raw)
            self.rust_declarations[support.file] = declarations
        expected_kind = {
            "import_binding": "use_declaration",
            "reexport": "use_declaration",
            "module_declaration": "mod_item",
        }.get(support.kind)
        matches = [
            declaration for declaration in declarations
            if declaration.kind == expected_kind
            and declaration.statement_line == support.line
        ]
        if len(matches) != 1:
            raise ValueError("Rust support has no unique enclosing declaration")
        declaration = matches[0]
        if declaration.kind != "use_declaration":
            return _span_from_declaration(raw, support, declaration)
        index = declarations.index(declaration)
        start = end = index
        while (
            start
            and declarations[start - 1].container == declaration.container
            and not raw[declarations[start - 1].end_byte:declarations[start].start_byte].strip()
        ):
            start -= 1
        while (
            end + 1 < len(declarations)
            and declarations[end + 1].container == declaration.container
            and not raw[declarations[end].end_byte:declarations[end + 1].start_byte].strip()
        ):
            end += 1
        block = _Declaration(
            declaration.kind,
            declarations[start].start_byte,
            declarations[end].end_byte,
            declarations[start].start_line,
            declarations[end].end_line,
            declarations[start].statement_line,
            declaration.container,
        )
        return _span_from_declaration(raw, support, block)

    def rust_configuration_support(self, record) -> tuple[Span, ...]:
        """Return exact cfg/other outer attributes for Rust record endpoints."""
        if getattr(record.raw, "language", None) != "rust":
            return ()
        endpoint_ids = [
            getattr(record, "source_id", getattr(record, "caller_id", None)),
            getattr(record, "target_id", None),
        ]
        endpoint_ids.extend(
            getattr(item, "endpoint_id", None) for item in getattr(record, "support", ())
        )
        spans = []
        for endpoint_id in dict.fromkeys(endpoint_ids):
            node = self.nodes.get(endpoint_id)
            if not isinstance(node, Mapping) or node.get("language") != "rust":
                continue
            file = node.get("file_path")
            offset = node.get("byte_offset")
            length = node.get("byte_length")
            if (
                not isinstance(file, str) or not isinstance(self.hashes.get(file), str)
                or type(offset) is not int or type(length) is not int or length <= 0
            ):
                continue
            content_hash = self.hashes[file]
            key = (file, content_hash, offset, offset + length)
            attributes = self.rust_configuration_attributes.get(key)
            if attributes is None:
                attributes = self._rust_endpoint_attributes(
                    file, content_hash, offset, offset + length,
                )
                self.rust_configuration_attributes[key] = attributes
            spans.extend(attributes)
        return tuple(dict.fromkeys(spans))

    def _rust_endpoint_attributes(
        self, file: str, content_hash: str, start_byte: int, end_byte: int,
    ) -> tuple[Span, ...]:
        raw, _ = self.cache.file(file, content_hash)
        try:
            from tree_sitter import Parser
            from tree_sitter_language_pack import get_language

            root = Parser(get_language("rust")).parse(raw).root_node
        except Exception as exc:
            raise ValueError("Rust configuration support source could not be parsed") from exc
        if root.has_error:
            raise ValueError("Rust configuration support source has parse errors")
        matched = next(
            (
                node for node in _walk_tree_nodes(root)
                if node.start_byte == start_byte and node.end_byte == end_byte
            ),
            None,
        )
        if matched is None:
            raise ValueError("Rust endpoint has no exact declaration node")
        attributes = []
        node = matched
        while node is not None:
            sibling = node.prev_named_sibling
            while sibling is not None:
                if sibling.type == "attribute_item":
                    attributes.append(sibling)
                elif sibling.type not in {"block_comment", "line_comment"}:
                    break
                sibling = sibling.prev_named_sibling
            node = node.parent
        spans = []
        for attribute in sorted(
            { (item.start_byte, item.end_byte) for item in attributes },
        ):
            start, end = attribute
            content = raw[start:end].decode("utf-8")
            line = raw[:start].count(b"\n") + 1
            spans.append(Span(file, start, end, line, line + content.count("\n"), content_hash, content))
        return tuple(spans)

    def control(self, control) -> Span:
        """Deliver complete, currently verified repository controls as evidence."""
        file = control.file
        if not _is_control_path(file):
            raise ValueError("Control evidence has an unsafe path")
        try:
            data, relative = read_contained_file(
                self.cache.repo,
                Path(file),
                record="Control evidence",
                max_bytes=MAX_GO_CONTROL_BYTES,
            )
        except GraphContractError as exc:
            raise ValueError("Control evidence is unavailable") from exc
        if relative != file or hashlib.sha256(data).hexdigest() != control.content_hash:
            raise ValueError("Control evidence differs from indexed input")
        if not data:
            raise ValueError("Control evidence is empty")
        try:
            content = data.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ValueError("Control evidence is not UTF-8") from exc
        return Span(
            file, 0, len(data), 1, data[:-1].count(b"\n") + 1,
            control.content_hash, content,
        )

    def member_terms(self, record) -> set[str]:
        raw = record.raw
        if raw.language == "python" and raw.context == "alias":
            # Python's explicit alias marker contains a colon but does not
            # introduce a property branch requiring a field-name query.
            return set()
        data, _ = self.cache.file(raw.source_file, raw.source_hash)
        prefix = data[max(raw.owner.start_byte, raw.start_byte - 4096):raw.start_byte].decode("utf-8", errors="ignore")
        match = _MEMBER.search(prefix)
        return _terms(next(group for group in match.groups() if group)) if match else set()


@dataclass(frozen=True)
class _Declaration:
    kind: str
    start_byte: int
    end_byte: int
    start_line: int
    end_line: int
    statement_line: int
    container: tuple[int, int]


def _walk_tree_nodes(node):
    yield node
    for child in node.named_children:
        yield from _walk_tree_nodes(child)


def _go_import_declarations(source: bytes) -> tuple[_Declaration, ...]:
    try:
        from tree_sitter import Parser
        from tree_sitter_language_pack import get_language

        root = Parser(get_language("go")).parse(source).root_node
    except Exception as exc:
        raise ValueError("Go import declaration source could not be parsed") from exc
    if root.has_error:
        raise ValueError("Go import declaration source has parse errors")
    declarations = []
    for node in root.named_children:
        if node.type != "import_declaration":
            continue
        start_line = node.start_point.row + 1
        end_line = node.end_point.row + 1
        if node.end_point.column == 0 and node.end_byte > node.start_byte:
            end_line -= 1
        declarations.append(
            _Declaration(
                node.type, node.start_byte, node.end_byte, start_line, end_line,
                node.start_point.row + 1, (node.parent.start_byte, node.parent.end_byte),
            )
        )
    return tuple(declarations)


def _rust_declarations(source: bytes) -> tuple[_Declaration, ...]:
    try:
        from tree_sitter import Parser
        from tree_sitter_language_pack import get_language

        root = Parser(get_language("rust")).parse(source).root_node
    except Exception as exc:
        raise ValueError("Rust declaration source could not be parsed") from exc
    if root.has_error:
        raise ValueError("Rust declaration source has parse errors")
    declarations = []
    stack = [root]
    while stack:
        parent = stack.pop()
        children = list(parent.named_children)
        for index, node in enumerate(children):
            if node.type not in {"use_declaration", "mod_item"}:
                continue
            start = node.start_byte
            for preceding in reversed(children[:index]):
                if preceding.type != "attribute_item":
                    break
                start = preceding.start_byte
            start_line = source[:start].count(b"\n") + 1
            end_line = node.end_point.row + 1
            if node.end_point.column == 0 and node.end_byte > start:
                end_line -= 1
            declarations.append(
                _Declaration(
                    node.type, start, node.end_byte, start_line, end_line,
                    node.start_point.row + 1, (node.parent.start_byte, node.parent.end_byte),
                )
            )
        stack.extend(reversed(children))
    return tuple(sorted(declarations, key=lambda item: (item.start_byte, item.end_byte)))


def _span_from_declaration(raw: bytes, support, declaration: _Declaration) -> Span:
    try:
        content = raw[declaration.start_byte:declaration.end_byte].decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError("Declaration source is not UTF-8") from exc
    return Span(
        support.file, declaration.start_byte, declaration.end_byte,
        declaration.start_line, declaration.end_line,
        support.content_hash, content,
    )


@dataclass(frozen=True)
class _EdgeRecord:
    record: Any
    context: str | None
    support: tuple
    controls: tuple = ()


@dataclass(frozen=True)
class _ControlEvidence:
    file: str
    content_hash: str


@dataclass(frozen=True)
class _PackageClauseSupport:
    kind: str
    file: str
    line: int
    content_hash: str
    endpoint_id: str | None = None


@dataclass(frozen=True)
class _ModuleDeclarationSupport:
    kind: str
    file: str
    line: int
    content_hash: str
    endpoint_id: str | None = None


def _edge_key(edge: GraphEdge) -> tuple[str, str, str, int]:
    return edge.type, edge.from_id, edge.to_id, edge.evidence.line


def _is_control_path(value: Any) -> bool:
    if not isinstance(value, str) or not value or "\\" in value:
        return False
    path = PurePosixPath(value)
    return (
        not path.is_absolute()
        and ".." not in path.parts
        and path.as_posix() == value
        and path.name in {"go.mod", "go.work", "Cargo.toml"}
    )


def _is_go_control_path(value: Any) -> bool:
    return _is_control_path(value) and PurePosixPath(value).name in {"go.mod", "go.work"}


def _is_rust_control_path(value: Any) -> bool:
    return _is_control_path(value) and PurePosixPath(value).name == "Cargo.toml"


def _go_controls(state: GraphIndexState) -> tuple[_ControlEvidence, ...]:
    return tuple(
        _ControlEvidence(file, content_hash)
        for file, content_hash in sorted(state.input_hashes.items())
        if _is_go_control_path(file)
        and isinstance(content_hash, str)
        and re.fullmatch(r"[0-9a-f]{64}", content_hash) is not None
    )


def _rust_controls(state: GraphIndexState, files: tuple[str, ...]) -> tuple[_ControlEvidence, ...]:
    controls = []
    for file in sorted(set(files)):
        content_hash = state.input_hashes.get(file)
        if not _is_rust_control_path(file) or not isinstance(content_hash, str):
            continue
        if re.fullmatch(r"[0-9a-f]{64}", content_hash) is None:
            continue
        controls.append(_ControlEvidence(file, content_hash))
    return tuple(controls)


def _go_package_clause_support(record: Any, nodes: Mapping[str, dict]) -> tuple[_PackageClauseSupport, ...]:
    target = nodes.get(getattr(record, "target_id", None))
    target_file = getattr(record, "target_file", None)
    if not isinstance(target_file, str) and isinstance(target, Mapping):
        target_file = target.get("file_path")
    if not isinstance(target_file, str):
        return ()
    file_node = next(
        (node for node in nodes.values()
         if node.get("kind") == "file" and node.get("file_path") == target_file),
        None,
    )
    package = None
    for evidence_node in (target, file_node):
        metadata = evidence_node.get("metadata") if isinstance(evidence_node, Mapping) else None
        loci = metadata.get("loci") if isinstance(metadata, Mapping) else None
        candidate = loci.get("go_package") if isinstance(loci, Mapping) else None
        if isinstance(candidate, Mapping):
            package = candidate
            break
    if not isinstance(package, Mapping):
        return ()
    if not isinstance(package.get("name"), str) or not package["name"]:
        return ()
    line = package.get("line")
    if type(line) is not int or line < 1:
        return ()
    evidence_node = file_node if isinstance(file_node, Mapping) else target
    content_hash = evidence_node.get("content_hash") if isinstance(evidence_node, Mapping) else None
    if not isinstance(content_hash, str) or re.fullmatch(r"[0-9a-f]{64}", content_hash) is None:
        return ()
    return (_PackageClauseSupport("package_clause", target_file, line, content_hash),)


def _rust_module_declaration_support(
    record: Any, state: GraphIndexState,
) -> tuple[_ModuleDeclarationSupport, ...]:
    raw = getattr(record, "raw", None)
    if getattr(raw, "language", None) != "rust":
        return ()
    seed_files = {
        value for value in (
            getattr(raw, "source_file", None), getattr(record, "target_file", None),
        ) if isinstance(value, str)
    }
    seed_files.update(
        support.file for support in getattr(record, "support", ())
        if isinstance(getattr(support, "file", None), str)
    )
    result = []
    pending = sorted(seed_files)
    seen_files = set()
    # Each resolved external module record proves one parent hop.  Follow only
    # those recorded hops from the involved files back to their crate roots.
    while pending:
        target_file = pending.pop(0)
        if target_file in seen_files:
            continue
        seen_files.add(target_file)
        parents = [
            imported for imported in state.imports
            if (
                imported.status == "resolved"
                and imported.raw.rust is not None
                and imported.raw.rust.kind == "module"
                and imported.target_file == target_file
            )
        ]
        for imported in sorted(parents, key=lambda item: (
            item.raw.source_file, item.raw.line, item.raw.specifier,
        )):
            result.append(_ModuleDeclarationSupport(
                "module_declaration", imported.raw.source_file, imported.raw.line,
                imported.raw.source_hash, imported.target_id,
            ))
            pending.append(imported.raw.source_file)
    record_line = getattr(raw, "line", None)
    for observation in state.rust_module_observations:
        context = observation.rust
        if (
            context is not None
            and context.kind == "module"
            and context.inline
            and observation.source_file in seen_files
            and type(record_line) is int
            and observation.line <= record_line <= observation.line + observation.text.count("\n")
        ):
            result.append(_ModuleDeclarationSupport(
                "module_declaration", observation.source_file, observation.line,
                observation.source_hash,
            ))
    return tuple(dict.fromkeys(result))


def _records(state: GraphIndexState, nodes: Mapping[str, dict]) -> dict[tuple, _EdgeRecord]:
    result = {}
    go_controls = _go_controls(state)
    references = {
        (r.raw.source_file, r.raw.source_hash, r.raw.start_byte, r.raw.end_byte): r
        for r in state.symbol_references if r.status == "resolved"
    }
    for record in sorted(state.type_relations, key=lambda r: type_site_key(r.raw)):
        if record.status == "resolved":
            key = record.raw.relation, record.source_id, record.target_id, record.raw.line
            controls = tuple(getattr(record, "resolution_controls", ())) if record.raw.language in {"go", "rust"} else ()
            support = (*record.support, *_rust_module_declaration_support(record, state))
            result.setdefault(key, _EdgeRecord(record, record.raw.context, support, controls))
    for record in state.calls:
        if record.status == "resolved":
            key = "calls", record.caller_id, record.target_id, record.raw.line
            support = record.support
            if record.resolution == "import-resolved":
                # The validated call joins one exact callee span. For imported
                # members that reference proves the declaring type, not the member.
                reference = references.get((record.raw.source_file, record.raw.source_hash,
                                            record.raw.callee_start_byte, record.raw.callee_end_byte))
                if reference is None:
                    continue
                support = (*support, *reference.support)
            if record.raw.language == "go":
                support = (*support, *_go_package_clause_support(record, nodes))
            if record.raw.language == "rust":
                support = (*support, *_rust_module_declaration_support(record, state))
            result.setdefault(key, _EdgeRecord(
                record, None, support,
                go_controls if record.raw.language == "go" else _rust_controls(
                    state, record.resolution_control_files,
                ) if record.raw.language == "rust" else (),
            ))
    for record in state.symbol_references:
        if record.status == "resolved":
            kind = "references_type" if record.binding.type_only else "references"
            key = kind, record.source_id, record.target_id, record.raw.line
            support = record.support
            if record.raw.language == "go":
                support = (*support, *_go_package_clause_support(record, nodes))
            if record.raw.language == "rust":
                support = (*support, *_rust_module_declaration_support(record, state))
            result.setdefault(key, _EdgeRecord(
                record, None, support,
                go_controls if record.raw.language == "go" else _rust_controls(
                    state, record.resolution_control_files,
                ) if record.raw.language == "rust" else (),
            ))
    return result


def _priority(step, node, record, source, query_terms, intent, depth, degree, threshold):
    weights = DEPENDENCY_WEIGHTS if intent == "dependencies" else TYPE_WEIGHTS if intent == "type_dependencies" else IMPACT_WEIGHTS
    matches = query_terms & _terms(node["name"])
    if intent == "dependencies" and record.record.raw.language == "javascript":
        reason, relevance = "Authored JavaScript dependency", .85 + .03 * min(4, len(matches))
    elif intent in {"type_dependencies", "dependencies"}:
        member_terms = source.member_terms(record.record)
        matches |= query_terms & member_terms
        if depth == 0:
            reason, relevance = "Direct declared type", 1.0
        elif step.edge.type in {
            "extends", "implements", "embeds", "supertrait", "impl_trait", "impl_self_type",
        } or (
            record.context in _STRUCTURAL_CONTEXTS and not member_terms
        ):
            reason, relevance = "Authored type or heritage continuation", .95
        elif matches:
            reason, relevance = "Query matches " + ", ".join(sorted(matches)[:4]), .8
        else:
            return None
    else:
        reason, relevance = "Known static dependent", .85 + .03 * min(4, len(matches))
    hub_factor = 1.0 / (1.0 + math.log2(max(1.0, degree / threshold)))
    return weights[step.edge.type] * relevance * hub_factor * .85, reason


def explore_context(
    repo: Path, store: IndexStore, nodes: dict[str, dict], state: GraphIndexState,
    query: str = "", *, intent: str = "locate", seed_ids: list[str] | None = None,
    max_hops: int | None = None, max_output_bytes: int = 16384,
    max_evidence_bytes: int = 8192, resolutions: list[str] | None = None,
    coverage: str = "unknown",
) -> dict:
    """Select proved relationships; relevance controls delivery, never certainty."""
    seeds, resolutions, limits = _limits(query, intent, seed_ids, max_hops,
                                        max_output_bytes, max_evidence_bytes, resolutions)
    missing = [seed for seed in seeds if seed not in nodes]
    if missing:
        raise GraphContractError("GRAPH_ENDPOINT_NOT_FOUND", "Source seed is not indexed", {"missing_ids": missing})
    omissions: Counter[str] = Counter()
    eligible = [node for node in nodes.values() if _source_symbol(node)]
    supported_seeds = [seed for seed in seeds if _source_symbol(nodes[seed])]
    omissions["unsupported_anchor"] += len(seeds) - len(supported_seeds)
    if seeds and not supported_seeds:
        anchors = ()
        mode = "explicit"
    else:
        selection = select_graph_anchors(eligible, query, supported_seeds, max_anchors=5 if seeds else 3)
        anchors = selection.anchors
        mode = selection.mode
        omissions["anchor_limit"] += selection.omitted_candidates
    base = {
        "schema_version": 1, "intent": intent, "selection": mode,
        "scope": {"source": "indexed_supported_source", "coverage": coverage,
                  "relationships": {"locate": "none", "type_dependencies": "authored_types", "dependencies": "authored_dependencies", "impact": "known_static_dependents"}[intent],
                  "exhaustive": False},
        "limits": limits, "usage": {"nodes_examined": 0},
    }
    if not anchors:
        omissions["no_anchor"] += 1
        base["omissions"] = _omissions(omissions)
        return pack_exploration(base, [])
    source = _Source(repo, store, nodes)
    focus = query
    for anchor in anchors:
        focus = re.sub(r"(?<![\w$])" + re.escape(nodes[anchor.node_id]["name"]) + r"(?![\w$])", " ", focus, flags=re.I)
    query_terms = _terms(focus)
    weights = DEPENDENCY_WEIGHTS if intent == "dependencies" else TYPE_WEIGHTS if intent == "type_dependencies" else IMPACT_WEIGHTS
    edges = filter_graph_edges(state.edges, namespaces=["loci"], edge_types=list(weights), resolutions=resolutions) if resolutions else ()
    if intent == "dependencies":
        edges = tuple(edge for edge in edges if edge.type in TYPE_WEIGHTS
                      or nodes[edge.from_id].get("language") == "javascript")
    if intent == "impact":
        adjacency = graph_adjacency(edges, direction="incoming")
    else:
        adjacency = graph_adjacency(edges, direction="outgoing")
        if intent in {"type_dependencies", "dependencies"}:
            reverse_impls = graph_adjacency(
                [edge for edge in edges if edge.type == "impl_self_type"],
                direction="incoming",
            )
            adjacency = {
                node_id: tuple(sorted(
                    (*adjacency.get(node_id, ()), *reverse_impls.get(node_id, ())),
                    key=lambda step: (
                        step.to_id, step.edge.type, step.edge.evidence.file,
                        step.edge.evidence.line, step.traversed,
                    ),
                ))
                for node_id in sorted(set(adjacency) | set(reverse_impls))
            }
    records = _records(state, nodes)
    degrees = Counter(endpoint for edge in edges for endpoint in (edge.from_id, edge.to_id))
    threshold = graph_hub_threshold(len(edges))
    unresolved = Counter(r.source_id for r in state.type_relations if r.status != "resolved")
    if intent == "dependencies":
        unresolved.update(r.source_id for r in state.symbol_references
                          if r.raw.language in {"javascript", "go"} and r.status != "resolved")
        unresolved.update(r.caller_id for r in state.calls
                          if r.raw.language in {"javascript", "go"} and r.status != "resolved")
    bundles = []
    visited = set()
    queue = []
    serial = 0
    for anchor in anchors:
        heapq.heappush(queue, (-1.0, serial, anchor.node_id, (), (), "Explicitly requested" if seeds else "Query matches " + ", ".join(anchor.matched_terms[:4])))
        serial += 1
    while queue and len(visited) < limits["max_nodes"]:
        negative, _, node_id, steps, lineage, why = heapq.heappop(queue)
        if node_id in visited:
            omissions["alternative_path"] += 1
            continue
        visited.add(node_id)
        node = nodes[node_id]
        if not _source_symbol(node):
            omissions["unsupported_anchor"] += 1
            continue
        try:
            span = source.definition(node)
            relation_values = []
            for step in steps:
                record = records.get(_edge_key(step.edge))
                if record is None:
                    raise ValueError("A projected relationship has no source record")
                supports = (
                    *(source.support(item) for item in record.support),
                    *(source.control(item) for item in record.controls),
                    *source.rust_configuration_support(record.record),
                )
                relation_values.append(Relation(
                    step.edge.to_dict(), step.traversed, supports,
                    getattr(record.record, "resolution_configuration", None),
                ))
            role = "anchor" if not steps else "dependency" if intent in {"type_dependencies", "dependencies"} else "dependent"
            bundles.append(Bundle({"id": node_id, "name": node["name"], "kind": node["kind"],
                                   "file": node["file_path"], "role": role, "depth": len(steps), "why": why},
                                  (span,), tuple(relation_values)))
        except (ValueError, UnicodeError, KeyError):
            omissions["source_unavailable"] += 1
            continue
        if intent == "locate":
            continue
        if intent in {"type_dependencies", "dependencies"}:
            supported = {"typescript", "python", "javascript", "go", "rust"} if intent == "dependencies" else {"typescript", "python", "go", "rust"}
            if node.get("language") not in supported:
                omissions["unsupported_language"] += 1
                continue
            omissions["unresolved_relation"] += unresolved[node_id]
        candidates = []
        neighbors = adjacency.get(node_id, ())
        omissions["neighbor_limit"] += max(0, len(neighbors) - limits["max_neighbors"])
        for step in neighbors[:limits["max_neighbors"]]:
            if step.to_id in (*lineage, node_id):
                omissions["cycle"] += 1
                continue
            record = records.get(_edge_key(step.edge))
            if record is None:
                omissions["source_unavailable"] += 1
                continue
            try:
                value = _priority(step, nodes[step.to_id], record, source, query_terms, intent,
                                  len(steps), degrees[step.to_id], threshold)
            except (ValueError, UnicodeError):
                omissions["source_unavailable"] += 1
                continue
            if value is None:
                omissions["not_selected"] += 1
                continue
            factor, reason = value
            candidates.append((-(-negative * factor), step.to_id, step, reason))
        candidates.sort(key=lambda c: (c[0], c[1], c[2].edge.type))
        if len(steps) >= limits["max_hops"]:
            omissions["hop_limit"] += len(candidates)
            continue
        for priority, target, step, reason in candidates:
            heapq.heappush(queue, (priority, serial, target, (*steps, step), (*lineage, node_id), reason))
            serial += 1
    if queue:
        omissions["node_limit"] += len({entry[2] for entry in queue} - visited)
    base["usage"]["nodes_examined"] = len(visited)
    base["omissions"] = _omissions(omissions)
    return pack_exploration(base, bundles)


def _omissions(values: Counter[str]) -> list[dict]:
    return [{"reason": reason, "count": count} for reason, count in sorted(values.items()) if count]
