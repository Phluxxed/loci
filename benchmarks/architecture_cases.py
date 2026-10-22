"""Frozen corpus adapter for isolated architecture comparisons.

The candidate supplies an index and the packets actually delivered to the
consumer.  Authored corpus context, never candidate index output, defines the
requests and scoring target.  Source delivery is measured separately from task
answer correctness, which requires an independently observed answer.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

from benchmarks.typescript_context_corpus import (
    _snapshot_files, load_corpus, materialize_snapshot,
)
from benchmarks.typescript_context_explore_relationships import score_relationships as score_typescript
from benchmarks.typescript_context_relationships import _proven_edge
from benchmarks.multilingual_context_relationships import (
    score_relationships as score_multilingual, validate_relation_mappings,
)
from benchmarks.ordinary_adoption_normal import (
    _byte_accounting, _relationships, _sources, _node_ids, _unique_extent_bytes,
)
from benchmarks.typescript_context_trace import _covered


def load_suite(root: Path) -> dict[str, Any]:
    """Load one frozen TypeScript or multilingual corpus from its input root."""
    corpus = load_corpus(root)
    if corpus.get("version") == "multilingual-context-v1":
        validate_relation_mappings(corpus)
    elif corpus.get("version") not in {"typescript-context-v1", "typescript-context-v3"}:
        raise ValueError(f"unsupported architecture corpus: {corpus.get('version')!r}")
    return corpus


def prepare_snapshots(corpus: dict, destination: Path) -> dict[str, str]:
    """Export every immutable fixture as an ordinary, non-Git directory."""
    destination = Path(destination)
    if destination.is_symlink():
        raise ValueError("snapshot destination is a symlink")
    destination.mkdir(parents=True, exist_ok=True)
    paths: dict[str, str] = {}
    for snapshot_id in corpus["snapshots"]:
        repo = destination / snapshot_id
        materialize_snapshot(corpus, snapshot_id, repo)
        paths[snapshot_id] = str(repo.resolve())
    verify_snapshots(corpus, paths)
    return paths


def _verify_snapshot(corpus: dict, snapshot_id: str, repo: Path) -> None:
    expected = _snapshot_files(corpus, snapshot_id)
    repo = Path(repo)
    if not repo.is_dir() or repo.is_symlink():
        raise ValueError(f"missing or linked snapshot: {snapshot_id}")
    observed: dict[str, str] = {}
    for path in repo.rglob("*"):
        if path.is_symlink():
            raise ValueError(f"linked snapshot member: {snapshot_id}/{path.relative_to(repo)}")
        if path.is_file():
            observed[path.relative_to(repo).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
        elif not path.is_dir():
            raise ValueError(f"non-regular snapshot member: {snapshot_id}/{path.relative_to(repo)}")
    wanted = {name: hashlib.sha256(data).hexdigest() for name, data in expected.items()}
    if observed != wanted:
        raise ValueError(f"snapshot inventory or content differs: {snapshot_id}")


def verify_snapshots(corpus: dict, paths: dict[str, str | Path]) -> None:
    """Reject missing, changed, extra and linked files in each export."""
    if set(paths) != set(corpus["snapshots"]):
        raise ValueError("snapshot path IDs differ from frozen corpus")
    for snapshot_id, repo in paths.items():
        _verify_snapshot(corpus, snapshot_id, Path(repo))


def requests(corpus: dict) -> list[dict[str, Any]]:
    """Choose each entry from frozen authored context, independently of an index."""
    result = []
    for case in corpus["cases"]:
        anchor = next(item for item in case["context"] if item["id"] == case["anchor"])
        symbol = anchor.get("symbol")
        # The authored file gives an exact, reproducible entry point even when
        # a source-only anchor has no indexed symbol identity.
        result.append({
            "case_id": case["id"], "snapshot": case["snapshot"],
            "query": symbol["name"] if isinstance(symbol, dict) else anchor["file"],
            "anchor_context_id": anchor["id"],
            "anchor_name": symbol.get("name") if isinstance(symbol, dict) else None,
        })
    return result


def _payload(packet: dict) -> dict:
    for key in ("structuredContent", "structured_content"):
        if isinstance(packet.get(key), dict):
            return packet[key]
    return packet


def _byte_failures(packet: dict, payload: dict, packet_no: int) -> list[dict]:
    """Check reported bytes against the exact supplied MCP envelope."""
    if "usage" not in payload:
        return []
    if "structuredContent" not in packet:
        return [{"packet": packet_no, "reason": "output_envelope_unavailable"}]
    source = _sources(payload.get("source") if "source" in payload else payload.get("sources"),
                      singular="source" in payload)
    if source["status"] != "complete":
        return [{"packet": packet_no, "reason": "malformed_source_schema"}]
    accounting = _byte_accounting(packet, payload, source)
    return ([{"packet": packet_no, "reason": "byte_accounting_" + accounting["status"],
              "reported_output_bytes": accounting["reported_output_bytes"],
              "actual_output_bytes": accounting["actual_output_bytes"]}]
            if accounting["status"] != "complete" else [])


def _packet_sources(payload: dict) -> list[dict]:
    sources = payload.get("sources", [])
    if "source" in payload:
        sources = [payload["source"]]
    if not isinstance(sources, list):
        raise ValueError("malformed packet sources")
    if any(not isinstance(source, dict) for source in sources):
        raise ValueError("malformed packet source")
    return sources


def _validated_spans(corpus: dict, snapshot: str, payloads: list[dict]) -> tuple[list[dict], list[dict]]:
    files = _snapshot_files(corpus, snapshot)
    spans: list[dict] = []
    failures: list[dict] = []
    for packet_no, payload in enumerate(payloads):
        if payload.get("error") is not None:
            failures.append({"packet": packet_no, "reason": "tool_error", "detail": payload["error"]})
            continue
        try:
            sources = _packet_sources(payload)
        except ValueError as exc:
            failures.append({"packet": packet_no, "reason": str(exc)})
            continue
        for source_no, source in enumerate(sources):
            name, start, end, content = (
                source.get("file"), source.get("start_byte"), source.get("end_byte"), source.get("content"),
            )
            raw = files.get(name) if isinstance(name, str) else None
            if (raw is None or type(start) is not int or type(end) is not int
                    or not 0 <= start < end <= len(raw) or not isinstance(content, str)
                    or raw[start:end] != content.encode("utf-8")
                    or source.get("content_hash") != hashlib.sha256(raw).hexdigest()):
                failures.append({"packet": packet_no, "source": source_no, "reason": "source_bytes_or_hash_mismatch"})
                continue
            spans.append({"file": name, "start_byte": start, "end_byte": end, "content": content})
    return spans, failures


def _normal_claim_packet(
    payload: dict, valid_source_ids: set[int], index: dict,
) -> tuple[dict | None, list[dict]]:
    """Adapt proven normal retrieval edges to the existing scorer's envelope."""
    relations = payload.get("relationships")
    if not isinstance(relations, list):
        return None, []
    source_readout = _sources(payload.get("sources"), singular=False)
    proof = _relationships(relations, source_readout["by_id"], _node_ids(payload.get("nodes")))
    if proof["status"] != "complete":
        return None, [{"reason": "malformed_normal_relationship_proof"}]
    semantic = []
    failures = []
    indexed_edges = index.get("graph", {}).get("edges", [])
    for relation in relations:
        if not all(item in valid_source_ids for item in relation["source_ids"]):
            failures.append({"reason": "relationship_source_not_validated", "relationship": relation["id"]})
        elif relation["edge"] not in indexed_edges:
            failures.append({"reason": "relationship_edge_not_in_index", "relationship": relation["id"]})
        elif _proven_edge(relation["edge"]):
            # The independent semantic scorer deliberately excludes structural
            # imports/containment; their schema, source and index checks above
            # remain mandatory normal-packet integrity checks.
            semantic.append(relation)
    return {"intent": "type_dependencies", "sources": payload["sources"],
            "relationships": semantic}, failures


