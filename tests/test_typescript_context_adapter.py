from __future__ import annotations

import json
from pathlib import Path

import pytest

from benchmarks.typescript_context_adapter import Adapter
from benchmarks.typescript_context_corpus import (
    _isolated_store,
    load_corpus,
    materialize_snapshot,
)
from loci.service import index_repo


CORPUS_ROOT = Path(__file__).parents[1] / "benchmarks" / "corpora" / "typescript-context-v1"


@pytest.fixture
def imported_adapter(tmp_path: Path):
    corpus = load_corpus(CORPUS_ROOT)
    repo = tmp_path / "snapshot"
    materialize_snapshot(corpus, "imported_interface", repo)
    cache = tmp_path / "cache"
    trace_path = tmp_path / "trace.json"
    run = {
        "repo": str(repo),
        "corpus_root": str(CORPUS_ROOT),
        "case_id": "imported_interface",
        "session_id": "adapter-imported-interface",
        "arm": "A",
        "repetition": 1,
        "trace_path": str(trace_path),
    }
    with _isolated_store(cache):
        index_repo(repo, incremental=False)
        yield Adapter(run), corpus, run, repo, trace_path


@pytest.fixture
def anvil_adapter(tmp_path: Path):
    corpus = load_corpus(CORPUS_ROOT)
    repo = tmp_path / "snapshot"
    materialize_snapshot(corpus, "anvil", repo)
    cache = tmp_path / "cache"
    trace_path = tmp_path / "trace.json"
    run = {
        "repo": str(repo),
        "corpus_root": str(CORPUS_ROOT),
        "case_id": "anvil_temporal_arguments",
        "session_id": "adapter-anvil-budget",
        "arm": "A",
        "repetition": 1,
        "trace_path": str(trace_path),
    }
    with _isolated_store(cache):
        index_repo(repo, incremental=False)
        yield Adapter(run), corpus, run, repo, trace_path


def _keys(value: object) -> set[str]:
    found: set[str] = set()
    if isinstance(value, dict):
        found.update(str(key) for key in value)
        for child in value.values():
            found.update(_keys(child))
    elif isinstance(value, list):
        for child in value:
            found.update(_keys(child))
    return found


def _assert_agent_result_is_evaluator_free(result: dict, corpus_root: Path) -> None:
    assert str(corpus_root) not in json.dumps(result, ensure_ascii=False)
    assert not _keys(result) & {
        "answer",
        "cases",
        "corpus",
        "gold",
        "required_context",
        "required_context_delivered",
    }


def test_search_get_lineage_and_exact_source_provenance(imported_adapter):
    adapter, corpus, _run_data, _repo, trace_path = imported_adapter

    search = adapter.read(
        "search",
        {"query": "processOrder"},
        "task_context",
        "Locate the processOrder entry point.",
    )
    search_result = search.structured_content
    assert isinstance(search_result, dict)
    _assert_agent_result_is_evaluator_free(search_result, CORPUS_ROOT)
    assert search_result["search_id"]
    symbol = next(item for item in search_result["symbols"] if item["name"] == "processOrder")
    search_event = adapter.trace.events[-1]

    selected = adapter.read(
        "get",
        {
            "symbol_ids": [symbol["id"]],
            "selected_from_search_id": search_result["search_id"],
            "context": 0,
        },
        "missing_context",
        "Hydrate the selected function source.",
        because=search_event["id"],
    )
    selected_result = selected.structured_content
    assert isinstance(selected_result, dict)
    _assert_agent_result_is_evaluator_free(selected_result, CORPUS_ROOT)
    item = selected_result["symbols"][0]
    assert item["id"] == symbol["id"] == "consumer.ts::processOrder#function"
    assert item["source"] == (
        "function processOrder(value: ImportedPayload): string {\n"
        "  return value.requestId;\n"
        "}"
    )

    event = adapter.trace.events[-1]
    assert event["operation"] == "get"
    assert event["because"] == search_event["id"]
    assert event["arguments"]["selected_from_search_id"] == search_result["search_id"]
    assert event["arguments"]["symbol_ids"] == [item["id"]]
    assert len(event["spans"]) == 1
    span = event["spans"][0]
    assert span["file"] == "consumer.ts"
    assert span["start_byte"] == item["byte_offset"]
    assert span["end_byte"] == item["byte_offset"] + len(item["source"].encode())
    assert len(span["sha256"]) == 64
    assert span["text"] == item["source"]
    source = adapter.trace.files["consumer.ts"]
    assert source[span["start_byte"]:span["end_byte"]].decode() == span["text"]
    gold = next(item for item in corpus["cases"] if item["id"] == "imported_interface")["context"]
    entry = next(item for item in gold if item["id"] == "entry")
    assert span["start_byte"] < entry["end_byte"] and entry["start_byte"] < span["end_byte"]
    assert json.loads(trace_path.read_text(encoding="utf-8"))["events"][-1] == event


