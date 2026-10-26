"""Independent raw-artifact audit of R0.6 uncertainty packets.

Uses only JSON/gzip retained packets and native observer projections. It does
not import Loci, a candidate summarizer, or any scorer.
"""
from __future__ import annotations

from collections import Counter
import gzip
import json
from pathlib import Path
import re
import sys

HERE = Path(__file__).resolve().parent
RESULTS = HERE / "results"
COMPARISONS = (
    "full-demand-focused",
    "full-focused-wide",
    "targeted-demand-focused",
    "targeted-focused-wide",
)
FAMILIES = (
    ("imports", "imports"),
    ("references", "symbol_references"),
    ("calls", "calls"),
    ("types", "type_relations"),
)
CATEGORY_BY_REASON = {
    "ambiguous_relation": "ambiguous_relation",
    "inaccessible_relation": "inaccessible_relation",
    "configuration_dependent_relation": "configuration_dependent_relation",
    "external_relation": "external_relation",
    "unresolved_relation": "unresolved_relation",
}


def load_json(path: Path):
    with path.open(encoding="utf-8") as stream:
        return json.load(stream)


def load_index(path: Path):
    with gzip.open(path, "rt", encoding="utf-8") as stream:
        return json.load(stream)


def classify(reason: str) -> str:
    if reason.startswith("ambiguous"):
        return "ambiguous_relation"
    if reason == "target_inaccessible":
        return "inaccessible_relation"
    if reason == "configuration_divergent":
        return "configuration_dependent_relation"
    if reason == "external":
        return "external_relation"
    return "unresolved_relation"


def expected_native(index: dict):
    graph = index.get("graph", {})
    counts = Counter()
    examples = Counter()
    unresolved_total = 0
    possible = 0
    for public_family, graph_family in FAMILIES:
        for record in graph.get(graph_family, []):
            possible += record.get("resolution_configuration") == "declared_possible"
            if record.get("status") != "unresolved":
                continue
            unresolved_total += 1
            reason = record.get("unresolved_reason") or "unknown"
            category = classify(reason)
            key = (public_family, reason, category)
            counts[key] += 1
            raw = record.get("raw", {})
            example = (public_family, raw.get("source_file"), raw.get("line"),
                       "unresolved", reason, record.get("import_unresolved_reason"))
            examples[example] += 1
    return counts, examples, unresolved_total, possible


def summary_counts(summary: dict):
    counts = Counter()
    for row in summary.get("counts", []):
        counts[(row.get("family"), row.get("reason"), row.get("consumer_reason"))] += row.get("count", 0)
    return counts


def packet_reasons(packet: dict):
    return {row.get("reason"): row.get("count", 0) for row in packet.get("omissions", [])}


