#!/usr/bin/env python3
"""Replay frozen graph-shape questions through bounded Loci traversal."""

from __future__ import annotations

import argparse
import hashlib
import importlib
import json
import os
import shutil
import sys
import tempfile
from contextlib import contextmanager
from dataclasses import dataclass
from math import ceil
from pathlib import Path
from time import perf_counter
from typing import Any, Callable, Iterator, Mapping, Sequence

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from benchmarks.graph_anchor_stage3 import load_contract, validate_contract
from loci.service import get_store, graph_retrieve, index_repo


@dataclass(frozen=True, slots=True)
class WikiRuntime:
    collect_pages: Callable[[Path], Mapping[str, Any]]
    collect_typed_edges: Callable[[Mapping[str, Any]], Sequence[Any]]
    body_link_re: Any
    resolve_link: Callable[[str, str, Mapping[str, Any]], str | None]


def load_wiki_runtime(llm_wiki_root: str | Path) -> WikiRuntime:
    source_root = Path(llm_wiki_root).expanduser().resolve() / "src"
    if not source_root.is_dir():
        raise ValueError(f"llm-wiki source root not found: {source_root}")
    source_value = str(source_root)
    if source_value not in sys.path:
        sys.path.insert(0, source_value)
    documents = importlib.import_module("llm_wiki_core.documents")
    graph = importlib.import_module("llm_wiki_core.graph")
    return WikiRuntime(
        collect_pages=documents.collect_pages,
        collect_typed_edges=graph.collect_typed_edges,
        body_link_re=graph.BODY_LINK_RE,
        resolve_link=graph.resolve_link,
    )


