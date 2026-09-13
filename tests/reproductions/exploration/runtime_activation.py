"""Disposable host-MCP acceptance fixture for the W5.5 runtime activation."""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).parents[3]
for import_root in (PROJECT_ROOT, PROJECT_ROOT / "src"):
    if str(import_root) not in sys.path:
        sys.path.insert(0, str(import_root))

from benchmarks.typescript_context_corpus import load_corpus, materialize_snapshot


ROOT = Path("/tmp/loci-w55-runtime-root")
PYTHON_ROOT = Path("/tmp/loci-w55-python-root")
PLAN = Path("/tmp/loci-w55-host-requests.json")
FRESH_PLAN = Path("/tmp/loci-w55-fresh-requests.json")
EVIDENCE = Path("/tmp/loci-w55-evidence")
CORPUS_ROOT = PROJECT_ROOT / "benchmarks/corpora/multilingual-context-v1"


def _request(name: str, tool: str, arguments: dict[str, Any], *, expected: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": name,
        "tool": tool,
        "arguments": arguments,
        "evidence_file": str(EVIDENCE / f"{name}.json"),
        "expected": expected,
    }


def _plan() -> dict[str, Any]:
    repo = str(ROOT)
    bounded = {"max_hops": 3, "max_evidence_bytes": 8192, "max_output_bytes": 16384}
    return {
        "schema_version": 1,
        "repo": repo,
        "instructions": "Call each public host tool exactly once and save its complete raw CallToolResult JSON to evidence_file.",
        "requests": [
            _request("python_types", "loci_explore", {"repo": repo, "intent": "type_dependencies", "seed_ids": ["python/consumer.py::decode#function"], **bounded}, expected={"ids": ["python/consumer.py::decode#function", "python/consumer.py::Alias#type"], "absent_ids": ["python/schema.py::Payload#class"], "edges": [["python/consumer.py::decode#function", "uses_type", "python/consumer.py::Alias#type"]], "relationships": "authored_types", "uncertainty": "Combined-root relocation makes absolute Python imports unresolved; retained fixture-layout control."}),
            _request("python_alias_payload", "loci_explore", {"repo": repo, "intent": "type_dependencies", "seed_ids": ["python/consumer.py::Alias#type"], "query": "Trace the authored Alias target to Payload.", "max_hops": 1, "max_evidence_bytes": 8192, "max_output_bytes": 16384}, expected={"ids": ["python/consumer.py::Alias#type"], "absent_ids": ["python/schema.py::Payload#class"], "relationships": "authored_types", "uncertainty": "Retained confirmation that query focus cannot compensate for the combined-root import layout."}),
            _request("python_supported_root", "loci_explore", {"repo": str(ROOT / "python"), "intent": "type_dependencies", "seed_ids": ["consumer.py::Alias#type"], "query": "Trace the authored Alias target to Payload.", "max_hops": 1, "max_evidence_bytes": 8192, "max_output_bytes": 16384}, expected={"error_code": "REPOSITORY_ROOT_OVERLAP", "uncertainty": "The host correctly refuses a nested root while its parent is indexed."}),
            _request("python_root_contract", "loci_explore", {"repo": str(PYTHON_ROOT), "intent": "type_dependencies", "seed_ids": ["consumer.py::Alias#type"], "query": "Trace the authored Alias target to Payload.", "max_hops": 1, "max_evidence_bytes": 8192, "max_output_bytes": 16384}, expected={"ids": ["consumer.py::Alias#type", "schema.py::Payload#class"], "edges": [["consumer.py::Alias#type", "uses_type", "schema.py::Payload#class"]], "relationships": "authored_types"}),
            _request("javascript_dependencies", "loci_explore", {"repo": repo, "intent": "dependencies", "seed_ids": ["javascript/app.js::run#function"], **bounded}, expected={"ids": ["javascript/app.js::run#function", "javascript/helper.js::make#function", "javascript/helper.js::add#function"], "edges": [["javascript/app.js::run#function", "calls", "javascript/helper.js::make#function"], ["javascript/app.js::run#function", "calls", "javascript/helper.js::add#function"]], "relationships": "authored_dependencies"}),
            _request("go_type_dependencies", "loci_explore", {"repo": repo, "intent": "type_dependencies", "seed_ids": ["go/app/main.go::Build#function"], **bounded}, expected={"ids": ["go/app/main.go::Build#function", "go/model/model.go::AliasID#type", "go/model/model.go::UserID#type", "go/model/model.go::Page#type", "go/model/model.go::Number#type"], "relationships": "authored_types", "source_files": ["go/go.mod"]}),
            _request("rust_type_dependencies", "loci_explore", {"repo": repo, "intent": "type_dependencies", "seed_ids": ["rust/src/lib.rs::build#function"], **bounded}, expected={"ids": ["rust/src/lib.rs::build#function", "rust/src/lib.rs::UserId#type", "rust/src/lib.rs::Format#trait", "rust/src/lib.rs::Render#trait", "rust/src/lib.rs::Envelope#struct"], "relationships": "authored_types", "source_files": ["rust/Cargo.toml"], "resolution_configuration": "unconditional"}),
            _request("tsx_type_dependencies", "loci_explore", {"repo": repo, "intent": "type_dependencies", "seed_ids": ["tsx/badge.tsx::Badge#function"], **bounded}, expected={"ids": ["tsx/badge.tsx::Badge#function", "tsx/props.ts::Props#interface"], "relationships": "authored_types"}),
            _request("go_module_control", "loci_file", {"repo": repo, "file_path": "go/go.mod"}, expected={"content_contains": "module ", "file": "go/go.mod"}),
            _request("cargo_control", "loci_file", {"repo": repo, "file_path": "rust/Cargo.toml"}, expected={"content_contains": "[package]", "file": "rust/Cargo.toml"}),
            _request("zero_evidence_bound", "loci_explore", {"repo": repo, "intent": "type_dependencies", "seed_ids": ["python/consumer.py::decode#function"], "max_evidence_bytes": 0, "max_output_bytes": 2048}, expected={"empty": True, "relationships": "authored_types"}),
            _request("rust_workspace_declared_possible", "loci_explore", {"repo": repo, "intent": "type_dependencies", "seed_ids": ["rust_workspace/app/src/lib.rs::use_it#function"], **bounded}, expected={"ids": ["rust_workspace/app/src/lib.rs::use_it#function", "rust_workspace/core/src/api.rs::Thing#struct"], "relationships": "authored_types", "resolution_configuration": "declared_possible", "source_files": ["rust_workspace/Cargo.toml", "rust_workspace/app/Cargo.toml", "rust_workspace/core/Cargo.toml"]}),
        ],
    }


