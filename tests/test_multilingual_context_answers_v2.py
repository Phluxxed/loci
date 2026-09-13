"""Future answer contracts clarify representation without donating answer facts."""
from copy import deepcopy
import json
from pathlib import Path

from jsonschema import Draft202012Validator
import pytest

from benchmarks.multilingual_context_answers_v2 import (
    ANSWER_CONTRACT, answer_schema, build_prompt, check_answer, validate_answer,
)
from benchmarks.multilingual_context_compare import build_prompt as legacy_prompt


INPUTS = Path(__file__).parents[1] / "benchmarks/comparisons/multilingual-context-workflow-v1/inputs"
CORPUS = json.loads((INPUTS / "corpus.json").read_text())
CONTROLS = json.loads((INPUTS / "comparison-controls.json").read_text())
CASES = {case["id"]: case for case in CORPUS["cases"]}


@pytest.mark.parametrize("case_id", CASES)
def test_every_case_has_an_explicit_schema_and_preserves_exact_gold(case_id):
    schema = answer_schema(case_id)
    Draft202012Validator.check_schema(schema)
    validator = Draft202012Validator(schema)
    gold = CASES[case_id]["answer"]
    assert validator.is_valid(gold)
    assert validate_answer(case_id, gold)
    assert check_answer(CORPUS, case_id, gold)
    assert set(schema["required"]) == set(gold) == set(schema["properties"])
    assert not check_answer(CORPUS, case_id, {**gold, "unrequested": "value"})
    missing = dict(gold)
    missing.pop(next(iter(missing)))
    assert not check_answer(CORPUS, case_id, missing)
    for field, value in gold.items():
        changed = deepcopy(gold)
        if type(value) is bool:
            changed[field] = not value
        elif isinstance(value, str):
            changed[field] = "wrong" + value
        elif isinstance(value, list):
            changed[field] = value + ["invented.py::Target"]
        elif isinstance(value, dict):
            changed[field]["invented_field"] = "WrongType"
        else:
            changed[field] = value + 1
        assert not check_answer(CORPUS, case_id, changed), field


@pytest.mark.parametrize("case_id", CASES)
def test_prompts_share_answer_contract_without_reading_evaluator_only_facts(case_id):
    before = deepcopy(CORPUS)
    prompts = {arm: build_prompt(CORPUS, CONTROLS, case_id, arm) for arm in ("A", "B")}
    marker = "\n\nAnswer contract " + ANSWER_CONTRACT
    assert prompts["A"].split(marker)[1] == prompts["B"].split(marker)[1]
    assert all(prompts[arm].startswith(legacy_prompt(CORPUS, CONTROLS, case_id, arm)) for arm in prompts)
    poisoned = deepcopy(CORPUS)
    for case in poisoned["cases"]:
        for field in ("answer", "context", "relationships", "forbidden_relationships", "allowed_unresolved"):
            case[field] = "EVALUATOR_ONLY_SECRET"
    assert prompts == {arm: build_prompt(poisoned, CONTROLS, case_id, arm) for arm in ("A", "B")}
    assert CORPUS == before


@pytest.mark.parametrize("path", ["props.ts::Props", "./props.ts", "/props.ts", "../props.ts", "src//props.ts", "src/./props.ts", "src/../props.ts", "props.ts/", "props.ts#class"])
def test_origin_fields_reject_endpoint_and_noncanonical_path_forms(path):
    answer = deepcopy(CASES["tsx_props_control"]["answer"])
    answer["props_origin"] = path
    assert not Draft202012Validator(answer_schema("tsx_props_control")).is_valid(answer)
    assert not validate_answer("tsx_props_control", answer)
    assert not check_answer(CORPUS, "tsx_props_control", answer)


@pytest.mark.parametrize("endpoint", ["src/lib.rs", "caller", "src/lib.rs::caller#function", "./src/lib.rs::caller", "src//lib.rs::caller", "src/lib.rs/::caller", "src/lib.rs::", "src/lib.rs::a/b"])
def test_endpoint_fields_require_file_and_qualified_name(endpoint):
    answer = deepcopy(CASES["rust_known_call_impact"]["answer"])
    answer["direct_caller"] = endpoint
    assert not Draft202012Validator(answer_schema("rust_known_call_impact")).is_valid(answer)
    assert not validate_answer("rust_known_call_impact", answer)


def test_maps_arrays_ordered_pairs_and_certainty_keep_distinct_meanings():
    alias = deepcopy(CASES["python_alias_annotation"]["answer"])
    alias["payload_fields"] = ["request_id: str"]
    assert not validate_answer("python_alias_annotation", alias)
    calls = deepcopy(CASES["javascript_known_call_impact"]["answer"])
    calls["direct_callers"].reverse()
    assert not validate_answer("javascript_known_call_impact", calls)
    pair = deepcopy(CASES["go_explicit_embedding"]["answer"])
    pair["struct_embedding"].reverse()
    assert validate_answer("go_explicit_embedding", pair)  # Shape is valid; source fact is wrong.
    assert not check_answer(CORPUS, "go_explicit_embedding", pair)
    optional = deepcopy(CASES["rust_contained_optional_reexport"]["answer"])
    optional["configuration"] = "unconditional"
    assert validate_answer("rust_contained_optional_reexport", optional)
    assert not check_answer(CORPUS, "rust_contained_optional_reexport", optional)
    optional["active_feature_proven"] = "false"
    assert not validate_answer("rust_contained_optional_reexport", optional)


def test_numeric_equality_preserves_existing_json_semantics():
    answer = deepcopy(CASES["markdown_section_control"]["answer"])
    answer["budget_bytes"] = 8192.0
    assert check_answer(CORPUS, "markdown_section_control", answer)
    for invalid in (True, "8192", float("inf"), 8192.5):
        answer["budget_bytes"] = invalid
        assert not validate_answer("markdown_section_control", answer)


def test_unknown_cases_cannot_silently_omit_contracts():
    with pytest.raises(ValueError, match="No multilingual-exact-answer-v2 schema"):
        answer_schema("future_case_without_contract")
