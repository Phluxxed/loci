"""Versioned observed tools for the matched exact-retrieval/explore trial.

The frozen v3 tool module remains the implementation of the original thirteen
tools.  This module adds the product ``loci_explore`` surface and binds those
tools to the explore-aware observed trace without changing the old protocol.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Annotated, Literal

from mcp.server.mcpserver import MCPServer
from mcp.types import CallToolResult
from pydantic import Field

from benchmarks import typescript_context_tools_v3 as prior
from benchmarks.typescript_context_adapter import wire
from benchmarks.typescript_context_explore_observed import ExploreObservedTrace
from loci import service


PROTOCOL = "typescript-context-explore-v1"
TOOL_NAMES_A = frozenset(prior.TOOL_NAMES)
TOOL_NAMES_B = frozenset((*TOOL_NAMES_A, "loci_explore"))

_EXPLORE_INTENTS = ("locate", "type_dependencies", "impact")
_EXPLORE_RESOLUTIONS = frozenset(("exact", "import-resolved"))
_MAX_EXPLORE_HOPS = 3
_MAX_EXPLORE_OUTPUT_BYTES = 32_768
_MAX_EXPLORE_EVIDENCE_BYTES = 16_384


def _normalize_explore_arguments(raw_args: dict[str, Any]) -> dict[str, Any]:
    """Normalize the public product fields and enforce its wire bounds."""
    raw = prior._require_mapping("loci_explore", raw_args)
    prior._reject_extras(
        "loci_explore",
        raw,
        {
            "intent",
            "query",
            "seed_ids",
            "max_hops",
            "max_output_bytes",
            "max_evidence_bytes",
            "resolutions",
        },
    )
    if "intent" not in raw:
        raise ValueError("loci_explore requires intent")
    intent = prior._string("loci_explore", "intent", raw["intent"])
    assert intent is not None
    if intent not in _EXPLORE_INTENTS:
        raise ValueError("loci_explore.intent must be one of locate, type_dependencies, impact")

    query = prior._string("loci_explore", "query", raw.get("query", ""))
    assert query is not None
    try:
        query_bytes = len(query.encode("utf-8"))
    except UnicodeEncodeError as exc:
        raise ValueError("loci_explore.query must be valid UTF-8") from exc
    if query_bytes > 4096:
        raise ValueError("loci_explore.query must be at most 4096 UTF-8 bytes")

    seed_ids = prior._strings("loci_explore", "seed_ids", raw.get("seed_ids"), optional=True)
    if seed_ids is not None:
        if len(seed_ids) > 5 or any(not item for item in seed_ids) or len(set(seed_ids)) != len(seed_ids):
            raise ValueError("loci_explore.seed_ids must contain at most five unique, nonempty IDs")

    max_hops = prior._integer("loci_explore", "max_hops", raw.get("max_hops"), optional=True)
    if max_hops is not None and not 0 <= max_hops <= _MAX_EXPLORE_HOPS:
        raise ValueError(f"loci_explore.max_hops must be between 0 and {_MAX_EXPLORE_HOPS}")

    max_output_bytes = prior._integer(
        "loci_explore", "max_output_bytes", raw.get("max_output_bytes", 16_384)
    )
    assert max_output_bytes is not None
    if not 2_048 <= max_output_bytes <= _MAX_EXPLORE_OUTPUT_BYTES:
        raise ValueError(
            f"loci_explore.max_output_bytes must be between 2048 and {_MAX_EXPLORE_OUTPUT_BYTES}"
        )

    max_evidence_bytes = prior._integer(
        "loci_explore", "max_evidence_bytes", raw.get("max_evidence_bytes", 8_192)
    )
    assert max_evidence_bytes is not None
    if not 0 <= max_evidence_bytes <= _MAX_EXPLORE_EVIDENCE_BYTES:
        raise ValueError(
            f"loci_explore.max_evidence_bytes must be between 0 and {_MAX_EXPLORE_EVIDENCE_BYTES}"
        )

    resolutions = prior._strings("loci_explore", "resolutions", raw.get("resolutions"), optional=True)
    if resolutions is not None and any(item not in _EXPLORE_RESOLUTIONS for item in resolutions):
        raise ValueError("loci_explore.resolutions only permits exact and import-resolved")

    result: dict[str, Any] = {
        "intent": intent,
        "query": query,
        "max_output_bytes": max_output_bytes,
        "max_evidence_bytes": max_evidence_bytes,
    }
    if seed_ids is not None:
        result["seed_ids"] = seed_ids
    if max_hops is not None:
        result["max_hops"] = max_hops
    if resolutions is not None:
        result["resolutions"] = resolutions
    return result


def normalize_arguments(tool_name: str, raw_args: dict[str, Any]) -> dict[str, Any]:
    """Return exact v3 arguments, including the versioned explore contract."""
    if tool_name == "loci_explore":
        return _normalize_explore_arguments(raw_args)
    return prior.normalize_arguments(tool_name, raw_args)


class ExploreAdapter(prior.ObservedAdapter):
    """Snapshot-bound v3 adapter with an honest ``loci_explore`` operation."""

    def __init__(self, run: dict):
        arm = run.get("arm")
        if arm not in {"A", "B"}:
            raise ValueError("explore protocol requires arm A or B")
        super().__init__(run)
        if self.corpus.get("version") != "typescript-context-v3":
            raise ValueError("ExploreAdapter requires corpus version typescript-context-v3")
        self.is_v2 = True
        self.trace = ExploreObservedTrace(
            self.corpus,
            run["case_id"],
            run["session_id"],
            arm,
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
            "protocol": PROTOCOL,
            "identity": trace.identity,
            "events": trace.events,
            "failures": getattr(self, "failures", []),
            "attempts": getattr(self, "attempts", 0),
            "deliveries": getattr(self, "deliveries", []),
        }
        Path(target_value).write_text(wire(payload) + "\n", encoding="utf-8")

    def read_operation(self, operation: str, parameters: dict) -> CallToolResult:
        public_operation = "loci_explore" if operation == "explore" else operation
        if public_operation == "loci_explore" and self.run.get("arm") != "B":
            raise ValueError("loci_explore is available only in arm B")
        normalized = normalize_arguments(public_operation, parameters)
        # Keep the internal trace operation distinct from the public tool name;
        # graph_* has the same convention in the frozen v3 adapter.
        trace_operation = "explore" if public_operation == "loci_explore" else public_operation
        return self._read_v2(
            trace_operation,
            normalized,
            reason="task_context",
            detail=f"Observed {public_operation} request.",
            because=None,
        )

    def dispatch(self, operation: str, parameters: dict) -> dict:
        if operation not in {"explore", "loci_explore"}:
            return super().dispatch(operation, parameters)
        if self.run.get("arm") != "B":
            raise ValueError("loci_explore is available only in arm B")
        normalized = normalize_arguments("loci_explore", parameters)
        # The evaluation server binds the repository.  Freshness follows the
        # product MCP route; the runner has already built the isolated index.
        result = service.explore(self.repo, ensure_fresh=True, **normalized)
        usage = result.get("usage") if isinstance(result, dict) else None
        if isinstance(result, dict) and "error" not in result:
            nodes_examined = usage.get("nodes_examined") if isinstance(usage, dict) else None
            if type(nodes_examined) is not int or nodes_examined < 0:
                raise ValueError("loci_explore result has invalid nodes_examined usage")
            if nodes_examined > self.limits["max_nodes"]:
                self.failures.append(
                    {
                        "attempt_id": f"{self.trace.identity['session_id']}/attempt/{self.attempts}",
                        "category": "budget_exhausted",
                        "limit": "max_nodes",
                    }
                )
                return {
                    "error": {
                        "code": "BUDGET_EXHAUSTED",
                        "limits": ["max_nodes"],
                        "message": "Result withheld before source delivery; run budget failure retained.",
                    }
                }
        return result

    def spans(self, operation: str, result: dict) -> list[dict]:
        if operation not in {"explore", "loci_explore"}:
            return super().spans(operation, result)
        if not isinstance(result, dict):
            raise ValueError("loci_explore result must be an object")
        sources = result.get("sources", [])
        if not isinstance(sources, list):
            raise ValueError("loci_explore sources must be a list")
        spans: list[dict] = []
        for source in sources:
            if not isinstance(source, dict):
                raise ValueError("loci_explore source must be an object")
            file = source.get("file")
            start = source.get("start_byte")
            end = source.get("end_byte")
            content = source.get("content")
            content_hash = source.get("content_hash")
            if not isinstance(file, str) or type(start) is not int or type(end) is not int:
                raise ValueError("loci_explore source has invalid byte range")
            if not isinstance(content, str) or not content:
                raise ValueError("loci_explore source content must be nonempty")
            encoded = content.encode("utf-8")
            if start < 0 or end != start + len(encoded):
                raise ValueError("loci_explore source byte range does not match content")
            self._file(file)
            if not isinstance(content_hash, str):
                raise ValueError("loci_explore source is missing content_hash")
            import hashlib

            if hashlib.sha256(self.trace.files[file]).hexdigest() != content_hash:
                raise ValueError("loci_explore source hash differs from snapshot")
            spans.append({"file": file, "start_byte": start, "text": content})
        return spans


def create_server(adapter: ExploreAdapter, arm: str | None = None) -> MCPServer:
    """Create A's thirteen tools or B's thirteen tools plus ``loci_explore``."""
    selected_arm = arm or getattr(adapter, "run", {}).get("arm", "B")
    if selected_arm not in {"A", "B"}:
        raise ValueError("explore protocol requires arm A or B")
    server = prior.create_server(adapter)
    if selected_arm == "B":

        @server.tool(
            description=(
                "Select bounded source for one explicit retrieval intent.\n\n"
                "``locate`` returns anchors only; ``type_dependencies`` follows outgoing "
                "proven TypeScript/TSX type and heritage edges; ``impact`` follows incoming known static "
                "dependents. Query text is at most 4096 UTF-8 bytes; seeds are at most five unique IDs; "
                "hops are 0..3 (defaults: locate 0, type 3, impact 1), output is 2048..32768 bytes "
                "for the complete MCP result, and source evidence is 0..16384 bytes. Use query terms "
                "to focus deeper type fields; inspect omissions and incomplete anchors. Impact is "
                "non-exhaustive. Use ``loci_get`` for an exact symbol read and graph tools for diagnostics "
                "or other edges."
            ),
            annotations=prior._READ_ONLY,
            structured_output=False,
        )
        async def loci_explore(
            intent: Literal["locate", "type_dependencies", "impact"],
            query: Annotated[str, Field(json_schema_extra={"maxLength": 4096})] = "",
            seed_ids: Annotated[
                list[str] | None,
                Field(json_schema_extra={"maxItems": 5, "uniqueItems": True}),
            ] = None,
            max_hops: Annotated[
                int | None,
                Field(json_schema_extra={"minimum": 0, "maximum": _MAX_EXPLORE_HOPS}),
            ] = None,
            max_output_bytes: Annotated[
                int,
                Field(json_schema_extra={"minimum": 2048, "maximum": _MAX_EXPLORE_OUTPUT_BYTES}),
            ] = 16_384,
            max_evidence_bytes: Annotated[
                int,
                Field(json_schema_extra={"minimum": 0, "maximum": _MAX_EXPLORE_EVIDENCE_BYTES}),
            ] = 8_192,
            resolutions: list[str] | None = None,
        ) -> CallToolResult:
            """Select bounded source for one explicit retrieval intent.

            ``locate`` returns anchors only; ``type_dependencies`` follows outgoing
            proven TypeScript/TSX type and heritage edges; ``impact`` follows incoming known static
            dependents. Query text is at most 4096 UTF-8 bytes; seeds are at most five
            unique IDs; hops are 0..3 (defaults: locate 0, type 3, impact 1), output
            is 2048..32768 bytes for the complete MCP result, and source evidence
            is 0..16384 bytes. Use query terms to focus deeper type fields; inspect
            omissions and incomplete anchors. Impact is non-exhaustive. Use ``loci_get``
            for an exact symbol read and graph tools for diagnostics or other edges.
            """
            async with adapter.lock:
                return adapter.read_operation(
                    "loci_explore",
                    normalize_arguments(
                        "loci_explore",
                        {
                            "intent": intent,
                            "query": query,
                            "seed_ids": seed_ids,
                            "max_hops": max_hops,
                            "max_output_bytes": max_output_bytes,
                            "max_evidence_bytes": max_evidence_bytes,
                            "resolutions": resolutions,
                        },
                    ),
                )

        prior._strict_tool_arguments(server)
    return server


def _load_run(args: argparse.Namespace) -> dict:
    if args.run is not None:
        run = json.loads(args.run.read_text(encoding="utf-8"))
    else:
        required = {
            "repo": args.repo,
            "corpus_root": args.case_path,
            "case_id": args.case_id,
            "session_id": args.session_id,
            "arm": args.arm,
            "repetition": args.repetition,
            "trace_path": args.trace_output,
        }
        missing = [key for key, value in required.items() if value is None]
        if missing:
            raise SystemExit("run JSON or all direct run options are required: " + ", ".join(missing))
        run = required
    overrides = {
        "arm": args.arm,
        "repo": args.repo,
        "corpus_root": args.case_path,
        "case_id": args.case_id,
        "session_id": args.session_id,
        "repetition": args.repetition,
        "trace_path": args.trace_output,
        "index_path": args.index_path,
        "result_path": args.result_output,
    }
    run.update({key: value for key, value in overrides.items() if value is not None})
    return run


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run", type=Path, nargs="?", help="JSON run description used by the comparison runner")
    parser.add_argument("--arm", choices=("A", "B"))
    parser.add_argument("--repo", type=Path)
    parser.add_argument("--index-path", type=Path)
    parser.add_argument("--case-path", type=Path)
    parser.add_argument("--case-id")
    parser.add_argument("--session-id")
    parser.add_argument("--repetition", type=int, choices=(1, 2, 3))
    parser.add_argument("--trace-output", type=Path)
    parser.add_argument("--result-output", type=Path)
    args = parser.parse_args(argv)
    run = _load_run(args)
    create_server(ExploreAdapter(run), run.get("arm")).run()


if __name__ == "__main__":
    main()


__all__ = [
    "ExploreAdapter",
    "PROTOCOL",
    "TOOL_NAMES_A",
    "TOOL_NAMES_B",
    "create_server",
    "main",
    "normalize_arguments",
]
