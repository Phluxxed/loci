from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Literal, TypedDict

QUERY_COVERAGE_SCHEMA_VERSION = 1
QUERY_COVERAGE_SAMPLE_LIMIT = 20

CoverageExclusionReason = Literal[
    "ignored",
    "policy_excluded",
    "sensitive_or_binary",
    "unsupported_file_type",
]
QueryScope = Literal["indexed_symbols", "indexed_source_text"]
EXCLUSION_REASONS: tuple[CoverageExclusionReason, ...] = (
    "ignored",
    "policy_excluded",
    "sensitive_or_binary",
    "unsupported_file_type",
)


class QueryCoverageExclusion(TypedDict):
    reason: CoverageExclusionReason
    paths: int
    samples: list[str]
    omitted_samples: int


class StoredQueryCoverage(TypedDict):
    schema_version: int
    state: Literal["complete", "partial", "unknown"]
    scope: Literal["repository"]
    source_scope: Literal["indexed_supported_source"]
    indexed_files: int
    excluded_paths: int | None
    exclusions: list[QueryCoverageExclusion]
    unknown_reason: str | None


class QueryCoverage(StoredQueryCoverage):
    query_scope: QueryScope


@dataclass
class QueryCoverageRecorder:
    _counts: dict[CoverageExclusionReason, int] = field(default_factory=dict)
    _samples: dict[CoverageExclusionReason, list[str]] = field(default_factory=dict)
    _recorded: set[tuple[CoverageExclusionReason, str]] = field(
        default_factory=set
    )

    def record(self, reason: CoverageExclusionReason, path: str) -> None:
        key = (reason, path)
        if key in self._recorded:
            return
        self._recorded.add(key)
        self._counts[reason] = self._counts.get(reason, 0) + 1
        samples = self._samples.setdefault(reason, [])
        if len(samples) < QUERY_COVERAGE_SAMPLE_LIMIT:
            samples.append(path)

    def build(self, indexed_files: int) -> StoredQueryCoverage:
        exclusions: list[QueryCoverageExclusion] = []
        for reason in EXCLUSION_REASONS:
            count = self._counts.get(reason, 0)
            if count == 0:
                continue
            samples = list(self._samples.get(reason, ()))
            exclusions.append({
                "reason": reason,
                "paths": count,
                "samples": samples,
                "omitted_samples": count - len(samples),
            })
        excluded_paths = sum(item["paths"] for item in exclusions)
        return {
            "schema_version": QUERY_COVERAGE_SCHEMA_VERSION,
            "state": "complete" if excluded_paths == 0 else "partial",
            "scope": "repository",
            "source_scope": "indexed_supported_source",
            "indexed_files": indexed_files,
            "excluded_paths": excluded_paths,
            "exclusions": exclusions,
            "unknown_reason": None,
        }


def query_coverage_from_index(
    index: Mapping[str, Any],
    query_scope: QueryScope,
) -> QueryCoverage:
    coverage = stored_query_coverage(index) or _unknown_query_coverage(index)
    return {**coverage, "query_scope": query_scope}


def stored_query_coverage(
    index: Mapping[str, Any],
) -> StoredQueryCoverage | None:
    raw = index.get("coverage")
    if not isinstance(raw, Mapping):
        return None
    state = raw.get("state")
    indexed_files = raw.get("indexed_files")
    excluded_paths = raw.get("excluded_paths")
    raw_exclusions = raw.get("exclusions")
    file_hashes = index.get("file_hashes")
    if (
        raw.get("schema_version") != QUERY_COVERAGE_SCHEMA_VERSION
        or state not in {"complete", "partial"}
        or raw.get("scope") != "repository"
        or raw.get("source_scope") != "indexed_supported_source"
        or not _is_nonnegative_int(indexed_files)
        or not isinstance(file_hashes, dict)
        or indexed_files != len(file_hashes)
        or not _is_nonnegative_int(excluded_paths)
        or not isinstance(raw_exclusions, list)
        or raw.get("unknown_reason") is not None
    ):
        return None

    exclusions: list[QueryCoverageExclusion] = []
    seen_reasons: set[str] = set()
    for raw_exclusion in raw_exclusions:
        if not isinstance(raw_exclusion, Mapping):
            return None
        reason = raw_exclusion.get("reason")
        paths = raw_exclusion.get("paths")
        samples = raw_exclusion.get("samples")
        omitted_samples = raw_exclusion.get("omitted_samples")
        if (
            reason not in EXCLUSION_REASONS
            or reason in seen_reasons
            or not _is_nonnegative_int(paths)
            or paths == 0
            or not isinstance(samples, list)
            or len(samples) > QUERY_COVERAGE_SAMPLE_LIMIT
            or not all(isinstance(sample, str) for sample in samples)
            or not _is_nonnegative_int(omitted_samples)
            or paths != len(samples) + omitted_samples
        ):
            return None
        seen_reasons.add(reason)
        exclusions.append({
            "reason": reason,
            "paths": paths,
            "samples": list(samples),
            "omitted_samples": omitted_samples,
        })

    if excluded_paths != sum(item["paths"] for item in exclusions):
        return None
    if state == "complete" and excluded_paths != 0:
        return None
    if state == "partial" and excluded_paths == 0:
        return None
    return {
        "schema_version": QUERY_COVERAGE_SCHEMA_VERSION,
        "state": state,
        "scope": "repository",
        "source_scope": "indexed_supported_source",
        "indexed_files": indexed_files,
        "excluded_paths": excluded_paths,
        "exclusions": exclusions,
        "unknown_reason": None,
    }


def _unknown_query_coverage(index: Mapping[str, Any]) -> StoredQueryCoverage:
    file_hashes = index.get("file_hashes")
    indexed_files = len(file_hashes) if isinstance(file_hashes, dict) else 0
    return {
        "schema_version": QUERY_COVERAGE_SCHEMA_VERSION,
        "state": "unknown",
        "scope": "repository",
        "source_scope": "indexed_supported_source",
        "indexed_files": indexed_files,
        "excluded_paths": None,
        "exclusions": [],
        "unknown_reason": "coverage_metadata_unavailable",
    }


def _is_nonnegative_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0