def prepare_wiki_mirror(
    source_root: str | Path,
    mirror_root: str | Path,
    runtime: WikiRuntime,
) -> dict[str, Any]:
    source = Path(source_root).expanduser().resolve()
    mirror = Path(mirror_root).resolve()
    pages = dict(runtime.collect_pages(source))
    if not pages:
        raise ValueError(f"wiki corpus contains no canonical pages: {source}")
    mirror.mkdir(parents=True, exist_ok=True)
    for relative in sorted(pages):
        source_path = source / relative
        target_path = mirror / relative
        if (
            not source_path.is_file()
            or not source_path.resolve().is_relative_to(source)
            or not target_path.resolve().is_relative_to(mirror)
        ):
            raise ValueError(f"canonical wiki page is unsafe: {relative}")
        target_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source_path, target_path)

    profile_dir = mirror / ".loci" / "graph" / "profiles"
    contribution_dir = mirror / ".loci" / "graph" / "contributions"
    profile_dir.mkdir(parents=True)
    contribution_dir.mkdir(parents=True)
    profile = {
        "schema_version": 1,
        "namespace": "llm-wiki",
        "node_rules": [{
            "selector": {"language": "markdown", "page_root": True},
            "attributes": [{
                "name": "mentioned_in_refs",
                "source": "frontmatter.mentioned_in",
                "value_type": "string_list",
                "allowed_values": [],
            }],
        }],
        "edge_types": [
            {
                "type": "body_link",
                "directed": True,
                "allowed_resolutions": ["declared"],
            },
            {
                "type": "mentioned_in",
                "directed": True,
                "allowed_resolutions": ["declared"],
            },
        ],
        "edge_rules": [],
    }
    (profile_dir / "llm-wiki.json").write_text(
        json.dumps(profile, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    index_repo(mirror, incremental=False)
    loaded = get_store().load(mirror)
    if loaded is None:
        raise RuntimeError("temporary wiki mirror did not produce an index")
    roots, frontmatter_lines = _canonical_roots(loaded.get("symbols", []))
    missing_roots = sorted(set(pages) - set(roots))
    if missing_roots:
        raise RuntimeError(f"wiki page lacks a canonical Loci root: {missing_roots[0]}")

    records = []
    for edge in runtime.collect_typed_edges(pages):
        source_file = str(edge.source)
        target_file = str(edge.target)
        edge_type = str(edge.type)
        if source_file not in roots or target_file not in roots:
            raise RuntimeError("wiki edge endpoint is outside the canonical mirror")
        evidence_file, evidence_line = _edge_evidence(
            edge_type,
            source_file,
            target_file,
            pages,
            frontmatter_lines,
            runtime,
        )
        evidence_path = mirror / evidence_file
        records.append({
            "from": roots[source_file],
            "to": roots[target_file],
            "type": edge_type,
            "directed": True,
            "namespace": "llm-wiki",
            "resolution": "declared",
            "evidence": {
                "file": evidence_file,
                "line": evidence_line,
                "content_hash": hashlib.sha256(evidence_path.read_bytes()).hexdigest(),
            },
        })
    _write_contribution_shards(contribution_dir, records)
    indexed = index_repo(mirror, incremental=True)
    if indexed.get("graph_status") != "healthy":
        raise RuntimeError(
            f"temporary wiki graph is degraded: {indexed.get('graph_diagnostics')}"
        )
    final = get_store().load(mirror)
    assert final is not None
    domain_edges = [
        edge for edge in final["graph"]["edges"]
        if edge["namespace"] == "llm-wiki"
    ]
    return {
        "root": mirror,
        "pages": len(pages),
        "edges": len(domain_edges),
        "node_ids": roots,
    }


def run_benchmark(
    contract: Mapping[str, Any],
    roots: Mapping[str, Path],
    *,
    llm_wiki_root: str | Path,
    max_anchors: int = 10,
    max_hops: int = 3,
    max_nodes: int = 64,
    max_paths: int = 8,
    max_evidence_bytes: int = 32_768,
    max_estimated_tokens: int = 8_192,
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
    runtime = load_wiki_runtime(llm_wiki_root)

    with tempfile.TemporaryDirectory(prefix="loci-stage4-") as temp_value:
        temp = Path(temp_value)
        with _temporary_loci_store(temp / "cache"):
            mirrors = {
                name: prepare_wiki_mirror(
                    root,
                    temp / "mirrors" / name,
                    runtime,
                )
                for name, root in resolved_roots.items()
            }
            fixture_results = []
            for fixture in contract["fixtures"]:
                corpus = str(fixture["corpus"])
                start = perf_counter()
                response = graph_retrieve(
                    mirrors[corpus]["root"],
                    str(fixture["question"]),
                    namespaces=["llm-wiki"],
                    edge_types=["body_link", "mentioned_in"],
                    resolutions=["declared"],
                    direction="either",
                    max_anchors=max_anchors,
                    max_hops=max_hops,
                    max_nodes=max_nodes,
                    max_paths=max_paths,
                    max_evidence_bytes=max_evidence_bytes,
                    max_estimated_tokens=max_estimated_tokens,
                )
                latency_ms = (perf_counter() - start) * 1_000
                fixture_results.append(
                    score_fixture(fixture, response, latency_ms=latency_ms)
                )

            result = {
                "schema_version": "1",
                "contract_approved_on": contract.get("approved_on"),
                "roots": {name: str(root) for name, root in resolved_roots.items()},
                "corpora": {
                    name: {
                        "pages": mirror["pages"],
                        "edges": mirror["edges"],
                    }
                    for name, mirror in mirrors.items()
                },
                "limits": {
                    "max_anchors": max_anchors,
                    "max_hops": max_hops,
                    "max_nodes": max_nodes,
                    "max_paths": max_paths,
                    "max_evidence_bytes": max_evidence_bytes,
                    "max_estimated_tokens": max_estimated_tokens,
                },
                "fixtures": fixture_results,
                "summary": summarize(fixture_results),
            }
    result["deterministic_digest"] = deterministic_digest(result)
    return result


def score_fixture(
    fixture: Mapping[str, Any],
    response: Mapping[str, Any],
    *,
    latency_ms: float,
) -> dict[str, Any]:
    selected_paths = [_path_files(path) for path in response.get("paths", [])]
    rejected_paths = [_rejected_path_files(path) for path in response.get("rejected_paths", [])]
    anchor_files = [
        str(anchor["node"]["attributes"]["file"])
        for anchor in response.get("anchors", [])
    ]
    reached_pages = set(anchor_files)
    for path in selected_paths:
        reached_pages.update(path)
    expected_pages = list(fixture.get("expected_pages") or [])
    endpoint_hits = [page for page in expected_pages if page in reached_pages]
    required_paths = list(fixture.get("bridge_paths_any") or [])
    selected_required = any(
        _path_present(candidate, selected_paths) for candidate in required_paths
    ) if required_paths else None
    forbidden_paths = list(fixture.get("forbidden_paths") or [])
    forbidden_selected = any(
        _path_present(candidate, selected_paths) for candidate in forbidden_paths
    )
    if fixture.get("shape") == "false_hub_shortcut" and len(expected_pages) >= 2:
        forbidden_selected = forbidden_selected or any(
            len(path) >= 2
            and {path[0], path[-1]} == {expected_pages[0], expected_pages[1]}
            for path in selected_paths
        )
    rejection_observed = any(
        _path_present(candidate, rejected_paths) for candidate in forbidden_paths
    )
    if fixture.get("shape") == "false_hub_shortcut" and len(expected_pages) >= 2:
        rejection_observed = rejection_observed or any(
            len(path) >= 2
            and {path[0], path[-1]} == {expected_pages[0], expected_pages[1]}
            for path in rejected_paths
        )
    correctly_rejected = sum(
        any(_path_present(candidate, [path]) for candidate in forbidden_paths)
        or (
            fixture.get("shape") == "false_hub_shortcut"
            and len(expected_pages) >= 2
            and len(path) >= 2
            and {path[0], path[-1]} == {expected_pages[0], expected_pages[1]}
        )
        for path in rejected_paths
    )
    rejected_path_precision = (
        correctly_rejected / len(rejected_paths)
        if forbidden_paths and rejected_paths
        else (0.0 if forbidden_paths else None)
    )
    evidence_complete = all(
        step.get("evidence_span", {}).get("content")
        for path in response.get("paths", [])
        for step in path.get("steps", [])
    )
    response_bytes = len(json.dumps(response, sort_keys=True, separators=(",", ":")).encode())
    positive_selected = sum(
        any(_path_present(candidate, [path]) for candidate in required_paths)
        for path in selected_paths
    )
    path_precision = (
        positive_selected / len(selected_paths)
        if selected_paths
        else (1.0 if not required_paths else 0.0)
    )
    return {
        "id": fixture["id"],
        "corpus": fixture["corpus"],
        "shape": fixture["shape"],
        "question": fixture["question"],
        "expected_pages": expected_pages,
        "selected_paths": selected_paths,
        "rejected_paths": rejected_paths,
        "rejection_reasons": [
            path.get("reason") for path in response.get("rejected_paths", [])
        ],
        "routing": response.get("routing"),
        "anchors": response.get("anchors", []),
        "paths": response.get("paths", []),
        "rejections": response.get("rejected_paths", []),
        "counts": response.get("counts", {}),
        "budget": response.get("budget", {}),
        "diagnostics": response.get("diagnostics", []),
        "latency_ms": round(latency_ms, 3),
        "score": {
            "endpoint_hits": endpoint_hits,
            "endpoint_recall": (
                round(len(endpoint_hits) / len(expected_pages), 3)
                if expected_pages else None
            ),
            "required_path_selected": selected_required,
            "forbidden_path_selected": forbidden_selected,
            "false_path_rejection_observed": rejection_observed,
            "selected_path_precision": round(path_precision, 3),
            "rejected_path_precision": (
                round(rejected_path_precision, 3)
                if rejected_path_precision is not None
                else None
            ),
            "serialized_rejections": len(rejected_paths),
            "hub_shortcut_rejections": sum(
                path.get("reason") == "HUB_SHORTCUT"
                for path in response.get("rejected_paths", [])
            ),
            "evidence_complete": evidence_complete,
            "response_bytes": response_bytes,
            "estimated_response_tokens": ceil(response_bytes / 4),
        },
    }


def summarize(fixtures: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    expected_slots = sum(len(fixture["expected_pages"]) for fixture in fixtures)
    endpoint_hits = sum(len(fixture["score"]["endpoint_hits"]) for fixture in fixtures)
    positive = [
        fixture for fixture in fixtures
        if fixture["score"]["required_path_selected"] is not None
    ]
    false_relations = [
        fixture for fixture in fixtures if fixture["shape"] == "false_hub_shortcut"
    ]
    serialized_rejections = sum(
        fixture["score"]["serialized_rejections"] for fixture in fixtures
    )
    hub_shortcut_rejections = sum(
        fixture["score"]["hub_shortcut_rejections"] for fixture in fixtures
    )
    return {
        "expected_endpoint_slots": expected_slots,
        "expected_endpoint_hits": endpoint_hits,
        "endpoint_recall": round(endpoint_hits / expected_slots, 3) if expected_slots else None,
        "positive_paths_selected": sum(
            fixture["score"]["required_path_selected"] is True for fixture in positive
        ),
        "positive_path_fixtures": len(positive),
        "forbidden_paths_selected": sum(
            fixture["score"]["forbidden_path_selected"] is True
            for fixture in false_relations
        ),
        "false_path_rejections_observed": sum(
            fixture["score"]["false_path_rejection_observed"] is True
            for fixture in false_relations
        ),
        "mean_selected_path_precision": _mean(
            fixture["score"]["selected_path_precision"] for fixture in fixtures
        ),
        "mean_rejected_path_precision": _mean(
            fixture["score"]["rejected_path_precision"]
            for fixture in fixtures
            if fixture["score"]["rejected_path_precision"] is not None
        ),
        "serialized_rejections": serialized_rejections,
        "hub_shortcut_rejections": hub_shortcut_rejections,
        "hub_shortcut_rejection_rate": round(
            hub_shortcut_rejections / serialized_rejections,
            3,
        ) if serialized_rejections else 0.0,
        "all_selected_evidence_complete": all(
            fixture["score"]["evidence_complete"] for fixture in fixtures
        ),
        "all_budgets_satisfied": all(
            fixture["budget"].get("evidence_bytes", 0)
            <= fixture["budget"].get("max_evidence_bytes", 0)
            and fixture["budget"].get("estimated_tokens", 0)
            <= fixture["budget"].get("max_estimated_tokens", 0)
            for fixture in fixtures
        ),
        "mean_response_bytes": _mean(
            fixture["score"]["response_bytes"] for fixture in fixtures
        ),
        "mean_estimated_response_tokens": _mean(
            fixture["score"]["estimated_response_tokens"] for fixture in fixtures
        ),
        "mean_latency_ms": _mean(fixture["latency_ms"] for fixture in fixtures),
    }


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
    return hashlib.sha256(payload.encode()).hexdigest()


def _canonical_roots(
    symbols: Sequence[Mapping[str, Any]],
) -> tuple[dict[str, str], dict[str, dict[str, int]]]:
    roots: dict[str, Mapping[str, Any]] = {}
    frontmatter_lines: dict[str, dict[str, int]] = {}
    for symbol in symbols:
        file_path = symbol.get("file_path")
        metadata = symbol.get("metadata")
        markdown = metadata.get("markdown") if isinstance(metadata, Mapping) else None
        if (
            not isinstance(file_path, str)
            or not isinstance(markdown, Mapping)
            or markdown.get("page_root") is not True
        ):
            continue
        current = roots.get(file_path)
        key = (
            int(symbol.get("line") or 0),
            int(symbol.get("byte_offset") or 0),
            str(symbol.get("id") or ""),
        )
        if current is None or key < (
            int(current.get("line") or 0),
            int(current.get("byte_offset") or 0),
            str(current.get("id") or ""),
        ):
            roots[file_path] = symbol
            lines = metadata.get("frontmatter_lines")
            frontmatter_lines[file_path] = {
                str(name): int(line)
                for name, line in lines.items()
                if isinstance(lines, Mapping)
                and isinstance(name, str)
                and isinstance(line, int)
            } if isinstance(lines, Mapping) else {}
    return (
        {file_path: str(symbol["id"]) for file_path, symbol in roots.items()},
        frontmatter_lines,
    )


def _edge_evidence(
    edge_type: str,
    source_file: str,
    target_file: str,
    pages: Mapping[str, Any],
    frontmatter_lines: Mapping[str, Mapping[str, int]],
    runtime: WikiRuntime,
) -> tuple[str, int]:
    if edge_type == "mentioned_in":
        line = frontmatter_lines.get(target_file, {}).get("mentioned_in")
        if line is None:
            raise RuntimeError(f"mentioned_in edge lacks source line: {target_file}")
        return target_file, line
    if edge_type != "body_link":
        raise RuntimeError(f"unsupported wiki benchmark edge type: {edge_type}")
    page = pages[source_file]
    for line_number, line in enumerate(str(page.text).splitlines(), start=1):
        for raw in runtime.body_link_re.findall(line):
            if runtime.resolve_link(raw, source_file, pages) == target_file:
                return source_file, line_number
    raise RuntimeError(f"body link edge lacks source line: {source_file} -> {target_file}")


def _write_contribution_shards(
    contribution_dir: Path,
    records: Sequence[Mapping[str, Any]],
    *,
    max_bytes: int = 240_000,
) -> None:
    chunks: list[list[Mapping[str, Any]]] = []
    current: list[Mapping[str, Any]] = []
    for record in records:
        candidate = [*current, record]
        payload = {
            "schema_version": 1,
            "namespace": "llm-wiki",
            "nodes": [],
            "edges": candidate,
        }
        encoded = (json.dumps(payload, sort_keys=True) + "\n").encode()
        if len(encoded) > max_bytes and current:
            chunks.append(current)
            current = [record]
            continue
        if len(encoded) > max_bytes:
            raise RuntimeError("one benchmark graph edge exceeds the shard limit")
        current = candidate
    if current:
        chunks.append(current)
    for index, chunk in enumerate(chunks):
        payload = {
            "schema_version": 1,
            "namespace": "llm-wiki",
            "nodes": [],
            "edges": chunk,
        }
        (contribution_dir / f"llm-wiki-{index:03d}.json").write_text(
            json.dumps(payload, sort_keys=True) + "\n",
            encoding="utf-8",
        )


def _path_files(path: Mapping[str, Any]) -> list[str]:
    return [str(node["attributes"]["file"]) for node in path.get("nodes", [])]


def _rejected_path_files(path: Mapping[str, Any]) -> list[str]:
    files = []
    for node_id in path.get("nodes", []):
        if not isinstance(node_id, str) or "::" not in node_id:
            continue
        files.append(node_id.split("::", 1)[0])
    return files


def _path_present(candidate: Sequence[str], paths: Sequence[Sequence[str]]) -> bool:
    return any(
        _contains_path(path, candidate) or _contains_path(path, tuple(reversed(candidate)))
        for path in paths
    )


def _contains_path(path: Sequence[str], candidate: Sequence[str]) -> bool:
    width = len(candidate)
    return width > 0 and any(
        list(path[index : index + width]) == list(candidate)
        for index in range(len(path) - width + 1)
    )


def _mean(values: Any) -> float | None:
    materialized = list(values)
    return round(sum(materialized) / len(materialized), 3) if materialized else None


@contextmanager
def _temporary_loci_store(path: Path) -> Iterator[None]:
    previous = os.environ.get("LOCI_BASE_DIR")
    os.environ["LOCI_BASE_DIR"] = str(path)
    try:
        yield
    finally:
        if previous is None:
            os.environ.pop("LOCI_BASE_DIR", None)
        else:
            os.environ["LOCI_BASE_DIR"] = previous


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--contract", type=Path, required=True)
    parser.add_argument("--llm-wiki-root", type=Path, required=True)
    parser.add_argument("--ai-graph-root", type=Path, required=True)
    parser.add_argument("--brain-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--max-anchors", type=int, default=10)
    parser.add_argument("--max-hops", type=int, default=3)
    parser.add_argument("--max-nodes", type=int, default=64)
    parser.add_argument("--max-paths", type=int, default=8)
    parser.add_argument("--max-evidence-bytes", type=int, default=32_768)
    parser.add_argument("--max-estimated-tokens", type=int, default=8_192)
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    result = run_benchmark(
        load_contract(args.contract),
        {
            "ai_graph_ideas": args.ai_graph_root,
            "brain": args.brain_root,
        },
        llm_wiki_root=args.llm_wiki_root,
        max_anchors=args.max_anchors,
        max_hops=args.max_hops,
        max_nodes=args.max_nodes,
        max_paths=args.max_paths,
        max_evidence_bytes=args.max_evidence_bytes,
        max_estimated_tokens=args.max_estimated_tokens,
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
