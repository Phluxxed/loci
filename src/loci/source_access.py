"""Integrity-bound projection of the validated index needed for exact reads.

This is derived local state, not an authorization credential. A missing or
mismatched projection requires the ordinary semantic-index path.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path, PurePosixPath
import re
from typing import Any, Mapping, TYPE_CHECKING

from loci.graph.contracts import GRAPH_STATE_SCHEMA_VERSION

if TYPE_CHECKING:
    from loci.graph.state import GraphIndexState


SCHEMA_VERSION = 1


def control_files(state: GraphIndexState) -> set[str]:
    paths = {path for path in state.input_hashes
             if PurePosixPath(path).name in {"go.mod", "go.work", "Cargo.toml", "Package.swift"}}
    for record in (*state.imports, *state.symbol_references, *state.calls, *state.type_relations):
        paths.update(getattr(record, "resolution_control_files", ()))
        paths.update(control.file for control in getattr(record, "resolution_controls", ()))
    return paths


def active_paths(index: Mapping[str, Any]) -> set[str]:
    """The same extension paths checked by normal repository freshness."""
    graph = index.get("graph")
    edges = graph.get("edges", []) if isinstance(graph, dict) else []
    symbols = {symbol.get("id"): symbol for symbol in index.get("symbols", [])
               if isinstance(symbol, dict) and isinstance(symbol.get("id"), str)}
    paths: set[str] = set()
    for node in graph.get("nodes", []) if isinstance(graph, dict) else []:
        if not isinstance(node, dict):
            continue
        symbol = symbols.get(node.get("id"))
        if isinstance(symbol, dict) and isinstance(symbol.get("file_path"), str):
            paths.add(symbol["file_path"])
    for edge in edges:
        if not isinstance(edge, dict) or edge.get("namespace") == "loci":
            continue
        evidence = edge.get("evidence")
        if isinstance(evidence, dict) and isinstance(evidence.get("file"), str):
            paths.add(evidence["file"])
        for endpoint in (edge.get("from"), edge.get("to")):
            symbol = symbols.get(endpoint)
            if isinstance(symbol, dict) and isinstance(symbol.get("file_path"), str):
                paths.add(symbol["file_path"])
    return paths


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, ensure_ascii=False,
                      separators=(",", ":"), allow_nan=False).encode("utf-8")


def source_index(index: dict, state: GraphIndexState) -> dict:
    return {**{key: index[key] for key in (
        "schema_version", "extractor_version", "graph_resolver_version", "repo_path", "file_hashes")},
        "coverage": index.get("coverage"),
        "graph": {"schema_version": state.schema_version, "input_hashes": dict(state.input_hashes)},
        "resolver_control_files": sorted(control_files(state)),
        "active_paths": sorted(active_paths(index))}


def source_digest(source: dict) -> str:
    payload = {"schema_version": SCHEMA_VERSION, "source_index": source}
    return hashlib.sha256(_canonical(payload)).hexdigest()


def projection(source: dict, index_bytes: bytes) -> dict:
    value = {"schema_version": SCHEMA_VERSION,
             "index_sha256": hashlib.sha256(index_bytes).hexdigest(),
             "source_index": source}
    return {**value, "checksum": hashlib.sha256(_canonical(value)).hexdigest()}


def _relative(value: Any) -> bool:
    if not isinstance(value, str) or not value or "\\" in value:
        return False
    path = PurePosixPath(value)
    return not path.is_absolute() and ".." not in path.parts and path.as_posix() == value


def _hashes(value: Any) -> bool:
    return isinstance(value, dict) and all(_relative(path) and isinstance(digest, str)
               and re.fullmatch(r"[0-9a-f]{64}", digest) for path, digest in value.items())


def load_projection(path: Path, index_path: Path, repo_identity: str) -> dict | None:
    """Accept only a complete matching generation, otherwise use legacy loading."""
    try:
        value = json.loads(path.read_bytes())
        if not isinstance(value, dict) or set(value) != {
            "schema_version", "index_sha256", "source_index", "checksum",
        }:
            return None
        checksum = value.pop("checksum")
        if (type(value["schema_version"]) is not int
                or value["schema_version"] != SCHEMA_VERSION
                or checksum != hashlib.sha256(_canonical(value)).hexdigest()):
            return None
        source = value["source_index"]
        keys = {"schema_version", "extractor_version", "graph_resolver_version", "repo_path",
                "file_hashes", "coverage", "graph", "resolver_control_files", "active_paths"}
        if not isinstance(source, dict) or set(source) != keys or source["repo_path"] != repo_identity:
            return None
        if any(type(source[key]) is not int for key in ("schema_version", "extractor_version", "graph_resolver_version")):
            return None
        if (not _hashes(source["file_hashes"]) or not isinstance(source["graph"], dict)
                or set(source["graph"]) != {"schema_version", "input_hashes"}
                or type(source["graph"]["schema_version"]) is not int
                or source["graph"]["schema_version"] != GRAPH_STATE_SCHEMA_VERSION
                or not _hashes(source["graph"]["input_hashes"])):
            return None
        for key in ("resolver_control_files", "active_paths"):
            paths = source[key]
            if not isinstance(paths, list) or not all(_relative(p) for p in paths) or len(paths) != len(set(paths)):
                return None
        if not set(source["resolver_control_files"]).issubset(source["graph"]["input_hashes"]):
            return None
        digest = hashlib.sha256()
        # The projection digest lives inside the actual validated index. A
        # self-checksummed sidecar alone must never grant new source eligibility.
        footer = b'\n  "source_access_sha256": "' + source_digest(source).encode("ascii") + b'"\n}'
        tail = b""
        before = index_path.stat()
        with index_path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
                tail = (tail + chunk)[-len(footer):]
        after = index_path.stat()
        unchanged = (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns, before.st_ctime_ns) == (
            after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns)
        if not unchanged or digest.hexdigest() != value["index_sha256"] or tail != footer:
            return None
        return source
    except (OSError, ValueError, TypeError, KeyError, UnicodeError, RecursionError):
        return None
