"""Pure, evidence-preserving output packing for exploration responses."""

from __future__ import annotations

import copy
import json
import math
import re
from dataclasses import dataclass, replace
from typing import Any, Mapping, Sequence


_OMISSION_REASONS = frozenset({
    "no_anchor", "anchor_limit", "unsupported_anchor", "unsupported_language",
    "unresolved_relation", "not_selected", "alternative_path", "cycle",
    "hop_limit", "node_limit", "neighbor_limit", "item_limit", "evidence_budget",
    "output_budget", "source_clipped", "source_unavailable", "ancestor_unavailable",
})
_PARTIAL_REASONS = _OMISSION_REASONS - {"not_selected", "alternative_path", "cycle"}
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_MAX_ITEMS = 12
_MAX_NODES = 64
_MAX_NEIGHBORS = 32


@dataclass(frozen=True)
class Span:
    file: str
    start_byte: int
    end_byte: int
    start_line: int
    end_line: int
    content_hash: str
    content: str


@dataclass(frozen=True)
class Relation:
    edge: dict[str, Any]
    traversed: str
    sources: tuple[Span, ...]


@dataclass(frozen=True)
class Bundle:
    item: dict[str, Any]
    sources: tuple[Span, ...]
    relations: tuple[Relation, ...]


@dataclass
class _State:
    items: list[dict[str, Any]]
    relations: list[dict[str, Any]]
    sources: list[Span]
    relation_keys: dict[str, int]
    source_keys: dict[tuple[str, int, int, str], int]

    def clone(self) -> _State:
        return _State(
            items=copy.deepcopy(self.items),
            relations=copy.deepcopy(self.relations),
            sources=list(self.sources),
            relation_keys=dict(self.relation_keys),
            source_keys=dict(self.source_keys),
        )


def pack_exploration(base: dict[str, Any], bundles: Sequence[Bundle]) -> dict[str, Any]:
    """Pack ordered evidence bundles under fixed MCP-result and evidence budgets.

    The caller supplies already selected, source-backed facts. This function only
    validates their shape, maintains atomic paths, and applies delivery budgets.
    """
    response_base, omissions, nodes_examined, output_limit, evidence_limit = _base(base)
    state = _State([], [], [], {}, {})
    snapshots: list[_State] = []

    def current() -> dict[str, Any]:
        return _render(response_base, state, omissions, nodes_examined)

    def fits(candidate: _State) -> tuple[bool, dict[str, Any]]:
        response = _render(response_base, candidate, omissions, nodes_examined)
        return (
            response["usage"]["evidence_bytes"] <= evidence_limit
            and response["usage"]["output_bytes"] <= output_limit,
            response,
        )

    def omit(reason: str, count: int = 1) -> None:
        _add_omission(omissions, reason, count)
        # An omission has framing cost. If it is the first occurrence of a new
        # reason, remove the most recently delivered item until the final
        # envelope fits, preserving no orphan relationship or source.
        nonlocal state
        while current()["usage"]["output_bytes"] > output_limit:
            if not snapshots:
                raise ValueError("base response cannot fit max_output_bytes")
            state = snapshots.pop().clone()
            _add_omission(omissions, "output_budget")

    for input_bundle in bundles:
        _validate_bundle(input_bundle)
        item_id = input_bundle.item["id"]
        is_root = not input_bundle.relations
        if len(state.items) >= _MAX_ITEMS:
            omit("item_limit")
            continue
        if item_id in {item["id"] for item in state.items}:
            omit("alternative_path")
            continue
        if not is_root and not _ancestors_available(input_bundle, state):
            omit("ancestor_unavailable")
            continue

        candidate = _append_bundle(state, input_bundle)
        accepted, _ = fits(candidate)
        if accepted:
            snapshots.append(state.clone())
            state = candidate
            continue

        if not is_root:
            evidence_after = _evidence_bytes(candidate.sources)
            omit("evidence_budget" if evidence_after > evidence_limit else "output_budget")
            continue

        clipped = _clip_anchor(
            state, input_bundle, response_base, omissions, nodes_examined,
            output_limit=output_limit, evidence_limit=evidence_limit,
        )
        if clipped is None:
            evidence_after = _evidence_bytes(candidate.sources)
            omit("evidence_budget" if evidence_after > evidence_limit else "output_budget")
            continue
        snapshots.append(state.clone())
        state = clipped
        omit("source_clipped")

    response = current()
    if response["usage"]["evidence_bytes"] > evidence_limit:
        raise ValueError("base response exceeds max_evidence_bytes")
    if response["usage"]["output_bytes"] > output_limit:
        raise ValueError("base response exceeds max_output_bytes")
    return response


