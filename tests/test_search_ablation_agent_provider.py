import importlib.util
import json
from pathlib import Path


SPEC = importlib.util.spec_from_file_location("agent_provider", Path(__file__).resolve().parents[1] / "evals/search_ablation/agent_provider.py")
provider = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(provider)


def events(usage=None):
    message = {"role": "assistant", "model": "model", "provider": "openai-codex", "responseId": "r1",
               "stopReason": "stop", "content": [{"type": "text", "text": "answer"}],
               "usage": usage if usage is not None else {"input": 10, "cacheRead": 20, "cacheWrite": 5, "output": 8, "reasoning": 6, "totalTokens": 43}}
    return [{"type": "message_end", "message": {"role": "system", "toolsAdded": [{"name": "read"}]}},
            {"type": "message_end", "message": message}, {"type": "turn_end", "message": message},
            {"type": "agent_end", "messages": [message]}, {"type": "agent_settled"}]


def test_cumulative_usage_counts_authoritative_responses_once_and_cache_disjoint():
    stream = events()
    stream.insert(2, stream[1])
    result = provider.summarize(stream, "model", ["read"])
    assert result["accounting_complete"]
    assert result["assistant_requests"] == 1
    assert result["usage"]["logical_input"] == 35
    assert result["usage"]["totalTokens"] == 43  # reasoning is already in output
    assert result["usage"]["reasoning"] == 6


def test_missing_zero_and_unreconciled_usage_do_not_pass_as_savings():
    for usage in ({}, {"input": 0, "cacheRead": 0, "cacheWrite": 0, "output": 0, "totalTokens": 0},
                  {"input": 10, "cacheRead": 20, "cacheWrite": 0, "output": 8, "totalTokens": 18}):
        assert not provider.summarize(events(usage), "model", ["read"])["accounting_complete"]


def test_compaction_usage_is_added_and_unknown_failed_consumption_is_visible():
    stream = events()
    stream.insert(2, {"type": "compaction_end", "result": {"usage": stream[1]["message"]["usage"]}})
    result = provider.summarize(stream, "model", ["read"])
    assert result["accounting_complete"]
    assert result["usage"]["totalTokens"] == 86
    stream.insert(2, {"type": "auto_retry_start"})
    assert not provider.summarize(stream, "model", ["read"])["accounting_complete"]


def test_missing_catalog_or_unfinished_tool_is_not_a_qualified_run():
    assert not provider.summarize(events(), "model", ["read", "loci_retrieve"])["accounting_complete"]
    stream = events() + [{"type": "tool_execution_start", "toolCallId": "unfinished", "toolName": "read", "args": {}}]
    assert not provider.summarize(stream, "model", ["read"])["accounting_complete"]


def test_prompt_metric_preserves_original_scores_and_strict_evidence(tmp_path):
    spec = importlib.util.spec_from_file_location("agent_cases", Path(__file__).resolve().parents[1] / "evals/search_ablation/agent_cases.py")
    cases = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cases)
    (tmp_path / "sample.py").write_text("def sample():\n    return True\n")
    case = {"case_id": "sample", "expected_fields": {"symbol": "sample"}, "required_evidence_paths": ["sample.py"],
            "rubric": [{"id": "extra_detail"}]}
    answer = json.dumps({"symbol": "sample", "evidence": [{"path": "sample.py", "start_line": 1, "end_line": 2, "quote": "def sample():"}]})
    review = {"case_id": "sample", "answer_sha256": cases.answer_sha256(answer), "blinded": True, "reviewer": "test-control",
              "claims": {"extra_detail": {"correct_and_supported": False, "reason": "Optional detail omitted"}},
              "no_material_contradictions": True, "prompt_assessment": {"requested_facts_correct": True,
              "requested_evidence_supported": True, "reason": "Requested symbol is defined at the cited source"}}
    assert not cases.grade_answer(case, answer, tmp_path, review)["pass"]
    assert cases.grade_prompt_answer(case, answer, tmp_path, review)["pass"]
    assert not cases.grade_prompt_answer(case, answer + "\n", tmp_path, review)["pass"]
    assert not cases.grade_prompt_answer(case, answer, tmp_path)["pass"]
    for wrong in (answer.replace('"sample"', '"wrong"'), answer.replace('def sample():', 'missing source')):
        rebound = {**review, "answer_sha256": cases.answer_sha256(wrong)}
        assert not cases.grade_prompt_answer(case, wrong, tmp_path, rebound)["pass"]
