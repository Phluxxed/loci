# W4.4 — Go type and embedding context

Task: `task_5eb1f78e6e2a876259dd9bf3b170288d`.

Starting exploration at `Build` now returns `AliasID`, `UserID`, `Page` and
`Number`, with their exact declarations and the import, package clause and
module source proving their origin. Starting at `Entity` supplies its explicitly
embedded `Audit`; starting at `Combined` supplies `Runner`.

This implementation remains on `feat/evidence-backed-exploration`. Acceptance
uses the unchanged [W4.1 cases](../design/2026-09-12-multilingual-context-cases.md).

## Supported meaning and proof

Go uses the shared `type_dependencies` and `dependencies` intents for declared
type context. `uses_type` records named signature, field, alias/defined-type,
generic argument and constraint dependencies. `embeds` records an authored
struct field or interface element, distinguished by `struct_embedding` and
`interface_embedding` contexts. It creates no class inheritance, implicit
interface satisfaction, inferred method set or promoted-member call target.

The parser preserves the type-spec source: `AliasID = UserID` remains distinct
from `UserID int64`. Grouped aliases are indexed with their exact native spans.
Local types retain their indexed owners; anonymous function signatures retain
an unindexed owner. Generic parameters block repository guesses. Parameter and
local declaration activation follows the
[Go scope rules](https://go.dev/ref/spec#Declarations_and_scope), including
body-only parameter scope and all names in grouped parameter declarations.

Exact local bindings use the existing lexical proof. Bare package names resolve
against declarations in the same directory and consistent declared package,
including private types across files. Receiver methods and function-local types
are excluded from that package surface. Imported types reuse existing contained
module/workspace/replacement routing, then require an exported type in the exact
target package. An implicit import name is matched to the declared package name,
never the directory basename. Duplicate names and conflicting packages remain
unresolved. No Go compiler, module download, ambient cache or repository code is
executed to resolve a type.

Build directives, cgo source and known platform filename suffixes are
conservatively unsupported for new exact type claims. No active configuration
or convergence evaluation is attempted. Builtins, generic parameters,
approximation/union terms, dot/blank imports, external targets and unproven
qualified names cannot acquire guessed repository endpoints.

The shared type records retain occurrence and owner spans, candidate scope,
definition and package support, and resolver-control hashes. Cache validation
reconstructs each result and requires the complete projected type edges. A
package endpoint cannot redirect lookup to a different directory with the same
package name: its directory must match its indexed anchor file.
Exploration delivers complete grouped imports and full `go.mod`/`go.work` bytes.
Go call/reference impact paths receive package and module evidence too. Control
reads are contained, bounded and hash checked; missing, changed or escaping
sources omit the proof. The current conservative control set includes all
indexed Go resolver controls, which can consume more evidence on larger trees.

## Frozen acceptance

| Case | Delivered and checked |
| --- | --- |
| `go_alias_generic_contract` | `Build`, both alias/defined types, `Page`, `Number`, and complete import/package/module proof. |
| `go_explicit_embedding` | `Start`, `Entity`, `Audit`, `Combined`, `Runner`; explicit embeddings retain Go meaning and `e.Stamp()` remains unproven. |
| `go_known_api_impact` | Incoming `Serve`/`Work` call paths preserve caller-to-callee direction; a separate dependency request supplies `Request`. |
| `go_unproven_package_uses` | `Keep -> Request` is proven; shadowed, ambiguous, external and wrong-origin calls remain diagnostics. Changing `go.mod` invalidates the old type route. |

All four cases retain required source within the unchanged 8192-byte evidence
and 16384-byte complete-result budgets. Each delivered definition has exact
bytes/hashes and one selected proof path. Reduced and zero evidence budgets
retain truthful omissions. The actual stdio MCP check validates Go exploration,
embedding diagnostics, strict schemas and exact complete-result byte accounting.

## Validation and next work

The focused compatibility run passes **476 tests**, covering Go acceptance,
type parsing/resolution/models, source hydration and packet accounting, existing
imports/references/module routing, and TypeScript/Python/JavaScript delivery.
Eight additional stdio checks pass for Go and existing type/get/exploration
tool boundaries. One stale invalid-intent assertion was updated to include the
already supported `dependencies` intent. Freshness
checks cover source/target edits, package candidate changes, `go.mod`, `go.work`
and contained replacement routes. Extractor version 28 invalidates old caches;
the stored graph schema and record fields remain unchanged. The focused final
resolver/storage run passes 69 tests, including a modified-package-metadata replay
regression and old-extractor rejection.

The frozen corpus remains 19 cases and 16 snapshots. This is source-delivery
acceptance; usefulness measurement and its implementation/schema/model/provider/
scorer freeze remain W4.7 work. Shared runtime integration remains separate.

Next: W4.5 Rust, `task_9a6c46f91458e3b44d5a46977af6fb97`.
