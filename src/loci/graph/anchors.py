from __future__ import annotations

import math
import re
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Any, Literal, Mapping, Sequence

from .contracts import GraphContractError


MAX_GRAPH_QUESTION_BYTES = 16_384
MAX_GRAPH_QUERY_TERMS = 32
MAX_GRAPH_ANCHORS = 32
_MAX_MATCH_SCOPES = 32
_MAX_SCORED_TERMS = 4
_TOKEN_RE = re.compile(r"[a-z0-9]+")
_STOP_WORDS = frozenset(
    {
        "a",
        "an",
        "and",
        "are",
        "as",
        "at",
        "be",
        "been",
        "by",
        "can",
        "could",
        "did",
        "do",
        "does",
        "evidence",
        "exact",
        "for",
        "from",
        "had",
        "has",
        "have",
        "how",
        "if",
        "in",
        "into",
        "is",
        "it",
        "its",
        "may",
        "measured",
        "of",
        "on",
        "or",
        "propose",
        "prove",
        "proven",
        "related",
        "result",
        "should",
        "show",
        "source",
        "support",
        "that",
        "the",
        "their",
        "then",
        "there",
        "these",
        "they",
        "this",
        "those",
        "to",
        "use",
        "was",
        "were",
        "what",
        "when",
        "where",
        "which",
        "who",
        "why",
        "will",
        "with",
        "would",
    }
)
_HIGH_SIGNAL_SCOPES = frozenset(
    {
        "file_basename",
        "symbol_name",
        "qualified_name",
        "page_frontmatter.title",
        "page_frontmatter.tags",
    }
)


@dataclass(frozen=True, slots=True)
class GraphAnchor:
    node_id: str
    matched_symbol_id: str
    name: str
    score: float | None
    matched_terms: tuple[str, ...]
    match_scope: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class GraphAnchorSelection:
    mode: Literal["explicit", "inferred"]
    anchors: tuple[GraphAnchor, ...]
    question_terms: tuple[str, ...]
    eligible_units: int
    qualified_candidates: int
    collapsed_symbols: int
    requested_max_anchors: int
    effective_max_anchors: int
    omitted_candidates: int


@dataclass(slots=True)
class _AnchorUnit:
    key: tuple[str, str]
    file_path: str
    symbols: list[Mapping[str, Any]]
    all_terms: set[str]


@dataclass(frozen=True, slots=True)
class _ScoredSymbol:
    symbol: Mapping[str, Any]
    score: float
    matched_terms: tuple[str, ...]
    match_scope: tuple[str, ...]
    high_signal: bool


def select_graph_anchors(
    symbols: Sequence[Mapping[str, Any]],
    question: str,
    seed_ids: Sequence[str],
    *,
    max_anchors: int,
) -> GraphAnchorSelection:
    """Select exact seeds or a bounded, explained set of inferred graph anchors."""
    _validate_request(question, seed_ids, max_anchors)
    indexed = {
        symbol_id: symbol
        for symbol in symbols
        if isinstance((symbol_id := symbol.get("id")), str) and symbol_id
    }
    unique_seeds = tuple(dict.fromkeys(seed_ids))
    if unique_seeds:
        return _select_explicit(indexed, unique_seeds, max_anchors)

    question_terms = _question_terms(question)
    units, eligible_symbols = _anchor_units(symbols)
    collapsed_symbols = max(0, eligible_symbols - len(units))
    effective_max = min(max_anchors, _corpus_anchor_cap(len(units)))
    if not question_terms or not units:
        return GraphAnchorSelection(
            mode="inferred",
            anchors=(),
            question_terms=question_terms,
            eligible_units=len(units),
            qualified_candidates=0,
            collapsed_symbols=collapsed_symbols,
            requested_max_anchors=max_anchors,
            effective_max_anchors=effective_max,
            omitted_candidates=0,
        )

    document_frequency = {
        term: sum(term in unit.all_terms for unit in units)
        for term in question_terms
    }
    canonical_markdown_roots = _canonical_markdown_roots(indexed)
    scored_units: list[tuple[float, str, str, GraphAnchor]] = []
    for unit in units:
        scored = _score_unit(
            unit,
            question_terms,
            document_frequency,
            corpus_size=len(units),
        )
        if scored is None:
            continue
        node = _anchor_node(
            scored.symbol,
            indexed,
            canonical_markdown_roots,
        )
        node_id = str(node["id"])
        file_path = str(node.get("file_path") or unit.file_path)
        anchor = GraphAnchor(
            node_id=node_id,
            matched_symbol_id=str(scored.symbol["id"]),
            name=str(node.get("name") or scored.symbol.get("name") or node_id),
            score=round(scored.score, 3),
            matched_terms=scored.matched_terms,
            match_scope=scored.match_scope,
        )
        scored_units.append((-scored.score, file_path, node_id, anchor))

    scored_units.sort(key=lambda item: item[:3])
    qualified = len(scored_units)
    anchors = tuple(item[3] for item in scored_units[:effective_max])
    return GraphAnchorSelection(
        mode="inferred",
        anchors=anchors,
        question_terms=question_terms,
        eligible_units=len(units),
        qualified_candidates=qualified,
        collapsed_symbols=collapsed_symbols,
        requested_max_anchors=max_anchors,
        effective_max_anchors=effective_max,
        omitted_candidates=max(0, qualified - len(anchors)),
    )


