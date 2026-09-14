"""Exact source locators and MCP byte accounting shared by normal retrieval."""
from __future__ import annotations

import base64
import hashlib
import json
import math
from pathlib import Path, PurePosixPath
import re
from typing import Any, Mapping

from ._exploration_output import Span, _envelope_bytes
from .graph.contracts import GraphContractError
from .graph.profiles import read_contained_file
from .graph.state import GraphIndexState
from .storage.index_store import IndexStore


READ_SOURCE_BYTES = 8192
READ_OUTPUT_BYTES = 16384
_REF_KEYS = {"v", "repo", "file", "hash", "start", "end", "offset"}


def _invalid(message: str) -> GraphContractError:
    return GraphContractError("INVALID_SOURCE_REF", message, {})


def _encode(value: Mapping[str, Any]) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True,
                     separators=(",", ":")).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def source_ref(repo: Path, span: Span) -> str:
    """Locate an exact owning extent; this is not an issuance credential."""
    return _encode({"v": 1, "repo": str(repo.resolve()), "file": span.file,
                    "hash": span.content_hash, "start": span.start_byte,
                    "end": span.end_byte, "offset": span.start_byte})


def serialize_source(repo: Path, span: Span, source_id: int) -> dict[str, Any]:
    return {"id": source_id, "file": span.file, "start_byte": span.start_byte,
            "end_byte": span.end_byte, "start_line": span.start_line,
            "end_line": span.end_line, "content_hash": span.content_hash,
            "content": span.content, "source_ref": source_ref(repo, span)}


def finalize_response(payload: dict[str, Any], evidence_bytes: int) -> dict[str, Any]:
    """Account for the entire successful MCP envelope, including this count."""
    usage = payload["usage"]
    usage["evidence_bytes"] = evidence_bytes
    usage["output_bytes"] = 0
    usage["output_encoding"] = "mcp_result_json_utf8"
    for _ in range(16):
        size = _envelope_bytes(payload)
        tokens = math.ceil(size / 4)
        if usage["output_bytes"] == size and (
            "estimated_tokens" not in usage or usage["estimated_tokens"] == tokens
        ):
            return payload
        usage["output_bytes"] = size
        if "estimated_tokens" in usage:
            usage["estimated_tokens"] = tokens
    raise ValueError("normal retrieval output accounting did not converge")


def _decode(repo: Path, reference: str) -> dict[str, Any]:
    if not isinstance(reference, str) or not reference or len(reference) > 16384:
        raise _invalid("Source reference must be a bounded encoded locator")
    try:
        raw = base64.b64decode(reference + "=" * (-len(reference) % 4),
                               altchars=b"-_", validate=True)
        value = json.loads(raw)
    except (ValueError, UnicodeError) as exc:
        raise _invalid("Source reference is not valid encoded JSON") from exc
    if not isinstance(value, dict) or set(value) != _REF_KEYS:
        raise _invalid("Source reference fields are invalid")
    if type(value["v"]) is not int or value["v"] != 1:
        raise _invalid("Source reference version is unsupported")
    if value["repo"] != str(repo.resolve()):
        raise _invalid("Source reference belongs to another repository")
    file = value["file"]
    if (not isinstance(file, str) or not file or "\\" in file
            or PurePosixPath(file).is_absolute() or ".." in PurePosixPath(file).parts
            or PurePosixPath(file).as_posix() != file):
        raise _invalid("Source reference path is not a contained relative path")
    if not isinstance(value["hash"], str) or not re.fullmatch(r"[0-9a-f]{64}", value["hash"]):
        raise _invalid("Source reference hash is invalid")
    if any(type(value[key]) is not int for key in ("start", "end", "offset")):
        raise _invalid("Source reference offsets must be integers")
    if not 0 <= value["start"] <= value["offset"] <= value["end"]:
        raise _invalid("Source reference extent is invalid")
    if _encode(value) != reference:
        raise _invalid("Source reference is not canonically encoded")
    return value


def _control_files(state: GraphIndexState) -> set[str]:
    paths = {path for path in state.input_hashes
             if PurePosixPath(path).name in {"go.mod", "go.work", "Cargo.toml", "Package.swift"}}
    for record in (*state.imports, *state.symbol_references, *state.calls, *state.type_relations):
        paths.update(getattr(record, "resolution_control_files", ()))
        paths.update(control.file for control in getattr(record, "resolution_controls", ()))
    return paths


def read_source(repo: Path, store: IndexStore, nodes: Mapping[str, dict],
                state: GraphIndexState, reference: str) -> dict[str, Any]:
    """Read a fixed page from a current, contained, indexed source extent."""
    value = _decode(repo, reference)
    file = value["file"]
    # Markdown has a page-root section rather than a zero-width file node.
    # The index's file hashes define source eligibility for every language.
    index = store.load(repo)
    hashes = dict(index.get("file_hashes", {})) if index is not None else {}
    if file in _control_files(state):
        hashes.setdefault(file, state.input_hashes.get(file))
    if file not in hashes:
        raise _invalid("Source reference is not indexed source or a resolver control")
    if hashes[file] != value["hash"]:
        raise GraphContractError("SOURCE_STALE", "Source reference differs from the current index", {"file": file})
    try:
        # Read current bytes as well as checking the index: changes after refresh
        # must not let old offsets silently address different source.
        raw, relative = read_contained_file(repo, Path(file), record="Source reference")
    except GraphContractError as exc:
        raise GraphContractError("SOURCE_UNAVAILABLE", "Source reference cannot be read", {"file": file}) from exc
    if relative != file or hashlib.sha256(raw).hexdigest() != value["hash"]:
        raise GraphContractError("SOURCE_STALE", "Source changed after reference selection", {"file": file})
    if value["end"] > len(raw):
        raise _invalid("Source reference extends beyond the file")
    try:
        # Validate the whole file and all caller-supplied boundaries.
        raw.decode("utf-8")
        for offset in (value["start"], value["offset"], value["end"]):
            raw[:offset].decode("utf-8")
    except UnicodeError as exc:
        raise _invalid("Source reference is not on UTF-8 boundaries") from exc
    start = value["offset"]
    end = min(value["end"], start + READ_SOURCE_BYTES)

    def page(end_byte: int) -> dict[str, Any]:
        content = raw[start:end_byte].decode("utf-8")
        line = raw[:start].count(b"\n") + 1
        span = Span(file, start, end_byte, line,
                    max(line, line + content.count("\n") - int(content.endswith("\n"))),
                    value["hash"], content)
        complete = end_byte == value["end"]
        result = {"schema_version": 1, "status": "ok",
                  "source": serialize_source(repo, span, 1), "complete": complete,
                  "next_source_ref": None if complete else _encode({**value, "offset": end_byte}),
                  "usage": {"evidence_bytes": 0, "output_bytes": 0,
                            "output_encoding": "mcp_result_json_utf8"}}
        return finalize_response(result, end_byte - start)

    while end > start and end < len(raw) and raw[end] & 0xC0 == 0x80:
        end -= 1
    result = page(end)
    # JSON escaping can expand source bytes substantially; bound the complete
    # envelope as well as the raw source and guarantee pagination makes progress.
    while result["usage"]["output_bytes"] > READ_OUTPUT_BYTES and end > start:
        end = start + (end - start) // 2
        while end > start and end < len(raw) and raw[end] & 0xC0 == 0x80:
            end -= 1
        result = page(end)
    if result["usage"]["output_bytes"] > READ_OUTPUT_BYTES or (end == start and start < value["end"]):
        raise GraphContractError("OUTPUT_BUDGET_EXCEEDED", "Source page cannot fit the fixed output budget", {})
    return result