def prepare() -> None:
    if ROOT.exists():
        shutil.rmtree(ROOT)
    corpus = load_corpus(CORPUS_ROOT)
    for directory, snapshot in {
        "python": "python_contracts", "javascript": "javascript_dependencies",
        "go": "go_contracts", "rust": "rust_contracts", "tsx": "tsx_props",
        "rust_workspace": "rust_workspace",
    }.items():
        materialize_snapshot(corpus, snapshot, ROOT / directory)
    if not PYTHON_ROOT.exists():
        materialize_snapshot(corpus, "python_contracts", PYTHON_ROOT)
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    PLAN.write_text(json.dumps(_plan(), indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"repo": str(ROOT), "plan": str(PLAN)}, sort_keys=True))


def prepare_python_root() -> None:
    if PYTHON_ROOT.exists():
        raise ValueError(f"refusing to replace existing fixture root: {PYTHON_ROOT}")
    materialize_snapshot(load_corpus(CORPUS_ROOT), "python_contracts", PYTHON_ROOT)
    PLAN.write_text(json.dumps(_plan(), indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"python_repo": str(PYTHON_ROOT), "plan": str(PLAN)}, sort_keys=True))


def freshen() -> None:
    path = ROOT / "tsx/badge.tsx"
    before = path.read_text(encoding="utf-8")
    assert "return <span>{props.label}</span>;" in before
    after = before.replace("return <span>{props.label}</span>;", "return <span>W55_FRESH:{props.label}</span>;")
    path.write_text(after, encoding="utf-8")
    go_control = ROOT / "go/go.mod"
    go_before = go_control.read_text(encoding="utf-8")
    assert "module example.com/acme" in go_before
    go_after = go_before.replace("module example.com/acme", "module example.com/w55fresh")
    go_control.write_text(go_after, encoding="utf-8")
    plan = {
        "schema_version": 1, "repo": str(ROOT),
        "changed_files": {
            "tsx/badge.tsx": {"before_sha256": hashlib.sha256(before.encode()).hexdigest(), "after_sha256": hashlib.sha256(after.encode()).hexdigest(), "marker": "W55_FRESH"},
            "go/go.mod": {"before_sha256": hashlib.sha256(go_before.encode()).hexdigest(), "after_sha256": hashlib.sha256(go_after.encode()).hexdigest(), "marker": "example.com/w55fresh"},
        },
        "requests": [
            _request("fresh_tsx_file", "loci_file", {"repo": str(ROOT), "file_path": "tsx/badge.tsx"}, expected={"content_contains": "W55_FRESH", "file": "tsx/badge.tsx"}),
            _request("fresh_tsx_explore", "loci_explore", {"repo": str(ROOT), "intent": "locate", "seed_ids": ["tsx/badge.tsx::Badge#function"], "max_evidence_bytes": 8192, "max_output_bytes": 16384}, expected={"ids": ["tsx/badge.tsx::Badge#function"], "marker": "W55_FRESH", "relationships": "none"}),
            _request("fresh_go_module_control", "loci_file", {"repo": str(ROOT), "file_path": "go/go.mod"}, expected={"content_contains": "example.com/w55fresh", "file": "go/go.mod"}),
        ],
    }
    FRESH_PLAN.write_text(json.dumps(plan, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"fresh_plan": str(FRESH_PLAN), "changed_files": plan["changed_files"]}, sort_keys=True))


