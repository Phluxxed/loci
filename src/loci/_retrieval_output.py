"""Deterministic atomic packing for normal retrieval responses."""
from __future__ import annotations

from collections import Counter
import copy
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Sequence

from ._exploration_output import Span, _evidence_bytes, _validate_span
from .graph.contracts import GraphContractError, GraphEdge
from .retrieval_io import finalize_response, serialize_source, source_ref


LIMITS = {
    "max_hops": 2,
    "max_nodes": 64,
    "max_neighbors": 32,
    "max_items": 12,
    "max_anchors": 3,
    "max_explicit_anchors": 5,
    "max_owner_members": 3,
    "max_evidence_bytes": 8192,
    "max_output_bytes": 16384,
    "max_anchor_source_bytes": 1024,
    "max_related_source_bytes": 768,
    "max_lookup_bytes": 33_554_432,
    "max_lookup_files": 4096,
    "max_literal_matches": 256,
}

_OMISSION_ORDER = (
    "no_anchor", "anchor_limit", "ambiguous_anchor", "lookup_limit",
    "node_limit", "neighbor_limit", "item_limit", "hop_limit", "cycle",
    "alternative_path", "ownership_limit", "unsupported_semantics",
    "unresolved_relation", "ambiguous_relation", "external_relation",
    "inaccessible_relation", "source_unavailable", "source_stale",
    "source_preview", "proof_unavailable", "evidence_budget", "output_budget",
)


@dataclass(frozen=True)
class ItemInput:
    node: Mapping[str, Any]
    role: str
    depth: int
    why: str
    full_span: Span
    preview_span: Span
    complete: bool


@dataclass(frozen=True)
class RelationInput:
    edge: GraphEdge
    traversed: str
    proof: tuple[Span, ...]
    resolution_configuration: str | None


@dataclass(frozen=True)
class Addition:
    nodes: tuple[Mapping[str, Any], ...] = ()
    items: tuple[ItemInput, ...] = ()
    ownership: tuple[tuple[str, str, str], ...] = ()
    relation: RelationInput | None = None


@dataclass
class _State:
    node_order: list[str] = field(default_factory=list)
    nodes: dict[str, dict[str, Any]] = field(default_factory=dict)
    items: list[dict[str, Any]] = field(default_factory=list)
    ownership: list[dict[str, str]] = field(default_factory=list)
    relationships: list[dict[str, Any]] = field(default_factory=list)
    relationship_keys: set[tuple[Any, ...]] = field(default_factory=set)
    spans: list[Span] = field(default_factory=list)
    span_ids: dict[tuple[Any, ...], int] = field(default_factory=dict)