def _validate_request(
    question: str,
    seed_ids: Sequence[str],
    max_anchors: int,
) -> None:
    if not isinstance(question, str):
        raise _error("Graph question must be a string", field="question")
    question_bytes = len(question.encode("utf-8"))
    if question_bytes > MAX_GRAPH_QUESTION_BYTES:
        raise _error(
            "Graph question exceeds the byte limit",
            field="question",
            bytes=question_bytes,
            max_bytes=MAX_GRAPH_QUESTION_BYTES,
        )
    if (
        not isinstance(max_anchors, int)
        or isinstance(max_anchors, bool)
        or not 1 <= max_anchors <= MAX_GRAPH_ANCHORS
    ):
        raise _error(
            "Graph anchor limit must be between 1 and 32",
            field="max_anchors",
            max_anchors=max_anchors,
        )
    if not isinstance(seed_ids, Sequence) or isinstance(seed_ids, (str, bytes)):
        raise _error("Graph seeds must be a list of strings", field="seed_ids")
    if any(not isinstance(seed_id, str) or not seed_id for seed_id in seed_ids):
        raise _error("Graph seeds must be non-empty strings", field="seed_ids")
    unique_seeds = tuple(dict.fromkeys(seed_ids))
    if len(unique_seeds) > max_anchors:
        raise _error(
            "Explicit graph seeds exceed the anchor limit",
            field="seed_ids",
            seed_count=len(unique_seeds),
            max_anchors=max_anchors,
        )
    if not question.strip() and not unique_seeds:
        raise _error(
            "A graph question or explicit seed is required",
            field="question",
        )


def _select_explicit(
    indexed: Mapping[str, Mapping[str, Any]],
    seed_ids: tuple[str, ...],
    max_anchors: int,
) -> GraphAnchorSelection:
    missing_ids = [seed_id for seed_id in seed_ids if seed_id not in indexed]
    if missing_ids:
        raise GraphContractError(
            "GRAPH_ENDPOINT_NOT_FOUND",
            "Graph seed is not indexed",
            {"missing_ids": missing_ids},
        )
    anchors = tuple(
        GraphAnchor(
            node_id=seed_id,
            matched_symbol_id=seed_id,
            name=str(indexed[seed_id].get("name") or seed_id),
            score=None,
            matched_terms=(),
            match_scope=(),
        )
        for seed_id in seed_ids
    )
    units, eligible_symbols = _anchor_units(tuple(indexed.values()))
    return GraphAnchorSelection(
        mode="explicit",
        anchors=anchors,
        question_terms=(),
        eligible_units=len(units),
        qualified_candidates=len(anchors),
        collapsed_symbols=max(0, eligible_symbols - len(units)),
        requested_max_anchors=max_anchors,
        effective_max_anchors=max_anchors,
        omitted_candidates=0,
    )


def _question_terms(question: str) -> tuple[str, ...]:
    terms: list[str] = []
    seen: set[str] = set()
    for raw_term in _TOKEN_RE.findall(question.casefold()):
        term = _normalize_term(raw_term)
        if len(term) < 2 or term in _STOP_WORDS or term in seen:
            continue
        terms.append(term)
        seen.add(term)
        if len(terms) == MAX_GRAPH_QUERY_TERMS:
            break
    return tuple(terms)


