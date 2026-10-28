"""Matched source-delivery replay; raw packets stay in the ignored output directory.

This measures in-process service calls and canonical JSON envelopes, not MCP
transport or agent use. R1 performs its unchanged repository refresh. Direct
reads check current path eligibility and the pinned file hash on every page.
The direct_full_refresh control additionally runs the existing repository
inventory refresh on each page. Oracle preparation and receipt writing are
outside elapsed_ns.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import time
from typing import Any
import uuid

from loci.graph_free import (
    GraphFreeError, _candidates, _canonical, _repo, _skipped, _source_bytes,
)
from loci.integrated import IntegratedSource


DIRECT_MAX_LINES = 2000
DIRECT_MAX_BYTES = 50 * 1024


def _digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _line_span(raw: bytes, start: int, end: int) -> tuple[int, int]:
    """Convert inclusive LF-based line numbers to exact byte boundaries."""
    offsets = [0]
    offsets.extend(index + 1 for index, byte in enumerate(raw) if byte == 10)
    if offsets[-1] == len(raw):
        offsets.pop()
    if type(start) is not int or type(end) is not int or not 1 <= start <= end <= len(offsets):
        raise ValueError("Required line span is outside the source")
    return offsets[start - 1], offsets[end] if end < len(offsets) else len(raw)


def _direct_page(root: Path, file: str, digest: str, offset: int, end: int) -> dict:
    # Reuse R1 containment, regular-file, 2MiB and current ignore-policy checks.
    if _skipped(file) or file not in _candidates(root):
        raise GraphFreeError("SOURCE_UNAVAILABLE", "Source is no longer eligible")
    raw = _source_bytes(root, file)
    if _digest(raw) != digest:
        raise GraphFreeError("SOURCE_STALE", "Source changed after span selection")
    if b"\x00" in raw:
        raise GraphFreeError("SOURCE_UNAVAILABLE", "Source is not an eligible text file")
    if not 0 <= offset <= end <= len(raw):
        raise GraphFreeError("INVALID_SOURCE_REF", "Invalid direct source extent")
    try:
        raw.decode("utf-8")
        raw[:offset].decode("utf-8")
        raw[:end].decode("utf-8")
    except UnicodeError as exc:
        raise GraphFreeError("INVALID_SOURCE_REF", "Extent is not UTF-8 aligned") from exc
    stop = min(end, offset + DIRECT_MAX_BYTES)
    # The byte cap can split a long line; continuation is byte-based and exact.
    position = offset
    for _ in range(DIRECT_MAX_LINES):
        newline = raw.find(b"\n", position, stop)
        if newline < 0:
            break
        position = newline + 1
    else:
        stop = position
    while stop > offset and stop < len(raw) and raw[stop] & 0xC0 == 0x80:
        stop -= 1
    if stop == offset and offset < end:
        raise GraphFreeError("OUTPUT_BUDGET_EXCEEDED", "Direct source page cannot progress")
    return {"source": {"file": file, "content_hash": digest,
                       "start_byte": offset, "end_byte": stop,
                       "content": raw[offset:stop].decode("utf-8")},
            "complete": stop == end, "next_offset": None if stop == end else stop,
            "limits": {"max_lines": DIRECT_MAX_LINES, "max_source_bytes": DIRECT_MAX_BYTES}}


def _coverage(sources: list[dict], original: bytes, file: str,
              start: int, end: int) -> dict:
    """Validate delivered bytes independently and account for overlap and waste."""
    digest = _digest(original)
    intervals = []
    required = bytearray(end - start)
    seen = bytearray(end - start)
    delivered = 0
    for source in sources:
        left, right = source["start_byte"], source["end_byte"]
        raw = source["content"].encode("utf-8")
        if (source["file"] != file or source["content_hash"] != digest
                or not 0 <= left <= right <= len(original)
                or raw != original[left:right]):
            raise ValueError("Delivered source differs from independent original bytes")
        delivered += len(raw)
        intervals.append((left, right))
        lo, hi = max(start, left), min(end, right)
        if lo < hi:
            required[lo - start:hi - start] = raw[lo - left:hi - left]
            seen[lo - start:hi - start] = b"\1" * (hi - lo)
    unique = 0
    previous = 0
    for left, right in sorted(intervals):
        unique += max(0, right - max(left, previous))
        previous = max(previous, right)
    covered = sum(seen)
    return {"complete": covered == end - start,
            "covered_required_bytes": covered,
            "delivered_source_bytes": delivered,
            "unique_source_bytes": unique,
            "extra_source_bytes": unique - covered,
            "duplicate_source_bytes": delivered - unique,
            "delivered_required_sha256": _digest(bytes(required)) if all(seen) else None}


def _covers(sources: list[dict], start: int, end: int) -> bool:
    cursor = start
    for source in sorted(sources, key=lambda row: row["start_byte"]):
        if source["start_byte"] > cursor:
            return False
        cursor = max(cursor, source["end_byte"])
        if cursor >= end:
            return True
    return cursor >= end


def run_case(case: dict, mode: str, config: dict) -> dict[str, Any]:
    """Replay with 'r1', 'direct', or 'direct_full_refresh'.

    Required config: source_root and output_dir (private receipt destination).
    Optional store and run_id allow caller-controlled isolated R1 inventory and
    receipt labels. content_sha256 is the required span digest, not file digest.
    """
    if mode not in {"r1", "direct", "direct_full_refresh"}:
        raise ValueError("Delivery mode must be r1, direct, or direct_full_refresh")
    root = _repo(config["source_root"])
    output = Path(config["output_dir"])
    output.mkdir(parents=True, exist_ok=True)
    run_id = config.get("run_id") or uuid.uuid4().hex
    # Keep caller labels from selecting arbitrary receipt paths.
    label = _digest(f"{case['id']}:{run_id}".encode())[:20]
    receipt = output / f"{mode}-{label}.json"
    result = {"case_id": case["id"], "mode": mode, "complete": False,
              "required_bytes": 0, "covered_required_bytes": 0,
              "delivered_source_bytes": 0, "unique_source_bytes": 0,
              "extra_source_bytes": 0, "duplicate_source_bytes": 0,
              "tool_calls": 0, "encoded_output_bytes": 0, "elapsed_ns": 0,
              "required_sha256": None, "delivered_required_sha256": None,
              "source_extent_complete": False, "error": None,
              "receipt_path": str(receipt)}
    packets: list[dict] = []
    sources: list[dict] = []
    started = None
    original = None
    try:
        file = case["file"]
        # Fixed oracle and source identity, prepared before the timed acquisition.
        original = _source_bytes(root, file)
        original_digest = _digest(original)
        start, end = _line_span(original, case["start_line"], case["end_line"])
        required = original[start:end]
        result.update(required_bytes=len(required), required_sha256=_digest(required))
        if result["required_sha256"] != case["content_sha256"]:
            raise GraphFreeError("FIXTURE_STALE", "Frozen required span differs from case hash")
        service = IntegratedSource(Path(config.get("store", output / "r1-store")))

        def deliver(operation, name):
            result["tool_calls"] += 1
            try:
                packet = operation()
            except (GraphFreeError, OSError, ValueError) as exc:
                packet = {"error": {"code": getattr(exc, "code", "SOURCE_UNAVAILABLE"),
                                    "message": str(exc), "details": getattr(exc, "details", {})}}
                packets.append({"operation": name, "packet": packet})
                result["encoded_output_bytes"] += len(_canonical(
                    {"content": [], "structuredContent": packet, "isError": True}))
                raise
            packets.append({"operation": name, "packet": packet})
            envelope = {"content": [], "structuredContent": packet, "isError": False}
            result["encoded_output_bytes"] += len(_canonical(envelope))
            rows = packet.get("sources", []) if name == "retrieve" else [packet["source"]]
            sources.extend(rows)
            return packet

        started = time.perf_counter_ns()
        if mode == "r1":
            packet = deliver(lambda: service.retrieve(root, file), "retrieve")
            item = next((row for row in packet["items"] if row["extent"]["file"] == file), None)
            if item is None:
                raise GraphFreeError("SOURCE_UNAVAILABLE", "Exact file was not delivered")
            result["source_extent_complete"] = item["complete"]
            reference = item["source_ref"]
            # R1 file refs start at byte zero. Preserve every preview/page byte,
            # including overlap; stop only once the requested span is covered.
            while not _covers(sources, start, end):
                packet = deliver(lambda: service.read(root, reference), "read")
                result["source_extent_complete"] = packet["complete"]
                reference = packet["next_source_ref"]
                if reference is None:
                    break
        else:
            offset = start

            def read_direct():
                if mode == "direct_full_refresh":
                    # This is the actual existing inventory implementation,
                    # not an estimated delay or a fixture-derived substitute.
                    service.index_repo(root)
                    hashes = service.inventory(root)["file_hashes"]
                    if file not in hashes:
                        raise GraphFreeError("SOURCE_UNAVAILABLE", "Source is absent from refreshed inventory")
                    if hashes[file] != original_digest:
                        raise GraphFreeError("SOURCE_STALE", "Source differs from pinned original")
                return _direct_page(root, file, original_digest, offset, end)

            while True:
                packet = deliver(read_direct, "read")
                result["source_extent_complete"] = (packet["complete"] and start == 0
                                                    and end == len(original))
                offset = packet["next_offset"]
                if offset is None:
                    break
        result["elapsed_ns"] = time.perf_counter_ns() - started
        result.update(_coverage(sources, original, file, start, end))
        if not result["complete"] or result["delivered_required_sha256"] != result["required_sha256"]:
            raise GraphFreeError("INCOMPLETE_DELIVERY", "Required source span was not delivered exactly")
    except (GraphFreeError, OSError, ValueError, UnicodeError) as exc:
        if started is not None and not result["elapsed_ns"]:
            result["elapsed_ns"] = time.perf_counter_ns() - started
        if original is not None and sources:
            try:
                result.update(_coverage(sources, original, case["file"], start, end))
            except ValueError:
                pass
        result["complete"] = False
        result["error"] = {"code": getattr(exc, "code", type(exc).__name__), "message": str(exc)}
    receipt.write_bytes(_canonical({"result": result, "case": case, "packets": packets}))
    return result
