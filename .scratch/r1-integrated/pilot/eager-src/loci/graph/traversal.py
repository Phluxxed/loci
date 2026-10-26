from __future__ import annotations

import math
import re
from collections import deque
from dataclasses import dataclass
from typing import Literal, Mapping, Sequence, cast

from .contracts import (
    RESOLUTION_TIERS,
    GraphContractError,
    GraphEdge,
)


MAX_GRAPH_FILTER_VALUES = 32
MAX_GRAPH_HOPS = 6
MAX_GRAPH_NODES = 512
MAX_GRAPH_PATHS = 32
MAX_GRAPH_PATH_OFFSET = 256
MAX_GRAPH_EVIDENCE_BYTES = 262_144
MAX_GRAPH_ESTIMATED_TOKENS = 65_536

GraphDirection = Literal["outgoing", "incoming", "either"]
TraversalOrientation = Literal["forward", "reverse"]

SAFE_GRAPH_RESOLUTIONS = ("exact", "declared", "import-resolved")
_DIRECTIONS = frozenset({"outgoing", "incoming", "either"})
_TOKEN_RE = re.compile(r"[a-z0-9]+")
_QUESTION_STOP_WORDS = frozenset({
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "been",
    "by",
    "can",
    "could",
    "did",
    "do",
    "does",
    "for",
    "from",
    "had",
    "has",
    "have",
    "how",
    "if",
    "in",
    "into",
    "is",
    "it",
    "its",
    "may",
    "of",
    "on",
    "or",
    "should",
    "that",
    "the",
    "their",
    "then",
    "there",
    "these",
    "they",
    "this",
    "those",
    "to",
    "was",
    "were",
    "what",
    "when",
    "where",
    "which",
    "who",
    "why",
    "will",
    "with",
    "would",
})


@dataclass(frozen=True, slots=True)
class GraphTraversalStep:
    from_id: str
    to_id: str
    edge: GraphEdge
    traversed: TraversalOrientation


@dataclass(frozen=True, slots=True)
class GraphPath:
    node_ids: tuple[str, ...]
    steps: tuple[GraphTraversalStep, ...]


@dataclass(frozen=True, slots=True)
class GraphTraversalResult:
    paths: tuple[GraphPath, ...]
    filtered_edge_count: int
    examined_nodes: int
    examined_paths: int
    omitted_nodes: int
    omitted_paths: int
    hop_limit_reached: bool
    node_limit_reached: bool
    next_path_offset: int | None


def filter_graph_edges(
    edges: Sequence[GraphEdge],
    *,
    namespaces: Sequence[str] | None,
    edge_types: Sequence[str] | None,
    resolutions: Sequence[str] | None,
) -> tuple[GraphEdge, ...]:
    namespace_values = _filter_values(namespaces, "namespaces")
    edge_type_values = _filter_values(edge_types, "edge_types")
    resolution_values = _filter_values(
        resolutions if resolutions is not None else SAFE_GRAPH_RESOLUTIONS,
        "resolutions",
    )
    assert resolution_values is not None
    unsupported = [
        value for value in resolution_values if value not in RESOLUTION_TIERS
    ]
    if unsupported:
        raise GraphContractError(
            "GRAPH_RESOLUTION_UNSUPPORTED",
            "Unsupported graph resolution tier",
            {"resolutions": unsupported},
        )

    namespace_set = set(namespace_values) if namespace_values is not None else None
    edge_type_set = set(edge_type_values) if edge_type_values is not None else None
    resolution_set = set(resolution_values)
    filtered = [
        edge
        for edge in edges
        if (
            (namespace_set is None or edge.namespace in namespace_set)
            and (edge_type_set is None or edge.type in edge_type_set)
            and edge.resolution in resolution_set
        )
    ]
    return tuple(sorted(filtered, key=_edge_key))


def graph_adjacency(
    edges: Sequence[GraphEdge],
    *,
    direction: GraphDirection,
) -> Mapping[str, tuple[GraphTraversalStep, ...]]:
    _validate_direction(direction)
    adjacency: dict[str, list[GraphTraversalStep]] = {}
    for edge in sorted(edges, key=_edge_key):
        if not edge.directed or direction in {"outgoing", "either"}:
            adjacency.setdefault(edge.from_id, []).append(
                GraphTraversalStep(
                    from_id=edge.from_id,
                    to_id=edge.to_id,
                    edge=edge,
                    traversed="forward",
                )
            )
        if not edge.directed or direction in {"incoming", "either"}:
            adjacency.setdefault(edge.to_id, []).append(
                GraphTraversalStep(
                    from_id=edge.to_id,
                    to_id=edge.from_id,
                    edge=edge,
                    traversed="reverse",
                )
            )
    return {
        node_id: tuple(sorted(steps, key=_step_key))
        for node_id, steps in sorted(adjacency.items())
    }


