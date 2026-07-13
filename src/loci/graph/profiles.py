from __future__ import annotations

import hashlib
import json
import math
import os
import re
import stat
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Literal, Mapping, Sequence, cast

from .contracts import (
    MAX_GRAPH_CONTRIBUTION_RECORDS,
    GraphContractError,
    JSONValue,
    ResolutionTier,
)


PROFILE_SCHEMA_VERSION = 1
PROFILE_DIR = Path(".loci/graph/profiles")
CONTRIBUTION_DIR = Path(".loci/graph/contributions")

MAX_PROFILE_FILES = 32
MAX_CONTRIBUTION_FILES = 256
MAX_EXTENSION_BYTES = 256 * 1024
MAX_JSON_DEPTH = 16
MAX_JSON_STRING = 4096
MAX_PROFILE_RULES = 128
MAX_CONTRIBUTION_RECORDS = MAX_GRAPH_CONTRIBUTION_RECORDS

ProfileValueType = Literal["string", "string_list"]
ProfileEdgeDirection = Literal["source_to_reference", "reference_to_source"]

_IDENTIFIER_RE = re.compile(r"[a-z][a-z0-9_-]{0,63}")
_SOURCE_RE = re.compile(r"frontmatter\.([a-z][a-z0-9_-]{0,63})")


@dataclass(frozen=True, slots=True)
class GraphNodeSelector:
    language: str
    page_root: bool

    def to_dict(self) -> dict[str, JSONValue]:
        return {"language": self.language, "page_root": self.page_root}

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> GraphNodeSelector:
        _require_keys(value, {"language", "page_root"}, "selector")
        if value["language"] != "markdown" or value["page_root"] is not True:
            raise _error(
                "Stage 2 graph selectors must target Markdown page roots",
                field="selector",
            )
        return cls(language="markdown", page_root=True)


