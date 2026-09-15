"""Fixed graph-on/off Loci MCP control with per-call source receipts.

This server is benchmark infrastructure.  The selected arm, target repository,
Loci store and receipt directory are bound by one startup configuration and are
not caller-selectable tool arguments.
"""
from __future__ import annotations

import argparse
import asyncio
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import threading
import time
from typing import Annotated, Any, Callable, Literal, Mapping
import uuid

from mcp.server.mcpserver import MCPServer
from mcp.types import CallToolResult, TextContent
from pydantic import ConfigDict, Field

from loci import service
from loci._retrieval_output import Addition, LIMITS
from loci.graph.contracts import GraphContractError
from loci.graph.profiles import read_contained_file
from loci.retrieval import _anchor_addition, _prepare_context
from loci.retrieval_io import finalize_response
from loci.storage.store_identity import initialize_store
from loci.storage.store_resolver import activate_mcp_store


CONFIG_SCHEMA_VERSION = 1
RECEIPT_SCHEMA_VERSION = 1
DIRECT_POLICY = "benchmark-direct-source-v1"
_CONFIG_KEYS = {
    "schema_version",
    "target_root",
    "arm",
    "store_dir",
    "receipt_dir",
    "store_namespace",
}


class _RepositoryUnavailable(Exception):
    pass


class _RepositoryOutOfScope(Exception):
    pass


@dataclass(frozen=True, slots=True)
class ControlConfig:
    """Immutable process-wide benchmark binding loaded before stdio starts."""

    target_root: Path
    arm: Literal["on", "off"]
    store_dir: Path
    receipt_dir: Path
    store_namespace: str
    config_sha256: str

    @classmethod
    def load(cls, path: str | Path) -> "ControlConfig":
        config_path = Path(path)
        raw = config_path.read_bytes()
        try:
            value = json.loads(raw)
        except (UnicodeError, json.JSONDecodeError) as exc:
            raise ValueError("control config must be one UTF-8 JSON object") from exc
        if not isinstance(value, dict) or set(value) != _CONFIG_KEYS:
            raise ValueError(
                "control config fields must be exactly: " + ", ".join(sorted(_CONFIG_KEYS))
            )
        if (
            type(value["schema_version"]) is not int
            or value["schema_version"] != CONFIG_SCHEMA_VERSION
        ):
            raise ValueError("unsupported control config schema_version")
        if not isinstance(value["arm"], str) or value["arm"] not in {"on", "off"}:
            raise ValueError("control config arm must be 'on' or 'off'")
        for field in ("target_root", "store_dir", "receipt_dir"):
            if not isinstance(value[field], str) or not Path(value[field]).is_absolute():
                raise ValueError(f"control config {field} must be an absolute path")
        if not isinstance(value["store_namespace"], str) or not value["store_namespace"]:
            raise ValueError("control config store_namespace must be a non-empty string")

        target = Path(value["target_root"]).resolve(strict=True)
        if not target.is_dir():
            raise ValueError("control config target_root must name an existing directory")
        store = Path(value["store_dir"]).resolve(strict=False)
        receipts = Path(value["receipt_dir"]).resolve(strict=False)
        _require_disjoint(target, store, "store_dir")
        _require_disjoint(target, receipts, "receipt_dir")
        _require_disjoint(store, receipts, "receipt_dir")

        # A measured target must be an isolated export.  Otherwise its own agent
        # could retrieve this control or the hidden evaluator implementation.
        protected = Path(__file__).resolve().parent
        if _contains(target, protected) or _contains(protected, target):
            raise ValueError(
                "target_root contains complete-work control/oracle code; use an isolated export"
            )
        return cls(
            target_root=target,
            arm=value["arm"],
            store_dir=store,
            receipt_dir=receipts,
            store_namespace=value["store_namespace"],
            config_sha256=hashlib.sha256(raw).hexdigest(),
        )


def _contains(parent: Path, child: Path) -> bool:
    try:
        child.relative_to(parent)
        return True
    except ValueError:
        return False