def refresh_fresh_plan() -> None:
    """Update validator-only plan metadata without changing the fresh fixture."""
    plan = json.loads(FRESH_PLAN.read_text(encoding="utf-8"))
    for request in plan["requests"]:
        if request["name"] == "fresh_tsx_explore":
            request["expected"]["relationships"] = "none"
    FRESH_PLAN.write_text(json.dumps(plan, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"fresh_plan": str(FRESH_PLAN), "refreshed": True}, sort_keys=True))


def _fail(name: str, message: str) -> None:
    raise AssertionError(f"{name}: {message}")


def _interval_bytes(sources: list[dict[str, Any]]) -> int:
    """Count unique byte intervals, preserving separate source versions."""
    intervals: dict[tuple[str, str], list[tuple[int, int]]] = {}
    for source in sources:
        intervals.setdefault((source["file"], source["content_hash"]), []).append(
            (source["start_byte"], source["end_byte"])
        )
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


def _wire_bytes(raw: dict[str, Any]) -> int:
    """Use the MCP SDK's exact response serialization, not a JSON approximation."""
    from mcp.types import CallToolResult

    result = CallToolResult.model_validate(raw)
    return len(result.model_dump_json(by_alias=True, exclude_unset=True).encode("utf-8"))


def _verify_sources(name: str, repo: Path, payload: dict[str, Any]) -> dict[int, dict[str, Any]]:
    source_by_id: dict[int, dict[str, Any]] = {}
    identities: set[tuple[str, str, int, int]] = set()
    for source in payload["sources"]:
        source_id = source["id"]
        if source_id in source_by_id:
            _fail(name, f"duplicate source id {source_id}")
        identity = (source["file"], source["content_hash"], source["start_byte"], source["end_byte"])
        if identity in identities:
            _fail(name, f"duplicate source interval {identity}")
        identities.add(identity)
        source_by_id[source_id] = source
        data = (repo / source["file"]).read_bytes()
        start, end = source["start_byte"], source["end_byte"]
        if not (0 <= start <= end <= len(data)):
            _fail(name, f"invalid byte span for {source['file']}")
        if hashlib.sha256(data).hexdigest() != source["content_hash"]:
            _fail(name, f"stale content hash for {source['file']}")
        if data[start:end] != source["content"].encode("utf-8"):
            _fail(name, f"source bytes differ for {source['file']}:{start}:{end}")
    return source_by_id