def test_file_and_grep_count_exact_occurrences_and_repeat_deliveries(imported_adapter):
    adapter, _corpus, _run_data, _repo, _trace_path = imported_adapter

    first_file = adapter.read(
        "file",
        {"file_path": "consumer.ts", "start_line": 1, "end_line": 2},
        "hydration",
        "Read the import and function signature lines.",
    )
    first_file_result = first_file.structured_content
    assert isinstance(first_file_result, dict)
    _assert_agent_result_is_evaluator_free(first_file_result, CORPUS_ROOT)
    first_file_event = adapter.trace.events[-1]
    first_file_bytes = first_file_event["source_bytes"]
    assert first_file_bytes == len(first_file_result["content"].encode())
    assert first_file_event["spans"]

    second_file = adapter.read(
        "file",
        {"file_path": "consumer.ts", "start_line": 1, "end_line": 2},
        "hydration",
        "Repeat the exact source read for accounting coverage.",
    )
    second_file_result = second_file.structured_content
    assert isinstance(second_file_result, dict)
    second_file_event = adapter.trace.events[-1]
    assert second_file_result["content"] == first_file_result["content"]
    assert second_file_event["source_bytes"] == first_file_bytes

    first_grep = adapter.read(
        "grep",
        {"pattern": "Payload"},
        "verification",
        "Verify all source occurrences of the imported type spelling.",
    )
    first_grep_result = first_grep.structured_content
    assert isinstance(first_grep_result, dict)
    _assert_agent_result_is_evaluator_free(first_grep_result, CORPUS_ROOT)
    first_grep_event = adapter.trace.events[-1]
    spans = first_grep_event["spans"]
    assert spans
    delivered_occurrences = []
    for match in first_grep_result["matches"]:
        delivered_occurrences.append((match["file"], match["line"], match["match"]))
        delivered_occurrences.extend(
            (match["file"], match["line"] - len(match.get("context_before", [])) + offset, text)
            for offset, text in enumerate(match.get("context_before", []))
        )
        delivered_occurrences.extend(
            (match["file"], match["line"] + 1 + offset, text)
            for offset, text in enumerate(match.get("context_after", []))
        )
    delivered_occurrences = [item for item in delivered_occurrences if item[2]]
    assert len(spans) == len(delivered_occurrences)
    assert len(delivered_occurrences) > len(set(delivered_occurrences))
    assert first_grep_event["source_bytes"] == sum(
        len(text.encode()) for _file, _line, text in delivered_occurrences
    )

    second_grep = adapter.read(
        "grep",
        {"pattern": "Payload"},
        "verification",
        "Repeat the grep to ensure duplicate delivery is charged.",
    )
    assert isinstance(second_grep.structured_content, dict)
    second_grep_event = adapter.trace.events[-1]
    assert second_grep_event["source_bytes"] == first_grep_event["source_bytes"]
    assert sum(event["source_bytes"] for event in adapter.trace.events) == (
        first_file_bytes * 2
        + first_grep_event["source_bytes"]
        + second_grep_event["source_bytes"]
    )


def test_graph_evidence_is_delivered_with_snapshot_source(imported_adapter):
    adapter, _corpus, _run_data, _repo, _trace_path = imported_adapter

    result = adapter.read(
        "graph_retrieve",
        {
            "question": "What types does processOrder depend on?",
            "seed_ids": ["consumer.ts::__file__#file"],
            "edge_types": ["references_type"],
        },
        "task_context",
        "Inspect the existing imported type relationship.",
    )
    payload = result.structured_content
    assert isinstance(payload, dict)
    _assert_agent_result_is_evaluator_free(payload, CORPUS_ROOT)
    assert payload["paths"]
    path = payload["paths"][0]
    assert path["nodes"][-1]["id"] == "types.ts::Payload#interface"
    evidence = path["steps"][0]["evidence_span"]
    event = adapter.trace.events[-1]
    assert event["operation"] == "graph"
    assert event["spans"]
    assert event["source_bytes"] == sum(
        span["end_byte"] - span["start_byte"] for span in event["spans"]
    )
    assert any(
        span["file"] == evidence["file"] and span["text"] == evidence["content"]
        for span in event["spans"]
    )
    source = adapter.trace.files[evidence["file"]]
    start = sum(len(line) for line in source.splitlines(keepends=True)[:evidence["start_line"] - 1])
    assert source[start:start + len(evidence["content"].encode())].decode() == evidence["content"]


