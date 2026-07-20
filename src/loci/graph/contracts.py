from __future__ import annotations

import math
import re
import unicodedata
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import TYPE_CHECKING, Any, Literal, Mapping, TypeAlias, cast

if TYPE_CHECKING:
    from .imports import ImportRecord
    from .references import SymbolReferenceRecord


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

GRAPH_SCHEMA_VERSION = 1  # Public contribution and retrieval envelopes.
GRAPH_STATE_SCHEMA_VERSION = 7  # Persisted index.json.graph envelope only.
MAX_GRAPH_CONTRIBUTION_RECORDS = 10_000
RESOLUTION_TIERS = frozenset({
    "exact",
    "declared",
    "import-resolved",
    "heuristic",
})
_SHA256_RE = re.compile(r"[0-9a-f]{64}")
_GO_KEYWORDS = frozenset({
    "break", "default", "func", "interface", "select", "case", "defer",
    "go", "map", "struct", "chan", "else", "goto", "package", "switch",
    "const", "fallthrough", "if", "range", "type", "continue", "for",
    "import", "return", "var",
})
_RUST_TARGET_KINDS = frozenset({
    "lib", "bin", "example", "test", "bench", "build_script",
})
_RUST_EDITIONS = frozenset({"2015", "2018", "2021", "2024"})


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
    file_hashes: Mapping[str, str] | None = None,
    imports: Sequence[ImportRecord] = (),
    symbol_references: Sequence[SymbolReferenceRecord] = (),
) -> None:
    reference_index = {}
    if symbol_references:
        from ._reference_validation import index_reference_edge_records

        reference_index = index_reference_edge_records(symbol_references)
    for edge_index, edge in enumerate(edges):
        _validate_evidence(edge.evidence, edge_index=edge_index)
        if edge.from_id == edge.to_id:
            raise GraphContractError(
                "INVALID_GRAPH_EDGE",
                "Graph edge endpoints must be different",
                {"edge_index": edge_index},
            )
        edge_kind = (edge.namespace, edge.type)
        if edge_kind == ("loci", "contains"):
            _validate_contains_edge(
                edge,
                edge_index=edge_index,
                indexed_nodes=indexed_nodes,
            )
        elif edge_kind in {
            ("loci", "imports"),
            ("loci", "imports_type"),
        }:
            _validate_import_edge(
                edge,
                edge_index=edge_index,
                indexed_nodes=indexed_nodes,
                file_hashes=file_hashes,
                imports=imports,
            )
        elif edge_kind in {
            ("loci", "references"),
            ("loci", "references_type"),
        }:
            _validate_reference_edge(
                edge,
                edge_index=edge_index,
                indexed_nodes=indexed_nodes,
                file_hashes=file_hashes,
                reference_index=reference_index,
            )
        else:
            raise GraphContractError(
                "GRAPH_EDGE_TYPE_UNSUPPORTED",
                "Unsupported graph edge type",
                {
                    "edge_index": edge_index,
                    "namespace": edge.namespace,
                    "type": edge.type,
                },
            )


def _validate_reference_edge(
    edge: GraphEdge,
    *,
    edge_index: int,
    indexed_nodes: Mapping[str, Mapping[str, Any]],
    file_hashes: Mapping[str, str] | None,
    reference_index: Mapping[
        tuple[str, str, bool, str, int, str],
        Sequence[SymbolReferenceRecord],
    ],
) -> None:
    from ._reference_validation import validate_reference_edge

    validate_reference_edge(
        edge,
        edge_index=edge_index,
        indexed_nodes=indexed_nodes,
        file_hashes=file_hashes,
        reference_index=reference_index,
    )


def _validate_contains_edge(
    edge: GraphEdge,
    *,
    edge_index: int,
    indexed_nodes: Mapping[str, Mapping[str, Any]],
) -> None:
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

    parent, child = _indexed_edge_endpoints(
        edge,
        edge_index=edge_index,
        indexed_nodes=indexed_nodes,
    )
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


