# Language-specific resolution

## Contents

- Exploration capabilities
- Measured workflow scope
- JavaScript and TypeScript
- Go
- Rust

Treat unresolved, ambiguous, external, inaccessible, unsupported, and
unsupported-configuration observations as bounded records with an explicit
`unresolved_reason`; they never become graph edges. Invalid controls degrade
graph health. Inspect aggregate file-node, Go-package, Rust-crate, and import
counts with `loci_graph_health`.

## Exploration capabilities

This matrix describes the implemented exploration branch. **Bounded** means
the listed source-proven subset, with uncertainty and delivery omissions; it
does not mean full language semantics. All five programming-language families
share the packet interface, source hashes and budget accounting. Markdown is
an additional navigation control.

| Language | Search/get and `locate` | `type_dependencies` | `dependencies` | `impact` |
| --- | --- | --- | --- | --- |
| Python | Exact indexed functions, classes and supported explicit aliases | Bounded annotations, alias definitions, generic arguments, literal bare/dotted forward names and direct bases | Same contract selection | Known incoming calls, imported references and authored type/base users |
| JavaScript | Exact indexed functions, methods, classes and named arrows | Unsupported; direct bases are available through `dependencies` | Bounded definite calls, declaration-owned imported values and direct class bases | Known incoming calls, imported references and direct-base users |
| TypeScript/TSX | Exact indexed declarations; `.tsx` uses JSX-aware grammar with TypeScript language identity | Bounded authored types, aliases, generic contracts, type queries and explicit `extends`/`implements` | Same contract selection | Known incoming calls, imported references and authored type/heritage users |
| Go | Exact indexed functions, methods and native type specifications, including aliases | Bounded signature/field/alias/generic uses and explicit struct/interface embedding | Same contract selection | Known incoming calls, package-qualified references and authored type/embedding users |
| Rust | Exact indexed functions, types, traits, aliases and separately owned impl sites | Bounded authored types/bounds, supertraits and impl-to-trait/self-type links; self types can select explicit impl sites in reverse | Same contract selection | Known incoming calls, imported references and authored contract users |
| Markdown | Exact headings and nested section spans | Unsupported | Unsupported | No programming-language impact claim; use navigation |

`impact` is non-exhaustive for every language. JSX syntax alone establishes no
component call. All traversals retain the original stored edge direction and
label the traversal direction separately. Question terms guide deeper contract
branches; selection does not increase relationship certainty.

| Language | Origin evidence delivered by exploration | Partial or unsupported behavior |
| --- | --- | --- |
| Python | Exact lexical declarations and contained import/re-export statements | Only uniquely bound supported `TypeAlias` markers and plain literal forward names; no annotation evaluation, compound forward strings, computed bases, MRO or Protocol/ABC inference |
| JavaScript | Exact local or contained ESM declaration and complete import/re-export statements | Resolver controls affect validation/refresh but their full source is not in the packet. No JSDoc type extraction, computed/dynamic imports or calls, CommonJS member inference, prototype inference or runtime dispatch; visible mutation can invalidate proof |
| TypeScript/TSX | Exact lexical or contained imported declaration and complete import/re-export statements | Project/package controls affect validation/refresh but their full source is not in the packet. Generic shadowing, ambiguous exports and unsupported computations stay unresolved; no structural assignability, inferred runtime type or JSX dispatch |
| Go | Exact package identity, import/package clauses and full contained `go.mod`/`go.work`/replacement controls | No implicit interface satisfaction, inferred method sets, promoted dispatch or active build/cgo/platform selection; dot/blank imports do not create symbol targets |
| Rust | Exact lexical or Cargo/module-owned imported declaration, complete import/re-export/module statements, cfg attributes and Cargo controls | `declared_possible` retains supported conditions without choosing an active build. Divergent, inaccessible, external and unowned origins stay unproven; no macro expansion, associated projection inference, trait-object dispatch or implementing census |

Go and Rust conservatively carry all indexed controls of their respective
families. Large workspaces can therefore exhaust the evidence budget even for a
short dependency path. A delivered related definition and its entire selected
proof path form one atomic bundle; a budget-limited bundle is omitted. Anchors
may be clipped on UTF-8 boundaries and report `complete=false`. Check packet
omissions and the source coverage state independently of relationship scope.
Use `loci_graph_references(family="type")`, the default symbol family and
`loci_graph_calls` for specific unresolved reasons beyond aggregate omissions.
For JS/TS resolver-control paths and hashes, inspect import/reference diagnostics;
read the named controls separately when their contents matter to the question.

