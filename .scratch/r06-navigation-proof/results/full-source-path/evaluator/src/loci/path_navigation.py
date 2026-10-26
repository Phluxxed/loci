"""Experimental graph-free path discovery from already delivered source only.

These are source acquisition candidates, never resolved imports or bindings.
The scheduler performs no I/O and imports no parser, graph, store, or evaluator.
"""
from __future__ import annotations

from pathlib import PurePosixPath
import posixpath
import re
from typing import Any

try:
    import tomllib
except ImportError:  # Python 3.10; already a project dependency.
    import tomli as tomllib


_WORDS = re.compile(r"\b[A-Za-z_][A-Za-z_0-9]*\b")
_STOP = frozenset("""abstract any as async await bool boolean break case catch char
class const continue def default delete dict do else enum except export extends
false finally float fn for from func function if impl import in int interface
is let list match mod module mut new None null number object of package pass
private protected pub public raise return self set static str string struct
super switch this throw trait true try type typeof undefined use var void while
with yield None True False""".split())
_CONTROLS = frozenset({"go.mod", "go.work", "Cargo.toml", "jsconfig.json", "tsconfig.json", "package.json"})
_JS = re.compile(
    r"\b(?:import|export)\s+(?:type\s+)?(?:[^;\"']*?\s+from\s*)?[\"']([^\"'\n]+)[\"']"
    r"|\b(?:require|import)\s*\(\s*[\"']([^\"'\n]+)[\"']\s*\)"
)
_RUST_MOD = re.compile(r"\b(?:pub(?:\s*\([^)]*\))?\s+)?mod\s+([A-Za-z_][A-Za-z_0-9]*)\s*;")
_RUST_PATH = re.compile(r"\b(?:use\s+)?(crate|self|super)((?:::[A-Za-z_][A-Za-z_0-9]*)+)")


def _join(base: str, relative: str) -> str | None:
    if not relative or relative.startswith("/") or "\\" in relative or "\x00" in relative:
        return None
    path = posixpath.normpath(posixpath.join(base, relative))
    return None if path == ".." or path.startswith("../") else path


def candidate_paths(file: str, text: str, files: dict) -> list[dict[str, str]]:
    """Return ordered admitted alternatives, without claiming module resolution.

    Relative JS import/export paths, Rust module/use paths, ancestor Cargo
    controls, and explicit Cargo local dependency paths are supported. Lexical
    matches may include comments or inactive configuration. Bare JS aliases,
    macro expansion, custom Rust target paths, and package resolution are not
    interpreted. Inventory membership bounds every emitted candidate.
    """
    source = PurePosixPath(file)
    parent = source.parent.as_posix()
    result: list[dict[str, str]] = []
    seen: set[str] = set()

    def add(path: str | None, reason: str) -> None:
        if path is not None and path in files and path not in seen:
            result.append({"path": path, "reason": reason, "observed_in": file})
            seen.add(path)

    if source.suffix in {".js", ".jsx", ".mjs", ".cjs", ".ts", ".tsx", ".mts", ".cts"}:
        for match in _JS.finditer(text):
            specifier = match.group(1) or match.group(2)
            if not specifier.startswith("."):
                continue
            path = _join(parent, specifier)
            add(path, "relative_import_or_export")
            if path is None:
                continue
            suffix = PurePosixPath(path).suffix
            # JS-written specifiers can refer to TS sources; retain all
            # admitted alternatives, rather than asserting a unique target.
            stem = path[:-len(suffix)] if suffix in {".js", ".jsx", ".mjs", ".cjs"} else path
            if not suffix or stem != path:
                for extension in (".ts", ".tsx", ".js", ".jsx", ".mts", ".mjs", ".cts", ".cjs"):
                    add(stem + extension, "relative_import_alternative")
            if not suffix:
                for extension in (".ts", ".tsx", ".js", ".jsx"):
                    add(_join(path, "index" + extension), "relative_directory_alternative")

    if source.suffix == ".rs":
        module_dir = parent if source.name in {"lib.rs", "main.rs", "mod.rs"} else str(source.with_suffix(""))
        for match in _RUST_MOD.finditer(text):
            path = _join(module_dir, match.group(1))
            add(path + ".rs" if path else None, "rust_module_declaration")
            add(path + "/mod.rs" if path else None, "rust_module_alternative")
        controls = [str(directory / "Cargo.toml") for directory in source.parents
                    if str(directory / "Cargo.toml") in files]
        crate_dir = str(PurePosixPath(controls[0]).parent / "src") if controls else None
        for match in _RUST_PATH.finditer(text):
            prefix, tail = match.groups()
            base = crate_dir if prefix == "crate" else module_dir
            if prefix == "super":
                base = posixpath.dirname(module_dir)
            if base is None:
                continue
            parts = tail.split("::")[1:]
            for depth in range(1, len(parts) + 1):
                path = _join(base, "/".join(parts[:depth]))
                add(path + ".rs" if path else None, "rust_use_path_candidate")
                add(path + "/mod.rs" if path else None, "rust_use_path_alternative")
        for control in controls:
            add(control, "rust_ancestor_control")

    if source.name == "Cargo.toml":
        try:
            value = tomllib.loads(text)
        except tomllib.TOMLDecodeError:
            value = {}
        tables: list[dict[str, Any]] = [value]
        workspace = value.get("workspace", {})
        if isinstance(workspace, dict):
            tables.append(workspace)
        target = value.get("target", {})
        if isinstance(target, dict):
            tables.extend(table for table in target.values() if isinstance(table, dict))
        for table in tables:
            for key in ("dependencies", "dev-dependencies", "build-dependencies"):
                dependencies = table.get(key, {})
                if not isinstance(dependencies, dict):
                    continue
                for dependency in dependencies.values():
                    if not isinstance(dependency, dict) or not isinstance(dependency.get("path"), str):
                        continue
                    path = _join(parent, dependency["path"])
                    if path is not None:
                        # Conventional entries are alternatives visible in the
                        # inventory; target existence does not prove a binding.
                        add(_join(path, "src/lib.rs"), "cargo_local_path_source_candidate")
                        add(_join(path, "src/main.rs"), "cargo_local_path_source_candidate")
                        add(_join(path, "Cargo.toml"), "cargo_local_path_control")
        for directory in source.parents:
            add(str(directory / "Cargo.toml"), "cargo_ancestor_control")
    return result


