from __future__ import annotations

import hashlib
import tempfile
import unittest
from pathlib import Path

from benchmarks.ordinary_adoption_review import ReviewValidationError, assess_review, validate_case_sources


def _digest_lines(path: Path, start: int, end: int) -> str:
    text = path.read_text(encoding="utf-8")
    return hashlib.sha256("".join(text.splitlines(keepends=True)[start - 1 : end]).encode("utf-8")).hexdigest()


class OrdinaryAdoptionReviewTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.file = self.root / "src" / "widget.ts"
        self.file.parent.mkdir()
        self.file.write_text("export type Widget = { token: string };\nexport function make(): Widget {\n  return { token: 'ok' };\n}\n", encoding="utf-8")
        self.reference = {
            "file": "src/widget.ts",
            "start_line": 1,
            "end_line": 3,
            "sha256_of_exact_utf8_lines": _digest_lines(self.file, 1, 3),
        }
        self.corpus = {
            "source_files": {"src/widget.ts": hashlib.sha256(self.file.read_bytes()).hexdigest()},
            "cases": [{"required_facts": [{"id": "widget_contract", "sources": [self.reference]}]},],
        }
        self.case = self.corpus["cases"][0]

    def tearDown(self) -> None:
        self.temp.cleanup()

    def _review(self, judgment: str, quote: str | None = None) -> dict[str, object]:
        entry: dict[str, object] = {"fact_id": "widget_contract", "judgment": judgment}
        if quote is not None:
            entry["answer_quote"] = quote
        if judgment in {"correct", "incorrect"}:
            entry["source_references"] = [self.reference]
        return {"fact_judgments": [entry]}

    def test_validates_sources_and_ordinary_non_graph_answer(self) -> None:
        self.assertEqual(validate_case_sources(self.corpus, self.root), {"validated_files": 1, "validated_fact_spans": 1})
        answer = "The contract is Widget. Reading the declaration directly is sufficient; no relationship retrieval is needed."
        result = assess_review(self.case, answer, self._review("correct", "The contract is Widget."))
        self.assertTrue(result["structurally_valid"])
        self.assertEqual(result["relationship_annotations"], 0)

    def test_accepts_incorrect_and_missing_reviewer_judgments(self) -> None:
        answer = "The contract is Record<string, string>."
        incorrect = assess_review(self.case, answer, self._review("incorrect", answer))
        self.assertEqual(incorrect["judgment_counts"]["incorrect"], 1)
        missing = assess_review(self.case, "I cannot find the declaration.", self._review("missing"))
        self.assertEqual(missing["judgment_counts"]["missing"], 1)

    def test_rejects_missing_or_duplicate_fact_judgments(self) -> None:
        with self.assertRaisesRegex(ReviewValidationError, "omits"):
            assess_review(self.case, "answer", {"fact_judgments": []})
        duplicate = self._review("missing")
        duplicate["fact_judgments"].append({"fact_id": "widget_contract", "judgment": "missing"})
        with self.assertRaisesRegex(ReviewValidationError, "duplicates"):
            assess_review(self.case, "answer", duplicate)

    def test_rejects_fabricated_answer_quote(self) -> None:
        with self.assertRaisesRegex(ReviewValidationError, "not an exact substring"):
            assess_review(self.case, "The contract is Widget.", self._review("correct", "invented quote"))

    def test_rejects_fabricated_source_reference(self) -> None:
        review = self._review("correct", "The contract is Widget.")
        review["fact_judgments"][0]["source_references"] = [{
            **self.reference,
            "start_line": 2,
        }]
        with self.assertRaisesRegex(ReviewValidationError, "not an accepted case reference"):
            assess_review(self.case, "The contract is Widget.", review)

    def test_rejects_changed_source_hash(self) -> None:
        self.file.write_text("export type Widget = { token: number };\n", encoding="utf-8")
        with self.assertRaisesRegex(ReviewValidationError, "SHA-256 mismatch"):
            validate_case_sources(self.corpus, self.root)

    def test_valid_non_graph_answer_needs_no_observed_registry(self) -> None:
        result = assess_review(
            self.case,
            "The contract is Widget, with one additional source-backed detail.",
            self._review("correct", "The contract is Widget"),
        )
        self.assertEqual(result["relationship_annotations"], 0)

    def test_rejects_invented_supported_relationship_references(self) -> None:
        answer = "The caller is main."
        review = self._review("missing")
        review["relationship_support"] = [{
            "answer_quote": "The caller is main.",
            "status": "supported",
            "native_item_id": "invented-item",
            "model_output_evidence_reference": "outer:call-17:line:42:block:0",
        }]
        observed = {"mcp-17": {"semantic_relationship_count": 1, "model_output_refs": ["outer:call-17:line:42:block:0"]}}
        with self.assertRaisesRegex(ReviewValidationError, "unknown native item"):
            assess_review(self.case, answer, review, observed)

    def test_rejects_unknown_model_output_reference(self) -> None:
        answer = "The caller is main."
        review = self._review("missing")
        review["relationship_support"] = [{
            "answer_quote": "The caller is main.",
            "status": "supported",
            "native_item_id": "mcp-17",
            "model_output_evidence_reference": "outer:invented:line:1:block:0",
        }]
        observed = {"mcp-17": {"semantic_relationship_count": 1, "model_output_refs": ["outer:call-17:line:42:block:0"]}}
        with self.assertRaisesRegex(ReviewValidationError, "unknown or belongs"):
            assess_review(self.case, answer, review, observed)

    def test_supported_relationship_requires_observed_registry(self) -> None:
        answer = "The caller is main."
        review = self._review("missing")
        review["relationship_support"] = [{
            "answer_quote": "The caller is main.",
            "status": "supported",
            "native_item_id": "mcp-17",
            "model_output_evidence_reference": "outer:call-17:line:42:block:0",
        }]
        with self.assertRaisesRegex(ReviewValidationError, "requires an observed_evidence registry"):
            assess_review(self.case, answer, review)

    def test_rejects_mismatched_native_to_model_output_pairing(self) -> None:
        answer = "The caller is main."
        review = self._review("missing")
        review["relationship_support"] = [{
            "answer_quote": "The caller is main.",
            "status": "supported",
            "native_item_id": "mcp-17",
            "model_output_evidence_reference": "outer:call-18:line:7:block:0",
        }]
        observed = {
            "mcp-17": {"semantic_relationship_count": 1, "model_output_refs": ["outer:call-17:line:42:block:0"]},
            "mcp-18": {"semantic_relationship_count": 1, "model_output_refs": ["outer:call-18:line:7:block:0"]},
        }
        with self.assertRaisesRegex(ReviewValidationError, "different native item"):
            assess_review(self.case, answer, review, observed)

    def test_rejects_zero_semantic_relationship_proof(self) -> None:
        answer = "The caller is main."
        review = self._review("missing")
        review["relationship_support"] = [{
            "answer_quote": "The caller is main.",
            "status": "supported",
            "native_item_id": "mcp-17",
            "model_output_evidence_reference": "outer:call-17:line:42:block:0",
        }]
        observed = {"mcp-17": {"semantic_relationship_count": 0, "model_output_refs": ["outer:call-17:line:42:block:0"]}}
        with self.assertRaisesRegex(ReviewValidationError, "positive semantic relationship"):
            assess_review(self.case, answer, review, observed)

    def test_accepts_real_supported_relationship_pairing(self) -> None:
        answer = "The caller is main."
        review = self._review("missing")
        review["relationship_support"] = [{
            "answer_quote": "The caller is main.",
            "status": "supported",
            "native_item_id": "mcp-17",
            "model_output_evidence_reference": "outer:call-17:line:42:block:0",
        }]
        observed = {"mcp-17": {"semantic_relationship_count": 2, "model_output_refs": ["outer:call-17:line:42:block:0"]}}
        result = assess_review(self.case, answer, review, observed)
        self.assertEqual(result["relationship_annotations"], 1)

    def test_records_material_unsupported_claim_even_when_facts_are_correct(self) -> None:
        answer = "The contract is Widget. Widget is the only contract."
        review = self._review("correct", "The contract is Widget.")
        review["material_unsupported_claims"] = [{
            "answer_quote": "Widget is the only contract.",
            "reason": "The supplied source span does not establish an exhaustive contract set.",
        }]
        result = assess_review(self.case, answer, review)
        self.assertEqual(result["judgment_counts"]["correct"], 1)
        self.assertEqual(result["material_unsupported_claim_quotes"], ["Widget is the only contract."])


if __name__ == "__main__":
    unittest.main()
