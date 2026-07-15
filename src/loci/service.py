from __future__ import annotations

import os
import re
import time
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Any

import pathspec

from loci.graph.contracts import (
    GRAPH_SCHEMA_VERSION,
    GraphContractError,
    GraphNodeRef,
    validate_graph_edges,
)
from loci.graph.anchors import select_graph_anchors
from loci.graph.materialize import load_graph_extensions, materialize_graph
from loci.graph.profiles import required_frontmatter_fields
from loci.graph.state import GraphDiagnostic, GraphIndexState
from loci.graph.retrieval import (
    retrieve_graph_neighbors,
    retrieve_graph_paths,
    retrieve_graph_question,
)
from loci.graph.traversal import GraphDirection
from loci.parser.extractor import parse_file
from loci.parser.imports import ImportExtractionError, RawImport, extract_imports
from loci.parser.languages import EXTENSION_MAP, MARKDOWN_SUFFIXES
from loci.parser.symbols import Symbol, make_file_symbol
from loci.storage.index_store import IndexStore, index_versions_current
from loci.storage.store_resolver import StoreResolution, resolve_store_base_dir

SKIP_DIRS = {
    ".git", "node_modules", "__pycache__", ".venv", "venv",
    ".tox", "dist", "build", ".mypy_cache", ".pytest_cache",
    ".ruff_cache", ".uv-cache", "uv-cache", "__tests__", "tests",
}
TEST_FILE_SUFFIXES = (
    ".test.ts", ".test.tsx", ".test.js", ".test.jsx",
    ".spec.ts", ".spec.tsx", ".spec.js", ".spec.jsx",
)
SKIP_FILES = {".env", ".env.local", "credentials.json", "secrets.json"}
SKIP_EXTENSIONS = {
    ".pyc", ".pyo", ".so", ".dylib", ".dll", ".exe",
    ".bin", ".pem", ".key", ".p12",
}
REFRESH_LOCK_POLL_SECONDS = 0.05


@dataclass
class LociError(Exception):
    code: str
    message: str
    details: dict[str, Any] = field(default_factory=dict)

    def __str__(self) -> str:
        return self.message

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "message": self.message,
            "details": self.details,
        }


def get_store() -> IndexStore:
    return _get_store_with_resolution()[0]


def get_store_resolution() -> StoreResolution:
    return resolve_store_base_dir()


def _get_store_with_resolution() -> tuple[IndexStore, StoreResolution]:
    resolution = resolve_store_base_dir()
    return IndexStore(base_dir=resolution.base_dir), resolution


