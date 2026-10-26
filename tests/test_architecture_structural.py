"""Focused independent checks for demand structural proof."""
from __future__ import annotations

import copy
import hashlib
from pathlib import Path

from benchmarks.architecture_structural import validate_structural
from benchmarks.architecture_cases import load_suite
from benchmarks.typescript_context_corpus import _isolated_store, materialize_snapshot
from loci import service


INPUTS = Path(__file__).resolve().parents[1] / "benchmarks/comparisons/multilingual-context-workflow-v1/inputs"


def _fixture(tmp_path: Path, snapshot: str) -> tuple[Path, dict]:
    corpus = load_suite(INPUTS)
    repo = tmp_path / snapshot
    materialize_snapshot(corpus, snapshot, repo)
    with _isolated_store(tmp_path / "store"):
        service.index_repo(repo, incremental=False)
        index = service.get_store().load(repo)
    assert index is not None
    index["semantic_scope"] = {
        "inventory_incomplete": False, "rust_closure_incomplete": False,
        "source_stale": False, "parse_limit": False,
        "import_closure_limit": False, "incomplete_reexport_files": [],
        "parsed_paths": list(index["file_hashes"]),
    }
    return repo, index


def _span(repo: Path, file: str, start: int = 0, end: int | None = None) -> dict:
    raw = (repo / file).read_bytes()
    end = len(raw) if end is None else end
    return {"file": file, "start_byte": start, "end_byte": end,
            "content_hash": hashlib.sha256(raw).hexdigest(),
            "content": raw[start:end].decode("utf-8")}


def _packet(edge: dict, spans: list[dict], configuration: str | None) -> dict:
    sources = [{"id": i, **span} for i, span in enumerate(spans, 1)]
    return {"structuredContent": {"policy": "demand-semantic-v1", "sources": sources,
            "relationships": [{"id": 1, "edge": edge, "source_ids": list(range(1, len(sources) + 1)),
                               "proof": "complete", "traversed": "forward",
                               "resolution_configuration": configuration}]}}


def _edge(index: dict, file: str, line: int) -> dict:
    return next(edge for edge in index["graph"]["edges"]
                if edge["type"] == "imports" and edge["evidence"]["file"] == file
                and edge["evidence"]["line"] == line)


def test_optional_crate_and_module_require_exact_controls_site_and_configuration(tmp_path: Path) -> None:
    repo, index = _fixture(tmp_path, "rust_workspace")
    crate = _edge(index, "app/src/lib.rs", 1)
    module = _edge(index, "core/src/lib.rs", 1)
    crate_packet = _packet(crate, [_span(repo, "app/src/lib.rs", 0, 26),
                                   _span(repo, "Cargo.toml"), _span(repo, "app/Cargo.toml"),
                                   _span(repo, "core/Cargo.toml")], "declared_possible")
    module_packet = _packet(module, [_span(repo, "core/src/lib.rs", 0, 13),
                                     _span(repo, "core/Cargo.toml")], "unconditional")
    assert validate_structural(index, [crate_packet, module_packet], repo) == []

    no_control = copy.deepcopy(crate_packet)
    no_control["structuredContent"]["relationships"][0]["source_ids"].remove(3)
    assert "complete structural import support" in validate_structural(index, [no_control], repo)[0]["reason"]

    no_module = copy.deepcopy(module_packet)
    no_module["structuredContent"]["relationships"][0]["source_ids"].remove(1)
    assert "complete structural import support" in validate_structural(index, [no_module], repo)[0]["reason"]

    forged = copy.deepcopy(crate_packet)
    forged["structuredContent"]["relationships"][0]["resolution_configuration"] = "unconditional"
    assert "configuration differs" in validate_structural(index, [forged], repo)[0]["reason"]

    forged_record = copy.deepcopy(index)
    record = next(item for item in forged_record["graph"]["imports"]
                  if item["source_id"] == crate["from"] and item["target_id"] == crate["to"])
    record["resolution_configuration"] = "unconditional"
    assert "promoted to unconditional" in validate_structural(forged_record, [forged], repo)[0]["reason"]

    omitted_control = copy.deepcopy(index)
    record = next(item for item in omitted_control["graph"]["imports"]
                  if item["source_id"] == crate["from"] and item["target_id"] == crate["to"])
    record["resolution_control_files"].remove("app/Cargo.toml")
    assert "omits required Cargo controls" in validate_structural(omitted_control, [crate_packet], repo)[0]["reason"]


def test_ancestor_module_and_unknown_edge_fail_closed(tmp_path: Path) -> None:
    repo, index = _fixture(tmp_path, "rust_uncertainty")
    nested = _edge(index, "src/model.rs", 10)
    native = next(item for item in index["graph"]["imports"]
                  if item["source_id"] == nested["from"] and item["target_id"] == nested["to"]
                  and item["raw"]["line"] == 10)
    # The nested import's own site is in model.rs; lib.rs declares model.
    packet = _packet(nested, [_span(repo, "src/model.rs"), _span(repo, "src/lib.rs"),
                              _span(repo, "Cargo.toml")], native["resolution_configuration"])
    assert validate_structural(index, [packet], repo) == []

    missing_parent = copy.deepcopy(packet)
    missing_parent["structuredContent"]["relationships"][0]["source_ids"].remove(2)
    assert "complete structural import support" in validate_structural(index, [missing_parent], repo)[0]["reason"]

    no_ancestor_record = copy.deepcopy(index)
    no_ancestor_record["graph"]["imports"] = [item for item in no_ancestor_record["graph"]["imports"]
                                               if item.get("target_file") != "src/model.rs"]
    assert "module ancestry is incomplete" in validate_structural(no_ancestor_record, [packet], repo)[0]["reason"]

    unknown = copy.deepcopy(packet)
    unknown["structuredContent"]["relationships"][0]["edge"]["to"] = "wrong.rs::__file__#file"
    assert "not a native indexed import" in validate_structural(index, [unknown], repo)[0]["reason"]

    limited = copy.deepcopy(index)
    limited["semantic_scope"]["rust_closure_incomplete"] = True
    assert "binding domain is incomplete" in validate_structural(limited, [packet], repo)[0]["reason"]
