"""Snapshot-bound tools for the multilingual compact-context workflow trial.

The shared surface deliberately stays the existing exact-read surface.  Arm B
adds only the product ``loci_explore`` tool, using the current Loci service
with the tighter, predeclared measurement limits.
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
from pathlib import Path
from typing import Any, Annotated, Literal

from mcp.server.mcpserver import MCPServer
from mcp.types import CallToolResult
from pydantic import Field

from benchmarks import typescript_context_tools_v3 as shared
from benchmarks.typescript_context_adapter import Adapter, wire
from loci import service


PROTOCOL = "multilingual-context-workflow-v1"
TOOL_NAMES_A = frozenset(shared.TOOL_NAMES)
TOOL_NAMES_B = frozenset((*TOOL_NAMES_A, "loci_explore"))

_INTENTS = ("locate", "type_dependencies", "dependencies", "impact")
_RESOLUTIONS = frozenset(("exact", "declared", "import-resolved"))
_DEFAULT_OUTPUT_BYTES = 16_384
_DEFAULT_EVIDENCE_BYTES = 8_192
_MAX_OUTPUT_BYTES = 16_384
_MAX_EVIDENCE_BYTES = 8_192
_MAX_HOPS = 3


def _normalize_explore_arguments(raw_args: Any) -> dict[str, Any]:
    """Resolve nullable byte defaults and reject every non-product field."""

    raw = shared._require_mapping("loci_explore", raw_args)
    shared._reject_extras(
        "loci_explore",
        raw,
        {
            "intent", "query", "seed_ids", "max_hops", "max_output_bytes",
            "max_evidence_bytes", "resolutions",
        },
    )
    if "intent" not in raw:
        raise ValueError("loci_explore requires intent")
    intent = shared._string("loci_explore", "intent", raw["intent"])
    assert intent is not None
    if intent not in _INTENTS:
        raise ValueError("loci_explore.intent must be one of " + ", ".join(_INTENTS))

    query = shared._string("loci_explore", "query", raw.get("query", ""))
    assert query is not None
    try:
        query_bytes = len(query.encode("utf-8"))
    except UnicodeEncodeError as exc:
        raise ValueError("loci_explore.query must be valid UTF-8") from exc
    if query_bytes > 4096:
        raise ValueError("loci_explore.query must be at most 4096 UTF-8 bytes")

    seed_ids = shared._strings("loci_explore", "seed_ids", raw.get("seed_ids"), optional=True)
    if seed_ids is not None and (
        len(seed_ids) > 5 or any(not value for value in seed_ids) or len(set(seed_ids)) != len(seed_ids)
    ):
        raise ValueError("loci_explore.seed_ids must contain at most five unique, nonempty IDs")

    max_hops = shared._integer("loci_explore", "max_hops", raw.get("max_hops"), optional=True)
    if max_hops is not None and not 0 <= max_hops <= _MAX_HOPS:
        raise ValueError(f"loci_explore.max_hops must be between 0 and {_MAX_HOPS}")

    def byte_limit(name: str, default: int, minimum: int, maximum: int) -> int:
        # Null has the native-MCP meaning: use its ordinary default.
        value = raw.get(name, default)
        if value is None:
            value = default
        parsed = shared._integer("loci_explore", name, value)
        assert parsed is not None
        if not minimum <= parsed <= maximum:
            raise ValueError(f"loci_explore.{name} must be between {minimum} and {maximum}")
        return parsed

    max_output_bytes = byte_limit(
        "max_output_bytes", _DEFAULT_OUTPUT_BYTES, 2_048, _MAX_OUTPUT_BYTES
    )
    max_evidence_bytes = byte_limit(
        "max_evidence_bytes", _DEFAULT_EVIDENCE_BYTES, 0, _MAX_EVIDENCE_BYTES
    )
    resolutions = shared._strings("loci_explore", "resolutions", raw.get("resolutions"), optional=True)
    if resolutions is not None and any(value not in _RESOLUTIONS for value in resolutions):
        raise ValueError("loci_explore.resolutions only permits exact, declared, and import-resolved")

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
    """Normalize one public tool call without widening the shared contract."""

    if tool_name == "loci_explore":
        return _normalize_explore_arguments(raw_args)
    return shared.normalize_arguments(tool_name, raw_args)


class MultilingualAdapter(Adapter):
    """Use the generic snapshot harness while retaining the multilingual ledger."""

    def __init__(self, run: dict):
        if run.get("arm") not in {"A", "B"}:
            raise ValueError("multilingual protocol requires arm A or B")
        # ``Adapter.__init__`` is deliberately not called: its historical
        # controls loader requires a corpus field the pinned multilingual
        # corpus does not contain.  The comparison input view supplies that
        # runtime-only bridge without modifying a frozen corpus byte.
        from benchmarks.multilingual_context_inputs import load_inputs
        from benchmarks.multilingual_context_observed import MultilingualObservedTrace

        self.run = run
        self.repo = Path(run["repo"]).resolve()
        self.corpus, controls = load_inputs(Path(run["corpus_root"]))
        if self.corpus.get("version") != "multilingual-context-v1":
            raise ValueError("MultilingualAdapter requires corpus version multilingual-context-v1")
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
        self.lines = {file: data.decode("utf-8").splitlines(keepends=True) for file, data in self.trace.files.items()}
        self.failures: list[dict] = []
        self.deliveries: list[dict] = []
        self.lock = asyncio.Lock()
        self.attempts = 0
        # The generic adapter only marks its historical v2 corpus this way.  The
        # multilingual controls use the same delivery ledger and hard bounds.
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
        normalized = normalize_arguments(public, parameters)
        if public != "loci_explore":
            return self._read_v2(
                public, normalized, reason="task_context", detail=f"Observed {public} request."
            )
        if self.run["arm"] != "B":
            raise ValueError("loci_explore is available only in arm B")

        # Adapter._read_v2 provides the established timeout, exact source,
        # output, run-budget, trace, and rejection ledger mechanics.  Give this
        # call its tighter product limits only; shared tools retain the run
        # limits from comparison-controls.json.
        original = {
            name: self.limits[name]
            for name in (
                "max_evidence_bytes", "max_estimated_evidence_tokens",
                "max_serialized_output_bytes_per_operation",
            )
        }
        self.limits["max_evidence_bytes"] = min(original["max_evidence_bytes"], normalized["max_evidence_bytes"])
        self.limits["max_estimated_evidence_tokens"] = min(
            original["max_estimated_evidence_tokens"], (normalized["max_evidence_bytes"] + 3) // 4
        )
        self.limits["max_serialized_output_bytes_per_operation"] = min(
            original["max_serialized_output_bytes_per_operation"], normalized["max_output_bytes"]
        )
        try:
            result = self._read_v2(
                "explore", normalized, reason="task_context", detail="Observed loci_explore request."
            )
        finally:
            self.limits.update(original)
        if self.deliveries:
            if result.structured_content.get("error", {}).get("code") == "BUDGET_EXHAUSTED":
                self.deliveries[-1]["status"] = "rejected"
            self.persist()
        return result

    def dispatch(self, operation: str, parameters: dict) -> dict:
        if operation != "explore":
            return super().dispatch(operation, parameters)
        result = service.explore(self.repo, ensure_fresh=True, **parameters)
        usage = result.get("usage") if isinstance(result, dict) else None
        if isinstance(result, dict) and "error" not in result:
            nodes_examined = usage.get("nodes_examined") if isinstance(usage, dict) else None
            if type(nodes_examined) is not int or nodes_examined < 0:
                raise ValueError("loci_explore result has invalid nodes_examined usage")
            if nodes_examined > self.limits["max_nodes"]:
                self.failures.append({
                    "attempt_id": f"{self.trace.identity['session_id']}/attempt/{self.attempts}",
                    "category": "budget_exhausted",
                    "limit": "max_nodes",
                })
                return {
                    "error": {
                        "code": "BUDGET_EXHAUSTED",
                        "limits": ["max_nodes"],
                        "message": "Result withheld before source delivery; run budget failure retained.",
                    }
                }
        return result

    def spans(self, operation: str, result: dict) -> list[dict]:
        if operation != "explore":
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
            file, start, end = source.get("file"), source.get("start_byte"), source.get("end_byte")
            content, content_hash = source.get("content"), source.get("content_hash")
            if not isinstance(file, str) or type(start) is not int or type(end) is not int:
                raise ValueError("loci_explore source has invalid byte range")
            if not isinstance(content, str) or not content:
                raise ValueError("loci_explore source content must be nonempty")
            encoded = content.encode("utf-8")
            if start < 0 or end != start + len(encoded):
                raise ValueError("loci_explore source byte range does not match content")
            self._file(file)
            if not isinstance(content_hash, str) or hashlib.sha256(self.trace.files[file]).hexdigest() != content_hash:
                raise ValueError("loci_explore source hash differs from snapshot")
            spans.append({"file": file, "start_byte": start, "text": content})
        return spans


_EXPLORE_DESCRIPTION = """Select bounded source for one explicit static retrieval intent.

