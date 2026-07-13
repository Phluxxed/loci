#!/usr/bin/env python3
"""Replay the frozen graph-shape questions through loci anchor selection."""

from __future__ import annotations

import argparse
import hashlib
import json
from math import ceil
from pathlib import Path
from time import perf_counter
from typing import Any, Mapping

from loci.service import graph_anchors, index_repo


_MAX_CONTRACT_BYTES = 1_048_576
_REQUIRED_FIXTURE_FIELDS = frozenset(
    {
        "id",
        "corpus",
        "shape",
        "question",
        "expected_pages",
        "bridge_paths_any",
        "bridge_literals_any",
        "forbidden_paths",
        "required_literals",
        "answerable",
        "graph_expected",
    }
)


def load_contract(path: str | Path) -> dict[str, Any]:
    contract_path = Path(path)
    raw = contract_path.read_bytes()
    if len(raw) > _MAX_CONTRACT_BYTES:
        raise ValueError("benchmark contract exceeds the byte limit")
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise ValueError("benchmark contract must be an object")
    validate_contract(value)
    return value


def validate_contract(contract: Mapping[str, Any]) -> None:
    if contract.get("schema_version") != "1":
        raise ValueError("unsupported benchmark schema version")
    corpora = contract.get("corpora")
    fixtures = contract.get("fixtures")
    if not isinstance(corpora, Mapping) or not corpora:
        raise ValueError("benchmark contract needs corpora")
    if not isinstance(fixtures, list) or not fixtures:
        raise ValueError("benchmark contract needs fixtures")

    seen_ids: set[str] = set()
    for fixture in fixtures:
        if not isinstance(fixture, Mapping):
            raise ValueError("benchmark fixture must be an object")
        missing = _REQUIRED_FIXTURE_FIELDS - set(fixture)
        if missing:
            raise ValueError(f"benchmark fixture missing {sorted(missing)[0]}")
        fixture_id = fixture["id"]
        if not isinstance(fixture_id, str) or not fixture_id:
            raise ValueError("benchmark fixture id must be a non-empty string")
        if fixture_id in seen_ids:
            raise ValueError(f"duplicate benchmark fixture id: {fixture_id}")
        seen_ids.add(fixture_id)
        corpus = fixture["corpus"]
        if not isinstance(corpus, str) or corpus not in corpora:
            raise ValueError(f"unknown benchmark fixture corpus: {corpus}")
        if not isinstance(fixture["question"], str) or not fixture["question"].strip():
            raise ValueError("benchmark fixture question must be a non-empty string")
        expected_pages = fixture["expected_pages"]
        if not isinstance(expected_pages, list) or not all(
            isinstance(page, str) and page for page in expected_pages
        ):
            raise ValueError("benchmark fixture expected_pages must be strings")