def test_path_escape_is_visible_as_a_bounded_tool_error(imported_adapter):
    adapter, _corpus, _run_data, _repo, trace_path = imported_adapter

    result = adapter.read(
        "file",
        {"file_path": "../consumer.ts", "start_line": 1, "end_line": 1},
        "verification",
        "Check that source paths stay inside the snapshot.",
    )
    payload = result.structured_content
    assert isinstance(payload, dict)
    assert payload["error"]["code"] in {"ValueError", "LociError"}
    assert "content" not in payload
    _assert_agent_result_is_evaluator_free(payload, CORPUS_ROOT)
    event = adapter.trace.events[-1]
    assert event["spans"] == []
    assert event["source_bytes"] == 0
    assert json.loads(trace_path.read_text(encoding="utf-8"))["events"][-1] == event


def test_invalid_selection_lineage_is_retained_as_visible_failure(imported_adapter):
    adapter, _corpus, _run_data, _repo, trace_path = imported_adapter
    search = adapter.read(
        "search",
        {"query": "processOrder"},
        "task_context",
        "Find the function before testing selection lineage.",
    )
    search_event = adapter.trace.events[-1]
    symbol_id = search.structured_content["symbols"][0]["id"]

    with pytest.raises(ValueError, match="selection"):
        adapter.read(
            "get",
            {
                "symbol_ids": [symbol_id],
                "selected_from_search_id": "foreign-search-id",
                "context": 0,
            },
            "missing_context",
            "Attempt a deliberately invalid selected get.",
            because=search_event["id"],
        )

    saved = json.loads(trace_path.read_text(encoding="utf-8"))
    assert saved["events"] == [search_event]
    assert saved["failures"]
    failure = saved["failures"][-1]
    assert failure["category"] == "invalid_trace"
    assert failure["event_id"] == f"{search_event['id'].rsplit(':', 1)[0]}:2"
    assert "selection" in failure["message"]


def test_oversized_result_is_withheld_and_budget_failure_persisted(anvil_adapter):
    adapter, _corpus, _run_data, _repo, trace_path = anvil_adapter

    result = adapter.read(
        "grep",
        {"pattern": "."},
        "task_context",
        "Probe the bounded fallback with a deliberately broad pattern.",
    )
    payload = result.structured_content
    assert isinstance(payload, dict)
    assert payload["error"]["code"] == "BUDGET_EXHAUSTED"
    assert payload["error"]["limits"]
    assert "matches" not in payload
    assert "content" not in payload
    _assert_agent_result_is_evaluator_free(payload, CORPUS_ROOT)

    assert len(adapter.trace.events) == 1
    event = adapter.trace.events[0]
    assert event["operation"] == "grep"
    assert event["spans"] == []
    assert event["source_bytes"] == 0
    assert any(
        failure["category"] == "budget_exhausted" and failure["event_id"] == event["id"]
        for failure in adapter.failures
    )
    saved = json.loads(trace_path.read_text(encoding="utf-8"))
    assert saved["events"] == [event]
    assert saved["failures"] == adapter.failures


def test_adapter_rejects_a_repository_outside_the_materialized_snapshot(tmp_path: Path):
    corpus = load_corpus(CORPUS_ROOT)
    outer = tmp_path / "outer"
    repo = outer / "snapshot"
    materialize_snapshot(corpus, "imported_interface", repo)
    cache = tmp_path / "cache"
    trace_path = tmp_path / "trace.json"
    with _isolated_store(cache):
        index_repo(outer, incremental=False)
    run = {
        "repo": str(outer),
        "corpus_root": str(CORPUS_ROOT),
        "case_id": "imported_interface",
        "session_id": "adapter-invalid-repo",
        "arm": "A",
        "repetition": 1,
        "trace_path": str(trace_path),
    }
    with _isolated_store(cache):
        with pytest.raises(ValueError, match="index|snapshot|repository|boundary"):
            Adapter(run)
