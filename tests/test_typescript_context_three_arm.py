"""The matched schedule and pinned-source boundary must fail closed."""

from copy import deepcopy

import pytest

from benchmarks.typescript_context_corpus import load_controls, load_corpus
from benchmarks.typescript_context_three_arm import (
    CORPUS_ROOT, engine_environment, materialize_engine, schedule, source_identity, verify_engine,
)


def test_schedule_has_every_rotated_matched_block_once():
    corpus = load_corpus(CORPUS_ROOT)
    controls = load_controls(corpus)
    plan = schedule(corpus, controls)
    assert len(plan) == len({item["attempt_id"] for item in plan}) == 153
    for offset in range(0, 153, 9):
        block = plan[offset:offset + 9]
        assert len({item["case_id"] for item in block}) == 1
        assert [item["arm"] for item in block] == list("ABCBCACAB")
        assert [item["repetition"] for item in block] == [1] * 3 + [2] * 3 + [3] * 3
    changed = deepcopy(controls)
    changed["schedule"]["concurrency"] = 2
    with pytest.raises(ValueError, match="schedule changed"):
        schedule(corpus, changed)


def test_engine_exports_match_distinct_pins_and_reject_contamination(tmp_path):
    sources = {arm: materialize_engine(source_identity(arm), tmp_path) for arm in "ABC"}
    assert b"EXTRACTOR_VERSION = 24" in (sources["A"] / "loci/storage/index_store.py").read_bytes()
    assert b"EXTRACTOR_VERSION = 24" in (sources["B"] / "loci/storage/index_store.py").read_bytes()
    assert b"EXTRACTOR_VERSION = 25" in (sources["C"] / "loci/storage/index_store.py").read_bytes()
    assert not (sources["A"] / "loci/type_context.py").exists()
    assert (sources["B"] / "loci/type_context.py").exists()
    assert not (sources["B"] / "loci/graph/type_relations.py").exists()
    assert (sources["C"] / "loci/graph/type_relations.py").exists()
    target = sources["B"] / "loci/service.py"
    target.write_bytes((sources["C"] / "loci/service.py").read_bytes())
    with pytest.raises(ValueError, match="differs from its pinned commit"):
        verify_engine(source_identity("B"), sources["B"])


def test_engine_source_precedes_ambient_pythonpath(tmp_path, monkeypatch):
    monkeypatch.setenv("PYTHONPATH", "/ambient/current/source")
    selected = tmp_path / "selected-source"
    environment = engine_environment(selected)
    assert environment["PYTHONPATH"].split(":")[0] == str(selected.resolve())
    assert "/ambient/current/source" not in environment["PYTHONPATH"]
    assert environment["PYTHONDONTWRITEBYTECODE"] == "1"
