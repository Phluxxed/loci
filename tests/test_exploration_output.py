from __future__ import annotations

import json
import math

import pytest

from loci._exploration_output import Bundle, Relation, Span, pack_exploration


HASH = "a" * 64


def _base(*, output=4096, evidence=2048, omissions=None):
    return {
        "schema_version": 1, "intent": "type_dependencies", "selection": "explicit",
        "scope": {"source": "indexed_supported_source", "coverage": "partial",
                  "relationships": "authored_types", "exhaustive": False},
        "limits": {"max_hops": 3, "max_output_bytes": output, "max_evidence_bytes": evidence},
        "usage": {"nodes_examined": 7}, "omissions": omissions or [],
    }


def _span(content="type A = B;\n", start=0, *, file="a.ts"):
    return Span(file, start, start + len(content.encode()), 1, 1 + content.count("\n"), HASH, content)


def _bundle(item_id="a.ts::A#type", *, role="anchor", depth=0, sources=None, relations=()):
    return Bundle(
        {"id": item_id, "name": item_id.split("::")[-1], "kind": "type", "file": "a.ts",
         "role": role, "depth": depth, "why": "selected"},
        tuple(sources or (_span(),)), tuple(relations),
    )


def _bytes(response):
    return len(json.dumps({"content": [], "structuredContent": response, "isError": False},
                          ensure_ascii=False, separators=(",", ":")).encode())


def test_packs_exact_envelope_and_non_ascii_utf8_usage():
    result = pack_exploration(_base(), [_bundle(sources=(_span("type Café = string;\n"),))])
    assert result["status"] == "ok"
    assert result["items"][0]["source_id"] == 1
    assert result["usage"]["output_bytes"] == _bytes(result)
    assert result["usage"]["estimated_tokens"] == math.ceil(_bytes(result) / 4)
    assert result["usage"]["evidence_bytes"] == len("type Café = string;\n".encode())


def test_related_bundle_is_atomic_and_requires_delivered_ancestor():
    relation = Relation({"from": "a.ts::A#type", "to": "a.ts::B#type", "type": "uses_type"},
                        "forward", (_span("A", 20),))
    orphan = _bundle("a.ts::B#type", role="dependency", depth=1, relations=(relation,))
    result = pack_exploration(_base(), [orphan])
    assert result["status"] == "empty"
    assert result["items"] == result["relationships"] == result["sources"] == []
    assert result["omissions"] == [{"reason": "ancestor_unavailable", "count": 1}]

    result = pack_exploration(_base(), [_bundle(), orphan])
    assert [item["id"] for item in result["items"]] == ["a.ts::A#type", "a.ts::B#type"]
    assert result["items"][1]["path"] == [1]
    assert result["relationships"][0]["source_ids"] == [2]


def test_contained_sources_reuse_id_and_overlap_counts_union_bytes():
    whole = _span("abcdefghij", 0)
    inner = _span("cdef", 2)
    result = pack_exploration(_base(), [_bundle(sources=(whole,)), _bundle("a.ts::B#type", sources=(inner,))])
    assert result["items"][1]["source_id"] == 1
    assert len(result["sources"]) == 1
    assert result["usage"]["evidence_bytes"] == 10

    left = _span("abcdef", 0)
    right = _span("defghi", 3)
    result = pack_exploration(_base(), [_bundle(sources=(left,)), _bundle("a.ts::B#type", sources=(right,))])
    assert len(result["sources"]) == 2
    assert result["usage"]["evidence_bytes"] == 9


def test_anchor_clips_only_when_full_source_cannot_fit():
    content = "x" * 220 + "\n" + "y" * 1600
    full = _span(content)
    result = pack_exploration(_base(output=2048, evidence=300), [_bundle(sources=(full,))])
    item, source = result["items"][0], result["sources"][0]
    assert item["complete"] is False
    assert source["content"] and len(source["content"].encode()) < len(content.encode())
    assert source["end_byte"] == len(source["content"].encode())
    assert source["content"].endswith("\n")
    assert source["end_line"] == source["start_line"]
    assert result["status"] == "partial"
    assert {item["reason"] for item in result["omissions"]} == {"source_clipped"}
    assert result["usage"]["evidence_bytes"] <= 300
    assert result["usage"]["output_bytes"] <= 2048


def test_related_over_budget_is_not_abbreviated_and_empty_is_honest():
    big = _span("x" * 600)
    relation = Relation({"from": "a.ts::A#type", "to": "a.ts::B#type", "type": "uses_type"},
                        "forward", (_span("proof", 700),))
    result = pack_exploration(_base(evidence=30), [_bundle(), _bundle("a.ts::B#type", role="dependency", depth=1,
        sources=(big,), relations=(relation,))])
    assert len(result["items"]) == 1
    assert result["items"][0]["complete"] is True
    assert result["relationships"] == []
    assert result["omissions"] == [{"reason": "evidence_budget", "count": 1}]
    assert result["status"] == "partial"


def test_malformed_spans_and_base_overflow_fail_loudly():
    bad = Span("a.ts", 0, 1, 1, 1, HASH, "é")
    with pytest.raises(ValueError, match="UTF-8"):
        pack_exploration(_base(), [_bundle(sources=(bad,))])
    with pytest.raises(ValueError, match="base response"):
        pack_exploration(_base(output=1), [])
