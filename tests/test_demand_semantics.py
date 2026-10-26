"""Focused safeguards for the isolated demand-driven semantic candidate."""
from __future__ import annotations

from pathlib import Path
import json

import pytest

from loci.demand_semantics import DemandSource
from loci.graph_free import GraphFreeError


def _source(tmp_path: Path, files: dict[str, str]) -> tuple[Path, DemandSource]:
    root = tmp_path / "repo"
    root.mkdir()
    for name, content in files.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
    return root, DemandSource(tmp_path / "store")


def test_source_only_operations_do_not_prepare_semantics(tmp_path: Path, monkeypatch):
    root, source = _source(tmp_path, {"a.ts": "export function hello() { return 1; }\n"})
    monkeypatch.setattr(source, "_resolve_slice", lambda *args: pytest.fail("semantic resolution ran"))
    source.index_repo(root)
    packet = source.retrieve(root, "hello")
    source.read(root, packet["items"][0]["source_ref"])
    assert source.semantic_observer() == {"index": None, "work": {"semantic_calls": 0}}


def test_exact_typescript_proof_cache_and_changed_source(tmp_path: Path):
    root, source = _source(tmp_path, {
        "a.ts": "export function hello() { return 1; }\n",
        "b.ts": "import { hello } from './a';\nexport function run() { return hello(); }\n",
    })
    first = source.semantic_context(root, "hello")
    assert {item["edge"]["type"] for item in first["relationships"]} >= {"calls", "references"}
    assert source.semantic_observer()["work"]["cache_hit"] is False
    assert source.semantic_observer()["work"]["parsed_paths"] == ["a.ts", "b.ts"]
    source.semantic_context(root, "hello")
    assert source.semantic_observer()["work"]["cache_hit"] is True
    assert source.semantic_observer()["work"]["parsed_paths"] == []
    assert source.semantic_observer()["work"]["cache_entries"] == 1
    assert source.semantic_observer()["work"]["cache_serialized_proxy_bytes"] > 0
    old_ref = first["items"][0]["source_ref"]
    (root / "a.ts").write_text("export function hello() { return 2; }\n")
    with pytest.raises(GraphFreeError, match="Semantic source changed|differs from inventory"):
        source.read(root, old_ref)
    source.semantic_context(root, "hello")
    assert source.semantic_observer()["work"]["cache_hit"] is False
    (root / "c.ts").write_text("export const EXTRA = 1;\n")
    source.semantic_context(root, "hello")
    assert source.semantic_observer()["work"]["cache_hit"] is False


def test_mutation_during_semantic_resolution_cannot_cache_proof(tmp_path: Path, monkeypatch):
    root, source = _source(tmp_path, {"a.ts": "export function hello() { return 1; }\n"})
    original = source._resolve_slice

    def changed(*args):
        result = original(*args)
        (root / "a.ts").write_text("export function hello() { return 2; }\n")
        return result

    monkeypatch.setattr(source, "_resolve_slice", changed)
    with pytest.raises(GraphFreeError, match="Repository changed during semantic resolution"):
        source.semantic_context(root, "hello")
    assert not source._semantic_cache


def test_unproven_entry_and_partial_import_closure(tmp_path: Path, monkeypatch):
    root, source = _source(tmp_path, {
        "a.ts": "export function hello() { return 1; }\n",
        "b.ts": "import { hello } from './a';\nexport function run() { return hello(); }\n",
        "notes.py": "def unrelated(): pass\n",
    })
    unsupported = source.semantic_context(root, "notes.py")
    assert unsupported["relationships"] == []
    assert {item["reason"] for item in unsupported["omissions"]} >= {"unsupported_language", "no_anchor"}
    monkeypatch.setattr("loci.demand_semantics.MAX_PARSED_FILES", 1)
    limited = source.semantic_context(root, "run")
    assert not any(item["edge"]["type"] in {"calls", "references"}
                   for item in limited["relationships"])
    assert source.semantic_observer()["index"]["semantic_scope"]["import_closure_limit"]
    assert any(item["reason"] == "import_closure_limit" for item in limited["omissions"])