def _base(base: Mapping[str, Any]) -> tuple[dict[str, Any], dict[str, int], int, int, int]:
    if not isinstance(base, Mapping):
        raise ValueError("base must be an object")
    required = {"schema_version", "intent", "selection", "scope", "limits", "usage"}
    if not required.issubset(base):
        raise ValueError("base is missing required exploration fields")
    if base["schema_version"] != 1:
        raise ValueError("schema_version must be 1")
    if base["intent"] not in {"locate", "type_dependencies", "dependencies", "impact"}:
        raise ValueError("intent is unsupported")
    if base["selection"] not in {"explicit", "inferred"}:
        raise ValueError("selection is unsupported")
    if not isinstance(base["scope"], Mapping) or not isinstance(base["limits"], Mapping):
        raise ValueError("scope and limits must be objects")
    limits = base["limits"]
    for field in ("max_hops", "max_output_bytes", "max_evidence_bytes"):
        if type(limits.get(field)) is not int or limits[field] < 0:
            raise ValueError(f"limits.{field} must be a non-negative integer")
    usage = base["usage"]
    if not isinstance(usage, Mapping) or type(usage.get("nodes_examined")) is not int or usage["nodes_examined"] < 0:
        raise ValueError("usage.nodes_examined must be a non-negative integer")
    omissions: dict[str, int] = {}
    supplied = base.get("omissions", [])
    if not isinstance(supplied, list):
        raise ValueError("omissions must be a list")
    for item in supplied:
        if not isinstance(item, Mapping) or set(item) != {"reason", "count"}:
            raise ValueError("omission must have reason and count")
        _add_omission(omissions, item["reason"], item["count"])
    response_base = {
        "schema_version": 1,
        "intent": base["intent"],
        "selection": base["selection"],
        "scope": copy.deepcopy(dict(base["scope"])),
        "limits": {
            "max_hops": limits["max_hops"], "max_nodes": _MAX_NODES,
            "max_items": _MAX_ITEMS, "max_neighbors": _MAX_NEIGHBORS,
            "max_output_bytes": limits["max_output_bytes"],
            "max_evidence_bytes": limits["max_evidence_bytes"],
        },
    }
    return response_base, omissions, usage["nodes_examined"], limits["max_output_bytes"], limits["max_evidence_bytes"]


def _add_omission(omissions: dict[str, int], reason: Any, count: Any = 1) -> None:
    if not isinstance(reason, str) or reason not in _OMISSION_REASONS:
        raise ValueError("unsupported omission reason")
    if type(count) is not int or count < 1:
        raise ValueError("omission count must be a positive integer")
    omissions[reason] = omissions.get(reason, 0) + count


def _validate_span(span: Span) -> None:
    if not isinstance(span, Span):
        raise ValueError("source must be a Span")
    if not isinstance(span.file, str) or not span.file:
        raise ValueError("span file must be non-empty")
    if type(span.start_byte) is not int or type(span.end_byte) is not int or span.start_byte < 0 or span.end_byte <= span.start_byte:
        raise ValueError("span byte range is invalid")
    if type(span.start_line) is not int or type(span.end_line) is not int or span.start_line < 1 or span.end_line < span.start_line:
        raise ValueError("span line range is invalid")
    if not isinstance(span.content, str) or not span.content or len(span.content.encode("utf-8")) != span.end_byte - span.start_byte:
        raise ValueError("span content does not match its UTF-8 range")
    if not isinstance(span.content_hash, str) or not _SHA256.fullmatch(span.content_hash):
        raise ValueError("span content_hash must be a SHA-256 digest")


