"""Deterministic atomic packing for normal retrieval responses."""
from __future__ import annotations

from collections import Counter
import copy
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, Mapping

from ._exploration_output import Span, _evidence_bytes, _validate_span
from .graph.contracts import GraphContractError
from .retrieval_io import finalize_response, serialize_source, source_ref
from .storage.index_store import IndexStore
from .storage.source_refs import SourceRefStore


LIMITS = {
    "max_nodes": 64,
    "max_items": 12,
    "max_anchors": 3,
    "max_explicit_anchors": 5,
    "max_evidence_bytes": 8192,
    "max_output_bytes": 16384,
    "max_lookup_bytes": 33_554_432,
    "max_lookup_files": 4096,
    "max_literal_matches": 256,
}

_OMISSION_ORDER = (
    "no_anchor", "anchor_limit", "ambiguous_anchor", "lookup_limit",
    "node_limit", "item_limit", "alternative_path", "source_unavailable",
    "source_stale", "source_preview", "evidence_budget", "output_budget",
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
    focus: tuple[int, int] | None = None
    preview_budget: int = 0


@dataclass(frozen=True)
class Addition:
    nodes: tuple[Mapping[str, Any], ...] = ()
    items: tuple[ItemInput, ...] = ()
    ownership: tuple[tuple[str, str, str], ...] = ()


@dataclass
class _State:
    node_order: list[str] = field(default_factory=list)
    nodes: dict[str, dict[str, Any]] = field(default_factory=dict)
    items: list[dict[str, Any]] = field(default_factory=list)
    ownership: list[dict[str, str]] = field(default_factory=list)
    spans: list[Span] = field(default_factory=list)
    span_ids: dict[tuple[Any, ...], int] = field(default_factory=dict)


def _anchor_excerpt(full: Span, max_bytes: int,
                    focus: tuple[int, int] | None) -> Span:
    raw = full.content.encode("utf-8")
    if focus is None:
        start = 0
    else:
        match_start = focus[0] - full.start_byte
        match_end = focus[1] - full.start_byte
        if not 0 <= match_start < match_end <= len(raw):
            raise ValueError("literal match is outside its indexed source extent")
        if match_end - match_start > max_bytes:
            raise ValueError("literal match exceeds source preview")
        start = min(max(0, match_start - (max_bytes - match_end + match_start) // 2),
                    len(raw) - max_bytes)
    while start < len(raw) and raw[start] & 0xC0 == 0x80:
        start += 1
    end = min(len(raw), start + max_bytes)
    while end > start and end < len(raw) and raw[end] & 0xC0 == 0x80:
        end -= 1
    if end <= start or (focus is not None and end < match_end):
        raise ValueError("source preview cannot include the literal match")
    content = raw[start:end].decode("utf-8")
    start_line = full.start_line + raw[:start].count(b"\n")
    return Span(full.file, full.start_byte + start, full.start_byte + end,
                start_line,
                max(start_line, start_line + content.count("\n")
                    - int(content.endswith("\n"))),
                full.content_hash, content)


class RetrievalPacker:
    def __init__(
        self,
        repo: Path,
        *,
        snapshot: str,
        selection: dict[str, Any],
        scope: dict[str, Any],
        anchors: list[dict[str, Any]],
        store: IndexStore | None = None,
    ) -> None:
        self.repo = repo
        self.references = SourceRefStore(repo, store) if store is not None else None
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
        def trial(value: Addition) -> tuple[_State, int, int]:
            candidate = copy.deepcopy(self.state)
            self._apply(candidate, value)
            previews = sum(not item.complete for item in value.items)
            self.omissions["source_preview"] += previews
            try:
                response = self._render(candidate)
                evidence = _evidence_bytes(candidate.spans)
                finalize_response(response, evidence)
            finally:
                self.omissions["source_preview"] -= previews
            return candidate, evidence, response["usage"]["output_bytes"]

        def fits(result: tuple[_State, int, int]) -> bool:
            return (result[1] <= LIMITS["max_evidence_bytes"]
                    and result[2] <= LIMITS["max_output_bytes"])

        try:
            result = trial(addition)
            selected = addition
            if addition.items and not fits(result):
                low = 0
                high = max(item.preview_budget for item in addition.items)
                best: tuple[_State, int, int] | None = None
                while low <= high:
                    cap = (low + high) // 2
                    excerpts = []
                    for item in addition.items:
                        full_bytes = len(item.full_span.content.encode("utf-8"))
                        minimum = (item.focus[1] - item.focus[0] if item.focus
                                   else len(item.full_span.content[0].encode("utf-8")))
                        budget = min(full_bytes, max(minimum, min(item.preview_budget, cap)))
                        excerpt = _anchor_excerpt(item.full_span, budget, item.focus)
                        excerpts.append(replace(item, preview_span=excerpt,
                                                complete=budget == full_bytes))
                    candidate_addition = replace(addition, items=tuple(excerpts))
                    candidate_result = trial(candidate_addition)
                    if fits(candidate_result):
                        best = candidate_result
                        selected = candidate_addition
                        low = cap + 1
                    else:
                        high = cap - 1
                if best is not None:
                    result = best
            if not fits(result):
                self.omit("evidence_budget" if result[1] > LIMITS["max_evidence_bytes"]
                          else "output_budget")
                return False
        except (KeyError, UnicodeError, ValueError):
            self.omit("source_unavailable")
            return False
        self.snapshots.append(copy.deepcopy(self.state))
        self.state = result[0]
        previews = sum(not item.complete for item in selected.items)
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
                if self.references is not None:
                    self.references.flush(
                        item["source_ref"]
                        for item in (*response["items"], *response["sources"])
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
                "source_ref": source_ref(self.repo, item.full_span, references=self.references),
            }
            if not any(current["node_id"] == value["node_id"] for current in state.items):
                state.items.append(value)

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
        status = "empty" if not state.items else "ok"
        if self.omissions or any(not item["complete"] for item in state.items):
            status = "partial" if status != "empty" else "empty"
        return {
            "schema_version": 1,
            "policy": "source-context-v1",
            "snapshot": self.snapshot,
            "status": status,
            "selection": copy.deepcopy(self.selection),
            "scope": copy.deepcopy(self.scope),
            "anchors": copy.deepcopy(self.anchors),
            "nodes": [copy.deepcopy(state.nodes[node_id]) for node_id in state.node_order],
            "items": copy.deepcopy(state.items),
            "ownership": copy.deepcopy(state.ownership),
            "relationships": [],
            "sources": [
                serialize_source(self.repo, span, index, references=self.references)
                for index, span in enumerate(state.spans, 1)
            ],
            "omissions": [
                {"reason": reason, "count": self.omissions[reason]}
                for reason in _OMISSION_ORDER if self.omissions[reason]
            ],
            "limits": dict(LIMITS),
            "usage": usage,
        }
