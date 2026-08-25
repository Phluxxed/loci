# Swift graph support

**Status:** `swift-extract` and `swift-local` landed on branch `swift-graph-support`
(`265a08f`, `a4d6c4e`, `c56c83d`, after the `else`-chain conversion in `c79147c`).
`swift-modules` stage 1 (manifest reader and module index) landed; its contract
widening and `swift-resolve` not started.
**Author:** Claude, 2026-08-24, at Vik's request.
**Prior art:** `docs/plans/2026-07-15-extensible-graph-retrieval-stage-7-go-import-resolution.md` — read its "Exact File Plan" (lines 888–919) before writing code. Swift should mirror Go, not Rust.

## Objective

Swift symbol extraction already works: a `LanguageSpec` at `src/loci/parser/languages.py:132-158` plus a
`.swift` row in `EXTENSION_MAP` indexes 42,145 symbols across 4,505 files of `lott-ios`, and `outline`, `get`,
`search` and `grep` all function. The graph layer does not: every Swift file raises during import or reference
extraction, so `loci_graph_*` returns nothing and `graph_status` is pinned to `degraded` for any repository
containing a single `.swift` file.

Goal: Swift reaches parity with Go — module-level import edges, same-file exact call edges, cross-module symbol
reference resolution, and a `healthy` graph status.

### Why this is worth doing

Measured on `lott-ios` against ground truth (13,631 line-level citations in 96 human-written feature specs, each
naming the exact files it drew on):

| | |
|---|---|
| Swift files under `source/` | 4,364 across 45 module owners |
| Share of files in the single largest module (the xcodeproj app target) | 58% (2,522 files) |
| Cited file-pairs that cross a module boundary — **visible** to an import-rooted graph | **65%** |
| Cited file-pairs inside one module — **invisible** | 35% |
| Features whose entire cited set sits in one module | 1 of 96 |

So roughly two thirds of the real file-to-file relationships in this codebase are cross-module and therefore
reachable. That is the payoff. State the other third as a known ceiling, not a defect.

### The ceiling, stated up front

loci's reference graph is **import-rooted**: `RawSymbolReference.candidate_bindings` cannot be empty
(`src/loci/parser/reference_models.py:268-269`), so a cross-file reference is only discoverable via an import
binding. Swift files in the same module reference each other with no `import` statement at all. Intra-module
cross-file references will therefore be structurally invisible — exactly as intra-package Go references are
today. This is a property of the architecture, not of the Swift implementation, and it is not in scope to change.

## What landed, and where the spec was wrong

Measured, not estimated. All figures are `lott-ios` after the work below.

| | |
|---|---|
| Swift files extracting cleanly | 4,410 of 4,486 |
| Imports recorded | 12,126 |
| Call sites recorded | 126,897, of which 656 resolve |
| References recorded | 437, of which 37 resolve |
| Edges | 1,100 |
| `graph_status` | `healthy` |

Four corrections to this document, each forced by something the build hit:

1. **`swift-extract` could not reach `healthy` as specified.** 116 files (2.6%) hit
   `tree.root_node.has_error`, which raised `ImportExtractionError` and degraded the whole
   repository. That conflates a grammar gap with a graph defect. `extract_import_batch` now raises
   `SourceParseError`, reported as an **`info`** `GRAPH_SOURCE_UNPARSED` diagnostic; genuine
   extraction failures keep `warning` severity and still degrade.
2. **The grammar was nine months stale.** `tree-sitter-language-pack` was pinned `>=0.7.0` with no
   lockfile, so the venv sat on 0.13.0 (2025-11-26) against 1.15.8. Upgrading dropped Swift parse
   failures from 116 to 76 (47 fixed, 7 newly broken) with **zero** node-type drift over the
   python, javascript, typescript, go and rust fixtures. 1.x downloads grammars on first use, so a
   cold cache needs network.
3. **Spec item 7 (split `extension` and `actor` from `class`) is not a spec edit.**
   `symbol_node_types` is a flat node-type-to-kind dict, and tree-sitter-swift emits
   `class_declaration` for class, struct, enum, extension **and** actor, distinguished only by the
   first keyword child. This needs a keyword-dispatch mechanism or an extractor branch. Not done;
   struct and enum are also still mislabelled `class`.
4. **`import struct Foundation.Data` binds the declaration, not the module.** Binding it as
   `Foundation` collided with a real `import Foundation` and turned shadow detection into
   `ambiguous`. Declaration-kind imports now bind the last component with `kind="symbol"`.

