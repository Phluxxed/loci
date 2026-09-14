"""Structural validation for evaluator-only ordinary-adoption annotations.

The module deliberately does not grade prose.  A reviewer supplies a compact
JSON-shaped mapping such as::

    {
      "fact_judgments": [
        {
          "fact_id": "public_contract",
          "judgment": "correct",
          "answer_quote": "The public contract is Widget.",
          "source_references": [{"file": "src/widget.ts", "start_line": 4,
                                 "end_line": 8,
                                 "sha256_of_exact_utf8_lines": "..."}],
        }
      ],
      "relationship_support": [
        {
          "answer_quote": "The caller is main.",
          "status": "supported",
          "native_item_id": "mcp-17",
          "model_output_evidence_reference": "outer:call-17:line:42:block:0"
        }
      ],
      "material_unsupported_claims": [
        {
          "answer_quote": "This is the only caller.",
          "reason": "The bounded evidence does not establish an exhaustive caller set."
        }
      ]
    }

``fact_judgments`` has exactly one entry for every case ``required_facts`` id.
``correct`` and ``incorrect`` require an exact nonempty answer quote and one
or more case-listed source references.  ``missing`` cannot carry an answer
quote.  ``uncertain`` may carry an exact quote and/or case-listed references,
but need not.  Relationship annotations are optional; supported requires both
an observer native item id and a model-visible-output evidence reference.
Pass observed_evidence only when a review claims supported. It is the
adapter-neutral registry {item_id: {semantic_relationship_count: int,
model_output_refs: [str, ...]}} derived from validated native artifacts.
The registry lists model-output refs only for full exact delivery; ambiguous
delivery remains an honest ambiguous_provenance status. An annotation records
observable delivery only and never establishes internal reliance.
"""

from __future__ import annotations

import hashlib
from pathlib import Path, PurePosixPath
from typing import Any, Mapping, Sequence


_JUDGMENTS = {"correct", "incorrect", "missing", "uncertain"}
_RELATIONSHIP_STATUSES = {
    "supported",
    "not_delivered",
    "not_used_in_answer",
    "ambiguous_provenance",
    "unknown",
}


class ReviewValidationError(ValueError):
    """Raised when corpus identities or reviewer annotation shape is invalid."""


def _mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ReviewValidationError(f"{label} must be an object")
    return value