def check_packet(packet: dict, index: dict, packet_path: Path, call_index: int):
    errors = []
    summary = packet.get("uncertainty")
    expected, native_examples, unresolved_total, possible = expected_native(index)
    got = summary_counts(summary)
    if got != expected:
        errors.append({"check": "native_reason_counts", "expected": dict(expected), "actual": dict(got)})
    if summary.get("scope") != "native_records_in_computed_slice":
        errors.append({"check": "slice_scope", "actual": summary.get("scope")})
    if summary.get("exhaustive") is not False:
        errors.append({"check": "uncertainty_non_exhaustive", "actual": summary.get("exhaustive")})
    if summary.get("configuration_possible_count") != possible:
        errors.append({"check": "declared_possible_count", "expected": possible,
                       "actual": summary.get("configuration_possible_count")})
    if summary.get("configuration_meaning") != "declared_possible does not establish active configuration":
        errors.append({"check": "active_configuration_unknown", "actual": summary.get("configuration_meaning")})

    examples = summary.get("examples", [])
    omitted = summary.get("examples_omitted")
    if len(examples) != min(8, unresolved_total):
        errors.append({"check": "example_cap", "expected": min(8, unresolved_total), "actual": len(examples)})
    if omitted != max(0, unresolved_total - len(examples)):
        errors.append({"check": "examples_omitted", "expected": max(0, unresolved_total - len(examples)), "actual": omitted})
    remaining_examples = native_examples.copy()
    for example in examples:
        key = (example.get("family"), example.get("file"), example.get("line"),
               example.get("status"), example.get("reason"), example.get("import_unresolved_reason"))
        if remaining_examples[key] <= 0:
            errors.append({"check": "example_native_match", "example": example})
        else:
            remaining_examples[key] -= 1

    reasons = packet_reasons(packet)
    required_reasons = Counter()
    for (_, _, category), count in expected.items():
        required_reasons[category] += count
    if possible:
        required_reasons["configuration_dependent_relation"] += possible
    has_uncertainty = bool(unresolved_total or possible)
    if has_uncertainty:
        if packet.get("scope", {}).get("coverage") != "partial":
            errors.append({"check": "packet_coverage_partial", "actual": packet.get("scope", {}).get("coverage")})
        if packet.get("scope", {}).get("exhaustive") is not False:
            errors.append({"check": "packet_non_exhaustive", "actual": packet.get("scope", {}).get("exhaustive")})
        for reason, count in required_reasons.items():
            if reasons.get(reason, 0) < count:
                errors.append({"check": "omission_reason_present", "reason": reason,
                               "minimum_count": count, "actual": reasons.get(reason, 0)})

    return {
        "packet": str(packet_path.relative_to(HERE)),
        "call_index": call_index,
        "policy": packet.get("policy"),
        "native_case_index": None,
        "native_unresolved_records": unresolved_total,
        "native_declared_possible_records": possible,
        "native_counts": [
            {"family": family, "reason": reason, "consumer_reason": category, "count": count}
            for (family, reason, category), count in sorted(expected.items())
        ],
        "reported_counts": [
            {"family": family, "reason": reason, "consumer_reason": category, "count": count}
            for (family, reason, category), count in sorted(got.items())
        ],
        "summary_count_entries": len(summary.get("counts", [])),
        "examples_returned": len(examples),
        "examples_omitted": omitted,
        "examples_native_match": not any(e.get("check", "").startswith("example_") for e in errors),
        "packet_omissions": reasons,
        "packet_status": packet.get("status"),
        "packet_scope_coverage": packet.get("scope", {}).get("coverage"),
        "packet_scope_exhaustive": packet.get("scope", {}).get("exhaustive"),
        "delivered_relationships": len(packet.get("relationships", [])),
        "checks": "pass" if not errors else "fail",
        "errors": errors,
    }


