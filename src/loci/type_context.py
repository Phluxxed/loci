"""Bounded source delivery over existing, resolved imported-type references."""

from __future__ import annotations

import hashlib
import json
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from .graph.state import GraphIndexState
from .storage.index_store import IndexStore


SCOPE = "existing_imported_type_references"
RESERVED_OUTPUT_BYTES = 1024
_REASONS = (
    "no_anchor", "anchor_limit", "nested_owner", "ambiguous_owner",
    "unresolved_reference", "edge_unavailable", "unsupported_target",
    "source_unavailable", "node_limit", "neighbor_limit", "reference_limit",
    "hop_limit", "source_bytes", "source_spans", "serialized_bytes", "root_budget",
)


@dataclass(frozen=True)
class TypeContextLimits:
    max_anchors: int = 5
    max_hops: int = 3
    max_nodes: int = 32
    max_neighbors_per_owner: int = 16
    max_references: int = 16
    max_source_spans: int = 64
    max_source_bytes: int = 16_384
    max_serialized_bytes: int = 32_768

    def __post_init__(self) -> None:
        for name, value in asdict(self).items():
            if type(value) is not int or value < 0:
                raise ValueError(f"{name} must be a nonnegative integer")


def empty_type_context(
    *, reason: str, unavailable: bool = False,
    limits: TypeContextLimits = TypeContextLimits(),
) -> dict[str, Any]:
    return {
        "scope": SCOPE,
        "status": "unavailable" if unavailable else "partial",
        "symbols": [], "references": [], "evidence": [],
        "limits": asdict(limits), "omissions": {reason: 1},
    }


def _real_declaration(symbol: dict[str, Any]) -> bool:
    if symbol.get("kind") in {"file", "package", "crate", "module"}:
        return False
    if symbol.get("language") == "markdown":
        return False
    metadata = symbol.get("metadata", {}).get("loci", {})
    if not isinstance(metadata, dict):
        metadata = {}
    if any(metadata.get(key) is True for key in
           ("file_node", "go_package", "rust_crate", "swift_module_node")):
        return False
    return (type(symbol.get("byte_offset")) is int
            and type(symbol.get("byte_length")) is int
            and symbol["byte_offset"] >= 0 and symbol["byte_length"] > 0)


def _contains(symbol: dict[str, Any], start: int, end: int) -> bool:
    return symbol["byte_offset"] <= start < end <= symbol["byte_offset"] + symbol["byte_length"]


def _source_cost(symbols: list[dict], evidence: list[dict]) -> tuple[int, int]:
    """Count delivered occurrences, including repeated literal signatures."""
    texts = [span["content"] for span in evidence]
    for symbol in symbols:
        source = symbol.get("source", "")
        if source:
            texts.append(source)
        signature = symbol.get("signature")
        if signature and signature in source:
            texts.append(signature)
        texts.extend(symbol.get("context_before", []))
        texts.extend(symbol.get("context_after", []))
    return sum(len(text.encode("utf-8")) for text in texts), len(texts)