def score(corpus: dict, case_id: str, repo: Path, index: dict, packets: list[dict]) -> dict[str, Any]:
    """Score delivered evidence and retained failures against authored truth.

    Task-answer correctness is intentionally ``None``: packets and an index do
    not contain the consumer's final structured answer.  The caller must score
    that independently with ``check_answer`` if one was observed.
    """
    case = next((item for item in corpus["cases"] if item["id"] == case_id), None)
    if case is None:
        raise ValueError(f"unknown architecture case: {case_id}")
    _verify_snapshot(corpus, case["snapshot"], repo)
    if not isinstance(index, dict) or not isinstance(packets, list):
        raise ValueError("index and packets must be supplied")
    if any(not isinstance(packet, dict) for packet in packets):
        raise ValueError("packet must be an object")
    payloads = [_payload(packet) for packet in packets]
    if any(not isinstance(packet, dict) for packet in payloads):
        raise ValueError("packet must be an object")
    spans, failures = _validated_spans(corpus, case["snapshot"], payloads)
    for packet_no, (packet, payload) in enumerate(zip(packets, payloads)):
        failures.extend(_byte_failures(packet, payload, packet_no))
    scoring_packets = []
    for packet_no, payload in enumerate(payloads):
        if isinstance(payload.get("relationships"), list) and payload.get("intent") not in {
            "locate", "type_dependencies", "dependencies", "impact",
        }:
            sources = payload.get("sources") if isinstance(payload.get("sources"), list) else []
            valid_ids = {
                source["id"] for source in sources if isinstance(source, dict)
                if type(source.get("id")) is int and any(
                    span["file"] == source.get("file")
                    and span["start_byte"] == source.get("start_byte")
                    and span["end_byte"] == source.get("end_byte")
                    for span in spans
                )
            }
            adapted, problems = _normal_claim_packet(payload, valid_ids, index)
            failures.extend({"packet": packet_no, **problem} for problem in problems)
            if adapted is not None:
                scoring_packets.append(adapted)
                # Multilingual scorer validates normal claims with the full
                # delivered source set below.
        else:
            scoring_packets.append(payload)
    scored_index = {**index, "repo_path": str(Path(repo).resolve())}
    if corpus["version"] == "multilingual-context-v1":
        relationships = score_multilingual(case, scored_index, scoring_packets, spans)
    else:
        relationships = score_typescript(case, scored_index, scoring_packets)
    anchor = next(item for item in case["context"] if item["id"] == case["anchor"])
    covered = sorted(item["id"] for item in case["context"] if _covered(spans, item))
    selected_ids = {
        value["node_id"] for payload in payloads for value in payload.get("anchors", [])
        if isinstance(value, dict) and isinstance(value.get("node_id"), str)
    }
    expected = anchor.get("symbol")
    anchor_ids = {
        item["id"] for item in index.get("symbols", [])
        if isinstance(expected, dict) and item.get("file_path") == anchor["file"]
        and item.get("name") == expected.get("name") and item.get("kind") == expected.get("kind")
        and type(item.get("byte_offset")) is int and type(item.get("byte_length")) is int
        and anchor["start_byte"] <= item["byte_offset"]
        and item["byte_offset"] + item["byte_length"] <= anchor["end_byte"]
    }
    anchor_selected = bool(anchor_ids & selected_ids)
    if expected is None:
        anchor_selected = any(
            item.get("role") == "anchor"
            and isinstance(item.get("extent"), dict)
            and item["extent"].get("file") == anchor["file"]
            and type(item["extent"].get("start_byte")) is int
            and type(item["extent"].get("end_byte")) is int
            and item["extent"]["start_byte"] < anchor["end_byte"]
            and item["extent"]["end_byte"] > anchor["start_byte"]
            for payload in payloads for item in payload.get("items", [])
            if isinstance(item, dict)
        )
    total_source_bytes = sum(span["end_byte"] - span["start_byte"] for span in spans)
    frozen = _snapshot_files(corpus, case["snapshot"])
    file_hashes = {name: hashlib.sha256(data).hexdigest() for name, data in frozen.items()}
    unique_source_bytes = _unique_extent_bytes([
        {**span, "content_hash": file_hashes[span["file"]]} for span in spans
    ])
    return {
        "case_id": case_id, "snapshot": case["snapshot"],
        "anchor_selection": {"selected": anchor_selected, "expected_context_id": anchor["id"],
                             "candidate_symbol_ids": sorted(anchor_ids), "selected_node_ids": sorted(selected_ids)},
        "source_coverage": {"covered_context_ids": covered, "required": len(case["context"]),
                            "covered": len(covered), "ratio": len(covered) / len(case["context"])},
        "efficiency": {"packet_count": len(packets),
                       "source_bytes": total_source_bytes,
                       "unique_source_bytes": unique_source_bytes,
                       "repeated_source_bytes": total_source_bytes - unique_source_bytes,
                       "output_bytes": sum(len(json.dumps(packet, ensure_ascii=False, allow_nan=False,
                                                          separators=(",", ":")).encode("utf-8"))
                                           for packet in packets)},
        "relationships": relationships,
        "negative_cases": {"forbidden_proven_relationships": relationships["forbidden_proven_relationships"],
                           "forbidden_delivered_relationships": relationships.get("forbidden_delivered_relationships")},
        "output_integrity": {"valid_source_spans": len(spans), "failures": failures,
                             "passed": not failures and not relationships.get("delivery_integrity_violations")},
        "integrity_ok": not failures and not relationships.get("delivery_integrity_violations"),
        "preserved_guarantees": {
            "snapshot_verified": True,
            "task_answer_correct": None,
            "task_answer_status": "unobserved; source and proof delivery do not establish task correctness",
        },
    }


