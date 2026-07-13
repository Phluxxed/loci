from __future__ import annotations

import math
import re
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Any, Literal, Mapping, TypeAlias, cast


JSONValue: TypeAlias = (
    None
    | bool
    | int
    | float
    | str
    | list["JSONValue"]
    | dict[str, "JSONValue"]
)
ResolutionTier: TypeAlias = Literal[
    "exact",
    "declared",
    "import-resolved",
    "heuristic",
]

GRAPH_SCHEMA_VERSION = 1
MAX_GRAPH_CONTRIBUTION_RECORDS = 10_000
RESOLUTION_TIERS = frozenset({
    "exact",
    "declared",
    "import-resolved",
    "heuristic",
})
_SHA256_RE = re.compile(r"[0-9a-f]{64}")


class GraphContractError(ValueError):
    def __init__(
        self,
        code: str,
        message: str,
        details: dict[str, JSONValue] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details or {}


@dataclass(frozen=True, slots=True)
class GraphNodeRef:
    id: str
    namespace: str
    kind: str
    attributes: dict[str, JSONValue]

    def to_dict(self) -> dict[str, JSONValue]:
        return {
            "id": self.id,
            "namespace": self.namespace,
            "kind": self.kind,
            "attributes": self.attributes,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> GraphNodeRef:
        _require_keys(
            value,
            {"id", "namespace", "kind", "attributes"},
            code="INVALID_GRAPH_SCHEMA",
            record="node",
        )
        node_id = _nonempty_string(value["id"], "id", "INVALID_GRAPH_SCHEMA")
        namespace = _nonempty_string(
            value["namespace"], "namespace", "INVALID_GRAPH_SCHEMA"
        )
        kind = _nonempty_string(value["kind"], "kind", "INVALID_GRAPH_SCHEMA")
        attributes = value["attributes"]
        if not isinstance(attributes, Mapping):
            raise GraphContractError(
                "INVALID_GRAPH_SCHEMA",
                "Graph node attributes must be an object",
                {"field": "attributes"},
            )
        normalized_attributes = dict(attributes)
        if not all(isinstance(key, str) for key in normalized_attributes):
            raise GraphContractError(
                "INVALID_GRAPH_SCHEMA",
                "Graph node attribute keys must be strings",
                {"field": "attributes"},
            )
        if not _is_json_value(normalized_attributes):
            raise GraphContractError(
                "INVALID_GRAPH_SCHEMA",
                "Graph node attributes must contain JSON-compatible values",
                {"field": "attributes"},
            )
        return cls(
            id=node_id,
            namespace=namespace,
            kind=kind,
            attributes=cast(dict[str, JSONValue], normalized_attributes),
        )


@dataclass(frozen=True, slots=True)
class GraphEvidence:
    file: str
    line: int
    content_hash: str

    def to_dict(self) -> dict[str, JSONValue]:
        return {
            "file": self.file,
            "line": self.line,
            "content_hash": self.content_hash,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> GraphEvidence:
        _require_keys(
            value,
            {"file", "line", "content_hash"},
            code="GRAPH_EVIDENCE_INVALID",
            record="evidence",
        )
        evidence = cls(
            file=_nonempty_string(
                value["file"], "file", "GRAPH_EVIDENCE_INVALID"
            ),
            line=value["line"],
            content_hash=_nonempty_string(
                value["content_hash"],
                "content_hash",
                "GRAPH_EVIDENCE_INVALID",
            ),
        )
        _validate_evidence(evidence)
        return evidence


@dataclass(frozen=True, slots=True)
class GraphEdge:
    from_id: str
    to_id: str
    type: str
    directed: bool
    namespace: str
    resolution: ResolutionTier
    evidence: GraphEvidence

    def to_dict(self) -> dict[str, JSONValue]:
        return {
            "from": self.from_id,
            "to": self.to_id,
            "type": self.type,
            "directed": self.directed,
            "namespace": self.namespace,
            "resolution": self.resolution,
            "evidence": self.evidence.to_dict(),
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> GraphEdge:
        _require_keys(
            value,
            {
                "from",
                "to",
                "type",
                "directed",
                "namespace",
                "resolution",
                "evidence",
            },
            code="INVALID_GRAPH_EDGE",
            record="edge",
        )
        resolution = _nonempty_string(
            value["resolution"], "resolution", "INVALID_GRAPH_EDGE"
        )
        if resolution not in RESOLUTION_TIERS:
            raise GraphContractError(
                "GRAPH_RESOLUTION_UNSUPPORTED",
                "Unsupported graph resolution tier",
                {"resolution": resolution},
            )
        if not isinstance(value["directed"], bool):
            raise GraphContractError(
                "INVALID_GRAPH_EDGE",
                "Graph edge directed must be a boolean",
                {"field": "directed"},
            )
        evidence_value = value["evidence"]
        if not isinstance(evidence_value, Mapping):
            raise GraphContractError(
                "GRAPH_EVIDENCE_INVALID",
                "Graph edge evidence must be an object",
                {"field": "evidence"},
            )
        edge = cls(
            from_id=_nonempty_string(value["from"], "from", "INVALID_GRAPH_EDGE"),
            to_id=_nonempty_string(value["to"], "to", "INVALID_GRAPH_EDGE"),
            type=_nonempty_string(value["type"], "type", "INVALID_GRAPH_EDGE"),
            directed=value["directed"],
            namespace=_nonempty_string(
                value["namespace"], "namespace", "INVALID_GRAPH_EDGE"
            ),
            resolution=cast(ResolutionTier, resolution),
            evidence=GraphEvidence.from_dict(evidence_value),
        )
        if edge.from_id == edge.to_id:
            raise GraphContractError(
                "INVALID_GRAPH_EDGE",
                "Graph edge endpoints must be different",
                {"from": edge.from_id, "to": edge.to_id},
            )
        return edge


@dataclass(frozen=True, slots=True)
class GraphContribution:
    schema_version: int
    namespace: str
    nodes: tuple[GraphNodeRef, ...]
    edges: tuple[GraphEdge, ...]

    def to_dict(self) -> dict[str, JSONValue]:
        return {
            "schema_version": self.schema_version,
            "namespace": self.namespace,
            "nodes": [node.to_dict() for node in self.nodes],
            "edges": [edge.to_dict() for edge in self.edges],
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> GraphContribution:
        _require_keys(
            value,
            {"schema_version", "namespace", "nodes", "edges"},
            code="INVALID_GRAPH_SCHEMA",
            record="contribution",
        )
        schema_version = value["schema_version"]
        if not isinstance(schema_version, int) or isinstance(schema_version, bool):
            raise GraphContractError(
                "INVALID_GRAPH_SCHEMA",
                "Graph schema version must be an integer",
                {"schema_version": cast(Any, schema_version)},
            )
        if schema_version != GRAPH_SCHEMA_VERSION:
            raise GraphContractError(
                "INVALID_GRAPH_SCHEMA",
                "Unsupported graph schema version",
                {"schema_version": schema_version},
            )
        namespace = _nonempty_string(
            value["namespace"], "namespace", "INVALID_GRAPH_SCHEMA"
        )
        node_values = value["nodes"]
        edge_values = value["edges"]
        if not isinstance(node_values, list) or not isinstance(edge_values, list):
            raise GraphContractError(
                "INVALID_GRAPH_SCHEMA",
                "Graph contribution nodes and edges must be lists",
                {},
            )
        if len(node_values) + len(edge_values) > MAX_GRAPH_CONTRIBUTION_RECORDS:
            raise GraphContractError(
                "INVALID_GRAPH_SCHEMA",
                "Graph contribution exceeds the record limit",
                {"limit": MAX_GRAPH_CONTRIBUTION_RECORDS},
            )
        nodes = tuple(
            GraphNodeRef.from_dict(_mapping(item, "node")) for item in node_values
        )
        edges = tuple(
            GraphEdge.from_dict(_mapping(item, "edge")) for item in edge_values
        )
        mismatched_nodes = [node.id for node in nodes if node.namespace != namespace]
        mismatched_edges = [
            index for index, edge in enumerate(edges) if edge.namespace != namespace
        ]
        if mismatched_nodes or mismatched_edges:
            raise GraphContractError(
                "INVALID_GRAPH_SCHEMA",
                "Graph contribution records must match the contribution namespace",
                {
                    "namespace": namespace,
                    "node_ids": mismatched_nodes,
                    "edge_indexes": mismatched_edges,
                },
            )
        return cls(
            schema_version=schema_version,
            namespace=namespace,
            nodes=nodes,
            edges=edges,
        )


def validate_graph_edges(
    edges: list[GraphEdge],
    *,
    indexed_nodes: Mapping[str, Mapping[str, Any]],
) -> None:
    for edge_index, edge in enumerate(edges):
        _validate_evidence(edge.evidence, edge_index=edge_index)
        if edge.from_id == edge.to_id:
            raise GraphContractError(
                "INVALID_GRAPH_EDGE",
                "Graph edge endpoints must be different",
                {"edge_index": edge_index},
            )
        if edge.namespace != "loci" or edge.type != "contains":
            raise GraphContractError(
                "GRAPH_EDGE_TYPE_UNSUPPORTED",
                "Unsupported graph edge type",
                {
                    "edge_index": edge_index,
                    "namespace": edge.namespace,
                    "type": edge.type,
                },
            )
        if edge.resolution != "exact":
            raise GraphContractError(
                "GRAPH_RESOLUTION_UNSUPPORTED",
                "Resolution tier is not permitted for this graph edge type",
                {"edge_index": edge_index, "resolution": edge.resolution},
            )
        if edge.directed is not True:
            raise GraphContractError(
                "INVALID_GRAPH_EDGE",
                "Contains edges must be directed",
                {"edge_index": edge_index, "field": "directed"},
            )

        missing_ids = [
            node_id
            for node_id in (edge.from_id, edge.to_id)
            if node_id not in indexed_nodes
        ]
        if missing_ids:
            raise GraphContractError(
                "GRAPH_ENDPOINT_NOT_FOUND",
                "Graph edge endpoint is not indexed",
                {"edge_index": edge_index, "missing_ids": missing_ids},
            )

        parent = indexed_nodes[edge.from_id]
        child = indexed_nodes[edge.to_id]
        if (
            parent.get("language") != "markdown"
            or child.get("language") != "markdown"
            or parent.get("file_path") != child.get("file_path")
        ):
            raise GraphContractError(
                "INVALID_GRAPH_EDGE",
                "Contains edge endpoints must be Markdown symbols in the same file",
                {"edge_index": edge_index},
            )
        expected_evidence = {
            "file": child.get("file_path"),
            "line": child.get("line"),
            "content_hash": child.get("content_hash"),
        }
        actual_evidence = edge.evidence.to_dict()
        for field, expected in expected_evidence.items():
            if actual_evidence[field] != expected:
                raise GraphContractError(
                    "GRAPH_EVIDENCE_INVALID",
                    "Graph evidence does not identify the target node",
                    {
                        "edge_index": edge_index,
                        "field": field,
                        "expected": cast(JSONValue, expected),
                        "actual": actual_evidence[field],
                    },
                )


def _mapping(value: Any, record: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise GraphContractError(
            "INVALID_GRAPH_SCHEMA",
            f"Graph {record} must be an object",
            {"record": record},
        )
    return value


def _require_keys(
    value: Mapping[str, Any],
    expected: set[str],
    *,
    code: str,
    record: str,
) -> None:
    actual = set(value)
    if actual != expected:
        raise GraphContractError(
            code,
            f"Invalid graph {record} fields",
            {
                "record": record,
                "missing": sorted(expected - actual),
                "unknown": sorted(actual - expected),
            },
        )


def _nonempty_string(value: Any, field: str, code: str) -> str:
    if not isinstance(value, str) or not value:
        raise GraphContractError(
            code,
            f"Graph {field} must be a non-empty string",
            {"field": field},
        )
    return value


def _validate_evidence(
    evidence: GraphEvidence,
    *,
    edge_index: int | None = None,
) -> None:
    details: dict[str, JSONValue] = {}
    if edge_index is not None:
        details["edge_index"] = edge_index
    path = PurePosixPath(evidence.file)
    if (
        not evidence.file
        or "\\" in evidence.file
        or path.is_absolute()
        or ".." in path.parts
        or str(path) != evidence.file
    ):
        details["field"] = "file"
    elif (
        not isinstance(evidence.line, int)
        or isinstance(evidence.line, bool)
        or evidence.line < 1
    ):
        details["field"] = "line"
    elif not isinstance(evidence.content_hash, str) or not _SHA256_RE.fullmatch(
        evidence.content_hash
    ):
        details["field"] = "content_hash"
    else:
        return
    raise GraphContractError(
        "GRAPH_EVIDENCE_INVALID",
        "Invalid graph evidence",
        details,
    )


def _is_json_value(value: Any) -> bool:
    if isinstance(value, float):
        return math.isfinite(value)
    if value is None or isinstance(value, (bool, int, str)):
        return True
    if isinstance(value, list):
        return all(_is_json_value(item) for item in value)
    if isinstance(value, dict):
        return all(
            isinstance(key, str) and _is_json_value(item)
            for key, item in value.items()
        )
    return False
