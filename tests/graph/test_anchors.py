from __future__ import annotations

from typing import Any

import pytest

from loci.graph.anchors import (
    MAX_GRAPH_ANCHORS,
    MAX_GRAPH_QUERY_TERMS,
    MAX_GRAPH_QUESTION_BYTES,
    select_graph_anchors,
)
from loci.graph.contracts import GraphContractError


def _symbol(
    symbol_id: str,
    *,
    name: str,
    file_path: str,
    language: str = "markdown",
    qualified_name: str | None = None,
    summary: str = "",
    docstring: str = "",
    keywords: list[str] | None = None,
    frontmatter: dict[str, Any] | None = None,
    root_id: str | None = None,
    page_root: bool = True,
    line: int = 1,
) -> dict[str, Any]:
    metadata: dict[str, Any] = {}
    if language == "markdown":
        metadata["markdown"] = {
            "page_root": page_root,
            "root_id": root_id or symbol_id,
            "span_kind": "page_root" if page_root else "section",
        }
    if frontmatter is not None:
        metadata["frontmatter"] = frontmatter
    return {
        "id": symbol_id,
        "name": name,
        "qualified_name": qualified_name or name,
        "kind": "section" if language == "markdown" else "function",
        "language": language,
        "file_path": file_path,
        "line": line,
        "end_line": line + 1,
        "signature": name,
        "summary": summary,
        "docstring": docstring,
        "keywords": keywords or [],
        "metadata": metadata,
    }


def test_explicit_seeds_override_inference_and_preserve_exact_order():
    first = _symbol("guide.md::Guide#section", name="Guide", file_path="guide.md")
    section = _symbol(
        "guide.md::Guide > Install#section",
        name="Install",
        file_path="guide.md",
        root_id=first["id"],
        page_root=False,
    )

    selection = select_graph_anchors(
        [first, section],
        "question that matches nothing",
        [section["id"], first["id"], section["id"]],
        max_anchors=2,
    )

    assert selection.mode == "explicit"
    assert selection.question_terms == ()
    assert [anchor.node_id for anchor in selection.anchors] == [
        section["id"],
        first["id"],
    ]
    assert all(anchor.node_id == anchor.matched_symbol_id for anchor in selection.anchors)
    assert all(anchor.score is None for anchor in selection.anchors)
    assert selection.effective_max_anchors == 2


def test_explicit_missing_seed_is_structured_error():
    with pytest.raises(GraphContractError) as raised:
        select_graph_anchors([], "question", ["missing"], max_anchors=8)

    assert raised.value.code == "GRAPH_ENDPOINT_NOT_FOUND"
    assert raised.value.details["missing_ids"] == ["missing"]


@pytest.mark.parametrize("max_anchors", [0, MAX_GRAPH_ANCHORS + 1])
def test_anchor_limit_is_bounded(max_anchors: int):
    with pytest.raises(GraphContractError) as raised:
        select_graph_anchors([], "question", [], max_anchors=max_anchors)

    assert raised.value.code == "INVALID_INPUT"


def test_question_or_explicit_seed_is_required():
    with pytest.raises(GraphContractError) as raised:
        select_graph_anchors([], "  ", [], max_anchors=8)

    assert raised.value.code == "INVALID_INPUT"


def test_question_bytes_are_bounded():
    question = "x" * (MAX_GRAPH_QUESTION_BYTES + 1)

    with pytest.raises(GraphContractError) as raised:
        select_graph_anchors([], question, [], max_anchors=8)

    assert raised.value.code == "INVALID_INPUT"
    assert raised.value.details["max_bytes"] == MAX_GRAPH_QUESTION_BYTES


def test_more_unique_explicit_seeds_than_limit_is_rejected():
    symbols = [
        _symbol(f"page-{index}.md::Page {index}#section", name=f"Page {index}", file_path=f"page-{index}.md")
        for index in range(3)
    ]

    with pytest.raises(GraphContractError) as raised:
        select_graph_anchors(
            symbols,
            "question",
            [symbol["id"] for symbol in symbols],
            max_anchors=2,
        )

    assert raised.value.code == "INVALID_INPUT"
    assert raised.value.details["seed_count"] == 3


