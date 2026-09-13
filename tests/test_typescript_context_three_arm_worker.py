from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from benchmarks.typescript_context_corpus import _isolated_store, load_corpus, materialize_snapshot
from benchmarks.typescript_context_three_arm_tools import ThreeArmAdapter
from benchmarks.typescript_context_three_arm import source_identity
from benchmarks.typescript_context_three_arm_worker import run_worker
from benchmarks import typescript_context_compare as compare
from loci import service


ROOT = Path(__file__).parents[1]
CORPUS_ROOT = ROOT / "benchmarks/corpora/typescript-context-v3"
ENGINE_ROOT = ROOT


def _run(corpus: dict, root: Path, arm: str, store_root: Path, trace: Path) -> ThreeArmAdapter:
    repo = store_root / f"snapshot-{arm}"
    materialize_snapshot(corpus, "imported_interface", repo)
    service.index_repo(repo, incremental=False)
    return ThreeArmAdapter({
        "repo": str(repo),
        "corpus_root": str(root),
        "case_id": "imported_interface",
        "session_id": f"worker-test-{arm}",
        "arm": arm,
        "repetition": 1,
        "trace_path": str(trace),
    })


@pytest.fixture
def imported_adapters(tmp_path: Path):
    corpus = load_corpus(CORPUS_ROOT)
    with _isolated_store(tmp_path / "store"):
        adapters = {
            arm: _run(corpus, CORPUS_ROOT, arm, tmp_path, tmp_path / f"{arm}.trace.json")
            for arm in ("A", "B", "C")
        }
        yield corpus, adapters


def test_c_get_delivers_w23_type_records_and_keeps_c_identity(imported_adapters) -> None:
    _corpus, adapters = imported_adapters
    result = adapters["C"].read_operation(
        "get", {"symbol_ids": ["consumer.ts::processOrder#function"]}
    ).structured_content

    context = result["type_context"]
    assert context["scope"] == "declared_type_relations"
    assert [item["id"] for item in context["symbols"]] == ["types.ts::Payload#interface"]
    assert {item["edge"]["type"] for item in context["references"]} == {"uses_type"}
    trace = json.loads(Path(adapters["C"].run["trace_path"]).read_text(encoding="utf-8"))
    assert trace["identity"]["arm"] == "C"
    assert trace["deliveries"][0]["status"] == "recorded"
    assert trace["deliveries"][0]["source_bytes"] > 0


def test_a_b_are_inherited_and_expanded_c_spans_are_charged(imported_adapters) -> None:
    _corpus, adapters = imported_adapters
    parameters = {"symbol_ids": ["consumer.ts::processOrder#function"]}
    exact = adapters["A"].read_operation("get", parameters).structured_content
    existing = adapters["B"].read_operation("get", parameters).structured_content
    typed = adapters["C"].read_operation("get", parameters).structured_content

    assert "type_context" not in exact
    assert existing["symbols"] == exact["symbols"]
    assert typed["symbols"] == exact["symbols"]
    assert [item["id"] for item in existing["type_context"]["symbols"]] == ["types.ts::Payload#interface"]
    assert [item["id"] for item in typed["type_context"]["symbols"]] == ["types.ts::Payload#interface"]
    assert json.loads(Path(adapters["A"].run["trace_path"]).read_text())["deliveries"][0]["source_bytes"] < \
        json.loads(Path(adapters["B"].run["trace_path"]).read_text())["deliveries"][0]["source_bytes"]
    assert json.loads(Path(adapters["B"].run["trace_path"]).read_text())["deliveries"][0]["source_bytes"] == \
        json.loads(Path(adapters["C"].run["trace_path"]).read_text())["deliveries"][0]["source_bytes"]

    with pytest.raises(ValueError, match="unknown operation"):
        adapters["C"].dispatch("get", {"symbol_ids": [], "extra": True})
    with pytest.raises(ValueError, match="nonnegative"):
        adapters["C"].dispatch("get", {"symbol_ids": [], "context": -1})
    with pytest.raises(ValueError, match="IDs must belong"):
        adapters["C"].dispatch("get", {"symbol_ids": ["missing#function"]})


def _worker_spec(tmp_path: Path, *, arm: str = "C", engine_src: Path | None = None) -> dict:
    engine = copy.deepcopy(source_identity(arm))
    selected_engine_src = (engine_src or ROOT / "src").resolve()
    return {
        "corpus_root": str(CORPUS_ROOT.resolve()),
        "output": str(tmp_path.resolve()),
        "catalog": str((tmp_path / "catalog.json").resolve()),
        "engine_src": str(selected_engine_src),
        "engine": engine,
        "plan": {
            "attempt_id": f"imported_interface-r1-{arm}",
            "case_id": "imported_interface",
            "snapshot": "imported_interface",
            "repetition": 1,
            "arm": arm,
        },
        "expected_schema_hash": "a" * 64,
        "freeze": {"version": "three-arm-test", "declared": True},
    }


def test_worker_passes_pinned_engine_to_mcp_and_restores_compare_bindings(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    catalog = tmp_path / "catalog.json"
    catalog.write_text("{}\n", encoding="utf-8")
    spec = _worker_spec(tmp_path)
    seen: dict = {}
    original_modules = compare.ARM_MODULES
    original_provenance = compare._source_provenance

    def fake_attempt(**kwargs):
        seen.update(kwargs)
        config = kwargs["settings"](tmp_path / "run.json", Path(spec["catalog"]), tmp_path / "store")
        # Model the overwrite performed by the frozen compare lifecycle.
        config["mcp_servers.evaluation.args"] = [
            "-m", compare.ARM_MODULES["C"], str(tmp_path / "run.json")
        ]
        seen["config"] = config
        return {"attempt_id": spec["plan"]["attempt_id"], "arm": "C", "provenance": {}}

    monkeypatch.setattr(compare, "_run_attempt", fake_attempt)
    result = run_worker(spec)

    assert result["attempt_id"] == "imported_interface-r1-C"
    assert compare.ARM_MODULES is original_modules
    assert compare._source_provenance is original_provenance
    env = seen["config"]["mcp_servers.evaluation.env"]
    assert env["PYTHONPATH"].split(":")[:2] == [str((ROOT / "src").resolve()), str(ROOT.resolve())]
    assert seen["config"]["mcp_servers.evaluation.args"] == [
        "-m", "benchmarks.typescript_context_three_arm_tools", str(tmp_path / "run.json")
    ]
    provenance = result["provenance"]
    assert provenance["source"]["engine"]["arm"] == "C"
    assert provenance["engine_runtime"]["extractor_version"] == 25
    assert provenance["source"]["freeze_commit"] is None
    assert provenance["source"]["source_scope"] == "assigned pinned engine; fixed v3 auto-get comparison"


def test_worker_rejects_engine_source_mismatch_before_attempt(tmp_path: Path, monkeypatch) -> None:
    catalog = tmp_path / "catalog.json"
    catalog.write_text("{}\n", encoding="utf-8")
    spec = _worker_spec(tmp_path, arm="B", engine_src=ROOT / "src")
    called = []

    def must_not_run(**_kwargs):
        called.append(True)
        raise AssertionError("source mismatch must be rejected before execution")

    monkeypatch.setattr(compare, "_run_attempt", must_not_run)
    with pytest.raises(ValueError, match="source differs"):
        run_worker(spec)
    assert called == []