def _require_disjoint(left: Path, right: Path, field: str) -> None:
    if _contains(left, right) or _contains(right, left):
        raise ValueError(f"control config {field} must be disjoint from other bound roots")


def bind_runtime_store(config: ControlConfig) -> None:
    """Bind Loci's process-global store to the config before serving calls."""
    binding = initialize_store(config.store_dir, config.store_namespace)
    activate_mcp_store(binding)


def prepare_target_index(config: ControlConfig) -> dict[str, Any]:
    """Create the bound store and fully index the clean target before timing."""
    bind_runtime_store(config)
    return service.index_repo(config.target_root, incremental=False)


def retrieve_direct_source(
    repo: Path,
    query: str = "",
    *,
    seed_ids: list[str] | None = None,
) -> dict[str, Any]:
    """Run maintained selection and direct-source packing without graph traversal."""
    store, nodes, state = service._load_graph_context(repo, ensure_fresh=True)
    coverage = service.query_coverage_from_index(
        service._load_required_index(store, repo), "indexed_symbols",
    )
    prepared = _prepare_context(
        repo,
        store,
        nodes,
        state,
        query,
        seed_ids=seed_ids,
        coverage=coverage["state"],
    )
    packer = prepared.packer
    visited: set[str] = set()
    for index, anchor in enumerate(prepared.anchors):
        if anchor.node_id in visited:
            packer.omit("alternative_path")
            continue
        if len(visited) >= LIMITS["max_nodes"]:
            packer.omit("node_limit")
            break
        visited.add(anchor.node_id)
        node = nodes[anchor.node_id]
        addition, missing_source = _anchor_addition(prepared.source, node, index, anchor)
        if missing_source:
            packer.omit("source_unavailable")
        # _anchor_addition also returns indexed-file membership.  The direct
        # control retains only the selected identity and its exact source.
        packer.add(Addition(nodes=(node,), items=addition.items))
    if not prepared.anchors:
        packer.omit("no_anchor")
    packer.usage["nodes_examined"] = len(visited)
    payload = packer.finish()
    payload["policy"] = DIRECT_POLICY
    payload["scope"]["relationships"] = "omitted_by_benchmark_control"
    return finalize_response(payload, payload["usage"]["evidence_bytes"])