## Capability map

| Module id | Responsibility | Depends on |
|---|---|---|
| `swift-extract` | Clean import/reference/call extraction; no raises; Swift repos reach `healthy` | — |
| `swift-local` | Lexical binding + shadowing model; same-file exact call and reference edges | `swift-extract` |
| `swift-modules` | `Package.swift` → target index; synthesize `kind="module"` nodes; module-level import edges | `swift-extract` |
| `swift-resolve` | Cross-module symbol reference and call resolution against the module index | `swift-local`, `swift-modules` |

Build order: `swift-extract` → `swift-local`, `swift-modules` (parallel) → `swift-resolve`

`swift-extract` alone removes the permanent `degraded` status and is independently shippable. `swift-modules` is
the largest and riskiest and can be cut without invalidating the other three.

---

## Module: `swift-extract`

Make every Swift file extract cleanly, recording honest `unresolved` records rather than raising.

### Where it currently dies

- `src/loci/parser/imports.py:253` — `_extract_node_imports` if/elif falls through → `ImportExtractionError("unsupported language: swift")`. Any Swift file containing an `import`.
- `src/loci/parser/_binding_context.py:137-138` — `collect_syntax_context` raises `ValueError`. Any Swift file *without* an import.

Both surface via `service.py:346-350` → `_extraction_diagnostic` (`service.py:2148-2169`) as
`GRAPH_IMPORT_EXTRACTION_FAILED` / `GRAPH_REFERENCE_EXTRACTION_FAILED`, and `_graph_status`
(`service.py:1899-1904`) degrades on any warning.

### Work

1. `_extract_swift_import()` in `parser/imports.py`, returning `list[RawImport]`. Swift imports are flat module
   names — `import Foundation`, `@preconcurrency import RxSwift`, and submodule form `import UIKit.UIView`. 12,268
   of them in `lott-ios`. One `ImportBinding` per import with `kind="module"`, `module_level=True`.
2. Add `"swift"` to `_import_is_module_level` (`parser/imports.py:893-905`) — it falls through to `False`, which
   would mark every binding non-module-level. `_import_scope_node` (`:908-925`) can keep the file-root default.
3. `_collect_swift_context()` registered in `parser/_binding_context.py:146-153`, plus `callable_types` (`:236-242`)
   and `unindexed_types` (`:243-259`) entries — both are `[language]` lookups that raise `KeyError` when missing.
   For `swift-extract` a minimal collector is enough; the real model is `swift-local`.
4. Add `"swift"` to the gates: `parser/references.py:56-57`, `parser/calls.py:22` (`_SUPPORTED_LANGUAGES`),
   `parser/calls.py:23-29` (`_CALL_NODE_TYPES` → `{"call_expression"}`), `parser/call_models.py:42`
   (`_SUPPORTED_LANGUAGES`, a hard `ValueError` in `__post_init__` otherwise), `graph/references.py:691-698`,
   and a `_swift` field on `ReferenceResolverIndex` (`graph/references.py:400-415`).
5. `graph/imports.py:444-568` — a `swift` branch in `_resolve_import` returning
   `unresolved_reason="external"` for now. Unresolved records produce no diagnostics, so this is enough to reach
   `healthy`.
6. Bump `EXTRACTOR_VERSION` (`src/loci/storage/index_store.py:29`, currently 12) to force reindex.
7. Correct the existing `LanguageSpec`: `extension` and `actor` both currently report `kind="class"`. Split them —
   `lott-ios` has 2,623 extensions and 30 actors.

### ⚠ The trap that must be handled first

Five if/elif chains end in a bare `else` that means **Rust**:

| Site | Bare `else` currently means |
|---|---|
| `parser/_binding_context.py:152-153` | Rust context collector |
| `parser/_reference_exports.py:87-94` | Rust local exports |
| `parser/references.py:400-405` | Rust path observation |
| `parser/calls.py:119-120` | `_rust_path` callee classifier |
| `graph/references.py:728-738` | Rust reference resolution |

Adding Swift without first converting each to an explicit `elif language == "rust"` will silently route Swift
through Rust logic and emit **wrong records that pass validation**. Do this conversion as the first commit, on its
own, with the existing Rust tests as the guard.

### Acceptance

- `loci index` over `lott-ios` reports `graph_status: "healthy"`, zero `GRAPH_*_EXTRACTION_FAILED` diagnostics.
- 12,268 Swift `ImportRecord`s exist, all `status="unresolved"`, `reason="external"`.
- Existing Go/Rust/JS/Python graph tests unchanged and passing.