def _validate_import_edge(
    edge: GraphEdge,
    *,
    edge_index: int,
    indexed_nodes: Mapping[str, Mapping[str, Any]],
    file_hashes: Mapping[str, str] | None,
    imports: Sequence[ImportRecord],
) -> None:
    if edge.resolution != "import-resolved":
        raise GraphContractError(
            "GRAPH_RESOLUTION_UNSUPPORTED",
            "Resolution tier is not permitted for this graph edge type",
            {"edge_index": edge_index, "resolution": edge.resolution},
        )
    if edge.directed is not True:
        raise GraphContractError(
            "INVALID_GRAPH_EDGE",
            "Import edges must be directed",
            {"edge_index": edge_index, "field": "directed"},
        )

    source, target = _indexed_edge_endpoints(
        edge,
        edge_index=edge_index,
        indexed_nodes=indexed_nodes,
    )
    source_file = source.get("file_path")
    if source.get("kind") != "file" or not isinstance(source_file, str):
        raise GraphContractError(
            "INVALID_GRAPH_EDGE",
            "Import edge source must be an indexed file node",
            {
                "edge_index": edge_index,
                "field": "endpoints",
                "source_kind": cast(JSONValue, source.get("kind")),
            },
        )
    if target.get("kind") in {"package", "crate"} and edge.type != "imports":
        target_description = (
            "Go package" if target.get("kind") == "package" else "Rust crate"
        )
        raise GraphContractError(
            "INVALID_GRAPH_EDGE",
            f"{target_description} imports cannot use the type-only edge type",
            {"edge_index": edge_index, "field": "type"},
        )

    if edge.evidence.file != source_file:
        _raise_import_evidence_error(
            edge_index,
            "file",
            expected=source_file,
            actual=edge.evidence.file,
        )

    current_hash = file_hashes.get(source_file) if file_hashes is not None else None
    if edge.evidence.content_hash != current_hash:
        _raise_import_evidence_error(
            edge_index,
            "content_hash",
            expected=current_hash,
            actual=edge.evidence.content_hash,
        )

    record_type_only = edge.type == "imports_type"
    candidates = [
        record
        for record in imports
        if (
            record.status == "resolved"
            and record.source_id == edge.from_id
            and record.target_id == edge.to_id
            and record.raw.source_file == source_file
            and record.raw.type_only is record_type_only
        )
    ]
    if not candidates:
        raise GraphContractError(
            "GRAPH_EVIDENCE_INVALID",
            "Import edge is not backed by a matching resolved import record",
            {"edge_index": edge_index, "field": "import_record"},
        )

    target_kinds = {record.target_kind for record in candidates}
    if target_kinds == {"file"}:
        target_file = target.get("file_path")
        if target.get("kind") != "file" or not isinstance(target_file, str):
            raise GraphContractError(
                "INVALID_GRAPH_EDGE",
                "File import target must be an indexed file node",
                {
                    "edge_index": edge_index,
                    "field": "endpoints",
                    "target_kind": cast(JSONValue, target.get("kind")),
                },
            )
        candidates = [
            record
            for record in candidates
            if record.target_file == target_file and record.target_package is None
        ]
    elif target_kinds == {"package"}:
        package_paths = {
            record.target_package
            for record in candidates
            if record.target_file is None and record.target_package is not None
        }
        if len(package_paths) != 1:
            raise GraphContractError(
                "GRAPH_EVIDENCE_INVALID",
                "Import edge has inconsistent package target records",
                {"edge_index": edge_index, "field": "import_record"},
            )
        _validate_go_package_endpoint(
            target,
            package_path=next(iter(package_paths)),
            edge_index=edge_index,
        )
    elif target_kinds == {"crate"}:
        crate_names = {
            record.target_crate
            for record in candidates
            if (
                record.target_file is None
                and record.target_package is None
                and record.target_crate is not None
            )
        }
        if len(crate_names) != 1:
            raise GraphContractError(
                "GRAPH_EVIDENCE_INVALID",
                "Import edge has inconsistent crate target records",
                {"edge_index": edge_index, "field": "import_record"},
            )
        crate_qualified_name = next(iter(crate_names))
        crate_root = _validate_rust_crate_endpoint(
            target,
            crate_qualified_name=crate_qualified_name,
            edge_index=edge_index,
            indexed_nodes=indexed_nodes,
            file_hashes=file_hashes,
        )
        if source_file == crate_root:
            raise GraphContractError(
                "INVALID_GRAPH_EDGE",
                "Rust crate-root files cannot import their own crate endpoint",
                {"edge_index": edge_index, "field": "endpoints"},
            )
    else:
        raise GraphContractError(
            "GRAPH_EVIDENCE_INVALID",
            "Import edge has inconsistent target kinds",
            {"edge_index": edge_index, "field": "import_record"},
        )

    if not candidates:
        raise GraphContractError(
            "GRAPH_EVIDENCE_INVALID",
            "Import edge is not backed by a matching resolved import record",
            {"edge_index": edge_index, "field": "import_record"},
        )

    line_candidates = [
        record for record in candidates if record.raw.line == edge.evidence.line
    ]
    if not line_candidates:
        _raise_import_evidence_error(
            edge_index,
            "line",
            expected=sorted({record.raw.line for record in candidates}),
            actual=edge.evidence.line,
        )
    if not any(
        record.raw.source_hash == edge.evidence.content_hash
        for record in line_candidates
    ):
        _raise_import_evidence_error(
            edge_index,
            "content_hash",
            expected=sorted({record.raw.source_hash for record in line_candidates}),
            actual=edge.evidence.content_hash,
        )


