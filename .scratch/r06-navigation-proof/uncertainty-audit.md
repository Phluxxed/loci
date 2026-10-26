# R0.6 uncertainty audit

## Finding

The retained Rust uncertainty case demonstrates that source navigation and semantic proof answer different questions. In `rust_unproven_contracts`, the demand packet contains complete source items and two complete relationships, and reports `scope.coverage=complete` with `omissions=[]`. The same request's retained native projection has four unresolved references and two unresolved type uses. The packet is complete only for its inferred, non-exhaustive set of emitted claims; it does not say that all potentially relevant relationships resolved or that no uncertainty exists.

This is a packet representation/selection gap, not a demonstrated source-closure failure. The demand preparation parsed the crate root and the four local Rust modules, included `Cargo.toml`, and recorded `rust_closure_incomplete=false`. The packet anchor is the exact `probe` function; it considers nine eligible graph edges and emits two. It also records five omitted symbol candidates, but no omission for the native unresolved outcomes. The packer traverses materialized resolved edges, so unresolved records do not become edges or packet omissions. Thus an empty packet omission list cannot be read as an empty native uncertainty set.

## Target case evidence

Artifacts are in `.scratch/r05-demand-semantics/results/full-source-demand/artifacts/variant-1-suite-1/` (the targeted pair has matching evidence under `targeted-source-demand/artifacts/variant-1-suite-1/`). The `packets/rust_unproven_contracts.json` file contains five observed calls; call 1 is the `demand-semantic-v1` response. The native observer projection is `case-indexes/rust_unproven_contracts.json.gz`; the repository-level inventory and case result are `inventories/rust_uncertainty.json` and `indexes/rust_uncertainty.json.gz`. Immediate repeat packet and observer files are suffixed `.repeat`; the retained run reports identical first/repeat capabilities.

The two delivered claims are:

- `probe` uses type `Thing`, `src/lib.rs:10` → `src/model.rs::Thing#struct`, configuration `unconditional`.
- `probe` references `Thing`, `src/lib.rs:11` → `src/model.rs::Thing#struct`, configuration `unconditional`.

Both proofs are complete and source-backed. The same native projection records:

| Native observation | Location | Native status and reason | Configuration / support |
| --- | --- | --- | --- |
| Import `std::fmt::Display` | `src/lib.rs:8` | unresolved / `external` | No local target or control file |
| Reference `Shared` | `src/lib.rs:12` | unresolved / `ambiguous_target` | `src/model.rs` import surface; candidate details remain in the observer |
| Reference `Choice` | `src/lib.rs:14` | unresolved / `configuration_divergent` | The two `Choice` reexports are each `declared_possible`; no active feature selection is claimed |
| Reference `Hidden` | `src/lib.rs:15` | unresolved / `target_inaccessible` | Local private module target exists |
| Reference `Display` | `src/lib.rs:16` | unresolved / `import_unresolved`, underlying import reason `external` | Standard-library target is outside this source index |
| Type use `Thing` | `src/lib.rs:19` annotation | unresolved / `type_parameter` | Local generic binding; not a missing declaration |
| Type use `Thing` | `src/lib.rs:19` return | unresolved / `type_parameter` | Same local generic binding |

The external import is one import observation and contributes one unresolved reference. The four unresolved references are `Shared`, `Choice`, `Hidden`, and `Display`; the two unresolved type observations are the annotation and return uses of the generic parameter. These are not six claims of a missing target.

The graph-free source response to the initial request has a complete `src/lib.rs` item but reports `unsupported_semantics` because it does not resolve relationships. Subsequent exact-file responses have complete source extents for `src/model.rs` and `src/private_api.rs`. These packets show successful source acquisition; their completeness does not answer the native resolution question.

## Retained corpus classification

Counted once per case from the 36 first-use native case indexes in `full-source-demand` (`variant-1-suite-0` and `variant-1-suite-1`), excluding `.repeat` indexes. Only JavaScript, TypeScript, and Rust records are included; these are native unresolved observations, not packet omission counts or unique underlying bugs.

| Record family and native unresolved reason | Count |
| --- | ---: |
| Imports: `external` | 74 |
| References: `ambiguous_source` | 37 |
| References: `ambiguous_target` | 3 |
| References: `configuration_divergent` | 1 |
| References: `target_inaccessible` | 1 |
| References: `binding_shadowed` | 3 |
| References: `import_unresolved` | 366 |
| References: `target_not_indexed` | 40 |
| References: `unsupported_reference` | 1 |
| Types: `ambiguous_target` | 1 |
| Types: `binding_not_found` | 174 |
| Types: `binding_unindexed` | 3 |
| Types: `target_not_indexed` | 7 |
| Types: `type_parameter` | 11 |
| Types: `unsupported_owner` | 94 |
| Types: `unsupported_syntax` | 19 |

Separate from unresolved status, configuration-sensitive resolved records marked `declared_possible` occur 3 times for imports, 2 for references, and 2 for type relations. This describes candidate configuration possibility, not active-feature resolution. Counts are record counts and include separate source occurrences; they are not normalized to distinct names or causes.

Python and Go are unsupported by the R0.5 demand semantic resolver. The retained corpus has 25 authored positive links in those languages, which receive no semantic credit; they must remain an explicit unsupported-language boundary, not be folded into native unresolved counts.

## Minimal consumer-facing treatment

Keep source navigation independent and available from the packet. When semantic proof is requested, expose unresolved native observations alongside proven relationships as a separate, non-claiming uncertainty list. The smallest useful record preserves:

- relation family and source symbol/file/line (and source text span when present);
- native `status`, `unresolved_reason`, and `import_unresolved_reason` without collapsing them;
- candidate IDs and candidate scope/completeness for ambiguous or unindexed outcomes;
- `resolution_configuration`, `resolution_control_files`, and control hashes where supplied;
- evidence source references for the observation and any available import/module support.

Do not turn unresolved outcomes into edges, treat `declared_possible` as active, or infer exhaustive absence from a complete source item, `scope.coverage=complete`, or `omissions=[]`. Keep the list explicitly scoped to the selected anchor, parsed slice, and supported languages.

A focused acceptance check should use this retained uncertainty case: confirm `probe` source navigation still returns its complete source item; confirm the two proven `Thing` relations remain complete; and confirm the optional uncertainty view preserves one external import, four unresolved references, two generic type-parameter observations, the `Choice` configuration divergence, and the exact native reasons above. Verify that no unsupported-language or exhaustiveness claim is introduced. This is a review recommendation only; no new measurement or implementation was performed here.

## R0.6 consumer uncertainty verification

Added the novel, gold-free Rust fixture in `tests/test_focused_uncertainty.py`. It exercises ambiguous aliases, inaccessible private type, external standard-library import, cfg-divergent alias, generic type parameters, and a `declared_possible` relation. The test derives expected family/reason/category totals directly from the retained native index, checks examples are capped at eight with `examples_omitted`, confirms uncertainty scope is non-exhaustive, and checks both initial and same-slice focused packets retain uncertainty. It also checks that uncertainty makes packet status and consumer coverage partial while preserving a complete source item and `resolution_configuration="declared_possible"`.

Verification passed: `PYTHONPATH=src /Users/brummerv/phluxxed/loci/.venv/bin/python -m pytest tests/test_focused_uncertainty.py -q` → `1 passed`. No source or scorer changes were made by this test assignment. A first fixture draft put `Hidden` in a public child module, which correctly resolved from the crate root; making the child item private produced the intended native inaccessible observation. The cfg-possible type was attached to the selected `probe` function so the packet could exercise that relation field directly.