def _wire_bytes(value: dict) -> int:
    return len(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8"))


class _CachedSource:
    def __init__(self, repo: Path, store: IndexStore):
        self.repo = repo
        self.store = store
        self.files: dict[str, tuple[bytes, str, list[bytes]]] = {}

    def file(self, path: str, expected_hash: str | None = None) -> tuple[bytes, list[bytes]]:
        if path not in self.files:
            result = self.store.get_file_content(self.repo, path)
            if result is None:
                raise ValueError("cached source is missing")
            raw = result["content"].encode("utf-8")
            self.files[path] = (raw, hashlib.sha256(raw).hexdigest(), raw.splitlines(keepends=True))
        raw, digest, lines = self.files[path]
        if expected_hash is not None and digest != expected_hash:
            raise ValueError("cached source hash differs from reference evidence")
        return raw, lines

    def symbol(self, meta: dict) -> dict:
        raw, _ = self.file(meta["file_path"])
        start, length = meta["byte_offset"], meta["byte_length"]
        source = raw[start:start + length]
        if len(source) != length or hashlib.sha256(source).hexdigest() != meta["content_hash"]:
            raise ValueError("cached definition differs from its indexed source span")
        result = {"id": meta["id"], "source": source.decode("utf-8")}
        result.update({key: meta.get(key) for key in
                       ("byte_offset", "byte_length", "line", "end_line", "signature", "kind", "language")})
        if meta.get("decorators"):
            result["decorators"] = meta["decorators"]
        return result

    def support(self, support) -> dict:
        _, lines = self.file(support.file, support.content_hash)
        if not 1 <= support.line <= len(lines):
            raise ValueError("support line is outside cached source")
        return {
            "file": support.file, "start_line": support.line, "end_line": support.line,
            "byte_offset": sum(map(len, lines[:support.line - 1])),
            "content": lines[support.line - 1].decode("utf-8"),
            "content_hash": support.content_hash,
        }


def expand_type_context(
    repo_path: Path,
    store: IndexStore,
    indexed_nodes: dict[str, dict[str, Any]],
    graph_state: GraphIndexState,
    root_symbols: list[dict[str, Any]],
    *,
    limits: TypeContextLimits = TypeContextLimits(),
) -> dict[str, Any]:
    """Select owned reference records, preserving their original graph edges."""
    result: dict[str, Any] = {
        "scope": SCOPE, "status": "complete", "symbols": [], "references": [],
        "evidence": [], "limits": asdict(limits), "omissions": {},
    }
    omissions: Counter[str] = Counter()
    declarations = {key: node for key, node in indexed_nodes.items() if _real_declaration(node)}
    roots = sorted({item["id"] for item in root_symbols if item["id"] in declarations})
    if not roots or limits.max_anchors == 0:
        return empty_type_context(reason="no_anchor", limits=limits)
    if len(roots) > limits.max_anchors:
        omissions["anchor_limit"] += len(roots) - limits.max_anchors
    selected = roots[:limits.max_anchors]
    delivered = {symbol["id"]: symbol for symbol in root_symbols}
    visited = set(roots)
    scheduled = set(selected)

    def exhausted(candidate: dict, *, reserve_omissions: bool = True) -> str | None:
        source_bytes, source_spans = _source_cost(root_symbols + candidate["symbols"], candidate["evidence"])
        if source_bytes > limits.max_source_bytes:
            return "source_bytes"
        if source_spans > limits.max_source_spans:
            return "source_spans"
        # Reserve a bounded worst-case omission map before admitting a bundle.
        envelope = dict(candidate)
        if reserve_omissions:
            envelope["omissions"] = {reason: 2_147_483_647 for reason in _REASONS}
            envelope["status"] = "partial"
        if _wire_bytes({"symbols": root_symbols, "type_context": envelope}) + RESERVED_OUTPUT_BYTES > limits.max_serialized_bytes:
            return "serialized_bytes"
        return None

    root_limit = exhausted(result)
    if root_limit or len(visited) > limits.max_nodes:
        result["status"] = "partial"
        result["omissions"] = {"root_budget": 1, root_limit or "node_limit": 1}
        return result

    nodes_by_file: dict[str, list[dict]] = defaultdict(list)
    for node in declarations.values():
        nodes_by_file[node["file_path"]].append(node)
    records_by_file: dict[str, list] = defaultdict(list)
    for record in graph_state.symbol_references:
        if any(binding.type_only for binding in record.raw.candidate_bindings):
            records_by_file[record.raw.source_file].append(record)
    for records in records_by_file.values():
        records.sort(key=lambda record: (record.raw.start_byte, record.raw.end_byte, record.target_id or ""))
    edges = {(edge.from_id, edge.to_id): edge for edge in graph_state.edges
             if edge.namespace == "loci" and edge.type == "references_type"
             and edge.resolution == "import-resolved" and edge.directed}
    source = _CachedSource(repo_path, store)
    evidence_keys: set[tuple[str, int]] = set()
    reference_keys: set[tuple[str, str]] = set()
    frontier = selected

    def source_covers(span: dict, symbols: dict[str, dict]) -> bool:
        start = span["byte_offset"]
        end = start + len(span["content"].encode("utf-8"))
        return any(indexed_nodes[key]["file_path"] == span["file"]
                   and _contains(indexed_nodes[key], start, end)
                   for key in symbols if key in declarations)

    for depth in range(limits.max_hops + 1):
        following: set[str] = set()
        for owner_id in sorted(frontier):
            owner = declarations[owner_id]
            candidates = []
            owner_targets: set[str] = set()
            for record in records_by_file.get(owner["file_path"], []):
                raw = record.raw
                if not _contains(owner, raw.start_byte, raw.end_byte):
                    continue
                containers = [node for node in nodes_by_file[raw.source_file]
                              if _contains(node, raw.start_byte, raw.end_byte)]
                minimum = min(node["byte_length"] for node in containers)
                narrowest = [node for node in containers if node["byte_length"] == minimum]
                if len(narrowest) != 1:
                    omissions["ambiguous_owner"] += 1
                    continue
                if narrowest[0]["id"] != owner_id:
                    omissions["nested_owner"] += 1
                    continue
                if record.status != "resolved" or record.binding is None or not record.binding.type_only:
                    omissions["unresolved_reference"] += 1
                    continue
                target_id = record.target_id
                if target_id not in declarations:
                    omissions["unsupported_target"] += 1
                    continue
                if (record.source_id, target_id) not in edges:
                    omissions["edge_unavailable"] += 1
                    continue
                if target_id in owner_targets or (owner_id, target_id) in reference_keys:
                    continue
                owner_targets.add(target_id)
                candidates.append(record)
            if depth == limits.max_hops:
                omissions["hop_limit"] += len(candidates)
                continue
            omissions["neighbor_limit"] += max(0, len(candidates) - limits.max_neighbors_per_owner)
            for record in candidates[:limits.max_neighbors_per_owner]:
                target_id = record.target_id
                if len(result["references"]) >= limits.max_references:
                    omissions["reference_limit"] += 1
                    continue
                if target_id not in visited and len(visited) >= limits.max_nodes:
                    omissions["node_limit"] += 1
                    continue
                raw = record.raw
                try:
                    cached, _ = source.file(raw.source_file, raw.source_hash)
                    if cached[raw.start_byte:raw.end_byte].decode("utf-8") != raw.text:
                        raise ValueError("reference does not match cached source")
                    owner_source = delivered[owner_id]
                    owner_start = owner_source["byte_offset"]
                    if owner_source["source"].encode("utf-8") != cached[owner_start:owner_start + owner_source["byte_length"]]:
                        raise ValueError("owner source does not match reference cache")
                    target = source.symbol(declarations[target_id])
                    if target_id in delivered and delivered[target_id]["source"] != target["source"]:
                        raise ValueError("already delivered target differs from cache")
                    supported = {**delivered, target_id: target}
                    added_evidence = {}
                    for support in record.support:
                        span = source.support(support)
                        key = (span["file"], span["start_line"])
                        if key not in evidence_keys and not source_covers(span, supported):
                            added_evidence[key] = span
                except (ValueError, UnicodeError, KeyError):
                    omissions["source_unavailable"] += 1
                    continue
                reference = {
                    "owner_id": owner_id, "target_id": target_id,
                    "reference": {"file": raw.source_file, "start_byte": raw.start_byte, "end_byte": raw.end_byte},
                    "edge": edges[(record.source_id, target_id)].to_dict(),
                    "support": [support.to_dict() for support in record.support],
                }
                added_symbols = [] if target_id in delivered else [target]
                candidate = {**result,
                             "symbols": result["symbols"] + added_symbols,
                             "references": result["references"] + [reference],
                             "evidence": result["evidence"] + [added_evidence[key] for key in sorted(added_evidence)]}
                reason = exhausted(candidate)
                if reason:
                    omissions[reason] += 1
                    continue
                result = candidate
                delivered[target_id] = target
                reference_keys.add((owner_id, target_id))
                evidence_keys.update(added_evidence)
                visited.add(target_id)
                if target_id not in scheduled:
                    scheduled.add(target_id)
                    following.add(target_id)
                if added_symbols:
                    file_bytes = store.get_symbol_file_size(repo_path, target_id)
                    if file_bytes is not None:
                        store.log_retrieval(target_id, len(target["source"].encode("utf-8")), file_bytes,
                                            repo_path=str(repo_path), kind=target["kind"], language=target["language"])
        frontier = sorted(following)
        if not frontier:
            break
    result["omissions"] = {reason: count for reason, count in sorted(omissions.items()) if count}
    result["status"] = "partial" if result["omissions"] else "complete"
    return result
