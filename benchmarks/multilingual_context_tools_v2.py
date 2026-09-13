"""Versioned bounded tool contracts for the multilingual workflow.

The frozen v1 module remains untouched.  This future surface preserves its
snapshot, source-delivery, and budget mechanics while publishing the bounds
that its generic adapter already enforces for graph pagination and explicit
graph anchors.
"""
from __future__ import annotations

import argparse
import asyncio
import json
from copy import deepcopy
from pathlib import Path
from typing import Any, Literal

from mcp.server.mcpserver import MCPServer
from mcp.types import CallToolResult

from benchmarks import multilingual_context_tools as prior
from benchmarks import typescript_context_tools_v3 as shared
from benchmarks.typescript_context_adapter import wire
from loci import service


PROTOCOL = "multilingual-context-workflow-v2"
TOOL_NAMES_A = frozenset(shared.TOOL_NAMES)
TOOL_NAMES_B = frozenset((*TOOL_NAMES_A, "loci_explore"))

_RECORD_TOOLS = frozenset(("graph_imports", "graph_references", "graph_calls"))
_GRAPH_ID_FIELDS = {
    "graph_anchors": ("seed_ids",),
    "graph_neighbors": ("seed_ids",),
    "graph_traverse_neighbors": ("seed_ids",),
    "graph_paths": ("source_ids", "target_ids"),
    "graph_retrieve": ("seed_ids",),
}
_MAX_RECORD_OFFSET = 10_000
_MAX_RECORD_LIMIT = 32
_MAX_GRAPH_ANCHORS = 5