def _validate_bundle(bundle: Bundle) -> None:
    if not isinstance(bundle, Bundle) or not isinstance(bundle.item, dict):
        raise ValueError("bundle item is invalid")
    required = {"id", "name", "kind", "file", "role", "depth", "why"}
    if set(bundle.item) != required:
        raise ValueError("bundle item fields are invalid")
    if any(not isinstance(bundle.item[field], str) or not bundle.item[field] for field in ("id", "name", "kind", "file", "role", "why")):
        raise ValueError("bundle item text field is invalid")
    if bundle.item["role"] not in {"anchor", "dependency", "dependent"} or type(bundle.item["depth"]) is not int or bundle.item["depth"] < 0:
        raise ValueError("bundle item role or depth is invalid")
    if not bundle.relations and bundle.item["role"] != "anchor":
        raise ValueError("a root bundle must be an anchor")
    if bundle.relations and bundle.item["role"] == "anchor":
        raise ValueError("a related bundle cannot be an anchor")
    if not isinstance(bundle.sources, tuple) or not bundle.sources:
        raise ValueError("bundle requires a definition source")
    for span in bundle.sources:
        _validate_span(span)
    if not isinstance(bundle.relations, tuple):
        raise ValueError("bundle relations must be a tuple")
    for relation in bundle.relations:
        if not isinstance(relation, Relation) or relation.traversed not in {"forward", "reverse"} or not isinstance(relation.edge, dict) or not relation.sources:
            raise ValueError("bundle relation is invalid")
        for span in relation.sources:
            _validate_span(span)


def _ancestors_available(bundle: Bundle, state: _State) -> bool:
    delivered = {item["id"] for item in state.items}
    delivered.add(bundle.item["id"])
    for relation in bundle.relations:
        try:
            ancestor = relation.edge["from"] if relation.traversed == "forward" else relation.edge["to"]
        except KeyError:
            return False
        if not isinstance(ancestor, str) or ancestor not in delivered:
            return False
    return True


def _append_bundle(state: _State, bundle: Bundle) -> _State:
    candidate = state.clone()
    definition_id = _source_id(candidate, bundle.sources[0])
    for span in bundle.sources[1:]:
        _source_id(candidate, span)
    path: list[int] = []
    for relation in bundle.relations:
        source_ids = list(dict.fromkeys(_source_id(candidate, span) for span in relation.sources))
        key = _relation_key(relation)
        relation_id = candidate.relation_keys.get(key)
        if relation_id is None:
            relation_id = len(candidate.relations) + 1
            candidate.relation_keys[key] = relation_id
            candidate.relations.append({
                "id": relation_id, "edge": copy.deepcopy(relation.edge),
                "traversed": relation.traversed, "source_ids": source_ids,
            })
        else:
            current = candidate.relations[relation_id - 1]["source_ids"]
            candidate.relations[relation_id - 1]["source_ids"] = list(dict.fromkeys([*current, *source_ids]))
        path.append(relation_id)
    item = copy.deepcopy(bundle.item)
    item.update({"source_id": definition_id, "complete": True, "path": path})
    candidate.items.append(item)
    return candidate


def _source_id(state: _State, span: Span) -> int:
    exact = (span.file, span.start_byte, span.end_byte, span.content_hash)
    existing = state.source_keys.get(exact)
    if existing is not None:
        if state.sources[existing - 1].content != span.content:
            raise ValueError("identical source spans have conflicting content")
        return existing
    for source_id, prior in enumerate(state.sources, 1):
        if (prior.file == span.file and prior.content_hash == span.content_hash
                and prior.start_byte <= span.start_byte and span.end_byte <= prior.end_byte):
            return source_id
    source_id = len(state.sources) + 1
    state.sources.append(span)
    state.source_keys[exact] = source_id
    return source_id


def _relation_key(relation: Relation) -> str:
    try:
        return json.dumps(
            {"edge": relation.edge, "traversed": relation.traversed},
            ensure_ascii=False, separators=(",", ":"), sort_keys=True,
        )
    except (TypeError, ValueError) as exc:
        raise ValueError("relation edge must be JSON serializable") from exc