@dataclass(frozen=True, slots=True)
class GraphNodeAttributeRule:
    name: str
    source: str
    value_type: ProfileValueType
    allowed_values: tuple[str, ...]

    def to_dict(self) -> dict[str, JSONValue]:
        return {
            "name": self.name,
            "source": self.source,
            "value_type": self.value_type,
            "allowed_values": list(self.allowed_values),
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> GraphNodeAttributeRule:
        _require_keys(
            value,
            {"name", "source", "value_type", "allowed_values"},
            "node attribute rule",
        )
        name = _identifier(value["name"], "name")
        source = _source(value["source"])
        value_type = value["value_type"]
        if value_type not in {"string", "string_list"}:
            raise _error("Unsupported profile value type", field="value_type")
        allowed_values = _unique_strings(value["allowed_values"], "allowed_values")
        return cls(
            name=name,
            source=source,
            value_type=cast(ProfileValueType, value_type),
            allowed_values=allowed_values,
        )


@dataclass(frozen=True, slots=True)
class GraphNodeRule:
    selector: GraphNodeSelector
    attributes: tuple[GraphNodeAttributeRule, ...]

    def to_dict(self) -> dict[str, JSONValue]:
        return {
            "selector": self.selector.to_dict(),
            "attributes": [attribute.to_dict() for attribute in self.attributes],
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> GraphNodeRule:
        _require_keys(value, {"selector", "attributes"}, "node rule")
        selector = GraphNodeSelector.from_dict(_mapping(value["selector"], "selector"))
        attribute_values = _bounded_list(value["attributes"], "attributes")
        attributes = tuple(
            GraphNodeAttributeRule.from_dict(_mapping(item, "node attribute rule"))
            for item in attribute_values
        )
        _require_unique(
            (attribute.name for attribute in attributes),
            "attribute name",
        )
        _require_unique(
            (attribute.source for attribute in attributes),
            "attribute source",
        )
        return cls(selector=selector, attributes=attributes)


@dataclass(frozen=True, slots=True)
class GraphEdgeTypePolicy:
    type: str
    directed: bool
    allowed_resolutions: tuple[ResolutionTier, ...]

    def to_dict(self) -> dict[str, JSONValue]:
        return {
            "type": self.type,
            "directed": self.directed,
            "allowed_resolutions": list(self.allowed_resolutions),
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> GraphEdgeTypePolicy:
        _require_keys(
            value,
            {"type", "directed", "allowed_resolutions"},
            "edge type",
        )
        edge_type = _identifier(value["type"], "type")
        if value["directed"] is not True:
            raise _error("Stage 2 graph edge types must be directed", field="directed")
        resolutions = _unique_strings(
            value["allowed_resolutions"],
            "allowed_resolutions",
        )
        if resolutions != ("declared",):
            raise GraphContractError(
                "GRAPH_RESOLUTION_UNSUPPORTED",
                "Stage 2 domain edges must use the declared resolution tier",
                {"allowed_resolutions": list(resolutions)},
            )
        return cls(
            type=edge_type,
            directed=True,
            allowed_resolutions=("declared",),
        )


@dataclass(frozen=True, slots=True)
class GraphEdgeRule:
    selector: GraphNodeSelector
    source: str
    type: str
    direction: ProfileEdgeDirection
    resolution: ResolutionTier

    def to_dict(self) -> dict[str, JSONValue]:
        return {
            "selector": self.selector.to_dict(),
            "source": self.source,
            "type": self.type,
            "direction": self.direction,
            "resolution": self.resolution,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> GraphEdgeRule:
        _require_keys(
            value,
            {"selector", "source", "type", "direction", "resolution"},
            "edge rule",
        )
        direction = value["direction"]
        if direction not in {"source_to_reference", "reference_to_source"}:
            raise _error("Unsupported graph edge direction", field="direction")
        if value["resolution"] != "declared":
            raise GraphContractError(
                "GRAPH_RESOLUTION_UNSUPPORTED",
                "Stage 2 domain edges must use the declared resolution tier",
                {"resolution": cast(Any, value["resolution"])},
            )
        return cls(
            selector=GraphNodeSelector.from_dict(
                _mapping(value["selector"], "selector")
            ),
            source=_source(value["source"]),
            type=_identifier(value["type"], "type"),
            direction=cast(ProfileEdgeDirection, direction),
            resolution="declared",
        )


@dataclass(frozen=True, slots=True)
class GraphProfile:
    schema_version: int
    namespace: str
    node_rules: tuple[GraphNodeRule, ...]
    edge_types: tuple[GraphEdgeTypePolicy, ...]
    edge_rules: tuple[GraphEdgeRule, ...]

    def to_dict(self) -> dict[str, JSONValue]:
        return {
            "schema_version": self.schema_version,
            "namespace": self.namespace,
            "node_rules": [rule.to_dict() for rule in self.node_rules],
            "edge_types": [edge_type.to_dict() for edge_type in self.edge_types],
            "edge_rules": [rule.to_dict() for rule in self.edge_rules],
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> GraphProfile:
        _require_keys(
            value,
            {"schema_version", "namespace", "node_rules", "edge_types", "edge_rules"},
            "profile",
        )
        if value["schema_version"] != PROFILE_SCHEMA_VERSION:
            raise _error(
                "Unsupported graph profile schema version",
                field="schema_version",
                schema_version=cast(Any, value["schema_version"]),
            )
        namespace = _identifier(value["namespace"], "namespace")
        if namespace == "loci":
            raise _error("The loci namespace is reserved", field="namespace")

        node_rules = tuple(
            GraphNodeRule.from_dict(_mapping(item, "node rule"))
            for item in _bounded_list(value["node_rules"], "node_rules")
        )
        edge_types = tuple(
            GraphEdgeTypePolicy.from_dict(_mapping(item, "edge type"))
            for item in _bounded_list(value["edge_types"], "edge_types")
        )
        edge_rules = tuple(
            GraphEdgeRule.from_dict(_mapping(item, "edge rule"))
            for item in _bounded_list(value["edge_rules"], "edge_rules")
        )
        _require_unique(
            (
                attribute.name
                for rule in node_rules
                for attribute in rule.attributes
            ),
            "attribute name",
        )
        _require_unique((edge_type.type for edge_type in edge_types), "edge type")
        _require_unique(
            (
                f"{rule.source}:{rule.type}:{rule.direction}"
                for rule in edge_rules
            ),
            "edge rule",
        )
        registered = {edge_type.type for edge_type in edge_types}
        for rule in edge_rules:
            if rule.type not in registered:
                raise _error(
                    "Graph edge rule references an unregistered type",
                    field="type",
                    type=rule.type,
                )
        return cls(
            schema_version=PROFILE_SCHEMA_VERSION,
            namespace=namespace,
            node_rules=node_rules,
            edge_types=edge_types,
            edge_rules=edge_rules,
        )


@dataclass(frozen=True, slots=True)
class LoadedGraphProfile:
    source: str
    content_hash: str
    profile: GraphProfile

    def to_dict(self) -> dict[str, JSONValue]:
        return {
            "source": self.source,
            "content_hash": self.content_hash,
            "profile": self.profile.to_dict(),
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> LoadedGraphProfile:
        _require_keys(value, {"source", "content_hash", "profile"}, "loaded profile")
        source = _relative_path(value["source"], "source")
        content_hash = value["content_hash"]
        if (
            not isinstance(content_hash, str)
            or not re.fullmatch(r"[0-9a-f]{64}", content_hash)
        ):
            raise _error("Graph profile hash must be SHA-256", field="content_hash")
        return cls(
            source=source,
            content_hash=content_hash,
            profile=GraphProfile.from_dict(_mapping(value["profile"], "profile")),
        )


def discover_graph_profile_paths(repo_path: Path) -> tuple[Path, ...]:
    return _discover_extension_paths(
        repo_path,
        PROFILE_DIR,
        limit=MAX_PROFILE_FILES,
        record="profile",
        validate_files=True,
    )


def discover_graph_contribution_paths(repo_path: Path) -> tuple[Path, ...]:
    return _discover_extension_paths(
        repo_path,
        CONTRIBUTION_DIR,
        limit=MAX_CONTRIBUTION_FILES,
        record="contribution",
        validate_files=True,
    )


def discover_graph_profile_candidates(repo_path: Path) -> tuple[Path, ...]:
    """Discover profile candidates while deferring per-file errors to the loader."""
    return _discover_extension_paths(
        repo_path,
        PROFILE_DIR,
        limit=MAX_PROFILE_FILES,
        record="profile",
        validate_files=False,
    )


def discover_graph_contribution_candidates(repo_path: Path) -> tuple[Path, ...]:
    """Discover contribution candidates while retaining valid sibling files."""
    return _discover_extension_paths(
        repo_path,
        CONTRIBUTION_DIR,
        limit=MAX_CONTRIBUTION_FILES,
        record="contribution",
        validate_files=False,
    )


def load_graph_profile(repo_path: Path, path: Path) -> LoadedGraphProfile:
    data, relative, content_hash = read_extension_json(repo_path, path, record="profile")
    return LoadedGraphProfile(
        source=relative,
        content_hash=content_hash,
        profile=GraphProfile.from_dict(_mapping(data, "profile")),
    )


def required_frontmatter_fields(
    profiles: Sequence[GraphProfile | LoadedGraphProfile],
) -> frozenset[str]:
    fields: set[str] = set()
    for item in profiles:
        profile = item.profile if isinstance(item, LoadedGraphProfile) else item
        for rule in profile.node_rules:
            fields.update(_source_field(attribute.source) for attribute in rule.attributes)
        fields.update(_source_field(rule.source) for rule in profile.edge_rules)
    return frozenset(fields)


def read_extension_json(
    repo_path: Path,
    path: Path,
    *,
    record: str,
) -> tuple[Any, str, str]:
    data, relative = read_contained_file(
        repo_path,
        path,
        record=record,
        max_bytes=MAX_EXTENSION_BYTES,
    )
    value = parse_extension_json(data, relative=relative, record=record)
    return value, relative, hashlib.sha256(data).hexdigest()


def parse_extension_json(
    data: bytes,
    *,
    relative: str,
    record: str,
) -> Any:
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise _error(
            f"Graph {record} must be UTF-8 JSON",
            source=relative,
            reason="invalid utf-8",
        ) from exc
    try:
        value = json.loads(
            text,
            object_pairs_hook=_unique_object,
            parse_constant=_reject_constant,
        )
    except (json.JSONDecodeError, RecursionError, ValueError) as exc:
        reason = "duplicate key" if str(exc).startswith("duplicate key:") else "invalid json"
        raise _error(
            f"Invalid graph {record} JSON",
            source=relative,
            reason=reason,
        ) from exc
    _validate_json_bounds(value)
    return value


def read_contained_file(
    repo_path: Path,
    path: Path,
    *,
    record: str,
    max_bytes: int | None = None,
) -> tuple[bytes, str]:
    """Read a regular file without allowing its resolved path to leave the repo."""
    return _read_contained_file(
        repo_path,
        path,
        record=record,
        max_bytes=max_bytes,
    )


def validate_contained_file(
    repo_path: Path,
    path: Path,
    *,
    record: str,
) -> str:
    """Validate containment and regular-file identity without reading content."""
    fd, relative = _open_contained_file(repo_path, path, record=record)
    os.close(fd)
    return relative


def _discover_extension_paths(
    repo_path: Path,
    relative_dir: Path,
    *,
    limit: int,
    record: str,
    validate_files: bool,
) -> tuple[Path, ...]:
    root = repo_path.resolve()
    directory = root / relative_dir
    if not directory.exists():
        if directory.is_symlink():
            raise _error(
                f"Graph {record} directory is an invalid symlink",
                source=relative_dir.as_posix(),
            )
        return ()
    try:
        resolved_dir = directory.resolve(strict=True)
        resolved_dir.relative_to(root)
    except (OSError, ValueError) as exc:
        raise _error(
            f"Graph {record} directory escapes the repository",
            source=relative_dir.as_posix(),
        ) from exc
    if not resolved_dir.is_dir():
        raise _error(
            f"Graph {record} directory is not a directory",
            source=relative_dir.as_posix(),
        )
    try:
        paths = sorted(
            (path for path in directory.iterdir() if path.name.endswith(".json")),
            key=lambda path: path.name,
        )
    except OSError as exc:
        raise _error(
            f"Unable to discover graph {record} files",
            source=relative_dir.as_posix(),
        ) from exc
    if len(paths) > limit:
        raise _error(
            f"Too many graph {record} files",
            source=relative_dir.as_posix(),
            limit=limit,
        )
    if validate_files:
        for path in paths:
            if path.is_symlink() or not path.is_file():
                raise _error(
                    f"Graph {record} must be a regular non-symlink file",
                    source=_relative_source(root, path),
                )
    return tuple(paths)


def _read_contained_file(
    repo_path: Path,
    path: Path,
    *,
    record: str,
    max_bytes: int | None,
) -> tuple[bytes, str]:
    fd, relative = _open_contained_file(repo_path, path, record=record)
    try:
        chunks: list[bytes] = []
        total = 0
        while True:
            chunk = os.read(fd, 64 * 1024)
            if not chunk:
                break
            chunks.append(chunk)
            total += len(chunk)
            if max_bytes is not None and total > max_bytes:
                raise _error(
                    f"Graph {record} exceeds the size limit",
                    source=relative,
                    limit=max_bytes,
                )
        data = b"".join(chunks)
    finally:
        os.close(fd)
    return data, relative


def _open_contained_file(
    repo_path: Path,
    path: Path,
    *,
    record: str,
) -> tuple[int, str]:
    root = repo_path.resolve()
    candidate = path if path.is_absolute() else root / path
    relative = _relative_source(root, candidate)
    if candidate.is_symlink():
        raise _error(
            f"Graph {record} must not be a symlink",
            source=relative,
        )
    try:
        resolved = candidate.resolve(strict=True)
        resolved.relative_to(root)
    except (OSError, ValueError) as exc:
        raise _error(
            f"Graph {record} path escapes the repository",
            source=relative,
        ) from exc

    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        fd = os.open(resolved, flags)
    except OSError as exc:
        raise _error(
            f"Unable to open graph {record}",
            source=relative,
        ) from exc
    try:
        opened = os.fstat(fd)
        current = os.stat(resolved, follow_symlinks=False)
        if not stat.S_ISREG(opened.st_mode) or (
            opened.st_dev,
            opened.st_ino,
        ) != (current.st_dev, current.st_ino):
            raise _error(
                f"Graph {record} changed while opening",
                source=relative,
            )
    except Exception:
        os.close(fd)
        raise
    return fd, relative


def _relative_source(root: Path, path: Path) -> str:
    try:
        return path.absolute().relative_to(root).as_posix()
    except ValueError:
        return str(path)


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate key: {key}")
        result[key] = value
    return result


def _reject_constant(value: str) -> None:
    raise ValueError(f"non-finite number: {value}")


def _validate_json_bounds(value: Any, *, depth: int = 0) -> None:
    if depth > MAX_JSON_DEPTH:
        raise _error("Graph extension JSON exceeds nesting limit", limit=MAX_JSON_DEPTH)
    if isinstance(value, str):
        if len(value) > MAX_JSON_STRING:
            raise _error("Graph extension JSON string exceeds limit", limit=MAX_JSON_STRING)
        return
    if isinstance(value, float) and not math.isfinite(value):
        raise _error("Graph extension JSON contains a non-finite number")
    if isinstance(value, list):
        for item in value:
            _validate_json_bounds(item, depth=depth + 1)
        return
    if isinstance(value, dict):
        for key, item in value.items():
            _validate_json_bounds(key, depth=depth + 1)
            _validate_json_bounds(item, depth=depth + 1)


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


def _bounded_list(value: Any, field: str) -> list[Any]:
    if not isinstance(value, list):
        raise _error(f"Graph profile {field} must be a list", field=field)
    if len(value) > MAX_PROFILE_RULES:
        raise _error(
            f"Graph profile {field} exceeds the rule limit",
            field=field,
            limit=MAX_PROFILE_RULES,
        )
    return value


def _identifier(value: Any, field: str) -> str:
    if not isinstance(value, str) or not _IDENTIFIER_RE.fullmatch(value):
        raise _error("Graph profile identifier is not canonical", field=field)
    return value


def _source(value: Any) -> str:
    if not isinstance(value, str) or not _SOURCE_RE.fullmatch(value):
        raise _error("Graph profile source must be frontmatter.<field>", field="source")
    return value


def _source_field(source: str) -> str:
    return source.removeprefix("frontmatter.")


def _relative_path(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value or "\\" in value:
        raise _error("Graph profile path must be repository-relative", field=field)
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts or path.as_posix() != value:
        raise _error("Graph profile path must be repository-relative", field=field)
    return value


def _unique_strings(value: Any, field: str) -> tuple[str, ...]:
    if not isinstance(value, list) or any(
        not isinstance(item, str) or not item for item in value
    ):
        raise _error(f"Graph profile {field} must contain non-empty strings", field=field)
    strings = tuple(value)
    if len(set(strings)) != len(strings):
        raise _error(f"Graph profile {field} must be unique", field=field)
    return strings


def _require_unique(values: Sequence[str] | Any, field: str) -> None:
    seen: set[str] = set()
    for value in values:
        if value in seen:
            raise _error("Duplicate graph profile registration", field=field, value=value)
        seen.add(value)


def _error(message: str, **details: Any) -> GraphContractError:
    return GraphContractError(
        "INVALID_GRAPH_PROFILE",
        message,
        cast(dict[str, JSONValue], details),
    )