def run_benchmark(
    contract: Mapping[str, Any],
    roots: Mapping[str, Path],
    *,
    max_anchors: int = 10,
) -> dict[str, Any]:
    validate_contract(contract)
    corpus_names = set(contract["corpora"])
    missing_roots = sorted(corpus_names - set(roots))
    if missing_roots:
        raise ValueError(f"benchmark root missing for corpus: {missing_roots[0]}")

    resolved_roots = {
        name: Path(roots[name]).expanduser().resolve()
        for name in sorted(corpus_names)
    }
    for root in resolved_roots.values():
        index_repo(root, incremental=True)

    fixture_results: list[dict[str, Any]] = []
    for fixture in contract["fixtures"]:
        corpus = str(fixture["corpus"])
        start = perf_counter()
        response = graph_anchors(
            resolved_roots[corpus],
            str(fixture["question"]),
            max_anchors=max_anchors,
        )
        latency_ms = (perf_counter() - start) * 1000
        response_bytes = len(
            json.dumps(
                response,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        )
        anchor_files = [
            str(anchor["node"]["attributes"]["file"])
            for anchor in response["anchors"]
        ]
        expected_pages = list(fixture["expected_pages"])
        endpoint_hits = [page for page in expected_pages if page in anchor_files]
        endpoint_recall = (
            len(endpoint_hits) / len(expected_pages)
            if expected_pages
            else None
        )
        if anchor_files:
            anchor_precision = len(endpoint_hits) / len(anchor_files)
        else:
            anchor_precision = 1.0 if not expected_pages else 0.0
        eligible_units = int(response["counts"]["eligible_units"])
        anchor_fraction = (
            len(anchor_files) / eligible_units if eligible_units else 0.0
        )
        cap_satisfied = (
            anchor_fraction < 0.10
            if eligible_units >= 11
            else len(anchor_files) <= 1
        )
        fixture_results.append(
            {
                "id": fixture["id"],
                "corpus": corpus,
                "shape": fixture["shape"],
                "question": fixture["question"],
                "expected_pages": expected_pages,
                "anchors": response["anchors"],
                "question_terms": response["question_terms"],
                "counts": response["counts"],
                "budget": response["budget"],
                "diagnostics": response["diagnostics"],
                "latency_ms": round(latency_ms, 3),
                "score": {
                    "endpoint_hits": endpoint_hits,
                    "endpoint_recall": (
                        round(endpoint_recall, 3)
                        if endpoint_recall is not None
                        else None
                    ),
                    "anchor_precision": round(anchor_precision, 3),
                    "anchor_fraction": round(anchor_fraction, 6),
                    "corpus_cap_satisfied": cap_satisfied,
                    "response_bytes": response_bytes,
                    "estimated_tokens": ceil(response_bytes / 4),
                },
            }
        )

    result = {
        "schema_version": "1",
        "contract_approved_on": contract.get("approved_on"),
        "roots": {name: str(root) for name, root in resolved_roots.items()},
        "fixtures": fixture_results,
        "summary": _summarize(fixture_results),
    }
    result["deterministic_digest"] = deterministic_digest(result)
    return result


def deterministic_digest(result: Mapping[str, Any]) -> str:
    stable = json.loads(json.dumps(result))
    stable.pop("deterministic_digest", None)
    stable.pop("roots", None)
    for fixture in stable.get("fixtures", []):
        fixture.pop("latency_ms", None)
    summary = stable.get("summary")
    if isinstance(summary, dict):
        summary.pop("mean_latency_ms", None)
    payload = json.dumps(stable, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _summarize(fixtures: list[Mapping[str, Any]]) -> dict[str, Any]:
    expected_slots = sum(len(fixture["expected_pages"]) for fixture in fixtures)
    endpoint_hits = sum(
        len(fixture["score"]["endpoint_hits"]) for fixture in fixtures
    )
    return {
        "expected_endpoint_slots": expected_slots,
        "expected_endpoint_hits": endpoint_hits,
        "endpoint_recall": (
            round(endpoint_hits / expected_slots, 3) if expected_slots else None
        ),
        "mean_anchor_precision": _mean(
            fixture["score"]["anchor_precision"] for fixture in fixtures
        ),
        "max_anchor_fraction": round(
            max(
                (fixture["score"]["anchor_fraction"] for fixture in fixtures),
                default=0.0,
            ),
            6,
        ),
        "all_corpus_caps_satisfied": all(
            fixture["score"]["corpus_cap_satisfied"] for fixture in fixtures
        ),
        "mean_response_bytes": _mean(
            fixture["score"]["response_bytes"] for fixture in fixtures
        ),
        "mean_estimated_tokens": _mean(
            fixture["score"]["estimated_tokens"] for fixture in fixtures
        ),
        "mean_latency_ms": _mean(
            fixture["latency_ms"] for fixture in fixtures
        ),
    }


def _mean(values: Any) -> float | None:
    materialized = list(values)
    if not materialized:
        return None
    return round(sum(materialized) / len(materialized), 3)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--contract", type=Path, required=True)
    parser.add_argument("--ai-graph-root", type=Path, required=True)
    parser.add_argument("--brain-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--max-anchors", type=int, default=10)
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    contract = load_contract(args.contract)
    result = run_benchmark(
        contract,
        {
            "ai_graph_ideas": args.ai_graph_root,
            "brain": args.brain_root,
        },
        max_anchors=args.max_anchors,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(result["summary"], indent=2, sort_keys=True))
    print(f"deterministic_digest={result['deterministic_digest']}")
    print(f"output={args.output.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
