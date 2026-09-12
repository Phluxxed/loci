"""Prompt identity and host-audit boundaries for the declared routing policy."""
import copy
import json

import pytest

from benchmarks.typescript_context_corpus import load_controls, load_corpus
from benchmarks.typescript_context_routing import (
    POLICY_PATH, ROOT, audit_request, build_prompt, prompt_manifest,
)


@pytest.fixture
def inputs():
    corpus = load_corpus(ROOT / "benchmarks/corpora/typescript-context-v3")
    return corpus, load_controls(corpus)


def test_every_original_prompt_is_preserved_and_policy_is_case_independent(inputs):
    corpus, controls = inputs
    prefix = POLICY_PATH.read_text(encoding="utf-8") + "\n"
    declaration = prompt_manifest(corpus, controls)
    assert len(declaration["cases"]) == 17
    assert sum(case["initial_route"] == "type_dependencies" for case in declaration["cases"]) == 13
    for case in corpus["cases"]:
        original = controls["agent"]["common_prompt"] + case["prompt"]
        assert build_prompt(corpus, controls, case["id"], "A") == original
        assert build_prompt(corpus, controls, case["id"], "B") == prefix + original
    with pytest.raises(ValueError, match="arm"):
        build_prompt(corpus, controls, corpus["cases"][0]["id"], "C")


def test_both_conditions_audit_the_same_real_host_tool_schema(inputs):
    corpus, controls = inputs
    request = json.loads((ROOT / "benchmarks/comparisons/typescript-context-explore-v2/"
                          "transport-verification-evidence/B_explore_query/effective-request.json").read_text())
    hashes = []
    for arm in ("A", "B"):
        prompt = build_prompt(corpus, controls, "imported_interface", arm)
        actual = copy.deepcopy(request)
        actual["input"][-1]["content"] = [{"type": "input_text", "text": prompt}]
        hashes.append(audit_request(actual, prompt)["canonical_tool_schemas_sha256"])
        with pytest.raises(ValueError, match="prompt differs"):
            audit_request(actual, prompt + "changed")
    expected = json.loads((ROOT / "benchmarks/comparisons/typescript-context-explore-v2/"
                           "transport-verification.json").read_text())["canonical_tool_schemas_sha256"]["B"]
    assert hashes == [expected, expected]


def test_legacy_a_schema_cannot_stand_in_for_routing_control(inputs):
    corpus, controls = inputs
    request = json.loads((ROOT / "benchmarks/comparisons/typescript-context-explore-v2/"
                          "transport-verification-evidence/A_exact_get/effective-request.json").read_text())
    prompt = build_prompt(corpus, controls, "imported_interface", "A")
    request["input"][-1]["content"] = [{"type": "input_text", "text": prompt}]
    with pytest.raises(ValueError, match="tool set"):
        audit_request(request, prompt)
