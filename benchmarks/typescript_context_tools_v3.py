"""Typed, intent-free v3 tools for the frozen TypeScript context corpus."""

from __future__ import annotations

from typing import Any, Literal

from mcp.server.mcpserver import MCPServer
from mcp.types import CallToolResult, ToolAnnotations
from pydantic import ConfigDict

from benchmarks.typescript_context_adapter import Adapter, wire


TOOL_NAMES = {
    "search",
    "get",
    "outline",
    "file",
    "grep",
    "graph_anchors",
    "graph_neighbors",
    "graph_traverse_neighbors",
    "graph_paths",
    "graph_retrieve",
    "graph_imports",
    "graph_references",
    "graph_calls",
}

_STATUSES = ("all", "resolved", "unresolved")


def _require_mapping(tool_name: str, raw_args: Any) -> dict[str, Any]:
    if type(raw_args) is not dict:
        raise TypeError(f"{tool_name} arguments must be an object")
    return raw_args


def _reject_extras(tool_name: str, raw_args: dict[str, Any], allowed: set[str]) -> None:
    extras = sorted(set(raw_args) - allowed)
    if extras:
        raise ValueError(f"{tool_name} received unknown parameter(s): {', '.join(extras)}")


def _string(tool_name: str, name: str, value: Any, *, optional: bool = False) -> str | None:
    if value is None and optional:
        return None
    if type(value) is not str:
        raise TypeError(f"{tool_name}.{name} must be a string")
    return value


def _integer(tool_name: str, name: str, value: Any, *, optional: bool = False) -> int | None:
    if value is None and optional:
        return None
    if type(value) is not int:
        raise TypeError(f"{tool_name}.{name} must be an integer")
    return value


def _strings(tool_name: str, name: str, value: Any, *, optional: bool = False) -> list[str] | None:
    if value is None and optional:
        return None
    if type(value) is not list or any(type(item) is not str for item in value):
        raise TypeError(f"{tool_name}.{name} must be a list of strings")
    return list(value)


def _status(tool_name: str, name: str, value: Any) -> str:
    value = _string(tool_name, name, value)
    assert value is not None
    if value not in _STATUSES:
        raise ValueError(f"{tool_name}.{name} must be one of {', '.join(_STATUSES)}")
    return value


