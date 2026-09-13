#!/usr/bin/env python3
"""Reproduce W5.2 JavaScript/Python compact-selection cases without a provider."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from benchmarks.typescript_context_corpus import (
    _isolated_store,
    load_corpus,
    materialize_snapshot,
)
from loci import service
from loci.storage.index_store import EXTRACTOR_VERSION, INDEX_SCHEMA_VERSION


RESULTS = ROOT / "benchmarks/results/multilingual-context-workflow-v1"
CORPUS_ROOT = ROOT / "benchmarks/comparisons/multilingual-context-workflow-v1/inputs"
FREEZE = ROOT / "benchmarks/comparisons/multilingual-context-workflow-v1/freeze.json"

CASES = {
    "javascript_value_dependencies": {
        "expected_edges": [
            ("app.js::run#function", "calls", "helper.js::add#function"),
            ("app.js::run#function", "calls", "helper.js::make#function"),
            ("helper.js::make#function", "calls", "helper.js::add#function"),
        ],
        "focused": [
            {
                "name": "make_to_add",
                "request": {
                    "intent": "dependencies",
                    "seed_ids": ["helper.js::make#function"],
                    "query": "Direct helper call made by make.",
                    "max_hops": 1,
                    "max_output_bytes": 16384,
                    "max_evidence_bytes": 8192,
                },
                "recover": [("helper.js::make#function", "calls", "helper.js::add#function")],
            }
        ],
        "classification": "documented_expected_bounded_omission",
    },
    "python_alias_annotation": {
        "expected_edges": [
            ("consumer.py::decode#function", "uses_type", "consumer.py::Alias#type"),
            ("consumer.py::Alias#type", "uses_type", "schema.py::Payload#class"),
            ("consumer.py::decode#function", "uses_type", "schema.py::Payload#class"),
        ],
        "focused": [
            {
                "name": "alias_to_payload",
                "request": {
                    "intent": "type_dependencies",
                    "seed_ids": ["consumer.py::Alias#type"],
                    "query": "Trace the authored Alias target to Payload.",
                    "max_hops": 1,
                    "max_output_bytes": 16384,
                    "max_evidence_bytes": 8192,
                },
                "recover": [("consumer.py::Alias#type", "uses_type", "schema.py::Payload#class")],
            }
        ],
        "classification": "documented_expected_bounded_omission_and_task_agent_request_choice",
    },
    "python_loci_bundle_contract": {
        "expected_edges": [
            ("src/loci/_exploration_output.py::_validate_bundle#function", "uses_type", "src/loci/_exploration_output.py::Bundle#class"),
            ("src/loci/_exploration_output.py::Bundle#class", "uses_type", "src/loci/_exploration_output.py::Span#class"),
            ("src/loci/_exploration_output.py::Bundle#class", "uses_type", "src/loci/_exploration_output.py::Relation#class"),
            ("src/loci/_exploration_output.py::Relation#class", "uses_type", "src/loci/_exploration_output.py::Span#class"),
        ],
        "focused": [],
        "classification": "documented_expected_bounded_omission_and_task_agent_request_choice",
    },
}


def canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def digest(value: Any) -> str:
    return hashlib.sha256(canonical(value)).hexdigest()


def file_digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def edge_key(edge: dict[str, Any]) -> tuple[str, str, str]:
    return edge["from"], edge["type"], edge["to"]


def packet_edges(packet: dict[str, Any]) -> list[dict[str, Any]]:
    return [relation["edge"] for relation in packet.get("relationships", [])]


def normalized_packet(packet: dict[str, Any]) -> dict[str, Any]:
    result = dict(packet)
    result.pop("_evaluation", None)
    return result


def validate_sources(repo: Path, packet: dict[str, Any]) -> tuple[list[dict[str, Any]], bool]:
    checks = []
    for source in packet.get("sources", []):
        raw = (repo / source["file"]).read_bytes()
        content = source["content"].encode()
        start, end = source["start_byte"], source["end_byte"]
        actual_start_line = raw[:start].count(b"\n") + 1
        actual_end_line = actual_start_line + content.count(b"\n") - int(content.endswith(b"\n"))
        check = {
            "id": source["id"],
            "file": source["file"],
            "start_byte": start,
            "end_byte": end,
            "start_line": source["start_line"],
            "end_line": source["end_line"],
            "file_sha256": hashlib.sha256(raw).hexdigest(),
            "declared_content_hash": source["content_hash"],
            "span_sha256": hashlib.sha256(content).hexdigest(),
            "bytes_match": raw[start:end] == content,
            "file_hash_match": hashlib.sha256(raw).hexdigest() == source["content_hash"],
            "line_span_match": actual_start_line == source["start_line"] and actual_end_line == source["end_line"],
        }
        checks.append(check)
    return checks, all(c["bytes_match"] and c["file_hash_match"] and c["line_span_match"] for c in checks)


def evidence_bytes(packet: dict[str, Any]) -> int:
    intervals: dict[tuple[str, str], list[tuple[int, int]]] = {}
    for source in packet.get("sources", []):
        intervals.setdefault((source["file"], source["content_hash"]), []).append((source["start_byte"], source["end_byte"]))
    total = 0
    for ranges in intervals.values():
        start = end = -1
        for current_start, current_end in sorted(ranges):
            if start < 0:
                start, end = current_start, current_end
            elif current_start <= end:
                end = max(end, current_end)
            else:
                total += end - start
                start, end = current_start, current_end
        if start >= 0:
            total += end - start
    return total


def envelope_bytes(packet: dict[str, Any]) -> int:
    return len(json.dumps({"content": [], "structuredContent": packet, "isError": False}, ensure_ascii=False, separators=(",", ":")).encode())


def validate_packet(repo: Path, packet: dict[str, Any], state_edges: dict[tuple[str, str, str], list[dict[str, Any]]]) -> dict[str, Any]:
    packet = normalized_packet(packet)
    sources = {source["id"]: source for source in packet.get("sources", [])}
    source_checks, source_valid = validate_sources(repo, packet)
    relationships = {relation["id"]: relation for relation in packet.get("relationships", [])}
    relation_checks = []
    for relation in relationships.values():
        edge = relation["edge"]
        expected = state_edges.get(edge_key(edge), [])
        evidence_raw = (repo / edge["evidence"]["file"]).read_bytes()
        relation_checks.append({
            "id": relation["id"],
            "edge_key": list(edge_key(edge)),
            "edge_sha256": digest(edge),
            "state_edge_exact": edge in expected,
            "evidence_hash_match": hashlib.sha256(evidence_raw).hexdigest() == edge["evidence"]["content_hash"],
            "source_ids_closed": all(source_id in sources for source_id in relation["source_ids"]),
            "traversed": relation["traversed"],
        })
    anchors = {item["id"] for item in packet.get("items", []) if item["role"] == "anchor"}
    path_checks = []
    for item in packet.get("items", []):
        path = item.get("path", [])
        if not path:
            valid = item["id"] in anchors
        else:
            current = None
            valid = True
            for relation_id in path:
                relation = relationships.get(relation_id)
                if relation is None:
                    valid = False
                    break
                edge = relation["edge"]
                source = edge["from"] if relation["traversed"] == "forward" else edge["to"]
                target = edge["to"] if relation["traversed"] == "forward" else edge["from"]
                if current is None:
                    valid = source in anchors
                elif current != source:
                    valid = False
                current = target
            valid = valid and current == item["id"]
        path_checks.append({"item": item["id"], "path": path, "valid": valid})
    recomputed_evidence_bytes = evidence_bytes(packet)
    recomputed_output_bytes = envelope_bytes(packet)
    accounting = {
        "recomputed_evidence_bytes": recomputed_evidence_bytes,
        "declared_evidence_bytes": packet["usage"]["evidence_bytes"],
        "evidence_bytes_exact": recomputed_evidence_bytes == packet["usage"]["evidence_bytes"],
        "evidence_within_limit": recomputed_evidence_bytes <= packet["limits"]["max_evidence_bytes"],
        "recomputed_output_bytes": recomputed_output_bytes,
        "declared_output_bytes": packet["usage"]["output_bytes"],
        "output_bytes_exact": recomputed_output_bytes == packet["usage"]["output_bytes"],
        "output_within_limit": recomputed_output_bytes <= packet["limits"]["max_output_bytes"],
    }
    accounting_valid = all(accounting[key] for key in (
        "evidence_bytes_exact", "evidence_within_limit", "output_bytes_exact", "output_within_limit"
    ))
    valid = source_valid and accounting_valid and all(
        row["state_edge_exact"] and row["evidence_hash_match"] and row["source_ids_closed"]
        for row in relation_checks
    ) and all(row["valid"] for row in path_checks)
    source_identity = [{k: row[k] for k in ("id", "file", "start_byte", "end_byte", "start_line", "end_line", "file_sha256", "span_sha256")} for row in source_checks]
    graph_identity = [{"edge": relation["edge"], "traversed": relation["traversed"], "source_ids": relation["source_ids"]} for relation in packet.get("relationships", [])]
    return {
        "valid": valid,
        "source_proof_sha256": digest(source_identity),
        "graph_proof_sha256": digest(graph_identity),
        "source_checks": source_checks,
        "relationship_checks": relation_checks,
        "path_checks": path_checks,
        "accounting": accounting,
    }


def retained_requests(case_id: str) -> list[dict[str, Any]]:
    rows = []
    for attempt_dir in sorted(RESULTS.glob(f"{case_id}-r*-B")):
        events = json.loads((attempt_dir / "events.json").read_text())
        result = json.loads((attempt_dir / "result.json").read_text())
        required = result["baseline"]["relationships"]["required_semantic_dependencies"]
        for event in events:
            item = event.get("item", {})
            if event.get("type") != "item.completed" or item.get("type") != "mcp_tool_call" or item.get("tool") != "loci_explore":
                continue
            packet = item["result"]["structured_content"]
            rows.append({
                "attempt": attempt_dir.name,
                "item_id": item["id"],
                "request": item["arguments"],
                "request_sha256": digest(item["arguments"]),
                "historical_packet": packet,
                "historical_raw_response_sha256": digest(packet),
                "historical_normalized_response_sha256": digest(normalized_packet(packet)),
                "historical_available": [
                    {
                        "from": row["from"], "kind": row["kind"], "to": row["to"],
                        "available": row["available"], "delivered": row["delivered"],
                        "available_edge_sha256": [digest(edge) for edge in row["available_edges"]],
                        "delivered_edge_sha256": [digest(edge) for edge in row["delivered_edges"]],
                        "available_edges": row["available_edges"],
                    }
                    for row in required
                ],
            })
    return rows


def compact_packet(packet: dict[str, Any], validation: dict[str, Any], *, detailed: bool = True) -> dict[str, Any]:
    result = {
        "status": packet["status"],
        "selection": packet["selection"],
        "items": [{k: item[k] for k in ("id", "role", "depth", "path")} for item in packet["items"]],
        "edges": packet_edges(packet),
        "omissions": packet["omissions"],
        "limits": packet["limits"],
        "usage": packet["usage"],
        "normalized_response_sha256": digest(normalized_packet(packet)),
        "graph_proof_sha256": validation["graph_proof_sha256"],
        "source_proof_sha256": validation["source_proof_sha256"],
        "accounting": validation["accounting"],
        "valid": validation["valid"],
    }
    if detailed:
        result.update({
            "source_checks": validation["source_checks"],
            "relationship_checks": validation["relationship_checks"],
            "path_checks": validation["path_checks"],
        })
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    corpus = load_corpus(CORPUS_ROOT)
    cases_by_id = {case["id"]: case for case in corpus["cases"]}
    freeze = json.loads(FREEZE.read_text())
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    tree = subprocess.check_output(["git", "rev-parse", "HEAD^{tree}"], cwd=ROOT, text=True).strip()
    output: dict[str, Any] = {
        "schema_version": 1,
        "production": {"head": head, "tree": tree, "assessment_base_commit": "a58e2e4053b2630069c2b9da9667c2c61ab9de5b"},
        "frozen_engine": {
            "commit": freeze["engine"]["commit"],
            "source_tree": freeze["engine"]["source_tree"],
            "extractor_version": freeze["engine"]["extractor_version"],
            "graph_state_version": freeze["engine"]["graph_state_version"],
        },
        "current_engine": {"index_schema_version": INDEX_SCHEMA_VERSION, "extractor_version": EXTRACTOR_VERSION},
        "frozen_inputs": {
            "corpus_json_sha256": file_digest(CORPUS_ROOT / "corpus.json"),
            "corpus_declared_sha256": (CORPUS_ROOT / "corpus.sha256").read_text().strip(),
            "fixtures_tar_sha256": file_digest(CORPUS_ROOT / "fixtures.tar.gz"),
        },
        "cases": {},
    }
    assertions = []
    frozen_file_hashes = freeze["files"]
    assertions.extend([
        {"check": "frozen_corpus_json_identity", "passed": output["frozen_inputs"]["corpus_json_sha256"] == frozen_file_hashes["benchmarks/comparisons/multilingual-context-workflow-v1/inputs/corpus.json"]},
        {"check": "frozen_corpus_declared_identity", "passed": output["frozen_inputs"]["corpus_declared_sha256"] == output["frozen_inputs"]["corpus_json_sha256"]},
        {"check": "frozen_fixtures_tar_identity", "passed": output["frozen_inputs"]["fixtures_tar_sha256"] == frozen_file_hashes["benchmarks/comparisons/multilingual-context-workflow-v1/inputs/fixtures.tar.gz"]},
    ])
    with tempfile.TemporaryDirectory(prefix="loci-w52-js-python-") as temporary:
        temp = Path(temporary)
        for case_id, specification in CASES.items():
            case = cases_by_id[case_id]
            repo = temp / case_id / "repo"
            store_path = temp / case_id / "store"
            materialize_snapshot(corpus, case["snapshot"], repo)
            with _isolated_store(store_path):
                index_result = service.index_repo(repo, incremental=False)
                store, _nodes, state = service._load_graph_context(repo, ensure_fresh=False)
                index = store.load(repo)
                assert index is not None
                all_edges = sorted((edge.to_dict() for edge in state.edges), key=lambda edge: (edge["from"], edge["type"], edge["to"], edge["evidence"]["file"], edge["evidence"]["line"]))
                state_edges: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
                for edge in all_edges:
                    state_edges.setdefault(edge_key(edge), []).append(edge)
                expected_edges = {tuple(row) for row in specification["expected_edges"]}
                available = [edge for key in sorted(expected_edges) for edge in state_edges.get(key, [])]
                snapshot_files = {str(path.relative_to(repo)): file_digest(path) for path in sorted(repo.rglob("*")) if path.is_file()}
                case_out: dict[str, Any] = {
                    "snapshot": case["snapshot"],
                    "snapshot_files": snapshot_files,
                    "snapshot_files_sha256": digest(snapshot_files),
                    "index_identity": {
                        "index_schema_version": index.get("schema_version"),
                        "extractor_version": index.get("extractor_version"),
                        "graph_state_version": index.get("graph", {}).get("schema_version"),
                        "all_edges": len(all_edges),
                        "all_edges_sha256": digest(all_edges),
                        "index_counts": {key: value for key, value in index_result.items() if key.startswith("graph_") and key not in {"graph_diagnostics"}},
                    },
                    "available_proof": [{"edge": edge, "edge_sha256": digest(edge)} for edge in available],
                    "available_proof_sha256": digest(available),
                    "retained": [],
                    "focused": [],
                    "classification": specification["classification"],
                    "proposed_engine_fix": None,
                }
                assertions.append({"case": case_id, "check": "expected_edges_in_fixed_state", "passed": all(state_edges.get(key) for key in expected_edges)})
                for retained in retained_requests(case_id):
                    historical = retained.pop("historical_packet")
                    historical_validation = validate_packet(repo, historical, state_edges)
                    reproduced = service.explore(repo, **retained["request"])
                    reproduced_validation = validate_packet(repo, reproduced, state_edges)
                    same = digest(normalized_packet(historical)) == digest(normalized_packet(reproduced))
                    available_exact = all(
                        edge in state_edges.get(edge_key(edge), [])
                        for row in retained["historical_available"]
                        for edge in row["available_edges"]
                    )
                    for row in retained["historical_available"]:
                        row.pop("available_edges")
                    assertions.extend([
                        {"case": case_id, "attempt": retained["attempt"], "item": retained["item_id"], "check": "historical_proof_valid", "passed": historical_validation["valid"]},
                        {"case": case_id, "attempt": retained["attempt"], "item": retained["item_id"], "check": "reproduced_proof_valid", "passed": reproduced_validation["valid"]},
                        {"case": case_id, "attempt": retained["attempt"], "item": retained["item_id"], "check": "normalized_response_exact", "passed": same},
                        {"case": case_id, "attempt": retained["attempt"], "item": retained["item_id"], "check": "historical_available_edges_exact_in_state", "passed": available_exact},
                    ])
                    case_out["retained"].append({
                        **retained,
                        "historical": compact_packet(historical, historical_validation),
                        "reproduction": compact_packet(reproduced, reproduced_validation, detailed=False),
                        "normalized_response_exact": same,
                    })
                focused = list(specification["focused"])
                if case_id == "python_loci_bundle_contract":
                    focused = [
                        {
                            "name": "entry_bundle_fields",
                            "request": {
                                "intent": "type_dependencies",
                                "seed_ids": ["src/loci/_exploration_output.py::_validate_bundle#function"],
                                "query": case["prompt"],
                                "max_hops": 2,
                                "max_output_bytes": 16384,
                                "max_evidence_bytes": 8192,
                            },
                            "recover": [
                                ("src/loci/_exploration_output.py::_validate_bundle#function", "uses_type", "src/loci/_exploration_output.py::Bundle#class"),
                                ("src/loci/_exploration_output.py::Bundle#class", "uses_type", "src/loci/_exploration_output.py::Span#class"),
                                ("src/loci/_exploration_output.py::Bundle#class", "uses_type", "src/loci/_exploration_output.py::Relation#class"),
                            ],
                        },
                        {
                            "name": "relation_to_span",
                            "request": {
                                "intent": "type_dependencies",
                                "seed_ids": ["src/loci/_exploration_output.py::Relation#class"],
                                "query": "Trace Relation field annotations to Span.",
                                "max_hops": 1,
                                "max_output_bytes": 16384,
                                "max_evidence_bytes": 8192,
                            },
                            "recover": [("src/loci/_exploration_output.py::Relation#class", "uses_type", "src/loci/_exploration_output.py::Span#class")],
                        },
                    ]
                for followup in focused:
                    packet = service.explore(repo, **followup["request"])
                    validation = validate_packet(repo, packet, state_edges)
                    delivered = {edge_key(edge) for edge in packet_edges(packet)}
                    recovered = set(followup["recover"]) <= delivered
                    assertions.extend([
                        {"case": case_id, "focused": followup["name"], "check": "proof_valid", "passed": validation["valid"]},
                        {"case": case_id, "focused": followup["name"], "check": "required_edges_recovered", "passed": recovered},
                    ])
                    case_out["focused"].append({
                        "name": followup["name"],
                        "request": followup["request"],
                        "request_sha256": digest(followup["request"]),
                        "required_recovery": [list(row) for row in followup["recover"]],
                        "required_edges_recovered": recovered,
                        "response": compact_packet(packet, validation),
                    })
                output["cases"][case_id] = case_out
    output["assertions"] = assertions
    output["summary"] = {
        "checks": len(assertions),
        "passed": sum(row["passed"] for row in assertions),
        "failed": [row for row in assertions if not row["passed"]],
        "engine_defect_demonstrated": False,
        "production_change_recommended": False,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(canonical(output) + b"\n")
    print(json.dumps(output["summary"], sort_keys=True))
    return 0 if not output["summary"]["failed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