def index_repo(path: str | Path, incremental: bool = True) -> dict[str, Any]:
    repo_path = Path(path).resolve()
    if not repo_path.exists():
        raise LociError(
            "PATH_NOT_FOUND",
            "Path not found",
            {"path": str(repo_path)},
        )
    if not repo_path.is_dir():
        raise LociError(
            "INVALID_INPUT",
            "Path is not a directory",
            {"path": str(repo_path)},
        )

    store = get_store()
    existing = store.load(repo_path) if incremental else None
    if existing is not None and not index_versions_current(existing):
        existing = None
    previous_graph: GraphIndexState | None = None
    if existing is not None:
        graph_value = existing.get("graph")
        if not isinstance(graph_value, dict):
            existing = None
        else:
            try:
                previous_graph = GraphIndexState.from_dict(graph_value)
            except GraphContractError:
                existing = None
    existing_hashes: dict[str, str] = existing.get("file_hashes", {}) if existing else {}
    existing_symbols: list[dict[str, Any]] = existing.get("symbols", []) if existing else []
    previous_imports: dict[str, list[RawImport]] = defaultdict(list)
    previous_import_diagnostics: dict[str, list[GraphDiagnostic]] = defaultdict(list)
    if previous_graph is not None:
        for record in previous_graph.imports:
            previous_imports[record.raw.source_file].append(record.raw)
        for diagnostic in previous_graph.diagnostics:
            if (
                diagnostic.code == "GRAPH_IMPORT_EXTRACTION_FAILED"
                and diagnostic.source is not None
            ):
                previous_import_diagnostics[diagnostic.source].append(diagnostic)
    extension_load = load_graph_extensions(
        repo_path,
        previous_graph=previous_graph,
    )
    profile_fields = required_frontmatter_fields(extension_load.profiles)
    previous_profile_fields = required_frontmatter_fields(
        previous_graph.profiles if previous_graph is not None else ()
    )
    profile_fields_changed = profile_fields != previous_profile_fields

    all_symbols: list[Symbol] = []
    new_file_hashes: dict[str, str] = {}
    files_skipped = 0
    language_counts: dict[str, int] = defaultdict(int)
    zero_symbol_warnings: list[dict[str, Any]] = []
    raw_imports: list[RawImport] = []
    import_diagnostics: list[GraphDiagnostic] = []

    for src_file, rel_path, file_hash in _iter_indexable_files(repo_path, store):
        new_file_hashes[rel_path] = file_hash

        requires_profile_reparse = (
            profile_fields_changed
            and src_file.suffix.lower() in MARKDOWN_SUFFIXES
        )
        if (
            incremental
            and not requires_profile_reparse
            and existing_hashes.get(rel_path) == file_hash
        ):
            kept = [Symbol.from_dict(s) for s in existing_symbols if s["file_path"] == rel_path]
            all_symbols.extend(kept)
            raw_imports.extend(previous_imports.get(rel_path, ()))
            import_diagnostics.extend(
                previous_import_diagnostics.get(rel_path, ())
            )
            files_skipped += 1
            lang = EXTENSION_MAP.get(src_file.suffix, "unknown")
            language_counts[lang] += 1
            continue

        if profile_fields and src_file.suffix.lower() in MARKDOWN_SUFFIXES:
            symbols = parse_file(
                src_file,
                markdown_frontmatter_fields=profile_fields,
            )
        else:
            symbols = parse_file(src_file)
        id_map: dict[str, str] = {}
        for sym in symbols:
            old_id = sym.id
            sym.file_path = rel_path
            suffix_match = re.search(r"~\d+$", old_id)
            suffix = suffix_match.group(0) if suffix_match else ""
            sym.id = f"{rel_path}::{sym.qualified_name}#{sym.kind}{suffix}"
            id_map[old_id] = sym.id
        for sym in symbols:
            _remap_markdown_hierarchy_ids(sym, id_map)
        all_symbols.extend(symbols)
        lang = EXTENSION_MAP.get(src_file.suffix, "unknown")
        if symbols:
            language_counts[lang] += 1
        else:
            try:
                file_bytes = src_file.read_bytes()
            except OSError:
                file_bytes = b""
            line_count = len(file_bytes.splitlines())
            is_nonempty_markdown = (
                src_file.suffix.lower() in MARKDOWN_SUFFIXES
                and bool(file_bytes.strip())
            )
            if line_count > 10 or is_nonempty_markdown:
                zero_symbol_warnings.append({
                    "file": rel_path,
                    "lines": line_count,
                    "reason": "0 symbols extracted",
                })
        if src_file.suffix.lower() not in MARKDOWN_SUFFIXES:
            all_symbols.append(make_file_symbol(
                rel_path,
                language=lang,
                content_hash=file_hash,
            ))
            try:
                raw_imports.extend(extract_imports(
                    src_file,
                    source_file=rel_path,
                    language=lang,
                    source_hash=file_hash,
                ))
            except ImportExtractionError as exc:
                import_diagnostics.append(GraphDiagnostic(
                    severity="warning",
                    code="GRAPH_IMPORT_EXTRACTION_FAILED",
                    message="Import observations could not be extracted",
                    source=rel_path,
                    details={"reason": str(exc)},
                ))

    graph_state = materialize_graph(
        repo_path,
        all_symbols,
        new_file_hashes,
        extension_load.profiles,
        extension_load.contributions,
        raw_imports=raw_imports,
        input_hashes=extension_load.input_hashes,
        diagnostics=(*extension_load.diagnostics, *import_diagnostics),
    )
    try:
        store.write(
            repo_path,
            all_symbols,
            file_hashes=new_file_hashes,
            graph_state=graph_state,
        )
    except GraphContractError as exc:
        raise LociError(exc.code, exc.message, exc.details) from exc

    output: dict[str, Any] = {
        "path": str(repo_path),
        "symbols_indexed": len(all_symbols),
        "graph_profiles_loaded": len(graph_state.profiles),
        "graph_contributions_loaded": len(graph_state.contributions),
        "graph_contributions_reused": extension_load.contributions_reused,
        "graph_node_overlays_indexed": len(graph_state.nodes),
        "graph_edges_indexed": len(graph_state.edges),
        "graph_file_nodes_indexed": sum(
            symbol.kind == "file" for symbol in all_symbols
        ),
        "graph_imports_indexed": len(graph_state.imports),
        "graph_imports_resolved": sum(
            record.status == "resolved" for record in graph_state.imports
        ),
        "graph_imports_unresolved": sum(
            record.status == "unresolved" for record in graph_state.imports
        ),
        "graph_status": _graph_status(graph_state),
        "graph_diagnostics": [
            diagnostic.to_dict() for diagnostic in graph_state.diagnostics
        ],
        "files_skipped": files_skipped,
        "languages": dict(language_counts),
    }
    if zero_symbol_warnings:
        output["warnings"] = zero_symbol_warnings
    return output