def test_question_terms_remove_stop_words_deduplicate_and_obey_bound():
    terms = [f"term{index}" for index in range(MAX_GRAPH_QUERY_TERMS + 5)]
    question = "What is the " + " ".join(terms + [terms[0]])

    selection = select_graph_anchors([], question, [], max_anchors=8)

    assert len(selection.question_terms) == MAX_GRAPH_QUERY_TERMS
    assert "what" not in selection.question_terms
    assert "the" not in selection.question_terms
    assert len(set(selection.question_terms)) == len(selection.question_terms)


def test_inferred_markdown_root_and_section_collapse_to_one_file_anchor():
    root_id = "ideas/retrieval.md::Retrieval Design#section"
    root = _symbol(
        root_id,
        name="Retrieval Design",
        file_path="ideas/retrieval.md",
        frontmatter={"title": "Retrieval Design", "tags": ["bounded-graph"]},
    )
    section = _symbol(
        "ideas/retrieval.md::Retrieval Design > Query Aware Traversal#section",
        name="Query Aware Traversal",
        file_path="ideas/retrieval.md",
        summary="Use bounded query aware graph traversal.",
        root_id=root_id,
        page_root=False,
    )

    selection = select_graph_anchors(
        [root, section],
        "How should query aware traversal stay bounded?",
        [],
        max_anchors=8,
    )

    assert selection.mode == "inferred"
    assert len(selection.anchors) == 1
    assert selection.anchors[0].node_id == root_id
    assert selection.anchors[0].matched_symbol_id == section["id"]
    assert set(selection.anchors[0].matched_terms) >= {"query", "aware", "traversal"}
    assert selection.collapsed_symbols == 1


def test_multiple_markdown_page_roots_still_collapse_by_file():
    first = _symbol(
        "brain.md::Operating Rule#section",
        name="Operating Rule",
        file_path="brain.md",
        summary="Rowan works directly with Vik.",
    )
    second = _symbol(
        "brain.md::Failure Mode#section",
        name="Failure Mode",
        file_path="brain.md",
        summary="Avoid split Rowan identity.",
        line=10,
    )

    selection = select_graph_anchors(
        [first, second],
        "How should split Rowan identity be avoided?",
        [],
        max_anchors=8,
    )

    assert len(selection.anchors) == 1
    assert selection.anchors[0].node_id == first["id"]
    assert selection.anchors[0].matched_symbol_id == second["id"]
    assert selection.eligible_units == 1


def test_non_markdown_symbols_in_one_file_remain_separate_units():
    symbols = [
        _symbol(
            "src/auth.py::login#function",
            name="login_user",
            file_path="src/auth.py",
            language="python",
        ),
        _symbol(
            "src/auth.py::logout#function",
            name="logout_user",
            file_path="src/auth.py",
            language="python",
        ),
    ]

    selection = select_graph_anchors(
        symbols,
        "login logout user",
        [],
        max_anchors=8,
    )

    assert selection.eligible_units == 2
    assert selection.qualified_candidates == 2
    assert selection.collapsed_symbols == 0
    assert selection.effective_max_anchors == 1


def test_short_rare_title_match_outranks_long_generic_heading():
    expected = _symbol(
        "ideas/query-aware-traversal.md::Query Aware Traversal#section",
        name="Query Aware Traversal",
        file_path="ideas/query-aware-traversal.md",
    )
    long_log = _symbol(
        "log.md::Long Event#section",
        name=(
            "Recorded graph retrieval wiki evidence and query aware traversal "
            "results before local adoption with many unrelated details"
        ),
        file_path="log.md",
    )
    fillers = [
        _symbol(
            f"notes/filler-{index}.md::Filler {index}#section",
            name=f"Filler {index}",
            file_path=f"notes/filler-{index}.md",
            summary="Generic graph wiki retrieval notes.",
        )
        for index in range(12)
    ]

    selection = select_graph_anchors(
        [long_log, expected, *fillers],
        "What evidence supports query aware graph traversal before adoption?",
        [],
        max_anchors=8,
    )

    assert selection.anchors[0].node_id == expected["id"]


def test_question_intent_words_do_not_make_evidence_artifact_beat_subject_page():
    subject = _symbol(
        "articles/code-graph-rag.md::Code Graph RAG#section",
        name="Code Graph RAG",
        file_path="articles/code-graph-rag.md",
    )
    evidence_artifact = _symbol(
        "sources/code-graph-rag-evidence.md::Code Graph RAG Evidence#section",
        name="Code Graph RAG Evidence",
        file_path="sources/code-graph-rag-evidence.md",
    )
    fillers = [
        _symbol(
            f"notes/filler-{index}.md::Filler {index}#section",
            name=f"Filler {index}",
            file_path=f"notes/filler-{index}.md",
        )
        for index in range(10)
    ]

    selection = select_graph_anchors(
        [evidence_artifact, subject, *fillers],
        "What evidence shows that Code Graph RAG improved retrieval?",
        [],
        max_anchors=8,
    )

    assert selection.anchors[0].node_id == subject["id"]


