"""Evaluator-only multilingual corpus/control view with a legacy ledger bridge."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from benchmarks.typescript_context_baseline import sha
from benchmarks.typescript_context_corpus import (
    load_controls as _legacy_load_controls,
    load_corpus as _legacy_load_corpus,
)


def load_controls(corpus: dict[str, Any]) -> dict[str, Any]:
    """Validate W4.1 identity, then provide only an in-memory legacy alias.

    W4.1 intentionally calls its source identity ``starting_implementation``.
    The pre-existing generic ledger calls it ``baseline_engine``.  No corpus
    file is changed: the alias exists only on the in-process dictionary passed
    to legacy adapter and trace validation.
    """

    root = Path(corpus["_root"])
    starting = corpus.get("starting_implementation")
    if not isinstance(starting, dict) or not all(isinstance(starting.get(key), str) and starting[key]
                                                  for key in ("repository", "commit")):
        raise ValueError("multilingual corpus is missing its W4.1 starting implementation identity")
    raw = (root / "comparison-controls.json").read_bytes()
    if sha(raw) != (root / "comparison-controls.sha256").read_text(encoding="utf-8").strip():
        raise ValueError("multilingual comparison controls hash mismatch")
    controls = json.loads(raw)
    if controls.get("schema_version") != 1:
        raise ValueError("unsupported multilingual comparison controls schema")
    if (controls.get("corpus_sha256") != sha((root / "corpus.json").read_bytes())
            or controls.get("corpus_version") != corpus.get("version")):
        raise ValueError("multilingual controls do not bind this corpus")
    if controls.get("case_ids") != [case["id"] for case in corpus.get("cases", [])]:
        raise ValueError("multilingual controls case order differs from W4.1")
    engine = controls.get("baseline_engine")
    if not isinstance(engine, dict) or not engine:
        raise ValueError("multilingual controls must pin the final W4.6 engine")
    protocol = controls.get("protocol")
    if not isinstance(protocol, dict) or not isinstance(protocol.get("file"), str) or not isinstance(protocol.get("sha256"), str):
        raise ValueError("multilingual controls lack a protocol identity")
    protocol_path = (root / protocol["file"]).resolve()
    if not protocol_path.is_relative_to(root) or not protocol_path.is_file() or sha(protocol_path.read_bytes()) != protocol["sha256"]:
        raise ValueError("multilingual controls protocol identity differs")
    corpus["baseline_engine"] = engine
    return _legacy_load_controls(corpus)


def load_inputs(root: Path | None = None) -> tuple[dict[str, Any], dict[str, Any]]:
    """Load the immutable corpus and evaluator-only controls view."""

    if root is None:
        root = Path(__file__).resolve().parent / "comparisons" / "multilingual-context-workflow-v1" / "inputs"
    corpus = _legacy_load_corpus(Path(root))
    if corpus.get("version") != "multilingual-context-v1" or len(corpus.get("cases", [])) != 19:
        raise ValueError("multilingual evaluator view has an unexpected corpus")
    return corpus, load_controls(corpus)


__all__ = ["load_controls", "load_inputs"]