def ensure_fresh_index(repo: str | Path) -> dict[str, Any]:
    repo_path = Path(repo).resolve()
    store = get_store()
    index = _load_required_index(store, repo_path)
    _validate_repo_path(repo_path)
    if not _index_is_stale(repo_path, store, index):
        return {"repo": str(repo_path), "refreshed": False}

    lock_path = store.refresh_lock_path(repo_path)
    timeout = float(os.environ.get("LOCI_REFRESH_LOCK_TIMEOUT", "10"))
    _acquire_refresh_lock(lock_path, timeout=timeout)
    try:
        index = _load_required_index(store, repo_path)
        if not _index_is_stale(repo_path, store, index):
            return {"repo": str(repo_path), "refreshed": False}
        result = index_repo(repo_path, incremental=True)
        return {"repo": str(repo_path), "refreshed": True, "index": result}
    except LociError:
        raise
    except Exception as exc:
        raise LociError(
            "STALE_INDEX_REFRESH_FAILED",
            "Failed to refresh stale index",
            {"repo": str(repo_path), "error": str(exc)},
        ) from exc
    finally:
        lock_path.unlink(missing_ok=True)


def outline_repo(
    path: str | Path,
    file: str | None = None,
    ensure_fresh: bool = False,
) -> list[dict[str, Any]]:
    repo_path = Path(path).resolve()
    store = get_store()
    if ensure_fresh:
        ensure_fresh_index(repo_path)
    index = _load_required_index(store, repo_path)

    grouped: dict[str, list[dict[str, Any]]] = {}
    languages: set[str] = set()
    for symbol in index["symbols"]:
        file_path = symbol["file_path"]
        if file and file_path != file:
            continue
        entry: dict[str, Any] = {
            "id": symbol.get("id", ""),
            "name": symbol.get("name", ""),
            "kind": symbol.get("kind", ""),
            "line": symbol.get("line", 0),
            "end_line": symbol.get("end_line", 0),
            "signature": symbol.get("signature", ""),
            "summary": symbol.get("summary", ""),
        }
        if symbol.get("decorators"):
            entry["decorators"] = symbol["decorators"]
        _add_markdown_retrieval_fields(entry, symbol)
        grouped.setdefault(file_path, []).append(entry)
        if symbol.get("language"):
            languages.add(symbol["language"])

    result = [{"file": fp, "symbols": symbols} for fp, symbols in sorted(grouped.items())]
    symbol_count = sum(len(symbols) for symbols in grouped.values())
    store.log_outline(
        str(repo_path),
        symbol_count,
        file_filter=file,
        languages=sorted(languages),
    )
    return result


def get_symbols(
    repo: str | Path,
    symbol_ids: list[str],
    context: int = 0,
    ensure_fresh: bool = False,
) -> list[dict[str, Any]]:
    repo_path = Path(repo).resolve()
    if not symbol_ids:
        raise LociError(
            "INVALID_INPUT",
            "At least one symbol id is required",
            {"repo": str(repo_path)},
        )
    if context < 0:
        raise LociError(
            "INVALID_INPUT",
            "Context must be greater than or equal to 0",
            {"context": context},
        )

    store = get_store()
    if ensure_fresh:
        ensure_fresh_index(repo_path)
    index = _load_required_index(store, repo_path)

    return [_get_symbol(repo_path, store, index, symbol_id, context) for symbol_id in symbol_ids]


def search_symbols(
    repo: str | Path,
    query: str,
    kind: str | None = None,
    lang: str | None = None,
    limit: int = 20,
    ensure_fresh: bool = False,
) -> list[dict[str, Any]]:
    repo_path = Path(repo).resolve()
    if limit < 1:
        raise LociError(
            "INVALID_INPUT",
            "Limit must be greater than 0",
            {"limit": limit},
        )

    store = get_store()
    if ensure_fresh:
        ensure_fresh_index(repo_path)
    _load_required_index(store, repo_path)

    results = store.search(repo_path, query, kind=kind, lang=lang, limit=limit)
    if results:
        search_id = str(uuid.uuid4())
        store.log_search(search_id, query, str(repo_path), [result["id"] for result in results])
    else:
        store.log_miss("search_empty", repo_path=str(repo_path), query=query)
    return results