# R0.4 source acquisition is a separate dimension from semantic proof. These
# constants and rules are shared across all architectures and frozen pre-run.
ACQUISITION_LIMITS = {"retrieval_calls": 5, "continuation_calls": 16,
                      "source_bytes": 131072, "output_bytes": 262144}
_WORDS = re.compile(r"\b[A-Za-z_][A-Za-z_0-9]*\b")
_STOP = frozenset("""abstract any as async await bool boolean break case catch char
class const continue def default delete dict do else enum except export extends
false finally float fn for from func function if impl import in int interface
is let list match mod module mut new None null number object of package pass
private protected pub public raise return self set static str string struct
super switch this throw trait true try type typeof undefined use var void while
with yield None True False""".split())
_CONTROLS = frozenset({"go.mod", "go.work", "Cargo.toml", "jsconfig.json", "tsconfig.json", "package.json"})


def next_acquisition_query(inventory: dict, packets: list[dict], asked: list[str]) -> str | None:
    """Gold-blind scheduler: only names/hashes and already delivered source.

    Expand a delivered file, then find paths named in source and ancestor
    manifests, then observed identifiers. This is lexical discovery, not name
    binding, semantic parsing or a surrogate relationship graph.
    """
    spans = [source for packet in packets for source in _packet_sources(_payload(packet))]
    files = inventory["files"]
    observed = list(dict.fromkeys(s["file"] for s in spans))
    for name in observed:
        size = files.get(name, {}).get("size")
        if name not in asked and type(size) is int and size and not _covered(spans, {
                "file": name, "start_byte": 0, "end_byte": size}):
            return name
    for source in spans:
        text = source["content"]
        words = set(_WORDS.findall(text))
        for name in sorted(files):
            path = Path(name)
            mentioned = (name in text or path.name in text or
                         (len(path.stem) > 2 and path.stem in words))
            ancestor = path.name in _CONTROLS and path.parent in Path(source["file"]).parents
            if name not in asked and name not in observed and (mentioned or ancestor):
                return name
    for source in spans:
        for word in _WORDS.findall(source["content"]):
            if len(word) >= 3 and word not in _STOP and word not in asked:
                return word
    return None