class ReceiptStore:
    """Synchronously retain every result and all source versions it cites."""

    def __init__(self, config: ControlConfig) -> None:
        self.config = config
        self.root = config.receipt_dir
        self.packets = self.root / "packets"
        self.sources = self.root / "sources"
        self.receipts = self.root / "receipts"
        for directory in (self.root, self.packets, self.sources, self.receipts):
            directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._sequence = self._next_sequence()

    def record(
        self,
        operation: str,
        arguments: Mapping[str, Any],
        result: CallToolResult,
        *,
        started_unix_ns: int,
    ) -> CallToolResult:
        with self._lock:
            sequence = self._sequence
            self._sequence += 1
            original_packet = _result_packet(result)
            original_artifact = self._store_packet(original_packet)
            versions, failures = self._capture_versions(result.structured_content)
            returned = result
            if failures:
                returned = _error_result(
                    "SOURCE_RECEIPT_FAILED",
                    "Loci result source versions could not be retained and validated",
                    {"failures": failures},
                )
            returned_packet = _result_packet(returned)
            returned_artifact = self._store_packet(returned_packet)
            receipt = {
                "schema_version": RECEIPT_SCHEMA_VERSION,
                "sequence": sequence,
                "operation": operation,
                "arm": self.config.arm,
                "target_root": str(self.config.target_root),
                "store_dir": str(self.config.store_dir),
                "config_sha256": self.config.config_sha256,
                "started_unix_ns": started_unix_ns,
                "recorded_unix_ns": time.time_ns(),
                "arguments": dict(arguments),
                "outcome": "error" if returned.is_error else "success",
                "operation_outcome": "error" if result.is_error else "success",
                "packet": returned_artifact,
                "operation_packet": original_artifact,
                "source_versions": versions,
                "validation": {
                    "status": "failed" if failures else "ok",
                    "failures": failures,
                },
            }
            self._write_receipt(sequence, operation, receipt)
            return returned

    def _next_sequence(self) -> int:
        values = []
        for path in self.receipts.glob("*.json"):
            prefix = path.name.partition("-")[0]
            if prefix.isdigit():
                values.append(int(prefix))
        return max(values, default=0) + 1

    def _store_packet(self, packet: bytes) -> dict[str, Any]:
        digest = hashlib.sha256(packet).hexdigest()
        path = self.packets / f"{digest}.json"
        _write_content_addressed(path, packet, digest)
        return {
            "path": path.relative_to(self.root).as_posix(),
            "sha256": digest,
            "bytes": len(packet),
        }

    def _capture_versions(
        self, payload: Mapping[str, Any] | None,
    ) -> tuple[list[dict[str, Any]], list[str]]:
        if not isinstance(payload, Mapping) or "error" in payload:
            return [], []
        claims, failures = _source_claims(payload)
        versions: list[dict[str, Any]] = []
        loaded: dict[tuple[str, str], bytes] = {}
        for claim in claims:
            file = claim.get("file")
            digest = claim.get("content_hash")
            if not _safe_relative(file) or not _sha256(digest):
                failures.append(f"{claim.get('origin', 'source')}: invalid file/hash claim")
                continue
            key = (file, digest)
            raw = loaded.get(key)
            if raw is None:
                try:
                    raw, relative = read_contained_file(
                        self.config.target_root,
                        Path(file),
                        record="Benchmark source receipt",
                    )
                except (GraphContractError, OSError) as exc:
                    failures.append(f"{claim['origin']}: source unavailable: {exc}")
                    continue
                actual = hashlib.sha256(raw).hexdigest()
                if relative != file or actual != digest:
                    failures.append(
                        f"{claim['origin']}: full source hash differs from {digest}"
                    )
                    continue
                loaded[key] = raw
                blob = self.sources / f"{digest}.bin"
                _write_content_addressed(blob, raw, digest)
                versions.append({
                    "file": file,
                    "sha256": digest,
                    "bytes": len(raw),
                    "path": blob.relative_to(self.root).as_posix(),
                })
            _validate_claim(claim, raw, failures)
        versions.sort(key=lambda value: (value["file"], value["sha256"]))
        return versions, failures

    def _write_receipt(self, sequence: int, operation: str, receipt: dict[str, Any]) -> None:
        safe_operation = operation.replace("_", "-")
        path = self.receipts / f"{sequence:06d}-{safe_operation}.json"
        raw = _canonical_json(receipt) + b"\n"
        _write_exclusive(path, raw)


def _source_claims(payload: Mapping[str, Any]) -> tuple[list[dict[str, Any]], list[str]]:
    claims: list[dict[str, Any]] = []
    failures: list[str] = []

    def source(value: Any, origin: str) -> None:
        if not isinstance(value, Mapping):
            failures.append(f"{origin}: source record is not an object")
            return
        claims.append({
            "origin": origin,
            "file": value.get("file"),
            "content_hash": value.get("content_hash"),
            "start_byte": value.get("start_byte"),
            "end_byte": value.get("end_byte"),
            "start_line": value.get("start_line"),
            "end_line": value.get("end_line"),
            "content": value.get("content"),
        })

    if "source" in payload:
        source(payload["source"], "source")
    values = payload.get("sources", [])
    if not isinstance(values, list):
        failures.append("sources: value is not an array")
    else:
        for index, value in enumerate(values):
            source(value, f"sources[{index}]")
    items = payload.get("items", [])
    if not isinstance(items, list):
        failures.append("items: value is not an array")
    else:
        for index, item in enumerate(items):
            extent = item.get("extent") if isinstance(item, Mapping) else None
            if not isinstance(extent, Mapping):
                failures.append(f"items[{index}].extent: value is not an object")
                continue
            claims.append({
                "origin": f"items[{index}].extent",
                "file": extent.get("file"),
                "content_hash": extent.get("content_hash"),
                "start_byte": extent.get("start_byte"),
                "end_byte": extent.get("end_byte"),
            })
    relationships = payload.get("relationships", [])
    if not isinstance(relationships, list):
        failures.append("relationships: value is not an array")
    else:
        for index, relationship in enumerate(relationships):
            edge = relationship.get("edge") if isinstance(relationship, Mapping) else None
            evidence = edge.get("evidence") if isinstance(edge, Mapping) else None
            if not isinstance(evidence, Mapping):
                failures.append(f"relationships[{index}].edge.evidence: invalid record")
                continue
            claims.append({
                "origin": f"relationships[{index}].edge.evidence",
                "file": evidence.get("file"),
                "content_hash": evidence.get("content_hash"),
                "line": evidence.get("line"),
            })
    return claims, failures