def test_ambiguous_name_keeps_multiple_anchors(tmp_path: Path):
    root, source = _source(tmp_path, {
        "a.ts": "export function hello() { return 1; }\n",
        "b.ts": "export function hello() { return 2; }\n",
    })
    packet = source.semantic_context(root, "hello")
    assert len(packet["anchors"]) == 2
    assert any(item["reason"] == "ambiguous_anchor" for item in packet["omissions"])


def test_evidence_accounting_uses_interval_union(tmp_path: Path):
    root, source = _source(tmp_path, {
        "a.ts": "export function hello() { return 1; }\n",
        "b.ts": "import { hello } from './a';\nexport function run() { return hello(); }\n",
    })
    packet = source.semantic_context(root, "hello")
    assert any(item["edge"]["type"] == "calls" for item in packet["relationships"])
    by_file: dict[tuple[str, str], list[tuple[int, int]]] = {}
    for item in packet["sources"]:
        by_file.setdefault((item["file"], item["content_hash"]), []).append(
            (item["start_byte"], item["end_byte"]))
    unique = 0
    raw_sum = 0
    for spans in by_file.values():
        end = 0
        for start, stop in sorted(spans):
            raw_sum += stop - start
            unique += max(0, stop - max(start, end))
            end = max(end, stop)
    assert unique < raw_sum
    assert packet["usage"]["evidence_bytes"] == unique
    envelope = {"content": [], "structuredContent": packet, "isError": False}
    assert packet["usage"]["output_bytes"] == len(json.dumps(
        envelope, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode())


def test_optional_rust_dependency_remains_declared_possible(tmp_path: Path):
    root, source = _source(tmp_path, {
        "Cargo.toml": '[workspace]\nmembers = ["app", "core"]\n\n[workspace.dependencies]\ncore_api = { package = "core-api", path = "core" }\n',
        "app/Cargo.toml": '[package]\nname = "app"\nversion = "0.1.0"\nedition = "2021"\n\n[dependencies]\ncore_api = { workspace = true, optional = true }\n',
        "app/src/lib.rs": 'use core_api::PublicThing;\npub fn use_it(value: PublicThing) -> PublicThing { value }\n',
        "core/Cargo.toml": '[package]\nname = "core-api"\nversion = "0.1.0"\nedition = "2021"\n',
        "core/src/lib.rs": 'pub mod api;\npub use crate::api::Thing as PublicThing;\n',
        "core/src/api.rs": 'pub struct Thing { pub id: u64 }\n',
    })
    packet = source.semantic_context(root, "use_it")
    assert "core/src/lib.rs" in source.semantic_observer()["work"]["parsed_paths"]
    assert any(item["resolution_configuration"] == "declared_possible"
               for item in packet["relationships"])
    assert not source.semantic_observer()["work"]["rust_closure_incomplete"]
    control = root / "app/Cargo.toml"
    control.write_text(control.read_text().replace(", optional = true", ""))
    changed = source.semantic_context(root, "use_it")
    assert not source.semantic_observer()["work"]["cache_hit"]
    assert changed["relationships"]
    assert all(item["resolution_configuration"] != "declared_possible"
               for item in changed["relationships"])


def test_root_package_question_in_nested_module_acquires_crate_root(tmp_path: Path):
    root, source = _source(tmp_path, {
        "Cargo.toml": '[package]\nname="root-pkg"\nversion="0.1.0"\nedition="2021"\n',
        "src/lib.rs": 'pub mod inner;\n',
        "src/inner.rs": 'pub fn inside() -> u32 { 1 }\n',
    })
    source.semantic_context(root, "inside")
    work = source.semantic_observer()["work"]
    assert {"src/lib.rs", "src/inner.rs"} <= set(work["parsed_paths"])
    assert not work["rust_closure_incomplete"]
