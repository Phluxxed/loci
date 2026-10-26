"""Independent, fail-closed proof check for demand import relationships.

The frozen semantic scorers intentionally exclude structural imports. This
observer checks a claimed structural edge against the candidate's serialized
native ImportRecord and the actual relation-linked source. It does not infer
semantic type/call credit or construct missing graph edges.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
import hashlib
from pathlib import Path
import tomllib
from typing import Any

from benchmarks import multilingual_context_relationships as proof


_STRUCTURAL = frozenset({"imports", "imports_type"})
_SUPPORTED = frozenset({"javascript", "typescript", "rust"})


def _payload(packet: Mapping[str, Any]) -> Mapping[str, Any]:
    value = packet.get("structuredContent", packet)
    if not isinstance(value, Mapping):
        raise ValueError("structural packet is malformed")
    return value


def _source(repo: Path, file: Any) -> bytes:
    # The independent scorer owns source-byte validation. Refuse symlinked
    # components as well as paths that leave the frozen snapshot.
    if not isinstance(file, str):
        raise ValueError("structural source path is missing")
    relative = Path(file)
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError("structural source path escapes snapshot")
    current = repo
    for part in relative.parts:
        current = current / part
        if current.is_symlink():
            raise ValueError("structural source path is linked")
    return proof._source_bytes(repo, file)


def _line(data: bytes, line: Any) -> tuple[int, int]:
    interval = proof._line_interval(data, line)
    if interval is None:
        raise ValueError("structural declaration line is invalid")
    return interval


def _declaration(repo: Path, raw: Mapping[str, Any]) -> tuple[str, int, int]:
    file = raw.get("source_file")
    data = _source(repo, file)
    if hashlib.sha256(data).hexdigest() != raw.get("source_hash"):
        raise ValueError("structural declaration hash differs from snapshot")
    start, end = _line(data, raw.get("line"))
    text = raw.get("text")
    if not isinstance(text, str) or not text:
        raise ValueError("structural declaration text is missing")
    encoded = text.encode("utf-8")
    at = data.find(encoded, start)
    if at < start or at > end:
        raise ValueError("structural declaration text differs from snapshot")
    # Multiline declarations must be present in full, not just their first line.
    return file, min(start, at), max(end, at + len(encoded))


def _controls(index: Mapping[str, Any], record: Mapping[str, Any], repo: Path) -> list[tuple[str, int, int]]:
    graph = index.get("graph", {})
    hashes = graph.get("input_hashes", {}) if isinstance(graph, Mapping) else {}
    if not isinstance(hashes, Mapping):
        raise ValueError("structural control hashes are unavailable")
    files = record.get("resolution_control_files")
    if not isinstance(files, list):
        raise ValueError("structural resolution controls are malformed")
    if record["raw"].get("language") == "rust":
        required: set[str] = set()
        for path in (record["raw"].get("source_file"), record.get("target_file")):
            if isinstance(path, str):
                current = Path(path).parent
                while True:
                    candidate = (current / "Cargo.toml").as_posix()
                    if (repo / candidate).is_file():
                        required.add(candidate)
                        break
                    if current == Path("."):
                        break
                    current = current.parent
        target = next((item for item in index.get("symbols", [])
                       if isinstance(item, Mapping) and item.get("id") == record.get("target_id")), None)
        metadata = target.get("metadata", {}).get("loci", {}) if isinstance(target, Mapping) else {}
        if record.get("target_kind") == "crate" and isinstance(metadata.get("manifest"), str):
            required.add(metadata["manifest"])
        if record.get("resolution_basis") == "cargo_workspace_dependency":
            required.add("Cargo.toml")
        if not required or not required.issubset(set(files)):
            raise ValueError("Rust native record omits required Cargo controls")
    intervals = []
    for file in files:
        data = _source(repo, file)
        if not data or hashlib.sha256(data).hexdigest() != hashes.get(file):
            raise ValueError("structural resolution control hash differs from snapshot")
        intervals.append((file, 0, len(data)))
    return intervals


def _rust_possible(record: Mapping[str, Any], repo: Path) -> bool:
    raw = record["raw"]
    rust = raw.get("rust")
    if not isinstance(rust, Mapping):
        raise ValueError("Rust import has no configuration observation")
    if rust.get("configuration") == "declared_possible":
        return True
    if "declared_possible" in rust.get("lexical_module_configurations", []):
        return True
    alias = raw.get("specifier", "").split("::", 1)[0]
    for file in record.get("resolution_control_files", []):
        if not isinstance(file, str) or Path(file).name != "Cargo.toml":
            continue
        try:
            cargo = tomllib.loads(_source(repo, file).decode("utf-8"))
        except (UnicodeError, tomllib.TOMLDecodeError) as exc:
            raise ValueError("Rust Cargo control cannot be parsed") from exc
        workspace = cargo.get("workspace")
        targets = cargo.get("target")
        dependencies = [cargo.get("dependencies", {}), cargo.get("dev-dependencies", {}),
                        cargo.get("build-dependencies", {}),
                        workspace.get("dependencies", {}) if isinstance(workspace, Mapping) else {}]
        for target in targets.values() if isinstance(targets, Mapping) else ():
            if isinstance(target, Mapping):
                dependencies.extend(target.get(key, {}) for key in
                                    ("dependencies", "dev-dependencies", "build-dependencies"))
        for group in dependencies:
            entry = group.get(alias) if isinstance(group, Mapping) else None
            if isinstance(entry, Mapping) and entry.get("optional") is True:
                return True
    return False


def _rust_ancestors(index: Mapping[str, Any], record: Mapping[str, Any], repo: Path) -> list[tuple[str, int, int]]:
    imports = index["graph"].get("imports", [])
    pending = [name for name in (record["raw"].get("source_file"), record.get("target_file"))
               if isinstance(name, str)]
    roots = {metadata["crate_root"] for item in index.get("symbols", [])
             if isinstance(item, Mapping) and item.get("kind") == "crate"
             for metadata in [item.get("metadata", {}).get("loci", {})]
             if isinstance(metadata, Mapping) and isinstance(metadata.get("crate_root"), str)}
    if not roots:
        raise ValueError("Rust crate root evidence is unavailable")
    seen: set[str] = set()
    intervals = []
    while pending:
        file = pending.pop(0)
        if file in seen:
            continue
        seen.add(file)
        parents = [item for item in imports if isinstance(item, Mapping)
                   and item.get("status") == "resolved" and item.get("target_file") == file
                   and isinstance(item.get("raw"), Mapping)
                   and isinstance(item["raw"].get("rust"), Mapping)
                   and item["raw"]["rust"].get("kind") == "module"]
        if len(parents) > 1:
            raise ValueError("Rust module ancestry is ambiguous")
        if not parents and file not in roots:
            raise ValueError("Rust module ancestry is incomplete")
        for parent in parents:
            intervals.append(_declaration(repo, parent["raw"]))
            pending.append(parent["raw"]["source_file"])
    return intervals


def _check_scope(index: Mapping[str, Any], record: Mapping[str, Any]) -> None:
    if record["raw"].get("language") != "rust":
        return
    scope = index.get("semantic_scope")
    if not isinstance(scope, Mapping):
        raise ValueError("Rust semantic closure scope is unavailable")
    for key in ("inventory_incomplete", "rust_closure_incomplete", "source_stale",
                "parse_limit", "import_closure_limit"):
        if scope.get(key):
            raise ValueError("Rust structural binding domain is incomplete: " + key)
    incomplete = scope.get("incomplete_reexport_files", [])
    if not isinstance(incomplete, (list, tuple)):
        raise ValueError("Rust reexport closure scope is malformed")
    if record["raw"].get("source_file") in incomplete or record.get("target_file") in incomplete:
        raise ValueError("Rust reexport route is incomplete")
    parsed = scope.get("parsed_paths")
    if not isinstance(parsed, list) or any(
        file not in parsed for file in (record["raw"].get("source_file"), record.get("target_file"))
        if isinstance(file, str)
    ):
        raise ValueError("Rust import endpoint extraction is incomplete")


def _endpoint(index: Mapping[str, Any], record: Mapping[str, Any], repo: Path) -> None:
    target_id = record.get("target_id")
    symbols = index.get("symbols", [])
    if not isinstance(symbols, list) or not any(
        isinstance(item, Mapping) and item.get("id") == target_id for item in symbols
    ):
        raise ValueError("structural target endpoint is not indexed")
    target_file = record.get("target_file")
    if isinstance(target_file, str):
        hashes = index.get("file_hashes", {})
        data = _source(repo, target_file)
        if not isinstance(hashes, Mapping) or hashes.get(target_file) != hashlib.sha256(data).hexdigest():
            raise ValueError("structural target file hash differs from snapshot")
        if not any(isinstance(item, Mapping) and item.get("id") == target_id
                   and item.get("file_path") == target_file
                   and item.get("content_hash") == hashes[target_file] for item in symbols):
            raise ValueError("structural target file node differs from record")


def _check_claim(index: Mapping[str, Any], payload: Mapping[str, Any],
                 relation: Mapping[str, Any], repo: Path) -> None:
    edge = relation.get("edge")
    if not isinstance(edge, Mapping) or edge.get("type") not in _STRUCTURAL:
        raise ValueError("structural edge is malformed")
    graph = index.get("graph")
    if (not isinstance(graph, Mapping) or edge not in graph.get("edges", [])
            or edge.get("namespace") != "loci" or edge.get("directed") is not True
            or edge.get("resolution") != "import-resolved"):
        raise ValueError("structural edge is not a native indexed import")
    imports = graph.get("imports", [])
    if not isinstance(imports, list):
        raise ValueError("native import records are unavailable")
    evidence = edge.get("evidence", {})
    matched = [record for record in imports if isinstance(record, Mapping)
               and record.get("status") == "resolved"
               and record.get("source_id") == edge.get("from")
               and record.get("target_id") == edge.get("to")
               and isinstance(record.get("raw"), Mapping)
               and ("imports_type" if record["raw"].get("type_only") else "imports") == edge.get("type")
               and record["raw"].get("source_file") == evidence.get("file")
               and record["raw"].get("line") == evidence.get("line")
               and record["raw"].get("source_hash") == evidence.get("content_hash")]
    if len(matched) != 1:
        raise ValueError("structural edge has no unique exact native import record")
    record = matched[0]
    language = record["raw"].get("language")
    if language not in _SUPPORTED:
        raise ValueError("structural language has no supported proof rule")
    if relation.get("resolution_configuration") != record.get("resolution_configuration"):
        raise ValueError("structural resolution configuration differs from record")
    _check_scope(index, record)
    _endpoint(index, record, repo)
    intervals = [_declaration(repo, record["raw"]), *_controls(index, record, repo)]
    if language == "rust":
        if _rust_possible(record, repo) and record.get("resolution_configuration") != "declared_possible":
            raise ValueError("Rust possible configuration was promoted to unconditional")
        intervals.extend(_rust_ancestors(index, record, repo))
    by_id = {item.get("id"): item for item in payload.get("sources", [])
             if isinstance(item, Mapping)}
    ids = relation.get("source_ids")
    if not isinstance(ids, list) or not ids or any(value not in by_id for value in ids):
        raise ValueError("structural claim lacks relation-linked sources")
    spans = []
    for value in ids:
        source = by_id[value]
        file = source.get("file")
        data = _source(repo, file)
        if source.get("content_hash") != hashlib.sha256(data).hexdigest():
            raise ValueError("structural proof source hash differs from snapshot")
        spans.append(proof._validate_span(source, repo))
    if not proof._covers(spans, list(dict.fromkeys(intervals))):
        raise ValueError("complete structural import support is not relation-linked")


def validate_structural(index: Mapping[str, Any], packets: Sequence[Mapping[str, Any]],
                        repo: str | Path) -> list[dict[str, Any]]:
    """Return violations for every demand structural claim; [] means all pass.

    Only demand packets are examined. Legacy graph packet status and frozen
    nonstructural scorers remain unchanged. Unknown or unjoined claims fail.
    """
    root = Path(repo).resolve()
    violations = []
    for packet_no, packet in enumerate(packets):
        payload = _payload(packet)
        if payload.get("policy") != "demand-semantic-v1":
            continue
        for relation in payload.get("relationships", []):
            if not isinstance(relation, Mapping):
                continue  # Outer packet shape is checked by architecture_cases.
            edge = relation.get("edge")
            if not isinstance(edge, Mapping) or edge.get("type") not in _STRUCTURAL:
                continue
            try:
                _check_claim(index, payload, relation, root)
            except (AttributeError, KeyError, TypeError, ValueError, OSError) as exc:
                violations.append({"packet": packet_no, "relationship": relation.get("id"),
                                   "edge": dict(edge), "reason": str(exc)})
    return violations
