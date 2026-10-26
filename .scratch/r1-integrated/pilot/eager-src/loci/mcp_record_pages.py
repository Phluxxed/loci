"""Project diagnostic records into byte-bounded MCP pages.

The service and stored records retain their full evidence. This module owns
only delivery: projection, size accounting and continuation of a record page.
"""
from __future__ import annotations

import json
from typing import Any, Callable, Literal


DEFAULT_RECORD_OUTPUT_BYTES = 16_384
MIN_RECORD_OUTPUT_BYTES = 2_048
MAX_RECORD_OUTPUT_BYTES = 262_144


def graph_record_page(
    read_page: Callable[[], dict[str, Any]],
    *,
    kind: Literal["references", "calls"],
    detail: str,
    max_output_bytes: int,
) -> dict[str, Any]:
    """Return a complete prefix of the requested page, never skipping a site."""
    # Keep MCP startup independent of the service's parser/storage imports.
    from loci.service import LociError

    if not isinstance(detail, str) or detail not in {"compact", "full"}:
        raise LociError("INVALID_INPUT", "detail must be compact or full")
    if type(max_output_bytes) is not int or not (
        MIN_RECORD_OUTPUT_BYTES <= max_output_bytes <= MAX_RECORD_OUTPUT_BYTES
    ):
        raise LociError(
            "INVALID_INPUT",
            "max_output_bytes must be an integer between 2048 and 262144",
        )

    page = read_page()
    original_items = page["items"]
    items = (
        original_items if detail == "full" else
        [_compact_record(item, kind, page.get("family", "symbol")) for item in original_items]
    )
    offset = page["pagination"]["offset"]

    def candidate(count: int) -> dict[str, Any]:
        clipped = count < len(items)
        result = {
            **page,
            "items": items[:count],
            "counts": {**page["counts"], "returned": count},
            "pagination": {
                **page["pagination"],
                "next_offset": offset + count if clipped else page["pagination"]["next_offset"],
            },
            "detail": detail,
            "budget": {
                "max_output_bytes": max_output_bytes,
                "output_bytes": 0,
                "byte_limit_reached": clipped,
            },
        }
        _account_output_bytes(result)
        return result

    # Even an empty result has an envelope. A nonempty result must deliver at
    # least one whole record or explicitly explain why no progress is possible.
    smallest = candidate(1 if items else 0)
    if smallest["budget"]["output_bytes"] > max_output_bytes:
        # The suggested budget changes the encoded budget field too. Account
        # for that width so retrying the reported minimum can actually fit.
        while smallest["budget"]["max_output_bytes"] != smallest["budget"]["output_bytes"]:
            smallest["budget"]["max_output_bytes"] = smallest["budget"]["output_bytes"]
            _account_output_bytes(smallest)
        raise LociError(
            "OUTPUT_BUDGET_EXCEEDED",
            "The next record or page envelope exceeds max_output_bytes; "
            "increase the budget or request compact detail",
            {
                "offset": offset,
                "detail": detail,
                "max_output_bytes": max_output_bytes,
                "required_output_bytes": smallest["budget"]["output_bytes"],
            },
        )
    if len(items) <= 1:
        return smallest

    # Record count is already bounded by the service. Find the largest prefix
    # fitting the wire budget without repeatedly encoding every smaller page.
    best = smallest
    low, high = 2, len(items)
    while low <= high:
        count = (low + high) // 2
        result = candidate(count)
        if result["budget"]["output_bytes"] <= max_output_bytes:
            best = result
            low = count + 1
        else:
            high = count - 1
    return best


def _compact_record(
    record: dict[str, Any], kind: Literal["references", "calls"], family: str,
) -> dict[str, Any]:
    raw = record["raw"]
    is_call = kind == "calls"
    result = {
        "source_id": record["caller_id"] if is_call else record["source_id"],
        "source_file": raw["source_file"],
        "target_id": record["target_id"],
        "target_file": record["target_file"],
        "language": raw["language"],
        "line": raw["line"],
        "column": raw["column"],
        "start_byte": raw["start_byte"],
        "end_byte": raw["end_byte"],
        "text": raw["callee_text"] if is_call else raw["text"],
        "status": record["status"],
        "resolution": record["resolution"],
        "unresolved_reason": record["unresolved_reason"],
        "resolution_configuration": record["resolution_configuration"],
    }
    if is_call:
        result.update(
            relation="calls",
            callee_start_byte=raw["callee_start_byte"],
            callee_end_byte=raw["callee_end_byte"],
            reference_unresolved_reason=record["reference_unresolved_reason"],
        )
    elif family == "type":
        result.update(
            relation=raw["relation"], context=raw["context"],
            import_unresolved_reason=None,
        )
    else:
        binding = record["binding"]
        result.update(
            relation="references_type" if binding and binding["type_only"] else "references",
            context=None,
            import_unresolved_reason=record["import_unresolved_reason"],
        )
    return result


def _account_output_bytes(result: dict[str, Any]) -> None:
    """Include the size field itself and the structured-only MCP framing."""
    for _ in range(16):
        measured = len(json.dumps(
            {"content": [], "structuredContent": result, "isError": False},
            ensure_ascii=False, separators=(",", ":"),
        ).encode("utf-8"))
        if result["budget"]["output_bytes"] == measured:
            return
        result["budget"]["output_bytes"] = measured
    raise RuntimeError("graph record output accounting did not converge")