def validate_inventory(corpus: dict, snapshot: str, inventory: dict) -> None:
    frozen = _snapshot_files(corpus, snapshot)
    if set(inventory) != {"schema_version", "files"} or inventory["schema_version"] != 1:
        raise ValueError("unknown acquisition inventory schema")
    if not isinstance(inventory["files"], dict):
        raise ValueError("malformed acquisition inventory")
    for name, metadata in inventory["files"].items():
        raw = frozen.get(name)
        if (raw is None or not isinstance(metadata, dict) or set(metadata) != {"sha256", "size"}
                or metadata != {"sha256": hashlib.sha256(raw).hexdigest(), "size": len(raw)}):
            raise ValueError("acquisition inventory differs from frozen source")


def validate_graph_free_packet(payload: dict) -> None:
    """Independent schema check; unknown formats cannot pass as empty graphs."""
    from loci.mcp_output_models import NormalSource, LociReadOutput
    if "source" in payload:
        LociReadOutput.model_validate(payload)
        return
    if (payload.get("schema_version") != 1 or payload.get("policy") != "graph-free-file-v1"
            or payload.get("status") not in {"ok", "partial", "empty"}
            or not isinstance(payload.get("items"), list)
            or not isinstance(payload.get("sources"), list)
            or not isinstance(payload.get("omissions"), list)
            or payload.get("relationships") != [] or payload.get("nodes") != []
            or payload.get("anchors") != [] or not isinstance(payload.get("usage"), dict)):
        raise ValueError("malformed graph-free acquisition schema or semantic claim")
    by_id = {}
    for source in payload["sources"]:
        NormalSource.model_validate(source)
        if source["id"] in by_id:
            raise ValueError("duplicate graph-free source ID")
        by_id[source["id"]] = source
    for item in payload["items"]:
        extent = item.get("extent", {})
        ids = item.get("source_ids")
        if (type(item.get("complete")) is not bool or not isinstance(item.get("source_ref"), str)
                or not isinstance(ids, list) or not ids or any(i not in by_id for i in ids)
                or not isinstance(extent.get("file"), str)
                or type(extent.get("start_byte")) is not int
                or type(extent.get("end_byte")) is not int
                or not 0 <= extent["start_byte"] <= extent["end_byte"]):
            raise ValueError("malformed graph-free acquisition item")