def _verify_paths(name: str, payload: dict[str, Any], sources: dict[int, dict[str, Any]]) -> None:
    items = {item["id"]: item for item in payload["items"]}
    relations = {relation["id"]: relation for relation in payload["relationships"]}
    if len(items) != len(payload["items"]):
        _fail(name, "duplicate item id")
    if len(relations) != len(payload["relationships"]):
        _fail(name, "duplicate relationship id")
    for relation in relations.values():
        edge = relation["edge"]
        if edge["from"] not in items or edge["to"] not in items:
            _fail(name, f"relationship endpoint outside delivered items: {edge}")
        ids = relation["source_ids"]
        if not ids or len(ids) != len(set(ids)) or any(source_id not in sources for source_id in ids):
            _fail(name, f"invalid relationship source closure for {relation['id']}")
    for item in items.values():
        if item["source_id"] not in sources:
            _fail(name, f"missing item source {item['source_id']}")
        path = item["path"]
        if item["depth"] != len(path) or any(relation_id not in relations for relation_id in path):
            _fail(name, f"invalid path metadata for {item['id']}")
        previous: str | None = None
        for relation_id in path:
            relation = relations[relation_id]
            edge = relation["edge"]
            begin, finish = (edge["from"], edge["to"]) if relation["traversed"] == "forward" else (edge["to"], edge["from"])
            if previous is not None and previous != begin:
                _fail(name, f"non-contiguous path for {item['id']}")
            previous = finish
        if previous is not None and previous != item["id"]:
            _fail(name, f"path does not end at {item['id']}")


def _verify_explore(request: dict[str, Any], raw: dict[str, Any]) -> dict[str, Any]:
    name = request["name"]
    expected, arguments = request["expected"], request["arguments"]
    if expected.get("error_code"):
        error = raw.get("structuredContent", {}).get("error", {})
        if raw.get("isError") is not True or error.get("code") != expected["error_code"]:
            _fail(name, f"expected host error {expected['error_code']}, got {raw}")
        return {"expected_error": error["code"]}
    if raw.get("isError") is not False:
        _fail(name, f"host error: {raw.get('structuredContent')}")
    payload = raw.get("structuredContent")
    if not isinstance(payload, dict):
        _fail(name, "missing structuredContent")
    from loci.mcp_output_models import LociExploreOutput
    LociExploreOutput.model_validate(payload)
    if payload["scope"]["relationships"] != expected["relationships"]:
        _fail(name, "unexpected relationship scope")
    if expected.get("empty"):
        if payload["status"] != "empty" or payload["items"] or payload["relationships"] or payload["sources"]:
            _fail(name, "zero-evidence request was not an empty packet")
    else:
        actual_ids = {item["id"] for item in payload["items"]}
        missing = set(expected["ids"]) - actual_ids
        if missing:
            _fail(name, f"missing expected declaration endpoints: {sorted(missing)}")
        unexpected = set(expected.get("absent_ids", [])) & actual_ids
        if unexpected:
            _fail(name, f"fixture-layout control unexpectedly resolved: {sorted(unexpected)}")
        actual_edges = {(edge["from"], edge["type"], edge["to"]) for edge in (r["edge"] for r in payload["relationships"])}
        for edge in expected.get("edges", []):
            if tuple(edge) not in actual_edges:
                _fail(name, f"missing expected declaration relationship: {edge}")
        config = expected.get("resolution_configuration")
        if config is not None and (not payload["relationships"] or any(r["resolution_configuration"] != config for r in payload["relationships"])):
            _fail(name, f"expected all relationships to be {config}")
    sources = _verify_sources(name, Path(arguments["repo"]), payload)
    _verify_paths(name, payload, sources)
    expected_sources = set(expected.get("source_files", []))
    actual_source_files = {source["file"] for source in payload["sources"]}
    if not expected_sources <= actual_source_files:
        _fail(name, f"missing controls: {sorted(expected_sources - actual_source_files)}")
    limits, usage = payload["limits"], payload["usage"]
    for limit_name in ("max_hops", "max_evidence_bytes", "max_output_bytes"):
        if limit_name in arguments and limits[limit_name] != arguments[limit_name]:
            _fail(name, f"echoed {limit_name} does not equal requested bound")
    if len(payload["items"]) > limits["max_items"]:
        _fail(name, "item cap exceeded")
    if len(payload["items"]) > limits["max_nodes"]:
        _fail(name, "node cap exceeded")
    if any(item["depth"] > limits["max_hops"] for item in payload["items"]):
        _fail(name, "hop cap exceeded")
    if usage["evidence_bytes"] != _interval_bytes(payload["sources"]):
        _fail(name, "evidence-byte accounting differs from delivered spans")
    if usage["evidence_bytes"] > limits["max_evidence_bytes"]:
        _fail(name, "evidence budget exceeded")
    if usage["output_bytes"] != _wire_bytes(raw):
        _fail(name, "output-byte accounting differs from MCP SDK serialization")
    if usage["output_bytes"] > limits["max_output_bytes"]:
        _fail(name, "output budget exceeded")
    marker = expected.get("marker")
    if marker and not any(marker in source["content"] for source in payload["sources"]):
        _fail(name, f"fresh marker {marker!r} is absent from delivered source")
    return {"items": len(payload["items"]), "relationships": len(payload["relationships"]), "output_bytes": usage["output_bytes"]}


