"""Supplement exact JSON-line delivery evidence for normalized observations.

This adapter is deliberately downstream of the frozen ordinary-adoption
observers.  It neither reconstructs a native rollout nor changes an existing
``model_delivery`` judgment.  It adds exact line-framed evidence and keeps
truncation local to the line where the host inserted its reduction marker.
"""

from __future__ import annotations

import argparse
from collections import Counter
from collections.abc import Mapping, Sequence
from copy import deepcopy
import hashlib
import json
import math
from pathlib import Path
import re
import sys
from typing import Any


DELIVERY_ADAPTER_VERSION = "ordinary-adoption-delivery-v3"
SCHEMA_VERSION = 1
_TEXT_BLOCK_TYPES = frozenset({"input_text", "text"})
_TRUNCATION_MARKER = re.compile(r"…(?P<tokens>[0-9]+) tokens truncated…")


class DeliverySupplementError(ValueError):
    """A normalized observation cannot support the supplementary readout."""


def _compact(value: Any, *, sort_keys: bool = True) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=sort_keys,
    )


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _json_hash(value: Any) -> str:
    return _sha256_text(_compact(value))


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise ValueError(f"duplicate JSON object key: {key}")
        value[key] = item
    return value


def _reject_constant(value: str) -> None:
    raise ValueError(f"non-finite JSON number: {value}")


def _parse_json_line(value: str) -> tuple[bool, Any]:
    try:
        return True, json.loads(
            value,
            object_pairs_hook=_unique_object,
            parse_constant=_reject_constant,
        )
    except (TypeError, ValueError, json.JSONDecodeError):
        return False, None


def _json_equal(left: Any, right: Any) -> bool:
    """Compare JSON values without Python's bool/int equality alias."""

    if isinstance(left, bool) or isinstance(right, bool):
        return type(left) is bool and type(right) is bool and left == right
    if left is None or right is None:
        return left is None and right is None
    if isinstance(left, (int, float)) and isinstance(right, (int, float)):
        return math.isfinite(left) and math.isfinite(right) and left == right
    if isinstance(left, str) or isinstance(right, str):
        return type(left) is str and type(right) is str and left == right
    if isinstance(left, list) or isinstance(right, list):
        return (
            isinstance(left, list)
            and isinstance(right, list)
            and len(left) == len(right)
            and all(_json_equal(a, b) for a, b in zip(left, right, strict=True))
        )
    if isinstance(left, Mapping) or isinstance(right, Mapping):
        return (
            isinstance(left, Mapping)
            and isinstance(right, Mapping)
            and left.keys() == right.keys()
            and all(_json_equal(left[key], right[key]) for key in left)
        )
    return type(left) is type(right) and left == right


def _wire_value(value: Any) -> Any:
    """Normalize integral JSON numbers the way JSON.stringify emits them."""

    if isinstance(value, bool) or value is None or isinstance(value, (str, int)):
        return value
    if isinstance(value, float):
        return int(value) if math.isfinite(value) and value.is_integer() else value
    if isinstance(value, list):
        return [_wire_value(item) for item in value]
    if isinstance(value, Mapping):
        return {key: _wire_value(item) for key, item in value.items()}
    return value


def _text_blocks(raw: Any) -> list[str]:
    if isinstance(raw, str):
        return [raw]
    if isinstance(raw, list):
        return [
            item["text"]
            for item in raw
            if isinstance(item, Mapping)
            and item.get("type") in _TEXT_BLOCK_TYPES
            and isinstance(item.get("text"), str)
        ]
    if raw is None:
        return []
    return [_compact(raw)]


def _line_content(raw_line: str) -> str:
    if raw_line.endswith("\r\n"):
        return raw_line[:-2]
    if raw_line.endswith(("\r", "\n")):
        return raw_line[:-1]
    return raw_line


def _line_records(text: str) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    byte_offset = 0
    fence: str | None = None
    for line_index, raw_line in enumerate(text.splitlines(keepends=True)):
        content = _line_content(raw_line)
        content_bytes = len(content.encode("utf-8"))
        parsed_ok, parsed = _parse_json_line(content)
        marker = _TRUNCATION_MARKER.search(content)
        stripped = content.lstrip()
        fence_marker = next(
            (candidate for candidate in ("```", "~~~") if stripped.startswith(candidate)),
            None,
        )
        quoted_context = fence is not None or fence_marker is not None
        records.append(
            {
                "line_index": line_index,
                "line_number": line_index + 1,
                "start_byte": byte_offset,
                "end_byte": byte_offset + content_bytes,
                "content": content,
                "parsed": parsed,
                "parsed_ok": parsed_ok,
                "quoted_context": quoted_context,
                "marker": marker,
            }
        )
        if fence is None and fence_marker is not None:
            fence = fence_marker
        elif fence is not None and stripped.startswith(fence):
            fence = None
        byte_offset += len(raw_line.encode("utf-8"))
    if not records and text == "":
        return []
    if text and not text.splitlines(keepends=True):
        raise AssertionError("nonempty text must produce a line record")
    return records