def _validate_go_package_endpoint(
    target: Mapping[str, Any],
    *,
    package_path: str,
    edge_index: int,
) -> None:
    metadata = target.get("metadata")
    loci = metadata.get("loci") if isinstance(metadata, Mapping) else None
    package_name = loci.get("package_name") if isinstance(loci, Mapping) else None
    if (
        target.get("kind") != "package"
        or target.get("language") != "go"
        or target.get("qualified_name") != package_path
        or not isinstance(loci, Mapping)
        or loci.get("go_package_node") is not True
        or loci.get("import_path") != package_path
        or not isinstance(package_name, str)
        or target.get("name") != package_name
        or package_name == "main"
        or not _valid_go_identifier(package_name)
    ):
        raise GraphContractError(
            "INVALID_GRAPH_EDGE",
            "Go import target must be the matching indexed package node",
            {
                "edge_index": edge_index,
                "field": "target",
                "target_id": cast(JSONValue, target.get("id")),
            },
        )


def _validate_rust_crate_endpoint(
    target: Mapping[str, Any],
    *,
    crate_qualified_name: str,
    edge_index: int,
    indexed_nodes: Mapping[str, Mapping[str, Any]],
    file_hashes: Mapping[str, str] | None,
) -> str:
    metadata = target.get("metadata")
    loci = metadata.get("loci") if isinstance(metadata, Mapping) else None
    manifest = loci.get("manifest") if isinstance(loci, Mapping) else None
    package_name = loci.get("package_name") if isinstance(loci, Mapping) else None
    package_root = loci.get("package_root") if isinstance(loci, Mapping) else None
    target_kind = loci.get("target_kind") if isinstance(loci, Mapping) else None
    target_name = loci.get("target_name") if isinstance(loci, Mapping) else None
    rust_crate_name = loci.get("crate_name") if isinstance(loci, Mapping) else None
    crate_root = loci.get("crate_root") if isinstance(loci, Mapping) else None
    edition = loci.get("edition") if isinstance(loci, Mapping) else None
    required_features = (
        loci.get("required_features") if isinstance(loci, Mapping) else None
    )
    expected_name = (
        f"{manifest}::{target_kind}:{rust_crate_name}"
        if (
            isinstance(manifest, str)
            and isinstance(target_kind, str)
            and isinstance(rust_crate_name, str)
        )
        else None
    )
    expected_package_root = (
        PurePosixPath(manifest).parent.as_posix()
        if isinstance(manifest, str)
        else None
    )
    current_root_hash = (
        file_hashes.get(crate_root)
        if file_hashes is not None and isinstance(crate_root, str)
        else None
    )
    root = (
        indexed_nodes.get(f"{crate_root}::__file__#file")
        if isinstance(crate_root, str)
        else None
    )
    valid_root = (
        isinstance(root, Mapping)
        and root.get("kind") == "file"
        and root.get("language") == "rust"
        and root.get("file_path") == crate_root
        and root.get("content_hash") == current_root_hash
    )
    valid_features = (
        isinstance(required_features, list)
        and all(isinstance(item, str) and item for item in required_features)
        and required_features == sorted(set(required_features))
    )
    if (
        target.get("kind") != "crate"
        or target.get("language") != "rust"
        or target.get("id") != f"{crate_qualified_name}#crate"
        or target.get("name") != rust_crate_name
        or target.get("qualified_name") != crate_qualified_name
        or target.get("qualified_name") != expected_name
        or target.get("file_path") != crate_root
        or target.get("byte_offset") != 0
        or target.get("byte_length") != 0
        or target.get("signature") != crate_qualified_name
        or target.get("content_hash") != current_root_hash
        or not valid_root
        or target.get("line") != 1
        or target.get("end_line") != 1
        or not isinstance(loci, Mapping)
        or loci.get("rust_crate_node") is not True
        or not _valid_relative_path(manifest, allow_dot=False)
        or PurePosixPath(manifest).name != "Cargo.toml"
        or not isinstance(package_name, str)
        or not package_name
        or not _valid_relative_path(package_root, allow_dot=True)
        or package_root != expected_package_root
        or target_kind not in _RUST_TARGET_KINDS
        or not isinstance(target_name, str)
        or not target_name
        or not isinstance(rust_crate_name, str)
        or not rust_crate_name
        or not _valid_relative_path(crate_root, allow_dot=False)
        or edition not in _RUST_EDITIONS
        or not valid_features
    ):
        raise GraphContractError(
            "INVALID_GRAPH_EDGE",
            "Rust import target must be the matching indexed crate node",
            {
                "edge_index": edge_index,
                "field": "target",
                "target_id": cast(JSONValue, target.get("id")),
            },
        )
    assert isinstance(crate_root, str)
    return crate_root