### Verify

`.venv/bin/pytest tests/parser tests/graph -q` plus `loci index <lott-ios> | jq '.graph_status, .graph_diagnostics|length'`

---

## Module: `swift-local`

A correct Swift lexical binding and shadowing model, giving same-file `exact` call and reference edges.

Reference implementations: Go's collector at `parser/_binding_context.py:667-757`, Rust's at `:773+`.

Swift specifics to model: `let`/`var` declarations, function and initializer parameters (including argument
labels vs. internal names), closure capture lists and `$0` shorthand (`lambda_literal`), `guard let` / `if let`
optional bindings that shadow the outer name, `self`, computed-property accessor scopes, and `case let` pattern
bindings.

Also needed: `_extract_swift_exports()` for `parser/_reference_exports.py`, honouring Swift's five visibility
levels (`open`, `public`, `package`, `internal`, `fileprivate`/`private`) — only `public`/`open`/`package` are
importable across a module boundary. And a `swift` branch in `_path_observation`
(`parser/references.py:372-406`) for `navigation_expression` / `simple_identifier`, and `_swift_path()` in
`parser/calls.py:105-123`.

### Acceptance

- Same-file Swift calls resolve with tier `exact` via `local_candidates`.
- A `guard let x = x` shadow produces `binding_state="shadowed"`, not a false `definite`.
- Exported-name extraction marks `private`/`fileprivate` declarations non-exported.

---

## Module: `swift-modules`

`Package.swift` → target index, `kind="module"` node synthesis, module-level import edges. Mirror
`graph/go_modules.py` (1,145 lines) — that is the realistic size.

`lott-ios` has 51 `Package.swift` files plus one `.xcodeproj`. A package declares `targets: [.target(name:…)]`
with an optional `path:`, defaulting to `Sources/<target>`; dependencies are `.product(name:package:)` or bare
target-name strings. Targets, paths and inter-module dependencies are all extractable — `Package.swift` is itself
Swift, so the grammar already in place parses it.

### Risks, and they are the real ones in this project

1. **`Package.swift` is executable Swift, not declarative TOML/JSON.** `go.mod` and `Cargo.toml` can be parsed
   exhaustively; a `Package.swift` can compute its target list at runtime. Parse the common literal form, and
   record an explicit `unsupported_configuration` unresolved reason when the declaration isn't statically
   readable. Do not attempt evaluation.
2. **The 58% of files that aren't in any SPM package.** The app target is an xcodeproj, not a package. Either
   synthesize a single implicit module for it from the `.xcodeproj`, or treat those files as module-less. This
   choice decides whether the largest module participates at all, so decide it before writing code.
3. **Introducing `kind="module"` widens the contract.** It needs: `ImportTargetKind` (`graph/imports.py:50-56`),
   the language↔target-kind rules in `ImportRecord.__post_init__` (`graph/imports.py:190-229`), a
   `_validate_swift_module_endpoint` in `graph/contracts.py:500-681`, a `materialize_import_edges` branch
   (`graph/imports.py:571-701`), a `swift_modules=` parameter threaded through `graph/materialize.py:229-358`, a
   `GraphIndexState` field and `GRAPH_STATE_SCHEMA_VERSION` bump (`graph/contracts.py:34`, currently 9), a
   `graph_health` count (`mcp_output_models.py:~720-737`), a `retrieval.py` node-attribute enricher alongside
   `_add_go_package_node_attributes` (`retrieval.py:1032-1057`), and a `Package.swift` control-file channel in
   `RepositoryScan` (`service.py:102-106`, `:2050-2065`).

### Acceptance

- All 51 `lott-ios` packages resolve to module nodes with correct target→directory mappings.
- `import LegacyLottoKit` from an app-target file produces a resolved import edge to that module node.
- A `Package.swift` that computes its targets dynamically yields `unsupported_configuration`, not a crash.

### Stage 1 landed — manifest reader and module index

`src/loci/graph/swift_modules.py`. Measured over `lott-ios`, 2026-08-25:

| | |
|---|---|
| Manifests read | 51 |
| Packages accepted | 50 |
| Module nodes | 87 |
| Swift files under a module directory | 1,873 of 4,486 (41.8%) |
| `import` statements naming a declared target | 4,071 of 10,763 (37.8%) |

That 37.8% is the ceiling for module import edges; the remainder are system
frameworks (`Foundation` 2,316, `XCTest` 1,107, `UIKit` 1,006) and external SPM
dependencies, which correctly stay `external`.