def _collect_blocks(observation: Mapping[str, Any]) -> list[dict[str, Any]]:
    outer = observation.get("outer_code_mode")
    if not isinstance(outer, list):
        raise DeliverySupplementError("outer_code_mode must be a list")
    blocks: list[dict[str, Any]] = []
    for request in outer:
        if not isinstance(request, Mapping):
            raise DeliverySupplementError("outer_code_mode contains a non-object")
        call_id = request.get("call_id")
        output_line = request.get("output_line")
        if not isinstance(call_id, str) or not call_id:
            raise DeliverySupplementError("outer Code Mode request has no call_id")
        for block_index, text in enumerate(_text_blocks(request.get("output"))):
            output_ref = f"outer:{call_id}:line:{output_line}:block:{block_index}"
            lines = _line_records(text)
            marker_lines = [line for line in lines if line["marker"] is not None]
            blocks.append(
                {
                    "call_id": call_id,
                    "output_line": output_line,
                    "block_index": block_index,
                    "output_ref": output_ref,
                    "bytes": len(text.encode("utf-8")),
                    "sha256": _sha256_text(text),
                    "warning_present": "Warning: truncated output" in text,
                    "marker_count": len(marker_lines),
                    "text": text,
                    "lines": lines,
                }
            )
    return blocks


def _candidates(result: Mapping[str, Any]) -> list[tuple[str, Any]]:
    candidates: list[tuple[str, Any]] = []
    if "structuredContent" in result:
        candidates.append(("structuredContent", result["structuredContent"]))
    candidates.append(("result", result))
    return candidates


def _line_provenance(block: Mapping[str, Any], line: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "output_ref": block["output_ref"],
        "call_id": block["call_id"],
        "output_line": block["output_line"],
        "block_index": block["block_index"],
        "line_index": line["line_index"],
        "line_number": line["line_number"],
        "start_byte": line["start_byte"],
        "end_byte": line["end_byte"],
    }


def _exact_matches(
    result: Mapping[str, Any], blocks: Sequence[Mapping[str, Any]]
) -> list[dict[str, Any]]:
    matches: list[dict[str, Any]] = []
    for block in blocks:
        block_line_matches: list[dict[str, Any]] = []
        for line in block["lines"]:
            if not line["parsed_ok"] or line["quoted_context"]:
                continue
            for candidate_name, candidate in _candidates(result):
                if not _json_equal(line["parsed"], candidate):
                    continue
                block_line_matches.append(
                    {
                        **_line_provenance(block, line),
                        "match": f"{candidate_name}_json_line",
                        "candidate_sha256": _json_hash(candidate),
                        "block_warning_present": block["warning_present"],
                        "line_truncation": "none",
                    }
                )
                break
        matches.extend(block_line_matches)
        if block_line_matches:
            continue
        parsed_ok, parsed = _parse_json_line(block["text"])
        if not parsed_ok:
            continue
        for candidate_name, candidate in _candidates(result):
            if not _json_equal(parsed, candidate):
                continue
            matches.append(
                {
                    "output_ref": block["output_ref"],
                    "call_id": block["call_id"],
                    "output_line": block["output_line"],
                    "block_index": block["block_index"],
                    "line_index": None,
                    "line_number": None,
                    "start_byte": 0,
                    "end_byte": block["bytes"],
                    "match": f"{candidate_name}_json_block",
                    "candidate_sha256": _json_hash(candidate),
                    "block_warning_present": block["warning_present"],
                    "line_truncation": "not_applicable",
                }
            )
            break
    return matches


def _clipping_evidence(
    result: Mapping[str, Any], blocks: Sequence[Mapping[str, Any]]
) -> list[dict[str, Any]]:
    evidence: list[dict[str, Any]] = []
    for block in blocks:
        for line in block["lines"]:
            marker = line["marker"]
            if marker is None or line["parsed_ok"] or line["quoted_context"]:
                continue
            prefix, suffix = line["content"][: marker.start()], line["content"][marker.end() :]
            if not prefix or not suffix:
                continue
            for candidate_name, candidate in _candidates(result):
                serialized = _compact(_wire_value(candidate), sort_keys=False)
                if (
                    len(serialized) <= len(prefix) + len(suffix)
                    or not serialized.startswith(prefix)
                    or not serialized.endswith(suffix)
                ):
                    continue
                marker_start = line["start_byte"] + len(prefix.encode("utf-8"))
                marker_end = marker_start + len(marker.group(0).encode("utf-8"))
                evidence.append(
                    {
                        **_line_provenance(block, line),
                        "candidate": candidate_name,
                        "candidate_sha256": _json_hash(candidate),
                        "qualification": "unproven_clipped_exact_fragments",
                        "reported_omitted_tokens": int(marker.group("tokens")),
                        "marker_start_byte": marker_start,
                        "marker_end_byte": marker_end,
                        "retained_prefix_bytes": len(prefix.encode("utf-8")),
                        "retained_suffix_bytes": len(suffix.encode("utf-8")),
                    }
                )
                break
    return evidence


