from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from types import SimpleNamespace

import pytest

from benchmarks.graph_anchor_stage3 import load_contract
from benchmarks.graph_traversal_stage4 import (
    WikiRuntime,
    deterministic_digest,
    prepare_wiki_mirror,
    score_fixture,
    summarize,
)
from loci.service import get_store


FROZEN = Path(
    "/Users/brummerv/llm-wiki/tests/fixtures/graph_shape_traversal_stage3.json"
)


def test_frozen_contract_is_unchanged_and_contains_all_ten_fixtures():
    contract = load_contract(FROZEN)

    assert len(contract["fixtures"]) == 10
    assert hashlib.sha256(FROZEN.read_bytes()).hexdigest() == (
        "c52def1bdf592ad735149d199910f74183598eccd9ccf8064335fa0cd0e84e27"
    )


def test_temporary_adapter_persists_exact_body_link_evidence(
    tmp_path: Path,
    monkeypatch,
):
    monkeypatch.setenv("LOCI_BASE_DIR", str(tmp_path / "cache"))
    source = tmp_path / "source"
    source.mkdir()
    (source / "a.md").write_text(
        "# Alpha\n\nAlpha supports [Beta](b.md).\n",
        encoding="utf-8",
    )
    (source / "b.md").write_text("# Beta\n", encoding="utf-8")
    pages = {
        "a.md": SimpleNamespace(text=(source / "a.md").read_text()),
        "b.md": SimpleNamespace(text=(source / "b.md").read_text()),
    }
    runtime = WikiRuntime(
        collect_pages=lambda _root: pages,
        collect_typed_edges=lambda _pages: [
            SimpleNamespace(source="a.md", target="b.md", type="body_link")
        ],
        body_link_re=re.compile(r"\[[^\]]+\]\(([^)#\s]+\.md)\)"),
        resolve_link=lambda raw, _source, targets: raw if raw in targets else None,
    )

    result = prepare_wiki_mirror(source, tmp_path / "mirror", runtime)
    loaded = get_store().load(result["root"])

    assert result["pages"] == 2
    assert result["edges"] == 1
    assert loaded is not None
    edge = next(
        edge for edge in loaded["graph"]["edges"]
        if edge["namespace"] == "llm-wiki"
    )
    assert edge["evidence"]["file"] == "a.md"
    assert edge["evidence"]["line"] == 3
    assert edge["evidence"]["content_hash"] == hashlib.sha256(
        (source / "a.md").read_bytes()
    ).hexdigest()


def test_temporary_adapter_rejects_page_paths_outside_the_source(
    tmp_path: Path,
):
    source = tmp_path / "source"
    source.mkdir()
    outside = tmp_path / "outside.md"
    outside.write_text("# Outside\n", encoding="utf-8")
    runtime = WikiRuntime(
        collect_pages=lambda _root: {
            "../outside.md": SimpleNamespace(text="# Outside\n")
        },
        collect_typed_edges=lambda _pages: [],
        body_link_re=re.compile(r"\[[^\]]+\]\(([^)#\s]+\.md)\)"),
        resolve_link=lambda _raw, _source, _targets: None,
    )

    with pytest.raises(ValueError, match="canonical wiki page is unsafe"):
        prepare_wiki_mirror(source, tmp_path / "mirror", runtime)