def find_graph_paths(
    edges: Sequence[GraphEdge],
    source_ids: Sequence[str],
    target_ids: Sequence[str],
    *,
    direction: GraphDirection,
    max_hops: int,
    max_nodes: int,
    max_paths: int,
    path_offset: int = 0,
    node_priorities: Mapping[str, float] | None = None,
) -> GraphTraversalResult:
    sources = _node_ids(source_ids, "source_ids")
    targets = _node_ids(target_ids, "target_ids")
    _validate_direction(direction)
    _bounded_int(max_hops, "max_hops", 1, MAX_GRAPH_HOPS)
    _bounded_int(max_nodes, "max_nodes", 2, MAX_GRAPH_NODES)
    _bounded_int(max_paths, "max_paths", 1, MAX_GRAPH_PATHS)
    _bounded_int(path_offset, "path_offset", 0, MAX_GRAPH_PATH_OFFSET)
    endpoint_count = len(set((*sources, *targets)))
    if endpoint_count > max_nodes:
        raise _error(
            "Graph endpoints exceed the node budget",
            field="source_ids,target_ids",
            endpoint_count=endpoint_count,
            max_nodes=max_nodes,
        )
    if not any(source != target for source in sources for target in targets):
        raise _error(
            "Graph path endpoints must include two different nodes",
            field="target_ids",
        )

    priorities = node_priorities or {}
    adjacency = graph_adjacency(edges, direction=direction)
    target_set = set(targets)
    admitted = set((*sources, *targets))
    queue = deque((source, (source,), ()) for source in sources)
    candidates: list[GraphPath] = []
    candidate_keys: set[tuple] = set()
    omitted_node_ids: set[str] = set()
    omitted_paths = 0
    hop_limit_reached = False
    node_limit_reached = False
    examined_path_states = 0
    candidate_limit = path_offset + max_paths + 1
    state_limit = max_nodes * max(2, candidate_limit) * max_hops

    while queue and len(candidates) < candidate_limit:
        origin, node_ids, steps = queue.popleft()
        examined_path_states += 1
        if examined_path_states > state_limit:
            omitted_paths += len(queue) + 1
            break
        current = node_ids[-1]
        available = _priority_steps(adjacency.get(current, ()), priorities)
        if len(steps) >= max_hops:
            if any(step.to_id not in node_ids for step in available):
                hop_limit_reached = True
                omitted_paths += 1
            continue

        for step in available:
            neighbor = step.to_id
            if neighbor in node_ids:
                continue
            if neighbor not in admitted:
                if len(admitted) >= max_nodes:
                    node_limit_reached = True
                    omitted_node_ids.add(neighbor)
                    continue
                admitted.add(neighbor)
            next_nodes = (*node_ids, neighbor)
            next_steps = (*steps, step)
            reached_target = neighbor in target_set and neighbor != origin
            if reached_target:
                candidate = GraphPath(next_nodes, next_steps)
                identity = _path_identity(candidate)
                if identity not in candidate_keys:
                    candidates.append(candidate)
                    candidate_keys.add(identity)
            if not reached_target or target_set.difference(next_nodes):
                queue.append((origin, next_nodes, next_steps))

    selected = tuple(candidates[path_offset : path_offset + max_paths])
    window_end = path_offset + len(selected)
    has_more = len(candidates) > window_end or bool(queue)
    next_offset = window_end if selected and has_more else None
    omitted_paths += max(0, len(candidates) - window_end)
    return GraphTraversalResult(
        paths=selected,
        filtered_edge_count=len(edges),
        examined_nodes=len(admitted),
        examined_paths=examined_path_states,
        omitted_nodes=len(omitted_node_ids),
        omitted_paths=omitted_paths,
        hop_limit_reached=hop_limit_reached,
        node_limit_reached=node_limit_reached,
        next_path_offset=next_offset,
    )

def graph_hub_threshold(filtered_edge_count: int) -> int:
    if (
        not isinstance(filtered_edge_count, int)
        or isinstance(filtered_edge_count, bool)
        or filtered_edge_count < 0
    ):
        raise _error(
            "Filtered edge count must be a non-negative integer",
            field="filtered_edge_count",
        )
    return max(4, math.ceil(math.sqrt(filtered_edge_count)))


