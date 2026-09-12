# Rust type, trait and implementation context

W4.5 (`task_9a6c46f91458e3b44d5a46977af6fb97`) delivers the Rust portion of the
[frozen multilingual contract](../design/2026-09-12-multilingual-context-cases.md)
on the isolated `feat/evidence-backed-exploration` branch.

## Delivered behavior

Both `type_dependencies` and `dependencies` select authored Rust type contracts.
The `UserId` alias now has an exact indexed declaration. Signature and field
types, alias definitions, generic arguments and bounds, direct supertraits and
explicit implementation sites retain their own declaration owners.

| Relation | Stored direction and meaning |
| --- | --- |
| `uses_type` | Declaration to a named authored type dependency. Context distinguishes annotation, return, property, alias, type argument and constraint. |
| `supertrait` | Trait to an explicitly required trait. |
| `impl_trait` | Separate implementation site to its implemented trait. |
| `impl_self_type` | Separate implementation site to its declared self type. |

Dependency selection may traverse `impl_self_type` in reverse to find explicit
sites for a selected type, then follow their outgoing contracts. The packet
retains the original edge and reports reverse traversal. It does not enumerate
every implementing type or prove trait-object dispatch, monomorphization,
promoted methods, inferred satisfaction or a runtime call target. Incoming
impact retains the existing caller-to-callee direction.

Local targets come from exact lexical declarations. Associated types do not leak
into the surrounding module as bare names, child modules do not inherit parent
module bindings, and generic parameters/`Self` block same-name repository types.
Trait-only positions reject a same-name struct. Imported contracts join the
existing visibility-checked Rust item reference at the identical source span,
path and import binding; executable ownership from that reference never replaces
the type declaration owner. Unsupported associated projections cannot borrow a
containing type's endpoint.

Rust records carry `resolution_configuration`: `unconditional` or
`declared_possible`. The latter preserves optional Cargo dependencies and
conditional items, enclosing declarations and external modules. No active
feature/target/profile is selected. Configuration-divergent routes, ambiguous
namespace imports, inaccessible items and external crates remain diagnostics.

Definitions retain exact search/get spans and file hashes. Exploration hydrates
complete authored import/re-export/module proof and Cargo control bytes. The
type family conservatively carries every indexed `Cargo.toml`; this is bounded
and may consume more of the retrieval budget in a large workspace. Source,
target, resolver control and declaration-configuration changes refresh proof.
Serialized type replay must match the accepted reference and current binding
evidence; altered targets or configuration are rejected.

Extractor version 29 invalidates prior extraction caches. Persisted graph schema
14 adds the type record configuration field. The public exploration envelope
remains version 1 with an optional relationship configuration field.

## Frozen cases

| Case | Acceptance |
| --- | --- |
| `rust_authored_trait_contract` | `build`, `UserId`, `Envelope`, `Render`, `Format`, `Receipt` and both full impl sites, with Cargo proof. The bound/impl declarations identify no dynamic call target. |
| `rust_contained_optional_reexport` | `use_it` and the exact `core/src/api.rs::Thing` origin, complete import/re-export/module and workspace/package manifests. Removing `optional = true` refreshes configuration from possible to unconditional. |
| `rust_known_call_impact` | Exact `parse` and incoming `caller` source with module/import/Cargo proof; the separate dependency request delivers `Config`. |
| `rust_unproven_contracts` | `probe` reaches the contained `Thing`; generic `Thing` stays shadowed. Existing diagnostics distinguish `Shared` namespace ambiguity, divergent `Choice`, inaccessible `Hidden` and external `Display`. No macro call target is invented. |

Positive definition and proof delivery stays within 8,192 evidence bytes and
16,384 serialized MCP bytes. Reduced and zero budgets produce explicit omissions.
The four frozen cases and source archives are unchanged. Negative-case diagnostic
source is not promoted to a proven target merely to increase source recall.

## Verification

- Combined focused compatibility and actual stdio run: **749 passed**. This
  covers Rust extraction/contracts, the frozen Python/JavaScript/Go controls,
  type record/schema/replay, search/get and exploration selection/wire output,
  existing imports/references/calls, Cargo/module resolution and storage.
- After the final unowned-file guard, the complete Rust slice passed **23
  checks** across `test_rust_declaration_extraction.py`,
  `test_rust_type_observations.py`, `test_rust_type_resolution.py`,
  `test_rust_context_delivery.py`, `test_rust_control_evidence.py` and
  `test_rust_context_mcp.py`. These sets overlap.
- The combined run includes **nine actual stdio checks**. Rust's boundary test
  verifies strict schemas, exact source bytes/hashes, implementation sites,
  optional workspace configuration and the actual serialized `CallToolResult`
  byte accounting at full, reduced and zero budgets.
- Direct proof checks cover nested external modules and multiline imports,
  cfg attribute delivery, source/target/configuration refresh, changed/missing/
  escaping Cargo controls, and rejection of modified stored type targets or
  configuration. Corpus integrity checks remain active and no corpus file
  changed; `git diff --check` passes.

The bounded review corrected an associated-type lexical leak, inherited
conditional-module configuration and proof, and the acceptance of local
contracts in files without declared crate/module ownership. Such unowned files
remain navigable but produce no trusted type edge. Exact metadata and persisted
schema assertions were updated for the deliberate new fields/version.

## Limits and next work

This is authored source delivery acceptance, with no provider outcome, task edit
success or causal cost claim. No Cargo/rustc, macro, build script, repository
code, crate fetch or ambient toolchain access is introduced into indexing.
Unproven direct `crate`/`self`/`super` type paths, associated projections,
generated types and inferred runtime behavior remain outside this type slice.
The existing imported-reference resolver retains its own bounded behavior.
Rust files without proven Cargo target/module ownership remain unsupported for
exact type relations.

Next is W4.6 shared interface verification
(`task_5463db0ee464fec8e1bc4db41ab17986`), including the recorded TSX `Badge`
extraction repair. Final implementation/schema/provider/scorer freezing and
usefulness measurement remain W4.7. The prior TypeScript benchmark verdicts and
the discontinued reliability study are unchanged. Runtime promotion remains a
separate decision.
