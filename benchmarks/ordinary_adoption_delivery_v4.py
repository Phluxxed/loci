"""Supplement delivery evidence for exact JSON values nested in wrappers.

Version 4 retains the version 3 line/block judgments and additionally accepts
a native result only when a strict JSON value at a structurally valid nested
position equals the complete native result.  The emitted value's byte span is
kept even when content later in its outer wrapper is incomplete.
"""

from __future__ import annotations

import argparse
from bisect import bisect_right
from collections.abc import Mapping, Sequence
from copy import deepcopy
import json
from pathlib import Path
import sys
from typing import Any

from benchmarks.ordinary_adoption_delivery_v3 import (
    DeliverySupplementError,
    _TRUNCATION_MARKER,
    _collect_blocks,
    _json_equal,
    _json_hash,
    _reject_constant,
    _sha256_text,
    _unique_object,
    supplement_delivery as _supplement_delivery_v3,
)


DELIVERY_ADAPTER_VERSION = "ordinary-adoption-delivery-v4"
SCHEMA_VERSION = 1
_MAX_BLOCK_BYTES = 2_000_000
_MAX_CONTAINER_DEPTH = 64
_MAX_SCANNED_VALUES = 20_000
_JSON_WHITESPACE = " \t\r\n"


class _NestedScanner:
    def __init__(
        self,
        text: str,
        block: Mapping[str, Any],
        candidates: Sequence[tuple[int, Mapping[str, Any]]],
    ) -> None:
        self.text = text
        self.block = block
        self.candidates = candidates
        self.decoder = json.JSONDecoder(
            object_pairs_hook=_unique_object,
            parse_constant=_reject_constant,
        )
        self.matches: list[dict[str, Any]] = []
        self.omissions: list[dict[str, Any]] = []
        self.scanned_values = 0
        self._byte_offsets = [0]
        for character in text:
            self._byte_offsets.append(
                self._byte_offsets[-1] + len(character.encode("utf-8"))
            )
        self._line_starts = [0]
        self._line_starts.extend(
            index + 1 for index, character in enumerate(text) if character == "\n"
        )

    def _byte(self, character_offset: int) -> int:
        return self._byte_offsets[character_offset]

    def _skip_whitespace(self, position: int) -> int:
        while position < len(self.text) and self.text[position] in _JSON_WHITESPACE:
            position += 1
        return position

    def _location(self, position: int) -> dict[str, int]:
        line_index = bisect_right(self._line_starts, position) - 1
        return {"line_index": line_index, "line_number": line_index + 1}

    def _omit(
        self,
        reason: str,
        position: int,
        path: Sequence[str | int],
        **details: Any,
    ) -> None:
        self.omissions.append(
            {
                "output_ref": self.block["output_ref"],
                "reason": reason,
                **self._location(position),
                "start_byte": self._byte(position),
                "json_path": list(path),
                **details,
            }
        )

    def _decode(self, position: int) -> tuple[bool, Any, int | None]:
        try:
            value, end = self.decoder.raw_decode(self.text, position)
        except (ValueError, RecursionError):
            return False, None, None
        return True, value, end

    def _consider(
        self,
        value: Any,
        start: int,
        end: int,
        path: Sequence[str | int],
        root_start: int,
    ) -> None:
        if not isinstance(value, Mapping):
            return
        for call_index, candidate in self.candidates:
            if not _json_equal(value, candidate):
                continue
            emitted = self.text[start:end]
            immediate = path[-1] if path else None
            outer_marker = any(
                marker.end() <= start or marker.start() >= end
                for marker in _TRUNCATION_MARKER.finditer(self.text)
            )
            self.matches.append(
                {
                    "_call_index": call_index,
                    "output_ref": self.block["output_ref"],
                    "call_id": self.block["call_id"],
                    "output_line": self.block["output_line"],
                    "block_index": self.block["block_index"],
                    **self._location(start),
                    "start_byte": self._byte(start),
                    "end_byte": self._byte(end),
                    "match": "result_json_nested",
                    "candidate_sha256": _json_hash(candidate),
                    "emitted_value_sha256": _sha256_text(emitted),
                    "block_warning_present": self.block["warning_present"],
                    "line_truncation": "none",
                    "outer_truncation_marker_outside_value": outer_marker,
                    "json_path": list(path),
                    "wrapper_key": immediate if isinstance(immediate, str) else None,
                    "wrapper_root_start_byte": self._byte(root_start),
                    "outer_wrapper_complete": None,
                    "scope": "complete nested JSON value equal in every native result field",
                }
            )

    def _scan_value(
        self,
        position: int,
        path: Sequence[str | int],
        depth: int,
        root_start: int,
    ) -> tuple[int | None, bool]:
        if self.scanned_values >= _MAX_SCANNED_VALUES:
            self._omit(
                "value_limit",
                position,
                path,
                limit=_MAX_SCANNED_VALUES,
            )
            return None, False
        self.scanned_values += 1
        parsed, value, end = self._decode(position)
        if parsed and end is not None:
            self._consider(value, position, end, path, root_start)
            if self.text[position] in "[{":
                if depth >= _MAX_CONTAINER_DEPTH:
                    self._omit(
                        "depth_limit",
                        position,
                        path,
                        limit=_MAX_CONTAINER_DEPTH,
                    )
                else:
                    self._scan_container(position, path, depth, root_start)
            return end, True
        if position < len(self.text) and self.text[position] in "[{":
            if depth >= _MAX_CONTAINER_DEPTH:
                self._omit(
                    "depth_limit",
                    position,
                    path,
                    limit=_MAX_CONTAINER_DEPTH,
                )
                return None, False
            return self._scan_container(position, path, depth, root_start)
        self._omit("invalid_or_incomplete_value", position, path)
        return None, False

    def _scan_container(
        self,
        start: int,
        path: Sequence[str | int],
        depth: int,
        root_start: int,
    ) -> tuple[int | None, bool]:
        if self.text[start] == "{":
            return self._scan_object(start, path, depth, root_start)
        return self._scan_array(start, path, depth, root_start)

    def _scan_object(
        self,
        start: int,
        path: Sequence[str | int],
        depth: int,
        root_start: int,
    ) -> tuple[int | None, bool]:
        position = self._skip_whitespace(start + 1)
        first = True
        keys: set[str] = set()
        while True:
            if position >= len(self.text):
                self._omit("incomplete_container", start, path)
                return None, False
            if self.text[position] == "}":
                return position + 1, True
            if not first:
                if self.text[position] != ",":
                    self._omit("invalid_container_separator", position, path)
                    return None, False
                position = self._skip_whitespace(position + 1)
            parsed, key, key_end = self._decode(position)
            if not parsed or key_end is None or not isinstance(key, str):
                self._omit("invalid_object_key", position, path)
                return None, False
            if key in keys:
                self._omit("duplicate_wrapper_key", position, (*path, key))
                return None, False
            keys.add(key)
            position = self._skip_whitespace(key_end)
            if position >= len(self.text) or self.text[position] != ":":
                self._omit("missing_object_colon", position, (*path, key))
                return None, False
            position = self._skip_whitespace(position + 1)
            end, complete = self._scan_value(
                position,
                (*path, key),
                depth + 1,
                root_start,
            )
            if not complete or end is None:
                return None, False
            position = self._skip_whitespace(end)
            first = False

    def _scan_array(
        self,
        start: int,
        path: Sequence[str | int],
        depth: int,
        root_start: int,
    ) -> tuple[int | None, bool]:
        position = self._skip_whitespace(start + 1)
        index = 0
        while True:
            if position >= len(self.text):
                self._omit("incomplete_container", start, path)
                return None, False
            if self.text[position] == "]":
                return position + 1, True
            if index:
                if self.text[position] != ",":
                    self._omit("invalid_container_separator", position, path)
                    return None, False
                position = self._skip_whitespace(position + 1)
            end, complete = self._scan_value(
                position,
                (*path, index),
                depth + 1,
                root_start,
            )
            if not complete or end is None:
                return None, False
            position = self._skip_whitespace(end)
            index += 1

    def scan_root(self, start: int) -> None:
        first_match = len(self.matches)
        end, complete = self._scan_container(start, (), 0, start)
        if complete and end is not None:
            line_end = self.text.find("\n", end)
            line_end = len(self.text) if line_end < 0 else line_end
            if self.text[end:line_end].strip():
                self._omit("non_json_trailing_text", end, ())
                del self.matches[first_match:]
                return
        for match in self.matches[first_match:]:
            match["outer_wrapper_complete"] = complete