def get_cached_file(
    repo: str | Path,
    file_path: str,
    start_line: int | None = None,
    end_line: int | None = None,
    ensure_fresh: bool = False,
) -> dict[str, Any]:
    repo_path = Path(repo).resolve()
    store = get_store()
    if ensure_fresh:
        ensure_fresh_index(repo_path)
    _load_required_index(store, repo_path)

    result = store.get_file_content(
        repo_path,
        file_path,
        start_line=start_line,
        end_line=end_line,
    )
    if result is None:
        raise LociError(
            "FILE_NOT_FOUND",
            "File not found in cache",
            {"repo": str(repo_path), "file": file_path},
        )

    symbol_bytes = len(result["content"].encode("utf-8"))
    file_bytes = result.pop("file_bytes")
    language = EXTENSION_MAP.get(Path(file_path).suffix)
    store.log_retrieval(
        file_path,
        symbol_bytes,
        file_bytes,
        repo_path=str(repo_path),
        language=language,
    )
    return result


def grep_repo(
    repo: str | Path,
    pattern: str,
    ensure_fresh: bool = False,
) -> list[dict[str, Any]]:
    repo_path = Path(repo).resolve()
    store = get_store()
    if ensure_fresh:
        ensure_fresh_index(repo_path)
    _load_required_index(store, repo_path)

    try:
        return store.grep_files(repo_path, pattern)
    except ValueError as exc:
        raise LociError(
            "INVALID_REGEX",
            str(exc),
            {"repo": str(repo_path), "pattern": pattern},
        ) from exc


def graph_anchors(
    repo: str | Path,
    question: str,
    seed_ids: list[str] | None = None,
    *,
    max_anchors: int = 10,
    ensure_fresh: bool = False,
) -> dict[str, Any]:
    repo_path = Path(repo).resolve()
    store = get_store()
    if ensure_fresh:
        ensure_fresh_index(repo_path)
    index = _load_required_index(store, repo_path)
    symbol_values = index.get("symbols", [])
    indexed_nodes = {
        symbol["id"]: symbol
        for symbol in symbol_values
        if isinstance(symbol, dict) and isinstance(symbol.get("id"), str)
    }
    graph_value = index.get("graph")
    if not isinstance(graph_value, dict):
        raise LociError(
            "INVALID_GRAPH_SCHEMA",
            "Persisted graph state is missing",
            {"repo": str(repo_path)},
        )
    try:
        graph_state = GraphIndexState.from_dict(graph_value)
        selection = select_graph_anchors(
            tuple(indexed_nodes.values()),
            question,
            seed_ids if seed_ids is not None else [],
            max_anchors=max_anchors,
        )
    except GraphContractError as exc:
        raise LociError(exc.code, exc.message, exc.details) from exc

    reason_kind = "explicit_seed" if selection.mode == "explicit" else "inferred"
    anchors = []
    for anchor in selection.anchors:
        node = indexed_nodes[anchor.node_id]
        anchors.append({
            "node": _graph_node_ref(node),
            "matched_symbol_id": anchor.matched_symbol_id,
            "name": anchor.name,
            "score": anchor.score,
            "reason": {
                "kind": reason_kind,
                "matched_terms": list(anchor.matched_terms),
                "match_scope": list(anchor.match_scope),
            },
        })
    return {
        "schema_version": GRAPH_SCHEMA_VERSION,
        "repo": str(repo_path),
        "question": question,
        "selection": selection.mode,
        "question_terms": list(selection.question_terms),
        "anchors": anchors,
        "counts": {
            "indexed_nodes": len(indexed_nodes),
            "eligible_units": selection.eligible_units,
            "qualified_candidates": selection.qualified_candidates,
            "collapsed_symbols": selection.collapsed_symbols,
            "returned_anchors": len(anchors),
            "omitted_candidates": selection.omitted_candidates,
        },
        "budget": {
            "requested_max_anchors": selection.requested_max_anchors,
            "effective_max_anchors": selection.effective_max_anchors,
        },
        "diagnostics": [
            diagnostic.to_dict() for diagnostic in graph_state.diagnostics
        ],
    }