class RetrievalPacker:
    def __init__(
        self,
        repo: Path,
        *,
        snapshot: str,
        selection: dict[str, Any],
        scope: dict[str, Any],
        anchors: list[dict[str, Any]],
    ) -> None:
        self.repo = repo
        self.snapshot = snapshot
        self.selection = selection
        self.scope = scope
        self.anchors = anchors
        self.state = _State()
        self.snapshots: list[_State] = []
        self.omissions: Counter[str] = Counter()
        self.usage = {
            "nodes_examined": 0,
            "eligible_edges_considered": 0,
            "edges_traversed": 0,
            "relationships_delivered": 0,
            "lookup_bytes": 0,
            "lookup_files": 0,
            "evidence_bytes": 0,
            "output_bytes": 0,
            "estimated_tokens": 0,
            "token_estimate_method": "utf8_bytes_div_4",
            "output_encoding": "mcp_result_json_utf8",
        }

    def omit(self, reason: str, count: int = 1) -> None:
        if count <= 0:
            return
        if reason not in _OMISSION_ORDER:
            raise ValueError(f"unsupported omission reason: {reason}")
        self.omissions[reason] += count

    def add(self, addition: Addition) -> bool:
        if len(self.state.items) + len(addition.items) > LIMITS["max_items"]:
            self.omit("item_limit", len(addition.items))
            return False
        candidate = copy.deepcopy(self.state)
        try:
            self._apply(candidate, addition)
        except (KeyError, UnicodeError, ValueError):
            self.omit("source_unavailable")
            return False
        response = self._render(candidate)
        evidence = _evidence_bytes(candidate.spans)
        finalize_response(response, evidence)
        if evidence > LIMITS["max_evidence_bytes"]:
            self.omit("evidence_budget")
            return False
        if response["usage"]["output_bytes"] > LIMITS["max_output_bytes"]:
            self.omit("output_budget")
            return False
        self.snapshots.append(copy.deepcopy(self.state))
        self.state = candidate
        previews = sum(not item.complete for item in addition.items)
        if previews:
            self.omit("source_preview", previews)
        return True

    def finish(self) -> dict[str, Any]:
        while True:
            response = self._render(self.state)
            finalize_response(response, _evidence_bytes(self.state.spans))
            if response["usage"]["output_bytes"] <= LIMITS["max_output_bytes"]:
                if any(anchor["node_id"] not in self.state.nodes for anchor in self.anchors):
                    raise GraphContractError(
                        "OUTPUT_BUDGET_EXCEEDED",
                        "Normal retrieval anchor identities cannot fit the fixed output budget",
                        {},
                    )
                return response
            if not self.snapshots:
                raise GraphContractError(
                    "OUTPUT_BUDGET_EXCEEDED",
                    "Normal retrieval framing cannot fit its fixed output budget",
                    {},
                )
            self.state = self.snapshots.pop()
            self.omissions["output_budget"] += 1

    def _apply(self, state: _State, addition: Addition) -> None:
        for node in addition.nodes:
            self._add_node(state, node)
        for owner_id, member_id, basis in addition.ownership:
            value = {"owner_id": owner_id, "member_id": member_id, "basis": basis}
            if value not in state.ownership:
                state.ownership.append(value)
        for item in addition.items:
            _validate_span(item.full_span)
            _validate_span(item.preview_span)
            source_id = self._source_id(state, item.preview_span)
            value = {
                "node_id": str(item.node["id"]),
                "role": item.role,
                "depth": item.depth,
                "why": item.why,
                "source_ids": [source_id],
                "complete": item.complete,
                "extent": {
                    "file": item.full_span.file,
                    "content_hash": item.full_span.content_hash,
                    "start_byte": item.full_span.start_byte,
                    "end_byte": item.full_span.end_byte,
                },
                "source_ref": source_ref(self.repo, item.full_span),
            }
            if not any(current["node_id"] == value["node_id"] for current in state.items):
                state.items.append(value)
        relation = addition.relation
        if relation is not None:
            if relation.traversed not in {"forward", "reverse"} or not relation.proof:
                raise ValueError("relationship requires complete proof")
            for span in relation.proof:
                _validate_span(span)
            edge = relation.edge.to_dict()
            key = (
                edge["namespace"], edge["type"], edge["from"], edge["to"],
                edge["directed"], edge["resolution"], edge["evidence"]["file"],
                edge["evidence"]["line"], edge["evidence"]["content_hash"],
            )
            if key not in state.relationship_keys:
                source_ids = list(dict.fromkeys(
                    self._source_id(state, span) for span in relation.proof
                ))
                state.relationship_keys.add(key)
                state.relationships.append({
                    "id": len(state.relationships) + 1,
                    "edge": edge,
                    "traversed": relation.traversed,
                    "source_ids": source_ids,
                    "proof": "complete",
                    "resolution_configuration": relation.resolution_configuration,
                })

    def _add_node(self, state: _State, node: Mapping[str, Any]) -> None:
        node_id = str(node["id"])
        value = {
            "id": node_id,
            "name": str(node.get("name") or ""),
            "kind": str(node.get("kind") or "unknown"),
            "file": str(node["file_path"]) if isinstance(node.get("file_path"), str) else None,
        }
        if node_id not in state.nodes:
            state.node_order.append(node_id)
            state.nodes[node_id] = value

    def _source_id(self, state: _State, span: Span) -> int:
        key = (span.file, span.start_byte, span.end_byte, span.content_hash)
        current = state.span_ids.get(key)
        if current is not None:
            return current
        for index, existing in enumerate(state.spans, 1):
            if (
                existing.file == span.file
                and existing.content_hash == span.content_hash
                and existing.start_byte <= span.start_byte
                and span.end_byte <= existing.end_byte
            ):
                return index
        source_id_value = len(state.spans) + 1
        state.spans.append(span)
        state.span_ids[key] = source_id_value
        return source_id_value

    def _render(self, state: _State) -> dict[str, Any]:
        usage = copy.deepcopy(self.usage)
        usage["relationships_delivered"] = len(state.relationships)
        status = "empty" if not state.items and not state.relationships else "ok"
        if self.omissions or any(not item["complete"] for item in state.items):
            status = "partial" if status != "empty" else "empty"
        return {
            "schema_version": 1,
            "policy": "normal-graph-v1",
            "snapshot": self.snapshot,
            "status": status,
            "selection": copy.deepcopy(self.selection),
            "scope": copy.deepcopy(self.scope),
            "anchors": copy.deepcopy(self.anchors),
            "nodes": [copy.deepcopy(state.nodes[node_id]) for node_id in state.node_order],
            "items": copy.deepcopy(state.items),
            "ownership": copy.deepcopy(state.ownership),
            "relationships": copy.deepcopy(state.relationships),
            "sources": [
                serialize_source(self.repo, span, index)
                for index, span in enumerate(state.spans, 1)
            ],
            "omissions": [
                {"reason": reason, "count": self.omissions[reason]}
                for reason in _OMISSION_ORDER if self.omissions[reason]
            ],
            "limits": dict(LIMITS),
            "usage": usage,
        }