def _nonempty_text(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ReviewValidationError(f"{label} must be a nonempty string")
    return value


def _items(value: Any, label: str) -> Sequence[Any]:
    if not isinstance(value, list):
        raise ReviewValidationError(f"{label} must be an array")
    return value


def _safe_file(root: Path, relative_name: Any) -> Path:
    relative_name = _nonempty_text(relative_name, "source file")
    relative = PurePosixPath(relative_name)
    if relative.is_absolute() or ".." in relative.parts:
        raise ReviewValidationError(f"source file is not a safe relative path: {relative_name!r}")
    candidate = (root / Path(*relative.parts)).resolve()
    try:
        candidate.relative_to(root)
    except ValueError as error:
        raise ReviewValidationError(f"source file escapes root: {relative_name!r}") from error
    return candidate


def _source_reference(value: Any, label: str) -> tuple[str, int, int, str]:
    reference = _mapping(value, label)
    file_name = _nonempty_text(reference.get("file"), f"{label}.file")
    start_line = reference.get("start_line")
    end_line = reference.get("end_line")
    if type(start_line) is not int or type(end_line) is not int or start_line < 1 or end_line < start_line:
        raise ReviewValidationError(f"{label} has invalid line bounds")
    digest = _nonempty_text(reference.get("sha256_of_exact_utf8_lines"), f"{label}.sha256_of_exact_utf8_lines")
    if len(digest) != 64 or any(character not in "0123456789abcdef" for character in digest):
        raise ReviewValidationError(f"{label} has an invalid SHA-256 digest")
    return file_name, start_line, end_line, digest


def _line_digest(path: Path, start_line: int, end_line: int) -> str:
    try:
        raw = path.read_bytes()
        text = raw.decode("utf-8")
    except OSError as error:
        raise ReviewValidationError(f"cannot read source file {path}") from error
    except UnicodeDecodeError as error:
        raise ReviewValidationError(f"source file is not UTF-8: {path}") from error
    lines = text.splitlines(keepends=True)
    if end_line > len(lines):
        raise ReviewValidationError(f"line span {start_line}-{end_line} exceeds {path}")
    return hashlib.sha256("".join(lines[start_line - 1 : end_line]).encode("utf-8")).hexdigest()


def validate_case_sources(corpus: Mapping[str, Any], root: str | Path) -> dict[str, int]:
    """Validate a corpus's complete-file and exact-line SHA identities.

    ``corpus`` must contain ``source_files`` (relative path to SHA-256) and
    ``cases``.  Every required-fact source must name a listed source file and
    use the four-field reference shape described in this module's docstring.
    The returned counts say only that identities and structure validated.
    """

    corpus = _mapping(corpus, "corpus")
    frozen_root = Path(root).resolve()
    if not frozen_root.is_dir():
        raise ReviewValidationError(f"source root is not a directory: {frozen_root}")
    source_files = _mapping(corpus.get("source_files"), "corpus.source_files")
    cases = _items(corpus.get("cases"), "corpus.cases")

    for relative_name, expected_digest in source_files.items():
        path = _safe_file(frozen_root, relative_name)
        if not path.is_file():
            raise ReviewValidationError(f"source file does not exist: {relative_name}")
        expected_digest = _nonempty_text(expected_digest, f"source_files[{relative_name!r}]")
        actual_digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if actual_digest != expected_digest:
            raise ReviewValidationError(f"source file SHA-256 mismatch: {relative_name}")

    span_count = 0
    for case_index, raw_case in enumerate(cases):
        case = _mapping(raw_case, f"cases[{case_index}]")
        facts = _items(case.get("required_facts"), f"cases[{case_index}].required_facts")
        seen_ids: set[str] = set()
        for fact_index, raw_fact in enumerate(facts):
            fact = _mapping(raw_fact, f"cases[{case_index}].required_facts[{fact_index}]")
            fact_id = _nonempty_text(fact.get("id"), "required fact id")
            if fact_id in seen_ids:
                raise ReviewValidationError(f"duplicate required fact id: {fact_id}")
            seen_ids.add(fact_id)
            references = _items(fact.get("sources"), f"required fact {fact_id}.sources")
            if not references:
                raise ReviewValidationError(f"required fact {fact_id} has no source references")
            for reference_index, raw_reference in enumerate(references):
                file_name, start_line, end_line, expected_digest = _source_reference(
                    raw_reference, f"required fact {fact_id}.sources[{reference_index}]"
                )
                if file_name not in source_files:
                    raise ReviewValidationError(f"required fact {fact_id} cites unlisted source file: {file_name}")
                actual_digest = _line_digest(_safe_file(frozen_root, file_name), start_line, end_line)
                if actual_digest != expected_digest:
                    raise ReviewValidationError(
                        f"required fact {fact_id} source span SHA-256 mismatch: {file_name}:{start_line}-{end_line}"
                    )
                span_count += 1
    return {"validated_files": len(source_files), "validated_fact_spans": span_count}


def _evidence_reference(value: Any, label: str) -> str:
    return _nonempty_text(value, label)


def _validate_quote(answer: str, value: Any, label: str) -> str:
    quote = _nonempty_text(value, label)
    if quote not in answer:
        raise ReviewValidationError(f"{label} is not an exact substring of the answer")
    return quote


def _supported_evidence(
    observed_evidence: Mapping[str, Any] | None,
    native_item_id: str,
    output_reference: str,
    index: int,
) -> None:
    if observed_evidence is None:
        raise ReviewValidationError(
            f"supported relationship annotation {index} requires an observed_evidence registry"
        )
    registry = _mapping(observed_evidence, "observed_evidence")
    if native_item_id not in registry:
        raise ReviewValidationError(f"supported relationship annotation {index} names unknown native item: {native_item_id}")
    record = _mapping(registry[native_item_id], f"observed_evidence[{native_item_id!r}]")
    edge_count = record.get("semantic_relationship_count")
    if type(edge_count) is not int or edge_count < 1:
        raise ReviewValidationError(
            f"supported relationship annotation {index} lacks positive semantic relationship evidence for native item: {native_item_id}"
        )
    output_references = _items(record.get("model_output_refs"), f"observed_evidence[{native_item_id!r}].model_output_refs")
    if any(not isinstance(reference, str) or not reference.strip() for reference in output_references):
        raise ReviewValidationError(f"observed_evidence[{native_item_id!r}].model_output_refs must contain nonempty strings")
    if output_reference not in output_references:
        raise ReviewValidationError(
            f"model output evidence reference for relationship annotation {index} is unknown or belongs to a different native item"
        )


def _material_unsupported_claims(answer: str, review: Mapping[str, Any]) -> list[str]:
    claims = _items(review.get("material_unsupported_claims", []), "review.material_unsupported_claims")
    recorded: list[str] = []
    for index, raw_claim in enumerate(claims):
        claim = _mapping(raw_claim, f"material_unsupported_claims[{index}]")
        quote = _validate_quote(answer, claim.get("answer_quote"), f"material unsupported claim quote {index}")
        _nonempty_text(claim.get("reason"), f"material unsupported claim reason {index}")
        recorded.append(quote)
    return recorded


def assess_review(
    case: Mapping[str, Any],
    answer: str,
    review: Mapping[str, Any],
    observed_evidence: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Validate reviewer annotations without judging whether their conclusions are true.

    This checks completeness, exact answer quotations, and whether citations are
    one of the case's accepted fixed-source references. A supported
    relationship annotation is cross-checked against the optional
    observer-derived observed_evidence registry; other statuses need no
    registry. It returns reviewer-supplied judgments separately from structural
    validation. It does not require relationship annotations, graph calls, or a
    JSON-shaped answer.
    """

    case = _mapping(case, "case")
    answer = _nonempty_text(answer, "answer")
    review = _mapping(review, "review")
    facts = _items(case.get("required_facts"), "case.required_facts")
    expected: dict[str, set[tuple[str, int, int, str]]] = {}
    for raw_fact in facts:
        fact = _mapping(raw_fact, "required fact")
        fact_id = _nonempty_text(fact.get("id"), "required fact id")
        if fact_id in expected:
            raise ReviewValidationError(f"duplicate required fact id: {fact_id}")
        references = _items(fact.get("sources"), f"required fact {fact_id}.sources")
        expected[fact_id] = {_source_reference(reference, f"required fact {fact_id} source") for reference in references}

    judgments = _items(review.get("fact_judgments"), "review.fact_judgments")
    seen: set[str] = set()
    reviewed: list[dict[str, str]] = []
    for index, raw_judgment in enumerate(judgments):
        judgment = _mapping(raw_judgment, f"review.fact_judgments[{index}]")
        fact_id = _nonempty_text(judgment.get("fact_id"), "review fact_id")
        if fact_id not in expected:
            raise ReviewValidationError(f"review names unknown required fact: {fact_id}")
        if fact_id in seen:
            raise ReviewValidationError(f"review duplicates required fact: {fact_id}")
        seen.add(fact_id)
        outcome = _nonempty_text(judgment.get("judgment"), f"review judgment for {fact_id}")
        if outcome not in _JUDGMENTS:
            raise ReviewValidationError(f"review judgment for {fact_id} is invalid: {outcome}")

        has_quote = "answer_quote" in judgment
        if outcome == "missing":
            if has_quote:
                raise ReviewValidationError(f"missing judgment for {fact_id} must not contain an answer quote")
            if judgment.get("source_references"):
                raise ReviewValidationError(f"missing judgment for {fact_id} must not contain source references")
        else:
            if has_quote:
                _validate_quote(answer, judgment["answer_quote"], f"answer quote for {fact_id}")
            elif outcome in {"correct", "incorrect"}:
                raise ReviewValidationError(f"{outcome} judgment for {fact_id} requires an answer quote")

            references_value = judgment.get("source_references")
            if outcome in {"correct", "incorrect"} and not references_value:
                raise ReviewValidationError(f"{outcome} judgment for {fact_id} requires source references")
            if references_value is not None:
                for reference_index, reference in enumerate(_items(references_value, f"source references for {fact_id}")):
                    normalized = _source_reference(reference, f"source reference for {fact_id}[{reference_index}]")
                    if normalized not in expected[fact_id]:
                        raise ReviewValidationError(f"source reference for {fact_id} is not an accepted case reference")
        reviewed.append({"fact_id": fact_id, "judgment": outcome})

    missing_ids = sorted(set(expected) - seen)
    if missing_ids:
        raise ReviewValidationError(f"review omits required fact judgments: {', '.join(missing_ids)}")

    relationships = review.get("relationship_support", [])
    for index, raw_annotation in enumerate(_items(relationships, "review.relationship_support")):
        annotation = _mapping(raw_annotation, f"relationship_support[{index}]")
        _validate_quote(answer, annotation.get("answer_quote"), f"relationship answer quote {index}")
        status = _nonempty_text(annotation.get("status"), f"relationship status {index}")
        if status not in _RELATIONSHIP_STATUSES:
            raise ReviewValidationError(f"relationship status {index} is invalid: {status}")
        if status == "supported":
            native_item_id = _nonempty_text(annotation.get("native_item_id"), f"relationship native_item_id {index}")
            output_reference = _evidence_reference(
                annotation.get("model_output_evidence_reference"),
                f"relationship model output evidence {index}",
            )
            _supported_evidence(observed_evidence, native_item_id, output_reference, index)

    counts = {outcome: sum(item["judgment"] == outcome for item in reviewed) for outcome in sorted(_JUDGMENTS)}
    unsupported_claims = _material_unsupported_claims(answer, review)
    return {
        "structurally_valid": True,
        "reviewer_fact_judgments": reviewed,
        "judgment_counts": counts,
        "relationship_annotations": len(relationships),
        "material_unsupported_claim_quotes": unsupported_claims,
        "required_fact_coverage_does_not_assess_extra_material_claims": True,
        "reviewer_judgments_are_not_semantically_verified": True,
        "relationship_annotations_do_not_establish_cognition": True,
    }