def _valid_relative_path(value: Any, *, allow_dot: bool) -> bool:
    if not isinstance(value, str) or not value or "\\" in value:
        return False
    path = PurePosixPath(value)
    return (
        not path.is_absolute()
        and ".." not in path.parts
        and path.as_posix() == value
        and (allow_dot or value != ".")
    )


def _valid_go_identifier(value: str) -> bool:
    if not value or value == "_" or value in _GO_KEYWORDS:
        return False
    for index, char in enumerate(value):
        category = unicodedata.category(char)
        is_letter = char == "_" or category.startswith("L")
        if not is_letter and not (index > 0 and category == "Nd"):
            return False
    return True


def _indexed_edge_endpoints(
    edge: GraphEdge,
    *,
    edge_index: int,
    indexed_nodes: Mapping[str, Mapping[str, Any]],
) -> tuple[Mapping[str, Any], Mapping[str, Any]]:
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
    return indexed_nodes[edge.from_id], indexed_nodes[edge.to_id]


def _raise_import_evidence_error(
    edge_index: int,
    field: str,
    *,
    expected: JSONValue,
    actual: JSONValue,
) -> None:
    raise GraphContractError(
        "GRAPH_EVIDENCE_INVALID",
        "Graph evidence does not identify the resolved import",
        {
            "edge_index": edge_index,
            "field": field,
            "expected": expected,
            "actual": actual,
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
