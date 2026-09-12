"""Rust Cargo controls fail closed when indexed bytes are no longer safe."""
from __future__ import annotations

import pytest

from benchmarks.typescript_context_corpus import load_corpus
from loci import service
from tests.test_python_context_delivery import CORPUS_ROOT, _indexed_snapshot, _items


@pytest.mark.parametrize("mutation", ["changed", "missing", "escaping_symlink"])
def test_stale_rust_cargo_control_is_not_delivered(tmp_path, mutation):
    corpus = load_corpus(CORPUS_ROOT)
    with _indexed_snapshot(tmp_path, corpus, "rust_workspace") as repo:
        manifest = repo / "app/Cargo.toml"
        if mutation == "changed":
            manifest.write_text(
                manifest.read_text(encoding="utf-8").replace(", optional = true", ""),
                encoding="utf-8",
            )
        elif mutation == "missing":
            manifest.unlink()
        else:
            outside = tmp_path / "outside-Cargo.toml"
            outside.write_text(manifest.read_text(encoding="utf-8"), encoding="utf-8")
            manifest.unlink()
            manifest.symlink_to(outside)

        result = service.explore(
            repo,
            intent="type_dependencies",
            seed_ids=["app/src/lib.rs::use_it#function"],
            max_evidence_bytes=8192,
            max_output_bytes=16384,
            ensure_fresh=False,
        )
        assert set(_items(result)) == {"app/src/lib.rs::use_it#function"}
        assert not result["relationships"]
        assert any(omission["reason"] == "source_unavailable" for omission in result["omissions"])