``locate`` returns anchors only. ``type_dependencies`` selects authored
TypeScript/TSX and Python types/bases, Go types/embeddings, or Rust
types/bounds/traits/impl sites. ``dependencies`` includes those relationships
and JavaScript definite calls, imported values, and direct bases. Rust self
types can select explicit impl sites by reverse traversal; stored direction and
possible configuration remain explicit. ``impact`` follows incoming known
static dependents, without runtime-dispatch or exhaustive-impact claims.
Parsing support is broader than these semantic subsets; inspect unsupported
language and unresolved omissions. Query text is at most 4096 UTF-8 bytes;
seeds are at most five unique IDs; requested hops are 0..3. Complete output is
2048..16384 bytes and source evidence is 0..8192 bytes; omitted or null byte
limits use 16384 and 8192. Use ``get`` for exact source and graph tools for
diagnostics or other edges."""


def create_server(adapter: MultilingualAdapter, arm: Literal["A", "B"] | None = None) -> MCPServer:
    """Create identical exact-read schemas, with B's one additional tool."""

    selected_arm = arm or adapter.run.get("arm")
    if selected_arm not in {"A", "B"}:
        raise ValueError("multilingual protocol requires arm A or B")
    server = shared.create_server(adapter)
    server._lowlevel_server.instructions = "Snapshot-only multilingual observed reads without causal declarations."
    if selected_arm == "B":

        @server.tool(description=_EXPLORE_DESCRIPTION, annotations=shared._READ_ONLY, structured_output=False)
        async def loci_explore(
            intent: Literal["locate", "type_dependencies", "dependencies", "impact"],
            query: Annotated[str, Field(json_schema_extra={"maxLength": 4096})] = "",
            seed_ids: Annotated[list[str] | None, Field(json_schema_extra={"maxItems": 5, "uniqueItems": True})] = None,
            max_hops: Annotated[int | None, Field(json_schema_extra={"minimum": 0, "maximum": _MAX_HOPS})] = None,
            max_output_bytes: Annotated[int | None, Field(json_schema_extra={"minimum": 2048, "maximum": _MAX_OUTPUT_BYTES})] = None,
            max_evidence_bytes: Annotated[int | None, Field(json_schema_extra={"minimum": 0, "maximum": _MAX_EVIDENCE_BYTES})] = None,
            resolutions: list[str] | None = None,
        ) -> CallToolResult:
            """Select bounded source for one explicit multilingual retrieval intent."""
            arguments = normalize_arguments("loci_explore", {
                "intent": intent, "query": query, "seed_ids": seed_ids, "max_hops": max_hops,
                "max_output_bytes": max_output_bytes, "max_evidence_bytes": max_evidence_bytes,
                "resolutions": resolutions,
            })
            async with adapter.lock:
                return adapter.read_operation("loci_explore", arguments)

        shared._strict_tool_arguments(server)
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
    "MultilingualAdapter", "PROTOCOL", "TOOL_NAMES_A", "TOOL_NAMES_B", "create_server", "main",
    "normalize_arguments",
]