def graph_neighbors(
    repo: str | Path,
    seed_ids: list[str],
    *,
    ensure_fresh: bool = False,
) -> dict[str, Any]:
    repo_path = Path(repo).resolve()
    if not seed_ids:
        raise LociError(
            "INVALID_INPUT",
            "At least one graph seed is required",
            {"repo": str(repo_path)},
        )
    if any(not isinstance(seed_id, str) or not seed_id for seed_id in seed_ids):
        raise LociError(
            "INVALID_INPUT",
            "Graph seeds must be non-empty strings",
            {"repo": str(repo_path)},
        )
    unique_seed_ids = list(dict.fromkeys(seed_ids))

    store = get_store()
    if ensure_fresh:
        ensure_fresh_index(repo_path)
    index = _load_required_index(store, repo_path)
    symbol_values = index.get("symbols", [])
    indexed_nodes = {
        symbol["id"]: symbol
        for symbol in symbol_values
        if isinstance(symbol, dict) and isinstance(symbol.get("id"), str)
    }
    missing_ids = [seed_id for seed_id in unique_seed_ids if seed_id not in indexed_nodes]
    if missing_ids:
        raise LociError(
            "GRAPH_ENDPOINT_NOT_FOUND",
            "Graph seed is not indexed",
            {"repo": str(repo_path), "missing_ids": missing_ids},
        )

    try:
        edges = [
            edge
            for edge in store.get_graph_edges(repo_path)
            if (
                edge.namespace == "loci"
                and edge.type == "contains"
                and edge.directed is True
                and edge.resolution == "exact"
            )
        ]
        validate_graph_edges(edges, indexed_nodes=indexed_nodes)
    except GraphContractError as exc:
        raise LociError(exc.code, exc.message, exc.details) from exc

    outgoing: dict[str, list] = {}
    for edge in sorted(
        edges,
        key=lambda item: (item.namespace, item.type, item.from_id, item.to_id),
    ):
        outgoing.setdefault(edge.from_id, []).append(edge)

    results = []
    for seed_id in unique_seed_ids:
        neighbors = [
            {
                "node": _graph_node_ref(indexed_nodes[edge.to_id]),
                "edge": edge.to_dict(),
            }
            for edge in outgoing.get(seed_id, [])
        ]
        results.append({
            "seed": _graph_node_ref(indexed_nodes[seed_id]),
            "neighbors": neighbors,
        })

    return {
        "schema_version": GRAPH_SCHEMA_VERSION,
        "repo": str(repo_path),
        "results": results,
        "diagnostics": [],
    }


def graph_traverse_neighbors(
    repo: str | Path,
    seed_ids: list[str],
    *,
    namespaces: list[str] | None = None,
    edge_types: list[str] | None = None,
    resolutions: list[str] | None = None,
    direction: GraphDirection = "outgoing",
    max_neighbors: int = 64,
    ensure_fresh: bool = False,
) -> dict[str, Any]:
    repo_path = Path(repo).resolve()
    _store, indexed_nodes, graph_state = _load_graph_context(
        repo_path,
        ensure_fresh=ensure_fresh,
    )
    try:
        return retrieve_graph_neighbors(
            repo_path,
            indexed_nodes,
            graph_state,
            seed_ids,
            namespaces=namespaces,
            edge_types=edge_types,
            resolutions=resolutions,
            direction=direction,
            max_neighbors=max_neighbors,
        )
    except GraphContractError as exc:
        raise LociError(exc.code, exc.message, exc.details) from exc


def graph_paths(
    repo: str | Path,
    source_ids: list[str],
    target_ids: list[str],
    *,
    namespaces: list[str] | None = None,
    edge_types: list[str] | None = None,
    resolutions: list[str] | None = None,
    direction: GraphDirection = "outgoing",
    max_hops: int = 3,
    max_nodes: int = 64,
    max_paths: int = 8,
    path_offset: int = 0,
    max_evidence_bytes: int = 32_768,
    max_estimated_tokens: int = 8_192,
    ensure_fresh: bool = False,
) -> dict[str, Any]:
    repo_path = Path(repo).resolve()
    store, indexed_nodes, graph_state = _load_graph_context(
        repo_path,
        ensure_fresh=ensure_fresh,
    )
    try:
        return retrieve_graph_paths(
            repo_path,
            store,
            indexed_nodes,
            graph_state,
            source_ids,
            target_ids,
            namespaces=namespaces,
            edge_types=edge_types,
            resolutions=resolutions,
            direction=direction,
            max_hops=max_hops,
            max_nodes=max_nodes,
            max_paths=max_paths,
            path_offset=path_offset,
            max_evidence_bytes=max_evidence_bytes,
            max_estimated_tokens=max_estimated_tokens,
        )
    except GraphContractError as exc:
        raise LociError(exc.code, exc.message, exc.details) from exc


