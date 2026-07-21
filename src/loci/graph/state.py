from __future__ import annotations

import math
import re
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Any, Literal, Mapping, Sequence, cast

from loci.parser.imports import RawImport
from loci.parser.reference_models import RawLocalExport

from .contracts import (
    GRAPH_STATE_SCHEMA_VERSION,
    GraphContractError,
    GraphContribution,
    GraphEdge,
    GraphNodeRef,
    JSONValue,
)
from .calls import CallRecord
from .imports import (
    ImportRecord,
    _import_record_from_state_dict,
    _import_record_to_state_dict,
    _is_inline_rust_module,
    _raw_import_from_state_dict,
    _raw_import_to_state_dict,
)
from .profiles import LoadedGraphProfile
from .references import SymbolReferenceRecord


GraphDiagnosticSeverity = Literal["info", "warning", "error"]
_SHA256_RE = re.compile(r"[0-9a-f]{64}")


@dataclass(frozen=True, slots=True)
class GraphDiagnostic:
    severity: GraphDiagnosticSeverity
    code: str
    message: str
    source: str | None
    details: dict[str, JSONValue]

    def to_dict(self) -> dict[str, JSONValue]:
        return {
            "severity": self.severity,
            "code": self.code,
            "message": self.message,
            "source": self.source,
            "details": self.details,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> GraphDiagnostic:
        _require_keys(
            value,
            {"severity", "code", "message", "source", "details"},
            "diagnostic",
        )
        severity = value["severity"]
        if severity not in {"info", "warning", "error"}:
            raise _error("Invalid graph diagnostic severity", field="severity")
        code = _nonempty_string(value["code"], "code")
        message = _nonempty_string(value["message"], "message")
        source = value["source"]
        if source is not None and not isinstance(source, str):
            raise _error("Graph diagnostic source must be a string or null", field="source")
        details = value["details"]
        if not isinstance(details, Mapping) or not _is_json_value(dict(details)):
            raise _error("Graph diagnostic details must be a JSON object", field="details")
        return cls(
            severity=cast(GraphDiagnosticSeverity, severity),
            code=code,
            message=message,
            source=source,
            details=cast(dict[str, JSONValue], dict(details)),
        )


@dataclass(frozen=True, slots=True)
class LoadedGraphContribution:
    source: str
    content_hash: str
    contribution: GraphContribution | None

    def to_dict(self) -> dict[str, JSONValue]:
        return {
            "source": self.source,
            "content_hash": self.content_hash,
            "contribution": (
                self.contribution.to_dict() if self.contribution is not None else None
            ),
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> LoadedGraphContribution:
        _require_keys(
            value,
            {"source", "content_hash", "contribution"},
            "loaded contribution",
        )
        source = _relative_path(value["source"], "source")
        content_hash = _sha256(value["content_hash"], "content_hash")
        contribution_value = value["contribution"]
        if contribution_value is None:
            contribution = None
        elif isinstance(contribution_value, Mapping):
            contribution = GraphContribution.from_dict(contribution_value)
        else:
            raise _error(
                "Graph contribution must be an object or null",
                field="contribution",
            )
        return cls(
            source=source,
            content_hash=content_hash,
            contribution=contribution,
        )


@dataclass(frozen=True, slots=True)
class GraphIndexState:
    schema_version: int
    profiles: tuple[LoadedGraphProfile, ...]
    nodes: tuple[GraphNodeRef, ...]
    edges: tuple[GraphEdge, ...]
    imports: tuple[ImportRecord, ...]
    rust_module_observations: tuple[RawImport, ...]
    exports: tuple[RawLocalExport, ...]
    symbol_references: tuple[SymbolReferenceRecord, ...]
    calls: tuple[CallRecord, ...]
    contributions: tuple[LoadedGraphContribution, ...]
    input_hashes: dict[str, str]
    diagnostics: tuple[GraphDiagnostic, ...]

    def to_dict(self) -> dict[str, JSONValue]:
        return {
            "schema_version": self.schema_version,
            "profiles": [profile.to_dict() for profile in self.profiles],
            "nodes": [node.to_dict() for node in self.nodes],
            "edges": [edge.to_dict() for edge in self.edges],
            "imports": [
                _import_record_to_state_dict(record)
                for record in self.imports
            ],
            "rust_module_observations": [
                _raw_import_to_state_dict(observation)
                for observation in self.rust_module_observations
            ],
            "exports": [
                cast(dict[str, JSONValue], export.to_dict())
                for export in self.exports
            ],
            "symbol_references": [
                record.to_dict() for record in self.symbol_references
            ],
            "calls": [record.to_dict() for record in self.calls],
            "contributions": [
                contribution.to_dict() for contribution in self.contributions
            ],
            "input_hashes": dict(sorted(self.input_hashes.items())),
            "diagnostics": [diagnostic.to_dict() for diagnostic in self.diagnostics],
        }

    @classmethod
    def empty(
        cls,
        *,
        edges: Sequence[GraphEdge] = (),
    ) -> GraphIndexState:
        return cls(
            schema_version=GRAPH_STATE_SCHEMA_VERSION,
            profiles=(),
            nodes=(),
            edges=tuple(edges),
            imports=(),
            rust_module_observations=(),
            exports=(),
            symbol_references=(),
            calls=(),
            contributions=(),
            input_hashes={},
            diagnostics=(),
        )

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> GraphIndexState:
        if (
            "schema_version" in value
            and value["schema_version"] != GRAPH_STATE_SCHEMA_VERSION
        ):
            raise _error(
                "Unsupported graph state schema version",
                field="schema_version",
                schema_version=cast(Any, value["schema_version"]),
            )
        _require_keys(
            value,
            {
                "schema_version",
                "profiles",
                "nodes",
                "edges",
                "imports",
                "rust_module_observations",
                "exports",
                "symbol_references",
                "calls",
                "contributions",
                "input_hashes",
                "diagnostics",
            },
            "state",
        )
        profiles = tuple(
            LoadedGraphProfile.from_dict(_mapping(item, "loaded profile"))
            for item in _list(value["profiles"], "profiles")
        )
        nodes = tuple(
            GraphNodeRef.from_dict(_mapping(item, "node"))
            for item in _list(value["nodes"], "nodes")
        )
        edges = tuple(
            GraphEdge.from_dict(_mapping(item, "edge"))
            for item in _list(value["edges"], "edges")
        )
        imports = tuple(
            _import_record_from_state_dict(_mapping(item, "import record"))
            for item in _list(value["imports"], "imports")
        )
        rust_module_observations = tuple(
            _rust_module_observation_from_dict(item)
            for item in _list(
                value["rust_module_observations"],
                "rust_module_observations",
            )
        )
        exports = tuple(
            _local_export_from_dict(item)
            for item in _list(value["exports"], "exports")
        )
        symbol_references = tuple(
            _symbol_reference_from_dict(item)
            for item in _list(value["symbol_references"], "symbol_references")
        )
        calls = tuple(
            _call_record_from_dict(item)
            for item in _list(value["calls"], "calls")
        )
        contributions = tuple(
            LoadedGraphContribution.from_dict(
                _mapping(item, "loaded contribution")
            )
            for item in _list(value["contributions"], "contributions")
        )
        input_hash_values = value["input_hashes"]
        if not isinstance(input_hash_values, Mapping):
            raise _error("Graph input hashes must be an object", field="input_hashes")
        input_hashes: dict[str, str] = {}
        for path, content_hash in input_hash_values.items():
            try:
                normalized_path = _relative_path(path, "input_hashes")
                normalized_hash = _sha256(content_hash, "input_hashes")
            except GraphContractError as exc:
                raise _error(
                    "Invalid graph input hash",
                    field="input_hashes",
                ) from exc
            input_hashes[normalized_path] = normalized_hash
        diagnostics = tuple(
            GraphDiagnostic.from_dict(_mapping(item, "diagnostic"))
            for item in _list(value["diagnostics"], "diagnostics")
        )
        return cls(
            schema_version=GRAPH_STATE_SCHEMA_VERSION,
            profiles=profiles,
            nodes=nodes,
            edges=edges,
            imports=imports,
            rust_module_observations=rust_module_observations,
            exports=exports,
            symbol_references=symbol_references,
            calls=calls,
            contributions=contributions,
            input_hashes=dict(sorted(input_hashes.items())),
            diagnostics=diagnostics,
        )


def _rust_module_observation_from_dict(value: Any) -> RawImport:
    observation = _raw_import_from_state_dict(
        _mapping(value, "Rust module observation")
    )
    if not _is_inline_rust_module(observation):
        raise _error(
            "Graph Rust module observation must describe an inline module",
            field="rust_module_observations",
        )
    return observation


def _local_export_from_dict(value: Any) -> RawLocalExport:
    try:
        return RawLocalExport.from_dict(_mapping(value, "local export"))
    except GraphContractError:
        raise
    except (KeyError, TypeError, ValueError) as exc:
        raise _error("Invalid graph local export", field="exports") from exc


def _symbol_reference_from_dict(value: Any) -> SymbolReferenceRecord:
    try:
        return SymbolReferenceRecord.from_dict(
            _mapping(value, "symbol reference record")
        )
    except GraphContractError:
        raise
    except (KeyError, TypeError, ValueError) as exc:
        raise _error(
            "Invalid graph symbol reference",
            field="symbol_references",
        ) from exc


def _call_record_from_dict(value: Any) -> CallRecord:
    try:
        return CallRecord.from_dict(_mapping(value, "call record"))
    except GraphContractError:
        raise
    except (KeyError, TypeError, ValueError) as exc:
        raise _error("Invalid graph call record", field="calls") from exc


def _require_keys(value: Mapping[str, Any], expected: set[str], record: str) -> None:
    actual = set(value)
    if actual != expected:
        raise _error(
            f"Invalid graph {record} fields",
            record=record,
            missing=sorted(expected - actual),
            unknown=sorted(actual - expected),
        )


def _mapping(value: Any, record: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise _error(f"Graph {record} must be an object", record=record)
    return value


def _list(value: Any, field: str) -> list[Any]:
    if not isinstance(value, list):
        raise _error(f"Graph {field} must be a list", field=field)
    return value


def _nonempty_string(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value:
        raise _error(f"Graph {field} must be a non-empty string", field=field)
    return value


def _sha256(value: Any, field: str) -> str:
    if not isinstance(value, str) or not _SHA256_RE.fullmatch(value):
        raise _error(f"Graph {field} must be a SHA-256 hash", field=field)
    return value


def _relative_path(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value or "\\" in value:
        raise _error(f"Graph {field} must be a relative path", field=field)
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts or path.as_posix() != value:
        raise _error(f"Graph {field} must be a relative path", field=field)
    return value


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


def _error(message: str, **details: Any) -> GraphContractError:
    return GraphContractError(
        "INVALID_GRAPH_SCHEMA",
        message,
        cast(dict[str, JSONValue], details),
    )