def _validate_claim(claim: Mapping[str, Any], raw: bytes, failures: list[str]) -> None:
    origin = str(claim["origin"])
    if "start_byte" in claim:
        start, end = claim.get("start_byte"), claim.get("end_byte")
        if type(start) is not int or type(end) is not int or not 0 <= start <= end <= len(raw):
            failures.append(f"{origin}: byte extent is invalid for retained source")
            return
        try:
            raw[:start].decode("utf-8")
            raw[:end].decode("utf-8")
            expected = raw[start:end].decode("utf-8")
        except UnicodeError:
            failures.append(f"{origin}: extent is not on UTF-8 boundaries")
            return
        if "content" in claim:
            if not isinstance(claim.get("content"), str) or claim["content"] != expected:
                failures.append(f"{origin}: returned content differs from retained extent")
            start_line = raw[:start].count(b"\n") + 1
            end_line = max(
                start_line,
                start_line + expected.count("\n") - int(expected.endswith("\n")),
            )
            if claim.get("start_line") != start_line or claim.get("end_line") != end_line:
                failures.append(f"{origin}: returned line extent differs from retained source")
    if "line" in claim:
        line = claim.get("line")
        line_count = raw.count(b"\n") + 1
        if type(line) is not int or not 1 <= line <= line_count:
            failures.append(f"{origin}: evidence line is outside retained source")


def _safe_relative(value: Any) -> bool:
    if not isinstance(value, str) or not value or "\\" in value:
        return False
    path = PurePosixPath(value)
    return not path.is_absolute() and ".." not in path.parts and path.as_posix() == value


def _sha256(value: Any) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


def _canonical_json(value: Any) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
    ).encode("utf-8")


def _result_packet(result: CallToolResult) -> bytes:
    return _canonical_json(result.model_dump(mode="json", by_alias=True, exclude_none=True))


def _write_content_addressed(path: Path, raw: bytes, digest: str) -> None:
    if path.exists():
        existing = path.read_bytes()
        if hashlib.sha256(existing).hexdigest() != digest or existing != raw:
            raise OSError(f"content-addressed artifact collision at {path}")
        return
    temporary = path.with_name(f".{path.name}.{os.getpid()}.{uuid.uuid4().hex}.tmp")
    try:
        _write_exclusive(temporary, raw)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _write_exclusive(path: Path, raw: bytes) -> None:
    descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(raw)
            handle.flush()
            os.fsync(handle.fileno())
    except Exception:
        path.unlink(missing_ok=True)
        raise


def _error_result(code: str, message: str, details: Mapping[str, Any]) -> CallToolResult:
    error = {"code": code, "message": message, "details": dict(details)}
    return CallToolResult(
        content=[TextContent(type="text", text=f"{code}: {message}")],
        structured_content={"error": error},
        is_error=True,
    )