def normalize_arguments(tool_name: str, raw_args: dict[str, Any]) -> dict[str, Any]:
    """Return the exact adapter arguments, with concrete defaults and no nulls."""

    raw = _require_mapping(tool_name, raw_args)

    if tool_name == "search":
        _reject_extras(tool_name, raw, {"query", "kind", "lang", "file_paths"})
        if "query" not in raw:
            raise ValueError("search requires query")
        result = {"query": _string(tool_name, "query", raw["query"])}
        kind = _string(tool_name, "kind", raw.get("kind"), optional=True)
        lang = _string(tool_name, "lang", raw.get("lang"), optional=True)
        file_paths = _strings(tool_name, "file_paths", raw.get("file_paths"), optional=True)
        if kind is not None:
            result["kind"] = kind
        if lang is not None:
            result["lang"] = lang
        if file_paths is not None:
            result["file_paths"] = file_paths
        return result

    if tool_name == "get":
        _reject_extras(tool_name, raw, {"symbol_ids", "context", "selected_from_search_id"})
        if "symbol_ids" not in raw:
            raise ValueError("get requires symbol_ids")
        symbol_ids = _strings(tool_name, "symbol_ids", raw["symbol_ids"])
        context = _integer(tool_name, "context", raw.get("context", 0))
        selected = _string(tool_name, "selected_from_search_id", raw.get("selected_from_search_id"), optional=True)
        assert symbol_ids is not None and context is not None
        result = {"symbol_ids": symbol_ids, "context": context}
        if selected is not None:
            result["selected_from_search_id"] = selected
        return result

    if tool_name == "outline":
        _reject_extras(tool_name, raw, {"file"})
        file = _string(tool_name, "file", raw.get("file"), optional=True)
        return {} if file is None else {"file": file}

    if tool_name == "file":
        _reject_extras(tool_name, raw, {"file_path", "start_line", "end_line"})
        if "file_path" not in raw:
            raise ValueError("file requires file_path")
        file_path = _string(tool_name, "file_path", raw["file_path"])
        start_line = _integer(tool_name, "start_line", raw.get("start_line"), optional=True)
        end_line = _integer(tool_name, "end_line", raw.get("end_line"), optional=True)
        assert file_path is not None
        result = {"file_path": file_path}
        if start_line is not None:
            result["start_line"] = start_line
        if end_line is not None:
            result["end_line"] = end_line
        return result

    if tool_name == "grep":
        _reject_extras(tool_name, raw, {"pattern"})
        if "pattern" not in raw:
            raise ValueError("grep requires pattern")
        return {"pattern": _string(tool_name, "pattern", raw["pattern"])}

    if tool_name == "graph_anchors":
        _reject_extras(tool_name, raw, {"question", "seed_ids"})
        if "question" not in raw:
            raise ValueError("graph_anchors requires question")
        question = _string(tool_name, "question", raw["question"])
        seed_ids = _strings(tool_name, "seed_ids", raw.get("seed_ids"), optional=True)
        assert question is not None
        result = {"question": question}
        if seed_ids is not None:
            result["seed_ids"] = seed_ids
        return result

    if tool_name == "graph_neighbors":
        _reject_extras(tool_name, raw, {"seed_ids"})
        if "seed_ids" not in raw:
            raise ValueError("graph_neighbors requires seed_ids")
        seed_ids = _strings(tool_name, "seed_ids", raw["seed_ids"])
        assert seed_ids is not None
        return {"seed_ids": seed_ids}

    if tool_name == "graph_traverse_neighbors":
        _reject_extras(tool_name, raw, {"seed_ids", "edge_types"})
        if "seed_ids" not in raw:
            raise ValueError("graph_traverse_neighbors requires seed_ids")
        seed_ids = _strings(tool_name, "seed_ids", raw["seed_ids"])
        edge_types = _strings(tool_name, "edge_types", raw.get("edge_types"), optional=True)
        assert seed_ids is not None
        result = {"seed_ids": seed_ids}
        if edge_types is not None:
            result["edge_types"] = edge_types
        return result

    if tool_name == "graph_paths":
        _reject_extras(tool_name, raw, {"source_ids", "target_ids", "edge_types"})
        if "source_ids" not in raw or "target_ids" not in raw:
            raise ValueError("graph_paths requires source_ids and target_ids")
        source_ids = _strings(tool_name, "source_ids", raw["source_ids"])
        target_ids = _strings(tool_name, "target_ids", raw["target_ids"])
        edge_types = _strings(tool_name, "edge_types", raw.get("edge_types"), optional=True)
        assert source_ids is not None and target_ids is not None
        result = {"source_ids": source_ids, "target_ids": target_ids}
        if edge_types is not None:
            result["edge_types"] = edge_types
        return result

    if tool_name == "graph_retrieve":
        _reject_extras(tool_name, raw, {"question", "seed_ids", "edge_types"})
        if "question" not in raw:
            raise ValueError("graph_retrieve requires question")
        question = _string(tool_name, "question", raw["question"])
        seed_ids = _strings(tool_name, "seed_ids", raw.get("seed_ids"), optional=True)
        edge_types = _strings(tool_name, "edge_types", raw.get("edge_types"), optional=True)
        assert question is not None
        result = {"question": question}
        if seed_ids is not None:
            result["seed_ids"] = seed_ids
        if edge_types is not None:
            result["edge_types"] = edge_types
        return result

    if tool_name in {"graph_imports", "graph_references", "graph_calls"}:
        _reject_extras(tool_name, raw, {"file", "status", "offset", "limit"})
        file = _string(tool_name, "file", raw.get("file"), optional=True)
        status = _status(tool_name, "status", raw.get("status", "all"))
        offset = _integer(tool_name, "offset", raw.get("offset", 0))
        limit = _integer(tool_name, "limit", raw.get("limit", 20))
        assert status is not None and offset is not None and limit is not None
        result = {"status": status, "offset": offset, "limit": limit}
        if file is not None:
            result["file"] = file
        return result

    raise ValueError(f"unknown v3 tool: {tool_name}")