Four problems, all genuine, none a crash:

- `DangerSwiftPeriphery/Package.swift` builds its target list as
  `[.target(...)] + developTargets`, where `developTargets` is computed from a
  variable. This is risk 1 above, occurring exactly once in 51 manifests. The
  whole package is refused as `unsupported_configuration` rather than
  partially read — a partial read silently omits targets.
- `LottoRESTUtil` declares two targets and ships no sources at all
  (`target_directory_missing`). The module nodes are kept, since the module is
  still importable, with `has_sources: false`.
- `LottoRESTConfig` is declared by two different manifests, so an `import` of
  that name cannot be attributed. Both are dropped, not arbitrated.

Two layout details the plan did not anticipate, both found by measurement:

- A target with no `path:` does not always live in `Sources/<name>`. SwiftPM
  also accepts the bare `Sources` directory when the package declares one
  target of that class, which is how `FeatureRetail` and several others are
  laid out. Without that fallback, 15 of 103 targets resolved to nothing.
- `path: ""` means the package directory, and appears in this corpus.

The target scan is deliberately confined to the elements of the `targets:`
array. A first version walked the whole manifest and read the
`.plugin(name: "OpenAPIGenerator")` entries inside a target's own `plugins:`
list as target declarations — eight false modules. A test pins the scoping.

### Stage 2 landed — contract widening and module import edges

`ImportTargetKind` gains `"module"`, `ImportRecord` gains `target_module`, and
a Swift `import` naming a declared target resolves to that module node. A
declaration import (`import struct LottoCore.Ticket`) still names its module
first, so the leading dotted component is the module either way.

| | before | after |
|---|---:|---:|
| Swift imports recorded (lott-ios) | 12,062 | 12,062 |
| Resolved | ~0 | 5,029 |
| Module import edges | 0 | 5,011 |

The remaining 7,033 are `external` — system frameworks and third-party SPM
packages, which is the correct answer, not a failure.

One claim in the plan was wrong: **no `GraphIndexState` field is needed.**
Module nodes ride in the index's `symbols` exactly as Go package nodes do, and
the go/rust indexes are rebuilt from control files at index time rather than
persisted. `GRAPH_STATE_SCHEMA_VERSION` still goes 9 to 10, but for a different
reason than the plan gave — the persisted `ImportRecord` gained a key.

`_validate_swift_module_endpoint` refuses any module edge whose endpoint is not
a manifest-declared target node, mirroring the Go package check.

---

## Module: `swift-resolve`

Cross-module reference and call resolution: `_swift_references.py`, mirroring `graph/_go_references.py`
(274 lines — the realistic floor). Build an index of importable declarations keyed by
`(module_id, name)`; resolve a reference by taking the name, the set of modules the file imports, and the
visibility rules from `swift-local`.

Swift's hard case, and it has no analogue in Go: **2,623 extensions spread 1,232 distinct types across arbitrary
files** in `lott-ios` — `ScreenFactory` is extended in 113 separate places. A type's members are not one
contiguous span, so `(module_id, name)` may legitimately map to many files. Decide explicitly whether an
extension member resolves to the extension's own span or to the base type's declaration, and record `ambiguous`
rather than guessing when both are plausible.

### Acceptance — this is the eval, and it has real ground truth

The 96 finished feature specs in `palo-discovery` cite 13,631 exact `file#Lnnn` locations. For the 65% of cited
file-pairs that cross a module boundary, measure what share the graph recovers as edges.

- Target: recover ≥50% of cross-module cited pairs as `references` or `calls` edges.
- Report intra-module pairs separately as the known-invisible 35%; they are not failures.
- Run the eval against a deliberately broken index first and confirm it scores near zero — a check that has never
  failed is unverified.

---

## Tests

There is no shared conformance harness; per-language coverage is hand-written and distinguished by test-name
prefix. Mirror that exactly:

- `tests/fixtures/sample.swift` (one flat file, for extractor tests).
- `test_swift_*` cases added to `tests/graph/test_imports.py`, `tests/graph/test_references.py`,
  `tests/graph/test_calls.py`, `tests/parser/test_imports.py`, `tests/parser/test_references.py`,
  `tests/parser/test_calls.py`, `tests/parser/test_languages.py`.