class ControlAdapter:
    def __init__(self, config: ControlConfig) -> None:
        self.config = config
        self.receipts = ReceiptStore(config)
        self.lock = asyncio.Lock()

    def _repo(self, supplied: str) -> Path:
        try:
            candidate = Path(supplied).resolve(strict=True)
        except (OSError, RuntimeError) as exc:
            raise _RepositoryUnavailable("repository path is unavailable") from exc
        if candidate != self.config.target_root:
            raise _RepositoryOutOfScope(
                "repository is outside the configured benchmark target"
            )
        return candidate

    def call(
        self,
        operation: Literal["loci_retrieve", "loci_read"],
        arguments: Mapping[str, Any],
        invoke: Callable[[Path], dict[str, Any]],
    ) -> CallToolResult:
        started = time.time_ns()
        try:
            repo = self._repo(str(arguments["repo"]))
            payload = invoke(repo)
            result = CallToolResult(content=[], structured_content=payload, is_error=False)
        except _RepositoryOutOfScope as exc:
            result = _error_result(
                "REPOSITORY_OUT_OF_SCOPE", str(exc),
                {"configured_target": str(self.config.target_root)},
            )
        except _RepositoryUnavailable as exc:
            result = _error_result("INVALID_REPOSITORY", str(exc), {})
        except service.LociError as exc:
            result = _error_result(exc.code, exc.message, exc.details)
        except GraphContractError as exc:
            result = _error_result(exc.code, exc.message, exc.details)
        except Exception as exc:
            result = _error_result(
                "BENCHMARK_CONTROL_FAILURE",
                "Benchmark Loci control failed",
                {"exception": type(exc).__name__, "message": str(exc)},
            )
        try:
            return self.receipts.record(
                operation, arguments, result, started_unix_ns=started,
            )
        except Exception as exc:
            return _error_result(
                "RECEIPT_WRITE_FAILED",
                "Benchmark call receipt could not be persisted",
                {"exception": type(exc).__name__, "message": str(exc)},
            )


def create_server(config: ControlConfig) -> MCPServer:
    """Create the identical two-tool MCP surface used by both fixed arms."""
    adapter = ControlAdapter(config)
    server = MCPServer(
        "loci",
        instructions=(
            "Retrieve deterministic bounded source context from the configured "
            "benchmark repository and expand exact returned source extents."
        ),
    )

    @server.tool(structured_output=False)
    async def loci_retrieve(
        repo: Annotated[str, Field(strict=True, min_length=1)],
        query: Annotated[
            str, Field(strict=True, json_schema_extra={"x-maxUtf8Bytes": 4096}),
        ] = "",
        seed_ids: Annotated[
            list[Annotated[str, Field(strict=True, min_length=1)]] | None,
            Field(default=None, max_length=5, json_schema_extra={"uniqueItems": True}),
        ] = None,
    ) -> CallToolResult:
        """Retrieve deterministic bounded static source context.

        Provide a query or up to five exact seed IDs returned earlier. An exact
        indexed relative file path in ``query`` selects that file; other queries
        select bounded source candidates. The repository refreshes automatically.
        Results report source, any relationship proof made available by the
        fixed startup policy, ambiguity and omissions. Use
        an incomplete item's short ``source_ref`` with ``loci_read`` to hydrate its
        exact source, or pass a returned node ID as a seed to re-anchor under the
        fixed startup policy. Relationships are static and non-exhaustive.
        """
        arguments = {"repo": repo, "query": query, "seed_ids": seed_ids}
        async with adapter.lock:
            if config.arm == "on":
                invoke = lambda target: service.retrieve(
                    target, query=query, seed_ids=seed_ids, ensure_fresh=True,
                )
            else:
                invoke = lambda target: retrieve_direct_source(
                    target, query=query, seed_ids=seed_ids,
                )
            return adapter.call("loci_retrieve", arguments, invoke)

    @server.tool(structured_output=False)
    async def loci_read(
        repo: Annotated[str, Field(strict=True, min_length=1)],
        source_ref: Annotated[str, Field(strict=True, min_length=1)],
    ) -> CallToolResult:
        """Expand one exact source extent named by a returned ``source_ref``.

        Pass the returned short handle unchanged. Follow ``next_source_ref``
        until it is null to page an incomplete extent. An unknown or expired
        handle requires fresh ``loci_retrieve`` context in the same repository.
        ``SOURCE_STALE`` means the indexed source changed; make a fresh
        ``loci_retrieve`` request instead of reusing the old locator.
        """
        arguments = {"repo": repo, "source_ref": source_ref}
        async with adapter.lock:
            return adapter.call(
                "loci_read",
                arguments,
                lambda target: service.read(target, source_ref, ensure_fresh=True),
            )

    _strict_tool_arguments(server)
    return server