class ObservedAdapter(Adapter):
    """Bind the v3 corpus to v2 budget mechanics and intent-free observations."""

    def __init__(self, run: dict):
        # The import remains here intentionally: the primary agent supplies the
        # v3 trace module, while this surface can still be schema-tested alone.
        from benchmarks.typescript_context_observed import ObservedTrace

        super().__init__(run)
        if self.corpus.get("version") != "typescript-context-v3":
            raise ValueError("ObservedAdapter requires corpus version typescript-context-v3")
        self.is_v2 = True
        self.trace = ObservedTrace(
            self.corpus,
            run["case_id"],
            run["session_id"],
            run["arm"],
            run["repetition"],
        )
        self.persist()

    def persist(self) -> None:
        trace = getattr(self, "trace", None)
        target_value = getattr(self, "run", {}).get("trace_path")
        if trace is None or not target_value:
            return
        payload = {
            "schema_version": 3,
            "identity": trace.identity,
            "events": trace.events,
            "failures": getattr(self, "failures", []),
            "attempts": getattr(self, "attempts", 0),
            "deliveries": getattr(self, "deliveries", []),
        }
        from pathlib import Path

        Path(target_value).write_text(wire(payload) + "\n", encoding="utf-8")

    def _v2_delivery(
        self,
        *,
        operation: str,
        parameters: dict,
        reason: str,
        detail: str,
        because: str | None,
        result: dict,
        response_json: str,
        started: float,
        status: str,
        trace_event_id: str | None,
        spans: list[dict],
    ) -> None:
        super()._v2_delivery(
            operation=operation,
            parameters=parameters,
            reason=reason,
            detail=detail,
            because=because,
            result=result,
            response_json=response_json,
            started=started,
            status=status,
            trace_event_id=trace_event_id,
            spans=spans,
        )
        if self.deliveries:
            self.deliveries[-1].pop("reason", None)
            self.deliveries[-1].pop("detail", None)
            self.deliveries[-1].pop("because", None)

    def _v2_evaluation(self, attempt_id: str, event_id: str | None = None) -> dict:
        evaluation = super()._v2_evaluation(attempt_id, event_id)
        evaluation.pop("event_id", None)
        return evaluation

    def read_operation(self, operation: str, parameters: dict) -> CallToolResult:
        """Record one typed, task-context read through the inherited v2 checks."""
        normalized = normalize_arguments(operation, parameters)
        return self._read_v2(
            operation,
            normalized,
            reason="task_context",
            detail=f"Observed {operation} request.",
            because=None,
        )


def _strict_tool_arguments(server: MCPServer) -> None:
    """Make SDK-generated argument models reject coercion and extra keys."""
    for tool in server._tool_manager.list_tools():
        model = tool.fn_metadata.arg_model
        config = dict(model.model_config)
        config.update({"extra": "forbid", "strict": True})
        model.model_config = ConfigDict(**config)
        model.model_rebuild(force=True)
        tool.parameters = model.model_json_schema(by_alias=True)


_READ_ONLY = ToolAnnotations(
    read_only_hint=True,
    destructive_hint=False,
    open_world_hint=False,
)