def _public_block(block: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "output_ref": block["output_ref"],
        "call_id": block["call_id"],
        "output_line": block["output_line"],
        "block_index": block["block_index"],
        "bytes": block["bytes"],
        "sha256": block["sha256"],
        "warning_present": block["warning_present"],
        "marker_count": block["marker_count"],
    }


def supplement_delivery(observation: Mapping[str, Any]) -> dict[str, Any]:
    """Return exact supplementary delivery evidence without mutating *observation*."""

    if not isinstance(observation, Mapping):
        raise DeliverySupplementError("observation must be an object")
    before = _compact(observation)
    calls = observation.get("mcp_calls")
    if not isinstance(calls, list):
        raise DeliverySupplementError("mcp_calls must be a list")
    blocks = _collect_blocks(observation)

    work: list[dict[str, Any]] = []
    exact_users: Counter[tuple[Any, ...]] = Counter()
    for call in calls:
        if not isinstance(call, Mapping):
            raise DeliverySupplementError("mcp_calls contains a non-object")
        result = call.get("result")
        item_id = call.get("item_id")
        line = call.get("line")
        if not isinstance(result, Mapping):
            raise DeliverySupplementError("MCP call has no result object")
        if not isinstance(item_id, str) or not item_id:
            raise DeliverySupplementError("MCP call has no item_id")
        if type(line) is not int or line < 1:
            raise DeliverySupplementError("MCP call has no positive native line")
        exact = _exact_matches(result, blocks)
        clipped = [] if exact else _clipping_evidence(result, blocks)
        for match in exact:
            exact_users[
                (
                    match["output_ref"],
                    match["start_byte"],
                    match["end_byte"],
                )
            ] += 1
        work.append({"call": call, "exact": exact, "clipped": clipped})

    supplemented_calls: list[dict[str, Any]] = []
    for entry in work:
        call, exact, clipped = entry["call"], entry["exact"], entry["clipped"]
        if exact:
            ambiguous = any(
                exact_users[
                    (
                        match["output_ref"],
                        match["start_byte"],
                        match["end_byte"],
                    )
                ]
                > 1
                for match in exact
            )
            status = "ambiguous_exact" if ambiguous else "full_exact"
        elif clipped:
            status = "unproven_clipped"
        elif blocks:
            status = "unproven"
        else:
            status = "not_emitted"
        original = call.get("model_delivery")
        original_status = original.get("status") if isinstance(original, Mapping) else None
        supplemented_calls.append(
            {
                "native_result_ref": f"native:{call['item_id']}:line:{call['line']}",
                "item_id": call["item_id"],
                "native_line": call["line"],
                "server": call.get("server"),
                "tool": call.get("tool"),
                "canonical_result_json_bytes": call.get("canonical_result_json_bytes"),
                "canonical_result_json_sha256": call.get("canonical_result_json_sha256")
                or _json_hash(call["result"]),
                "original_model_delivery": deepcopy(original),
                "original_status": original_status,
                "supplemental_model_delivery": {
                    "status": status,
                    "exact_matches": exact,
                    "clipping_evidence": clipped,
                    "unrelated_truncation_not_applied": not exact
                    and not clipped
                    and any(block["warning_present"] for block in blocks),
                },
            }
        )

    if _compact(observation) != before:
        raise AssertionError("supplement adapter mutated its observation input")
    run = observation.get("run")
    retained = observation.get("retained_interval")
    return {
        "schema_version": SCHEMA_VERSION,
        "adapter_version": DELIVERY_ADAPTER_VERSION,
        "kind": "supplemental_delivery_interpretation",
        "frozen_outcome_unchanged": True,
        "source": {
            "run_id": run.get("run_id") if isinstance(run, Mapping) else None,
            "thread_id": run.get("thread_id") if isinstance(run, Mapping) else None,
            "turn_id": run.get("turn_id") if isinstance(run, Mapping) else None,
            "retained_interval_sha256": retained.get("sha256")
            if isinstance(retained, Mapping)
            else None,
            "normalized_observation_sha256": _sha256_text(before),
        },
        "outer_blocks": [_public_block(block) for block in blocks],
        "calls": supplemented_calls,
        "limits": {
            "exactness": "whole parsed JSON-line equality only",
            "clipping": "candidate-aligned fragments around a marker remain unproven",
            "attribution": "identical native invocations remain ambiguous without trusted host provenance",
            "interpretation": "supplement only; no frozen result, review, score, or answer grade is revised",
        },
    }


def _main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("observation", type=Path)
    arguments = parser.parse_args(argv)
    try:
        raw = json.loads(arguments.observation.read_text(encoding="utf-8"))
        normalized = raw.get("observation", raw) if isinstance(raw, Mapping) else raw
        result = supplement_delivery(normalized)
    except (OSError, json.JSONDecodeError, DeliverySupplementError) as exc:
        print(str(exc), file=sys.stderr)
        return 2
    json.dump(result, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