def _strict_tool_arguments(server: MCPServer) -> None:
    for tool in server._tool_manager.list_tools():
        model = tool.fn_metadata.arg_model
        config = dict(model.model_config)
        config.update({"extra": "forbid", "strict": True})
        model.model_config = ConfigDict(**config)
        model.model_rebuild(force=True)
        tool.parameters = model.model_json_schema(by_alias=True)


def load_receipts(receipt_dir: str | Path) -> list[dict[str, Any]]:
    """Load and validate the ordered receipt sequence for controller analysis."""
    root = Path(receipt_dir).resolve(strict=True)
    values: list[dict[str, Any]] = []
    for path in sorted((root / "receipts").glob("*.json")):
        value = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(value, dict) or value.get("schema_version") != RECEIPT_SCHEMA_VERSION:
            raise ValueError(f"invalid complete-work receipt: {path}")
        for field in ("packet", "operation_packet"):
            _validate_artifact(root, value.get(field), field)
        versions = value.get("source_versions")
        if not isinstance(versions, list):
            raise ValueError(f"invalid source_versions in complete-work receipt: {path}")
        for version in versions:
            _validate_artifact(root, version, "source_version")
        values.append(value)
    sequences = [value.get("sequence") for value in values]
    if sequences != list(range(1, len(values) + 1)):
        raise ValueError("complete-work receipt sequence is not contiguous")
    return values


def _validate_artifact(root: Path, value: Any, field: str) -> None:
    if not isinstance(value, Mapping):
        raise ValueError(f"complete-work receipt {field} is not an object")
    relative, digest, size = value.get("path"), value.get("sha256"), value.get("bytes")
    if not _safe_relative(relative) or not _sha256(digest) or type(size) is not int or size < 0:
        raise ValueError(f"complete-work receipt {field} descriptor is invalid")
    path = (root / relative).resolve(strict=True)
    if not _contains(root, path) or not path.is_file():
        raise ValueError(f"complete-work receipt {field} escapes its receipt root")
    raw = path.read_bytes()
    if len(raw) != size or hashlib.sha256(raw).hexdigest() != digest:
        raise ValueError(f"complete-work receipt {field} content address is invalid")


def receipt_source_bytes(receipt_dir: str | Path, digest: str) -> bytes:
    """Read one retained source version and verify its content address."""
    if not _sha256(digest):
        raise ValueError("source digest must be lowercase SHA-256")
    raw = (Path(receipt_dir) / "sources" / f"{digest}.bin").read_bytes()
    if hashlib.sha256(raw).hexdigest() != digest:
        raise ValueError("retained source version does not match its content address")
    return raw


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--prepare",
        action="store_true",
        help="fully index the configured target and exit before measured execution",
    )
    parser.add_argument("config", type=Path, help="immutable complete-work control JSON")
    args = parser.parse_args(argv)
    config = ControlConfig.load(args.config)
    if args.prepare:
        result = prepare_target_index(config)
        print(json.dumps(result, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
        return
    bind_runtime_store(config)
    create_server(config).run(transport="stdio")


if __name__ == "__main__":
    main()


__all__ = [
    "ControlConfig",
    "DIRECT_POLICY",
    "ReceiptStore",
    "bind_runtime_store",
    "create_server",
    "load_receipts",
    "main",
    "prepare_target_index",
    "receipt_source_bytes",
    "retrieve_direct_source",
]
