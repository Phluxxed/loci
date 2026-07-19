# Plan: Extensible Graph Retrieval Stage 9 — Cargo-aware Rust Dependency Resolution

- **Status:** owner-approved; implementation in progress (Tasks 1–3 complete)
- **Date:** 2026-07-18
- **Repository:** `/Users/brummerv/loci`
- **Governing design:** `docs/design/2026-07-13-extensible-graph-retrieval-design.md`
- **Predecessor:** `docs/plans/2026-07-18-extensible-graph-retrieval-stage-8-javascript-typescript-import-resolution.md`
- **Live baseline:** commit `2a3b33505ba388e652e257c686edadbc524df4e6`
- **Collected baseline:** 665 tests
- **Frozen benchmark:** `/Users/brummerv/llm-wiki/tests/fixtures/graph_shape_traversal_stage3.json`
- **Frozen benchmark SHA-256:** `c52def1bdf592ad735149d199910f74183598eccd9ccf8064335fa0cd0e84e27`

## Goal

Make Loci understand deterministic, repository-contained Rust dependencies from
the evidence Rust and Cargo actually use.

Today Loci parses Rust symbols and notices a `use` declaration, but it stores an
entire grouped use tree as one string and deliberately reports every Rust import
as `unresolved/unsupported_language`. It does not know which `Cargo.toml` owns a
file, which target compiles it, what local crate a dependency alias names, where
an external `mod` declaration loads its source, or whether a module route is
visible.

Stage 9 will add a bounded static resolver for:

- Cargo packages, workspaces, conventional and explicit targets;
- contained path dependencies and inherited workspace dependencies;
- Cargo package names, dependency aliases, library crate names, target kinds,
  editions, optional dependencies, target conditions, and required features;
- Rust `use` trees, `extern crate`, external `mod` declarations, inline module
  scope, literal `#[path]`, `crate`, `self`, `super`, absolute paths, and
  edition-specific bare paths;
- definite module aliases and re-exports; and
- Rust module visibility along every module route Loci asserts.

The result remains a directed, evidence-backed relationship from an importing
Rust file to exactly one indexed Rust file or one stable Cargo target/crate node.
If the contained evidence does not converge on one endpoint, Loci keeps an
inspectable unresolved record and emits no trusted edge.

“Complete” in this plan means complete for the explicit static contract below.
It does not mean reproducing `cargo metadata`, rustc name resolution, macro
expansion, build-script output, or a particular feature/target invocation by
executing those systems.

## Plain-language Outcome

Given:

~~~text
repo/
├── Cargo.toml                         workspace members = ["app", "core"]
├── app/
│   ├── Cargo.toml                     core_api = { package = "core", path = "../core" }
│   └── src/main.rs                    use core_api::format::render;
└── core/
    ├── Cargo.toml                     package core, library crate core
    ├── src/lib.rs                     pub mod format;
    └── src/format.rs                  pub fn render(...) { ... }
~~~

Loci will be able to prove:

~~~text
app/src/main.rs::__file__#file
    -- loci:imports / import-resolved -->
core/src/format.rs::__file__#file
~~~

It will explain that `core_api` is a dependency alias declared by
`app/Cargo.toml`, that the path points to the contained `core` package, that the
package exposes a library crate, and that `format` is a public external module
declared by `core/src/lib.rs`.

For `use core_api::Render`, where `Render` is an item rather than a module, this
stage will target the stable `core` library-crate node. It proves which crate
owns the requested item; resolving `Render` itself belongs to the next roadmap
stage.

If `format` is private, the observation becomes `unresolved/inaccessible`. If
the dependency is registry- or git-backed, it becomes `unresolved/external`. If
two target-specific dependency declarations map `core_api` to different local
crates, it becomes `unresolved/ambiguous`. None of those cases becomes an edge.

## Authorization and Review Posture

The owner selected Cargo-aware Rust resolution as the next dependency-layer
stage and approved this implementation boundary on 2026-07-18.

That approval authorizes:

1. one conditional runtime dependency, `tomli`, for Python versions below 3.11;
2. additive Rust observation, import-record, crate-node, service, and MCP result
   fields described below;
3. graph-state and extractor version bumps with full rebuild rather than a
   compatibility shim; and
4. incremental implementation and direct commits/pushes under the repository’s
   standing workflow rule.

Implementation still ends at a separate final review gate. Stage 9 is not
called accepted until the final evidence packet is explicitly approved.

## Reconciliation with Governing Documents

### Extensible graph design

`docs/design/2026-07-13-extensible-graph-retrieval-design.md` places Cargo-aware
Rust resolution immediately after accepted Stage 8, before symbol references or
cross-file calls. It requires crate, package, workspace, module, feature, and
visibility boundaries under a separate design and review gate.

This plan is that gate. It does not pull symbol ownership or call binding
forward from later stages.

### Earlier graph trust design

`docs/design/2026-06-10-graph-layer-design.md` requires deterministic evidence,
directed importer-to-dependency edges, and honest unresolved outcomes. It also
forbids repository-wide bare-name fallback.

Stage 9 therefore resolves a Rust name only through its owning crate context,
lexical module scope, Rust edition, Cargo dependency table, and explicit module
declarations. It never searches the repository for a matching `.rs` filename,
crate name, package name, or symbol after a legitimate resolution path fails.

### Superseded import plan

`docs/plans/2026-07-01-import-dependency-graph.md` remains extraction research,
but its “best effort” Rust mapping is not an acceptable resolver contract. Stage
6 superseded its proposed top-level import store and CLI.

Stage 9 keeps the accepted `index.json.graph` import records,
`loci:imports`/`import-resolved` edges, `graph_imports()` service operation, and
`loci_graph_imports` MCP tool. It does not add the old import store, an import
CLI, or filename-based guessing.

## Official Semantics Used

Implementation is grounded in primary documentation:

- [Cargo manifest format](https://doc.rust-lang.org/cargo/reference/manifest.html)
  defines `Cargo.toml`, packages, editions, targets, dependencies, features, and
  workspace inheritance.
- [Cargo targets](https://doc.rust-lang.org/cargo/reference/cargo-targets.html)
  defines library, binary, example, test, benchmark, and build-script crates,
  conventional roots, auto-discovery controls, target names, paths, editions,
  and `required-features`.
- [Cargo package layout](https://doc.rust-lang.org/cargo/guide/project-layout.html)
  defines the conventional source locations Stage 9 discovers.
- [Cargo workspaces](https://doc.rust-lang.org/cargo/reference/workspaces.html)
  defines root and virtual manifests, member/exclude patterns, automatic local
  path members, package workspace pointers, and inherited package/dependency
  fields.
- [Cargo dependency specification](https://doc.rust-lang.org/cargo/reference/specifying-dependencies.html)
  defines declaring-manifest-relative path dependencies, dependency renaming,
  workspace inheritance, dependency kinds, optional dependencies, and
  target-specific dependency tables.
- [Cargo features](https://doc.rust-lang.org/cargo/reference/features.html)
  defines optional-dependency features, `dep:` activation, feature unification,
  and invocation-dependent feature selection.
- [Rust crates and source files](https://doc.rust-lang.org/reference/crates-and-source-files.html)
  defines a crate’s source-file/module relationship.
- [Rust modules](https://doc.rust-lang.org/reference/items/modules.html) defines
  inline modules, external module source files, module filename alternatives,
  and literal `path` overrides.
- [Rust use declarations](https://doc.rust-lang.org/reference/items/use-declarations.html)
  defines grouped use trees, aliases, `self`, globs, public re-exports, and the
  2015/2018 path differences.
- [Rust extern-crate declarations](https://doc.rust-lang.org/reference/items/extern-crates.html)
  define crate bindings, aliases, extern-prelude insertion, and the exact
  `extern crate self as name` current-crate form.
- [Rust paths](https://doc.rust-lang.org/reference/paths.html) defines `::`,
  `crate`, `self`, and repeated `super` qualifiers.
- [Rust visibility and privacy](https://doc.rust-lang.org/reference/visibility-and-privacy.html)
  defines private ancestry access and restricted `pub` scopes.
- [Rust preludes](https://doc.rust-lang.org/reference/names/preludes.html)
  defines the extern prelude and edition behavior.
- [Rust conditional compilation](https://doc.rust-lang.org/reference/conditional-compilation.html)
  defines `cfg` as configuration-dependent source inclusion.
- [Python `tomllib`](https://docs.python.org/3/library/tomllib.html) provides a
  read-only TOML 1.0 parser from Python 3.11 and explicitly recommends bounding
  untrusted input size.
- [Tomli](https://github.com/hukkin/tomli) is the standard-library parser’s
  maintained backport and documents the conditional dependency/import pattern
  for Python below 3.11.

Stage 9 narrows these semantics to repository evidence that can be reproduced
without an ambient toolchain or build invocation.

## Live Implementation Baseline

Loci inspection on 2026-07-18 established:

- `src/loci/parser/languages.py` indexes `.rs`, extracts functions, structs,
  enums, traits, impls, and constants, and declares only `use_declaration` as an
  import node.
- `src/loci/parser/imports.py` stores the entire `argument` of a Rust `use` as
  one `RawImport`. It does not expand brace trees or extract scopes,
  visibility, `extern crate`, external `mod`, `#[path]`, or configuration state.
- Tree-sitter exposes the required syntax as `scoped_use_list`, `use_list`,
  `use_as_clause`, `use_wildcard`, `extern_crate_declaration`, `mod_item`,
  `visibility_modifier`, and preceding `attribute_item` nodes.
- `src/loci/graph/imports.py` supports only file and Go package targets,
  restricts resolution provenance to JavaScript/TypeScript, and explicitly
  rejects every resolved Rust record.
- `resolve_imports()` builds Python, JavaScript/TypeScript, and Go resolver
  indexes, then returns `unresolved/unsupported_language` for Rust.
- `src/loci/graph/materialize.py` and `src/loci/service.py` have no Cargo or Rust
  context parameter.
- `RepositoryScan` discovers Go and JavaScript controls but not `Cargo.toml`.
- stable Go package nodes demonstrate the accepted pattern for a zero-width,
  metadata-validated synthetic endpoint; retrieval and index verification have
  Go-specific helpers that must be generalized for Rust crate nodes.
- `GRAPH_STATE_SCHEMA_VERSION` is 4, `EXTRACTOR_VERSION` is 7,
  `INDEX_SCHEMA_VERSION` is 5, and `GRAPH_SCHEMA_VERSION` is 1.
- the project supports Python 3.10+, but TOML parsing is not a declared runtime
  dependency. The current lock happens to contain Tomli transitively; Stage 9
  must not rely on that accident.
- the clean `master` baseline matches `origin/master`, collects 665 tests, and
  the frozen benchmark file matches its recorded checksum.

No existing public tool needs to be replaced.

## Frozen Stage 9 Contract

### Included

Stage 9 supports:

1. strict, bounded `Cargo.toml` parsing;
2. standalone packages, root packages, virtual workspaces, workspace
   `members`/`exclude`, and explicit `package.workspace` pointers;
3. package and edition inheritance from `[workspace.package]` where relevant to
   target construction;
4. direct normal/dev/build dependencies, target-specific dependency tables,
   optional dependencies, dependency `package` renames, and
   `workspace = true` inheritance;
5. contained path dependencies whose exact target manifest and package/library
   identity are present;
6. library, binary, example, test, benchmark, and build-script target crates,
   including conventional discovery and explicit target tables;
7. per-target edition and `required-features` metadata;
8. grouped/nested use-tree leaf expansion, aliases, `self`, and globs;
9. `extern crate`, including aliases needed by edition 2015 and exact
   `extern crate self as ...` current-crate aliases;
10. inline and external module declarations, both supported module filename
    forms, and direct literal `#[path = "..."]`;
11. edition 2015 and 2018/2021/2024 path semantics;
12. exact current-crate, lexical-module, extern-prelude, same-package-library,
    and contained dependency bindings;
13. definite non-glob module aliases/re-exports through a bounded fixed point;
14. private, `pub`, `pub(crate)`, `pub(self)`, `pub(super)`, and valid
    `pub(in path)` module visibility; and
15. explicit configuration provenance distinguishing unconditional from
    declared-possible results.

### Explicitly outside Stage 9

Stage 9 does not:

- run `cargo`, `rustc`, `rustdoc`, build scripts, procedural macros, generators,
  tests, examples, or repository binaries;
- use the network, registry index, git checkout, Cargo home, target directory,
  ambient workspace, environment variables, or installed toolchain state;
- parse `Cargo.lock` or reproduce Cargo version/source selection;
- resolve registry or git dependencies into repository files, even if a
  same-named package happens to exist locally;
- choose an active feature set, target triple, profile, or `cfg` expression;
- expand declarative/procedural macros, `include!`, generated modules, or
  macro-generated imports;
- treat `cfg_attr(..., path = ...)` or another configuration-dependent module
  source override as definite;
- infer an undeclared module merely because a plausible `.rs` file exists;
- resolve terminal structs, traits, functions, types, macros, variants, or
  associated items; or
- add cross-file call edges.

Those cases remain external, unsupported, inaccessible, not indexed, or
ambiguous as appropriate. A later stage may extend them only through another
reviewed contract.

## Architecture Decisions

### 1. Cargo targets become stable crate nodes

A Cargo package may compile several independent crates with different roots,
editions, features, and dependency kinds. A package node would therefore be too
coarse, while selecting an arbitrary source file would be false.

Every valid indexed Cargo target receives one zero-width `kind="crate"`,
`language="rust"` `Symbol` anchored to its exact root source file.

Stable ID:

~~~text
<manifest-source>::<target-kind>:<crate-name>#crate
~~~

Example:

~~~text
core/Cargo.toml::lib:core#crate
~~~

The node metadata is:

~~~json
{
  "loci": {
    "rust_crate_node": true,
    "manifest": "core/Cargo.toml",
    "package_name": "core",
    "package_root": "core",
    "target_kind": "lib",
    "target_name": "core",
    "crate_name": "core",
    "crate_root": "core/src/lib.rs",
    "edition": "2024",
    "required_features": []
  }
}
~~~

`file_path`, `content_hash`, and drift verification refer to the crate-root
source. `qualified_name` is the stable ID prefix without `#crate`; `name` is the
Rust crate name. Duplicate target identities invalidate the package context.

### 2. Import targets distinguish files, Go packages, and Rust crates

`ImportTargetKind` becomes:

~~~python
ImportTargetKind: TypeAlias = Literal["file", "package", "crate"]
~~~

- external `mod foo;` and a path whose deepest definite endpoint is an external
  module source target a file node;
- a use that reaches only a crate root/terminal item owner targets a crate node;
- Go continues to target package nodes; and
- Python and JavaScript/TypeScript continue to target file nodes.

`ImportRecord` gains `target_crate`. Exactly one target-shape field is populated
for a resolved record. Rust crate metadata exposes the Cargo package without
overloading Go’s `target_package` field.

Materialization suppresses both ordinary identical-node self-edges and a Rust
file-to-crate edge when the target crate’s root is the importing file itself.
The resolved observation remains inspectable; a crate root does not acquire a
fake dependency on its own synthetic identity. Same-package library edges from
another target root remain valid.

### 3. Rust extraction records syntax Loci will need after incremental reuse

`RawImport` gains an optional strict `rust` context rather than scattering
Rust-only nullable fields across the generic record:

~~~python
RustObservationKind: TypeAlias = Literal["use", "module", "extern_crate"]
RustConfiguration: TypeAlias = Literal[
    "unconditional",
    "conditional",
    "unsupported",
]

@dataclass(frozen=True, slots=True)
class RustImportContext:
    kind: RustObservationKind
    lexical_module_path: tuple[str, ...]
    visibility: str
    module_level: bool
    configuration: RustConfiguration
    path_override: str | None = None

@dataclass(frozen=True, slots=True)
class RawImport:
    source_file: str
    language: str
    line: int
    text: str
    specifier: str
    imported_name: str | None
    type_only: bool
    is_reexport: bool
    source_hash: str
    rust: RustImportContext | None = None
~~~

For non-Rust observations, `rust` must be null. Every Rust observation requires
it and must have `type_only=False`.

- one expanded `use` leaf has `kind="use"`, the normalized complete leaf path
  in `specifier`, and the local alias/imported leaf in `imported_name`;
- `mod foo;` has `kind="module"`, `specifier="foo"`, `imported_name="foo"`,
  and a direct literal path in `path_override` when present; and
- `extern crate actual as local;` has `kind="extern_crate"`,
  `specifier="actual"`, and `imported_name="local"`.

`lexical_module_path` contains only inline-module ancestry within that source
file. The crate index prepends the file’s canonical module path. `module_level`
prevents block-local aliases from being incorrectly treated as module-wide.

`visibility` is one canonical value: `private`, `pub`, `pub(crate)`,
`pub(self)`, `pub(super)`, or `pub(in <normalized-path>)`. Invalid restricted
visibility makes only that observation unsupported. `is_reexport` is true for
non-private Rust `use`/`extern crate`, preserving the existing generic flag.

Direct `cfg` makes the observation `conditional`. A resolution-changing
`cfg_attr`, malformed/unsupported path attribute, or macro-sensitive source
choice makes it `unsupported` and therefore unable to create an edge.

### 4. The graph is a declared-possible static dependency graph

Cargo features, target conditions, `required-features`, and Rust `cfg` are
selected by a build invocation Loci does not have. Stage 9 will not silently
pretend it knows the active build.

`ImportRecord` gains:

~~~python
RustResolutionConfiguration: TypeAlias = Literal[
    "unconditional",
    "declared_possible",
]

resolution_configuration: RustResolutionConfiguration | None = None
~~~

Every resolved Rust record requires this field. It is `declared_possible` when
the source observation is conditional or the crate/dependency/target binding is
optional, target-specific, or feature-gated; otherwise it is `unconditional`.
Other languages keep null in Stage 9.

This means Rust traversal answers “can this declared source depend on that
contained endpoint?” It does not answer “does Cargo’s default build activate
this edge?” `loci_graph_imports` exposes the distinction. An active-build graph
would require an explicit feature/target input contract in a future stage.

When configuration alternatives produce different endpoints, the observation
is `unresolved/ambiguous`, not several trusted targets. Alternatives that all
converge on the same endpoint may resolve as `declared_possible`.

### 5. Cargo loading is pure, bounded, and repository-contained

`src/loci/graph/rust_crates.py` will parse candidate manifests from bytes using
`tomllib` on Python 3.11+ and `tomli` on Python 3.10. It will use the existing
contained-file safety pattern: `lstat`, regular-file check, symlink rejection,
resolved containment, bounded read, and post-read identity/size verification.

The declared PEP 621 dependency entry is:

~~~toml
dependencies = [
  "tomli>=2.0.0,<3; python_version < '3.11'",
]
~~~

No parser is hand-written, and no transitive dependency is assumed.
Tomli is a zero-dependency, MIT-licensed backport of the standard-library
parser; it is installed only on Python 3.10 under the existing support floor.

Workspace patterns are evaluated only against discovered contained manifest
directories. Invalid/unsupported patterns reject that workspace rather than
partially selecting members. A contained path dependency resolves only to the
exact `Cargo.toml` in the normalized dependency directory and only when its
declared package name matches the dependency’s `package` expectation.

### 6. Targets and dependency kinds remain separate

Target discovery creates:

- at most one library target;
- explicit and auto-discovered binary, example, test, and benchmark targets;
- a build-script target when enabled and indexed; and
- no target for a missing, escaping, symlinked, duplicate, or non-indexed root.

Target edition uses an explicit target edition when valid, then the owning
package/workspace-inherited edition, and finally Cargo’s documented `2015`
default when omitted. Only `2015`, `2018`, `2021`, and `2024` are accepted by
this stage; an unknown edition rejects that target context.

Dependency availability is target-aware:

- normal dependencies apply to library, binary, example, test, and benchmark
  target contexts;
- dev dependencies additionally apply only to examples, tests, and benchmarks;
- build dependencies apply only to the build-script target;
- the package library crate is available by its crate name to the package’s
  binary/example/test/benchmark targets, but not as a self-dependency of the
  library or build script; and
- target-specific tables are declared-possible additions to their matching
  dependency kind, not evaluated platform truth.

If multiple applicable declarations for one code-visible alias converge on the
same contained library crate, the binding is usable and configuration-aware. If
they disagree, it is ambiguous.

Registry-only and git dependencies are external. A dependency with both a
version and contained `path` uses the path for this repository-local graph.

### 7. Only explicit module declarations create the module tree

Each crate starts from its exact target root. The builder follows only extracted
external `mod` observations reachable from that root, plus inline-module scope
recorded on nested observations.

For `mod foo;`, the builder applies the edition/source-file module directory
rules and tests the two legitimate filenames. Zero indexed candidates is
`not_indexed`; two candidates is `ambiguous`. A direct literal `#[path]` is
resolved relative to the declaring source under Rust’s documented rules and
must remain contained and indexed.

A plausible file that is not reachable from a crate root through explicit
module declarations does not belong to that crate. There is no directory sweep
or filename fallback.

A file may belong to more than one target crate. A Rust observation resolves
only when every applicable owning context that can interpret it converges on
the same endpoint; endpoint disagreement is ambiguous. If any convergent
context is conditional, the merged result widens to `declared_possible`.

### 8. Path resolution is edition- and scope-aware

For each owning crate/module context:

- `crate::...` starts at the current crate root;
- `self::...` starts at the current lexical module;
- repeated `super::...` walks parents and rejects escape above the root;
- in edition 2015, an unqualified `use` path starts at the crate root, and an
  external crate must have a definite `extern crate` binding;
- from edition 2018 onward, an unqualified first segment checks the current
  lexical module’s declared module/item aliases before the extern prelude; a
  local name shadows an external crate; and
- `::name` means crate root in 2015 and extern prelude from 2018 onward.

The resolver walks known module segments and stops at the deepest definite
module file. Remaining terminal segments are treated as not-yet-resolved items
owned by that file/crate. It never searches for the item by name.

Standard-library/prelude crates such as `std`, `core`, `alloc`, and
`proc_macro` have no contained target and remain external unless an explicit,
valid contained Cargo binding proves otherwise.

### 9. Definite module aliases and re-exports use a bounded fixed point

Module-level, non-glob `use`/`extern crate` observations that resolve exactly to
a known module or crate may introduce a local alias. Public variants may also
introduce an externally visible route.

The builder resolves aliases in deterministic source order until no new route
appears. Duplicate bindings, conflicting targets, cycles, globs, block-local
scope, item aliases, or exhaustion of the pass/candidate bounds do not become
routes. Their own dependency observation may still resolve to the deepest
definite endpoint, but later paths cannot rely on an uncertain alias.

This is enough for definite module re-export façades without claiming resolved
symbol references.

### 10. Visibility is checked for every known module segment

For an intra-crate route, private modules are visible only from their defining
module and descendants. Restricted `pub` forms are normalized to an allowed
ancestor scope and checked against the importer’s module path.

For a route entered through another crate, every known canonical or re-exported
module segment must be publicly reachable. `pub(crate)` and narrower routes are
not external APIs. A private or too-narrow module produces
`unresolved/inaccessible`.

Stage 9 does not claim the visibility of the unresolved terminal item. It proves
only the crate/module ownership prefix; item visibility belongs to symbol
resolution.

### 11. Normal uncertainty is data, invalid control context is diagnostic

Normal import outcomes reuse the accepted reasons:

- `external`
- `not_indexed`
- `ambiguous`
- `invalid_specifier`
- `inaccessible`
- `unsupported_configuration`

They remain inspectable and do not degrade graph health.

Malformed/unsafe/over-limit Cargo or crate contexts add bounded diagnostics:

- `GRAPH_CARGO_MANIFEST_INVALID`
- `GRAPH_CARGO_WORKSPACE_INVALID`
- `GRAPH_RUST_CRATE_INVALID`
- `GRAPH_RUST_MODULE_INVALID`
- `GRAPH_RUST_INDEX_LIMIT_EXCEEDED`

Bad Rust controls must not prevent ordinary source/symbol indexing. They do
degrade graph health because the resolver context itself is incomplete.

## Threat Model and Resource Bounds

Repository manifests and Rust source are untrusted input. The loader and builder
must resist path escape, symlink substitution, oversized/deep controls,
workspace expansion, target/dependency explosion, module cycles, use-tree
explosion, and alias fixed-point abuse.

Frozen Cargo/index constants in `src/loci/graph/rust_crates.py`:

~~~python
MAX_CARGO_CONTROL_BYTES = 1_048_576
MAX_CARGO_CONTROL_FILES = 10_000
MAX_CARGO_TOTAL_BYTES = 67_108_864
MAX_CARGO_TOML_DEPTH = 64
MAX_CARGO_WORKSPACE_PATTERNS = 1_000
MAX_CARGO_PACKAGES = 10_000
MAX_CARGO_TARGETS = 50_000
MAX_CARGO_DEPENDENCIES = 100_000
MAX_RUST_MODULE_DECLARATIONS = 250_000
MAX_RUST_OBSERVATIONS = 1_000_000
MAX_RUST_MODULE_DEPTH = 128
MAX_RUST_RESOLUTION_CANDIDATES = 256
MAX_RUST_ALIAS_PASSES = 128
~~~

The extraction-layer bound remains in its owning module,
`src/loci/parser/imports.py`:

~~~python
MAX_RUST_USE_LEAVES_PER_DECLARATION = 1_024
~~~

Rules:

1. bounds reject the whole affected control/context; they never silently
   truncate into a plausible partial graph;
2. manifest paths are normalized repository-relative POSIX paths;
3. absolute paths, NUL, backslashes, empty segments, `.`/`..` escape, symlinks,
   devices, FIFOs, sockets, and post-check file substitution are rejected;
4. TOML duplicate keys and invalid UTF-8 fail the manifest;
5. nested value shapes and counts are validated after parsing;
6. per-control and aggregate manifest-byte bounds are enforced before a parsed
   context is accepted;
7. arbitrary manifest/source values are not echoed into diagnostics;
8. diagnostics contain bounded reason codes, relative control paths, and
   numeric limits only; and
9. the resolver performs no file I/O after `RustCrateIndex` construction.

## Exact Internal APIs

### Cargo model and loader

New `src/loci/graph/rust_crates.py` exports:

~~~python
RustTargetKind: TypeAlias = Literal[
    "lib", "bin", "example", "test", "bench", "build_script"
]
RustDependencyKind: TypeAlias = Literal["normal", "dev", "build"]
RustResolutionBasis: TypeAlias = Literal[
    "rust_module_declaration",
    "rust_module_path",
    "cargo_path_dependency",
    "cargo_workspace_dependency",
    "cargo_package_library",
]
RustResolutionConfiguration: TypeAlias = Literal[
    "unconditional",
    "declared_possible",
]

@dataclass(frozen=True, slots=True)
class RustDependency:
    alias: str
    package_name: str
    kind: RustDependencyKind
    path: str | None
    optional: bool
    default_features: bool
    features: tuple[str, ...]
    target_condition: str | None
    inherited: bool
    source: str

@dataclass(frozen=True, slots=True)
class RustTarget:
    kind: RustTargetKind
    target_name: str
    crate_name: str
    root_file: str
    edition: str
    required_features: tuple[str, ...]

@dataclass(frozen=True, slots=True)
class CargoPackage:
    source: str
    root: str
    name: str
    workspace_source: str | None
    edition: str
    features: Mapping[str, tuple[str, ...]]
    dependencies: tuple[RustDependency, ...]
    targets: tuple[RustTarget, ...]

@dataclass(frozen=True, slots=True)
class CargoWorkspace:
    source: str
    root: str
    member_sources: tuple[str, ...]

@dataclass(frozen=True, slots=True)
class RustCrateProblem:
    code: RustCrateProblemCode
    message: str
    source: str
    details: dict[str, JSONValue]

@dataclass(frozen=True, slots=True)
class CargoContext:
    packages: tuple[CargoPackage, ...]
    workspaces: tuple[CargoWorkspace, ...]

@dataclass(frozen=True, slots=True)
class CargoLoad:
    context: CargoContext
    input_hashes: dict[str, str]
    problems: tuple[RustCrateProblem, ...]

def load_cargo_context(
    repo_path: Path,
    candidates: Sequence[Path],
    *,
    max_control_bytes: int = MAX_CARGO_CONTROL_BYTES,
    max_control_files: int = MAX_CARGO_CONTROL_FILES,
    max_total_bytes: int = MAX_CARGO_TOTAL_BYTES,
) -> CargoLoad: ...
~~~

All tuples and mappings are deterministically ordered/frozen before return.
Problems never contain absolute paths or raw TOML values.

### Crate/module index

~~~python
@dataclass(frozen=True, slots=True)
class RustCrate:
    id: str
    manifest: str
    package_name: str
    target: RustTarget

@dataclass(frozen=True, slots=True)
class RustDependencyBinding:
    source_crate_id: str
    alias: str
    target_crate_id: str
    basis: RustResolutionBasis
    configuration: RustResolutionConfiguration
    control_files: tuple[str, ...]

@dataclass(frozen=True, slots=True)
class RustModuleBinding:
    crate_id: str
    module_path: tuple[str, ...]
    source_file: str
    visibility: str
    configuration: RustResolutionConfiguration

@dataclass(frozen=True, slots=True)
class RustCrateIndex:
    crate_nodes: tuple[Symbol, ...]
    crates_by_id: Mapping[str, RustCrate]
    crate_ids_by_source_file: Mapping[str, tuple[str, ...]]
    modules_by_crate_path: Mapping[
        tuple[str, tuple[str, ...]], tuple[RustModuleBinding, ...]
    ]
    dependencies_by_crate_alias: Mapping[
        tuple[str, str], tuple[RustDependencyBinding, ...]
    ]
    module_failures_by_observation: Mapping[
        tuple[str, str, int, tuple[str, ...], str],
        ImportUnresolvedReason,
    ]

@dataclass(frozen=True, slots=True)
class RustCrateBuild:
    index: RustCrateIndex
    problems: tuple[RustCrateProblem, ...]

@dataclass(frozen=True, slots=True)
class RustImportResolution:
    target_file: str | None
    target_crate: str | None
    target_id: str | None
    basis: RustResolutionBasis | None
    control_files: tuple[str, ...]
    configuration: RustResolutionConfiguration | None
    unresolved_reason: ImportUnresolvedReason | None

def make_rust_crate_id(
    manifest: str,
    target_kind: RustTargetKind,
    crate_name: str,
) -> str: ...

def build_rust_crate_index(
    context: CargoContext,
    *,
    file_nodes: Mapping[str, Symbol],
    observations: Sequence[RawImport],
) -> RustCrateBuild: ...

def resolve_rust_import(
    raw: RawImport,
    *,
    index: RustCrateIndex,
) -> RustImportResolution: ...
~~~

`rust_crates.py` owns the public models, loader contract, validation policy,
and thin public builder/resolver entry points. Private `_cargo_workspace.py`
and `_cargo_targets.py` keep workspace membership and Cargo target-discovery
mechanics out of that stable API module. New `src/loci/graph/_rust_resolution.py`
owns crate/module index construction, alias construction, visibility
evaluation, and
per-import resolution so neither the public module nor generic import plumbing
becomes a monolith. Alias/re-export tables remain private implementation
structures. The public frozen index above contains every lookup the per-import
resolver needs and performs no I/O after construction.

### Parser API

`extract_import_batch()` retains its signature and single-parse behavior. Its
docstring becomes “Extract import/dependency observations and language file
metadata from one source parse.” `ImportExtractionBatch` keeps `imports` and
`go_package`; Rust’s module/extern observations are in `imports`, so no second
Rust metadata channel is required.

`extract_imports()` remains a compatibility wrapper returning only the batch’s
observations.

### Resolver API

`src/loci/graph/imports.py` generalizes provenance:

~~~python
ImportResolutionBasis: TypeAlias = JavaScriptResolutionBasis | RustResolutionBasis

@dataclass(frozen=True, slots=True)
class ImportRecord:
    raw: RawImport
    source_id: str
    target_file: str | None
    target_package: str | None
    target_crate: str | None
    target_kind: ImportTargetKind | None
    target_id: str | None
    status: ImportStatus
    unresolved_reason: ImportUnresolvedReason | None
    resolution_basis: ImportResolutionBasis | None = None
    resolution_control_files: tuple[str, ...] = ()
    resolution_configuration: RustResolutionConfiguration | None = None

def resolve_imports(
    raw_imports: Sequence[RawImport],
    *,
    file_nodes: Mapping[str, Symbol],
    go_packages: GoPackageIndex | None = None,
    javascript_modules: JavaScriptResolutionIndex | None = None,
    rust_crates: RustCrateIndex | None = None,
) -> list[ImportRecord]: ...

def materialize_import_edges(
    records: Sequence[ImportRecord],
    *,
    file_nodes: Mapping[str, Symbol],
    go_packages: GoPackageIndex | None = None,
    rust_crates: RustCrateIndex | None = None,
) -> list[GraphEdge]: ...
~~~

Validation invariants:

- `target_kind="file"` requires only `target_file` and may be used by Rust;
- `target_kind="package"` requires only `target_package` and remains Go-only;
- `target_kind="crate"` requires only `target_crate` and remains Rust-only;
- resolved JavaScript/TypeScript and Rust records require a language-valid
  resolution basis;
- resolved Rust records require resolution configuration and may carry Cargo
  control files;
- unresolved records have no target, basis, or resolution configuration;
- unresolved Rust records have no control files, while JavaScript/TypeScript
  retain the accepted Stage 8 behavior of listing controls that explain a
  failed resolution; and
- Python/Go record bytes and behavior remain unchanged except for strict new
  null fields required by graph-state schema 5.

### Materialization and service APIs

`materialize_graph()` gains only:

~~~python
rust_crates: RustCrateIndex | None = None
~~~

`RepositoryScan` becomes:

~~~python
@dataclass(frozen=True, slots=True)
class RepositoryScan:
    indexable_files: tuple[tuple[Path, str, str], ...]
    go_control_candidates: tuple[Path, ...]
    javascript_control_candidates: tuple[Path, ...]
    cargo_control_candidates: tuple[Path, ...]
~~~

`index_repo()` adds `graph_rust_crates_indexed` to its result. Existing keys and
semantics remain. No existing service function changes signature.

### Public graph-import API

`graph_imports()` keeps:

~~~python
def graph_imports(
    path: str | Path,
    *,
    status: str | None = None,
    file: str | None = None,
    offset: int = 0,
    limit: int = DEFAULT_GRAPH_IMPORT_LIMIT,
) -> dict[str, Any]: ...
~~~

Every item retains existing fields and gains additive fields through the strict
record/raw serialization:

~~~json
{
  "raw": {
    "rust": {
      "kind": "use",
      "lexical_module_path": [],
      "visibility": "private",
      "module_level": true,
      "configuration": "unconditional",
      "path_override": null
    }
  },
  "target_crate": null,
  "target_kind": "file",
  "resolution_basis": "cargo_path_dependency",
  "resolution_control_files": [
    "app/Cargo.toml",
    "core/Cargo.toml"
  ],
  "resolution_configuration": "unconditional"
}
~~~

`loci_graph_imports` keeps its exact MCP input schema and returns the same
additive fields. There is no new MCP tool and no import CLI.

Generic graph node references for Rust crate endpoints add validated attributes:

~~~json
{
  "manifest": "core/Cargo.toml",
  "package_name": "core",
  "package_root": "core",
  "target_kind": "lib",
  "target_name": "core",
  "crate_name": "core",
  "crate_root": "core/src/lib.rs",
  "edition": "2024",
  "required_features": []
}
~~~

`loci_graph_neighbors` remains exact-containment-only. Filtered traversal,
paths, and retrieval consume crate endpoints through the standard graph.

## Resolution Outcome Table

| Evidence | Outcome |
| --- | --- |
| `mod foo;` has one reachable indexed source candidate | resolved file, `rust_module_declaration` |
| both `foo.rs` and `foo/mod.rs` are candidates | `ambiguous` |
| module source is missing/generated | `not_indexed` |
| direct contained literal `#[path]` identifies one indexed file | resolved file, `rust_module_declaration` |
| configuration-dependent path override | `unsupported_configuration` |
| `crate/self/super` reaches one visible known module file | resolved file, `rust_module_path` |
| current-crate path reaches only root/item ownership | resolved current crate node, `rust_module_path` |
| direct contained path dependency alias reaches target root/item | resolved crate, `cargo_path_dependency` |
| same dependency then reaches one public module file | resolved file, `cargo_path_dependency` |
| inherited contained workspace dependency converges | file/crate, `cargo_workspace_dependency` |
| package binary/example/test/bench uses its library crate | file/crate, `cargo_package_library` |
| registry/git dependency, standard library, or absent dependency | `external` |
| local package name exists but no exact Cargo binding does | `external`; no name search |
| module route is too private | `inaccessible` |
| owning crate contexts or target-specific aliases disagree | `ambiguous` |
| all conditional alternatives converge | resolved, `declared_possible` |
| macro/include/generated name is required | `unsupported_configuration` |
| `.rs` file is not reachable from a target root | `unsupported_configuration` |

## Persistence and Freshness

- bump `GRAPH_STATE_SCHEMA_VERSION` from 4 to 5 because `RawImport` and
  `ImportRecord` strict fields change;
- bump `EXTRACTOR_VERSION` from 7 to 9 because Rust observations, inline-module
  ancestry, and synthetic crate-node construction change;
- keep `INDEX_SCHEMA_VERSION` at 5 and `GRAPH_SCHEMA_VERSION` at 1;
- force a full rebuild for any old extractor/graph-state version; and
- do not fabricate Rust scope, crate targets, provenance, or configuration for
  old records.

`index_repo()` performs:

1. one sorted root scan for sources plus Go, JavaScript, and Cargo controls;
2. bounded Go, JavaScript, and Cargo control loading;
3. graph-extension loading;
4. normal source parse/reuse and import/dependency observation extraction;
5. file-node construction;
6. Go package, JavaScript resolution, and Rust crate/module index construction;
7. addition of Go package and Rust crate nodes;
8. graph materialization with all three language indexes; and
9. one atomic store replacement after validation.

Cargo input hashes merge with existing graph-extension, Go, and JavaScript
control hashes. Manifest add/change/delete re-resolves unchanged Rust source.
Rust source add/change/delete already changes file hashes and rebuilds module
ownership. Invalid controls retain stable hash/problem sentinels so
`ensure_fresh_index()` cannot loop forever.

Full and incremental serialized indexes must match. Incremental reuse excludes
old synthetic `package` and `crate` nodes and rebuilds them from current
contexts; retained Rust observations provide the module declarations needed for
unchanged files.

## Exact File Changes

| File | Change |
| --- | --- |
| `pyproject.toml` | Declare conditional Tomli runtime dependency |
| `uv.lock` | Lock the explicit conditional dependency |
| `src/loci/graph/rust_crates.py` | New bounded Cargo loader, public Rust models, and thin builder/resolver entry points |
| `src/loci/graph/_cargo_workspace.py` | Private bounded Cargo workspace membership and path-member mechanics |
| `src/loci/graph/_cargo_targets.py` | Private bounded Cargo target discovery and validation mechanics |
| `src/loci/graph/_rust_resolution.py` | New private target/module/alias/visibility builder and pure per-import resolver |
| `src/loci/parser/languages.py` | Register Rust `extern_crate_declaration` and `mod_item` dependency observations |
| `src/loci/parser/imports.py` | Add strict Rust context, use-tree expansion, `extern crate`, `mod`, attributes, scope, visibility, and bounds |
| `src/loci/graph/imports.py` | Add crate targets, generalized provenance/configuration, and Rust resolution |
| `src/loci/graph/materialize.py` | Thread Rust crate index through resolution and edge materialization |
| `src/loci/graph/contracts.py` | Validate Rust crate endpoints and bump graph-state schema to 5 |
| `src/loci/graph/retrieval.py` | Expose only validated Rust crate-node attributes |
| `src/loci/service.py` | Discover/load/hash Cargo controls, build crate index, add nodes/diagnostics/count, preserve one scan |
| `src/loci/storage/index_store.py` | Bump extractor to 8, exclude/rebuild crate nodes, verify crate-root anchor hashes |
| `tests/graph/test_rust_crates.py` | New Cargo, target, module, alias, visibility, configuration, bounds, and safety tests |
| `tests/parser/test_imports.py` | Rust extraction/use-tree/scope/attribute/limit tests and other-language regressions |
| `tests/graph/test_imports.py` | Record invariants and exact Rust resolution outcomes |
| `tests/graph/test_materialize.py` | Rust file/crate edges, evidence, self-edge suppression, and non-edge cases |
| `tests/graph/test_contracts.py` | Strict crate endpoint and evidence validation |
| `tests/graph/test_state.py` | Schema-5 round trips and old-state rejection |
| `tests/storage/test_index_store.py` | Version rebuild, crate-anchor verify, full/incremental persistence |
| `tests/test_service.py` | End-to-end Cargo discovery, freshness, diagnostics, counts, retrieval, and compatibility |
| `tests/test_mcp_server.py` | Fresh-process additive import/crate output and unchanged input schema |
| `README.md` | Supported Rust/Cargo semantics, declared-possible meaning, and limits |
| `skills/loci/SKILL.md` | Agent-facing capability and trust boundary |
| `docs/design/2026-07-13-extensible-graph-retrieval-design.md` | Record proposed Stage 9 now; mark implemented/accepted only after gates |
| `docs/reviews/2026-07-18-extensible-graph-retrieval-stage-9-final-review.md` | New final evidence packet during implementation |

No benchmark fixture, llm-wiki source, Anvil source, Cargo manifest in another
repository, or generated output is modified.

## Incremental Implementation Tasks

Every task begins with focused failing tests, ends green, and is committed and
pushed only after its local gate passes. Tasks stay narrow by behavior; strict
schema/API changes may also update mechanically affected compatibility tests.

### Task 1 — Cargo loader and safety shell

**Implementation status:** complete on 2026-07-18; focused gate, full suite,
build, lock, frozen-benchmark checksum, and Loci integrity checks passed.

Files:

- new `src/loci/graph/rust_crates.py`
- new `src/loci/graph/_cargo_workspace.py`
- new `src/loci/graph/_cargo_targets.py`
- new `tests/graph/test_rust_crates.py`
- `pyproject.toml`
- `uv.lock`

Add the explicit TOML parser dependency, strict/bounded reads, manifest shape
validation, workspace membership, contained path normalization, input hashes,
problems, and all resource bounds. No crate node or import resolves yet.

Gate:

~~~sh
uv run pytest -q tests/graph/test_rust_crates.py
uv lock --check
~~~

### Task 2 — Rust dependency observation extraction

**Implementation status:** complete on 2026-07-18; 82 focused tests and all
692 repository tests passed, the package and lock verified, Loci integrity and
graph health passed, and the frozen-benchmark checksum remained unchanged.

Files:

- `src/loci/parser/imports.py`
- `src/loci/parser/languages.py`
- `tests/parser/test_imports.py`
- `src/loci/storage/index_store.py`
- `tests/storage/test_index_store.py`

Add `RustImportContext`, use-tree leaf expansion, `extern crate`, external
`mod`, inline lexical scope, visibility, direct attributes, configuration state,
and extraction bounds. Bump extractor version to 8 and prove old indexes rebuild.

Gate:

~~~sh
uv run pytest -q tests/parser/test_imports.py tests/storage/test_index_store.py
~~~

### Task 3 — Cargo targets, crate nodes, and module ownership

**Implementation status:** complete on 2026-07-19; the 171-test affected
surface and all 707 repository tests passed, the lock and package build
verified, and the frozen-benchmark checksum remained unchanged. No judge was
run.

Files:

- `src/loci/graph/rust_crates.py`
- new `src/loci/graph/_rust_resolution.py`
- new `src/loci/graph/_rust_aliases.py`
- new `src/loci/graph/_rust_semantics.py`
- `tests/graph/test_rust_crates.py`
- `src/loci/parser/imports.py`
- `tests/parser/test_imports.py`
- `src/loci/graph/imports.py`
- `tests/graph/test_imports.py`
- `src/loci/storage/index_store.py`
- `tests/storage/test_index_store.py`

Build target discovery, stable crate nodes, exact module trees, literal path
overrides, multi-crate ownership, dependency bindings, alias fixed point,
visibility, and configuration convergence. Add whole-root verification for
validated crate nodes.

The implementation also closes one Task 2/Task 3 boundary hole: inline module
observations now retain their visibility and configuration ancestry, including
empty inline modules, so the crate builder can model them without rereading
source. Extractor version 9 forces old indexes to rebuild. Inline module
observations are explicitly excluded from generic import records because they
describe ownership metadata rather than a dependency; external `mod foo;`
observations remain available for Task 4 resolution.

Gate:

~~~sh
uv run pytest -q tests/graph/test_rust_crates.py tests/storage/test_index_store.py
~~~

**Next implementation boundary:** Task 4 adds schema-5 import records and pure
Rust path resolution. Task 3 deliberately does not materialize Rust import
edges.

### Task 4 — Import record and pure Rust resolution

**Implementation status:** complete on 2026-07-19; 145 focused tests and all
762 repository tests passed, the lock and package build verified, Loci
re-indexed healthy with 1,717/1,717 symbols verified, and the frozen-benchmark
checksum remained unchanged. No judge was run.

Files:

- `src/loci/graph/imports.py`
- new `src/loci/graph/_rust_import_schema.py`
- `src/loci/graph/_rust_resolution.py`
- `src/loci/graph/_rust_aliases.py`
- `src/loci/graph/rust_crates.py`
- `src/loci/graph/contracts.py`
- `tests/graph/test_imports.py`
- `tests/graph/test_state.py`
- `tests/graph/test_contracts.py`
- `tests/storage/test_index_store.py`
- `tests/test_service.py`

Add crate target fields, generalized bases, resolution configuration, schema-5
record serialization, Rust path resolution, and strict invariants. Prove the
existing `GraphIndexState` delegation needs no production edit and preserve
exact Python/JavaScript/TypeScript/Go behavior.

Implementation required three narrow corrections to the originally listed
file boundary: `rust_crates.py` owns the approved public resolution model and
thin entry point; `_rust_aliases.py` retains only proven `extern crate`
bindings for edition 2015; and `contracts.py` owns the schema-version constant.
`_rust_import_schema.py` keeps strict Rust persistence validation out of the
already-large generic resolver. Direct constructor and fresh-process service
tests received only the mechanical schema-5 null fields.

The frozen crate index retains bounded per-observation module failures because
the resolver otherwise cannot distinguish a missing module source from the
explicit two-candidate `foo.rs` versus `foo/mod.rs` ambiguity after index
construction. This is evidence preservation, not a filename fallback: the
builder records only failures from the exact declared-module candidates it
already evaluated.

The broad draft statement that every unresolved record has no controls was
reconciled with accepted Stage 8 behavior: unresolved JavaScript/TypeScript
records may still list the control files that explain failure. Rust unresolved
records remain target-, basis-, control-, and configuration-free. Task 4 does
not materialize Rust edges or wire Cargo discovery into the service; those
remain Tasks 5 and 6.

Gate:

~~~sh
uv run pytest -q tests/graph/test_imports.py tests/graph/test_state.py
~~~

### Task 5 — Edge materialization and contracts

**Implementation status:** complete on 2026-07-19; 171 focused tests and all
798 repository tests passed, the lock and package build verified, Loci
re-indexed healthy with 1,720 symbols, and the frozen-benchmark checksum
remained unchanged. No judge was run.

Files:

- `src/loci/graph/materialize.py`
- `src/loci/graph/contracts.py`
- `tests/graph/test_materialize.py`
- `tests/graph/test_contracts.py`
- `src/loci/graph/imports.py`

Thread Rust context, materialize file/crate edges, validate crate endpoint
metadata and record-backed evidence, and suppress self-edges while consuming
the schema-5 record shape established by Task 4.

`materialize_graph()` and `materialize_import_edges()` now accept the approved
optional `RustCrateIndex`. Rust file targets continue through the generic file
path; crate targets must be present in the supplied index and match its Cargo
identity, root source, zero-width synthetic-node shape, metadata, and root
content hash before an edge is emitted. Resolved observations remain persisted
when the ordinary endpoint IDs match or when a crate-root file resolves to its
own crate identity, but those two self-edge shapes are not materialized.
Another target root in the same package may still depend on the library crate.

The persisted-edge contract independently requires a current Rust crate node,
runtime `imports` type, one matching resolved crate record, exact source line
and hash evidence, normalized contained manifest/root paths, supported target
kind and edition, and deterministic required-feature metadata. It rejects a
crate-root-to-own-crate edge even if malformed graph state is supplied directly.
Python, JavaScript/TypeScript, and Go retain their existing behavior. Cargo
discovery and service wiring remain Task 6.

Gate:

~~~sh
uv run pytest -q tests/graph/test_materialize.py tests/graph/test_contracts.py tests/graph/test_imports.py
~~~

### Task 6 — Service, freshness, diagnostics, and retrieval

Files:

- `src/loci/service.py`
- `src/loci/graph/retrieval.py`
- `tests/test_service.py`
- `tests/storage/test_index_store.py`

Extend the one-pass scan, load/build/hash the Cargo context, rebuild synthetic
nodes, merge bounded diagnostics, add the crate count, expose validated crate
attributes, and prove control/source add/change/delete plus full/incremental
equality.

Gate:

~~~sh
uv run pytest -q tests/test_service.py tests/storage/test_index_store.py
~~~

### Task 7 — MCP and user/agent documentation

Files:

- `tests/test_mcp_server.py`
- `README.md`
- `skills/loci/SKILL.md`
- `docs/design/2026-07-13-extensible-graph-retrieval-design.md`

Prove fresh-process MCP output and document the exact supported/unsupported and
declared-possible semantics. Mark Stage 9 implemented in the governing design
only when all implementation gates pass. The MCP server should need no code
change; if its input or tool set must change, stop for owner review.

Gate:

~~~sh
uv run pytest -q tests/test_mcp_server.py
~~~

### Task 8 — Final verification and owner review packet

Files:

- new `docs/reviews/2026-07-18-extensible-graph-retrieval-stage-9-final-review.md`

Run the evidence matrix, inspect Loci through its real MCP interface, record
compatibility/limitations/security evidence, verify local/remote state, and
present the final owner gate. Do not mark accepted before explicit approval.

## Required Test Matrix

### Cargo loader and security

Prove:

1. package, virtual-workspace, and combined root manifests parse deterministically;
2. invalid UTF-8/TOML, duplicate keys, wrong types, unsupported editions, and
   excessive nesting reject the manifest;
3. oversized, symlinked, non-regular, absolute, escaping, or post-check changed
   controls cannot be consumed;
4. workspace member/exclude patterns, nested workspaces, explicit workspace
   pointers, missing members, and duplicate package ownership are bounded and
   deterministic;
5. direct and inherited dependency tables preserve alias, package, kind,
   optional, default-feature, requested-feature, path, and target-condition
   semantics;
6. path dependencies are relative to the correct declaring workspace/package
   manifest and identify the exact target package;
7. registry/git sources never bind to a same-named repository package;
8. all count bounds reject contexts rather than truncate; and
9. diagnostics contain no host path, raw TOML value, source text, or secret.

### Target and crate construction

Prove:

1. conventional and explicit library/binary/example/test/bench/build targets;
2. target auto-discovery enable/disable controls and duplicate root/name cases;
3. package/target edition, dash-to-underscore crate naming, library name
   override, explicit path, and required features;
4. missing/escaping/symlinked/unindexed roots produce no crate node;
5. stable crate IDs/metadata, deterministic order, searchability, and root-hash
   verification;
6. normal/dev/build dependency availability by target kind;
7. same-package library availability only to legitimate targets; and
8. conflicting target-specific aliases are ambiguous while convergent aliases
   retain declared-possible configuration.

### Rust extraction

Prove:

1. simple, scoped, nested-brace, alias, `self`, trailing-self, and glob use
   observations expand into deterministic leaves;
2. empty braces emit no false import;
3. use-leaf explosion is rejected at the declaration bound;
4. `extern crate` names/aliases and external `mod` declarations are extracted;
5. inline-module ancestry and module-level versus block-local scope;
6. every visibility form normalizes or fails closed;
7. direct literal/raw-string path attributes are captured safely;
8. direct cfg becomes conditional and resolution-changing cfg_attr becomes
   unsupported; and
9. Python, JavaScript/TypeScript, and Go observations remain equivalent with
   `rust=null`.

### Module tree and path semantics

Prove:

1. target roots, inline modules, `foo.rs`, `foo/mod.rs`, nested children, and
   direct path overrides;
2. missing, duplicate, cyclic, too-deep, and unreachable modules;
3. a plausible undeclared file is never selected;
4. 2015 crate-root use paths, required `extern crate` bindings, and exact
   `extern crate self` current-crate aliases;
5. 2018/2021/2024 lexical, extern-prelude, local-shadowing, and `::` behavior;
6. `crate`, `self`, repeated `super`, and root escape;
7. module/item boundary stops at the deepest definite file or crate;
8. module aliases/re-exports converge, while globs/cycles/conflicts/block scope
   do not create routes; and
9. multi-crate source ownership resolves only on convergence.

### Visibility and configuration

Prove:

1. private ancestry access within a crate;
2. public, crate, self, super, and valid ancestor-restricted visibility;
3. external routes require public module segments/re-exports;
4. inaccessible routes emit no edge;
5. unconditional bindings are labeled unconditional;
6. source cfg, optional dependency, target-specific dependency, and required
   features are labeled declared-possible;
7. convergent alternatives resolve once; and
8. divergent alternatives are ambiguous.

### Records, edges, persistence, and compatibility

Prove:

1. schema 5 and extractor 9 force a full rebuild;
2. Rust contexts, target shape, basis, controls, and configuration round-trip
   strictly through a fresh process;
3. resolved module declarations/imports emit one directed file/crate edge with
   exact source evidence;
4. unresolved observations emit no edge and remain paginated/inspectable;
5. file/crate self-edges are suppressed without losing their import record;
6. crate endpoints must be current validated synthetic nodes;
7. full and incremental serialized indexes match;
8. Cargo/source add/change/delete re-resolves unchanged observations;
9. invalid controls reach stable degraded health without refresh loops;
10. `graph_imports` filters/counts/order/pagination/input validation remain;
11. `loci_graph_imports` inputs are unchanged and output additions are exact;
12. Python, JavaScript/TypeScript, and Go records/edges remain behaviorally
    equivalent apart from strict null schema-5 additions;
13. search, outline, get, file, grep, verify, graph health, anchors, traversal,
    paths, retrieval, Markdown profiles, and contributions retain behavior; and
14. repository discovery still traverses the root once.

## Verification Commands

Focused gates run after every task. Final local verification is:

~~~sh
uv lock --check
uv run pytest -q tests/graph/test_rust_crates.py
uv run pytest -q tests/parser/test_imports.py
uv run pytest -q tests/graph/test_imports.py tests/graph/test_materialize.py tests/graph/test_contracts.py tests/graph/test_state.py
uv run pytest -q tests/storage/test_index_store.py tests/test_service.py tests/test_mcp_server.py
uv run pytest -q tests/graph/test_anchor_benchmark.py tests/graph/test_traversal_benchmark.py
uv run pytest -q
uv build
~~~

Then use the production MCP surface against at least three disposable fixture
repositories:

1. a single package with lib/bin, inline/external modules, and visibility;
2. a virtual workspace with renamed/inherited contained path dependencies,
   features, and target-specific declarations; and
3. an adversarial repository containing invalid manifests, path escape,
   ambiguity, cycles, cfg/path uncertainty, and same-name traps.

Required MCP evidence:

- `loci_index` reports Rust crate/import counts and expected graph health;
- `loci_graph_imports` shows resolved/unresolved reasons, crate/file target
  shapes, Cargo controls, and configuration class;
- `loci_graph_traverse_neighbors`, `loci_graph_paths`, and
  `loci_graph_retrieve` reach expected crate/module endpoints;
- `loci_get` reads an exact Rust symbol selected from that graph evidence;
- `loci_verify` passes crate-root synthetic nodes; and
- a fresh server process reads the persisted result without rebuilding.

## Frozen Benchmark Policy

Before implementation and in the final packet, verify:

~~~sh
test "$(shasum -a 256 /Users/brummerv/llm-wiki/tests/fixtures/graph_shape_traversal_stage3.json | awk '{print $1}')" = \
  "c52def1bdf592ad735149d199910f74183598eccd9ccf8064335fa0cd0e84e27"
~~~

The fixture is immutable. Stage 9 does not change Markdown parsing, traversal
ranking, benchmark contracts, or the llm-wiki adapter, so the expensive frozen
benchmark/judge is not run by default. Run its deterministic local tests in the
normal suite. Stop and request owner approval before any fixture edit or paid
judge rerun.

## Final Review Gate

The final packet must include:

1. commit range and exact changed files;
2. focused and full test/build output;
3. frozen benchmark checksum and confirmation of no fixture mutation;
4. disposable-repository MCP evidence for file and crate endpoints;
5. at least one example each for unconditional, declared-possible,
   inaccessible, ambiguous, external, not-indexed, and unsupported outcomes;
6. proof that Cargo/rustc/repository code/network were not invoked by indexing;
7. path/symlink/bounds/diagnostic-redaction evidence;
8. full/incremental and fresh-process equality;
9. Python/JavaScript/TypeScript/Go/Markdown compatibility evidence;
10. documented residual limitations and next-stage boundary;
11. clean worktree and `master == origin/master`; and
12. explicit owner approval.

Review questions:

- Does every trusted Rust edge have exact Cargo/module evidence?
- Can any repository-wide name/filename fallback still create an edge?
- Does every crate endpoint identify one real Cargo target and indexed root?
- Are conditional relationships visibly distinguished from active-build truth?
- Are module privacy and dependency kinds enforced at the supported boundary?
- Can malformed controls or combinatorial source exhaust indexing or leak data?
- Did any later-stage symbol/call resolution enter the implementation?

Any “no,” unexplained ambiguity, public input/tool change, benchmark drift, or
cross-language regression blocks acceptance.

## Rollback

Before final acceptance, rollback is the ordered revert of Stage 9 commits.
Because graph-state 5 and extractor 9 force rebuilds, reverting returns Loci to
the accepted Stage 8 behavior: Rust observations may still be extracted by the
old parser but remain `unresolved/unsupported_language`, and no crate nodes or
Rust edges survive a fresh index.

Do not hand-edit cached indexes, downgrade version constants in place, or keep a
partial compatibility shim. Re-index representative repositories after revert
and rerun the Stage 8 compatibility suite.

## Owner Review Decision

Implementation begins only after the owner approves this boundary, including:

- stable Cargo target/crate nodes;
- declared-possible configuration semantics;
- contained path/workspace dependencies only;
- conditional Tomli support for Python 3.10;
- exact additive APIs and version bumps; and
- the separate final acceptance gate.

Until then, the accepted Stage 8 implementation remains authoritative and Rust
imports remain unsupported in the trusted graph.