def create_server(adapter: ObservedAdapter) -> MCPServer:
    """Create the thirteen typed, snapshot-bound v3 read tools."""

    server = MCPServer(
        "evaluation",
        instructions="Snapshot-only TypeScript observed reads without causal declarations.",
    )

    @server.tool(description="Search indexed snapshot symbols.", annotations=_READ_ONLY, structured_output=False)
    async def search(
        query: str,
        kind: str | None = None,
        lang: str | None = None,
        file_paths: list[str] | None = None,
    ) -> CallToolResult:
        """Search indexed snapshot symbols."""
        async with adapter.lock:
            return adapter.read_operation(
                "search",
                normalize_arguments("search", {
                    "query": query, "kind": kind, "lang": lang, "file_paths": file_paths,
                }),
            )

    @server.tool(description="Retrieve exact indexed symbol source.", annotations=_READ_ONLY, structured_output=False)
    async def get(
        symbol_ids: list[str],
        context: int = 0,
        selected_from_search_id: str | None = None,
    ) -> CallToolResult:
        """Retrieve exact indexed symbol source."""
        async with adapter.lock:
            return adapter.read_operation(
                "get",
                normalize_arguments("get", {
                    "symbol_ids": symbol_ids,
                    "context": context,
                    "selected_from_search_id": selected_from_search_id,
                }),
            )

    @server.tool(description="Return the indexed snapshot outline.", annotations=_READ_ONLY, structured_output=False)
    async def outline(file: str | None = None) -> CallToolResult:
        """Return the indexed snapshot outline."""
        async with adapter.lock:
            return adapter.read_operation("outline", normalize_arguments("outline", {"file": file}))

    @server.tool(description="Read cached snapshot file content.", annotations=_READ_ONLY, structured_output=False)
    async def file(
        file_path: str,
        start_line: int | None = None,
        end_line: int | None = None,
    ) -> CallToolResult:
        """Read cached snapshot file content."""
        async with adapter.lock:
            return adapter.read_operation(
                "file",
                normalize_arguments("file", {
                    "file_path": file_path, "start_line": start_line, "end_line": end_line,
                }),
            )

    @server.tool(description="Regex-search indexed snapshot files.", annotations=_READ_ONLY, structured_output=False)
    async def grep(pattern: str) -> CallToolResult:
        """Regex-search indexed snapshot files."""
        async with adapter.lock:
            return adapter.read_operation("grep", normalize_arguments("grep", {"pattern": pattern}))

    @server.tool(description="Select graph anchors for a question.", annotations=_READ_ONLY, structured_output=False)
    async def graph_anchors(question: str, seed_ids: list[str] | None = None) -> CallToolResult:
        """Select graph anchors for a question."""
        async with adapter.lock:
            return adapter.read_operation(
                "graph_anchors",
                normalize_arguments("graph_anchors", {"question": question, "seed_ids": seed_ids}),
            )

    @server.tool(description="Return outgoing graph neighbours.", annotations=_READ_ONLY, structured_output=False)
    async def graph_neighbors(seed_ids: list[str]) -> CallToolResult:
        """Return outgoing graph neighbours."""
        async with adapter.lock:
            return adapter.read_operation(
                "graph_neighbors", normalize_arguments("graph_neighbors", {"seed_ids": seed_ids})
            )

    @server.tool(description="Traverse filtered graph neighbours.", annotations=_READ_ONLY, structured_output=False)
    async def graph_traverse_neighbors(
        seed_ids: list[str], edge_types: list[str] | None = None
    ) -> CallToolResult:
        """Traverse filtered graph neighbours."""
        async with adapter.lock:
            return adapter.read_operation(
                "graph_traverse_neighbors",
                normalize_arguments("graph_traverse_neighbors", {
                    "seed_ids": seed_ids, "edge_types": edge_types,
                }),
            )

    @server.tool(description="Find bounded graph paths.", annotations=_READ_ONLY, structured_output=False)
    async def graph_paths(
        source_ids: list[str], target_ids: list[str], edge_types: list[str] | None = None
    ) -> CallToolResult:
        """Find bounded graph paths."""
        async with adapter.lock:
            return adapter.read_operation(
                "graph_paths",
                normalize_arguments("graph_paths", {
                    "source_ids": source_ids, "target_ids": target_ids, "edge_types": edge_types,
                }),
            )

    @server.tool(description="Retrieve question-shaped graph evidence.", annotations=_READ_ONLY, structured_output=False)
    async def graph_retrieve(
        question: str,
        seed_ids: list[str] | None = None,
        edge_types: list[str] | None = None,
    ) -> CallToolResult:
        """Retrieve question-shaped graph evidence."""
        async with adapter.lock:
            return adapter.read_operation(
                "graph_retrieve",
                normalize_arguments("graph_retrieve", {
                    "question": question, "seed_ids": seed_ids, "edge_types": edge_types,
                }),
            )

    @server.tool(description="Read graph import records.", annotations=_READ_ONLY, structured_output=False)
    async def graph_imports(
        file: str | None = None,
        status: Literal["all", "resolved", "unresolved"] = "all",
        offset: int = 0,
        limit: int = 20,
    ) -> CallToolResult:
        """Read graph import records."""
        async with adapter.lock:
            return adapter.read_operation(
                "graph_imports",
                normalize_arguments("graph_imports", {
                    "file": file, "status": status, "offset": offset, "limit": limit,
                }),
            )

    @server.tool(description="Read graph reference records.", annotations=_READ_ONLY, structured_output=False)
    async def graph_references(
        file: str | None = None,
        status: Literal["all", "resolved", "unresolved"] = "all",
        offset: int = 0,
        limit: int = 20,
    ) -> CallToolResult:
        """Read graph reference records."""
        async with adapter.lock:
            return adapter.read_operation(
                "graph_references",
                normalize_arguments("graph_references", {
                    "file": file, "status": status, "offset": offset, "limit": limit,
                }),
            )

    @server.tool(description="Read graph call records.", annotations=_READ_ONLY, structured_output=False)
    async def graph_calls(
        file: str | None = None,
        status: Literal["all", "resolved", "unresolved"] = "all",
        offset: int = 0,
        limit: int = 20,
    ) -> CallToolResult:
        """Read graph call records."""
        async with adapter.lock:
            return adapter.read_operation(
                "graph_calls",
                normalize_arguments("graph_calls", {
                    "file": file, "status": status, "offset": offset, "limit": limit,
                }),
            )

    _strict_tool_arguments(server)
    return server


__all__ = ["ObservedAdapter", "TOOL_NAMES", "create_server", "normalize_arguments"]


def main():
    import argparse
    import json
    from pathlib import Path

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run", type=Path)
    args = parser.parse_args()
    create_server(ObservedAdapter(json.loads(args.run.read_text()))).run()


if __name__ == "__main__":
    main()
