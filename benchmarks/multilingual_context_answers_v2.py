"""Authored, answer-free contracts for future multilingual exact scoring.

Legacy corpus prompts and scores remain unchanged. These contracts describe
representation only; values still require source and strict evaluator equality.
"""
from __future__ import annotations

import json
import math
from pathlib import PurePosixPath
import re
from typing import Any

from benchmarks.multilingual_context_compare import build_prompt as legacy_build_prompt
from benchmarks.typescript_context_corpus import check_answer as legacy_check_answer

PROTOCOL = "multilingual-context-workflow-v2"
ANSWER_CONTRACT = "multilingual-exact-answer-v2"
_PATH_PATTERN = r"^(?!/)(?!.*//)(?!.*\/$)(?!.*(?:^|/)\.{1,2}(?:/|$))[^\\:#\s]+$"
_ENDPOINT_PATTERN = r"^(?!/)(?!.*//)(?!.*(?:^|/)\.{1,2}(?:/|$))[^\\:#\s/](?:[^\\:#\s]*[^\\:#\s/])?::[^/\\:#\s]+$"

# Authored from task semantics, never inferred from expected answer values.
# Every key is already named by the corresponding model-visible task prompt.
_FIELDS: dict[str, dict[str, str]] = {
    "python_alias_annotation": dict(function_file="path", alias_rhs="string", payload_origin="path", payload_fields="fields", authored_return="string"),
    "python_base_and_literal_forward": dict(direct_base="string", base_origin="path", base_fields="fields", literal_forward_target="endpoint", mro_computed="boolean"),
    "python_known_call_impact": dict(target_file="path", caller_file="path", caller_name="string", local_import_name="string", edge_direction="pair"),
    "python_unproven_contracts": dict(exact_repository_targets="endpoints", generic_P_is_imported_payload="boolean", compound_string_supported="boolean", runtime_evaluation_allowed="boolean"),
    "javascript_value_dependencies": dict(function_file="path", direct_callees="strings", helper_origin="path", add_expression="string", default_export_binding="string"),
    "javascript_direct_class_base": dict(class_file="path", local_base_name="string", base_name="string", base_origin="path", base_method="string", proves_runtime_dispatch="boolean"),
    "javascript_known_call_impact": dict(origin_file="path", direct_callers="endpoints"),
    "javascript_unproven_dependencies": dict(proven_targets="endpoints", default_forwarded_by_star="boolean", computed_call_exact="boolean", shadowed_Thing_is_import="boolean", commonjs_member_proven="boolean", dynamic_import_proven="boolean", computed_base_proven="boolean", jsdoc_type_supported="boolean"),
    "go_alias_generic_contract": dict(function_file="path", model_origin="path", alias_target="string", defined_underlying_type="string", generic_constraint="string", constraint_terms="strings", page_field="string"),
    "go_explicit_embedding": dict(struct_embedding="pair", interface_embedding="pair", audit_field="string", runner_method="string", embedding_is_class_inheritance="boolean", promoted_call_proven="boolean"),
    "go_known_api_impact": dict(api_file="path", known_direct_callers="endpoints", request_field="string", request_field_type="string"),
    "go_unproven_package_uses": dict(keep_type_origin="path", exact_probe_or_missing_callees="endpoints", old_proof_survives_module_change="boolean"),
    "rust_authored_trait_contract": dict(alias_underlying_type="string", build_bound="string", return_constructor="string", supertrait="string", receipt_field="string", explicitly_implemented_traits="strings", dynamic_call_target_proven="boolean"),
    "rust_contained_optional_reexport": dict(public_name="string", declaration_origin="path", field_name="string", field_type="string", dependency_package="string", configuration="configuration", active_feature_proven="boolean"),
    "rust_known_call_impact": dict(parse_file="path", direct_caller="endpoint", config_field="string", field_type="string", configuration="configuration"),
    "rust_unproven_contracts": dict(probe_type_origin="path", generic_Thing_is_model_Thing="boolean", choice_single_origin_proven="boolean", hidden_accessible="boolean", external_Display_contained="boolean", macro_target_proven="boolean", shared_import_may_be_guessed="boolean"),
    "tsx_props_control": dict(component_file="path", props_origin="path", prop_fields="fields", rendered_field="string", jsx_proves_call="boolean"),
    "markdown_section_control": dict(heading="string", nested_heading="string", budget_bytes="integer", unicode_word="string", following_peer="string"),
    "python_loci_bundle_contract": dict(bundle_fields="strings", span_fields="strings", relation_fields="strings", item_fields="strings", allowed_traversal="strings", root_role="string", missing_definition_error="string"),
}