def _anchor_units(
    symbols: Sequence[Mapping[str, Any]],
) -> tuple[list[_AnchorUnit], int]:
    grouped: dict[tuple[str, str], _AnchorUnit] = {}
    eligible_symbols = 0
    for symbol in symbols:
        symbol_id = symbol.get("id")
        file_path = symbol.get("file_path")
        if not isinstance(symbol_id, str) or not symbol_id:
            continue
        if not isinstance(file_path, str) or not file_path:
            continue
        if _is_template_path(file_path):
            continue
        eligible_symbols += 1
        if symbol.get("language") == "markdown":
            key = ("markdown", file_path)
        else:
            key = ("symbol", symbol_id)
        unit = grouped.get(key)
        if unit is None:
            unit = _AnchorUnit(key, file_path, [], set())
            grouped[key] = unit
        unit.symbols.append(symbol)
        unit.all_terms.update(_symbol_terms(symbol))
    return [grouped[key] for key in sorted(grouped)], eligible_symbols


def _score_unit(
    unit: _AnchorUnit,
    question_terms: tuple[str, ...],
    document_frequency: Mapping[str, int],
    *,
    corpus_size: int,
) -> _ScoredSymbol | None:
    best: _ScoredSymbol | None = None
    for symbol in unit.symbols:
        scored = _score_symbol(
            symbol,
            question_terms,
            document_frequency,
            corpus_size=corpus_size,
        )
        if scored is None:
            continue
        if best is None or _scored_symbol_key(scored) < _scored_symbol_key(best):
            best = scored
    return best


def _score_symbol(
    symbol: Mapping[str, Any],
    question_terms: tuple[str, ...],
    document_frequency: Mapping[str, int],
    *,
    corpus_size: int,
) -> _ScoredSymbol | None:
    fields = _search_fields(symbol)
    contributions: dict[str, float] = {}
    scopes: list[str] = []
    high_signal = False
    phrase_bonus = 0.0
    question_pairs = set(zip(question_terms, question_terms[1:]))

    for scope, text, weight in fields:
        tokens = _tokens(text)
        if not tokens:
            continue
        token_set = set(tokens)
        hits = [term for term in question_terms if term in token_set]
        if not hits:
            continue
        if scope not in scopes and len(scopes) < _MAX_MATCH_SCOPES:
            scopes.append(scope)
        if scope in _HIGH_SIGNAL_SCOPES:
            high_signal = True
        field_coverage = len(hits) / max(1, len(token_set))
        density = 0.35 + (0.65 * field_coverage * field_coverage)
        for term in hits:
            specificity = _specificity(
                document_frequency.get(term, corpus_size),
                corpus_size,
            )
            contribution = weight * specificity * density
            contributions[term] = max(contributions.get(term, 0.0), contribution)
        if scope in _HIGH_SIGNAL_SCOPES and question_pairs:
            field_pairs = set(zip(tokens, tokens[1:]))
            matched_pairs = question_pairs & field_pairs
            if matched_pairs:
                phrase_bonus = max(
                    phrase_bonus,
                    weight * 2.0,
                )

    matched_terms = tuple(term for term in question_terms if term in contributions)
    if not matched_terms or (not high_signal and len(matched_terms) < 2):
        return None
    coverage = min(len(matched_terms), _MAX_SCORED_TERMS) / len(question_terms)
    strongest_terms = sorted(contributions.values(), reverse=True)[:_MAX_SCORED_TERMS]
    score = (sum(strongest_terms) + phrase_bonus) * (1.0 + 0.25 * coverage)
    return _ScoredSymbol(
        symbol=symbol,
        score=score,
        matched_terms=matched_terms,
        match_scope=tuple(scopes),
        high_signal=high_signal,
    )