def test_fixture_scoring_separates_selected_and_rejected_paths():
    fixture = {
        "id": "T1",
        "corpus": "test",
        "shape": "false_hub_shortcut",
        "question": "question",
        "expected_pages": ["a.md", "c.md"],
        "bridge_paths_any": [],
        "forbidden_paths": [["a.md", "hub.md", "c.md"]],
    }
    response = {
        "anchors": [
            {"node": {"attributes": {"file": "a.md"}}},
            {"node": {"attributes": {"file": "c.md"}}},
        ],
        "paths": [],
        "rejected_paths": [{
            "nodes": [
                "a.md::Alpha#section",
                "hub.md::Hub#section",
                "c.md::Gamma#section",
            ],
            "reason": "HUB_SHORTCUT",
        }],
        "counts": {},
        "budget": {
            "evidence_bytes": 0,
            "max_evidence_bytes": 1024,
            "estimated_tokens": 0,
            "max_estimated_tokens": 256,
        },
        "diagnostics": [],
        "routing": {"kind": "relationship"},
    }

    scored = score_fixture(fixture, response, latency_ms=4.2)

    assert scored["score"]["forbidden_path_selected"] is False
    assert scored["score"]["false_path_rejection_observed"] is True
    assert scored["rejection_reasons"] == ["HUB_SHORTCUT"]
    assert scored["score"]["endpoint_recall"] == 1.0


def test_summary_reports_positive_false_path_cost_and_evidence_metrics():
    fixtures = [
        {
            "expected_pages": ["a.md", "b.md"],
            "shape": "direct_relation",
            "score": {
                "endpoint_hits": ["a.md", "b.md"],
                "required_path_selected": True,
                "forbidden_path_selected": False,
                "false_path_rejection_observed": False,
                "selected_path_precision": 1.0,
                "rejected_path_precision": None,
                "serialized_rejections": 0,
                "hub_shortcut_rejections": 0,
                "evidence_complete": True,
                "response_bytes": 400,
                "estimated_response_tokens": 100,
            },
            "budget": {
                "evidence_bytes": 40,
                "max_evidence_bytes": 1024,
                "estimated_tokens": 10,
                "max_estimated_tokens": 256,
            },
            "latency_ms": 2.0,
        },
        {
            "expected_pages": ["c.md", "d.md"],
            "shape": "false_hub_shortcut",
            "score": {
                "endpoint_hits": ["c.md", "d.md"],
                "required_path_selected": None,
                "forbidden_path_selected": False,
                "false_path_rejection_observed": True,
                "selected_path_precision": 1.0,
                "rejected_path_precision": 1.0,
                "serialized_rejections": 1,
                "hub_shortcut_rejections": 1,
                "evidence_complete": True,
                "response_bytes": 200,
                "estimated_response_tokens": 50,
            },
            "budget": {
                "evidence_bytes": 0,
                "max_evidence_bytes": 1024,
                "estimated_tokens": 0,
                "max_estimated_tokens": 256,
            },
            "latency_ms": 4.0,
        },
    ]

    summary = summarize(fixtures)

    assert summary["endpoint_recall"] == 1.0
    assert summary["positive_paths_selected"] == 1
    assert summary["forbidden_paths_selected"] == 0
    assert summary["false_path_rejections_observed"] == 1
    assert summary["mean_rejected_path_precision"] == 1.0
    assert summary["hub_shortcut_rejection_rate"] == 1.0
    assert summary["all_selected_evidence_complete"] is True
    assert summary["mean_latency_ms"] == 3.0


def test_deterministic_digest_excludes_roots_and_latency():
    first = {
        "roots": {"wiki": "/one"},
        "fixtures": [{"id": "T1", "latency_ms": 1.0}],
        "summary": {"mean_latency_ms": 1.0, "endpoint_recall": 1.0},
    }
    second = {
        "roots": {"wiki": "/two"},
        "fixtures": [{"id": "T1", "latency_ms": 999.0}],
        "summary": {"mean_latency_ms": 999.0, "endpoint_recall": 1.0},
    }

    assert deterministic_digest(first) == deterministic_digest(second)


def test_production_graph_code_does_not_contain_frozen_gold_identifiers():
    production = "\n".join(
        path.read_text(encoding="utf-8")
        for path in sorted((Path("src/loci")).rglob("*.py"))
    )

    assert "AI-D1" not in production
    assert "BR-F1" not in production
    assert "ai_graph_ideas" not in production
    assert "faithfulness-before-connectivity-graph-construction.md" not in production