`loci_get(include_type_context=true)` remains a bounded compatibility expansion
over outgoing type records with supporting lines. It does not provide the full
Go/Rust control-source, configuration or reverse impl-selection contract above. Use
`loci_explore` when the question requires those proofs, and ordinary exact get
when editing a complete declaration.

## Measured workflow scope

The [W4.7 review](../../../docs/reviews/2026-09-13-multilingual-workflow-measurement.md)
retains 114 attempts and exact independent replay. Python, JavaScript, Go and
Rust comparison claims are withheld because of incomplete evaluator accounting;
the maintained Python and TSX controls record measured coverage/quality and cost
limits. Only the single Markdown section-navigation control passes every
workflow gate. Use the capability matrix for implemented authored semantics;
this measurement establishes no programming-language efficiency recommendation.

Check required relationships as well as source coverage. Compact selection can
deliver correct definitions while omitting available alternate paths, or stop
at declared anchor/hop/selection bounds. Follow up on the specific missing
source or proof; a correct answer or a packet with valid selected proofs does
not establish complete contract coverage.

Exact `loci_file` and grep read mirrored indexed source. A present `go.mod` or
`Cargo.toml` can
therefore return a cache miss through those tools even while exploration can
hydrate its complete control source. Treat that as a retrieval-surface limit,
not evidence that the file is absent. Inspect the returned control proof or use
an authorized targeted filesystem read when full control contents are required.
Keep authored relationships distinct from model assertions of runtime certainty.

## JavaScript and TypeScript

Inspect `resolution_basis` and `resolution_control_files` before explaining
why a file target was selected. Supported sources are `.ts`, `.tsx`, `.mts`,
`.cts`, `.js`, `.jsx`, `.mjs`, and `.cjs`. The bounded resolver can use
relative paths, standard `tsconfig.json`/`jsconfig.json` controls, declared
package-json or pnpm workspaces, package `exports`/`imports`, self-references,
and conservative legacy entries. Workspace edges require a unique active
package and an explicit dependency declaration by the importing package.

Loci intentionally does not inspect installs or lockfiles, execute toolchains
or repository code, use the network, model custom loaders or bundler aliases,
or resolve dynamic `import()` and shadowable `require()` calls.

## Go

Go resolution is repository-contained and bounded. It supports same-module
packages, explicitly active contained workspace modules, and contained local
replacements backed by direct unambiguous requirements. It enforces
nested-module ownership and `internal` visibility, rejects command packages as
targets, and excludes vendor, test-only, missing, invalid, or conflicting
package directories. Unsupported cases remain inspectable unresolved records,
not guessed edges.

Loci never runs Go or repository code, reads an ambient workspace, downloads
modules, implements minimal version selection, follows remote replacements,
models vendoring, or evaluates build/platform/cgo constraints.

## Rust

Rust resolution is repository-contained and bounded. It supports strict Cargo
packages/workspaces/targets, inherited or direct contained path dependencies,
same-package libraries, explicit inline/external module trees, edition-aware
paths, definite module aliases/re-exports, dependency-kind rules, and known
module visibility. It never binds by repository-wide filename, package-name,
or crate-name similarity. Registry/git/standard-library crates remain
external.

Configuration-dependent relationships resolve only when all supported
alternatives converge and are labeled
`resolution_configuration="declared_possible"`; unconditional relationships
are labeled `"unconditional"`. Divergent alternatives stay ambiguous.

Loci never runs Cargo/rustc/repository code, uses the network or ambient
toolchain state, reads lockfiles or Cargo caches, chooses an active feature,
target, profile, or cfg set, expands macros/generated modules, infers
undeclared files, or creates a call edge from an import alone. A Rust import
edge means only that the declared source can depend on the contained endpoint;
it does not mean the current default Cargo build activates that edge. The
resolved-symbol reference layer reaches a terminal Rust item only for the
bounded, visibility-checked, configuration-convergent subset.

Normal unresolved outcomes do not degrade graph health. Loci does not guess
targets by bare name, maintain a separate top-level import store, or expose an
import CLI command.