- `tests/graph/test_swift_modules.py` — only if `swift-modules` is in scope; mirror `test_go_modules.py` (1,003 lines).
- Integration coverage in `tests/test_service.py` and `tests/test_mcp_server.py`.
- Assert the `EXTRACTOR_VERSION` bump in `tests/storage/test_index_store.py`.

Graph tests build no fixture trees — they construct `RawImport`/`Symbol` objects in-process via local helpers
(`tests/graph/test_imports.py:54-88`). Follow that, and use `tmp_path` for real `Package.swift` files when
testing the control-file loader.

## Not required

`graph/profiles.py`, `graph/builtins.py`, `graph/anchors.py`, `graph/traversal.py` need no Swift entry — profiles
and builtins are the markdown/wiki extension system (`GraphNodeSelector` hard-asserts `language == "markdown"`),
and traversal is pure edge algebra. `graph/retrieval.py` needs an entry only if `kind="module"` is introduced.

## Boundaries

- **Always:** convert the five bare-`else`-means-Rust chains to explicit `elif` before adding any Swift branch;
  run the full existing suite after each module; keep unresolved records honest rather than guessing a target.
- **Ask first:** introducing `ImportTargetKind="module"`; bumping `GRAPH_STATE_SCHEMA_VERSION`; any change to
  `ImportRecord`/`SymbolReferenceRecord` invariants; adding a dependency.
- **Never:** evaluate `Package.swift`; emit a resolved record you can't cite with `GraphEvidence`; widen the
  provenance allowlist (`graph/references.py:234-238`) to make a test pass.

## Effort, honestly

| Module | Estimate | Risk |
|---|---|---|
| `swift-extract` (incl. the `else`-chain conversion) | 1–2 days | low |
| `swift-local` | 1–2 weeks | medium — correct shadowing is fiddly, well-tested elsewhere |
| `swift-modules` | 1–2 weeks | **high** — executable `Package.swift`, contract widening, the 58% xcodeproj question |
| `swift-resolve` | 1 week | medium — extensions complicate `(module, name)` |

Vik's read was that this should be relatively easy given the other languages to copy. That holds for
`swift-extract` and largely for `swift-resolve`; it does not hold for `swift-modules`, because Go and Rust both
get a declarative manifest and Swift does not. Rust's graph support is ~4,200 lines across six files, Go's ~1,400
across two, JS's ~2,770 across three — Swift lands between Go and Rust.

## Open questions

1. ~~Does the 58% of files in the xcodeproj app target get a synthesized implicit module, or stay
   module-less?~~ **Answered, and it does not decide whether the largest module participates.**
   Measured over the citation corpus: of 47,843 cited file-pairs, 34.6% are intra-module, 44.9%
   pair an app-target file with a package file, and 20.5% pair two packages — reproducing the 65%
   cross-module figure above exactly. `resolve_go_reference` (`graph/_go_references.py:195-229`),
   the model Swift copies, keys only on `import_record.target_id` and the name; it never consults
   the importing file's own module. A Swift package cannot import an app target, so the app-target
   file is always the importer. Those 44.9% therefore resolve with **no** synthesized app-target
   module, and the ceiling stays near 65%. Module synthesis is an optimisation, not a gate.
2. Ship `swift-extract` alone first to clear the `degraded` status, or hold everything until `swift-resolve`?
3. Is the ≥50% cross-module citation-recovery target the right bar, and is `lott-ios` the right eval corpus given
   it is the only large Swift repo we have ground truth for?

## After implementation: member-scope resolution

Not Swift work, and deliberately out of scope here — recorded because `swift-local` is what exposed
it.

Over `lott-ios`, 126,897 Swift call sites yield 656 resolved. The reason is not Swift: a call's
candidates come only from import bindings and file-scope lexical bindings, so loci has no concept of
**member scope** at all. A bare `record(value)` inside `Widget`, meaning `self.record`, has nowhere
to resolve to, and neither does `self.record()`. Every language whose dominant call form is a method
on a receiver hits the same wall — Python `self.x`, Rust `impl` blocks, Go methods, TypeScript class
members.

The general fix is to let the enclosing type contribute candidates, driven by the parent/container
information the symbol table already records, rather than adding a Swift rule to the resolver. It
changes the call resolver's scope model, so it wants its own spec, and it must be measured across
all six languages rather than on Swift alone. Two things to settle first:

- Confirm how parent/container is stored for Swift methods, and whether extensions of the same type
  in other files break the parent link.
- A type's members can also arrive from an extension elsewhere or an inherited superclass, so where
  one file cannot settle the target the record must say `ambiguous` rather than pick.