def graph_retrieve(
    repo: str | Path,
    question: str,
    seed_ids: list[str] | None = None,
    *,
    namespaces: list[str] | None = None,
    edge_types: list[str] | None = None,
    resolutions: list[str] | None = None,
    direction: GraphDirection = "either",
    max_anchors: int = 10,
    max_hops: int = 3,
    max_nodes: int = 64,
    max_paths: int = 8,
    path_offset: int = 0,
    max_evidence_bytes: int = 32_768,
    max_estimated_tokens: int = 8_192,
    ensure_fresh: bool = False,
) -> dict[str, Any]:
    repo_path = Path(repo).resolve()
    store, indexed_nodes, graph_state = _load_graph_context(
        repo_path,
        ensure_fresh=ensure_fresh,
    )
    try:
        return retrieve_graph_question(
            repo_path,
            store,
            indexed_nodes,
            graph_state,
            question,
            seed_ids,
            namespaces=namespaces,
            edge_types=edge_types,
            resolutions=resolutions,
            direction=direction,
            max_anchors=max_anchors,
            max_hops=max_hops,
            max_nodes=max_nodes,
            max_paths=max_paths,
            path_offset=path_offset,
            max_evidence_bytes=max_evidence_bytes,
            max_estimated_tokens=max_estimated_tokens,
        )
    except GraphContractError as exc:
        raise LociError(exc.code, exc.message, exc.details) from exc


def graph_health(
    repo: str | Path,
    *,
    ensure_fresh: bool = False,
) -> dict[str, Any]:
    repo_path = Path(repo).resolve()
    store = get_store()
    if ensure_fresh:
        ensure_fresh_index(repo_path)
    index = _load_required_index(store, repo_path)
    graph_value = index.get("graph")
    if not isinstance(graph_value, dict):
        raise LociError(
            "INVALID_GRAPH_SCHEMA",
            "Persisted graph state is missing",
            {"repo": str(repo_path)},
        )
    try:
        state = GraphIndexState.from_dict(graph_value)
    except GraphContractError as exc:
        raise LociError(exc.code, exc.message, exc.details) from exc

    profiles = []
    for loaded in state.profiles:
        profile = loaded.profile
        node_attributes = sorted({
            attribute.name
            for rule in profile.node_rules
            for attribute in rule.attributes
        })
        profiles.append({
            "namespace": profile.namespace,
            "source": loaded.source,
            "content_hash": loaded.content_hash,
            "node_attributes": node_attributes,
            "edge_types": [
                edge_type.to_dict() for edge_type in profile.edge_types
            ],
        })
    diagnostic_values = [
        diagnostic.to_dict() for diagnostic in state.diagnostics
    ]
    return {
        "schema_version": GRAPH_SCHEMA_VERSION,
        "repo": str(repo_path),
        "status": _graph_status(state),
        "profiles": profiles,
        "counts": {
            "profiles": len(state.profiles),
            "node_overlays": len(state.nodes),
            "edges": len(state.edges),
            "contributions": len(state.contributions),
            "diagnostics": len(state.diagnostics),
        },
        "diagnostics": diagnostic_values,
    }


def verify_repo(path: str | Path) -> dict[str, Any]:
    repo_path = Path(path).resolve()
    store = get_store()
    result = store.verify_index(repo_path)
    if "error" in result:
        raise LociError(
            "REPO_NOT_INDEXED",
            "Repository is not indexed",
            {"repo": str(repo_path)},
        )
    return result


def list_repos() -> list[dict[str, Any]]:
    return get_store().list_repos()


def session_stats(
    repo: str | Path | None = None,
    since_days: int | None = 7,
) -> dict[str, Any]:
    if since_days is not None and since_days < 0:
        raise LociError(
            "INVALID_INPUT",
            "since_days must be greater than or equal to 0",
            {"since_days": since_days},
        )

    store, resolution = _get_store_with_resolution()
    repo_filter = str(Path(repo).resolve()) if repo else None
    stats = store.get_session_stats(repo_filter=repo_filter, since_days=since_days)
    stats["store"] = resolution.to_dict()
    return stats


def reset_session_stats() -> dict[str, Any]:
    store, resolution = _get_store_with_resolution()
    backup = store.reset_session()
    return {
        "reset": True,
        "backup": str(backup) if backup is not None else None,
        "store": resolution.to_dict(),
    }


def analyze_usage(
    repo: str | Path | None = None,
    since_days: int = 30,
) -> dict[str, Any]:
    if since_days < 0:
        raise LociError(
            "INVALID_INPUT",
            "since_days must be greater than or equal to 0",
            {"since_days": since_days},
        )

    store, resolution = _get_store_with_resolution()
    repo_filter = str(Path(repo).resolve()) if repo else None
    result = store.analyze(since_days=since_days, repo_filter=repo_filter)
    result["store"] = resolution.to_dict()
    return result


def _validate_repo_path(repo_path: Path) -> None:
    if not repo_path.exists():
        raise LociError(
            "PATH_NOT_FOUND",
            "Path not found",
            {"path": str(repo_path)},
        )
    if not repo_path.is_dir():
        raise LociError(
            "INVALID_INPUT",
            "Path is not a directory",
            {"path": str(repo_path)},
        )