def _verify_file(request: dict[str, Any], raw: dict[str, Any]) -> dict[str, Any]:
    name, expected = request["name"], request["expected"]
    if raw.get("isError") is not False:
        _fail(name, f"host error: {raw.get('structuredContent')}")
    payload = raw.get("structuredContent")
    if not isinstance(payload, dict) or payload.get("file") != expected["file"]:
        _fail(name, "file response did not identify the requested control")
    actual = (Path(request["arguments"]["repo"]) / expected["file"]).read_text(encoding="utf-8")
    if payload.get("content") != actual:
        _fail(name, "delivered file content differs from fixture")
    if expected["content_contains"] not in payload["content"]:
        _fail(name, "expected control declaration absent")
    return {"bytes": len(actual.encode("utf-8"))}


def verify(*, fresh: bool) -> None:
    plan_path = FRESH_PLAN if fresh else PLAN
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    results: dict[str, Any] = {}
    for request in plan["requests"]:
        evidence_path = Path(request["evidence_file"])
        if not evidence_path.is_file():
            _fail(request["name"], f"missing raw host evidence: {evidence_path}")
        raw = json.loads(evidence_path.read_text(encoding="utf-8"))
        results[request["name"]] = (_verify_explore(request, raw) if request["tool"] == "loci_explore" else _verify_file(request, raw))
    if fresh:
        for relative, expected_change in plan["changed_files"].items():
            after = hashlib.sha256((ROOT / relative).read_bytes()).hexdigest()
            if after != expected_change["after_sha256"] or after == expected_change["before_sha256"]:
                _fail("freshness", f"fixture did not retain declared post-change hash for {relative}")
    print(json.dumps({"ok": True, "fresh": fresh, "requests": results}, sort_keys=True))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("stage", choices=("prepare", "prepare-python-root", "freshen", "fresh-plan", "verify", "plan"))
    parser.add_argument("--fresh", action="store_true")
    args = parser.parse_args()
    if args.stage == "prepare": prepare()
    elif args.stage == "prepare-python-root": prepare_python_root()
    elif args.stage == "freshen": freshen()
    elif args.stage == "fresh-plan": refresh_fresh_plan()
    elif args.stage == "verify": verify(fresh=args.fresh)
    else: PLAN.write_text(json.dumps(_plan(), indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