def semantic_bridge_terms(
    question: str,
    source_text: str,
    target_text: str,
) -> tuple[str, ...]:
    if not all(isinstance(value, str) for value in (question, source_text, target_text)):
        raise _error(
            "Semantic bridge inputs must be strings",
            field="question",
        )
    endpoint_terms = set(graph_text_terms(f"{source_text} {target_text}"))
    stop_terms = {_stem_term(word) for word in _QUESTION_STOP_WORDS}
    terms: list[str] = []
    seen: set[str] = set()
    for term in graph_text_terms(question):
        if term in stop_terms or term in endpoint_terms or term in seen:
            continue
        terms.append(term)
        seen.add(term)
    return tuple(terms)


def graph_relation_terms(question: str) -> tuple[str, ...]:
    if not isinstance(question, str):
        raise _error("Graph question must be a string", field="question")
    relation_vocabulary = set(graph_text_terms(
        "become bridge cause connect define derive improve improved incubated link promote "
        "propose related relation relationship support transform transition"
    ))
    return tuple(
        term for term in graph_text_terms(question) if term in relation_vocabulary
    )


def graph_text_terms(text: str) -> tuple[str, ...]:
    return tuple(
        normalized
        for raw in _TOKEN_RE.findall(text.casefold())
        if len((normalized := _stem_term(raw))) >= 2
    )


def _filter_values(
    values: Sequence[str] | None,
    field: str,
) -> tuple[str, ...] | None:
    if values is None:
        return None
    if isinstance(values, (str, bytes)) or not isinstance(values, Sequence):
        raise _error("Graph filters must be lists of strings", field=field)
    if not values:
        raise _error("Graph filter lists cannot be empty", field=field)
    if len(values) > MAX_GRAPH_FILTER_VALUES:
        raise _error(
            "Graph filter exceeds the value limit",
            field=field,
            count=len(values),
            max_values=MAX_GRAPH_FILTER_VALUES,
        )
    if any(not isinstance(value, str) or not value for value in values):
        raise _error("Graph filters must contain non-empty strings", field=field)
    return tuple(dict.fromkeys(values))


def _node_ids(values: Sequence[str], field: str) -> tuple[str, ...]:
    if isinstance(values, (str, bytes)) or not isinstance(values, Sequence):
        raise _error("Graph endpoints must be lists of strings", field=field)
    if not values:
        raise _error("Graph endpoint lists cannot be empty", field=field)
    if any(not isinstance(value, str) or not value for value in values):
        raise _error("Graph endpoints must be non-empty strings", field=field)
    return tuple(dict.fromkeys(values))


def _validate_direction(direction: str) -> None:
    if direction not in _DIRECTIONS:
        raise _error(
            "Graph direction must be outgoing, incoming, or either",
            field="direction",
            direction=direction,
        )


def _bounded_int(value: int, field: str, minimum: int, maximum: int) -> None:
    if (
        not isinstance(value, int)
        or isinstance(value, bool)
        or not minimum <= value <= maximum
    ):
        raise _error(
            "Graph traversal limit is out of range",
            field=field,
            value=value,
            minimum=minimum,
            maximum=maximum,
        )


def _edge_key(edge: GraphEdge) -> tuple:
    return (
        edge.namespace,
        edge.type,
        edge.from_id,
        edge.to_id,
        edge.resolution,
        edge.evidence.file,
        edge.evidence.line,
        edge.evidence.content_hash,
    )


def _step_key(step: GraphTraversalStep) -> tuple:
    return (step.to_id, step.traversed, _edge_key(step.edge))


def _priority_steps(
    steps: Sequence[GraphTraversalStep],
    priorities: Mapping[str, float],
) -> tuple[GraphTraversalStep, ...]:
    return tuple(
        sorted(
            steps,
            key=lambda step: (-float(priorities.get(step.to_id, 0.0)), _step_key(step)),
        )
    )


def _path_identity(path: GraphPath) -> tuple:
    return (
        path.node_ids,
        tuple((step.traversed, _edge_key(step.edge)) for step in path.steps),
    )


def _stem_term(term: str) -> str:
    if len(term) > 7 and term.endswith("ness"):
        term = term[:-4]
    elif len(term) > 5 and term.endswith("ing"):
        term = term[:-3]
    elif len(term) > 4 and term.endswith("ed"):
        term = term[:-2]
    elif len(term) > 4 and term.endswith("ies"):
        term = term[:-3] + "y"
    elif len(term) > 4 and term.endswith("es"):
        term = term[:-2]
    elif len(term) > 3 and term.endswith("s") and not term.endswith(("ss", "us", "is")):
        term = term[:-1]
    return term


def _error(message: str, **details: object) -> GraphContractError:
    return GraphContractError(
        "INVALID_INPUT",
        message,
        cast(dict, details),
    )