def _search_fields(symbol: Mapping[str, Any]) -> list[tuple[str, str, float]]:
    file_path = str(symbol.get("file_path") or "")
    basename = PurePosixPath(file_path).stem if file_path else ""
    fields = [
        ("file_basename", basename, 8.0),
        ("file_path", file_path, 3.0),
        ("symbol_name", str(symbol.get("name") or ""), 7.0),
        ("qualified_name", str(symbol.get("qualified_name") or ""), 5.0),
        ("signature", str(symbol.get("signature") or ""), 3.0),
        ("summary", str(symbol.get("summary") or ""), 2.0),
        ("docstring", str(symbol.get("docstring") or ""), 1.5),
        ("keywords", " ".join(_string_values(symbol.get("keywords"))), 4.0),
    ]
    metadata = symbol.get("metadata")
    frontmatter = metadata.get("frontmatter") if isinstance(metadata, Mapping) else None
    if isinstance(frontmatter, Mapping):
        for key in sorted(frontmatter):
            values = _string_values(frontmatter[key])
            if not values:
                continue
            if key == "title":
                weight = 7.0
            elif key == "tags":
                weight = 5.0
            elif key == "description":
                weight = 4.0
            elif key == "source":
                weight = 4.0
            else:
                weight = 3.0
            fields.append((f"page_frontmatter.{key}", " ".join(values), weight))
    return fields


def _symbol_terms(symbol: Mapping[str, Any]) -> set[str]:
    terms: set[str] = set()
    for _scope, text, _weight in _search_fields(symbol):
        terms.update(_tokens(text))
    return terms


def _anchor_node(
    matched: Mapping[str, Any],
    indexed: Mapping[str, Mapping[str, Any]],
    canonical_markdown_roots: Mapping[str, Mapping[str, Any]],
) -> Mapping[str, Any]:
    if matched.get("language") != "markdown":
        return matched
    file_path = matched.get("file_path")
    if isinstance(file_path, str) and file_path in canonical_markdown_roots:
        return canonical_markdown_roots[file_path]
    metadata = matched.get("metadata")
    markdown = metadata.get("markdown") if isinstance(metadata, Mapping) else None
    root_id = markdown.get("root_id") if isinstance(markdown, Mapping) else None
    root = indexed.get(root_id) if isinstance(root_id, str) else None
    if root is not None and root.get("file_path") == matched.get("file_path"):
        return root
    return matched


def _canonical_markdown_roots(
    indexed: Mapping[str, Mapping[str, Any]],
) -> dict[str, Mapping[str, Any]]:
    roots: dict[str, Mapping[str, Any]] = {}
    for symbol in indexed.values():
        if symbol.get("language") != "markdown":
            continue
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
        if current is None or _markdown_root_key(symbol) < _markdown_root_key(current):
            roots[file_path] = symbol
    return roots


def _markdown_root_key(symbol: Mapping[str, Any]) -> tuple[int, int, str]:
    line = symbol.get("line")
    byte_offset = symbol.get("byte_offset")
    return (
        line if isinstance(line, int) and not isinstance(line, bool) else 0,
        byte_offset
        if isinstance(byte_offset, int) and not isinstance(byte_offset, bool)
        else 0,
        str(symbol.get("id") or ""),
    )


def _tokens(text: str) -> tuple[str, ...]:
    return tuple(
        term
        for raw_term in _TOKEN_RE.findall(text.casefold())
        if len((term := _normalize_term(raw_term))) >= 2
    )


def _normalize_term(term: str) -> str:
    if len(term) > 4 and term.endswith("ies"):
        return term[:-3] + "y"
    if (
        len(term) > 4
        and term.endswith("s")
        and not term.endswith(("ss", "us", "is"))
    ):
        return term[:-1]
    return term


def _string_values(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        return [item for item in value if isinstance(item, str)]
    if isinstance(value, (bool, int, float)):
        return [str(value)]
    return []


def _specificity(document_frequency: int, corpus_size: int) -> float:
    return 1.0 + math.log((corpus_size + 1) / (document_frequency + 1))


def _corpus_anchor_cap(eligible_units: int) -> int:
    if eligible_units < 11:
        return 1
    return max(1, (eligible_units - 1) // 10)


def _scored_symbol_key(scored: _ScoredSymbol) -> tuple[float, str]:
    return (-scored.score, str(scored.symbol.get("id") or ""))


def _is_template_path(file_path: str) -> bool:
    return "_templates" in PurePosixPath(file_path).parts


def _error(message: str, **details: Any) -> GraphContractError:
    return GraphContractError("INVALID_INPUT", message, details)
