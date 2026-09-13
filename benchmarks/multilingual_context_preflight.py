"""No-provider scorer proof from fresh multilingual fixture indexes.

This prepares retained evidence for the comparison without changing the frozen
corpus, engine, or any provider state.  Every positive and zero-budget packet is
the direct result of the current ``service.explore`` product route.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path
import tempfile
from typing import Any

from benchmarks.multilingual_context_inputs import load_inputs
from benchmarks.multilingual_context_relationships import score_relationships, validate_relation_mappings
from benchmarks.typescript_context_baseline import ROOT, save, sha
from benchmarks.typescript_context_corpus import _isolated_store, materialize_snapshot
from loci import service


COMPARISON = "multilingual-context-workflow-v1"
DEFAULT_OUTPUT = ROOT / "benchmarks/comparisons" / COMPARISON / "scorer-proof"
VERIFICATION = ROOT / "benchmarks/comparisons" / COMPARISON / "scorer-verification.json"

# These are product symbol IDs from the frozen fixtures.  Rust implementation
# symbols are discovered from the fresh index because their disambiguators are
# deliberately index-owned.
_PROBES = (
    ("python", "python_alias_annotation", "type_dependencies", (
        "consumer.py::decode#function", "consumer.py::Alias#type",
    )),
    ("javascript", "javascript_value_dependencies", "dependencies", (
        "app.js::run#function", "helper.js::make#function",
    )),
    ("go", "go_alias_generic_contract", "type_dependencies", (
        "app/main.go::Build#function", "model/model.go::AliasID#type",
    )),
    ("rust", "rust_authored_trait_contract", "type_dependencies", (
        "src/lib.rs::build#function", "src/lib.rs::Receipt#struct", "src/lib.rs::Envelope#struct",
    )),
    ("tsx", "tsx_props_control", "type_dependencies", ("badge.tsx::Badge#function",)),
    ("markdown", "markdown_section_control", "locate", (
        "guide.md::Context guide > Limits#section",
    )),
)


def _write(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    save(path, value)


def _index_identity(index: dict[str, Any]) -> dict[str, Any]:
    """Retain only an evaluator-side index identity, never a mutable cache path."""

    compact = json.dumps(index, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return {
        "schema_version": 1,
        "index_sha256": hashlib.sha256(compact).hexdigest(),
        "symbols": len(index.get("symbols", [])),
        "graph": {
            key: len(index.get("graph", {}).get(key, []))
            for key in ("type_relations", "calls", "imports", "symbol_references")
        },
    }


def _explore(repo: Path, intent: str, seed_ids: list[str], *, evidence: int = 8192) -> dict[str, Any]:
    return service.explore(
        repo,
        intent=intent,
        seed_ids=seed_ids,
        max_hops=3,
        max_evidence_bytes=evidence,
        max_output_bytes=16_384,
        ensure_fresh=True,
    )


def _rust_impl_ids(index: dict[str, Any]) -> list[str]:
    return [
        symbol["id"]
        for symbol in index.get("symbols", [])
        if symbol.get("kind") == "impl" and symbol.get("id", "").startswith("src/lib.rs::Receipt#impl")
    ]


def _endpoint_id(case: dict[str, Any], index: dict[str, Any], context_id: str) -> str | None:
    context = next((item for item in case.get("context", []) if item.get("id") == context_id), None)
    if not isinstance(context, dict) or not isinstance(context.get("symbol"), dict):
        return None
    symbol = context["symbol"]
    matches = [
        item.get("id") for item in index.get("symbols", [])
        if item.get("file_path") == context.get("file")
        and item.get("name") == symbol.get("name") and item.get("kind") == symbol.get("kind")
    ]
    return matches[0] if len(matches) == 1 and isinstance(matches[0], str) else None


def _wrong_origin_score(
    case: dict[str, Any], index: dict[str, Any], packet: dict[str, Any]
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    """Inject one evaluator-only wrong-file record and require scorer detection."""

    forbidden = next((item for item in case.get("forbidden_relationships", []) if item.get("target_file")), None)
    synthetic = not isinstance(forbidden, dict)
    if synthetic:
        forbidden = next((item for item in case.get("forbidden_relationships", []) if item.get("kind") == "calls" or item.get("use")), None)
    if not isinstance(forbidden, dict):
        return ({"applicable": False, "reason": "source-only control has no relationship negative"}, {}, packet)
    source_id = _endpoint_id(case, index, forbidden.get("from", case.get("anchor")))
    if not source_id:
        return ({"applicable": False, "reason": "negative has no indexed source endpoint"}, {}, packet)
    if synthetic:
        # There is no fixture-side distractor for these cases.  Forge only a
        # delivered packet claim: retain the real index, relation source, name
        # and kind, but move its endpoint to an evaluator-only wrong path.
        # This proves that the trust gate rejects a plausible same-name claim
        # without pretending the product resolved it.
        altered_packet = copy.deepcopy(packet)
        relation = next((item for item in altered_packet.get("relationships", []) if item.get("source_ids")), None)
        if not isinstance(relation, dict) or not isinstance(relation.get("edge"), dict):
            return ({"applicable": False, "reason": "positive packet has no source-backed relationship"}, {}, packet)
        claimed = copy.deepcopy(relation)
        claimed["id"] = max((item.get("id", 0) for item in altered_packet["relationships"] if isinstance(item, dict)), default=0) + 1
        edge = claimed["edge"]
        original_target = edge.get("to")
        if not isinstance(original_target, str):
            return ({"applicable": False, "reason": "positive relation has no target identity"}, {}, packet)
        edge["to"] = f"wrong-origin/{original_target}"
        altered_packet["relationships"].append(claimed)
        score = score_relationships(case, index, [altered_packet])
        return ({
            "applicable": True,
            "family": "synthetic-packet",
            "source_id": source_id,
            "original_target_id": original_target,
            "wrong_target_id": edge["to"],
            "synthetic_wrong_origin": True,
            "product_packet_mutated": True,
            "index_unchanged": True,
            "expectation": "non-indexed same-name wrong-origin claim is rejected by delivery integrity",
        }, score, altered_packet)
    mutated = copy.deepcopy(index)
    graph = mutated.setdefault("graph", {})
    target: dict[str, Any] | None = None
    if not synthetic:
        target = next((item for item in mutated.get("symbols", []) if item.get("file_path") == forbidden["target_file"]), None)
    if not isinstance(target, dict) or not isinstance(target.get("id"), str):
        name = forbidden.get("target_name") or "format"
        target = {
            "id": f"wrong-origin/{name}.synthetic::{name}#function",
            "name": name,
            "kind": "function",
            "file_path": f"wrong-origin/{name}.synthetic",
        }
        mutated.setdefault("symbols", []).append(target)
        synthetic = True
    for key, source_key in (() if synthetic else (("type_relations", "source_id"), ("calls", "caller_id"))):
        records = graph.get(key, [])
        exemplar = next((item for item in records if item.get("status") == "resolved" and item.get(source_key) == source_id), None)
        if isinstance(exemplar, dict):
            injected = copy.deepcopy(exemplar)
            injected["target_id"] = target["id"]
            injected["target_file"] = target["file_path"]
            records.append(injected)
            edges = graph.get("edges", [])
            edge = next((item for item in edges if item.get("from") == source_id
                         and item.get("to") == exemplar.get("target_id")
                         and item.get("evidence", {}).get("line") == exemplar.get("raw", {}).get("line")), None)
            if not isinstance(edge, dict):
                return {"applicable": False, "reason": "no matching proven edge to mutate"}, None
            injected_edge = copy.deepcopy(edge)
            injected_edge["to"] = target["id"]
            injected_edge["namespace"] = "loci"
            injected_edge["directed"] = True
            if injected_edge.get("resolution") not in {"exact", "declared", "import-resolved"}:
                injected_edge["resolution"] = "exact"
            edges.append(injected_edge)
            altered_packet = copy.deepcopy(packet)
            relation = next((item for item in altered_packet.get("relationships", []) if item.get("source_ids")), None)
            if not isinstance(relation, dict):
                return {"applicable": False, "reason": "positive packet has no source-backed relationship"}, {}, packet
            claimed = copy.deepcopy(relation)
            claimed["id"] = max((item.get("id", 0) for item in altered_packet["relationships"] if isinstance(item, dict)), default=0) + 1
            claimed["edge"] = injected_edge
            altered_packet["relationships"].append(claimed)
            score = score_relationships(case, mutated, [altered_packet])
            mutation = {
                "applicable": True,
                "family": key,
                "source_id": source_id,
                "wrong_target_id": target["id"],
                "wrong_target_file": target["file_path"],
                "synthetic_wrong_origin": synthetic,
                "product_packet_mutated": True,
                "expectation": "evaluator detects the source-backed wrong-origin claim from injected index proof",
            }
            return mutation, score, altered_packet

    # Rust/TSX negatives can forbid calls even though their positive path is a
    # type relation.  Construct a bounded evaluator-only call proof using an
    # existing edge envelope; it deliberately does not claim product resolution.
    edges = graph.get("edges", [])
    template = next((item for item in edges if isinstance(item, dict)), None)
    if not isinstance(template, dict):
        return {"applicable": False, "reason": "index has no edge envelope"}, {}, packet
    raw_text = "span" if forbidden.get("target_name") == "span" else "format!"
    line = template.get("evidence", {}).get("line", 1)
    record = {
        "status": "resolved", "caller_id": source_id, "target_id": target["id"],
        "raw": {"line": line, "callee_text": raw_text},
    }
    graph.setdefault("calls", []).append(record)
    injected_edge = copy.deepcopy(template)
    injected_edge.update({"from": source_id, "to": target["id"], "type": "calls", "namespace": "loci", "directed": True, "resolution": "exact"})
    injected_edge.setdefault("evidence", {})["line"] = line
    edges.append(injected_edge)
    altered_packet = copy.deepcopy(packet)
    relation = next((item for item in altered_packet.get("relationships", []) if item.get("source_ids")), None)
    if not isinstance(relation, dict):
        return {"applicable": False, "reason": "positive packet has no source-backed relationship"}, {}, packet
    claimed = copy.deepcopy(relation)
    claimed["id"] = max((item.get("id", 0) for item in altered_packet["relationships"] if isinstance(item, dict)), default=0) + 1
    claimed["edge"] = injected_edge
    altered_packet["relationships"].append(claimed)
    score = score_relationships(case, mutated, [altered_packet])
    return ({"applicable": True, "family": "calls", "source_id": source_id, "wrong_target_id": target["id"],
             "wrong_target_file": target["file_path"], "synthetic_wrong_origin": True,
             "product_packet_mutated": True, "expectation": "synthetic wrong-origin call is rejected"}, score, altered_packet)


def _missing_proof(packet: dict[str, Any]) -> dict[str, Any] | None:
    """Remove one actual relation proof source while preserving all other bytes."""

    altered = copy.deepcopy(packet)
    relations = altered.get("relationships", [])
    if not relations or not isinstance(relations[0], dict):
        return None
    source_ids = relations[0].get("source_ids")
    if not isinstance(source_ids, list) or not source_ids:
        return None
    missing_id = source_ids[0]
    altered["sources"] = [item for item in altered.get("sources", []) if item.get("id") != missing_id]
    return altered


def _unknown_mapping_rejected(corpus: dict[str, Any]) -> dict[str, Any]:
    mutated = copy.deepcopy(corpus)
    first = next(case for case in mutated["cases"] if case.get("relationships"))
    first["relationships"][0]["kind"] = "unknown_preflight_kind"
    try:
        validate_relation_mappings(mutated)
    except ValueError as exc:
        return {"rejected": True, "error": str(exc)}
    return {"rejected": False, "error": "unknown relationship kind was accepted"}


def run(output: Path = DEFAULT_OUTPUT, verification: Path = VERIFICATION) -> dict[str, Any]:
    """Create bounded, fresh-index actual-packet evidence and a truthful summary."""

    output, verification = Path(output).resolve(), Path(verification).resolve()
    corpus, _controls = load_inputs()
    validate_relation_mappings(corpus)
    cases = {case["id"]: case for case in corpus["cases"]}
    mapping_kinds = sorted({
        f"{case['language']}:{relation['kind']}"
        for case in corpus["cases"] for relation in case.get("relationships", [])
    })
    checks: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []

    with tempfile.TemporaryDirectory(prefix="loci-multilingual-scorer-preflight-") as raw:
        temporary = Path(raw)
        for family, case_id, intent, base_seeds in _PROBES:
            case = cases[case_id]
            repo, store = temporary / family, temporary / f"store-{family}"
            materialize_snapshot(corpus, case["snapshot"], repo)
            target = output / family
            with _isolated_store(store):
                service.index_repo(repo, incremental=False)
                index = service.get_store().load(repo.resolve())
                if not isinstance(index, dict):
                    raise ValueError("fresh preflight index was not retained")
                seeds = [*base_seeds]
                if family == "rust":
                    seeds.extend(_rust_impl_ids(index))
                if len(seeds) > 5 or any(seed not in {item.get("id") for item in index.get("symbols", [])} for seed in seeds):
                    raise ValueError(f"preflight seeds are not exact current symbols: {family}")
                positive = _explore(repo, intent, seeds)
                positive_score = score_relationships(case, index, [positive])
                _write(target / "positive.packet.json", positive)
                _write(target / "positive.score.json", positive_score)
                _write(target / "index-identity.json", _index_identity(index))
                positive_ok = (
                    "error" not in positive
                    and positive_score["forbidden_proven_relationships"] == 0
                    and not positive_score["delivery_integrity_violations"]
                    and (family == "markdown" or positive_score["delivered_dependency_links_total"] > 0)
                    and (family != "markdown" or bool(positive.get("sources")))
                )

                zero = _explore(repo, intent, seeds, evidence=0)
                zero_score = score_relationships(case, index, [zero])
                _write(target / "zero-budget.packet.json", zero)
                _write(target / "zero-budget.score.json", zero_score)
                zero_ok = (
                    "error" not in zero and not zero.get("relationships") and not zero.get("sources")
                    and zero_score["delivered_dependency_links_total"] == 0
                    and bool(zero.get("omissions"))
                )

                altered = _missing_proof(positive)
                if family == "markdown":
                    missing = {"applicable": False, "reason": "source-only control has no relationship proof"}
                    _write(target / "missing-proof.not-applicable.json", missing)
                    missing_ok = True
                elif altered is None:
                    missing = {"applicable": False, "reason": "positive packet has no relationship proof"}
                    _write(target / "missing-proof.not-applicable.json", missing)
                    missing_ok = False
                else:
                    missing_score = score_relationships(case, index, [altered])
                    _write(target / "missing-proof.packet.json", altered)
                    _write(target / "missing-proof.score.json", missing_score)
                    missing = {"applicable": True, "missing_source_removed": True, "score": missing_score}
                    missing_ok = (
                        missing_score["delivered_dependency_links_total"] < positive_score["delivered_dependency_links_total"]
                        and bool(missing_score["delivery_integrity_violations"])
                    )

                mutation, wrong_score, wrong_packet = _wrong_origin_score(case, index, positive)
                _write(target / "wrong-origin.mutation.json", mutation)
                if family == "rust":
                    _write(target / "wrong-origin.prior-draft.json", {
                        "status": "superseded_failed_preparation",
                        "reason": "The first synthetic probe invented a format call and mutated the evaluator index, so it could not establish packet-origin rejection.",
                        "replacement": "packet-only endpoint forgery against the unchanged fresh index",
                    })
                if wrong_packet is not positive:
                    _write(target / "wrong-origin.packet.json", wrong_packet)
                if wrong_score:
                    _write(target / "wrong-origin.score.json", wrong_score)
                # Markdown has no semantic relationship claim.  Every
                # programming family proves a wrong-origin rejection: frozen
                # distractors where available, otherwise a packet-only forged
                # endpoint that must fail the delivery-integrity trust gate.
                wrong_not_applicable = family == "markdown" and not mutation.get("applicable", False)
                wrong_ok = wrong_not_applicable or (
                    wrong_score is not None and (
                        wrong_score["forbidden_proven_relationships"] > 0
                        or bool(wrong_score["delivery_integrity_violations"])
                    )
                )
                check = {
                    "family": family, "case_id": case_id, "intent": intent, "seed_ids": seeds,
                    "positive": positive_ok, "zero_budget": zero_ok, "missing_proof": missing_ok,
                    "wrong_origin": wrong_ok, "wrong_origin_not_applicable": wrong_not_applicable,
                    "relationships_not_applicable": family == "markdown",
                }
                checks.append(check)
                if not all(check[name] for name in ("positive", "zero_budget", "missing_proof", "wrong_origin")):
                    failures.append(check)

    unknown = _unknown_mapping_rejected(corpus)
    unknown_path = output / "unknown-kind-rejection.json"
    _write(unknown_path, unknown)
    summary = {
        "schema_version": 1,
        "comparison": COMPARISON,
        "provider_calls": 0,
        "implementation": "fresh fixture indexes and direct current service.explore packets",
        "mapping_coverage": {"validated": True, "mapped_kinds": mapping_kinds, "count": len(mapping_kinds)},
        "unknown_kind_rejection": unknown,
        "checks": checks,
        "failures": failures,
        "passed": not failures and unknown["rejected"],
    }
    _write(verification, summary)
    return summary


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--verification", type=Path, default=VERIFICATION)
    args = parser.parse_args(argv)
    print(json.dumps(run(args.output, args.verification), ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