def _root_starts(text: str) -> list[int]:
    starts: list[int] = []
    character_offset = 0
    fence: str | None = None
    for raw_line in text.splitlines(keepends=True):
        content = raw_line[:-2] if raw_line.endswith("\r\n") else raw_line.rstrip("\r\n")
        stripped = content.lstrip()
        fence_marker = next(
            (candidate for candidate in ("```", "~~~") if stripped.startswith(candidate)),
            None,
        )
        quoted_context = fence is not None or fence_marker is not None
        if not quoted_context and stripped.startswith(("{", "[")):
            starts.append(character_offset + len(content) - len(stripped))
        if fence is None and fence_marker is not None:
            fence = fence_marker
        elif fence is not None and stripped.startswith(fence):
            fence = None
        character_offset += len(raw_line)
    return starts


def _nested_matches(
    blocks: Sequence[Mapping[str, Any]],
    calls: Sequence[Mapping[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], int]:
    candidates = [(index, call["result"]) for index, call in enumerate(calls)]
    matches: list[dict[str, Any]] = []
    omissions: list[dict[str, Any]] = []
    scanned_values = 0
    seen: set[tuple[int, str, int, int]] = set()
    for block in blocks:
        if block["bytes"] > _MAX_BLOCK_BYTES:
            omissions.append(
                {
                    "output_ref": block["output_ref"],
                    "reason": "block_byte_limit",
                    "bytes": block["bytes"],
                    "limit": _MAX_BLOCK_BYTES,
                }
            )
            continue
        scanner = _NestedScanner(block["text"], block, candidates)
        for start in _root_starts(block["text"]):
            scanner.scan_root(start)
        scanned_values += scanner.scanned_values
        omissions.extend(scanner.omissions)
        for match in scanner.matches:
            identity = (
                match["_call_index"],
                match["output_ref"],
                match["start_byte"],
                match["end_byte"],
            )
            if identity not in seen:
                seen.add(identity)
                matches.append(match)
    unique_omissions = []
    seen_omissions: set[str] = set()
    for omission in omissions:
        identity = json.dumps(omission, ensure_ascii=False, sort_keys=True)
        if identity not in seen_omissions:
            seen_omissions.add(identity)
            unique_omissions.append(omission)
    return matches, unique_omissions, scanned_values


def supplement_delivery(observation: Mapping[str, Any]) -> dict[str, Any]:
    """Return v3-compatible evidence plus strict nested-wrapper matches."""

    if not isinstance(observation, Mapping):
        raise DeliverySupplementError("observation must be an object")
    calls = observation.get("mcp_calls")
    if not isinstance(calls, list):
        raise DeliverySupplementError("mcp_calls must be a list")
    before = deepcopy(observation)
    supplement = _supplement_delivery_v3(observation)
    blocks = _collect_blocks(observation)
    nested, omissions, scanned_values = _nested_matches(blocks, calls)

    nested_by_call: dict[int, list[dict[str, Any]]] = {}
    for raw_match in nested:
        match = dict(raw_match)
        call_index = match.pop("_call_index")
        nested_by_call.setdefault(call_index, []).append(match)

    for index, supplemented_call in enumerate(supplement["calls"]):
        delivery = supplemented_call["supplemental_model_delivery"]
        added = nested_by_call.get(index, [])
        delivery["exact_matches"].extend(deepcopy(added))
        delivery["nested_wrapper_matches"] = deepcopy(added)

    exact_users: dict[tuple[Any, ...], set[int]] = {}
    for call_index, supplemented_call in enumerate(supplement["calls"]):
        for match in supplemented_call["supplemental_model_delivery"]["exact_matches"]:
            location = (match["output_ref"], match["start_byte"], match["end_byte"])
            exact_users.setdefault(location, set()).add(call_index)
    for supplemented_call in supplement["calls"]:
        delivery = supplemented_call["supplemental_model_delivery"]
        exact = delivery["exact_matches"]
        if exact:
            ambiguous = any(
                len(
                    exact_users[
                        (match["output_ref"], match["start_byte"], match["end_byte"])
                    ]
                )
                > 1
                for match in exact
            )
            delivery["status"] = "ambiguous_exact" if ambiguous else "full_exact"
            delivery["unrelated_truncation_not_applied"] = False

    supplement["adapter_version"] = DELIVERY_ADAPTER_VERSION
    supplement["nested_wrapper_scan"] = {
        "status": "partial" if omissions else "complete",
        "scanned_values": scanned_values,
        "omissions": omissions,
        "limits": {
            "block_bytes": _MAX_BLOCK_BYTES,
            "container_depth": _MAX_CONTAINER_DEPTH,
            "values_per_block": _MAX_SCANNED_VALUES,
            "root_scope": "JSON object or array beginning a non-quoted output line",
            "candidate_scope": "strict complete nested value equal to the full native result",
        },
    }
    if observation != before:
        raise AssertionError("supplement adapter mutated its observation input")
    return supplement


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