def _clip_anchor(
    state: _State,
    bundle: Bundle,
    response_base: dict[str, Any],
    omissions: dict[str, int],
    nodes_examined: int,
    *,
    output_limit: int,
    evidence_limit: int,
) -> _State | None:
    full = bundle.sources[0]
    if len(full.content) < 2:
        return None
    trial_omissions = dict(omissions)
    _add_omission(trial_omissions, "source_clipped")

    def candidate_for(chars: int) -> _State:
        prefix = full.content[:chars]
        clipped = replace(
            full, end_byte=full.start_byte + len(prefix.encode("utf-8")),
            end_line=(full.start_line + prefix.count("\n")
                      - int(prefix.endswith("\n"))), content=prefix,
        )
        changed = Bundle(bundle.item, (clipped, *bundle.sources[1:]), bundle.relations)
        result = _append_bundle(state, changed)
        result.items[-1]["complete"] = False
        return result

    def fits(chars: int) -> bool:
        if chars < 1:
            return False
        candidate = candidate_for(chars)
        response = _render(response_base, candidate, trial_omissions, nodes_examined)
        return response["usage"]["evidence_bytes"] <= evidence_limit and response["usage"]["output_bytes"] <= output_limit

    low, high = 1, len(full.content) - 1
    best = 0
    while low <= high:
        middle = (low + high) // 2
        if fits(middle):
            best = middle
            low = middle + 1
        else:
            high = middle - 1
    if not best:
        return None
    # Keep a whole final source line when it is close to the maximal byte-safe
    # prefix. A distant newline would discard useful bounded evidence, so the
    # byte-optimal prefix remains preferable in that case.
    newline = full.content.rfind("\n", 0, best + 1)
    if newline >= 0 and best - (newline + 1) <= 128 and fits(newline + 1):
        best = newline + 1
    return candidate_for(best)


def _render(base: dict[str, Any], state: _State, omissions: Mapping[str, int], nodes_examined: int) -> dict[str, Any]:
    response: dict[str, Any] = {
        "schema_version": base["schema_version"], "intent": base["intent"],
        "status": "empty", "selection": base["selection"],
        "scope": copy.deepcopy(base["scope"]), "items": copy.deepcopy(state.items),
        "relationships": copy.deepcopy(state.relations),
        "sources": [
            {"id": source_id, "file": span.file, "start_byte": span.start_byte,
             "end_byte": span.end_byte, "start_line": span.start_line,
             "end_line": span.end_line, "content_hash": span.content_hash,
             "content": span.content}
            for source_id, span in enumerate(state.sources, 1)
        ],
        "omissions": [{"reason": reason, "count": omissions[reason]} for reason in sorted(omissions)],
        "limits": copy.deepcopy(base["limits"]),
        "usage": {
            "nodes_examined": nodes_examined, "evidence_bytes": _evidence_bytes(state.sources),
            "output_bytes": 0, "estimated_tokens": 0,
            "token_estimate_method": "utf8_bytes_div_4",
            "output_encoding": "mcp_result_json_utf8",
        },
    }
    response["status"] = _status(response["items"], omissions)
    for _ in range(16):
        bytes_used = _envelope_bytes(response)
        tokens = math.ceil(bytes_used / 4)
        if response["usage"]["output_bytes"] == bytes_used and response["usage"]["estimated_tokens"] == tokens:
            return response
        response["usage"]["output_bytes"] = bytes_used
        response["usage"]["estimated_tokens"] = tokens
    raise ValueError("output accounting did not converge")


def _status(items: Sequence[Mapping[str, Any]], omissions: Mapping[str, int]) -> str:
    if not items:
        return "empty"
    return "partial" if any(reason in _PARTIAL_REASONS for reason in omissions) else "ok"


def _envelope_bytes(response: Mapping[str, Any]) -> int:
    return len(json.dumps(
        {"content": [], "structuredContent": response, "isError": False},
        ensure_ascii=False, separators=(",", ":"),
    ).encode("utf-8"))


def _evidence_bytes(spans: Sequence[Span]) -> int:
    intervals: dict[tuple[str, str], list[tuple[int, int]]] = {}
    for span in spans:
        intervals.setdefault((span.file, span.content_hash), []).append((span.start_byte, span.end_byte))
    total = 0
    for ranges in intervals.values():
        start = end = -1
        for current_start, current_end in sorted(ranges):
            if start < 0:
                start, end = current_start, current_end
            elif current_start <= end:
                end = max(end, current_end)
            else:
                total += end - start
                start, end = current_start, current_end
        if start >= 0:
            total += end - start
    return total