def score_acquisition(corpus: dict, case_id: str, repo: Path, index: dict,
                      packets: list[dict], acquisition: dict, inventory: dict) -> dict:
    """Replay queries and both checkpoints; preserve frozen semantic scoring."""
    case = next(c for c in corpus["cases"] if c["id"] == case_id)
    initial = next(r for r in requests(corpus) if r["case_id"] == case_id)["query"]
    validate_inventory(corpus, case["snapshot"], inventory)
    queries = acquisition["queries"]
    if not queries or len(queries) > ACQUISITION_LIMITS["retrieval_calls"]:
        raise ValueError("acquisition query inventory violates call limit")
    cursor = 0
    asked = []
    for n, row in enumerate(queries):
        expected = initial if n == 0 else next_acquisition_query(inventory, packets[:cursor], asked)
        if row["query"] != expected or row["packet_start"] != cursor or not cursor < row["packet_end"] <= len(packets):
            raise ValueError("acquisition query is not the frozen gold-blind policy")
        cursor = row["packet_end"]
        asked.append(expected)
    if cursor != len(packets) or len(packets) - len(queries) > ACQUISITION_LIMITS["continuation_calls"]:
        raise ValueError("acquisition packets differ from call inventory")
    result = score(corpus, case_id, repo, index, packets)
    first = score(corpus, case_id, repo, index, packets[:queries[0]["packet_end"]])
    result.update(score_session_proof(corpus, case_id, repo, index, packets))
    covered = set(result["source_coverage"]["covered_context_ids"])
    result["acquisition"] = {**acquisition, "limits": ACQUISITION_LIMITS,
        "initial_source_coverage": first["source_coverage"],
        "initial_semantic_integrity_ok": first["integrity_ok"],
        "anchor_source_acquired": case["anchor"] in covered,
        "relationship_endpoint_contexts_acquired": sum(
            r.get("from") in covered and r.get("to") in covered for r in case.get("relationships", [])),
        "qualification": "endpoint source availability is not semantic proof or task correctness"}
    result["acquisition"]["session_proof_qualification"] = (
        "unchanged strict scorer over same-case acquired source union; packet proof score remains unchanged")
    snapshot_bytes = sum(len(raw) for raw in _snapshot_files(corpus, case["snapshot"]).values())
    result["efficiency"]["snapshot_source_bytes"] = snapshot_bytes
    result["efficiency"]["snapshot_fraction_delivered"] = result["efficiency"]["unique_source_bytes"] / snapshot_bytes
    discovery_bytes = len(json.dumps(inventory, ensure_ascii=False, separators=(",", ":")).encode())
    result["efficiency"]["discovery_output_bytes"] = discovery_bytes
    result["efficiency"]["total_delivered_bytes"] = result["efficiency"]["output_bytes"] + discovery_bytes
    return result

def score_session_proof(corpus: dict, case_id: str, repo: Path, index: dict, packets: list[dict]) -> dict:
    """Require unchanged strict support, using only actual same-case delivery."""
    case = next(c for c in corpus["cases"] if c["id"] == case_id)
    result = score(corpus, case_id, repo, index, packets)
    # A distinct session metric, never a rewrite of the frozen packet score.
    # Retain exact delivered sources and provenance; only their IDs are remapped.
    global_sources, provenance, claims = [], [], []
    for packet_no, packet in enumerate(packets):
        payload = _payload(packet)
        for source in _packet_sources(payload):
            source_id = len(global_sources) + 1
            global_sources.append({**source, "id": source_id})
            provenance.append({"session_id": source_id, "packet": packet_no, "source_id": source["id"]})
    if not result["output_integrity"]["failures"]:
        for packet in packets:
            payload = _payload(packet)
            if isinstance(payload.get("relationships"), list):
                valid_ids = {s["id"] for s in payload.get("sources", [])}
                adapted, problems = _normal_claim_packet(payload, valid_ids, index)
                if problems:
                    raise ValueError("session adaptation cannot repair malformed original proof")
                if adapted is not None:
                    claims.append({**adapted, "sources": global_sources, "relationships": [
                        {**r, "source_ids": [s["id"] for s in global_sources]}
                        for r in adapted["relationships"]]})
    scored_index = {**index, "repo_path": str(repo.resolve())}
    proof_sources = global_sources if not result["output_integrity"]["failures"] else []
    session = (score_multilingual(case, scored_index, claims, proof_sources)
               if corpus["version"] == "multilingual-context-v1"
               else score_typescript(case, scored_index, claims))
    return {"session_relationships": session, "session_source_provenance": provenance,
            "acquisition_integrity_ok": (not result["output_integrity"]["failures"]
                                          and not session.get("delivery_integrity_violations"))}