def _load_required_index(store: IndexStore, repo_path: Path) -> dict[str, Any]:
    index = store.load(repo_path)
    if index is None:
        raise LociError(
            "REPO_NOT_INDEXED",
            "Repository is not indexed",
            {"repo": str(repo_path)},
        )
    return index


def _index_is_stale(repo_path: Path, store: IndexStore, index: dict[str, Any]) -> bool:
    if not index_versions_current(index):
        return True
    current_hashes = {
        rel_path: file_hash
        for _, rel_path, file_hash in _iter_indexable_files(repo_path, store)
    }
    indexed_hashes = index.get("file_hashes", {})
    if current_hashes != indexed_hashes:
        return True
    current_graph_hashes = load_graph_extensions(repo_path).input_hashes
    graph = index.get("graph")
    if not isinstance(graph, dict):
        return True
    try:
        persisted_graph = GraphIndexState.from_dict(graph)
    except GraphContractError:
        return True
    indexed_graph_hashes = persisted_graph.input_hashes
    if current_graph_hashes != indexed_graph_hashes:
        return True
    return not _active_graph_paths_are_safe(repo_path, index)


def _active_graph_paths_are_safe(
    repo_path: Path,
    index: dict[str, Any],
) -> bool:
    graph = index.get("graph")
    edge_values = graph.get("edges", []) if isinstance(graph, dict) else []
    symbols = {
        symbol.get("id"): symbol
        for symbol in index.get("symbols", [])
        if isinstance(symbol, dict) and isinstance(symbol.get("id"), str)
    }
    paths: set[str] = set()
    node_values = graph.get("nodes", []) if isinstance(graph, dict) else []
    for node in node_values:
        if not isinstance(node, dict):
            continue
        symbol = symbols.get(node.get("id"))
        if isinstance(symbol, dict) and isinstance(symbol.get("file_path"), str):
            paths.add(symbol["file_path"])
    for edge in edge_values:
        if not isinstance(edge, dict) or edge.get("namespace") == "loci":
            continue
        evidence = edge.get("evidence")
        if isinstance(evidence, dict) and isinstance(evidence.get("file"), str):
            paths.add(evidence["file"])
        for endpoint in (edge.get("from"), edge.get("to")):
            symbol = symbols.get(endpoint)
            if isinstance(symbol, dict) and isinstance(symbol.get("file_path"), str):
                paths.add(symbol["file_path"])
    return all(_repository_file_path_is_safe(repo_path, path) for path in paths)


def _repository_file_path_is_safe(repo_path: Path, value: str) -> bool:
    path = PurePosixPath(value)
    if (
        not value
        or "\\" in value
        or path.is_absolute()
        or ".." in path.parts
        or path.as_posix() != value
    ):
        return False
    candidate = repo_path / value
    if candidate.is_symlink():
        return False
    try:
        resolved = candidate.resolve(strict=True)
        resolved.relative_to(repo_path)
    except (OSError, ValueError):
        return False
    return resolved.is_file()


def _load_graph_context(
    repo_path: Path,
    *,
    ensure_fresh: bool,
) -> tuple[IndexStore, dict[str, dict[str, Any]], GraphIndexState]:
    store = get_store()
    if ensure_fresh:
        ensure_fresh_index(repo_path)
    index = _load_required_index(store, repo_path)
    indexed_nodes = {
        symbol["id"]: symbol
        for symbol in index.get("symbols", [])
        if isinstance(symbol, dict) and isinstance(symbol.get("id"), str)
    }
    graph_value = index.get("graph")
    if not isinstance(graph_value, dict):
        raise LociError(
            "INVALID_GRAPH_SCHEMA",
            "Persisted graph state is missing",
            {"repo": str(repo_path)},
        )
    try:
        state = GraphIndexState.from_dict(graph_value)
    except GraphContractError as exc:
        raise LociError(exc.code, exc.message, exc.details) from exc
    return store, indexed_nodes, state



def _graph_status(graph_state: GraphIndexState) -> str:
    if any(
        diagnostic.severity in {"warning", "error"}
        for diagnostic in graph_state.diagnostics
    ):
        return "degraded"
    return "healthy"


def _acquire_refresh_lock(lock_path: Path, timeout: float) -> None:
    deadline = time.monotonic() + timeout
    while True:
        try:
            fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            if time.monotonic() >= deadline:
                raise LociError(
                    "STALE_INDEX_REFRESH_FAILED",
                    "Timed out waiting for stale index refresh lock",
                    {"lock": str(lock_path), "timeout_seconds": timeout},
                )
            time.sleep(REFRESH_LOCK_POLL_SECONDS)
            continue
        with os.fdopen(fd, "w") as f:
            f.write(str(os.getpid()))
        return