def _bounded_graph_ids(tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    """Reject only the anchor size that Adapter.dispatch already bounds."""

    for field in _GRAPH_ID_FIELDS.get(tool_name, ()):
        values = arguments.get(field)
        if values is not None and len(values) > _MAX_GRAPH_ANCHORS:
            raise ValueError(f"{tool_name}.{field} must contain at most {_MAX_GRAPH_ANCHORS} IDs")
    return arguments


def _bounded_pagination(tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    """Publish the pre-existing record pagination boundary before dispatch."""

    if tool_name not in _RECORD_TOOLS:
        return arguments
    for field, maximum in (("offset", _MAX_RECORD_OFFSET), ("limit", _MAX_RECORD_LIMIT)):
        value = arguments[field]
        if not 0 <= value <= maximum:
            raise ValueError(f"{tool_name}.{field} must be between 0 and {maximum}")
    return arguments


def normalize_arguments(tool_name: str, raw_args: dict[str, Any]) -> dict[str, Any]:
    """Return the v2 public arguments that are safe to dispatch unchanged.

    Nullable optional fields, empty lists, and duplicate graph IDs retain their
    v1 meanings.  In particular, this function does not deduplicate or impose
    a minimum list length; it only makes the adapter's existing upper bounds
    observable at the public contract boundary.
    """

    if tool_name == "loci_explore":
        return prior.normalize_arguments(tool_name, raw_args)
    normalized = shared.normalize_arguments(tool_name, raw_args)
    return _bounded_pagination(tool_name, _bounded_graph_ids(tool_name, normalized))


class MultilingualAdapter(prior.MultilingualAdapter):
    """The v2 protocol adapter, isolated from the frozen v1 implementation."""

    def __init__(self, run: dict):
        if run.get("arm") not in {"A", "B"}:
            raise ValueError("multilingual protocol requires arm A or B")
        from benchmarks.multilingual_context_inputs import load_inputs
        from benchmarks.multilingual_context_observed_v2 import MultilingualObservedTrace

        self.run = run
        self.repo = Path(run["repo"]).resolve()
        self.corpus, controls = load_inputs(Path(run["corpus_root"]))
        if self.corpus.get("version") != "multilingual-context-v1":
            raise ValueError("MultilingualAdapter requires the frozen multilingual-context-v1 corpus")
        self.limits = controls["limits"]
        self.trace = MultilingualObservedTrace(
            self.corpus, run["case_id"], run["session_id"], run["arm"], run["repetition"]
        )
        entries = list(self.repo.rglob("*"))
        if any(path.is_symlink() for path in entries):
            raise ValueError("snapshot must not contain symlinks")
        files = {path.relative_to(self.repo).as_posix(): path for path in entries if path.is_file()}
        if files.keys() != self.trace.files.keys():
            raise ValueError("repository inventory must match the frozen snapshot exactly")
        if any(path.read_bytes() != self.trace.files[name] for name, path in files.items()):
            raise ValueError("repository contents must match the frozen snapshot exactly")
        index = service.get_store().load(self.repo)
        if index is None:
            raise ValueError("fresh index must be built before agent timing")
        self.symbols = {symbol["id"]: symbol for symbol in index["symbols"]}
        self.lines = {
            name: data.decode("utf-8").splitlines(keepends=True)
            for name, data in self.trace.files.items()
        }
        self.failures: list[dict] = []
        self.deliveries: list[dict] = []
        self.lock = asyncio.Lock()
        self.attempts = 0
        self.is_v2 = True
        self.persist()

    def persist(self) -> None:
        target = self.run.get("trace_path")
        if not target:
            return
        payload = {
            "schema_version": 3,
            "protocol": PROTOCOL,
            "identity": self.trace.identity,
            "events": self.trace.events,
            "failures": self.failures,
            "attempts": self.attempts,
            "deliveries": self.deliveries,
        }
        Path(target).write_text(wire(payload) + "\n", encoding="utf-8")

    def read_operation(self, operation: str, parameters: dict[str, Any]) -> CallToolResult:
        public = "loci_explore" if operation == "explore" else operation
        return super().read_operation(operation, normalize_arguments(public, parameters))

    def dispatch(self, operation: str, parameters: dict) -> dict:
        public = "loci_explore" if operation in {"explore", "loci_explore"} else operation
        internal = "explore" if public == "loci_explore" else public
        return super().dispatch(internal, normalize_arguments(public, parameters))


def _array_schema(schema: dict[str, Any]) -> dict[str, Any] | None:
    if schema.get("type") == "array":
        return schema
    for branch in schema.get("anyOf", []):
        if isinstance(branch, dict) and branch.get("type") == "array":
            return branch
    return None


def _publish_v2_bounds(server: MCPServer) -> None:
    """Update this server's public schemas without altering shared tool models."""

    for tool in server._tool_manager.list_tools():
        schema = deepcopy(tool.parameters)
        properties = schema.get("properties", {})
        if tool.name in _RECORD_TOOLS:
            properties["offset"].update({"minimum": 0, "maximum": _MAX_RECORD_OFFSET})
            properties["limit"].update({"minimum": 0, "maximum": _MAX_RECORD_LIMIT})
        for field in _GRAPH_ID_FIELDS.get(tool.name, ()):
            array = _array_schema(properties[field])
            if array is None:
                raise ValueError(f"{tool.name}.{field} schema is not an array")
            array["maxItems"] = _MAX_GRAPH_ANCHORS
        tool.parameters = schema


def create_server(adapter: MultilingualAdapter, arm: Literal["A", "B"] | None = None) -> MCPServer:
    """Create the v2 A/B tool surface with matching schema and dispatch bounds."""

    selected_arm = arm or adapter.run.get("arm")
    if selected_arm not in {"A", "B"}:
        raise ValueError("multilingual protocol requires arm A or B")
    server = prior.create_server(adapter, selected_arm)
    _publish_v2_bounds(server)
    return server


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run", type=Path, help="run.json supplied by the comparison runner")
    args = parser.parse_args(argv)
    run = json.loads(args.run.read_text(encoding="utf-8"))
    create_server(MultilingualAdapter(run), run.get("arm")).run()


if __name__ == "__main__":
    main()


__all__ = [
    "MultilingualAdapter",
    "PROTOCOL",
    "TOOL_NAMES_A",
    "TOOL_NAMES_B",
    "create_server",
    "main",
    "normalize_arguments",
]
