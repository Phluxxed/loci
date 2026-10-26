from __future__ import annotations

from . import rust_crates as rust


def merge_observed_configuration(
    current: rust.RustResolutionConfiguration,
    observed: str,
) -> rust.RustResolutionConfiguration | None:
    if observed == "unsupported":
        return None
    if current == "declared_possible" or observed == "conditional":
        return "declared_possible"
    if observed != "unconditional":
        return None
    return "unconditional"


def widest_configuration(
    left: rust.RustResolutionConfiguration,
    right: rust.RustResolutionConfiguration,
) -> rust.RustResolutionConfiguration:
    if "declared_possible" in {left, right}:
        return "declared_possible"
    return "unconditional"