def main():
    output = {
        "schema_version": 1,
        "method": "independent retained JSON/gzip audit; no candidate code or scorer imported",
        "comparisons": [],
        "packet_checks": [],
        "baseline_negative_checks": [],
        "target_case": {},
        "python_go_boundary": {
            "classification": "unsupported-language capability gap; kept separate from unresolved-native counts",
            "evidence": ".scratch/r05-demand-semantics/RESULTS.md: full corpus notes Python and Go are source-only; 25 authored positive links receive zero semantic credit",
        },
        "status": "pass",
    }
    failures = []
    all_uncertainty_packets = 0
    all_missing_baseline = 0
    for comparison in COMPARISONS:
        comparison_root = RESULTS / comparison
        result = load_json(comparison_root / "result.json")
        comp_entry = {"name": comparison, "status": result.get("status"), "arms": []}
        for arm_root in sorted((comparison_root / "artifacts").iterdir()):
            if not arm_root.is_dir() or not re.fullmatch(r"(?:control|variant)-[12]-suite-[01]", arm_root.name):
                continue
            arm_entry = {"arm": arm_root.name, "packet_files": 0,
                         "uncertainty_responses": 0, "responses_without_uncertainty": 0}
            packet_dir = arm_root / "packets"
            for packet_path in sorted(packet_dir.glob("*.json")):
                arm_entry["packet_files"] += 1
                repeat = packet_path.name.endswith(".repeat.json")
                case_name = packet_path.name[:-len(".repeat.json")] if repeat else packet_path.stem
                suffix = ".repeat.json.gz" if repeat else ".json.gz"
                index_path = arm_root / "case-indexes" / f"{case_name}{suffix}"
                envelopes = load_json(packet_path)
                for call_index, envelope in enumerate(envelopes if isinstance(envelopes, list) else [envelopes]):
                    packet = envelope.get("structuredContent", {})
                    if not isinstance(packet, dict):
                        continue
                    if "uncertainty" not in packet:
                        arm_entry["responses_without_uncertainty"] += 1
                        continue
                    arm_entry["uncertainty_responses"] += 1
                    all_uncertainty_packets += 1
                    if not index_path.exists():
                        error = {"check": "native_case_index_exists", "path": str(index_path.relative_to(HERE))}
                        failures.append(error)
                        output["packet_checks"].append({"packet": str(packet_path.relative_to(HERE)),
                                                        "call_index": call_index, "checks": "fail", "errors": [error]})
                        continue
                    index = load_index(index_path)
                    check = check_packet(packet, index, packet_path, call_index)
                    check["native_case_index"] = str(index_path.relative_to(HERE))
                    check["arm"] = arm_root.name
                    check["comparison"] = comparison
                    output["packet_checks"].append(check)
                    if check["checks"] != "pass":
                        failures.extend(check["errors"])
                    if case_name == "rust_unproven_contracts":
                        summary = packet["uncertainty"]
                        graph = index.get("graph", {})
                        refs = [r for r in graph.get("symbol_references", []) if r.get("status") == "unresolved"]
                        imports = [r for r in graph.get("imports", []) if r.get("status") == "unresolved"]
                        types = [r for r in graph.get("type_relations", []) if r.get("status") == "unresolved"]
                        row = {
                            "comparison": comparison, "arm": arm_root.name,
                            "packet": str(packet_path.relative_to(HERE)), "call_index": call_index,
                            "native_external_imports": sum(r.get("unresolved_reason") == "external" for r in imports),
                            "native_unresolved_references": len(refs),
                            "native_reference_reasons": dict(Counter(r.get("unresolved_reason") for r in refs)),
                            "native_unresolved_type_parameter_records": sum(r.get("unresolved_reason") == "type_parameter" for r in types),
                            "native_unresolved_types": len(types),
                            "external_reference_example_preserved": any(
                                ex.get("family") == "references"
                                and ex.get("import_unresolved_reason") == "external"
                                for ex in summary.get("examples", [])),
                            "configuration_possible_count": summary.get("configuration_possible_count"),
                            "configuration_meaning": summary.get("configuration_meaning"),
                            "packet_delivered_relationships": [
                                {"type": r.get("edge", {}).get("type"),
                                 "line": r.get("edge", {}).get("evidence", {}).get("line"),
                                 "configuration": r.get("resolution_configuration"),
                                 "proof": r.get("proof")}
                                for r in packet.get("relationships", [])],
                            "packet_status": packet.get("status"),
                            "scope_exhaustive": summary.get("exhaustive"),
                            "checks": check["checks"],
                        }
                        output["target_case"].setdefault("observations", []).append(row)
            # Old R0.5 demand arm is expected not to expose R0.6 uncertainty.
            is_old_demand = comparison in ("full-demand-focused", "targeted-demand-focused") and arm_root.name.startswith("control-")
            if is_old_demand:
                all_missing_baseline += arm_entry["responses_without_uncertainty"]
                arm_entry["expected_no_uncertainty"] = True
                arm_entry["negative_check"] = "pass" if arm_entry["uncertainty_responses"] == 0 else "fail"
                if arm_entry["uncertainty_responses"]:
                    failures.append({"check": "baseline_has_no_r06_uncertainty", "comparison": comparison,
                                    "arm": arm_root.name, "count": arm_entry["uncertainty_responses"]})
                output["baseline_negative_checks"].append({"comparison": comparison, **arm_entry})
            comp_entry["arms"].append(arm_entry)
        output["comparisons"].append(comp_entry)

    # Each full/targeted R0.6 candidate comparison has two repetitions,
    # each with first-use and immediate-repeat packet artifacts.
    target_rows = output["target_case"].get("observations", [])
    target_errors = []
    for row in target_rows:
        if row["native_external_imports"] != 1:
            target_errors.append({"packet": row["packet"], "check": "target_external_import_count",
                                 "actual": row["native_external_imports"]})
        if row["native_unresolved_references"] != 4:
            target_errors.append({"packet": row["packet"], "check": "target_unresolved_reference_count",
                                 "actual": row["native_unresolved_references"]})
        if row["native_unresolved_type_parameter_records"] != 2:
            target_errors.append({"packet": row["packet"], "check": "target_type_parameter_count",
                                 "actual": row["native_unresolved_type_parameter_records"]})
        if row["configuration_possible_count"] <= 0:
            target_errors.append({"packet": row["packet"], "check": "target_configuration_possible"})
        if not row["external_reference_example_preserved"]:
            target_errors.append({"packet": row["packet"], "check": "target_external_import_reason_example"})
    if target_errors:
        failures.extend(target_errors)
    output["target_case"]["required_observation_rows"] = len(target_rows)
    output["target_case"]["expected_coverage"] = "initial and focused packets; first and repeat; two candidate repetitions; four focused/full-targeted architectures"
    output["target_case"]["checks"] = "pass" if not target_errors and target_rows else "fail"
    output["totals"] = {
        "comparisons": len(output["comparisons"]),
        "uncertainty_bearing_packet_responses": all_uncertainty_packets,
        "baseline_no_uncertainty_responses": all_missing_baseline,
        "passed_packet_checks": sum(row.get("checks") == "pass" for row in output["packet_checks"]),
        "failed_packet_checks": sum(row.get("checks") == "fail" for row in output["packet_checks"]),
        "target_case_observations": len(target_rows),
        "uncertainty_responses_with_empty_source_or_proof_status": sum(
            row.get("packet_status") == "empty" for row in output["packet_checks"]),
        "uncertainty_responses_empty_status_but_partial_scope": sum(
            row.get("packet_status") == "empty" and row.get("packet_scope_coverage") == "partial"
            for row in output["packet_checks"]),
        "uncertainty_responses_with_empty_status_and_native_uncertainty": sum(
            row.get("packet_status") == "empty" and row.get("packet_scope_coverage") == "partial"
            and bool(row.get("native_unresolved_records", 0) or row.get("native_declared_possible_records", 0))
            for row in output["packet_checks"]),
    }
    output["status"] = "pass" if not failures and all(row.get("checks") == "pass" for row in output["packet_checks"]) else "fail"
    output["failures"] = failures
    (HERE / "consumer-checks.json").write_text(json.dumps(output, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    md = ["# R0.6 retained consumer uncertainty checks", "",
          f"**Status: {output['status'].upper()}**", "",
          "Independent raw JSON/gzip comparison of consumer uncertainty against each paired native case-index projection. No candidate summarizer, scorer, source resolver, or measurement was run.", "",
          "## Coverage", "",
          f"- Comparisons: {output['totals']['comparisons']}",
          f"- Uncertainty-bearing packet responses checked: {all_uncertainty_packets}",
          f"- Old R0.5 demand baseline responses confirmed without the R0.6 uncertainty field: {all_missing_baseline}",
          f"- Passed packet checks: {output['totals']['passed_packet_checks']}; failed: {output['totals']['failed_packet_checks']}",
          f"- `rust_unproven_contracts` target observations: {len(target_rows)}",
          f"- Uncertainty-bearing packets with `status=empty` and partial uncertainty coverage: {output['totals']['uncertainty_responses_with_empty_status_and_native_uncertainty']}", "",
          "Each candidate repetition includes initial and immediate-repeat responses. Each focused arm includes its initial semantic packet and focused same-slice packets. Full and targeted demand-focused and focused-wide comparisons are included.", "",
          "## `rust_unproven_contracts`", "",
          "The native projection and consumer summary agree for each checked packet. The case retains one external import, four unresolved symbol references, and two unresolved type records with reason `type_parameter`. The nested `import_unresolved_reason=external` is preserved in an example. `configuration_possible_count` is read from native records marked `declared_possible`; the packet's explicit meaning says those do not establish active configuration. This audit validates uncertainty delivery only; it does not duplicate the retained strict proof replay.", "",
          "Some focused packets have `status=empty` because they delivered no source item or proof relationship. Where native uncertainty is present, those packets still expose the reason counts and report `scope.coverage=partial`, `scope.exhaustive=false`, and nonempty omissions; this status label therefore does not hide uncertainty or claim absence.", "",
          "## Unsupported language boundary", "",
          "Python and Go remain a separate capability gap: R0.5 retained outcomes classify them as source-only, with 25 authored positive links receiving no semantic credit. Those are not native unresolved-record counts and are not used to inflate the checks above.", "",
          "## Per-comparison response counts", "",
          "| Comparison | Arm | Packet files | Responses with uncertainty | Responses without uncertainty |", "|---|---|---:|---:|---:|"]
    for comp in output["comparisons"]:
        for arm in comp["arms"]:
            md.append(f"| {comp['name']} | {arm['arm']} | {arm['packet_files']} | {arm['uncertainty_responses']} | {arm['responses_without_uncertainty']} |")
    md.extend(["", "## Detailed records", "", "See `consumer-checks.json` for per-packet native counts, packet omission counts, paired index paths, matched example records, and check results.", ""])
    (HERE / "consumer-checks.md").write_text("\n".join(md), encoding="utf-8")
    print(json.dumps({"status": output["status"], "totals": output["totals"],
                      "target_case_rows": len(target_rows), "failures": failures[:10]}, indent=2))
    return 0 if output["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