def _iter_indexable_files(
    repo_path: Path,
    store: IndexStore,
) -> list[tuple[Path, str, str]]:
    gitignore = _load_gitignore(repo_path)
    files: list[tuple[Path, str, str]] = []
    for src_file in sorted(repo_path.rglob("*")):
        if not src_file.is_file():
            continue
        if any(part in SKIP_DIRS for part in src_file.parts):
            continue
        if _should_skip_file(src_file):
            continue

        rel_path = str(src_file.relative_to(repo_path))
        if gitignore and gitignore.match_file(rel_path):
            continue
        files.append((src_file, rel_path, store.hash_file(src_file)))
    return files


def _get_symbol(
    repo_path: Path,
    store: IndexStore,
    index: dict[str, Any],
    symbol_id: str,
    context: int,
) -> dict[str, Any]:
    meta = next((s for s in index["symbols"] if s["id"] == symbol_id), None)
    if meta is None:
        store.log_miss("get_not_found", repo_path=str(repo_path), symbol_id=symbol_id)
        raise LociError(
            "SYMBOL_NOT_FOUND",
            "Symbol not found",
            {"repo": str(repo_path), "symbol_id": symbol_id},
        )

    content = store.get_symbol_content(repo_path, symbol_id)
    if content is None:
        store.log_miss("get_not_found", repo_path=str(repo_path), symbol_id=symbol_id)
        raise LociError(
            "SYMBOL_NOT_FOUND",
            "Symbol source not found",
            {"repo": str(repo_path), "symbol_id": symbol_id},
        )

    symbol_bytes = len(content.encode("utf-8"))
    file_bytes = store.get_symbol_file_size(repo_path, symbol_id)
    if file_bytes is not None:
        search_id, search_rank = store.resolve_search_correlation(symbol_id, repo=str(repo_path))
        store.log_retrieval(
            symbol_id,
            symbol_bytes,
            file_bytes,
            repo_path=str(repo_path),
            kind=meta.get("kind"),
            language=meta.get("language"),
            search_id=search_id,
            search_rank=search_rank,
        )

    result: dict[str, Any] = {
        "id": symbol_id,
        "source": content,
        **{
            key: meta.get(key)
            for key in (
                "byte_offset",
                "byte_length",
                "line",
                "end_line",
                "signature",
                "kind",
                "language",
            )
        },
    }
    if meta.get("decorators"):
        result["decorators"] = meta["decorators"]
    if context > 0:
        symbol_context = store.get_symbol_context(repo_path, symbol_id, context)
        if symbol_context:
            result["context_before"] = symbol_context["context_before"]
            result["context_after"] = symbol_context["context_after"]
    return result


def _remap_markdown_hierarchy_ids(sym: Symbol, id_map: dict[str, str]) -> None:
    metadata = sym.metadata if isinstance(sym.metadata, dict) else {}
    markdown = metadata.get("markdown")
    if not isinstance(markdown, dict):
        return
    for key in ("parent_id", "root_id"):
        value = markdown.get(key)
        if isinstance(value, str) and value:
            markdown[key] = id_map.get(value, value)


def _add_markdown_retrieval_fields(entry: dict[str, Any], symbol: dict[str, Any]) -> None:
    metadata = symbol.get("metadata")
    markdown = metadata.get("markdown") if isinstance(metadata, dict) else None
    if not isinstance(markdown, dict):
        return
    for key in ("file_bytes", "saved_pct", "span_kind"):
        if key in markdown:
            entry[key] = markdown[key]


def _graph_node_ref(symbol: dict[str, Any]) -> dict[str, Any]:
    return GraphNodeRef(
        id=symbol["id"],
        namespace="loci",
        kind=symbol["kind"],
        attributes={
            "language": symbol["language"],
            "file": symbol["file_path"],
            "line": symbol.get("line", 0),
            "end_line": symbol.get("end_line", 0),
        },
    ).to_dict()


def _load_gitignore(repo_path: Path) -> "pathspec.PathSpec | None":
    gitignore = repo_path / ".gitignore"
    if not gitignore.exists():
        return None
    lines = gitignore.read_text(encoding="utf-8", errors="replace").splitlines()
    return pathspec.PathSpec.from_lines("gitwildmatch", lines)


def _should_skip_file(path: Path) -> bool:
    if path.name in SKIP_FILES:
        return True
    if path.suffix in SKIP_EXTENSIONS:
        return True
    if path.suffix not in EXTENSION_MAP:
        return True
    name = path.name
    if name.startswith("test_") or name.endswith("_test.py") or name.endswith("_test.go"):
        return True
    if any(name.endswith(suffix) for suffix in TEST_FILE_SUFFIXES):
        return True
    return False