_CONVENTIONS = """Return one JSON object with exactly the required keys and no Markdown fences.
File/origin fields use the repository-relative declaration file only: POSIX slashes,
no leading ./, absolute path, import specifier, ::symbol or #kind suffix.
Endpoint fields use file::Qualified.name, including the declaring class for methods;
do not append Loci's #kind suffix. Names and authored expression/type strings retain
source spelling, case, quotes and internal spacing. Field maps contain field-name
keys and authored type/annotation string values. Array values are strings, sorted
alphabetically, except ordered pairs: edge_direction is [caller name, callee name],
and embedding pairs are [owner name, embedded name]. Use an empty array when no
exact target is proven; do not invent an endpoint for unresolved evidence. Use JSON
booleans, not strings or numbers. Configuration is unconditional or declared_possible;
configuration metadata alone does not prove an active feature. Object-key order is
irrelevant; array order and exact string spelling are scored. JSON numbers compare
by value, with booleans treated separately. The schema specifies representation,
not the correct facts: derive values and certainty only from available source."""


def _field_schema(kind: str) -> dict[str, Any]:
    string = {"type": "string", "minLength": 1}
    if kind == "string":
        return {**string, "description": "Authored name, expression, type or text; preserve exact source spelling."}
    if kind == "path":
        return {**string, "pattern": _PATH_PATTERN, "description": "Repository-relative declaration file only; no ::symbol or #kind suffix."}
    if kind == "endpoint":
        return {**string, "pattern": _ENDPOINT_PATTERN, "description": "Repository-relative file::Qualified.name; no #kind suffix."}
    if kind in {"strings", "endpoints", "pair"}:
        result = {"type": "array", "items": _field_schema("endpoint") if kind == "endpoints" else string}
        if kind == "pair":
            result.update(minItems=2, maxItems=2, description="Ordered pair as specified by the task; do not alphabetize.")
        else:
            result["description"] = "Alphabetically sorted strings; use [] when none are proven."
        return result
    if kind == "fields":
        return {"type": "object", "propertyNames": string, "additionalProperties": string,
                "description": "Field-name to authored type/annotation string map."}
    if kind == "configuration":
        return {"type": "string", "enum": ["unconditional", "declared_possible"]}
    return {"type": kind}


def answer_schema(case_id: str) -> dict[str, Any]:
    """Return only authored representation rules, without reading corpus gold."""
    if case_id not in _FIELDS:
        raise ValueError(f"No {ANSWER_CONTRACT} schema for case {case_id}")
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "type": "object", "additionalProperties": False,
        "required": list(_FIELDS[case_id]),
        "properties": {name: _field_schema(kind) for name, kind in _FIELDS[case_id].items()},
    }


def _valid(kind: str, value: Any) -> bool:
    if kind == "boolean":
        return type(value) is bool
    if kind == "integer":
        return type(value) is int or (type(value) is float and math.isfinite(value) and value.is_integer())
    if kind == "fields":
        return type(value) is dict and all(_valid("string", k) and _valid("string", v) for k, v in value.items())
    if kind in {"strings", "endpoints", "pair"}:
        if type(value) is not list or not all(_valid("endpoint" if kind == "endpoints" else "string", item) for item in value):
            return False
        return len(value) == 2 if kind == "pair" else value == sorted(value)
    if type(value) is not str or not value:
        return False
    if kind == "configuration":
        return value in {"unconditional", "declared_possible"}
    if kind in {"path", "endpoint"}:
        pattern = _PATH_PATTERN if kind == "path" else _ENDPOINT_PATTERN
        path = value.split("::", 1)[0]
        return bool(re.fullmatch(pattern, value)) and PurePosixPath(path).as_posix() == path
    return True


def validate_answer(case_id: str, answer: Any) -> bool:
    """Check representation and ordering only; this does not judge truth."""
    answer_schema(case_id)  # Reject unknown cases rather than silently omitting a contract.
    return type(answer) is dict and answer.keys() == _FIELDS[case_id].keys() and all(
        _valid(kind, answer[name]) for name, kind in _FIELDS[case_id].items()
    )


def check_answer(corpus: dict[str, Any], case_id: str, answer: Any) -> bool:
    """Preserve exact source/certainty judgments after enforcing representation."""
    return validate_answer(case_id, answer) and legacy_check_answer(corpus, case_id, answer)


def build_prompt(corpus: dict[str, Any], controls: dict[str, Any], case_id: str, arm: str) -> str:
    """Append the same answer-free contract in both arms; never edit frozen input."""
    prompt = legacy_build_prompt(corpus, controls, case_id, arm)
    return prompt + "\n\nAnswer contract " + ANSWER_CONTRACT + ":\n" + _CONVENTIONS + "\n" + json.dumps(
        answer_schema(case_id), ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
