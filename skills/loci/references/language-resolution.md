# Language-specific resolution

## Contents

- JavaScript and TypeScript
- Go
- Rust

Treat unresolved, ambiguous, external, inaccessible, unsupported, and
unsupported-configuration observations as bounded records with an explicit
`unresolved_reason`; they never become graph edges. Invalid controls degrade
graph health. Inspect aggregate file-node, Go-package, Rust-crate, and import
counts with `loci_graph_health`.

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
