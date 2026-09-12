"""Acceptance coverage for Rust declaration owners in the frozen corpus."""
from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path

from benchmarks.typescript_context_corpus import (
    _isolated_store,
    load_corpus,
    materialize_snapshot,
)
from loci import service
from loci.parser.extractor import parse_file


CORPUS_ROOT = Path(__file__).parents[1] / "benchmarks/corpora/multilingual-context-v1"


@contextmanager
def _indexed_rust_contracts(tmp_path: Path):
    corpus = load_corpus(CORPUS_ROOT)
    repo = tmp_path / "rust_contracts"
    materialize_snapshot(corpus, "rust_contracts", repo)
    with _isolated_store(tmp_path / "store"):
        service.index_repo(repo, incremental=False)
        yield repo


def test_rust_alias_and_impl_sites_keep_exact_declaration_ownership(tmp_path: Path):
    with _indexed_rust_contracts(tmp_path) as repo:
        source_path = repo / "src/lib.rs"
        source = source_path.read_bytes()
        direct = parse_file(source_path)
        alias, format_impl, render_impl, render_method = service.get_symbols(
            repo,
            [
                "src/lib.rs::UserId#type",
                "src/lib.rs::Receipt#impl",
                "src/lib.rs::Receipt#impl~1",
                "src/lib.rs::Receipt.render#method",
            ],
        )

    assert (alias["id"], alias["kind"], alias["signature"], alias["source"]) == (
        "src/lib.rs::UserId#type",
        "type",
        "pub type UserId = u64;",
        "pub type UserId = u64;",
    )
    assert (format_impl["id"], format_impl["kind"], format_impl["source"]) == (
        "src/lib.rs::Receipt#impl",
        "impl",
        "impl Format for Receipt {}",
    )
    assert (render_impl["id"], render_impl["kind"], render_impl["source"]) == (
        "src/lib.rs::Receipt#impl~1",
        "impl",
        'impl Render for Receipt {\n    fn render(&self) -> String { format!("{}", self.id) }\n}',
    )
    assert (render_method["id"], render_method["kind"], render_method["source"]) == (
        "src/lib.rs::Receipt.render#method",
        "method",
        'fn render(&self) -> String { format!("{}", self.id) }',
    )

    by_id = {symbol.id: symbol for symbol in direct}
    alias_direct = by_id[next(symbol.id for symbol in direct if symbol.name == "UserId")]
    assert source[alias_direct.byte_offset:alias_direct.byte_offset + alias_direct.byte_length] == (
        b"pub type UserId = u64;"
    )
    assert alias_direct.metadata["loci"]["rust_type_configuration"] == "unconditional"
    assert all(
        by_id[symbol_id].metadata["loci"]["rust_type_configuration"] == "unconditional"
        for symbol_id in (
            next(symbol.id for symbol in direct if symbol.kind == "impl"),
            next(symbol.id for symbol in direct if symbol.kind == "impl" and symbol.id.endswith("~1")),
            next(symbol.id for symbol in direct if symbol.name == "render" and symbol.kind == "method"),
        )
    )


def test_rust_type_configuration_inherits_an_enclosing_cfg_impl(tmp_path: Path):
    source_path = tmp_path / "conditional.rs"
    source_path.write_text(
        """#[cfg(feature = \"optional\")]
impl Receipt {
    fn render(&self) -> String { String::new() }
}
""",
        encoding="utf-8",
    )

    symbols = {symbol.kind: symbol for symbol in parse_file(source_path)}

    assert symbols["impl"].metadata["loci"]["rust_type_configuration"] == "declared_possible"
    assert symbols["method"].metadata["loci"]["rust_type_configuration"] == "declared_possible"