def test_inferred_selection_diversifies_redundant_query_aspects():
    recall = _symbol(
        "ideas/recall-efficient-traversal.md::Recall Efficient Traversal#section",
        name="Recall Efficient Wiki Traversal",
        file_path="ideas/recall-efficient-traversal.md",
    )
    duplicates = [
        _symbol(
            f"sources/recall-efficient-traversal-{index}.md::Recall Efficient Traversal {index}#section",
            name=f"Recall Efficient Wiki Traversal Evidence {index}",
            file_path=f"sources/recall-efficient-traversal-{index}.md",
        )
        for index in range(5)
    ]
    code_graph = _symbol(
        "articles/code-graph-rag.md::Code Graph RAG#section",
        name="Code Graph RAG",
        file_path="articles/code-graph-rag.md",
    )
    fillers = [
        _symbol(
            f"notes/filler-{index}.md::Filler {index}#section",
            name=f"Filler {index}",
            file_path=f"notes/filler-{index}.md",
        )
        for index in range(14)
    ]

    selection = select_graph_anchors(
        [recall, *duplicates, code_graph, *fillers],
        "Did Code Graph RAG improve Recall Efficient Wiki Traversal?",
        [],
        max_anchors=8,
    )

    assert selection.effective_max_anchors == 2
    assert {anchor.node_id for anchor in selection.anchors} == {
        recall["id"],
        code_graph["id"],
    }


def test_one_word_exact_entity_name_is_eligible():
    codex = _symbol(
        "entities/codex.md::Codex#section",
        name="Codex",
        file_path="entities/codex.md",
    )
    unrelated = _symbol(
        "entities/brain.md::Brain#section",
        name="Brain",
        file_path="entities/brain.md",
    )

    selection = select_graph_anchors(
        [codex, unrelated],
        "Codex",
        [],
        max_anchors=8,
    )

    assert [anchor.node_id for anchor in selection.anchors] == [codex["id"]]


def test_templates_are_excluded_from_inference_but_allowed_explicitly():
    template = _symbol(
        "_templates/idea.md::Query Aware Traversal#section",
        name="Query Aware Traversal",
        file_path="_templates/idea.md",
    )

    inferred = select_graph_anchors(
        [template],
        "query aware traversal",
        [],
        max_anchors=8,
    )
    explicit = select_graph_anchors(
        [template],
        "",
        [template["id"]],
        max_anchors=8,
    )

    assert inferred.anchors == ()
    assert [anchor.node_id for anchor in explicit.anchors] == [template["id"]]


def test_inferred_anchor_count_is_strictly_below_ten_percent_for_large_corpus():
    symbols = [
        _symbol(
            f"pages/page-{index}.md::Graph Retrieval {index}#section",
            name=f"Graph Retrieval {index}",
            file_path=f"pages/page-{index}.md",
        )
        for index in range(25)
    ]

    selection = select_graph_anchors(
        symbols,
        "graph retrieval",
        [],
        max_anchors=8,
    )

    assert selection.effective_max_anchors == 2
    assert len(selection.anchors) == 2
    assert len(selection.anchors) / selection.eligible_units < 0.10
    assert selection.omitted_candidates == 23


def test_tiny_corpus_allows_one_inferred_anchor():
    symbol = _symbol(
        "guide.md::Graph Guide#section",
        name="Graph Guide",
        file_path="guide.md",
    )

    selection = select_graph_anchors(
        [symbol],
        "graph guide",
        [],
        max_anchors=8,
    )

    assert selection.effective_max_anchors == 1
    assert len(selection.anchors) == 1


def test_no_qualified_candidate_is_successful_and_deterministic():
    symbol = _symbol(
        "guide.md::Install#section",
        name="Install",
        file_path="guide.md",
    )

    first = select_graph_anchors([symbol], "unrelated question", [], max_anchors=8)
    second = select_graph_anchors([symbol], "unrelated question", [], max_anchors=8)

    assert first.anchors == ()
    assert first == second