def _sources(packets: list[dict]) -> list[dict]:
    sources = []
    for packet in packets:
        payload = packet.get("structuredContent", packet.get("structured_content", packet))
        sources.extend([payload["source"]] if "source" in payload else payload.get("sources", []))
    return sources


def _texts(spans: list[dict]) -> list[tuple[str, str]]:
    """Join only contiguous delivered bytes, including imports split by pages."""
    by_file: dict[str, list[dict]] = {}
    for span in spans:
        by_file.setdefault(span["file"], []).append(span)
    texts = []
    for file, parts in by_file.items():
        end = None
        content = b""
        for span in sorted(parts, key=lambda s: (s["start_byte"], s["end_byte"])):
            raw = span["content"].encode("utf-8")
            left, right = span["start_byte"], span["end_byte"]
            if end is None or left > end:
                if end is not None:
                    texts.append((file, content.decode("utf-8")))
                end, content = right, raw
            elif right > end:
                content += raw[end - left:]
                end = right
        if end is not None:
            texts.append((file, content.decode("utf-8")))
    return texts


def _complete(spans: list[dict], file: str, size: int) -> bool:
    end = 0
    for span in sorted((s for s in spans if s["file"] == file), key=lambda s: s["start_byte"]):
        if span["start_byte"] > end:
            return False
        end = max(end, span["end_byte"])
    return end >= size


def choose_next_query(inventory: dict, packets: list[dict], asked: list[str]) -> dict:
    """Replayable next query plus provenance and non-I/O work counters.

    Source-byte scan counters count bytes presented to each scheduler pass;
    they are not filesystem bytes or estimates of regex engine operations.
    Timing/CPU for this function must be charged by its caller.
    """
    spans = _sources(packets)
    files = inventory["files"]
    observed = list(dict.fromkeys(s["file"] for s in spans))
    work = {"inventory_paths_available": len(files), "source_spans_received": len(spans),
            "source_bytes_received": sum(len(s["content"].encode("utf-8")) for s in spans),
            "source_bytes_path_scan": 0, "source_bytes_lexical_scan": 0,
            "candidate_paths_generated": 0, "filesystem_source_bytes_read": 0}

    def result(query, reason, observed_in=None):
        return {"query": query, "reason": reason, "observed_in": observed_in, "work": work}

    for name in observed:
        size = files.get(name, {}).get("size")
        if name not in asked and type(size) is int and size and not _complete(spans, name, size):
            return result(name, "expand_delivered_file", name)
    texts = _texts(spans)
    for file, text in texts:
        work["source_bytes_path_scan"] += len(text.encode("utf-8"))
        candidates = candidate_paths(file, text, files)
        work["candidate_paths_generated"] += len(candidates)
        for candidate in candidates:
            name = candidate["path"]
            if name not in asked and name not in observed:
                return result(name, candidate["reason"], file)
    # Frozen R0.4 lexical fallback, expressed locally to keep this candidate
    # independent of evaluator imports and context gold.
    for source in spans:
        text = source["content"]
        work["source_bytes_lexical_scan"] += len(text.encode("utf-8"))
        words = set(_WORDS.findall(text))
        for name in sorted(files):
            path = PurePosixPath(name)
            mentioned = name in text or path.name in text or (len(path.stem) > 2 and path.stem in words)
            ancestor = path.name in _CONTROLS and path.parent in PurePosixPath(source["file"]).parents
            if name not in asked and name not in observed and (mentioned or ancestor):
                return result(name, "lexical_path_or_control", source["file"])
    for source in spans:
        work["source_bytes_lexical_scan"] += len(source["content"].encode("utf-8"))
        for word in _WORDS.findall(source["content"]):
            if len(word) >= 3 and word not in _STOP and word not in asked:
                return result(word, "lexical_identifier", source["file"])
    return result(None, "discovery_exhausted")


def next_acquisition_query(inventory: dict, packets: list[dict], asked: list[str]) -> str | None:
    return choose_next_query(inventory, packets, asked)["query"]
