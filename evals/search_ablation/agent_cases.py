"""Private-case loading and source/answer-bound manual grading helpers.

This module contains no task prompts, private source, or answer keys. Correct
JSON fields and authentic quotations are necessary checks; independent source
review supplies the separate judgment that the cited evidence supports claims.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


def answer_sha256(answer: str) -> str:
    """Bind review to the exact UTF-8 final-answer text, including whitespace."""
    return hashlib.sha256(answer.encode("utf-8")).hexdigest()


def load_manifest(path: str | Path) -> dict[str, Any]:
    manifest = json.loads(Path(path).read_text(encoding="utf-8"))
    if manifest.get("schema_version") != 1 or not manifest.get("cases"):
        raise ValueError("Unsupported or empty private case manifest")
    ids = [case["case_id"] for case in manifest["cases"]]
    if len(ids) != len(set(ids)):
        raise ValueError("Duplicate case identity")
    return manifest


def validate_answer(case: dict[str, Any], answer: str, source_root: str | Path) -> dict[str, Any]:
    """Check factual fields and quote authenticity, without semantic keyword tests.

    The source root is the frozen pristine snapshot, not an agent-writable copy.
    Extra explanation is allowed and must be assessed separately by the reviewer.
    """
    errors: list[str] = []
    try:
        parsed = json.loads(answer)
    except (ValueError, TypeError) as exc:
        return {"pass": False, "errors": [f"Invalid final-answer JSON: {exc}"]}
    if not isinstance(parsed, dict):
        return {"pass": False, "errors": ["Final answer must be a JSON object"]}

    def compare(actual: Any, expected: Any, field: str) -> None:
        if isinstance(expected, dict):
            if not isinstance(actual, dict):
                errors.append(f"{field}: expected object")
                return
            for key, value in expected.items():
                if key not in actual:
                    errors.append(f"{field}.{key}: missing")
                else:
                    compare(actual[key], value, f"{field}.{key}")
        elif isinstance(expected, list):
            # Result property order is immaterial; duplicates remain incorrect.
            if not isinstance(actual, list) or len(actual) != len(expected) or any(
                actual.count(value) != expected.count(value) for value in expected
            ):
                errors.append(f"{field}: incorrect properties")
        elif type(actual) is not type(expected) or actual != expected:
            errors.append(f"{field}: incorrect")

    compare(parsed, case["expected_fields"], "answer")
    for field in case.get("nonempty_fields", []):
        if not isinstance(parsed.get(field), str) or not parsed[field].strip():
            errors.append(f"answer.{field}: nonempty explanation required")

    root = Path(source_root).resolve()
    entries = parsed.get("evidence")
    if not isinstance(entries, list) or not entries:
        errors.append("Source citations required")
        entries = []
    cited: set[str] = set()
    for number, entry in enumerate(entries):
        label = f"evidence[{number}]"
        try:
            if not isinstance(entry, dict):
                raise ValueError("expected object")
            name, lo, hi, quote = (entry[key] for key in ("path", "start_line", "end_line", "quote"))
            if not isinstance(name, str):
                raise ValueError("path must be a relative string")
            path = root / name
            if Path(name).is_absolute() or not path.resolve().is_relative_to(root):
                raise ValueError("citation escapes source snapshot")
            if not path.is_file():
                raise ValueError("source path missing")
            lines = path.read_text(encoding="utf-8").splitlines()
            if type(lo) is not int or type(hi) is not int or not (1 <= lo <= hi <= len(lines)) or hi - lo >= 12:
                raise ValueError("invalid citation range (maximum 12 lines)")
            if not isinstance(quote, str) or not 8 <= len(quote) <= 360 or not quote.strip():
                raise ValueError("invalid bounded quotation")
            if quote not in "\n".join(lines[lo - 1 : hi]):
                raise ValueError("quotation absent from cited lines")
            cited.add(name)
        except (KeyError, ValueError, TypeError, OSError) as exc:
            errors.append(f"{label}: {exc}")
    for name in case["required_evidence_paths"]:
        if name not in cited:
            errors.append(f"Missing source citation: {name}")
    return {"pass": not errors, "errors": errors}


def _review_binding_errors(case: dict, answer: str, review: dict) -> list[str]:
    errors = []
    if review.get("case_id") != case["case_id"] or review.get("answer_sha256") != answer_sha256(answer):
        errors.append("Review is not bound to this case and exact answer")
    if review.get("blinded") is not True or not review.get("reviewer"):
        errors.append("Independent blinded reviewer identity required")
    return errors


def grade_answer(
    case: dict[str, Any], answer: str, source_root: str | Path,
    review: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return a Promptfoo-compatible assertion after a blinded source review.

    A missing review is pending, never a correctness pass. Reviewers must not
    receive condition, usage, tool traces, or frozen mechanical grade beforehand.
    """
    checked = validate_answer(case, answer, source_root)
    errors = list(checked["errors"])
    if review is None:
        return {"pass": False, "score": 0, "reason": "Pending independent source review", "pending": True, "mechanical": checked}
    errors.extend(_review_binding_errors(case, answer, review))
    claims = review.get("claims", {})
    if not isinstance(claims, dict):
        claims = {}
    for claim in case["rubric"]:
        judgment = claims.get(claim["id"], {})
        if not isinstance(judgment, dict) or judgment.get("correct_and_supported") is not True:
            errors.append(f"Unmet or unsupported claim: {claim['id']}")
        if not isinstance(judgment, dict) or not isinstance(judgment.get("reason"), str) or not judgment["reason"].strip():
            errors.append(f"Missing review evidence: {claim['id']}")
    if review.get("no_material_contradictions") is not True:
        errors.append("Material contradictory/unsupported explanation or incomplete contradiction review")
    return {"pass": not errors, "score": int(not errors), "reason": "; ".join(errors) if errors else "Factual fields, authentic citations and independent source review pass", "pending": False, "mechanical": checked}


def grade_prompt_answer(case: dict, answer: str, source_root: str | Path, review: dict | None = None) -> dict:
    """Disclosed amended metric: actual prompt compliance, with strict citations.

    Preserve grade_answer as the original frozen rubric. This separate metric
    removes only optional details identified by the blinded reviewer, not false
    fields, missing requested support, or invalid quotations/line ranges.
    """
    checked = validate_answer(case, answer, source_root)
    errors = list(checked["errors"])
    if review is None:
        return {"pass": False, "score": 0, "reason": "Pending independent source review", "pending": True, "mechanical": checked}
    errors.extend(_review_binding_errors(case, answer, review))
    assessment = review.get("prompt_assessment", {})
    for field in ("requested_facts_correct", "requested_evidence_supported"):
        if assessment.get(field) is not True:
            errors.append(f"Prompt assessment failed: {field}")
    if not isinstance(assessment.get("reason"), str) or not assessment["reason"].strip():
        errors.append("Missing source-based prompt assessment reason")
    if review.get("no_material_contradictions") is not True:
        errors.append("Material contradictory/unsupported explanation or incomplete contradiction review")
    return {"pass": not errors, "score": int(not errors), "reason": "; ".join(errors) if errors else "Requested facts, source support and exact citations pass", "pending": False, "mechanical": checked}
