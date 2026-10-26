"""Bounded consumer uncertainty from one retained native Rust slice."""
from collections import Counter

from loci.focused_proof import FocusedDemandSource


def _rust_repo(tmp_path):
    root = tmp_path / "repo"
    (root / "src").mkdir(parents=True)
    (root / "Cargo.toml").write_text(
        '[package]\nname = "uncertainty_case"\nversion = "0.1.0"\nedition = "2021"\n',
        encoding="utf-8",
    )
    (root / "src/lib.rs").write_text(
        '''pub mod a;
pub mod b;
pub mod model;
mod private_api;
use crate::model::{Twin, Choice};
use crate::private_api::Hidden;
use std::fmt::Display;

pub struct Thing;
pub fn probe(_twin: Twin, _choice: Choice, _hidden: Hidden, _display: Display,
             _conditional: Conditional) -> Thing {
    Thing
}
pub fn generic<T>(value: T) -> T { value }
#[cfg(feature = "alpha")]
pub struct Conditional;
pub fn conditional(_value: Conditional) {}
''',
        encoding="utf-8",
    )
    (root / "src/a.rs").write_text(
        "pub struct Value;\npub struct Twin;\n", encoding="utf-8"
    )
    (root / "src/b.rs").write_text(
        "pub struct Value;\npub struct Twin;\n", encoding="utf-8"
    )
    (root / "src/model.rs").write_text(
        '''pub use crate::a::Value as Twin;
pub use crate::b::Value as Twin;
#[cfg(feature = "alpha")]
pub use crate::a::Value as Choice;
#[cfg(not(feature = "alpha"))]
pub use crate::b::Value as Choice;
''',
        encoding="utf-8",
    )
    (root / "src/private_api.rs").write_text(
        "struct Hidden;\n", encoding="utf-8"
    )
    return root


def _unresolved_native_counts(index):
    counts = Counter()
    unresolved_total = 0
    for family, records in (
        ("imports", index["graph"]["imports"]),
        ("references", index["graph"]["symbol_references"]),
        ("calls", index["graph"]["calls"]),
        ("types", index["graph"]["type_relations"]),
    ):
        for record in records:
            if record["status"] != "unresolved":
                continue
            unresolved_total += 1
            reason = record.get("unresolved_reason") or "unknown"
            category = (
                "ambiguous_relation" if reason.startswith("ambiguous") else
                "inaccessible_relation" if reason == "target_inaccessible" else
                "configuration_dependent_relation" if reason == "configuration_divergent" else
                "external_relation" if reason == "external" else
                "unresolved_relation"
            )
            counts[family, reason, category] += 1
    return counts, unresolved_total


def test_initial_and_focused_packets_report_bounded_native_rust_uncertainty(tmp_path):
    root = _rust_repo(tmp_path)
    service = FocusedDemandSource(tmp_path / "store")

    initial = service.semantic_context(root, "probe")
    index = service.semantic_observer()["index"]
    uncertainty = initial["uncertainty"]

    native_counts, unresolved_total = _unresolved_native_counts(index)
    reported_counts = {
        (row["family"], row["reason"], row["consumer_reason"]): row["count"]
        for row in uncertainty["counts"]
    }
    assert reported_counts == dict(native_counts)
    assert uncertainty["scope"] == "native_records_in_computed_slice"
    assert uncertainty["exhaustive"] is False
    assert len(uncertainty["examples"]) == min(8, unresolved_total)
    assert uncertainty["examples_omitted"] == max(0, unresolved_total - 8)

    packet_reasons = {row["reason"] for row in initial["omissions"]}
    assert {"ambiguous_relation", "inaccessible_relation", "external_relation",
            "unresolved_relation", "configuration_dependent_relation"} <= packet_reasons
    assert initial["status"] == "partial"
    assert initial["scope"]["coverage"] == "partial"
    assert initial["scope"]["exhaustive"] is False
    assert any(item["node_id"] == "src/lib.rs::probe#function" and item["complete"]
               for item in initial["items"])

    refs = index["graph"]["symbol_references"]
    reasons = {row.get("unresolved_reason") for row in refs if row["status"] == "unresolved"}
    assert {"ambiguous_target", "configuration_divergent", "target_inaccessible",
            "import_unresolved"} <= reasons
    external_ref = next(row for row in refs
                        if row["status"] == "unresolved"
                        and row.get("import_unresolved_reason") == "external")
    assert external_ref["unresolved_reason"] == "import_unresolved"

    type_rows = [row for row in index["graph"]["type_relations"]
                 if row["status"] == "unresolved"]
    assert sum(row["unresolved_reason"] == "type_parameter" for row in type_rows) >= 2
    possible_count = sum(
        row.get("resolution_configuration") == "declared_possible"
        for family in ("imports", "symbol_references", "calls", "type_relations")
        for row in index["graph"][family]
    )
    assert possible_count > 0
    assert uncertainty["configuration_possible_count"] == possible_count
    assert uncertainty["configuration_meaning"] == (
        "declared_possible does not establish active configuration"
    )
    possible_relation = next(row for row in initial["relationships"]
                             if row["resolution_configuration"] == "declared_possible")
    assert possible_relation["resolution_configuration"] == "declared_possible"

    focused = service.proof_context(root, initial["anchors"][0]["node_id"])
    assert focused["uncertainty"] == uncertainty
    assert focused["scope"]["coverage"] == "partial"
    assert focused["status"] == "partial"
    assert focused["proof_request"]["scope"] == "same_computed_slice"
