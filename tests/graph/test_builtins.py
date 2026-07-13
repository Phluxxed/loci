from __future__ import annotations

from loci.graph.builtins import extract_markdown_contains_edges
from loci.parser.symbols import Symbol


def _markdown_symbol(
    symbol_id: str,
    *,
    name: str,
    line: int,
    parent_id: str = "",
    content_hash: str,
    span_kind: str = "section",
) -> Symbol:
    return Symbol(
        id=symbol_id,
        name=name,
        qualified_name=name,
        kind="section",
        language="markdown",
        file_path="guide.md",
        byte_offset=0,
        byte_length=20,
        content_hash=content_hash,
        line=line,
        end_line=line + 2,
        metadata={
            "markdown": {
                "parent_id": parent_id,
                "root_id": symbol_id if not parent_id else "guide.md::Guide#section",
                "span_kind": span_kind,
            }
        },
    )


def test_markdown_contains_edges_use_final_repo_relative_ids():
    parent_id = "guide.md::Guide#section"
    child_id = "guide.md::Guide > Install#section"
    symbols = [
        _markdown_symbol(
            parent_id,
            name="Guide",
            line=1,
            content_hash="a" * 64,
            span_kind="page_root",
        ),
        _markdown_symbol(
            child_id,
            name="Install",
            line=5,
            parent_id=parent_id,
            content_hash="b" * 64,
        ),
    ]

    edges = extract_markdown_contains_edges(symbols)

    assert [(edge.from_id, edge.to_id) for edge in edges] == [
        (parent_id, child_id)
    ]


def test_markdown_contains_edges_are_directed_and_exact():
    parent_id = "guide.md::Guide#section"
    child_id = "guide.md::Guide > Install#section"
    symbols = [
        _markdown_symbol(
            parent_id,
            name="Guide",
            line=1,
            content_hash="a" * 64,
            span_kind="page_root",
        ),
        _markdown_symbol(
            child_id,
            name="Install",
            line=5,
            parent_id=parent_id,
            content_hash="b" * 64,
        ),
    ]

    edge = extract_markdown_contains_edges(symbols)[0]

    assert edge.type == "contains"
    assert edge.directed is True
    assert edge.namespace == "loci"
    assert edge.resolution == "exact"


def test_markdown_root_and_preamble_emit_no_parent_edge():
    symbols = [
        _markdown_symbol(
            "guide.md::(preamble)#section",
            name="(preamble)",
            line=1,
            content_hash="a" * 64,
            span_kind="preamble",
        ),
        _markdown_symbol(
            "guide.md::Guide#section",
            name="Guide",
            line=3,
            content_hash="b" * 64,
            span_kind="page_root",
        ),
    ]

    assert extract_markdown_contains_edges(symbols) == []


def test_contains_evidence_identifies_child_heading():
    parent_id = "guide.md::Guide#section"
    child_id = "guide.md::Guide > Install#section"
    symbols = [
        _markdown_symbol(
            parent_id,
            name="Guide",
            line=1,
            content_hash="a" * 64,
            span_kind="page_root",
        ),
        _markdown_symbol(
            child_id,
            name="Install",
            line=5,
            parent_id=parent_id,
            content_hash="b" * 64,
        ),
    ]

    evidence = extract_markdown_contains_edges(symbols)[0].evidence

    assert evidence.file == "guide.md"
    assert evidence.line == 5
    assert evidence.content_hash == "b" * 64


def test_contains_edges_are_deterministically_sorted():
    root_id = "guide.md::Guide#section"
    alpha_id = "guide.md::Guide > Alpha#section"
    zulu_id = "guide.md::Guide > Zulu#section"
    symbols = [
        _markdown_symbol(
            zulu_id,
            name="Zulu",
            line=9,
            parent_id=root_id,
            content_hash="c" * 64,
        ),
        _markdown_symbol(
            root_id,
            name="Guide",
            line=1,
            content_hash="a" * 64,
            span_kind="page_root",
        ),
        _markdown_symbol(
            alpha_id,
            name="Alpha",
            line=5,
            parent_id=root_id,
            content_hash="b" * 64,
        ),
    ]

    edges = extract_markdown_contains_edges(symbols)

    assert [edge.to_id for edge in edges] == [alpha_id, zulu_id]


def test_non_markdown_symbols_never_emit_contains_edges():
    symbol = Symbol(
        id="src/app.py::Widget.method#method",
        name="method",
        qualified_name="Widget.method",
        kind="method",
        language="python",
        file_path="src/app.py",
        byte_offset=0,
        byte_length=20,
        content_hash="a" * 64,
        line=1,
        end_line=2,
        metadata={"markdown": {"parent_id": "src/app.py::Widget#class"}},
    )

    assert extract_markdown_contains_edges([symbol]) == []
